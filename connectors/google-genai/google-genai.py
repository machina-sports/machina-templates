from google import genai

from google.genai import types

from google.oauth2 import service_account

from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_google_vertexai import ChatVertexAI

from io import BytesIO

from PIL import Image

import base64

import json

import os

import requests

import tempfile


def invoke_prompt(params):
    """
    Standard prompt invocation using langchain.

    Supports both AI Studio (default) and Vertex AI providers.

    Parameters:
    - provider: "ai_studio" (default) or "vertex_ai"
    - model_name: Model name (e.g., "gemini-2.5-flash", "gemini-pro")

    AI Studio Parameters:
    - api_key: Required - Get from https://aistudio.google.com/apikey

    Vertex AI Parameters:
    - project_id: Required - Your GCP Project ID (find with: gcloud config get-value project)
    - location: Optional (default: "us-central1") - Use "global" for Global Endpoint
    - credential: Optional - Service account JSON (string or dict). If not provided, uses ADC.

    IMPORTANT: Vertex AI does NOT support API keys - use OAuth2 credentials only!

    Vertex AI Credentials (in order of precedence):
    1. credential parameter (service account JSON)
    2. GOOGLE_APPLICATION_CREDENTIALS env var (auto-detected)
    3. ADC from `gcloud auth application-default login` (auto-detected)
    4. Attached service account if running on GCP (auto-detected)
    """
    provider = params.get("provider", "ai_studio").lower()

    model_name = params.get("model_name")

    if not model_name:
        return {"status": False, "message": "Model name is required."}

    # AI Studio Implementation (default)
    if provider == "ai_studio":
        api_key = params.get("api_key")

        if not api_key:
            return {"status": False, "message": "API key is required for AI Studio."}

        try:
            llm = ChatGoogleGenerativeAI(model=model_name, api_key=api_key)
            return {
                "status": True,
                "data": llm,
                "message": f"Model loaded via AI Studio: {model_name}",
            }
        except Exception as e:
            return {
                "status": False,
                "message": f"Exception when creating AI Studio model: {e}",
            }

    # Vertex AI Implementation
    elif provider == "vertex_ai":
        project_id = params.get("project_id")
        location = params.get(
            "location", "us-central1"
        )  # Default to us-central1, supports "global"
        credential = params.get("credential")  # JSON string or dict

        if not project_id:
            return {"status": False, "message": "project_id is required for Vertex AI."}

        try:
            # Handle credentials (Vertex AI does NOT support API keys!)
            credentials = None
            credentials_source = "Application Default Credentials (ADC)"

            if credential:
                # Parse credential if it's a JSON string
                if isinstance(credential, str):
                    try:
                        credential = json.loads(credential)
                    except json.JSONDecodeError:
                        return {
                            "status": False,
                            "message": "credential must be valid JSON",
                        }

                # Create credentials from service account info
                credentials = service_account.Credentials.from_service_account_info(
                    credential
                )
                credentials_source = "provided service account credentials"

            llm = ChatVertexAI(
                model_name=model_name,
                project=project_id,
                location=location,
                credentials=credentials,
            )

            endpoint_info = (
                "Global Endpoint"
                if location == "global"
                else f"Regional Endpoint ({location})"
            )

            return {
                "status": True,
                "data": llm,
                "message": f"Model loaded via Vertex AI: {model_name} using {endpoint_info} (Auth: {credentials_source})",
            }
        except Exception as e:
            return {
                "status": False,
                "message": f"Exception when creating Vertex AI model: {e}",
            }

    else:
        return {
            "status": False,
            "message": f"Invalid provider: {provider}. Must be 'ai_studio' or 'vertex_ai'.",
        }


