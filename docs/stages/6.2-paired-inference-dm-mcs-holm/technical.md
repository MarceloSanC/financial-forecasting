---
title: Technical — Stage 6.2 — Inferência pareada (Diebold–Mariano/HLN, Holm, Model Confidence Set)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), TDD inside-out no BC evaluation (2ª fatia — domain stdlib + dois ports-out de oráculo + adapters statsmodels/arch + fixtures do oráculo R)
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, paired-inference-dm-mcs-holm, evaluation, paired-loss-series, student-t, diebold-mariano, hln, holm, mcs, bootstrap-indices, inference-backend, mcs-backend, statsmodels, arch, r-oracle, dm-test, importlinter, port-coverage]
status: done
created_at: 2026-09-28
updated_at: 2026-09-28
stage_id: 6.2-paired-inference-dm-mcs-holm
stage_title: Inferência pareada (DM/HLN, Holm, MCS)
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [6.1-scoring-and-calibration-metrics]
concept_ref: ./concept.md
issue_id: 114
branch: feat/114-6-2-paired-inference-dm-mcs-holm
tasks_count: 13
---

# Technical — Stage 6.2 — Inferência pareada (DM/HLN, Holm, MCS)

> **Como usar (para code assistant):** ler §1, executar Tasks em ordem (§2),
> 1 Task = 1 commit, não avançar sem verificação verde; ao fim validar §3 e
> registrar §7. Commits seguem [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(evaluation): <descrição> [6.2/task-NN]`, `Refs #114`.
>
> Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
> resolver pelo §2 de [`PROMPT-step-single-session.md`](../../PROMPT-step-single-session.md)
> (docs → ADR; E/C → `evidence-resolution` + ADR 6.2.0007+; P → sobe à sessão
> mestra) e registrar em §7. Nunca propagar silenciosamente.

## 1. Contexto e estratégia de execução

### Resumo

Segunda fatia do BC `evaluation`: o VO `PairedLossSeries` (T × k perdas L_t de um
horizonte) e a fábrica `paired_pinball_losses` (média ponto a ponto entre seeds);
a CDF da t de Student em stdlib (`student_t.py`); os serviços de domínio
`DieboldMariano` (DM/HLN unilateral com fallback do oráculo), `HolmCorrection`
(família por horizonte) e `ModelConfidenceSet` (procedimento 'R' de HLN 2011 sobre
o VO `BootstrapIndices`, mais a regra de bloco); dois ports-out de oráculo
(`InferenceBackend`, `McsBackend`) com fakes, suítes de contrato
`[fake, statsmodels]` e `[fake, arch]` e adapters `StatsmodelsHac`/`ArchMcs`; o
oráculo R `dm.test` como fixture versionada com teste genérico de proveniência; as
dependências `arch`/`statsmodels`; o contrato import-linter
`evaluation-no-inference-lib-leak`; e as edições de documentação do concept D9.

Todas as decisões vêm do concept **por referência** — nenhuma é re-derivada: D1
([ADR 6.2.0001](../../adr/6_2_0001-paired-loss-series-single-aligned-matrix-vo.md)),
D2 ([ADR 6.2.0002](../../adr/6_2_0002-student-t-p-value-stdlib-in-domain.md)), D3
([ADR 6.2.0003](../../adr/6_2_0003-dm-holm-of-record-statsmodels-oracle-no-dm-wrapper.md)
e [ADR 0.0.0056](../../adr/0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md)),
D4 ([ADR 6.2.0004](../../adr/6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md)),
D5 ([ADR 6.2.0005](../../adr/6_2_0005-mcs-block-length-ceiling-integer.md)), D6
([ADR 6.2.0006](../../adr/6_2_0006-r-oracle-fixtures-provenance-and-scope.md)), D7
(testes por camada, nomes do roadmap), D8 (sem persistência/e2e), D9 (docs). Fórmulas:
doc de domínio [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md)
§2.4, §6.1–§6.5, §6.7, §6.9, §10.1, §11.3.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`): dependências + cerca import-linter
primeiro (a biblioteca só entra já cercada) → funções e VOs puros de baixo para
cima (t de Student → `PairedLossSeries` → DM → Holm → `BootstrapIndices` → MCS),
cada um com fixture analítica no mesmo commit → fixtures do oráculo R + testes de
integração (consomem o DM já pronto) → port `InferenceBackend` + fake + suíte →
adapter statsmodels → port `McsBackend` + fake + suíte → adapter arch + integração
com `arch.MCS` → documentação.

**Exceções de ordem/contagem declaradas (PIPELINE §4.3; skill `task-ordering-hex`):**

- **13 Tasks** — acima da faixa 3–12 e abaixo do alarme ≥ 14 (CONVENTIONS §6).
  `ROADMAP-1` (roadmap §Convenções) nomeia a 6.2 entre as Stages densas (até ~15).
  A estimativa do concept §12 era ~12; +1 porque `BootstrapIndices` (dois
  validadores de port + VO) fica numa Task própria antes do MCS, para que o
  procedimento 'R' — o serviço mais longo — tenha um commit só dele.
- **Baseline transitório do `port-coverage`, duas janelas** —
  [ADR 6.1.0005](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md).
  Tasks 09 → 10 (`InferenceBackend`) e 11 → 12 (`McsBackend`): o port nasce sem
  adapter real (regra dura port ≠ adapter) e o `check_port_coverage.py` fica
  vermelho; a Task do port acrescenta a entrada em `scripts/arch_baseline.toml`
  **e** ajusta `test_real_repo_violations_are_exactly_the_declared_baseline`
  (`tests/architecture/test_port_coverage_gate.py`, hoje `== ["Hasher"]`) para
  `["Hasher", "InferenceBackend"]` (09) / `["Hasher", "McsBackend"]` (11); a Task do
  adapter reverte **as duas pontas** para `["Hasher"]` (10 / 12) — o gate reprova
  entrada morta e o teste de arquitetura reprova a lista desatualizada, então a
  reversão é forçada. As janelas não se sobrepõem.
- **Dependências antes dos ports** (lição da 6.1): a Task 01 instala `arch` e
  `statsmodels`, então as Tasks 10 e 12 vêm imediatamente depois das 09 e 11 — cada
  janela vive um commit.
- **Task 08 com 7 arquivos** — 4 deles são **uma** unidade de oráculo R indivisível
  pelo ADR 6.2.0006 (`Dockerfile`, `dm_test_cases.R`, `.json`, `.sessionInfo.txt`,
  gerados juntos por um único `docker run`); 2 são os testes de integração que os
  leem; o 7º é a linha `tests/fixtures/` do `LAYOUT.md` §2 (a árvore do LAYOUT passa
  a descrever o diretório no mesmo commit que o cria). Precedente de excesso
  declarado: 6.1 Tasks 01/09/10.
- **Nenhum use case nesta Stage** (concept D8; ADR 6.2.0003 item 6; ADR 6.2.0004
  item 7): a `application` tem só os dois ports; não há wiring no composition root.
  A verificação executável dos ports são as suítes de contrato e as integrações.

**Decisões de detalhe planejadas (abaixo do limiar de concept — não mudam
contrato, fronteira nem critério; viram entrada `[decision]` em §7 ao executar):**

- **Onde moram os validadores de DM/Holm** (Tasks 04/05). O concept §4 (linhas
  379–385) lista a validação única por port e diz "no módulo
  `domain/value_objects/bootstrap_indices.py`" — leitura adotada: essa localização
  vale para os **dois validadores de bootstrap** nomeados no contrato do
  `BootstrapIndices` (`validate_bootstrap_request`, `validate_block_length_request`);
  a do DM/Holm só é fixada como "um validador de domínio chamado pelos primitivos,
  pelo fake e pelo adapter" (ADR 6.2.0003 item 3), sem módulo. Para evitar o ciclo
  de import (o validador do DM confere `DmVarianceEstimator`, que mora em
  `diebold_mariano.py`, e o DM chama o validador), **`validate_dm_request` mora em
  `diebold_mariano.py`** ao lado do enum; `inference_input_validation.py` nasce na
  Task 05 só com `validate_p_values` e `validate_alpha` (Holm e MCS). Nomes do
  concept §4 intactos.
- **`McsReport.__post_init__` confere a parte interna do I9** (Task 07): o relatório
  não carrega `series.models` nem o `BootstrapIndices`, então "nomes =
  `series.models`" e "scheme/block/reps/seed/generator iguais aos dos índices" são
  garantias de **construção** (`ModelConfidenceSet.evaluate`, com testes próprios —
  tokens `copies_bootstrap`, `elimination_names`, `included_order`); o
  `__post_init__` confere o resto do I9 (máximo acumulado, último = 1,0, `included`
  = {m : p̂ ≥ α}, `statistic == "R"`, nomes únicos, faixas).
- **Chaves de `block_estimates` exatamente as tuplas de `series.model_pairs()`**
  (Task 07): par invertido `(b, a)` conta como **par desconhecido** (C7) — uma só
  grafia por par, sem normalização silenciosa.
- **`ArchMcs.optimal_block_length` nunca devolve número calculado por divisão por
  zero** (Task 12): a chamada roda sob `np.errstate(divide="raise",
  invalid="raise")`; `FloatingPointError` ou resultado não-finito/negativo →
  `ArithmeticError`, declarado no docstring do port `McsBackend` (Task 11) como a
  falha numérica do backend real — mesma postura do teto do Lentz da t e do ADR
  6.2.0004 itens 3/5 (o validador é a paridade; o adapter só se recusa a mentir).
  Motivo medido: a série de 22 pontos `[1, −1, 0, …, 0]` passa pelo validador (não
  constante, finita, ≥ 11) e o `arch` devolve 8,0 com 12 avisos de divisão por
  zero. Com L_t contínuas não ocorre; não é caso de paridade (o fake não a
  reproduz) — fica num teste de integração do adapter.
- **`PairedLossSeries.differential`/`losses_of` com nome desconhecido ou
  `first == second` → `ValueError`** (Task 03), mesma postura de C2.
- **Teto de iterações do Lentz `_MAX_ITERATIONS = 1000`** (Task 02): ~18× o máximo
  medido (56 iterações em df 1–2500 × |x| até 10³); constante de módulo para que o
  teste de C5 force a não-convergência via `monkeypatch`.

**Coordenação com a 6.3 (em paralelo, `feat/113-6-3-calibration-risk-backtests`):**
a 6.3 não toca `pyproject.toml`/`uv.lock`/`.importlinter`/`LAYOUT.md` (todos só
aqui); ela cria `chi_square.py`, altera `coverage_series.py`/`coverage_metrics.py`
(predicados FA7) e cria o mesmo `tests/fixtures/r_oracle/Dockerfile`. **Esta Stage
não edita `coverage_series.py` nem `coverage_metrics.py`** — `paired_pinball_losses`
só importa `CoverageSeries`/`PinballScore`; se alguma Task precisar alterá-los,
registra `[finding]` de coordenação em §7 e para. O `Dockerfile` é byte-idêntico
nas duas branches (add/add idêntico não conflita). O teste genérico de
proveniência (Task 08) varre **todo** `r_oracle/*.json`, inclusive o
`var_test_cases.json` da 6.3 quando as duas estiverem em `develop`; ele depende só
do bloco `provenance` (regras do Step abaixo) e dos objetos `{"dec", "hex"}` do
ADR 6.2.0006, **não** dos nomes de campo dos casos, e aceita chaves extras em
`provenance` (ex.: `t_max` da 6.3). Mapa de conflitos e rebase: §5.

**Gate por Task (RUNBOOK §Gates em camadas, ADR 0.0.0055):** T1 =
`make check-task SLICE=evaluation`. As Tasks que tocam `pyproject.toml`/`uv.lock`,
`.importlinter`, `scripts/arch_baseline.toml` ou `tests/architecture/` (01, 09, 10,
11, 12) rodam **T3** (`make check`) no lugar do T1; as que tocam docs de
`docs/` (08, 13) somam `make docs-check`. Checkpoint C (T2, `make check-block`)
após as Tasks 03, 05, 08, 10 e 13.

**Onde rodar — convenção dos blocos de verificação (vale para §2 e §3; regra do
Step):**

- Cada verificação vem rotulada **Container** ou **Host**. O host não tem o
  toolchain (`uv`/`make` só no container).
- **Container:** o bloco inteiro roda num **único** `bash -euo pipefail -c`, dentro
  de **um** `docker run`, com o venv **da 6.2** (volume `ff-step62-venv`; a 6.3 usa
  outro volume, sem disputa de lock `statsmodels` 0.15 × 0.14.6):
  ```bash
  WT=feat-114-6-2-paired-inference-dm-mcs-holm
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT:/app" \
    -v "C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git" \
    -v ff-step62-venv:/app/.venv \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app \
    -w /app financial_forecasting-app:dev bash -euo pipefail -c "$(cat <<'EOF'
  git config --global --add safe.directory '*'
  # <linhas do bloco Container da Task>
  EOF
  )"
  ```
  (script por `-c`, não por stdin: um comando que lesse stdin consumiria o resto.)
- **Host:** Git Bash na raiz da worktree, o bloco como um só script
  `bash -euo pipefail` (scripts stdlib `python scripts/check_*.py`, `cmp`, greps de
  docs, `git`).
- **Negação:** `set -e` ignora o status de `! cmd`; toda asserção negativa é
  `if <cmd>; then echo "FAIL: <motivo>"; exit 1; fi`. Arquivo produzido e lido no
  mesmo bloco, e toda leitura começa por `test -s "$f"` (o `/tmp` não sobrevive entre
  `docker run --rm`; `grep` sobre arquivo ausente devolve 2 — falso verde medido na
  6.3).
- O oráculo R roda **só** na Task 08, na imagem `ff-r-oracle:4.4.1` (construída do
  `Dockerfile` versionado).

### Pré-condições

- Stage `6.1-scoring-and-calibration-metrics` em `done` e mergeada em `develop`
  (`CoverageSeries`, `PinballScore.per_point_losses`, `is_finite_number`,
  `tests/unit/features/evaluation/conftest.py::make_series`).
- Concept desta Stage em `done`; ADRs 6.2.0001–0006 e 0.0.0056 em `accepted`.
- Working tree na branch `feat/114-6-2-paired-inference-dm-mcs-holm`; volume
  `ff-step62-venv` criado (cópia do venv do Step).
- Imagem `ff-r-oracle:4.4.1` disponível localmente (Task 08); se não estiver,
  `docker build -t ff-r-oracle:4.4.1 tests/fixtures/r_oracle`.

### Premissas técnicas

- Python 3.12; `uv`; `make check` = ruff + mypy strict + check_layout +
  lint-imports + fake-parity + port-coverage + docs-check + pytest com cobertura
  ≥ 90 %.
- `mypy` global com `ignore_missing_imports = true` (statsmodels sem stubs); o
  `arch` traz anotações — onde o tipo do pandas vazar no adapter, converter para
  `float`/`int` nativos na fronteira (a assinatura do port é a do concept §4).
  Reexport explícito (`no_implicit_reexport`) não é necessário: nenhum módulo
  reexporta nomes de outro.
- `statsmodels` 0.14.6 já está no `uv.lock` (transitiva via `statsforecast`, que
  exige `>=0.14.5`); a 0.15.0 exige `formulaic>=1.1.0` além de `patsy`. `arch` 8.0.0
  exige `numpy<3` (lock: 2.5.0), `scipy>=1.8`, `pandas>=1.4`, `statsmodels>=0.13`.
- O grimp resolve módulos externos pelo AST (precedente `numba`/`scoringrules`);
  aqui o contrato novo nasce **na mesma Task** que instala as libs.
- Testes unit e de contrato **não** importam `arch`/`statsmodels`/`scipy`/`numpy`
  diretamente (contrato só via adapter); unit também não importa adapter nem lê
  arquivo (marcador "unit = sem I/O" do `pyproject.toml`; concept I13). Geradores de
  dado de teste usam `random.Random(<seed declarada>)` (stdlib) e referências
  analíticas usam `math`.
- **Nomes de teste com tokens obrigatórios:** cada Task lista os tokens que os nomes
  das funções de teste (**sem** o id `[...]` de parametrização) **devem** conter; a
  matriz aponta para eles e o §3 prova, por coleta, que cada token de cada arquivo
  casa ≥ 1 teste. Os tokens de um arquivo são **únicos, nenhum contido em outro** do
  mesmo arquivo (o laço do §3 recusa a lista se estiver) e **específicos do
  comportamento** (prefixo por arquivo, ex.: `pls_invalid`, `prov_r_version_mismatch`)
  — genéricos como `horizon` ou `c4` casariam testes de erro e tornariam a prova
  vácua. Única exceção: na integração `test_mcs_vs_arch.py` os esquemas
  `stationary`/`moving_block` vivem só nos ids — provados pela contagem de exatamente
  8 ids `PASSED` (Task 12 e §3), não pelo laço.
- Tolerâncias sempre declaradas no módulo de teste, absoluta + relativa (ADR
  0.0.0021; concept I12), a partir das medições abaixo.

### Medições da Fase 3B (base das tolerâncias e do C9)

Rodadas no container de dev (scipy 1.18.0; `arch` 8.0.0 e `statsmodels` 0.15.0 de
um diretório de sondagem fora do repo), sobre **protótipos** stdlib dos algoritmos
fixados nos ADRs. As Tasks 02, 06 e 07 **re-medem com a implementação final** e
registram em §7 (concept A14) com o cabeçalho exato
`### <data> — [decision] Task NN — medição A14 (<assunto>) — <autor>`; se o
re-medido passar de 1/10 da tolerância declarada, `[decision]` em §7 antes de
seguir.

1. **t de Student (A14.1)** — protótipo nos ramos do `pt.c` com a cauda pequena
   calculada **direto** pela fração contínua (nunca `1 − I`), contra
   `scipy.stats.t.cdf`, df ∈ {1, 2, 3, 4, 5, 7, 10, 20, 30, 59, 100, 249, 500, 999,
   1500, 2000, 2499, 2500} × 1601 valores de x (0 e ±10⁻¹²…±10³, log):
   - df ≥ 2: erro absoluto máx. **3,6e−13**; erro relativo máx. na cauda inferior
     (x < 0, F > 10⁻²⁹⁰) **7,6e−12** (df = 2000); caudas extremas conferem (df = 999,
     x = −10: 8,354109e−23, rel 2,2e−13; df = 2499, x = −40: 3,748606e−271, rel
     3,2e−14); máx. 56 iterações do Lentz.
   - df = 1 em |x| ≲ 10⁻⁸: diferença absoluta 2,3e−9 — o **scipy** devolve 0,5
     exato onde a forma fechada ½ + arctan(x)/π dá 0,5 − 2,35e−9 (o protótipo
     concorda com a forma fechada). Por isso df = 1, 2 e 3 são checados contra as
     formas fechadas (unit), e o cruzamento com scipy (contrato) usa T ≥ 12.
   - Armadilha medida: a versão que calcula `lower = ½·(1 − I_z(½, n/2))` para
     n > x² perde **toda** a precisão na cauda com df grande (df = 999, x = −10 → 0
     em vez de 8,35e−23). A implementação calcula `1 − I` pela simetria 8.17.4
     (ramo que devolve a cauda direto), como o `pbeta(..., lower_tail = FALSE)` do
     `pt.c`.
2. **DM domínio × `statsmodels` + `scipy`** — 960 pares aleatórios (T ∈ {12, 30,
   250, 1000}, h ∈ {1, 2, 7}, retangular e Bartlett; 22 caíram no fallback, todos
   com o mesmo `horizon_used` nas duas pernas): estatística rel. máx. **5,0e−14**;
   variância rel. máx. **1,0e−13**; p-valor abs. máx. **9,9e−14**, rel. máx. na
   cauda (p < 0,5) **1,2e−12**.
3. **Holm domínio × `multipletests(method='holm')`** — 500 listas aleatórias (m
   1–8): **zero** divergências, p-valores ajustados **idênticos** (mesma operação:
   um produto e um máximo acumulado) e `reject` idêntico em α ∈ {0,05; 0,10}.
4. **Tamanho mínimo de `optimal_block_length` (A14.3)** — `arch` 8.0.0
   `_single_optimal_block` calcula autocorrelações até o lag m_max = ⌈√n⌉ +
   max(5, ⌊log₁₀ n⌋) e divide por `√(v1·v2)` com `v1 = eps[i+1:] @ eps[i+1:]`: para
   n ≤ 10 o lag chega a n − 1 e `v1 = 0` → divisão por zero em **200/200** séries
   normais de cada n ∈ 1..10 (e um número espúrio, ex. 1,4168 em n = 10); n = 11 →
   0/200. Robustez n = 11..60 × 5 famílias (normal, AR(0,9), t₂, binária, inteiros
   −2..2) × 50 séries: 2 avisos, ambos em séries inteiras com cauda demeaned nula
   (a guarda de detalhe do adapter acima). **Mínimo: 11 pontos**
   (`MIN_BLOCK_LENGTH_OBS = 11`).
5. **Custo do MCS stdlib (A14.2)** — protótipo do procedimento 'R' a T = 1000, k = 7,
   reps = 1000, bloco 10: **0,45 s** (estacionário) e **0,53 s** (moving-block) no
   domínio; índices do `arch` 0,2–0,3 s; `arch.MCS` inteiro 0,09 s; mesma ordem de
   eliminação nas duas rotas. Cabe com folga (mesmo × as sensibilidades da 6.5).

**Tolerâncias declaradas (constantes nos módulos de teste):**

| Grandeza | Onde | Tolerância |
|---|---|---|
| estatística S1*, d̄, var̂(d̄) | contrato (statsmodels) e integração (R) | `math.isclose(rel_tol=1e-11, abs_tol=1e-14)` (≥ 100× o medido) |
| p-valor do DM e `student_t_cdf` × scipy/R | contrato e integração | `abs ≤ 1e-12` sempre **e** `abs ≤ 1e-10·ref` quando `ref < 0,5` (cauda) — helper `_assert_p_close` |
| `student_t_cdf` × formas fechadas df = 1, 2, 3 | unit | `abs ≤ 1e-14` e, na cauda (x < 0), `rel ≤ 1e-12` com as formas sem cancelamento (Task 02) |
| Holm ajustado × statsmodels | contrato | igualdade exata (`==`); se divergir, `[deviation]` com `rel ≤ 1e-15` |
| p-valores MCS × `arch.MCS` | integração | igualdade exata (múltiplos de 1/reps) |
| DM à mão, MCS diádico/inteiro | unit | igualdade exata onde a aritmética é exata; senão `abs ≤ 1e-15` |

### Estrutura de pastas afetada

```
src/financial_forecasting/features/evaluation/
├── domain/
│   ├── value_objects/{paired_loss_series.py, bootstrap_indices.py}          # NOVOS
│   └── services/{student_t.py, paired_pinball_losses.py,                    # NOVOS
│                 diebold_mariano.py, inference_input_validation.py,
│                 holm_correction.py, model_confidence_set.py}
├── application/ports/out/{inference_backend.py, mcs_backend.py}             # NOVOS
└── adapters/out/inference/{__init__.py, statsmodels_hac.py, arch_mcs.py}    # NOVOS
tests/
├── unit/features/evaluation/{test_student_t.py, test_paired_loss_series.py,
│     test_paired_pinball_losses.py, test_dm_vs_r_oracle.py,
│     test_inference_input_validation.py, test_holm_vs_statsmodels.py,
│     test_bootstrap_indices.py, test_mcs_vs_arch.py}                        # NOVOS (analíticos)
├── fakes/features/evaluation/{fake_inference_backend.py, fake_mcs_backend.py}   # NOVOS
├── contract/features/evaluation/{test_inference_backend_contract.py,
│     test_mcs_backend_contract.py}                                          # NOVOS
├── integration/features/evaluation/{test_r_oracle_provenance.py,
│     test_dm_r_oracle_fixtures.py, test_mcs_vs_arch.py}                     # NOVOS
├── fixtures/r_oracle/{Dockerfile, dm_test_cases.R, dm_test_cases.json,
│     dm_test_cases.sessionInfo.txt}                                         # NOVOS
└── architecture/{test_import_contracts.py, test_port_coverage_gate.py}      # MODIFICADOS
.importlinter                                          # MODIFICADO (01)
scripts/arch_baseline.toml                             # +09 −10 +11 −12
pyproject.toml / uv.lock                               # MODIFICADOS (01)
docs/LAYOUT.md                                         # MODIFICADO (08)
docs/{roadmap.md, overview.md}                         # MODIFICADOS (13)
docs/domain/evaluation/probabilistic-forecast-evaluation.md   # MODIFICADO (13)
```

Os testes unit ficam **planos** em `tests/unit/features/evaluation/` (padrão da
6.1); os três nomes do roadmap (`test_dm_vs_r_oracle.py`, `test_mcs_vs_arch.py`,
`test_holm_vs_statsmodels.py`) ficam, com **só fixtures analíticas** — desvio de
caminho declarado no concept D7. Os dois `test_mcs_vs_arch.py` (unit e integration)
convivem porque os diretórios são pacotes (`__init__.py`).

### Rastreabilidade — concept §11 → Tasks

"Tokens" = substrings obrigatórias nos nomes das funções de teste do arquivo (sem o
id `[...]`), provadas pelo laço de coleta do §3.

| # | Critério de aceitação (concept §11) | Tasks | Check objetivo |
|---|---|---|---|
| A1 | `PairedLossSeries` ergue em cada caso de C1 (um teste por caso, inclusive T = h, T < h, perda negativa, nome repetido); aceita par de comparadores com diferencial constante e o DM do candidato contra os demais roda; `losses_of`/`differential`/`model_pairs` corretos em k = 3 | 03 (VO), 04 (DM sobre a série com par degenerado) | pytest de `test_paired_loss_series.py` + tokens `pls_invalid`, `pls_degenerate_pair_accepted`, `pls_model_pairs_order`, `pls_differential_sign`, `pls_losses_of_column`, `pls_frozen`; token `dm_degenerate_comparator_pair` em `test_dm_vs_r_oracle.py` |
| A2 | Fábrica: S = 1 → colunas = `per_point_losses`; S = 3 → média ponto a ponto; ergue com horizonte/timestamps/grade divergentes entre seeds e entre modelos, modelo sem séries, < 2 modelos | 03 | pytest de `test_paired_pinball_losses.py` + tokens `factory_single_seed_identity`, `factory_seed_mean`, `factory_mismatch`, `factory_no_series`, `factory_single_model` |
| A3 | `student_t_cdf`: x = 0 → ½; df = 1 e df = 2 nas formas fechadas; simetria; argumento complementar sem cancelamento; C5 ergue; p-valor do domínio ≡ `StatsmodelsHac` (scipy) em todos os casos de contrato sob tolerância declarada | 02 (unit), 10 (contrato) | pytest de `test_student_t.py` + tokens `t_zero_half`, `t_df1_closed`, `t_df2_closed`, `t_df3_closed`, `t_symmetry`, `t_complement_no_cancel`, `t_monotone`; `_assert_p_close` em todo caso de `dm_random_matches_domain[statsmodels…]` |
| A4 | DM à mão (h = 1; h = 2 retangular e Bartlett; HLN; fallback; C3 com T = h, perda negativa, h > T); integração reproduz **todas** as fixtures de `dm_test_cases.json` cobrindo h ∈ {1, 7}, os dois estimadores, candidato melhor/pior, T pequeno, fallback, diferencial constante h = 2, h > T, variância nula h = 1; nenhum caso h = T | 04 (unit), 08 (integração) | tokens `dm_hand_h1`, `dm_h2_rectangular`, `dm_h2_bartlett`, `dm_hln_factor`, `dm_fallback_alternating`, `dm_constant_differential`, `dm_c3_invalid`; integração da Task 08 com zero `SKIPPED` e tokens `r_fixture_case_matches`, `r_fixture_covers_required_scenarios` |
| A5 | `r_oracle/` com `dm_test_cases.{json,R,sessionInfo.txt}` + `Dockerfile` de duas linhas; teste de proveniência sobre **todo** `*.json` reprova chave ausente, versão ≠ `sessionInfo`, gerador/`sessionInfo` inexistente, `{"dec","hex"}` com formas diferentes ou que não dão o mesmo double | 08 | pytest de `test_r_oracle_provenance.py`: `prov_real_fixture_clean`, `prov_dockerfile_two_lines` + um token **por regra** (Task 08): `prov_missing_key`, `prov_generator_missing`, `prov_session_info_missing`, `prov_r_version_mismatch`, `prov_package_version_mismatch`, `prov_hex_mismatch`, `prov_dec_length_mismatch`, `prov_scalar_list_shape_mismatch`, `prov_image_from_mismatch`, `prov_generated_at_not_iso`, `prov_generated_at_invalid_date`, `prov_extra_key_allowed` + `cmp` do `Dockerfile` (Host) |
| A6 | `holm_adjust`/`holm_reject` analíticos (m = 1; máximo acumulado; teto 1; ordem de entrada; empates; fronteira p̃ = α rejeita); contrato: `multipletests(method='holm')` em listas aleatórias com paridade de `reject` para α ∈ {0,01; 0,025; 0,05; 0,10; 0,20} e m ≤ 7; C4 nas duas pernas | 05 (unit), 09 (fake), 10 (statsmodels) | tokens `holm_dyadic`, `holm_single_p`, `holm_cap_one`, `holm_tie_order_free`, `holm_input_order`, `holm_boundary_rejects`; no contrato `holm_adjusted_equal`, `holm_rejected_equal`, `holm_c4_parity` |
| A7 | `HolmCorrection.family` k = 7 → 6 comparações na ordem do VO, cada `dm` = `DieboldMariano.compare`; C2; `DmHolmFamilyReport` à mão ergue (comparador repetido, candidato entre comparadores, `n_points` misturados, estimador misturado, ajustado ≠ `holm_adjust`, `rejected` incoerente); API sem parâmetro de mais de um candidato | 05 | tokens `family_k7_all_comparators`, `family_unknown_candidate`, `family_report_incoherent`, `family_single_candidate_signature` em `test_holm_vs_statsmodels.py` |
| A8 | Integração: T = 250, k = 4, reps = 1000, seeds {1, 7}, blocos {3, 10}, dois esquemas, perdas sem empate → domínio sobre `ArchMcs.bootstrap_indices` com a **mesma ordem de eliminação** e p-valores MCS **idênticos** aos de `arch.MCS(method='R')`; não compara `included` | 12 | uma função parametrizada `test_mcs_matches_arch` (token `mcs_matches_arch`) com exatamente **8** ids `<scheme>-seed<s>-block<l>` `PASSED` (contagem na Task 12 e no §3), zero `SKIPPED` |
| A9 | MCS analítico: dominado eliminado primeiro; `mcs_p_value` = máximo acumulado, último = 1; fronteira p̂ = α **incluída**; empate exato elimina **um** modelo (o primeiro modelo-linha); C6 (reps = 999, diferencial constante, índices que reproduzem a amostra → var̂ = 0, moving-block com `block_size = n_obs`); `McsReport` incoerente ergue | 06 (C6 da construção dos índices), 07 | tokens `mcs_dominated_first`, `mcs_cumulative_max`, `mcs_boundary_included`, `mcs_exact_tie_one_model`, `mcs_c6_invalid`, `mcs_report_incoherent` (unit `test_mcs_vs_arch.py`); `bootstrap_request_invalid`, `indices_invalid_row` (`test_bootstrap_indices.py`) |
| A10 | `block_length`: (h = 7, máx. 9,2) → 10; (7, 3,4) → 7; (1, 0,0) → 1; C7 (par faltando, desconhecido, negativo, não-finito) | 07 | tokens `block_length_ceiling`, `block_length_c7_invalid` (unit `test_mcs_vs_arch.py`) |
| A11 | Suítes `[fake, statsmodels]` e `[fake, arch]` verdes (forma, faixa, determinismo, seeds diferem, contiguidade do moving-block, wrap-around do estacionário, `generator`; b̂_sb finito ≥ 0; fake devolve a constante); C9 igual nas pernas; `check_port_coverage.py`/`check_fake_parity.py` verdes sem baseline residual | 09, 10, 11, 12 | bloco A11 do §3 (zero `SKIPPED`, ids `[fake`, `[statsmodels`, `[arch`) + tokens `indices_shape`, `indices_range`, `indices_determinism`, `indices_seeds_differ`, `indices_request_echo`, `indices_generator_filled`, `moving_block_contiguity`, `stationary_wraparound`, `block_length_finite_nonnegative`, `fake_constant_block_length`, `c9_bootstrap_parity`, `c9_block_length_parity`, `dm_c3_parity`, `dm_constant_raises`, `holm_c4_parity`; guarda do adapter `arch_block_length_arithmetic_error` (integração) + ausência de `InferenceBackend`/`McsBackend` no baseline e no teste de arquitetura |
| A12 | Deps `arch>=8,<9`, `statsmodels>=0.15,<0.16`; contrato novo em `_EXPECTED_CONTRACTS` com um caso real por módulo proibido; nenhum unit importa `arch`/`statsmodels`/`scipy`/adapter nem lê arquivo | 01 (deps + contrato), todas (grep) | Task 01 (greps dos pins, `lint-imports`, casos reais) + grep de pureza do §3 (unit e contrato) |
| A13 | `roadmap.md` §6.2 sem "gate A/B/C/F" nem "top-50", `arquivos_a_criar`/`contratos_*` alinhados; §6.4 com `McsBackend`; doc de domínio §6.5, §10 #16b, §10.1 (B-MCS), §11.3; `overview.md` §7, §8, §10 e nota do ADR 0.0.0020; `LAYOUT.md` §2 com `tests/fixtures/` e `tests/architecture/` | 08 (LAYOUT §2), 13 (o resto; §6.4, overview §7/§8 e a nota do ADR 0.0.0020 já estão nos commits 7d70047/b1ef16b — a Task só confere) | greps das Tasks 08 e 13: os ancorados em texto novo reprovariam hoje; `McsBackend` no §6.4, `0.0.0056` no overview e `PairedLossSeries` no S62 são **conferências** que já passam |
| A14 | Medições em §7: precisão da t (df 1–2500, caudas); tempo do MCS (T = 1000, k = 7, reps = 1000); tamanho mínimo de `optimal_block_length` | 02, 06, 07 (re-medição da implementação final; base no §1) | §3 Host: para cada n ∈ {02, 06, 07}, exatamente **uma** linha `^### <data> — [decision] Task n — medição A14` em §7 |
| A15 | `make check` verde; cobertura ≥ 90 % global e por arquivo tocado; ADRs 6.2.0001–0006 e 0.0.0056 `accepted` | todas; gate §3 | `make check` + bloco A15 do §3 (falha se arquivo < 90 % ou arquivo novo ausente) + ≥ 7 ADRs encontrados e todos com `status: accepted` |

**Casos de erro e invariantes → Tasks** (arquivo e tokens obrigatórios; o laço do §3
prova cada token):

| Item | Tasks | Arquivo → tokens |
|---|---|---|
| C1 (VO e fábrica) | 03 | `test_paired_loss_series.py` → `pls_invalid`; `test_paired_pinball_losses.py` → `factory_mismatch`, `factory_no_series`, `factory_single_model` |
| C2 (nome desconhecido, candidato = comparador) | 03, 04, 05 | `test_paired_loss_series.py` → `pls_unknown_name`, `pls_same_model`; `test_dm_vs_r_oracle.py` → `dm_unknown_name`, `dm_same_model`; `test_holm_vs_statsmodels.py` → `family_unknown_candidate` |
| C3 (DM primitivo e validador) | 04, 08, 09/10 | `test_dm_vs_r_oracle.py` → `dm_c3_invalid`, `dm_validate_request`; `test_dm_r_oracle_fixtures.py` → `r_fixture_case_matches` (casos `expected_error`); `test_inference_backend_contract.py` → `dm_c3_parity` |
| C4 (Holm) | 05, 09/10 | `test_inference_input_validation.py` → `p_values_invalid`, `alpha_invalid`, `valid_inputs_accepted`; `test_holm_vs_statsmodels.py` → `holm_c4_invalid`; contrato → `holm_c4_parity` |
| C5 (t) | 02 | `test_student_t.py` → `t_invalid_input`, `t_not_converge` |
| C6 (MCS + `BootstrapIndices`) | 06, 07 | `test_bootstrap_indices.py` → `bootstrap_request_invalid`, `bootstrap_request_accepts`, `indices_invalid_row`, `indices_valid_reps`, `indices_frozen`; `test_mcs_vs_arch.py` (unit) → `mcs_c6_invalid` |
| C7 (bloco) | 07 | `test_mcs_vs_arch.py` (unit) → `block_length_c7_invalid` |
| C8 (relatórios à mão) | 04, 05, 07 | `test_dm_vs_r_oracle.py` → `dm_result_incoherent`; `test_holm_vs_statsmodels.py` → `family_report_incoherent`; `test_mcs_vs_arch.py` (unit) → `mcs_report_incoherent` |
| C9 (paridade de erro no port) | 09–12 | `test_inference_backend_contract.py` → `dm_c3_parity`, `holm_c4_parity`; `test_mcs_backend_contract.py` → `c9_bootstrap_parity`, `c9_block_length_parity`; validador de domínio em `test_bootstrap_indices.py` → `block_length_request_invalid`, `block_length_min_length`, `block_length_constant_series` |
| I1 por horizonte | 03, 05, 07 | `test_paired_pinball_losses.py` → `factory_horizon_propagated`; `test_holm_vs_statsmodels.py` → `family_horizon_propagated`; `test_mcs_vs_arch.py` (unit) → `mcs_horizon_propagated` |
| I2 invariantes do VO | 03 | = C1 |
| I3 L_t pela fábrica | 03 | = A2 |
| I4/I5 DM segue o oráculo; resultado coerente | 04, 08, 10 | `test_dm_vs_r_oracle.py` → `dm_hand_h1`, `dm_sign_swap`, `dm_hln_factor`, `dm_fallback_alternating`, `dm_result_incoherent`; integração → `r_fixture_case_matches`, `r_fixture_t_isolated`; contrato → `dm_random_matches_domain`, `dm_fallback_both_legs` |
| I6/I7 Holm e família fechada | 05, 10 | = A6/A7 |
| I8/I9 MCS 'R' e relatório | 07, 12 | `test_mcs_vs_arch.py` (unit) → `mcs_copies_bootstrap`, `mcs_elimination_names`, `mcs_included_order`, `mcs_all_included`, `mcs_alpha_signature`; integração → `mcs_matches_arch` (+ contagem de 8 ids) |
| I10 regra de bloco | 07 | = A10 |
| I11 domínio puro | 01, todas (T1) | `lint-imports` + `check_layout.py` + mypy strict |
| I12 oráculo por unidade | 02, 08, 10, 12 | tolerâncias do §1 nos módulos de teste |
| I13 testes por camada | todas | grep de pureza do §3 (unit e contrato) |

## 2. Tasks

> Faixa desta Stage: **13 Tasks** (`ROADMAP-1`; ver §1 Exceções). Blocos
> **Container**/**Host** seguem a convenção do §1.

### Task 01 — Dependências `arch`/`statsmodels` + contrato `evaluation-no-inference-lib-leak`

- **Arquivos a modificar:**
  - `pyproject.toml`
  - `uv.lock`
  - `.importlinter`
  - `tests/architecture/test_import_contracts.py`
- **Arquivos a criar:** nenhum.
- **O que fazer (concept §1, I11, A12; ADR 6.2.0003/6.2.0004):**
  1. `pyproject.toml` `dependencies`: bloco comentado no padrão dos anteriores
     (Stage 6.2 / ADRs 6.2.0003–0004 e 0.0.0056; `statsmodels` é o oráculo de
     DM/Holm atrás de `InferenceBackend`, `arch` o gerador de registro dos índices de
     bootstrap e de b̂_sb atrás de `McsBackend`; vivem **só** em
     `features/evaluation/adapters/out/inference/`; gate
     `evaluation-no-inference-lib-leak`; em `dependencies` e não num extra porque as
     pernas reais das suítes e o teste `arch.MCS` rodam no CI; `statsmodels` deixa de
     ser só transitiva): `"arch>=8,<9"` e `"statsmodels>=0.15,<0.16"`.
  2. `uv lock` e `uv sync --inexact` **no container com o volume `ff-step62-venv`**.
  3. `.importlinter`: contrato novo **14** `evaluation-no-inference-lib-leak`
     (`type = forbidden`, padrão do 13): sources
     `financial_forecasting.features.evaluation.{application,domain}`; forbidden
     `arch`, `statsmodels`; `allow_indirect_imports = False`; comentário citando
     concept 6.2 I11 / ADR 6.2.0003–0004 e dizendo que `scipy`/`numpy` já estão no
     13 e `pandas` no `store-no-storage-leak`. O `bc-independence` passa a nº **15**
     (só o rótulo do comentário).
  4. `test_import_contracts.py`: o contrato em `_EXPECTED_CONTRACTS` (comentário
     Stage 6.2 A12); em `_REAL_VIOLATION_CASES`, três casos:
     - `evaluation-no-inference-lib-leak:evaluation-application-imports-arch`
       (`features/evaluation/application/_arch_audit_taint_arch.py`, `import arch`);
     - `…:evaluation-application-imports-statsmodels`
       (`…/application/_arch_audit_taint_statsmodels.py`, `import statsmodels`);
     - `…:evaluation-domain-imports-arch`
       (`features/evaluation/domain/_arch_audit_taint_arch.py`, `import arch`) —
       prova a matrícula de `evaluation.domain` (nem `domain-purity` nem
       `check_layout.py` proíbem `arch`/`statsmodels` ali; lição do Checkpoint C da
       6.1).
- **Detalhes técnicos:** medir a árvore transitiva com `git diff uv.lock` (pacotes
  novos e versões; esperado ao menos `arch` e `formulaic` + dependências dele) e
  registrar `[decision]` em §7; conferir que `statsforecast` segue resolvendo com
  `statsmodels` 0.15 (a suíte de `modeling` no `make check` cobre).
- **Critério de aceite:** `uv lock` resolve; `import arch, statsmodels` imprime
  8.x e 0.15.x; `lint-imports` verde no repo limpo; os três casos novos deixam o
  contrato `broken`; `test_importlinter_declares_expected_contracts` e
  `test_every_forbidden_module_has_a_real_violation_case` verdes.
- **Verificação (T3) — Container:**
  ```bash
  grep -q '"arch>=8,<9"' pyproject.toml
  grep -q '"statsmodels>=0.15,<0.16"' pyproject.toml
  uv run python -c "import arch, statsmodels; print(arch.__version__, statsmodels.__version__); assert arch.__version__.startswith('8.') and statsmodels.__version__.startswith('0.15.')"
  uv run lint-imports
  uv run pytest tests/architecture/test_import_contracts.py -v -k "inference or expected or forbidden_module"
  make check
  ```
- **Commit sugerido:** `build(evaluation): arch e statsmodels cercados pelo contrato evaluation-no-inference-lib-leak [6.2/task-01]`

---

### Task 02 — `student_t_cdf` em stdlib

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/student_t.py`
  - `tests/unit/features/evaluation/test_student_t.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I4, C5; ADR 6.2.0002):** função pura
  `student_t_cdf(x: float, df: float) -> float` (cauda inferior). Validação:
  `is_finite_number(x)` e `is_finite_number(df)` com `df ≥ 1` (bool, `None`,
  não-finito → `ValueError`). Algoritmo = ramos do `pt.c`: x = 0 → 0,5; com
  `x2 = x*x`, se `df > x2` a cauda P(|T| > |x|) = 1 − I_{x2/(df+x2)}(½, df/2)
  (argumento `x2/(df + x2)` e complemento `df/(df + x2)` calculados **direto**); senão
  P(|T| > |x|) = I_{df/(df+x2)}(df/2, ½) (complemento `x2/(df + x2)` direto); cauda
  inferior = ½·P; x > 0 → 1 − cauda. Função privada
  `_regularized_beta_pair(z, one_minus_z, a, b) -> tuple[float, float]` que devolve
  (I, 1 − I) calculando **direto** o termo da fração contínua (DLMF 8.17.22,
  coeficientes 8.17.23; simetria 8.17.4 quando z > (a+1)/(a+b+2)), prefator com
  `math.lgamma`; `_continued_fraction(a, b, z)` pelo Lentz modificado com
  `_MAX_ITERATIONS = 1000` → `ArithmeticError` sem valor parcial.
