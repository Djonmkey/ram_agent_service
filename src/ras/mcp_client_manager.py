import asyncio
import importlib.util
import sys
from typing import Dict, Optional, List, Any
from pathlib import Path
import threading

from src.ras.agent_config_buffer import get_tools_and_data_mcp_commands_config

class MCPClientManager:
    """
    Generic MCP Client Manager using duck typing.
    Manages client modules without knowing their specific implementation.
    Each agent gets its own client module instance.
    """
    
    def __init__(self):
        self.client_modules: Dict[str, Any] = {}  # agent_name -> loaded module
        self.client_instances: Dict[str, Any] = {}  # agent_name -> client instance
        self.lock = threading.Lock()
        self.connection_status: Dict[str, bool] = {}  # agent_name -> connection success
        
    def _load_module(self, module_path: str) -> Any:
        """
        Dynamically load a Python module from a file path.
        
        Args:
            module_path: File path to the Python module
            
        Returns:
            The loaded module
        """
        # Convert to absolute path
        abs_path = Path(module_path).resolve()
        
        if not abs_path.exists():
            # Try relative to project root
            project_root = Path.cwd()
            abs_path = project_root / module_path
            
        if not abs_path.exists():
            raise FileNotFoundError(f"Module not found: {module_path}")
        
        # Create a unique module name
        module_name = f"mcp_client_{abs_path.stem}_{id(abs_path)}"
        
        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, abs_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {abs_path}")
            
        module = importlib.util.module_from_spec(spec)
        
        # Add to sys.modules temporarily for the exec
        sys.modules[module_name] = module
        
        try:
            spec.loader.exec_module(module)
        finally:
            # Clean up sys.modules
            sys.modules.pop(module_name, None)
        
        return module
    
    async def add_client(self, agent_name: str, module_path: str) -> bool:
        """
        Load and initialize a client module for an agent.
        Uses duck typing - expects the module to have 'main' and 'process_query' functions.
        
        Args:
            agent_name: Name of the agent
            module_path: Path to the client module
            
        Returns:
            True if client was successfully added, False otherwise
        """
        with self.lock:
            if agent_name in self.client_modules:
                print(f"Client for agent '{agent_name}' already exists")
                return True
        
        try:
            print(f"Loading MCP client module for agent '{agent_name}' from {module_path}")
            
            # Load the module
            module = self._load_module(module_path)
            
            # Verify it has the required methods (duck typing)
            if not hasattr(module, 'main') or not callable(getattr(module, 'main')):
                raise AttributeError(f"Module {module_path} does not have a 'main' function")
            
            if not hasattr(module, 'process_query') or not callable(getattr(module, 'process_query')):
                raise AttributeError(f"Module {module_path} does not have a 'process_query' function")
            
            # Call the module's main() function to initialize
            # The main function should handle its own server connections
            print(f"Initializing MCP client for agent '{agent_name}'...")
            client_instance = await module.main(agent_name)
            
            # Store references
            with self.lock:
                self.client_modules[agent_name] = module
                self.client_instances[agent_name] = client_instance
                self.connection_status[agent_name] = True
            
            print(f"✓ Successfully added MCP client for agent '{agent_name}'")
            return True
            
        except Exception as e:
            print(f"✗ Error adding MCP client for agent '{agent_name}': {str(e)}")
            self.connection_status[agent_name] = False
            return False
    
    async def add_client_from_config(self, agent_name: str) -> bool:
        """
        Add a client based on agent configuration.
        Looks for mcp_client_python_code_module in tools_and_data config.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if client was added, False if no config or failed
        """
        # Get tools and data config for the agent
        tools_and_data_config = get_tools_and_data_mcp_commands_config(agent_name)
        
        if not tools_and_data_config:
            print(f"No tools and data config found for agent '{agent_name}'")
            return False
        
        # Look for mcp_client_python_code_module
        module_path = tools_and_data_config.get('mcp_client_python_code_module')
        
        if not module_path:
            print(f"No mcp_client_python_code_module configured for agent '{agent_name}'")
            return False
        
        return await self.add_client(agent_name, module_path)
    
    def get_client_modules(self, agent_name: str) -> Optional[Any]:
        """
        Get the client module for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Client module or None if not found
        """
        with self.lock:
            return self.client_modules.get(agent_name)
    
    def get_client_instances(self, agent_name: str) -> Optional[Any]:
        """
        Get the client instance for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Client instance or None if not found
        """
        with self.lock:
            return self.client_instances.get(agent_name)
    
    def has_client(self, agent_name: str) -> bool:
        """
        Check if a client exists for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if client exists, False otherwise
        """
        with self.lock:
            return agent_name in self.client_modules
    
    async def process_query(self, agent_name: str, query: str, meta_data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Process a query using the agent's client module.
        Uses duck typing - calls the module's process_query function.
        
        Args:
            agent_name: Name of the agent
            query: Query to process
            meta_data: Optional metadata
            
        Returns:
            Response from the client or None if client not found
        """
        module = self.get_client(agent_name)
        
        if not module:
            print(f"No MCP client found for agent '{agent_name}'")
            return None
        
        try:
            # Call the module's process_query function
            # It should accept (agent_name, query, meta_data)
            result = await module.process_query(agent_name, query, meta_data)
            return result
        except Exception as e:
            print(f"Error processing query for agent '{agent_name}': {str(e)}")
            return None
    
    def list_agents(self) -> List[str]:
        """
        Get list of all agent names with active clients.
        
        Returns:
            List of agent names
        """
        with self.lock:
            return list(self.client_modules.keys())
    
    def get_connection_status(self, agent_name: str) -> bool:
        """
        Get connection status for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if connected, False otherwise
        """
        return self.connection_status.get(agent_name, False)
    
    async def remove_client(self, agent_name: str) -> bool:
        """
        Remove and cleanup MCP client for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if client was removed, False if not found
        """
        module = None
        instance = None
        
        with self.lock:
            module = self.client_modules.pop(agent_name, None)
            instance = self.client_instances.pop(agent_name, None)
            self.connection_status.pop(agent_name, None)
        
        if module:
            try:
                # Check if the module has a cleanup method (duck typing)
                if hasattr(module, 'cleanup') and callable(getattr(module, 'cleanup')):
                    await module.cleanup()
                # Or if the instance has a cleanup method
                elif instance and hasattr(instance, 'cleanup') and callable(getattr(instance, 'cleanup')):
                    await instance.cleanup()
                
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
        Cleanup all MCP clients.
        """
        agents_to_cleanup = self.list_agents()
        
        cleanup_tasks = []
        for agent_name in agents_to_cleanup:
            cleanup_tasks.append(self.remove_client(agent_name))
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        
        print("✓ Cleaned up all MCP clients")
    
    async def reconnect_agent(self, agent_name: str) -> bool:
        """
        Reconnect client for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            True if reconnection successful
        """
        print(f"Reconnecting MCP client for agent '{agent_name}'...")
        
        # Remove existing client
        await self.remove_client(agent_name)
        
        # Add new client from config
        return await self.add_client_from_config(agent_name)
    
    def get_status_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status summary for all agents.
        
        Returns:
            Dictionary with agent status information
        """
        summary = {}
        
        with self.lock:
            for agent_name in self.client_modules:
                summary[agent_name] = {
                    "connected": self.connection_status.get(agent_name, False),
                    "has_module": agent_name in self.client_modules,
                    "has_instance": agent_name in self.client_instances
                }
        
        return summary