def invoke_image(request_data):
    """Generate images using Google's Gemini model with optional input image"""

    params = request_data.get("params")
    headers = request_data.get("headers")
    api_key = headers.get("api_key")

    if not api_key:
        return {"status": False, "message": "API key is required."}

    # Get parameters
    image_paths = params.get("image_paths", [])  # Accept array of image paths
    image_path = params.get("image_path")  # Keep backward compatibility

    # Collect individual image_path_N fields and add to array
    i = 1
    while True:
        field_name = f"image_path_{i}"
        field_value = params.get(field_name)
        if field_value:
            image_paths.append(field_value)
            print(f"📎 Adicionado {field_name}: {field_value}")
            i += 1
        else:
            break

    # If single image_path is provided, convert to array
    if image_path and image_path not in image_paths:
        image_paths.append(image_path)

    prompt = params.get("prompt", "Um gato fofo brincando com uma bola de lã")
    model_name = params.get("model-name", "gemini-2.5-flash-image-preview")
    aspect_ratio = params.get("aspect_ratio")  # e.g., "16:9", "1:1", "9:16"

    try:
        client = genai.Client(api_key=api_key)

        # Prepare image parts if image_paths are provided
        image_parts = []
        if image_paths:
            print(f"🖼️ Processando {len(image_paths)} imagens")
            for i, img_path in enumerate(image_paths):
                print(f"📷 Processando imagem {i+1}/{len(image_paths)}: {img_path}")

                image_data = None
                if img_path.startswith(("http://", "https://")):
                    # Download image from URL
                    print(f"🌐 Baixando imagem de URL: {img_path}")
                    try:
                        response = requests.get(img_path)
                        response.raise_for_status()
                        image_data = response.content
                        print(f"📊 Tamanho da imagem baixada: {len(image_data)} bytes")
                    except Exception as e:
                        print(f"❌ Erro ao baixar imagem {i+1}: {e}")
                        continue
                elif os.path.exists(img_path):
                    # Read local file
                    print(f"📁 Lendo imagem local: {img_path}")
                    try:
                        with open(img_path, "rb") as image_file:
                            image_data = image_file.read()
                        print(f"📊 Tamanho da imagem: {len(image_data)} bytes")
                    except Exception as e:
                        print(f"❌ Erro ao ler imagem {i+1}: {e}")
                        continue
                else:
                    print(f"❌ Imagem não encontrada: {img_path}")
                    continue

                if image_data:
                    # Detect MIME type based on file extension or content
                    mime_type = "image/jpeg"  # default
                    if img_path.lower().endswith(".png"):
                        mime_type = "image/png"
                    elif img_path.lower().endswith(".gif"):
                        mime_type = "image/gif"
                    elif img_path.lower().endswith(".webp"):
                        mime_type = "image/webp"

                    image_part = types.Part(
                        inline_data=types.Blob(data=image_data, mime_type=mime_type)
                    )
                    image_parts.append(image_part)
                    print(f"✅ Imagem {i+1} preparada com sucesso ({mime_type})")

            print(f"✅ Total de {len(image_parts)} imagens preparadas com sucesso")

        # Decide contents based on available inputs
        if image_parts or prompt is not None:
            parts = []

            # Add all image parts
            if image_parts:
                parts.extend(image_parts)
                print(f"🖼️ Adicionando {len(image_parts)} imagens aos parts")

            # Add text prompt
            if prompt is not None:
                parts.append(types.Part(text=prompt))
                print("📝 Adicionando prompt aos parts")

            contents = [types.Content(role="user", parts=parts)]
            print(f"📦 Contents preparado com {len(parts)} parts")
        else:
            # Fallback default when nothing provided
            contents = "Um gato fofo brincando com uma bola de lã"
            print("⚠️ Usando prompt padrão")

        print(f"Gerando imagem com prompt: {prompt}")
        if image_parts:
            print(f"✅ Usando {len(image_parts)} imagens de entrada junto com o prompt")
        if aspect_ratio:
            print(f"📐 Aspect ratio configurado: {aspect_ratio}")

        # Configure image generation with aspect ratio if provided
        config = None
        if aspect_ratio:
            config = types.GenerateContentConfig(
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                )
            )

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )

        # Debug: Log the response structure
        print(f"📋 Response object type: {type(response)}")
        print(f"📋 Response has candidates: {hasattr(response, 'candidates')}")
        if hasattr(response, "candidates"):
            print(f"📋 Number of candidates: {len(response.candidates) if response.candidates else 0}")
        
        # Check for prompt feedback (safety filters, etc.)
        if hasattr(response, "prompt_feedback"):
            print(f"⚠️ Prompt feedback: {response.prompt_feedback}")
            if hasattr(response.prompt_feedback, "block_reason"):
                return {
                    "status": False,
                    "message": f"Request blocked: {response.prompt_feedback.block_reason}",
                    "details": str(response.prompt_feedback),
                }

        if hasattr(response, "candidates") and response.candidates:
            for idx, candidate in enumerate(response.candidates):
                print(f"📋 Candidate {idx}: has content = {hasattr(candidate, 'content')}")
                
                # Check for finish reason
                if hasattr(candidate, "finish_reason"):
                    print(f"📋 Candidate {idx} finish_reason: {candidate.finish_reason}")
                
                # Check for safety ratings
                if hasattr(candidate, "safety_ratings"):
                    print(f"📋 Candidate {idx} safety_ratings: {candidate.safety_ratings}")
                
                if hasattr(candidate, "content") and candidate.content:
                    print(f"📋 Candidate {idx} has {len(candidate.content.parts)} parts")
                    
                    for part_idx, part in enumerate(candidate.content.parts):
                        print(f"📋 Part {part_idx}: has inline_data = {hasattr(part, 'inline_data')}")
                        if hasattr(part, "text"):
                            print(f"📋 Part {part_idx} has text: {part.text[:200] if part.text else 'None'}")
                        
                        if hasattr(part, "inline_data") and part.inline_data:
                            image_data = part.inline_data.data
                            image = Image.open(BytesIO(image_data))
                            temp_file = tempfile.NamedTemporaryFile(
                                delete=False, suffix=".jpg"
                            )
                            temp_path = temp_file.name
                            temp_file.close()
                            image.save(temp_path, format="JPEG")

                            # Extract filename from temp_path
                            filename = os.path.basename(temp_path)

                            return {
                                "status": True,
                                "data": {
                                    "image_path": temp_path,
                                    "filename": filename,
                                    "image_format": "JPEG",
                                    "prompt": prompt,
                                    "model": model_name,
                                    "input_images_count": len(image_parts),
                                    "input_image_paths": (
                                        image_paths if image_paths else []
                                    ),
                                },
                                "message": f"Image generated successfully using {len(image_parts)} input images.",
                            }
                else:
                    print(f"❌ Candidate {idx} has no content")
            
            return {
                "status": False,
                "message": "No image was generated - candidates exist but contain no image data",
                "debug_info": f"Response had {len(response.candidates)} candidates but none contained inline_data",
            }
        else:
            return {
                "status": False,
                "message": "Error generating image - no candidates in response",
                "debug_info": str(response) if response else "Response is None",
            }

    except Exception as e:
        return {"status": False, "message": f"Exception when generating image: {e}"}


