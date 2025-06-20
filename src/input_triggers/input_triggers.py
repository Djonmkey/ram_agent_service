# src/input_triggers/input_triggers.py
import re
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
DEFAULT_MCP_COMMANDS_PATH = SRC_DIR / "tools_and_data" / "commands.json"
DEFAULT_MCP_SECRETS_PATH = SRC_DIR / "tools_and_data" / "secrets.json"
DEFAULT_MCP_MODULES_DIR = ""

from ras.work_queue_manager import enqueue_input_trigger

class InputTrigger(ABC):
    """
    Abstract base class for input triggers (event listeners).
    Provides common functionality for configuration, logging, and AI agent interaction.
    """

    def __init__(self,
                 agent_config_data: Dict[str, Any],
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
        self.agent_config_data = agent_config_data
        self.agent_name = agent_config_data["name"]
        # Store the provided config and secrets, defaulting to empty dicts if None
        self.trigger_config: Dict[str, Any] = trigger_config_data or {}
        self.trigger_secrets: Dict[str, Any] = trigger_secrets or {}

        self.logger = logging.getLogger(f"{self.agent_name}.{self.__class__.__name__}") # Include agent name in logger
        self.loop: Optional[asyncio.AbstractEventLoop] = None

        # Get configurable paths from the trigger-specific config, falling back to defaults
        # Note: We now use self.trigger_config instead of self.config
        self.mcp_commands_path = Path(self.agent_config_data.get("tools_and_data", {}).get("mcp_commands_config_file", DEFAULT_MCP_COMMANDS_PATH))
        self.mcp_secrets_path = Path(self.agent_config_data.get("tools_and_data", {}).get("mcp_commands_secrets_file", DEFAULT_MCP_SECRETS_PATH))
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


        prompt_to_send = current_prompt if current_prompt is not None else initial_query

        if recursion_depth >= MAX_RECURSION_DEPTH:
            self.logger.warning(f"Max recursion depth ({MAX_RECURSION_DEPTH}) reached for query: {initial_query[:50]}...")
            callback("Error: Reached maximum processing depth. Could not fully resolve request.")
            return

        self.logger.info(f"Executing AI Agent (Depth: {recursion_depth}). Prompt starts with: {prompt_to_send[:100]}...")

        # Define the callback that GPT handler will call
        async def gpt_handler_callback(response: str):
            self.logger.debug(f"AI Agent response received (Depth: {recursion_depth}). Starts with: {response[:100]}...")
            # Check if the response contains an MCP command
            if self.contains_mcp_command(response):
                immediate_response = self.escape_system_text_with_command_escape_text(response)

                # Chat back that we are still processing
                callback(immediate_response)
                
                self.logger.info(f"AI response contains MCP command(s). Processing... (Depth: {recursion_depth})")
                # Generate the new prompt with command results
                next_prompt = self._process_mcp_commands(response, initial_query)
                # Recursive call with the new prompt and incremented depth
                self._execute_ai_agent_async(initial_query, callback, next_prompt, recursion_depth + 1)
            else:
                # No commands, this is the final answer
                self.logger.info(f"AI Agent processing complete (Depth: {recursion_depth}). Calling final callback.")

                if asyncio.iscoroutinefunction(callback):
                    # If it's an async function, await it
                    await callback(response)
                else:
                    # If it's a regular function, just call it
                    callback(response)

        # Make the asynchronous call to the GPT handler
        try:
            meta_data = {
                "message_id": None,
                "ack_message_id": None,
                "channel_id": None,
                "guild_id": None,
                "author_id": None,
                "author_name": None
            }

            agent_name = self.agent_config_data["name"]
        
            enqueue_input_trigger(agent_name, prompt_to_send, meta_data)

        except Exception as e:
             self.logger.error(f"Failed to queue request to GPT handler: {e}", exc_info=True)
             callback(f"Error: Failed to communicate with AI agent: {e}")

