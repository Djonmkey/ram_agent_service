import asyncio
import os
import sys
import json
from datetime import datetime
import threading
from pathlib import Path
import time
import queue # Keep queue if needed elsewhere, otherwise remove
import argparse # <-- Import argparse

from startup import on_startup_dispatcher

# Add the event_listeners directory to the path
# Ensure this path is correct relative to where main.py is run
event_listeners_dir = os.path.join(os.path.dirname(__file__), 'event_listeners')
if event_listeners_dir not in sys.path:
    sys.path.append(event_listeners_dir)

# Import the main function from input_triggers_main.py
# Make sure input_triggers_main doesn't rely on UI elements
try:
    from input_triggers_main import main as input_triggers_main, listeners
except ImportError as e:
    print(f"Error importing from input_triggers_main: {e}")
    print("Please ensure input_triggers_main.py exists and is accessible.")
    sys.exit(1)

# Import the GPT handler - ensure gpt_thread doesn't rely on UI
try:
    from gpt_thread import get_gpt_handler
except ImportError as e:
    print(f"Error importing from gpt_thread: {e}")
    print("Please ensure gpt_thread.py exists and is accessible.")
    sys.exit(1)


# Global variables
log_directory = os.path.join(os.path.dirname(__file__), 'logs')
# current_conversations might not be needed without the UI,
# but keep it for now as the logger uses it.
current_conversations = {}

# --- ConversationLogger class remains the same ---
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

        # Use absolute path for log_directory consistently
        abs_log_directory = os.path.abspath(log_directory)
        log_path = os.path.join(abs_log_directory, event_listener_name, year, month, day)
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
            print(f"Logged conversation for {event_listener_name} to {log_file}")
        except IOError as e:
            print(f"Error writing log file {log_file}: {e}")
            return None # Indicate failure
        except Exception as e:
             print(f"An unexpected error occurred during logging: {e}")
             return None # Indicate failure


        # Update the current conversation (optional, might remove if not needed elsewhere)
        # Consider if this global state is truly necessary or if it can be managed differently
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
        logs = []
        # Use absolute path for log_directory consistently
        abs_log_directory = os.path.abspath(log_directory)

        # Define the base directory to search
        base_dir = os.path.join(abs_log_directory, event_listener_name) if event_listener_name else abs_log_directory

        if not os.path.exists(base_dir):
            print(f"Log directory not found: {base_dir}")
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

