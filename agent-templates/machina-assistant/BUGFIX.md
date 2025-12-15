# Bug Fix: Thread Document Loading Error

## Problem

When querying the Machina Assistant with deployment questions (e.g., "How Machina deployment works"), the system correctly identified the intent (`is_deployment_question: true`) but failed with the error:

```
Error: 'list' object has no attribute 'replace'
```

This error occurred in the `load-thread-document` task when processing the `messages` output.

## Root Cause

The issue was caused by variable name conflicts and inconsistent handling of message arrays across workflows:

1. **Variable Name Collision**: The output variable `messages` from `load-thread-document` was conflicting with workflow state management
2. **Inconsistent Message Handling**: The `input_message` parameter (which is an array) was being passed directly to prompts that expected structured message objects
3. **Missing Filter**: The `load-thread-document` search was missing the `name: "'thread'"` filter in `assistant-response.yml`

## Changes Made

### 1. `workflows/assistant-reasoning.yml`

**Changed output variable names to avoid conflicts:**
```yaml
# BEFORE
outputs:
  messages: $.get('documents')[0].get('value', {}).get('messages', []) if len($.get('documents', [])) > 0 else []

# AFTER  
outputs:
  messages_loaded: $.get('documents')[0].get('value', {}).get('messages', []) if len($.get('documents', [])) > 0 else []
```

**Updated prompt inputs to use the renamed variable:**
```yaml
# BEFORE
inputs:
  _1-conversation-history: $.get('messages', [])[-5:]
  _2-user-question: $.get('input_message')

# AFTER
inputs:
  _1-conversation-history: $.get('messages_loaded', [])[-5:]
  _2-user-messages: $.get('input_message')
```

### 2. `workflows/assistant-response.yml`

**Added missing filter and renamed output variable:**
```yaml
# BEFORE
filters:
  document_id: $.get('document_id')
outputs:
  messages: $.get('documents')[0].get('value', {}).get('messages', []) if len($.get('documents', [])) > 0 else []

# AFTER
filters:
  name: "'thread'"
  document_id: $.get('document_id')
outputs:
  thread_messages: $.get('documents')[0].get('value', {}).get('messages', []) if len($.get('documents', [])) > 0 else []
```

**Updated prompt inputs to extract message content correctly:**
```yaml
# BEFORE
inputs:
  conversation_history: $.get('messages', [])[-5:]
  user_question: $.get('messages', [])[-1] if len($.get('messages', [])) > 0 else []

# AFTER
inputs:
  conversation_history: $.get('thread_messages', [])[-5:]
  user_question: $.get('thread_messages', [])[-1].get('content', '') if len($.get('thread_messages', [])) > 0 else ''
```

### 3. `prompts/assistant-reasoning.yml`

**Updated instruction to clarify input structure:**
```yaml
# BEFORE
instruction: |
  Analyze the conversation history and current message to understand what the user needs help with.

# AFTER
instruction: |
  Review the conversation history (_1-conversation-history) and the new user messages (_2-user-messages) to understand what the user needs help with.
  The user messages may contain one or more messages - analyze all of them together to understand the complete question or request.
```

## Why This Fixes the Issue

1. **Eliminates Name Conflicts**: By using unique variable names (`messages_loaded`, `thread_messages`) instead of generic `messages`, we avoid conflicts with the workflow state management system

2. **Proper Type Handling**: Extracting `.get('content', '')` from message objects ensures we're passing strings to prompts, not complex objects or arrays

3. **Consistent Filtering**: Adding the `name: "'thread'"` filter ensures we're querying the correct document type

4. **Better Input Structure**: Renaming `_2-user-question` to `_2-user-messages` and updating the prompt instruction makes it clear that the input can be multiple messages

## Testing

To test the fix, send a deployment-related question to the assistant:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "How does Machina deployment work?"
    }
  ]
}
```

Expected behavior:
1. ✅ `assistant-reasoning` workflow should identify `is_deployment_question: true`
2. ✅ `load-thread-document` should load/create thread without errors
3. ✅ `search-knowledge-base` should find relevant documentation from `deployment-guide.md`
4. ✅ `assistant-response` should generate a helpful response with deployment information

## Related Files

- `workflows/assistant-reasoning.yml`
- `workflows/assistant-response.yml`
- `prompts/assistant-reasoning.yml`
- `knowledge/deployment-guide.md`
