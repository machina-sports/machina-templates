# PR 3 — consumer inventory and classification

Hand-authored. Companion to the generated `docs/iptc/INVENTORY.md` / `inventory.json`,
which stay authoritative for *what reads an IPTC field path inside this repository*.
This document adds the thing a generator cannot produce: a per-surface **classification**,
a **migration order**, and the **seam** every migrated consumer will call.

Nothing here changes production code, mapping YAML, workflows, connectors, install
manifests, tests, or the generated inventory. This is the classification gate that
the internal design-decision record and `.claude/tasks/CURRENT.md` require before any
PR 3 refactor starts.

---

## 1. Scope and methodology

**In scope.** Every surface that consumes a sports *event* shape produced by Machina —
whether that shape is the legacy `sport:`-prefixed document, a provider payload, or a
hand-rolled normalized model. Both this repository and the cross-repo consumers named
in the PR 3 brief.

**Method, in order of authority:**

1. **Generated inventory first.** `docs/iptc/inventory.json` lists **75** consumer
   files. That list is re-runnable (`python3 -m tools.iptc`) and is the authority for
   in-repo legacy dependencies. This document extends it with categories; it does not
   re-scan and does not restate its rows as if independently discovered.
2. **Targeted verification** of each grounded finding in the PR 3 brief, by reading the
   exact file and symbol named, and by running scoped greps whose patterns are recorded
   below so the result is reproducible.
3. **Bounded cross-repo reads.** Sibling repositories were read at their current checked-out
   ref, read-only, limited to the files needed to classify the surface.
4. **Worktree de-duplication** before counting anything (§7).

**Reproducibility of the scoped greps.** Where this document states a count that is not
from the generated inventory, it came from one of two patterns run over a named directory:

- *legacy-shape pattern* — `worldcup:event|sport:competitors|schema:startDate|sport:competition|sport:venue|sport:status`
- *canonical-key pattern* — `machina_sports_schema|event_view|sport_schema_graph|check_compatibility`

Both are substring matches over file text. They are a floor, not a ceiling: a consumer
that builds a field path at runtime is missed, exactly as the generated inventory's own
"known gaps" section warns. **A consumer either pattern misses is an inventory defect to
fix, not a tolerance to widen.**

**Deliberately not attempted.** No exhaustive manual enumeration of every YAML in every
customer repository is claimed. Where a repository was searched and returned nothing, that
is stated as "searched, no match", not as "has no coupling".

---

## 2. Headline counts and observations

| Fact | Count | Source |
|---|---|---|
| Generated in-repo consumer rows | **75** | `docs/iptc/inventory.json` → `totals.consumer_files` |
| …of which are test scaffolds | 4 | 3 `*-test.yml` under `agent-templates/iptc-mappings/`, 1 `tests/test_worldcup_market_intelligence.py` |
| Emitting mappings / files | 25 / 16 | `totals.emitting_mappings`, `totals.emitting_files` |
| **Production YAML consumers of the canonical contract** | **0** | canonical-key pattern over `agent-templates/` + `connectors/` — no match |
| Corrected canonical envelopes checked in | 8 | `tools/iptc/fixtures/corrected/*-envelope.json` |
| Corrected canonical graphs checked in | 8 | `tools/iptc/fixtures/corrected/*-graph.json` |
| In-repo canonical provider adapters | 6 | `tools/iptc/canonical/adapters/` (api_football, sportradar_{soccer,nfl,mlb,tennis}, stats_perform_opta) |
| Capability names in the contract | 19 | `ALL_CAPABILITIES` in `tools/iptc/canonical/capabilities.py` |
| …with a presence predicate | 15 | `_PRESENCE` |
| …reported `not_expressible` | 4 | `NOT_EXPRESSIBLE` (derived: `ALL_CAPABILITIES − _PRESENCE`) |

### The generated inventory's 75 rows, grouped

| Group | Rows |
|---|---|
| `agent-templates/world-cup-intelligence` | 14 |
| `agent-templates/assistant-tools` | 9 |
| `agent-templates/iptc-mappings` | 6 |
| `agent-templates/kalshi-market-agent` | 5 |
| `agent-templates/coverage-tools` | 4 |
| `agent-templates/chat-completion` | 1 |
| `connectors/api-football` | 9 |
| `connectors/stats-perform` | 9 |
| `connectors/sportradar-soccer` | 8 |
| `connectors/sportradar-nfl` | 4 |
| `connectors/sportradar-mlb` | 3 |
| `connectors/sportradar-tennis` | 2 |
| `connectors/american-football` | 1 |
| **Total** | **75** |

### Observation 1 — the canonical contract has zero production consumers today

The canonical-key pattern over `agent-templates/` and `connectors/` returns **no match**.
Every hit for `machina_sports_schema`, `event_view`, `sport_schema_graph` and
`check_compatibility` in this repository is in `tools/iptc/**`, `tests/**`,
`docs/rfcs/00{1,2}-*.md`, or one comment line in
`agent-templates/iptc-mappings/contexts/iptc-sport-schema-1.1.context.jsonld`.
Two near-hits for the words *capabilities* / *rights* in production YAML —
`agent-templates/machina-media/prompts/storyline-ranking-prompt.yml` (editorial prose about
"rights-dependent video") and `connectors/google-speech-to-text/google-speech-to-text.yml`
("speech-to-text capabilities") — are English, not contract fields.

