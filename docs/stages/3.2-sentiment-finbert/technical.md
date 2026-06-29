---
title: Technical — Stage 3.2 — Sentimento via FinBERT version-pinned (feature_engineering)
description: Plano de execução da Stage 3.2 — Tasks ordenadas inside-out (port-out SentimentModel Protocol → fake InMemorySentimentModel + contract test → função pura scores_from_probs + _build_text sem torch → use case ScoreAndAggregateSentiment com DTO + agregação por dia de pregão + guarda de causalidade contra fake/oráculo → extra opcional sentiment + import lazy + adapter FinbertSentimentModel → contrato import-linter sentiment-no-ml-leak → integration skipif → gate agregado), 1 Task = 1 commit, pronto para code assistant
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, sentiment, finbert, prosusai, sentiment-model, score-and-aggregate-sentiment, scores-from-probs, daily-sentiment, trading-calendar, causality, anti-leakage, version-pinned, hf-revision, lazy-import, optional-extra, sentiment-no-ml-leak, import-linter, protocol, dto, oracle, fixture]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.2-sentiment-finbert
stage_title: Sentimento via FinBERT version-pinned
step_id: 3
step_title: Camada de features (silver)
depends_on: [2.1-medallion-storage-contracts, 2.3-news-fundamentals-ingestion, 2.4-trading-calendar, 3.1-technical-indicators]
concept_ref: ./concept.md
issue_id: 25
branch: feat/25-3-2-sentiment-finbert
tasks_count: 9
---

# Technical — Stage 3.2 — Sentimento via FinBERT version-pinned (`feature_engineering`)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.2/task-NN]`, body em bullets,
>    rodapé `Refs #25`. Escopo ASCII/kebab (sem `/`); use `.` no lugar de `/`
>    para a camada (`feature-engineering.application`), padrão aceito pelo
>    `check_commit_msg.py` (ver technical 3.1 §1 e 2.2 §7).
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[finding]`/`[deviation]`. Esta é corrida autônoma overnight
>    (ADR `0.0.0050`): **não perguntar** — decidir com julgamento, registrar e seguir.
> 7. **Fechamento NÃO é desta sessão.** O commit `stage 3.2: complete` e a marcação
>    `done` no `roadmap.md` são do **orquestrador**, após auditoria independente.
>    Esta sessão entrega concept/technical/código/testes commitados e gates verdes.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/25-3-2-sentiment-finbert`. Não há sub-PRs internos. Fluxo Git completo:
> [`GIT-WORKFLOW.md`](../../GIT-WORKFLOW.md).

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage adiciona o **eixo de sentimento** ao BC `feature_engineering` (já
container layered desde a 3.1 — **não** recriar). Entrega: o port-out
`SentimentModel` (`Protocol` estrutural que recebe `Sequence[NewsArticle]` →
`Sequence[float]` em `[-1, +1]`, ordem preservada, expõe `model_name`/`revision`,
**sem** `torch`/`transformers`); o fake comportamental `InMemorySentimentModel`; a
**função pura `scores_from_probs`** (stdlib-only, `p[2] − p[0]`) + o helper
`_build_text`, ambos **testáveis sem torch**; o use case `ScoreAndAggregateSentiment`
que lê a bronze `news` via `MedallionStore`, scora pelo port, mapeia
`published_at` → dia de pregão via `TradingCalendar` (sessões materializadas pelo
`ExchangeCalendarProvider`) com **guarda de causalidade**, **agrega por dia de
pregão** (`mean`/`pstdev`/`n`) e devolve só **DTOs frozen**; o adapter
`FinbertSentimentModel` (`ProsusAI/finbert` com `revision` HF **pinada**,
`transformers`/`torch` com **import LAZY**); o **extra opcional `sentiment`** no
`pyproject.toml` **fora do grupo `dev`**; e o **novo contrato import-linter
`sentiment-no-ml-leak`**. Os oráculos do old
(`scored_news_AAPL.parquet`/`daily_sentiment_AAPL.parquet`) são **fixtures de
regressão**, não entrada — o modelo (~400 MB) **não** é baixado/rodado no fluxo
unattended (integration `skipif`).

### Estratégia

Ordem **inside-out / TDD** (skill `task-ordering-hex`, default de vertical-slice),
cada Task deixando o build verde:

1. **Application port primeiro** (Task 01): `SentimentModel` (`Protocol`) **antes**
   de qualquer adapter (regra dura §4.3 PIPELINE — port antes de adapter, **não**
   misturar criação de port com criação de adapter no mesmo commit). Stdlib +
   entity `NewsArticle` (cross-BC, application pode importar domain — LAYOUT §3/§7,
   mesma travessia que a 3.1 faz com `Candle`). Sem `torch`/`transformers`/adapters.
2. **Fake + contract test do port** (Task 02): `InMemorySentimentModel`
   comportamental (**não** `Mock`, stdlib-only) + contract test (ordem preservada,
   score em `[-1, +1]`) — roda **sem torch**. O contract test nasce com o fake; o
   adapter real (Task 06) será adicionado ao mesmo contrato de forma só onde rodar
   sem baixar o modelo (ver Task 06 — paridade de forma sob `skipif`).
3. **Lógica pura de scoring** (Task 03): `scores_from_probs` + `_build_text` num
   **módulo de domínio-de-cálculo do adapter** (`adapters/out/finbert/scoring.py`),
   stdlib-only, **sem** `torch`. É o que garante coverage ≥90% do código vivo do BC
   sem instalar torch (I8/D3). Testado com fixtures de probabilidade hand-computed
   + regressão de **range/`confidence`** contra o oráculo `scored_news_AAPL.parquet`.
4. **Use case + agregação + causalidade** (Tasks 04–05): `ScoreAndAggregateSentiment`
   (Request/Result + DTOs frozen) testado com **fake** do `SentimentModel` + **fake**
   do `ExchangeCalendarProvider` + `TradingCalendar` **real** (Task 04: happy path +
   agregação mean/pstdev/n + DTO na fronteira); a **guarda de causalidade** (cutoff
   pós-close → próxima sessão; naive → `ValueError`; fora da janela → `ValueError`)
   ganha Task própria (Task 05) — é a DoD central (anti-leakage `0.0.0018`) e merece
   teste dedicado, sem misturar com a montagem do use case. A regressão end-to-end
   contra o oráculo diário (`daily_sentiment_AAPL.parquet`) entra na Task 05.
5. **Dependência ML + adapter** (Task 06): criar o extra opcional `sentiment`
   (`torch`+`transformers`) no `pyproject.toml` **e** o adapter `FinbertSentimentModel`
   com import LAZY **no mesmo commit** — a dep nasce onde o `import` nasce (lição 2.2
   §7 / technical 3.1 Task 04), mas aqui a dep é **opcional** e o adapter faz import
   lazy, então não há `import` no topo do módulo que quebre a coleta de testes sem a
   lib. O adapter satisfaz o port por duck-typing; delega a fórmula a
   `scores_from_probs` (Task 03). **Exceção justificada** à regra "deps em Task
   própria": como a dep é opcional e lazy, separar o `pyproject.toml` numa Task
   isolada não deixaria nada verificável (nenhum import a smoke-testar no CI sem
   torch); a unidade testável é o par extra+adapter sob `skipif`.
6. **Contrato anti-leak** (Task 07): adicionar `sentiment-no-ml-leak` ao
   `.importlinter` — **só** depois que application/adapter existem, para o
   `type=forbidden` ter o que medir. Prova por quebra intencional revertida.
