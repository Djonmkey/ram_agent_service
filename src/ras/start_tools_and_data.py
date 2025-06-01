import os
import sys
import json
import asyncio
from pathlib import Path # Ensure Path is imported
from typing import Optional

# Determine the project root based on this file's location
# start_tools_and_data.py -> ras -> src -> project_root
SRC_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SRC_DIR.parent

from ras.agent_config_buffer import get_agent_name_list, get_tools_and_data_mcp_commands_config, get_tools_and_data_mcp_commands_secrets, load_agent_manifest
from ras.mcp_client_manager import MCPClientManager

# Global MCP client manager instance
_mcp_client_manager: Optional[MCPClientManager] = None

def cleanup_mcp_clients():
    """Clean up all MCP client connections"""
    global _mcp_client_manager
    
    if _mcp_client_manager:
        try:
            asyncio.run(_mcp_client_manager.cleanup_all())
            print("MCP client cleanup completed.")
        except Exception as e:
            print(f"Error during MCP client cleanup: {e}")
    else:
        print("No MCP client manager to clean up.")


def start_mcp_commands(command_data, secrets, agent_name: str):
    """Executes startup MCP commands for a given agent using the legacy approach."""
    common_params = secrets.get("common", {})
    
    from importlib.util import spec_from_file_location, module_from_spec # Keep import local

    startup_command_executed = False
    for cmd in command_data.get("mcp_commands", []): # Use .get for safety
        if not cmd.get("run_on_start_up"):
            continue

        if cmd.get("enabled") is False:
            continue

        startup_command_executed = True # Mark that we found at least one startup command
        module_path_str = cmd.get("python_code_module")
        handler_name = cmd.get("handler_function", "execute_command") # Default handler name

        if not module_path_str:
            print(f"⚠️ Skipping startup command for agent {agent_name}: Missing 'python_code_module' in command config: {cmd.get('system_text', 'Unnamed Command')}")
            continue

        # Convert to Path and handle both absolute and relative paths
        module_file = Path(module_path_str)
        if not module_file.is_absolute():
            # If relative, make it relative to project root
            module_file = PROJECT_ROOT / module_path_str
            
        if not module_file.exists() or not module_file.is_file():
            print(f"⚠️ Skipping startup command for agent {agent_name}: Module file not found or is not a file: {module_file}")
            continue

        # Load module using spec_from_file_location
        try:
            spec = spec_from_file_location(module_file.stem, module_file) # Use stem for module name
            if not spec or not spec.loader:
                 print(f"⚠️ Skipping startup command for agent {agent_name}: Could not create module spec for {module_file}")
                 continue

            module = module_from_spec(spec)
            # Add the module to sys.modules BEFORE executing it to handle potential circular imports within commands
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # Find internal params for the module
            secret_entry = next(
                (s for s in secrets.get("secrets", []) if s.get("python_code_module") == module_path_str),
                None # Use None as default, then handle it
            )
            # Merge common with specific, specific taking precedence
            if secret_entry:
                internal_params = {**common_params, **secret_entry.get("internal_params", {})}
            else:
                print(f"ℹ️ No specific secrets entry found for module {module_path_str} in agent {agent_name}'s secrets. Using common params only.")
                internal_params = common_params # Use only common if specific are missing

            # Call the handler
            if hasattr(module, handler_name):
                handler = getattr(module, handler_name)
                print(f"  🚀 Running startup handler for agent '{agent_name}': {module_path_str}.{handler_name}")
                # Assuming handler takes ({}, internal_params) based on InputTrigger code
                result = handler({}, internal_params)
                print(f"  ✅ Result: {result}") # Indent result for clarity
            else:
                print(f"  ⚠️ Handler '{handler_name}' not found in {module_path_str} for agent {agent_name}")

        except ImportError as ie:
             print(f"  ❌ Error importing module dependencies for {module_path_str} (Agent: {agent_name}): {ie}")
        except Exception as e:
            print(f"  ❌ Error executing startup handler {module_path_str}.{handler_name} (Agent: {agent_name}): {type(e).__name__}: {e}")

    if not startup_command_executed:
        print(f"  ℹ️ No startup commands marked with 'run_on_start_up: true' found for agent '{agent_name}'.")


