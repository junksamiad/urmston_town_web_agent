from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API key from environment
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError("Please set the OPENAI_API_KEY environment variable in your .env file")

client = OpenAI(api_key=api_key)

completion = client.chat.completions.create(
  model="gpt-4.1",
  messages=[
      {
          "role": "user",
          "content": "Write a one-sentence bedtime story about a unicorn."
      }
  ]
)

# Print the entire completion object
print("Full completion object:")
print(completion)

# Print the message content
#print("\nJust the message content:")
#print(completion.choices[0].message.content)
