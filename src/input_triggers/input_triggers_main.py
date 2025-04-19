import asyncio
import importlib
import os
import sys
from typing import List, Dict, Any, Optional, Type
from pathlib import Path # Use pathlib for better path manipulation

# Determine the absolute path to the 'src' directory
# Assumes this file is located at src/input_triggers/input_triggers_main.py
# Goes up two levels: input_triggers -> src
SRC_DIR = Path(__file__).resolve().parent.parent
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

def discover_event_listeners() -> List[Type[InputTrigger]]:
    """
    Discover and load all event listener implementations within the src directory.

    Returns:
        A list of EventListener classes.
    """
    listener_classes = []
    src_path = SRC_DIR # Use the calculated SRC_DIR Path object

    print(f"Searching for listeners starting from: {src_path}")

    # Walk through the src directory
    for root, dirs, files in os.walk(src_path):
        # Skip __pycache__ and hidden directories for efficiency
        dirs[:] = [d for d in dirs if not d.startswith('__') and not d.startswith('.')]

        current_path = Path(root)

        for file in files:
            file_path = current_path / file
            # Skip non-Python files, __init__.py, and this file itself
            if (not file.endswith('.py') or
                file == '__init__.py' or
                file_path.resolve() == Path(__file__).resolve()):
                continue

            # Calculate the module path relative to src_path
            try:
                # Get path relative to src_dir
                relative_path = file_path.relative_to(src_path)
                # Convert path separators to dots and remove .py extension
                module_path_parts = list(relative_path.parts)
                module_path_parts[-1] = module_path_parts[-1][:-3] # Remove .py
                module_path = '.'.join(module_path_parts)

                # Skip if module path is empty (shouldn't happen with checks)
                if not module_path:
                    continue

                # Dynamically import the module and look for EventListener subclasses
                module = importlib.import_module(module_path)
                for attr_name in dir(module):
                    try:
                        attr = getattr(module, attr_name)

                        # Check if it's a class, a subclass of EventListener,
                        # and not EventListener itself or an abstract class
                        if (isinstance(attr, type) and
                            issubclass(attr, InputTrigger) and
                            attr is not InputTrigger and
                            not getattr(attr, '__abstractmethods__', False)): # Check if it's concrete
                            if attr not in listener_classes: # Avoid duplicates
                                listener_classes.append(attr)
                                print(f"  Discovered listener class: {attr.__name__} from {module_path}")
                    except Exception as inner_e:
                        # Catch errors during attribute access or checks within a module
                        print(f"Warning: Error inspecting attribute '{attr_name}' in module {module_path}: {inner_e}")

            except (ImportError, AttributeError, ModuleNotFoundError) as e:
                # Catch errors during module import
                print(f"Warning: Could not import or process module {module_path}: {e}")
            except Exception as e:
                 # Catch any other unexpected errors during file processing
                 print(f"Error processing file {file_path}: {e}")

    return listener_classes

async def load_event_listeners():
    """
    Load and initialize all discovered event listeners.
    """
    print("Discovering event listeners...")
    listener_classes = discover_event_listeners()

    if not listener_classes:
        print("No concrete event listener implementations found.")
        return

    print(f"\nFound {len(listener_classes)} concrete event listener class(es).")

    # Initialize each listener
    for listener_class in listener_classes:
        try:
            listener = listener_class() # Instantiate the class
            listener_name = listener.name # Get name *after* instantiation
            print(f"Initializing '{listener_name}' ({listener_class.__name__})...")
            await listener.initialize()
            listeners[listener_name] = listener
            print(f"Successfully initialized '{listener_name}'.")
        except Exception as e:
            print(f"ERROR: Failed to initialize {listener_class.__name__}: {e}")
            # Optionally, add more detailed error logging here (e.g., traceback)

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


async def main():
    """
    Main entry point for the application.
    Loads, starts, and manages event listeners.
    """
    try:
        # Load and start all event listeners
        await load_event_listeners()
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
        gpt_handler.shutdown()
        print("Shutdown complete.")

# Example of direct usage
if __name__ == "__main__":
    # Set up asyncio event loop and run the main function
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # This might catch a Ctrl+C before asyncio.run() fully handles it
        print("\nShutdown initiated from __main__.")
