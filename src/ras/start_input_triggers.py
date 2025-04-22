# /Users/david/Documents/projects/ram_agent_service/src/ras/start_input_triggers.py
import asyncio
import os
import sys
import json
from datetime import datetime
import threading
import time # Keep time if needed by input_triggers_main or listeners
from typing import Optional, Dict, Any, TYPE_CHECKING # Added for type hinting

# --- Path manipulation might be needed by input_triggers_main, keep its logic ---

# Import the main function from input_triggers_main.py
try:
    # input_triggers_main is now responsible for the core agent loop
    from input_triggers.input_triggers_main import main as input_triggers_main
except ImportError as e:
    print(f"Error importing from input_triggers.input_triggers_main: {e}")
    print("Please ensure input_triggers_main.py exists in src/input_triggers and src is in sys.path.")
    sys.exit(1)

# Import for type hinting and potentially for determine_caller_name
# Use TYPE_CHECKING to avoid circular imports if chat_thread imports this module indirectly
if TYPE_CHECKING:
    from ..chat_models.chat_model_openai import GPTThreadHandler # Assuming singleton removed from chat_thread
try:
    # Attempt to import for runtime checks in determine_caller_name
    # This helps identify the trigger instance calling the patched method
    from input_triggers.input_triggers import InputTrigger
except ImportError:
    # Define a dummy InputTrigger if it cannot be imported,
    # so isinstance check doesn't raise NameError.
    class InputTrigger: pass
    print("Warning: Could not import InputTrigger base class for type checking in determine_caller_name.")


# --- Globals ---
log_directory = None # Set by initialize_input_triggers
current_conversations = {} # Used by ConversationLogger

# --- ConversationLogger class ---
# (Keep as is, but added minor path sanitization for safety)
class ConversationLogger:
    """Handles logging of conversations from event listeners."""

    @staticmethod
    def log_conversation(event_listener_name, request, response, begin_time=None):
        """
        Log a conversation to a JSON file.

        Args:
            event_listener_name: Name of the event listener (should correspond to agent name or specific trigger)
            request: The request sent to the event listener
            response: The response from the event listener
            begin_time: Optional datetime when the request was sent. If None, current time is used.
        """
        global log_directory, current_conversations

        if not log_directory:
             print("Error: Log directory not initialized in ConversationLogger.")
             return None

        end_time = datetime.now()
        if begin_time is None: begin_time = end_time
        duration = (end_time - begin_time).total_seconds()

        year, month, day = end_time.strftime("%Y"), end_time.strftime("%m"), end_time.strftime("%d")
        timestamp = end_time.strftime("%H_%M_%S_%f")[:-3]

        # Sanitize listener name for use in file path
        safe_listener_name = "".join(c for c in str(event_listener_name) if c.isalnum() or c in ('_', '-')).rstrip()
        if not safe_listener_name: safe_listener_name = "UnnamedListener"

        log_path = os.path.join(log_directory, safe_listener_name, year, month, day)
        try:
            os.makedirs(log_path, exist_ok=True)
        except OSError as e:
            print(f"Error creating log directory {log_path}: {e}")
            return None

        log_file = os.path.join(log_path, f"{timestamp}_conversation.json")
        log_data = {
            "timestamp": end_time.isoformat(),
            "begin_time": begin_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration,
            "event_listener": event_listener_name, # Log original name
            "request": request,
            "response": response
        }

        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)
        except IOError as e:
            print(f"Error writing log file {log_file}: {e}")
            return None
        except Exception as e:
             print(f"An unexpected error occurred during logging: {e}")
             return None

        # Update current_conversations (optional)
        current_conversations[event_listener_name] = {**log_data, "log_file": log_file}
        return log_file

    # --- get_conversation_logs and load_conversation_log ---
    # (Assume these are present and function correctly, potentially using similar path sanitization)
    @staticmethod
    def get_conversation_logs(event_listener_name=None, limit=10):
        # ... (implementation unchanged from context, add sanitization if needed) ...
        global log_directory # Ensure we use the module global
        logs = []

        if not log_directory:
             print("Error: Log directory not initialized in ConversationLogger.")
             return logs

        # Define the base directory to search
        # Sanitize listener name for path construction if provided
        safe_listener_name = None
        if event_listener_name:
            safe_listener_name = "".join(c for c in str(event_listener_name) if c.isalnum() or c in ('_', '-')).rstrip()
            if not safe_listener_name: safe_listener_name = "UnnamedListener" # Fallback

        base_dir = os.path.join(log_directory, safe_listener_name) if safe_listener_name else log_directory


        if not os.path.exists(base_dir):
            return logs

        # Walk through the directory structure (simplified example)
        try:
            all_files = []
            for root, _, files in os.walk(base_dir):
                 for file in files:
                    if file.endswith("_conversation.json"):
                        all_files.append(os.path.join(root, file))

            # Sort logs by modification time (newest first)
            all_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            logs = all_files[:limit]

        except OSError as e:
            print(f"Error scanning or sorting logs in {base_dir}: {e}")
            return [] # Return empty list on error

        return logs


    @staticmethod
    def load_conversation_log(log_file):
        # ... (implementation unchanged from context) ...
        if not os.path.exists(log_file):
            print(f"Log file not found: {log_file}")
            return None
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, Exception) as e:
            print(f"Error reading or parsing log file {log_file}: {e}")
            return None


