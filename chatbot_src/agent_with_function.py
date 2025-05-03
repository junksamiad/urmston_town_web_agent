#!/usr/bin/env python
import os
import re 
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Literal, Optional 

# --- Agent SDK Imports ---
from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, RunContextWrapper, function_tool 

# --- Airtable Import ---
from pyairtable import Table

# --- Load Environment Variables ---
load_dotenv()

# OpenAI Key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: FATAL: OPENAI_API_KEY not found.")
    exit(1)

# Airtable Credentials
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")
if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID]):
    print("Error: FATAL: Airtable credentials (API Key, Base ID, Table ID) not found in .env file.")
    exit(1) 
else:
    print("OpenAI and Airtable credentials loaded successfully.")
    print(f"DEBUG: Loaded AIRTABLE_TABLE_ID = {AIRTABLE_TABLE_ID}")

# --- Pydantic Models (Same as before) ---
class ClassificationOutput(BaseModel):
    input_type: Literal["name", "email", "unknown"] = Field(..., description="Classification of the input")
    processed_value: str = Field(..., description="Input value after case adjustment (name capitalized, email lowercased)")

class ValidationOutput(BaseModel):
    input_type: Literal["name", "email", "unknown"]
    is_valid: bool
    processed_value: Optional[str] = None
    validation_details: str

# --- Guardrail Agent (Same as before) ---
validation_agent = Agent(
    name="Input Classifier",
    instructions=(
        "Classify the input as 'name' or 'email'. "
        "If name, capitalize first letter of each part. If email, convert to lowercase. "
        "If neither, classify as 'unknown'. Respond ONLY with JSON: {'input_type': '...', 'processed_value': '...'}."
    ),
    output_type=ClassificationOutput,
)

# --- Guardrail Function (Same as before) ---
async def validate_input_guardrail(ctx: RunContextWrapper, agent: Agent, input_data: str) -> GuardrailFunctionOutput:
    print("--- Running Validation Guardrail ---")
    is_valid = False
    validation_details = "Validation failed."
    final_input_type: Literal["name", "email", "unknown"] = "unknown"
    processed_value_from_llm = input_data 
    try:
        classification_result = await Runner.run(validation_agent, input_data, context=ctx.context)
        classification = classification_result.final_output_as(ClassificationOutput)
        final_input_type = classification.input_type
        processed_value_from_llm = classification.processed_value
        print(f"LLM Classification: type='{final_input_type}', processed_value='{processed_value_from_llm}'")
        if final_input_type == "name":
            parts = processed_value_from_llm.split()
            if len(parts) >= 2 and all(re.match(r"^[a-zA-ZÀ-ÖØ-öø-ÿ'\-]+$", part) for part in parts): 
                is_valid = True
                validation_details = "Input validated as a name."
            else:
                 validation_details = "Validation failed: Name format invalid."
        elif final_input_type == "email":
            if re.fullmatch(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', processed_value_from_llm):
                is_valid = True
                validation_details = "Input validated as an email address."
            else:
                validation_details = "Validation failed: Email format invalid."
        else:
             validation_details = "Validation failed: Input not classified as name or email."
    except Exception as e:
        print(f"Guardrail Error: {e}")
        validation_details = f"Guardrail internal error: {e}"
        is_valid = False 
    tripwire_triggered = not is_valid
    print(f"Python Validation: is_valid={is_valid}, details='{validation_details}'")
    print(f"Tripwire Triggered: {tripwire_triggered}")
    print("------------------------------------")
    output_info = ValidationOutput(
        input_type=final_input_type,
        is_valid=is_valid,
        processed_value=processed_value_from_llm if is_valid else input_data, 
        validation_details=validation_details,
    )
    return GuardrailFunctionOutput(output_info=output_info, tripwire_triggered=tripwire_triggered)

# --- Airtable Tool Function ---
@function_tool
def write_name_to_db(full_name: str) -> str:
    """Writes the provided full name to the Airtable database. Splits the name into first and last name fields."""
    print(f"--- Running Airtable Tool: write_name_to_db ({full_name}) ---")
    try:
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        
        name_parts = full_name.strip().split()
        if len(name_parts) == 0:
             return "Error: Cannot write empty name to database."
        
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "" # Handle single names / just use rest
        
        record_data = {
            'first_name': first_name,
            'last_name': last_name,
            'full_name': full_name # Primary field
        }
        
        response = table.create(record_data)
        print(f"Airtable API Response: {response}")
        # Check response structure if needed, assume success if no exception
        return f"Successfully wrote '{full_name}' to the database."
    
    except Exception as e:
        print(f"Airtable Tool Error: {e}")
        return f"Error: Failed to write '{full_name}' to the database. Details: {e}"
    finally:
         print("---------------------------------------------")


# --- Greeter Agent (NEW) ---
greeter_agent = Agent(
    name="Greeter",
    instructions="Greet the user warmly and clearly ask them to enter their full name OR email address."
    # No tools, handoffs, or guardrails needed for the simple greeting
)

# --- Specialist Agents (Name Agent Updated) ---
name_agent = Agent(
    name="Name Agent",
    handoff_description="Specialist agent for handling names and saving them.",
    instructions="You have been given a person's full name. First, use the 'write_name_to_db' tool to save the name. Then, report the outcome of the saving operation (success or error) to the user, thank them politely for the information, and confirm the exact name back to them.",
    tools=[write_name_to_db] # ADDED TOOL
)

email_agent = Agent(
    name="Email Agent",
    handoff_description="Specialist agent for handling email addresses.",
    instructions="You have been given an email address. Thank the user politely for providing the information and then confirm the exact email address back to them.", 
    # No tools needed for email agent in this example
)

# --- Triage Agent (Same as before) ---
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine if the validated input is a name or an email address and route it to the appropriate specialist agent.",
    handoffs=[name_agent, email_agent], 
    input_guardrails=[
        InputGuardrail(guardrail_function=validate_input_guardrail), 
    ],
)

