"""`TftPanelGeometry` — estrutura do painel e elegibilidade de decisão do TFT (domínio).

Casa ÚNICA da regra que o port `TftTrainer` impõe sobre o painel sequencial que
atravessa a fronteira (concept 5.4 §4/§5; issue #75). Antes vivia duplicada, linha
a linha, no adapter `PfTftTrainer` e no fake `InMemoryTftTrainer` — o quarto caso da
patologia dos #66/#70/#71, num ponto mais sensível: a **elegibilidade** é *a*
decisão anti-vazamento do TFT (qual decisão pode entrar no treino e no monitor), e
uma cópia corrigida só de um lado manteria a suíte `[fake, real]` verde com o
adapter real vazando.

Três regras, stdlib-only, na ordem em que o adapter e o fake as aplicam:

- **`validate_structure` (C4)** — pré-condições da fronteira: `len(target) ==
  len(rows)`; largura de cada linha == `len(feature_names)`; `known_feature_names ⊆
  feature_names`; `max_horizon >= 1`; `horizons` não vazio e dentro de
  `1..max_horizon`; monitor não vazio (sem monitor não há seleção de época); as três
  faixas de decisão contíguas, crescentes e dentro do painel (`validate_contiguous`,
  C4/D5 — a biblioteca só expressa PISO de decisão, o teto vem de recortar o quadro,
  então um conjunto não-contíguo não seria honrável pelo adapter). Devolve o tamanho
  do painel.
- **`eligible_decisions` (I17)** — decisões com janela de contexto E decodificador
  completos: `t >= encoder_length - 1` (a janela é `[t-L+1, t]`, `t` inclusive) e
  `t + max_horizon <= panel_size - 1`.
- **`resolve_panel_geometry` (C3)** — a composição que os dois lados executam:
  valida a estrutura, filtra treino e monitor pela elegibilidade e ergue quando
  qualquer um esvazia ("nenhuma decisão de treino/monitor sobrou…"). Devolve
  `PanelGeometry` com o tamanho do painel e as faixas elegíveis — o adapter recorta
  os `TimeSeriesDataSet` com elas; o fake ajusta o normalizador e conta com elas.

Vocabulário próprio (painel sequencial com codificador/decodificador), distinto de
`quantile_training_validation` (matriz tabular, #71) e de `baseline_emission` (série
univariada causal, #66) — não se unificam sem inventar uma abstração que o domínio
não tem (não-objetivo da #75).

Pureza: importa SÓ stdlib. Mensagens de erro em PT com o marcador `(C3)`/`(C4)` no
fim — texto congelado pelo golden `test_tft_trainer_golden.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass(frozen=True)
class PanelGeometry:
    """Resultado de `resolve_panel_geometry`: painel validado + faixas elegíveis (I17)."""

    panel_size: int
    fitted_decisions: tuple[int, ...]
    monitored_decisions: tuple[int, ...]


def validate_contiguous(name: str, indices: Sequence[int], panel_size: int) -> None:
    """C4/D5 — `indices` é uma faixa contígua, crescente e dentro de `[0, panel_size)`.

    Contiguidade não é capricho: o adapter só expressa piso de decisão (a biblioteca
    não tem teto), e o teto vem de recortar o quadro. Aceitar aqui um conjunto que o
    adapter não honra produziria divergência fake<->real silenciosa justamente no
    monitor — onde ela significaria `calib` entrando na perda de validação.
    """
    for position, index in enumerate(indices):
        if not 0 <= index < panel_size:
            msg = f"{name}[{position}]={index} fora do painel de {panel_size} sessões (C4)"
            raise ValueError(msg)
        if position > 0 and index != indices[position - 1] + 1:
            msg = (
                f"{name} deve ser uma faixa contígua e crescente; "
                f"{indices[position - 1]} seguido de {index} (C4)"
            )
            raise ValueError(msg)


def eligible_decisions(
    indices: Sequence[int], *, encoder_length: int, max_horizon: int, panel_size: int
) -> tuple[int, ...]:
    """I17 — decisões com janela de contexto E decodificador completos.

    Janela completa sse `t >= encoder_length - 1` (a janela é `[t-L+1, t]`,
    terminando em `t` INCLUSIVE); decodificador completo sse
    `t + max_horizon <= panel_size - 1`.
    """
    return tuple(
        index
        for index in indices
        if index >= encoder_length - 1 and index + max_horizon <= panel_size - 1
    )


def validate_structure(  # noqa: PLR0913 — validação coesa da fronteira (C4)
    *,
    feature_names: Sequence[str],
    known_feature_names: Sequence[str],
    rows: Sequence[Sequence[float]],
    target: Sequence[float],
    train_decision_indices: Sequence[int],
    early_stop_decision_indices: Sequence[int],
    test_decision_indices: Sequence[int],
    max_horizon: int,
    horizons: Sequence[int],
) -> int:
    """C4 — valida a estrutura da fronteira do port e devolve o tamanho do painel."""
    if len(target) != len(rows):
        msg = f"len(target)={len(target)} != len(rows)={len(rows)} (C4)"
        raise ValueError(msg)
    width = len(feature_names)
    for position, row in enumerate(rows):
        if len(row) != width:
            msg = f"rows[{position}] tem {len(row)} colunas, esperado {width} (C4)"
            raise ValueError(msg)
    unknown_known = set(known_feature_names) - set(feature_names)
    if unknown_known:
        msg = f"known_feature_names não contido em feature_names: {sorted(unknown_known)} (C4)"
        raise ValueError(msg)
    if max_horizon < 1:
        msg = f"max_horizon deve ser >= 1, recebido {max_horizon} (C4)"
        raise ValueError(msg)
    if not horizons:
        msg = "horizons não pode ser vazio (C4)"
        raise ValueError(msg)
    out_of_range = [h for h in horizons if not 1 <= h <= max_horizon]
    if out_of_range:
        msg = f"horizons {out_of_range} fora de 1..{max_horizon} (C4)"
        raise ValueError(msg)
    if not early_stop_decision_indices:
        msg = "early_stop_decision_indices vazio — sem monitor não há seleção de época (C4)"
        raise ValueError(msg)

    panel_size = len(rows)
    for name, indices in (
        ("train_decision_indices", train_decision_indices),
        ("early_stop_decision_indices", early_stop_decision_indices),
        ("test_decision_indices", test_decision_indices),
    ):
        validate_contiguous(name, indices, panel_size)
    return panel_size


def resolve_panel_geometry(  # noqa: PLR0913 — composição da regra sobre a fronteira
    *,
    encoder_length: int,
    feature_names: Sequence[str],
    known_feature_names: Sequence[str],
    rows: Sequence[Sequence[float]],
    target: Sequence[float],
    train_decision_indices: Sequence[int],
    early_stop_decision_indices: Sequence[int],
    test_decision_indices: Sequence[int],
    max_horizon: int,
    horizons: Sequence[int],
) -> PanelGeometry:
    """Valida (C4), filtra treino/monitor pela elegibilidade (I17) e exige ambos (C3)."""
    panel_size = validate_structure(
        feature_names=feature_names,
        known_feature_names=known_feature_names,
        rows=rows,
        target=target,
        train_decision_indices=train_decision_indices,
        early_stop_decision_indices=early_stop_decision_indices,
        test_decision_indices=test_decision_indices,
        max_horizon=max_horizon,
        horizons=horizons,
    )
    fitted = eligible_decisions(
        train_decision_indices,
        encoder_length=encoder_length,
        max_horizon=max_horizon,
        panel_size=panel_size,
    )
    monitored = eligible_decisions(
        early_stop_decision_indices,
        encoder_length=encoder_length,
        max_horizon=max_horizon,
        panel_size=panel_size,
    )
    for label, decisions in (("treino", fitted), ("monitor", monitored)):
        if not decisions:
            msg = (
                f"nenhuma decisão de {label} sobrou após exigir janela de contexto de "
                f"{encoder_length} sessões e decodificador de {max_horizon} passos (C3)"
            )
            raise ValueError(msg)
    return PanelGeometry(
        panel_size=panel_size, fitted_decisions=fitted, monitored_decisions=monitored
    )
