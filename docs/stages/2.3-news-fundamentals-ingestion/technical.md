---
title: Technical — Stage 2.3 — Ingestão de news e fundamentals (market_data)
description: Plano de execução da Stage 2.3 — Tasks ordenadas inside-out (entities NewsArticle/FundamentalReport no domain → ports NewsFetcher/FundamentalFetcher Protocol → use cases IngestNews/IngestFundamentals + fakes → adapters parquet-reuse default + Alpha Vantage não-default offline → gate agregado), 1 Task = 1 commit, pronto para code assistant
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, news-fundamentals-ingestion, news-article, fundamental-report, news-fetcher, fundamental-fetcher, ingest-news, ingest-fundamentals, bronze, medallion-store, parquet-reuse, alpha-vantage, earnings, reported-date, throttle, dedup, article-id, contract-test, fake]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 2.3-news-fundamentals-ingestion
stage_title: Ingestão de news e fundamentals
step_id: 2
step_title: Camada bronze + calendário
depends_on: [2.1-medallion-storage-contracts, 2.2-market-data-ingestion]
concept_ref: ./concept.md
issue_id: 21
branch: feat/21-2-3-news-fundamentals-ingestion
tasks_count: 11
---

# Technical — Stage 2.3 — Ingestão de news e fundamentals (`market_data`)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.3/task-NN]`, body em bullets,
>    rodapé `Refs #21`. Escopo ASCII/kebab; usar `.` no lugar de `/` para
>    indicar camada (`market-data.domain` etc. — o hook `check_commit_msg.py`
>    rejeita `/` no escopo; precedente 2.2 §7).
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[finding]`/`[deviation]`. Esta é corrida autônoma overnight
>    (ADR `0.0.0050`): **não perguntar** — decidir com julgamento, registrar e seguir.
> 7. **Fechamento NÃO é desta sessão.** O commit `stage 2.3: complete` e a marcação
>    `done` no `roadmap.md` são do **orquestrador**, após auditoria independente.
>    Esta sessão entrega concept/technical/código/testes commitados e gates verdes;
>    qualquer teste adicionado na auditoria de testes entra **antes** do fechamento.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/21-2-3-news-fundamentals-ingestion`. Não há sub-PRs internos. Fluxo Git
> completo: [`GIT-WORKFLOW.md`](../../GIT-WORKFLOW.md).

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage **estende** o BC de feature `market_data` (já criado e layered na 2.2)
com dois novos tipos de dado — news e fundamentals de AAPL — repetindo o **mesmo
padrão** de `IngestCandles`. Entrega, nas três camadas hexagonais existentes: as
entities `NewsArticle` e `FundamentalReport` (frozen+slots, **stdlib-only**,
invariantes portadas do old); os ports-out `NewsFetcher` e `FundamentalFetcher`
(`Protocol`); os use cases `IngestNews` e `IngestFundamentals` (DTO frozen in/out,
**nunca** vazam entity, gravam bronze `news`/`fundamental` via `MedallionStore` da
2.1); os adapters de **origem default** `ParquetRawNewsFetcher`/
`ParquetFundamentalFetcher` (leem o parquet existente sem re-baixar) e os adapters
**não-default** `AlphaVantageNewsFetcher`/`AlphaVantageFundamentalFetcher`
(construídos, testados **sem rede**); fakes comportamentais; e contract tests
parametrizados paridade fake↔real dos dois ports.

### Estratégia

Ordem **inside-out / TDD** (skill `task-ordering-hex`, default de vertical-slice),
cada Task deixando o build verde — **duas trilhas paralelas** (news + fundamentals)
dentro de um mesmo BC, intercaladas por camada:

1. **Domain primeiro** (Tasks 01–02): `NewsArticle` (Task 01) e `FundamentalReport`
   (Task 02), cada uma com `__post_init__` validando suas invariantes e unit test no
   mesmo commit. Sem dependentes ainda; reusam o helper UTC `require_tz_aware` do
   domain `market_data` (2.2, Task 02).
