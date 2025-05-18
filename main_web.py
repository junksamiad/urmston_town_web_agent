#!/usr/bin/env python

# FastAPI application for the Urmston Town Juniors FC chatbot

import asyncio
import os
import re # <--- ADDED IMPORT
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse
from dotenv import load_dotenv
import json # To send JSON in SSE
from pydantic import BaseModel, Field, validator # Added BaseModel, Field
from typing import List, Optional, Dict, Any, Literal # Added List, Optional, Dict, Any, Literal
from fastapi.middleware.cors import CORSMiddleware # <-- Import CORS Middleware

# Import specific event types for streaming
from agents.stream_events import (
    RawResponsesStreamEvent, 
    RunItemStreamEvent, 
    AgentUpdatedStreamEvent, # Added this import
    # HandoffEvent, # Let's comment out others for now until we know their location
    # AgentErrorEvent, 
    # FinalOutputEvent,
    # ToolCallStreamEvent, 
    # ToolOutputEvent      
)
# We will also need the base StreamEvent type alias
from agents.stream_events import StreamEvent

# Load environment variables (especially for agent keys later)
load_dotenv()

# --- Pydantic Models --- 

class ChatMessageInput(BaseModel):
    """Represents a single message in the chat history (OpenAI format)."""
    role: str = Field(..., description="Role of the message sender (e.g., 'user', 'assistant', 'tool')")
    content: str = Field(..., description="Content of the message")
    # Add other potential fields like 'tool_calls', 'tool_call_id' if needed later

class ChatRequest(BaseModel):
    """Model for the request body sent to /chat/stream."""
    user_message: str = Field(..., description="The latest message entered by the user.")
    history: Optional[List[ChatMessageInput]] = Field(default_factory=list, description="Previous messages in the conversation.")
    session_id: Optional[str] = Field(None, description="Unique identifier for the chat session.")
    last_agent_name: Optional[str] = Field(None, description="Name of the agent that responded last.")
    registration_code: Optional[str] = Field(None, description="The unique registration code entered by the user.") # NEW FIELD

# NEW Pydantic Models for Registration Code
class RegistrationCodeDetails(BaseModel):
    code_type: Literal["new_registration", "renewal_registration"]
    team_name: str
    age_group: int
    season_start_year: int
    season_end_year: int
    raw_code: str # Store the original code for reference

class CodeValidationResponse(BaseModel):
    status: Literal["valid", "invalid"]
    details: Optional[RegistrationCodeDetails] = None
    reason: Optional[str] = None
    raw_code: str

# --- End Pydantic Models ---

# --- Agent Imports and Definitions ---

from agents import Agent, Runner # Import SDK components

# Import agents from our chatbot source package
from chatbot_src.registration import (
    code_verification_agent,
    registration_agent,
    renew_registration_agent,
    new_registration_agent,
    RegistrationSummary # Import the model if needed for type checking later
)
# Import tools if needed directly (though agents should encapsulate them)
# from chatbot_src.tools import validate_registration_code

# Define Classification Rules (copied from go.py)
query_classification_list = """ 
{ 
  "classification_policy": [
    {
      "classification": "registration",
      "keywords": ["register", "signing on", "sign up", "join", "get involved", "membership"],
      "description": "Query is about joining the club or becoming a member.",
      "action_type": "handoff",
      "action_target": "Code Verification Agent" 
    },
    {
      "classification": "payments",
      "keywords": ["membership fee", "subscription", "fee", "subs", "direct debit", "standing order", "payment issues", "setup payment", "amend payment", "cancel payment"],
      "description": "Query is about anything relating to setting up, modifying, making or cancelling payments of any sort.",
      "action_type": "handoff",
      "action_target": "Payments Agent" 
    },
    {
         "classification": "training_times",
         "keywords": ["training", "schedule", "when", "where", "time", "practice"],
         "description": "Query is about training sessions.",
         "action_type": "tool_call",
         "action_target": "get_training_schedule"
     },
    {
      "classification": "other",
      "keywords": [],
      "description": "Any query not matching other classifications.",
      "action_type": "respond",
      "action_target": "Acknowledge the query and state that you will find the right person to help, but cannot answer directly."
    }
  ]
}
"""

# Define Placeholder Payments Agent 
payments_agent = Agent(
    name="Payments Agent", 
    instructions="You handle payment queries related to Urmston Town Juniors FC." # Slightly more specific
)

