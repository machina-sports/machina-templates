
def invoke_upload(request_data):
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

    # Handle different Machina request structures (params vs inputs)
    params = request_data.get("params") or request_data.get("inputs") or {}
    headers = request_data.get("headers") or {}

    # api_key and bucket_name can be in headers or params
    api_key = headers.get("api_key") or params.get("api_key")
    bucket_name = headers.get("bucket_name") or params.get("bucket_name")

    # Accept both image_path (legacy) and file_path (generic)
    file_input = params.get("file_path") or params.get("image_path")
    
    if not file_input:
        return {"status": "error", "message": "file_path or image_path is required."}

    # Ensure file_input is a string if it's not bytes
    if not isinstance(file_input, bytes):
        file_input = str(file_input)

    # Check the type of input
    is_url = isinstance(file_input, str) and file_input.startswith(('http://', 'https://', 'gs://'))
    is_base64 = False
    is_raw_bytes = isinstance(file_input, bytes)
    base64_data = None
    mime_type = None

    # Detect Base64 (Data URI or raw)
    if isinstance(file_input, str) and file_input.startswith('data:'):
        is_base64 = True
        try:
            # Format: data:audio/mp3;base64,AAAA...
            header, base64_data = file_input.split(',', 1)
            mime_match = re.search(r'data:(.*?);', header)
            if mime_match:
                mime_type = mime_match.group(1)
        except Exception:
            return {"status": "error", "message": "Invalid Data URI format."}
    elif not is_url and isinstance(file_input, str) and len(file_input) > 100: # Simple heuristic for raw base64
        # Check if it's a valid base64 string
        try:
            # Try to decode a small piece to verify
            base64.b64decode(file_input[:100], validate=True)
            is_base64 = True
            base64_data = file_input
        except Exception:
            is_base64 = False

    # Get filename
    filename = params.get("filename")
    if not filename:
        if is_url:
            parsed_url = urllib.parse.urlparse(file_input)
            filename = os.path.basename(parsed_url.path)
            if not filename or len(filename) < 3:
                query_params = urllib.parse.parse_qs(parsed_url.query)
                if 'id' in query_params:
                    filename = f"drive_{query_params['id'][0]}.bin"
                else:
                    filename = "upload_" + os.urandom(4).hex()
        elif is_base64:
            ext = ".bin"
            if mime_type:
                guessed_ext = mimetypes.guess_extension(mime_type)
                if guessed_ext:
                    ext = guessed_ext
            filename = "voice_upload_" + os.urandom(4).hex() + ext
        elif is_raw_bytes:
            filename = params.get("filename") or "upload_" + os.urandom(4).hex() + ".bin"
        else:
            filename = os.path.basename(file_input) or "upload_" + os.urandom(4).hex()

    remote = f"static/{filename}"

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    temp_file_path = None
    temp_sa_path = None
    try:
        # Handle service account
        service_account_info = None
        if isinstance(api_key, dict):
            service_account_info = api_key
        else:
            try:
                service_account_info = json.loads(api_key)
            except Exception:
                if os.path.exists(str(api_key)):
                    with open(api_key, 'r') as f:
                        service_account_info = json.load(f)
                else:
                    return {"status": "error", "message": "Invalid service account key."}

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_sa:
            json.dump(service_account_info, temp_sa)
            temp_sa_path = temp_sa.name

        client = storage.Client.from_service_account_json(temp_sa_path)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(remote)

        if is_base64:
            # Upload Base64 data
            try:
                decoded_data = base64.b64decode(base64_data)
                content_type = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                blob.upload_from_string(decoded_data, content_type=content_type)
            except Exception as e:
                return {"status": "error", "message": f"Error decoding/uploading base64: {str(e)}"}
        
        elif is_raw_bytes:
            # Upload raw bytes
            try:
                content_type = params.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                blob.upload_from_string(file_input, content_type=content_type)
            except Exception as e:
                return {"status": "error", "message": f"Error uploading raw bytes: {str(e)}"}

        elif is_url:
            # Download and upload from URL
            try:
                with tempfile.NamedTemporaryFile(delete=False) as download_temp:
                    download_temp_path = download_temp.name

                # Check if it's a GCS URL to use the authenticated client
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
                    # Format: https://storage.googleapis.com/bucket-name/object-path
                    parsed_url = urllib.parse.urlparse(file_input)
                    path_parts = parsed_url.path.lstrip("/").split("/", 1)
                    if len(path_parts) >= 2:
                        source_bucket_name = path_parts[0]
                        source_blob_name = path_parts[1]

                if is_gcs_url and source_bucket_name and source_blob_name:
                    # Use authenticated client for GCS URLs
                    source_bucket = client.bucket(source_bucket_name)
                    source_blob = source_bucket.blob(source_blob_name)
                    source_blob.download_to_filename(download_temp_path)
                else:
                    # Regular URL download
                    req = urllib.request.Request(file_input, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req) as response:
                        with open(download_temp_path, 'wb') as f:
                            f.write(response.read())

                content_type, _ = mimetypes.guess_type(download_temp_path)
                content_type = content_type or "application/octet-stream"

                with open(download_temp_path, "rb") as f:
                    blob.upload_from_file(f, content_type=content_type)

                if os.path.exists(download_temp_path):
                    os.unlink(download_temp_path)
            except Exception as e:
                return {"status": "error", "message": f"Error downloading from URL: {str(e)}"}
        else:
            # Handle local file
            if not os.path.exists(file_input):
                return {"status": "error", "message": f"Local file not found: {file_input}"}

            content_type, _ = mimetypes.guess_type(file_input)
            content_type = content_type or "application/octet-stream"

            with open(file_input, "rb") as f:
                blob.upload_from_file(f, content_type=content_type)

        if os.path.exists(temp_sa_path):
            os.unlink(temp_sa_path)

        # blob.reload() # Optional, sometimes fails if permissions are tight
        public_url = f"https://storage.googleapis.com/{bucket_name}/{remote}"
        gcs_uri = f"gs://{bucket_name}/{remote}"

        return {
            "status": True,
            "data": {
                "message": "File uploaded successfully.",
                "url": public_url,
                "path": remote,
                "gcs_uri": gcs_uri,
                "filename": filename
            }
        }

    except Exception as e:
        if temp_sa_path and os.path.exists(temp_sa_path):
            os.unlink(temp_sa_path)
        return {"status": "error", "message": f"Exception: {str(e)}"}


