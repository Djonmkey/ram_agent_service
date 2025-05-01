"""
chat_model_openai.py

This module provides a thread-safe function `ask_chat_model` for interacting with OpenAI's chat models
with conversation memory support.
"""

import os
import sys
import json
import glob

from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List
from threading import Lock

from openai import OpenAI

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_chat_model_system_instructions, get_tools_and_data_mcp_commands_config, get_chat_model_secrets, get_chat_model_config
from ras.work_queue_manager import enqueue_chat_model_response

# Thread lock for logging to avoid race conditions
_log_lock = Lock()


def log_raw_chat(agent_name: str, request_params: Dict[str, Any], response, conversation_id: str = None) -> str:
    """
    Log the raw chat request and response to a JSON file.

    :param agent_name: Name of the agent for organizing logs
    :param request_params: The parameters sent to the GPT API.
    :param response: The response from the GPT API.
    :param conversation_id: Optional conversation ID to group related messages
    :return: The conversation ID used for this log entry
    """
    try:
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        timestamp = now.strftime("%H_%M_%S_%f")[:-3]

        # Generate a conversation ID if not provided
        if not conversation_id:
            conversation_id = f"conv_{now.strftime('%Y%m%d%H%M%S')}_{timestamp}"

        log_path = os.path.join("logs", agent_name, "RawChat", year, month, day)
        os.makedirs(log_path, exist_ok=True)

        log_file = os.path.join(log_path, f"{timestamp}_{conversation_id}_raw_chat.json")

        # Convert response to dict - structure has changed in OpenAI v1.0.0+
        response_dict = {
            "id": response.id,
            "model": response.model,
            "object": response.object,
            "created": now.isoformat(),
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

        # Extract messages that were sent to the API for better conversation tracking
        messages = []
        for msg in request_params.get("messages", []):
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # Add the assistant's response to the messages
        messages.append({
            "role": "assistant",
            "content": response.choices[0].message.content
        })

        log_data = {
            "timestamp": now.isoformat(),
            "conversation_id": conversation_id,
            "request": request_params,
            "response": response_dict,
            "messages": messages
        }

        with _log_lock:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)

        return conversation_id

    except Exception as e:
        print(f"Error logging raw chat: {e}")
        return conversation_id or "error_conversation_id"


