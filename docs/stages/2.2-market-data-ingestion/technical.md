---
title: Technical — Stage 2.2 — Ingestão de candles de mercado (market_data)
description: Plano de execução da Stage 2.2 — Tasks ordenadas inside-out (domain Candle + UTC → port CandleFetcher + use case IngestCandles + fake → adapters parquet-raw/yfinance → market_data como container layered no import-linter), 1 Task = 1 commit, pronto para code assistant
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, market-data-ingestion, candle, candle-fetcher, ingest-candles, bronze, medallion-store, parquet-raw, yfinance, import-linter, layered-container, ohlc-invariants, utc]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 2.2-market-data-ingestion
stage_title: Ingestão de candles de mercado
step_id: 2
step_title: Camada bronze + calendário
depends_on: [2.1-medallion-storage-contracts]
concept_ref: ./concept.md
issue_id: 19
branch: feat/19-2-2-market-data-ingestion
tasks_count: 9
---

# Technical — Stage 2.2 — Ingestão de candles de mercado (`market_data`)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.2/task-NN]`, body em bullets,
>    rodapé `Refs #19`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[finding]`/`[deviation]`. Esta é corrida autônoma overnight
>    (ADR `0.0.0050`): **não perguntar** — decidir com julgamento, registrar e seguir.
> 7. **Fechamento NÃO é desta sessão.** O commit `stage 2.2: complete` e a marcação
>    `done` no `roadmap.md` são do **orquestrador**, após auditoria independente.
>    Esta sessão entrega concept/technical/código/testes commitados e gates verdes.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/19-2-2-market-data-ingestion`. Não há sub-PRs internos. Fluxo Git completo:
> [`GIT-WORKFLOW.md`](../../GIT-WORKFLOW.md).

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage cria o **primeiro bounded context de _feature_** — `market_data` — em
`src/financial_forecasting/features/market_data/`, com as três camadas hexagonais
(`domain` ← `application` ← `adapters/out`). Entrega: a entity `Candle` (frozen,
stdlib-only, invariantes OHLC fortes), helpers UTC de domínio, o port-out
`CandleFetcher` (`Protocol`), o use case `IngestCandles` (DTO frozen in/out, grava
bronze `candle` via `MedallionStore` da 2.1 injetando `asset`), os adapters
`ParquetRawCandleFetcher` (origem **default**, lê o raw existente sem re-baixar) e
`YfinanceCandleFetcher` (não-default, teste de integração **sem** rede), um
`FakeCandleFetcher` comportamental, e a prova **inward-only** do BC novo
adicionando `market_data` aos `containers` do contrato `hexagonal-layers` no
`.importlinter`.

### Estratégia

Ordem **inside-out / TDD** (skill `task-ordering-hex`, default de vertical-slice),
cada Task deixando o build verde:

1. **Domain primeiro** (Tasks 01–02): `Candle` + invariantes (sem dependentes) e
   helpers UTC. Nenhuma camada acima existe ainda — testes unit no mesmo commit.
2. **Application** (Tasks 03–04): port `CandleFetcher` (`Protocol`) **antes** de
   qualquer adapter (regra dura §4.3 PIPELINE: port antes de adapter, e **não**
   misturar criação de port com criação de adapter no mesmo commit). Em seguida o
   use case `IngestCandles` + `FakeCandleFetcher` + teste do use case com os DOIS
   fakes (`FakeCandleFetcher` novo + `FakeMedallionStore` reusado da 2.1) — use
   case testável sem infra externa.
3. **Adapters out** (Tasks 05–06): `ParquetRawCandleFetcher` (real, origem default)
   com contract test parametrizado **paridade fake↔real**; depois
   `YfinanceCandleFetcher` (real, não-default) com teste de integração via
   `monkeypatch` (nunca rede).
4. **Gate de arquitetura** (Task 07): adicionar `market_data` aos `containers` do
   `hexagonal-layers` no `.importlinter` e `yfinance>=0.2` ao `pyproject.toml` —
   só aqui, **depois** que as três camadas físicas existem, a prova inward-only
   tem o que medir. Quebra intencional (`import pandas` no domain) reprova e é
   revertida.
5. **Verificações de fechamento** (Tasks 08–09): contract test paridade
   fake↔real estabilizado contra o raw real (4024 linhas) + `make check`/`make
   test`/cobertura ≥90% no diff. (Task 08 cobre o caso de o contract test do port
   precisar de ajuste fino ao casar contra o raw real; Task 09 é o gate agregado.)

**Decisão de ordering declarada:** as Tasks 01–02 (domain) NÃO têm dependentes até
a Task 03; o port (Task 03) precede ambos os adapters (Tasks 05–06); o
`.importlinter` (Task 07) só é tocado **após** as camadas existirem fisicamente,
pois o contrato `type=layers` precisa dos módulos reais para provar a direção.

