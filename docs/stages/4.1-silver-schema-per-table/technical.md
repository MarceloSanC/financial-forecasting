---
title: Technical — Stage 4.1 — Silver schema por tabela (analytics_store)
description: Plano de execução da Stage 4.1 — novo BC analytics_store com VOs de domínio (RunRecord/PredictionRow) e schemas pandera silver POR TABELA (dim_run/fact_config/fact_oos_predictions/fact_split_metrics/fact_failures) + SilverTable + SILVER_REGISTRY, gates import-linter estendidos, sem escrita
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, silver-schema-per-table, analytics-store, pandera, dim_run, fact_oos_predictions, quantile-long, schema-version, import-linter, silver-registry]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 4.1-silver-schema-per-table
stage_title: Silver schema por tabela
step_id: 4
step_title: Analytics store (silver)
depends_on: [1.4-identity-and-fingerprints, 2.1-medallion-storage-contracts]
concept_ref: ./concept.md
issue_id: 34
branch: feat/34-4-1-silver-schema-per-table
tasks_count: 9
---

# Technical — Stage 4.1 — Silver schema por tabela (analytics_store)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [4.1/task-NN]`, body em bullets,
>    rodapé `Refs #34`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar como `[decision]`/`[deviation]`/`[finding]` em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done). Nesta corrida
>    autônoma (ADR `0_0_0050`) **NÃO** pergunte ao humano — decida com base
>    concreta e registre.
> 7. O commit reservado `stage 4.1: complete` e a marcação `done` no
>    `roadmap.md` são do **orquestrador**, NÃO desta sessão.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/34-4-1-silver-schema-per-table`. Sobre o fluxo Git ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

Criar o **novo bounded context `analytics_store`** sob
`features/analytics_store/` com duas entregas: (1) VOs de domínio **frozen,
stdlib-only** — `RunRecord` (metadados de execução, identidade pela PK lógica
de `dim_run`) e `PredictionRow` (uma **linha LONGA** de predição out-of-sample,
H-1: `quantile_level` é um campo, não colunas por quantil); (2) os **contratos
de schema silver POR TABELA** (um módulo `.py` por tabela), validados por
`pandera`, para as **5 tabelas consumidas pelos Steps 1–4** — `dim_run`,
`fact_config`, `fact_oos_predictions`, `fact_split_metrics`, `fact_failures` —
mais a dataclass `SilverTable` (espelha `BronzeTable` da 2.1) e o
`SILVER_REGISTRY[("silver", <table>)]`. Acompanham: extensão do `.importlinter`
(`analytics_store` como container layered; `.domain` em `domain-purity`;
`.{application,domain}` em `store-no-storage-leak`), provada por quebra
intencional revertida; e testes `pandera` de payload **VÁLIDO** e **INVÁLIDO**
para cada tabela. **Nenhuma escrita em disco, nenhum port/repositório** (4.2),
**nenhuma lógica de preenchimento** (4.3) — só o schema como contrato versionado.

### Estratégia

**Schema/data-modeling Stage com BC novo — exceção parcial ao inside-out**
(skill `task-ordering-hex`, linha "Schema / migration": persistência/constraints
primeiro). Esta Stage **não tem port nem use case** (são da 4.2): o "inside" é
o **domínio puro** (VOs) e o "outside" é o **adapter de schema** (`pandera`).
Logo a ordem é:

1. **Task 01 (scaffold):** árvore de pacotes do BC `analytics_store`
   (`domain/value_objects`, `adapters/out/parquet/schemas`) + pacotes de teste.
   Sem código de regra — só `__init__.py` para o BC existir e o `check_layout`
   passar.
2. **Task 02 (gate ANTES do código):** estender o `.importlinter`
   (`hexagonal-layers` + `domain-purity` + `store-no-storage-leak`). Vem **antes**
   das VOs e dos schemas para que o gate prove, por construção, que o domínio
   nasce puro e o `pandera` nasce confinado ao adapter (mesma postura da 2.1
   task-03: gate antes do port). Quebra intencional revertida documenta a prova.
3. **Tasks 03–04 (domain, inside):** os VOs `RunRecord` (03) e `PredictionRow`
   (04) — frozen, stdlib-only, com unit test no mesmo commit (igualdade por
   valor, `FrozenInstanceError`, ausência de grade de quantis em
   `PredictionRow`).
4. **Task 05 (adapter — base):** `silver_table.py` (`SilverTable` frozen) — a
   metadata-shape que cada módulo de tabela instancia. Sem schema concreto ainda.
5. **Tasks 06–07 (adapter — schemas por tabela):** um módulo `.py` por tabela
   (Task 06 = `dim_run` + `fact_config` + `fact_split_metrics` + `fact_failures`;
   Task 07 = `fact_oos_predictions`, isolada por carregar H-1 e os testes de
   ausência de `quantile_p*`), cada um com `pandera` `strict=True` + unit test
   VÁLIDO/INVÁLIDO. **Um módulo por tabela** (DoD — nenhum mega-schema).
6. **Task 08 (adapter — registry):** `silver_registry.py` montando
   `SILVER_REGISTRY[("silver", <table>)]` com as 5 tabelas + unit test (chaves
   exatas, lookup de chave inexistente → `KeyError`).
7. **Task 09 (prova de gate):** teste de arquitetura amarrando os 3 contratos
   estendidos + execução da quebra intencional revertida (registrada como nota).

Regra dura respeitada: **nenhuma Task mistura criar port com criar adapter do
mesmo port** (não há port nesta Stage). VOs (domain) e schemas (adapter) ficam
em commits separados; o gate (Task 02) precede o código que ele protege.
Cada Task ≤ 5 arquivos e deixa o build verde.

### Pré-condições

- Stage `1.4-identity-and-fingerprints` em `done`: `RunId`, `ConfigSignature`,
  `DatasetFingerprint`, `SplitFingerprint` em `shared/domain/value_objects/`
  (consumidos — só como `string` hex nas colunas, nunca recomputados).
- Stage `2.1-medallion-storage-contracts` em `done`: padrão `BronzeTable` +
  `BRONZE_REGISTRY` + contrato `store-no-storage-leak` a espelhar/estender;
  `pandas`/`pyarrow`/`pandera` já em `[project].dependencies` (verificado).
- Branch `feat/34-4-1-silver-schema-per-table` em checkout.
- ADRs `4_1_0001` e `4_1_0002` já escritos (`status: accepted`).

### Premissas técnicas

- Python 3.12, `uv`, `mypy --strict`, `ruff`, `pytest`, cobertura ≥90% (gate).
- `import-linter` rodado por `uv run lint-imports`, plugado em `make check` e CI;
  config em `.importlinter` (root `financial_forecasting`,
  `include_external_packages = True`, `exclude_type_checking_imports = True`).
- `pandera.pandas` (`pa.DataFrameSchema`/`pa.Column`) já usado no
  `bronze_schemas.py` — mesma API para o silver.
- Dtypes do silver = **lógicos do analytics store** (não fidelidade de raw em
  disco como o bronze): identificadores/hashes/timestamps como `string`
  (`run_id`, `config_signature`, `split_fingerprint`, `timestamp_utc`,
  `target_timestamp_utc`, `failed_at_utc`); contagens/horizonte/`schema_version`/
  `decision_idx`/`guardrail_applied` como `int64`; métricas e `value_raw`/
  `value_guardrail`/`quantile_level` como `float64`. Decisão de dtype fixada
  aqui dentro do contrato do concept §13 (`quantile_level` `float64`;
  `guardrail_applied` `int64`). `strict=True`, `coerce=False` (espelha bronze).

### Estrutura de pastas afetada

```
src/financial_forecasting/
└── features/analytics_store/
    ├── __init__.py                                          # NEW (Task 01)
    ├── domain/
    │   ├── __init__.py                                      # NEW (Task 01)
    │   └── value_objects/
    │       ├── __init__.py                                  # NEW (Task 01)
    │       ├── run_record.py                                # NEW (Task 03)
    │       └── prediction_row.py                            # NEW (Task 04)
    └── adapters/out/parquet/schemas/
        ├── __init__.py (+ pacotes intermediários)           # NEW (Task 01)
        ├── silver_table.py                                  # NEW (Task 05)
        ├── dim_run_schema.py                                # NEW (Task 06)
        ├── fact_config_schema.py                            # NEW (Task 06)
        ├── fact_split_metrics_schema.py                     # NEW (Task 06)
        ├── fact_failures_schema.py                          # NEW (Task 06)
        ├── fact_oos_predictions_schema.py                   # NEW (Task 07)
        └── silver_registry.py                               # NEW (Task 08)
