"""VO `ForecastRecord` — uma linha longa do silver já juntada ao `dim_run` (6.4).

Value object de domínio **frozen, stdlib-only** (concept 6.4 §4 "Domínio", D1; ADR
`6_4_0003`, `6_4_0004`). Uma linha de `fact_oos_predictions` (um nível de quantil de
um ponto de previsão) com a identidade do run: `model` é o `model_version` do fato, e
`seed`/`fold` vêm do `dim_run` do mesmo `run_id` (junção no use case — technical 6.4
§1). O `guardrail_applied` chega como `bool` (o int 0/1 do silver é convertido na
leitura).

Valida só a **forma** de cada campo, com mensagens que nomeiam o campo. As regras
entre linhas (uma observação por ponto, grade completa, `decision_idx` coerente com o
índice do realizado…) são do `SeriesAssembly` e viram achados, não exceção. A validade
da grade (níveis em (0, 1), simetria) e a finitude de `value_raw`/`value_guardrail`
são da `CoverageSeries`/`QuantileForecast`: aqui só o tipo.
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.features.evaluation.domain.value_objects._finite_number import (
    is_finite_number,
)
from financial_forecasting.features.evaluation.domain.value_objects._horizon import (
    validate_horizon,
)


def check_non_empty_str(value: object, *, field: str) -> None:
    """`str` não-vazia (identificadores e timestamps ISO dos VOs de entrada do gold)."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty str, got {value!r}")


def check_optional_seed(value: object) -> None:
    """`seed` do `dim_run`: `int` não-`bool` ou `None` (modelo determinístico)."""
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
        raise ValueError(f"seed must be an int or None, got {value!r}")


def check_optional_fold(value: object) -> None:
    """`fold` do `dim_run`: `str` ou `None` (nullable no schema)."""
    if value is not None and not isinstance(value, str):
        raise ValueError(f"fold must be a str or None, got {value!r}")


@dataclass(frozen=True)
class ForecastRecord:
    """Um nível de quantil de um ponto de previsão, com a identidade do run.

    Campos:
        run_id: id do run (hash hex do `dim_run`).
        model: `model_version` do fato.
        seed: seed do run (`None` em modelo determinístico).
        fold: fold do run (`None` quando o run não tem fold).
        horizon: rótulo do horizonte (int não-`bool` ≥ 1).
        decision_idx: índice de sessão da decisão no dataset (int não-`bool` ≥ 0).
        decision_timestamp, target_timestamp: timestamps ISO UTC.
        split: split do fato (só `"test"` entra na avaliação — regra do `SeriesAssembly`).
        quantile_level: nível do quantil (`float` finito).
        value_raw, value_guardrail: valores persistidos (`float`; finitude é da
            `CoverageSeries`).
        guardrail_applied: flag persistida (`bool`).

    Raises:
        ValueError: campo com tipo ou valor fora da forma acima, na construção.
    """

    run_id: str
    model: str
    seed: int | None
    fold: str | None
    horizon: int
    decision_idx: int
    decision_timestamp: str
    target_timestamp: str
    split: str
    quantile_level: float
    value_raw: float
    value_guardrail: float
    guardrail_applied: bool

    def __post_init__(self) -> None:
        """Forma de cada campo (mensagem nomeia o campo)."""
        for field in ("run_id", "model", "decision_timestamp", "target_timestamp", "split"):
            check_non_empty_str(getattr(self, field), field=field)
        check_optional_seed(self.seed)
        check_optional_fold(self.fold)
        validate_horizon(self.horizon, field="horizon")
        idx = self.decision_idx
        if isinstance(idx, bool) or not isinstance(idx, int) or idx < 0:
            raise ValueError(f"decision_idx must be an int >= 0, got {idx!r}")
        level = self.quantile_level
        if not isinstance(level, float) or not is_finite_number(level):
            raise ValueError(f"quantile_level must be a finite float, got {level!r}")
        for field in ("value_raw", "value_guardrail"):
            if not isinstance(getattr(self, field), float):
                raise ValueError(f"{field} must be a float, got {getattr(self, field)!r}")
        if type(self.guardrail_applied) is not bool:
            raise ValueError(f"guardrail_applied must be a bool, got {self.guardrail_applied!r}")
