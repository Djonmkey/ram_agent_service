import os
import sys
import json
from pathlib import Path # Ensure Path is imported

# Determine the project root based on this file's location
# start_tools_and_data.py -> ras -> src -> project_root
SRC_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = SRC_DIR.parent

def start_mcp_commands(command_data, secrets, agent_name: str):
    """Executes startup MCP commands for a given agent."""
    common_params = secrets.get("common", {})
    mcp_commands_dir = PROJECT_ROOT / "mcp_commands" # Base directory for modules

    if not mcp_commands_dir.is_dir():
        print(f"⚠️ MCP commands directory not found at {mcp_commands_dir} for agent {agent_name}. Skipping startup commands.")
        return

    # Add mcp_commands dir to sys.path if not already there, specific to this execution context
    # This is generally discouraged in favor of proper packaging, but done here for consistency
    # with the original approach. Consider refactoring later.
    mcp_commands_dir_str = str(mcp_commands_dir)
    if mcp_commands_dir_str not in sys.path:
        sys.path.insert(0, mcp_commands_dir_str) # Insert at beginning to prioritize

    from importlib.util import spec_from_file_location, module_from_spec # Keep import local

    startup_command_executed = False
    for cmd in command_data.get("mcp_commands", []): # Use .get for safety
        if not cmd.get("run_on_start_up"):
            continue

        startup_command_executed = True # Mark that we found at least one startup command
        module_path_str = cmd.get("python_code_module")
        handler_name = cmd.get("handler_function", "execute_command") # Default handler name

        if not module_path_str:
            print(f"⚠️ Skipping startup command for agent {agent_name}: Missing 'python_code_module' in command config: {cmd.get('system_text', 'Unnamed Command')}")
            continue

        module_file = mcp_commands_dir / module_path_str
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

    # Clean up path modification if it was added
    # if mcp_commands_dir_str in sys.path and sys.path[0] == mcp_commands_dir_str:
    #     sys.path.pop(0)
    # Note: Removing from sys.path can be tricky if other parts rely on it later.
    # Leaving it might be safer unless causing conflicts.

    if not startup_command_executed:
        print(f"  ℹ️ No startup commands marked with 'run_on_start_up: true' found for agent '{agent_name}'.")


def on_startup_dispatcher(agent_manifest_data: dict) -> None:
    """
    Dispatch startup routines for each enabled agent in the manifest by loading
    their configuration and initializing startup MCP commands.

    :param agent_manifest_data: Parsed JSON from agent_manifest.json
    """
    print("\n--- Running MCP Startup Dispatcher ---") # Header for clarity

    if not agent_manifest_data or "agents" not in agent_manifest_data:
        print("❌ ERROR: Agent manifest data is missing or invalid. Cannot run startup dispatcher.")
        return

    enabled_agents_count = 0
    for agent in agent_manifest_data["agents"]:
        # Ensure agent is a dictionary and get name safely
        if not isinstance(agent, dict):
            print(f"⚠️ Skipping invalid agent entry (not a dictionary): {agent}")
            continue
        agent_name = agent.get("name", "Unnamed Agent")

        if not agent.get("enabled", False):
            # print(f"ℹ️ Skipping disabled agent: {agent_name}") # Optional: Less verbose
            continue

        enabled_agents_count += 1
        print(f"\n🚀 Initializing startup for enabled agent: '{agent_name}'")

        # --- Agent Config File Handling ---
        agent_config_relative_path = agent.get("agent_config_file")
        if not agent_config_relative_path:
            print(f"  ⚠️ Skipping agent '{agent_name}': Missing 'agent_config_file' in manifest.")
            continue

        # Construct absolute path relative to the project root
        agent_config_absolute_path = (PROJECT_ROOT / agent_config_relative_path).resolve()

        print(f"  Config Path (relative): {agent_config_relative_path}")
        print(f"  Config Path (absolute): {agent_config_absolute_path}")

        # Check if the config file exists and is a file BEFORE trying to open
        if not agent_config_absolute_path.exists():
            print(f"  ❌ ERROR: Agent config file not found: {agent_config_absolute_path}")
            continue # Skip this agent
        if not agent_config_absolute_path.is_file():
            print(f"  ❌ ERROR: Agent config path is not a file: {agent_config_absolute_path}")
            continue # Skip this agent
        # --- End Agent Config File Handling ---

        try:
            # Load the agent config file (now we know it exists)
            with open(agent_config_absolute_path, "r", encoding="utf-8") as f:
                agent_config = json.load(f)
            print(f"  ✅ Agent config loaded successfully.")

            # --- Command and Secrets File Handling ---
            # Get paths from the loaded agent_config
            command_data_relative_path = agent_config.get("mcp_commands_config_file")
            secrets_data_relative_path = agent_config.get("mcp_commands_secrets_file")

            if not command_data_relative_path or not secrets_data_relative_path:
                print(f"  ⚠️ Skipping MCP startup for agent '{agent_name}': Missing 'mcp_commands_config_file' or 'mcp_commands_secrets_file' path in agent config ({agent_config_absolute_path.name}).")
                continue

            # Resolve paths relative to project root
            command_data_absolute_path = (PROJECT_ROOT / command_data_relative_path).resolve()
            secrets_data_absolute_path = (PROJECT_ROOT / secrets_data_relative_path).resolve()

            print(f"  MCP Commands Path: {command_data_absolute_path}")
            print(f"  MCP Secrets Path: {secrets_data_absolute_path}")

            # Check existence for commands config
            if not command_data_absolute_path.exists() or not command_data_absolute_path.is_file():
                 print(f"  ❌ ERROR: MCP commands config file not found or not a file: {command_data_absolute_path}")
                 continue # Skip MCP startup for this agent

            # Check existence for secrets config
            if not secrets_data_absolute_path.exists() or not secrets_data_absolute_path.is_file():
                 print(f"  ❌ ERROR: MCP secrets file not found or not a file: {secrets_data_absolute_path}")
                 continue # Skip MCP startup for this agent

            # Load the command config and secrets files
            with open(command_data_absolute_path, "r", encoding="utf-8") as f_cmd:
                command_data = json.load(f_cmd)
            print(f"  ✅ MCP commands config loaded.")

            with open(secrets_data_absolute_path, "r", encoding="utf-8") as f_sec:
                secrets = json.load(f_sec)
            print(f"  ✅ MCP secrets loaded.")
            # --- End Command and Secrets File Handling ---

            # Call the startup command execution function
            start_mcp_commands(command_data, secrets, agent_name)

        except json.JSONDecodeError as e:
            # More specific error for JSON parsing issues
            print(f"  ❌ ERROR: Failed to parse JSON for agent '{agent_name}'. File: {e.doc}. Error: {e}")
        except IOError as e:
             print(f"  ❌ ERROR: Could not read a required file for agent '{agent_name}': {e}")
        except Exception as e:
            # Catch-all for other unexpected errors during agent initialization
            print(f"  ❌ ERROR: Unexpected error initializing agent '{agent_name}': {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc() # Print stack trace for unexpected errors

    if enabled_agents_count == 0:
        print("\nℹ️ No enabled agents found in the manifest to run startup dispatcher for.")
    else:
        print(f"\n--- Finished MCP Startup Dispatcher for {enabled_agents_count} enabled agent(s) ---")

