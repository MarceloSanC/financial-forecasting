"""Port-out `SentimentModel` (`Protocol`) — scoring de sentimento por artigo.

`SentimentModel` é o port secundário (driven) do bounded context
`feature_engineering` para o eixo de sentimento: abstrai O SCORING de uma
`Sequence[NewsArticle]` em uma `Sequence[float]` no intervalo `[-1, +1]`. A
`application` (use case `ScoreAndAggregateSentiment`, Task 04) depende SÓ deste
`Protocol` estrutural; o adapter concreto (`FinbertSentimentModel`, Task 06) o
satisfaz por duck-typing (NÃO herda da `application`, ao contrário da ABC do old
`interfaces/sentiment_model.py` — concept 3.2 I7/D4).

`Protocol` (não ABC) é a postura hexagonal do projeto (`hex-arch-python`, LAYOUT
§3), idêntica a `IndicatorCalculator` (3.1), `MedallionStore` (2.1) e
`ExperimentTracker` (1.5). Importa a entity `NewsArticle` do `domain` de
`market_data` em runtime — a `application` pode importar `domain`, inclusive de
outro BC (LAYOUT §3/§7; concept 3.2 §3 premissas).

I5 — o port NÃO vaza `torch`/`transformers`: a fronteira troca
`Sequence[NewsArticle]` → `Sequence[float]` + os metadados de rastreabilidade
`model_name`/`revision`. As libs de ML vivem APENAS no adapter
`adapters/out/finbert/`; o gate `import-linter` `sentiment-no-ml-leak` (Task 07)
reprova se vazarem para `application`/`domain`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)


class SentimentModel(Protocol):
    """Contrato de scoring de sentimento por artigo, agnóstico de biblioteca de ML.

    Atributos de rastreabilidade (I6 — reprodutibilidade, ADR 0.0.0017):

    - `model_name`: identificador do modelo (ex.: `"ProsusAI/finbert"`).
    - `revision`: revisão pinada (SHA do commit HF) que congela os pesos.

    Semântica garantida por qualquer implementação (concept 3.2 §4/§5):

    - **I2 — alinhamento 1-artigo → 1-score, ordem preservada:** devolve
      `len(scores) == len(articles)` com `articles[i] → scores[i]` (o iésimo score
      corresponde ao iésimo artigo de entrada).
    - **I1 — score em `[-1, +1]` = `P(pos) - P(neg)`:** cada `scores[i]` é finito e
      `-1.0 <= scores[i] <= 1.0`. A polaridade segue `P(pos) - P(neg)` sobre os
      rótulos FinBERT; sinal positivo = sentimento positivo.
    - **Sequência vazia → saída vazia:** `score_articles([]) == []`.
    """

    model_name: str
    revision: str

    def score_articles(self, articles: Sequence[NewsArticle]) -> Sequence[float]:
        """Pontua cada artigo em `[-1, +1]`, preservando a ordem da entrada (I1/I2)."""
        ...
