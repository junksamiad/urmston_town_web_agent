#!/usr/bin/env python
import os
import re 
import asyncio
from dotenv import load_dotenv
from pydantic import BaseModel, Field # Keep BaseModel if needed elsewhere, remove if not
from typing import Literal, Optional # Keep these if needed elsewhere

# --- Agent SDK Imports ---
from agents import Agent, InputGuardrail, GuardrailFunctionOutput, Runner, RunContextWrapper, function_tool 

# --- Import Standardized Prompt Prefix ---
from .formatting_prompt import format_prompt_with_prefix

# --- Import Registration Components (Updated) ---
from .registration import registration_agent, RegistrationSummary, renew_registration_agent, new_registration_agent, code_verification_agent # Added code_verification_agent

# --- Load Environment Variables ---
load_dotenv()

# OpenAI Key
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: FATAL: OPENAI_API_KEY not found.")
    exit(1)
else:
    print("OpenAI API Key loaded successfully.")

# Airtable Keys (Added checks for clarity)
airtable_api_key = os.getenv("AIRTABLE_API_KEY")
airtable_base_id = os.getenv("AIRTABLE_BASE_ID")
if not airtable_api_key:
    print("Warning: AIRTABLE_API_KEY not found in .env. Code verification tool will fail.")
if not airtable_base_id:
    print("Warning: AIRTABLE_BASE_ID not found in .env. Code verification tool will fail.")

# --- Define Classification Rules with Actions (Updated Registration Target) ---
query_classification_list = """ 
{ 
  "classification_policy": [
    {
      "classification": "registration",
      "keywords": ["register", "signing on", "sign up", "join", "get involved", "membership"],
      "description": "Query is about joining the club or becoming a member.",
      "action_type": "handoff",
      "action_target": "Code Verification Agent" # UPDATED from "Registration Agent"
    },
    {
      "classification": "payments",
      "keywords": ["membership fee", "subscription", "fee", "subs", "direct debit", "standing order", "payment issues", "setup payment", "amend payment", "cancel payment"],
      "description": "Query is about anything relating to setting up, modifying, making or cancelling payments of any sort.",
      "action_type": "handoff",
      "action_target": "Payments Agent" # Use the Agent name string here
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

# --- Placeholder Payments Agent --- 
# (Keep this placeholder here or move if creating payments.py)
payments_agent = Agent(
    name="Payments Agent", 
    instructions=format_prompt_with_prefix("You handle payment queries and assist users with all financial aspects of club membership. Help with setting up payments, addressing payment issues, and explaining fee structures.") # Updated with prompt prefix
)

# --- Router Agent Definition (Updated Handoffs) ---
router_agent = Agent(
    name="Router Agent",
    instructions=format_prompt_with_prefix(f"""
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
"""),
    # Reference the imported agents in handoffs
    handoffs=[code_verification_agent, registration_agent, payments_agent], # Added code_verification_agent
    # tools=[get_training_schedule] # Add tools here if needed
)

# --- Agents are now defined across files ---
print("Agents (Router, Payments placeholders) defined in go.py.")
print("Agents (Registration flow) imported from registration.py.")


# --- Emoji Mapping for Agents (Updated) --- 
AGENT_EMOJIS = {
    "Router Agent": "🔵",  
    "Code Verification Agent": "🔑", # Added
    "Registration Agent": "🟢", 
    "Renew Registration Agent": "🟡", 
    "New Registration Agent": "🟣", 
    "Payments Agent": "🟠", 
    "DEFAULT": "⚪"  
}


# --- Main Execution Logic (Updated for Conversation) ---
async def main():
    print("\nPlease enter your query:")
    
    previous_run_result = None 

    while True:
        user_message = input("You: ")
        if user_message.lower() in ["quit", "exit"]:
            print("Ending conversation.")
            break

        # Determine Agent and Input for this turn
        agent_to_run = router_agent 
        
        if previous_run_result is None:
            agent_input = user_message
            print("(Starting with Router Agent - initial input)")
        else:
            if hasattr(previous_run_result, 'last_agent') and previous_run_result.last_agent:
                 agent_to_run = previous_run_result.last_agent
                 print(f"(Continuing with {agent_to_run.name})")
            else:
                 print("(Fallback to Router Agent - missing last_agent)")
                 agent_to_run = router_agent 
                 
            try:
                input_list_for_next_run = previous_run_result.to_input_list()
                agent_input = input_list_for_next_run + [{
                    "role": "user", 
                    "content": user_message
                }]
                print(f"(Processing with history - {len(agent_input)} items)")
                print("--- Input to Agent (History + New Message) ---")
                for item in agent_input:
                     print(item) 
                print("--------------------------------------------")
            except Exception as e:
                 print(f"Error creating input list: {e}. Processing only current message.")
                 agent_input = user_message 
                 previous_run_result = None 
                 agent_to_run = router_agent 
                 print("(Resetting to Router Agent due to history error)")
        
        print(f"Agent ({agent_to_run.name}) thinking...")
        try:
            current_run_result = await Runner.run(agent_to_run, agent_input)

            # Display the agent's response 
            print("\n--- Agent Response ---")
            responding_agent_name = "Agent" 
            agent_emoji = AGENT_EMOJIS.get("DEFAULT")
            
            if hasattr(current_run_result, 'last_agent') and current_run_result.last_agent and hasattr(current_run_result.last_agent, 'name'):
                responding_agent_name = current_run_result.last_agent.name
                agent_emoji = AGENT_EMOJIS.get(responding_agent_name, AGENT_EMOJIS.get("DEFAULT"))
            
            if current_run_result.final_output:
                # Check if the output is our structured summary 
                # Use the imported RegistrationSummary type
                if isinstance(current_run_result.final_output, RegistrationSummary): 
                    print(f"{agent_emoji} {responding_agent_name}: (Structured Output)")
                    print(current_run_result.final_output.model_dump_json(indent=2))
                else:
                    print(f"{agent_emoji} {responding_agent_name}: {current_run_result.final_output}") 
            else:
                print(f"{agent_emoji} {responding_agent_name}: (No response generated for this turn)")

            previous_run_result = current_run_result

        except Exception as e:
            error_message = str(e)
            if "triggered tripwire" in error_message.lower():
                print("\n--- Final Result ---")
                print("Sorry, the input provided is not valid.")
                print(f"(Debug info: {error_message})")
            else:
                print(f"\nAn error occurred during execution: {e}")
            previous_run_result = None 
            print("(Resetting conversation history due to error)")

# --- Boilerplate ---
if __name__ == "__main__":
    asyncio.run(main()) 