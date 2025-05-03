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

# --- FastAPI Setup ---
app = FastAPI()
# Assuming templates are in the root 'templates' directory relative to workspace root
templates = Jinja2Templates(directory="templates") 

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
    # Added debug print previously, can be removed if desired
    print(f"DEBUG: Loaded AIRTABLE_TABLE_ID = {AIRTABLE_TABLE_ID}") 


# --- Pydantic Models --- 
class ClassificationOutput(BaseModel):
    input_type: Literal["name", "email", "unknown"] = Field(..., description="Classification of the input")
    processed_value: str = Field(..., description="Input value after case adjustment (name capitalized, email lowercased)")

class ValidationOutput(BaseModel):
    input_type: Literal["name", "email", "unknown"]
    is_valid: bool
    processed_value: Optional[str] = None
    validation_details: str

# --- Guardrail Agent --- 
validation_agent = Agent(
    name="Input Classifier",
    instructions=(
        "Classify the input as 'name' or 'email'. "
        "If name, capitalize first letter of each part. If email, convert to lowercase. "
        "If neither, classify as 'unknown'. Respond ONLY with JSON: {'input_type': '...', 'processed_value': '...'}."
    ),
    output_type=ClassificationOutput,
)

# --- Guardrail Function --- 
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

# --- Greeter Agent (NEW) ---
greeter_agent = Agent(
    name="Greeter",
    instructions="Greet the user warmly and clearly ask them to enter their full name OR email address."
)

# --- Airtable Tool Function --- 
@function_tool
def write_name_to_db(full_name: str) -> str:
    """Writes the provided full name to the Airtable database. Splits the name into first and last name fields."""
    print(f"--- Running Airtable Tool: write_name_to_db ({full_name}) ---")
    try:
        # Note: DeprecationWarning will show in console, consider updating pyairtable usage later
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        name_parts = full_name.strip().split()
        if len(name_parts) == 0: return "Error: Cannot write empty name to database."
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "" 
        record_data = {
            'first_name': first_name,
            'last_name': last_name,
            'full_name': full_name 
        }
        response = table.create(record_data)
        print(f"Airtable API Response: {response}")
        return f"Successfully wrote '{full_name}' to the database."
    except Exception as e:
        print(f"Airtable Tool Error: {e}")
        return f"Error: Failed to write '{full_name}' to the database. Details: {e}"
    finally:
         print("---------------------------------------------")

# --- Specialist Agents --- 
name_agent = Agent(
    name="Name Agent",
    handoff_description="Specialist agent for handling names and saving them.",
    instructions="You have been given a person's full name. First, use the 'write_name_to_db' tool to save the name. Then, report the outcome of the saving operation (success or error) to the user, thank them politely for the information, and confirm the exact name back to them.",
    tools=[write_name_to_db] 
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
    handoffs=[name_agent, email_agent], 
    input_guardrails=[
        InputGuardrail(guardrail_function=validate_input_guardrail), 
    ],
)

print("Agents defined successfully.")

# --- Simple In-Memory Chat History --- 
# (Replace with a database or more robust storage for production)
chat_history = [] 

# --- API Endpoints ---
@app.get("/", response_class=HTMLResponse)
async def chat_interface(request: Request):
    """Serves the chat interface, adding an initial greeting if history is empty."""
    global chat_history # Declare intent to modify global variable
    
    if not chat_history: # Only greet if history is empty
        print("Chat history empty, running Greeter Agent...")
        try:
            greeting_result = await Runner.run(greeter_agent, "initiate") # Dummy input
            if greeting_result.final_output:
                greeting_message = greeting_result.final_output
            else:
                greeting_message = "Hello! Please enter your name or email." # Fallback
            
            # Add greeting to the start of the history
            chat_history.insert(0, {"sender": "agent", "message": greeting_message, "is_error": False})
            print(f"Added greeting: {greeting_message}")
            
        except Exception as e:
            print(f"Error running greeter agent: {e}")
            # Add a fallback greeting even if agent fails
            fallback_greeting = "Hello! Please enter your name or email."
            if not any(entry['message'] == fallback_greeting for entry in chat_history):
                 chat_history.insert(0, {"sender": "agent", "message": fallback_greeting, "is_error": True})

    return templates.TemplateResponse("index.html", {"request": request, "chat_history": chat_history})

@app.post("/process", response_class=HTMLResponse)
async def process_message(request: Request, query: str = Form(...)):
    """Processes the user message using the triage agent and updates chat history."""
    global chat_history # Declare intent to modify global variable
    print(f"Received query: {query}")
    agent_response_text = ""
    is_error = False

    # Add user query to history
    chat_history.append({"sender": "user", "message": query})
    
    try:
        # Run the triage agent asynchronously
        agent_result = await Runner.run(triage_agent, query)
        
        # If successful (no exception), get the agent's final output
        if agent_result and agent_result.final_output:
             agent_response_text = agent_result.final_output
             print(f"Agent Response: {agent_response_text}")
        else:
             agent_response_text = "Agent finished, but no final output was generated."
             print(agent_response_text)
             is_error = True # Treat unexpected empty output as an error state

    except Exception as e:
        # Handle exceptions, specifically looking for guardrail tripwires
        error_message = str(e)
        print(f"Error during agent run: {error_message}")
        is_error = True
        if "triggered tripwire" in error_message.lower():
            # More specific error for guardrail failure
            agent_response_text = "Validation Error: Please enter a valid full name (e.g., Ada Lovelace) or email address (e.g., test@example.com)."
        else:
            # Handle other potential errors during execution
            agent_response_text = f"An unexpected error occurred processing your request."
            # Consider logging the full error_message for backend debugging

    # Add agent response (or error) to history
    chat_history.append({"sender": "agent", "message": agent_response_text, "is_error": is_error})

    # Re-render the template with the updated chat history
    return templates.TemplateResponse("index.html", {"request": request, "chat_history": chat_history})

# --- Uvicorn Run Instructions (Comment) ---
# To run this application:
# 1. Make sure you have uvicorn and fastapi installed: pip install fastapi uvicorn pyairtable python-dotenv
# 2. Make sure template file `templates/index.html` exists and is updated for chat UI.
# 3. Run from the workspace root directory: uvicorn agents_sdk_lee.agent_with_function_webui:app --reload 