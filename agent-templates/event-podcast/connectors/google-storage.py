from google.cloud import storage

import json
import mimetypes
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import os
import base64
import re


def invoke_upload(request_data):
    # Machina sometimes provides connector inputs under `params`, sometimes under `inputs`
    params = request_data.get("params") or request_data.get("inputs") or {}
    headers = request_data.get("headers") or {}

    api_key = headers.get("api_key") or params.get("api_key")
    bucket_name = headers.get("bucket_name") or params.get("bucket_name")

    # Accept file_path (generic), video_path (legacy), and image_path (legacy)
    file_input = (
        params.get("file_path")
        or params.get("video_path")
        or params.get("image_path")
    )
    if not file_input:
        return {
            "status": "error",
            "message": "file_path (or video_path / image_path) is required.",
        }

    # Ensure file_input is a string when it is not bytes
    if not isinstance(file_input, bytes):
        file_input = str(file_input)

    # Classify input
    is_url = isinstance(file_input, str) and file_input.startswith(
        ("http://", "https://", "gs://")
    )
    is_raw_bytes = isinstance(file_input, bytes)
    is_base64 = False
    base64_data = None
    mime_type = None

    if isinstance(file_input, str) and file_input.startswith("data:"):
        is_base64 = True
        try:
            header, base64_data = file_input.split(",", 1)
            mime_match = re.search(r"data:(.*?);", header)
            if mime_match:
                mime_type = mime_match.group(1)
        except Exception:
            return {"status": "error", "message": "Invalid Data URI format."}
    elif not is_url and isinstance(file_input, str) and len(file_input) > 100:
        # Simple heuristic for raw base64
        try:
            base64.b64decode(file_input[:100], validate=True)
            is_base64 = True
            base64_data = file_input
        except Exception:
            is_base64 = False

    # Resolve filename
    filename = params.get("filename")
    if not filename:
        if is_url:
            parsed_url = urllib.parse.urlparse(file_input)
            filename = os.path.basename(parsed_url.path)
            if (
                not filename
                or len(filename) < 3
                or (
                    "." not in filename
                    and not filename.replace("_", "").replace("-", "").isalnum()
                )
            ):
                if parsed_url.fragment:
                    fragment_path = parsed_url.fragment
                    fragment_filename = os.path.basename(fragment_path)
                    if fragment_filename and (
                        "." in fragment_filename
                        or len(fragment_filename) > len(filename or "")
                    ):
                        filename = fragment_filename
            if not filename:
                filename = "downloaded_file"
        elif is_base64:
            ext = ".bin"
            if mime_type:
                guessed_ext = mimetypes.guess_extension(mime_type)
                if guessed_ext:
                    ext = guessed_ext
            filename = "upload_" + os.urandom(4).hex() + ext
        elif is_raw_bytes:
            filename = "upload_" + os.urandom(4).hex() + ".bin"
        else:
            filename = os.path.basename(file_input) or (
                "upload_" + os.urandom(4).hex()
            )

    # Custom remote path, default to static/{filename}
    remote_path = params.get("remote_path")
    if remote_path:
        if remote_path.endswith("/"):
            remote = f"{remote_path}{filename}"
        else:
            remote = remote_path
    else:
        remote = f"static/{filename}"

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    temp_sa_path = None
    try:
        # Accept service account as dict, JSON string, or path to JSON file
        service_account_info = None
        if isinstance(api_key, dict):
            service_account_info = api_key
        else:
            try:
                service_account_info = json.loads(api_key)
            except Exception:
                if os.path.exists(str(api_key)):
                    with open(api_key, "r") as f:
                        service_account_info = json.load(f)
                else:
                    return {
                        "status": "error",
                        "message": "Invalid service account JSON in api_key.",
                    }

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".json"
        ) as temp_sa:
            json.dump(service_account_info, temp_sa)
            temp_sa_path = temp_sa.name

        client = storage.Client.from_service_account_json(temp_sa_path)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(remote)

        cache_control = params.get("cache_control")
        if cache_control:
            blob.cache_control = cache_control

        if is_base64:
            try:
                decoded_data = base64.b64decode(base64_data)
                content_type = (
                    mime_type
                    or mimetypes.guess_type(filename)[0]
                    or "application/octet-stream"
                )
                blob.upload_from_string(decoded_data, content_type=content_type)
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Error decoding/uploading base64: {e}",
                }

        elif is_raw_bytes:
            try:
                content_type = (
                    params.get("content_type")
                    or mimetypes.guess_type(filename)[0]
                    or "application/octet-stream"
                )
                blob.upload_from_string(file_input, content_type=content_type)
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Error uploading raw bytes: {e}",
                }

        elif is_url:
            try:
                with tempfile.NamedTemporaryFile(delete=False) as download_temp:
                    download_temp_path = download_temp.name

                # Use authenticated client for GCS URLs
                is_gcs_url = False
                source_bucket_name = None
                source_blob_name = None

                if file_input.startswith("gs://"):
                    is_gcs_url = True
                    parts = file_input[5:].split("/", 1)
                    source_bucket_name = parts[0]
                    source_blob_name = parts[1] if len(parts) > 1 else ""
                elif "storage.googleapis.com" in file_input:
                    is_gcs_url = True
                    parsed_url = urllib.parse.urlparse(file_input)
                    path_parts = parsed_url.path.lstrip("/").split("/", 1)
                    if len(path_parts) >= 2:
                        source_bucket_name = path_parts[0]
                        source_blob_name = path_parts[1]

                if is_gcs_url and source_bucket_name and source_blob_name:
                    source_bucket = client.bucket(source_bucket_name)
                    source_blob = source_bucket.blob(source_blob_name)
                    source_blob.download_to_filename(download_temp_path)
                else:
                    req = urllib.request.Request(
                        file_input, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req) as response:
                        with open(download_temp_path, "wb") as f:
                            f.write(response.read())

                content_type, _ = mimetypes.guess_type(download_temp_path)
                content_type = content_type or "application/octet-stream"

                with open(download_temp_path, "rb") as f:
                    blob.upload_from_file(f, content_type=content_type)

                if os.path.exists(download_temp_path):
                    os.unlink(download_temp_path)
            except urllib.error.URLError as e:
                return {
                    "status": "error",
                    "message": f"Failed to download file from URL: {e}",
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Error downloading from URL: {e}",
                }

        else:
            # Local file path
            if not os.path.exists(file_input):
                return {
                    "status": "error",
                    "message": f"Local file not found: {file_input}",
                }

            content_type, _ = mimetypes.guess_type(file_input)
            content_type = content_type or "application/octet-stream"

            with open(file_input, "rb") as f:
                blob.upload_from_file(f, content_type=content_type)

        blob.reload()

    except Exception as e:
        return {"status": "error", "message": f"Exception when uploading file: {e}"}
    finally:
        if temp_sa_path and os.path.exists(temp_sa_path):
            os.unlink(temp_sa_path)

    public_url = f"https://storage.googleapis.com/{bucket_name}/{remote}"
    gcs_uri = f"gs://{bucket_name}/{remote}"

    return {
        "status": True,
        "data": {
            "message": "File uploaded.",
            "url": public_url,
            "path": remote,
            "gcs_uri": gcs_uri,
            "filename": filename,
        },
    }