def invoke_search(request_data):
    """Search the web using Google Gemini with Google Search grounding"""

    params = request_data.get("params")

    headers = request_data.get("headers")

    credential = headers.get("credential")

    project_id = headers.get("project_id")

    location = params.get("location", "global")

    model_name = params.get("model_name")

    search_query = params.get("search_query")

    credentials = None
    if credential:
        if isinstance(credential, str):
            try:
                credential = json.loads(credential)
            except json.JSONDecodeError:
                return {
                    "status": False,
                    "message": "credential must be valid JSON string",
                }
        credentials = service_account.Credentials.from_service_account_info(credential)

    if not project_id:
        return {"status": False, "message": "project_id is required."}

    if not search_query:
        return {"status": False, "message": "search_query is required."}

    try:
        llm = ChatVertexAI(
            model=model_name,
            credentials=credentials,
            location=location,
            project=project_id,
        )

        llm = llm.bind_tools([{"google_search": {}}])

        response = llm.invoke(search_query)

        # Extract grounding metadata
        grounding_metadata = response.response_metadata.get("grounding_metadata", {})
        
        # Extract search results (links and titles)
        grounding_chunks = grounding_metadata.get("grounding_chunks", [])
        search_results = []
        for chunk in grounding_chunks:
            if "web" in chunk:
                search_results.append({
                    "title": chunk["web"].get("title", ""),
                    "url": chunk["web"].get("uri", "")
                })
        
        # Extract search queries used
        web_queries = grounding_metadata.get("web_search_queries", [])

        return {
            "status": True,
            "data": {
                "query": search_query,
                "answer": response.content,
                "search_results": search_results,  # Easy access to links and titles
                "search_queries": web_queries,     # Queries that were executed
                # "grounding_metadata": grounding_metadata,  # Full metadata for advanced use
            },
            "message": "Search completed successfully",
        }

    except Exception as e:
        return {"status": False, "message": f"Exception during search: {e}"}