7. **Integration live skipif** (Task 08): `test_finbert_sentiment_model.py` com
   `skipif`/marker (lib/modelo ausente) — **SKIPPED** no CI; valida score em
   `[-1, +1]` contra um caso de oráculo quando rodado manualmente com o extra.
8. **Gate agregado** (Task 09): `make check` + `make test` + cobertura ≥90% no
   código vivo do BC **sem** torch + ADRs `accepted`.

**Decisão de ordering declarada (3 desvios do default, justificados):**
(a) A **lógica pura** (`scores_from_probs`/`_build_text`, Task 03) vem **antes** do
adapter (Task 06) — invertendo o "código junto do adapter" — porque é stdlib-only e
testável sem torch; é o que sustenta o coverage do CI (I8). (b) **Extra ML + adapter
no mesmo commit** (Task 06), em vez de dep em Task própria, porque a dep é opcional e
o import é lazy (não há smoke de import no CI sem torch). (c) A **causalidade** ganha
Task própria (Task 05) **depois** do use case base (Task 04) — exceção justificada ao
"teste no mesmo commit do código": a guarda é a DoD central (anti-leakage `0.0.0018`)
e a regressão contra o oráculo diário é rede analítica independente (ADR `0.0.0021`).
O `.importlinter` (Task 07) só é tocado após application + adapter existirem.

### Pré-condições

- Stage `2.1-medallion-storage-contracts` em `done` — port `MedallionStore`
  (`read(layer, table, filters)` → `Sequence[Mapping]`) e schema bronze `news`
  (PK lógica `(asset_id, article_id)`, colunas `asset_id`/`article_id`/`published_at`
  UTC/`headline`/`summary`/`source`/`url`/`language`) — **verificado** no repo.
- Stage `2.3-news-fundamentals-ingestion` em `done` — entity `NewsArticle`
  (`features/market_data/domain/entities/news_article.py`, frozen, stdlib-only,
  `published_at` tz-aware, identidade `(asset_id, article_id)`) e bronze `news`
  populada — **verificado**.
- Stage `2.4-trading-calendar` em `done` — `TradingCalendar.trading_day_from_timestamp(ts, close_hour)`
  (`shared/domain/services/trading_calendar.py`) e `ExchangeCalendarProvider.sessions(start, end)`
  (`shared/application/ports/out/exchange_calendar_provider.py`); fake
  `FakeExchangeCalendarProvider` (`tests/fakes/shared/`) reusável — **verificado**.
- Stage `3.1-technical-indicators` em `done` — BC `feature_engineering` container
  layered no `.importlinter` (`hexagonal-layers` containers + `domain-purity` +
  `store-no-storage-leak`) — **verificado**.
- Branch `feat/25-3-2-sentiment-finbert` em checkout (já criada).
- ADRs `3_2_0001`, `3_2_0002`, `0_0_0017`, `0_0_0018` **já presentes** em
  `docs/adr/` com `status: accepted` (criados na Fase 3A — **verificado**); o
  concept (§1/§7 D8) os descrevia como "criar", o as-built é "já criados, conferir
  status" (ver §7 [deviation], padrão da 3.1 com `0_0_0024`).

### Premissas técnicas

- Python 3.12, `uv`, `mypy --strict`, `ruff`, `pytest`.
- `features/feature_engineering/` já tem `domain`/`application`/`adapters/out` da
  3.1; esta Stage **acrescenta** `application/ports/out/sentiment_model.py`,
  `application/use_cases/`, `adapters/out/finbert/` — **não** recria o container.
- O CI roda `uv sync --extra dev`; `torch`/`transformers` **não** entram em `dev`
  (extra `sentiment`, fora do `dev`) — finding overnight; o adapter faz import LAZY,
  então a coleta de testes e o `mypy --strict` do código vivo **não** exigem a lib.
- **Oráculo (forma confirmada na Fase 3B):**
  `data/processed/scored_news/AAPL/scored_news_AAPL.parquet` tem colunas
  `asset_id`/`article_id`/`published_at`(UTC)/`sentiment_score`/`confidence`/
  `model_name` — guarda o **score final** `P(pos)−P(neg)` por artigo (e
  `confidence = |score|`), **não** os vetores de probabilidade `[neg,neu,pos]`.
  Logo `scores_from_probs` é validada com **fixtures de probabilidade hand-computed**
  (casos com score conhecido) + o oráculo serve de **regressão de invariante**
  (todos os `sentiment_score ∈ [-1, +1]`; `confidence == abs(sentiment_score)`),
  não de fonte de probabilidades. `daily_sentiment_AAPL.parquet`
  (`asset_id`/`day`/`sentiment_score`/`n_articles`/`sentiment_std`) mapeia 1:1 ao
  contrato de agregação (mean/pstdev/n) e é a **regressão end-to-end** do use case
  (alimentar os scores per-article do `scored_news` no fake → use case → comparar o
  `Result.daily` ao oráculo diário). Esta precisão de oráculo é detalhe de
  construção de teste, **não** muda contrato/fronteira (concept A3/D3 dizia "amostra
  de probabilidades → scores batem" — atendido pelas fixtures hand-computed);
  registrar como `[decision]` na §7 se algum ajuste de tolerância/agrupamento surgir.

### Estrutura de pastas afetada

```
src/financial_forecasting/features/feature_engineering/
├── application/
│   ├── ports/out/sentiment_model.py                         # Task 01 (Protocol)
│   └── use_cases/score_and_aggregate_sentiment.py           # Task 04 (use case + DTOs)
└── adapters/out/finbert/
    ├── scoring.py                                           # Task 03 (scores_from_probs + _build_text, sem torch)
    └── finbert_sentiment_model.py                           # Task 06 (adapter, import lazy)
tests/
├── fakes/features/feature_engineering/
│   └── in_memory_sentiment_model.py                         # Task 02
├── contract/features/feature_engineering/
│   └── test_sentiment_model_contract.py                     # Task 02 (fake) + Task 06 (real, skipif)
├── unit/features/feature_engineering/adapters/
│   └── test_sentiment_scoring.py                            # Task 03 (função pura + oráculo regressão)
├── unit/features/feature_engineering/application/
│   ├── test_score_and_aggregate_sentiment.py                # Task 04 (agregação + DTO)
│   └── test_sentiment_causality.py                          # Task 05 (cutoff/naive/janela + oráculo diário)
└── integration/features/feature_engineering/
    └── test_finbert_sentiment_model.py                      # Task 08 (skipif)
.importlinter                                                # Task 07
pyproject.toml / uv.lock                                     # Task 06
```

(Os `__init__.py` intermediários das novas pastas
`features/feature_engineering/application/use_cases/`,
`adapters/out/finbert/` e `tests/**/features/feature_engineering/**` são criados
junto da primeira Task que toca cada pasta.)

## 2. Tasks

> Faixa saudável: **3–8 Tasks**. Esta Stage tem **9** (decisões já fechadas no
> concept; cada Task fica pequena e com check objetivo — dentro da faixa de
> governança da corrida autônoma, concept §12).

### Task 01 — application: port-out `SentimentModel` (`Protocol`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/application/ports/out/sentiment_model.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `SentimentModel` como `typing.Protocol` estrutural (não
  ABC — I7/D4), atributos de classe `model_name: str` e `revision: str`, método
  `score_articles(self, articles: Sequence[NewsArticle]) -> Sequence[float]`. Tipos
  stdlib (`collections.abc.Sequence`) + a entity `NewsArticle` importada de
  `financial_forecasting.features.market_data.domain.entities.news_article`.