def get_conversation_history(agent_name: str, conversation_id: str = None, 
                             max_messages: int = 10, hours_limit: int = 24) -> List[Dict[str, str]]:
    """
    Retrieve conversation history from logs.
    
    :param agent_name: Name of the agent whose logs to search
    :param conversation_id: Optional conversation ID to filter by
    :param max_messages: Maximum number of messages to retrieve
    :param hours_limit: Only retrieve messages from the last X hours
    :return: List of message dictionaries with role and content
    """
    try:
        # Calculate the cutoff time
        cutoff_time = datetime.now() - timedelta(hours=hours_limit)
        
        # Determine the date range to search
        now = datetime.now()
        search_dates = []
        
        # Add today
        search_dates.append((now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")))
        
        # Add yesterday if we're looking back more than 24 hours
        if hours_limit > 24:
            yesterday = now - timedelta(days=1)
            search_dates.append((yesterday.strftime("%Y"), yesterday.strftime("%m"), yesterday.strftime("%d")))
        
        all_log_files = []
        for year, month, day in search_dates:
            log_path = os.path.join("logs", agent_name, "RawChat", year, month, day)
            
            # Skip if directory doesn't exist
            if not os.path.exists(log_path):
                continue
                
            # Get all log files for the specific conversation or all recent conversations
            if conversation_id:
                pattern = os.path.join(log_path, f"*_{conversation_id}_raw_chat.json")
                log_files = glob.glob(pattern)
            else:
                pattern = os.path.join(log_path, f"*_raw_chat.json")
                log_files = glob.glob(pattern)
                
            all_log_files.extend(log_files)
        
        # Extract messages from log files
        messages = []
        
        for log_file in sorted(all_log_files):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_data = json.load(f)
                
                # Skip if older than cutoff time
                log_timestamp = datetime.fromisoformat(log_data.get("timestamp"))
                if log_timestamp < cutoff_time:
                    continue
                
                # Get conversation ID if we don't have one yet
                if not conversation_id and "conversation_id" in log_data:
                    conversation_id = log_data["conversation_id"]
                
                # Extract messages - prioritize stored messages if available
                if "messages" in log_data:
                    # Skip system messages as they'll be added separately
                    file_messages = [msg for msg in log_data["messages"] if msg["role"] != "system"]
                    messages.extend(file_messages)
                else:
                    # Fall back to reconstructing from request/response
                    if log_data.get("request", {}).get("messages"):
                        for msg in log_data["request"]["messages"]:
                            if msg["role"] != "system":
                                messages.append(msg)
                    
                    # Add assistant response
                    if log_data.get("response", {}).get("choices") and len(log_data["response"]["choices"]) > 0:
                        assistant_msg = {
                            "role": "assistant",
                            "content": log_data["response"]["choices"][0]["message"]["content"]
                        }
                        messages.append(assistant_msg)
            except Exception as e:
                print(f"Error processing log file {log_file}: {e}")
        
        # Return only the most recent messages up to max_messages
        return messages[-max_messages:] if len(messages) > max_messages else messages
    
    except Exception as e:
        print(f"Error retrieving conversation history: {e}")
        return []


def ask_chat_model(agent_name: str, prompt: str, meta_data: Dict[str, Any]):
    """
    Submit a prompt to the OpenAI chat model configured for the specified agent,
    with memory of previous conversations.

    :param agent_name: Name of the agent whose configuration should be used.
    :param prompt: The user's input prompt to send to the model.
    :param meta_data: Metadata about the request, may include conversation_id
    :return: The model's response as a string.
    """
    # Extract conversation ID if available in metadata
    conversation_id = meta_data.get("conversation_id", None)
    
    # Get configuration
    chat_model_config = get_chat_model_config(agent_name)
    model = chat_model_config["model"]
    temperature = chat_model_config.get("temperature", 0.7)
    max_tokens = chat_model_config.get("max_tokens", 1000)
    
    # Memory settings - can be moved to agent config if needed
    use_memory = chat_model_config.get("use_memory", True)
    memory_max_messages = chat_model_config.get("memory_max_messages", 10)
    memory_hours_limit = chat_model_config.get("memory_hours_limit", 24)

    chat_model_secrets = get_chat_model_secrets(agent_name)
    api_key = chat_model_secrets["api_key"]

    base_instructions = get_chat_model_system_instructions(agent_name)
    command_data = get_tools_and_data_mcp_commands_config(agent_name)

    command_descriptions = "\n".join(
        f"{cmd['system_text']}: {cmd['system_description']}"
        + (f" (Response format: {cmd['response_format']})" if cmd.get("response_format") else "")
        for cmd in command_data.get("mcp_commands", [])
    )

    if command_data.get("mcp_commands", []):
        first_command = command_data.get("mcp_commands", [])[0]["system_text"]
        system_content = (
            f"{base_instructions.strip()}\n\n"
            f"Available MCP commands:\n{command_descriptions}"
        )

        system_content = system_content + f"\n\nIf additional information is required, respond with a single line for each MCP Command to execute.\n\nExample:\n{first_command}"
        system_content = system_content + "\nDo not use commands that are not explicitly mentioned in the list of Available MCP commands provided. This ensures that any requests made are within the scope of commands commands available to you."

    # Initialize messages with system message
    messages = [{"role": "system", "content": system_content}]
    
    # Retrieve conversation history if memory is enabled
    if use_memory:
        history_messages = get_conversation_history(
            agent_name=agent_name,
            conversation_id=conversation_id,
            max_messages=memory_max_messages,
            hours_limit=memory_hours_limit
        )
        
        # Add history messages to the conversation
        messages.extend(history_messages)
    
    # Add the current user prompt
    messages.append({"role": "user", "content": prompt})

    request_params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    try:
        # Initialize the OpenAI client with the API key
        client = OpenAI(api_key=api_key)
        
        # Use the client to create a chat completion
        response = client.chat.completions.create(**request_params)

        # Log the chat and get conversation ID for future reference
        conversation_id = log_raw_chat(agent_name, request_params, response, conversation_id)
        
        # Store conversation_id in meta_data for future use
        meta_data["conversation_id"] = conversation_id

        # Extract the response text from the first choice
        response_text = response.choices[0].message.content.strip()

        enqueue_chat_model_response(agent_name, response_text, meta_data)

    except Exception as e:
        print(f"Error calling chat model: {e}")
        return "An error occurred while processing the request."