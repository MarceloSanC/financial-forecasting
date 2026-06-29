"""Unit test da hierarquia de exceções — foco em `DuplicateKeyError` (Stage 2.1).

`DuplicateKeyError` representa colisão de PK lógica em write append-only sem
`overwrite` (concept 2.1 D5/C1). É erro de **orquestração/estado**, logo deve
herdar de `ApplicationError` — e NÃO de `DomainError` nem ser um `ValueError`
cru. O contract test do `MedallionStore` (fake e real) levanta exatamente este
tipo; este teste blinda a posição da classe na hierarquia para que a paridade
fake↔real continue observável por um único `pytest.raises(DuplicateKeyError)`.
"""

import pytest

from financial_forecasting.shared.domain.exceptions.base import (
    ApplicationError,
    DomainError,
    DuplicateKeyError,
)


@pytest.mark.unit
def test_duplicate_key_error_is_application_error() -> None:
    """D5: `DuplicateKeyError` é `ApplicationError` (erro de orquestração)."""
    assert issubclass(DuplicateKeyError, ApplicationError)


@pytest.mark.unit
def test_duplicate_key_error_is_not_domain_error() -> None:
    """D5: NÃO é `DomainError` — colisão de PK não é violação de regra de negócio."""
    assert not issubclass(DuplicateKeyError, DomainError)


@pytest.mark.unit
def test_duplicate_key_error_carries_message() -> None:
    """A mensagem (montada por quem levanta) é preservada e é uma `Exception`."""
    exc = DuplicateKeyError("(bronze, candle): pk=(asset, timestamp) collisions=[...]")

    assert isinstance(exc, Exception)
    assert "candle" in str(exc)
