import pytest

import facts


def doc_for(eid, dataset, contract, client):
    event = next(e for e in dataset["events"] if e["id"] == eid)
    return facts.build_doc(event, dataset, contract, client)


def fact(doc, kind, subject):
    return next(f for f in doc["facts"] if f["kind"] == kind and f["subject"] == subject)


def test_match_fact_has_every_field(dataset, contract, client):
    m = doc_for("401841282", dataset, contract, client)["facts"][0]  # kicks off 2026-10-25T00:00Z
    assert m["kind"] == "match"
    assert m["value"]["date"] == "24/10/2026" and m["value"]["time_local"] == "21h00"
    assert m["value"]["start_iso"] == "2026-10-24T21:00:00-03:00"
    assert m["value"]["status"] == "not_started" and m["value"]["competition"] == "Brasileirão Série A"
    assert "sábado, 24/10/2026" in m["text"]
    assert set(contract["match_fields"]) <= set(m["value"]) and m["value"]["sport"] == "Futebol"
    assert "adiada" not in m["text"]


def test_postponed_status_is_stated_in_the_match_text(dataset, contract, client):
    event = dict(dataset["events"][0], status="postponed")
    m = facts.build_doc(event, dataset, contract, client)["facts"][0]
    assert m["value"]["status"] == "postponed" and m["text"].endswith("Partida adiada.")


def test_last5_text_has_wdl_counts(dataset, contract, client):
    f = fact(doc_for("401841281", dataset, contract, client), "last5", "home")
    v = f["value"]
    assert "3 vitórias, 1 empate e 1 derrota." in f["text"]  # Vasco: V V V E D
    assert v["won"] + v["drawn"] + v["lost"] == 5


def test_streak_carries_the_game_that_broke_it(dataset, contract, client):
    f = fact(doc_for("401841287", dataset, contract, client), "streak", "away")  # Remo, 11 without a win
    brk = f["value"]["broken_by"]
    assert f["value"]["length"] == 11
    assert f"A última vitória foi em {brk['date']}: {brk['gf']}x{brk['ga']} contra {brk['opponent']}" in f["text"]


def test_relegation_zone_measured_against_16th_others_against_17th(dataset, contract, client):
    doc = doc_for("401841281", dataset, contract, client)  # Vasco 15th x Corinthians 16th
    corinthians = fact(doc, "relegation_gap", "away")
    assert corinthians["value"]["team_position"] == 17 and corinthians["value"]["points_over_first_relegated"] == 1
    inter = fact(doc_for("401841285", dataset, contract, client), "relegation_gap", "home")  # Internacional 17th
    assert inter["value"]["team_position"] == 16 and inter["value"]["points_to_safety"] == 1
    assert "atrás do 16º colocado (Corinthians" in inter["text"]


def test_missing_team_in_table_is_a_connector_error(dataset, contract, client):
    dataset["standings"] = [r for r in dataset["standings"] if r["team"]["short_name"] != "Remo"]
    with pytest.raises(facts.MissingFactError, match="connector error"):
        doc_for("401841287", dataset, contract, client)
    docs, errors = facts.build_round(dataset, contract, client)
    assert list(errors) == ["401841287"] and len(docs) == 9  # the rest of the round still gets articles


def test_missing_venue_is_a_connector_error(dataset, contract, client):
    dataset["events"][0]["venue"] = {"name": "", "city": ""}
    with pytest.raises(facts.MissingFactError, match="match.venue"):
        facts.build_doc(dataset["events"][0], dataset, contract, client)


def test_missing_last5_is_a_connector_error(dataset, contract, client):
    dataset["results"] = []  # season start: no results, so no last-5 fact
    with pytest.raises(facts.MissingFactError, match="last5.home"):
        facts.build_doc(dataset["events"][0], dataset, contract, client)


def test_suspended_status_and_no_invented_rate(dataset, contract, client):
    event = dict(dataset["events"][0], status="suspended")
    assert facts.build_doc(event, dataset, contract, client)["facts"][0]["text"].endswith("Partida suspensa.")
    home = event["competitors"][0]["team"]["id"]
    row = next(r for r in dataset["standings"] if r["team"]["id"] == home)
    row["played"] = 0  # table says no games: no goals-per-game fact, and "0 jogos" not "0 jogo"
    doc = facts.build_doc(event, dataset, contract, client)
    assert not any(f["kind"] == "goals_rate" and f["subject"] == "home" for f in doc["facts"])
    row["played"] = 1
    assert "em 1 jogo (" in fact(facts.build_doc(event, dataset, contract, client), "standing", "home")["text"]
