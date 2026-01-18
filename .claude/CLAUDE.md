# Machina Templates - Shared Agent Templates & Connectors

## 🚀 Quick Start

### Available Skills

| Skill | Description |
|-------|-------------|
| `/mkn-templates:create-template` | Scaffold new template with correct structure |
| `/mkn-templates:validate-template` | Validate YAML patterns before installation |
| `/mkn-templates:install-template` | Install templates via MCP (local or Git) |
| `/mkn-templates:analyze-template` | Analyze template structure, dependencies, secrets |
| `/mkn-templates:configure-secrets` | Configure vault secrets for connectors |

### Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](guides/getting-started.md) | Quick start for template development |
| [Template YAML Reference](guides/template-yaml-reference.md) | Complete YAML syntax and patterns |
| [Connectors Catalog](guides/connectors-catalog.md) | All 35+ available connectors |

---

## 📋 Project Overview

Central repository of reusable agent templates and connectors for the Machina Sports platform. Contains 24 agent templates and 38 connectors used across all tenant deployments.

**Repository**: `/Users/fernando/machina/machina-templates`
**Main Technologies**: Python, YAML configurations, REST API integrations
**Key Features**: Shared connectors, agent templates, data transformations, API wrappers

## 🏗️ Architecture

```
machina-templates/
├── agent-templates/        # Reusable agent patterns (24 templates)
│   ├── assistant-tools/
│   ├── chat-completion/
│   ├── coverage-tools/
│   ├── machina-assistant/
│   ├── soccer-predictions-analyst/
│   └── ...
│
└── connectors/            # External service integrations (38 connectors)
    ├── AI Services/
    │   ├── openai/
    │   ├── google-genai/
    │   ├── google-vertex/
    │   ├── groq/
    │   ├── perplexity/
    │   └── machina-ai/
    │
    ├── Sports Data APIs/
    │   ├── api-football/
    │   ├── sportradar-soccer/
    │   ├── sportradar-nfl/
    │   ├── sportradar-nba/
    │   ├── sportradar-mlb/
    │   └── stats-perform/
    │
    ├── Content & Storage/
    │   ├── wordpress/
    │   ├── google-storage/
    │   ├── storage/
    │   └── temp-downloader/
    │
    └── Utilities/
        ├── bwin/ (betting odds)
        ├── kalshi/ (prediction markets)
        ├── tallysight/ (sports analytics)
        ├── oxylabs/ (web scraping)
        └── zendesk/ (support)
```

## 🔌 Connector Catalog

### AI Services (8 connectors)

| Connector | Purpose | Key Commands |
|-----------|---------|--------------|
| **openai** | OpenAI API (GPT-4, embeddings) | `invoke_prompt`, `create_embedding` |
| **google-genai** | Google Gemini models | `generate_content` |
| **google-vertex** | Google Vertex AI | `invoke_prompt`, `generate_video` |
| **groq** | Groq fast inference | `invoke_prompt` |
| **grok** | xAI Grok models | `invoke_prompt` |
| **perplexity** | Perplexity web search | `web_search` |
| **machina-ai** | Custom Machina LLM wrapper | `invoke_prompt` |
| **machina-ai-fast** | Fast inference variant | `invoke_prompt` |

**Environment Variables**:
- `$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_GOOGLE_VERTEX_PROJECT_ID`
- `$MACHINA_CONTEXT_VARIABLE_GROQ_API_KEY`

### Sports Data APIs (8 connectors)

| Connector | Sport | Commands |
|-----------|-------|----------|
| **api-football** | Soccer | `get_fixtures`, `get_standings`, `get_h2h` |
| **sportradar-soccer** | Soccer | `get_schedule`, `get_match_summary` |
| **sportradar-nfl** | NFL | `sync_games`, `sync_injuries`, `detect_season` |
| **sportradar-nba** | NBA | `get_schedule`, `get_standings` |
| **sportradar-mlb** | MLB | `get_games`, `get_standings` |
| **sportradar-nhl** | NHL | `get_schedule` |
| **sportradar-rugby** | Rugby | `get_schedule` |
| **stats-perform** | Multi-sport | `get_fixtures` |