- **Detalhes técnicos:**
  - Import de `NewsArticle` é runtime aqui (application pode importar domain de
    outro BC — LAYOUT §3/§7; concept §3 premissas). **Nenhum** import de
    `adapters`/`torch`/`transformers`.
  - **I2 — contrato de saída:** 1 score por artigo, **ordem preservada**
    (`articles[i] → scores[i]`); **I1 — score em `[-1, +1]`** = `P(pos) − P(neg)`.
    Documentar na docstring que o intervalo e a ordem são garantidos por qualquer
    implementação; `model_name`/`revision` para rastreabilidade (I6).
  - **Não** criar adapter/fake nesta Task (regra dura §4.3).
- **Critério de aceite (A1):** módulo importa (`Protocol` sem corpo); `mypy
  --strict` verde; nenhum import de `adapters`/`torch`/`transformers`;
  `check_layout.py` verde.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/application/ports/out/sentiment_model.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.application): port-out SentimentModel (Protocol) [3.2/task-01]`

---

### Task 02 — application/tests: `InMemorySentimentModel` (fake) + contract test do port

- **Arquivos a criar:**
  - `tests/fakes/features/feature_engineering/in_memory_sentiment_model.py`
  - `tests/contract/features/feature_engineering/test_sentiment_model_contract.py`
  - `__init__.py` em `tests/contract/features/feature_engineering/` se ausente.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `InMemorySentimentModel` comportamental (stdlib-only,
  **não** `Mock`) que satisfaz o `Protocol` `SentimentModel` por duck-typing:
  expõe `model_name`/`revision` (defaults fake) e devolve, para cada `NewsArticle`,
  um score determinístico — via **mapa `article_id → score`** injetado (default) ou
  função; artigos sem entrada no mapa caem num default finito em `[-1, +1]`.
  Escrever o contract test que prova **ordem preservada** e **score em `[-1, +1]`**.
- **Detalhes técnicos:**
  - O fake é a garantia (A2) de que o port é testável sem infra ML (skill
    `pytest-with-fakes`): o use case (Task 04/05) e o contract test consomem-no
    **sem torch**.
  - Contract test: rodar sobre o fake os asserts de **forma** — `len(scores) ==
    len(articles)`; `scores[i]` corresponde a `articles[i]` (ordem, ex. mapa que
    devolve scores distintos por `article_id` permutados na entrada); todo score
    `-1.0 <= s <= 1.0` (I1/C6). Estruturar o teste **parametrizado** com uma fixture
    de "modelos sob teste" começando só com `[fake]`; a Task 06 acrescenta o real
    sob `skipif` ao **mesmo** contrato (paridade de forma fake↔real, postura 2.1/2.2/3.1).
  - `mypy --strict`: uma variável anotada `SentimentModel` recebe o fake (prova a
    satisfação estrutural do `Protocol`).
- **Critério de aceite (A2):** contract test verde **sem torch**; fake atribuível a
  `SentimentModel` (`mypy --strict` verde); ordem preservada e score em `[-1, +1]`
  verificados; o teste é parametrizável para receber o real depois.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/feature_engineering/test_sentiment_model_contract.py -v
  uv run mypy --strict tests/fakes/features/feature_engineering/in_memory_sentiment_model.py
  ```
- **Commit sugerido:** `test(feature-engineering.application): InMemorySentimentModel + contract test do port [3.2/task-02]`

---

### Task 03 — adapter (lógica pura): `scores_from_probs` + `_build_text` (sem torch)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/adapters/out/finbert/scoring.py`
  - `tests/unit/features/feature_engineering/adapters/test_sentiment_scoring.py`
  - `__init__.py` em `.../adapters/out/finbert/` e na pasta de teste unit/adapters
    (se ausente).
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar o módulo `scoring.py` (**stdlib-only**, **sem** `torch`/
  `transformers`) com: (1) `scores_from_probs(probs: Sequence[Sequence[float]]) ->
  list[float]` fazendo `p[2] − p[0]` por linha (labels FinBERT `[neg, neu, pos]`),
  validando que cada linha tem **exatamente 3** componentes; (2)
  `build_text(article: NewsArticle) -> str` (= `_build_text` do old) concatenando
  `headline` + `summary` com join por espaço, fallback `" "` se ambos vazios.
  Escrever os unit tests sem torch.
- **Detalhes técnicos:**
  - **I1/C5 — `scores_from_probs`:** linha com ≠ 3 componentes → `ValueError`
    explícito (não devolve score parcial/silencioso); por construção `p ∈ [0,1]` ⇒
    resultado `∈ [-1, +1]`. Função pura: mesma entrada → mesma saída; sem estado.
  - **I10 — `build_text`:** `headline`/`summary` `strip()`; `" ".join(p for p in
    (h, s) if p)`; vazio → `" "` (fallback neutro do old
    `finbert_sentiment_model.py:_build_text`). Replica a política do old; vive no
    adapter (não cruza o port).
  - **Validação contra oráculo (A3, com a ressalva da Fase 3B em §1 premissas):** o
    `scored_news_AAPL.parquet` guarda `sentiment_score` (final) e `confidence`, não
    probs — então a função é validada por **fixtures hand-computed** (ex. `[0.1, 0.2,
    0.7] → 0.6`; `[0.7, 0.2, 0.1] → −0.6`; `[0.0, 1.0, 0.0] → 0.0`; extremos `[1,0,0]
    → −1.0`, `[0,0,1] → +1.0`); o oráculo entra como **regressão de invariante**: ler
    uma amostra do parquet e assertar `−1 <= sentiment_score <= 1` e `confidence ==
    abs(sentiment_score)` (o teste vive em `tests/`, pode importar `pyarrow`/`pandas`
    para ler o oráculo — fora do gate import-linter, que cobre `src/`).
  - **D3:** esta função é a separação que garante coverage ≥90% sem torch (I8); o
    adapter (Task 06) só produz `probs` (tokenização/forward) e delega a fórmula aqui.
- **Critério de aceite (A3/A4):** `scores_from_probs` produz os scores hand-computed
  exatos, levanta `ValueError` para linha com ≠ 3 componentes, resultado em `[-1,+1]`;
  amostra do oráculo respeita `score ∈ [-1,+1]` e `confidence == abs(score)`;
  `build_text` cobre os 4 casos (ambos / só headline / só summary / vazios →
  fallback `" "`); roda **sem torch**; `mypy --strict` verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/adapters/test_sentiment_scoring.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/adapters/out/finbert/scoring.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.adapters): scores_from_probs + build_text puros (sem torch) [3.2/task-03]`

---

### Task 04 — application: use case `ScoreAndAggregateSentiment` (DTOs + agregação)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/application/use_cases/score_and_aggregate_sentiment.py`
  - `tests/unit/features/feature_engineering/application/test_score_and_aggregate_sentiment.py`
  - `__init__.py` em `.../application/use_cases/` e na pasta de teste (se ausente).
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `ScoreAndAggregateSentiment` recebendo no construtor
  `MedallionStore`, `SentimentModel`, `ExchangeCalendarProvider` (todos `Protocol`s
  injetados). `execute(request: ScoreAndAggregateSentimentRequest) ->
  ScoreAndAggregateSentimentResult` com os DTOs frozen do concept §4. Fluxo: ler
  bronze `news` filtrada por `asset` → mapear linhas para `NewsArticle` → scorar via
  port → materializar sessões via `ExchangeCalendarProvider.sessions(start, end)` →
  `TradingCalendar` **real** sobre o VO → `trading_day` por artigo → agregar por dia.
