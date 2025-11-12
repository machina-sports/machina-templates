import base64
import mimetypes
import tempfile
import urllib.request
import urllib.error
import urllib.parse
import os

def invoke_download(request_data):
    params = request_data.get("params", {})
    
    # Get the image URL
    image_url = params.get("image_url")
    if not image_url:
        return {"status": "error", "message": "image_url is required."}
    
    # Check if it's a valid URL
    if not image_url.startswith(('http://', 'https://')):
        return {"status": "error", "message": "Invalid URL format. Must start with http:// or https://"}
    
    # Get filename from URL or use provided filename
    filename = params.get("filename")
    if not filename:
        parsed_url = urllib.parse.urlparse(image_url)
        filename = os.path.basename(parsed_url.path)
        if not filename:
            filename = "downloaded_image"
    
    try:
        # Create a temporary file to store the downloaded image
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            # Download the image
            req = urllib.request.Request(image_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                temp_file.write(response.read())
            
            temp_file_path = temp_file.name
        
        # Get the content type
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "image/png"
        
        # Get the file size
        file_size = os.path.getsize(temp_file_path)
        
        return {
            "status": True,
            "data": {
                "message": "File downloaded successfully.",
                "filename": filename,
                "content_type": content_type,
                "size": file_size,
                "temp_path": temp_file_path
            }
        }
        
    except urllib.error.URLError as e:
        return {"status": "error", "message": f"Failed to download file from URL: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Error downloading file: {e}"}


def invoke_save_to_tmp(request_data):

    headers = request_data.get("headers")
    params = request_data.get("params")

    image_base64 = params.get("image_base64")

    if not image_base64:
        return {
            "status": False,
            "data": {},
            "message": "Image base64 is required.",
        }

    try:
        # Handle data URI format (e.g., "data:image/png;base64,...")
        if isinstance(image_base64, str) and image_base64.startswith("data:"):
            # Extract just the base64 part after the comma
            image_base64 = image_base64.split(",", 1)[1] if "," in image_base64 else image_base64
        
        # Decode base64 string to bytes
        image_data = base64.b64decode(image_base64)
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_file.write(image_data)
            temp_path = temp_file.name

        return {
            "status": True,
            "data": {"image_path": temp_path},
            "message": "Image saved to tmp successfully.",
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {},
            "message": f"Error saving image: {str(e)}",
        }
