"""Factories dos modelos da OpenAI (chat e embeddings)"""

from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langsmith import traceable
from langsmith.run_helpers import get_current_run_tree

from agentic_rag.config import get_settings


def _trace_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Tira o `self` (embeddings com a chave da API) dos inputs registrados no LangSmith."""
    return {k: v for k, v in inputs.items() if k != "self"}


def _trace_outputs(outputs: Any) -> dict[str, Any]:
    """Registra só o formato dos vetores (milhares de floats poluem o trace)."""
    vectors = outputs if outputs and isinstance(outputs[0], list) else [outputs]
    return {"vectors": len(vectors), "dimensions": len(vectors[0]) if vectors[0] else 0}


class TracedOpenAIEmbeddings(OpenAIEmbeddings):
    """OpenAIEmbeddings que aparece como run do tipo `embedding` no LangSmith.

    O LangChain não gera runs para embeddings sozinho, então cada chamada é envolvida
    em @traceable. Sem LANGSMITH_TRACING ligado, o decorator não faz nada.
    """

    def _tag_run(self) -> None:
        """Marca provedor e modelo no run atual (usados pelo LangSmith nos runs de embedding)."""
        run = get_current_run_tree()
        if run is not None:
            run.metadata.update({"ls_provider": "openai", "ls_model_name": self.model})

    @traceable(
        run_type="embedding",
        name="embed_query",
        process_inputs=_trace_inputs,
        process_outputs=_trace_outputs,
    )
    def embed_query(self, text: str) -> list[float]:
        self._tag_run()
        return super().embed_query(text)

    @traceable(
        run_type="embedding",
        name="embed_documents",
        process_inputs=_trace_inputs,
        process_outputs=_trace_outputs,
    )
    def embed_documents(self, texts: list[str], chunk_size: int | None = None) -> list[list[float]]:
        self._tag_run()
        return super().embed_documents(texts, chunk_size)


def get_chat_model() -> ChatOpenAI:
    """Cria o modelo de chat configurano no Settings"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        openai_api_key=settings.openai_api_key,
        timeout=30,
        max_retries=2,
    )


def get_embeddings() -> TracedOpenAIEmbeddings:
    """Cria o modelo de embeddings configurado no Settings (com trace no LangSmith)."""
    settings = get_settings()
    return TracedOpenAIEmbeddings(
        model=settings.embedding_model, openai_api_key=settings.openai_api_key
    )
