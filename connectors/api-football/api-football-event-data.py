"""Validate and project exact API-Football event data into stable documents."""

from __future__ import annotations

from copy import deepcopy
import hashlib


PROVIDER = "api-football"
SCHEMA_VERSION = "api-football-event-projection/1"
DOCUMENT_SPECS = (
    ("events", "api-football-event-actions", "event-actions", "event.actions"),
    ("lineups", "api-football-event-lineups", "event-lineups", "event.lineups"),
    (
        "team_statistics",
        "api-football-event-team-statistics",
        "event-team-statistics",
        "event.team-statistics",
    ),
    (
        "player_statistics",
        "api-football-event-player-statistics",
        "event-player-statistics",
        "event.player-statistics",
    ),
    (
        "head_to_head",
        "api-football-event-head-to-head",
        "event-head-to-head",
        "event.head-to-head",
    ),
)


def _params(request_data):
    return dict((request_data or {}).get("params") or {})


def _text(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value)
    return text if text else None


def _urn(kind, *parts):
    material = "\x1f".join(str(part) for part in parts)
    digest = hashlib.blake2b(material.encode("utf-8"), digest_size=16).hexdigest()
    return "urn:machina:sports:{0}:{1}".format(kind, digest)


def _result(status, message, **data):
    return {"status": status, "message": message, "data": data}


def _fixture_identity(fixture, provider_fixture_id):
    if not isinstance(fixture, dict):
        return None, "fixture must be an object"
    fixture_data = fixture.get("fixture")
    teams = fixture.get("teams")
    if not isinstance(fixture_data, dict) or not isinstance(teams, dict):
        return None, "fixture must contain fixture and teams objects"
    home = teams.get("home")
    away = teams.get("away")
    fixture_id = _text(fixture_data.get("id"))
    home_id = _text(home.get("id")) if isinstance(home, dict) else None
    away_id = _text(away.get("id")) if isinstance(away, dict) else None
    if fixture_id is None or home_id is None or away_id is None:
        return None, "fixture.id and exact home/away team ids are required"
    if fixture_id != _text(provider_fixture_id):
        return None, "fixture.id must equal provider_fixture_id"
    if home_id == away_id:
        return None, "home and away team ids must differ"
    return {
        "fixture_id": fixture_id,
        "provider_fixture_id": fixture_data["id"],
        "home_id": home_id,
        "away_id": away_id,
        "home": home,
        "away": away,
    }, None


def _required_metadata(params):
    event_code = _text(params.get("event_code"))
    source_event_document_id = _text(params.get("source_event_document_id"))
    provider_fixture_id = _text(params.get("provider_fixture_id"))
    observed_at = _text(params.get("observed_at"))
    provider = params.get("provider")
    rights = params.get("rights")
    provenance = params.get("provenance")
    if not event_code or not source_event_document_id or not provider_fixture_id or not observed_at:
        return None, (
            "event_code, source_event_document_id, provider_fixture_id, and "
            "observed_at are required"
        )
    if not isinstance(rights, dict) or not rights or not isinstance(provenance, dict) or not provenance:
        return None, "rights and provenance must be non-empty objects"
    if not isinstance(provider, dict) or provider.get("namespace") != PROVIDER:
        return None, "provider must be an object with namespace api-football"
    return {
        "event_code": event_code,
        "source_event_document_id": source_event_document_id,
        "provider_fixture_id": provider_fixture_id,
        "observed_at": observed_at,
        "provider": provider,
        "rights": rights,
        "provenance": provenance,
    }, None


def _errors(value):
    if isinstance(value, dict):
        return ["{0}: {1}".format(key, item)[:500] for key, item in list(value.items())[:20]]
    if isinstance(value, list):
        return [str(item)[:500] for item in value[:20]]
    return [str(value)[:500]] if value else []


def _provider_response(envelope, fixture_id, *, h2h_pair=None):
    if not isinstance(envelope, dict):
        return None, "provider response must be an object"
    response = envelope.get("response")
    results = envelope.get("results")
    errors = _errors(envelope.get("errors"))
    if errors:
        return None, "provider errors: {0}".format("; ".join(errors))
    if not isinstance(response, list):
        return None, "provider response.response must be an array"
    if not isinstance(results, int) or isinstance(results, bool) or results != len(response):
        return None, "provider results must equal response length"
    parameters = envelope.get("parameters")
    if not isinstance(parameters, dict):
        return None, "provider response parameters must be an object"
    if h2h_pair is None:
        if _text(parameters.get("fixture")) != fixture_id:
            return None, "provider response fixture does not match fixture.id"
    elif _text(parameters.get("h2h")) != h2h_pair:
        return None, "head-to-head request does not match the exact fixture team pair"
    if not response:
        return [], "provider returned zero results"
    return response, None


def _team(row, identity):
    team = row.get("team") if isinstance(row, dict) else None
    team_id = _text(team.get("id")) if isinstance(team, dict) else None
    if team_id not in (identity["home_id"], identity["away_id"]):
        return None, None, "provider team id is not an exact fixture team"
    return team, team_id, None


