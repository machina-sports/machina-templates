import argparse
import os
import sys
from typing import Any, Dict

from wordpress import create_draft_post


def build_request_data(args: argparse.Namespace) -> Dict[str, Any]:
    headers = {
        "site_url": args.site_url or os.environ.get("WORDPRESS_SITE_URL"),
    }
    # prefer WordPress.com bearer token if provided
    bearer = args.bearer_token or os.environ.get("WORDPRESS_BEARER_TOKEN")
    if bearer:
        headers["bearer_token"] = bearer
    else:
        headers["username"] = args.username or os.environ.get("WORDPRESS_USERNAME")
        headers["application_password"] = args.app_password or os.environ.get("WORDPRESS_APP_PASSWORD")

    images = []
    if args.image_url:
        images.append({"url": args.image_url, "title": "Uploaded via test_local"})
    if args.image_path:
        images.append({"file_path": args.image_path, "title": "Uploaded via test_local"})

    params = {
        "title": args.title,
        "content_html": args.content,
        "excerpt": args.excerpt,
        "images": images,
        "set_featured_image": True,
        "auto_append_images": True,
    }

    return {"headers": headers, "params": params}


def main() -> int:
    parser = argparse.ArgumentParser(description="Local test for WordPress draft push.")
    parser.add_argument("--title", required=True, help="Post title")
    parser.add_argument("--content", default="<p>Hello from local test.</p>", help="Post HTML content")
    parser.add_argument("--excerpt", default=None, help="Optional excerpt")
    parser.add_argument("--image-url", dest="image_url", default=None, help="Optional image URL to upload")
    parser.add_argument("--image-path", dest="image_path", default=None, help="Optional local image path to upload")

    parser.add_argument("--site-url", dest="site_url", default=None, help="WordPress site URL (override env)")
    parser.add_argument("--username", dest="username", default=None, help="WordPress username (override env)")
    parser.add_argument(
        "--app-password",
        dest="app_password",
        default=None,
        help="WordPress Application Password (override env)",
    )
    parser.add_argument(
        "--bearer-token",
        dest="bearer_token",
        default=None,
        help="WordPress.com OAuth Bearer token (overrides username/app-password)",
    )

    args = parser.parse_args()

    request_data = build_request_data(args)
    result = create_draft_post(request_data)

    if not result.get("status"):
        print(f"Error: {result.get('message')}")
        return 1

    data = result.get("data", {})
    post = data.get("post", {})
    print("Draft created successfully.")
    print(f"Post ID: {post.get('id')}")
    print(f"Post Link: {post.get('link')}")
    uploaded_media = data.get("uploaded_media", [])
    if uploaded_media:
        print("Uploaded media IDs:", [m.get("id") for m in uploaded_media])
    return 0


if __name__ == "__main__":
    sys.exit(main())


