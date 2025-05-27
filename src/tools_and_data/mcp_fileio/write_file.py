# mcp_fileio/write_file.py

from typing import Any, Dict

def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    root_path = internal_params.get("root_path")
    filename = command_parameters.get("filename")
    contents = command_parameters.get("contents", "")

    file_path_name = f"{root_path}/{filename}"
    
    with open(file_path_name, "w", encoding="utf-8") as file:
        file.write(contents)
    
    return f"Successfully wrote to file: {file_path_name}"