- **Detalhes técnicos:**
  - **DTOs (concept §4, I7):** `ScoreAndAggregateSentimentRequest(asset, start,
    end, close_hour)`; `ScoredNewsDTO(asset, article_id, published_at, trading_day,
    score)`; `DailySentimentDTO(asset, day, sentiment_score, sentiment_std,
    n_articles)`; `ScoreAndAggregateSentimentResult(scored, daily, model_name,
    revision)` — todos `@dataclass(frozen=True)`. A entity `NewsArticle` **nunca**
    cruza para fora (I7).
  - **Row → `NewsArticle`:** mapear as colunas da bronze `news`
    (`asset_id`/`article_id`/`published_at`/`headline`/`summary`/`source`/`url`/
    `language`) para a entity; `read(layer="bronze", table="news",
    filters={"asset": request.asset})`.
  - **I4 — agregação (replica `SentimentAggregator` do old `:55-85`):** agrupar os
    `ScoredNewsDTO` por `trading_day`; `sentiment_score = mean(scores)`;
    `sentiment_std = pstdev(scores) if n > 1 else 0.0`; `n_articles = len(scores)`;
    **`Result.daily` ordenado por `day`**. Usar `statistics.mean`/`pstdev` (stdlib).
  - **D7 — não materializar dias vazios:** `Result.daily` contém **só** dias com
    `n_articles >= 1` (o fill de grade é da 3.5). Não preencher `score=0.0`/`n=0`.
  - **`model_name`/`revision`** do `Result` vêm do `SentimentModel` injetado (I6).
  - **Causalidade nesta Task:** usar o `TradingCalendar.trading_day_from_timestamp`
    (que já rola pós-close → próxima sessão); o **teste dedicado** da guarda é a
    Task 05. Aqui o teste cobre happy path + agregação + DTO na fronteira.
  - **Janela de sessões (C3/D6):** materializar `[start.date(), end.date()]` — ou
    janela com folga suficiente para o cutoff do último artigo; documentar que o
    caller passa janela larga o bastante (estouro → `ValueError`, herdado, Task 05).
  - Testar com `InMemorySentimentModel` (Task 02, mapa `article_id → score`),
    `FakeExchangeCalendarProvider` (`tests/fakes/shared/`, reuso 2.4) e
    `InMemoryMedallionStore` (`tests/fakes/shared/`, reuso 2.1) — **sem torch**.
- **Critério de aceite (A5):** use case recebe/devolve `dataclass` frozen (nunca
  entity); agrega `mean`/`pstdev`/`n` por dia de pregão (assert por dia com scores
  conhecidos: n=1 → std 0.0; n>1 → pstdev); `Result.daily` ordenado por `day` e só
  com `n>=1`; `Result` expõe `(model_name, revision)`; roda **sem torch**; coverage
  da `application` do BC ≥90%.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/application/test_score_and_aggregate_sentiment.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/application/use_cases/score_and_aggregate_sentiment.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.application): use case ScoreAndAggregateSentiment + DTOs + agregação diária [3.2/task-04]`

---

### Task 05 — application/tests: guarda de causalidade + regressão contra oráculo diário

- **Arquivos a criar:**
  - `tests/unit/features/feature_engineering/application/test_sentiment_causality.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** escrever o teste da **guarda de causalidade / anti-leakage**
  (I3, ADR `0.0.0018` — não-negociável) sobre o use case (com fakes, **sem torch**):
  (a) artigo publicado **após** `close_hour` é atribuído à **próxima sessão**
  (`next_session`), nunca à sessão corrente; (b) `published_at` naive → `ValueError`
  (herdado de `NewsArticle`/`TradingCalendar`); (c) dia de pregão fora da janela
  materializada → `ValueError` (sem clamp, herdado); (d) **nenhum artigo futuro** é
  usado. Mais a **regressão end-to-end** contra o oráculo diário.
- **Detalhes técnicos (I3/C1/C2/C3):**
  - **C2 — cutoff:** construir 2 artigos no mesmo dia civil — um antes do
    `close_hour`, um depois — e provar que o segundo cai na `next_session` (compor o
    `FakeExchangeCalendarProvider` com uma janela que tenha a sessão seguinte). A
    aritmética é do `TradingCalendar` (2.4); aqui prova-se que o **use case** a
    honra ponta-a-ponta.
  - **C1 — naive:** um row cujo `published_at` seja naive levanta `ValueError` ao
    construir a `NewsArticle` (não há fallback silencioso, I3).
  - **C3 — janela:** artigo cujo `trading_day` cairia além de `[start, end]` das
    sessões materializadas → `ValueError` propagado do `TradingCalendar`.
  - **Regressão contra oráculo diário (A6, robusta a `skipif` de leitura):** ler uma
    **amostra** de `scored_news_AAPL.parquet` (scores per-article + `published_at`)
    para um intervalo de dias, montar um `InMemorySentimentModel` com o mapa
    `article_id → sentiment_score` do oráculo, rodar o use case com
    `FakeExchangeCalendarProvider`/`TradingCalendar` reais e comparar o
    `Result.daily` (mean/pstdev/n por dia) ao `daily_sentiment_AAPL.parquet` dentro
    de tolerância (`atol` para `float`). Se a granularidade temporal/política de
    cutoff do oráculo do old divergir (ex. close_hour diferente), **reduzir o caso
    de regressão a 1–2 dias verificáveis** e registrar `[decision]` na §7 — o
    contrato (mean/pstdev/n por dia de pregão) é fixo; o oráculo é rede, não fonte.
    O teste de leitura do parquet pode usar `pytest.importorskip("pyarrow")` se a
    lib não estiver no ambiente (mantém o teste resiliente; não baixa modelo nenhum).
- **Critério de aceite (A6):** cutoff pós-close → próxima sessão (C2); naive →
  `ValueError` (C1); fora da janela → `ValueError` (C3); nenhum artigo futuro
  agregado no dia corrente; regressão diária bate com o oráculo (amostra) dentro de
  tolerância; roda **sem torch**.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/application/test_sentiment_causality.py -v
  ```
- **Commit sugerido:** `test(feature-engineering.application): guarda de causalidade + regressão oráculo diário [3.2/task-05]`

---

### Task 06 — deps + adapter: extra opcional `sentiment` + `FinbertSentimentModel` (import lazy) + contract real

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/adapters/out/finbert/finbert_sentiment_model.py`
- **Arquivos a modificar:**
  - `pyproject.toml` (`[project.optional-dependencies].sentiment = [torch, transformers]`)
  - `uv.lock` (sincronizado via `uv lock`)
  - `tests/contract/features/feature_engineering/test_sentiment_model_contract.py`
    (acrescentar o real ao contrato sob `skipif`)
- **O que fazer:** (1) adicionar o extra opcional `sentiment` ao `pyproject.toml`
  **FORA** do grupo `dev`, com `torch`/`transformers` pinados por minor; rodar `uv
  lock`. (2) Implementar `FinbertSentimentModel` (satisfaz `SentimentModel` por
  duck-typing) com `model_name = "ProsusAI/finbert"` e `revision` (SHA do commit HF)
  **pinada e exposta** como parâmetro de `__init__` (default = a SHA confirmada na
  execução, Q1); `transformers`/`torch` com **import LAZY** (dentro de
  `__init__`/método, **não** no topo do módulo) com `ImportError` claro orientando
  `uv sync --extra sentiment` se ausente; `batch_size=16`/`max_length=512`;
  tokenização/forward → `probs`, delegando a fórmula a `scores_from_probs` (Task 03)
  e o texto a `build_text` (Task 03). (3) Acrescentar o adapter real ao contract
  test sob `skipif`.
