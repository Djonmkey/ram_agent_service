import asyncio
import os
import sys
import json
from datetime import datetime
import threading
from pathlib import Path
import time
import queue # Keep queue if needed elsewhere, otherwise remove
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

        log_path = os.path.join(log_directory, event_listener_name, year, month, day)
        os.makedirs(log_path, exist_ok=True)

        # Create the log file
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
        except Exception as e:
             print(f"An unexpected error occurred during logging: {e}")


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
        logs = []

        # Define the base directory to search
        base_dir = os.path.join(log_directory, event_listener_name) if event_listener_name else log_directory

        if not os.path.exists(base_dir):
            return logs

        # Walk through the directory structure
        try:
            for root, dirs, files in os.walk(base_dir):
                for file in files:
                    if file.endswith("_conversation.json"):
                        logs.append(os.path.join(root, file))
        except OSError as e:
            print(f"Error walking directory {base_dir}: {e}")
            return [] # Return empty list on error

        # Sort logs by modification time (newest first)
        try:
            logs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        except OSError as e:
            print(f"Error getting modification time for sorting logs: {e}")
            # Attempt to continue with potentially unsorted logs or return empty
            return []


        # Limit the number of logs
        return logs[:limit]

    @staticmethod
    def load_conversation_log(log_file):
        """
        Load a conversation log from a file. (May not be needed without UI)

        Args:
            log_file: Path to the log file

        Returns:
            The conversation log data or None if loading fails
        """
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


# Monkey patch the GPT handler to log conversations
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
        try:
            frame = sys._getframe(2) # Go back 2 frames to get the caller of the patched function
            event_listener_name = "Unknown"
            while frame:
                # Check if 'self' exists and has a 'name' attribute
                if 'self' in frame.f_locals:
                    instance = frame.f_locals['self']
                    # Check common patterns for listener names
                    if hasattr(instance, 'name'):
                        event_listener_name = instance.name
                        break
                    elif hasattr(instance, '__class__') and hasattr(instance.__class__, '__name__'):
                         # Fallback to class name if 'name' attribute isn't present
                         event_listener_name = instance.__class__.__name__
                         break
                # Check if called from a module-level function within listeners
                elif 'event_listener_name' in frame.f_globals:
                     event_listener_name = frame.f_globals['event_listener_name']
                     break

                frame = frame.f_back # Move up the call stack
            return event_listener_name
        except Exception as e:
            print(f"Error determining caller name: {e}")
            return "ErrorDeterminingCaller"


    def patched_ask_gpt(prompt, callback=None):
        """Patched version of ask_gpt that logs conversations."""
        begin_time = datetime.now()
        event_listener_name = determine_caller_name()

        def wrapped_callback(response):
            """Wrap the callback to log the conversation."""
            ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
            if callback:
                try:
                    callback(response)
                except Exception as e:
                    print(f"Error in original callback for {event_listener_name}: {e}")

        # Call the original method with our wrapped callback
        return original_ask_gpt(prompt, wrapped_callback)

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
        ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
        return response

    # Replace the original methods with our patched versions
    try:
        handler.ask_gpt = patched_ask_gpt
        handler.ask_gpt_sync = patched_ask_gpt_sync
        print("GPT handler patched successfully for logging.")
    except Exception as e:
        print(f"Failed to apply patches to GPT handler: {e}")


async def run_event_listeners():
    """Run the event listeners in the background."""
    print("Creating log directory...")
    os.makedirs(log_directory, exist_ok=True)

    print("Patching GPT handler for logging...")
    patch_gpt_handler()

    print("Starting event listeners...")
    try:
        # Ensure input_triggers_main is an async function
        await input_triggers_main()
        print("Event listeners finished.")
    except Exception as e:
        print(f"Error running event listeners main function: {e}")
        # Consider more robust error handling or shutdown procedures here


def start_event_listeners_thread():
    """Start the event listeners in a separate thread."""
    print("Starting event listeners thread...")
    try:
        asyncio.run(run_event_listeners())
    except Exception as e:
        print(f"Error running asyncio event loop in thread: {e}")

if __name__ == "__main__":
    print("Executing MCP startup dispatcher...")
    try:
        on_startup_dispatcher()
        print("MCP startup dispatcher finished.")
    except Exception as e:
        print(f"Error during MCP startup: {e}")
        sys.exit(1) # Exit if startup fails

    print("Initializing event listeners...")
    # Start the event listeners in a separate thread
    listener_thread = threading.Thread(target=start_event_listeners_thread, daemon=True)
    listener_thread.start()

    print("Main thread running. Event listeners started in background thread.")
    print("Press Ctrl+C to exit.")

    # Keep the main thread alive, otherwise the daemon thread might exit prematurely
    # You might want a more sophisticated shutdown mechanism here
    try:
        while listener_thread.is_alive():
            time.sleep(1) # Keep main thread alive while listeners run
    except KeyboardInterrupt:
        print("\nCtrl+C received. Shutting down...")
        # Add any necessary cleanup for listeners or GPT handler here
        # e.g., get_gpt_handler().shutdown() if it exists and is needed
        print("Shutdown complete.")

    # --- UI Creation and mainloop Removed ---
    # TODO: Start HTTP service for UI
