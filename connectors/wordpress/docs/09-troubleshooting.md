# 09. Troubleshooting

## Common problem resolution

### 401 Unauthorized

**Symptom**: 401 error when trying to create posts or upload media

**Causes and solutions**:

#### WordPress.com (Bearer token)
- **Expired token**: Re-authorize your OAuth application
- **Incorrect scopes**: Make sure to request `global posts media`
- **Wrong account**: Authorize while logged into the account that administers the site

#### Self-hosted (Application Password)
- **Incorrect password**: Verify you copied the application password correctly
- **Wrong username**: Use WordPress username (not email)
- **Permissions**: Verify the user can create posts

### 403 Forbidden

**Symptom**: 403 error when downloading images

**Solutions**:
- **Restrictive CDN**: Try another image source
- **User-Agent**: Use `--image-path` for local files
- **Custom headers**: Programmatically, customize `download_user_agent`/`download_headers`

### Incorrect site URL

**Symptom**: Connection errors or site not found

**Solutions**:
- **Self-hosted**: Use complete site URL (e.g., `https://example.com`)
- **WordPress.com**: Use domain (e.g., `example.wordpress.com`) or complete URL

### SSL/Proxy issues

**Symptom**: Connection errors or timeout

**Solutions**:
- Confirm your network/proxy trusts the endpoints
- Verify `requests` can reach the endpoints
- Test basic connectivity first

### Blocks don't render

**Symptom**: Raw HTML appears instead of rendered component

**Solutions**:
- **Block doesn't exist**: Verify the block type is available
- **Plugin disabled**: For third-party blocks, ensure the plugin is active
- **Incompatible theme**: Test with default WordPress theme
- **Sanitization**: Use WordPress core blocks when possible

### Shortcode problems

**Symptom**: Shortcode appears as plain text

**Solutions**:
- **Shortcode not registered**: Verify the plugin/theme registered the shortcode
- **Permissions**: Confirm security plugins allow shortcodes
- **Test**: Publish the draft and view the front-end

### Python syntax errors

**Symptom**: `SyntaxError: f-string: expressions nested too deeply`

**Solution**: 
- Use placeholders and `.replace()` instead of nested f-strings
- Example in `test_local.py` with `--contract-json`

### Virtual environment problems

**Symptom**: Modules not found or incorrect versions

**Solutions**:
- **Activate venv**: `.venv\Scripts\Activate.ps1` (Windows)
- **Install dependencies**: `pip install -U requests`
- **Check Python**: Make sure to use Python 3.10+

## Configuration validation

### Basic connectivity test

```powershell
# WordPress.com
$h = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "https://public-api.wordpress.com/rest/v1.1/sites/YOUR_SITE.wordpress.com" -Headers $h | Out-Null

# Self-hosted
$cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$username:$app_password"))
$h = @{ Authorization = "Basic $cred" }
Invoke-RestMethod "https://YOUR_SITE.com/wp-json/wp/v2/posts?per_page=1" -Headers $h | Out-Null
```

### Check environment variables

```powershell
Write-Output "SITE_URL: $env:WORDPRESS_SITE_URL"
Write-Output "USERNAME: $env:WORDPRESS_USERNAME"
Write-Output "APP_PASSWORD: $env:WORDPRESS_APP_PASSWORD"
Write-Output "BEARER_TOKEN: $env:WORDPRESS_BEARER_TOKEN"
```

## Logs and debugging

### Enable detailed logs

For advanced debugging, modify scripts to include:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check API responses

Capture and analyze complete API responses to identify specific problems.

## Additional resources

- [WordPress REST API Handbook](https://developer.wordpress.org/rest-api/)
- [WordPress.com API Documentation](https://developer.wordpress.com/docs/api/)
- [Gutenberg Block Reference](https://developer.wordpress.org/block-editor/reference-guides/block-api/block-registration/)

## Support

For problems not covered here:
1. Check error logs
2. Test with minimal configuration
3. Compare with working examples
4. Consult WordPress API documentation

---

[← Back to index](../README.md) | [← Previous](08-contract-card.md)
