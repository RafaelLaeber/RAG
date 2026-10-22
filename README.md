# Agentic RAG

RAG agêntico com memória de curto e longo prazo, construído com LangChain (LCEL), LangGraph, OpenAI e Astra DB.

## Stack

- **LLM e embeddings:** OpenAI (`gpt-6-luna`, `text-embedding-3-small`)
- **Vector store:** Astra DB
- **Orquestração:** LangChain (LCEL) e LangGraph
- **Configuração:** pydantic-settings

## Instalação

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Configuração

Copie `.env.example` para `.env` e preencha as chaves:

```bash
cp .env.example .env
```

## Desenvolvimento

```bash
pytest -m "not integration"   # testes unitários
ruff check .                  # lint
ruff format .                 # formatação
mypy src tests                # checagem de tipos
```
