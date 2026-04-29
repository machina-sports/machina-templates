from langchain_groq import ChatGroq
from groq import Groq


def list_models(params):
    """List available models from Groq API. Useful for testing credentials."""
    api_key = params.get("headers", {}).get("api_key") or params.get("params", {}).get("api_key") or params.get("api_key", "")

    if not api_key:
        return {"status": False, "message": "API key is required."}

    try:
        client = Groq(api_key=api_key)
        models = client.models.list()
        model_list = [{"id": m.id, "owned_by": m.owned_by} for m in models.data[:10]]
        return {"status": True, "data": {"models": model_list, "total_count": len(models.data)}, "message": "Models retrieved successfully."}
    except Exception as e:
        return {"status": False, "message": f"Error listing models: {str(e)}"}


def invoke_embedding(params):

    api_key = params.get("api_key", "")

    model_name = params.get("model_name", "llama2-70b-4096")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    try:
        llm = ChatGroq(
            api_key=api_key,
            model_name=model_name
        )
    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def invoke_prompt(params):

    api_key = params.get("api_key")

    model_name = params.get("model_name", "llama2-70b-4096")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    try:
        llm = ChatGroq(
            api_key=api_key,
            model_name=model_name
        )
    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."} 
