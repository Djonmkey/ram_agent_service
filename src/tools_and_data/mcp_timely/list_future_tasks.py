# timely/list_future_tasks.py

from typing import Any, Dict
import requests
import json
import os
import pathlib
from datetime import date, timedelta


def extract_summary(forecasts: list) -> list:
    """
    Extracts a summary from forecasted tasks with only the required fields.

    :param forecasts: List of forecast task dictionaries
    :return: List of summarized task dictionaries
    """
    summary = []

    for item in forecasts:
        summary.append({
            "id": item.get("id"),
            "note": item.get("note"),
            "title": item.get("title"),
            "description": item.get("description"),
            "from": item.get("from"),
            "to": item.get("to"),
            "estimated_minutes": item.get("estimated_duration", {}).get("total_minutes"),
            "logged_minutes": item.get("logged_duration", {}).get("total_minutes"),
            "project_id": item.get("project", {}).get("id"),
            "project_name": item.get("project", {}).get("name")
        })

    return summary


def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    Executes the MCP command to list forecasted tasks in Timely starting from yesterday.

    :param command_parameters: External command parameters (unused here).
    :param internal_params: Internal config with:
                            - access_token: OAuth token
                            - account_id: Timely workspace ID
    :return: JSON string of forecasted tasks.
    """
    access_token = internal_params["access_token"]
    account_id = internal_params["account_id"]

    #yesterday = (date.today() - timedelta(days=1)).isoformat()
    #url = f"https://api.timelyapp.com/1.1/{account_id}/forecasts?since={yesterday}"
    url = f"https://api.timelyapp.com/1.1/{account_id}/forecasts"

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
    forecasts = response.json()

    # Cache the response if forecasts were returned
    if len(forecasts) > 0:
        # Ensure cache directory exists
        cache_dir = pathlib.Path('mcp_commands/timeely/cache')
        cache_dir.mkdir(exist_ok=True)
        
        # Write the response to the cache file
        cache_file = cache_dir / 'list_tasks.json'
        with open(cache_file, 'w') as f:
            json.dump(forecasts, f, indent=2)
    else:
        # Read forecasts from cache if API returned no results
        cache_file = pathlib.Path('mcp_commands/timeely/cache/list_tasks.json')
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    forecasts = json.load(f)
            except json.JSONDecodeError:
                # If cache file is corrupted, return empty list
                forecasts = []
        else:
            # If cache file doesn't exist, return empty list
            forecasts = []

    summary = extract_summary(forecasts)

    return json.dumps(summary, indent=2)