# Define Router Agent 
router_agent = Agent(
    name="Router Agent",
    instructions=f"""
Urmston Town Juniors Football Club is a grassroots club based in Urmston, Manchester, UK. 
Your role is to act as a first point of contact chatbot.
Your objective is to analyze the user's query and classify it according to the `classification_policy` JSON structure provided below. 
Once classified, you MUST perform the specified action (`action_type` and `action_target`) and nothing else for that classification. 
Adhere strictly to the policy. Do not deviate.

Policy:
```json
{query_classification_list}
```

If the query is ambiguous and you cannot confidently classify it based on the policy, ask clarifying questions to help determine the correct classification BEFORE taking any action.
""",
    # Include ALL agents that can be handed off to OR that might be the 'last_agent'
    handoffs=[code_verification_agent, registration_agent, payments_agent, renew_registration_agent, new_registration_agent],
    # tools=[get_training_schedule] # Add if/when defined
)

# Agent Registry for easy lookup by name
AGENT_REGISTRY: Dict[str, Agent] = {
    router_agent.name: router_agent,
    code_verification_agent.name: code_verification_agent,
    registration_agent.name: registration_agent,
    payments_agent.name: payments_agent,
    renew_registration_agent.name: renew_registration_agent,
    new_registration_agent.name: new_registration_agent,
}

print("Agents imported and defined.")
print(f"Agent Registry contains: {list(AGENT_REGISTRY.keys())}")

