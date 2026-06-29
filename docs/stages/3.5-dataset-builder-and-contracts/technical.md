---
title: Technical — Stage 3.5 — Dataset builder e contratos
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, dataset-builder, build-dataset, target-definition, anti-leakage, pandera, quality-gate, composition-root]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.5-dataset-builder-and-contracts
stage_title: Dataset builder e contratos
step_id: 3
step_title: Feature engineering e dataset
depends_on: [3.1-technical-indicators, 3.2-sentiment-finbert, 3.3-fundamentals-asof-join, 3.4-feature-registry-and-derived]
concept_ref: ./concept.md
issue_id: 31
branch: feat/31-3-5-dataset-builder-and-contracts
tasks_count: 8
---

# Technical — Stage 3.5 — Dataset builder e contratos

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.5/task-NN]`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage).
>    O commit final `stage 3.5: complete` e a marcação `done` no `roadmap.md`
>    **são do orquestrador** (pós-auditoria independente), não desta sessão.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/31-3-5-dataset-builder-and-contracts` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

Esta é a **Stage de integração do Step 3** no BC `feature_engineering`. Construímos
os artefatos que fazem convergir os quatro produtos das Stages 3.1–3.4 num único
dataset TFT causal, auditável e validado: o domain-service puro `TargetDefinition`
(dono único do alvo backward log-return), o domain-service `DatasetQualityGate`
(gate warmup-aware), o adapter `DatasetAssembler` (montagem pandas/duckdb +
validadores anti-leakage in-process que re-derivam cada feature via o oráculo puro
`DerivedFeatures` 3.4 + indicadores canônicos 3.1), o `dataset_schema` pandera
(contrato físico das 62 colunas) e o use case `BuildDataset` (orquestração que
depende só de ports e devolve DTO frozen). Por fim, o **wiring** em
`composition_root.py` instancia os 3 adapters concretos do BC + `BuildDataset` —
**resolvendo os findings F2 de wiring deferido** das auditorias 3.1/3.2/3.3 (sem
isso esses ports/adapters seriam dead-code).

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`, Stage de fatia vertical em 1 BC):
domain puro primeiro (Tasks 01–02), depois o adapter de montagem e seus validadores
(Task 03) e o schema pandera (Task 04) — ambos `adapters/out`, testáveis com dados
sintéticos sem orquestração —, então o use case `BuildDataset` testado **com fakes
dos ports** (Task 05, reusando os fakes `InMemory*` já existentes de 3.1/3.2/3.3),
o wiring no composition root (Task 06), o teste de integração end-to-end contra o
oráculo AAPL (Task 07) e o fechamento de débitos/`make check` final (Task 08).

> **Desvio justificado ao default inside-out** (skill `task-ordering-hex`, regra
> "declare exceções no preâmbulo): o `DatasetAssembler` (adapter out, Task 03) é
> construído **antes** do use case `BuildDataset` (application, Task 05), invertendo
> a ordem "application antes de adapter out". Razão: o assembler é a engine física
> de montagem (pandas/duckdb) que hospeda os validadores anti-leakage e produz o
> `DataFrame`; ele é **dado ao use case via port/Protocol** (o use case não monta
> nada, só orquestra). Os ports consumidos pelo use case (`IndicatorCalculator`,
> `SentimentModel`, `AsofJoinAdapter`) já existem de 3.1/3.2/3.3 com fakes prontos,
> então o use case (Task 05) já nasce testável com fakes — o assembler também é
> exposto ao use case por um Protocol `DatasetAssemblerPort` (Task 03) com fake
> próprio. Nenhuma Task mistura criação de port com criação do seu adapter.

### Pré-condições

- Stages `3.1`, `3.2`, `3.3`, `3.4` em `done` e seus artefatos presentes no BC
  `feature_engineering` (ports, adapters, fakes, `FeatureRegistry`,
  `DerivedFeatures`).
- Stage `2.1` (`MedallionStore` + `ParquetMedallionStore`) e `2.4`
  (`TradingCalendar`) em `done`.
- ADRs `3_5_0001` e `3_5_0002` presentes em `docs/adr/` (já criados na Fase 3A);
  promovidos a `accepted` no fechamento.
- Oráculo `data/processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet` disponível
  (4023 linhas × 62 colunas) para o teste de regressão de integração (Task 07).
- `concept.status == done`.

### Premissas técnicas

- Python 3.12; `uv`; `mypy --strict` em `domain/`+`application/`; `ruff`; pandera
  e pandas/duckdb já disponíveis como deps de `adapters/out`.
- `FeatureRegistry` é a **fonte única** do set, da ordem e do warmup por feature —
  sem lista paralela `FEATURE_WARMUP_BARS`.
- pandas/duckdb/pyarrow **confinados** a `adapters/out`; `import-linter`
  (`store-no-storage-leak`, `domain-purity`) + `check_layout.py` são gate.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── features/feature_engineering/
│   ├── domain/services/
│   │   ├── target_definition.py                    # Task 01
│   │   └── dataset_quality_gate.py                 # Task 02
│   ├── application/
│   │   ├── ports/out/dataset_assembler.py          # Task 03 (Protocol)
│   │   └── use_cases/build_dataset.py              # Task 05 (use case + DTOs)
│   └── adapters/out/
│       ├── pandas/dataset_assembler.py             # Task 03 (impl + validadores)
│       └── parquet/schemas/dataset_schema.py       # Task 04 (pandera)
├── composition_root.py                             # Task 06 (wiring)
tests/
├── unit/features/feature_engineering/
│   ├── domain/
│   │   ├── test_target_definition.py               # Task 01
│   │   └── test_dataset_quality_gate.py            # Task 02
│   └── application/test_build_dataset.py           # Task 05 (com fakes)
├── contract/features/feature_engineering/
│   ├── test_dataset_assembler_anti_leakage.py      # Task 03
│   └── test_dataset_schema.py                      # Task 04
├── fakes/features/feature_engineering/
│   └── in_memory_dataset_assembler.py              # Task 03
├── unit/test_composition_root.py                   # Task 06 (wiring)
└── integration/features/feature_engineering/
    └── test_build_dataset_aapl.py                  # Task 07
```

