---
title: Technical — Stage 4.3 — Persister de predições multi-horizonte (analytics_store)
description: Plano de execução do domain service MultiHorizonPredictionPersister (dono único do target_timestamp indexado por dia de pregão), do VO QuantileForecast (grade densa + guardrail monotônico) e do use case PersistPredictions (grava LONG raw+guardrail via AnalyticsRepository, pula janela incompleta), em Tasks atômicas inside-out
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, prediction-persister, multi-horizon, target-timestamp, trading-day-indexing, off-by-one, quantile-forecast, dense-grid, monotonic-guardrail, long-format, analytics-store, gap-6, fake-port]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 4.3-prediction-persister
stage_title: Persister de predições multi-horizonte
step_id: 4
step_title: Analytics store (silver)
depends_on: [4.1-silver-schema-per-table, 4.2-silver-repository, 2.4-trading-calendar]
concept_ref: ./concept.md
issue_id: 38
branch: feat/38-4-3-prediction-persister
tasks_count: 5
---

# Technical — Stage 4.3 — Persister de predições multi-horizonte

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [4.3/task-NN]`, body em bullets,
>    rodapé `Refs #38`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar `[decision]`/`[deviation]`/`[finding]` em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done). Decisões fora de
>    questão já fechada: decidir sozinho (modo autônomo overnight,
>    ADR 0.0.0050) — sem perguntas.
> 7. **NÃO** fazer o commit `stage 4.3: complete` nem marcar a Stage `done`
>    no `roadmap.md` — isso é do ORQUESTRADOR após auditoria independente.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/38-4-3-prediction-persister`. Push/PR/merge são do orquestrador.

## 1. Contexto e estratégia de execução

### Resumo

Entregar o **dono único e puro** da convenção temporal de predições do BC
`analytics_store`, fechando na origem o Gap 6 / bug E4 do projeto antigo (TFT
usava `decoder_end_day` e baseline usava `decision_day`; ambos somavam
`pd.Timedelta(days=h)` de **calendário** numa grade de **pregão**). Cria-se: (a)
o **domain service `MultiHorizonPredictionPersister`** (stdlib-only) que
materializa `timestamp_utc = dataset_timestamps[decision_idx]` e
`target_timestamp_utc = dataset_timestamps[decision_idx + horizon]`
**indexado por dia de pregão** (índice do array de sessões, nunca timedelta),
levantando `IncompletePredictionWindowError` na borda; (b) o **VO
`QuantileForecast`** (stdlib-only) que carrega a **grade densa** de níveis +
`raw_values` e aplica o **guardrail de monotonicidade generalizado**
(`enforce_monotonic_triplet` do old estendido para a grade densa — `sorted` ao
longo dos níveis, marca `guardrail_applied`, preserva valores não-finitos com
`applied = False`); (c) o **use case `PersistPredictions`** (DTO frozen in/out)
que combina persister + guardrail, mapeia cada `(decision, h, nível)` para um
`PredictionRow` (4.1) no **formato LONG** com `value_raw` **e**
`value_guardrail` na **mesma** linha, preenche as colunas que o schema
`fact_oos_predictions` exige mas o VO não carrega (`schema_version`,
`model_version`, `asset`, `feature_set_name`, `year`), grava via
`AnalyticsRepository.write(layer="silver", table="fact_oos_predictions", …,
allow_upsert=False)` e **pula** (skip + `rows_skipped`) janelas incompletas sem
fabricar `y_true`.

### Estratégia

**Vertical slice domain → application, inside-out** (skill `task-ordering-hex`,
ordem default itens 1–2). Esta Stage **não** introduz novo port, **não** cria
adapter real e **não** toca o composition root:

- O **port-out `AnalyticsRepository`** e seu **`FakeAnalyticsRepository`
  in-memory** já existem da 4.2 — o use case é testado contra o **fake
  existente** (nunca mock; ADR `0_0_0021`), sem reentrar no ciclo de adapter.
- O **`PredictionRow`** e o schema `fact_oos_predictions` (PK lógica, partição,
  dtypes) já existem da 4.1 — esta Stage só os **consome**.
- Os dois **ADRs** (`4_3_0001`, `4_3_0002`) já existem `accepted` (escritos na
  Fase conceitual) — não há Task de ADR; a Task de fechamento (§3) é do
  orquestrador.

Ordem das Tasks e razão (cada Task deixa o build verde):

1. **Domain — persister** (`domain/services/…` + teste de alinhamento
   temporal). É o **coração do rewrite**; nasce isolado e provado primeiro
   (h=1/h=7 separados por exatamente h sessões + sex→seg com diff de calendário
   ≠ h + bordas). Não depende de nada novo (task-01).
2. **Domain — `QuantileForecast`** (`domain/value_objects/…` + teste de
   invariantes/guardrail). Independente do persister; grade densa + reordenação
   + postura defensiva não-finito (task-02).
3. **Application — `PersistPredictions`** (DTOs + use case + teste contra o
   `FakeAnalyticsRepository`). Consome persister (task-01), `QuantileForecast`
   (task-02), `PredictionRow`/schema (4.1) e o port (4.2). Testa LONG raw+
   guardrail na mesma linha, PK única, preenchimento de colunas de schema
   (`year` do decision_day, inclusive cruzando fronteira de ano), skip de janela
   incompleta e propagação de `DuplicateKeyError` (task-03).

As task-01 e task-02 são domain puro e mutuamente independentes; poderiam trocar
de ordem, mas o persister vem primeiro por ser o alvo de risco. A task-03 só pode
vir depois de 01 e 02. As Tasks 04 e 05 são de pacote/saneamento (`__init__` e
gate final do BC) e fecham a slice.

### Pré-condições

- Stage `4.1-silver-schema-per-table` em `done`: `PredictionRow`
  (`domain/value_objects/prediction_row.py`) e o schema/`SilverTable`
  `fact_oos_predictions` (`adapters/out/parquet/schemas/`) presentes —
  verificado: PK lógica `(run_id, split, horizon, timestamp_utc,
  target_timestamp_utc, quantile_level)`, partição `(asset, feature_set_name,
  year)`, colunas exigidas `nullable=False` `schema_version:int64`,
  `model_version:str`, `asset:str`, `feature_set_name:str`, `year:int64`.
- Stage `4.2-silver-repository` em `done`: port-out `AnalyticsRepository`
  (`application/ports/out/analytics_repository.py`),
  `FakeAnalyticsRepository` (`tests/fakes/features/analytics_store/…`) com a
  MESMA semântica observável (append-only, `DuplicateKeyError` sem
  `allow_upsert`, partição por payload), e `DuplicateKeyError`/`ApplicationError`
  (`shared/domain/exceptions/base.py`).
- Stage `1.5` em `done`: `Clock`/`FakeClock` — necessário **apenas** para
  instanciar o `FakeAnalyticsRepository` nos testes da application (o use case em
  si não usa `Clock`; `fact_oos_predictions` não tem `created_at_utc`).
- Stage `2.4-trading-calendar` em `done`: garantia **conceitual** de que
  `dataset_timestamps` é grade de pregão (não é import do persister — D2).
- ADRs `4_3_0001` e `4_3_0002` já em `docs/adr/` com `status: accepted`.

### Premissas técnicas

- Python 3.12, `uv`, mypy `--strict`, ruff, pytest.
- `dataset_timestamps` chega **já resolvido em grade de pregão** (sem
  feriados/fins de semana), em **string ISO UTC** — o domínio trafega `str`,
  **não** parseia `datetime` nem importa `pandas` (D3).
- `MultiHorizonPredictionPersister` e `QuantileForecast` importam **só stdlib**
  (`dataclasses`, `math`, `collections.abc`). Gate domain-purity (import-linter)
  + `scripts/check_layout.py` reprovam vazamento.
- O `FakeAnalyticsRepository` exige um `Clock`; nos testes usar `FakeClock`
  determinístico só para satisfazer o construtor — `fact_oos_predictions` não
  consome `created_at_utc`.
- O use case recebe o port por **injeção** (parâmetro do `__init__`/`__call__`);
  não há wiring de composition root nesta Stage (concept §1 "fora do escopo").

### Estrutura de pastas afetada

```
src/financial_forecasting/features/analytics_store/
├── domain/
│   ├── services/
│   │   ├── __init__.py                              # task-04
│   │   └── multi_horizon_prediction_persister.py   # task-01
│   └── value_objects/
│       └── quantile_forecast.py                    # task-02
└── application/
    └── use_cases/
        ├── __init__.py                             # task-04
        └── persist_predictions.py                  # task-03
