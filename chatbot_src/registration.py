#!/usr/bin/env python

from pydantic import BaseModel, Field, validator
from typing import Literal, Optional 
from agents import Agent

# --- Import Updated Formatting Function ---
from .prompt_prefix import append_formatting_guidelines # UPDATED IMPORT

# --- Import Tool (if needed by any agents here, e.g. code_verification_agent if it's kept) ---
from .tools import validate_registration_code # Used by code_verification_agent

# --- Pydantic Model for Final Summary (used by renew_registration_agent) --- 
class RegistrationSummary(BaseModel):
    handoff_type: Literal["renewal", "new"]
    role: Literal["Parent/Guardian", "Player 16+", "Unknown"] 
    player_first_name: Optional[str] = None
    player_last_name: Optional[str] = None
    guardian_first_name: Optional[str] = None
    guardian_last_name: Optional[str] = None
    # Add other relevant fields if needed

# --- NEW Pydantic Model for Structured Conversational JSON Output ---
class ConversationalJsonResponse(BaseModel):
    agent_response_text: str = Field(..., description="The text content of the agent's response to the user. This text should follow the formatting guidelines provided at the end of the main instructions.")
    overall_task_complete: bool = Field(..., description="True if all sub-tasks are completed and the agent's objective is fulfilled, otherwise false.")
    pass_off_to_agent: Optional[str] = Field(None, description="The name of the next agent to handoff to. Set only when overall_task_complete is true. For now, use 'RegistrationComplete'.")

    @validator('pass_off_to_agent', always=True)
    def check_pass_off_consistency(cls, v, values):
        if values.get('overall_task_complete') is True and v is None:
            pass 
        if values.get('overall_task_complete') is False and v is not None:
            raise ValueError("pass_off_to_agent must be None if overall_task_complete is false.")
        return v

# --- New Registration Agent ---
# User's original core instructions for the agent's tasks:
user_core_instructions_for_new_reg = """Your specific task in this work flow is as follows:

1. Welcome the user to the registration portal, briefly acknowledging the key details you've received (e.g., "Welcome to registration for the {Team Name} {Age Group} for the {Registration Season} season!") and ask to take their first and last name to begin. You will refer to them by first name only for the rest of the conversation.
2. Validate their name by ensuring it contains real text only values and they haven't tried to pass in symbols or apha numeric values as their name, and that their name consists of at least two parts. 
3. Determine whether the user is a parent registering their child or a player registering themselves. You can do this by reviewing the user's age_group attirbute passed into you. If it is less than u16s then you can assume the user is a parent and skip this step. If the user's age_group attribute is u16s or above then you need to ask the question and clarify. 
"""

new_registration_agent_main_instructions = f"""You are an assigned agent which forms part of a registraton system for a grassrotts footaball club called Urmston Town Juniors FC, based in Manchester, England. 
You have been passed in some values which provide some starting information about what team and age group your the user belongs to, and what season we are registering for.

**CRITICAL INSTRUCTION: Your *every* response, whether asking a question or confirming information based on the sub-tasks below, MUST be a single JSON object conforming EXACTLY to the 'ConversationalJsonResponse' schema. No other text or formatting outside this JSON structure is permitted.**

The `agent_response_text` field within the JSON is where your conversational message to the user (based on the sub-tasks) goes. This text should adhere to the formatting guidelines appended to your overall instructions.
For all conversational turns while working through sub-tasks, set `overall_task_complete` to `false` and `pass_off_to_agent` to `null`.

**Your Sub-tasks (Work through these one at a time, using `agent_response_text` for your communication):**
{user_core_instructions_for_new_reg}

**Task Completion Signaling:**
Once you feel you have completed all the sub-tasks above, your final response MUST be a JSON object also conforming to 'ConversationalJsonResponse'. For this final response:
-   Populate `agent_response_text` with a brief concluding message (e.g., "Thank you! All initial details collected.").
-   Set `overall_task_complete` to `true`.
-   Set `pass_off_to_agent` to "RegistrationComplete".

**'ConversationalJsonResponse' JSON Schema (Your output MUST be this JSON object):**
```json
{{
  "type": "object",
  "properties": {{
    "agent_response_text": {{
      "type": "string",
      "description": "The text content of the agent's response to the user for THIS turn. This text should follow the formatting guidelines provided at the end of your instructions."
    }},
    "overall_task_complete": {{
      "type": "boolean",
      "description": "Set to true ONLY when all sub-tasks are completed and this agent's objective is fulfilled. Otherwise, set to false. Until all sub-tasks are completed, this must be set to false."
    }},
    "pass_off_to_agent": {{
      "type": "string",
      "nullable": true,
      "description": "The name of the next agent to handoff to. Set to 'RegistrationComplete' ONLY when overall_task_complete is true. Otherwise, set to null."
    }}
  }},
  "required": ["agent_response_text", "overall_task_complete"]
}}
```
"""

new_registration_agent = Agent(
    name="New Registration Agent", 
    instructions=append_formatting_guidelines(new_registration_agent_main_instructions),
    output_type=ConversationalJsonResponse
)

# --- Renew Registration Agent (Placeholder) ---
renew_registration_agent_main_instructions = """
You are the Renew Registration Agent for Urmston Town Juniors FC.
You have just received initial details derived from a validated registration code. This information will be in the user's first message to you, outlining:
- Membership Status (which will be 'existing' for you)
- Team Name
- Age Group
- Registration Season

For now, please perform the following:
1. Acknowledge the details you've received (Membership Status, Team Name, Age Group, Season).
2. State: "This is the renewal registration path. Further detailed instructions for confirming your renewal will be implemented soon. For now, I will summarize the information I have."
3. Your final output MUST be ONLY a JSON object matching the 'RegistrationSummary' schema. Set 'handoff_type' to 'renewal'. If the initial message contained enough information to infer a player name (e.g. if it mentioned a name in relation to the code), try to populate player_first_name and player_last_name. Otherwise, leave name fields as null or appropriately indicate they are not yet collected in this flow. Assume role is 'Unknown' for now unless explicitly stated in first message.
"""
renew_registration_agent = Agent(
    name="Renew Registration Agent", 
    instructions=append_formatting_guidelines(renew_registration_agent_main_instructions), # Use new function
    output_type=RegistrationSummary 
)

# Removed old registration_agent and code_verification_agent definitions 