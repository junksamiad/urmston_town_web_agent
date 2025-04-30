from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from agents import Agent, Runner
from dotenv import load_dotenv
import os
import uvicorn # Added for running the app
import asyncio # Needed for async run
from pprint import pformat # To pretty-print the trace

# Load environment variables from .env file
load_dotenv()

# Ensure the API key is loaded
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY not found. Set it in your .env file.")

# --- Agent Definitions ---
# Specialized Agent (Worker)
caps_agent = Agent(
    name="Caps Assistant",
    instructions="You are a helpful assistant. You MUST respond ONLY in ALL CAPS.",
    model="gpt-4o"
)

# Manager Agent
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
# --- End Agent Definitions ---


# --- FastAPI App Setup ---
app = FastAPI()

# Check if templates directory exists, create if not
if not os.path.exists("templates"):
    os.makedirs("templates")

templates = Jinja2Templates(directory="templates")
# --- End FastAPI App Setup ---


# --- Web Routes ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the initial HTML form."""
    # Add trace=None to the initial context
    return templates.TemplateResponse("index.html", {"request": request, "response": None, "query": None, "trace": None})

@app.post("/ask", response_class=HTMLResponse)
async def ask_agent(request: Request, user_query: str = Form(...)):
    """Handles form submission, runs the manager agent, and displays the result and trace."""
    print(f"Received query for Manager: {user_query}")
    agent_response = None
    execution_trace = None
    try:
        # Run the MANAGER agent asynchronously
        result = await Runner.run(manager_agent, user_query)
        agent_response = result.final_output

        # Extract and format the execution trace (new_items)
        if hasattr(result, 'new_items') and result.new_items:
            # Use pformat for a more readable representation of the objects
            execution_trace = pformat(result.new_items)
        else:
            execution_trace = "No execution trace (new_items) found."

        print(f"Manager agent final response: {agent_response}")
        # Optionally print trace to console as well
        # print(f"\nExecution Trace:\n{execution_trace}")

    except Exception as e:
        print(f"Error running manager agent: {e}")
        agent_response = f"ERROR: {e}"
        execution_trace = f"Error during execution: {e}"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "response": agent_response,
        "query": user_query,
        "trace": execution_trace # Pass trace to the template
    })
# --- End Web Routes ---

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting FastAPI server...")
    # Make sure the templates directory exists before starting Uvicorn
    if not os.path.exists("templates"):
        os.makedirs("templates")
        print("Created 'templates' directory.")
    # Create a dummy index.html if it doesn't exist, to prevent Uvicorn errors on startup
    if not os.path.exists("templates/index.html"):
        with open("templates/index.html", "w") as f:
            f.write("<html><body>Placeholder</body></html>")
        print("Created placeholder 'templates/index.html'.")

    uvicorn.run(app, host="0.0.0.0", port=8000)
# --- End Main Execution --- 