## 2. Tasks

### Task 01 — `TargetDefinition` (domain-service puro, dono único do alvo)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/target_definition.py`
  - `tests/unit/features/feature_engineering/domain/test_target_definition.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** criar função pura stdlib-only que recebe os closes ordenados por
  timestamp e devolve a série de alvo alinhada com a convenção **backward**
  `target[t] = log(close_t / close_{t-1})` e `target[0] = None`. **Dono único** do
  alvo (concept I1, D1, ADR `3_5_0001`).
- **Detalhes técnicos:**
  - Assinatura: `compute_target_return(closes: Sequence[float]) -> tuple[float | None, ...]`,
    `len(saída) == len(closes)`, `saída[0] is None`, demais `= math.log(c_t/c_{t-1})`.
  - stdlib only (`math`, `collections.abc`); **proibido** pandas/numpy/pydantic.
  - C1: menos de 2 closes → `ValueError("not enough rows to compute target_return")`.
    Close `<= 0` ou não-finito → `ValueError` claro.
  - Verbatim com old `build_tft_dataset_use_case.py:563-572`; alinhado na origem
    com `target_timestamp` da 4.3 (`timestamp_utc = decision_day`).
- **Critério de aceite:** testes cobrem happy path (valores conferidos contra
  `math.log` manual), `target[0] is None`, C1 (<2 closes), close inválido; sem
  import de pandas/numpy.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/feature_engineering/domain/test_target_definition.py -v
  mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/target_definition.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering): TargetDefinition backward log-return [3.5/task-01]`

---

