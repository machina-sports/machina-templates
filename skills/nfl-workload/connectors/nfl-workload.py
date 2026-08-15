"""
nfl-workload connector - derived fantasy opportunity metrics for the NFL.

No third-party projections or consensus rankings exist on this platform, so
opportunity is derived from nflverse play-by-play instead: target share, air
yards share, WOPR, rush share, red-zone touches, EPA per opportunity, plus a
recent-vs-season trend.

Commands:
  generate_workload_report(request_data)
      -> {"status": True, "data": {"report": {...}, "season", "week",
                                     "position", "n_players", "deps"}}
  generate_machina_workload_snapshot(request_data)
       -> additive machina-player-workload-snapshot/1 aggregate. Requires a
          caller-supplied observed_at; the canonical rights gate runs before
          dependency bootstrap or data loading.
  get_player_workload(request_data)
      -> {"status": True, "data": {"player": {...}, "matched_name": "...",
                                   "reason": "matched", "selected_team",
                                   "other_stints": [...], "deps"}}
  get_player_pair_workload(request_data)
      params: season, week, position, player_a_name, player_b_name,
              player_a_team, player_b_team   (teams per player, both optional)
      -> {"status": True, "data": {"player_a": {...}, "player_b": {...},
                                   "season", "week", "position",
                                   "n_matched", "deps"}}
  get_player_context(request_data)
      -> {"status": True, "data": {"depth_chart_role": {...},
                                   "injury_status": {...},
                                   "matched_name": "...",
                                   "reason": "matched", "deps"}}

Every response carries `deps` - {"nflreadpy": version, "polars": version} as
actually loaded - so the build that computed a number is visible in the number's
own payload rather than inferred from call latency.

TRADED PLAYERS - which stint answers, and saying so:
  Usage is grouped per team, so a player traded mid-season holds one row per
  stint and a name alone does not name a row. Stint scoping is optional, and
  the parameter is named for how many players the command resolves:

    - get_player_workload takes `team` - one name, one team.
    - get_player_pair_workload takes `player_a_team` and `player_b_team`,
      independent and individually optional. Two compared players are usually
      on two different rosters, so a single shared team would be wrong more
      often than right; passing `team` there is refused rather than applied to
      both or silently dropped.

  Given a team, the name is matched only within that team's rows, and a player
  who exists elsewhere but holds no row there is not_found scoped to that team,
  with his actual stints listed. Never a fallback to another stint. Omitted, the
  busiest stint wins, tie-broken on the most recent week (last_week, a new
  per-stint column) - measured 2025 through week 16, Lil'Jordan Humphrey held
  NYG and DEN stints at 10 opportunities each, previously settled by whichever
  row the frame yielded first and now by DEN's later last_week.

  Both outcomes carry `selected_team` and `other_stints` [{team, opportunities,
  wopr}], because the previous behaviour made the choice invisible: Rashid
  Shaheed's 2025 week 17 lookup returned his New Orleans stint - 68
  opportunities against Seattle's 32 - and said nothing about the other one, so
  a comparison against him silently used part of his season.

The first three commands run the same computation: _load_frames ->
_build_report_payload. get_player_workload then resolves a single row out of
that report by name, and get_player_pair_workload resolves two off one build
rather than paying for the season load twice. All of them build the report
unfiltered (min_opportunities=0, limit=0) for per-player lookups, because the
floor and the head() cut exist to shape a ranked leaderboard; applying them to
a single-player lookup would report a real but low-usage or low-ranked player
as missing.

MISSES ARE DATA, NOT ERRORS:
  A name matching nothing, or matching several players, returns status True
  with an explicit `reason` - "not_found" or "ambiguous", against "matched" on
  a hit - plus a human-readable `message` and, for an ambiguous query, the
  `candidates` that collided. get_player_context adds two more: "historical"
  when the requested season/week is not the current week, and "unknown_week"
  when the current week could not be established at all. status False is
  reserved for genuine faults: a missing or half-supplied required parameter,
  a window outside the season, a failed season load, an unresolvable or
  ambiguous team, both context sources down, an unsatisfiable dependency pin.

  The distinction is operational, not stylistic. These commands run under
  continue_on_error, which preserves the payload of a status True result and
  discards the message of a status False one. Reporting a miss as False
  therefore destroyed the only text that said what went wrong: "'Brown' is
  ambiguous between three players" and "Mahomes is not in this report"
  arrived downstream as the same empty output, and nothing could tell a
  caller which had happened or what to do about it.

get_player_context answers a different question and reads a different source:
role and availability, from ESPN via sports-skills rather than from nflverse
play-by-play. Workload says how a player has been used; context says where
they sit on the chart and whether they are hurt. It resolves the team through
get_teams() FIRST, then narrows the league-wide get_injuries() feed to that
team before matching any name. Matching a name against the whole feed is what
previously let a same-surname player on another roster answer a question about
this one. It does not call _ensure_deps(): it touches neither nflreadpy nor
polars, and gating it on that install would fail it closed on a dependency it
never uses - which also means its `deps` field reports whatever the worker
happens to hold rather than what produced the answer.

  TEMPORAL SCOPE - get_player_context serves CURRENT STATE, and now says so:
    ESPN's depth-chart and injury endpoints expose present state only; there
    is no historical equivalent behind them. Rather than leave that for the
    caller to remember, the command takes optional `season` and `week` and
    checks them against the live coordinate from get_scoreboard() before
    looking anything up:

      - season.type == 2 is the regular season and week.number is the live
        fantasy week. A request naming exactly that (season, week) proceeds
        normally.
      - Any other season.type - 1 preseason, 3+ postseason - means there is
        no current fantasy week at all, so every request is historical.
        Measured 2026-08-06 on Hall of Fame game night, get_scoreboard()
        returned season {"year": 2026, "type": 1}, week {"number": 1}: it
        reports where the league actually is, not a stale week 22 from the
        preceding February.
      - A mismatch returns the soft-miss shape with reason "historical" and a
        message naming both coordinates, instead of stapling today's roles
        and injuries onto a past week.
      - If the scoreboard call itself fails, the answer is "unknown_week":
        the request cannot honestly be called current or historical.

    Omitting season and week preserves the previous behavior exactly - no
    scoreboard call, no added latency, no new fields, and a payload stamped
    as_of "current". The check is opt-in.

    Roster churn is why this matters. A player who has since changed teams,
    retired or been cut is absent from his old team's current depth chart, so
    a historical query came back not_found - truthful about today, misleading
    about the week asked for. Rashid Shaheed is the worked example: his 2025
    week 17 workload row is the New Orleans stint, and he resolves to nothing
    on the current New Orleans roster.

    Serving past weeks with real historical context still needs a source that
    carries history; ESPN's endpoints cannot provide it. This refuses the
    question rather than answering the wrong one.

DEVIATION from the sports-skills connector pattern, deliberate:
  This reads nflreadpy directly rather than calling
  sports_skills.nfl.get_nflverse_play_by_play. That wrapper normalizes to a
  dict and accepts a `limit`, and the metrics here need air_yards, epa,
  yardline_100 and receiver/rusher ids intact across every play of a season.
  Normalized reads have already cost us fields elsewhere (ESPN's
  _normalize_plays strips the wallclock that get_plays_near_timestamp needs).
  Going direct keeps the full column set and makes truncation impossible.

BOOTSTRAP, fail-closed and version-exact by design:
  nflreadpy is absent from the shared sports-skills install: it sits behind a
  python_version >= '3.10' marker in extras and the pod installs bare
  sports-skills. This connector installs it itself, at the exact versions in
  _PIP_PACKAGES. The gate compares the resident __version__ of every pinned
  package against its pin and treats a mismatch as absence, so the pin holds on
  a warm pod as well as a cold one - previously the bootstrap returned early on
  a bare `import polars` and the pin governed nothing but a fresh container.
  Every fallback path re-checks the pins and returns an error rather than
  proceeding on a partial or wrong-version install, since a silent degrade
  would surface later as an AttributeError with no trace back to its cause.
"""

import importlib
import math
import os
import re
import subprocess
import sys
from datetime import datetime

# nflreadpy is not part of the shared sports-skills install: it sits behind a
# python_version >= '3.10' environment marker in extras, and the pod bootstraps
# bare `sports-skills`, so it is absent. This connector installs it itself.
_PIP_PACKAGES = ["nflreadpy==0.1.5", "polars==1.43.2"]
_TARGET_DIR = "/tmp/nfl-workload-site"
_PIP_TIMEOUT_SECONDS = 300

# Weighted Opportunity Rating (Hermsmeyer): volume plus downfield role.
WOPR_TARGET_WEIGHT = 1.5
WOPR_AIR_YARDS_WEIGHT = 0.7

REDZONE_YARDLINE = 20

# Fantasy regular season ends after week 17; week 18 is not fantasy-relevant.
FANTASY_LAST_WEEK = 17

_DEFAULT_LOOKBACK_WEEKS = 3
_DEFAULT_MIN_OPPORTUNITIES = 10
_DEFAULT_LIMIT = 50

_SNAPSHOT_SCHEMA_VERSION = "machina-player-workload-snapshot/1"
_SNAPSHOT_RIGHTS = {
    "data_class": "open-public",
    "prototype_only": True,
    "commercial_use": False,
}
_SNAPSHOT_PRESENT_CAPABILITIES = (
    "participant.player_statistics",
    "provenance",
)
_SNAPSHOT_CAPABILITY_VOCABULARY = (
    "event.actions",
    "event.clock",
    "event.competition",
    "event.coordinates",
    "event.expected_metrics",
    "event.formations",
    "event.identity",
    "event.lineups",
    "event.live_statistics",
    "event.participants",
    "event.period",
    "event.play_by_play",
    "event.result",
    "event.score",
    "event.start_time",
    "event.start_time.bounded",
    "event.status",
    "event.tracking",
    "participant.player_statistics",
    "provenance",
)
_SNAPSHOT_STATISTICS = {
    "targets": "spamfstat:receptionsLooks",
    "receptions": "spamfstat:receptionsTotal",
    "carries": "spamfstat:rushesAttempts",
}
_SNAPSHOT_METRICS = (
    "air_yards",
    "target_share",
    "air_yards_share",
    "rush_share",
    "wopr",
    "opportunities",
    "rz_targets",
    "rz_carries",
    "rz_touches",
    "rec_epa",
    "rush_epa",
    "total_epa",
    "epa_per_opportunity",
    "recent_target_share",
    "recent_wopr",
    "recent_rush_share",
    "recent_opportunities",
    "target_share_delta",
    "wopr_delta",
    "rush_share_delta",
    "last_week",
)
_SNAPSHOT_INTEGER_METRICS = {
    "opportunities",
    "rz_targets",
    "rz_carries",
    "rz_touches",
    "recent_opportunities",
    "last_week",
}
_RFC3339_OFFSET = re.compile(
    r"^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
_RFC3339_SECOND_60 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:60"
    r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)