tests/
└── unit/features/analytics_store/
    ├── domain/value_objects/
    │   ├── test_run_record.py                               # NEW (Task 03)
    │   └── test_prediction_row.py                           # NEW (Task 04)
    └── adapters/out/parquet/schemas/
        ├── test_silver_table.py                             # NEW (Task 05)
        ├── test_dim_run_schema.py                           # NEW (Task 06)
        ├── test_fact_config_schema.py                       # NEW (Task 06)
        ├── test_fact_split_metrics_schema.py                # NEW (Task 06)
        ├── test_fact_failures_schema.py                     # NEW (Task 06)
        ├── test_fact_oos_predictions_schema.py              # NEW (Task 07)
        └── test_silver_registry.py                          # NEW (Task 08)
tests/architecture/test_import_contracts.py                  # MOD (Task 02/09, se houver assert de lista)
.importlinter                                                # MOD (Task 02)
```

## 2. Tasks

> Faixa saudável: 3–8; aqui **9 Tasks** (concept §11/§12) — recorte fino
> (scaffold + gate + 2 VOs + base + schemas por grupo + registry + prova de
> gate). Decisões já pré-fechadas (H-1, §B 4.1, ADRs 4.1.0001/0002), então cada
> Task é pequena, de baixo risco e build-verde a cada commit.

### Task 01 — Scaffold do BC `analytics_store`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/__init__.py`
  - `src/financial_forecasting/features/analytics_store/domain/__init__.py`
  - `src/financial_forecasting/features/analytics_store/domain/value_objects/__init__.py`
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/__init__.py`
    (+ `adapters/__init__.py`, `adapters/out/__init__.py`,
    `adapters/out/parquet/__init__.py` conforme exigir o pacote)
  - `tests/unit/features/analytics_store/__init__.py` (+ subpacotes
    `domain/value_objects/`, `adapters/out/parquet/schemas/`)
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar a árvore de pacotes do BC vazia (só `__init__.py`),
  espelhando o layout de `market_data`/`feature_engineering` (LAYOUT.md §camadas).
  Sem nenhuma regra/classe ainda.
- **Detalhes técnicos:**
  - `__init__.py` vazios (ou com docstring PT de 1 linha do pacote). Stdlib-only.
  - Não adicionar `analytics_store` ao `.importlinter` aqui — é a Task 02
    (separar o gate do scaffold mantém cada commit atômico).
- **Critério de aceite:**
  - `scripts/check_layout.py` verde com a nova árvore.
  - `make check` segue verde (scaffold inerte, sem imports proibidos).
- **Comando de verificação:**
  ```bash
  uv run python scripts/check_layout.py
  uv run lint-imports
  ```
- **Commit sugerido:** `chore(analytics-store): scaffold do bounded context silver [4.1/task-01]`

---

### Task 02 — Gate `import-linter` para `analytics_store`

- **Arquivos a modificar:**
  - `.importlinter`
  - `tests/architecture/test_import_contracts.py` (só se houver assert sobre a
    lista de contratos/containers esperados; senão, nenhum)
- **Arquivos a criar:** nenhum.
- **O que fazer:** estender três contratos existentes (mesma postura aplicada a
  `market_data`/`feature_engineering`):
  - `hexagonal-layers`: adicionar
    `financial_forecasting.features.analytics_store` aos `containers`.
  - `domain-purity`: adicionar
    `financial_forecasting.features.analytics_store.domain` a `source_modules`.
  - `store-no-storage-leak`: adicionar
    `financial_forecasting.features.analytics_store.application` **e**
    `...analytics_store.domain` a `source_modules` (`application` entra por
    defesa em profundidade — ainda não existe nesta Stage, mas `exhaustive=False`
    / `(adapters)` opcional toleram a ausência, como em feature_engineering).
- **Detalhes técnicos:**
  - Comentário no `.importlinter` citando concept I1/I2/I8/D4 + os ADRs vigentes
    `1_3_0001` (fitness function) e `2_1_0002` (store-no-storage-leak). É
    aplicação direta — **sem ADR próprio** (registrar `[decision]` em §7).
  - Manter `allow_indirect_imports = False` nos contratos forbidden.
  - Vem **antes** das VOs/schemas: o gate fica verde com o código ainda
    inexistente e passa a proteger por construção.
- **Critério de aceite:**
  - `uv run lint-imports` verde (todos os contratos `kept`, nenhum `broken`).
  - Quebra intencional revertida: `import pandas` em
    `analytics_store/domain/...` deixa `domain-purity` (e
    `store-no-storage-leak`) **vermelho** (prova manual; revertida, não
    commitada).
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/ -v
  ```
