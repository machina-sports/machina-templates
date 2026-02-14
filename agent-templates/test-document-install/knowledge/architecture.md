# Machina Architecture

## Technical Architecture

The Machina platform is built on a microservices architecture with the following components:

- **Core API**: Handles agent management, workflow orchestration, and document storage
- **MCP Server**: Model Context Protocol server for AI tool integration
- **Workers**: Celery-based async processing for agent execution

## Data Flow

1. User triggers workflow via API or MCP
2. Workflow orchestrator dispatches tasks to agents
3. Agents execute using configured prompts and connectors
4. Results stored as documents in MongoDB
