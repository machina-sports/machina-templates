"""Stability image connector with sandboxed artifact output."""

import os
import re
import uuid
from pathlib import Path

import requests

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def generate_image(request_data):
    request_data = request_data or {}
    headers = request_data.get("headers") or {}
    params = request_data.get("params") or request_data
    api_key = headers.get("api_key") or params.get("api_key")
    if not api_key:
        return {"status": False, "data": None, "message": "API key is required."}

    image_id = SAFE_NAME.sub("-", str(params.get("image_id") or "stability-image")).strip("-.")
    image_id = image_id[:80] or "stability-image"
    configuration = params.get("configuration") or {}
    try:
        response = requests.post(
            "https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={"Accept": "image/*", "Authorization": f"Bearer {api_key}"},
            files=configuration,
            timeout=(5, 60),
            allow_redirects=False,
        )
        response.raise_for_status()
        root = Path(os.getenv("MACHINA_WORK_DIR", os.getcwd())).expanduser().resolve()
        output_dir = root / "images"
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{image_id}-{uuid.uuid4().hex}.webp"
        output = (output_dir / filename).resolve()
        if root != output and root not in output.parents:
            return {"status": False, "data": None, "message": "The image output path is not allowed."}
        output.write_bytes(response.content)
        return {
            "status": True,
            "data": {"final_filename": filename, "full_filepath": str(output.relative_to(root))},
            "message": "Image generated.",
        }
    except Exception:
        return {"status": False, "data": None, "message": "The Stability provider could not generate an image."}
