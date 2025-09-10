from google.cloud import storage

import json

import tempfile

# BUCKET = "machina-templates-bucket-default"

def invoke_upload(request_data):
    
    params = request_data.get("params")
    
    headers = request_data.get("headers")
    
    api_key = headers.get("api_key")
    
    bucket_name = headers.get("bucket_name")

    image_path = params.get("image_path")
    if not image_path:
        return {"status": "error", "message": "image_path is required."}
    
    remote = "static/test-screenshot.png"

    if not api_key:
        return {"status": "error", "message": "API key is required."}
    
    try:
        service_account_info = json.loads(api_key)
    except json.JSONDecodeError:
        return {"status": "error", "message": "Invalid service account JSON in api_key"}

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            json.dump(service_account_info, temp_file)
            temp_file_path = temp_file.name

        client = storage.Client.from_service_account_json(temp_file_path)
        
        import os
        os.unlink(temp_file_path)

        bucket = client.bucket(bucket_name)

        blob = bucket.blob(remote)

        with open(image_path, "rb") as f:
            blob.upload_from_file(f, content_type="image/png")

        blob.reload()

    except Exception as e:
        return {"status": "error", "message": f"Exception when uploading file: {e}"}

    public_url = f"https://storage.googleapis.com/{bucket_name}/{remote}"
    
    return {
        "status": True,
        "data": {
            "message": "File uploaded.",
            "url": public_url,
            "path": remote
        }
    }
