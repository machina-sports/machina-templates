# Native Machina Read

## Current v4 single-story format

The production producer and reader request `edition_format: 4`. Each generated
edition contains one sport and one concrete story. The producer builds a bounded,
breadth-preserving shortlist across every eligible sport it can fit. A first Gemini
call ranks up to three full-article candidates using newsworthiness, evidence,
stakes and novelty. Pure transforms then resolve names to provider IDs from native
catalogs and schedules, dispatch bounded Sports Skills research, and select the
first candidate with quantitative context. A second Gemini call writes only from
that researched packet. There is no sport rotation or fixed sport priority.

V4 is the transformer default so an omitted format cannot silently invoke the old
cross-sport mashup. Explicit `edition_format: 3` still reads or assembles legacy v3
records for compatibility. Discovery can contain `article` or `event` anchors, but
the research planner admits only a full `article` anchor for a new edition. The
final packet contains that article, one provider-scoped `statistic`, and at most
one exactly matched market. Markets are optional and do not have to be cited. RSS
headlines cannot anchor a v4 edition. Writing uses self-contained facts and
optional earned humor, not compulsory jokes or comparisons. Automated reporting
never sets `editorReviewed`; that remains an independent consumer-owned signal.

The sections below describe the discovery lanes and the legacy v3 behavior where
they explicitly refer to cross-sport editions. The v4 selection rules above govern
the current producer. Scheduler ownership and evidence/publication gates remain.

A native workflow package, not a standalone application or agent service. There
is no shadow collector, local runner or background service anywhere in it.

## Install and ownership

The target pod needs the existing `sports-skills` and `machina-ai` connectors.
Import `connectors/machina-read-reporting` and `connectors/machina-read-multisport`,
then this package's workflows.
`connectors/machina-read-transform` remains in the repository, with its own
tests, for the previous v2 MLB pipeline; no v3 workflow calls it, so importing it
is optional. Credentials remain runtime-owned. Do not update unrelated connectors
or routing policy as part of installation.

- `machina-read-produce-daily`: native broad collection, deterministic pure
  compaction and shortlisting, Gemini selection, targeted native research, Gemini
  writing, validation and native v4 document save.
- `machina-read-get-latest`: native v4 document retrieval, admission and expiry
  check only. No source calls or generation.
- `machina-read-source-probe`: read-only installation canary for the older MLB
  lanes; not the daily producer.

`machina-read-multisport` contains only pure domain logic. It performs no
network, SDK, model, database, filesystem or scheduler operations, and it never
raises out of a task: bad provider input becomes an `unavailable` envelope. All
external work belongs to native workflow tasks.

## Collection

One producer run, on a cache miss, makes at most these calls, each with
`continue_on_error: true` and each compacted by its own pure task immediately
afterwards so raw feeds never accumulate into one oversized persisted output:

| Lane | Connector call |
| --- | --- |
| Cross-sport schedule | `sports-skills invoke_markets get_sport_schedule` for today |
| Football (soccer) | `sports-skills invoke_football get_daily_schedule` for today |
| Tennis | `sports-skills invoke_tennis get_scoreboard` for `atp` and `wta` |
| News | `sports-skills invoke_news fetch_items` once per supported sport (nine calls) |
| Full reporting | `machina-read-reporting invoke_reporting` once per supported sport (nine fixed ESPN paths) |

After selection, at most three choices enter research. The pure planner emits at
most 12 discovery slots and 18 target slots. Native `sports-skills` tasks dispatch
only allowlisted read commands through the sport-appropriate connector command:
`invoke_football`, `invoke_nfl`, `invoke_mlb`, `invoke_nba`, `invoke_nhl`,
`invoke_tennis`, `invoke_golf`, `invoke_f1`, `invoke_cricket`, or
`invoke_markets`. Team IDs come from `get_teams`/`search_team`; event IDs come
from dated scoreboards or schedules. Model output never supplies an ID.

Team-sport research can include game summaries, team season stats, standings,
schedule/form and injuries. Tennis, golf, motorsport and cricket use their own
scoreboard, ranking, leaderboard, race or series commands. A candidate without a
genuinely quantitative, subject-bound response is skipped in favor of the next
ranked choice. If none qualifies, no replacement is stored.

