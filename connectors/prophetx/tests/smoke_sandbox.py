#!/usr/bin/env python3
"""Bounded read-only smoke test for the ProphetX Affiliate connector.

Answers the design log's open questions empirically, with ~8 GETs max:
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

    # ---- Step 3: events of the first active tournament ----
    events = []
    tournament_id = None
    for tournament in tournament_list[:3]:
        tournament_id = tournament.get("id")
        if tournament_id is None:
            continue
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
        if events:
            break
    if not events:
        report["findings"]["note"] = "no events found in first active tournaments — markets steps skipped"
        print(json.dumps(report, indent=2))
        return 0

    event_id = events[0].get("event_id")
    scheduled = events[0].get("scheduled")
    report["findings"]["sample_event"] = {"event_id": event_id, "scheduled": scheduled}

    # ---- Step 4: markets v3 (default) ----
    markets_v3 = px.get_markets(request_data(scheme_used, event_id=event_id, api_version="v3"))
    report["requests_used"] += 1
    v3_list = (markets_v3.get("data") or {}).get("markets") or []
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
                    if updated_at_sample is None and level.get("updated_at") is not None:
                        updated_at_sample = level["updated_at"]
    report["steps"].append({"step": "get_markets(v3)", "ok": markets_v3.get("status"), "count": len(v3_list)})
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

    # ---- Step 6: multiple markets dual-shape check (2 ids) ----
    ids = [event_id] + [e.get("event_id") for e in events[1:2] if e.get("event_id")]
    multi = px.get_multiple_markets(request_data(scheme_used, event_ids=ids, api_version="v3"))
    report["requests_used"] += 1
    multi_data = multi.get("data") or {}
    report["steps"].append(
        {
            "step": f"get_multiple_markets({len(ids)} ids)",
            "ok": multi.get("status"),
            "market_count": multi_data.get("market_count"),
            "unattributed": len((multi_data.get("markets_by_event") or {}).get("_unattributed", [])),
        }
    )
    report["findings"]["multiple_markets_shape"] = (
        "dict-by-event" if multi.get("status") and "_unattributed" not in (multi_data.get("markets_by_event") or {}) else "flat-list-or-error"
    )

    report["status"] = "PASSED" if all(step.get("ok") for step in report["steps"]) else "PARTIAL"
    output = json.dumps(report, indent=2)
    print(output)
    if args.out:
        Path(args.out).write_text(output + "\n")
    return 0 if report["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