- **Detalhes técnicos:**
  - **I9/D2 — extra fora do dev:** espelhar o comentário dos extras existentes
    (`pandas-ta-classic`/`exchange-calendars`); citar ADR `3_2_0002`. O CI roda `uv
    sync --extra dev` (sem torch); o integration (Task 08) é SKIPPED.
  - **I5/C4 — import lazy:** **nenhum** `import torch`/`import transformers` no topo
    do módulo (quebraria a coleta de testes sem a lib e violaria o objetivo do extra
    opcional). Importar dentro de `__init__` (ou método) com `try/except ImportError`
    → re-raise com mensagem clara (`"Install the optional 'sentiment' extra: uv sync
    --extra sentiment"`). Carregar tokenizer + modelo com `revision=self.revision`
    (I6).
  - **I1/D3 — fórmula:** `_score_texts` produz só `probs` (`torch.softmax(logits,
    dim=1)` → `[neg,neu,pos]` por linha, `.tolist()`); a fórmula `p[2]−p[0]` é
    delegada a `scores_from_probs` (Task 03). `score_articles` mapeia
    `articles → build_text → probs → scores_from_probs`, preservando ordem (I2),
    em batches de 16 (`_batch`, do old).
  - **Q1 (concept §13):** confirmar na execução o **SHA da `revision`** de
    `ProsusAI/finbert` e que preserva a ordem `[negative, neutral, positive]`. Se a
    ordem divergir, mapear label **por nome** (via `model.config.id2label`) em vez de
    índice fixo e registrar `[decision]` na §7. **Não baixar o modelo no fluxo
    unattended** — a confirmação do SHA pode ser feita por consulta de metadados HF
    (sem baixar pesos) ou diferida ao integration manual (Task 08); o contrato (score
    `[-1,+1]`, agregação, causalidade) já está fixado independentemente do SHA.
  - **Contract real sob `skipif`:** parametrizar o contract test (Task 02) para
    incluir o `FinbertSentimentModel` **somente** quando `transformers`/`torch`/
    modelo estiverem disponíveis (`pytest.importorskip` / `skipif`); no CI fica
    SKIPPED (não baixa ~400 MB). A paridade de **forma** (ordem + range) é o que se
    valida — a fórmula já é coberta pela Task 03.
  - **Exceção de ordering (declarada §1):** dep + adapter no mesmo commit porque a
    dep é **opcional** e o import é **lazy** (não há smoke de import no CI sem torch);
    separar o `pyproject.toml` numa Task isolada não deixaria check verificável.
- **Critério de aceite (A7/A8):** `[project.optional-dependencies].sentiment =
  [torch, transformers]` (pinados por minor) **fora** do `dev`; `uv.lock`
  sincronizado; CI `uv sync --extra dev` segue sem torch; `FinbertSentimentModel`
  implementa o port com `revision` pinada exposta, import LAZY com `ImportError`
  claro, `batch_size=16`/`max_length=512`, delegando fórmula a `scores_from_probs`;
  contract test inclui o real sob `skipif` (SKIPPED no CI); `mypy --strict` do
  adapter verde **sem** instalar torch (anotações sob `TYPE_CHECKING`/`Any` se
  necessário, sem import no topo).
- **Comando de verificação:**
  ```bash
  uv lock
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/adapters/out/finbert/finbert_sentiment_model.py
  uv run pytest tests/contract/features/feature_engineering/test_sentiment_model_contract.py -v
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.adapters): FinbertSentimentModel (revisão pinada, import lazy) + extra opcional sentiment [3.2/task-06]`

---

### Task 07 — `.importlinter`: contrato `sentiment-no-ml-leak`

- **Arquivos a modificar:**
  - `.importlinter` (novo contrato `sentiment-no-ml-leak` + comentário citando o
    molde dos contratos vizinhos)
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar um contrato `type = forbidden` chamado
  `sentiment-no-ml-leak` com `source_modules =
  financial_forecasting.features.feature_engineering.application` +
  `...feature_engineering.domain` e `forbidden_modules = torch` + `transformers`,
  `allow_indirect_imports = False`. Espelhar o cabeçalho/comentário de
  `calendar-no-exchange-calendars-leak` (linhas 197-216) / `tracker-no-mlflow-leak`
  (145-153). Provar por **quebra intencional revertida**.
- **Detalhes técnicos (I5/D2):**
  - Comentário citando concept 3.2 I5/D2 + ADR `3_2_0002`: "`torch`/`transformers`
    vivem só no adapter `adapters/out/finbert/`; o port-out `SentimentModel`
    (Protocol) troca só `Sequence[float]` + a entity `NewsArticle`". `domain` entra
    por defesa em profundidade (já stdlib-only).
  - **Prova por quebra intencional (A9):** inserir temporariamente `import torch` no
    use case (`application`), rodar `uv run lint-imports` → deve **reprovar**
    `sentiment-no-ml-leak`; reverter → verde. Registrar na §7 se relevante.
  - Só esta Task toca `.importlinter`, e só **depois** que application + adapter
    existem (Tasks 01–06) — o `type=forbidden` precisa dos módulos reais.
  - Os contratos da 3.1 (`hexagonal-layers` containers + `domain-purity` +
    `store-no-storage-leak`) **já cobrem** o BC `feature_engineering` — **não**
    re-adicionar; só o novo `sentiment-no-ml-leak` é introduzido aqui.
- **Critério de aceite (A9):** `uv run lint-imports` verde com `sentiment-no-ml-leak`
  ativo (+ `domain-purity` + `store-no-storage-leak` seguem verdes); quebra
  intencional (`import torch` na application) reprova e é revertida; `check_layout.py`
  verde para `adapters/out/finbert`.
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `chore(import-linter): contrato sentiment-no-ml-leak (torch/transformers só no adapter) [3.2/task-07]`

---

### Task 08 — integration: `test_finbert_sentiment_model.py` (skipif live)

- **Arquivos a criar:**
  - `tests/integration/features/feature_engineering/test_finbert_sentiment_model.py`
  - `__init__.py` em `tests/integration/features/feature_engineering/` (se ausente).
- **Arquivos a modificar:** nenhum.
- **O que fazer:** escrever o integration test **live** do `FinbertSentimentModel`
  com `skipif`/marker quando `transformers`/`torch`/modelo estiverem ausentes —
  **SKIPPED no CI**, **não** baixa o modelo (~400 MB) no fluxo unattended; quando
  rodado manualmente com `uv sync --extra sentiment`, valida que `score_articles`
  devolve scores em `[-1, +1]` (ordem preservada) para um caso de oráculo.
- **Detalhes técnicos (I9/I8):**
  - `skipif`: `importlib.util.find_spec("torch") is None or
    find_spec("transformers") is None` (mesma postura `yfinance`/`exchange-calendars`
    nos integration de 2.2/2.3/2.4). Marker `@pytest.mark.integration` se o projeto
    usa markers de integração (conferir `pyproject.toml [tool.pytest]`; se não, só o
    `skipif`).
  - Caso de oráculo: 1–3 `NewsArticle` reais (headline/summary de uma notícia AAPL
    do `scored_news` cujo `sentiment_score` é conhecido) — assertar score em
    `[-1, +1]` e, com tolerância folgada (o SHA pode diferir do old), sinal
    coerente; o objetivo é fumaça de integração, não regressão fina (a fórmula já é
    coberta pela Task 03).
  - **Coverage:** este teste **não** conta como código vivo testado no CI `dev`
    (fica SKIPPED) — por isso a Task 03/04/05 já garantem ≥90% sem torch (I8).
