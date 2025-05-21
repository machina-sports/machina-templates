from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from openai import OpenAI

import base64


def edit_image(request_data):

    headers = request_data.get("headers")

    params = request_data.get("params")

    api_key = headers.get("api_key", "")

    image_id = params.get("image_id", "")

    model_name = params.get("model", "")

    instruction = params.get("instruction", "")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    prompt = f"""
        Edite a imagem base fornecida para criar uma miniatura quadrada 1:1 para um card de jogador de futebol com estatísticas de desempenho.
        Use a máscara fornecida para definir as áreas editáveis e integre a foto do jogador naturalmente.

        Compreensão da Imagem Base:
        - Trabalhe com o template da imagem base fornecida como fundação
        - Use a máscara para identificar áreas que devem ser modificadas
        - Integre a foto do jogador fornecida apenas uma vez, na área designada à direita
        - Ao fundo do jogador, coloque uma marca d'água do time e o logo pequeno
        - A marca d'água deve ser pequena e não deve cobrir a foto do jogador
        
        Nome do Jogador:
        - Posicione o nome do jogador no topo do quadro a esquerda
        - Use fonte grande e clara
        - Garanta alta legibilidade
        - Use duas linhas se o nome for longo
        
        Estrutura do Layout (Seguindo o Template Base):
        - Mantenha a divisão: 70% esquerda para estatística, 30% direita para a foto do jogador
        - Área da direita: mantenha a foto do jogador pequena, ocupando no máximo 30% da altura
        - Não duplique ou repita a imagem do jogador em nenhum lugar
        - A foto do jogador deve ser pequena e compacta
        
        Integração da Estatística (Lado Esquerdo):
        - Apresente APENAS UM valor numérico usando: {instruction}
        - Mostre somente um índice e seu respectivo valor
        - Use fonte grande e clara para o valor
        - Exemplo: 4 Gols na partida, 3 escanteios cobrados
        - Dê enfaise ao valor numérico
        - Use somente um texto de descrição para o valor numérico
        
        Integração da Foto do Jogador (Lado Direito):
        - Posicione uma única foto do jogador, pequena e compacta
        - Mantenha a foto na parte superior direita
        - Não adicione elementos textuais ou descrições
        - Mantenha a proporção da foto do jogador pequena e contida

        Consistência Visual:
        - Mantenha o design minimalista e limpo
        - Foque na clareza do número e nome
        - Evite textos descritivos além do nome
        - Preserve a simplicidade do layout

        Correspondência de Cores:
        - Modifique a paleta de cores do template para se parecer com a cor do time
        - Mantenha alto contraste para o número e nome
        - Use cores sólidas e claras
        - Evite gradientes ou efeitos complexos

        Requisitos Obrigatórios:
        - Nome do jogador no topo
        - Apenas UM valor numérico com seu índice
        - Uma única foto do jogador, pequena e à direita
        - Mantenha o design limpo e minimalista

        Restrições:
        - Não adicione outros textos descritivos além do nome
        - Não duplique a foto do jogador
        - Não modifique áreas fora da máscara fornecida
        - Não adicione mais de um valor numérico
        """

    try:
        llm = OpenAI(api_key=api_key)

        result = llm.images.edit(
            model=model_name,
            image=[
                open(f"/work/images/card_model_example3_raw.png", "rb"),
                open(f"/work/images/card_model_example_player4.png", "rb")
            ],
            mask=open(f"/work/images/card_model_example4_raw.png", "rb"),
            prompt=prompt,
            size="1536x1024",
            quality="high",
        )

        image_base64 = result.data[0].b64_json

        image_bytes = base64.b64decode(image_base64)

        full_filepath = f"/work/images/{image_id}.webp"

        with open(full_filepath, 'wb') as f:

            f.write(image_bytes)

        final_filename = f"{image_id}.webp"

        result = {
            "final_filename": final_filename,
            "full_filepath": full_filepath
        }

        return {"status": True, "data": result, "message": "Image generated."}

    except Exception as e:
        return {"status": False, "message": f"Exception when generating image: {e}"} 


