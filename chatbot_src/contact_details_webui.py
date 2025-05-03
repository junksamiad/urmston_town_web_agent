#!/usr/bin/env python
import os
import re 
import asyncio
import uuid # For session IDs
import json # <-- Added for SSE event serialization
from dotenv import load_dotenv
from typing import Dict, List, Any 
import typing as t # Added for type hinting if needed

# --- Web Framework Imports ---
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

# --- Agent SDK Imports ---
# Assuming 'agents' library is installed and accessible
from agents import Agent, Runner, RunContextWrapper, function_tool
from agents import WebSearchTool

# --- OpenAI Specific Import for Raw Events ---
# Note: This creates a dependency on the specific structure of OpenAI events.
# If using other providers, the raw event types might differ.
from openai.types.responses import ResponseTextDeltaEvent

# --- Airtable Import ---
from pyairtable import Table

# --- Load Environment Variables ---
load_dotenv()

# OpenAI Key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: FATAL: OPENAI_API_KEY not found.")
    exit(1)
# Set the key for the agents library (if it doesn't pick it up automatically)
# openai.api_key = api_key 

# Airtable Credentials
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")
if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID]):
    print("Error: FATAL: Airtable credentials (API Key, Base ID, Table ID) not found in .env file.")
    exit(1) 
else:
    print("OpenAI and Airtable credentials loaded successfully.")
    # print(f"DEBUG: Loaded AIRTABLE_TABLE_ID = {AIRTABLE_TABLE_ID}") # Optional debug

# --- FastAPI Setup ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- In-memory storage for conversation history (Demo purposes only!) ---
# A dictionary mapping session_id (str) to conversation_history (List[Dict])
conversation_histories: Dict[str, List[Dict[str, Any]]] = {}

# NEW: Per-session async queues for streaming events
session_queues: Dict[str, "asyncio.Queue[str]"] = {}

# NEW: Track the agent that should start the next turn for each session
next_start_agent: Dict[str, Agent] = {}

# --- Airtable Tool Functions ---
@function_tool
def write_name_to_db(full_name: str) -> str:
    """Writes the provided full name (PLAYER'S NAME) to the Airtable database. Splits the name into first and last name fields. Returns the record ID on success."""
    print(f"--- Running Airtable Tool: write_name_to_db ({full_name}) ---")
    try:
        # Note: Consider initializing Table/API object once outside the function if performance is critical
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        name_parts = full_name.strip().split()
        if len(name_parts) == 0:
             return "Error: Cannot write empty name to database."
        first_name = name_parts[0]
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "" 
        record_data = {'first_name': first_name, 'last_name': last_name, 'full_name': full_name}
        response = table.create(record_data)
        record_id = response['id']
        print(f"Airtable API Response: {response}")
        return f"Successfully wrote player '{full_name}' to the database. Record ID: {record_id}"
    except Exception as e:
        print(f"Airtable Tool Error: {e}")
        # It's often better to return structured error info if the agent needs to parse it
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

# Combined Contact Details Agent
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
        "7. After the email tool call completes (success or failure), provide the final confirmation. Use the registrar's name collected in step 2 and the player's name from step 3. Example: 'Thank you [Registrar's Name], [Player's Name] has been successfully registered with the club.'"
     ), 
    tools=[write_name_to_db, update_email_in_db],
)

# Initial Contact Agent 
registration_assistant_agent = Agent(
    name="Urmston Town Registration Assistant", 
    instructions=(
        "Introduce yourself warmly as the 'Urmston Town Registration Assistant'. Ask the user 'How can I help you today?'. "
        "You can answer questions about upcoming Urmston Town fixtures. If asked about fixtures, use your web search tool with the specific query \"Urmston Town Fixtures\" to find the most current information. "
        "If the user indicates they want to register, sign up, join, or similar, **do not reply yourself**. Your ONLY action should be to perform a silent handoff to the 'Contact Details Agent'."
    ), 
    tools=[WebSearchTool()],
    handoffs=[contact_details_agent] 
)

print("Agents defined successfully.")

# --- FastAPI Endpoints --- 

# Root endpoint to serve the HTML
@app.get("/", response_class=HTMLResponse)
async def get_chat_page(request: Request):
    session_id = str(uuid.uuid4())  # Generate a unique ID for this session
    print(f"New session started: {session_id}")
    # Initialize history and session state
    initial_greeting = "Hello! I'm the Urmston Town Registration Assistant. How can I help you today?"
    conversation_histories[session_id] = [
        {"role": "assistant", "content": initial_greeting}
    ]
    # Prepare streaming queue & next start agent for this session
    session_queues[session_id] = asyncio.Queue()
    next_start_agent[session_id] = registration_assistant_agent
    return templates.TemplateResponse("chat_index.html", {"request": request, "session_id": session_id, "initial_greeting": initial_greeting})