tests/unit/features/analytics_store/
├── test_prediction_persister_target_timestamp.py   # task-01
├── test_quantile_forecast_invariants.py            # task-02
└── application/
    ├── __init__.py                                 # task-03
    └── test_persist_predictions.py                 # task-03
```

## 2. Tasks

> Faixa saudável: **3–8 Tasks por Stage**. ≥ 10 = Stage provavelmente
> está grande demais; reabrir Fase 3A para dividir.

### Task 01 — Domain service `MultiHorizonPredictionPersister` (alinhamento temporal)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/domain/services/multi_horizon_prediction_persister.py`
  - `tests/unit/features/analytics_store/test_prediction_persister_target_timestamp.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o domain service **puro** (stdlib-only) dono único da convenção
  temporal. Definir `IncompletePredictionWindowError(ValueError)`, o VO frozen
  `PredictionWindow(decision_idx:int, timestamp_utc:str,
  target_timestamp_utc:str)` e `MultiHorizonPredictionPersister.build(*,
  decision_idx, horizon, dataset_timestamps: Sequence[str]) -> PredictionWindow`.
  `build` valida (`horizon >= 1`, `decision_idx >= 0` → `ValueError`), computa
  `target_pos = decision_idx + horizon`, levanta `IncompletePredictionWindowError`
  se `target_pos >= len` ou `decision_idx >= len`, e devolve
  `PredictionWindow(decision_idx, timestamp_utc=dataset_timestamps[decision_idx],
  target_timestamp_utc=dataset_timestamps[target_pos])`. Indexar o array
  diretamente (D2); **proibido** `pd.Timestamp`/`pd.Timedelta`/parsing de
  `datetime`. Docstring referencia ADR `4_3_0001` (R-20 opção d) e o backward
  `target_return` (y_true fornecido pelo caller — esta Stage não calcula).
- **Detalhes técnicos:**
  - I1: `timestamp_utc = dataset_timestamps[decision_idx]` (NUNCA `decoder_end`).
  - I2: `target_timestamp_utc = dataset_timestamps[decision_idx + horizon]`
    indexado por sessão (índice do array).
  - I4/C1/C2: ordem das validações — argumentos inválidos (`ValueError`) antes da
    borda; borda → `IncompletePredictionWindowError`.
  - I8/D3: importa só `dataclasses` + `collections.abc.Sequence`; timestamps `str`.
  - Testes obrigatórios (coração do rewrite — **provar verbatim**):
    (a) h=1: `decision_idx=k` → `target_timestamp == dataset_timestamps[k+1]`
    e `timestamp == dataset_timestamps[k]`;
    (b) h=7: idem com `k+7`, separados por **exatamente 7 posições** no array;
    (c) **sex→seg**: dataset de pregão com sexta seguida de segunda; h=1 numa
    sexta → diff de **calendário** entre `timestamp_utc` e
    `target_timestamp_utc` == 3 dias (prova indexação por sessão, não calendário);
    (d) borda: `decision_idx + horizon >= len` e `decision_idx >= len` →
    `IncompletePredictionWindowError`; `horizon=0`/`-1` e `decision_idx=-1` →
    `ValueError`.
- **Critério de aceite:**
  - `test_prediction_persister_target_timestamp.py` cobre (a)–(d) acima; A1, A2,
    A3 verdes; nenhum import de `pandas`/`datetime` no módulo de domínio.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/analytics_store/test_prediction_persister_target_timestamp.py -v
  mypy --strict src/financial_forecasting/features/analytics_store/domain/services/multi_horizon_prediction_persister.py
  python scripts/check_layout.py
  grep -nE "import pandas|from pandas|pd\.|import datetime|from datetime" src/financial_forecasting/features/analytics_store/domain/services/multi_horizon_prediction_persister.py && echo "LEAK" || echo "clean"
  ```
