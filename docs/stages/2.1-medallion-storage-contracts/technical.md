---
title: Technical — Stage 2.1 — Contratos de storage medalhão (MedallionStore + bronze)
description: Plano de execução da Stage 2.1 — port-out MedallionStore (Protocol), adapter ParquetMedallionStore (pyarrow/duckdb), schemas pandera bronze, DuplicateKeyError, gate import-linter de não-vazamento, fake↔real contract test e wiring no composition_root
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, medallion-storage-contracts, medallion-store, parquet, pyarrow, duckdb, pandera, bronze, hive-partition, append-only, duplicate-key, import-linter, settings, composition-root]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 2.1-medallion-storage-contracts
stage_title: Contratos de storage medalhão
step_id: 2
step_title: Camada bronze + calendário
depends_on: [1.5-config-and-tracking]
concept_ref: ./concept.md
issue_id: 15
branch: feat/15-2-1-medallion-storage-contracts
tasks_count: 10
---

# Technical — Stage 2.1 — Contratos de storage medalhão (MedallionStore + bronze)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.1/task-NN]`, body em bullets,
>    rodapé `Refs #15`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar como `[decision]`/`[deviation]`/`[finding]` em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done). Nesta corrida
>    autônoma (ADR `0_0_0050`) NÃO pergunte ao humano — decida com base
>    concreta e registre.
> 7. O commit reservado `stage 2.1: complete` e a marcação `done` no
>    `roadmap.md` são do **orquestrador**, NÃO desta sessão.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/15-2-1-medallion-storage-contracts`. Sobre o fluxo Git ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

Introduzir o primeiro **adapter-out real** da pipeline medalhão: o port-out
`MedallionStore` (`Protocol` stdlib-only em `shared/application/ports/out/`)
para gravar/ler datasets `(layer, table)` particionados em Parquet, e o adapter
`ParquetMedallionStore` (`shared/adapters/out/parquet/`) que o implementa sobre
`pyarrow` (escrita Hive batch-por-partição), `duckdb` (leitura com *partition
pruning*) e `pandera` (validação de schema no write). Acompanham: schemas
`pandera` bronze (candle/news/fundamental) espelhando os dtypes reais em disco,
`DuplicateKeyError(ApplicationError)`, um `FakeMedallionStore` in-memory que
passa o **mesmo** contract test parametrizado que o adapter real, integration
test gravando/lendo particionado de verdade, um novo contrato `import-linter`
(`store-no-storage-leak`) barrando libs de storage fora de adapters, o campo
`data_root` em `Settings`/`.env.example` e o wiring de `ParquetMedallionStore`
no `composition_root`.

### Estratégia

**Inside-out (TDD), com desvio justificado de início** (skill `task-ordering-hex`).
Esta Stage **não é vertical-slice** com `domain` novo: é majoritariamente
adapter-out sobre infra de fundação. Por isso a ordem começa por
**precondições de infra** (deps externas, gate de pureza) ANTES do port, e só
depois sobe domain→application→adapter→wiring:

1. **Task 01 (deps):** adicionar `pandas`/`pyarrow`/`duckdb`/`pandera` ao
   `pyproject.toml` + `uv.lock`. Sem as libs, nada importa.
2. **Task 02 (domain):** `DuplicateKeyError(ApplicationError)` — tipo
   observável estável que o contract test exige em ambas as impls.
3. **Task 03 (gate):** contrato `import-linter` `store-no-storage-leak`
   barrando `pandas/pyarrow/duckdb/pandera` em `application`+`domain`. Vem
   ANTES do port para provar, por construção, que o port é stdlib-only (o gate
   já estaria verde com o port escrito puro).
4. **Task 04 (application):** o port `MedallionStore` (`Protocol`).
5. **Task 05 (fake + contract):** `FakeMedallionStore` in-memory + o contract
   test parametrizado (a princípio só sobre o fake) — a `application`/contrato
   fica testável **sem** infra externa (regra `pytest-with-fakes`: fake antes
   do real).
6. **Task 06 (schemas):** schemas `pandera` bronze + registry `(layer, table)`
   (no adapter), com unit test por tabela — fundação de dtype que o adapter usa.
7. **Task 07 (adapter):** `ParquetMedallionStore`, parametrizando o **mesmo**
   contract test da Task 05 sobre `[fake, real]` (paridade fake↔real).
8. **Task 08 (integration):** integration test em `tmp_path` gravando/lendo
   particionado real (layout Hive, round-trip de dtype, pruning).
9. **Task 09 (config):** `data_root` em `Settings` + `.env.example`.
10. **Task 10 (wiring):** `ParquetMedallionStore` no `composition_root`,
    `ApplicationDependencies.store: MedallionStore`.

Regra dura respeitada: **port (Task 04) e adapter (Task 07) em commits
separados**; fake (05) antes do real (07). Tasks 01–03 são habilitadoras e não
dependem do contrato semântico.

### Pré-condições

- Stage `1.5-config-and-tracking` em `done`: `Settings`/`get_settings`/
  `wire_dependencies`/`ApplicationDependencies` disponíveis; padrão de wiring
  estabelecido.
- `DomainError`/`ApplicationError` já em `shared/domain/exceptions/base.py`.
- Branch `feat/15-2-1-medallion-storage-contracts` em checkout.
- ADRs `2_1_0001` e `2_1_0002` já escritos (`status: accepted`).

### Premissas técnicas

- Python 3.12, `uv`, `mypy --strict`, `ruff`, `pytest`, cobertura ≥90% (gate).
- `import-linter` rodado por `uv run lint-imports`, plugado em `make check`;
  config em `.importlinter` (root_package `financial_forecasting`,
  `include_external_packages = True`).
- `pyarrow` escreve Parquet por partição preservando `datetime64[ns, UTC]` e
  `float32`; `duckdb` lê Parquet via glob Hive com *partition pruning* por
  coluna de partição. Validar no integration test (Task 08), não assumir.
- Dtypes reais do raw já **verificados** (concept §9): candle OHLC `float32` /
  `volume` `int64` / `timestamp` UTC; news 8 strings + `published_at` UTC;
  fundamental 5 `float64` / `fiscal_date_end` UTC / `reported_date` UTC
  **nullable (NaT)** / `report_type`/`source` strings.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── composition_root.py                                   # MOD (Task 10)
└── shared/
    ├── application/ports/out/
    │   └── medallion_store.py                             # NEW (Task 04)
    ├── adapters/out/parquet/
    │   ├── __init__.py                                    # NEW (Task 06/07)
    │   ├── schemas/
    │   │   ├── __init__.py                                # NEW (Task 06)
    │   │   └── bronze_schemas.py                          # NEW (Task 06)
    │   └── parquet_medallion_store.py                     # NEW (Task 07)
    ├── domain/exceptions/base.py                          # MOD (Task 02)
    └── infrastructure/config/settings.py                  # MOD (Task 09)
tests/
├── fakes/shared/in_memory_medallion_store.py             # NEW (Task 05)
├── contract/shared/test_medallion_store_contract.py      # NEW (Task 05/07)
├── integration/shared/test_parquet_medallion_store.py    # NEW (Task 08)
└── unit/shared/
    ├── adapters/out/parquet/test_bronze_schemas.py        # NEW (Task 06)
    ├── domain/exceptions/test_base.py                      # NEW (Task 02)
    ├── infrastructure/config/test_settings.py              # MOD (Task 09)
    └── test_composition_root.py                            # MOD (Task 10)
pyproject.toml / uv.lock                                   # MOD (Task 01)
.importlinter                                              # MOD (Task 03)
.env.example                                               # MOD (Task 09)
```

