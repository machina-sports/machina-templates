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
    api_base = params.get("api_base")
    api_key = params.get("api_key")
    model_name = params.get("model_name")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    try:
        llm_params = {"model": model_name, "api_key": api_key}
        if api_base:
            llm_params["client_options"] = {"api_endpoint": api_base}
        
        llm = ChatGoogleGenerativeAI(**llm_params)
        
    except Exception as e:
        print(f"[DEBUG] Exception creating model: {e}")
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

    try:
        client = genai.Client(api_key=api_key)

        # Prepare image parts if image_paths are provided
        image_parts = []
        if image_paths:
            print(f"🖼️ Processando {len(image_paths)} imagens")
            for i, img_path in enumerate(image_paths):
                print(f"📷 Processando imagem {i+1}/{len(image_paths)}: {img_path}")
                
                image_data = None
                if img_path.startswith(('http://', 'https://')):
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
                    if img_path.lower().endswith('.png'):
                        mime_type = "image/png"
                    elif img_path.lower().endswith('.gif'):
                        mime_type = "image/gif"
                    elif img_path.lower().endswith('.webp'):
                        mime_type = "image/webp"
                    
                    image_part = types.Part(
                        inline_data=types.Blob(
                            data=image_data,
                            mime_type=mime_type
                        )
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
                                    "input_images_count": len(image_parts),
                                    "input_image_paths": image_paths if image_paths else [],
                                },
                                "message": f"Image generated successfully using {len(image_parts)} input images.",
                            }
            else:
                return {"status": "error", "message": "No image was generated"}
        else:
            return {"status": "error", "message": "Error generating image"}

    except Exception as e:
        return {"status": "error", "message": f"Exception when generating image: {e}"}
