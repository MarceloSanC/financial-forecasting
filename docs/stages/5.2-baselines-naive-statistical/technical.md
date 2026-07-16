---
title: Technical — Stage 5.2 — Baselines naive e estatísticos (5 specs, grade densa de quantis)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), TDD inside-out no BC modeling (1ª fatia vertical — domain + application + adapters/out)
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, baselines-naive-statistical, modeling, quantile-emission, zero-return, historical-mean, ar1, ewma, historical-quantiles, statsforecast, run-baselines, medallion-store, importlinter]
status: done
created_at: 2026-07-15
updated_at: 2026-07-16
stage_id: 5.2-baselines-naive-statistical
stage_title: Baselines naive e estatísticos
step_id: 5
step_title: Modelagem, baselines e treino
depends_on: [5.1-walk-forward-harness]
concept_ref: ./concept.md
issue_id: 51
branch: feat/51-5-2-baselines-naive-statistical
tasks_count: 10
---

# Technical — Stage 5.2 — Baselines naive e estatísticos

> **Como usar (para code assistant):** ler §1, executar Tasks em ordem (§2),
> 1 Task = 1 commit, não avançar sem verificação verde; ao fim validar §3 e
> registrar §7. Commits seguem [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(<scope>): <descrição> [5.2/task-NN]`, escopo `modeling` (ou `store`
> para a Task 04, `roadmap` para a Task 10), `Refs #51`.
>
> Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
> perguntar ao humano com opções e recomendação, e registrar em §7. Nunca
> propagar silenciosamente.

## 1. Contexto e estratégia de execução

### Resumo

Primeira **fatia vertical** do BC `modeling`: o VO `BaselineSpec` (5 famílias
canônicas pré-registradas), os serviços de domínio puros de emissão/estatística
(grade degenerada, conversão gaussiana via `statistics.NormalDist`, quantil
tipo 7, recursão EWMA, formas fechadas h-step do AR(1)) validados contra
**oráculos** (ADR 0.0.0021), o port-out `BaselineForecaster` com fake +
contract test único, o use case `RunBaselines` (orquestra splitter 5.1 →
forecaster → guardrail 4.3 → dedup com remoção-zero assertada → persistência
4.3 + `dim_run` 4.2), o adapter `StatsforecastBaselineForecaster`
(`statsforecast` confinado ao fit do AR(1) — ADR 5.2.0001), o par read-only
`("processed", "dataset_tft")` no `MedallionStore`, dois contratos de fitness
no `.importlinter` e o retoque do roadmap ("6 baselines" → 5 specs).

Todas as decisões de projeto vêm do concept **por referência** — nenhuma é
re-derivada aqui: D1 (matemática no domínio; statsforecast só no fit AR(1) —
[ADR 5.2.0001](../../adr/5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md)),
D2 (estimação congelada no train; estado causal até a decisão —
[ADR 5.2.0002](../../adr/5_2_0002-frozen-train-estimation-causal-state.md)),
D3 (leitura via `MedallionStore`, par read-only), D4 (`historical_mean` no
train expansivo; semente EWMA σ̂²₁ = r₁²), D5 (`split="test"`; `run_id` por
spec × fold), D6 (W = 252 —
[ADR 5.2.0003](../../adr/5_2_0003-historical-quantiles-window-252.md)).
Fórmulas: doc de domínio
[`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
§3; convenções de emissão: ADR 0.0.0052.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`): domínio puro primeiro (VO +
serviços de emissão/estatística, cada um com teste analítico + oráculo no
mesmo commit), depois a fronteira de dados (par read-only do store — pré-
requisito do use case), depois port + fake + suite de contrato, depois o use
case com fakes, depois o adapter real (statsforecast + oráculo + registro na
mesma suite de contrato), depois as fitness functions (provadas por quebra
intencional revertida), por fim wiring no composition root + teste de
integração ponta-a-ponta e o retoque do roadmap.

**Exceções de ordem/contagem declaradas (PIPELINE §4.3):**

- **Task 04 toca `shared/adapters` (fora do BC `modeling`)** — é a extensão
  read-only do `MedallionStore` decidida no concept D3 (contrato consumido),
  análoga à exceção da Task 02 da 5.1. Intencional e mínima; vem antes do use
  case porque o fake do store precisa suportar o par para os testes da Task 06.
- **Tasks 05 e 07 excedem 5 arquivos** — o excedente é boilerplate mecânico
  (`__init__.py` de pacotes novos src+tests; `uv.lock` regenerado). Precedente
  da Task 01 da 5.1.
- **Port (Task 05) e adapter real (Task 07) em Tasks separadas** — regra dura
  do §4.3 respeitada; entre elas a Task 06 testa o use case só com fakes
  (skill `pytest-with-fakes`).

### Pré-condições

- Stages `5.1`, `4.1`–`4.3`, `3.5`, `2.1`, `1.4` em `done` e mergeadas em
  `develop`.
- Working tree na branch `feat/51-5-2-baselines-naive-statistical`.
- Concept desta Stage em `done`; ADRs 5.2.0001–0003 em `accepted`.
- Dataset TFT real existente em `data/processed/dataset_tft/AAPL/` (para uso
  manual; os testes usam fixtures sintéticas em `tmp_path`).

### Premissas técnicas

- Python 3.12; `uv`; `make check` = ruff + mypy strict + `lint-imports` +
  `check_layout` + `docs-check` + pytest com cobertura ≥ 90%.
- `statistics.NormalDist().inv_cdf` (stdlib, AS241) fornece z_τ — sem
  numpy/scipy no domínio; numpy/pandas podem ser usados **nos testes** como
  oráculo (ADR 0.0.0021 — a duplicação É a verificação).
- `Row` do `MedallionStore` devolve `timestamp` como objeto datetime
  (tz-aware UTC); a application o trata pela API de `datetime` (`.date()`,
  `.isoformat()`) sem importar pandas.
- `FoldSplit.train/test` carregam datas ISO (`date.isoformat()`, `YYYY-MM-DD`);
  o `RunBaselines` mapeia ISO → índice na grade densa do dataset.
- `mypy` global usa `ignore_missing_imports = True` — `statsforecast` sem
  stubs não quebra o strict; a fronteira do wrapper é tipada com
  `float`/tuplas.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── shared/adapters/out/parquet/parquet_medallion_store.py   # MODIFICADO (par read-only)
├── composition_root.py                                       # MODIFICADO (wiring RunBaselines)
└── features/modeling/
    ├── domain/
    │   ├── value_objects/baseline_spec.py                    # NOVO
    │   └── services/
    │       ├── quantile_grid_emission.py                     # NOVO
    │       └── baseline_statistics.py                        # NOVO
    ├── application/
    │   ├── ports/{__init__.py, out/__init__.py}              # NOVO (pacotes)
    │   ├── ports/out/baseline_forecaster.py                  # NOVO
    │   └── use_cases/{__init__.py, run_baselines.py}         # NOVO
    └── adapters/out/statsforecast/
        └── {__init__.py, statsforecast_baseline_forecaster.py}  # NOVO
tests/
├── unit/features/modeling/
│   ├── domain/value_objects/test_baseline_spec.py            # NOVO
│   ├── domain/services/{test_quantile_grid_emission.py, test_baseline_statistics.py}  # NOVO
│   └── application/{__init__.py, test_run_baselines.py}      # NOVO
├── fakes/features/modeling/{__init__.py, in_memory_baseline_forecaster.py}  # NOVO
├── contract/features/modeling/{__init__.py, test_baseline_forecaster_contract.py}  # NOVO
├── contract/shared/test_medallion_store_contract.py          # MODIFICADO (par processed)
├── fakes/shared/in_memory_medallion_store.py                 # MODIFICADO (par processed)
├── integration/features/modeling/{__init__.py, test_statsforecast_baseline_forecaster.py, test_run_baselines.py}  # NOVO
├── unit/shared/test_composition_root.py                      # MODIFICADO (run_baselines)
└── architecture/test_import_contracts.py                     # MODIFICADO (novo contrato)
.importlinter                                                  # MODIFICADO (2 contratos)
pyproject.toml / uv.lock                                       # MODIFICADO (statsforecast)
docs/roadmap.md                                                # MODIFICADO (Task 10)
```

### Rastreabilidade — concept §11 → Tasks

| # | Critério de aceitação (concept §11) | Tasks | Check objetivo |
|---|---|---|---|
| A1 | `canonical_five()` = 5 specs pré-registradas; spec inválida ergue (C3) | 01 | `pytest tests/unit/features/modeling/domain/value_objects/test_baseline_spec.py` |
| A2 | `zero_return`/`historical_mean` emitem grade degenerada que atravessa o guardrail com `guardrail_applied=False` (I5) | 02, 09 | `pytest .../test_quantile_grid_emission.py` (degenerada × `QuantileForecast.from_raw`) + asserção no e2e (`guardrail_applied == 0` nas linhas persistidas) |
| A3 | `ar1`/`ewma_vol`/`historical_quantiles` emitem as fórmulas §3 validadas contra oráculo/fixture com tolerância declarada | 02, 03, 07 | `pytest .../test_quantile_grid_emission.py .../test_baseline_statistics.py tests/integration/features/modeling/test_statsforecast_baseline_forecaster.py` |
| A4 | Causalidade por truncamento (I3); parâmetros insensíveis fora do train (I4) | 05, 07 | `pytest tests/contract/features/modeling/test_baseline_forecaster_contract.py` (fake na 05; fake+real na 07) |
| A5 | Predições alinhadas por `target_timestamp` (I2), persistidas com `model_version='baseline_*'`, `run_id` em `dim_run` (I10) | 06, 09 | `pytest tests/unit/features/modeling/application/test_run_baselines.py` + `pytest tests/integration/features/modeling/test_run_baselines.py` |
| A5-pré | Pré-requisito de A5 e dos units da Task 06: par read-only `("processed", "dataset_tft")` no `MedallionStore` (fake + real), write no par ergue (concept D3) | 04 | `pytest tests/contract/shared/test_medallion_store_contract.py` |
| A6 | Remoção-zero do dedup: folds sobrepostos sintéticos → `RunBaselines` ergue (I6) | 06 | dois casos em `test_run_baselines.py`: splitter stub com blocos test sobrepostos → `ValueError` C9 do serviço 5.1 ("ambiguous operationally-latest…"); unit direto do helper `_assert_zero_removal` (defesa-em-profundidade I6) |
| A7 | Contract test único do `BaselineForecaster` (fake + real) cobrindo I3/I4/C5 | 05, 07 | `pytest tests/contract/features/modeling/test_baseline_forecaster_contract.py -v` verde nos ids `fake` e `real` |
| A8 | C1–C5 erguem; C6 pula e conta | 01 (C3), 05/07 (C1/C4/C5), 06 (C2/C6/C7) | casos nomeados nas suites das Tasks citadas |
| A9 | `modeling.{application,domain}` verdes em `store-no-storage-leak` **e** `modeling-no-statsforecast-leak`; quebra intencional revertida; domain stdlib-only (I8) | 08 | `uv run lint-imports` + `pytest tests/architecture/` + prova registrada em §7 |
| A10 | Roadmap: "6 baselines" → 5 specs (DoDs 5.2 e 5.5) + descrição humana da 5.2 retocada | 10 | `grep -n "6 baselines" docs/roadmap.md` vazio; diff das 3 linhas |
| A11 | `make check` verde; coverage ≥ 90%; unit + integration | todas; gate §3 | `make check` |

## 2. Tasks

> Faixa alvo desta Stage: 10 Tasks (estimativa do concept §12: 8, com o
> port+fake+use case desdobrado em duas — regra dura port≠adapter e commit ≤ 5
> arquivos — e o roadmap como Task docs própria, escopo de commit distinto).

### Task 01 — VO `BaselineSpec` (5 famílias canônicas)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/value_objects/baseline_spec.py`
  - `tests/unit/features/modeling/domain/value_objects/test_baseline_spec.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar o VO frozen stdlib-only com a assinatura do concept
  §4: constante `BASELINE_FAMILIES: Final = ("zero_return",
  "historical_mean", "ar1", "ewma_vol", "historical_quantiles")` (ordem do doc
  de domínio §3.8), `@dataclass(frozen=True)` com `family: str`,
  `window: int | None = None`, `decay_lambda: float | None = None`; property
  `model_version -> str` (`f"baseline_{family}"`); fábrica estática
  `canonical_five(*, historical_quantiles_window: int = 252)` (ADR 5.2.0003 —
  o parâmetro existe só para testes/sensibilidade).
- **Detalhes técnicos:**
  - `__post_init__` valida (C3, `ValueError`): família ∈ `BASELINE_FAMILIES`;
    `ewma_vol` exige `decay_lambda ∈ (0, 1)` e proíbe `window`;
    `historical_quantiles` exige `window >= 20` e proíbe `decay_lambda`; as
    demais famílias proíbem ambos.
  - `canonical_five()` devolve `ewma_vol` com `decay_lambda=0.94` e
    `historical_quantiles` com `window=252` (defaults pré-registrados — ADRs
    0.0.0052 / 5.2.0003).
- **Critério de aceite:** testes cobrem: construção válida de cada família;
  frozen (`FrozenInstanceError`); cada ramo de C3 (família desconhecida,
  parâmetro obrigatório ausente, parâmetro proibido presente, `window < 20`,
  `decay_lambda` fora de (0,1)); `canonical_five()` = exatamente 5 specs, na
  ordem canônica, com `model_version` = `baseline_zero_return` …
  `baseline_historical_quantiles` (A1).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/value_objects/test_baseline_spec.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/value_objects/baseline_spec.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(modeling): VO BaselineSpec com as 5 specs canônicas pré-registradas [5.2/task-01]`

---

### Task 02 — Serviços de domínio de emissão da grade (`quantile_grid_emission`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/services/quantile_grid_emission.py`
  - `tests/unit/features/modeling/domain/services/test_quantile_grid_emission.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** três funções puras stdlib-only (assinaturas do concept §4;
  fórmulas por referência ao doc de domínio §3 — não re-derivar):
  `degenerate_grid(*, value, levels)` (§3.4 — `value` repetido em todo nível);
  `gaussian_grid(*, mean, std, levels)` (§3.5/§3.6 — `mean + std *
  NormalDist().inv_cdf(tau)`, QRM Eq. (2.19)); `sample_quantiles_type7(*,
  values, levels)` (§3.7 — Hyndman & Fan tipo 7, `h = (n-1)p + 1`,
  interpolação linear).
- **Detalhes técnicos:**
  - Validações defensivas (`ValueError`): `levels` não-vazio, estritamente
    crescente, único, em (0,1); `std > 0` no `gaussian_grid`; `values`
    não-vazio no tipo 7; entradas não-finitas (NaN/Inf) erguem (alimenta C5 —
    um baseline determinístico nunca emite não-finito).
  - Saída sempre `tuple[float, ...]` alinhada 1:1 a `levels`.
- **Critério de aceite (oráculos com tolerância declarada — ADR 0.0.0021):**
  - `gaussian_grid`: fixture de z_τ tabulados (ex.: Φ⁻¹(0.95) =
    1.6448536269…, Φ⁻¹(0.5) = 0) com tolerância declarada (ex.: 1e-9).
  - `sample_quantiles_type7`: paridade com `numpy.quantile(...,
    method="linear")` (oráculo no teste) em fixtures determinísticas,
    incluindo níveis extremos da grade; tolerância declarada.
  - `degenerate_grid`: constante em todo nível; composição com
    `QuantileForecast.from_raw` produz `guardrail_applied=False` (I5 — empate
    degenerado passa; metade da A2).
  - Ramos de erro cobertos.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/services/test_quantile_grid_emission.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/services/quantile_grid_emission.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(modeling): serviços de emissão da grade (degenerada, gaussiana, tipo 7) com oráculos [5.2/task-02]`

---

### Task 03 — Serviços de domínio de estatística (`baseline_statistics`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/services/baseline_statistics.py`
  - `tests/unit/features/modeling/domain/services/test_baseline_statistics.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** duas funções puras stdlib-only (concept §4):
  `ewma_variance_path(*, returns, decay_lambda) -> tuple[float, ...]` — RMTD
  Eq. [5.3], `sigma2[t]` = variância prevista para `t+1` dado `returns[:t+1]`,
  semente `sigma2[0] = returns[0]**2` (D4), recursão
  `sigma2[t] = λ·sigma2[t-1] + (1-λ)·returns[t]**2`, O(n) por caminho;
  `ar1_step_forecast(*, mu, phi, sigma2_eps, last_return, horizon) ->
  tuple[float, float]` — média `μ + φ^h(r_t − μ)` e desvio
  `sqrt(σ²_ε · Σ_{j=0}^{h-1} φ^{2j})` (Hamilton §4.2 / Box-Jenkins (5.1.16)).
- **Detalhes técnicos:**
  - Validações (`ValueError`): `returns` não-vazio e finito;
    `decay_lambda ∈ (0,1)`; `horizon >= 1`; `sigma2_eps > 0`; `|phi| < 1`
    (superfície de C4 no domínio); `mu`/`last_return` finitos.
- **Critério de aceite (oráculos com tolerância declarada):**
  - EWMA: paridade com `pandas.Series(r**2).ewm(alpha=1-λ, adjust=False).mean()`
    (oráculo no teste) em série sintética; caso analítico curto conferido à
    mão; irrelevância numérica da semente para n > 500 (decai como λⁿ — D4).
  - AR(1): fixture fechada (μ, φ, σ²_ε, r_t, h conhecidos → média/desvio à
    mão); variância crescente em h e convergindo para a incondicional
    σ²_ε/(1−φ²); h=1 reduz a σ_ε.
  - Ramos de erro cobertos.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/services/test_baseline_statistics.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/services/baseline_statistics.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(modeling): serviços de estatística de baseline (EWMA path, AR(1) h-step) com oráculos [5.2/task-03]`

---

### Task 04 — Par read-only `("processed", "dataset_tft")` no `MedallionStore`

- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/adapters/out/parquet/parquet_medallion_store.py`
  - `tests/fakes/shared/in_memory_medallion_store.py`
  - `tests/contract/shared/test_medallion_store_contract.py`
- **Arquivos a criar:** nenhum.
- **O que fazer (concept D3):** expor `("processed", "dataset_tft")` como par
  **read-only** no adapter real e no fake, resolvendo o layout físico **já
  existente** da 3.5 (`<data_root>/processed/dataset_tft/<asset>/dataset_tft_<asset>.parquet`
  — diretório por asset, **não** Hive), sem tocar a semântica de escrita
  bronze.
- **Detalhes técnicos:**
  - **Adapter real:** registrar o par numa pequena entrada de registry
    read-only interna ao adapter (fora do `BRONZE_REGISTRY` pandera — o
    contrato físico do dataset é da 3.5). `read` monta o glob por asset
    (`processed/dataset_tft/<asset>/*.parquet` quando `filters={"asset": ...}`;
    `processed/dataset_tft/**/*.parquet` sem filtro), `SELECT *` sem
    `hive_partitioning` (não há coluna de partição fantasma aqui), sessão
    DuckDB `TimeZone='UTC'`, normalização `NaN → None` como no read bronze;
    dataset/asset inexistente → vazio (C4 do port). `write` para o par ergue
    `ApplicationError` ("read-only"). Par fora do registry segue erro (C2).
  - **Fake:** mesma semântica observável; ganha um helper de semeadura fora
    do port (ex.: `seed_read_only(layer, table, asset, rows)`) para os testes
    unit da Task 06 popularem o dataset em memória; `write` no par ergue o
    MESMO `ApplicationError`.
  - **Contract test:** novos casos parametrizados `[fake, real]` (o real
    semeia gravando o Parquet direto no `tmp_path` com pandas, espelhando o
    layout da 3.5): round-trip de leitura filtrada por `asset`; asset
    inexistente → vazio; `write` no par ergue; bronze intacto (casos
    existentes seguem verdes).
- **Critério de aceite:** contract test verde em fake e real para o novo par;
  todos os casos bronze pré-existentes inalterados e verdes; `write` read-only
  ergue nas duas implementações.
- **Comando de verificação:**
  ```bash
  pytest tests/contract/shared/test_medallion_store_contract.py -v
  mypy --strict src/financial_forecasting/shared/adapters/out/parquet/parquet_medallion_store.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(store): par read-only (processed, dataset_tft) no MedallionStore [5.2/task-04]`

---

### Task 05 — Port `BaselineForecaster` + fake + suite de contrato (perna fake)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/ports/__init__.py`
  - `src/financial_forecasting/features/modeling/application/ports/out/__init__.py`
  - `src/financial_forecasting/features/modeling/application/ports/out/baseline_forecaster.py`
  - `tests/fakes/features/modeling/__init__.py`
  - `tests/fakes/features/modeling/in_memory_baseline_forecaster.py`
  - `tests/contract/features/modeling/__init__.py`
  - `tests/contract/features/modeling/test_baseline_forecaster_contract.py`
- **Arquivos a modificar:** nenhum. (Excedente de arquivos = `__init__.py`
  boilerplate — exceção declarada em §1.)
- **O que fazer:** criar o Protocol do concept §4 — alias
  `GridByHorizon = Mapping[int, tuple[float, ...]]` e
  `BaselineForecaster.forecast(*, spec, returns, train_end_idx,
  decision_indices, horizons, quantile_levels) -> Mapping[int, GridByHorizon]`
  (dados como primitivos/`collections.abc`; o VO `BaselineSpec` cruza o port —
  precedente `Candle`/`IndicatorCalculator`). Criar o fake determinístico e a
  **suite de contrato única** (skill `pytest-with-fakes`), parametrizada por
  factory com ids `["fake"]` nesta Task — a Task 07 adiciona `"real"` (mesmo
  desenho do contract test do `MedallionStore`).
- **Detalhes técnicos:**
  - **Fake (`FakeBaselineForecaster`):** implementa as 5 famílias reusando os
    serviços de domínio das Tasks 02/03 (a emissão É o contrato); estimação
    stdlib simples congelada no train (I4/D2): `μ̂` = média de
    `returns[:train_end_idx+1]`; para `ar1`, momentos do train (φ̂ =
    autocorrelação lag-1, σ̂²_ε = (1−φ̂²)·var); estado condicionante causal
    até cada decisão (r_t, recursão EWMA desde a origem, janela rolante
    terminando em t — D2/D4). Ergue `ValueError` em janela/train insuficiente
    (C1) e em emissão não-finita (C5).
  - **Contract suite (cobre o contrato semântico do port — A4/A7/A8):**
    parametrizada sobre as 5 specs de `canonical_five()` (com
    `historical_quantiles_window` reduzido, ex. 20, para fixtures curtas —
    override sancionado pelo ADR 5.2.0003) ×  implementações:
    - **I3 (causalidade por truncamento):** mutar/truncar `returns` após a
      decisão `t` não muda a grade em `t` — todas as famílias.
    - **I4 (congelamento, recorte por família — ADR 5.2.0002 Implementation
      notes):** para `ar1`/`historical_mean`, mutar
      `returns[train_end_idx+1 : t]` (excluindo o r_t condicionante no caso
      `ar1`) não muda a emissão em `t`; para `zero_return`, qualquer mutação
      pós-train é inócua; para `ewma_vol`/`historical_quantiles` NÃO assertar
      invariância de emissão (o caminho causal legitimamente entra) — o freeze
      é λ/W virem da spec.
    - **C5:** NaN injetado na janela condicionante → ergue (nunca emite).
    - **C1:** `historical_quantiles` com menos de `window` retornos até a
      decisão ergue; train trivialmente insuficiente para `ar1` ergue.
    - **Forma:** toda decisão pedida presente no retorno; toda grade com
      `len == len(quantile_levels)`; `zero_return` constante 0; flat em h para
      as famílias flat, variância crescente em h para `ar1` (concept §3).
- **Critério de aceite:** suite de contrato verde no id `fake`; port sem
  imports proibidos (application importa só domain/shared-ports).
- **Comando de verificação:**
  ```bash
  pytest tests/contract/features/modeling/test_baseline_forecaster_contract.py -v
  mypy --strict src/financial_forecasting/features/modeling/application/ports/out/baseline_forecaster.py
  uv run lint-imports
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(modeling): port BaselineForecaster + fake + suite de contrato (I3/I4/C1/C5) [5.2/task-05]`

---

### Task 06 — Use case `RunBaselines` (unit com fakes; remoção-zero do dedup)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/__init__.py`
  - `src/financial_forecasting/features/modeling/application/use_cases/run_baselines.py`
  - `tests/unit/features/modeling/application/__init__.py`
  - `tests/unit/features/modeling/application/test_run_baselines.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar DTOs e use case com a assinatura exata do
  concept §4 (`RunBaselinesCommand`, `BaselineRunSummary`,
  `RunBaselinesResult`, `RunBaselines.__init__(*, store, splitter, forecaster,
  persist_predictions, analytics_repository, hasher)` e `__call__`). Fluxo do
  concept §4 (por referência — é o contrato):
  1. Valida o comando (C2) **antes de qualquer I/O**: `quantile_levels`
     estritamente crescentes/únicos em (0,1); `horizons` não-vazio, positivos,
     `max(horizons) <= scope.max_horizon`; specs sem `model_version` duplicado.
  2. Lê `("processed", "dataset_tft")` com `filters={"asset": scope.asset_id}`;
     vazio → `ValueError` (C7). Ordena por `timestamp`, extrai
     `dataset_timestamps` (ISO, via `datetime.isoformat()`) e
     `target_return: tuple[float, ...]`.
  3. `splitter.split(sessions, scope, n_folds=..., test_size=..., val_size=...,
     calib_size=..., embargo=..., hasher=hasher)` com `sessions` =
     `timestamp.date()` da grade; mapeia ISO-date → índice para resolver
     `train_end_idx` (= índice de `fold.train[-1]`) e `decision_indices`
     (índices de `fold.test`) — **aritmética de índices, sem resolver
     timestamp** (I2).
  4. Por (spec × fold): `forecaster.forecast(...)`; por decisão monta
     `Mapping[horizon, QuantileForecast.from_raw(levels, raw)]` (guardrail
     4.3, I5).
  5. `run_id = hasher.hash_mapping(payload canônico: campos do scope + campos
     da spec + fingerprint do fold + horizons + quantile_levels +
     schema_version)`; `config_signature = hasher.hash_mapping(payload da
     spec + horizons + quantile_levels + schema_version)`; grava 1 `RunRecord`
     em `dim_run` via `analytics_repository.write(layer="silver",
     table="dim_run", rows=[asdict(record)])` (o adapter injeta
     `created_at_utc` — 4.2 I5) com `fold=str(fold_index)`, `seed=None`,
     `parent_sweep_id=scope.cohort_id`, `split_fingerprint` do fold (I9/I10/D5).
  6. **Enforcement I6 (duas camadas):** por spec, coleta as entradas
     estruturais de emissão de todos os folds — chave `(split, horizon,
     decision_idx + horizon, quantile_level)`, rank `decision_idx` — e aplica
     `deduplicate_operationally_latest`. **Nota de alcançabilidade:** com essa
     chave o rank é função da chave (`horizon` fixo na chave ⇒ mesmo
     `decision_idx + horizon` ⇒ mesmo `decision_idx`), logo toda duplicata
     real de ponto alinhado tem empate de rank e **ergue primeiro no próprio
     serviço 5.1** (C9, `ValueError` "ambiguous operationally-latest…" —
     `operationally_latest_dedup.py`). A asserção de remoção-zero do use case
     (I6 do concept) permanece como **defesa-em-profundidade** atrás dela:
     extrair um helper puro module-level em `run_baselines.py` —
     `_assert_zero_removal(*, before: int, after: int)` que ergue `ValueError`
     com mensagem própria ("dedup removed N aligned-point entries — upstream
     fold geometry bug") quando `before != after` — chamado no fluxo após o
     dedup e **testável por unit direto** (sem ramo morto, sem
     `# pragma: no cover`).
  7. Persiste via `PersistPredictions` (1 comando por decisão, com
     `dataset_timestamps` da grade completa; `split="test"`,
     `model_version=spec.model_version`, `asset`/`feature_set_name` do scope,
     `schema_version` do comando); `IncompletePredictionWindowError` é tratado
     DENTRO do 4.3 (C6 — linhas puladas contam em `rows_skipped`);
     `DuplicateKeyError` **propaga** (C8). Agrega `rows_written`/`rows_skipped`
     por (spec × fold) em `BaselineRunSummary`.
- **Detalhes técnicos:**
  - Import cross-BC `modeling.application → analytics_store.application`
    (`PersistPredictions` + VOs) é decisão consciente do concept §8 —
    documentar no docstring do módulo com a justificativa por referência.
  - Determinismo (I9): sem clock/aleatoriedade no use case; mesma entrada →
    mesmos payloads/hashes.
- **Critério de aceite (unit, tudo com fakes — `FakeMedallionStore` semeado
  via helper da Task 04, `FakeBaselineForecaster`, `FakeAnalyticsRepository`,
  `InMemoryHasher`, splitter real sobre grade sintética):**
  - Happy path: 5 specs × N folds → 1 `BaselineRunSummary` e 1 linha `dim_run`
    por (spec × fold) com `model_version='baseline_*'`, `fold=str(i)`,
    `seed=None`, `parent_sweep_id=cohort_id`; linhas de predição no fake repo
    com `split="test"` e grade completa por decisão × horizonte (A5-unit).
  - `run_id` determinístico: duas invocações idênticas → mesmos `run_id`s (I9).
  - C2: cada validação ergue **sem** nenhuma chamada a store/repo (fake conta
    chamadas). C7: read vazio ergue.
  - C6: decisões na cauda da grade (janela incompleta para h) → contadas em
    `rows_skipped`, sem linha fabricada.
  - **A6/I6 (duas asserções, uma por camada):**
    - **C9 (1ª linha de defesa real):** stub de splitter (subclasse de
      `WalkForwardSplitter` com `split` sobrescrito) devolvendo dois folds com
      blocos `test` sobrepostos (duplicata de ponto alinhado fabricada) →
      `RunBaselines` ergue o `ValueError` do serviço 5.1 com a mensagem
      "ambiguous operationally-latest…" (empate de chave+rank).
    - **I6 (defesa-em-profundidade, sem ramo morto):** unit direto do helper
      puro `_assert_zero_removal` — `before == after` passa; `before != after`
      ergue `ValueError` com a mensagem "dedup removed … aligned-point
      entries…" (cobre o ramo sem `# pragma: no cover` e sem depender de
      entrada real que o C9 intercepta antes).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/application/test_run_baselines.py -v
  mypy --strict src/financial_forecasting/features/modeling/application/use_cases/run_baselines.py
  uv run lint-imports
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(modeling): use case RunBaselines com dedup remoção-zero assertado [5.2/task-06]`

---

### Task 07 — Adapter `StatsforecastBaselineForecaster` + oráculo AR(1) + perna real do contrato

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/adapters/out/__init__.py`
  - `src/financial_forecasting/features/modeling/adapters/out/statsforecast/__init__.py`
  - `src/financial_forecasting/features/modeling/adapters/out/statsforecast/statsforecast_baseline_forecaster.py`
  - `tests/integration/features/modeling/__init__.py`
  - `tests/integration/features/modeling/test_statsforecast_baseline_forecaster.py`
