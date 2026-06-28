# World Cup Perfect-Bracket Simulator — Design

**Date:** 2026-06-28
**Pod:** `world-cup-mcp` (all WC data already lives here)
**Status:** additive / exploration. Touches no existing component.

## Goal

From the current tournament state forward (Round of 32 → Final), produce the
single most-likely complete bracket plus every team's per-round advancement and
championship probabilities — as accurately as possible by anchoring on
prediction-market prices (Kalshi / Polymarket) where they exist and carrying the
unpriced deep rounds with a Dixon-Coles team-strength model.

This is an exploration project to demonstrate AI-driven tournament simulation.

## Current state (verified 2026-06-28)

- Real **FIFA World Cup 2026**, 48 teams, cached in `worldcup:event` docs.
- Group stage complete: 76 matches `ft`. We are at the **Round of 32**.
- The next match to kick off is **South Africa vs Canada** (2026-06-28 19:00 UTC) —
  the "Canada vs South Africa" opener in the request.
- 16 knockout fixtures cached (June 28 – July 4); 2 already `ft`, 14 `ns`.
- Deeper rounds (R16 → Final) are NOT seeded — they depend on results, so the
  simulator constructs them forward.
- Markets are **per-match** (Kalshi `KXWCGAME-*` moneyline, spreads, totals;
  Polymarket). No separate outright-champion market is cached.

## What already exists (reused, not rebuilt)

`worldcup-market-intelligence` connector provides:
- `compute_power_ranking(finished_fixtures, seed_ratings)` → `team_index`
  ({team_urn: {power_score, breakdown.attack_score/defense_score, confidence}}).
- `normalize_fifa_seed` and `worldcup:fifa-ranking` seed docs.
- `_match_probabilities` — analytic Dixon-Coles 1X2 from two rankings.

`worldcup-sync-model-forecasts` workflow shows the canonical path to obtain
`team_index`: api-football `get-fixtures` → finished → `compute_power_ranking`.

## What is missing (this project builds)

Tournament-level chaining: nobody forward-simulates the knockout tree to a full
bracket. That is the additive piece.

## Components (naming prefix `wcbracket-`, zero collision)

1. **Connector `wcbracket-engine`** (pyscript), two commands:
   - `build_bracket` — from knockout `worldcup:event` docs (+ finished fixture
     results) construct: the R32 field, resolved winners for completed knockout
     matches, and the forward single-elimination tree (R32→R16→QF→SF→Final).
     R32 matches ordered by kickoff and paired adjacently (standard schedule
     order); the constructed tree is emitted for inspection. Validates/dedups
     (each team once in R32) and warns on data anomalies.
   - `simulate_bracket` — inputs: bracket, `team_index`, per-match market 1X2
     map, config. Precomputes analytic Dixon-Coles **pairwise knockout advance
     probability** P(A beats B) for every possible matchup (regulation 1X2 with
     draw resolved via ET/penalties). For R32 matches with a market moneyline,
     blends model 1X2 with market 1X2 (default 65% market). Runs N≈20k Monte
     Carlo tournaments, tallies per-team per-round reach + champion counts, and
     derives the most-likely bracket (modal occupant per slot, higher-advance
     team per match). Embedded DC math (no cross-connector import).

2. **Workflow `wcbracket-simulate`** — loads finished fixtures, FIFA seed,
   knockout events, and per-match markets; calls `compute_power_ranking` then the
   engine; stores one `worldcup:bracket-simulation` document.

3. **Workflow `wcbracket-get-bracket`** — read-only; serves the latest stored
   simulation for the chat agent / inspection.

4. **Agent `wcbracket-simulator`** — runs `wcbracket-simulate` on demand (can be
   scheduled to refresh after each match day) and answers questions from the
   stored document.

## Market-anchored blend

- **R32 (priced):** blend model 1X2 with Kalshi/Polymarket moneyline (market-weighted).
- **R16+ (unpriced):** model pairwise advance from market-/results-calibrated
  power ranking (the ranking already blends FIFA seed + actual group results).
- **Completed knockout matches:** actual result, fixed.

## Output document `worldcup:bracket-simulation`

`value`: advancement matrix (team → P(reach R16/QF/SF/Final/win)), champion
leaderboard, the most-likely bracket round-by-round, per-R32-match win
probabilities with model-vs-market provenance, the constructed tree, run config
and timestamp, plus `disclaimer` (informational, not betting advice).

## Assumptions / caveats

- R32→R16 tree pairing uses kickoff order (no authoritative bracket map in data);
  the tree is emitted so it can be corrected via an explicit override input.
- No outright-champion market exists to anchor on; per-match markets anchor R32,
  the model carries the rest.
- Informational simulation, not betting advice (mirrors existing WC disclaimers).
