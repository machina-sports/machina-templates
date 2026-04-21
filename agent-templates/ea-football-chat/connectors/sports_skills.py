"""sports-skills pyscript connector — single dispatcher entry point.

The ea-football-chat tools call this connector with `command: "football"` and
pass the internal function name via the `command` input param, e.g.:

    connector:
      name: sports-skills
      command: football
    inputs:
      command: "'get_season_standings'"
      season_id: "$.get('season_id')"

This `football()` function dispatches the request to the corresponding
`sports_skills.football._connector` function, which returns an ESPN /
Understat / FPL / Transfermarkt payload. Returned as `{"result": <data>}`
so the tools can read it via `$.get('result')`.
"""

from __future__ import annotations


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


def football(params):
    """Dispatch to the named sports_skills.football function.

    params: flat dict of all workflow inputs. Reads `command` to pick the
    function; forwards the remaining keys as the function's params.
    """
    # Diagnostic shield — surface the actual input shape instead of
    # propagating AttributeErrors from wrong assumptions about `params`.
    if not isinstance(params, dict):
        return {
            "result": {
                "error": True,
                "message": f"params is not a dict: got {type(params).__name__} = {params!r}",
            }
        }

    command = params.get("command")

    # Diagnostic ping — does not touch the sports-skills library.
    if command == "ping":
        return {
            "result": {
                "ping": "pong",
                "params_received": params,
                "params_type": type(params).__name__,
            }
        }

    if not command:
        return {"result": {"error": True, "message": "'command' input is required"}}

    if command not in _ALLOWED:
        return {"result": {"error": True, "message": f"Unknown command: {command}"}}

    try:
        from sports_skills.football import _connector
    except Exception as exc:
        return {
            "result": {
                "error": True,
                "message": f"sports-skills import failed: {type(exc).__name__}: {exc}",
            }
        }

    fn = getattr(_connector, command, None)
    if fn is None:
        return {
            "result": {
                "error": True,
                "message": f"Command not found on module: {command}",
            }
        }

    forwarded = {k: v for k, v in params.items() if k != "command"}

    try:
        data = fn({"params": forwarded})
    except Exception as exc:
        return {
            "result": {
                "error": True,
                "message": f"{command} raised {type(exc).__name__}: {exc}",
            }
        }

    return {"result": data}
