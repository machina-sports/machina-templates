# World Cup Intelligence — MongoDB indexes + TTL

Version-controlled, idempotent index/TTL setup for the pod's `world-cup-2`
database. Pattern adopted from `entain-templates/infrastructure/mongodb`
(SportingBOT production).

Run: `./apply.sh` (defaults: namespace `tenant-machina-drops`, db `world-cup-2`,
shared mongo pod `tenant-machina-drops-databases`, container `mongodb`).

## Why
The `document` collection (~1,900 docs and growing) had only the default `_id_`
index — every `search_documents` (resolve, reads, market-movers, market search)
was a full collection scan. These indexes turn the hot paths into `IXSCAN`.

## Indexes (on `document`, all `name`-prefixed)
| Index | Serves |
|-------|--------|
| `idx_name_value_id` | reads/crosswalk by URN + `^`-anchored `_id` regex |
| `idx_name_pid_{apifootball,sportradar,opta,entain,espn}` | `worldcup-resolve` (`$or` per provider) + reads |
| `idx_name_competition_slug` | competition-slug filters |
| `idx_name_ts` | `worldcup-market-movers` snapshot ts range |
| `idx_name_related_team_urns` | market → team |
| `idx_name_event_urn` | market → event |

## TTL
`ttl_market_snapshot_30d` — **partial** TTL on `created`, scoped to
`name: "worldcup:market-snapshot"` (30-day retention for the price-history
time series). Partial scoping is mandatory: the `document` collection is shared,
so an unscoped TTL would expire identity/event/market docs too.

## Execution-log retention (CronJob)
Execution-log collections (`workflow_tasks`, `workflow_run`, `agent_run`) store
`timestamp` as a **string**, not a BSON Date, so Mongo TTL cannot apply. They are
pruned by `execution-log-cleanup-cronjob.yaml` — a k8s CronJob (daily 04:30 UTC)
that runs `mongosh` against the `world-cup-2` db and `deleteMany`s rows older than
`RETENTION_DAYS` (default 14) via lexicographic ISO-string comparison. The
doc-store API only reaches the `document` collection, so this is a CronJob rather
than a workflow. Apply: `kubectl apply -f execution-log-cleanup-cronjob.yaml`.
