#!/usr/bin/env python

import os
from dotenv import load_dotenv
from pyairtable import Api, Table # Use Api for key loading
from agents import function_tool # For the decorator

# Load environment variables
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
REGISTRATION_CODE_TABLE_ID = "tblQfnU1bQudFVhDu" # Hardcoded as requested

if not AIRTABLE_API_KEY:
    print("Warning: AIRTABLE_API_KEY not found in environment variables.")
if not AIRTABLE_BASE_ID:
    print("Warning: AIRTABLE_BASE_ID not found in environment variables.")

@function_tool
def validate_registration_code(registration_code: str) -> dict:
    """
    Validates a provided registration code by checking if it exists (case-insensitive) 
    in the 'code' field of the specified Airtable table.

    Args:
        registration_code: The code provided by the user.

    Returns:
        A dictionary with 'status': 'valid' if found, or 'status': 'invalid' with a 'reason' if not found or an error occurred.
    """
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
        return {"status": "invalid", "reason": "Airtable API Key or Base ID not configured."}

    try:
        # Use Api object for authentication
        api = Api(AIRTABLE_API_KEY)
        # Get the table
        code_table = api.table(AIRTABLE_BASE_ID, REGISTRATION_CODE_TABLE_ID)
        
        # Convert input code to lowercase for case-insensitive comparison
        code_to_check = registration_code.strip().lower() 

        # Construct the formula to find the code (case-insensitive)
        # Using LOWER() in the formula ensures we match regardless of case in Airtable
        formula = f"LOWER({{code}}) = '{code_to_check}'"

        # Find the first matching record
        match = code_table.first(formula=formula)

        if match:
            print(f"Airtable lookup successful: Found code '{registration_code}' (as '{code_to_check}').")
            return {"status": "valid"}
        else:
            print(f"Airtable lookup unsuccessful: Code '{registration_code}' (as '{code_to_check}') not found.")
            return {"status": "invalid", "reason": "Code not found"}

    except Exception as e:
        print(f"Error during Airtable lookup for code '{registration_code}': {e}")
        return {"status": "invalid", "reason": f"An error occurred during validation: {e}"} 