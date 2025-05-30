import asyncio
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv()  # load environment variables from .env

from ras.agent_config_buffer import get_tools_and_data_mcp_commands_config
from ras.work_queue_manager import process_chat_model_request
from .single_server_client import SingleServerMCPClient

class MCPClient:
    """MCP Client that manages multiple SingleServerMCPClient instances"""
    
    def __init__(self):
        self.clients: List[SingleServerMCPClient] = []
        self.tool_to_client_map: Dict[str, SingleServerMCPClient] = {}
        self.agent_name: Optional[str] = None

    async def connect_to_server(self, agent_name: str):
        """Connect to MCP servers based on agent configuration
        
        Args:
            agent_name: Name of the agent to load configuration for
        """
        self.agent_name = agent_name
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
        
        # Create SingleServerMCPClient instances
        self.clients = []
        for module_type, module_path in unique_modules:
            client = SingleServerMCPClient(module_type, module_path, agent_name)
            self.clients.append(client)
        
        print(f"Connecting to {len(self.clients)} MCP servers concurrently...")
        
        # Connect to all servers concurrently (this solves the blocking issue)
        connection_tasks = []
        for client in self.clients:
            connection_tasks.append(client.connect(timeout=10.0))
        
        # Execute all connections concurrently
        results = await asyncio.gather(*connection_tasks, return_exceptions=True)
        
        # Process results and build tool mapping
        successful_clients = []
        all_tools = []
        
        for i, result in enumerate(results):
            client = self.clients[i]
            if isinstance(result, Exception):
                print(f"✗ Exception connecting to {client.module_path}: {str(result)}")
            elif result:  # Connection successful
                successful_clients.append(client)
                
                # Map each tool to its client
                for tool in client.get_tools():
                    tool_name = tool["name"]
                    if tool_name in self.tool_to_client_map:
                        print(f"Warning: Tool '{tool_name}' is available on multiple servers. Using first occurrence.")
                    else:
                        self.tool_to_client_map[tool_name] = client
                    all_tools.append(tool_name)
            else:
                print(f"✗ Failed to connect to {client.module_path}")
        
        # Update clients list to only include successful connections
        self.clients = successful_clients
        
        if self.clients:
            print(f"\n✓ Successfully connected to {len(self.clients)} servers")
            print(f"✓ Total tools available: {all_tools}")
        else:
            print("✗ No servers were successfully connected.")

    def find_client_for_tool(self, tool_name: str) -> Optional[SingleServerMCPClient]:
        """Find the client that provides a specific tool"""
        return self.tool_to_client_map.get(tool_name)

    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """
        Call a tool on the appropriate server
        
        Args:
            tool_name: Name of the tool to call
            tool_args: Arguments for the tool call
            
        Returns:
            Tool execution result
            
        Raises:
            ValueError: If tool is not available on any server
        """
        client = self.find_client_for_tool(tool_name)
        if not client:
            available_tools = list(self.tool_to_client_map.keys())
            raise ValueError(f"Tool '{tool_name}' not available. Available tools: {available_tools}")
        
        return await client.call_tool(tool_name, tool_args)

    async def process_query(self, agent_name: str, query: str, meta_data: Optional[Dict[str, Any]] = None) -> str:
        """Process a query using Chat Model and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        if not self.clients:
            print("Error: No MCP client connections available")
            return "Error: No MCP server connections available"
        
        # Get all available tools from all servers
        available_tools = []
        for client in self.clients:
            available_tools.extend(client.get_tools())

        # Initial Claude API call
        task_data = {"agent_name": agent_name, "prompt": query}
        
        final_text_future = asyncio.Future()
        tool_results = []
        final_text = []

        async def response_callback(response):
            nonlocal final_text, tool_results
            try:
                for content in response.content:
                    if content.type == 'text':
                        final_text.append(content.text)
                    elif content.type == 'tool_use':
                        tool_name = content.name
                        tool_args = content.input
                        
                        # Execute tool call on the appropriate server
                        result = await self.call_tool(tool_name, tool_args)
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

                        # multi-turn conversations
                        process_chat_model_request(task_data, callback=response_callback)
                final_text_future.set_result("\n".join(final_text))
            except Exception as e:
                final_text_future.set_exception(e)

        process_chat_model_request(task_data, callback=response_callback)

        return await final_text_future

    async def chat_loop(self):
        """Run an interactive chat loop"""
        if not self.agent_name:
            print("Error: No agent name set. Call connect_to_server first.")
            return
            
        print(f"\nMCP Client Started for agent '{self.agent_name}'!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = await self.process_query(self.agent_name, query)
                print("\n" + response)
                    
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    async def cleanup(self):
        """Clean up all client resources"""
        cleanup_tasks = []
        for client in self.clients:
            cleanup_tasks.append(client.cleanup())
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        self.clients.clear()
        self.tool_to_client_map.clear()
        self.agent_name = None
        print(f"✓ Cleaned up all MCP connections")

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
