#!/usr/bin/env python3

import asyncio
import sys
import os
from typing import Any, Sequence
from mcp.types import InitializeResult, Implementation
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types


server = Server("read-file-server")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        Tool(
            name="read_file",
            description="Read content from a file at the specified path",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The file path to read from (can be absolute or relative)"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "The text encoding to use when reading the file",
                        "default": "utf-8"
                    }
                },
                "required": ["file_path"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    if name == "read_file":
        file_path = arguments.get("file_path")
        encoding = arguments.get("encoding", "utf-8")
        
        if not file_path:
            return [TextContent(type="text", text="Error: file_path is required")]
        
        try:
            # Convert to absolute path if relative
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            
            # Check if file exists
            if not os.path.exists(file_path):
                return [TextContent(type="text", text=f"Error: File does not exist: {file_path}")]
            
            # Check if it's a file (not a directory)
            if not os.path.isfile(file_path):
                return [TextContent(type="text", text=f"Error: Path is not a file: {file_path}")]
            
            # Read the file
            with open(file_path, "r", encoding=encoding) as file:
                content = file.read()
            
            return [TextContent(type="text", text=content)]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Error reading file: {str(e)}")]
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    # Run the server using stdin/stdout streams
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializeResult(
                protocolVersion="2024-11-05",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
                serverInfo=Implementation(
                    name="read-file-server",
                    version="1.0.0"
                ),
            ),
        )


# Legacy support for the old execute_command interface
def execute_command(command_parameters: dict[str, Any], internal_params: dict[str, Any]) -> str:
    """Legacy execute_command interface for backward compatibility"""
    root_path = command_parameters.get("file_path")
    filename = command_parameters.get("filename")
    if not filename:
        filename = command_parameters["model_parameters"]

    filename = filename.replace("'", "").strip()
    file_path_name = filename

    if root_path:
        file_path_name = os.path.join(root_path, filename)
    
    try:
        with open(file_path_name, "r", encoding="utf-8") as file:
            contents = file.read()
        return contents
    except Exception as e:
        return f"Error reading file: {str(e)}"


if __name__ == "__main__":
    asyncio.run(main())