### Task 02 — `DatasetQualityGate` (domain-service, gate warmup-aware)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/dataset_quality_gate.py`
  - `tests/unit/features/feature_engineering/domain/test_dataset_quality_gate.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** criar `DatasetQualityGateConfig` (frozen dataclass) +
  `DatasetQualityGate` (domain-service) operando sobre `Sequence`/`Mapping` (não
  `DataFrame`), lendo o warmup do `FeatureRegistry` (sem lista paralela). Concept
  I5, D4; old `dataset_quality_gate.py:87-99`.
- **Detalhes técnicos:**
  - `DatasetQualityGateConfig(frozen)`: `max_nan_ratio_per_feature: float`,
    `require_unique_timestamps: bool`, `require_monotonic_timestamps: bool`,
    `min_temporal_coverage_days: int`.
  - Gate: (a) warmup — dropa linhas antes do warmup máximo do registry; mede
    NaN-ratio por feature **após** descontar o warmup de cada uma; (b)
    monotonicidade — timestamps únicos + ordenados (C4 → erro de domínio); (c)
    missing — NaN-ratio por feature ≤ máximo; `failing_features` ordenado desc.
    (C5); (d) cobertura temporal mínima (C6).
  - Lê o warmup via `FeatureRegistry` (`get_feature_spec(...).warmup_count` /
    `list_feature_specs`); stdlib only.
- **Critério de aceite:** testes cobrem warmup-drop + NaN-ratio pós-warmup, erro
  em timestamp duplicado e não-monótono, `failing_features` ordenado desc.,
  cobertura insuficiente; stdlib-only (sem pandas/numpy).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/feature_engineering/domain/test_dataset_quality_gate.py -v
  mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/dataset_quality_gate.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering): DatasetQualityGate warmup-aware [3.5/task-02]`

---

### Task 03 — Port `DatasetAssembler` + adapter pandas com validadores anti-leakage

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/application/ports/out/dataset_assembler.py`
  - `src/financial_forecasting/features/feature_engineering/adapters/out/pandas/dataset_assembler.py`
  - `tests/fakes/features/feature_engineering/in_memory_dataset_assembler.py`
  - `tests/contract/features/feature_engineering/test_dataset_assembler_anti_leakage.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** declarar o port `DatasetAssemblerPort` (Protocol) cuja fronteira
  não vaza `DataFrame` (troca primitivos/`Mapping`/`Sequence`), criar o adapter
  concreto em `adapters/out/pandas` que monta o `DataFrame` (pandas/duckdb
  confinados) e **hospeda os validadores anti-leakage in-process**, e um fake
  in-memory para o port. Concept §4 (`DatasetAssembler`), D5, I2, I3, I4.
  > **Exceção declarada (§4.3 regra 4):** port + adapter ficam em Tasks
  > conceitualmente separadas, mas aqui o port `DatasetAssemblerPort` e seu **fake**
  > entram no mesmo commit que o adapter real porque o contract test de paridade
  > anti-leakage precisa do trio (port/fake/real) coeso; o adapter real é a
  > entrega central da Task. Justificado pela coesão do contrato anti-leakage.
- **Detalhes técnicos:**
  - Port `DatasetAssemblerPort.assemble(...)` recebe insumos primitivos das 4
    famílias + grade de pregão + alvo e devolve estrutura tabular agnóstica
    (`Sequence[Mapping[str, object]]` ou DTO equivalente) — **nunca** `DataFrame`
    cruza a fronteira (I7/I6).
  - Adapter monta na ordem candles→grade→indicadores→sentimento→derivadas→
    as-of→derivadas-de-fundamento→time-features; reordena colunas pelo
    `FeatureRegistry` antes de devolver (I7); regimes/flags `float64` com NaN no
    warmup (D2 / ADR `3_5_0002`).
  - **Validadores anti-leakage (I2/D3):** re-derivar **cada** feature via
    `DerivedFeatures` (3.4) + `IndicatorCalculator` canônico (3.1) como **oráculo
    puro** e conferir contra o valor montado (`atol ~1e-12`); divergência ⇒
    `AntiLeakageError` nomeando a feature (C2). **Não** re-implementar a fórmula
    inline em pandas (old `:346-372`).
  - **Guarda as-of (I3/C3):** após o merge, re-checar
    `fundamentals_effective_date <= day`; violação ⇒ `AntiLeakageError`.
  - `AntiLeakageError` é o de 3.3 (`fundamentals_asof_policy.py`) — **reutilizar**,
    não redefinir.
