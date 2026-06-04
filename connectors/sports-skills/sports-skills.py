"""
sports-skills connector — thin dispatcher over the
`machina-sports/sports-skills` Python package (PyPI: `sports-skills`).

Design:
- One `invoke_<module>` per registered sports-skills module (football,
  nba, nfl, ...). Each forwards a `command` param (the function name on
  that module) plus arbitrary kwargs.
- 19 modules × ~13 commands each ≈ 241 underlying functions, kept off
  the connector's flat command surface. The agent picks a module via
  the connector command, then names the specific function in `inputs`.
- Most modules wrap public providers (ESPN, Understat, FPL, openfootball,
  Polymarket, Kalshi). No API keys for the public ones. Betting-market
  modules use their own keys when the customer wants order placement.

Runtime requirement:
- The pod's Python env must have `sports-skills` importable. The
  preferred path is adding `sports-skills>=0.21` to
  `machina-client-api/requirements.txt` and rebuilding the pod image.
- As a fallback this module attempts a one-time `pip install
  sports-skills` on first ImportError so customers can use the
  connector without waiting on a pod-image rebuild. The first call is
  then ~15-30s slower; subsequent calls are instant.
"""

import importlib
import inspect
import os
import subprocess
import sys


_MIN_VERSION = (0, 25, 1)
_PIP_PACKAGE = "sports-skills>=0.25.1,<1.0"
# Writable install target for in-place upgrades. The pod runs as a non-root
# user whose home dir is read-only (`pip install --user` fails with EACCES on
# /home/machina), and system site-packages is root-owned — /tmp is the one
# reliably writable location. Contents live for the container's lifetime,
# which matches how long the upgrade is needed.
_TARGET_DIR = "/tmp/sports-skills-site"


def _version_ok():
    """True when the importable sports-skills meets _MIN_VERSION."""
    try:
        from importlib import metadata

        parts = metadata.version("sports-skills").split(".")[:3]
        return tuple(int(p) for p in parts) >= _MIN_VERSION
    except Exception:
        return False


def _activate_target():
    """Put _TARGET_DIR first on sys.path and drop stale imported modules."""
    if _TARGET_DIR not in sys.path:
        sys.path.insert(0, _TARGET_DIR)
    importlib.invalidate_caches()
    for name in [m for m in sys.modules if m == "sports_skills" or m.startswith("sports_skills.")]:
        del sys.modules[name]


