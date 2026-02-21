# machina-cockpit

Dev-UX Docker image for Google Cloud Workstations. Repository-agnostic base image with all tools needed for Machina development with Claude Code headless.

## What's Included

| Layer | Tools |
|-------|-------|
| Base | Code OSS (VS Code web), git, curl, wget, sudo |
| System | gh CLI, jq, vim, htop, tmux |
| Python | python3, pip, virtualenv |
| Node.js | Node.js 20 LTS |
| AI | Claude Code (`@anthropic-ai/claude-code`) |
| Cloud | gcloud CLI |
| Containers | Docker CLI (DinD via workstation config) |

## Build

```bash
docker build -t machinasports/machina-cockpit:latest .
```

## Push

```bash
docker push machinasports/machina-cockpit:latest
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(empty)* | API key for Claude Code |
| `CLAUDE_CODE_USE_BEDROCK` | `0` | Set `1` to use AWS Bedrock |
| `GIT_USER_NAME` | *(unset)* | Auto-configure `git config user.name` |
| `GIT_USER_EMAIL` | *(unset)* | Auto-configure `git config user.email` |
| `MACHINA_REPOS` | *(unset)* | Comma-separated repo URLs to auto-clone |
| `MACHINA_CLONE_DIR` | `/home/user/repos` | Target directory for auto-cloned repos |

## Workstation Config

### Update existing config

```bash
gcloud workstations configs update machina-config \
  --project=dev1mymachinadiyproject \
  --region=us-central1 \
  --cluster=machina-cluster \
  --container-custom-image=machinasports/machina-cockpit:latest
```

### Set env vars on config

Env vars are configured in the workstation config (GCP Console or gcloud). The `ANTHROPIC_API_KEY` should be injected there, not baked into the image.

### Recreate workstation (required after image change)

```bash
# Delete old
gcloud workstations delete machina-ws-01 \
  --project=dev1mymachinadiyproject \
  --region=us-central1 \
  --cluster=machina-cluster \
  --config=machina-config

# Create new
gcloud workstations create machina-ws-01 \
  --project=dev1mymachinadiyproject \
  --region=us-central1 \
  --cluster=machina-cluster \
  --config=machina-config
```

## Verify

```bash
# SSH in
gcloud workstations ssh machina-ws-01 \
  --project=dev1mymachinadiyproject \
  --region=us-central1 \
  --cluster=machina-cluster \
  --config=machina-config

# Check tools
claude --version
python3 --version
node --version
gh --version
gcloud --version
docker --version
```
