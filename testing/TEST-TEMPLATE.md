# Testing: [nome-do-workflow]

Descrição breve do que está sendo testado (1 linha).

---

## Pré-requisitos

1. Template instalado no MCP:
```python
mcp__docker_localhost__get_local_template(
    template="agent-templates/[nome-template]",
    project_path="/app/machina-templates/agent-templates/[nome-template]"
)
```

2. Variáveis de ambiente configuradas:
   - `TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY` (ou outro necessário)

3. Workflow disponível (verificar):
```python
mcp__docker_localhost__search_workflow(
    filters={"name": "[nome-workflow]"},
    sorters=["created", -1],
    page_size=5
)
```

---

## Cenário 1: [Nome do Cenário]

**Objetivo**: [O que estamos validando - 1 linha].

### Executar workflow

```python
mcp__docker_localhost__execute_workflow(
    name="[nome-workflow]",
    context={
        "param1": "value1",
        "param2": "value2"
    }
)
```

### Resultado esperado

```json
{
  "status": "success",
  "outputs": {
    "output_field": "valor esperado",  // ✅ Validação específica
    "workflow-status": "executed"
  }
}
```

### Validação (opcional)

```python
# Código adicional para validar side effects (ex: documento criado)
result = mcp__docker_localhost__search_documents(
    filters={"name": "document-type"},
    sorters=["created", -1],
    page_size=1
)

# Validar campos do documento
assert result["data"]["data"][0]["value"]["field"] == "expected_value"
```

---

## Cenário 2: [Edge Case ou Cenário Alternativo]

**Objetivo**: [O que estamos testando quando algo é diferente].

### Executar workflow

```python
mcp__docker_localhost__execute_workflow(
    name="[nome-workflow]",
    context={
        "param1": "different_value"
    }
)
```

### Resultado esperado

```json
{
  "status": "success",
  "outputs": {
    "output_field": "valor alternativo",  // ✅ Comportamento diferente
    "workflow-status": "executed"
  }
}
```

---

## Cenário 3: [Erro ou Input Inválido]

**Objetivo**: Validar tratamento de erro quando [condição de erro].

### Executar workflow

```python
mcp__docker_localhost__execute_workflow(
    name="[nome-workflow]",
    context={
        "param1": None  # Input inválido
    }
)
```

### Resultado esperado

- ❌ Workflow falha com mensagem clara
- OU ✅ Workflow retorna erro tratado:

```json
{
  "status": "error",
  "message": "Mensagem de erro esperada"
}
```

---

## Checklist de Validação

### ✅ Funcionalidade Core
- [ ] Output principal retornado corretamente
- [ ] Workflow executa sem erros
- [ ] Side effects ocorrem (documentos criados, threads atualizados, etc.)

### ✅ Performance
- [ ] TTFT < 1.0s (para workflows com LLM)
- [ ] Workflow completa em tempo razoável

### ✅ Edge Cases
- [ ] Input inválido tratado corretamente
- [ ] Cenário de erro retorna mensagem clara
- [ ] Workflow não quebra em caso de falha parcial

---

## Debug: Ver Execuções do Workflow

```python
# Buscar últimas execuções
mcp__docker_localhost__search_workflow_executions(
    filters={"workflow_name": "[nome-workflow]"},
    sorters=["created", -1],
    page_size=10
)

# Ver detalhes de uma execução específica
mcp__docker_localhost__get_workflow_execution(
    execution_id="<execution_id>"
)
```

---

## Troubleshooting

### Erro: `[Erro comum 1]`
**Causa**: [Por que acontece]
**Solução**: [Como resolver]

### Erro: `[Erro comum 2]`
**Causa**: [Por que acontece]
**Solução**: [Como resolver]

### Performance ruim (TTFT > Xs)
- Verificar latência de rede para API externa
- Considerar trocar modelo LLM (ex: Groq para Gemini Flash)
- Reduzir tamanho do contexto

---

## Limpeza (Cleanup)

Após os testes, limpar documentos criados:

```python
# Deletar documentos de teste
mcp__docker_localhost__bulk_delete_documents(
    filters={
        "name": "[document-type]",
        "metadata.test": True  # Marcar docs de teste com metadata.test=True
    }
)
```

---

**Last Updated**: [YYYY-MM-DD]
**Workflow**: [nome-workflow]
**Purpose**: [Propósito breve do workflow em 1 linha]