print("Agents defined successfully.")

# --- Main Execution (Updated Flow) ---
async def main():
    # --- Step 1: Get Greeting --- 
    print("--- Running Greeter Agent ---")
    try:
        greeting_result = await Runner.run(greeter_agent, "initiate") # Dummy input
        if greeting_result.final_output:
            print(f"\nAgent: {greeting_result.final_output}")
        else:
            print("\nAgent: Hello! Please enter your name or email.") # Fallback greeting
    except Exception as e:
        print(f"\nError getting greeting: {e}")
        print("Agent: Hello! Please enter your name or email.") # Fallback greeting
    
    # --- Step 2: Get User Input --- 
    user_query = input("Your input: ") # Updated prompt
    
    # --- Step 3: Process User Input with Triage Agent & Guardrails ---
    print(f"\n--- Running Triage Agent with input: '{user_query}' ---")
    try:
        result = await Runner.run(triage_agent, user_query)
        print("\n--- Final Result ---")
        if hasattr(result, 'guardrail_tripwires') and result.guardrail_tripwires:
             print("Guardrail tripped! Input is invalid.")
             # Extract details if possible
             guardrail_output = result.guardrail_tripwires[0].get('output_info')
             user_error_message = "Sorry, the input provided could not be validated." 
             if guardrail_output:
                  try:
                       details = ValidationOutput.parse_obj(guardrail_output)
                       user_error_message = f"Sorry, the input is not valid: {details.validation_details}"
                  except Exception as parse_error:
                       print(f"(Could not parse guardrail details: {parse_error})")
                       user_error_message = "Sorry, the input provided could not be validated (parsing error)."
             else:
                  print("(No detailed guardrail output available)")
             print(f"\n{user_error_message}")   
        elif result.final_output:
             print(f"Agent Response: {result.final_output}")
        else:
            print("Execution finished, but no final output generated.")
    except Exception as e:
        error_message = str(e)
        if "triggered tripwire" in error_message.lower():
            print("\n--- Final Result ---")
            print("Sorry, the input provided is not valid.")
            print(f"(Debug info: {error_message})")
        else:
            print(f"\nAn error occurred during execution: {e}")

# --- Boilerplate ---
if __name__ == "__main__":
    asyncio.run(main()) 