- **Commit sugerido:** `feat(analytics-store): persister multi-horizonte dono do target_timestamp [4.3/task-01]`

---

### Task 02 — VO `QuantileForecast` (grade densa + guardrail monotônico)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/domain/value_objects/quantile_forecast.py`
  - `tests/unit/features/analytics_store/test_quantile_forecast_invariants.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o VO frozen **puro** (stdlib-only) `QuantileForecast(levels:
  tuple[float, ...], raw_values: tuple[float, ...], guardrail_values:
  tuple[float, ...], guardrail_applied: bool)` com construtor
  `from_raw(*, levels, raw_values) -> QuantileForecast`. `from_raw` valida
  `len(levels) == len(raw_values)`, `levels` **estritamente crescentes e únicos**
  (senão `ValueError` — C3), e aplica o guardrail de monotonicidade
  generalizado: se **todos** os `raw_values` forem finitos, ordena-os com
  `sorted` (não-decrescente ao longo dos níveis) e marca `guardrail_applied =
  (ordem mudou)`; se algum valor for não-finito/`None`, **preserva** os
  `raw_values` em `guardrail_values` e marca `guardrail_applied = False`
  (postura defensiva do old — C4). Generaliza `enforce_monotonic_triplet`
  (p10/p50/p90 do old) para grade densa ~7-9 (D4, ADR `4_3_0002`).
- **Detalhes técnicos:**
  - I5: guardrail garante quantis não-decrescentes ao longo dos níveis;
    reordena via `sorted`; marca `applied` quando a ordem mudou. **SEPARADO** do
    gate de degeneração `q_low == q_high` (Step 6 — NÃO implementar aqui).
  - C3: `levels` não-monotônico/duplicado ou tamanhos divergentes → `ValueError`
    na construção.
  - C4: usar `math.isfinite`; `None` ou não-finito → preserva, `applied = False`.
    Equivalência com o caso base triplet (p10/p50/p90) deve ser testada.
  - I8/D3: importa só `dataclasses` + `math` (e `collections.abc` se preciso);
    valores `float`, sem pandas/numpy.
  - Testes obrigatórios:
    (a) grade desordenada → `guardrail_values` reordenado (`sorted`),
    `guardrail_applied = True`, `raw_values` intactos;
    (b) grade já-monotônica → `guardrail_values == raw_values`, `applied = False`;
    (c) não-finito (`inf`/`nan`)/`None` → valores preservados, `applied = False`;
    (d) caso base triplet p10/p50/p90 reproduz o `enforce_monotonic_triplet` old;
    (e) construção inválida (`len` divergente, níveis não-crescentes/duplicados)
    → `ValueError`.
- **Critério de aceite:**
  - `test_quantile_forecast_invariants.py` cobre (a)–(e); A4 verde; nenhum import
    de `pandas`/`numpy` no módulo.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/analytics_store/test_quantile_forecast_invariants.py -v
  mypy --strict src/financial_forecasting/features/analytics_store/domain/value_objects/quantile_forecast.py
  python scripts/check_layout.py
  grep -nE "import pandas|import numpy|from pandas|from numpy" src/financial_forecasting/features/analytics_store/domain/value_objects/quantile_forecast.py && echo "LEAK" || echo "clean"
  ```