**Featured: sportradar-nfl**
- Season type detection (PRE/REG/PST)
- Automatic playoff week conversion (19→1, 20→2)
- Injury sync (current + next week)
- Unit tests: `scripts/tests/` (13 tests, 100% passing)

**Documentation**: See [NFL Season Detection](../../docs/.claude/features/nfl-season-detection.md)

### Content & Storage (6 connectors)

| Connector | Purpose | Commands |
|-----------|---------|----------|
| **wordpress** | WordPress API | `create_post`, `update_post` |
| **google-storage** | Google Cloud Storage | `upload_file`, `download_file` |
| **google-storage-v2** | GCS v2 API | `upload_blob` |
| **storage** | Generic storage wrapper | `save`, `load` |
| **temp-downloader** | Temporary file handling | `download` |
| **elevenlabs** | Text-to-speech | `generate_audio` |

### Utilities (16 connectors)

| Connector | Purpose |
|-----------|---------|
| **bwin** | Betting odds integration |
| **kalshi** | Prediction market data |
| **tallysight** | Sports analytics platform |
| **oxylabs** | Web scraping proxy |
| **zendesk** | Customer support |
| **fastf1** | Formula 1 telemetry |
| **exa-search** | Semantic web search |
| **docling** | Document processing |
| **rss-feed** | RSS feed parser |
| **google-speech-to-text** | Audio transcription |
| **stability** | Image generation (Stable Diffusion) |
| **american-football** | NFL data utilities |
| **mlb-statsapi** | MLB Stats API |

## 🎯 Agent Template Catalog

### Content Generation (8 templates)

| Template | Purpose | Key Workflows |
|----------|---------|---------------|
| **chat-completion** | Generic LLM chat interface | `chat`, `stream_chat` |
| **voice-chat-completion** | Voice-enabled chat | `speech_to_text`, `text_to_speech` |
| **social-media-generator** | Twitter/social content | `generate_thread`, `generate_post` |
| **template-newsletter** | Email newsletters | `generate_content` |
| **template-quizzes** | Sports quizzes | `generate_quiz` |
| **template-sportsblog** | Blog post generation | `write_article` |
| **roast-agent** | Humorous sports commentary | `generate_roast` |
| **personalized-podcast** | AI podcast scripts | `generate_script` |

### Sports Analytics (6 templates)

| Template | Purpose | Sport |
|----------|---------|-------|
| **soccer-predictions-analyst** | Match predictions + analysis | Soccer |
| **kalshi-market-agent** | Prediction market integration | Multi-sport |
| **nfl-podcast-generator** | NFL podcast content | NFL |
| **bundesliga-podcast** | Bundesliga content | Soccer |
| **psg-podcast-generator** | PSG-specific content | Soccer |
| **template-superbowl-lix** | Super Bowl LIX content | NFL |

### Platform Templates (10 templates)

| Template | Purpose |
|----------|---------|
| **assistant-tools** | Helper functions for agents |
| **coverage-tools** | Live event coverage utilities |
| **iptc-mappings** | IPTC metadata mappings |
| **machina-assistant** | Generic Machina AI assistant |
| **onboarding** | User onboarding workflows |
| **nfl-2025-preseason** | NFL preseason automation |
| **corinthians-twitter** | Team-specific social content |
| **template-fastf1** | F1 data analysis |

## 🛠️ Technical Architecture

### 3-Tier System