- **Detalhes técnicos:** nunca `1 − n/(n + x²)` nem `½·(1 − I)` por subtração na
  cauda (armadilha medida no §1). Docstring cita DLMF §8.17 e R `src/nmath/pt.c`.
- **Critério de aceite (A3 unit, C5):**
  - x = 0 → 0,5 exato para df ∈ {1, 2, 30, 2500}.
  - df = 1: F(x) = ½ + arctan(x)/π para |x| ≤ 1 e, na cauda, F(x) = −arctan(1/x)/π
    (x < 0, sem cancelamento) — x ∈ {−10¹⁵⁰, −10⁶, −10, −1, −10⁻⁹, 0,3, 7}.
  - df = 2: F(x) = ½ + x/(2√(2 + x²)) e, na cauda, F(x) = 1/(√(2+x²)(√(2+x²) − x))
    (x < 0) — mesmos x.
  - df = 3: F(x) = ½ + (1/π)[(x/√3)/(1 + x²/3) + arctan(x/√3)] em |x| ≤ 5.
  - Simetria F(−x) = 1 − F(x) (abs ≤ 1e−15) numa grade de x × df ∈ {1, 5, 59, 999}.
  - Argumento complementar: `0.5 - student_t_cdf(-1e-9, 30)` ≈ 10⁻⁹·f(0) com
    f(0) = Γ((ν+1)/2)/(√(νπ)Γ(ν/2)) via `math.lgamma` (rel ≤ 1e−6) — a versão com
    `1 − n/(n + x²)` daria 0.
  - Monotonicidade: F crescente numa grade de 200 x para df ∈ {1, 2, 59, 2499}.
  - C5: df ∈ {0,5; 0; −1; nan; inf; True; None}, x ∈ {nan; inf; −inf; None; True}
    → `ValueError`; `monkeypatch.setattr(student_t, "_MAX_ITERATIONS", 1)` num ponto
    que exige > 1 iteração → `ArithmeticError`.
  - **Tokens** (`test_student_t.py`): `t_zero_half`, `t_df1_closed`, `t_df2_closed`, `t_df3_closed`, `t_symmetry`, `t_complement_no_cancel`, `t_monotone`, `t_invalid_input`, `t_not_converge`.
  - **A14.1 (re-medição):** sondagem fora do repo (scipy do venv, que o teste unit
    não pode importar) repete a grade do §1 com a função final e registra
    `### <data> — [decision] Task 02 — medição A14 (t de Student) — <autor>` em §7
    com a tabela df × erro.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_student_t.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): student_t_cdf stdlib pelos ramos do pt.c com cauda direta [6.2/task-02]`

---

### Task 03 — VO `PairedLossSeries` + fábrica `paired_pinball_losses`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/paired_loss_series.py`
  - `src/financial_forecasting/features/evaluation/domain/services/paired_pinball_losses.py`
  - `tests/unit/features/evaluation/test_paired_loss_series.py`
  - `tests/unit/features/evaluation/test_paired_pinball_losses.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I1–I3, C1, C2; ADR 6.2.0001):**
  - VO frozen stdlib com a assinatura do concept §4. `__post_init__` (`ValueError`,
    mensagem nomeando modelo/índice): `horizon` int não-bool ≥ 1; `len(models) ≥ 2`,
    nomes `str` não-vazios e únicos; `T = len(target_timestamps) ≥ 2` e `T > horizon`;
    timestamps estritamente crescentes (comparação de string ISO, como a
    `CoverageSeries`); `len(losses) == len(models)`; toda coluna com T valores,
    `is_finite_number` e ≥ 0. **Sem** checagem de variância (I2).
  - `n_points`; `losses_of(model)`; `differential(first, second)` = L_first −
    L_second ponto a ponto; `model_pairs()` = pares não-ordenados `(models[i],
    models[j])`, i < j, na ordem de `models`. Nome desconhecido ou `first == second`
    → `ValueError` (decisão de detalhe do §1).
  - Fábrica `paired_pinball_losses(series_by_model: Mapping[str,
    Sequence[CoverageSeries]]) -> PairedLossSeries`: < 2 modelos → `ValueError`;
    modelo com 0 séries → `ValueError`; todas as séries (entre seeds e entre modelos)
    com `horizon`, `target_timestamps` e `levels` **iguais** aos da primeira → senão
    `ValueError` nomeando modelo e seed; coluna = `math.fsum` das S colunas de
    `PinballScore.per_point_losses`, ponto a ponto, / S; ordem dos modelos = do
    mapping. Não importa nada de `modeling`; não edita `coverage_series.py`.
- **Critério de aceite (A1, A2):**
  - A1: um teste por ramo de C1 — `horizon` 0 e `True`; k = 1; nome vazio; nome
    repetido; T = 1; **T = h**; **T < h**; timestamp repetido e fora de ordem;
    `len(losses) ≠ k`; coluna com tamanho ≠ T; perda `nan`, `inf`, `None`, `True` e
    **negativa**. Série k = 3 aceita com duas colunas de diferencial constante
    entre si (`losses_of`, `differential` com sinal L_first − L_second e
    `model_pairs() == (("a","b"),("a","c"),("b","c"))` conferidos à mão); C2 em
    `losses_of` e `differential`; frozen (`FrozenInstanceError`).
  - A2: S = 1 → coluna **igual** (`==`) a `PinballScore.per_point_losses`; S = 3 →
    média ponto a ponto (valores diádicos → igualdade exata); cada ramo de erro da
    fábrica com um teste (horizonte, timestamps, grade divergentes **entre seeds** e
    **entre modelos**; modelo sem séries; mapping com 1 modelo); I1: resultado com
    `horizon`/`target_timestamps` da entrada. Séries montadas com a fixture
    `make_series` do `conftest.py` da 6.1.
  - **Tokens:** `test_paired_loss_series.py` → `pls_invalid`, `pls_unknown_name`, `pls_same_model`, `pls_degenerate_pair_accepted`, `pls_model_pairs_order`, `pls_differential_sign`, `pls_losses_of_column`, `pls_frozen`;
    `test_paired_pinball_losses.py` → `factory_single_seed_identity`, `factory_seed_mean`, `factory_mismatch`, `factory_no_series`, `factory_single_model`, `factory_horizon_propagated`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_paired_loss_series.py tests/unit/features/evaluation/test_paired_pinball_losses.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): PairedLossSeries e fábrica de L_t com média entre seeds [6.2/task-03]`

