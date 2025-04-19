# timely/list_projects.py

from typing import Any, Dict
import requests
import json
import os
import pathlib


def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    Executes the MCP command to list all active projects in Timely.

    :param command_parameters: External command parameters (unused here).
    :param internal_params: Internal config with:
                            - access_token: OAuth token
                            - account_id: Timely workspace ID
    :return: JSON string of active projects including budget metadata and inferred scope.
    """
    access_token = internal_params["access_token"]
    account_id = internal_params["account_id"]

    url = f"https://api.timelyapp.com/1.1/{account_id}/projects"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": "HTTP/1.0",
        "Host": "api.timelyapp.com",
        "Cookie": ""
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    projects = response.json()

       # Cache the response if projects were returned
    if len(projects) > 0:
        # Ensure cache directory exists
        cache_dir = pathlib.Path('mcp_commands/timeely/cache')
        cache_dir.mkdir(exist_ok=True)
        
        # Write the response to the cache file
        cache_file = cache_dir / 'list_projects.json'
        with open(cache_file, 'w') as f:
            json.dump(projects, f, indent=2)

    else:
        # Read projects from cache if API returned no results
        cache_file = pathlib.Path('mcp_commands/timeely/cache/list_projects.json')
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    projects = json.load(f)
            except json.JSONDecodeError:
                # If cache file is corrupted, return empty list
                projects = []
        else:
            # If cache file doesn't exist, return empty list
            projects = []

    simplified = []

    for project in projects:
        if not project.get("active", True):
            continue

        name_lower = project.get("name", "").lower()
        if "weekly" in name_lower:
            inferred_scope = "weekly"
        elif "monthly" in name_lower:
            inferred_scope = "monthly"
        else:
            inferred_scope = None

        simplified.append({
            "id": project["id"],
            "name": project["name"],
            "description": project.get("description"),
            "budget": project.get("budget"),
            "budget_type": project.get("budget_type"),
            "has_recurrences": project.get("has_recurrences"),
            "budget_calculation": project.get("budget_calculation"),
            "inferred_budget_scope": inferred_scope
        })
    
    return json.dumps(simplified, indent=2)
