# /Users/david/Documents/projects/ram_agent_service/src/input_triggers/input_triggers_main.py
import asyncio
import importlib
import os
import sys
import json
import logging # Added logging
from typing import List, Dict, Any, Optional, Type
from pathlib import Path

# --- BEGIN: Define Project Root ---
# Determine the absolute path to the project root directory
# Assumes this file is located at src/input_triggers/input_triggers_main.py
# Goes up three levels: input_triggers_main.py -> input_triggers -> src -> project_root
try:
    # Resolve the path of the current file
    current_file_path = Path(__file__).resolve()
    # Navigate up three levels to get the project root
    PROJECT_ROOT = current_file_path.parent.parent.parent
except NameError:
    # Fallback if __file__ is not defined (e.g., in interactive mode)
    # Adjust this fallback if necessary based on how the script might be run
    print("Warning: __file__ not defined, attempting fallback for PROJECT_ROOT.")
    # Example fallback: Assumes script is run from the 'src' directory
    PROJECT_ROOT = Path('.').resolve().parent

# Optional: Add src directory to sys.path if needed for imports within this module
# This might already be handled by main.py, but can be added here for robustness
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    # Insert at index 1 (after the script's directory) to avoid potential conflicts
    # if the script's directory needs priority for some reason.
    # Or use insert(0, ...) if you want src to have the highest priority.
    sys.path.insert(1, str(SRC_DIR))
    print(f"Added SRC_DIR to sys.path: {SRC_DIR}") # Optional: confirm path addition
# --- END: Define Project Root ---


# Now imports relative to src should work
from input_triggers.input_triggers import InputTrigger
from ras.chat_thread import get_gpt_handler

# Use logging instead of print for better control
logger = logging.getLogger(__name__)
# Configure basic logging if running standalone (though main app should configure)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# Dictionary to store loaded event listeners
listeners: Dict[str, InputTrigger] = {}

def ask_gpt(prompt: str, agent_config_data: Dict[str, Any]) -> str:
    """
    Send a request to the GPT model and wait for the response.
    This is a synchronous wrapper around the asynchronous GPT handler.

    Args:
        prompt: The prompt to send to the GPT model.
        agent_config_data: Configuration data for the specific agent.

    Returns:
        The response from the GPT model.
    """
    gpt_handler = get_gpt_handler(agent_config_data)
    return gpt_handler.ask_gpt_sync(prompt)

def ask_gpt_async(prompt: str, agent_config_data: Dict[str, Any], callback=None):
    """
    Queue a request to the GPT model without waiting for the response.

    Args:
        prompt: The prompt to send to the GPT model.
        agent_config_data: Configuration data for the specific agent.
        callback: Optional callback function to call with the response.
    """
    gpt_handler = get_gpt_handler(agent_config_data)
    gpt_handler.ask_gpt(prompt, callback)


def _load_json_file(file_path: Path, description: str) -> Optional[Dict[str, Any]]:
    """Loads a JSON file with error handling and logging."""
    if not file_path.exists():
        logger.error(f"  ❌ {description} file not found: {file_path}")
        return None
    if not file_path.is_file():
        logger.error(f"  ❌ {description} path is not a file: {file_path}")
        return None
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"  ✅ Successfully loaded {description} file: {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"  ❌ ERROR: Failed to parse JSON from {description} file '{file_path}': {e}")
        return None
    except IOError as e:
        logger.error(f"  ❌ ERROR: Could not read {description} file '{file_path}': {e}")
        return None
    except Exception as e:
        logger.error(f"  ❌ ERROR: An unexpected error occurred loading {description} file '{file_path}': {e}", exc_info=True)
        return None


