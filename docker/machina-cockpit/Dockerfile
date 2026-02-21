FROM us-central1-docker.pkg.dev/cloud-workstations-images/predefined/code-oss:latest

# ============================================================
# machinasports/machina-cockpit
# Dev-UX image for Google Cloud Workstations
# ============================================================

USER root

# --- System tools -----------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        jq vim htop tmux unzip software-properties-common \
        apt-transport-https ca-certificates gnupg lsb-release \
    && rm -rf /var/lib/apt/lists/*

# --- GitHub CLI --------------------------------------------------------------
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# --- Python 3.11 -------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# --- Node.js 20 LTS ----------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Claude Code --------------------------------------------------------------
RUN npm install -g @anthropic-ai/claude-code

# --- gcloud CLI ---------------------------------------------------------------
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

# --- Docker CLI (DinD via workstation config) ---------------------------------
RUN curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# --- Entrypoint ---------------------------------------------------------------
COPY entrypoint.sh /machina-cockpit-entrypoint.sh
RUN chmod +x /machina-cockpit-entrypoint.sh

# --- Environment defaults (overridable via workstation config) ----------------
ENV ANTHROPIC_API_KEY=""
ENV CLAUDE_CODE_USE_BEDROCK=0

USER user

ENTRYPOINT ["/machina-cockpit-entrypoint.sh"]