### Pré-condições

- Stage `2.1-medallion-storage-contracts` em `done` (`MedallionStore`,
  `ParquetMedallionStore`, schema bronze `CANDLE`, `FakeMedallionStore`,
  `DuplicateKeyError` disponíveis) — **verificado** no repo.
- Branch `feat/19-2-2-market-data-ingestion` em checkout (já criada).
- Raw real presente em
  `data/raw/market/candles/AAPL/candles_AAPL_1d.parquet` — **verificado**
  (154 KB, ~4024 linhas, 6 colunas sem `asset`).

### Premissas técnicas

- Python 3.12, `uv`, `mypy --strict`, `ruff`, `pytest`.
- `features/` está **vazio** hoje (só `__init__.py`); `market_data` é o primeiro
  feature container — o `.importlinter` (linha 42 verbatim) já previu "cada feature
  vira container ao ganhar layers".
- Schema bronze `CANDLE` (2.1): `logical_pk=(asset, timestamp)`, colunas
  `asset(str)`/`timestamp(UTC)`/`open|high|low|close(float32)`/`volume(int64)`,
  `strict=True`, `coerce=False`. **Reusado, não redefinido** — o use case produz
  `Row`s que casam com ele (D4/I9).
- `yfinance` não exige chave de API; o adapter é construível, mas o teste de
  integração **não** depende de rede (robustez overnight, I13).

### Estrutura de pastas afetada

```
src/financial_forecasting/features/market_data/
├── domain/
│   ├── entities/candle.py                          # Task 01
│   └── time/utc.py                                 # Task 02
├── application/
│   ├── ports/out/candle_fetcher.py                 # Task 03
│   └── use_cases/ingest_candles.py                 # Task 04
└── adapters/out/
    ├── parquet/parquet_raw_candle_fetcher.py       # Task 05
    └── yfinance/yfinance_candle_fetcher.py         # Task 06
tests/
├── unit/features/market_data/domain/
│   ├── test_candle.py                              # Task 01
│   └── test_utc.py                                 # Task 02
├── unit/features/market_data/application/
│   └── test_ingest_candles.py                      # Task 04
├── fakes/features/market_data/
│   └── in_memory_candle_fetcher.py                 # Task 04
├── contract/features/market_data/
│   └── test_candle_fetcher_contract.py             # Tasks 05, 08
└── integration/features/market_data/adapters/out/yfinance/
    └── test_yfinance_candle_fetcher.py             # Task 06
.importlinter                                       # Task 07
pyproject.toml / uv.lock                            # Task 07
```

(Os `__init__.py` intermediários das novas pastas `features/market_data/**` e
`tests/**/features/market_data/**` são criados junto da primeira Task que toca
cada pasta.)

## 2. Tasks

> Faixa saudável: **3–8 Tasks**. Esta Stage tem **9** (decisões já fechadas no
> concept; cada Task fica pequena e com check objetivo — dentro da faixa de
> governança da corrida autônoma, ver concept §12).

### Task 01 — entity `Candle` + invariantes OHLC fortes (domain)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/domain/entities/candle.py`
  - `tests/unit/features/market_data/domain/test_candle.py`
  - `__init__.py` em `features/market_data/`, `.../domain/`, `.../domain/entities/`
    e nas pastas de teste correspondentes.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `Candle` como `@dataclass(frozen=True)`, **domain puro
  stdlib-only** (só `dataclasses` + `datetime`), campos
  `asset: str`, `timestamp: datetime`, `open/high/low/close: float`,
  `volume: int`; identidade lógica `(asset, timestamp)`. `__post_init__` valida as
  invariantes OHLC fortes e levanta `ValueError` em qualquer violação.
- **Detalhes técnicos:**
  - **I1** — `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`.
  - **I2** — todos os `open/high/low/close/volume` `>= 0`.
  - **I3** — nenhum campo `None` (checagem explícita; frozen não impede `None`).
  - **I4** — `timestamp` tz-aware (delega a `require_tz_aware`; naive → `ValueError`).
    A **normalização** a `00:00 UTC` é feita na fronteira do adapter (Tasks 05/06),
    não na entity; a entity exige apenas tz-aware UTC.
  - **I5** — `asset` faz parte da identidade (não validar duplicidade aqui — I6/D5).
  - Mensagens de erro claras por invariante.