- **Commit sugerido:** `feat(analytics-store): VO QuantileForecast grade densa com guardrail monotônico [4.3/task-02]`

---

### Task 03 — Use case `PersistPredictions` (DTO + grava LONG via fake do port)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/application/use_cases/persist_predictions.py`
  - `tests/unit/features/analytics_store/application/__init__.py`
  - `tests/unit/features/analytics_store/application/test_persist_predictions.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar os DTOs **frozen** `PersistPredictionsCommand` (in) e
  `PersistPredictionsResult` (out: `rows_written:int`, `rows_skipped:int`) e o
  use case `PersistPredictions` que recebe o `AnalyticsRepository` (port-out, 4.2)
  por injeção no `__init__`. O `__call__(command) -> PersistPredictionsResult`:
  para cada `(decision_idx, horizon)` × cada nível da `QuantileForecast`
  associada, chama `MultiHorizonPredictionPersister.build` para obter
  `timestamp_utc`/`target_timestamp_utc`; **captura
  `IncompletePredictionWindowError`** → `continue` + `rows_skipped += 1` (não
  grava, não fabrica `y_true`); monta um `PredictionRow` por nível com
  `value_raw` = raw e `value_guardrail` = guardrail (mesma linha) +
  `guardrail_applied` 0/1; mapeia `PredictionRow` → `Row` (dict) preenchendo as
  colunas que o schema exige e o VO não carrega — `schema_version`,
  `model_version`, `asset`, `feature_set_name`, `year = ano do decision_day`
  (extraído de `timestamp_utc`, ex.: `int(timestamp_utc[:4])`) — e grava o batch
  via `repo.write(layer="silver", table="fact_oos_predictions", rows,
  allow_upsert=False)`. Devolve `rows_written`/`rows_skipped`.
- **Detalhes técnicos:**
  - I9: DTOs frozen in/out; depende do **Protocol** (port), não do adapter;
    testar com `FakeAnalyticsRepository` (fake, não mock).
  - I6/D6: uma linha LONG por nível, `value_raw` + `value_guardrail` +
    `guardrail_applied` na **mesma** linha; PK única por `(run_id, split,
    horizon, timestamp_utc, target_timestamp_utc, quantile_level)`.
  - I7/D5: `schema_version`/`model_version`/`asset`/`feature_set_name`/`year`
    preenchidos na fronteira (vêm do `command`/contexto de run); `year` derivado
    do **decision_day** (`timestamp_utc[:4]`), consistente cruzando fronteira de
    ano. `schema_version` é `int`; `quantile_level` é `float`; `guardrail_applied`
    é `int` (0/1); `horizon`/`decision_idx` são `int`.
  - C5: o use case **não** captura `DuplicateKeyError` — propaga (reprocessamento
    consciente é do caller).
  - Definir a forma do `command` para mapear `QuantileForecast` por `(decision,
    h)`: campos `run_id`, `split`, `model_version`, `asset`, `feature_set_name`,
    `schema_version`, `decision_idx`, `horizons`, `dataset_timestamps`, e a(s)
    `QuantileForecast` por horizonte (ex.: `forecasts: Mapping[int,
    QuantileForecast]` keyed por `horizon`). Tipos de DTO são primitivos/VO de
    domínio interno; a fronteira de saída devolve só o DTO `Result`.
  - Mapeamento `PredictionRow → Row`: pode usar `dataclasses.asdict` do
    `PredictionRow` + merge das colunas de schema, ou montagem explícita do dict
    — o dict final deve conter exatamente as 15 colunas do schema
    `fact_oos_predictions` (concept §4 / schema 4.1).
  - Testes obrigatórios (contra `FakeAnalyticsRepository` + `FakeClock`):
    (a) grava **N linhas LONG por (decision, h)** (uma por nível) com `value_raw`
    e `value_guardrail` na mesma linha; ler de volta confirma PK única por nível;
    (b) `year == int(timestamp_utc[:4])`, incluindo um caso cruzando fronteira de
    ano (decision em dez, target em jan → `year` do **decision**);
    (c) colunas de schema preenchidas (`schema_version`/`model_version`/`asset`/
    `feature_set_name`) batem com o `command`;
    (d) janela incompleta (`decision_idx + h` fora do range) → linha **pulada**,
    `rows_skipped` incrementado, `y_true` NÃO fabricado, demais linhas gravadas;
    (e) `guardrail_applied` chega 1 quando a grade foi reordenada, 0 caso
    contrário;
    (f) reprocessar mesma PK sem `allow_upsert` → `DuplicateKeyError` propagado.
- **Critério de aceite:**
  - `test_persist_predictions.py` cobre (a)–(f) usando o fake do port (não mock);
    A5, A6, A7 verdes.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/analytics_store/application/test_persist_predictions.py -v
  mypy --strict src/financial_forecasting/features/analytics_store/application/use_cases/persist_predictions.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(analytics-store): use case PersistPredictions grava grade LONG raw+guardrail [4.3/task-03]`

