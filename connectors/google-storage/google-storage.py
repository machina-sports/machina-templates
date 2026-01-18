from google.cloud import storage

import json
import mimetypes
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import os

# BUCKET = "machina-templates-bucket-default"

def invoke_upload(request_data):

    # Machina sometimes provides connector inputs under `params`, sometimes under `inputs`
    params = request_data.get("params") or request_data.get("inputs") or {}
    headers = request_data.get("headers") or {}

    api_key = headers.get("api_key") or params.get("api_key")

    bucket_name = headers.get("bucket_name") or params.get("bucket_name")

    # Backwards compatible: historically this connector used `image_path`, but workflows may
    # upload videos or other assets via `video_path` or `file_path`.
    file_path = params.get("file_path") or params.get("video_path") or params.get("image_path")
    if not file_path:
        return {"status": "error", "message": "file_path (or video_path / image_path) is required."}

    # Normalize to string
    file_path = str(file_path)

    # Check if file_path is a URL
    is_url = file_path.startswith(('http://', 'https://'))

    # Get filename from file_path or use default
    filename = params.get("filename")
    if not filename:
        if is_url:
            # For URLs, extract exact filename from URL path or fragment
            parsed_url = urllib.parse.urlparse(file_path)

            # First try to get filename from path
            filename = os.path.basename(parsed_url.path)

            # Check if the filename from path has an extension or is reasonable
            # If not, check the fragment (for Wikipedia URLs and similar)
            if (not filename or
                (len(filename) < 3) or
                ('.' not in filename and not filename.replace('_', '').replace('-', '').isalnum())):

                if parsed_url.fragment:
                    # Fragment might be in format "/media/Ficheiro:filename.ext"
                    fragment_path = parsed_url.fragment
                    if fragment_path.startswith('/media/'):
                        fragment_filename = os.path.basename(fragment_path)
                    else:
                        fragment_filename = os.path.basename(fragment_path)

                    # Use fragment filename if it's more likely to be the actual file
                    if (fragment_filename and
                        ('.' in fragment_filename or len(fragment_filename) > len(filename))):
                        filename = fragment_filename

            # Final fallback if still no filename
            if not filename:
                filename = "downloaded_file"
        else:
            # For local files, use exact basename (preserve as-is)
            filename = os.path.basename(file_path)

    # Allow custom remote path, default to static/{filename} for backwards compatibility
    remote_path = params.get("remote_path")
    if remote_path:
        # If remote_path ends with /, append filename
        if remote_path.endswith("/"):
            remote = f"{remote_path}{filename}"
        else:
            remote = remote_path
    else:
        remote = f"static/{filename}"

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    # Handle temporary file for both URLs and local files
    temp_file_path = None

    try:
        service_account_info = json.loads(api_key)
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid service account JSON in api_key"}

    try:
        # Create temporary service account file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            json.dump(service_account_info, temp_file)
            temp_file_path = temp_file.name

        client = storage.Client.from_service_account_json(temp_file_path)

        bucket = client.bucket(bucket_name)
        blob = bucket.blob(remote)

        # Download file if it's a URL or use local file
        if is_url:
            # Download from URL to temporary file
            try:
                with tempfile.NamedTemporaryFile(delete=False) as download_temp:
                    download_temp_path = download_temp.name

                # Download the file
                req = urllib.request.Request(file_path, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    with open(download_temp_path, 'wb') as f:
                        f.write(response.read())

                # Detect content type from downloaded file
                content_type, _ = mimetypes.guess_type(download_temp_path)
                if not content_type:
                    content_type = "application/octet-stream"

                # Upload the downloaded file
                with open(download_temp_path, "rb") as f:
                    blob.upload_from_file(f, content_type=content_type)

                # Clean up downloaded temp file
                os.unlink(download_temp_path)

            except urllib.error.URLError as e:
                return {"status": "error", "message": f"Failed to download file from URL: {e}"}
            except Exception as e:
                return {"status": "error", "message": f"Error downloading file: {e}"}
        else:
            # Handle local file
            if not os.path.exists(file_path):
                return {"status": "error", "message": f"Local file not found: {file_path}"}

            # Detect content type based on file extension
            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                content_type = "application/octet-stream"

            with open(file_path, "rb") as f:
                blob.upload_from_file(f, content_type=content_type)

        blob.reload()

    except Exception as e:
        return {"status": "error", "message": f"Exception when uploading file: {e}"}
    finally:
        # Clean up service account temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    public_url = f"https://storage.googleapis.com/{bucket_name}/{remote}"

    return {
        "status": True,
        "data": {
            "message": "File uploaded.",
            "url": public_url,
            "path": remote
        }
    }
