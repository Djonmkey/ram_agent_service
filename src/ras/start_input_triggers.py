# /Users/david/Documents/projects/ram_agent_service/src/ras/start_input_triggers.py
import asyncio
import os
import sys
import json
from datetime import datetime
import threading
import time # Keep time if needed by input_triggers_main or listeners
from typing import Optional, Dict, Any # Added for type hinting

# Add the event_listeners directory to the path relative to this file
# Assuming start_input_triggers.py is in the same dir as main.py
# --- This path manipulation might be redundant if input_triggers_main handles src path ---
# event_listeners_dir = os.path.join(os.path.dirname(__file__), 'event_listeners')
# if event_listeners_dir not in sys.path:
#     sys.path.append(event_listeners_dir)
# --- Consider removing the above if imports work via input_triggers_main's sys.path logic ---

# Import the main function from input_triggers_main.py
try:
    # Assuming input_triggers_main needs to be imported here now
    # Make sure input_triggers_main.py correctly adds src to sys.path
    from input_triggers.input_triggers_main import main as input_triggers_main, listeners
except ImportError as e:
    print(f"Error importing from input_triggers.input_triggers_main: {e}")
    print("Please ensure input_triggers_main.py exists in src/input_triggers and src is in sys.path.")
    sys.exit(1)

from .chat_thread import get_gpt_handler

# --- Globals moved from main.py ---
# log_directory will be set by initialize_input_triggers
log_directory = None
# current_conversations is used by ConversationLogger
current_conversations = {}

# --- ConversationLogger class moved from main.py ---
class ConversationLogger:
    """Handles logging of conversations from event listeners."""

    @staticmethod
    def log_conversation(event_listener_name, request, response, begin_time=None):
        """
        Log a conversation to a JSON file.

        Args:
            event_listener_name: Name of the event listener
            request: The request sent to the event listener
            response: The response from the event listener
            begin_time: Optional datetime when the request was sent. If None, current time is used.
        """
        global log_directory, current_conversations # Ensure we use the module globals

        if not log_directory:
             print("Error: Log directory not initialized in ConversationLogger.")
             return None

        # Record end time
        end_time = datetime.now()

        # If begin_time wasn't provided, use end_time (less accurate but prevents errors)
        if begin_time is None:
            begin_time = end_time

        # Calculate duration in seconds
        duration = (end_time - begin_time).total_seconds()

        # Create the log directory structure
        year = end_time.strftime("%Y")
        month = end_time.strftime("%m")
        day = end_time.strftime("%d")
        timestamp = end_time.strftime("%H_%M_%S_%f")[:-3]  # Hour, minute, second, millisecond

        # Use the globally set absolute log_directory
        log_path = os.path.join(log_directory, event_listener_name, year, month, day)
        try:
            os.makedirs(log_path, exist_ok=True)
        except OSError as e:
            print(f"Error creating log directory {log_path}: {e}")
            return None # Indicate failure

        # Create the log file path
        log_file = os.path.join(log_path, f"{timestamp}_conversation.json")

        # Create the log data
        log_data = {
            "timestamp": end_time.isoformat(),
            "begin_time": begin_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration,
            "event_listener": event_listener_name,
            "request": request,
            "response": response
        }

        # Write the log data to the file
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)
            # print(f"Logged conversation for {event_listener_name} to {log_file}") # Optional: reduce verbosity
        except IOError as e:
            print(f"Error writing log file {log_file}: {e}")
            return None # Indicate failure
        except Exception as e:
             print(f"An unexpected error occurred during logging: {e}")
             return None # Indicate failure

        # Update the current conversation (optional, might remove if not needed elsewhere)
        current_conversations[event_listener_name] = {
            "timestamp": end_time.isoformat(),
            "begin_time": begin_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration,
            "request": request,
            "response": response,
            "log_file": log_file
        }

        return log_file

    @staticmethod
    def get_conversation_logs(event_listener_name=None, limit=10):
        """
        Get the most recent conversation logs. (May not be needed without UI)

        Args:
            event_listener_name: Optional name of the event listener to filter by
            limit: Maximum number of logs to return

        Returns:
            A list of log file paths
        """
        global log_directory # Ensure we use the module global
        logs = []

        if not log_directory:
             print("Error: Log directory not initialized in ConversationLogger.")
             return logs

        # Define the base directory to search
        base_dir = os.path.join(log_directory, event_listener_name) if event_listener_name else log_directory

        if not os.path.exists(base_dir):
            # print(f"Log directory not found: {base_dir}") # Less verbose
            return logs

        # Walk through the directory structure
        try:
            # Use scandir for potentially better performance on large directories
            for entry in os.scandir(base_dir):
                if entry.is_dir():
                    # Recursively search subdirectories (year, month, day)
                    for root, _, files in os.walk(entry.path):
                         for file in files:
                            if file.endswith("_conversation.json"):
                                logs.append(os.path.join(root, file))
                elif entry.is_file() and entry.name.endswith("_conversation.json") and not event_listener_name:
                    # Handle logs directly in the base log_directory if no specific listener is given
                    logs.append(entry.path)

        except OSError as e:
            print(f"Error scanning directory {base_dir}: {e}")
            return [] # Return empty list on error

        # Sort logs by modification time (newest first)
        try:
            # Filter out potential non-existent files before sorting
            valid_logs = [log for log in logs if os.path.exists(log)]
            valid_logs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        except OSError as e:
            print(f"Error getting modification time for sorting logs: {e}")
            # Attempt to continue with potentially unsorted logs or return empty
            return []

        # Limit the number of logs
        return valid_logs[:limit]

    @staticmethod
    def load_conversation_log(log_file):
        """
        Load a conversation log from a file. (May not be needed without UI)

        Args:
            log_file: Path to the log file

        Returns:
            The conversation log data or None if loading fails
        """
        # Check existence using the provided path directly
        if not os.path.exists(log_file):
            print(f"Log file not found: {log_file}")
            return None

        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from {log_file}: {e}")
            return None
        except IOError as e:
            print(f"Error reading log file {log_file}: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred loading log {log_file}: {e}")
            return None

