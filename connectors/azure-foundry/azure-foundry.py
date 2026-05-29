from langchain_openai import ChatAzureOpenAI, AzureOpenAIEmbeddings


def invoke_prompt(params):
    """
    Load ChatAzureOpenAI client.

    Parameters:
    - api_key (str): Azure OpenAI API key
    - azure_endpoint (str): Azure OpenAI base endpoint (e.g. https://<your-subdomain>.openai.azure.com/)
    - azure_deployment (str): Deployment name of the model on Azure OpenAI
    - api_version (str): Azure OpenAI API version (defaults to '2024-08-01-preview')
    - temperature (float): Sampling temperature (defaults to 0.7)
    """
    # Flexibly retrieve API keys and endpoints from headers, params, or root levels
    headers = params.get("headers", {}) or {}
    inner_params = params.get("params", {}) or {}

    api_key = (
        params.get("api_key")
        or headers.get("api_key")
        or inner_params.get("api_key")
        or params.get("credential")
    )
    azure_endpoint = (
        params.get("azure_endpoint")
        or params.get("endpoint")
        or headers.get("endpoint")
        or headers.get("azure_endpoint")
        or inner_params.get("endpoint")
        or inner_params.get("azure_endpoint")
    )
    azure_deployment = (
        params.get("azure_deployment")
        or params.get("deployment_name")
        or params.get("model_name")
        or params.get("model")
        or inner_params.get("azure_deployment")
        or inner_params.get("deployment_name")
        or headers.get("azure_deployment")
    )
    api_version = (
        params.get("api_version")
        or inner_params.get("api_version")
        or "2024-08-01-preview"
    )
    temperature = float(
        params.get("temperature") or inner_params.get("temperature") or 0.7
    )

    if not api_key:
        return {"status": "error", "message": "Azure OpenAI API key is required."}
    if not azure_endpoint:
        return {
            "status": "error",
            "message": "Azure OpenAI Endpoint (azure_endpoint) is required.",
        }
    if not azure_deployment:
        return {
            "status": "error",
            "message": "Azure Deployment Name (azure_deployment) is required.",
        }

    try:
        llm = ChatAzureOpenAI(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            azure_deployment=azure_deployment,
            api_version=api_version,
            temperature=temperature,
        )
        return {
            "status": True,
            "data": llm,
            "message": f"Azure OpenAI model '{azure_deployment}' loaded successfully.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception when creating Azure OpenAI model: {e}",
        }


def invoke_embedding(params):
    """
    Load AzureOpenAIEmbeddings client.

    Parameters:
    - api_key (str): Azure OpenAI API key
    - azure_endpoint (str): Azure OpenAI base endpoint
    - azure_deployment (str): Deployment name of the embedding model
    - api_version (str): Azure OpenAI API version (defaults to '2023-05-15')
    """
    headers = params.get("headers", {}) or {}
    inner_params = params.get("params", {}) or {}

    api_key = (
        params.get("api_key")
        or headers.get("api_key")
        or inner_params.get("api_key")
        or params.get("credential")
    )
    azure_endpoint = (
        params.get("azure_endpoint")
        or params.get("endpoint")
        or headers.get("endpoint")
        or headers.get("azure_endpoint")
        or inner_params.get("endpoint")
        or inner_params.get("azure_endpoint")
    )
    azure_deployment = (
        params.get("azure_deployment")
        or params.get("deployment_name")
        or params.get("model_name")
        or params.get("model")
        or inner_params.get("azure_deployment")
        or inner_params.get("deployment_name")
        or headers.get("azure_deployment")
    )
    api_version = (
        params.get("api_version")
        or inner_params.get("api_version")
        or "2023-05-15"
    )

    if not api_key:
        return {"status": "error", "message": "Azure OpenAI API key is required."}
    if not azure_endpoint:
        return {
            "status": "error",
            "message": "Azure OpenAI Endpoint (azure_endpoint) is required.",
        }
    if not azure_deployment:
        return {
            "status": "error",
            "message": "Azure Deployment Name (azure_deployment) is required.",
        }

    try:
        embeddings = AzureOpenAIEmbeddings(
            azure_endpoint=azure_endpoint,
            api_key=api_key,
            azure_deployment=azure_deployment,
            api_version=api_version,
        )
        return {
            "status": True,
            "data": embeddings,
            "message": f"Azure OpenAI embeddings '{azure_deployment}' loaded successfully.",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Exception when creating Azure OpenAI embeddings: {e}",
        }
