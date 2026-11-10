"""Tool de câmbio: cotação real de moedas via AwesomeAPI"""

import logging

import httpx
from langchain_core.tools import tool

from agentic_rag.config import get_settings

logger = logging.getLogger(__name__)


@tool
def get_exchange_rate(currency: str) -> str:
    """Busca a cotação atual de uma moeda estrangeira em reais (BRL).

    Use para converter despesas feitas no exterior antes de calcular o reembolso.

    Args:
        currency: Código ISO da moeda, ex.: "USD", "EUR", "GBP".
    """
    settings = get_settings()
    code = currency.strip().upper()
    url = f"{settings.exchange_api_url}/{code}-BRL"
    try:
        response = httpx.get(url, timeout=settings.exchange_timeout)
        response.raise_for_status()
        quote = response.json()[f"{code}BRL"]
    except httpx.HTTPStatusError as exc:
        logger.warning("Cotação indisponível para %s: %s", code, exc)
        return f"Moeda '{code}' não encontrada ou cotação indisponível."
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.error("Falha ao consultar a API de câmbio: %s", exc)
        return "Não foi possível consultar a cotação agora. Tente novamente."

    # "bid" = preço de compra, usado como taxa de conversão
    return f"1 {code} = {float(quote['bid']):.4f} BRL (cotação de {quote['create_date']})"
