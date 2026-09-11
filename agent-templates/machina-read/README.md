# Native Machina Read

## Current v4 single-story format

The production producer and reader request `edition_format: 4`. Each generated
edition contains one sport and one concrete story. The producer builds a bounded,
breadth-preserving shortlist of coherent candidate packets across every eligible
sport it can fit. The existing single Gemini call chooses the strongest supported
current development using newsworthiness, evidence, stakes and novelty. There is
no sport rotation, fixed sport priority or requirement to spread editions across
sports. The same sport may lead on successive days.

V4 is the transformer default so an omitted format cannot silently invoke the old
cross-sport mashup. Explicit `edition_format: 3` still reads or assembles legacy v3
records for compatibility. Each v4 candidate has one non-market anchor and may
carry one conservatively matched same-subject market; markets are optional and do
not have to be cited. Writing uses self-contained facts and optional earned humor,
not compulsory jokes or comparisons. Full-article enrichment is not automated for
every source; editor-reviewed posts must be labelled as such by consumers.

The sections below describe the discovery lanes and the legacy v3 behavior where
they explicitly refer to cross-sport editions. The v4 selection rules above govern
the current producer. Scheduler ownership and evidence/publication gates remain.

A native workflow package, not a standalone application or agent service. There
is no shadow collector, local runner or background service anywhere in it.

## Install and ownership

The target pod needs the existing `sports-skills` and `machina-ai` connectors.
Import `connectors/machina-read-multisport`, then this package's workflows.
`connectors/machina-read-transform` remains in the repository, with its own
tests, for the previous v2 MLB pipeline; no v3 workflow calls it, so importing it
is optional. Credentials remain runtime-owned. Do not update unrelated connectors
or routing policy as part of installation.

- `machina-read-produce-daily`: native broad collection, deterministic pure
  compaction and shortlisting, one Gemini selection/writing task, validation and
  native v4 document save.
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
| Polymarket | `sports-skills invoke_polymarket get_sports_events` |
| Kalshi | `sports-skills invoke_kalshi get_markets` on the `KXMLB` baseball series |
| News | `sports-skills invoke_news fetch_items` once per supported sport (nine calls) |

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

Market sport is classified only from explicit league or competition tokens in the
provider's own title, slug and question. A requested sport label is never
trusted, and a market matching two sports or none is skipped rather than guessed.
Polymarket contracts must remain open for more than 24 hours at collection so a
daily edition cannot expire between scheduled checks. Near-term game markets
are deliberately excluded from this daily surface, not presented as live odds.
Contracts that are closed, expired, stale (quote older than 24 hours), illiquid,
or priced with a boolean, non-finite or out-of-range value are dropped, which
also removes resolved contracts masquerading as active. Quotes are rendered from
the provider value with `Decimal`, never by model arithmetic, and the provider
quote time is carried separately from our observation time. The Kalshi lane is
deliberately the proven baseball title series only; no wider Kalshi adapter and
no identity join to other sports is claimed. No trade, wallet or order command is
used anywhere.

News stays headline evidence: RFC publication dates control recency, headlines
older than 48 hours or dated in the future are rejected, and routine "how to
watch", TV-listing, betting-promo, bonus and casino headlines are filtered out.
Full articles are not retrieved and nothing inside them is verified.

## Shortlisting and coverage

The v4 assembler admits concrete results, fixtures and reported headlines as
anchors; a static market quote cannot form a candidate by itself. It takes one
candidate per eligible sport before considering a second from any sport, up to two
per sport and 12 total, while enforcing the 14,000-character evidence budget and
24,000-byte prompt budget. This is deterministic capacity control, not a local
editorial score: feed volume cannot fill the shortlist before other represented
sports get a candidate, and the model makes the editorial choice. A same-subject
market can be attached only after anchor breadth is secured and only if budgets
still permit it. Full scan coverage remains recorded separately.

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

Editorial voice: a short, engaging factual account that names the central athlete
or team, what happened, the competition and why it matters for a non-fan. A brief
dry observational line is optional when the facts earn it. Humour is commentary
and never supplies a fact; forced analogies, impersonation, injury jokes, cruelty
and fabricated quotes or incidents are prohibited. All provider text is treated
as untrusted data and never as instructions.

The only model route is `machina-ai`, Vertex AI, `gemini-3.5-flash-lite`, with
one call per generated edition and none at all on a cache hit. Do not substitute
another model without approval.

Before storage, the pure v4 validator requires: a `stop` finish reason with no
tool calls, the exact JSON field set, a known `selectedAnchorSourceId`, the anchor
cited by the headline/body, bounded text lengths, and every citation bound to that
one candidate packet. It rejects cross-candidate mixing even within the same
sport, unbound sport references, unknown or non-string source IDs, and numbers not
present in the source cited by that fragment. Identifiers and URLs cannot launder
a figure. A supplied related market is not mandatory. Selection metadata is
stripped after validation, leaving the unchanged website v4 story shape. Only
cited sources and the selected sport are retained. These checks do not prove model
editorial quality or every semantic claim; consequential claims still need review.

`docs/machina-read-v3-contract.md` holds the fixed v3 contract shared with the
website, including the URL allowlist and the native projection that strips only
`publicApproved`, `marketSnapshots` and `coverage`. There is no `teams` field in
v3.

## Cache and publication

A same-day, admitted, unexpired v4 edition is reused and every provider and model
task is skipped. This is sequential cache reuse, not a claim of race-safe global
once-per-day execution. Because the production cache probe and reader both require
`schemaVersion: 4`, older editions cannot be served by this pipeline. Explicit v3
cache validation remains available only to legacy callers.
Failed validation stores no replacement and does not extend an old expiry; reads
never renew a TTL or rewrite a provider timestamp.

The transformer defaults to private results; the producer explicitly supplies
boolean `publish_public: True` after validation, and anything else, including the
string `"True"`, stays private. Reads select admitted editions only.

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
python scripts/check-machina-ai-policy.py agent-templates/machina-read/workflows/machina-read-produce-daily.yml
```

Tests use synthetic fixtures built to observed provider shapes; no real payload,
credential or execution artefact is committed. Passing tests are not evidence of
a successful live run. Verify the imported definitions, one complete execution,
the exact saved document and a cache-only second execution on the pod before
claiming runtime success.
