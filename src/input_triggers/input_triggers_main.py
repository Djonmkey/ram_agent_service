# /Users/david/Documents/projects/ram_agent_service/src/input_triggers/input_triggers_main.py
import asyncio
import importlib
import os
import sys
import json
import logging
from typing import List, Dict, Any, Optional, Type
from pathlib import Path
import pathlib

import ras.work_queue_manager 
from ras.agent_config_buffer import get_agent_name_list, get_agent_config
from ras.work_queue_manager import enqueue_chat_model_request

# --- Removed PROJECT_ROOT and SRC_DIR definition ---
# It's assumed that the main application entry point (e.g., main.py)
# correctly configures sys.path so that imports relative to 'src' work.

# Now imports relative to src should work if sys.path is configured correctly
from input_triggers.input_triggers import InputTrigger

# Use logging instead of print for better control
logger = logging.getLogger(__name__)
# Configure basic logging if running standalone (though main app should configure)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# (Assuming PROJECT_ROOT_PATH is defined elsewhere, e.g., at the module level)
# Example definition:
PROJECT_ROOT_PATH = pathlib.Path(__file__).resolve().parent.parent.parent # Adjust based on actual project structure

# --- Helper Function to Get Project Root ---
def _get_project_root() -> Path:
    """
    Determines the absolute path to the project root directory.
    Assumes this file is located at src/input_triggers/input_triggers_main.py
    Goes up three levels: input_triggers_main.py -> input_triggers -> src -> project_root
    """
    try:
        # Resolve the path of the current file
        current_file_path = Path(__file__).resolve()
        # Navigate up three levels to get the project root
        project_root = current_file_path.parent.parent.parent
        return project_root
    except NameError:
        # Fallback if __file__ is not defined (e.g., in interactive mode)
        # This fallback is less reliable as it depends on the CWD.
        logger.warning("Warning: __file__ not defined, attempting fallback for project root based on CWD.")
        # Example fallback: Assumes script is run from the 'src' directory
        # Adjust this if necessary based on how the script might be run without __file__
        project_root = Path('.').resolve().parent # CWD/../
        logger.warning(f"Using fallback project root: {project_root}")
        return project_root

def _resolve_path_relative_to_project_root(relative_path_str: str) -> str:
    """Resolves a relative path string to an absolute path string relative to the project root.

    Args:
        relative_path_str: The relative path as a string (e.g., "data/input.csv").

    Returns:
        The absolute path as a string.

    Raises:
        FileNotFoundError: If the resolved path does not exist.
        TypeError: If relative_path_str is not a string.
    """
    if not isinstance(relative_path_str, str):
        return None

    # Ensure PROJECT_ROOT_PATH is a Path object
    project_root = pathlib.Path(PROJECT_ROOT_PATH)

    if os.path.exists(relative_path_str):
        # If the path already exists, return it as is
        return str(pathlib.Path(relative_path_str).resolve())

    # Create a Path object from the relative string and resolve it
    # Use the / operator for joining paths, which is idiomatic for pathlib
    absolute_path = (project_root / relative_path_str).resolve()

    # Check if the file/directory exists
    if not absolute_path.exists():
        raise FileNotFoundError(f"Resolved path does not exist: {absolute_path}")

    # Convert the Path object to a string before returning
    return str(absolute_path)


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
    agent_name = agent_config_data["name"]
    enqueue_chat_model_request(agent_name, prompt)

def ask_gpt_async(prompt: str, agent_config_data: Dict[str, Any], callback=None):
    """
    Queue a request to the GPT model without waiting for the response.

    Args:
        prompt: The prompt to send to the GPT model.
        agent_config_data: Configuration data for the specific agent.
        callback: Optional callback function to call with the response.
    """
    agent_name = agent_config_data["name"]

    enqueue_chat_model_request(agent_name, prompt)