So: corrected canonical output exists (8 envelopes, 8 graphs, 6 adapters), `sports-skills`
ships a canonical CLI mode, and **not one Machina workflow reads any of it.** The producer
side is finished and the consumer side has not started. That is why the first
implementation step in PR 3 is the **shared access seam** (§5), not a consumer rewrite:
without a seam, each of the surfaces below would invent its own way to reach the envelope,
and PR 3 would end with several new dialects instead of one contract.

### Observation 2 — the generated inventory undercounts World Cup Intelligence by 13 workflows

The generated scan keys on **IPTC field paths and payload state keys**. World Cup
Intelligence also couples to the legacy shape through the *document name*
`'worldcup:event'` in `filters:` blocks, which is not a field path. Running the
legacy-shape pattern over `agent-templates/world-cup-intelligence/` returns 13 workflow
files that carry legacy coupling and are **not** among the 14 generated rows:

`worldcup-get-iptc-event-context.yml`, `worldcup-match-preview.yml`,
`worldcup-get-event-context.yml`, `worldcup-get-schedule.yml`, `worldcup-get-signal.yml`,
`worldcup-resolve.yml`, `worldcup-refresh-live-status.yml`,
`worldcup-refresh-prematch-enrichment.yml`, `worldcup-sync-event-crosswalk.yml`,
`worldcup-generate-market-brief.yml`, `worldcup-get-player-performance-context.yml`,
`worldcup-fan-pulse.yml`, `worldcup-fan-sentiment-context.yml`.

Per the generated inventory's own rule, this is an inventory defect. **Proposed PR 3
action:** extend `tools/iptc/inventory.py` to also record document-name coupling, and
re-generate. Not done in this commit — the generated inventory is out of scope here.

### Observation 3 — Machina Media is invisible to the inventory because it never used IPTC at all

`agent-templates/machina-media/` contributes **0** of the 75 rows. It is not conformant and
not exempt; it is a **parallel event model** that the IPTC-shaped scan cannot see.
`mappings/map-normalize-event.yml` describes itself as mapping "to the canonical 'event'
data model" — a second thing calling itself canonical is the exact duplication PR 3 exists
to remove.

### Observation 4 — a documentation/code discrepancy consumers will hit

RFC 002 §8 states "Five capabilities have no predicate". `NOT_EXPRESSIBLE` in
`tools/iptc/canonical/capabilities.py` derives to **four** names
(`event.coordinates`, `event.tracking`, `event.expected_metrics`, `event.formations`);
the RFC's fifth is the prose placeholder "anything a later version adds", not a name.
Consumers authoring `requires`/`optional` lists should read the code constant, which is
also the vendored one. Recorded as an evidence gap (§10), not fixed here.

---

## 3. Classification

Buckets, as defined for PR 3:

- **canonical already** — reads the `machina_sports_schema` envelope.
- **legacy canonical** — reads the pre-1.1 `sport:`-prefixed Machina document shape.
- **provider-coupled** — reads a provider payload (API-Football fixture, Sportradar,
  Opta) directly, above what should be the boundary.
- **projection-only** — reads only to render/summarize; owns no model and would be
  satisfied by `event_view`.
- **customer-specific** — lives in a customer/product repo, migrates on the customer's
  schedule.
- **dead/unused/test/docs-only** — test scaffolds, docs, generated artefacts, stale worktrees.

Proof confidence: **high** = exact file and symbol read in this session; **medium** =
pattern match over the named directory with at least one file read; **low** = search
result only.

### 3.1 World Cup Intelligence — priority 1

