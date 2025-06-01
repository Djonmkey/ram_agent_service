"""
openai_cua_runner.py
===================

MCP wrapper around OpenAI's **computer_use** tool.  The call streams a natural-
language task to the model and returns its textual response plus metadata.

Environment
-----------
- ``OPENAI_API_KEY``             : required
- ``OPENAI_CUA_MODEL`` (optional): defaults to ``gpt-4o-mini-cua``

Example
-------
>>> execute_command({"task": "Open vscode.dev"}, {})
'{"tool_response": "..."}'
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import openai


# --------------------------------------------------------------------------- #
# Constants & client
# --------------------------------------------------------------------------- #
openai.api_key = os.environ["OPENAI_API_KEY"]
MODEL_NAME: str = os.getenv("OPENAI_CUA_MODEL", "gpt-4o-mini-cua")


# --------------------------------------------------------------------------- #
# Public MCP entry-point
# --------------------------------------------------------------------------- #
def execute_command(
    command_parameters: Dict[str, Any],
    internal_params: Dict[str, Any],
) -> str:
    """
    Invoke an OpenAI **computer_use** run.

    Parameters
    ----------
    command_parameters :
        Expected keys::

            {
              "task"   : str,   # required – what you want done
              "timeout": int    # optional – sec, default 180
            }

    internal_params :
        Opaque values from the MCP runtime; passed through for tracing.

    Returns
    -------
    str
        JSON string with keys ``tool_response`` (LLM text), ``model``,
        and any passthrough identifiers.
    """
    # --- Validation -------------------------------------------------------- #
    task: str | None = command_parameters.get("task")
    if not task:
        raise ValueError("`task` (str) is required in command_parameters.")

    timeout: int = int(command_parameters.get("timeout", 180))

    # --- LLM call ---------------------------------------------------------- #
    completion = openai.ChatCompletion.create(
        model=MODEL_NAME,
        tools=[{"type": "computer_use"}],  # activates CUA
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert computer operator.  Complete the user's "
                    "task exactly and stop when finished."
                ),
            },
            {"role": "user", "content": task},
        ],
        timeout=timeout,
    )

    # --- Return ------------------------------------------------------------ #
    result: Dict[str, Any] = {
        "tool_response": completion.choices[0].message.content,
        "model": MODEL_NAME,
        "conversation_id": internal_params.get("conversation_id"),
    }
    return json.dumps(result, ensure_ascii=False)
