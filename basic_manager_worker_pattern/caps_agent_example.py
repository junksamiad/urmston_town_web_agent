from agents import Agent, Runner
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Ensure the API key is loaded (optional check, good practice)
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY not found in environment variables. Make sure it's set in your .env file.")

# 1. Define the Specialized Agent (Worker)
caps_agent = Agent(
    name="Caps Assistant",
    instructions="You are a helpful assistant. You MUST respond ONLY in ALL CAPS.",
    model="gpt-4o"
)

# 2. Define the Manager Agent
manager_agent = Agent(
    name="Manager Agent",
    instructions=(
        "You are the primary assistant. Greet the user and answer their questions normally. "
        "ONLY if the user explicitly asks for the response IN ALL CAPS, use the 'get_caps_response' tool. "
        "Otherwise, answer directly."
    ),
    model="gpt-4o", # Manager can use the same or a different model
    tools=[
        caps_agent.as_tool(
            tool_name="get_caps_response",
            tool_description="Use this tool when the user specifically asks for a response in ALL CAPS."
        )
    ]
)

# 3. Get input for the Manager
user_query = input("Enter your query for the Manager Agent: ")

# 4. Run the MANAGER agent
print(f"\nSending query to Manager Agent: '{user_query}'")
# Using async Runner.run as it's generally safer with potential internal async operations
import asyncio

async def run_manager():
    result = await Runner.run(manager_agent, user_query)
    # 5. Print the full result object summary for debugging
    print("\n--- Full Run Result Summary ---")
    print(result)
    print("--- End Full Run Result Summary ---")

    # Inspect the internal attributes of the RunResult object
    print("\n--- Inspecting RunResult Attributes (vars) ---")
    try:
        print(vars(result))
    except TypeError:
        print(f"Could not run vars() on result. Type: {type(result)}")
        print("Try printing dir(result) instead:")
        print(dir(result))
    print("--- End Inspecting RunResult Attributes ---")

    # Print the Manager's final output
    print("\nManager Agent Response:")
    print(result.final_output)

if __name__ == "__main__":
    asyncio.run(run_manager()) 