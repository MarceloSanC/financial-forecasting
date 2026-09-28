---
title: Technical — Stage 6.3 — Backtests de calibração condicional e risco (Christoffersen, Kupiec POF, banda de Wilson, VaR descritivo)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), TDD inside-out no domínio do BC evaluation — predicados FA7, kernels χ²/Kupiec/Wilson, HitSequence, ChristoffersenTest (trio puro, 3 estados, Monte Carlo), VaR descritivo, oráculo rugarch congelado e redação de roadmap/doc de domínio
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, calibration-risk-backtests, evaluation, hit-sequence, christoffersen, kupiec, pof, wilson, chi-square, monte-carlo, dufour, var, rugarch, r-oracle, fixtures]
status: done
created_at: 2026-09-28
updated_at: 2026-09-28
stage_id: 6.3-calibration-risk-backtests
stage_title: Backtests de calibração condicional e risco
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [6.1-scoring-and-calibration-metrics]
concept_ref: ./concept.md
issue_id: 113
branch: feat/113-6-3-calibration-risk-backtests
tasks_count: 12
---

# Technical — Stage 6.3 — Backtests de calibração condicional e risco

> **Como usar (para code assistant):** ler §1, executar Tasks em ordem (§2),
> 1 Task = 1 commit, não avançar sem verificação verde; ao fim validar §3 e
> registrar §7. Commits seguem [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(evaluation): <descrição> [6.3/task-NN]`, `Refs #113`, subject
> ≤ 100 caracteres (hook `commit-msg`).
>
> Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
> resolver pelo §2 de [`PROMPT-step-single-session.md`](../../PROMPT-step-single-session.md)
> (docs → ADR; E/C → `evidence-resolution` + ADR 6.3.0007+; P → sobe à sessão
> mestra) e registrar em §7. Nunca propagar silenciosamente.

## 1. Contexto e estratégia de execução

### Resumo

Segunda fatia de domínio do BC `evaluation`, **só domínio** (nenhum port,
adapter, use case ou dependência nova): os predicados FA7 extraídos do
`CoverageMetrics` da 6.1 para `coverage_series.py`, o rótulo `MPIW_LABEL` no
`PairCoverage`, os kernels stdlib `chi_square_sf` (+ piso numérico I13),
`kupiec_pof` e `WilsonBand`, o VO `HitSequence` (com a partição DGT e a
contagem única de transições) e o construtor `HitSequences`, o serviço único
de LR `ChristoffersenTest` (trio puro + leitura Kupiec, LR_uc de 3 estados,
p-valor Monte Carlo com desempate de Dufour), o `VarDescriptive`, a unidade de
fixture R `var_test_cases` (gerada offline na imagem `ff-r-oracle:4.4.1`)
lida por dois testes de integração, e a redação do roadmap (6.3 e 6.5), do doc
de domínio e do overview.

Todas as decisões vêm do concept **por referência** — nenhuma é re-derivada:
D1 (um primitivo + um serviço de LR —
[ADR 6.3.0001](../../adr/6_3_0001-violation-sequence-and-single-lr-service.md)),
D2 (pedido de mudança do roadmap), D3 (oráculo R congelado, sem port —
[ADR 6.3.0002](../../adr/6_3_0002-rugarch-oracle-frozen-as-test-fixtures.md)),
D4 (dois *feeds* —
[ADR 6.3.0003](../../adr/6_3_0003-pure-convention-oracle-comparison-by-two-feeds.md)),
D5 (lacunas quebram transições —
[ADR 6.3.0004](../../adr/6_3_0004-mask-gaps-break-transitions.md)), D6
(contagens reais —
[ADR 6.3.0005](../../adr/6_3_0005-count-kernels-accept-mean-counts.md)), D7
(MC de Dufour —
[ADR 6.3.0006](../../adr/6_3_0006-monte-carlo-p-value-dufour-tie-breaking.md)),
D8 (canal de emissão = VOs de relatório), D9 (coordenação com a 6.2), D10
(`MPIW_LABEL`). Fórmulas: doc de domínio
[`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md)
§4.4, §4.5, §5.3, §6.9, §7.1–§7.7, §10, §11.3. Formato da fixture R: ADR
6.2.0006 (PR da 6.2; citado por id) com as regras do Step fixadas pela sessão
mestra (§Pré-condições).

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`), só dentro de
`evaluation/domain`: primeiro os retoques nos arquivos da 6.1 (predicados FA7
com dono único; `MPIW_LABEL`) → kernels folha sem dependência interna
(`chi_square_sf` + piso, `kupiec_pof`; `WilsonBand`) → VO `HitSequence` →
construtor `HitSequences` (consome predicados FA7 + `DegeneracyGate`) →
`ChristoffersenTest` (consome `kupiec_pof`, `chi_square_sf`, a contagem de
transições do VO) → sensibilidades (3 estados, MC) → `VarDescriptive`
(consome `HitSequences` + `ChristoffersenTest`) → fixture R (dado de teste,
independente do código) → testes de integração contra o R → docs. Cada Task
traz a fixture analítica do próprio kernel no mesmo commit; cada commit deixa
o build verde.

**Nada de port/adapter/fake nesta Stage** (concept D3; ADR 0.0.0056 opção A):
não há biblioteca Python a embrulhar. **Conferido nesta Fase 3B contra o
`arch`** (concept D1, §13): o `arch` não está no venv `ff-step6-venv` (a 6.2
ainda não o instalou); lido o sdist `arch-8.0.0.tar.gz` do PyPI (a versão que
a 6.2 pina, `arch>=8,<9`): `grep -rniE "kupiec|christoffersen|backtest"` em
`arch/` → **zero** ocorrências; o único "Value-at-Risk" do pacote está no
notebook de exemplo `examples/univariate_volatility_forecasting.ipynb`
("Value-at-Risk Forecasting" — VaR **previsto** por modelos GARCH do próprio
`arch`); a API pública (`arch.bootstrap`, `arch.univariate`,
`arch.unitroot`, `arch.covariance`, `arch.utility`) não tem teste de
cobertura/independência de uma grade de quantis externa. O D1 se confirma:
nenhum wrapper possível; oráculo = `rugarch` congelado.

**Exceções de ordem/contagem declaradas (PIPELINE §4.3; skill `task-ordering-hex`):**

- **12 Tasks** — o teto da faixa saudável (CONVENTIONS §6); estimativa do
  concept §12 era ~10. +1 porque o retoque da 6.1 virou duas Tasks (o
  refactor dos predicados FA7 não muda comportamento; o `MPIW_LABEL` muda um
  VO público — tipos de commit diferentes) e +1 porque χ²/Kupiec e Wilson são
  Tasks separadas (kernels independentes, testes de fronteira diferentes).
- **Nenhuma Task toca gate de arquitetura nem inventário**: nenhum port novo
  (`tests/architecture/test_port_coverage_gate.py` segue `["Hasher"]`),
  nenhum contrato (`.importlinter` intocado — D9, I11), nenhuma dependência
  (`pyproject.toml`/`uv.lock` intocados), nenhum adapter (fake-parity e
  port-coverage inalterados). Os módulos novos caem em pacotes já
  matriculados na 6.1 em `domain-purity`, `evaluation-no-scoring-lib-leak`,
  `store-no-storage-leak`, `hexagonal-layers`, `inward-only` e
  `bc-independence` (casos reais de violação já existem por contrato para
  `evaluation.domain` em `tests/architecture/test_import_contracts.py`);
  nenhum módulo novo importa `QuantileForecast` (lêem via `CoverageSeries`),
  logo nenhuma aresta nova no `bc-independence`.
- **Coordenação com a 6.2 (D9):** não tocar `pyproject.toml`, `uv.lock`,
  `.importlinter`, `docs/LAYOUT.md` (a 6.2 edita o §2 para `tests/fixtures/`);
  não criar `student_t.py`; o `tests/fixtures/r_oracle/Dockerfile` é criado
  também aqui com conteúdo **byte-idêntico** ao do ADR 6.2.0006 (duas linhas
  — o add/add idêntico mescla sem conflito); **não** duplicar o teste de
  proveniência de fixtures R da 6.2
  (`tests/integration/features/evaluation/test_r_oracle_provenance.py`, que
  varre todo `r_oracle/*.json`): o JSON desta Stage só precisa satisfazê-lo.
  Nada de `conftest.py` novo em `tests/integration/features/evaluation/`
  (colisão provável com a 6.2): o carregador da fixture é um módulo privado
  com o nome da unidade (Task 11). Mapa de conflitos de rebase em §5.

**Decisões de detalhe planejadas (abaixo do limiar de concept — não mudam
contrato, fronteira nem critério; viram entrada `[decision]` em §7 ao
executar):**

- **Piso numérico I13 com dono único em `chi_square.py`** (Task 03):
  `floor_lr_statistic(value) -> float` (`[−1e-9, 0)` → `0.0`; abaixo ergue
  `ValueError`; não-finito ergue) + constante `LR_NEGATIVE_FLOOR = -1e-9`.
  Mora no módulo-folha porque é a razão de existir do piso (`erfc(√(x/2))`
  com x < 0) e porque todos os consumidores (`chi_square_sf`, `kupiec_pof`,
  LR_ind, 3 estados) já dependem dele — uma escrita da regra, nenhuma cópia.
- **`xlogy(x, y)` público em `kupiec_pof.py`** (Task 03): a convenção
  `0·log 0 = 0` escrita **uma** vez (x = 0 → 0.0; senão `x * math.log(y)`),
  consumida por `kupiec_pof`, LR_ind e LR_uc de 3 estados (Tasks 07/08).
- **Contagem de transições com dono único** (Tasks 05/07, Checkpoint B T4):
  função de módulo `count_transitions(violations) -> tuple[int, int, int,
  int]` em `value_objects/hit_sequence.py` (pares consecutivos **ambos**
  observados — ADR 6.3.0004 item 2); `HitSequence.transition_counts` delega a
  ela e `christoffersen_statistics` a consome (direção serviço → VO). Nenhuma
  segunda escrita da regra das lacunas.
- **`HitSequence` valida a tolerância com o predicado único do slice**
  (Task 05): `is_finite_number(tolerance) and tolerance >= 0.0` — o VO não
  pode importar o `_validate_tolerance` privado do `DegeneracyGate` (direção
  interna serviço → VO); a regra "finito" segue com dono único
  (`_finite_number.py`).
- **Sub-série DGT só existe com `horizon ≥ 2`** (Task 05, Checkpoint B T17):
  além do C1 (um dos dois preenchido; `dgt_offset ≥ dgt_step`), o VO exige
  `dgt_step == horizon` (a I8 fixa isso), `dgt_step ≥ 2` (a I8 manda
  `horizon = 1` devolver `(self,)`, logo não há sub-série de passo 1) e
  `dgt_offset ≥ 0`. O MC checa "sub-série DGT" **antes** de "`horizon > 1`",
  de modo que os dois ramos do C5 têm mensagem própria e são alcançáveis.
- **`christoffersen_statistics` valida os elementos** (Task 07): `bool` ou
  `None` (`type(v) is bool`), a mesma regra do VO — o primitivo também é
  chamado direto pelo MC e pelos testes de oráculo, fora de uma
  `HitSequence`.
- **Predicados FA7 sem validação própria** (Task 01): recebem valores já
  validados pela `CoverageSeries` (C2 da 6.1); `is_at_or_below` é
  `realized <= quantile` e `is_inside_closed` é `lower <= realized <= upper`
  — validar de novo por ponto só custaria tempo nos laços.
- **Carregador da fixture R como módulo privado dos testes de integração**
  (Task 11): `tests/integration/features/evaluation/_var_test_cases.py`
  (sem `test_` no nome; não é `conftest.py`), importado **absolutamente**
  (`from tests.integration.features.evaluation._var_test_cases import …`,
  padrão de `tests/contract/**` com `tests.fakes…`) pelos dois testes de
  oráculo — uma leitura do JSON, nenhuma cópia. O mypy do `make check` não
  cobre `tests/`; o carregador é tipado mesmo assim (dataclasses frozen).

**Custo do Monte Carlo — medido nesta Fase 3B, não presumido (concept §3,
ADR 6.3.0006 "Negative"):** protótipo stdlib do laço do ADR 6.3.0006
(sorteio de T `random()` + U_i + contagem de transições e aplicabilidade)
no container de dev (`python 3.12.13`): T = 1 000, p = 0.05, N = 9 999,
`min_violations = 2` → **1,86 s**, 9 999 tentativas; p = 0.02 → 1,81 s;
T = 250, p = 0.01, N = 9 999 → 0,49 s com **13 963** tentativas (39 % de
redraws pela referência condicionada); pior caso limitado pelo teto 100·N
(≈ 100× o custo base). Na escala do piloto, ~2 s por sequência h+1: stdlib
basta. A Task 08 re-mede com a implementação real (bloco `timeit` da Task) e
registra em §7; os testes unitários usam N ≤ 2 000 e T ≤ 40.

**Gate por Task (RUNBOOK §Gates em camadas, ADR 0.0.0055):** T1 =
`make check-task SLICE=evaluation` em **todas** as Tasks de código (nenhuma
toca dependência, `.importlinter`, script de gate, `tests/architecture/` nem
conftest compartilhado — o `tests/unit/features/evaluation/conftest.py` é
local do slice, precedente 6.1 Task 02). Task 12 (docs) roda
`make docs-check`. Checkpoint C (T2, `make check-block`) após as Tasks 03,
06, 09 e 12; T3 (`make check`) no gate de saída (§3).

**Onde rodar — convenção dos blocos de verificação (vale para §2 e §3):**

- Cada verificação vem num bloco rotulado **Container** ou **Host**. O host
  não tem o toolchain (`uv`/`make` só existem no container).
- **Container:** o bloco inteiro roda num **único** shell `bash` com
  `set -euo pipefail`, dentro de **um** `docker run` (o `sh` do container é
  `dash`; linhas em `docker run --rm` distintos perdem arquivos temporários —
  um `grep` sobre arquivo inexistente devolve 2 e o `!` o transforma em verde
  falso, medido no Checkpoint B):
  ```bash
  WT=feat-113-6-3-calibration-risk-backtests
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT:/app" \
    -v "C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git" \
    -v ff-step6-venv:/app/.venv \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app \
    -w /app financial_forecasting-app:dev bash -euo pipefail -c "$(cat <<'EOF'
  git config --global --add safe.directory '*'
  # <linhas do bloco Container da Task>
  EOF
  )"
  ```
  (script passado por `-c`, não por stdin: um comando do bloco que lesse
  stdin consumiria o resto do script.)
- **Host:** Git Bash na raiz da worktree, o bloco como um só script
  `bash -euo pipefail` (scripts stdlib `python scripts/check_*.py`, a
  pré-checagem da Task 10, `cmp`, greps de docs, `git diff`).
- **Negação:** `set -e` **ignora** o status de um comando prefixado por `!`;
  toda asserção negativa é escrita `! <cmd> || exit 1`. Arquivo produzido e
  lido no mesmo bloco, e a leitura começa por `test -s "$f"`.
- A geração da fixture R (Task 10) roda na imagem `ff-r-oracle:4.4.1`.

### Pré-condições

- Stage `6.1-scoring-and-calibration-metrics` em `done` e mergeada em
  `develop` (PR #112): `CoverageSeries`, `pair_miscoverage`,
  `DegeneracyGate`/`DegeneracyReport`, `CoverageMetrics`/`PairCoverage`,
  `is_finite_number`.
- Concept desta Stage em `done`; ADRs 6.3.0001–0006 em `accepted`.
- Working tree na branch `feat/113-6-3-calibration-risk-backtests`.
- Imagem local `ff-r-oracle:4.4.1` (R 4.4.1, `rugarch` **`1.5-3`** na forma
  do `sessionInfo()`/`packageDescription()` — `packageVersion()` imprime
  `1.5.3`; `jsonlite`; build com o `Dockerfile` de duas linhas do ADR
  6.2.0006), offline.
- **Regras do formato de fixture R do Step** (sessão mestra, sobre o ADR
  6.2.0006 — valem mesmo que a cópia irmã do ADR mostre versão anterior):
  toda **entrada** de ponto flutuante (escalar ou vetor) é o objeto
  `{"dec": <número | [números]>, "hex": <string | [strings]>}` — `dec` por
  `sprintf("%.17g")`, `hex` por `sprintf("%a")`, mesma forma; inteiros
  (contagens, 0/1 das violações) e strings ficam JSON puro; **saídas** são
  números JSON escritos com `%.17g`; testes lêem entradas por
  `float.fromhex(hex)`; `provenance` com `generator`, `image`, `r_version`,
  `packages`, `cran_snapshot`, `generated_at`, `session_info` (caminho
  relativo ao JSON do `<unit>.sessionInfo.txt`), `command`;
  `provenance.packages[p] = packageDescription(p)$Version` (forma do
  `sessionInfo()`, ex. `rugarch_1.5-3`); `jsonlite::toJSON(digits = NA)` só
  escreve 15 dígitos — literais montados com `sprintf`.
- **A10 (parte "o teste de proveniência da 6.2 passa sobre este JSON")
  depende da 6.2 e é BLOQUEANTE de merge:** o teste
  `tests/integration/features/evaluation/test_r_oracle_provenance.py` nasce
  no PR da 6.2 (`feat/114-6-2-paired-inference-dm-mcs-holm`). Enquanto ele
  não existir nesta branch, a Task 10 roda a pré-checagem local equivalente
  (mesmos campos, formas de versão e round-trip), o gate de saída imprime
  `PENDENTE` (§3), a §7 recebe um `[finding]` e o A10 fica **desmarcado** no
  PR: a 6.3 só mergeia depois que a 6.2 estiver em `develop`, esta branch
  rebasear e o teste da 6.2 passar sobre `var_test_cases.json` (fix em
  `[6.3/task-10-fix]` se reprovar).

### Premissas técnicas

- Python 3.12; `uv`; `make check` = ruff + mypy strict + check_layout +
  lint-imports + fake-parity + port-coverage + docs-check + pytest com
  cobertura ≥ 90 %.
- Domínio só stdlib: `math` (`erfc`, `exp`, `log`, `sqrt`, `fsum`,
  `nextafter`), `statistics.NormalDist` (κ do Wilson), `random.Random` (MC;
  só `random()` — reprodutibilidade garantida entre versões pela doc do
  Python), `enum.StrEnum`, `dataclasses`. **Sem scipy/numpy** (I7, I11).
- Marcador `unit` = sem I/O: testes que leem a fixture são de
  **integração** (`pytestmark = pytest.mark.integration`), em
  `tests/integration/features/evaluation/` (pacote já existe, com
  `__init__.py`).
- Tolerâncias numéricas sempre declaradas no módulo de teste (ADR 0.0.0021):
  identidades de float `1e-12`; oráculo R `1e-10` absoluto (ADR 6.3.0003 —
  arredondamento, nunca O(1/T)).
- **Nomes de teste com tokens obrigatórios:** cada Task lista os tokens que
  os nomes dos seus testes **devem** conter; a matriz I*/C* abaixo aponta
  para eles e o §3 prova, por coleta, que cada token de cada arquivo casa
  ≥ 1 teste (Checkpoint B T2).
- **Valores de fronteira medidos nesta Fase 3B** (fórmulas do concept,
  float64) — os critérios A3–A5/A7/A9 não são presumidos:
  - `erfc(√(3.841458820694124/2)) = 0.05000000000000008`;
    `exp(−5.991464547107979/2) = 0.05000000000000007` (ambos a < 1e-12 de
    0.05);
  - Wilson 95 %: c = 10, n = 500 → (0.01089918359621081, 0.03642018324687933)
    → [0.011, 0.036]; c = 20, n = 1000 → [0.013, 0.031]; região de aceitação a
    τ = 0.02, n = 500: **c ∈ [4, 16]**; equivariância c ↔ n − c com erro
    ≤ 1.2e-16; c = 10.5 → (0.011610…, 0.037693…), entre os de 10 e 11;
  - Kupiec (p = 0.02, χ²(1) a 5 % = 3.841458820694124): maior T que rejeita
    por excesso x = 1 → 3, 2 → 17, 3 → 38, 4 → 63 (e T + 1 não rejeita);
    não-rejeição T = 250 → [2, 9], 500 → [5, 16], 1000 → [12, 29]
    (contíguas); x = 4, T = 500 → 4.742845480299913 (4,74); x = 0, T = 500 →
    20.202707317519465 = −2·500·log(0.98);
  - LR_uc de 3 estados (taxas 0.02/0.02): (7, 3, 200) → 2.1294…,
    (7.5, 3, 200) → 2.7357…, (8, 3, 200) → 3.4114… (o real fica entre os
    vizinhos inteiros de `lower_count`); (4, 4, 200) → `-0.0` (igual a 0.0);
  - **Piso I13 — entradas reais que dão LR bruto negativo** (forma
    `−2·(ℓ(p) − ℓ(p̂))` com log-somas e `xlogy`): `kupiec_pof(violations=2,
    observations=5, violation_rate=0.39999999999999997)` → −8.88e-16;
    LR_ind com transições (n00, n01, n10, n11) = (1, 2, 3, 6) → −1.78e-15
    (sequência de 13 posições `[1,1,1,1,1,1,1,0,0,1,0,1,0]`);
    `lr_uc_three_state(lower_count=1, upper_count=3, n=6,
    lower_rate=1/6, upper_rate=0.5)` → −1.78e-15. A ordem de operações da
    implementação decide o float: se uma dessas der ≥ 0 na execução, varrer
    outra entrada (taxas = contagens/n; π̂01 = π̂11) e registrar o valor
    medido em §7 — o piso também é testado direto no helper;
  - `1 - 0.02 == 0.98` em float64 (A9).

### Estrutura de pastas afetada

```
src/financial_forecasting/features/evaluation/domain/
├── value_objects/
│   ├── coverage_series.py          # MODIFICADO (01): is_at_or_below, is_inside_closed
│   └── hit_sequence.py             # NOVO (05): HitKind, HitSequence, count_transitions
└── services/
    ├── coverage_metrics.py         # MODIFICADO (01, 02): consome FA7; MPIW_LABEL
    ├── chi_square.py               # NOVO (03): chi_square_sf, floor_lr_statistic
    ├── kupiec_pof.py               # NOVO (03): xlogy, kupiec_pof
    ├── wilson_band.py              # NOVO (04)
    ├── hit_sequences.py            # NOVO (06)
    ├── christoffersen_test.py      # NOVO (07), MODIFICADO (08)
    └── var_descriptive.py          # NOVO (09)
tests/
├── unit/features/evaluation/
│   ├── conftest.py                 # MODIFICADO (05): fábrica de HitSequence
│   ├── test_coverage_series.py     # MODIFICADO (01)
│   ├── test_coverage_metrics.py    # MODIFICADO (01, 02)
│   ├── test_chi_square.py          # NOVO (03)
│   ├── test_kupiec_pof.py          # NOVO (03)
│   ├── test_wilson_band.py         # NOVO (04)
│   ├── test_hit_sequence.py        # NOVO (05)
│   ├── test_hit_sequences.py       # NOVO (06)
│   ├── test_christoffersen_test.py # NOVO (07), MODIFICADO (08)
│   ├── test_christoffersen_monte_carlo.py  # NOVO (08)
│   └── test_var_descriptive.py     # NOVO (09)
├── integration/features/evaluation/
│   ├── _var_test_cases.py          # NOVO (11): carregador da fixture
│   ├── test_kupiec_vs_oracle.py    # NOVO (11)
│   └── test_christoffersen_vs_rugarch.py  # NOVO (11)
└── fixtures/r_oracle/
    ├── Dockerfile                  # NOVO (10) — byte-idêntico ao da 6.2
    ├── var_test_cases.R            # NOVO (10)
    ├── var_test_cases.json         # NOVO (10)
    └── var_test_cases.sessionInfo.txt  # NOVO (10)
docs/roadmap.md                                             # MODIFICADO (12)
docs/domain/evaluation/probabilistic-forecast-evaluation.md # MODIFICADO (12)
docs/overview.md                                            # MODIFICADO (12)
```

Intocados por decisão (D9, I11): `pyproject.toml`, `uv.lock`,
`.importlinter`, `docs/LAYOUT.md`, `scripts/**`, `tests/architecture/**`,
`src/**/adapters/**`, `src/**/application/**`; nenhum `.R` fora de
`tests/fixtures/r_oracle/`.

### Rastreabilidade — concept §11 (critérios A*) → Tasks

| # | Critério de aceitação (concept §11) | Tasks | Check objetivo |
|---|---|---|---|
| A1 | `HitSequence` ergue em cada caso de C1 (um teste por caso); `n_observed`/`n_violations`/`transition_counts` com lacunas; `dgt_partition` h = 3/T = 8 → {0,3,6},{1,4,7},{2,5}; h = 3/T = 2 → 2 sub-séries; h = 1 → `(self,)`; partição de sub-série ergue | 05 | `uv run pytest tests/unit/features/evaluation/test_hit_sequence.py -v` + tokens do §3 |
| A2 | `HitSequences`: empates I3; taxas exatas; máscara = `DegeneracyGate` da mesma série; `tolerance`/`degeneracy_rate`; `include_degenerate`; identidades de contagem com o `CoverageReport` (1e-12); `CoverageMetrics` consome os predicados e a 6.1 segue verde; C2 | 01 (predicados + consumo), 06 (resto) | Task 01: pytest dos dois arquivos + grep negativo de comparação inline; Task 06: `uv run pytest tests/unit/features/evaluation/test_hit_sequences.py -v`; tokens do §3 |
| A3 | `chi_square_sf` df 1/2 em 3.8414…/5.9914… → 0.05 (±1e-12); x = 0 → 1; df ∉ {1, 2}, negativo além do piso, não-finito erguem | 03 | `uv run pytest tests/unit/features/evaluation/test_chi_square.py -v` |
| A4 | Wilson: [0.011, 0.036], [0.013, 0.031]; região c ∈ [4, 16] (falso em 3 e 17); equivariância; contagem real entre inteiros; n = 0 não aplicável; `horizon = 7` → aviso; C3/C9 | 04 | `uv run pytest tests/unit/features/evaluation/test_wilson_band.py -v` |
| A5 | `kupiec_pof` = expressão (6) escrita no teste; Table 2 (3/17/38/63); regiões [2,9]/[5,16]/[12,29]; 4,74; x = 0; contagem real; piso I13 | 03 | `uv run pytest tests/unit/features/evaluation/test_kupiec_pof.py -v` |
| A6 | `ChristoffersenTest.evaluate`: fixture à mão; `lr_cc == lr_uc + lr_ind` exato e ≈ forma direta (1e-12); `n11 = 0`; I_1 = 1 fora do n_1 puro e dentro do POF; um teste por `IndependenceStatus` (linha e coluna vazias) + precedência; `independence_descriptive`; piso antes de `p_ind`; C4 (com `bool`) e C9 (cada desigualdade) | 07 | `uv run pytest tests/unit/features/evaluation/test_christoffersen_test.py -v` |
| A7 | `lr_uc_three_state`: valor à mão; 0 quando contagens = n·taxas; χ²(2) pelo `chi_square_sf`; contagens reais; C3 | 08 | `uv run pytest tests/unit/features/evaluation/test_christoffersen_test.py -v -k three_state` |
| A8 | MC: `mc_p_value` à mão com empates (G̃_N, p̃ exatos; p̃ ≤ p̂); determinismo + regressão congelada; `attempts = 0` sem LR_uc; identidade + `min_violations` no resultado; envelope binomial; referência condicionada (replay independente do RNG ≡ implementação, ≠ não condicionada); teto → `MC_CAP_REACHED` com `p_uc` presente; C5; C4 | 08 | `uv run pytest tests/unit/features/evaluation/test_christoffersen_monte_carlo.py -v` |
| A9 | `VarDescriptive`: um `VarTailBacktest` por τ ≠ 0.5 na ordem da grade; `kind` por τ; `var_level` 0.98/0.98; `backtest` = `ChristoffersenTest.evaluate(HitSequences.…)`; rótulo (divergente ergue); série 100 % degenerada → todas não aplicáveis | 09 | `uv run pytest tests/unit/features/evaluation/test_var_descriptive.py -v` |
| A10 | Unidade `var_test_cases` no formato do Step (o teste da 6.2 passa sobre ela); T ≤ 500 no `provenance`; iid + agrupados para vários p; saídas finitas; ≥ 1 caso I_1 = 1 com \|LR_uc puro − `uc` inteiro\| > 0.1; casos em que o R falha gravados; os dois testes de integração verdes sob tolerância de arredondamento; R-falha testado como política; unit só analítico; nenhum arquivo novo em `adapters/`/`application/ports/` | 10 (fixture + pré-checagem), 11 (testes); §3 (teste da 6.2 — **bloqueante de merge**) | pré-checagem da Task 10 (Host) + bloco Container da Task 11 (zero `SKIPPED` no mesmo shell) + §3: `test_r_oracle_provenance.py` verde ou `PENDENTE` (A10 desmarcado, merge bloqueado) |
| A11 | `PairCoverage.mpiw_label == MPIW_LABEL`; divergente ergue; 6.1 verde | 02 | `uv run pytest tests/unit/features/evaluation/test_coverage_metrics.py -v` |
| A12 | Nenhum identificador heurístico no slice; `lint-imports` verde (sem aresta cross-slice; domínio sem numpy/scipy) | 01–11 (cada T1 roda `lint-imports`); gate §3 | grep A12 do §3 (Host; zero ocorrências no slice — nem em prosa) + `uv run lint-imports` (Container) |
| A13 | Roadmap 6.3 (D2) e 6.5; doc de domínio §7.6/§10.1/linha 22, §7.7/§11.3/conv. 21; Dufour 2006 e BCP 2011 em overview §10 e doc §11.2; `make docs-check` | 12 | greps por (arquivo, seção, termo) da Task 12 (Host) + `make docs-check` (Container) |
| A14 | `make check` verde; cobertura ≥ 90 % global e por arquivo; mypy strict e `check_layout.py`; ADRs 6.3.0001–0006 `accepted` | todas (T1 por Task); gate §3 | bloco Container do §3 (`make check` + cobertura por arquivo no mesmo shell, exit ≠ 0 se algum arquivo de `features/evaluation/` < 90 %) + `grep -L` dos ADRs (Host) |

### Rastreabilidade — invariantes (I*) e casos de erro (C*) → Tasks

Notação: `arquivo::token` = o arquivo de teste (em
`tests/unit/features/evaluation/`, salvo indicação) contém ≥ 1 teste cujo
nome (sem o id `[...]` de parametrização) contém o token — **provado no
§3** pelo laço de coleta. Os tokens de um mesmo arquivo são únicos e nenhum
é substring de outro (o laço recusa a lista se for), para a prova não ser
vácua.

| # | Regra (concept §5/§6) | Tasks | Check objetivo |
|---|---|---|---|
| I1 | Por série/horizonte; relatórios trazem `horizon` (inclusive Wilson) | 04, 05, 07, 08, 09 | `test_wilson_band.py::wilson_horizon`, `test_hit_sequence.py::hitseq_horizon`, `test_christoffersen_test.py::copies_identity`, `test_christoffersen_monte_carlo.py::mc_carries_identity`, `test_var_descriptive.py::var_horizon` |
| I2 | `True` = violação; taxa nominal da grade pela regra do `kind`; hits ↔ violações dão LR idênticos | 05, 06, 07, 09 | `test_hit_sequence.py::kind_rate`, `test_hit_sequences.py::grid_rates`, `test_christoffersen_test.py::hits_invariance`, `test_var_descriptive.py::var_level` |
| I3 | FA7 com dono único; vetor pós-guardrail; identidades de contagem | 01, 06 | `test_coverage_series.py::fa7_at_or_below`, `::fa7_inside_closed`; `test_coverage_metrics.py::consumes_fa7_predicates`; `test_hit_sequences.py::fa7_ties`, `::count_identities`, `::scores_guardrail`, `::consumes_predicates` |
| I4 | Máscara da própria série como lacuna `None`; n = observadas, nunca S·T; "sem lacunas" explícita; 100 % degenerada toda `None` | 05, 06 | `test_hit_sequence.py::mask_gaps`; `test_hit_sequences.py::gate_mask`, `::without_gaps_variant`, `::all_none_when_degenerate` |
| I5 | Transições só entre consecutivas observadas (uma função de contagem); LR_uc puro com n_1 = n01 + n11; `lr_cc := lr_uc + lr_ind`; conv. 21 só no trio | 05, 07 | `test_hit_sequence.py::gap_transitions`; `test_christoffersen_test.py::pure_convention`, `::lr_cc_identity`, `::first_observation`, `::primitive_gaps`, `::single_counting` |
| I6 | Aplicabilidade é resultado; ordem de precedência; `n11 = 0` aplicável; `min_violations` `int` obrigatório, conta todas as violações observadas | 07 | `test_christoffersen_test.py::status_each`, `::status_precedence`, `::n11_zero`, `::min_violations_base`, `::min_violations_signature` |
| I7 | χ² fechado; κ por `NormalDist`; sem scipy; MC só h = 1, `draws`/`seed` obrigatórios, Dufour, referência condicionada | 03, 04, 08 | `test_chi_square.py::chi2_critical`; `test_wilson_band.py::wilson_bcd`; `test_christoffersen_monte_carlo.py::dufour_ties`, `::conditioned_reference`, `::mc_signature` |
| I8 | h > 1 → `independence_descriptive` (salvo DGT); MC recusa h > 1 e sub-série; partição DGT | 05, 07, 08 | `test_hit_sequence.py::dgt_partition`; `test_christoffersen_test.py::h7_descriptive`; `test_christoffersen_monte_carlo.py::horizon_raises`, `::dgt_subseries_raises` |
| I9 | Rótulos `VAR_DESCRIPTIVE_LABEL`/`MPIW_LABEL` validados; `var_level` | 02, 09 | `test_coverage_metrics.py::mpiw_label`; `test_var_descriptive.py::descriptive_label`, `::var_level` |
| I10 | Kernels de contagem aceitam reais; trio/MC inteiros; 3 estados com contagens unilaterais (as das `HitSequences` de cauda) sobre todas as observadas | 03, 04, 08 | `test_kupiec_pof.py::kupiec_real_count`; `test_wilson_band.py::wilson_real_count`; `test_christoffersen_test.py::three_state_real_count`, `::three_state_composition` |
| I11 | Domínio puro; nada de R em `src/`; `.importlinter`/`pyproject.toml`/`uv.lock`/`LAYOUT.md` intocados | todas; gate §3 | `uv run lint-imports` (T1) + bloco Host do §3 (`git diff --quiet` e nenhum `.R` fora de `tests/fixtures/r_oracle/`) |
| I12 | Oráculo exato por convenção igual (dois *feeds*), tolerância de arredondamento | 11 | `tests/integration/…/test_christoffersen_vs_rugarch.py::trio_two_feeds`, `::lr_ind_whole_feed`; `tests/integration/…/test_kupiec_vs_oracle.py::kupiec_whole_feed` (`_ORACLE_ABS_TOL = 1e-10`) |
| I13 | Piso `[−1e-9, 0)` → 0.0 antes de guardar/somar; abaixo ergue | 03, 07, 08 | `test_chi_square.py::chi2_floor`, `test_kupiec_pof.py::kupiec_floor`, `test_christoffersen_test.py::lr_ind_floor`, `::three_state_floor` |
| C1 | `HitSequence` mal-formada (cada ramo) | 05 | `test_hit_sequence.py::hitseq_invalid` (um caso por ramo, parametrizado) |
| C2 | Par/nível inexistente; tolerância inválida no construtor | 06 | `test_hit_sequences.py::unknown_pair_or_level`, `::invalid_tolerance` |
| C3 | Kernel com argumento inválido (contagens, n, não-finito/`bool`, taxas, `band_level`, `nominal`, df, estatística, 3 estados) | 03, 04, 08 | `test_chi_square.py::chi2_invalid`, `test_kupiec_pof.py::kupiec_invalid`, `test_wilson_band.py::wilson_invalid`, `::wilson_nominal`, `test_christoffersen_test.py::three_state_invalid` |
| C4 | `min_violations`/`draws`/`seed` inválidos ou `bool` | 07, 08 | `test_christoffersen_test.py::min_violations_invalid`; `test_christoffersen_monte_carlo.py::invalid_draws`, `::invalid_seed` |
| C5 | MC com h > 1 ou em sub-série DGT (ramos distintos) | 08 | `test_christoffersen_monte_carlo.py::horizon_raises`, `::dgt_subseries_raises` |
| C6 | Estatística indefinida → relatório com `None` + status | 07, 08 | `test_christoffersen_test.py::all_masked_not_applicable`; `test_christoffersen_monte_carlo.py::uc_not_applicable`, `::uc_only` |
| C7 | Série 100 % degenerada → toda `None`; relatórios não aplicáveis; Wilson n = 0; VaR com caudas não aplicáveis | 04, 06, 07, 09 | `test_hit_sequences.py::all_none_when_degenerate`, `test_christoffersen_test.py::all_masked_not_applicable`, `test_var_descriptive.py::all_tails_not_applicable`, `test_wilson_band.py::wilson_not_applicable` |
| C8 | Fixture fora do formato do Step → teste da 6.2 falha; erro do R nunca é valor esperado | 10, 11; §3 | pré-checagem da Task 10; §3 (teste da 6.2 ou `PENDENTE`); `tests/integration/…/test_christoffersen_vs_rugarch.py::r_error_policy` |
| C9 | Relatório incoerente construído à mão (cada ramo) | 04, 07, 08, 09 | `test_wilson_band.py::wilson_incoherent`, `test_christoffersen_test.py::report_incoherent`, `test_christoffersen_monte_carlo.py::mc_incoherent`, `test_var_descriptive.py::tail_incoherent` |

## 2. Tasks

> Faixa desta Stage: **12 Tasks** (estimativa do concept §12: ~10 — ver
> exceções declaradas em §1). Blocos de verificação conforme a convenção
> **Container/Host** do §1.

### Task 01 — Predicados FA7 com dono único; `CoverageMetrics` passa a consumi-los

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/coverage_series.py`
  - `src/financial_forecasting/features/evaluation/domain/services/coverage_metrics.py`
  - `tests/unit/features/evaluation/test_coverage_series.py`
  - `tests/unit/features/evaluation/test_coverage_metrics.py`
- **Arquivos a criar:** nenhum.
- **O que fazer (concept §4 "Predicados FA7", I3; ADR 6.3.0001 item 2):**
  funções de módulo ao lado de `pair_miscoverage` —
  `is_at_or_below(realized: float, quantile: float) -> bool` (1{y ≤ q̂}) e
  `is_inside_closed(realized: float, lower: float, upper: float) -> bool`
  ([l ≤ y ≤ u]) — com docstring citando FA7/doc §4.5 e os consumidores
  (`CoverageMetrics`, `HitSequences`; a violação de cauda superior é
  `not is_at_or_below`). O `CoverageMetrics` importa os dois **nomes** no
  seu namespace (`from … import is_at_or_below, is_inside_closed`) e troca as
  comparações inline de ĉ(τ) e do PICP por eles. Nenhuma mudança de
  comportamento.
- **Detalhes técnicos:** predicados sem validação própria (decisão de detalhe
  do §1). O cálculo do MPIW e o resto do `CoverageMetrics` não mudam.
- **Critério de aceite:**
  - `test_coverage_series.py`: `is_at_or_below(y, q)` é `True` em y < q e em
    y = q, `False` em y > q; `is_inside_closed` é `True` em y = l, y = u e
    l < y < u, `False` fora (I3).
  - `test_coverage_metrics.py`: teste de **consumo** — com
    `monkeypatch.setattr(coverage_metrics_module, "is_at_or_below", lambda *_: True)`
    todo ĉ(τ) vira 1.0, e com `is_inside_closed` → `False` todo PICP vira 0.0
    (prova que o serviço não tem cópia própria da regra); todos os testes da
    6.1 seguem verdes sem alteração de expectativa.
  - Nenhuma comparação inline sobra no serviço (grep abaixo).
  - **Tokens de nome exigidos:** `test_coverage_series.py`: `fa7_at_or_below`,
    `fa7_inside_closed`; `test_coverage_metrics.py`: `consumes_fa7_predicates`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_coverage_series.py tests/unit/features/evaluation/test_coverage_metrics.py -v
  test -s src/financial_forecasting/features/evaluation/domain/services/coverage_metrics.py
  ! grep -nE "realized\[i\] <=|low <= series.realized" src/financial_forecasting/features/evaluation/domain/services/coverage_metrics.py || exit 1
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `refactor(evaluation): predicados FA7 com dono único consumidos pelo CoverageMetrics [6.3/task-01]`

---

### Task 02 — `MPIW_LABEL` no `PairCoverage`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/coverage_metrics.py`
  - `tests/unit/features/evaluation/test_coverage_metrics.py`
- **Arquivos a criar:** nenhum.
- **O que fazer (concept D10, I9):** constante de módulo
  `MPIW_LABEL: Final = "MPIW — sharpness descritiva, não-inferencial"` e campo
  aditivo `PairCoverage.mpiw_label: str = MPIW_LABEL` (último campo, com
  default — nenhum call-site muda), validado no `__post_init__`
  (`mpiw_label != MPIW_LABEL` → `ValueError`), no padrão do
  `CrpsReport.label` da 6.1. Docstring do `PairCoverage` cita o rótulo.
- **Critério de aceite (A11):** `CoverageMetrics.evaluate(...)` devolve todo
  `PairCoverage` com `mpiw_label == MPIW_LABEL`; `PairCoverage(...,
  mpiw_label="MPIW")` ergue; testes da 6.1 verdes. **Tokens:**
  `test_coverage_metrics.py`: `mpiw_label`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_coverage_metrics.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): rótulo descritivo MPIW_LABEL no PairCoverage [6.3/task-02]`

---

### Task 03 — Kernels `chi_square_sf` (+ piso I13) e `kupiec_pof`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/chi_square.py`
  - `src/financial_forecasting/features/evaluation/domain/services/kupiec_pof.py`
  - `tests/unit/features/evaluation/test_chi_square.py`
  - `tests/unit/features/evaluation/test_kupiec_pof.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I7, I10, I13, C3; ADRs 6.3.0001 itens 3 e 8, 6.3.0005):**
  - `chi_square.py`: `LR_NEGATIVE_FLOOR = -1e-9`;
    `floor_lr_statistic(value: float) -> float` (não-finito/`bool` ergue;
    `[LR_NEGATIVE_FLOOR, 0)` → `0.0`; abaixo ergue; ≥ 0 inalterado);
    `chi_square_sf(statistic: float, *, df: int) -> float` — `df` `int`
    não-`bool` em {1, 2} (senão ergue), aplica `floor_lr_statistic`, então
    df = 1: `math.erfc(math.sqrt(x / 2))`; df = 2: `math.exp(-x / 2)`.
  - `kupiec_pof.py`: `xlogy(x, y)` (0·log 0 = 0 — única escrita da
    convenção); `kupiec_pof(*, violations: float, observations: float,
    violation_rate: float) -> float` — valida (C3) com `is_finite_number`
    (não-finito e `bool` erguem), `observations > 0`,
    `0 <= violations <= observations`, `violation_rate` em (0, 1); calcula
    `−2·(ℓ(x, n, p) − ℓ(x, n, x/n))` com `ℓ(x, n, q) = xlogy(n − x, 1 − q) +
    xlogy(x, q)` (log-somas, sem produto de verossimilhanças) e devolve
    `floor_lr_statistic(...)`. Docstring cita Kupiec 1995 expr. (6) e a
    identidade POF ≡ LR_uc (doc §7.3).
- **Critério de aceite:**
  - **A3** (`test_chi_square.py`): `chi_square_sf(3.841458820694124, df=1)`
    e `chi_square_sf(5.991464547107979, df=2)` a ±1e-12 de 0.05 (valores
    medidos em §1); x = 0 → 1.0 nos dois df; `df=0`, `df=3`, `df=True`
    erguem; `nan`/`inf`/`True` como estatística erguem; −1e-14 → 1.0 (piso);
    −2e-9 ergue. `floor_lr_statistic`: −1e-14 → 0.0, `LR_NEGATIVE_FLOOR`
    exato → 0.0 (fronteira inclusa), `math.nextafter(LR_NEGATIVE_FLOOR,
    -math.inf)` ergue, 0.0 e 3.5 inalterados.
  - **A5** (`test_kupiec_pof.py`): igual (1e-12) à expressão (6) de Kupiec
    escrita **no teste** como `-2*log((1-p)**(n-x) * p**x) +
    2*log((1-x/n)**(n-x) * (x/n)**x)` em n pequeno (≤ 60, sem sub-fluxo), com
    x ∈ {1, …, n−1}; **Table 2** (p = 0.02): para x = 1, 2, 3, 4 o maior T
    com `x/T > p` e `chi_square_sf(kupiec_pof(...), df=1) < 0.05` é 3, 17,
    38, 63, e T + 1 não rejeita; **regiões de não-rejeição** a 5 % para
    T = 250/500/1000 são exatamente [2, 9], [5, 16], [12, 29]; x = 4,
    T = 500 → `round(·, 2) == 4.74`; x = 0 → `−2·n·log(1 − p)` (1e-12);
    **contagem real**: x = 10.5, n = 500 fica estritamente entre os valores
    em x = 10 e x = 11 (p·n = 10: lado crescente) e bate com a expressão (6)
    em x = 10.5, n = 500.5; **piso**: `kupiec_pof(violations=2,
    observations=5, violation_rate=0.39999999999999997)` devolve
    **exatamente** `0.0` (bruto medido em §1: −8.88e-16; se a implementação
    der ≥ 0, varrer outra entrada e registrar em §7); **C3**:
    `observations=0`, `violations=-1`, `violations > observations`, taxa
    0/1/1.5, `nan`, `inf`, `True` em cada argumento erguem (um caso
    parametrizado por ramo).
  - **Tokens:** `test_chi_square.py`: `chi2_critical`, `chi2_floor`,
    `chi2_invalid`; `test_kupiec_pof.py`: `kupiec_expression`, `kupiec_table2`,
    `kupiec_region`, `kupiec_real_count`, `kupiec_floor`, `kupiec_invalid`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_chi_square.py tests/unit/features/evaluation/test_kupiec_pof.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): kernels chi_square_sf com piso numérico e kupiec_pof [6.3/task-03]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

---

### Task 04 — `WilsonBand`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/wilson_band.py`
  - `tests/unit/features/evaluation/test_wilson_band.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I1, I4, I10, C3, C7, C9; doc §4.4; ADR 6.3.0005):**
  `wilson_interval(*, count, n, band_level) -> tuple[float, float]` — BCD 2001
  Eq. (4): κ = `NormalDist().inv_cdf(1 − (1 − band_level)/2)`,
  centro `(c + κ²/2)/(n + κ²)`, meia-largura
  `κ·√n/(n + κ²)·√(p̂(1 − p̂) + κ²/(4n))`; valida `count`/`n`/`band_level`
  (finitos, não-`bool`, `0 ≤ count ≤ n`, `n > 0`, `band_level` em (0, 1)).
  `WilsonBandReport` frozen com `__post_init__` (C9): `horizon ≥ 1`;
  `nominal` e `band_level` em (0, 1); `applicable == (n > 0)`; com
  `applicable = False` todos os campos de banda `None`; com `True`,
  `estimate == count / n`, `lower ≤ upper` e `contains_nominal ==
  (lower <= nominal <= upper)`; `serial_dependence_warning == (horizon > 1)`.
  `WilsonBand.evaluate(*, horizon, count, n, nominal, band_level)` — valida
  `horizon` (`int` ≥ 1) e `nominal` (finito, em (0, 1)); `n == 0` (com
  `count == 0`) → relatório não aplicável; senão chama `wilson_interval`.
  Docstrings dizem que `count`/`n` podem ser médias entre seeds (ADR 6.3.0005)
  e usam "nível da banda", nunca o termo proibido pelo A12.
- **Critério de aceite (A4):** c = 10, n = 500, 95 % → `[round(l, 3),
  round(u, 3)] == [0.011, 0.036]`; c = 20, n = 1000 → `[0.013, 0.031]`
  (`wilson_bcd`); `contains_nominal` a τ = 0.02, n = 500, 95 % é `True` para todo
  c ∈ [4, 16] e `False` em 3 e 17 (`wilson_region`, fronteira medida em §1);
  equivariância: banda de n − c = `(1 − upper(c), 1 − lower(c))` (1e-12) em
  três (c, n) (`wilson_equivariance`); c = 10.5 dá limites estritamente entre os de
  10 e 11 (`wilson_real_count`); n = 0 → `applicable = False` e
  `estimate`/`lower`/`upper`/`contains_nominal` `None` (`wilson_not_applicable`);
  `horizon = 7` → `serial_dependence_warning is True`, `horizon = 1` →
  `False`, e `report.horizon` = o passado (`wilson_horizon`, I1); C3 (`wilson_invalid`, um
  caso por ramo: `count < 0`, `count > n`, `n < 0`, `n = 0` em
  `wilson_interval`, `band_level` 0/1, `nan`/`inf`/`bool`); **`nominal` 0, 1,
  `nan` e `horizon` 0, `True` em `evaluate` erguem** (`wilson_nominal`, `wilson_horizon`);
  C9 (`wilson_incoherent`, um caso por ramo do `__post_init__`: `contains_nominal`
  invertido, banda preenchida com `applicable = False`, `applicable = True`
  com n = 0, `estimate` ≠ c/n, aviso incoerente com o horizonte, `nominal`
  fora de (0, 1), `horizon` 0).
  **Tokens:** `wilson_bcd`, `wilson_region`, `wilson_equivariance`,
  `wilson_real_count`, `wilson_not_applicable`, `wilson_horizon`,
  `wilson_nominal`, `wilson_invalid`, `wilson_incoherent`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_wilson_band.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): banda de Wilson com contagens reais e veredito contém-o-nominal [6.3/task-04]`

---

### Task 05 — VO `HitSequence` (com partição DGT e contagem única de transições)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/hit_sequence.py`
  - `tests/unit/features/evaluation/test_hit_sequence.py`
- **Arquivos a modificar:**
  - `tests/unit/features/evaluation/conftest.py` — fábrica
    `make_hit_sequence(violations, *, kind=HitKind.LOWER_TAIL, levels=(0.05,),
    horizon=1, tolerance=0.0, includes_degenerate=False, …)` que deriva
    `violation_rate` pela regra do `kind`, `degeneracy_rate = n_None / T` e
    timestamps via `iso_timestamps` (usada pelas Tasks 05, 07, 08).
- **O que fazer (concept §4 `HitSequence`, I2, I4, I5, I8, C1; ADRs 6.3.0001
  item 1, 6.3.0004):** `HitKind(StrEnum)`, a função de módulo
  `count_transitions(violations: Sequence[bool | None]) -> tuple[int, int,
  int, int]` (pares consecutivos **ambos** observados — dono único, decisão
  de detalhe do §1) e `HitSequence` frozen stdlib-only com os campos e
  propriedades do concept §4. `__post_init__` (C1, um ramo por caso,
  mensagens nomeiam o campo/posição): tamanhos iguais e ≥ 1; timestamps
  estritamente crescentes; `horizon ≥ 1`; `levels` com tamanho 2 (INTERVAL)
  ou 1 (caudas); `violation_rate` **igual** (exato) a
  `pair_miscoverage(levels[0])` / `levels[0]` / `1.0 - levels[0]` e em
  (0, 1); elementos `bool` ou `None` (`1`, `0`, `"x"` erguem — `type(v) is
  bool`); `tolerance` via `is_finite_number` e ≥ 0; `degeneracy_rate` em
  [0, 1]; `includes_degenerate = True` com algum `None` exige todos `None`;
  variante mascarada fora de sub-série DGT exige `degeneracy_rate ==
  n_None / T` (mesma forma do `DegeneracyReport`); `dgt_offset`/`dgt_step`
  ambos ou nenhum; `0 ≤ dgt_offset < dgt_step`; `dgt_step == horizon`;
  `dgt_step ≥ 2` (decisões de detalhe do §1).
  Propriedades: `n_observed` (não-`None`), `n_violations` (`True` entre as
  observadas), `transition_counts` (= `count_transitions(self.violations)`).
  `dgt_partition()`: sub-série ergue; `horizon == 1` → `(self,)`; senão
  `min(horizon, T)` sub-séries `j = 0..`, posições `j, j + h, …`, com os
  timestamps e violações dessas posições, mesmo `horizon`/`kind`/`levels`/
  `violation_rate`/`tolerance`/`includes_degenerate`/`degeneracy_rate` (o da
  série de origem), `dgt_offset = j`, `dgt_step = horizon`.
- **Critério de aceite (A1):** um caso por ramo de C1 (lista acima, inclusive
  os de DGT — só um preenchido, `offset ≥ step`, `offset < 0`,
  `step ≠ horizon`, `step = 1` com `horizon = 1` — e o `bool`-vs-`int`)
  (`hitseq_invalid`); taxa por `kind` exata e taxa divergente ergue (`kind_rate`);
  fixture com lacunas `[F, T, None, T, T, None, F, T]` → `n_observed = 6`,
  `n_violations = 4` (`mask_gaps`), `transition_counts == count_transitions(...)
  == (0, 2, 0, 1)` (pares (0,1) F→T, (3,4) T→T, (6,7) F→T; os que atravessam
  `None` não contam — `gap_transitions`); h = 3, T = 8 → 3 sub-séries com
  posições {0, 3, 6}, {1, 4, 7}, {2, 5}, lacunas preservadas,
  `dgt_offset`/`dgt_step`, `horizon` e timestamps certos, união disjunta = a
  sequência; h = 3, T = 2 → 2 sub-séries; h = 1 → `seq.dgt_partition() ==
  (seq,)`; `sub.dgt_partition()` ergue (`dgt_partition`); `horizon = 0` ergue e o
  `horizon` passado é preservado (`hitseq_horizon`); frozen
  (`FrozenInstanceError`).
  **Tokens:** `hitseq_invalid`, `kind_rate`, `mask_gaps`, `gap_transitions`,
  `dgt_partition`, `hitseq_horizon`.
- **Comando de verificação (T1 — conftest local do slice) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_hit_sequence.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): VO HitSequence com lacunas da máscara e partição DGT [6.3/task-05]`

---

### Task 06 — Construtor `HitSequences`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/hit_sequences.py`
  - `tests/unit/features/evaluation/test_hit_sequences.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4 `HitSequences`, I2, I3, I4, C2, C7; ADRs 6.3.0001
  item 2, 6.3.0004 item 4, 6.1.0004):** três `@staticmethod`
  (`interval`, `lower_tail`, `upper_tail`) com `tolerance` keyword-only **sem
  default** e `include_degenerate: bool = False`. Cada um: casa `pair` com
  `series.symmetric_pairs` / `level` com `series.levels` por igualdade exata
  (senão `ValueError`, C2); roda `DegeneracyGate.evaluate(series,
  tolerance=tolerance)` da **mesma** série (tolerância inválida ergue pelo C3
  do gate); indicador por linha via `series.scored_values(i)` (pós-guardrail)
  e os predicados da Task 01 — intervalo: `not is_inside_closed(y, l, u)`;
  cauda inferior: `is_at_or_below(y, q̂_τ)`; superior:
  `not is_at_or_below(y, q̂_τ)`; linha degenerada → `None` na variante
  mascarada; `include_degenerate=True` não mascara, salvo taxa de
  degeneração 1.0 (toda `None`); `violation_rate` pela regra do `kind`
  (`pair_miscoverage(τ_l)`, `τ`, `1.0 - τ`); `tolerance` e
  `degeneracy_rate = report.rate` gravados. Nenhum import de
  `QuantileForecast`.
- **Critério de aceite (A2):** empates — y = l e y = u não violam o
  intervalo; y = q̂_τ viola a cauda inferior e não a superior (`fa7_ties`); taxas
  exatas (`(0.05, 0.95)` → `pair_miscoverage(0.05)`, que é 0.1; cauda
  inferior 0.02 → 0.02; superior 0.98 → `1 - 0.98`) numa série com a grade
  (0.02, 0.05, 0.5, 0.95, 0.98) (`grid_rates`); linha degenerada → `None` e
  posições `None` == `DegeneracyGate.evaluate(series, tolerance=t)
  .degenerate`, com `tolerance`/`degeneracy_rate` iguais aos do gate
  (`gate_mask`); `include_degenerate=True` sem `None` numa série mista
  (`without_gaps_variant`) e toda `None` numa série 100 % degenerada (C7,
  `all_none_when_degenerate`); **identidades de contagem** com
  `CoverageMetrics.evaluate(series, tolerance=t)` da mesma série, numa série
  aleatória com linhas degeneradas (`random.Random(<seed declarada>)`): cauda
  inferior `n_violations/n_observed == ĉ(τ)`, superior `== 1 − ĉ(τ)`,
  intervalo `== 1 − PICP` (1e-12) (`count_identities`); fixture cruzada
  (`direct=True` com `guardrail_grids`) → indicadores pelo
  `guardrail_values` (`scores_guardrail`); consumo dos predicados provado por
  `monkeypatch` (`consumes_predicates`); C2: par (0.05, 0.98) e nível 0.3 inexistentes
  erguem (`unknown_pair_or_level`), tolerância −1/`nan` ergue (`invalid_tolerance`);
  `inspect.signature`: `tolerance` keyword-only sem default nos três
  (`tolerance_signature`).
  **Tokens:** `fa7_ties`, `grid_rates`, `gate_mask`, `without_gaps_variant`,
  `all_none_when_degenerate`, `count_identities`, `scores_guardrail`,
  `consumes_predicates`, `unknown_pair_or_level`, `invalid_tolerance`,
  `tolerance_signature`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_hit_sequences.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): construtor HitSequences com a máscara da própria série [6.3/task-06]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

---

### Task 07 — `ChristoffersenTest.evaluate` (trio puro + leitura Kupiec)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/christoffersen_test.py`
  - `tests/unit/features/evaluation/test_christoffersen_test.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I2, I5, I6, I8, I13, C4, C6, C9; ADRs 6.3.0001
  itens 4, 7, 8 e Implementation notes, 6.3.0004 item 2):**
  `IndependenceStatus`, `ChristoffersenStatistics` (frozen, `__post_init__`
  C9), `christoffersen_statistics(*, violations, violation_rate,
  min_violations)`, `ChristoffersenReport` (frozen, `__post_init__` C9) e
  `ChristoffersenTest.evaluate(sequence, *, min_violations)`.
  - Primitivo: valida `violation_rate` em (0, 1), `min_violations` (`int`,
    `type(...) is int`, ≥ 0 — C4) e os elementos (`bool`/`None` — decisão de
    detalhe do §1); conta `n_observed`, `n_violations` e as transições por
    **`count_transitions`** do VO (importado pelo nome no namespace do
    módulo — dono único); `kupiec_pof` = `kupiec_pof(n_violations,
    n_observed, p)` (None ⇔ `n_observed == 0`); `lr_uc` puro =
    `kupiec_pof(n01 + n11, Σn_ij, p)` (None ⇔ Σ = 0); status na ordem
    NO_TRANSITIONS → BELOW_MIN_VIOLATIONS (`n_violations <
    min_violations`, sobre **todas** as observadas) →
    DEGENERATE_TRANSITION_MATRIX (linha **ou** coluna vazia) → APPLICABLE;
    `lr_ind` (C&P 2004 §4.1, com `xlogy`: `−2·[ℓ(π̂) − ℓ(π̂01, π̂11)]`) passa
    por `floor_lr_statistic`; `lr_cc = lr_uc + lr_ind` composto **depois** do
    piso.
  - `ChristoffersenStatistics.__post_init__`: `lr_cc == lr_uc + lr_ind`
    exato; estatística preenchida ⇔ status APPLICABLE (e o inverso);
    `kupiec_pof is None` ⇔ `n_observed == 0`; `lr_uc is None` ⇔ Σn_ij = 0;
    as quatro desigualdades do ADR 6.3.0001 (Implementation notes).
  - `ChristoffersenReport.__post_init__`: p-valores em [0, 1] e `None`
    exatamente quando a estatística correspondente é `None`;
    `independence_descriptive == (horizon > 1 and dgt_offset is None)`.
  - `evaluate`: identidade (`horizon`, `kind`, `levels`, `violation_rate`,
    `tolerance`, `degeneracy_rate`, `includes_degenerate`, `dgt_offset`,
    `dgt_step`) copiada da sequência e `min_violations` gravado; `statistics`
    do primitivo sobre `sequence.violations`;
    `kupiec_pof_p_value`/`p_uc`/`p_ind` por `chi_square_sf(df=1)`, `p_cc` por
    `chi_square_sf(df=2)`; `min_violations` keyword-only sem default.
- **Critério de aceite (A6):**
  - fixture analítica pequena (≈ 12 posições, sem lacunas, I_1 = 0) com n_ij
    e as três LR calculadas **à mão no teste** (log-somas escritas no teste)
    (`trio_hand`, `pure_convention`); `lr_cc == lr_uc + lr_ind` (igualdade exata do campo) e
    `≈ −2·log[L(p)/L(Π̂_1)]` escrita direta no teste (1e-12) (`lr_cc_identity`);
  - `n11 = 0` (`[F, T, F, F, T, F]`: (1, 2, 2, 0)) aplicável e igual à forma
    de C&P §4.1 (`n11_zero`); sequência com I_1 = 1: n_1 puro = n01 + n11 exclui a
    primeira violação e `kupiec_pof` a inclui (valores diferentes, ambos
    conferidos à mão) (`first_observation`);
  - **lacunas no primitivo** (Checkpoint B T4): `christoffersen_statistics`
    sobre `[F, T, None, T, T, None, F, T]` → `transitions == (0, 2, 0, 1)`
    `== make_hit_sequence(...).transition_counts`, `n_observed = 6`,
    `n_violations = 4`, `kupiec_pof == kupiec_pof(violations=4,
    observations=6, …)` (`primitive_gaps`); consumo da contagem única provado por
    `monkeypatch` de `count_transitions` no namespace de
    `christoffersen_test` (`single_counting`);
  - um teste por status — NO_TRANSITIONS (`[T]`; e `[T, None, F, None, T]`),
    BELOW_MIN_VIOLATIONS, linha vazia (`[F, F, F, T]`, `min_violations=1`:
    n10 + n11 = 0), coluna vazia (`[T, F, F, F]`, `min_violations=1`:
    n01 + n11 = 0) (`status_each`) — e precedência (`[F]` com
    `min_violations=1` → NO_TRANSITIONS; `[F, F, F]` com `min_violations=1`
    → BELOW_MIN_VIOLATIONS, apesar da coluna vazia) (`status_precedence`);
  - **base da contagem do mínimo** (Checkpoint B T10): `[T, F, F, T, F]` com
    `min_violations=2` → APPLICABLE (`n_violations = 2`, embora
    `n01 + n11 = 1`) (`min_violations_base`);
  - sequência toda `None` → tudo `None`, status NO_TRANSITIONS
    (`all_masked_not_applicable`);
  - `horizon = 7` → `independence_descriptive is True`, sub-série DGT de
    h = 7 → `False` (`h7_descriptive`);
  - `evaluate` copia a identidade inteira da sequência (inclusive
    `dgt_offset`/`dgt_step` de uma sub-série) e grava `min_violations`
    (`copies_identity`);
  - **invariância hits ↔ violações** (I2, doc §7.1): para três sequências
    sem lacunas, `christoffersen_statistics(violations=[not v …],
    violation_rate=1 − p, min_violations=0)` dá `lr_uc`, `lr_ind`, `lr_cc` e
    `kupiec_pof` iguais (1e-12) aos de `(v, p)` (`hits_invariance`);
  - **piso**: `[T,T,T,T,T,T,T,F,F,T,F,T,F]` (transições (1, 2, 3, 6), LR_ind
    bruto medido em §1: −1.78e-15) dá `lr_ind == 0.0` e `p_ind == 1.0`
    (`lr_ind_floor`; se a implementação der ≥ 0, varrer e registrar em §7);
  - C4: `min_violations` −1, 1.5, `True` erguem (`min_violations_invalid`);
    `inspect.signature`: `min_violations` sem default em `evaluate` e no
    primitivo (`min_violations_signature`); C9 (`report_incoherent`): um caso por ramo dos dois
    `__post_init__` (cada uma das quatro desigualdades, `lr_cc` ≠ soma,
    estatística com status não aplicável e vice-versa, p-valor 1.5, p-valor
    sem estatística, `independence_descriptive` incoerente).
  - **Tokens:** `trio_hand`, `pure_convention`, `lr_cc_identity`, `n11_zero`,
    `first_observation`, `primitive_gaps`, `single_counting`, `status_each`,
    `status_precedence`, `min_violations_base`, `all_masked_not_applicable`,
    `h7_descriptive`, `copies_identity`, `hits_invariance`, `lr_ind_floor`,
    `min_violations_invalid`, `min_violations_signature`, `report_incoherent`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_christoffersen_test.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): ChristoffersenTest com trio puro e leitura Kupiec [6.3/task-07]`