- **Arquivos a modificar:**
  - `pyproject.toml` + `uv.lock` (dependência `statsforecast`, pin por minor —
    postura `exchange-calendars`/`pandas-ta-classic`; ver §5 para o risco
    numba)
  - `tests/contract/features/modeling/test_baseline_forecaster_contract.py`
    (adiciona a factory `_build_real` com id `"real"`)
  - (Excedente de arquivos = `__init__.py` + lockfile — exceção declarada em §1.)
- **O que fazer (D1 — ADR 5.2.0001):** implementar o port com **dispatch
  exaustivo** pelas 5 famílias, delegando TODA a emissão aos serviços de
  domínio (Tasks 02/03); `statsforecast` usado **apenas** na estimação do
  AR(1) (`ARIMA(order=(1, 0, 0), include_mean=True).fit(y).model_` — port do
  `arima` do R), atrás do **seam injetável**
  `_fit_ar1(returns) -> (mu, phi, sigma2_eps)` (C4 testável com fit forjado).
- **Detalhes técnicos:**
  - Estimação só com `returns[:train_end_idx+1]` (I4/D2); estado causal por
    decisão: `ar1` condiciona em `r_t = returns[t]`; `ewma_vol` usa
    `ewma_variance_path(returns[:t+1], λ)[-1]` → `gaussian_grid(mean=0,
    std=σ̂)` idêntica para todo h (flat — RMTD [5.18]); `historical_quantiles`
    usa `sample_quantiles_type7(returns[t-W+1 : t+1])` (janela termina EM t —
    ADR 5.2.0003), C1 se `t+1 < W`; `zero_return`/`historical_mean` via
    `degenerate_grid`.
  - **Atenção μ vs intercepto:** a parametrização do R devolve o "intercept"
    que É a média quando `include_mean=True`; o wrapper converte
    explicitamente para (μ̂, φ̂, σ̂²_ε) — o oráculo abaixo existe para pegar
    exatamente esse bug de wiring (concept §8).
  - C4: fit com |φ̂| ≥ 1, σ̂²_ε ≤ 0 ou não-finito → ergue. C5: qualquer valor
    cru não-finito → ergue antes do VO. Família desconhecida → ergue (I7;
    ramo coberto via spec forjada com `object.__setattr__` no teste).
  - Wrapper fino tipado (`float`/tuplas na fronteira); `# type: ignore`
    localizado e comentado se necessário.
