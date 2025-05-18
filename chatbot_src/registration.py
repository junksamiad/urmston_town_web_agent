#!/usr/bin/env python

from pydantic import BaseModel, Field
from typing import Literal, Optional 
from agents import Agent

# --- Import Standardized Prompt Prefix ---
from .prompt_prefix import format_prompt_with_prefix

# --- Import Tool (if needed by any agents here, e.g. code_verification_agent if it's kept) ---
from .tools import validate_registration_code # Used by code_verification_agent

# --- Pydantic Model for Final Summary --- 
class RegistrationSummary(BaseModel):
    handoff_type: Literal["renewal", "new"]
    role: Literal["Parent/Guardian", "Player 16+", "Unknown"] 
    player_first_name: Optional[str] = None
    player_last_name: Optional[str] = None
    guardian_first_name: Optional[str] = None
    guardian_last_name: Optional[str] = None
    # Add other relevant fields if needed

# --- New Registration Agent ---
new_registration_agent_instructions = """You are an assigned agent which forms part of a registraton system for a grassrotts footaball club called Urmston Town Juniors FC, based in Manchester, England. You have been passed in some values which provide some starting information about what team and age group your the user belongs to, and what season we are registering for, You have a specific set of sub-tasks below to work through in order to complete your overall objective. Work through these sub-task one at a time, asking the user one question at a time:

1. Welcome the user to the registration portal, briefly acknowledging the key details you've received (e.g., "Welcome to registration for the {Team Name} {Age Group} for the {Registration Season} season!") and ask to take their first and last name to begin. You will refer to them by first name only for the rest of the conversation.
2. Validate their name by ensuring it contains real text only values and they haven't tried to pass in symbols or apha numeric values as their name, and that their name consists of at least two parts. 
3. Determine whether the user is a parent registering their child or a player registering themselves. You can do this by reviewing the user's age_group attirbute passed into you. If it is less than u16s then you can assume the user is a parent and skip this step. If the user's age_group attribute is u16s or above then you need to ask the question and clarify. 

Once you feel you have completed all the sub tasks above, then your final response should be to create a structured json as follows, which will indicate to our system code that you have completed the task so it can handover to another agent and save the transcript of your conversation to a database. 

The JSON schema you MUST output is:
```json
{
  "type": "object",
  "properties": {
    "pass_off_to_agent": {
      "type": "string",
      "description": "The name of the next agent to handoff to. For now, set this to 'RegistrationComplete'."
    },
    "overall_task_complete": {
      "type": "boolean",
      "description": "Set to true when all sub-tasks are completed and this agent's objective is fulfilled. Until all sub-tasks are completed, this must be set to false."
    }
  },
  "required": ["pass_off_to_agent", "overall_task_complete"]
}
```
"""

new_registration_agent = Agent(
    name="New Registration Agent", 
    instructions=format_prompt_with_prefix(new_registration_agent_instructions),
    # No handoffs, no specific output_type defined for now as its task ends after info gathering
)

# --- Renew Registration Agent (Placeholder) ---
renew_registration_agent_instructions = """
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
    instructions=format_prompt_with_prefix(renew_registration_agent_instructions),
    output_type=RegistrationSummary 
)

# Removed old registration_agent and code_verification_agent definitions 