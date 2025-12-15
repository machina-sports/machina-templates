# Machina Assistant

AI-powered assistant for the Machina platform. This template provides conversational AI that helps users understand and implement Machina workflows, connectors, agents, deployment strategies, and more.

## Overview

The Machina Assistant is a comprehensive help system that:
- Answers questions about Machina architecture and components
- Provides deployment and configuration guidance
- Explains how to create chat completions, podcasts, and quizzes
- Offers code examples and step-by-step tutorials
- Maintains conversation context across multiple interactions
- Uses RAG (Retrieval-Augmented Generation) with a curated knowledge base

## Features

✅ **Conversational AI**: Natural language interface for platform guidance  
✅ **Knowledge Base**: Comprehensive documentation with vector search  
✅ **Code Examples**: YAML and Python examples for common tasks  
✅ **Context Awareness**: Maintains conversation history  
✅ **Structured Responses**: Clear, organized answers with suggestions  
✅ **Multi-Topic Support**: Architecture, deployment, APIs, and more  

## Architecture

### Components

1. **Agent** (`assistant-executor.yml`)
   - Orchestrates the conversation flow
   - Manages three-step workflow execution

2. **Workflows**
   - `assistant-reasoning.yml`: Analyzes user intent and searches knowledge base
   - `assistant-response.yml`: Generates helpful responses with examples
   - `assistant-update.yml`: Updates conversation thread

3. **Prompts**
   - `assistant-reasoning.yml`: Intent classification and query extraction
   - `assistant-response.yml`: Response generation with structured output

4. **Knowledge Base**
   - Pre-populated documentation on all Machina topics
   - Vector embeddings for semantic search
   - Automatically loaded via `_populate-knowledge.yml`

5. **Utilities**
   - `message-formatter`: Prepares conversation history for prompts

## Topics Covered

The assistant can help with:

- **Architecture**: Connectors, workflows, agents, system design
- **Deployment**: Production setup, Docker, scaling, configuration
- **Chat Completion**: LLM integration, RAG, streaming
- **Podcasts**: TTS, audio content generation
- **Quizzes**: Trivia generation, structured schemas
- **Database**: Document storage, vector search, embeddings
- **APIs**: SportRadar, API Football, OxyLabs, storage
- **Development**: Creating custom connectors and workflows

## Installation

1. Navigate to the Machina Studio
2. Go to Templates
3. Find "Machina Assistant" in the special-templates category
4. Click "Install"
5. Wait for the knowledge base to be populated (automatic)

## Usage

### Basic Conversation

```json
POST /agent/stream/machina-assistant-executor
{
  "messages": [
    {
      "role": "user",
      "content": "How do I create a custom connector?"
    }
  ],
  "stream_workflows": true
}
```

### Continuing a Conversation

```json
POST /agent/stream/machina-assistant-executor
{
  "context-agent": {
    "thread_id": "previous-thread-id"
  },
  "messages": [
    {
      "role": "user",
      "content": "Can you show me an example?"
    }
  ],
  "stream_workflows": true
}
```

## Example Questions

Here are some example questions you can ask:

**Architecture & Basics**
- "What is Machina?"
- "Explain the three-tier architecture"
- "How do connectors work?"
- "What's the difference between agents and workflows?"

**Deployment**
- "How do I deploy to production?"
- "What environment variables do I need?"
- "How to scale the system horizontally?"
- "Help me set up Docker"

**Chat & LLMs**
- "How to create a chat bot?"
- "What LLM providers are available?"
- "How do I implement RAG?"
- "Show me a streaming chat example"

**Content Generation**
- "How to generate podcasts?"
- "Create a quiz workflow"
- "How to use text-to-speech?"

**Database & Search**
- "How to save documents?"
- "What is vector search?"
- "How do embeddings work?"
- "Show me database query examples"

**APIs & Integrations**
- "How to use SportRadar API?"
- "What APIs are available?"
- "How to upload files to storage?"
- "Integrate OxyLabs for web scraping"

## Configuration

### Required Environment Variables

```bash
# OpenAI for embeddings and chat
TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY=your-openai-key

# Google Vertex AI for reasoning and responses
TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL=your-vertex-credential
TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID=your-project-id

# Optional: Groq for faster inference
TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY=your-groq-key
```

### Models Used

- **Reasoning**: Gemini 2.5 Flash (fast intent classification)
- **Response**: Gemini 2.5 Pro (high-quality answers)
- **Embeddings**: OpenAI text-embedding-3-small

You can modify these in the workflow files if needed.

## Knowledge Base

The knowledge base is automatically populated with documentation covering:

1. Machina Architecture Overview
2. Deployment Guide
3. Chat Completion Guide
4. Podcast Generation
5. Quiz Creation
6. Document Database & Vector Search
7. API Integrations
8. Connector Development
9. Workflow Development

All documents are embedded for semantic search, allowing the assistant to find relevant information based on user questions.

## Customization

### Adding New Knowledge

Edit `_populate-knowledge.yml` to add more documentation:

```yaml
- type: document
  name: save-your-docs
  config:
    action: save
    embed-vector: true
  connector:
    name: "machina-ai"
    command: "invoke_embedding"
    model: "text-embedding-3-small"
  documents:
    machina-knowledge: |
      {
        'title': 'Your Topic',
        'category': 'your-category',
        'content': '''Your documentation here...''',
        'tags': ['tag1', 'tag2']
      }
```

### Modifying Response Style

Edit `prompts/assistant-response.yml` to change:
- Response structure
- Tone and style
- Code example format
- Suggestion types

### Changing Models

Update the connector configurations in the workflow files:

```yaml
connector:
  name: "machina-ai"  # or google-genai, machina-ai-fast
  command: "invoke_prompt"
  model: "gpt-4o"  # or gemini-2.5-pro, llama-3.3-70b-versatile
```

## Response Format

The assistant provides structured responses with:

1. **Main Response**: Comprehensive answer with examples
2. **Suggestions**: Follow-up questions you might want to ask
3. **Related Topics**: Connected concepts to explore

Example response structure:
```markdown
## Main Topic

Brief overview and explanation

### Code Example

```yaml
# Working example here
```

### Best Practices
- Practice 1
- Practice 2

### Next Steps
- Step 1
- Step 2
```

## Limitations

- Knowledge base is static and needs manual updates
- Responses are based on documented information only
- Complex multi-step implementations may need human review
- Code examples should be tested before production use

## Troubleshooting

### Assistant not responding
- Check environment variables are set correctly
- Verify Vertex AI credentials are valid
- Check MongoDB connection for thread storage

### Poor quality responses
- Ensure knowledge base is populated (run `_populate-knowledge.yml`)
- Check vector search is returning relevant documents
- Consider using higher quality models (GPT-4o, Gemini 2.5 Pro)

### Conversation not maintaining context
- Verify thread_id is being passed correctly
- Check thread documents are being saved
- Review message history preparation in workflows

## Contributing

To improve the assistant:

1. Add more documentation to the knowledge base
2. Refine prompt instructions for better responses
3. Add new topic categories and classifications
4. Improve code examples and tutorials
5. Enhance error handling and edge cases

## Version History

- **v1.0.0** (2025-12): Initial release
  - Core conversation flow
  - Knowledge base with 9 topics
  - Structured response generation
  - Context-aware conversations

## Support

For issues or questions:
1. Ask the assistant itself!
2. Check the Machina documentation
3. Review workflow logs for debugging
4. Contact the Machina team

---

Built with ❤️ for the Machina community