- **Critério de aceite:**
  - **Oráculo AR(1) (A3):** série sintética AR(1) com **μ ≠ 0 material** e φ
    alto o suficiente para distinguir μ do intercepto c = μ(1−φ) dentro da
    tolerância (ex.: μ = 0.05, φ = 0.6, n = 2000, RNG semeado); recuperação de
    (μ̂, φ̂, σ̂²_ε) com tolerância **declarada** no teste; fixture fechada
    confirmando que a emissão do adapter = `ar1_step_forecast` +
    `gaussian_grid` do domínio.
  - C4 exercitado via seam com fit forjado (φ̂ = 1.2; σ̂²_ε = 0; NaN) → ergue.
  - Dispatch exaustivo: teste parametrizado sobre `BASELINE_FAMILIES` — toda
    família canônica emite; spec de família desconhecida ergue (I7).
  - **Suite de contrato verde nos ids `fake` E `real`** (A7 fechado).
- **Comando de verificação:**
  ```bash
  uv sync --extra dev
  pytest tests/integration/features/modeling/test_statsforecast_baseline_forecaster.py -v
  pytest tests/contract/features/modeling/test_baseline_forecaster_contract.py -v
  mypy --strict src/financial_forecasting/features/modeling/adapters/out/statsforecast/statsforecast_baseline_forecaster.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(modeling): adapter statsforecast (fit AR(1) atrás de seam) com oráculo de recuperação [5.2/task-07]`