- **Critério de aceite (A1):** unit test cobre `Candle` válido + uma violação por
  invariante (`high < close`, `low > open`, `high < low`, valor negativo, campo
  `None`, `timestamp` naive) → cada uma `ValueError`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/domain/test_candle.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/domain/entities/candle.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data/domain): entity Candle com invariantes OHLC fortes [2.2/task-01]`

---

### Task 02 — helpers UTC de domínio (domain)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/domain/time/utc.py`
  - `tests/unit/features/market_data/domain/test_utc.py`
  - `__init__.py` em `.../domain/time/`.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** reimplementar, em domínio puro (stdlib `datetime` only), os
  helpers UTC portados do old com julgamento: `require_tz_aware(dt, name) -> None`,
  `to_utc(dt) -> datetime`, `ensure_utc(dt) -> datetime`,
  `parse_iso_utc(value: str) -> datetime`, mais um helper de **normalização ao
  `00:00 UTC` do dia** (usado pelos adapters no diário).
- **Detalhes técnicos:**
  - `require_tz_aware` levanta `ValueError` se `dt.tzinfo is None`.
  - `to_utc` exige tz-aware e converte (`astimezone(UTC)`); `ensure_utc` assume UTC
    se naive (uso só em fronteira/parse, não em domínio puro de adapter).
  - `parse_iso_utc` aceita `Z`/offset/sem tz (ver old); retorna tz-aware UTC.
  - Normalização diária: `datetime.combine(dt_utc.date(), time(0,0), tzinfo=UTC)`.
  - Endereça **I4** (entity) e a normalização temporal usada em Tasks 05/06.
- **Critério de aceite (A2):** unit test cobre tz-aware ok, naive → `ValueError`
  (em `require_tz_aware`/`to_utc`), conversão de outra tz para UTC, parse de cada
  formato ISO aceito, e normalização a `00:00 UTC`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/domain/test_utc.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/domain/time/utc.py
  ```
- **Commit sugerido:** `feat(market-data/domain): helpers UTC tz-aware e normalização diária [2.2/task-02]`

---

### Task 03 — port-out `CandleFetcher` (`Protocol`) (application)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/application/ports/out/candle_fetcher.py`
  - `__init__.py` em `.../application/`, `.../application/ports/`,
    `.../application/ports/out/`.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `CandleFetcher` como `typing.Protocol` estrutural
  (não ABC — D2/I11), método
  `fetch_candles(self, symbol: str, start: datetime, end: datetime) -> list[Candle]`,
  tipos stdlib + a entity `Candle`. Sem import de `adapters`/`pandas`.
- **Detalhes técnicos:**
  - Import de `Candle` é runtime aqui (a `application` pode importar o `domain`);
    não precisa de `TYPE_CHECKING`.
  - Docstring documenta a semântica temporal: `start`/`end` tz-aware,
    `Candle.timestamp` sempre UTC (no diário, `00:00 UTC`).
  - **Não** criar adapter nesta Task (regra dura §4.3: port e adapter em commits
    separados).
- **Critério de aceite (A3):** o módulo importa (`Protocol` sem corpo), `mypy
  --strict` verde; nenhum import de `adapters`/`pandas`/`pyarrow`.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/features/market_data/application/ports/out/candle_fetcher.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data/application): port-out CandleFetcher (Protocol) [2.2/task-03]`

---

### Task 04 — use case `IngestCandles` + DTOs frozen + `FakeCandleFetcher` + teste (application)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/application/use_cases/ingest_candles.py`
  - `tests/fakes/features/market_data/in_memory_candle_fetcher.py`
  - `tests/unit/features/market_data/application/test_ingest_candles.py`
  - `__init__.py` em `.../application/use_cases/` e nas pastas de teste/fake.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `IngestCandlesRequest`/`IngestCandlesResult` (dataclasses
  frozen), o use case `IngestCandles` (injeta `CandleFetcher` + `MedallionStore`,
  `execute(request) -> IngestCandlesResult`), o `FakeCandleFetcher` comportamental
  (stdlib-only, **não** `Mock`, devolve `list[Candle]` pré-carregada) e o teste do
  use case usando `FakeCandleFetcher` + `FakeMedallionStore` (reusado da 2.1).
- **Detalhes técnicos:**
  - DTOs (concept §4): `Request{asset, start, end}` (tz-aware),
    `Result{asset, ingested, start, end}`. **Nunca** devolve `Candle`/`tuple` (I7/D6).
  - `execute`: chama `fetcher.fetch_candles(symbol=request.asset, start, end)`,
    mapeia cada `Candle → Row` (`Mapping[str, object]`) **injetando `asset`**
    (I9/D4) e preservando dtypes-alvo (`open/high/low/close`→`float32`,
    `volume`→`int64`; I10), e grava
    `store.write(layer="bronze", table="candle", rows=..., overwrite=False)`.
    Devolve `Result(ingested=len(rows), ...)`.
  - Validação de fronteira: `start`/`end` tz-aware e `start <= end` (C5,
    via helper UTC) → `ValueError`.
  - **Duplicados (I6/D5):** delegar a colisão de PK ao `MedallionStore`
    (`DuplicateKeyError` com `overwrite=False`); não reimplementar dedup. Se a
    execução mostrar necessidade de pré-checagem na coleção, registrar `[decision]`
    na §7 (concept §13 deixou isso aberto a julgamento).
  - **Nota de dtype no fake/teste:** o mapeamento `Candle → Row` parte de
    `float`/`int` Python; a coerção para `float32`/`int64` casando `coerce=False`
    do bronze é responsabilidade do adapter de **escrita** (`ParquetMedallionStore`,
    2.1) — o teste do use case asserta a **presença** de `asset` e a forma das
    `Row`s; a fidelidade de dtype contra o schema real é provada no caminho real
    (Task 05/contract + rede de segurança `pandera` em C3). Se surgir gap de dtype,
    registrar `[decision]`/`[deviation]` na §7.