---

### Task 04 — Pacotes `__init__` de `domain/services` e `application/use_cases`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/domain/services/__init__.py`
  - `src/financial_forecasting/features/analytics_store/application/use_cases/__init__.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Garantir que os novos diretórios de pacote (`domain/services/`,
  `application/use_cases/`) tenham `__init__.py` (padrão dos demais pacotes do
  BC). Pode ser feito junto às Tasks 01/03 se a ferramenta exigir o pacote para
  import; se já criados ali, esta Task vira **no-op** e é absorvida (registrar
  `[deviation]` em §7). Mantida explícita para a slice ter os pacotes fechados.
- **Detalhes técnicos:**
  - `__init__.py` vazios (ou com docstring de 1 linha), sem reexports que
    induzam ciclo de import.
  - Rodar `scripts/regen_tree.py` se o projeto mantém árvore documentada.
- **Critério de aceite:**
  - Import dos módulos novos funciona via caminho de pacote; `check_layout.py`
    verde.
- **Comando de verificação:**
  ```bash
  python -c "import financial_forecasting.features.analytics_store.domain.services.multi_horizon_prediction_persister; import financial_forecasting.features.analytics_store.application.use_cases.persist_predictions"
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `chore(analytics-store): pacotes de services e use_cases do persister [4.3/task-04]`

