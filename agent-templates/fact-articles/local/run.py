"""Run a full round locally: fetch -> facts -> rank -> plan -> write (5 parallel) -> verify (rules + judge) -> publish -> render.

    uv run --no-project --with sports-skills==0.33.0 --with pyyaml python local/run.py \\
        --client clients/demo-ptbr.yml --from 2026-10-23 --to 2026-10-26 [--offline] [--dataset file.json]

--offline stops after the plan (no writer); --dataset reads a saved connector dataset instead of fetching.
Writes <out>/<event_id>.{facts,article,verify,pub}.json, .html (when scripts/render.py exists) and round_report.json.
"""
import argparse
import json
import pathlib
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "connectors")]

import facts as facts_step  # noqa: E402
import plan as plan_step  # noqa: E402
import publish as publish_step  # noqa: E402
import rank as rank_step  # noqa: E402
import verify as verify_step  # noqa: E402
import write as write_step  # noqa: E402


def load_render():
    try:
        from render import render_article
    except ImportError:
        return None
    return render_article


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1))


def known_names(dataset):
    """Every team (official and short name), venue and city in the dataset: naming one needs a cited fact."""
    games = dataset["events"] + dataset["results"]
    return sorted({n for r in dataset["standings"] for n in (r["team"]["name"], r["team"]["short_name"])}
                  | {n for e in games for n in verify_step.venue_names((e.get("venue") or {}).get("name"))}
                  | {(e.get("venue") or {}).get("city") for e in games} - {None, ""})


class Budget:
    """Caps claude calls for the whole run (writer + judge); a job that would exceed it stops and says so."""

    def __init__(self, limit):
        self.limit, self.used, self.lock = limit, 0, threading.Lock()

    def take(self):
        with self.lock:
            if self.limit is not None and self.used >= self.limit:
                raise RuntimeError(f"claude call budget of {self.limit} exhausted")
            self.used += 1


def frame_problems(result):
    """Headline, meta and section-title failures: any of them keeps the page off."""
    return [f"{r['role']}: {r['text']!r} {r['problems']}" for r in result["sentences"]
            if r["role"] != "sentence" and not r["ok"]]