---

### Task 08 — Fitness functions: `modeling-no-statsforecast-leak` + registro em `store-no-storage-leak`

- **Arquivos a modificar:**
  - `.importlinter`
  - `tests/architecture/test_import_contracts.py`
- **Arquivos a criar:** nenhum.
- **O que fazer (I8; finding da 5.1 §7; critério de aceite da issue #51):**
  1. Registrar `financial_forecasting.features.modeling.application` e
     `financial_forecasting.features.modeling.domain` em `source_modules` do
     contrato 6 `store-no-storage-leak` (comentário com referência Stage 5.2 /
     finding 5.1, no padrão dos registros anteriores).
  2. Criar o contrato 9 `modeling-no-statsforecast-leak` (type = forbidden;
     padrão `tracker-no-mlflow-leak`/`sentiment-no-ml-leak`): sources
     `modeling.{domain,application}`; forbidden `statsforecast`, `numba`,
     `numpy`; `allow_indirect_imports = False`; comentário explicando que o
     `domain-purity` cobre numpy só no domain — este contrato fecha a camada
     application.
  3. Estender `tests/architecture/test_import_contracts.py`: novo contrato na
     lista de contratos esperados e nos casos parametrizados de reação a
     violação (ex.: `modeling.application` importando `statsforecast` e
     `pandas` reprova).
  4. **Prova por quebra intencional revertida (A9):** inserir `import
     statsforecast` em `run_baselines.py` → `uv run lint-imports` vermelho →
     reverter; idem `import pandas` (store-no-storage-leak). Registrar as duas
     provas em §7 ao executar.
- **Critério de aceite:** `uv run lint-imports` verde no repo limpo; vermelho
  com cada quebra intencional; testes de arquitetura verdes; `modeling.domain`
  segue stdlib-only (`domain-purity` já registrado na 5.1).
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  pytest tests/architecture/test_import_contracts.py -v
  ```
- **Commit sugerido:** `chore(modeling): fitness functions modeling-no-statsforecast-leak e store-no-storage-leak [5.2/task-08]`

---

### Task 09 — Wiring no composition root + integração ponta-a-ponta `RunBaselines`

- **Arquivos a criar:**
  - `tests/integration/features/modeling/test_run_baselines.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `tests/unit/shared/test_composition_root.py`
- **O que fazer:**
  - **Wiring (regra 5 do CLAUDE.md; concept §8):** `wire_dependencies` passa a
    montar e expor `run_baselines: RunBaselines` em
    `ApplicationDependencies` — `PersistPredictions(repository=
    analytics_repository)`; `WalkForwardSplitter(TradingCalendar(
    calendar_provider.sessions(start=..., end=...)))` com janela ampla fixa
    cobrindo o span plausível do dataset (ex.: 1990-01-01 a 2035-12-31 —
    constantes comentadas; ver §5); `StatsforecastBaselineForecaster()` como
    port `BaselineForecaster`; `store`/`analytics_repository`/`hasher` já
    wireados.
  - **Integração e2e (A5/A2/C6):** em `tmp_path`, semear um dataset TFT
    sintético (`processed/dataset_tft/TEST/...parquet`, grade densa de
    sessões com `timestamp` + `target_return` — layout da 3.5) e rodar
    `RunBaselines` com **adapters reais** (`ParquetMedallionStore`,
    `ParquetAnalyticsRepository`, `StatsforecastBaselineForecaster`,
    `CanonicalJsonHasher`, splitter real). Specs com
    `historical_quantiles_window` reduzido (override de teste sancionado —
    ADR 5.2.0003) para a fixture caber em ~centenas de sessões.
- **Critério de aceite (asserções do teste de integração):**
  - `fact_oos_predictions` contém linhas LONG para as **5**
    `model_version='baseline_*'`, `split="test"`, grade completa por decisão ×
    horizonte; `target_timestamp_utc == dataset_timestamps[decision_idx + h]`
    (I2 — resolvido só pelo persister).
  - `dim_run` tem 1 linha por (spec × fold) com `run_id` referenciado pelas
    predições (I10), `seed=None`, `parent_sweep_id` do cohort.
  - Linhas de `zero_return`/`historical_mean` persistem com `value_guardrail`
    **idêntico em todas as linhas de `quantile_level` de uma mesma decisão ×
    horizonte** e `guardrail_applied == 0` (A2/I5 — degenerada passa; o schema
    `fact_oos_predictions` é LONG, sem colunas q_low/q_high).
  - Decisões da cauda sem janela completa → `rows_skipped > 0` e nenhuma
    linha fabricada (C6).
  - Reexecução da mesma invocação → `DuplicateKeyError` propaga (C8).
  - Teste do composition root: `wire_dependencies()` expõe `run_baselines`
    montado (campos tipados pelos ports).
- **Comando de verificação:**
  ```bash
  pytest tests/integration/features/modeling/test_run_baselines.py -v
  pytest tests/unit/shared/test_composition_root.py -v
  make check
  ```
- **Commit sugerido:** `feat(modeling): wiring RunBaselines no composition root + integração ponta-a-ponta [5.2/task-09]`

---

### Task 10 — Roadmap: "6 baselines" → 5 specs (DoDs 5.2 e 5.5) + descrição humana da 5.2

- **Arquivos a modificar:**
  - `docs/roadmap.md`
- **Arquivos a criar:** nenhum.
- **O que fazer (escopo desta Stage por decisão do ADR 0.0.0052, Implementation
  notes; concept §1/§8):** ajustar as **duas** linhas de `definition_of_done`
  que dizem "6 baselines" — Stage 5.2 (que também diz "triplet degenerado" →
  "grade degenerada") e Stage 5.5 — para "5 specs de baseline (`zero_return`
  ≡ RW sem drift)"; retocar a **descrição humana** da 5.2: "via
  `statsforecast`" → "via `statsforecast` (fit do AR(1)) + fórmulas canônicas
  no domínio validadas por oráculo (ADR 5.2.0001)". Nenhuma outra linha do
  roadmap muda nesta Task (status/datas da Stage são do fechamento, commit
  `[5.2/--]` pós-auditoria).
