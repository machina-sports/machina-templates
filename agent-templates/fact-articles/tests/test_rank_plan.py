import facts
import plan
import rank


def planned(dataset, contract, client):
    docs, errors = facts.build_round(dataset, contract, client)
    assert not errors
    for d in docs:
        rank.score_facts(d["facts"])
    return {d["event_id"]: d for d in plan.plan_round(docs, contract)}


def by(doc, kind, subject):
    return next(f for f in doc["facts"] if f["kind"] == kind and f["subject"] == subject)


def lead(doc):
    return next(f for f in doc["facts"] if f["id"] == doc["plan"]["lead_fact"])


def test_standing_score_is_graduated(dataset, contract, client):
    docs = planned(dataset, contract, client)
    scores = [f["score"] for d in docs.values() for f in d["facts"] if f["kind"] == "standing"]
    assert len(set(scores)) >= 10  # 20 teams, not a 2-value step
    chape = by(docs["401841278"], "standing", "home")
    flamengo = by(docs["401841286"], "standing", "home")
    assert chape["norm"] == 1.0 and flamengo["norm"] < 0.5  # last 8 points adrift beats 1st by 1 point


def test_palmeiras_standing_no_longer_beats_its_unbeaten_run(dataset, contract, client):
    d = planned(dataset, contract, client)["401841283"]
    standing, run = by(d, "standing", "home"), by(d, "streak", "home")
    assert run["value"] == {**run["value"], "type": "jogos sem perder", "length": 8}
    assert standing["norm"] < run["norm"]
    assert lead(d)["kind"] != "standing"


def test_norm_is_score_over_best_of_same_kind(dataset, contract, client):
    docs = planned(dataset, contract, client)
    best = {}
    for d in docs.values():
        for f in d["facts"]:
            best[f["kind"]] = max(best.get(f["kind"], 0), f["score"])
    for d in docs.values():
        for f in d["facts"]:
            if best[f["kind"]]:
                assert abs(f["norm"] - f["score"] / best[f["kind"]]) < 0.001


def test_no_kind_leads_more_than_30_percent(dataset, contract, client):
    docs = planned(dataset, contract, client)
    kinds = [lead(d)["kind"] for d in docs.values()]
    assert max(kinds.count(k) for k in kinds) <= 3


def test_strongest_match_chooses_first():
    def doc(eid, streak_score, other_score):
        return {"event_id": eid, "facts": [
            {"id": "f01", "kind": "match", "score": 0.0},
            {"id": "f02", "kind": "streak", "score": streak_score},
            {"id": "f03", "kind": "goals_rate", "score": other_score}]}
    docs = [doc("weak", 5.0, 0.1), doc("strong", 10.0, 0.1)]  # listed weakest first on purpose
    contract = {"lead_cap": 0.3, "sections": [{"title": "S", "kinds": ["streak", "goals_rate"], "min_facts": 1}]}
    out = {d["event_id"]: d["plan"]["lead_fact"] for d in plan.plan_round(docs, contract)}
    assert out == {"strong": "f02", "weak": "f03"}  # cap is 1: the strongest streak takes the only streak slot


def test_sections_follow_contract_and_order_by_strength(dataset, contract, client):
    d = planned(dataset, contract, client)["401841281"]
    titles = [s["title"] for s in d["plan"]["sections"]]
    assert set(titles) <= {s["title"] for s in contract["sections"]}
    norms = [s["max_norm"] for s in d["plan"]["sections"]]
    assert norms == sorted(norms, reverse=True)
    assert d["plan"]["match_fact"] == "f01"
