from google import genai

from google.genai import types

from google.oauth2 import service_account

from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_google_vertexai import ChatVertexAI, VertexAIEmbeddings

from io import BytesIO

from PIL import Image

import base64

import datetime

import ipaddress

import json

import os

import requests

import socket

import tempfile

import time

import uuid

import wave
import re
from pathlib import Path
from urllib.parse import urlparse


OMNI_VIDEO_MODEL_PREFIX = "gemini-omni"
OMNI_DEFAULT_VIDEO_MODEL = "gemini-omni-flash-preview"


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _is_omni_video_model(model_name):
    return str(model_name or "").startswith(OMNI_VIDEO_MODEL_PREFIX)


def _guess_mime_type(path_or_url, fallback="image/jpeg"):
    lowered = str(path_or_url or "").split("?")[0].lower()
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".gif"):
        return "image/gif"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".jpg") or lowered.endswith(".jpeg"):
        return "image/jpeg"
    if lowered.endswith(".mp4"):
        return "video/mp4"
    return fallback


def _allowed_media_hosts():
    return {
        host.strip().lower()
        for host in os.getenv("GOOGLE_GENAI_MEDIA_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }


def _validate_remote_media_url(raw_url):
    parsed = urlparse(str(raw_url or ""))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Remote image URL is not allowed")
    if parsed.hostname.lower() not in _allowed_media_hosts():
        raise ValueError("Remote image host is not allowlisted")
    for result in socket.getaddrinfo(parsed.hostname, None):
        address = ipaddress.ip_address(result[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast or address.is_unspecified:
            raise ValueError("Remote image host resolves to a protected address")
    return parsed.geturl()


def _download_remote_image(raw_url, max_bytes=25 * 1024 * 1024):
    url = _validate_remote_media_url(raw_url)
    response = requests.get(url, timeout=(5, 30), stream=True, allow_redirects=False)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        raise ValueError("Remote media is not an image")
    content = bytearray()
    for chunk in response.iter_content(64 * 1024):
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ValueError("Remote image exceeds the configured size limit")
    return bytes(content), content_type


def _safe_local_media_path(raw_path, max_bytes=25 * 1024 * 1024):
    path = Path(str(raw_path)).expanduser().resolve()
    root = Path(os.getenv("MACHINA_WORK_DIR", os.getcwd())).expanduser().resolve()
    if path != root and root not in path.parents:
        raise ValueError("Local image path is outside the approved work directory")
    if not path.is_file() or path.stat().st_size > max_bytes:
        raise ValueError("Local image is missing or exceeds the configured size limit")
    return path


def _load_image_part(image_path=None, image_base64=None, mime_type=None):
    """Return an Interactions API image input part from a URL/path or base64 payload."""
    if image_base64:
        return {
            "type": "image",
            "data": image_base64,
            "mime_type": mime_type or "image/jpeg",
        }

    if not image_path:
        return None

    image_bytes = None
    if str(image_path).startswith(("http://", "https://")):
        image_bytes, detected_mime = _download_remote_image(image_path)
    else:
        local_path = _safe_local_media_path(image_path)
        image_bytes = local_path.read_bytes()
        detected_mime = None

    return {
        "type": "image",
        "data": base64.b64encode(image_bytes).decode("utf-8"),
        "mime_type": mime_type or detected_mime or _guess_mime_type(image_path),
    }


def _extract_omni_video_outputs(interaction):
    """Extract video output objects from Interactions API SDK-like and raw REST shapes."""
    outputs = []
    if not isinstance(interaction, dict):
        return outputs

    for key in ("output_video", "outputVideo"):
        value = interaction.get(key)
        if isinstance(value, dict):
            outputs.append(value)

    for step in interaction.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        for content in step.get("content", []) or []:
            if isinstance(content, dict) and content.get("type") == "video":
                outputs.append(content)

    # Some SDK/REST revisions may put model output under output/content directly.
    for content in interaction.get("content", []) or []:
        if isinstance(content, dict) and content.get("type") == "video":
            outputs.append(content)

    return outputs


def _extract_file_id_from_uri(uri):
    if not uri:
        return None
    match = re.search(r"files/([^/:?]+)", uri)
    return match.group(1) if match else None


def _download_omni_video_uri(uri, api_key, poll_interval=5, max_poll_attempts=120):
    """Poll a Gemini File API URI until active, then download the MP4 bytes."""
    file_id = _extract_file_id_from_uri(uri)
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    if file_id:
        for attempt in range(max_poll_attempts):
            status_url = f"{base_url}/files/{file_id}?key={api_key}"
            status_response = requests.get(status_url, timeout=60)
            if status_response.status_code == 200:
                status_payload = status_response.json()
                state = status_payload.get("state")
                if isinstance(state, dict):
                    state = state.get("name")
                if state in {"ACTIVE", "SUCCEEDED"}:
                    break
                if state == "FAILED":
                    raise RuntimeError(f"Gemini Omni video file failed: {json.dumps(status_payload)[:500]}")
            # If the status endpoint is unavailable but we have a download URI, try the download below.
            elif status_response.status_code in {400, 404} and ":download" in uri:
                break

            if attempt == max_poll_attempts - 1:
                raise TimeoutError(f"Timed out waiting for Gemini Omni video file {file_id} to become ACTIVE")
            time.sleep(float(poll_interval or 5))

    if uri.startswith("http"):
        download_url = uri
        if file_id and ":download" not in download_url:
            download_url = f"{base_url}/files/{file_id}:download?alt=media"
    elif file_id:
        download_url = f"{base_url}/files/{file_id}:download?alt=media"
    else:
        download_url = uri

    if "generativelanguage.googleapis.com" in download_url and "key=" not in download_url:
        separator = "&" if "?" in download_url else "?"
        download_url = f"{download_url}{separator}key={api_key}"

    video_response = requests.get(download_url, timeout=300)
    video_response.raise_for_status()
    return video_response.content


def _save_video_results(video_payloads, output_path=None):
    video_results = []
    for idx, video_bytes in enumerate(video_payloads):
        if not video_bytes:
            continue
        if output_path and len(video_payloads) == 1:
            video_output_path = output_path
        elif output_path:
            base, ext = os.path.splitext(output_path)
            video_output_path = f"{base}_{idx + 1}{ext or '.mp4'}"
        else:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            video_output_path = temp_file.name
            temp_file.close()

        with open(video_output_path, "wb") as f:
            f.write(video_bytes)
        video_results.append({
            "video_path": video_output_path,
            "filename": os.path.basename(video_output_path),
        })
    return video_results


def _invoke_omni_video(request_data, params, headers, prompt, model_name, poll_interval, output_path):
    """Generate/edit video through Gemini Omni Flash Interactions API."""
    api_key = headers.get("api_key") or params.get("api_key")
    if not api_key:
        return {"status": False, "message": "API key is required for Gemini Omni video generation."}
    if not prompt:
        return {"status": False, "message": "Prompt is required for Gemini Omni video generation."}

    model_name = model_name or OMNI_DEFAULT_VIDEO_MODEL
    aspect_ratio = params.get("aspect_ratio")
    delivery = params.get("delivery") or "uri"
    task = params.get("task")
    negative_prompt = params.get("negative_prompt")
    if negative_prompt:
        # Omni does not support a separate negative_prompt field; docs recommend writing negatives in the prompt.
        prompt = f"{prompt}\nDo not include: {negative_prompt}."

    input_parts = []
    image_specs = []

    # Backward-compatible single-image inputs.
    if params.get("image_base64") or params.get("image_path"):
        image_specs.append({
            "image_path": params.get("image_path"),
            "image_base64": params.get("image_base64"),
            "mime_type": params.get("image_mime_type") or params.get("mime_type"),
        })

    # Optional multi-reference inputs for Omni prompt-guide tags (<IMAGE_REF_N>, <FIRST_FRAME>).
    for key in ("image_paths", "reference_image_paths"):
        value = params.get(key)
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            for path in value:
                image_specs.append({"image_path": path, "mime_type": None})

    try:
        for spec in image_specs:
            part = _load_image_part(**spec)
            if part:
                input_parts.append(part)
    except Exception as e:
        return {"status": False, "message": f"Failed to prepare Gemini Omni image input: {e}"}

    if input_parts:
        input_parts.append({"type": "text", "text": prompt})
        interaction_input = input_parts
        task = task or "image_to_video"
    else:
        interaction_input = prompt
        task = task or "text_to_video"

    response_format = {"type": "video", "delivery": delivery}
    if aspect_ratio:
        response_format["aspect_ratio"] = aspect_ratio

    request_body = {
        "model": model_name,
        "input": interaction_input,
        "response_format": response_format,
        "generation_config": {"video_config": {"task": task}},
        "background": _as_bool(params.get("background"), False),
        "store": _as_bool(params.get("store"), False),
        "stream": _as_bool(params.get("stream"), False),
    }
    previous_interaction_id = params.get("previous_interaction_id")
    if previous_interaction_id:
        request_body["previous_interaction_id"] = previous_interaction_id

    print(f"🎬 Starting Gemini Omni video generation with model: {model_name}")
    print(f"🎯 Omni task={task}, delivery={delivery}, aspect_ratio={aspect_ratio or 'default'}")
    print(f"📝 Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"📝 Prompt: {prompt}")

    try:
        response = requests.post(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            json=request_body,
            timeout=600,
        )
        if response.status_code != 200:
            return {
                "status": False,
                "message": f"Gemini Omni API error: {response.status_code} - {response.text[:1000]}",
            }

        interaction = response.json()
        raw_response_json = json.dumps(interaction, indent=2, default=str)
        video_outputs = _extract_omni_video_outputs(interaction)
        if not video_outputs:
            return {
                "status": False,
                "message": "Gemini Omni completed but returned no video output.",
                "raw_api_response": raw_response_json,
            }

        video_payloads = []
        max_poll_attempts = int(params.get("max_poll_attempts", 120))
        for output in video_outputs:
            if output.get("data"):
                video_payloads.append(base64.b64decode(output["data"]))
            elif output.get("uri"):
                video_payloads.append(_download_omni_video_uri(output["uri"], api_key, poll_interval, max_poll_attempts))

        video_results = _save_video_results(video_payloads, output_path)
        if not video_results:
            return {
                "status": False,
                "message": "Gemini Omni returned video outputs, but no videos could be downloaded/saved.",
                "raw_api_response": raw_response_json,
            }

        if len(video_results) == 1:
            return {
                "status": True,
                "data": {
                    "video_path": video_results[0]["video_path"],
                    "filename": video_results[0]["filename"],
                    "video_format": "MP4",
                    "prompt": prompt,
                    "model": model_name,
                    "interaction_id": interaction.get("id"),
                    "raw_api_response": raw_response_json,
                },
                "message": "Video generated successfully with Gemini Omni.",
            }

        return {
            "status": True,
            "data": {
                "videos": video_results,
                "video_count": len(video_results),
                "video_format": "MP4",
                "prompt": prompt,
                "model": model_name,
                "interaction_id": interaction.get("id"),
                "raw_api_response": raw_response_json,
            },
            "message": f"{len(video_results)} videos generated successfully with Gemini Omni.",
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Exception during Gemini Omni video generation: {error_trace}")
        return {
            "status": False,
            "message": f"Exception when generating Gemini Omni video: {e}",
            "raw_api_response": error_trace,
        }


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

    # Optional per-call timeout (seconds). Values larger than 600 are
    # interpreted as milliseconds for backwards compatibility with workflows
    # that already set e.g. `timeout: 20000`.
    timeout_param = params.get("timeout")
    timeout_seconds = None
    if timeout_param is not None:
        try:
            timeout_seconds = float(timeout_param)
            if timeout_seconds > 600:
                timeout_seconds = timeout_seconds / 1000.0
        except (TypeError, ValueError):
            timeout_seconds = None

    # AI Studio Implementation (default)
    if provider == "ai_studio":
        api_key = params.get("api_key")

        if not api_key:
            return {"status": False, "message": "API key is required for AI Studio."}

        try:
            llm_kwargs = {"model": model_name, "api_key": api_key}
            if timeout_seconds is not None:
                llm_kwargs["timeout"] = timeout_seconds
            llm = ChatGoogleGenerativeAI(**llm_kwargs)
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
        priority_mode = params.get("priority_mode", False)  # Priority PayGo tier

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

            additional_headers = {}
            if priority_mode:
                additional_headers["x-vertex-ai-llm-shared-request-type"] = "priority"

            vertex_kwargs = {
                "model_name": model_name,
                "project": project_id,
                "location": location,
                "credentials": credentials,
                "additional_headers": additional_headers if additional_headers else None,
            }
            if timeout_seconds is not None:
                # ChatVertexAI accepts both `timeout` (modern langchain) and
                # `request_timeout` (legacy). Pass `timeout`; fall back if the
                # installed version rejects it.
                try:
                    llm = ChatVertexAI(timeout=timeout_seconds, **vertex_kwargs)
                except TypeError:
                    llm = ChatVertexAI(request_timeout=timeout_seconds, **vertex_kwargs)
            else:
                llm = ChatVertexAI(**vertex_kwargs)

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


def invoke_embedding(params):
    """
    Vertex AI text embeddings (default: text-embedding-004).

    Mirrors the Vertex auth convention used by invoke_prompt (provider=vertex_ai):
    reads `credential` (service account JSON, string or dict) and `project_id`
    from the connector context-variables. OpenAI model names
    (text-embedding-3-*, *ada*) are remapped to text-embedding-004 so existing
    workflows keep working without touching the `model` they pass.

    Parameters:
    - model_name: Model to use (default: "text-embedding-004")
    - project_id: GCP Project ID (from context-variables)
    - location:   GCP location (default: "us-central1")
    - credential: Service account JSON (string or dict). Falls back to ADC.
    """
    model_name = params.get("model_name") or ""
    if (not model_name) or ("text-embedding-3" in model_name) or ("ada" in model_name):
        model_name = "text-embedding-004"

    project_id = params.get("project_id") or params.get("project")
    location = params.get("location", "us-central1")
    credential = params.get("credential")

    try:
        credentials = None
        if credential:
            if isinstance(credential, str):
                try:
                    credential = json.loads(credential)
                except json.JSONDecodeError as e:
                    return {"status": False, "message": f"credential must be valid JSON: {e}"}
            credentials = service_account.Credentials.from_service_account_info(
                credential, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )

        kwargs = {"model_name": model_name}
        if project_id:
            kwargs["project"] = project_id
        if location:
            kwargs["location"] = location
        if credentials:
            kwargs["credentials"] = credentials

        llm = VertexAIEmbeddings(**kwargs)

        return {
            "status": True,
            "data": llm,
            "message": f"VertexAI embeddings loaded: {model_name}",
        }
    except Exception as e:
        return {"status": False, "message": f"Exception when creating embedding model: {e}"}


def invoke_image(request_data):
    """Generate images using Google's Gemini model with optional input image.

    Supports both AI Studio (default) and Vertex AI providers.

    Provider selection:
    - provider: "ai_studio" (default) or "vertex_ai" — read from params first, then headers.

    AI Studio auth (provider="ai_studio"):
    - api_key: Required — get from https://aistudio.google.com/apikey

    Vertex AI auth (provider="vertex_ai"):
    - project_id: Required — your GCP Project ID
    - credential: Required — service account JSON (string or dict)
    - location: Optional — defaults to "us-central1"

    NOTE: Vertex AI does NOT support API keys; OAuth2 service account credentials only.
    """

    params = request_data.get("params") or {}
    headers = request_data.get("headers") or {}

    provider = (params.get("provider") or headers.get("provider") or "ai_studio").lower()

    if provider == "ai_studio":
        api_key = headers.get("api_key") or params.get("api_key")
        if not api_key:
            return {"status": False, "message": "API key is required for AI Studio."}
    elif provider == "vertex_ai":
        project_id = headers.get("project_id") or params.get("project_id")
        if not project_id:
            return {"status": False, "message": "project_id is required for Vertex AI."}

        credential = headers.get("credential") or params.get("credential")
        location = params.get("location") or headers.get("location") or "us-central1"

        credentials = None
        if credential:
            if isinstance(credential, str):
                try:
                    credential = json.loads(credential)
                except json.JSONDecodeError:
                    return {"status": False, "message": "credential must be valid JSON"}
            # genai.Client (unlike ChatVertexAI) doesn't apply default scopes to
            # raw service-account credentials, so calls fail with `invalid_scope`.
            credentials = service_account.Credentials.from_service_account_info(
                credential,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
    else:
        return {
            "status": False,
            "message": f"Invalid provider: {provider}. Must be 'ai_studio' or 'vertex_ai'.",
        }

    # Get parameters
    image_paths = params.get("image_paths") or []  # Accept array of image paths
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    else:
        image_paths = list(image_paths)
    image_path = params.get("image_path")  # Keep backward compatibility

    # Collect individual image_path_N fields and add to array
    i = 1
    while True:
        field_name = f"image_path_{i}"
        field_value = params.get(field_name)
        if field_value:
            image_paths.append(field_value)
            i += 1
        else:
            break

    # If single image_path is provided, convert to array
    if image_path and image_path not in image_paths:
        image_paths.append(image_path)

    prompt = params.get("prompt", "Ronaldinho Gaúcho brincando com uma bola de lã")
    model_name = params.get("model_name") or "gemini-3-pro-image-preview"
    aspect_ratio = params.get("aspect_ratio")  # e.g., "16:9", "1:1", "9:16"

    # Get template variables for replacement
    home_team = params.get("home_team")
    away_team = params.get("away_team")
    home_animal = params.get("home_animal")
    away_animal = params.get("away_animal")

    # Substitute template variables in prompt
    if "{{" in prompt:
        if home_team:
            prompt = prompt.replace("{{home_team}}", str(home_team))
        if away_team:
            prompt = prompt.replace("{{away_team}}", str(away_team))
        if home_animal:
            prompt = prompt.replace("{{home_animal}}", str(home_animal))
        if away_animal:
            prompt = prompt.replace("{{away_animal}}", str(away_animal))

    try:
        if provider == "ai_studio":
            client = genai.Client(api_key=api_key)
        else:  # vertex_ai
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=credentials,
            )

        # Prepare image parts under the same local/remote media policy used by
        # the router. Remote hosts are deny-by-default and configured through
        # GOOGLE_GENAI_MEDIA_ALLOWED_HOSTS.
        #
        # Legacy behavior preserved: an invalid input image is skipped (and
        # recorded in the response metadata), not fatal to the whole call.
        # Skip reasons are sanitized fixed strings — never the raw path.
        image_parts = []
        skipped_media = []
        for img_index, img_path in enumerate(image_paths or []):
            try:
                if str(img_path).startswith(("http://", "https://")):
                    image_data, mime_type = _download_remote_image(img_path)
                else:
                    local_path = _safe_local_media_path(img_path)
                    image_data = local_path.read_bytes()
                    mime_type = _guess_mime_type(local_path)
            except Exception:
                is_remote = str(img_path).startswith(("http://", "https://"))
                skipped_media.append(
                    {
                        "index": img_index,
                        "kind": "remote" if is_remote else "local",
                        "reason": "failed media security validation; input skipped",
                    }
                )
                continue
            image_parts.append(
                types.Part(inline_data=types.Blob(data=image_data, mime_type=mime_type))
            )
        if skipped_media:
            print(f"⚠️ {len(skipped_media)} input image(s) skipped by media security validation")

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
                                delete=False, suffix=".webp"
                            )
                            temp_path = temp_file.name
                            temp_file.close()
                            image.save(temp_path, format="WEBP", quality=85)

                            # Extract filename from temp_path
                            filename = os.path.basename(temp_path)

                            return {
                                "status": True,
                                "data": {
                                    "image_path": temp_path,
                                    "filename": filename,
                                    "image_format": "WEBP",
                                    "prompt": prompt,
                                    "model": model_name,
                                    "input_images_count": len(image_parts),
                                    "input_image_paths": (
                                        image_paths if image_paths else []
                                    ),
                                    "skipped_media": skipped_media,
                                },
                                "message": f"Image generated successfully using {len(image_parts)} input images.",
                            }
                else:
                    print(f"❌ Candidate {idx} has no content")
            
            return {
                "status": False,
                "message": "No image was generated - candidates exist but contain no image data",
                "debug_info": f"Response had {len(response.candidates)} candidates but none contained inline_data",
                "skipped_media": skipped_media,
            }
        else:
            return {
                "status": False,
                "message": "Error generating image - no candidates in response",
                "debug_info": str(response) if response else "Response is None",
                "skipped_media": skipped_media,
            }

    except Exception:
        return {"status": False, "message": "The configured image provider could not generate an image."}


def edit_image(request_data):
    """Compatibility alias for the previously observed google-genai/edit_image call."""
    payload = dict(request_data or {})
    params = dict(payload.get("params") or payload)
    temporary_paths = []
    params.setdefault("prompt", params.get("instruction"))
    legacy_images = params.get("images_base64") or []
    image_paths = list(params.get("image_paths") or [])
    for item in legacy_images:
        if not item:
            continue
        if str(item).startswith(("http://", "https://")):
            image_paths.append(item)
            continue
        encoded = str(item)
        if encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except Exception:
            return {"status": False, "message": "A legacy image input is not valid base64."}
        temp_root = Path(os.getenv("MACHINA_WORK_DIR", os.getcwd())).expanduser().resolve()
        temp_root.mkdir(parents=True, exist_ok=True)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png", dir=temp_root)
        temp_file.write(image_bytes)
        temp_file.close()
        temporary_paths.append(temp_file.name)
        image_paths.append(temp_file.name)
    params["image_paths"] = image_paths
    requested_model = params.get("model_name") or params.get("model")
    if not requested_model or str(requested_model).lower().startswith("gpt-"):
        params["model_name"] = "gemini-3-pro-image-preview"
    payload["params"] = params
    try:
        result = invoke_image(payload)
        if result.get("status") and isinstance(result.get("data"), dict):
            data = result["data"]
            data.setdefault("final_filename", data.get("filename"))
            data.setdefault("full_filepath", data.get("image_path"))
        return result
    finally:
        for path in temporary_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


def invoke_search(request_data):
    """Search the web using Google Gemini with Google Search grounding"""

    params = request_data.get("params")

    headers = request_data.get("headers")

    credential = headers.get("credential")

    project_id = headers.get("project_id")

    location = params.get("location", "global")

    # Get model_name from params first, then check headers (connector config)
    model_name = params.get("model_name") or headers.get("model")

    search_query = params.get("search_query")

    # Optional per-call timeout (seconds). Without it a stalled grounded-search
    # request hangs indefinitely (ChatVertexAI.invoke has no default deadline),
    # which can block a whole batch. Mirrors invoke_prompt: values > 600 are
    # treated as milliseconds for backwards compatibility.
    timeout_param = params.get("timeout")
    search_timeout_seconds = None
    if timeout_param is not None:
        try:
            search_timeout_seconds = float(timeout_param)
            if search_timeout_seconds > 600:
                search_timeout_seconds = search_timeout_seconds / 1000.0
        except (TypeError, ValueError):
            search_timeout_seconds = None

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
    days_back = params.get("days_back")  # window size before an explicit end date
    recency_days = params.get("recency_days")  # rolling window of the last N days, anchored to today

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

    priority_mode = params.get("priority_mode", False)  # Priority PayGo tier

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
            # recency_days (preferred) and days_back share the same window size.
            # Default of 3 only matters when an end date is present (explicit or anchored).
            days_back_n = _parse_days_back(
                recency_days if recency_days is not None else days_back, "recency_days"
            )

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

            # recency_days: anchor the rolling window to today when no explicit dates were given
            if recency_days is not None and end_dt is None and start_dt is None:
                end_dt = datetime.datetime.utcnow().date()

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

        additional_headers = {}
        if priority_mode:
            additional_headers["x-vertex-ai-llm-shared-request-type"] = "priority"

        vertex_search_kwargs = {
            "model": model_name,
            "credentials": credentials,
            "location": location,
            "project": project_id,
            "additional_headers": additional_headers if additional_headers else None,
        }
        if search_timeout_seconds is not None:
            vertex_search_kwargs["timeout"] = search_timeout_seconds

        llm = ChatVertexAI(**vertex_search_kwargs)

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
                "recency_days": recency_days,   # echo input
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
    Generate videos using Google's Gemini Omni or Veo APIs via direct REST calls.
    
    Uses direct HTTP calls to the Generative Language API, bypassing SDK version issues.
    
    Parameters:
    - model_name: Model name. Available models:
        - "gemini-omni-flash-preview" (Gemini Omni Flash Interactions API - multimodal video)
        - "veo-3.1-generate-preview" (Veo 3.1 Preview - 720p/1080p, 8s/6s/4s)
        - "veo-3.1-fast-generate-preview" (Veo 3.1 Fast Preview - optimized for speed)
        - "veo-3.0-generate-001" (Veo 3 - 720p/1080p 16:9 only, 8s)
        - "veo-3.0-fast-generate-001" (Veo 3 Fast)
        - "veo-2.0-generate-001" (Veo 2 - 720p, 5-8s, up to 2 videos)
    - prompt: Required - Text prompt describing the video to generate.
              Supports template variables: {{dialogue}}, {{speaker_team}}, {{previous_dialogue}}, {{emotion}},
              {{home_voice_description}}, {{away_voice_description}}, {{speaker_voice_description}},
              {{home_personality_description}}, {{away_personality_description}}, {{speaker_personality_description}},
              {{home_team}}, {{away_team}}, {{speaker_team_name}}, {{home_animal}}, {{away_animal}}, {{speaker_animal}}
    - image_path: Optional - Input image URL or path for image-to-video generation
    - poll_interval: Optional - Seconds between status checks (default: 10)
    - output_path: Optional - Custom output path for the video
    - max_retries: Optional - Maximum retry attempts for empty video responses (default: 3)
    - retry_delay: Optional - Seconds to wait between retries (default: 5)
    - api_key: Required - Get from https://aistudio.google.com/apikey
    
    Template Variables (for prompt substitution):
    - dialogue: Optional - Dialogue text to substitute for {{dialogue}} in prompt
    - speaker_team: Optional - Team name to substitute for {{speaker_team}} in prompt
    - previous_dialogue: Optional - Previous dialogue to substitute for {{previous_dialogue}} in prompt
    - emotion: Optional - Emotion/delivery cue to substitute for {{emotion}} in prompt
    - home_voice_description: Optional - Voice description for home team to substitute for {{home_voice_description}} in prompt
    - away_voice_description: Optional - Voice description for away team to substitute for {{away_voice_description}} in prompt
    - speaker_voice_description: Optional - Voice description for current speaker to substitute for {{speaker_voice_description}} in prompt
    - home_personality_description: Optional - Personality description for home team to substitute for {{home_personality_description}} in prompt
    - away_personality_description: Optional - Personality description for away team to substitute for {{away_personality_description}} in prompt
    - speaker_personality_description: Optional - Personality description for current speaker to substitute for {{speaker_personality_description}} in prompt
    - home_team: Optional - Home team name to substitute for {{home_team}} in prompt
    - away_team: Optional - Away team name to substitute for {{away_team}} in prompt
    - speaker_team_name: Optional - Current speaker's team name to substitute for {{speaker_team_name}} in prompt
    - home_animal: Optional - Home team animal to substitute for {{home_animal}} in prompt
    - away_animal: Optional - Away team animal to substitute for {{away_animal}} in prompt
    - speaker_animal: Optional - Current speaker's animal to substitute for {{speaker_animal}} in prompt
    - aspect_ratio: Optional - Video aspect ratio. Omni supports "16:9" and "9:16"; Veo support varies by model.
    - delivery: Optional Omni delivery mode, "uri" (default) or inline base64.
    - task: Optional Omni video_config task: "text_to_video", "image_to_video", "reference_to_video", or "edit".
    - previous_interaction_id: Optional Omni interaction ID for iterative editing (requires stored prior interaction).
    - negative_prompt: Optional - Text describing what to avoid; Omni folds this into the regular prompt.
    
    Note: Request latency varies from 11 seconds to 6 minutes during peak hours.
    Generated videos are stored on server for 2 days before removal.
    """
    import base64
    import json
    
    params = request_data.get("params")
    headers = request_data.get("headers")
    
    # Get parameters
    prompt = params.get("prompt")
    # Use 'or' instead of default to handle None values
    model_name = params.get("model_name") or OMNI_DEFAULT_VIDEO_MODEL
    poll_interval = params.get("poll_interval", 10)  # seconds
    output_path = params.get("output_path")  # Optional custom output path
    max_retries = params.get("max_retries", 3)  # Maximum retry attempts
    retry_delay = params.get("retry_delay", 5)  # Seconds between retries
    
    # Video generation parameters
    aspect_ratio = params.get("aspect_ratio")  # e.g., "16:9", "9:16", "1:1"
    negative_prompt = params.get("negative_prompt")  # e.g., "cartoon, drawing, low quality"
    
    # Input image support for image-to-video
    image_path = params.get("image_path")
    
    # Template variables for prompt substitution
    dialogue = params.get("dialogue", "")
    speaker_team = params.get("speaker_team", "")
    previous_dialogue = params.get("previous_dialogue", "")
    emotion = params.get("emotion", "")
    home_voice_description = params.get("home_voice_description", "")
    away_voice_description = params.get("away_voice_description", "")
    speaker_voice_description = params.get("speaker_voice_description", "")
    home_personality_description = params.get("home_personality_description", "")
    away_personality_description = params.get("away_personality_description", "")
    speaker_personality_description = params.get("speaker_personality_description", "")
    home_team = params.get("home_team", "")
    away_team = params.get("away_team", "")
    speaker_team_name = params.get("speaker_team_name", "")
    home_animal = params.get("home_animal", "")
    away_animal = params.get("away_animal", "")
    speaker_animal = params.get("speaker_animal", "")
    
    # API key is required
    api_key = headers.get("api_key")
    
    if not api_key:
        return {"status": False, "message": "API key is required for video generation."}
    
    if not prompt:
        return {"status": False, "message": "Prompt is required for video generation."}
    
    # Substitute template variables in prompt
    if "{{" in prompt:
        prompt = prompt.replace("{{dialogue}}", str(dialogue))
        prompt = prompt.replace("{{speaker_team}}", str(speaker_team))
        prompt = prompt.replace("{{previous_dialogue}}", str(previous_dialogue))
        prompt = prompt.replace("{{emotion}}", str(emotion))
        prompt = prompt.replace("{{home_voice_description}}", str(home_voice_description))
        prompt = prompt.replace("{{away_voice_description}}", str(away_voice_description))
        prompt = prompt.replace("{{speaker_voice_description}}", str(speaker_voice_description))
        prompt = prompt.replace("{{home_personality_description}}", str(home_personality_description))
        prompt = prompt.replace("{{away_personality_description}}", str(away_personality_description))
        prompt = prompt.replace("{{speaker_personality_description}}", str(speaker_personality_description))
        prompt = prompt.replace("{{home_team}}", str(home_team))
        prompt = prompt.replace("{{away_team}}", str(away_team))
        prompt = prompt.replace("{{speaker_team_name}}", str(speaker_team_name))
        prompt = prompt.replace("{{home_animal}}", str(home_animal))
        prompt = prompt.replace("{{away_animal}}", str(away_animal))
        prompt = prompt.replace("{{speaker_animal}}", str(speaker_animal))
        print(f"🔄 Template variables substituted in prompt")
    
    if _is_omni_video_model(model_name):
        return _invoke_omni_video(request_data, params, headers, prompt, model_name, poll_interval, output_path)

    # Retry loop for handling empty video responses
    video_results = None  # Initialize outside loop
    raw_response_json = None  # Initialize outside loop
    
    for attempt in range(max_retries + 1):  # +1 because first attempt is not a retry
        if attempt > 0:
            print(f"🔄 Retry attempt {attempt}/{max_retries} after empty video response...")
            print(f"⏳ Waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)
        
        try:
            # Base URL for Generative Language API
            base_url = "https://generativelanguage.googleapis.com/v1beta"
        
            print(f"🎬 Starting video generation with model: {model_name}")
            print(f"📝 Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"📝 Prompt: {prompt}")
            
            # Build the request body
            request_body = {
                "instances": [
                    {
                        "prompt": prompt
                    }
                ]
            }
            
            # Add parameters (aspectRatio, negativePrompt) if provided
            parameters = {}
            if aspect_ratio:
                parameters["aspectRatio"] = aspect_ratio
                print(f"📐 Aspect ratio: {aspect_ratio}")
            if negative_prompt:
                parameters["negativePrompt"] = negative_prompt
                print(f"🚫 Negative prompt: {negative_prompt}")
            
            if parameters:
                request_body["parameters"] = parameters
            
            # Prepare input image if provided (image-to-video)
            if image_path:
                print(f"🖼️ Processing input image: {image_path}")
                
                image_data = None
                if image_path.startswith(("http://", "https://")):
                    # Download image from URL
                    print(f"🌐 Downloading image from URL: {image_path}")
                    try:
                        response = requests.get(image_path)
                        response.raise_for_status()
                        image_data = response.content
                        print(f"📊 Downloaded image size: {len(image_data)} bytes")
                    except Exception as e:
                        print(f"❌ Error downloading image: {e}")
                        return {"status": False, "message": f"Failed to download input image: {e}"}
                elif os.path.exists(image_path):
                    # Read local file
                    print(f"📁 Reading local image: {image_path}")
                    try:
                        with open(image_path, "rb") as image_file:
                            image_data = image_file.read()
                        print(f"📊 Image size: {len(image_data)} bytes")
                    except Exception as e:
                        print(f"❌ Error reading image: {e}")
                        return {"status": False, "message": f"Failed to read input image: {e}"}
                else:
                    print(f"❌ Image not found: {image_path}")
                    return {"status": False, "message": f"Input image not found: {image_path}"}
                
                if image_data:
                    # Detect MIME type based on file extension
                    mime_type = "image/jpeg"  # default
                    if image_path.lower().endswith(".png"):
                        mime_type = "image/png"
                    elif image_path.lower().endswith(".gif"):
                        mime_type = "image/gif"
                    elif image_path.lower().endswith(".webp"):
                        mime_type = "image/webp"
                    
                    # Encode image to base64
                    image_base64 = base64.b64encode(image_data).decode("utf-8")
                    
                    # Add image to request body
                    request_body["instances"][0]["image"] = {
                        "bytesBase64Encoded": image_base64,
                        "mimeType": mime_type
                    }
                    print(f"✅ Input image prepared for video generation ({mime_type})")
                    print("🖼️ Using input image for image-to-video generation")
            else:
                print("📝 Using text-only prompt for video generation")
            
            # Make the API call to start video generation
            generate_url = f"{base_url}/models/{model_name}:predictLongRunning?key={api_key}"
            
            print(f"🌐 Calling API: {base_url}/models/{model_name}:predictLongRunning")
            
            response = requests.post(
                generate_url,
                headers={"Content-Type": "application/json"},
                json=request_body
            )
            
            if response.status_code != 200:
                error_detail = response.text
                print(f"❌ API error: {response.status_code} - {error_detail}")
                return {
                    "status": False,
                    "message": f"Video generation API error: {response.status_code} - {error_detail}"
                }
            
            operation_data = response.json()
            operation_name = operation_data.get("name")
            
            if not operation_name:
                return {"status": False, "message": "No operation name returned from API."}
            
            print(f"⏳ Video generation operation started: {operation_name}")
            print(f"⏳ Polling every {poll_interval} seconds...")
            
            # Poll the operation status until the video is ready
            while True:
                print("⏳ Waiting for video generation to complete...")
                time.sleep(poll_interval)
                
                # Check operation status
                poll_url = f"{base_url}/{operation_name}?key={api_key}"
                poll_response = requests.get(poll_url)
                
                if poll_response.status_code != 200:
                    print(f"⚠️ Poll error: {poll_response.status_code}")
                    continue
                
                poll_data = poll_response.json()
                
                # Check if operation is done
                if poll_data.get("done", False):
                    print("✅ Video generation completed!")
                    break
                
                # Check for error during polling
                if "error" in poll_data:
                    error_msg = poll_data["error"].get("message", "Unknown error")
                    raw_response = json.dumps(poll_data, indent=2, default=str)
                    return {
                        "status": False,
                        "message": f"Video generation failed: {error_msg}",
                        "raw_api_response": raw_response
                    }
            
            # Capture full raw response for debugging
            raw_response_json = json.dumps(poll_data, indent=2, default=str)
            print(f"📋 Full API Response:\n{raw_response_json}")
            
            # Extract response from completed operation
            if "error" in poll_data:
                error_msg = poll_data["error"].get("message", "Unknown error")
                return {
                    "status": False,
                    "message": f"Video generation failed: {error_msg}",
                    "raw_api_response": raw_response_json
                }
            
            # Check for errors in response as well
            response_data = poll_data.get("response", {})
            if isinstance(response_data, dict) and "error" in response_data:
                error_msg = response_data["error"].get("message", "Unknown error")
                return {
                    "status": False,
                    "message": f"Video generation failed in response: {error_msg}",
                    "raw_api_response": raw_response_json
                }
            
            # Try multiple response structures
            generated_samples = None
            
            # Structure 1: generateVideoResponse.generatedSamples
            if not generated_samples:
                generated_samples = response_data.get("generateVideoResponse", {}).get("generatedSamples", [])
            
            # Structure 2: predictions array
            if not generated_samples:
                predictions = response_data.get("predictions", [])
                if predictions:
                    generated_samples = predictions
            
            # Structure 3: Direct response array
            if not generated_samples and isinstance(response_data, list):
                generated_samples = response_data
            
            # Structure 4: Check if response itself is the samples
            if not generated_samples and "video" in response_data:
                generated_samples = [response_data]
            
            if not generated_samples:
                # Include FULL response in error for debugging
                error_msg = "Video generation completed but no videos were generated."
                print(f"⚠️ {error_msg}")
                print(f"📋 Response structure: {raw_response_json[:500]}...")
                
                # If we have retries left, continue to retry
                if attempt < max_retries:
                    print(f"🔄 Will retry ({attempt + 1}/{max_retries})...")
                    continue  # Retry the entire generation process
                
                # No more retries left, return error
                return {
                    "status": False,
                    "message": f"{error_msg} (after {attempt + 1} attempt(s))",
                    "raw_api_response": raw_response_json
                }
            
            print(f"🎬 Generated {len(generated_samples)} video(s)")
            
            # Process all generated videos
            video_results = []
            for idx, sample in enumerate(generated_samples):
                # Get video data - could be in different formats
                video_bytes = None
                video_uri = None
                
                # Check for video field with bytes or uri
                video_data = sample.get("video", sample)
                
                if isinstance(video_data, dict):
                    if "bytesBase64Encoded" in video_data:
                        video_bytes = base64.b64decode(video_data["bytesBase64Encoded"])
                    elif "uri" in video_data:
                        video_uri = video_data["uri"]
                
                # Alternative: check for videoUri directly in sample
                if not video_bytes and not video_uri:
                    video_uri = sample.get("videoUri") or sample.get("video_uri")
                
                if not video_bytes and video_uri:
                    # Download video from URI
                    print(f"🌐 Downloading video from: {video_uri}")
                    try:
                        # If it's a Google storage URI, we may need to append API key
                        download_url = video_uri
                        if "generativelanguage.googleapis.com" in video_uri and "key=" not in video_uri:
                            separator = "&" if "?" in video_uri else "?"
                            download_url = f"{video_uri}{separator}key={api_key}"
                        
                        video_response = requests.get(download_url)
                        video_response.raise_for_status()
                        video_bytes = video_response.content
                    except Exception as e:
                        print(f"❌ Error downloading video: {e}")
                        continue
                
                if not video_bytes:
                    print(f"⚠️ Video {idx + 1} has no downloadable content, skipping")
                    continue
                
                # Determine output path for this video
                if output_path and len(generated_samples) == 1:
                    video_output_path = output_path
                elif output_path:
                    # Multiple videos: append index to filename
                    base, ext = os.path.splitext(output_path)
                    video_output_path = f"{base}_{idx + 1}{ext}"
                else:
                    # Create a temporary file
                    temp_file = tempfile.NamedTemporaryFile(
                        delete=False, suffix=".mp4"
                    )
                    video_output_path = temp_file.name
                    temp_file.close()
                
                # Save the video
                print(f"💾 Saving video {idx + 1} to: {video_output_path}")
                with open(video_output_path, "wb") as f:
                    f.write(video_bytes)
                
                video_filename = os.path.basename(video_output_path)
                print(f"✅ Video {idx + 1} saved: {video_filename} ({len(video_bytes)} bytes)")
                
                video_results.append({
                    "video_path": video_output_path,
                    "filename": video_filename,
                })
            
            if not video_results:
                error_msg = "Video generation completed but no videos could be saved."
                print(f"⚠️ {error_msg}")
                
                # If we have retries left, continue to retry
                if attempt < max_retries:
                    print(f"🔄 Will retry ({attempt + 1}/{max_retries})...")
                    continue  # Retry the entire generation process
                
                # No more retries left, return error
                return {
                    "status": False,
                    "message": f"{error_msg} (after {attempt + 1} attempt(s))",
                    "raw_api_response": raw_response_json
                }
            
            # Success! Break out of retry loop
            print(f"✅ Video generation successful on attempt {attempt + 1}")
            break  # Exit retry loop on success
        
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"❌ Exception on attempt {attempt + 1}: {error_trace}")
            
            # Only retry on "no videos generated" errors, not on other exceptions
            # Check if this is a retryable error (empty response)
            if attempt < max_retries and ("no videos" in str(e).lower() or "no videos were generated" in str(e).lower()):
                print(f"🔄 Will retry after exception ({attempt + 1}/{max_retries})...")
                continue
            
            # Non-retryable error or out of retries
            return {
                "status": False,
                "message": f"Exception when generating video: {e}",
                "raw_api_response": error_trace
            }
    
    # If we exited the loop without success (shouldn't happen, but safety check)
    if not video_results:
        return {
            "status": False,
            "message": f"Video generation failed after {max_retries + 1} attempt(s).",
            "raw_api_response": raw_response_json if raw_response_json else "No response captured"
        }
    
    # Return single video format for backward compatibility, or multiple if requested
    if len(video_results) == 1:
        return {
            "status": True,
            "data": {
                "video_path": video_results[0]["video_path"],
                "filename": video_results[0]["filename"],
                "video_format": "MP4",
                "prompt": prompt,
                "model": model_name,
                "input_image_path": image_path if image_path else None,
                "raw_api_response": raw_response_json,  # Include full API response
            },
            "message": "Video generated successfully.",
        }
    else:
        return {
            "status": True,
            "data": {
                "videos": video_results,
                "video_count": len(video_results),
                "video_format": "MP4",
                "prompt": prompt,
                "model": model_name,
                "input_image_path": image_path if image_path else None,
                "raw_api_response": raw_response_json,  # Include full API response
            },
            "message": f"{len(video_results)} videos generated successfully.",
        }
    
    # Final safety check (should not reach here if video_results was set)
    return {
        "status": False,
        "message": f"Video generation failed after {max_retries + 1} attempt(s).",
        "raw_api_response": "Unexpected end of retry loop"
    }


def invoke_tts(request_data):
    """
    Text-to-Speech using Gemini TTS via Vertex AI API.

    Parameters (via inputs in workflows):
    - text: Required - Text content to synthesize
    - voice_name: Voice to use (default: "Kore")
    - model_id: TTS model (default: "gemini-2.5-flash-tts")
    - language_code: BCP-47 language code (default: "en-us")
    - prompt: Optional styling instructions (e.g., "Say in a cheerful tone")
    - location: Vertex AI region (default: "us-central1")

    Authentication (via context-variables headers):
    - credential + project_id: Vertex AI service account (required)

    Returns:
    - file_path: Path to generated WAV audio file
    """
    from google.auth.transport.requests import Request as AuthRequest

    params = request_data.get("params", {})
    headers = request_data.get("headers", {})

    credential = headers.get("credential")
    project_id = headers.get("project_id")

    text = params.get("text")
    voice_name = params.get("voice_name") or "Kore"
    model_id = params.get("model_id") or "gemini-2.5-flash-tts"
    language_code = params.get("language_code") or "en-us"
    style_prompt = params.get("prompt")
    location = params.get("location") or "us-central1"

    if not credential or not project_id:
        return {"status": False, "message": "Missing Vertex AI credentials (credential + project_id required)."}

    if not text:
        return {"status": False, "message": "Missing text parameter."}

    try:
        # Parse credentials
        cred = credential
        if isinstance(cred, str):
            try:
                cred = json.loads(cred)
            except json.JSONDecodeError:
                return {"status": False, "message": "credential must be valid JSON"}

        credentials = service_account.Credentials.from_service_account_info(
            cred,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        credentials.refresh(AuthRequest())

        # Build content text
        if style_prompt:
            content_text = f"{style_prompt}: {text}"
        else:
            content_text = text

        print(f"TTS: model={model_id}, voice={voice_name}, lang={language_code}, location={location}, text_len={len(text)}")

        # Vertex AI API endpoint
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1"
            f"/projects/{project_id}/locations/{location}"
            f"/publishers/google/models/{model_id}:generateContent"
        )

        payload = {
            "contents": {
                "role": "user",
                "parts": {"text": content_text},
            },
            "generationConfig": {
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": voice_name
                        }
                    }
                },
                "temperature": 2.0,
            },
        }

        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {credentials.token}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )

        if response.status_code != 200:
            error_text = response.text[:500]
            print(f"TTS API error: {response.status_code} - {error_text}")
            return {"status": False, "message": f"TTS API error {response.status_code}: {error_text}"}

        result = response.json()

        # Extract audio from Vertex AI response
        candidates = result.get("candidates", [])
        if not candidates:
            return {"status": False, "message": f"No candidates in response: {json.dumps(result)[:500]}"}

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return {"status": False, "message": "No audio parts in response."}

        inline_data = parts[0].get("inlineData", {})
        audio_b64 = inline_data.get("data")

        if not audio_b64:
            return {"status": False, "message": "No audio data in response."}

        audio_data = base64.b64decode(audio_b64)

        # Save as WAV (Vertex AI returns PCM 24kHz 16-bit)
        temp_dir = tempfile.mkdtemp()
        save_file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.wav")

        with wave.open(save_file_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(audio_data)

        audio_duration = len(audio_data) / (24000 * 2)
        print(f"TTS: WAV saved to {save_file_path} ({audio_duration:.1f}s, {len(audio_data)} bytes)")

        return {
            "status": True,
            "data": {
                "file_path": save_file_path,
            },
            "message": "Text to speech converted and saved successfully.",
        }

    except Exception as e:
        print(f"TTS Error: {e}")
        return {"status": False, "message": f"Error generating speech: {str(e)}"}


# ---------------------------------------------------------------------------
# Custom Voice (Cloud Text-to-Speech) — Instant + Professional
#
# These three commands wrap the Google Cloud Text-to-Speech Custom Voice
# REST API. They share the same auth path as `invoke_tts` (Vertex
# service-account credential + project_id) and rely only on `requests` so
# we don't add new heavy dependencies to the connector image.
#
# - invoke_clone_instant_voice:    upload a 10-30s consented audio sample
#                                  and get back a `voice_clone_key` that
#                                  can be passed straight to synthesis.
#
# - invoke_train_pro_voice:        kick off a Professional Custom Voice
#                                  training job from a CSV manifest of
#                                  (transcript, audio_uri) pairs in GCS.
#                                  Returns the long-running operation
#                                  name; callers poll it themselves.
#
# - invoke_synthesize_custom_voice: synthesize text using either a
#                                  voice_clone_key (instant) or a
#                                  custom_voice.model name (pro). Saves
#                                  the resulting LINEAR16 audio as a WAV
#                                  next to the connector's tempdir.
# ---------------------------------------------------------------------------


def _gcp_access_token(credential):
    """Refresh a service-account credential and return its access token."""
    from google.auth.transport.requests import Request as AuthRequest

    cred = credential
    if isinstance(cred, str):
        try:
            cred = json.loads(cred)
        except json.JSONDecodeError:
            raise ValueError("credential must be valid JSON")

    credentials = service_account.Credentials.from_service_account_info(
        cred,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(AuthRequest())
    return credentials.token


def invoke_clone_instant_voice(request_data):
    """
    Create an Instant Custom Voice clone from a short consented sample.

    Parameters (params):
    - reference_audio_path: Required - Local path OR https/gs URL to a
      10-30 second WAV/LINEAR16 mono 24kHz sample of the speaker.
    - reference_audio_base64: Optional - alternative to reference_audio_path,
      a base64-encoded WAV blob.
    - consent_script: Required - The exact spoken-consent phrase the
      speaker recorded (Google requires this to verify consent).
    - language_code: BCP-47 language code (default: "en-US").

    Auth (headers, same as invoke_tts):
    - credential + project_id: Vertex AI service account.

    Returns:
    - data.voice_clone_key: opaque string to pass into
      invoke_synthesize_custom_voice as `voice_clone_key`.
    - data.consent_script: echo of the consent phrase used.
    """
    params = request_data.get("params", {})
    headers = request_data.get("headers", {})

    credential = headers.get("credential")
    project_id = headers.get("project_id")

    reference_audio_path = params.get("reference_audio_path")
    reference_audio_base64 = params.get("reference_audio_base64")
    consent_script = params.get("consent_script")
    language_code = params.get("language_code") or "en-US"

    if not credential or not project_id:
        return {"status": False, "message": "Missing Vertex AI credentials (credential + project_id required)."}
    if not consent_script:
        return {"status": False, "message": "consent_script is required (the exact phrase the speaker recorded)."}
    if not reference_audio_path and not reference_audio_base64:
        return {"status": False, "message": "Provide reference_audio_path (URL or local path) or reference_audio_base64."}

    try:
        # Resolve audio bytes
        audio_bytes = None
        if reference_audio_base64:
            audio_bytes = base64.b64decode(reference_audio_base64)
        elif reference_audio_path.startswith(("http://", "https://")):
            print(f"Downloading reference audio: {reference_audio_path}")
            resp = requests.get(reference_audio_path, timeout=60)
            resp.raise_for_status()
            audio_bytes = resp.content
        elif reference_audio_path.startswith("gs://"):
            return {
                "status": False,
                "message": "gs:// references not supported here — pre-fetch and pass an https URL or local path.",
            }
        elif os.path.exists(reference_audio_path):
            with open(reference_audio_path, "rb") as fh:
                audio_bytes = fh.read()
        else:
            return {"status": False, "message": f"Reference audio not found: {reference_audio_path}"}

        print(f"Instant voice clone: {len(audio_bytes)} bytes of reference audio, lang={language_code}")

        token = _gcp_access_token(credential)
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        url = "https://texttospeech.googleapis.com/v1beta1/voices:generateVoiceCloningKey"
        # `voice_talent_consent` expects the SAME shape as `reference_audio`
        # (audio_config + content) — it's the speaker's own recording of the
        # consent script, not the script text. The script text goes in the
        # top-level `consent_script` field. When the caller hasn't supplied a
        # separate consent recording, reuse the reference audio (the speaker
        # is the same person and Google verifies the voice match, not script
        # contents).
        audio_block = {
            "audio_config": {
                "audio_encoding": "LINEAR16",
                "sample_rate_hertz": 24000,
            },
            "content": audio_b64,
        }
        payload = {
            "reference_audio": audio_block,
            "voice_talent_consent": audio_block,
            "consent_script": consent_script,
            "language_code": language_code,
        }

        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Goog-User-Project": project_id,
                "Content-Type": "application/json",
            },
            timeout=120,
        )

        if response.status_code != 200:
            return {
                "status": False,
                "message": f"voiceCloningKey API error {response.status_code}: {response.text[:500]}",
            }

        result = response.json()
        voice_clone_key = result.get("voiceCloningKey") or result.get("voice_cloning_key")

        if not voice_clone_key:
            return {
                "status": False,
                "message": f"No voiceCloningKey returned: {json.dumps(result)[:500]}",
            }

        print(f"Instant voice clone key created (len={len(voice_clone_key)})")
        return {
            "status": True,
            "data": {
                "voice_clone_key": voice_clone_key,
                "consent_script": consent_script,
                "language_code": language_code,
            },
            "message": "Instant custom voice clone key created.",
        }

    except ValueError as ve:
        return {"status": False, "message": str(ve)}
    except Exception as e:
        print(f"Instant voice clone error: {e}")
        return {"status": False, "message": f"Error creating instant voice clone: {e}"}


def invoke_train_pro_voice(request_data):
    """
    Kick off a Professional Custom Voice training job.

    Pro voices require a curated multi-utterance dataset hosted in GCS
    plus a CSV manifest (transcript|gs://uri pairs). This function only
    starts the long-running training operation; you poll it yourself
    via the returned operation name.

    Parameters (params):
    - voice_name: Required - human-readable name for the resulting voice
      model (e.g. "anchor-en-male-01"). Must be unique within the project.
    - dataset_uri: Required - gs:// URI to the CSV manifest with one row
      per training utterance, formatted `<transcript>|<gs://audio.wav>`.
    - consent_audio_uri: Required - gs:// URI to a single WAV recording of
      the voice talent reading Google's standard consent script.
    - language_code: BCP-47 (default: "en-US").
    - location: GCP region for the training job (default: "global").

    Auth (headers): credential + project_id (same as invoke_tts).

    Returns:
    - data.operation_name: long-running operation; poll with the standard
      Google AI Platform `operations.get` endpoint.
    - data.voice_name: echo for downstream synthesis.
    """
    params = request_data.get("params", {})
    headers = request_data.get("headers", {})

    credential = headers.get("credential")
    project_id = headers.get("project_id")

    voice_name = params.get("voice_name")
    dataset_uri = params.get("dataset_uri")
    consent_audio_uri = params.get("consent_audio_uri")
    language_code = params.get("language_code") or "en-US"
    location = params.get("location") or "global"

    if not credential or not project_id:
        return {"status": False, "message": "Missing Vertex AI credentials (credential + project_id required)."}
    if not voice_name:
        return {"status": False, "message": "voice_name is required."}
    if not dataset_uri or not dataset_uri.startswith("gs://"):
        return {"status": False, "message": "dataset_uri must be a gs:// URI to the training manifest CSV."}
    if not consent_audio_uri or not consent_audio_uri.startswith("gs://"):
        return {"status": False, "message": "consent_audio_uri must be a gs:// URI to the consent WAV."}

    try:
        token = _gcp_access_token(credential)

        url = (
            f"https://texttospeech.googleapis.com/v1beta1"
            f"/projects/{project_id}/locations/{location}/customVoices"
        )
        payload = {
            "displayName": voice_name,
            "languageCode": language_code,
            "trainingConfig": {
                "datasetUri": dataset_uri,
                "consentAudioUri": consent_audio_uri,
            },
        }

        print(f"Starting Pro voice training: {voice_name} (dataset={dataset_uri})")
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Goog-User-Project": project_id,
                "Content-Type": "application/json",
            },
            timeout=120,
        )

        if response.status_code not in (200, 201):
            return {
                "status": False,
                "message": f"customVoices.create error {response.status_code}: {response.text[:500]}",
            }

        result = response.json()
        operation_name = result.get("name")
        if not operation_name:
            return {
                "status": False,
                "message": f"No operation name returned: {json.dumps(result)[:500]}",
            }

        print(f"Pro voice training started: {operation_name}")
        return {
            "status": True,
            "data": {
                "operation_name": operation_name,
                "voice_name": voice_name,
                "language_code": language_code,
                "location": location,
            },
            "message": "Professional custom voice training job started.",
        }

    except ValueError as ve:
        return {"status": False, "message": str(ve)}
    except Exception as e:
        print(f"Pro voice training error: {e}")
        return {"status": False, "message": f"Error starting pro voice training: {e}"}


def invoke_synthesize_custom_voice(request_data):
    """
    Synthesize text with either an Instant clone key OR a trained Pro voice.

    Parameters (params):
    - text: Required - text to synthesize.
    - voice_clone_key: Optional - returned by invoke_clone_instant_voice.
    - custom_voice_model: Optional - the Pro custom voice model name,
      e.g. "projects/<id>/locations/global/customVoices/anchor-en-male-01".
    - language_code: BCP-47 (default: "en-US").
    - speaking_rate: Optional float (default 1.0).
    - pitch: Optional float (default 0.0).
    - audio_encoding: "LINEAR16" (default) or "MP3".
    - sample_rate_hertz: Optional int (default 24000 for LINEAR16).

    Exactly one of voice_clone_key / custom_voice_model is required.

    Auth (headers): credential + project_id.

    Returns:
    - data.file_path: local path to the synthesized audio file.
    """
    params = request_data.get("params", {})
    headers = request_data.get("headers", {})

    credential = headers.get("credential")
    project_id = headers.get("project_id")

    text = params.get("text")
    voice_clone_key = params.get("voice_clone_key")
    custom_voice_model = params.get("custom_voice_model")
    language_code = params.get("language_code") or "en-US"
    speaking_rate = params.get("speaking_rate", 1.0)
    pitch = params.get("pitch", 0.0)
    audio_encoding = (params.get("audio_encoding") or "LINEAR16").upper()
    sample_rate_hertz = int(params.get("sample_rate_hertz") or 24000)

    if not credential or not project_id:
        return {"status": False, "message": "Missing Vertex AI credentials (credential + project_id required)."}
    if not text:
        return {"status": False, "message": "text is required."}
    if bool(voice_clone_key) == bool(custom_voice_model):
        return {
            "status": False,
            "message": "Provide exactly one of voice_clone_key (instant) or custom_voice_model (pro).",
        }

    try:
        token = _gcp_access_token(credential)

        voice_block = {"languageCode": language_code}
        if voice_clone_key:
            voice_block["voiceClone"] = {"voiceCloningKey": voice_clone_key}
        else:
            voice_block["customVoice"] = {"model": custom_voice_model}

        audio_config = {
            "audioEncoding": audio_encoding,
            "speakingRate": speaking_rate,
            "pitch": pitch,
        }
        if audio_encoding == "LINEAR16":
            audio_config["sampleRateHertz"] = sample_rate_hertz

        payload = {
            "input": {"text": text},
            "voice": voice_block,
            "audioConfig": audio_config,
        }

        url = "https://texttospeech.googleapis.com/v1beta1/text:synthesize"
        print(
            f"Custom voice synth: encoding={audio_encoding}, "
            f"mode={'instant' if voice_clone_key else 'pro'}, text_len={len(text)}"
        )

        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Goog-User-Project": project_id,
                "Content-Type": "application/json",
            },
            timeout=180,
        )

        if response.status_code != 200:
            return {
                "status": False,
                "message": f"text:synthesize error {response.status_code}: {response.text[:500]}",
            }

        result = response.json()
        audio_b64 = result.get("audioContent")
        if not audio_b64:
            return {"status": False, "message": f"No audioContent in response: {json.dumps(result)[:300]}"}

        audio_bytes = base64.b64decode(audio_b64)

        # Save to a temp file matching the requested encoding.
        temp_dir = tempfile.mkdtemp()
        if audio_encoding == "MP3":
            save_path = os.path.join(temp_dir, f"{uuid.uuid4()}.mp3")
            with open(save_path, "wb") as fh:
                fh.write(audio_bytes)
        else:
            save_path = os.path.join(temp_dir, f"{uuid.uuid4()}.wav")
            with wave.open(save_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate_hertz)
                wf.writeframes(audio_bytes)

        approx_duration = (
            len(audio_bytes) / (sample_rate_hertz * 2) if audio_encoding == "LINEAR16" else None
        )
        print(
            f"Custom voice audio saved: {save_path} "
            f"({len(audio_bytes)} bytes"
            + (f", ~{approx_duration:.1f}s" if approx_duration else "")
            + ")"
        )

        return {
            "status": True,
            "data": {
                "file_path": save_path,
                "audio_encoding": audio_encoding,
                "sample_rate_hertz": sample_rate_hertz if audio_encoding == "LINEAR16" else None,
                "voice_mode": "instant" if voice_clone_key else "pro",
            },
            "message": "Custom voice synthesis completed.",
        }

    except ValueError as ve:
        return {"status": False, "message": str(ve)}
    except Exception as e:
        print(f"Custom voice synth error: {e}")
        return {"status": False, "message": f"Error synthesizing custom voice: {e}"}


def invoke_music(request_data):
    """Generate music using Google's Lyria 3 model.

    Supports both AI Studio (default) and Vertex AI providers.

    Provider selection:
    - provider: "ai_studio" (default) or "vertex_ai" — read from params first, then headers.

    AI Studio auth (provider="ai_studio"):
    - api_key: Required — get from https://aistudio.google.com/apikey

    Vertex AI auth (provider="vertex_ai"):
    - project_id: Required — your GCP Project ID
    - credential: Required — service account JSON (string or dict)
    - location: Optional — defaults to "us-central1"

    NOTE: Vertex AI does NOT support API keys; OAuth2 service account credentials only.
    """

    params = request_data.get("params")
    headers = request_data.get("headers")

    api_key = None
    project_id = None
    location = None
    credentials = None

    provider = (params.get("provider") or headers.get("provider") or "ai_studio").lower()

    if provider == "ai_studio":
        api_key = headers.get("api_key") or params.get("api_key")
        if not api_key:
            return {"status": False, "message": "API key is required for AI Studio."}
    elif provider == "vertex_ai":
        project_id = headers.get("project_id") or params.get("project_id")
        if not project_id:
            return {"status": False, "message": "project_id is required for Vertex AI."}

        credential = headers.get("credential") or params.get("credential")
        location = params.get("location") or headers.get("location") or "us-central1"

        credentials = None
        if credential:
            if isinstance(credential, str):
                try:
                    credential = json.loads(credential)
                except json.JSONDecodeError:
                    return {"status": False, "message": "credential must be valid JSON"}
            credentials = service_account.Credentials.from_service_account_info(
                credential,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
    else:
        return {
            "status": False,
            "message": f"Invalid provider: {provider}. Must be 'ai_studio' or 'vertex_ai'.",
        }

    # Get parameters
    prompt = params.get("prompt", "A 30-second cheerful acoustic folk song with guitar and harmonica.")
    model_name = params.get("model_name") or "lyria-3-clip-preview"
    response_format_param = params.get("response_format", "mp3").lower()

    # Input image paths
    image_paths = params.get("image_paths", [])
    image_path = params.get("image_path")

    # Collect individual image_path_N fields and add to array
    i = 1
    while True:
        field_name = f"image_path_{i}"
        field_value = params.get(field_name)
        if field_value:
            image_paths.append(field_value)
            i += 1
        else:
            break

    if image_path and image_path not in image_paths:
        image_paths.append(image_path)

    # Get template variables for replacement
    home_team = params.get("home_team")
    away_team = params.get("away_team")
    home_animal = params.get("home_animal")
    away_animal = params.get("away_animal")

    # Substitute template variables in prompt
    if "{{" in prompt:
        if home_team:
            prompt = prompt.replace("{{home_team}}", str(home_team))
        if away_team:
            prompt = prompt.replace("{{away_team}}", str(away_team))
        if home_animal:
            prompt = prompt.replace("{{home_animal}}", str(home_animal))
        if away_animal:
            prompt = prompt.replace("{{away_animal}}", str(away_animal))

    try:
        if provider == "ai_studio":
            client = genai.Client(api_key=api_key)
        else:  # vertex_ai
            client = genai.Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=credentials,
            )

        # Prepare image parts if image_paths are provided
        image_parts = []
        if image_paths:
            print(f"🖼️ Processando {len(image_paths)} imagens")
            for i, img_path in enumerate(image_paths):
                print(f"📷 Processando imagem {i+1}/{len(image_paths)}: {img_path}")

                image_data = None
                if img_path.startswith(("http://", "https://")):
                    print(f"🌐 Baixando imagem de URL: {img_path}")
                    try:
                        resp = requests.get(img_path)
                        resp.raise_for_status()
                        image_data = resp.content
                    except Exception as e:
                        print(f"❌ Erro ao baixar imagem {i+1}: {e}")
                        continue
                elif os.path.exists(img_path):
                    print(f"📁 Lendo imagem local: {img_path}")
                    try:
                        with open(img_path, "rb") as image_file:
                            image_data = image_file.read()
                    except Exception as e:
                        print(f"❌ Erro ao ler imagem {i+1}: {e}")
                        continue
                else:
                    print(f"❌ Imagem não encontrada: {img_path}")
                    continue

                if image_data:
                    mime_type = "image/jpeg"
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

        # Decide contents based on available inputs
        parts = []
        if image_parts:
            parts.extend(image_parts)
        if prompt:
            parts.append(types.Part(text=prompt))

        if parts:
            contents = [types.Content(role="user", parts=parts)]
        else:
            contents = "Create a 30-second cheerful acoustic folk song."

        # Configure response format (for Lyria 3 Pro, WAV can be requested)
        config = None
        if response_format_param == "wav" or response_format_param == "audio/wav":
            config = types.GenerateContentConfig(
                response_modalities=["AUDIO", "TEXT"],
                response_format={"audio": {"mime_type": "audio/wav"}},
            )
            print("🔊 Formato de saída configurado para WAV")

        print(f"Gerando música com modelo {model_name}...")
        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config
        )

        parts_to_parse = []
        if hasattr(response, "parts") and response.parts:
            parts_to_parse = response.parts
        elif hasattr(response, "candidates") and response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            if hasattr(candidate, "content") and candidate.content and hasattr(candidate.content, "parts"):
                parts_to_parse = candidate.content.parts

        lyrics = []
        audio_data = None

        for part in parts_to_parse:
            if hasattr(part, "text") and part.text:
                lyrics.append(part.text)
            elif hasattr(part, "inline_data") and part.inline_data:
                audio_data = part.inline_data.data

        if audio_data:
            suffix = f".{response_format_param}"
            temp_file = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix
            )
            temp_path = temp_file.name
            temp_file.write(audio_data)
            temp_file.close()

            filename = os.path.basename(temp_path)
            lyrics_text = "\n".join(lyrics) if lyrics else None

            return {
                "status": True,
                "data": {
                    "audio_path": temp_path,
                    "filename": filename,
                    "audio_format": response_format_param.upper(),
                    "prompt": prompt,
                    "model": model_name,
                    "lyrics": lyrics_text,
                    "input_images_count": len(image_parts),
                    "input_image_paths": image_paths if image_paths else [],
                },
                "message": "Music generated successfully.",
            }
        else:
            # Check for block/safety issues
            if hasattr(response, "prompt_feedback") and response.prompt_feedback:
                if hasattr(response.prompt_feedback, "block_reason"):
                    return {
                        "status": False,
                        "message": f"Request blocked: {response.prompt_feedback.block_reason}",
                    }

            return {
                "status": False,
                "message": "No audio data was returned by the Lyria model.",
            }

    except Exception as e:
        return {"status": False, "message": f"Exception when generating music: {e}"}