| System / repo | Files / symbols | Current shape / producer | Category | Prio | PR 3 action | Proof |
|---|---|---|---|---|---|---|
| WCI (this repo) | `agent-templates/world-cup-intelligence/worldcup-market-intelligence.py` → `mint_event_identity` (l. 2053) | Mints the obsolete shape itself: `@context.sport = https://www.sportschema.org/ontologies/sport#`, `@type: ["sport:Event","schema:SportsEvent"]`, `schema:startDate`, `sport:status`, `sport:competition`, `sport:venue` (`@type: sport:Venue`), `sport:competitors` (`sport:qualifier`), plus `live_score`, `round`, `stage`, `provider_ids` | legacy canonical (**producer**, not just consumer) | **1** | Replace body with a call to the canonical API-Football adapter + `canonical_envelope`; keep the `worldcup:event` doc as a persisted projection during transition | high |
| WCI | `workflows/worldcup-ingest-fixtures.yml` | `api-football get-fixtures` → `mint_event_identity` → `bulk-update` into `'worldcup:event'`; separately crosswalks Sportradar (`get-seasons/{season_id}/schedules.json`), Entain/bwin, Opta into `build_event_crosswalk` | provider-coupled + legacy canonical | **1** | Single ingest that emits one envelope per fixture; crosswalk feeds `provider_ids`, not a side table | high |
| WCI | `workflows/worldcup-get-iptc-event-context.yml` | `document.search` on `name: 'worldcup:event'`, `value._id` / `value.provider_ids.api_football`, then applies the response mapping | legacy canonical | **1** | Becomes the first caller of `resolve-canonical-event` (§5) | high |
| WCI | `mappings/worldcup-iptc-event-to-api-response.yml` | Hand-rolled projection: `event_urn`, `provider_ids`, `iptc` (whole doc), `name`, `competition` ← `sport:competition.name`, `start_date` ← `schema:startDate`, `status` ← `sport:status`, `teams` ← `sport:competitors`, `venue` ← `sport:venue` | projection-only | **1** | Delete and serve `event_view` — this mapping *is* an ad-hoc `event_view`, field for field | high |
| WCI | `workflows/worldcup-match-preview.yml` | `load-event` searches `'worldcup:event'` by `value._id`, passes the raw doc to `worldcup-match-preview` prompt; also `worldcup:model-forecast`, `worldcup:market-cache`, caches to `worldcup:skill-match-preview` | legacy canonical | **1** | **Representative flow for the substitution proof** (§8) | high |
| WCI | `workflows/worldcup-match-recap.yml`, `prompts/worldcup-match-recap.yml` | Same doc read, recap prompt | legacy canonical | 1 | Migrate with preview | high (generated row) |
| WCI | `workflows/worldcup-get-schedule.yml`, `worldcup-resolve.yml`, `worldcup-get-event-context.yml`, `worldcup-get-signal.yml`, `worldcup-refresh-live-status.yml`, `worldcup-refresh-prematch-enrichment.yml`, `worldcup-sync-event-crosswalk.yml`, `worldcup-generate-market-brief.yml`, `worldcup-get-player-performance-context.yml`, `worldcup-fan-pulse.yml`, `worldcup-fan-sentiment-context.yml` | `'worldcup:event'` document reads / `sport:*` field reads | legacy canonical | 1 | Migrate behind the seam; **also add to the generated inventory** (Observation 2) | medium |
| WCI | `workflows/worldcup-get-standings.yml`, `worldcup-get-injuries.yml`, `worldcup-get-squads.yml` | Generated rows; event-adjacent reads | legacy canonical | 2 | Migrate after the event path lands | high (generated rows) |
| WCI | `workflows/wcbracket-enrich-teams.yml`, `wcbracket-simulate.yml` | Generated rows; bracket sim over event docs | legacy canonical | 2 | Migrate after the event path lands | high (generated rows) |
| WCI | `workflows/worldcup-sync-market-sources.yml`, `worldcup-sync-model-forecasts.yml`, `worldcup-coverage-gateway.yml` | Generated rows | legacy canonical | 2 | Migrate after the event path lands | high (generated rows) |
| WCI | `tests/test_worldcup_market_intelligence.py` | Asserts the legacy mint shape | test | 1 | Update in lockstep with `mint_event_identity` | high |
| WCI | `__pycache__/*.pyc`, `docs/api-contracts.md`, `docs/worldcup-bracket-sim-design.md`, `_folders.yml` | Byte-compiled output and prose that mention the shape | dead / docs-only | — | No code change; refresh docs when the shape changes | high |

### 3.2 Machina Media — priority 2

| System / repo | Files / symbols | Current shape / producer | Category | Prio | PR 3 action | Proof |
|---|---|---|---|---|---|---|
| Machina Media (this repo) | `agent-templates/machina-media/mappings/map-normalize-event.yml` | Independent event model: `sport`, `league`, `home_team{name,score}`, `away_team{name,score}`, `score` as the string `"h-a"`, `clock`, `status`, `start_time`, `external_ids`. Self-described "canonical 'event' data model" | **legacy canonical (duplicate model)** | **2** | **Delete the model.** Replace with `event_view`. Do not preserve as a second canonical shape | high |
| Machina Media | `workflows/sync-sports-state.yml` | Three separate connector pulls — `machina-media-football-data get-matches`, `machina-media-nfl-data get-games`, `machina-media-nba-data get-games` — concatenated and fed to `map-normalize-event` | provider-coupled | **2** | One canonical fan-in; per-sport connectors become adapter inputs below the boundary | high |
| Machina Media | `workflows/detect-storylines.yml` → `prompts/storyline-detection-prompt.yml` (`- Live Events: {normalized_events}`) | Consumes `normalized_events` directly | projection-only | 2 | Repoint to `event_view`; prompt text needs the field names updated once | high |
| Machina Media | `workflows/rank-storylines.yml` | Consumes `candidate_storylines`, not events | projection-only (no event coupling) | 4 | No change | high |
| Machina Media | `workflows/generate-postgame-recap.yml` (`final_event`), `generate-morning-briefing.yml` (`overnight_results`, `todays_schedule`), `generate-live-desk-update.yml` (`live_context`) | Typed as bare `object`; shape supplied by the caller, i.e. the normalized model in practice | projection-only | 2 | Document the input as `event_view` and declare capabilities (§6). Low code delta, real contract delta | high |
| Machina Media | `mappings/map-normalize-news-item.yml`, `map-normalize-market-signal.yml` | News and market signals, not events | out of scope | — | No change | high |
| Machina Media | `connectors/machina-media-{football,nfl,nba}-data.{yml,json}` | Provider surfaces | provider-coupled | 2 | Stay, but below the boundary | high |
| Machina Media | `_install.yml` | Manifest listing the mappings above | — | 2 | Update only when the mapping is removed | high |

### 3.3 Shared in-repo consumers — priority 3

Cited from the generated inventory. Counts are its rows; the characterizations below come
from reading one or two representative files per group.

