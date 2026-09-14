"""Exceções nomeadas do contrato dos ports de `modeling` (issue #84).

Os quatro ports do caminho confirmatório (`BaselineForecaster`,
`QuantileModelTrainer`, `TftTrainer`, `HyperparameterSearch`) declaravam
`Raises: ValueError` e só. Os adapters não traduziam nada: `LightGBMError`
(`Exception` direto), `MisconfigurationException` do Lightning (`Exception`
direto), `OptunaError` (`Exception` direto) e o que o `statsforecast`/`torch`
erguem atravessavam o port como tipo de infraestrutura — e o chamador não
distinguia "entrada inválida" (bug do chamador) de "a biblioteca explodiu"
(falha do backend). `docs/operational-evolution-policy.md` §4, invariante 2: *o
adapter captura exceções da lib de terceiros e as converte em exceções do domínio
antes de propagar* — a camada anticorrupção deste projeto fica AQUI, entre os
adapters e as libs que não controlamos.

Duas exceções, uma por natureza de contrato:

- **`ModelTrainingError`** — o backend de treino/estimação falhou (LightGBM,
  pytorch-forecasting/Lightning/torch, statsforecast). A original vai em
  `__cause__` (`raise ... from exc`), nunca se perde.
- **`HyperparameterSearchError`** — o backend de busca (Optuna) falhou numa
  operação do estudo (`ask`/`tell`/`fail`/`best_trial`).

O que NÃO é traduzido, de propósito: `ValueError` erguido pela **regra do
domínio/port** antes de tocar a lib (C1/C3/C4/C5 — entrada estruturalmente
inválida ou inviável, bug do chamador ou trial inviável), e `RuntimeError` de
**wiring** (`create_study` não chamado) — erro de programação, que deve propagar.

Ambas herdam de `DomainError` (raiz dos erros nomeáveis do sistema): são o
vocabulário do domínio para "o backend falhou", não `ValueError` cru.
"""

from __future__ import annotations

from financial_forecasting.shared.domain.exceptions.base import DomainError


class ModelTrainingError(DomainError):
    """O backend de treino/estimação falhou (lib de terceiros); original em `__cause__`."""


class HyperparameterSearchError(DomainError):
    """O backend de busca de hiperparâmetros falhou (lib de terceiros); original em `__cause__`."""
