"""Focused contract tests for bounded API-Football roster enrichment."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = CONNECTOR_ROOT / "api-football-roster.py"
SPEC = importlib.util.spec_from_file_location("api_football_roster", MODULE_PATH)
roster = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(roster)


def fixture_payload():
    return {
        "fixture": {"id": 7001, "status": {"short": "NS"}},
        "league": {"id": 39, "name": "Premier League", "season": 2026},
        "teams": {
            "home": {"id": 40, "name": "Home FC"},
            "away": {"id": 47, "name": "Away FC"},
        },
        "goals": {"home": None, "away": None},
    }


def invoke(command, **params):
    return command({"params": params})


def squad(team_id, team_name, players):
    return [{"team": {"id": team_id, "name": team_name}, "players": players}]


def test_no_roster_returns_an_explicit_unavailable_requirement():
    payload = fixture_payload()

    result = invoke(roster.normalize_event_roster, payload=payload)

    assert result["status"] is True
    assert result["data"] == {
        "valid": True,
        "available": False,
        "payload": payload,
        "roster_source": None,
        "requirements_unavailable": ["event.rosters"],
        "metadata": result["metadata"],
    }
    assert result["data"]["payload"] is not payload
    assert result["metadata"]["source_refs"] == [
        {"kind": "endpoint-class", "value": "api-football/fixtures"},
        {"kind": "endpoint-class", "value": "api-football/players/squads"},
    ]
    assert result["metadata"]["roster"] == {
        "available": False,
        "fixture_id": 7001,
        "source": None,
        "team_count": 0,
        "player_count": 0,
        "profile_count": 0,
        "unavailable_reason": "each squad response must contain exactly one team",
    }


def test_squad_fallback_adds_distinct_exact_rosters_to_the_raw_fixture():
    payload = fixture_payload()
    home = squad(40, "Home FC", [
        {"id": 101, "name": "A. Keeper", "number": 1,
         "position": "Goalkeeper", "age": 28, "photo": "ignored"},
        {"id": 102, "name": "D. Back", "number": None,
         "position": "Defender"},
    ])
    away = squad(47, "Away FC", [
        {"id": 201, "name": "F. Striker", "number": 9,
         "position": "Attacker"},
    ])

    result = invoke(
        roster.normalize_event_roster,
        payload=payload,
        lineups=[],
        home_squad=home,
        away_squad=away,
        player_profiles=[],
    )

    assert result["status"] is True
    assert result["data"]["available"] is True
    assert result["data"]["roster_source"] == "team-squads"
    assert result["data"]["requirements_unavailable"] == []
    enriched = result["data"]["payload"]
    assert {key: enriched[key] for key in payload} == payload
    assert "lineups" not in enriched
    assert "players" not in enriched
    assert "_roster_provenance" not in enriched
    assert enriched["rosters"] == [
        {
            "team": {"id": 40, "name": "Home FC"},
            "players": [
                {"id": 101, "name": "A. Keeper", "position": "Goalkeeper",
                 "number": 1},
                {"id": 102, "name": "D. Back", "position": "Defender",
                 "number": None},
            ],
        },
        {
            "team": {"id": 47, "name": "Away FC"},
            "players": [
                {"id": 201, "name": "F. Striker", "position": "Attacker",
                 "number": 9},
            ],
        },
    ]
    assert result["metadata"] == {
        "provider": {"namespace": "api-football", "family": "licensed"},
        "source_refs": [
            {"kind": "endpoint-class", "value": "api-football/fixtures"},
            {"kind": "endpoint-class", "value": "api-football/players/squads"},
        ],
        "roster": {
            "available": True,
            "fixture_id": 7001,
            "source": "team-squads",
            "team_count": 2,
            "player_count": 3,
            "profile_count": 0,
        },
    }


def test_squad_players_never_become_lineups_or_canonical_fields():
    payload = fixture_payload()
    result = invoke(
        roster.normalize_event_roster,
        payload=payload,
        home_squad=squad(40, "Home FC", [{"id": 101, "name": "Home"}]),
        away_squad=squad(47, "Away FC", [{"id": 201, "name": "Away"}]),
    )

    enriched = result["data"]["payload"]
    assert "lineups" not in enriched
    assert "participants" not in enriched
    assert "memberships" not in enriched
    assert "capabilities" not in enriched
    assert "machina_sports_schema" not in enriched


def test_source_refs_are_metadata_not_provider_payload_fields():
    payload = fixture_payload()
    result = invoke(
        roster.normalize_event_roster,
        payload=payload,
        home_squad=squad(40, "Home FC", [{"id": 101, "name": "Home"}]),
        away_squad=squad(47, "Away FC", [{"id": 201, "name": "Away"}]),
    )

    assert "source_refs" in result["metadata"]
    assert result["data"]["metadata"] == result["metadata"]
    assert "source_refs" not in result["data"]["payload"]
    assert "roster" in result["metadata"]
    assert "roster" not in payload


def test_lineups_take_precedence_and_remain_exact_provider_data():
    payload = fixture_payload()
    lineups = [
        {
            "team": {"id": 40, "name": "Home FC"},
            "formation": "4-3-3",
            "coach": {"id": 501, "name": "Home Coach"},
            "startXI": [{"player": {"id": 111, "name": "H. Starter",
                                      "number": 8, "pos": "M", "grid": "2:2"}}],
            "substitutes": [],
        },
        {
            "team": {"id": 47, "name": "Away FC"},
            "formation": "4-4-2",
            "startXI": [{"player": {"id": 211, "name": "A. Starter",
                                      "number": 10, "pos": "F"}}],
            "substitutes": [{"player": {"id": 212, "name": "A. Bench",
                                          "number": 18, "pos": "D"}}],
        },
    ]

    result = invoke(
        roster.normalize_event_roster,
        payload=payload,
        lineups=lineups,
        home_squad=squad(40, "Home FC", [{"id": 999, "name": "Ignored"}]),
        away_squad=squad(47, "Away FC", [{"id": 998, "name": "Ignored"}]),
    )

    enriched = result["data"]["payload"]
    assert result["data"]["roster_source"] == "fixture-lineups"
    assert enriched["lineups"] == lineups
    assert enriched["lineups"] is not lineups
    assert enriched["rosters"] == [
        {
            "team": {"id": 40, "name": "Home FC"},
            "players": [
                {"id": 111, "name": "H. Starter", "position": "M",
                 "number": 8},
            ],
        },
        {
            "team": {"id": 47, "name": "Away FC"},
            "players": [
                {"id": 211, "name": "A. Starter", "position": "F",
                 "number": 10},
                {"id": 212, "name": "A. Bench", "position": "D",
                 "number": 18},
            ],
        },
    ]
    assert 999 not in {
        player["id"]
        for team_roster in enriched["rosters"]
        for player in team_roster["players"]
    }
    assert result["metadata"]["source_refs"] == [
        {"kind": "endpoint-class", "value": "api-football/fixtures"},
        {"kind": "endpoint-class", "value": "api-football/fixtures/lineups"},
    ]
    assert result["metadata"]["roster"] == {
        "available": True,
        "fixture_id": 7001,
        "source": "fixture-lineups",
        "team_count": 2,
        "player_count": 3,
        "profile_count": 0,
    }


def test_profiles_are_bounded_and_only_planned_for_missing_names():
    home = squad(40, "Home FC", [
        {"id": player_id, "name": None, "position": "Defender"}
        for player_id in range(100, 125)
    ])
    away = squad(47, "Away FC", [{"id": 201, "name": "Already Named"}])

    disabled = invoke(
        roster.plan_player_profiles,
        include_player_profiles=False,
        max_profile_requests=20,
        home_squad=home,
        away_squad=away,
    )
    planned = invoke(
        roster.plan_player_profiles,
        include_player_profiles=True,
        max_profile_requests=20,
        home_squad=home,
        away_squad=away,
    )

    assert disabled["data"]["profile_requests"] == []
    assert planned["data"]["profile_requests"] == [
        {"id": player_id} for player_id in range(100, 120)
    ]
    assert planned["data"]["truncated"] is True
    assert invoke(
        roster.plan_event_roster,
        payload=fixture_payload(),
        max_profile_requests=21,
    )["status"] is False


def test_profile_name_is_used_only_for_the_same_provider_player_id():
    result = invoke(
        roster.normalize_event_roster,
        payload=fixture_payload(),
        home_squad=squad(40, "Home FC", [
            {"id": 101, "name": None, "number": 4, "position": "Defender"},
        ]),
        away_squad=squad(47, "Away FC", [
            {"id": 201, "name": "Away Player", "position": "Midfielder"},
        ]),
        player_profiles=[
            {"response": [{"player": {"id": 101, "name": "Exact Profile"}}]},
        ],
    )

    assert result["data"]["payload"]["rosters"][0]["players"][0] == {
        "id": 101,
        "name": "Exact Profile",
        "position": "Defender",
        "number": 4,
    }
    assert result["metadata"]["roster"]["profile_count"] == 1
    assert result["metadata"]["source_refs"][-1] == {
        "kind": "endpoint-class",
        "value": "api-football/players/profiles",
    }


def test_duplicate_player_across_squads_is_unavailable():
    result = invoke(
        roster.normalize_event_roster,
        payload=fixture_payload(),
        home_squad=squad(40, "Home FC", [{"id": 101, "name": "Home"}]),
        away_squad=squad(47, "Away FC", [{"id": 101, "name": "Away"}]),
    )

    assert result["status"] is True
    assert result["data"]["available"] is False
    assert result["data"]["requirements_unavailable"] == ["event.rosters"]


def test_malformed_lineup_arrays_fail_unavailable_without_squad_fallback():
    lineups = [
        {"team": {"id": 40}, "startXI": {}, "substitutes": []},
        {"team": {"id": 47}, "startXI": [], "substitutes": []},
    ]

    result = invoke(
        roster.normalize_event_roster,
        payload=fixture_payload(),
        lineups=lineups,
        home_squad=squad(40, "Home FC", [{"id": 999, "name": "Ignored"}]),
        away_squad=squad(47, "Away FC", [{"id": 998, "name": "Ignored"}]),
    )

    assert result["data"]["available"] is False
    assert "rosters" not in result["data"]["payload"]


def test_workflow_and_installer_expose_only_bounded_supported_resources():
    workflow = yaml.safe_load(
        (CONNECTOR_ROOT / "enrich-event-roster.yml").read_text(encoding="utf-8")
    )["workflow"]
    tasks = {task["name"]: task for task in workflow["tasks"]}
    assert tasks["fetch-fixture-lineups"]["connector"]["command"] == \
        "get-fixtures/lineups"
    assert tasks["fetch-home-squad"]["connector"]["command"] == \
        "get-players/squads"
    assert tasks["fetch-away-squad"]["connector"]["command"] == \
        "get-players/squads"
    profiles = tasks["fetch-player-profiles"]
    assert profiles["connector"]["command"] == "get-players/profiles"
    assert profiles["foreach"] == {
        "concurrent": False,
        "limit": 20,
        "name": "profile-request",
        "expr": "$",
        "value": "$.get('profile-requests', [])",
    }
    assert "len($.get('lineup-response', [])) == 0" in \
        tasks["fetch-home-squad"]["condition"]
    assert "not $.get('errors')" in \
        profiles["outputs"]["player-profile-validity"]
    assert workflow["outputs"]["metadata"] == \
        "$.get('roster-metadata', {})"
    assert workflow["outputs"]["requirements-unavailable"] == \
        "$.get('requirements-unavailable', ['event.rosters'])"
    assert tasks["normalize-event-roster"]["outputs"]["roster-metadata"] == \
        "$.get('metadata', {})"

    install = yaml.safe_load(
        (CONNECTOR_ROOT / "_install.yml").read_text(encoding="utf-8")
    )
    entries = {(item["type"], item["path"]) for item in install["datasets"]}
    assert ("connector", "api-football-roster.yml") in entries
    assert ("workflow", "enrich-event-roster.yml") in entries
    for resource_type, path in entries:
        assert resource_type in {"agent", "connector", "workflow"}
        assert (CONNECTOR_ROOT / path).is_file()
