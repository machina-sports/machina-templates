"""Vertex AI text embedding connector with sanitized credential handling."""

import json

from google.oauth2 import service_account
from langchain_google_vertexai import VertexAIEmbeddings


def _sources(request_data):
    request_data = request_data or {}
    params = request_data.get("params") or request_data
    headers = request_data.get("headers") or {}
    return params, headers


def _failure(message, code=400):
    return {"status": False, "data": None, "message": message, "error": {"code": code, "message": message}}


def invoke_embedding(request_data):
    params, headers = _sources(request_data)
    model_name = params.get("model_name") or params.get("model") or "text-embedding-004"
    location = params.get("location") or "global"
    credential = headers.get("credential") or params.get("credential")
    project = headers.get("project_id") or headers.get("project") or params.get("project_id") or params.get("project")

    credentials = None
    if credential:
        try:
            info = json.loads(credential) if isinstance(credential, str) else credential
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        except Exception:
            return _failure("The configured Vertex credential is invalid.")

    kwargs = {"model_name": model_name, "location": location}
    if project:
        kwargs["project"] = project
    if credentials:
        kwargs["credentials"] = credentials
    try:
        model = VertexAIEmbeddings(**kwargs)
    except Exception:
        return _failure("Unable to create the configured Vertex embedding model.", 500)
    return {"status": True, "data": model, "message": f"VertexAI embeddings loaded: {model_name}"}


def embed_query(request_data):
    params, _ = _sources(request_data)
    text = params.get("value") or params.get("input") or params.get("text")
    if not isinstance(text, str) or not text:
        return _failure("Text value is required.")
    result = invoke_embedding(request_data)
    if not result.get("status"):
        return result
    try:
        embedding = result["data"].embed_query(text)
    except Exception:
        return _failure("The configured Vertex model could not embed the query.", 500)
    return {"status": True, "data": embedding, "message": f"Embedding generated ({len(embedding)} dimensions)"}


def embed_documents(request_data):
    params, _ = _sources(request_data)
    texts = params.get("values") or params.get("texts") or params.get("input")
    if not isinstance(texts, list) or not texts:
        return _failure("A non-empty list of text values is required.")
    try:
        if not all(isinstance(item, str) for item in texts):
            return _failure("Every embedding input must be text.")
        result = invoke_embedding(request_data)
        if not result.get("status"):
            return result
        embeddings = result["data"].embed_documents(texts)
    except Exception:
        return _failure("The configured Vertex model could not embed the documents.", 500)
    return {"status": True, "data": embeddings, "message": f"Embeddings generated for {len(texts)} documents"}