| System / repo | Files / symbols | Current shape / producer | Category | Prio | PR 3 action | Proof |
|---|---|---|---|---|---|---|
| assistant-tools (9 rows) | `tools/find-upcoming.yml`, `find-odds.yml`, `find-historical.yml`, `event-matcher.yml`; `scripts/event-processor.py`, `event-summarizer.py`, `market-event-matcher.py`, `market-extractor.py`, `message-data-transformer.py` | Document search on `name: 'sport:Event'`, sorted by `value.schema:startDate`, then `iptc-events-summary`. `event-processor.py` reads `schema:startDate`, `sport:competitor(s)`, `sport:homeScore`, `sport:score`, `sport:status` | legacy canonical + projection-only | **3** | Repoint to the seam. **Note the filter coupling**: `value.schema:startDate` and `value.sport:status` are *storage* predicates, so migration needs either a stored canonical projection or an index-compatible alias — this is the hardest part of group 3 | high |
| IPTC any-selectors / summaries (6 rows) | `iptc-mappings/any-selector/event-selector.yml`, `events-selector.yml`, `events-summary.yml` (`iptc-events-summary`, `iptc-events-summary-statistics`) | Pure readers: `@id`, `name`, `schema:startDate`, `schema:sportName`, `sport:score.{homeScore,awayScore}`, `sport:status`, `sport:venue`, `sport:channels`, `sport:statParticipant`/`sport:statLabel`/`sport:statValue` | **projection-only** | **3** | The single highest-leverage migration in group 3: these are the shared selectors most other surfaces route through. Rewrite against `event_view` once | high |
| coverage-tools (4 rows) | `mappings/selectors.yml` (`coverage-iptc-events-summary`, `coverage-mapping-search-date-interval`), `scripts/past_events.py`, `tools/find-images.yml`, `tools/soccer/tallysight-widgets.yml` | Same legacy reads plus timezone formatting (BRT/CET) | projection-only | 3 | Repoint to `event_view`; timezone logic is presentation and stays | high |
| Kalshi matcher / market (5 rows) | `kalshi-market-agent/workflows/event-matcher.yml`, `market-analysis/{consumer,executor}.yml`, `combo-analysis/executor.yml`, `scripts/market-event-matcher.py` | Filters `'sport:Event'` by `value.sport:competition.sport:season.@id`, `value.sport:status: {$nin: [Played, closed, ended, FT]}`, `value.schema:startDate` | legacy canonical | 3 | Same storage-predicate problem as assistant-tools. **The `$nin` status list is a provider-vocabulary leak** (`FT` is API-Football, `closed` is Sportradar) — canonical `status` fixes it | high |
| chat-completion (1 row) | `workflows/chat-moderator.yml` | Incidental event read | projection-only | 4 | Repoint with group 3 | high (generated row) |
| Provider connector sync/consumer workflows (36 rows) | `connectors/api-football/**` (9), `stats-perform/**` (9), `sportradar-soccer/**` (8), `sportradar-nfl/**` (4), `sportradar-mlb/**` (3), `sportradar-tennis/**` (2), `american-football/**` (1) | Provider payload → legacy IPTC mapping → document store. These are the **producers** that the 6 in-repo canonical adapters already replace at the library level | provider-coupled | 3 | Route through the corresponding `tools/iptc/canonical/adapters/*` and emit the envelope. **Highest row count and lowest risk per row** — each is a mechanical producer swap once the seam exists | high (generated rows) |
| Test scaffolds (4 rows) | `iptc-mappings/any-source/custom-event-test.yml`, `iptc-mappings/api-football/event-mapping-test.yml`, `iptc-mappings/sportradar/event-mapping-test.yml`, WCI `tests/test_worldcup_market_intelligence.py` | Exercise the legacy emitters | test | with their subject | Update alongside the mapping they test; never ahead of it | high |

### 3.4 SportsClaw — priority 4

| System / repo | Files / symbols | Current shape / producer | Category | Prio | PR 3 action | Proof |
|---|---|---|---|---|---|---|
| `sportsclaw` | `src/tools/sports_query.ts` → `executePythonBridge(input.sport, input.command, input.args, …)`, returns `JSON.stringify(result.data)` | Raw native `sports-skills` payload, passed through untouched | provider-coupled (pass-through) | **4** | Add a canonical event tool that requests canonical mode and **validates the envelope before returning it** | high |
| `sportsclaw` | `src/bridge.ts` → `buildArgs(sport, command, args)` builds `["-m","sports_skills",sport,command, "--k=v"…]` | Already forwards arbitrary CLI args, so `--format=machina-canonical` / `--observed-at` / `--consumer-tier` are reachable **today with no bridge change** | enabler | 4 | No change needed to `buildArgs` — this is the cheapest part | high |
| `sportsclaw` | Whole `src/` tree | Canonical-key pattern returns **no** match for `machina_sports_schema`, `event_view`, `sport_schema_graph`, `check_compatibility`. (Hits for the *word* "canonical" are cache keys, entity resolution and guardrail hashing — unrelated.) | **gap** | 4 | SportsClaw does not validate the envelope, does not enforce capabilities or rights, and exposes no stable canonical event tool | high |
| `sports-skills` (`origin/main` @ `944c14e`) | `src/sports_skills/canonical/_cli.py`: `CANONICAL_FORMAT = "machina-canonical"`, `EVENT_COMMANDS = {("football","get_event_summary"), ("football","get_daily_schedule")}`, `DEFAULT_CONSUMER_TIER = "prototype"`, `_vendored/{capabilities,rights,ids,observation,serialize,vocab}.py` | Canonical mode exists and is byte-vendored from this repo | **canonical already** (producer) | — | Consume it. **Do not copy canonical terms into SportsClaw** — SportsClaw consumes the schema, it does not own it | high |

