from google import genai

from google.genai import types

from langchain_google_genai import ChatGoogleGenerativeAI

from io import BytesIO

from PIL import Image

import base64
import os
import tempfile
import requests


def invoke_prompt(params):
    """Standard prompt invocation using langchain"""
    api_key = params.get("api_key")
    model_name = params.get("model_name")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    try:
        llm = ChatGoogleGenerativeAI(model=model_name, api_key=api_key)

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def invoke_image(request_data):
    """Generate images using Google's Gemini model with optional input image"""

    params = request_data.get("params")
    headers = request_data.get("headers")
    api_key = headers.get("api_key")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    # Get parameters
    image_path = params.get("image_path")
    prompt = params.get("prompt", "Um gato fofo brincando com uma bola de lã")
    model_name = params.get("model-name", "gemini-2.5-flash-image-preview")

    try:
        client = genai.Client(api_key=api_key)

        # Prepare image part if image_path is provided
        image_part = None
        if image_path:
            if image_path.startswith(('http://', 'https://')):
                # Download image from URL
                print(f"🌐 Baixando imagem de URL: {image_path}")
                try:
                    response = requests.get(image_path)
                    response.raise_for_status()
                    image_data = response.content
                    print(f"📊 Tamanho da imagem baixada: {len(image_data)} bytes")
                except Exception as e:
                    print(f"❌ Erro ao baixar imagem: {e}")
                    image_data = None
            elif os.path.exists(image_path):
                # Read local file
                print(f"📁 Lendo imagem local: {image_path}")
                with open(image_path, "rb") as image_file:
                    image_data = image_file.read()
                print(f"📊 Tamanho da imagem: {len(image_data)} bytes")
            else:
                print(f"❌ Imagem não encontrada: {image_path}")
                image_data = None
            
            if image_data:
                image_part = types.Part(
                    inline_data=types.Blob(
                        data=image_data,
                        mime_type="image/jpeg"
                    )
                )
                print("✅ Imagem preparada com sucesso")

        # Decide contents based on available inputs
        if image_part is not None or prompt is not None:
            parts = []
            if image_part is not None:
                parts.append(image_part)
                print("🖼️ Adicionando imagem aos parts")
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
        if image_part:
            print("✅ Usando imagem de entrada junto com o prompt")

        response = client.models.generate_content(model=model_name, contents=contents)

        if hasattr(response, "candidates") and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, "content") and candidate.content:
                    for part in candidate.content.parts:
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
                                },
                                "message": "Image generated successfully.",
                            }
            else:
                return {"status": "error", "message": "No image was generated"}
        else:
            return {"status": "error", "message": "Error generating image"}

    except Exception as e:
        return {"status": "error", "message": f"Exception when generating image: {e}"}
