"""Alinhamento da equivalência: seleção D7, interseção T∩ e agregação de seeds (Stage 8.2).

Regras puras sobre linhas em memória (doc §5.3 itens 2-4; concept 8.2 D7, D12 d):

- `window_starts` / `latest_window_points` — no lado anterior, um `target_timestamp` que
  aparece em duas janelas de teste sobrepostas fica com o ponto da janela **mais recente**
  (maior início de teste do `config_signature`), a regra `operationally_latest_fold` que o
  próprio anterior declara;
- `intersection` — T∩ por horizonte, na interseção exata dos `target_timestamp` presentes
  nos dois lados; o fold não é chave; T∩ vazio é registrado, não contornado;
- `mean_loss_by_timestamp` / `mean_over_seeds` — B-SEEDS: pinball do candidato pela média
  das perdas ponto a ponto entre seeds; PICP/MPIW pela média das coberturas/larguras por seed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence

Row = Mapping[str, object]


def window_starts(
    rows: Iterable[Row], *, window: str, horizon: str, timestamp: str
) -> dict[tuple[object, object], str]:
    """Início de teste (menor `timestamp`) de cada (janela, horizonte)."""
    starts: dict[tuple[object, object], str] = {}
    for row in rows:
        key = (row[window], row[horizon])
        value = str(row[timestamp])
        if key not in starts or value < starts[key]:
            starts[key] = value
    return starts


def latest_window_points[T: Row](
    rows: Sequence[T],
    *,
    point_key: Callable[[T], Hashable],
    window: str,
    horizon: str,
    timestamp: str,
) -> list[T]:
    """Um ponto por `point_key` (modelo, seed, horizonte, timestamp): o da janela mais recente.

    Raises:
        ValueError: duas linhas com a mesma chave na mesma janela (dedup ambíguo).
    """
    starts = window_starts(rows, window=window, horizon=horizon, timestamp=timestamp)
    chosen: dict[Hashable, tuple[str, T]] = {}
    for row in rows:
        start = starts[(row[window], row[horizon])]
        key = point_key(row)
        if key in chosen:
            if chosen[key][0] == start:
                raise ValueError(f"two rows for {key!r} in the same test window {start}")
            if chosen[key][0] > start:
                continue
        chosen[key] = (start, row)
    return [row for _, row in chosen.values()]


def intersection(
    prior: Mapping[int, Iterable[str]], new: Mapping[int, Iterable[str]]
) -> dict[int, tuple[str, ...]]:
    """T∩ por horizonte (ordenado); horizonte de um lado só ou sem ponto comum → vazio."""
    horizons = sorted(set(prior) | set(new))
    return {
        horizon: tuple(sorted(set(prior.get(horizon, ())) & set(new.get(horizon, ()))))
        for horizon in horizons
    }


def timestamps_by_horizon(
    rows: Iterable[Row], *, horizon: str, timestamp: str
) -> dict[int, set[str]]:
    """Os `target_timestamp` presentes por horizonte (o fold e o resto da linha não contam)."""
    found: dict[int, set[str]] = defaultdict(set)
    for row in rows:
        h = row[horizon]
        assert isinstance(h, int)
        found[h].add(str(row[timestamp]))
    return dict(found)


def mean_loss_by_timestamp(
    losses_by_seed: Mapping[object, Mapping[str, float]], timestamps: Sequence[str]
) -> dict[str, float]:
    """Perda do candidato por timestamp = média das perdas das seeds (B-SEEDS).

    Raises:
        ValueError: sem seed, ou seed sem algum dos `timestamps`.
    """
    if not losses_by_seed:
        raise ValueError("no seed to aggregate")
    out: dict[str, float] = {}
    for ts in timestamps:
        missing = [seed for seed, losses in losses_by_seed.items() if ts not in losses]
        if missing:
            raise ValueError(f"seeds {missing!r} have no point at {ts}")
        out[ts] = math.fsum(losses[ts] for losses in losses_by_seed.values()) / len(losses_by_seed)
    return out


def mean_over_seeds(values_by_seed: Mapping[object, float]) -> float:
    """Média entre seeds de uma grandeza por seed (PICP, MPIW — B-SEEDS).

    Raises:
        ValueError: sem seed.
    """
    if not values_by_seed:
        raise ValueError("no seed to aggregate")
    return math.fsum(values_by_seed.values()) / len(values_by_seed)