- **Critério de aceite:** contract test injeta divergência sintética numa feature
  e espera `AntiLeakageError` nomeando-a; testa a guarda as-of
  (`effective_date > day` ⇒ erro); confirma ordem de colunas = registry e regimes
  `float64`; fake satisfaz o Protocol por duck-typing.
- **Comando de verificação:**
  ```bash
  pytest tests/contract/features/feature_engineering/test_dataset_assembler_anti_leakage.py -v
  mypy --strict src/financial_forecasting/features/feature_engineering/application/ports/out/dataset_assembler.py
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(feature-engineering): DatasetAssembler + validadores anti-leakage [3.5/task-03]`

---

### Task 04 — `dataset_schema` pandera (contrato físico das 62 colunas)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/adapters/out/parquet/schemas/dataset_schema.py`
  - `tests/contract/features/feature_engineering/test_dataset_schema.py`
- **Arquivos a modificar:** nenhum (criar `__init__.py` em `parquet/`/`parquet/schemas/` se faltarem — não conta como Task)
- **O que fazer:** criar o schema pandera que valida o `DataFrame` montado:
  colunas-base + dtypes, nullability, presença e **ordem** do set de features do
  `FeatureRegistry`. **Sem** regra de negócio (unicidade/monotonia/warmup ficam no
  domain gate). Concept §4 (`dataset_schema`), I7, D2, C7, C8.
- **Detalhes técnicos:**
  - dtypes: `asset_id=string`;
    `timestamp`/`fundamentals_effective_date=timestamp[ns, UTC]`;
    `time_idx`/`day_of_week`/`month`/`news_volume`/`has_news`/
    `volume_spike_flag=int64`; `target_return` e demais features `=float64`
    (regimes `float64` por D2).
  - Set/ordem das colunas de feature derivados de `FeatureRegistry`
    (`list_feature_specs`) — não hardcodar lista paralela.
  - Confinado a `adapters/out`; `pandera`/`pandas` só aqui. Coluna ausente, dtype
    divergente ou ordem quebrada ⇒ `SchemaError` (C7); coluna do registry ausente
    ou extra ⇒ erro antes do schema (C8).
- **Critério de aceite:** teste valida um `DataFrame` mínimo conforme (passa) e
  variações inválidas (coluna ausente, dtype errado, ordem trocada → `SchemaError`);
  confere que o set de colunas de feature vem do registry (62 colunas no oráculo).
- **Comando de verificação:**
  ```bash
  pytest tests/contract/features/feature_engineering/test_dataset_schema.py -v
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(feature-engineering): schema pandera do dataset TFT [3.5/task-04]`

---

