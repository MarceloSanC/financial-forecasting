"""Serviço de domínio: a POLÍTICA de emissão dos baselines (issue #66).

Domínio puro (stdlib-only — ADR 5.2.0001). Reúne, num único lugar, tudo o que
antes vivia duplicado entre `StatsforecastBaselineForecaster` (adapter) e
`FakeBaselineForecaster` (dublê): o despacho exaustivo pelas 5 famílias
canônicas, a janela condicionante de cada uma, a convenção flat-em-h, os guards
C1/C4/C5 e a ordem em que eles disparam.

**Por que isso é domínio e não adapter.** A conversa que o núcleo tem com o
mundo externo não é "preveja baselines" — é "estime os parâmetros do AR(1)".
Todas as fórmulas de emissão já eram serviços de domínio
(`quantile_grid_emission`/`baseline_statistics`); o que faltava mover era a
*política* que os orquestra. Enquanto ela morava nos dois lados, o contract
test parametrizado `[fake, real]` executava duas cópias da mesma regra e não
podia sustentar a proposição que um contract test existe para sustentar (o
dublê responde como o real responderia). Medido antes da extração: remover o
guard de monotonicidade estrita SÓ no adapter deixava
`test_baseline_forecaster_contract.py` inteiramente verde.

Três funções puras, na ordem em que o contrato as usa:

- `validate_structure` — pré-condições estruturais da chamada + C5 de entrada.
- `emit_decision` — despacho por família para UMA decisão.
- `emit_baseline_grids` — a composição das duas, com a estimação do AR(1)
  INJETADA. O estimador é o único ponto legítimo de divergência entre dublê e
  real (o *shortcut* de Meszaros): o adapter passa o fit do `statsforecast`,
  o fake passa os momentos stdlib. A ORDEM (validar → estimar uma vez sobre o
  train congelado → emitir por decisão) é ela própria parte da regra (I4/D2 do
  ADR 5.2.0002) e por isso mora aqui, não nos chamadores.

O tipo devolvido por decisão é estruturalmente o `GridByHorizon` do port
(`Mapping[int, tuple[float, ...]]`) — escrito por extenso porque o domínio não
importa da `application` (LAYOUT §3).
"""

from __future__ import annotations

import math
from statistics import fmean
from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.domain.services.baseline_statistics import (
    ar1_step_forecast,
    ewma_variance_path,
)
from financial_forecasting.features.modeling.domain.services.quantile_grid_emission import (
    degenerate_grid,
    gaussian_grid,
    sample_quantiles_type7,
)
from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
    BASELINE_FAMILIES,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from financial_forecasting.features.modeling.domain.value_objects.baseline_spec import (
        BaselineSpec,
    )


def validate_structure(
    returns: Sequence[float],
    train_end_idx: int,
    decision_indices: Sequence[int],
    horizons: Sequence[int],
) -> None:
    """Valida índices/horizontes e a finitude da janela condicionante (C5).

    Args:
        returns: série de retornos na grade densa de pregão (não-vazia).
        train_end_idx: último índice da partição train (fronteira de estimação).
        decision_indices: dias de decisão, estritamente crescentes e todos
            posteriores a `train_end_idx`.
        horizons: horizontes em dias de pregão (não-vazio, todos >= 1).

    Raises:
        ValueError: qualquer pré-condição estrutural violada, ou valor
            não-finito na janela condicionante mais larga da chamada (C5).
    """
    if not returns:
        raise ValueError("returns must be non-empty")
    if not 0 <= train_end_idx < len(returns):
        raise ValueError(f"train_end_idx must be in [0, {len(returns) - 1}]; got {train_end_idx}")
    if not decision_indices:
        raise ValueError("decision_indices must be non-empty")
    previous: int | None = None
    for idx in decision_indices:
        if not 0 <= idx < len(returns):
            raise ValueError(f"decision index {idx} out of range [0, {len(returns) - 1}]")
        if idx <= train_end_idx:
            raise ValueError(f"decision index {idx} must be after train_end_idx={train_end_idx}")
        if previous is not None and idx <= previous:
            raise ValueError("decision_indices must be strictly increasing")
        previous = idx
    if not horizons or any(h < 1 for h in horizons):
        raise ValueError(f"horizons must be non-empty and >= 1; got {tuple(horizons)}")
    # C5 (entrada): a janela condicionante mais larga da chamada é
    # returns[: max(decisions)+1]; não-finito ali é bug de dado, nunca emite.
    widest = max(decision_indices)
    if any(not math.isfinite(r) for r in returns[: widest + 1]):
        raise ValueError(
            "non-finite value in the conditioning window "
            f"returns[: {widest + 1}] — a deterministic baseline never emits (C5)"
        )


