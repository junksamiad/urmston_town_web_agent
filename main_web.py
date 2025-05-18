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
import uuid # Add for generating unique IDs

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
    # code_verification_agent, # REMOVED
    # registration_agent,      # REMOVED
    renew_registration_agent,
    new_registration_agent,
    RegistrationSummary 
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
    # Handoffs updated to only include currently defined agents relevant to router
    handoffs=[payments_agent, new_registration_agent, renew_registration_agent], 
    # tools=[get_training_schedule] # Add if/when defined
)

# Agent Registry for easy lookup by name
AGENT_REGISTRY: Dict[str, Agent] = {
    router_agent.name: router_agent, 
    # code_verification_agent.name: code_verification_agent, # REMOVED
    # registration_agent.name: registration_agent,          # REMOVED
    payments_agent.name: payments_agent,
    new_registration_agent.name: new_registration_agent, 
    renew_registration_agent.name: renew_registration_agent, 
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

# --- End Agent Imports and Definitions ---

# --- Streaming Logic ---

async def run_agent_stream(agent_to_run: Agent, agent_input: List[Dict[str, Any]]):
    """Runs the agent using run_streamed and yields JSON serializable events."""
    assistant_message_id = f"asst_{uuid.uuid4()}" # Generate a unique ID for this agent's response stream
    agent_name_to_yield = agent_to_run.name # Get agent name

    try:
        # 1. Yield START_ASSISTANT_MESSAGE as plain JSON
        start_event_data = {
            "event_type": "START_ASSISTANT_MESSAGE",
            "data": {"id": assistant_message_id, "agent_name": agent_name_to_yield},
        }
        print(f"DEBUG: run_agent_stream yielding START_ASSISTANT_MESSAGE: {json.dumps(start_event_data)}")
        yield json.dumps(start_event_data) # Yield plain JSON

        print(f"Running agent {agent_name_to_yield} with streaming...")
        # Corrected agent streaming call
        result_stream_obj = Runner.run_streamed(agent_to_run, agent_input)
        async for event in result_stream_obj.stream_events():
            event_type = event.__class__.__name__
            event_data = None
            if isinstance(event, RawResponsesStreamEvent):
                if hasattr(event, 'data') and hasattr(event.data, 'delta') and event.data.delta is not None:
                    event_data = {"delta": event.data.delta}
                    print(f"BACKEND RawResponsesStreamEvent DELTA: -->{event.data.delta}<--")
                # else:
                #     # Log other types of RawResponsesStreamEvent if needed for debugging
                #     # For now, we only care about deltas for direct streaming to UI
                #     response_type = event.raw_response.type if hasattr(event.raw_response, 'type') else "N/A"
                #     # print(f"BACKEND RawResponsesStreamEvent: Non-delta type or missing type attribute: {response_type}")
                #     pass # Don't yield non-delta RawResponsesStreamEvents for now

            elif isinstance(event, RunItemStreamEvent):
                print(f"BACKEND RunItemStreamEvent received: name={event.name}, item_type={type(event.item).__name__}")
                # We are not sending this to frontend currently, so event_data remains None
            elif isinstance(event, AgentUpdatedStreamEvent):
                # Corrected way to access the new agent's name
                if hasattr(event, 'new_agent') and hasattr(event.new_agent, 'name'):
                    event_data = {"agent_name": event.new_agent.name}
                    print(f"BACKEND AgentUpdatedStreamEvent: New agent is {event.new_agent.name}")
                else:
                    print(f"BACKEND AgentUpdatedStreamEvent: Received event but could not find new_agent.name. Event: {event}")
            elif hasattr(event, 'final_output'): # Generic check for final output events
                print(f"BACKEND FinalOutput-like event ({event_type}) detected.")
                output = event.final_output
                if isinstance(output, BaseModel):
                    event_data = {"final_output": output.model_dump()}
                else:
                    event_data = {"final_output": str(output)}
            elif hasattr(event, 'error'): # Generic check for error events
                print(f"BACKEND Error-like event ({event_type}) detected: {event.error}")
                event_data = {"error": str(event.error)}
            # Add more specific `isinstance` checks for other StreamEvent types if needed
            # e.g., ToolCallStreamEvent, ToolOutputEvent, HandoffEvent

            if event_data is not None:
                json_to_yield = json.dumps({"event_type": event_type, "data": event_data})
                print(f"BACKEND YIELDING JSON: {json_to_yield}") 
                yield json_to_yield # Yield plain JSON
            # else:
            #     # print(f"BACKEND Event Type {event_type} did not produce yieldable event_data (or was handled by specific log, e.g. RunItemStreamEvent).")
            #     pass
        
        # 2. CRITICAL: Yield COMPLETE_ASSISTANT_MESSAGE as plain JSON
        complete_event_data = {
            "event_type": "COMPLETE_ASSISTANT_MESSAGE",
            "data": {"id": assistant_message_id},
        }
        print(f"DEBUG: run_agent_stream yielding COMPLETE_ASSISTANT_MESSAGE: {json.dumps(complete_event_data)}")
        yield json.dumps(complete_event_data) # Yield plain JSON

    except Exception as e:
        print(f"Error in run_agent_stream for {agent_name_to_yield}: {e}")
        error_event = {
            "event_type": "AgentErrorEvent",  # Consistent error event type
            "data": {"error": str(e), "agent_name": agent_name_to_yield}
        }
        yield json.dumps(error_event) # Yield plain JSON
    finally:
        print(f"Agent {agent_name_to_yield} streaming finished.")

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
    If user_message is treated as a registration code, it validates it, 
    then routes to the appropriate registration agent with extracted details.
    Otherwise, (eventually) streams back other agent responses using SSE.
    """

    potential_code = chat_request.user_message 
    print(f"[ENDPOINT] Received potential registration code: {potential_code}")

    async def event_generator():
        validation_message_id = f"val_{uuid.uuid4()}" # Unique ID for the validation message sequence
        
        try:
            # Attempt to parse and validate the code
            validation_response = parse_and_validate_registration_code(potential_code)
            print(f"[ENDPOINT] Validation result: {validation_response.status}, Reason: {validation_response.reason or 'N/A'}")

            if validation_response.status == "invalid":
                # Only send validation events if the code is invalid
                event_to_yield = {
                    "event_type": "START_ASSISTANT_MESSAGE",
                    "data": {"id": validation_message_id, "agent_name": "Validation Service"},
                }
                print(f"DEBUG: chat_stream_endpoint yielding START_ASSISTANT_MESSAGE for invalid validation: {json.dumps(event_to_yield)}")
                yield json.dumps(event_to_yield)

                validation_data_with_id = validation_response.model_dump(exclude_none=True)
                validation_data_with_id["id"] = validation_message_id
                # Replace detailed validation data with a user-friendly message for invalid codes
                user_friendly_invalid_message = "It seems you have provided an invalid code. Please check again or confirm with your manager that the code is correct."
                if validation_response.reason: # Optionally append the specific reason if it exists and is simple
                    # We might want to be careful not to expose too much internal detail in the reason
                    # For now, let's keep it generic as requested.
                    pass # user_friendly_invalid_message += f" (Details: {validation_response.reason})"

                event_to_yield = {
                    "event_type": "code_validation_result",
                    "data": {
                        "id": validation_message_id, 
                        "status": "invalid", 
                        "display_message": user_friendly_invalid_message,
                        "raw_code": validation_response.raw_code # Still useful for context
                    }
                }
                print(f"DEBUG: chat_stream_endpoint yielding code_validation_result event for invalid code: {json.dumps(event_to_yield)}")
                yield json.dumps(event_to_yield)
                
                event_to_yield = {
                    "event_type": "COMPLETE_ASSISTANT_MESSAGE",
                    "data": {"id": validation_message_id},
                }
                print(f"DEBUG: chat_stream_endpoint yielding COMPLETE_ASSISTANT_MESSAGE for invalid validation: {json.dumps(event_to_yield)}")
                yield json.dumps(event_to_yield)

            elif validation_response.status == "valid" and validation_response.details:
                print(f"[ENDPOINT] Code valid. Proceeding to stream agent directly without explicit validation message in UI.")
                details = validation_response.details
                agent_to_run_selected = None
                initial_agent_message_content = ""

                if details.code_type == "new_registration": # "100"
                    agent_to_run_selected = new_registration_agent
                    initial_agent_message_content = (
                        f"Starting registration with the following context provided from the validated code:\n"
                        f"- Membership Status: new\n"
                        f"- Team Name: {details.team_name}\n"
                        f"- Age Group: u{details.age_group}s\n"
                        f"- Registration Season: {details.season_start_year % 100}{details.season_end_year % 100}\n"
                        f"(Based on validated raw code: {details.raw_code})"
                    )
                elif details.code_type == "renewal_registration": # "200"
                    agent_to_run_selected = renew_registration_agent
                    initial_agent_message_content = (
                        f"Starting renewal with the following context provided from the validated code:\n"
                        f"- Membership Status: renew\n"
                        f"- Team Name: {details.team_name}\n"
                        f"- Age Group: u{details.age_group}s\n"
                        f"- Registration Season: {details.season_start_year % 100}{details.season_end_year % 100}\n"
                        f"(Based on validated raw code: {details.raw_code})"
                    )
                
                if agent_to_run_selected:
                    print(f"[ENDPOINT] Initial message for agent: {initial_agent_message_content}")
                    agent_input = [{"role": "user", "content": initial_agent_message_content}]
                    
                    # Yield from run_agent_stream (which now yields plain JSON strings)
                    async for agent_event_json_str in run_agent_stream(agent_to_run_selected, agent_input):
                        yield agent_event_json_str # Pass through the plain JSON string
                else:
                    # This case should ideally not be hit if validation implies agent existence
                    print(f"[ENDPOINT] ERROR: Code valid but no agent selected for type '{details.code_type}'")
                    error_event = { "event_type": "ServerError", "data": { "error": "Internal configuration error: No agent for valid code type."}}
                    yield json.dumps(error_event) # Yield plain JSON
            
        except Exception as e:
            print(f"Error in chat_stream_endpoint event_generator: {e}")
            # Ensure some error message is sent to the client
            error_event = {
                "event_type": "ServerError", # General server error
                "data": {"error": f"Failed to process chat stream: {str(e)}"}
            }
            yield json.dumps(error_event) # Yield plain JSON

    return EventSourceResponse(event_generator())

# Main execution block (for running with uvicorn)
if __name__ == "__main__":
    import uvicorn
    # Recommended command: uvicorn main_web:app --reload --port 8000
    print("Starting Uvicorn server. Run with: uvicorn main_web:app --reload --port 8000")
    # Note: Running this script directly won't work correctly for FastAPI/Uvicorn
    # uvicorn.run(app, host="0.0.0.0", port=8000) # This can work but --reload is better for dev

# API endpoints will be defined here

# Main execution block will go here 