def _ensure_sports_skills():
    """Import sports_skills, pip-installing or upgrading when needed.

    Returns (ok: bool, err_msg: str|None). Pod base images bake a pinned
    sports-skills into system site-packages; when that copy is older than
    _MIN_VERSION (features like the 'worldcup' sport key would be missing),
    this installs the current release to _TARGET_DIR and puts it first on
    sys.path instead of silently using the stale version. Long-term the
    floor should be enforced in the pod image requirements — this branch
    keeps already-deployed pods working without a rebuild.
    """
    # Fast path: an acceptable version is already importable.
    if _version_ok():
        try:
            importlib.import_module("sports_skills")
            return True, None
        except ImportError:
            pass

    # A previous call (possibly in another worker process of this container)
    # may have already installed the upgrade to /tmp — just activate it.
    if os.path.isdir(os.path.join(_TARGET_DIR, "sports_skills")):
        _activate_target()
        if _version_ok():
            try:
                importlib.import_module("sports_skills")
                return True, None
            except ImportError:
                pass

    # Install/upgrade into the writable target. Capture stdout+stderr so
    # failures surface a real error in the workflow output instead of a
    # cryptic exit code.
    proc = subprocess.run(  # noqa: S603 — args are constants, no shell
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-cache-dir",
            "--upgrade",
            "--target",
            _TARGET_DIR,
            _PIP_PACKAGE,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if proc.returncode != 0:
        # pip prints the actionable bit to stderr; include both for safety.
        tail = (proc.stderr or proc.stdout or "")[-1500:]
        # If a stale baked copy exists, degrade gracefully rather than
        # hard-fail (offline pods keep working on the old feature set).
        try:
            importlib.import_module("sports_skills")
            return True, None
        except ImportError:
            pass
        return False, f"pip install {_PIP_PACKAGE} failed (rc={proc.returncode}): {tail}"

    _activate_target()
    try:
        importlib.import_module("sports_skills")
        return True, None
    except ImportError as e:
        return False, (
            f"sports_skills installed but not importable from {_TARGET_DIR}: {e}. "
            f"pip stdout tail: {(proc.stdout or '')[-500:]}"
        )


def _dispatch(module_name, request_data):
    """Run `sports_skills.<module_name>.<command>(**kwargs)`.

    `command` is read from `params` and removed before forwarding the
    rest as kwargs. Returns the package's normalized response wrapped
    in the standard connector envelope (status/data/message).
    """
    ok, err = _ensure_sports_skills()
    if not ok:
        return {"status": False, "message": err}

    params = dict(request_data.get("params") or {})
    command = params.pop("command", None)
    if not command:
        return {
            "status": False,
            "message": f"invoke_{module_name}: missing required `command` param (the function name on sports_skills.{module_name}).",
        }

    try:
        mod = importlib.import_module(f"sports_skills.{module_name}")
    except ImportError as e:
        return {
            "status": False,
            "message": f"unknown sports-skills module 'sports_skills.{module_name}': {e}",
        }

    fn = getattr(mod, command, None)
    if fn is None or not callable(fn):
        # List available callables on the module for a useful error.
        available = sorted(
            n for n in dir(mod) if not n.startswith("_") and callable(getattr(mod, n))
        )
        return {
            "status": False,
            "message": (
                f"command '{command}' not found on sports_skills.{module_name}. "
                f"Available: {', '.join(available)}"
            ),
        }

    # The workflow runtime injects framework-level keys (model_name,
    # debugger, api_key, headers, etc.) into every connector params dict.
    # sports_skills functions have narrow signatures and reject unknown
    # kwargs with TypeError. Filter `params` down to what the function
    # actually accepts so the agent never has to know which keys are
    # framework noise vs. real call args.
    try:
        sig = inspect.signature(fn)
        accepts_kwargs = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        if not accepts_kwargs:
            allowed = set(sig.parameters.keys())
            params = {k: v for k, v in params.items() if k in allowed}
    except (TypeError, ValueError):
        # Builtins / C-extensions don't expose signatures — pass through.
        pass

    try:
        result = fn(**params)
    except TypeError as e:
        return {
            "status": False,
            "message": f"invalid args for sports_skills.{module_name}.{command}: {e}",
        }
    except Exception as e:  # noqa: BLE001 — surface upstream errors as data, not crashes
        return {
            "status": False,
            "message": f"sports_skills.{module_name}.{command} raised: {e}",
        }

    # sports-skills returns either plain dicts/lists or pydantic Response
    # objects. Normalize both into JSON-serializable shapes.
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    elif hasattr(result, "dict"):
        result = result.dict()
    return {"status": True, "data": result}


# -------------------------------------------------------------------
# Module dispatchers — one per sports-skills module.
# Pass `command=<function_name>` in inputs plus the function's kwargs.
# -------------------------------------------------------------------


def invoke_football(request_data):
    """Football (soccer) — ESPN/Understat/FPL/Transfermarkt/openfootball.

    Commands: get_current_season, get_competitions, get_competition_seasons,
    get_season_schedule, get_season_standings, get_season_leaders,
    get_season_teams, search_player, search_team, get_team_profile,
    get_daily_schedule, get_event_summary, get_event_lineups,
    get_event_statistics, get_event_timeline, get_team_schedule,
    get_head_to_head, get_event_xg, get_event_players_statistics,
    get_missing_players, get_season_transfers, get_player_profile,
    get_player_season_stats.
    """
    return _dispatch("football", request_data)


def invoke_nba(request_data):
    """NBA — ESPN. Commands: get_scoreboard, get_standings, get_team_schedule, ..."""
    return _dispatch("nba", request_data)


def invoke_wnba(request_data):
    """WNBA — ESPN."""
    return _dispatch("wnba", request_data)


def invoke_nfl(request_data):
    """NFL — ESPN. Commands: get_scoreboard, get_standings, ..."""
    return _dispatch("nfl", request_data)


def invoke_nhl(request_data):
    """NHL — ESPN."""
    return _dispatch("nhl", request_data)


def invoke_mlb(request_data):
    """MLB — ESPN/MLB Stats API."""
    return _dispatch("mlb", request_data)


def invoke_cfb(request_data):
    """College Football — ESPN."""
    return _dispatch("cfb", request_data)


def invoke_cbb(request_data):
    """College Basketball — ESPN."""
    return _dispatch("cbb", request_data)


def invoke_tennis(request_data):
    """Tennis — ESPN."""
    return _dispatch("tennis", request_data)


def invoke_golf(request_data):
    """Golf — ESPN (PGA, LPGA, Euro)."""
    return _dispatch("golf", request_data)


def invoke_f1(request_data):
    """Formula 1 — FastF1 / ESPN."""
    return _dispatch("f1", request_data)


def invoke_volleyball(request_data):
    """Volleyball — ESPN."""
    return _dispatch("volleyball", request_data)


def invoke_xctf(request_data):
    """Cross-country / Track & Field — ESPN."""
    return _dispatch("xctf", request_data)


def invoke_polymarket(request_data):
    """Polymarket prediction markets. Read-only commands (get_*) require no
    auth. Order-placement commands (create_order, market_order, cancel_*)
    require a wallet key passed via `configure` first.

    Commands: get_sports_markets, get_sports_events, get_series, get_market_details,
    get_event_details, get_market_prices, get_order_book, get_sports_market_types,
    get_sports_config, get_todays_events, search_markets, get_price_history,
    get_last_trade_price, configure, create_order, market_order, cancel_order,
    cancel_all_orders, get_orders, get_user_trades.
    """
    return _dispatch("polymarket", request_data)


def invoke_kalshi(request_data):
    """Kalshi prediction markets. Read-only by default.

    Commands: get_exchange_status, get_exchange_schedule, get_series_list,
    get_series, get_events, get_event, get_markets, get_market, get_trades,
    get_market_candlesticks, get_sports_filters, get_sports_config,
    get_todays_events, search_markets.
    """
    return _dispatch("kalshi", request_data)


def invoke_betting(request_data):
    """Betting utilities — no upstream calls, pure math.

    Commands: convert_odds, devig, find_edge, kelly_criterion, evaluate_bet,
    find_arbitrage, parlay_analysis, line_movement, matchup_probability.
    """
    return _dispatch("betting", request_data)


def invoke_markets(request_data):
    """Cross-sportsbook market normalization & matching.

    Commands: get_todays_markets, search_entity, compare_odds,
    get_sport_markets, get_sport_schedule, normalize_price, evaluate_market.
    """
    return _dispatch("markets", request_data)


def invoke_metadata(request_data):
    """Team / league metadata helpers.

    Commands: get_team_logo.
    """
    return _dispatch("metadata", request_data)


def invoke_news(request_data):
    """Sports news aggregation across providers.

    Commands: fetch_items (params: query, limit).
    """
    return _dispatch("news", request_data)


def invoke_sports_skills(request_data):
    """Dynamic sports-skills dispatcher with cascading league lookup fallbacks."""
    params = request_data.get("params") or {}

    # Extract sport and league
    sport = str(params.get("sport") or "").strip().lower()
    league = str(params.get("league") or "").strip().upper()

    # 1. Handle Basketball cascading lookup if league is missing
    if sport == "basketball" and not league:
        request_data.setdefault("params", {})["command"] = "get_player_stats"
        res = _dispatch("wnba", request_data)
        if res.get("status") is True and res.get("data", {}).get("status") is True:
            return res
        # Try NBA next
        res = _dispatch("nba", request_data)
        if res.get("status") is True and res.get("data", {}).get("status") is True:
            return res
        # Fall back to CBB (College Basketball)
        return _dispatch("cbb", request_data)

    # 2. Standard resolution
    if sport == "soccer" or (sport == "football" and league in ["MLS", "LALIGA", "PREMIER LEAGUE", "NWSL"]):
        module_name = "football"
        default_command = "get_player_profile"
    elif league == "NBA":
        module_name = "nba"
        default_command = "get_player_stats"
    elif league == "WNBA":
        module_name = "wnba"
        default_command = "get_player_stats"
    elif sport == "baseball":
        module_name = "mlb"
        default_command = "get_player_stats"
    else:
        # Default to NFL
        module_name = "nfl"
        default_command = "get_player_stats"

    # Inject resolved default command if not already provided
    if "command" not in params or not params.get("command"):
        request_data.setdefault("params", {})["command"] = default_command

    return _dispatch(module_name, request_data)

