# Alexa Sports Narrator

Alexa skill que narra dados esportivos em tempo real usando templates Machina e síntese de voz.

## Visão Geral

Esta skill integra com Amazon Alexa para fornecer atualizações esportivas por voz em múltiplos esportes:
- **NFL**: Jogos, placares, estatísticas de times e jogadores
- **NBA**: Jogos de basquete e estatísticas
- **Soccer/Futebol**: Resultados de partidas e classificações
- **MLB, NHL**: Dados de baseball e hockey

## Recursos

- **Multi-Esporte**: NFL, NBA, Soccer, MLB, NHL via Sportradar
- **Linguagem Natural**: Respostas conversacionais geradas por LLM
- **Dados em Tempo Real**: Placares e estatísticas ao vivo
- **Personalização**: Preferências do usuário para times favoritos
- **Multi-Idioma**: Suporte para pt-BR e en-US

## Arquitetura

```
Alexa Device → Lambda Function → Machina Workflow → Alexa Response
                                        ↓
                                [Sportradar API]
                                        ↓
                                [LLM Generation]
```

## Estrutura de Arquivos

```
alexa-sports-narrator/
├── SKILL.md                          # Documentação da skill
├── README.md                         # Este arquivo
├── skill.yml                         # Definição da skill Machina
├── _install.yml                      # Configuração de instalação
├── alexa-model/                      # Interaction models Alexa
│   ├── en-US.json                   # Modelo em inglês
│   └── pt-BR.json                   # Modelo em português
├── lambda/                           # Lambda function
│   ├── lambda_function.py           # Handler principal
│   └── requirements.txt             # Dependências Python
├── workflows/                        # Workflows Machina
│   ├── alexa-sports-query.yml       # Consulta de esportes
│   ├── alexa-personalized-update.yml # Update personalizado
│   ├── alexa-save-favorite-team.yml # Salvar time favorito
│   └── prompts/
│       └── generate-alexa-response.yml # Prompt LLM
├── references/                       # Guias de referência
│   ├── setup.md
│   ├── intents.md
│   ├── workflows.md
│   └── lambda.md
└── schemas/                          # Schemas de dados
    ├── alexa-request.m
    ├── alexa-response.md
    └── sports-intents.md
```

## Setup Rápido

### Pré-requisitos

1. **Conta Amazon Developer**: https://developer.amazon.com
2. **Conta AWS**: Para Lambda function
3. **API Keys**:
   - Sportradar API (NFL, NBA, Soccer)
   - OpenAI API (para LLM)
   - Machina API

### Passo 1: Criar Alexa Skill

1. Acesse [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask)
2. Clique em **Create Skill**
3. Configure:
   - **Skill name**: Sports Narrator
   - **Default language**: English (US) ou Portuguese (BR)
   - **Choose a model**: Custom
   - **Choose a method**: Start from scratch
4. Clique em **Create skill**

### Passo 2: Configurar Interaction Model

1. No Alexa Developer Console, vá para **Build** > **Interaction Model** > **JSON Editor**
2. Cole o conteúdo de `alexa-model/en-US.json` (ou `pt-BR.json`)
3. Clique em **Save Model**
4. Clique em **Build Model**

### Passo 3: Deploy Lambda Function

#### Opção A: Deploy Manual via AWS Console