def _load_json_file(file_path_str: str, description: str) -> Optional[Dict[str, Any]]:
    """Loads a JSON file with error handling and logging.

    Args:
        file_path_str: The absolute path to the JSON file as a string.
        description: A description of the file being loaded (for logging).

    Returns:
        A dictionary containing the loaded JSON data, or None if an error occurred.
    """
    try:
        # --- Convert the input string path to a Path object ---
        file_path = Path(file_path_str)

        # Note: The check for absolute path might be less critical now if
        # _resolve_path_relative_to_project_root guarantees absoluteness,
        # but keeping it can be a safety measure.
        if not file_path.is_absolute():
            logger.error(f"  ❌ Path provided to _load_json_file should be absolute, but received: {file_path_str}")
            # Depending on requirements, you might want to resolve it here,
            # but it's generally better if the caller provides an absolute path.
            # file_path = file_path.resolve() # Resolves relative to CWD if not absolute
            return None

        if not file_path.exists():
            logger.error(f"  ❌ {description} file not found: {file_path}")
            return None
        if not file_path.is_file():
            logger.error(f"  ❌ {description} path is not a file: {file_path}")
            return None

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"  ✅ Successfully loaded {description} file: {file_path}")
        return data
    except json.JSONDecodeError as e:
        logger.error(f"  ❌ ERROR: Failed to parse JSON from {description} file '{file_path_str}': {e}")
        return None
    except IOError as e:
        logger.error(f"  ❌ ERROR: Could not read {description} file '{file_path_str}': {e}")
        return None
    except TypeError as e: # Catch potential errors if file_path_str isn't a string-like object for Path()
        logger.error(f"  ❌ ERROR: Invalid path type provided for {description}: {type(file_path_str)}. Error: {e}")
        return None
    except Exception as e:
        # Use file_path_str in the log message as file_path might not be defined if Path() failed
        logger.error(f"  ❌ ERROR: An unexpected error occurred loading {description} file '{file_path_str}': {e}", exc_info=True)
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

    module_path_str_original = trigger_info.get("python_code_module")
    if not module_path_str_original or not isinstance(module_path_str_original, str):
        logger.warning(f"  Skipping {trigger_index_str} for agent '{agent_name}' due to missing or invalid 'python_code_module'.")
        return False

    # --- Convert file path to Python import path ---
    module_path_for_import = module_path_str_original
    if module_path_for_import.endswith(".py"):
        module_path_for_import = module_path_for_import[:-3] # Remove .py extension
    # Replace OS-specific separators (like / or \) with dots
    module_path_for_import = module_path_for_import.replace(os.path.sep, '.')

    # --- Get Trigger-Specific Config and Secrets Paths ---
    trigger_config_relative_path = trigger_info.get("input_trigger_config_file")
    if not trigger_config_relative_path or not isinstance(trigger_config_relative_path, str):
        logger.warning(f"  Skipping {trigger_index_str} ('{module_path_str_original}') for agent '{agent_name}' due to missing or invalid 'input_trigger_config_file'.")
        return False

    trigger_secrets_relative_path = trigger_info.get("input_trigger_secrets_file")
    if not trigger_secrets_relative_path or not isinstance(trigger_secrets_relative_path, str):
        logger.warning(f"  Warning {trigger_index_str} ('{module_path_str_original}') for agent '{agent_name}' due to missing 'input_trigger_secrets_file'.")

    # --- Resolve paths relative to project root using the helper ---
    try:
        trigger_config_absolute_path = _resolve_path_relative_to_project_root(trigger_config_relative_path)
        trigger_secrets_absolute_path = _resolve_path_relative_to_project_root(trigger_secrets_relative_path)
    except (ValueError, Exception) as e:
         logger.error(f"    ❌ ERROR: Could not resolve paths for {trigger_index_str} ('{module_path_str_original}') for agent '{agent_name}': {e}", exc_info=True)
         return False

    logger.info(f"      Input Trigger Module '{module_path_str_original}' (Import Path: '{module_path_for_import}')")
    logger.info(f"      Config Path (Resolved): {trigger_config_absolute_path}")
    logger.info(f"      Secrets Path (Resolved): {trigger_secrets_absolute_path}")

    # --- Load Trigger-Specific Config and Secrets ---
    trigger_config_data = _load_json_file(trigger_config_absolute_path, f"{trigger_index_str} Config")
    if trigger_config_data is None:
        return False # Error already logged by _load_json_file

    trigger_secrets_data = _load_json_file(trigger_secrets_absolute_path, f"{trigger_index_str} Secrets")

    # --- Import Module and Find Class ---
    logger.info(f"    Attempting to import trigger module: {module_path_for_import}")
    try:
        # Use the converted import path
        module = importlib.import_module(module_path_for_import)
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
                logger.warning(f"      Warning: Error inspecting attribute '{attr_name}' in module {module_path_for_import}: {inner_e}")

        if not input_trigger_class:
            logger.error(f"    ❌ ERROR: No concrete InputTrigger subclass found in module {module_path_for_import}.")
            return False

        # --- Instantiate the listener class with specific config and secrets ---
        try:
            # Pass the full agent config, trigger config, and trigger secrets
            listener = input_trigger_class(
                agent_config_data=agent_config_data, # Pass the whole agent config
                trigger_config_data=trigger_config_data,
                trigger_secrets=(trigger_secrets_data or {}).get("secrets", {})
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
        # Log the import path that failed
        logger.error(f"    ❌ ERROR: Could not import trigger module '{module_path_for_import}': {e}", exc_info=True)
        return False
    except Exception as e:
         logger.error(f"    ❌ ERROR: Unexpected error processing trigger module '{module_path_for_import}': {e}", exc_info=True)
         return False


async def load_input_triggers():
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
    loaded_listener_count = 0
    processed_agents = 0

    for agent_name in get_agent_name_list():
        processed_agents += 1

        # Load the agent-specific configuration JSON using the helper
        agent_config_data =  get_agent_config(agent_name)

        # Load input triggers specified in this agent's config
        input_trigger = agent_config_data.get("input_trigger", [])
        
        success = await _load_and_initialize_single_trigger(
            trigger_info=input_trigger,
            agent_name=agent_name,
            agent_config_data=agent_config_data, # Pass the loaded agent config
            trigger_index_str=""
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


async def main(mcp_client_manager): # Manifest is now required
    """
    Main entry point for the input triggers system.
    Loads, starts, and manages event listeners based on the agent manifest.

    Args:
        mcp_client_manager: The MCPClientManager instance.
    """
    try:
        # Load listeners using the new manifest-driven logic
        await load_input_triggers() # Pass the manifest

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

# Example Usage (optional, for demonstration):
if __name__ == '__main__':
    try:
        # Assuming a file 'README.md' exists at the project root for this example
        readme_path_str = _resolve_path_relative_to_project_root("README.md")
        print(f"Resolved path (string): {readme_path_str}")
        print(f"Type: {type(readme_path_str)}")

        # Example of a non-existent file
        # non_existent_path = _resolve_path_relative_to_project_root("non_existent_file.txt")
        # print(non_existent_path)

        # Example of incorrect input type
        # invalid_input = _resolve_path_relative_to_project_root(123)
        # print(invalid_input)

    except (FileNotFoundError, TypeError) as e:
        print(f"Error: {e}")
    except NameError:
         print("Error: PROJECT_ROOT_PATH is not defined correctly for the example usage.")
