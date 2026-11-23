"""Figura de apoio: como cada comparador produz os quantis (ilustrativa, dados simulados).

Um painel por comparador, todos sobre a MESMA série simulada de retornos, mostrando o
que cada modelo emitiria para h+1: faixa de 96% (0,02-0,98), faixa de 80% (0,1-0,9) e
mediana. As receitas seguem a implementação (baseline_emission.emit_decision e
lightgbm_quantile_trainer):

- retorno nulo: os sete quantis valem 0;
- média histórica: os sete quantis valem a média do treino (fixa no fold);
- AR(1): mu e phi estimados no treino; média mu + phi*(r_t - mu), desvio do resíduo
  do treino, quantis gaussianos;
- EWMA-vol: sigma2_t = 0,94*sigma2_{t-1} + 0,06*r_t**2 (semente r_0**2), média 0,
  quantis gaussianos;
- quantis empíricos: quantis tipo 7 dos últimos 252 retornos;
- GBM quantílico: um LightGBM por nível tau (objective='quantile'), grade ordenada.
  Aqui com três indicadores simples simulados, não os 55 do estudo.

Nenhum número vem do texto do TCC. Rodar a partir de text/apresentacao/:
    uv run --no-project --with matplotlib --with numpy --with lightgbm python gera_comparadores.py
"""

from statistics import NormalDist

import lightgbm as lgb
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

LEVELS = (0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98)
LAMBDA = 0.94
WINDOW = 252
SHOWN = 200
TARGET = "../figuras/apoio/35_comparadores_como_funcionam.png"
RETURN = "#9a9a9a"
# Cores dos modelos nas figuras do TCC (MODEL_STYLES em matplotlib_figure_renderer.py).
PANELS = (
    ("Retorno nulo", "#eb6834", "os 7 quantis valem 0, todo dia"),
    ("Média histórica", "#1baf7a", "os 7 quantis valem a média do treino"),
    ("AR(1)", "#eda100", "sino de largura fixa; centro segue o último retorno"),
    ("EWMA-vol", "#e87ba4", r"sino de centro 0; $\sigma^2_t = 0{,}94\,\sigma^2_{t-1} + 0{,}06\,r_t^2$"),
    ("Quantis empíricos", "#008300", "quantis dos últimos 252 retornos, sem forma imposta"),
    ("GBM quantílico", "#6250d6", "árvores treinadas para cada quantil, com indicadores"),
)


def _pct(x: float, _pos: object = None) -> str:
    return f"{x * 100:.0f}%".replace("-", "−")


def _simulated_returns(rng: np.random.Generator) -> np.ndarray:
    """Treino com um episódio agitado; no trecho mostrado, um choque e a volta à calma."""
    n = WINDOW + SHOWN
    days = np.arange(n)
    vol = np.full(n, 0.011)
    vol[110:140] = 0.026
    shock = WINDOW + 70
    vol[shock : shock + 30] = 0.032
    vol[shock + 30 :] = 0.011 + 0.021 * np.exp(-(days[shock + 30 :] - shock - 30) / 25)
    returns = rng.normal(0.0004, vol)
    for t in range(1, n):  # leve autocorrelação, para o AR(1) ter o que estimar
        returns[t] += 0.05 * returns[t - 1]
    return returns