1. Acesse [AWS Lambda Console](https://console.aws.amazon.com/lambda)
2. Clique em **Create function**
3. Configure:
   - **Function name**: alexa-sports-narrator
   - **Runtime**: Python 3.11
   - **Architecture**: x86_64
4. Em **Code source**, faça upload do código:
   ```bash
   cd lambda/
   pip install -r requirements.txt -t .
   zip -r function.zip .
   ```
5. Faça upload do `function.zip`
6. Configure **Environment variables**:
   ```
   MACHINA_API_KEY=your_machina_api_key
   MACHINA_BASE_URL=https://api.machina.sports
   ```

#### Opção B: Deploy via AWS CLI

```bash
cd lambda/

# Instalar dependências
pip install -r requirements.txt -t .

# Criar pacote
zip -r function.zip .

# Criar função
aws lambda create-function \
  --function-name alexa-sports-narrator \
  --runtime python3.11 \
  --role arn:aws:iam::YOUR_ACCOUNT_ID:role/lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip \
  --environment Variables="{MACHINA_API_KEY=your_key,MACHINA_BASE_URL=https://api.machina.sports}"

# Adicionar permissão Alexa
aws lambda add-permission \
  --function-name alexa-sports-narrator \
  --statement-id alexa-skill-invoke \
  --action lambda:InvokeFunction \
  --principal alexa-appkit.amazon.com \
  --event-source-token your_skill_id
```

### Passo 4: Configurar Endpoint no Alexa

1. No Alexa Developer Console, vá para **Build** > **Endpoint**
2. Selecione **AWS Lambda ARN**
3. Cole o ARN da sua Lambda function (ex: `arn:aws:lambda:us-east-1:123456789:function:alexa-sports-narrator`)
4. Clique em **Save Endpoints**

### Passo 5: Configurar Secrets na Machina

Configure as API keys necessárias:

```bash
# Via Machina CLI
machina secret set SPORTRADAR_NFL_API_KEY "your_sportradar_nfl_key"
machina secret set SPORTRADAR_NBA_API_KEY "your_sportradar_nba_key"
machina secret set SPORTRADAR_SOCCER_API_KEY "your_sportradar_soccer_key"
machina secret set SDK_OPENAI_API_KEY "your_openai_key"
```

### Passo 6: Instalar Workflows Machina

```bash
# Na raiz do projeto machina-templates
machina install skills/alexa-sports-narrator
```

### Passo 7: Testar

1. No Alexa Developer Console, vá para **Test**
2. Ative **Test is enabled for this skill**
3. Digite ou fale: "Alexa, open sports narrator"
4. Tente comandos:
   - "What were the NFL scores today?"
   - "How are the Lakers doing?"
   - "My favorite team is the Chiefs"

## Comandos Disponíveis

### Inglês (en-US)

| Comando | Descrição |
|---------|-----------|
| "Alexa, open sports narrator" | Abre a skill |
| "What were the NFL scores today?" | Placar NFL de hoje |
| "How did the Chiefs do?" | Resultado de um time específico |
| "How are the Lakers doing this season?" | Estatísticas da temporada |
| "Give me my personalized sports update" | Update personalizado |
| "My favorite team is the Chiefs" | Define time favorito |

### Português (pt-BR)

| Comando | Descrição |
|---------|-----------|
| "Alexa, abrir narrador esportivo" | Abre a skill |
| "Quais foram os resultados da NFL hoje?" | Placar NFL de hoje |
| "Como foi o Flamengo?" | Resultado de um time específico |
| "Como está o Lakers nesta temporada?" | Estatísticas da temporada |
| "Me dê minha atualização esportiva" | Update personalizado |
| "Meu time favorito é o Flamengo" | Define time favorito |

## Desenvolvimento

### Estrutura dos Workflows

#### 1. alexa-sports-query.yml

Workflow principal para consultas esportivas:
- Recebe intent da Alexa
- Busca dados via Sportradar
- Gera resposta natural com LLM
- Retorna texto formatado para Alexa

#### 2. alexa-personalized-update.yml

Gera update personalizado baseado nos times favoritos do usuário:
- Carrega perfil do usuário
- Busca dados de cada time favorito
- Gera resposta consolidada

#### 3. alexa-save-favorite-team.yml

Salva times favoritos do usuário:
- Carrega perfil existente
- Adiciona novo time
- Salva perfil atualizado

### Modificar Respostas

Edite o prompt em `workflows/prompts/generate-alexa-response.yml` para customizar o tom e estilo das respostas.

### Adicionar Novos Esportes

1. Adicione connector do esporte em `workflows/alexa-sports-query.yml`
2. Adicione intent no interaction model (`alexa-model/*.json`)
3. Atualize Lambda handler em `lambda/lambda_function.py`

### Testing Local

```bash
# Testar workflow localmente
machina workflow run alexa-sports-query \
  --input '{"intent_name":"GetNFLScoresIntent","sport":"nfl","language":"en-US"}'

# Ver logs
machina logs workflow alexa-sports-query
```

## Troubleshooting

### Lambda Timeout (8 segundos)

Se a Lambda estourar timeout:
- Aumente memory da Lambda (configurações)
- Otimize workflows (reduza chamadas API)
- Use cache para dados frequentes

### Resposta Muito Longa

Alexa tem limite de ~90 segundos de fala:
- Ajuste prompt para respostas mais concisas
- Limite número de jogos retornados (atualmente 5)

### API Rate Limits

Sportradar free tier: 1000 req/month
- Implemente cache de respostas
- Use update incremental ao invés de full sync

### Erros de Certificação

Amazon rejeita skills com:
- Respostas muito longas
- Erros não tratados
- Invocations mal configuradas

## API Keys e Custos

### Sportradar (Free Tier)
- 1000 requests/month
- $0 até o limite
- Depois: ~$150/month por esporte

### OpenAI
- GPT-4o-mini: ~$0.15 / 1M tokens input
- ~$0.60 / 1M tokens output
- Estimado: $5-10/month para uso moderado

### AWS Lambda
- 1M requests free/month
- ~$0.20 por 1M requests depois
- Memória: Free tier geralmente suficiente

## Roadmap

- [ ] Adicionar áudio customizado com ElevenLabs
- [ ] Suporte para mais idiomas (es-ES, fr-FR)
- [ ] Integração com Fantasy Sports
- [ ] Notificações proativas de jogos
- [ ] Skill para Google Assistant
- [ ] Dashboard web para gerenciar favoritos

## Contribuindo

1. Fork o repositório
2. Crie uma branch: `git checkout -b feature/nova-funcionalidade`
3. Commit suas mudanças: `git commit -am 'Add nova funcionalidade'`
4. Push para a branch: `git push origin feature/nova-funcionalidade`
5. Abra um Pull Request

## Licença

MIT License - veja [LICENSE](../../LICENSE) para detalhes.

## Suporte

- **Issues**: https://github.com/machina-sports/machina-templates/issues
- **Documentação**: [SKILL.md](SKILL.md)
- **Discord**: https://discord.gg/machina-sports

## Autores

Criado pela equipe Machina Sports usando templates existentes:
- voice-chat-completion
- nfl-podcast-generator
- sportradar connectors
- elevenlabs TTS

---

**Feito com Machina Templates** 🎙️⚡
