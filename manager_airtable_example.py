from agents import Agent, Runner, function_tool
from dotenv import load_dotenv
import os
import asyncio
from pprint import pformat
from pyairtable import Table

# Load environment variables from .env file
load_dotenv()

# --- Environment Variable Checks ---
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Set it in your .env file.")
if not AIRTABLE_API_KEY:
    raise ValueError("AIRTABLE_API_KEY not found. Set it in your .env file.")
if not AIRTABLE_BASE_ID:
    raise ValueError("AIRTABLE_BASE_ID not found. Set it in your .env file.")
if not AIRTABLE_TABLE_ID:
    raise ValueError("AIRTABLE_TABLE_ID not found. Set it in your .env file.")

# --- Tool Definition (Used by Worker Agent) ---
@function_tool
def get_airtable_records() -> list[dict]:
    """Fetches the first 3 records from the configured Airtable database table."""
    print("--- [Worker Tool] Python function get_airtable_records called ---")
    try:
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        records = table.all(max_records=3)
        print(f"--- [Worker Tool] Successfully fetched {len(records)} records from Airtable ---")
        return records
    except Exception as e:
        print(f"--- [Worker Tool] Error fetching from Airtable: {e} ---")
        return [{ "error": f"Failed to fetch records from Airtable: {e}" }]
# --- End Tool Definition ---

# --- Agent Definitions ---
# Worker Agent: Has the actual Airtable tool
airtable_worker_agent = Agent(
    name="Airtable Worker Agent",
    instructions="You are a specialized agent. Your only job is to use the 'get_airtable_records' tool to fetch data when called.",
    model="gpt-4o", # Can be same or different model
    tools=[get_airtable_records]
)

# Manager Agent: Interacts with user, uses Worker Agent as a tool
manager_agent = Agent(
    name="Manager Agent",
    instructions="You are the primary assistant. Handle user queries. If the user asks for data from the Airtable database, "
                 "you MUST use the 'fetch_database_records' tool to get the data.",
    model="gpt-4o",
    tools=[
        airtable_worker_agent.as_tool(
            tool_name="fetch_database_records", # Tool name as seen by Manager
            tool_description="Use this tool to fetch the first few records from the company Airtable database."
        )
    ]
)
# --- End Agent Definitions ---

# --- Main Execution Logic (Conversational Loop) ---
async def run_conversation():
    print("Starting Manager Agent for Airtable.")
    print("Type 'quit' or 'exit' to end the conversation.")

    conversation_history = []

    while True:
        user_query = input("\nYou: ")
        if user_query.lower() in ["quit", "exit"]:
            print("Exiting conversation.")
            break

        conversation_history.append({"role": "user", "content": user_query})

        print("Manager Agent thinking...")
        try:
            # Run the MANAGER agent with the current history
            result = await Runner.run(manager_agent, conversation_history)

            print(f"\nAgent: {result.final_output}")

            # Update history for the next turn using the Manager's result
            conversation_history = result.to_input_list()

        except Exception as e:
            print(f"\nAn error occurred: {e}")
            if conversation_history:
                 conversation_history.pop()
            pass

if __name__ == "__main__":
    asyncio.run(run_conversation())
# --- End Main Execution Logic --- 