**Constraint to design around, not around which to design.** `_cli.py` states every
envelope it emits is `open-public` / `prototype_only`, and the rights gate refuses a
`production` consumer tier *before* the provider is called. So SportsClaw-over-sports-skills
can prove canonical **shape and behavior** at prototype tier and can never prove production
rights. That is the gate working, not a defect (§8).

### 3.5 Machina Sports TV — priority 5

Provider-coupled and high value, but sequenced **after** WCI, Machina Media, shared
selectors and SportsClaw. Nothing found forces it earlier: it reads the WCI pod's
`worldcup:event` docs, so it inherits whatever WCI migrates to.

| System / repo | Files / symbols | Current shape / producer | Category | Prio | PR 3 action | Proof |
|---|---|---|---|---|---|---|
| `machina-sports-tv` | `agent-templates/machina-sports-tv/mappings/api-football-event-mapping.yml` (`iptc-api-football-event-mapping`) | Its **own** copy of the API-Football → legacy IPTC mapping, `@id: urn:apifootball:sport_event:{id}`, non-official `sport:` IRI, `schema:startDate`, `sport:status`, `sport:competition`/`sport:season` | provider-coupled + legacy canonical | **5** | Replace with the shared canonical adapter; stop maintaining a fork of the mapping | high |
| `machina-sports-tv` | `mappings/api-football-event-teams-stats.yml`, `mappings/events-summary.yml` | Fork of the shared summary selector, with its own live-vs-full-time score precedence comment | projection-only (forked) | 5 | Collapse into the shared `event_view` selector | high |
| `machina-sports-tv` | `operator-sink/src/worldcup.ts` → `interface WcLiveMatch`, `mapPodEventDoc(d)` (l. 635), and the sibling mapper at l. ~597 | TypeScript model built straight off legacy keys: `v["sport:status"]`, `v["sport:competitors"]` filtered on `c["sport:qualifier"]`, `v["sport:score"]["sport:liveHomeScore"] ?? ["sport:homeScore"]`, `v["sport:venue"].name`, `v["sport:minutesElapsed"]` | legacy canonical (typed) | 5 | Regenerate the interface from `event_view`; the live/full-time score precedence becomes a canonical `event.score` concern | high |
| `machina-sports-tv` | `operator-sink/src/football.ts` → `FootballResult`, shells `python -m sports_skills football …` | Native `sports-skills` payload as a *correction* source for missing pod scores | provider-coupled | 5 | Once both sides are canonical this fallback becomes a same-shape merge instead of a second parser | high |
| `machina-sports-tv` | `workflows/ingest-*.yml` (10 ingest workflows incl. `ingest-sport-events.yml`, `ingest-football-state.yml`), `connectors/api-football.{yml,json}` | Independent API-Football ingest path | provider-coupled | 5 | Adapter swap, same pattern as the in-repo connectors | medium |

### 3.6 Customer-specific — later lane, evidence-gated

**These are not rewritten for purity.** Each row records only coupling that was actually
found. The lane exists so PR 3 can state what would break, not so PR 3 can change it.

| System / repo | Files / symbols | Current shape / producer | Category | Prio | PR 3 action | Proof |
|---|---|---|---|---|---|---|
| `dazn-templates` | 23 code files (`.yml`/`.py`) match the legacy-shape pattern — incl. `agent-templates/dazn-coverage/event-{preview,recap,narration}/workflows/{selector,update,executor}.yml`, `dazn-predictions/workflows/{generate-by-round,auto-settle-checkin,test-player-selection}.yml`, `dazn-predictions/scripts/{format-event-summary,format-prediction-package}.py`, `dazn-coverage/event-preview/scripts/format_slack_messages.py`, plus `docs/examples/sport-event.json` | Legacy `sport:` event reads: run-of-show, predictions, coverage | customer-specific (legacy canonical) | **later lane** | Migration/removal plan only. No code change in PR 3 | medium |
| `entain-templates` | 17 code files match — incl. `agent-templates/blog-br/soccer-preview/workflows/{dispatch,consumer,preview,stories,reasoning,player}.yml`, `blog-br/tools/soccer/tallysight-widgets.yml`, `entain-predictions/workflows/{predictions-find-upcoming,predictions-forecast}.yml`, `entain-predictions/agents/predictions-scheduler-{nba,nfl,mlb,wc}.yml`, `entain-predictions/scripts/{extract-event-data,extract-team-stats}.py`, `configs/setup-{dev,prd}.yml` | Legacy `sport:` event reads; SportingBOT surfaces | customer-specific (legacy canonical) | later lane | Migration/removal plan only | medium |
| `SINCH` (Globo World Cup) | `sinch-templates/globo/mappings/worldcup-match.yml` (`worldcup-match`, `worldcup-fixture-resolver`), `workflows/worldcup-postmatch-dispatch.yml`, `workflows/worldcup-chat.yml`, `prompts/worldcup-{postmatch-summary,match-reasoning,match-response,audio-rewriter}.yml` | **Raw API-Football**, not IPTC at all: `event.fixture.{id,status.short,status.elapsed,date,venue.*}`, `event.league.{id,name,season,round}`, `event.teams.{home,away}.{id,name}`, `event.goals.{home,away}`; then `get-fixtures/events` | customer-specific (**provider-coupled**) | later lane | Migration/removal plan only. Note: this is *direct* provider coupling, so it is the customer surface a provider change would break first | high |
| `sportingbot-web` | Legacy-shape pattern over code: **0 matches**. Provider coupling exists in `lib/types/fixtures.ts`, `lib/api/competition-season.ts`, `components/competition/upcoming-fixtures.tsx`, `app/copa-mundo/wc-teams.ts`, `public/copa-rumo-ao-hexa/lib/api.js`, plus `fan-engagement-agent/connectors/sportradar-nfl-v7.yml` and `agent-templates/nba-grok-chat/connectors/sportradar-nba-v8.yml`. One docs hit: `docs/troubleshooting/preview-parser-fix.md` | customer-specific; the typed surfaces are **frontend**, an explicit non-goal (§11) | later lane | Record only. The two agent-template connectors are the only non-frontend rows | medium |
| `ADIDAS` | Legacy-shape pattern: **0 matches**. Searched, nothing found | no coupling on current evidence | — | **No PR 3 change** | medium |

