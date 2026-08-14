#!/usr/bin/env bash
# Condition 10 — the no-mutation proof for the historical World Cup runtime.
#
# Approved Amendment C (§C2, §C6) discharges "known legacy consumer breakages: 0"
# by declining to mutate the historical runtime at all, rather than by migrating
# it. The claim is therefore checkable as a fact about the diff: no path under
# the historical template may appear in it, tracked or untracked.
#
# This is a script rather than a unit test on purpose. The question is about a
# working tree measured against a base ref, so a unit test that shells out to git
# would report "this checkout has no upstream ref" as a failure of the thing
# under test. Here, a missing ref is a clear error about the audit itself.
#
# Usage:
#   scripts/check-no-wci-mutation.sh [base-ref]      # default: origin/main
#
# Exit 0 = no mutation. Exit 1 = a path under the historical template moved.

set -euo pipefail

BASE_REF="${1:-origin/main}"
GUARDED_PATH="agent-templates/world-cup-intelligence"

cd "$(dirname "$0")/.."

if ! git rev-parse --verify --quiet "${BASE_REF}^{commit}" >/dev/null; then
  echo "error: base ref '${BASE_REF}' does not resolve; pass one explicitly" >&2
  exit 2
fi

# Tracked changes: committed or staged or working-tree, against the base ref.
tracked="$(git diff --name-only "${BASE_REF}" -- "${GUARDED_PATH}")"

# Untracked additions. A NEW file under the historical template is a mutation
# that `git diff` alone does not see, which is exactly how the previous
# pre-pivot artifacts landed there.
untracked="$(git ls-files --others --exclude-standard -- "${GUARDED_PATH}")"

if [ -n "${tracked}" ] || [ -n "${untracked}" ]; then
  echo "FAIL: the historical runtime under ${GUARDED_PATH}/ has been mutated." >&2
  echo "Amendment C §C2 requires it byte-unchanged." >&2
  [ -n "${tracked}" ] && { echo "  changed vs ${BASE_REF}:" >&2; \
    echo "${tracked}" | sed 's/^/    /' >&2; }
  [ -n "${untracked}" ] && { echo "  untracked additions:" >&2; \
    echo "${untracked}" | sed 's/^/    /' >&2; }
  exit 1
fi

echo "OK: ${GUARDED_PATH}/ is byte-unchanged against ${BASE_REF} (tracked and untracked)."
