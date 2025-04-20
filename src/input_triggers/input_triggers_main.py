# /Users/david/Documents/projects/ram_agent_service/src/input_triggers/input_triggers_main.py
import asyncio
import importlib
import os
import sys
import json # Added for loading agent configs
from typing import List, Dict, Any, Optional, Type
from pathlib import Path # Use pathlib for better path manipulation

# Determine the absolute path to the 'src' directory
# Assumes this file is located at src/input_triggers/input_triggers_main.py
# Goes up two levels: input_triggers -> src
SRC_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SRC_DIR.parent # Define project root for resolving relative paths

# Add src directory to sys.path to ensure imports work correctly,
# especially for dynamically loaded modules. Insert at the beginning
# to prioritize it.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Now imports relative to src should work
from input_triggers.input_triggers import InputTrigger # Adjusted import path
from gpt_thread import get_gpt_handler

# Dictionary to store loaded event listeners
listeners: Dict[str, InputTrigger] = {}

def ask_gpt(prompt: str) -> str:
    """
    Send a request to the GPT model and wait for the response.
    This is a synchronous wrapper around the asynchronous GPT handler.

    Args:
        prompt: The prompt to send to the GPT model.

    Returns:
        The response from the GPT model.
    """
    gpt_handler = get_gpt_handler()
    return gpt_handler.ask_gpt_sync(prompt)

def ask_gpt_async(prompt: str, callback=None):
    """
    Queue a request to the GPT model without waiting for the response.

    Args:
        prompt: The prompt to send to the GPT model.
        callback: Optional callback function to call with the response.
    """
    gpt_handler = get_gpt_handler()
    gpt_handler.ask_gpt(prompt, callback)

