"""
agent_s2_runner.py
==================

Wrapper for the *Agent S2* open-source desktop automation framework
( https://github.com/AgentOps/Agent-S2 ).

Install
-------
pip install agent-s2

Assumptions
-----------
- An Agent S2 server is reachable at ``AGENT_S2_ENDPOINT`` (default http://localhost:8080).
- The server exposes a POST /execute { "task": ... } → { "result": ... } API.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import requests

ENDPOINT: str = os.getenv("AGENT_S2_ENDPOINT", "http://localhost:8080/execute")


def execute_command(
    command_parameters: Dict[str, Any],
    internal_params: Dict[str, Any],
) -> str:
    """
    Forward a task to the Agent S2 REST API.

    Parameters
    ----------
    command_parameters :
        { "task": "...", "timeout": 300, ... }
    internal_params :
        Arbitrary MCP metadata.

    Returns
    -------
    str
        JSON with the Agent S2 reply, echoed MCP metadata, and HTTP status.
    """
    task: str | None = command_parameters.get("task")
    if not task:
        raise ValueError("`task` key is mandatory for Agent S2 execution.")

    timeout: int = int(command_parameters.get("timeout", 300))

    response = requests.post(
        ENDPOINT,
        json={"task": task, "timeout": timeout},
        timeout=timeout,
    )
    response.raise_for_status()

    return json.dumps(
        {
            "tool_response": response.json().get("result"),
            "status_code": response.status_code,
            "endpoint": ENDPOINT,
            "trace_id": internal_params.get("trace_id"),
        },
        ensure_ascii=False,
    )