- **Commit sugerido:** `chore(import-linter): registrar analytics_store nos contratos de camada/pureza [4.1/task-02]`

---

### Task 03 — VO `RunRecord` (domínio, frozen, stdlib-only)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/domain/value_objects/run_record.py`
  - `tests/unit/features/analytics_store/domain/value_objects/test_run_record.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** definir `@dataclass(frozen=True) class RunRecord` (concept §4)
  com os metadados de execução. Identidade pela PK lógica de `dim_run`
  (`run_id`). Stdlib-only; nenhum mapeamento para `DataFrame` (isso é do adapter).
- **Detalhes técnicos:**
  - Campos (tipos stdlib): `run_id: str`, `asset: str`,
    `parent_sweep_id: str | None`, `feature_set_name: str`,
    `config_signature: str`, `split_fingerprint: str`, `fold: str | None`,
    `seed: int | None`, `model_version: str`, `schema_version: int`.
  - `config_signature`/`split_fingerprint` guardam o **hash hex (`str`)** vindo
    da 1.4 — **não** reimplementar/recomputar (I10).
  - `frozen=True` (igualdade por valor + imutabilidade). Imports SÓ de stdlib
    (`dataclasses`, `typing`/`__future__`) — sem pandas/pandera/pydantic.
- **Critério de aceite:**
  - Teste prova: igualdade por valor (dois `RunRecord` iguais ⇒ `==` e mesmo
    `hash`); `FrozenInstanceError` ao tentar reatribuir campo; campos opcionais
    aceitam `None`.
  - `lint-imports` verde (gate da Task 02 confirma pureza).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/analytics_store/domain/value_objects/test_run_record.py -v
  uv run mypy --strict src/financial_forecasting/features/analytics_store/domain/value_objects/run_record.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store/domain): adicionar VO RunRecord [4.1/task-03]`

---

### Task 04 — VO `PredictionRow` (linha LONGA, H-1)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/domain/value_objects/prediction_row.py`
  - `tests/unit/features/analytics_store/domain/value_objects/test_prediction_row.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** definir `@dataclass(frozen=True) class PredictionRow` (concept
  §4 / H-1) representando **uma linha LONGA** de predição out-of-sample —
  `quantile_level` é um **campo**, **não** colunas `p10/p50/p90`.
- **Detalhes técnicos:**
  - Campos: `run_id: str`, `split: str`, `horizon: int`,
    `decision_idx: int`, `timestamp_utc: str`, `target_timestamp_utc: str`,
    `quantile_level: float`, `value_raw: float`, `value_guardrail: float`,
    `guardrail_applied: int`.
  - `decision_idx`/`target_timestamp_utc` são **contrato de schema** (âncora
    ADR-0003 do old, *mechanical > procedural*); a lógica de off-by-one é da 4.3
    (concept I11/D5) — aqui só o campo existe.
  - `frozen=True`, stdlib-only. **PROIBIDO** qualquer campo `quantile_p*` (I5).
- **Critério de aceite:**
  - Teste prova: igualdade por valor + `FrozenInstanceError`; **`quantile_level`
    é um campo** e os campos `quantile_p10`/`quantile_p50`/`quantile_p90`
    (e `_post_guardrail`) **não existem** (ex.: assert sobre
    `{f.name for f in fields(PredictionRow)}` — grade NÃO fixada, A3).
  - `lint-imports` verde.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/analytics_store/domain/value_objects/test_prediction_row.py -v
  uv run mypy --strict src/financial_forecasting/features/analytics_store/domain/value_objects/prediction_row.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store/domain): adicionar VO PredictionRow longo (H-1) [4.1/task-04]`

