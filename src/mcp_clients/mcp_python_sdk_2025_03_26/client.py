import asyncio
import sys
from typing import Optional, List, Dict, Any
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv()  # load environment variables from .env

from ras.agent_config_buffer import get_tools_and_data_mcp_commands_config
from ras.work_queue_manager import process_chat_model_request

class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.sessions: List[ClientSession] = []
        self.exit_stack = AsyncExitStack()
        self.server_modules: List[str] = []

    async def connect_to_server(self, agent_name: str):
        """Connect to MCP servers based on agent configuration
        
        Args:
            agent_name: Name of the agent to load configuration for
        """
        tools_and_data_mcp_commands_config = get_tools_and_data_mcp_commands_config(agent_name)
        
        if not tools_and_data_mcp_commands_config or 'mcp_commands' not in tools_and_data_mcp_commands_config:
            print(f"No MCP commands configuration found for agent: {agent_name}")
            return
        
        # Get unique server modules from enabled commands
        unique_modules = set()
        for command in tools_and_data_mcp_commands_config['mcp_commands']:
            if not command.get('enabled', True):
                continue
                
            # Check for python_code_module or node_code_module
            if 'python_code_module' in command:
                unique_modules.add(('python', command['python_code_module']))
            elif 'node_code_module' in command:
                unique_modules.add(('node', command['node_code_module']))
        
        if not unique_modules:
            print(f"No enabled MCP server modules found for agent: {agent_name}")
            return
        
        # Connect to each unique server module
        all_tools = []
        for module_type, module_path in unique_modules:
            try:
                # Resolve the full path if it's relative
                if not Path(module_path).is_absolute():
                    # Assume it's relative to the project root
                    full_path = Path.cwd() / module_path
                else:
                    full_path = Path(module_path)
                
                if not full_path.exists():
                    print(f"Warning: Server module not found: {full_path}")
                    continue
                
                command = "python" if module_type == 'python' else "node"
                server_params = StdioServerParameters(
                    command=command,
                    args=[str(full_path)],
                    env=None
                )
                
                stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                stdio, write = stdio_transport
                session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
                
                await session.initialize()
                self.sessions.append(session)
                self.server_modules.append(str(full_path))
                
                # List available tools for this server
                response = await session.list_tools()
                tools = response.tools
                tool_names = [tool.name for tool in tools]
                all_tools.extend(tool_names)
                print(f"\nConnected to {module_path} with tools: {tool_names}")
                
            except Exception as e:
                print(f"Failed to connect to server {module_path}: {str(e)}")
        
        if self.sessions:
            print(f"\nTotal tools available across all servers: {all_tools}")
        else:
            print("No servers were successfully connected.")

    async def process_query(self, agent_name, query: str) -> str:
        """Process a query using Chat Model and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()
        available_tools = [{ 
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        } for tool in response.tools]

        # Initial Claude API call
        task_data = { "agent_name":agent_name, "prompt": query}

        response = process_chat_model_request(task_data)

        # Process response and handle tool calls
        tool_results = []
        final_text = []

        for content in response.content:
            if content.type == 'text':
                final_text.append(content.text)
            elif content.type == 'tool_use':
                tool_name = content.name
                tool_args = content.input
                
                # Execute tool call
                result = await self.session.call_tool(tool_name, tool_args)
                tool_results.append({"call": tool_name, "result": result})
                final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

                # Continue conversation with tool results
                if hasattr(content, 'text') and content.text:
                    messages.append({
                      "role": "assistant",
                      "content": content.text
                    })
                messages.append({
                    "role": "user", 
                    "content": result.content
                })

                # Get next response from Claude
                response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=messages,
                )

                final_text.append(response.content[0].text)

        return "\n".join(final_text)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()

async def main():
    if len(sys.argv) < 2:
        print("Usage: client.py <agent_name>")
        sys.exit(1)
        
    client = MCPClient()
    try:
        await client.connect_to_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())
