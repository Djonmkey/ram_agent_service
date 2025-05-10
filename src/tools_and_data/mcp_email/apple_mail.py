"""
calendar_concierge_commands.py
==============================

MCP command implementations for the **Calendar Concierge** agent.

Each function name matches the MCP command verb and follows the
standard signature used across David McKee's RAM Agent Service::

    def <command>(command_parameters: Dict[str, Any],
                  internal_params: Dict[str, Any]) -> str:

* ``command_parameters`` - the JSON payload supplied by the caller
  (usually another agent). It must match the schema defined in the
  Calendar Concierge system prompt.
* ``internal_params`` - runtime context provided by the agent framework
  (e.g. auth tokens, export directory paths).

All functions return **JSON-encoded strings** so upstream agents can
forward the raw payload directly to Discord or other transports.

The module relies on :pymod:`calendar_integration` for CalDAV pushes
and ``.ics`` fallback logic.

Requirements
------------
::

    pip install caldav python-dateutil requests

Storage layout
--------------
* Event JSON records live in ``~/ram_data/horizons/events/<uid>.json``.
* Daily JSON-Lines logs live in ``~/ram_data/logs/cal_concierge_<YYYY-MM-DD>.jsonl``.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import dateutil.parser as dt_parser
from calendar_integration import (
    build_vevent,
    create_and_push_event,
    push_event_to_icloud,
    write_ics_file,
)

# ---------------------------------------------------------------------
# Constants & helpers
# ---------------------------------------------------------------------

STORE_DIR = Path(os.path.expanduser("~/ram_data/horizons/events"))
LOG_DIR = Path(os.path.expanduser("~/ram_data/logs"))
STORE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# America/New_York (EDT / EST handled by dateutil)
TZ_DEFAULT = timezone(timedelta(hours=-4))


def _log(action: str, payload: Dict[str, Any]) -> None:
    """Append a JSON-line log for auditing."""
    log_path = LOG_DIR / f"cal_concierge_{datetime.now(timezone.utc).date()}.jsonl"
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        **payload,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _uid() -> str:  # RFC-822 style UID helper
    return uuid.uuid4().hex.upper()


def _event_path(uid: str) -> Path:
    return STORE_DIR / f"{uid}.json"


def _load_event(uid: str) -> Dict[str, Any]:
    p = _event_path(uid)
    if not p.exists():
        raise FileNotFoundError(f"Event {uid} not found.")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_event(event: Dict[str, Any]) -> None:
    _event_path(event["uid"]).write_text(
        json.dumps(event, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _parse_iso(dt_str: str) -> datetime:
    return dt_parser.isoparse(dt_str)


def _within_window(event: Dict[str, Any], win_from: datetime, win_to: datetime) -> bool:
    start = _parse_iso(event["dt_start"]).astimezone(timezone.utc)
    return win_from <= start <= win_to


# ---------------------------------------------------------------------
# MCP command implementations
# ---------------------------------------------------------------------

def create_event(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /create_event – create a new calendar entry (single or recurring).
    """
    try:
        data = command_parameters.copy()
        data.setdefault("uid", _uid())
        data.setdefault("timezone", "America/New_York")
        uid = data["uid"]

        if "dt_start" not in data or ("duration" not in data and "dt_end" not in data):
            raise ValueError("dt_start and duration|dt_end required.")

        tzinfo = timezone.utc if data["timezone"].upper() == "UTC" else TZ_DEFAULT
        dt_start = _parse_iso(data["dt_start"]).astimezone(tzinfo)

        # crude ISO-8601 duration parse (PT#H#M)
        if "duration" in data:
            iso = data["duration"]
            hours = int(iso.split("T")[1].split("H")[0]) if "H" in iso else 0
            minutes = (
                int(iso.split("H")[1].split("M")[0]) if "H" in iso and "M" in iso else
                int(iso.split("T")[1].split("M")[0]) if "M" in iso else 0
            )
            duration_td = timedelta(hours=hours, minutes=minutes)
        else:
            duration_td = _parse_iso(data["dt_end"]) - dt_start

        # Build VEVENT and push
        vevent = build_vevent(
            summary=data["summary"],
            description=data.get("description", ""),
            dt_start=dt_start,
            duration=duration_td,
            uid=uid,
        )

        cal_uid, ics_path = create_and_push_event(
            summary=data["summary"],
            description=data.get("description", ""),
            dt_start=dt_start,
            duration=duration_td,
        )

        data["calendar_uid"] = cal_uid
        if ics_path:
            data["fallback_path"] = str(ics_path)

        _save_event(data)
        _log("create", {"uid": uid})

        return json.dumps({"status": "ok", "data": data, "uid": uid})
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"status": "error", "error": {"code": "internal", "message": str(exc)}}
        )


