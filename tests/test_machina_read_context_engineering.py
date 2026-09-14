"""Synthetic observed-shape tests for the v4 targeted-research pipeline."""
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "connectors/machina-read-multisport/machina-read-multisport.py"
SPEC = importlib.util.spec_from_file_location("read_context_engineering", SOURCE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
NOW = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)


def call(name, params):
    return getattr(module, name)({"params": params})["data"]


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(module, "now", lambda: NOW)


def source(ident, sport, text, url):
    return {"id": ident, "sport": sport, "kind": "article", "label": "Bills win a wild opener",
            "text": text, "url": url, "observedAt": "2026-09-14T14:00:00.000Z",
            "publishedAt": "2026-09-14T13:00:00.000Z"}


def context():
    article = source(
        "article:espn:americanfootball:50003001", "americanfootball",
        "The Buffalo Bills beat the Houston Texans 36-31 in the NFL opener. "
        "Josh Allen led Buffalo in a game that established a 1-0 record and an early AFC result. "
        "This synthetic article body is long enough to represent the full reporting contract.",
        "https://www.espn.com/nfl/story/_/id/50003001/synthetic-report")
    packet = {"anchorSourceId": article["id"],
              "sport": {"id": "americanfootball", "label": "American football"}, "sources": [article]}
    return {"status": "ready", "schemaVersion": 4, "observedAt": "2026-09-14T14:00:00.000Z",
            "scope": "Best sports story of the day", "sports": [packet["sport"]], "sources": [article],
            "candidates": [packet], "coverage": [], "marketSnapshots": [], "prompt": "selection"}


def selection(**overrides):
    choice = {"anchorSourceId": "article:espn:americanfootball:50003001", "subjectType": "team",
              "subjectName": "Buffalo Bills", "teamName": "Buffalo Bills", "competition": "NFL"}
    choice.update(overrides)
    return {"role": "assistant", "finish_reason": "stop", "content": json.dumps({"choices": [choice]})}


def wrapped(request, response):
    return {"request": request, "response": response}


def evaluate_task_output(expression, response, state=None):
    """Mirror machina-client-api _save_outputs substitutions exactly."""
    if expression.strip() == "$":
        return response
    prepared = expression.replace("$.context", "state").replace("$.get", "response.get")
    return eval(prepared, {"response": response, "state": state or {}})


def discovery(plan, team_name="Buffalo Bills"):
    requests = {request["command"]: request for request in plan["requests"]}
    teams = {"status": True, "data": {"teams": [
        {"id": "2", "name": team_name, "abbreviation": "BUF", "nickname": "Bills", "location": "Buffalo"},
        {"id": "34", "name": "Houston Texans", "abbreviation": "HOU", "nickname": "Texans", "location": "Houston"},
    ]}}
    scoreboard = {"status": True, "data": {"events": [{"id": "401872660",
        "name": "Buffalo Bills at Houston Texans", "start_time": "2026-09-14T17:00Z", "status": "closed",
        "competitors": [
            {"team": {"id": "34", "name": "Houston Texans", "abbreviation": "HOU"}, "score": "31", "record": "0-1"},
            {"team": {"id": "2", "name": "Buffalo Bills", "abbreviation": "BUF"}, "score": "36", "record": "1-0"}],
        "odds": None, "week": 1}]}}
    return [wrapped(requests["get_teams"], teams), wrapped(requests["get_scoreboard"], scoreboard),
            wrapped(requests["get_standings"], {"status": True, "data": {"season": 2026, "groups": []}}),
            wrapped(requests["get_injuries"], {"status": True, "data": {"teams": []}})]


def team_stats(team_id="2", season=2026):
    return {"status": True, "data": {"team_id": team_id, "season_year": season, "season_type": 2,
        "categories": [{"name": "Passing", "stats": [
            {"name": "completionPct", "display_name": "Completion Percentage", "value": 68.966,
             "display_value": "69.0", "rank": 5, "rank_display": "Tied-5th"},
            {"name": "passingYards", "display_name": "Passing Yards", "value": 323,
             "display_value": "323", "rank": 3, "rank_display": "3rd"}]}]}}