### Task 05 — Use case `BuildDataset` + DTOs (testado com fakes dos ports)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/application/use_cases/build_dataset.py`
  - `tests/unit/features/feature_engineering/application/test_build_dataset.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** criar o use case `BuildDataset` (application) que orquestra o
  join das 4 famílias sobre a grade de pregão, anexa o alvo (`TargetDefinition`),
  aplica o gate (`DatasetQualityGate`), delega a montagem física ao
  `DatasetAssemblerPort` e persiste via `MedallionStore`. Recebe/devolve **DTO
  frozen**; depende **só de ports**. Concept §4, I1, I6, A2.
- **Detalhes técnicos:**
  - `BuildDatasetRequest(frozen)`: `asset: str`, `start: date | None`,
    `end: date | None`.
  - `BuildDatasetResult(frozen)`: `asset: str`, `n_rows: int`, `start: date`,
    `end: date`, `feature_set_hash: str`, `n_features: int`.
  - Depende dos ports `IndicatorCalculator` (3.1), `SentimentModel` via
    `ScoreAndAggregateSentiment` (3.2), `AsofJoinAdapter` + `FundamentalsAsofPolicy`
    (3.3), `TradingCalendar` (2.4), `DatasetAssemblerPort` (Task 03),
    `MedallionStore` (2.1); usa `FeatureRegistry` (set/ordem/hash) + `TargetDefinition`
    + `DatasetQualityGate` (domain). **Nunca** devolve entidade nem `DataFrame`.
  - `feature_set_hash` (de `FeatureRegistry.feature_set_hash`) registrado no result.
  - C1 propagado de `TargetDefinition`; gate erra conforme C4–C6.
- **Critério de aceite:** teste com **fakes** de todos os ports (`InMemory*` de
  3.1/3.2/3.3 + fake do assembler da Task 03 + fake `MedallionStore`) cobre happy
  path (result com `n_rows`/`n_features`/`feature_set_hash` corretos), C1 e
  propagação de erro do gate; valida que não devolve entidade nem `DataFrame`.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/feature_engineering/application/test_build_dataset.py -v
  mypy --strict src/financial_forecasting/features/feature_engineering/application/use_cases/build_dataset.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering): use case BuildDataset com DTOs frozen [3.5/task-05]`

---

### Task 06 — Wiring no composition root (resolve findings F2)

- **Arquivos a criar:**
  - `tests/unit/test_composition_root.py` (ou estender o existente, se houver)
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
- **O que fazer:** instanciar no `composition_root.py` os 3 adapters concretos do
  BC (`PandasTaIndicatorCalculator` 3.1, `FinbertSentimentModel` 3.2,
  `AsofJoinDuckdbAdapter` 3.3) + `DatasetAssembler` (pandas) + `BuildDataset`,
  expostos em `ApplicationDependencies` por campos **tipados pelos ports**
  (não pelos concretos). **Resolve os findings F2 de wiring deferido** (I8, A7).
- **Detalhes técnicos:**
  - Adicionar campos a `ApplicationDependencies` tipados por `IndicatorCalculator`,
    `SentimentModel`, `AsofJoinAdapter`, `DatasetAssemblerPort`, e o use case
    `BuildDataset` (já montado).
  - Instanciar os concretos **apenas** dentro de `wire_dependencies` (composition
    root é o único lugar — skill `composition-root`).
  - Sem singletons globais; injeção explícita via construtor do use case.
- **Critério de aceite:** teste de wiring monta `wire_dependencies(...)` com
  `Settings` fake e confere que os campos existem, são tipados pelos ports e que
  `BuildDataset` está montado com os adapters reais (não fakes). `make check` verde.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/test_composition_root.py -v
  mypy --strict src/financial_forecasting/composition_root.py
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(feature-engineering): wira BuildDataset + 3 adapters no composition root [3.5/task-06]`

---

### Task 07 — Teste de integração end-to-end AAPL contra o oráculo

- **Arquivos a criar:**
  - `tests/integration/features/feature_engineering/test_build_dataset_aapl.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** rodar `BuildDataset` para AAPL (via wiring real do composition
  root) e bater **set + ordem de colunas + contagem (62) + n_rows** contra o
  oráculo `data/processed/dataset_tft/AAPL/dataset_tft_AAPL.parquet`
  (regressão por colunas/contagem, **não** bit-identidade). Concept A6, I7.
- **Detalhes técnicos:**
  - Usar o AAPL existente; comparar colunas/ordem/contagem e `n_rows` (~4023) com
    tolerância de regressão (não comparar bytes).
  - Marcar com `@pytest.mark.integration`; pode pular (skip) se o oráculo/dados
    não estiverem presentes no ambiente de CI (documentar a condição de skip).
  - Confirma que `feature_set_hash` no result é estável.
