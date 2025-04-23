"""
chat_model_openai.py

This module provides a thread-safe function `ask_chat_model` for interacting with OpenAI's chat models.
"""

import os
import sys
import json

from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from threading import Lock

from openai import OpenAI

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_chat_model_system_instructions, get_tools_and_data_mcp_commands_config, get_chat_model_secrets, get_chat_model_config
from ras.work_queue_manager import enqueue_chat_model_response

# Thread lock for logging to avoid race conditions
_log_lock = Lock()


def log_raw_chat(request_params: Dict[str, Any], response) -> None:
    """
    Log the raw chat request and response to a JSON file.

    :param request_params: The parameters sent to the GPT API.
    :param response: The response from the GPT API.
    """
    try:
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        timestamp = now.strftime("%H_%M_%S_%f")[:-3]

        log_path = os.path.join("logs", "RawChat", year, month, day)
        os.makedirs(log_path, exist_ok=True)

        log_file = os.path.join(log_path, f"{timestamp}_raw_chat.json")

        # Convert response to dict - structure has changed in OpenAI v1.0.0+
        response_dict = {
            "id": response.id,
            "model": response.model,
            "object": response.object,
            "created": int(response.created.timestamp()),
            "choices": [{
                "index": i,
                "message": {
                    "role": choice.message.role,
                    "content": choice.message.content
                },
                "finish_reason": choice.finish_reason
            } for i, choice in enumerate(response.choices)],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }

        log_data = {
            "timestamp": now.isoformat(),
            "request": request_params,
            "response": response_dict
        }

        with _log_lock:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)

    except Exception as e:
        print(f"Error logging raw chat: {e}")


def ask_chat_model(agent_name: str, prompt: str, meta_data: Dict[str, Any]):
    """
    Submit a prompt to the OpenAI chat model configured for the specified agent.

    :param agent_name: Name of the agent whose configuration should be used.
    :param prompt: The user's input prompt to send to the model.
    :return: The model's response as a string.
    """
    chat_model_config = get_chat_model_config(agent_name)
    model = chat_model_config["model"]
    temperature = chat_model_config.get("temperature", 0.7)
    max_tokens = chat_model_config.get("max_tokens", 1000)

    chat_model_secrets = get_chat_model_secrets(agent_name)
    api_key = chat_model_secrets["api_key"]

    base_instructions = get_chat_model_system_instructions(agent_name)
    command_data = get_tools_and_data_mcp_commands_config(agent_name)

    command_descriptions = "\n".join(
        f"{cmd['system_text']}: {cmd['system_description']}"
        + (f" (Response format: {cmd['response_format']})" if cmd.get("response_format") else "")
        for cmd in command_data.get("mcp_commands", [])
    )

    system_content = (
        f"{base_instructions.strip()}\n\n"
        f"Available MCP commands:\n{command_descriptions}"
    )

    request_params = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        # Initialize the OpenAI client with the API key
        client = OpenAI(api_key=api_key)
        
        # Use the client to create a chat completion
        response = client.chat.completions.create(**request_params)

        log_raw_chat(request_params, response)

        # Extract the response text from the first choice
        response_text = response.choices[0].message.content.strip()

        enqueue_chat_model_response(agent_name, response_text, meta_data)

    except Exception as e:
        print(f"Error calling chat model: {e}")
        return "An error occurred while processing the request."