# --- patch_gpt_handler function moved from main.py ---
def patch_gpt_handler(agent_config_data: Dict[str, Any]):
    """Patch the GPT handler to log conversations."""
    try:
        handler = get_gpt_handler(agent_config_data) # Get instance once
        if not handler: # Check if handler was successfully retrieved
             print("Skipping GPT handler patching because handler instance is None.")
             return
        original_ask_gpt = handler.ask_gpt
        original_ask_gpt_sync = handler.ask_gpt_sync
    except Exception as e:
        print(f"Failed to get GPT handler for patching: {e}")
        return # Stop patching if handler cannot be obtained

    def determine_caller_name():
        """Helper to determine the event listener name from the call stack."""
        try:
            frame = sys._getframe(2) # Go back 2 frames to get the caller of the patched function
            event_listener_name = "UnknownListener" # More specific default
            max_depth = 10
            depth = 0
            while frame and depth < max_depth:
                instance = frame.f_locals.get('self')
                if instance:
                    # Check if it's an InputTrigger instance and has a name
                    if hasattr(instance, 'name') and isinstance(instance.name, str):
                        # Check if it inherits from InputTrigger to be more specific
                        try:
                            # Need InputTrigger class definition available here
                            from input_triggers.input_triggers import InputTrigger
                            if isinstance(instance, InputTrigger):
                                event_listener_name = instance.name
                                break
                        except ImportError:
                            # Fallback if InputTrigger cannot be imported here
                            event_listener_name = instance.name # Use name if found
                            # break # Decide if any object with 'name' is okay

                    # Fallback to class name if 'name' attribute isn't suitable
                    elif hasattr(instance, '__class__') and hasattr(instance.__class__, '__name__'):
                         event_listener_name = instance.__class__.__name__
                         # break # Decide if class name is specific enough

                # Check globals (less reliable)
                elif 'event_listener_name' in frame.f_globals:
                     event_listener_name = frame.f_globals['event_listener_name']
                     break

                frame = frame.f_back
                depth += 1

            if frame is None or depth == max_depth:
                 # print(f"Warning: Could not determine specific caller name, using '{event_listener_name}'.") # Less verbose
                 pass

            return event_listener_name
        except Exception as e:
            print(f"Error determining caller name: {e.__class__.__name__}: {e}")
            return "ErrorDeterminingCaller"

    def patched_ask_gpt(prompt, callback=None):
        """Patched version of ask_gpt that logs conversations."""
        begin_time = datetime.now()
        event_listener_name = determine_caller_name()

        def wrapped_callback(response):
            """Wrap the callback to log the conversation."""
            log_file = ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
            # if not log_file: # Less verbose
            #      print(f"Warning: Failed to log conversation for {event_listener_name}")

            if callback:
                try:
                    callback(response)
                except Exception as e:
                    print(f"Error in original callback for {event_listener_name}: {e.__class__.__name__}: {e}")

        try:
            # Call the original method stored earlier
            return original_ask_gpt(prompt, wrapped_callback)
        except Exception as e:
            print(f"Error calling original ask_gpt for {event_listener_name}: {e}")
            if callback:
                callback(f"Error during GPT request: {e}")

    def patched_ask_gpt_sync(prompt):
        """Patched version of ask_gpt_sync that logs conversations."""
        begin_time = datetime.now()
        event_listener_name = determine_caller_name()

        try:
            # Call the original method stored earlier
            response = original_ask_gpt_sync(prompt)
        except Exception as e:
            print(f"Error in original ask_gpt_sync for {event_listener_name}: {e}")
            ConversationLogger.log_conversation(event_listener_name, prompt, f"Error: {e}", begin_time)
            raise # Re-raise the original exception

        log_file = ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
        # if not log_file: # Less verbose
        #     print(f"Warning: Failed to log successful sync conversation for {event_listener_name}")
        return response

    try:
        # Apply the patches
        handler.ask_gpt = patched_ask_gpt
        handler.ask_gpt_sync = patched_ask_gpt_sync
        print("GPT handler patched successfully for logging.")
    except AttributeError as e:
         print(f"Failed to apply patches to GPT handler (AttributeError): {e}. Check if methods exist.")
    except Exception as e:
        print(f"Failed to apply patches to GPT handler: {e.__class__.__name__}: {e}")