---

### Task 08 — Sensibilidades pré-registradas: LR_uc de 3 estados e p-valor Monte Carlo

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/christoffersen_test.py`
  - `tests/unit/features/evaluation/test_christoffersen_test.py` (testes do
    3 estados)
- **Arquivos a criar:**
  - `tests/unit/features/evaluation/test_christoffersen_monte_carlo.py`
- **O que fazer (concept §4, I7, I8, I10, C3, C4, C5, C6, C9; ADRs 6.3.0005
  item 2, 6.3.0006 itens 1–7):**
  - `lr_uc_three_state(*, lower_count, upper_count, n, lower_rate,
    upper_rate) -> float` — valida (C3: finitos não-`bool`, contagens ≥ 0,
    `lower_count + upper_count <= n`, `n > 0`, taxas em (0, 1),
    `lower_rate + upper_rate < 1`); `−2·[ℓ(taxas) − ℓ(p̂)]` multinomial com
    `xlogy`; `floor_lr_statistic`.
  - `MonteCarloStatus`, `MonteCarloPValues` (frozen, `__post_init__`:
    p-valores em [0, 1]; `p_uc is None` ⇔ `uc_status != APPLICABLE`; idem
    `p_ind`/`p_cc` com `ind_status`; `uc_status` nunca é `MC_CAP_REACHED`;
    `uc_status == NOT_APPLICABLE` ⇒ `attempts == 0` e `ind_status ==
    NOT_APPLICABLE`; senão `draws <= attempts <= 100·draws`).
  - `mc_p_value(*, observed, simulated, uniforms, observed_uniform)` — kernel
    puro do ADR 6.3.0006 item 4 (G̃_N com `≤`, "=" e "≤" exatos; p̃ =
    (N·G̃_N + 1)/(N + 1)); valida `len(simulated) == len(uniforms) >= 1`.
  - `ChristoffersenTest.monte_carlo_p_values(sequence, *, min_violations,
    draws, seed)` — `draws`/`seed` `int` não-`bool` obrigatórios (C4); ergue
    primeiro em sub-série DGT e depois em `horizon > 1` (C5, mensagens
    distintas — decisão de detalhe do §1); sem LR_uc observado → tudo
    `None`, `NOT_APPLICABLE`, `attempts = 0`; senão a ordem de RNG do ADR
    item 5 (um `random.Random(seed)`; U_0; por tentativa um `random()` por
    posição observada na ordem — violação ⇔ `< violation_rate` —, depois o
    U_i), mesmas lacunas da sequência, cada sorteio pontuado por
    `christoffersen_statistics` com o mesmo `min_violations`; referência de
    LR_uc = N primeiros sorteios; de LR_ind/LR_cc = N primeiros
    **APPLICABLE**, teto 100·N → `MC_CAP_REACHED`; observado não
    APPLICABLE → `p_ind`/`p_cc` `None`, `ind_status = NOT_APPLICABLE` e
    nenhum redraw (`attempts == draws`).
- **Critério de aceite:**
  - **A7** (`test_christoffersen_test.py`, tokens `three_state_*`): valor à mão (log-somas no teste) em (7, 3, 200), taxas
    0.02/0.02 (`three_state_hand`); exatamente 0.0 (comparação `== 0.0`,
    que aceita o `-0.0` medido) em (4, 4, 200) (`three_state_zero`); p via
    `chi_square_sf(stat, df=2) == math.exp(-stat / 2)`
    (`three_state_chi2`); **contagem real**: (7.5, 3, 200) aceita e
    estritamente entre os valores em (7, 3, 200) e (8, 3, 200) — os dois
    vizinhos inteiros de `lower_count`, com `upper_count` e `n` fixos
    (medidos em §1: 2.1294 < 2.7357 < 3.4114) (`three_state_real_count`);
    **piso**: `lr_uc_three_state(lower_count=1, upper_count=3, n=6,
    lower_rate=1/6, upper_rate=0.5)` devolve exatamente `0.0` (bruto medido
    −1.78e-15) (`three_state_floor`); C3 (`three_state_invalid`, um caso por
    ramo, inclusive soma > n e taxas somando 1); **composição consumida pela
    6.5** (I10, Checkpoint B T22): numa série mista, com
    `lower = HitSequences.lower_tail(series, level=τ_l, tolerance=t)` e
    `upper = HitSequences.upper_tail(series, level=τ_u, tolerance=t)`,
    `lower.n_observed == upper.n_observed` e
    `lr_uc_three_state(lower_count=lower.n_violations,
    upper_count=upper.n_violations, n=lower.n_observed,
    lower_rate=lower.violation_rate, upper_rate=upper.violation_rate)` é
    finito e bate com o valor à mão das mesmas contagens
    (`three_state_composition`).
  - **A8** (`test_christoffersen_monte_carlo.py`):
    - `mc_p_value` em fixture à mão com empates — S_0 = 2.0,
      S = [1.0, 2.0, 2.0, 3.0], U = [0.3, 0.9, 0.1, 0.5], U_0 = 0.5 →
      G̃_N = 1 − 3/4 + 1/4 = 0.5, p̃ = 0.6; não-aleatorizado p̂ = 0.8 ≥ p̃
      (Dufour Eq. (2.33)); tamanhos diferentes/vazios erguem (`dufour_ties`);
    - determinismo: duas chamadas com a mesma (sequência, `seed`, N) dão o
      mesmo `MonteCarloPValues` (`mc_determinism`); **regressão congelada** — um
      (sequência, seed = 20260928, N = 199) fixo com `p_uc`, `p_ind`, `p_cc`
      e `attempts` literais no teste (medidos na execução; guardam a ordem de
      consumo do RNG) (`mc_regression`);
    - **referência condicionada — replay independente** (Checkpoint B T1;
      ADR 6.3.0006 item 3, `6.3-MC-COND`): fixture T = 40, p = 0.05,
      `min_violations=3`, observado APPLICABLE, N = 199, seed fixa. O teste
      reimplementa **no próprio teste** a ordem do ADR item 5
      (`random.Random(seed)`; U_0; por tentativa um `random()` por posição
      observada, depois U_i), pontua cada sorteio com
      `christoffersen_statistics`, guarda os N primeiros sorteios para LR_uc
      e os N primeiros **APPLICABLE** para LR_ind/LR_cc, e calcula os
      esperados com `mc_p_value`: `p_uc`, `p_ind`, `p_cc` e `attempts` da
      implementação **iguais** aos do replay; e o `p_ind` da referência **não
      condicionada** (N primeiros sorteios, inaplicáveis contados como
      LR_ind = 0 — Alternativa D do ADR), calculado no mesmo replay, é
      **diferente** do `p_ind` da implementação; `attempts > draws`
      (`conditioned_reference`). Se na fixture escolhida os dois p-valores coincidirem,
      trocar a seed e registrar em §7;
    - teto: T = 20, 10 violações observadas (matriz não degenerada),
      p = 0.01, `min_violations=10`, N = 5 → `ind_status == MC_CAP_REACHED`,
      `p_ind is None`, `p_cc is None`, `p_uc` presente, `attempts == 500`
      (`mc_cap_reached`);
    - LR_uc aplicável e LR_ind não (Checkpoint B T9): `[F]*10`,
      `min_violations=1` → `uc_status == APPLICABLE`, `ind_status ==
      NOT_APPLICABLE`, `p_ind`/`p_cc` `None`, `attempts == draws`
      (`uc_only`); LR_uc não aplicável (`[T]`) → `attempts == 0` e tudo
      `None` (`uc_not_applicable`);
    - `MonteCarloPValues` carrega `min_violations`, `draws`, `seed` e a
      identidade (`horizon`, `kind`, `levels`, `tolerance`,
      `includes_degenerate`) da sequência (`mc_carries_identity`);
    - envelope sem lacunas: T = 30, p = 0.1, N = 2 000 — p̃ de LR_uc em
      `[P(S > s₀) − ε, P(S ≥ s₀) + ε]`, com as probabilidades exatas de LR_uc
      sob Bern(p) calculadas no teste (n_1 puro ~ Binomial(29, p); soma de
      `comb(29, k)·p^k·(1−p)^(29−k)` sobre os k cujo LR_uc é > / ≥ s₀) e ε do
      ADR 6.3.0006 item 4 (`iid_envelope`); **envelope com lacunas** (Checkpoint
      B T4): a mesma verificação numa sequência de 34 posições com 4 `None`
      espalhados, com Binomial(nº de pares observados, p) — cada par tem a
      sua segunda posição distinta — e as mesmas lacunas nos sorteios
      (`gaps_envelope`);
    - C5: sub-série DGT (h = 7, mensagem de sub-série) e sequência h = 7 fora
      de sub-série (mensagem de horizonte) erguem, cada uma com `match=`
      próprio (`dgt_subseries_raises`, `horizon_raises`); C4: `draws` 0, 1.5, `True` (`invalid_draws`),
      `seed` 1.5, `True` (`invalid_seed`) erguem; `inspect.signature`: `draws`,
      `seed`, `min_violations` sem default (`mc_signature`); C9
      (`mc_incoherent`): um caso por ramo do `__post_init__`.
  - Custo medido com a implementação real (bloco `timeit` abaixo) registrado
    em §7 (`[decision]`; §1 traz o do protótipo).
  - **Tokens:** `test_christoffersen_test.py`: `three_state_hand`,
    `three_state_zero`, `three_state_chi2`, `three_state_real_count`,
    `three_state_floor`, `three_state_invalid`, `three_state_composition`;
    `test_christoffersen_monte_carlo.py`: `dufour_ties`, `mc_determinism`,
    `mc_regression`, `conditioned_reference`, `mc_cap_reached`, `uc_only`,
    `uc_not_applicable`, `mc_carries_identity`, `iid_envelope`,
    `gaps_envelope`, `dgt_subseries_raises`, `horizon_raises`,
    `invalid_draws`, `invalid_seed`, `mc_signature`, `mc_incoherent`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_christoffersen_test.py tests/unit/features/evaluation/test_christoffersen_monte_carlo.py -v --durations=5
  uv run python - <<'PY'
  import random, timeit
  from financial_forecasting.features.evaluation.domain.services.christoffersen_test import ChristoffersenTest
  from financial_forecasting.features.evaluation.domain.value_objects.hit_sequence import HitKind, HitSequence
  rng = random.Random(1)
  v = tuple(rng.random() < 0.05 for _ in range(1000))
  seq = HitSequence(horizon=1, kind=HitKind.LOWER_TAIL, levels=(0.05,), violation_rate=0.05,
                    target_timestamps=tuple(f"t{i:04d}" for i in range(1000)), violations=v,
                    tolerance=0.0, degeneracy_rate=0.0, includes_degenerate=False,
                    dgt_offset=None, dgt_step=None)
  print("MC T=1000 N=9999:", timeit.timeit(lambda: ChristoffersenTest.monte_carlo_p_values(
      seq, min_violations=2, draws=9999, seed=1), number=1), "s")
  PY
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): LR_uc de 3 estados e p-valor Monte Carlo com desempate de Dufour [6.3/task-08]`

