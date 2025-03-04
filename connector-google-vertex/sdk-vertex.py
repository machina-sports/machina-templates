from google.oauth2 import service_account

from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings

import json


def invoke_embedding(params):
    """
    Create embeddings using Google Vertex AI via LangChain.

    :param params: Dictionary containing project, location, and model parameters
    :return: Embedding model instance or error message
    """
    credentials_object = params.get("credentials", "")

    credentials = json.loads(credentials_object)

    project = params.get("project", "prismatic-smoke-433121-j9")

    location = params.get("location", "us-central1")

    model_name = params.get("model_name", "textembedding-gecko")

    try:

        # Parse the API key string as JSON and create credentials
        credentials_parsed = service_account.Credentials.from_service_account_info(credentials)

        embeddings = VertexAIEmbeddings(
            project=project,
            location=location,
            model_name=model_name,
            credentials=credentials_parsed,
        )
        return {"status": True, "data": embeddings, "message": "Model loaded."}

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}


def invoke_prompt(params):
    """
    Create a text generation model using Google Vertex AI via LangChain.

    :param params: Dictionary containing project, location, and model parameters
    :return: Generation model instance or error message
    """

    credentials_object = params.get("credentials", "")

    credentials = json.loads(credentials_object)

    project = params.get("project", "prismatic-smoke-433121-j9")

    location = params.get("location", "us-central1")

    model_name = params.get("model_name", "gemini-pro")

    try:

        credentials_parsed = service_account.Credentials.from_service_account_info(credentials)

        llm = ChatVertexAI(
            project=project,
            location=location,
            model_name=model_name,
            credentials=credentials_parsed,
        )
        return {"status": True, "data": llm, "message": "Model loaded."}

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}


def invoke_vision(params):
    """
    Create a multimodal vision model using Google Vertex AI via LangChain.

    :param params: Dictionary containing project, location, and model parameters
    :return: Vision model instance or error message
    """

    credentials_object = params.get("credentials", "")

    credentials = json.loads(credentials_object)

    project = params.get("project", "prismatic-smoke-433121-j9")

    location = params.get("location", "us-central1")

    model_name = params.get("gemini-pro-vision")

    try:
        vision_model = ChatVertexAI(
            project=project,
            location=location,
            model_name=model_name,
            credentials=credentials,
        )
        return {"status": True, "data": vision_model, "message": "Model loaded."}

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}
