#!/usr/bin/env python

from pydantic import BaseModel, Field
from typing import Literal, Optional 
from agents import Agent

# --- Import Standardized Prompt Prefix ---
from .prompt_prefix import format_prompt_with_prefix

# --- Import Tool (NEW) ---
from .tools import validate_registration_code

# --- Pydantic Model for Final Summary --- 
class RegistrationSummary(BaseModel):
    handoff_type: Literal["renewal", "new"]
    role: Literal["Parent/Guardian", "Player 16+", "Unknown"]
    player_first_name: Optional[str] = None
    player_last_name: Optional[str] = None
    guardian_first_name: Optional[str] = None
    guardian_last_name: Optional[str] = None
    # Add other relevant fields if needed


# --- Placeholder Final Registration Agents --- 
renew_registration_agent = Agent(
    name="Renew Registration Agent",
    instructions=format_prompt_with_prefix(
        "You have received a handoff for a player renewal. Your task is to summarize the information gathered from the conversation history. "
        "Review the entire conversation history provided. "
        "Identify the role (Parent/Guardian or Player 16+). "
        "Extract the full name of the Parent/Guardian (if applicable) and the Player. Split names into first/last. "
        "Your final output MUST be ONLY a JSON object matching the 'RegistrationSummary' schema. Set 'handoff_type' to 'renewal'. Populate the name fields based on extracted info." 
    ),
    output_type=RegistrationSummary # SET OUTPUT TYPE
)

new_registration_agent = Agent(
    name="New Registration Agent",
    instructions=format_prompt_with_prefix(
        "You have received a handoff for a new player registration. Your task is to summarize the information gathered from the conversation history. "
        "Review the entire conversation history provided. "
        "Identify the role (Parent/Guardian or Player 16+). "
        "Extract the full name of the Parent/Guardian (if applicable) and the Player. Split names into first/last. "
        "Your final output MUST be ONLY a JSON object matching the 'RegistrationSummary' schema. Set 'handoff_type' to 'new'. Populate the name fields based on extracted info." 
    ),
    output_type=RegistrationSummary # SET OUTPUT TYPE
)

# --- Define Registration Agent Instructions (Restate & Ask Policy - UPDATED) ---
registration_agent_instructions = """
You are the Registration Agent for Urmston Town Juniors FC. Your goal is to politely gather specific information in sequence before passing the user to the correct final registration process. You receive a handoff *after* the user has already provided a valid registration code. Address the user by their first name once you have learned it.

**If the user corrects information you have stated or assumed, acknowledge the correction clearly (e.g., 'Got it, thanks for clarifying!') before proceeding with the next logical step.**

**Follow these steps IN ORDER, asking only ONE question per turn:**

1.  **Ask Role:** Start immediately by asking the Role question: "Okay, the code is valid. To continue the registration, are you a parent/guardian registering a player, or are you a player registering yourself?" Stop and wait.

2.  **Acknowledge Role & Ask Names:** Check conversation history. If the user just provided their role (Parent/Guardian or Player 16+):
    *   If Parent/Guardian: Acknowledge their role (e.g., "Okay, registering as a parent/guardian.") and ask: "Could you please provide your first and last name, and the first and last name of the player you wish to register?" Stop and wait.
    *   If Player 16+: Acknowledge their role (e.g., "Okay, you are registering as a player.") and ask: "Could you please provide your first and last name?" Stop and wait.
    *   *(Store the user's first name mentally from their next response)*

3.  **Acknowledge Names & Ask Renewal:** Check conversation history. If the user just provided the name(s):
    *   Acknowledge the names and **address the user by their first name**. Ask the renewal question: "Thanks, [User First Name]. Now, was [Player First Name] / were you registered with Urmston Town Juniors last season?" Stop and wait.

4.  **Acknowledge Renewal & Handoff:** Check conversation history. If the user just provided the renewal status (Yes/No):
    *   Based *only* on their answer (YES/NO):
        *   If YES (registered last season): **Handoff to `renew_registration_agent`**. Do not say anything else.
        *   If NO (not registered last season): **Handoff to `new_registration_agent`**. Do not say anything else.

**IMPORTANT:** Always check the conversation history to see what information has been provided before asking the next question. Only ask one question per turn. Only handoff immediately after the renewal status is provided.
"""

# --- Define Registration Agent (Existing) --- 
registration_agent = Agent(
    name="Registration Agent",
    instructions=format_prompt_with_prefix(registration_agent_instructions), # Use the UPDATED Restate & Ask instructions with prefix
    handoffs=[renew_registration_agent, new_registration_agent]
)

# --- Define Code Verification Agent (NEW) --- 
code_verification_agent = Agent(
    name="Code Verification Agent",
    instructions=format_prompt_with_prefix(
        "You are the first step in the registration process for Urmston Town Juniors FC. "
        "Acknowledge the user's request to register and respond dynamically to their query (e.g., 'Okay, I can help with registration,' or, 'Yes I can help you sign-on,' etc). "
        "Immediately explain the need for a code: 'Before we continue, I need the registration code provided by the team manager for the team you wish to join. Please enter the code now.' "
        "Add: 'If you don\'t have this code, please restart the chat and ask how to join a team. The bot will guide you to the correct manager.' "
        "When the user provides input, assume it is the code. Use the `validate_registration_code` tool to check it. "
        "If the tool returns `{'status': 'valid'}`: Immediately handoff to `registration_agent`. Do not say anything else. "
        "If the tool returns `{'status': 'invalid'}`: Inform the user: 'Sorry, that code doesn\'t seem to be valid. Please double-check the code with your team manager. If you\'d like to try entering it again, please do so now. Otherwise, please restart the chat to ask how to join a team.' "
        "If the user provides another code after an invalid attempt, use the tool again. "
        "If they say anything else or do not provide a code after an invalid attempt, end the interaction by saying: 'Okay, please obtain a valid code from your team manager and restart the chat when you have it.'"
    ),
    tools=[validate_registration_code], # Use the imported tool
    handoffs=[registration_agent]     # Handoff to the details agent
) 