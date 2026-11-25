"""Detecção heurística de instruções embutidas em conteúdo externo (prompt injection).

É uma lista de padrões conhecidos, em português e inglês: pega ataques ingênuos, mas é
fácil de contornar. Serve para bloquear memórias suspeitas e para alertar (no log e no
envelope) sobre documentos suspeitos. A proteção principal é o envelope de untrusted.py.
"""

import re
import unicodedata

_PATTERNS: dict[str, str] = {
    # "ignore/desconsidere/esqueça as instruções/regras anteriores"
    "ignorar_instrucoes": (
        r"\b(ignor\w*|desconsider\w*|esque[cç]\w*|disregard|forget|override)\b"
        r".{0,40}\b(instru[cç]\w*|regras?|orienta[cç]\w*|prompt|instructions?|rules?)\b"
    ),
    # "a partir de agora você/responda...", "you are now..." ("a partir de agora" sozinho é
    # comum em fatos legítimos, ex.: "A partir de agora trabalha em Recife")
    "troca_de_papel": (
        r"\b(a partir de agora|de agora em diante|from now on)\b.{0,30}"
        r"\b(voc[eê]|you|responda|answer|aja|act|diga|say)\b"
        r"|\b(voc[eê] agora [eé]|you are now|act as|aja como|finja ser|pretend to be)\b"
    ),
    # "novas instruções:", "new instructions"
    "novas_instrucoes": r"\b(novas? instru[cç]\w*|new instructions?|instru[cç][oõ]es do sistema)\b",
    # pede o prompt do sistema
    "prompt_do_sistema": r"\b(system prompt|prompt do sistema|mensagem do sistema)\b",
    # marcadores de papel/turno de chat no meio do texto
    "marcador_de_papel": (
        r"(^|\n)\s*(system|assistant|sistema|assistente)\s*:"
        r"|<\|?(im_start|im_end|system|endoftext)\|?>"
        r"|\[/?(inst|system)\]"
    ),
    # tenta fechar ou abrir o envelope de dados externos
    "envelope_falso": r"</?\s*dados_externos",
    # manda o assistente usar ferramentas ou mexer na memória
    "comando_de_ferramenta": (
        r"\b(chame|execute|use|call|invoke)\b.{0,20}"
        r"\b(save_memory|update_memory|delete_memory|search_policies|convert_currency"
        r"|get_exchange_rate|ferramenta|tool)\b"
    ),
}

_COMPILED = {name: re.compile(pattern, re.IGNORECASE) for name, pattern in _PATTERNS.items()}


def _normalize(text: str) -> str:
    """Remove caracteres invisíveis e de formatação usados para esconder padrões."""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Cf")


def find_injection_signals(text: str) -> list[str]:
    """Nomes dos padrões de instrução embutida encontrados no texto (vazio se nenhum)."""
    normalized = _normalize(text)
    return [name for name, pattern in _COMPILED.items() if pattern.search(normalized)]
