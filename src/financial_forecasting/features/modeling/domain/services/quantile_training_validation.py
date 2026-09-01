"""Serviço de domínio: pré-condições estruturais do treino quantílico (issue #71).

Domínio puro (stdlib-only). Contém a validação C4 do port `QuantileModelTrainer`
— o alinhamento da matriz de projeto com os rótulos e com as decisões de teste —
que até a issue #71 vivia em **duas cópias literalmente idênticas** (49 linhas,
`diff` vazio) no adapter `LightgbmQuantileTrainer` e no dublê
`FakeQuantileModelTrainer`. Era o maior bloco duplicado do repositório.

**Por que é domínio e não detalhe do LightGBM.** Nada aqui fala de booster,
`Dataset` ou iteração: fala de largura de linha, comprimento de vetor de rótulo
e paridade de conjuntos de horizonte. É regra de CONTRATO do port — a mesma
para qualquer implementação que o satisfaça, presente ou futura. Enquanto
morava nos dois lados, o contract test parametrizado `[fake, real]` executava
duas cópias da mesma validação. Medido antes da extração: remover `test_rows`
da checagem de largura SÓ no adapter deixava
`test_quantile_model_trainer_contract.py` inteiramente verde.

**Por que NÃO mora junto com `baseline_emission.validate_structure`.** As duas
são "validação estrutural de fronteira de port" e param aí. Não compartilham um
único predicado, vocabulário nem invariante: aquela fala de série temporal
univariada (causalidade `decisão > train_end_idx`, monotonicidade das decisões,
finitude da janela condicionante — C1/C5); esta fala de matriz tabular
(largura x nomes de feature, comprimento de rótulo x número de linhas, paridade
de horizontes — C4). Unificá-las exigiria inventar uma abstração de "coisa
validável" que não existe no domínio, e é exatamente o risco que a própria
issue #71 manda não correr ("unificar duas regras que só se parecem é pior que
duplicá-las"). Módulos separados porque são conceitos separados.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def validate_training_structure(  # noqa: PLR0913 — parâmetros coesos de uma chamada de treino
    *,
    feature_names: Sequence[str],
    train_rows: Sequence[Sequence[float]],
    train_labels_by_horizon: Mapping[int, Sequence[float]],
    early_stop_rows: Sequence[Sequence[float]],
    early_stop_labels_by_horizon: Mapping[int, Sequence[float]],
    test_rows: Sequence[Sequence[float]],
    test_decision_indices: Sequence[int],
) -> None:
    """C4: estrutura inconsistente ergue `ValueError` (paridade fake<->real).

    Args:
        feature_names: nomes das colunas da matriz de projeto (não-vazio); a
            cardinalidade define a largura exigida de TODA linha.
        train_rows: linhas de treino.
        train_labels_by_horizon: rótulos de treino por horizonte (não-vazio);
            o conjunto de chaves define os horizontes da chamada.
        early_stop_rows: linhas do monitor (não-vazio — sem monitor não há m*).
        early_stop_labels_by_horizon: rótulos do monitor, nos MESMOS horizontes
            do treino.
        test_rows: linhas de teste.
        test_decision_indices: índice de decisão de cada linha de teste, 1:1.

    Raises:
        ValueError: qualquer inconsistência estrutural, com a mensagem que
            identifica o bloco e a posição (C4).
    """
    if not feature_names:
        raise ValueError("feature_names must be non-empty (C4)")
    if not train_labels_by_horizon:
        raise ValueError("train_labels_by_horizon must be non-empty (C4)")
    if set(train_labels_by_horizon) != set(early_stop_labels_by_horizon):
        raise ValueError(
            "train and early_stop label horizons must match; got "
            f"{sorted(train_labels_by_horizon)} vs "
            f"{sorted(early_stop_labels_by_horizon)} (C4)"
        )
    if not early_stop_rows:
        raise ValueError("early_stop_rows must be non-empty — no monitor, no m* (C4)")
    if len(test_decision_indices) != len(test_rows):
        raise ValueError(
            f"test_decision_indices length {len(test_decision_indices)} != "
            f"test_rows length {len(test_rows)} (C4)"
        )
    width = len(feature_names)
    for block_name, rows in (
        ("train_rows", train_rows),
        ("early_stop_rows", early_stop_rows),
        ("test_rows", test_rows),
    ):
        for position, row in enumerate(rows):
            if len(row) != width:
                raise ValueError(
                    f"{block_name}[{position}] width {len(row)} != len(feature_names)={width} (C4)"
                )
    for block_name, rows_len, labels_by_horizon in (
        ("train", len(train_rows), train_labels_by_horizon),
        ("early_stop", len(early_stop_rows), early_stop_labels_by_horizon),
    ):
        for horizon, labels in labels_by_horizon.items():
            if len(labels) != rows_len:
                raise ValueError(
                    f"{block_name} labels for horizon {horizon} length "
                    f"{len(labels)} != rows length {rows_len} (C4)"
                )