---

### Task 05 — `SilverTable` (dataclass de metadata, adapter)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/silver_table.py`
  - `tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_silver_table.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** definir `@dataclass(frozen=True) class SilverTable` (concept §4)
  espelhando `BronzeTable` da 2.1: `name: str`, `schema_version: int`,
  `logical_pk: tuple[str, ...]`, `partition_by: tuple[str, ...]`,
  `update_policy: str` (`"upsert" | "append-only"`),
  `schema: pa.DataFrameSchema`.
- **Detalhes técnicos:**
  - Vive **no adapter** (`adapters/out/parquet/schemas/`) — importa
    `pandera.pandas as pa` (permitido só aqui; gate `store-no-storage-leak`
    reprova se vazar para domain/application).
  - `update_policy` é `str` (não enum) — espelha o `BronzeTable` (consistência
    entre BCs); validação do conjunto fica nos schemas/registry.
  - Não declarar `asset_col`/`year_anchor` do bronze: o silver particiona por
    colunas já presentes (`asset`, `parent_sweep_id`, `feature_set_name`,
    `year`) sem derivação de âncora — registrar `[decision]` se a 4.2 precisar
    de uma âncora de `year` (deferível).
- **Critério de aceite:**
  - Teste constrói um `SilverTable` mínimo e prova: `frozen` (`FrozenInstanceError`)
    e que carrega os 6 campos com os tipos esperados.
  - `mypy --strict` verde; `lint-imports` verde (pandera só no adapter).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_silver_table.py -v
  uv run mypy --strict src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/silver_table.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store/adapters-out): dataclass SilverTable (metadata+schema) [4.1/task-05]`

---

### Task 06 — Schemas das 4 tabelas `upsert`/fact (dim_run, fact_config, fact_split_metrics, fact_failures)

- **Arquivos a criar:**
  - `src/.../adapters/out/parquet/schemas/dim_run_schema.py`
  - `src/.../adapters/out/parquet/schemas/fact_config_schema.py`
  - `src/.../adapters/out/parquet/schemas/fact_split_metrics_schema.py`
  - `src/.../adapters/out/parquet/schemas/fact_failures_schema.py`
  - `tests/.../schemas/test_dim_run_schema.py`,
    `test_fact_config_schema.py`, `test_fact_split_metrics_schema.py`,
    `test_fact_failures_schema.py` (4 arquivos de teste)
- **Arquivos a modificar:** nenhum.
- **O que fazer:** **um módulo `.py` por tabela** (DoD — nenhum mega-schema),
  cada um expondo uma constante `SilverTable` (`DIM_RUN`, `FACT_CONFIG`,
  `FACT_SPLIT_METRICS`, `FACT_FAILURES`) com `pa.DataFrameSchema`
  (`strict=True`, `coerce=False`) + `schema_version` + `logical_pk` +
  `partition_by` + `update_policy` conforme a tabela do concept §4. Colunas
  derivadas do old `analytics_store_schema.py` (validar, não copiar cego),
  com fingerprints como `string` (I10).
- **Detalhes técnicos (concept §4):**
  - `dim_run`: `logical_pk=("run_id",)`, `partition_by=("asset","parent_sweep_id")`,
    `update_policy="upsert"` (**única** upsert, I6). Colunas mínimas: `run_id`,
    `asset`, `parent_sweep_id`, `feature_set_name`, `config_signature`,
    `split_fingerprint`, `fold`, `seed`, `model_version`, `schema_version`
    (alinhar com os campos de `RunRecord`).
  - `fact_config`: `logical_pk=("run_id",)`,
    `partition_by=("asset","parent_sweep_id")`, `update_policy="append-only"`.
  - `fact_split_metrics`: `logical_pk=("run_id","split")`,
    `partition_by=("asset","parent_sweep_id")`, `update_policy="append-only"`.
  - `fact_failures`: `logical_pk=("run_id","failed_at_utc","stage")`,
    `partition_by=("asset",)`, `update_policy="append-only"`.
  - Dtypes: identificadores/hashes/timestamps `string`; contagens/`schema_version`
    `int64`; métricas `float64` (ver §1 Premissas). Colunas opcionais →
    `nullable=True` onde o old não as exigia.
  - Cada módulo importa `SilverTable` (Task 05) e `pandera.pandas as pa`.