- **Critério de aceite (A10):** `test_finbert_sentiment_model.py` SKIPPED no CI
  (`make test` verde com o teste skipped); quando rodado com o extra, valida score
  em `[-1, +1]`; **não** baixa o modelo no fluxo unattended.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/feature_engineering/test_finbert_sentiment_model.py -v
  # esperado: SKIPPED (torch/transformers ausentes no CI dev)
  ```
- **Commit sugerido:** `test(feature-engineering.adapters): integration FinbertSentimentModel com skipif live [3.2/task-08]`

---

### Task 09 — gate agregado da Stage (check + cobertura + ADRs)

- **Arquivos a modificar:** nenhum esperado (correções pontuais se um gate acusar).
- **Arquivos a criar:** nenhum.
- **O que fazer:** rodar o gate agregado e garantir tudo verde **sem instalar
  torch**: `make check` (ruff + mypy --strict + import-linter + check_layout +
  testes), `make test`, cobertura ≥90% no **código vivo do BC** (port + scoring +
  use case). Conferir A12 (ADRs `3_2_0001`/`3_2_0002`/`0_0_0017`/`0_0_0018` em
  `status: accepted` — já presentes).
- **Detalhes técnicos:**
  - Se um gate acusar, corrigir de forma mínima dentro do escopo da Stage (sem novos
    contratos) e re-rodar.
  - Cobertura medida com o adapter `FinbertSentimentModel` parcialmente descoberto
    (o forward/tokenização sob `skipif` não roda no CI) — o **código vivo** (port,
    `scoring.py`, use case, DTOs) deve estar ≥90%; documentar na §7 se o número
    global do BC ficar abaixo por causa do bloco lazy do adapter (esperado e aceito,
    I8) e mirar a cobertura nos módulos vivos.
  - **Não** fazer o commit `stage 3.2: complete` nem marcar `done` no roadmap — é do
    orquestrador após auditoria (ver preâmbulo). Esta Task entrega a branch com
    gates verdes.
- **Critério de aceite (A11/A12):** `make check` e `make test` verdes (integration
  SKIPPED); cobertura ≥90% no código vivo do BC sem torch; `import-linter` verde
  (`domain-purity` + `store-no-storage-leak` + `sentiment-no-ml-leak`);
  `check_layout.py` verde; ADRs `3_2_0001`/`3_2_0002`/`0_0_0017`/`0_0_0018`
  `accepted`.
- **Comando de verificação:**
  ```bash
  make check
  make test
  uv run pytest --cov=financial_forecasting.features.feature_engineering --cov-report=term-missing tests/
  ```
- **Commit sugerido:** `test(feature-engineering): gate verde da Stage 3.2 (check + cobertura) [3.2/task-09]`
  (omitir se a Task não produzir mudança de arquivo — neste caso é só verificação.)

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 3.2: complete` (feito pelo **orquestrador**, não por esta sessão) e ser
> mergeada em `develop`.

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
make test                 # todos os testes (unit + contract + integration SKIPPED)
uv run lint-imports       # domain-purity + store-no-storage-leak + sentiment-no-ml-leak
uv run python scripts/check_layout.py
uv run pytest --cov=financial_forecasting.features.feature_engineering --cov-report=term-missing tests/
```

### Verificações funcionais
- [ ] `SentimentModel` é `Protocol`, importa `NewsArticle`, devolve 1 score por
      artigo em `[-1, +1]` com ordem preservada, expõe `model_name`/`revision`, sem
      `torch`/`transformers`.
- [ ] `scores_from_probs([0.1,0.2,0.7]) == 0.6` (hand-computed); linha com ≠ 3
      componentes → `ValueError`; amostra do oráculo `scored_news_AAPL.parquet`
      respeita `score ∈ [-1,+1]` e `confidence == abs(score)`.
- [ ] `ScoreAndAggregateSentiment` agrega `mean`/`pstdev(n>1)/0.0(n==1)`/`n` por dia
      de pregão, devolve só DTOs (nunca entity), `Result.daily` ordenado e só com
      `n>=1`, `Result` expõe `(model_name, revision)`.
- [ ] Guarda de causalidade: artigo pós-`close_hour` → próxima sessão; naive →
      `ValueError`; fora da janela → `ValueError`; nenhum artigo futuro no dia
      corrente; regressão diária bate com `daily_sentiment_AAPL.parquet` (amostra).
- [ ] `InMemorySentimentModel` (e o `FinbertSentimentModel` sob `skipif`) passam o
      **mesmo** contract test (ordem + range).
- [ ] Quebra intencional (`import torch` na application) reprova `sentiment-no-ml-leak`
      e é revertida; `torch`/`transformers` fora do grupo `dev`.
- [ ] `test_finbert_sentiment_model.py` SKIPPED no CI (modelo não baixado no fluxo
      unattended).

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — Score `[-1,+1]` = P(pos)−P(neg) | `test_sentiment_scoring.py` (hand-computed + `ValueError` 3-comp + oráculo range/`confidence`, Task 03); contract test (range, Task 02/06) |
| I2 — Ordem preservada entrada↔saída | `test_sentiment_model_contract.py` (`articles[i]→scores[i]`, Task 02/06) |
| I3 — Causalidade / anti-leakage | `test_sentiment_causality.py` (cutoff pós-close→próxima sessão; naive→`ValueError`; fora da janela→`ValueError`; nenhum futuro, Task 05) |
| I4 — Agregação diária (mean/pstdev/n) | `test_score_and_aggregate_sentiment.py` (mean/pstdev(n>1)/0.0/n, ordenado, Task 04) + regressão oráculo diário (Task 05) |
| I5 — Pureza hex / `sentiment-no-ml-leak` | `lint-imports` (`sentiment-no-ml-leak` + quebra intencional, Task 07); import lazy no adapter (Task 06) |
| I6 — Reprodutibilidade / FinBERT pinado | `FinbertSentimentModel.revision` pinada exposta (Task 06); `Result` cruza `(model_name, revision)` (Task 04) |
| I7 — DTO na fronteira / port `Protocol` | `mypy --strict` (Protocol sem ABC, Task 01); use case devolve DTO frozen, nunca entity (Task 04) |
| I8 — Coverage ≥90% sem torch | `scoring.py` + use case + DTOs testados sem torch (Tasks 03/04/05); cobertura no gate (Task 09) |
| I9 — Extra opcional fora do dev | `pyproject.toml` (`sentiment` fora do `dev`, Task 06); integration SKIPPED (Task 08) |
| I10 — `build_text` + params do tokenizer no adapter | `test_sentiment_scoring.py` (`build_text` 4 casos, Task 03); `batch_size`/`max_length` internos ao adapter (Task 06) |
| I11 — Gates verdes | `make check`/`make test`/cobertura (Task 09); `lint-imports`/`check_layout` |

### Checklist de fechamento da Stage
- [ ] Todas as 9 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` e `make test` verdes no branch; cobertura ≥90% no código vivo do BC
- [ ] ADRs `3_2_0001`/`3_2_0002`/`0_0_0017`/`0_0_0018` em `status: accepted`
- [ ] `concept.md`/`technical.md` desta Stage não precisam de retoque material
- [ ] **(orquestrador, pós-auditoria)** commit `stage 3.2: complete` aplicado e
      `roadmap.md` marcado `done` — **fora do escopo desta sessão**

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out). Explícito:

