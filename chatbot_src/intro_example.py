import os
from dotenv import load_dotenv
from agents import Agent, Runner

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


# Define the agent
agent = Agent(name="Assistant", instructions="You are a helpful assistant")

# Get the query from the user
user_query = input("Please enter your query for the agent: ")

# Run the agent with the user's query
# Note: Runner.run_sync requires the API key to be set as an environment variable.
# load_dotenv() handles making it available via os.getenv(), and the openai library
# typically picks it up automatically from the environment.
print(f"\\nRunning agent with query: '{user_query}'...")
try:
    result = Runner.run_sync(agent, user_query)
    print("\\nAgent Result:")
    print(result.final_output)
except Exception as e:
    print(f"\\nAn error occurred: {e}") 