# NEW: Function to parse and validate the registration code
def parse_and_validate_registration_code(code: str) -> CodeValidationResponse:
    parts = code.strip().split('-')
    raw_code = code # Keep original for response

    if len(parts) != 4:
        return CodeValidationResponse(status="invalid", reason="Code does not have 4 parts separated by hyphens.", raw_code=raw_code)

    code_type_str, team_name_str, age_group_str, season_str = parts

    # Validate code_type
    if code_type_str == "100": # Note: User mentioned "001 or 002" then "100 or 200". Assuming "100" and "200" based on examples.
        parsed_code_type = "new_registration"
    elif code_type_str == "200":
        parsed_code_type = "renewal_registration"
    else:
        return CodeValidationResponse(status="invalid", reason=f"Invalid code type: '{code_type_str}'. Must be '100' or '200'.", raw_code=raw_code)

    # Validate team_name (basic validation: not empty and reasonably alphanumeric)
    if not team_name_str or not re.match(r"^[a-zA-Z0-9_]+$", team_name_str): # Allow alphanumeric and underscore for team names
        return CodeValidationResponse(status="invalid", reason="Team name cannot be empty and should be alphanumeric.", raw_code=raw_code)
    
    # Validate age_group
    if not age_group_str.isdigit() or not (1 <= len(age_group_str) <= 2):
        return CodeValidationResponse(status="invalid", reason=f"Invalid age group: '{age_group_str}'. Must be a 1 or 2 digit number.", raw_code=raw_code)
    parsed_age_group = int(age_group_str)
    if not (1 <= parsed_age_group <= 21): # Example reasonable age range for youth football
        return CodeValidationResponse(status="invalid", reason=f"Age group '{parsed_age_group}' out of typical range (1-21).", raw_code=raw_code)


    # Validate season
    if not season_str.isdigit() or len(season_str) != 4:
        return CodeValidationResponse(status="invalid", reason=f"Invalid season format: '{season_str}'. Must be 4 digits (e.g., 2526).", raw_code=raw_code)
    
    season_start_yy_str = season_str[:2]
    season_end_yy_str = season_str[2:]

    if not season_start_yy_str.isdigit() or not season_end_yy_str.isdigit():
        return CodeValidationResponse(status="invalid", reason=f"Season year parts '{season_start_yy_str}' or '{season_end_yy_str}' are not numeric.", raw_code=raw_code)

    season_start_yy = int(season_start_yy_str)
    season_end_yy = int(season_end_yy_str)

    # Basic check for season validity (e.g., end year is start year + 1, handles 9900 for YY(YY+1) )
    if season_end_yy != (season_start_yy + 1) % 100:
        return CodeValidationResponse(status="invalid", reason=f"Invalid season progression: '{season_str}'. End year short-form should be start year short-form + 1.", raw_code=raw_code)

    # Determine full years (e.g. 2526 -> 2025, 2026; 9900 -> 1999, 2000)
    # This assumes current century for YY < 50 (e.g. 25 -> 2025) and previous for YY >=50 (e.g. 99 -> 1999)
    # This is a common way to infer century but can be adjusted.
    base_start_year = 2000 + season_start_yy if season_start_yy < 50 else 1900 + season_start_yy
    
    # Calculate end year based on start year and short end year
    # If end_yy is 00 and start_yy is 99, it's a century crossover
    if season_start_yy == 99 and season_end_yy == 0:
        base_end_year = base_start_year + 1 
    else: # normal progression within the same inferred century for start_year
        base_end_year = (base_start_year // 100) * 100 + season_end_yy
        # If, due to YY interpretation, end year appears before start (e.g. start 2099, end_yy 00 implies 2000, not 2100)
        # This means we crossed a century based on the YY values.
        if base_end_year < base_start_year:
             base_end_year += 100


    details = RegistrationCodeDetails(
        code_type=parsed_code_type,
        team_name=team_name_str,
        age_group=parsed_age_group,
        season_start_year=base_start_year,
        season_end_year=base_end_year,
        raw_code=raw_code
    )
    return CodeValidationResponse(status="valid", details=details, raw_code=raw_code)

# NEW: Streaming generator for code validation response
async def stream_code_validation_result(validation_response: CodeValidationResponse):
    """Yields a single JSON event for code validation."""
    yield json.dumps({"event_type": "code_validation_result", "data": validation_response.model_dump()})
    # To keep SSE connection alive briefly if client expects it before closing or for more events
    # For this specific case, one event might be enough, and client can disconnect.
    # await asyncio.sleep(1) # Optional: keep alive for a second

# --- End Agent Imports and Definitions ---

# --- Streaming Logic ---

async def run_agent_stream(agent_to_run: Agent, agent_input: List[Dict[str, Any]]):
    """Runs the agent using run_streamed and yields JSON serializable events."""
    try:
        print(f"Running agent {agent_to_run.name} with streaming...")
        result_stream_obj = Runner.run_streamed(agent_to_run, agent_input)
        last_yielded_agent_name = None # Keep track of the last agent name yielded

        async for event in result_stream_obj.stream_events():
            event_data = None
            event_type = type(event).__name__ # Get the class name as event type string

            # Extract relevant data based on event type
            if isinstance(event, RawResponsesStreamEvent):
                # Check the inner event type for text delta
                if hasattr(event.data, 'type') and event.data.type == "response.output_text.delta":
                    if hasattr(event.data, 'delta') and event.data.delta:
                        event_data = {"delta": event.data.delta}
                        # We don't yield agent name here, assuming it was set by RunItem/AgentUpdated
                    else:
                        # Handle cases where type is delta but no delta content (should be rare)
                        event_data = None # Or maybe log a warning
                else:
                     # Other raw response types, ignore for now or handle specifically if needed
                     event_data = None 
            elif isinstance(event, RunItemStreamEvent):
                # Indicates an agent or tool run item was created (message, tool call, handoff)
                # We previously tried to get agent_name here, but it caused warnings.
                # AgentUpdatedStreamEvent seems to handle agent context changes reliably.
                # For now, we won't yield anything specific for RunItemStreamEvent unless needed later.
                # We could potentially yield event.name and event.item.type for frontend debugging/state?
                print(f"RunItemStreamEvent received: name={event.name}, item_type={type(event.item).__name__}")
                event_data = None # Don't send this event to frontend for now
            elif isinstance(event, AgentUpdatedStreamEvent): # Added specific handler
                # Signals which agent is now controlling the flow
                agent_name = event.new_agent.name # Get name from the Agent object
                event_data = {"agent_name": agent_name} 
                last_yielded_agent_name = agent_name
            elif isinstance(event, StreamEvent):
                 # Generic handler for other StreamEvent subtypes (Handoff, ToolCall, ToolOutput, FinalOutput, AgentError)
                 # Try to dump if possible, otherwise just report the type
                 try:
                     # Attempt model_dump for events that support it (like Handoff, Tool events)
                     event_data = event.model_dump() 
                 except AttributeError:
                     # Handle FinalOutputEvent specifically within this block
                     if hasattr(event, 'final_output'):
                         output = event.final_output
                         if isinstance(output, BaseModel):
                             event_data = {"final_output": output.model_dump()}
                         else:
                             event_data = {"final_output": str(output)}
                     # Handle AgentErrorEvent specifically
                     elif hasattr(event, 'error'): 
                         print(f"Agent Error Event: {event.error}")
                         event_data = {"error": str(event.error)}
                     else:
                         # Fallback for unknown StreamEvent subtypes without model_dump
                         print(f"Unhandled StreamEvent subtype: {event_type}")
                         event_data = {"info": f"Unhandled event type: {event_type}"} 

            if event_data is not None:
                # Yield the event as JSON
                yield json.dumps({"event_type": event_type, "data": event_data})
        
        print(f"Agent {agent_to_run.name} streaming finished.")

    except Exception as e:
        print(f"Error during agent streaming: {e}")
        # Yield an error event to the frontend
        yield json.dumps({"event_type": "ServerError", "data": {"error": str(e)}})

# NEW: Simple echo stream generator
async def stream_echo_response(user_message: str):
    """Yields the user's message back as a mock assistant response."""
    assistant_message_id = f"echo-assistant-{hash(user_message)}" 

    yield json.dumps({
        "event_type": "START_ASSISTANT_MESSAGE", 
        "data": {"id": assistant_message_id, "agent_name": "Echo Bot"}
    })
    
    yield json.dumps({
        "event_type": "RawResponsesStreamEvent", 
        "data": { 
            "delta": user_message 
        }
    })

    yield json.dumps({
        "event_type": "COMPLETE_ASSISTANT_MESSAGE", 
        "data": {"id": assistant_message_id}
    })

# FastAPI app instance
app = FastAPI()

# --- CORS Middleware Configuration --- 
# Define allowed origins (adjust if your frontend runs on a different port/domain)
origins = [
    "http://localhost:3000", # Next.js default dev port
    "http://localhost",      # Allow if accessing without port sometimes?
    # Add other origins if needed, e.g., deployed frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True, # Allow cookies if needed later
    allow_methods=["*"],    # Allow all methods (including OPTIONS, POST)
    allow_headers=["*"],    # Allow all headers
)
# --- End CORS Configuration --- 

# Simple streaming generator for the stub endpoint
async def initial_connection_stream():
    """Yields a simple connected message and then waits indefinitely."""
    yield json.dumps({"event_type": "connection_ack", "data": "Connected to backend stream."}) # Send as JSON
    while True:
        # Keep the connection alive
        await asyncio.sleep(60) # Send a heartbeat or just wait
        # Optionally send a keep-alive message
        # yield json.dumps({"event_type": "keepalive"})

@app.post("/chat/stream") 
async def chat_stream_endpoint(chat_request: ChatRequest): 
    """
    Handles chat requests. 
    If user_message is treated as a registration code, it validates it and streams back the result.
    Otherwise, (eventually) streams back agent responses using SSE.
    """

    potential_code = chat_request.user_message 
    print(f"Received potential registration code: {potential_code}")

    # --- REGISTRATION CODE VALIDATION LOGIC ---
    validation_response = parse_and_validate_registration_code(potential_code)
    print(f"Validation result: {validation_response.status}, Reason: {validation_response.reason if validation_response.reason else 'N/A'}")
    
    return EventSourceResponse(stream_code_validation_result(validation_response))

    # --- TEMPORARY ECHO LOGIC (Now replaced by code validation logic above) ---
    # print(f"Received user message for echo: {chat_request.user_message}")
    # echo_event_generator = stream_echo_response(chat_request.user_message)
    # return EventSourceResponse(echo_event_generator)

    # --- ORIGINAL AGENT LOGIC (Still Commented out) ---
    # # --- NEW: Handle Registration Code if present --- 
    # # This block would be used if chat_request.registration_code was populated by frontend
    # if chat_request.registration_code:
    #     print(f"Received registration code: {chat_request.registration_code}")
    #     validation_response = parse_and_validate_registration_code(chat_request.registration_code)
    #     print(f"Validation result: {validation_response.status}, Reason: {validation_response.reason if validation_response.reason else 'N/A'}")
    #     return EventSourceResponse(stream_code_validation_result(validation_response))
    # # --- END NEW ---
    
    # # --- Determine Agent to Run --- 
    # if chat_request.last_agent_name and chat_request.last_agent_name in AGENT_REGISTRY:
    #     agent_to_run = AGENT_REGISTRY[chat_request.last_agent_name]
    #     print(f"Continuing conversation with: {agent_to_run.name}")
    # else:
    #     agent_to_run = router_agent # Default to router agent for new conversations
    #     print(f"Starting new conversation with: {agent_to_run.name}")

    # # --- Prepare Agent Input --- 
    # history_dicts = [msg.model_dump() for msg in chat_request.history] if chat_request.history else []
    # agent_input = history_dicts + [{
    #     "role": "user", 
    #     "content": chat_request.user_message
    # }]
    # print(f"Agent Input ({len(agent_input)} messages): {agent_input}")

    # # --- Run Agent and Stream Events --- 
    # event_generator = run_agent_stream(agent_to_run, agent_input)
    # return EventSourceResponse(event_generator)
    # --- END OF ORIGINAL AGENT LOGIC ---

# Main execution block (for running with uvicorn)
if __name__ == "__main__":
    import uvicorn
    # Recommended command: uvicorn main_web:app --reload --port 8000
    print("Starting Uvicorn server. Run with: uvicorn main_web:app --reload --port 8000")
    # Note: Running this script directly won't work correctly for FastAPI/Uvicorn
    # uvicorn.run(app, host="0.0.0.0", port=8000) # This can work but --reload is better for dev

# API endpoints will be defined here

# Main execution block will go here 