## 2. Tasks

> Faixa saudável: 3–8; aqui **10 Tasks** (concept §12) — decisões já
> pré-fechadas no ledger §B, então cada Task é pequena e de baixo risco.

### Task 01 — Adicionar deps de storage (pandas/pyarrow/duckdb/pandera)

- **Arquivos a modificar:**
  - `pyproject.toml` (bloco `[project].dependencies`)
  - `uv.lock`
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar `pandas`, `pyarrow`, `duckdb`, `pandera` a
  `[project].dependencies` com *lower bounds* compatíveis com Python 3.12;
  sincronizar o lock com `uv lock`.
- **Detalhes técnicos:**
  - Manter o estilo dos pins existentes (ex.: `mlflow>=2.14`).
  - NÃO criar grupo separado: são deps de runtime (o adapter é runtime).
  - Não tocar `omit` de cobertura aqui — `adapters/*` NUNCA entra em `omit`
    (ver pyproject, política herdada da 1.2).
- **Critério de aceite:**
  - `python -c "import pandas, pyarrow, duckdb, pandera"` ok no ambiente uv.
  - `uv.lock` sincronizado (sem diff pendente após `uv lock --check`).
- **Comando de verificação:**
  ```bash
  uv sync && uv run python -c "import pandas, pyarrow, duckdb, pandera; print('ok')"
  uv lock --check
  ```
- **Commit sugerido:** `build(deps): adicionar pandas/pyarrow/duckdb/pandera para storage medalhão [2.1/task-01]`

---

### Task 02 — `DuplicateKeyError(ApplicationError)` no domínio

- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/domain/exceptions/base.py`
- **Arquivos a criar:**
  - `tests/unit/shared/domain/exceptions/__init__.py`
  - `tests/unit/shared/domain/exceptions/test_base.py`
- **O que fazer:** adicionar `class DuplicateKeyError(ApplicationError)` com
  docstring PT explicando que representa colisão de PK lógica em `write`
  append-only sem `overwrite` (concept C1/D5). Unit test cobrindo a herança.
- **Detalhes técnicos:**
  - É `ApplicationError` (erro de orquestração/estado), **não** `DomainError`
    nem `ValueError` (concept D5).
  - Não precisa de campos estruturados obrigatórios; a mensagem (citando
    `(layer, table)`, colunas de PK e amostra de colisões) é montada por quem
    levanta (o adapter/fake). Stdlib-only.
- **Critério de aceite:**
  - `test_base.py` prova `issubclass(DuplicateKeyError, ApplicationError)` e
    `not issubclass(DuplicateKeyError, DomainError)`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/domain/exceptions/test_base.py -v
  uv run mypy --strict src/financial_forecasting/shared/domain/exceptions/base.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(domain): adicionar DuplicateKeyError de aplicação para colisão de PK [2.1/task-02]`

