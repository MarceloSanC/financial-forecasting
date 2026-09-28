---
title: Technical — Stage 6.1 — Métricas de scoring e calibração (pinball, CRPS_Q, interval score, PICP/MPIW, gate de degeneração)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), TDD inside-out no BC evaluation (1ª fatia — domain + application/ports + adapters/out/scoring)
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, scoring-and-calibration-metrics, evaluation, coverage-series, pinball, crps, interval-score, degeneracy-gate, coverage-metrics, scoring-backend, sklearn, scoringrules, importlinter, port-coverage]
status: done
created_at: 2026-09-28
updated_at: 2026-09-28
stage_id: 6.1-scoring-and-calibration-metrics
stage_title: Métricas de scoring e calibração
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [4.3-prediction-persister]
concept_ref: ./concept.md
issue_id: 77
branch: feat/77-6-1-scoring-and-calibration-metrics
tasks_count: 11
---

# Technical — Stage 6.1 — Métricas de scoring e calibração

> **Como usar (para code assistant):** ler §1, executar Tasks em ordem (§2),
> 1 Task = 1 commit, não avançar sem verificação verde; ao fim validar §3 e
> registrar §7. Commits seguem [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(evaluation): <descrição> [6.1/task-NN]`, `Refs #77`.
>
> Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
> resolver pelo §2 de [`PROMPT-step-single-session.md`](../../PROMPT-step-single-session.md)
> (docs → ADR; E/C → `evidence-resolution` + ADR; P → sobe à sessão mestra) e
> registrar em §7. Nunca propagar silenciosamente.

## 1. Contexto e estratégia de execução

### Resumo

Primeira fatia do BC `evaluation`: o VO `CoverageSeries` (série alinhada de um
modelo × horizonte sobre o `QuantileForecast` da 4.3), os cinco serviços de
domínio stdlib-only (`PinballScore`, `CrpsScore`, `IntervalScore`,
`DegeneracyGate`, `CoverageMetrics`), cada um com o seu VO de relatório no
próprio módulo, o validador único de entrada dos kernels (C7), o port-out
`ScoringBackend` com `FakeScoringBackend` e a suíte de contrato
`[fake, sklearn, scoringrules]`, os adapters `SklearnScoring` e
`ScoringrulesBackend`, as dependências `scikit-learn`/`scoringrules`, o
registro do slice em seis contratos import-linter (um deles novo) e o
LAYOUT §7 atualizado.

Todas as decisões vêm do concept **por referência** — nenhuma é re-derivada:
D1 (fórmulas no domínio, libs como oráculo atrás do port —
[ADR 6.1.0001](../../adr/6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md)),
D2 (`CoverageSeries` —
[ADR 6.1.0002](../../adr/6_1_0002-coverage-series-aligned-input-vo.md)),
D3 (tolerância absoluta do gate —
[ADR 6.1.0003](../../adr/6_1_0003-degeneracy-absolute-spread-tolerance.md)),
D4 (o gate invalida só as métricas de calibração — ADR 0.0.0011), D5 (a
cobertura recomputa o gate —
[ADR 6.1.0004](../../adr/6_1_0004-coverage-metrics-recomputes-degeneracy-mask.md)),
D6 (sem persistência nem e2e), D7 (arquivos de teste do roadmap + suíte de
contrato adicional), D8 (`mean_width` ≠ MPIW com degeneração). Fórmulas: doc
de domínio [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md)
§2, §3, §4.1–§4.3, §4.5–§4.6, §5, §11.3.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`): scaffolding do slice já
registrado nos gates de pureza (precedente 5.1 Task 01) → VO → aresta
`bc-independence` do VO + LAYOUT §7 (só depois do VO: com
`unmatched_ignore_imports_alerting = error`, a exceção da aresta precisa casar
com um import que já exista) → serviços de domínio, um por Task, cada um com
fixture analítica no mesmo commit → dependências → port + fake + suíte (perna
`fake`) → adapter sklearn → adapter scoringrules. As dependências vêm **antes**
do port para que a janela sem adapter real seja de exatamente um commit
(ADR 6.1.0005).

**Exceções de ordem/contagem declaradas (PIPELINE §4.3; skill `task-ordering-hex`):**

- **Baseline transitório do `port-coverage` (Tasks 09 → 10)** —
  [ADR 6.1.0005](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md).
  A Task 09 cria o port sem adapter real (regra dura port ≠ adapter), o que
  deixa o `check_port_coverage.py` vermelho; ela adiciona a entrada
  `ScoringBackend` em `scripts/arch_baseline.toml` **e** ajusta o
  `test_real_repo_violations_are_exactly_the_declared_baseline`
  (`tests/architecture/test_port_coverage_gate.py`, hoje `== ["Hasher"]`)
  para `["Hasher", "ScoringBackend"]`; a Task 10 (primeiro adapter real)
  reverte os dois — o gate reprova entrada morta e o teste de arquitetura
  reprova a lista desatualizada, então a reversão é forçada.
- **Tasks 01, 09 e 10 excedem 5 arquivos** — excedente é boilerplate
  (`__init__.py` de pacotes novos em `src/` e `tests/`). Precedente: 5.1
  Task 01 e 5.2 Tasks 05/07.
- **Nenhum use case nesta Stage** (concept D1/D6; ADR 6.1.0001 item 5): a
  camada `application` tem só o port; não há wiring no composition root nem
  teste de integração ponta-a-ponta. A verificação executável do port é a
  suíte de contrato.

**Decisões de detalhe planejadas (abaixo do limiar de concept — não mudam
contrato, fronteira nem critério; viram entrada `[decision]` em §7 ao
executar):**

- **`store-no-storage-leak` também cobre `evaluation.{application,domain}`**
  (Task 01). O concept A9 lista os contratos obrigatórios; este é adicional e
  **reforça** a I11 ("`evaluation.domain` e `evaluation.application` importam
  só stdlib + o VO do 4.3"), fechando `pandas`/`pyarrow`/`duckdb`/`pandera`
  na application, que nenhum contrato do A9 cobre. Todos os outros slices já
  estão nele.
- **Validação nos kernels por ponto** (Task 04). O ADR 6.1.0001 item 1 põe a
  validação C7 no validador único "chamado pelas funções de domínio";
  `pinball_loss`, `crps_quantile` e `interval_score` também o chamam (nível,
  miscobertura, `len(quantiles) == len(levels)`, `lower ≤ upper`), com um
  teste C7 por kernel — senão um kernel aceitaria `level = 1.5` que a função
  de série recusa.
- **Sequência vazia ergue `ValueError`** nas funções de série e no port
  (Task 04). O C7 não lista o caso; a média sobre zero pontos é indefinida e
  os relatórios já exigem `n_points ≥ 1` (concept §4). É pré-condição do
  kernel, não contrato novo.

**Gate por Task (RUNBOOK §Gates em camadas, ADR 0.0.0055):** T1 =
`make check-task SLICE=evaluation`. As Tasks que tocam `.importlinter`,
`scripts/arch_baseline.toml`, `tests/architecture/` ou
`pyproject.toml`/`uv.lock` (01, 03, 08, 09, 10) rodam **T3** (`make check`) no
lugar do T1. Checkpoint C (T2, `make check-block`) após as Tasks 03, 06, 09
e 11.

**Onde rodar:** todo comando `uv run`/`make` roda no container de dev
(`financial_forecasting-app:dev`), com o venv da sessão; o host não tem o
toolchain. Scripts stdlib de docs (`python scripts/check_*.py`) rodam no host.

### Pré-condições

- Stage `4.3-prediction-persister` em `done` e mergeada em `develop`
  (`QuantileForecast` em `analytics_store/domain/value_objects/quantile_forecast.py`).
- Concept desta Stage em `done`; ADRs 6.1.0001–0005 em `accepted`.
- Working tree na branch `feat/77-6-1-scoring-and-calibration-metrics`.
- **A12 depende da 5.5:** a redação do DoD da 6.1 ("métricas de
  **calibração** da linha") hoje só existe na branch
  `feat/102-5-5-confirmatory-retrain` (`roadmap.md:763`). A 6.1 **não** edita
  o DoD; o A12 só fecha quando a 5.5 estiver em `develop` e a 6.1 for
  rebaseada sobre ela. Se a 6.1 chegar ao gate de saída antes, registra
  `[finding]` em §7 e o A12 fica pendente dessa condição, declarado no PR.

### Premissas técnicas

- Python 3.12; `uv`; `make check` = ruff + mypy strict + check_layout +
  lint-imports + fake-parity + port-coverage + docs-check + pytest com
  cobertura ≥ 90 %.
- `mypy` global com `ignore_missing_imports = true` — `scoringrules`/`sklearn`
  sem stubs não quebram o strict; a fronteira dos adapters é tipada com os
  tipos literais da assinatura do port (concept §4).
- `scikit-learn` 1.9.0 já está no `uv.lock` (transitiva); `scoringrules` é
  nova. O grimp resolve pelo AST módulos externos não instalados (precedente
  `numba` em `test_import_contracts.py`), então o contrato novo pode proibir
  `scoringrules` na Task 01, antes da Task 08 instalá-lo.
- Os testes podem usar `random` (stdlib) com seed declarada para grades sem
  empate. Os testes **unit** não importam sklearn/scoringrules: os valores de
  referência do sklearn entram como constantes (fixtures oficiais da doc do
  `mean_pinball_loss`); a checagem contra as bibliotecas é a suíte de contrato
  (ADR 6.1.0001 item 4).
- Tolerâncias numéricas sempre declaradas no módulo de teste (ADR 0.0.0021;
  ADR 6.1.0001 Implementation notes: ruído de soma float64 da ordem de 1e-12).

### Estrutura de pastas afetada

```
src/financial_forecasting/features/evaluation/                 # NOVO slice
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── value_objects/{__init__.py, coverage_series.py}
│   └── services/{__init__.py, scoring_input_validation.py, pinball_score.py,
│                 crps_score.py, interval_score.py, degeneracy_gate.py,
│                 coverage_metrics.py}
├── application/
│   ├── __init__.py
│   └── ports/{__init__.py, out/{__init__.py, scoring_backend.py}}
└── adapters/
    ├── __init__.py
    └── out/{__init__.py, scoring/{__init__.py, sklearn_scoring.py, scoringrules_backend.py}}
tests/
├── unit/features/evaluation/{__init__.py, conftest.py, test_coverage_series.py,
│     test_scoring_input_validation.py, test_pinball_vs_oracle.py,
│     test_crps_interval_score.py, test_degeneracy_gate.py, test_coverage_metrics.py}
├── fakes/features/evaluation/{__init__.py, fake_scoring_backend.py}
├── contract/features/evaluation/{__init__.py, test_scoring_backend_contract.py}
└── architecture/{test_import_contracts.py, test_port_coverage_gate.py}   # MODIFICADOS
.importlinter                                                    # MODIFICADO
scripts/arch_baseline.toml                                       # MODIFICADO (09) e revertido (10)
pyproject.toml / uv.lock                                         # MODIFICADO (08)
docs/LAYOUT.md                                                   # MODIFICADO (§7)
```

Os testes unit ficam **planos** em `tests/unit/features/evaluation/`, como o
roadmap lista os três arquivos obrigatórios (concept D7).

### Rastreabilidade — concept §11 → Tasks

| # | Critério de aceitação (concept §11) | Tasks | Check objetivo |
|---|---|---|---|
| A1 | `CoverageSeries` ergue em cada caso C1/C2 (um teste por caso); `symmetric_pairs` e `guardrail_applied_rate` corretos em grade de 7 níveis; grade (0.02, …, 0.98) aceita | 02 | `uv run pytest tests/unit/features/evaluation/test_coverage_series.py -v` |
| A1b | Grade bruta cruzada: pinball, IS, ĉ e gate dão o valor de `guardrail_values` e ≠ do de `raw_values` | 04 (pinball), 05 (IS), 06 (gate), 07 (ĉ) | teste `test_*_scores_guardrail_not_raw` em `test_pinball_vs_oracle.py`, `test_crps_interval_score.py`, `test_degeneracy_gate.py`, `test_coverage_metrics.py` |
| A2 | Fixtures oficiais do sklearn (0.0333…, 0.3); P̄_G = \|y − x\|/2 no Dirac simétrico; pesos iguais; perda 0 no empate; média de `per_point_losses` = P̄_G | 04 | `uv run pytest tests/unit/features/evaluation/test_pinball_vs_oracle.py -v` |
| A3 | CRPS_Q = 2·P̄_G em toda série; = \|y − x\| no Dirac; `CRPS_Q_LABEL` no relatório | 05 | `uv run pytest tests/unit/features/evaluation/test_crps_interval_score.py -v -k crps` |
| A4 | IS_α nos três casos; (2/α)\|y − x\| no Dirac (50·\|y − x\| em α = 0.04); `mean_score` ≈ `mean_interval_score`; um `PairIntervalScore` por par com `miscoverage = 2·τ_l`, `nominal = 1 − 2·τ_l` | 05 | `uv run pytest tests/unit/features/evaluation/test_crps_interval_score.py -v -k interval` |
| A5 | ĉ com 1{y ≤ q̂}; PICP com [l ≤ y ≤ u]; MPIW em unidade de y; nominal exato (0.96, 0.9, 0.8, 0.5); PICP = ĉ(τ_u) − ĉ(τ_l) sem empates; C8 ergue | 07 | `uv run pytest tests/unit/features/evaluation/test_coverage_metrics.py -v` |
| A6 | Dirac marcado com `tolerance = 0.0`; fronteira diádica 0.25 marca / 0.125 não; colapso de par interno não marca a linha e aparece em `pair_collapse_rates`; `rate`; mesmo veredito com valores brutos em ordens diferentes; C3; `DegeneracyReport.__post_init__` ergue nos casos de C4 | 06 | `uv run pytest tests/unit/features/evaluation/test_degeneracy_gate.py -v` |
| A7 | Série mista (proper scores em T, cobertura em T − n_degenerate); 100 % degenerada → `applicable = False` com proper scores definidos; `CoverageReport.degeneracy` = gate da mesma série; máscaras diferentes → relatórios diferentes; `CoverageReport`/`PinballReport` mal-formados erguem (todos os ramos de C4); I10 (`mean_width` = `mpiw` com taxa 0, ≠ com uma linha de largura 0) | 04 (`PinballReport`), 07 (resto) | `uv run pytest tests/unit/features/evaluation/test_pinball_vs_oracle.py -v -k report` + `uv run pytest tests/unit/features/evaluation/test_coverage_metrics.py -v` |
| A8 | Suíte `[fake, sklearn, scoringrules]` concorda sob tolerância declarada nos três métodos (fixtures analíticas, grades aleatórias sem empate com seed declarada, Dirac); C7 ergue nas três pernas; `check_port_coverage.py` verde | 09 (fake), 10 (sklearn), 11 (scoringrules) | `uv run pytest tests/contract/features/evaluation/test_scoring_backend_contract.py -v -rs` com **zero** `SKIPPED` (as pernas reais não têm `skipif`) e os ids `fake`, `sklearn`, `scoringrules` presentes + `uv run python scripts/check_port_coverage.py` **sem** entrada `ScoringBackend` no baseline (a partir da 10) |
| A9 | Deps declaradas; `evaluation` em `hexagonal-layers`, `domain-purity`, `inward-only`, `bc-independence` (aresta comentada) e no contrato novo `evaluation-no-scoring-lib-leak` (em `_EXPECTED_CONTRACTS`, um caso real por módulo proibido); LAYOUT §7 (cinco slices, 21 arestas) | 01 (contratos + casos reais por contrato), 03 (`bc-independence` + LAYOUT + comentário do `.importlinter`), 08 (deps) | `uv run lint-imports` + `uv run pytest tests/architecture/test_import_contracts.py -v` — inclui casos reais que deixam `broken` **cada** contrato em que `evaluation` entra (`hexagonal-layers`, `inward-only`, `domain-purity`, `store-no-storage-leak`, `bc-independence`, e um por módulo do contrato novo) + `grep -n "scikit-learn>=1.9,<2.0" pyproject.toml` + `grep -n "scoringrules>=0.11,<0.12" pyproject.toml` + greps separados do LAYOUT (Task 03) |
| A10 | Nenhum serviço aceita mais de um horizonte nem exclui linhas: todo relatório traz `horizon` e `n_points = T` | 04, 05, 06, 07 | um assert `report.horizon == series.horizon and report.n_points == series.n_points` por serviço + `test_every_report_carries_horizon_and_all_points` em `test_coverage_metrics.py` |
| A11 | `make check` verde; cobertura ≥ 90 % global e por arquivo tocado; mypy strict e check_layout verdes | todas (T1/T3 por Task); gate §3 | `make check` + comando de cobertura por arquivo do §3 (falha com exit ≠ 0 se algum arquivo de `features/evaluation` < 90 %) |
| A12 | ADRs da Stage `accepted` (6.1.0001–0004 do concept + 6.1.0005 deste technical); DoD da 6.1 na redação já aplicada pela 5.5 | gate §3 (condicionado à 5.5 em `develop` — ver Pré-condições) | `test -z "$(grep -L '^status: accepted' docs/adr/6_1_000*.md)"` + após o rebase em `develop`: `grep -n "métricas de \*\*calibração\*\*" docs/roadmap.md` |

## 2. Tasks

> Faixa desta Stage: **11 Tasks** (estimativa do concept §12: ~9; +1 pela
> aresta `bc-independence` separada do scaffolding — a exceção só casa depois
> que o VO existe — e +1 pelas dependências como Task própria antes do port).

### Task 01 — Scaffolding do slice `evaluation` + contratos de pureza e `evaluation-no-scoring-lib-leak`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/__init__.py`
  - `src/financial_forecasting/features/evaluation/domain/__init__.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/__init__.py`
  - `src/financial_forecasting/features/evaluation/domain/services/__init__.py`
  - `src/financial_forecasting/features/evaluation/application/__init__.py`
  - `src/financial_forecasting/features/evaluation/adapters/__init__.py`
  - `tests/unit/features/evaluation/__init__.py`
- **Arquivos a modificar:**
  - `.importlinter`
  - `tests/architecture/test_import_contracts.py`
- **O que fazer:** criar os pacotes do slice (as três camadas existem desde já:
  `check_layout.py` regra 5 exige `domain/`, `application/`, `adapters/` em
  toda feature; `hexagonal-layers` exige `application` e `domain`) e
  registrá-lo nos gates **antes** de qualquer código:
  1. `hexagonal-layers`: `financial_forecasting.features.evaluation` em
     `containers`.
  2. `domain-purity`: `financial_forecasting.features.evaluation.domain` em
     `source_modules`.
  3. `inward-only`: `evaluation.application` e `evaluation.domain` em
     `source_modules`.
  4. `store-no-storage-leak`: `evaluation.application` e `evaluation.domain`
     em `source_modules` (decisão de detalhe do §1 — reforça a I11).
  5. Contrato novo `evaluation-no-scoring-lib-leak` (`type = forbidden`,
     padrão `modeling-no-statsforecast-leak`): sources
     `evaluation.{application,domain}`; forbidden `sklearn`, `scoringrules`,
     `numpy`, `scipy`; `allow_indirect_imports = False`; comentário citando
     concept 6.1 I11 / ADR 6.1.0001 item 6 e explicando que `domain-purity`
     já cobre `numpy` no domain — este contrato fecha a application e os
     outros três módulos.
  6. `test_import_contracts.py`: o contrato novo em `_EXPECTED_CONTRACTS`
     (comentário Stage 6.1 A9). Em `_REAL_VIOLATION_CASES`, casos reais que
     provam a matrícula do slice em **cada** contrato (lint-imports verde num
     slice vazio é vácuo):
     - `evaluation-no-scoring-lib-leak`: **um caso por módulo proibido**
       (`sklearn`, `scoringrules`, `numpy`, `scipy`), todos em
       `features/evaluation/application/_arch_audit_taint_<mod>.py` (o domain
       não discriminaria o `numpy`, já coberto por `domain-purity`);
     - `domain-purity`: `features/evaluation/domain/_arch_audit_taint.py`
       com `import pandas`;
     - `store-no-storage-leak`:
       `features/evaluation/application/_arch_audit_taint_pandas.py` com
       `import pandas` (a application não é coberta por `domain-purity`);
     - `hexagonal-layers`:
       `features/evaluation/domain/_arch_audit_taint_layers.py` com import de
       **runtime** `import financial_forecasting.features.evaluation.application`
       (domain → application; fora de `TYPE_CHECKING`, que o grimp ignora);
     - `inward-only`:
       `features/evaluation/application/_arch_audit_taint_inward.py`
       importando `Settings` de `shared.infrastructure.config.settings`.
- **Detalhes técnicos:** `bc-independence` **não** entra aqui (Task 03).
- **Critério de aceite:** `lint-imports` verde no repo limpo;
  `test_importlinter_declares_expected_contracts`,
  `test_every_forbidden_module_has_a_real_violation_case` e os **oito** casos
  novos de `test_production_contract_reacts_to_real_violation` verdes (cada
  um deixa o contrato esperado `broken`); `check_layout.py` verde com o slice
  novo.
- **Comando de verificação (T3 — tocou `.importlinter`):**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/test_import_contracts.py -v -k "evaluation or expected or forbidden_module"
  uv run python scripts/check_layout.py
  make check
  ```
- **Commit sugerido:** `chore(evaluation): scaffolding do slice e contratos de pureza com evaluation-no-scoring-lib-leak [6.1/task-01]`

---

### Task 02 — VO `CoverageSeries`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/coverage_series.py`
  - `tests/unit/features/evaluation/conftest.py`
  - `tests/unit/features/evaluation/test_coverage_series.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** VO frozen stdlib-only com a assinatura do concept §4
  (`horizon`, `levels`, `target_timestamps`, `forecasts`, `realized`;
  `n_points`, `symmetric_pairs`, `guardrail_applied_rate`, `scored_values`),
  importando `QuantileForecast` de
  `analytics_store.domain.value_objects.quantile_forecast` **em runtime** (a
  aresta que a Task 03 declara). Invariantes do ADR 6.1.0002 item 2 no
  `__post_init__`.
- **Detalhes técnicos:**
  - Ordem das checagens: vazios/comprimentos → `horizon ≥ 1` → `levels`
    (em (0, 1), estritamente crescentes, simétricos com
    `abs(levels[k] + levels[K-1-k] - 1) <= 1e-12`, `levels[0] < 0.5`) →
    timestamps estritamente crescentes (comparação de string ISO, formato
    único do silver) → por ponto: `forecast.levels == levels`, todo
    `guardrail_values` finito (`None` também ergue) e não-decrescente,
    `realized` finito. Mensagens de `ValueError` nomeiam o índice do ponto.
  - `symmetric_pairs` = pares `(levels[k], levels[K-1-k])` com
    `levels[k] < 0.5`; o nível central 0.5 (K ímpar) não forma par.
  - `guardrail_applied_rate` = fração de pontos com
    `forecast.guardrail_applied` (diagnóstico, doc §2.2).
  - `scored_values(i)` devolve `forecasts[i].guardrail_values` (I3 — nenhum
    caminho expõe `raw_values` para pontuação).
  - `conftest.py` **local do slice** (não compartilhado; precedente
    `tests/integration/features/modeling/conftest.py`): fixture-fábrica
    `make_series(...)` que monta `CoverageSeries` a partir de listas de
    grades, com `QuantileForecast.from_raw` por padrão e opção de construir o
    `QuantileForecast` direto (para A1b e para o caso C1 de valores
    cruzados), timestamps ISO sintéticos crescentes; usada pelas Tasks 04–07.
- **Critério de aceite (A1):** um teste por caso de C1 e C2 — comprimentos
  diferentes, T = 0, timestamp duplicado, timestamp fora de ordem, nível fora
  de (0, 1), `levels` fora de ordem, `forecast.levels ≠ levels`, grade
  assimétrica (> 1e-12), K = 1 {0.5}, `guardrail_values` decrescente num
  `QuantileForecast` construído direto, `horizon = 0`, `guardrail_values` com
  `nan`, `inf` e `None`, `realized` com `nan` e com `inf` — todos
  `ValueError`; `symmetric_pairs` e `guardrail_applied_rate` corretos numa
  grade de 7 níveis; grade (0.02, 0.05, 0.1, 0.5, 0.9, 0.95, 0.98) aceita
  apesar de `1 - 0.98 != 0.02`; frozen (`FrozenInstanceError`).
- **Comando de verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_coverage_series.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): VO CoverageSeries com invariantes de série alinhada por horizonte [6.1/task-02]`

---

### Task 03 — `evaluation` no `bc-independence` (aresta do `QuantileForecast`) + LAYOUT §7

- **Arquivos a modificar:**
  - `.importlinter`
  - `tests/architecture/test_import_contracts.py`
  - `docs/LAYOUT.md`
- **Arquivos a criar:** nenhum.
- **O que fazer (concept A9; ADR 6.1.0002 item 3; ADR 0.0.0053 item 3):**
  1. `bc-independence`: `financial_forecasting.features.evaluation` em
     `modules` e no `name` do contrato; nova linha em `ignore_imports`
     `financial_forecasting.features.evaluation.domain.value_objects.coverage_series -> financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast`
     com comentário "aresta de DADOS (VO do fornecedor) — ADR 0.0.0053 item 3 /
     ADR 6.1.0002 item 3". Total: 21 arestas. Atualizar também o bloco de
     comentário acima do contrato ("Os quatro slices estão no perímetro…",
     "(20 hoje)", "entre estes quatro slices") para **cinco** slices e
     **21** arestas, citando a entrada do `evaluation` na Stage 6.1.
  2. `test_import_contracts.py`: caso `bc-independence` com
     `features/evaluation/application/_arch_audit_taint_bc.py` importando
     `PredictionRow` de `analytics_store.domain.value_objects.prediction_row`
     (aresta **não** declarada — prova que o slice novo está dentro do
     perímetro; segue o precedente do caso do `modeling`).
  3. `docs/LAYOUT.md` §7 "Perímetro do gate hoje": "**quatro** slices" →
     "**cinco** slices" (lista com `evaluation`), "As 20 arestas" → "As 21
     arestas", citando a aresta nova `evaluation.domain → QuantileForecast`
     como dado (ADR 0.0.0053).
- **Detalhes técnicos:** `unmatched_ignore_imports_alerting = error` — a linha
  só casa porque o import de runtime da Task 02 existe. Nenhum serviço das
  Tasks 04–07 importa `QuantileForecast` (lêem `series.scored_values`); se
  importasse, nasceria aresta não declarada e o contrato reprovaria (efeito
  desejado).
- **Critério de aceite:** `lint-imports` verde; o caso novo deixa
  `bc-independence` `broken`; LAYOUT §7 e o comentário do `.importlinter`
  dizem cinco slices e 21 arestas.
- **Comando de verificação (T3 — tocou `.importlinter`):**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/test_import_contracts.py -v -k "bc-independence or bc_independence or expected"
  grep -n "\*\*cinco\*\* slices" docs/LAYOUT.md
  grep -Pzo "21\s+arestas" docs/LAYOUT.md
  grep -n "evaluation" docs/LAYOUT.md
  grep -n "21 hoje" .importlinter && ! grep -n "20 hoje" .importlinter
  make check
  ```
- **Commit sugerido:** `chore(evaluation): slice no bc-independence com a aresta do QuantileForecast e LAYOUT §7 [6.1/task-03]`

---

### Task 04 — Validador de entrada dos kernels + `PinballScore`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/scoring_input_validation.py`
  - `src/financial_forecasting/features/evaluation/domain/services/pinball_score.py`
  - `tests/unit/features/evaluation/test_scoring_input_validation.py`
  - `tests/unit/features/evaluation/test_pinball_vs_oracle.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  - **Validador único (C7; ADR 6.1.0001 item 1):** funções puras que erguem
    `ValueError`. Por ponto: `validate_level(level)` (em (0, 1)),
    `validate_miscoverage(miscoverage)` (em (0, 1)),
    `validate_grid_row(quantiles, levels)` (tamanhos iguais, cada nível em
    (0, 1)), `validate_interval_bounds(lower, upper)` (`lower ≤ upper`). Por
    série, compostas das anteriores: `validate_pinball_inputs(realized,
    quantiles, level)`, `validate_crps_inputs(realized, quantile_grid,
    levels)`, `validate_interval_inputs(realized, lower, upper, miscoverage)`
    (tamanhos iguais, sequência não-vazia — decisão de detalhe do §1). É o
    **único** validador: chamado pelos kernels por ponto e pelas funções de
    série do domínio (decisão de detalhe do §1), pelo fake (Task 09, via as
    funções de série) e pelos dois adapters (Tasks 10/11).
  - **`PinballScore`** (concept §4, doc §3.1; I4/I6): `pinball_loss` (ρ_τ,
    sem fator 2; chama `validate_level`), `mean_pinball` (valida a série,
    depois média de `pinball_loss`), `PinballReport` frozen com
    `__post_init__` (`len(per_level) == K ≥ 2`, `n_points ≥ 1`) e
    `PinballScore.per_point_losses` (L_t = média dos K ρ_τ do ponto, pesos
    iguais) / `score` (P̄_τ por nível via `mean_pinball` sobre a coluna do
    nível; P̄_G = média simples dos P̄_τ).
- **Detalhes técnicos:** todos os valores pontuados via
  `series.scored_values(i)` (I3). `score` usa **as mesmas** funções de série
  que o fake delegará (ADR 6.1.0001 item 4).
- **Critério de aceite:**
  - A2: `mean_pinball(realized=[1,2,3], quantiles=[0,2,3], level=0.1)` =
    0.03333… e `quantiles=[1,2,4]` → 0.3 (fixtures oficiais do sklearn,
    tolerância declarada); P̄_G = |y − x|/2 numa grade simétrica Dirac; pesos
    iguais (P̄_G = média aritmética dos P̄_τ); `pinball_loss` = 0 em y = q;
    média de `per_point_losses` = `grid_mean` (tolerância declarada).
  - A1b (pinball): série com `QuantileForecast` de raw cruzado → `score`
    confere com o valor calculado à mão sobre `guardrail_values` e difere do
    calculado sobre `raw_values`.
  - A7 (parte): `PinballReport` com `per_level` de tamanho errado (0 ou 1
    nível) ou `n_points = 0` ergue.
  - A10 (parte): `report.horizon == series.horizon`,
    `report.n_points == series.n_points`.
  - C7 (domínio): cada ramo do validador ergue, um teste por ramo;
    `pinball_loss(level=0.0)` e `(level=1.5)` erguem (kernel por ponto);
    `mean_pinball` com sequências vazias ergue.
- **Comando de verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_scoring_input_validation.py tests/unit/features/evaluation/test_pinball_vs_oracle.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): PinballScore e validador único de entrada dos kernels [6.1/task-04]`

---

### Task 05 — `CrpsScore` e `IntervalScore`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/crps_score.py`
  - `src/financial_forecasting/features/evaluation/domain/services/interval_score.py`
  - `tests/unit/features/evaluation/test_crps_interval_score.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4; doc §3.2, §3.3; I4/I5/I7):**
  - `CrpsScore`: `CRPS_Q_LABEL`; `crps_quantile` = (2/K)·Σ_k ρ_{τ_k} (chama
    `validate_grid_row`); `mean_crps_quantile` (valida a série, média de
    `crps_quantile`); `CrpsReport`; `per_point`/`score`.
  - `IntervalScore`: `interval_score` (GR 2007 Eq. (43): `(u − l) +
    (2/α)(l − y)·1{y < l} + (2/α)(y − u)·1{y > u}`; chama
    `validate_miscoverage` e `validate_interval_bounds`);
    `mean_interval_score` (valida a série, média); `PairIntervalScore` com
    `mean_score` definido como a soma dos três termos médios;
    `IntervalScoreReport` com `__post_init__` (`len(per_pair) ≥ 1`,
    `n_points ≥ 1`); `score` monta um `PairIntervalScore` por
    `series.symmetric_pairs`, com `miscoverage = 2·τ_l` e
    `nominal = 1 − 2·τ_l` (nunca `1 − (τ_u − τ_l)`), médias sobre **todas**
    as linhas.
- **Critério de aceite:**
  - A3: `CrpsScore.score(s).crps_q` = `2 * PinballScore.score(s).grid_mean`
    (tolerância declarada) em série aleatória sem empate e em série mista;
    = |y − x| no Dirac com grade simétrica; `report.label == CRPS_Q_LABEL`;
    média de `CrpsScore.per_point(s)` = `crps_q` (tolerância declarada).
  - A4: IS_α = (2/α)[ρ_{α/2}(y − l) + ρ_{1−α/2}(y − u)] nos três casos
    (y < l; l ≤ y ≤ u com y = l e y = u inclusos; y > u); Dirac com
    α = 0.04 → 50·|y − x|; `mean_score` ≈ `mean_interval_score` sob
    tolerância declarada; um `PairIntervalScore` por par;
    `miscoverage`/`nominal` por igualdade exata de float para (0.05, 0.95) →
    0.1/0.9; `IntervalScoreReport` com `per_pair = ()` ou `n_points = 0` ergue (um teste por ramo).
  - C7 (kernels por ponto): `crps_quantile` com `len(quantiles) ≠
    len(levels)` ou nível fora de (0, 1) ergue; `interval_score` com
    `miscoverage ∉ (0, 1)` ou `lower > upper` ergue; `mean_*` com sequência
    vazia ergue.
  - A1b (IS): mesma fixture cruzada da Task 04 — valores de
    `guardrail_values`, ≠ dos de `raw_values`.
  - A10 (parte): `horizon`/`n_points` nos dois relatórios.
- **Comando de verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_crps_interval_score.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): CrpsScore (2×pinball da grade) e IntervalScore por par simétrico [6.1/task-05]`

---

### Task 06 — `DegeneracyGate`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/degeneracy_gate.py`
  - `tests/unit/features/evaluation/test_degeneracy_gate.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4; I8/I9; ADR 0.0.0011; ADR 6.1.0003):**
  `DegeneracyReport` frozen com `__post_init__` (máscara e timestamps com
  tamanho `n_points`, `n_degenerate == sum(degenerate)`,
  `rate == n_degenerate / n_points`) e `DegeneracyGate.evaluate(series, *,
  tolerance)` — `tolerance` keyword-only **sem default**: valida `tolerance`
  (finita, ≥ 0 — C3); linha degenerada ⇔ `max − min` de `scored_values(i)`
  ≤ `tolerance`; `pair_collapse_rates` por par simétrico = fração de linhas
  **não-degeneradas** com `q_u − q_l ≤ tolerance`, `None` se não há linha
  não-degenerada (C6). Nunca reordena nem altera valores; nunca exclui linha.
- **Critério de aceite (A6):**
  - Dirac marcado com `tolerance = 0.0`; grade de 0.25 a 0.5 (amplitude
    0.25, diádica): `tolerance = 0.25` marca, `0.125` não; colapso só de um
    par interno não marca a linha e aparece em `pair_collapse_rates`; `rate`
    correta numa série mista; mesmo veredito para duas previsões com os
    mesmos valores brutos em ordens diferentes (via `from_raw`);
    `tolerance` negativa, `nan` e `inf` erguem (C3); série 100 % degenerada →
    `pair_collapse_rates` com `None` (C6).
  - Rastro de auditoria: `report.target_timestamps == series.target_timestamps`
    e `report.tolerance == tolerance`.
  - C4 — `DegeneracyReport` à mão ergue em cada ramo, um teste por ramo:
    máscara com tamanho ≠ `n_points`; `target_timestamps` com tamanho ≠
    `n_points`; `n_degenerate` ≠ soma da máscara; `rate` inconsistente.
  - `inspect.signature(DegeneracyGate.evaluate).parameters["tolerance"]`:
    keyword-only e `default is inspect.Parameter.empty` (ADR 6.1.0003 — sem
    default).
  - A1b (gate): fixture cruzada em que o par de `raw_values` teria
    `q_u − q_l ≤ tolerance` (valores invertidos) e o de `guardrail_values`
    não → `pair_collapse_rates` reflete `guardrail_values`; o veredito por
    linha (amplitude) é o mesmo nos dois vetores (I9).
  - A10 (parte): `horizon`/`n_points`.
- **Comando de verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_degeneracy_gate.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): DegeneracyGate com tolerância absoluta e taxa sempre reportada [6.1/task-06]`

---

### Task 07 — `CoverageMetrics`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/coverage_metrics.py`
  - `tests/unit/features/evaluation/test_coverage_metrics.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4; doc §4.1–§4.3, §5.3; I6/I7/I8/I10; ADR 6.1.0004):**
  `PairCoverage`; `CoverageReport` frozen com o `__post_init__` do concept
  §4; `CoverageMetrics.evaluate(series, *, tolerance)` roda
  `DegeneracyGate.evaluate(series, tolerance=tolerance)` internamente e
  calcula, **só nas linhas não-degeneradas**: ĉ(τ_k) = média de
  1{y ≤ q̂_{τ_k}}, PICP = média de 1{l ≤ y ≤ u}, MPIW = média de u − l,
  `nominal = 1 − 2·τ_l`; `applicable = False` com `per_level`/`per_pair`
  vazios quando `n_evaluated == 0`. `interval_widths(series, *, tolerance,
  pair)` devolve as larguras por linha não-degenerada; `pair` fora de
  `series.symmetric_pairs` (igualdade exata) → `ValueError` (C8). `tolerance`
  keyword-only sem default nos dois métodos.
- **Critério de aceite:**
  - A5: empate y = q̂ conta como coberto em ĉ; y = l e y = u contam como
    dentro no PICP; MPIW em unidade de y; nominal por igualdade exata de
    float — (0.02, 0.98) → 0.96, (0.05, 0.95) → 0.9, (0.1, 0.9) → 0.8,
    (0.25, 0.75) → 0.5; PICP = ĉ(τ_u) − ĉ(τ_l) em fixture sem empates; C8
    ergue.
  - `interval_widths` (caminho feliz): série mista → exatamente
    `T − n_degenerate` larguras, iguais a `u − l` das linhas não-degeneradas
    na ordem da série, com média = `mpiw` do mesmo par (tolerância
    declarada).
  - A7: série mista — `PinballScore`/`CrpsScore`/`IntervalScore` com
    `n_points = T` e `CoverageReport.n_evaluated = T − n_degenerate`; série
    100 % degenerada → `applicable = False`, `per_level == ()`,
    `per_pair == ()` e proper scores finitos (C5; caso dos baselines
    pontuais); `CoverageReport.degeneracy ==
    DegeneracyGate.evaluate(series, tolerance=t)`; duas séries com mesmo T e
    horizonte e máscaras diferentes → relatórios diferentes (C4).
  - C4 — `CoverageReport` à mão ergue em cada ramo do `__post_init__`, um
    teste por ramo: `degeneracy.n_points ≠ n_points`; `degeneracy.horizon ≠
    horizon`; `n_evaluated ≠ n_points − degeneracy.n_degenerate`;
    `applicable = True` com `n_evaluated = 0`; `applicable = False` com
    `n_evaluated > 0`; `per_level` preenchido com `applicable = False`;
    `per_pair` preenchido com `applicable = False`; `per_level` com tamanho
    ≠ K; `per_pair` com tamanho ≠ nº de pares simétricos.
  - `inspect.signature`: `tolerance` keyword-only e sem default em
    `CoverageMetrics.evaluate` e `CoverageMetrics.interval_widths`.
  - I10: taxa 0 → `mean_width` do `IntervalScore` ≈ `mpiw` do mesmo par
    (tolerância declarada); série com uma linha degenerada de largura 0 →
    diferentes.
  - A1b (ĉ): fixture cruzada — ĉ sobre `guardrail_values`, ≠ do raw.
  - A10: `test_every_report_carries_horizon_and_all_points` — os cinco
    relatórios de uma mesma série trazem `horizon` e `n_points = T`.
- **Comando de verificação (T1):**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_coverage_metrics.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): CoverageMetrics com nominal dinâmico e máscara recomputada da própria série [6.1/task-07]`

---

### Task 08 — Dependências `scikit-learn` e `scoringrules`

- **Arquivos a modificar:**
  - `pyproject.toml`
  - `uv.lock`
- **Arquivos a criar:** nenhum.
- **O que fazer (concept §1; ADR 6.1.0001 item 6):** em `dependencies`, bloco
  comentado no padrão dos anteriores (Stage 6.1 / ADR 6.1.0001; vivem SÓ em
  `features/evaluation/adapters/out/scoring/`; gate
  `evaluation-no-scoring-lib-leak`; em `dependencies` e não num extra porque
  as pernas reais da suíte rodam no CI; pin por minor):
  `"scikit-learn>=1.9,<2.0"` e `"scoringrules>=0.11,<0.12"`. `uv lock` e
  `uv sync --inexact` no container. Vem **antes** do port (Task 09) para que
  a janela port-sem-adapter seja um commit só (ADR 6.1.0005).
- **Detalhes técnicos:** medir a árvore transitiva nova com
  `git diff uv.lock` (pacotes adicionados e versões) e registrar o resultado
  em §7; se `scoringrules` puxar `numba`/`jax` como obrigatória, `[decision]`
  em §7 com o tamanho medido antes de seguir (risco do concept §10).
- **Critério de aceite:** `uv lock` resolve; `import sklearn, scoringrules`
  imprime 1.9.x e 0.11.x; `make check` verde.
- **Comando de verificação (T3 — tocou dependência):**
  ```bash
  grep -n "scikit-learn>=1.9,<2.0" pyproject.toml && grep -n "scoringrules>=0.11,<0.12" pyproject.toml
  uv run python -c "import sklearn, scoringrules; print(sklearn.__version__, scoringrules.__version__)"
  make check
  ```
- **Commit sugerido:** `build(evaluation): scikit-learn e scoringrules como dependências dos adapters de scoring [6.1/task-08]`

---

### Task 09 — Port `ScoringBackend` + `FakeScoringBackend` + suíte de contrato (perna `fake`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/__init__.py`
  - `src/financial_forecasting/features/evaluation/application/ports/out/__init__.py`
  - `src/financial_forecasting/features/evaluation/application/ports/out/scoring_backend.py`
  - `tests/fakes/features/evaluation/__init__.py`
  - `tests/fakes/features/evaluation/fake_scoring_backend.py`
  - `tests/contract/features/evaluation/__init__.py`
  - `tests/contract/features/evaluation/test_scoring_backend_contract.py`
- **Arquivos a modificar (ADR 6.1.0005):**
  - `scripts/arch_baseline.toml` — entrada transitória `ScoringBackend`;
  - `tests/architecture/test_port_coverage_gate.py` —
    `test_real_repo_violations_are_exactly_the_declared_baseline` passa a
    esperar `["Hasher", "ScoringBackend"]`, com comentário citando o ADR
    6.1.0005 e a Task 10 que reverte.
- **O que fazer (concept §4; ADR 6.1.0001 itens 2 e 4):**
  - Port: `ScoringBackend(Protocol)` com a **assinatura literal do concept
    §4** — `mean_pinball(self, *, realized: Sequence[float], quantiles:
    Sequence[float], level: float) -> float`,
    `mean_crps_quantile(self, *, realized: Sequence[float], quantile_grid:
    Sequence[Sequence[float]], levels: Sequence[float]) -> float`,
    `mean_interval_score(self, *, realized: Sequence[float], lower:
    Sequence[float], upper: Sequence[float], miscoverage: float) -> float`;
    parâmetro `miscoverage` (nunca `alpha`); docstring com a convenção de cada
    parâmetro e a exigência C7.
  - Fake `FakeScoringBackend`: cada método **delega** à função de série do
    domínio (`mean_pinball`, `mean_crps_quantile`, `mean_interval_score`) —
    sem média própria (o oráculo cobre o código de registro).
  - Suíte de contrato parametrizada por factory, ids `["fake"]` nesta Task
    (Tasks 10/11 acrescentam `"sklearn"` e `"scoringrules"`, **sem**
    `skipif` — as libs são dependências do projeto desde a Task 08): fixtures
    analíticas (sklearn oficiais, Dirac com CRPS_Q = |y − x| e
    IS = (2/α)|y − x|, os três casos do IS, um empate y = q), grades
    aleatórias sem empate (`random.Random(<seed declarada>)`, K = 7 simétrico,
    T ≈ 200) comparadas **contra o domínio** com tolerância declarada no
    módulo (`_REL_TOL`, `_ABS_TOL` da ordem de 1e-12), e C7 em cada método
    (nível/miscobertura fora de (0, 1), tamanhos diferentes, `lower > upper`,
    sequência vazia) → `ValueError`.
  - Baseline: `[[port_coverage.allow]]` `key = "ScoringBackend"`, `motivo`
    citando ADR 6.1.0005 ("port criado uma Task antes do primeiro adapter
    real; removido na 6.1 Task 10"), `issue = 77`.
- **Critério de aceite:** suíte verde no id `fake`; `check_port_coverage.py`
  e `check_fake_parity.py` verdes (a entrada nova tolerada, nenhuma morta);
  `tests/architecture/test_port_coverage_gate.py` verde; `lint-imports` verde
  (port importa só stdlib).
- **Comando de verificação (T3 — tocou `scripts/arch_baseline.toml` e `tests/architecture/`):**
  ```bash
  uv run pytest tests/contract/features/evaluation/test_scoring_backend_contract.py -v
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  uv run python scripts/check_fake_parity.py
  make check
  ```
- **Commit sugerido:** `feat(evaluation): port ScoringBackend com fake e suíte de contrato [6.1/task-09]`

---

### Task 10 — Adapter `SklearnScoring` + perna `sklearn` do contrato (reverte o baseline)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/__init__.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/scoring/__init__.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/scoring/sklearn_scoring.py`
- **Arquivos a modificar:**
  - `tests/contract/features/evaluation/test_scoring_backend_contract.py`
    (factory `"sklearn"`)
  - `scripts/arch_baseline.toml` — remove a entrada `ScoringBackend`
    (ADR 6.1.0005);
  - `tests/architecture/test_port_coverage_gate.py` — volta a
    `["Hasher"]` e remove o comentário da janela (ADR 6.1.0005).
- **O que fazer (ADR 6.1.0001 item 3):** classe pública `SklearnScoring`
  cujo docstring declara que satisfaz o port `ScoringBackend` (heurística do
  `check_port_coverage.py`). Cada método chama primeiro o validador de
  domínio da Task 04 (C7 idêntico ao do domínio) e então:
  `mean_pinball` = `sklearn.metrics.mean_pinball_loss(realized, quantiles,
  alpha=level)` (`alpha` = **nível**); `mean_crps_quantile` = 2 × média sobre
  k de `mean_pinball_loss(realized, coluna_k, alpha=τ_k)` (identidade doc
  §3.2); `mean_interval_score` = (2/α)·[`mean_pinball_loss(realized, lower,
  alpha=α/2)` + `mean_pinball_loss(realized, upper, alpha=1−α/2)`]
  (identidade doc §3.3, Bracher et al. 2021 App. A Eq. (5)). Retorno
  convertido para `float` nativo.
- **Detalhes técnicos:** nenhuma média ou fórmula copiada do domínio (o
  `check_fake_parity.py` compara fake × adapter; aqui a rota é a identidade
  via sklearn).
- **Critério de aceite:** suíte verde nos ids `fake` e `sklearn` (fixtures
  analíticas, aleatórias, Dirac e C7), zero `SKIPPED`;
  `check_port_coverage.py` verde **sem** a entrada `ScoringBackend` no
  baseline (entrada morta reprovaria); `test_port_coverage_gate.py` verde com
  `["Hasher"]`; `lint-imports` verde (sklearn só no adapter).
- **Comando de verificação (T3 — tocou `scripts/arch_baseline.toml` e `tests/architecture/`):**
  ```bash
  uv run pytest tests/contract/features/evaluation/test_scoring_backend_contract.py -v -rs
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  grep -n "ScoringBackend" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; test $? -eq 1
  make check
  ```
- **Commit sugerido:** `feat(evaluation): adapter SklearnScoring pelas identidades do doc e perna sklearn do contrato [6.1/task-10]`

---

### Task 11 — Adapter `ScoringrulesBackend` + perna `scoringrules` do contrato

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/scoring/scoringrules_backend.py`
- **Arquivos a modificar:**
  - `tests/contract/features/evaluation/test_scoring_backend_contract.py`
    (factory `"scoringrules"`)
- **O que fazer (ADR 6.1.0001 item 3; doc §11.3):** classe pública
  `ScoringrulesBackend` (docstring: satisfaz `ScoringBackend`). Cada método
  chama o validador de domínio e então a função nativa com **backend fixado
  explicitamente** em toda chamada (constante de módulo comentada, ex.
  `_BACKEND = "numpy"` — doc §11.3: o default muda quando numba está
  instalado): `quantile_score(obs, fct, alpha=level)` → média;
  `crps_quantile(obs, fct[T×K], alpha=levels)` → média;
  `interval_score(obs, lower, upper, alpha=miscoverage)` (`alpha` =
  **miscobertura**; desigualdades estritas, compatíveis com o domínio porque
  y = l e y = u não pagam penalidade nas duas definições) → média. Retorno
  `float` nativo.
- **Critério de aceite (A8 fechado):** suíte verde nos ids `fake`, `sklearn`
  e `scoringrules`, **zero** `SKIPPED` no relatório `-rs`; C7 ergue nas três
  pernas; `check_port_coverage.py` e `check_fake_parity.py` verdes.
- **Comando de verificação (T1):**
  ```bash
  set -o pipefail; uv run pytest tests/contract/features/evaluation/test_scoring_backend_contract.py -v -rs | tee /tmp/contract.txt
  ! grep -q "SKIPPED" /tmp/contract.txt
  grep -q "\[scoringrules" /tmp/contract.txt && grep -q "\[sklearn" /tmp/contract.txt && grep -q "\[fake" /tmp/contract.txt
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): adapter ScoringrulesBackend com backend fixado e perna scoringrules do contrato [6.1/task-11]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 6.1: complete` e ser mergeada em `develop`.

### Verificações automatizadas
```bash
make check                 # ruff + mypy strict + check_layout + lint-imports + fake-parity + port-coverage + docs-check + testes (cov >= 90%)

# A11 — cobertura por arquivo do slice (falha com exit 1 se algum arquivo < 90%)
uv run pytest --cov=financial_forecasting --cov-report=json:/tmp/cov-6.1.json -q
uv run python -c "import json,sys; d=json.load(open('/tmp/cov-6.1.json'))['files']; bad={f:v['summary']['percent_covered'] for f,v in d.items() if 'features/evaluation/' in f.replace(chr(92),'/') and v['summary']['percent_covered']<90}; ev=[f for f in d if 'features/evaluation/' in f.replace(chr(92),'/')]; print(len(ev),'arquivos do slice; abaixo de 90%:',bad); sys.exit(1 if bad or not ev else 0)"

# A8 — três pernas, zero skips
set -o pipefail; uv run pytest tests/contract/features/evaluation/test_scoring_backend_contract.py -v -rs | tee /tmp/contract-6.1.txt
! grep -q "SKIPPED" /tmp/contract-6.1.txt

python scripts/check_technical_postexec.py docs/stages/6.1-scoring-and-calibration-metrics/technical.md
test -z "$(grep -L '^status: accepted' docs/adr/6_1_000*.md)"
grep -n "ScoringBackend" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py ; test $? -eq 1

# A12 — só depois da 5.5 em develop e do rebase (ver Pré-condições)
grep -n "métricas de \*\*calibração\*\*" docs/roadmap.md
```

(A saída dos comandos de A11 e A8 é colada no PR.)

### Verificações funcionais
- [ ] Para uma `CoverageSeries` sintética mista (linhas degeneradas e não
      degeneradas), os cinco serviços devolvem relatórios com o mesmo
      `horizon` e `n_points = T`, proper scores sobre T linhas e cobertura
      sobre T − n_degenerate (A7/A10).
- [ ] A suíte de contrato prova domínio ≡ sklearn ≡ scoringrules nos três
      métodos sob tolerância declarada, sem perna pulada (A8).
- [ ] Sem verificação end-to-end com dado real: a Stage não persiste nem
      expõe métrica (concept D6); o e2e sobre o silver é da 6.4.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com o seu gate (T1/T3) verde.
- [ ] `make check` verde no branch.
- [ ] Cobertura ≥ 90 % global e por arquivo do slice, pelo comando acima
      (A11), saída colada.
- [ ] `scripts/arch_baseline.toml` e `test_port_coverage_gate.py` sem
      `ScoringBackend` (ADR 6.1.0005).
- [ ] §7 reflete a execução real (inclusive a árvore transitiva medida na
      Task 08 e as três decisões de detalhe do §1).
- [ ] **A12:** o DoD da 6.1 no `roadmap.md` tem a redação da 5.5 ("métricas
      de **calibração** da linha") depois do rebase em `develop`. A 6.1 não
      edita o DoD; se a 5.5 ainda não estiver em `develop`, `[finding]` em §7
      e o A12 fica declarado como pendente dessa condição no PR.
- [ ] Commit final `stage 6.1: complete` aplicado (pós-auditoria).
- [ ] `roadmap.md`: Stage 6.1 marcada `done`, `updated_at` e
      `last_reviewed_at` no fechamento.
- [ ] ADRs 6.1.0001–0005 em `accepted`.
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

```
Task 01 (scaffolding + contratos) ─► Task 02 (CoverageSeries) ─► Task 03 (bc-independence + LAYOUT)
                                            │
                                            ├─► Task 04 (validador + PinballScore) ─► Task 05 (CRPS_Q + IS)
                                            └─► Task 06 (DegeneracyGate)
Tasks 04, 05, 06 ─► Task 07 (CoverageMetrics; testes A7/I10 usam os outros serviços)
Tasks 04, 05 ─► Task 08 (deps) ─► Task 09 (port + fake + suíte; baseline +) ─► Task 10 (sklearn; baseline −) ─► Task 11 (scoringrules)
```

- A Task 03 vem logo depois da 02 porque a exceção da aresta só casa com um
  import existente (`unmatched_ignore_imports_alerting = error`).
- A Task 07 depende das 04–06: os testes A7/I10 comparam os relatórios de
  proper score e o `DegeneracyReport` com o `CoverageReport`.
- A Task 08 (deps) precede o port para que a Task 10 venha imediatamente
  depois da 09: a entrada de baseline vive um commit só (ADR 6.1.0005).
- A Task 09 depende das 04 e 05: o fake delega às funções de série e ao
  validador; as Tasks 10/11 dependem da 08 (libs instaladas).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `scoringrules` puxar dependência pesada obrigatória (numba/jax) | Medir na Task 08 (`git diff uv.lock`); se vier algo novo e pesado, `[decision]` em §7 com o tamanho; o backend fixado no adapter mantém o resultado determinístico |
| grimp não resolver `scoringrules` não instalado na Task 01 (o caso de violação real não quebra o contrato) | Mover o módulo `scoringrules` do contrato e o seu caso para a Task 08 (já instalado), registrando `[deviation]` em §7 |
| Caso `hexagonal-layers` com `import <pacote application>` não gerar aresta no grimp | Importar um nome concreto do pacote (ex.: `from financial_forecasting.features.evaluation import application` ou um módulo-probe criado no próprio caso, como o caso `shared-no-features`), registrando `[deviation]` |
| `sklearn`/`scoringrules` somarem em ordem diferente e passarem da tolerância 1e-12 | Afrouxar para no máximo 1e-10 relativo, declarado no módulo de teste, com `[deviation]` em §7; nunca tolerância implícita |
| `scoringrules` exigir outra forma de array (ex.: `alpha` escalar × vetor, `fct` T×K) | Ajuste local no adapter (reshape), coberto pela suíte; o port não muda |
| `check_port_coverage.py` não reconhecer um adapter (docstring sem o nome do port) | Citar `ScoringBackend` no docstring do módulo/classe, como todos os adapters do repo |
| `check_fake_parity.py` acusar bloco idêntico fake × adapter | Não copiar lógica: o fake delega ao domínio; a validação mora só no validador de domínio (ADR 6.1.0001 item 1) |
| Serviço importar `QuantileForecast` e criar aresta nova | O `bc-independence` reprova (efeito desejado); os serviços leem via `series.scored_values` e não importam a classe. A única aresta é o import de runtime do VO (Task 02), declarado na Task 03 |
| Cobertura < 90 % nos ramos de erro dos `__post_init__` | Um teste por ramo (A6/A7/C1–C8); `# pragma: no cover` só comentado e para ramo comprovadamente inalcançável |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo, contratos (§4), invariantes (§5),
  erros (§6), decisões D1–D8 (§7), integrações (§8), critérios (§11).
- ADRs desta Stage:
  [`6.1.0001`](../../adr/6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md),
  [`6.1.0002`](../../adr/6_1_0002-coverage-series-aligned-input-vo.md),
  [`6.1.0003`](../../adr/6_1_0003-degeneracy-absolute-spread-tolerance.md),
  [`6.1.0004`](../../adr/6_1_0004-coverage-metrics-recomputes-degeneracy-mask.md),
  [`6.1.0005`](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md);
  relacionados: [`0.0.0009`](../../adr/0_0_0009-pinball-primary-crps-complementary.md),
  [`0.0.0011`](../../adr/0_0_0011-preregistration-invariants-and-h1-gate.md),
  [`0.0.0020`](../../adr/0_0_0020-statistics-in-domain-over-value-objects.md),
  [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md),
  [`0.0.0053`](../../adr/0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [`0.0.0055`](../../adr/0_0_0055-tiered-quality-gates.md),
  [`4.3.0002`](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md).
- Doc de domínio: [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md).
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7; [`../../PIPELINE.md`](../../PIPELINE.md) §4.3;
  [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) §Gates em camadas.
- Skills: `task-ordering-hex`, `hex-arch-python`, `ddd-tactical-patterns`,
  `pytest-with-fakes`, `import-linter-rules`.
- Stage de referência: [`../5.2-baselines-naive-statistical/technical.md`](../5.2-baselines-naive-statistical/technical.md).

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a Fase 4. Apenas esta seção é editável após
> `status: done`. Cada entrada carrega data + autor.

### 2026-09-28 — [decision] Task 01: `store-no-storage-leak` também cobre `evaluation.{application,domain}` — Claude (Opus 5.5)
**Contexto:** o concept A9 lista os contratos em que `evaluation` entra
(`hexagonal-layers`, `domain-purity`, `inward-only`, `bc-independence` e o novo
`evaluation-no-scoring-lib-leak`); nenhum deles fecha `pandas`/`pyarrow`/`duckdb`/
`pandera` na `application` do slice.
**Razão:** decisão de detalhe planejada no §1 — o slice entra também em
`store-no-storage-leak`, reforçando a I11 ("`evaluation.domain` e
`evaluation.application` importam só stdlib + o VO do 4.3"). Todos os outros slices
já estão nesse contrato. Provado pelo caso
`store-no-storage-leak:evaluation-application-imports-pandas`. Efeito colateral de
numeração: o contrato novo é o nº 13 do `.importlinter` e o `bc-independence` passou
a nº 14 (só o rótulo do comentário; nenhum doc cita o número).

### 2026-09-28 — [decision] Task 02: `CoverageSeries` exige `len(guardrail_values) == len(levels)` por ponto — Claude (Opus 5.5)
**Contexto:** o ADR 6.1.0002 item 2 lista `forecast.levels == levels` por ponto, mas
não o tamanho do vetor de valores. `QuantileForecast` é dataclass pública sem
`__post_init__`: construído direto (fora do `from_raw`), pode ter `levels` corretos e
`guardrail_values` com outro tamanho — e então `zip` com a grade truncaria em silêncio.
**Razão:** a série é "alinhada 1:1" (ADR 6.1.0002 item 2; concept I2), o que inclui o
alinhamento valor↔nível; a checagem ergue `ValueError` nomeando o ponto, coberta por
`test_guardrail_values_misaligned_with_levels_raise`. Reversível e sem efeito sobre
séries montadas pelo `from_raw` (que já garante o tamanho).

### 2026-09-28 — [deviation] Task 01: caso real de `evaluation.domain` no `evaluation-no-scoring-lib-leak` — Claude (Opus 5.5)
**Contexto:** a Task 01 especificou os quatro casos do contrato novo só na
`application`. O Checkpoint C do bloco 1 apontou que nada provava a matrícula de
`evaluation.domain` nele: `domain-purity` não proíbe `sklearn`/`scoringrules`/`scipy`
e o `check_layout.py` também não — tirar o domain de `source_modules` passaria verde.
**Razão:** lacuna de especificação fechada em `fix(...) [6.1/task-01-fix]`: caso
`evaluation-no-scoring-lib-leak:evaluation-domain-imports-sklearn`
(`features/evaluation/domain/_arch_audit_taint_sklearn.py`, `import sklearn`) e o
comentário do contrato no `.importlinter` corrigido ("todos na application" deixou de
ser verdade). Não muda contrato nem critério; só reforça a prova do A9.

### 2026-09-28 — [decision] Task 06: `DegeneracyReport` exige `n_points ≥ 1`; `tolerance` não-numérica ergue — Claude (Opus 5.5)
**Contexto:** o `__post_init__` do concept §4 checa máscara/timestamps com tamanho
`n_points`, `n_degenerate` e `rate == n_degenerate / n_points`, mas não `n_points ≥ 1`;
com `n_points = 0` a checagem de `rate` dividiria por zero (`ZeroDivisionError`, não o
`ValueError` do C4). O C3 fala em tolerância "negativa ou não-finita".
**Razão:** `n_points ≥ 1` entra como primeira checagem do `__post_init__` (mesma
pré-condição de `PinballReport`/`IntervalScoreReport`; uma série tem T ≥ 1), com teste
próprio. No C3, `None` e `bool` também erguem `ValueError` com a mesma mensagem (não
são número finito; `bool` é subclasse de `int`, mesma postura do `_is_finite_number`
do 4.3). Reversível, sem efeito sobre relatórios produzidos pelo gate.

### 2026-09-28 — [decision] Task 02 (fix pós-Checkpoint C do bloco 2): `CoverageSeries.symmetric_pair_indices` — Claude (Opus 5.5)
**Contexto:** a regra par → colunas do vetor pontuado (`levels.index(τ_l)`,
`levels.index(τ_u)`) estava repetida em `IntervalScore.score` e no
`DegeneracyGate`, e a Task 07 (`CoverageMetrics`) a repetiria uma terceira vez.
**Razão:** a regra é da grade, logo do VO (ADR 6.1.0002 item 4: valores derivados no
VO, não no serviço). `symmetric_pair_indices` devolve `(k, K-1-k)` alinhado 1:1 com
`symmetric_pairs` (que passa a derivar dele); IS e gate o consomem e a Task 07 também
consumirá. Propriedade nova; nada do contrato do concept §4 muda.

### 2026-09-28 — [deviation] Task 05: `IntervalScore.score` decompõe a média em vez de delegar a `mean_interval_score` — Claude (Opus 5.5)
**Contexto:** o ADR 6.1.0001 itens 1/4 pede que os serviços agreguem pelas **mesmas**
funções de série que o fake delega (`PinballScore` usa `mean_pinball`, `CrpsScore`
usa `mean_crps_quantile`). A I5 do concept, porém, **define** `mean_score` como
`mean_width + mean_lower_penalty + mean_upper_penalty` — os três termos médios do
`PairIntervalScore` —, o que `mean_interval_score` (um escalar) não entrega. O
Checkpoint C do bloco 2 apontou a divergência.
**Razão:** a decomposição da I5 fica; o que o ADR protege é garantido de outro modo.
(1) A entrada de cada par passa pelo **mesmo** validador único
(`validate_interval_inputs`) que `mean_interval_score` usa (C7). (2) A ponte
`mean_score ≈ mean_interval_score` (tolerância declarada 1e-12) é testada em série
aleatória sem empate, em série mista com linhas degeneradas e na fixture cruzada do
A1b — o oráculo de biblioteca, que cobre `mean_interval_score`, fica ligado ao
relatório por essa identidade. Além disso, o `PairIntervalScore` passa a erguer se
`miscoverage != 2·τ_l` ou `nominal != 1 - miscoverage` (I5/I7 por construção) e o
`CrpsReport` se `n_points < 1` ou `label != CRPS_Q_LABEL` (I4 por construção).

<!-- END: post-execution -->
