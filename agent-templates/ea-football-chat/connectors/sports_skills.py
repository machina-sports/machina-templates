"""sports-skills pyscript connector — single dispatcher entry point.

Machina calls pyscript functions with request_data = {
    "connector_exec": "football",
    "headers": {...},
    "params": { ...task inputs... },
    ...
}

Task inputs land under request_data["params"]. Must return:
    {"status": True, "data": <payload>}          on success
    {"status": False, "data": {}, "error": {"code": N, "message": "..."}}  on error
"""

from __future__ import annotations

import os
import sys
import subprocess

_CUSTOM_PATH = "/tmp/sports_skills_pkg"

_ALLOWED = {
    "get_current_season",
    "get_competitions",
    "get_competition_seasons",
    "get_season_schedule",
    "get_season_standings",
    "get_season_leaders",
    "get_season_teams",
    "search_team",
    "search_player",
    "get_team_profile",
    "get_team_schedule",
    "get_daily_schedule",
    "get_event_summary",
    "get_event_lineups",
    "get_event_statistics",
    "get_event_timeline",
    "get_event_xg",
    "get_event_players_statistics",
    "get_head_to_head",
    "get_missing_players",
    "get_season_transfers",
    "get_player_profile",
    "get_player_season_stats",
}


def _get_connector():
    if os.path.isdir(_CUSTOM_PATH) and _CUSTOM_PATH not in sys.path:
        sys.path.insert(0, _CUSTOM_PATH)
    try:
        from sports_skills.football import _connector
        return _connector
    except ImportError:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "sports-skills>=0.4.0",
             "--target", _CUSTOM_PATH, "-q", "--no-cache-dir"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pip install failed (exit {result.returncode}): {result.stderr.strip()[:500]}"
            )
        if _CUSTOM_PATH not in sys.path:
            sys.path.insert(0, _CUSTOM_PATH)
        from sports_skills.football import _connector
        return _connector


def football(request_data):
    """Dispatch to the named sports_skills.football function.

    request_data["params"] contains the evaluated task inputs.
    Reads request_data["params"]["command"] to pick the function;
    forwards remaining params as the function's input payload.
    """
    task_inputs = request_data.get("params", {})
    command = task_inputs.get("command")
    if not command:
        return {"status": False, "data": {}, "error": {"code": 400, "message": "'command' input is required"}}

    if command not in _ALLOWED:
        return {"status": False, "data": {}, "error": {"code": 400, "message": f"Unknown command: {command}"}}

    try:
        _connector = _get_connector()
    except Exception as exc:
        return {"status": False, "data": {}, "error": {"code": 500, "message": f"sports-skills install failed: {exc}"}}

    fn = getattr(_connector, command, None)
    if fn is None:
        return {"status": False, "data": {}, "error": {"code": 404, "message": f"Command not found: {command}"}}

    forwarded = {k: v for k, v in task_inputs.items() if k != "command"}

    try:
        data = fn({"params": forwarded})
    except Exception as exc:
        return {"status": False, "data": {}, "error": {"code": 500, "message": f"{command} failed: {exc}"}}

    return {"status": True, "data": data}
