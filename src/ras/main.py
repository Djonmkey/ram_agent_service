# /Users/david/Documents/projects/ram_agent_service/src/ras/main.py
import asyncio
import os
import sys
import json
from datetime import datetime
import threading
from pathlib import Path # <-- Make sure pathlib is imported
import time
import argparse

# --- BEGIN: Add src directory to sys.path ---
# Determine the absolute path to the 'src' directory
# Assumes this file is located at src/ras/main.py
# Goes up one level: ras -> src
SRC_DIR = Path(__file__).resolve().parent.parent

# Add src directory to sys.path to ensure imports work correctly
# across the application modules. Insert at the beginning
# to prioritize it.
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
# --- END: Add src directory to sys.path ---

# Now imports relative to src should work everywhere
from ras.start_tools_and_data import on_startup_dispatcher # Use explicit relative or absolute
from ras.start_input_triggers import initialize_input_triggers # Use explicit relative or absolute
from .chat_thread import get_gpt_handler


# Global variables
# Keep log_directory definition here as it's based on main.py's location
log_directory = os.path.join(os.path.dirname(__file__), 'logs')
# current_conversations moved to start_input_triggers.py

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

    # --- Filter Agents based on 'enabled' flag ---
    filtered_manifest_data = None
    if agent_manifest_data:
        original_agents = agent_manifest_data.get("agents")

        if original_agents is None:
            print("❌ ERROR: Manifest is missing the 'agents' list key.")
            sys.exit(1)
        elif not isinstance(original_agents, list):
             print(f"❌ ERROR: Manifest 'agents' key is not a list (type: {type(original_agents).__name__}).")
             sys.exit(1)
        else:
            enabled_agents = []
            print("\nFiltering agents based on 'enabled' flag:")
            for agent_config in original_agents:
                # Ensure agent_config is a dictionary before proceeding
                if not isinstance(agent_config, dict):
                    print(f"  ⚠️ Skipping invalid agent entry (not a dictionary): {agent_config}")
                    continue

                agent_name = agent_config.get("name", "Unnamed Agent")
                # Treat agent as enabled only if "enabled" key exists and is explicitly True
                if agent_config.get("enabled") is True:
                    print(f"  ✅ Enabling agent: {agent_name}")
                    enabled_agents.append(agent_config)
                else:
                    # This covers cases where "enabled" is false, null, missing, or any other value
                    print(f"  ➖ Skipping disabled agent: {agent_name}")

            # Create a new manifest structure containing only the enabled agents,
            # but preserving other top-level keys (like 'secrets').
            filtered_manifest_data = agent_manifest_data.copy()
            filtered_manifest_data["agents"] = enabled_agents

            if not enabled_agents:
                print("\n⚠️ No enabled agents found in the manifest. No input triggers will be started.")
            else:
                 print(f"\nProceeding with {len(enabled_agents)} enabled agent(s).")

    else:
        # This case should technically not be reached due to earlier exit calls,
        # but added for robustness.
        print("⚠️ Agent manifest data was not loaded. Cannot initialize triggers.")
        sys.exit(1)
    # --- End of Agent Filtering ---


    print("\nExecuting MCP startup dispatcher...")
    try:
        # Pass the original manifest data to startup dispatcher, as it might need
        # info about all potential commands/secrets, not just enabled agents.
        # Adjust if startup dispatcher should only know about enabled agents.
        on_startup_dispatcher(agent_manifest_data)
        print("MCP startup dispatcher finished.")
    except Exception as e:
        print(f"❌ Error during MCP startup: {e}")
        sys.exit(1) # Exit if startup fails

    # --- Initialize and start event listeners using the new function ---
    # Calculate absolute log path to pass
    abs_log_directory = os.path.abspath(log_directory)
    # Ensure the base log directory exists before starting listeners
    try:
        os.makedirs(abs_log_directory, exist_ok=True)
        print(f"\nBase log directory ensured at: {abs_log_directory}")
    except OSError as e:
        print(f"⚠️ Warning: Could not ensure base log directory {abs_log_directory}: {e}")
        # Continue execution, but logging might fail later

    # Call the function from start_input_triggers.py with the FILTERED manifest data
    listener_thread = None
    if filtered_manifest_data and filtered_manifest_data.get("agents"):
        listener_thread = initialize_input_triggers(filtered_manifest_data, abs_log_directory)
    else:
        print("Skipping input trigger initialization as there are no enabled agents.")
    # --- End of listener initialization ---

    print("\nMain thread running.")
    if listener_thread:
        print("Event listeners started in background thread for enabled agents.")
    print("Press Ctrl+C to exit.")

    # Keep the main thread alive, otherwise the daemon thread might exit prematurely
    try:
        # Only join if the thread was actually started
        if listener_thread:
            while listener_thread.is_alive():
                listener_thread.join(timeout=1.0)
        else:
            # If no listeners started, just wait for KeyboardInterrupt
            while True:
                time.sleep(1)
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
        if listener_thread:
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

    print("\nApplication finished.") # Add a final message
    sys.exit(0) # Explicitly exit with success code

    # --- UI Creation and mainloop Removed ---
    # TODO: Start HTTP service for UI

