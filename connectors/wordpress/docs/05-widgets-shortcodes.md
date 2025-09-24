# 05. Widgets via shortcode

## Inserting widgets via shortcode block

Classic widgets and many plugins expose a shortcode. You can embed any shortcode inside a Gutenberg Shortcode block. The test script supports appending a shortcode automatically via `--shortcode`.

## Basic example

```powershell
python connectors/wordpress/test_local.py `
  --title "Post with widget" `
  --content "<p>Below is the widget:</p>" `
  --shortcode "[my_custom_widget]"
```

This will append the following to the post content:

```html
<!-- wp:shortcode -->
[my_custom_widget]
<!-- /wp:shortcode -->
```

## Complex widgets via shortcode

For widgets with parameters:

```powershell
python connectors/wordpress/test_local.py `
  --title "Advanced: Widget via shortcode" `
  --content "<p>Widget below:</p>" `
  --shortcode "[your_widget id=\"42\" style=\"compact\"]"
```

## External widgets (example: Tallysight)

For external widgets like Tallysight:

```powershell
python connectors/wordpress/test_local.py `
  --title "Tallysight Widget" `
  --content "<p>Odds widget below:</p>" `
  --shortcode "[tallysight-widget type='tile' id='68470e30d434471a062df79c' config-format='decimal' config-odds-by='sportingbet' config-type='games' config-workspace='sporting-bet' config-locale='pt' config-hide-brand-logo='true']"
```

## Requirements on your WordPress site

- The shortcode must be registered (e.g., by your theme/plugin)
- For a classic widget, you can expose it via a shortcode handler calling `the_widget()`
- Ensure your security/hardening plugins permit shortcode rendering for the post type and user role

## Testing tips

- Publish the draft and view the front-end to verify the widget renders
- If it renders as plain text, confirm the shortcode exists and isn't disabled by your site's configuration
- Test with different types of widgets to ensure compatibility

## Next steps

- [06. Advanced blocks (HTML/embeds)](06-advanced-blocks.md) - Inserting advanced Gutenberg blocks
- [07. Available workflows](07-workflows.md) - Running workflows

---

[← Back to index](../README.md) | [← Previous](04-local-tests.md)