---

### Task 03 — Gate `import-linter` `store-no-storage-leak`

- **Arquivos a modificar:**
  - `.importlinter`
- **Arquivos a modificar (teste):**
  - `tests/architecture/test_import_contracts.py` (se houver assert sobre a
    lista de contratos esperados; senão, nenhum)
- **O que fazer:** adicionar um contrato `forbidden` (espelhando
  `tracker-no-mlflow-leak`) barrando `pandas`/`pyarrow`/`duckdb`/`pandera` em
  `financial_forecasting.shared.application` e `...shared.domain`.
- **Detalhes técnicos:**
  - `domain-purity` já barra `pandas`/`pyarrow`/`numpy` no `domain`; o NOVO
    cobre **`application`** (não coberto hoje) e adiciona **`duckdb`**/
    **`pandera`** (não listados em `domain-purity`). `domain` entra por defesa
    em profundidade.
  - `allow_indirect_imports = False`, como os outros contratos forbidden.
  - Comentário no `.importlinter` citando concept I4 + ADR `2_1_0002` e a
    razão (`domain-purity`/`tracker-no-mlflow-leak` como precedentes).
- **Critério de aceite:**
  - `uv run lint-imports` verde com o port ainda inexistente (o contrato não
    quebra nada hoje).
  - Quebra intencional revertida: um `import pandas` em
    `shared/application/...` deixa `lint-imports` vermelho (prova manual,
    não commitada).
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/ -v
  ```
- **Commit sugerido:** `chore(import-linter): barrar libs de storage em application/domain [2.1/task-03]`

---

### Task 04 — Port-out `MedallionStore` (Protocol)

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/application/ports/out/medallion_store.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** definir o `Protocol` `MedallionStore` (concept §4) com
  `write(*, layer, table, rows, overwrite=False) -> None` e
  `read(*, layer, table, filters=None) -> Sequence[Row]`, onde
  `Row = Mapping[str, object]`. Docstring PT declarando a semântica garantida
  (append-only; recolisão de PK lógica sem `overwrite` → `DuplicateKeyError`;
  PK e partição vêm do registry por `(layer, table)`, não do chamador; `read`
  filtra por partição com pruning e nunca carrega o dataset inteiro; `read` de
  dataset/asset inexistente → sequência vazia, C4). Citar ADR `2_1_0002`.
- **Detalhes técnicos:**
  - Imports SÓ de `collections.abc` (`Mapping`, `Sequence`) e `typing`
    (`Protocol`). **Nenhum** `import pandas/pyarrow/duckdb/pandera` — o gate da
    Task 03 reprova se vazar (I3/I4).
  - Sem corpo nos métodos (`...`); type hints completos para `mypy --strict`.
- **Critério de aceite:**
  - `lint-imports` verde (port stdlib-only confirmado pelo gate da Task 03).
  - `mypy --strict` verde no arquivo.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/shared/application/ports/out/medallion_store.py
  uv run lint-imports
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(application): definir port MedallionStore (Protocol) [2.1/task-04]`

---

### Task 05 — `FakeMedallionStore` + contract test (só fake)

- **Arquivos a criar:**
  - `tests/fakes/shared/in_memory_medallion_store.py`
  - `tests/contract/shared/test_medallion_store_contract.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar o `FakeMedallionStore` in-memory que satisfaz o
  `Protocol` (dict por `(layer, table)` → lista de rows; PK/partição lidas de
  um registry-leve interno espelhando o do adapter — mesmas PKs lógicas da
  concept §9) e o contract test parametrizado (a princípio com `params=[fake]`,
  estrutura pronta para ganhar `real` na Task 07). Cobre: round-trip de write/
  read; append-only; **colisão de PK → `DuplicateKeyError`** (C1);
  `overwrite=True` substitui colididas (I2); filtro por `asset` retorna só o
  asset pedido (I7); `read` de dataset/asset inexistente → vazio (C4);
  `(layer, table)` fora do registry → erro de aplicação (C2).
- **Detalhes técnicos:**
  - O fake é stdlib-only (vive em `tests/`, fora do gate, mas mantém o contrato
    agnóstico — não usa pandas). Levanta o MESMO `DuplicateKeyError` do real.
  - PK lógica: candle `(asset, timestamp)`, news `(asset_id, article_id)`,
    fundamental `(asset_id, report_type, fiscal_date_end)`. A coluna `asset`
    de partição vem de `asset`/`asset_id` conforme a tabela.
  - Marcar os testes `@pytest.mark.contract`. Fixture `store` parametrizada via
    factories `_build_fake` (e `_build_real` adicionado na Task 07), espelhando
    `test_experiment_tracker_contract.py`.
- **Critério de aceite:**
  - Contract test verde sobre o fake; cobre C1/C2/C4/I2/I7 e round-trip.
  - `mypy --strict` verde no fake.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/shared/test_medallion_store_contract.py -v
  uv run mypy --strict tests/fakes/shared/in_memory_medallion_store.py
  ```