- **Detalhes técnicos:** executar como última Task, junto do fechamento da
  Stage (mesmo PR), para o texto não ficar stale nem adiantado.
- **Critério de aceite:** `grep -n "6 baselines" docs/roadmap.md` não devolve
  nada; `grep -n "triplet degenerado" docs/roadmap.md` não devolve nada; as 3
  linhas alteradas conferem com o concept §1 ("Ajuste do texto…") e §8.
- **Comando de verificação:**
  ```bash
  grep -n "6 baselines\|triplet degenerado" docs/roadmap.md; test $? -eq 1
  make docs-check
  ```
- **Commit sugerido:** `docs(roadmap): DoDs 5.2/5.5 de 6 baselines para 5 specs e descrição da 5.2 [5.2/task-10]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 5.2: complete` e ser mergeada em `develop`.

### Verificações automatizadas
```bash
make check                 # ruff + mypy strict + lint-imports + check_layout + docs-check + testes (cov >= 90%)
uv run pytest --cov=financial_forecasting --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/5.2-baselines-naive-statistical/technical.md
grep -rn "6 baselines" docs/roadmap.md ; test $? -eq 1
```

### Verificações funcionais
- [ ] Uma invocação de `RunBaselines` (integração, `tmp_path`) produz, para as
      5 specs canônicas, predições na grade densa comum em
      `fact_oos_predictions` (`model_version='baseline_*'`, `split="test"`,
      alinhadas por `target_timestamp`) e 1 linha em `dim_run` por
      (spec × fold) — nenhum baseline documentado sem implementação (I7/A5).