2. **Application — ports** (Task 03): `NewsFetcher` **e** `FundamentalFetcher` como
   `Protocol` no mesmo commit (dois ports, **zero adapter** — não viola a regra dura
   §4.3 PIPELINE "não misturar criação de port com criação de adapter do mesmo
   port"; criar dois ports irmãos num commit é permitido e mantém a trilha enxuta).
3. **Application — use cases + fakes** (Tasks 04–05): `IngestNews` + DTOs +
   `InMemoryNewsFetcher` + teste com os dois fakes (Task 04); `IngestFundamentals` +
   DTOs + `InMemoryFundamentalFetcher` + teste (Task 05). Cada use case testável sem
   infra (reusa `FakeMedallionStore` da 2.1).
4. **Adapters out — reuso parquet (default)** (Tasks 06–07): `ParquetRawNewsFetcher`
   + contract test paridade fake↔real (Task 06); `ParquetFundamentalFetcher` +
   contract test (Task 07). Cada um valida contra o parquet real (6921 / 81 linhas).
5. **Adapters out — Alpha Vantage (não-default, offline)** (Tasks 08–09):
   `AlphaVantageNewsFetcher` (Task 08) e `AlphaVantageFundamentalFetcher` (Task 09),
   cada um com teste de integração via `monkeypatch` do cliente HTTP + fixtures JSON;
   **nunca** rede ao vivo (live só com `skipif`).
6. **Verificações de fechamento** (Tasks 10–11): estabilizar os contract tests
   paridade fake↔real contra os parquet reais (Task 10) + gate agregado `make
   check`/`make test`/cobertura ≥90% no diff (Task 11).

**Decisão de ordering declarada:** as entities (01–02) não têm dependentes até os
ports (03); os ports precedem os use cases (04–05, que consomem) e os adapters
(06–09, que implementam); os adapters parquet (06–07) vêm antes dos Alpha Vantage
(08–09) porque são a **origem default** e dão a paridade fake↔real do contract test;
os AV são não-default e só precisam existir + ser provados offline.

**Sem Task de `.importlinter` / `pyproject`** (diferença vs 2.2): o container
`market_data` e a cobertura `domain-purity`/`store-no-storage-leak` da sua
`domain`/`application` **já existem** (2.2, finding F2.2 — verificado em
`.importlinter`); arquivos novos caem em camadas já cobertas. O cliente HTTP dos
adapters Alpha Vantage usa **`httpx`** (já em `[project].dependencies`, `>=0.27`) em
vez do `requests` do old — sem nova dependência, sem tocar `uv.lock`. Ver §5 / §7.

### Pré-condições

- Stage `2.1-medallion-storage-contracts` em `done` — **verificado**:
  `MedallionStore`, `ParquetMedallionStore`, schemas bronze `NEWS`/`FUNDAMENTAL`
  (`bronze_schemas.py:76-141`), `FakeMedallionStore`
  (`tests/fakes/shared/in_memory_medallion_store.py`), `DuplicateKeyError`
  disponíveis.
- Stage `2.2-market-data-ingestion` em `done` e mergeada — **verificado**: BC
  `market_data` é container layered no `.importlinter` (linha 53); sua
  `domain`/`application` já estão em `domain-purity`/`store-no-storage-leak` (linhas
  74, 163–164); helper `require_tz_aware` em
  `features/market_data/domain/time/utc.py`; padrão `IngestCandles`/`CandleFetcher`
  a espelhar.
- Branch `feat/21-2-3-news-fundamentals-ingestion` em checkout (já criada).
- Parquet reais presentes — **verificado**: `data/raw/news/AAPL/news_AAPL.parquet`
  (3.0 MB, 6921×8) e `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet`
  (11 KB, 81×10, 17 `NaT`).
- ADRs `2.3.0001` / `2.3.0002` presentes em `docs/adr/` (`status: accepted`) —
  **verificado**.

### Premissas técnicas

- Python 3.12, `uv`, `mypy --strict`, `ruff`, `pytest`.
- Schema bronze `NEWS`: **8 colunas `nullable=False`** (`asset_id`, `article_id`,
  `published_at` UTC, `headline`, `summary`, `source`, `url`, `language`),
  `strict=True`, `coerce=False` → row-mapper precisa de **fallback non-null** nos
  opcionais da entity (I6/D5). **Reusado, não redefinido.**
- Schema bronze `FUNDAMENTAL`: 5 floats `float64` `nullable=True`, `reported_date`
  `datetime64[ns, UTC]` `nullable=True`, `report_type`/`source`/`fiscal_date_end`
  non-null, ordem das colunas conforme `bronze_schemas.py:95-110`. **Reusado.**
- `MedallionStore` garante append-only + dedup por PK lógica
  (`(asset_id, article_id)` news; `(asset_id, report_type, fiscal_date_end)`
  fundamental), `DuplicateKeyError` sem `overwrite`. **Não reimplementar dedup.**
- `ALPHAVANTAGE_API_KEY` configurada, mas o caminho default e os testes **não**
  batem na API (free-tier ~25 req/dia — robustez overnight, I13).
- Os use cases são **stdlib-only** (não usam `pandas`); a coerção de dtype final
  (`float64`, `datetime64[ns, UTC]`) é do `ParquetMedallionStore` (2.1, I7).

### Estrutura de pastas afetada

```
src/financial_forecasting/features/market_data/
├── domain/entities/
│   ├── news_article.py                                 # Task 01
│   └── fundamental_report.py                           # Task 02
├── application/
│   ├── ports/out/
│   │   ├── news_fetcher.py                              # Task 03
│   │   └── fundamental_fetcher.py                       # Task 03
│   └── use_cases/
│       ├── ingest_news.py                              # Task 04
│       └── ingest_fundamentals.py                      # Task 05
└── adapters/out/
    ├── parquet/
    │   ├── parquet_raw_news_fetcher.py                 # Task 06
    │   └── parquet_fundamental_fetcher.py              # Task 07
    └── alpha_vantage/
        ├── alpha_vantage_news_fetcher.py               # Task 08
        └── alpha_vantage_fundamental_fetcher.py        # Task 09
tests/
├── unit/features/market_data/domain/
│   ├── test_news_article.py                            # Task 01
│   └── test_fundamental_report.py                      # Task 02
├── unit/features/market_data/application/
│   ├── test_ingest_news.py                             # Task 04
│   └── test_ingest_fundamentals.py                     # Task 05
├── fakes/features/market_data/
│   ├── in_memory_news_fetcher.py                       # Task 04
│   └── in_memory_fundamental_fetcher.py                # Task 05
├── contract/features/market_data/
│   ├── test_news_fetcher_contract.py                   # Tasks 06, 10
│   └── test_fundamental_fetcher_contract.py            # Tasks 07, 10
└── integration/features/market_data/adapters/out/alpha_vantage/
    ├── test_alpha_vantage_news_fetcher.py              # Task 08
    └── test_alpha_vantage_fundamental_fetcher.py       # Task 09
```

(Os `__init__.py` das novas pastas `adapters/out/alpha_vantage/`,
`tests/.../alpha_vantage/` são criados junto da primeira Task que toca cada pasta.
`adapters/out/parquet/` e as pastas de teste de domain/application/contract já
existem da 2.2.)

## 2. Tasks

> Faixa saudável: **3–8 Tasks**. Esta Stage tem **11**: duas trilhas paralelas
> (news + fundamentals) dentro de um BC, decisões já fechadas no concept, cada Task
> pequena e com check objetivo — dentro da faixa de governança da corrida autônoma
> (concept §12).

### Task 01 — entity `NewsArticle` + invariantes (domain)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/domain/entities/news_article.py`
  - `tests/unit/features/market_data/domain/test_news_article.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `NewsArticle` como `@dataclass(frozen=True, slots=True)`,
  **domain puro stdlib-only** (só `dataclasses` + `datetime`), campos `asset_id`,
  `published_at` (tz-aware), `headline`, `summary`, `source`, `url|None=None`,
  `article_id|None=None`, `language|None="en"`. `__post_init__` valida I1 e
  normaliza `language`.
- **Detalhes técnicos (I1, portada do old `news_article.py:32-77`):**
  - `asset_id` `str` não-vazia; `headline`/`summary`/`source` são `str` (não `None`);
    `source` não-vazia.
  - `published_at` é `datetime` tz-aware → delegar a `require_tz_aware` do domain
    `market_data` (`...domain/time/utc.py`, 2.2); naive → `ValueError`.
  - `url`, quando dado, começa com `http://`/`https://` (senão `ValueError`).
  - `language`, quando dado, normalizado para lowercase contendo só letras e `-`
    (caractere inválido → `ValueError`); normalização via `object.__setattr__`
    (frozen).
  - Campo de texto `None` em obrigatório → `TypeError`.
- **Critério de aceite (A1):** unit test cobre `NewsArticle` válido + uma violação
  por invariante (`asset_id` vazio, `published_at` naive, `source` vazia, `url` sem
  http(s), `language` com caractere inválido, texto `None`) → cada uma
  `ValueError`/`TypeError`; normalização de `language` (`"EN"`→`"en"`) verificada.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/domain/test_news_article.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/domain/entities/news_article.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data.domain): entity NewsArticle com invariantes [2.3/task-01]`

---

### Task 02 — entity `FundamentalReport` + invariantes (domain)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/domain/entities/fundamental_report.py`
  - `tests/unit/features/market_data/domain/test_fundamental_report.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `FundamentalReport` como
  `@dataclass(frozen=True, slots=True)`, **stdlib-only** (só `dataclasses` +
  `datetime`), campos na ordem do schema bronze `FUNDAMENTAL` (`bronze_schemas.py`):
  `asset_id`, `report_type`, `fiscal_date_end` (`date`), `reported_date` (`date|None`),
  `revenue|None`, `net_income|None`, `operating_cash_flow|None`,
  `total_shareholder_equity|None`, `total_liabilities|None`, `source`.
  `__post_init__` valida I2.
- **Detalhes técnicos (I2, portada do old `fundamental_report.py:32-60`):**
  - `asset_id`/`source` `str` não-vazias.
  - `fiscal_date_end` é `date` **sem hora** — `datetime` (subclasse de `date`) →
    `TypeError` (checar `isinstance(x, datetime)` explicitamente, pois
    `isinstance(datetime, date)` é `True`).
  - `report_type` ∈ `{"annual", "quarterly"}` (senão `ValueError`).
  - os cinco numéricos são `float`-ou-`None` (`int` aceitar como float? espelhar o
    old — registrar `[decision]` se divergir).
  - `reported_date` é `date`-ou-`None`; `datetime` → `TypeError`.
- **Critério de aceite (A2):** unit test cobre `FundamentalReport` válido (com e
  **sem** `reported_date`) + uma violação por invariante (`fiscal_date_end` com hora,
  `report_type` fora do conjunto, numérico não-float, `reported_date` `datetime`,
  `asset_id` vazio) → `ValueError`/`TypeError`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/domain/test_fundamental_report.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/domain/entities/fundamental_report.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data.domain): entity FundamentalReport com invariantes [2.3/task-02]`

