#!/usr/bin/env bash
# Version-controlled MongoDB indexes + TTL for the World Cup Intelligence pod.
# Idempotent: createIndex is a no-op when the index already exists.
# Modeled on entain-templates/infrastructure/mongodb (SportingBOT production).
#
# Usage: ./apply.sh [namespace] [db-pod] [database]
set -euo pipefail
NS="${1:-tenant-machina-drops}"
DB="${3:-world-cup-2}"
POD="${2:-$(kubectl -n "$NS" get pods -o name | grep -m1 -- '-databases' | grep -v world-cup | sed 's#pod/##')}"
# Default to the shared tenant mongo pod if not given:
POD="${POD:-$(kubectl -n "$NS" get pods -o name | grep -m1 'tenant-machina-drops-databases' | sed 's#pod/##')}"

echo "namespace=$NS pod=$POD db=$DB"

kubectl -n "$NS" exec "$POD" -c mongodb -- mongosh "$DB" --quiet --eval '
const r=[];
function ci(keys,name,opts){ try{ db.document.createIndex(keys, Object.assign({name:name}, opts||{})); r.push("OK   "+name);}catch(e){ r.push("ERR  "+name+": "+e.codeName);} }
// Performance indexes — every read filters by `name`, so all are name-prefixed.
ci({name:1,"value._id":1},"idx_name_value_id");                                  // reads/crosswalk by URN (+ ^anchored regex)
ci({name:1,"value.provider_ids.api_football":1},"idx_name_pid_apifootball");     // resolve + provider_event_id reads
ci({name:1,"value.provider_ids.sportradar":1},"idx_name_pid_sportradar");        // resolve
ci({name:1,"value.provider_ids.opta":1},"idx_name_pid_opta");                    // resolve
ci({name:1,"value.provider_ids.entain":1},"idx_name_pid_entain");                // resolve
ci({name:1,"value.provider_ids.espn":1},"idx_name_pid_espn");                    // resolve
ci({name:1,"value.machina_competition_slug":1},"idx_name_competition_slug");     // competition filters
ci({name:1,"value.ts":1},"idx_name_ts");                                         // market-snapshot movers (ts range)
ci({name:1,"value.related_team_urns":1},"idx_name_related_team_urns");           // market -> team
ci({name:1,"value.event_urn":1},"idx_name_event_urn");                           // market -> event
// TTL (partial): expire ONLY market snapshots older than 30d. The `document`
// collection is shared across entity types, so the TTL MUST be partial-scoped
// by name or it would delete identity/event/market docs too. `created` is the
// BSON Date field on document docs.
ci({created:1},"ttl_market_snapshot_30d",{expireAfterSeconds:2592000, partialFilterExpression:{name:"worldcup:market-snapshot"}});
r.forEach(x=>print(x));
print("total document indexes: "+db.document.getIndexes().length);
'
