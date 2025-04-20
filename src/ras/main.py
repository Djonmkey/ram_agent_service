# /Users/david/Documents/projects/ram_agent_service/src/ras/main.py
import asyncio
import os
import sys
import json
from datetime import datetime
import threading
from pathlib import Path
import time
# import queue # Removed queue as it's no longer used here
import argparse

from startup import on_startup_dispatcher
# Import the new initialization function
from start_input_triggers import initialize_input_triggers

# Add the event_listeners directory to the path - Still needed for gpt_thread potentially?
# Let's keep it for now, but it might be removable if gpt_thread finds its files relatively.
event_listeners_dir = os.path.join(os.path.dirname(__file__), 'event_listeners')
if event_listeners_dir not in sys.path:
    sys.path.append(event_listeners_dir)

# Import the GPT handler - Still needed for shutdown
try:
    from gpt_thread import get_gpt_handler
except ImportError as e:
    print(f"Error importing from gpt_thread: {e}")
    print("Please ensure gpt_thread.py exists and is accessible.")
    sys.exit(1)

# Global variables
# Keep log_directory definition here as it's based on main.py's location
log_directory = os.path.join(os.path.dirname(__file__), 'logs')
# current_conversations moved to start_input_triggers.py

# --- ConversationLogger class removed ---

# --- patch_gpt_handler function removed ---

# --- run_event_listeners function removed ---

# --- start_event_listeners_thread function removed ---


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
        print("Exiting due to missing agent manifest.")
        sys.exit(1)
    else:
        try:
            with open(manifest_path_absolute, 'r', encoding='utf-8') as f:
                agent_manifest_data = json.load(f)
            print("✅ Agent manifest loaded successfully.")
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
        on_startup_dispatcher() # Pass agent_manifest_data if needed by dispatcher
        print("MCP startup dispatcher finished.")
    except Exception as e:
        print(f"Error during MCP startup: {e}")
        sys.exit(1) # Exit if startup fails

    # --- Initialize and start event listeners using the new function ---
    # Calculate absolute log path to pass
    abs_log_directory = os.path.abspath(log_directory)
    # Ensure the base log directory exists before starting listeners
    try:
        os.makedirs(abs_log_directory, exist_ok=True)
        print(f"Base log directory ensured at: {abs_log_directory}")
    except OSError as e:
        print(f"Warning: Could not ensure base log directory {abs_log_directory}: {e}")
        # Continue execution, but logging might fail later

    # Call the function from start_input_triggers.py
    listener_thread = initialize_input_triggers(agent_manifest_data, abs_log_directory)
    # --- End of listener initialization ---

    print("Main thread running. Event listeners started in background thread.")
    print("Press Ctrl+C to exit.")

    # Keep the main thread alive, otherwise the daemon thread might exit prematurely
    try:
        while listener_thread.is_alive():
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
        # (Currently, they run until completion or error - asyncio loop cancellation might be needed)
        print("Waiting for listener thread to finish...")
        listener_thread.join(timeout=5.0) # Wait a bit longer
        if listener_thread.is_alive():
             print("Warning: Listener thread did not exit cleanly.")

        print("Shutdown complete.")
    except Exception as e:
         print(f"\nAn unexpected error occurred in the main loop: {e}")
         # Perform similar shutdown procedures on unexpected errors
         try:
            gpt_handler = get_gpt_handler()
            if gpt_handler:
                 print("Shutting down GPT handler due to error...")
                 gpt_handler.shutdown()
         except Exception as shutdown_e:
            print(f"Error during GPT handler shutdown after main loop error: {shutdown_e}")
         sys.exit(1) # Exit with error status

    print("Application finished.") # Add a final message
    sys.exit(0) # Explicitly exit with success code

    # --- UI Creation and mainloop Removed ---
    # TODO: Start HTTP service for UI