---

### Task 05 — Gate verde do BC (lint + type + import-linter + cobertura ≥ 90%)

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:** apenas correções de lint/type/cobertura se o gate
  acusar (ex.: testes faltando para um ramo).
- **O que fazer:**
  Rodar o gate completo da Stage e fechar quaisquer lacunas: `make check` (ruff +
  mypy `--strict` + import-linter + `check_layout`), suíte do BC, e cobertura ≥
  90% do BC `analytics_store`. Confirmar **grep limpo** de `pandas`/`numpy` nos
  dois módulos de domínio (domain-purity) e que o domain-purity contract do
  import-linter cobre `domain/services/`. Esta Task é o **gate de saída**
  (§3) consolidado numa verificação; **não** inclui o commit `stage 4.3:
  complete` (orquestrador).
- **Detalhes técnicos:**
  - Se o import-linter não tiver contrato cobrindo `domain/services/` da
    `analytics_store`, registrar `[finding]`/`[decision]` em §7 e estender o
    contrato (espelhar `domain/value_objects/`); domain-purity é gate (I8).
  - Cobertura medida sobre os 3 módulos novos; ramos de erro (C1–C5) precisam de
    teste — adicionar se faltar (volta à Task da camada correspondente).
- **Critério de aceite:**
  - `make check` verde; `pytest tests/` verde; cobertura do BC ≥ 90%; grep de
    `pandas`/`numpy` nos módulos de domínio retorna vazio.
- **Comando de verificação:**
  ```bash
  make check
  pytest tests/unit/features/analytics_store/ tests/contract/features/analytics_store/ -v
  pytest --cov=financial_forecasting.features.analytics_store --cov-report=term-missing tests/
  grep -rnE "import pandas|import numpy|from pandas|from numpy" src/financial_forecasting/features/analytics_store/domain/ && echo "LEAK" || echo "clean"
  ```
