# 01. Prerequisites and virtual environment

## What this connector can do

- Create WordPress draft posts (self-hosted or WordPress.com)
- Upload media and optionally set the first image as featured
- Auto-append uploaded images to the post content when not already referenced
- Use either Application Passwords (self-hosted) or OAuth Bearer tokens (WordPress.com)

## Files in this directory

- `wordpress.py`: core functions `upload_media` and `create_draft_post`
- `test_local.py`: quick local test (self-hosted or bearer)
- `send_article_bearer.py`: reads `articles.model.json`, transforms, and creates a draft using a Bearer token
- Workflows: `workflow_send_article.yml`, `workflow_send_article_bearer.yml`, `workflow_push_article.yml`, `workflow_test.yml`
- Widgets/blocks workflow: `workflow_push_widgets.yml`
- Contract card workflow: `workflow_render_contract.yml`

## Prerequisites

### Python
- Python 3.10+

### Virtual environment
Activate the virtual environment (Windows PowerShell example):

```bash
.venv\Scripts\Activate.ps1
```

### Dependencies
Install dependencies (this connector uses `requests`):

```bash
pip install -U requests
```

## Next steps

- [02. WordPress.com OAuth](02-oauth-wpcom.md) - OAuth setup for WordPress.com
- [03. Self-hosted (Application Password)](03-selfhosted-app-password.md) - Setup for self-hosted WordPress
- [04. Local tests (scripts)](04-local-tests.md) - How to test locally

---

[← Back to index](../README.md)
