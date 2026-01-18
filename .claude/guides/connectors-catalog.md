# Machina Connectors Catalog

**Version**: 1.0  
**Last Updated**: 2026-01-17  
**Repository**: [machina-templates/connectors](https://github.com/machina-sports/machina-templates/tree/main/connectors)

## 📋 Overview

This catalog documents all available connectors in the Machina platform. Connectors are reusable integrations with external services and APIs, used by agents and workflows to access data, generate content, and interact with third-party systems.

**Total Connectors**: 35
**Connector Types**:
- **PyScript** - Python-based connectors with custom logic
- **REST API** - OpenAPI spec-based REST connectors

## 🔍 Quick Reference Index

### By Category

| Category | Connectors | Count |
|----------|-----------|-------|
| **AI/LLM Services** | openai, google-genai, groq, grok, perplexity, machina-ai, machina-ai-fast | 7 |
| **Sports Data** | api-football, sportradar-soccer, sportradar-nfl, sportradar-nba, sportradar-mlb, sportradar-nhl, sportradar-rugby, sportradar-tennis, opta (stats-perform), american-football, mlb-statsapi, fastf1 | 12 |
| **Content & Publishing** | wordpress, elevenlabs, google-speech-to-text, docling | 4 |
| **Storage & Files** | google-storage, google-storage-v2, storage, temp-downloader | 4 |
| **Data & Search** | exa-search, oxylabs, rss-feed | 3 |
| **Betting & Markets** | bwin, tallysight | 2 |
| **Support & Services** | zendesk | 1 |
| **Media Generation** | stability | 1 |

### Alphabetical Index

| Connector | Type | Category | Key Commands |
|-----------|------|----------|--------------|
| american-football | REST | Sports Data | (OpenAPI spec) |
| api-football | REST | Sports Data | (OpenAPI spec) |
| bwin | REST | Betting | (OpenAPI spec) |
| docling | PyScript | Content | (see connector yml) |
| elevenlabs | PyScript | Content | (see connector yml) |
| exa-search | REST | Data | (OpenAPI spec) |
| fastf1 | PyScript | Sports Data | (see connector yml) |
| google-genai | PyScript | AI/LLM | invoke_prompt, invoke_image, invoke_video, invoke_search |
| google-speech-to-text | PyScript | Content | (see connector yml) |
| google-storage | PyScript | Storage | (see connector yml) |
| google-storage-v2 | PyScript | Storage | invoke_upload |
| grok | REST | AI/LLM | (OpenAPI spec) |
| groq | PyScript | AI/LLM | invoke_prompt |
| machina-ai | PyScript | AI/LLM | invoke_prompt |
| machina-ai-fast | PyScript | AI/LLM | invoke_prompt |
| mlb-statsapi | REST | Sports Data | (OpenAPI spec) |
| openai | PyScript | AI/LLM | list_models, invoke_embedding, invoke_prompt, transcribe_audio_to_text |
| opta | PyScript | Sports Data | authorization, invoke_request |
| oxylabs | REST | Data | (OpenAPI spec) |
| perplexity | REST | AI/LLM | (OpenAPI spec) |
| rss-feed | PyScript | Data | (see connector yml) |
| sportradar-mlb | REST | Sports Data | (OpenAPI spec) |
| sportradar-nba | REST | Sports Data | (OpenAPI spec) |
| sportradar-nfl | REST | Sports Data | (OpenAPI spec) |
| sportradar-nhl | REST | Sports Data | (OpenAPI spec) |
| sportradar-rugby | REST | Sports Data | (OpenAPI spec) |
| sportradar-soccer | REST | Sports Data | (OpenAPI spec) |
| sportradar-tennis | REST | Sports Data | (OpenAPI spec) |
| stability | PyScript | Media | (see connector yml) |
| storage | PyScript | Storage | (see connector yml) |
| tallysight | REST | Betting | (OpenAPI spec) |
| temp-downloader | PyScript | Storage | (see connector yml) |
| wordpress | REST | Content | (OpenAPI spec) |
| zendesk | PyScript | Support | (see connector yml) |

**Note**: REST connectors use OpenAPI specs - check the `.json` file in each connector directory for available endpoints. PyScript connectors define commands in their `.yml` file.

---

## 🚀 Priority Connectors (Detailed Documentation)

The following connectors are documented in detail due to their high usage and importance in the platform.

### 1. OpenAI (`openai`)

**Type**: PyScript  
**Category**: AI/LLM Services  
**Location**: `machina-templates/connectors/openai/`

**Description**:  
Official OpenAI SDK connector providing access to GPT models, embeddings, and audio transcription via the OpenAI API.

**Environment Variables**:
- `MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY` - OpenAI API key

**Commands**:

#### `invoke_prompt`
Invoke a GPT model for text generation.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | OpenAI API key |
| model_name | string | Yes | Model ID (e.g., "gpt-4", "gpt-3.5-turbo") |

**Output**:
```json
{
  "status": true,
  "data": "<ChatOpenAI object>",
  "message": "Model loaded."
}
```

**Example Workflow YAML**:
```yaml
- task: llm-generate
  name: Generate content with GPT-4
  connector: 
    name: openai
    command: invoke_prompt
  params:
    api_key: $MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY
    model_name: "gpt-4"
```

#### `invoke_embedding`
Generate embeddings for text.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | OpenAI API key |
| model_name | string | Yes | Embedding model (e.g., "text-embedding-3-small") |

**Output**:
```json
{
  "status": true,
  "data": "<OpenAIEmbeddings object>",
  "message": "Model loaded."
}
```

#### `transcribe_audio_to_text`
Transcribe audio files using Whisper.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | OpenAI API key (via headers) |
| audio-path | array | Yes | Path to audio file |

**Output**:
```json
{
  "status": true,
  "data": "Transcribed text..."
}
```

---

### 2. Google GenAI (`google-genai`)

**Type**: PyScript  
**Category**: AI/LLM Services  
**Location**: `machina-templates/connectors/google-genai/`

**Description**:  
Google Gemini models connector supporting text, image, video generation, and web-grounded search.

**Environment Variables**:
- `MACHINA_CONTEXT_VARIABLE_GOOGLE_GENAI_API_KEY` - Google GenAI API key

**Commands**:

#### `invoke_prompt`
Generate text using Gemini models.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | Google GenAI API key |
| model_name | string | Yes | Model ID (e.g., "gemini-1.5-pro") |

**Example Workflow YAML**:
```yaml
- task: llm-generate
  name: Generate with Gemini
  connector:
    name: google-genai
    command: invoke_prompt
  params:
    api_key: $MACHINA_CONTEXT_VARIABLE_GOOGLE_GENAI_API_KEY
    model_name: "gemini-1.5-pro"
```

#### `invoke_image`
Generate images using Gemini.

#### `invoke_video`
Generate or analyze video content.

#### `invoke_search`
Perform web-grounded search with Gemini.

---

### 3. Sportradar NFL (`sportradar-nfl`)

**Type**: REST API  
**Category**: Sports Data  
**Location**: `machina-templates/connectors/sportradar-nfl/`

**Description**:  
Sportradar NFL API v7 connector for accessing NFL schedules, game data, injuries, and statistics.

**Environment Variables**:
- `MACHINA_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY` - Sportradar API key

**Key Features**:
- Automatic season type detection (PRE/REG/PST)
- Playoff week conversion (19→1, 20→2)
- Injury synchronization for current + next week
- Extensive unit test coverage

**REST Endpoints** (via OpenAPI spec):

#### `GET /games/{year}/{season_type}/schedule.json`
Get season schedule.

**Parameters**:
| Parameter | Location | Type | Required | Description |
|-----------|----------|------|----------|-------------|
| api_key | query | string | Yes | API key |
| year | path | integer | Yes | Season year |
| season_type | path | string | Yes | REG, PRE, or PST |

**Example Workflow YAML**:
```yaml
- task: rest-api-get
  name: Get NFL schedule
  connector:
    name: sportradar-nfl
    endpoint: /games/{year}/{season_type}/schedule.json
  params:
    api_key: $MACHINA_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY
    year: 2024
    season_type: "REG"
```

#### `GET /games/{game_id}/summary.json`
Get detailed game summary.

#### `GET /teams/{team_id}/injuries.json`
Get team injury report.

**Documentation**: See [NFL Season Detection](../features/nfl-season-detection.md)

---

### 4. WordPress (`wordpress`)

**Type**: PyScript  
**Category**: Content & Publishing  
**Location**: `machina-templates/connectors/wordpress/`

**Description**:  
WordPress REST API connector for creating, updating, and managing posts and content.

**Commands**:

#### `create_post`
Create a new WordPress post.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| url | string | Yes | WordPress site URL |
| username | string | Yes | WordPress username |
| password | string | Yes | Application password |
| title | string | Yes | Post title |
| content | string | Yes | Post content (HTML) |
| status | string | No | Post status (draft/publish) |
| categories | array | No | Category IDs |
| tags | array | No | Tag IDs |

**Output**:
```json
{
  "status": true,
  "data": {
    "id": 123,
    "link": "https://site.com/post-slug"
  }
}
```

**Example Workflow YAML**:
```yaml
- task: publish-content
  name: Create WordPress post
  connector:
    name: wordpress
    command: create_post
  params:
    url: "https://blog.example.com"
    username: $WP_USERNAME
    password: $WP_APP_PASSWORD
    title: "New Article Title"
    content: "<p>Article content here</p>"
    status: "publish"
```

#### `update_post`
Update an existing post.

#### `get_posts`
Retrieve posts by criteria.

---

### 5. API-Football (`api-football`)

**Type**: REST API  
**Category**: Sports Data  
**Location**: `machina-templates/connectors/api-football/`

**Description**:  
Comprehensive soccer data API providing fixtures, standings, statistics, and predictions for 1000+ competitions worldwide.

**Environment Variables**:
- `MACHINA_CONTEXT_VARIABLE_API_FOOTBALL_KEY` - API-Football API key

**Key Features**:
- 1000+ soccer leagues and cups
- Live scores and statistics
- H2H records and predictions
- Player and team statistics

**REST Endpoints**:

#### `GET /fixtures`
Get fixtures by various criteria.

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| league | integer | No | League ID |
| season | integer | No | Season year |
| date | string | No | Date (YYYY-MM-DD) |
| team | integer | No | Team ID |

**Example Workflow YAML**:
```yaml
- task: rest-api-get
  name: Get fixtures
  connector:
    name: api-football
    endpoint: /fixtures
  headers:
    x-rapidapi-key: $MACHINA_CONTEXT_VARIABLE_API_FOOTBALL_KEY
  params:
    league: 39
    season: 2024
    date: "2024-01-15"
```

#### `GET /standings`
Get league standings.

#### `GET /fixtures/headtohead`
Get head-to-head records between teams.

---

### 6. Sportradar Soccer (`sportradar-soccer`)

**Type**: REST API  
**Category**: Sports Data  
**Location**: `machina-templates/connectors/sportradar-soccer/`

**Description**:  
Sportradar Soccer API for accessing match schedules, lineups, statistics, and live data.

**Environment Variables**:
- `MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_API_KEY` - Sportradar API key

**REST Endpoints**:

#### `GET /schedules/{date}/schedule.json`
Get matches for a specific date.

#### `GET /sport_events/{event_id}/summary.json`
Get detailed match summary with lineups and stats.

**Example Workflow YAML**:
```yaml
- task: rest-api-get
  name: Get soccer schedule
  connector:
    name: sportradar-soccer
    endpoint: /schedules/{date}/schedule.json
  params:
    api_key: $MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_API_KEY
    date: "2024-01-15"
```

---

### 7. Google Storage (`google-storage`, `google-storage-v2`)

**Type**: PyScript  
**Category**: Storage & Files  
**Location**: `machina-templates/connectors/google-storage/`

**Description**:  
Google Cloud Storage connector for uploading, downloading, and managing files in GCS buckets.

**Commands** (`google-storage`):

#### `upload_file`
Upload a file to GCS.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| bucket_name | string | Yes | GCS bucket name |
| source_file | string | Yes | Local file path |
| destination_blob | string | Yes | Destination path in bucket |
| credentials_json | string | Yes | Service account JSON |

**Output**:
```json
{
  "status": true,
  "data": {
    "blob_name": "path/to/file.txt",
    "public_url": "https://storage.googleapis.com/..."
  }
}
```

**Example Workflow YAML**:
```yaml
- task: upload-file
  name: Upload to GCS
  connector:
    name: google-storage
    command: upload_file
  params:
    bucket_name: "my-bucket"
    source_file: "/tmp/data.json"
    destination_blob: "data/output.json"
    credentials_json: $GCS_CREDENTIALS
```

#### `download_file`
Download a file from GCS.

---

### 9. ElevenLabs (`elevenlabs`)

**Type**: PyScript  
**Category**: Media Generation  
**Location**: `machina-templates/connectors/elevenlabs/`

**Description**:  
ElevenLabs text-to-speech connector for generating high-quality voice audio.

**Commands**:

#### `generate_audio`
Generate speech audio from text.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | ElevenLabs API key |
| text | string | Yes | Text to convert |
| voice_id | string | Yes | Voice ID |
| model_id | string | No | Model ID (default: eleven_monolingual_v1) |

**Output**:
```json
{
  "status": true,
  "data": {
    "audio_path": "/tmp/audio.mp3"
  }
}
```

**Example Workflow YAML**:
```yaml
- task: generate-audio
  name: Create podcast audio
  connector:
    name: elevenlabs
    command: generate_audio
  params:
    api_key: $ELEVENLABS_API_KEY
    text: "Welcome to the podcast..."
    voice_id: "21m00Tcm4TlvDq8ikWAM"
```

---

### 10. Perplexity (`perplexity`)

**Type**: PyScript  
**Category**: AI/LLM Services  
**Location**: `machina-templates/connectors/perplexity/`

**Description**:  
Perplexity AI connector for web-grounded search and question answering.

**Commands**:

#### `web_search`
Perform web search with AI summarization.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | Perplexity API key |
| query | string | Yes | Search query |
| model | string | No | Model ID |

**Example Workflow YAML**:
```yaml
- task: web-search
  name: Research topic
  connector:
    name: perplexity
    command: web_search
  params:
    api_key: $PERPLEXITY_API_KEY
    query: "Latest NFL injury updates"
```

---

### 11. Groq (`groq`)

**Type**: PyScript  
**Category**: AI/LLM Services  
**Location**: `machina-templates/connectors/groq/`

**Description**:  
Groq fast inference connector for LLama and Mixtral models with ultra-low latency.

**Commands**:

#### `invoke_prompt`
Generate text with Groq models.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | Groq API key |
| model_name | string | Yes | Model ID (e.g., "llama-3.1-70b") |

**Example Workflow YAML**:
```yaml
- task: llm-generate
  name: Fast generation with Groq
  connector:
    name: groq
    command: invoke_prompt
  params:
    api_key: $MACHINA_CONTEXT_VARIABLE_GROQ_API_KEY
    model_name: "llama-3.1-70b-versatile"
```

---

### 12. FastF1 (`fastf1`)

**Type**: PyScript  
**Category**: Sports Data  
**Location**: `machina-templates/connectors/fastf1/`

**Description**:  
Formula 1 data connector using the FastF1 library for telemetry, lap times, and session data.

**Commands**:

#### `get_session`
Get F1 session data.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| year | integer | Yes | Season year |
| event | string/integer | Yes | Event name or round number |
| session | string | Yes | Session type (FP1, FP2, FP3, Q, R) |

**Example Workflow YAML**:
```yaml
- task: get-f1-data
  name: Get qualifying session
  connector:
    name: fastf1
    command: get_session
  params:
    year: 2024
    event: "Monaco"
    session: "Q"
```

#### `get_telemetry`
Get telemetry data for specific laps.

---

### 13. Stats Perform (`stats-perform`)

**Type**: REST API  
**Category**: Sports Data  
**Location**: `machina-templates/connectors/stats-perform/`

**Description**:  
Stats Perform multi-sport data provider with fixtures, standings, and statistics.

**REST Endpoints**:

#### `GET /fixtures`
Get fixtures for multiple sports.

**Example Workflow YAML**:
```yaml
- task: rest-api-get
  name: Get fixtures
  connector:
    name: stats-perform
    endpoint: /fixtures
  params:
    api_key: $STATS_PERFORM_API_KEY
    sport: "soccer"
    date: "2024-01-15"
```

---

### 14. Exa Search (`exa-search`)

**Type**: PyScript  
**Category**: Data & Search  
**Location**: `machina-templates/connectors/exa-search/`

**Description**:  
Exa web search connector for AI-powered web research and content discovery.

**Commands**:

#### `web_search`
Search the web with AI ranking.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | Exa API key |
| query | string | Yes | Search query |
| num_results | integer | No | Number of results (default: 10) |

**Example Workflow YAML**:
```yaml
- task: web-search
  name: Research content
  connector:
    name: exa-search
    command: web_search
  params:
    api_key: $EXA_API_KEY
    query: "NFL playoff predictions 2024"
    num_results: 5
```

---

### 15. Stability AI (`stability`)

**Type**: PyScript  
**Category**: Media Generation  
**Location**: `machina-templates/connectors/stability/`

**Description**:  
Stability AI connector for image generation using Stable Diffusion models.

**Commands**:

#### `generate_image`
Generate images from text prompts.

**Input Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| api_key | string | Yes | Stability API key |
| prompt | string | Yes | Text prompt |
| width | integer | No | Image width |
| height | integer | No | Image height |

**Example Workflow YAML**:
```yaml
- task: generate-image
  name: Create article image
  connector:
    name: stability
    command: generate_image
  params:
    api_key: $STABILITY_API_KEY
    prompt: "Soccer stadium during sunset"
    width: 1024
    height: 1024
```

---

## 📦 Lightweight Connector Documentation

The following connectors are documented with essential information only.

### AI/LLM Services

#### `grok`
**Type**: PyScript  
**Purpose**: xAI Grok model access  
**Key Command**: `invoke_prompt`

#### `machina-ai`
**Type**: PyScript  
**Purpose**: Custom Machina LLM wrapper  
**Key Command**: `invoke_prompt`

#### `machina-ai-fast`
**Type**: PyScript  
**Purpose**: Fast inference variant of machina-ai  
**Key Command**: `invoke_prompt`

---

### Sports Data APIs

#### `american-football`
**Type**: REST API  
**Purpose**: American football data  
**Key Endpoints**: `/schedule`, `/roster`

#### `mlb-statsapi`
**Type**: PyScript  
**Purpose**: MLB statistics via MLB Stats API  
**Key Commands**: `get_games`, `get_standings`

#### `sportradar-nba`
**Type**: REST API  
**Purpose**: NBA data via Sportradar  
**Key Endpoints**: `/schedule`, `/standings`, `/game_summary`

#### `sportradar-mlb`
**Type**: REST API  
**Purpose**: MLB data via Sportradar  
**Key Endpoints**: `/schedule`, `/boxscore`

#### `sportradar-nhl`
**Type**: REST API  
**Purpose**: NHL data via Sportradar  
**Key Endpoints**: `/schedule`, `/standings`

#### `sportradar-rugby`
**Type**: REST API  
**Purpose**: Rugby data via Sportradar  
**Key Endpoints**: `/schedule`, `/match_summary`

#### `sportradar-tennis`
**Type**: REST API  
**Purpose**: Tennis data via Sportradar  
**Key Endpoints**: `/schedule`, `/rankings`, `/match_summary`

---

### Content & Publishing

#### `google-speech-to-text`
**Type**: PyScript  
**Purpose**: Audio transcription via Google Cloud  
**Key Command**: `transcribe_audio`

#### `docling`
**Type**: PyScript  
**Purpose**: Document conversion and processing  
**Key Command**: `convert_document`

---

### Storage & Files

#### `storage`
**Type**: PyScript  
**Purpose**: Generic storage operations  
**Key Commands**: `save_file`, `load_file`

#### `temp-downloader`
**Type**: PyScript  
**Purpose**: Temporary file download and handling  
**Key Command**: `download_temp_file`

---

### Data & Search

#### `oxylabs`
**Type**: PyScript  
**Purpose**: Web scraping proxy service  
**Key Command**: `scrape_website`

#### `rss-feed`
**Type**: PyScript  
**Purpose**: RSS feed parsing and fetching  
**Key Commands**: `fetch_feed`, `parse_feed`

---

### Betting & Markets

#### `bwin`
**Type**: REST API  
**Purpose**: Bwin betting odds and markets  
**Key Endpoints**: `/odds`, `/markets`

#### `kalshi`
**Type**: REST API  
**Purpose**: Kalshi prediction markets  
**Key Endpoints**: `/markets`, `/trades`

#### `tallysight`
**Type**: PyScript  
**Purpose**: Sports betting analytics  
**Key Command**: `get_analytics`

---

### Support & Services

#### `zendesk`
**Type**: REST API  
**Purpose**: Zendesk support ticket management  
**Key Endpoints**: `/tickets`, `/users`

---

## 🔧 Usage Patterns

### Using Connectors in Workflows

Connectors are invoked in workflow YAML files using the following patterns:

**PyScript Connector (with command)**:
```yaml
- task: task-name
  name: Descriptive name
  connector:
    name: connector-name
    command: command-name
  params:
    param1: value1
    param2: value2
```

**REST API Connector (with endpoint)**:
```yaml
- task: rest-api-get
  name: Descriptive name
  connector:
    name: connector-name
    endpoint: /path/to/endpoint
  headers:
    Authorization: Bearer $API_KEY
  params:
    query_param: value
```

### Environment Variables

Most connectors use environment variables for API keys and credentials. These are referenced with the `$MACHINA_CONTEXT_VARIABLE_` prefix:

```yaml
params:
  api_key: $MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY
```

Common environment variable patterns:
- `$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_GOOGLE_GENAI_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_NFL_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_API_FOOTBALL_KEY`

### Error Handling

Connectors return standardized response formats:

**Success Response**:
```json
{
  "status": true,
  "data": { ... },
  "message": "Success message"
}
```

**Error Response**:
```json
{
  "status": false,
  "message": "Error description"
}
```

### Data Abstraction in Workflow Outputs

**Important**: The SDK automatically unwraps the `data` object when passing values to workflow outputs.

**In the connector (Python):**
```python
def invoke_upload(request_data):
    # ... processing ...
    return {
        "status": True,
        "data": {                         # Results go inside "data"
            "video_path": "/tmp/video.mp4",
            "filename": "output.mp4",
            "duration": 30
        },
        "message": "Upload successful"
    }
```

**In the workflow (YAML):**
```yaml
- type: connector
  name: upload-video
  connector:
    name: google-storage
    command: invoke_upload
  inputs:
    file_path: "$.get('source_path')"
  outputs:
    video_path: "$.get('video_path')"    # Access directly, NOT $.get('data').get('video_path')
    filename: "$.get('filename')"
    duration: "$.get('duration')"
```

**How it works:**
```
Connector returns:              Workflow context receives:
─────────────────────           ──────────────────────────
{
  "status": True,         →     status = True
  "data": {               →     video_path = "/tmp/video.mp4"
    "video_path": "...",  →     filename = "output.mp4"
    "filename": "...",    →     duration = 30
    "duration": 30        →     message = "Upload successful"
  },
  "message": "..."
}
```

**Key points:**
- ✅ Use `$.get('field')` to access fields from `data`
- ✅ `status` and `message` are also available directly
- ❌ Do NOT use `$.get('data').get('field')` - the unwrapping is automatic

---

## 📚 Additional Resources

### Connector Development
- **Location**: `machina-templates/connectors/`
- **Template Structure**:
  ```
  connector-name/
  ├── connector-name.yml      # Connector metadata
  ├── connector-name.py       # PyScript implementation
  ├── connector-name.json     # OpenAPI spec (REST)
  ├── _install.yml           # Installation metadata
  └── test-credentials.yml   # Credential tests
  ```

### Related Documentation
- [Template Development Workflow](./template-development-workflow.md)
- [Template Creation Guide](./template-creation-guide.md)
- [NFL Season Detection Feature](../features/nfl-season-detection.md)
- [machina-templates CLAUDE.md](https://github.com/machina-sports/machina-templates/blob/main/.claude/CLAUDE.md)

### Testing Connectors

Connectors can be tested using the credential test files:
```yaml
# test-credentials.yml example
test:
  connector: connector-name
  command: test-command
  params:
    api_key: $TEST_API_KEY
```

---

## 🔄 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-17 | Initial catalog creation with 38 connectors |

---

**Maintained by**: Machina Platform Team  
**Last Review**: 2026-01-17  
**Next Review**: 2026-04-17 (Quarterly)

