"""Bounded, deterministic API-Football event-roster normalization.

The workflow owns provider retrieval. This connector only validates a fixture
payload, plans the bounded calls, and merges provider responses without fuzzy
matching or invented player facts.
"""

from __future__ import annotations

from copy import deepcopy


MAX_PROFILE_REQUESTS = 20
REQUIRED_CAPABILITY = "event.lineups"


def _params(request_data):
    return dict((request_data or {}).get("params") or {})


def _result(status, message, **data):
    return {"status": status, "message": message, "data": data}


def _text(value):
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text or None


def _fixture_identity(payload):
    if not isinstance(payload, dict):
        return None, None, None, "payload must be an object"
    fixture = payload.get("fixture")
    teams = payload.get("teams")
    if not isinstance(fixture, dict) or not isinstance(teams, dict):
        return None, None, None, "payload must contain fixture and teams objects"
    fixture_id = _text(fixture.get("id"))
    home = teams.get("home")
    away = teams.get("away")
    home_id = _text(home.get("id")) if isinstance(home, dict) else None
    away_id = _text(away.get("id")) if isinstance(away, dict) else None
    if fixture_id is None or home_id is None or away_id is None:
        return None, None, None, "fixture.id and both teams.*.id values are required"
    if home_id == away_id:
        return None, None, None, "home and away team ids must differ"
    return fixture_id, home_id, away_id, None


def _bounded_limit(value):
    if value is None:
        return MAX_PROFILE_REQUESTS
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None
    if limit < 0 or limit > MAX_PROFILE_REQUESTS:
        return None
    return limit


def plan_event_roster(request_data):
    """Validate one fixture and return the identifiers used by the workflow."""
    params = _params(request_data)
    payload = params.get("payload")
    fixture_id, home_id, away_id, error = _fixture_identity(payload)
    if error:
        return _result(False, error, valid=False,
                       requirements_unavailable=[REQUIRED_CAPABILITY])

    profile_limit = _bounded_limit(params.get("max_profile_requests"))
    if profile_limit is None:
        return _result(
            False,
            "max_profile_requests must be between 0 and {0}".format(
                MAX_PROFILE_REQUESTS),
            valid=False,
            requirements_unavailable=[REQUIRED_CAPABILITY],
        )

    embedded = payload.get("lineups")
    if embedded is not None and not isinstance(embedded, list):
        return _result(False, "payload.lineups must be an array when present",
                       valid=False,
                       requirements_unavailable=[REQUIRED_CAPABILITY])

    return _result(
        True,
        "event roster request is valid",
        valid=True,
        fixture_id=payload["fixture"]["id"],
        home_team_id=payload["teams"]["home"]["id"],
        away_team_id=payload["teams"]["away"]["id"],
        embedded_lineups=bool(embedded),
        max_profile_requests=profile_limit,
        requirements_unavailable=[],
    )


def _squad_entries(response):
    return response if isinstance(response, list) else []


def _profile_index(responses):
    index = {}
    if not isinstance(responses, list):
        return index
    for response in responses:
        entries = response.get("response") if isinstance(response, dict) else None
        if not isinstance(entries, list):
            continue
        for entry in entries:
            player = entry.get("player") if isinstance(entry, dict) else None
            if not isinstance(player, dict):
                continue
            player_id = _text(player.get("id"))
            name = _text(player.get("name"))
            if player_id is not None and name is not None:
                index[player_id] = name
    return index


def plan_player_profiles(request_data):
    """Request profiles only for squad rows that have an id but no name."""
    params = _params(request_data)
    limit = _bounded_limit(params.get("max_profile_requests"))
    if limit is None:
        return _result(False, "invalid profile request limit", valid=False,
                       profile_requests=[])
    if params.get("include_player_profiles") is not True or limit == 0:
        return _result(True, "player profiles are disabled", valid=True,
                       profile_requests=[], truncated=False)

    missing = []
    seen = set()
    for response in (params.get("home_squad"), params.get("away_squad")):
        for squad in _squad_entries(response):
            players = squad.get("players") if isinstance(squad, dict) else None
            if not isinstance(players, list):
                continue
            for player in players:
                if not isinstance(player, dict) or _text(player.get("name")) is not None:
                    continue
                player_id = _text(player.get("id"))
                if player_id is not None and player_id not in seen:
                    seen.add(player_id)
                    missing.append({"id": player.get("id")})

    return _result(
        True,
        "player profile requests planned",
        valid=True,
        profile_requests=missing[:limit],
        truncated=len(missing) > limit,
    )


def _player_fields(player, *, profile_names):
    if not isinstance(player, dict):
        return None, "player row must be an object"
    player_id = _text(player.get("id"))
    name = _text(player.get("name"))
    if name is None and player_id is not None:
        name = profile_names.get(player_id)
    if player_id is None or name is None:
        return None, "every roster player requires provider id and name"
    normalized = {"id": player.get("id"), "name": name}
    number = player.get("number")
    if number is not None and _text(number) is not None:
        normalized["number"] = number
    position = player.get("pos")
    if position is None:
        position = player.get("position")
    if _text(position) is not None:
        normalized["pos"] = position
    return normalized, None


