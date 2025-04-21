from pathlib import Path
from typing import Any, Dict


def read_markdown_files_as_string(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    Reads all Markdown (or specified) files from a directory and concatenates them into a single string.
    Each file's content is separated by a Markdown comment indicating the file name.

    :param command_parameters: Dictionary containing:
        - "file_path": Path to the directory containing Markdown files.
        - "extension_list": List of file extensions to include (default is ['.md']).
    :param internal_params: Dictionary of internal parameters (unused here).
    :return: A single string with concatenated contents of all Markdown files.
    """
    file_path = command_parameters.get("file_path")
    extension_list = command_parameters.get("extension_list", ['.md'])

    if not file_path:
        raise ValueError("Missing required 'file_path' in command_parameters.")

    directory = Path(file_path)
    if not directory.is_dir():
        raise NotADirectoryError(f"'{file_path}' is not a valid directory.")

    combined_content = ""

    for file in sorted(directory.iterdir()):
        if file.suffix in extension_list and file.is_file():
            try:
                with file.open("r", encoding="utf-8") as f:
                    file_content = f.read()
                    combined_content += f"\n<!-- Begin: {file.name} -->\n{file_content}\n<!-- End: {file.name} -->\n"
            except OSError as e:
                raise RuntimeError(f"Error reading '{file}': {e}")

    return combined_content.strip()
