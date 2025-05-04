# Ensure src is in path for sibling imports
import sys
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> output_actions -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_output_action_secrets, get_output_action_config

def write_response_to_file(output_file_path: str, chat_model_response: str) -> None:
    """
    Writes the chat model response to a file, ensuring the output directory exists.

    :param output_file_path: Full path to the output file.
    :param chat_model_response: The response text to write to the file.
    """
    path = Path(output_file_path)
    path.parent.mkdir(parents=True, exist_ok=True)  # Ensure the directory exists

    with path.open('w', encoding='utf-8') as file:
        file.write(chat_model_response + "\n")

def process_output_action(agent_name: str, chat_model_response: str, meta_data: dict) -> None:
    output_action_config = get_output_action_config(agent_name)
    output_file_path = output_action_config.get("output_file_path", "")
    
    if not output_file_path:
        raise ValueError("Output file path is not set in the configuration.")

    # write the response to the file
    write_response_to_file(output_file_path, chat_model_response)

    