_SURROGATE_URN = re.compile(
    r"^urn:machina:sports:[a-z][a-z0-9_-]*:x[0-9a-f]{32}$"
)

# Only the columns the metrics need. A full pbp frame is ~49k rows x 372 cols;
# narrowing immediately keeps the pod's memory profile predictable.
_PBP_COLUMNS = [
    "season", "week", "season_type", "posteam", "game_id",
    "pass_attempt", "rush_attempt", "sack", "two_point_attempt",
    "complete_pass", "air_yards", "epa", "yardline_100",
    "receiver_player_id", "receiver_player_name",
    "rusher_player_id", "rusher_player_name",
]

_PLAYER_STATS_COLUMNS = ["player_id", "position", "player_display_name"]

# nflverse carries two spellings of a name: play-by-play abbreviates
# ("M.Nabers") while the stats table spells it out ("Malik Nabers"). A user
# types either, or just a surname. Both columns are searched.
_NAME_COLUMNS = ["player_display_name", "player_name"]


# ---------------------------------------------------------------------------
# bootstrap - fail closed
# ---------------------------------------------------------------------------

def _pinned_versions():
    """{package: exact version} parsed out of _PIP_PACKAGES.

    One source of truth: the same list pip installs from is the list the gate
    below enforces, so the pin and the check cannot drift apart. A spec without
    `==` is skipped rather than guessed at, so loosening a pin also loosens the
    gate instead of silently failing every call.
    """
    pinned = {}
    for spec in _PIP_PACKAGES:
        name, sep, version = spec.partition("==")
        if sep and version.strip():
            pinned[name.strip()] = version.strip()
    return pinned


def _loaded_versions():
    """Resident __version__ for each pinned package, None where unavailable.

    Doubles as the payload's `deps` field, so what the gate checks and what a
    caller sees are the same reading.
    """
    versions = {}
    for name in _pinned_versions():
        try:
            module = importlib.import_module(name)
        except Exception:
            versions[name] = None
            continue
        versions[name] = str(getattr(module, "__version__", "") or "") or None
    return versions


def _pins_satisfied():
    """True only when every pinned package imports AT its exact version.

    Deliberately stricter than importability. _ensure_deps used to return early
    on a bare `import polars`, which meant the pin governed a cold pod and
    nothing else: a worker already holding some other polars kept it forever,
    and the pinned version was never what computed the numbers. Treating a
    version mismatch as absence is what makes the pin authoritative.
    """
    loaded = _loaded_versions()
    return all(loaded.get(name) == want for name, want in _pinned_versions().items())


def _pin_mismatch():
    """want-vs-loaded, for the failure messages."""
    loaded = _loaded_versions()
    return ", ".join(
        "%s want %s loaded %s" % (name, want, loaded.get(name) or "absent")
        for name, want in sorted(_pinned_versions().items())
    )


def _is_pinned_module(name, roots):
    """Whether a sys.modules key belongs to one of the pinned packages.

    Leading underscores are stripped before matching, because a package's
    compiled half is often a separate private distribution. polars ships as a
    thin py3-none-any wrapper that loads its binary from `polars-runtime-32`,
    imported as `_polars_runtime_32` - and a plain root-prefix test misses that
    name entirely. Measured 2026-08-10 upgrading 1.42.1 -> 1.43.2 in-process:
    the purge dropped `polars` but kept the OLD `_polars_runtime_32`, so the new
    wrapper found a mismatched binary, raised "Polars binary is missing!", and
    the bootstrap refused to proceed - pip reported success while the import
    failed. Failing closed was right; missing the runtime was not.
    """
    bare = name.lstrip("_")
    return any(
        bare == root or bare.startswith(root + ".") or bare.startswith(root + "_")
        for root in roots
    )


def _activate_target():
    """Put the target dir first on sys.path and drop cached pinned modules.

    Both halves matter. Prepending alone does nothing for a package already in
    sys.modules, because import returns the cached module without consulting
    sys.path - so a wrong-version polars would survive the reinstall. The purge
    covers every pinned package and its private runtime (see
    _is_pinned_module), which is what lets the version gate actually take
    effect rather than merely detect a mismatch it cannot repair.
    """
    if _TARGET_DIR not in sys.path:
        sys.path.insert(0, _TARGET_DIR)
    importlib.invalidate_caches()
    roots = tuple(_pinned_versions())
    if not roots:
        return
    for name in [m for m in list(sys.modules) if _is_pinned_module(m, roots)]:
        del sys.modules[name]


def _ensure_deps():
    """Install the pinned nflreadpy + polars into a writable target dir.

    Returns (ok, error_message). Never reports success on a degraded path:
    every fallback re-checks the pins and anything short of an exact match is
    returned as a failure. A resident package at the wrong version counts as
    absent, so the pin holds on a warm pod as well as a cold one.
    """
    if _pins_satisfied():
        return True, None

    if os.path.isdir(os.path.join(_TARGET_DIR, "nflreadpy")):
        _activate_target()
        if _pins_satisfied():
            return True, None

    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pip", "install", "--no-cache-dir",
                "--upgrade", "--target", _TARGET_DIR, *_PIP_PACKAGES,
            ],
            capture_output=True,
            text=True,
            timeout=_PIP_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        _activate_target()
        if _pins_satisfied():
            return True, None
        return False, (
            "pip install timed out after %ss and the pins are unsatisfied (%s)"
            % (_PIP_TIMEOUT_SECONDS, _pin_mismatch())
        )
    except Exception as exc:
        _activate_target()
        if _pins_satisfied():
            return True, None
        return False, "pip install raised %s: %s (%s)" % (
            type(exc).__name__,
            exc,
            _pin_mismatch(),
        )

    if proc.returncode != 0:
        _activate_target()
        if _pins_satisfied():
            return True, None
        tail = (proc.stderr or proc.stdout or "")[-1200:]
        return False, "pip install failed (rc=%s): %s (%s)" % (
            proc.returncode,
            tail,
            _pin_mismatch(),
        )

    _activate_target()
    if _pins_satisfied():
        return True, None
    return False, (
        "pip install reported success but the pins are unsatisfied (%s)"
        % _pin_mismatch()
    )


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

def _regular_season(pl, pbp, through_week):
    frame = pbp.filter(
        (pl.col("season_type") == "REG")
        & (pl.col("two_point_attempt") != 1)
        & pl.col("posteam").is_not_null()
        & (pl.col("week") <= through_week)
    )
    return frame


def _targets(pl, frame):
    """A target is a pass attempt with an identified receiver. Sacks excluded."""
    return frame.filter(
        (pl.col("pass_attempt") == 1)
        & (pl.col("sack") != 1)
        & pl.col("receiver_player_id").is_not_null()
    )


def _carries(pl, frame):
    return frame.filter(
        (pl.col("rush_attempt") == 1) & pl.col("rusher_player_id").is_not_null()
    )


def _safe_share(pl, numerator, denominator, alias):
    """Share that yields null - not zero - when the denominator is unusable.

    A player with genuinely no targets and a player whose team totals are
    missing are different facts. Collapsing both to 0.0 would present a
    confident number built on absent data.
    """
    return (
        pl.when(pl.col(denominator) > 0)
        .then(pl.col(numerator) / pl.col(denominator))
        .otherwise(None)
        .alias(alias)
    )


def _compute_usage(pl, pbp, through_week):
    frame = _regular_season(pl, pbp, through_week)
    if frame.height == 0:
        raise ValueError(
            "no regular-season plays in window (through_week=%s)" % through_week
        )

    targets = _targets(pl, frame)
    carries = _carries(pl, frame)

    team_targets = targets.group_by("posteam").agg(
        pl.len().alias("team_targets"),
        pl.col("air_yards").fill_null(0).sum().alias("team_air_yards"),
    )
    team_carries = carries.group_by("posteam").agg(
        pl.len().alias("team_carries"),
    )
    teams = team_targets.join(
        team_carries, on="posteam", how="full", coalesce=True
    ).with_columns(
        pl.col("team_targets").fill_null(0),
        pl.col("team_air_yards").fill_null(0.0),
        pl.col("team_carries").fill_null(0),
    )

    # Grouped on (player_id, team) only, with the name taken as an aggregate.
    # nflverse play-by-play carries more than one spelling of the same player
    # - "M.Wilson" and "Mi.Wilson" are both Michael Wilson in 2025 - and
    # keying on the name split one stint into two rows, each holding a
    # fraction of his usage while both divided by the same team denominator.
    # That understated every share and made (player_id, team) non-unique, so
    # the recent-window join in _compute_trend attached one recent row to both
    # halves. player_display_name off the player_stats join is the
    # authoritative label, so the pbp spelling is only a fallback; .first()
    # takes the earliest appearance in play order, which is deterministic for
    # a given frame.
    receiving = targets.group_by(
        pl.col("receiver_player_id").alias("player_id"),
        pl.col("posteam").alias("team"),
    ).agg(
        pl.col("receiver_player_name").drop_nulls().first().alias("player_name"),
        pl.len().alias("targets"),
        pl.col("air_yards").fill_null(0).sum().alias("air_yards"),
        pl.col("complete_pass").fill_null(0).sum().alias("receptions"),
        (pl.col("yardline_100") <= REDZONE_YARDLINE).sum().alias("rz_targets"),
        pl.col("epa").fill_null(0).sum().alias("rec_epa"),
        # Latest week this stint saw a target. Feeds the recency tie-break when
        # two stints hold equal opportunities and something has to choose.
        pl.col("week").max().alias("last_receiving_week"),
    )

    rushing = carries.group_by(
        pl.col("rusher_player_id").alias("player_id"),
        pl.col("posteam").alias("team"),
    ).agg(
        pl.col("rusher_player_name").drop_nulls().first().alias("rush_player_name"),
        pl.len().alias("carries"),
        (pl.col("yardline_100") <= REDZONE_YARDLINE).sum().alias("rz_carries"),
        pl.col("epa").fill_null(0).sum().alias("rush_epa"),
        pl.col("week").max().alias("last_rushing_week"),
    )

    # Joined on the same two keys. A rusher with no targets brings only his
    # own spelling, hence the coalesce rather than a plain rename.
    usage = receiving.join(
        rushing, on=["player_id", "team"], how="full", coalesce=True
    ).with_columns(
        pl.coalesce("player_name", "rush_player_name").alias("player_name"),
        # A receiving-only stint has no rushing week and vice versa, so take
        # whichever is later rather than either one alone.
        pl.max_horizontal(
            "last_receiving_week", "last_rushing_week"
        ).alias("last_week"),
        pl.col("targets").fill_null(0),
        pl.col("air_yards").fill_null(0.0),
        pl.col("receptions").fill_null(0),
        pl.col("rz_targets").fill_null(0),
        pl.col("rec_epa").fill_null(0.0),
        pl.col("carries").fill_null(0),
        pl.col("rz_carries").fill_null(0),
        pl.col("rush_epa").fill_null(0.0),
    ).drop("rush_player_name", "last_receiving_week", "last_rushing_week")

    usage = usage.join(teams, left_on="team", right_on="posteam", how="left")

    usage = usage.with_columns(
        _safe_share(pl, "targets", "team_targets", "target_share"),
        _safe_share(pl, "air_yards", "team_air_yards", "air_yards_share"),
        _safe_share(pl, "carries", "team_carries", "rush_share"),
        (pl.col("targets") + pl.col("carries")).alias("opportunities"),
        (pl.col("rz_targets") + pl.col("rz_carries")).alias("rz_touches"),
        (pl.col("rec_epa") + pl.col("rush_epa")).alias("total_epa"),
    )

    return usage.with_columns(
        (
            WOPR_TARGET_WEIGHT * pl.col("target_share")
            + WOPR_AIR_YARDS_WEIGHT * pl.col("air_yards_share")
        ).alias("wopr"),
        _safe_share(pl, "total_epa", "opportunities", "epa_per_opportunity"),
    )


