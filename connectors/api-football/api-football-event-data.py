"""Validate and project exact API-Football event data into stable documents."""

from __future__ import annotations

from copy import deepcopy
import hashlib


PROVIDER = "api-football"
SCHEMA_VERSION = "api-football-event-projection/2"
DOCUMENT_SPECS = (
    (
        "events",
        "api-football-event-actions",
        "event-actions",
        "internal.api-football.event-actions",
        "api-football/fixtures/events",
    ),
    (
        "lineups",
        "api-football-event-lineups",
        "event-lineups",
        "internal.api-football.event-lineups",
        "api-football/fixtures/lineups",
    ),
    (
        "team_statistics",
        "api-football-event-team-statistics",
        "event-team-statistics",
        "internal.api-football.event-team-statistics",
        "api-football/fixtures/statistics",
    ),
    (
        "player_statistics",
        "api-football-event-player-statistics",
        "event-player-statistics",
        "internal.api-football.event-player-statistics",
        "api-football/fixtures/players",
    ),
    (
        "head_to_head",
        "api-football-event-head-to-head",
        "event-head-to-head",
        "internal.api-football.event-head-to-head",
        "api-football/fixtures/headtohead",
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


def resolve_provider_fixture_id(request_data):
    """Resolve one API-Football fixture ID from a canonical event document."""
    params = _params(request_data)
    event_value = params.get("event_document_value")
    if not isinstance(event_value, dict):
        return _result(False, "event_document_value must be an object")

    canonical = event_value.get("machina_sports_schema")
    if not isinstance(canonical, dict):
        return _result(False, "canonical machina_sports_schema is required")
    event_view = canonical.get("event_view")
    event_id = _text(event_view.get("event_id")) if isinstance(event_view, dict) else None
    if not event_id:
        return _result(False, "canonical event_view.event_id is required")

    provider_ids = canonical.get("provider_ids")
    if not isinstance(provider_ids, list):
        return _result(False, "canonical provider_ids crosswalk must be an array")
    candidates = [
        entry
        for entry in provider_ids
        if isinstance(entry, dict)
        and entry.get("provider_namespace") == PROVIDER
        and entry.get("entity_type") == "event"
    ]
    if len(candidates) != 1:
        return _result(
            False,
            "canonical event must have exactly one api-football provider id",
        )

    candidate = candidates[0]
    if _text(candidate.get("machina_id")) != event_id:
        return _result(
            False,
            "api-football provider id must map to canonical event_view.event_id",
        )
    provider_fixture_id = _text(candidate.get("provider_id"))
    if not provider_fixture_id:
        return _result(False, "api-football event provider_id is required")
    return _result(
        True,
        "API-Football fixture id resolved from canonical event crosswalk",
        provider_fixture_id=provider_fixture_id,
    )


def _required_context(params):
    source_event_document_id = _text(params.get("source_event_document_id"))
    provider_fixture_id = _text(params.get("provider_fixture_id"))
    event_view = params.get("event_view")
    provider_ids = params.get("provider_ids")
    rights = params.get("source_event_rights")
    provenance = params.get("source_event_provenance")
    observed_at = params.get("endpoint_observed_at")
    request_contexts = params.get("request_contexts")
    if not source_event_document_id or not provider_fixture_id:
        return None, "source_event_document_id and provider_fixture_id are required"
    if not isinstance(event_view, dict) or not _text(event_view.get("event_id")):
        return None, "canonical event_view.event_id is required"
    if not isinstance(event_view.get("participants"), list):
        return None, "canonical event_view.participants must be an array"
    if not isinstance(provider_ids, list):
        return None, "canonical provider_ids crosswalk must be an array"
    if not isinstance(rights, dict) or not rights:
        return None, "source_event_rights must be a non-empty object"
    if not isinstance(provenance, dict) or not provenance:
        return None, "source_event_provenance must be a non-empty object"
    provider = provenance.get("provider")
    if not isinstance(provider, dict) or provider.get("namespace") != PROVIDER:
        return None, "source event provider namespace must be api-football"
    if not isinstance(observed_at, dict) or not isinstance(request_contexts, dict):
        return None, "endpoint_observed_at and request_contexts must be objects"
    if not isinstance(request_contexts.get("fixture"), dict):
        return None, "request context is required for endpoint fixture"
    for source_key, _, _, _, _ in DOCUMENT_SPECS:
        if not _text(observed_at.get(source_key)):
            return None, "observed_at is required for endpoint {0}".format(source_key)
        if not isinstance(request_contexts.get(source_key), dict):
            return None, "request context is required for endpoint {0}".format(source_key)
    return {
        "event_code": _text(event_view["event_id"]),
        "event_view": event_view,
        "provider_ids": provider_ids,
        "source_event_document_id": source_event_document_id,
        "provider_fixture_id": provider_fixture_id,
        "provider": provider,
        "rights": rights,
        "provenance": provenance,
        "endpoint_observed_at": observed_at,
        "request_contexts": request_contexts,
    }, None


def _crosswalk_index(entries):
    index = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        namespace = entry.get("provider_namespace")
        entity_type = entry.get("entity_type")
        provider_id = _text(entry.get("provider_id"))
        machina_id = _text(entry.get("machina_id"))
        if namespace != PROVIDER or not entity_type or not provider_id or not machina_id:
            continue
        key = (entity_type, provider_id)
        if key in index and index[key] != machina_id:
            return None, "provider crosswalk maps one identifier to multiple canonical ids"
        index[key] = machina_id
    return index, None


def _fixture_identity(fixture, context):
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
    if fixture_id != context["provider_fixture_id"]:
        return None, "fixture.id must equal provider_fixture_id"
    if home_id == away_id:
        return None, "home and away team ids must differ"

    crosswalk, error = _crosswalk_index(context["provider_ids"])
    if error:
        return None, error
    event_code = context["event_code"]
    if crosswalk.get(("event", fixture_id)) != event_code:
        return None, "provider event id must map to the source canonical event_code"

    participants = context["event_view"]["participants"]
    by_role = {
        participant.get("role"): _text(participant.get("id"))
        for participant in participants
        if isinstance(participant, dict)
        and participant.get("role") in ("home", "away")
        and _text(participant.get("id"))
    }
    if len(by_role) != 2:
        return None, "event_view must select one canonical home and away participant"
    canonical_home = crosswalk.get(("team", home_id))
    canonical_away = crosswalk.get(("team", away_id))
    if canonical_home != by_role["home"] or canonical_away != by_role["away"]:
        return None, "provider team ids must map exactly to selected event_view participants"

    player_ids = {
        provider_id: machina_id
        for (entity_type, provider_id), machina_id in crosswalk.items()
        if entity_type in ("athlete", "player")
    }
    return {
        "fixture_id": fixture_id,
        "provider_fixture_id": fixture_data["id"],
        "home_id": home_id,
        "away_id": away_id,
        "home": home,
        "away": away,
        "team_ids": {home_id: canonical_home, away_id: canonical_away},
        "player_ids": player_ids,
    }, None


def _errors(value):
    if isinstance(value, dict):
        return ["{0}: {1}".format(key, item)[:500] for key, item in list(value.items())[:20]]
    if isinstance(value, list):
        return [str(item)[:500] for item in value[:20]]
    return [str(value)[:500]] if value else []


def _request_matches(request_context, expected):
    if not isinstance(request_context, dict):
        return False
    return all(_text(request_context.get(key)) == _text(value) for key, value in expected.items())


def _provider_response(envelope, request_context, expected):
    if not isinstance(envelope, dict):
        return None, "provider response must be an object"
    if not _request_matches(request_context, expected):
        return None, "request context does not match the selected event"
    if "parameters" in envelope:
        parameters = envelope["parameters"]
        if not isinstance(parameters, dict) or not _request_matches(parameters, expected):
            return None, "provider response parameters do not match request context"
    if "errors" not in envelope or not isinstance(envelope["errors"], (dict, list)):
        return None, "provider response errors must be an array or object"
    errors = _errors(envelope.get("errors"))
    if errors:
        return None, "provider errors: {0}".format("; ".join(errors))
    response = envelope.get("response")
    results = envelope.get("results")
    if not isinstance(response, list):
        return None, "provider response.response must be an array"
    if not isinstance(results, int) or isinstance(results, bool) or results != len(response):
        return None, "provider results must equal response length"
    if not response:
        return [], "provider returned zero results"
    return response, None


def _team(row, identity):
    team = row.get("team") if isinstance(row, dict) else None
    team_id = _text(team.get("id")) if isinstance(team, dict) else None
    canonical_team_id = identity["team_ids"].get(team_id)
    if canonical_team_id is None:
        return None, None, None, "provider team id is not an exact fixture team"
    return team, team_id, canonical_team_id, None


def _player(player, canonical_team_id, event_id, canonical_player_ids):
    if not isinstance(player, dict) or _text(player.get("id")) is None:
        return None, "provider player id is required"
    provider_player_id = _text(player["id"])
    normalized = {
        "@id": _urn(
            "participation", event_id, canonical_team_id, provider_player_id
        ),
        "participation_id": _urn(
            "participation", event_id, canonical_team_id, provider_player_id
        ),
        "identity_scope": "event-participation",
        "provider_player_id": player["id"],
        "name": player.get("name"),
    }
    # This runtime has no canonical person-resolution command. Only an athlete ID
    # already supplied by the canonical source crosswalk may be carried forward.
    canonical_player_id = canonical_player_ids.get(provider_player_id)
    if canonical_player_id is not None:
        normalized["canonical_athlete_id"] = canonical_player_id
    return normalized, None


def _player_reference(provider_player_id, canonical_team_id, event_id, canonical_player_ids):
    provider_id = _text(provider_player_id)
    if provider_id is None:
        return {}
    fields = {
        "provider_player_id": provider_player_id,
        "participation_id": _urn(
            "participation", event_id, canonical_team_id, provider_id
        ),
    }
    canonical_player_id = canonical_player_ids.get(provider_id)
    if canonical_player_id is not None:
        fields["canonical_athlete_id"] = canonical_player_id
    return fields


def _project_actions(rows, identity, event_id):
    facts = []
    seen = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("time"), dict):
            return None, "every action must contain a time object"
        elapsed = row["time"].get("elapsed")
        if not isinstance(elapsed, int) or isinstance(elapsed, bool):
            return None, "every action requires an integer elapsed minute"
        team, _, canonical_team_id, error = _team(row, identity)
        if error:
            return None, error
        provider_event_id = _text(row.get("id"))
        action_id = (
            _urn("action", PROVIDER, "provider-event", provider_event_id)
            if provider_event_id is not None
            else _urn("action", event_id, ordinal)
        )
        if action_id in seen:
            return None, "provider event id appears more than once"
        seen.add(action_id)
        player = row.get("player")
        assist = row.get("assist")
        player_provider_id = player.get("id") if isinstance(player, dict) else None
        assist_provider_id = assist.get("id") if isinstance(assist, dict) else None
        fact = {
            "@id": action_id,
            "type": "action",
            "event_id": event_id,
            "team_id": canonical_team_id,
            "provider_team_id": team["id"],
            "provider_response_ordinal": ordinal,
            "provider_facts": deepcopy(row),
        }
        if provider_event_id is not None:
            fact["provider_event_id"] = row["id"]
        fact.update(
            _player_reference(
                player_provider_id,
                canonical_team_id,
                event_id,
                identity["player_ids"],
            )
        )
        assist_fields = _player_reference(
            assist_provider_id,
            canonical_team_id,
            event_id,
            identity["player_ids"],
        )
        if assist_fields:
            fact["provider_assist_player_id"] = assist_fields["provider_player_id"]
            fact["assist_participation_id"] = assist_fields["participation_id"]
            if "canonical_athlete_id" in assist_fields:
                fact["canonical_assist_athlete_id"] = assist_fields[
                    "canonical_athlete_id"
                ]
        facts.append(fact)
    return facts, None


def _lineup_players(rows, canonical_team_id, event_id, canonical_player_ids):
    if not isinstance(rows, list):
        return None, "lineup player groups must be arrays"
    players = []
    seen = set()
    for row in rows:
        player = row.get("player") if isinstance(row, dict) else None
        normalized, error = _player(
            player, canonical_team_id, event_id, canonical_player_ids
        )
        if error:
            return None, error
        if normalized["participation_id"] in seen:
            return None, "lineup contains a duplicate provider player id"
        seen.add(normalized["participation_id"])
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
        team, team_id, canonical_team_id, error = _team(row, identity)
        if error or team_id in seen:
            return None, error or "lineups must contain each fixture team exactly once"
        starting, error = _lineup_players(
            row.get("startXI"), canonical_team_id, event_id, identity["player_ids"]
        )
        if error:
            return None, error
        substitutes, error = _lineup_players(
            row.get("substitutes"),
            canonical_team_id,
            event_id,
            identity["player_ids"],
        )
        if error:
            return None, error
        seen.add(team_id)
        facts.append({
            "@id": _urn("lineup", event_id, canonical_team_id),
            "event_id": event_id,
            "team_id": canonical_team_id,
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
        team, team_id, canonical_team_id, error = _team(row, identity)
        statistics = row.get("statistics") if isinstance(row, dict) else None
        if error or team_id in seen or not isinstance(statistics, list):
            return None, error or "team statistics shape or team identity is invalid"
        seen.add(team_id)
        facts.append({
            "@id": _urn("team-statistics", event_id, canonical_team_id),
            "event_id": event_id,
            "team_id": canonical_team_id,
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
        team, team_id, canonical_team_id, error = _team(row, identity)
        players = row.get("players") if isinstance(row, dict) else None
        if error or team_id in seen_teams or not isinstance(players, list):
            return None, error or "player statistics shape or team identity is invalid"
        projected_players = []
        for item in players:
            player = item.get("player") if isinstance(item, dict) else None
            statistics = item.get("statistics") if isinstance(item, dict) else None
            normalized, error = _player(
                player, canonical_team_id, event_id, identity["player_ids"]
            )
            if error or not isinstance(statistics, list):
                return None, error or "player statistics must be an array"
            if normalized["participation_id"] in seen_players:
                return None, "provider player participation appears more than once"
            seen_players.add(normalized["participation_id"])
            normalized["statistics"] = deepcopy(statistics)
            projected_players.append(normalized)
        seen_teams.add(team_id)
        facts.append({
            "@id": _urn("player-statistics", event_id, canonical_team_id),
            "event_id": event_id,
            "team_id": canonical_team_id,
            "provider_team_id": team["id"],
            "players": projected_players,
        })
    return facts, None


def _project_head_to_head(rows, identity, event_id):
    expected = {identity["home_id"], identity["away_id"]}
    facts = []
    for ordinal, row in enumerate(rows):
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
            "@id": _urn("head-to-head-observation", event_id, ordinal, fixture_id),
            "event_id": event_id,
            "provider_fixture_id": fixture["id"],
            "home_team_id": identity["team_ids"][home_id],
            "away_team_id": identity["team_ids"][away_id],
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


def _document(spec, facts, reason, envelope, request_context, identity, context):
    source_key, name, kind, capability_name, endpoint = spec
    status = "available" if facts else "unavailable"
    event_code = context["event_code"]
    source_event_document_id = context["source_event_document_id"]
    projection_key = _urn(
        "projection", name, source_event_document_id, event_code
    )
    source_event_ref = {
        "kind": "source-event-document",
        "value": source_event_document_id,
    }
    provenance = {
        "provider": deepcopy(context["provider"]),
        "observed_at": context["endpoint_observed_at"][source_key],
        "source_refs": [
            {"kind": "endpoint-class", "value": endpoint},
            source_event_ref,
        ],
    }
    rights = {
        "terms": deepcopy(context["rights"]),
        "source_event_rights_ref": {
            **source_event_ref,
            "path": "value.machina_sports_schema.rights",
        },
    }
    value = {
        "@id": projection_key,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "event_id": event_code,
        "event_code": event_code,
        "source_event_document_id": source_event_document_id,
        "provider_fixture_id": identity["provider_fixture_id"],
        "request_context": deepcopy(request_context),
        "provider_envelope": deepcopy(envelope),
        "facts": facts or [],
    }
    if status == "unavailable":
        value["unavailable_reason"] = reason or "provider returned no facts"
    return {
        "_id": projection_key,
        "name": name,
        "key": projection_key,
        "metadata": {
            "event_code": event_code,
            "source_event_document_id": source_event_document_id,
            "provider_fixture_id": identity["provider_fixture_id"],
            "provider": deepcopy(context["provider"]),
            "rights": rights,
            "provenance": provenance,
            "projection_capability": {"name": capability_name, "status": status},
            "status": status,
            "observed_at": context["endpoint_observed_at"][source_key],
            "projection_key": projection_key,
        },
        "value": value,
    }


def project_event_data(request_data):
    """Project one canonical event and exact provider endpoint envelopes."""
    params = _params(request_data)
    context, error = _required_context(params)
    if error:
        return _result(False, error, valid=False, documents=[])

    fixture_request = {"id": context["provider_fixture_id"]}
    fixture_rows, error = _provider_response(
        params.get("fixture_envelope"),
        context["request_contexts"]["fixture"],
        fixture_request,
    )
    if error or not fixture_rows or len(fixture_rows) != 1:
        return _result(
            False,
            error or "fixture endpoint must return exactly one fixture",
            valid=False,
            documents=[],
        )
    identity, error = _fixture_identity(fixture_rows[0], context)
    if error:
        return _result(False, error, valid=False, documents=[])

    event_id = context["event_code"]
    documents = []
    unavailable = []
    diagnostics = {}
    h2h_pair = "{0}-{1}".format(identity["home_id"], identity["away_id"])
    for spec in DOCUMENT_SPECS:
        source_key, _, _, capability_name, _ = spec
        envelope = params.get(source_key)
        request_context = context["request_contexts"][source_key]
        expected = (
            {"h2h": h2h_pair, "last": 5}
            if source_key == "head_to_head"
            else {"fixture": identity["fixture_id"]}
        )
        rows, reason = _provider_response(envelope, request_context, expected)
        facts = None
        if rows:
            facts, shape_error = PROJECTORS[source_key](rows, identity, event_id)
            reason = shape_error or reason
        if facts is None:
            facts = []
        if not facts:
            unavailable.append(capability_name)
            diagnostics[capability_name] = reason or "provider returned no facts"
        documents.append(
            _document(
                spec,
                facts,
                reason,
                envelope,
                request_context,
                identity,
                context,
            )
        )

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
