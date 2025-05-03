import os
import re 
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Literal, Optional 
from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, RunContextWrapper

# --- FastAPI Setup ---
app = FastAPI()
# Assuming templates are in the root 'templates' directory relative to workspace root
templates = Jinja2Templates(directory="templates") 

# --- Load API Key ---
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: FATAL: OPENAI_API_KEY not found in .env file or environment variables.")
    exit(1)
else:
    print("OpenAI API Key loaded successfully.")

# --- Pydantic Models (Copied) ---
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

# --- Guardrail Agent (Copied) ---
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
    output_type=ClassificationOutput,
)

# --- Guardrail Function (Copied) ---
async def validate_input_guardrail(ctx: RunContextWrapper, agent: Agent, input_data: str) -> GuardrailFunctionOutput:
    """Guardrail to validate if input is a plausible name or email."""
    print("--- Running Validation Guardrail ---") # Keep console logs for debugging
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
                validation_details = "Input validated as a name (>= 2 parts, allowed characters)."
            else:
                 validation_details = "Validation failed: Name should have at least two parts and contain only letters, hyphens, or apostrophes."

        elif final_input_type == "email":
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
        is_valid = False 
        
    tripwire_triggered = not is_valid
    print(f"Python Validation Result: is_valid={is_valid}, details='{validation_details}'")
    print(f"Tripwire Triggered: {tripwire_triggered}")
    print("------------------------------------")

    output_info = ValidationOutput(
        input_type=final_input_type,
        is_valid=is_valid,
        processed_value=processed_value_from_llm if is_valid else input_data, 
        validation_details=validation_details,
    )

    return GuardrailFunctionOutput(
        output_info=output_info,
        tripwire_triggered=tripwire_triggered,
    )

# --- Specialist Agents (Copied) ---
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

# --- Triage Agent (Copied) ---
triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine if the validated input is a name or an email address and route it to the appropriate specialist agent.",
    handoffs=[name_agent, email_agent], 
    input_guardrails=[
        InputGuardrail(guardrail_function=validate_input_guardrail), 
    ],
)

print("Agents defined successfully.")

# --- API Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the initial HTML form."""
    return templates.TemplateResponse("index.html", {"request": request, "result": None, "query": None})

@app.post("/process", response_class=HTMLResponse)
async def process_query(request: Request, query: str = Form(...)):
    """Processes the user input using the triage agent and guardrails."""
    print(f"Received query: {query}")
    display_result = ""
    
    try:
        # Run the triage agent asynchronously
        agent_result = await Runner.run(triage_agent, query)
        
        # If successful (no exception), get the agent's final output
        if agent_result and agent_result.final_output:
             display_result = agent_result.final_output
             print(f"Agent Response: {display_result}")
        else:
             display_result = "Agent finished, but no final output was generated."
             print(display_result)

    except Exception as e:
        # Handle exceptions, specifically looking for guardrail tripwires
        error_message = str(e)
        print(f"Error during agent run: {error_message}")
        if "triggered tripwire" in error_message.lower():
            # Attempt to extract validation details if possible (might need adjustment based on actual exception object)
            # For now, provide a generic message based on the exception type
            display_result = "Sorry, the input provided is not valid. Please enter a valid full name or email address."
            # Potentially log more details from 'e' if needed for debugging
        else:
            # Handle other potential errors during execution
            display_result = f"An unexpected error occurred: {error_message}"

    # Re-render the template with the result and original query
    return templates.TemplateResponse("index.html", {"request": request, "result": display_result, "query": query})

# --- Uvicorn Run Instructions (Comment) ---
# To run this application:
# 1. Make sure you have uvicorn and fastapi installed: pip install fastapi uvicorn
# 2. Run from the workspace root directory: uvicorn agents_sdk_lee.quickstart_guardrails_webui:app --reload 