async def _load_and_initialize_single_trigger(
    trigger_info: Dict[str, Any],
    agent_name: str,
    agent_config_data: Dict[str, Any], # Pass the whole agent config
    trigger_index_str: str # For logging context
) -> bool:
    """
    Loads configuration, imports module, finds class, instantiates,
    and initializes a single input trigger.

    Args:
        trigger_info: Dictionary containing the trigger's configuration from the agent config.
        agent_name: The name of the agent this trigger belongs to.
        agent_config_data: The full configuration data for the parent agent.
        trigger_index_str: A string identifier for logging (e.g., "Trigger #1").

    Returns:
        True if the trigger was successfully loaded and initialized, False otherwise.
    """
    global listeners # Need access to the global listener dict

    if not isinstance(trigger_info, dict):
        logger.warning(f"  Skipping {trigger_index_str} for agent '{agent_name}' - item in 'input_triggers' is not a dictionary.")
        return False

    module_path_str = trigger_info.get("python_code_module")
    if not module_path_str or not isinstance(module_path_str, str):
        logger.warning(f"  Skipping {trigger_index_str} for agent '{agent_name}' due to missing or invalid 'python_code_module'.")
        return False

    # --- Get Trigger-Specific Config and Secrets Paths ---
    trigger_config_relative_path = trigger_info.get("input_trigger_config_file")
    if not trigger_config_relative_path or not isinstance(trigger_config_relative_path, str):
        logger.warning(f"  Skipping {trigger_index_str} ('{module_path_str}') for agent '{agent_name}' due to missing or invalid 'input_trigger_config_file'.")
        return False

    trigger_secrets_relative_path = trigger_info.get("input_trigger_secrets_file")
    if not trigger_secrets_relative_path or not isinstance(trigger_secrets_relative_path, str):
        logger.warning(f"  Skipping {trigger_index_str} ('{module_path_str}') for agent '{agent_name}' due to missing or invalid 'input_trigger_secrets_file'.")
        return False

    # Construct absolute paths relative to project root
    trigger_config_absolute_path = PROJECT_ROOT / trigger_config_relative_path
    trigger_secrets_absolute_path = PROJECT_ROOT / trigger_secrets_relative_path

    logger.info(f"    {trigger_index_str}: Module '{module_path_str}'")
    logger.info(f"      Config Path: {trigger_config_absolute_path}")
    logger.info(f"      Secrets Path: {trigger_secrets_absolute_path}")

    # --- Load Trigger-Specific Config and Secrets ---
    trigger_config_data = _load_json_file(trigger_config_absolute_path, f"{trigger_index_str} Config")
    if trigger_config_data is None:
        return False # Error already logged by _load_json_file

    trigger_secrets_data = _load_json_file(trigger_secrets_absolute_path, f"{trigger_index_str} Secrets")
    if trigger_secrets_data is None:
        return False # Error already logged by _load_json_file

    # --- Import Module and Find Class ---
    logger.info(f"    Attempting to load trigger module: {module_path_str}")
    try:
        module = importlib.import_module(module_path_str)
        input_trigger_class: Optional[Type[InputTrigger]] = None
        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)
                # Check if it's a class, a subclass of InputTrigger, not InputTrigger itself,
                # and not an abstract class (if InputTrigger might have abstract methods)
                if (isinstance(attr, type) and
                    issubclass(attr, InputTrigger) and
                    attr is not InputTrigger and
                    not getattr(attr, '__abstractmethods__', False)): # Check if concrete
                    input_trigger_class = attr
                    logger.info(f"      Found listener class: {input_trigger_class.__name__}")
                    break
            except Exception as inner_e:
                # Log potential issues inspecting attributes but continue searching
                logger.warning(f"      Warning: Error inspecting attribute '{attr_name}' in module {module_path_str}: {inner_e}")

        if not input_trigger_class:
            logger.error(f"    ❌ ERROR: No concrete InputTrigger subclass found in module {module_path_str}.")
            return False

        # --- Instantiate the listener class with specific config and secrets ---
        try:
            # Pass the full agent config, trigger config, and trigger secrets
            listener = input_trigger_class(
                agent_config_data=agent_config_data, # Pass the whole agent config
                trigger_config_data=trigger_config_data,
                trigger_secrets=trigger_secrets_data
            )

            # Unique listener name for the global dictionary
            # Use agent name prefix for uniqueness across agents
            listener_name = f"{agent_name}_{listener.name}"

            if listener_name in listeners:
                 logger.error(f"    ❌ ERROR: Duplicate listener instance name '{listener_name}' detected. Skipping this instance.")
                 return False # Prevent overwriting

            logger.info(f"    Initializing '{listener_name}' ({input_trigger_class.__name__})...")
            await listener.initialize() # Call the async initialize method
            listeners[listener_name] = listener # Add to global dict
            logger.info(f"    ✅ Successfully initialized '{listener_name}' for agent '{agent_name}'.")
            return True # Indicate success

        except TypeError as te:
            # Catch if the listener __init__ doesn't accept the expected args
            logger.error(f"    ❌ ERROR: Failed to instantiate {input_trigger_class.__name__} (TypeError): {te}. Check its __init__ method signature (expected agent_config_data, trigger_config_data, trigger_secrets).", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"    ❌ ERROR: Failed to initialize {input_trigger_class.__name__} for agent '{agent_name}': {e}", exc_info=True)
            return False

    except (ImportError, ModuleNotFoundError) as e:
        logger.error(f"    ❌ ERROR: Could not import trigger module '{module_path_str}': {e}", exc_info=True)
        return False
    except Exception as e:
         logger.error(f"    ❌ ERROR: Unexpected error processing trigger module '{module_path_str}': {e}", exc_info=True)
         return False


