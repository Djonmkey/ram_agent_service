#!/usr/bin/env python3

import asyncio
import sys
import os
import logging
from typing import Any, Sequence
from mcp.types import InitializeResult, Implementation
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent, ImageContent, EmbeddedResource
import mcp.types as types

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/write_file_mcp.log'),
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger('write_file_server')

logger.info("Starting write_file.py MCP server...")


logger.info("Creating write-file-server instance...")
server = Server("write-file-server")
logger.info("Server instance created successfully")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    logger.info("Handling list_tools request")
    return [
        Tool(
            name="write_file",
            description="Write content to a file at the specified path",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The file path to write to (can be absolute or relative)"
                    },
                    "content": {
                        "type": "string", 
                        "description": "The content to write to the file"
                    },
                    "create_directories": {
                        "type": "boolean",
                        "description": "Whether to create parent directories if they don't exist",
                        "default": True
                    }
                },
                "required": ["file_path", "content"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent | ImageContent | EmbeddedResource]:
    """
    Handle tool execution requests.
    """
    logger.info(f"Handling tool call: {name} with arguments: {arguments}")
    if name == "write_file":
        file_path = arguments.get("file_path")
        content = arguments.get("content")
        create_directories = arguments.get("create_directories", True)
        
        if not file_path:
            return [TextContent(type="text", text="Error: file_path is required")]
        
        if content is None:
            return [TextContent(type="text", text="Error: content is required")]
        
        try:
            # Convert to absolute path if relative
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            
            # Create parent directories if requested
            if create_directories:
                directory = os.path.dirname(file_path)
                if directory:
                    os.makedirs(directory, exist_ok=True)
            
            # Write the file
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(content)
            
            return [TextContent(type="text", text=f"Successfully wrote to file: {file_path}")]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Error writing file: {str(e)}")]
    
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    logger.info("Starting main() function")
    try:
        # Run the server using stdin/stdout streams
        logger.info("Setting up stdio_server...")
        async with stdio_server() as (read_stream, write_stream):
            logger.info("stdio_server created, starting server.run()")
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
                    name="write-file-server",
                    version="1.0.0"
                ),
            ),
        )
        logger.info("Server run completed")
    except Exception as e:
        logger.error(f"Error in main(): {e}", exc_info=True)
        raise


# Legacy support for the old execute_command interface
def execute_command(command_parameters: dict[str, Any], internal_params: dict[str, Any]) -> str:
    """Legacy execute_command interface for backward compatibility"""
    root_path = command_parameters.get("file_path", "")
    model_parameters = command_parameters.get("model_parameters", "")

    # Parse the old format: <file_path> """<content>"""
    try:
        params = model_parameters.split('"""')
        if len(params) >= 2:
            filename = params[0].replace("'", "").strip()
            contents = params[1].strip()
        else:
            # Fallback if the format is different
            filename = model_parameters
            contents = command_parameters.get("content", "")
        
        if root_path:
            file_path = os.path.join(root_path, filename)
        else:
            file_path = filename
        
        # Ensure the directory exists
        directory = os.path.dirname(file_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as file:
            file.write(contents)
        
        return f"Successfully wrote to file: {file_path}"
        
    except Exception as e:
        return f"Error writing file: {str(e)}"


if __name__ == "__main__":
    logger.info("Script started, running main()")
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error running main(): {e}", exc_info=True)
        sys.exit(1)
    logger.info("Script completed")
