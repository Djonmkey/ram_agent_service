# /Users/david/Documents/projects/ram_agent_service/src/ras/main.py
import asyncio
import os
import sys
import json
from datetime import datetime
import threading
from pathlib import Path 
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
from ras.work_queue_manager import start_all_queue_workers
from ras.agent_config_buffer import load_agent_manifest, get_agent_name_list
from ras.start_tools_and_data import on_mcp_startup_dispatcher  # Use explicit relative or absolute
from ras.start_input_triggers import initialize_input_triggers  # Use explicit relative or absolute

# Global variables
# Keep log_directory definition here as it's based on main.py's location
log_directory = os.path.join(os.path.dirname(__file__), 'logs')
# current_conversations moved to start_input_triggers.py

async def load_and_connect_mcp_clients(manifest_path: str) -> MCPClientManager:
    """
    Load MCP clients using the generic manager.
    Each agent with mcp_client_python_code_module gets its own client.
    """
    mcp_client_manager = MCPClientManager()
    
    # Get enabled agents
    enabled_agent_name_list = get_agent_name_list()
    
    # Load the manifest to get agent configurations
    with open(manifest_path, 'r') as f:
        agent_manifest = json.load(f)
    
    # Process each enabled agent
    connection_tasks = []
    
    for agent_name in enabled_agent_name_list:
        # Find the agent config in manifest
        agent_config = None
        for config in agent_manifest.get("agents", []):
            if config.get('name') == agent_name and config.get('enabled', False):
                agent_config = config
                break
        
        if not agent_config:
            continue
        
        # Check if agent has mcp_client_python_code_module
        mcp_client_python_code_module = agent_config.get('mcp_client_python_code_module')
        
        if mcp_client_python_code_module:
            print(f"\nProcessing MCP client for agent: {agent_name}")
            # Create task to add client
            connection_tasks.append(
                mcp_client_manager.add_client(agent_name, mcp_client_python_code_module)
            )
    
    # Connect all clients concurrently
    if connection_tasks:
        print(f"\nConnecting {len(connection_tasks)} MCP clients concurrently...")
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        # Log results
        success_count = sum(1 for r in results if r is True)
        print(f"\n✓ Successfully connected {success_count}/{len(connection_tasks)} MCP clients")
    else:
        print("\nNo agents with MCP clients found")
    
    # Print status summary
    status_summary = mcp_client_manager.get_status_summary()
    if status_summary:
        print("\nMCP Client Status:")
        for agent_name, status in status_summary.items():
            print(f"  - {agent_name}: {'Connected' if status['connected'] else 'Failed'}")
    
    return mcp_client_manager

if __name__ == "__main__":
    # --- Agent Manifest File Loading ---
    parser = argparse.ArgumentParser(description="Run the RAM Agent Service.")
    parser.add_argument(
        'manifest_file',
        nargs='?', # Makes the argument optional
        default='../../config/agent_manifest.json', # Default value if not provided
        help='Path to the agent manifest JSON file (relative to main.py location).'
    )
    args = parser.parse_args()

    # Construct the absolute path relative to this script's location
    script_dir = os.path.dirname(__file__)
    manifest_path_relative = args.manifest_file
    manifest_path_absolute = os.path.abspath(os.path.join(script_dir, manifest_path_relative))

    print(f"Attempting to load agent manifest from: {manifest_path_absolute}")

    if not os.path.exists(manifest_path_absolute):
        print(f"❌ ERROR: Agent manifest file not found at the expected location: {manifest_path_absolute}")
        print("Exiting due to missing agent manifest.")
        sys.exit(1)
    else:
        try:
            load_agent_manifest(str(manifest_path_absolute))
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

    print("\nExecuting MCP startup dispatcher...")
    try:
        # Pass the original manifest data to startup dispatcher, as it might need
        # info about all potential commands/secrets, not just enabled agents.
        # Adjust if startup dispatcher should only know about enabled agents.
        on_mcp_startup_dispatcher()
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

    # Run the async client loading using the generic manager
    mcp_client_manager = asyncio.run(load_and_connect_mcp_clients(manifest_path_absolute))

    # Start the Queue Manager
    start_all_queue_workers()

    # Call the function from start_input_triggers.py with the FILTERED manifest data
    listener_thread = None
    if get_agent_name_list():
        listener_thread = initialize_input_triggers(abs_log_directory)
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

        # Cleanup MCP client sessions using the generic manager
        async def cleanup_mcp_clients():
            """Clean up all MCP client connections"""
            await mcp_client_manager.cleanup_all()
        
        # Run cleanup
        try:
            asyncio.run(cleanup_mcp_clients())
            print("MCP client cleanup completed.")
        except Exception as e:
            print(f"Error during MCP client cleanup: {e}")

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
         sys.exit(1) # Exit with error status

    print("\nApplication finished.")
    sys.exit(0)