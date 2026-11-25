"""Guardrails contra prompt injection.

Princípio: todo conteúdo que não vem do colaborador nem das regras do agente (documentos,
respostas de APIs, memórias guardadas) é dado não confiável. Ele chega ao LLM envelopado
e marcado como dado, nunca como instrução.

Camadas (nenhuma é suficiente sozinha):
- untrusted: envelopa o conteúdo externo com um delimitador aleatório por chamada;
- detection: heurística que identifica texto com cara de instrução ao assistente;
- memory: valida o que pode virar memória de longo prazo (vai para todas as conversas);
- middleware: aplica o envelope em todo resultado de tool do agente.
"""