```
Task 01 (port SentimentModel) ─► Task 02 (fake + contract) ─► Task 04 (use case + DTOs) ─► Task 05 (causalidade + oráculo diário)
                                                                  ▲
Task 03 (scores_from_probs + build_text, sem torch) ──────────────┤ (delegada pelo adapter)
                                                                  │
Task 02 + Task 03 ─► Task 06 (extra sentiment + adapter + contract real skipif) ─► Task 07 (.importlinter sentiment-no-ml-leak)
Task 06 ─► Task 08 (integration skipif) 
Task 01..08 ─► Task 09 (gate agregado)
```

- Task 02 depende de 01 (o fake satisfaz o port); Task 03 é independente do port
  (lógica pura — pode ser feita em paralelo, mas listada após 02 por coesão);
  Task 04 depende de 01/02 (usa o port + fake) e do `MedallionStore`/
  `ExchangeCalendarProvider`/`TradingCalendar` (2.1/2.4, já no repo); Task 05
  depende de 04 (testa o use case); Task 06 depende de 01 (implementa o port) e 03
  (delega a fórmula); Task 07 depende de 04+06 (application + adapter existem para o
  `forbidden` medir); Task 08 depende de 06 (testa o adapter real); Task 09 é o gate
  agregado final.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `revision` pinada do FinBERT troca a ordem de labels `[neg,neu,pos]` ou a semântica (Q1) | Mapear label **por nome** (`model.config.id2label`) em vez de índice fixo no adapter; `[decision]` na §7. Fixtures hand-computed (Task 03) + contract test (range) são a rede; SHA pinada congela o modelo |
| Oráculo `scored_news` não guarda probs (só score final) — `scores_from_probs` sem oráculo direto de probs | Validar a função com fixtures hand-computed (score conhecido) + usar o oráculo como regressão de invariante (range/`confidence`); já refletido na Task 03 (§1 premissas) — sem mudança de contrato |
| Oráculo diário do old usou `close_hour`/política de cutoff diferente → regressão diária não bate exato | Reduzir a regressão a 1–2 dias verificáveis com tolerância; `[decision]` na §7; o contrato (mean/pstdev/n por dia de pregão) é fixo, o oráculo é rede não fonte |
| `torch`/`transformers` vazam para `application`/`domain` | Task 07: `sentiment-no-ml-leak` + import lazy; quebra intencional reprova e é revertida (lição 2.2/3.1 §7) |
| `torch` entra no `dev` e estoura/lentidão no runner CI | I9/D2: extra `sentiment` fora do `dev`; CI roda `uv sync --extra dev` (sem torch); integration SKIPPED |
| `mypy --strict` do adapter exige tipos de `torch`/`transformers` ausentes no CI | Anotar com `Any`/`TYPE_CHECKING` (sem import no topo); o forward é tipado localmente; `scores_from_probs` (puro) carrega o tipo forte |
| Modelo (~400 MB) baixado no fluxo unattended | I9: integration `skipif` (lib/modelo ausente) + não baixar pesos para confirmar SHA (metadados HF ou diferir ao manual); oráculo é fixture, não re-scora |
| `uv lock` não resolve `torch`/`transformers` no extra | Pin por minor; se o resolver travar (CUDA/CPU wheels), fixar a variante CPU compatível e registrar `[deviation]`; o extra é opcional (não afeta o CI `dev`) |
| Coverage <90% por bloco lazy do adapter descoberto no CI | I8/D3: medir o **código vivo** (port/scoring/use case ≥90%); o forward sob `skipif` é esperado descoberto; documentar na §7 (Task 09) |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (escopo, contratos §4,
  invariantes §5, casos de erro §6, decisões §7, critérios §11, Q1 §13)
- [`../../overview.md`](../../overview.md) — §3/§6/§7/§11 (FinBERT version-pinned,
  anti-leakage, oráculo)
- [`../../roadmap.md`](../../roadmap.md) — Stage `3.2-sentiment-finbert`
  (`arquivos_a_criar`, DoD, `non_goals`, `contratos_consumidos`) e vizinhas
  (3.4 interações sentimento×vol, 3.5 dataset-builder/persistência `processed`)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — §B linha 3.2 (`ProsusAI/finbert` + pinar revisão; score `P(pos)−P(neg)`; média
  diária por dia de pregão)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches, commits, status
- [`../../LAYOUT.md`](../../LAYOUT.md) §1/§3/§7 — estrutura `features/<feature>/`,
  direção inward, application pode importar domain de outro BC
- [`../../PIPELINE.md`](../../PIPELINE.md) §4.3 — Task atômica (port antes de adapter)
- ADRs desta Stage:
  [`3.2.0001`](../../adr/3_2_0001-finbert-pinned-revision-and-scoring.md),
  [`3.2.0002`](../../adr/3_2_0002-ml-deps-optional-extra-and-lazy-import.md),
  [`0.0.0017`](../../adr/0_0_0017-finbert-version-pinned.md),
  [`0.0.0018`](../../adr/0_0_0018-anti-leakage-non-negotiable.md)
- ADRs de fundação/padrão: [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md)
  (contract tests + oráculo); [`2.1.0002`](../../adr/2_1_0002-medallion-store-port-shape.md)
  / [`3.1.0001`](../../adr/3_1_0001-feature-engineering-bc-and-indicator-contracts.md)
  (port-as-Protocol + DTO na fronteira; registry bronze-only);
  [`2.4.0001`](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md)
  (`TradingCalendar` sobre `TradingSessions` injetado pelo `ExchangeCalendarProvider`)
- Stages consumidas: 2.1 (`MedallionStore`/bronze `news`), 2.3 (`NewsArticle`/bronze
  `news` populada), 2.4 (`TradingCalendar`/`ExchangeCalendarProvider` + fake), 3.1
  (BC `feature_engineering` container layered)
- `.importlinter` — contratos `tracker-no-mlflow-leak` (145-153),
  `store-no-storage-leak` (167-189), `calendar-no-exchange-calendars-leak` (207-216)
  — moldes do novo `sentiment-no-ml-leak`
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `ddd-tactical-patterns`, `import-linter-rules`
- Old (semântica/lógica, **não** implementação):
  `financial-time-series-forecasting/src/adapters/finbert_sentiment_model.py:91-124`
  (`_build_text`/`_score_texts`/`_batch`; fórmula `probs[:,2]−probs[:,0]`;
  batch16/maxlen512; import torch no topo → mover p/ lazy; `model_name` sem
  `revision` → pinar),
  `src/interfaces/sentiment_model.py` (ABC → `Protocol`),
  `src/domain/services/sentiment_aggregator.py:55-85` (agregação `mean`/`pstdev`/`n`,
  ordenado por `day`),
  `src/use_cases/sentiment_feature_engineering_use_case.py:116-186` (guarda de
  causalidade; `_fill_missing_days_with_zero_news` — fill deferido a 3.5)
- Oráculos (fixture de regressão, **não** entrada):
  `data/processed/scored_news/AAPL/scored_news_AAPL.parquet`
  (`asset_id`/`article_id`/`published_at`/`sentiment_score`/`confidence`/`model_name`),
  `data/processed/sentiment_daily/AAPL/daily_sentiment_AAPL.parquet`
  (`asset_id`/`day`/`sentiment_score`/`n_articles`/`sentiment_std`)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.
