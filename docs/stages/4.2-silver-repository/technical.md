---
title: Technical — Stage 4.2 — Repositório silver (analytics_store)
description: Plano de execução do port-out AnalyticsRepository + adapter Parquet dedicado (append-only/upsert, partição Hive literal, pandera no write, read com pruning, round-trip do sentinel), em Tasks atômicas inside-out
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, silver-repository, analytics-store, append-only, upsert, parquet, partition-pruning, parent-sweep-id, clock, created-at-utc, contract-test]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 4.2-silver-repository
stage_title: Repositório silver
step_id: 4
step_title: Analytics store (silver)
depends_on: [4.1-silver-schema-per-table]
concept_ref: ./concept.md
issue_id: 36
branch: feat/36-4-2-silver-repository
tasks_count: 9
---

# Technical — Stage 4.2 — Repositório silver

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [4.2/task-NN]`, body em bullets,
>    rodapé `Refs #36`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar `[decision]`/`[deviation]`/`[finding]` em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done). Decisões fora de
>    questão já fechada: decidir sozinho (modo autônomo overnight,
>    ADR 0.0.0050) — sem perguntas.
> 7. **NÃO** fazer o commit `stage 4.2: complete` nem marcar a Stage `done`
>    no `roadmap.md` — isso é do ORQUESTRADOR após auditoria independente.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/36-4-2-silver-repository`. Push/PR/merge são do orquestrador.

## 1. Contexto e estratégia de execução

### Resumo

Entregar o **músculo de escrita/leitura** do BC `analytics_store` sobre os
contratos de schema da 4.1. Cria-se um **port-out `AnalyticsRepository`**
(`Protocol` estrutural, stdlib-only, `write/read` genéricos por `(layer, table)`)
e um **adapter Parquet dedicado `ParquetAnalyticsRepository`** que despacha por
`SILVER_REGISTRY`, valida `pandera` no write antes de tocar o disco, particiona
Hive pelas **colunas literais** de `SilverTable.partition_by` (1..3 níveis),
aplica **append-only** nos 4 fatos (upsert só em `dim_run` por política ou via
`allow_upsert=True`), preenche `created_at_utc` de `dim_run` no write-time via
**`Clock` injetado** (OBS-1), e lê de volta com **partition pruning** (DuckDB)
preservando `parent_sweep_id` no **round-trip `__none__` → `None`**. Tudo provado
por **um contract test único parametrizado `[fake, real]`** + **um integration
test particionado real**, mais o **wiring no `composition_root`**.

### Estratégia

**Adapter-only sobre BC consolidado, com introdução de um novo port** — a 4.1 já
entregou `domain` (VO `RunRecord`), os 5 schemas `pandera`, `SilverTable` e o
`SILVER_REGISTRY`. Portanto **não há nova entidade/VO a modelar**; a ordem é
**inside-out a partir da application** (skill `task-ordering-hex`, exceção
"adapter-only on a consolidated BC", mas aqui o port é novo, então começamos pelo
port + fake + contract antes do adapter real):

1. **Port** (`application/ports/out`) — stdlib-only, `Protocol` (task-01).
2. **Fake + contract test scaffold parametrizado só `[fake]`** — o fake é a
   especificação executável da semântica observável (task-02, task-03).
3. **Adapter real, em duas Tasks** (não bundlar port+adapter, §4.3): primeiro o
   **write** (despacho, pandera, partição, dedup/append/upsert, mapper
   `RunRecord`→row com `Clock`) (task-04), depois o **read** (pruning, projeção,
   round-trip `__none__`) (task-05).
4. **Ligar o adapter real ao contract test** (parametrizar `[fake, real]`) —
   prova paridade fake↔real (task-06).
5. **Integration test particionado real** — confere layout Hive em disco,
   append-only/upsert reais, round-trip do sentinel (task-07).
6. **Wiring** no `composition_root` (task-08).
7. **Fechar os 2 ADRs** desta Stage (`accepted`) (task-09).

Cada Task deixa o build verde: depois do task-03 o contract já roda sobre o fake
(use case testável sem infra); reverter o integration test (task-07) não quebra a
application.

### Pré-condições

- Stage `4.1-silver-schema-per-table` em `done`: `SILVER_REGISTRY`,
  `SilverTable`, os 5 schemas `pandera`, VO `RunRecord` presentes
  (verificado: `features/analytics_store/adapters/out/parquet/schemas/*`,
  `domain/value_objects/run_record.py`).
- Stage `2.1` em `done`: `MedallionStore`/`ParquetMedallionStore` +
  `DuplicateKeyError`/`ApplicationError` (`shared/domain/exceptions/base.py`) —
  referência de forma e exceções reusadas.
- Stage `1.5` em `done`: `Clock` (`shared/application/ports/out/clock.py`) +
  `SystemClock` (`shared/infrastructure/clock/system_clock.py`);
  `Settings.data_root` para o wiring.
- ADRs `4_2_0001` e `4_2_0002` já existem em `docs/adr/` (escritos na Fase
  conceitual) — task-09 só confirma `status: accepted` e fecha referências.

### Premissas técnicas

- Python 3.12, `uv`, `pandas`/`pyarrow`/`duckdb`/`pandera` disponíveis no extra de
  dev (confinados ao adapter; `import-linter` reprova vazamento).
- `year` em `fact_oos_predictions` chega como coluna `int64` literal do payload
  (o persister 4.3 a preencherá); a 4.2 só a usa como nível de partição.
- O contract test usa um `FakeClock` determinístico (timestamp fixo) para o
  `created_at_utc` de `dim_run`.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── features/analytics_store/
│   ├── application/ports/out/
│   │   └── analytics_repository.py            # task-01 (port + Row)
│   └── adapters/out/parquet/
│       ├── parquet_analytics_repository.py    # task-04 (write) + task-05 (read)
│       └── mappers/
│           └── run_record_mapper.py           # task-04 (RunRecord→row dim_run)
├── composition_root.py                        # task-08 (wiring)
tests/
├── fakes/features/analytics_store/
│   └── in_memory_analytics_repository.py      # task-02 (fake)
├── contract/features/analytics_store/
│   └── test_analytics_repository_contract.py  # task-03 (scaffold [fake]) + task-06 ([fake,real])
└── integration/features/analytics_store/
    └── test_parquet_analytics_repository.py   # task-07 (layout Hive real)
docs/adr/
├── 4_2_0001-analytics-repository-port-shape-and-dedicated-parquet.md  # task-09
└── 4_2_0002-created-at-utc-via-injected-clock.md                       # task-09
```

## 2. Tasks

> Faixa saudável 3–8; aqui **9 Tasks** (recorte fino, build verde a cada commit;
> ROADMAP-1 / concept §12 permitem >8). Nenhuma Task mistura criar port com criar
> o adapter do mesmo port (§4.3).

### Task 01 — Port-out `AnalyticsRepository` (Protocol stdlib-only)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/application/ports/out/__init__.py`
  - `src/financial_forecasting/features/analytics_store/application/ports/__init__.py`
  - `src/financial_forecasting/features/analytics_store/application/ports/out/analytics_repository.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar o `Protocol` estrutural `AnalyticsRepository` e o alias
  `Row = Mapping[str, object]`, **stdlib-only** (`collections.abc`, `typing`).
  Métodos: `write(*, layer: str, table: str, rows: Sequence[Row], allow_upsert: bool = False) -> None`
  e `read(*, layer: str, table: str, filters: Mapping[str, object] | None = None) -> Sequence[Row]`.
- **Detalhes técnicos:**
  - Docstring documenta a semântica do contrato (concept §4): partição derivada
    do schema (não do chamador); append-only nos fatos → `DuplicateKeyError` sem
    flag; upsert quando `update_policy=="upsert"` (dim_run) **ou**
    `allow_upsert=True`; `pandera` no write; `read` com pruning; round-trip
    `__none__`→`None` para `parent_sweep_id`; `(layer, table)` fora do registry →
    `ApplicationError`; `read` de dataset/asset inexistente → sequência vazia.
  - **Nada de** `pandas`/`pyarrow`/`duckdb`/`pandera`/`DataFrame` na assinatura
    (I1, A1). Criar os `__init__.py` faltantes da árvore `application/ports/{,out}`.
- **Critério de aceite (A1):** `Protocol` estrutural (sem herança), assinaturas
  keyword-only conforme §4, `mypy --strict` limpo; nenhum import de storage.
- **Comando de verificação:**
  ```bash
  mypy --strict src/financial_forecasting/features/analytics_store/application/ports/out/analytics_repository.py
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store): port-out AnalyticsRepository write/read genéricos [4.2/task-01]`

---

### Task 02 — Fake in-memory `FakeAnalyticsRepository`

- **Arquivos a criar:**
  - `tests/fakes/features/analytics_store/__init__.py`
  - `tests/fakes/features/analytics_store/in_memory_analytics_repository.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar o fake in-memory que satisfaz o port (mesma
  semântica observável do adapter real), **stdlib-only** (sem pandas/pandera).
  Mantém um registry-leve interno espelhando `logical_pk`/`partition_by`/
  `update_policy` das 5 tabelas e aceita um `Clock` injetado no construtor.
- **Detalhes técnicos:**
  - Bucketiza `rows` por tupla de partição (valores de `partition_by`, `None` →
    `"__none__"`); dentro da partição, dedup por `logical_pk`.
  - Append-only: PK colidida sem flag → `DuplicateKeyError` (de
    `shared/domain/exceptions/base.py`) com `pk_columns`/`collisions`/`path`-like
    na mensagem. Upsert quando `update_policy=="upsert"` (dim_run) **ou**
    `allow_upsert=True` (substitui só as colididas).
  - `write` de `dim_run`: se a row não traz `created_at_utc`, preenche via
    `clock.now()` ISO UTC (espelha o write-time do adapter, para paridade no
    contract). `read` filtra por `filters` (pruning lógico) e re-traduz
    `"__none__"` → `None` em `parent_sweep_id`. `(layer, table)` fora do
    registry-leve → `ApplicationError`. Dataset/asset inexistente → `()`.
  - O fake **não** valida `pandera` (isso é detalhe do adapter real; o contract
    só exige semântica observável — colisão, round-trip, vazio, dispatch).
- **Critério de aceite:** o fake importa só stdlib + exceções de domínio; expõe
  exatamente a interface do port; usável com `FakeClock`.
- **Comando de verificação:**
  ```bash
  mypy --strict tests/fakes/features/analytics_store/in_memory_analytics_repository.py
  python -c "import importlib; importlib.import_module('tests.fakes.features.analytics_store.in_memory_analytics_repository')"
  ```
- **Commit sugerido:** `test(analytics-store): fake in-memory AnalyticsRepository [4.2/task-02]`

---

### Task 03 — Contract test scaffold parametrizado `[fake]`

- **Arquivos a criar:**
  - `tests/contract/features/analytics_store/__init__.py`
  - `tests/contract/features/analytics_store/test_analytics_repository_contract.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** escrever o contract test único parametrizado por uma fixture
  `repo` que, **nesta Task, parametriza só o fake** (`_build_fake`). A estrutura
  fica pronta para o `[fake, real]` da task-06 (espelha o padrão do
  `test_medallion_store_contract.py`: fixture com `params=[...]`, `_build_real`
  adicionado depois).
- **Detalhes técnicos (casos a cobrir, concept §6/§11):**
  - round-trip write→read de uma row por tabela (linhas com dtypes que o adapter
    real aceitará: `year` `int`, hashes `str`, etc.);
  - **C1** colisão de PK lógica em fato append-only sem flag → `DuplicateKeyError`;
  - **C5** `allow_upsert=True` substitui só as colididas (demais permanecem);
  - **I3** `dim_run` faz upsert por `update_policy` mesmo sem flag;
  - **C2** `(layer, table)` fora do registry → `ApplicationError`;
  - **C4** `read` de tabela/asset inexistente → sequência vazia;
  - **A8/C6** `parent_sweep_id=None` round-trip: lido de volta como `None`;
  - **I8** `read` com `filters={"asset": ...}` devolve só o asset pedido;
  - **A6** `dim_run` com `FakeClock` fixo → `created_at_utc` determinístico.
- **Critério de aceite:** o contract passa 100% sobre o fake; uma única função de
  teste por invariante, parametrizada pela fixture `repo`.
- **Comando de verificação:**
  ```bash
  pytest tests/contract/features/analytics_store/test_analytics_repository_contract.py -v
  ```
- **Commit sugerido:** `test(analytics-store): contract test AnalyticsRepository (fake) [4.2/task-03]`

---

### Task 04 — Adapter real `ParquetAnalyticsRepository.write` + mapper `RunRecord`→row

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py`
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/mappers/__init__.py`
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/mappers/run_record_mapper.py`
  - `tests/unit/features/analytics_store/adapters/out/parquet/test_parquet_analytics_repository_write.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar a metade **`write`** do adapter (a classe é criada
  aqui com `read` levantando `NotImplementedError` provisório, preenchido na
  task-05) + o mapper `RunRecord`→row de `dim_run`. Construtor:
  `ParquetAnalyticsRepository(*, data_root: Path, clock: Clock)`.
- **Detalhes técnicos (concept §5 I2/I3/I4/I5/I7, §6 C1/C2/C3/C5):**
  - **Despacho:** `SILVER_REGISTRY[(layer, table)]`; `KeyError` → `ApplicationError`
    (não engolir o erro cru) (C2).
  - **Mapper `dim_run`:** converte `RunRecord` → `dict` e injeta
    `created_at_utc = clock.now()` em ISO 8601 UTC `string` (formato fixado:
    `datetime.now(UTC).isoformat()` via `clock`), pois o VO não o tem e o schema
    exige `nullable=False` (I5/OBS-1). **Nunca** `datetime.now()` hardcoded.
  - **Validação pandera:** `SilverTable.schema.validate(df, strict=True, coerce=False)`
    **antes** de tocar Parquet; payload fora de schema/dtype/PK → `SchemaError`
    propaga (I4, C3). (pandera `unique` ≠ dedup do write — OBS-2.)
  - **Partição literal:** path Hive das colunas de `SilverTable.partition_by`
    (1..3 níveis), `None` → `_safe_partition`/sentinel `"__none__"`; **não**
    derivar ano de âncora (divergência vs bronze, D2). Layout concept §9.
  - **Dedup/policy:** bucketiza por path de partição (I7, batch-por-partição),
    lê parquet existente da partição, detecta colisão por `logical_pk`; sem flag e
    `update_policy!="upsert"` → `DuplicateKeyError` com `pk_columns`/`collisions`/
    `path`; com `allow_upsert=True` ou `update_policy=="upsert"` substitui só as
    colididas e reescreve a partição (C1/C5/I3). Espelha
    `_write_with_overwrite_policy`/`_append_rows_partitioned`/`_pk_tuples` do
    `ParquetMedallionStore` / old `parquet_analytics_run_repository.py`.
  - **Confinamento (I1):** `pandas`/`pyarrow`/`pandera` só neste módulo.
- **Critério de aceite (A2/A3/A4/A5/A6):** unit test cobre dispatch+erro,
  pandera-antes-do-disco, partição 1..3 níveis (inclui
  `fact_oos_predictions` `asset/feature_set_name/year`), colisão→`DuplicateKeyError`,
  upsert por flag e por política, `created_at_utc` via `FakeClock`.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/analytics_store/adapters/out/parquet/test_parquet_analytics_repository_write.py -v
  mypy --strict src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py
  lint-imports
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(analytics-store): ParquetAnalyticsRepository.write append-only/upsert + mapper dim_run [4.2/task-04]`

---

### Task 05 — `ParquetAnalyticsRepository.read` (pruning + projeção + round-trip)

- **Arquivos a criar:**
  - `tests/unit/features/analytics_store/adapters/out/parquet/test_parquet_analytics_repository_read.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py`
- **O que fazer:** preencher o método `read` (substituindo o
  `NotImplementedError` provisório da task-04): leitura via DuckDB com partition
  pruning e round-trip do sentinel.
- **Detalhes técnicos (concept §5 I6/I8, §6 C4/C6, D5):**
  - **Pruning:** `filters` empurra `WHERE` para as colunas de `partition_by`
    presentes (ao menos `asset`; opcional `parent_sweep_id`/`feature_set_name`/
    `year`); varre só as partições casadas. Espelha o `read` do
    `ParquetMedallionStore` (pruning + projeção).
  - **Projeção:** seleciona as colunas do `SilverTable.schema` (não `SELECT *`),
    na ordem do schema. Sessão DuckDB com `SET TimeZone='UTC'`.
  - **Round-trip (I6/C6):** sentinel `"__none__"` em `parent_sweep_id` →
    reconstituído como `None` (`None if pd.isna(...)` análogo do store).
  - **Vazio (C4):** `(layer, table)` não gravado ou `asset` sem dados → `()`
    (não erro). `(layer, table)` fora do registry → `ApplicationError` (mesma
    porta de despacho da task-04).
  - Retorna `Sequence[Row]` (`list[dict[str, object]]`), sem `DataFrame` cruzando
    a fronteira (I1).
- **Critério de aceite (A7/A8):** unit test cobre pruning por `asset` (e opcional
  por `parent_sweep_id`/`year`), projeção do schema, round-trip `None`, e vazio
  para inexistente.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/analytics_store/adapters/out/parquet/test_parquet_analytics_repository_read.py -v
  mypy --strict src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py
  lint-imports
  ```
- **Commit sugerido:** `feat(analytics-store): ParquetAnalyticsRepository.read com pruning e round-trip __none__ [4.2/task-05]`

---

### Task 06 — Ligar o adapter real ao contract test `[fake, real]`

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `tests/contract/features/analytics_store/test_analytics_repository_contract.py`
- **O que fazer:** adicionar `_build_real` (`ParquetAnalyticsRepository(
  data_root=tmp_path, clock=FakeClock(...))`) e parametrizar a fixture `repo`
  como `[fake, real]`, de modo que **o mesmo contract** roda idêntico nas duas
  implementações (I9, A9).
- **Detalhes técnicos:**
  - As linhas de exemplo do contract devem usar os dtypes exatos que o `pandera`
    do adapter real aceita (espelha o cuidado do
    `test_medallion_store_contract.py`): `year` `int`, hashes `str`,
    `parent_sweep_id` `str|None`, etc. Ajustar as fixtures de dados se necessário.
  - `DuplicateKeyError` deve ser **o mesmo tipo** levantado por fake e real.
- **Critério de aceite (A9):** os ~8 casos do contract passam idênticos para
  `[fake, real]`; sem ramificações `if real:` no corpo dos testes (paridade
  observável).
- **Comando de verificação:**
  ```bash
  pytest tests/contract/features/analytics_store/test_analytics_repository_contract.py -v
  ```
- **Commit sugerido:** `test(analytics-store): contract test parametrizado [fake, real] [4.2/task-06]`

---

### Task 07 — Integration test particionado real (layout Hive em disco)

- **Arquivos a criar:**
  - `tests/integration/features/analytics_store/__init__.py`
  - `tests/integration/features/analytics_store/test_parquet_analytics_repository.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** integration test que escreve com o adapter real em `tmp_path`,
  inspeciona o **layout Hive no disco** (caminhos de partição literais) e confere
  políticas reais e round-trip.
- **Detalhes técnicos (concept §11 A10):**
  - Confere os caminhos: `silver/dim_run/asset=AAPL/parent_sweep_id=<sweep|__none__>/...`,
    `silver/fact_oos_predictions/asset=AAPL/feature_set_name=<fs>/year=<yyyy>/...`,
    `silver/fact_failures/asset=AAPL/...` (1..3 níveis distintos por tabela).
  - **Append-only real:** segunda escrita com PK colidida sem flag →
    `DuplicateKeyError`; com `allow_upsert=True` substitui só as colididas e o
    arquivo da partição reflete o estado upsertado.
  - **Round-trip real:** `parent_sweep_id=None` grava sob `__none__` e
    `read` devolve `None`.
  - **pandera real:** payload com dtype divergente → `SchemaError` antes do disco
    (nenhum arquivo escrito).
- **Critério de aceite (A10):** os arquivos `.parquet` existem nos paths Hive
  esperados; append-only/upsert e round-trip verificados lendo o disco.
- **Comando de verificação:**
  ```bash
  pytest tests/integration/features/analytics_store/test_parquet_analytics_repository.py -v
  ```
- **Commit sugerido:** `test(analytics-store): integration test layout Hive particionado real [4.2/task-07]`

---

### Task 08 — Wiring no `composition_root`

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
- **O que fazer:** instanciar `ParquetAnalyticsRepository(data_root=cfg.data_root,
  clock=SystemClock())` em `wire_dependencies` e expor um campo
  `analytics_repository: AnalyticsRepository` em `ApplicationDependencies`,
  **tipado pelo port** (I9/I10, A11).
- **Detalhes técnicos:**
  - Importar `SystemClock` de `shared/infrastructure/clock/system_clock.py` e o
    port `AnalyticsRepository` para tipar o campo do dataclass.
  - Nenhum use case da 4.2 (o persister é 4.3); só registrar o adapter pronto para
    consumo. Não tocar o demais wiring.
- **Critério de aceite (A11):** `wire_dependencies()` retorna o contêiner com
  `analytics_repository` tipado pelo port; `mypy --strict` limpo.
- **Comando de verificação:**
  ```bash
  pytest tests/ -k "composition or wire" -v
  mypy --strict src/financial_forecasting/composition_root.py
  lint-imports
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(analytics-store): wire ParquetAnalyticsRepository no composition root [4.2/task-08]`

---

### Task 09 — Fechar ADRs 4.2.0001 e 4.2.0002 (`accepted`)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `docs/adr/4_2_0001-analytics-repository-port-shape-and-dedicated-parquet.md`
  - `docs/adr/4_2_0002-created-at-utc-via-injected-clock.md`
- **O que fazer:** confirmar/ajustar os dois ADRs (já existentes) para
  `status: accepted`, com decisão+consequências consistentes com o que foi
  implementado (forma do port genérico + adapter Parquet dedicado; `created_at_utc`
  via `Clock` injetado). Cruzar referências de arquivo:linha com o código final.
- **Detalhes técnicos:**
  - Garantir que `4_2_0001` cobre D1 (port genérico vs 13 métodos do old) **e** D2
    (repo dedicado vs reuso do `ParquetMedallionStore`), conforme concept §7.
  - `4_2_0002` cobre D3 (OBS-1 via `Clock`).
  - D4 (`allow_upsert`) e D5 (read com pruning/round-trip) **não** viram ADR
    isolado — registrá-los como `[decision]` na §7 deste technical.
- **Critério de aceite:** ambos ADRs em `status: accepted`, frontmatter válido
  (`docs/CONVENTIONS.md` §2/§3), links resolvem.
- **Comando de verificação:**
  ```bash
  python scripts/check_frontmatter.py docs/adr/4_2_0001-analytics-repository-port-shape-and-dedicated-parquet.md docs/adr/4_2_0002-created-at-utc-via-injected-clock.md || true
  grep -l "status: accepted" docs/adr/4_2_0001-*.md docs/adr/4_2_0002-*.md
  ```
- **Commit sugerido:** `docs(analytics-store): aceitar ADRs 4.2.0001 e 4.2.0002 [4.2/task-09]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 4.2: complete` (feito pelo ORQUESTRADOR, não por esta sessão).

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + lint-imports + check_layout
pytest tests/             # todos os testes
pytest --cov=financial_forecasting.features.analytics_store \
       --cov-report=term-missing \
       tests/contract/features/analytics_store \
       tests/integration/features/analytics_store \
       tests/unit/features/analytics_store   # cobertura do BC ≥ 90%
```

### Verificações funcionais
- [ ] Escrever um `RunRecord` em `dim_run` via adapter real e ler de volta:
      `created_at_utc` presente e determinístico (com `FakeClock`),
      `parent_sweep_id=None` round-trip para `None`.
- [ ] Escrever a mesma PK lógica num fato append-only sem flag levanta
      `DuplicateKeyError`; com `allow_upsert=True` substitui só as colididas.
- [ ] Layout Hive em disco confere as colunas literais de cada tabela
      (1..3 níveis), incluindo `fact_oos_predictions` `asset/feature_set_name/year`.
- [ ] Nenhum `pandas`/`pyarrow`/`duckdb`/`pandera` fora do adapter
      (`lint-imports` `store-no-storage-leak`/`domain-purity` verdes).

### Mapping invariante ↔ teste

| Invariante / critério | Teste que prova |
|---|---|
| I1 — pureza de camada (port/fake stdlib-only) | `lint-imports` (`store-no-storage-leak`, `domain-purity`) + `mypy` na task-01/02 |
| I2 / A4 — partição literal 1..3 níveis (inclui `feature_set_name/year`) | unit `..._write.py` + integration `test_parquet_analytics_repository.py` (paths Hive) |
| I3 / A5 / C1 / C5 — append-only + upsert por flag/política → `DuplicateKeyError` | contract `[fake, real]` + unit `..._write.py` + integration |
| I4 / A3 / C3 — `pandera` antes do disco | unit `..._write.py` + integration (dtype divergente → `SchemaError`, sem arquivo) |
| I5 / A6 / OBS-1 — `created_at_utc` via `Clock` injetado | contract (`FakeClock` determinístico) + unit `..._write.py` |
| I6 / A8 / C6 — round-trip `__none__` → `None` | contract `[fake, real]` + unit `..._read.py` + integration |
| I7 — escrita batch-por-partição | unit `..._write.py` (bucketização) |
| I8 / A7 / C4 — read pruning + projeção + vazio | contract + unit `..._read.py` |
| I9 / A9 — Protocol + contract `[fake, real]` (paridade) | contract `test_analytics_repository_contract.py` |
| I10 / A11 — injeção + instanciação única (composition root) | task-08 wiring test + `check_layout` |
| C2 / A2 — `(layer, table)` fora do registry → `ApplicationError` | contract + unit (`write` e `read`) |
| I11 / A12 — gates verdes + cobertura ≥ 90% | `make check` + `pytest --cov` |

### Checklist de fechamento da Stage
- [ ] Todas as 9 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura do BC `analytics_store` ≥ 90%
- [ ] ADRs `4_2_0001` e `4_2_0002` em `status: accepted`
- [ ] `concept.md` desta Stage não precisou de retoque retrospectivo material
- [ ] **(orquestrador)** commit final `stage 4.2: complete` + `roadmap.md` `done`

## 4. Ordem de dependência entre Tasks

```
task-01 (port) ─► task-02 (fake) ─► task-03 (contract [fake])
                                          │
task-01 ──────────────────────────► task-04 (adapter.write + mapper)
                                          │
                                     task-05 (adapter.read) ──► task-06 (contract [fake,real])
                                                                     │
                                                                task-07 (integration Hive)
task-04/05 ─────────────────────────────────────────────────► task-08 (wiring)
                                                                task-09 (ADRs) — independente, fecha por último
```

- task-03 só precisa de task-01+02 (build verde sobre o fake).
- task-06 precisa do adapter real completo (task-04+05).
- task-09 (ADRs) é independente do código; pode ir por último.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Dtype do contract não bate com `pandera` do adapter real (task-06) | Ajustar as fixtures de dados do contract para os dtypes do schema (espelha `test_medallion_store_contract.py`); registrar `[deviation]` |
| DuckDB pruning não casa o sentinel `__none__` em `WHERE` | Tratar `None` no `filters` como igualdade com `'__none__'` na query; cobrir no unit `..._read.py` |
| `pandera` `strict=True` reprovar coluna de partição extra no DataFrame | Validar o DataFrame com as colunas do schema **antes** de adicionar colunas de partição derivadas (ordem: validar → particionar → escrever) |
| Reuso indevido do motor do bronze acoplaria silver↔bronze | D2/ADR 4.2.0001: adapter dedicado, sem import de `ParquetMedallionStore`; copiar os ~40 linhas de dedup |
| Cobertura < 90% por ramos de erro do adapter | Adicionar casos de erro (C2/C3) no unit de write/read antes de fechar |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (contratos §4, invariantes §5, casos §6, decisões §7)
- [`../../overview.md`](../../overview.md) — §3/§6/§7/§11
- [`../../roadmap.md`](../../roadmap.md) — Stage 4.2 (DoD, non_goals)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md) — §B 4.2 (regras append-only/upsert/partição)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits §4, frontmatter §2/§3
- [`../../LAYOUT.md`](../../LAYOUT.md) — regras de import/camadas
- ADRs desta Stage: [`../../adr/4_2_0001-...`](../../adr/4_2_0001-analytics-repository-port-shape-and-dedicated-parquet.md), [`../../adr/4_2_0002-...`](../../adr/4_2_0002-created-at-utc-via-injected-clock.md)
- ADR governança: [`../../adr/0_0_0050-autonomous-overnight-mode.md`](../../adr/0_0_0050-autonomous-overnight-mode.md)
- Skills aplicáveis: `repository-pattern`, `pytest-with-fakes`, `task-ordering-hex`, `composition-root`, `hex-arch-python`, `import-linter-rules`
- Forma espelhada (2.1): `shared/application/ports/out/medallion_store.py`, `shared/adapters/out/parquet/parquet_medallion_store.py`, `tests/contract/shared/test_medallion_store_contract.py`
- Repo antigo: `financial-time-series-forecasting/src/adapters/parquet_analytics_run_repository.py` (motor dedup/overwrite/batch-por-partição)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
>
> Modo autônomo overnight (ADR 0.0.0050): decisões fora de questão fechada são
> tomadas pela sessão (sem perguntar) e registradas aqui como `[decision]`.
> D4 (`allow_upsert`) e D5 (read com pruning/round-trip) já antecipados no
> concept §7 como decisões sem ADR isolado — confirmar aqui se materializarem
> divergência na execução.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Decisão/Razão:** <...>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage** (+ Stage candidata).
- `[deviation]` — ajuste pequeno vs. o plano original.

### 2026-06-29 — [decision] escopo 4.2 (task-04) — flag `allow_upsert` + reuso de `DuplicateKeyError` (D4)
**Contexto:** o concept §7 D4 antecipou `allow_upsert: bool = False` no `write` e o
reuso de `DuplicateKeyError(ApplicationError)` (sem ADR isolado).
**Decisão/Razão:** materializado como previsto — `write(*, ..., allow_upsert=False)`;
upsert acontece quando `allow_upsert=True` **ou** `meta.update_policy == "upsert"`
(`dim_run`); colisão sem flag levanta o MESMO `DuplicateKeyError` do
`ParquetMedallionStore`, com mensagem `pk_columns`/`collisions`/`path`. Nenhum tipo
novo de exceção. Decisão de baixo risco confirmada na execução.

### 2026-06-29 — [decision] escopo 4.2 (task-05) — `read` com pruning + round-trip `__none__` → `None` (D5)
**Contexto:** o concept §7 D5 antecipou a leitura (ausente no old) com pruning,
projeção do schema e round-trip do sentinel (sem ADR isolado).
**Decisão/Razão:** implementado via DuckDB com `hive_partitioning=false` —
**divergência consciente vs `ParquetMedallionStore` (que usa `hive_partitioning=true`)**:
no silver as colunas de partição (`asset`/`parent_sweep_id`/`feature_set_name`/`year`)
são **físicas no Parquet** (não derivadas de âncora), então o hive partitioning
duplicaria colunas; ler as colunas físicas + projetar o schema basta. O `WHERE` nas
colunas de `partition_by` vindas de `filters` faz o pruning; `parent_sweep_id`/`NaN`/
`__none__` voltam como `None`.

### 2026-06-29 — [decision] escopo 4.2 (task-05) — sentinel `__none__` materializado na coluna física (não só no path)
**Contexto:** ao implementar o `read`, uma partição com `parent_sweep_id=None`
gravava a coluna física como `NULL`; o DuckDB tipava a coluna toda-NULL como
`"NULL"` e o `WHERE parent_sweep_id = ?` (VARCHAR) falhava com `ConversionException`.
**Decisão/Razão:** no `write`, após a validação `pandera`, materializo o sentinel
`__none__` também na **coluna física** das partições nullable (`parent_sweep_id`),
não só no path — path e coluna passam a concordar e a coluna é sempre VARCHAR. O
`read` reconverte `__none__` → `None` (round-trip I6/C6 preservado). Não altera o
contrato observável (testado em contract `[fake, real]` + integration).

### 2026-06-29 — [decision] escopo 4.2 (task-06) — `created_at_utc` write-time também no caminho genérico do `write`
**Contexto:** o contract `[fake, real]` escreve rows dict-like de `dim_run` SEM
`created_at_utc` (o fake preenche em `_prepare`). O adapter real validava `pandera`
ANTES de preencher, então o caminho genérico (`write` de um dict de `dim_run`)
reprovava por `created_at_utc` ausente — quebrando a paridade fake↔real.
**Decisão/Razão:** o `write` do adapter passa a preencher `created_at_utc` via o
`Clock` injetado (`_fill_write_time`) para `dim_run` quando a coluna falta, ANTES da
validação — espelhando o fake e fechando a paridade do contrato genérico. O mapper
`run_record_to_row` segue como caminho tipado para `RunRecord`; o preenchimento é
idempotente (se o mapper já preencheu, o `write` não sobrescreve). Coerente com a
intenção de ADR 4.2.0002 (write-time concern via `Clock`, nunca `datetime.now()`).

### 2026-06-29 — [deviation] escopo 4.2 (task-05) — remoção do teste provisório `NotImplementedError`
**Contexto:** o task-04 deixou `read` provisório com um teste
`test_read_is_not_implemented_yet`; o task-05 implementou `read`.
**Decisão/Razão:** removi esse teste no task-05 (o `read` agora é coberto por
`test_..._read.py`); ajuste pequeno e esperado pelo plano inside-out.

### 2026-06-29 — [deviation] escopo 4.2 (task-05-extra) — teste do lado positivo do round-trip de `parent_sweep_id`
**Contexto:** auditoria de testes (mutation-mental). A cobertura de linha estava
em 100%, mas o round-trip do sentinel só tinha o lado `None` coberto
(`test_read_round_trips_parent_sweep_id_none`). Inverter a guarda do sentinel em
`_restore_value` (`value == _PARTITION_NONE` → `!=`) nulaava um `parent_sweep_id`
real e NENHUM teste falhava.
**Decisão/Razão:** adicionados `test_read_preserves_real_parent_sweep_id_value`
(unit read) e `test_parent_sweep_id_real_value_round_trip` (contract `[fake, real]`)
que asseguram que um `parent_sweep_id` legítimo (`"sweep-1"`/`"sweep-42"`) volta
como a string literal. Mutação confirmada como capturada (I6/C6 lado positivo).

### 2026-06-29 — [deviation] escopo 4.2 (task-04-extra) — idempotência do `created_at_utc` write-time
**Contexto:** auditoria de testes (mutation-mental). Todos os testes de `dim_run`
fixavam `created_at_utc == FakeClock.now()`, então o guard
`prepared.get(_CREATED_AT_UTC) is None` em `_fill_write_time` era indistinguível
de "preencher sempre" — remover o guard (clobber) passava silenciosamente,
contrariando a idempotência registrada na entrada [decision] do task-06.
**Decisão/Razão:** adicionado `test_write_does_not_clobber_existing_created_at_utc`
com um `created_at_utc` pré-existente DIFERENTE do clock; o write deve preservá-lo.
Mutação (drop do guard) confirmada como capturada (I5).

### 2026-06-29 — [deviation] escopo 4.2 (task-04-extra) — conteúdo diagnóstico da `DuplicateKeyError`
**Contexto:** auditoria de testes (mutation-mental). O contrato C1 exige que a
`DuplicateKeyError` cite `pk_columns`/`collisions`/`path`, mas nenhum teste
inspecionava a mensagem — esvaziá-la passaria silenciosamente.
**Decisão/Razão:** adicionado
`test_collision_message_carries_pk_columns_and_path` (unit write) asseverando os
três marcadores + o nome da coluna de PK na mensagem. Mutação (mensagem trocada
por `"collision"`) confirmada como capturada (C1, diagnóstico).

<!-- END: post-execution -->