### 3.7 Dead / unused / stale — excluded from all counts

| Surface | Why excluded | Proof |
|---|---|---|
| The two sibling local worktree checkouts for the PR 1 and PR 2 lanes, and this worktree | All three share one `.git` common dir with `machina-templates`. They are PR 1 / PR 2 / PR 3 worktrees of **one** repository | `git worktree list` in `machina-templates` |
| `sportsclaw-pr136`, `sportsclaw-pr137`, `sportsclaw-pr138`, `sportsclaw-v0292` | Registered worktrees of the single `sportsclaw` repo (plus two `prunable` temp worktrees) | `git worktree list` in `sportsclaw` |
| `sports-skills-machina-schema` | Checkout of the `sports-skills` PR 2 branch, superseded by `origin/main` @ `944c14e` | branch `feat/machina-sports-schema` |
| `agent-templates/world-cup-intelligence/**/__pycache__/*.pyc` | Byte-compiled output of a file already counted | matched only by content |
| Generated JS / `.d.ts` / `.js.map` under `sportsclaw` | Build output of already-counted TypeScript | 11 files, none in `src/` |
| Prose hits — WCI `docs/*.md`, `_folders.yml`, `machina-sports-tv/docs/**`, `.superpowers/**`, `dazn-templates/*.md`, `entain-templates/.claude/**` and `commands/*.md` | Documentation describing the shape, not code reading it | inspected |

**No surface is counted twice.** Cross-repo rows are attributed to the source-of-truth
repository only.

---

## 4. Core PR 3 migration order

1. **World Cup Intelligence.** Largest single concentration of legacy coupling (14
   generated rows + 13 uncounted workflows), and the only place that *mints* the obsolete
   shape in Python (`mint_event_identity`). It also owns the docs that
   `sportsclaw-machina` and `machina-sports-tv` both read, so migrating it unblocks two
   downstream systems.
2. **Machina Media.** A second self-described canonical model. It must be **removed**, not
   reconciled, and it is small enough (1 mapping, 1 sync workflow, 1 direct consumer) that
   removing it early prevents anyone building on it during PR 3.
3. **Shared selectors and summaries.** `iptc-events-summary` and friends, then
   assistant-tools, coverage-tools, Kalshi, and the 36 provider connector workflows. Highest
   row count, most mechanical, but blocked on the storage-predicate question (§10).
4. **SportsClaw.** Consumes the contract. Cheapest code change (the bridge already forwards
   args) and the clearest statement of the boundary: a consumer that validates and gates but
   owns nothing.
5. **Machina Sports TV**, then **proven customer-specific consumers** as a separate,
   deferred lane.

Ordering rationale: **producers before readers, shared before local, owners before
consumers.** Nothing in the evidence forces a different order — Machina Sports TV reads
WCI's output, so it cannot lead; SportsClaw reads `sports-skills`, which is already
canonical, so it can move at any time and is placed where its proof is most useful.

---

## 5. Shared canonical access seam — requirements

One seam, built first, before any consumer is touched.

1. **A stable resolver.** `resolve-canonical-event` (name provisional) taking
   `{event_urn | provider + provider_event_id}` and returning the
   `machina_sports_schema` envelope. Every consumer in §3 reaches canonical data through
   this and only this. `worldcup-get-iptc-event-context.yml` is its first caller and
   already has the right signature (`event_urn` / `provider_event_id` / `provider`).
2. **Envelope validation at the seam, not at each consumer.** Reject anything that is not
   `schema_version: machina-sports-schema/1` + `profile: machina-iptc-profile/1.1`.
   RFC 002 §9: `canonical_envelope` raises `ValueError` on an invalid observation, so an
   envelope that reaches a consumer has already been validated once; the seam must not
   weaken that by constructing envelopes by hand.
