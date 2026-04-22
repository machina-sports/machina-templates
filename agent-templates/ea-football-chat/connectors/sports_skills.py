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
        import sys, os, importlib
        user_site = "/home/machina/.local/lib/python3.11/site-packages"
        fs_check = {}
        try:
            fs_check["hostname"] = os.uname().nodename
            fs_check["uid"] = os.getuid()
            fs_check["euid"] = os.geteuid()
            fs_check["cwd"] = os.getcwd()
        except Exception as e:
            fs_check["ident_error"] = repr(e)
        try:
            with open("/etc/hostname") as f:
                fs_check["etc_hostname"] = f.read().strip()
        except Exception as e:
            fs_check["etc_hostname_error"] = repr(e)
        try:
            fs_check["root_home_contents"] = sorted(os.listdir("/root"))[:10]
        except Exception as e:
            fs_check["root_home_err"] = repr(e)
        try:
            fs_check["system_sp_has_sports"] = any(
                n.startswith("sports") for n in os.listdir("/usr/local/lib/python3.11/site-packages")
            )
        except Exception as e:
            fs_check["system_sp_err"] = repr(e)
        fs_check["tmp_pylib_exists"] = os.path.isdir("/tmp/pylib")
        if fs_check["tmp_pylib_exists"]:
            try:
                fs_check["tmp_pylib_contents"] = sorted(os.listdir("/tmp/pylib"))[:20]
            except Exception as e:
                fs_check["tmp_pylib_err"] = repr(e)
        # Identify which container by checking init-process command line
        try:
            with open("/proc/1/cmdline", "rb") as f:
                fs_check["proc1_cmd"] = f.read().replace(b"\x00", b" ").decode("utf-8", "replace").strip()
        except Exception as e:
            fs_check["proc1_err"] = repr(e)
        fs_check["user_site_exists"] = os.path.isdir(user_site)
        if os.path.isdir(user_site):
            try:
                fs_check["user_site_contents"] = sorted(os.listdir(user_site))[:20]
            except Exception as exc:
                fs_check["user_site_listing_error"] = repr(exc)
        ss_init = user_site + "/sports_skills/__init__.py"
        fs_check["sports_skills_init_exists"] = os.path.isfile(ss_init)
        for _p in (
            "/tmp/pylib",
            user_site,
            "/root/.local/lib/python3.11/site-packages",
        ):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        importlib.invalidate_caches()
        lib_check = {"sys_path": list(sys.path), "fs_check": fs_check}
        try:
            import sports_skills

            lib_check["sports_skills_version"] = getattr(
                sports_skills, "__version__", "unknown"
            )
            lib_check["import_ok"] = True
        except Exception as exc:
            lib_check["import_ok"] = False
            lib_check["import_error"] = repr(exc)
        try:
            from sports_skills.football import _connector

            lib_check["football_module_ok"] = True
            lib_check["football_fns_sample"] = [
                n for n in dir(_connector) if n.startswith("get_")
            ][:5]
        except Exception as exc:
            lib_check["football_module_ok"] = False
            lib_check["football_module_error"] = repr(exc)
        return {
            "status": True,
            "data": {
                "ping": "pong",
                "received_params": params,
                "lib_check": lib_check,
            },
        }

    if not command:
        return _err("'command' input is required")

    if command not in _ALLOWED:
        return _err("unknown command: " + str(command))

    try:
        import sys, importlib
        for _p in (
            "/tmp/pylib",
            "/home/machina/.local/lib/python3.11/site-packages",
            "/root/.local/lib/python3.11/site-packages",
        ):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        importlib.invalidate_caches()
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