- **Critério de aceite:** integração roda AAPL, set+ordem+contagem de colunas (62)
  batem com o oráculo, `n_rows` dentro da tolerância; schema pandera passa antes
  de persistir; sem `AntiLeakageError`.
- **Comando de verificação:**
  ```bash
  pytest tests/integration/features/feature_engineering/test_build_dataset_aapl.py -v
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `test(feature-engineering): integração BuildDataset AAPL vs oráculo [3.5/task-07]`

---

### Task 08 — Fechamento: débitos registrados e `make check`/`test-cov` verdes

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `docs/stages/3.5-dataset-builder-and-contracts/technical.md` (§7 — entradas
    `[decision]`/`[deviation]` de D3/D4/D5/D6 e do desvio de ordem da Task 03)
  - ADRs `3_5_0001`/`3_5_0002`: confirmar `status: accepted`
- **O que fazer:** registrar em §7 os `[decision]`/`[deviation]` previstos
  (D3 oráculo puro; D4 config do gate; D5 engine confinada; D6 coexistência
  `IndicatorSpec`/`FeatureSpec`; desvio de ordem assembler-antes-do-use-case),
  confirmar ADRs `accepted`, e rodar a suíte completa + cobertura.
- **Detalhes técnicos:**
  - §7 editável só entre os marcadores `BEGIN/END: post-execution`
    (`check_technical_postexec.py`).
  - Cobertura global ≥ 90% (`make test-cov`).
- **Critério de aceite:** `make check` e `make test-cov` (≥ 90%) verdes;
  `check_technical_postexec.py` verde; ADRs `accepted`; §7 reflete a execução.
- **Comando de verificação:**
  ```bash
  make check
  make test-cov
  python scripts/check_technical_postexec.py
  ```
- **Commit sugerido:** `docs(feature-engineering): registra decisões da execução 3.5 [3.5/task-08]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage entregar a branch pronta. O commit
> `stage 3.5: complete` e a marcação `done` no `roadmap.md` são do **orquestrador**
> (pós-auditoria independente), não desta sessão.

### Verificações automatizadas
```bash
make check                # lint + type + import-linter + check_layout + testes
make test-cov             # cobertura ≥ 90%
pytest tests/             # todos os testes
python scripts/check_technical_postexec.py   # §7 do technical restrita aos marcadores
```

### Verificações funcionais
- [ ] `BuildDataset` para AAPL produz dataset com **62 colunas** na ordem do
      `FeatureRegistry` e `n_rows` ~4023, batendo o oráculo por set/ordem/contagem.
- [ ] Validadores anti-leakage levantam `AntiLeakageError` em divergência sintética
      e na guarda as-of (`effective_date > day`).
- [ ] `composition_root.py` expõe `BuildDataset` + os 3 adapters do BC tipados
      pelos ports; nenhum dos ports 3.1/3.2/3.3 é dead-code.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — alvo backward log-return, dono único, `target[0]=None` | `test_target_definition.py` (happy + C1 + close inválido) |
| I2 — anti-leakage re-derivado via oráculo puro, `atol~1e-12` | `test_dataset_assembler_anti_leakage.py` (divergência sintética → `AntiLeakageError`) |
| I3 — as-of backward defense-in-depth + coluna persistida | `test_dataset_assembler_anti_leakage.py` (guarda `effective_date <= day`) |
| I4 — causalidade das derivadas (shifts n>0; fundamento depois do as-of) | `test_dataset_assembler_anti_leakage.py` (ordem de montagem) + `test_build_dataset_aapl.py` |
| I5 — gate (warmup / monotonia / missing / cobertura) | `test_dataset_quality_gate.py` (C4/C5/C6) |
| I6 — pureza/camadas; DTO frozen; use case só ports | `check_layout.py` + `lint-imports` + `mypy --strict` + `test_build_dataset.py` |
| I7 — `FeatureRegistry` fonte única de set/ordem; hash no result | `test_dataset_schema.py` + `test_build_dataset.py` + `test_build_dataset_aapl.py` |
| I8 — wiring dos 3 adapters + `BuildDataset`, campos tipados por ports | `test_composition_root.py` |