async def load_input_triggers(agent_manifest_data: Dict[str, Any]):
    """
    Load and initialize input triggers specified in agent configuration files
    listed in the agent manifest.

    Args:
        agent_manifest_data: Dictionary containing the loaded agent manifest data.
                             Expected structure: {"agents": [{"name": "...", "agent_config_file": "path/to/config.json", ...}, ...]}
    """
    global listeners # Ensure we modify the global dict
    listeners = {} # Clear any previous listeners

    logger.info("Loading input triggers based on agent manifest...")

    if not agent_manifest_data or "agents" not in agent_manifest_data:
        logger.error("Agent manifest data is missing or does not contain an 'agents' list.")
        return

    loaded_listener_count = 0
    processed_agents = 0

    for agent_info in agent_manifest_data.get("agents", []):
        processed_agents += 1
        agent_name = agent_info.get("name", f"Agent_{processed_agents}") # Use name or generate one
        config_file_relative = agent_info.get("agent_config_file")

        if not config_file_relative:
            logger.warning(f"Agent '{agent_name}' is missing the 'agent_config_file' key in the manifest. Skipping.")
            continue

        # Construct absolute path relative to the project root
        config_file_absolute = PROJECT_ROOT / config_file_relative

        logger.info(f"\nProcessing Agent: '{agent_name}'")
        logger.info(f"  Attempting to load agent config: {config_file_absolute}")

        # Load the agent-specific configuration JSON using the helper
        agent_config_data = _load_json_file(config_file_absolute, f"Agent '{agent_name}' Config")
        if agent_config_data is None:
            continue # Error already logged

        # Ensure agent name from config matches manifest/generated name (or update if needed)
        # This assumes the agent config *also* has a "name" field.
        config_agent_name = agent_config_data.get("name")
        if config_agent_name and config_agent_name != agent_name:
             logger.warning(f"  Agent name mismatch: Manifest/Generated='{agent_name}', Config='{config_agent_name}'. Using '{agent_name}'.")
             # Ensure the agent_config_data used later has the consistent name
             agent_config_data["name"] = agent_name
        elif not config_agent_name:
             logger.warning(f"  Agent config file {config_file_absolute} is missing the 'name' key. Using '{agent_name}'.")
             agent_config_data["name"] = agent_name # Add it for consistency


        # Load input triggers specified in this agent's config
        input_triggers_list = agent_config_data.get("input_triggers", [])
        if not isinstance(input_triggers_list, list):
            logger.warning(f"  'input_triggers' in config for agent '{agent_name}' is not a list. Skipping triggers for this agent.")
            continue

        if not input_triggers_list:
            logger.info(f"  No 'input_triggers' found or list is empty in the config for agent '{agent_name}'.")
            continue

        logger.info(f"  Found {len(input_triggers_list)} input trigger(s) specified for '{agent_name}'.")

        # --- Loop through triggers and call the helper function ---
        for i, trigger_info in enumerate(input_triggers_list):
            trigger_index_str = f"Trigger #{i+1}" # For logging context
            # Call the new helper function to handle loading/initialization
            success = await _load_and_initialize_single_trigger(
                trigger_info=trigger_info,
                agent_name=agent_name,
                agent_config_data=agent_config_data, # Pass the loaded agent config
                trigger_index_str=trigger_index_str
            )
            if success:
                loaded_listener_count += 1
            # Errors are logged within the helper function

    logger.info(f"\nFinished processing {processed_agents} agent(s).")
    if loaded_listener_count > 0:
        logger.info(f"✅ Successfully loaded and initialized {loaded_listener_count} input trigger(s) in total.")
    else:
        logger.warning("⚠️ No input triggers were successfully loaded.")