---

### Task 03 — ports-out `NewsFetcher` + `FundamentalFetcher` (`Protocol`) (application)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/application/ports/out/news_fetcher.py`
  - `src/financial_forecasting/features/market_data/application/ports/out/fundamental_fetcher.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar os dois ports como `typing.Protocol` estrutural (não ABC —
  D1/I4), importando só a entity do domain (`NewsArticle`/`FundamentalReport`); sem
  `httpx`/`pandas`/`pyarrow`. **Nenhum adapter nesta Task** (regra dura §4.3).
  - `NewsFetcher.fetch_company_news(self, ticker: str, start_date: datetime, end_date: datetime) -> list[NewsArticle]`
  - `FundamentalFetcher.fetch_fundamentals(self, asset_id: str) -> list[FundamentalReport]`
- **Detalhes técnicos:**
  - Import das entities é runtime (a `application` pode importar o `domain`).
  - Docstring documenta a semântica: `start_date`/`end_date` tz-aware; origem **sem
    dados** no intervalo → `[]`; origem **indisponível** → erro (não silencia em
    vazio) (C6).
  - Criar dois ports irmãos num commit é permitido (não mistura port com adapter do
    mesmo port) e mantém a trilha enxuta.
- **Critério de aceite (A3):** ambos os módulos importam (`Protocol` sem corpo),
  `mypy --strict` verde; nenhum import de `adapters`/`httpx`/`pandas`/`pyarrow`.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/features/market_data/application/ports/out/news_fetcher.py src/financial_forecasting/features/market_data/application/ports/out/fundamental_fetcher.py
  uv run python scripts/check_layout.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(market-data.application): ports-out NewsFetcher e FundamentalFetcher (Protocol) [2.3/task-03]`

---

### Task 04 — use case `IngestNews` + DTOs + `InMemoryNewsFetcher` + teste (application)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/application/use_cases/ingest_news.py`
  - `tests/fakes/features/market_data/in_memory_news_fetcher.py`
  - `tests/unit/features/market_data/application/test_ingest_news.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `IngestNewsRequest`/`IngestNewsResult` (dataclasses frozen,
  concept §4), o use case `IngestNews` (injeta `NewsFetcher` + `MedallionStore`,
  `execute(request) -> IngestNewsResult`), o `InMemoryNewsFetcher` comportamental
  (stdlib-only, **não** `Mock`, devolve `list[NewsArticle]` pré-carregada) e o teste
  do use case usando `InMemoryNewsFetcher` + `FakeMedallionStore` (reusado da 2.1).
- **Detalhes técnicos:**
  - DTOs: `Request{asset, start, end}` (tz-aware), `Result{asset, ingested, start,
    end}`. **Nunca** devolve `NewsArticle`/`list` (I5/D6).
  - `execute`: valida `start`/`end` tz-aware (`require_tz_aware`) e `start <= end`
    (C5 → `ValueError`); chama `fetcher.fetch_company_news(ticker=request.asset,
    start_date=request.start, end_date=request.end)`; mapeia cada
    `NewsArticle → Row` (`Mapping[str, object]`) com **8 chaves non-null** (I6/D5):
    `url`/`summary`/`language` `None`/vazio → string non-null (`""` ou o valor);
    `article_id` non-null garantido via fallback `url > f"{published_at_iso}:{headline[:80]}"`
    **antes** de montar a Row (mesma regra do adapter de news — D5); grava
    `store.write(layer="bronze", table="news", rows=..., overwrite=False)`. Devolve
    `Result(ingested=len(rows), ...)`.
  - **Dedup (I8/D5):** delegar colisão de PK ao `MedallionStore`
    (`DuplicateKeyError` com `overwrite=False`); não reimplementar dedup.
  - **Sem cursor-walking** do old `fetch_news_use_case.py` (D4 — non-goal).
  - Forma do fallback non-null (`""` vs sentinel) fica a julgamento (concept §13);
    default `""` para texto, ID estável para `article_id`. Registrar `[decision]` se
    divergir.
- **Critério de aceite (A5):** teste com fakes cobre: 8 chaves non-null em **toda**
  Row (fallback aplicado para `url`/`summary`/`language` vazios); `article_id`
  non-null garantido (fallback `url > time+title`); chamada a `write` com
  `layer="bronze"`, `table="news"`, `overwrite=False`; `Result.ingested` == nº de
  artigos; retorno é `IngestNewsResult` (nunca entity); colisão de PK propaga
  `DuplicateKeyError`; `start > end`/naive → `ValueError`. Cobertura ≥90% no use case.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/application/test_ingest_news.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/application/use_cases/ingest_news.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data.application): use case IngestNews + DTO + fake do fetcher [2.3/task-04]`

