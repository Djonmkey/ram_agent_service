import asyncio
import sys
from typing import Optional, Dict, Any, List
import os
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv()  # load environment variables from .env

from ras.agent_config_buffer import get_tools_and_data_mcp_commands_secrets_by_module

class SingleServerMCPClient:
    """MCP Client that connects to a single server"""
    
    def __init__(self, module_type: str, module_path: str, agent_name: str):
        """
        Initialize MCP client for a single server
        
        Args:
            module_type: Type of server ('python' or 'node')
            module_path: Path to the server module
            agent_name: Name of the agent this client belongs to
        """
        self.module_type = module_type
        self.module_path = module_path
        self.agent_name = agent_name
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.tools: List[Dict[str, Any]] = []
        self.is_connected = False
        self.connection_error: Optional[str] = None
        
    async def connect(self, timeout: float = 10.0) -> bool:
        """
        Connect to the MCP server
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Resolve the full path if it's relative
            if not Path(self.module_path).is_absolute():
                # Assume it's relative to the project root
                full_path = Path.cwd() / self.module_path
            else:
                full_path = Path(self.module_path)
            
            if not full_path.exists():
                self.connection_error = f"Server module not found: {full_path}"
                print(f"Warning: {self.connection_error}")
                return False
            
            # Get secrets for this specific module
            secrets = get_tools_and_data_mcp_commands_secrets_by_module(self.agent_name, self.module_path)
            
            # Prepare environment variables, merging secrets with current environment
            env = os.environ.copy()
            if secrets:
                for key, value in secrets.items():
                    env[key] = str(value)
            
            # Use the same Python interpreter as the main process for Python servers
            command = sys.executable if self.module_type == 'python' else "node"
            server_params = StdioServerParameters(
                command=command,
                args=["-u", str(full_path)],
                env=env
            )
            
            # Use asyncio.wait_for for timeout
            stdio_transport = await asyncio.wait_for(
                self.exit_stack.enter_async_context(stdio_client(server_params)),
                timeout=timeout
            )
            stdio, write = stdio_transport
            
            self.session = await asyncio.wait_for(
                self.exit_stack.enter_async_context(ClientSession(stdio, write)),
                timeout=timeout
            )
            
            await asyncio.wait_for(self.session.initialize(), timeout=timeout)
            
            # List available tools for this server
            response = await self.session.list_tools()
            self.tools = [{
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema
            } for tool in response.tools]
            
            self.is_connected = True
            tool_names = [tool["name"] for tool in self.tools]
            print(f"✓ Connected to {self.module_path} with tools: {tool_names}")
            return True
            
        except asyncio.TimeoutError:
            self.connection_error = f"Connection timeout for {self.module_path}"
            print(f"✗ {self.connection_error}")
            return False
        except Exception as e:
            self.connection_error = f"Failed to connect to {self.module_path}: {str(e)}"
            print(f"✗ {self.connection_error}")
            return False
    
    async def call_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """
        Call a tool on this server
        
        Args:
            tool_name: Name of the tool to call
            tool_args: Arguments for the tool call
            
        Returns:
            Tool execution result
            
        Raises:
            RuntimeError: If client is not connected
            ValueError: If tool is not available on this server
        """
        if not self.is_connected or not self.session:
            raise RuntimeError(f"Client not connected to {self.module_path}")
        
        # Check if tool is available on this server
        if not any(tool["name"] == tool_name for tool in self.tools):
            raise ValueError(f"Tool '{tool_name}' not available on server {self.module_path}")
        
        try:
            result = await self.session.call_tool(tool_name, tool_args)
            return result
        except Exception as e:
            print(f"Error calling tool {tool_name} on {self.module_path}: {str(e)}")
            raise
    
    def has_tool(self, tool_name: str) -> bool:
        """Check if this server has a specific tool"""
        return any(tool["name"] == tool_name for tool in self.tools)
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools"""
        return self.tools.copy()
    
    async def cleanup(self):
        """Clean up resources"""
        try:
            await self.exit_stack.aclose()
            self.is_connected = False
            self.session = None
        except Exception as e:
            print(f"Error during cleanup of {self.module_path}: {str(e)}")
    
    def __str__(self):
        status = "connected" if self.is_connected else "disconnected"
        tool_count = len(self.tools) if self.tools else 0
        return f"SingleServerMCPClient({self.module_path}, {status}, {tool_count} tools)"
