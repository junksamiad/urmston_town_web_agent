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

# --- OpenAI Specific Import for Raw Events ---
# This is still needed to check the type of event.data
from openai.types.responses import ResponseTextDeltaEvent

# --- Agent SDK Imports ---
from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, RunContextWrapper, function_tool 
from agents import WebSearchTool

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

# --- Pydantic Models (REMOVED Classification/Validation as guardrails are removed) ---
# class ClassificationOutput(...): ...
# class ValidationOutput(...): ...

# --- Guardrail Agent (REMOVED) ---
# validation_agent = Agent(...)

# --- Guardrail Function (REMOVED) ---
# async def validate_input_guardrail(...): ...

# --- Airtable Tool Functions (Unchanged for now) ---
@function_tool
def write_name_to_db(full_name: str) -> str:
    """Writes the provided full name (PLAYER'S NAME) to the Airtable database. Splits the name into first and last name fields. Returns the record ID on success."""
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
        record_id = response['id']
        print(f"Airtable API Response: {response}")
        return f"Successfully wrote player '{full_name}' to the database. Record ID: {record_id}"
    
    except Exception as e:
        print(f"Airtable Tool Error: {e}")
        return f"Error: Failed to write player '{full_name}' to the database. Details: {e}"
    finally:
         print("---------------------------------------------")


@function_tool
def update_email_in_db(record_id: str, email: str) -> str:
    """Updates the 'player_email' field for the specified record_id in Airtable."""
    print(f"--- Running Airtable Tool: update_email_in_db (Record: {record_id}, Email: {email}) ---")
    try:
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        response = table.update(record_id, {'player_email': email})
        print(f"Airtable API Response: {response}")
        return f"Successfully updated record {record_id} with email {email}."
    except Exception as e:
        print(f"Airtable Tool Error: {e}")
        return f"Error updating record {record_id} with email {email}. Details: {e}"
    finally:
        print("-----------------------------------------------------------------------")


# --- Agent Definitions ---

# --- Central Orchestrator Agent (REMOVED) ---
# registration_agent = Agent(...)

# --- Specialist Email Agent (REMOVED) ---
# email_agent = Agent(...)

# --- Combined Contact Details Agent (Handles Conversation & DB Updates) ---
contact_details_agent = Agent(
    name="Contact Details Agent", 
    handoff_description="Specialist agent for handling the capture of contact details during the registration process and updating the details to a database.", 
    instructions=(
        "Your primary task is to capture the contact details for the player and the parent/guardian involved in the registration process." 
        "Follow these steps precisely:" 
        "1. Casually ask the user to clarify that they are a parent / guardian or a player over 16 years of age?" 
        "2. Once answered, ask if you can take their full name? (This is the registrar's name)." 
        "3. Once answered, if they are the parent / guardian, ask it you can take their child's full name." 
        "4. Once you have the player's name, use the 'write_name_to_db' tool to save it. The tool will return the record ID." 
        "5. After the name tool call returns the record ID, ask for an email address for the parent / guardian or the player if over 16 years of age." 
        "6. Once you have the email address, use the 'update_email_in_db' tool, providing the record_id and the player's email." 
        "7. After the email tool call completes (success or failure), provide the final confirmation. Use the registrar's name collected in step 2 and the player's name from step 3. Example: 'Thank you [Registrar's Name], [Player's Name] has been successfully registered with the club.'" # Changed: Now provides final output
     ), 
    tools=[write_name_to_db, update_email_in_db],
    # Removed handoffs parameter
)

# --- Update Email Agent Handoffs (REMOVED) ---
# email_agent.handoffs = [name_agent]

# --- Initial Contact Agent (Re-adding Web Search) ---
registration_assistant_agent = Agent(
    name="Urmston Town Registration Assistant", 
    instructions=(
        "Introduce yourself warmly as the 'Urmston Town Registration Assistant'. Ask the user 'How can I help you today?'. "
        "You can answer questions about upcoming Urmston Town fixtures. If asked about fixtures, use your web search tool with the specific query \"Urmston Town Fixtures\" to find the most current information. "
        "If the user indicates they want to register, sign up, join, or similar, **do not reply yourself**. Your ONLY action should be to perform a silent handoff to the 'Contact Details Agent'."
    ), 
    tools=[WebSearchTool(user_location={"type": "approximate", "city": "Manchester"})],
    handoffs=[contact_details_agent]
)

# --- Debug the WebSearchTool ---
print("Debug: WebSearchTool configuration:")
print(f"API key set: {'YES' if api_key else 'NO'}")
print(f"WebSearchTool should be using the 'web_search_preview' endpoint")
# Print OpenAI client info if available
print(f"Environment variables for OpenAI setup:")
print(f"OPENAI_API_KEY is {'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET'}")

# --- Update Registration Agent Handoffs (REMOVED) ---
# registration_agent.handoffs = [contact_details_agent] 


print("Agents defined successfully.")