def _compute_trend(pl, pbp, through_week, lookback_weeks):
    """Recent-window shares against full-season shares.

    The absolute share level does not distinguish a locked-in role from a
    fading one. The delta is the part a start/sit decision turns on.

    Joined on player_id AND team, because _compute_usage groups per team: a
    player traded mid-season legitimately holds one row per stint. Joining on
    player_id alone let the recent window of the new team subtract from the
    season total of the old one, yielding a delta that describes no real
    player - a share against one denominator minus a share against another.
    Keying on the stint leaves the delta null wherever the two windows do not
    line up. A null delta is honest about a comparison that cannot be made;
    a mixed one is confidently wrong about a player who changed teams.
    """
    season = _compute_usage(pl, pbp, through_week)

    first_recent_week = max(1, through_week - lookback_weeks + 1)
    recent_frame = pbp.filter(pl.col("week") >= first_recent_week)
    recent = _compute_usage(pl, recent_frame, through_week)

    recent = recent.select(
        "player_id",
        "team",
        pl.col("target_share").alias("recent_target_share"),
        pl.col("wopr").alias("recent_wopr"),
        pl.col("rush_share").alias("recent_rush_share"),
        pl.col("opportunities").alias("recent_opportunities"),
    )

    merged = season.join(recent, on=["player_id", "team"], how="left")

    return merged.with_columns(
        (pl.col("recent_target_share") - pl.col("target_share")).alias(
            "target_share_delta"
        ),
        (pl.col("recent_wopr") - pl.col("wopr")).alias("wopr_delta"),
        (pl.col("recent_rush_share") - pl.col("rush_share")).alias(
            "rush_share_delta"
        ),
    )


# ---------------------------------------------------------------------------
# shared pipeline - both commands run exactly this
# ---------------------------------------------------------------------------

def _parse_window(params, command, week_key="through_week"):
    """Season / week / lookback, validated identically for both commands.

    Returns (window, error_message). `week_key` names the param the caller
    exposes so the error text points at what the caller actually accepts.
    """
    try:
        season = int(params.get("season"))
    except (TypeError, ValueError):
        return None, (
            "%s: 'season' is required and must be an integer" % command
        )

    try:
        through_week = int(params.get(week_key))
    except (TypeError, ValueError):
        return None, (
            "%s: '%s' is required and must be an integer" % (command, week_key)
        )

    if not 1 <= through_week <= FANTASY_LAST_WEEK:
        return None, (
            "%s=%s outside the fantasy season (1-%s)"
            % (week_key, through_week, FANTASY_LAST_WEEK)
        )

    try:
        lookback_weeks = int(
            params.get("lookback_weeks", _DEFAULT_LOOKBACK_WEEKS)
        )
    except (TypeError, ValueError):
        lookback_weeks = _DEFAULT_LOOKBACK_WEEKS
    if lookback_weeks < 1:
        return None, "lookback_weeks must be >= 1, got %s" % lookback_weeks

    return (
        {
            "season": season,
            "through_week": through_week,
            "lookback_weeks": lookback_weeks,
        },
        None,
    )


def _load_frames(nflreadpy, season):
    """Load play-by-play + the position lookup for a season.

    Returns (pbp, positions, error_message).
    """
    pbp = nflreadpy.load_pbp(seasons=[season])
    if pbp.height == 0:
        return None, None, "no play-by-play returned for season %s" % season

    missing = [c for c in _PBP_COLUMNS if c not in pbp.columns]
    if missing:
        return None, None, (
            "play-by-play is missing expected columns: %s" % ", ".join(missing)
        )
    pbp = pbp.select(_PBP_COLUMNS)

    stats = nflreadpy.load_player_stats(seasons=[season])
    if stats.height == 0:
        return None, None, "no player stats returned for season %s" % season
    positions = stats.select(_PLAYER_STATS_COLUMNS).unique(
        subset=["player_id"], keep="first"
    )

    return pbp, positions, None


def _build_report_payload(
    pl,
    pbp,
    positions,
    season,
    through_week,
    lookback_weeks,
    position,
    team,
    min_opportunities,
    limit,
):
    """The report body. Single source of truth for both commands."""
    report = _compute_trend(pl, pbp, through_week, lookback_weeks)
    report = report.join(positions, on="player_id", how="left")

    if position is not None:
        report = report.filter(pl.col("position") == position)
    if team is not None:
        report = report.filter(pl.col("team") == team)

    report = report.filter(pl.col("opportunities") >= min_opportunities)

    # WOPR is a receiving metric: ranking backfields by it buries a
    # high-volume rusher beneath a pass-catching backup.
    sort_key = "opportunities" if position == "RB" else "wopr"
    report = report.sort(sort_key, descending=True, nulls_last=True)

    if limit > 0:
        report = report.head(limit)

    return {
        "season": season,
        "through_week": through_week,
        "position": position or "ALL",
        "team": team or "ALL",
        "lookback_weeks": lookback_weeks,
        "sorted_by": sort_key,
        "method_version": "workload-v0",
        "source": "nflverse play-by-play via nflreadpy (public data)",
        "players": report.to_dicts(),
    }


def _normalize_name(value):
    """Fold the two nflverse spellings toward each other for comparison.

    "J.Smith-Njigba" and "Jaxon Smith-Njigba" must both be reachable from what
    a user types, so periods become spaces and whitespace collapses.
    """
    return " ".join(str(value or "").replace(".", " ").lower().split())


def _tokens(value):
    """Normalized name as a set of whole words.

    Matching on tokens rather than raw substrings keeps "Brown" off
    "Brownlee": a surname that merely starts with the query is a different
    player, not a looser spelling of the same one. Hyphenated names stay
    single tokens ("smith-njigba"), which is what a caller types.
    """
    return set(_normalize_name(value).split())


def _name_hits(players, predicate, name_columns=None):
    """Rows whose either name column satisfies `predicate`, as (row, name).

    `predicate` receives the normalized name string. `name_columns` defaults
    to the nflverse pair; ESPN rows carry a single "name" and pass their own.
    """
    hits = []
    for row in players:
        for column in name_columns or _NAME_COLUMNS:
            name = _normalize_name(row.get(column))
            if name and predicate(name):
                hits.append((row, row.get(column)))
                break
    return hits


def _stint_rank(row):
    """Sort key for one player's stints: busiest first, then most recent.

    Returned as a tuple so opportunities decide and last_week only breaks a
    tie. Equal opportunities used to be settled by whichever row the frame
    happened to yield first, which is not a decision anyone made; recency is
    the better default because a start/sit question is about where a player is
    now, not where he was busiest.
    """
    return (row.get("opportunities") or 0, row.get("last_week") or 0)


def _stint_summary(row):
    """Compact per-stint shape for the response's other_stints."""
    return {
        "team": row.get("team"),
        "opportunities": row.get("opportunities"),
        "wopr": row.get("wopr"),
    }


def _stints_for(players, row):
    """Every row this player holds, busiest-and-most-recent first."""
    return sorted(
        [r for r in players if r.get("player_id") == row.get("player_id")],
        key=_stint_rank,
        reverse=True,
    )


def _match_player(players, query, name_columns=None, id_key="player_id", rank=None):
    """Resolve a name against the report. Returns one of:

        {"row": row, "name": matched_name}   exactly one player matched
        {"candidates": [name, ...]}          several distinct players matched
        None                                 nothing matched

    Exact match on either name column wins outright; only when nothing is
    exact does it fall back to whole-word matching in either direction, so
    "Nabers" reaches "Malik Nabers" but not "Nabersmith".

    Candidates are collapsed by `id_key` before the count is taken, because
    a player traded mid-season legitimately holds two rows (usage is grouped
    per team). Two rows for one player is not an ambiguous query; two players
    is, and guessing between them on opportunities would hand back a
    confidently wrong row under a name the caller never typed.

    `name_columns`, `id_key` and `rank` exist so the ESPN-backed context
    command reuses this exact token logic against differently-shaped rows
    rather than restating it. Defaults reproduce the workload-report behavior.
    """
    wanted = _normalize_name(query)
    if not wanted:
        return None

    rank = rank or _stint_rank

    hits = _name_hits(players, lambda name: name == wanted, name_columns)
    if not hits:
        wanted_tokens = _tokens(wanted)
        hits = _name_hits(
            players,
            lambda name: _tokens(name) >= wanted_tokens
            or _tokens(name) <= wanted_tokens,
            name_columns,
        )
    if not hits:
        return None

    by_player = {}
    for row, name in hits:
        by_player.setdefault(row.get(id_key) or name, []).append(
            (row, name)
        )

    def _best(group):
        return max(group, key=lambda hit: rank(hit[0]))

    if len(by_player) > 1:
        best = [_best(group) for group in by_player.values()]
        best.sort(key=lambda hit: rank(hit[0]), reverse=True)
        return {"candidates": [name for _, name in best]}

    row, name = _best(next(iter(by_player.values())))
    return {"row": row, "name": name}


