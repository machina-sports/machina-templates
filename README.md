# Machina Templates
Repository of templates and connectors for Machina Sports - a platform for creating AI-powered sports content workflows.

## Repository Structure

This repository is organized into two main directories:

### 1. Connectors
The `connectors` directory contains all the connectors used by the templates. Each connector follows a standardized naming convention:

- Directory name: `connectors/{connector-name}`
- Main files: `{connector-name}.{extension}`

### 2. Agent Templates
The `agent-templates` directory contains all the agent templates, organized by categories:

- Reporter templates (e.g., `reporter-briefing-en`, `reporter-image`, `reporter-polls-en`)
- Sport-specific templates (e.g., `sportingbet-nba`, `sportradar-soccer`)
- Brand-specific templates (e.g., `template-estelarbet`, `template-quizzes-dazn`)
- General templates (e.g., `chat-completion`)

## Naming Conventions

The repository follows these naming conventions:

### Connectors
Connectors use simple, descriptive names without prefixes:
- `openai` (previously `sdk-openai`)
- `groq` (previously `sdk-groq`)
- `perplexity` (previously `api-perplexity`)
- `sportradar-soccer` (previously `api-sportradar-soccer`)

### Environment Variables
Environment variables use the `$MACHINA_CONTEXT_VARIABLE_` prefix followed by the service name:
- `$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_GROQ_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_PERPLEXITY_API_KEY`
- `$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY`

## Installation Instructions

To install a template:

1. Choose a template from the `agent-templates` directory
2. Make sure the required connectors are installed from the `connectors` directory
3. Configure the necessary environment variables in your Machina environment
4. Import the template workflows into your Machina instance

## Available Templates

The repository includes a wide range of templates for various sports content workflows:

### Reporter Templates
- `reporter-summary`: Generate game summaries
- `reporter-briefing-en/es`: Create pre-game briefings in English/Spanish
- `reporter-polls-en/es`: Generate interactive polls in English/Spanish
- `reporter-quizzes-en/es`: Create sports quizzes in English/Spanish
- `reporter-image`: Generate sports-related images
- `reporter-websearch`: Research web content for sports events
- `reporter-recap-pt-br`: Create post-game recaps in Portuguese

### Sport-Specific Templates
- `sportingbet-nba`: NBA-specific content workflows
- `sportradar-soccer`: Soccer data processing workflows
- `template-superbowl-lix`: NFL Super Bowl specific templates
- `kingpool-fantasy`: Fantasy sports content

### Brand-Specific Templates
- `template-estelarbet`: Templates for Estelarbet brand
- `template-quizzes-dazn`: Quiz templates for DAZN
- `sportingbet-blog`: Blog content for Sportingbet

### General Templates
- `chat-completion`: Generic chat completion workflows
- `template-quizzes`: Generic sports quiz templates

## Available Connectors

The repository includes connectors for various services:

### AI Services
- `openai`: OpenAI API integration
- `groq`: Groq API integration
- `perplexity`: Perplexity API for web search
- `google-vertex`: Google Vertex AI integration
- `stability`: Stability AI for image generation

### Sports Data
- `sportradar-soccer`: Soccer data API
- `sportradar-nba`: NBA data API
- `sportradar-nfl`: NFL data API
- `sportradar-rugby`: Rugby data API
- `sportingbet`: Sports betting data

### Utilities
- `storage`: Data storage connector
- `machina-db`: Database connector
- `exa-search`: Search functionality
- `docling`: Document processing

## Usage Examples

### Basic Workflow Structure
```yaml
workflow:
  name: "workflow-name"
  title: "Workflow Title"
  description: "Workflow description"
  context-variables:
    openai:
      api_key: "$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY"
    sportradar-soccer:
      sportradar_api_key: "$MACHINA_CONTEXT_VARIABLE_SPORTRADAR_SOCCER_V4_API_KEY"
  inputs:
    event_code: "$.get('event_code') or None"
  outputs:
    workflow-status: "$.get('event-exists') is not True and 'skipped' or 'executed'"
  tasks:
    # Task definitions
```

## Contributing

To contribute to this repository:

1. Follow the established naming conventions
2. Ensure all environment variables use the `$MACHINA_CONTEXT_VARIABLE_` prefix
3. Document your templates and connectors thoroughly
4. Test your workflows before submitting