# --- MODIFIED: patch_gpt_handler function ---
# Now accepts the specific handler instance to patch.
# Should be called from input_triggers_main.py for each agent's handler.
def patch_gpt_handler(handler: 'GPTThreadHandler'):
    """
    Patches the ask_gpt/ask_gpt_sync methods of a specific GPTThreadHandler
    instance to enable conversation logging via ConversationLogger.

    Args:
        handler: The GPTThreadHandler instance to patch.
    """
    if not handler:
         print("Skipping GPT handler patching: Handler instance is None.")
         return

    try:
        # Store references to the original methods of *this specific instance*
        original_ask_gpt = handler.ask_gpt
        original_ask_gpt_sync = handler.ask_gpt_sync
    except AttributeError as e:
        print(f"Failed to get methods for patching on handler instance: {e}")
        return # Cannot patch if methods don't exist

    def determine_caller_name():
        """Helper to determine the event listener name from the call stack."""
        try:
            frame = sys._getframe(2) # 2 frames back: determine_caller_name -> patched_method -> caller
            event_listener_name = "UnknownListener"
            max_depth = 10
            depth = 0
            while frame and depth < max_depth:
                instance = frame.f_locals.get('self')
                if instance:
                    # Prioritize InputTrigger instances with a 'name' attribute
                    if isinstance(instance, InputTrigger) and hasattr(instance, 'name') and isinstance(instance.name, str):
                        event_listener_name = instance.name
                        break
                    # Fallback to class name
                    elif hasattr(instance, '__class__') and hasattr(instance.__class__, '__name__'):
                         event_listener_name = instance.__class__.__name__
                         # Optional: break here if class name is acceptable

                # Fallback: Check globals (less reliable)
                elif 'event_listener_name' in frame.f_globals:
                     event_listener_name = frame.f_globals['event_listener_name']
                     break

                frame = frame.f_back
                depth += 1
            return event_listener_name
        except Exception as e:
            print(f"Error determining caller name: {e.__class__.__name__}: {e}")
            return "ErrorDeterminingCaller"

    # Define the patched methods within this scope to capture originals
    def patched_ask_gpt(prompt, callback=None):
        """Patched version of ask_gpt that logs conversations."""
        begin_time = datetime.now()
        event_listener_name = determine_caller_name()

        def wrapped_callback(response):
            ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
            if callback:
                try:
                    callback(response)
                except Exception as e:
                    print(f"Error in original callback for {event_listener_name}: {e.__class__.__name__}: {e}")

        try:
            return original_ask_gpt(prompt, wrapped_callback)
        except Exception as e:
            print(f"Error calling original ask_gpt for {event_listener_name}: {e}")
            # Log error and call callback with error message if possible
            error_msg = f"Error during GPT request: {e}"
            ConversationLogger.log_conversation(event_listener_name, prompt, error_msg, begin_time)
            if callback:
                try:
                    callback(error_msg)
                except Exception as cb_e:
                     print(f"Error in original callback (during error handling) for {event_listener_name}: {cb_e}")
            # Depending on original_ask_gpt's behavior, might need to return None or re-raise

    def patched_ask_gpt_sync(prompt):
        """Patched version of ask_gpt_sync that logs conversations."""
        begin_time = datetime.now()
        event_listener_name = determine_caller_name()
        try:
            response = original_ask_gpt_sync(prompt)
            ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
            return response
        except Exception as e:
            print(f"Error in original ask_gpt_sync for {event_listener_name}: {e}")
            error_msg = f"Error: {e}"
            ConversationLogger.log_conversation(event_listener_name, prompt, error_msg, begin_time)
            raise # Re-raise the original exception after logging

    try:
        # Apply the patches TO THE SPECIFIC HANDLER INSTANCE
        handler.ask_gpt = patched_ask_gpt
        handler.ask_gpt_sync = patched_ask_gpt_sync
        # print(f"GPT handler instance patched for logging.") # Less verbose logging
    except Exception as e:
        print(f"Failed to apply patches to GPT handler instance: {e.__class__.__name__}: {e}")


