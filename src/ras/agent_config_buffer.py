"""
Module: agent_config_buffer

This module loads and stores all enabled AI agent configuration data in memory from an agent manifest JSON file.
The configuration data includes agent configuration, input triggers, tools and data (if present), and chat model configuration.
All files are loaded as raw strings, and helper accessors are available to parse them into JSON objects on demand.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

# Configure logger
logger = logging.getLogger(__name__)

# Global storage for all agent configurations
global_agent_manifest_entry = {}
global_agent_config = {}

global_tools_and_data_mcp_commands_config = {}
global_tools_and_data_mcp_commands_secrets = {}

global_chat_model_system_instructions = {}
global_chat_model_config = {}
global_chat_model_secrets = {}

global_output_action_config = {}
global_output_action_secrets = {}

global_input_augmentation_config = {}

# Input Augmentation
def set_input_augmentation_config(agent_name: str, input_augmentation_config: Dict[str, Any]) -> None:
    json_string = json.dumps(input_augmentation_config)
    global_input_augmentation_config[agent_name] = json_string


def get_input_augmentation_config(agent_name: str) -> Dict[str, Any]:
    if agent_name in global_input_augmentation_config:
        json_string = global_input_augmentation_config[agent_name]
        return json.loads(json_string)
    else:
        logger.warning(f"No Input Augmentation config found for agent: {agent_name}")
        return {}

# Agent Manifest
def set_agent_manifest_entry(agent_name: str, agent_manifest_entry: Dict[str, Any]) -> None:
    """
    Store agent manifest entry as JSON string
    
    Args:
        agent_name: Name of the agent
        agent_manifest_entry: Dictionary containing agent manifest entry
    """
    json_string = json.dumps(agent_manifest_entry)
    global_agent_manifest_entry[agent_name] = json_string


def get_agent_manifest_entry(agent_name: str) -> Dict[str, Any]:
    """
    Retrieve and parse agent manifest entry
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary containing parsed agent manifest entry
    """
    json_string = global_agent_manifest_entry[agent_name]
    return json.loads(json_string)

# Agent Config
def set_agent_config(agent_name: str, agent_config: Dict[str, Any]) -> None:
    """
    Store agent configuration as JSON string
    
    Args:
        agent_name: Name of the agent
        agent_config: Dictionary containing agent configuration
    """
    agent_config["name"] = agent_name # backup in case the name isn't also set in the file.
    json_string = json.dumps(agent_config)
    global_agent_config[agent_name] = json_string


def get_agent_config(agent_name: str) -> Dict[str, Any]:
    """
    Retrieve and parse agent configuration
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary containing parsed agent configuration
    """
    json_string = global_agent_config[agent_name]
    return json.loads(json_string)

# Tools and Data
## MCP Commands
def set_tools_and_data_mcp_commands_config(agent_name: str, tools_and_data_mcp_commands_config: Dict[str, Any]) -> None:
    """
    Store MCP commands configuration as JSON string
    
    Args:
        agent_name: Name of the agent
        tools_and_data_mcp_commands_config: Dictionary containing MCP commands configuration
    """
    json_string = json.dumps(tools_and_data_mcp_commands_config)
    global_tools_and_data_mcp_commands_config[agent_name] = json_string


def get_tools_and_data_mcp_commands_config(agent_name: str) -> Dict[str, Any]:
    """
    Retrieve and parse MCP commands configuration
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary containing parsed MCP commands configuration
    """
    if agent_name in global_tools_and_data_mcp_commands_config:
        json_string = global_tools_and_data_mcp_commands_config[agent_name]
        return json.loads(json_string)
    else:
        logger.warning(f"No MCP commands config found for agent: {agent_name}")
        return {}

## MCP Secrets
def set_tools_and_data_mcp_commands_secrets(agent_name: str, tools_and_data_mcp_commands_secrets: Dict[str, Any]) -> None:
    """
    Store MCP commands secrets as JSON string
    
    Args:
        agent_name: Name of the agent
        tools_and_data_mcp_commands_secrets: Dictionary containing MCP commands secrets
    """
    json_string = json.dumps(tools_and_data_mcp_commands_secrets)
    global_tools_and_data_mcp_commands_secrets[agent_name] = json_string


def get_tools_and_data_mcp_commands_secrets_by_module(agent_name: str, python_code_module: str) -> Dict[str, Any]:
    """
    Retrieve and parse MCP commands secrets specific to a Python module.
    
    This function extracts the 'common' secrets and combines them with module-specific 'internal_params'.
    
    Args:
        agent_name: Name of the agent
        python_code_module: Python module filename (e.g., 'apple_calendar.py')
        
    Returns:
        Dictionary containing combined common and module-specific secrets
    """
    tools_and_data_mcp_commands_secrets = get_tools_and_data_mcp_commands_secrets(agent_name)
    result = {}
    
    # Always include common elements if they exist
    if 'common' in tools_and_data_mcp_commands_secrets:
        result.update(tools_and_data_mcp_commands_secrets['common'])
    
    # Look for module-specific secrets
    if 'secrets' in tools_and_data_mcp_commands_secrets:
        # Extract filename from path if full path is provided
        module_filename = os.path.basename(python_code_module)
        
        for secret in tools_and_data_mcp_commands_secrets['secrets']:
            # Extract filename from the module path in the secrets configuration
            secret_module = os.path.basename(secret.get('python_code_module', ''))
            
            # Check if either the full path or just the filename matches
            if secret.get('python_code_module') == python_code_module or secret_module == module_filename:
                if 'internal_params' in secret:
                    result.update(secret['internal_params'])
                break
    
    return result

def get_tools_and_data_mcp_commands_secrets(agent_name: str) -> Dict[str, Any]:
    """
    Retrieve and parse MCP commands secrets
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary containing parsed MCP commands secrets
    """
    if agent_name in global_tools_and_data_mcp_commands_secrets:
        json_string = global_tools_and_data_mcp_commands_secrets[agent_name]
        return json.loads(json_string)
    else:
        logger.warning(f"No MCP commands secrets found for agent: {agent_name}")
        return {}

# Chat Model
## Chat Model System Instructions
def set_chat_model_system_instructions(agent_name: str, system_instructions: str) -> None:
    """
    Store chat model system instructions
    
    Args:
        agent_name: Name of the agent
        system_instructions: System instructions as string
    """
    global_chat_model_system_instructions[agent_name] = system_instructions


def get_chat_model_system_instructions(agent_name: str) -> str:
    """
    Retrieve chat model system instructions
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        System instructions as string
    """
    return global_chat_model_system_instructions[agent_name]

## Chat Model Config
def set_chat_model_config(agent_name: str, chat_model_config: Dict[str, Any]) -> None:
    """
    Store chat model configuration as JSON string
    
    Args:
        agent_name: Name of the agent
        chat_model_config: Dictionary containing chat model configuration
    """
    json_string = json.dumps(chat_model_config)
    global_chat_model_config[agent_name] = json_string


def get_chat_model_config(agent_name: str) -> Dict[str, Any]:
    """
    Retrieve and parse chat model configuration
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary containing parsed chat model configuration
    """
    json_string = global_chat_model_config[agent_name]
    return json.loads(json_string)

## Chat Model Secrets
def set_chat_model_secrets(agent_name: str, chat_model_secrets: Dict[str, Any]) -> None:
    """
    Store chat model secrets as JSON string
    
    Args:
        agent_name: Name of the agent
        chat_model_secrets: Dictionary containing chat model secrets
    """
    json_string = json.dumps(chat_model_secrets)
    global_chat_model_secrets[agent_name] = json_string


def get_chat_model_secrets(agent_name: str) -> Dict[str, Any]:
    """
    Retrieve and parse chat model secrets
    
    Args:
        agent_name: Name of the agent
        
    Returns:
        Dictionary containing parsed chat model secrets
    """
    json_string = global_chat_model_secrets[agent_name]
    return json.loads(json_string)

def set_output_action_config(agent_name: str, output_actions_config: Dict[str, Any]) -> None:
    """
    Store chat model secrets as JSON string
    
    Args:
        agent_name: Name of the agent
        chat_model_secrets: Dictionary containing chat model secrets
    """
    json_string = json.dumps(output_actions_config)
    global_output_action_config[agent_name] = json_string


def get_output_action_config(agent_name: str) -> Dict[str, Any]:
    json_string = global_output_action_config[agent_name]
    return json.loads(json_string)


def set_output_action_secrets(agent_name: str, output_actions_config: Dict[str, Any]) -> None:
    """
    Store chat model secrets as JSON string
    
    Args:
        agent_name: Name of the agent
        chat_model_secrets: Dictionary containing chat model secrets
    """
    json_string = json.dumps(output_actions_config)
    global_output_action_secrets[agent_name] = json_string


def get_output_action_secrets(agent_name: str) -> Dict[str, Any]:
    json_string = global_output_action_secrets[agent_name]
    return json.loads(json_string)

def load_json_file(file_path: str) -> Dict[str, Any]:
    """
    Load and parse JSON file
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        Dictionary containing parsed JSON data
    
    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    try:
        file_path = Path(file_path)
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {file_path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading file {file_path}: {str(e)}")
        raise


def load_text_file(file_path: str) -> str:
    """
    Load text file content
    
    Args:
        file_path: Path to the text file
        
    Returns:
        String containing file content
    
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    try:
        file_path = Path(file_path)
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading text file {file_path}: {str(e)}")
        raise


def resolve_path(base_path: Path, file_path: str) -> str:
    """
    Resolve file path relative to base path if it's not absolute
    
    Args:
        base_path: Base directory path
        file_path: File path (absolute or relative)
        
    Returns:
        Resolved Path object
    """
    path = Path(file_path)

    if path.exists():
        return str(path)

    if path.is_absolute():
        return str(path)
    
    return str(base_path / path)


def load_agent_manifest(manifest_path: str) -> None:
    """
    Loads configuration data for all enabled agents from the agent manifest.

    Args:
        manifest_path: Path to the agent manifest JSON file.
    """
    try:
        logger.info(f"Loading agent manifest from: {manifest_path}")
        manifest_path = Path(manifest_path)
        base_path = manifest_path.parent

        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        enabled_count = 0
        for agent in manifest.get("agents", []):
            if not agent.get("enabled", False):
                continue

            enabled_count += 1
            agent_name = agent["name"]
            logger.info(f"Loading configuration for enabled agent: {agent_name}")

            # Store the Agent Manifest Entry
            set_agent_manifest_entry(agent_name, agent)

            # Load and store the agent configuration
            agent_config_path = resolve_path(base_path, agent["agent_config_file"])
            agent_config = load_json_file(agent_config_path)
            set_agent_config(agent_name, agent_config)

            # Optional: tools_and_data
            tools_and_data = agent_config.get("tools_and_data", {})
            if tools_and_data:
                if "mcp_commands_config_file" in tools_and_data:
                    config_path = resolve_path(base_path, tools_and_data["mcp_commands_config_file"])
                    mcp_commands_config = load_json_file(str(config_path))
                    set_tools_and_data_mcp_commands_config(agent_name, mcp_commands_config)
                    logger.info(f"Loaded MCP commands config for {agent_name}")

                if "mcp_commands_secrets_file" in tools_and_data:
                    secrets_path = resolve_path(base_path, tools_and_data["mcp_commands_secrets_file"])
                    mcp_commands_secrets = load_json_file(str(secrets_path))
                    set_tools_and_data_mcp_commands_secrets(agent_name, mcp_commands_secrets)
                    logger.info(f"Loaded MCP commands secrets for {agent_name}")

            # Required: chat_model
            chat_model = agent_config.get("chat_model", {})
            if chat_model:
                # Load system instructions
                if "chat_system_instructions_file" in chat_model:
                    instructions_path = resolve_path(base_path, chat_model["chat_system_instructions_file"])
                    system_instructions = load_text_file(str(instructions_path))
                    set_chat_model_system_instructions(agent_name, system_instructions)
                    logger.info(f"Loaded chat system instructions for {agent_name}")
                
                # Load chat model config
                if "chat_model_config_file" in chat_model:
                    config_path = resolve_path(base_path, chat_model["chat_model_config_file"])
                    chat_config = load_json_file(str(config_path))
                    set_chat_model_config(agent_name, chat_config)
                    logger.info(f"Loaded chat model config for {agent_name}")
                
                # Load chat model secrets
                if "chat_model_secrets_file" in chat_model:
                    secrets_path = resolve_path(base_path, chat_model["chat_model_secrets_file"])
                    chat_secrets = load_json_file(str(secrets_path))
                    set_chat_model_secrets(agent_name, chat_secrets)
                    logger.info(f"Loaded chat model secrets for {agent_name}")

            # Optional: output actions
            output_action = agent_config.get("output_action", {})
            if output_action:
                # Load chat model config
                if "output_action_config_file" in output_action:
                    config_path = resolve_path(base_path, output_action["output_action_config_file"])
                    output_action_config_config = load_json_file(str(config_path))
                    set_output_action_config(agent_name, output_action_config_config)
                    logger.info(f"Loaded output action model config for {agent_name}")
                
                # Load chat model secrets
                if "output_action_secrets_file" in output_action:
                    secrets_path = resolve_path(base_path, output_action["output_action_secrets_file"])
                    output_action_secrets = load_json_file(str(secrets_path))
                    set_output_action_secrets(agent_name, output_action_secrets)
                    logger.info(f"Loaded output action model secrets for {agent_name}")
        
        logger.info(f"Finished loading configuration for {enabled_count} enabled agent(s)")
    
    except Exception as e:
        logger.error(f"Error loading agent manifest: {str(e)}")
        raise

def get_agent_name_list() -> List[str]:
    """
    Retrieve all agent names (keys) from the global agent manifest.

    :return: A list of agent names.
    :rtype: List[str]
    """
    return list(global_agent_manifest_entry.keys())