- **Critério de aceite (A5):** teste com fakes cobre: `asset` injetado em **toda**
  `Row`; chamada a `write` com `layer="bronze"`, `table="candle"`,
  `overwrite=False`; `Result.ingested` == nº de candles; retorno é
  `IngestCandlesResult` (nunca `Candle`/`tuple`); colisão de PK propaga
  `DuplicateKeyError`; `start > end`/naive → `ValueError`. Cobertura ≥90% no use case.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/market_data/application/test_ingest_candles.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/application/use_cases/ingest_candles.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(market-data/application): use case IngestCandles + DTO + fake do fetcher [2.2/task-04]`

---

### Task 05 — adapter `ParquetRawCandleFetcher` (origem default) + contract test paridade fake↔real

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/adapters/out/parquet/parquet_raw_candle_fetcher.py`
  - `tests/contract/features/market_data/test_candle_fetcher_contract.py`
  - `__init__.py` em `.../adapters/`, `.../adapters/out/`,
    `.../adapters/out/parquet/` e nas pastas de teste.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar `ParquetRawCandleFetcher` (implementa o `Protocol`
  `CandleFetcher` por duck-typing) lendo o parquet raw existente
  (`data/raw/market/candles/AAPL/candles_AAPL_1d.parquet`) e mapeando para
  `list[Candle]`; criar o contract test parametrizado que roda o **mesmo** contrato
  sobre `FakeCandleFetcher` e `ParquetRawCandleFetcher` (paridade fake↔real, I14).
- **Detalhes técnicos:**
  - `pandas`/`pyarrow` vivem **só** aqui (D3). Construtor recebe o caminho do raw
    (default = constante do adapter; injetável p/ teste — concept §13 deixa
    constante vs `Settings` a julgamento; usar constante simples-e-trocável e
    registrar `[decision]` se divergir).
  - Mapeia cada linha → `Candle` preservando `float32`/`int64` e tz UTC; normaliza
    `timestamp` a `00:00 UTC` via helper (Task 02). Injeta `asset` (do `symbol`
    pedido) ao construir cada `Candle` (o raw não tem `asset` — D4).
  - Filtra por `[start, end]` tz-aware (require_tz_aware na fronteira; C5).
  - Arquivo ausente/ilegível → erro de aplicação claro, **não** lista vazia (C4).
  - **Paridade fake↔real (I14):** o contract test segue a postura da 2.1
    (`tests/contract/shared/test_medallion_store_contract.py`): fixture
    parametrizada `[fake, real]`, mesmos asserts de contrato — `fetch_candles`
    devolve `list[Candle]`, todos tz-aware UTC, invariantes OHLC respeitadas,
    `start > end` → `ValueError`. O real lê o raw existente (não baixa).