- **Commit sugerido:** `test(analytics-store): fecha cobertura e gates do persister 4.3 [4.3/task-05]`
  (omitir o commit se a Task for no-op porque o gate já estava verde após a
  task-03/04 — registrar `[deviation]` em §7)

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 4.3: complete` (feito pelo ORQUESTRADOR após auditoria) e ser mergeada.

### Verificações automatizadas
```bash
make check                # lint + type + import-linter + check_layout + testes
pytest tests/             # todos os testes
pytest --cov=financial_forecasting.features.analytics_store --cov-report=term-missing tests/  # cobertura ≥ 90%
grep -rnE "import pandas|import numpy" src/financial_forecasting/features/analytics_store/domain/  # vazio (domain-purity)
```

### Verificações funcionais
- [ ] `MultiHorizonPredictionPersister.build` devolve `timestamp_utc =
      dataset_timestamps[decision_idx]` e `target_timestamp_utc =
      dataset_timestamps[decision_idx + h]` para h=1 e h=7 (separados por
      exatamente h posições) e prova sex→seg (diff calendário ≠ h).
- [ ] `PersistPredictions` grava N linhas LONG por `(decision, h)` (uma por
      nível) com `value_raw` + `value_guardrail` na mesma linha e PK única, lendo
      de volta pelo `FakeAnalyticsRepository`.
- [ ] Janela incompleta → linha pulada e `rows_skipped` incrementado, sem
      fabricar `y_true`.

### Tabela invariante ↔ teste (mapping de saída)

| Invariante (concept §5/§6) | Critério (concept §11) | Task | Teste |
|---|---|---|---|
| I1 — âncora `timestamp_utc = decision_day` | A1 | 01 | `test_prediction_persister_target_timestamp.py` (h=1/h=7) |
| I2 — indexação por dia de pregão (não timedelta) | A1, A2 | 01 | idem + caso sex→seg (diff calendário ≠ h) |
| I3 — zero off-by-one (y_true backward, caller) | A1 | 01 | h=1 e h=7 separados por exatamente h posições |
| I4/C1/C2 — borda + args inválidos | A3 | 01 | `IncompletePredictionWindowError` / `ValueError` |
| I5/C3/C4 — guardrail monotônico + defensivo | A4 | 02 | `test_quantile_forecast_invariants.py` |
| I6/D6 — LONG raw+guardrail na mesma linha, PK única | A5 | 03 | `test_persist_predictions.py` (a) |
| I7/D5 — colunas de schema na fronteira, `year` decision-day | A6 | 03 | `test_persist_predictions.py` (b)(c) + fronteira de ano |
| I4/I9/C1 — skip de janela incompleta via fake | A7 | 03 | `test_persist_predictions.py` (d) |
| C5 — `DuplicateKeyError` propagado | A5 | 03 | `test_persist_predictions.py` (f) |
| I8 — domínio puro (stdlib-only) | A8 | 01,02,05 | grep limpo + import-linter + `check_layout` |
| I9 — application por DTO + fake do port | A7 | 03 | use case testado contra `FakeAnalyticsRepository` |
| ADRs `accepted` | A9 | — | `4_3_0001`, `4_3_0002` (já `accepted`) |

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura do BC `analytics_store` ≥ 90%
- [ ] ADRs `4_3_0001` e `4_3_0002` em `status: accepted` (já estão)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
- [ ] **(orquestrador)** Commit final `stage 4.3: complete` + `roadmap.md`
      Stage `done` — **NÃO** feito por esta sessão

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências. task-01 e task-02 são domain
puro e mutuamente independentes (persister primeiro por ser o alvo de risco).
task-03 (application) depende de **ambas**. task-04 fecha os pacotes (pode ser
absorvida em 01/03). task-05 é o gate consolidado, ao fim.

```
task-01 (persister) ─┐
task-02 (forecast) ──┴─► task-03 (use case + fake) ─► task-04 (__init__) ─► task-05 (gate)
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Off-by-one volta (coração do rewrite) | Testes verbatim h=1/h=7 + sex→seg na task-01 antes de qualquer wiring; convenção num único arquivo (I1–I3). |
| Pandas/numpy vazar para o domínio (como no old) | Gate domain-purity + import-linter + `check_layout`; grep nos comandos de verificação das tasks 01/02/05; timestamps `str` (D3). |
| Import-linter não cobre `domain/services/` da `analytics_store` | Estender o contrato espelhando `domain/value_objects/` (registrar `[decision]` em §7); domain-purity é gate. |
| Confundir guardrail monotônico com gate de degeneração (`q_low==q_high`) | I5 + non_goals: guardrail só reordena (`sorted`); degeneração é Step 6 — não implementar. |
| `year` inconsistente cruzando fronteira de ano | `year = int(timestamp_utc[:4])` (decision-day) + teste explícito dez→jan (task-03 (b)). |
| Cobertura < 90% por ramo de erro não testado | task-05 reabre a Task da camada e adiciona o teste do ramo (C1–C5). |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (§4 contratos, §5
  invariantes, §11 critérios)
