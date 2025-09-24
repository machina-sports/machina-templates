# 03. Self-hosted (Application Password)

## Setup for self-hosted WordPress

### 1. Configure Application Password

1. In your WordPress Admin, go to `Users → Profile` for the user who will make posts
2. Scroll to the `Application Passwords` section
3. In `Add new application password`:
   - **Name**: Application name (e.g., "Machina Connector")
   - Click "Add new application password"
4. **Copy the generated password** (format: `abcd efgh ijkl mnop`)
5. Click "Close"

### 2. Configure environment variables

For self-hosted tests, configure these variables:

```powershell
$env:WORDPRESS_SITE_URL = "https://example.com"
$env:WORDPRESS_USERNAME = "your_user"
$env:WORDPRESS_APP_PASSWORD = "abcd efgh ijkl mnop"
```

**Important**: 
- Use the complete site URL (e.g., `https://example.com`)
- Use WordPress username (not email)
- Use the generated application password (not your login password)

### 3. Verify configuration

Make sure that:
- The user has permissions to create posts
- The site is accessible via HTTPS
- No security plugins are blocking Application Passwords

## Environment variables for workflows

For the provided workflows, you can also use these context variables when running in the Machina runtime:

- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_SITE_URL`
- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_USERNAME`
- `MACHINA_CONTEXT_VARIABLE_WORDPRESS_APP_PASSWORD`

## Complete configuration example

```powershell
# Configure for current PowerShell session
$env:WORDPRESS_SITE_URL = "https://mysite.com"
$env:WORDPRESS_USERNAME = "admin"
$env:WORDPRESS_APP_PASSWORD = "abcd efgh ijkl mnop"

# Verify they were configured
Write-Output "SITE_URL: $env:WORDPRESS_SITE_URL"
Write-Output "USERNAME: $env:WORDPRESS_USERNAME"
Write-Output "APP_PASSWORD: $env:WORDPRESS_APP_PASSWORD"
```

## Next steps

- [04. Local tests (scripts)](04-local-tests.md) - How to test locally
- [05. Widgets via shortcode](05-widgets-shortcodes.md) - Inserting widgets via shortcode

---

[← Back to index](../README.md) | [← Previous](02-oauth-wpcom.md)
