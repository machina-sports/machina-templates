"""
Vertex AI Text Embedding Connector
Uses text-embedding-004 model for generating embeddings
"""

from langchain_google_vertexai import VertexAIEmbeddings
from google.oauth2 import service_account
import json


def invoke_embedding(request_data):
    """
    Create VertexAIEmbeddings instance for text-embedding-004

    Args:
        request_data: Dictionary containing:
            - params: Dictionary with model parameters
                - model_name: Model to use (default: "text-embedding-004")
                - location: GCP location (optional, default: "us-central1")
            - headers: Dictionary with credentials (from context-variables)
                - credential: Service account JSON credentials (string or dict)
                - project: GCP project ID
                         If not provided, uses Application Default Credentials (ADC)

    Returns:
        Dictionary with status and LangChain embeddings instance
    """
    # Extract params and headers (similar to google-genai)
    params = request_data.get("params", {}) or request_data
    headers = request_data.get("headers", {})

    # DEBUG: Log what we're receiving
    print(f"[DEBUG vertex-embedding] request_data keys: {request_data.keys()}")
    print(f"[DEBUG vertex-embedding] headers: {headers}")
    print(f"[DEBUG vertex-embedding] params keys: {params.keys() if isinstance(params, dict) else 'not dict'}")

    model_name = params.get("model_name", "text-embedding-004")
    location = params.get("location", "us-central1")

    # Get credentials from headers (context-variables) or params
    credential = headers.get("credential") or params.get("credential")
    project = headers.get("project_id") or headers.get("project") or params.get("project_id") or params.get("project")

    # DEBUG: Log credential details
    print(f"[DEBUG vertex-embedding] credential type: {type(credential)}")
    print(f"[DEBUG vertex-embedding] credential value (first 100 chars): {str(credential)[:100] if credential else None}")
    print(f"[DEBUG vertex-embedding] project: {project}")

    try:
        # Handle credentials (similar to google-genai connector)
        credentials = None
        credentials_source = "Application Default Credentials (ADC)"

        if credential:
            # Parse credential if it's a JSON string
            if isinstance(credential, str):
                print(f"[DEBUG vertex-embedding] credential is string, attempting JSON parse...")
                try:
                    credential = json.loads(credential)
                    print(f"[DEBUG vertex-embedding] JSON parse successful!")
                except json.JSONDecodeError as e:
                    print(f"[DEBUG vertex-embedding] JSON parse failed: {e}")
                    return {
                        "status": False,
                        "data": {},
                        "error": {"code": 400, "message": f"credential must be valid JSON: {str(e)}"}
                    }

            # Create credentials from service account info with required scopes
            credentials = service_account.Credentials.from_service_account_info(
                credential,
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            credentials_source = "provided service account credentials"
            print(f"[DEBUG vertex-embedding] Credentials object created: {type(credentials)}")

        # Create VertexAI embeddings instance
        kwargs = {"model_name": model_name}

        if project:
            kwargs["project"] = project
        if location:
            kwargs["location"] = location
        if credentials:
            kwargs["credentials"] = credentials

        print(f"[DEBUG vertex-embedding] VertexAIEmbeddings kwargs: {list(kwargs.keys())}")
        print(f"[DEBUG vertex-embedding] credentials in kwargs: {credentials is not None}")
        print(f"[DEBUG vertex-embedding] project in kwargs: {kwargs.get('project')}")

        llm = VertexAIEmbeddings(**kwargs)

        print(f"[DEBUG vertex-embedding] VertexAIEmbeddings instance created successfully!")

        return {
            "status": True,
            "data": llm,
            "message": f"VertexAI embeddings loaded: {model_name} (Auth: {credentials_source})"
        }

    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": f"Error creating embeddings: {str(e)}"}
        }


def embed_query(request_data):
    """
    Generate embedding for a single query text

    Args:
        request_data: Dictionary containing:
            - params: Dictionary with:
                - value: Text to embed (required)
                - model_name: Model to use
                - location: GCP location
            - headers: Dictionary with credentials
                - credential: Service account JSON
                - project: GCP project ID

    Returns:
        Dictionary with embedding vector
    """
    params = request_data.get("params", {}) or request_data
    text = params.get("value")

    if not text:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "Text value is required"}
        }

    # Get embeddings instance (pass full request_data)
    embed_result = invoke_embedding(request_data)

    if not embed_result.get("status"):
        return embed_result

    llm = embed_result.get("data")

    try:
        # Generate embedding
        embedding = llm.embed_query(text)

        return {
            "status": True,
            "data": embedding,
            "message": f"Embedding generated ({len(embedding)} dimensions)"
        }

    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": f"Error embedding text: {str(e)}"}
        }


def embed_documents(request_data):
    """
    Generate embeddings for multiple documents

    Args:
        request_data: Dictionary containing:
            - params: Dictionary with:
                - values: List of texts to embed (required)
                - model_name: Model to use
                - location: GCP location
            - headers: Dictionary with credentials
                - credential: Service account JSON
                - project: GCP project ID

    Returns:
        Dictionary with list of embedding vectors
    """
    params = request_data.get("params", {}) or request_data
    texts = params.get("values", [])

    if not texts or not isinstance(texts, list):
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "List of text values is required"}
        }

    # Get embeddings instance (pass full request_data)
    embed_result = invoke_embedding(request_data)

    if not embed_result.get("status"):
        return embed_result

    llm = embed_result.get("data")

    try:
        # Generate embeddings
        embeddings = llm.embed_documents(texts)

        return {
            "status": True,
            "data": embeddings,
            "message": f"Embeddings generated for {len(texts)} documents"
        }

    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": f"Error embedding documents: {str(e)}"}
        }