- **Critério de aceite (A4/A6):** contract test verde para `[fake, real]`; o real
  lê o raw (4024 linhas) e produz `Candle`s válidos com dtypes preservados e tz UTC;
  `import-linter`/`check_layout` não acusam `pandas` fora do adapter.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/market_data/test_candle_fetcher_contract.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/adapters/out/parquet/parquet_raw_candle_fetcher.py
  ```
- **Commit sugerido:** `feat(market-data/adapters): ParquetRawCandleFetcher (raw default) + contract test paridade [2.2/task-05]`

---

### Task 06 — adapter `YfinanceCandleFetcher` (não-default) + teste de integração sem rede

- **Arquivos a criar:**
  - `src/financial_forecasting/features/market_data/adapters/out/yfinance/yfinance_candle_fetcher.py`
  - `tests/integration/features/market_data/adapters/out/yfinance/test_yfinance_candle_fetcher.py`
  - `__init__.py` em `.../adapters/out/yfinance/` e nas pastas de teste.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** portar do old com julgamento o `YfinanceCandleFetcher`
  (implementa `CandleFetcher`): retry + backoff exponencial, normalização de
  `MultiIndex`, tz→`00:00 UTC` (helper Task 02), validação de colunas
  `Open/High/Low/Close/Volume`; teste de integração via `monkeypatch` de
  `yf.download` — **nunca** bate na API ao vivo (I13).
- **Detalhes técnicos:**
  - `yfinance` (`import yfinance as yf`) vive **só** aqui.
  - Construtor: `max_retries`, `retry_delay` (como o old). `require_tz_aware` em
    `start`/`end`; `start <= end` (C5). Injeta `asset=symbol` em cada `Candle`.
  - `df` vazio / colunas faltando, após esgotar retries → erro do adapter (C6); não
    afeta o caminho default (parquet).
  - Teste de integração: `@pytest.mark.integration`, `monkeypatch.setattr(yf,
    "download", fake_df_fn)` devolvendo um `DataFrame` fixture (com `MultiIndex` e
    tz-naive p/ exercitar a normalização); um teste live opcional com
    `pytest.mark.skipif(<sem rede>)` (não roda no CI overnight).
  - **Proveniência:** este arquivo está em `arquivos_a_criar` do roadmap; o
    `ParquetRawCandleFetcher` (Task 05) é a adição justificada por finding
    (registrar `[deviation]` na §7 referenciando ADR `2.2.0002`).
- **Critério de aceite (A7):** teste de integração com `monkeypatch` verde, **sem**
  acesso a rede; normalização `MultiIndex`/tz→`00:00 UTC` exercitada; colunas
  faltando → erro do adapter; live só com `skipif`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/market_data/adapters/out/yfinance/test_yfinance_candle_fetcher.py -v
  uv run mypy --strict src/financial_forecasting/features/market_data/adapters/out/yfinance/yfinance_candle_fetcher.py
  ```
- **Commit sugerido:** `feat(market-data/adapters): YfinanceCandleFetcher com retry/backoff e teste sem rede [2.2/task-06]`

---

### Task 07 — `market_data` como container layered no `.importlinter` + dependência `yfinance`

- **Arquivos a modificar:**
  - `.importlinter` (adicionar `market_data` aos `containers` de `hexagonal-layers`)
  - `pyproject.toml` (`yfinance>=0.2` em `[project].dependencies`)
  - `uv.lock` (sincronizado via `uv lock`)
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar
  `financial_forecasting.features.market_data` à lista `containers` do contrato
  `hexagonal-layers` (mantendo `exhaustive = False` — não há `adapters/in`/`ports/in`
  nesta Stage), provando inward-only (`domain` ← `application` ← `adapters`) no BC
  novo (D1/I8). Adicionar `yfinance>=0.2` e rodar `uv lock`.
- **Detalhes técnicos:**
  - Só esta Task toca `.importlinter` — e só **depois** que as três camadas
    físicas existem (Tasks 01–06), senão o contrato `type=layers` não tem módulos
    para medir.
  - **Prova por quebra intencional (A8):** inserir temporariamente `import pandas`
    no `domain` de `market_data`, rodar `uv run lint-imports` → deve **reprovar**
    (`hexagonal-layers`/`domain-purity`); reverter a quebra → verde. Registrar a
    quebra/reversão na §7 se relevante.
  - Conferir que `store-no-storage-leak`/`domain-purity` continuam cobrindo só
    `shared.*` (a pureza do domain de `market_data` é coberta por `hexagonal-layers`
    + a ausência de imports proibidos; se a execução mostrar que o domain de feature
    precisa de cobertura `forbidden` explícita, registrar `[finding]` p/ Stage de
    contratos).
- **Critério de aceite (A8):** `uv run lint-imports` verde com `market_data` nos
  `containers`; quebra intencional reprova e é revertida; `check_layout.py` verde
  para a estrutura da feature; `yfinance>=0.2` em `[project].dependencies` com
  `uv.lock` sincronizado.
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run python scripts/check_layout.py
  uv lock --check || uv lock
  ```
- **Commit sugerido:** `chore(import-linter): market_data como container layered + dependência yfinance [2.2/task-07]`

---

### Task 08 — estabilizar contract test do `CandleFetcher` contra o raw real

- **Arquivos a modificar:**
  - `tests/contract/features/market_data/test_candle_fetcher_contract.py` (ajustes
    finos se o raw real exigir; ex.: tolerância de invariante OHLC por float —
    risco §10 do concept).
- **Arquivos a criar:** nenhum.
- **O que fazer:** rodar o contract test paridade fake↔real contra as 4024 linhas
  reais e estabilizar: garantir que **todas** as linhas legítimas do raw passam as
  invariantes OHLC fortes (I1) e que fake e real respondem idênticos ao mesmo
  contrato. Se alguma linha legítima reprovar por ruído de `float32`
  (`high` ligeiramente < `close`), tratar com critério (não tolerância arbitrária):
  comparar com a precisão correta do dtype ou ajustar a invariante para o domínio
  do dtype, registrando `[decision]` na §7.
- **Detalhes técnicos:**
  - Esta Task é o ponto de verdade do risco "invariantes OHLC rejeitam linhas
    legítimas do raw" (concept §10). Se nenhuma linha reprovar, a Task vira um
    no-op de confirmação (pode ser dobrada na Task 05 via `[deviation]` se nada
    mudar — registrar).
- **Critério de aceite:** contract test verde sobre `[fake, real]` com o raw real
  completo; nenhuma linha legítima falsamente rejeitada; qualquer ajuste de
  invariante registrado como `[decision]`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/market_data/test_candle_fetcher_contract.py -v
  ```
