def football(request_data):
    params = request_data.get("params") if isinstance(request_data, dict) else None

    if params is None:
        params = request_data if isinstance(request_data, dict) else {}

    command = params.get("command") if isinstance(params, dict) else None

    if command == "ping":
        return {
            "status": True,
            "result": {
                "ping": "pong",
                "received_request_shape": type(request_data).__name__,
                "received_params_shape": type(params).__name__,
                "received_keys": list(request_data.keys()) if isinstance(request_data, dict) else None,
            },
        }

    if not command:
        return {"status": False, "result": {"error": "command is required", "shape_dump": str(request_data)[:500]}}

    _ALLOWED = {
        "get_current_season", "get_competitions", "get_competition_seasons",
        "get_season_schedule", "get_season_standings", "get_season_leaders",
        "get_season_teams", "search_team", "search_player", "get_team_profile",
        "get_team_schedule", "get_daily_schedule", "get_event_summary",
        "get_event_lineups", "get_event_statistics", "get_event_timeline",
        "get_event_xg", "get_event_players_statistics", "get_head_to_head",
        "get_missing_players", "get_season_transfers", "get_player_profile",
        "get_player_season_stats",
    }

    if command not in _ALLOWED:
        return {"status": False, "result": {"error": "unknown command: " + str(command)}}

    try:
        from sports_skills.football import _connector
    except Exception as exc:
        return {"status": False, "result": {"error": "import failed: " + repr(exc)}}

    fn = getattr(_connector, command, None)
    if fn is None:
        return {"status": False, "result": {"error": "no function: " + command}}

    forwarded = {k: v for k, v in params.items() if k != "command"}

    try:
        data = fn({"params": forwarded})
    except Exception as exc:
        return {"status": False, "result": {"error": command + " raised " + repr(exc)}}

    return {"status": True, "result": data}