# --- patch_gpt_handler function remains the same ---
def patch_gpt_handler():
    """Patch the GPT handler to log conversations."""
    try:
        handler = get_gpt_handler() # Get instance once
        original_ask_gpt = handler.ask_gpt
        original_ask_gpt_sync = handler.ask_gpt_sync
    except Exception as e:
        print(f"Failed to get GPT handler for patching: {e}")
        # Decide how to handle this - exit, or continue without patching?
        # For now, let's print an error and potentially let it fail later.
        return # Stop patching if handler cannot be obtained

    def determine_caller_name():
        """Helper to determine the event listener name from the call stack."""
        # Consider adding caching or a more robust way if performance becomes an issue
        try:
            frame = sys._getframe(2) # Go back 2 frames to get the caller of the patched function
            event_listener_name = "UnknownListener" # More specific default
            # Limit stack walk depth to prevent infinite loops in weird scenarios
            max_depth = 10
            depth = 0
            while frame and depth < max_depth:
                # Check if 'self' exists and has a 'name' attribute (common pattern)
                instance = frame.f_locals.get('self')
                if instance:
                    # Check common patterns for listener names
                    if hasattr(instance, 'name') and isinstance(instance.name, str):
                        event_listener_name = instance.name
                        break
                    elif hasattr(instance, '__class__') and hasattr(instance.__class__, '__name__'):
                         # Fallback to class name if 'name' attribute isn't present/valid
                         event_listener_name = instance.__class__.__name__
                         # Potentially break here too, depending on desired specificity
                         # break

                # Check if called from a module-level function within listeners
                # This check might be fragile, relying on a specific global variable name
                elif 'event_listener_name' in frame.f_globals:
                     event_listener_name = frame.f_globals['event_listener_name']
                     break

                frame = frame.f_back # Move up the call stack
                depth += 1

            if frame is None or depth == max_depth:
                 print(f"Warning: Could not determine specific caller name, using '{event_listener_name}'.")

            return event_listener_name
        except Exception as e:
            # Log the specific error for debugging
            print(f"Error determining caller name: {e.__class__.__name__}: {e}")
            return "ErrorDeterminingCaller"


    def patched_ask_gpt(prompt, callback=None):
        """Patched version of ask_gpt that logs conversations."""
        begin_time = datetime.now()
        # Determine caller name *before* the async operation if possible
        event_listener_name = determine_caller_name()

        def wrapped_callback(response):
            """Wrap the callback to log the conversation."""
            # Log using the name determined before the async call
            log_file = ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
            if not log_file:
                 print(f"Warning: Failed to log conversation for {event_listener_name}") # Add warning if logging fails

            if callback:
                try:
                    callback(response)
                except Exception as e:
                    # Log the exception from the original callback
                    print(f"Error in original callback for {event_listener_name}: {e.__class__.__name__}: {e}")
                    # Optionally, log this error to the conversation log as well or a separate error log

        # Call the original method with our wrapped callback
        # Ensure the original method is actually called
        try:
            return original_ask_gpt(prompt, wrapped_callback)
        except Exception as e:
            print(f"Error calling original ask_gpt for {event_listener_name}: {e}")
            # Handle the error appropriately, maybe call the callback with an error message
            if callback:
                callback(f"Error during GPT request: {e}")
            # Or re-raise the exception if the caller should handle it
            # raise

    def patched_ask_gpt_sync(prompt):
        """Patched version of ask_gpt_sync that logs conversations."""
        begin_time = datetime.now()
        event_listener_name = determine_caller_name()

        # Call the original method
        try:
            response = original_ask_gpt_sync(prompt)
        except Exception as e:
            print(f"Error in original ask_gpt_sync for {event_listener_name}: {e}")
            # Log the error attempt before re-raising or returning an error indicator
            ConversationLogger.log_conversation(event_listener_name, prompt, f"Error: {e}", begin_time)
            raise # Re-raise the exception so the caller knows it failed

        # Log the successful conversation
        log_file = ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
        if not log_file:
            print(f"Warning: Failed to log successful sync conversation for {event_listener_name}") # Add warning if logging fails
        return response

    # Replace the original methods with our patched versions
    try:
        # Ensure handler is not None before attempting to patch
        if handler:
            handler.ask_gpt = patched_ask_gpt
            handler.ask_gpt_sync = patched_ask_gpt_sync
            print("GPT handler patched successfully for logging.")
        else:
            print("Skipping GPT handler patching because handler instance is None.")
    except AttributeError as e:
         print(f"Failed to apply patches to GPT handler (AttributeError): {e}. Check if methods exist.")
    except Exception as e:
        print(f"Failed to apply patches to GPT handler: {e.__class__.__name__}: {e}")


# --- run_event_listeners function remains the same ---
async def run_event_listeners():
    """Run the event listeners in the background."""
    print("Creating log directory...")
    # Use absolute path and handle potential errors during creation
    abs_log_directory = os.path.abspath(log_directory)
    try:
        os.makedirs(abs_log_directory, exist_ok=True)
        print(f"Log directory ensured at: {abs_log_directory}")
    except OSError as e:
        print(f"Error creating log directory {abs_log_directory}: {e}. Logging might fail.")
        # Decide if this is critical enough to exit
        # sys.exit(1)


    print("Patching GPT handler for logging...")
    patch_gpt_handler()

    print("Starting event listeners...")
    try:
        # Ensure input_triggers_main is an async function if awaited
        if asyncio.iscoroutinefunction(input_triggers_main):
            await input_triggers_main()
        else:
            # If it's a regular function, run it directly (though the async setup suggests it should be async)
             print("Warning: input_triggers_main is not an async function, running synchronously.")
             input_triggers_main()
        print("Event listeners finished.")
    except Exception as e:
        print(f"Error running event listeners main function: {e.__class__.__name__}: {e}")
        # Consider more robust error handling or shutdown procedures here


# --- start_event_listeners_thread function remains the same ---
def start_event_listeners_thread():
    """Start the event listeners in a separate thread."""
    print("Starting event listeners thread...")
    listener_loop = None
    try:
        # Create a new event loop for the thread
        listener_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(listener_loop)
        listener_loop.run_until_complete(run_event_listeners())
    except Exception as e:
        print(f"Error running asyncio event loop in thread: {e.__class__.__name__}: {e}")
    finally:
        if listener_loop:
            listener_loop.close()
        print("Event listener thread finished.")


