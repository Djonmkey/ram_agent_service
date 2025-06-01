"""
pyautogui_runner.py
===================

Thin, deterministic MCP wrapper that executes a *list of GUI actions*
locally via PyAutoGUI (cross-platform mouse / keyboard automation).

Install
-------
pip install pyautogui pygetwindow

Task schema
-----------
command_parameters = {
  "actions": [
      {"type": "click", "x": 100, "y": 200, "button": "left"},
      {"type": "write", "text": "hello world", "interval": 0.05},
      {"type": "hotkey", "keys": ["ctrl", "s"]}
  ],
  "pause": 0.3          # optional default pause between actions (sec)
}
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List

import pyautogui

# Fail fast if user moves mouse to upper-left (emergency abort)
pyautogui.FAILSAFE = True


def _run_click(action: Dict[str, Any]) -> None:
    pyautogui.click(
        x=int(action["x"]),
        y=int(action["y"]),
        button=str(action.get("button", "left")),
    )


def _run_write(action: Dict[str, Any]) -> None:
    pyautogui.write(
        str(action["text"]),
        interval=float(action.get("interval", 0.0)),
    )


def _run_hotkey(action: Dict[str, Any]) -> None:
    keys = action["keys"]
    if isinstance(keys, str):
        keys = [keys]
    pyautogui.hotkey(*keys)


_ACTION_MAP = {
    "click": _run_click,
    "write": _run_write,
    "hotkey": _run_hotkey,
}


def execute_command(
    command_parameters: Dict[str, Any],
    internal_params: Dict[str, Any],
) -> str:
    """
    Sequentially execute GUI **actions** using PyAutoGUI.

    Returns a short JSON summary (successful step count & runtime).

    Raises
    ------
    KeyError
        If an action dict is missing required keys.
    ValueError
        If unknown action ``type`` is encountered.
    """
    actions: List[Dict[str, Any]] = command_parameters.get("actions", [])
    if not actions:
        raise ValueError("`actions` list is required.")

    pause: float = float(command_parameters.get("pause", 0.3))

    start_ts: float = time.time()
    for i, action in enumerate(actions, start=1):
        handler = _ACTION_MAP.get(action["type"])
        if handler is None:
            raise ValueError(f"Unsupported action type: {action['type']}")
        handler(action)
        time.sleep(pause)

    duration: float = round(time.time() - start_ts, 3)
    return json.dumps(
        {
            "tool_response": f"Executed {len(actions)} steps in {duration}s",
            "mcp_context": internal_params,
        },
        ensure_ascii=False,
    )