- [ ] Suite de contrato do `BaselineForecaster` verde nos ids `fake` e `real`
      (I3/I4/C1/C5 — A7).
- [ ] `import statsforecast` (ou `pandas`) em `modeling.application` reprova o
      `lint-imports` — quebras intencionais revertidas registradas em §7 (A9).
- [ ] Grades degeneradas persistem com `value_guardrail` idêntico em todas as
      linhas de `quantile_level` de uma mesma decisão × horizonte e
      `guardrail_applied == 0` (I5/A2 — schema LONG, sem q_low/q_high).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde.
- [ ] `make check` verde no branch.
- [ ] Cobertura ≥ 90% nos arquivos da Stage (A11).
- [ ] §7 reflete a execução real — incluindo as provas de quebra intencional
      (Task 08) e o **[finding] para a 5.5** (concept §8): o hash do cohort
      confirmatório deve incluir `quantile_levels` no payload (fecha I11).
- [ ] Commit final `stage 5.2: complete` aplicado (pós-auditoria).
- [ ] Branch mergeado em `develop`.
- [ ] `roadmap.md` atualizado: Task 10 aplicada; Stage marcada `done`,
      `updated_at` e `last_reviewed_at` no fechamento.
- [ ] ADRs 5.2.0001/0002/0003 em `accepted` (já estão).
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências; casos não óbvios:

```
Task 01 (BaselineSpec) ────────────────┐
Task 02 (emissão) ──┐                  ├─► Task 05 (port+fake+contrato) ─► Task 06 (RunBaselines)
Task 03 (estatística) ┴────────────────┘            │                          │
Task 04 (store par read-only) ─────────────────────►┼──────────────────────────┤ (fake do store na 06;
                                                    └─► Task 07 (adapter real) ┤  store real na 09)
Task 07 ─► Task 08 (fitness: statsforecast instalado p/ a quebra intencional)  │
Task 06 + Task 07 + Task 08 ─► Task 09 (wiring + e2e)                          │
Task 10 (roadmap) — independente; executar por último, junto do fechamento ◄───┘
```

- Task 04 precede a 06 porque o `FakeMedallionStore` precisa suportar o par
  `("processed", "dataset_tft")` nos testes unit do use case.
- Task 08 sucede a 07 porque a prova de quebra intencional importa
  `statsforecast` (precisa estar instalado e declarado).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `statsforecast` (arrasta `numba`) pesa no `uv sync`/CI ou falha de build | Pin por minor + `uv.lock`; uso confinado ao seam `_fit_ar1` — fallback documentado no ADR 5.2.0001 (Alt. C): trocar a estimação por implementação própria/`statsmodels` + oráculo, sem tocar port/domínio; se a 1ª compilação numba estourar o tempo de CI, marcar o teste do adapter como `slow` e registrar `[decision]` em §7 |