# --- discover_event_listeners function removed ---

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

    print("Loading input triggers based on agent manifest...")

    if not agent_manifest_data or "agents" not in agent_manifest_data:
        print("ERROR: Agent manifest data is missing or does not contain an 'agents' list.")
        return

    loaded_listener_count = 0
    processed_agents = 0

    for agent_info in agent_manifest_data.get("agents", []):
        processed_agents += 1
        agent_name = agent_info.get("name", f"Agent_{processed_agents}") # Use name or generate one
        config_file_relative = agent_info.get("agent_config_file")

        if not config_file_relative:
            print(f"WARNING: Agent '{agent_name}' is missing the 'agent_config_file' key in the manifest. Skipping.")
            continue

        # Construct absolute path relative to the project root
        config_file_absolute = PROJECT_ROOT / config_file_relative

        print(f"\nProcessing Agent: '{agent_name}'")
        print(f"  Attempting to load agent config: {config_file_absolute}")

        if not config_file_absolute.exists():
            print(f"  ❌ ERROR: Agent config file not found: {config_file_absolute}")
            continue
        if not config_file_absolute.is_file():
            print(f"  ❌ ERROR: Agent config path is not a file: {config_file_absolute}")
            continue

        # Load the agent-specific configuration JSON
        try:
            with open(config_file_absolute, 'r', encoding='utf-8') as f:
                agent_config_data = json.load(f)
            print(f"  ✅ Successfully loaded agent config for '{agent_name}'.")
        except json.JSONDecodeError as e:
            print(f"  ❌ ERROR: Failed to parse JSON from agent config file '{config_file_absolute}': {e}")
            continue
        except IOError as e:
            print(f"  ❌ ERROR: Could not read agent config file '{config_file_absolute}': {e}")
            continue
        except Exception as e:
            print(f"  ❌ ERROR: An unexpected error occurred loading agent config '{config_file_absolute}': {e}")
            continue

        # Load input triggers specified in this agent's config
        input_triggers_list = agent_config_data.get("input_triggers", [])
        if not isinstance(input_triggers_list, list):
            print(f"  WARNING: 'input_triggers' in config for agent '{agent_name}' is not a list. Skipping triggers for this agent.")
            continue

        if not input_triggers_list:
            print(f"  No 'input_triggers' found or list is empty in the config for agent '{agent_name}'.")
            continue

        print(f"  Found {len(input_triggers_list)} input trigger(s) specified for '{agent_name}'.")

        for i, trigger_info in enumerate(input_triggers_list):
            trigger_index_str = f"Trigger #{i+1}" # For logging
            if not isinstance(trigger_info, dict):
                print(f"  WARNING: Skipping {trigger_index_str} for agent '{agent_name}' - item in 'input_triggers' is not a dictionary.")
                continue

            module_path_str = trigger_info.get("python_code_module")
            if not module_path_str or not isinstance(module_path_str, str):
                print(f"  WARNING: Skipping {trigger_index_str} for agent '{agent_name}' due to missing or invalid 'python_code_module'.")
                continue

            # --- Get Trigger-Specific Config and Secrets Paths ---
            trigger_config_relative_path = trigger_info.get("input_trigger_config_file")
            if not trigger_config_relative_path or not isinstance(trigger_config_relative_path, str):
                print(f"  WARNING: Skipping {trigger_index_str} ('{module_path_str}') for agent '{agent_name}' due to missing or invalid 'input_trigger_config_file'.")
                continue

            trigger_secrets_relative_path = trigger_info.get("input_trigger_secrets_file")
            if not trigger_secrets_relative_path or not isinstance(trigger_secrets_relative_path, str):
                print(f"  WARNING: Skipping {trigger_index_str} ('{module_path_str}') for agent '{agent_name}' due to missing or invalid 'input_trigger_secrets_file'.")
                continue

            # Construct absolute paths relative to project root
            trigger_config_absolute_path = PROJECT_ROOT / trigger_config_relative_path
            trigger_secrets_absolute_path = PROJECT_ROOT / trigger_secrets_relative_path

            print(f"    {trigger_index_str}: Module '{module_path_str}'")
            print(f"      Config Path: {trigger_config_absolute_path}")
            print(f"      Secrets Path: {trigger_secrets_absolute_path}")

            # --- Load Trigger-Specific Config ---
            trigger_config_data = None
            if not trigger_config_absolute_path.exists():
                 print(f"      ❌ ERROR: Trigger config file not found: {trigger_config_absolute_path}")
                 continue
            if not trigger_config_absolute_path.is_file():
                 print(f"      ❌ ERROR: Trigger config path is not a file: {trigger_config_absolute_path}")
                 continue
            try:
                with open(trigger_config_absolute_path, 'r', encoding='utf-8') as f:
                    trigger_config_data = json.load(f)
                print(f"      ✅ Loaded trigger config.")
            except json.JSONDecodeError as e:
                print(f"      ❌ ERROR: Failed to parse JSON from trigger config file '{trigger_config_absolute_path}': {e}")
                continue
            except IOError as e:
                print(f"      ❌ ERROR: Could not read trigger config file '{trigger_config_absolute_path}': {e}")
                continue
            except Exception as e:
                print(f"      ❌ ERROR: An unexpected error occurred loading trigger config '{trigger_config_absolute_path}': {e}")
                continue

            # --- Load Trigger-Specific Secrets ---
            trigger_secrets_data = None
            if not trigger_secrets_absolute_path.exists():
                 print(f"      ❌ ERROR: Trigger secrets file not found: {trigger_secrets_absolute_path}")
                 continue
            if not trigger_secrets_absolute_path.is_file():
                 print(f"      ❌ ERROR: Trigger secrets path is not a file: {trigger_secrets_absolute_path}")
                 continue
            try:
                with open(trigger_secrets_absolute_path, 'r', encoding='utf-8') as f:
                    trigger_secrets_data = json.load(f)
                print(f"      ✅ Loaded trigger secrets.")
            except json.JSONDecodeError as e:
                print(f"      ❌ ERROR: Failed to parse JSON from trigger secrets file '{trigger_secrets_absolute_path}': {e}")
                continue
            except IOError as e:
                print(f"      ❌ ERROR: Could not read trigger secrets file '{trigger_secrets_absolute_path}': {e}")
                continue
            except Exception as e:
                print(f"      ❌ ERROR: An unexpected error occurred loading trigger secrets '{trigger_secrets_absolute_path}': {e}")
                continue

            # --- Import Module and Find Class ---
            print(f"    Attempting to load trigger module: {module_path_str}")
            try:
                module = importlib.import_module(module_path_str)
                input_trigger_class = None
                for attr_name in dir(module):
                    try:
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and
                            issubclass(attr, InputTrigger) and
                            attr is not InputTrigger and
                            not getattr(attr, '__abstractmethods__', False)):
                            input_trigger_class = attr
                            print(f"      Found listener class: {input_trigger_class.__name__}")
                            break
                    except Exception as inner_e:
                        print(f"      Warning: Error inspecting attribute '{attr_name}' in module {module_path_str}: {inner_e}")

                if not input_trigger_class:
                    print(f"    ❌ ERROR: No concrete InputTrigger subclass found in module {module_path_str}.")
                    continue

                # --- Instantiate the listener class with specific config and secrets ---
                try:
                    # Pass agent_name, loaded trigger config, and loaded trigger secrets
                    listener = input_trigger_class(
                        agent_name=agent_name,
                        trigger_config_data=trigger_config_data,
                        trigger_secrets=trigger_secrets_data
                    )

                    # Unique listener name for the global dictionary
                    listener_name = f"{agent_name}_{listener.name}" # Use agent name prefix for uniqueness

                    if listener_name in listeners:
                         print(f"    ❌ ERROR: Duplicate listener instance name '{listener_name}' detected. Skipping this instance.")
                         continue

                    print(f"    Initializing '{listener_name}' ({input_trigger_class.__name__})...")
                    await listener.initialize()
                    listeners[listener_name] = listener
                    loaded_listener_count += 1
                    print(f"    ✅ Successfully initialized '{listener_name}' for agent '{agent_name}'.")

                except TypeError as te:
                    # Catch if the listener __init__ doesn't accept the expected args
                    print(f"    ❌ ERROR: Failed to instantiate {input_trigger_class.__name__} (TypeError): {te}. Check its __init__ method signature (expected agent_name, trigger_config_data, trigger_secrets).")
                except Exception as e:
                    print(f"    ❌ ERROR: Failed to initialize {input_trigger_class.__name__} for agent '{agent_name}': {e}")
                    # Optionally, add more detailed error logging here (e.g., traceback)

            except (ImportError, ModuleNotFoundError) as e:
                print(f"    ❌ ERROR: Could not import trigger module '{module_path_str}': {e}")
            except Exception as e:
                 print(f"    ❌ ERROR: Unexpected error processing trigger module '{module_path_str}': {e}")

    print(f"\nFinished processing {processed_agents} agent(s).")
    if loaded_listener_count > 0:
        print(f"✅ Successfully loaded and initialized {loaded_listener_count} input trigger(s) in total.")
    else:
        print("⚠️ No input triggers were successfully loaded.")


