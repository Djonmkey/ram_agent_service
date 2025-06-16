# timely/list_future_tasks.py

from typing import Any, Dict

def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    filename = command_parameters.get("filename")

    with open(filename, "r", encoding="utf-8") as file:
        contents = file.read()

    return contents
