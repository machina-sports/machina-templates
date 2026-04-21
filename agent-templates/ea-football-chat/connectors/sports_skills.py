"""sports-skills pyscript connector — single dispatcher entry point.

Framework contract discovered by probing the pyscript invoker:
- Inputs arrive as ``request_data = {"params": {...}, "headers": {}, ...}``.
  The task's ``inputs:`` block lands inside ``request_data["params"]``.
- The response MUST have ``{"status": True, "data": <dict>}``. The
  ``data`` value is exposed as ``$`` inside the task's ``outputs:`` block;
  every other top-level key in the response (including ``result``,
  ``message`` and custom names) is stripped.

Tools call this connector with ``command: "football"`` and pass the
internal function name via the ``command`` input, e.g.:

    connector:
      name: sports-skills
      command: football
    inputs:
      command: "'get_season_standings'"
      season_id: "$.get('season_id')"

The dispatcher forwards to ``sports_skills.football._connector.<fn>``
and returns whatever the library returned under ``data``. Tools read
library fields directly via ``$.get('<field>')``.
"""

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


def _err(message):
    return {"status": False, "data": {"error": str(message)}}


def football(request_data):
    """Dispatch to the named sports_skills.football._connector.<fn>."""
    if not isinstance(request_data, dict):
        return _err("request_data is not a dict")

    params = request_data.get("params") or {}
    if not isinstance(params, dict):
        return _err("params is not a dict")

    command = params.get("command")

    if command == "ping":
        return {"status": True, "data": {"ping": "pong", "received_params": params}}

    if not command:
        return _err("'command' input is required")

    if command not in _ALLOWED:
        return _err("unknown command: " + str(command))

    try:
        from sports_skills.football import _connector
    except Exception as exc:
        return _err("sports-skills import failed: " + repr(exc))

    fn = getattr(_connector, command, None)
    if fn is None:
        return _err("no function: " + command)

    forwarded = {
        k: v
        for k, v in params.items()
        if k not in ("command", "model_name") and v is not None
    }

    try:
        data = fn({"params": forwarded})
    except Exception as exc:
        return _err(command + " raised " + repr(exc))

    if not isinstance(data, dict):
        return {"status": True, "data": {"value": data}}

    return {"status": True, "data": data}