def article_job(doc, client, names, render, out, judge=None, budget=None):
    """Write, verify (deterministic, then the judge when given), regenerate once when the headline, meta or a
    section title fails, publish, render. Failing twice: no page. Returns the match's report row."""
    eid = doc["event_id"]
    budget = budget or Budget(None)
    row = {"event_id": eid, "attempts": 0, "claude_calls": 0}
    for stale in ("article.json", "verify.json", "pub.json", "html"):  # nothing from an earlier run may survive
        (out / f"{eid}.{stale}").unlink(missing_ok=True)
    try:
        for _ in range(2):
            row["attempts"] += 1
            budget.take()
            row["claude_calls"] += 1
            article = write_step.write(doc, client)
            result = verify_step.verify(doc, article, client, names)
            if judge and not frame_problems(result):  # only judge what the deterministic layer let through
                budget.take()
                row["claude_calls"] += 1
                result = verify_step.verify(doc, article, client, names, judge=judge)
            if not frame_problems(result):
                break
            row.setdefault("retry_reasons", []).append(frame_problems(result))
    except verify_step.JudgeError as e:  # fail closed: an article the judge could not read gets no page
        return {**row, "dropped": [f"judge: {e}"]}
    except Exception as e:  # noqa: BLE001 - one bad match must not sink the round
        return {**row, "error": f"{type(e).__name__}: {e}"}
    dump(out / f"{eid}.article.json", article)
    dump(out / f"{eid}.verify.json", result)
    summary = {"headline": article.get("headline"), "headline_ok": result["headline_ok"], "meta_ok": result["meta_ok"],
               "titles_ok": result["titles_ok"], "anchored": result["anchored"], "total": result["total"],
               "anchored_pct": result["anchored_pct"], "lead_kind": result["lead_kind"]}
    if frame_problems(result):
        return {**row, **summary, "dropped": frame_problems(result)}
    pub = publish_step.publish(article, result)
    dump(out / f"{eid}.pub.json", pub)
    if render:
        (out / f"{eid}.html").write_text(render(pub, doc, client))
    return {**row, **summary, "removed": [{"text": r["text"], "problems": r["problems"]} for r in result["sentences"]
                                          if r["role"] == "sentence" and not r["ok"]]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", default=str(ROOT / "clients" / "demo-ptbr.yml"))
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--dataset", help="saved connector dataset JSON (skips the fetch)")
    ap.add_argument("--out", help="output dir (default: client output_dir/<client>/<from>_<to>)")
    ap.add_argument("--offline", action="store_true", help="stop after facts and plan; no writer")
    ap.add_argument("--no-judge", action="store_true", help="deterministic verifier only (no entailment judge)")
    ap.add_argument("--max-claude-calls", type=int, default=25, help="writer + judge calls for the whole run")
    a = ap.parse_args(argv)

    client = yaml.safe_load(pathlib.Path(a.client).read_text())
    verify_step.require_ptbr(client)
    contract = yaml.safe_load((ROOT / "contracts" / f"{client.get('contract', 'football_preview')}.yml").read_text())
    if a.dataset:
        dataset = json.loads(pathlib.Path(a.dataset).read_text())
    else:
        if not (a.date_from and a.date_to):
            ap.error("--from and --to are required unless --dataset is given")
        import sports_skills_football as connector
        dataset = connector.fetch_round(client["competition_id"], a.date_from, a.date_to,
                                        int(client.get("timezone_offset_hours", 0)))
    out = pathlib.Path(a.out or pathlib.Path(client.get("output_dir", "~/machina/entain/fact-articles-out")).expanduser()
                       / client.get("client", "client") / f"{a.date_from or 'dataset'}_{a.date_to or ''}".rstrip("_"))
    out.mkdir(parents=True, exist_ok=True)
    dump(out / "dataset.json", dataset)

    docs, errors = facts_step.build_round(dataset, contract, client)
    for d in docs:
        rank_step.score_facts(d["facts"])
    plan_step.plan_round(docs, contract)
    for d in docs:
        dump(out / f"{d['event_id']}.facts.json", d)
        m, lead = d["facts"][0]["value"], next(f for f in d["facts"] if f["id"] == d["plan"]["lead_fact"])
        print(f"{d['event_id']} {m['home']} x {m['away']} | lead {lead['kind']} ({lead['norm']}): {lead['text']}")
    for eid, err in errors.items():
        print(f"{eid} NO ARTICLE: {err}")

    report = {"client": client.get("client"), "dataset_as_of": dataset["as_of"], "facts_errors": errors,
              # the verifier is frozen for the run: regex layer + judge prompt + judge model, one hash
              "verifier_hash": verify_step.rules_hash(client),
              "planned_leads": dict(Counter(next(f["kind"] for f in d["facts"] if f["id"] == d["plan"]["lead_fact"])
                                            for d in docs))}
    if not a.offline:
        write_step.system_prompt()  # fail fast with a clear message when prompts/writer.md is missing
        render = load_render()
        names = known_names(dataset)
        budget = Budget(a.max_claude_calls)
        judge = None if a.no_judge else verify_step.claude_judge(client, on_retry=budget.take)
        with ThreadPoolExecutor(5) as ex:
            rows = list(ex.map(lambda d: article_job(d, client, names, render, out, judge, budget), docs))
        done = [r for r in rows if "error" not in r and "anchored" in r]
        anchored, total = sum(r["anchored"] for r in done), sum(r["total"] for r in done)
        report.update({"matches": rows, "rendered": render is not None,
                       "anchored": anchored, "total": total, "anchored_pct": round(100 * anchored / total) if total else 0,
                       "lead_kinds": dict(Counter(r["lead_kind"] for r in done)), "judged": judge is not None,
                       "claude_calls": budget.used, "pages": sum("dropped" not in r and "error" not in r for r in rows)})
        for r in rows:
            state = r.get("error") or (f"{r['anchored']}/{r['total']} anchored, lead={r['lead_kind']}" if "anchored" in r else "")
            print(r["event_id"], state, f"attempts={r['attempts']}", f"DROPPED {r['dropped']}" if "dropped" in r else "")
        if render is None:
            print("scripts/render.py not found: wrote article JSON only")
    dump(out / "round_report.json", report)
    print("out:", out)
    return report


if __name__ == "__main__":
    main()
