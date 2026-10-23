import json

import pytest

import run
import sports_skills_football as conn
from conftest import load_dataset


def fake_article(doc, client):
    """A writer stub: first call per match returns a generic headline, the second a good one."""
    fake_article.calls[doc["event_id"]] = fake_article.calls.get(doc["event_id"], 0) + 1
    m = doc["facts"][0]["value"]
    lead = doc["plan"]["lead_fact"]
    return {"headline": f"{m['home']} x {m['away']}: prévia" if fake_article.calls[doc["event_id"]] == 1
            else f"{m['home']} recebe o {m['away']}", "headline_fact_ids": ["f01"], "meta_description": "m",
            "lead": [{"text": next(f["text"] for f in doc["facts"] if f["id"] == lead), "fact_ids": [lead]},
                     {"text": "Os alvinegros chegam com tudo.", "fact_ids": [lead]}],
            "sections": []}


fake_article.calls = {}


def test_runner_end_to_end_offline(tmp_path, monkeypatch):
    ds = tmp_path / "dataset.json"
    ds.write_text(json.dumps(load_dataset()))
    monkeypatch.setattr(run.write_step, "write", fake_article)
    monkeypatch.setattr(run.write_step, "system_prompt", lambda: "x")
    monkeypatch.setattr(run, "load_render", lambda: lambda pub, doc, client: "<html>" + pub["headline"] + "</html>")
    judged = []
    monkeypatch.setattr(run.verify_step, "claude_judge", lambda client, on_retry=None: lambda items: judged.append(items) or
                        [{"i": x["i"], "supported": True, "reason": ""} for x in items])
    out = tmp_path / "out"
    report = run.main(["--dataset", str(ds), "--out", str(out), "--max-claude-calls", "30"])
    assert len(report["matches"]) == 10 and all(r["attempts"] == 2 and r["headline_ok"] for r in report["matches"])
    # the bad first headline is regenerated without judging it: 2 writer calls + 1 judge call per match
    assert len(judged) == 10 and report["claude_calls"] == 30 and report["pages"] == 10
    for suffix in ("facts.json", "article.json", "verify.json", "pub.json", "html"):
        assert (out / f"401841281.{suffix}").exists(), suffix
    pub = json.loads((out / "401841281.pub.json").read_text())
    assert pub["removed"] == ["Os alvinegros chegam com tudo."] and len(pub["lead"]) == 1
    assert json.loads((out / "round_report.json").read_text())["anchored_pct"] == 50


def test_runner_fails_fast_without_prompt(tmp_path, monkeypatch):
    ds = tmp_path / "dataset.json"
    ds.write_text(json.dumps(load_dataset()))
    monkeypatch.setattr(run.write_step, "PROMPT", tmp_path / "missing" / "writer.md")
    with pytest.raises(run.write_step.WriterError, match="prompts/writer.md"):
        run.main(["--dataset", str(ds), "--out", str(tmp_path / "out")])


def test_judge_rejection_removes_sentence_and_budget_stops_the_run(tmp_path, monkeypatch, dataset, contract, client):
    import facts, plan, rank
    docs, _ = facts.build_round(dataset, contract, client)
    for d in docs:
        rank.score_facts(d["facts"])
    doc = plan.plan_round(docs, contract)[0]
    monkeypatch.setattr(run.write_step, "write", lambda d, c: {
        "headline": "Cruzeiro recebe o Remo", "headline_fact_ids": ["f01"], "meta_description": "Cruzeiro x Remo.",
        "lead": [{"text": "Cruzeiro e Remo jogam no Mineirão.", "fact_ids": ["f01"]},
                 {"text": "O Remo chega embalado.", "fact_ids": ["f01"]}], "sections": []})
    stub = lambda items: [{"i": x["i"], "supported": "embalado" not in x["text"], "reason": "stub"} for x in items]  # noqa: E731
    row = run.article_job(doc, client, run.known_names(dataset), None, tmp_path, judge=stub)
    assert row["claude_calls"] == 2 and row["removed"] == [{"text": "O Remo chega embalado.", "problems": ["juiz: stub"]}]
    pub = json.loads((tmp_path / f"{doc['event_id']}.pub.json").read_text())
    assert [s["text"] for s in pub["lead"]] == ["Cruzeiro e Remo jogam no Mineirão."]
    row = run.article_job(doc, client, [], None, tmp_path, judge=stub, budget=run.Budget(1))
    assert "budget" in row["error"]  # the writer ran, the judge call would exceed the cap: no unjudged page


class FakeFootball:
    def __init__(self, days, ok=True):
        self.days, self.ok = days, ok

    def get_current_season(self, competition_id):
        return {"status": self.ok, "message": "down", "data": {"competition": {"id": competition_id, "name": "C"},
                                                             "season": {"id": f"{competition_id}-2026"}}}

    def get_daily_schedule(self, date):
        return {"status": True, "data": {"events": self.days.get(date, [])}}

    def get_season_schedule(self, season_id):
        return {"status": True, "data": {"schedules": [ev("old", "2026-01-01T20:00Z", status="closed")]}}

    def get_season_standings(self, season_id):
        return {"status": True, "data": {"standings": [{"entries": [{"position": 1}]}]}}


def ev(eid, start, comp="serie-a-brazil", status="not_started"):
    return {"id": eid, "start_time": start, "competition": {"id": comp}, "status": status}


def test_connector_filters_by_local_date_and_competition():
    days = {"2026-10-23": [ev("late22", "2026-10-23T02:00Z"), ev("a", "2026-10-23T23:00Z"), ev("pl", "2026-10-23T19:00Z", "premier-league")],
            "2026-10-27": [ev("sun", "2026-10-27T00:30Z"), ev("mon", "2026-10-27T22:00Z")],
            "2026-10-24": [ev("a", "2026-10-23T23:00Z"), ev("played", "2026-10-24T20:00Z", status="closed"),
                           ev("live", "2026-10-24T21:00Z", status="live"), ev("susp", "2026-10-24T22:00Z", status="suspended")]}
    data = conn.fetch_round("serie-a-brazil", "2026-10-23", "2026-10-26", -3, football=FakeFootball(days), as_of="2026-10-22")
    # 22/10 23h local and 27/10 local are out; no dupes; played and live games are out, suspended stays
    assert [e["id"] for e in data["events"]] == ["a", "susp", "sun"]
    assert data["season_id"] == "serie-a-brazil-2026" and [e["id"] for e in data["results"]] == ["old"]


def test_connector_error_on_failed_feed():
    with pytest.raises(conn.ConnectorError, match="get_current_season failed: down"):
        conn.fetch_round("serie-a-brazil", "2026-10-23", "2026-10-26", -3, football=FakeFootball({}, ok=False))
    with pytest.raises(conn.ConnectorError, match="no serie-a-brazil events"):
        conn.fetch_round("serie-a-brazil", "2026-10-23", "2026-10-26", -3, football=FakeFootball({}))