async def start_input_triggers():
    """
    Start all successfully initialized event listeners.
    """
    if not listeners:
        logger.warning("No listeners were successfully initialized to start.")
        return

    logger.info(f"\nStarting {len(listeners)} initialized event listener(s)...")

    start_tasks = []
    # Start each listener concurrently
    for name, listener in listeners.items():
        logger.info(f"Creating start task for '{name}'...")
        start_tasks.append(asyncio.create_task(listener.start(), name=f"start_{name}"))

    # Wait for all start tasks to complete (or raise exceptions)
    if start_tasks:
        try:
            # Use gather to run them concurrently and wait
            results = await asyncio.gather(*start_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                 task_name = start_tasks[i].get_name().replace("start_", "")
                 if isinstance(result, Exception):
                     logger.error(f"ERROR: Failed to start '{task_name}': {result}", exc_info=result)
                 else:
                     logger.info(f"Successfully started '{task_name}'.")
        except Exception as e:
            logger.error(f"ERROR: An unexpected error occurred during listener startup: {e}", exc_info=True)


async def stop_event_listeners():
    """
    Stop all running event listeners.
    """
    if not listeners:
        return # Nothing to stop

    logger.info(f"\nStopping {len(listeners)} event listener(s)...")

    stop_tasks = []
    # Stop each listener concurrently
    for name, listener in listeners.items():
         logger.info(f"Creating stop task for '{name}'...")
         # Ensure stop is awaitable, handle potential errors during stop
         stop_tasks.append(asyncio.create_task(listener.stop(), name=f"stop_{name}"))

    # Wait for all stop tasks to complete (or raise exceptions)
    if stop_tasks:
        try:
            results = await asyncio.gather(*stop_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                 task_name = stop_tasks[i].get_name().replace("stop_", "")
                 if isinstance(result, Exception):
                     logger.error(f"ERROR: Error stopping '{task_name}': {result}", exc_info=result)
                 else:
                     logger.info(f"Successfully stopped '{task_name}'.")
        except Exception as e:
            logger.error(f"ERROR: An unexpected error occurred during listener shutdown: {e}", exc_info=True)


async def main(agent_manifest_data: Dict[str, Any]): # Manifest is now required
    """
    Main entry point for the input triggers system.
    Loads, starts, and manages event listeners based on the agent manifest.

    Args:
        agent_manifest_data: Dictionary containing agent manifest data.
    """
    try:
        # Load listeners using the new manifest-driven logic
        await load_input_triggers(agent_manifest_data) # Pass the manifest

        # Start whatever listeners were successfully loaded
        await start_input_triggers()

        if not listeners:
             logger.warning("No listeners running. Exiting.")
             return # Exit if no listeners started

        # Keep the main thread alive while listeners run in the background
        logger.info("\nAll available event listeners started. Press Ctrl+C to exit.")
        while True:
            # Check if any listener tasks have unexpectedly stopped (optional)
            # Add more sophisticated monitoring if needed
            await asyncio.sleep(3600) # Sleep for a long time, woken by Ctrl+C

    except asyncio.CancelledError:
         logger.info("Main task cancelled.") # Handle cancellation if running within another loop
    except KeyboardInterrupt:
        logger.info("\nCtrl+C received. Shutting down gracefully...")
    finally:
        # Ensure proper cleanup
        logger.info("Initiating listener shutdown...")
        await stop_event_listeners()

# Example of direct usage (less likely now it's called from elsewhere)
if __name__ == "__main__":
    # Basic logging setup for direct execution testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.error("Running input_triggers_main directly is not supported with the new manifest-driven loading.")
    logger.error("Please run the main application entry point (e.g., ras/main.py) which provides the manifest.")
    # You could potentially load a dummy manifest here for testing if needed:
    # dummy_manifest = {"agents": [...]}
    # asyncio.run(main(dummy_manifest))
