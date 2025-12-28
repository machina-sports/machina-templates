from google import genai

from google.genai import types

from google.oauth2 import service_account

from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_google_vertexai import ChatVertexAI

from io import BytesIO

from PIL import Image

import base64

import datetime

import json

import os

import requests

import tempfile

import time


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

    prompt = params.get("prompt", "Ronaldinho Gaúcho brincando com uma bola de lã")
    model_name = params.get("model_name") or "gemini-2.5-flash-image-preview"
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
    # Date filtering (inclusive).
    # We support:
    # - start_date/end_date as YYYY-MM-DD
    # - startDate/endDate as ISO8601 datetime strings (e.g. 2025-08-15T19:00:00+00:00)
    # - Back-compat: if schema provides `startDate` and `end_date` is not provided,
    #   we treat `startDate` as the anchor/end of the search window.
    start_date = params.get("start_date")  # YYYY-MM-DD
    end_date = params.get("end_date")  # YYYY-MM-DD
    start_date_iso = params.get("startDate")  # ISO8601 datetime
    end_date_iso = params.get("endDate")  # ISO8601 datetime
    days_back = params.get("days_back", 3)  # used when start_date is missing but end is present

    def _parse_date_or_datetime(value, field_name):
        """
        Accepts either:
        - YYYY-MM-DD
        - ISO8601 datetime (e.g. 2025-08-15T19:00:00+00:00)
        Returns a datetime.date or None.
        """
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError(f"{field_name} must be a string (YYYY-MM-DD or ISO8601 datetime)")
        v = value.strip()
        try:
            # Be permissive: if the value begins with YYYY-MM-DD, extract that date portion.
            # This covers many ISO variants (fractions, Z suffix, timezone offsets, etc.).
            if len(v) >= 10 and v[4] == "-" and v[7] == "-":
                return datetime.date.fromisoformat(v[:10])
            if "T" in v:
                return datetime.datetime.fromisoformat(v).date()
            return datetime.date.fromisoformat(v)
        except Exception:
            raise ValueError(
                f"{field_name} must be YYYY-MM-DD or ISO8601 datetime (got: {value})"
            )

    def _parse_days_back(value, field_name="days_back"):
        if value is None or value == "":
            return 3
        if isinstance(value, bool):
            raise ValueError(f"{field_name} must be an integer (got: {value})")
        try:
            n = int(value)
        except Exception:
            raise ValueError(f"{field_name} must be an integer (got: {value})")
        if n < 0:
            raise ValueError(f"{field_name} must be >= 0 (got: {n})")
        return n

    def _apply_date_filter_to_query(query, start_dt, end_dt):
        """
        Adds Google date operators to the query string:
        - start_dt (inclusive) -> after:YYYY-MM-DD
        - end_dt (inclusive) -> before:(end_dt + 1 day) because before: is typically exclusive
        """
        q = (query or "").strip()
        tokens = []
        if start_dt:
            tokens.append(f"after:{start_dt.isoformat()}")
        if end_dt:
            before_dt = end_dt + datetime.timedelta(days=1)
            tokens.append(f"before:{before_dt.isoformat()}")
        if not tokens:
            return q
        # Keep original query first for relevance, then apply date constraints
        return f"{q} {' '.join(tokens)}".strip()

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
        try:
            days_back_n = _parse_days_back(days_back, "days_back")

            # Direct params take precedence
            start_dt = _parse_date_or_datetime(start_date, "start_date")
            end_dt = _parse_date_or_datetime(end_date, "end_date")

            # ISO variants (explicit endDate wins; startDate can be used as start OR as anchor)
            if end_dt is None and end_date_iso:
                end_dt = _parse_date_or_datetime(end_date_iso, "endDate")

            # Back-compat anchor behavior: if end not set, treat startDate as anchor/end of window
            anchor_end_dt = None
            if start_date_iso:
                anchor_end_dt = _parse_date_or_datetime(start_date_iso, "startDate")
                if end_dt is None:
                    end_dt = anchor_end_dt

            # If we have an end date but no start date, derive start_dt = end_dt - days_back
            if end_dt is not None and start_dt is None:
                start_dt = end_dt - datetime.timedelta(days=days_back_n)
        except ValueError as e:
            return {"status": False, "message": str(e)}

        if start_dt and end_dt and start_dt > end_dt:
            return {
                "status": False,
                "message": "start_date must be earlier than or equal to end_date",
            }

        final_query = _apply_date_filter_to_query(search_query, start_dt, end_dt)

        llm = ChatVertexAI(
            model=model_name,
            credentials=credentials,
            location=location,
            project=project_id,
        )

        llm = llm.bind_tools([{"google_search": {}}])

        response = llm.invoke(final_query)

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
                "query": search_query,          # original user query
                "final_query": final_query,     # query actually used (includes after:/before:)
                "start_date": start_date,       # echo input (YYYY-MM-DD)
                "end_date": end_date,           # echo input (YYYY-MM-DD)
                "startDate": start_date_iso,    # echo input (ISO8601)
                "endDate": end_date_iso,        # echo input (ISO8601)
                "days_back": days_back,         # echo input
                "derived_start_date": start_dt.isoformat() if start_dt else None,
                "derived_end_date": end_dt.isoformat() if end_dt else None,
                "answer": response.content,
                "search_results": search_results,  # Easy access to links and titles
                "search_queries": web_queries,     # Queries that were executed
                # "grounding_metadata": grounding_metadata,  # Full metadata for advanced use
            },
            "message": "Search completed successfully",
        }

    except Exception as e:
        return {"status": False, "message": f"Exception during search: {e}"}


