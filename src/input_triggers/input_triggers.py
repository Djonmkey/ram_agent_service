# src/input_triggers/input_triggers.py
import json
import os
import sys
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

# Ensure src is in path for sibling imports if run directly (though main entry point should handle this)
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Assuming constants are defined relative to src or configured
# If constants.py is in src: from constants import ...
# Otherwise, make these paths configurable
DEFAULT_MCP_COMMANDS_PATH = SRC_DIR / "mcp_commands" / "commands.json"
DEFAULT_MCP_SECRETS_PATH = SRC_DIR / "mcp_commands" / "secrets.json"
DEFAULT_MCP_MODULES_DIR = SRC_DIR / "mcp_commands"

# Import GPT handler safely
try:
    from gpt_thread import get_gpt_handler
except ImportError:
    print("Warning: Could not import get_gpt_handler. AI agent functionality will be limited.")
    get_gpt_handler = None # type: ignore


class InputTrigger(ABC):
    """
    Abstract base class for input triggers (event listeners).
    Provides common functionality for configuration, logging, and AI agent interaction.
    """

    def __init__(self,
                 agent_name: str,
                 trigger_config_data: Optional[Dict[str, Any]] = None,
                 trigger_secrets: Optional[Dict[str, Any]] = None):
        """
        Initialize the base trigger.

        Args:
            agent_name: The name of the agent this trigger instance belongs to.
            trigger_config_data: Dictionary containing the specific configuration
                                 for this trigger instance.
            trigger_secrets: Dictionary containing the secrets required by this
                             trigger instance.
        """
        self.agent_name = agent_name
        # Store the provided config and secrets, defaulting to empty dicts if None
        self.trigger_config: Dict[str, Any] = trigger_config_data or {}
        self.trigger_secrets: Dict[str, Any] = trigger_secrets or {}

        self.logger = logging.getLogger(f"{self.agent_name}.{self.__class__.__name__}") # Include agent name in logger
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Get configurable paths from the trigger-specific config, falling back to defaults
        # Note: We now use self.trigger_config instead of self.config
        self.mcp_commands_path = Path(self.trigger_config.get("mcp_commands_path", DEFAULT_MCP_COMMANDS_PATH))
        self.mcp_secrets_path = Path(self.trigger_config.get("mcp_secrets_path", DEFAULT_MCP_SECRETS_PATH))
        self.mcp_modules_dir = Path(self.trigger_config.get("mcp_modules_dir", DEFAULT_MCP_MODULES_DIR))

        self.logger.debug(f"Base trigger initialized for Agent '{self.agent_name}', Trigger '{self.name}'")
        self.logger.debug(f"Trigger Config Keys: {list(self.trigger_config.keys())}") # Log keys, not values
        # Avoid logging secrets keys unless necessary for debugging specific issues
        # self.logger.debug(f"Trigger Secrets Keys: {list(self.trigger_secrets.keys())}")
        self.logger.debug(f"MCP Commands Path: {self.mcp_commands_path}")
        self.logger.debug(f"MCP Secrets Path: {self.mcp_secrets_path}")
        self.logger.debug(f"MCP Modules Dir: {self.mcp_modules_dir}")

    # --- Removed _resolve_config_path and _load_config methods ---
    # Configuration is now passed directly via __init__

    @abstractmethod
    async def initialize(self):
        """
        Initialize the specific trigger.
        Should be called by subclasses after super().initialize().
        Responsible for setting up connections, resources, etc.
        """
        self.loop = asyncio.get_running_loop()
        self.logger.info(f"Initializing trigger: {self.name} for Agent: {self.agent_name}")
        # Subclasses should continue initialization here

    @abstractmethod
    async def start(self):
        """
        Start the trigger's main loop or event listening process.
        """
        self.logger.info(f"Starting trigger: {self.name} for Agent: {self.agent_name}")
        pass

    @abstractmethod
    async def stop(self):
        """
        Stop the trigger and clean up resources.
        """
        self.logger.info(f"Stopping trigger: {self.name} for Agent: {self.agent_name}")
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the unique name of the trigger class (subclass responsibility).
        Note: The unique instance name used in the main loop is agent_name + listener.name
        """
        pass

    # --- MCP Command Handling (no changes needed here, uses self.mcp_... paths) ---
    # ... (rest of the MCP methods remain the same) ...
    def _load_json_safely(self, file_path: Path) -> Optional[Dict]:
        """Safely load JSON data from a file."""
        if not file_path.exists():
            self.logger.error(f"Required file not found: {file_path}")
            return None
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            self.logger.error(f"Failed to decode JSON from: {file_path}", exc_info=True)
            return None
        except Exception:
            self.logger.error(f"Error reading file: {file_path}", exc_info=True)
            return None

    def contains_command(self, message_text: str) -> bool:
        """Checks if the message text contains any known MCP command or alias."""
        command_data = self._load_json_safely(self.mcp_commands_path)
        if not command_data:
            return False

        message_text_lower = message_text.lower().strip() # Case-insensitive check
        try:
            for cmd in command_data.get("mcp_commands", []):
                system_text = cmd.get("system_text")
                if system_text and system_text.lower() in message_text_lower:
                    self.logger.debug(f"Found command '{system_text}' in message.")
                    return True
                for alias in cmd.get("aliases", []):
                    if alias.lower() in message_text_lower:
                        self.logger.debug(f"Found command alias '{alias}' in message.")
                        return True
            return False
        except Exception:
            self.logger.error("Error during command checking", exc_info=True)
            return False

    def _run_mcp_command(self, command_text: str) -> str:
        """Executes a specific MCP command identified by its system_text."""
        self.logger.info(f"Attempting to run MCP command: {command_text}")
        command_data = self._load_json_safely(self.mcp_commands_path)
        secrets_data = self._load_json_safely(self.mcp_secrets_path) # MCP secrets, not trigger secrets

        if not command_data or not secrets_data:
            return "Error: Could not load MCP command or secrets configuration."

        try:
            # Find the command definition matching the exact system_text
            matched_cmd = next(
                (cmd for cmd in command_data.get("mcp_commands", [])
                 if cmd.get("system_text") == command_text),
                None
            )
            if not matched_cmd:
                self.logger.warning(f"Unknown MCP command requested: {command_text}")
                return f"Unknown MCP command: {command_text}"

            module_path_str = matched_cmd.get("python_code_module")
            handler_name = matched_cmd.get("handler_function", "execute_command")

            if not module_path_str:
                 self.logger.error(f"Command '{command_text}' is missing 'python_code_module' in config.")
                 return f"Configuration error for command: {command_text}"

            module_file = self.mcp_modules_dir / module_path_str
            if not module_file.exists():
                self.logger.error(f"MCP module file not found: {module_file}")
                return f"Error: Module file not found for command {command_text}"

            # Load secrets for the module from MCP secrets file
            common_params = secrets_data.get("common", {})
            secret_entry = next(
                (s for s in secrets_data.get("secrets", [])
                 if s.get("python_code_module") == module_path_str),
                None
            )
            if not secret_entry:
                self.logger.warning(f"Missing secrets entry for module: {module_path_str} in {self.mcp_secrets_path}")
                internal_params = common_params # Use only common if specific are missing
            else:
                # Merge common with specific, specific taking precedence
                internal_params = {**common_params, **secret_entry.get("internal_params", {})}

            # Dynamically load and execute the module's handler function
            spec = spec_from_file_location(module_file.stem, module_file)
            if not spec or not spec.loader:
                 self.logger.error(f"Could not create module spec for {module_file}")
                 return f"Error loading module for command {command_text}"

            cmd_mod = module_from_spec(spec)
            spec.loader.exec_module(cmd_mod)

            if hasattr(cmd_mod, handler_name):
                handler = getattr(cmd_mod, handler_name)
                self.logger.info(f"🚀 Running MCP Command: {module_path_str}.{handler_name}")
                # Pass MCP internal params. Trigger secrets (self.trigger_secrets) are available
                # within the trigger instance if needed by the trigger logic itself, but not
                # typically passed directly to MCP command handlers unless designed that way.
                result = handler({}, internal_params)
                self.logger.info(f"✅ MCP Command '{command_text}' result received.")
                return str(result) # Ensure result is string
            else:
                self.logger.error(f"Handler function '{handler_name}' not found in module {module_path_str}")
                return f"Error: Handler not found for command {command_text}"

        except Exception as e:
            self.logger.error(f"Error executing MCP command '{command_text}': {e}", exc_info=True)
            return f"Error executing command {command_text}: {e}"

    def _process_mcp_commands(self, gpt_response: str, initial_query: str) -> str:
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

        # Get all defined command system_texts
        all_commands = [
            cmd["system_text"] for cmd in command_data.get("mcp_commands", []) if "system_text" in cmd
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


    # --- AI Agent Interaction (no changes needed here) ---
    # ... (rest of the AI methods remain the same) ...
    def _execute_ai_agent_async(self,
                                initial_query: str,
                                callback: Callable[[str], None],
                                current_prompt: Optional[str] = None,
                                recursion_depth: int = 0):
        """
        Handles interaction with the AI agent, including MCP command execution loops.

        Args:
            initial_query: The original query from the user/event source.
            callback: The final callback function to call with the AI's definitive answer.
            current_prompt: The prompt to send to the AI in the current step. Defaults to initial_query.
            recursion_depth: Internal counter to prevent infinite loops.
        """
        MAX_RECURSION_DEPTH = 3 # Allow initial call + 2 rounds of MCP commands
        if get_gpt_handler is None:
            self.logger.error("GPT Handler not available. Cannot execute AI agent.")
            callback("Error: AI agent is not configured.")
            return

        gpt_handler = get_gpt_handler()
        prompt_to_send = current_prompt if current_prompt is not None else initial_query

        if recursion_depth >= MAX_RECURSION_DEPTH:
            self.logger.warning(f"Max recursion depth ({MAX_RECURSION_DEPTH}) reached for query: {initial_query[:50]}...")
            callback("Error: Reached maximum processing depth. Could not fully resolve request.")
            return

        self.logger.info(f"Executing AI Agent (Depth: {recursion_depth}). Prompt starts with: {prompt_to_send[:100]}...")

        # Define the callback that GPT handler will call
        def gpt_handler_callback(response: str):
            self.logger.debug(f"AI Agent response received (Depth: {recursion_depth}). Starts with: {response[:100]}...")
            # Check if the response contains an MCP command
            if self.contains_command(response):
                self.logger.info(f"AI response contains MCP command(s). Processing... (Depth: {recursion_depth})")
                # Generate the new prompt with command results
                next_prompt = self._process_mcp_commands(response, initial_query)
                # Recursive call with the new prompt and incremented depth
                self._execute_ai_agent_async(initial_query, callback, next_prompt, recursion_depth + 1)
            else:
                # No commands, this is the final answer
                self.logger.info(f"AI Agent processing complete (Depth: {recursion_depth}). Calling final callback.")
                callback(response)

        # Make the asynchronous call to the GPT handler
        try:
            gpt_handler.ask_gpt(prompt_to_send, gpt_handler_callback)
        except Exception as e:
             self.logger.error(f"Failed to queue request to GPT handler: {e}", exc_info=True)
             callback(f"Error: Failed to communicate with AI agent: {e}")

