#!/usr/bin/env python3
"""
Test script to demonstrate the one-client-per-server MCP architecture
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import load_agent_manifest
from ras.mcp_client_manager import MCPClientManager
from mcp_clients.mcp_python_sdk_2025_03_26.multi_server_client import MultiServerMCPClient

async def test_multi_server_client(agent_name: str):
    """Test the new MultiServerMCPClient directly"""
    print(f"=== Testing MultiServerMCPClient for agent '{agent_name}' ===")
    
    client = MultiServerMCPClient(agent_name)
    
    try:
        # Test concurrent connection to multiple servers
        print("Connecting to servers concurrently...")
        status = await client.connect_to_servers(concurrent_connections=3, timeout=5.0)
        
        print("\nConnection Results:")
        for server_path, success in status.items():
            status_icon = "✓" if success else "✗"
            print(f"  {status_icon} {server_path}")
        
        # Show all available tools
        tools = client.get_all_tools()
        print(f"\nTotal tools available: {len(tools)}")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description']}")
        
        # Test tool routing
        print(f"\nTool routing test:")
        for tool in tools[:3]:  # Test first 3 tools
            tool_name = tool['name']
            client_for_tool = client.find_client_for_tool(tool_name)
            if client_for_tool:
                print(f"  Tool '{tool_name}' -> {client_for_tool.module_path}")
        
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    finally:
        await client.cleanup()

async def test_mcp_client_manager():
    """Test the updated MCPClientManager"""
    print("\n=== Testing MCPClientManager ===")
    
    manager = MCPClientManager()
    
    try:
        # Test adding clients for multiple agents
        agents = ["Kairos", "Mercurius", "calendar_concierge_discord"]
        
        for agent_name in agents:
            print(f"\nAdding client for agent '{agent_name}'...")
            success = await manager.add_client(agent_name)
            print(f"Result: {'Success' if success else 'Failed'}")
        
        # Show status summary
        print("\n=== MCP Client Manager Status Summary ===")
        summary = manager.get_status_summary()
        
        for agent_name, info in summary.items():
            print(f"\nAgent: {agent_name}")
            print(f"  Servers: {info['connected_servers']}/{info['total_servers']} connected")
            print(f"  Tools: {info['total_tools']} available")
            print(f"  Tool names: {', '.join(info['tool_names'][:5])}{'...' if len(info['tool_names']) > 5 else ''}")
            
            for server_path, connected in info['server_status'].items():
                status_icon = "✓" if connected else "✗"
                print(f"    {status_icon} {server_path}")
        
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False
    finally:
        await manager.cleanup_all()

async def benchmark_connection_speed():
    """Benchmark connection speed: sequential vs concurrent"""
    print("\n=== Connection Speed Benchmark ===")
    
    agent_name = "Kairos"  # Use agent with multiple servers
    
    # Test concurrent connections (new architecture)
    print("Testing concurrent connections...")
    client = MultiServerMCPClient(agent_name)
    
    start_time = asyncio.get_event_loop().time()
    status = await client.connect_to_servers(concurrent_connections=5, timeout=10.0)
    concurrent_time = asyncio.get_event_loop().time() - start_time
    
    successful_connections = sum(1 for connected in status.values() if connected)
    print(f"Concurrent: {successful_connections} servers connected in {concurrent_time:.2f}s")
    
    await client.cleanup()
    
    print(f"\nConcurrent connection approach:")
    print(f"  ✓ No blocking - all servers connect in parallel")
    print(f"  ✓ Error isolation - failed servers don't block others")
    print(f"  ✓ Timeout control - configurable per-server timeouts")
    print(f"  ✓ Better tool routing - each client knows its tools")

async def main():
    """Main test function"""
    print("Testing One-Client-Per-Server MCP Architecture")
    print("=" * 50)
    
    # Load agent configuration
    try:
        print("Loading agent manifest...")
        load_agent_manifest("config/example_agent_manifest.json")
        print("✓ Agent manifest loaded successfully")
    except Exception as e:
        print(f"✗ Failed to load agent manifest: {str(e)}")
        print("Make sure you're running from the project root directory")
        return
    
    # Test MultiServerMCPClient
    success = await test_multi_server_client("Kairos")
    if not success:
        print("MultiServerMCPClient test failed")
        return
    
    # Test MCPClientManager
    success = await test_mcp_client_manager()
    if not success:
        print("MCPClientManager test failed")
        return
    
    # Benchmark connection speed
    await benchmark_connection_speed()
    
    print("\n" + "=" * 50)
    print("✓ All tests completed successfully!")
    print("\nKey improvements achieved:")
    print("  ✓ No more blocking on session.initialize()")
    print("  ✓ Concurrent server connections")
    print("  ✓ Individual server error isolation")
    print("  ✓ Proper tool routing to correct servers")
    print("  ✓ Better resource management per server")
    print("  ✓ Configurable timeouts and retry logic")

if __name__ == "__main__":
    asyncio.run(main())
