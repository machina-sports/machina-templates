# Frontend Integration Guide

Este guia explica como integrar o Machina Assistant com o frontend boilerplate.

## Configuração

O frontend já está configurado para fazer proxy das requisições para a API do Machina. Apenas certifique-se de que as variáveis de ambiente estão corretas:

```env
MACHINA_API_URL=http://localhost:5003  # ou sua URL do Machina
MACHINA_API_KEY=your-api-key-here
```

## Fluxo de Comunicação

```
Frontend → /api/assistant/stream/[agent] → Machina API → Agent → Workflows → Response
```

## Formato da Requisição

O frontend deve enviar para `/api/assistant/stream/machina-assistant-executor`:

```typescript
{
  "messages": [
    {
      "role": "user",
      "content": "Como funcionam os connectors?"
    }
  ],
  // Opcional: para continuar conversa existente
  "context-agent": {
    "thread_id": "previous-thread-id"
  }
}
```

## Formato da Resposta (NDJSON Stream)

O agent retorna um stream NDJSON com os seguintes tipos de eventos:

### 1. Start Event
```json
{
  "type": "start",
  "content": "Starting Machina Assistant...",
  "metadata": {
    "agent": "machina-assistant-executor"
  }
}
```

### 2. Workflow Start
```json
{
  "type": "workflow_start",
  "content": "machina-assistant-reasoning",
  "metadata": {
    "workflow": "machina-assistant-reasoning",
    "step": 1,
    "total": 3
  }
}
```

### 3. Status Update
```json
{
  "type": "status_update",
  "content": "Searching knowledge base...",
  "metadata": {}
}
```

### 4. Content (Resposta do LLM)
```json
{
  "type": "content",
  "content": "Connectors are the bridge between Machina and external services...",
  "metadata": {
    "chunk": true
  }
}
```

### 5. Workflow Complete
```json
{
  "type": "workflow_complete",
  "content": "machina-assistant-response",
  "metadata": {
    "workflow": "machina-assistant-response",
    "status": "executed"
  }
}
```

### 6. Done Event (Final)
```json
{
  "type": "done",
  "content": "",
  "metadata": {
    "state": {
      "thread_id": "thread-id-here",
      "response_text": "Full response text...",
      "suggestions": [
        "Can you show me an example?",
        "How do I create a custom connector?",
        "What about workflows?"
      ]
    }
  }
}
```

## Como o Frontend Deve Processar

### 1. Acumular Content Chunks

```typescript
let fullResponse = '';

// Para cada chunk do tipo "content"
if (chunk.type === 'content') {
  fullResponse += chunk.content;
  // Atualizar UI com texto parcial
  updateMessageUI(fullResponse);
}
```

### 2. Extrair Suggestions do Done Event

```typescript
if (chunk.type === 'done') {
  const suggestions = chunk.metadata?.state?.suggestions || [];
  const threadId = chunk.metadata?.state?.thread_id;
  
  // Mostrar suggestions como botões clicáveis
  displaySuggestions(suggestions);
  
  // Salvar thread_id para próxima mensagem
  storeThreadId(threadId);
}
```

### 3. Mostrar Status Updates

```typescript
if (chunk.type === 'status_update') {
  // Mostrar loading com mensagem
  showLoadingStatus(chunk.content);
}

if (chunk.type === 'workflow_start') {
  // Mostrar progresso (Step 1/3, etc.)
  showProgress(chunk.metadata.step, chunk.metadata.total);
}
```

## Exemplo Completo de Integração

