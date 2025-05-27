import os
import sys
import logging
from pathlib import Path
from typing import Optional
from importlib.util import spec_from_file_location, module_from_spec

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_tools_and_data_mcp_commands_config, get_tools_and_data_mcp_commands_secrets

def escape_system_text_with_command_escape_text(agent_name, response: str, command_escape_text: str = "(in progress...)"):
    """
    Replaces any MCP command system text found in the response with a command escape text.
    
    If the entire string only contains commands or whitespace, returns the escape text.

    Args:
        response: The response text potentially containing MCP commands.
        command_escape_text: Text to replace commands with, defaults to "(in progress...)".
    
    Returns:
        The response with commands replaced by the escape text.
    """
    # Strip leading/trailing whitespace for consistent behavior
    response = response.strip()
    
    command_data = get_tools_and_data_mcp_commands_config(agent_name)
    
    if not command_data:
        logger.warning(f"No command data found for agent {agent_name}")
        return command_escape_text

    try:
        # Check each command for aliases in the response
        for cmd in command_data.get("mcp_commands", []):
            if cmd.get("enabled") is False:
                continue
                
            aliases = cmd.get("aliases", [])
            for alias in aliases:
                if alias in response:
                    # Use the command's command_escape_text if available, otherwise use default
                    escape_text = cmd.get("command_escape_text", command_escape_text)
                    return escape_text
                    
        return response.strip()
        
    except Exception as e:
        logger.error(f"Error during command escape processing: {e}", exc_info=True)
        return response.strip()

def contains_mcp_command(agent_name: str, message_text: str) -> bool:
    """
    Checks if the message text contains any known MCP command or alias.
    
    Args:
        agent_name: The name of the agent to check commands for.
        message_text: The message text to check for commands.
        
    Returns:
        True if a command is found, False otherwise.
    """
    command_data = get_tools_and_data_mcp_commands_config(agent_name)   
    if not command_data:
        logger.warning(f"No command data found for agent {agent_name}")
        return False

    message_text_lower = message_text.lower().strip() # Case-insensitive check
    try:
        for cmd in command_data.get("mcp_commands", []):
            if cmd.get("enabled") is False:
                continue

            system_text = cmd.get("system_text")
            if system_text and system_text.lower() in message_text_lower:
                logger.info(f"Found command '{system_text}' in message.")
                return True
            for alias in cmd.get("aliases", []):
                if alias.lower() in message_text_lower:
                    logger.info(f"Found command alias '{alias}' in message.")
                    return True
        return False
    except Exception as e:
        logger.error(f"Error during command checking: {e}", exc_info=True)
        return False
    
def extract_model_parameters(agent_name, command_text, model_response):
    command_only = extract_command(agent_name, command_text).strip()

    if model_response.startswith(command_only):
        return model_response[len(command_only):].strip()
    elif command_only in model_response:
        return model_response.split(command_only, 1)[1].strip()

    return None

def run_mcp_command(agent_name: str, command_text: str, model_response: str) -> str:
    """
    Executes an MCP command with the given text for the specified agent.
    
    Args:
        agent_name: The name of the agent to run the command for. Example: calendar_concierge_discord
        command_text: The command text to execute. Example: /create_event <json>
        model_response. Example: /create_event {"summary":"Test Stand-up","description":"Temp","dt_start":"2025-05-21T07:00:00-04:00","duration":"PT15M","horizon":"week","source_agent":"manual_test"}
        
    Returns:
        The result of the command execution as a string.
    """
    command_data = get_tools_and_data_mcp_commands_config(agent_name)
    secrets_data = get_tools_and_data_mcp_commands_secrets(agent_name)

    try:
        # Find the command definition matching the exact system_text
        matched_cmd = next(
            (cmd for cmd in command_data.get("mcp_commands", [])
                if cmd.get("system_text") == command_text),
            None
        )
        if not matched_cmd:
            logger.warning(f"Unknown MCP command requested: {command_text}")
            return f"Unknown MCP command: {command_text}"

        module_path_str = matched_cmd.get("python_code_module")
        handler_name = matched_cmd.get("handler_function", "execute_command")

        if not module_path_str:
            logger.error(f"Command '{command_text}' is missing 'python_code_module' in config.")
            return f"Configuration error for command: {command_text}"

        # Convert string path to Path object
        module_path = Path(module_path_str)
        
        if not module_path.exists():
            logger.error(f"MCP module file not found: {module_path}")
            return f"Error: Module file not found for command {command_text}"

        # Load secrets for the module from MCP secrets file
        common_params = secrets_data.get("common", {})
        secret_entry = next(
            (s for s in secrets_data.get("secrets", [])
                if s.get("python_code_module") == module_path_str),
            None
        )
        if not secret_entry:
            logger.warning(f"Missing secrets entry for module: {module_path_str}")
            internal_params = common_params # Use only common if specific are missing
        else:
            # Merge common with specific, specific taking precedence
            internal_params = {**common_params, **secret_entry.get("internal_params", {})}

        # Dynamically load and execute the module's handler function
        spec = spec_from_file_location(module_path.stem, module_path)
        if not spec or not spec.loader:
            logger.error(f"Could not create module spec for {module_path}")
            return f"Error loading module for command {command_text}"

        cmd_mod = module_from_spec(spec)
        spec.loader.exec_module(cmd_mod)

        # extract parameters from the model response
        model_parameters = extract_model_parameters(agent_name, command_text, model_response)

        if model_parameters:
            matched_cmd["command_parameters"]["model_parameters"] = model_parameters

        matched_cmd["command_parameters"]["agent_name"] = agent_name
        
        if hasattr(cmd_mod, handler_name):
            handler = getattr(cmd_mod, handler_name)
            logger.info(f"Running MCP Command: {module_path}.{handler_name}")
            result = handler(matched_cmd["command_parameters"], internal_params)
            logger.info(f"MCP Command '{command_text}' result received.")
            return str(result) # Ensure result is string
        else:
            logger.error(f"Handler function '{handler_name}' not found in module {module_path}")
            return f"Error: Handler not found for command {command_text}"

    except Exception as e:
        logger.error(f"Error executing MCP command '{command_text}': {e}", exc_info=True)
        return f"Error executing command {command_text}: {e}"