- **Commit sugerido:** `test(application): FakeMedallionStore + contract test do port [2.1/task-05]`

---

### Task 06 — Schemas `pandera` bronze + registry `(layer, table)`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/adapters/out/parquet/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/parquet/schemas/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/parquet/schemas/bronze_schemas.py`
  - `tests/unit/shared/adapters/__init__.py` (+ subpacotes `out/parquet/`)
  - `tests/unit/shared/adapters/out/parquet/test_bronze_schemas.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** definir `DataFrameSchema` `pandera` para candle/news/
  fundamental espelhando os dtypes reais (concept §9 / ADR `2_1_0001`) e uma
  dataclass **frozen** de metadata por tabela (`logical_pk: tuple[str, ...]`,
  `partition_by: tuple[str, ...]` = `(asset_col, "year")`, `year_anchor: str`,
  `schema: DataFrameSchema`), agregadas num registry `BRONZE_REGISTRY:
  Mapping[tuple[str, str], BronzeTable]` chaveado por `("bronze", table)`.
- **Detalhes técnicos:**
  - Dtypes: candle `open/high/low/close` `float32`, `volume` `int64`,
    `timestamp` `datetime64[ns, UTC]`, `asset` string; news 8 strings +
    `published_at` UTC; fundamental `revenue/net_income/operating_cash_flow/
    total_shareholder_equity/total_liabilities` `float64`, `fiscal_date_end`
    UTC, `reported_date` UTC **`nullable=True`**, `asset_id/report_type/source`
    string.
  - `year_anchor`: candle→`timestamp`, news→`published_at`,
    fundamental→`fiscal_date_end`. `asset_col`: candle→`asset`,
    news/fundamental→`asset_id`.
  - Schemas/registry vivem SÓ no adapter (gate Task 03 garante que
    `application`/`domain` não os importam).
  - Recursos embarcados (se algum schema externo): `importlib.resources.files()`,
    NUNCA `Path(__file__)` (I8). Nesta Stage os schemas são código Python, então
    provavelmente não há recurso externo — registrar `[deviation]` se introduzir.
- **Critério de aceite:**
  - Unit test por tabela: um DataFrame de exemplo com os dtypes corretos
    **valida**; `reported_date` com `NaT` é **aceito** (nullable, C3/I5); um
    DataFrame com dtype errado (ex.: `volume` `float64`, `timestamp` tz-naive)
    **falha** a validação.
  - `BRONZE_REGISTRY` tem exatamente as 3 chaves esperadas com PK/partição
    corretas.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/adapters/out/parquet/test_bronze_schemas.py -v
  uv run mypy --strict src/financial_forecasting/shared/adapters/out/parquet/schemas/bronze_schemas.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(adapters-out): schemas pandera bronze + registry (layer,table) [2.1/task-06]`

---

### Task 07 — `ParquetMedallionStore` + paridade no contract test

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/adapters/out/parquet/parquet_medallion_store.py`
- **Arquivos a modificar:**
  - `tests/contract/shared/test_medallion_store_contract.py` (parametrizar `real`)
- **O que fazer:** implementar `ParquetMedallionStore(data_root: Path | str)`
  satisfazendo o `Protocol`. `write`: valida `rows`→DataFrame contra o schema
  `pandera` do registry; deriva `year` da `year_anchor`; agrupa em batch por
  partição (`asset=<asset>/year=<year>`); para cada partição alvo, lê as PKs
  lógicas já gravadas, detecta colisão (sem `overwrite` → `DuplicateKeyError`
  com `(layer, table)`+PKs+amostra; com `overwrite` substitui), grava o
  Parquet da partição via `pyarrow`. `read`: monta `SELECT` DuckDB sobre o glob
  Hive com `WHERE` na(s) coluna(s) de partição vindas de `filters` (pruning);
  dataset/asset inexistente → vazio. Depois, adicionar `_build_real` à fixture
  do contract test para rodar o MESMO contrato sobre `[fake, real]` (I6).
- **Detalhes técnicos:**
  - Layout: `<data_root>/bronze/<table>/asset=<asset>/year=<year>/<table>.parquet`.
  - `_safe_partition`: valor `None`/vazio → sentinela estável (espelha o old);
    `year` derivado da âncora.
  - Colisão checada **por partição** (não dataset inteiro) — barato no piloto
    single-asset; otimizável depois sem mudar contrato.
  - `(layer, table)` fora do `BRONZE_REGISTRY` → erro de aplicação (C2).
  - `data_root` é **injetado** (não hardcoded, I8/I9). Adapter NÃO entra em
    `omit` (conta cobertura).
  - O contract test passa `_build_real(tmp_path)` =
    `ParquetMedallionStore(tmp_path)` — isolamento por `tmp_path`.
- **Critério de aceite:**
  - O contract test inteiro verde sobre `[fake, real]` (mesmos casos C1/C2/C4/
    I2/I7 + round-trip) — paridade fake↔real provada.
  - `mypy --strict` verde no adapter.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/shared/test_medallion_store_contract.py -v
  uv run mypy --strict src/financial_forecasting/shared/adapters/out/parquet/parquet_medallion_store.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(adapters-out): ParquetMedallionStore (pyarrow+duckdb+pandera) [2.1/task-07]`