---

### Task 04 — `DieboldMariano` com o seu validador

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/diebold_mariano.py`
  - `tests/unit/features/evaluation/test_dm_vs_r_oracle.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I4, I5, C2, C3, C8; ADR 6.2.0003 itens 1/3):**
  - `DmVarianceEstimator` (StrEnum) e, **no mesmo módulo** (decisão de detalhe do §1,
    sem ciclo de import), o **validador único** `validate_dm_request(*,
    candidate_losses, comparator_losses, horizon, variance_estimator) -> None`
    (`ValueError`): tamanhos iguais; T ≥ 2; todo valor `is_finite_number` e ≥ 0;
    `horizon` int não-bool ≥ 1 e **< T**; `variance_estimator` membro de
    `DmVarianceEstimator` (string crua → erro). Chamado pelo primitivo, pelo fake
    (Task 09, via o primitivo) e pelo adapter (Task 10).
  - `DieboldMarianoResult` com `__post_init__` (I5: `fallback_applied ⇔
    horizon_used ≠ horizon`; `horizon_used ∈ {horizon, 1}`; `degrees_of_freedom ==
    n_points − 1`; `long_run_variance` finita e > 0; `statistic` finito; `p_value ∈
    [0, 1]`; `horizon ≥ 1`, `n_points ≥ 2`).
  - Primitivo `diebold_mariano(...)`: valida; d_t = cand − comp; d̄ = `fsum`/T;
    γ̂_k = `fsum`((d_t − d̄)(d_{t−k} − d̄), t = k..T−1)/T; retangular (γ̂₀ + 2Σ_{k<h}
    γ̂_k)/T, Bartlett com pesos 1 − k/h; var̂ ≤ 0 e h > 1 → recalcula **tudo** com
    h = 1 e `fallback_applied = True`; var̂ ≤ 0 e h = 1 → `ValueError("Variance of DM
    statistic is zero")`; S1* = HLN(T, h_used)·d̄/√var̂, HLN =
    ((T + 1 − 2h + h(h−1)/T)/T)^{1/2}; p = `student_t_cdf(S1*, T − 1)`.
  - `DieboldMariano.compare(series, *, candidate, comparator, variance_estimator=
    RECTANGULAR)`: C2 (nome fora de `series.models`, candidato = comparador) e
    delega ao primitivo com `series.losses_of(...)`.
