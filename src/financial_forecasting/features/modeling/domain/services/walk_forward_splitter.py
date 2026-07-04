"""Serviço de domínio `WalkForwardSplitter` — folds walk-forward sem vazamento.

Domínio puro (stdlib-only). Dada a grade densa de dias de pregão do dataset (uma
linha por sessão — Stage 3.5) e um `ScopeSpec`, gera folds walk-forward de
**janela expansiva** (anchored), cada um com quatro partições disjuntas e
temporalmente ordenadas — `train`, `early_stop`, `calib`, `test` — separadas por
**purga + embargo medidos em dias de pregão** via
`TradingCalendar.shift_trading_days` (Stage 2.4).

Geometria por fold (ordem temporal):

```
[ TRAIN (ancorado em sessions[0]) ] gap [ EARLY_STOP ] gap [ CALIB ] gap [ TEST ]
```

- `gap = scope.max_horizon (purga) + embargo` sessões excluídas em cada fronteira.
  A purga = `max_horizon` impede que o alvo de horizonte `h ≤ max_horizon` de uma
  linha (realizado em `t + h`, ADR 4.3.0001) caia num bloco posterior; o embargo é
  o buffer de correlação serial (ADR 0.0.0018 regra 4; López de Prado 2018).
- Os `n_folds` blocos de `test` ladrilham a **cauda** da grade em blocos contíguos
  e disjuntos de `test_size` sessões; `train` sempre ancora em `sessions[0]` e
  cresce com o fold (janela expansiva — ADR 5.1.0001).
- O `calib` é o bloco **mais recente** antes do `test` (recency conformal —
  ADR 5.1.0002), intocado por early stopping.

Postura de fronteira (concept §6): grade inválida, janela insuficiente e
parâmetros inválidos **erguem `ValueError`** — sem clamp (erguer, não fabricar).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from financial_forecasting.features.modeling.domain.value_objects.fold_split import (
    FoldSplit,
)
from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date

    from financial_forecasting.features.modeling.domain.value_objects.scope_spec import (
        ScopeSpec,
    )
    from financial_forecasting.shared.application.ports.out.hasher import Hasher
    from financial_forecasting.shared.domain.services.trading_calendar import (
        TradingCalendar,
    )


class WalkForwardSplitter:
    """Gera folds walk-forward expansivos com purga+embargo e calib dedicado."""

    def __init__(self, calendar: TradingCalendar) -> None:
        self._calendar = calendar

    def split(  # noqa: PLR0913 — parâmetros coesos do protocolo de walk-forward
        self,
        sessions: Sequence[date],
        scope: ScopeSpec,
        *,
        n_folds: int,
        test_size: int,
        val_size: int,
        calib_size: int,
        embargo: int,
        hasher: Hasher,
    ) -> tuple[FoldSplit, ...]:
        """Particiona `sessions` em `n_folds` folds walk-forward expansivos.

        Args:
            sessions: grade densa de dias de pregão, ordenada estritamente.
            scope: escopo do cohort; `scope.max_horizon` fixa a largura da purga.
            n_folds: número de folds (blocos de test na cauda).
            test_size: sessões por bloco de test.
            val_size: sessões no early-stop.
            calib_size: sessões no calibration set dedicado.
            embargo: sessões de embargo além da purga (buffer serial).
            hasher: port de hashing canônico (injetado) para a `SplitFingerprint`.

        Returns:
            Tupla de `FoldSplit` (um por fold), do mais antigo ao mais recente.

        Raises:
            ValueError: parâmetros inválidos, grade inválida ou janela
                insuficiente para acomodar `train + gaps + val + calib + test`.
        """
        self._validate_params(n_folds, test_size, val_size, calib_size, embargo)
        grid = tuple(sessions)
        self._validate_grid(grid)

        total = len(grid)
        gap = scope.max_horizon + embargo

        if n_folds * test_size > total:
            raise ValueError(
                f"grid too short to tile {n_folds} test blocks of {test_size} "
                f"sessions: need {n_folds * test_size}, have {total}"
            )

        folds: list[FoldSplit] = []
        for fold_index in range(n_folds):
            test_start = total - (n_folds - fold_index) * test_size
            test_end = test_start + test_size
            calib_end = test_start - gap
            calib_start = calib_end - calib_size
            early_stop_end = calib_start - gap
            early_stop_start = early_stop_end - val_size
            train_end = early_stop_start - gap

            if train_end < 1:
                raise ValueError(
                    f"insufficient history for fold {fold_index}: an expanding train "
                    f"needs >= 1 session before early_stop, but 3 gaps of {gap} + "
                    f"val_size={val_size} + calib_size={calib_size} + "
                    f"test_size={test_size} leave train_end={train_end}. Provide more "
                    "sessions or smaller blocks/embargo."
                )

            train = grid[0:train_end]
            early_stop = grid[early_stop_start:early_stop_end]
            calib = grid[calib_start:calib_end]
            test = grid[test_start:test_end]

            # Resolução autoritativa da purga+embargo em DIAS DE PREGÃO: o 1º
            # elemento do bloco posterior deve estar exatamente `gap + 1` sessões à
            # frente do último do bloco anterior (gap sessões excluídas entre eles).
            self._assert_trading_day_gap(train[-1], early_stop[0], gap)
            self._assert_trading_day_gap(early_stop[-1], calib[0], gap)
            self._assert_trading_day_gap(calib[-1], test[0], gap)

            folds.append(
                self._build_fold(fold_index, train, early_stop, calib, test, hasher)
            )

        return tuple(folds)

    @staticmethod
    def _validate_params(
        n_folds: int, test_size: int, val_size: int, calib_size: int, embargo: int
    ) -> None:
        """Ergue `ValueError` em qualquer parâmetro de geometria inválido."""
        for name, value in (
            ("n_folds", n_folds),
            ("test_size", test_size),
            ("val_size", val_size),
            ("calib_size", calib_size),
        ):
            if value < 1:
                raise ValueError(f"{name} must be >= 1; got {value}")
        if embargo < 0:
            raise ValueError(f"embargo must be >= 0; got {embargo}")

    def _validate_grid(self, grid: tuple[date, ...]) -> None:
        """Valida grade não-vazia, estritamente crescente, de sessões contíguas.

        Cada elemento deve ser sessão (`is_session`) e cada par consecutivo deve
        ser adjacente no calendário (`next_session`), de modo que um deslocamento
        de N índices seja exatamente N dias de pregão (base da purga/embargo).
        """
        if not grid:
            raise ValueError("sessions must be a non-empty grid")
        previous: date | None = None
        for current in grid:
            if not self._calendar.is_session(current):
                raise ValueError(
                    f"grid contains a non-trading day: {current.isoformat()}"
                )
            if previous is not None:
                if current <= previous:
                    raise ValueError(
                        "sessions must be strictly increasing; got "
                        f"{previous.isoformat()} followed by {current.isoformat()}"
                    )
                if self._calendar.next_session(previous) != current:
                    raise ValueError(
                        "sessions must be a contiguous run of trading days; "
                        f"{current.isoformat()} is not the session after "
                        f"{previous.isoformat()}"
                    )
            previous = current

    def _assert_trading_day_gap(
        self, earlier: date, later: date, gap: int
    ) -> None:
        """Confere que `later` está `gap + 1` sessões à frente de `earlier`."""
        expected = self._calendar.shift_trading_days(
            earlier, gap + 1, direction="forward"
        )
        if expected != later:
            raise ValueError(
                f"purge+embargo gap mismatch: expected {gap} trading sessions "
                f"between {earlier.isoformat()} and {later.isoformat()}, but "
                f"shift lands on {expected.isoformat()}"
            )

    @staticmethod
    def _build_fold(  # noqa: PLR0913 — as 4 partições + índice + hasher compõem um fold
        fold_index: int,
        train: tuple[date, ...],
        early_stop: tuple[date, ...],
        calib: tuple[date, ...],
        test: tuple[date, ...],
        hasher: Hasher,
    ) -> FoldSplit:
        """Serializa as partições para ISO e compõe o `FoldSplit` com impressão."""
        train_iso = [day.isoformat() for day in train]
        early_stop_iso = [day.isoformat() for day in early_stop]
        calib_iso = [day.isoformat() for day in calib]
        test_iso = [day.isoformat() for day in test]
        fingerprint = SplitFingerprint.compute(
            hasher=hasher,
            train=train_iso,
            val=early_stop_iso,
            test=test_iso,
            calib=calib_iso,
        )
        return FoldSplit(
            fold_index=fold_index,
            train=tuple(train_iso),
            early_stop=tuple(early_stop_iso),
            calib=tuple(calib_iso),
            test=tuple(test_iso),
            fingerprint=fingerprint,
        )
