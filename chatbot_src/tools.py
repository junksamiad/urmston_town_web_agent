#!/usr/bin/env python

import os
from dotenv import load_dotenv
from pyairtable import Api, Table # Use Api for key loading
from typing import Optional, Dict, Any # For type hinting
from agents import function_tool # For the decorator

# Load environment variables
load_dotenv()

AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
# The table ID for registration records might be different from the one used for code validation.
# Let's assume it's the one you provided earlier for general registration.
# If you have a specific table for *just* these new registration records, update this ID.
REGISTRATION_RECORDS_TABLE_ID = os.getenv("AIRTABLE_TABLE_ID") # Expecting tbl5yWKR7ktOFEyKE or similar via .env

if not AIRTABLE_API_KEY:
    print("Warning: AIRTABLE_API_KEY not found in environment variables.")
if not AIRTABLE_BASE_ID:
    print("Warning: AIRTABLE_BASE_ID not found in environment variables.")
if not REGISTRATION_RECORDS_TABLE_ID:
    print("Warning: REGISTRATION_RECORDS_TABLE_ID (from AIRTABLE_TABLE_ID env var) not found.")

@function_tool
async def create_airtable_registration_record(
    player_first_name: Optional[str] = None,
    player_last_name: Optional[str] = None,
    player_dob: Optional[str] = None, # Store as string, Airtable can parse dates
    player_gender: Optional[str] = None,
    parent_relationship_to_player: Optional[str] = None,
    parent_first_name: Optional[str] = None,
    parent_last_name: Optional[str] = None,
    registree_role: Optional[str] = None, # e.g., "Parent/Guardian", "Player 16+"
    registration_code: Optional[str] = None,
    player_has_any_medical_issues: Optional[bool] = None, # Boolean for Airtable checkbox or Yes/No
    description_of_player_medical_issues: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a new registration record in the Airtable database for Urmston Town Juniors FC.

    Args:
        player_first_name: The first name of the player.
        player_last_name: The last name of the player.
        player_dob: The date of birth of the player (e.g., "YYYY-MM-DD" or "DD/MM/YYYY").
        player_gender: The gender of the player.
        parent_relationship_to_player: The parent/guardian's relationship to the player.
        parent_first_name: The first name of the parent/guardian.
        parent_last_name: The last name of the parent/guardian.
        registree_role: The role of the person completing the registration (e.g., Parent/Guardian).
        registration_code: The unique registration code used.
        player_has_any_medical_issues: Whether the player has known medical issues (True/False).
        description_of_player_medical_issues: Details of any medical issues.

    Returns:
        A dictionary containing the status of the operation ('success' or 'error'), 
        and if successful, the created 'record_id' and 'created_fields', 
        or an error 'message' if unsuccessful.
    """
    if not all([AIRTABLE_API_KEY, AIRTABLE_BASE_ID, REGISTRATION_RECORDS_TABLE_ID]):
        error_msg = "Airtable API Key, Base ID, or Registration Records Table ID is not configured properly."
        print(f"[AIRTABLE TOOL ERROR] {error_msg}")
        return {"status": "error", "message": error_msg}

    try:
        # Use Api object for authentication if needed, or Table directly if key is implicitly handled by pyairtable's env var loading
        # For clarity with explicit key usage for Table:
        table = Table(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, REGISTRATION_RECORDS_TABLE_ID)
        
        fields_to_create = {}
        # Dynamically build the fields dictionary to avoid sending empty keys
        if player_first_name is not None: fields_to_create['player_first_name'] = player_first_name
        if player_last_name is not None: fields_to_create['player_last_name'] = player_last_name
        if player_dob is not None: fields_to_create['player_dob'] = player_dob
        if player_gender is not None: fields_to_create['player_gender'] = player_gender
        if parent_relationship_to_player is not None: fields_to_create['parent_relationship_to_player'] = parent_relationship_to_player
        if parent_first_name is not None: fields_to_create['parent_first_name'] = parent_first_name
        if parent_last_name is not None: fields_to_create['parent_last_name'] = parent_last_name
        if registree_role is not None: fields_to_create['registree_role'] = registree_role
        if registration_code is not None: fields_to_create['registration_code'] = registration_code
        
        if player_has_any_medical_issues is not None:
            # Assuming Airtable field is a Single Select "Yes"/"No" or Checkbox
            fields_to_create['player_has_any_medical_issues'] = "Yes" if player_has_any_medical_issues else "No"
        
        if description_of_player_medical_issues is not None: 
            fields_to_create['description_of_player_medical_issues'] = description_of_player_medical_issues

        if not fields_to_create:
            return {"status": "error", "message": "No data provided to create Airtable record."}

        print(f"[AIRTABLE TOOL] Creating record in table '{REGISTRATION_RECORDS_TABLE_ID}' with fields: {fields_to_create}")
        created_record = table.create(fields_to_create)
        print(f"[AIRTABLE TOOL] Successfully created record. ID: {created_record['id']}")
        return {
            "status": "success", 
            "record_id": created_record['id'], 
            "created_fields": created_record.get('fields', {}) # .get for safety
        }

    except Exception as e:
        error_msg = f"An error occurred while creating Airtable record: {str(e)}"
        print(f"[AIRTABLE TOOL ERROR] {error_msg}")
        return {"status": "error", "message": "Failed to create Airtable record due to an internal error."} 