- **Critério de aceite (A4 unit, A1 parte, C3, C8):**
  - Caso à mão h = 1: candidato (1, 2, 3, 4), comparador (2, 2, 2, 2) → d̄ = 0,5,
    var̂ = 0,3125, HLN = √0,75, S1* = √0,6, p = F₃(√0,6) pela forma fechada df = 3;
    trocar candidato e comparador troca o sinal de S1* e p → 1 − p.
  - h = 2 retangular e Bartlett num d com γ̂₁ > 0 (valores calculados à mão no
    teste; pesos 1 e ½); fator HLN conferido isolado (T = 10, h = 7 →
    ((10 + 1 − 14 + 4,2)/10)^{1/2} = √0,12).
  - Fallback analítico: candidato (3, 1)×5, comparador (2,)×10 → d = ±1; h = 2
    retangular → var̂ < 0 → `fallback_applied`, `horizon_used = 1`, S1* = 0, p = 0,5;
    o mesmo com Bartlett **não** cai no fallback (var̂ = 1/T² > 0).
  - Diferencial constante com h = 2 → fallback e depois `ValueError`; com h = 1 →
    `ValueError`.
  - C3 no primitivo e em `validate_dm_request` (um teste por ramo): tamanhos
    diferentes, T = 1, `nan`/`inf`/`None`/`True`, perda negativa, h = 0, h `True`,
    **h = T**, **h > T**, estimador `"rectangular"` (string crua).
  - A1 (parte): `compare` sobre uma série k = 3 em que os dois comparadores têm
    diferencial constante entre si roda para (cand, comp1) e (cand, comp2); C2 com
    nome desconhecido e cand = comp.
  - C8: `DieboldMarianoResult` à mão ergue em cada ramo do `__post_init__`.
  - Docstring do módulo de teste declara o desvio de caminho do D7 (nome do
    roadmap, conteúdo analítico; o R vive na integração da Task 08).
  - **Tokens** (`test_dm_vs_r_oracle.py`): `dm_hand_h1`, `dm_sign_swap`, `dm_h2_rectangular`, `dm_h2_bartlett`, `dm_hln_factor`, `dm_fallback_alternating`, `dm_constant_differential`, `dm_c3_invalid`, `dm_validate_request`, `dm_unknown_name`, `dm_same_model`, `dm_degenerate_comparator_pair`, `dm_result_incoherent`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_dm_vs_r_oracle.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): DieboldMariano HLN unilateral com fallback do oráculo e validador único [6.2/task-04]`

---

### Task 05 — `HolmCorrection` e a família por horizonte

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/inference_input_validation.py`
  - `src/financial_forecasting/features/evaluation/domain/services/holm_correction.py`
  - `tests/unit/features/evaluation/test_inference_input_validation.py`
  - `tests/unit/features/evaluation/test_holm_vs_statsmodels.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I6, I7, C2, C4, C8; ADR 6.2.0003 item 2):**
  - `inference_input_validation.py` (sem import de serviço — só `is_finite_number`):
    `validate_p_values(p_values)` (não-vazia; cada valor `is_finite_number` em
    [0, 1]) e `validate_alpha(alpha)` (`is_finite_number`, 0 < α < 1) — este também
    consumido pelo MCS (Task 07).
  - `holm_adjust(p_values) -> tuple[float, ...]`: ordena por p (estável), p̃_(j) =
    max_{i≤j} min(1, (m − i + 1)·p_(i)), devolve **na ordem de entrada**.
    `holm_reject(p_values, *, alpha)`: p̃ ≤ α.
  - `HolmComparison`, `DmHolmFamilyReport` com o `__post_init__` do concept §4.
  - `HolmCorrection.family(series, *, candidate: str, alpha: float,
    variance_estimator=RECTANGULAR)`: C2; `validate_alpha`; um
    `DieboldMariano.compare` por **cada** outro modelo, na ordem de `series.models`
    (m = k − 1); `holm_adjust` sobre os p-valores; relatório. `alpha` sem default.
- **Critério de aceite (A6 unit, A7):**
  - Holm diádico: p = (0,125; 0,25; 0,0625; 0,5) → (0,375; 0,5; 0,25; 0,5); m = 1 →
    p bruto; teto: (0,5; 0,75) → (1,0; 1,0); empate (0,125; 0,125) → (0,25; 0,25)
    em qualquer ordem; ordem de entrada preservada; fronteira: α = 0,25 com
    p̃ = 0,25 → rejeita.
  - C4 (um teste por ramo, validador e funções): lista vazia; p −0,1, 1,1, `nan`,
    `None`, `True`; α ∈ {0; 1; −0,1; `nan`; `True`}.
  - A7: série k = 7 → 6 comparações na ordem do VO sem o candidato; cada `dm ==
    DieboldMariano.compare(series, candidate=c, comparator=m)`; `adjusted_p_value`
    = `holm_adjust`; `rejected` coerente; I1 (`horizon`/`n_points` da série). C2:
    candidato desconhecido.
  - C8: `DmHolmFamilyReport` à mão ergue — lista vazia; comparador repetido;
    candidato entre os comparadores; `n_points`/`horizon` misturados; estimador
    misturado; ajustado ≠ `holm_adjust`; `rejected` incoerente com α; α fora de
    (0, 1) (um teste por ramo).
  - Antigo "gate B": `inspect.signature(HolmCorrection.family)` tem exatamente
    `series, candidate, alpha, variance_estimator`, `candidate` anotado `str`,
    `alpha` keyword-only **sem default**.
  - **Tokens:** `test_inference_input_validation.py` → `p_values_invalid`, `alpha_invalid`, `valid_inputs_accepted`;
    `test_holm_vs_statsmodels.py` → `holm_dyadic`, `holm_single_p`, `holm_cap_one`, `holm_tie_order_free`, `holm_input_order`, `holm_boundary_rejects`, `holm_c4_invalid`, `family_k7_all_comparators`, `family_unknown_candidate`, `family_report_incoherent`, `family_single_candidate_signature`, `family_horizon_propagated`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_holm_vs_statsmodels.py tests/unit/features/evaluation/test_inference_input_validation.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): HolmCorrection com família fechada por horizonte [6.2/task-05]`

---

