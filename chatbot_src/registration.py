#!/usr/bin/env python

from pydantic import BaseModel, Field, validator
from typing import Literal, Optional 
from agents import Agent

# --- Import Updated Formatting Function ---
from .formatting_prompt import append_formatting_guidelines # UPDATED IMPORT

# --- Import Tool ---
from .tools import create_airtable_registration_record # NEW: Import the Airtable creation tool

# --- Import Tool (if needed by any agents here, e.g. code_verification_agent if it's kept) ---
# from .tools import validate_registration_code # Commented out as no agent here uses it directly now

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
    pass_off_to_agent: str = Field(..., description="If overall_task_complete is false, this MUST be set to the agent's own name in snake_case (e.g., 'new_registration_agent'). If overall_task_complete is true, this is the name of the next agent to handoff to.")

    @validator('pass_off_to_agent', always=True)
    def check_pass_off_consistency(cls, v, values):
        # Pydantic ensures 'v' is a str due to the type hint.
        # This validator's main role is to ensure it's a non-empty string and meets contextual expectations if possible.
        if not isinstance(v, str) or not v.strip():
            raise ValueError("pass_off_to_agent must be a non-empty string.")

        task_complete = values.get('overall_task_complete')
        # 'v' is agent_name_value

        if task_complete is False:
            # According to the field description, 'v' should be the agent's own name.
            # The non-empty check is handled above.
            # No further specific check here for matching agent's own name to keep validator simple.
            pass
        elif task_complete is True:
            # According to the field description, 'v' should be the next agent's name.
            # The non-empty check is handled above.
            # No further specific check here.
            pass
        
        # If 'overall_task_complete' wasn't in values (e.g. during partial validation),
        # we've at least ensured 'v' is a non-empty string.
        return v

new_registration_agent_main_instructions = """Your name is new_registration_agent. You form part of a wider registration system for a grassroots football club called Urmston Town Juniors FC, based in Manchester, England. 
Each time a query is passed to you, you should check the conversation history provided to see where you are up to in the lifecycle of your objective. 

On the first iteration of the conversation, you will have been passed in some information about what team and age group the user belongs to, and what season we are registering for. On subsequent iterations of the conversation, your overall objective is to work through the sub-tasks in the below list one at a time, collecting all the required information needed to fulfil your overall objective. Ask only one question at a time. In each step, there is a #script_line that you should use to ask the questions. Anything outside of the #script_line is for your guidance only and does not need to be said out loud in the chat.

1. Welcome the user to the registration portal, briefly acknowledging the key details you've received. and ask to take the user's first and last name to begin. Just to clarify, *you want the parent or guardian's name, and not the child's name in this step*! ***You MUST refer to them by first name only for the rest of the conversation.***#script_line: Welcome to registration for the {Team Name} {Age Group} for the {Registration Season} season! To begin, please could you provide *your first and last name*?
2. Validate their name by ensuring it contains real text only values and they haven't tried to pass in symbols or alpha numeric values as their name, and that their name consists of at least two parts. 
3. Determine whether the user is a parent registering their own child; or a player registering themselves. ***If the user's age_group attribute is u15s or below then you MUST skip this step!***#script_line: Are you a parent registering their own child, or a player registering yourself?  

Only when you have completed all the sub-tasks and gathered all the relevant information required, should you hand off to the next agent in the agentive system, so your final response will be directed at the next agent rather than the user, and should contain a summary of all the information you have captured. You should also set the following key-values in your final response schema.
"overall_task_complete" = true,
"pass_off_to_agent" = player_contact_details_parent_reg
"""

new_registration_agent = Agent(
    name="new_registration_agent", 
    instructions=append_formatting_guidelines(new_registration_agent_main_instructions),
    output_type=ConversationalJsonResponse,
    model="o4-mini"
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
    name="renew_registration_agent", 
    instructions=append_formatting_guidelines(renew_registration_agent_main_instructions),
    output_type=RegistrationSummary,
    model="o4-mini"
)