- **Critério de aceite:**
  - Para cada uma das 4 tabelas, o teste prova: payload **VÁLIDO** passa; e os
    payloads **INVÁLIDOS** levantam erro `pandera`/`SchemaError` — coluna
    obrigatória ausente (C1), dtype divergente (C3), coluna extra com
    `strict=True` (C4), PK duplicada/nula (C5). `schema_version` mismatch (C2)
    coberto comparando o valor do payload com `table.schema_version`.
  - Metadata correta: `logical_pk`/`partition_by`/`update_policy`/`schema_version`
    batem com o concept §4 (assert direto na constante).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_dim_run_schema.py tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_fact_config_schema.py tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_fact_split_metrics_schema.py tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_fact_failures_schema.py -v
  uv run mypy --strict src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store/adapters-out): schemas silver dim_run/fact_config/fact_split_metrics/fact_failures [4.1/task-06]`

---

### Task 07 — Schema `fact_oos_predictions` (formato LONGO/agnóstico, H-1)

- **Arquivos a criar:**
  - `src/.../adapters/out/parquet/schemas/fact_oos_predictions_schema.py`
  - `tests/.../schemas/test_fact_oos_predictions_schema.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** módulo separado expondo `FACT_OOS_PREDICTIONS: SilverTable`
  com `pa.DataFrameSchema` em **formato LONGO** (H-1 / D2 / ADR 4.1.0002):
  `quantile_level` é coluna **na PK**, com `value_raw`, `value_guardrail`,
  `guardrail_applied`. **PROIBIDO** colunas `quantile_p10/p50/p90 (+_post_guardrail)`.
- **Detalhes técnicos (concept §4/§9):**
  - `logical_pk=("run_id","split","horizon","timestamp_utc","target_timestamp_utc","quantile_level")`.
  - `partition_by=("asset","feature_set_name","year")`,
    `update_policy="append-only"`.
  - Colunas (dtype): `run_id`/`split`/`timestamp_utc`/`target_timestamp_utc`
    `string`; `horizon`/`decision_idx`/`guardrail_applied`/`year`/`schema_version`
    `int64`; `quantile_level`/`value_raw`/`value_guardrail` `float64`;
    `asset`/`feature_set_name` `string`. `quantile_level` `float64` (concept §13
    / §10 risco de dtype: níveis numéricos, `coerce=False`).
  - Isolada em Task própria por carregar a invariante H-1 e o teste de **ausência
    de `quantile_p*`** — separar reduz risco de port-por-inércia (concept §10).
- **Critério de aceite:**
  - Payload **VÁLIDO** (≥2 linhas com `quantile_level` distintos para o mesmo
    `(run_id, split, horizon, timestamp_utc, target_timestamp_utc)`) passa;
    payloads **INVÁLIDOS** (C1/C3/C4/C5) levantam erro `pandera`.
  - Teste **prova H-1**: nenhuma coluna `quantile_p10`/`quantile_p50`/
    `quantile_p90` (nem `_post_guardrail`) no schema; `quantile_level` **está**
    em `FACT_OOS_PREDICTIONS.logical_pk`; partição
    `("asset","feature_set_name","year")`; `update_policy == "append-only"`
    (A5).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_fact_oos_predictions_schema.py -v
  uv run mypy --strict src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/fact_oos_predictions_schema.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store/adapters-out): schema silver fact_oos_predictions longo (H-1) [4.1/task-07]`

---

### Task 08 — `SILVER_REGISTRY` `(layer, table)`

- **Arquivos a criar:**
  - `src/.../adapters/out/parquet/schemas/silver_registry.py`
  - `tests/.../schemas/test_silver_registry.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** montar `SILVER_LAYER = "silver"` e
  `SILVER_REGISTRY: Mapping[tuple[str, str], SilverTable]` chaveado por
  `("silver", <table>)` com as **5** `SilverTable` (importadas dos 5 módulos),
  espelhando `BRONZE_REGISTRY` da 2.1.
- **Detalhes técnicos:**
  - Importa as 5 constantes (`DIM_RUN`, `FACT_CONFIG`, `FACT_OOS_PREDICTIONS`,
    `FACT_SPLIT_METRICS`, `FACT_FAILURES`) e `SilverTable`. Vive no adapter.
  - Lookup com par inexistente é `KeyError` (C6) — o registry não engole;
    quem despacha (4.2) trata. Não criar wrapper de erro nesta Stage.
