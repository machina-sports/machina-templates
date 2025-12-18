# Storage and External APIs

## Google Cloud Storage

Machina integrates with Google Cloud Storage for file storage and management.

### Upload Files

```yaml
- type: connector
  name: upload-to-storage
  connector:
    name: "storage"
    command: "upload_file"
  inputs:
    file_data: "$.get('file_content')"
    file_name: "'my-file.txt'"
    bucket: "'machina-storage'"
    content_type: "'text/plain'"
  outputs:
    file_url: "$.get('public_url')"
    file_id: "$.get('file_id')"
```

### Download Files

```yaml
- type: connector
  name: download-from-storage
  connector:
    name: "storage"
    command: "download_file"
  inputs:
    file_path: "'path/to/file.txt'"
    bucket: "'machina-storage'"
  outputs:
    file_content: "$.get('content')"
```

### List Files

```yaml
- type: connector
  name: list-storage-files
  connector:
    name: "storage"
    command: "list_files"
  inputs:
    prefix: "'podcasts/2025/'"
    bucket: "'machina-storage'"
  outputs:
    files: "$.get('files', [])"
```

## OxyLabs Web Scraping

OxyLabs provides web scraping and proxy services for data collection.

### Basic Web Scraping

```yaml
context-variables:
  oxylabs:
    username: "$MACHINA_CONTEXT_VARIABLE_OXYLABS_USERNAME"
    password: "$MACHINA_CONTEXT_VARIABLE_OXYLABS_PASSWORD"

tasks:
  - type: connector
    name: scrape-website
    connector:
      name: "oxylabs"
      command: "scrape_url"
    inputs:
      url: "'https://example.com/sports-news'"
      render: "true"  # Enable JavaScript rendering
      country: "'US'"
    outputs:
      html_content: "$.get('content')"
      status_code: "$.get('status_code')"
```

### Web Search with OxyLabs

```yaml
- type: connector
  name: search-web
  connector:
    name: "oxylabs"
    command: "google_search"
  inputs:
    query: "'Premier League latest news'"
    num_results: "10"
    country: "'US'"
  outputs:
    search_results: "$.get('results', [])"
```

### E-commerce Scraping

```yaml
- type: connector
  name: scrape-product
  connector:
    name: "oxylabs"
    command: "ecommerce_scrape"
  inputs:
    url: "'https://example.com/product/123'"
    platform: "'amazon'"
  outputs:
    product_data: "$"
```

## Sports Data APIs

### SportRadar API

Comprehensive sports data for multiple sports.

#### Get Match Information

```yaml
context-variables:
  sportradar-soccer:
    sportradar_api_key: "$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY"

tasks:
  - type: connector
    name: get-match-data
    connector:
      name: "sportradar-soccer"
      command: "get_match"
    inputs:
      match_id: "'sr:match:12345'"
    outputs:
      match_data: "$"
      home_team: "$.get('sport_event', {}).get('competitors', [])[0]"
      away_team: "$.get('sport_event', {}).get('competitors', [])[1]"
```

#### Get League Standings

```yaml
- type: connector
  name: get-standings
  connector:
    name: "sportradar-soccer"
    command: "get_standings"
  inputs:
    competition_id: "'sr:competition:17'"  # Premier League
    season: "'2024'"
  outputs:
    standings: "$.get('standings', [])"
```

#### Get Player Statistics

```yaml
- type: connector
  name: get-player-stats
  connector:
    name: "sportradar-soccer"
    command: "get_player_profile"
  inputs:
    player_id: "'sr:player:123456'"
  outputs:
    player_info: "$"
    career_stats: "$.get('statistics', {})"
```

### API Football

Alternative football data API.

```yaml
context-variables:
  api-football:
    api_key: "$MACHINA_CONTEXT_VARIABLE_API_FOOTBALL_KEY"

tasks:
  - type: connector
    name: get-fixtures
    connector:
      name: "api-football"
      command: "get_fixtures"
    inputs:
      league: "39"  # Premier League
      season: "2024"
      date: "'2025-01-15'"
    outputs:
      fixtures: "$.get('response', [])"
```

### SportRadar NBA

```yaml
context-variables:
  sportradar-nba:
    api_key: "$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_NBA_API_KEY"

tasks:
  - type: connector
    name: get-nba-game
    connector:
      name: "sportradar-nba"
      command: "get_game"
    inputs:
      game_id: "'sr:match:nba12345'"
    outputs:
      game_data: "$"
      home_score: "$.get('home', {}).get('points')"
      away_score: "$.get('away', {}).get('points')"
```

