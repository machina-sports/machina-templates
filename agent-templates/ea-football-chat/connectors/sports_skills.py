"""sports-skills pyscript connector — single dispatcher entry point.

The framework wraps inputs as `{"params": {...}, "headers": {}, ...}` and
strips `status` / `result` / `data` keys from the response. Data is
returned under the non-reserved `payload` key so tools can read it via
`$.get('payload')`.

The ea-football-chat tools call this connector with `command: "football"`
and pass the internal function name via the `command` input param, e.g.:

    connector:
      name: sports-skills
      command: football
    inputs:
      command: "'get_season_standings'"
      season_id: "$.get('season_id')"

This `football()` function dispatches to
`sports_skills.football._connector.<fn>` and returns the result under
`payload`.
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


def football(request_data):
    """Dispatch to the named sports_skills.football function.

    request_data is the framework-provided dict of shape:
      {"params": {...}, "headers": {...}, "connector_exec": "football", ...}

    Reads the inner `command` from params, forwards the remaining params
    to the corresponding `sports_skills.football._connector` function, and
    returns the library output under `payload`.
    """
    if not isinstance(request_data, dict):
        return {"sk_output": {"error": "request_data is not a dict"}}

    params = request_data.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    command = params.get("command")

    if command == "ping":
        return {
            "sk_output": {
                "ping": "pong",
                "received_params": params,
            }
        }

    if not command:
        return {"sk_output": {"error": "'command' input is required"}}

    if command not in _ALLOWED:
        return {"sk_output": {"error": "unknown command: " + str(command)}}

    try:
        from sports_skills.football import _connector
    except Exception as exc:
        return {"sk_output": {"error": "sports-skills import failed: " + repr(exc)}}

    fn = getattr(_connector, command, None)
    if fn is None:
        return {"sk_output": {"error": "no function: " + command}}

    forwarded = {k: v for k, v in params.items() if k not in ("command", "model_name")}

    try:
        data = fn({"params": forwarded})
    except Exception as exc:
        return {"sk_output": {"error": command + " raised " + repr(exc)}}

    return {"sk_output": data}