```
┌─────────────────────────────────────────────┐
│              AGENTS                         │
│  (When & How workflows execute)             │
│  - Scheduled execution                      │
│  - Event-driven triggers                    │
│  - Context/state management                 │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│            WORKFLOWS                        │
│  (Logic pipelines)                          │
│  - Task sequencing                          │
│  - Data transformation                      │
│  - Conditional logic                        │
│  - Foreach loops                            │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│            CONNECTORS                       │
│  (External service bridges)                 │
│  - API clients                              │
│  - Python scripts                           │
│  - REST API wrappers                        │
└─────────────────────────────────────────────┘
```

### Connector Structure

**Directory Pattern**:
```
connectors/{connector-name}/
├── {connector-name}.yml       # Definition
├── {connector-name}.py        # Python implementation
├── {connector-name}.json      # REST API spec (alternative)
└── README.md                  # Documentation
```

**YAML Definition** (`openai.yml`):
```yaml
connector:
  name: "openai"
  description: "OpenAI API integration"
  filename: "openai.py"
  filetype: "pyscript"
  commands:
    - name: "Invoke Prompt"
      value: "invoke_prompt"
    - name: "Create Embedding"
      value: "create_embedding"
```

**Python Implementation** (`openai.py`):
```python
def invoke_prompt(params):
    api_key = params.get("api_key")
    messages = params.get("messages", [])
    model = params.get("model", "gpt-4o")

    # Call OpenAI API
    response = client.chat.completions.create(
        model=model,
        messages=messages
    )

    return {"choices": [...], "usage": {...}}
```

### Workflow Task Types

#### 1. Connector Task
Execute external service calls:
```yaml
- type: "connector"
  name: "fetch-match-data"
  connector:
    name: "api-football"
    command: "get_fixtures"
  inputs:
    league_id: "$.get('league')"
    season: "2025"
  outputs:
    fixtures: "$.get('response')"
```

#### 2. Document Task
Database operations (MongoDB):
```yaml
- type: "document"
  name: "save-events"
  config:
    action: "bulk-update"
    embed-vector: false
  document_name: "sport:Event"
  documents:
    events: "$.get('fixtures')"
```

#### 3. Prompt Task
LLM interactions:
```yaml
- type: "prompt"
  name: "generate-analysis"
  connector:
    name: "openai"
    command: "invoke_prompt"
    model: "gpt-4o"
  inputs:
    messages: |
      [{"role": "user", "content": "Analyze: " + $.get('match_data')}]
  outputs:
    analysis: "$.get('choices')[0].get('message').get('content')"
```

## 📦 Installation & Usage

### Import Template (via MCP)

```python
# 1. Import shared connector
mcp__machina_client_dev__get_local_template(
    template="connectors/sportradar-nfl",
    project_path="/app/machina-templates/connectors/sportradar-nfl"
)

# 2. Configure credentials in vault
mcp__machina_client_dev__create_secrets(
    data={
        "name": "TEMP_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY",
        "key": "your-api-key-here"
    }
)

# 3. Test credentials (ALWAYS do this after import!)
mcp__machina_client_dev__execute_workflow(
    name="sportradar-nfl-test-credentials"
)
# Check workflow-status == 'executed' to confirm success

# 4. Import agent template (after connectors are verified)
mcp__machina_client_dev__get_local_template(
    template="agent-templates/soccer-predictions-analyst",
    project_path="/app/machina-templates/agent-templates/soccer-predictions-analyst"
)
```

**Important**: Always test credentials immediately after importing connectors. This catches configuration issues early.

### Environment Variables

All connectors use the `$MACHINA_CONTEXT_VARIABLE_` prefix:

```bash
# OpenAI
MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY=sk-...

# Google Vertex
MACHINA_CONTEXT_VARIABLE_GOOGLE_VERTEX_PROJECT_ID=project-123
MACHINA_CONTEXT_VARIABLE_GOOGLE_VERTEX_CREDENTIALS={"type":"service_account",...}

# SportRadar
MACHINA_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY=...
MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY=...

# WordPress
MACHINA_CONTEXT_VARIABLE_WORDPRESS_URL=https://example.com
MACHINA_CONTEXT_VARIABLE_WORDPRESS_TOKEN=...
```

