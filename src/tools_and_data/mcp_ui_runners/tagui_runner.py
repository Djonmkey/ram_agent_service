"""
tagui_runner.py
===============

TagUI is an open-source browser & desktop RPA tool.  The Python
wrapper (`rpa`) converts a simple DSL into cross-platform automation.

Install
-------
pip install rpa  # brings TagUI runtime on first use

Task schema
-----------
command_parameters = {
  "script": [
      "tab to https://example.com",
      "type username hello@example.com",
      "type password secret",
      "click text(\"Login\")",
      "snap page to ./login.png"
  ]
}

Notes
-----
- The caller provides an ordered list of TagUI DSL commands (`script`).
- For large scripts you may also send a single multiline string.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import rpa as tagui  # noqa: E402


def execute_command(
    command_parameters: Dict[str, Any],
    internal_params: Dict[str, Any],
) -> str:
    """
    Run a TagUI script (headless by default).

    Returns
    -------
    str
        JSON string containing execution status and optional artifacts path.
    """
    # --- Prepare script ---------------------------------------------------- #
    script_raw = command_parameters.get("script")
    if script_raw is None:
        raise ValueError("`script` key required (list[str] or str).")

    script: str
    if isinstance(script_raw, list):
        script = "\n".join(script_raw)
    else:
        script = str(script_raw)

    headless: bool = bool(command_parameters.get("headless", True))

    # --- Execute ----------------------------------------------------------- #
    tagui.init(chrome_headless=headless)  # opens a browser session
    try:
        tagui.run(script)
        tagui.close()
        status = "success"
    except Exception as exc:  # pragma: no cover
        tagui.close()
        status = f"error: {exc}"

    return json.dumps(
        {
            "tool_response": status,
            "script_lines": len(script.splitlines()),
            "session_headless": headless,
            "run_id": internal_params.get("run_id"),
        },
        ensure_ascii=False,
    )
