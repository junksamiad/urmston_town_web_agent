#!/usr/bin/env python

"""Module to define and format a standardized prompt prefix for all agents."""

# New, concise formatting guidelines
DEFAULT_FORMATTING_GUIDELINES = """IMPORTANT: When providing text meant for the user (e.g., in 'agent_response_text'), use the following formatting guidelines:
- Use double line breaks (creating an empty line) between distinct pieces of information or questions for visual separation.
- Use bold for emphasis and important information using Markdown (e.g., **this is important**).
- Use bullet points and numbered lists for structured information.
- Use headings (## and ###) for section titles where appropriate.
- Use code formatting (backticks) for codes or specific inputs.
"""

def append_formatting_guidelines(main_instructions: str) -> str:
    """Appends the standardized formatting guidelines to the main agent instructions."""
    return f"{main_instructions}\n\n{DEFAULT_FORMATTING_GUIDELINES}" 