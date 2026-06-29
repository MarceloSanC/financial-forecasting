"""Testes unitários do value object `Pagination` (domínio puro, sem I/O).

`Pagination` é o único VO de domínio transversal vivo hoje a 0% de cobertura
(Stage 1.2 §1, baseline F3). Cobre construção default, `offset`/`limit`,
validação em `__post_init__` (page/page_size) e imutabilidade (frozen). Sem
port nem fake — é VO puro, então o teste é direto sobre a classe.
"""

import dataclasses

import pytest

from financial_forecasting.shared.domain.value_objects.pagination import (
    MAX_PAGE_SIZE,
    Pagination,
)

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20


@pytest.mark.unit
def test_default_construction() -> None:
    """Sem argumentos, usa page=1 e page_size=20 (defaults do template)."""
    pagination = Pagination()

    assert pagination.page == DEFAULT_PAGE
    assert pagination.page_size == DEFAULT_PAGE_SIZE


@pytest.mark.unit
def test_offset_is_zero_on_first_page() -> None:
    """offset = (page-1)*page_size — primeira página não desloca."""
    assert Pagination(page=1, page_size=20).offset == 0


@pytest.mark.unit
def test_offset_computes_page_minus_one_times_page_size() -> None:
    """offset salta page_size registros por página anterior."""
    pagination = Pagination(page=3, page_size=25)
    expected_offset = (3 - 1) * 25

    assert pagination.offset == expected_offset


@pytest.mark.unit
def test_limit_is_alias_for_page_size() -> None:
    """limit é apenas um alias de page_size para legibilidade em SQL."""
    chosen_page_size = 42
    pagination = Pagination(page=2, page_size=chosen_page_size)

    assert pagination.limit == chosen_page_size
    assert pagination.limit == pagination.page_size


@pytest.mark.unit
def test_rejects_page_below_one() -> None:
    """page < 1 é inválido (não existe página zero ou negativa)."""
    with pytest.raises(ValueError, match="page deve ser >= 1"):
        Pagination(page=0)


@pytest.mark.unit
def test_rejects_page_size_below_one() -> None:
    """page_size < 1 é inválido (página vazia não faz sentido)."""
    with pytest.raises(ValueError, match="page_size deve estar entre"):
        Pagination(page_size=0)


@pytest.mark.unit
def test_rejects_page_size_above_max() -> None:
    """page_size acima do teto protege contra queries que varrem tudo."""
    with pytest.raises(ValueError, match="page_size deve estar entre"):
        Pagination(page_size=MAX_PAGE_SIZE + 1)


@pytest.mark.unit
def test_accepts_page_size_at_lower_boundary() -> None:
    """page_size == 1 é o limite inferior aceito (inclusivo).

    Boundary do lado de baixo: protege contra a mutação `1 < page_size`
    (que rejeitaria page_size=1). Sem este teste, trocar `<=` por `<` na
    borda inferior de `__post_init__` passa silenciosamente.
    """
    pagination = Pagination(page_size=1)

    assert pagination.page_size == 1


@pytest.mark.unit
def test_accepts_page_size_at_max_boundary() -> None:
    """page_size == MAX_PAGE_SIZE é o limite superior aceito (inclusivo)."""
    pagination = Pagination(page_size=MAX_PAGE_SIZE)

    assert pagination.page_size == MAX_PAGE_SIZE


@pytest.mark.unit
def test_is_frozen() -> None:
    """VO imutável: atribuir a um campo levanta FrozenInstanceError."""
    pagination = Pagination()

    with pytest.raises(dataclasses.FrozenInstanceError):
        pagination.page = 5  # type: ignore[misc]