- **Commit sugerido:** `test(market-data): contract test do CandleFetcher estável contra o raw real [2.2/task-08]`

---

### Task 09 — gate agregado da Stage (check + cobertura)

- **Arquivos a modificar:** nenhum esperado (correções pontuais se um gate acusar).
- **Arquivos a criar:** nenhum.
- **O que fazer:** rodar o gate agregado da Stage e garantir tudo verde:
  `make check` (ruff + mypy + import-linter + check_layout + testes), `make test`,
  cobertura ≥90% no diff (I15). Conferir A9/A10 (ADRs `2.2.0001`/`2.2.0002` em
  `status: accepted` — já presentes no repo).
- **Detalhes técnicos:**
  - Se algum gate acusar, corrigir de forma mínima dentro do escopo da Stage
    (sem novos contratos) e re-rodar.
  - **Não** fazer o commit `stage 2.2: complete` nem marcar `done` no roadmap —
    isso é do orquestrador após auditoria (ver preâmbulo). Esta Task entrega a
    branch com gates verdes.
- **Critério de aceite (A9/A10):** `make check` e `make test` verdes; cobertura
  ≥90% no diff; `import-linter` verde com `market_data` nos containers; ADRs
  `accepted`.
- **Comando de verificação:**
  ```bash
  make check
  make test
  uv run pytest --cov=financial_forecasting.features.market_data --cov-report=term-missing tests/
  ```
- **Commit sugerido:** `test(market-data): gate verde da Stage 2.2 (check + cobertura) [2.2/task-09]`
  (omitir se a Task não produzir mudança de arquivo — neste caso é só verificação.)

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 2.2: complete` (feito pelo **orquestrador**, não por esta sessão) e ser
> mergeada em `develop`.

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
make test                 # todos os testes (unit + contract + integration)
uv run lint-imports       # market_data nos containers de hexagonal-layers
uv run python scripts/check_layout.py
uv run pytest --cov=financial_forecasting.features.market_data --cov-report=term-missing tests/
```

### Verificações funcionais
- [ ] Executar `IngestCandles` para `AAPL`/`1d` com `ParquetRawCandleFetcher`
      (origem default) + `FakeMedallionStore` lê o raw existente (sem re-baixar),
      valida OHLC, injeta `asset`, grava `(bronze, candle)` e devolve
      `IngestCandlesResult` com `ingested == 4024` (nunca uma `Candle`).
- [ ] `FakeCandleFetcher` e `ParquetRawCandleFetcher` passam o **mesmo** contract
      test parametrizado do port (paridade fake↔real).
- [ ] Quebra intencional (`import pandas` no domain de `market_data`) reprova no
      `import-linter` e é revertida.
- [ ] Teste de integração do `YfinanceCandleFetcher` roda **sem** acesso a rede.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — OHLC consistente | `test_candle.py` (cada violação → `ValueError`); contract test sobre o raw real (Task 08) |
| I2 — Não-negatividade OHLCV | `test_candle.py` (valor negativo → `ValueError`) |
| I3 — Sem nulos | `test_candle.py` (campo `None` → `ValueError`) |
| I4 — Timestamp tz-aware UTC normalizado | `test_candle.py` (naive → `ValueError`) + `test_utc.py` (normalização `00:00 UTC`) |
| I5 — Identidade `(asset, timestamp)` | `test_candle.py` (asset presente); contract test (asset injetado) |
| I6 — Sem duplicados (coleção) | `test_ingest_candles.py` (colisão → `DuplicateKeyError` via `FakeMedallionStore`) |
| I7 — Use case não vaza entity | `test_ingest_candles.py` (retorno é `IngestCandlesResult`, nunca `Candle`/`tuple`) |
| I8 — Pureza do domínio | `lint-imports` (quebra intencional reprova, Task 07) + `check_layout.py` |
| I9 — Injeção de `asset` | `test_ingest_candles.py` (asset em toda `Row`); contract test do parquet |
| I10 — Preservação de dtype | `test_ingest_candles.py` / contract test (forma `float32`/`int64`); rede de segurança `pandera` no `write` |
| I11 — Forma `Protocol` do port | `mypy --strict` + ausência de herança ABC; adapters satisfazem por duck-typing |
| I12 — Origem default = raw | contract test `ParquetRawCandleFetcher` lê o raw existente (Task 05) |
| I13 — Integração não bate na API | `test_yfinance_candle_fetcher.py` (`monkeypatch`, sem rede; live só `skipif`) |
| I14 — Paridade fake↔real | `test_candle_fetcher_contract.py` parametrizado `[fake, real]` |
| I15 — Gates verdes | `make check` / `make test` / cobertura ≥90% (Task 09) |