def _resolve_one(players, query, season, through_week, position, team=None):
    """Match one name against a built report and describe the outcome.

    Returns the per-player block shared by get_player_workload and
    get_player_pair_workload, so a miss reads identically whichever command
    produced it. Every outcome carries the same keys - player, matched_name,
    query, requested_team, reason, selected_team, other_stints - plus a message,
    and candidates when a name collided.

    A player traded mid-season holds one row per stint, so a name on its own
    does not name a row. Which row you get is now an explicit decision:

      team supplied - the name is matched only among that team's rows, which
        also keeps a surname that is unique on one roster from reading as
        ambiguous league-wide. A player who matched elsewhere but never played
        for that team is not_found SCOPED TO THAT TEAM, and the message lists
        the stints he does hold. There is deliberately no fallback to another
        stint: a caller who named a team asked about that team, and quietly
        answering about a different one is the confidently-wrong behavior this
        redesign exists to remove.

      no team - the busiest stint wins, tie-broken on the most recent week
        (see _stint_rank).

    Either way selected_team names the stint that answered and other_stints
    lists the ones that did not, so a caller can see that a choice was made and
    what it was made against. Previously the choice was invisible: Rashid
    Shaheed's 2025 week 17 lookup silently returned his New Orleans stint and
    said nothing about the Seattle one.

    A miss is described, not raised. These commands run under
    continue_on_error, which preserves the payload of a status True result and
    discards the message of a status False one - so reporting a miss as False
    threw away the only text that said what went wrong, and "'Brown' matches
    three players" reached the caller looking exactly like "Mahomes is not in
    this report": both as nothing at all.
    """
    wanted_team = str(team).strip().upper() if team else None
    scope = " on %s" % wanted_team if wanted_team else ""

    pool = players
    if wanted_team:
        pool = [
            r for r in players
            if str(r.get("team") or "").upper() == wanted_team
        ]

    matched = _match_player(pool, query)

    if matched is None and wanted_team:
        # He may hold rows on other rosters. Identify him against the full
        # report so the miss can name those stints - reporting them, never
        # answering with one of them.
        elsewhere = _match_player(players, query)
        if elsewhere is not None and "row" in elsewhere:
            stints = _stints_for(players, elsewhere["row"])
            return {
                "player": None,
                "matched_name": None,
                "query": query,
                "requested_team": team,
                "reason": "not_found",
                "selected_team": None,
                "other_stints": [_stint_summary(r) for r in stints],
                "message": "'%s' matched %s for season %s week %s but holds no "
                "%s row; stints found: %s"
                % (
                    query,
                    elsewhere["name"],
                    season,
                    through_week,
                    wanted_team,
                    ", ".join(
                        "%s (%s opportunities)"
                        % (r.get("team"), r.get("opportunities"))
                        for r in stints
                    ),
                ),
            }
        # Ambiguous or absent league-wide: fall through to the generic
        # handling below rather than inventing a team-specific story.
        matched = elsewhere

    if matched is None:
        return {
            "player": None,
            "matched_name": None,
            "query": query,
            "requested_team": team,
            "reason": "not_found",
            "selected_team": None,
            "other_stints": [],
            "message": "no player matching '%s'%s found in %s for season %s week %s"
            % (query, scope, position or "ALL", season, through_week),
        }

    if "candidates" in matched:
        return {
            "player": None,
            "matched_name": None,
            "query": query,
            "requested_team": team,
            "reason": "ambiguous",
            "candidates": matched["candidates"],
            "selected_team": None,
            "other_stints": [],
            "message": "ambiguous match for '%s'%s in %s season %s week %s: "
            "matches %s - provide a more specific name"
            % (
                query,
                scope,
                position or "ALL",
                season,
                through_week,
                ", ".join(matched["candidates"]),
            ),
        }

    stints = _stints_for(players, matched["row"])
    # With a team the pool held only that team's rows, so the match IS the
    # scoped row; without one, the rank order decides.
    row = matched["row"] if wanted_team else stints[0]

    return {
        "player": row,
        "matched_name": matched["name"],
        "query": query,
        "requested_team": team,
        "reason": "matched",
        "selected_team": row.get("team"),
        "other_stints": [_stint_summary(r) for r in stints if r is not row],
    }


# ---------------------------------------------------------------------------
# roster context - ESPN via sports-skills
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# STOPGAP - remove once sports-skills is fixed upstream
# ---------------------------------------------------------------------------
# sports-skills overrides urllib's User-Agent with a spoofed browser string,
# and ESPN's edge rejects it with 403 "Access Denied" on every request. This
# breaks get_player_context entirely: it fails on the very first get_teams()
# call and never reaches the depth chart or the injury feed.
#
# Measured 2026-08-04 against site.api.espn.com/.../football/nfl/teams:
#
#     Mozilla/5.0 (Macintosh; ...) AppleWebKit/537.36        -> 403  (what it sends)
#     Mozilla/5.0 (...) Chrome/120.0.0.0 Safari/537.36       -> 403  (well-formed too)
#     Mozilla/5.0                                            -> 403
#     sports-skills/0.27.1                                   -> 403
#     SportsSkills/1.0                                       -> 403
#     curl/8.7.1                                             -> 200
#     Go-http-client/2.0                                     -> 200
#     Python-urllib/3.14                                     -> 200
#     <no override at all, urllib's own default>             -> 200
#
# So the edge is not rejecting a malformed browser string - it rejects any
# browser claim and any custom product name, and accepts recognized standard
# client tokens. The override is the bug; urllib's untouched default works.
#
# This sets the UA to exactly what urllib would send natively, so the stopgap
# reproduces the upstream fix rather than inventing a third behavior. The
# constant is duplicated upstream (_espn_base.py:107, football/_connector.py:420,
# polymarket/_connector.py:92); this only repairs the _espn_base copy, which is
# the one sports_skills.nfl uses. It is NOT a fix for football or polymarket.
#
# Fixed upstream in sports-skills 0.30.0 (commit e6a5870, #101, 2026-08-04),
# which replaces the constant with a derived Python-urllib string plus a
# SPORTS_SKILLS_USER_AGENT override. Verified 2026-08-06 against origin/main at
# 0.30.1: this block becomes a silent no-op there, because it only ever
# replaces the exact known-bad string. REMOVE IT once the pod pins >=0.30.1;
# the pod was still on 0.27.1 at that check, and get_scoreboard() reaching ESPN
# through this workaround is what makes the temporal gate work today.
_BROKEN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
)


def _urllib_default_user_agent():
    """What urllib.request sends when nothing overrides it."""
    return "Python-urllib/%d.%d" % sys.version_info[:2]


def _apply_user_agent_stopgap():
    """Replace the known-bad UA on sports_skills._espn_base.

    Returns a short note when the swap was applied, else None.

    Only the exact known-bad string is replaced, so this becomes a silent
    no-op the day upstream fixes it or an operator overrides it deliberately.

    Deliberately NOT restored afterwards: putting the broken string back would
    re-break every later ESPN call in this worker process, and the pod reuses
    workers across requests.
    """
    try:
        from sports_skills import _espn_base
    except ImportError as exc:
        return "sports_skills._espn_base not importable: %s" % exc

    if getattr(_espn_base, "_USER_AGENT", None) != _BROKEN_USER_AGENT:
        return None

    _espn_base._USER_AGENT = _urllib_default_user_agent()
    return (
        "applied User-Agent stopgap: sports-skills ships a spoofed browser UA "
        "that ESPN 403s; using urllib's default instead. Remove once fixed "
        "upstream."
    )


# Resolution order matters: an abbreviation is unambiguous, an id is exact,
# and only then do the prose fields get a look.
_TEAM_MATCH_FIELDS = ["abbreviation", "id", "name", "nickname"]

# Fields a loose query ("New York") may match on once nothing is exact.
_TEAM_FUZZY_FIELDS = ["name", "nickname", "location"]

# nflverse posteam codes that disagree with ESPN's abbreviations.
#
# This matters because the natural way to call get_player_context is to hand it
# the team off a workload row, and that row carries the nflverse spelling. On
# these five codes ESPN has no matching abbreviation, so the lookup resolved to
# nothing - and because callers treat missing context as a soft degrade, the
# player simply came back with no role and no injury rather than an error.
# Silent, and wrong only for some teams, which is the worst shape for a bug.
#
# Two are current-era (LA, WAS); the other three appear in historical
# play-by-play from before the relocations, so any query over an older season
# hits them.
_NFLVERSE_TEAM_ALIASES = {
    "la": "LAR",    # Rams        - nflverse LA,  ESPN LAR
    "was": "WSH",   # Commanders  - nflverse WAS, ESPN WSH
    "oak": "LV",    # Raiders     - pre-2020 seasons
    "sd": "LAC",    # Chargers    - pre-2017 seasons
    "stl": "LAR",   # Rams        - pre-2016 seasons
}


def _espn_data(response, what):
    """Unwrap the sports-skills {status, data, message} envelope.

    Returns (data, error_message).
    """
    if not isinstance(response, dict):
        return None, "%s returned %s, expected a dict" % (
            what,
            type(response).__name__,
        )
    if not response.get("status"):
        return None, "%s failed: %s" % (
            what,
            response.get("message") or "unknown error",
        )
    data = response.get("data")
    if not isinstance(data, dict):
        return None, "%s returned no data" % what
    return data, None


# ESPN's season.type: 1 preseason, 2 regular season, 3+ postseason. Only 2
# carries a fantasy week; the others have their own week numbering that means
# something else entirely, so a bare week number is not a coordinate.
_ESPN_SEASON_TYPE_REGULAR = 2