### Task 06 — VO `BootstrapIndices` + validadores do `McsBackend`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/bootstrap_indices.py`
  - `tests/unit/features/evaluation/test_bootstrap_indices.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, C6, C9; ADR 6.2.0004 itens 2/3):**
  - `BootstrapScheme` (StrEnum `stationary`/`moving_block`).
  - `validate_bootstrap_request(*, n_obs, block_size, reps, seed, scheme)`
    (`ValueError`): `n_obs`, `block_size`, `reps`, `seed` int **não-bool**;
    `n_obs ≥ 2`; `block_size ≥ 1`; `reps ≥ 1`; `scheme` membro de
    `BootstrapScheme`; `moving_block` exige `block_size < n_obs`.
  - `MIN_BLOCK_LENGTH_OBS: Final = 11` (medição do §1 item 4, citada no docstring) e
    `validate_block_length_request(series)`: `len ≥ MIN_BLOCK_LENGTH_OBS`; todo
    valor `is_finite_number`; série **não constante** (todos iguais → erro).
  - `BootstrapIndices` frozen: `__post_init__` chama `validate_bootstrap_request`
    com `reps = len(indices)`; `generator` `str` não-vazia; cada linha com `n_obs`
    índices int não-bool em [0, `n_obs`). `reps` = `len(indices)`.
- **Critério de aceite (C6 construção, C9 domínio):**
  - Um teste por ramo de cada validador: `n_obs` 1, `True`, 2,0; `block_size` 0;
    `reps` 0; seed `True`, 1,0, `None`; scheme `"stationary"` (string crua);
    moving-block com `block_size == n_obs` e `> n_obs` (erro) e `n_obs − 1` (ok);
    estacionário com `block_size > n_obs` aceito; série de 10 pontos (erro) e de 11
    (ok); `nan`/`inf`/`None`/`True` na série; série constante.
  - `BootstrapIndices`: linha com tamanho ≠ `n_obs`; índice −1 e `n_obs`; índice
    `True`; `generator` vazio; `indices = ()` (reps 0) → `ValueError`; caso válido
    com `reps` correto; frozen.
  - **Tokens** (`test_bootstrap_indices.py`): `bootstrap_request_invalid`, `bootstrap_request_accepts`, `block_length_request_invalid`, `block_length_min_length`, `block_length_constant_series`, `indices_invalid_row`, `indices_valid_reps`, `indices_frozen`.
  - **A14.3 (re-medição):** com o `arch` instalado (Task 01), sondagem fora do repo
    repete a varredura n = 1..15 e a robustez n = 11..60 do §1 e registra
    `### <data> — [decision] Task 06 — medição A14 (tamanho mínimo de optimal_block_length) — <autor>`
    em §7.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_bootstrap_indices.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): BootstrapIndices com proveniência e validadores únicos do McsBackend [6.2/task-06]`

---

### Task 07 — `ModelConfidenceSet` ('R') + regra de bloco

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/model_confidence_set.py`
  - `tests/unit/features/evaluation/test_mcs_vs_arch.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I8–I10, C6–C8; ADR 6.2.0004 itens 1/4, 6.2.0005):**
  - `MIN_MCS_REPS: Final = 1000`; `McsElimination`; `McsReport` com `__post_init__`
    (decisão de detalhe do §1: `statistic == "R"`; α via `validate_alpha`;
    `horizon ≥ 1`, `n_points > horizon`; `block_size ≥ 1`; `reps ≥ MIN_MCS_REPS`;
    `generator` não-vazio; ≥ 2 eliminações com nomes únicos não-vazios; cada
    `step_p_value` em [0, 1]; `mcs_p_value` = máximo acumulado dos `step_p_value`;
    último `step_p_value == mcs_p_value == 1.0`; `set(included) == {m : mcs_p ≥ α}`
    sem repetição).
  - `evaluate(series, *, bootstrap, alpha)` — `alpha` sem default; pré-condições na
    ordem: `validate_alpha`; `bootstrap.reps ≥ MIN_MCS_REPS`; `bootstrap.n_obs ==
    series.n_points`; nenhum par de `model_pairs()` com diferencial constante;
    depois: L̄_i (`fsum`/T); médias bootstrap L̄*_{i,b} (`fsum` sobre a linha b)/T;
    var̂_ij = `fsum`((L̄*_i,b − L̄*_j,b − d̄_ij)², b)/B **uma vez**; algum var̂_ij ≤ 0
    → `ValueError`; t_ij = d̄_ij/√var̂_ij; por passo sobre os incluídos: T_R = max
    t_ij, p do passo = #{b : T_R < max t*_ij,b}/B, elimina o modelo-linha do máximo
    (empate exato → o **primeiro** modelo-linha na ordem de `series.models`); p MCS =
    máximo acumulado; sobrevivente com 1,0; `included` = {m : p̂ ≥ α} na ordem de
    `series.models`; `scheme`/`block_size`/`reps`/`seed`/`generator` copiados do
    `bootstrap`.
  - `block_length(series, *, block_estimates)`: chaves = exatamente as tuplas de
    `series.model_pairs()` (faltando, sobrando ou invertida → `ValueError`);
    estimativas `is_finite_number` e ≥ 0; devolve `max(h, math.ceil(max))` como
    `int`.
- **Critério de aceite (A9, A10, C6, C7, C8; I1, I9):** índices montados à mão
  (unit, sem RNG de biblioteca; `generator = "manual (teste)"`), perdas
  inteiras/diádicas:
  - Dominado: k = 3, C com perdas inteiras sistematicamente maiores que as de A e B
    (ex.: A + 2 + ε_t com ε_t ∈ {0, 1} **não constante** — senão o diferencial
    seria constante e o MCS ergueria) → C eliminado primeiro; `mcs_p_value` =
    máximo acumulado; último = 1,0; I1.
  - Fronteira p̂ = α: k = 2, 900 linhas identidade (t* = 0) + 100 linhas de um mesmo
    reamostrado com |d̄* − d̄| > |d̄| → p do passo = 100/1000 = 0,1 exato; α = 0,1 →
    **incluído**; α = 0,101 → excluído.
  - Empate exato: k = 3, B = A com duas posições p, q trocadas (A[p] ≠ A[q]), C com
    C[p] = C[q], e o conjunto de 1000 linhas fechado pela troca de p e q (500
    linhas + as suas imagens) → d̄_AC = d̄_BC e var̂_AC = var̂_BC exatamente, logo
    t_AC = t_BC; A e B piores que C → a 1ª eliminação é **só** A (B segue incluído
    no passo seguinte).
  - Todos incluídos ("não é erro", concept §6): dados pouco informativos (k = 3,
    diferenças pequenas diante da variância bootstrap) com α = 0,10 →
    `included == series.models`, sem exceção.
  - I9, parte de construção: `report.scheme/block_size/reps/seed/generator` iguais
    aos do `BootstrapIndices`; `{e.model for e in eliminations} ==
    set(series.models)` com k entradas; `included` na ordem de `series.models`
    num caso com ≥ 2 incluídos eliminados **fora** dessa ordem.
  - C6: α ∈ {0; 1; `nan`}; reps = 999; `n_obs ≠ T`; diferencial constante num par;
    1000 linhas identidade (reproduzem a amostra) → var̂ = 0; moving-block com
    `block_size = n_obs` barrado já no `BootstrapIndices` (Task 06).
  - C8: `McsReport` à mão ergue em cada ramo do `__post_init__` (um teste por ramo).
  - A10: (h = 7, máx. 9,2) → 10; (7, 3,4) → 7; (1, 0,0) → 1; retorno `int`. C7: par
    faltando; par desconhecido; par invertido; estimativa −0,1, `nan`, `inf`.
  - `inspect.signature`: `alpha` keyword-only sem default em `evaluate`.
  - **Tokens** (`test_mcs_vs_arch.py`, unit): `mcs_dominated_first`, `mcs_cumulative_max`, `mcs_boundary_included`, `mcs_exact_tie_one_model`, `mcs_all_included`, `mcs_copies_bootstrap`, `mcs_elimination_names`, `mcs_included_order`, `mcs_c6_invalid`, `mcs_report_incoherent`, `block_length_ceiling`, `block_length_c7_invalid`, `mcs_alpha_signature`, `mcs_horizon_propagated`.
  - **A14.2 (re-medição):** tempo de `evaluate` a T = 1000, k = 7, reps = 1000 (índices
    `random.Random` estacionários, bloco 10) por sondagem fora do repo; registrar
    `### <data> — [decision] Task 07 — medição A14 (custo do MCS) — <autor>` em §7;
    > 10 s → `[finding]` de desempenho antes de seguir.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_mcs_vs_arch.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): ModelConfidenceSet 'R' sobre BootstrapIndices e regra de bloco com teto [6.2/task-07]`

---

### Task 08 — Oráculo R `dm.test` em fixtures + proveniência + golden test do DM

- **Arquivos a criar:**
  - `tests/fixtures/r_oracle/Dockerfile`
  - `tests/fixtures/r_oracle/dm_test_cases.R`
  - `tests/fixtures/r_oracle/dm_test_cases.json` (gerado)
  - `tests/fixtures/r_oracle/dm_test_cases.sessionInfo.txt` (gerado)
  - `tests/integration/features/evaluation/test_r_oracle_provenance.py`
  - `tests/integration/features/evaluation/test_dm_r_oracle_fixtures.py`
- **Arquivos a modificar:**
  - `docs/LAYOUT.md` — §2: `tests/fixtures/` (dados versionados de teste, ex.
    `r_oracle/` do ADR 6.2.0006) e `tests/architecture/` (testes dos gates) na
    árvore de `tests/` (7º arquivo, exceção declarada no §1).
- **O que fazer (concept A4, A5, A13 parte, I12; ADR 6.2.0006):**
  - `Dockerfile` com **exatamente** as duas linhas do ADR 6.2.0006 item 2 (cada uma
    terminada em `\n`), byte-idêntico ao da 6.3.
  - `dm_test_cases.R` determinístico (`set.seed` fixo; `library(forecast)`,
    `library(jsonlite)`): para cada caso chama `dm.test(e1 = candidato, e2 =
    comparador, alternative = "less", h, power = 1, varestimator)` capturando aviso e
    erro. Entradas de ponto flutuante como `{"dec": sprintf("%.17g"), "hex":
    sprintf("%a")}` (escalar ou lista), com `stopifnot(as.numeric(sprintf("%.17g",
    x)) == x)` antes de gravar; `dec` e as saídas `%.17g` injetados **verbatim**
    (`jsonlite` `json_verbatim = TRUE`; `toJSON(digits = NA)` só escreve 15
    dígitos); inteiros/strings em JSON simples. Grava o `.json` e o `sessionInfo()`
    em `dm_test_cases.sessionInfo.txt`.
  - **Schema da unidade** (local; o teste genérico não depende dele): `{"provenance":
    {…}, "cases": [{"id", "description", "inputs": {"candidate_losses",
    "comparator_losses", "horizon", "varestimator", "alternative", "power"},
    "expected": {"statistic", "p_value", "horizon_used", "warning"}} | {…,
    "expected_error": "<mensagem R>"}]}`.
  - **`provenance` — valores pelas regras do Step** (sobre o ADR 6.2.0006; conferidos
    na `ff-r-oracle:4.4.1`):
    - `generator` = `tests/fixtures/r_oracle/dm_test_cases.R` (relativo à **raiz do
      repo**);
    - `image` = `"rocker/r-ver:4.4.1"`;
    - `r_version` = `paste(R.version$major, R.version$minor, sep = ".")` → `"4.4.1"`
      (`R.version$major.minor` não existe — dá `NULL`);
    - `packages[p]` = `packageDescription(p)$Version` para `forecast` e `jsonlite`
      — a grafia do `sessionInfo()` (ex.: `rugarch` `1.5-3`, enquanto
      `packageVersion()` dá `1.5.3`; `forecast` `8.23.0`), para que a checagem
      `<nome>_<versão>` case por texto;
    - `cran_snapshot` = `getOption("repos")[["CRAN"]]`;
    - `generated_at` = `format(Sys.Date(), "%Y-%m-%d")`;
    - `session_info` = `dm_test_cases.sessionInfo.txt` (relativo ao **JSON**);
    - `command` = `docker build -t ff-r-oracle:4.4.1 tests/fixtures/r_oracle &&
      docker run --rm -v "$PWD/tests/fixtures/r_oracle:/work" -w /work
      ff-r-oracle:4.4.1 Rscript dm_test_cases.R`;
    - chaves extras são **permitidas** (ex.: `t_max` da 6.3).
  - **Casos** (ADR 6.2.0006 item 4; perdas ≥ 0, T > h sempre): h = 1 e h = 7 ×
    `acf`/`bartlett` × candidato melhor/pior sobre T = 60 (8); T = 250 com h = 7
    retangular (perdas com dependência, candidato melhor); T pequeno sem erro (T = 8,
    h = 1 e h = 2); fallback h = 7 → 1 (busca determinística de seed com variância
    retangular ≤ 0, teto de seeds e `stopifnot(found)`) e o mesmo dado com
    `bartlett`; fallback analítico h = 2 (d = ±1, T = 10); diferencial constante com
    h = 2 (aviso de fallback e depois o erro "Variance of DM statistic is zero");
    erro h > T (T = 6, h = 7); erro variância nula com h = 1. **Nenhum** caso h = T.
  - `test_r_oracle_provenance.py` (integração; lê arquivo): função
    `_fixture_problems(json_path, *, repo_root) -> list[str]` — `generator`
    resolvido contra `repo_root`, `session_info` e `Dockerfile` contra o diretório do
    JSON — com **uma regra por item** (as seis primeiras são o ADR 6.2.0006 item 3;
    as duas últimas, as regras do Step acima):
    1. chave obrigatória de `provenance` ausente (`generator`, `image`,
       `r_version`, `packages`, `cran_snapshot`, `generated_at`, `session_info`,
       `command`);
    2. `generator` inexistente;
    3. `session_info` inexistente;
    4. `r_version` sem `R version <v> ` no `sessionInfo`;
    5. pacote de `packages` sem `<nome>_<versão>` no `sessionInfo`;
    6. em **todo** objeto cujo conjunto de chaves é `{"dec", "hex"}` (varredura
       recursiva): formas diferentes (escalar × lista; listas de tamanhos diferentes)
       ou `float(dec) != float.fromhex(hex)`;
    7. `image` ≠ imagem do `FROM` do `Dockerfile`;
    8. `generated_at` fora de `^\d{4}-\d{2}-\d{2}$` (o regex é o gate de
       **formato**: no Python ≥ 3.11 `date.fromisoformat("20260928")` é aceito) ou
       não aceito por `date.fromisoformat` (data inexistente).
    Testes: parametrizado por **todo** `tests/fixtures/r_oracle/*.json` (glob; ≥ 1
    arquivo, senão falha) → `== []`; `Dockerfile` == as duas linhas; **um caso de
    violação construído por regra** num repo mínimo em `tmp_path` (cópia da fixture
    real, do `.R`, do `sessionInfo` e do `Dockerfile`, com a quebra injetada), cada
    um afirmando a mensagem da sua regra — as 8 chaves removidas uma a uma (regra 1),
    gerador apagado, `sessionInfo` apagado, `r_version` trocado, versão de pacote
    trocada, `hex` de outro double, lista `dec` com um item a menos, escalar × lista,
    `image` diferente do `FROM`, `generated_at = "20260928"` (formato), `generated_at =
    "2026-02-30"` (formato ISO, data inválida — exercita o ramo do `fromisoformat`);
    e um caso positivo com
    chave extra (`t_max`) → `== []`. O validador verde sobre fixture boa é vácuo sem
    esses casos (lição da 6.1).
  - `test_dm_r_oracle_fixtures.py` (integração): para **cada** caso (parametrizado
    por `id`), entradas via `float.fromhex`; `expected_error` →
    `pytest.raises(ValueError)` no primitivo `diebold_mariano`; senão `horizon_used`
    igual, `fallback_applied == (horizon_used != horizon)`, estatística por
    `math.isclose(rel_tol=1e-11, abs_tol=1e-14)` e p por `_assert_p_close`
    (tolerâncias do §1); isolamento da t: `student_t_cdf(expected.statistic, T − 1)`
    vs `expected.p_value` pelo mesmo helper (R `pt` como oráculo da t — concept I12).
    `test_r_fixture_covers_required_scenarios` confere que os casos cobrem h ∈ {1, 7},
    os dois estimadores, sinal dos dois lados, **algum caso sem erro com T ≤ 10**
    ("T pequeno" do A4), um fallback, o constante h = 2, h > T e variância nula
    h = 1, e que nenhum tem `horizon == T`.
  - **Tokens** (um por regra; nomes das funções, sem o id `[...]` — o id
    `[r_version]` de `prov_missing_key` **não** satisfaz `prov_r_version_mismatch`):
    `test_r_oracle_provenance.py` → `prov_real_fixture_clean`, `prov_dockerfile_two_lines`, `prov_missing_key`, `prov_generator_missing`, `prov_session_info_missing`, `prov_r_version_mismatch`, `prov_package_version_mismatch`, `prov_hex_mismatch`, `prov_dec_length_mismatch`, `prov_scalar_list_shape_mismatch`, `prov_image_from_mismatch`, `prov_generated_at_not_iso`, `prov_generated_at_invalid_date`, `prov_extra_key_allowed`;
    `test_dm_r_oracle_fixtures.py` → `r_fixture_case_matches`, `r_fixture_t_isolated`, `r_fixture_covers_required_scenarios`.
- **Detalhes técnicos:** geração (uma vez, Host com Docker):
  `MSYS_NO_PATHCONV=1 docker run --rm -v "<worktree>/tests/fixtures/r_oracle:/work"
  -w /work ff-r-oracle:4.4.1 Rscript dm_test_cases.R`. O CI não roda R (ADR
  6.2.0006). Os testes resolvem caminhos com `pathlib` relativo ao arquivo de teste
  (sem depender do cwd).
- **Critério de aceite (A4 integração, A5, A13 parte):** os dois módulos verdes com
  zero `SKIPPED`; todos os casos do JSON reproduzidos; cada violação construída
  deixa `_fixture_problems` com a mensagem da sua regra; `Dockerfile`
  byte-idêntico; LAYOUT §2 com as duas pastas.
- **Verificação (T1 + docs):**
  - **Host:**
    ```bash
    printf 'FROM rocker/r-ver:4.4.1\nRUN install2.r --error --ncpus 4 forecast rugarch jsonlite\n' | cmp - tests/fixtures/r_oracle/Dockerfile
    L=$(awk '/^## 2\./,/^## 3\./' docs/LAYOUT.md); test -n "$L"
    grep -q "fixtures/" <<<"$L"
    grep -q "architecture/" <<<"$L"
    python scripts/check_docs_pointers.py
    ```
  - **Container:**
    ```bash
    f=$(mktemp)
    uv run pytest tests/integration/features/evaluation/test_r_oracle_provenance.py tests/integration/features/evaluation/test_dm_r_oracle_fixtures.py -v -rs | tee "$f"
    test -s "$f"
    if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
    make check-task SLICE=evaluation
    make docs-check
    ```
- **Commit sugerido:** `test(evaluation): oráculo R dm.test em fixture com proveniência testada e golden do DM [6.2/task-08]`

---

### Task 09 — Port `InferenceBackend` + `FakeInferenceBackend` + suíte de contrato (perna `fake`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/inference_backend.py`
  - `tests/fakes/features/evaluation/fake_inference_backend.py`
  - `tests/contract/features/evaluation/test_inference_backend_contract.py`
- **Arquivos a modificar (ADR 6.1.0005):**
  - `scripts/arch_baseline.toml` — entrada transitória `InferenceBackend`
    (`motivo` citando ADR 6.1.0005, "removida na 6.2 Task 10", `issue = 114`);
  - `tests/architecture/test_port_coverage_gate.py` —
    `test_real_repo_violations_are_exactly_the_declared_baseline` passa a esperar
    `["Hasher", "InferenceBackend"]`, com comentário citando o ADR e a Task 10.
- **O que fazer (concept §4; ADR 6.2.0003 item 3):**
  - Port `InferenceBackend(Protocol)` com a **assinatura literal do concept §4**
    (`diebold_mariano`, `holm_adjusted`, `holm_rejected`, keyword-only), importando
    `DieboldMarianoResult`/`DmVarianceEstimator` do domínio; docstring com a
    convenção de sinal (d = L_cand − L_comp, H1: E[d] < 0) e as exigências C3/C4.
  - `FakeInferenceBackend`: cada método **só delega** ao primitivo de domínio
    (`diebold_mariano`, `holm_adjust`, `holm_reject`) — sem fórmula própria.
  - Suíte parametrizada por factory, ids `["fake"]` nesta Task (a Task 10 acrescenta
    `"statsmodels"` **sem** `skipif`), dados só por `random.Random(20260928)`: DM
    contra o **domínio** em pares aleatórios (T ∈ {12, 30, 250}, h ∈ {1, 2, 7}, dois
    estimadores, candidato melhor/pior) comparando `horizon_used`/`fallback_applied`
    exatos e estatística/d̄/var̂/p com as tolerâncias do §1; fallback analítico
    (d = ±1, h = 2); diferencial constante h = 2 → `ValueError`; C3 (tamanhos,
    T = 1, `nan`/`inf`, negativo, h = 0, h = T, h > T, estimador string) e C4
    (vazia, p fora de [0, 1], `nan`, α ∈ {0, 1}) → `ValueError`; Holm: 200 listas
    aleatórias (m 1–7) com `holm_adjusted` igual (`==`) ao domínio e
    `holm_rejected` igual para α ∈ {0,01; 0,025; 0,05; 0,10; 0,20}.
  - **Tokens** (`test_inference_backend_contract.py`): `dm_random_matches_domain`, `dm_fallback_both_legs`, `dm_constant_raises`, `dm_c3_parity`, `holm_c4_parity`, `holm_adjusted_equal`, `holm_rejected_equal`.
- **Critério de aceite:** suíte verde no id `fake`; `check_port_coverage.py` e
  `check_fake_parity.py` verdes (entrada nova tolerada); `test_port_coverage_gate.py`
  verde; `lint-imports` verde (port importa só stdlib + domínio).
- **Verificação (T3) — Container:**
  ```bash
  uv run pytest tests/contract/features/evaluation/test_inference_backend_contract.py -v
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  uv run python scripts/check_fake_parity.py
  grep -q 'key = "InferenceBackend"' scripts/arch_baseline.toml
  make check
  ```
- **Commit sugerido:** `feat(evaluation): port InferenceBackend com fake e suíte de contrato [6.2/task-09]`

---

### Task 10 — Adapter `StatsmodelsHac` + perna `statsmodels` (reverte o baseline)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/inference/__init__.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/inference/statsmodels_hac.py`
- **Arquivos a modificar:**
  - `tests/contract/features/evaluation/test_inference_backend_contract.py` (factory `"statsmodels"`)
  - `scripts/arch_baseline.toml` — remove `InferenceBackend`;
  - `tests/architecture/test_port_coverage_gate.py` — volta a `["Hasher"]` e remove o comentário da janela.
- **O que fazer (concept §4 Adapters, §8 Externas; ADR 6.2.0003 item 3):** classe
  pública `StatsmodelsHac` (docstring: satisfaz o port `InferenceBackend`). Cada
  método chama primeiro o validador de domínio (`validate_dm_request` de
  `diebold_mariano.py`; `validate_p_values`/`validate_alpha` de
  `inference_input_validation.py`) e então:
  - `diebold_mariano`: `d = np.asarray(cand) − np.asarray(comp)`;
    `OLS(d, np.ones(T)).fit().get_robustcov_results(cov_type="HAC",
    kernel="uniform" | "bartlett", maxlags=h − 1, use_correction=False)`; var̂ =
    `float(cov_params()[0, 0])`; **o adapter checa o sinal** (o statsmodels não
    ergue): ≤ 0 com h > 1 → refaz com h = 1 e marca fallback; ≤ 0 com h = 1 →
    `ValueError`; S1* = fator HLN × `params[0]`/√var̂ (fator escrito no adapter —
    o concept manda aplicá-lo "por fora"; quem o verifica contra uma fonte
    independente é o R, Task 08); p = `float(scipy.stats.t.cdf(S1*, T − 1))`;
    devolve o `DieboldMarianoResult` do domínio com `float`/`int` nativos.
  - `holm_adjusted`: `multipletests(p, method="holm")[1]` (método **explícito**; o
    default é `'hs'`); `holm_rejected`: `multipletests(p, alpha=alpha,
    method="holm")[0]`; tuplas de `float`/`bool` nativos.
- **Critério de aceite (A3, A6, A11 parte):** suíte verde em `fake` e `statsmodels`,
  zero `SKIPPED`; o p-valor do adapter (scipy) concorda com o do domínio em **todo**
  caso DM (`_assert_p_close`); C3/C4 erguem nas duas pernas; `check_port_coverage.py`
  verde **sem** `InferenceBackend` no baseline (entrada morta reprovaria);
  `test_port_coverage_gate.py` verde com `["Hasher"]`; `lint-imports` verde.
- **Verificação (T3) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_inference_backend_contract.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  grep -q "\[statsmodels" "$f"
  grep -q "\[fake" "$f"
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  test -s scripts/arch_baseline.toml
  test -s tests/architecture/test_port_coverage_gate.py
  if grep -n "InferenceBackend" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; then echo "FAIL: baseline residual"; exit 1; fi
  make check
  ```
- **Commit sugerido:** `feat(evaluation): adapter StatsmodelsHac com checagem de sinal e perna statsmodels do contrato [6.2/task-10]`

---

### Task 11 — Port `McsBackend` + `FakeMcsBackend` + suíte de contrato (perna `fake`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/mcs_backend.py`
  - `tests/fakes/features/evaluation/fake_mcs_backend.py`
  - `tests/contract/features/evaluation/test_mcs_backend_contract.py`
- **Arquivos a modificar (ADR 6.1.0005):**
  - `scripts/arch_baseline.toml` — entrada transitória `McsBackend` (`issue = 114`, "removida na 6.2 Task 12");
  - `tests/architecture/test_port_coverage_gate.py` — `["Hasher", "McsBackend"]`.
- **O que fazer (concept §4; ADR 6.2.0004 itens 3/5):**
  - Port `McsBackend(Protocol)` com a assinatura literal do concept §4
    (`optimal_block_length(*, series) -> float`, `bootstrap_indices(*, n_obs,
    block_size, reps, seed, scheme) -> BootstrapIndices`); docstring: b̂_sb finito
    ≥ 0; `int` no bloco (ADR 6.2.0005); entradas inválidas → `ValueError` pelos
    validadores de domínio (C9); **o backend real pode erguer `ArithmeticError`**
    quando a estimativa é numericamente indefinida para uma série que passa pelo
    validador (decisão de detalhe do §1; ADR 6.2.0004 itens 3/5); consumidor de
    produção = 6.4.
  - `FakeMcsBackend(block_length: float = 1.0)`: `optimal_block_length` chama
    `validate_block_length_request` e devolve a constante; `bootstrap_indices` chama
    `validate_bootstrap_request` e gera com `random.Random(seed)`, com o **mesmo
    leiaute** dos esquemas do `arch` — estacionário: início uniforme e, a cada passo,
    novo início com prob. 1/`block_size`, senão `(anterior + 1) % n_obs`;
    moving-block: blocos de `block_size` índices consecutivos com início uniforme em
    [0, `n_obs − block_size`], concatenados e truncados em `n_obs`;
    `generator = "stdlib random.Random"`. A geração é do fake (o domínio não tem
    RNG); a validação é a do domínio.
  - Suíte parametrizada, ids `["fake"]` (a Task 12 acrescenta `"arch"` sem
    `skipif`): forma (reps × n_obs), faixa [0, n_obs), determinismo (mesma seed →
    igual), seeds 1 e 2 diferem, `scheme`/`block_size`/`seed`/`n_obs` do pedido,
    `generator` não-vazio; moving-block: cada bloco `[j·l, (j+1)·l)` da linha é
    consecutivo e começa em ≤ `n_obs − l`; estacionário: alguma linha contém a
    transição `n_obs − 1 → 0` (n_obs = 5, l = 3, reps = 200); `optimal_block_length`
    finito ≥ 0 numa série AR(1) de 250 pontos gerada com `random.Random(<seed
    declarada>)` (stdlib; sem numpy no teste); C9 (um caso por ramo dos dois
    validadores, inclusive moving-block `block_size ≥ n_obs`, série de 10 pontos,
    `nan`/`inf`, constante) → `ValueError`. Teste só do fake (fora da
    parametrização): `FakeMcsBackend(block_length=2.5).optimal_block_length(...) ==
    2.5` e default 1,0.
  - **Tokens** (`test_mcs_backend_contract.py`): `indices_shape`, `indices_range`, `indices_determinism`, `indices_seeds_differ`, `indices_request_echo`, `indices_generator_filled`, `moving_block_contiguity`, `stationary_wraparound`, `block_length_finite_nonnegative`, `c9_bootstrap_parity`, `c9_block_length_parity`, `fake_constant_block_length`.
- **Critério de aceite:** suíte verde no id `fake`; `check_port_coverage.py`,
  `check_fake_parity.py`, `test_port_coverage_gate.py` e `lint-imports` verdes.
- **Verificação (T3) — Container:**
  ```bash
  uv run pytest tests/contract/features/evaluation/test_mcs_backend_contract.py -v
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  uv run python scripts/check_port_coverage.py --list
  uv run python scripts/check_fake_parity.py
  grep -q 'key = "McsBackend"' scripts/arch_baseline.toml
  make check
  ```
- **Commit sugerido:** `feat(evaluation): port McsBackend de dois métodos com fake e suíte de contrato [6.2/task-11]`

---

### Task 12 — Adapter `ArchMcs` + perna `arch` + integração com `arch.MCS` (reverte o baseline)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/inference/arch_mcs.py`
  - `tests/integration/features/evaluation/test_mcs_vs_arch.py`
- **Arquivos a modificar:**
  - `tests/contract/features/evaluation/test_mcs_backend_contract.py` (factory `"arch"`)
  - `scripts/arch_baseline.toml` — remove `McsBackend`;
  - `tests/architecture/test_port_coverage_gate.py` — volta a `["Hasher"]`.
- **O que fazer (concept §4 Adapters, §8; ADR 6.2.0004 itens 5/6):** classe pública
  `ArchMcs` (docstring: satisfaz `McsBackend`; gerador de registro dos índices
  confirmatórios).
  - `bootstrap_indices`: `validate_bootstrap_request`; `cls =
    StationaryBootstrap | MovingBlockBootstrap`; `bs = cls(block_size,
    np.arange(n_obs), seed=seed)` com seed `int` — **exatamente** como o `arch.MCS`
    monta o seu; linhas = `data[0][0]` de cada réplica de `bs.bootstrap(reps)`
    convertidas para tuplas de `int`; `generator = f"arch {arch.__version__}
    {cls.__name__} / numpy default_rng"`.
  - `optimal_block_length`: `validate_block_length_request`; sob
    `np.errstate(divide="raise", invalid="raise")`,
    `float(optimal_block_length(np.asarray(series, dtype=float))["stationary"].iloc[0])`
    (coluna `"stationary"`, não `b_sb`); `FloatingPointError`, não-finito ou < 0 →
    `ArithmeticError` (decisão de detalhe do §1; registrar `[decision]` em §7
    citando o ADR 6.2.0004).
  - `test_mcs_vs_arch.py` (integração; importa `arch` e `numpy`): **uma** função
    parametrizada `test_mcs_matches_arch` com exatamente **8** ids
    `<scheme>-seed<s>-block<l>` (`scheme ∈ {stationary, moving_block}`,
    `s ∈ {1, 7}`, `l ∈ {3, 10}`); perdas T = 250, k = 4, sem empate (seed
    declarada; colunas com escalas distintas; timestamps ISO sintéticos);
    `ModelConfidenceSet.evaluate` sobre `ArchMcs().bootstrap_indices(...)` (α = 0,10,
    reps = 1000) vs `arch.MCS(losses, size=0.10, reps=1000, block_size=l,
    method="R", bootstrap=scheme, seed=seed).compute()`: ordem de eliminação
    (colunas → nomes) **igual** e p-valores MCS **iguais** (`==`); **não** compara
    `included`. Mais um teste do adapter: série `[1, −1] + [0]*20` →
    `ArithmeticError`.
  - **Tokens** (integração `test_mcs_vs_arch.py`): `mcs_matches_arch`, `arch_block_length_arithmetic_error`;
    os esquemas `stationary`/`moving_block` vivem só nos ids e são provados pela
    contagem de 8 ids `PASSED` (exceção declarada no §1).
- **Critério de aceite (A8, A11):** contrato verde em `fake` e `arch`, zero
  `SKIPPED`; os 8 ids de integração `PASSED`; `check_port_coverage.py` verde
  **sem** `McsBackend` no baseline; `test_port_coverage_gate.py` com `["Hasher"]`.
- **Verificação (T3) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_mcs_backend_contract.py tests/integration/features/evaluation/test_mcs_vs_arch.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  grep -q "\[arch" "$f"
  grep -q "\[fake" "$f"
  n=$(grep -cE "test_mcs_vs_arch.py::test_mcs_matches_arch\[(stationary|moving_block)-seed[0-9]+-block[0-9]+\] PASSED" "$f" || true)
  test "$n" -eq 8
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  test -s scripts/arch_baseline.toml
  test -s tests/architecture/test_port_coverage_gate.py
  if grep -n "McsBackend" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; then echo "FAIL: baseline residual"; exit 1; fi
  make check
  ```
- **Commit sugerido:** `feat(evaluation): adapter ArchMcs como gerador de registro e MCS do domínio conferido contra arch.MCS [6.2/task-12]`

---

### Task 13 — Documentação (roadmap §6.2, doc de domínio, overview §10)

- **Arquivos a modificar:**
  - `docs/roadmap.md`
  - `docs/domain/evaluation/probabilistic-forecast-evaluation.md`
  - `docs/overview.md`
- **Arquivos a criar:** nenhum.
- **Antes de começar (Host):** `git fetch origin && git rebase origin/develop` —
  a 6.3 edita linhas vizinhas nos três arquivos (mapa no §5); conflito resolvido
  mantendo as duas edições, com `[deviation]` em §7 se algo mudar de lugar.
- **O que fazer (concept §1, D9, A13; autoridade em D9):**
  - `roadmap.md` §Stage 6.2: descrição humana e DoD sem o vocabulário órfão
    ("gates A/B/C/F", "top-50") — no lugar, as convenções do doc §9.3 (L_t como
    perda pareada; sem seleção entre candidatos; família de Holm por horizonte;
    1 obs por `target_timestamp`) e a postura do ADR 0.0.0056 (DM/Holm/MCS no
    domínio, statsmodels/arch como oráculos atrás de port, R como fixture);
    `arquivos_a_criar` = a lista real do §1 (sem `dm_wrapper.py` nem
    `mcs_cases.json`; com `tests/fixtures/r_oracle/dm_test_cases.*` e `Dockerfile`);
    `contratos_introduzidos` = `PairedLossSeries`, `BootstrapIndices` (VOs),
    `paired_pinball_losses`, `student_t_cdf`, `DieboldMariano`, `HolmCorrection`,
    `ModelConfidenceSet` (domain-services), `InferenceBackend`, `McsBackend`
    (ports-out); `contratos_consumidos` = `CoverageSeries`, `PinballScore` (6.1) —
    sai `ScopeSpec/dedup (5.1)`; nota do desvio de caminho D7 (testes "vs oráculo"
    do roadmap são analíticos; bibliotecas/R em contrato e integração). §6.4 já
    consome `McsBackend` (commit 7d70047) — só conferir.
  - Doc de domínio:
    - §6.5 — bloco `l = max(h, ⌈max b̂_sb⌉)` (ADR 6.2.0005) e localizadores de
      Politis & White 2004 ("SB em §3.1 p. 55"; b_opt em §3.2 Eq. (6));
    - §10, linha `| 16b |` — ⌈·⌉ na regra;
    - §10.1 (registro B-MCS) — a frase `` `optimal_block_length` → `b_sb` `` vira
      `` `optimal_block_length(...)["stationary"]` ``;
    - §11.3 — (i) `optimal_block_length` devolve as colunas `"stationary"`/
      `"circular"` (o docstring diz `b_sb`/`b_cb`); (ii) o `dm.test` cai no fallback
      também com dv = 0 (condição `dv > 0`), apesar da mensagem "Variance is
      negative"; (iii) empate exato na eliminação do `arch` remove o modelo-linha
      **e** o modelo-coluna do primeiro par empatado;
    - §11.2 — no bloco **"Inferência pareada:"** (a 6.3 edita blocos vizinhos): NIST
      DLMF §8.17 (algoritmo da t) e Bernardi & Catania (2018) como fonte consultada e
      descartada como oráculo de pertença.
  - `overview.md` §10: NIST DLMF §8.17 e Bernardi & Catania (2018) no item do doc
    de domínio de avaliação (§7/§8 e a nota do ADR 0.0.0020 já estão no b1ef16b —
    só conferir).
- **Critério de aceite (A13):** os greps ancorados em texto novo reprovariam no
  `develop` de hoje e passam depois; três são **conferências** que já passam hoje
  (`McsBackend` no §6.4 — commit 7d70047; `0.0.0056` no overview — b1ef16b;
  `PairedLossSeries` no S62 — já no roadmap); `make docs-check` verde.
- **Verificação (T1 + docs):**
  - **Host:**
    ```bash
    S62=$(awk '/^#### Stage 6.2/,/^#### Stage 6.3/' docs/roadmap.md); test -n "$S62"
    if grep -nE "gates? [ABCF]\b|A/B/C/F|top-50|dm_wrapper|mcs_cases|ScopeSpec" <<<"$S62"; then echo "FAIL: roadmap 6.2"; exit 1; fi
    for t in CoverageSeries BootstrapIndices PairedLossSeries McsBackend student_t_cdf "r_oracle/dm_test_cases"; do grep -q -- "$t" <<<"$S62" || { echo "FAIL: roadmap 6.2 sem $t"; exit 1; }; done
    S64=$(awk '/^#### Stage 6.4/,/^#### Stage 6.5/' docs/roadmap.md); grep -q "McsBackend" <<<"$S64"
    D=docs/domain/evaluation/probabilistic-forecast-evaluation.md; test -s "$D"
    S65=$(awk '/^### 6\.5 /,/^### 6\.6 /' "$D"); test -n "$S65"
    grep -q "⌈" <<<"$S65"
    grep -q "§3.1 p. 55" <<<"$S65"
    grep -E '^\| 16b \|' "$D" | grep -q "⌈"
    S101=$(awk '/^### 10\.1 /,/^## 11\./' "$D"); test -n "$S101"
    if grep -q 'optimal_block_length` → `b_sb`' <<<"$S101"; then echo "FAIL: B-MCS ainda cita b_sb"; exit 1; fi
    grep -q 'optimal_block_length.*"stationary"' <<<"$S101"
    S113=$(awk '/^### 11\.3 /,0' "$D"); test -n "$S113"
    grep -q '"circular"' <<<"$S113"
    grep -q "dv = 0" <<<"$S113"
    grep -q "modelo-coluna" <<<"$S113"
    S112=$(awk '/^Inferência pareada:/,/^### 11\.3 /' "$D"); test -n "$S112"
    grep -q "DLMF" <<<"$S112"
    grep -q "Bernardi" <<<"$S112"
    O=$(awk '/^## 10\./,/^## 11\./' docs/overview.md); test -n "$O"
    grep -q "DLMF" <<<"$O"
    grep -q "Bernardi" <<<"$O"
    grep -q "0.0.0056" docs/overview.md
    python scripts/check_docs_pointers.py
    ```
  - **Container:**
    ```bash
    make docs-check
    make check-task SLICE=evaluation
    ```
- **Commit sugerido:** `docs(evaluation): roadmap 6.2, doc de domínio e overview alinhados à Stage 6.2 [6.2/task-13]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 6.2: complete` e ser mergeada em `develop`.

### Verificações automatizadas

**Container** (um único `bash -euo pipefail -c` no wrapper do §1):
```bash
make check                 # ruff + mypy strict + check_layout + lint-imports + fake-parity + port-coverage + docs-check + testes (cov >= 90%)

# A15 — cobertura por arquivo do slice (JSON gerado e lido no mesmo shell): falha se arquivo < 90% ou arquivo novo ausente
cov=$(mktemp --suffix=.json)
uv run pytest --cov=financial_forecasting --cov-report=json:"$cov" -q
test -s "$cov"
uv run python - "$cov" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["files"]
ev = {f.replace(chr(92), "/"): v["summary"]["percent_covered"] for f, v in d.items() if "features/evaluation/" in f.replace(chr(92), "/")}
need = ["paired_loss_series.py", "bootstrap_indices.py", "student_t.py", "paired_pinball_losses.py",
        "inference_input_validation.py", "diebold_mariano.py", "holm_correction.py", "model_confidence_set.py",
        "inference_backend.py", "mcs_backend.py", "statsmodels_hac.py", "arch_mcs.py"]
miss = [n for n in need if not any(f.endswith("/" + n) for f in ev)]
bad = {f: p for f, p in ev.items() if p < 90}
print(len(ev), "arquivos do slice; abaixo de 90%:", bad, "; ausentes:", miss)
sys.exit(1 if bad or miss else 0)
PY

# A11 — duas suítes, três pernas, zero skips
f=$(mktemp)
uv run pytest tests/contract/features/evaluation/test_inference_backend_contract.py tests/contract/features/evaluation/test_mcs_backend_contract.py -v -rs | tee "$f"
test -s "$f"
if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED no contrato"; exit 1; fi
grep -q "\[fake" "$f"
grep -q "\[statsmodels" "$f"
grep -q "\[arch" "$f"

# A4/A5/A8 — integrações (fixtures R, proveniência, arch.MCS), zero skips
g=$(mktemp)
uv run pytest tests/integration/features/evaluation/test_r_oracle_provenance.py tests/integration/features/evaluation/test_dm_r_oracle_fixtures.py tests/integration/features/evaluation/test_mcs_vs_arch.py -v -rs | tee "$g"
test -s "$g"
if grep -q "SKIPPED" "$g"; then echo "FAIL: SKIPPED na integração"; exit 1; fi
n=$(grep -cE "test_mcs_vs_arch.py::test_mcs_matches_arch\[(stationary|moving_block)-seed[0-9]+-block[0-9]+\] PASSED" "$g" || true)
test "$n" -eq 8

# A12 — sem aresta nova de lib
uv run lint-imports

# Matriz — cada token casa >= 1 teste do arquivo (coleta uma vez por arquivo; token casado contra o
# nome da função após o '::' SEM o id '[...]', substring sem distinção de caixa, como o -k).
# A lista é recusada se um token repetir ou estiver contido em outro do mesmo arquivo (prova vácua).
U=tests/unit/features/evaluation; C=tests/contract/features/evaluation; I=tests/integration/features/evaluation
while read -r file toks; do
  test -s "$file"
  for a in $toks; do for b in $toks; do
    [ "$a" = "$b" ] || [[ "$b" != *"$a"* ]] || { echo "FAIL: token '$a' contido em '$b' ($file)"; exit 1; }
  done; done
  test "$(tr ' ' '\n' <<<"$toks" | sort | uniq -d | wc -l)" -eq 0
  ids=$(uv run pytest --co -q "$file" </dev/null | grep '::' | sed 's/^[^:]*:://; s/\[.*//' | sort -u)
  test -n "$ids"
  for t in $toks; do grep -qi -- "$t" <<<"$ids" || { echo "FAIL: sem teste '$t' em $file"; exit 1; }; done
