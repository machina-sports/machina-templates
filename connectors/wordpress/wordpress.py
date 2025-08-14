import base64
import mimetypes
import os
from typing import Any, Dict, List, Tuple

import requests
from urllib.parse import urlparse


def _build_basic_auth(username: str, application_password: str) -> Dict[str, str]:
    token = base64.b64encode(f"{username}:{application_password}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}


def _build_bearer_auth(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _detect_mode(headers: Dict[str, Any], params: Dict[str, Any]) -> str:
    """Return 'wpcom' if bearer_token provided, else 'selfhosted'."""
    if (headers.get("bearer_token") or params.get("bearer_token")):
        return "wpcom"
    return "selfhosted"


def _normalize_site_url(site_url: str) -> str:
    if not site_url:
        return site_url
    return site_url.rstrip("/")


def _get_site_domain(site_url: str) -> str:
    """Extract domain for WordPress.com API (sites/{domain})."""
    parsed = urlparse(site_url if "://" in site_url else f"https://{site_url}")
    domain = parsed.netloc or parsed.path
    return domain.rstrip("/")


def _get_credentials_and_base(headers: Dict[str, Any], params: Dict[str, Any]) -> Tuple[str, Dict[str, str], str]:
    """
    Returns (mode, auth_header, api_base).
    - mode: 'selfhosted' or 'wpcom'
    - auth_header: dict with Authorization header
    - api_base: base URL to wp/v2 (no trailing slash)
    """
    site_url = headers.get("site_url") or params.get("site_url")
    if not site_url:
        raise ValueError("Missing WordPress 'site_url'.")

    mode = _detect_mode(headers, params)

    if mode == "wpcom":
        token = headers.get("bearer_token") or params.get("bearer_token")
        if not token:
            raise ValueError("Missing WordPress.com 'bearer_token'.")
        domain = _get_site_domain(site_url)
        api_base = f"https://public-api.wordpress.com/wp/v2/sites/{domain}"
        return mode, _build_bearer_auth(token), api_base

    # self-hosted (Application Password)
    username = headers.get("username") or params.get("username")
    application_password = headers.get("application_password") or params.get("application_password")
    if not username:
        raise ValueError("Missing WordPress 'username'.")
    if not application_password:
        raise ValueError("Missing WordPress 'application_password'.")
    base = _normalize_site_url(site_url)
    api_base = f"{base}/wp-json/wp/v2"
    return mode, _build_basic_auth(username, application_password), api_base


def _refresh_wpcom_access_token(params: Dict[str, Any]) -> Dict[str, Any]:
    client_id = params.get("client_id")
    client_secret = params.get("client_secret")
    refresh_token = params.get("refresh_token")
    if not client_id or not client_secret or not refresh_token:
        return {"status": False, "message": "Missing client_id, client_secret or refresh_token for refresh."}
    try:
        body = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        resp = requests.post(
            "https://public-api.wordpress.com/oauth2/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        if resp.status_code >= 400:
            return {"status": False, "message": f"Refresh failed: {resp.status_code} - {resp.text}"}
        payload = resp.json()
        return {"status": True, "data": payload}
    except Exception as e:
        return {"status": False, "message": f"Exception refreshing token: {e}"}


def _safe_filename(path_or_name: str) -> str:
    name = os.path.basename(path_or_name)
    return name or "upload.bin"


def _guess_mime_type(filename: str) -> str:
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def _download_file_to_bytes(url: str, timeout: int = 30, headers: Dict[str, str] | None = None) -> bytes:
    resp = requests.get(url, timeout=timeout, headers=headers or {})
    resp.raise_for_status()
    return resp.content


def upload_media(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a media asset to WordPress Media Library.

    headers: expects site_url, username, application_password
    params:
      - file_path: local path to the file (optional if url provided)
      - url: remote URL to download and upload (optional if file_path provided)
      - filename: override filename (optional)
      - title: media title (optional)
      - alt_text: alternative text (optional)
      - caption: caption HTML/text (optional)
      - description: description (optional)
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        mode, auth_header, api_base = _get_credentials_and_base(headers, params)
    except Exception as e:
        return {"status": False, "message": str(e)}

    file_path = params.get("file_path")
    remote_url = params.get("url")
    override_filename = params.get("filename")
    title = params.get("title")
    alt_text = params.get("alt_text")
    caption = params.get("caption")
    description = params.get("description")

    if not file_path and not remote_url:
        return {"status": False, "message": "Either 'file_path' or 'url' must be provided."}

    try:
        if remote_url:
            # Build download headers with a compliant User-Agent for sources like Wikimedia
            default_ua = "machina-templates-wordpress-connector/1.0 (+https://machina.ai)"
            download_user_agent = (
                headers.get("download_user_agent")
                or params.get("download_user_agent")
                or default_ua
            )
            extra_download_headers = params.get("download_headers") or {}
            dl_headers = {"User-Agent": download_user_agent, **extra_download_headers}
            file_bytes = _download_file_to_bytes(remote_url, headers=dl_headers)
            filename = override_filename or _safe_filename(remote_url)
        else:
            filename = override_filename or _safe_filename(file_path)
            with open(file_path, "rb") as f:
                file_bytes = f.read()

        mime_type = _guess_mime_type(filename)

        api_url = f"{api_base}/media"

        files = {"file": (filename, file_bytes, mime_type)}
        data: Dict[str, Any] = {}
        if title:
            data["title"] = title
        if caption:
            data["caption"] = caption
        if description:
            data["description"] = description
        if alt_text:
            data["alt_text"] = alt_text

        resp = requests.post(api_url, headers=auth_header, files=files, data=data, timeout=60)
        if resp.status_code >= 400:
            return {"status": False, "message": f"Media upload failed: {resp.status_code} - {resp.text}"}

        media = resp.json()
        return {"status": True, "data": media, "message": "Media uploaded."}

    except Exception as e:
        return {"status": False, "message": f"Exception during media upload: {e}"}


def create_draft_post(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a draft post and optionally upload and attach images.

    headers: expects site_url, username, application_password
    params:
      - title: required
      - content_html: optional HTML content
      - excerpt: optional
      - categories: optional list of category IDs
      - tags: optional list of tag IDs
      - images: optional list of image dicts. Each item can include:
          {file_path|url, filename?, title?, alt_text?, caption?, description?}
      - set_featured_image: bool, default True
      - auto_append_images: bool, default True. If content_html doesn't include these images, append them at the end.
    """
    headers = request_data.get("headers", {})
    params = request_data.get("params", {})

    try:
        mode, auth_header, api_base = _get_credentials_and_base(headers, params)
    except Exception as e:
        return {"status": False, "message": str(e)}

    title = params.get("title")
    if not title:
        return {"status": False, "message": "Missing required 'title'."}

    content_html = params.get("content_html", "")
    excerpt = params.get("excerpt")
    categories = params.get("categories") or []
    tags = params.get("tags") or []
    images = params.get("images") or []
    set_featured_image = params.get("set_featured_image", True)
    auto_append_images = params.get("auto_append_images", True)

    uploaded_media: List[Dict[str, Any]] = []

    # 1) Upload images if provided
    for img in images:
        try:
            media_payload = {
                "headers": headers,
                "params": {
                    "file_path": img.get("file_path"),
                    "url": img.get("url"),
                    "filename": img.get("filename"),
                    "title": img.get("title"),
                    "alt_text": img.get("alt_text"),
                    "caption": img.get("caption"),
                    "description": img.get("description"),
                },
            }
            result = upload_media(media_payload)
            if not result.get("status"):
                return {"status": False, "message": f"Image upload failed: {result.get('message')}"}
            uploaded_media.append(result.get("data", {}))
        except Exception as e:
            return {"status": False, "message": f"Exception uploading image: {e}"}

    # 2) Optionally append uploaded images to the content
    if auto_append_images and uploaded_media:
        appended_html_parts: List[str] = []
        for media in uploaded_media:
            src = media.get("source_url")
            alt = media.get("alt_text") or ""
            if src and (src not in content_html):
                appended_html_parts.append(
                    f'<figure class="wp-block-image"><img src="{src}" alt="{alt}" /></figure>'
                )
        if appended_html_parts:
            content_html = f"{content_html}\n\n" + "\n".join(appended_html_parts)

    # 3) Create the draft post
    post_endpoint = f"{api_base}/posts"
    post_body: Dict[str, Any] = {
        "title": title,
        "content": content_html,
        "status": "draft",
    }
    if excerpt is not None:
        post_body["excerpt"] = excerpt
    if categories:
        post_body["categories"] = categories
    if tags:
        post_body["tags"] = tags

    # Set featured image to first uploaded media if requested
    if set_featured_image and uploaded_media:
        first_media_id = uploaded_media[0].get("id")
        if first_media_id:
            post_body["featured_media"] = first_media_id

    try:
        resp = requests.post(post_endpoint, headers=auth_header, json=post_body, timeout=60)
        if resp.status_code >= 400:
            return {"status": False, "message": f"Create post failed: {resp.status_code} - {resp.text}"}
        post = resp.json()
        return {
            "status": True,
            "data": {
                "post": post,
                "uploaded_media": uploaded_media,
            },
            "message": "Draft post created.",
        }
    except Exception as e:
        return {"status": False, "message": f"Exception creating post: {e}"}


