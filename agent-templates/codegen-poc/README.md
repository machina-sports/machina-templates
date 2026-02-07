# Codegen PoC - Claude Agent SDK Integration

This template provides a Proof of Concept for integrating Claude Agent SDK (formerly Claude Code SDK) with Machina workflows.

## Overview

The Codegen connector allows Machina workflows to:
- Execute autonomous coding tasks via Claude
- Maintain session context across multiple turns
- Stream responses in real-time
- Access and modify codebases

## Prerequisites

### 1. Install Claude Code CLI

```bash
# Install globally
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version
```

### 2. Configure API Key

```bash
# Set in environment
export ANTHROPIC_API_KEY="your-api-key"

# Or add to Docker compose .env_app
ANTHROPIC_API_KEY=your-api-key
```

### 3. Mount Codebase in Docker

Add to `docker/development/compose.yml`:

```yaml
services:
  app:
    volumes:
      # ... existing mounts
      - /path/to/your/codebase:/app/target-codebase

  celery-normal:
    volumes:
      # ... existing mounts
      - /path/to/your/codebase:/app/target-codebase

  celery-streaming:
    volumes:
      # ... existing mounts
      - /path/to/your/codebase:/app/target-codebase
```

### 4. Install Claude Code in Docker Container

Add to `docker/development/dockerfile`:

```dockerfile
# Install Node.js for Claude Code CLI
RUN apt-get update && apt-get install -y curl
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
RUN apt-get install -y nodejs

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code
```

## Installation

### Install the connector

```python
mcp__docker_localhost__import_template_from_local(
    template="connectors/codegen",
    project_path="/app/machina-templates/connectors/codegen"
)
```

### Install the agent template

```python
mcp__docker_localhost__import_template_from_local(
    template="agent-templates/codegen-poc",
    project_path="/app/machina-templates/agent-templates/codegen-poc"
)
```

## Usage

### Direct Workflow Execution

```python
# Execute a coding task
mcp__docker_localhost__execute_workflow(
    name="codegen-execute",
    context={
        "context-workflow": {
            "prompt": "Find all TODO comments in the codebase and create a summary",
            "working_directory": "/app/target-codebase",
            "allowed_tools": ["Read", "Glob", "Grep"],
            "max_turns": 10
        }
    }
)
```

### Resume Session

```python
# Continue a previous session
mcp__docker_localhost__execute_workflow(
    name="codegen-resume",
    context={
        "context-workflow": {
            "session_id": "abc123-session-id-from-previous",
            "prompt": "Now fix the highest priority TODO",
            "working_directory": "/app/target-codebase"
        }
    }
)
```

### Via Agent

```python
mcp__docker_localhost__execute_agent(
    agent_id="codegen-assistant-id",
    messages=[{
        "role": "user",
        "content": "Analyze the authentication module and suggest improvements"
    }],
    context={}
)
```

## Connector Commands

| Command | Description |
|---------|-------------|
| `health_check` | Verify Claude CLI is installed and configured |
| `execute_prompt` | Execute a single coding prompt |
| `execute_with_session` | Execute and return session_id for continuation |
| `resume_session` | Continue an existing session |

## Workflow Parameters

### codegen-execute

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | required | The coding task to execute |
| `working_directory` | string | `/app` | Directory with codebase |
| `allowed_tools` | array | `["Read", "Glob", "Grep"]` | Tools to allow |
| `max_turns` | int | 10 | Maximum agent turns |
| `timeout` | int | 300 | Execution timeout (seconds) |
| `save_to_document` | bool | false | Save result to document |

### codegen-resume

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | string | required | Session ID from previous execution |
| `prompt` | string | required | Follow-up prompt |
| `working_directory` | string | `/app` | Directory with codebase |

## Streaming (Future Enhancement)

The `execute_streaming` function in the connector supports real-time streaming via Redis Pub/Sub. This requires integration with the Celery streaming queue.

Events published:
- `start`: Execution beginning
- `content`: Each message/chunk from Claude
- `tool_use`: Tool being used (Read, Edit, etc.)
- `done`: Execution complete
- `error`: If execution fails

## Limitations

1. **Synchronous execution**: Current implementation waits for full completion
2. **No permission prompts**: Runs with `bypassPermissions` mode
3. **Session expiration**: Claude sessions expire after ~4.5 minutes of inactivity
4. **Container requirements**: Requires Node.js and Claude CLI in container

## Troubleshooting

### Claude CLI not found

```bash
# Check installation
docker exec -it development-app-1 claude --version

# Reinstall if needed
docker exec -it development-app-1 npm install -g @anthropic-ai/claude-code
```

### API Key not configured

```bash
# Check environment
docker exec -it development-app-1 env | grep ANTHROPIC

# Add to .env_app
echo "ANTHROPIC_API_KEY=your-key" >> docker/development/.env_app
docker-compose restart app celery-normal
```

### Session expired

Sessions expire after ~4.5 minutes of inactivity. Start a new session with `execute_with_session`.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Machina Workflow                          │
├─────────────────────────────────────────────────────────────┤
│  Workflow: codegen-execute                                   │
│  ├── Task: execute-codegen (connector: codegen)             │
│  └── Task: save-result (document)                           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 Codegen Connector (PyScript)                 │
│  execute_prompt() → subprocess → claude CLI                  │
│  resume_session() → subprocess → claude CLI --resume         │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Claude Code CLI                                 │
│  - Access to mounted codebase                                │
│  - Tools: Read, Edit, Bash, Glob, Grep, etc.                │
│  - Session management via --resume flag                      │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Claude Agent SDK (Runtime)                      │
│  - Autonomous agent loop                                     │
│  - Context management                                        │
│  - Tool execution                                            │
└─────────────────────────────────────────────────────────────┘
```

## Next Steps

1. **Streaming integration**: Connect to Celery streaming queue for real-time updates
2. **Permission hooks**: Add approval callbacks for sensitive operations
3. **MCP integration**: Allow Claude to use Machina's MCP servers
4. **Multi-codebase**: Support dynamic codebase selection