def invoke_video(request_data):
    """
    Generate videos using Google's Veo model.
    
    Supports both AI Studio (default) and Vertex AI providers.
    
    Parameters:
    - provider: "ai_studio" (default) or "vertex_ai"
    - model_name: Model name (e.g., "veo-3.1-fast-generate-001")
    
    AI Studio Parameters:
    - api_key: Required - Get from https://aistudio.google.com/apikey
    
    Vertex AI Parameters:
    - project_id: Required - Your GCP Project ID
    - location: Optional (default: "us-central1")
    - credential: Optional - Service account JSON (string or dict)
    """
    
    params = request_data.get("params")
    headers = request_data.get("headers")
    
    # Get provider (default to ai_studio for backward compatibility)
    provider = params.get("provider", "ai_studio").lower()
    
    # Get parameters
    prompt = params.get("prompt")
    model_name = params.get("model_name", "veo-3.1-fast-generate-001")
    poll_interval = params.get("poll_interval", 10)  # seconds
    output_path = params.get("output_path")  # Optional custom output path
    
    if not prompt:
        return {"status": False, "message": "Prompt is required for video generation."}
    
    try:
        # Initialize client based on provider
        if provider == "vertex_ai":
            project_id = headers.get("project_id")
            location = params.get("location", "us-central1")
            credential = headers.get("credential")
            
            if not project_id:
                return {"status": False, "message": "project_id is required for Vertex AI."}
            
            # Handle credentials
            credentials = None
            if credential:
                if isinstance(credential, str):
                    try:
                        credential = json.loads(credential)
                    except json.JSONDecodeError:
                        return {"status": False, "message": "credential must be valid JSON"}
                
                credentials = service_account.Credentials.from_service_account_info(credential)
            
            # Initialize Vertex AI client
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=credentials,
            )
            print(f"🔐 Using Vertex AI authentication (project: {project_id}, location: {location})")
        else:
            # AI Studio (default)
            api_key = headers.get("api_key")
            
            if not api_key:
                return {"status": False, "message": "API key is required for AI Studio."}
            
            client = genai.Client(api_key=api_key)
            print("🔐 Using AI Studio API key authentication")
        
        print(f"🎬 Starting video generation with model: {model_name}")
        print(f"📝 Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"📝 Prompt: {prompt}")
        
        # Start video generation
        operation = client.models.generate_videos(
            model=model_name,
            prompt=prompt,
        )
        
        print(f"⏳ Video generation operation started. Polling every {poll_interval} seconds...")
        
        # Poll the operation status until the video is ready
        while not operation.done:
            print("⏳ Waiting for video generation to complete...")
            time.sleep(poll_interval)
            operation = client.operations.get(operation)
        
        print("✅ Video generation completed!")
        
        # Check if operation was successful
        if not hasattr(operation, "response") or not operation.response:
            return {
                "status": False,
                "message": "Video generation completed but no response received.",
            }
        
        if not hasattr(operation.response, "generated_videos") or not operation.response.generated_videos:
            return {
                "status": False,
                "message": "Video generation completed but no videos were generated.",
            }
        
        # Get the first generated video
        generated_video = operation.response.generated_videos[0]
        
        if not hasattr(generated_video, "video"):
            return {
                "status": False,
                "message": "Generated video object does not contain video file reference.",
            }
        
        # Determine output path
        if not output_path:
            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=".mp4"
            )
            output_path = temp_file.name
            temp_file.close()
        
        # Download and save the generated video
        print(f"💾 Downloading video to: {output_path}")
        client.files.download(file=generated_video.video)
        generated_video.video.save(output_path)
        
        # Extract filename from output_path
        filename = os.path.basename(output_path)
        
        print(f"✅ Video saved successfully: {filename}")
        
        return {
            "status": True,
            "data": {
                "video_path": output_path,
                "filename": filename,
                "video_format": "MP4",
                "prompt": prompt,
                "model": model_name,
            },
            "message": "Video generated successfully.",
        }
        
    except Exception as e:
        return {"status": False, "message": f"Exception when generating video: {e}"}