def research(resolved, stats=None, market=None):
    output = []
    for request in resolved["requests"]:
        if request["command"] == "get_team_stats":
            response = stats if stats is not None else team_stats()
        elif request["command"] == "get_game_summary":
            response = {"status": False, "message": "synthetic omission"}
        elif request["command"] == "search_entity":
            response = market if market is not None else {"status": True, "data": {
                "query": "Buffalo Bills", "sport": "nfl", "kalshi": [], "polymarket": [], "prophetx": [],
                "total_results": 0}}
        elif request["command"] == "match_markets":
            response = {"status": True, "data": {"sport": "nfl", "date": "2026-09-14", "matches": [],
                                                       "match_count": 0, "unmatched": {"kalshi": [], "polymarket": []}}}
        else:
            response = {"status": False, "message": "synthetic omission"}
        output.append(wrapped(request, response))
    return output


def build_brief(**mutations):
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection(**mutations)})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved,
                                          "responses": research(resolved)})
    return initial, plan, resolved, brief


def test_selection_resolves_provider_ids_and_emits_only_allowlisted_read_calls():
    _, plan, resolved, brief = build_brief()
    assert plan["status"] == resolved["status"] == brief["status"] == "ready"
    assert resolved["choices"][0]["teamId"] == "2"
    assert resolved["choices"][0]["eventId"] == "401872660"
    assert all((request["module"], request["command"]) in module.RESEARCH_ALLOWLIST
               for request in plan["requests"] + resolved["requests"])
    assert {source["kind"] for source in brief["sources"]} == {"article", "statistic"}
    statistic = next(source for source in brief["sources"] if source["kind"] == "statistic")
    assert "2026 regular season" in statistic["text"] and "68.966" in statistic["text"]
    assert "Buffalo Bills" in statistic["text"]
    assert "nfl.get_team_stats" in statistic["text"]
    assert statistic["url"] == "https://www.espn.com/nfl/team/stats/_/name/buf/season/2026"
    assert statistic["observedAt"] == "2026-09-14T15:00:00.000Z"
    assert brief["observedAt"] == statistic["observedAt"]


@pytest.mark.parametrize(("sport", "competition", "subject", "team", "expected_module"), [
    ("football", "Premier League", "River City", "River City", "football"),
    ("americanfootball", "NFL", "Buffalo Bills", "Buffalo Bills", "nfl"),
    ("baseball", "MLB", "Metro Drakes", "Metro Drakes", "mlb"),
    ("basketball", "NBA", "Summit Bears", "Summit Bears", "nba"),
    ("hockey", "NHL", "Glacier Kings", "Glacier Kings", "nhl"),
    ("tennis", "ATP", "Callum Wren", "", "tennis"),
    ("motorsport", "Formula 1", "Rory Vance", "", "f1"),
    ("golf", "PGA", "Rory Vance", "", "golf"),
    ("cricket", "IPL", "Harbor XI", "", "cricket"),
])
def test_every_supported_sport_maps_to_its_native_module(sport, competition, subject, team, expected_module):
    article = source(f"article:espn:{sport}:5001", sport,
                     f"{subject} produced the reported result in the {competition}. " + "Researchable context. " * 12,
                     "https://www.espn.com/nfl/story/_/id/5001/synthetic")
    packet = {"anchorSourceId": article["id"], "sport": {"id": sport, "label": module.SPORTS[sport]},
              "sources": [article]}
    pack = {"status": "ready", "schemaVersion": 4, "observedAt": "2026-09-14T14:00:00.000Z",
            "candidates": [packet]}
    selected = {"choices": [{"anchorSourceId": article["id"],
                              "subjectType": "team" if team else "player", "subjectName": subject,
                              "teamName": team, "competition": competition}]}
    plan = call("plan_research", {"context_pack": pack,
                                   "model_reply": {"role": "assistant", "content": json.dumps(selected)}})
    assert plan["status"] == "ready"
    assert {request["module"] for request in plan["requests"]} == {expected_module}
    assert all((request["module"], request["command"]) in module.RESEARCH_ALLOWLIST
               for request in plan["requests"])