---

### Task 08 — Integration test particionado real em `tmp_path`

- **Arquivos a criar:**
  - `tests/integration/shared/__init__.py`
  - `tests/integration/shared/test_parquet_medallion_store.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** integration test (`@pytest.mark.integration`) gravando/lendo
  um dataset bronze particionado de verdade em `tmp_path` para as 3 tabelas
  (ao menos candle + fundamental por causa do `NaT`). Asserta: layout Hive em
  disco (`asset=<asset>/year=<year>/<table>.parquet` existe); **round-trip de
  dtype exato** (UTC preservado, `float32` não vira `float64`, `volume`
  `int64`, fundamentals `float64`, `reported_date` `NaT` preservado);
  append-only entre dois `write`; e que `read({"asset": A})` num dataset com
  dois assets retorna SÓ as linhas de `A` (pruning, I7/A6).
- **Detalhes técnicos:**
  - Usar dados sintéticos pequenos com os dtypes exatos da concept §9.
  - Verificar pruning observacionalmente: gravar A e B, `read(asset=A)` não traz
    linhas de B (e idealmente o predicado não lê o arquivo de B — basta o
    resultado correto para o gate).
  - Conferir o `NaT` ida-e-volta (linha de fundamental com `reported_date` NaT).
- **Critério de aceite:**
  - Test verde; dtype round-trip e filtro por asset assertados (A6).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/shared/test_parquet_medallion_store.py -v
  ```
- **Commit sugerido:** `test(adapters-out): integration de ParquetMedallionStore particionado [2.1/task-08]`

---

### Task 09 — `data_root` em `Settings` + `.env.example`

- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/infrastructure/config/settings.py`
  - `.env.example`
  - `tests/unit/shared/infrastructure/config/test_settings.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar `data_root: Path = Path("data")` a `Settings`
  (concept D4), com docstring PT (raiz dos dados medalhão; override por
  `DATA_ROOT`; default relativo ao repo/worktree). Espelhar `DATA_ROOT=data`
  em `.env.example`. Estender `test_settings.py` cobrindo default + override
  por env.
- **Detalhes técnicos:**
  - Nome do campo: **`data_root`** (decidido — concept §13: `data_root` vs
    `medallion_root`; escolhido `data_root` por ser a raiz de TODAS as camadas
    medalhão, com o sufixo `bronze/` aplicado pelo adapter). Registrar
    `[decision]` em §7.
  - `Path` é suportado por pydantic-settings; manter `extra="ignore"`.
- **Critério de aceite:**
  - `Settings(_env_file=None).data_root == Path("data")`; override via
    `DATA_ROOT=/x` (monkeypatch env) reflete em `data_root`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/infrastructure/config/test_settings.py -v
  uv run mypy --strict src/financial_forecasting/shared/infrastructure/config/settings.py
  ```
- **Commit sugerido:** `feat(config): adicionar data_root em Settings e .env.example [2.1/task-09]`

---

### Task 10 — Wiring de `ParquetMedallionStore` no composition root

- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `tests/unit/shared/test_composition_root.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar `store: MedallionStore` a `ApplicationDependencies`
  (tipado pelo **port**) e, em `wire_dependencies`, instanciar
  `ParquetMedallionStore(cfg.data_root)` (único lugar, I9). Estender o teste de
  wiring exercitando `store` com um `Settings` fake cujo `data_root` aponta para
  `tmp_path`.
- **Detalhes técnicos:**
  - `ApplicationDependencies.store: MedallionStore` — NÃO o concreto.
  - Teste: `Settings(_env_file=None, data_root=tmp_path)` →
    `isinstance(deps.store, ParquetMedallionStore)` e que a raiz injetada é a do
    `Settings` (sem depender do `lru_cache` global, I6).
- **Critério de aceite:**
  - Teste de wiring verde; `composition_root` segue fora do `omit` (cobre
    ≥90%).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/test_composition_root.py -v
  make check
  ```
- **Commit sugerido:** `feat(bootstrap): wirar ParquetMedallionStore no composition root [2.1/task-10]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 2.1: complete` (feito pelo **orquestrador**, não por esta sessão).

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
uv run pytest tests/      # todos os testes (unit + contract + integration + architecture)
uv run lint-imports       # store-no-storage-leak verde
uv lock --check           # lock sincronizado
uv run python -c "import pandas, pyarrow, duckdb, pandera; print('ok')"
```

