# 06. Advanced blocks (HTML/embeds)

## Inserting advanced Gutenberg blocks

You can inject a complete Gutenberg block snippet via `--block` or load it from a file via `--block-file`. Use PowerShell here-strings for multi-line content or save the block to an `.html` file.

## Latest Posts block (core/latest-posts)

### Via PowerShell variable:

```powershell
$block = @'
<!-- wp:latest-posts {"displayPostContent":true,"excerptLength":20,"postsToShow":3} /-->
'@

python connectors/wordpress/test_local.py `
  --title "Advanced: Latest Posts" `
  --content "<p>Below are latest posts:</p>" `
  --block $block
```

### Via file:

```powershell
Set-Content -Path ".\wp-block.html" -Value @'
<!-- wp:latest-posts {"displayPostContent":true,"excerptLength":20,"postsToShow":3} /-->
'@

python connectors/wordpress/test_local.py `
  --title "Advanced: Latest Posts (file)" `
  --content "<p>Below are latest posts:</p>" `
  --block-file ".\wp-block.html"
```

## YouTube embed (auto-embed)

### Via PowerShell variable:

```powershell
$block = @'
<!-- wp:embed {"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","type":"video"} -->
<figure class="wp-block-embed is-type-video"><div class="wp-block-embed__wrapper">
https://www.youtube.com/watch?v=dQw4w9WgXcQ
</div></figure>
<!-- /wp:embed -->
'@

python connectors/wordpress/test_local.py `
  --title "Advanced: YouTube" `
  --content "<p>Video below:</p>" `
  --block $block
```

### Via file:

```powershell
Set-Content -Path ".\wp-embed.html" -Value @'
<!-- wp:embed {"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ","type":"video"} -->
<figure class="wp-block-embed is-type-video"><div class="wp-block-embed__wrapper">
https://www.youtube.com/watch?v=dQw4w9WgXcQ
</div></figure>
<!-- /wp:embed -->
'@

python connectors/wordpress/test_local.py `
  --title "Advanced: YouTube (file)" `
  --content "<p>Video below:</p>" `
  --block-file ".\wp-embed.html"
```

## Custom HTML block (iframe)

For iframes and custom HTML:

```powershell
$htmlBlock = @'
<!-- wp:html -->
<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;">
  <iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ" frameborder="0" allowfullscreen style="position:absolute;top:0;left:0;width:100%;height:100%;"></iframe>
</div>
<!-- /wp:html -->
'@

python connectors/wordpress/test_local.py `
  --title "HTML iframe block" `
  --content "<p>Video below:</p>" `
  --block $htmlBlock
```

## Column and layout blocks

For more complex layouts:

```powershell
$columnsBlock = @'
<!-- wp:columns {"verticalAlignment":"top"} -->
<div class="wp-block-columns are-vertically-aligned-top">
<!-- wp:column {"width":"50%"} -->
<div class="wp-block-column" style="flex-basis:50%">
<!-- wp:heading -->
<h2>Left Column</h2>
<!-- /wp:heading -->
<!-- wp:paragraph -->
<p>Left column content.</p>
<!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
<!-- wp:column {"width":"50%"} -->
<div class="wp-block-column" style="flex-basis:50%">
<!-- wp:heading -->
<h2>Right Column</h2>
<!-- /wp:heading -->
<!-- wp:paragraph -->
<p>Right column content.</p>
<!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
</div>
<!-- /wp:columns -->
'@

python connectors/wordpress/test_local.py `
  --title "Columns Layout" `
  --content "<p>Column layout:</p>" `
  --block $columnsBlock
```

## Important notes

- Block HTML must be valid for your site's block editor
- If it renders as raw HTML, check that the block type exists and is not disabled
- For third-party blocks, ensure the plugin is installed and active
- Use WordPress core blocks when possible for better compatibility

## Next steps

- [07. Available workflows](07-workflows.md) - Running workflows
- [08. Contract card (dynamic generation)](08-contract-card.md) - Generating blocks dynamically

---

[← Back to index](../README.md) | [← Previous](05-widgets-shortcodes.md)