# --- Main Execution (Loop structure remains the same) ---
async def main():
    # --- Step 1: Start Conversation with Assistant ---
    print(f"--- Running {registration_assistant_agent.name} ---")
    conversation_history = []
    agent_for_next_turn = registration_assistant_agent # Initialize starting agent
    try:
        # Initial message from assistant to kick things off
        initiation_result = await Runner.run(agent_for_next_turn, "initiate conversation") 
        
        if initiation_result.final_output:
            print(f"\nAssistant: {initiation_result.final_output}")
            conversation_history.extend(initiation_result.to_input_list()) 
            # Update agent for next turn based on the initial run
            if hasattr(initiation_result, 'last_agent') and initiation_result.last_agent:
                 agent_for_next_turn = initiation_result.last_agent
            # No else needed, default remains registration_assistant_agent if last_agent not found initially
        else:
            # Fallback if initial greeting fails
             print("\nAssistant: Hello, I am the Urmston Town Registration Assistant. How can I help? (Fallback)")
             conversation_history.append({"role": "assistant", "content": "Hello, I am the Urmston Town Registration Assistant. How can I help? (Fallback)"})
             
    except Exception as e:
        print(f"\nError during initial greeting: {e}")
        return

    # --- Multi-Turn Conversation Loop ---
    while True: 
        user_input = input("Your input: ")
        
        len_before_user = len(conversation_history)
        conversation_history.append({"role": "user", "content": user_input})

        print(f"\n--- Running Agent '{agent_for_next_turn.name}' with input: '{user_input}' ---") # Use dynamic agent name
        try:
            # Use the agent determined from the PREVIOUS turn
            current_run_result = await Runner.run(agent_for_next_turn, conversation_history)

            # Get the full list of messages as the runner sees it after the run
            full_list_after_run = current_run_result.to_input_list() 
            
            start_index_for_new = len(conversation_history)
            new_messages = full_list_after_run[start_index_for_new:]

            # Update history with messages from this turn
            conversation_history.extend(new_messages)
            
            # --- Log new_items for debugging --- 
            print("\n--- DEBUG: Items generated during this run ---")
            if hasattr(current_run_result, 'new_items') and current_run_result.new_items:
                for i, item in enumerate(current_run_result.new_items):
                    item_type = getattr(item, 'type', 'unknown')
                    print(f"Item {i}: Type={item_type}")
                    # Print more details based on type
                    if item_type == 'tool_call_item':
                        print(f"  Tool Call: Name={getattr(item, 'name', 'N/A')}, Args={getattr(item, 'arguments', {})}, ID={getattr(item, 'id', 'N/A')}")
                    elif item_type == 'tool_call_output_item':
                         print(f"  Tool Output: ID={getattr(item, 'tool_call_id', 'N/A')}, Output={getattr(item, 'output', 'N/A')}")
                    elif item_type == 'handoff_output_item':
                         source_agent_name = getattr(getattr(item, 'source_agent', None), 'name', 'N/A')
                         target_agent_name = getattr(getattr(item, 'target_agent', None), 'name', 'N/A')
                         print(f"  Handoff: From={source_agent_name}, To={target_agent_name}")
                    elif item_type == 'message_output_item':
                         # The raw item here is often the message dict itself
                         raw_message = getattr(item, 'raw', None)
                         print(f"  Message Output: {raw_message}")
                    else:
                         # Print the raw item representation for other types
                         print(f"  Raw Item: {getattr(item, 'raw', item)}") # Fallback to item itself
            else:
                 print("(No new items reported by result object)")
            print("-------------------------------------------")
            # --- End Log new_items --- 

            agent_response = current_run_result.final_output
            
            # DETERMINE AGENT FOR THE *NEXT* TURN
            if hasattr(current_run_result, 'last_agent') and current_run_result.last_agent:
                 agent_for_next_turn = current_run_result.last_agent
                 print(f"(Debug: Next turn will start with: {agent_for_next_turn.name})") # Debug print
            else:
                 # Fallback if last_agent isn't available - perhaps stick with current?
                 # Or reset to assistant? Let's reset to assistant for safety.
                 print("(Debug: last_agent not found, resetting start agent for next turn)")
                 agent_for_next_turn = registration_assistant_agent 

            if agent_response:
                 print(f"\nAssistant: {agent_response}")
                 if "has been successfully registered" in agent_response:
                      print("\n--- Registration Complete ---")
                      break 
            else:
                 # Check if the last messages were tool interactions or silent handoffs
                 is_internal_processing = False
                 if new_messages:
                      last_message = new_messages[-1]
                      # Check if the last message object signifies tool or handoff activity
                      # Note: The exact structure might vary, this is a basic check
                      if isinstance(last_message, dict) and (last_message.get("role") == "tool" or last_message.get("type") == "handoff"):
                           is_internal_processing = True 
                 
                 if is_internal_processing:
                      print("\nAssistant: (Processing...) ")
                 else:
                      print("\nAssistant: (Continuing process...)") # Default if no output but not clearly tool/handoff


        except Exception as e:
             print(f"\nAn error occurred during execution: {e}")
             print("Current Conversation History:")
             for msg in conversation_history:
                 # Use .get() for safer access in case keys are missing
                 role = msg.get('role', 'unknown')
                 # Content might be complex, try getting 'text' if 'content' isn't there
                 content_raw = msg.get('content', msg.get('text', str(msg)))
                 content_str = str(content_raw) # Ensure it's a string
                 print(f"- {role}: {content_str[:100]}...") # Print snippet safely
             break # Exit loop on error

# --- Boilerplate ---
if __name__ == "__main__":
    asyncio.run(main()) 