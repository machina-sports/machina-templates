#!/usr/bin/env python3
"""Repeatable ProphetX demo: browse markets on an odds screen, hand off via Auto-Fill.

Proves the task's end-to-end experience (ClickUp 86ak0a1jm) with sandbox data:
  1. discover an event with priced markets (bounded scan)
  2. render a terminal odds screen (market / selection / American odds /
     implied probability / available stake)
  3. pick the first priced selection and build the OFFICIAL Auto-Fill handoff
     links (app deep link, OneLink, web fallback) with partner attribution

Machina never executes a wager: the demo ends at the links — account,
geolocation, wallet, and wager placement are entirely ProphetX's.

Credentials: reads PROPHETX_API_SANDBOX (or PROPHETX_API_PROD with
--environment production, which requires separate approval). Values are never
printed. partner_id defaults to "machina-sports" (--partner_id to override).

Usage:
  python3 connectors/prophetx/tests/demo_odds_screen.py \
      [--environment sandbox] [--tournament-id 109] [--event-id N] \
      [--partner-id machina-sports] [--max-rows 12]
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

# Upstream-documented game tournaments (the active-tournaments head is
# dominated by futures catalogs with empty books).
DEFAULT_TOURNAMENTS = (109, 31, 132, 234)  # MLB, NFL, NBA, NHL


def load_connector():
    spec = importlib.util.spec_from_file_location("prophetx_demo", CONNECTOR_DIR / "prophetx.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_key(environment):
    for name in ENV_VAR_CANDIDATES[environment]:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def iter_levels(market):
    for side in market.get("selections") or []:
        for level in side if isinstance(side, list) else [side]:
            if isinstance(level, dict):
                yield level


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", default="sandbox", choices=("sandbox", "production"))
    parser.add_argument("--tournament-id", type=int, default=None)
    parser.add_argument("--event-id", type=int, default=None)
    parser.add_argument("--partner-id", default="machina-sports")
    parser.add_argument("--max-rows", type=int, default=12)
    args = parser.parse_args()

    key = resolve_key(args.environment)
    if not key:
        print(f"SKIPPED: no credential in env ({' or '.join(ENV_VAR_CANDIDATES[args.environment])})")
        return 1

    px = load_connector()

    def rd(**params):
        merged = {"environment": args.environment}
        merged.update(params)
        return {"headers": {"api_key": key}, "params": merged}

    requests_used = 0

    # ---- 1. discover an event (prefer one with priced selections) ----
    event = None
    markets = []
    if args.event_id:
        candidates = [{"event_id": args.event_id, "name": f"event {args.event_id}"}]
    else:
        candidates = []
        tournament_ids = [args.tournament_id] if args.tournament_id else list(DEFAULT_TOURNAMENTS)
        for tid in tournament_ids:
            result = px.get_sport_events(rd(tournament_id=tid))
            requests_used += 1
            events = (result.get("data") or {}).get("sport_events") or []
            candidates.extend(sorted(events, key=lambda e: e.get("scheduled") or "9999")[:5])
            if len(candidates) >= 10:
                break

    for candidate in candidates[:8]:
        result = px.get_markets(rd(event_id=candidate["event_id"], api_version="v3"))
        requests_used += 1
        found = (result.get("data") or {}).get("markets") or []
        if not found:
            continue
        priced = any(level.get("odds") is not None for m in found for level in iter_levels(m))
        if event is None or priced:
            event, markets = candidate, found
        if priced:
            break

    if event is None:
        print(f"No event with markets found ({requests_used} requests). Try --tournament-id or --event-id.")
        return 1

    # ---- 2. odds screen ----
    print()
    print(f"PROPHETX ODDS SCREEN — {args.environment.upper()}  ({requests_used} read-only requests)")
    print(f"Event: {event.get('name')}  |  scheduled: {event.get('scheduled', '?')}  |  status: {event.get('status', '?')}")
    print("-" * 92)
    print(f"{'MARKET':<34} {'SELECTION':<26} {'ODDS':>7} {'PROB':>6} {'STAKE $':>10}")
    print("-" * 92)
    rows = 0
    first_priced = None
    first_any = None
    for market in markets:
        for level in iter_levels(market):
            if rows >= args.max_rows:
                break
            odds = level.get("display_odds") or "—"
            prob = level.get("implied_probability")
            stake = level.get("stake")
            print(
                f"{market.get('name', '')[:33]:<34} {str(level.get('name', ''))[:25]:<26} "
                f"{odds:>7} {(f'{prob:.1%}' if prob else '—'):>6} {(f'{stake:,.0f}' if stake else '—'):>10}"
            )
            rows += 1
            if level.get("line_id"):
                first_any = first_any or level
                if level.get("odds") is not None:
                    first_priced = first_priced or level
        if rows >= args.max_rows:
            break
    print("-" * 92)
    if not first_priced:
        print("NOTE: no priced selections on this event right now (empty public book) — handoff links still work by line_id.")

    # ---- 3. Auto-Fill handoff (pure — no network, no wager) ----
    selected = first_priced or first_any
    if not selected:
        print("No selection with a line_id available — cannot build handoff links.")
        return 1
    links = px.build_autofill_link(
        {
            "params": {
                "line_id": selected["line_id"],
                "partner_id": args.partner_id,
                "odds": selected.get("odds"),
            }
        }
    )
    print()
    print(f"AUTO-FILL HANDOFF — selection: {selected.get('name')} {selected.get('display_odds', '')}".rstrip())
    print(f"(attribution partner_id={args.partner_id}; Machina executes NO wager — the flow ends at these links)")
    print(json.dumps(links.get("data") or {}, indent=2))
    return 0 if links.get("status") else 1


if __name__ == "__main__":
    sys.exit(main())