- **Critério de aceite:**
  - Teste prova: `set(SILVER_REGISTRY) == {("silver", t) for t in {dim_run,
    fact_config, fact_oos_predictions, fact_split_metrics, fact_failures}}`
    (exatamente 5 chaves, A7); cada valor é o `SilverTable` correto
    (`.name` bate); `SILVER_REGISTRY[("silver","inexistente")]` levanta
    `KeyError` (C6).
  - `dim_run` é `upsert` e as 4 facts são `append-only` (A6) — assert via
    registry.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_silver_registry.py -v
  uv run mypy --strict src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/silver_registry.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store/adapters-out): SILVER_REGISTRY (layer,table) com as 5 tabelas [4.1/task-08]`

---

### Task 09 — Prova dos gates de arquitetura (quebra intencional revertida)

- **Arquivos a modificar:**
  - `tests/architecture/test_import_contracts.py` (se houver assert sobre
    containers/contratos esperados — incluir `analytics_store`)
- **Arquivos a criar:** nenhum (o gate em si já está no `.importlinter` da
  Task 02; aqui é a prova final + amarração).
- **O que fazer:** rodar a quebra intencional revertida que prova os contratos
  estendidos: (1) `import pandas` em
  `analytics_store/domain/value_objects/run_record.py` → `lint-imports`
  **vermelho** (`domain-purity` + `store-no-storage-leak`); reverter. (2) um
  import `application → adapters` (ou `domain → adapters`) → `inward-only`/
  `hexagonal-layers` **vermelho**; reverter. Registrar o resultado como nota em
  §7 (A9). Se `test_import_contracts.py` mantém a lista de containers esperados,
  adicionar `analytics_store` à expectativa.
- **Detalhes técnicos:**
  - As quebras são **manuais e não commitadas** (prova viva, não regressão
    automatizada — espelha a postura das Stages 2.1/3.1/3.2).
  - O commit desta Task carrega só o ajuste de `test_import_contracts.py`
    (se necessário) e fecha a Stage com `make check` verde.
- **Critério de aceite:**
  - `import pandas` no domínio do BC deixa `lint-imports` vermelho; revertido,
    fica verde (prova de `domain-purity`/`store-no-storage-leak` para
    `analytics_store`, A9).
  - `make check` verde no branch (ruff + mypy --strict + lint-imports +
    check_layout + testes); cobertura do BC `analytics_store` ≥ 90% (A10).
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/ -v
  make check
  ```
- **Commit sugerido:** `test(analytics-store): provar gates de camada/pureza do BC silver [4.1/task-09]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 4.1: complete` (feito pelo **orquestrador**, não por esta sessão).

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
uv run pytest tests/      # todos os testes (unit + architecture)
uv run lint-imports       # hexagonal-layers + domain-purity + store-no-storage-leak verdes
```

### Verificações funcionais
- [ ] `RunRecord` e `PredictionRow` instanciáveis, frozen (reatribuição levanta
      `FrozenInstanceError`), iguais por valor; `PredictionRow` **sem** campos
      `quantile_p*` e **com** `quantile_level`.
- [ ] Para cada uma das 5 tabelas: um payload válido passa o `pandera`; payloads
      inválidos (missing required, dtype errado, coluna extra, PK
      duplicada/nula, `schema_version` mismatch) levantam erro.
- [ ] `fact_oos_predictions` em formato longo: `quantile_level` na PK, partição
      `(asset, feature_set_name, year)`, `append-only`, **sem** `quantile_p*`.
- [ ] `SILVER_REGISTRY[("silver", <table>)]` contém exatamente as 5 tabelas;
      `dim_run` é `upsert`, demais `append-only`.
- [ ] Quebra intencional (`import pandas` no domínio do BC) reprova
      `lint-imports` e é revertida.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — Domínio puro (stdlib-only, frozen) | Task 03/04 unit (`FrozenInstanceError`, igualdade); Task 09 (quebra `import pandas` reprova `domain-purity`) |
| I2 — `pandera`/`pandas` confinados ao adapter | Task 02 gate `store-no-storage-leak` estendido; Task 09 quebra revertida |
| I3 — Um módulo por tabela (nenhum mega-schema) | Task 06 (4 módulos) + Task 07 (1 módulo) = 5 arquivos `.py` separados |
| I4 — Metadados completos por tabela | Task 06/07 (cada `SilverTable` com `schema_version`+`logical_pk`+`partition_by`+`update_policy`); Task 08 assert via registry |
| I5 — H-1: `fact_oos_predictions` longo, sem `quantile_p*` | Task 04 (`PredictionRow` sem `quantile_p*`); Task 07 (schema sem `quantile_p*`, `quantile_level` na PK) |
| I6 — `dim_run` única `upsert`; facts `append-only` | Task 06/07 (`update_policy` por tabela); Task 08 assert via registry (A6) |
| I7 — `pandera` estrito (`strict=True`) | Task 06/07 unit VÁLIDO/INVÁLIDO (C1/C3/C4/C5) |
| I8 — Inward-only / container layered | Task 02 `hexagonal-layers` + `inward-only`; Task 09 quebra revertida |
| I9 — Identidade via PK lógica (igualdade por valor) | Task 03/04 (igualdade `==`/`hash` do dataclass frozen) |
| I10 — Fingerprints não reimplementados (string) | Task 03 (`config_signature`/`split_fingerprint` `str`); Task 06 (colunas `string`) |
| I11 — `decision_idx`/`target_timestamp_utc` = contrato, não lógica | Task 04 (`PredictionRow` tem o campo); Task 07 (coluna no schema) — sem lógica de off-by-one |
| C2 — `(layer, table)` fora do registry → `KeyError` | Task 08 (`SILVER_REGISTRY[("silver","x")]` levanta `KeyError`) |

### Checklist de fechamento da Stage
- [ ] Todas as 9 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura ≥90% no BC `analytics_store` (VOs + schemas + registry contam)
- [ ] ADRs `4_1_0001` e `4_1_0002` em `status: accepted`
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
- [ ] **NÃO** marcar `roadmap.md` como `done` nem fazer o commit
      `stage 4.1: complete` — isso é do orquestrador, após auditoria

## 4. Ordem de dependência entre Tasks

```
Task 01 (scaffold) ─► Task 02 (gate) ─► Task 03 (RunRecord) ─► Task 04 (PredictionRow)
                                     └► Task 05 (SilverTable) ─► Task 06 (4 schemas) ─┐
                                                              └► Task 07 (fact_oos) ──┤
                                                                                      ├► Task 08 (registry) ─► Task 09 (prova gates)
