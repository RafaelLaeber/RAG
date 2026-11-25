"""Escopo e confidencialidade: o que o colaborador pode pedir ao assistente.

As respostas fixas ficam aqui para o system prompt e o middleware usarem o mesmo texto.
A detecção de pedidos de prompt/instruções internas é heurística e conservadora: pega os
pedidos diretos sem chamar o LLM; os disfarçados ficam com a regra do system prompt.
"""

import re
import unicodedata

CONFIDENTIAL_REPLY = "Não posso informar esse dado."
OFF_TOPIC_REPLY = (
    "Só posso ajudar com assuntos da Órbita: políticas internas, reembolsos e despesas."
)

# Aplicados ao texto em minúsculas e sem acentos. Cada padrão exige um alvo claro (o
# prompt/as instruções do assistente), para não barrar perguntas legítimas como
# "quais são as instruções para pedir reembolso?".
_EXTRACTION_PATTERNS = [
    r"\bsystem\s*prompts?\b",
    r"\bprompts?\s+(do|de|da)\s+(sistema|assistente|agente|ia|bot|chat\w*)\b",
    r"\bprompts?\s+(interno|original|inicial|base|completo|oculto|secreto)s?\b",
    r"\b(seu|teu|seus|teus|your)\s+prompts?\b",
    r"\b(suas|tuas)\s+(instrucoes|regras|diretrizes|configuracoes|orientacoes)\b",
    r"\binstrucoes\s+(internas|do sistema|iniciais|originais|ocultas|secretas)\b",
    r"\b(instrucoes|regras|diretrizes)\s+(que\s+)?(voce|vc|tu)\s+(recebeu|segue|seguiu|tem)\b",
    r"\byour\s+(instructions|rules|guidelines)\b",
    r"\bmensage(m|ns)\s+(do|de)\s+sistema\b",
    r"\b(modo|mode)\s+(desenvolvedor|developer|dan|debug|admin|deus|god)\b",
    r"\b(repita|repeat|copie|imprima|print)\b.{0,30}\b(acima|above|anterior|previous)\b",
    # "ignore suas instruções", "esqueça as regras anteriores"
    r"\b(ignore|ignora|esqueca|desconsidere|disregard|forget)\b.{0,30}"
    r"\b((suas|tuas|your)\s+(instrucoes|regras|instructions|rules)"
    r"|(instrucoes|regras|prompt|instructions|rules)\s+(anteriores|acima|iniciais|originais"
    r"|do sistema|previous|above))\b",
]
_COMPILED = [re.compile(pattern) for pattern in _EXTRACTION_PATTERNS]


def _normalize(text: str) -> str:
    """Minúsculas, sem acentos e sem caracteres invisíveis."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(
        ch
        for ch in decomposed
        if not unicodedata.combining(ch) and unicodedata.category(ch) != "Cf"
    )


def is_prompt_extraction(text: str) -> bool:
    """Diz se a mensagem pede o prompt, as instruções internas ou tenta trocá-las."""
    normalized = _normalize(text)
    return any(pattern.search(normalized) for pattern in _COMPILED)
