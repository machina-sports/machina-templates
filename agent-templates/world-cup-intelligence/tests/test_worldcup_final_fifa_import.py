"""Regression coverage for the immutable final FIFA player leaderboard import."""

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "worldcup-market-intelligence.py"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "fifa-final-power-ranking-285023.json.gz"
FIXTURE_SHA256 = "5192eeb55a3b9a957f1f3951a0c757b00da608a3bcb10a13641627fb14dc0735"
SPEC = importlib.util.spec_from_file_location("worldcup_final_fifa_import", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _names(name):
    return [{"locale": "en-GB", "description": name}]


def _outfield(player_id, name, iso="BRA"):
    return {
        "teamId": 43924,
        "teamName": _names("Brazil"),
        "teamFlag": f"https://api.fifa.com/api/v3/picture/flags-{{format}}-{{size}}/{iso}",
        "playerId": player_id,
        "attackingRank": 7,
        "attackingScore": 6.992136478424072,
        "attackingRankChange": 0,
        "attackingRankWithinTeam": 1,
        "defensiveRank": 262,
        "defensiveScore": 4.667199611663818,
        "defensiveRankChange": 11,
        "defensiveRankWithinTeam": 10,
        "creativityRank": 16,
        "creativityScore": 6.836964130401611,
        "creativityRankChange": -1,
        "creativityRankWithinTeam": 1,
        "playerName": _names(name),
        "playerPicture": {"id": f"picture-{player_id}", "pictureUrl": f"https://example.test/{player_id}"},
    }


def _goalkeeper(player_id, name, iso="BRA"):
    return {
        "teamId": 43924,
        "teamName": _names("Brazil"),
        "teamFlag": f"https://api.fifa.com/api/v3/picture/flags-{{format}}-{{size}}/{iso}",
        "playerId": player_id,
        "inPossessionRank": 27,
        "inPossessionScore": 4.456326007843018,
        "defendingTheGoalRank": 18,
        "defendingTheGoalScore": 5.448060989379883,
        "inPossessionRankChange": -1,
        "defendingTheGoalRankChange": 0,
        "playerName": _names(name),
        "playerPicture": {"id": f"picture-{player_id}", "pictureUrl": f"https://example.test/{player_id}"},
    }


def _identity(player_id, name, iso="bra", birth_date="2000-01-01", fifa_id=True):
    provider_ids = {"fifa": str(player_id)} if fifa_id else {"api_football": str(player_id + 1000000)}
    urn = f"urn:machina:sport:soccer:player:{MODULE._slugify(name)}:{birth_date.replace('-', '')}:{iso}"
    return {
        "_id": urn,
        "@id": urn,
        "@type": ["sport:IdentityCrosswalk", "sport:Player"],
        "name": name,
        "birth_date": birth_date,
        "nationality": iso,
        "team": {"@id": f"urn:machina:sport:soccer:team:test:{iso}", "name": "Test"},
        "provider_ids": provider_ids,
        "machina_competition_slug": "world-cup-2026",
    }


def _snapshot():
    outfield = [_outfield(400000 + index, f"Outfield Player {index}") for index in range(202)]
    outfield[175] = _outfield(405742, "VINICIUS JUNIOR")
    goalkeepers = [_goalkeeper(500000 + index, f"Goalkeeper Player {index}") for index in range(28)]
    goalkeepers[23] = _goalkeeper(308370, "ALISSON")
    rows = outfield + goalkeepers
    identities = [_identity(row["playerId"], MODULE._localized_description(row["playerName"])) for row in rows]
    return {
        "competitionId": 285023,
        "nMatches": 104,
        "competitionStage": "Final",
        "messageTimeUtc": "2026-07-20T00:28:49.92294Z",
        "outfieldPlayers": outfield,
        "goalkeepers": goalkeepers,
        "tournamentHistory": [],
    }, identities


def _import(snapshot, identities):
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return MODULE.import_final_fifa_player_power_rankings({"params": {
        "source_payload": snapshot,
        "source_url": MODULE.FIFA_FINAL_POWER_RANKING_URL,
        "expected_sha256": hashlib.sha256(raw).hexdigest(),
        "fetched_at": "2026-08-31T12:00:00Z",
        "players": identities,
    }})["data"]


def test_committed_live_fixture_has_exact_raw_hash_gates_counts_and_ids():
    with gzip.open(FIXTURE_PATH, "rb") as fixture:
        raw = fixture.read()
    payload = json.loads(raw)
    outfield = payload["outfieldPlayers"]
    goalkeepers = payload["goalkeepers"]
    player_ids = [str(row["playerId"]) for row in outfield + goalkeepers]

    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA256 == MODULE.FIFA_FINAL_SHA256
    assert payload["competitionId"] == MODULE.FIFA_FINAL_COMPETITION_ID == 285023
    assert payload["nMatches"] == MODULE.FIFA_FINAL_MATCH_COUNT == 104
    assert payload["competitionStage"] == "Final"
    assert len(outfield) == MODULE.FIFA_FINAL_OUTFIELD_COUNT == 202
    assert len(goalkeepers) == MODULE.FIFA_FINAL_GOALKEEPER_COUNT == 28
    assert len(player_ids) == len(set(player_ids)) == 230


def test_final_import_maps_every_field_and_preserves_separate_player_schemas():
    snapshot, identities = _snapshot()
    result = _import(snapshot, identities)

    assert result["published_count"] == 230
    assert len(result["records"]) == 230
    assert len(result["documents"]) == 231
    vinicius = next(record for record in result["records"] if record["source_player_name"] == "VINICIUS JUNIOR")
    assert vinicius["_id"] == "world-cup-2026:player-power-ranking:405742"
    assert vinicius["status"] == "available"
    assert vinicius["player_type"] == "outfield"
    assert vinicius["scores"] == {
        "attacking": 6.992136478424072,
        "creativity": 6.836964130401611,
        "defending": 4.667199611663818,
    }
    assert vinicius["classification"]["category_rankings"] == [
        {"category": "attacking", "rank": 7, "score": 6.992136478424072, "rank_change": 0, "rank_within_team": 1},
        {"category": "creativity", "rank": 16, "score": 6.836964130401611, "rank_change": -1, "rank_within_team": 1},
        {"category": "defending", "rank": 262, "score": 4.667199611663818, "rank_change": 11, "rank_within_team": 10},
    ]

    alisson = next(record for record in result["records"] if record["source_player_name"] == "ALISSON")
    assert alisson["_id"] == "world-cup-2026:player-power-ranking:308370"
    assert alisson["status"] == "available"
    assert alisson["player_type"] == "goalkeeper"
    assert alisson["scores"] == {
        "in_possession": 4.456326007843018,
        "defending_goal": 5.448060989379883,
    }
    assert alisson["classification"]["category_rankings"] == [
        {"category": "in_possession", "rank": 27, "score": 4.456326007843018, "rank_change": -1},
        {"category": "defending_goal", "rank": 18, "score": 5.448060989379883, "rank_change": 0},
    ]


def test_final_import_manifest_has_hash_counts_and_zero_identity_gaps():
    snapshot, identities = _snapshot()
    result = _import(snapshot, identities)
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    source = result["manifest"]["source_snapshot"]

    assert source == {
        "url": MODULE.FIFA_FINAL_POWER_RANKING_URL,
        "messageTimeUtc": "2026-07-20T00:28:49.92294Z",
        "fetched_at": "2026-08-31T12:00:00Z",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "competitionId": 285023,
        "nMatches": 104,
        "competitionStage": "Final",
        "counts": {"outfield_players": 202, "goalkeepers": 28, "published_players": 230},
    }
    assert result["source_accounting"]["source_rows"] == 230
    assert result["source_accounting"]["published_rows"] == 230
    assert result["source_accounting"]["unresolved_identities"] == 0
    assert result["source_accounting"]["ambiguous_identities"] == 0
    assert result["source_accounting"]["resolution_methods"] == {"fifa_id": 230}
    assert len({record["player_urn"] for record in result["records"]}) == 230
    assert result["manifest"]["metadata"] == {
        "competition": "world-cup-2026",
        "record_type": "snapshot_manifest",
        "snapshot_id": "fifa:285023:final",
    }


def test_document_metadata_upsert_keys_round_trip_without_duplicates():
    snapshot, identities = _snapshot()
    store = {}

    for _ in range(2):
        documents = json.loads(json.dumps(_import(snapshot, identities)["documents"]))
        for document in documents:
            key = (
                "worldcup:final-fifa-player-power-ranking",
                json.dumps(document.get("metadata", {}), sort_keys=True),
            )
            store[key] = document

    assert len(store) == 231
    assert len({key[1] for key in store}) == 231
    assert sum(document["record_type"] == "snapshot_manifest" for document in store.values()) == 1


def test_final_import_rejects_non_injective_player_urn_resolution():
    snapshot, identities = _snapshot()
    identities[1]["_id"] = identities[0]["_id"]

    with pytest.raises(ValueError, match="duplicate canonical player_urn"):
        _import(snapshot, identities)


@pytest.mark.parametrize("fifa_iso,canonical_iso", [
    ("GER", "deu"), ("SUI", "che"), ("CRO", "hrv"), ("POR", "prt"),
    ("NED", "nld"), ("ALG", "dza"), ("RSA", "zaf"), ("PAR", "pry"),
])
def test_identity_resolution_accepts_fifa_iso_aliases(fifa_iso, canonical_iso):
    row = _outfield(1, "Test Player", fifa_iso)
    player = _identity(1, "Test Player", canonical_iso, fifa_id=False)
    detail = {"BirthDate": "2000-01-01T00:00:00Z", "IdCountry": fifa_iso, "Name": _names("Test Player")}

    resolved, method = MODULE._resolve_fifa_player_identity(row, [player], detail)

    assert resolved is player
    assert method == "birth_date_team_unique"


@pytest.mark.parametrize("name,iso", [
    ("Marawan Attia", "egy"),
    ("Lisandro Martinez", "arg"),
    ("Douglas Santos", "bra"),
])
def test_identity_resolution_uses_unique_name_and_team_when_fifa_dob_disagrees(name, iso):
    row = _outfield(1, name, iso.upper())
    player = _identity(1, name, iso, birth_date="1998-08-12", fifa_id=False)
    detail = {"BirthDate": "1998-08-13T00:00:00Z", "IdCountry": iso.upper(), "Name": _names(name)}

    resolved, method = MODULE._resolve_fifa_player_identity(row, [player], detail)

    assert resolved is player
    assert method == "name_team"


def test_identity_resolution_expands_unique_fifa_short_name_within_team():
    row = _outfield(356731, "Raul JIMENEZ", "MEX")
    row["teamName"] = _names("Mexico")
    player = _identity(1, "Raul Alonso Jimenez Rodriguez", "mex", birth_date="1991-05-05", fifa_id=False)
    player["team"]["name"] = "Mexico"
    detail = {"BirthDate": "1991-05-05T00:00:00Z", "IdCountry": "MEX", "Name": _names("Raul JIMENEZ")}

    resolved, method = MODULE._resolve_fifa_player_identity(row, [player], detail)

    assert resolved is player
    assert method == "birth_date_team_unique"


def test_identity_resolution_accepts_unique_birth_date_and_tournament_team_nickname():
    row = _outfield(477770, "PICO LOPES", "CPV")
    row["teamName"] = _names("Cabo Verde")
    player = _identity(1, "Roberto Carlos Lopes", "cpv", birth_date="1992-06-17", fifa_id=False)
    player["team"]["name"] = "Cabo Verde"
    detail = {"BirthDate": "1992-06-17T00:00:00Z", "IdCountry": "CPV", "Name": _names("PICO LOPES")}

    resolved, method = MODULE._resolve_fifa_player_identity(row, [player], detail)

    assert resolved is player
    assert method == "birth_date_team_unique"


def test_identity_resolution_accepts_only_high_confidence_unique_team_fuzzy_match():
    row = _outfield(461788, "MARAWAN ATTIA", "EGY")
    row["teamName"] = _names("Egypt")
    player = _identity(1, "Marwan Attia", "egy", birth_date="1998-08-12", fifa_id=False)
    player["team"]["name"] = "Egypt"
    detail = {"BirthDate": "1998-08-01T00:00:00Z", "IdCountry": "EGY", "Name": _names("MARAWAN ATTIA")}

    resolved, method = MODULE._resolve_fifa_player_identity(row, [player], detail)

    assert resolved is player
    assert method == "name_team_high_confidence_fuzzy"


def test_identity_resolution_allows_only_unique_containment_within_team():
    row = _outfield(1, "Gonzalez", "ARG")
    players = [
        _identity(1, "Nicolas Gonzalez", "arg", fifa_id=False),
        _identity(2, "Unrelated Player", "arg", fifa_id=False),
    ]

    resolved, method = MODULE._resolve_fifa_player_identity(row, players, {})

    assert resolved is players[0]
    assert method == "name_team_containment"


def test_identity_resolution_disambiguates_birth_date_collision_by_name():
    row = _outfield(1, "Nico Gonzalez", "ARG")
    players = [
        _identity(1, "Nicolas Gonzalez", "arg", birth_date="1998-04-06", fifa_id=False),
        _identity(2, "Other Player", "arg", birth_date="1998-04-06", fifa_id=False),
    ]
    detail = {"BirthDate": "1998-04-06T00:00:00Z", "IdCountry": "ARG", "Name": _names("Nico Gonzalez")}

    resolved, method = MODULE._resolve_fifa_player_identity(row, players, detail)

    assert resolved is players[0]
    assert method == "birth_date_country_name_surname_initial"


def test_identity_resolution_fails_closed_when_name_and_team_are_ambiguous():
    row = _outfield(1, "Same Player", "BRA")
    players = [
        _identity(1, "Same Player", "bra", birth_date="2000-01-01", fifa_id=False),
        _identity(2, "Same Player", "bra", birth_date="2001-01-01", fifa_id=False),
    ]

    with pytest.raises(ValueError, match="ambiguous FIFA identity"):
        MODULE._resolve_fifa_player_identity(row, players, {})


def test_team_name_is_used_when_fifa_flag_code_is_unmapped():
    row = _outfield(1, "Test Player", "ZZZ")
    row["teamName"] = _names("Brazil")

    assert MODULE._fifa_team_iso(row) == "bra"


def test_import_resolves_unique_exact_name_and_team_without_detail_calls(monkeypatch):
    snapshot, identities = _snapshot()
    for identity in identities:
        identity["provider_ids"] = {}

    def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("safe no-detail identity resolution should avoid detail fetches")

    monkeypatch.setattr(MODULE, "_fetch_fifa_json", unexpected_fetch)
    result = _import(snapshot, identities)

    assert result["published_count"] == 230
    assert result["source_accounting"]["detail_fetches"] == 0
    assert result["source_accounting"]["resolution_methods"] == {"name_team": 230}


@pytest.mark.parametrize("field,value", [
    ("competitionId", 999), ("nMatches", 103), ("competitionStage", "Semi-final"),
])
def test_final_import_rejects_source_gate_drift_before_publication(field, value):
    snapshot, identities = _snapshot()
    snapshot[field] = value

    with pytest.raises(ValueError, match="snapshot drift"):
        _import(snapshot, identities)


def test_final_import_rejects_unexpected_immutable_snapshot_hash():
    snapshot, identities = _snapshot()

    with pytest.raises(ValueError, match="sha256 drift"):
        MODULE.import_final_fifa_player_power_rankings({"params": {
            "source_payload": snapshot,
            "expected_sha256": "0" * 64,
            "players": identities,
        }})


def test_final_import_rejects_schema_score_rank_and_duplicate_id_drift():
    snapshot, identities = _snapshot()
    del snapshot["outfieldPlayers"][0]["attackingScore"]
    with pytest.raises(ValueError, match="schema drift"):
        _import(snapshot, identities)

    snapshot, identities = _snapshot()
    snapshot["goalkeepers"][0]["inPossessionScore"] = 10.1
    with pytest.raises(ValueError, match="invalid score"):
        _import(snapshot, identities)

    snapshot, identities = _snapshot()
    snapshot["outfieldPlayers"][0]["attackingRank"] = 0
    with pytest.raises(ValueError, match="invalid positive rank"):
        _import(snapshot, identities)

    snapshot, identities = _snapshot()
    snapshot["goalkeepers"][0]["playerId"] = snapshot["outfieldPlayers"][0]["playerId"]
    with pytest.raises(ValueError, match="duplicate playerId"):
        _import(snapshot, identities)


def test_http_fetch_has_bounded_timeout_and_explicit_user_agent(monkeypatch):
    observed = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    def fake_urlopen(request, timeout):
        observed["user_agent"] = request.get_header("User-agent")
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr(MODULE.urllib_request, "urlopen", fake_urlopen)
    payload, raw = MODULE._fetch_fifa_json("https://example.test/data.json", 999)

    assert payload == {"ok": True}
    assert raw == b'{"ok":true}'
    assert observed == {"user_agent": MODULE.FIFA_HTTP_USER_AGENT, "timeout": 30.0}


def test_http_fetch_retries_with_bounded_exponential_backoff(monkeypatch):
    attempts = []
    sleeps = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    def flaky_urlopen(_request, timeout):
        attempts.append(timeout)
        if len(attempts) < 3:
            raise TimeoutError("transient")
        return Response()

    monkeypatch.setattr(MODULE.urllib_request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(MODULE.time, "sleep", sleeps.append)

    payload, _ = MODULE._fetch_fifa_json("https://example.test/data.json", 10, attempts=9, backoff_seconds=3)

    assert payload == {"ok": True}
    assert attempts == [10.0, 10.0, 10.0]
    assert sleeps == [2.0, 2.0]


def test_detail_fetch_failures_are_sorted_and_fail_closed(monkeypatch):
    snapshot, identities = _snapshot()
    failed_ids = [str(snapshot["outfieldPlayers"][1]["playerId"]), str(snapshot["outfieldPlayers"][0]["playerId"])]
    for index in (0, 1):
        identities[index]["provider_ids"] = {}
        identities[index]["name"] = f"Unmatched Identity {index}"

    def failed_fetch(*_args, **_kwargs):
        raise TimeoutError("provider-specific unstable text")

    monkeypatch.setattr(MODULE, "_fetch_fifa_json", failed_fetch)
    raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    with pytest.raises(
        RuntimeError,
        match=f"playerIds={','.join(sorted(failed_ids, key=int))}$",
    ):
        MODULE.import_final_fifa_player_power_rankings({"params": {
            "source_payload": snapshot,
            "expected_sha256": hashlib.sha256(raw).hexdigest(),
            "players": identities,
            "fetch_attempts": 1,
            "retry_backoff_seconds": 0,
        }})