def extract_command(agent_name, input_string: str) -> Optional[str]:
    """
    Extract the command from a command string.

    A command is defined as the first word in the input, usually starting with a '/'.
    If there are no spaces, the entire input is returned. Leading/trailing whitespace is trimmed.

    :param input_string: The full command string including parameters.
    :type input_string: str
    :return: The extracted command portion of the string.
    :rtype: Optional[str]
    """

    command_data = get_tools_and_data_mcp_commands_config(agent_name)

    if "mcp_commands" in command_data:
        for command in command_data["mcp_commands"]:
            if "/" + command["command"] in input_string:
                return "/" + command["command"]

    stripped = input_string.strip()
    if not stripped:
        return None

    return stripped.split(" ", 1)[0]

def process_mcp_commands(agent_name: str, gpt_response: str, initial_prompt: str) -> str:
    """
    Finds MCP commands in the GPT response, executes them, and formats a new prompt.

    Args:
        agent_name: The name of the agent to process commands for.
        gpt_response: The raw response from the GPT model.
        initial_prompt: The original user query that started the interaction.

    Returns:
        A new prompt string containing the command results, instructing the AI
        to use them to answer the initial query.
    """
    
    command_data = get_tools_and_data_mcp_commands_config(agent_name)
    if not command_data:
        logger.warning(f"No command data found for agent {agent_name}")
        return gpt_response

    # Get all defined command system_texts where the command is enabled
    all_commands = [
        cmd["system_text"]
        for cmd in command_data.get("mcp_commands", [])
        if cmd.get("enabled") and "system_text" in cmd
    ]

    # Sort by length descending to match longer commands first
    all_commands.sort(key=len, reverse=True)

    executed_results = []
    found_commands = False

    # Iterate through commands and execute if found in the response
    command_only = extract_command(agent_name, gpt_response) # Work on a copy
    for command in all_commands:
        # Use case-insensitive check but execute with original case
        # Note: The space is added to ensure a full command match.
        if command_only.lower() + " " in command.lower() + " ":
            found_commands = True
            
            command_result = run_mcp_command(agent_name, command, gpt_response)
            executed_results.append(f"--- Command: {command} ---\nResult:\n{command_result}\n--- End {command} ---")
            # Optional: Remove the command from temp_response to avoid re-matching parts?
            # This is complex if commands overlap. Simpler to just list results.

    if not found_commands:
         # Should not happen if called after contains_command, but handle defensively
         logger.info("No commands found in response despite previous check")
         return gpt_response # Return original if no commands were actually found/executed

    # Format the new prompt for the AI
    results_text = "\n\n".join(executed_results)
    new_prompt = (
        f"In response to my original request \"{initial_prompt}\", you asked to run one or more tools/commands. "
        f"I have executed them and here are the results:\n\n"
        f"{results_text}\n\n"
        f"Please use these results to provide the final answer to my original request: \"{initial_prompt}\""
    )

    return new_prompt
