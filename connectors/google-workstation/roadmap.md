# Google Cloud Workstation Connector

## Architecture

```
Machina Agent → Connector (Celery) → HTTP/NDJSON → Cockpit Relay (port 8080) → Claude Code CLI
                                                                                      ↓
Frontend ← SocketIO ← Redis Pub/Sub ← Connector ← Streamed NDJSON ←──────────────────┘
```

- **Cockpit image**: `machinasports/machina-cockpit:{sha}` (Docker Hub, SHA-tagged)
- **Service account**: `vertex-express@dev1mymachinadiyproject.iam.gserviceaccount.com`
- **Vault secret**: `gcw-credential` (service account JSON)
- **Relay server**: `aiohttp` on port 8080, started via `/etc/workstation-startup.d/060-relay-server.sh`
- **GCW proxy**: `https://8080-{host}.cloudworkstations.dev` with Bearer token auth
- **ADR**: `docs/adrs/0027-cockpit-relay-server-streaming.md`

## Workstation Access

- **Project**: `dev1mymachinadiyproject`
- **Cluster**: `machina-cluster` (us-central1)
- **Config**: `machina-config` (e2-standard-4, 200GB persistent disk)
- **Workstation**: `machina-ws-01`
- **SSH disabled** — relay server is the only programmatic access

## Commands (13 total)

### Workstation Lifecycle
| Command | Description |
|---------|-------------|
| List Clusters | List clusters in project/location |
| List Configs | List configs in a cluster |
| List Workstations | List workstations in a config |
| Get Workstation | Get workstation details and state |
| Create Workstation | Create a new workstation |
| Start Workstation | Start a stopped workstation |
| Stop Workstation | Stop a running workstation |
| Delete Workstation | Delete a workstation |
| Generate Access Token | Generate short-lived access token |

### Claude Code Execution (via Relay)
| Command | Description |
|---------|-------------|
| Execute Claude | Legacy composite: start WS + exec prompt (non-streaming) |
| List Sessions | List running Claude processes via relay `/api/sessions` |
| Send Message | Execute prompt with NDJSON streaming + Redis pub/sub |
| Kill Session | Kill Claude process by session_id or PID |

## Completed

### 2026-02-21: End-to-End Stream-JSON Validation
- Refactored connector to fully self-contained functions (PyScript engine constraint: no module-level helpers)
- Fixed NDJSON parsing for actual Claude Code `stream-json` format (`message.content[].text`, not top-level `content`)
- Validated `Send Message` end-to-end: Celery → GCW SDK → relay → Claude Code → streamed NDJSON → parsed response
- Configured vault secret `gcw-credential` with `vertex-express@` service account
- Fixed GCW image caching: switched from `latest` tag to SHA-tagged images (`machinasports/machina-cockpit:{sha}`)
- SA `development@` lacks Workstations permissions; `vertex-express@` has full access

### 2026-02-21: Relay Server + Streaming Connector
- Created `relay_server.py` (aiohttp, ~140 lines) with 4 endpoints
- Created `start-relay.sh` startup script for workstation startup.d
- Added `--break-system-packages` for pip on Python 3.12 base image
- Added `--verbose` flag required for `stream-json` output format
- Updated Dockerfile, built and pushed cockpit image
- Switched workstation config to Docker Hub image (`docker.io/machinasports/...`)
- Added connector commands: Send Message (streaming + Redis), List Sessions (relay), Kill Session
- Validated relay endpoints on `machina-ws-01`: health, sessions, message (json)
- Connector installed and commands validated in Celery workers

### 2026-02-21: Initial Connector
- GCW SDK connector with 10 lifecycle commands
- Composite `Execute Claude` command (start WS + generate token + HTTP exec)
- Test credentials workflow

## Backlog

### Stream-JSON End-to-End
- [x] Test `Send Message` with `stream-json` output format — validated via Celery connector_executor
- [ ] Validate Redis pub/sub messages appear on `thread:{thread_id}:stream` channel
- [ ] Verify SocketIO Bridge delivers chunks to frontend in real-time

### Agent Integration
- [ ] Create agent template that uses `Send Message` in a workflow
- [x] Configure vault secret for GCW credentials (`gcw-credential`)
- [ ] Define context-variables mapping in agent template
- [ ] Build multi-turn conversation flow using `session_id` continuity

### MCP Configs on Workstation
- [ ] Auto-configure `.mcp.json` per project via relay or entrypoint
- [ ] Support multiple MCP server connections from workstation Claude Code

### Production Hardening
- [ ] Add relay request logging to persistent disk
- [ ] Add timeout/max-concurrent-sessions limits to relay
- [ ] Health check integration with GCW monitoring
- [ ] Consider relay process supervisor (systemd or supervisord) instead of background nohup

### CI/CD Improvements
- [ ] Add Artifact Registry push to `build-cockpit.yml` (eliminate manual Docker Hub → AR sync)
- [ ] Tag cockpit images with semver in addition to `latest`

## Issues Fixed

### 2026-02-21: pip install fails on Python 3.12 (PEP 668)
- **Symptom**: `build-cockpit.yml` CI failed — `pip3 install aiohttp` rejected
- **Root cause**: Base GCW Code OSS image uses Python 3.12 which enforces PEP 668 (externally-managed environment)
- **Fix**: Added `--break-system-packages` flag to pip install in Dockerfile

### 2026-02-21: stream-json requires --verbose
- **Symptom**: Relay returned error `--output-format=stream-json requires --verbose`
- **Root cause**: Claude Code CLI requires `--verbose` when using `stream-json` with `-p` flag
- **Fix**: Added `--verbose` to the claude command in relay_server.py

### 2026-02-21: GCW caches Docker `latest` tag
- **Symptom**: Workstation restart still ran old relay (without `--verbose`)
- **Root cause**: GCW caches image digest for `latest` tag; stop/start doesn't re-pull
- **Fix**: Switch to SHA-tagged images (`machinasports/machina-cockpit:{git-sha}`) and update config before restart

### 2026-02-21: stream-json NDJSON parsing mismatch
- **Symptom**: `invoke_send_message` returned empty response despite relay success
- **Root cause**: Connector expected `type:assistant, subtype:text, content:"..."` but actual format is `type:assistant, message.content[].text`
- **Fix**: Updated parsing to extract from `message.content[].text` + fallback to `result.result`

### 2026-02-21: SA `development@` lacks Workstations permissions
- **Symptom**: `invoke_list_clusters` returned 403 Permission denied
- **Root cause**: `development@` SA only has Storage roles, not Workstations
- **Fix**: Switched to `vertex-express@` SA which has `workstations.user` + `workstations.viewer`

### 2026-02-21: adidas-tracker MCP not working
- **Symptom**: `health_check` OK but `search_agents` returned AUTH-013 (500)
- **Root cause 1**: MCP deployment nginx proxy had wrong env var
- **Root cause 2**: Workstation `.bashrc` had old token
- **Fix**: Updated kubectl env + workstation `.bashrc`
