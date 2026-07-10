"""Testes do serviço `deduplicate_operationally_latest` (domínio puro).

Cobrem o colapso de duplicatas mantendo o maior rank, a preservação de chaves
únicas, a ordem determinística (primeira aparição) e o `ValueError` em empate.
"""

from __future__ import annotations

from typing import NamedTuple

import pytest

from financial_forecasting.features.modeling.domain.services.operationally_latest_dedup import (
    deduplicate_operationally_latest,
)


class _Prediction(NamedTuple):
    """Registro OOS mínimo: chave de alinhamento + rank operacional + rótulo."""

    target_timestamp: str
    horizon: int
    fold_index: int  # rank operacional: fold mais recente = maior
    tag: str


def _key(p: _Prediction) -> tuple[str, int]:
    return (p.target_timestamp, p.horizon)


def _rank(p: _Prediction) -> int:
    return p.fold_index


@pytest.mark.unit
def test_keeps_highest_rank_per_key() -> None:
    """Duas predições do mesmo ponto: mantém a do fold mais recente."""
    older = _Prediction("2020-03-01", 1, fold_index=0, tag="fold0")
    newer = _Prediction("2020-03-01", 1, fold_index=1, tag="fold1")

    result = deduplicate_operationally_latest(
        [older, newer], alignment_key=_key, operational_rank=_rank
    )

    assert result == (newer,)


@pytest.mark.unit
def test_highest_rank_wins_regardless_of_input_order() -> None:
    """O vencedor é o de maior rank mesmo quando o mais recente vem primeiro."""
    newer = _Prediction("2020-03-01", 1, fold_index=2, tag="fold2")
    older = _Prediction("2020-03-01", 1, fold_index=1, tag="fold1")

    result = deduplicate_operationally_latest(
        [newer, older], alignment_key=_key, operational_rank=_rank
    )

    assert result == (newer,)


@pytest.mark.unit
def test_distinct_keys_are_all_kept() -> None:
    """Chaves distintas (timestamp/horizonte) sobrevivem todas."""
    a = _Prediction("2020-03-01", 1, fold_index=0, tag="a")
    b = _Prediction("2020-03-01", 7, fold_index=0, tag="b")  # mesmo ts, horizonte !=
    c = _Prediction("2020-03-02", 1, fold_index=0, tag="c")

    result = deduplicate_operationally_latest(
        [a, b, c], alignment_key=_key, operational_rank=_rank
    )

    assert set(result) == {a, b, c}


@pytest.mark.unit
def test_output_order_is_first_appearance_of_each_key() -> None:
    """A ordem de saída segue a 1ª aparição de cada chave (determinística)."""
    first = _Prediction("2020-03-02", 1, fold_index=0, tag="first")
    second = _Prediction("2020-03-01", 1, fold_index=0, tag="second")
    first_dup_newer = _Prediction("2020-03-02", 1, fold_index=5, tag="first-newer")

    result = deduplicate_operationally_latest(
        [first, second, first_dup_newer], alignment_key=_key, operational_rank=_rank
    )

    assert result == (first_dup_newer, second)


@pytest.mark.unit
def test_tie_on_rank_raises() -> None:
    """Mesma chave e mesmo rank é ambíguo -> ValueError (sem desempate silencioso)."""
    a = _Prediction("2020-03-01", 1, fold_index=3, tag="a")
    b = _Prediction("2020-03-01", 1, fold_index=3, tag="b")

    with pytest.raises(ValueError, match="ambiguous operationally-latest"):
        deduplicate_operationally_latest(
            [a, b], alignment_key=_key, operational_rank=_rank
        )


@pytest.mark.unit
def test_empty_input_returns_empty_tuple() -> None:
    """Sem registros, retorna tupla vazia."""
    result = deduplicate_operationally_latest(
        [], alignment_key=_key, operational_rank=_rank
    )

    assert result == ()
