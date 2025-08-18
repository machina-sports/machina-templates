# 07. Available workflows

## Running workflows (Machina runtime)

If you are using the Machina workflow runner, you can execute the YAML workflows in this folder. Configure the indicated context variables and inputs as defined in each file.

## Available workflows

### `workflow_send_article_bearer.yml`
- **Function**: Reads an article, transforms, and creates a draft using an existing Bearer token
- **Usage**: For WordPress.com sites with valid OAuth token

### `workflow_send_article.yml`
- **Function**: Refreshes a WordPress.com access token using `client_id`, `client_secret`, and `refresh_token`, then creates a draft
- **Usage**: For WordPress.com sites with refresh token

### `workflow_push_article.yml`
- **Function**: Accepts raw fields (or an article object to transform), refreshes the token, and creates a draft with images, categories, and tags
- **Usage**: For creating posts with complete metadata

### `workflow_push_widgets.yml`
- **Function**: Creates posts with shortcodes or raw Gutenberg blocks using bearer authentication
- **Usage**: For inserting widgets and advanced blocks

### `workflow_render_contract.yml`
- **Function**: Renders a contract card from JSON data and creates a draft
- **Usage**: For dynamic generation of complex components

### `workflow_test.yml`
- **Function**: Simple test to create a draft with an optional image
- **Usage**: For smoke tests and validation

## Example: workflow_push_widgets.yml

### Inputs for HTML iframe block:

```powershell
$htmlBlock = @'
<!-- wp:html -->
<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;">
  <iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" frameborder="0" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe>
</div>
<!-- /wp:html -->
'@

$inputs = @{ title = "Widgets via workflow"; content_html = "<p>Body</p>"; block = $htmlBlock } | ConvertTo-Json -Compress
```

### Execution (adjust to your runner CLI):

```bash
# Example (adjust to your runner CLI):
# machina run connectors/wordpress/workflow_push_widgets.yml --inputs $inputs
```

## Context variables

Each workflow defines its own context variables. The main ones include:

- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_SITE_URL`
- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_BEARER_TOKEN`
- `MACHINA_CONTEXT_VARIABLE_WPCOM_CLIENT_ID`
- `MACHINA_CONTEXT_VARIABLE_WPCOM_CLIENT_SECRET`
- `MACHINA_CONTEXT_VARIABLE_WPCOM_REFRESH_TOKEN`
- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_USERNAME`
- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_APP_PASSWORD`

## Consulting workflows

Consult each workflow file for the expected `context-variables`, `inputs`, and `outputs`. Use your runner's CLI to pass inputs and context variables appropriately.

## Next steps

- [08. Contract card (dynamic generation)](08-contract-card.md) - Generating blocks dynamically
- [09. Troubleshooting](09-troubleshooting.md) - Problem resolution

---

[← Back to index](../README.md) | [← Previous](06-advanced-blocks.md)
