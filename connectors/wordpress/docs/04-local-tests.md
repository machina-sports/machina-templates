# 04. Local tests (scripts)

## Quick local test (self-hosted or bearer)

Use `test_local.py`. If a `--bearer-token` (or `WORDPRESS_BEARER_TOKEN`) is present, it uses WordPress.com mode; otherwise it uses self-hosted username + application password.

## Test using environment variables (self-hosted)

```bash
python connectors/wordpress/test_local.py \
  --title "Hello from Machina" \
  --content "<p>Sample body</p>" \
  --image-url "https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png"
```

## Passing credentials via flags (self-hosted)

```bash
python connectors/wordpress/test_local.py \
  --title "Hello from Machina" \
  --content "<p>Sample body</p>" \
  --site-url "https://example.com" \
  --username "your_user" \
  --app-password "abcd efgh ijkl mnop" \
  --image-path "C:/path/to/local/image.jpg"
```

## WordPress.com using Bearer token

```bash
python connectors/wordpress/test_local.py \
  --title "Hello from Machina (WP.com)" \
  --content "<p>Sample body</p>" \
  --site-url "example.wordpress.com" \
  --bearer-token "YOUR_ACCESS_TOKEN" \
  --image-url "https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png"
```

## End-to-end test from `articles.model.json` (Bearer)

`send_article_bearer.py` reads from `articles.model.json`, converts the article into WordPress fields, optionally attaches an image, and creates a draft using a Bearer token.

### Using environment variables:

```bash
$env:WORDPRESS_SITE_URL = "example.wordpress.com"
$env:WORDPRESS_BEARER_TOKEN = "YOUR_ACCESS_TOKEN"
python connectors/wordpress/send_article_bearer.py \
  --file-path articles.model.json \
  --json-pointer "0.value" \
  --image-url "https://upload.wikimedia.org/wikipedia/commons/4/47/PNG_transparency_demonstration_1.png"
```

### Passing via flags:

```bash
python connectors/wordpress/send_article_bearer.py \
  --file-path articles.model.json \
  --json-pointer "0.value" \
  --site-url "example.wordpress.com" \
  --bearer-token "YOUR_ACCESS_TOKEN"
```

## Expected output

The output includes the draft `Post ID` and `Post Link`. If an image is uploaded, its IDs will also be printed.

## Example output

```
Post created successfully!
Post ID: 12345
Post Link: https://example.com/?p=12345
Uploaded media IDs: [67890]
```

## Next steps

- [05. Widgets via shortcode](05-widgets-shortcodes.md) - Inserting widgets via shortcode
- [06. Advanced blocks (HTML/embeds)](06-advanced-blocks.md) - Inserting advanced Gutenberg blocks

---

[← Back to index](../README.md) | [← Previous](03-selfhosted-app-password.md)
