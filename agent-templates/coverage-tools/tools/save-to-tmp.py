import base64
import tempfile

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