---

### Task 05 — use case `IngestFundamentals` + DTOs + `InMemoryFundamentalFetcher` + teste (application)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/application/use_cases/ingest_fundamentals.py`
  - `tests/fakes/features/market_data/in_memory_fundamental_fetcher.py`
  - `tests/unit/features/market_data/application/test_ingest_fundamentals.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `IngestFundamentalsRequest`/`IngestFundamentalsResult`
  (frozen, concept §4), o use case `IngestFundamentals` (injeta
  `FundamentalFetcher` + `MedallionStore`), o `InMemoryFundamentalFetcher`
  comportamental e o teste com os dois fakes.
- **Detalhes técnicos:**
  - DTOs: `Request{asset_id, start=None, end=None, report_types=("annual","quarterly")}`,
    `Result{asset_id, ingested}`. **Nunca** devolve entity (I5/D6).
  - `execute`: chama `fetcher.fetch_fundamentals(request.asset_id)`; **filtra** por
    `report_type ∈ request.report_types` e por intervalo de `fiscal_date_end` ∈
    `[start, end]` **inclusivo** quando `start`/`end` dados (I10, lógica do old
    `fetch_fundamentals_use_case.py:55-65`; quando dados, validar tz-aware antes de
    filtrar — C5); mapeia cada `FundamentalReport → Row` (10 colunas, I7):
    `report_type`/`source` non-null, `fiscal_date_end` convertido a `datetime` UTC
    (non-null), `reported_date` `date → datetime` UTC **ou** `None` (os 17 `NaT`
    permanecem nulos), os cinco floats Python (ou `None`); grava
    `store.write(layer="bronze", table="fundamental", rows=..., overwrite=False)`.
  - O use case é stdlib-only — a conversão `date → datetime` UTC usa
    `datetime.combine(d, time(0,0), tzinfo=UTC)`; a coerção de dtype final é do
    `ParquetMedallionStore` (I7).
  - Dedup por PK `(asset_id, report_type, fiscal_date_end)` delegada ao store (C3).
- **Critério de aceite (A6):** teste com fakes cobre: filtro por `report_type` e por
  intervalo de `fiscal_date_end` (inclusivo); report **sem** `reported_date` →
  Row com `reported_date=None` (`NaT`); conversão `date → datetime` UTC; 10 colunas
  na Row; `Result.ingested` == nº gravado; retorno é `IngestFundamentalsResult`
  (nunca entity); colisão de PK → `DuplicateKeyError`; `start`/`end` naive →
  `ValueError`. Cobertura ≥90% no use case.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/application/test_ingest_fundamentals.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/application/use_cases/ingest_fundamentals.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data.application): use case IngestFundamentals + DTO + fake do fetcher [2.3/task-05]`

---

### Task 06 — adapter `ParquetRawNewsFetcher` (origem default) + contract test paridade fake↔real

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/adapters/out/parquet/parquet_raw_news_fetcher.py`
  - `tests/contract/features/market_data/test_news_fetcher_contract.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar `ParquetRawNewsFetcher` (implementa o `Protocol`
  `NewsFetcher` por duck-typing) lendo `data/raw/news/AAPL/news_AAPL.parquet`
  (6921×8) e mapeando para `list[NewsArticle]`; criar o contract test parametrizado
  que roda o **mesmo** contrato sobre `InMemoryNewsFetcher` e `ParquetRawNewsFetcher`
  (paridade fake↔real, I14, postura ADR 0.0.0021).
- **Detalhes técnicos:**
  - `pandas`/`pyarrow` vivem **só** aqui (D2). Construtor recebe o caminho do parquet
    (default = constante do adapter; injetável p/ teste — espelhar o
    `ParquetRawCandleFetcher` da 2.2).
  - Mapeia cada linha → `NewsArticle` preservando tz UTC em `published_at`;
    `url`/`article_id`/`language`/`summary` da coluna parquet (já non-null no raw).
  - `fetch_company_news(ticker, start_date, end_date)` filtra por `[start, end]`
    tz-aware (`require_tz_aware`; C5); origem sem dados no intervalo → `[]`.
  - Arquivo ausente/ilegível → erro de aplicação claro, **não** lista vazia (C6).
  - **Contract test (I14):** fixture parametrizada `[fake, real]`, mesmos asserts —
    `fetch_company_news` devolve `list[NewsArticle]`, todos `published_at` tz-aware
    UTC, invariantes I1 respeitadas, `start_date > end_date` → `[]` (ou semântica
    declarada). O real lê o parquet existente (não baixa).
- **Critério de aceite (A4/A7-news):** contract test verde para `[fake, real]`; o
  real lê o parquet (6921 linhas) e produz `NewsArticle`s válidos com tz UTC;
  `import-linter`/`check_layout` não acusam `pandas` fora do adapter.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/market_data/test_news_fetcher_contract.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/adapters/out/parquet/parquet_raw_news_fetcher.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(market-data.adapters): ParquetRawNewsFetcher (raw default) + contract test paridade [2.3/task-06]`

---

### Task 07 — adapter `ParquetFundamentalFetcher` (origem default) + contract test paridade fake↔real

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/adapters/out/parquet/parquet_fundamental_fetcher.py`
  - `tests/contract/features/market_data/test_fundamental_fetcher_contract.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar `ParquetFundamentalFetcher` (implementa
  `FundamentalFetcher`) lendo
  `data/processed/fundamentals/AAPL/fundamentals_AAPL.parquet` (81×10, 17 `NaT`) e
  mapeando para `list[FundamentalReport]`; criar o contract test parametrizado
  `[fake, real]`.
- **Detalhes técnicos:**
  - `pandas`/`pyarrow` só aqui (D2). Construtor recebe o caminho (default =
    constante; injetável p/ teste).
  - Converte datas UTC → `date`/`None`: `fiscal_date_end` (`datetime64 UTC →
    .date()`); `reported_date` (`NaT → None`, senão `.date()`), espelhando o old
    `parquet_fundamental_repository.py:54,93-94` (normalização `asset_id`;
    `date → pd.Timestamp(tz="UTC")` na ida — aqui é a **volta**).
  - Floats `NaN → None`; normaliza `asset_id`.
  - `fetch_fundamentals(asset_id)` devolve todos os reports do ativo (filtro de
    `report_type`/intervalo é do use case, I10 — adapter não filtra).
  - Arquivo ausente/ilegível → erro de aplicação claro (C6).
  - **Contract test (I14):** `[fake, real]`, mesmos asserts — devolve
    `list[FundamentalReport]`, invariantes I2 respeitadas, `reported_date`
    `date|None` (alguns `None` reais), `fiscal_date_end` é `date` sem hora.
- **Critério de aceite (A4/A7-fund):** contract test verde para `[fake, real]`; o
  real lê 81 linhas (17 com `reported_date=None`) e produz `FundamentalReport`s
  válidos; datas UTC → `date`/`None` corretas; `import-linter` verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/market_data/test_fundamental_fetcher_contract.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/adapters/out/parquet/parquet_fundamental_fetcher.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(market-data.adapters): ParquetFundamentalFetcher (parquet default) + contract test paridade [2.3/task-07]`