@pytest.mark.parametrize(("competition", "league"), [
    ("Premier League", "epl"),
    ("UEFA Champions League", "ucl"),
    ("La Liga", "laliga"),
    ("Serie A", "seriea"),
    ("Bundesliga", "bundesliga"),
    ("Ligue 1", "ligue1"),
    ("MLS", "mls"),
])
def test_validated_football_competition_maps_to_specific_sport_dispatch(competition, league):
    article = source("article:espn:football:5002", "football",
                     f"River City produced the reported result in the {competition}. " + "Context. " * 25,
                     "https://www.espn.com/soccer/story/_/id/5002/synthetic")
    packet = {"anchorSourceId": article["id"], "sport": {"id": "football", "label": "Football (soccer)"},
              "sources": [article]}
    pack = {"status": "ready", "schemaVersion": 4, "observedAt": "2026-09-14T14:00:00.000Z",
            "candidates": [packet]}
    selected = {"choices": [{"anchorSourceId": article["id"], "subjectType": "team",
                              "subjectName": "River City", "teamName": "River City",
                              "competition": competition}]}
    plan = call("plan_research", {"context_pack": pack,
                                   "model_reply": {"role": "assistant", "content": json.dumps(selected)}})
    assert plan["selections"][0]["marketSport"] == league
    assert {request["sport"] for request in plan["requests"]} == {league}
    assert league != "soccer"


def test_generic_soccer_is_not_an_accepted_football_competition():
    article = source("article:espn:football:5003", "football",
                     "River City produced the reported result in Soccer. " + "Context. " * 25,
                     "https://www.espn.com/soccer/story/_/id/5003/synthetic")
    packet = {"anchorSourceId": article["id"], "sport": {"id": "football", "label": "Football (soccer)"},
              "sources": [article]}
    selected = {"choices": [{"anchorSourceId": article["id"], "subjectType": "team",
                              "subjectName": "River City", "teamName": "River City",
                              "competition": "Soccer"}]}
    result = call("plan_research", {"context_pack": {"status": "ready", "schemaVersion": 4,
        "observedAt": "2026-09-14T14:00:00.000Z", "candidates": [packet]},
        "model_reply": {"role": "assistant", "content": json.dumps(selected)}})
    assert result == {"status": "unavailable", "reason": "competition_mismatch"}


@pytest.mark.parametrize("sport,competition", [("basketball", "NBA"), ("hockey", "NHL")])
def test_nba_and_nhl_october_articles_use_the_season_end_year(sport, competition):
    article = source(f"article:espn:{sport}:5004", sport,
                     f"Summit Bears produced the reported result in the {competition}. " + "Context. " * 25,
                     f"https://www.espn.com/{competition.lower()}/story/_/id/5004/synthetic")
    article["publishedAt"] = "2026-10-14T13:00:00.000Z"
    packet = {"anchorSourceId": article["id"], "sport": {"id": sport, "label": module.SPORTS[sport]},
              "sources": [article]}
    selected = {"choices": [{"anchorSourceId": article["id"], "subjectType": "team",
                              "subjectName": "Summit Bears", "teamName": "Summit Bears",
                              "competition": competition}]}
    plan = call("plan_research", {"context_pack": {"status": "ready", "schemaVersion": 4,
        "observedAt": "2026-10-14T14:00:00.000Z", "candidates": [packet]},
        "model_reply": {"role": "assistant", "content": json.dumps(selected)}})
    assert plan["selections"][0]["seasonYear"] == 2027
    standings = next(request for request in plan["requests"] if request["command"] == "get_standings")
    assert standings["season"] == 2027


@pytest.mark.parametrize(("mutation", "reason"), [
    ({"subjectName": "Unknown Club", "teamName": "Unknown Club"}, "unbound_subject"),
    ({"competition": "NBA"}, "competition_mismatch"),
])
def test_unknown_entity_and_wrong_competition_fail_before_dispatch(mutation, reason):
    result = call("plan_research", {"context_pack": context(), "model_reply": selection(**mutation)})
    assert result == {"status": "unavailable", "reason": reason}


def test_mismatched_team_or_season_cannot_supply_quantitative_context():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    for bad in (team_stats(team_id="999"), team_stats(season=2025)):
        brief = call("build_research_brief", {"plan": plan, "resolution": resolved,
                                              "responses": research(resolved, stats=bad)})
        assert brief["reason"] == "no_researchable_story"


def test_identifier_only_payload_is_not_treated_as_quantitative_evidence():
    with pytest.raises(ValueError, match="no_quantitative_stats"):
        module.quantitative_excerpt({"player": {"id": "123", "name": "Callum Wren"}},
                                     "Callum Wren", "2026 season")


