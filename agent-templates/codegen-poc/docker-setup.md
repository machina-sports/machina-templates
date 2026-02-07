# Docker Setup for Codegen PoC

This document describes the changes needed to run the Codegen connector in Docker.

## Option A: Minimal Setup (Test Only)

For quick testing, install Claude Code CLI directly in the running container:

```bash
# Enter the container as root
docker exec -it -u root development-app-1 bash

# Install Node.js
apt-get update && apt-get install -y curl
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Install Claude Code CLI
npm install -g @anthropic-ai/claude-code

# Verify installation
claude --version

# Exit
exit
```

Repeat for celery workers:
```bash
docker exec -it -u root development-celery-normal-1 bash
# ... same commands ...

docker exec -it -u root development-celery-streaming-1 bash
# ... same commands ...
```

**Note**: These changes are lost when containers restart.

---

## Option B: Persistent Setup (Recommended)

### 1. Modify Dockerfile

Edit `machina-client-api/docker/development/dockerfile`:

```dockerfile
# Base image
FROM python:3.11-slim

# Create a non-root user and group
RUN groupadd -r machina && useradd -r -g machina machina

# Set the working directory
WORKDIR /usr/src/app

# Copy requirements first to leverage Docker caching
COPY docker/development/requirements.txt /usr/src/app/

# Install build dependencies, Node.js, and pip packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    rustc \
    cargo \
    libfreetype-dev \
    libpng-dev \
    pkg-config \
    curl \
    && pip install --no-cache-dir --upgrade pip setuptools wheel cython \
    && pip install --no-cache-dir pyyaml \
    && pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt \
    # Install Node.js 20.x
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    # Install Claude Code CLI
    && npm install -g @anthropic-ai/claude-code \
    # Cleanup build dependencies
    && apt-get purge -y --auto-remove build-essential cmake rustc cargo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY pyproject.toml /usr/src/app/
COPY core/ /usr/src/app/core/
COPY static/ /usr/src/app/static/
COPY utils/ /usr/src/app/utils/
COPY server/ /usr/src/app/server/
COPY app.py /usr/src/app/
COPY gunicorn_config.py /usr/src/app/

# Change ownership of the app directory to the machina user
RUN chown -R machina:machina /usr/src/app/

# Switch to the non-root user
USER machina

# Expose the application port
EXPOSE 5003
```

### 2. Add Environment Variables

Edit `machina-client-api/docker/development/.env_app`:

```bash
# Add Anthropic API key for Claude Code
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here

# Optional: Configure Claude Code model
CLAUDE_CODE_MODEL=claude-sonnet-4-20250514
```

### 3. Mount Target Codebase

Edit `machina-client-api/docker/development/compose.yml`:

```yaml
services:
  app:
    # ... existing config ...
    volumes:
      - /Users/fernando/machina/dazn-templates:/app/dazn-templates
      - /Users/fernando/machina/entain-templates:/app/entain-templates
      - /Users/fernando/machina/machina-templates:/app/machina-templates
      - /Users/fernando/machina/otg-templates:/app/otg-templates
      # Add your target codebase
      - /path/to/your/codebase:/app/target-codebase

  celery-normal:
    # ... existing config ...
    volumes:
      - /Users/fernando/machina/dazn-templates:/app/dazn-templates
      - /Users/fernando/machina/entain-templates:/app/entain-templates
      - /Users/fernando/machina/machina-templates:/app/machina-templates
      - /Users/fernando/machina/otg-templates:/app/otg-templates
      # Add your target codebase
      - /path/to/your/codebase:/app/target-codebase

  celery-streaming:
    # ... existing config ...
    volumes:
      # Add template mounts (currently missing)
      - /Users/fernando/machina/dazn-templates:/app/dazn-templates
      - /Users/fernando/machina/entain-templates:/app/entain-templates
      - /Users/fernando/machina/machina-templates:/app/machina-templates
      - /Users/fernando/machina/otg-templates:/app/otg-templates
      # Add your target codebase
      - /path/to/your/codebase:/app/target-codebase
```

### 4. Rebuild and Restart

```bash
cd /Users/fernando/machina/machina-client-api/docker/development

# Rebuild images
docker-compose build app celery-normal celery-streaming

# Restart services
docker-compose down
docker-compose up -d

# Verify Claude Code installation
docker exec development-app-1 claude --version
```

---

## Option C: Alternative - SDK via Python (No CLI)

If you prefer not to install Node.js in the container, use the Python SDK directly.

### 1. Add to requirements.txt

Edit `machina-client-api/docker/development/requirements.txt`:

```
# Add at the end
claude-agent-sdk>=0.2.0
```

### 2. Modify Connector to Use Python SDK

Replace subprocess calls with Python SDK calls. See `codegen_sdk.py` alternative implementation.

---

## Verification

After setup, test the connector:

```bash
# Test CLI availability
docker exec development-app-1 claude --version

# Test API key
docker exec development-app-1 env | grep ANTHROPIC

# Test health check via MCP
```

Then install and test via MCP:

```python
# Install connector
mcp__docker_localhost__import_template_from_local(
    template="connectors/codegen",
    project_path="/app/machina-templates/connectors/codegen"
)

# Test health check
mcp__docker_localhost__connector_executor(
    connector_name="codegen",
    connector_exec="health_check",
    params={}
)
```
