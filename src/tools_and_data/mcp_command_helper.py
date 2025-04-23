import sys 

from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_tools_and_data_mcp_commands_config

def escape_system_text_with_command_escape_text(self, response: str):
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
    
def process_mcp_commands(self, gpt_response: str, initial_query: str) -> str:
        """
        Finds MCP commands in the GPT response, executes them, and formats a new prompt.

        Args:
            gpt_response: The raw response from the GPT model.
            initial_query: The original user query that started the interaction.

        Returns:
            A new prompt string containing the command results, instructing the AI
            to use them to answer the initial query.
        """
        self.logger.debug("Processing potential MCP commands in GPT response.")
        command_data = self._load_json_safely(self.mcp_commands_path)
        if not command_data:
            return "Error: Could not load MCP command configuration for processing."

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
                self.logger.info(f"Found command '{command}' in response, executing.")
                command_result = self._run_mcp_command(command)
                executed_results.append(f"--- Command: {command} ---\nResult:\n{command_result}\n--- End {command} ---")
                # Optional: Remove the command from temp_response to avoid re-matching parts?
                # This is complex if commands overlap. Simpler to just list results.

        if not found_commands:
             self.logger.debug("No MCP commands found in the response.")
             # Should not happen if called after contains_command, but handle defensively
             return gpt_response # Return original if no commands were actually found/executed

        # Format the new prompt for the AI
        results_text = "\n\n".join(executed_results)
        new_prompt = (
            f"In response to my original request \"{initial_query}\", you asked to run one or more tools/commands. "
            f"I have executed them and here are the results:\n\n"
            f"{results_text}\n\n"
            f"Please use these results to provide the final answer to my original request: \"{initial_query}\""
        )
        self.logger.debug("Formatted new prompt with MCP command results.")
        return new_prompt
