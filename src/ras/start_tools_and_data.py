import os
import sys
import json

def start_mcp_commands(command_data, secrets):
    common_params = secrets.get("common", {})

    for cmd in command_data["mcp_commands"]:
        if not cmd.get("run_on_start_up"):
            continue

        module_path = cmd["python_code_module"]
        handler_name = cmd.get("handler_function", "execute_command")

        # Load module
        try:
            # Add mcp_commands to sys.path
            mcp_commands_dir = os.path.abspath("mcp_commands")
            if mcp_commands_dir not in sys.path:
                sys.path.append(mcp_commands_dir)
                
            # Load module using spec_from_file_location
            from importlib.util import spec_from_file_location, module_from_spec
            from pathlib import Path
            
            module_file = Path(os.path.join(mcp_commands_dir, module_path))
            spec = spec_from_file_location("cmd_mod", module_file)
            module = module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find internal params for the module
            secret_entry = next(
                (s for s in secrets["secrets"] if s["python_code_module"] == module_path),
                {}
            )
            internal_params = {**common_params, **secret_entry.get("internal_params", {})}

            # Call the handler
            if hasattr(module, handler_name):
                handler = getattr(module, handler_name)
                print(f"🚀 Running startup handler: {module_path}.{handler_name}")
                result = handler({}, internal_params)
                print(f"✅ Result:\n{result}\n")
            else:
                print(f"⚠️ Handler '{handler_name}' not found in {module_path}")

        except Exception as e:
            print(f"❌ Error importing or executing {module_path}: {e}")



def on_startup_dispatcher(agent_manifest_data: dict) -> None:
    """
    Dispatch startup routines for each enabled agent in the manifest by loading
    their configuration and initializing startup MCP commands.

    :param agent_manifest_data: Parsed JSON from agent_manifest.json
    """
    for agent in agent_manifest_data["agents"]:
        if not agent.get("enabled", False):
            continue

        agent_config_path = agent.get("agent_config_file")
        if not agent_config_path:
            print(f"⚠️ Skipping agent {agent.get('name')}: Missing agent_config_file")
            continue

        try:
            # Load the agent config file
            with open(agent_config_path, "r", encoding="utf-8") as f:
                agent_config = json.load(f)

            # Load the command config and secrets files
            command_data_path = agent_config.get("mcp_commands_config_file")
            secrets_data_path = agent_config.get("mcp_commands_secrets_file")

            if not command_data_path or not secrets_data_path:
                print(f"⚠️ Skipping agent {agent.get('name')}: Missing config or secrets file path in agent config.")
                continue

            with open(command_data_path, "r", encoding="utf-8") as f:
                command_data = json.load(f)

            with open(secrets_data_path, "r", encoding="utf-8") as f:
                secrets = json.load(f)

            print(f"🚀 Starting agent: {agent['name']}")
            start_mcp_commands(command_data, secrets)

        except Exception as e:
            print(f"❌ Failed to initialize agent {agent.get('name')}: {e}")



    