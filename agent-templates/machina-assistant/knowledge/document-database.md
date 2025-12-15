# Document Database and Vector Search

## Overview

Machina includes a MongoDB-based document database with vector search capabilities. This allows you to store, search, and retrieve documents using both traditional queries and semantic similarity search.

## Document Structure

Every document in Machina has:
- `_id`: Unique identifier
- `name`: Document type/collection name
- `value`: The actual content (flexible JSON object)
- `metadata`: Additional information for filtering
- `embedding`: Vector representation (for semantic search)

## Document Actions

### 1. Save Document

Create or save a new document:

```yaml
- type: document
  name: save-game-data
  config:
    action: save
    embed-vector: true  # Generate embeddings
    force-update: false
  documents:
    sport:Event: |
      {
        'title': 'Manchester United vs Liverpool',
        'sport_id': '4',
        'event_code': 'sr:match:12345',
        'start_date': '2025-01-15T20:00:00Z',
        'teams': ['Manchester United', 'Liverpool']
      }
  metadata:
    event_code: "'sr:match:12345'"
    sport_id: "'4'"
    league: "'Premier League'"
```

### 2. Search Documents

Search with filters:

```yaml
- type: document
  name: search-events
  config:
    action: search
    search-limit: 10
    search-vector: false
  filters:
    name: "'sport:Event'"
    sport_id: "'4'"
  inputs:
    metadata.league: "'Premier League'"
  outputs:
    events: "$.get('documents', [])"
```

### 3. Vector Search

Semantic search using embeddings:

```yaml
- type: document
  name: search-similar-content
  description: "Find similar documents using vector search"
  config:
    action: search
    threshold-docs: 5
    threshold-similarity: 0.01
    search-limit: 1000
    search-vector: true
  connector:
    name: "machina-ai"
    command: "invoke_embedding"
    model: "text-embedding-3-small"
  inputs:
    name: "'content-snippet'"
    search-query: "$.get('user_query')"
  outputs:
    similar_docs: |
      [
        {
          **d.get('value', {}),
          'similarity': d.get('similarity_score', 0)
        }
        for d in $.get('documents', [])
      ]
```

### 4. Update Document

Update existing documents:

```yaml
- type: document
  name: update-thread
  config:
    action: update
    embed-vector: false
    force-update: true
  documents:
    thread: |
      {
        **$.get('existing_thread'),
        'messages': [
          *$.get('existing_thread').get('messages', []),
          $.get('new_message')
        ],
        'updated_at': datetime.now().isoformat()
      }
  filters:
    document_id: "$.get('thread_id')"
```

### 5. Bulk Update

Update multiple documents at once:

```yaml
- type: document
  name: bulk-update-events
  config:
    action: bulk-update
    embed-vector: false
    force-update: true
  documents:
    sport:Event: "$.get('events_to_update')"
```

## Common Document Types

### sport:Event
Sports events/matches:
```python
{
  'title': 'Team A vs Team B',
  'sport_id': '4',  # 4=Football, 5=Tennis, 11=Basketball
  'event_code': 'sr:match:12345',
  'start_date': '2025-01-15T20:00:00Z',
  'home_team': 'Team A',
  'away_team': 'Team B',
  'competition': 'League Name',
  'status': 'scheduled'  # or 'live', 'finished'
}
```

### sport:Team
Team information:
```python
{
  'name': 'Manchester United',
  'team_code': 'sr:team:123',
  'sport_id': '4',
  'country': 'England',
  'logo_url': 'https://...'
}
```

### content-snippet
Knowledge base articles:
```python
{
  'title': 'How to create workflows',
  'content': 'Full text content here...',
  'category': 'documentation',
  'tags': ['workflow', 'tutorial']
}
```

### content-article
Blog posts and articles:
```python
{
  'title': 'Article Title',
  'content': 'Article content...',
  'author': 'Author Name',
  'published_at': '2025-01-15T10:00:00Z'
}
```