### Verificações funcionais
- [ ] Gravar um lote bronze `(bronze, candle)` particiona em
      `asset=<asset>/year=<year>/candle.parquet` e a releitura por `asset`
      devolve as mesmas linhas com dtypes preservados (UTC + `float32` + `int64`).
- [ ] Recolisão de PK lógica sem `overwrite` levanta `DuplicateKeyError`; com
      `overwrite=True` substitui as linhas colididas.
- [ ] `read({"asset": A})` num dataset com dois assets devolve só `A`.
- [ ] `FakeMedallionStore` e `ParquetMedallionStore` passam o MESMO contract
      test parametrizado.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — Partição Hive `asset`/`<tabela>`/`year` | Task 08 integration (layout em disco `asset=…/year=…`) |
| I2 — Append-only + colisão de PK lógica | Task 05/07 contract (C1 + `overwrite`); Task 08 (2º write) |
| I3 — Port stdlib-only | Task 04 + gate Task 03 (`lint-imports` verde com port escrito) |
| I4 — `application` não importa libs de storage (gate) | Task 03 `store-no-storage-leak`; `tests/architecture/` |
| I5 — Fidelidade de dtype/nulabilidade bronze | Task 06 unit (schema valida/rejeita); Task 08 round-trip + `NaT` |
| I6 — Paridade fake↔real | Task 07 contract parametrizado `[fake, real]` |
| I7 — Leitura por partição com pruning | Task 05/07 contract (filtro por `asset`); Task 08 (dois assets) |
| I8 — `importlib.resources` / raiz injetada | Task 07 (`data_root` injetado); Task 10 (vindo de `Settings`) |
| I9 — Wiring centralizado, sem singleton | Task 10 (`composition_root` único criador, `store: MedallionStore`) |
| I10 — Gates verdes | §3 automatizadas (`make check`, `lint-imports`, cobertura ≥90%) |

### Checklist de fechamento da Stage
- [ ] Todas as 10 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥90% no diff (adapter + composition_root contam)
- [ ] ADRs `2_1_0001` e `2_1_0002` em `status: accepted`
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
- [ ] **NÃO** marcar `roadmap.md` como `done` nem fazer o commit
      `stage 2.1: complete` — isso é do orquestrador, após auditoria

## 4. Ordem de dependência entre Tasks

```
Task 01 (deps) ─► Task 06 (schemas) ─► Task 07 (adapter) ─► Task 08 (integration)
Task 02 (DuplicateKeyError) ─► Task 05 (fake+contract) ─► Task 07
Task 03 (gate) ─► Task 04 (port) ─► Task 05
                                  └► Task 07
Task 09 (Settings.data_root) ─► Task 10 (wiring)
Task 07 ─► Task 10
```

- 01 antes de 06/07/08 (precisa das libs); 02 antes de 05 (fake levanta
  `DuplicateKeyError`); 03 antes de 04 (gate prova port puro); 04 antes de
  05/07; 05 (fake) antes de 07 (real) — fake antes do real (regra dura);
  06 antes de 07 (adapter usa o registry); 09 antes de 10 (`data_root`).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `pyarrow` rebaixa `float32`→`float64` ou perde tz no round-trip | Forçar dtype no DataFrame antes de escrever; assertar no integration (Task 08); se irreconciliável, fixar schema Arrow explícito e registrar `[decision]` |
| DuckDB não faz pruning como esperado (lê tudo) | O gate exige só **resultado correto** do filtro (Task 08); pruning é otimização — se a engine não podar, o contrato ainda passa; registrar `[finding]` para otimização futura |
| `pandera` rejeita `datetime64[ns, UTC]` ou exige engine específico | Usar `pandera.pandas` API e `Column(dtype, nullable=...)`; se houver atrito de versão, pinar versão compatível em Task 01 e registrar `[deviation]` |
| `reported_date` `NaT` quebra escrita Parquet | Schema marca nullable (Task 06); integration cobre `NaT` (Task 08); se pyarrow exigir tipo explícito, declarar coluna `timestamp[us, tz=UTC]` nullable |
| Cobertura <90% no adapter | Contract (fake+real) + integration cobrem write/read/colisão/filtro; adicionar casos de borda (registry desconhecido, partição vazia) se faltar |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (invariantes I1–I10,
  casos C1–C4, decisões D1–D5)
- [`../../overview.md`](../../overview.md) — §11 ADR `0.0.0022` (engine
  pandas+duckdb), `0.0.0021` (contract tests)
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.1` e consumidoras (2.2/2.3)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md) — §B linha 2.1
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches/commits/status
- ADRs desta Stage:
  [`2.1.0001`](../../adr/2_1_0001-medallion-partition-and-bronze-schemas.md),
  [`2.1.0002`](../../adr/2_1_0002-medallion-store-port-shape.md)
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`,
  `pytest-with-fakes`, `repository-pattern`, `composition-root`,
  `import-linter-rules`