Every lane is filtered on its own observed timestamps, not on transport success.
The live all-sport schedule returns fixtures months ahead, so events outside a
recent-36h / upcoming-48h window are dropped, and rows with an unknown status or
a missing start time are rejected. That schedule feed carries no scores, so its
sources never state a result. A football fixture that is not `closed` is
described as unplayed: a provider placeholder of `0`-`0` is never reported as a
score. Tennis matches are taken from whole-tournament draws, so each match is
filtered on its own date and only completed matches with exactly one winner and
two known competitors are used; the provider result line and set scores are
preserved and no athlete identifier is invented.

Broad discovery does not collect a market buffet. Only after Gemini selects named
subjects does the workflow call `markets.search_entity` and `markets.match_markets`.
The pure join distrusts requested sport labels and accepts only an exact season or
next-fixture match. Boolean, non-finite and out-of-range prices are rejected. Quotes
are rendered from provider values with `Decimal`, never by model arithmetic. No
trade, wallet or order command is used anywhere.

RSS news stays headline evidence: RFC publication dates control recency, headlines
older than 48 hours or dated in the future are rejected, and routine "how to
watch", TV-listing, betting-promo, bonus and casino headlines are filtered out.
It cannot anchor a v4 edition. The dedicated reporting connector retrieves public
ESPN Story API records with fixed paths, no credentials, disabled proxies, no
redirects, a six-second timeout and a 262,144-byte response ceiling. Premium,
malformed, stale, future, unbound URL and bodyless records are dropped. HTML is
reduced to plain text, excluding `script`, `style` and `embed`, and bounded to
6,000 characters with explicit truncation awareness. See
`docs/machina-read-reporting-design.md`.

## Shortlisting and coverage

The v4 assembler discovers substantive articles, concrete results and fixtures;
a bare headline or static market quote cannot form a candidate. The subsequent
research planner requires a substantive article before any new edition. Within
each sport articles precede event evidence, without forcing the final editorial
choice. It takes one candidate per eligible sport before considering a second from
any sport, up to two per sport and 12 total, while enforcing a 30,000-character
candidate evidence budget and 40,000-byte prompt budget. This is deterministic
capacity control, not a local editorial score: feed volume cannot fill the
shortlist before other represented sports get a candidate, and the model makes
the editorial choice. Discovery markets do not become final evidence. Targeted
market searches run only after a subject has been resolved, and the final packet
adds no more than two contextual sources to its article. Full scan coverage remains
recorded separately.

The producer supplies up to seven admitted prior v4 editions. Sources with the
same normalized label and evidence text are omitted from the new shortlist, but a
sport is never penalized merely for appearing previously. A fixture that changes
from scheduled to final is new evidence even when its provider ID and URL stay the
same. If every concrete development is an exact repeat, generation fails with no
replacement rather than redating old evidence.

`coverage` records which sports produced usable recent evidence, which is not a
transport signal: a lane that answered but returned only off-season or
unverifiable rows is reported `unavailable`. No edition claims that every sport
played today.

Explicit v3 assembly retains its legacy round-robin cross-sport behavior, source
limits and Polymarket assignment for existing consumers. It is not the active
production path.

## Reasoning and output

Editorial voice: an 80-130-word factual account, within 900 characters, that names
the central athlete or team, what happened, the sport or competition and why it
matters for a non-fan, briefly unpacking insider jargon. A brief dry observational
reversal is optional when a verified detail earns it. Humour is commentary
and never supplies a fact; forced analogies, impersonation, injury jokes, cruelty
and fabricated quotes or incidents are prohibited. All provider text is treated
as untrusted data and never as instructions.

The only model route is `machina-ai`, Vertex AI, `gemini-3.5-flash-lite`, with
one bounded selection call and one writing call per generated edition, and no
model call at all on a cache hit. Do not substitute another model without approval.

The research wire contract is:

1. Selection returns `choices[]` with an exact article anchor ID, subject type,
   subject name, competition, and an exact team name for team sports. It never
   returns provider IDs.
2. `plan_research` validates those strings against the article and emits allowlisted
   discovery requests with stable request IDs.
3. `resolve_research` matches exact provider catalog names and dated schedules,
   then emits ID-bound target requests plus `search_entity` and `match_markets`.
4. `build_research_brief` accepts the first ranked choice with an article and a
   quantitative source. Its packet has at most three sources and a 24,000-byte prompt.