---

### Task 09 — `VarDescriptive`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/var_descriptive.py`
  - `tests/unit/features/evaluation/test_var_descriptive.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, I2, I9, C7, C9; doc §7.5, conv. 24; ADR 6.3.0001
  item 5):** `VAR_DESCRIPTIVE_LABEL: Final = "VaR descritivo — sem claim de
  gestão de risco"`; `VarTailBacktest` (frozen, `__post_init__`: τ < 0.5 ⇒
  `LOWER_TAIL` e `var_level == 1.0 - level`; τ > 0.5 ⇒ `UPPER_TAIL` e
  `var_level == level`; τ = 0.5 ergue; `backtest.kind == kind` e
  `backtest.levels == (level,)`); `VarDescriptiveReport` (frozen,
  `__post_init__`: `label == VAR_DESCRIPTIVE_LABEL`, `tails` não-vazio, todo
  `backtest.horizon == horizon`); `VarDescriptive.backtest(series, *,
  tolerance, min_violations)` — um `VarTailBacktest` por τ ≠ 0.5 na ordem da
  grade, cada `backtest = ChristoffersenTest.evaluate(HitSequences.
  lower_tail/upper_tail(series, level=τ, tolerance=tolerance),
  min_violations=min_violations)`, só a variante mascarada. Nenhum cálculo
  novo (só re-rotulação e laço).