- Padrões espelhados no repo: `experiment_tracker.py` (forma do port),
  `test_experiment_tracker_contract.py` (contract parametrizado),
  `test_composition_root.py` (wiring com `Settings` fake), `.importlinter`
  (`tracker-no-mlflow-leak`)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`.** Nesta corrida autônoma (ADR `0_0_0050`) NÃO se pergunta ao
> humano: decisões não-triviais viram `[decision]` aqui (com opções + escolha +
> razão), gaps para próxima Stage viram `[finding]`, ajustes pequenos viram
> `[deviation]`.

### Execução — Stage 2.1 (10 Tasks, todas commitadas, gates verdes)

Resultado: `make check` verde (195 testes, cobertura total 99.67%); contract
test parametrizado `[fake, real]` (22 casos) verde — paridade fake↔real provada;
integration test (5 casos) verde; `lint-imports` 6 contratos `kept`/0 `broken`
(novo `store-no-storage-leak`); `uv lock --check` sincronizado. Cobertura no
código novo do adapter `parquet_medallion_store.py` = 99% (1 linha defensiva
`_safe_partition(None)` não exercitada; > 90%); `bronze_schemas.py` 100%; port
`medallion_store.py` 100%; `composition_root.py` 100%; `settings.py` 100%.

#### [decision] Nome do campo de raiz de dados = `data_root` (Task 09 / concept D4)

- **Opções:** (a) `data_root`; (b) `medallion_root`.
- **Escolha:** `data_root` (`Path`, default `Path("data")`).
- **Razão:** é a raiz de TODAS as camadas medalhão; o sufixo `bronze/<table>/…`
  é aplicado pelo `ParquetMedallionStore` por dentro (não pelo `Settings`), então
  o campo descreve a raiz de dados genérica e não amarra a config à camada
  bronze. Pré-declarado no concept §13; segue a fundação 1.5 (override por
  `DATA_ROOT`, 12-factor) — sem ADR próprio.

#### [decision] Detecção de colisão de PK lê a partição com `pandas`, não DuckDB (Task 07)

- **Opções:** (a) ler o Parquet da partição alvo com `pd.read_parquet` e comparar
  tuplas de PK (como o old `_write_with_overwrite_policy`); (b) consultar as PKs
  existentes via DuckDB no caminho de escrita.
- **Escolha:** (a) — `pandas` no write; DuckDB fica só no `read` (pruning).
- **Razão:** o caminho de colisão precisa carregar o conteúdo da partição alvo de
  qualquer forma para fazer o merge/substituição; `pd.read_parquet(path)` é
  direto, espelha a semântica validada do old e mantém o write sem montar SQL. O
  custo é a leitura da partição (não do dataset todo) — barato no piloto
  single-asset, otimizável depois sem mudar o contrato (risco já mapeado em §5).

#### [deviation] pre-commit mypy ganhou `pandas/pyarrow/duckdb/pandera` em `additional_dependencies` (Task 07)

- **O quê:** o hook `mypy` do `.pre-commit-config.yaml` roda num venv isolado com
  `additional_dependencies` próprias. Sem as libs de storage lá, `pq.write_table`
  vira `Any` e o hook acusava o `# type: ignore[no-untyped-call]` (NECESSÁRIO no
  venv do projeto, onde `make check`/`uv run mypy` veem o pyarrow tipado) como
  `unused-ignore` — divergência entre os dois mypy.
- **Ajuste:** adicionadas `pandas>=2.2`/`pyarrow>=16.0`/`duckdb>=1.0`/`pandera>=0.20`
  ao `additional_dependencies` do hook, alinhando-o ao `make check` (o hook é um
  espelho do gate, não um gate distinto). Reversível e de baixo risco.

#### [finding] Fidelidade `float32` vive no Parquet em disco, não no `Row` escalar (Tasks 07/08)

- `read` devolve `Sequence[Mapping[str, object]]`; `DataFrame.to_dict(orient=
  "records")` converte escalares numpy para tipos Python nativos, então um
  `float32` lido vira `float` (float64) NO ESCALAR do `Row`. A fidelidade de
  dtype que 2.2/2.3 precisam está PRESERVADA no arquivo Parquet (relido como
  `DataFrame` mantém `float32`/`int64`/UTC) — o integration test asserta o dtype
  no Parquet em disco, não no escalar. **Para 2.2/2.3:** consumir o store por
  leitura de DataFrame quando o dtype exato importar; o `Row` é uma view
  dict-like agnóstica de dtype (esperado pelo contrato do port).

#### [finding] DuckDB devolve `datetime64[us, UTC]` (resolução `us`, não `ns`) (Task 07)

- Com `SET TimeZone='UTC'`, o `read` via DuckDB devolve timestamps tz-aware em
  UTC mas com resolução `us` (microssegundo) em vez de `ns`. O INSTANTE é
  idêntico (UTC preservado); só a resolução do dtype difere do `datetime64[ns,
  UTC]` gravado. Aceitável — o integration test asserta tz-aware-UTC e o mesmo
  instante, não a resolução literal. Se uma Stage futura exigir `ns` no read,
  basta um `CAST`/conversão no adapter (sem mudar o contrato do port).