### Checklist de fechamento da Stage
- [ ] Todas as 9 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` e `make test` verdes no branch; cobertura ≥90% no diff
- [ ] ADRs `2.2.0001` e `2.2.0002` em `status: accepted`
- [ ] `concept.md`/`technical.md` desta Stage não precisam de retoque material
- [ ] **(orquestrador, pós-auditoria)** commit `stage 2.2: complete` aplicado e
      `roadmap.md` marcado `done` — **fora do escopo desta sessão**

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out). Explícito:

```
Task 01 (Candle) ─┬─► Task 03 (port) ─► Task 04 (use case + fake)
Task 02 (UTC) ────┘                          │
                                             ├─► Task 05 (parquet adapter + contract) ─► Task 08 (contract vs raw real)
                                             └─► Task 06 (yfinance adapter)
Task 05 + Task 06 ─► Task 07 (.importlinter container + yfinance dep)
Task 07 + Task 08 ─► Task 09 (gate agregado)
```

- Task 03 depende de 01 (o port tipa `Candle`); 04 depende de 03 (consome o port)
  e de 02 (validação UTC); 05/06 dependem de 03 (implementam o port) e de 02
  (normalização tz); 07 depende de 05+06 (camada `adapters` precisa existir para o
  contrato `type=layers` provar a direção); 08 estabiliza o contract test de 05
  contra o raw real; 09 é o gate agregado final.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Invariantes OHLC fortes rejeitam linhas legítimas do raw por ruído de `float32` (concept §10) | Task 08 isola o risco; comparar na precisão do dtype (não tolerância arbitrária); registrar `[decision]` |
| Mapeamento promove `float32`→`float64` / `volume`→`float`, quebrando `coerce=False` do bronze (I10) | Asserts de forma no teste do use case + contract test; rede de segurança `pandera` no `write` (C3); registrar `[decision]` se exigir coerção explícita no adapter |
| Esquecer de injetar `asset` → `pandera strict` rejeita (I9) | Teste do use case verifica `asset` em toda `Row`; contract test do parquet grava de fato |
| `import-linter` não detecta vazamento por `market_data` ainda não ser container | Task 07 adiciona o container; quebra intencional (`import pandas` no domain) prova a detecção e é revertida |
| Domain de feature sem cobertura `forbidden` explícita (só `hexagonal-layers`) | Se necessário, `[finding]` para Stage de contratos estender `domain-purity`/`store-no-storage-leak` a `features.**.domain`/`application` |
| Teste de integração do yfinance tenta bater na rede (anti-padrão do old) | `monkeypatch` de `yf.download`; live só com `skipif(sem rede)` + `@pytest.mark.integration` (I13) |
| `yfinance` arrasta deps pesadas / conflito no `uv lock` | Pin `>=0.2`; se conflito, fixar versão compatível e registrar `[deviation]` |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (escopo, contratos §4,
  invariantes §5, casos de erro §6, decisões §7, critérios §11)
- [`../../overview.md`](../../overview.md) — §3/§6/§7/§11
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.2-market-data-ingestion`
  (`arquivos_a_criar`, `definition_of_done`, `non_goals`)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — §A (reuso só de `raw/`), H-1/H-2/H-3
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches, commits, status
- [`../../LAYOUT.md`](../../LAYOUT.md) §1/§3/§6/§7 — estrutura `features/<feature>/`,
  direção inward, fronteira composition_root
- [`../../PIPELINE.md`](../../PIPELINE.md) §4.3 — Task atômica (port antes de adapter)
- ADRs desta Stage:
  [`2.2.0001`](../../adr/2_2_0001-market-data-feature-as-layered-container.md),
  [`2.2.0002`](../../adr/2_2_0002-reuse-raw-candles-default-vs-live-yfinance.md)
- Stage 2.1 (consumida): `MedallionStore`, schema bronze `CANDLE`,
  `FakeMedallionStore`, `DuplicateKeyError`; ADRs `2.1.0001`/`2.1.0002`
- ADR de fundação `1.3.0001` (container layered por feature); `.importlinter`
  linha 42 (verbatim)
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `ddd-tactical-patterns`, `import-linter-rules`, `repository-pattern`
- Old (semântica, não implementação): `src/entities/candle.py`,
  `src/interfaces/candle_fetcher.py`, `src/use_cases/fetch_candles_use_case.py`,
  `src/adapters/yfinance_candle_fetcher.py`, `src/domain/time/utc.py`

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
> não-triviais viram ADR `2_2_NNNN`.

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