```

- 01 antes de tudo (BC precisa existir); 02 (gate) antes do código que ele
  protege (VOs/schemas) — gate verde com código inexistente, depois protege por
  construção (igual 2.1 task-03). 05 (`SilverTable`) antes de 06/07 (os módulos
  de tabela instanciam `SilverTable`). 06 e 07 são independentes entre si (podem
  trocar de ordem), ambos antes de 08 (registry importa as 5 constantes). 09
  (prova final + `make check`) por último. VOs (03/04) são independentes dos
  schemas (05–08) — listados primeiro por serem o "inside" (domínio), mas sem
  acoplamento de import.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `pandera` rejeita coluna `string` vs `object`/`str` (atrito de dtype literal) | Espelhar o `bronze_schemas.py` (`pa.Column(str, ...)` para strings); se houver atrito, usar o literal `"string"` (pandas StringDtype) e fixar no teste; registrar `[deviation]` |
| `quantile_level` `float64` vs `string` ambíguo (concept §10) | Decidido `float64` (níveis numéricos, query-áveis); `coerce=False` + teste de dtype. Se o Step 5 exigir string-key, é mudança de schema versionada (não nesta Stage) |
| Teste de PK duplicada exige checagem de unicidade que `pandera` não faz por default | Declarar `unique=` na(s) coluna(s) de PK **ou** `pa.DataFrameSchema(..., unique=[<pk cols>])`; se a versão da lib não suportar `unique` composto, validar PK no teste com `df.duplicated(subset=pk)` e registrar `[finding]` para a checagem-no-write da 4.2 |
| `import-linter` `exhaustive`/container reclama de `application` ausente no BC | `exhaustive=False` + `(adapters)` opcional já toleram (igual feature_engineering); `application` em `store-no-storage-leak` é source vazio — sem erro. Se reclamar, registrar `[decision]` e ajustar o container |
| Cobertura <90% no BC (VOs/schemas têm pouca lógica executável) | Os testes VÁLIDO/INVÁLIDO por tabela + igualdade/`FrozenInstanceError` dos VOs exercitam o código; se faltar, cobrir o branch de `KeyError` do registry e os campos opcionais dos VOs |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (invariantes I1–I11,
  casos C1–C6, decisões D1–D5, contratos §4)
- [`../../overview.md`](../../overview.md) — §3 escopo, §7 abordagem, §11 ADRs
- [`../../roadmap.md`](../../roadmap.md) — Stage `4.1` e consumidoras (4.2/4.3)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — H-1 (quantis long) e §B 4.1 (5 tabelas, 8 deferidas)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches/commits/status
- ADRs desta Stage:
  [`4.1.0001`](../../adr/4_1_0001-analytics-store-silver-schema-per-table.md),
  [`4.1.0002`](../../adr/4_1_0002-fact-oos-predictions-long-quantile-format.md)
- Skills aplicáveis: `task-ordering-hex`, `ddd-tactical-patterns`,
  `hex-arch-python`, `import-linter-rules`, `pytest-with-fakes`
- Padrões espelhados no repo: `bronze_schemas.py` (forma do `BronzeTable` +
  `BRONZE_REGISTRY` + schemas `pandera`); `.importlinter` (containers
  `market_data`/`feature_engineering`, contratos `domain-purity`/
  `store-no-storage-leak`)
- Repo antigo de referência:
  `financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`
  (colunas/`logical_pk`/`partition_by`/`update_policy` das 5 tabelas — validar,
  não copiar; `quantile_p*` é o anti-padrão substituído por H-1)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`.** Nesta corrida autônoma (ADR `0_0_0050`) NÃO se pergunta ao
> humano: decisões não-triviais viram `[decision]` aqui (com opções + escolha +
> razão), gaps para próxima Stage viram `[finding]`, ajustes pequenos viram
> `[deviation]`.

### Execução — 2026-06-29 (todas as 9 Tasks, build verde)

**[decision] Task 01 — `application/` criado no scaffold.** O `scripts/check_layout.py`
(`REQUIRED_FEATURE_DIRS`, linhas 84/155-169) exige que **toda** feature tenha
`domain/`, `application/` **e** `adapters/`. O concept/technical previam só
`domain/` + `adapters/`. Criei `features/analytics_store/application/__init__.py`
vazio (placeholder das Stages 4.2/4.3). É reversível e alinha com a Task 02, que já
adiciona `analytics_store.application` ao `store-no-storage-leak` (defesa em
profundidade — source sem imports não reprova). Sem isto, o `layout-check` do
`make check` reprovaria.

**[decision] Task 02 — extensão do `.importlinter` sem ADR próprio (concept D4).**
Adicionei `analytics_store` ao `hexagonal-layers` (container layered), `.domain` ao
`domain-purity` e `.{application,domain}` ao `store-no-storage-leak`. É aplicação
direta dos ADRs vigentes `1.3.0001` (import-linter como fitness function) e
`2.1.0002` (`store-no-storage-leak`) — mesma postura já aplicada a `market_data`/
`feature_engineering`. Provado verde com código inexistente e por quebra intencional
revertida (ver A9 abaixo).