---

### Task 08 — adapter `AlphaVantageNewsFetcher` (não-default) + teste de integração sem rede

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/adapters/out/alpha_vantage/alpha_vantage_news_fetcher.py`
  - `tests/integration/features/market_data/adapters/out/alpha_vantage/test_alpha_vantage_news_fetcher.py`
  - `__init__.py` em `.../adapters/out/alpha_vantage/` e na pasta de teste.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** portar do old com julgamento o `AlphaVantageNewsFetcher`
  (implementa `NewsFetcher`), trocando `requests` por **`httpx`** (já em deps);
  teste de integração via `monkeypatch` do cliente HTTP + fixtures JSON — **nunca**
  rede ao vivo (I13).
- **Detalhes técnicos:**
  - `httpx` vive **só** aqui. Endpoint `NEWS_SENTIMENT` (`tickers`,
    `time_from`/`time_to`, `sort=EARLIEST`, `limit=1000`, `apikey`); chave via
    `ALPHAVANTAGE_API_KEY` (lida na construção/env, não em import).
  - Parse `time_published` por regex `^\d{8}T\d{4}(\d{2})?$` → UTC; ID estável
    `url > f"{time_published}:{headline[:80]}"` (old `:169-170`).
  - Throttle `_MIN_INTERVAL=1.1s` + lock + `time.monotonic` **no adapter** (I9, old
    `:32`); não acopla domínio/use case.
  - Guard `Note`/`Information` → `RuntimeError`; JSON não-dict / `feed`
    ausente-ou-não-lista → `RuntimeError`/`ValueError` (C7); itens com
    `time_published` inválido são ignorados (parse defensivo), sem quebrar o lote.
  - **Nenhuma** chamada de rede em import/instanciação.
  - Teste de integração: `monkeypatch` do método de GET do `httpx` (ou injeção de um
    client fake) devolvendo fixtures JSON (`feed` válido + caso `Information`/`Note`
    + item com `time_published` inválido); assertar mapeamento → `NewsArticle`,
    guard de rate-limit → `RuntimeError`, item inválido ignorado. **Roda sem rede.**
    Live só com `pytest.mark.skipif(<sem rede / sem ALPHAVANTAGE_API_KEY>)`.
- **Critério de aceite (A8/A10-news):** o adapter implementa `NewsFetcher`; teste de
  integração com `monkeypatch` verde **sem** rede; parse regex, ID estável, throttle
  e guard `Note`/`Information` exercitados; live só com `skipif`; sem rede em import.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/market_data/adapters/out/alpha_vantage/test_alpha_vantage_news_fetcher.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/adapters/out/alpha_vantage/alpha_vantage_news_fetcher.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(market-data.adapters): AlphaVantageNewsFetcher (NEWS_SENTIMENT, throttle, offline) [2.3/task-08]`

---

### Task 09 — adapter `AlphaVantageFundamentalFetcher` (4 endpoints incl. EARNINGS, não-default) + teste sem rede

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/adapters/out/alpha_vantage/alpha_vantage_fundamental_fetcher.py`
  - `tests/integration/features/market_data/adapters/out/alpha_vantage/test_alpha_vantage_fundamental_fetcher.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** portar do old com julgamento o `AlphaVantageFundamentalFetcher`
  (implementa `FundamentalFetcher`), `httpx` no lugar de `requests`; teste de
  integração via `monkeypatch` + fixtures JSON dos **4 endpoints** — sem rede (I13).
- **Detalhes técnicos (D3/I11, ADR 2.3.0001; old `:108-201`):**
  - **4 endpoints**: `INCOME_STATEMENT` + `BALANCE_SHEET` + `CASH_FLOW` + `EARNINGS`
    (`symbol`, `apikey`).
  - Field maps **verbatim** do old: `totalRevenue→revenue`, `netIncome→net_income`,
    `operatingCashflow→operating_cash_flow`,
    `totalShareholderEquity→total_shareholder_equity`,
    `totalLiabilities→total_liabilities`, `EARNINGS.reportedDate→reported_date`.
  - `_merge_reports` por `(report_type, fiscal_date_end)` (annual/quarterly).
    EARNINGS é a **única** fonte de `reported_date` (nullable; ausente → `None`).
  - `_to_float`/`_to_date` defensivos (old `:89-105`): `"None"`/`"NaN"`/`""` →
    `None`; `fiscalDateEnding` ausente/ilegível → item pulado (`_to_date → None →
    continue`, C8).
  - Throttle `_MIN_INTERVAL=12.5s` + lock + `time.monotonic` **no adapter** (I9, old
    `:30`).
  - Guard `Note`/`Information` → `RuntimeError` (C7); sem rede em import.
  - Teste de integração: `monkeypatch` do cliente HTTP devolvendo fixtures JSON dos
    4 endpoints (incluindo `"None"`/`"NaN"` em campos numéricos e `reportedDate`
    **ausente** → `reported_date=None`); assertar merge → `FundamentalReport`,
    `reported_date` `None` quando EARNINGS não traz a data, guard de rate-limit.
    **Sem rede.** Live só com `skipif`.