- **Critério de aceite (A9):** grade (0.02, 0.05, 0.5, 0.95, 0.98) → 4 caudas
  na ordem da grade, 0.02/0.05 `LOWER_TAIL`, 0.95/0.98 `UPPER_TAIL`
  (`grid_order`); `var_level == 0.98` para τ = 0.02 e para τ = 0.98 (igualdade
  exata, medida em §1) (`var_level`); cada `backtest` `==` o
  `ChristoffersenTest.evaluate(HitSequences.…)` montado no teste
  (`matches_evaluate`); `report.label == VAR_DESCRIPTIVE_LABEL` e
  `VarDescriptiveReport(..., label="VaR")` ergue (`descriptive_label`); série 100 %
  degenerada → toda cauda com `statistics.kupiec_pof is None` e status
  NO_TRANSITIONS (C7, `all_tails_not_applicable`); `report.horizon ==
  series.horizon` e horizonte divergente de uma cauda ergue (`var_horizon`); C9
  (`tail_incoherent`): `var_level` errado, `kind` trocado, τ = 0.5, `tails = ()`
  erguem; `tolerance`/`min_violations` keyword-only sem default
  (`var_signature`).
  **Tokens:** `grid_order`, `var_level`, `matches_evaluate`,
  `descriptive_label`, `all_tails_not_applicable`, `var_horizon`,
  `tail_incoherent`, `var_signature`.