def generate_signed_url(request_data):
    """
    Generates a signed URL for uploading a file directly to Google Cloud Storage.
    This allows the frontend to send raw bytes (PUT) without passing through the backend.
    """
    from google.cloud import storage
    import json
    import tempfile
    import os
    from datetime import timedelta

    params = request_data.get("params") or request_data.get("inputs") or {}
    headers = request_data.get("headers") or {}

    api_key = headers.get("api_key")
    bucket_name = headers.get("bucket_name")
    
    filename = params.get("filename")
    content_type = params.get("content_type", "application/octet-stream")
    expiration_minutes = int(params.get("expiration_minutes", 15))

    if not api_key:
        return {"status": "error", "message": "API key is required."}
    
    if not filename:
         # Generate a random filename if not provided
         filename = "upload_" + os.urandom(4).hex() + ".bin"

    remote = f"static/{filename}"
    
    temp_sa_path = None
    try:
        # Handle service account
        service_account_info = None
        if isinstance(api_key, dict):
            service_account_info = api_key
        else:
            try:
                service_account_info = json.loads(api_key)
            except Exception:
                if os.path.exists(str(api_key)):
                    with open(api_key, 'r') as f:
                        service_account_info = json.load(f)
                else:
                    return {"status": "error", "message": "Invalid service account key."}

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_sa:
            json.dump(service_account_info, temp_sa)
            temp_sa_path = temp_sa.name

        client = storage.Client.from_service_account_json(temp_sa_path)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(remote)

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=expiration_minutes),
            method="PUT",
        )
        
        if os.path.exists(temp_sa_path):
            os.unlink(temp_sa_path)
            
        public_url = f"https://storage.googleapis.com/{bucket_name}/{remote}"
        gcs_uri = f"gs://{bucket_name}/{remote}"

        return {
            "status": True,
            "data": {
                "upload_url": url,
                "method": "PUT",
                "filename": filename,
                "path": remote,
                "gcs_uri": gcs_uri,
                "public_url": public_url,
                "content_type": content_type
            }
        }

    except Exception as e:
        if temp_sa_path and os.path.exists(temp_sa_path):
            os.unlink(temp_sa_path)
        
        # Log error details for debugging
        import traceback
        traceback_str = traceback.format_exc()
        return {"status": "error", "message": f"Exception generating signed URL: {str(e)}", "details": traceback_str}