### thread
Conversation threads:
```python
{
  'messages': [
    {'role': 'user', 'content': 'Hello'},
    {'role': 'assistant', 'content': 'Hi there!'}
  ],
  'status': 'active',
  'created_at': '2025-01-15T10:00:00Z'
}
```

### game-market
Betting markets:
```python
{
  'event_code': 'sr:match:12345',
  'market_name': '3way',
  'selections': [
    {'name': 'Home Win', 'odds': 2.10},
    {'name': 'Draw', 'odds': 3.40},
    {'name': 'Away Win', 'odds': 3.20}
  ]
}
```

## Vector Search Best Practices

### 1. Use Appropriate Thresholds

```yaml
config:
  threshold-docs: 5          # Minimum number of documents to return
  threshold-similarity: 0.7  # Minimum similarity score (0-1)
  search-limit: 1000         # Maximum documents to consider
```

### 2. Choose the Right Embedding Model

- **text-embedding-3-small**: Fast, good for most use cases
- **text-embedding-3-large**: More accurate, but slower

### 3. Optimize Search Queries

Combine vector search with filters:
```yaml
- type: document
  name: search-premier-league-content
  config:
    action: search
    search-vector: true
    search-limit: 100
  connector:
    name: "machina-ai"
    command: "invoke_embedding"
    model: "text-embedding-3-small"
  filters:
    name: "'content-snippet'"
  inputs:
    metadata.league: "'Premier League'"
    search-query: "$.get('user_question')"
```

## RAG (Retrieval-Augmented Generation)

Combine document search with LLMs:

```yaml
tasks:
  # 1. Search for relevant documents
  - type: document
    name: find-relevant-docs
    config:
      action: search
      search-vector: true
      threshold-docs: 5
    connector:
      name: "machina-ai"
      command: "invoke_embedding"
      model: "text-embedding-3-small"
    inputs:
      name: "'content-snippet'"
      search-query: "$.get('user_question')"
    outputs:
      context_docs: "$.get('documents', [])"
  
  # 2. Generate answer with context
  - type: prompt
    name: generate-answer
    connector:
      name: "machina-ai"
      command: "invoke_prompt"
      model: "gpt-4o"
    inputs:
      context: "$.get('context_docs')"
      question: "$.get('user_question')"
    outputs:
      answer: "$.get('choices')[0].get('message').get('content')"
```

## Document Metadata

Use metadata for efficient filtering:

```yaml
metadata:
  sport_id: "'4'"
  league: "'Premier League'"
  season: "'2024-25'"
  event_code: "'sr:match:12345'"
  created_at: "datetime.now().isoformat()"
  source: "'sportradar'"
```

## Conditional Document Operations

Only save if conditions are met:

```yaml
- type: document
  name: save-if-new
  condition: "$.get('event_exists') is False"
  config:
    action: save
    embed-vector: true
  documents:
    sport:Event: "$.get('event_data')"
```

## Document Transformations

Transform documents after retrieval:

```yaml
outputs:
  parsed_events: |
    [
      {
        'id': d.get('metadata', {}).get('event_code'),
        'title': d.get('value', {}).get('title'),
        'date': d.get('value', {}).get('start_date'),
        'teams': [
          d.get('value', {}).get('home_team'),
          d.get('value', {}).get('away_team')
        ]
      }
      for d in $.get('documents', [])
      if d.get('value', {}).get('status') == 'scheduled'
    ]
```

## Best Practices

1. **Use meaningful document names**: Makes filtering easier
2. **Add comprehensive metadata**: Enables efficient filtering
3. **Enable embeddings selectively**: Only when you need vector search
4. **Batch operations**: Use bulk-update for multiple documents
5. **Index frequently queried fields**: Add to metadata
6. **Clean up old data**: Implement data retention policies
7. **Test vector search thresholds**: Tune for your use case

