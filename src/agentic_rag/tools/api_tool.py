"""Tools de câmbio: cotação real de moedas via AwesomeAPI e conversão de valores para reais"""

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx
from langchain_core.tools import tool

from agentic_rag.config import get_settings

logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


class QuoteUnavailableError(Exception):
    """Cotação não obtida; a mensagem é devolvida ao agente como resultado da tool."""


@dataclass(frozen=True)
class Quote:
    """Cotação de uma moeda em reais."""

    code: str
    rate: Decimal  # BRL por 1 unidade da moeda, com a precisão devolvida pela API
    date: str


def fetch_quote(currency: str) -> Quote:
    """Consulta a cotação atual da moeda em BRL.

    Raises:
        QuoteUnavailableError: Moeda inexistente ou falha na API.
    """
    settings = get_settings()
    code = currency.strip().upper()
    url = f"{settings.exchange_api_url}/{code}-BRL"
    try:
        response = httpx.get(url, timeout=settings.exchange_timeout)
        response.raise_for_status()
        quote = response.json()[f"{code}BRL"]
        # "bid" = preço de compra, usado como taxa de conversão. Lido como texto para
        # o Decimal não herdar o erro de arredondamento do float.
        return Quote(code=code, rate=Decimal(str(quote["bid"])), date=str(quote["create_date"]))
    except httpx.HTTPStatusError as exc:
        logger.warning("Cotação indisponível para %s: %s", code, exc)
        raise QuoteUnavailableError(
            f"Moeda '{code}' não encontrada ou cotação indisponível."
        ) from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation) as exc:
        logger.error("Falha ao consultar a API de câmbio: %s", exc)
        raise QuoteUnavailableError(
            "Não foi possível consultar a cotação agora. Tente novamente."
        ) from exc


@tool
def get_exchange_rate(currency: str) -> str:
    """Busca a cotação atual de uma moeda estrangeira em reais (BRL).

    Use só para informar a cotação. Para converter um valor, use convert_currency.

    Args:
        currency: Código ISO da moeda, ex.: "USD", "EUR", "GBP".
    """
    try:
        quote = fetch_quote(currency)
    except QuoteUnavailableError as exc:
        return str(exc)
    return f"1 {quote.code} = {quote.rate} BRL (cotação de {quote.date})"


@tool
def convert_currency(amount: float, currency: str) -> str:
    """Converte um valor em moeda estrangeira para reais (BRL) com a cotação atual.

    Use sempre que precisar do valor em reais de uma despesa feita no exterior.
    A conta já vem pronta e arredondada em centavos: use o resultado, não refaça a conta.

    Args:
        amount: Valor na moeda estrangeira, ex.: 45.9.
        currency: Código ISO da moeda, ex.: "USD", "EUR", "GBP".
    """
    value = Decimal(str(amount))  # str() evita levar o erro binário do float para o Decimal
    if not value.is_finite() or value <= 0:
        return "O valor a converter deve ser maior que zero."
    try:
        quote = fetch_quote(currency)
    except QuoteUnavailableError as exc:
        return str(exc)
    total = (value * quote.rate).quantize(CENTS, rounding=ROUND_HALF_UP)
    return (
        f"{value} {quote.code} × {quote.rate} BRL/{quote.code} = {total} BRL "
        f"(cotação de {quote.date})"
    )
