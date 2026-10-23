"""QA round-2 tests, moved from fact-articles-out/qa/round2/test_round2.py. Only change: docs and names are
built from the offline fixtures (same feed data as QA's run dir, which a re-run overwrites); a guard test
pins the fact ids QA cited."""
import subprocess
import sys

import pytest
import yaml

from conftest import ROOT, load_dataset

sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "local")]
import facts  # noqa: E402
import plan  # noqa: E402
import rank  # noqa: E402
import run  # noqa: E402
import verify  # noqa: E402

CLIENT = yaml.safe_load((ROOT / "clients/demo-ptbr.yml").read_text())
CONTRACT = yaml.safe_load((ROOT / "contracts/football_preview.yml").read_text())
DATASET = load_dataset()
NAMES = run.known_names(DATASET)
_docs, _ = facts.build_round(DATASET, CONTRACT, CLIENT)
for _d in _docs:
    rank.score_facts(_d["facts"])
DOC = {d["event_id"]: d for d in plan.plan_round(_docs, CONTRACT) if d["event_id"] in ("401841281", "401841285", "401841287")}


def test_fact_ids_match_qa_run():
    kind = lambda e, i: next(f["kind"] for f in DOC[e]["facts"] if f["id"] == i)  # noqa: E731
    assert kind("401841285", "f04") == "last5" and kind("401841281", "f04") == "last5"
    assert kind("401841287", "f10") == "streak"
    assert [kind("401841281", i) for i in ("f02", "f03", "f07", "f08")] == ["standing", "relegation_gap"] * 2


def det_ok(eid, text, ids):
    art = {"headline": "x", "headline_fact_ids": ["f01"], "lead": [{"text": text, "fact_ids": ids}], "sections": []}
    return verify.verify(DOC[eid], art, CLIENT, NAMES)["sentences"][1]["ok"]


@pytest.mark.parametrize("eid,text,ids", [  # all TRUE against the cited facts
    ("401841285", "O Internacional venceu o Corinthians por 2x1 em 07/10 e perdeu para o Mirassol por 0x2 em 16/10.", ["f04"]),
    ("401841281", "O Vasco venceu o Grêmio por 2x1 fora de casa e perdeu para o São Paulo por 0x1.", ["f04"]),
    ("401841287", "O Remo busca a primeira vitória desde 26/07.", ["f10"]),
    ("401841281", "O Vasco, 15º com 35 pontos, tem 3 a mais que o Internacional; o Corinthians, 16º com 33, tem 1 a mais.",
     ["f02", "f03", "f07", "f08"]),
])
def test_true_sentence_is_kept(eid, text, ids):
    assert det_ok(eid, text, ids)


def test_judge_answer_with_self_correction_does_not_crash(monkeypatch):
    # Real judge output seen 22/10: a JSON, a "Correção:" paragraph, then a corrected JSON.
    raw = ('{"items": [{"i": 1, "supported": true, "reason": "a"}]}\n\nCorreção: o item 1 não é suportado.\n\n'
           '{"items": [{"i": 1, "supported": false, "reason": "b"}]}')
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, raw, ""))
    art = {"headline": "Vasco x Corinthians: 9 jogos sem vencer", "headline_fact_ids": ["f10", "f01"],
           "lead": [{"text": "O Corinthians está com 9 jogos sem vencer.", "fact_ids": ["f10"]}], "sections": []}
    res = verify.verify(DOC["401841281"], art, CLIENT, NAMES, judge=verify.claude_judge(CLIENT))
    assert res["sentences"][1]["ok"] is False  # the corrected verdict wins, and no exception drops the page


# Coordinator decisions of round 2 (not QA's tests).
def test_judge_without_verdict_retries_once_then_fails_closed(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(1) or subprocess.CompletedProcess(a, 0, "sem JSON", ""))
    art = {"headline": "Vasco recebe o Corinthians", "headline_fact_ids": ["f01"], "meta_description": "Vasco x Corinthians.",
           "lead": [{"text": "Vasco e Corinthians jogam em 24/10/2026.", "fact_ids": ["f01"]}], "sections": []}
    monkeypatch.setattr(run.write_step, "write", lambda d, c: art)
    retries = []
    row = run.article_job(DOC["401841281"], CLIENT, NAMES, None, tmp_path, judge=verify.claude_judge(CLIENT, lambda: retries.append(1)))
    assert len(calls) == 2 and len(retries) == 1 and "judge" in row["dropped"][0]
    assert not (tmp_path / "401841281.pub.json").exists()


def test_headline_and_meta_keep_home_x_away():
    art = {"headline": "Corinthians x Vasco: 9 jogos sem vencer", "headline_fact_ids": ["f10", "f01"],
           "meta_description": "Corinthians x Vasco em 24/10/2026.",
           "lead": [{"text": "Vasco e Corinthians jogam em 24/10/2026.", "fact_ids": ["f01"]}], "sections": []}
    r = verify.verify(DOC["401841281"], art, CLIENT, NAMES)
    assert not r["headline_ok"] and not r["meta_ok"] and "trocados" in r["sentences"][0]["problems"][0]
    art["headline"], art["meta_description"] = "Vasco x Corinthians: 9 jogos sem vencer", "Vasco x Corinthians em 24/10/2026."
    r = verify.verify(DOC["401841281"], art, CLIENT, NAMES)
    assert r["headline_ok"] and r["meta_ok"]


def test_cap_is_four_fact_ids():
    assert not det_ok("401841281", "O Vasco tem 35 pontos.", ["f02", "f03", "f04", "f05", "f06"])


def test_facts_step_refuses_played_match():
    event = dict(DATASET["events"][0], status="closed")
    with pytest.raises(facts.MissingFactError, match="already played"):
        facts.build_doc(event, DATASET, CONTRACT, CLIENT)


def test_rules_hash_covers_judge_prompt(monkeypatch):
    before = verify.rules_hash(CLIENT)
    monkeypatch.setattr(verify, "JUDGE_PROMPT", verify.JUDGE_PROMPT + " x")
    assert verify.rules_hash(CLIENT) != before
    assert verify.rules_hash(dict(CLIENT, verifier_model="opus")) != verify.rules_hash(CLIENT)