```typescript
async function sendMessage(message: string, threadId?: string) {
  const body: any = {
    messages: [
      {
        role: 'user',
        content: message
      }
    ]
  };
  
  // Se há thread anterior, incluir para manter contexto
  if (threadId) {
    body['context-agent'] = { thread_id: threadId };
  }
  
  const response = await fetch('/api/assistant/stream/machina-assistant-executor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  
  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullResponse = '';
  let suggestions: string[] = [];
  let newThreadId: string | undefined;
  
  while (true) {
    const { done, value } = await reader!.read();
    if (done) break;
    
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    
    for (const line of lines) {
      if (!line.trim()) continue;
      
      try {
        const chunk = JSON.parse(line);
        
        switch (chunk.type) {
          case 'start':
            console.log('Stream started');
            break;
            
          case 'status_update':
            showStatus(chunk.content);
            break;
            
          case 'content':
            fullResponse += chunk.content;
            updateMessageUI(fullResponse);
            break;
            
          case 'done':
            suggestions = chunk.metadata?.state?.suggestions || [];
            newThreadId = chunk.metadata?.state?.thread_id;
            displaySuggestions(suggestions);
            break;
        }
      } catch (e) {
        console.error('Failed to parse chunk:', line, e);
      }
    }
  }
  
  return { fullResponse, suggestions, threadId: newThreadId };
}
```

## Componente UI Sugerido

```typescript
<div className="assistant-container">
  {/* Messages */}
  <div className="messages">
    {messages.map((msg, i) => (
      <div key={i} className={`message ${msg.role}`}>
        <div className="content">
          {msg.content}
        </div>
        {msg.role === 'assistant' && msg.suggestions && (
          <div className="suggestions">
            {msg.suggestions.map((suggestion, j) => (
              <button 
                key={j}
                onClick={() => sendMessage(suggestion)}
                className="suggestion-btn"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}
      </div>
    ))}
    
    {/* Loading status */}
    {isLoading && (
      <div className="status-message">
        {statusMessage}
      </div>
    )}
  </div>
  
  {/* Input */}
  <div className="input-area">
    <textarea
      value={input}
      onChange={(e) => setInput(e.target.value)}
      placeholder="Ask me anything about Machina..."
      onKeyPress={(e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleSend();
        }
      }}
    />
    <button onClick={handleSend}>Send</button>
  </div>
</div>
```

## Tratamento de Erros

```typescript
// Erro no stream
if (chunk.type === 'error') {
  showError(chunk.content);
  console.error('Stream error:', chunk.metadata);
}

// Erro HTTP
if (!response.ok) {
  const error = await response.json();
  showError(error.error || 'Failed to connect to assistant');
}

// Timeout
const timeout = setTimeout(() => {
  reader?.cancel();
  showError('Request timed out');
}, 60000); // 60 seconds
```

## Dicas de UX

1. **Loading States**: Mostre mensagens de status enquanto processa
   - "Analyzing your question..."
   - "Searching knowledge base..."
   - "Generating response..."

2. **Suggestions**: As sugestões devem ser clicáveis e enviar automaticamente

3. **Thread ID**: Salve o thread_id no localStorage ou estado para manter contexto

4. **Markdown**: A resposta vem em markdown, use um renderer como `react-markdown`

5. **Code Blocks**: Destaque código com syntax highlighting

6. **Scroll**: Auto-scroll para última mensagem ao receber conteúdo

## Testando

1. **Primeira mensagem** (cria novo thread):
```typescript
sendMessage("O que é Machina?")
```

2. **Follow-up** (usa thread existente):
```typescript
sendMessage("Me dê um exemplo", threadId)
```

3. **Nova conversa**:
```typescript
sendMessage("Como fazer deploy?") // Sem threadId = novo thread
```

## Debug

Para debug, log todos os chunks:

```typescript
console.log('[Assistant]', chunk.type, chunk.content);
```

Verifique especialmente:
- Se `content` chunks estão chegando
- Se `done` contém `response_text` e `suggestions`
- Se `thread_id` está sendo retornado

## Notas Importantes

- **Thread ID**: SEMPRE passe o thread_id para manter contexto da conversa
- **Suggestions**: São geradas pelo LLM e são relevantes ao contexto
- **Content Chunks**: Chegam incrementalmente, acumule para exibir
- **Timeout**: Configure timeout adequado (sugestão: 60s+)

