# timely/project_hours.py

from typing import Any, Dict, List
import requests
import json
from datetime import date, timedelta, datetime
import calendar


def format_date_range(start: date, end: date) -> str:
    return f"from={start.isoformat()}&to={end.isoformat()}"


def get_timeframes() -> Dict[str, str]:
    today = date.today()
    yesterday = today - timedelta(days=1)

    def first_day_of_month(d): return d.replace(day=1)
    def last_day_of_month(d): return d.replace(day=calendar.monthrange(d.year, d.month)[1])

    def first_day_of_quarter(d):
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)

    def last_day_of_quarter(d):
        start = first_day_of_quarter(d)
        month = start.month + 2
        return date(d.year, month, calendar.monthrange(d.year, month)[1])

    def first_day_of_year(d): return date(d.year, 1, 1)
    def last_day_of_year(d): return date(d.year, 12, 31)

    last_week_start = today - timedelta(days=today.weekday() + 7)
    last_week_end = last_week_start + timedelta(days=6)

    current_quarter_start = first_day_of_quarter(today)
    last_quarter_end = current_quarter_start - timedelta(days=1)
    last_quarter_start = first_day_of_quarter(last_quarter_end)

    return {
        "today": format_date_range(today, today),
        "yesterday": format_date_range(yesterday, yesterday),
        "week_to_date": format_date_range(today - timedelta(days=today.weekday()), today),
        "last_week": format_date_range(last_week_start, last_week_end),
        "month_to_date": format_date_range(first_day_of_month(today), today),
        "last_month": format_date_range(first_day_of_month(today - timedelta(days=today.day)), last_day_of_month(today - timedelta(days=today.day))),
        "this_quarter": format_date_range(current_quarter_start, today),
        "last_quarter": format_date_range(last_quarter_start, last_quarter_end),
        "year_to_date": format_date_range(first_day_of_year(today), today),
        "last_year": format_date_range(first_day_of_year(today.replace(year=today.year - 1)), last_day_of_year(today.replace(year=today.year - 1))),
    }

def extract_project_summary(events: list) -> dict:
    """
    Aggregates total minutes by project and returns a summary dictionary keyed by project_id.
    
    :param events: List of Timely event JSON objects
    :return: Dict with project_id as keys and aggregated project summary as values
    """
    summary = {}

    for entry in events:
        project = entry.get("project")
        if not project:
            continue

        project_id = project.get("id")
        if not project_id:
            continue

        duration = entry.get("duration", {})
        minutes = duration.get("total_minutes", 0)

        if project_id not in summary:
            summary[project_id] = {
                "project_id": project_id,
                "project_name": project.get("name"),
                "budget": project.get("budget"),
                "budget_type": project.get("budget_type"),
                "budget_progress": project.get("budget_progress"),
                "total_minutes": 0
            }

        summary[project_id]["total_minutes"] += minutes

    return summary

def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    access_token = internal_params["access_token"]
    account_id = internal_params["account_id"]
    user_id = internal_params.get("user_id")  # Optional: for filtering to a specific user

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": "HTTP/1.0",
        "Host": "api.timelyapp.com",
        "Cookie": ""
    }

    timeframes = get_timeframes()
    results = {}

    for label, date_range in timeframes.items():
        url = f"https://api.timelyapp.com/1.1/{account_id}/events?{date_range}"
        if user_id:
            url += f"&user_ids[]={user_id}"

        response = requests.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()

        json_string = json.dumps(data, indent=2)

        print("")
        print("")
        print("")

        print(json_string)

        # Extract project name and hours
        results[label] = [
           extract_project_summary(data)
        ]

    return json.dumps(results, indent=2)
