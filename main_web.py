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
from copy import deepcopy # NEW IMPORT

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
    renew_registration_agent,
    new_registration_agent,
    RegistrationSummary,
    new_registration_agent_main_instructions,
    player_contact_details_parent_reg # ADD THIS IMPORT
)
# Import tools if needed directly (though agents should encapsulate them)
# from chatbot_src.tools import validate_registration_code

# Import formatting guidelines
from chatbot_src.formatting_prompt import append_formatting_guidelines # Ensure this is imported

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
    instructions="You handle payment queries related to Urmston Town Juniors FC. Your capabilities are currently under development. Please inform the user that payment-related functionalities will be available soon."
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
    payments_agent.name: payments_agent,
    new_registration_agent.name: new_registration_agent, 
    renew_registration_agent.name: renew_registration_agent,
    player_contact_details_parent_reg.name: player_contact_details_parent_reg # ADD THIS AGENT
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

async def run_agent_stream(
    agent_to_run: Agent, 
    messages_input: List[Dict[str, Any]], # RENAMED and RE-TYPED: This is now just the list of messages
    response_accumulator: Dict[str, str] # For collecting the full JSON response
):
    """Runs the agent using run_streamed and yields JSON serializable events."""
    assistant_message_id = f"asst_{uuid.uuid4()}" # Generate a unique ID for this agent's response stream
    agent_name_to_yield = agent_to_run.name # Get agent name
    response_accumulator["final_json_response"] = "" # Initialize accumulator

    try:
        # 1. Yield START_ASSISTANT_MESSAGE as plain JSON
        start_event_data = {
            "event_type": "START_ASSISTANT_MESSAGE",
            "data": {"id": assistant_message_id, "agent_name": agent_name_to_yield},
        }
        print(f"DEBUG: run_agent_stream yielding START_ASSISTANT_MESSAGE: {json.dumps(start_event_data)}")
        yield json.dumps(start_event_data) # Yield plain JSON

        print(f"Running agent {agent_name_to_yield} with streaming messages_input: {messages_input}")
        
        # The messages_input IS the direct input for the runner.
        # Template variables for agent instructions must be handled *before* this function is called,
        # by creating/configuring the agent_to_run with its fully formatted instructions.

        print(f"DEBUG: Runner.run_streamed called with agent: {agent_to_run.name} and messages: {messages_input}")
        # Ensure messages_input is a list of dicts as expected by the SDK
        # Example: [{"role": "user", "content": "Hello there"}]

        result_stream_obj = Runner.run_streamed(agent_to_run, messages_input) # SIMPLIFIED CALL
        async for event in result_stream_obj.stream_events():
            event_type = event.__class__.__name__
            event_data = None
            if isinstance(event, RawResponsesStreamEvent):
                if hasattr(event, 'data') and hasattr(event.data, 'delta') and event.data.delta is not None:
                    delta_content = event.data.delta
                    if isinstance(delta_content, str): # Ensure delta is a string
                        response_accumulator["final_json_response"] += delta_content # Accumulate
                        event_data = {"delta": delta_content}
                        print(f"BACKEND RawResponsesStreamEvent DELTA: -->{delta_content}<--")
                    else:
                        print(f"BACKEND RawResponsesStreamEvent: Delta is not a string: {type(delta_content)}")

            elif isinstance(event, RunItemStreamEvent):
                print(f"BACKEND RunItemStreamEvent received: name={event.name}, item_type={type(event.item).__name__}")
                # We are not sending this to frontend currently, so event_data remains None
            elif isinstance(event, AgentUpdatedStreamEvent):
                # Corrected way to access the new agent's name
                if hasattr(event, 'new_agent') and hasattr(event.new_agent, 'name'):
                    new_name = event.new_agent.name
                    event_data = {"agent_name": new_name, "id": assistant_message_id}
                    print(f"BACKEND AgentUpdatedStreamEvent: New agent is {new_name}")
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
            #     # print(f"BACKEND Event Type {event_type} did not produce yieldable event_data (or was handled by specific log, e.g. RunItemStreamEvent).\n")
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
            "data": {"error": str(e), "agent_name": agent_name_to_yield, "id": assistant_message_id } # Include ID
        }
        # Ensure COMPLETE is sent for this message ID if an error occurs mid-stream after START
        yield json.dumps(error_event)
        yield json.dumps({
            "event_type": "COMPLETE_ASSISTANT_MESSAGE",
            "data": {"id": assistant_message_id},
        })

    finally:
        print(f"Agent {agent_name_to_yield} streaming finished. Accumulated JSON: {response_accumulator['final_json_response']}")

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
    Handles chat requests. Can involve a chain of agents if a handoff is indicated
    by an agent completing its task.
    """

    print(f"[ENDPOINT] Received: User='{chat_request.user_message}', LastAgent='{chat_request.last_agent_name}', HistoryEmpty={not chat_request.history}")

    async def event_generator():
        current_turn_conversation_history: List[ChatMessageInput] = list(chat_request.history) if chat_request.history else []
        
        # Initial user message for the very first agent in a potential chain
        # For subsequent agents in a silent handoff chain, this will be overridden.
        current_input_content_for_agent = chat_request.user_message

        # Determine the first agent to run
        initial_agent_name_for_turn: Optional[str] = None
        initial_agent_context_for_turn: Optional[Dict[str, Any]] = None

        if not current_turn_conversation_history: # STRICT: First message from the user for the whole session
            print("[ENDPOINT] First message in session. Expecting registration code.")
            validation_response = parse_and_validate_registration_code(current_input_content_for_agent)

            if validation_response.status == "valid" and validation_response.details:
                print(f"[ENDPOINT] Registration code '{current_input_content_for_agent}' is VALID for first turn.")
                details = validation_response.details
                if details.code_type == "new_registration":
                    initial_agent_name_for_turn = new_registration_agent.name
                elif details.code_type == "renewal_registration":
                    initial_agent_name_for_turn = renew_registration_agent.name
                
                if initial_agent_name_for_turn:
                    initial_agent_context_for_turn = {"parsed_code_details": details.model_dump()}
                else:
                    err_msg = f"Valid code type '{details.code_type}' on first turn has no mapped agent."
                    # (Error handling for no mapped agent - yield error to client and return)
                    print(f"[ENDPOINT] ERROR: {err_msg}")
                    error_message_id = f"val_err_{uuid.uuid4()}"
                    yield json.dumps({"event_type": "START_ASSISTANT_MESSAGE", "data": {"id": error_message_id, "agent_name": "System Message"}})
                    yield json.dumps({"event_type": "RawResponsesStreamEvent", "data": {"delta": "Sorry, an internal error occurred with the code. Please try again."}})
                    yield json.dumps({"event_type": "COMPLETE_ASSISTANT_MESSAGE", "data": {"id": error_message_id}})
                    return
            else:
                # (Error handling for invalid code - yield error to client and return)
                print(f"[ENDPOINT] Input '{current_input_content_for_agent}' on first turn is not a valid registration code. Reason: {validation_response.reason if validation_response.reason else 'Not a valid code format.'}")
                error_message_id = f"val_invalid_{uuid.uuid4()}"
                yield json.dumps({"event_type": "START_ASSISTANT_MESSAGE", "data": {"id": error_message_id, "agent_name": "System Message"}})
                yield json.dumps({"event_type": "RawResponsesStreamEvent", "data": {"delta": "Sorry, you don't seem to have entered a valid code, please try again."}})
                yield json.dumps({"event_type": "COMPLETE_ASSISTANT_MESSAGE", "data": {"id": error_message_id}})
                return

        elif chat_request.last_agent_name:
            initial_agent_name_for_turn = chat_request.last_agent_name
            print(f"[ENDPOINT] Continuing with last agent specified by client: {initial_agent_name_for_turn}")
        else:
            # (Error handling for unexpected state - yield error to client and return)
            print(f"[ENDPOINT] UNEXPECTED STATE: History not empty, but no last_agent_name provided. User message: '{current_input_content_for_agent}'")
            error_message_id = f"err_unexpected_state_{uuid.uuid4()}"
            yield json.dumps({"event_type": "START_ASSISTANT_MESSAGE", "data": {"id": error_message_id, "agent_name": "System Error"}})
            yield json.dumps({"event_type": "RawResponsesStreamEvent", "data": {"delta": "Sorry, an unexpected error occurred. Please try starting a new conversation."}})
            yield json.dumps({"event_type": "COMPLETE_ASSISTANT_MESSAGE", "data": {"id": error_message_id}})
            return

        # --- Agent Execution Loop ---
        active_agent_name_in_chain = initial_agent_name_for_turn
        # This history accumulates messages from the original request PLUS any silent handoffs
        loop_conversation_history = list(current_turn_conversation_history) # Make a mutable copy for the loop
        
        # The current_input_content_for_agent holds the message that triggers the *first* agent in this chain.
        # This could be the raw user input (e.g. registration code) or a system-generated handoff message.
        # It needs to be added to the history for that first agent.
        # For subsequent agents in a silent handoff chain, their "user" input is added later in the loop.

        if active_agent_name_in_chain: # Only add if we are actually going to run an agent
            is_first_message_in_loop_history_user_and_matches_current_input = False
            if loop_conversation_history:
                last_msg = loop_conversation_history[-1]
                if last_msg.role == "user" and last_msg.content == current_input_content_for_agent:
                    is_first_message_in_loop_history_user_and_matches_current_input = True
            
            if not is_first_message_in_loop_history_user_and_matches_current_input:
                # If history is empty, or last message isn't the same user input, add it.
                # This ensures the first agent in the chain gets the triggering input.
                loop_conversation_history.append(ChatMessageInput(role="user", content=current_input_content_for_agent))
                print(f"[LOOP PREP] Added triggering input for first agent ({active_agent_name_in_chain}): '{current_input_content_for_agent}'")


        # This context is specific to the new_registration_agent for its first run with a code.
        # It should only be used once by that agent.
        current_agent_initial_context = initial_agent_context_for_turn

        while active_agent_name_in_chain:
            print(f"[LOOP] Attempting to run agent: {active_agent_name_in_chain}")
            base_agent_from_registry = AGENT_REGISTRY.get(active_agent_name_in_chain)

            if not base_agent_from_registry:
                err_msg = f"Agent '{active_agent_name_in_chain}' for handoff not found in registry."
                print(f"[LOOP] ERROR: {err_msg}")
                error_id = f"err_agent_lookup_loop_{uuid.uuid4()}"
                # This error breaks the chain and is sent to the client.
                yield json.dumps({"event_type": "START_ASSISTANT_MESSAGE", "data": {"id": error_id, "agent_name": "System Error"}})
                yield json.dumps({"event_type": "RawResponsesStreamEvent", "data": {"delta": f"Error: {err_msg}"}})
                yield json.dumps({"event_type": "COMPLETE_ASSISTANT_MESSAGE", "data": {"id": error_id}})
                active_agent_name_in_chain = None # Break loop
                continue

            agent_to_run_dynamically_configured: Agent = base_agent_from_registry
            
            # --- Dynamic Configuration for new_registration_agent (first turn with code) ---
            if current_agent_initial_context and base_agent_from_registry.name == new_registration_agent.name:
                details = current_agent_initial_context.get("parsed_code_details")
                if details:
                    # (Formatting logic for new_registration_agent instructions)
                    team_name_for_prompt = details.get("team_name", "Unknown Team")
                    age_group_val = details.get("age_group")
                    age_group_for_prompt = f"u{age_group_val}" if age_group_val is not None else "Unknown Age Group"
                    start_yy = details.get('season_start_year', 0) % 100
                    end_yy = details.get('season_end_year', 0) % 100
                    registration_season_for_prompt = f"{start_yy:02d}/{end_yy:02d}"
                    
                    final_instructions_for_agent = new_registration_agent_main_instructions.format(
                        **{"Team Name": team_name_for_prompt, "Age Group": age_group_for_prompt, "Registration Season": registration_season_for_prompt}
                    )
                    print(f"[LOOP] Initial turn for {new_registration_agent.name}. Dynamically formatted instructions.")
                    agent_to_run_dynamically_configured = Agent(
                        name=new_registration_agent.name,
                        instructions=append_formatting_guidelines(final_instructions_for_agent),
                        output_type=new_registration_agent.output_type, # Ensure this is correct, e.g., ConversationalJsonResponse
                        tools=deepcopy(new_registration_agent.tools) if new_registration_agent.tools else [],
                        handoffs=deepcopy(new_registration_agent.handoffs) if new_registration_agent.handoffs else [],
                    )
                    current_agent_initial_context = None # Consume this context; it's only for the first run
                else: # Should not happen if initial_agent_context_for_turn was set correctly
                    print(f"[LOOP] WARN: {new_registration_agent.name} was expected to have initial context but details were missing.")
            elif base_agent_from_registry.name == new_registration_agent.name and not current_agent_initial_context:
                print(f"[LOOP] Subsequent turn for {new_registration_agent.name} or it's being run without initial code context.")
                # Ensure instructions are neutral if placeholders were expected.
                # The current new_registration_agent_main_instructions is designed to work even if those are not filled,
                # as the agent is told to check history.
                # We might need to re-apply append_formatting_guidelines if not done by default or if agent obj is reused.
                # For safety, let's re-create it simply if it's this agent to ensure formatting guidelines.
                agent_to_run_dynamically_configured = Agent(
                        name=new_registration_agent.name,
                        instructions=append_formatting_guidelines(new_registration_agent_main_instructions.format(
                            **{"Team Name": "the team", "Age Group": "your age group", "Registration Season": "the current season"} # Generic fillers
                        )), # Or ensure original agent def has this.
                        output_type=new_registration_agent.output_type,
                        tools=deepcopy(new_registration_agent.tools) if new_registration_agent.tools else [],
                        handoffs=deepcopy(new_registration_agent.handoffs) if new_registration_agent.handoffs else [],
                    )
            else: # For other agents or if new_registration_agent is run in a state not needing specific formatting
                print(f"[LOOP] Agent {base_agent_from_registry.name} will run with its standard defined instructions.")
                # Ensure formatting guidelines are applied if not inherently part of agent definition
                # This assumes other agents like player_contact_details_parent_reg also have instructions ready
                # and their Agent objects are correctly defined with formatting appended.
                # For safety, let's ensure it, especially for agents using ConversationalJsonResponse
                if hasattr(base_agent_from_registry, 'output_type') and base_agent_from_registry.output_type.__name__ == 'ConversationalJsonResponse':
                     agent_to_run_dynamically_configured = Agent(
                        name=base_agent_from_registry.name,
                        instructions=append_formatting_guidelines(base_agent_from_registry.instructions),
                        output_type=base_agent_from_registry.output_type,
                        tools=deepcopy(base_agent_from_registry.tools) if base_agent_from_registry.tools else [],
                        handoffs=deepcopy(base_agent_from_registry.handoffs) if base_agent_from_registry.handoffs else [],
                    )


            messages_for_agent_run: List[Dict[str, Any]] = [msg.model_dump() for msg in loop_conversation_history]
            print(f"[LOOP] History for agent run ({agent_to_run_dynamically_configured.name}): {json.dumps(messages_for_agent_run, indent=2)}")

            response_accumulator = {"final_json_response": ""}
            assistant_message_id_for_stream = f"asst_{uuid.uuid4()}" # Unique ID for this agent's interaction in the loop
            
            stream_to_client_this_agent = True # Assume we stream unless silent handoff happens

            # Buffer events for the current agent. We only send them if it's not a silent handoff.
            buffered_events_for_client = []

            async for event_json_str in run_agent_stream(agent_to_run_dynamically_configured, messages_for_agent_run, response_accumulator):
                # Always buffer START and COMPLETE messages.
                # For other messages, buffer them to be sent if not a silent handoff.
                buffered_events_for_client.append(event_json_str)

            # --- Post-agent run processing ---
            final_json_response_str = response_accumulator.get("final_json_response", "{}")
            print(f"[LOOP] Agent {active_agent_name_in_chain} finished. Accumulated JSON: {final_json_response_str}")

            try:
                # This is where we expect ConversationalJsonResponse for agents that use it.
                parsed_agent_response = json.loads(final_json_response_str)
                
                agent_response_text = parsed_agent_response.get("agent_response_text", "No text response.")
                overall_task_complete = parsed_agent_response.get("overall_task_complete", False)
                pass_off_to_agent_name = parsed_agent_response.get("pass_off_to_agent")

                print(f"[LOOP] Parsed response: task_complete={overall_task_complete}, pass_off_to={pass_off_to_agent_name}")

                # Add this agent's full JSON response to the loop's conversation history
                # The role is 'assistant' and content is the raw JSON string it produced.
                loop_conversation_history.append(ChatMessageInput(role="assistant", content=final_json_response_str))

                if overall_task_complete and pass_off_to_agent_name and pass_off_to_agent_name != active_agent_name_in_chain : # Ensure it's a different agent
                    print(f"[LOOP] Silent handoff: From {active_agent_name_in_chain} to {pass_off_to_agent_name}.")
                    stream_to_client_this_agent = False # Do not send buffered events for the handing-off agent

                    # Prepare for next agent in chain
                    active_agent_name_in_chain = pass_off_to_agent_name
                    
                    # The "user" message for the next agent is derived from the previous agent's response text.
                    # This makes the handoff content explicit in the history for the next agent.
                    handoff_input_content = f"System Handoff: The previous agent ({agent_to_run_dynamically_configured.name}) has completed its task. Its summary and findings are: {agent_response_text}"
                    loop_conversation_history.append(ChatMessageInput(role="user", content=handoff_input_content))
                    
                    current_agent_initial_context = None # Clear any prior initial context, it's consumed.
                    # Loop continues with the new active_agent_name_in_chain
                else:
                    print(f"[LOOP] No silent handoff. Agent {active_agent_name_in_chain} response will be sent to client. Task_complete: {overall_task_complete}, Pass_off_to: {pass_off_to_agent_name}")
                    active_agent_name_in_chain = None # Break loop, wait for next user interaction
            
            except json.JSONDecodeError as e:
                print(f"[LOOP] ERROR: Failed to parse final JSON response from agent {active_agent_name_in_chain}: {e}")
                print(f"[LOOP] Raw response was: {final_json_response_str}")
                # Send an error to the client for this agent
                error_event_data = {
                    "event_type": "AgentErrorEvent",
                    "data": {"error": f"Failed to parse final response: {e}", "agent_name": agent_to_run_dynamically_configured.name, "id": assistant_message_id_for_stream }
                }
                buffered_events_for_client.append(json.dumps(error_event_data))
                # Ensure a COMPLETE event for this broken agent stream if START was sent or buffered
                found_start = any("\"event_type\": \"START_ASSISTANT_MESSAGE\"" in evt for evt in buffered_events_for_client if isinstance(evt, str))
                if found_start:
                     buffered_events_for_client.append(json.dumps({"event_type": "COMPLETE_ASSISTANT_MESSAGE", "data": {"id": assistant_message_id_for_stream}}))
                
                active_agent_name_in_chain = None # Break loop due to error

            if stream_to_client_this_agent:
                print(f"[LOOP] Streaming {len(buffered_events_for_client)} events to client for agent {agent_to_run_dynamically_configured.name}.")
                for event_json_str in buffered_events_for_client:
                    yield event_json_str
            else:
                print(f"[LOOP] Suppressed streaming of {len(buffered_events_for_client)} events to client due to silent handoff from agent {agent_to_run_dynamically_configured.name}.")

            # If loop is broken (active_agent_name_in_chain is None), the event_generator finishes.

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