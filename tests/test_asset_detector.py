import pytest
from src.asset_detector import find_assets

PATTERN = r"\b[A-Z]{4}(?:11|3|4)\b"


def test_finds_stock_on4():
    assert find_assets("Comprei PETR4 hoje", PATTERN) == {"PETR4"}


def test_finds_stock_on3():
    assert find_assets("Relatório da VALE3 Q3", PATTERN) == {"VALE3"}


def test_finds_fii():
    assert find_assets("FII MXRF11 distribuiu R$1,10", PATTERN) == {"MXRF11"}


def test_finds_multiple_assets():
    result = find_assets("PETR4 e VALE3 subiram; MXRF11 pagou dividendo", PATTERN)
    assert result == {"PETR4", "VALE3", "MXRF11"}


def test_no_assets_in_plain_text():
    assert find_assets("Este relatório não menciona nenhum ativo.", PATTERN) == set()


def test_partial_match_not_included():
    # PETR41 should NOT match PETR4 due to word boundary
    assert find_assets("código PETR41 inválido", PATTERN) == set()


def test_lowercase_text_is_uppercased():
    # Text is uppercased before matching
    assert find_assets("petr4 vale3 mxrf11", PATTERN) == {"PETR4", "VALE3", "MXRF11"}


def test_false_positive_excluded():
    from src.asset_detector import _FALSE_POSITIVES
    for fp in _FALSE_POSITIVES:
        result = find_assets(f"texto {fp} aqui", PATTERN)
        assert fp not in result, f"{fp} deveria ser filtrado como falso positivo"


def test_same_ticker_counted_once():
    assert find_assets("PETR4 PETR4 PETR4", PATTERN) == {"PETR4"}


def test_empty_text():
    assert find_assets("", PATTERN) == set()
