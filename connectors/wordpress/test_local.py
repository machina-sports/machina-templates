import argparse
import json
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

    # Build content, optionally appending a shortcode block or raw block markup
    content_html = args.content
    if getattr(args, "shortcode", None):
        shortcode_block = f"\n\n<!-- wp:shortcode -->\n{args.shortcode}\n<!-- /wp:shortcode -->\n"
        content_html = f"{content_html}{shortcode_block}"
    # Optionally generate a contract block from JSON input
    if getattr(args, "contract_json", None):
        try:
            with open(args.contract_json, "r", encoding="utf-8") as fh:
                contract = json.load(fh)
        except Exception as e:
            raise RuntimeError(f"Failed to read --contract-json '{args.contract_json}': {e}")

        def text(value: Any, default: str = "") -> str:
            return (value or default)

        name = text(contract.get("name"))
        team = text(contract.get("team"))
        length = text(contract.get("length"))
        salary = text(contract.get("salary"))
        contract_type = text(contract.get("contract_type"))
        total = text(contract.get("total"))
        date_str = text(contract.get("date"))

        contract_block = """
<!-- wp:group {"style":{"border":{"radius":"12px","width":"1px"},"spacing":{"padding":{"top":"16px","bottom":"16px","left":"16px","right":"16px"}}}} -->
<div class="wp-block-group" style="border-width:1px;border-radius:12px;padding-top:16px;padding-bottom:16px;padding-left:16px;padding-right:16px">
<!-- wp:columns {"verticalAlignment":"top"} -->
<div class="wp-block-columns are-vertically-aligned-top">
<!-- wp:column {"width":"38%"} -->
<div class="wp-block-column" style="flex-basis:38%">
<!-- wp:heading {"level":3} -->
<h3>__NAME__</h3>
<!-- /wp:heading -->
<!-- wp:paragraph {"fontSize":"small"} -->
<p class="has-small-font-size"><strong>SIGNED BY</strong></p>
<!-- /wp:paragraph -->
<!-- wp:paragraph {"fontSize":"large"} -->
<p class="has-large-font-size"><strong>__TEAM__</strong></p>
<!-- /wp:paragraph -->
</div>
<!-- /wp:column -->

<!-- wp:column {"width":"62%"} -->
<div class="wp-block-column" style="flex-basis:62%">
<!-- wp:columns {"columns":2} -->
<div class="wp-block-columns has-2-columns">
<!-- wp:column -->
<div class="wp-block-column">
<!-- wp:paragraph --><p><strong>Length:</strong><br/>__LENGTH__</p><!-- /wp:paragraph -->
<!-- wp:paragraph --><p><strong>Salary Cap Hit:</strong><br/>__SALARY__</p><!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
<!-- wp:column -->
<div class="wp-block-column">
<!-- wp:paragraph --><p><strong>Contract Type:</strong><br/>__CTYPE__</p><!-- /wp:paragraph -->
<!-- wp:paragraph --><p><strong>Total:</strong><br/>__TOTAL__</p><!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
</div>
<!-- /wp:columns -->
<!-- wp:paragraph {"align":"center","fontSize":"small"} -->
<p class="has-text-align-center has-small-font-size">__DATE__</p>
<!-- /wp:paragraph -->
</div>
<!-- /wp:column -->
</div>
<!-- /wp:columns -->
</div>
<!-- /wp:group -->
"""

        # Replace tokens with values
        contract_block = (
            contract_block
            .replace("__NAME__", name)
            .replace("__TEAM__", team)
            .replace("__LENGTH__", length)
            .replace("__SALARY__", salary)
            .replace("__CTYPE__", contract_type.title())
            .replace("__TOTAL__", total)
            .replace("__DATE__", date_str)
        )
        content_html = f"{content_html}\n\n{contract_block}"

    # Combine inline block and file-based block (if both provided, append both)
    block_markup = getattr(args, "block", None)
    block_file = getattr(args, "block_file", None)
    if block_file:
        try:
            with open(block_file, "r", encoding="utf-8") as fh:
                file_block = fh.read()
            block_markup = f"{block_markup or ''}{('\n\n' if block_markup else '')}{file_block}" if file_block else block_markup
        except Exception as e:
            raise RuntimeError(f"Failed to read --block-file '{block_file}': {e}")
    if block_markup:
        # Append raw Gutenberg block markup as provided (caller is responsible for correctness)
        content_html = f"{content_html}\n\n{block_markup}"

    params = {
        "title": args.title,
        "content_html": content_html,
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
    parser.add_argument(
        "--shortcode",
        dest="shortcode",
        default=None,
        help="Optional shortcode to embed via a Shortcode block (e.g., [my_custom_widget attr=\"x\"]).",
    )
    parser.add_argument(
        "--block",
        dest="block",
        default=None,
        help="Optional raw Gutenberg block markup to append (use PowerShell here-string to pass multi-line).",
    )
    parser.add_argument(
        "--block-file",
        dest="block_file",
        default=None,
        help="Path to a file containing raw Gutenberg block markup to append.",
    )
    parser.add_argument(
        "--contract-json",
        dest="contract_json",
        default=None,
        help="Path to a JSON file with contract data to render a core-blocks card (no custom CSS).",
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


