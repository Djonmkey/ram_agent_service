import asyncio
import sys
from typing import Optional, List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

SRC_DIR = Path(__file__).resolve().parent.parent

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

load_dotenv()  # load environment variables from .env

from .multi_server_client import MultiServerMCPClient

class MCPClient:
    """
    Legacy wrapper for MultiServerMCPClient to maintain backward compatibility
    """
    
    def __init__(self):
        # Backward compatibility - will be set when connect_to_server is called
        self.multi_client: Optional[MultiServerMCPClient] = None
        self.agent_name: Optional[str] = None

    async def connect_to_server(self, agent_name: str):
        """Connect to MCP servers based on agent configuration
        
        Args:
            agent_name: Name of the agent to load configuration for
        """
        self.agent_name = agent_name
        self.multi_client = MultiServerMCPClient(agent_name)
        
        status = await self.multi_client.connect_to_servers()
        
        # Legacy compatibility - print summary
        success_count = sum(1 for connected in status.values() if connected)
        if success_count > 0:
            all_tools = [tool["name"] for tool in self.multi_client.get_all_tools()]
            print(f"\n✓ Legacy MCPClient connected {success_count} servers with tools: {all_tools}")
        else:
            print("✗ Legacy MCPClient: No servers were successfully connected.")

    async def process_query(self, agent_name: str, query: str, meta_data: Optional[Dict[str, Any]] = None) -> str:
        """Process a query using Chat Model and available tools"""
        if not self.multi_client:
            print("Error: No MCP client available. Call connect_to_server first.")
            return "Error: No MCP client available"
        
        # Delegate to the multi-server client
        return await self.multi_client.process_query(query, meta_data)

    async def chat_loop(self):
        """Run an interactive chat loop"""
        if not self.multi_client:
            print("Error: No MCP client available. Call connect_to_server first.")
            return
        
        # Delegate to the multi-server client
        await self.multi_client.chat_loop()
    
    async def cleanup(self):
        """Clean up resources"""
        if self.multi_client:
            await self.multi_client.cleanup()
            self.multi_client = None
            self.agent_name = None

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