## IPTC Mappings

IPTC (International Press Telecommunications Council) standard for sports data mapping.

### Map SportRadar to IPTC

```yaml
- type: mapping
  name: map-to-iptc
  connector:
    name: "iptc-mapper"
    command: "sportradar_to_iptc"
  inputs:
    sportradar_data: "$.get('match_data')"
  outputs:
    iptc_format: "$"
```

### IPTC Event Structure

```json
{
  "event_id": "iptc:event:12345",
  "sport": {
    "id": "football",
    "name": "Football"
  },
  "competition": {
    "id": "iptc:comp:premier-league",
    "name": "Premier League"
  },
  "participants": [
    {
      "id": "iptc:team:123",
      "name": "Manchester United",
      "role": "home"
    },
    {
      "id": "iptc:team:456",
      "name": "Liverpool",
      "role": "away"
    }
  ],
  "event_status": "scheduled",
  "start_date": "2025-01-15T20:00:00Z",
  "venue": {
    "name": "Old Trafford",
    "city": "Manchester"
  }
}
```

## Perplexity AI (Web Search)

Search the web using Perplexity AI:

```yaml
context-variables:
  perplexity:
    api_key: "$MACHINA_CONTEXT_VARIABLE_PERPLEXITY_API_KEY"

tasks:
  - type: connector
    name: web-search
    connector:
      name: "perplexity"
      command: "search"
    inputs:
      query: "'Latest news about Premier League transfers'"
      return_citations: "true"
    outputs:
      search_results: "$.get('results')"
      citations: "$.get('citations', [])"
```

## Exa Search

Semantic web search:

```yaml
context-variables:
  exa-search:
    api_key: "$MACHINA_CONTEXT_VARIABLE_EXA_SEARCH_API_KEY"

tasks:
  - type: connector
    name: semantic-search
    connector:
      name: "exa-search"
      command: "search"
    inputs:
      query: "'In-depth analysis of Liverpool's tactics'"
      num_results: "10"
      include_content: "true"
    outputs:
      results: "$.get('results', [])"
```

## Best Practices

### API Rate Limiting

Implement rate limiting and error handling:

```yaml
- type: connector
  name: api-call-with-retry
  connector:
    name: "sportradar-soccer"
    command: "get_match"
  inputs:
    match_id: "$.get('match_id')"
    retry_count: "3"
    retry_delay: "2"
  outputs:
    data: "$"
    api_status: "$.get('status')"
```

### Caching API Responses

Store API responses in the database:

```yaml
tasks:
  # Check cache first
  - type: document
    name: check-cache
    config:
      action: search
      search-vector: false
    filters:
      name: "'api-cache'"
    inputs:
      metadata.cache_key: "f\"match-{$.get('match_id')}\""
    outputs:
      cached_data: "$.get('documents', [])"
  
  # Call API if not cached
  - type: connector
    name: fetch-from-api
    condition: "len($.get('cached_data', [])) == 0"
    connector:
      name: "sportradar-soccer"
      command: "get_match"
    inputs:
      match_id: "$.get('match_id')"
    outputs:
      fresh_data: "$"
  
  # Save to cache
  - type: document
    name: save-to-cache
    condition: "$.get('fresh_data') is not None"
    config:
      action: save
      embed-vector: false
    documents:
      api-cache: "$.get('fresh_data')"
    metadata:
      cache_key: "f\"match-{$.get('match_id')}\""
      cached_at: "datetime.now().isoformat()"
      ttl_hours: "24"
```

### Error Handling

```yaml
- type: connector
  name: safe-api-call
  connector:
    name: "sportradar-soccer"
    command: "get_match"
  inputs:
    match_id: "$.get('match_id')"
  outputs:
    success: "$.get('status') == 'success'"
    data: "$ if $.get('status') == 'success' else None"
    error: "$.get('error') if $.get('status') != 'success' else None"
```

### Cost Optimization

1. **Cache aggressively**: Store API responses
2. **Batch requests**: Combine multiple queries when possible
3. **Use appropriate endpoints**: Choose the most efficient endpoint
4. **Monitor usage**: Track API call counts and costs
5. **Implement fallbacks**: Have backup data sources

