# Market Stabilization Signal — Requirements

**Created:** 2026-06-30
**Scope:** Standard (feature) — new read-only signal on the deployed cross-source market layer
**Target template:** `agent-templates/world-cup-intelligence`
**Origin:** BetFanatics call 2026-06-30 (Ciaran Foy, Director of Product, trading sports products) + the cross-source pairing work shipped same day (PR #283)

---

## Problem Frame

BetFanatics suspends a market when its price becomes unreliable, then waits for their traditional pricing feed (Ciaran named "TX Fusion") to push an update before putting the market back on site. That wait costs them on-site time — bettable markets sit dark longer than necessary.

Ciaran's ask (verbatim, lightly cleaned): *"prediction market feeds from Kalshi, Polymarket and a singular JSON schema … to help us get markets back on site quicker once the pricing normalizes on Polymarket and Kalshi, as opposed to waiting for updates from like a TX Fusion feed."*

We already normalize both venues into one schema and flag **unreliable** quotes (crossed/thin books). The gap is the **inverse**: an explicit, explainable signal that a quote has **settled into a stable, reliable, cross-venue-agreeing state** — usable as a faster re-enable trigger.

## Goal & Success Criteria

A read-only "stabilized markets" worklist the desk can poll. Success for the 2-week demo:

- **S1.** The signal fires on real, live World Cup markets and returns a worklist of currently-stable markets, each with a `stable_since` timestamp.
- **S2.** Every result is **explainable** — it names which conditions made it stable (spread tight, low recent movement, volume present, cross-venue agreement).
- **S3.** It does **not** mark thin / crossed / still-moving books as stable (no false "safe to re-enable"). Verified against the same books the `unreliable` flag and the de-vig guard already catch.
- **S4.** Honest framing: the demo proves the signal exists and is sound; it does **not** claim a measured latency win over TX Fusion (we lack their suspension events and feed).

Non-goal for success: integration into Fanatics' live re-enablement, or any pricing/execution action.

## Actors

- **A1 — Trading desk / pricing platform (BetFanatics).** Primary consumer. Polls the worklist (via MCP tool / API) to decide which suspended markets are candidates to re-enable.
- **A2 — Machina (demo delivery).** Runs the signal on live WC markets to demonstrate it during the sprint.

## Requirements

- **R1.** A market is classified **stabilized** when, evaluated over a short trailing window of the existing hourly snapshots plus the current quote, all of:
  - currently `price_quality: ok` (not the `unreliable` flag), and
  - the book is complete enough to de-vig (passes the overround band already used by `pair_cross_source`), and
  - spread is tight (within a configurable bps threshold), and
  - **low recent movement** — the primary outcome price has not moved more than a configurable bps across the trailing window, and
  - volume / liquidity is present above a configurable floor.
- **R2.** **Cross-venue agreement upgrades confidence, but is not required.** When both venues price the same outcome and their de-vigged fair prices agree within N bps (reuse `pair_cross_source`), the result is tagged a higher confidence tier (`corroborated`). Single-venue markets can still be `stable` on R1 alone — most markets are single-venue.
- **R3.** Each stabilized result carries: `stable_since` (start of the current uninterrupted stable streak, derived from snapshot history), a `confidence` tier, and a `drivers` list naming the satisfied conditions (S2).
- **R4.** A dedicated read workflow + MCP tool (`worldcup-stable-markets` / `worldcup_stable_markets`) returns the worklist, filterable by team/competition and sorted by `stable_since` (most-recently-stabilized first — the re-enable worklist). Read-only; carries the same resolution-risk disclaimers as the other market tools.
- **R5.** Thresholds (spread bps, movement bps, agreement bps, volume floor, window length) are parameters with sane defaults, so the desk can tune sensitivity without code changes.
- **R6.** Stateless computation — the signal is derived on each call from `worldcup:market-cache` + `worldcup:market-snapshot`; no new persistent state. (Stateful transition logging is deferred — see Scope Boundaries.)

## Scope Boundaries

**In scope:** the stability engine computation, the `worldcup-stable-markets` workflow + MCP tool, explainable drivers, configurable thresholds, reuse of the deployed cache/snapshot/de-vig/pairing primitives.

**Deferred for later (the "prove the speed win" follow-up):**
- Append-only **transition-event logging** (`unstable → stable`, timestamped) and **detection-latency benchmarking** vs a feed baseline. This is what would let us *measure* the re-enable speed advantage — it needs Fanatics' suspension events + TX Fusion timestamps, which we won't have in the demo window.
- A push/alert on transition (vs poll).

**Outside this product's identity:** any pricing, market-making, or execution action; integration into Fanatics' internal re-enablement logic; ingesting Fanatics' proprietary feed. This stays read-only intelligence.

## Key Decisions

- **KD1 — Stateless worklist, not an event stream.** "Currently stable" computed from the snapshot window on each call; `stable_since` read from history. Avoids new persistent state and fits the sprint; the event-stream/latency path is the deferred follow-up.
- **KD2 — Stability is the explainable inverse of the `unreliable` flag, not a new pricing model.** It composes the primitives already shipped (price_quality, de-vig band, snapshot movement, pair_cross_source agreement) — low carrying cost, consistent with the existing engine.
- **KD3 — Single-venue stability is valid; cross-venue agreement is a confidence upgrade.** Requiring both venues would exclude most markets and weaken the demo.

## Dependencies / Assumptions

- Depends on the deployed cross-source layer (PR #283): `worldcup:market-cache`, `worldcup:market-snapshot`, `pair_cross_source`, `price_quality`, the de-vig band guard.
- **Assumption:** the hourly snapshot cadence is granular enough to demonstrate "low recent movement" meaningfully. If a finer cadence is needed for a crisp demo, increasing snapshot frequency during the sprint is a small change (the snapshot id is hourly-bucketed today — noted for planning, not decided here).
- **Assumption (explicit):** we cannot measure latency-vs-TX-Fusion in the demo (no access to their suspension events or feed). Success is framed accordingly (S4).

## Outstanding Questions (resolve at planning or with Fanatics)

- Default threshold values (spread bps, movement bps, agreement bps, volume floor, window length) — pick demo-sane defaults at planning; ideally calibrate against Ciaran's tolerance for re-enable risk.
- Whether the hourly snapshot cadence suffices or the sprint should add a finer-grained snapshot for the demo.
- Confirm with Ciaran whether a polled worklist matches how their re-enablement logic would consume it, or whether they'd want a webhook/push (would promote the deferred transition-event path into scope).
