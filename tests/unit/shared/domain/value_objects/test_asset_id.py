"""Testes unitários do value object `AssetId` (issue #69 c, domínio puro).

`parse` é a regra única de "mesmo ativo": espaços das pontas, sufixo de bolsa no
primeiro `.` e caixa não mudam a identidade. O construtor direto só aceita a forma
canônica, e a forma canônica casa com o padrão de identificador de caminho.
"""

import dataclasses

import pytest

from financial_forecasting.shared.domain.value_objects.asset_id import AssetId


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["AAPL", "aapl", "Aapl", " AAPL ", "AAPL.US", "aapl.us", "AAPL.SA"])
def test_parse_maps_spellings_of_the_same_asset_to_one_identity(raw: str) -> None:
    assert AssetId.parse(raw) == AssetId("AAPL")


@pytest.mark.unit
def test_parse_keeps_digits_dash_and_underscore() -> None:
    assert AssetId.parse("petr4").value == "PETR4"
    assert AssetId.parse("brk-b").value == "BRK-B"
    assert AssetId.parse("x_y").value == "X_Y"


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    ["", "   ", ".US", "AA PL", "AAPL/..", "AA\nPL", "ÄAPL"],
    ids=["empty", "blank", "only-suffix", "inner-space", "path-sep", "newline", "non-ascii"],
)
def test_parse_rejects_what_cannot_be_a_path_identifier(raw: str) -> None:
    with pytest.raises(ValueError, match="asset_id"):
        AssetId.parse(raw)


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, 42, b"AAPL"], ids=["none", "int", "bytes"])
def test_parse_rejects_non_str(raw: object) -> None:
    with pytest.raises(ValueError, match="must be a str"):
        AssetId.parse(raw)


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["aapl", "AAPL.US"], ids=["lowercase", "suffix"])
def test_constructor_requires_canonical_form(raw: str) -> None:
    with pytest.raises(ValueError, match="canonical"):
        AssetId(raw)


@pytest.mark.unit
def test_str_is_the_value_and_vo_is_frozen() -> None:
    asset = AssetId("AAPL")
    assert str(asset) == "AAPL"
    with pytest.raises(dataclasses.FrozenInstanceError):
        asset.value = "MSFT"  # type: ignore[misc]
