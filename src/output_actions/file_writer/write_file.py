# Ensure src is in path for sibling imports
import sys
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> output_actions -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_output_action_secrets, get_output_action_config

def process_output_action(agent_name: str, chat_model_response: str, meta_data: dict) -> None:
    output_file_path = get_output_action_config(agent_name, "output_file_path")
    if not output_file_path:
        raise ValueError("Output file path is not set in the configuration.")

    #wriote the response to the file
    with open(output_file_path, 'w') as file:
        file.write(chat_model_response + "\n")

    