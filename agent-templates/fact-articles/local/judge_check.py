"""One-off check of the entailment judge (layer b) on QA's false sentences, plus true controls. Not in pytest:
it calls the real judge (2 claude calls, one per match).

    uv run --no-project --with pytest --with pyyaml python local/judge_check.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts"), str(ROOT / "local")]
from conftest import load_dataset  # noqa: E402
import facts, plan, rank, run, verify  # noqa: E401,E402

V, I = "401841281", "401841285"  # Vasco x Corinthians ; Internacional x Botafogo
FALSE = [  # QA's attack sentences (fact-articles-out/qa/attack_*.py), every one of them false
    (V, "No primeiro turno, o Vasco venceu o Corinthians por 1x0.", ["f13"]),
    (I, "O Internacional venceu o Mirassol por 2x0 em 16/10.", ["f04"]),
    (V, "O Corinthians somou 10 de 15 pontos nos últimos cinco jogos.", ["f04"]),
    (V, "O Corinthians é o 15º, com 35 pontos.", ["f02"]),
    (V, "O Vasco marcou 18 gols em casa.", ["f06"]),
    (I, "O Internacional recebe o Botafogo em 16/10/2026.", ["f03", "f01"]),
    (I, "A partida começa às 17h30 (Brasília).", ["f01", "f03"]),
    (I, "O Internacional recebe o Botafogo em 25/10/2026.", ["f01"]),
    (I, "O Botafogo tem 3 pontos de diferença para o Internacional.", ["f02", "f07"]),
    (V, "O Vasco abre 3 pontos de vantagem sobre o Corinthians.", ["f02", "f07", "f03"]),
    (I, "O Internacional tem quarenta pontos.", ["f02"]),
    (I, "O Internacional é o terceiro colocado.", ["f02"]),
    (I, "O líder Botafogo visita o Internacional.", ["f07"]),
    (I, "O Botafogo não venceu nenhuma partida fora de casa.", ["f11"]),
    (I, "O placar provável é Internacional 2x1 Botafogo.", ["f04"]),
    (I, "Vale a pena arriscar no empate entre Internacional e Botafogo.", ["f12"]),
    (V, "A cotacao do Vasco subiu.", ["f02"]),
    (V, "Vasco is the best bet.", ["f02"]),
    (V, "O Gigante da Colina recebe o Corinthians.", ["f01"]),
    (V, "O Vascão recebe o Corinthians.", ["f01"]),
    (V, "Vasco e Corinthians jogam em São Paulo.", ["f01"]),
    (V, "Vasco e Corinthians jogam em Porto Alegre.", ["f01"]),
    (V, "Vasco e Corinthians jogam na Neo Química Arena.", ["f01"]),
    (V, "Vasco e Corinthians jogam no Mineirão.", ["f01"]),
    (V, "O Vasco já venceu o Atletico-MG.", ["f04"]),
    (V, "Vasco e Corinthians jogam nesta sexta.", ["f01"]),
    (V, "Vasco e Corinthians jogam amanhã, em 24/10/2026.", ["f01"]),
    (V, "O Vasco venceu 47% dos jogos em casa.", ["f06"]),
    (V, "A partida entre Vasco e Corinthians foi adiada.", ["f01"]),
]
TRUE = [  # controls: true sentences the judge must keep
    (V, "No primeiro turno, o Corinthians venceu o Vasco por 1x0, em casa.", ["f13"]),
    (V, "O Vasco somou 10 de 15 pontos nos últimos cinco jogos; o Corinthians, 1.", ["f04", "f09"]),
    (V, "O Corinthians está com 9 jogos sem vencer no Brasileirão Série A.", ["f10"]),
    (I, "O Internacional está em 17º, 1 ponto atrás do Corinthians.", ["f03"]),
    (I, "A partida começa às 16h30 (Brasília), no Estadio Beira-Rio, em Porto Alegre.", ["f01"]),
]


def main():
    client = yaml.safe_load((ROOT / "clients" / "demo-ptbr.yml").read_text())
    contract = yaml.safe_load((ROOT / "contracts" / "football_preview.yml").read_text())
    dataset = load_dataset()
    docs, _ = facts.build_round(dataset, contract, client)
    for d in docs:
        rank.score_facts(d["facts"])
    docs = {d["event_id"]: d for d in plan.plan_round(docs, contract)}
    names, judge = run.known_names(dataset), verify.claude_judge(client)
    cases = [(e, t, ids, False) for e, t, ids in FALSE] + [(e, t, ids, True) for e, t, ids in TRUE]
    verdict, det = {}, {}
    for eid in (V, I):  # one judge call per match, every case of that match in it
        mine = [c for c in cases if c[0] == eid]
        fx = {f["id"]: f["text"] for f in docs[eid]["facts"]}
        for v in judge([{"i": n, "role": "sentence", "text": t, "facts": [fx[x] for x in ids]} for n, (_, t, ids, _) in enumerate(mine)]):
            verdict[mine[int(v["i"])][1]] = v
        for _, t, ids, _ in mine:
            art = {"headline": "x", "headline_fact_ids": ["f01"], "lead": [{"text": t, "fact_ids": ids}], "sections": []}
            det[t] = verify.verify(docs[eid], art, client, names)["sentences"][1]["ok"]
    caught = sum(verdict.get(t, {}).get("supported") is not True for _, t, _, truth in cases if not truth)
    both = sum(verdict.get(t, {}).get("supported") is not True or not det[t] for _, t, _, truth in cases if not truth)
    kept = sum(verdict.get(t, {}).get("supported") is True for _, t, _, truth in cases if truth)
    for _, t, _, truth in cases:
        v = verdict.get(t, {})
        print(f"{'true ' if truth else 'false'} judge={'keep' if v.get('supported') is True else 'CUT '} det={'ok ' if det[t] else 'CUT'} | {t} | {v.get('reason', '')}")
    print(f"judge alone caught {caught}/{len(FALSE)} false; deterministic or judge {both}/{len(FALSE)}; "
          f"true kept by judge {kept}/{len(TRUE)}")


if __name__ == "__main__":
    main()