done <<LIST
$U/test_student_t.py t_zero_half t_df1_closed t_df2_closed t_df3_closed t_symmetry t_complement_no_cancel t_monotone t_invalid_input t_not_converge
$U/test_paired_loss_series.py pls_invalid pls_unknown_name pls_same_model pls_degenerate_pair_accepted pls_model_pairs_order pls_differential_sign pls_losses_of_column pls_frozen
$U/test_paired_pinball_losses.py factory_single_seed_identity factory_seed_mean factory_mismatch factory_no_series factory_single_model factory_horizon_propagated
$U/test_dm_vs_r_oracle.py dm_hand_h1 dm_sign_swap dm_h2_rectangular dm_h2_bartlett dm_hln_factor dm_fallback_alternating dm_constant_differential dm_c3_invalid dm_validate_request dm_unknown_name dm_same_model dm_degenerate_comparator_pair dm_result_incoherent
$U/test_inference_input_validation.py p_values_invalid alpha_invalid valid_inputs_accepted
$U/test_holm_vs_statsmodels.py holm_dyadic holm_single_p holm_cap_one holm_tie_order_free holm_input_order holm_boundary_rejects holm_c4_invalid family_k7_all_comparators family_unknown_candidate family_report_incoherent family_single_candidate_signature family_horizon_propagated
$U/test_bootstrap_indices.py bootstrap_request_invalid bootstrap_request_accepts block_length_request_invalid block_length_min_length block_length_constant_series indices_invalid_row indices_valid_reps indices_frozen
$U/test_mcs_vs_arch.py mcs_dominated_first mcs_cumulative_max mcs_boundary_included mcs_exact_tie_one_model mcs_all_included mcs_copies_bootstrap mcs_elimination_names mcs_included_order mcs_c6_invalid mcs_report_incoherent block_length_ceiling block_length_c7_invalid mcs_alpha_signature mcs_horizon_propagated
$C/test_inference_backend_contract.py dm_random_matches_domain dm_fallback_both_legs dm_constant_raises dm_c3_parity holm_c4_parity holm_adjusted_equal holm_rejected_equal
$C/test_mcs_backend_contract.py indices_shape indices_range indices_determinism indices_seeds_differ indices_request_echo indices_generator_filled moving_block_contiguity stationary_wraparound block_length_finite_nonnegative c9_bootstrap_parity c9_block_length_parity fake_constant_block_length
$I/test_r_oracle_provenance.py prov_real_fixture_clean prov_dockerfile_two_lines prov_missing_key prov_generator_missing prov_session_info_missing prov_r_version_mismatch prov_package_version_mismatch prov_hex_mismatch prov_dec_length_mismatch prov_scalar_list_shape_mismatch prov_image_from_mismatch prov_generated_at_not_iso prov_generated_at_invalid_date prov_extra_key_allowed
$I/test_dm_r_oracle_fixtures.py r_fixture_case_matches r_fixture_t_isolated r_fixture_covers_required_scenarios
$I/test_mcs_vs_arch.py mcs_matches_arch arch_block_length_arithmetic_error
LIST
```

**Host** (Git Bash, raiz da worktree, um script `bash -euo pipefail`):
```bash
T=docs/stages/6.2-paired-inference-dm-mcs-holm/technical.md
# A11 — baseline sem resíduo
test -s scripts/arch_baseline.toml
test -s tests/architecture/test_port_coverage_gate.py
if grep -n "InferenceBackend\|McsBackend" scripts/arch_baseline.toml tests/architecture/test_port_coverage_gate.py; then echo "FAIL: baseline residual"; exit 1; fi
# A12/I13 — unit sem biblioteca, sem adapter, sem I/O; contrato sem import direto de biblioteca
test -d tests/unit/features/evaluation
test -d tests/contract/features/evaluation
if grep -rnE "^\s*(from|import)\s+(arch|statsmodels|scipy|numpy|sklearn|scoringrules)\b|adapters\.out|open\(|read_text\(|read_bytes\(|json\.load" tests/unit/features/evaluation/; then echo "FAIL: unit impuro"; exit 1; fi
if grep -rnE "^\s*(from|import)\s+(arch|statsmodels|scipy|numpy)\b" tests/contract/features/evaluation/; then echo "FAIL: contrato importa lib"; exit 1; fi
# A14 — exatamente uma entrada de medição por Task (02, 06, 07) em §7
test -s "$T"
for n in 02 06 07; do test "$(grep -cE "^### [0-9-]+ — \[decision\] Task $n — medição A14" "$T")" -eq 1; done
# A15 — ADRs; §7; issue
test "$(ls docs/adr/6_2_000*.md docs/adr/0_0_0056-*.md | wc -l)" -ge 7
test -z "$(grep -L '^status: accepted' docs/adr/6_2_000*.md docs/adr/0_0_0056-*.md)"
python scripts/check_technical_postexec.py "$T"
python scripts/check_stage_issue.py
```

(A saída dos blocos A15, A11, integrações e do laço de tokens é colada no PR.)

### Verificações funcionais
- [ ] Para uma `PairedLossSeries` sintética k = 7, `HolmCorrection.family` devolve 6
      DMs e o Holm do horizonte; `ModelConfidenceSet.evaluate` sobre índices do
      `ArchMcs` devolve o MCS com a ordem e os p-valores do `arch.MCS` (A7/A8).
- [ ] Cada DM das fixtures R é reproduzido pelo domínio sob tolerância declarada,
      inclusive o fallback e os erros (A4).
- [ ] Sem verificação end-to-end com dado real: a Stage não persiste nem expõe
      métrica (concept D8); o e2e sobre o silver é da 6.4.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com o seu gate (T1/T3) verde.
- [ ] `make check` verde no branch; cobertura por arquivo (A15) colada.
- [ ] Laço de tokens da matriz C*/I* verde, saída colada.
- [ ] `scripts/arch_baseline.toml` e `test_port_coverage_gate.py` sem
      `InferenceBackend`/`McsBackend` (ADR 6.1.0005).
- [ ] §7 com as três medições A14 (Tasks 02, 06, 07 — uma por Task, contagem do §3), a árvore
      transitiva (Task 01) e as decisões de detalhe do §1 efetivamente aplicadas.
- [ ] Rebase em `origin/develop` antes do push (GIT-WORKFLOW Etapa 4); se a 6.3 já
      estiver em `develop`, o teste de proveniência passa também sobre
      `var_test_cases.json` (senão `[finding]` de coordenação).
- [ ] Commit final `stage 6.2: complete` aplicado (pós-auditoria).
- [ ] `roadmap.md`: Stage 6.2 marcada `done`, `updated_at` e `last_reviewed_at` no
      fechamento.
- [ ] ADRs 6.2.0001–0006 e 0.0.0056 em `accepted`.
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

```
Task 01 (deps + contrato)
  ├─► Task 02 (t) ─────────────┐
  ├─► Task 03 (VO + fábrica) ──┴─► Task 04 (DM) ─┬─► Task 05 (Holm) ─┐
  │                                              └─► Task 08 (R)     │
  └─► Task 06 (BootstrapIndices) ─────────────────────► Task 07 (MCS) ◄┘ (validate_alpha)