def _normalize_lineups(entries, expected_team_ids, profile_names):
    if not isinstance(entries, list) or not entries:
        return None, "fixture lineups are absent"
    normalized = []
    seen_teams = set()
    seen_players = set()
    for entry in entries:
        team = entry.get("team") if isinstance(entry, dict) else None
        team_id = _text(team.get("id")) if isinstance(team, dict) else None
        if team_id not in expected_team_ids or team_id in seen_teams:
            return None, "fixture lineups must contain each fixture team exactly once"
        normalized_entry = {"team": {"id": team.get("id")}}
        team_name = _text(team.get("name"))
        if team_name is not None:
            normalized_entry["team"]["name"] = team_name
        formation = _text(entry.get("formation"))
        if formation is not None:
            normalized_entry["formation"] = entry.get("formation")
        player_count = 0
        for source_key in ("startXI", "substitutes"):
            rows = entry.get(source_key)
            if not isinstance(rows, list):
                return None, "fixture lineup {0} must be an array".format(source_key)
            output_rows = []
            for row in rows:
                player = row.get("player") if isinstance(row, dict) else None
                normalized_player, error = _player_fields(
                    player, profile_names=profile_names)
                if error:
                    return None, error
                player_id = _text(normalized_player["id"])
                if player_id in seen_players:
                    return None, "a provider player id appears more than once"
                seen_players.add(player_id)
                output_rows.append({"player": normalized_player})
            normalized_entry[source_key] = output_rows
            player_count += len(output_rows)
        if player_count == 0:
            return None, "each fixture lineup must contain at least one player"
        seen_teams.add(team_id)
        normalized.append(normalized_entry)
    if seen_teams != expected_team_ids:
        return None, "fixture lineups are incomplete for this fixture"
    return normalized, None


def _normalize_squad(response, expected_team_id, fixture_team, profile_names):
    entries = _squad_entries(response)
    if len(entries) != 1 or not isinstance(entries[0], dict):
        return None, "each squad response must contain exactly one team"
    entry = entries[0]
    team = entry.get("team")
    team_id = _text(team.get("id")) if isinstance(team, dict) else None
    if team_id != expected_team_id:
        return None, "squad team id does not match the fixture team id"
    players = entry.get("players")
    if not isinstance(players, list) or not players:
        return None, "each squad must contain at least one player"

    normalized_team = {"id": team.get("id")}
    team_name = _text(team.get("name"))
    if team_name is None and isinstance(fixture_team, dict):
        team_name = _text(fixture_team.get("name"))
    if team_name is not None:
        normalized_team["name"] = team_name

    normalized_players = []
    seen = set()
    for player in players:
        normalized_player, error = _player_fields(
            player, profile_names=profile_names)
        if error:
            return None, error
        player_id = _text(normalized_player["id"])
        if player_id in seen:
            return None, "a squad contains a duplicate provider player id"
        seen.add(player_id)
        normalized_players.append({"player": normalized_player})
    return {"team": normalized_team, "players": normalized_players}, None


def _unavailable(payload, reason):
    return _result(
        True,
        "event roster unavailable: {0}".format(reason),
        valid=True,
        available=False,
        payload=deepcopy(payload) if isinstance(payload, dict) else {},
        roster_source=None,
        requirements_unavailable=[REQUIRED_CAPABILITY],
    )


def normalize_event_roster(request_data):
    """Merge exact provider roster facts into ``lineups`` or ``players``."""
    params = _params(request_data)
    payload = params.get("payload")
    fixture_id, home_id, away_id, error = _fixture_identity(payload)
    if error:
        return _result(False, error, valid=False, available=False,
                       requirements_unavailable=[REQUIRED_CAPABILITY])

    profile_names = _profile_index(params.get("player_profiles"))
    expected_team_ids = {home_id, away_id}
    embedded_lineups = payload.get("lineups")
    fetched_lineups = params.get("lineups")
    lineups = embedded_lineups if embedded_lineups else fetched_lineups
    enriched = deepcopy(payload)

    if lineups:
        normalized, reason = _normalize_lineups(
            lineups, expected_team_ids, profile_names)
        if normalized is None:
            return _unavailable(payload, reason)
        enriched["lineups"] = normalized
        enriched.pop("players", None)
        source = "fixture-lineups"
        endpoints = ["api-football/fixtures", "api-football/fixtures/lineups"]
    else:
        teams = payload["teams"]
        normalized = []
        for response, team_id, fixture_team in (
            (params.get("home_squad"), home_id, teams.get("home")),
            (params.get("away_squad"), away_id, teams.get("away")),
        ):
            squad, reason = _normalize_squad(
                response, team_id, fixture_team, profile_names)
            if squad is None:
                return _unavailable(payload, reason)
            normalized.append(squad)
        home_players = {
            _text(row["player"].get("id")) for row in normalized[0]["players"]
        }
        away_players = {
            _text(row["player"].get("id")) for row in normalized[1]["players"]
        }
        if home_players & away_players:
            return _unavailable(
                payload, "a provider player id appears in both fixture squads")
        enriched["players"] = normalized
        enriched.pop("lineups", None)
        source = "team-squads"
        endpoints = ["api-football/fixtures", "api-football/players/squads"]
        if profile_names:
            endpoints.append("api-football/players/profiles")

    enriched["_roster_provenance"] = {
        "provider": {"namespace": "api-football", "family": "licensed"},
        "fixture_id": payload["fixture"]["id"],
        "source": source,
        "endpoint_classes": endpoints,
        "profile_count": len(profile_names),
    }
    return _result(
        True,
        "event roster enriched from {0}".format(source),
        valid=True,
        available=True,
        payload=enriched,
        roster_source=source,
        requirements_unavailable=[],
    )
