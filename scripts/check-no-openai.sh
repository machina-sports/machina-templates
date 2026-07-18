#!/usr/bin/env bash
# Repository AI-provider guardrail.
#
# Vertex AI remains the mandatory default.  The only provider-independent
# workflow facade allowed is the structurally checked machina-ai router.

set -euo pipefail

MODE="${1:-all}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$MODE" != "all" && "$MODE" != "staged" ]]; then
  echo "usage: $0 [all|staged]" >&2
  exit 2
fi

if [[ "$MODE" == "staged" ]]; then
  # Include renamed files so a rename+edit cannot dodge the pre-commit scan.
  FILES=$(git diff --cached --name-only --diff-filter=ACMR | grep -E '\.(yml|yaml)$' || true)
else
  FILES=$(find . -type f \( -name '*.yml' -o -name '*.yaml' \) \
    -not -path './.git/*' \
    -not -path './node_modules/*' \
    -not -path './connectors/openai/*' \
    -not -path './connectors/machina-ai/*' \
    -not -path './connectors/azure-foundry/*' \
    -not -path './scripts/*' \
    -not -path './.githooks/*' \
    -not -path './.github/workflows/lint-no-openai.yml' 2>/dev/null || true)
fi

FILTERED=""
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  file="${file#./}"
  case "$file" in
    connectors/openai/*|connectors/machina-ai/*|connectors/azure-foundry/*|scripts/*|.githooks/*|.github/workflows/lint-no-openai.yml)
      continue ;;
  esac
  FILTERED+="$file"$'\n'
done <<< "$FILES"

PATTERNS=(
  '["'"'"']?name["'"'"']?:[[:space:]]+["'"'"']?openai["'"'"']?[[:space:]]*(#.*)?$'
  '["'"'"']?model["'"'"']?:[[:space:]]+["'"'"']?text-embedding-(3-(small|large)|ada-002)'
  '["'"'"']?model["'"'"']?:[[:space:]]+["'"'"']?gpt-'
  '\$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY'
  '\$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY'
)

HITS=""
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  for pattern in "${PATTERNS[@]}"; do
    if [[ "$MODE" == "staged" ]]; then
      matches=$(git show ":$file" 2>/dev/null | grep -nE "$pattern" || true)
    else
      matches=$(grep -nE "$pattern" "$file" 2>/dev/null || true)
    fi
    if [[ -n "$matches" ]]; then
      while IFS= read -r line; do
        HITS+="$file:$line"$'\n'
      done <<< "$matches"
    fi
  done
done <<< "$FILTERED"

if [[ -n "$HITS" ]]; then
  cat >&2 <<'EOF'
[lint-no-openai] Banned direct OpenAI/GPT references found.

Vertex AI remains the repository default. Workflows may use google-genai
explicitly or the policy-governed machina-ai facade; they may not hardcode an
OpenAI connector, GPT model, deprecated OpenAI embedding, or OpenAI secret.

Hits:
EOF
  printf '%s' "$HITS" | while IFS= read -r line; do
    [[ -n "$line" ]] && printf '  %s\n' "$line" >&2
  done
  cat >&2 <<'EOF'

Use Vertex models and credentials, or use machina-ai without workflow-owned
provider credentials/endpoints. The structural router policy lint will reject
non-Vertex profiles/providers and caller-controlled routing fields.
EOF
  exit 1
fi

# In CI the semantic (parsed-YAML) router-policy pass is mandatory: a runner
# without PyYAML must fail loudly instead of silently degrading to the
# line-based scan (which flow-style YAML can dodge). Local pre-commit runs
# still degrade gracefully, with a stderr warning from the script itself.
if [[ -n "${CI:-}" || -n "${GITHUB_ACTIONS:-}" ]]; then
  python3 scripts/check-machina-ai-policy.py "$MODE" --require-semantic
else
  python3 scripts/check-machina-ai-policy.py "$MODE"
fi
