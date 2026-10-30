# Optional LLM and actual execution mode

## Why
Users need a functional optional LLM connection for grounded answers and an unambiguous display of the actual embedding device after Auto selection. The removed browser-only fields never connected a model.

## What changes
Add server-persisted optional OpenAI-compatible and Anthropic chat settings, credential redaction, connection test, retrieval-first generated answers and failure fallback. Display active CPU/GPU/Hybrid with evidence and deployment device independently of requested settings.
