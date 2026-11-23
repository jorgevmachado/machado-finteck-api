import pytest

from app.domain.receipt.rules.validate import (
    normalize_code,
    normalize_name,
    validate_pattern,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  Itaú Unibanco  ", "Itaú Unibanco"),
        ("Nubank", "Nubank"),
        ("  a  ", "a"),
    ],
)
def test_normalize_name_strips_surrounding_whitespace(value, expected):
    assert normalize_name(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "\n\t"])
def test_normalize_name_rejects_blank_names(value):
    with pytest.raises(ValueError, match="Name cannot be empty"):
        normalize_name(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("itau_unibanco", "ITAU_UNIBANCO"),
        ("  nu_pagamentos  ", "NU_PAGAMENTOS"),
        ("CAIXA-ECONOMICA", "CAIXA-ECONOMICA"),
        ("A", "A"),
        ("9" * 64, "9" * 64),
    ],
)
def test_normalize_code_uppercases_and_keeps_allowed_characters(value, expected):
    assert normalize_code(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "_LEADING_UNDERSCORE",
        "-LEADING_DASH",
        "COM ESPACO",
        "ACENTUAÇÃO",
        "PONTO.PONTO",
        "A" * 65,
    ],
)
def test_normalize_code_rejects_codes_outside_the_allowed_shape(value):
    with pytest.raises(ValueError, match="Invalid institution code"):
        normalize_code(value)


def test_validate_pattern_compiles_case_insensitively():
    pattern = validate_pattern(r"pagador:\s*(?P<value>.+)")

    assert pattern.flags & 2  # re.IGNORECASE
    assert pattern.search("PAGADOR: Maria").group("value") == "Maria"


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_validate_pattern_rejects_blank_patterns(value):
    with pytest.raises(ValueError, match="Pattern cannot be empty"):
        validate_pattern(value)


@pytest.mark.parametrize(
    "value",
    [
        "(?P<value>",  # grupo sem fechamento
        "((((((((((((((((((((((((((((((((((((",  # parênteses desbalanceados
        "[unclosed",
        "(?P<1invalid>x)",
        "a{2,1}",
    ],
)
def test_validate_pattern_rejects_invalid_regular_expressions(value):
    with pytest.raises(ValueError, match="Invalid regular expression"):
        validate_pattern(value)


def test_validate_pattern_accepts_python_specific_syntax():
    """O backend aceita sintaxe que o JS rejeita — não validar regex no cliente."""
    pattern = validate_pattern(r"\A\s*(?P<value>[^\n]+)\s*\Z")

    assert pattern.search("  Maria  ").group("value").strip() == "Maria"