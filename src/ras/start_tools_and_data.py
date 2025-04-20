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



def on_startup_dispatcher(agent_manifest_data):
    for agent in agent_manifest_data["agents"]:
        command_data = None
        secrets = None

        # TODO: load agent_config_file 
        # TODO: load the mcp_commands_config_file from the agent_config_file into the command_data variable.
        # TODO: load the mcp_commands_secrets_file from  the agent_config_file into the secrets

        start_mcp_commands(command_data, secrets)


    