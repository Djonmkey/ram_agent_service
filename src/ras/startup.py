import os
import sys
import json
from constants import MCP_COMMANDS_PATH, MCP_SECRETS_PATH

def on_startup_dispatcher():
    with open(MCP_COMMANDS_PATH, "r") as f:
        command_data = json.load(f)

    with open(MCP_SECRETS_PATH, "r") as f:
        secrets = json.load(f)

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