- [`../../overview.md`](../../overview.md) — §11 ADRs `0_0_0011`/`0_0_0012`
- [`../../roadmap.md`](../../roadmap.md) — Stage `4.3-prediction-persister`, Step 4
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — H-1, §B 4.3
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs desta Stage:
  [`../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md`](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md),
  [`../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md`](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md)
- Skills aplicáveis: `ddd-tactical-patterns`, `hex-arch-python`,
  `pytest-with-fakes`, `task-ordering-hex`
- Old repo: `src/domain/services/multi_horizon_prediction_persister.py`,
  `src/domain/services/quantile_guardrail_service.py`,
  `docs/01_architecture/decisions/ADR-0003-multi-horizon-prediction-persister.md`

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
> **Modo autônomo overnight (ADR 0.0.0050):** decisões fora de questão já
> fechada são tomadas pela sessão **sem perguntar**; registrar aqui como
> `[decision]`/`[deviation]`/`[finding]`.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Decisão:** <o que foi decidido>
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-06-29 — [deviation] task-04 absorvida em task-01/task-03 — Claude (overnight)
**Contexto:** os `__init__.py` de `domain/services/` e `application/use_cases/`
eram pré-condição de import dos módulos das task-01/task-03; criá-los só na task-04
deixaria os commits anteriores sem build verde.
**Decisão:** criei `domain/services/__init__.py` junto da task-01 (commit task-01) e
`application/use_cases/__init__.py` junto da task-03 (commit task-03). A task-04
virou no-op e não recebeu commit próprio.
**Razão:** o technical §2 task-04 já previa essa absorção ("Pode ser feito junto às
Tasks 01/03 se a ferramenta exigir o pacote para import; se já criados ali, esta Task
vira no-op"). Mantém cada commit anterior verde e a slice com os pacotes fechados.

### 2026-06-29 — [finding] import-linter já cobre `analytics_store.domain/application` — Claude (overnight)
**Contexto:** o technical §2 task-05 e o risco em §5 previam estender o contrato
import-linter caso `domain/services/` da `analytics_store` não estivesse coberto.
**Decisão:** nenhuma extensão necessária. Os contratos `domain-purity` e
`store-no-storage-leak` (`.importlinter`) já listam
`financial_forecasting.features.analytics_store.domain` e `.application` como
`source_modules` desde a Stage 4.1 — e `forbidden` cobre `source_modules` recursivamente,
então `domain/services/` e `application/use_cases/` herdam a proteção. `lint-imports`
fecha verde com 8/8 contratos KEPT; grep de `pandas`/`numpy` nos dois módulos de domínio
retorna vazio.
**Razão:** registro para fechar o item de risco como verificado (não houve gap).

### 2026-06-29 — [decision] horizonte incompleto pula a grade inteira do horizonte — Claude (overnight)
**Contexto:** o concept/technical descrevem o skip de "linha" em janela incompleta,
mas a unidade real de skip precisava ser definida (uma `QuantileForecast` por
`(decision, horizon)` expande para N níveis/linhas LONG).
**Decisão:** em `IncompletePredictionWindowError`, o use case pula **todos os níveis
daquele horizonte** (a janela temporal é a mesma para todos os níveis de um horizonte)
e incrementa `rows_skipped` por **nível** (`len(forecast.levels)`), refletindo quantas
linhas LONG deixaram de ser gravadas. Verificado por teste: h=1 válido grava 3 linhas,
h=2 incompleto pula 3.
**Razão:** o alinhamento temporal depende só de `(decision_idx, horizon)`, não do
nível; logo a borda é por horizonte. Contar por linha (nível) mantém `rows_skipped`
comparável a `rows_written` (ambos em linhas LONG), sem fabricar `y_true`.

<!-- END: post-execution -->