### Dependencies Between Templates

**Common Pattern**: Import dependencies first, then specific templates

**Example** (Sports Interaction setup):
1. Import `machina-templates` dependencies (13 connectors)
2. Import `entain-templates` specific agents
3. Configure credentials via vault

See [SIA Setup Skill](../../docs/.claude/skills/sia-setup/README.md)

## 🧪 Testing

### Credential Validation Workflows

Most connectors include a `test-credentials.yml` workflow to validate API credentials after installation. **Always run these tests after importing connectors** to verify your credentials are correctly configured.

**Available test-credentials workflows**:

| Connector | Workflow Name | What it Tests |
|-----------|---------------|---------------|
| **openai** | `openai-test-credentials` | Lists available models |
| **groq** | `groq-test-credentials` | Lists available models |
| **google-genai** | `google-genai-test-credentials` | Lists available models |
| **perplexity** | `perplexity-test-credentials` | Minimal chat completion |
| **grok** | `grok-test-credentials` | Minimal chat completion |
| **exa-search** | `exa-search-test-credentials` | Minimal search query |
| **api-football** | `api-football-test-credentials` | Fetches timezone list |
| **sportradar-soccer** | `sportradar-soccer-test-credentials` | Lists competitions |
| **sportradar-nfl** | `sportradar-nfl-test-credentials` | Fetches league schedule |
| **sportradar-nba** | `sportradar-nba-test-credentials` | Fetches league injuries |
| **sportradar-mlb** | `sportradar-mlb-test-credentials` | Fetches schedule |
| **sportradar-nhl** | `sportradar-nhl-test-credentials` | Fetches schedule |
| **bwin** | `bwin-test-credentials` | Fetches language codes |
| **elevenlabs** | `elevenlabs-test-credentials` | Lists available voices |
| **machina-ai** | `machina-ai-test-credentials` | Minimal chat completion |

**How to use**:

```python
# 1. First, create secrets with TEMP_ prefix for testing
mcp__machina_client_dev__create_secrets(
    data={
        "name": "TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY",
        "key": "sk-your-api-key-here"
    }
)

# 2. Execute the test workflow
mcp__machina_client_dev__execute_workflow(
    name="openai-test-credentials"
)

# 3. Check results - workflow-status should be 'executed'
# The 'result' field contains the API response
```

**Best Practice**: After importing any connector, immediately run its test-credentials workflow to verify credentials are working before using in production workflows.

**Naming Convention**: Test credentials use `$TEMP_CONTEXT_VARIABLE_*` prefix. For production, use `$MACHINA_CONTEXT_VARIABLE_*`.

### Unit Tests (sportradar-nfl example)

```bash
cd connectors/sportradar-nfl/scripts/tests
python test_detect_season_type.py

# 13 tests:
# - Season transitions (Aug→Sep, Jan→Feb)
# - Playoff week conversions (19→1, 23→5)
# - Edge cases (Super Bowl, Wild Card)
```

**Test Coverage**: Season detection logic has 100% test coverage

## 🔗 Related Projects

### Documentation Hub
**Path**: `/Users/fernando/machina/docs`
**Docs**: [docs/.claude/CLAUDE.md](../../docs/.claude/CLAUDE.md)

### Client API (Execution Engine)
**Path**: `/Users/fernando/machina/machina-client-api`
**Docs**: [machina-client-api/.claude/CLAUDE.md](../../machina-client-api/.claude/CLAUDE.md)

### Template Consumers
- [DAZN Templates](../../dazn-templates/.claude/CLAUDE.md) - Uses: coverage-tools, assistant-tools
- [Entain Templates](../../entain-templates/.claude/CLAUDE.md) - Uses: sportradar-nfl, bwin, wordpress

## 💡 Best Practices