- **Comando de verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_var_descriptive.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): VaR descritivo por cauda como re-rotulação dos backtests [6.3/task-09]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

---

### Task 10 — Unidade de fixture R `var_test_cases` (oráculo `rugarch::VaRTest` congelado)

- **Arquivos a criar:**
  - `tests/fixtures/r_oracle/Dockerfile` — exatamente as duas linhas do ADR
    6.2.0006 (`FROM rocker/r-ver:4.4.1` /
    `RUN install2.r --error --ncpus 4 forecast rugarch jsonlite`, com quebra
    de linha final; byte-idêntico ao da 6.2)
  - `tests/fixtures/r_oracle/var_test_cases.R`
  - `tests/fixtures/r_oracle/var_test_cases.json`
  - `tests/fixtures/r_oracle/var_test_cases.sessionInfo.txt`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept D3/D4, §8 Externas, A10, C8; ADRs 6.3.0002,
  6.3.0003, 6.2.0006 + regras do Step em §Pré-condições):**
  - **Gerador `var_test_cases.R`** (determinístico, `set.seed(20260928)`,
    RNG registrado pelo `sessionInfo()`): monta os casos, chama
    `rugarch::VaRTest(alpha = p, actual = ifelse(v == 1, -1, 1), VaR =
    rep(0, T))` em **dois feeds** — série inteira e a partir de t = 2
    (`v[-1]`) — com `tryCatch` gravando `conditionMessage` em caso de erro;
    grava `uc.LRstat` e `cc.LRstat` de cada *feed* bem-sucedido. **Para sem
    escrever** (`stopifnot`) diante de qualquer saída não-finita e de
    qualquer T > 500. Números: a taxa `p` (única entrada de ponto flutuante)
    como `{"dec": <%.17g>, "hex": "<%a>"}`, com
    `stopifnot(as.numeric(sprintf("%.17g", x)) == x)`; 0/1 das violações em
    JSON puro; saídas como número JSON por `sprintf("%.17g")` — **nunca**
    `toJSON(digits = NA)`: literais montados com `sprintf` (texto JSON à mão,
    ou `jsonlite::toJSON(..., json_verbatim = TRUE)` com
    `structure(sprintf(...), class = "json")`). Escreve também
    `var_test_cases.sessionInfo.txt` (`capture.output(sessionInfo())`). O
    gerador começa com `library(rugarch)` e `library(jsonlite)` (anexados:
    os dois aparecem em "other attached packages" do `sessionInfo()`, mesmo
    que o JSON seja montado à mão).
  - **`provenance`**: `generator` (`tests/fixtures/r_oracle/var_test_cases.R`,
    relativo ao repo), `image` (`rocker/r-ver:4.4.1`, igual ao `FROM` do
    `Dockerfile`), `r_version` (`paste(R.version$major, R.version$minor,
    sep = ".")`), `packages` (`rugarch`, `jsonlite` →
    **`packageDescription(p)$Version`**, ex. `1.5-3`), `cran_snapshot`
    (`getOption("repos")` no container), `generated_at` (`format(Sys.Date())`, `AAAA-MM-DD`),
    `session_info` (`var_test_cases.sessionInfo.txt`, **relativo ao JSON**),
    `command` (ver abaixo) + a chave específica da 6.3 **`t_max: 500`**
    (concept A10). Conferir o `dm_test_cases.json` e o teste de proveniência
    da 6.2 (worktree irmã) antes de gerar.
  - **Casos** (`cases`: `id`, `description`, `category`, `violation_rate`
    {dec, hex}, `violations` [0/1], `whole` e `from_t2`, cada um
    `{uc_lrstat, cc_lrstat}` **ou** `{error}`), no mínimo:
    - `iid` — Bern(p) para p ∈ {0.01, 0.02, 0.05, 0.1} × T ∈ {100, 250,
      500}, só os com ambos os *feeds* válidos (re-sortear com a seed
      seguinte, registrada na `description`, se o R falhar);
    - `clustered` — cadeia de Markov com π11 alto (ex.: π01 = p/2,
      π11 = 0.3) para p ∈ {0.02, 0.05, 0.1}, T ∈ {250, 500};
    - `first_violation` — I_1 = 1 forçado, ≥ 3 casos, ≥ 1 com
      |`uc`(t ≥ 2) − `uc`(inteira)| > 0.1 (sonda do ADR 6.3.0003: Bern(0.05),
      T = 250 → 0.185 vs 0.021);
    - `n11_zero` — violações isoladas (sem 1→1), ambos *feeds* válidos
      (0^0 = 1 do R), incluindo um caso com violação isolada em t = 1 e outro
      em t = T com *feed* inteiro válido;
    - `r_error` — zero violações; todas violações; uma única violação em
      t = 1; uma única em t = T; violações só em t = 1 e t = T (gravar o que
      o R devolver em cada *feed*).
  - **Geração (Host, raiz da worktree)** — o literal efetivamente executado
    fica em `provenance.command`, passado ao gerador pela variável
    `FF_R_ORACLE_COMMAND` (o gerador faz `stopifnot(nzchar(...))` e grava o
    valor; o literal gravado omite só o próprio `-e` que o transporta):
    ```bash
    docker build -t ff-r-oracle:4.4.1 tests/fixtures/r_oracle
    CMD="docker run --rm -v \"$(pwd -W)/tests/fixtures/r_oracle:/work\" -w /work ff-r-oracle:4.4.1 Rscript var_test_cases.R"
    MSYS_NO_PATHCONV=1 docker run --rm -e FF_R_ORACLE_COMMAND="$CMD" \
      -v "$(pwd -W)/tests/fixtures/r_oracle:/work" -w /work ff-r-oracle:4.4.1 Rscript var_test_cases.R
    ```