@pytest.mark.parametrize("payload", [
    {"standings": [{"team": {"id": "2", "name": "Buffalo Bills"},
                     "rank": 1, "year": 2026, "week": 1}]},
    {"leaderboard": [{"athlete": {"id": "7", "name": "Callum Wren"},
                       "rank": 1, "jersey": 12}]},
    {"stats": [{"player": {"id": "7", "name": "Callum Wren"},
                "season": 2026, "rank": 1}]},
    {"events": [{"name": "Buffalo Bills at Houston Texans", "week": 1,
                 "competitors": [{"team": {"id": "2", "name": "Buffalo Bills"}, "score": 36}]}]},
])
def test_identity_rank_and_score_only_payloads_do_not_qualify_as_statistics(payload):
    subject = "Buffalo Bills" if "Buffalo" in json.dumps(payload) else "Callum Wren"
    with pytest.raises(ValueError, match="no_quantitative_stats"):
        module.quantitative_excerpt(payload, subject, "2026 season")


@pytest.mark.parametrize("payload,subject,expected", [
    ({"standings": [{"team": {"id": "2", "name": "Buffalo Bills"},
                      "stats": [{"name": "wins", "display_name": "Wins", "value": 4}]}]},
     "Buffalo Bills", '"name":"wins"'),
    ({"leaderboard": [{"athlete": {"id": "7", "name": "Rory Vance"},
                        "statistics": [{"name": "score", "display_name": "Score", "value": -12}]}]},
     "Rory Vance", '"name":"score"'),
    ({"categories": [{"name": "Passing", "athlete": {"name": "Callum Wren"},
                       "stats": [{"name": "passingYards", "value": 323}]}]},
     "Callum Wren", '"name":"passingYards"'),
])
def test_named_measures_in_observed_stat_containers_are_admitted(payload, subject, expected):
    excerpt = module.quantitative_excerpt(payload, subject, "2026 season")
    assert expected in excerpt
    assert excerpt.startswith("2026 season:")


@pytest.mark.parametrize(("module_name", "command", "expected"), [
    ("nfl", "get_team_stats", "https://www.espn.com/nfl/team/stats/_/name/buf/season/2026"),
    ("nfl", "get_game_summary", "https://www.espn.com/nfl/game/_/gameId/401872660"),
    ("football", "get_event_statistics", "https://www.espn.com/soccer/match/_/gameId/401872660"),
    ("tennis", "get_rankings", "https://www.espn.com/tennis/rankings"),
    ("golf", "get_leaderboard", "https://www.espn.com/golf/leaderboard"),
    ("f1", "get_driver_standings", "https://www.espn.com/f1/standings"),
])
def test_statistic_urls_point_to_the_relevant_espn_data_page(module_name, command, expected):
    choice = {"module": module_name, "teamAbbreviation": "BUF", "teamId": "2",
              "eventId": "401872660", "seasonYear": 2026}
    assert module.statistic_url(choice, command) == expected


@pytest.mark.parametrize(("team_name", "catalog_mutation", "expected_id"), [
    ("Buffalo Bills", None, "2"),
    ("Bills", None, "2"),
    ("BUF", None, "2"),
    ("Bills", {"id": "99", "name": "Bay City Bills", "abbreviation": "BCB", "nickname": "Bills"}, None),
])
def test_team_resolution_accepts_unique_provider_aliases_and_rejects_ambiguity(team_name, catalog_mutation,
                                                                                expected_id):
    initial = context()
    initial["sources"][0]["text"] += f" The provider also identifies them as {team_name}."
    initial["candidates"][0]["sources"][0]["text"] = initial["sources"][0]["text"]
    plan = call("plan_research", {"context_pack": initial,
                                   "model_reply": selection(subjectName=team_name, teamName=team_name)})
    responses = discovery(plan)
    teams = next(row for row in responses if row["request"]["command"] == "get_teams")
    if catalog_mutation:
        teams["response"]["data"]["teams"].append(catalog_mutation)
    resolved = call("resolve_research", {"plan": plan, "responses": responses})
    assert resolved["choices"][0]["teamId"] == expected_id
    if expected_id:
        assert resolved["choices"][0]["teamName"] == "Buffalo Bills"
        market_request = next(request for request in resolved["requests"]
                              if request["command"] == "search_entity")
        assert market_request["query"] == "Buffalo Bills"