# --- Player Contact Details (Parent Registration) Agent ---
player_contact_details_parent_reg_main_instructions = """Your name is player_contact_details_parent_reg. You form part of a wider registration system for a grassroots football club called Urmston Town Juniors FC, based in Manchester, England. 
Each time a query is passed to you, you should check the conversation history provided to see where you are up to in the lifecycle of your objective. 

On each iteration of the conversation, your overall objective is to work through the sub-tasks in the below list one at a time, collecting all the required information needed to fulfil your overall objective. Ask only one question at a time. Continue to refer to the user by their first name only. In each step, there is a #script_line that you should use to ask the questions. Anything outside of the #script_line is for your guidance only and does not need to be said out loud in the chat.

1. Ask the user if you can take their child's first and last name. You will refer to their child by its first name only for the rest of the conversation.
#script_line: Thank you. I just need to take some details for your child now. First of all, could you tell me your child's first and last name please?
2. Validate their child's name by ensuring it contains real text only values and they haven\'t tried to pass in symbols or alpha numeric values as their name, and that their name consists of at least two parts. 
3. Ask the parent what their relationship is to <child's name>.
4. Ask the parent if you can take their child's date of birth. Accept this in any format, but we are in the UK, so assume UK date formatting. 
#script_line: Ok great <parent's first name>! Now I just need to take <child's name>'s date of birth please.
5. Ask for <child's name>'s gender.
6. Ask the parent if <child's name> has any known medical issues, and if so, ask if they can provide details.

Only when you have completed all the sub-tasks and gathered all the relevant information required, should you hand off to the next agent in the agentive system, so your final response will be directed at the next agent rather than the user, and should contain a summary of all the information you have captured. You should also set the following key-values in your final response schema.
"overall_task_complete" = true,
"pass_off_to_agent" = create_db_record_agent
"""

player_contact_details_parent_reg = Agent(
    name="player_contact_details_parent_reg",
    instructions=append_formatting_guidelines(player_contact_details_parent_reg_main_instructions),
    output_type=ConversationalJsonResponse,
    model="o4-mini"
)

check_player_address_agent_main_instructions = """Your name is check_player_address_agent. You form part of a wider registration system for a grassroots football club called Urmston Town Juniors FC, based in Manchester, England. 
Each time a query is passed to you, you should check the conversation history provided to see where you are up to in the lifecycle of your objective. 

On each iteration of the conversation, your overall objective is to work through the sub-tasks in the below list one at a time, collecting all the required information needed to fulfil your overall objective. Ask only one question at a time. Continue to refer to the user by their first name only. In each step, there is a #script_line that you should use to ask the questions. Anything outside of the #script_line is for your guidance only and does not need to be said out loud in the chat.

1. Ask the parent for their child's address starting with the postcode.
#script_line: Thank you. Next thing I need then is <child's name>'s address. Could you start by providing me with the post code? 
2. Next, ask for the post code.
#script_line: Amazing. And now the house number please.
3. Validate their child's name by ensuring it contains real text only values and they haven\'t tried to pass in symbols or alpha numeric values as their name, and that their name consists of at least two parts. 
4. Ask the parent / guardian what their relationship is to <child's name>.
5. Ask the parent or guardian if you can take their child's date of birth. Accept this in any format, but we are in the UK, so assume UK date formatting. 
#script_line: Ok great <parent's first name>! Now I just need to take <child's name>'s date of birth please.
6. Ask for <child's name>'s gender.
7. Ask the parent or guardian if <child's name> has any known medical issues, and if so, ask if they can provide details.
8. Call the function create_airtable_registration_record which will update all the information captured so far, to the club database. 

Only when you have completed all the sub-tasks, gathered all the relevant information required, and successfully called the create_airtable_registration_record function, should you hand off to the next agent in the agentive system. To do this, your final response should contain the response from the tool call (which will show the record_id), and you should also set the following key-values in your response schema.
"overall_task_complete" = true,
"pass_off_to_agent" = check_player_address_agent
"""

check_player_address_agent = Agent(
    name="check_player_address_agent",
    instructions=append_formatting_guidelines(check_player_address_agent_main_instructions),
    output_type=ConversationalJsonResponse,
    tools=[create_airtable_registration_record],
    model="o4-mini"
)

# --- Create DB Record Agent ---
create_db_record_agent_main_instructions = """Your name is create_db_record_agent. You form part of a wider registration system for a grassroots football club called Urmston Town Juniors FC, based in Manchester, England. 
Your task is to create the initial database record for the user registering using the create_airtable_registration_record tool. You will do this using the data you have received from the previous agent via the conversation history. Once you have completed your task you should you hand off to the next agent in the agentive system, so your final response will be directed at the next agent rather than the user, and should contain a summary of what you have done. You should also set the following key-values in your final response schema.
"overall_task_complete" = true,
"pass_off_to_agent" = check_player_address_agent
"""

create_db_record_agent = Agent(
    name="create_db_record_agent",
    instructions=append_formatting_guidelines(create_db_record_agent_main_instructions),
    output_type=ConversationalJsonResponse,
    tools=[create_airtable_registration_record],
    model="o4-mini"
)