# --- MODIFIED: run_event_listeners function ---
async def run_event_listeners():
    """
    Runs the main input trigger logic (from input_triggers_main).
    Global patching is REMOVED from here.

    Args:
        agent_manifest_data: Dictionary containing filtered agent manifest data.
    """
    global log_directory

    print("Ensuring base log directory exists...")
    if log_directory:
        try:
            os.makedirs(log_directory, exist_ok=True)
            print(f"Base log directory ensured at: {log_directory}")
        except OSError as e:
            print(f"Warning: Could not ensure base log directory {log_directory}: {e}.")
    else:
         print("Warning: Log directory is not set. Logging may fail.")

    # --- REMOVED Global Patching Call ---
    # print("Patching GPT handler for logging...") # No longer done here

    print("Starting event listeners via input_triggers_main...")
    try:
        # input_triggers_main is now responsible for the agent loop,
        # handler creation, patching (using the patch_gpt_handler above),
        # and listener setup.
        if asyncio.iscoroutinefunction(input_triggers_main):
            await input_triggers_main()
        else:
             print("Warning: input_triggers_main is not async. Running synchronously.")
             input_triggers_main()

        print("Event listeners main function finished.")
    except Exception as e:
        print(f"Error running event listeners main function: {e.__class__.__name__}: {e}")
        import traceback
        traceback.print_exc()


# --- start_event_listeners_thread function (Conceptually Unchanged) ---
# Starts the thread that runs run_event_listeners.
def start_event_listeners_thread():
    """Starts the event listeners in a separate thread."""
    print("Starting event listeners thread...")
    listener_loop = None
    try:
        listener_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(listener_loop)
        listener_loop.run_until_complete(run_event_listeners())
    except Exception as e:
        print(f"Error running asyncio event loop in thread: {e.__class__.__name__}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Graceful loop cleanup (important for async tasks)
        if listener_loop:
            try:
                if listener_loop.is_running():
                    print("Stopping event loop...")
                    tasks = asyncio.all_tasks(loop=listener_loop)
                    if tasks:
                        print(f"Cancelling {len(tasks)} outstanding tasks...")
                        for task in tasks: task.cancel()
                        try:
                            # Wait for tasks to finish cancelling
                            listener_loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                            print("Tasks cancelled.")
                        except asyncio.CancelledError:
                            print("Gather itself was cancelled during shutdown.")
                    listener_loop.stop()
                    print("Event loop stopped.")
                # Close the loop only if it's not already closed
                if not listener_loop.is_closed():
                    listener_loop.close()
                    print("Event loop closed.")
            except RuntimeError as loop_close_e:
                 print(f"Info: Error during event loop cleanup (might be expected): {loop_close_e}")
            except Exception as loop_close_e:
                 print(f"Error closing event loop: {loop_close_e}")
        print("Event listener thread finished.")


# --- initialize_input_triggers function (Conceptually Unchanged) ---
# Sets the global log directory and starts the listener thread.
# Added check to return None if no agents are enabled.
def initialize_input_triggers(log_dir_abs_path: str) -> Optional[threading.Thread]:
    """
    Initializes and starts the event listeners in a background thread.

    Args:
        agent_manifest_data: The loaded and filtered agent manifest data.
        log_dir_abs_path: The absolute path to the main log directory.

    Returns:
        The started listener thread object, or None if no agents are enabled.
    """
    global log_directory
    log_directory = log_dir_abs_path

    print(f"Initializing Input Triggers...")

    listener_thread = threading.Thread(
        target=start_event_listeners_thread,
        daemon=True,
        name="EventListenerThread"
    )
    listener_thread.start()
    return listener_thread # Return the thread object