def test_mismatched_event_date_is_not_resolved():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    responses = discovery(plan)
    scoreboard = next(row for row in responses if row["request"]["command"] == "get_scoreboard")
    scoreboard["response"]["data"]["events"][0]["start_time"] = "2025-09-14T17:00Z"
    resolved = call("resolve_research", {"plan": plan, "responses": responses})
    assert resolved["choices"][0]["eventId"] is None
    assert not any(request["command"] == "get_game_summary" for request in resolved["requests"])


def test_no_stats_rejects_generation_while_no_market_is_an_honest_gap():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    missing = research(resolved, stats={"status": False, "message": "not found"})
    assert call("build_research_brief", {"plan": plan, "resolution": resolved,
                                         "responses": missing})["reason"] == "no_researchable_story"
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved,
                                          "responses": research(resolved)})
    assert brief["status"] == "ready" and not any(s["kind"] == "market" for s in brief["sources"])
    assert "Kalshi: no exact related market" in brief["gaps"]
    assert "Polymarket: no exact related market" in brief["gaps"]


def test_score_only_game_summary_cannot_replace_missing_performance_stats():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    responses = research(resolved, stats={"status": False, "message": "not found"})
    summary = next(row for row in responses if row["request"]["command"] == "get_game_summary")
    summary["response"] = {"status": True, "data": {
        "game_info": {"id": "401872660", "status": "STATUS_FINAL"},
        "competitors": [
            {"team": {"id": "34", "name": "Houston Texans"}, "score": 31},
            {"team": {"id": "2", "name": "Buffalo Bills"}, "score": 36},
        ]}}
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved, "responses": responses,
                                           "discovery_responses": discovery(plan)})
    assert brief == {"status": "unavailable", "reason": "no_researchable_story"}


def test_missing_stats_falls_through_to_the_next_ranked_researchable_article():
    first = context()
    second_article = source(
        "article:espn:americanfootball:50003002", "americanfootball",
        "The Metro Drakes beat the Coast Gulls 20-10 in the NFL opener. " + "Synthetic full report context. " * 10,
        "https://www.espn.com/nfl/story/_/id/50003002/synthetic-report")
    second_packet = {"anchorSourceId": second_article["id"],
                     "sport": {"id": "americanfootball", "label": "American football"},
                     "sources": [second_article]}
    first["candidates"].append(second_packet)
    selected = {"choices": [json.loads(selection()["content"])["choices"][0],
        {"anchorSourceId": second_article["id"], "subjectType": "team", "subjectName": "Metro Drakes",
         "teamName": "Metro Drakes", "competition": "NFL"}]}
    plan = call("plan_research", {"context_pack": first,
                                   "model_reply": {"role": "assistant", "content": json.dumps(selected)}})
    discoveries = []
    for request in plan["requests"]:
        if request["command"] == "get_teams":
            name, ident, abbr = (("Buffalo Bills", "2", "BUF") if request["choice"] == 0
                                 else ("Metro Drakes", "101", "MD"))
            response = {"status": True, "data": {"teams": [
                {"id": ident, "name": name, "abbreviation": abbr, "nickname": name.split()[-1],
                 "location": name.split()[0]}]}}
        elif request["command"] == "get_scoreboard":
            response = {"status": True, "data": {"events": []}}
        else:
            response = {"status": True, "data": {}}
        discoveries.append(wrapped(request, response))
    resolved = call("resolve_research", {"plan": plan, "responses": discoveries})
    responses = []
    for request in resolved["requests"]:
        if request["command"] == "get_team_stats" and request["choice"] == 1:
            response = team_stats(team_id="101")
        elif request["command"] in ("search_entity", "match_markets"):
            response = {"status": True, "data": {"query": "Metro Drakes", "sport": "nfl",
                "kalshi": [], "polymarket": [], "matches": []}}
            if request["choice"] == 0:
                response["data"]["query"] = "Buffalo Bills"
        else:
            response = {"status": False, "message": "synthetic omission"}
        responses.append(wrapped(request, response))
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved, "responses": responses})
    assert brief["status"] == "ready"
    assert brief["candidates"][0]["anchorSourceId"] == second_article["id"]


