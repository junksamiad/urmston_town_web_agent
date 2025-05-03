import os
from dotenv import load_dotenv
from agents import Agent
import asyncio
from agents import Runner # Make sure Runner is imported

# Load environment variables from .env file
load_dotenv()

# Check if the API key is loaded (optional but good practice)
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("Error: OPENAI_API_KEY not found in .env file or environment variables.")
    # You might want to exit here or handle the error appropriately
    exit(1)
# else: # Optional: uncomment to confirm key is loaded (don't print the key itself)
#     print("OpenAI API Key loaded successfully.")

print("Defining agents...")

history_tutor_agent = Agent(
    name="History Tutor",
    handoff_description="Specialist agent for historical questions",
    instructions="You provide assistance with historical queries. Explain important events and context clearly.",
)

math_tutor_agent = Agent(
    name="Math Tutor",
    handoff_description="Specialist agent for math questions",
    instructions="You provide help with math problems. Explain your reasoning at each step and include examples",
)

triage_agent = Agent(
    name="Triage Agent",
    instructions="You determine which agent to use based on the user's homework question",
    handoffs=[history_tutor_agent, math_tutor_agent]
)

print("Agents defined successfully.")

# --- Code to run or interact with these agents would go here ---

async def main():
    # Get the query from the user
    user_query = input("Please enter your query for the triage agent: ")
    
    print(f"\nRunning triage agent with query: '{user_query}'...")
    try:
        # Run the triage agent asynchronously
        result = await Runner.run(triage_agent, user_query)
        print("\nAgent Result:")
        print(result.final_output)
    except Exception as e:
        print(f"\nAn error occurred: {e}")

# Standard boilerplate to run the async main function
if __name__ == "__main__":
    asyncio.run(main()) 