def _opt_int(value):
    """int(value) or None. Used where a param is optional, not defaulted."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _current_fantasy_week(nfl):
    """The live coordinate off ESPN's scoreboard. Returns (current, error).

    `current` is {"season", "week", "season_type", "is_regular_season"}.
    `week` is populated only during the regular season, because that is the
    only season type whose week number is a fantasy week.

    get_scoreboard() with no arguments reports where the league actually is,
    not the last week it played. Measured 2026-08-06 on Hall of Fame game
    night it returned season {"year": 2026, "type": 1}, week {"number": 1} -
    preseason week 1, rather than a stale week 22 left over from February.
    """
    data, err = _espn_data(nfl.get_scoreboard(), "get_scoreboard")
    if err:
        return None, err

    season = data.get("season") or {}
    week = data.get("week") or {}

    season_type = _opt_int(season.get("type"))
    if season_type is None:
        return None, "get_scoreboard returned no usable season.type"

    current = {
        "season": _opt_int(season.get("year")),
        "week": None,
        "season_type": season_type,
        "is_regular_season": season_type == _ESPN_SEASON_TYPE_REGULAR,
    }
    if current["is_regular_season"]:
        current["week"] = _opt_int(week.get("number"))
    return current, None


def _resolve_team(nfl, query):
    """Resolve a team query to one ESPN team dict. Returns (team, error).

    Exact match on abbreviation / id / name / nickname in that order, then the
    nflverse alias table, then a whole-word fallback across name / nickname /
    location. An ambiguous loose query ("New York" -> Giants and Jets) is
    reported, never guessed: picking one would silently answer about the wrong
    roster, which is the same class of bug that resolving the team is here to
    prevent.
    """
    wanted = _normalize_name(query)
    if not wanted:
        return None, "get_player_context: 'team' is required"

    data, err = _espn_data(nfl.get_teams(), "get_teams")
    if err:
        return None, err

    teams = data.get("teams") or []
    if not teams:
        return None, "get_teams returned no teams"

    for field in _TEAM_MATCH_FIELDS:
        for team in teams:
            if _normalize_name(team.get(field)) == wanted:
                return team, None

    # An nflverse code is not an ESPN abbreviation. Translated only after the
    # exact pass above, so a genuine ESPN value always wins if one ever
    # collides with a code in the table.
    aliased = _NFLVERSE_TEAM_ALIASES.get(wanted)
    if aliased:
        aliased_wanted = _normalize_name(aliased)
        for team in teams:
            if _normalize_name(team.get("abbreviation")) == aliased_wanted:
                return team, None

    wanted_tokens = _tokens(wanted)
    hits = {}
    for team in teams:
        for field in _TEAM_FUZZY_FIELDS:
            if _tokens(team.get(field)) >= wanted_tokens:
                hits.setdefault(str(team.get("id") or ""), team)
                break

    if len(hits) == 1:
        return next(iter(hits.values())), None
    if len(hits) > 1:
        names = sorted(str(t.get("name") or "") for t in hits.values())
        return None, (
            "unknown team: '%s' is ambiguous, matches %s - use an abbreviation"
            % (query, ", ".join(names))
        )

    return None, (
        "unknown team: '%s' matched none of the %s NFL teams by abbreviation, "
        "id, name or nickname" % (query, len(teams))
    )


def _depth_chart_entries(nfl, team):
    """Flatten a team's depth chart to one row per athlete-position slot.

    Returns (entries, error). A player legitimately holds several rows: a
    returner also listed at WR appears on both units.
    """
    data, err = _espn_data(
        nfl.get_depth_chart(team_id=team.get("id")), "get_depth_chart"
    )
    if err:
        return None, err

    entries = []
    for chart in data.get("charts") or []:
        for position in chart.get("positions") or []:
            for athlete in position.get("athletes") or []:
                entries.append(
                    {
                        "id": str(athlete.get("id") or ""),
                        "name": athlete.get("name") or "",
                        "depth": athlete.get("depth"),
                        "position": position.get("abbreviation") or "",
                        "position_name": position.get("name") or "",
                        "unit": chart.get("name") or "",
                    }
                )
    return entries, None


def _team_injuries(nfl, team):
    """The resolved team's injury block out of the league-wide feed.

    Returns (injuries, error). team_id is authoritative; the normalized team
    name is the fallback for a block that arrives without one.

    Coverage is PARTIAL, not injured-only. Measured 2026-08-06 against CIN
    (97 depth-chart entries, 25 injury entries): Chase, Higgins, Iosivas and
    Charlie Jones all appear carrying status "Active", while Tinsley does not
    appear at all. Presence here therefore does not mean a player is hurt,
    and absence does not mean he is healthy - it means the feed does not
    cover him. An empty list likewise means this team has no block in the
    feed, not that the roster is fully fit. The caller reports it as such.
    """
    data, err = _espn_data(nfl.get_injuries(), "get_injuries")
    if err:
        return None, err

    blocks = data.get("teams") or []
    team_id = str(team.get("id") or "")
    team_name = _normalize_name(team.get("name"))

    block = None
    if team_id:
        for candidate in blocks:
            if str(candidate.get("team_id") or "") == team_id:
                block = candidate
                break
    if block is None and team_name:
        for candidate in blocks:
            if _normalize_name(candidate.get("team")) == team_name:
                block = candidate
                break
    if block is None:
        return [], None

    return block.get("injuries") or [], None


def _depth_label(entry):
    """"WR1"-style label: position abbreviation plus depth rank."""
    position = entry.get("position") or ""
    depth = entry.get("depth")
    if position and isinstance(depth, int):
        return "%s%s" % (position, depth)
    return position


def _shallowest(row):
    """Rank for depth-chart rows: the starter outranks the backup.

    _match_player keeps the highest-ranked row and depth counts upward, so
    the sign flips. A row carrying no depth sorts last.
    """
    depth = row.get("depth")
    return -depth if isinstance(depth, int) else -999


def _context_envelope(team, stopgap_note, depth_err, injury_err, week_check=None):
    """Fields every get_player_context response carries, hit or miss.

    Held in one place so a soft miss reports the same team, provenance and
    degradation as a hit. A caller should not have to branch on the outcome to
    learn which sources actually answered.

    `week_check` carries the requested-versus-current coordinate and is merged
    in verbatim when the caller supplied season/week. Omitted entirely
    otherwise, so a caller who does not ask for a temporal check sees exactly
    the payload this command has always returned.
    """
    envelope = {
        "team": {
            "id": team.get("id"),
            "name": team.get("name"),
            "abbreviation": team.get("abbreviation"),
        },
        "source": "ESPN via sports-skills "
        "(get_teams, get_depth_chart, get_injuries)",
        # Current-state only, per the module docstring. Stamped into every
        # payload so a consumer pairing this with a past week can see the
        # mismatch in the data rather than having to read the docs.
        "as_of": "current",
        # Reported for parity with the workload commands, but read it
        # differently here: this command touches neither package and never
        # calls _ensure_deps, so these are whatever the worker happens to hold
        # rather than what produced this answer, and either may be null.
        "deps": _loaded_versions(),
    }

    # One source down while the other answered: the result stands, but the
    # gap is named rather than passed off as a complete picture.
    if depth_err or injury_err:
        envelope["degraded"] = {
            "depth_chart_error": depth_err,
            "injury_error": injury_err,
        }

    # Surfaced rather than silent: a caller reading this response should be
    # able to see that a local workaround is propping up the upstream call,
    # and the field disappears on its own once sports-skills is fixed.
    if stopgap_note:
        envelope["stopgap"] = stopgap_note

    if week_check:
        envelope.update(week_check)

    return envelope


# ---------------------------------------------------------------------------
# Machina workload snapshot - aggregate contract, never an event observation
# ---------------------------------------------------------------------------

def _has_value(value):
    return value is not None and value != "" and value != [] and value != {}


def _official_statistic_string(field, value):
    valid_int = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    valid_float = (
        isinstance(value, float)
        and math.isfinite(value)
        and value >= 0
        and value.is_integer()
    )
    if not (valid_int or valid_float):
        raise ValueError(f"{field} must be a non-negative integer")
    return str(int(value))


def _validate_observed_at(observed_at):
    value = str(observed_at or "")
    if _RFC3339_SECOND_60.fullmatch(value):
        raise ValueError(
            "observed_at is not a valid RFC3339 timestamp: second 60 is not accepted"
        )
    if not _RFC3339_OFFSET.fullmatch(value):
        raise ValueError(
            "observed_at is required as RFC3339 with an explicit offset"
        )
    try:
        parse_value = value
        if parse_value.endswith("Z"):
            parse_value = parse_value[:-1] + "+00:00"
        datetime.fromisoformat(parse_value)
    except ValueError as exc:
        raise ValueError("observed_at is not a valid RFC3339 timestamp") from exc
    return value


def _provider_id_evidence(
    machina_id,
    entity_type,
    provider_id,
    resolution_method,
    evidence,
):
    if not all(_has_value(value) for value in (machina_id, provider_id, evidence)):
        return None
    return {
        "machina_id": machina_id,
        "entity_type": entity_type,
        "provider_namespace": "nflverse",
        "provider_id": str(provider_id),
        "resolution_method": resolution_method,
        "confidence": 1.0,
        "evidence": evidence,
    }


def _snapshot_player_sort_key(row, sort_key):
    value = row.get(sort_key)
    is_number = (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )
    return (
        value is None,
        -value if is_number else 0,
        str(row.get("player_id") or ""),
        str(row.get("team") or ""),
    )


def _snapshot_contract_findings(snapshot):
    """Small runtime guard for the public JSON Schema's critical invariants."""
    findings = []
    if not isinstance(snapshot, dict) or set(snapshot) != {"machina_workload_snapshot"}:
        return ["snapshot must contain only machina_workload_snapshot"]
    body = snapshot.get("machina_workload_snapshot")
    if not isinstance(body, dict):
        return ["machina_workload_snapshot must be an object"]
    if body.get("schema_version") != _SNAPSHOT_SCHEMA_VERSION:
        findings.append("unexpected schema_version")
    required_body_keys = {
        "schema_version",
        "observed_at",
        "identity",
        "rights",
        "competition",
        "season",
        "scope",
        "players",
        "provider_ids",
        "capabilities",
        "provenance",
    }
    if not required_body_keys <= set(body) or set(body) - required_body_keys - {"team"}:
        findings.append("snapshot body does not match the closed public contract")
    try:
        _validate_observed_at(body.get("observed_at"))
    except ValueError as exc:
        findings.append(str(exc))

    rights = body.get("rights")
    if rights != _SNAPSHOT_RIGHTS:
        findings.append("rights must be the exact open-public prototype-only claim")

    capabilities = body.get("capabilities")
    if not isinstance(capabilities, dict) or set(capabilities) != {
        "present",
        "absent",
        "not_expressible",
    }:
        findings.append("capabilities must report present, absent and not_expressible")
    elif capabilities.get("present") != sorted(_SNAPSHOT_PRESENT_CAPABILITIES):
        findings.append("capabilities overclaim or omit present support")
    else:
        present = capabilities["present"]
        absent = capabilities["absent"]
        not_expressible = capabilities["not_expressible"]
        vocabulary = set(_SNAPSHOT_CAPABILITY_VOCABULARY)
        if (
            present != sorted(set(present))
            or absent != sorted(set(absent))
            or set(present).intersection(absent)
            or set(present).union(absent) != vocabulary
            or not_expressible != sorted(
                name for name in absent if name.startswith("event.")
            )
        ):
            findings.append("capabilities do not partition the pinned vocabulary")

    provenance = body.get("provenance")
    dependencies = provenance.get("dependencies") if isinstance(provenance, dict) else None
    if not isinstance(dependencies, dict) or not all(
        isinstance(dependencies.get(name), str) and dependencies.get(name)
        for name in ("nflreadpy", "polars")
    ):
        findings.append("provenance must name nflreadpy and polars versions")
    elif set(dependencies) != {"nflreadpy", "polars"}:
        findings.append("provenance dependencies must match the closed contract")
    source_refs = provenance.get("source_refs") if isinstance(provenance, dict) else None
    if not isinstance(source_refs, list) or not source_refs:
        findings.append("provenance must carry safe source_refs")
    else:
        for source_ref in source_refs:
            value = source_ref.get("value") if isinstance(source_ref, dict) else None
            if not _has_value(value) or "://" in str(value) or "credential" in str(value).lower():
                findings.append("source_refs must be non-URL and non-credential")
                break
    if not isinstance(provenance, dict) or provenance.get("method_version") != "workload-v0":
        findings.append("provenance must name workload-v0")
    determinism = provenance.get("determinism") if isinstance(provenance, dict) else None
    if determinism != {
        "id_strategy": "provider-scoped-surrogate",
        "digest": "blake2b-128",
        "canonical_id_service": "not-available-in-this-phase",
    }:
        findings.append("provenance must describe the injected surrogate resolver")

    season = body.get("season")
    scope = body.get("scope")
    if not isinstance(season, dict) or not (
        isinstance(season.get("year"), int)
        and not isinstance(season.get("year"), bool)
    ):
        findings.append("season must carry an integer year")
    if not isinstance(scope, dict) or not (
        isinstance(scope.get("through_week"), int)
        and not isinstance(scope.get("through_week"), bool)
        and 1 <= scope["through_week"] <= FANTASY_LAST_WEEK
        and isinstance(scope.get("lookback_weeks"), int)
        and not isinstance(scope.get("lookback_weeks"), bool)
        and scope["lookback_weeks"] >= 1
        and isinstance(scope.get("position"), str)
        and bool(scope["position"])
        and isinstance(scope.get("team"), str)
        and bool(scope["team"])
        and scope.get("sorted_by") in ("opportunities", "wopr")
    ):
        findings.append("scope is missing a bounded native report coordinate")

    players = body.get("players")
    if not isinstance(players, list):
        findings.append("players must be an array")
    else:
        for player in players:
            if not isinstance(player, dict) or not _has_value(player.get("id")):
                findings.append("every player must have an id")
                break
            if not isinstance(player.get("name"), str) or not player["name"]:
                findings.append("every player must have a name label")
                break
            if set(player) - {"id", "name", "position", "team_id", "statistics", "metrics"}:
                findings.append("player contains a property outside the closed contract")
                break
            if not _SURROGATE_URN.fullmatch(str(player["id"])):
                findings.append("every player id must be a marked surrogate")
                break
            statistics = player.get("statistics")
            if not isinstance(statistics, dict) or set(statistics) - set(
                _SNAPSHOT_STATISTICS.values()
            ):
                findings.append("statistics contain a non-pinned property")
                break
            if not all(
                isinstance(value, str) and value.isdigit()
                for value in statistics.values()
            ):
                findings.append("statistics must carry non-negative integer strings")
                break
            metrics = player.get("metrics")
            if not isinstance(metrics, dict) or set(metrics) - set(_SNAPSHOT_METRICS):
                findings.append("metrics contain an unbounded property")
                break
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                for value in metrics.values()
            ):
                findings.append("metrics must be numeric")
                break
            if not all(
                isinstance(metrics[name], int) and not isinstance(metrics[name], bool)
                for name in _SNAPSHOT_INTEGER_METRICS.intersection(metrics)
            ):
                findings.append("integer metrics must remain integers")
                break
            if player.get("position") is not None and (
                not isinstance(player["position"], str) or not player["position"]
            ):
                findings.append("player position must be a non-empty string")
                break
            if player.get("team_id") is not None and not _SURROGATE_URN.fullmatch(
                str(player["team_id"])
            ):
                findings.append("player team_id must be a marked surrogate")
                break

    for entity_name in ("competition", "season", "team"):
        entity = body.get(entity_name)
        if entity is not None and (
            not isinstance(entity, dict)
            or not _SURROGATE_URN.fullmatch(str(entity.get("id") or ""))
        ):
            findings.append("%s must carry a marked surrogate id" % entity_name)
    team = body.get("team")
    if team is not None and (
        not isinstance(team.get("abbreviation"), str) or not team["abbreviation"]
    ):
        findings.append("team abbreviation must be a non-empty string")

    provider_ids = body.get("provider_ids")
    if not isinstance(provider_ids, list) or not provider_ids:
        findings.append("provider_ids must carry structured evidence")
    else:
        provider_items_valid = True
        for item in provider_ids:
            if not isinstance(item, dict) or not all(
                _has_value(item.get(key))
                for key in (
                    "machina_id",
                    "entity_type",
                    "provider_namespace",
                    "provider_id",
                    "resolution_method",
                    "evidence",
                )
            ):
                findings.append("provider_ids contain missing evidence")
                provider_items_valid = False
                break
            if set(item) != {
                "machina_id",
                "entity_type",
                "provider_namespace",
                "provider_id",
                "resolution_method",
                "confidence",
                "evidence",
            }:
                findings.append("provider evidence contains an extra property")
                provider_items_valid = False
                break
            if item.get("entity_type") not in {
                "competition",
                "season",
                "player",
                "team",
            }:
                findings.append("provider evidence has an unknown entity_type")
                provider_items_valid = False
                break
            if item.get("provider_namespace") != "nflverse":
                findings.append("provider_ids must remain nflverse-scoped")
                provider_items_valid = False
                break
            if not _SURROGATE_URN.fullmatch(str(item.get("machina_id"))):
                findings.append("provider evidence must point to a marked surrogate")
                provider_items_valid = False
                break
            if item.get("confidence") != 1.0:
                findings.append("provider evidence confidence must be exactly 1.0")
                provider_items_valid = False
                break
            expected_method = (
                "declared"
                if item.get("entity_type") in {"competition", "season"}
                else "provider-native"
            )
            if item.get("resolution_method") != expected_method:
                findings.append("provider evidence has an incorrect resolution_method")
                break

        if provider_items_valid:
            if any(
                item in provider_ids[:index]
                for index, item in enumerate(provider_ids)
            ):
                findings.append("provider_ids must not contain duplicate evidence")

            entity_counts = {
                entity_type: sum(
                    item["entity_type"] == entity_type for item in provider_ids
                )
                for entity_type in ("competition", "season")
            }
            if entity_counts != {"competition": 1, "season": 1}:
                findings.append(
                    "provider_ids must contain exactly one competition and one season item"
                )

            evidence_counts = {}
            provider_targets = {}
            provider_conflict = False
            for item in provider_ids:
                evidence_key = (item["entity_type"], item["machina_id"])
                evidence_counts[evidence_key] = evidence_counts.get(evidence_key, 0) + 1
                provider_key = (
                    item["entity_type"],
                    item["provider_namespace"],
                    item["provider_id"],
                )
                previous_target = provider_targets.get(provider_key)
                if previous_target is not None and previous_target != item["machina_id"]:
                    provider_conflict = True
                provider_targets[provider_key] = item["machina_id"]

            if provider_conflict or any(
                count != 1 for count in evidence_counts.values()
            ):
                findings.append("provider evidence conflicts for an emitted surrogate")

            expected_evidence = set()
            for entity_type in ("competition", "season", "team"):
                entity = body.get(entity_type)
                if isinstance(entity, dict) and _has_value(entity.get("id")):
                    expected_evidence.add((entity_type, entity["id"]))
            if isinstance(players, list):
                for player in players:
                    if not isinstance(player, dict):
                        continue
                    if _has_value(player.get("id")):
                        expected_evidence.add(("player", player["id"]))
                    if _has_value(player.get("team_id")):
                        expected_evidence.add(("team", player["team_id"]))

            actual_evidence = set(evidence_counts)
            if expected_evidence - actual_evidence:
                findings.append("provider evidence is missing for an emitted surrogate")
            if actual_evidence - expected_evidence:
                findings.append("provider evidence references an unemitted surrogate")

    forbidden = {
        "machina_sports_schema",
        "sport_schema_graph",
        "event_view",
        "@context",
        "@id",
        "@type",
    }

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    for key in keys(snapshot):
        if key in forbidden or str(key).startswith("sport:"):
            findings.append("event/RDF/envelope keys are forbidden in this aggregate")
            break
    return findings