- **Critério de aceite (A10, parte fixture; C8):** o `Dockerfile` é
  byte-idêntico às duas linhas; a pré-checagem local abaixo passa — ela
  **não** substitui nem duplica o teste de proveniência da 6.2 (não vira
  arquivo de teste; é o check desta Task até a 6.2 estar em `develop`) e
  cobre o que esse teste exige (campos, `session_info` relativo ao JSON,
  `generated_at` `AAAA-MM-DD`, `r_version == "4.4.1"`, `image` == `FROM`,
  `R version <v> (` e cada `<pkg>_<versão>` delimitado por espaço/fim no
  `sessionInfo`, caminhos relativos, violações `int` 0/1 (não `bool` JSON),
  `library(jsonlite)` no gerador, round-trip dec ↔ hex).
- **Comando de verificação — Host:**
  ```bash
  printf 'FROM rocker/r-ver:4.4.1\nRUN install2.r --error --ncpus 4 forecast rugarch jsonlite\n' | cmp - tests/fixtures/r_oracle/Dockerfile
  python - <<'PY'
  import json, math, pathlib, re
  j_path = pathlib.Path("tests/fixtures/r_oracle/var_test_cases.json")
  j = json.loads(j_path.read_text(encoding="utf-8"))
  p = j["provenance"]
  need = {"generator", "image", "r_version", "packages", "cran_snapshot",
          "generated_at", "session_info", "command", "t_max"}
  assert need <= p.keys(), need - p.keys()
  assert p["t_max"] == 500 and p["r_version"] == "4.4.1"
  for key in ("generator", "session_info"):
      assert not p[key].startswith(("/", "\\")) and not re.match(r"^[A-Za-z]:", p[key]), (key, p[key])
  frm = (j_path.parent / "Dockerfile").read_text(encoding="utf-8").splitlines()[0]
  assert frm == f"FROM {p['image']}", (frm, p["image"])
  gen = pathlib.Path(p["generator"])
  assert gen.is_file(), p["generator"]
  assert re.search(r'library\(jsonlite\)|loadNamespace\("jsonlite"\)', gen.read_text(encoding="utf-8"))
  assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["generated_at"]), p["generated_at"]
  si = (j_path.parent / p["session_info"]).read_text(encoding="utf-8")
  assert f"R version {p['r_version']} (" in si, p["r_version"]
  for k, v in p["packages"].items():
      assert re.search(rf"(^|\s){re.escape(k)}_{re.escape(v)}(\s|$)", si), (k, v)
  assert "rugarch" in p["packages"] and "jsonlite" in p["packages"]
  assert "ff-r-oracle:4.4.1" in p["command"] and "Rscript var_test_cases.R" in p["command"]
  cats = {}
  for c in j["cases"]:
      r = c["violation_rate"]
      assert set(r) == {"dec", "hex"} and float(r["dec"]) == float.fromhex(r["hex"]), c["id"]
      assert all(type(x) is int and x in (0, 1) for x in c["violations"]), c["id"]  # int, nunca bool
      assert 2 <= len(c["violations"]) <= p["t_max"], c["id"]
      for feed in ("whole", "from_t2"):
          f = c[feed]
          assert ("error" in f) != ("uc_lrstat" in f), (c["id"], feed)
          assert all(math.isfinite(f[k]) for k in ("uc_lrstat", "cc_lrstat") if k in f), c["id"]
      cats[c["category"]] = cats.get(c["category"], 0) + 1
  assert {"iid", "clustered", "first_violation", "n11_zero", "r_error"} <= cats.keys(), cats
  gap = [c["id"] for c in j["cases"] if c["violations"][0] == 1 and "uc_lrstat" in c["whole"]
         and "uc_lrstat" in c["from_t2"] and abs(c["from_t2"]["uc_lrstat"] - c["whole"]["uc_lrstat"]) > 0.1]
  assert gap, "nenhum caso I_1 = 1 com |uc(t>=2) - uc(inteira)| > 0.1"
  print("ok", cats, "I_1=1 com gap:", gap)
  PY
  ```
  **Container:** `make check-task SLICE=evaluation`.
