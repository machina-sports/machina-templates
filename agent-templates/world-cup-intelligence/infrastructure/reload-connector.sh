#!/usr/bin/env bash
# Reload the cached pyscript connector WITHOUT a pod rollout, so the MCP session
# survives (no `/mcp` reconnect needed).
#
# Why: pyscript connector code is cached per-process in the client-api + worker
# containers, so a code change needs those processes restarted. `kubectl rollout
# restart` recreates the WHOLE pod — including the mcp-server container — which
# drops the MCP session (every tool call then returns -32602 until `/mcp`).
#
# Instead, SIGTERM PID 1 of ONLY the connector-executing containers; k8s restarts
# just those in place. mcp-server / mcp-proxy are siblings and stay up, so the MCP
# session is preserved. (SIGKILL does NOT work: a process inside the PID namespace
# can't SIGKILL its own init; SIGTERM is delivered because celery/uvicorn handle it.)
#
# Use after `import_templates_from_git` for connector (.py) changes, instead of
# `kubectl rollout restart deployment/...`.
#
# Usage: ./reload-connector.sh [namespace] [deployment] [container-prefix]
set -euo pipefail
NS="${1:-tenant-machina-drops}"
DEP="${2:-tenant-machina-drops-world-cup-2-deployment}"
PREFIX="${3:-tenant-machina-drops-world-cup-2}"
POD="$(kubectl -n "$NS" get pods -l app="$DEP" --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')"
[ -n "$POD" ] || { echo "no running pod for app=$DEP"; exit 1; }
echo "pod=$POD  (mcp-server/mcp-proxy will NOT be touched)"
for c in client-api worker-normal worker-streaming; do
  echo "  SIGTERM PID1 -> $c"
  kubectl -n "$NS" exec "$POD" -c "${PREFIX}-${c}" -- sh -c 'kill -TERM 1' || true
done
sleep 6
kubectl -n "$NS" wait --for=condition=Ready "pod/$POD" --timeout=120s
echo "connector reloaded; MCP session preserved (no /mcp needed)."