5. `finalize` binds every number to the source cited by that fragment and requires
   both article and statistic citations for researched v4 generation.

Market discovery examines the returned Kalshi and Polymarket lists separately.
The requested sport is not trusted: a season market must match exact subject,
competition and season, while a fixture market must match both scheduled teams and
the exact next-fixture date. Every retained quote includes named outcomes and an
observation timestamp. One quote never supports movement or a causal explanation.
Empty or malformed venue results become explicit gaps; no market is preferable to
an unrelated contract. ProphetX results may be reported by the SDK but are not part
of this two-venue publication contract.

Before storage, the pure researched-v4 validator requires: a `stop` finish reason with no
tool calls, the exact JSON field set, a known `selectedAnchorSourceId`, the anchor
cited by the headline/body, bounded text lengths, and every citation bound to that
one candidate packet. It rejects cross-candidate mixing even within the same
sport, unbound sport references, unknown or non-string source IDs, and numbers not
present in the source cited by that fragment. Identifiers and URLs cannot launder
a figure. Article and quantitative-statistic citations are mandatory; a supplied
related market is not. Unsupported price movement and causal language is rejected.
Selection metadata is stripped after validation, leaving the unchanged website v4 story shape. Only
cited sources and the selected sport are retained. These checks do not prove model
editorial quality or every semantic claim; consequential claims still need review.

`docs/machina-read-v3-contract.md` holds the fixed v3 contract shared with the
website, including the URL allowlist and the native projection that strips only
`publicApproved`, `marketSnapshots` and `coverage`. There is no `teams` field in
v3.

## Cache and publication

A same-day, admitted, unexpired v4 edition is reused and every provider and model
task is skipped unless the native workflow context supplies boolean
`force_refresh: true`. In the document task output, `$.get(...)` reads the document
response while `$.context.get(...)` reads workflow state; that exact boolean passes
an empty document list to the cache validator. Strings and other values do not
bypass the cache. This is sequential
cache reuse, not a claim of race-safe global once-per-day execution. Because the
production cache probe and reader both require `schemaVersion: 4`, older editions
cannot be served by this pipeline. Explicit v3 cache validation remains available
only to legacy callers.
Failed validation stores no replacement and does not extend an old expiry; reads
never renew a TTL or rewrite a provider timestamp.

The transformer defaults to private results. The producer's native
`publish_public` input defaults to boolean `True` for ordinary scheduled runs, but
only an exact boolean `True` reaches finalization as public. Boolean `False`,
strings and other values store a private edition, return it only as the `preview`
output and leave the public `edition` output empty. Reads and cache searches still
select only editions with boolean `publicApproved: True`.

Workflows retain draft definitions and the `machina-read-daily` agent ships
**inactive** with a disabled native `type: agent` job targeting itself, with
`interval: 43200` seconds. Fantasy's observed Celery Beat scheduler evaluates
`jobs.enabled`; the legacy `context.config-frequency` mechanism does not drive
that scheduler. Activation enables this job and the agent after deployment,
without starting a separate scheduler or restarting the pod. After verified activation it checks twice a day; healthy
same-day editions are reused, so normal generation is once per UTC day. Failed
refreshes may be retried on the next scheduled check, not continuously. This is
not a wall-clock cron promise.

Every completed producer check writes `machina-read-health` on both the cache and
the generation path, with an explicit healthy/failed state, the reason and a
timestamp, also exposed in workflow and agent output. These are native
operational records, not a claim that any external notification or alert channel
is configured. A source or storage outage can prevent a health write; platform
execution failures remain separate evidence.

## Checks

```
python -m pytest tests/test_machina_read_multisport.py tests/test_machina_read_single_story.py tests/test_machina_read_native.py -q
python -m pytest tests/test_machina_read_reporting.py tests/test_machina_read_context_engineering.py -q
python scripts/check-machina-ai-policy.py agent-templates/machina-read/workflows/machina-read-produce-daily.yml
python scripts/check-ai-command-inventory.py
```

Tests use synthetic fixtures built to observed provider shapes; no real payload,
credential or execution artefact is committed. Passing tests and read-only SDK
sampling are not evidence of a successful native workflow run. The remaining gate
is to import the definitions, execute one private forced preview, inspect its exact
saved document and evidence, then execute a public run and a cache-only second run.
Activation and the disabled job must remain unchanged during that gate.