def get_event(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /get_event – return the full event object for *uid*.
    """
    try:
        uid = command_parameters["uid"]
        event = _load_event(uid)
        return json.dumps({"status": "ok", "data": event})
    except FileNotFoundError:
        return json.dumps(
            {"status": "error", "error": {"code": "not_found", "message": "uid not found"}}
        )


def list_events(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /list_events – list events in a time window (defaults to current week).
    """
    try:
        now = datetime.now(TZ_DEFAULT)
        win_from = _parse_iso(command_parameters.get("from", now.isoformat()))
        win_to = _parse_iso(
            command_parameters.get("to", (now + timedelta(days=7)).isoformat())
        )

        events = []
        for file in STORE_DIR.glob("*.json"):
            event = json.loads(file.read_text(encoding="utf-8"))
            if _within_window(event, win_from, win_to):
                events.append(event)

        events.sort(key=lambda e: e["dt_start"])
        return json.dumps({"status": "ok", "data": events})
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"status": "error", "error": {"code": "internal", "message": str(exc)}}
        )


def update_event(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /update_event – patch fields on an existing event.
    """
    try:
        uid = command_parameters["uid"]
        patch = command_parameters.get("patch", {})
        event = _load_event(uid)

        event.update(patch)
        _save_event(event)
        _log("update", {"uid": uid})

        # Re-push to CalDAV
        tzinfo = timezone.utc if event.get("timezone") == "UTC" else TZ_DEFAULT
        dt_start = _parse_iso(event["dt_start"]).astimezone(tzinfo)

        dur_iso = event["duration"]
        hours = int(dur_iso.split("T")[1].split("H")[0]) if "H" in dur_iso else 0
        minutes = (
            int(dur_iso.split("H")[1].split("M")[0]) if "H" in dur_iso and "M" in dur_iso else
            int(dur_iso.split("T")[1].split("M")[0]) if "M" in dur_iso else 0
        )
        duration_td = timedelta(hours=hours, minutes=minutes)

        vevent = build_vevent(
            summary=event["summary"],
            description=event.get("description", ""),
            dt_start=dt_start,
            duration=duration_td,
            uid=uid,
        )

        push_event_to_icloud(
            vevent=vevent,
            calendar_url=os.getenv("ICLOUD_CALDAV_URL"),
            username=os.getenv("ICLOUD_USER"),
            app_password=os.getenv("ICLOUD_APP_PASSWORD"),
        )

        return json.dumps({"status": "ok", "data": event, "uid": uid})
    except FileNotFoundError:
        return json.dumps(
            {"status": "error", "error": {"code": "not_found", "message": "uid not found"}}
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"status": "error", "error": {"code": "internal", "message": str(exc)}}
        )


def delete_event(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /delete_event – remove an event (scope defaults to ALL for recurring).
    """
    try:
        uid = command_parameters["uid"]
        scope = command_parameters.get("scope", "ALL")
        path = _event_path(uid)
        if not path.exists():
            raise FileNotFoundError

        # TODO: CalDAV DELETE (and RRULE rewrite for scope=THIS/FUTURE)
        path.unlink()
        _log("delete", {"uid": uid, "scope": scope})

        return json.dumps({"status": "ok", "uid": uid})
    except FileNotFoundError:
        return json.dumps(
            {"status": "error", "error": {"code": "not_found", "message": "uid not found"}}
        )


def search_events(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /search_events – simple text search across summary/description/horizon.
    """
    try:
        query = command_parameters["query"].lower()
        win_from = _parse_iso(
            command_parameters.get(
                "from", datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()
            )
        )
        win_to = _parse_iso(
            command_parameters.get(
                "to", (datetime.now(TZ_DEFAULT) + timedelta(days=365)).isoformat()
            )
        )
        max_results = int(command_parameters.get("max_results", 50))

        matches: List[Dict[str, Any]] = []
        for file in STORE_DIR.glob("*.json"):
            event = json.loads(file.read_text(encoding="utf-8"))
            haystack = " ".join(
                [
                    event.get("summary", ""),
                    event.get("description", ""),
                    event.get("horizon", ""),
                ]
            ).lower()
            if query in haystack and _within_window(event, win_from, win_to):
                matches.append(event)
                if len(matches) >= max_results:
                    break

        matches.sort(key=lambda e: e["dt_start"])
        return json.dumps({"status": "ok", "data": matches})
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"status": "error", "error": {"code": "internal", "message": str(exc)}}
        )


def free_busy(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /free_busy – return merged busy blocks for clash detection.
    """
    try:
        now = datetime.now(TZ_DEFAULT)
        win_from = _parse_iso(command_parameters.get("from", now.isoformat()))
        win_to = _parse_iso(
            command_parameters.get("to", (now + timedelta(days=7)).isoformat())
        )

        busy_blocks: List[Tuple[datetime, datetime]] = []
        for file in STORE_DIR.glob("*.json"):
            event = json.loads(file.read_text(encoding="utf-8"))
            start = _parse_iso(event["dt_start"]).astimezone(timezone.utc)

            iso = event["duration"]
            hours = int(iso.split("T")[1].split("H")[0]) if "H" in iso else 0
            minutes = (
                int(iso.split("H")[1].split("M")[0]) if "H" in iso and "M" in iso else
                int(iso.split("T")[1].split("M")[0]) if "M" in iso else 0
            )
            dur = timedelta(hours=hours, minutes=minutes)
            end = start + dur

            if start <= win_to and end >= win_from:
                busy_blocks.append((start, end))

        # merge overlaps
        busy_blocks.sort(key=lambda t: t[0])
        merged: List[Tuple[datetime, datetime]] = []
        for blk in busy_blocks:
            if not merged or blk[0] > merged[-1][1]:
                merged.append(list(blk))  # type: ignore[arg-type]
            else:
                merged[-1][1] = max(merged[-1][1], blk[1])  # type: ignore[index]

        merged_iso = [{"start": s.isoformat(), "end": e.isoformat()} for s, e in merged]
        return json.dumps({"status": "ok", "data": merged_iso})
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"status": "error", "error": {"code": "internal", "message": str(exc)}}
        )