- **Critério de aceite (A9/A10-fund):** o adapter implementa `FundamentalFetcher`; 4
  endpoints, field maps verbatim, `_merge_reports` por `(report_type,
  fiscal_date_end)`, EARNINGS → `reported_date`, `_to_float`/`_to_date` defensivos,
  throttle `12.5s`; teste com `monkeypatch` cobre `"None"`/`"NaN"` e `reportedDate`
  ausente (`NaT`); **roda sem rede**; live só com `skipif`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/market_data/adapters/out/alpha_vantage/test_alpha_vantage_fundamental_fetcher.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/adapters/out/alpha_vantage/alpha_vantage_fundamental_fetcher.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(market-data.adapters): AlphaVantageFundamentalFetcher (4 endpoints incl. EARNINGS, offline) [2.3/task-09]`

---

### Task 10 — estabilizar contract tests paridade fake↔real contra os parquet reais

- **Arquivos a modificar:**
  - `tests/contract/features/market_data/test_news_fetcher_contract.py` (ajustes
    finos se o parquet real exigir)
  - `tests/contract/features/market_data/test_fundamental_fetcher_contract.py`
- **Arquivos a criar:** nenhum (ou um teste de integração `read-all` se decidir
  isolar a leitura completa — registrar `[deviation]`, espelhando o
  `test_parquet_raw_candle_fetcher.py` da 2.2).
- **O que fazer:** rodar os dois contract tests paridade fake↔real contra os parquet
  reais completos (6921 news; 81 fundamentals) e estabilizar: garantir que **todas**
  as linhas legítimas produzem entity válida (I1/I2), que `published_at` é sempre
  tz-aware UTC, que os 17 `NaT` viram `reported_date=None` (não erro), e que fake e
  real respondem idênticos ao mesmo contrato.
- **Detalhes técnicos:**
  - Ponto de verdade dos riscos do concept §10: campo opcional de news chegando
    vazio, conversão `date→datetime`/perda dos 17 `NaT`, ID estável. Se nada
    reprovar, esta Task confirma (pode ser dobrada nas Tasks 06/07 via `[deviation]`
    — registrar).
  - Nenhuma tolerância arbitrária: se uma linha legítima reprovar, tratar com
    critério (comparar no dtype correto, ajustar mapeamento) e registrar
    `[decision]`.
- **Critério de aceite:** ambos os contract tests verdes sobre `[fake, real]` com os
  parquet reais completos; zero linha legítima falsamente rejeitada; 17 `NaT` →
  `None` confirmados; qualquer ajuste registrado como `[decision]`/`[deviation]`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/market_data/test_news_fetcher_contract.py tests/contract/features/market_data/test_fundamental_fetcher_contract.py -v
  ```
- **Commit sugerido:** `test(market-data): contract tests de news/fundamental estáveis contra os parquet reais [2.3/task-10]`

---

### Task 11 — gate agregado da Stage (check + cobertura)

- **Arquivos a modificar:** nenhum esperado (correções pontuais se um gate acusar).
- **Arquivos a criar:** nenhum.
- **O que fazer:** rodar o gate agregado e garantir tudo verde: `make check` (ruff +
  mypy --strict + import-linter + check_layout + testes), `make test`, cobertura
  ≥90% no diff (I16). Conferir A12 (ADRs `2.3.0001`/`2.3.0002` em `status: accepted`
  — já presentes no repo).
- **Detalhes técnicos:**
  - `import-linter` verde **reusando** o container `market_data` da 2.2 (nenhuma
    edição no `.importlinter` nesta Stage — os novos arquivos caem em camadas já
    cobertas; I16).
  - Se algum gate acusar, corrigir de forma mínima dentro do escopo da Stage (sem
    novos contratos) e re-rodar.
  - **Não** fazer o commit `stage 2.3: complete` nem marcar `done` no roadmap — é do
    orquestrador após auditoria (preâmbulo).
- **Critério de aceite (A11/A12):** `make check` e `make test` verdes; cobertura
  ≥90% no diff; `import-linter` verde com `market_data` (reusado); `check_layout.py`
  verde; ADRs `2.3.0001`/`2.3.0002` `accepted`.
- **Comando de verificação:**
  ```bash
  make check
  make test
  uv run pytest --cov=financial_forecasting.features.market_data --cov-report=term-missing tests/
  ```
- **Commit sugerido:** `test(market-data): gate verde da Stage 2.3 (check + cobertura) [2.3/task-11]`
  (omitir se a Task não produzir mudança de arquivo — neste caso é só verificação.)

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 2.3: complete` (feito pelo **orquestrador**, não por esta sessão) e ser
> mergeada em `develop`.

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
make test                 # todos os testes (unit + contract + integration)
uv run lint-imports       # market_data (container da 2.2, reusado) verde
uv run python scripts/check_layout.py
uv run pytest --cov=financial_forecasting.features.market_data --cov-report=term-missing tests/
```

### Verificações funcionais
- [ ] Executar `IngestNews` para `AAPL` com `ParquetRawNewsFetcher` (origem default)
      + `FakeMedallionStore` lê o parquet existente (sem re-baixar), mapeia 8 chaves
      non-null, grava `(bronze, news)` e devolve `IngestNewsResult` com a contagem
      (nunca um `NewsArticle`).
- [ ] Executar `IngestFundamentals` para `AAPL` com `ParquetFundamentalFetcher` +
      `FakeMedallionStore` filtra por `report_type`/intervalo, converte `date →
      datetime` UTC (17 `NaT` → `None`), grava `(bronze, fundamental)` e devolve
      `IngestFundamentalsResult` (nunca entity).
- [ ] `InMemoryNewsFetcher`/`ParquetRawNewsFetcher` e
      `InMemoryFundamentalFetcher`/`ParquetFundamentalFetcher` passam os **mesmos**
      contract tests parametrizados dos ports (paridade fake↔real).
- [ ] Testes de integração dos adapters Alpha Vantage rodam **sem** acesso a rede
      (`monkeypatch` + fixtures JSON); live só com `skipif`.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — `NewsArticle` válido | `test_news_article.py` (cada violação → `ValueError`/`TypeError`; `language` normalizado); contract test sobre o parquet real (Task 10) |