def test_market_requires_exact_subject_competition_season_outcome_and_carries_timestamp():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    good = {"status": True, "data": {"query": "Buffalo Bills", "sport": "nfl", "kalshi": [],
        "polymarket": [{"source": "polymarket", "market_id": "3031300",
            "title": "Will Buffalo Bills win the 2026 NFL championship?", "slug": "buffalo-bills-2026-nfl",
            "outcomes": [{"outcome": "Yes", "price": 0.21}, {"outcome": "No", "price": 0.79}]}],
        "prophetx": [], "total_results": 1}}
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved,
                                          "responses": research(resolved, market=good)})
    market = next(source for source in brief["sources"] if source["kind"] == "market")
    assert "season outlook" in market["text"] and "Yes 0.21" in market["text"]
    assert "observed 2026-09-14T15:00:00.000Z" in market["text"]

    for title, outcomes in [
        ("Will Houston Texans win the 2026 NFL championship?", good["data"]["polymarket"][0]["outcomes"]),
        ("Will Buffalo Bills win the 2025 NFL championship?", good["data"]["polymarket"][0]["outcomes"]),
        ("Will Buffalo Bills win the 2026 NBA championship?", good["data"]["polymarket"][0]["outcomes"]),
        ("Will Buffalo Bills win the 2026 NFL championship?", [{"outcome": "Houston Texans", "price": 0.21}]),
    ]:
        bad = json.loads(json.dumps(good))
        bad["data"]["polymarket"][0]["title"] = title
        bad["data"]["polymarket"][0]["outcomes"] = outcomes
        result = call("build_research_brief", {"plan": plan, "resolution": resolved,
                                               "responses": research(resolved, market=bad)})
        assert not any(source["kind"] == "market" for source in result["sources"])


def test_next_fixture_market_requires_both_teams_and_exact_date():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    responses = research(resolved, market={"status": True, "data": {
        "query": "Buffalo Bills", "sport": "nfl", "kalshi": [], "prophetx": [],
        "polymarket": [{"source": "polymarket", "market_id": "4001",
            "title": "Detroit Lions at Buffalo Bills on 2026-09-18", "slug": "det-buf-2026-09-18",
            "outcomes": [{"outcome": "Buffalo Bills", "price": 0.6},
                         {"outcome": "Detroit Lions", "price": 0.4}]}]}})
    schedule = {"status": True, "data": {"team": {"id": "2", "name": "Buffalo Bills"}, "season": 2026,
        "events": [{"id": "401872932", "name": "Detroit Lions at Buffalo Bills", "status": "not_started",
                    "start_time": "2026-09-18T00:15Z", "competitors": [
                        {"team": {"id": "2", "name": "Buffalo Bills"}},
                        {"team": {"id": "8", "name": "Detroit Lions"}}]}]}}
    row = next(row for row in responses if row["request"]["command"] == "get_team_schedule")
    row["response"] = schedule
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved, "responses": responses})
    market = next(source for source in brief["sources"] if source["kind"] == "market")
    assert "next fixture" in market["text"] and "not the completed game" in market["text"]

    responses = json.loads(json.dumps(responses))
    market_row = next(row for row in responses if row["request"]["command"] == "search_entity")
    market_row["response"]["data"]["polymarket"][0]["slug"] = "det-buf-2026-09-19"
    market_row["response"]["data"]["polymarket"][0]["title"] = "Detroit Lions at Buffalo Bills"
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved, "responses": responses})
    assert not any(source["kind"] == "market" for source in brief["sources"])