**[deviation] Escopo e tamanho do subject de commit vs sugestões do technical.**
O hook `check_commit_msg.py` aceita escopo só em `[a-z0-9._-]+` (sem `/`) e subject
≤ 100 chars. Os "Commit sugerido" deste technical usavam `/` no escopo
(`analytics-store/domain`) e um subject longo na Task 06. Usei o separador `.`
(`analytics-store.domain`, `analytics-store.adapters-out` — consistente com o
exemplo `payment.retry` do CONVENTIONS §4) e encurtei o subject da Task 06 para
"schemas silver das 4 tabelas upsert/fact". Conteúdo idêntico ao planejado.

**[decision] Tasks 06/07 — recorte de colunas do old com julgamento (não cópia cega).**
O old (`analytics_store_schema.py`) carregava colunas operacionais e especulativas.
Reduzi cada tabela ao contrato confirmatório dos Steps 1-4:
- `dim_run`: campos alinhados ao VO `RunRecord` + `created_at_utc` (descartados
  `execution_id`, `git_commit`, `library_versions_json`, `hardware_info_json`,
  `checkpoint_path_*`, `duration_*`, `eta_*`, `retries`, `feature_set_hash`,
  `feature_list_ordered_json`, `pipeline_version`, `trial_number`, `status` — ou são
  da 4.2/5.x, ou são as 8 tabelas deferidas; `status` derivava de lógica que não é
  schema). Mantida a PK/partição/`upsert` do old.
- `fact_config`: núcleo de modo/loss/horizontes + os 3 JSONs canônicos
  (`quantile_levels_json`/`evaluation_horizons_json`/`training_config_json`); os
  hiperparâmetros individuais do TFT (hidden_size, dropout, …) ficam dentro do
  `training_config_json` (coerente com H-1: grade/hparams = dado, não coluna).
- `fact_split_metrics`: só as métricas pontuais descritivas do old (rmse/mae/mape/
  smape/directional_accuracy/n_samples); as métricas probabilísticas confirmatórias
  (pinball/CRPS/calibração) são gold (Step 6), fora do escopo.
- `fact_failures`: núcleo auditável (error_type/message/trace_hash/excerpt);
  descartadas colunas de captura de processo (`cmdline`/`stdout_truncated`/
  `stderr_truncated`/`execution_id`/`entrypoint`).
- `fact_oos_predictions`: **formato LONGO** (H-1) — `quantile_level` na PK +
  `value_raw`/`value_guardrail`/`guardrail_applied`; **removidas** as 7 colunas
  `quantile_p*`/`_post_guardrail`/`quantile_guardrail_applied` do old. Removidas
  também `y_true`/`y_pred`/`error`/`abs_error`/`sq_error` (são erro/alvo derivados
  no domínio de avaliação do Step 6, não predição bruta); `seed`/`fold` ficam em
  `dim_run` (PK lógica `run_id` resolve). Mantidos `decision_idx`/`timestamp_utc`/
  `target_timestamp_utc` como contrato (I11), `year` para partição.
Decisão reversível: adicionar coluna a uma tabela é mudança local + `schema_version`
bump — exatamente o que a decomposição por módulo habilita.

**[finding] PK lógica validada por `pandera unique=[...]` no schema (C5), mas a
dedup-no-write é da 4.2.** `pandera` 0.32 suporta `unique` composto no
`DataFrameSchema` e reprova PK duplicada; `nullable=False` nas colunas de PK reprova
PK nula. Isso valida um payload já montado, mas **não** substitui a política
`append-only`/`upsert` no momento da escrita — a Stage 4.2 (`AnalyticsRepository`)
deve aplicar a dedup operationally-latest/upsert ao gravar. Registro para a 4.2 não
assumir que o schema sozinho garante unicidade entre escritas.

**[decision] Task 09 — prova automatizada além do manual.** Além da quebra
intencional revertida manual (pandas no domínio → `domain-purity` e
`store-no-storage-leak` vermelhos, exit=1; domínio→adapters → `hexagonal-layers`
vermelho; todos revertidos com `lint-imports` exit=0), adicionei 2 casos
parametrizados a `_REAL_VIOLATION_CASES` em
`tests/architecture/test_import_contracts.py`
(`domain-purity:analytics-store-domain-imports-pandas` e
`store-no-storage-leak:analytics-store-domain-imports-pandera`). Eles injetam o
import proibido na árvore real e exigem o contrato `broken`, travando o "contrato
míope" (drift de `source_modules`) para o BC novo. Custo baixo, proteção de
regressão alta — coerente com a postura do próprio teste (modo de falha 3).

**[finding] dtype `string` literal (`pa.Column(str, ...)`) aceita `pandas` StringDtype
e `object`-string sem atrito.** Espelhei o `bronze_schemas.py` usando `pa.Column(str)`
para colunas string; os testes usam `pd.array(..., dtype="string")`/`"Int64"` e
validam sem coerção. Sem o atrito previsto no risco §5 (não foi preciso o literal
`"string"`). `seed` opcional usa `Int64` nullable no payload de teste; a coluna no
schema é `int64` com `nullable=True` — `pandera` aceita o `Int64` nullable do pandas.

**Gates de saída (verdes):** `make check` (ruff + mypy --strict + layout-check +
lint-imports + docs-check + test) verde — 907 passed, 7 skipped, cobertura total
98.33%. Cobertura do BC `analytics_store` isolado = **100%** (77 statements, 0
missed). `lint-imports`: 8 contratos kept, 0 broken.

<!-- END: post-execution -->
