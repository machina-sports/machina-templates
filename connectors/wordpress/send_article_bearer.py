import argparse
import importlib.util
import json
import os
import sys
from typing import Any, Dict, List


def _load_function(module_path: str, func_name: str):
    spec = importlib.util.spec_from_file_location("_dynamic_module_" + os.path.basename(module_path), module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    func = getattr(module, func_name)
    return func


def main() -> int:
    parser = argparse.ArgumentParser(description="Send an article as a WordPress draft using Bearer token.")
    parser.add_argument("--file-path", dest="file_path", default="articles.model.json", help="Path to JSON file")
    parser.add_argument("--json-pointer", dest="json_pointer", default="0.value", help="Dot path to article object (e.g., 0.value)")
    parser.add_argument("--image-url", dest="image_url", default=None, help="Optional remote image URL")
    parser.add_argument("--image-path", dest="image_path", default=None, help="Optional local image path")
    parser.add_argument("--image-alt", dest="image_alt", default=None, help="Optional image alt text")
    parser.add_argument("--site-url", dest="site_url", default=None, help="Override site URL (instead of env)")
    parser.add_argument("--bearer-token", dest="bearer_token", default=None, help="Override bearer token (instead of env)")

    args = parser.parse_args()

    site_url = args.site_url or os.environ.get("MACHINA_CONTEXT_VARIABLE_WORDPRESS_SITE_URL") or os.environ.get("WORDPRESS_SITE_URL")
    bearer = args.bearer_token or os.environ.get("MACHINA_CONTEXT_VARIABLE_WORDPRESS_BEARER_TOKEN") or os.environ.get("WORDPRESS_BEARER_TOKEN")

    if not site_url or not bearer:
        print("Missing environment variables: WORDPRESS_SITE_URL and WORDPRESS_BEARER_TOKEN.")
        return 2

    # 1) Read JSON
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    json_reader_path = os.path.join(repo_root, "connectors", "json-reader", "json_reader.py")
    transform_path = os.path.join(repo_root, "connectors", "transform", "transform.py")
    wordpress_path = os.path.join(os.path.dirname(__file__), "wordpress.py")

    read_json_file = _load_function(json_reader_path, "read_json_file")
    article_model_to_wp_params = _load_function(transform_path, "article_model_to_wp_params")
    create_draft_post = _load_function(wordpress_path, "create_draft_post")

    read_res = read_json_file({"params": {"file_path": args.file_path, "json_pointer": args.json_pointer}})
    if not read_res.get("status"):
        print(f"Error reading JSON: {read_res.get('message')}")
        return 1
    article_obj = read_res.get("data")

    # 2) Transform
    images: List[Dict[str, Any]] = []
    if args.image_url:
        images.append({"url": args.image_url, "alt_text": args.image_alt})
    if args.image_path:
        images.append({"file_path": args.image_path, "alt_text": args.image_alt})

    tr_res = article_model_to_wp_params({"params": {"article": article_obj, "images": images}})
    if not tr_res.get("status"):
        print(f"Error transforming article: {tr_res.get('message')}")
        return 1
    payload = tr_res.get("data", {})

    # 3) Create draft
    headers = {"site_url": site_url, "bearer_token": bearer}
    cr_res = create_draft_post({"headers": headers, "params": payload})
    if not cr_res.get("status"):
        print(f"Error creating draft: {cr_res.get('message')}")
        return 1

    data = cr_res.get("data", {})
    post = data.get("post", {})
    uploaded_media = data.get("uploaded_media", [])
    print(json.dumps({
        "post_id": post.get("id"),
        "draft_url": post.get("link"),
        "uploaded_media_ids": [m.get("id") for m in uploaded_media],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())


