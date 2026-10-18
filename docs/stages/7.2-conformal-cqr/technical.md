---
title: Technical — Stage 7.2 — Conformal CQR assimétrico como benchmark (calibrador no domain do inference, oráculos MAPIE e NexCP, cobertura no evaluation, integração no gold, emenda cega r2)
description: Plano de execução da Stage 7.2 em 23 Tasks inside-out (1 Task = 1 commit) — política de reprodução no domain, calib dedicado, split-CQR e NexCP em aritmética exata com fixture dos autores, contrato inference-no-mapie-leak, port e adapter do oráculo MAPIE, use case CalibrateConformal, cobertura conformal sobre a série nativa, prova sintética, bloco [conformal] do pré-registro, montagem calib/teste, port do consumidor, RefreshParameters, tabelas gold, RefreshGold pelo port, ponta a ponta sintético, prova de geometria real, r2 e âncora — e a Etapa G (geometria sobre o cohort real, sem métrica)
when-use: Consultar durante a Fase 4 (execução) da Stage 7.2; cada Task traz lista fechada de arquivos, testes a escrever primeiro, o gate da camada (T1/T2/T3), o critério do concept que cobre e a verificação; a Etapa G traz o comando docker da prova de geometria real
keywords: [technical, plano de execução, conformal-cqr, inference, evaluation, cqr, nexcp, mapie, oracle, fixture, calibration-set, embargo, coverage, refresh-gold, gold, preregistration, r2, anchor, reproduction-policy, port-coverage, import-linter, blinding, geometry]
status: done
created_at: 2026-10-17
updated_at: 2026-10-17
stage_id: 7.2-conformal-cqr
stage_title: Conformal CQR (benchmark)
step_id: 7
step_title: Inferência, conformal, explicabilidade e API
depends_on: [7.1-inference-engine, 5.1-walk-forward-harness, 6.1-scoring-and-calibration-metrics]
concept_ref: ./concept.md
issue_id: 158
branch: feat/158-7-2-conformal-cqr
tasks_count: 23
---

# Technical — Stage 7.2 — Conformal CQR (benchmark)

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01 (decisões de forma fixadas aqui).
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de
>    arquivos de cada Task é **fechada**: tocar arquivo fora dela = parar e
>    perguntar (RUNBOOK Passo 8, "Escopo estrito"). Arquivos `__init__.py`
>    marcados *(pacote)* são marcadores vazios ou de uma linha de docstring;
>    **pacotes não contam** na contagem de arquivos da Task (PIPELINE §4.3
>    item 2), mas estão na lista fechada.
> 3. Escrever primeiro os testes de "Testes primeiro" (vermelho), depois o
>    código (verde). O gate de commit de cada Task é a camada indicada (T1/T2/T3,
>    [RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)).
> 4. Commit: `<type>(<escopo>): <descrição> [7.2/task-NN]`, body em bullets,
>    `Refs #158`, subject ≤ 100 caracteres, mensagem UTF-8 sem BOM por
>    `git commit -F` ([`CONVENTIONS.md`](../../CONVENTIONS.md) §4).
> 5. Algo não previsto em §1–§6, no concept ou nos ADRs → pausar, perguntar com
>    opções, registrar em §7. Nunca propagar em silêncio.
> 6. Depois da Task 22: **Etapa G** (prova de geometria real), auditoria de
>    testes, Task 23 (âncora da r2), §3 e o commit `stage 7.2: complete`.
>
> **Stage = 1 branch:** `feat/158-7-2-conformal-cqr`, worktree própria.
>
> **Cegamento (I12, inegociável).** Nenhuma Task, teste, script ou etapa desta
> Stage calcula escore, Q̂, cobertura ou qualquer função de predição × realizado
> sobre o cohort `aapl_confirmatory-r0-665f45d9169a`, e nenhum `RefreshGold`
> roda sobre ele. Os testes usam silver sintético. A Etapa G lê só timestamps,
> partições, fingerprints e o manifesto — nunca `value_*` nem `target_return`.

## 1. Contexto e estratégia de execução

### Resumo

O concept aprovado ([`concept.md`](./concept.md); ADRs
[7.2.0001](../../adr/7_2_0001-cqr-preregistration-details.md)–[7.2.0005](../../adr/7_2_0005-reproduction-policy-in-inference-domain.md))
pede, no **inference**: a política de reprodução da 7.1 movida para o domain
(F3); o `CalibrationSet` (calib dedicado com embargo); o `ConformalCalibrator`
stdlib (split-CQR assimétrico e NexCP ρ = 0,99, posto e pesos em `Fraction`,
+∞ sem corte); o oráculo MAPIE atrás do port `ConformalBackend` e a fixture
congelada do `splitCP_LS` dos autores; e o use case puro `CalibrateConformal`
com status por unidade. No **evaluation**: a cobertura conformal sobre a série
nativa embutida (`ConformalCoverageSeries`, `ConformalCoverage`), o VO
`ConformalParameters` aceito pelo `Preregistration`, a montagem calib/teste
(`ConformalAssembly`, reusando as regras donas do `SeriesAssembly`), o port do
consumidor `ConformalCalibration`, o bloco `conformal_parameters` no
`RefreshParameters`, duas tabelas gold e o `RefreshGold` chamando o port. Fecham
a Stage a emenda cega r2 ancorada na #158 e a prova de geometria do calib sobre
o cohort real (Etapa G, sem métrica).

### Estratégia (ordem e porquê)

TDD inside-out (skill `task-ordering-hex`), em dois slices, com o fornecedor
antes do consumidor:

1. **F3 primeiro (Task 01).** É refactor sem mudança de comportamento e cria o
   pacote `inference/domain/services/`, que o calibrador ocupa em seguida.
2. **Domain do inference (Tasks 02–04):** VO → split-CQR → NexCP com a fixture.
   O enum `ConformalVariant` nasce com um membro na Task 03 e ganha o segundo na
   04 (nenhum ramo "não implementado" entre commits).
3. **Gate antes do oráculo (Task 05):** contrato `inference-no-mapie-leak` e a
   dependência `mapie` no mesmo commit, para que o caso de quebra `import mapie`
   seja real desde o início.
4. **Port do oráculo → adapter (Tasks 06–07)**, pelo padrão do
   [ADR 6.1.0005](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md)
   (ver "Exceções" abaixo).
5. **Use case (Task 08)**, puro, sem port (nenhum use case chama o
   `ConformalBackend`, I1).
6. **Domain do evaluation (Tasks 09, 11–14)**, com a prova sintética (Task 10)
   assim que `CalibrateConformal` e `ConformalCoverage` existem.
7. **Port do consumidor (Task 15)** — o real (`CalibrateConformal`) já existe, sem
   baseline.
8. **Gold de fora para dentro do use case (Tasks 16–19):** parâmetros → DTOs →
   schema e builders (registrados no composition root, zero linhas) → o
   `RefreshGold` chama o port, com a aresta de dados e o wiring do real.
9. **Provas e pré-registro (Tasks 20–23):** ponta a ponta sintético, teste de
   geometria ativado por ambiente, r2, Etapa G, auditoria de testes e âncora.

**Exceções declaradas à regra 4 do PIPELINE §4.3 (port × adapter):**

- `ConformalBackend` (Task 06) nasce **sem** adapter real. A Task 06 acrescenta a
  entrada temporária em `scripts/arch_baseline.toml` (`key = "ConformalBackend"`,
  `issue = 158`, `motivo` citando o ADR 6.1.0005 — campo obrigatório no
  `arch_baseline_lib.py`) **e**, no mesmo commit, troca a lista literal de
  `test_real_repo_violations_are_exactly_the_declared_baseline` em
  `tests/architecture/test_port_coverage_gate.py` de `["Hasher"]` para
  `["ConformalBackend", "Hasher"]`, com comentário citando o ADR 6.1.0005. A Task
  07 (adapter) reverte as duas edições. As duas Tasks são T3. O gate de saída exige
  `scripts/arch_baseline.toml` sem diferença contra o `develop` e a lista literal
  de volta a `["Hasher"]`.
- `ConformalCalibration` (Task 15) não precisa de baseline: o real é o
  `CalibrateConformal` (Task 08), reconhecido pela regra #93 do
  `check_port_coverage.py` (anotações textualmente iguais + contrato `[fake, real]`
  que importa os dois pelo nome).
- **Homônimos:** nenhum port novo tem nome igual a port de outro slice (o
  `InferenceBackend` do evaluation é outro nome). O teste do gate indexa por
  `(slice, nome)` (7.1 §7) e a Task 15 acrescenta a asserção explícita dos dois
  ports novos.

**Tasks acima de 5 arquivos** (pacotes não contam; justificadas na própria Task):
06 (port, fake, contrato, helper, guarda e o
par do ADR 6.1.0005), 07 (adapter, perna do contrato, par do ADR 6.1.0005 revertido, errata do ADR 7.2.0002 e, como contingência declarada, o helper de tamanhos), 16 (construções literais de `RefreshParameters` nos testes),
18 (schemas novos entram em `GOLD_SCHEMAS`, e a regra "COMPLETED lista toda
tabela" obriga registrar os builders no composition root no mesmo commit) e 19 (a
mudança do construtor do `RefreshGold` obriga o composition root; a aresta de
runtime obriga `.importlinter`, o caso de arquitetura e LAYOUT §7 no mesmo commit —
`unmatched_ignore_imports_alerting = error` reprova o ignore sem import, e o
`bc-independence` reprova o import sem ignore).

**Etapa G = execução real, não Task** (concept D8): não produz código; a evidência
vai para §7 num commit `docs(inference): evidência da prova de geometria real [7.2/--]`.

### Decisões de forma fixadas aqui (o concept deixou para a Fase 3B)

- **`exact_level` mora em `inference/domain/value_objects/calibration_set.py`**
  (o VO precisa dele para conferir o par; o serviço importa o VO, então o inverso
  criaria ciclo). `conformal_calibrator.py` a importa e a reexporta no `__all__`,
  e o caminho do concept §4 continua válido. Recusa `bool`, não-número e
  não-finito com `ValueError`.
- **Timestamps do `CalibrationSet`** são comparados como `datetime` (via
  `datetime.fromisoformat`), não como texto, e **têm de ter fuso** (`tzinfo` não
  nulo); ISO inválido ou sem fuso → `ValueError` nomeando o campo (nunca o
  `TypeError` da comparação naive × aware).
- **`CalibrateConformalCommand.nexcp_rho: float | None`** — `None` só é aceito sem
  `NEXCP` em `variants` (o C3 "ρ ausente para NEXCP" exige que ele possa faltar).
- **Funções públicas do módulo `calibrate_conformal.py`**, donas únicas usadas pelo
  use case **e** pelo `FakeConformalCalibration` (o padrão do `merge_run_entry` da
  7.1): `validate_command(command) -> None` (os erros de comando do C3) e
  `calibration_set_for(unit, pair) -> CalibrationSet | str` (o VO, ou o motivo de
  `undefined` — ponto de calib sem `realized`, grade sem um nível do par, unidade
  sem ponto de teste; `ValueError`/`ArithmeticError` do VO propagam para o chamador
  capturar como `error`). Unidade **sem ponto de teste** é `undefined`
  (entrada incompleta; `test_start` não existe).
- **Ordem do `CalibrateConformalResult`:** unidades por `(fold_index, seed,
  horizon)` crescentes; dentro da unidade, pares e variantes na ordem do comando.
  `test_start = test[0].decision_timestamp`; `lower`/`upper` do calib e do teste =
  `grid[τ_lo]`/`grid[τ_hi]` (o `value_guardrail`, I2).
- **`ConformalUnitAssembly.fold_index: int | None`** (e `ConformalUnitRecord`),
  mais **`fold_raw: str`** (o `fold` cru do `CohortRun`, `"<none>"` quando `None`):
  `fold_index = None` ⇔ o `fold` do run não é inteiro (inclui `fold = None`); a
  unidade é `undefined` com o fold cru no motivo e nunca vai ao port, cujo DTO
  segue com `fold_index: int`. É a única forma de representar o caso que o C9
  declara. `full_series_folds: Mapping[(seed, h), tuple[int | None, ...]]` (o
  `None` do ponto vem do mesmo fold não inteiro). **Seed `None`** num run do
  candidato também vira unidade `undefined` (motivo `"seed is None"`), nunca
  exceção.
- **Regras públicas do `SeriesAssembly`** (Task 13), no próprio
  `series_assembly.py`: `RuleViolation(kind: AlignmentKind, detail: str)` (frozen);
  `duplicate_levels(rows_by_level: Mapping[float, Sequence[ForecastRecord]], *, target_timestamp: str) -> RuleViolation | None`;
  `index_violations(*, target_timestamp: str, decisions: Iterable[tuple[str, int]], horizon: int, realized: RealizedReturns) -> tuple[RuleViolation, ...]`
  (`REALIZED_MISSING`, `DECISION_INDEX_MISMATCH`, `HORIZON_LABEL_MISMATCH`);
  `missing_levels(*, present: Iterable[float], expected: Iterable[float], target_timestamp: str) -> RuleViolation | None`
  (`GRID_INCOMPLETE`). O `detail` é o texto que o `SeriesAssembly` emite hoje
  (os testes da 6.4 passam sem mudar asserção); o `SeriesAssembly` acrescenta
  horizonte, modelo e seed ao converter em `AlignmentFinding`.
- **Infinito no gold:** `GoldTable` recusa float não-finito (`_cell_ok`). Correção
  +∞ vai como `correction = null` com `infinite = true`; MPIW infinito como
  `mpiw = null` com `mpiw_infinite = true`. No domain e nos DTOs o valor segue
  `math.inf`; só o builder (adapter) mapeia. **Leitor (7.4, D9):** reconstrói +∞
  por `infinite = true`; o `status` separa esse `null` (`ok`, infinito) do `null`
  de unidade não-`ok` (`undefined`/`error`, com `infinite` nulo).
- **Chaves finais do bloco `[conformal]`** (catálogo `CONFORMAL_RULE_CATALOG`,
  valores do concept §4):

  | chave | valor |
  |---|---|
  | `variant_of_record` | `"split_cqr_asymmetric_unweighted_v1"` |
  | `rank` | `"ceil_n_plus_1_one_minus_tail_alpha_exact_v1"` |
  | `sensitivity` | `"nexcp_fixed_geometric_weights_v1"` |
  | `nexcp_rho` | `0.99` (float em (0, 1]) |
  | `weighted_threshold` | `"smallest_score_cumulative_weight_ge_v1"` |
  | `calibration_unit` | `"fold_seed_horizon_pair_tail_v1"` |
  | `base_vector` | `"guardrail"` |
  | `output_rearrangement` | `"none"` |
  | `pairs` | `[[0.02, 0.98], [0.1, 0.9], [0.25, 0.75]]` |
  | `primary_pair` | `[0.1, 0.9]` |
  | `comparison` | `"descriptive_model_full_native_mask_seed_mean_counts_v1"` |
  | `profile_quantities` | `"nesting_crossing_seed_dispersion_tail_beta_reference_v1"` |

- **Colunas das tabelas gold** (ADR 7.2.0003 item 7; mais `asset`,
  `parent_sweep_id`, `preregistration_ref` por `partition_columns(confirmatory=True)`):
  - `gold_conformal_corrections` — chave `(fold_raw, seed, horizon, lower_level,
    upper_level, variant, tail)`, com `fold_raw` = o fold cru em texto (nunca nulo,
    então dois folds não inteiros distintos não colidem); `read_columns = (fold,
    tail_level, rho, status, reason, n, rank, correction, infinite, beta_a, beta_b,
    beta_mean, beta_sd)`, com `fold` inteiro ou nulo ⇔ fold não inteiro. Uma linha
    por cauda (`tail ∈ {lower, upper}`); unidade não-`ok` (da montagem ou do port)
    → as duas linhas com medidas e `infinite` nulos, `status` e `reason`; unidade
    `undefined` da montagem expande para todo par e variante do plano. A `seed`
    nula (unidade `undefined` por seed `None`) é única por `fold_raw`.
  - `gold_conformal_coverage` — chave `(horizon, variant, kind, lower_level,
    upper_level, seed, band_level)`; `read_columns = (status, reason, label,
    n_points, n_evaluated, nominal, count, coverage, mean_of_seed_coverages,
    sd_of_seed_coverages, n_seeds_used, seeds_excluded, mpiw, mpiw_infinite,
    crossed_rate, nesting_violation_rate, wilson_lower, wilson_upper,
    wilson_contains_nominal, serial_dependence_warning)`. `kind ∈ {lower_tail,
    upper_tail, pair, nesting}`: caudas com `count_at_or_below`, ĉ, nominal τ e
    Wilson (uma linha por `band_level`); `pair` com PICP em `coverage`,
    `pair_nominal`, MPIW e cruzamento (`band_level` nulo); `nesting` com níveis e
    `band_level` nulos. `seed` nulo ⇔ linha de média entre seeds (`coverage` =
    c̄/n̄, `mean_of_seed_coverages` e `sd_of_seed_coverages` ao lado,
    `n_seeds_used`, `seeds_excluded` como texto `"s1,s2"` ordenado, `""` sem
    exclusão). `status ∈ {ok, undefined, not_applicable}` (C6 = série 100 %
    degenerada). `label` = `EMPIRICAL_COVERAGE_LABEL` em toda linha `ok`.
    **Forma fixa das linhas não-`ok`** (as mesmas chaves das linhas `ok`, então
    nunca colidem): (seed, horizonte, variante) `undefined` ou `not_applicable`
    gera o conjunto completo de linhas daquela seed — por par, `lower_tail` e
    `upper_tail` por `band_level`, `pair`, e uma `nesting` — com `status`,
    `reason` (nulo em `not_applicable`), `n_points` e, em `not_applicable`,
    `n_evaluated = 0`; todas as medidas, Wilson e `label` nulos. A média entre
    seeds com **zero seeds completas** gera o mesmo conjunto com `seed` nulo,
    `status = undefined`, `n_seeds_used = 0`, `seeds_excluded` = todas e medidas
    nulas. **Com uma única seed usada, `sd_of_seed_coverages` é nulo** (dp
    amostral indefinido).
