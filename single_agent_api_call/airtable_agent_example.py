from agents import Agent, Runner, function_tool
from dotenv import load_dotenv
import os
import asyncio
from pprint import pformat
from pyairtable import Table  # Import the Airtable Table class

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

# --- Tool Definition ---
@function_tool
def get_airtable_records() -> list[dict]:
    """Fetches the first 3 records from the configured Airtable database table."""
    print("--- Python function get_airtable_records called ---")
    try:
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
        # Fetch only the first 3 records
        records = table.all(max_records=3)
        print(f"--- Successfully fetched {len(records)} records from Airtable ---")
        # Return the list of record dictionaries (includes id, fields, createdTime)
        return records
    except Exception as e:
        print(f"--- Error fetching from Airtable: {e} ---")
        return [{ "error": f"Failed to fetch records from Airtable: {e}" }]
# --- End Tool Definition ---

# --- Agent Definition ---
airtable_agent = Agent(
    name="Airtable Agent",
    instructions="You are an assistant that can fetch data from our company Airtable database. "
                 "Use the 'get_airtable_records' tool when the user asks to see data from the table.",
    model="gpt-4o",
    tools=[get_airtable_records] # Provide the function as a tool
)
# --- End Agent Definition ---

# --- Main Execution Logic (Conversational Loop) ---
async def run_conversation():
    print("Starting conversational Airtable Agent.")
    print("Type 'quit' or 'exit' to end the conversation.")

    # Initialize conversation history (list of message dicts)
    conversation_history = []

    while True:
        user_query = input("\nYou: ")
        if user_query.lower() in ["quit", "exit"]:
            print("Exiting conversation.")
            break

        # Add user message to history in the expected format
        conversation_history.append({"role": "user", "content": user_query})

        print("Airtable Agent thinking...")
        try:
            # Run the agent with the current full history
            result = await Runner.run(airtable_agent, conversation_history)

            # Print the agent's response for this turn
            print(f"\nAgent: {result.final_output}")

            # IMPORTANT: Update history for the next turn using the result
            # This includes the user message, tool calls/results, and agent response
            conversation_history = result.to_input_list()

        except Exception as e:
            print(f"\nAn error occurred: {e}")
            # Remove last user query on error to prevent resending bad input
            if conversation_history:
                 conversation_history.pop()
            pass

if __name__ == "__main__":
    asyncio.run(run_conversation())
# --- End Main Execution Logic --- 