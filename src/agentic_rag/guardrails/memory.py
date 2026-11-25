"""Validação do que pode virar memória de longo prazo.

Uma memória vai para o system prompt de todas as conversas futuras do colaborador. Por
isso o bloqueio aqui é rígido: um texto injetado via documento que o agente tentasse
salvar seria persistido e reaplicado em todas as conversas.
"""

from agentic_rag.config import get_settings
from agentic_rag.guardrails.detection import find_injection_signals


class MemoryRejectedError(ValueError):
    """Memória recusada; a mensagem é devolvida ao agente como resultado da tool."""


def validate_memory(content: str) -> str:
    """Valida e normaliza um fato antes de gravar.

    Returns:
        O fato numa linha só, sem espaços sobrando.

    Raises:
        MemoryRejectedError: Vazio, longo demais, com marcação ou com cara de instrução.
    """
    fact = " ".join(content.split())  # uma linha só: quebras de linha imitam novos itens
    max_chars = get_settings().memory_max_chars
    if not fact:
        raise MemoryRejectedError("Memória recusada: o fato está vazio.")
    if len(fact) > max_chars:
        raise MemoryRejectedError(
            f"Memória recusada: o fato tem {len(fact)} caracteres (máximo {max_chars}). "
            "Guarde um fato curto sobre o colaborador."
        )
    # < > imitam as tags de dados externos; [ ] imitam os ids das memórias no prompt
    if any(char in fact for char in "<>[]"):
        raise MemoryRejectedError(
            "Memória recusada: fatos não podem conter marcação (<, >, [ ou ])."
        )
    if signals := find_injection_signals(fact):
        raise MemoryRejectedError(
            "Memória recusada: o texto parece uma instrução ao assistente "
            f"({', '.join(signals)}), não um fato sobre o colaborador."
        )
    return fact
