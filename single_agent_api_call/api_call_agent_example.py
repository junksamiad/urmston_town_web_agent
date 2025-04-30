from agents import Agent, Runner, function_tool
from dotenv import load_dotenv
import os
import asyncio
from pprint import pformat # For pretty printing the trace

# Load environment variables from .env file
load_dotenv()

# --- Tool Definition ---
@function_tool
def get_simulated_weather(city: str) -> str:
    """Gets the simulated weather forecast for a given city."""
    print(f"--- Python function get_simulated_weather called with city: {city} ---")
    # In a real scenario, you would make an API call here using libraries like requests or httpx
    # For example: response = requests.get(f"https://api.weatherapi.com/v1/current.json?key=YOUR_KEY&q={city}")
    # simulated_data = response.json()
    # return f"The weather in {city} is {simulated_data['current']['condition']['text']}..."
    return f"SIMULATED: The weather in {city} is sunny and warm."
# --- End Tool Definition ---

# --- Agent Definition ---
weather_agent = Agent(
    name="Weather Agent",
    instructions="You are a helpful assistant that can provide weather information. "
                 "Use the 'get_simulated_weather' tool when the user asks for the weather.",
    model="gpt-4o",
    tools=[get_simulated_weather] # Pass the function itself to the tools list
)
# --- End Agent Definition ---

# --- Main Execution Logic ---
async def run_agent():
    user_query = input("Enter your query for the Weather Agent: ")
    print(f"\nSending query to Weather Agent: '{user_query}'")

    result = await Runner.run(weather_agent, user_query)

    # Print the full result object summary for debugging
    print("\n--- Full Run Result Summary ---")
    print(result)
    print("--- End Full Run Result Summary ---")

    # Inspect the internal attributes of the RunResult object
    print("\n--- Inspecting RunResult Attributes (vars) ---")
    try:
        # Use pformat for better readability of the nested objects
        print(pformat(vars(result)))
    except TypeError:
        print(f"Could not run vars() on result. Type: {type(result)}")
        print("Try printing dir(result) instead:")
        print(dir(result))
    print("--- End Inspecting RunResult Attributes ---")

    # Print the Agent's final output
    print("\nWeather Agent Response:")
    print(result.final_output)

if __name__ == "__main__":
    # Ensure API key is loaded before running
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not found. Set it in your .env file.")
    asyncio.run(run_agent())
# --- End Main Execution Logic --- 