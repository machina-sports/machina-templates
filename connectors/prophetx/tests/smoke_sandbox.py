#!/usr/bin/env python3
"""Bounded read-only smoke test for the ProphetX Affiliate connector.

Answers the design log's open questions empirically, with ~15 GETs max:
  1. auth scheme: raw key vs `Bearer` prefix (tries raw first, bearer on 401)
  2. odds format evidence (American-looking ints vs decimal floats)
  3. `updated_at` unit (s/ms/ns magnitude)
  4. selections nesting on v3/v4 (side groups x liquidity levels)
  5. multiple-markets response shape (dict-by-event vs flat list)

Credential handoff (never printed, never logged): reads the FIRST present of
  PROPHETX_API_SANDBOX | EXPORT_PROPHETX_API_SANDBOX   (sandbox, default)
  PROPHETX_API_PROD    | EXPORT_PROPHETX_API_PROD      (--environment production)
Output contains counts, shapes, booleans, and error classes only.

Production runs are read-only and bounded like sandbox, but require separate
approval (task 86ak0a1jm AC) — do not run --environment production without it.

Usage:
  python3 connectors/prophetx/tests/smoke_sandbox.py [--environment sandbox|production] [--out FILE.json]
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

CONNECTOR_DIR = Path(__file__).resolve().parents[1]

ENV_VAR_CANDIDATES = {
    "sandbox": ("PROPHETX_API_SANDBOX", "EXPORT_PROPHETX_API_SANDBOX"),
    "production": ("PROPHETX_API_PROD", "EXPORT_PROPHETX_API_PROD"),
}


def load_connector():
    spec = importlib.util.spec_from_file_location("prophetx_smoke", CONNECTOR_DIR / "prophetx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_key(environment):
    for name in ENV_VAR_CANDIDATES[environment]:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    return None, None


def classify_odds(values):
    """Evidence only — never converts. American odds are int-like with |v|>=100;
    decimal odds are floats typically in (1.01, ~20)."""
    ints = [v for v in values if float(v) == int(float(v)) and abs(float(v)) >= 100]
    decimals = [v for v in values if 1.0 < float(v) < 50 and float(v) != int(float(v))]
    if ints and not decimals:
        return "american-like"
    if decimals and not ints:
        return "decimal-like"
    if ints and decimals:
        return "mixed"
    return "inconclusive"


def updated_at_unit(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "absent"
    if number > 1e17:
        return "nanoseconds"
    if number > 1e14:
        return "microseconds"
    if number > 1e11:
        return "milliseconds"
    return "seconds"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", default="sandbox", choices=("sandbox", "production"))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    key, var_name = resolve_key(args.environment)
    if not key:
        print(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "reason": f"no credential found in env ({' or '.join(ENV_VAR_CANDIDATES[args.environment])})",
                }
            )
        )
        return 1

    px = load_connector()
    report = {
        "environment": args.environment,
        "credential_source_var": var_name,  # the NAME only — never the value
        "requests_used": 0,
        "findings": {},
        "steps": [],
    }

    def request_data(scheme, **params):
        merged = {"environment": args.environment, "auth_scheme": scheme}
        merged.update(params)
        return {"headers": {"api_key": key}, "params": merged}

    # ---- Step 1: auth scheme resolution (raw first, bearer fallback) ----
    scheme_used = None
    health = None
    for scheme in ("raw", "bearer"):
        health = px.health(request_data(scheme))
        report["requests_used"] += 1
        if health.get("status"):
            scheme_used = scheme
            break
        if health.get("error_class") != "credential_invalid":
            break  # unreachable/rate-limited — bearer retry won't change it
    report["findings"]["auth_scheme"] = scheme_used or "FAILED"
    report["steps"].append(
        {
            "step": "health",
            "ok": bool(health and health.get("status")),
            "error_class": None if health.get("status") else health.get("error_class"),
            "tournament_count": (health.get("data") or {}).get("tournament_count"),
        }
    )
    if not scheme_used:
        print(json.dumps(report, indent=2))
        return 1

    # ---- Step 2: tournaments with active events ----
    tournaments = px.get_tournaments(request_data(scheme_used, has_active_events=True))
    report["requests_used"] += 1
    tournament_list = (tournaments.get("data") or {}).get("tournaments") or []
    report["steps"].append(
        {"step": "get_tournaments(active)", "ok": tournaments.get("status"), "count": len(tournament_list)}
    )
    if not tournament_list:
        fallback = px.get_tournaments(request_data(scheme_used))
        report["requests_used"] += 1
        tournament_list = (fallback.get("data") or {}).get("tournaments") or []
        report["steps"].append(
            {"step": "get_tournaments(all)", "ok": fallback.get("status"), "count": len(tournament_list)}
        )

    # ---- Step 3: find an event that actually carries markets ----
    # Futures/outright tournaments can list events with zero markets; scan a
    # few tournaments (soonest events first) until v3 returns markets, within
    # a hard request budget.
    event_id = None
    sibling_event_id = None
    markets_v3 = None
    v3_list = []
    market_probes = 0
    seen_event_ids = []
    for tournament in tournament_list[:6]:
        tournament_id = tournament.get("id")
        if tournament_id is None:
            continue
        if market_probes >= 5:
            break
        events_result = px.get_sport_events(request_data(scheme_used, tournament_id=tournament_id))
        report["requests_used"] += 1
        events = (events_result.get("data") or {}).get("sport_events") or []
        report["steps"].append(
            {
                "step": f"get_sport_events(tournament={tournament_id})",
                "ok": events_result.get("status"),
                "count": len(events),
            }
        )
        events = sorted(events, key=lambda e: e.get("scheduled") or "9999")
        seen_event_ids.extend(e.get("event_id") for e in events if e.get("event_id"))
        if event_id is not None:
            continue  # markets already found — keep collecting ids for step 6
        for event in events[:3]:
            candidate_id = event.get("event_id")
            if candidate_id is None or market_probes >= 5:
                continue
            probe = px.get_markets(request_data(scheme_used, event_id=candidate_id, api_version="v3"))
            report["requests_used"] += 1
            market_probes += 1
            probe_list = (probe.get("data") or {}).get("markets") or []
            report["steps"].append(
                {"step": f"get_markets(v3, event={candidate_id})", "ok": probe.get("status"), "count": len(probe_list)}
            )
            if probe_list:
                event_id = candidate_id
                markets_v3 = probe
                v3_list = probe_list
                siblings = [e.get("event_id") for e in events if e.get("event_id") not in (None, candidate_id)]
                sibling_event_id = siblings[0] if siblings else None
                report["findings"]["sample_event"] = {
                    "event_id": candidate_id,
                    "scheduled": event.get("scheduled"),
                    "tournament_id": tournament_id,
                }
                break

    if event_id is None:
        report["findings"]["note"] = "no event with markets found within the probe budget — odds questions remain open"
        report["status"] = "PARTIAL"
        output = json.dumps(report, indent=2)
        print(output)
        if args.out:
            Path(args.out).write_text(output + "\n")
        return 1
    odds_values = []
    nesting = {"markets": len(v3_list), "sides_max": 0, "levels_max": 0}
    updated_at_sample = None
    for market in v3_list:
        selections = market.get("selections") or []
        nesting["sides_max"] = max(nesting["sides_max"], len(selections))
        for side in selections:
            levels = side if isinstance(side, list) else [side]
            nesting["levels_max"] = max(nesting["levels_max"], len(levels))
            for level in levels:
                if isinstance(level, dict):
                    if level.get("odds") is not None:
                        odds_values.append(level["odds"])
                    if updated_at_sample is None and level.get("updated_at"):
                        updated_at_sample = level["updated_at"]
    report["findings"]["v3_nesting"] = nesting
    report["findings"]["odds_format_evidence"] = {
        "sampled": len(odds_values),
        "classification": classify_odds(odds_values) if odds_values else "no-odds-sampled",
        "sample_values": odds_values[:6],
    }
    report["findings"]["updated_at_unit"] = updated_at_unit(updated_at_sample)

    # ---- Step 5: markets v4 (CFTC naming check) ----
    markets_v4 = px.get_markets(request_data(scheme_used, event_id=event_id, api_version="v4"))
    report["requests_used"] += 1
    v4_list = (markets_v4.get("data") or {}).get("markets") or []
    v4_mapped = bool(
        v4_list
        and any(
            level.get("line_id") is not None and level.get("odds") is not None
            for market in v4_list
            for side in (market.get("selections") or [])
            for level in (side if isinstance(side, list) else [side])
            if isinstance(level, dict)
        )
    )
    report["steps"].append({"step": "get_markets(v4)", "ok": markets_v4.get("status"), "count": len(v4_list)})
    report["findings"]["v4_cftc_mapping_populated"] = v4_mapped

    # ---- Step 6: multiple markets dual-shape check + broad odds evidence ----
    # One batched call over up to 25 seen events: exercises the dual-shape
    # parser and gives the odds/updated_at questions a much wider sample than
    # the single probed event.
    ordered_ids = [event_id] + [eid for eid in seen_event_ids if eid != event_id]
    ids = list(dict.fromkeys(ordered_ids))[:25]
    multi = px.get_multiple_markets(request_data(scheme_used, event_ids=ids, api_version="v3"))
    report["requests_used"] += 1
    multi_data = multi.get("data") or {}
    grouped = multi_data.get("markets_by_event") or {}
    report["steps"].append(
        {
            "step": f"get_multiple_markets({len(ids)} ids)",
            "ok": multi.get("status"),
            "market_count": multi_data.get("market_count"),
            "unattributed": len(grouped.get("_unattributed", [])),
        }
    )
    report["findings"]["multiple_markets_shape"] = (
        "dict-by-event" if multi.get("status") and "_unattributed" not in grouped else "flat-list-or-error"
    )
    batch_odds = []
    for key, markets in grouped.items():
        if key == "_unattributed":
            continue
        for market in markets:
            for side in market.get("selections") or []:
                for level in (side if isinstance(side, list) else [side]):
                    if isinstance(level, dict):
                        if level.get("odds") not in (None, 0):
                            batch_odds.append(level["odds"])
                        if updated_at_sample is None and level.get("updated_at"):
                            updated_at_sample = level["updated_at"]
    if batch_odds:
        report["findings"]["odds_format_evidence"] = {
            "sampled": len(batch_odds),
            "classification": classify_odds(batch_odds),
            "sample_values": batch_odds[:6],
        }
    report["findings"]["updated_at_unit"] = updated_at_unit(updated_at_sample)

    report["status"] = "PASSED" if all(step.get("ok") for step in report["steps"]) else "PARTIAL"
    output = json.dumps(report, indent=2)
    print(output)
    if args.out:
        Path(args.out).write_text(output + "\n")
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