# --- run_event_listeners function updated ---
async def run_event_listeners(agent_manifest_data: Optional[Dict[str, Any]] = None):
    """
    Run the event listeners main function, passing manifest data.

    Args:
        agent_manifest_data: Optional dictionary containing agent manifest data.
    """
    global log_directory # Ensure we use the module global

    print("Creating log directory (if needed)...")
    # Log directory path is already absolute and set globally
    try:
        # The logger will create subdirs; just ensure the base exists if needed
        # os.makedirs(log_directory, exist_ok=True) # This might be redundant if main ensures it
        print(f"Log directory set to: {log_directory}")
    except OSError as e:
        print(f"Error related to log directory {log_directory}: {e}. Logging might fail.")
        # Decide if this is critical enough to exit
        # sys.exit(1) # Probably not, let logger handle errors

    print("Patching GPT handler for logging...")
    patch_gpt_handler()

    print("Starting event listeners...")
    try:
        # Ensure input_triggers_main is an async function if awaited
        if asyncio.iscoroutinefunction(input_triggers_main):
            # Pass the agent_manifest_data to the main function
            await input_triggers_main(agent_manifest_data=agent_manifest_data)
        else:
             print("Error: input_triggers_main is not an async function and cannot be awaited.")
             # Cannot easily pass data if it's not async and run in loop
             # Consider making input_triggers_main async mandatory
             # Or run it synchronously outside the loop (but that blocks)
             # input_triggers_main() # Old way, cannot pass data easily here
        print("Event listeners finished.")
    except Exception as e:
        print(f"Error running event listeners main function: {e.__class__.__name__}: {e}")
        import traceback
        traceback.print_exc() # Print stack trace for debugging


# --- start_event_listeners_thread function updated ---
def start_event_listeners_thread(agent_manifest_data: Optional[Dict[str, Any]] = None):
    """
    Start the event listeners in a separate thread, managing the event loop.

    Args:
        agent_manifest_data: Optional dictionary containing agent manifest data.
    """
    print("Starting event listeners thread...")
    listener_loop = None
    try:
        # Create a new event loop for the thread
        listener_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(listener_loop)
        # Pass agent_manifest_data to run_event_listeners
        listener_loop.run_until_complete(run_event_listeners(agent_manifest_data=agent_manifest_data))
    except Exception as e:
        print(f"Error running asyncio event loop in thread: {e.__class__.__name__}: {e}")
        import traceback
        traceback.print_exc() # Print stack trace for debugging
    finally:
        if listener_loop:
            try:
                # Gracefully stop the loop before closing
                if listener_loop.is_running():
                    # Gather pending tasks and cancel them before stopping
                    tasks = asyncio.all_tasks(loop=listener_loop)
                    for task in tasks:
                        task.cancel()
                    # Allow tasks to finish cancellation
                    listener_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    listener_loop.stop()
                # Close the loop
                listener_loop.close()
                print("Event loop closed.")
            except Exception as loop_close_e:
                 print(f"Error closing event loop: {loop_close_e}")
        print("Event listener thread finished.")


# --- initialize_input_triggers function updated ---
def initialize_input_triggers(agent_manifest_data: Optional[Dict[str, Any]], log_dir_abs_path: str) -> threading.Thread:
    """
    Initializes and starts the event listeners in a background thread.

    Args:
        agent_manifest_data: The loaded agent manifest data.
        log_dir_abs_path: The absolute path to the main log directory.

    Returns:
        The started listener thread object.
    """
    global log_directory # Set the module-level global for other functions here
    log_directory = log_dir_abs_path

    print(f"Initializing event listeners (using manifest: {'loaded' if agent_manifest_data else 'not loaded'}, log path: {log_directory})...")

    # Create the thread, passing agent_manifest_data to the target function
    listener_thread = threading.Thread(
        target=start_event_listeners_thread,
        args=(agent_manifest_data,), # Pass manifest data as argument tuple
        daemon=True,
        name="EventListenerThread" # Give the thread a name
    )
    listener_thread.start()

    return listener_thread # Return the thread object to the caller (main.py)

