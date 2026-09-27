"""Value object `CohortGeometry` — geometria walk-forward do cohort confirmatório.

Frozen, domínio puro (stdlib-only). Declara os cinco parâmetros que o
`WalkForwardSplitter` (5.1) recebe e deriva deles, sem I/O, três fatos que o
cohort da Stage 5.5 precisa antes de treinar:

- **`exploratory()`** — a geometria dos sweeps: um único fold cujo bloco de teste
  cobre toda a cauda OOS confirmatória. Como o splitter ladrilha os testes a
  partir do fim da grade, o treino e o early_stop desse fold coincidem com os do
  fold 0 confirmatório: a busca de hiperparâmetros nunca vê dado que o
  confirmatório pontua (D2; ADR 5.5.0002).
- **`expected_prediction_rows()`** — linhas de predição que um run persiste num
  fold: cada decisão de teste, por horizonte e por nível, menos as decisões do ÚLTIMO
  fold cujo alvo `t + h` cai além do painel (o persister as pula). Base da
  verificação por contagem da retomada (ADR 5.5.0003) e do `verify`.
- **`fold0_train_size()` / `fits()`** — tamanho do treino do fold 0 e a recusa de
  uma geometria que não cabe no grid útil (`GeometryDoesNotFitError`).
"""

from __future__ import annotations

from dataclasses import dataclass

from financial_forecasting.features.modeling.domain.exceptions.cohort import (
    GeometryDoesNotFitError,
)

_GAPS_BEFORE_TEST = 3  # train | gap | early_stop | gap | calib | gap | test


@dataclass(frozen=True)
class CohortGeometry:
    """Parâmetros do walk-forward do cohort (os mesmos do `WalkForwardSplitter.split`).

    Attributes:
        n_folds: blocos de teste ladrilhados na cauda.
        test_size: sessões por bloco de teste.
        val_size: sessões de early_stop por fold.
        calib_size: sessões de calibração dedicada por fold.
        embargo: sessões de embargo além da purga (`gap = max_horizon + embargo`).
    """

    n_folds: int
    test_size: int
    val_size: int
    calib_size: int
    embargo: int

    def __post_init__(self) -> None:
        """Tamanhos positivos e embargo não negativo."""
        for name in ("n_folds", "test_size", "val_size", "calib_size"):
            value = getattr(self, name)
            if value < 1:
                raise ValueError(f"CohortGeometry.{name} must be >= 1; got {value}")
        if self.embargo < 0:
            raise ValueError(f"CohortGeometry.embargo must be >= 0; got {self.embargo}")

    @property
    def oos_sessions(self) -> int:
        """Sessões de teste somadas de todos os folds (a cauda OOS)."""
        return self.n_folds * self.test_size

    def exploratory(self) -> CohortGeometry:
        """Geometria dos sweeps: 1 fold cujo teste é toda a cauda OOS confirmatória."""
        return CohortGeometry(
            n_folds=1,
            test_size=self.oos_sessions,
            val_size=self.val_size,
            calib_size=self.calib_size,
            embargo=self.embargo,
        )

    def expected_prediction_rows(
        self, *, fold_index: int, horizons: tuple[int, ...], n_levels: int
    ) -> int:
        """Linhas de predição que um run persiste no fold `fold_index`.

        Cada decisão de teste gera `n_levels` linhas por horizonte, exceto as
        decisões cujo alvo `t + h` cai além do painel — o persister as pula. Com
        os testes ladrilhados a partir do fim da grade, a decisão do fold `i` na
        posição `k` do bloco fica a `e = (n_folds - i) * test_size - k` sessões do
        fim, e tem alvo sse `h < e`: no último fold perdem-se `h` decisões; se
        `h > test_size`, o penúltimo também perde. Horizontes repetidos são erro
        (o persister os colapsa por chave).
        """
        if not 0 <= fold_index < self.n_folds:
            raise ValueError(f"fold_index must be in [0, {self.n_folds}); got {fold_index}")
        if not horizons or any(h < 1 for h in horizons):
            raise ValueError(f"horizons must be non-empty positive integers; got {horizons}")
        if len(set(horizons)) != len(horizons):
            raise ValueError(f"horizons must be unique; got {horizons}")
        if n_levels < 1:
            raise ValueError(f"n_levels must be >= 1; got {n_levels}")
        farthest = (self.n_folds - fold_index) * self.test_size
        decisions = sum(max(0, min(self.test_size, farthest - h)) for h in horizons)
        return decisions * n_levels

    def expected_runs(self, *, runs_per_fold: int) -> int:
        """Runs que uma unidade grava: um por fold e por modelo da unidade.

        TFT e GBM: `runs_per_fold = 1`; baselines: `runs_per_fold = 5` (uma spec
        por família) — base da classificação por contagem (I7).
        """
        if runs_per_fold < 1:
            raise ValueError(f"runs_per_fold must be >= 1; got {runs_per_fold}")
        return self.n_folds * runs_per_fold

    def fold0_train_size(self, *, n_sessions: int, max_horizon: int) -> int:
        """Sessões de treino do fold 0 (o menor treino do cohort) num grid de `n_sessions`."""
        gap = max_horizon + self.embargo
        return (
            n_sessions
            - self.oos_sessions
            - self.calib_size
            - self.val_size
            - _GAPS_BEFORE_TEST * gap
        )

    def fits(self, *, n_sessions: int, max_horizon: int) -> None:
        """Recusa geometria em que o fold 0 fica sem treino (`GeometryDoesNotFitError`)."""
        train = self.fold0_train_size(n_sessions=n_sessions, max_horizon=max_horizon)
        if train < 1:
            raise GeometryDoesNotFitError(
                f"cohort geometry does not fit a grid of {n_sessions} usable sessions: "
                f"fold 0 would train on {train} sessions (need >= 1)"
            )
