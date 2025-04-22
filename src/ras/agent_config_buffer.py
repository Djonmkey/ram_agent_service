"""
Module: agent_config_buffer

This module loads and stores all enabled AI agent configuration data in memory from an agent manifest JSON file.
The configuration data includes agent configuration, input triggers, tools and data (if present), and chat model configuration.
All files are loaded as raw strings, and helper accessors are available to parse them into JSON objects on demand.
"""

from pathlib import Path
from typing import Dict, Optional, Any
import json

# At the module level
global_agent_manifest_entry = {}
global_agent_config = {}
global_tools_and_data_mcp_commands_config = {}
global_tools_and_data_mcp_commands_secrets = {}
global_chat_model_system_instructions = {}
global_chat_model_config = {}
global_chat_model_secrets = {}


# Agent Manifest
def set_agent_manifest_entry(agent_name, agent_manifest_entry: Dict[str, Any]):
    json_string = json.dumps(agent_manifest_entry)

    global_agent_manifest_entry[agent_name] = json_string


def get_agent_manifest_entry(agent_name):
    json_string = global_agent_manifest_entry(agent_name)

    return json.loads(json_string)

# Agent Config
def set_agent_agent_config(agent_name, agent_config: Dict[str, Any]):
    json_string = json.dumps(agent_config)

    global_agent_config[agent_name] = json_string

def get_agent_agent_config(agent_name):
    json_string = global_agent_config(agent_name)

    return json.loads(json_string)

# Tools and Data
## MCP Commands
def set_tools_and_data_mcp_commands_config(agent_name, tools_and_data_mcp_commands_config: Dict[str, Any]):
    json_string = json.dumps(tools_and_data_mcp_commands_config)

    global_tools_and_data_mcp_commands_config[agent_name] = json_string

def get_tools_and_data_mcp_commands_config(agent_name):
    json_string = global_tools_and_data_mcp_commands_config(agent_name)

    return json.loads(json_string)

## MCP Secrets
def set_tools_and_data_mcp_commands_secrets(agent_name, tools_and_data_mcp_commands_secrets: Dict[str, Any]):
    json_string = json.dumps(tools_and_data_mcp_commands_secrets)

    global_tools_and_data_mcp_commands_secrets[agent_name] = json_string

def get_tools_and_data_mcp_commands_secrets(agent_name):
    json_string = global_tools_and_data_mcp_commands_secrets(agent_name)

    return json.loads(json_string)

# Chat Model
## Chat Model System Instructions
def set_chat_model_system_instructions(agent_name, system_instructions: str):
    global_chat_model_system_instructions[agent_name] = system_instructions

def get_chat_model_system_instructions(agent_name):
    system_instructions = global_chat_model_system_instructions(agent_name)
    return system_instructions

## Chat Model Config
def set_chat_model_config(agent_name, chat_model_config: Dict[str, Any]):
    json_string = json.dumps(chat_model_config)

    global_chat_model_config[agent_name] = json_string

def get_chat_model_config(agent_name):
    json_string = global_chat_model_config(agent_name)

    return json.loads(json_string)

## Chat Model Secrets
def set_chat_model_secrets(agent_name, chat_model_secrets: Dict[str, Any]):
    json_string = json.dumps(chat_model_secrets)

    global_chat_model_secrets[agent_name] = json_string

def get_chat_model_secrets(agent_name):
    json_string = global_chat_model_secrets(agent_name)

    return json.loads(json_string)

def load_json_file(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

def load_agent_manifest(manifest_path: str) -> None:
    """
    Loads configuration data for all enabled agents from the agent manifest.

    :param manifest_path: Path to the agent manifest JSON file.
    """
    manifest_path = Path(manifest_path)
    base_path = manifest_path.parent

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    for agent in manifest.get("agents", []):
        if not agent.get("enabled", False):
            continue

        agent_name = agent["name"]

        # Store the Agent Manifest Data
        set_agent_manifest_entry(agent_name, agent)

        # Now load the agent_config_file
        agent_config_file = agent["agent_config_file"]
        agent_config = load_json_file(agent_config_file)

        # Store the Agent Config Data
        set_agent_agent_config(agent_name, agent_config)

        # Optional: tools_and_data
        tools_and_data = agent_config.get("tools_and_data")
        if tools_and_data:
            if "mcp_commands_config_file" in tools_and_data:
                mcp_commands_config_file = tools_and_data["mcp_commands_config_file"]
                mcp_commands_config = load_json_file(mcp_commands_config_file)
                set_tools_and_data_mcp_commands_config(agent_name, mcp_commands_config)

            if "mcp_commands_secrets_file" in tools_and_data:
                mcp_commands_secrets_file = tools_and_data["mcp_commands_secrets_file"]
                mcp_commands_secrets = load_json_file(mcp_commands_secrets_file)
                set_tools_and_data_mcp_commands_secrets(agent_name, mcp_commands_secrets)

        # Required: chat_model
        chat_model = agent_config["chat_model"]
        
        
        self._load_file(agent_name, "chat_system_instructions_file", base_path / chat_model["chat_system_instructions_file"])
        self._load_file(agent_name, "chat_model_config_file", base_path / chat_model["chat_model_config_file"])
        self._load_file(agent_name, "chat_model_secrets_file", base_path / chat_model["chat_model_secrets_file"])
