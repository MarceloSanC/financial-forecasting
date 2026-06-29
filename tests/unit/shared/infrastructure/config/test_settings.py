"""Unit test de `Settings` — defaults, override por env e validação de tipo.

Cobre os invariantes da Stage 1.5 sobre config:

- **I1/A1** — defaults declarados, incluindo o novo `mlflow_tracking_uri`.
- **I1/A1** — override por variável de ambiente (`MLFLOW_TRACKING_URI`,
  `PORT`).
- **C1** — tipo inválido (`PORT="abc"`) levanta `ValidationError` no boot.

Cada caso que mexe em env limpa o `lru_cache` de `get_settings` para não
vazar estado entre testes. Os casos de default/override constroem `Settings`
com `_env_file=None` para NÃO serem poluídos por um `.env` real presente na
worktree do desenvolvedor (o repo tem `.env` gitignored) — isolando o teste à
fronteira env/defaults declarada, não ao arquivo local.
"""

import pytest
from pydantic import ValidationError

from financial_forecasting.shared.infrastructure.config.settings import (
    Settings,
    get_settings,
)

_DEFAULT_PORT = 8000
_OVERRIDDEN_PORT = 9100


@pytest.fixture(autouse=True)
def _clean_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isola o ambiente: limpa o `lru_cache` e remove env vars relevantes.

    `MlflowTracker.__init__` chama `mlflow.set_tracking_uri`, que muta
    `os.environ["MLFLOW_TRACKING_URI"]` no processo. Como `Settings(_env_file=
    None)` ainda lê `os.environ`, esse efeito de OUTROS testes (ex.: o contract
    test do tracker) vazaria para os casos de default/validação aqui. Remover as
    env vars que estes testes asseguram (mais o `PORT`) antes de cada caso
    garante isolamento; `monkeypatch` restaura ao fim.
    """
    get_settings.cache_clear()
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    yield
    get_settings.cache_clear()


@pytest.mark.unit
def test_defaults_include_mlflow_tracking_uri() -> None:
    """A1: defaults declarados, incluindo o novo `mlflow_tracking_uri`."""
    settings = Settings(_env_file=None)

    assert settings.app_name == "financial_forecasting"
    assert settings.debug is False
    assert settings.host == "0.0.0.0"
    assert settings.port == _DEFAULT_PORT
    assert settings.log_level == "INFO"
    assert settings.mlflow_tracking_uri == "sqlite:///mlruns.db"


@pytest.mark.unit
def test_mlflow_tracking_uri_overridden_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A1: `MLFLOW_TRACKING_URI` no ambiente resolve `mlflow_tracking_uri`."""
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///custom/path.db")

    settings = Settings(_env_file=None)

    assert settings.mlflow_tracking_uri == "sqlite:///custom/path.db"


@pytest.mark.unit
def test_existing_field_overridden_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A1: campo existente (`PORT`) também é resolvido do ambiente e coercido."""
    monkeypatch.setenv("PORT", str(_OVERRIDDEN_PORT))

    settings = Settings(_env_file=None)

    assert settings.port == _OVERRIDDEN_PORT


@pytest.mark.unit
def test_invalid_port_type_raises_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """C1: tipo inválido (`PORT="abc"`) levanta `ValidationError` no boot."""
    monkeypatch.setenv("PORT", "abc")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.unit
def test_get_settings_is_cached() -> None:
    """`get_settings()` devolve a mesma instância (singleton por processo)."""
    first = get_settings()
    second = get_settings()

    assert first is second
