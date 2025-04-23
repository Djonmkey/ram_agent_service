import os
import sys 

from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_tools_and_data_mcp_commands_config, get_tools_and_data_mcp_commands_secrets

def escape_system_text_with_command_escape_text(response: str):
    """
    Strips any trailing slash-prefixed commands (e.g., /list_my_goals) from a response string.

    If the entire string only contains commands or whitespace, returns an empty string.

    :param response: The response text potentially containing trailing commands.
    :return: The cleaned response string with commands removed, or an empty string if only commands were present.
    """
    # Strip leading/trailing whitespace for consistent behavior
    response = response.strip()

    # TODO: Replace system_text found with command_escape_text, which defaults to '(in progress…)'
    
    return response.strip()

def contains_mcp_command(agent_name: str, message_text: str) -> bool:
    """Checks if the message text contains any known MCP command or alias."""
    command_data = get_tools_and_data_mcp_commands_config(agent_name)   
    if not command_data:
        return False

    message_text_lower = message_text.lower().strip() # Case-insensitive check
    try:
        for cmd in command_data.get("mcp_commands", []):
            if cmd.get("enabled") is False:
                continue

            system_text = cmd.get("system_text")
            if system_text and system_text.lower() in message_text_lower:
                print(f"Found command '{system_text}' in message.")
                return True
            for alias in cmd.get("aliases", []):
                if alias.lower() in message_text_lower:
                    print(f"Found command alias '{alias}' in message.")
                    return True
        return False
    except Exception:
        print("Error during command checking")
        return False
    
def run_mcp_command(agent_name, command_text: str) -> str:
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
            print(f"Unknown MCP command requested: {command_text}")
            return f"Unknown MCP command: {command_text}"

        module_path_str = matched_cmd.get("python_code_module")
        handler_name = matched_cmd.get("handler_function", "execute_command")

        if not module_path_str:
                print(f"Command '{command_text}' is missing 'python_code_module' in config.")
                return f"Configuration error for command: {command_text}"

        if not os.path.exists(module_path_str):
            print(f"MCP module file not found: {module_path_str}")
            return f"Error: Module file not found for command {command_text}"

        # Load secrets for the module from MCP secrets file
        common_params = secrets_data.get("common", {})
        secret_entry = next(
            (s for s in secrets_data.get("secrets", [])
                if s.get("python_code_module") == module_path_str),
            None
        )
        if not secret_entry:
            print(f"⚠️ Missing secrets entry for module: {module_path_str} in {self.mcp_secrets_path}")
            internal_params = common_params # Use only common if specific are missing
        else:
            # Merge common with specific, specific taking precedence
            internal_params = {**common_params, **secret_entry.get("internal_params", {})}

        # Dynamically load and execute the module's handler function
        spec = spec_from_file_location(module_path_str.stem, module_path_str)
        if not spec or not spec.loader:
                print(f"Could not create module spec for {module_path_str}")
                return f"Error loading module for command {command_text}"

        cmd_mod = module_from_spec(spec)
        spec.loader.exec_module(cmd_mod)

        if hasattr(cmd_mod, handler_name):
            handler = getattr(cmd_mod, handler_name)
            print(f"🚀 Running MCP Command: {module_path_str}.{handler_name}")
            # Pass MCP internal params. Trigger secrets (self.trigger_secrets) are available
            # within the trigger instance if needed by the trigger logic itself, but not
            # typically passed directly to MCP command handlers unless designed that way.
            result = handler(matched_cmd["command_parameters"], internal_params)
            print(f"✅ MCP Command '{command_text}' result received.")
            return str(result) # Ensure result is string
        else:
            print(f"Handler function '{handler_name}' not found in module {module_path_str}")
            return f"Error: Handler not found for command {command_text}"

    except Exception as e:
        print(f"Error executing MCP command '{command_text}': {e}", exc_info=True)
        return f"Error executing command {command_text}: {e}"

def process_mcp_commands(agent_name, gpt_response: str, initial_prompt: str) -> str:
        """
        Finds MCP commands in the GPT response, executes them, and formats a new prompt.

        Args:
            gpt_response: The raw response from the GPT model.
            initial_query: The original user query that started the interaction.

        Returns:
            A new prompt string containing the command results, instructing the AI
            to use them to answer the initial query.
        """
        
        command_data = get_tools_and_data_mcp_commands_config(agent_name)

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
        temp_response = gpt_response # Work on a copy
        for command in all_commands:
            # Use case-insensitive check but execute with original case
            if command.lower() in temp_response.lower():
                found_commands = True
                
                command_result = run_mcp_command(command)
                executed_results.append(f"--- Command: {command} ---\nResult:\n{command_result}\n--- End {command} ---")
                # Optional: Remove the command from temp_response to avoid re-matching parts?
                # This is complex if commands overlap. Simpler to just list results.

        if not found_commands:
             # Should not happen if called after contains_command, but handle defensively
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
