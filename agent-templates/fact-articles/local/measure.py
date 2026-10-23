"""Measure a round written by local/run.py: anchored %, lead-kind diversity and blind identification.

    uv run --no-project --with pyyaml python local/measure.py <out_dir> [--no-judge]

Blind identification (the prototype's corrected version): from each published article drop the headline,
the meta description and every sentence citing the match fact; mask both team names (and venue/city);
a judge that gets the non-match facts of every match in the round must say which match it is.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

JUDGE = ("Você recebe um artigo de prévia de futebol com os nomes dos dois times trocados por TIME_A e TIME_B "
         "(título, data, hora e estádio foram removidos) e os fatos de todos os jogos da rodada. Diga de qual jogo é "
         'o artigo. Responda só JSON: {"event_id": "...", "certeza": "alta|media|baixa", "pistas": "..."}')


def load(out):
    docs = {p.name.split(".")[0]: json.loads(p.read_text()) for p in sorted(out.glob("*.facts.json"))}
    report = out / "round_report.json"
    matches = json.loads(report.read_text()).get("matches") if report.exists() else None
    if matches is not None:  # only this run's pages: dropped or failed matches are not measured
        pages = {m["event_id"] for m in matches if "anchored" in m and "dropped" not in m}
        docs = {e: d for e, d in docs.items() if e in pages}
    verify = {e: json.loads((out / f"{e}.verify.json").read_text()) for e in docs if (out / f"{e}.verify.json").exists()}
    pubs = {e: json.loads((out / f"{e}.pub.json").read_text()) for e in docs if (out / f"{e}.pub.json").exists()}
    return docs, verify, pubs


def anchoring(verify):
    anchored, total = sum(v["anchored"] for v in verify.values()), sum(v["total"] for v in verify.values())
    kinds = Counter(v["lead_kind"] for v in verify.values())
    return {"anchored": anchored, "total": total, "anchored_pct": round(100 * anchored / total) if total else 0,
            "lead_kinds": dict(kinds),
            "max_lead_kind_share": round(max(kinds.values()) / len(verify), 2) if verify else 0}


def mask(pub, doc):
    match = next(f for f in doc["facts"] if f["kind"] == "match")
    keep = lambda ss: [s["text"] for s in ss if match["id"] not in s.get("fact_ids", [])]  # noqa: E731
    text = "\n".join(keep(pub.get("lead", [])) + [f"## {sec['title']}\n" + " ".join(keep(sec["sentences"]))
                                                  for sec in pub.get("sections", [])])
    m = match["value"]
    for label, name in (("TIME_A", m["home"]), ("TIME_B", m["away"])):
        text = re.sub(re.escape(name), label, text)
    for name, label in ((m.get("venue"), "ESTADIO"), (m.get("city"), "CIDADE")):
        if name:
            text = text.replace(name, label)
    return text


def cards(docs):
    return "\n\n".join(f"JOGO {e}:\n" + "\n".join("- " + f["text"] for f in d["facts"] if f["kind"] != "match")
                       for e, d in docs.items())


def judge(eid, masked, all_cards, model="sonnet"):
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_PLUGIN_DIRS"}
    out = subprocess.run(["claude", "-p", "--model", model, "--setting-sources", "", "--strict-mcp-config", "--tools", "",
                          "--system-prompt", JUDGE, f"ARTIGO:\n{masked}\n\nFATOS DOS JOGOS:\n{all_cards}"],
                         capture_output=True, text=True, env=env, timeout=600, stdin=subprocess.DEVNULL)
    t = out.stdout
    try:
        ans = json.loads(t[t.find("{"):t.rfind("}") + 1])
    except json.JSONDecodeError:
        return {"event_id": eid, "guess": None, "ok": False, "error": (out.stderr or t)[:200]}
    return {"event_id": eid, "guess": ans.get("event_id"), "ok": str(ans.get("event_id")) == eid,
            "certeza": ans.get("certeza"), "pistas": ans.get("pistas")}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--no-judge", action="store_true")
    a = ap.parse_args(argv)
    out = pathlib.Path(a.out).expanduser()
    docs, verify, pubs = load(out)
    res = anchoring(verify)
    if not a.no_judge and pubs:
        all_cards = cards(docs)
        with ThreadPoolExecutor(5) as ex:
            ident = list(ex.map(lambda e: judge(e, mask(pubs[e], docs[e]), all_cards), pubs))
        res["identification"] = {"correct": sum(r["ok"] for r in ident), "total": len(ident), "results": ident}
    (out / "measure.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"anchored {res['anchored']}/{res['total']} ({res['anchored_pct']}%), max lead-kind share "
          f"{res['max_lead_kind_share']}, lead kinds {res['lead_kinds']}")
    if "identification" in res:
        print(f"blind identification {res['identification']['correct']}/{res['identification']['total']}")
    return res


if __name__ == "__main__":
    main()
