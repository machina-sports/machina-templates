from azure.storage.blob import BlobServiceClient


def store_image(request_data):

    headers = request_data.get("headers")

    params = request_data.get("params")

    azure_blob_str = headers.get("api_key", "")

    full_filepath = params.get("full_filepath", "")
    
    final_filename = params.get("final_filename", "")

    if azure_blob_str is None:

        return {"status": False, "message": "Missing Azure Blob connection string."}

    blob_service_client = BlobServiceClient.from_connection_string(azure_blob_str)

    container_name = 'gb-blob-images'

    blob_client = blob_service_client.get_blob_client(container=container_name, blob=final_filename)

    with open(full_filepath, 'rb') as data:

        blob_client.upload_blob(data, overwrite=True)

    return {"status": True, "data": {"data": final_filename}, "message": "Image stored."}


def store_base64_image(request_data):

    headers = request_data.get("headers")

    params = request_data.get("params")

    azure_blob_str = headers.get("api_key", "")

    base64_image = params.get("base64_image", "")

    final_filename = params.get("final_filename", "")
    
    if azure_blob_str is None:

        return {"status": False, "message": "Missing Azure Blob connection string."}

    blob_service_client = BlobServiceClient.from_connection_string(azure_blob_str)

    container_name = 'gb-blob-images'

    blob_client = blob_service_client.get_blob_client(container=container_name, blob=final_filename)

    blob_client.upload_blob(base64_image, overwrite=True)

    return {"status": True, "data": {"data": final_filename}, "message": "Image stored."}
