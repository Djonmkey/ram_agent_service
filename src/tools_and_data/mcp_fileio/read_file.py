# timely/list_future_tasks.py

import os
from typing import Any, Dict

def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    root_path = command_parameters.get("file_path")
    filename = command_parameters.get("filename")
    if not filename:
        filename = command_parameters["model_parameters"]

    filename = filename.replace("'", "").strip()
    file_path_name = filename

    if root_path:
        file_path_name = os.path.join(root_path, filename)
    
    with open(file_path_name, "r", encoding="utf-8") as file:
        contents = file.read()

    return contents
