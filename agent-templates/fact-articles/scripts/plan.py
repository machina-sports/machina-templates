"""Step 3, at round level: normalise scores per kind, pick each match's lead under the kind cap,
and order the contract's sections by their strongest fact."""
import math
from collections import Counter


def normalise(docs):
    """norm = score / best score of the same kind in the round (0 when the kind never scores)."""
    top = Counter()
    for d in docs:
        for f in d["facts"]:
            top[f["kind"]] = max(top[f["kind"]], f["score"])
    for d in docs:
        for f in d["facts"]:
            f["norm"] = round(f["score"] / top[f["kind"]], 3) if top[f["kind"]] else 0.0


def sections_for(facts, contract):
    norm = {f["id"]: f["norm"] for f in facts}
    out = []
    for sec in contract["sections"]:
        ids = [f["id"] for f in facts if f["kind"] in sec["kinds"]]
        if len(ids) >= sec.get("min_facts", 1):
            out.append({"title": sec["title"], "fact_ids": ids, "max_norm": max(norm[i] for i in ids)})
    return sorted(out, key=lambda s: -s["max_norm"])


def plan_round(docs, contract):
    """Set `plan` on every facts doc in place. Each kind leads at most lead_cap of the matches
    (floor, at least 1); matches with the strongest candidate choose first."""
    normalise(docs)
    cap = max(1, math.floor(contract.get("lead_cap", 0.3) * len(docs)))
    cands = {d["event_id"]: sorted((f for f in d["facts"] if f["kind"] != "match"), key=lambda f: (-f["norm"], -f["score"]))
             for d in docs}
    used = Counter()
    for d in sorted(docs, key=lambda d: -cands[d["event_id"]][0]["norm"] if cands[d["event_id"]] else 0):
        free = [f for f in cands[d["event_id"]] if used[f["kind"]] < cap]
        lead = (free or cands[d["event_id"]])[0]  # every kind capped out (tiny rounds): fall back to the best fact
        used[lead["kind"]] += 1
        d["plan"] = {"lead_fact": lead["id"],
                     "match_fact": next(f["id"] for f in d["facts"] if f["kind"] == "match"),
                     "sections": sections_for(d["facts"], contract)}
    return docs


def invoke_plan(request_data):
    p = request_data.get("params") or {}
    try:
        docs = plan_round(p["facts_docs"], p["contract"])
    except KeyError as e:
        return {"status": False, "message": f"plan: missing {e}"}
    return {"status": True, "data": {"facts_docs": docs}}