def test_research_brief_and_final_story_enforce_budgets_citations_and_no_invented_numbers():
    _, _, _, brief = build_brief()
    assert len(brief["prompt"].encode()) <= module.RESEARCH_PROMPT_BUDGET
    assert len(brief["sources"]) <= 3
    article_id = next(source["id"] for source in brief["sources"] if source["kind"] == "article")
    stat_id = next(source["id"] for source in brief["sources"] if source["kind"] == "statistic")
    story = {"selectedAnchorSourceId": brief["candidates"][0]["anchorSourceId"],
             "headline": "Buffalo turns one win into an early marker",
             "body": "Buffalo Bills beat Houston Texans 36-31 in the NFL opener. The 2026 regular-season data adds 323 passing yards, explaining the scale of the attack without turning one game into a title forecast.",
             "sourceIds": [article_id, stat_id],
             "points": [{"text": "The full report establishes the result and its immediate context.", "sourceIds": [article_id]},
                        {"text": "The 323 passing yards quantify the performance, but the period covers one game.", "sourceIds": [stat_id]}]}
    reply = {"role": "assistant", "finish_reason": "stop", "content": json.dumps(story)}
    assert call("finalize", {"context_pack": brief, "model_reply": reply})["status"] == "ready"
    story["points"][1]["text"] = "The 999 passing yards prove a season-long trend."
    reply["content"] = json.dumps(story)
    assert call("finalize", {"context_pack": brief, "model_reply": reply})["reason"] == "unsupported_numeric_claim"


def test_single_market_observation_cannot_be_written_as_movement_or_causality():
    initial = context()
    plan = call("plan_research", {"context_pack": initial, "model_reply": selection()})
    resolved = call("resolve_research", {"plan": plan, "responses": discovery(plan)})
    market_response = {"status": True, "data": {"query": "Buffalo Bills", "sport": "nfl", "kalshi": [],
        "polymarket": [{"source": "polymarket", "market_id": "3031300",
            "title": "Will Buffalo Bills win the 2026 NFL championship?", "slug": "buffalo-bills-2026-nfl",
            "outcomes": [{"outcome": "Yes", "price": 0.21}, {"outcome": "No", "price": 0.79}]}]}}
    brief = call("build_research_brief", {"plan": plan, "resolution": resolved,
                                          "responses": research(resolved, market=market_response)})
    article_id = next(source["id"] for source in brief["sources"] if source["kind"] == "article")
    stat_id = next(source["id"] for source in brief["sources"] if source["kind"] == "statistic")
    market_id = next(source["id"] for source in brief["sources"] if source["kind"] == "market")
    story = {"selectedAnchorSourceId": brief["candidates"][0]["anchorSourceId"],
             "headline": "Buffalo opens with a statement", "body": "Buffalo Bills beat Houston Texans 36-31.",
             "sourceIds": [article_id],
             "points": [{"text": "The 323 passing yards quantify the attack.", "sourceIds": [stat_id]},
                        {"text": "The Polymarket price rose because of the win.", "sourceIds": [market_id]}]}
    result = call("finalize", {"context_pack": brief, "model_reply": {
        "role": "assistant", "finish_reason": "stop", "content": json.dumps(story)}})
    assert result["reason"] == "unsupported_market_inference"


def test_workflow_has_separate_selection_and_writing_models_and_bounded_native_dispatch():
    workflow = yaml.safe_load((ROOT / "agent-templates/machina-read/workflows/machina-read-produce-daily.yml").read_text())["workflow"]
    models = [task for task in workflow["tasks"] if task.get("connector", {}).get("name") == "machina-ai"]
    assert [task["name"] for task in models] == ["select-researchable-story", "write-researched-story"]
    dispatch = [task for task in workflow["tasks"] if task["name"].startswith("research-")]
    assert dispatch and all(task.get("foreach", {}).get("concurrent") is False for task in dispatch)
    allowed_connectors = {"invoke_football", "invoke_nfl", "invoke_mlb", "invoke_nba", "invoke_nhl",
                          "invoke_tennis", "invoke_golf", "invoke_f1", "invoke_cricket", "invoke_markets"}
    assert {task["connector"]["command"] for task in dispatch} <= allowed_connectors
    assert all(task.get("continue_on_error") is True for task in dispatch)


def test_foreach_outputs_use_the_runtime_response_binding_and_shared_inputs_keep_sport():
    workflow = yaml.safe_load((ROOT / "agent-templates/machina-read/workflows/machina-read-produce-daily.yml").read_text())["workflow"]
    tasks = [task for task in workflow["tasks"] if task.get("foreach")]
    assert tasks
    response = {"status": True, "data": {"sentinel": 1}}
    request = {"requestId": "choice:0", "sport": "epl"}
    for task in tasks:
        expression = next(iter(task["outputs"].values()))
        assert evaluate_task_output(expression, response, {"research_item": request}) == [
            {"request": request, "response": response}]
        assert task["inputs"]["sport"] == "$.get('research_item', {}).get('sport')"
