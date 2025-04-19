# mcp_commands/lightrag/goals_context.py

import os
from typing import Any, Dict
from mcp_commands.lightrag.lightrag import LightRAG

INDEX_NAME = "goals_index"

def resolve_goal_dir(internal_params: Dict[str, Any]) -> str:
    return os.path.abspath(internal_params.get("goal_dir", "goals"))

def execute_command(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    Searches indexed Markdown goal documents for relevant context using LightRAG.
    """
    query = command_parameters.get("query")
    if not query:
        return "Error: 'query' parameter is required."

    try:
        rag = LightRAG(name=INDEX_NAME)
        rag.load_index(f"{INDEX_NAME}.lrag")
        results = rag.query(query, top_k=5)

        if not results:
            return "No relevant goal context found."

        return "\n\n".join([r["content"] for r in results])

    except Exception as e:
        return f"Error querying LightRAG: {str(e)}"

def rebuild_index(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    Rebuilds the LightRAG index from Markdown documents in the goal directory.
    """
    try:
        goal_dir = resolve_goal_dir(internal_params)

        if not os.path.exists(goal_dir):
            return f"Error: Goal directory {goal_dir} does not exist."

        rag = LightRAG(name=INDEX_NAME)
        rag.index_local_files(goal_dir, file_extensions=[".md"])
        rag.save_index(f"{INDEX_NAME}.lrag")

        return f"✅ Rebuilt index '{INDEX_NAME}.lrag' from files in {goal_dir}"

    except Exception as e:
        return f"Error rebuilding index: {str(e)}"
