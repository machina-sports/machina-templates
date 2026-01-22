#!/bin/bash

# Deployment script for sportradar-soccer-config-seasons agent loop fix
# Usage: ./DEPLOY-FIX.sh [dev|prd]

set -e

ENVIRONMENT=${1:-dev}

echo "🚀 Deploying Agent Loop Fix to Blog BR ${ENVIRONMENT^^}"
echo "================================================"
echo ""

# Validate environment
if [ "$ENVIRONMENT" != "dev" ] && [ "$ENVIRONMENT" != "prd" ]; then
    echo "❌ Error: Environment must be 'dev' or 'prd'"
    echo "Usage: ./DEPLOY-FIX.sh [dev|prd]"
    exit 1
fi

# Set namespace
if [ "$ENVIRONMENT" = "dev" ]; then
    NAMESPACE="tenant-entain-organization"
    POD_PREFIX="tenant-entain-organization-blog-br-dev-deployment"
else
    NAMESPACE="tenant-entain-organization"
    POD_PREFIX="tenant-entain-organization-blog-br-prd-deployment"
fi

echo "📋 Pre-Deployment Checks"
echo "------------------------"

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if we can access the cluster
if ! kubectl cluster-info &> /dev/null; then
    echo "❌ Cannot connect to Kubernetes cluster"
    exit 1
fi

echo "✅ kubectl connected to cluster"

# Check current pod status
echo ""
echo "📊 Current Pod Status"
echo "---------------------"
kubectl get pods -n $NAMESPACE | grep "$POD_PREFIX"

echo ""
echo "📈 Current Agent Activity (last 60 seconds)"
echo "-------------------------------------------"
CURRENT_POD=$(kubectl get pods -n $NAMESPACE | grep "$POD_PREFIX" | grep "Running" | head -1 | awk '{print $1}')

if [ -z "$CURRENT_POD" ]; then
    echo "⚠️  No running pod found"
else
    EXEC_COUNT=$(kubectl logs -n $NAMESPACE $CURRENT_POD -c ${POD_PREFIX:0:50}-worker-normal --since=60s 2>/dev/null | grep -c "Executing sportradar-soccer-sync" || echo "0")
    echo "Workflow executions in last 60s: $EXEC_COUNT"

    if [ "$EXEC_COUNT" -gt 10 ]; then
        echo "🚨 LOOP DETECTED! Executions: $EXEC_COUNT (expected: 0-10)"
    else
        echo "✅ Activity seems normal"
    fi
fi

echo ""
echo "📦 Deployment Steps"
echo "-------------------"
echo ""
echo "⚠️  MANUAL STEPS REQUIRED:"
echo ""
echo "1. Commit and push the fixed files to GitHub:"
echo "   cd /Users/fernando/machina/machina-templates"
echo "   git add connectors/sportradar-soccer/"
echo "   git commit -m \"fix: add cooldown mechanism to sportradar-soccer-config-seasons agent\""
echo "   git push origin main"
echo ""
echo "2. Use MCP to import new workflows (Python):"
echo ""
cat <<'PYTHON'
# Import cooldown-check workflow
mcp__sportingbet_blog_dev__import_templates_from_git(
    repositories=[{
        "repo_url": "https://github.com/machina-sports/machina-templates",
        "template": "connectors/sportradar-soccer/workflows/cooldown-check",
        "repo_branch": "main"
    }]
)

# Import update-timestamp workflow
mcp__sportingbet_blog_dev__import_templates_from_git(
    repositories=[{
        "repo_url": "https://github.com/machina-sports/machina-templates",
        "template": "connectors/sportradar-soccer/workflows/update-timestamp",
        "repo_branch": "main"
    }]
)
PYTHON
echo ""
echo "3. Search for the agent ID:"
echo ""
cat <<'PYTHON'
agents = mcp__sportingbet_blog_dev__search_agents(
    filters={"name": "sportradar-soccer-config-seasons"},
    sorters=["created", -1],
    page_size=1
)
print(agents['agents'][0]['_id'])  # Copy this ID
PYTHON
echo ""
echo "4. Update the agent with fixed configuration:"
echo "   - Read config-seasons.yml.FIXED"
echo "   - Use update_agent MCP call with agent_id from step 3"
echo ""
echo "5. Verify deployment:"
echo "   kubectl logs -n $NAMESPACE <pod-name> -c ${POD_PREFIX:0:50}-worker-normal --tail=100 | grep -i cooldown"
echo ""

echo "📚 Full documentation available at:"
echo "   /Users/fernando/machina/machina-templates/connectors/sportradar-soccer/AGENT-LOOP-FIX.md"
echo ""

read -p "Have you completed the manual steps above? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled. Complete the manual steps first."
    exit 1
fi

echo ""
echo "🔍 Verifying Deployment"
echo "-----------------------"

# Wait for pod restart if needed
echo "Waiting 10 seconds for changes to take effect..."
sleep 10

# Get new pod
NEW_POD=$(kubectl get pods -n $NAMESPACE | grep "$POD_PREFIX" | grep "Running" | head -1 | awk '{print $1}')

if [ -z "$NEW_POD" ]; then
    echo "⚠️  No running pod found after deployment"
    exit 1
fi

echo "Checking new pod: $NEW_POD"

# Check for cooldown messages in logs
echo ""
echo "Looking for cooldown check logs..."
COOLDOWN_LOGS=$(kubectl logs -n $NAMESPACE $NEW_POD -c ${POD_PREFIX:0:50}-worker-normal --tail=200 2>/dev/null | grep -i "cooldown\|should-execute" | tail -5)

if [ -z "$COOLDOWN_LOGS" ]; then
    echo "⚠️  No cooldown logs found yet. This is normal if agent hasn't triggered."
    echo "   Monitor with: kubectl logs -n $NAMESPACE $NEW_POD -c ${POD_PREFIX:0:50}-worker-normal --follow | grep cooldown"
else
    echo "✅ Cooldown mechanism detected:"
    echo "$COOLDOWN_LOGS"
fi

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "📊 Next Steps:"
echo "1. Monitor for 5-10 minutes:"
echo "   kubectl logs -n $NAMESPACE $NEW_POD -c ${POD_PREFIX:0:50}-worker-normal --follow | grep -E 'cooldown|Executing sportradar-soccer-sync'"
echo ""
echo "2. Verify execution frequency reduced:"
echo "   kubectl logs -n $NAMESPACE $NEW_POD -c ${POD_PREFIX:0:50}-worker-normal --since=10m | grep -c 'Executing sportradar-soccer-sync'"
echo "   Expected: 0-20 (down from 1650+)"
echo ""
echo "3. Check for pod stability:"
echo "   kubectl get pods -n $NAMESPACE | grep $POD_PREFIX"
echo "   Should show same pod age > 10 minutes (no restarts)"
echo ""