def emit_decision(  # noqa: PLR0913 — parâmetros coesos de uma decisão
    *,
    spec: BaselineSpec,
    returns: Sequence[float],
    train_end_idx: int,
    decision_idx: int,
    horizons: Sequence[int],
    quantile_levels: Sequence[float],
    ar1_params: tuple[float, float, float] | None,
) -> Mapping[int, tuple[float, ...]]:
    """Despacha a família e monta `horizon -> grade crua` para UMA decisão.

    Args:
        spec: spec canônica do baseline (família + parâmetros pré-registrados).
        returns: série de retornos já validada por `validate_structure`.
        train_end_idx: fronteira de estimação (I4).
        decision_idx: o dia de decisão desta emissão.
        horizons: horizontes pedidos.
        quantile_levels: grade densa comum do cohort.
        ar1_params: `(mu, phi, sigma2_eps)` estimados no train congelado —
            obrigatório para a família `ar1`, ignorado nas demais.

    Returns:
        `horizon -> grade crua` alinhada 1:1 a `quantile_levels`.

    Raises:
        ValueError: janela insuficiente (C1), variância condicionante zero, ou
            família fora do canônico (I7).
    """
    train = returns[: train_end_idx + 1]

    if spec.family == "zero_return":
        grid = degenerate_grid(value=0.0, levels=quantile_levels)
        return {h: grid for h in horizons}

    if spec.family == "historical_mean":
        grid = degenerate_grid(value=fmean(train), levels=quantile_levels)
        return {h: grid for h in horizons}

    if spec.family == "ar1":
        if ar1_params is None:
            # Erro de programação do chamador (não do dado). `ValueError` e não
            # `assert` porque esta é fronteira PÚBLICA de domínio e `assert`
            # evapora sob `python -O`.
            raise ValueError("ar1 emission requires ar1_params estimated on the frozen train")
        mu, phi, sigma2_eps = ar1_params
        last_return = returns[decision_idx]
        emission: dict[int, tuple[float, ...]] = {}
        for horizon in horizons:
            mean, std = ar1_step_forecast(
                mu=mu,
                phi=phi,
                sigma2_eps=sigma2_eps,
                last_return=last_return,
                horizon=horizon,
            )
            emission[horizon] = gaussian_grid(mean=mean, std=std, levels=quantile_levels)
        return emission

    if spec.family == "ewma_vol":
        assert spec.decay_lambda is not None  # garantido pelo VO (C3)
        sigma2 = ewma_variance_path(
            returns=returns[: decision_idx + 1], decay_lambda=spec.decay_lambda
        )[-1]
        if sigma2 <= 0.0:
            # Borda Checkpoint C: série toda-zero até a decisão => sigma2-hat = 0;
            # gaussian_grid exige std > 0 — erguer, não fabricar.
            raise ValueError(
                "ewma_vol conditioning window produced zero variance at decision "
                f"{decision_idx} (all-zero returns up to t) — refusing to emit a "
                "degenerate Gaussian scale"
            )
        grid = gaussian_grid(mean=0.0, std=math.sqrt(sigma2), levels=quantile_levels)
        return {h: grid for h in horizons}  # flat em h — RMTD [5.18]

    if spec.family == "historical_quantiles":
        assert spec.window is not None  # garantido pelo VO (C3)
        if decision_idx + 1 < spec.window:
            raise ValueError(
                f"historical_quantiles needs {spec.window} returns up to the decision; "
                f"decision {decision_idx} has only {decision_idx + 1} (C1)"
            )
        window_values = returns[decision_idx - spec.window + 1 : decision_idx + 1]
        grid = sample_quantiles_type7(values=window_values, levels=quantile_levels)
        return {h: grid for h in horizons}  # flat em h (incondicional)

    # I7 — dispatch exaustivo: família fora do canônico ergue (o VO já barra na
    # construção; este ramo blinda contra spec forjada/nova família sem adapter).
    raise ValueError(
        f"unknown baseline family {spec.family!r}; expected one of {BASELINE_FAMILIES} (I7)"
    )


def emit_baseline_grids(  # noqa: PLR0913 — parâmetros coesos do contrato de emissão
    estimate_ar1: Callable[[Sequence[float]], tuple[float, float, float]],
    *,
    spec: BaselineSpec,
    returns: Sequence[float],
    train_end_idx: int,
    decision_indices: Sequence[int],
    horizons: Sequence[int],
    quantile_levels: Sequence[float],
) -> Mapping[int, Mapping[int, tuple[float, ...]]]:
    """Emite `decisão -> horizonte -> grade crua` com a estimação INJETADA.

    A ordem é parte da regra e não do chamador: valida a estrutura ANTES de
    estimar (uma entrada estruturalmente inválida nunca chega ao estimador), e
    estima UMA vez sobre o train congelado `returns[: train_end_idx + 1]`
    (I4/D2 — ADR 5.2.0002), reusando os parâmetros em todas as decisões.

    Args:
        estimate_ar1: colaborador que devolve `(mu, phi, sigma2_eps)` do train.
            É o ÚNICO ponto de divergência legítima entre dublê e adapter real
            (fit `statsforecast` vs momentos stdlib); só é chamado quando a
            família é `ar1`.
        spec: spec canônica do baseline.
        returns: série de retornos na grade densa de pregão.
        train_end_idx: fronteira de estimação.
        decision_indices: dias de decisão, estritamente crescentes.
        horizons: horizontes em dias de pregão.
        quantile_levels: grade densa comum do cohort.

    Returns:
        `decision_idx -> horizon -> grade crua`, com TODA decisão pedida
        presente.

    Raises:
        ValueError: qualquer borda de `validate_structure`/`emit_decision`, ou
            o que o próprio `estimate_ar1` erguer (C1/C4).
    """
    series = tuple(float(r) for r in returns)
    validate_structure(series, train_end_idx, decision_indices, horizons)

    ar1_params = estimate_ar1(series[: train_end_idx + 1]) if spec.family == "ar1" else None
    return {
        decision_idx: emit_decision(
            spec=spec,
            returns=series,
            train_end_idx=train_end_idx,
            decision_idx=decision_idx,
            horizons=horizons,
            quantile_levels=quantile_levels,
            ar1_params=ar1_params,
        )
        for decision_idx in decision_indices
    }