def export_ics(command_parameters: Dict[str, Any], internal_params: Dict[str, Any]) -> str:
    """
    /export_ics – generate an `.ics` file and return a local download URL.
    """
    try:
        uid = command_parameters["uid"]
        event = _load_event(uid)

        tzinfo = timezone.utc if event.get("timezone") == "UTC" else TZ_DEFAULT
        dt_start = _parse_iso(event["dt_start"]).astimezone(tzinfo)

        iso = event["duration"]
        hours = int(iso.split("T")[1].split("H")[0]) if "H" in iso else 0
        minutes = (
            int(iso.split("H")[1].split("M")[0]) if "H" in iso and "M" in iso else
            int(iso.split("T")[1].split("M")[0]) if "M" in iso else 0
        )
        duration_td = timedelta(hours=hours, minutes=minutes)

        vevent = build_vevent(
            summary=event["summary"],
            description=event.get("description", ""),
            dt_start=dt_start,
            duration=duration_td,
            uid=uid,
        )

        ics_path = Path(internal_params.get("export_dir", "~/Downloads")).expanduser() / f"{uid}.ics"
        write_ics_file(vevent, ics_path)

        return json.dumps(
            {"status": "ok", "data": {"download_url": f"file://{ics_path}"}, "uid": uid}
        )
    except FileNotFoundError:
        return json.dumps(
            {"status": "error", "error": {"code": "not_found", "message": "uid not found"}}
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps(
            {"status": "error", "error": {"code": "internal", "message": str(exc)}}
        )