def _gaussian(mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    z = np.array([NormalDist().inv_cdf(level) for level in LEVELS])
    return mean[:, None] + std[:, None] * z[None, :]


def _features(returns: np.ndarray) -> np.ndarray:
    """Três indicadores observados até t: |r_t|, volatilidade de 5 e de 20 pregões."""
    rows = []
    for t in range(len(returns)):
        r5 = returns[max(0, t - 4) : t + 1]
        r20 = returns[max(0, t - 19) : t + 1]
        rows.append((abs(returns[t]), r5.std(), r20.std()))
    return np.array(rows)


def _grids(returns: np.ndarray) -> list[np.ndarray]:
    """Grade (dia de decisão t -> 7 quantis para t+1) de cada comparador no trecho mostrado."""
    train = returns[:WINDOW]
    decisions = np.arange(WINDOW - 1, WINDOW + SHOWN - 1)  # prevê os dias WINDOW..fim
    k = len(decisions)

    zero = np.zeros((k, len(LEVELS)))
    mean = np.full((k, len(LEVELS)), train.mean())

    x, y = train[:-1], train[1:]
    phi = np.cov(x, y, bias=True)[0, 1] / x.var()
    mu = train.mean()
    resid = y - (mu + phi * (x - mu))
    ar1 = _gaussian(mu + phi * (returns[decisions] - mu), np.full(k, resid.std()))

    sigma2 = [returns[0] ** 2]
    for r in returns[1:]:
        sigma2.append(LAMBDA * sigma2[-1] + (1 - LAMBDA) * r**2)
    ewma = _gaussian(np.zeros(k), np.sqrt(np.array(sigma2)[decisions]))

    empirical = np.array(
        [np.quantile(returns[t - WINDOW + 1 : t + 1], LEVELS, method="linear") for t in decisions]
    )

    feats = _features(returns)
    fit_x, fit_y = feats[: WINDOW - 1], returns[1:WINDOW]
    gbm = np.column_stack([
        lgb.train(
            {"objective": "quantile", "alpha": level, "num_leaves": 7, "learning_rate": 0.05,
             "min_data_in_leaf": 20, "verbose": -1, "seed": 7},
            lgb.Dataset(fit_x, fit_y),
            num_boost_round=150,
        ).predict(feats[decisions])
        for level in LEVELS
    ])
    gbm = np.sort(gbm, axis=1)  # a mesma ordenação que garante quantis monótonos
    return [zero, mean, ar1, ewma, empirical, gbm]


def main() -> None:
    rng = np.random.default_rng(2026)
    returns = _simulated_returns(rng)
    shown = returns[WINDOW:]
    days = np.arange(SHOWN)

    plt.rcParams.update({"font.size": 12, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 3, figsize=(13.33, 7.5), dpi=150, sharex=True, sharey=True)
    fig.subplots_adjust(left=0.06, right=0.985, top=0.80, bottom=0.21, hspace=0.5, wspace=0.08)
    fig.suptitle("Como cada comparador produz os 7 quantis de amanhã (ilustrativo, dados simulados)",
                 fontsize=17, fontweight="bold", y=0.985)
    fig.text(0.5, 0.925, "Mesma série de retornos em todos os painéis; previsão para h+1 feita na "
             "véspera, com o que se sabia até o dia anterior", ha="center", fontsize=12.5,
             color="#333333")

    for ax, (name, color, recipe), grid in zip(axes.flat, PANELS, _grids(returns), strict=True):
        ax.vlines(days, 0, shown, color=RETURN, linewidth=1.0, zorder=1)
        ax.fill_between(days, grid[:, 0], grid[:, 6], color=color, alpha=0.18, linewidth=0, zorder=2)
        ax.fill_between(days, grid[:, 1], grid[:, 5], color=color, alpha=0.38, linewidth=0, zorder=2)
        ax.plot(days, grid[:, 3], color=color, linewidth=2.2, zorder=3)
        ax.set_title(name, loc="left", fontsize=14.5, fontweight="bold", color=color, pad=22)
        ax.text(0, 1.03, recipe, transform=ax.transAxes, fontsize=11, color="#333333")
        if np.allclose(grid[:, 0], grid[:, 6]):
            ax.text(0.98, 0.06, "sem faixa: os 7 quantis\nsão o mesmo número",
                    transform=ax.transAxes, ha="right", fontsize=11, color=color)
        ax.set_ylim(-0.09, 0.09)
        ax.set_xlim(0, SHOWN - 1)
        ax.yaxis.set_major_formatter(FuncFormatter(_pct))
        ax.axhline(0, color="#cccccc", linewidth=0.6, zorder=0)
    for ax in axes[1]:
        ax.set_xlabel("pregão do período de teste")
    for ax in axes[:, 0]:
        ax.set_ylabel("retorno")

    handles = [
        Patch(color="#777777", alpha=0.25, label="faixa de 96% (0,02 a 0,98)"),
        Patch(color="#777777", alpha=0.55, label="faixa de 80% (0,1 a 0,9)"),
        Line2D([], [], color="#555555", linewidth=2.2, label="mediana (0,5)"),
        Line2D([], [], color=RETURN, linewidth=1.0, label="retorno do dia"),
    ]
    fig.legend(handles=handles, loc="lower center", ncols=4, frameon=False, fontsize=12,
               bbox_to_anchor=(0.5, 0.07))
    fig.text(0.06, 0.012,
             "Em h+7, nulo, média, EWMA-vol e quantis empíricos emitem a mesma grade; o AR(1) "
             "centra mais perto da média e alarga; o GBM treina outro modelo.\n"
             "GBM aqui com 3 indicadores simulados (|r|, volatilidade de 5 e de 20 pregões), "
             "não os 55 do estudo.",
             fontsize=11, style="italic", color="#333333", linespacing=1.4)
    fig.savefig(TARGET)


if __name__ == "__main__":
    main()