Tasks 04, 05 ─► Task 09 (port InferenceBackend; baseline +) ─► Task 10 (statsmodels; baseline −)
Tasks 06, 07 ─► Task 11 (port McsBackend; baseline +) ─► Task 12 (arch + arch.MCS; baseline −)
Tasks 01–12 ─► (rebase em origin/develop) ─► Task 13 (docs)
```

- A Task 01 vem primeiro: a biblioteca só entra já cercada, e as Tasks 10/12 seguem
  imediatamente as 09/11 (janela de baseline de um commit — ADR 6.1.0005).
- A Task 04 usa a t da 02 e o VO da 03; a 05 usa o DM da 04; a 07 usa
  `validate_alpha` da 05 e o VO da 06. Nenhum ciclo de import: `diebold_mariano.py`
  não importa `holm_correction.py` nem `inference_input_validation.py`.
- A Task 08 depende da 04 (golden test sobre o primitivo) e da 02 (isolamento da t).
- A Task 06 re-mede o mínimo de `optimal_block_length` com o `arch` da Task 01.
- A Task 13 fecha a documentação com a lista real de arquivos, depois do rebase.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `statsmodels` 0.15 quebrar o `statsforecast` (modeling) ou `formulaic`/`arch` puxarem algo pesado | Medir na Task 01 (`git diff uv.lock` + `make check`); se o `statsforecast` quebrar, `[decision]` em §7 com o erro e HALT à sessão mestra (mudar o pin muda o contrato do concept) |
| `arch` sem wheel para a plataforma do container | Medido na Task 01 (`uv sync`); sem wheel → HALT (dependência do concept) |
| Implementação final da t acima da tolerância declarada (re-medição da Task 02) | Corrigir o ramo da cauda (o §1 mostra a armadilha `1 − I`); só afrouxar com `[decision]` e o número medido, nunca tolerância implícita |
| p-valor MCS do domínio diferir do `arch.MCS` por 1/reps em algum id (T*_R a um ulp de T_R) | Conferir primeiro os índices (`ArchMcs` × índices internos do `arch.MCS`, sondagem fora do repo); se for ruído de soma, trocar a seed dos **dados** do teste (dados sem quase-empate) e registrar `[deviation]` — o critério "idêntico" do A8 não é relaxado |
| `jsonlite` reescrever os números (`digits`) e o round-trip falhar | `json_verbatim = TRUE` com strings `%.17g` já formatadas; o teste de proveniência reprova o que escapar |
| Fixture R não gerar o fallback h = 7 (busca de seed) | O caso analítico d = ±1 com h = 2 cobre o fallback; a busca de h = 7 tem teto de seeds e `stopifnot(found)` |
| A 6.3 mergear antes com fixture fora do formato do ADR 6.2.0006 / das regras do Step | O teste genérico reprova no rebase da 6.2; `[finding]` de coordenação à sessão mestra (o formato tem dono único aqui) |
| **Conflitos de merge com a 6.3 (mapa):** `overview.md` §10 linha 135 (item "Avaliação probabilística" — **mesma linha** que a 6.3 edita: conflito trivial certo); doc de domínio §11.3 linhas 1960–1962 (bullets vizinhos) e §11.2 (blocos vizinhos); `roadmap.md` tabela de Stages linhas 102/103 (linhas adjacentes) e seções §6.2/§6.3 | `git fetch origin && git rebase origin/develop` **antes da Task 13** e de novo no PR (GIT-WORKFLOW Etapa 4); resolver mantendo as duas edições; a 6.2 só acrescenta no bloco "Inferência pareada" do §11.2 |
| `check_port_coverage.py` não reconhecer um adapter | Citar o nome do port no docstring do módulo/classe, como todos os adapters do repo |
| `check_fake_parity.py` acusar bloco idêntico fake × adapter | O fake de inferência só delega ao domínio; o de MCS gera com `random` e não compartilha código com o `arch`; validação só nos validadores de domínio |
| mypy strict sobre tipos do `arch`/pandas no adapter | Converter para `float`/`int` nativos na fronteira; `cast` comentado só onde o stub é impreciso |
| Cobertura < 90 % nos ramos de `__post_init__` | Um teste por ramo (C1, C3–C9); `# pragma: no cover` só comentado e para ramo comprovadamente inalcançável |
| Verde falso por shell (`!` sob `set -e`, arquivo lido em outro `docker run`) | Convenção do §1: um `bash -euo pipefail -c` por bloco, negação por `if …; then exit 1; fi`, `test -s` antes de ler |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo, contratos (§4), invariantes (§5), erros
  (§6), decisões D1–D9 (§7), integrações (§8), critérios (§11).
- ADRs desta Stage:
  [`0.0.0056`](../../adr/0_0_0056-own-statistics-in-domain-r-oracle-as-fixtures.md),
  [`6.2.0001`](../../adr/6_2_0001-paired-loss-series-single-aligned-matrix-vo.md),
  [`6.2.0002`](../../adr/6_2_0002-student-t-p-value-stdlib-in-domain.md),
  [`6.2.0003`](../../adr/6_2_0003-dm-holm-of-record-statsmodels-oracle-no-dm-wrapper.md),
  [`6.2.0004`](../../adr/6_2_0004-mcs-procedure-in-domain-over-backend-bootstrap-indices.md),
  [`6.2.0005`](../../adr/6_2_0005-mcs-block-length-ceiling-integer.md),
  [`6.2.0006`](../../adr/6_2_0006-r-oracle-fixtures-provenance-and-scope.md);
  relacionados: [`0.0.0010`](../../adr/0_0_0010-paired-inference-dm-holm-mcs.md),
  [`0.0.0020`](../../adr/0_0_0020-statistics-in-domain-over-value-objects.md),
  [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md),
  [`0.0.0055`](../../adr/0_0_0055-tiered-quality-gates.md),
  [`6.1.0001`](../../adr/6_1_0001-scoring-libraries-as-oracle-backend-behind-port.md),
  [`6.1.0005`](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md).