- **Commit sugerido:** `test(evaluation): fixture R var_test_cases do rugarch VaRTest com proveniência [6.3/task-10]`

---

### Task 11 — Testes de integração contra o oráculo R congelado

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/_var_test_cases.py` — carregador:
    lê `tests/fixtures/r_oracle/var_test_cases.json` (caminho a partir de
    `Path(__file__)`), devolve casos tipados (dataclasses frozen:
    `violations` como `tuple[bool, ...]`, taxa por `float.fromhex(hex)`,
    *feeds* com `uc`/`cc` ou `error`) e o `provenance`. Importado
    absolutamente pelos testes
    (`from tests.integration.features.evaluation._var_test_cases import …`).
  - `tests/integration/features/evaluation/test_kupiec_vs_oracle.py`
  - `tests/integration/features/evaluation/test_christoffersen_vs_rugarch.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept A10, I12, C8; ADRs 6.3.0002 item 4, 6.3.0003):**
  `pytestmark = pytest.mark.integration`; `_ORACLE_ABS_TOL = 1e-10`
  declarado em cada módulo (arredondamento; nunca O(1/T)); testes
  parametrizados por `id` do caso.
  - `test_kupiec_vs_oracle.py` (`kupiec_whole_feed`): para todo caso com *feed* inteiro
    válido, `kupiec_pof(violations=x, observations=T, violation_rate=p)` e
    `christoffersen_statistics(...).kupiec_pof` == `whole.uc_lrstat`
    (1e-10).
  - `test_christoffersen_vs_rugarch.py`, com `min_violations=0`:
    - `trio_two_feeds` — todo caso com os dois *feeds* válidos: `lr_uc` puro ==
      `from_t2.uc_lrstat`; `lr_ind` == `whole.cc_lrstat −
      whole.uc_lrstat`; `lr_cc` == a soma (1e-10);
    - `lr_ind_whole_feed` (Checkpoint B T14) — **todo** caso com *feed* inteiro
      válido, mesmo com o t ≥ 2 falhando (cobre `n11_zero` com violação em
      t = 1 e em t = T): `lr_ind` == `whole.cc_lrstat − whole.uc_lrstat`;
    - `r_error_policy` — política sobre **todos** os casos: *feed* inteiro com erro
      ⇔ `christoffersen_statistics(violations, …, min_violations=0)
      .independence_status != APPLICABLE`, e *feed* t ≥ 2 com erro ⇔ o mesmo
      sobre `violations[1:]` (a matriz de transição perde um símbolo
      exatamente onde o `table(head, tail)` do R perde — ADR 6.3.0001 item
      7); nesses casos `lr_ind is None` e `kupiec_pof` segue definido (x = 0
      → `−2·T·log(1 − p)`); nenhum valor de *feed* com erro é usado como
      esperado (C8);
    - `first_violation_gap` — ≥ 1 caso `first_violation` com
      |`from_t2.uc` − `whole.uc`| > 0.1 **e** o domínio reproduz os dois
      lados (o puro bate com t ≥ 2, o POF com a inteira — a convenção
      importa);
    - `fixture_guard` — todo caso com T ≤ `provenance["t_max"]` == 500; cada
      categoria do gerador presente.
- **Critério de aceite (A10, I12):** os dois módulos verdes em todos os
  casos, zero `SKIPPED` (provado no mesmo shell); nenhum
  `tests/unit/features/evaluation/**` lê arquivo; nenhuma mudança em
  `src/**/adapters/` nem em `application/ports/` (`git diff --quiet`).
  **Tokens:** `test_kupiec_vs_oracle.py`: `kupiec_whole_feed`;
  `test_christoffersen_vs_rugarch.py`: `trio_two_feeds`, `lr_ind_whole_feed`,
  `r_error_policy`, `first_violation_gap`, `fixture_guard`.
- **Comando de verificação (T1) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/integration/features/evaluation/test_kupiec_vs_oracle.py tests/integration/features/evaluation/test_christoffersen_vs_rugarch.py -v -rs | tee "$f"
  test -s "$f"
  ! grep -q "SKIPPED" "$f" || exit 1
  grep -q "passed" "$f"
  make check-task SLICE=evaluation
  ```
  **Host:**
  ```bash
  test -d tests/unit/features/evaluation
  ! grep -rnE "r_oracle|read_text|open\(" tests/unit/features/evaluation/ || exit 1
  git diff --quiet origin/develop...HEAD -- 'src/financial_forecasting/features/*/adapters/*' 'src/financial_forecasting/features/*/application/ports/*'
  ```
- **Commit sugerido:** `test(evaluation): Christoffersen e Kupiec contra o rugarch congelado por dois feeds [6.3/task-11]`

---

### Task 12 — Roadmap (6.3 e 6.5), doc de domínio e overview

- **Arquivos a modificar:**
  - `docs/roadmap.md`
  - `docs/domain/evaluation/probabilistic-forecast-evaluation.md`
  - `docs/overview.md`
- **Arquivos a criar:** nenhum.
- **Antes de editar:** `git fetch origin && git rebase origin/develop` (a 6.2
  edita os mesmos três arquivos — §5).
- **O que fazer (concept §1 "Redação do roadmap", D2, A13; ADRs 6.3.0001
  item 6, 6.3.0002 item 5, 6.3.0003, 6.3.0005, 6.3.0006):**
  - **Roadmap, linha da 6.3** (bloco `#### Stage 6.3` e a linha da tabela de
    Stages): descrição humana sem o vocabulário órfão ("Gate D", "C.0",
    "DELETAR …", "DESCRIPTIVE MPIW/win-rate"); `camada_alvo: domain` (bloco
    e tabela); `arquivos_a_criar` conforme D2 (três serviços do roadmap +
    `value_objects/hit_sequence.py`, `services/{hit_sequences.py,
    wilson_band.py, chi_square.py}`; os dois testes de oráculo em
    `tests/integration/features/evaluation/`; a unidade
    `tests/fixtures/r_oracle/var_test_cases.{json,R,sessionInfo.txt}` + o
    `Dockerfile` do Step; **sem** `adapters/out/inference/…`; tocados
    `coverage_series.py`/`coverage_metrics.py`); `contratos_introduzidos`
    conforme D2 (`HitSequence`, `HitSequences`, `WilsonBand`,
    `chi_square_sf`, `kupiec_pof` (kernel — **não** mais `KupiecPof`),
    `ChristoffersenTest`, `lr_uc_three_state`, `MonteCarloPValues`/
    `mc_p_value`, `VarDescriptive`, predicados FA7 `is_at_or_below`/
    `is_inside_closed`, `MPIW_LABEL`);
    `contratos_consumidos` conforme D2 (`CoverageSeries`,
    `pair_miscoverage`, `DegeneracyGate`, `CoverageReport`/`PairCoverage`,
    `is_finite_number`); `definition_of_done` = o texto do "DoD reescrito"
    do concept §11.
  - **Roadmap, linha da 6.5:** `contratos_consumidos` passa a listar
    `WilsonBand`, `kupiec_pof`, `lr_uc_three_state`, `chi_square_sf`,
    `ChristoffersenTest`, `HitSequences` (6.3), com a composição do 3
    estados registrada (Checkpoint B T22): contagens de
    `HitSequences.lower_tail(τ_l)`/`upper_tail(τ_u)` (`n_violations`) sobre
    o mesmo `n_observed` (I10; ADR 6.3.0005 item 2) — preservando o que a 6.2
    tiver editado na mesma linha.
  - **Doc de domínio** (mecânica, nenhuma convenção mudada): §7.6 — desempate
    aleatorizado de Dufour (G̃_N com ≤) e referência de LR_ind/LR_cc
    condicionada ao evento de aplicabilidade do observado, apontando o ADR
    6.3.0006; §10.1 — os registros `[decision:E] 6.3-MC-TIES` e
    `[decision:E] 6.3-MC-COND` (texto do ADR 6.3.0006) e a linha 22 da
    tabela §10 citando Dufour 2006 e o ADR 6.3.0006; §7.7, §11.3 (bullet
    `rugarch::VaRTest`, "Neutralizar") e linha 21 da tabela (conv. 21) —
    receita dos dois *feeds* (LR_uc ↔ `uc` do *feed* a partir de t = 2;
    LR_ind ↔ `cc − uc` do *feed* inteiro; ADR 6.3.0003) e a delimitação do
    escopo da conv. 21 (só o trio 2-estados; POF, Wilson e LR_uc de 3 estados
    sobre todas as posições observadas; ADR 6.3.0005); §11.2 — Dufour (2006)
    e Berkowitz, Christoffersen & Pelletier (2011) com DOI.
  - **Overview §10:** Dufour (2006) e BCP (2011) com DOI.
- **Critério de aceite (A13):** cada (arquivo, seção, termo) do bloco abaixo
  casa isoladamente (um `grep -q` por par — nenhum grep multi-arquivo);
  `make docs-check` verde; nenhuma linha de teoria/convenção alterada além
  das citadas (revisão do diff).
- **Comando de verificação — Host:**
  ```bash
  D=docs/domain/evaluation/probabilistic-forecast-evaluation.md
  test -s "$D" && test -s docs/roadmap.md && test -s docs/overview.md
  R63() { sed -n '/^#### Stage 6.3/,/^#### Stage 6.4/p' docs/roadmap.md; }
  R65() { sed -n '/^#### Stage 6.5/,/^---$/p' docs/roadmap.md; }
  sec() { sed -n "/^$1/,/^$2/p" "$D"; }
  has() { grep -qF -- "$2" <<<"$1" || { echo "FALTA: $3 :: $2"; exit 1; }; }
  ! R63 | grep -nE "Gate D|C\.0|DELETAR|DESCRIPTIVE|KupiecPof|r_backtest_oracle_fixtures|adapters/out" || exit 1
  B63=$(R63)
  for t in "camada_alvo: domain" "value_objects/hit_sequence.py" "hit_sequences.py" "wilson_band.py" "chi_square.py" \
           "tests/integration/features/evaluation/test_christoffersen_vs_rugarch.py" \
           "tests/integration/features/evaluation/test_kupiec_vs_oracle.py" "var_test_cases" "Dockerfile" \
           "HitSequence" "WilsonBand" "chi_square_sf" "kupiec_pof" "lr_uc_three_state" "mc_p_value" \
           "MonteCarloPValues" "MPIW_LABEL" "is_at_or_below" "DegeneracyGate" "is_finite_number" \
           "pair_miscoverage" "aceita contagens médias" "LR_ind = cc − uc"; do has "$B63" "$t" "roadmap 6.3"; done
  grep -qF '| `6.3-calibration-risk-backtests` | evaluation | domain |' docs/roadmap.md
  B65=$(R65)
  for t in WilsonBand kupiec_pof lr_uc_three_state chi_square_sf ChristoffersenTest HitSequences upper_tail n_observed; do has "$B65" "$t" "roadmap 6.5"; done
  S76=$(sec '### 7.6' '### 7.7'); has "$S76" "desempate" "doc §7.6"; has "$S76" "6.3.0006" "doc §7.6"
  S77=$(sec '### 7.7' '## 8'); has "$S77" "6.3.0003" "doc §7.7"; has "$S77" "cc − uc" "doc §7.7"
  S101=$(sec '### 10.1' '## 11'); has "$S101" "6.3-MC-TIES" "doc §10.1"; has "$S101" "6.3-MC-COND" "doc §10.1"
  L21=$(grep -E '^\| 21 \|' "$D"); has "$L21" "6.3.0005" "conv. 21"; has "$L21" "6.3.0003" "conv. 21"
  L22=$(grep -E '^\| 22 \|' "$D"); has "$L22" "Dufour" "linha 22"; has "$L22" "6.3.0006" "linha 22"
  S112=$(sec '### 11.2' '### 11.3'); has "$S112" "10.1016/j.jeconom.2005.06.007" "doc §11.2"; has "$S112" "10.1287/mnsc.1080.0964" "doc §11.2"
  S113=$(sed -n '/^### 11.3/,$p' "$D" | grep -F 'rugarch::VaRTest'); has "$S113" "6.3.0003" "doc §11.3"
  O10=$(sed -n '/^## 10\./,/^## 11\./p' docs/overview.md)
  has "$O10" "10.1016/j.jeconom.2005.06.007" "overview §10"; has "$O10" "10.1287/mnsc.1080.0964" "overview §10"
  ```
  **Container:** `make docs-check`.
- **Commit sugerido:** `docs(evaluation): roadmap 6.3/6.5 e receitas de oráculo e MC no doc de domínio [6.3/task-12]`

> **Checkpoint C (T2) após esta Task:** `make check-block` (Container).

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 6.3: complete` e ser mergeada em `develop`. Antes: `git fetch` +
> `git rebase origin/develop` (§5).

### Verificações automatizadas

**Container** (um único shell, convenção do §1):
```bash
make check                 # ruff + mypy strict + check_layout + lint-imports + fake-parity + port-coverage + docs-check + testes (cov >= 90%)

