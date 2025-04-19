import json
from abc import ABC, abstractmethod
import sys
import os
from constants import MCP_COMMANDS_PATH, MCP_SECRETS_PATH

# Add parent directory to path to import from main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpt_thread import get_gpt_handler

# Global Variable for initial prompt.  Used to recover initial prompt when MCP calls are made
INITIAL_PROMPT = ""

class InputTrigger(ABC):
    """
    Abstract base class for event listeners.
    Any event source (Discord, Slack, Email, etc.) should implement this interface.
    """
    
    @abstractmethod
    async def initialize(self):
        """
        Initialize the event listener.
        This method should set up any necessary connections or configurations.
        """
        pass
    
    @abstractmethod
    async def start(self):
        """
        Start listening for events.
        This method should begin the event listening process.
        """
        pass
    
    @abstractmethod
    async def stop(self):
        """
        Stop listening for events.
        This method should clean up any resources and stop the event listening process.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the name of the event listener.
        
        Returns:
            The name of the event listener.
        """
        pass

    def contains_command(self, message_text: str) -> bool:
        """Checks if the message text contains any known MCP command or alias."""
        try:
            with open(MCP_COMMANDS_PATH, "r") as f:
                command_data = json.load(f)

            message_text = message_text.strip()
            for cmd in command_data.get("mcp_commands", []):
                if cmd.get("system_text") and cmd["system_text"] in message_text:
                    return True
                for alias in cmd.get("aliases", []):
                    if alias in message_text:
                        return True
            return False
        except Exception as e:
            print(f"Error checking for command: {e}")
            return False
            
    def _run_mcp_command(self, command_text: str) -> str:
        """Executes an MCP command from commands.json."""
        try:
            with open(MCP_COMMANDS_PATH, "r") as f:
                command_data = json.load(f)

            matched = next(
                (cmd for cmd in command_data["mcp_commands"] if cmd["system_text"] == command_text),
                None
            )
            if not matched:
                return f"Unknown MCP command: {command_text}"

            module_path = matched["python_code_module"]
            handler_name = matched.get("handler_function", "execute_command")

            # Load secrets
            with open(MCP_SECRETS_PATH, "r") as f:
                secrets = json.load(f)
                
            # Get common parameters
            common_params = secrets.get("common", {})

            # Find secrets for the matching module
            secret_entry = next(
                (s for s in secrets["secrets"] if s["python_code_module"] == module_path),
                None
            )
            if not secret_entry:
                return f"Missing secrets for module: {module_path}"

            # Merge common parameters with module-specific parameters
            # Module-specific parameters take precedence
            internal_params = {**common_params, **secret_entry["internal_params"]}
            command_parameters = {}  # Add if needed

            # Add mcp_commands to sys.path to allow importing modules from there
            mcp_commands_dir = os.path.abspath("mcp_commands")
            if mcp_commands_dir not in sys.path:
                sys.path.append(mcp_commands_dir)
                
            # Load and run the module
            from importlib.util import spec_from_file_location, module_from_spec
            from pathlib import Path
            module_file = Path(os.path.join(mcp_commands_dir, module_path))
            spec = spec_from_file_location("cmd_mod", module_file)
            cmd_mod = module_from_spec(spec)
            spec.loader.exec_module(cmd_mod)

            # Call the handler
            if hasattr(cmd_mod, handler_name):
                handler = getattr(cmd_mod, handler_name)
                print(f"🚀 Running MCP Command: {module_path}.{handler_name}")
                result = handler({}, internal_params)
                print(f"✅ Result:\n{result}\n")
            else:
                print(f"⚠️ Handler '{handler_name}' not found in {module_path}")

        except Exception as e:
            return f"Error executing command: {e}"
            
    def _process_mcp_commands(self, message_text: str) -> str:
        """Process and execute MCP commands found in the message text."""
        processed_text = (
            'In response to my initial prompt, "' + INITIAL_PROMPT + '", '
            'you requested the results of one or more MCP commands. '
            'Here are those results:\n\n'
        )

        try:
            # Load commands data
            with open(MCP_COMMANDS_PATH, "r") as f:
                command_data = json.load(f)
            
            # Get all available commands
            all_commands = [cmd["system_text"] for cmd in command_data.get("mcp_commands", [])]
            
            # Sort commands by length (descending) to avoid partial matches
            all_commands.sort(key=len, reverse=True)
            
            # Find and replace all commands in the response
            for command in all_commands:
                if command in message_text:
                    # Execute the command
                    command_result = self._run_mcp_command(command)
                    
                    # Replace the command with its result in the processed text
                    processed_text = processed_text + f"{command} Results:\n\n{command_result}\n"
        
        except Exception as e:
            # In case of error, append error message to the response
            processed_text += f"\n\nError processing commands: {str(e)}"

        processed_text = (
            processed_text
            + '\n\nPlease use the MCP command results provided to answer my initial prompt: "'
            + INITIAL_PROMPT
            + '"'
        )

        return processed_text


    def _execute_ai_agent_async(self, query: str, callback=None, recursion_depth=0):
        """
        Runs your AI agent locally using OpenAI API and MCP.
        If GPT returns a known command (e.g., /list_projects), execute it.
        """
        # Set a maximum recursion depth to prevent infinite loops
        MAX_RECURSION_DEPTH = 2
        gpt_handler = get_gpt_handler()

        if recursion_depth == 0:
            global INITIAL_PROMPT
            INITIAL_PROMPT = query

        def wrapped_callback(response: str):
            # Check if the response is an MCP command
            if self.contains_command(response) and recursion_depth < MAX_RECURSION_DEPTH:
                result_with_mcp_commands = self._process_mcp_commands(response)
                
                if callback:
                    # Pass the incremented recursion depth to prevent infinite loops
                    self._execute_ai_agent_async(result_with_mcp_commands, callback, recursion_depth + 1)
            else:
                if callback:
                    callback(response)

        gpt_handler.ask_gpt(query, wrapped_callback)