### 2026-06-29 — [decision] import-linter — pureza do domain/application do BC novo — code assistant
**Contexto:** A Task 07 (A8) exige que `import pandas` no domain de `market_data`
**reprove**. Verificado por quebra intencional que, com `market_data` apenas nos
`containers` de `hexagonal-layers`, **NÃO reprovava**: o contrato `type=layers`
prova só a DIREÇÃO (domain não importa application/adapters), não a pureza de lib
externa do domain de feature; `domain-purity` e `store-no-storage-leak` tinham
`source_modules` só em `shared.*`; o `check_layout.py` não lista pandas/pyarrow
para `/domain/`.
**Decisão:** Estender `domain-purity` para `source_modules += features.market_data.domain`
e `store-no-storage-leak` para `+= features.market_data.{application,domain}`. Com
isso a quebra intencional reprova (exit 1) e foi revertida; clean build segue verde
(7/7 KEPT). Cada nova feature com domain/application entra nestes contratos (mesma
postura do `shared.*`).
**Razão:** Skill `import-linter-rules` ("toda regra de LAYOUT vira contrato; não
silenciar com noqa") + concept 2.2 D1/I8 (a 1ª feature precisa de prova mecânica de
pureza). Antecipado em concept §7 D1 ("se o domain de feature precisar de cobertura
forbidden explícita, registrar finding"). Custo baixo (duas linhas), fecha o gap na
origem em vez de empurrar pra Stage de contratos. Coberto pela intenção do ADR
`2.2.0001` (feature como container layered provado inward-only) — sem ADR novo.

### 2026-06-29 — [deviation] git — escopo de commit com `.` em vez de `/` — code assistant
**Contexto:** Os commits sugeridos em §2 usam escopo `market-data/domain`,
`market-data/application`, `market-data/adapters`. O hook `check_commit_msg.py`
restringe o escopo a `[a-z0-9._-]+` (sem `/`).
**Razão:** Para preservar a informação de camada no escopo sem violar o hook, usei
`.` no lugar de `/` (`market-data.domain`, `market-data.application`,
`market-data.adapters`) — padrão já aceito pelo próprio hook (exemplo
`fix(payment.retry)`). Ajuste cosmético, sem efeito na estrutura.

### 2026-06-29 — [deviation] deps — `yfinance` adicionado na Task 06 (não na 07) — code assistant
**Contexto:** O plano colocava `yfinance>=0.2` + `uv lock` na Task 07. Mas o
`YfinanceCandleFetcher` (Task 06) faz `import yfinance`, e seu teste de integração
(Task 06) não importa/coleta sem a lib instalada.
**Razão:** A dependência foi adicionada ao `pyproject.toml` + `uv.lock` na Task 06
(onde o import nasce), deixando a Task 07 só com o `.importlinter`. Mantém cada Task
com build verde (port-antes-de-adapter intacto). Sem efeito no conteúdo entregue.

### 2026-06-29 — [deviation] adapters — `ParquetRawCandleFetcher` como adição justificada — code assistant
**Contexto:** O `roadmap.md` lista em `arquivos_a_criar` só o `yfinance_candle_fetcher.py`;
o `ParquetRawCandleFetcher` (origem default, lê o raw existente) não está lá.
**Razão:** Adição já justificada e ratificada no concept §7 D3 + ADR
[`2.2.0002`](../../adr/2_2_0002-reuse-raw-candles-default-vs-live-yfinance.md)
(reuso do raw como origem default vs yfinance live) — sem ela a DoD "reusa raw
existente sem re-baixar por padrão" não teria implementação de produção. Registrado
aqui conforme instrução da §2 Task 06.

### 2026-06-29 — [decision] tests — risco de invariantes OHLC sobre o raw real fechado — code assistant
**Contexto:** Risco concept §10 / Task 08: invariantes OHLC fortes poderiam rejeitar
linhas legítimas do raw por ruído de `float32`.
**Decisão:** Adicionado `tests/integration/.../parquet/test_parquet_raw_candle_fetcher.py`
que lê as **4024 linhas reais** de AAPL via `ParquetRawCandleFetcher`: TODAS produzem
`Candle` válido (zero rejeição), `asset` injetado, tz UTC a 00:00, contagem == 4024.
Nenhuma tolerância arbitrária foi necessária — as invariantes canônicas passam como
estão. Risco fechado; a Task 08 foi confirmação (não exigiu ajuste de invariante).
**Razão:** Concept 2.2 §10 / A6; valida o caminho default real sem rede.

<!-- END: post-execution -->
