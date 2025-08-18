# 02. WordPress.com OAuth

## OAuth setup for WordPress.com

### 1. Create application in Developer Console

1. Access the [WordPress.com Developer Console](https://developer.wordpress.com/apps/)
2. Login with the account that administers the target site
3. Click "Create a new application"
4. Configure:
   - **Name**: Your application name
   - **Description**: Optional description
   - **Website URL**: Your site URL
   - **Redirect URLs**: `http://localhost:8765/callback` (for manual flows)
5. Click "Create application"
6. Note your `client_id` and `client_secret`

### 2. Authorization URL

Use this URL to authorize (login as site admin; request correct scopes):

```text
https://public-api.wordpress.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A8765%2Fcallback&response_type=code&scope=global%20posts%20media
```

**Important**: Replace `YOUR_CLIENT_ID` with your actual client_id.

### 3. Get authorization code

1. Access the authorization URL in your browser
2. Login with the account that administers the site
3. Authorize the application
4. You will be redirected to a URL like:
   ```
   http://localhost:8765/callback?code=CODE_HERE
   ```
5. **Copy only the value of the `code` parameter** (not the entire URL)

### 4. Exchange code for access token

Use PowerShell to exchange the code for a token (example):

```powershell
$client_id = "YOUR_CLIENT_ID"
$client_secret = "YOUR_CLIENT_SECRET"
$redirect_uri = "http://localhost:8765/callback"
$code = "PASTE_CODE_FROM_REDIRECT"

$body = "client_id=$client_id&client_secret=$client_secret&redirect_uri=$([System.Uri]::EscapeDataString($redirect_uri))&grant_type=authorization_code&code=$code"
$resp = Invoke-RestMethod -Method Post -Uri "https://public-api.wordpress.com/oauth2/token" -ContentType "application/x-www-form-urlencoded" -Body $body
$token = $resp.access_token
```

### 5. Validate token

Test the token against your site (must return 200):

```powershell
$h = @{ Authorization = "Bearer $token" }
Invoke-RestMethod "https://public-api.wordpress.com/rest/v1.1/sites/YOUR_SITE.wordpress.com" -Headers $h | Out-Null
Invoke-RestMethod "https://public-api.wordpress.com/rest/v1.1/sites/YOUR_SITE.wordpress.com/posts?number=1" -Headers $h | Out-Null
```

**Replace `YOUR_SITE.wordpress.com` with your site's domain.**

### 6. Configure environment variables

For WordPress.com tests after obtaining `$token`:

```powershell
$env:WORDPRESS_SITE_URL = "https://YOUR_SITE.wordpress.com"
$env:WORDPRESS_BEARER_TOKEN = $token
```

## Important notes

- **Scopes**: Make sure to request `global posts media` during authorization
- **Validation**: If validation fails (401), verify you authorized while logged into the account that administers the site
- **Refresh token**: Keep the `refresh_token` if the response includes it. Some flows may not return it
- **Re-authorization**: Use bearer-only flow or re-authorize when the token expires

## Next steps

- [03. Self-hosted (Application Password)](03-selfhosted-app-password.md) - Setup for self-hosted WordPress
- [04. Local tests (scripts)](04-local-tests.md) - How to test locally

---

[← Back to index](../README.md) | [← Previous](01-prereqs.md)
