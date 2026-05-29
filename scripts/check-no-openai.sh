#!/usr/bin/env bash
# Guardrail: fail when a workflow re-introduces OpenAI/GPT/text-embedding-3
# references that should be Vertex (`google-genai`) instead.
#
# Runs in:
#   - .githooks/pre-commit  (local; only scans staged files)
#   - .github/workflows/lint-no-openai.yml  (CI; scans the whole tree)
#
# Exit 0 = clean, exit 1 = found banned patterns.
#
# What's banned (in *.yml / *.yaml outside the listed exemptions):
#   - connector `name: openai` / `name: "openai"`
#   - connector `name: machina-ai` / `name: "machina-ai"`
#   - model: text-embedding-3-{small,large} / text-embedding-ada-002
#   - model: gpt-{3.5*,4*}
#   - $TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY
#   - $MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY
#
# Exempted paths (legacy connector self-refs + this script):
#   - connectors/openai/
#   - connectors/machina-ai/
#   - connectors/azure-foundry/
#   - scripts/
#   - .githooks/
#   - .github/workflows/lint-no-openai.yml

set -euo pipefail

MODE="${1:-all}"  # "all" or "staged"

# Find candidate files
if [[ "$MODE" == "staged" ]]; then
  FILES=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.(yml|yaml)$' || true)
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

if [[ -z "$FILES" ]]; then
  exit 0
fi

# Apply per-file exemptions before grepping (staged mode picks up files that may
# live under exempt dirs — filter them out here).
FILTERED=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  case "$f" in
    connectors/openai/*|connectors/machina-ai/*|connectors/azure-foundry/*|scripts/*|.githooks/*|.github/workflows/lint-no-openai.yml)
      continue ;;
  esac
  FILTERED+="$f"$'\n'
done <<< "$FILES"

if [[ -z "$FILTERED" ]]; then
  exit 0
fi

# Patterns. The `name:` patterns are anchored by indent + colon so we don't
# match it inside comments or unrelated strings.
PATTERNS=(
  'name:[[:space:]]+"?openai"?[[:space:]]*$'
  'name:[[:space:]]+"?machina-ai"?[[:space:]]*$'
  'model:[[:space:]]+"?text-embedding-(3-(small|large)|ada-002)"?'
  'model:[[:space:]]+"?gpt-(3\.5|4)'
  '\$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY'
  '\$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY'
)

HITS=""
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  for pat in "${PATTERNS[@]}"; do
    if matches=$(grep -nE "$pat" "$f" 2>/dev/null); then
      while IFS= read -r line; do
        HITS+="$f:$line"$'\n'
      done <<< "$matches"
    fi
  done
done <<< "$FILTERED"

if [[ -n "$HITS" ]]; then
  cat <<EOF >&2
[lint-no-openai] Banned OpenAI/GPT references found.

  We migrated all workflows to Google Vertex AI via the \`google-genai\`
  connector (incident 2026-05-16; see scripts/migrate-openai-to-vertex.py).
  New workflows must use Vertex from day one.

  Hits:

EOF
  echo "$HITS" | sed 's/^/  /' >&2
  cat <<EOF >&2

  How to fix:
    - connector  →  name: google-genai (add location: "global", provider: "vertex_ai")
    - embedding  →  model: text-embedding-004
    - prompt     →  model: gemini-2.5-flash (cheap)  /  gemini-2.5-pro (quality)
    - credential →  \$TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL
                    + \$TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID

  Or run the migration helper on a single file:
    python3 scripts/migrate-openai-to-vertex.py --apply --paths <file.yml>

EOF
  exit 1
fi
exit 0