### Connector Design
- **Single responsibility**: One connector = one service
- **Environment variables**: Always use `$MACHINA_CONTEXT_VARIABLE_` prefix
- **Error handling**: Return structured errors for debugging
- **Documentation**: Include usage examples in README

### Workflow Design
- **JSONPath everywhere**: Use `$.get('field')` for state access
- **Inline Python**: Transform data in `outputs` blocks
- **Conditional tasks**: Use `condition:` to skip unnecessary work
- **Modularity**: Break complex flows into reusable workflows

### Agent Patterns
- **Context variables**: Store API keys and configuration
- **Workflow orchestration**: Chain workflows via inputs/outputs
- **Scheduling**: Use `config-frequency` for periodic execution
- **State management**: Use agent context for persistence

### Template Naming
- **Lowercase with hyphens**: `soccer-predictions-analyst`
- **No prefixes**: Use `openai` not `sdk-openai`
- **Sport-specific**: Include sport in name when relevant
- **Descriptive**: Name should indicate purpose

## 📚 Documentation

### Technical References
- [README.md](../README.md) - Full technical architecture guide
- [NFL Season Detection](../../docs/.claude/features/nfl-season-detection.md) - SportRadar NFL patterns

### Connector Docs
Each connector should have:
- `README.md` - Usage, authentication, examples
- `_install.yml` - Template manifest
- Unit tests (when complex logic exists)

### Agent Template Docs
Each template should have:
- `README.md` - Purpose, workflows, usage
- `_install.yml` - Dependencies and installation
- Example context variables

## 🔍 Common Patterns

### Multi-Sport Coverage
Use abstract patterns that work across sports:
```yaml
workflow:
  name: "sync-fixtures"
  inputs:
    sport: "$.get('sport', 'soccer')"
    league_id: "$.get('league_id')"
  tasks:
    - type: "connector"
      name: "fetch-fixtures"
      connector:
        name: "$.get('sport') + '-api'"
        command: "get_fixtures"
```

### Batch Processing
Process multiple items efficiently:
```yaml
- type: "connector"
  name: "process-batch"
  foreach:
    items: "$.get('fixture_list')"
    item: "fixture"
    concurrent: true  # Parallel processing
  connector:
    name: "api-football"
    command: "get_match_details"
  inputs:
    match_id: "$.get('fixture').get('id')"
```

### Error Recovery
Graceful fallbacks:
```yaml
- type: "connector"
  name: "try-primary-api"
  condition: "$.get('use_primary', True)"
  connector:
    name: "sportradar-soccer"
    command: "get_data"
  # If fails, fallback workflow catches it
```

## 🚀 Quick Start Tutorial

**Create a "Hello World" connector**:

1. **Create directory**: `connectors/hello-world/`
2. **Define connector** (`hello-world.yml`):
```yaml
connector:
  name: "hello-world"
  filename: "hello.py"
  filetype: "pyscript"
  commands:
    - name: "Say Hello"
      value: "say_hello"
```

3. **Implement** (`hello.py`):
```python
def say_hello(args):
    name = args.get("name", "World")
    return {"message": f"Hello, {name}!"}
```

4. **Create workflow** (`agent-templates/tutorial/hello-workflow.yml`):
```yaml
workflow:
  name: "hello-flow"
  tasks:
    - type: "connector"
      name: "greet"
      connector:
        name: "hello-world"
        command: "say_hello"
      inputs:
        name: "'Developer'"
      outputs:
        greeting: "$.get('message')"
```

5. **Import and test**:
```python
mcp__machina_client_dev__get_local_template(
    template="connectors/hello-world",
    project_path="/app/machina-templates/connectors/hello-world"
)
```

---

**Last Updated**: 2026-01-16
**Maintained by**: Claude Code (automated)
**Total Templates**: 24 agent templates + 38 connectors
**Test Workflows**: 15 credential validation workflows