def _player(player, team_id):
    if not isinstance(player, dict) or _text(player.get("id")) is None:
        return None, "provider player id is required"
    player_id = _urn("player", PROVIDER, team_id, player["id"])
    return {
        "@id": player_id,
        "player_id": player_id,
        "provider_player_id": player["id"],
        "name": player.get("name"),
    }, None


def _project_actions(rows, identity, event_id):
    facts = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("time"), dict):
            return None, "every action must contain a time object"
        elapsed = row["time"].get("elapsed")
        extra = row["time"].get("extra")
        if not isinstance(elapsed, int) or isinstance(elapsed, bool):
            return None, "every action requires an integer elapsed minute"
        team, team_id, error = _team(row, identity)
        if error:
            return None, error
        event_type = _text(row.get("type"))
        detail = _text(row.get("detail"))
        player = row.get("player")
        player_provider_id = player.get("id") if isinstance(player, dict) else None
        assist = row.get("assist")
        assist_provider_id = assist.get("id") if isinstance(assist, dict) else None
        if event_type is None or detail is None:
            return None, "every action requires type and detail"
        action_id = _urn(
            "action", PROVIDER, identity["fixture_id"], elapsed, extra,
            team_id, player_provider_id, event_type, detail,
        )
        if action_id in seen:
            continue
        seen.add(action_id)
        fact = {
            "@id": action_id,
            "type": "action",
            "event_id": event_id,
            "team_id": _urn("team", PROVIDER, team_id),
            "provider_team_id": team["id"],
            "provider_player_id": player_provider_id,
            "player_id": (
                _urn("player", PROVIDER, team_id, player_provider_id)
                if _text(player_provider_id) is not None else None
            ),
            "provider_assist_player_id": assist_provider_id,
            "assist_player_id": (
                _urn("player", PROVIDER, team_id, assist_provider_id)
                if _text(assist_provider_id) is not None else None
            ),
            "provider_facts": deepcopy(row),
        }
        facts.append(fact)
    return facts, None


def _lineup_players(rows, team_id):
    if not isinstance(rows, list):
        return None, "lineup player groups must be arrays"
    players = []
    seen = set()
    for row in rows:
        player = row.get("player") if isinstance(row, dict) else None
        normalized, error = _player(player, team_id)
        if error:
            return None, error
        if normalized["@id"] in seen:
            return None, "lineup contains a duplicate provider player id"
        seen.add(normalized["@id"])
        normalized["number"] = player.get("number")
        normalized["position"] = player.get("pos")
        normalized["grid"] = player.get("grid")
        players.append(normalized)
    return players, None


def _project_lineups(rows, identity, event_id):
    if len(rows) != 2:
        return None, "lineups must contain both fixture teams exactly once"
    facts = []
    seen = set()
    for row in rows:
        team, team_id, error = _team(row, identity)
        if error or team_id in seen:
            return None, error or "lineups must contain each fixture team exactly once"
        starting, error = _lineup_players(row.get("startXI"), team_id)
        if error:
            return None, error
        substitutes, error = _lineup_players(row.get("substitutes"), team_id)
        if error:
            return None, error
        seen.add(team_id)
        facts.append({
            "@id": _urn("lineup", PROVIDER, identity["fixture_id"], team_id),
            "event_id": event_id,
            "team_id": _urn("team", PROVIDER, team_id),
            "provider_team_id": team["id"],
            "formation": row.get("formation"),
            "coach": deepcopy(row.get("coach")),
            "starting": starting,
            "substitutes": substitutes,
        })
    if seen != {identity["home_id"], identity["away_id"]}:
        return None, "lineups must contain the exact fixture teams"
    return facts, None


def _project_team_statistics(rows, identity, event_id):
    if len(rows) != 2:
        return None, "team statistics must contain both fixture teams"
    facts = []
    seen = set()
    for row in rows:
        team, team_id, error = _team(row, identity)
        statistics = row.get("statistics") if isinstance(row, dict) else None
        if error or team_id in seen or not isinstance(statistics, list):
            return None, error or "team statistics shape or team identity is invalid"
        seen.add(team_id)
        facts.append({
            "@id": _urn("team-statistics", PROVIDER, identity["fixture_id"], team_id),
            "event_id": event_id,
            "team_id": _urn("team", PROVIDER, team_id),
            "provider_team_id": team["id"],
            "statistics": deepcopy(statistics),
        })
    return facts, None