| I2 — `FundamentalReport` válido | `test_fundamental_report.py` (cada violação; `fiscal_date_end` sem hora; sem `reported_date`); contract test sobre o parquet real (Task 10) |
| I3 — Pureza do domínio | `lint-imports` (`domain-purity` já cobre `features.market_data.domain`, 2.2) + `check_layout.py` |
| I4 — Ports `Protocol` (não ABC) | `mypy --strict` + ausência de herança ABC; adapters satisfazem por duck-typing |
| I5 — Use case não vaza entity | `test_ingest_news.py`/`test_ingest_fundamentals.py` (retorno é `Ingest*Result`, nunca entity/list) |
| I6 — `NewsArticle → Row` 8 colunas non-null | `test_ingest_news.py` (8 chaves non-null; fallback `url`/`summary`/`language` vazio → string) |
| I7 — `FundamentalReport → Row` 10 colunas | `test_ingest_fundamentals.py` (`date → datetime` UTC; `reported_date None → NaT`; 5 floats) |
| I8 — Dedup de news (coleção) delegada ao store | `test_ingest_news.py` (colisão `(asset_id, article_id)` → `DuplicateKeyError` via `FakeMedallionStore`) |
| I9 — Throttle só no adapter AV | `test_alpha_vantage_*` (throttle no adapter); use case/domain sem `_MIN_INTERVAL` |
| I10 — Filtro `report_type` + intervalo no use case | `test_ingest_fundamentals.py` (descarta `report_type` fora; intervalo `fiscal_date_end` inclusivo) |
| I11 — EARNINGS é o 4º endpoint | `test_alpha_vantage_fundamental_fetcher.py` (fixture EARNINGS → `reported_date`; ausente → `None`) |
| I12 — Origem default = parquet | contract tests (Tasks 06/07) leem o parquet existente; AV não-default |
| I13 — Integração não bate na API | `test_alpha_vantage_*` (`monkeypatch`, sem rede; live só `skipif`; sem rede em import) |
| I14 — Paridade fake↔real | `test_news_fetcher_contract.py`/`test_fundamental_fetcher_contract.py` parametrizados `[fake, real]` |
| I15 — Schemas bronze não estendidos | `bronze_schemas.py` `NEWS`/`FUNDAMENTAL` inalterados; rows casam 1:1 (rede de segurança `pandera` no `write`) |
| I16 — Gates verdes | `make check`/`make test`/cobertura ≥90% (Task 11) |

### Checklist de fechamento da Stage
- [ ] Todas as 11 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` e `make test` verdes no branch; cobertura ≥90% no diff
- [ ] ADRs `2.3.0001` e `2.3.0002` em `status: accepted`
- [ ] `concept.md`/`technical.md` desta Stage não precisam de retoque material
- [ ] **(orquestrador, pós-auditoria)** commit `stage 2.3: complete` aplicado e
      `roadmap.md` marcado `done` — **fora do escopo desta sessão**

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out). Explícito:

```
Task 01 (NewsArticle) ─────┐
Task 02 (FundamentalReport)┤
                           └─► Task 03 (ports NewsFetcher + FundamentalFetcher)
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                        ▼                        │
        Task 04 (IngestNews)    Task 05 (IngestFundamentals)    │
              │                        │                        │
              ▼                        ▼                        │
        Task 06 (Parquet news   Task 07 (Parquet fund          │
        + contract)             + contract)                     │
              │                        │                        │
        Task 08 (AV news)       Task 09 (AV fund) ◄─────────────┘
              └────────────┬───────────┘
                           ▼
                     Task 10 (contract tests estáveis vs parquet real)
                           ▼
                     Task 11 (gate agregado)
```

- Task 03 depende de 01+02 (os ports tipam as entities); 04 depende de 03 (consome
  `NewsFetcher`); 05 depende de 03 (consome `FundamentalFetcher`); 06 depende de
  03+04 (implementa o port, paridade contra o fake do use case); 07 depende de 03+05;
  08/09 dependem de 03 (implementam os ports) — independentes dos parquet, mas vêm
  depois porque são não-default; 10 estabiliza os contract tests de 06/07 contra os
  parquet reais; 11 é o gate agregado final. Tasks 04/06/08 (news) e 05/07/09
  (fundamentals) são trilhas paralelas — a ordem listada intercala por camada.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Campo opcional de news (`url`/`article_id`/`language`/`summary` vazio) chega `None`/vazio à Row → `pandera` `NEWS` (`nullable=False`) rejeita | I6/D5: row-mapper com fallback non-null (`""`/ID estável); teste do use case assertando 8 chaves non-null; rede de segurança `pandera` (C4) |
| `IngestFundamentals` perde `reported_date` (todas as linhas) por omitir EARNINGS no adapter AV | I11/D3/ADR 2.3.0001: manter os 4 endpoints; fixture de integração com `reportedDate` ausente cobre o `None`/`NaT` (Task 09) |
| Conversão `date→datetime` em fundamentals promove tz errada ou perde os 17 `NaT` | I7: `datetime.combine(..., tzinfo=UTC)`; `None → NaT`; Task 05/10 cobrem report sem `reported_date`; `pandera` `FUNDAMENTAL` (`reported_date` nullable) |
| `requests` (old) não está em deps; adicionar arrasta dependência redundante | **Usar `httpx`** (já em `[project].dependencies>=0.27`) nos adapters AV — sem nova dep, sem tocar `uv.lock`; registrar `[decision]` na §7 (porte `requests→httpx`) |
| Teste de integração bate na API ao vivo (anti-padrão do old; free-tier ~25 req/dia estoura) | I13: `monkeypatch` do cliente `httpx`; live só com `skipif`(sem rede/sem chave); sem rede em import/instanciação |
| `article_id` colide e mascara notícia distinta (ID instável quando `url` ausente) | ID estável `url > f"{published_at}:{headline[:80]}"` (regra do old/adapter); dedup por PK do store é determinístico (I8) |
| Reescrever schema bronze por engano ao "encaixar" os dados | I15: schemas 2.1 batem 1:1 (verificado 6921×8; 81×10/17 `NaT`); **proibido** estender — só reusar |
| Tentar tocar `.importlinter`/`pyproject` achando que precisa de novo container | Desnecessário: `market_data` já é container e sua domain/application já estão em `domain-purity`/`store-no-storage-leak` (2.2, F2.2 — verificado); `httpx` já em deps |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (escopo, contratos §4,
  invariantes §5, casos de erro §6, decisões §7, critérios §11)
- [`../../overview.md`](../../overview.md) — §3/§6/§7/§11
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.3-news-fundamentals-ingestion`
  (`arquivos_a_criar`, `definition_of_done`, `non_goals`)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — §A (reuso só de `raw/`); H-3 (fallback as-of `reported_date` OU
  `fiscal_date_end + 45d`, 3.3); §B linha 2.3 (endpoints AV + dedup + throttle)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches, commits, status
- [`../../LAYOUT.md`](../../LAYOUT.md) §1/§3/§6/§7 — estrutura `features/<feature>/`,
  direção inward, fronteira composition_root
- [`../../PIPELINE.md`](../../PIPELINE.md) §4.3 — Task atômica (port antes de adapter)
- ADRs desta Stage:
  [`2.3.0001`](../../adr/2_3_0001-alpha-vantage-fundamental-endpoints-and-earnings.md),
  [`2.3.0002`](../../adr/2_3_0002-reuse-existing-news-fundamentals-as-default-source.md)
