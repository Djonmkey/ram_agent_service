"""
oca_runner.py
=============

MCP wrapper for Hugging Face's **open-computer-agent** package
( https://huggingface.co/spaces/yifanlu/Open-Computer-Agent ).

Install
-------
pip install open-computer-agent

Environment
-----------
OCAGENT_MODEL        : optional, default "opencomputer/gpt-4o-mini-vision"

Task schema (command_parameters)
--------------------------------
{
  "task": "Describe what you want done (string)",
  "max_steps": 40             # optional
}
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from open_computer_agent import ComputerAgent  # type: ignore


# --------------------------------------------------------------------------- #
# Globals
# --------------------------------------------------------------------------- #
_MODEL = os.getenv("OCAGENT_MODEL", "opencomputer/gpt-4o-mini-vision")
_AGENT = ComputerAgent(model_name=_MODEL)


# --------------------------------------------------------------------------- #
# MCP entry-point
# --------------------------------------------------------------------------- #
def execute_command(
    command_parameters: Dict[str, Any],
    internal_params: Dict[str, Any],
) -> str:
    """
    Run a task through **Open-Computer-Agent**.

    Parameters
    ----------
    command_parameters
        Keys:
            * ``task``      – required, natural-language instruction
            * ``max_steps`` – optional, int
    internal_params
        Context from MCP; echoed back for traceability.

    Returns
    -------
    str
        JSON dump with ``tool_response`` and metadata.
    """
    task: str | None = command_parameters.get("task")
    if not task:
        raise ValueError("`task` is required for OCA runner.")

    max_steps: int = int(command_parameters.get("max_steps", 40))

    response: str = _AGENT.run(task, max_steps=max_steps)

    result: Dict[str, Any] = {
        "tool_response": response,
        "model": _MODEL,
        "request_id": internal_params.get("request_id"),
    }
    return json.dumps(result, ensure_ascii=False)