def _project_player_statistics(rows, identity, event_id):
    if len(rows) != 2:
        return None, "player statistics must contain both fixture teams"
    facts = []
    seen_teams = set()
    seen_players = set()
    for row in rows:
        team, team_id, error = _team(row, identity)
        players = row.get("players") if isinstance(row, dict) else None
        if error or team_id in seen_teams or not isinstance(players, list):
            return None, error or "player statistics shape or team identity is invalid"
        projected_players = []
        for item in players:
            player = item.get("player") if isinstance(item, dict) else None
            statistics = item.get("statistics") if isinstance(item, dict) else None
            normalized, error = _player(player, team_id)
            if error or not isinstance(statistics, list):
                return None, error or "player statistics must be an array"
            if normalized["@id"] in seen_players:
                return None, "provider player id appears more than once"
            seen_players.add(normalized["@id"])
            normalized["statistics"] = deepcopy(statistics)
            projected_players.append(normalized)
        seen_teams.add(team_id)
        facts.append({
            "@id": _urn("player-statistics", PROVIDER, identity["fixture_id"], team_id),
            "event_id": event_id,
            "team_id": _urn("team", PROVIDER, team_id),
            "provider_team_id": team["id"],
            "players": projected_players,
        })
    return facts, None


def _project_head_to_head(rows, identity, event_id):
    expected = {identity["home_id"], identity["away_id"]}
    facts = []
    for row in rows:
        fixture = row.get("fixture") if isinstance(row, dict) else None
        teams = row.get("teams") if isinstance(row, dict) else None
        home = teams.get("home") if isinstance(teams, dict) else None
        away = teams.get("away") if isinstance(teams, dict) else None
        fixture_id = _text(fixture.get("id")) if isinstance(fixture, dict) else None
        home_id = _text(home.get("id")) if isinstance(home, dict) else None
        away_id = _text(away.get("id")) if isinstance(away, dict) else None
        if fixture_id is None or {home_id, away_id} != expected:
            return None, "head-to-head result is outside the exact fixture team pair"
        facts.append({
            "@id": _urn("event", PROVIDER, fixture_id),
            "event_id": event_id,
            "provider_fixture_id": fixture["id"],
            "home_team_id": _urn("team", PROVIDER, home_id),
            "away_team_id": _urn("team", PROVIDER, away_id),
            "provider_home_team_id": home["id"],
            "provider_away_team_id": away["id"],
            "facts": deepcopy(row),
        })
    return facts, None


PROJECTORS = {
    "events": _project_actions,
    "lineups": _project_lineups,
    "team_statistics": _project_team_statistics,
    "player_statistics": _project_player_statistics,
    "head_to_head": _project_head_to_head,
}


def _document(spec, facts, reason, identity, metadata, event_id):
    _, name, kind, capability_name = spec
    status = "available" if facts else "unavailable"
    projection_key = _urn("projection", PROVIDER, identity["fixture_id"], kind)
    capability = {"name": capability_name, "status": status}
    value = {
        "@id": projection_key,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "event_id": event_id,
        "event_code": metadata["event_code"],
        "source_event_document_id": metadata["source_event_document_id"],
        "provider_fixture_id": identity["provider_fixture_id"],
        "facts": facts or [],
    }
    if status == "unavailable":
        value["unavailable_reason"] = reason or "provider returned no facts"
    return {
        "name": name,
        "key": projection_key,
        "metadata": {
            "event_code": metadata["event_code"],
            "source_event_document_id": metadata["source_event_document_id"],
            "provider_fixture_id": identity["provider_fixture_id"],
            "provider": deepcopy(metadata["provider"]),
            "rights": deepcopy(metadata["rights"]),
            "provenance": deepcopy(metadata["provenance"]),
            "capability": capability,
            "status": status,
            "observed_at": metadata["observed_at"],
            "projection_key": projection_key,
        },
        "value": value,
    }


def project_event_data(request_data):
    """Project one exact fixture and five endpoint envelopes without inference."""
    params = _params(request_data)
    metadata, error = _required_metadata(params)
    if error:
        return _result(False, error, valid=False, documents=[])
    identity, error = _fixture_identity(
        params.get("fixture"), metadata["provider_fixture_id"]
    )
    if error:
        return _result(False, error, valid=False, documents=[])

    event_id = metadata["event_code"]
    documents = []
    unavailable = []
    diagnostics = {}
    h2h_pair = "{0}-{1}".format(identity["home_id"], identity["away_id"])
    for spec in DOCUMENT_SPECS:
        source_key, _, _, capability_name = spec
        rows, reason = _provider_response(
            params.get(source_key),
            identity["fixture_id"],
            h2h_pair=h2h_pair if source_key == "head_to_head" else None,
        )
        facts = None
        if rows:
            facts, shape_error = PROJECTORS[source_key](rows, identity, event_id)
            reason = shape_error or reason
        if facts is None:
            facts = []
        if not facts:
            unavailable.append(capability_name)
            diagnostics[capability_name] = reason or "provider returned no facts"
        documents.append(_document(spec, facts, reason, identity, metadata, event_id))

    if not unavailable:
        workflow_status = "executed"
    elif len(unavailable) == len(DOCUMENT_SPECS):
        workflow_status = "unavailable"
    else:
        workflow_status = "partial"
    return _result(
        True,
        "event data projected",
        valid=True,
        workflow_status=workflow_status,
        event_id=event_id,
        documents=documents,
        requirements_unavailable=unavailable,
        diagnostics=diagnostics,
    )
