# Native Machina Read

A native workflow package, not a standalone application or agent service. There
is no shadow collector, local runner or background service anywhere in it.

## Install and ownership

The target pod needs the existing `sports-skills` and `machina-ai` connectors.
Import `connectors/machina-read-multisport`, then this package's workflows.
`connectors/machina-read-transform` remains in the repository, with its own
tests, for the previous v2 MLB pipeline; no v3 workflow calls it, so importing it
is optional. Credentials remain runtime-owned. Do not update unrelated connectors
or routing policy as part of installation.

- `machina-read-produce-daily`: native multi-sport collection, deterministic pure
  compaction, one Gemini task, validation and native document save (v3).
- `machina-read-get-latest`: native v3 document retrieval, admission and expiry
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

## Balancing and coverage

The assembler round-robins candidates across sports, preferring completed
sporting evidence, then markets, then fixtures, then headlines, so neither
alphabetical order nor a high-volume feed decides the edition. Every edition must
carry at least two sports and at most 24 sources within a bounded text budget.
`coverage` records which sports produced usable recent evidence, which is not a
transport signal: a lane that answered but returned only off-season or
unverifiable rows is reported `unavailable`. No edition claims that every sport
played today.

## Reasoning and output

Editorial voice: a short witty hook built on a contrast between two sports, a
brief wry line where it fits, then two or three points that go from cited
evidence to a sporting implication to an honest caveat. Humour is commentary and
never supplies a fact; injuries, illness, tragedy and personal traits are not
joke material, and fabricated quotes or incidents are prohibited. All provider
text is treated as untrusted data and never as instructions.

The only model route is `machina-ai`, Vertex AI, `gemini-3.5-flash-lite`, with
one call per generated edition and none at all on a cache hit. Do not substitute
another model without approval.

Before storage, the pure validator requires: a `stop` finish reason with no tool
calls, the exact JSON field set, bounded text lengths, citations that all
resolve, cited sources spanning at least two sports, a market citation whenever
market evidence exists, no sport token in the prose that was not cited, and every
number in a fragment present in the sources that same fragment cites, with the
permitted pool built from source prose only so identifiers and URLs cannot
launder a figure. Only cited sources and their sports are retained. These are
deterministic checks, not a semantic guarantee for every possible model claim:
review consequential claims, and never read movement, momentum or trader emotion
into a single price snapshot. Jokes are not validated mechanically.

`docs/machina-read-v3-contract.md` holds the fixed v3 contract shared with the
website, including the URL allowlist and the native projection that strips only
`publicApproved`, `marketSnapshots` and `coverage`. There is no `teams` field in
v3.

## Cache and publication

A same-day, admitted, unexpired v3 edition is reused and every provider and model
task is skipped. This is sequential cache reuse, not a claim of race-safe global
once-per-day execution. Because the cache probe and the reader both require
`schemaVersion: 3`, a stored v2 MLB edition can never be served by this pipeline.
Failed validation stores no replacement and does not extend an old expiry; reads
never renew a TTL or rewrite a provider timestamp.

The transformer defaults to private results; the producer explicitly supplies
boolean `publish_public: True` after validation, and anything else, including the
string `"True"`, stays private. Reads select admitted editions only.

Workflows retain draft definitions and the `machina-read-daily` agent ships
**inactive** with `jobs: []` and the platform's established
`context.config-frequency: 720` mechanism, not a cron entry. The parent activates
it after deployment. After verified activation it checks twice a day; healthy
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
python -m pytest tests/test_machina_read_multisport.py tests/test_machina_read_native.py -q
python scripts/check-machina-ai-policy.py agent-templates/machina-read/workflows/machina-read-produce-daily.yml
```

Tests use synthetic fixtures built to observed provider shapes; no real payload,
credential or execution artefact is committed. Passing tests are not evidence of
a successful live run. Verify the imported definitions, one complete execution,
the exact saved document and a cache-only second execution on the pod before
claiming runtime success.