>
> **Corrida autônoma overnight (ADR `0.0.0050`):** nesta corrida o agente
> **não pergunta** — decide com julgamento (política de decisão do BRIEF),
> registra como `[decision]`/`[finding]`/`[deviation]` e segue. Decisões
> não-triviais viram ADR `3_2_NNNN`.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Decisão:** <o que foi decidido>                        <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage** (com direção sugerida
  e Stage candidata).
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-06-29 — [decision] Task 06 — revisão HF pinada + mapeamento de labels por nome — Claude (autonomous overnight)
**Contexto:** O `concept`/`ADR 3.2.0001`/`old` assumiam a ordem de rótulos
`[negative, neutral, positive]` (índices 0/1/2) e o old fazia `probs[:,2]−probs[:,0]`
por **índice fixo**. Ao resolver o SHA da `revision` de `ProsusAI/finbert` via
**metadados HF** (`https://huggingface.co/api/models/ProsusAI/finbert` →
`sha = 4556d13015211d73dccd3fdd39d39232506f3e43`) e ler o `config.json` desse commit
(sem baixar pesos), o `id2label` desse SHA é `{0: positive, 1: negative, 2: neutral}`
— ordem **diferente** da assumida. Usar índice fixo produziria o score com sinal
trocado (`P(neg)−P(pos)`).
**Decisão:** (a) pinar `revision = "4556d13015211d73dccd3fdd39d39232506f3e43"` (SHA
resolvido por metadados, sem download — fluxo unattended preservado); (b) o adapter
`FinbertSentimentModel` mapeia os rótulos **por NOME** via `model.config.id2label`,
reordenando a saída crua do modelo para a ordem canônica `[neg, neu, pos]` **antes**
de chamar `scores_from_probs` (que permanece pura e validada por oráculo). O fallback
estava **pré-declarado** em §5 (riscos) e §13/Q1 do concept — logo NÃO requer ADR
novo; fica dentro do envelope já aceito (`3.2.0001`/`0.0.0017`).
**Razão:** Corrige um bug latente (sinal invertido) e torna o adapter robusto a
revisões com rótulos reordenados; mantém a fórmula pura simples e a fronteira do port
inalterada. `_resolve_canonical_order` levanta `ValueError` se um rótulo esperado
faltar (defesa contra revisão inesperada).

### 2026-06-29 — [decision] Task 05 — regressão diária contra oráculo por dia civil==pregão — Claude (autonomous overnight)
**Contexto:** O oráculo `daily_sentiment_AAPL.parquet` do old usa **dias civis** com
**fill de dias-zero** (`n_articles=0`, `score=0.0` em feriados/fins de semana), ao
passo que o contrato desta Stage é por **dia de pregão** só com `n>=1` (D7, fill
deferido à 3.5). Comparar 1:1 ao oráculo diário não bate por construção (o oráculo
tem milhares de dias n=0 e dias com rolagem de cutoff).
**Decisão:** A regressão end-to-end (`test_daily_aggregation_matches_oracle_on_verifiable_days`)
alimenta os scores per-article do oráculo `scored_news_AAPL.parquet` no use case com
`close_hour = 21:00 UTC` (fechamento NYSE em EST = 16:00 ET, inferido dos timestamps
de 2023-01-12, onde o artigo das 22:43 UTC rolou para a sessão seguinte no oráculo) e
compara `Result.daily` ao oráculo diário **só nos dias do 1º trimestre/2023 em que o
dia civil coincide com a sessão de pregão e o oráculo registra `n>=1`** — **21 dias
verificáveis** (2 multi-artigo). Os dias com rolagem de cutoff (n diverge) ficam fora
do conjunto verificável por construção.
**Razão:** O contrato (mean/pstdev/n por dia de pregão) é fixo; o oráculo é **rede de
regressão**, não fonte. A precisão de construção de teste não muda contrato/fronteira
(premissa §1 do technical). 21 dias verificáveis dão teeth reais à regressão.

### 2026-06-29 — [deviation] Tasks 02/06/08 — import dinâmico/lazy e per-file-ignore PLC0415 — Claude (autonomous overnight)
**Contexto:** O hook `pre-commit` pina `ruff v0.6.9` (não conhece `PLC0415`,
import-should-be-at-top-level), mas o `make check` autoritativo usa `ruff 0.15.20`
(que **flagra** `PLC0415`). O hook removia o `# noqa: PLC0415` como "não usado",
reintroduzindo a violação no gate autoritativo. O adapter precisa de import **lazy**
de `torch`/`transformers` (extra opcional), e os testes precisam importar o adapter
**condicionalmente** (sem torch no CI).
**Decisão/ajuste:** (a) nos testes (`test_sentiment_model_contract.py`,
`test_finbert_sentiment_model.py`), trocar `from ... import` lazy por
`importlib.import_module(...)` — idioma de import dinâmico que não dispara `PLC0415`
em nenhuma versão; (b) no adapter (lazy import obrigatório dentro do `__init__`),
adicionar `[tool.ruff.lint.per-file-ignores]` para `PLC0415` **só** no arquivo
`finbert_sentiment_model.py` (o lazy import é o design, não um descuido). Reversível
quando o pin do hook subir.
**Razão:** Mantém `make check` e o hook **ambos** verdes sem enfraquecer a regra
globalmente; o lazy import é a condição do extra opcional (I5/I9/D2).

### 2026-06-29 — [decision] Task 06 — pin de torch/transformers por minor no extra opcional — Claude (autonomous overnight)
**Contexto:** O extra `sentiment` precisava de versões pinadas; o ambiente é CPU e o
`uv lock` resolve wheels CUDA por default.
**Decisão:** `torch>=2.2,<3.0` + `transformers>=4.40,<5.0` (pin por minor, mesma
postura de `exchange-calendars`/`yfinance`); `uv lock` resolveu `torch 2.12.1` +
`transformers 4.57.6` no `uv.lock`. Confirmado que `uv sync --extra dev` **não**
instala torch (invariante do CI mantido: `find_spec("torch") is None`).
**Razão:** O extra é opcional e fora do `dev`; o pin por minor evita breaking changes
sem travar patches. Não afeta o CI `dev`.

### 2026-06-29 — [finding] Task 09 — cobertura do adapter FinBERT sob skipif (esperado, aceito) — Claude (autonomous overnight)
**Contexto:** O **código vivo torch-free** do BC (port `sentiment_model.py` + `scoring.py`
+ use case `score_and_aggregate_sentiment.py` + DTOs) está em **100%** de cobertura
sem torch. O adapter `finbert_sentiment_model.py` (55 linhas) fica **0%** porque todo
o corpo (`__init__`/forward) é o bloco lazy de ML, **SKIPPED** no CI (torch ausente).
O `make check` global passa (95.62% ≥ 90%, gate verde), mas uma medição **escopada ao
BC incluindo o adapter** mostra ~78% por causa do bloco lazy descoberto.
**Razão/direção:** Esperado e aceito (concept/technical I8/D3): o forward do adapter
só roda com `uv sync --extra sentiment` + download do modelo (~400 MB), fora do fluxo
unattended; o integration `skipif` (Task 08) o exercita quando rodado manualmente. A
fórmula é coberta pela função pura (Task 03) e a forma pelo contract test (Tasks
02/06). Nenhuma ação pendente — registrado para a auditoria não confundir o 0% do
bloco lazy com gap de teste.

<!-- END: post-execution -->