def _project_machina_workload_snapshot(
    report,
    observed_at,
    dependency_versions,
    *,
    id_resolver,
    rights,
    capability_names,
    contract_findings_fn,
):
    """Pure projection of a native report into the aggregate snapshot contract."""
    observed_at = _validate_observed_at(observed_at)
    if rights != _SNAPSHOT_RIGHTS:
        raise ValueError("rights are missing or unreadable: %s" % rights)

    if set(capability_names) != set(_SNAPSHOT_CAPABILITY_VOCABULARY):
        raise ValueError("canonical capability vocabulary does not match snapshot contract v1")
    known_capabilities = _SNAPSHOT_CAPABILITY_VOCABULARY
    unknown_present = sorted(set(_SNAPSHOT_PRESENT_CAPABILITIES) - set(known_capabilities))
    if unknown_present:
        raise ValueError("unknown capability names: %s" % ", ".join(unknown_present))
    present = sorted(_SNAPSHOT_PRESENT_CAPABILITIES)
    absent = sorted(set(known_capabilities) - set(present))
    not_expressible = sorted(
        name for name in absent if name.startswith("event.")
    )

    competition_id = id_resolver("competition", "nfl")
    season = report.get("season")
    season_id = id_resolver("season", season)
    report_team = report.get("team")
    filtered_team = report_team if report_team and report_team != "ALL" else None

    provider_ids = [
        _provider_id_evidence(
            competition_id,
            "competition",
            "nfl",
            "declared",
            "snapshot.competition.constant",
        ),
        _provider_id_evidence(
            season_id,
            "season",
            season,
            "declared",
            "report.season",
        ),
    ]
    body = {
        "schema_version": _SNAPSHOT_SCHEMA_VERSION,
        "observed_at": observed_at,
        "identity": {
            "status": "provider-scoped-surrogate",
            "canonical_identity": False,
        },
        "rights": dict(rights),
        "competition": {
            "id": competition_id,
            "name": "National Football League",
        },
        "season": {"id": season_id, "year": season},
        "scope": {
            "through_week": report.get("through_week"),
            "position": report.get("position"),
            "team": report_team,
            "lookback_weeks": report.get("lookback_weeks"),
            "sorted_by": report.get("sorted_by"),
        },
        "players": [],
        "provider_ids": provider_ids,
        "capabilities": {
            "present": present,
            "absent": absent,
            "not_expressible": not_expressible,
        },
        "provenance": {
            "provider": "nflverse",
            "adapter": {
                "name": "nflreadpy",
                "version": dependency_versions.get("nflreadpy"),
            },
            "method_version": report.get("method_version"),
            "dependencies": {
                name: dependency_versions.get(name)
                for name in ("nflreadpy", "polars")
                if _has_value(dependency_versions.get(name))
            },
            "source_refs": [
                {"kind": "dataset", "value": "nflverse-play-by-play"},
                {"kind": "library", "value": "nflreadpy"},
            ],
            "determinism": dict(getattr(id_resolver, "strategy", {})),
        },
    }

    if filtered_team:
        team_id = id_resolver("team", filtered_team)
        body["team"] = {"id": team_id, "abbreviation": filtered_team}
        provider_ids.append(
            _provider_id_evidence(
                team_id,
                "team",
                filtered_team,
                "provider-native",
                "report.team",
            )
        )

    seen_evidence = {
        (item["machina_id"], item["entity_type"], item["provider_id"])
        for item in provider_ids
        if item is not None
    }
    snapshot_rows = sorted(
        report.get("players") or [],
        key=lambda row: _snapshot_player_sort_key(row, report.get("sorted_by")),
    )
    for index, row in enumerate(snapshot_rows):
        player_provider_id = row.get("player_id")
        if not _has_value(player_provider_id):
            raise ValueError("player_id is required for every snapshot row")
        player_id = id_resolver("player", player_provider_id)
        team_provider_id = row.get("team")
        team_id = (
            id_resolver("team", team_provider_id)
            if _has_value(team_provider_id)
            else None
        )
        player = {
            "id": player_id,
            "name": row.get("player_display_name") or row.get("player_name"),
            "position": row.get("position"),
            "statistics": {
                curie: _official_statistic_string(source_key, row[source_key])
                for source_key, curie in _SNAPSHOT_STATISTICS.items()
                if _has_value(row.get(source_key))
            },
            "metrics": {
                metric: row[metric]
                for metric in _SNAPSHOT_METRICS
                if _has_value(row.get(metric))
            },
        }
        if team_id:
            player["team_id"] = team_id
        body["players"].append(
            {key: value for key, value in player.items() if _has_value(value)}
        )

        evidence_rows = [
            _provider_id_evidence(
                player_id,
                "player",
                player_provider_id,
                "provider-native",
                "report.players[%s].player_id" % index,
            ),
            _provider_id_evidence(
                team_id,
                "team",
                team_provider_id,
                "provider-native",
                "report.players[%s].team" % index,
            ),
        ]
        for evidence in evidence_rows:
            if evidence is None:
                continue
            identity = (
                evidence["machina_id"],
                evidence["entity_type"],
                evidence["provider_id"],
            )
            if identity not in seen_evidence:
                provider_ids.append(evidence)
                seen_evidence.add(identity)

    body["provider_ids"] = [item for item in provider_ids if item is not None]
    snapshot = {"machina_workload_snapshot": body}
    contract_errors = contract_findings_fn(snapshot)
    if contract_errors:
        raise ValueError("snapshot contract failed: %s" % "; ".join(contract_errors))
    return snapshot