- Doc de domínio: [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md).
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §7; [`../../PIPELINE.md`](../../PIPELINE.md) §4.3;
  [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) §Gates em camadas;
  [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §6.
- Skills: `task-ordering-hex`, `hex-arch-python`, `ddd-tactical-patterns`,
  `pytest-with-fakes`, `import-linter-rules`.
- Stage de referência: [`../6.1-scoring-and-calibration-metrics/technical.md`](../6.1-scoring-and-calibration-metrics/technical.md) (+ §7).
- Externas: NIST DLMF §8.17; R `src/nmath/pt.c`; forecast 8.23.0 `R/DM2.R`; arch 8.0.0
  `arch/bootstrap/{base,multiple_comparison}.py`; statsmodels 0.15
  `get_robustcov_results`/`multipletests`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a Fase 4. Apenas esta seção é editável após
> `status: done`. Cada entrada carrega data + autor.

### 2026-09-28 — [decision] Task 01: árvore transitiva de `arch`/`statsmodels` medida no `uv.lock` — Claude (Opus 5.5)
**Contexto:** a Task 01 pede medir a árvore transitiva com `git diff uv.lock` e conferir
que o `statsforecast` segue resolvendo com `statsmodels` 0.15.
**Razão:** `uv lock` resolveu 181 pacotes; o diff traz exatamente **4 pacotes novos** —
`arch` 8.0.0 (deps: numpy, packaging, pandas, scipy, statsmodels — todas já no lock),
`formulaic` 1.2.2 (exigido pelo `statsmodels` 0.15; deps novas só as duas abaixo, o resto
— narwhals, numpy, pandas, scipy, typing-extensions — já no lock), `interface-meta` 2.0.1
e `wrapt` 2.5.0 — e **1 atualização**, `statsmodels` 0.14.6 → 0.15.0 (transitiva via
`statsforecast`, que exige `>=0.14.5`: a 0.15 satisfaz). Nenhum pacote removido. `uv sync
--inexact --extra dev` só no volume `ff-step62-venv`. O `make check` (T3) passou com a
suíte inteira — inclusive a de `modeling`/`statsforecast` sob `statsmodels` 0.15 (2697
passed, cobertura 98,48 %); a primeira rodada caiu na **coleta** com `OSError: [Errno 12]
Cannot allocate memory` (pressão de memória do host com outras sessões em paralelo, não
código) e a segunda, sozinha, ficou verde.

### 2026-09-28 — [decision] Task 02 — medição A14 (t de Student) — Claude (Opus 5.5)
**Contexto:** re-medição A14.1 com a função final `student_t_cdf` (sondagem fora do repo,
`scipy.stats.t.cdf` 1.18.0 do venv da 6.2), na grade do §1: df ∈ {1, 2, 3, 4, 5, 7, 10,
20, 30, 59, 100, 249, 500, 999, 1500, 2000, 2499, 2500} × 1601 valores de x (0 e
±10⁻¹²…±10³, log). A **primeira** versão (o protótipo do §1 transcrito: log B(a, b) =
`lgamma(a) + lgamma(b) − lgamma(a + b)` e log(1 − z) por `log`) reproduziu o §1 — abs.
máx. **3,6e−13** (df = 2000, x = −1,67), rel. máx. na cauda **7,6e−12** —, e 3,6e−13
passa de 1/10 da tolerância declarada do p-valor (`abs ≤ 1e-12`; o gatilho do §1).
Causa medida: a subtração `lgamma(df/2) − lgamma(df/2 + ½)` (dois números ~ 5,9e3 com
ulp ~ 9e−13) no prefator, amplificada no ramo z abaixo do limiar, onde P = 1 − I com
I ≈ 0,9.
**Razão:** em vez de afrouxar a tolerância, o prefator passou a seguir o próprio oráculo:
log B(a, b) pelo ramo "p < 10 ≤ q" do R `src/nmath/lbeta.c` (correção de Stirling,
8 termos, no argumento grande) e log(z)/log(1 − z) por `log1p` do lado da fração ≤ ½.
Algoritmo, ramos e contrato inalterados (ADR 6.2.0002 itens 2–3: "prefator com
`math.lgamma`" continua — o `lgamma(p)` do argumento pequeno). Medição da função final:

| df | abs. máx. | rel. máx. cauda (x < 0, F > 1e−290) |
|---|---|---|
| 1 | 2,35e−9 (x ≈ −7e−9: o scipy devolve 0,5; a função = forma fechada ½ + arctan(x)/π) | 4,7e−9 (idem) |
| 2 – 10 | ≤ 6,1e−16 | ≤ 1,1e−14 |
| 20 – 249 | ≤ 7,1e−16 | ≤ 9,9e−14 |
| 500 – 1500 | ≤ 3,3e−15 | ≤ 1,7e−13 |
| 2000 / 2499 / 2500 | 2,8e−15 / 2,0e−15 / 5,9e−15 | 1,8e−13 / 1,6e−13 / 2,5e−13 |

Global df ≥ 2: abs. **5,9e−15** (1/170 de 1e−12) e rel. na cauda **2,5e−13** (1/400 de
1e−10) — abaixo de 1/10 das duas tolerâncias. Caudas extremas: df = 999, x = −10 →
8,354109e−23 (rel 7,2e−15); df = 2499, x = −40 → 3,748606e−271 (rel 1,5e−13). Máximo de
iterações do Lentz na grade log: 56 — **corrigido no Checkpoint C do bloco 1**: a grade log
não passa pelo pior ponto, x logo abaixo do limiar da simetria 8.17.4 (z = 3/(df + 5), onde
a fração contínua converge mais devagar); a revisão achou 72 (df = 999, x ≈ −1,73) e a
busca adensada em torno do limiar (df ≤ 2500, passos relativos de 2,5e−3 e 2e−5 em x) dá
**86** (df = 1012, x ≈ −1,81) — o teto `_MAX_ITERATIONS = 1000` fica ~12× acima. Domínio
validado contra `mpmath` (60 dígitos, x ∈ [−20, 0) passo 0,05): df ≤ 1e4 → abs ≤ 1,5e−14,
rel ≤ 6,4e−13; df 1e5 → rel 6,1e−12; df 1e6 → rel 5,7e−11; df 1e7 → rel 5,3e−10 (abs
1,1e−11) — o docstring declara df ≤ ~1e4. Custo ~7,5 µs por chamada. Detalhe ancorado no `pt.c` também aplicado: o ramo
assintótico `nx > 1e100` (A&S 26.5.4 em log) cobre |x| com x² estourando float64 — é o que
cobre df = 1 e df = 2 em x = −10¹⁵⁰ no unit.

### 2026-09-28 — [decision] Task 03: C2 nos acessores do VO e ordem de validação da fábrica — Claude (Opus 5.5)
**Contexto:** decisão de detalhe planejada no §1 ("`differential`/`losses_of` com nome
desconhecido ou `first == second` → `ValueError`") e um ponto que a Task não fixa: em que
ordem a fábrica confere modelo sem séries × eixos divergentes.
**Razão:** aplicada como planejada — `losses_of` e `differential` erguem `ValueError`
nomeando o modelo desconhecido (e a lista de conhecidos) e `differential(a, a)` ergue
antes de ler colunas (tokens `pls_unknown_name`, `pls_same_model`). Na fábrica, primeiro
< 2 modelos, depois **todo** modelo sem séries, e só então os eixos contra a primeira
série de todas (horizonte → timestamps → grade, na ordem da Task; realizados desde o
fix do Checkpoint C, entrada abaixo), com a mensagem `model '<m>', seed index <i>: …` (a
`CoverageSeries` não carrega id de seed — é o índice na sequência); a referência é a seed 0 do primeiro modelo do mapping, por
isso um eixo divergente entre modelos é atribuído ao modelo de fora. Reversível, sem efeito
no contrato (o concept §4 só exige erguer).

### 2026-09-28 — [decision] Task 03: fábrica exige o mesmo `realized` em todas as séries (regra aditiva de C1) — Claude (Opus 5.5)
**Contexto:** o Checkpoint C do bloco 1 achou que `paired_pinball_losses` aceitava séries
com o mesmo horizonte, timestamps e grade mas **realizados diferentes** (entre seeds ou
entre modelos): o diferencial d_t passava a medir a diferença de alvo (−0,24 no caso da
revisão), não a de modelo. O concept C1 lista horizonte, timestamps e grade, não o y_t.
**Razão:** decisão da sessão mestra — o pareamento de DM/Holm/MCS pressupõe o **mesmo
y_t** em todas as colunas (doc §6.7: amostra pareada; mesma lógica da grade comum da
6.1). `series.realized != reference.realized` → `ValueError` nomeando modelo e índice da
seed, checado depois da grade; casos `realized-between-seeds` e `realized-between-models`
em `test_factory_mismatch_raises`. Regra **aditiva** (só recusa entrada que antes passava
em silêncio); não muda assinatura, port nem formato persistido.

### 2026-09-28 — [finding] Task 03: `CoverageSeries` adota o helper `_timestamps` depois do merge de 6.2 e 6.3 — Claude (Opus 5.5)
**Contexto:** o Checkpoint C do bloco 1 apontou que `PairedLossSeries._check_timestamps`
era cópia byte a byte da regra da `CoverageSeries` (dono duplicado de uma regra de
domínio). O fix `[6.2/task-03-fix]` criou `domain/value_objects/_timestamps.py`
(`check_strictly_increasing`, privado do slice) e a `PairedLossSeries` passou a usá-lo;
a `CoverageSeries` **não** foi tocada, porque a Stage 6.3 (em paralelo) edita
`coverage_series.py` e a troca geraria conflito de merge. Pelo mesmo motivo a docstring
de `_finite_number.py` (que a 6.3 também editou) não ganhou a contagem de consumidores da
6.2 (`PairedLossSeries`).
**Razão:** escalado para a próxima Stage que tocar a série depois de 6.2 e 6.3 estarem em
`develop` — **candidata: 6.4** —: `CoverageSeries._check_timestamps` delega a
`check_strictly_increasing` (mesma mensagem, testes existentes seguem valendo) e a
docstring de `_finite_number.py` passa a listar a `PairedLossSeries` entre os consumidores.
**Ampliado no Checkpoint C do bloco 2:** unificar também a regra de horizonte (int
não-bool ≥ 1) de `value_objects/_paired_inputs.py` (6.2) com o `value_objects/_horizon.py`
que a 6.3 cria em paralelo e com o `_check_horizon` da `CoverageSeries` — três escritas da
mesma regra depois do merge das duas Stages (candidata: 6.4). O nome `_paired_inputs.py`
foi escolhido para não colidir com o `_horizon.py` da 6.3.

### 2026-09-28 — [decision] Task 04: validador do DM no módulo do enum; `mean_differential` finito no I5 — Claude (Opus 5.5)
**Contexto:** decisão de detalhe planejada no §1 (onde mora o validador do DM) e dois
pontos que a Task não fixa: o `__post_init__` do concept (I5) não lista `mean_differential`,
e `compare` precisa escolher a ordem entre "candidato = comparador" e "nome desconhecido".
**Razão:** (1) aplicada como planejada — `validate_dm_request` mora em
`diebold_mariano.py`, ao lado de `DmVarianceEstimator`, e confere nesta ordem: tamanhos,
T ≥ 2, perdas (finitas, ≥ 0, sem `bool`), `horizon` (int não-bool ≥ 1, depois < T),
estimador (membro do enum; a string crua `"rectangular"`, igual ao membro por `StrEnum`,
é recusada por `isinstance`). (2) `DieboldMarianoResult` também recusa `mean_differential`
não-finito — mesma postura de finitude de `statistic`/`long_run_variance`; reversível.
(3) `compare` confere candidato = comparador antes de ler colunas; nome desconhecido sai
do `PairedLossSeries.losses_of` (mensagem única do VO). O fator HLN é a função privada
`_hln_factor`, testada isolada (T = 10, h = 7 → √0,12) como pede a Task.

### 2026-09-28 — [decision] Task 05: decisão de Holm só por `holm_reject`; ordem do I7 no relatório — Claude (Opus 5.5)
**Contexto:** a Task fixa `holm_reject` (p̃ ≤ α) e o `__post_init__` de
`DmHolmFamilyReport` ("rejected ⇔ adjusted ≤ alpha"), mas não diz se `family` e o
`__post_init__` reescrevem a comparação. Uma sondagem de mutantes da própria execução
mostrou que a cópia `value <= alpha` em `family` trocada por `<` sobrevivia à suíte: na
família não há p-valor de DM exatamente na fronteira.
**Razão:** regra com dono único — `family` e o `__post_init__` tiram a decisão de
`holm_reject(p_values, alpha=...)`. **Corrigido no Checkpoint C do bloco 2:** o texto
original dizia que o teste `holm_boundary_rejects` protegia as duas — não protegia (ele
chama `holm_reject` direto, e o fixture k = 7 da família dava `rejected` todo `False`, então
o mutante `rejected=(False,)*m` sobrevivia). O commit `[6.2/task-05-extra]` acrescenta dois
casos **da família**: um candidato dominante contra "bad*" e indistinguível de "twin*"
(`rejected` misto — True/False — em cada α ∈ {0,01; 0,025; 0,05; 0,10; 0,20}) e a fronteira
com α igual ao menor p̃ da própria família (rejeita esse, não o seguinte). p̃ exatamente
igual a um α do conjunto registrado não é construível com p-valores de DM (seriam
p = α/m exatos), por isso a fronteira usa o p̃ observado. O `__post_init__` confere nesta ordem: α (validador único), m ≥ 1,
comparadores únicos, candidato fora deles, mesma amostra (horizonte/T) e estimador de cada
DM, ajustado `==` `holm_adjust` (igualdade exata: mesma operação) e decisão. `family`
confere o candidato (C2) antes de α. `validate_p_values`/`validate_alpha` moram em
`inference_input_validation.py` (decisão de detalhe do §1 aplicada). Na mesma sondagem, os
mutantes do DM "fallback em < 0" e "HLN com o h pedido após o fallback" sobreviviam — fechados
pelo caso à mão do commit `[6.2/task-04-extra]`.

### 2026-09-28 — [decision] Tasks 03/04: regras de horizonte, T, perda e d_t num dono único (`_paired_inputs`) — Claude (Opus 5.5)
**Contexto:** o Checkpoint C do bloco 2 apontou as mesmas regras escritas mais de uma vez
na branch: "horizon int ≥ 1 não-bool" (VO, `validate_dm_request`, `DieboldMarianoResult`),
"perda finita ≥ 0" (VO, validador do DM), "T ≥ 2"/"T > h" com `_MIN_POINTS` duplicado, e
d_t = L_a − L_b escrito no VO e no primitivo.
**Razão:** criado `domain/value_objects/_paired_inputs.py` (privado do slice, direção
serviço → VO) com `check_horizon`, `check_points` (T ≥ 2 e T > h), `check_loss` e
`differential`; consumidores: `PairedLossSeries` (`_check_*` e `differential`),
`validate_dm_request`, `DieboldMarianoResult.__post_init__` e o primitivo
`diebold_mariano` (d_t). Efeitos: (1) a ordem do validador do DM passa a ser tamanhos →
horizonte → T (≥ 2, > h) → perdas → estimador (substitui a ordem da entrada da Task 04;
cada caso de C3 tem um só defeito, então nenhum teste muda de ramo); (2) as mensagens
viram as do dono (`paired losses need T >= 2 points`, `T must be greater than the horizon
(T > h)`, `<onde>: loss must be a finite number >= 0`); (3) o `DieboldMarianoResult`
passa a recusar também `n_points ≤ horizon` (sugestão opcional da revisão; caso
`n-points-not-above-horizon`). Unificação com o `_horizon.py` da 6.3: `[finding]` da
Task 03 acima, ampliado.

### 2026-09-28 — [decision] Task 04: nota do fallback com Bartlett e premissa da tolerância contra o R — Claude (Opus 5.5)
**Contexto:** a revisão numérica do Checkpoint C do bloco 2 (146 casos contra o
`forecast::dm.test` real, zero falhas) registrou dois fatos que o código não dizia.
**Razão:** (1) com o estimador de Bartlett a variância de longo prazo é positiva
semidefinida — só zera com d constante, que ergue do mesmo jeito depois do fallback —, então
o ramo de fallback é observacionalmente equivalente sob Bartlett; comentário de uma linha no
`diebold_mariano.py` (o ramo segue único, como no `dm.test`). (2) A tolerância declarada
contra o R (estatística `rel_tol=1e-11`, Task 08) supõe var̂ ≫ ulp(d̄)²: com diferencial
quase constante (amplitude no ruído de float) a estatística diverge entre implementações
por arredondamento da soma, enquanto o p-valor sai idêntico (satura em 0/1). A Task 08 não
gera fixture nesse regime; se um dia gerar, a comparação é só do p-valor.

### 2026-09-28 — [decision] Task 06 — medição A14 (tamanho mínimo de optimal_block_length) — Claude (Opus 5.5)
**Contexto:** re-medição A14.3 com o `arch` 8.0.0 instalado pela Task 01 (numpy 2.5.0),
sondagem fora do repo com avisos numéricos capturados (`np.errstate(all="warn")` +
`warnings.catch_warnings`), `arch.bootstrap.optimal_block_length(x)["stationary"]`.
**Razão:** confirma o §1 item 4 e fixa `MIN_BLOCK_LENGTH_OBS = 11`:

| n | séries normais com aviso ou erro (de 200) | exemplo de saída |
|---|---|---|
| 1 | 200 | `nan` |
| 2 – 7 | 200 | `ValueError` do `arch` |
| 8 – 10 | 200 | número espúrio (3,0; 3,0; 4,0) com divisão por zero |
| 11 – 15 | **0** | — |

Robustez n = 11..60 × 50 séries por família (séries constantes puladas — o validador as
barra): normal 0/2500, AR(1) φ = 0,9 0/2500, t₂ 0/2500, binária {0, 1} 0/2500, inteiros
−2..2 **5/2500** com aviso (séries inteiras com cauda demeaned nula — a guarda
`ArithmeticError` do adapter, decisão de detalhe do §1 para a Task 12); nenhuma saída
não-finita ou negativa. A série de 22 pontos `[1, −1, 0, …, 0]` do §1 reproduz: 12 avisos e
8,0. Constante: 0,0 → `nan` (14 avisos); 0,3 → 7,81 sem aviso (o ADR 6.2.0004 cita 10,51
para outro tamanho) — o validador de série não constante é necessário para a paridade.

### 2026-09-28 — [decision] Task 06: `seed ≥ 0` no `validate_bootstrap_request` — Claude (Opus 5.5)
**Contexto:** o concept §4 e a Task pedem `seed` int não-bool, sem faixa. A sondagem da
medição acima mostrou que `StationaryBootstrap(3, np.arange(10), seed=-1)` ergue
`ValueError: expected non-negative integer` (o `numpy.random.default_rng` do `arch`),
enquanto o fake (`random.Random(seed)`) aceitaria −1: sem faixa, C9 (paridade de erro no
port) quebraria na Task 12.
**Razão:** o validador único exige `seed ≥ 0` (caso `seed-negative` em
`bootstrap_request_invalid` e `request-invalid` na construção do VO). Regra aditiva — só
recusa entrada que o gerador de registro já recusa —; reversível; não muda assinatura
nem formato.

<!-- END: post-execution -->
