import re
import logging

logger = logging.getLogger(__name__)

# Falsos positivos conhecidos: palavras comuns que batem no padrão mas não são tickers
_FALSE_POSITIVES: frozenset[str] = frozenset(
    [
        "PARA4",
        "ITEM3",
        "PAGE4",
        "FORM4",
        "TYPE3",
        "FILE4",
        "DATA3",
        "NOTE3",
        "NOTA3",
    ]
)


def find_assets(text: str, pattern: str) -> set[str]:
    """Return unique tickers found in *text* using *pattern*."""
    tickers: set[str] = set()
    for m in re.finditer(pattern, text.upper()):
        ticker = m.group(0)
        if ticker not in _FALSE_POSITIVES:
            tickers.add(ticker)

    if tickers:
        logger.debug("Ativos encontrados: %s", tickers)
    return tickers