3. **`event_view` is the default.** Application-facing consumers get `event_view`. This is
   what almost every row in §3 actually needs — `worldcup-iptc-event-to-api-response.yml`
   and `iptc-events-summary` are both hand-rolled `event_view`s already.
4. **`sport_schema_graph` is opt-in.** Requested only by graph/interchange consumers.
   No consumer in §3 needs it today.
5. **Capabilities, rights and provenance travel with either path.** They are envelope
   siblings of `event_view` and `sport_schema_graph`, so serving a projection must not
   strip them. A projection without its rights block is an unlicensed payload wearing a
   licensed one's shape.
6. **Fail closed on required capabilities.** The seam calls
   `check_compatibility(capabilities, requires=…, optional=…)` with the consumer's own
   declaration and refuses when `compatible` is false — including on `unknown_capabilities`,
   which is the whole point of the fails-closed rule in RFC 002 §8.
7. **Rights gate at the seam.** `rights_findings(envelope, consumer_tier=…)` runs before the
   consumer sees anything. A `production` consumer served a `prototype_only` envelope is
   refused, never downgraded.
8. **No provider field crosses the boundary.** Above the seam there is no `fixture.id`, no
   `sport:qualifier`, no `FT`/`NS`/`closed` status string. Provider identity survives only
   as `provider_ids` and `provenance`. The Kalshi `$nin: ['Played','closed','ended','FT']`
   filter is the current best example of what this rule deletes.

---

## 6. Consumer capability declarations

Using the **existing** dotted names from `ALL_CAPABILITIES` — PR 3 declares, it does not
extend.

**WCI match preview** — needs the fixture, both sides and a kickoff time; a score is
optional because a preview runs pre-match; a forecast and market snapshot are separate
documents, not capabilities.

```yaml
requires:
  - event.identity
  - event.competition
  - event.participants
  - event.start_time
  - event.status
  - provenance
optional:
  - event.score
  - event.lineups
```

**Machina Media postgame recap** — a recap is meaningless without a final score and result,
so those are required, not optional; player statistics and play-by-play enrich it.

```yaml
requires:
  - event.identity
  - event.participants
  - event.status
  - event.score
  - event.result
  - provenance
optional:
  - event.actions
  - event.play_by_play
  - participant.player_statistics
```

Two rules for every other declaration: **`provenance` is always required** (an
unattributed fact is not usable editorially), and a capability goes in `requires` only if
the consumer would produce something *wrong* without it — a consumer that would merely
produce something *thinner* declares it `optional`. Over-declaring `requires` turns the
fails-closed gate into an outage.

---

## 7. Source-of-truth vs. stale — how double counting was avoided

Every candidate directory was resolved to a repository before being counted:
`git rev-parse --git-common-dir` for shared worktrees, `git worktree list` for
registrations, and branch/ref inspection for stale checkouts. The result is §3.7. Four
`sportsclaw-*` directories, two sibling PR-lane worktree directories, this worktree, and
`sports-skills-machina-schema` collapse to **three** repositories: `sportsclaw`,
`machina-templates`, `sports-skills`. Generated JS, `.d.ts`, `.map` and `__pycache__`
artefacts are excluded on the same principle: they are a second copy of a counted source.

---

## 8. Provider substitution acceptance path

**Representative flow: `agent-templates/world-cup-intelligence/workflows/worldcup-match-preview.yml`.**

Chosen on evidence, not convenience. It is a real production workflow; it reads exactly one
event document (`load-event`, filtering `name: 'worldcup:event'` on `value._id`); its
downstream — grounded research, the `worldcup-match-preview` prompt, and the
`worldcup:skill-match-preview` cache write — never touches a provider field. So the
provider dependency is concentrated in one task, which is what makes substitution
demonstrable rather than asserted. The alternative candidates were rejected:
`worldcup-get-iptc-event-context.yml` is a thin lookup with no downstream to hold constant,
and `worldcup-match-recap.yml` needs a completed match and therefore a narrower fixture set.

**Acceptance criteria.**

1. **Downstream workflow code is identical across providers.** After the one-time change
   that repoints `load-event` at the seam, the prompt task, the cache write, the outputs
   block and the freshness logic are byte-identical for every provider run. The only
   difference between runs is configuration: which provider the seam resolves.
2. **Same sanitized fixture, three providers.** One equivalent match resolved via
   `sports-skills` (ESPN), API-Football, and Sportradar, each through its adapter —
   `sports_skills.canonical.adapters.football`, `tools/iptc/canonical/adapters/api_football.py`,
   `tools/iptc/canonical/adapters/sportradar_soccer.py`.
3. **Configuration-only changes.** Provider selection is a parameter. No task added,
   removed or reordered; no field path edited per provider.
4. **Capability report drives behavior, not a provider name.** Where providers differ, the
   workflow reacts to `capabilities`, never to `provenance.provider`.
5. **Rights gate observed.** The run records the tier it asked for and what the gate
   answered.

**What this proves, stated precisely.** The corrected fixtures under
`tools/iptc/fixtures/corrected/` are synthetic. They prove **substitution of shape and
behavior**: that three providers produce one envelope a single consumer reads unchanged.
They do **not** prove live provider parity — no live API is called — and they do **not**
prove rights. On rights the evidence points the other way and should be reported that way:
`sports-skills` `_cli.py` documents that every envelope it emits is `open-public` /
`prototype_only`, and the gate refuses a `production` consumer *before* the provider call.
So the `sports-skills` leg of the proof is valid at **prototype** tier only. A production-tier
substitution claim requires the licensed adapters and a live authorized sandbox (§10).
Saying otherwise would be the exact false conformance claim the rights block exists to stop.