#### [deviation] Local do integration test = `tests/integration/shared/test_parquet_medallion_store.py`

- O bloco §1 (estrutura) e o roadmap (`arquivos_a_criar`) divergiam levemente do
  caminho (`.../shared/adapters/out/parquet/...` vs `.../shared/...`). Seguido o
  caminho da **Task 08** (plano executável): `tests/integration/shared/
  test_parquet_medallion_store.py`. Sem impacto funcional.

#### [deviation] Auditoria de testes — cobertura de C3 no ADAPTER (não só no schema isolado)

- **Gap fechado (HIGH value):** C3/I5 ("write com dado fora do schema bronze →
  rejeitado pelo `pandera` no ADAPTER; não grava Parquet inválido") não tinha
  teste no nível do adapter. O contract test roda sobre `[fake, real]`, mas o fake
  não tem `pandera` (não pode enforçar dtype), então C3 ficava fora do contrato
  compartilhado; e `test_bronze_schemas.py` validava o `DataFrameSchema` em
  ISOLAMENTO, nunca pelo caminho `ParquetMedallionStore.write()`. **Mutação
  provada:** comentar `meta.schema.validate(incoming)` (linha 131) NÃO quebrava
  nenhum teste antes — a linha tinha cobertura de execução (99%) mas zero
  cobertura comportamental.
- **Adicionado** em `tests/integration/shared/test_parquet_medallion_store.py`:
  - `test_write_rejects_row_outside_schema_and_writes_no_parquet` — linha com
    coluna extra (`strict=True`) é rejeitada por `pandera` no adapter E nenhum
    Parquet é gravado (atomicidade de C3). Confirmado que mata a mutação acima.
  - `test_write_rejects_missing_required_column` — linha sem coluna obrigatória
    (`close`) é rejeitada (caminho de coluna FALTANTE, distinto do extra).
- **Por que integration (não unit/contract):** C3 é comportamento do adapter
  concreto (pandera + não-escrita-em-disco); não cabe no contract test
  compartilhado (fake é stdlib-only por design) nem no unit do schema (que testa
  o schema, não o adapter). A asserção `not list((tmp_path/"bronze").rglob(...))`
  prova a invariante "não grava Parquet inválido".

#### [finding] (blocker F1) `read` devolvia coluna de partição fantasma `asset` para news/fundamental — corrigido

- **Blocker (auditoria independente, severidade `blocker`, dentro da Stage).** O
  `read` montava `SELECT * EXCLUDE (year)`. Com `hive_partitioning=true`, o DuckDB
  materializa AMBAS as colunas de partição (`asset` **e** `year`). O `EXCLUDE`
  removia só `year`. Para `candle` não havia problema (a coluna de partição
  `asset` é literalmente a coluna do schema). Mas `news`/`fundamental` têm coluna
  lógica `asset_id` — o `asset` da partição NÃO pertence ao schema bronze. O
  `read` real devolvia 9 chaves (`asset` fantasma duplicando `asset_id`), o fake
  devolvia 8. **Viola I6** (paridade fake↔real — "mesmo contract test em [fake,
  real]") e a **fidelidade de schema do read** (A5/A6) que 2.2/2.3 consomem.
- **Causa do falso-verde.** O contract test que existia para PROVAR I6 era míope:
  só checava `len(rows)` e uma chave (`rows[0]["article_id"]`), nunca o conjunto
  de chaves. O `test_news_round_trip_with_string_columns` passava verde em
  `[fake, real]` apesar de key-sets divergentes (verificação assimétrica;
  estrutural ≠ semântico).
- **Correção (Opção A da recomendação).** No `read`, projetar SÓ as colunas
  declaradas no schema bronze do registry (`SELECT "<col>", ... FROM
  read_parquet(..., hive_partitioning=true) WHERE ...`) em vez de `SELECT *
  EXCLUDE (year)`. Isso dropa QUALQUER coluna de partição que não esteja no
  schema (o `asset` fantasma) e mantém `WHERE asset = ?` válido (a partição segue
  disponível para pruning, só não é selecionada). Identificadores citados (helper
  `_quote_ident`, escape de `"`) para tolerar nomes que colidem com keywords (ex.:
  `open`). Para `candle` o resultado é idêntico (o DuckDB funde a coluna de dado
  `asset` com a de partição de mesmo nome; verificado).
- **Buraco de I6 fechado (escopo da Stage).** Adicionado ao contract test
  (rodando em `[fake, real]`) o assert de conjunto EXATO de chaves
  `set(rows[0]) == set(written)`: reforçado em `test_write_then_read_round_trip`
  (candle) e `test_news_round_trip_with_string_columns` (news), e criado
  `test_fundamental_round_trip_no_phantom_partition` (fundamental, que antes só
  tinha cobertura integration real, sem paridade). **Mutação provada:** com o
  `SELECT * EXCLUDE (year)` antigo restaurado, os dois asserts de news/fundamental
  falham (`Extra items in the left set: 'asset'`); com a projeção por schema,
  todos passam.

<!-- END: post-execution -->