# ---------------------------------------------------------------------------
#   Streaming GET endpoint – the browser maintains a single SSE connection
# ---------------------------------------------------------------------------
@app.get("/chat_stream/{session_id}")
async def get_chat_stream(session_id: str):
    """Return a persistent Server-Sent Events stream for the given session."""
    if session_id not in session_queues:
        # Create a queue if not yet initialised (e.g. after server reload)
        session_queues[session_id] = asyncio.Queue()
    queue = session_queues[session_id]

    async def streamer():
        while True:
            data = await queue.get()
            if data is None:
                # Sentinel value -> terminate stream
                break
            yield data

    return EventSourceResponse(streamer())

# ---------------------------------------------------------------------------
#   Message submission endpoint
# ---------------------------------------------------------------------------
@app.post("/send_message/{session_id}")
async def send_message(session_id: str, message: str = Form(...)):
    """Handle a user message: update history, run the agent (streamed) in a
    background task, and immediately return JSON ack. The SSE queue for the
    session will receive streaming tokens/events."""

    # Ensure per-session structures exist
    conversation_histories.setdefault(session_id, [])
    session_queues.setdefault(session_id, asyncio.Queue())
    next_start_agent.setdefault(session_id, registration_assistant_agent)

    history = conversation_histories[session_id]
    history.append({"role": "user", "content": message})
    start_agent = next_start_agent[session_id]

    queue = session_queues[session_id]

    async def parse_and_enqueue_events():
        tool_calls_in_progress: Dict[str, str] = {}
        last_agent_name = start_agent.name
        len_before_run = len(history)
        try:
            run_streamed = Runner.run_streamed(start_agent, history)
            # ---------------- Stream internal events -------------------
            async for event in run_streamed.stream_events():
                event_data = None
                if event.type == "raw_response_event":
                    if isinstance(event.data, ResponseTextDeltaEvent):
                        delta = event.data.delta
                        if delta:
                            event_data = {"event": "text_delta", "text": delta}
                elif event.type == "run_item_stream_event":
                    item = event.item
                    item_type = getattr(item, "type", None)
                    if item_type == "tool_call_item":
                        tool_name = getattr(item, "name", "unknown_tool")
                        call_id = getattr(item, "id", None)
                        if call_id:
                            tool_calls_in_progress[call_id] = tool_name
                        event_data = {"event": "tool_start", "name": tool_name}
                    elif item_type == "tool_call_output_item":
                        call_id = getattr(item, "tool_call_id", None)
                        tool_name = tool_calls_in_progress.pop(call_id, "unknown_tool")
                        event_data = {"event": "tool_end", "name": tool_name}
                    elif item_type == "handoff_output_item":
                        target_agent = getattr(item, "target_agent", None)
                        if target_agent and hasattr(target_agent, "name"):
                            target_name = target_agent.name
                            if target_name != last_agent_name:
                                event_data = {"event": "handoff", "target_agent": target_name}
                                last_agent_name = target_name
                elif event.type == "agent_updated_stream_event":
                    new_agent = getattr(event, "new_agent", None)
                    if new_agent and hasattr(new_agent, "name"):
                        new_name = new_agent.name
                        if new_name != last_agent_name:
                            event_data = {"event": "handoff", "target_agent": new_name}
                            last_agent_name = new_name
                if event_data:
                    await queue.put(json.dumps(event_data))

            # ---------------- After completion -------------------------
            final_history = run_streamed.to_input_list()
            new_messages = final_history[len_before_run:]
            history.extend(new_messages)
            await queue.put(json.dumps({"event": "end"}))

            # Update next_start_agent for the subsequent turn
            if hasattr(run_streamed, "last_agent") and run_streamed.last_agent:
                next_start_agent[session_id] = run_streamed.last_agent
            else:
                next_start_agent[session_id] = registration_assistant_agent

        except Exception as e:
            err = f"An agent error occurred: {e}"
            await queue.put(json.dumps({"event": "error", "detail": err}))
            await queue.put(json.dumps({"event": "end"}))
            print(f"Error in background task (session {session_id}): {err}")

    # Launch background streaming task
    asyncio.create_task(parse_and_enqueue_events())

    # Immediate ACK so the browser's fetch() resolves
    return {"status": "ok"}

# Placeholder for running with uvicorn
if __name__ == "__main__":
   import uvicorn
   # Ensure reload is False or handled carefully if using in-memory history
   uvicorn.run(app, host="0.0.0.0", port=8000) 