---

## 9. Legacy removal plan — grouping

**Group A — mint and store (blocking).** `mint_event_identity` and
`worldcup-ingest-fixtures.yml`. Until the producer emits canonical, every reader migration
is a translation layer. Removal target: the obsolete `@context` binding
`https://www.sportschema.org/ontologies/sport#` and the hand-built `sport:Venue` /
`sport:competitors` blocks.

**Group B — duplicate models.** `map-normalize-event.yml` (Machina Media) and
`iptc-api-football-event-mapping` + `events-summary.yml` (Machina Sports TV's forks).
Delete, do not reconcile.

**Group C — hand-rolled projections.** `worldcup-iptc-event-to-api-response.yml`,
`iptc-event-selector`, `iptc-events-summary`, `coverage-iptc-events-summary`,
`mapPodEventDoc`. Each is an `event_view` someone wrote by hand; each collapses into one.

**Group D — provider producers.** The 36 connector rows. Mechanical adapter swaps, done
last within the core lane because they are the least risky and benefit from the seam being
settled.

**Group E — storage predicates.** `value.schema:startDate`, `value.sport:status`,
`value.sport:competition.sport:season.@id`, `name: 'sport:Event'`,
`name: 'worldcup:event'`. **Not a code change** — a document-store migration. Sequenced
explicitly because it is the one item in §9 that can strand a half-migrated system.

### Deferred / customer lane — explicitly out of the core PR 3 sequence

`dazn-templates` (23 files), `entain-templates` (17 files), `SINCH` Globo (7 files),
`sportingbot-web` (2 non-frontend connector files). This lane produces a **migration and
removal plan** with per-customer sequencing, not code changes. `ADIDAS` has no entry: the
search returned nothing, and no PR 3 change is recommended on current evidence.
`sportsclaw-machina` sits here too — `src/prompt-builder.ts` names legacy `worldcup:event`,
`value.sport:venue.name`, `value.schema:startDate` and `value.name` in its MCP routing
guidance, and routes World Cup traffic to pod workflows/documents while sending all other
sports to native `sports-skills`. It is a **customer/product-specific bridge consumer** of
the pod contract. It follows WCI's migration; it is not a canonical owner and must not be
made one.

---

## 10. Open questions and blockers

1. **Full authorized live sandbox import.** Every substitution artefact available today is
   synthetic. A production-tier parity claim needs an authorized sandbox with real
   API-Football and Sportradar credentials and an explicit rights decision per provider.
   **Blocker for §8 criterion 5 at production tier.** Not a blocker for the shape proof.
2. **Runtime packaging and access for the canonical adapters.** `tools/iptc/canonical/**`
   is repository tooling. Workflow tasks cannot import `tools.*` — RFC 002 §10 already
   states the vendoring constraint and `sports-skills` already vendors byte-exact. How the
   Machina workflow runtime reaches the adapters (a pyscript connector, a vendored package,
   a service) is **undecided and blocks the seam**, which blocks everything in §4.
3. **Storage predicates (Group E).** Consumers filter on `value.schema:startDate`,
   `value.sport:status` and `name: 'sport:Event'` at the document store. Does the stored
   document become canonical, or does an alias/index layer keep legacy predicates working
   during migration? Different answers give different migration orders inside group 3.
4. **`worldcup:event` document name.** WCI's coupling is as much to the *document name* as
   to field paths. Renaming breaks `sportsclaw-machina` prompt guidance and Machina Sports
   TV's `mapPodEventDoc` simultaneously. Keep the name and change the value shape, or
   version the name?
5. **Canonical coverage of non-event surfaces.** `sports-skills` canonical mode allowlists
   exactly two commands (`football get_event_summary`, `football get_daily_schedule`).
   WCI standings, injuries, squads and bracket workflows have no canonical counterpart.
   Do they stay legacy through PR 3, or does PR 3 scope grow?
6. **Inventory generator gap (Observation 2).** 13 WCI workflows are legacy-coupled and
   uncounted. Fixing `tools/iptc/inventory.py` changes the headline 75. Decide whether the
   "zero known legacy consumer breakages" claim is scoped to 75 or to the corrected number
   before the claim is made.
7. **RFC 002 §8 vs. `NOT_EXPRESSIBLE` (Observation 4).** Prose says five, the constant
   derives four. Cosmetic, but consumers read the RFC to author `requires`.

---

## 11. Explicit non-goals

PR 3 does **not**:

- change the canonical schema, its terms, its capability names, its envelope, or the
  rights model — the canonical layer is frozen per the internal design-decision record,
  except bugs and standards/provider corrections;
- touch Experience or any other adjacent product surface;
- rewrite customer repositories for purity — `dazn-templates`, `entain-templates`,
  `SINCH`, `sportingbot-web` and `sportsclaw-machina` get a plan, not a refactor;
- change any frontend;
- introduce a graph database, or make `sport_schema_graph` a default output;
- make SportsClaw or any other consumer an owner of canonical terms;
- assert live provider parity or production rights from synthetic fixtures.