# ---------------------------------------------------------------------------
# command: generate_workload_report
# ---------------------------------------------------------------------------

def generate_workload_report(request_data):
    ok, err = _ensure_deps()
    if not ok:
        return {"status": False, "message": "nfl-workload bootstrap failed: %s" % err}

    import nflreadpy
    import polars as pl

    params = dict(request_data.get("params") or {})

    window, err = _parse_window(params, "generate_workload_report")
    if err:
        return {"status": False, "message": err}

    position = params.get("position") or None
    team = params.get("team") or None

    try:
        min_opportunities = int(
            params.get("min_opportunities", _DEFAULT_MIN_OPPORTUNITIES)
        )
    except (TypeError, ValueError):
        min_opportunities = _DEFAULT_MIN_OPPORTUNITIES

    try:
        limit = int(params.get("limit", _DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = _DEFAULT_LIMIT

    try:
        pbp, positions, err = _load_frames(nflreadpy, window["season"])
        if err:
            return {"status": False, "message": err}

        payload = _build_report_payload(
            pl,
            pbp,
            positions,
            season=window["season"],
            through_week=window["through_week"],
            lookback_weeks=window["lookback_weeks"],
            position=position,
            team=team,
            min_opportunities=min_opportunities,
            limit=limit,
        )

        return {
            "status": True,
            "data": {
                "report": payload,
                "season": window["season"],
                "week": window["through_week"],
                "position": position or "ALL",
                "n_players": len(payload["players"]),
                # What actually computed these numbers, not what the pin asks
                # for. Stamped on every response so the loaded version is
                # observable rather than inferred from call latency.
                "deps": _loaded_versions(),
            },
        }
    except Exception as exc:
        return {
            "status": False,
            "message": "generate_workload_report failed: %s: %s"
            % (type(exc).__name__, exc),
        }


# ---------------------------------------------------------------------------
# command: generate_machina_workload_snapshot
# ---------------------------------------------------------------------------

def generate_machina_workload_snapshot(request_data):
    """Produce the additive aggregate contract without changing the native report."""
    params = dict(request_data.get("params") or {})
    try:
        observed_at = _validate_observed_at(params.get("observed_at"))
    except ValueError as exc:
        return {"status": False, "message": str(exc)}

    consumer_tier = str(params.get("consumer_tier") or "production").lower()

    # Runtime owns these decisions. Import and evaluate the canonical gate
    # before dependency bootstrap, provider imports or workload data access.
    try:
        from machina_sports_canonical.capabilities import ALL_CAPABILITIES
        from machina_sports_canonical.ids import surrogate_resolver
        from machina_sports_canonical.rights import rights_findings
    except ImportError:
        return {
            "status": False,
            "message": "machina_sports_canonical is required at runtime",
        }

    rights_probe = {
        "machina_sports_schema": {"rights": dict(_SNAPSHOT_RIGHTS)},
    }
    try:
        rights_errors = rights_findings(rights_probe, consumer_tier=consumer_tier)
    except Exception:
        return {
            "status": False,
            "message": "canonical rights gate failed closed",
        }
    if not isinstance(rights_errors, list):
        return {
            "status": False,
            "message": "canonical rights gate failed closed",
        }
    if rights_errors:
        return {
            "status": False,
            "message": "rights refusal: canonical policy does not permit this consumer tier",
            "data": {
                "allowed": False,
                "snapshot": None,
                "refusals": rights_errors[:1],
                "stage": "pre-retrieval",
            },
        }

    native = generate_workload_report(request_data)
    if not native.get("status"):
        return native
    data = native["data"]
    try:
        snapshot = _project_machina_workload_snapshot(
            data["report"],
            observed_at,
            data.get("deps") or {},
            id_resolver=surrogate_resolver("nflverse"),
            rights=dict(_SNAPSHOT_RIGHTS),
            capability_names=ALL_CAPABILITIES,
            contract_findings_fn=_snapshot_contract_findings,
        )
    except Exception as exc:
        return {
            "status": False,
            "message": "generate_machina_workload_snapshot failed: %s: %s"
            % (type(exc).__name__, exc),
        }

    report = data["report"]
    return {
        "status": True,
        "data": {
            "snapshot": snapshot,
            "season": data["season"],
            "week": data["week"],
            "position": data["position"],
            "team": report.get("team") or "ALL",
            "n_players": data["n_players"],
            "deps": data.get("deps") or {},
        },
    }


# ---------------------------------------------------------------------------
# command: get_player_workload
# ---------------------------------------------------------------------------

def get_player_workload(request_data):
    """One player's workload row out of the same report the leaderboard uses.

    Takes a single optional `team`, because it resolves a single name. A traded
    player holds one row per stint: with a team the answer is that stint or a
    scoped not_found, and without one it is the busiest stint, tie-broken on
    recency. Either way selected_team and other_stints say which was chosen.
    """
    ok, err = _ensure_deps()
    if not ok:
        return {"status": False, "message": "nfl-workload bootstrap failed: %s" % err}

    import nflreadpy
    import polars as pl

    params = dict(request_data.get("params") or {})

    player_name = str(params.get("player_name") or "").strip()
    if not player_name:
        return {
            "status": False,
            "message": "get_player_workload: 'player_name' is required",
        }

    # `week` is this command's parameter; `through_week` is accepted as an
    # alias so a caller can hand the same params to either command.
    week_key = "week"
    if params.get("week") is None and params.get("through_week") is not None:
        week_key = "through_week"

    window, err = _parse_window(params, "get_player_workload", week_key)
    if err:
        return {"status": False, "message": err}

    position = params.get("position") or None
    team = params.get("team") or None

    try:
        pbp, positions, err = _load_frames(nflreadpy, window["season"])
        if err:
            return {"status": False, "message": err}

        payload = _build_report_payload(
            pl,
            pbp,
            positions,
            season=window["season"],
            through_week=window["through_week"],
            lookback_weeks=window["lookback_weeks"],
            position=position,
            # Team scoping moved into _resolve_one, so the report deliberately
            # stays league-wide: filtering it here would hide the very stints
            # other_stints exists to report, and a team miss could not name
            # what the player actually holds.
            team=None,
            # Unfiltered: the floor and the cut rank a leaderboard, and would
            # otherwise report a real player as missing.
            min_opportunities=0,
            limit=0,
        )

        # A miss is a soft result, not a failure: see _resolve_one.
        return {
            "status": True,
            "data": dict(
                _resolve_one(
                    payload["players"],
                    player_name,
                    window["season"],
                    window["through_week"],
                    position,
                    team,
                ),
                deps=_loaded_versions(),
            ),
        }
    except Exception as exc:
        return {
            "status": False,
            "message": "get_player_workload failed: %s: %s"
            % (type(exc).__name__, exc),
        }


# ---------------------------------------------------------------------------
# command: get_player_pair_workload
# ---------------------------------------------------------------------------

def get_player_pair_workload(request_data):
    """Two players' workload rows off a single load of the season.

    Exists because the obvious way to compare two players - call
    get_player_workload twice - loads the play-by-play and recomputes every
    team's shares twice over, for one frame that would have served both names.
    The season load dominates the runtime, so the second call pays full price
    to learn nothing the first had not already computed.

    Same internals, no second copy of the logic: _load_frames ->
    _build_report_payload -> _resolve_one per name. Each player carries its own
    reason, so one name missing or ambiguous does not discard the one that
    matched - which is the whole point of resolving them together.

    TEAMS ARE PER PLAYER, NOT SHARED. Stint scoping is `player_a_team` and
    `player_b_team`, independent of one another and each optional: scope one
    player, both, or neither. This differs deliberately from
    get_player_workload, which resolves a single name and so takes a single
    `team`. Two players being compared are usually on two different rosters,
    which is the ordinary case rather than the exception, so one shared team
    would be wrong far more often than right.

    A `team` key is therefore rejected outright rather than applied to both or
    silently dropped. Applying it would answer about the wrong roster for one of
    the two, and ignoring it would discard scoping the caller asked for - both
    are the class of quiet wrongness the soft-miss and stint work exists to
    remove, so this fails closed with a message naming the right parameters.
    """
    ok, err = _ensure_deps()
    if not ok:
        return {"status": False, "message": "nfl-workload bootstrap failed: %s" % err}

    import nflreadpy
    import polars as pl

    params = dict(request_data.get("params") or {})

    player_a = str(params.get("player_a_name") or "").strip()
    player_b = str(params.get("player_b_name") or "").strip()
    absent = [
        key
        for key, value in (
            ("player_a_name", player_a),
            ("player_b_name", player_b),
        )
        if not value
    ]
    if absent:
        return {
            "status": False,
            "message": "get_player_pair_workload: %s %s required"
            % (" and ".join(absent), "is" if len(absent) == 1 else "are"),
        }

    # `week` is this command's parameter; `through_week` is accepted as an
    # alias so a caller can hand the same params to any workload command.
    week_key = "week"
    if params.get("week") is None and params.get("through_week") is not None:
        week_key = "through_week"

    window, err = _parse_window(params, "get_player_pair_workload", week_key)
    if err:
        return {"status": False, "message": err}

    position = params.get("position") or None

    # Per-player, independent, both optional. See the docstring: a single
    # shared `team` is refused rather than guessed at or quietly ignored.
    if params.get("team") is not None:
        return {
            "status": False,
            "message": "get_player_pair_workload: 'team' is not accepted because "
            "one team cannot scope two players - use 'player_a_team' and/or "
            "'player_b_team', which are independent and individually optional "
            "(get_player_workload takes 'team' because it resolves one name)",
        }
    team_a = params.get("player_a_team") or None
    team_b = params.get("player_b_team") or None

    try:
        pbp, positions, err = _load_frames(nflreadpy, window["season"])
        if err:
            return {"status": False, "message": err}

        # Built once, unfiltered, then read twice - the saving this command is
        # for. Same min_opportunities=0 / limit=0 reasoning as the single-
        # player command: a leaderboard's floor and cut would report a real
        # but low-usage player as missing.
        payload = _build_report_payload(
            pl,
            pbp,
            positions,
            season=window["season"],
            through_week=window["through_week"],
            lookback_weeks=window["lookback_weeks"],
            position=position,
            # League-wide for the same reason as the single-player command:
            # team scoping is _resolve_one's job now.
            team=None,
            min_opportunities=0,
            limit=0,
        )

        # Each name is resolved against its own team, so one player can be
        # scoped to a stint while the other is picked by the busiest-then-most-
        # recent rule. Each block records its own requested_team.
        blocks = {
            key: _resolve_one(
                payload["players"],
                name,
                window["season"],
                window["through_week"],
                position,
                stint_team,
            )
            for key, name, stint_team in (
                ("player_a", player_a, team_a),
                ("player_b", player_b, team_b),
            )
        }

        return {
            "status": True,
            "data": dict(
                blocks,
                season=window["season"],
                week=window["through_week"],
                position=position or "ALL",
                n_matched=sum(
                    1 for block in blocks.values() if block["reason"] == "matched"
                ),
                deps=_loaded_versions(),
            ),
        }
    except Exception as exc:
        return {
            "status": False,
            "message": "get_player_pair_workload failed: %s: %s"
            % (type(exc).__name__, exc),
        }


# ---------------------------------------------------------------------------
# command: get_player_context
# ---------------------------------------------------------------------------

def get_player_context(request_data):
    """Depth-chart role and injury status for one player on one team.

    The team is resolved before either per-player lookup, and the league-wide
    injury feed is narrowed to that team's block before any name is matched.
    Both sources are consulted; a hit on either is a success, and a miss on
    both is an error naming the team and the player rather than a payload of
    nulls the caller has to re-interpret.

    CURRENT STATE ONLY. There is no season or week parameter: ESPN's depth
    chart and injury endpoints serve present state and nothing else, so this
    returns what is true today no matter which week the caller is reasoning
    about. Only correct for live in-season use. A historical query gets
    today's roles and injuries stapled to a past week's workload, and any
    player who has since moved teams comes back not-found rather than with
    the role he actually held then. Both failures are silent - the payload
    looks the same as a legitimately healthy or legitimately absent player -
    so callers reasoning about past weeks must account for it themselves.
    """
    try:
        from sports_skills import nfl
    except ImportError as exc:
        return {
            "status": False,
            "message": "get_player_context requires sports-skills: %s" % exc,
        }

    # STOPGAP, see _apply_user_agent_stopgap above. Must run before the first
    # ESPN call or get_teams() 403s and nothing else executes.
    stopgap_note = _apply_user_agent_stopgap()

    params = dict(request_data.get("params") or {})
    team_query = str(params.get("team") or "").strip()
    player_name = str(params.get("player_name") or "").strip()

    if not team_query:
        return {
            "status": False,
            "message": "get_player_context: 'team' is required",
        }
    if not player_name:
        return {
            "status": False,
            "message": "get_player_context: 'player_name' is required",
        }

    # season/week are optional and only meaningful together: a season without
    # a week names no coordinate to check against. Supplying one is a bad
    # request rather than a soft miss, so it fails closed like any other.
    wants_check = params.get("season") is not None or params.get("week") is not None
    season_req = _opt_int(params.get("season"))
    week_req = _opt_int(params.get("week"))
    if wants_check and (season_req is None or week_req is None):
        return {
            "status": False,
            "message": "get_player_context: 'season' and 'week' must both be "
            "integers when either is supplied (got season=%r, week=%r)"
            % (params.get("season"), params.get("week")),
        }

    try:
        # Team first. Every lookup below is scoped by what this returns, and an
        # unresolvable team is a fault whatever week was asked for.
        team, err = _resolve_team(nfl, team_query)
        if err:
            return {"status": False, "message": err}

        # Temporal check before the per-player lookups: if this request is not
        # about the current week there is nothing worth fetching, because the
        # only thing behind these endpoints is current state.
        if wants_check:
            current, current_err = _current_fantasy_week(nfl)
            week_check = {
                "requested_season": season_req,
                "requested_week": week_req,
                "current_season": (current or {}).get("season"),
                "current_week": (current or {}).get("week"),
                "season_type": (current or {}).get("season_type"),
            }

            if current_err:
                # The coordinate could not be established, so this request
                # cannot be called current OR historical. Saying either would
                # assert something never observed.
                return {
                    "status": True,
                    "data": dict(
                        _context_envelope(
                            team, stopgap_note, None, None, week_check
                        ),
                        depth_chart_role=None,
                        injury_status=None,
                        matched_name=None,
                        query=player_name,
                        on_depth_chart=False,
                        injury_listed=False,
                        reason="unknown_week",
                        message="cannot tell whether season %s week %s is the "
                        "current week: %s" % (season_req, week_req, current_err),
                    ),
                }

            is_current = (
                current["is_regular_season"]
                and current["season"] == season_req
                and current["week"] == week_req
            )
            if not is_current:
                if current["is_regular_season"]:
                    why = "the current week is season %s week %s" % (
                        current["season"],
                        current["week"],
                    )
                else:
                    why = (
                        "there is no current fantasy week: ESPN reports season "
                        "%s type %s, and only type %s is the regular season"
                        % (
                            current["season"],
                            current["season_type"],
                            _ESPN_SEASON_TYPE_REGULAR,
                        )
                    )
                return {
                    "status": True,
                    "data": dict(
                        _context_envelope(
                            team, stopgap_note, None, None, week_check
                        ),
                        depth_chart_role=None,
                        injury_status=None,
                        matched_name=None,
                        query=player_name,
                        on_depth_chart=False,
                        injury_listed=False,
                        reason="historical",
                        message="season %s week %s is not the current week (%s); "
                        "get_player_context serves current ESPN depth-chart and "
                        "injury state only and cannot describe that week"
                        % (season_req, week_req, why),
                    ),
                }
        else:
            week_check = None

        depth_entries, depth_err = _depth_chart_entries(nfl, team)
        injuries, injury_err = _team_injuries(nfl, team)

        # Both upstreams failing is an outage, not a missing player. Reporting
        # "not found" here would assert an absence never actually observed.
        if depth_entries is None and injuries is None:
            return {
                "status": False,
                "message": "get_player_context: both sources failed for %s - "
                "depth chart: %s; injuries: %s"
                % (team.get("name"), depth_err, injury_err),
            }

        depth_match = _match_player(
            depth_entries or [],
            player_name,
            name_columns=["name"],
            id_key="id",
            rank=_shallowest,
        )
        # Injury rows carry no athlete id, so the name is the collapse key:
        # one player listed once must not read as ambiguous.
        injury_match = _match_player(
            injuries or [],
            player_name,
            name_columns=["name"],
            id_key="name",
        )

        for match, source in (
            (depth_match, "depth chart"),
            (injury_match, "injury report"),
        ):
            if match and "candidates" in match:
                # Soft: the team resolved and both feeds answered, so this is a
                # question about the name, not a fault. Returned as data with
                # the candidates attached so the caller can ask again.
                return {
                    "status": True,
                    "data": dict(
                        _context_envelope(
                            team, stopgap_note, depth_err, injury_err, week_check
                        ),
                        depth_chart_role=None,
                        injury_status=None,
                        matched_name=None,
                        query=player_name,
                        on_depth_chart=False,
                        injury_listed=False,
                        reason="ambiguous",
                        ambiguous_source=source,
                        candidates=match["candidates"],
                        message="ambiguous match for '%s' on the %s %s: matches "
                        "%s - provide a more specific name"
                        % (
                            player_name,
                            team.get("name"),
                            source,
                            ", ".join(match["candidates"]),
                        ),
                    ),
                }

        if depth_match is None and injury_match is None:
            # Soft: an observed absence from two feeds that did answer, which
            # is a fact about the roster worth reporting, not an error.
            return {
                "status": True,
                "data": dict(
                    _context_envelope(
                        team, stopgap_note, depth_err, injury_err, week_check
                    ),
                    depth_chart_role=None,
                    injury_status=None,
                    matched_name=None,
                    query=player_name,
                    on_depth_chart=False,
                    injury_listed=False,
                    reason="not_found",
                    message="no player matching '%s' on %s: absent from the "
                    "depth chart (%s entries) and the injury report (%s entries)"
                    % (
                        player_name,
                        team.get("name"),
                        len(depth_entries or []),
                        len(injuries or []),
                    ),
                ),
            }

        depth_row = depth_match["row"] if depth_match else None
        injury_row = injury_match["row"] if injury_match else None

        data = dict(
            _context_envelope(
                team, stopgap_note, depth_err, injury_err, week_check
            ),
            depth_chart_role=(
                {
                    "label": _depth_label(depth_row),
                    "position": depth_row.get("position"),
                    "position_name": depth_row.get("position_name"),
                    "depth": depth_row.get("depth"),
                    "unit": depth_row.get("unit"),
                }
                if depth_row
                else None
            ),
            injury_status=(
                {
                    "status": injury_row.get("status"),
                    "type": injury_row.get("type"),
                    "detail": injury_row.get("detail"),
                    "side": injury_row.get("side"),
                    "return_date": injury_row.get("return_date"),
                }
                if injury_row
                else None
            ),
            matched_name=(
                depth_match["name"] if depth_match else injury_match["name"]
            ),
            query=player_name,
            # A player absent from the injury feed is not an affirmatively
            # healthy one: coverage is partial rather than injured-only (see
            # _team_injuries), so absence means the feed does not cover him.
            # These flags say which source actually spoke, so a null above is
            # never read as a fact.
            on_depth_chart=depth_row is not None,
            injury_listed=injury_row is not None,
            reason="matched",
        )

        return {"status": True, "data": data}
    except Exception as exc:
        return {
            "status": False,
            "message": "get_player_context failed: %s: %s"
            % (type(exc).__name__, exc),
        }
