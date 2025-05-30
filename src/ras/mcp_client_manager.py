import threading
import asyncio
from typing import Dict, Optional, List
from src.mcp_clients.mcp_python_sdk_2025_03_26.multi_server_client import MultiServerMCPClient

class MCPClientManager:
    """
    Manages MCP clients for multiple agents
    Each agent has one MultiServerMCPClient that manages multiple server connections
    """
    
    def __init__(self):
        self.clients: Dict[str, MultiServerMCPClient] = {}
        self.lock = threading.Lock()
        self.connection_status: Dict[str, Dict[str, bool]] = {}  # agent -> {server_path: success}

    async def add_client(self, agent_name: str) -> bool:
        """
        Create and connect a new MultiServerMCPClient for an agent
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if at least one server connected successfully, False otherwise
        """
        with self.lock:
            if agent_name in self.clients:
                print(f"Client for agent '{agent_name}' already exists")
                return True
        
        print(f"Creating MCP client for agent '{agent_name}'...")
        client = MultiServerMCPClient(agent_name)
        
        try:
            # Connect to all servers for this agent
            status = await client.connect_to_servers()
            
            # Store connection status
            self.connection_status[agent_name] = status
            
            # Check if any servers connected successfully
            success_count = sum(1 for connected in status.values() if connected)
            
            if success_count > 0:
                with self.lock:
                    self.clients[agent_name] = client
                print(f"✓ Added MCP client for agent '{agent_name}' with {success_count} connected servers")
                return True
            else:
                print(f"✗ Failed to connect any servers for agent '{agent_name}'")
                await client.cleanup()
                return False
                
        except Exception as e:
            print(f"✗ Error creating MCP client for agent '{agent_name}': {str(e)}")
            await client.cleanup()
            return False

    def get_client(self, agent_name: str) -> Optional[MultiServerMCPClient]:
        """
        Get the MultiServerMCPClient for an agent
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            MultiServerMCPClient instance or None if not found
        """
        with self.lock:
            return self.clients.get(agent_name)
    
    def has_client(self, agent_name: str) -> bool:
        """
        Check if a client exists for an agent
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if client exists, False otherwise
        """
        with self.lock:
            return agent_name in self.clients
    
    def get_connection_status(self, agent_name: str) -> Dict[str, bool]:
        """
        Get connection status for all servers of an agent
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Dictionary mapping server paths to connection success status
        """
        return self.connection_status.get(agent_name, {})
    
    def list_agents(self) -> List[str]:
        """
        Get list of all agent names with active clients
        
        Returns:
            List of agent names
        """
        with self.lock:
            return list(self.clients.keys())
    
    async def remove_client(self, agent_name: str) -> bool:
        """
        Remove and cleanup MCP client for an agent
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if client was removed, False if not found
        """
        client = None
        with self.lock:
            client = self.clients.pop(agent_name, None)
            self.connection_status.pop(agent_name, None)
        
        if client:
            try:
                await client.cleanup()
                print(f"✓ Removed MCP client for agent '{agent_name}'")
                return True
            except Exception as e:
                print(f"✗ Error cleaning up MCP client for agent '{agent_name}': {str(e)}")
                return False
        else:
            print(f"No MCP client found for agent '{agent_name}'")
            return False
    
    async def cleanup_all(self):
        """
        Cleanup all MCP clients
        """
        agents_to_cleanup = None
        with self.lock:
            agents_to_cleanup = list(self.clients.keys())
        
        cleanup_tasks = []
        for agent_name in agents_to_cleanup:
            cleanup_tasks.append(self.remove_client(agent_name))
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        print("✓ Cleaned up all MCP clients")
    
    async def reconnect_agent(self, agent_name: str) -> bool:
        """
        Reconnect all servers for an agent
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if at least one server reconnected successfully
        """
        print(f"Reconnecting MCP client for agent '{agent_name}'...")
        
        # Remove existing client
        await self.remove_client(agent_name)
        
        # Add new client
        return await self.add_client(agent_name)
    
    def get_status_summary(self) -> Dict[str, Dict[str, any]]:
        """
        Get status summary for all agents
        
        Returns:
            Dictionary with agent status information
        """
        summary = {}
        
        with self.lock:
            for agent_name in self.clients:
                client = self.clients[agent_name]
                connection_status = self.connection_status.get(agent_name, {})
                
                total_servers = len(connection_status)
                connected_servers = sum(1 for connected in connection_status.values() if connected)
                all_tools = client.get_all_tools()
                
                summary[agent_name] = {
                    "total_servers": total_servers,
                    "connected_servers": connected_servers,
                    "total_tools": len(all_tools),
                    "tool_names": [tool["name"] for tool in all_tools],
                    "server_status": connection_status
                }
        
        return summary
