# Chat Completion in Machina

## Overview

Chat completion workflows allow you to create conversational AI experiences using various LLM providers (OpenAI, Groq, Google Gemini, etc.).

## Basic Chat Completion Workflow

```yaml
workflow:
  name: "chat-completions"
  title: "Chat Completions"
  description: "Workflow to execute a chat completion."
  context-variables:
    machina-ai:
      api_key: "$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY"
    machina-ai-fast:
      api_key: "$TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY"
    google-genai:
      api_key: "$TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY"
  inputs:
    messages: "$.get('messages', [])"
  outputs:
    message: "$.get('message')"
    workflow-status: "$.get('message') is not None and 'executed' or 'skipped'"
  tasks:
    # chat-completions-prompt
    - type: "prompt"
      name: "chat-completions-prompt"
      description: "Chat Completions."
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        messages: "$.get('messages')"
      outputs:
        message: "$.get('choices')[0].get('message').get('content')"
```

## Chat with RAG (Retrieval-Augmented Generation)

Add context from your document database:

```yaml
tasks:
  # Load similar documents using vector search
  - type: "document"
    name: "load-similar-documents"
    description: "Load similar documents"
    config:
      action: "search"
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
      search-query: "$.get('messages')"
    outputs:
      parsed_documents: |
        [
          {
            **d.get('value', {}),
          }
          for d in $.get('documents', [])
        ]

  # Send to LLM with context
  - type: "prompt"
    name: "chat-completions-prompt"
    connector:
      name: "google-genai"
      command: "invoke_prompt"
      model: "gemini-2.5-pro"
    inputs:
      documents: "$.get('parsed_documents', [])"
      messages: "$.get('messages')"
    outputs:
      message: "$.get('choices')[0].get('message').get('content')"
```

## Available LLM Providers

### OpenAI (machina-ai)
```yaml
connector:
  name: "machina-ai"
  command: "invoke_prompt"
  model: "gpt-4o"  # or "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"
```

### Groq (machina-ai-fast)
Fast inference for open-source models:
```yaml
connector:
  name: "machina-ai-fast"
  command: "invoke_prompt"
  model: "llama-3.3-70b-versatile"
  # Other options:
  # - "llama-3.1-8b-instant"
  # - "deepseek-r1-distill-llama-70b"
```

### Google Gemini (google-genai)
```yaml
connector:
  name: "google-genai"
  command: "invoke_prompt"
  model: "gemini-2.5-pro"  # or "gemini-2.5-flash"
```

### Google Vertex AI
```yaml
connector:
  name: "google-genai"
  command: "invoke_prompt"
  model: "gemini-2.5-flash"
  location: "global"
  provider: "vertex_ai"
context-variables:
  google-genai:
    credential: "$TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL"
    project_id: "$TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID"
```

## Structured Output with Schema

Use prompts with defined schemas for structured responses:

```yaml
prompts:
  - type: prompt
    name: "assistant-chat-reasoning-prompt"
    title: "Assistant Chat Reasoning"
    instruction: |
      Analyze the user's question and extract structured information.
    schema:
      title: AssistantChatReasoning
      type: object
      required: ["intent", "confidence", "extracted_data"]
      properties:
        intent:
          type: string
          enum: ["question", "command", "greeting"]
        confidence:
          type: number
          description: "Confidence score between 0 and 1"
        extracted_data:
          type: object
          description: "Extracted structured data"
```

## Streaming Responses

For real-time streaming, use the streaming agent endpoint:

```bash
POST /agent/stream/{agent_id}
{
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream_workflows": true
}
```

Response format (NDJSON):
```json
{"type":"start","content":"Starting...","metadata":{}}
{"type":"content","content":"Hello! How can","metadata":{}}
{"type":"content","content":" I help you today?","metadata":{}}
{"type":"done","content":"","metadata":{"state":{}}}
```

## Best Practices

1. **Use appropriate models**: 
   - Fast/cheap: Groq models, GPT-4o-mini
   - High quality: GPT-4o, Gemini 2.5 Pro
   - Balance: Gemini 2.5 Flash

2. **Implement RAG when needed**: Add context from your database for domain-specific answers

3. **Handle errors gracefully**: Use conditions to handle missing data

4. **Optimize prompt design**: Clear instructions lead to better results

5. **Use structured output**: Define schemas when you need predictable formats

