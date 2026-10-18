"""Unit test do `SILVER_REGISTRY` (Stage 4.1, task-08; #164).

Prova (concept 4.1 A6/A7 / C6): o registry tem exatamente as 2 chaves
`("silver", <table>)` com escritor; cada valor é o `SilverTable` certo; `dim_run` é
`upsert` e `fact_oos_predictions` é `append-only`; as 3 tabelas sem escritor que saíram
na #164 são `KeyError`; lookup de par inexistente levanta `KeyError`.
"""

from __future__ import annotations

import pytest

from financial_forecasting.features.analytics_store.adapters.out.parquet.schemas.silver_registry import (  # noqa: E501
    SILVER_LAYER,
    SILVER_REGISTRY,
)

_EXPECTED_TABLES = 2
_EXPECTED_TABLE_NAMES = frozenset({"dim_run", "fact_oos_predictions"})
_REMOVED_TABLE_NAMES = ("fact_config", "fact_split_metrics", "fact_failures")


@pytest.mark.unit
def test_registry_has_exactly_the_written_silver_tables() -> None:
    """A7: o registry contém exatamente as 2 chaves ('silver', <table>) esperadas."""
    assert len(SILVER_REGISTRY) == _EXPECTED_TABLES
    assert set(SILVER_REGISTRY) == {(SILVER_LAYER, name) for name in _EXPECTED_TABLE_NAMES}


@pytest.mark.unit
def test_each_value_matches_its_key_name() -> None:
    """A7: cada SilverTable está sob a chave do seu próprio name."""
    for (layer, table), silver_table in SILVER_REGISTRY.items():
        assert layer == SILVER_LAYER
        assert silver_table.name == table


@pytest.mark.unit
def test_dim_run_is_upsert_others_append_only() -> None:
    """A6: dim_run é a única upsert; fact_oos_predictions é append-only."""
    assert SILVER_REGISTRY[(SILVER_LAYER, "dim_run")].update_policy == "upsert"
    for name in _EXPECTED_TABLE_NAMES - {"dim_run"}:
        assert SILVER_REGISTRY[(SILVER_LAYER, name)].update_policy == "append-only"


@pytest.mark.unit
@pytest.mark.parametrize("name", _REMOVED_TABLE_NAMES)
def test_tables_without_writer_are_not_registered(name: str) -> None:
    """#164: as 3 tabelas que nunca tiveram escritor não voltam ao registry."""
    with pytest.raises(KeyError):
        _ = SILVER_REGISTRY[(SILVER_LAYER, name)]


@pytest.mark.unit
def test_unknown_pair_raises_key_error() -> None:
    """C6: par (layer, table) fora do registry levanta KeyError (não engole)."""
    with pytest.raises(KeyError):
        _ = SILVER_REGISTRY[(SILVER_LAYER, "inexistente")]


@pytest.mark.unit
def test_unknown_layer_raises_key_error() -> None:
    """C6: layer fora de 'silver' também é KeyError (ex.: gold não está aqui)."""
    with pytest.raises(KeyError):
        _ = SILVER_REGISTRY[("gold", "dim_run")]
