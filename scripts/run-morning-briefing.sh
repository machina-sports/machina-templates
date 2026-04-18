#!/bin/bash
#
# run-morning-briefing.sh
#
# Usage:
#   export MACHINA_API_KEY="your_api_key"
#   export MACHINA_PROJECT_ID="your_project_id"
#   ./scripts/run-morning-briefing.sh
#
# Description:
#   This script authenticates with the Machina Core and Client APIs
#   to execute the "project-morning-briefing" workflow. It requires
#   an API key and a Project ID to be set as environment variables.
#
#   The script will:
#   1. Check for required environment variables.
#   2. Obtain a core session JWT from the Core API.
#   3. Obtain a project-scoped JWT and Client API URL from the Core API.
#   4. Execute the workflow on the Client API.
#   5. Print the JSON response and exit with an appropriate status code.
#

set -e
set -o pipefail

# --- Configuration ---
CORE_API_URL="https://api.machina.gg"

# --- Validate Environment Variables ---
if [ -z "$MACHINA_API_KEY" ]; then
  echo "Error: MACHINA_API_KEY environment variable is not set." >&2
  echo "Usage: export MACHINA_API_KEY=\"your_api_key\"" >&2
  exit 1
fi

if [ -z "$MACHINA_PROJECT_ID" ]; then
  echo "Error: MACHINA_PROJECT_ID environment variable is not set." >&2
  echo "Usage: export MACHINA_PROJECT_ID=\"your_project_id\"" >&2
  exit 1
fi

# --- Step 1: Authenticate and get Core Session Token ---
# This step is implicit in the /login/project call when using an API key.
# The Core API directly validates the X-Api-Token and issues the necessary JWTs.

# --- Step 2: Get Project Token and Client API URL ---
echo "Authenticating with Core API and fetching project token..."
login_response=$(curl -s -w "\\n%{http_code}" -X POST \
  "${CORE_API_URL}/login/project" \
  -H "Content-Type: application/json" \
  -H "X-Api-Token: ${MACHINA_API_KEY}" \
  -d "{\"project_id\": \"${MACHINA_PROJECT_ID}\"}")

login_http_code=$(echo "$login_response" | tail -n1)
login_body=$(echo "$login_response" | sed '$d')

if [ "$login_http_code" -ne 200 ]; then
  echo "Error: Failed to get project token. HTTP status: ${login_http_code}" >&2
  echo "Response: ${login_body}" >&2
  exit 1
fi

PROJECT_TOKEN=$(echo "$login_body" | jq -r '.data.project_jwt')
SESSION_TOKEN=$(echo "$login_body" | jq -r '.data.jwt')
CLIENT_API_URL=$(echo "$login_body" | jq -r '.data.web_url')

if [ -z "$PROJECT_TOKEN" ] || [ "$PROJECT_TOKEN" == "null" ]; then
    echo "Error: Project JWT is missing from API response." >&2
    echo "$login_body" >&2
    exit 1
fi
if [ -z "$SESSION_TOKEN" ] || [ "$SESSION_TOKEN" == "null" ]; then
    echo "Error: Session JWT is missing from API response." >&2
    echo "$login_body" >&2
    exit 1
fi
if [ -z "$CLIENT_API_URL" ] || [ "$CLIENT_API_URL" == "null" ]; then
    echo "Error: Client API URL is missing from API response." >&2
    echo "$login_body" >&2
    exit 1
fi

echo "Successfully obtained project token and Client API URL."

# --- Step 3: Execute the Workflow ---
WORKFLOW_NAME="project-morning-briefing"
echo "Executing workflow '${WORKFLOW_NAME}' on ${CLIENT_API_URL}..."

workflow_response=$(curl -s -w "\\n%{http_code}" -X POST \
  "${CLIENT_API_URL}/workflow/execute/${WORKFLOW_NAME}" \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: ${SESSION_TOKEN}" \
  -H "X-Project-Token: ${PROJECT_TOKEN}" \
  -d '{"context-workflow": {}}')

workflow_http_code=$(echo "$workflow_response" | tail -n1)
workflow_body=$(echo "$workflow_response" | sed '$d')

# --- Step 4 & 5: Print Response and Exit ---
echo "Workflow execution completed. HTTP status: ${workflow_http_code}"

if command -v jq &> /dev/null; then
  echo "$workflow_body" | jq .
else
  echo "$workflow_body"
fi

if [ "$workflow_http_code" -ne 200 ]; then
  exit 1
else
  exit 0
fi
