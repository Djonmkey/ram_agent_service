import json
from pathlib import Path
from typing import Any, Dict, List


def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    Reads all JSON files from a directory and combines their contents into a single JSON array string.

    :param command_parameters: Dictionary containing:
        - "file_path": Path to the directory containing JSON files.
        - "extension_list": List of file extensions to include (default is ['.json']).
    :param internal_params: Dictionary of internal parameters (unused here).
    :return: A JSON array string combining all parsed file contents.
    """
    file_path = command_parameters.get("file_path")
    extension_list = command_parameters.get("extension_list", ['.json'])

    if not file_path:
        raise ValueError("Missing required 'file_path' in command_parameters.")

    directory = Path(file_path)
    if not directory.is_dir():
        raise NotADirectoryError(f"'{file_path}' is not a valid directory.")

    combined_items: List[Any] = []

    for file in directory.iterdir():
        if file.suffix in extension_list and file.is_file():
            try:
                with file.open("r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        combined_items.extend(content)
                    else:
                        combined_items.append(content)
            except (json.JSONDecodeError, OSError) as e:
                raise RuntimeError(f"Error reading or parsing '{file}': {e}")

    json_array_text = json.dumps(combined_items, indent=2)
    return json_array_text