def generate_image(request_data):

    headers = request_data.get("headers")

    params = request_data.get("params")

    api_key = headers.get("api_key", "")

    image_id = params.get("image_id", "")

    model_name = params.get("model", "")

    instruction = params.get("instruction", "")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    prompt = f"""
        Create a 1:1 square image thumbnail for a soccer player card with performance statistics.

        Layout Structure:
        - Split the image into two main sections: left 60% for stats, right 40% for player/logo
        - Left section: Create a solid rectangular container for statistics display
        - Right section: Feature the player figure overlapping a watermarked team logo
        - Position a large jersey number beside the player on the right section
        
        Statistics Box (Left 60%):
        - Create a modern, structured layout for stats from: {instruction}
        - Organize stats vertically in the left container with clear spacing
        - Each stat should have a large number with a label underneath
        - Use consistent vertical rhythm for all statistics
        - Include subtle dividing lines between stat groups
        - Ensure high contrast between numbers and background
        
        Player and Logo Section (Right 40%):
        - Position the player figure overlapping a large, watermarked team logo
        - Place a bold, large jersey number beside the player
        - Player should appear to emerge from or interact with the team logo
        - Logo should be subtle enough to not compete with the player
        - Jersey number should be prominent but not overshadow the player

        Visual Style:
        - Use bold typography for statistics and jersey number
        - Create clear visual hierarchy: Stats > Player > Logo
        - Maintain professional, clean design with sharp edges
        - Apply subtle shadows or gradients for depth
        - Use team colors consistently throughout the design

        Typography Hierarchy:
        - Statistics Numbers: Large, bold, high-contrast
        - Stat Labels: Smaller, clear sans-serif
        - Jersey Number: Extra large, semi-transparent
        - All text must be crisp and easily readable

        Color Treatment:
        - Primary: Strong team color for the statistics box
        - Secondary: Complementary team color for accents
        - Background: Clean, gradient or solid color
        - Ensure sufficient contrast for all text elements

        Mandatory Elements:
        - Statistics box must occupy exactly 60% of the left side
        - Player must overlap with team logo in right section
        - Jersey number must be visible beside player
        - All stats must be contained within the left box
        - Maintain clean edges and professional finish

        Restrictions:
        - No sponsorship logos on jerseys
        - Never include the Sportingbet logo, word-mark, or symbol
        - Avoid recognizable player likenesses
        - Don't overflow statistics outside the left container
        """

    try:
        llm = OpenAI(api_key=api_key)

        result = llm.images.generate(
            model=model_name,
            prompt=prompt,
            size="1536x1024",
            quality="high",
        )

        image_base64 = result.data[0].b64_json

        image_bytes = base64.b64decode(image_base64)

        full_filepath = f"/work/images/{image_id}.webp"

        with open(full_filepath, 'wb') as f:

            f.write(image_bytes)

        final_filename = f"{image_id}.webp"

        result = {
            "final_filename": final_filename,
            "full_filepath": full_filepath
        }

        return {"status": True, "data": result, "message": "Image generated."}

    except Exception as e:
        return {"status": False, "message": f"Exception when generating image: {e}"} 
    

def invoke_embedding(params):

    api_key = params.get("api_key", "")

    model_name = params.get("model_name")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    try:
        llm = OpenAIEmbeddings(api_key=api_key, model=model_name)
        # llm = OpenAI(api_key=api_key)

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def invoke_prompt(params):

    api_key = params.get("api_key")

    model_name = params.get("model_name")

    if not api_key:
        return {"status": "error", "message": "API key is required."}

    if not model_name:
        return {"status": "error", "message": "Model name is required."}

    try:
        llm = ChatOpenAI(model=model_name, api_key=api_key)

    except Exception as e:
        return {"status": "error", "message": f"Exception when creating model: {e}"}

    return {"status": True, "data": llm, "message": "Model loaded."}


def transcribe_audio_to_text(params):
    """
    Transcribe an audio file to text using the new OpenAI Whisper transcription API.

    :param params: Dictionary containing the 'api_key' and 'audio-path' parameters.
    :return: Transcribed text or error message.
    """

    api_key = params.get("headers").get("api_key")
    file_items = params.get("params").get("audio-path", [])

    audio_file_path = file_items[0]

    try:

        llm = OpenAI(api_key=api_key)

        with open(audio_file_path, "rb") as audio_file:
            print(f"Transcribing file: {audio_file_path}")

            transcript = llm.audio.transcriptions.create(
              model="whisper-1",
              file=audio_file
            )

        return {"status": True, "data": transcript.text}

    except Exception as e:
        return {"status": False, "message": f"Exception when transcribing audio: {e}"} 
    