| `statsforecast` sem stubs quebra mypy strict | `ignore_missing_imports = True` global já cobre; fronteira do wrapper tipada com `float`/tuplas; `# type: ignore` localizado e comentado se sobrar resíduo |
| Desalinhamento μ vs intercepto (c = μ(1−φ)) na parametrização do R | É exatamente o que o oráculo com μ ≠ 0 material da Task 07 detecta; corrigir o wrapper, nunca afrouxar a tolerância |
| Loops stdlib no domínio lentos na escala real (~4k sessões × ~800 decisões) | Recursões O(n) por caminho; medir no teste de integração; se doer, mover o cálculo quente para o adapter (numpy) mantendo o domínio como oráculo — reversão local prevista no concept §10/ADR 5.2.0001, registrar `[deviation]` |
| Par read-only bagunçar a semântica do store | Entrada de registry read-only isolada (write ergue), layout físico inalterado; casos bronze do contract test seguem verdes (Task 04) |
| Janela do `TradingCalendar` no wiring (span fixo 1990–2035) não cobrir um dataset futuro | Constantes comentadas no composition root; se apertar, promover a campo de `Settings` ou factory por invocação — registrar `[decision]` em §7 (não muda contrato do use case) |
| Amplificação de escrita (1 `write` por decisão × spec × fold, read-merge-rewrite no Parquet) | Aceita na escala piloto (concept §10); se doer na execução, vira `[finding]` em §7 (Stage candidata 4.x/5.5) — nunca mudança silenciosa de contrato |
| Cobertura < 90% em ramos de erro (C1–C9) | Casos de erro dedicados por Task; se sobrar ramo inalcançável, `# pragma: no cover` comentado (padrão do repo) |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo, contratos (§4), invariantes (§5),
  erros (§6), decisões D1–D6 (§7), integrações (§8), critérios (§11).
- ADRs desta Stage:
  [`5.2.0001`](../../adr/5_2_0001-baseline-math-in-domain-statsforecast-ar1-fit.md),
  [`5.2.0002`](../../adr/5_2_0002-frozen-train-estimation-causal-state.md),
  [`5.2.0003`](../../adr/5_2_0003-historical-quantiles-window-252.md);
  relacionados: [`0.0.0052`](../../adr/0_0_0052-baseline-quantile-emission-conventions.md),
  [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md),
  [`0.0.0018`](../../adr/0_0_0018-anti-leakage-non-negotiable.md),
  [`4.1.0002`](../../adr/4_1_0002-fact-oos-predictions-long-quantile-format.md),
  [`4.3.0001`](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md),
  [`4.3.0002`](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md).
- Doc de domínio: [`quantile-model-training.md`](../../domain/modeling/quantile-model-training.md)
  §2/§3/§7.
- Stage anterior: [`../5.1-walk-forward-harness/technical.md`](../5.1-walk-forward-harness/technical.md)
  (precedentes de Task; finding `store-no-storage-leak` em §7).
- [`../../LAYOUT.md`](../../LAYOUT.md), [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4,
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3/§9.
- Skills aplicáveis: `task-ordering-hex`, `pytest-with-fakes`,
  `hex-arch-python`, `ddd-tactical-patterns`, `import-linter-rules`,
  `composition-root`, `repository-pattern`, `project-scope-principles`,
  `dmls-ch05-model-development-and-evaluation`.
- Issue: [#51](https://github.com/MarceloSanC/financial-forecasting/issues/51).
- Externas: documentação oficial `statsforecast` (Nixtla — inventário
  verificado 2026-07-15); fontes primárias do doc de domínio §9.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->
<!-- END: post-execution -->