# A14 — cobertura por arquivo do slice (gera e lê o JSON no mesmo shell; exit 1 se algum arquivo < 90%)
cov=$(mktemp --suffix=.json)
uv run pytest --cov=financial_forecasting --cov-report=json:"$cov" -q
test -s "$cov"
uv run python - "$cov" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["files"]
ev = [f for f in d if "features/evaluation/" in f.replace(chr(92), "/")]
bad = {f: d[f]["summary"]["percent_covered"] for f in ev if d[f]["summary"]["percent_covered"] < 90}
print(len(ev), "arquivos do slice; abaixo de 90%:", bad)
sys.exit(1 if bad or not ev else 0)
PY

# A10 — oráculo R, zero skips (arquivo produzido e lido no mesmo shell)
f=$(mktemp)
uv run pytest tests/integration/features/evaluation/test_kupiec_vs_oracle.py tests/integration/features/evaluation/test_christoffersen_vs_rugarch.py -v -rs | tee "$f"
test -s "$f"
! grep -q "SKIPPED" "$f" || exit 1

# A10 / C8 — teste de proveniência da 6.2 sobre var_test_cases.json: BLOQUEANTE de merge
if [ -f tests/integration/features/evaluation/test_r_oracle_provenance.py ]; then
  uv run pytest tests/integration/features/evaluation/test_r_oracle_provenance.py -v
else
  echo "PENDENTE: A10/C8 — teste de proveniência da 6.2 ausente; A10 desmarcado, merge bloqueado até a 6.2 em develop"
fi

# A12 — sem aresta nova
uv run lint-imports

# Matriz I*/C* — cada token casa >= 1 teste do arquivo (coleta uma vez por arquivo; token casado
# contra o nome após o '::' sem o '[...]', substring sem distinção de caixa, como o -k)
U=tests/unit/features/evaluation; I=tests/integration/features/evaluation
while read -r file toks; do
  test -s "$file"
  # tokens únicos e nenhum substring de outro do mesmo arquivo (senão a prova é vácua)
  for a in $toks; do for b in $toks; do
    [ "$a" = "$b" ] || [[ "$b" != *"$a"* ]] || { echo "token '$a' contido em '$b' ($file)"; exit 1; }
  done; done
  # nomes sem o id de parametrização '[...]'
  ids=$(uv run pytest --co -q "$file" </dev/null | grep '::' | sed 's/^[^:]*:://; s/\[.*//' | sort -u)
  test -n "$ids"
  for t in $toks; do grep -qi -- "$t" <<<"$ids" || { echo "sem teste '$t' em $file"; exit 1; }; done
done <<LIST
$U/test_coverage_series.py fa7_at_or_below fa7_inside_closed
$U/test_coverage_metrics.py consumes_fa7_predicates mpiw_label
$U/test_chi_square.py chi2_critical chi2_floor chi2_invalid
$U/test_kupiec_pof.py kupiec_expression kupiec_table2 kupiec_region kupiec_real_count kupiec_floor kupiec_invalid
$U/test_wilson_band.py wilson_bcd wilson_region wilson_equivariance wilson_real_count wilson_not_applicable wilson_horizon wilson_nominal wilson_invalid wilson_incoherent
$U/test_hit_sequence.py hitseq_invalid kind_rate mask_gaps gap_transitions dgt_partition hitseq_horizon
$U/test_hit_sequences.py fa7_ties grid_rates gate_mask without_gaps_variant all_none_when_degenerate count_identities scores_guardrail consumes_predicates unknown_pair_or_level invalid_tolerance tolerance_signature
$U/test_christoffersen_test.py trio_hand pure_convention lr_cc_identity n11_zero first_observation primitive_gaps single_counting status_each status_precedence min_violations_base all_masked_not_applicable h7_descriptive copies_identity hits_invariance lr_ind_floor min_violations_invalid min_violations_signature report_incoherent three_state_hand three_state_zero three_state_chi2 three_state_real_count three_state_floor three_state_invalid three_state_composition
$U/test_christoffersen_monte_carlo.py dufour_ties mc_determinism mc_regression conditioned_reference mc_cap_reached uc_only uc_not_applicable mc_carries_identity iid_envelope gaps_envelope dgt_subseries_raises horizon_raises invalid_draws invalid_seed mc_signature mc_incoherent
$U/test_var_descriptive.py grid_order var_level matches_evaluate descriptive_label all_tails_not_applicable var_horizon tail_incoherent var_signature
$I/test_kupiec_vs_oracle.py kupiec_whole_feed
$I/test_christoffersen_vs_rugarch.py trio_two_feeds lr_ind_whole_feed r_error_policy first_violation_gap fixture_guard
LIST
```

**Host** (Git Bash, raiz da worktree):
```bash
printf 'FROM rocker/r-ver:4.4.1\nRUN install2.r --error --ncpus 4 forecast rugarch jsonlite\n' | cmp - tests/fixtures/r_oracle/Dockerfile

# A12 — nada a deletar
test -d src/financial_forecasting/features/evaluation
! grep -rnwE "prob_up|expected_move|win_?rate|winrate|downside|expected_shortfall|confidence" src/financial_forecasting/features/evaluation/ || exit 1

# I11 / D9 — arquivos que esta Stage não toca; nada de R fora das fixtures
git diff --quiet origin/develop...HEAD -- .importlinter pyproject.toml uv.lock docs/LAYOUT.md
git diff --quiet origin/develop...HEAD -- 'src/financial_forecasting/features/*/adapters/*' 'src/financial_forecasting/features/*/application/ports/*'
! git diff --name-only origin/develop...HEAD | grep -q "student_t.py" || exit 1
! git diff --name-only origin/develop...HEAD | grep '\.R$' | grep -v '^tests/fixtures/r_oracle/' || exit 1
test -d tests/unit/features/evaluation
! grep -rnE "r_oracle|read_text|open\(" tests/unit/features/evaluation/ || exit 1

# A14 — ADRs; §7 do technical; issue
test -z "$(grep -L '^status: accepted' docs/adr/6_3_000*.md)"
python scripts/check_technical_postexec.py docs/stages/6.3-calibration-risk-backtests/technical.md
python scripts/check_stage_issue.py
```

(A saída dos comandos de A14, A10 — inclusive a linha do teste da 6.2 ou o
`PENDENTE` —, A12 e do laço de tokens é colada no PR.)

### Verificações funcionais
- [ ] Para uma `CoverageSeries` sintética mista, `HitSequences` +
      `WilsonBand`/`ChristoffersenTest`/`VarDescriptive` devolvem relatórios
      autodescritivos (horizonte, tolerância, taxa de degeneração, variante,
      identidade DGT) coerentes com o `CoverageReport` da mesma série (A2).
- [ ] O trio puro e o POF batem com o `rugarch` congelado a menos de
      arredondamento, e os casos em que o R falha são "não aplicável" no
      domínio (A10).
- [ ] Sem verificação end-to-end com dado real: a Stage não persiste nem
      expõe número (concept D8); o e2e sobre o silver é da 6.4.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com o seu T1 verde; Checkpoints C
      (T2) após 03, 06, 09 e 12.
- [ ] `make check` verde no branch (após rebase em `origin/develop`).
- [ ] Cobertura ≥ 90 % global e por arquivo do slice (A14), saída colada.
- [ ] Laço de tokens da matriz I*/C* verde, saída colada.
- [ ] **A10:** teste de proveniência da 6.2 verde sobre `var_test_cases.json`.
      Se o gate imprimir `PENDENTE`: `[finding]` em §7, A10 **desmarcado** no
      PR e merge bloqueado até a 6.2 estar em `develop` e o teste rodar
      verde nesta branch rebaseada.
- [ ] §7 reflete a execução real (decisões de detalhe do §1, custo do MC
      medido, valores congelados, entradas do piso).
- [ ] Commit final `stage 6.3: complete` aplicado (pós-auditoria).
- [ ] `roadmap.md`: Stage 6.3 marcada `done`, `updated_at` e
      `last_reviewed_at` no fechamento.
- [ ] ADRs 6.3.0001–0006 em `accepted`.
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

```
Task 01 (FA7) ─► Task 02 (MPIW_LABEL)
Task 03 (χ² + piso + kupiec_pof)      Task 04 (Wilson; só stdlib)
Task 05 (HitSequence + count_transitions) ─┬─► Task 06 (HitSequences; usa 01 + gate da 6.1)
Task 03 ───────────────────────────────────┴─► Task 07 (ChristoffersenTest) ─► Task 08 (3 estados + MC; usa 06 no teste de composição)
Tasks 06, 07 ─► Task 09 (VarDescriptive)
Task 10 (fixture R; independente do código)
Tasks 03, 07, 10 ─► Task 11 (integração contra o R)
Tasks 01–11 ─► Task 12 (docs descrevem o que existe; rebase antes)
```

- A Task 02 vem depois da 01 porque ambas editam `coverage_metrics.py` e
  `test_coverage_metrics.py` (commits limpos em sequência).
- A Task 04 não depende de nenhuma outra; fica logo após a 03 para agrupar os
  kernels.
- A Task 06 depende da 01 (predicados) e da 05 (VO); a 07 depende da 03
  (`kupiec_pof`, `chi_square_sf`, piso, `xlogy`) e da 05
  (`count_transitions`); a 08 usa a 06 no teste de composição do 3 estados.
- A Task 10 pode rodar em qualquer ponto; fica antes da 11 para que o teste
  nasça com a fixture presente.
- A Task 12 fecha: o roadmap descreve arquivos e contratos que já existem.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Entrada medida do piso (§1) dar LR bruto ≥ 0 com a ordem de operações real | Varrer entradas vizinhas (taxas = contagens/n; π̂01 = π̂11) até achar LR ∈ [−1e-9, 0); registrar entrada e valor em §7 `[decision]`; o piso segue testado direto no helper |
| Replay condicionado ≡ não condicionado na fixture do A8 (`conditioned_reference`) | Trocar a seed/fixture até os dois p-valores diferirem; registrar em §7 — o teste exige a diferença |
| `rugarch` falhar num caso `iid`/`clustered` sorteado | Gerador re-sorteia com a seed seguinte (registrada na `description`); caso de erro só entra na categoria `r_error` |
| `sessionInfo`/`provenance` divergirem do que o teste da 6.2 exige | Regras do Step em §Pré-condições (versão por `packageDescription`, `session_info` relativo ao JSON); conferir o `dm_test_cases.json` e o teste da 6.2 na worktree irmã antes de gerar; se o teste reprovar depois do rebase, corrigir gerador/JSON em `[6.3/task-10-fix]` |
| **Mapa de conflitos com a 6.2** (Checkpoint B T21): `docs/roadmap.md` (linhas adjacentes 6.2/6.3 da tabela de Stages; bloco da 6.5), `docs/domain/evaluation/probabilistic-forecast-evaluation.md` (§10 tabela, §10.1, §11.2, §11.3 — a 6.2 edita os mesmos blocos para DM/MCS), `docs/overview.md` (§7/§8 pela 6.2, §10 pelas duas), `tests/fixtures/r_oracle/Dockerfile` | `git fetch && git rebase origin/develop` **antes da Task 12** e de novo no PR (GIT-WORKFLOW Etapa 4); resolver à mão mantendo as duas edições; o `Dockerfile` é byte-idêntico (add/add igual não conflita); rerodar os greps da Task 12 depois de cada rebase |
| MC lento nos testes unitários | N ≤ 2 000 e T ≤ 40 nos testes (envelope e condicionada); regressão com N = 199; `--durations=5` e `timeit` na Task 08 mostram o custo |
| Envelope do MC falhar | ε do ADR 6.3.0006 ≈ 4 desvios-padrão + 1/(N+1); seed fixa torna o teste determinístico — se falhar, é bug, não azar |
| Cobertura < 90 % nos ramos dos `__post_init__` | Um teste por ramo (C1/C9); `# pragma: no cover` só comentado e em ramo comprovadamente inalcançável |
| `grep -w confidence` pegar prosa em docstring | Docstrings em PT ("nível da banda"); o A12 é estrito (zero ocorrências no slice) |
| `jsonlite` truncar dígitos | Literais montados por `sprintf("%.17g")`/`%a`; pré-checagem da Task 10 confere `float(dec) == float.fromhex(hex)` |
| Verde falso por shell (`!` sob `set -e`, arquivo em outro `docker run`) | Convenção Container/Host do §1: um shell por bloco, `! cmd || exit 1`, `test -s` antes de ler |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo, contratos (§4), invariantes (§5),
  erros (§6), decisões D1–D10 (§7), integrações (§8), critérios (§11).
- ADRs desta Stage:
  [`6.3.0001`](../../adr/6_3_0001-violation-sequence-and-single-lr-service.md),
  [`6.3.0002`](../../adr/6_3_0002-rugarch-oracle-frozen-as-test-fixtures.md),
  [`6.3.0003`](../../adr/6_3_0003-pure-convention-oracle-comparison-by-two-feeds.md),
  [`6.3.0004`](../../adr/6_3_0004-mask-gaps-break-transitions.md),
  [`6.3.0005`](../../adr/6_3_0005-count-kernels-accept-mean-counts.md),
  [`6.3.0006`](../../adr/6_3_0006-monte-carlo-p-value-dufour-tie-breaking.md);
  relacionados: [`0.0.0011`](../../adr/0_0_0011-preregistration-invariants-and-h1-gate.md),
  [`0.0.0020`](../../adr/0_0_0020-statistics-in-domain-over-value-objects.md),
  [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md),
  [`0.0.0055`](../../adr/0_0_0055-tiered-quality-gates.md),
  [`6.1.0004`](../../adr/6_1_0004-coverage-metrics-recomputes-degeneracy-mask.md);
  ADR 0.0.0056 e ADR 6.2.0006 (PR da 6.2 — sem link, ainda fora desta branch).
- Doc de domínio: [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md).
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7; [`../../PIPELINE.md`](../../PIPELINE.md) §4.3;
  [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) §Gates em camadas.
- Skills: `task-ordering-hex`, `hex-arch-python`, `ddd-tactical-patterns`,
  `pytest-with-fakes`.
- Stage de referência: [`../6.1-scoring-and-calibration-metrics/technical.md`](../6.1-scoring-and-calibration-metrics/technical.md).
- `arch` 8.0.0 (sdist PyPI, lido nesta Fase 3B — §1 Estratégia).

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a Fase 4. Apenas esta seção é editável após
> `status: done`. Cada entrada carrega data + autor.

<!-- END: post-execution -->