- Stage 2.1 (consumida): `MedallionStore`, schemas bronze `NEWS`/`FUNDAMENTAL`
  (`bronze_schemas.py:76-141`), `FakeMedallionStore`, `DuplicateKeyError`
- Stage 2.2 (padrão espelhado):
  [`../2.2-market-data-ingestion/technical.md`](../2.2-market-data-ingestion/technical.md);
  `features/market_data/application/use_cases/ingest_candles.py`,
  `.../ports/out/candle_fetcher.py`, `.../domain/time/utc.py` (`require_tz_aware`);
  ADR [`2.2.0002`](../../adr/2_2_0002-reuse-raw-candles-default-vs-live-yfinance.md);
  `.importlinter` (container `market_data` + `domain-purity`/`store-no-storage-leak`)
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `ddd-tactical-patterns`, `repository-pattern`, `composition-root`
- Old (semântica, não implementação):
  `src/entities/news_article.py` (`:32-77`), `src/entities/fundamental_report.py`
  (`:32-60`), `src/interfaces/{news_fetcher,fundamental_fetcher}.py` (ABCs → Protocol),
  `src/use_cases/fetch_news_use_case.py` (`:30-269` cursor-walking — **não** portar),
  `src/use_cases/fetch_fundamentals_use_case.py` (`:55-65` filtro; `:86` nunca-vaza),
  `src/adapters/alpha_vantage_news_fetcher.py` (`:32` throttle; `:60-82` parse;
  `:131-135` guard; `:169-170` ID estável),
  `src/adapters/alpha_vantage_fundamental_fetcher.py` (`:30` `_MIN_INTERVAL=12.5`;
  `:89-105` `_to_date`/`_to_float`; `:108-201` merge + 4 endpoints + EARNINGS),
  `src/adapters/parquet_fundamental_repository.py` (`:54` normalização `asset_id`;
  `:93-94` `date↔pd.Timestamp(tz="UTC")`)

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
> não-triviais viram ADR `2_3_NNNN`.

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

### 2026-06-29 — [decision] Task 02 — entity FundamentalReport — Claude (corrida autônoma)
**Contexto:** o old (`fundamental_report.py:48-56`) valida os numéricos com
`isinstance(value, (int, float))`, que aceita `bool` (subclasse de `int`) como
numérico válido — um `revenue=True` passaria silenciosamente.
**Decisão:** endurecer a invariante I2 — `bool` nos cinco numéricos levanta
`TypeError` (`isinstance(value, bool) or not isinstance(value, int | float)`),
mantendo `int` aceito como float (espelhando o old). Coberto por
`test_bool_numeric_field_raises`.
**Razão:** reversível e barato; fecha um caminho de corrupção silenciosa (bool→1.0)
sem custo no caminho legítimo. Não muda o contrato observável dos dados reais (os 81
fundamentos são floats/None). Sem ADR próprio — endurecimento local de invariante.

### 2026-06-29 — [decision] Tasks 08/09 — adapters Alpha Vantage — Claude (corrida autônoma)
**Contexto:** o old usa `requests` (não está em `[project].dependencies`); o plano
(technical §1 / §5) já antecipava o porte para `httpx`.
**Decisão:** os adapters `AlphaVantageNewsFetcher`/`AlphaVantageFundamentalFetcher`
usam `httpx.Client` (já em deps, `>=0.27`) no lugar de `requests`. O cliente é
injetável no construtor (`client: httpx.Client | None`) para teste offline; sem
`client`, um `httpx.Client` é criado na construção (sem rede até o primeiro `get`).
**Razão:** sem nova dependência, sem tocar `uv.lock`; mantém o adapter trocável e
testável sem rede (I13). Sem ADR próprio — porte de biblioteca dentro do escopo do
adapter, decisão já declarada no concept/technical.

### 2026-06-29 — [deviation] Tasks 06/07 — adapters parquet de reuso — Claude (corrida autônoma)
**Contexto:** `arquivos_a_criar` do roadmap/technical lista só os adapters Alpha
Vantage; `ParquetRawNewsFetcher`/`ParquetFundamentalFetcher` (origem default) foram
adicionados conforme concept §1/§7 D2 e ADR 2.3.0002.
**Razão:** a DoD exige reuso do parquet existente como origem de produção; sem o
adapter de reuso, o reuso só existiria em fixture e a paridade fake↔real do contract
test ficaria sem o "real". Adição justificada e já prevista no concept (ADR
2.3.0002) — `[deviation]` registrado por completude.

### 2026-06-29 — [deviation] Task 10 — testes read-all vs parquet real — Claude (corrida autônoma)
**Contexto:** o plano da Task 10 (technical §2) previa estabilizar os contract tests
contra os parquet reais; os contract tests (Tasks 06/07) ficaram herméticos
(parquet sintético em `tmp_path`).
**Decisão:** criar dois testes de integração `read-all` dedicados
(`tests/integration/.../parquet/test_parquet_raw_news_fetcher.py` e
`test_parquet_fundamental_fetcher.py`), espelhando `test_parquet_raw_candle_fetcher`
da 2.2, com `skipif` se o parquet real estiver ausente. Provam 6921 news válidas
(UTC, `article_id` non-null) e 81 fundamentos (17 `NaT` → `None`).
**Razão:** mantém os contract tests rápidos/herméticos e isola a leitura completa do
real num teste de integração marcado — mesma postura já adotada na 2.2. Zero linha
legítima reprovou; os 17 `NaT` confirmados como `None`.

### 2026-06-29 — [finding] campos opcionais de news non-null no schema bronze — Claude
**Contexto:** confirmado em execução (concept §7 D5): a entity `NewsArticle` declara
`url`/`article_id`/`language` opcionais, mas o schema bronze `NEWS` exige as 8
colunas `nullable=False`. O `IngestNews` resolve com fallback non-null no row-mapper
(`url`/`summary`/`language` vazio → `""`; `article_id` via ID estável). O parquet
real de AAPL, porém, já vem com as 8 colunas todas non-null (0 nulos verificados).
**Direção sugerida:** quando a 3.2 (`sentiment-finbert`, `depends_on: 2.3`) ler a
bronze `news`, tratar `url`/`language` `""` como "ausente" (não confundir com URL
vazia legítima); o `article_id` é sempre uma chave estável, não necessariamente uma
URL. Stage candidata: 3.2.

<!-- END: post-execution -->