async def start_event_listeners():
    """
    Start all successfully initialized event listeners.
    """
    if not listeners:
        print("No listeners were successfully initialized to start.")
        return

    print(f"\nStarting {len(listeners)} initialized event listener(s)...")

    start_tasks = []
    # Start each listener concurrently
    for name, listener in listeners.items():
        print(f"Creating start task for '{name}'...")
        start_tasks.append(asyncio.create_task(listener.start(), name=f"start_{name}"))

    # Wait for all start tasks to complete (or raise exceptions)
    if start_tasks:
        try:
            # Use gather to run them concurrently and wait
            results = await asyncio.gather(*start_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                 task_name = start_tasks[i].get_name().replace("start_", "")
                 if isinstance(result, Exception):
                     print(f"ERROR: Failed to start '{task_name}': {result}")
                 else:
                     print(f"Successfully started '{task_name}'.")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during listener startup: {e}")


async def stop_event_listeners():
    """
    Stop all running event listeners.
    """
    if not listeners:
        return # Nothing to stop

    print(f"\nStopping {len(listeners)} event listener(s)...")

    stop_tasks = []
    # Stop each listener concurrently
    for name, listener in listeners.items():
         print(f"Creating stop task for '{name}'...")
         # Ensure stop is awaitable, handle potential errors during stop
         stop_tasks.append(asyncio.create_task(listener.stop(), name=f"stop_{name}"))

    # Wait for all stop tasks to complete (or raise exceptions)
    if stop_tasks:
        try:
            results = await asyncio.gather(*stop_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                 task_name = stop_tasks[i].get_name().replace("stop_", "")
                 if isinstance(result, Exception):
                     print(f"ERROR: Error stopping '{task_name}': {result}")
                 else:
                     print(f"Successfully stopped '{task_name}'.")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred during listener shutdown: {e}")


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
        await start_event_listeners()

        if not listeners:
             print("No listeners running. Exiting.")
             return # Exit if no listeners started

        # Keep the main thread alive while listeners run in the background
        print("\nAll available event listeners started. Press Ctrl+C to exit.")
        while True:
            # Check if any listener tasks have unexpectedly stopped (optional)
            # Add more sophisticated monitoring if needed
            await asyncio.sleep(3600) # Sleep for a long time, woken by Ctrl+C

    except asyncio.CancelledError:
         print("Main task cancelled.") # Handle cancellation if running within another loop
    except KeyboardInterrupt:
        print("\nCtrl+C received. Shutting down gracefully...")
    finally:
        # Ensure proper cleanup
        print("Initiating listener shutdown...")
        await stop_event_listeners()

        # Clean shutdown of GPT handler
        print("Shutting down GPT handler...")
        gpt_handler = get_gpt_handler()
        if gpt_handler: # Check if handler exists before shutdown
            gpt_handler.shutdown()
        print("Shutdown complete.")

# Example of direct usage (less likely now it's called from elsewhere)
if __name__ == "__main__":
    print("ERROR: Running input_triggers_main directly is not supported with the new manifest-driven loading.")
    print("Please run the main application entry point (e.g., ras/main.py) which provides the manifest.")
