import os
import re # Import regex for email validation
from dotenv import load_dotenv
# Updated imports
from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, RunContextWrapper # Added RunContextWrapper 
from pydantic import BaseModel, Field, validator
from typing import Literal, Optional # Added Optional
import asyncio

# Load environment variables from .env file
load_dotenv()

# Check if the API key is loaded (optional but good practice)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in .env file or environment variables.")
    exit(1)
# else: # Optional: uncomment to confirm key is loaded (don't print the key itself)
#     print("OpenAI API Key loaded successfully.")

print("Defining agents and guardrails...")

# --- Pydantic Models ---
class ClassificationOutput(BaseModel):
    """Output model for the validation_agent's classification."""
    input_type: Literal["name", "email", "unknown"] = Field(..., description="Classification of the input")
    processed_value: str = Field(..., description="Input value after case adjustment (name capitalized, email lowercased)")

class ValidationOutput(BaseModel):
    """Output model for the overall guardrail function."""
    input_type: Literal["name", "email", "unknown"]
    is_valid: bool
    processed_value: Optional[str] = None
    validation_details: str

# --- Guardrail Agent ---
# Renamed from guardrail_agent to validation_agent
validation_agent = Agent(
    name="Input Classifier",
    instructions=(
        "Classify the input as 'name' (if it looks like a person's full name) "
        "or 'email' (if it looks like an email address). "
        "If it's a name, capitalize the first letter of each part. "
        "If it's an email, convert it entirely to lowercase. "
        "If unsure or it's neither, classify as 'unknown' and return the original input. "
        "Respond ONLY with a JSON object matching the ClassificationOutput schema with keys 'input_type' and 'processed_value'."
    ),
    output_type=ClassificationOutput, # Expects this structure
)

# --- Guardrail Function ---
async def validate_input_guardrail(ctx: RunContextWrapper, agent: Agent, input_data: str) -> GuardrailFunctionOutput:
    """Guardrail to validate if input is a plausible name or email."""
    print("--- Running Validation Guardrail ---")
    is_valid = False
    validation_details = "Validation failed."
    final_input_type: Literal["name", "email", "unknown"] = "unknown"
    processed_value_from_llm = input_data # Default

    try:
        # 1. Use LLM agent for classification and initial processing
        classification_result = await Runner.run(validation_agent, input_data, context=ctx.context)
        classification = classification_result.final_output_as(ClassificationOutput)
        final_input_type = classification.input_type
        processed_value_from_llm = classification.processed_value
        print(f"LLM Classification: type='{final_input_type}', processed_value='{processed_value_from_llm}'")

        # 2. Perform stricter validation based on classification
        if final_input_type == "name":
            parts = processed_value_from_llm.split()
            # Allow letters, hyphens, apostrophes
            if len(parts) >= 2 and all(re.match(r"^[a-zA-ZÀ-ÖØ-öø-ÿ'\-]+$", part) for part in parts): 
                is_valid = True
                validation_details = "Input validated as a name (>= 2 parts, allowed characters)."
            else:
                 validation_details = "Validation failed: Name should have at least two parts and contain only letters, hyphens, or apostrophes."

        elif final_input_type == "email":
            # Basic email regex check
            if re.fullmatch(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', processed_value_from_llm):
                is_valid = True
                validation_details = "Input validated as an email address."
            else:
                validation_details = "Validation failed: Email format is invalid."
        else: # unknown
             validation_details = "Validation failed: Input could not be classified as name or email."

    except Exception as e:
        print(f"Guardrail Error: Could not process input or parse LLM output. Error: {e}")
        validation_details = f"Guardrail internal error: {e}"
        is_valid = False # Fail validation on error
        
    tripwire_triggered = not is_valid
    print(f"Python Validation Result: is_valid={is_valid}, details='{validation_details}'")
    print(f"Tripwire Triggered: {tripwire_triggered}")
    print("------------------------------------")

    # Prepare final output object for the guardrail
    output_info = ValidationOutput(
        input_type=final_input_type,
        is_valid=is_valid,
        processed_value=processed_value_from_llm if is_valid else input_data, # Return processed only if valid
        validation_details=validation_details,
    )

    return GuardrailFunctionOutput(
        output_info=output_info,
        tripwire_triggered=tripwire_triggered,
    )

# --- Specialist Agents ---
name_agent = Agent(
    name="Name Agent",
    handoff_description="Specialist agent for handling names.",
    instructions="You have been given a person's full name. Thank the user politely for providing the information and then confirm the exact name back to them.",
)

email_agent = Agent(
    name="Email Agent",
    handoff_description="Specialist agent for handling email addresses.",
    instructions="You have been given an email address. Thank the user politely for providing the information and then confirm the exact email address back to them.",
)

# --- Triage Agent ---
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine if the validated input is a name or an email address and route it to the appropriate specialist agent.",
    handoffs=[name_agent, email_agent], # Updated handoffs
    input_guardrails=[
        InputGuardrail(guardrail_function=validate_input_guardrail), # Use the new guardrail
    ],
)

print("Agents defined successfully.")

# --- Main Execution ---
async def main():
    # Get the query from the user
    user_query = input("Please enter your full name OR email address: ")
    
    print(f"\nRunning triage agent with input: '{user_query}'...")
    try:
        # Run the triage agent asynchronously
        result = await Runner.run(triage_agent, user_query)

        # This block might only be reached if guardrails pass OR if they trip 
        # but the runner is configured *not* to raise an exception (depends on SDK/config)
        print("\n--- Final Result ---")
        if hasattr(result, 'guardrail_tripwires') and result.guardrail_tripwires:
             # This path might be less common if exceptions are raised on tripwire
             print("Guardrail tripped! Input is invalid.")
             guardrail_output = result.guardrail_tripwires[0].get('output_info')
             user_error_message = "Sorry, the input provided could not be validated." 
             if guardrail_output:
                  try:
                       details = ValidationOutput.parse_obj(guardrail_output)
                       user_error_message = f"Sorry, the input is not valid: {details.validation_details}"
                  except Exception as parse_error:
                       print(f"(Could not parse guardrail details: {parse_error}) {guardrail_output}")
                       user_error_message = "Sorry, the input provided could not be validated (parsing error)."
             else:
                  print("(No detailed guardrail output available)")
             
             print(f"\n{user_error_message}")
             
        elif result.final_output:
             print(f"Agent Response: {result.final_output}")
        else:
            print("Execution finished, but no final output was generated (potentially unexpected state).")

    except Exception as e:
        # Catch exceptions, including potential guardrail tripwires
        error_message = str(e)
        if "triggered tripwire" in error_message.lower():
            # Specific handling for guardrail tripwire exception
            print("\n--- Final Result ---")
            print("Sorry, the input provided is not valid.")
            # We don't have easy access to detailed validation_details here 
            # because the exception halted execution before returning the result object.
            # Printing the raw error can help debugging:
            print(f"(Debug info: {error_message})")
        else:
            # Handle other potential errors during execution
            print(f"\nAn error occurred during execution: {e}")

# Standard boilerplate to run the async main function
if __name__ == "__main__":
    asyncio.run(main()) 