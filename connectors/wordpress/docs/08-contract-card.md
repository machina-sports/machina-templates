# 08. Contract card (dynamic generation)

## Generating blocks dynamically

The WordPress connector now supports dynamic generation of complex Gutenberg blocks from JSON data. The `render_contract_card` command creates a styled contract card using WordPress core blocks.

## render_contract_card command

### Function
- Generates a Gutenberg block for contract card
- Optionally uploads team logo
- Returns the HTML block and uploaded media information

### Input parameters
- `contract`: JSON with contract data
- `name`: Player name
- `team`: Team name
- `length`: Contract duration
- `salary`: Salary/cap hit
- `contract_type`: Contract type
- `total`: Total value
- `date`: Signing date
- `team_logo_url`: Team logo URL (optional)
- `team_logo_alt`: Logo alt text (optional)
- `upload_logo`: Whether to upload logo (default: true)

## Local usage example

### 1. Create contract JSON file

```powershell
$contract = @'
{
  "name": "Ryker Evans",
  "team": "Seattle",
  "length": "2 yrs",
  "salary": "$2.05 million",
  "contract_type": "re-signing",
  "total": "$4.1 million",
  "date": "August 11, 2025 - 6.23pm"
}
'@

Set-Content -Path ".\contract.json" -Value $contract
```

### 2. Execute with --contract-json

```powershell
python connectors/wordpress/test_local.py `
  --title "Contract: Ryker Evans" `
  --content "<p>Signing confirmed:</p>" `
  --contract-json ".\contract.json"
```

## Generated block structure

The command generates a block using WordPress core blocks:

- **Group**: Main container with borders and padding
- **Columns**: Two-column layout (38% + 62%)
- **Heading**: Player name
- **Paragraph**: Team and contract information
- **Nested columns**: For contract details

### Example HTML output

```html
<!-- wp:group {"style":{"border":{"radius":"12px","width":"1px"},"spacing":{"padding":{"top":"16px","bottom":"16px","left":"16px","right":"16px"}}}} -->
<div class="wp-block-group" style="border-width:1px;border-radius:12px;padding-top:16px;padding-bottom:16px;padding-left:16px;padding-right:16px">
<!-- wp:columns {"verticalAlignment":"top"} -->
<div class="wp-block-columns are-vertically-aligned-top">
<!-- wp:column {"width":"38%"} -->
<div class="wp-block-column" style="flex-basis:38%">
<!-- wp:heading {"level":3} -->
<h3>Ryker Evans</h3>
<!-- /wp:heading -->
<!-- wp:paragraph {"fontSize":"small"} -->
<p class="has-small-font-size"><strong>SIGNED BY</strong></p>
<!-- /wp:paragraph -->
<!-- wp:paragraph {"fontSize":"large"} -->
<p class="has-large-font-size"><strong>Seattle</strong></p>
<!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
<!-- wp:column {"width":"62%"} -->
<div class="wp-block-column" style="flex-basis:62%">
<!-- wp:columns {"columns":2} -->
<div class="wp-block-columns has-2-columns">
<!-- wp:column -->
<div class="wp-block-column">
<!-- wp:paragraph --><p><strong>Length:</strong><br/>2 yrs</p><!-- /wp:paragraph -->
<!-- wp:paragraph --><p><strong>Salary Cap Hit:</strong><br/>$2.05 million</p><!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
<!-- wp:column -->
<div class="wp-block-column">
<!-- wp:paragraph --><p><strong>Contract Type:</strong><br/>Re-signing</p><!-- /wp:paragraph -->
<!-- wp:paragraph --><p><strong>Total:</strong><br/>$4.1 million</p><!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
</div>
<!-- /wp:columns -->
<!-- wp:paragraph {"align":"center","fontSize":"small"} -->
<p class="has-text-align-center has-small-font-size">August 11, 2025 - 6.23pm</p>
<!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
</div>
<!-- /wp:columns -->
</div>
<!-- /wp:group -->
```

## workflow_render_contract.yml workflow

### Function
1. Calls `render_contract_card` to generate the block
2. Creates a draft post with the generated block

### Inputs
- `title`: Post title
- `content_html`: Base HTML content
- `contract`: Contract data (JSON)
- Individual contract fields
- `team_logo_url`: Logo URL (optional)
- `upload_logo`: Whether to upload (default: true)

### Outputs
- `post_id`: Created post ID
- `draft_url`: Draft URL
- `workflow-status`: Execution status

## Approach advantages

- **Compatibility**: Uses WordPress core blocks
- **Responsive**: Layout adaptable to different themes
- **Maintainable**: No hardcoded custom CSS
- **Flexible**: Dynamic data via JSON
- **Integrated**: Works as part of workflow

## Next steps

- [09. Troubleshooting](09-troubleshooting.md) - Problem resolution
- [← Back to index](../README.md) - Main index

---

[← Back to index](../README.md) | [← Previous](07-workflows.md)
