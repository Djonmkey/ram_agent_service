import os
from typing import Dict, Any

def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    root_path = command_parameters.get("file_path")
    
    # Assume format <file_path> """<problem_statement>""""
    model_parameters = command_parameters["model_parameters"]

    params = model_parameters.split('"""')

    filename = params[0]
    contents = params[1]
    
    filename = filename.replace("'", "").strip()
    contents = contents.strip()

    file_path_name = os.path.join(root_path, filename)
    
    # Ensure the directory exists
    directory = os.path.dirname(file_path_name)
    os.makedirs(directory, exist_ok=True)

    with open(file_path_name, "w", encoding="utf-8") as file:
        file.write(contents)
    
    return f"Successfully wrote to file: {file_path_name}"