if __name__ == "__main__":
    # --- Agent Manifest Loading ---
    parser = argparse.ArgumentParser(description="Run the RAM Agent Service.")
    parser.add_argument(
        'manifest_file',
        nargs='?', # Makes the argument optional
        default='config/agent_manifest.json', # Default value if not provided
        help='Path to the agent manifest JSON file (relative to main.py location).'
    )
    args = parser.parse_args()

    # Construct the absolute path relative to this script's location
    script_dir = os.path.dirname(__file__)
    manifest_path_relative = args.manifest_file
    manifest_path_absolute = os.path.abspath(os.path.join(script_dir, manifest_path_relative))

    print(f"Attempting to load agent manifest from: {manifest_path_absolute}")

    agent_manifest_data = None
    if not os.path.exists(manifest_path_absolute):
        print(f"❌ ERROR: Agent manifest file not found at the expected location: {manifest_path_absolute}")
        # Decide if the application should exit if the manifest is critical
        print("Exiting due to missing agent manifest.")
        sys.exit(1)
    else:
        try:
            with open(manifest_path_absolute, 'r', encoding='utf-8') as f:
                agent_manifest_data = json.load(f)
            print("✅ Agent manifest loaded successfully.")
            # You can now use the agent_manifest_data dictionary
            # print(f"Manifest content: {agent_manifest_data}") # Optional: print content for debugging
        except json.JSONDecodeError as e:
            print(f"❌ ERROR: Failed to parse agent manifest file '{manifest_path_absolute}': {e}")
            print("Exiting due to invalid agent manifest.")
            sys.exit(1)
        except IOError as e:
            print(f"❌ ERROR: Could not read agent manifest file '{manifest_path_absolute}': {e}")
            print("Exiting due to agent manifest read error.")
            sys.exit(1)
        except Exception as e:
            print(f"❌ ERROR: An unexpected error occurred loading the agent manifest: {e}")
            print("Exiting due to unexpected error.")
            sys.exit(1)

    # --- End of Agent Manifest Loading ---


    print("Executing MCP startup dispatcher...")
    try:
        # Pass the loaded manifest data to the startup dispatcher if needed
        # on_startup_dispatcher(agent_manifest_data) # Example modification
        on_startup_dispatcher() # Keep original call if dispatcher doesn't need manifest yet
        print("MCP startup dispatcher finished.")
    except Exception as e:
        print(f"Error during MCP startup: {e}")
        sys.exit(1) # Exit if startup fails

    print("Initializing event listeners...")
    # Start the event listeners in a separate thread
    listener_thread = threading.Thread(target=start_event_listeners_thread, daemon=True, name="EventListenerThread") # Give the thread a name
    listener_thread.start()

    print("Main thread running. Event listeners started in background thread.")
    print("Press Ctrl+C to exit.")

    # Keep the main thread alive, otherwise the daemon thread might exit prematurely
    try:
        while listener_thread.is_alive():
            # Use join with a timeout for a slightly cleaner loop
            listener_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        print("\nCtrl+C received. Shutting down...")
        # Add any necessary cleanup for listeners or GPT handler here
        try:
            gpt_handler = get_gpt_handler()
            if gpt_handler:
                 print("Shutting down GPT handler...")
                 gpt_handler.shutdown()
        except Exception as e:
            print(f"Error during GPT handler shutdown: {e}")

        # Signal event listeners to stop if they have a mechanism for it
        # (Currently, they run until completion or error)
        print("Waiting for listener thread to finish...")
        # Wait a bit longer for the thread to potentially clean up after shutdown signals
        listener_thread.join(timeout=5.0)
        if listener_thread.is_alive():
             print("Warning: Listener thread did not exit cleanly.")

        print("Shutdown complete.")
    except Exception as e:
         print(f"\nAn unexpected error occurred in the main loop: {e}")
         # Perform similar shutdown procedures on unexpected errors
         # (Code duplication - consider a dedicated shutdown function)
         try:
            gpt_handler = get_gpt_handler()
            if gpt_handler:
                 print("Shutting down GPT handler due to error...")
                 gpt_handler.shutdown()
         except Exception as shutdown_e:
            print(f"Error during GPT handler shutdown after main loop error: {shutdown_e}")
         sys.exit(1) # Exit with error status

    # --- UI Creation and mainloop Removed ---
    # TODO: Start HTTP service for UI
