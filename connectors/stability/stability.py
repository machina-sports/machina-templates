import requests


def generate_image(request_data):

    headers = request_data.get("headers")

    params = request_data.get("params")

    api_key = headers.get("api_key", "")

    image_id = params.get("image_id", "")

    configuration = params.get("configuration", "")

    api_host = "https://api.stability.ai"

    if api_key is None:
        return {"status": "error", "message": "API key is required."}

    response = requests.post(
        f"{api_host}/v2beta/stable-image/generate/core",
        headers={
            "Accept": "image/*",
            "Authorization": f"Bearer {api_key}"
        },
        files=configuration
    )

    if response.status_code != 200:

        return {"status": False, "message": "Non-200 response: " + str(response.text)}

    if response.status_code == 200:

        full_filepath = f"work/images/{image_id}.webp"

        with open(full_filepath, 'wb') as f:

            f.write(response.content)

        final_filename = f"{image_id}.webp"

    result = {
        "final_filename": final_filename,
        "full_filepath": full_filepath
    }

    return {"status": True, "data": result, "message": "Image generated."}