- **Fakes novos:** `tests/fakes/features/inference/fake_conformal_backend.py`
  (`FakeConformalBackend`: Q̂ pelo `split_conformal_rank` do domain sobre os
  escores ordenados, sem os defeitos do MAPIE) e
  `tests/fakes/features/evaluation/fake_conformal_calibration.py`
  (`FakeConformalCalibration`: `validate_command` e `calibration_set_for` do
  fornecedor, correções **zero** em toda unidade `ok` — limites = os quantis
  nativos do par —, `force_status: Mapping[(fold, seed, horizon), (status,
  reason)]`, `raises: Exception | None` e o registro `calls`). O
  `check_fake_parity.py` compara fake × adapter e é cego a use case; o ponto cego
  é coberto por uma guarda AST (Task 15): o fake **importa** `validate_command` e
  `calibration_set_for` de `calibrate_conformal` e **não** define nem importa
  `calibrate`/`ConformalCalibrator`.
- **Comandos no container.** Fluxo Docker-only; a worktree roda por `docker run`
  avulso com os limites de recurso do projeto. Git Bash:

  ```bash
  WT=feat-158-7-2-conformal-cqr
  WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
  WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
  MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
  MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
  VENV=financial-forecasting_app-venv      # Tasks 01–04; da Task 05 em diante: financial-forecasting_ff72-venv
  # função, não string: o VENV é lido a cada chamada (uma string expandiria na atribuição)
  run() { MSYS_NO_PATHCONV=1 docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
    -v "$WTD:/app" -v "$MAIND/.git:/main.git" -v "$VENV:/app/.venv" \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev "$@"; }
  PRE="git config --global --add safe.directory '*'"
  PAR="PYTEST_PAR='-n 4 --dist loadgroup'"
  BASE=$(git -C "$WTH" merge-base origin/develop HEAD)   # base de todo diff "contra o develop"
  # uso: run sh -c "$PRE; make check-task SLICE=inference $PAR"
  #      run sh -c "$PRE; make check-task SLICE='inference evaluation' $PAR"
  ```

  Caminhos com barra normal (com `\` o bind mount sai vazio sem erro). Nos blocos
  de verificação, as linhas `make …`/`uv run …` rodam dentro de
  `run sh -c "$PRE; …"`; as linhas `git -C "$WTH" …`, `grep` e
  `python scripts/…` rodam no host. **Dentro de `sh -c "…"` só aspas simples**
  (`SLICE='a b'`): aspas duplas internas fecham a string do host e derrubam o
  segundo slice e o `PYTEST_PAR`. Todo diff "contra o develop" usa `$BASE`. O
  volume `ff72-venv` existe para que a sincronização com o `uv.lock` desta branch
  (com `mapie`) não altere o venv compartilhado do checkout principal.

### Pré-condições

- Concept `done` (`4389bec`) e ADRs 7.2.0001–0005 `accepted`; 7.1, 5.1, 6.1, 6.5
  e 6.6 em `develop`; roadmap já emendado no concept (`ce772b8`, com linha no
  histórico).
- Imagem `financial_forecasting-app:dev` e volume `financial-forecasting_app-venv`.
- Etapa G: `data/cohorts/aapl/` no checkout principal com `silver/`,
  `inference/aapl_confirmatory-r0-665f45d9169a/manifest.json` (7.1, Etapa E) e
  sem `gold/`.
- Task 04: o zip dos autores baixado **uma vez** para o scratchpad da sessão (fora
  do repo), sha256 anotado.

### Premissas técnicas

- Python 3.12, mypy strict, `from __future__ import annotations`; imports
  cross-slice de tipo só sob `TYPE_CHECKING` (invisíveis ao import-linter,
  `exclude_type_checking_imports = True`) — por isso as Tasks 06 e 19 trazem
  guardas AST em `tests/architecture/`.
- `make check-task SLICE=…` (T1) aceita `inference` e `evaluation` (têm testes em
  `tests/{unit,contract,integration}/features/<slice>`); **não** roda
  `tests/architecture/` — Task que toca `.importlinter`, `pyproject.toml`,
  `uv.lock`, `scripts/arch_baseline.toml` ou `tests/architecture/` é T3.
- `tests/architecture/test_unit_evaluation_purity.py`: nenhum
  `tests/unit/features/evaluation/**` importa `numpy`/`scipy`/`sklearn`/adapter
  nem chama `open`/`read_text`/`json.load`. Teste que lê arquivo do repo (fixture,
  TOML real, espelho) vai em `tests/integration/` ou `tests/architecture/`. Como o
  T1 não roda esse gate, **toda Task que cria ou muda teste em
  `tests/unit/features/evaluation/`** (09, 11, 12, 13, 14, 16, 17, 19) roda também
  `uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov`.
- O mypy roda só sobre `src/` (`make typecheck`); arquivo de teste quebra pelo
  pytest (import), não pelo mypy.
- `GoldTable` recusa float não-finito; `GoldGeneration.from_stored` exige que uma
  geração `COMPLETED` liste toda tabela de `GOLD_SCHEMAS` e que `BLOCKED` não liste
  tabela de `CONFIRMATORY_TABLES`.
- `check_manifest` compara `parameters.as_mapping()` inteiro: a chave nova entra
  na comparação sem código novo no comparador.

### Estrutura de pastas afetada

```
.importlinter, docs/LAYOUT.md §7, tests/architecture/test_import_contracts.py   (mod, Tasks 05, 19)
pyproject.toml, uv.lock                                                           (mod, Task 05)
scripts/arch_baseline.toml, tests/architecture/test_port_coverage_gate.py         (mod, Tasks 06/07, 15)
tests/architecture/test_stage_7_2_regression_guards.py                            (novo 06, mod 15, 19)
config/preregistration/aapl_confirmatory-r2{.toml (22), .anchor.toml (23)}
docs/preregistration/aapl_confirmatory.md                                         (mod, 22, 23)
src/financial_forecasting/
├── composition_root.py                                                           (mod, 18, 19)
└── features/
    ├── inference/
    │   ├── domain/services/{reproduction_policy (01), conformal_calibrator (03/04)}.py
    │   ├── domain/value_objects/calibration_set.py                               (02)
    │   ├── application/ports/out/conformal_backend.py                            (06)
    │   ├── application/use_cases/{run_inference (mod 01), calibrate_conformal (08)}.py
    │   ├── adapters/in/cli/inference_commands.py                                 (mod 01)
    │   └── adapters/out/mapie/mapie_cqr_backend.py                               (07)
    └── evaluation/
        ├── domain/value_objects/{conformal_coverage_series (09), conformal_parameters (11), preregistration (mod 12)}.py
        ├── domain/services/{conformal_coverage (09), series_assembly (mod 13), conformal_assembly (14)}.py
        ├── application/ports/out/conformal_calibration.py                        (15)
        ├── application/dtos/{refresh_gold (16, 17), confirmatory_scorecard (16), gold_schema (18)}.py
        ├── application/use_cases/refresh_gold.py                                 (mod 17, 19)
        └── adapters/out/duckdb/gold_builders/{conformal_corrections, conformal_coverage}.py (18)
tests/
├── fixtures/nexcp_oracle/{generate_nexcp_cases.py, nexcp_cases.json}            (04)
├── fakes/features/inference/fake_conformal_backend.py                            (06)
├── fakes/features/evaluation/fake_conformal_calibration.py                       (15)
├── contract/features/inference/{_coincidence_sizes, test_conformal_backend_contract}.py (06/07)
├── contract/features/evaluation/{test_conformal_calibration_contract (15), test_conformal_gold_builders (18)}.py
├── unit/features/inference/{test_conformal_embargo (02/08), test_conformal_calib_set_dedicated (08)}.py
├── unit/features/inference/domain/{test_reproduction_policy (01), test_conformal_calibrator (03),
│                                   test_nexcp_weighted_threshold (04)}.py
├── unit/features/inference/application/test_calibrate_conformal.py               (08)
├── unit/features/evaluation/{test_conformal_coverage_series, test_conformal_coverage (09),
│                             test_conformal_parameters, _conformal_parameters (11)}.py
├── unit/features/evaluation/gold/{test_series_assembly_rules (13), test_conformal_assembly (14)}.py
├── integration/features/inference/{test_nexcp_oracle_fixture (04), test_cqr_empirical_coverage (10),
│                                   test_conformal_geometry_real_cohort (21)}.py
└── integration/features/evaluation/{test_conformal_catalog_matches_variants (11),
                                     test_conformal_refresh_end_to_end (20)}.py
```

## 2. Tasks

> Faixa de referência: 3–12 Tasks (CONVENTIONS §6). **Esta Stage tem 23**, mais
> a Etapa G. A contagem é referência, não gate: o concept (§12, D3) não tem
> fronteira de escopo real para dividir, e a estimativa de ~20 cresceu porque o
> port do oráculo e o seu adapter são commits separados (ADR 6.1.0005), os DTOs do
> gold separam-se do `RefreshGold` (cada commit verde) e a âncora é uma Task
> própria depois da auditoria.

### Task 01 — Política de reprodução no domain do inference (F3)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/domain/services/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/domain/services/reproduction_policy.py`
  - `tests/unit/features/inference/domain/__init__.py` *(pacote)*
  - `tests/unit/features/inference/domain/test_reproduction_policy.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/inference/application/use_cases/run_inference.py`
  - `src/financial_forecasting/features/inference/adapters/in/cli/inference_commands.py`
  - `tests/unit/features/inference/application/test_run_inference.py` (**só o bloco
    de import**: `STRICT`, `TOLERANCE` e `within_mode` passam a vir do domain, seu
    único dono — o use case não os reexporta, então o import antigo falharia no
    pytest; nenhuma asserção muda)
- **Testes primeiro** (`test_reproduction_policy.py`):
  `test_equal_non_ignored_keys_without_justification_is_strict` (`reason ==
  "non-code keys equal"`); `test_difference_only_in_an_ignored_key_stays_strict`
  (mata a mutação que ignora `ignored_keys`);
  `test_differing_key_is_tolerance_with_sorted_keys_in_reason`;
  `test_justification_with_equal_keys_forces_tolerance` (`forced is True`);
  `test_differing_keys_win_over_justification` (`forced is False`);
  `test_within_mode_strict_is_exact_equality` (1 ulp reprova);
  `test_within_mode_tolerance_boundary` (no limite `atol + rtol·|z|` passa,
  `math.nextafter` acima reprova); `test_tolerance_constants`
  (`1e-5`, `1.3e-6`); `test_compare_reproduction_counts_failures_and_max_diffs`;
  `test_compare_reproduction_reports_missing_and_extra_keys`;
  `test_compare_reproduction_with_nothing_compared` (`compared == 0`).
- **O que fazer (concept §1 item 1, D6; ADR 7.2.0005):** `STRICT`, `TOLERANCE`,
  `TOLERANCE_ATOL`, `TOLERANCE_RTOL`, `ReproductionMode`, `reproduction_mode(...,
  *, ignored_keys)`, `within_mode`, `ReproductionComparison` e
  `compare_reproduction` no domain, stdlib-only (o domain não importa o
  `modeling`, I13). O `RunInference` importa-os, passa
  `ignored_keys = frozenset({*CODE_KEYS, DIRTY_KEY})`, troca `_Mode` por
  `ReproductionMode`, faz o `_reproduce_test` montar os dois mapas e chamar
  `compare_reproduction`, e ergue `ReproductionError` com **as mesmas mensagens**
  (C7); `_verify_decision` fica no use case e chama `within_mode` (C8). O CLI
  importa `STRICT` do domain; nada é reexportado pelo use case.
- **Critério de aceite (CA1; I13):** testes novos verdes; toda a suíte da 7.1
  verde; o diff de `test_run_inference.py` só nas linhas de import;
  `tests/integration/features/inference/test_run_inference.py` intocado;
  `lint-imports` sem aresta nova (o T1 roda o import-linter).
- **Verificação (T1):**
  ```bash
  make check-task SLICE=inference $PAR
  uv run --no-sync pytest tests/unit/test_cli.py -q --no-cov          # o CLI importa STRICT do domain
  git -C "$WTH" diff -U0 -- tests/unit/features/inference/application/test_run_inference.py   # só import
  git -C "$WTH" diff --exit-code -- tests/integration/features/inference/test_run_inference.py
  grep -nE "^(STRICT|TOLERANCE|TOLERANCE_ATOL|TOLERANCE_RTOL) =|^class _Mode|^def (within_mode|reproduction_mode)" "$WTH/src/financial_forecasting/features/inference/application/use_cases/run_inference.py"   # vazio
  ```
- **Commit:** `refactor(inference): política de reprodução no domain do inference [7.2/task-01]`

---

### Task 02 — `CalibrationSet`: calib dedicado com embargo

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/domain/value_objects/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/domain/value_objects/calibration_set.py`
  - `tests/unit/features/inference/test_conformal_embargo.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (`test_conformal_embargo.py`, um caso por recusa do I7, a
  mensagem nomeia o campo): `test_empty_calib_refused`;
  `test_repeated_target_refused`; `test_out_of_order_target_refused`;
  `test_calib_decision_at_test_start_refused` e `..._after_test_start_refused`;
  `test_calib_target_at_test_start_refused` e `..._after_test_start_refused`
  (o embargo: alvo do calib sobre o teste); `test_non_finite_value_refused`
  (parametrizado: `lower`, `upper`, `realized` × NaN, +∞, −∞);
  `test_non_symmetric_pair_refused` (0,1/0,8); `test_lower_level_zero_refused`
  (0,0/1,0); `test_lower_level_half_refused` (0,5/0,5);
  `test_lower_level_above_half_refused` (0,9/0,1);
  `test_naive_or_invalid_timestamp_refused` (parametrizado: ISO sem fuso em
  `decision_timestamp`, `target_timestamp` e `test_start`, e texto não ISO —
  `ValueError` nomeando o campo, nunca `TypeError`); `test_valid_set_accepted`;
  `test_exact_level_is_the_shortest_decimal` (`exact_level(0.99) ==
  Fraction(99, 100)`; `exact_level(0.1) + exact_level(0.9) == 1`);
  `test_exact_level_refuses_bool_and_non_finite`.
- **O que fazer (concept §4 `CalibrationSet`, I7; ADR 7.2.0002 item 2):**
  `CalibrationPoint` e `CalibrationSet` frozen, validação no `__post_init__`
  (timestamps como `datetime`; par por `exact_level`: τ_lo + τ_hi = 1 exato e
  τ_lo ∈ (0; 0,5)); `points` como tupla. `exact_level` neste módulo (§1).
- **Critério de aceite (CA5, parte VO; I7; C1):** cada recusa com `ValueError`
  nomeando o campo; conjunto válido aceito.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/inference/test_conformal_embargo.py -v --no-cov
  make check-task SLICE=inference $PAR
  ```
- **Commit:** `feat(inference): calib dedicado com embargo como value object [7.2/task-02]`

---

### Task 03 — `ConformalCalibrator`: split-CQR assimétrico com posto exato

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/domain/services/conformal_calibrator.py`
  - `tests/unit/features/inference/domain/test_conformal_calibrator.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (`test_conformal_calibrator.py`):
  `test_rank_at_n_252_for_the_three_tail_alphas` (248, 228, 190);
  `test_rank_small_n_table` (n = 1..30 × três α contra ⌈(n+1)(1−α)⌉ em
  `Fraction`); `test_upper_alpha_of_0_9_is_exactly_one_tenth` (α_hi de 0,9 =
  `Fraction(1, 10)` e o mesmo posto que α_lo de 0,1 para n = 1..400);
  `test_rank_above_n_is_infinite_and_not_clipped` (n = 10, α = 0,02 ⇒ k = 11,
  `correction == math.inf`, `infinite is True`, `rank == 11`);
  `test_ties_counted_with_multiplicity`;
  `test_score_sides` (y sempre 1 abaixo de q̂_lo ⇒ Q̂_lo = 1 e L = q̂_lo − 1;
  y sempre 2 acima de q̂_hi ⇒ Q̂_hi = 2 — mata troca de sinal e de cauda);
  `test_negative_scores_shrink_positive_widen`;
  `test_limits_are_not_rearranged` (`limits` devolve L > U sem trocar, e ±∞);
  `test_beta_reference_at_n_252` (α = 0,02: l = 5 ⇒ Beta(248, 5), média e dp em
  forma fechada); `test_beta_reference_none_when_l_is_zero` (n = 10, α = 0,02);
  `test_beta_reference_uses_exact_alpha` (n = 9, α_hi de τ = 0,9 ⇒ l = 1,
  Beta(9, 1); em float64 ⌊10·(1 − 0.9)⌋ = 0 e a mutação devolveria `None`);
  `test_split_variant_refuses_rho`.
- **O que fazer (concept §4, I2, I3, I5, D7; ADR 7.2.0002 itens 2–3):**
  `ConformalVariant` com **só** `SPLIT_CQR` (o `NEXCP` entra na Task 04),
  `TailCorrection`, `PairCorrection.limits`, `BetaReference`,
  `split_conformal_rank`, `beta_reference`, `ConformalCalibrator.calibrate` para a
  variante sem pesos; escores E^lo = q̂_lo − y e E^hi = y − q̂_hi; α_lo = τ_lo e
  α_hi = 1 − τ_hi em `Fraction`; reexporta `exact_level`.
- **Critério de aceite (CA2; parte de CA6: `beta_reference` com l = 0; I2, I3, I5;
  C2):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/inference/domain/test_conformal_calibrator.py -v --no-cov
  make check-task SLICE=inference $PAR
  ```
- **Commit:** `feat(inference): split-CQR assimétrico com posto exato no domain [7.2/task-03]`

---

### Task 04 — NexCP com pesos geométricos e fixture do `splitCP_LS`

- **Arquivos a criar:**
  - `tests/unit/features/inference/domain/test_nexcp_weighted_threshold.py`
  - `tests/fixtures/nexcp_oracle/generate_nexcp_cases.py`
  - `tests/fixtures/nexcp_oracle/nexcp_cases.json`
  - `tests/integration/features/inference/test_nexcp_oracle_fixture.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/inference/domain/services/conformal_calibrator.py`
- **Testes primeiro:**
  - unit: `test_rho_one_equals_the_unweighted_rank` (propriedade,
    `random.Random(20261017)`, 200 casos, n ∈ [1, 300], três α);
    `test_most_recent_point_weighs_rho` (escores crescentes no tempo, ρ = 0,5: o
    limiar difere do da ordem invertida — mata a orientação);
    `test_normalization_counts_the_test_point_weight` (caso em que Σw̃ sem o +1
    alcançaria 1 − α e com o +1 não ⇒ +∞); `test_insufficient_mass_is_infinite`
    (C2); `test_n_252_tail_002_finite_at_099_infinite_at_098` (doc §4.5);
    `test_tied_scores_enter_together`;
    `test_calibrate_passes_exact_geometric_weights` (o resultado de `calibrate`
    = `weighted_conformal_threshold` com `exact_level(ρ)**(n+1−i)`);
    `test_nexcp_has_no_rank_and_no_beta`;
    `test_variant_has_exactly_the_two_members` (I17);
    `test_rho_refused` (0, 1,0000001, NaN, −0,5, `None` para NEXCP).
  - golden (`test_nexcp_oracle_fixture.py`): `test_every_case_selects_the_authors_score`
    (`float.fromhex` exato; +∞ como `"inf"`);
    `test_provenance_block_complete` (URL, sha256 de 64 hex, id da célula,
    versão do numpy, semente); `test_cases_cover_each_rho_and_an_infinite_case`.
- **O que fazer (concept §1 item 3, I4; ADR 7.2.0002 itens 3 e 5):**
  `ConformalVariant.NEXCP`, `weighted_conformal_threshold(scores, weights, alpha)`
  em `Fraction` (normalização por Σw + 1, empates juntos, massa finita < 1 − α ⇒
  +∞) e o ramo NEXCP do `calibrate` (w_i = ρ^(n+1−i), i crescente no
  `target_timestamp`). Gerador (rodado **uma vez** no container, com o zip do
  scratchpad montado só leitura em `/scratch`; nunca no CI). Comando literal (host,
  Git Bash; `SCRATCH` = scratchpad da sessão com barra normal, `ZIPSHA` = o sha256
  anotado no download):

  ```bash
  ZIPSHA=$(sha256sum "$SCRATCH/nonexchangeable_conformal.zip" | cut -d' ' -f1)
  MSYS_NO_PATHCONV=1 docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
    -v "$WTD:/app" -v "$MAIND/.git:/main.git" -v "$VENV:/app/.venv" -v "$SCRATCH:/scratch:ro" \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev \
    sh -c "$PRE; uv run --no-sync python tests/fixtures/nexcp_oracle/generate_nexcp_cases.py --zip /scratch/nonexchangeable_conformal.zip --sha256 $ZIPSHA --out tests/fixtures/nexcp_oracle/nexcp_cases.json"
  ```

  — recusa o zip se o sha256 calculado ≠ `--sha256` e grava esse valor na
  proveniência; localiza o notebook e a célula do `splitCP_LS`,
  **afirma** que as linhas transcritas do bloco de limiar estão no código-fonte da
  célula, gera casos (semente 20261017; n ∈ {20, 49, 100, 252}; ρ ∈ {1,0; 0,99;
  0,95; 0,9}; α ∈ {0,02; 0,1; 0,25}) e descarta os que ficam a menos de 1e-9 de
  1 − α no índice escolhido; JSON no formato `{"dec", "hex"}` do ADR 6.2.0006 e
  bloco `provenance`.
- **Critério de aceite (CA3; I4, I17; C2):** testes verdes; o JSON versionado com
  ≥ 1 caso infinito e ≥ 1 caso por ρ.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/inference/domain/test_nexcp_weighted_threshold.py tests/integration/features/inference/test_nexcp_oracle_fixture.py -v --no-cov
  make check-task SLICE=inference $PAR
  ```
- **Commit:** `feat(inference): NexCP com pesos geométricos e oráculo do código dos autores [7.2/task-04]`
- **Checkpoint C** (T2 `make check-block $PAR` + revisão do diff das Tasks 01–04).

---

### Task 05 — Contrato `inference-no-mapie-leak` e a dependência `mapie`

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `pyproject.toml` (`"mapie>=1.5,<1.6"` em `[project].dependencies`, com
    comentário: só o adapter `inference/adapters/out/mapie/` e a suíte de contrato;
    ADR 7.2.0002 item 7)
  - `uv.lock`
  - `.importlinter` (contrato `inference-no-mapie-leak`, `type = forbidden`;
    fontes `financial_forecasting.features.inference.application` e
    `financial_forecasting.features.inference.domain`; proibidos `mapie`, `numpy`,
    `sklearn`, `scipy`; comentário com o perímetro do ADR 7.2.0002 item 1)
  - `tests/architecture/test_import_contracts.py` (`"inference-no-mapie-leak"` em
    `_EXPECTED_CONTRACTS`; casos de quebra)
  - `docs/LAYOUT.md` §7 (o contrato novo e o perímetro: `mapie`/`numpy`/`sklearn`/
    `scipy` só em `inference/adapters/out/mapie/`) e §2 (uma linha
    `tests/fixtures/nexcp_oracle/` ao lado de `r_oracle/`)
- **Testes primeiro** (casos novos em `test_import_contracts.py`; cada módulo
  proibido em cada fonte — `test_every_forbidden_module_has_a_real_violation_case`
  exige ao menos um por módulo):
  `inference-no-mapie-leak:inference-domain-imports-mapie`,
  `inference-no-mapie-leak:inference-application-imports-mapie`,
  `inference-no-mapie-leak:inference-application-imports-numpy`,
  `inference-no-mapie-leak:inference-domain-imports-numpy`,
  `inference-no-mapie-leak:inference-domain-imports-scipy`,
  `inference-no-mapie-leak:inference-application-imports-sklearn`.
- **O que fazer:** como acima. `uv lock` no container (rede); o diff do `uv.lock`
  só acrescenta o `mapie` e o que ele puxa de novo — numpy e scikit-learn não
  mudam de versão (senão HALT, §5). **Volume próprio desta branch, na ordem:**
  1. `docker volume create financial-forecasting_ff72-venv`;
  2. `VENV=financial-forecasting_ff72-venv` (a função `run` lê o valor a cada
     chamada);
  3. prova de que o volume montado é o ff72 **antes** do sync: copiar o venv
     compartilhado (montado **só leitura**) para ele e marcar o volume —
     `docker run --rm -v financial-forecasting_app-venv:/from:ro
     -v financial-forecasting_ff72-venv:/to alpine sh -c 'cp -a /from/. /to/ && touch /to/.ff72-marker'`
     —; então `run sh -c 'test -f /app/.venv/.ff72-marker' || { echo "VENV NÃO É O ff72"; exit 1; }`
     (**aborta** a Task se falhar: o `run` não está montando o ff72) e
     `run sh -c "uv run --no-sync python -c 'import mapie'"` → **falha**
     (`ModuleNotFoundError`);
  4. `run sh -c "$PRE; uv lock --check && uv sync --locked --inexact --extra dev"`
     (o padrão das Stages 6.1/6.2; sem `--extra dev` o sync desinstala pytest,
     mypy, ruff e import-linter; `--inexact` não remove nada);
  5. `run sh -c "uv run --no-sync python -c 'import mapie; print(mapie.__version__)'"`
     → 1.5.x; e, com `VENV=financial-forecasting_app-venv` só para esta checagem, o
     mesmo comando continua **falhando** (o compartilhado não foi tocado); voltar
     `VENV` para o ff72.
- **Critério de aceite (CA4, parte gate; I1):** `lint-imports` verde com o
  contrato; os seis casos verdes; `uv lock --check` limpo; `import mapie` resolve
  1.5.x só no volume ff72.
- **Verificação (T3 — dependência e `.importlinter`):**
  ```bash
  uv lock --check
  uv run --no-sync python -c "import mapie; print(mapie.__version__)"   # 1.5.x (ff72)
  uv run --no-sync pytest tests/architecture/test_import_contracts.py -v --no-cov
  make check $PAR
  git -C "$WTH" diff --stat "$BASE" -- uv.lock
  ```
- **Commit:** `build(inference): mapie como oráculo e contrato inference-no-mapie-leak [7.2/task-05]`

---

### Task 06 — Port `ConformalBackend`, fake e contrato (perna fake)

> **> 5 arquivos, justificado:** port, fake, suíte, helper de tamanhos, a guarda
> do I1 e o par baseline/teste do ADR 6.1.0005.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/ports/out/conformal_backend.py`
  - `tests/fakes/features/inference/fake_conformal_backend.py`
  - `tests/contract/features/inference/_coincidence_sizes.py`
  - `tests/contract/features/inference/test_conformal_backend_contract.py`
  - `tests/architecture/test_stage_7_2_regression_guards.py`
- **Arquivos a modificar:**
  - `scripts/arch_baseline.toml` (entrada temporária `ConformalBackend`, §1)
  - `tests/architecture/test_port_coverage_gate.py` (lista literal →
    `["ConformalBackend", "Hasher"]`, §1)
- **Testes primeiro:**
  - helper `_coincidence_sizes.py`: `coincidence_sizes()` — os n ∈ [50, 399] em que
    o posto do MAPIE coincide com o posto exato do domain para os três α ao mesmo
    tempo — e `divergent_sizes()` (n ≥ 50 em que diferem). O piso é 50 porque o
    MAPIE 1.5.0 recusa todo n ≤ 49 com α_cauda = 0,02 (C5, ver Task 07). O posto do
    MAPIE é a **cadeia literal**, na ordem do MAPIE 1.5.0
    (`mapie/regression/quantile_regression.py` l. 2313–2317):
    `confidence_level = 1 − 2·α_tail`;
    `alpha = float(Decimal("1") - Decimal(str(confidence_level)))`;
    `q = (1 − alpha/2)·(1 + 1/n)` em float64; índice 0-based `ceil(q·(n − 1))` do
    `np.quantile(..., method="higher")` (posto 1-based = índice + 1). Antes do
    commit, a cadeia é **conferida no container contra o `mapie` do ff72** (o
    executor lê `mapie/regression/quantile_regression.py` e o `np.quantile` usado e
    registra a linha conferida no docstring do helper);
    `test_helper_sizes_include_252` no próprio contrato (e
    `len(coincidence_sizes()) ≥ 100`).
  - contrato `[fake]` (a perna `mapie` entra na Task 07):
    `test_corrections_match_the_domain_at_coincidence_sizes` (todos os n do
    helper × três pares, escores distintos de `random.Random(20261017)`, igual ao
    `ConformalCalibrator.calibrate(..., SPLIT_CQR)`);
    `test_corrections_returned_as_lower_then_upper`.
  - guarda (`test_stage_7_2_regression_guards.py`):
    `test_only_the_mapie_adapter_imports_the_conformal_backend_port` (AST sobre
    `src/`, inclusive `TYPE_CHECKING`: além do próprio módulo do port, só
    `inference/adapters/out/mapie/**` pode importar `conformal_backend` — nenhum
    use case nem o composition root, I1 e ADR 6.4.0008). A guarda pega as três
    formas: `from ….conformal_backend import …`, `from ….ports.out import
    conformal_backend [as x]` e `importlib.import_module("…conformal_backend")`
    (constante de texto); `test_guard_catches_every_import_form` planta as três
    num módulo temporário e afirma que cada uma é acusada.
- **O que fazer (concept §4 "Inference — application"; ADR 7.2.0002 itens 4 e 6):**
  `ConformalBackend.split_cqr_corrections(*, calib_lower, calib_upper,
  calib_realized, tail_alpha) -> tuple[float, float]`, docstring: oráculo da
  variante sem pesos, nunca chamado por use case. `FakeConformalBackend` (§1).
- **Critério de aceite (CA4, parte):** suíte e guarda verdes;
  `check_port_coverage.py` verde **com** a entrada temporária.
- **Verificação (T3 — baseline e `tests/architecture/`):**
  ```bash
  uv run --no-sync pytest tests/contract/features/inference/test_conformal_backend_contract.py tests/architecture/test_stage_7_2_regression_guards.py tests/architecture/test_port_coverage_gate.py -v --no-cov
  uv run --no-sync python scripts/check_port_coverage.py --list
  make check $PAR
  ```
- **Commit:** `feat(inference): port ConformalBackend do oráculo, fake e contrato [7.2/task-06]`

---

### Task 07 — `MapieCqrBackend` (perna real do oráculo)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/adapters/out/mapie/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/inference/adapters/out/mapie/mapie_cqr_backend.py`
- **Arquivos a modificar:**
  - `tests/contract/features/inference/test_conformal_backend_contract.py` (perna
    `mapie`; casos só da perna `mapie`)
  - `scripts/arch_baseline.toml` (reverte a entrada da Task 06)
  - `tests/architecture/test_port_coverage_gate.py` (lista literal de volta a `["Hasher"]`)
  - `docs/adr/7_2_0002-own-cqr-in-domain-mapie-oracle-nexcp-fixture.md` (errata no
    formato "⚠️ Errata (2026-10-17)" no item 4, com `updated_at` atualizado: com
    α_cauda = 0,02 o `conformalize` (α_par = 0,04) recusa n < 25 e o
    `predict_interval` (`_check_alpha_and_n_samples` com α_par/2 = 0,02) recusa
    n < 50, com "Number of samples of the score is too low"; o ramo do
    `np.quantile` nunca é alcançado; o contrato roda com n ≥ 50; nada mais muda no
    ADR)
  - **contingência declarada:** `tests/contract/features/inference/_coincidence_sizes.py`,
    só se a perna `mapie` mostrar que a cadeia da Task 06 diverge do MAPIE real
    (correção da cadeia com `[deviation]` em §7; nunca afrouxar a comparação)
- **Testes primeiro:** os casos da Task 06 parametrizados em `[fake, mapie]`
  (`abs_tol = 1e-12` quando o Q̂ do MAPIE vem por subtração q̂ − L);
  só na perna `mapie`: `test_mapie_rank_differs_by_one_at_a_divergent_size` (n de
  `divergent_sizes()`: o Q̂ do MAPIE = o (k+1)-ésimo escore do domain; o fake não
  reproduz o defeito) e `test_mapie_refuses_small_n` (α_cauda = 0,02, parametrizado
  n ∈ {24, 30, 49}: `ValueError` com `"Number of samples of the score is too low"`
  propagado pelo adapter — n = 24 já no `conformalize`, n = 30 e 49 no
  `predict_interval`; medido contra o MAPIE 1.5.0, C5 e `[deviation]` em §7).
- **O que fazer (ADR 7.2.0002 item 4; concept §8 "Externas"):** envoltório
  `prefit` **privado** (`_PrefitPredictions`, para o gate não o tomar por adapter)
  que devolve as predições dadas por índice de linha e define `n_features_in_` e
  `__sklearn_is_fitted__` (sem eles o MAPIE avisa que o estimador não está
  ajustado); `test_mapie_leg_emits_no_warning` (perna `mapie`, com
  `warnings.catch_warnings(record=True)`) afirma zero avisos;
  `ConformalizedQuantileRegressor(estimator=[lo, hi, med], confidence_level=1 −
  2α, prefit=True)`, `conformalize(X, y)`; o Q̂ de cada cauda lido do atributo que
  guarda o quantil conformal quando a API o expõe, senão por
  `predict_interval(X, symmetric_correction=False)` e subtração. Docstring cita o
  port `ConformalBackend` (o gate acha o real por citação). Erros do MAPIE
  propagam.
- **Critério de aceite (CA4):** suíte `[fake, mapie]` verde em todos os n de
  coincidência (n = 252 incluído, todos ≥ 50) e nos três pares; caso +1 e C5 na
  perna `mapie`; `check_port_coverage.py` verde **sem** a entrada; baseline sem
  diferença contra o `develop`; errata presente no ADR 7.2.0002.
- **Verificação (T3):**
  ```bash
  uv run --no-sync pytest tests/contract/features/inference/test_conformal_backend_contract.py -v --no-cov
  uv run --no-sync python scripts/check_port_coverage.py
  git -C "$WTH" diff --exit-code "$BASE" -- scripts/arch_baseline.toml
  make check $PAR
  ```
- **Commit:** `feat(inference): MapieCqrBackend como oráculo do split-CQR [7.2/task-07]`

---

### Task 08 — Use case `CalibrateConformal` com status por unidade

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/use_cases/calibrate_conformal.py`
  - `tests/unit/features/inference/application/test_calibrate_conformal.py`
  - `tests/unit/features/inference/test_conformal_calib_set_dedicated.py`
- **Arquivos a modificar:**
  - `tests/unit/features/inference/test_conformal_embargo.py` (só acréscimos)
- **Testes primeiro:**
  - `test_calibrate_conformal.py`:
    `test_one_calibration_per_unit_pair_tail_variant_in_order` (I6; ordem do §1);
    `test_tail_corrections_equal_the_calibrator_called_directly` (campo a campo);
    `test_test_limits_aligned_to_the_test_points` (L_j = q̂_lo(teste j) − Q̂_lo,
    U_j = q̂_hi(teste j) + Q̂_hi; mata troca de cauda e de sinal);
    `test_beta_only_for_the_split_variant_per_tail`;
    `test_calib_point_without_realized_is_undefined`;
    `test_grid_without_a_pair_level_is_undefined_only_for_that_pair`;
    `test_unit_without_test_points_is_undefined`;
    `test_non_ok_results_carry_reason_and_no_values`;
    `test_command_errors_raise_before_any_unit` (parametrizado: unidade duplicada,
    variante `"aci"`, ρ 0 / 1,5 / NaN, ρ `None` com NEXCP, par 0,1/0,8, τ_lo 0,
    τ_lo 0,5 — com `ConformalCalibrator.calibrate` substituído por um espião via
    `monkeypatch` que conta **zero** chamadas).
  - `test_conformal_embargo.py` (acréscimo):
    `test_vo_refusal_becomes_error_only_in_its_unit` (parametrizado sobre cada
    recusa do VO **exceto as de par**: a unidade ruim volta `error` com a mensagem
    em `reason`, e as vizinhas do mesmo comando são iguais às de um comando sem a
    unidade ruim — I7, independência).
  - `test_conformal_calib_set_dedicated.py`:
    `test_corrections_invariant_to_any_test_value` (50 perturbações dos valores e
    da grade de teste, `random.Random(20261017)`: correções idênticas);
    `test_changing_a_calib_value_changes_the_correction` (não vacuidade).
- **O que fazer (concept §4 `CalibrateConformal`, I6, I7, C3; ADR 7.2.0003 item
  2):** os DTOs do concept §4, `UnitStatus`, `validate_command`,
  `calibration_set_for` e o use case; captura de `ValueError`/`ArithmeticError`
  **só** em volta da construção do VO e do `calibrate` de cada unidade; Beta pelo
  `beta_reference` por cauda, só na variante sem pesos. Não lê nem grava nada.
- **Critério de aceite (CA5; I6, I7; C1, C3):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/inference -v --no-cov
  make check-task SLICE=inference $PAR
  ```
- **Commit:** `feat(inference): use case CalibrateConformal com status por unidade [7.2/task-08]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 05–08).

---

### Task 09 — Cobertura conformal sobre a série nativa embutida

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/conformal_coverage_series.py`
  - `src/financial_forecasting/features/evaluation/domain/services/conformal_coverage.py`
  - `tests/unit/features/evaluation/test_conformal_coverage_series.py`
  - `tests/unit/features/evaluation/test_conformal_coverage.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:**
  - VO: `test_limits_length_must_match_the_native_series`;
    `test_nan_limit_refused_infinite_accepted`;
    `test_pair_must_be_symmetric_and_in_the_native_grid`;
    `test_duplicate_pair_refused`.
  - serviço: `test_zero_corrections_equal_the_native_coverage_metrics` (ĉ, PICP,
    MPIW e `n_evaluated` = os do `CoverageMetrics` da mesma série);
    `test_mask_is_the_native_series_mask` (linha degenerada fora do denominador);
    `test_tolerance_changes_the_mask` (a tolerância é a passada);
    `test_tail_tie_counts_at_or_below` (`y == L` e `y == U`);
    `test_picp_closed_ties` (`y == L` e `y == U` dentro);
    `test_crossed_interval_not_covered_and_counted` (`crossed_rate` e aninhamento);
    `test_infinite_limits_cover_and_flag_mpiw`;
    `test_wilson_nominal_is_the_tail_level` (τ_lo e τ_hi, não o nominal do par —
    mata a troca); `test_label_is_exact_and_validated` (I9);
    `test_fully_degenerate_native_is_not_applicable` (C6);
    `test_seed_mean_coverage_is_mean_count_over_mean_n` (caso com n diferentes por
    seed em que c̄/n̄ ≠ média das coberturas; as duas persistidas, com o dp);
    `test_seed_mean_reports_used_and_excluded_seeds`;
    `test_seed_mean_with_one_seed_has_no_dispersion` (sd `None`);
    `test_seed_mean_without_reports_is_undefined`;
    `test_seed_mean_refuses_mixed_horizon_variant_and_bad_seeds`.
- **O que fazer (concept §4 "Evaluation — domain", I8, I9; ADR 7.2.0004):** os
  VOs e `ConformalCoverage.evaluate`/`seed_mean`, reusando `DegeneracyGate`,
  `is_at_or_below`, `is_inside_closed`, `pair_nominal` e `WilsonBand` (nenhuma
  re-derivação). Sem import do inference: os limites chegam como floats.
- **Critério de aceite (CA6, menos "unidade não-`ok`" — Task 19 — e a Beta — Task
  03; I8, I9; C1, C6):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_conformal_coverage_series.py tests/unit/features/evaluation/test_conformal_coverage.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): cobertura conformal sobre a série nativa embutida [7.2/task-09]`

---

### Task 10 — Prova sintética da cobertura sob permutabilidade

- **Arquivos a criar:**
  - `tests/integration/features/inference/test_cqr_empirical_coverage.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_split_cqr_tail_coverage_in_the_theoretical_band`
  (três pares × duas caudas: média de ĉ(L) em [α_lo − 1/(n+1), α_lo] e de ĉ(U) em
  [τ_hi, τ_hi + 1/(n+1)], com ±3 EP de Monte Carlo);
  `test_nexcp_guarantee_side` (ĉ(L) ≤ α_lo + 3 EP e ĉ(U) ≥ τ_hi − 3 EP);
  `test_narrow_base_model_is_widened_and_wide_is_shrunk` (Q̂ médio > 0 e < 0).
- **O que fazer (concept CA7):** y e modelo base i.i.d., semente 20261017, n = 252
  de calib e m = 252 de teste por réplica, R = 1000 (sem pesos) e R = 200 (NexCP
  ρ = 0,99); grade sintética dos sete níveis; tudo por `CalibrateConformal` +
  `ConformalCoverage` (a `CoverageSeries` nativa montada dos quantis sintéticos).
  Tempo medido; acima de 120 s → `pytest.mark.slow` e `[deviation]` em §7.
- **Critério de aceite (CA7):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/integration/features/inference/test_cqr_empirical_coverage.py -v --no-cov --durations=5
  make check-task SLICE='inference evaluation' $PAR
  ```
- **Commit:** `test(inference): prova sintética da cobertura do CQR sob permutabilidade [7.2/task-10]`

---

### Task 11 — VO `ConformalParameters` e catálogo

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/conformal_parameters.py`
  - `tests/unit/features/evaluation/test_conformal_parameters.py`
  - `tests/unit/features/evaluation/_conformal_parameters.py` (helper
    `conformal_block()`/`conformal_parameters()` com os valores do §1)
  - `tests/integration/features/evaluation/test_conformal_catalog_matches_variants.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_round_trip` (`from_mapping(as_payload()) == vo`);
  `test_unknown_and_missing_keys_refused_with_dotted_path`;
  `test_identifier_outside_the_catalog_refused` (inclusive `"aci"` e `"enbpi"` em
  `variant_of_record` e `sensitivity` — I17); `test_rho_refused` (0, 1,5, NaN,
  `bool`); `test_non_symmetric_pair_refused`;
  `test_pair_symmetry_is_exact` (a soma é conferida com `Fraction(repr(x))` local —
  o evaluation não importa o `exact_level` do inference —: 0,1/0,9 e 0,02/0,98
  aceitos; um par cuja soma em float dá 1,0 mas a decimal não, 0,4/0,6000000000000001
  (`0.4 + 0.6000000000000001 == 1.0` em float64), recusado); `test_primary_pair_must_be_a_pair`;
  integração `test_catalog_variant_ids_are_exactly_the_conformal_variant_values`
  (I16: `{catálogo[variant_of_record], catálogo[sensitivity]} == {v.value for v in
  ConformalVariant}`; compõe os dois slices só no teste).
- **O que fazer (concept §4 `ConformalParameters`; ADR 7.2.0001 item 2):**
  `CONFORMAL_RULE_CATALOG` e o VO com as chaves do §1; `as_payload` é a única
  serialização (TOML, manifesto); erros `ValueError` com caminho pontuado
  (`conformal.pairs[1]`), padrão do `ProfileParameters`.
- **Critério de aceite (CA8, parte C4 e I16/I17):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_conformal_parameters.py tests/integration/features/evaluation/test_conformal_catalog_matches_variants.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): regras nomeadas do bloco conformal do pré-registro [7.2/task-11]`

---

### Task 12 — `Preregistration` aceita `[conformal]` (opcional, proibido no r0)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/preregistration.py`
  - `tests/unit/features/evaluation/test_preregistration_value_object.py`
  - `tests/unit/features/evaluation/test_preregistration_immutable_hash.py`
  - `tests/unit/features/evaluation/_preregistration_payload.py` (acréscimo `r2_payload()`)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_conformal_block_forbidden_in_revision_0`;
  `test_conformal_pairs_must_be_in_quantile_levels`;
  `test_primary_pair_must_be_the_h1_gate_pair`; `test_plan_with_block_round_trips`;
  `test_block_changes_the_hash` e `test_any_block_field_changes_the_hash`;
  `test_r0_and_r1_payload_hashes_unchanged` (os sintéticos sem bloco).
- **O que fazer (concept §4, último parágrafo antes de "Config"; C4):** campo
  `conformal: ConformalParameters | None`; `conformal` em `_OPTIONAL_KEYS`
  (conferido por `ConformalParameters.from_mapping`); cruzamentos no
  `__post_init__`; `as_payload` só escreve a chave quando presente.
- **Critério de aceite (CA8, parte; C4; I11 — hashes de r0 e r1 inalterados):**
  testes verdes; `test_preregistration_consistency.py` (arquivos versionados) verde
  sem mudança.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_preregistration_value_object.py tests/unit/features/evaluation/test_preregistration_immutable_hash.py tests/integration/features/evaluation/test_preregistration_consistency.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): pré-registro aceita o bloco conformal opcional [7.2/task-12]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 09–12).

---

### Task 13 — Regras de alinhamento do `SeriesAssembly` como funções públicas

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/series_assembly.py`
- **Arquivos a criar:**
  - `tests/unit/features/evaluation/gold/test_series_assembly_rules.py`
- **Testes primeiro:** um par por regra — `None`/tupla vazia na entrada conforme e
  a violação com `kind` e `detail` na não conforme: `test_duplicate_levels_rule`,
  `test_index_violations_realized_missing`,
  `test_index_violations_decision_index_mismatch`,
  `test_index_violations_horizon_label_mismatch`, `test_missing_levels_rule`;
  `test_series_assembly_findings_unchanged` (os achados de um cohort com as
  violações são os mesmos, campo a campo, que a 6.4 espera).
- **O que fazer (concept §4 "Regras da montagem"; ADR 7.2.0003 item 4):** as
  funções do §1; os `_check_*` do `SeriesAssembly` passam a chamá-las e a converter
  `RuleViolation` em `AlignmentFinding`. Uma definição só por regra.
- **Critério de aceite (CA13, parte "regras do teste aplicadas ao calib"):** testes
  novos verdes; `tests/unit/features/evaluation/gold/test_series_assembly.py` sem
  diferença e verde.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold -v --no-cov
  git -C "$WTH" diff --exit-code -- tests/unit/features/evaluation/gold/test_series_assembly.py
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `refactor(evaluation): regras de alinhamento do SeriesAssembly como funções públicas [7.2/task-13]`

---

### Task 14 — `ConformalAssembly`: unidades calib/teste a partir do silver

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/conformal_assembly.py`
  - `tests/unit/features/evaluation/gold/test_conformal_assembly.py`
- **Arquivos a modificar:**
  - `tests/unit/features/evaluation/gold/_cohort_factory.py` (só acréscimo:
    `with_calib(cohort, *, model, calib_decisions)` gera registros `split = "calib"`
    pelos mesmos runs)
- **Testes primeiro** (um por regra do CA13):
  `test_calib_only_from_calib_records_of_the_unit_run` (um registro de calib de
  outro run da mesma decisão não entra); `test_test_only_from_test_records`;
  `test_early_stop_records_never_enter`; `test_realized_taken_at_the_calib_target`;
  `test_full_series_folds_aligned_by_target`; `test_unit_without_calib_undefined`;
  `test_partial_calib_undefined`; `test_calib_target_without_realized_undefined`;
  `test_horizon_mismatch_undefined`; `test_duplicate_undefined`;
  `test_incomplete_levels_undefined`; `test_non_integer_fold_undefined`
  (parametrizado `"x"` e `None`: `fold_index is None`, `fold_raw` = o cru, e o
  ponto correspondente de `full_series_folds` é `None`);
  `test_two_non_integer_folds_stay_distinct` (`"x"` e `"y"` → duas unidades com
  `fold_raw` diferentes); `test_seed_none_is_undefined_with_reason`;
  `test_grids_use_value_guardrail_not_value_raw` (registros com `value_raw ≠
  value_guardrail`: as grades de calib e teste da unidade têm o `value_guardrail` —
  I2; mata a troca de coluna); `test_test_targets_must_equal_native_fold_targets` (parametrizado: alvo a mais,
  a menos e trocado com a mesma contagem — nunca por posição);
  `test_violation_is_never_an_alignment_finding` (o `SeriesAssembly` sobre os
  mesmos registros não acusa nada).
- **O que fazer (concept §4 `ConformalAssembly` e "Regras da montagem"; C9; ADR
  7.2.0003 item 4):** por run do candidato e horizonte, calib de `split = "calib"`
  e teste de `split = "test"` **do mesmo run**; regras pelas funções da Task 13;
  realizado do `RealizedReturns`; grades por nível = `value_guardrail`;
  `full_series_folds[(seed, h)]: tuple[int | None, ...]` = o fold do run que
  previu cada alvo de `native_full[(seed, h)]`; unidades em ordem `(fold_raw,
  seed, horizon)`; violação → `status = "undefined"` com o motivo. Stdlib, sem
  import do inference.
- **Critério de aceite (CA13; I14 — calib/teste por split e run; C9 lado
  montagem):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold/test_conformal_assembly.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): montagem das unidades conformais a partir do silver [7.2/task-14]`

---

### Task 15 — Port do consumidor `ConformalCalibration`, fake e contrato `[fake, real]`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/conformal_calibration.py`
  - `tests/fakes/features/evaluation/fake_conformal_calibration.py`
  - `tests/contract/features/evaluation/test_conformal_calibration_contract.py`
- **Arquivos a modificar:**
  - `tests/architecture/test_port_coverage_gate.py` (acréscimo
    `test_real_repo_conformal_ports_resolve`: `("evaluation",
    "ConformalCalibration")` → `CalibrateConformal` pela regra #93 e
    `("inference", "ConformalBackend")` com `"MapieCqrBackend" in port.adapters`
    — pertencimento, não igualdade, porque a lista de adapters é por citação —,
    cada um com o contrato que satisfaz o predicado do gate)
  - `tests/architecture/test_stage_7_2_regression_guards.py` (acréscimo
    `test_fake_conformal_calibration_reuses_the_supplier_rules`: AST do fake —
    importa `validate_command` e `calibration_set_for` de `calibrate_conformal`, não
    define função/método chamado `calibrate` nem importa `ConformalCalibrator`; cobre
    o ponto cego do `check_fake_parity.py`, que não olha use case)
- **Testes primeiro** (contrato `[fake, real]`; o módulo importa
  `FakeConformalCalibration` e `CalibrateConformal` **pelo nome**):
  `test_ok_unit_returns_one_result_per_pair_tail_variant_in_order`;
  `test_incomplete_input_unit_is_undefined`;
  `test_embargo_violation_unit_is_error_and_neighbours_ok`;
  `test_command_errors_raise` (unidade duplicada, variante desconhecida, ρ
  ausente para NEXCP); `test_non_ok_fields_are_none`;
  `test_test_limits_aligned_to_test_points`; só na perna fake:
  `test_fake_zero_corrections_give_the_native_quantiles`,
  `test_fake_forced_status` e `test_fake_raises_when_configured`.
- **O que fazer (concept §4; ADR 7.2.0003 item 3; LAYOUT §7, #93):**
  `ConformalCalibration.__call__(self, command: CalibrateConformalCommand) ->
  CalibrateConformalResult` — anotações **textualmente iguais** às do use case;
  os DTOs só sob `TYPE_CHECKING` (nenhuma aresta nova ainda). Fake do §1.
- **Critério de aceite (CA14, parte port):** suíte verde nas duas pernas;
  `check_port_coverage.py --list` mostra o port com fake, real `CalibrateConformal`
  e contrato, sem baseline.
- **Verificação (T3 — `tests/architecture/`):**
  ```bash
  uv run --no-sync pytest tests/contract/features/evaluation/test_conformal_calibration_contract.py tests/architecture/test_port_coverage_gate.py tests/architecture/test_stage_7_2_regression_guards.py -v --no-cov
  uv run --no-sync python scripts/check_port_coverage.py --list
  make check $PAR
  ```
- **Commit:** `feat(evaluation): port do consumidor ConformalCalibration com fake e contrato [7.2/task-15]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 13–15).

---

### Task 16 — `RefreshParameters.conformal_parameters` pela derivação única

> **> 5 arquivos, justificado:** o campo obrigatório quebra cada construção
> literal de `RefreshParameters` nos testes (mecânico; precedente: 6.6 Task 12).

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
  - `tests/unit/features/evaluation/test_refresh_command_from.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/unit/features/evaluation/test_scorecard_evidence_mapper.py` (teste do
    `check_manifest` para o campo novo)
  - construções de `RefreshParameters`:
    `tests/contract/features/evaluation/_gold_inputs.py`,
    `tests/contract/features/evaluation/test_gold_generation_reader_contract.py`,
    `tests/contract/features/evaluation/test_gold_store_contract.py`,
    `tests/integration/features/evaluation/test_refresh_gold.py`,
    `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_r0_and_r1_derive_no_conformal_parameters`;
  `test_plan_with_block_derives_the_block`;
  `test_check_manifest_refuses_a_divergent_conformal_block`
  (`MismatchField.PARAMETERS`);
  `test_manifest_without_conformal_parameters_is_corrupt` (C10, via
  `GoldGeneration.from_stored`); `test_conformal_parameters_type_refused`;
  `test_as_mapping_round_trip_with_block`.
- **O que fazer (concept §4 `RefreshParameters`; I16; ADR 7.2.0003 item 6):** o
  campo, a chave obrigatória em `_PARAMETER_KEYS`, `as_mapping`
  (`None` ou `as_payload()`) e `from_mapping`; `refresh_command_from` preenche com
  `prereg.conformal`.
- **Critério de aceite (I16 — derivação única; C10):** testes verdes; nenhuma
  outra construção de `RefreshParameters` fora da lista.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation tests/contract/features/evaluation tests/integration/features/evaluation/test_refresh_gold.py -q --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): bloco conformal na derivação única do refresh [7.2/task-16]`

---

### Task 17 — Relatórios conformais nos insumos do gold

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/refresh_gold.py`
    (passa `ConformalReports` vazio e `conformal_error_units = 0`; o port entra na
    Task 19)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py` (acréscimo:
    `conformal_error_units == 0`)
  - `tests/contract/features/evaluation/_gold_inputs.py` (`completed_inputs()` com
    `conformal_reports` cheios — unidades `ok`, `undefined` e `error`, cobertura
    por seed, uma cobertura `undefined`, média entre seeds com uma seed excluída;
    nova `completed_inputs_without_conformal()`)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_conformal_records_validate_their_fields`
  (`status ∈ {ok, undefined, error}`, `reason` obrigatório fora de `ok`, medidas
  `None` fora de `ok`, duas caudas por registro);
  `test_blocked_inputs_have_no_conformal_reports`;
  `test_completed_inputs_accept_conformal_reports`.
- **O que fazer (concept §4 `ConformalUnitRecord`/`ConformalReports`; ADR
  7.2.0003 item 5):** `ConformalTailRecord`, `ConformalUnitRecord`,
  `ConformalReports` e `EMPTY_CONFORMAL_REPORTS`; `GoldInputs.conformal_reports`
  (BLOCKED ⇒ vazio, coerência no `__post_init__`);
  `RefreshGoldResult.conformal_error_units`. **Nenhum import do inference** neste
  módulo (nem sob `TYPE_CHECKING`).
- **Critério de aceite (I14 — BLOCKED; base de CA15):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold tests/contract/features/evaluation -q --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): relatórios conformais nos insumos do gold [7.2/task-17]`

---

### Task 18 — Tabelas gold conformais: schema, builders e registro

> **> 5 arquivos, justificado:** os schemas entram em `GOLD_SCHEMAS`, e a regra
> "COMPLETED lista toda tabela" da 6.6 reprova o refresh wireado sem os builders
> registrados — schema, builders e registro têm de nascer no mesmo commit.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/conformal_corrections.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/conformal_coverage.py`
  - `tests/contract/features/evaluation/test_conformal_gold_builders.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
  - `src/financial_forecasting/composition_root.py` (registra os dois builders)
  - `tests/contract/features/evaluation/test_gold_builder_contract.py` (ids novos)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py` (conjuntos exatos de `GOLD_SCHEMAS`/`CONFIRMATORY_TABLES`)
  - `tests/unit/shared/test_composition_root.py` (`build_order` com 15 builders)
  - `tests/integration/features/evaluation/test_refresh_gold.py`: nova
    `_CONFORMAL_TABLES` e `_ALL_TABLES = _TABLES + _PROFILE_TABLES +
    _CONFORMAL_TABLES` (o conjunto exato contra `GOLD_SCHEMAS`); a asserção de
    "toda tabela com linhas" (`all(generation.tables[name] …)`, hoje na linha 453)
    passa a iterar `_TABLES + _PROFILE_TABLES` — o cenário desse arquivo é sem
    bloco `[conformal]`, então as conformais vêm vazias —; asserção nova de que as
    duas de `_CONFORMAL_TABLES` existem com zero linhas; docstring "treze" →
    "quinze"
- **Testes primeiro** (`test_conformal_gold_builders.py`):
  `test_corrections_rows_cell_by_cell` (inclusive Beta nula no NEXCP e com l = 0);
  `test_infinite_correction_maps_to_null_with_flag`;
  `test_non_ok_unit_maps_to_two_tail_rows_with_reason`;
  `test_undefined_assembly_unit_expands_to_every_pair_and_variant`;
  `test_coverage_rows_cell_by_cell` (caudas por `band_level`, par, aninhamento,
  linha de média com `seed` nulo, c̄/n̄ e `mean_of_seed_coverages` lado a lado);
  `test_infinite_mpiw_maps_to_null_with_flag`;
  `test_undefined_coverage_rows_carry_the_reason` (forma fixa do §1, sem colisão
  de chave); `test_not_applicable_coverage_rows_carry_status_and_null_measures`;
  `test_seed_mean_with_zero_complete_seeds_rows` e
  `test_seed_mean_with_one_seed_has_null_sd`;
  `test_non_integer_folds_do_not_collide` (dois `fold_raw` não inteiros, `fold`
  nulo nos dois, `GoldTable` aceita);
  `test_label_on_every_ok_coverage_row` (I9);
  `test_without_conformal_inputs_both_tables_are_empty`.
- **O que fazer (concept §4 "Evaluation — application e gold"; ADR 7.2.0003 item
  7):** `GOLD_CONFORMAL_CORRECTIONS` e `GOLD_CONFORMAL_COVERAGE` (colunas do §1),
  em `GOLD_SCHEMAS` e `CONFIRMATORY_TABLES`; builders de mapeamento puro,
  `depends_on = {QUALITY_CHECKS}`, `runs_when_blocked = False`; registro no
  `RefreshGold` do composition root.
- **Critério de aceite (I14 — mesma geração, zero linhas sem bloco, BLOCKED sem
  elas, COMPLETED sem uma é corrompida):** testes verdes; integração: as duas
  tabelas na geração (zero linhas — o port entra na Task 19), BLOCKED sem elas.
- **Verificação (T2 — composition root):**
  ```bash
  uv run --no-sync pytest tests/contract/features/evaluation tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py tests/integration/features/evaluation/test_refresh_gold.py -q --no-cov
  make check-block $PAR
  ```
- **Commit:** `feat(evaluation): tabelas gold das correções e da cobertura conformais [7.2/task-18]`

---

### Task 19 — `RefreshGold` calcula a cobertura conformal pelo port

> **> 5 arquivos, justificado:** o construtor novo obriga o composition root; a
> aresta de runtime `refresh_gold → calibrate_conformal` obriga `.importlinter`,
> o caso de arquitetura e LAYOUT §7 no mesmo commit.

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/refresh_gold.py`
  - `src/financial_forecasting/composition_root.py` (`conformal_calibration=CalibrateConformal()`)
  - `.importlinter` (ignore da aresta, com comentário: ADR 7.2.0003 item 3, ADR
    0.0.0053 item 3; exceção do **módulo**, não do slice)
  - `docs/LAYOUT.md` §7 (a aresta nova; contagem de arestas de runtime 27 → 28)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
  - `tests/unit/shared/test_composition_root.py`
  - `tests/architecture/test_import_contracts.py`
  - `tests/architecture/test_stage_7_2_regression_guards.py`
- **Arquivos a criar:** nenhum.
- **Testes primeiro:**
  - use case (com `FakeConformalCalibration`):
    `test_one_port_call_with_only_the_ok_assembly_units`;
    `test_assembly_undefined_units_become_rows_without_reaching_the_port`;
    `test_port_error_unit_counts_and_makes_that_coverage_undefined` (a mesma seed
    em outro horizonte e as outras seeds publicadas; `conformal_error_units == 1`);
    `test_port_exception_propagates_and_nothing_is_published`;
    `test_without_block_the_port_is_not_called`;
    `test_blocked_generation_does_not_call_the_port`;
    `test_verdict_inputs_identical_with_and_without_block` (I15:
    `horizon_reports`, `mcs_reports`, `profile_reports`, `check_results`,
    `block_estimates`);
    `test_conformal_n_evaluated_equals_the_native_n` (I8/I14);
    `test_limits_joined_by_target_not_by_position` (unidades dos folds devolvidas
    pelo fake em ordem invertida ⇒ mesma cobertura);
    `test_seed_mean_over_complete_seeds_only`.
  - composition root: `test_refresh_gold_wires_calibrate_conformal`.
  - arquitetura: caso de quebra
    `bc-independence:other-evaluation-module-imports-calibrate-conformal` (outro
    módulo do evaluation que importe `calibrate_conformal` reprova; a aresta
    declarada fica verde em `test_real_repo_has_zero_broken_contracts`); guardas
    `test_evaluation_dtos_builders_and_domain_never_import_inference` (AST,
    inclusive `TYPE_CHECKING`: `application/dtos/**`, `domain/**`,
    `adapters/out/duckdb/gold_builders/**`),
    `test_conformal_calibration_port_imports_inference_only_for_typing` e
    `test_refresh_gold_imports_only_calibrate_conformal_from_inference`.
- **O que fazer (concept §1 item 6, I8, I14, I15, C9; ADR 7.2.0003 item 5):**
  construtor `conformal_calibration: ConformalCalibration`; etapa
  `_timed("conformal", …)` depois de `mcs_blocks`, só sem bloqueio e com
  `parameters.conformal_parameters`: `ConformalAssembly.assemble` (séries nativas
  completas do candidato por seed, `levels` da amostra) → uma chamada ao port com
  as unidades `ok` (nenhuma `ok` ⇒ sem chamada) → mapeamento para
  `ConformalUnitRecord` (só neste módulo) → por (seed, horizonte, variante)
  completo, limites por ponto unidos à série nativa **por `target_timestamp`**,
  `ConformalCoverage.evaluate` (`degeneracy_tolerance`, `band_levels` do plano) →
  `seed_mean` por (horizonte, variante) com `expected_seeds` = as seeds do
  candidato; (seed, horizonte, variante) com unidade não-`ok` → linha `undefined`
  com o motivo. Cada `error` soma 1 a `conformal_error_units`; exceção do port
  propaga.
- **Critério de aceite (CA14 — aresta única; parte de CA6 "unidade não-`ok`";
  I14, I15; C9):** testes verdes; `lint-imports` com exatamente uma aresta nova.
- **Verificação (T3):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py tests/unit/shared/test_composition_root.py tests/architecture -q --no-cov
  uv run --no-sync lint-imports
  git -C "$WTH" diff "$BASE" -- .importlinter | grep -cE '^\+\s*financial_forecasting\..* -> '   # = 1
  make check $PAR
  ```
- **Commit:** `feat(evaluation): refresh do gold calcula a cobertura conformal pelo port [7.2/task-19]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 16–19).

---

### Task 20 — Ponta a ponta do refresh conformal sobre silver sintético

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_conformal_refresh_end_to_end.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (silver sintético em `tmp_path` com calib e teste do
  candidato, dois folds, duas seeds, h ∈ {1, 7}, com **`value_raw ≠
  value_guardrail` em parte das linhas** — grade crua cruzada, `guardrail_applied =
  1` —, para que a troca de coluna mude o resultado (I2); planos sintéticos r1 e r2 por
  `r1_payload()`/`r2_payload()` com `cohort_id` sintético; padrão do
  `test_profiles_end_to_end.py`):
  `test_completed_generation_has_both_conformal_tables` (linhas > 0; manifesto com
  `conformal_parameters == r2.conformal.as_payload()`);
  `test_conformal_n_evaluated_equals_native_n_observed` (por seed, horizonte,
  par e cauda contra a linha da `gold_calibration_table` com `model` = candidato,
  `sample = "model_full"`, `kind` da cauda, `level_low` = τ,
  `includes_degenerate = false`, `dgt_offset` nulo; a linha de média com n̄ = a
  média deles — I14);
  `test_zero_corrections_coverage_equals_native` (`FakeConformalCalibration` no
  `RefreshGold` montado com os adapters reais de arquivo);
  `test_r1_plan_writes_empty_conformal_tables`;
  `test_blocked_generation_has_no_conformal_tables`;
  `test_port_error_unit_row_count_and_undefined_coverage` (fake com
  `force_status`);
  `test_r1_and_r2_refreshes_same_verdict_and_same_tables` (I10/I15: dois refreshes
  do mesmo silver; `ScorecardVerdict` igual; tabelas da 6.4–6.6 iguais sem
  `preregistration_ref`; manifesto difere só em `preregistration_ref` (topo e
  `parameters`), `parameters.conformal_parameters`, as contagens das duas tabelas
  conformais e os timestamps do `Clock`);
  `test_real_use_case_through_the_composition_root` (`wire_dependencies`,
  `refresh_command_from(r2 sintética)`, modelo base estreito:
  `conformal_error_units == 0`, uma linha escolhida de `gold_conformal_corrections`
  igual, campo a campo, ao `ConformalCalibrator.calibrate` sobre o mesmo calib
  montado do `value_guardrail`, e diferente do calculado sobre o `value_raw` numa
  unidade com linha cruzada).
- **O que fazer (concept CA15, I10, I15, I16):** como acima.
- **Critério de aceite (CA15; CA8, parte "dois refreshes"; I10, I14, I15, I16):**
  testes verdes; nenhum teste lê o `parent_sweep_id` do cohort real.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/integration/features/evaluation/test_conformal_refresh_end_to_end.py -v --no-cov
  make check-task SLICE='evaluation inference' $PAR
  ! grep -rn "aapl_confirmatory-r0-665f45d9169a" "$WTH/tests" --include=*.py | grep -v test_preregistration_consistency
  ```
- **Commit:** `test(evaluation): ponta a ponta do refresh conformal sobre silver sintético [7.2/task-20]`

---

### Task 21 — Prova de geometria do calib sobre o cohort real (ativada por ambiente)

- **Arquivos a criar:**
  - `tests/integration/features/inference/test_conformal_geometry_real_cohort.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:**
  - sempre rodam (sintéticos, em `tmp_path`): `test_requested_columns_exclude_values_and_target`
    (as tuplas literais `_DIM_RUN_COLUMNS`, `_FACT_COLUMNS` e `_GRID_COLUMNS` não
    têm `value_*` nem `target_return`); `test_checks_pass_on_a_consistent_synthetic_root`;
    `test_checks_fail_on_a_planted_violation` (parametrizado: fingerprint
    divergente, decisão de calib fora do `FoldSplit.calib`, calib ∩ `early_stop`,
    alvo de calib ≥ `test[0]`, manifesto com 59 `completed`).
  - pulado sem `FF_REAL_COHORT_DATA_ROOT` (e **falha**, não pula, se a variável
    aponta para caminho inexistente): `test_real_cohort_calib_geometry` — por run
    do candidato, `SplitFingerprint` recomposto = `dim_run.split_fingerprint`;
    decisões de calib no silver = `FoldSplit.calib` (h+1 e h+7); interseção com
    `early_stop` vazia; todo `target_timestamp_utc` de calib < `test[0]`;
    manifesto com 60 entradas `completed`; imprime a linha-resumo da Etapa G.
- **O que fazer (concept D8, I12, C7):** leitura por `pyarrow` com `columns=`
  explícito (só as colunas das três tuplas); o `WalkForwardSplitter` é recomposto
  pela geometria do `CohortSpec` (`config/cohorts/aapl_confirmatory.toml`, leitor
  existente) sobre as sessões da grade, **sem reimplementar o splitter**; o
  `cohort_id` vem do `CohortHash` do spec (nunca literal no teste). Nenhum `gold/`
  criado; nada é escrito.
- **Critério de aceite (CA10, parte código; I12):** testes sintéticos verdes; o
  real pulado no T1.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/integration/features/inference/test_conformal_geometry_real_cohort.py -v -rs --no-cov
  make check-task SLICE=inference $PAR
  ```
- **Commit:** `test(inference): prova de geometria do calib sobre o cohort real, ativada por ambiente [7.2/task-21]`

---

### Task 22 — Emenda cega r2, espelho e consistência

- **Arquivos a criar:**
  - `config/preregistration/aapl_confirmatory-r2.toml`
- **Arquivos a modificar:**
  - `docs/preregistration/aapl_confirmatory.md`
  - `tests/integration/features/evaluation/test_preregistration_consistency.py`
- **Testes primeiro:** `test_every_revision_hash_quoted` com a lista `[r0, r1, r2]`;
  `test_r2_equals_r1_except_amendment_and_conformal` (todo campo igual salvo
  `revision`, `amends`, `justification`, `blind_status`, `conformal`);
  `test_r2_amends_r1_blinded` (`amends = "aapl_confirmatory-r1-bfa8028498ca"`,
  `blind_status = "blinded"`, justificativa sem afirmação sobre o passado);
  `test_r2_conformal_block_is_the_catalog_values` (= `conformal_parameters()` do
  helper; par primário = par do `h1_gate`); `test_r0_and_r1_hashes_unchanged`;
  `test_r0_to_r2_chain_read_by_the_source` (`TomlPreregistrationSource`).
- **O que fazer (concept §1 item 7, I11; ADR 7.2.0001 itens 1–2):** r2 = r1
  literal salvo `revision = 2`, a emenda e `[conformal]` (§1); espelho com a seção
  "Revisão r2" (hash completo, o que muda, declaração de cegamento). Arquivos de
  revisões ancoradas não são editados.
- **Critério de aceite (CA8 menos a âncora; I11):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/integration/features/evaluation/test_preregistration_consistency.py -v --no-cov
  git -C "$WTH" diff --exit-code "$BASE" -- config/preregistration/aapl_confirmatory-r0.toml config/preregistration/aapl_confirmatory-r1.toml
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): emenda cega r2 com o bloco conformal [7.2/task-22]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 20–22).

---

### Etapa G — Prova de geometria do calib sobre o cohort real (sem métrica)

Não é Task numerada (concept D8): não produz código. Roda **depois** da Task 22,
com a árvore limpa e `make check` verde no HEAD. Evidência literal em §7
(`[deviation] etapa-g`), num commit
`docs(inference): evidência da prova de geometria real [7.2/--]`.

**G0 — Pré-condições (host, Git Bash; variáveis do §1).**
```bash
SCRATCH=<diretório de scratchpad da sessão, caminho absoluto, fora do repo>
git -C "$WTH" status --short                      # vazio
docker ps --format '{{.Names}} {{.Mounts}}'       # nenhum container usando data/cohorts/aapl
ls -a "$MAINH/data/cohorts/aapl" | tee "$SCRATCH/g0-ls.txt"   # sem gold/ nem .writer.lock
ls "$MAINH/data/cohorts/aapl/inference/aapl_confirmatory-r0-665f45d9169a"   # manifest.json
touch "$SCRATCH/g0-marker"                                    # referência de tempo do G2
```

**G1 — Execução (o `data_root` do checkout principal montado SOMENTE LEITURA, fora
de `/app`; `.git` somente leitura; volume `ff72-venv`).**
```bash
MSYS_NO_PATHCONV=1 docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
  -v $WTD:/app -v $MAIND/.git:/main.git:ro \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl:/real/aapl:ro \
  -v financial-forecasting_ff72-venv:/app/.venv \
  -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0 \
  -e FF_REAL_COHORT_DATA_ROOT=/real/aapl -w /app financial_forecasting-app:dev \
  sh -c "$PRE; uv run --no-sync pytest tests/integration/features/inference/test_conformal_geometry_real_cohort.py -v -s -rs -p no:cacheprovider --no-cov" \
  2>&1 | tee "$SCRATCH/geometry.log"; echo "EXIT=${PIPESTATUS[0]}"
```

**Saída esperada:** `EXIT=0`; todos os testes `PASSED` e **nenhum** `SKIPPED`
(`test_real_cohort_calib_geometry` incluído); a linha-resumo
`geometry aapl_confirmatory-r0-665f45d9169a: 60 runs (6 folds x 10 seeds); fingerprint ok 60/60; calib = FoldSplit.calib 60/60 (h1, h7); calib ∩ early_stop = 0; max calib target < test[0] 60/60; manifest completed 60/60; calib rows 211680`
(252 decisões × 2 horizontes × 7 níveis = 3.528 por run).

**G2 — Depois.**
```bash
ls -a "$MAINH/data/cohorts/aapl" | diff "$SCRATCH/g0-ls.txt" - && echo DATA_ROOT_UNCHANGED   # sem gold/
find "$MAINH/data/cohorts/aapl" -newer "$SCRATCH/g0-marker" | wc -l                         # 0
```

Colar em §7: G0 (`ls`), a linha-resumo, a linha final do pytest e o G2.

**Se falhar** (nunca relaxar o critério — C7; nunca editar o silver):

| Sintoma | Ação |
|---|---|
| `test_real_cohort_calib_geometry` `SKIPPED` | a variável não chegou ao container: corrigir o comando; não registrar como evidência |
| Fingerprint ≠ `dim_run.split_fingerprint`, decisões ≠ `FoldSplit.calib`, interseção com `early_stop` ou alvo ≥ `test[0]` | **HALT**; `[finding]` em §7 com run, fold, seed e a diferença; diagnosticar (geometria do spec, grade aparada, convenção do `target_timestamp`) antes de qualquer correção; a âncora (Task 23) não roda |
| Manifesto sem 60 entradas `completed` | **HALT**; `[finding]`; a 7.1 não fechou como registrado — perguntar ao humano |
| Recompor a grade exige `target_return` ou `value_*` | **HALT** e perguntar (I12 proíbe a leitura; nenhuma coluna é acrescentada sem decisão) |
| `Read-only file system` ou tentativa de escrita | é defeito do teste (ele não escreve): corrigir o teste numa Task `-fix`, nunca remover o `:ro` |

---

### Task 23 — Âncora da r2 (última antes do PR)

- **Arquivos a criar:**
  - `config/preregistration/aapl_confirmatory-r2.anchor.toml`
- **Arquivos a modificar:**
  - `docs/preregistration/aapl_confirmatory.md`
  - `tests/integration/features/evaluation/test_preregistration_consistency.py`
- **O que fazer (ADR 6.5.0003; ADR 7.2.0001 item 4 — depois da Etapa G e da
  Auditoria de Testes, com a r2 inalterada desde a Task 22):**
  `COMMIT=$(git -C "$WTH" log -1 --format=%H -- config/preregistration/aapl_confirmatory-r2.toml)`
  (o último commit que tocou o arquivo — nunca um hash digitado);
  `git tag preregistration/<ref-r2> "$COMMIT"`; `git push origin <tag>`;
  comentário na **#158** com `preregistration_ref`, hash completo, tag, commit,
  `cohort_id` e hash do cohort; `created_at` do comentário lido pela API
  (`gh api`) e gravado no `.anchor.toml` (tag, commit, comment_url, anchored_at);
  seção "Âncora r2" no espelho. Rede ou permissão falhou → não gravar
  `.anchor.toml`, repetir; nunca inventar `anchored_at` (C8). **Depois da tag,
  nenhum rebase da branch** (o commit marcado tem de continuar no histórico do PR):
  atualização com o `develop` só por merge.
- **Testes primeiro:** `test_r2_anchor_after_r1` (o `TomlPreregistrationSource` lê
  r0, r1 e r2 com âncora; `anchored_at(r2) > anchored_at(r1)`; tag =
  `preregistration/<ref>`; `"/issues/158#issuecomment-"` no `comment_url`; URL e
  commit citados no espelho).
- **Critério de aceite (CA9; I11):** teste verde.
- **Verificação (T1):**
  ```bash
  git -C "$WTH" ls-remote --tags origin "preregistration/aapl_confirmatory-r2-*"
  git -C "$WTH" merge-base --is-ancestor "$COMMIT" HEAD && echo TAGGED_COMMIT_IN_HISTORY
  # corpo do comentário pela API, conferido campo a campo (ID = o id do comentário do .anchor.toml)
  gh api repos/MarceloSanC/financial-forecasting/issues/comments/$ID --jq .body > "$SCRATCH/anchor-comment.txt"
  for s in "$REF" "$FULL_HASH" "preregistration/$REF" "$COMMIT" "$COHORT_ID" "$COHORT_HASH"; do grep -qF "$s" "$SCRATCH/anchor-comment.txt" || echo "MISSING $s"; done   # nenhuma linha
  uv run --no-sync pytest tests/integration/features/evaluation/test_preregistration_consistency.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `chore(evaluation): âncora da revisão r2 do pré-registro [7.2/task-23]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check $PAR                                                       # T3, idêntico ao CI (no container)
uv run --no-sync pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing -q   # cada arquivo de src/ tocado >= 90%
uv run --no-sync python scripts/check_port_coverage.py
git -C "$WTH" diff --exit-code "$BASE" -- scripts/arch_baseline.toml
grep -n 'violating == \["Hasher"\]' "$WTH/tests/architecture/test_port_coverage_gate.py"
python scripts/check_technical_postexec.py docs/stages/7.2-conformal-cqr/technical.md
! grep -rn "aapl_confirmatory-r0-665f45d9169a" "$WTH/tests" --include=*.py | grep -v test_preregistration_consistency
```

### Verificações funcionais
- [ ] Ponta a ponta sintético (Task 20): geração COMPLETED com as duas tabelas
      conformais, n conformal = n nativo, r1 e r2 com o mesmo veredito, use case
      real pelo composition root com `conformal_error_units == 0`.
- [ ] **Último quilômetro:** as tabelas gold conformais são dado novo, mas o
      cegamento (I12) proíbe produzi-las sobre o cohort real nesta Stage; a
      verificação de ponta a ponta é a da Task 20 sobre silver sintético, com os
      adapters reais de arquivo, e o primeiro refresh real é o da 8.1.
- [ ] Etapa G concluída com a saída esperada, colada em §7; `data_root` intocado.
- [ ] r2 ancorada (Task 23) depois da Etapa G e da auditoria de testes.

### Checklist de fechamento
- [ ] 23 Tasks commitadas, cada uma com o seu gate verde; Checkpoints C nas
      fronteiras de §4 com disposições registradas em §7
- [ ] Auditoria de testes (subagente) com todos os itens "sim", inclusive mutação
      das regras críticas (posto exato, orientação/normalização do NexCP, máscara,
      join por `target_timestamp`, status por unidade, campos da r2)
- [ ] `docs/roadmap.md`: 7.2 `done`, `updated_at` e `last_reviewed_at` de hoje,
      linha no histórico (commit `docs(roadmap): … [7.2/--]`); commit
      `stage 7.2: complete`
- [ ] ADRs 7.2.0001–0005 `accepted` (já estão)
- [ ] PR contra `develop` com `Closes #158`
- [ ] Depois do merge: `docker volume rm financial-forecasting_ff72-venv` (o
      volume dedicado da branch não sobrevive à Stage)
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
inference:  01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08
evaluation: 09 (após 08) ─► 10 ;  11 ─► 12 ;  13 ─► 14 ;  15 (após 08)
gold:       12 ─► 16 ─► 17 ─► 18 ─► 19 (após 14 e 15) ─► 20
fecho:      21 ─► 22 (após 12) ─► [Etapa G] ─► (auditoria de testes) ─► 23
```

- 01 cria `domain/services/`; 02 antes de 03 (o calibrador consome o VO); 03 antes
  de 04 (o NEXCP estende o serviço); 05 antes de 06/07 (o contrato e o `mapie`
  antes do adapter); 06 antes de 07 (port antes do adapter); 03/04 antes de 08; 08 e
  09 antes de 10; 08 antes de 15 (o real do port); 11 antes de 12 (o VO antes do
  plano); 13 antes de 14 (as regras públicas antes da montagem); 12 antes de 16; 16
  antes de 17; 17 antes de 18 (os insumos dos builders); 14, 15 e 18 antes de 19;
  19 antes de 20; a Etapa G depois de 21 e 22; 23 por último.
- A ordem linear de §2 (01 → 23) respeita todas essas arestas.
- **Checkpoint C** (T2 `make check-block $PAR` + revisão do diff) depois de 04, 08,
  12, 15, 19 e 22.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| MAPIE 1.5 recusa o envoltório `prefit` de predições dadas | o adapter chama a função pública de mais baixo nível do MAPIE que calcula o quantil conformal sobre os escores; `[decision]` em §7 (concept §10) |
| `uv lock` com `mapie` muda numpy/scikit-learn | HALT (contrato externo); perguntar antes de aceitar a mudança de versão |
| `uv sync --locked --inexact --extra dev` sobre a cópia do venv compartilhado (Task 05) muda pacote além do `mapie` e das suas dependências novas | parar; `uv lock --check` e o diff do `uv.lock` dizem se o lock mudou; nenhum `uv sync` sem `--extra dev` (desinstala pytest, mypy, ruff e import-linter); `[deviation]` |
| Zip dos autores indisponível na Task 04 | gerar do código já baixado na verificação do concept (sha256 registrado); sem ele, NexCP só por casos analíticos e o oráculo vira `[finding]` (concept §10) |
| Caso da fixture na fronteira float × exato | o gerador descarta casos a menos de 1e-9 de 1 − α; caso que diverge no golden = bug da transcrição, nunca tolerância |
| A prova sintética (Task 10) passa de 120 s | `pytest.mark.slow` (sai só do T1) e `[deviation]`; nunca baixar R abaixo do piso do CA7 |
| Refactor do `SeriesAssembly` (Task 13) muda texto de achado | o `detail` é copiado byte a byte; diferença = bug da extração, nunca asserção atualizada |
| `check_port_coverage.py` não reconhece o `CalibrateConformal` como real | alinhar o texto das anotações do port ao do use case; nunca entrada nova no baseline |
| Recompor a grade na Etapa G exige coluna proibida | HALT e perguntar (I12) |
| Prova de geometria acusa divergência | HALT (C7), diagnóstico antes de qualquer correção; a âncora espera |
| Âncora falha (rede/permissão) | não gravar `.anchor.toml`; repetir; nunca inventar `anchored_at` (C8) |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs
  [7.2.0001](../../adr/7_2_0001-cqr-preregistration-details.md),
  [7.2.0002](../../adr/7_2_0002-own-cqr-in-domain-mapie-oracle-nexcp-fixture.md),
  [7.2.0003](../../adr/7_2_0003-conformal-intervals-on-demand-gold-via-refresh-gold.md),
  [7.2.0004](../../adr/7_2_0004-conformal-coverage-series-embeds-native-series.md),
  [7.2.0005](../../adr/7_2_0005-reproduction-policy-in-inference-domain.md);
  consumidos: 0.0.0053, 0.0.0055, 6.1.0005, 6.2.0006, 6.4.0008, 6.5.0003, 6.6.0002
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3; [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) Passos 6–10 e §Gates em camadas
- Technicals [7.1](../7.1-inference-engine/technical.md) (forma, Etapa E, §7 F3) e
  [6.6](../6.6-scorecard-profiles/technical.md) (parâmetros, builders, r1 e âncora)
- Skills: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `composition-root`, `import-linter-rules`, `ddd-tactical-patterns`
- Issue [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158)

### Matriz de rastreabilidade (concept §11, §5, §6 → Task → teste)

**Critérios de aceite**

| # | Critério (concept §11) | Task(s) | Teste / evidência |
|---|---|---|---|
| CA1 | F3: política no domain; 7.1 verde sem mudar asserção; sem aresta nova | 01 | `test_reproduction_policy.py::*`; suíte da 7.1; diff só de import; `lint-imports` |
| CA2 | Posto exato (248, 228, 190), n pequenos, α_hi de 0,9 = α_lo de 0,1, k > n ⇒ +∞, empates, sinais | 03 | `test_conformal_calibrator.py::{test_rank_at_n_252_for_the_three_tail_alphas, test_rank_small_n_table, test_upper_alpha_of_0_9_is_exactly_one_tenth, test_rank_above_n_is_infinite_and_not_clipped, test_ties_counted_with_multiplicity, test_score_sides, test_negative_scores_shrink_positive_widen}` |
| CA3 | NexCP: golden do `splitCP_LS`; ρ = 1 ≡ sem pesos; massa ⇒ +∞; n = 252, 0,02: ρ 0,99 finito, 0,98 infinito | 04 | `test_nexcp_oracle_fixture.py::*`; `test_nexcp_weighted_threshold.py::{test_rho_one_equals_the_unweighted_rank, test_insufficient_mass_is_infinite, test_n_252_tail_002_finite_at_099_infinite_at_098, test_most_recent_point_weighs_rho, test_normalization_counts_the_test_point_weight}` |
| CA4 | Oráculo MAPIE `[fake, mapie]` nos n de coincidência; +1 num n divergente; `inference-no-mapie-leak` com quebra; port-coverage | 05, 06, 07 | `test_conformal_backend_contract.py::*`; `test_import_contracts.py::inference-no-mapie-leak:{inference-domain-imports-mapie, inference-application-imports-mapie, inference-application-imports-numpy, inference-domain-imports-numpy, inference-domain-imports-scipy, inference-application-imports-sklearn}`; `check_port_coverage.py` (Task 07, sem baseline) |
| CA5 | Calib dedicado e embargo: recusas do VO; erro por unidade com vizinhas intactas; `undefined`; erros de comando antes de qualquer unidade; uma calibração por unidade na ordem | 02, 08 | `test_conformal_embargo.py::*`; `test_conformal_calib_set_dedicated.py::*`; `test_calibrate_conformal.py::*` |
| CA6 | Cobertura: = `CoverageMetrics` com correção zero; máscara; empates; cruzado; infinito; rótulo; 100 % degenerada; unidade não-`ok` ⇒ `undefined`; `seed_mean`; Beta `None` com l = 0 | 09, 19, 03 | `test_conformal_coverage.py::*`; `test_refresh_gold_use_case.py::test_port_error_unit_counts_and_makes_that_coverage_undefined`; `test_conformal_calibrator.py::test_beta_reference_none_when_l_is_zero` |
| CA7 | Prova sintética (R = 1000 / 200, três pares, faixa teórica, lado da garantia, estreito alarga, largo encolhe) | 10 | `test_cqr_empirical_coverage.py::*` |
| CA8 | `Preregistration` lê r0–r2; hashes r0/r1 inalterados; C4 (com `"aci"`/`"enbpi"`); catálogo = `ConformalVariant`; dois refreshes r1 × r2; espelho e consistência | 11, 12, 20, 22 | `test_conformal_parameters.py::*`; `test_conformal_catalog_matches_variants.py::*`; `test_preregistration_value_object.py` (casos novos); `test_conformal_refresh_end_to_end.py::test_r1_and_r2_refreshes_same_verdict_and_same_tables`; `test_preregistration_consistency.py::{test_every_revision_hash_quoted, test_r2_equals_r1_except_amendment_and_conformal, test_r0_to_r2_chain_read_by_the_source}` |
| CA9 | Âncora: tag, comentário na #158, `.anchor.toml` posterior à r1, cadeia r0 → r2 com âncoras | 23 | `test_preregistration_consistency.py::test_r2_anchor_after_r1`; `git ls-remote --tags`; `merge-base --is-ancestor` do commit marcado; corpo do comentário por `gh api` com `grep -F` de ref, hash completo, tag, commit, `cohort_id` e hash do cohort |
| CA10 | Geometria real verde no container, `:ro`, saída em §7, sem `gold/`, colunas listadas | 21, Etapa G | `test_conformal_geometry_real_cohort.py::*`; saída de G1/G2 em §7 |
| CA11 | Roadmap e LAYOUT §7 emendados; `make docs-check` verde | concept (`ce772b8`), 05, 19, §3 | diff do LAYOUT §7 nas Tasks 05 e 19; linha do histórico do roadmap; `make docs-check` |
| CA12 | `make check` verde | §3 | saída do `make check` no relatório |
| CA13 | Montagem: calib/teste por split e run; realizado; fold por ponto; `undefined` com motivo por regra; fold não inteiro; join por `target_timestamp` | 13, 14 | `test_series_assembly_rules.py::*`; `test_conformal_assembly.py::*` |
| CA14 | Port `[fake, real]` com os três status e erros de comando; port-coverage; exatamente uma aresta nova | 15, 19 | `test_conformal_calibration_contract.py::*`; `test_port_coverage_gate.py::test_real_repo_conformal_ports_resolve`; `test_import_contracts.py::bc-independence:other-evaluation-module-imports-calibrate-conformal`; `test_real_repo_has_zero_broken_contracts` |
| CA15 | Refresh sintético: COMPLETED com as duas tabelas; manifesto; n conformal = nativo; correção zero = nativa; r1 vazio; BLOCKED; `error` contado; I15; C10; use case real pelo composition root | 16, 17, 18, 19, 20 | `test_conformal_refresh_end_to_end.py::*`; `test_refresh_gold_dtos.py::test_manifest_without_conformal_parameters_is_corrupt`; `test_conformal_gold_builders.py::*` |

**Invariantes**

| # | Invariante (concept §5) | Task(s) | Teste / evidência |
|---|---|---|---|
| I1 | Registro único no domain; sem mapie/numpy/sklearn/scipy; nenhum use case chama o backend | 03, 04, 05, 06 | `inference-no-mapie-leak:*`; `test_only_the_mapie_adapter_imports_the_conformal_backend_port` |
| I2 | Escores sobre o vetor rearranjado | 03, 08, 14, 20 | `test_score_sides`; `test_test_limits_aligned_to_the_test_points`; `test_grids_use_value_guardrail_not_value_raw`; `test_real_use_case_through_the_composition_root` (silver com `value_raw ≠ value_guardrail`) |
| I3 | Posto exato, empates, +∞ sem corte | 03 | CA2 |
| I4 | NexCP: orientação, normalização +1, empates, massa ⇒ +∞, ρ = 1 ≡ I3, ρ exato | 04 | CA3; `test_calibrate_passes_exact_geometric_weights` |
| I5 | Saída sem rearranjo, ±∞ sinalizado | 03, 08, 18 | `test_limits_are_not_rearranged`; `test_infinite_correction_maps_to_null_with_flag` |
| I6 | Uma calibração por (fold, seed, h, par, cauda, variante) | 08 | `test_one_calibration_per_unit_pair_tail_variant_in_order` |
| I7 | Calib dedicado e embargo; Q̂ só do calib; status por unidade | 02, 08 | CA5 |
| I8 | Cobertura no evaluation sobre a máscara nativa; n idêntico; Wilson; não-`ok` ⇒ `undefined`; duas médias | 09, 19 | CA6; `test_conformal_n_evaluated_equals_the_native_n` |
| I9 | Rótulo exato validado | 09, 18 | `test_label_is_exact_and_validated`; `test_label_on_every_ok_coverage_row` |
| I10 | Sem veredito: dois refreshes r1 × r2, mesmo `ScorecardVerdict`, manifesto difere só nos campos listados | 20 | `test_r1_and_r2_refreshes_same_verdict_and_same_tables` |
| I11 | r2 = r1 salvo emenda e bloco; hashes r0/r1; cega; âncora posterior | 12, 22, 23 | `test_r2_equals_r1_except_amendment_and_conformal`; `test_r0_and_r1_hashes_unchanged`; `test_r2_anchor_after_r1` |
| I12 | Cegamento: nada sobre o cohort real; a Etapa G não lê valores | 20, 21, Etapa G | `test_requested_columns_exclude_values_and_target`; `grep` do `cohort_id` (§3); mount `:ro` |
| I13 | F3 sem regressão; domain do inference sem modeling | 01 | suíte da 7.1; `bc-independence` sem aresta nova |
| I14 | Gold: mesma geração, zero linhas sem bloco, COMPLETED sem uma é corrompida, BLOCKED sem elas; calib/teste por split; n conformal = n nativo | 14, 17, 18, 20 | `test_without_conformal_inputs_both_tables_are_empty`; `test_blocked_generation_has_no_conformal_tables`; `test_conformal_n_evaluated_equals_native_n_observed`; regra da 6.6 em `test_refresh_gold_dtos.py` |
| I15 | Isolamento: unidade não aborta; tabelas 6.4–6.6 e veredito idênticos com e sem bloco | 19, 20 | `test_verdict_inputs_identical_with_and_without_block`; `test_r1_and_r2_refreshes_same_verdict_and_same_tables` |
| I16 | Derivação única; ids do catálogo = `ConformalVariant`; e2e real com `conformal_error_units == 0` | 11, 16, 20 | `test_catalog_variant_ids_are_exactly_the_conformal_variant_values`; `test_plan_with_block_derives_the_block`; `test_real_use_case_through_the_composition_root` |
| I17 | ACI/EnbPI ausentes | 04, 08, 11 | `test_variant_has_exactly_the_two_members`; `test_command_errors_raise_before_any_unit` (`"aci"`); `test_identifier_outside_the_catalog_refused` |

**Casos de erro**

| # | Caso (concept §6) | Task(s) | Teste / evidência |
|---|---|---|---|
| C1 | VO/série/comando inválido → `ValueError` nomeando o campo | 02, 08, 09 | `test_conformal_embargo.py::*`; `test_conformal_coverage_series.py::*` |
| C2 | α < 1/(n+1) ou massa insuficiente → +∞, não erro | 03, 04 | `test_rank_above_n_is_infinite_and_not_clipped`; `test_insufficient_mass_is_infinite` |
| C3 | Erros de comando antes de qualquer unidade | 08, 15 | `test_command_errors_raise_before_any_unit`; `test_conformal_calibration_contract.py::test_command_errors_raise` |
| C4 | `[conformal]` no r0, id fora do catálogo, chave desconhecida/ausente, par primário ≠ gate, par fora da grade | 11, 12 | `test_conformal_parameters.py::*`; `test_conformal_block_forbidden_in_revision_0`; `test_primary_pair_must_be_the_h1_gate_pair`; `test_conformal_pairs_must_be_in_quantile_levels` |
| C5 | MAPIE recusa n pequeno (medido no 1.5.0: `conformalize` n < 25, `predict_interval` n < 50 com α_cauda = 0,02); contrato só com n ≥ 50 | 06, 07 | `test_mapie_refuses_small_n` (n ∈ {24, 30, 49}); `_coincidence_sizes.py` (≥ 50); errata do ADR 7.2.0002 (Task 07) |
| C6 | Série nativa 100 % degenerada → não aplicável | 09, 18 | `test_fully_degenerate_native_is_not_applicable`; `test_not_applicable_coverage_rows_carry_status_and_null_measures` |
| C7 | Etapa G falha → HALT, critério nunca relaxado | 21, Etapa G | `test_checks_fail_on_a_planted_violation`; tabela "Se falhar" |
| C8 | Âncora falha → não gravar, repetir | 23 | procedimento da Task 23; `test_r2_anchor_after_r1` |
| C9 | Montagem `undefined` sem ir ao port (inclui fold não inteiro e seed `None`); status do port; `error` soma; exceção do port propaga | 14, 18, 19 | `test_conformal_assembly.py::*` (inclusive `test_seed_none_is_undefined_with_reason`, `test_two_non_integer_folds_stay_distinct`); `test_non_integer_folds_do_not_collide`; `test_assembly_undefined_units_become_rows_without_reaching_the_port`; `test_port_exception_propagates_and_nothing_is_published` |
| C10 | Manifesto anterior (sem `conformal_parameters`) não lê | 16 | `test_manifest_without_conformal_parameters_is_corrupt` |

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-10-17 — [finding] ambiente — versão do uv da imagem × CI — Claude (Opus 5.5)
**Contexto:** no Checkpoint B a imagem `financial_forecasting-app:dev` tinha uv
0.12.3, e o CI pina 0.11.28. O `uv.lock` medido saiu limpo nas duas versões
(`uv lock --check`), e por isso a Task 05 roda `uv lock --check` antes do sync.
**Direção sugerida:** alinhar a versão do uv da imagem de dev ao pin do CI (ou o
contrário) numa issue de tooling, fora desta Stage; até lá, todo `uv lock` da
branch é seguido de `uv lock --check`.

### 2026-10-17 — [deviation] C5 — mecanismo de recusa do MAPIE para n pequeno (Checkpoint B, B-G13) — Claude (Opus 5.5)
**Contexto:** o concept C5 e o ADR 7.2.0002 item 4 dizem que, com α_cauda = 0,02,
o MAPIE recusa n < 25 pelo `_check_alpha_and_n_samples` e que, de 25 a 48, quem
ergue é o `np.quantile`. Medido contra o MAPIE 1.5.0, o mecanismo é outro. O
`conformalize`, com α_par = 0,04, recusa n < 25. O `predict_interval` chama o
mesmo check com α_par/2 = 0,02 e recusa **todo n ≤ 49**, com "Number of samples
of the score is too low". O ramo do `np.quantile` nunca é alcançado.
**O que mudou:**
- O piso dos tamanhos do contrato passou de ≥ 49 para ≥ 50 (Tasks 06 e 07,
  `coincidence_sizes()`/`divergent_sizes()`, matriz C5).
- O `test_mapie_refuses_small_n` confere a mensagem em n = 24, 30 e 49.
- A cadeia do posto do MAPIE segue `quantile_regression.py` l. 2313–2317, com
  `alpha = float(Decimal("1") - Decimal(str(confidence_level)))`.
- O ADR 7.2.0002 recebe errata na Task 07, com o arquivo na lista fechada.
**Razão:** é comportamento do oráculo e não muda contrato nem critério de aceite.
O domínio continua cobrindo n pequeno pelo C2 e o contrato continua só em tamanhos
que o MAPIE aceita. Por decisão do orquestrador, o concept não regride.

### 2026-10-17 — [decision] Task 04 — forma da fixture NexCP e dos testes de orientação — Claude (Opus 5.5)
**Contexto:** a Task 04 deixa abertos detalhes de forma da fixture e de dois testes.
**O que foi decidido:**
- O escore esperado de cada caso vai como `{"dec", "hex"}` (ou `"inf"`), e não como
  número simples (a regra de saída do ADR 6.2.0006), porque a Task pede leitura
  exata por `float.fromhex`. As chaves da proveniência são `source_url`,
  `zip_sha256`, `notebook`, `cell_id`, `numpy_version` (2.5.0) e `seed`, mais
  `transcribed_lines`, `margin` e `discarded_cases`.
- O descarte pela margem de 1e-9 vale no índice escolhido **e** no anterior (ou na
  massa total, no caso +∞). É mais estrito que o texto da Task e fecha o caso em
  que o float fica logo abaixo de 1 − α e o exato o alcança. Foram 3 descartes de
  48, entre eles a massa total n/(n+1) = 1 − α exata (ρ = 1, n = 49, α = 0,02).
  Ficaram 45 casos, 14 deles +∞.
- `test_most_recent_point_weighs_rho` usa ρ = 0,5 direto no
  `weighted_conformal_threshold`. Pelo `calibrate`, ρ = 0,5 dá sempre +∞ para
  α < 0,5, porque a massa total fica abaixo de 1/2. A orientação pelo `calibrate`
  é conferida com ρ = 0,9.
- `test_calibrate_passes_exact_geometric_weights` captura os pesos passados ao
  `weighted_conformal_threshold` por `monkeypatch`. Sem um caso de empate exato,
  não há como distinguir o resultado com `exact_level(ρ)` do resultado com o
  binário de ρ, e uma busca por subconjuntos com n ≤ 10 não achou nenhum.
- Mutantes equivalentes, registrados para a auditoria. O NexCP elemento a elemento,
  sem agrupar empates, dá o mesmo escore (ADR 7.2.0002 item 3). Na Task 03, o
  `float(alpha)` no posto e na Beta é equivalente **na grade** (α ∈ {1/50, 1/10,
  1/4}, medido até n = 2000) e é **morto por caso fora da grade**
  (task-03-fix, Checkpoint C C1-1): `split_conformal_rank(8, Fraction(1, 3)) == 6`
  (em float daria 7) e `beta_reference(99, Fraction(29, 100))` com b = 29 (em float
  daria 28). O mutante de 1 − τ_hi em float também morre.
**Razão:** são escolhas reversíveis e baratas que o plano não fixa.

### 2026-10-17 — [decision] ambiente — trava `ff-gate` na função `run()` — Claude (Opus 5.5)
**Contexto:** por regra do usuário, a VM do WSL/Docker passou a ter 6 CPUs e 10 GB,
então cabe um gate de 8 GB por vez. Um `make check` da Task 05 morreu no meio com
"error waiting for container: unexpected EOF" quando o engine reiniciou.
**O que foi decidido:** a função `run()` do §1 ganha `--name ff-gate` (o nome é a
trava). Antes de rodar, espera-se `docker ps --filter name=ff-gate -q` vazio, e
container alheio nunca é removido; um `ff-gate` parado (Exited) pode sair com
`docker rm`. O `make check` da Task 05 rodou de novo, inteiro, sob a trava.
**Razão:** é detalhe operacional e não muda nenhum contrato da Stage.

### 2026-10-18 — [decision] ambiente — gate desta Stage com o nome `ff-gate-158` — Claude (Opus 5.5)
**Contexto:** a fila da trava `ff-gate` ficou presa por dois containers de outras
sessões (`ff-gate` e `ff-gate-160`), travados havia ~15 h com ~0 % de CPU. Esses
containers não são removidos nem tocados.
**O que foi decidido:** por orientação do orquestrador, os gates desta Stage rodam
como `--name ff-gate-158`, com os mesmos limites (`--cpus 6 --memory 8g
--memory-swap 8g`, `PYTEST_PAR='-n 4 --dist loadgroup'`), um por vez. Antes de cada
um, confere-se que não há outro `ff-gate-158` e que nenhum gate alheio está ativo
(CPU > 50 %). O log vai para um arquivo montado, porque o CLI do Docker perdeu a
conexão com "unexpected EOF" várias vezes com o container ainda rodando.
**Razão:** é detalhe operacional e não muda nenhum contrato da Stage.

### 2026-10-18 — [finding] ambiente — 2 falhas fora do escopo no `make check` da Task 06 — Claude (Opus 5.5)
**Contexto:** o `make check` da Task 06 (rodado antes da regra do ADR 0.0.0059)
terminou com `2 failed, 6274 passed, 24 skipped`. As duas falhas foram
`tests/contract/features/modeling/test_quantile_model_trainer_determinism.py::test_two_seeds_produce_identical_grids[defaults-5.3]`
e `tests/e2e/test_cohort_cli.py::test_cohort_runner_end_to_end`. Elas ficam fora do
slice `inference`, e a Task 06 não toca nenhum arquivo que elas importam. A execução
coincidiu com o engine do Docker sob carga (vários gates de outras sessões ativos e
"unexpected EOF" no CLI), e os tracebacks se perderam.
**Direção sugerida:** tratar como provável instabilidade de ambiente e reconfirmar no
próximo gate completo planejado da Stage. Se repetirem, investigar fora desta Stage.

### 2026-10-18 — [decision] gates — plano de gates da Stage pela ADR 0.0.0059 (Tasks 07–23) — Claude (Opus 5.5)
**Contexto:** com a Stage em execução (Tasks 01–06 commitadas), o develop trocou a
regra de gates (PR #188, [ADR 0.0.0059](../../adr/0_0_0059-planned-full-gate-budget-per-stage.md);
fonte única: [RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)),
e a branch foi rebaseada sobre o `origin/develop` (HEAD `ab3b574`). O plano entra
aqui, e não no §1: o §1–§6 está congelado desde `stage 7.2: technical approved`
(`ef4ccb7`), e o `check_technical_postexec.py` reprova diff fora da §7. **Esta
entrada prevalece** sobre as linhas `make check-task …`, `make check-block …`,
`make check $PAR` e "Checkpoint C (T2 …)" das Verificações das Tasks 07–23.
**Pergunta:** onde rodam os `make check` completos dos 17 commits que faltam?
**Opções:**
- A — manter o plano aprovado (T3 nas Tasks 07, 15 e 19, T2 na 18, check-block nos
  Checkpoints C): seis ou mais gates completos, acima do orçamento.
- B — três pontos (depois da 07, depois da 19 e na saída); por Task, só os testes da
  Task e os gates específicos que ela toca ✅ recomendada.
**Decisão:** B, a regra que o usuário pediu: gate completo só onde é essencial.

**Por Task (T1 da ADR 0.0.0059).** Antes de todo commit: `run sh -c "$PRE; uv run
--no-sync pytest <arquivos de teste que a Task escreveu ou alterou> -q --no-cov"`, e os
hooks do pre-commit (ruff-format, ruff, mypy, commit-msg) no próprio commit. Extras,
só quando a Task toca o que eles guardam (todos rodam em segundos, sem `make`):

| Task toca… | Roda também | Tasks |
|---|---|---|
| `tests/architecture/`, `scripts/arch_baseline.toml` ou o port-coverage | os testes de arquitetura alterados + `python scripts/check_port_coverage.py` | 07, 15 |
| `.importlinter` | `uv run --no-sync lint-imports` + `pytest tests/architecture/test_import_contracts.py` + a contagem de arestas da Task 19 | 19 |
| VO novo em `domain/value_objects/` | `python scripts/check_vo_invariants.py` | 09, 11, task-02-fix |
| `src/` do evaluation | `pytest tests/architecture/test_evaluation_validation_single_owner.py --no-cov` | 09, 11, 12, 13, 14, 16, 17, 18, 19 |
| `tests/unit/features/evaluation/` | `pytest tests/architecture/test_unit_evaluation_purity.py --no-cov` | 09, 11, 12, 13, 14, 16, 17, 19 |
| `tests/architecture/test_stage_7_2_regression_guards.py` | esse arquivo | 15, 19 |

Esses extras não são gate completo: cobrem o ponto cego do T1 (que não roda
`tests/architecture/`) só para o gate que a Task pode quebrar. `make check-task` e
`make check-block` saem da rotina; `check-task` só com motivo concreto registrado em §7.

**Gates completos (`make check $PAR`, T3) — 3 pontos, a saída incluída:**

| # | Depois de | Por quê |
|---|---|---|
| A | Task 07 | fecha o grupo **dependências e scripts de gate**. É o primeiro gate completo depois do rebase de 136 commits, com o `uv.lock` mesclado automaticamente, o `arch_baseline.toml` do develop com seções novas e quatro gates de arquitetura novos (`check_vo_invariants`, `check_use_case_deps`, `check_domain_determinism`, `check_schema_literals`). Cobre também o `fix` da Task 02 (abaixo), o adapter `mapie` e a reversão do par do ADR 6.1.0005. Esperar a Task 19 deixaria doze Tasks construídas sobre um lock ou baseline possivelmente quebrado |
| B | Task 19 | fecha o grupo **contratos entre slices e composition root**: o port do consumidor lido pelo `refresh_gold` (15), `GOLD_SCHEMAS`/`CONFIRMATORY_TABLES` e os builders registrados no composition root (18), o construtor do `RefreshGold`, a aresta nova no `.importlinter` e o wiring do `CalibrateConformal` (19). Esperar a saída deixaria o e2e (20) e a Etapa G montados sobre um wiring não verificado |
| C | saída (Passo 10) | gate de saída, antes do `git push` que abre o PR (§3) |

Nenhuma reordenação: 15, 18 e 19, as Tasks de risco do segundo grupo, já são
contíguas e terminam no ponto B. A saída de cada ponto é colada nesta §7. Ponto
vermelho → commit `fix(<escopo>): … [7.2/task-NN-fix]` antes da próxima Task.

**Os `make check` das Tasks 05 e 06 não valem mais.** Rodaram antes do rebase,
sobre outro `develop`, e não contam no orçamento. As duas falhas da Task 06
(`[finding]` acima) são reconfirmadas no ponto A.

**Checkpoint C** continua por bloco (depois de 08, 12, 15, 19 e 22), como revisão do
diff por subagente, **sem** gate de suíte.

**Ambiente (inalterado):** gate completo como `--name ff-gate-158`, um por vez,
`--cpus 6 --memory 8g --memory-swap 8g`, `PYTEST_PAR='-n 4 --dist loadgroup'`, log em
arquivo montado; volume `financial-forecasting_ff72-venv`; só aspas simples dentro de
`sh -c "…"`.
**Razão:** ADR 0.0.0059 itens 1–6. O orçamento fica em 3, e cada ponto do meio fecha
um grupo cuja quebra invalidaria as Tasks seguintes.

### 2026-10-18 — [deviation] task-02-fix — `CalibrationPoint` sem `__post_init__` reprova o gate novo de VO — Claude (Opus 5.5)
**Contexto:** o develop trouxe o `check_vo_invariants.py` (#61/#160): todo
`@dataclass(frozen=True)` em `domain/value_objects/` precisa de `__post_init__`. Sobre
o HEAD rebaseado (`ab3b574`), o script reprova
`inference/domain/value_objects/calibration_set.py::CalibrationPoint` (L46). A Task 02
pôs as recusas por ponto (finitude, timestamps) no `CalibrationSet`.
**O que muda:** um commit `fix(inference): CalibrationPoint valida os próprios campos
[7.2/task-02-fix]` **antes da Task 07**. Arquivos:
`src/financial_forecasting/features/inference/domain/value_objects/calibration_set.py`
e `tests/unit/features/inference/test_conformal_embargo.py`. O `CalibrationPoint`
ganha `__post_init__` com as regras de um ponto: valor finito e timestamp ISO com
fuso. O `CalibrationSet` fica com as regras entre pontos e contra o teste (ordem,
repetição, embargo, par). As mensagens continuam nomeando o campo. Um teste novo
constrói o ponto inválido direto, sem passar pelo set, e as asserções existentes de
`test_conformal_embargo.py` não mudam. Não vale o marcador `# vo-invariant: none`,
porque o ponto tem invariante. Verificação: os testes da Task e
`python scripts/check_vo_invariants.py`; o ponto A cobre o resto.
**Por que ficou abaixo do limiar de pergunta:** é conformidade com um gate que entrou
no develop, sem contrato novo. A Task 02 nasceu antes da regra.
**Na execução (2026-10-18):** duas asserções de `test_conformal_embargo.py` mudaram.
Elas são `test_non_finite_value_refused` e `test_naive_or_invalid_timestamp_refused`.
Antes casavam `points[1].<campo>`, mas agora o ponto ruim é recusado ao ser construído,
antes de existir o set, e o ponto não conhece o próprio índice. As duas passaram a
construir o ponto direto e casam `<campo>: …`. O ponto também recusa valor que não é
número (`bool`, texto, `None`), com um teste novo. As recusas entre pontos seguem no set,
com o índice na mensagem.

### 2026-10-18 — [deviation] Tasks 09, 11, 12, 13, 14, 16–19 — premissas do evaluation depois do rebase — Claude (Opus 5.5)
**Contexto:** conferi cada Task restante contra os arquivos que o develop mudou
(`8a2df7c..972e571`): `preregistration.py`, `toml_preregistration_source.py`,
`preregistration_hash.py`, `series_assembly.py`, `dtos/refresh_gold.py`, os testes do
refresh, `arch_baseline*` e `pyproject.toml`.
**Seguem válidas, sem mudança:**
- os nomes que o technical cita (`CoverageSeries`, `is_at_or_below`,
  `is_inside_closed`, `pair_nominal`, `is_symmetric_pair`, `DegeneracyGate`,
  `WilsonBand`);
- as regras privadas do `SeriesAssembly` que a Task 13 extrai (o develop só trocou a
  validação de `window_deficits` no `_check_call`);
- as construções de `RefreshParameters` listadas na Task 16 (os mesmos sete
  arquivos) e as duas de `RefreshGold` em `test_refresh_gold_use_case.py`;
- `_ALL_TABLES` e `all(generation.tables[name] …)` em `test_refresh_gold.py:126/453`
  (Task 18);
- a lista `[r0, r1]` de `test_every_revision_hash_quoted` (l. 195, Task 22);
- "As 27 arestas de runtime" em LAYOUT §7 l. 311 (Task 19: 27 → 28);
- a lista literal `["ConformalBackend", "Hasher"]` e a entrada temporária no
  baseline (Task 07 reverte só a entrada `ConformalBackend`; o "sem diferença
  contra `$BASE`" vale com o `$BASE` novo).

**O que muda nas Tasks:**
- **Dono único das regras do evaluation** (`test_evaluation_validation_single_owner.py`,
  #118/#167). O código novo do evaluation (09, 11, 12, 14, 16, 17, 18, 19) valida
  inteiro por `is_int`/`validate_int_at_least` (`_integer.py`), número por
  `is_real_number`/`is_finite_number` (`_finite_number.py`) e ordem estrita de
  timestamps por `check_strictly_increasing` (`_timestamps.py`). Nunca se escreve
  `isinstance(x, bool)` ao lado de `isinstance(x, int | float)`. O `nexcp_rho` do
  `ConformalParameters` (11) passa por `is_real_number`. Os arquivos das listas
  fechadas não mudam: são imports de módulos existentes.
- **Task 12:** o `preregistration.py` não tem mais `_check_int_at_least` nem
  `_check_sha256`; o bloco `[conformal]` usa `validate_int_at_least` e
  `validate_sha256_hex`, se precisar. Os testes de hash que constroem
  `PreregistrationHash` cru usam hex válido, porque o VO agora valida no
  `__post_init__` (#160).
- **VOs novos (09, 11)** têm `__post_init__` por desenho (`ConformalPairLimits`,
  `ConformalCoverageSeries`, `ConformalParameters`). Um VO auxiliar sem invariante
  leva `# vo-invariant: none — <motivo>`.
- **`check_use_case_deps`:** o `RefreshGold.__init__` recebe o port
  `ConformalCalibration` (19), nunca o `CalibrateConformal`. O plano já previa isso;
  agora há gate.
**Por que ficou abaixo do limiar de pergunta:** nenhuma assinatura de contrato da
Stage muda. São regras de dono único e de VO que o develop passou a impor.

### 2026-10-18 — [decision] gates — saída do ponto A (depois da Task 07) — Claude (Opus 5.5)
**Contexto:** primeiro gate completo depois do rebase, sobre o HEAD `ee2a530` (Task
07), com `--name ff-gate-158`, os limites de recurso, `PYTEST_PAR='-n 4 --dist
loadgroup'` e o log em arquivo montado.
**Saída:**
- `uv lock --check` no ff72: `Resolved 182 packages`;
- ruff `All checks passed!`; mypy `Success: no issues found in 349 source files`;
  `check_layout` PASSOU; `Contracts: 17 kept, 0 broken`;
- `[fake_parity]`, `[use_case_deps]`, `[domain_determinism]` e `[vo_invariants]`
  PASSOU; `[port_coverage]` PASSOU com 1 no baseline (`Hasher`);
  `[schema_literals]` PASSOU com 17 no baseline;
- pytest: `6738 passed, 24 skipped, 577 warnings in 1145.48s (0:19:05)`, cobertura
  `99.15%` (mínimo 90%); `EXIT=0`.

O ponto A ficou verde e não pediu nenhum task-NN-fix. As duas falhas do `[finding]`
da Task 06 passaram aqui (`test_two_seeds_produce_identical_grids[defaults-5.3]` e
`test_cohort_runner_end_to_end`). Fica confirmada a instabilidade de ambiente, e o
`[finding]` fecha sem ação.

### 2026-10-18 — [finding] tooling — `index.lock` velho depois do `make check` — Claude (Opus 5.5)
Algum teste da suíte deixa `.git/worktrees/<wt>/index.lock` velho durante o `make check` (visto em três gates desta Stage, às 17:32, 10:50 e 15:18:59, e o commit seguinte falha até o arquivo ser removido); issue a abrir pelo orquestrador.

### 2026-10-18 — [decision] Task 09 — forma da média entre seeds e dos relatórios conformais — Claude (Opus 5.5)
> ⚠️ **Errata (2026-10-18, Checkpoint C das Tasks 09–15, C3-2):** a premissa abaixo
> estava errada. O concept §4 (concept.md:428) diz "PICP, MPIW, cruzamento e aninhamento
> pelas duas médias", então a média entre seeds traz, para cada uma das quatro
> quantidades, a contada (c̄/n̄; MPIW ponderado por n) e a média simples por seed com o
> dp: `mean_of_seed_mpiws`, `mean_of_seed_crossed_rates` e `mean_of_seed_nesting_rates`,
> cada uma com `sd_of_seed_*` (task-09-fix). Com MPIW infinito numa seed, a média simples
> é infinita e o dp é `None`. A Task 18 leva essas colunas para a gold. O resto da
> entrada vale.

**Contexto:** o concept §4 deixa o corpo do `ConformalSeedMeanCoverage` em "…" e não
diz como PICP, MPIW, cruzamento e aninhamento entram na média entre seeds, nem o que
fazer com uma seed completa cuja série nativa é 100 % degenerada.
**O que foi decidido:**
- `ConformalPairCoverage` ganha `covered_count` e `crossed_count`, e o
  `ConformalCoverageReport` ganha `nesting_violation_count`. São as contagens inteiras
  que a média entre seeds precisa para c̄/n̄ sem reconstruir contagens de razões em
  float.
- Na média, cada cauda tem c̄, `coverage` = c̄/n̄ (base da banda de Wilson, nominal τ),
  `mean_of_seed_coverages` e o dp amostral (`None` com uma seed). O par tem PICP pelas
  duas médias (c̄_dentro/n̄ e a média dos PICP por seed, com o dp). Cruzamento e
  aninhamento usam c̄/n̄. O MPIW é a média ponderada por n (Σ n_s·MPIW_s / Σ n_s),
  infinito se alguma seed for infinita. Cada coluna da tabela gold tem um valor só.
- Uma seed com relatório não aplicável (série nativa 100 % degenerada, C6) não entra
  nas médias e fica em `seeds_excluded`. Zero seeds aplicáveis dá `applicable = False`.
- Os relatórios de média e de seed validam o rótulo (I9) e a coerência
  `n_evaluated` × máscara na construção.
**Razão:** são escolhas reversíveis, sem formato persistido nesta Task. A Task 18
fixa as colunas e lê estes campos.

### 2026-10-18 — [deviation] task-08-fix — pontos de teste validados por unidade (Checkpoint C, C2-1, C2-2, C2-4) — Claude (Opus 5.5)
**Contexto:** o `calibration_set_for` não validava os pontos de teste. Um q̂ NaN ou
±inf virava limite `ok`, e um texto erguia `TypeError` fora do bloco capturado,
derrubando todas as unidades. O `test_start = test[0]` também dependia da ordem.
**O que mudou:**
- Os timestamps de teste precisam de fuso, e os q̂ do par no teste precisam ser
  números finitos. A violação ergue `ValueError` dentro do bloco capturado e vira
  `error` da unidade. ±inf só sai, vindo de Q = +inf.
- Decisões de teste que não são estritamente crescentes viram `undefined` com motivo.
  Com isso o `test_start` (a primeira decisão) é o mínimo de fato.
- O realizado ausente no calib é procurado no calib inteiro antes de construir
  qualquer ponto, então `undefined` prevalece sobre `error` em qualquer ordem.
**Por que ficou abaixo do limiar de pergunta:** o I7 já manda valor não finito para
`error` e entrada incompleta para `undefined`; o fix só estende isso aos pontos de
teste. Nenhum DTO muda.

### 2026-10-18 — [decision] task-08-fix — `validate_command` recusa par e variante duplicados (C2-7) — Claude (Opus 5.5)
Par ou variante repetidos no comando gerariam duas linhas com a mesma chave
(unidade, par, variante) e colidiriam na tabela gold. O `validate_command` passa a
recusar os dois com `ValueError` (`pairs:` e `variants:`), antes de qualquer unidade,
como os outros erros de comando do C3.

### 2026-10-18 — [deviation] task-07-fix — o que o MAPIE confere no estimador prefit (Checkpoint C, C2-8, C2-9) — Claude (Opus 5.5)
**Contexto:** a Task 07 diz que, sem `n_features_in_` e `__sklearn_is_fitted__`, o MAPIE
avisa que o estimador não está ajustado.
**Medido contra o MAPIE 1.5.0:** só o `n_features_in_` conta. Sem ele, o MAPIE avisa
"Estimator does not appear fitted". Sem o `__sklearn_is_fitted__`, não há aviso nem
diferença. A docstring do `_PrefitPredictions` passa a dizer isso. A perna `mapie`
ganha os dois casos separados (`test_mapie_warns_without_n_features_in` e
`test_mapie_is_silent_without_the_fitted_hook`). O hook fica pelo protocolo do
`check_is_fitted` do sklearn. A frase da Task 07 no §2 fica como está (o §2 está
congelado); esta entrada a corrige.
**Mutante equivalente (C2-9, "ad-med"):** a mediana do adapter, (q_lo + q_hi)/2, é o
terceiro estimador que o MAPIE exige, mas não entra nos escores do CQR assimétrico
(`symmetric_correction=False`). Trocar a mediana por qualquer vetor entre q_lo e q_hi
dá o mesmo Q. O mutante é equivalente, fica registrado e não tem teste.

### 2026-10-18 — [decision] Task 14 — "calib parcial" e o join teste × série nativa — Claude (Opus 5.5)
**Contexto:** o C9 lista "calib parcial" e "alvos de teste ≠ alvos da série nativa do
fold", mas não diz como se mede cada um.
**O que foi decidido:**
- **Calib parcial:** os índices de decisão do calib da unidade, em ordem de alvo,
  precisam ser consecutivos. Um salto (ex.: 14, 15, 17) vira `undefined` com o salto
  no motivo. O `RunInference` grava o calib como faixa contígua (7.1), então um salto
  é escrita parcial. O tamanho esperado do calib não chega à montagem.
- **Join por alvo:** os alvos da série nativa completa que caem entre o primeiro e o
  último alvo de teste da unidade precisam ser exatamente os alvos de teste dela. Alvo
  a mais, a menos ou trocado vira `undefined`. A comparação é sempre por
  `target_timestamp`, nunca por posição.
- **Série nativa inteira (task-14-fix, Checkpoint C C3-5, opção 1):** por (seed, h), a
  união dos alvos de teste das unidades `ok` tem de ser igual a
  `native.target_timestamps`. As sobras saem em
  `ConformalAssemblyResult.uncovered_targets[(seed, h)]`, e essa (seed, h) fica sem
  cobertura conformal (o `RefreshGold` a publica `undefined`). Isso pega o ponto
  nativo no vão entre folds, que o join por unidade não vê.
- **Ordem das verificações:** fold não inteiro, seed `None`, série nativa ausente,
  sem calib, sem teste e, então, as regras do `SeriesAssembly` (duplicata, níveis,
  índices e realizado), primeiro no calib e depois no teste. Na sequência vêm o
  calib parcial e o join. Vale o primeiro motivo encontrado.
**Razão:** são escolhas reversíveis, sem formato persistido. O motivo vai para a
coluna `reason` da tabela gold.

### 2026-10-18 — [decision] Task 19 — a etapa conformal do `RefreshGold` e a aresta única para a `inference` — Claude (Opus 5.5)
**Contexto:** o plano da Task 19 liga o port `ConformalCalibration` ao `RefreshGold`.
Faltava dizer o que o use case importa da `inference`, como a ordem das unidades é
fixada (Checkpoint C, C3-8 a/b) e o que fazer com uma linha `ok` do port sem cauda.
**O que foi decidido:**
- **Uma aresta de runtime:** o `refresh_gold` importa do `calibrate_conformal` só os
  DTOs de comando (`CalibrateConformalCommand`, `ConformalUnitInput`,
  `ConformalPointInput`). O `ConformalUnitResult` fica sob `TYPE_CHECKING`, e o
  `_tail_record` lê a cauda da própria linha. Assim nenhum serviço do calibrador cruza.
  A aresta entra no `.importlinter` como exceção do módulo (27 → 28). O caso
  `other-evaluation-module-imports-calibrate-conformal` prova que outro módulo reprova.
  Três guardas AST na `test_stage_7_2_regression_guards.py` veem o que o import-linter
  não vê: DTOs, adapters e domínio do `evaluation` nunca importam a `inference`; o
  port só a importa sob `TYPE_CHECKING`; o `refresh_gold` importa só o
  `calibrate_conformal`.
- **C3-8 a:** a aresta type-only do port entra nas listas de perímetro do
  `.importlinter` e do LAYOUT §7.
- **C3-8 b:** a montagem ordena as unidades por `(fold_index is None, fold_index,
  fold_raw, seed, h)`. O fold `"10"` vem depois do `"2"`, e os não inteiros ficam no
  fim. As linhas do port são unidas por chave `(fold, seed, h, par, variante)` e os
  limites por `target_timestamp`. Dentro de uma unidade, `test_lower`/`test_upper`
  seguem a ordem dos pontos de teste do comando (contrato do port), com
  `zip(strict=True)`.
- **Linha `ok` sem cauda ou sem limites:** é `ValueError`, e não vira linha nula. O
  contrato do port garante as duas, e o erro propaga como erro de programação.
- **Fixture:** no `make_cohort`, o calib do fold 0 para na decisão 2. Com a decisão
  3, o alvo em h=2 cai no `test_start` e o `CalibrationSet` (corretamente) recusa.
**Razão:** é a regra da ADR 7.2.0003 item 3 (o port no consumidor, dados cruzando) e
da ADR 0.0.0053 item 3. A ordem numérica e o join por chave tiram da ordem de
iteração qualquer efeito sobre o resultado.

### 2026-10-18 — [finding] ponto B — `test_arch_check_changed` corre contra a injeção de violação — Claude (Opus 5.5)
**Contexto:** a primeira rodada do ponto B (`make check` completo, depois da Task 19)
falhou num teste só, `tests/unit/tooling/test_arch_check_changed.py::test_main_exit_codes`
(7013 passed, 1 failed). O erro foi `FileNotFoundError` em
`src/.../inference/domain/_arch_audit_taint.py`.
**O que foi achado:** o `main()` do `check_changed.py` (#161) varre a árvore real de
`src/`. O probe de violação do `test_import_contracts.py`, gravado e apagado em outro
worker, sumiu entre o `rglob` e o `read_text`. O `tests/conftest.py` só põe no grupo
`real-src-tree` os testes de `tests/architecture/**`, e esse arquivo fica em
`tests/unit/tooling/`. O flake não vem da 7.2: já existe em `develop` e depende de
como o xdist distribui os testes.
**O que foi feito:** o arquivo declara `xdist_group(name="real-src-tree")`, que o
`conftest` respeita. Os testes dele passam a rodar no mesmo worker que os de
`tests/architecture/**`. O fix está no commit `fix(tooling)` `[7.2/--]`; o ponto B
foi rodado de novo depois dele.

### 2026-10-18 — [decision] saída do ponto B (plano de gates da ADR 0.0.0059) — Claude (Opus 5.5)
**Contexto:** o ponto B do plano é o `make check` completo depois da Task 19, com
`uv lock --check` no venv ff72, `--cpus 6 --memory 8g` e `-n 4 --dist loadgroup`.
**O que foi registrado:** na primeira rodada, `7013 passed, 1 failed` (o flake do
`[finding]` acima). Depois do fix, a segunda rodada (HEAD `2d79bba`) terminou com
`7014 passed, 24 skipped`, cobertura 99,10 % (mínimo 90 %) e `EXIT=0`. Os gates de
lint, mypy, layout, import-linter (com a aresta 28), fake-parity, port-coverage e
docs passaram nas duas rodadas.
**Razão:** o plano pede o resultado de cada ponto no §7. O ponto C é o `make check`
de saída da Stage.

<!-- END: post-execution -->