### Checklist de fechamento da Stage
- [ ] Todas as Tasks (01–08) commitadas, cada uma com seu check verde
- [ ] `make check` e `make test-cov` (≥ 90%) verdes no branch
- [ ] §7 do `technical.md` reflete a execução (`[decision]`/`[deviation]`)
- [ ] `check_technical_postexec.py` verde
- [ ] ADRs `3_5_0001`/`3_5_0002` em `status: accepted`
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
- [ ] **NÃO** fazer `stage 3.5: complete` nem marcar roadmap `done` — é do orquestrador

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências. Explicitando os acoplamentos:

```
Task 01 (TargetDefinition) ─┐
Task 02 (QualityGate)       ├─► Task 05 (BuildDataset use case) ─► Task 06 (wiring) ─► Task 07 (integração) ─► Task 08 (fechamento)
Task 03 (Assembler+port)   ─┤
Task 04 (schema pandera)   ─┘
```

- Tasks 01–04 são independentes entre si (domain puro + adapters out + schema);
  podem ser feitas em qualquer ordem relativa, mas a ordem inside-out (domain →
  adapter → schema) é a recomendada.
- Task 05 depende de 01, 02, 03 (consome `TargetDefinition`, `DatasetQualityGate`,
  `DatasetAssemblerPort`) e usa o `FeatureRegistry` (já existente de 3.4).
- Task 06 depende de 03, 04, 05 (wira o use case + assembler real + adapters).
- Task 07 depende de 06 (usa o wiring real). Task 08 fecha após 07.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Dtype de regimes diverge do oráculo (int64 vs float64) | D2 / ADR `3_5_0002`: `float64` com NaN no warmup; `test_dataset_schema.py` cobre |
| Ordem de montagem ≠ ordem do registry | Assembler reordena pelo `FeatureRegistry` antes do schema; teste de ordem (I7) |
| Validador anti-leakage com falso-negativo (re-shift inline) | D3: usar oráculo puro 3.4 (`DerivedFeatures`), não fórmula inline; teste injeta divergência sintética |
| `DataFrame` vaza pela fronteira do port | Port `DatasetAssemblerPort` troca primitivos; `lint-imports`/`check_layout.py` reprovam vazamento |
| Oráculo AAPL ausente no CI | Task 07 marcada `integration` com skip condicional documentado; regressão roda local |
| Cobertura < 90% | Reforçar testes unitários de domain (01/02) e do use case com fakes (05) antes do fechamento |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md) — §"Modelagem e dados" (`0_0_0016`, `0_0_0018`), §"Arquitetura" (`0_0_0021`, `0_0_0022`)
- [`../../roadmap.md`](../../roadmap.md) — §Stage 3.5; grafo `3.1–3.4 → 3.5`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits §4, status §3
- [`../../PIPELINE.md`](../../PIPELINE.md) — §4 Task atômica, §10 fluxo Git
- ADRs desta Stage: [`../../adr/3_5_0001-target-definition-backward-log-return.md`](../../adr/3_5_0001-target-definition-backward-log-return.md), [`../../adr/3_5_0002-regime-features-nan-warmup-dtype.md`](../../adr/3_5_0002-regime-features-nan-warmup-dtype.md)
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`, `composition-root`, `import-linter-rules`
- Old: `src/use_cases/build_tft_dataset_use_case.py` (418-624), `src/domain/services/dataset_quality_gate.py` (87-99)

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
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão. Apenas após a decisão, registre a entrada abaixo.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage**; inclui Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

<!-- END: post-execution -->