async def load_and_connect_mcp_clients(manifest_path: str, mcp_client_manager: MCPClientManager) -> dict:
    """
    Load MCP clients using the generic manager for agents that have mcp_client_python_code_module.
    
    Args:
        manifest_path: Path to the agent manifest file
        mcp_client_manager: The MCP client manager instance
        
    Returns:
        Dictionary mapping agent names to connection results
    """
    # Get enabled agents
    enabled_agent_name_list = get_agent_name_list()
    
    # Load the manifest to get agent configurations
    with open(manifest_path, 'r') as f:
        agent_manifest = json.load(f)
    
    # Track which agents use MCP client manager vs legacy
    agents_with_mcp_client = []
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
            agents_with_mcp_client.append(agent_name)
            print(f"\n🔌 Processing MCP client for agent: {agent_name}")
            # Create task to add client
            connection_tasks.append(
                mcp_client_manager.add_client(agent_name, mcp_client_python_code_module)
            )
    
    # Connect all clients concurrently
    connection_results = {}
    if connection_tasks:
        print(f"\n🔗 Connecting {len(connection_tasks)} MCP clients concurrently...")
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        # Map results
        for i, agent_name in enumerate(agents_with_mcp_client):
            connection_results[agent_name] = results[i]
        
        # Log results
        success_count = sum(1 for r in results if r is True)
        print(f"\n✓ Successfully connected {success_count}/{len(connection_tasks)} MCP clients")
    
    return connection_results


def on_mcp_startup_dispatcher(manifest_path: Optional[str] = None):
    """
    Dispatch startup routines for each enabled agent in the manifest.
    For agents with mcp_client_python_code_module, use the MCP client manager.
    For others, use the legacy start_mcp_commands approach.
    
    Args:
        manifest_path: Optional path to the manifest file
        
    Returns:
        The initialized MCP client manager
    """
    global _mcp_client_manager
    
    print("\n--- Running MCP Startup Dispatcher ---")
    
    # Create MCP client manager instance
    _mcp_client_manager = MCPClientManager()
    
    # If manifest_path provided, ensure it's loaded
    if manifest_path:
        load_agent_manifest(manifest_path)
    
    # Get enabled agents
    enabled_agent_list = get_agent_name_list()
    
    if not enabled_agent_list:
        print("\nℹ️ No enabled agents found in the manifest.")
        return _mcp_client_manager
    
    # First, handle agents with MCP client modules
    print("\n📡 Phase 1: Initializing MCP client connections...")
    
    # Run async client loading
    if manifest_path:
        # Load all MCP Clients using a mcp_client_python_code_module
        connection_results = asyncio.run(load_and_connect_mcp_clients(manifest_path, _mcp_client_manager))
    else:
        print("⚠️ No manifest path provided. Skipping MCP client connections.")
        connection_results = {}
    
    # Print MCP client status summary
    status_summary = _mcp_client_manager.get_status_summary()
    if status_summary:
        print("\n📊 MCP Client Status:")
        for agent_name, status in status_summary.items():
            print(f"  - {agent_name}: {'Connected' if status['connected'] else 'Failed'}")
    
    # Second, handle agents without MCP client modules (legacy approach)
    print("\n🚀 Phase 2: Running legacy startup commands...")
    
    # Load Legacy MCP Servers
    legacy_agent_count = 0
    for agent_name in enabled_agent_list:
        tools_and_data_mcp_commands_config = get_tools_and_data_mcp_commands_config(agent_name)
        mcp_client_python_code_module = tools_and_data_mcp_commands_config.get("mcp_client_python_code_module")

        # Skip if this agent uses MCP client manager, already loaded above
        if agent_name in connection_results:
            continue
        
        legacy_agent_count += 1
        print(f"\n🔧 Initializing legacy startup for agent: '{agent_name}'")
        
        try:
            command_data = get_tools_and_data_mcp_commands_config(agent_name)
            secrets = get_tools_and_data_mcp_commands_secrets(agent_name)
            
            # Call the legacy startup command execution function
            start_mcp_commands(command_data, secrets, agent_name)
            
        except json.JSONDecodeError as e:
            print(f"  ❌ ERROR: Failed to parse JSON for agent '{agent_name}'. File: {e.doc}. Error: {e}")
        except IOError as e:
            print(f"  ❌ ERROR: Could not read a required file for agent '{agent_name}': {e}")
        except Exception as e:
            print(f"  ❌ ERROR: Unexpected error initializing agent '{agent_name}': {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n--- MCP Startup Dispatcher Summary ---")
    print(f"  • MCP Client Manager agents: {len(connection_results)}")
    print(f"  • Legacy startup agents: {legacy_agent_count}")
    print(f"  • Total enabled agents: {len(enabled_agent_list)}")
    print("--- Finished MCP Startup Dispatcher ---\n")
    
    return _mcp_client_manager