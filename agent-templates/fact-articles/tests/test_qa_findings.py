"""QA regression tests (review of 22/10), moved from fact-articles-out/qa/test_qa_findings.py.
Each test states the claim; it failed while the bug existed. Changes from QA's file: docs and names are
built from the offline fixtures (same feed data as QA's run dir, which a re-run overwrites), and the last
test follows decision 3 (pt-BR only)."""
import sys

import pytest
import yaml

from conftest import ROOT, load_dataset

sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "local")]
import facts  # noqa: E402
import plan  # noqa: E402
import rank  # noqa: E402
import render  # noqa: E402
import run  # noqa: E402
import verify  # noqa: E402
import write as write_step  # noqa: E402

CLIENT = yaml.safe_load((ROOT / "clients/demo-ptbr.yml").read_text())
CONTRACT = yaml.safe_load((ROOT / "contracts/football_preview.yml").read_text())
DATASET = load_dataset()
NAMES = run.known_names(DATASET)
_docs, _ = facts.build_round(DATASET, CONTRACT, CLIENT)
for _d in _docs:
    rank.score_facts(_d["facts"])
DOCS = {d["event_id"]: d for d in plan.plan_round(_docs, CONTRACT)}
VASCO = DOCS["401841281"]   # Vasco x Corinthians, São Januário, Rio de Janeiro
INTER = DOCS["401841285"]   # Internacional x Botafogo


def test_fact_ids_match_qa_run():
    # Guard for the move: QA's cases cite ids from its run dir; they must point at the same facts here.
    kinds = {(d["event_id"], f["id"]): f["kind"] for d in (VASCO, INTER) for f in d["facts"]}
    assert kinds[("401841281", "f13")] == "h2h_season" and kinds[("401841281", "f04")] == "last5"
    assert kinds[("401841285", "f04")] == "last5" and kinds[("401841285", "f02")] == "standing"
    assert kinds[("401841285", "f03")] == "relegation_gap" and kinds[("401841285", "f05")] == "goals_rate"


def ok(doc, text, ids):
    art = {"headline": "Vasco x Corinthians: 10 de 15 pontos", "headline_fact_ids": ["f04", "f01"],
           "lead": [{"text": text, "fact_ids": ids}], "sections": []}
    return verify.verify(doc, art, CLIENT, NAMES)["sentences"][1]["ok"]


# Round-2 decision 3: the deterministic win/loss rule is deleted (it removed true sentences in two runs); who won
# is the judge's call, and local/judge_check.py shows the real judge cutting both. strict: if the regex layer
# starts deciding them again, this turns red.
JUDGE_OWNED = pytest.mark.xfail(strict=True, reason="result direction is judged by layer b (decision 3, round 2)")


@pytest.mark.parametrize("doc,text,ids", [
    pytest.param(VASCO, "No primeiro turno, o Vasco venceu o Corinthians por 1x0.", ["f13"], marks=JUDGE_OWNED),  # fact: Corinthians 1x0 Vasco
    pytest.param(INTER, "O Internacional venceu o Mirassol por 2x0 em 16/10.", ["f04"], marks=JUDGE_OWNED),   # fact: 0x2 (D)
    (VASCO, "O Corinthians somou 10 de 15 pontos nos últimos cinco jogos.", ["f04"]),      # Vasco's number
    (INTER, "O Internacional recebe o Botafogo em 16/10/2026.", ["f03", "f01"]),           # date is 24/10
    (VASCO, "Vasco e Corinthians jogam em Porto Alegre.", ["f01"]),                        # city is Rio de Janeiro
    (VASCO, "A cotacao do Vasco subiu.", ["f02"]),                                         # forbidden 'cotaç' unaccented
    (INTER, "O Internacional é o terceiro colocado.", ["f02"]),                            # 17º
])
def test_false_sentence_is_rejected(doc, text, ids):
    assert not ok(doc, text, ids)


def test_failing_headline_and_meta_never_reach_page(tmp_path, monkeypatch):
    bad = {"headline": "Duelo: Vasco é favorito contra o Timão", "headline_fact_ids": ["f01"],
           "meta_description": "Palpite: Vasco vence o Timão por 3x0; odds de 1.80.",
           "lead": [{"text": "Vasco e Corinthians jogam em 24/10/2026.", "fact_ids": ["f01"]}], "sections": []}
    monkeypatch.setattr(write_step, "write", lambda d, c: bad)
    run.article_job(VASCO, CLIENT, NAMES, render.render_article, tmp_path)
    page = (tmp_path / "401841281.html").read_text() if (tmp_path / "401841281.html").exists() else ""
    assert "favorito" not in page and "Palpite" not in page and "odds" not in page


def test_non_ptbr_client_is_refused(tmp_path):
    # Decision 3 (pt-BR only in this phase) replaces QA's "English decimal true sentence is kept".
    en = dict(CLIENT, language="en-GB")
    with pytest.raises(ValueError, match="pt-BR only"):
        verify.verify(INTER, {"headline": "x", "lead": [{"text": "Internacional score 1.06 goals per game.",
                                                         "fact_ids": ["f05"]}], "sections": []}, en, NAMES)
    p = tmp_path / "en.yml"
    p.write_text(yaml.safe_dump(en, allow_unicode=True))
    with pytest.raises(ValueError, match="pt-BR only"):
        run.main(["--client", str(p), "--dataset", "unused.json", "--offline"])


def test_real_run_true_sentence_with_win_and_loss_is_kept():
    # Removed by mistake in the 22/10 re-run (winner check read "venceu" from the first clause).
    assert ok(INTER, "O Internacional venceu o Corinthians por 2x1 em casa em 07/10 e perdeu por 0x2 para o Mirassol "
                     "em 16/10.", ["f04"])
