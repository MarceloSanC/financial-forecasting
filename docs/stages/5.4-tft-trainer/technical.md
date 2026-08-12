---
title: Technical — Trainer do TFT quantílico
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, tft-trainer, pytorch-forecasting, optuna, mlflow]
status: done
created_at: 2026-08-09
updated_at: 2026-08-11
stage_id: 5.4-tft-trainer
stage_title: Trainer do TFT quantílico
step_id: 5
step_title: Modelagem e harness de walk-forward
depends_on: [5.1-walk-forward-harness]
concept_ref: ./concept.md
issue_id: 57
branch: feat/57-5-4-tft-trainer
tasks_count: 15
---

# Technical — Stage 5.4 — Trainer do TFT quantílico

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [5.4/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 5.4: complete` e atualizar `roadmap.md`.

## 1. Contexto e estratégia de execução

### Resumo

Implementar o candidato TFT: port-out `TftTrainer` (fronteira só de
primitivos, painel completo + faixas contíguas de índices por partição), use
case `TrainTft` (lê dataset 3.5, splits 5.1, tipagem known/unknown, guardrail
4.3, dedup, `dim_run`, persistência com `model_version='tft_quantile'`,
rastreamento no MLflow com artefato), adapter `PfTftTrainer` (um modelo por
fold com decodificador de `max_horizon` passos, normalizador explícito ajustado
no quadro de treino, parada antecipada com restauração do melhor checkpoint,
emissão quantílica recortada por comprimento de decodificador) e a varredura
exploratória (`HyperparameterSearch` *ask-and-tell* + `OptunaSearch` +
`RunTftSweep`). Contratos e invariantes: `concept.md` §4–§6; decisões D1–D11
(ADRs 5.4.0001–0006).

### Estratégia

TDD inside-out com fitness function primeiro (skill `task-ordering-hex`):

1. **Ambiente e gate antes do código** (Tasks 01–02): dependências com o
   caminho de instalação que de fato as resolve, depois os dois contratos
   import-linter com prova de quebra — o guard-rail existe antes do primeiro
   import da lib.
2. **Contrato antes da implementação** (Task 03): port e DTOs, testáveis sem lib.
3. **Fake antes do real** (Task 04): o fake materializa as regras que não
   dependem da lib — emissão na cauda (I16), descarte declarado (I17), C3/C4,
   determinismo, codificação `(decisão, horizonte)` — e vira o oráculo de forma
   da suite de contrato.
4. **Aplicação com fakes** (Tasks 05–06): orquestração e rastreamento testados
   sem `torch`.
5. **Adapter real em três seams** (Tasks 07–09): datasets+normalizador,
   treino+checkpoint, predição+emissão. Cada seam tem a sua armadilha verificada
   isoladamente — é onde os achados de biblioteca do Checkpoint A moram.
6. **Equivalência fake↔real** (Task 10).
7. **Varredura** (Tasks 11–13): port, adapter, use case isolado.
8. **Wiring + e2e** (Task 14) e **gate agregado** (Task 15).

Cada commit deixa `make check` verde. Checkpoint C após Tasks 04, 06, 09, 13 e
14 — esta Stage é pesada (modelo novo, dois ports novos, dependência
estrutural), então o Checkpoint C usa **2 revisores** com lentes distintas,
conforme a regra de fan-out proporcional ao peso.

### Pré-condições

- Stage `5.1-walk-forward-harness` em `done` e mergeada em `develop`;
  4.3/3.4/3.5/1.5/1.4 `done` (transitivas).
- Issue #57 aberta; branch `feat/57-5-4-tft-trainer` ativa.
- Issue #58 aberta (piso declarado do D4 — calendário na registry).
- Concept em `status: done`.

### Premissas técnicas

- Python 3.12 + uv (host: 0.11.28); `make check` = lint + typecheck + layout +
  lint-imports + docs-check + test com cobertura.
- **O ambiente de execução é o Docker** (workflow docker-only). Toda
  verificação de resolução de dependência vale dentro da imagem, não só no host.
- Dataset físico `processed/dataset_tft/<asset>/*.parquet` com as 62 colunas
  do schema 3.5; features de desenho = 55 da registry (todas `unknown` hoje) +
  `day_of_week` + `month` como conhecidas; `time_idx` é índice, não covariável.
- Registry hoje: 55 specs, todas `enabled_by_default=True` (verificado
  2026-08-09); C6 protege contra drift futuro.

### Geometria canônica de fixture

A aritmética abaixo é **parte do plano**, não detalhe de teste: vários critérios
(A4b, A12, A13) só são construtíveis se a geometria satisfizer as condições de
alcance de I4 e de cauda de I16.

```
max_horizon = 2      embargo = 1      => gap = max_horizon + embargo = 3
max_encoder_length (L) = 12
val_size = calib_size = test_size = 5      n_folds = 1
painel = 54 sessões (train_end = 30)
```

Blocos (fatias semiabertas do `walk_forward_splitter`):

| bloco | índices |
|---|---|
| `train` | `[0, 30)` |
| gap | `[30, 33)` |
| `early_stop` | `[33, 38)` |
| gap | `[38, 41)` |
| `calib` | `[41, 46)` |
| gap | `[46, 49)` |
| `test` | `[49, 54)` |

Consequências que os testes exploram:

- **Alcance (I4):** a decisão de teste de offset `j` alcança `calib` sse
  `j <= L − gap − 2 = 7`. Para `j = 0` (t = 49), a janela é `[38, 49]`, que
  contém `41..45` — dentro de `calib`, com folga de 7 sessões.
- **Cauda (I16):** o bloco de teste termina no índice 53, última sessão do
  painel. `h = 1` emite `t ∈ [49, 52]` (4 decisões); `h = 2` emite
  `t ∈ [49, 51]` (3). As amostras de predição são 4, com comprimentos de
  decodificador `[2, 2, 2, 1]` — é o recorte da Task 09 que impede o padding da
  quarta amostra de virar predição de `h = 2`.
- **Descarte declarado (I17):** quem descarta as decisões de treino com `t < 11`
  **não** é o piso de decisão, e sim `min_encoder_length = max_encoder_length`
  (janela completa exigida). Com o quadro de treino `rows[0:32]`,
  `fitted_decision_count = 30 − 11 = 19`; decisões de monitor são `t ∈ [33, 37]`,
  logo `monitored_decision_count = 5`.
- **Normalizador:** `L = 12 < 20`, então a seleção automática da biblioteca
  escolheria o normalizador por quadro — enquanto a produção (`L = 60`)
  escolheria o por janela. É por isso que D10 fixa o normalizador
  explicitamente: sem isso, esta fixture validaria um caminho que a produção não
  usa.

### Mecanismo de recorte por partição (consequência de D5)

A biblioteca só expressa **piso** de decisão (`min_prediction_idx`); não há
teto. O teto vem de **recortar o quadro**:

| dataset | quadro | `min_prediction_idx` (= 1ª decisão + 1) | último índice do quadro |
|---|---|---|---|
| treino | `rows[0 : train_end + max_horizon]` = `rows[0:32]` | 1 | 31 |
| monitor | `rows[0 : max(early_stop) + max_horizon + 1]` = `rows[0:40]` | 34 | **39** |
| predição | painel inteiro | 50 | 53 |

A coluna do meio é o parâmetro da biblioteca — o **primeiro índice do
decodificador** —, não o índice da primeira decisão. Piso 34 no monitor
corresponde às decisões `t ∈ [33, 37]` (cinco), e piso 50 na predição
corresponde a `t ∈ [49, 53]`. Ler a coluna como "primeira decisão" derrubaria
as contagens de I17 e a regra de cauda de I16 em exatamente uma posição.

O quadro de monitor terminar no índice 39, antes de `calib` (que começa em 41),
é o que torna A4(a) uma invariância **estrutural**, não uma esperança.

O quadro de treino incluir os índices 30–31 é **necessário**: são os rótulos das
últimas decisões de treino (o decodificador de `t = 29` cobre 30–31). São
sessões de purga, estritamente antes de `early_stop` — daí a definição de
*quadro de treino* em I4(b) do concept, e daí a população contra a qual A4(c)
compara o normalizador.

### Estratégia de fixture de dados (duas técnicas, uma por camada)

O `WalkForwardSplitter` valida que **cada** sessão da grade é pregão XNYS real e
contígua, então a grade não pode ser `date + timedelta`:

- **Testes unit** (Tasks 05, 06, 13): grade sintética via `TradingSessions` +
  `TradingCalendar`, no padrão de
  `tests/unit/features/modeling/application/test_train_gbm_quantile.py`.
- **Testes de integração/e2e** (Tasks 07–10, 12, 14): sessões reais via
  `ExchangeCalendarsProvider().sessions(...)`, porque o `wire_dependencies`
  monta o calendário XNYS.

Os helpers que fazem isso hoje (`_seed_dataset`, `_xnys_sessions`, `_lcg`) são
privados do módulo do e2e da 5.3. A Task 14 os **move** para
`tests/integration/features/modeling/conftest.py` e ajusta o e2e da 5.3 para
importá-los de lá — uma segunda cópia de uma fixture cuja correção é sutil
(sessões XNYS reais, 62 colunas, `timestamp` tz-aware) é exatamente o tipo de
duplicação que apodrece.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── composition_root.py                                         (Task 14 — modificar)
├── shared/infrastructure/config/settings.py                    (Task 14 — modificar)
└── features/modeling/
    ├── application/
    │   ├── ports/out/tft_trainer.py                            (Task 03 — criar)
    │   ├── ports/out/hyperparameter_search.py                  (Task 11 — criar)
    │   └── use_cases/
    │       ├── train_tft.py                                    (Tasks 05, 06 — criar/modificar)
    │       └── run_tft_sweep.py                                (Task 13 — criar)
    └── adapters/out/
        ├── pytorch_forecasting/{__init__.py, pf_tft_trainer.py} (Tasks 07-09)
        └── optuna/{__init__.py, optuna_search.py}               (Task 12)
tests/
├── architecture/test_import_contracts.py                       (Task 02 — modificar)
├── fakes/features/modeling/{in_memory_tft_trainer.py,
│                            in_memory_hyperparameter_search.py} (Tasks 04, 11)
├── unit/features/modeling/application/test_*.py                 (Tasks 03-06, 11, 13)
├── unit/shared/test_composition_root.py                        (Task 14 — modificar)
├── integration/features/modeling/{conftest.py, test_pf_tft_*.py,
│                    test_optuna_search.py, test_train_tft.py}   (Tasks 07-09, 12, 14)
├── integration/features/modeling/test_train_gbm_quantile.py    (Task 14 — modificar:
│                                       passa a importar os helpers do conftest)
└── contract/features/modeling/test_*_contract.py                (Tasks 10, 12)
pyproject.toml, uv.lock, Dockerfile, Makefile, .github/workflows/ci.yml (Task 01)
.importlinter                                                    (Task 02)
docs/roadmap.md                                                  (Task 15)
```

> **Nota de mapeamento vs `arquivos_a_criar` do roadmap.**
> `test_known_unknown_typing.py` (flat) materializa como
> `unit/.../application/test_train_tft.py` (a tipagem é função pública do use
> case — padrão da 5.3 com `expected_feature_names`);
> `test_train_tft_smoke.py` materializa como os três testes de integração do
> adapter (`test_pf_tft_*.py`), o smoke desdobrado por seam. O adapter da
> varredura é `optuna_search.py` e não `optuna_sweep.py`: o port é uma **busca**;
> a varredura é o use case. Divergências e contratos que o bloco YAML não
> desdobrou estão declarados no concept §1 e são reconciliados na Task 15.

## 2. Tasks

### Task 01 — Dependências + caminho de instalação que as resolve

- **Arquivos a modificar:** `pyproject.toml`, `uv.lock`, `Dockerfile`,
  `Makefile`, `.github/workflows/ci.yml`
- **O que fazer:**
  Adicionar `torch>=2.12,<3.0`, `lightning>=2.5,<2.7`,
  `pytorch-forecasting>=1.8,<2.0` e `optuna>=4.0,<5.0` a
  `[project].dependencies`, com bloco de comentário no padrão dos existentes
  (por que core e não extra — D3 / ADR 5.4.0003; pin por minor, lock trava o
  patch, como todos os outros blocos). Declarar o índice CPU **com marker**:
  ```toml
  [[tool.uv.index]]
  name = "pytorch-cpu"
  url = "https://download.pytorch.org/whl/cpu"
  explicit = true

  [tool.uv.sources]
  torch = [{ index = "pytorch-cpu", marker = "platform_system != 'Darwin'" }]
  ```
  **Migrar o caminho de instalação para a interface de projeto:** `uv pip
  install` ignora `tool.uv.sources`, e o `Dockerfile` sequer copia o `uv.lock` —
  sem isso a imagem instala a variante CUDA e a decisão D3 não vale onde o
  projeto roda. Trocar `uv pip install -e ".[dev]"` por `uv sync --locked
  --extra dev` no `Makefile` (`setup`, `install`) e nas duas stages do
  `Dockerfile`, copiando `uv.lock` antes. No workflow: pinar a versão do
  `setup-uv`, habilitar `enable-cache: true`, trocar `uv sync --extra dev` por
  `uv sync --locked --extra dev` e subir `timeout-minutes` de 15 para 30.
  Reconciliar a declaração dupla de `torch` (dependência principal × extra
  `sentiment`) e corrigir o comentário do extra, que hoje afirma que o CI não
  instala `torch`.
- **Detalhes técnicos:**
  - Marker obrigatório: o índice CPU não publica wheels de macOS; sem ele o
    lock universal não resolve no split darwin.
  - Guarda contra rebaixamento silencioso: `numpy`, `pandas`, `scipy` e
    `scikit-learn` estão hoje fixados **transitivamente** no lock em versões
    altas; um re-lock com `pytorch-forecasting` pode rebaixá-los e mover as
    fixtures-oráculo de `pandas-ta-classic`/`statsforecast`/`pandera`.
  - Medir e registrar o tempo do job de instalação antes/depois (risco R1).
- **Critério de aceite:**
  - **Dentro da imagem** (`make docker-build` + probe):
    `python -c "import torch; print(torch.__version__)"` imprime versão com
    sufixo `+cpu`, e nenhum pacote `nvidia-*`/`triton` aparece em
    `uv pip list`. Um probe só no host **não** conta — é falso verde.
  - `uv lock --check` verde; `git diff uv.lock` revisado e sem mudança de
    major/minor em numpy/pandas/scipy/scikit-learn (o diff vai ao relatório).
  - `make check` verde no host e na imagem.
- **Comando de verificação:**
  ```bash
  uv lock --check
  make docker-build
  docker compose run --rm app python -c "import torch, pytorch_forecasting, optuna; print(torch.__version__)"
  docker compose run --rm app sh -lc "uv pip list | grep -Ei 'nvidia|triton' && exit 1 || echo 'sem cuda'"
  make check
  ```
- **Commit sugerido:** `build(modeling): adicionar torch cpu, pytorch-forecasting e optuna via uv sync [5.4/task-01]`

---

### Task 02 — Gates de vazamento `modeling-no-torch-leak` e `modeling-no-optuna-leak`

- **Arquivos a modificar:** `.importlinter`, `tests/architecture/test_import_contracts.py`
- **O que fazer:**
  Adicionar dois contratos `forbidden` no template do
  `modeling-no-lightgbm-leak`: `modeling-no-torch-leak` (proibindo `torch`,
  `lightning` e `pytorch_forecasting`) e `modeling-no-optuna-leak` (proibindo
  `optuna`), ambos com `source_modules` = `modeling.application` +
  `modeling.domain`. Registrar os nomes em `_EXPECTED_CONTRACTS` e adicionar os
  casos em `_REAL_VIOLATION_CASES`.
- **Detalhes técnicos:**
  - `_REAL_VIOLATION_CASES` é a guarda contra **contrato míope** (um
    `source_modules` apontando para o pacote errado passaria verde). O formato é
    `pytest.param("<nome-do-contrato>", {"<path relativo a _SRC_ROOT>": "<conteúdo>"}, id=...)`.
  - **Um caso por módulo proibido**, não um por contrato: com três módulos sob
    `modeling-no-torch-leak`, um único caso com `import torch` deixaria um typo
    em `lightning`/`pytorch_forecasting` passar verde — exatamente o furo que a
    constante existe para fechar.
  - O alvo tem de ser `features/modeling/application/...`: `domain-purity` já
    proíbe `torch` no `modeling.domain`, então um caso mirando o domínio não
    discrimina o contrato novo.
  - O path de injeção `_arch_audit_taint.py` já é usado por casos existentes;
    usar um nome distinto por caso evita depender da ordem de execução.
  - Prova de quebra intencional manual (saída literal em §7 e no relatório):
    `import torch` em `train_gbm_quantile.py` → `uv run lint-imports` vermelho →
    reverter → verde. Idem `import optuna`.
  - Corrigir também aqui o comentário do contrato `sentiment-no-ml-leak`, que
    afirma que `torch` vive fora do `dev` e fora do CI — falso a partir da
    Task 01 (o par em `pyproject.toml` é corrigido lá; este é o outro).
- **Critério de aceite:**
  - `uv run lint-imports` verde com os dois contratos listados como kept;
  - `tests/architecture/` verde, com um caso de violação real por módulo
    proibido (quatro casos no total);
  - as duas provas de quebra manuais executadas e revertidas.
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run pytest tests/architecture/ -q
  make check
  ```
- **Commit sugerido:** `build(modeling): gates de vazamento de torch e optuna [5.4/task-02]`

---

### Task 03 — Port `TftTrainer` + DTOs

- **Arquivos a criar:**
  `src/financial_forecasting/features/modeling/application/ports/out/tft_trainer.py`,
  `tests/unit/features/modeling/application/test_tft_trainer_port.py`
- **O que fazer:**
  `TftTrainingParams` (frozen, defaults do concept §4, `__post_init__` validando
  C2-params), `TftTrainingResult` (frozen, com os nove campos do concept §4) e o
  `Protocol` `TftTrainer` com a assinatura exata, reusando `GridByHorizon`.
  A **docstring do módulo é o contrato**: janela `[t − L + 1, t]` (completa sse
  `t >= L − 1`); faixas de índice contíguas e crescentes (C4); regra de emissão
  I16; descarte declarado I17; `artifact_path` = checkpoint da época
  `best_epoch`; `val_loss_by_epoch` sem passagem de sanidade; modo fit-only;
  grade crua sem guardrail.
- **Detalhes técnicos:**
  - Validações → `ValueError` nomeando o campo: `max_encoder_length < 1`,
    `hidden_size < 1`, `attention_head_size < 1`, `dropout` fora de `[0, 1)`,
    `learning_rate <= 0`, `max_epochs < 1`, `patience < 1`, `batch_size < 1`.
  - Só `dataclasses`/`typing`/`collections.abc` no módulo (gate de leak).
- **Critério de aceite:**
  - Params default válidos; cada violação ergue `ValueError` nomeando o campo;
    DTOs imutáveis (`FrozenInstanceError`).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_tft_trainer_port.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): port TftTrainer com params validados [5.4/task-03]`

---

### Task 04 — Fake in-memory do `TftTrainer`

- **Arquivos a criar:**
  `tests/fakes/features/modeling/in_memory_tft_trainer.py`,
  `tests/unit/features/modeling/application/test_in_memory_tft_trainer.py`
- **O que fazer:**
  Fake determinístico que honra todas as regras do port que não dependem da
  biblioteca: valida C4 (larguras, contenção de `known_feature_names`, índices
  no painel, **contiguidade e crescimento**, `horizons ⊆ 1..max_horizon`,
  monitor não vazio); aplica a regra de janela e decodificador completos e
  devolve as contagens de I17; ergue C3 quando alguma contagem zera; emite grade
  apenas para os pares que I16 autoriza; codifica `(decision_idx, horizon)` na
  grade; **materializa um arquivo determinístico em `artifact_dir` e devolve o
  caminho dele** (sem isso o fake do `ExperimentTracker`, que valida existência
  em `log_artifact`, reprovaria A8); no modo fit-only devolve grids e
  `artifact_path` vazios e **não** escreve arquivo. Registra `last_call` para as
  asserções estruturais de A6 e A10.
- **Detalhes técnicos:**
  - A emissão é função determinística dos alvos visíveis somada ao código de
    `(decision_idx, horizon)` — é o que torna a perna fake de A15 discriminante
    entre `g(t+h)` e `g(t+h±1)`.
  - `val_loss_by_epoch` é decrescente determinística com `best_epoch` no argmin.
- **Critério de aceite:**
  - Emissão respeita I16; contagens de I17 batem com a aritmética da geometria
    canônica; C3 e C4 (inclusive faixa não contígua) erguem; fit-only devolve
    vazio e não escreve arquivo; duas chamadas idênticas devolvem grades
    idênticas; `artifact_path` existe em disco no modo normal.
  - **A15 (perna fake):** com alvo sintético injetivo `g`, a mediana emitida
    para `(t, h)` é mais próxima de `g(t+h)` que de `g(t+h±1)`; deslocar o
    mapeamento em um passo reprova.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_in_memory_tft_trainer.py -q
  make check
  ```
- **Commit sugerido:** `test(modeling): fake in-memory do TftTrainer com regras de emissão e descarte [5.4/task-04]`

> **Checkpoint C — bloco 1** (Tasks 01–04), 2 revisores.

---

### Task 05 — Use case `TrainTft` (tipagem, orquestração, persistência)

- **Arquivos a criar:**
  `src/financial_forecasting/features/modeling/application/use_cases/train_tft.py`,
  `tests/unit/features/modeling/application/test_train_tft.py`
- **O que fazer:**
  Use case no padrão do `train_gbm_quantile.py`: valida comando (C2), lê o
  dataset (C1/C6), monta o painel completo ordenado por sessão, gera folds,
  deriva as três faixas de índices do `FoldSplit`, compõe
  `artifact_dir = <artifacts_root>/tft/<run_id>`, chama o port, aplica o
  guardrail por (decisão × horizonte emitido), acumula o dedup, grava `dim_run`
  e persiste via `PersistPredictions` com `model_version='tft_quantile'`. Expor
  `unknown_feature_names()` e `known_feature_names()`, derivadas da registry por
  `spec.tft_typing` mais a constante de calendário (D4/I2).
  **O construtor já recebe `ExperimentTracker` e `artifacts_root`** — mesmo que
  o comportamento de rastreamento só entre na Task 06 —, para que a Task 06 não
  precise mudar a assinatura e invalidar os testes escritos aqui.
- **Detalhes técnicos:**
  - `feature_names` = desconhecidas + conhecidas, nessa ordem; as duas tuplas
    ordenadas entram nos payloads de `run_id`/`config_signature` (I10).
  - `rows_skipped` vem do 4.3; nesta Stage é **zero por construção** (a condição
    de emissão do port e a de pulo do persister são a mesma desigualdade) — o
    teste assere isso em vez de ignorá-lo.
- **Critério de aceite:**
  - **A3:** listas de tipagem exatamente como a regra prescreve, com uma spec
    `known` injetada via monkeypatch provando que a coluna troca de lista
    sozinha; `time_idx` ausente das duas; mutação de tipagem detectada.
  - **A6:** nenhum índice de `calib` aparece em `train_decision_indices` nem em
    `early_stop_decision_indices` do `last_call` do fake.
  - **C1**; **C6**; **C2 com um teste por cláusula**: `horizons` vazio,
    duplicado, com elemento `< 1`, com `max(horizons) > scope.max_horizon`;
    `quantile_levels` vazio, com elemento fora de `(0, 1)`, não estritamente
    crescente.
  - Dedup com remoção zero (I11); guardrail aplicado (grade fora de ordem sai
    ordenada); `rows_skipped == 0`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_train_tft.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): use case TrainTft com tipagem known/unknown e persistência [5.4/task-05]`

---

### Task 06 — Rastreamento do run no `TrainTft`

- **Arquivos a criar:** `tests/unit/features/modeling/application/test_train_tft_tracking.py`
- **Arquivos a modificar:**
  `src/financial_forecasting/features/modeling/application/use_cases/train_tft.py`
- **O que fazer:**
  Implementar I12 usando o tracker já injetado na Task 05: por fold, abrir run,
  registrar params (semente, hiperparâmetros, geometria, grade, impressão do
  split), métricas (perda por época e a da melhor época), tags
  (`model_version`, `phase='confirmatory_ready'`, `fold`), registrar o artefato
  e fechar o run. Implementar C8: falha do tracker é **absorvida** (log), a
  execução segue e o `TftRunSummary` sai com `tracking_run_id` vazio.
- **Detalhes técnicos:**
  - Ordem obrigatória: **persistir primeiro, rastrear depois**. É o que torna a
    absorção segura — ela nunca pode esconder uma persistência incompleta.
  - `log_artifact` só é chamado quando `artifact_path` não é vazio.
- **Critério de aceite:**
  - **A8:** um `start_run`/`end_run` por fold; params, métricas e tags
    presentes; `log_artifact` com caminho existente em disco; tracker que ergue
    **não** derruba a execução — o resultado volta com `tracking_run_id` vazio e
    as linhas persistidas permanecem.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_train_tft_tracking.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): registrar run e artefato do TFT no ExperimentTracker [5.4/task-06]`

> **Checkpoint C — bloco 2** (Tasks 05–06), 2 revisores.

---

### Task 07 — Adapter `PfTftTrainer` (I): datasets, tipagem e normalizador explícito

- **Arquivos a criar:**
  `src/.../adapters/out/pytorch_forecasting/__init__.py`,
  `src/.../adapters/out/pytorch_forecasting/pf_tft_trainer.py`,
  `tests/integration/features/modeling/test_pf_tft_dataset.py`
- **O que fazer:**
  Declarar o **seam interno de teste** `_build_datasets(...) -> _TftDatasets`,
  onde `_TftDatasets` expõe os três datasets, `normalizer_center`,
  `normalizer_scale` e as contagens de amostras de treino e monitor. Sem esse
  seam os critérios desta Task só seriam alcançáveis depois do treino (Task 08),
  e a Task deixaria de ser verificável no próprio commit.
  Construir os três `TimeSeriesDataSet` conforme o mecanismo de recorte de §1:
  treino a partir do quadro recortado com piso de decisão; monitor e predição
  **derivados do de treino** (herdam o normalizador ajustado — I4b). Fixar
  `target_normalizer` explicitamente como padronizador de grupo único (D10),
  nunca `auto`. Aplicar a tipagem recebida, índice temporal relativo, grupo
  constante, `min_encoder_length = max_encoder_length` e
  **`min_prediction_length`**: igual a `max_prediction_length` no treino e no
  monitor (decodificador completo, perda do paper), e **1** na predição (cauda
  variável — D2/I16). Validar C4 antes de qualquer construção.
- **Detalhes técnicos:**
  - `normalizer_center`/`normalizer_scale` saem dos parâmetros do normalizador
    **ajustado** — recalculá-los no adapter tornaria a asserção de A4(c)
    tautológica.
  - `ignore_missing_imports = true` faz tudo de `pytorch_forecasting` virar
    `Any`, e `warn_return_any` (parte do strict) morde na volta: converter
    explicitamente com `float(...)`, como o adapter LightGBM já faz.
- **Critério de aceite:**
  - **A4(c):** centro e escala batem com a média e o desvio amostral (com
    epsilon) do alvo sobre o **quadro de treino** (`rows[0:32]` na geometria
    canônica — bloco `train` + as 2 sessões de purga que são rótulos). A mutação
    que isso detecta é construir o dataset de **treino** a partir do painel
    inteiro; os três datasets compartilham os mesmos parâmetros de normalizador
    (asserção de identidade).
  - **A12 (parte):** contagens de amostras de treino (19) e monitor (5) batem
    com a aritmética; caso adicional com `max_encoder_length > train_end`
    produzindo contagem zero e disparando C3.
  - **Amostras de predição:** exatamente 4, com comprimentos de decodificador
    `[2, 2, 2, 1]` — é o que prova que `min_prediction_length = 1` chegou ao
    dataset de predição. Sem este caso, o default da biblioteca
    (`min_prediction_length = max_prediction_length`) descartaria a amostra
    `t = 52` e o erro só apareceria duas Tasks adiante, em A13.
  - C4 ergue nos casos estruturais, incluindo faixa não contígua.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/test_pf_tft_dataset.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling.adapters): construir TimeSeriesDataSet com tipagem e normalizador de treino [5.4/task-07]`

---

### Task 08 — Adapter `PfTftTrainer` (II): treino, parada antecipada e checkpoint

- **Arquivos a criar:** `tests/integration/features/modeling/test_pf_tft_training.py`
- **Arquivos a modificar:** `src/.../pytorch_forecasting/pf_tft_trainer.py`
- **O que fazer:**
  Instanciar o `TemporalFusionTransformer` a partir do dataset de treino com a
  perda quantílica na grade **do comando** (o default da biblioteca não é a
  grade do projeto), treinar em CPU com modo determinístico e sem passagem de
  sanidade, com callbacks de parada antecipada, de checkpoint da melhor época e
  o de histórico (D11). Implementar C10. Semear a cada chamada e restaurar a
  flag global de algoritmos determinísticos ao sair (I9).
- **Detalhes técnicos:**
  - O callback de histórico ignora a passagem de sanidade (ou ela é
    desabilitada): uma entrada antes da época 0 deslocaria o índice e quebraria
    a identidade `best_epoch == argmin` que A5 usa como prova.
  - No modo fit-only nenhum callback de checkpoint é registrado — a varredura
    roda dezenas de treinos e não deve deixar arquivos órfãos.
  - Para C10 ser alcançável de forma determinística, a seleção do melhor
    checkpoint fica num helper puro testável direto (precedente `_finite_grid`
    da 5.3), além do caminho por monkeypatch do callback.
- **Critério de aceite:**
  - **A5 (parte):** `best_epoch == argmin(val_loss_by_epoch)`;
    `len(val_loss_by_epoch)` == número de épocas executadas; `artifact_path`
    existe em disco e corresponde à época `best_epoch`.
  - **A4(a):** mutar os alvos em `calib` (41–45) e em `test` (49–53) deixa
    `best_epoch` e `val_loss_by_epoch` **idênticos** — invariância estrutural,
    porque o quadro do monitor termina no índice 39.
  - **A2 (cláusula de I8):** exatamente **um** ajuste por fold (contagem de
    instâncias de treinador/`fit`).
  - **C10** ergue quando a perda de validação nunca é finita ou o caminho do
    melhor checkpoint volta vazio.
  - Fit-only não escreve checkpoint.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/test_pf_tft_training.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling.adapters): treino do TFT com parada antecipada e checkpoint [5.4/task-08]`

---

### Task 09 — Adapter `PfTftTrainer` (III): predição quantílica e regra de emissão

- **Arquivos a criar:** `tests/integration/features/modeling/test_pf_tft_prediction.py`
- **Arquivos a modificar:** `src/.../pytorch_forecasting/pf_tft_trainer.py`
- **O que fazer:**
  Restaurar o melhor checkpoint e predizer em modo quantílico pedindo **índice**
  e **comprimentos de decodificador** junto com a saída; recortar cada amostra
  pelo comprimento real; chavear por decisão a partir do índice devolvido;
  emitir apenas os pares que I16 autoriza; validar finitude (C5) **depois** do
  recorte.
- **Detalhes técnicos:**
  - A chave de decisão vem do índice devolvido pela predição, não de uma
    contagem paralela — é isso que A15 assere na perna real, e o que impede o
    off-by-one da classe registrada no ADR 4.3.0001.
  - Sem o recorte, o padding viraria predição fabricada (I15) ou dispararia C5
    em toda cauda legítima.
  - A verificação de finitude fica num helper puro testável direto, para que C5
    tenha gatilho determinístico sem depender de o treino divergir.
- **Critério de aceite:**
  - **A2:** grade completa por par emitido, alinhada 1:1 a `quantile_levels`.
  - **A5 (fecho):** a predição de teste é idêntica à de um modelo recarregado de
    `artifact_path` — a mutação "predizer com os pesos da última época" reprova.
  - **A9 (parte real):** duas chamadas idênticas no mesmo processo devolvem
    grades, `best_epoch` e `best_val_loss` idênticos.
  - **A15 (perna real):** o passo `h` corresponde a `t + h` pelo índice
    devolvido; deslocar o mapeamento em um passo reprova.
  - **A4(b):** mutar sessões dentro da janela de `t = 49` (`[38, 49]`, cobrindo
    `calib` em 41–45) **altera** a grade daquela decisão — sem este caso, a
    invariância de A4(a) passaria também para um modelo que ignora as entradas.
  - **A13 (parte):** o conjunto de pares emitidos é exatamente
    `{(t, h) : t ∈ test, t + h <= 53}` — 4 pares para `h = 1`, 3 para `h = 2`.
  - **C5** ergue em posição realmente prevista e **não** ergue por padding.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/test_pf_tft_prediction.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling.adapters): emissão quantílica recortada por comprimento de decodificador [5.4/task-09]`

> **Checkpoint C — bloco 3** (Tasks 07–09), 2 revisores.

---

### Task 10 — Suite de contrato `TftTrainer` fake ↔ real

- **Arquivos a criar:** `tests/contract/features/modeling/test_tft_trainer_contract.py`
- **O que fazer:**
  Suite parametrizada sobre `[fake, real]`: forma da grade (A2), regra de
  emissão I16, contagens de I17, C3 e C4 idênticos nas duas pernas, determinismo
  por chamada (A9), fit-only. Docstring declara o que é **exclusivo da perna
  real** e por quê: C5, C10 e A4(c) — inatingíveis no fake por construção, na
  linha do finding herdado da 5.3.
- **Detalhes técnicos:**
  - A perna real reusa um modelo treinado por sessão de teste onde o caso não
    exige treino próprio (orçamento de R2).
- **Critério de aceite:**
  - Todos os casos verdes nas duas pernas; paridade de marcador de erro entre
    fake e real (precedente da 5.3).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/modeling/test_tft_trainer_contract.py -q
  make check
  ```
- **Commit sugerido:** `test(modeling): suite de contrato do TftTrainer (fake e real) [5.4/task-10]`

---

### Task 11 — Port `HyperparameterSearch` + DTOs + fake

- **Arquivos a criar:**
  `src/.../application/ports/out/hyperparameter_search.py`,
  `tests/fakes/features/modeling/in_memory_hyperparameter_search.py`,
  `tests/unit/features/modeling/application/test_hyperparameter_search_port.py`
- **O que fazer:**
  Port *ask-and-tell* com `SearchDimension` (validando C11), `SearchTrial` e o
  `Protocol`. Fake com amostrador determinístico (grade regular), que ergue em
  `best_trial` sobre estudo vazio (C9). Docstring declara que a fronteira
  devolve sempre `float` e que a reconversão por `kind` é do use case.
- **Critério de aceite:**
  - Cada violação de C11 (`kind` inválido, `low >= high`, `low < 1` com inteiro
    logarítmico, `name` fora dos campos de `TftTrainingParams`) ergue
    `ValueError` nomeando o campo; `best_trial` sem `tell` ergue; o fake é
    reprodutível para a mesma semente.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_hyperparameter_search_port.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): port HyperparameterSearch ask-and-tell com dimensões validadas [5.4/task-11]`

---

### Task 12 — Adapter `OptunaSearch` + suite de contrato

- **Arquivos a criar:**
  `src/.../adapters/out/optuna/__init__.py`, `src/.../adapters/out/optuna/optuna_search.py`,
  `tests/integration/features/modeling/test_optuna_search.py`,
  `tests/contract/features/modeling/test_hyperparameter_search_contract.py`
- **O que fazer:**
  Traduzir `SearchDimension` para as distribuições da biblioteca (inteira/
  contínua, com escala logarítmica), criar o estudo com amostrador semeado (a
  semente do port vira semente do amostrador — o Optuna não a recebe no estudo),
  e implementar `ask`/`tell`/`best_trial` por número de trial. Suite de contrato
  parametrizada sobre `[fake, real]`.
- **Critério de aceite:**
  - Contrato verde nas duas pernas: `ask` respeita os limites; `tell` por
    número; `best_trial` devolve o de menor objetivo; estudo vazio ergue; mesma
    semente → mesma sequência de trials na perna real.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/test_optuna_search.py tests/contract/features/modeling/test_hyperparameter_search_contract.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling.adapters): OptunaSearch ask-and-tell com amostrador semeado [5.4/task-12]`

---

### Task 13 — Use case `RunTftSweep` (varredura exploratória isolada)

- **Arquivos a criar:**
  `src/.../application/use_cases/run_tft_sweep.py`,
  `tests/unit/features/modeling/application/test_run_tft_sweep.py`
- **O que fazer:**
  Lê o dataset, gera os folds e, por trial: pede os valores ao port de busca,
  reconverte por `kind`, monta os params sobre uma cópia dos `base_params`,
  chama o trainer em **modo fit-only**, informa o objetivo (perda de validação)
  ao estudo e registra o trial no tracker com `phase='exploratory'`. Devolve o
  melhor trial e os params correspondentes. Construtor **sem**
  `PersistPredictions` e **sem** `AnalyticsRepository`.
- **Critério de aceite:**
  - **A10:** a assinatura do construtor não tem porta de persistência de
    resultados; o fake do `MedallionStore` registra zero escritas; o trainer
    recebe `test_decision_indices == ()` em todos os trials e nenhum arquivo é
    escrito em `artifact_dir`; o objetivo informado é a perda de validação
    devolvida pelo trainer; todos os runs levam `phase='exploratory'`.
  - **C9** nos dois casos (`n_trials < 1`; todos os trials falharam).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/modeling/application/test_run_tft_sweep.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): use case RunTftSweep exploratório e isolado do confirmatório [5.4/task-13]`

> **Checkpoint C — bloco 4** (Tasks 10–13), 2 revisores.

---

### Task 14 — Wiring no composition root + e2e com adapter e tracker reais

- **Arquivos a criar:**
  `tests/integration/features/modeling/conftest.py`,
  `tests/integration/features/modeling/test_train_tft.py`
- **Arquivos a modificar:**
  `src/financial_forecasting/composition_root.py`,
  `src/financial_forecasting/shared/infrastructure/config/settings.py`,
  `tests/unit/shared/test_composition_root.py`,
  `tests/integration/features/modeling/test_train_gbm_quantile.py`
- **O que fazer:**
  Adicionar `artifacts_root` a `Settings` (default relativo, padrão de
  `data_root`); wirar `train_tft` e `run_tft_sweep` em
  `ApplicationDependencies` com proxies lazy (`_LazyPfTftTrainer`,
  `_LazyOptunaSearch`) no padrão do `_LazyLightgbmQuantileTrainer`. Mover os
  helpers de fixture (`_seed_dataset`, `_xnys_sessions`, `_lcg`) do e2e da 5.3
  para `conftest.py`, **parametrizando-os pela contagem de sessões** (hoje
  `_xnys_sessions()` não recebe argumento e depende da constante de módulo
  `_N_SESSIONS = 120`; a geometria canônica da 5.4 precisa de 54), e ajustar
  aquele teste a importá-los. Escrever o e2e:
  dataset semente em `tmp_path`, `wire_dependencies` com store real,
  `MlflowTracker` real em `sqlite:///<tmp_path>/mlruns.db`, execução completa e
  verificação do parquet, do artefato em disco e do run no MLflow.
- **Detalhes técnicos:**
  - **A13 (paridade):** rodar `TrainGbmQuantile` (5.3) sobre o **mesmo** dataset
    e a **mesma** geometria. As geometrias são compatíveis (`gap =
    scope.max_horizon + embargo` para os dois) e uma fixture serve aos dois
    porque `expected_feature_names()` do GBM é o mesmo conjunto de 57 colunas —
    enquanto toda spec da registry for `unknown`. **Pinar
    `GbmTrainingParams(min_data_in_leaf=5, num_boost_round_max=10)`**: o default
    `min_data_in_leaf=20` faria o adapter LightGBM erguer C3 com o painel de 30
    linhas de treino, por um motivo que nada tem a ver com paridade.
  - Justificativa dos 6 arquivos: mover a fixture em vez de duplicá-la é o que
    evita uma segunda cópia de uma construção cuja correção é sutil (sessões
    XNYS reais, 62 colunas, `timestamp` tz-aware).
- **Critério de aceite:**
  - **A16:** fluxo completo verde, artefato existente em disco, run no MLflow
    com params/tags e artefato registrado.
  - **A13:** igualdade exata dos conjuntos de `target_timestamp` por horizonte
    contra a 5.3.
  - **A7:** linhas com `model_version='tft_quantile'`, guardrail aplicado,
    `dim_run` com `seed` preenchida.
  - **A9 (perna do use case):** duas execuções contra stores isolados produzem
    as mesmas predições.
  - **C7:** reexecução idêntica contra o **mesmo** store propaga
    `DuplicateKeyError` — pina a semântica de replay para a 5.5.
  - **Wiring (parte de A1):** `deps.train_tft` e `deps.run_tft_sweep` existem e
    são dos tipos certos; probe de import lazy provando que importar o
    composition root **não** importa `torch` nem `optuna` (precedente
    `test_lazy_wiring_importing_composition_root_does_not_import_lightgbm`).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/modeling/ tests/unit/shared/test_composition_root.py -q
  make check
  ```
- **Commit sugerido:** `feat(modeling): wirar TrainTft e RunTftSweep no composition root com e2e real [5.4/task-14]`

> **Checkpoint C — bloco 5** (Task 14), 2 revisores.

---

### Task 15 — Gate agregado da Stage (roadmap, cobertura, medições)

- **Arquivos a modificar:** `docs/roadmap.md`
- **O que fazer:**
  Reconciliar o bloco YAML da Stage 5.4 com o que foi entregue (quatro
  contratos; arquivos desdobrados), conforme a divergência declarada no concept
  §1. Rodar o gate completo, medir cobertura por arquivo tocado, medir o tempo
  do job de CI e o da suite do adapter (R1/R2) e registrar os números.
- **Critério de aceite:**
  - `make check` verde; cobertura global ≥ 90%; cada arquivo tocado ≥ 90% no
    `term-missing` ou justificado por escrito;
  - bloco YAML coerente com a entrega; números de R1/R2 registrados.
- **Comando de verificação:**
  ```bash
  make check
  uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing
  git diff --name-only $(git merge-base origin/develop HEAD) HEAD -- src/
  ```
- **Commit sugerido:** `docs(roadmap): reconciliar bloco da stage 5.4 com a entrega [5.4/task-15]`

## 3. Gate de saída da Stage

### Matriz de rastreabilidade (critério do concept → Task que o prova)

| Critério | Task(s) | Verificação objetiva |
|---|---|---|
| A1 — contratos, `make check`, wiring | 03, 05, 11, 12, 13, 14, 15 | mypy strict + layout + lint-imports + campos de `ApplicationDependencies` |
| A2 — grade 1:1 e um modelo por fold | 08 (I8), 09 (grade), 10 (contrato) | contagem de ajustes; suite `[fake, real]` |
| A3 — tipagem como regra | 05 | spec `known` injetada troca de lista sozinha |
| A4(a) — ajuste/monitor não veem `calib`/`test` | 08 | mutação 41–45 e 49–53 → `best_epoch`/histórico idênticos |
| A4(b) — contexto não é vácuo | 09 | mutação em `[38, 49]` → grade de `t = 49` muda |
| A4(c) — normalizador no quadro de treino | 07 | centro/escala == estatística de `rows[0:32]`; mutação = treino do painel inteiro |
| A5 — melhor checkpoint restaurado | 08 (argmin, arquivo), 09 (identidade com recarga) | — |
| A6 — `calib` fora de treino e monitor | 05 | `last_call` do fake |
| A7 — persistência com identidade | 14 | store real em `tmp_path` |
| A8 — rastreamento e C8 absorvido | 06 | fake do tracker |
| A9 — determinismo | 09 (port real), 10 (contrato), 14 (use case) | duas chamadas / duas execuções |
| A10 — varredura isolada | 13, 12 (perna real do contrato de busca) | construtor + zero escritas + fit-only; suite `[fake, optuna]` |
| A11 — C1–C11 | ver mapa abaixo | um teste por caso |
| A12 — descarte declarado | 07, 10 | contagens 19/5 + caso `L > train_end` |
| A13 — paridade com a 5.3 | 09 (parte), 14 | igualdade exata dos `target_timestamp` |
| A14 — gates de vazamento | 02 | 4 casos em `_REAL_VIOLATION_CASES` + prova de quebra |
| A15 — alinhamento passo ↔ horizonte | 04 (fake), 09 (real) | oráculo de proximidade / índice devolvido |
| A16 — e2e com adapter e tracker reais | 14 | fluxo completo + run no MLflow |
| A17 — cobertura por arquivo | 15 | `term-missing` colado no relatório |

Mapa dos casos de erro: C1/C6 → 05; **C2 → 03 (cláusulas de `params`, no
`__post_init__`) + 05 (cláusulas de comando)**; C3/C4 → 04, 07, 10; C5 → 09;
C7 → 14; C8 → 06; C9 → 11, 13; C10 → 08; C11 → 11.

### Verificações automatizadas

```bash
make check
uv run lint-imports
uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/5.4-tft-trainer/technical.md
```

### Verificações funcionais

- Fluxo `TrainTft` exercitado ponta a ponta via `wire_dependencies` com adapter
  **real** e tracker **real** (A16).
- Probe **dentro da imagem** provando `torch` CPU e ausência de pacotes CUDA.
- As duas provas de quebra de import-linter executadas e revertidas, com saída
  literal no relatório (A14).
- Paridade de base amostral com a 5.3 verificada (A13).

### Checklist de fechamento da Stage

- [ ] Critérios A1–A17 do concept satisfeitos (ou desvio registrado em §7).
- [ ] `make check` verde com saída colada.
- [ ] Cobertura ≥ 90% global e por arquivo tocado (medição colada).
- [ ] `check_technical_postexec.py` verde.
- [ ] Auditoria de testes independente com todos os itens "sim".
- [ ] Checkpoints A/B/C com todos os achados dispostos.
- [ ] §7 reflete a execução real.
- [ ] Findings escalados com Stage candidata.
- [ ] `roadmap.md` com a Stage 5.4 em `status: done`, `updated_at` e
      `last_reviewed_at` de hoje.
- [ ] ADRs 5.4.0001–0006 em `accepted`.

## 4. Ordem de dependência entre Tasks

```
01 (deps + instalação)
 └─> 02 (gates) ─┬─> 03 (port) ──> 04 (fake) ──> 05 (use case) ──> 06 (tracking) ──┐
                 │                   │                                              │
                 │                   └─> 07 (datasets) ─> 08 (treino) ─> 09 (predição) ─> 10 (contrato) ──┤
                 │                                                                                        │
                 └─> 11 (port busca) ─> 12 (adapter busca) ─> 13 (sweep) ─────────────────────────────────┤
                                                                                                          │
                                                                              14 (wiring + e2e) <─────────┘
                                                                                   └─> 15 (gate)
```

- 01 antes de tudo: sem as libs instaladas, 07 e 12 não importam.
- 02 antes do primeiro import da lib: o gate existe antes do código que ele guarda.
- 03 antes de 04 (o fake implementa o contrato); 04 antes de 05 (o use case é
  testado com o fake).
- 07→08→09 é sequencial por construção (cada seam usa o anterior).
- 14 depende de 06, 10 e 13; 15 fecha.

## 5. Riscos de execução e fallbacks

| Risco | Gatilho observável | Fallback |
|---|---|---|
| R1 — instalação pesada | job de setup passa de ~8 min mesmo com cache | registrar o número; avaliar imagem base com as libs pré-instaladas (fora do escopo desta Stage — vira issue) |
| R2 — suite do adapter lenta | `tests/integration/features/modeling/test_pf_tft_*` passa de ~3 min | reuso de modelo treinado por sessão; se persistir, marcar `slow` os casos que não são critério de aceite e registrar deviation |
| R3 — API da biblioteca divergir | teste de mecânica da Task 07 vermelho | ajuste local do adapter; o contrato do port **não** muda. Divergência estrutural (ex.: predição não devolve índice) → PARAR e perguntar, porque muda A15 |
| **R10 (novo, só de execução)** — migração do `uv pip` → `uv sync` quebrar a imagem | `make docker-build` vermelho na Task 01 | resolver na própria Task; **não** seguir para a 02 com a imagem quebrada — todo o resto da Stage roda nela |
| R9 — divergência numérica no treino de fumaça | C10 dispara nas fixtures de treino normal | reduzir a taxa de aprendizado da fixture; C10 continua testado pelo helper puro, que não depende de divergência real |
| R5 — descarte maior que o esperado (I17) | contagens de A12 não batem | investigar `min_encoder_length`; não silenciar ajustando o número esperado no teste |

## 6. Referências

- [`./concept.md`](./concept.md) — contratos (§4), invariantes (§5), casos de
  erro (§6), decisões D1–D11 (§7), critérios A1–A17 (§11)
- ADRs desta Stage: 5.4.0001 a 5.4.0006 em [`../../adr/`](../../adr/)
- [`../../domain/modeling/quantile-model-training.md`](../../domain/modeling/quantile-model-training.md) §5
- Precedente direto: [`../5.3-gbm-quantile-baseline/technical.md`](../5.3-gbm-quantile-baseline/technical.md)
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4

## 7. Execução (post-hoc, editável após done)

<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas via
> `scripts/check_technical_postexec.py`. Cada entrada carrega data + autor.

### 2026-08-09 — [decision] Task 01 — medições de R1/R2 e diff do lock — Claude (Opus 5)
**Contexto:** o critério de aceite pedia o número, não a impressão.
**Medido:** `uv sync --locked --extra dev` no container: **27 s**, 14 pacotes
novos, `torch 2.13.0+cpu` (182.9 MiB de download). `make docker-build` (stage
builder, do zero): **4 min 07 s**, com o step de `uv sync` em 54.9 s. `make check`
antes/depois: 3 min 11 s → 3 min 18 s. **R1 estava superestimado**: o concept
projetava ~250–300 MB porque supunha `scipy`/`scikit-learn` novos, mas os dois já
estavam no lock (via statsforecast/lightgbm) — o custo marginal real é ~185 MB.
**Diff do lock:** removidos todos os `nvidia-*` e `triton`; adicionados
torch/lightning/pytorch-lightning/pytorch-forecasting/optuna/torchmetrics/
scikit-base/colorlog. `numpy 2.5.0`, `pandas 2.3.3`, `scipy 1.18.0` e
`scikit-learn 1.9.0` **inalterados** — a guarda contra rebaixamento silencioso
das fixtures-oráculo passou.

### 2026-08-09 — [deviation] Task 01 — dois call sites de instalação além dos planejados — Claude (Opus 5)
**Contexto:** o Checkpoint C do bloco 1 (dois revisores, convergentes) apontou
que a migração para `uv sync --locked` cobriu `Makefile`, `Dockerfile` e CI, mas
deixou de fora `.devcontainer/devcontainer.json` (`postCreateCommand`) e o
fallback de `scripts/worktree-new.py`.
**Razão:** o devcontainer é o ambiente de dev REAL desta máquina e roda **depois**
do build, sobre o bind mount — ele recriava o venv com `uv pip install`,
descartando o install correto da imagem. Deixá-lo fora tornaria a migração inócua
exatamente onde ela mais importa. Corrigido em `[5.4/task-01-fix]`; a lista de
arquivos da Task 01 fica com 7 em vez de 5, o que registro aqui em vez de
silenciar.

### 2026-08-09 — [deviation] Task 01 — a premissa do racional estava errada — Claude (Opus 5)
**Contexto:** concept §1, ADR 5.4.0003, `pyproject.toml` e `Dockerfile`
afirmavam que `uv pip` **ignora** `[tool.uv.sources]`, e que por isso a imagem
baixaria a variante CUDA.
**Medido (uv 0.11.28, alvo linux):** `uv pip compile --extra dev` resolve
`torch==2.13.0+cpu` e **zero** pacotes `nvidia-*`; só com `--no-sources` a
resolução volta para CUDA (16 pacotes `nvidia-*` + `triton`). Ou seja, `uv pip`
**honra** as sources.
**Razão da correção:** a migração continua certa, mas pelo outro motivo — o que
`uv pip` não consome é o `uv.lock`: ele re-resolve a cada execução e pode
instalar um conjunto que ninguém revisou. Acertar o motivo importa porque é o que
a próxima pessoa vai ler ao mexer no caminho de instalação. Texto corrigido no
concept §1, no ADR 5.4.0003, no `pyproject.toml` e no `Dockerfile`.

### 2026-08-09 — [deviation] Task 01 — probe da imagem por `docker run`, não `docker compose run` — Claude (Opus 5)
**Contexto:** o comando de verificação escrito no plano usava
`docker compose run --rm app ...`.
**Razão:** `docker-compose.yml` monta o volume nomeado `app-venv` sobre
`/app/.venv`, então um probe via compose inspeciona o **volume** (possivelmente
anterior à Stage) e não a imagem — o falso verde que o próprio critério dizia
querer evitar. A verificação executada foi
`docker run --rm --entrypoint sh financial_forecasting-app:dev -lc '...'`, que
devolveu `torch 2.13.0+cpu` e nenhum pacote CUDA/triton. Consequência operacional
registrada: quem já tinha a stack de pé precisa de `docker compose down -v` para
o volume ser recriado.

### 2026-08-09 — [deviation] Task 01 — `importorskip("torch")` deixou de guardar o que declarava — Claude (Opus 5)
**Contexto:** `tests/integration/features/feature_engineering/test_build_dataset_aapl.py`
usava `pytest.importorskip("torch")` como procuração para "o extra `sentiment`
está instalado".
**Razão:** com `torch` promovido a dependência principal, a guarda passou a
sempre passar. Com bronze presente, o teste seguiria até o
`_LazyFinbertSentimentModel`, que importa `transformers` e estouraria
`ImportError` no meio do pipeline — onde o desenho quer um skip limpo. Trocado
para `importorskip("transformers")`. Invisível no CI hoje (não há bronze), o que
é justamente por que cairia em silêncio mais adiante.

### 2026-08-09 — [decision] Task 01 — `make install` sem `--locked` — Claude (Opus 5)
**Contexto:** a migração pôs `--locked` em todos os alvos, inclusive `install`.
**Razão:** o `help` descreve `install` como "após mudar pyproject.toml" —
exatamente o caso em que `--locked` aborta. `install` re-resolve e atualiza o
lock (que entra no commit junto); `--locked` fica em `setup`, Dockerfile,
devcontainer e CI, onde o objetivo é reproduzir o conjunto revisado, não mudá-lo.

### 2026-08-09 — [finding] Task 01 — a imagem `runtime` passou a carregar a pilha de deep learning — Claude (Opus 5)
**Contexto:** com `torch`/`lightning`/`pytorch-forecasting`/`optuna` em
`[project.dependencies]`, a stage `runtime` — cujo propósito declarado é imagem
slim sem dev deps — instala todos eles (~700 MB a mais). O ADR 5.4.0003
precificou o custo no CI, não no artefato de deploy. `optuna` em particular é
ferramenta exploratória e não tem função em produção.
**Stage candidata: 7.1-inference-engine**, que é quando o runtime deixa de ser
hipotético e se sabe se a superfície de inferência serve o TFT. Se servir, a
pilha é legítima ali; se não, o caminho é um extra `modeling` que o CI instala e
o runtime não. Registrado agora para a decisão não ser tomada por omissão.

### 2026-08-09 — [decision] Task 02 — prova de quebra dos gates, saída literal — Claude (Opus 5)
**Contexto:** A14 exige a prova executada e revertida, com saída no relatório.
**Executado:** `import torch` em `train_gbm_quantile.py` →
`Contracts: 11 kept, 1 broken`, exit **1**, com a mensagem
`financial_forecasting.features.modeling.application is not allowed to import
torch`. Idem `import optuna` → `Contracts: 11 kept, 1 broken`, exit **1**.
Revertidos → `Contracts: 12 kept, 0 broken`, exit **0**.

### 2026-08-09 — [deviation] Task 04 — fake: lista de não-cobertura ampliada e C3-monitor coberto — Claude (Opus 5)
**Contexto:** o Checkpoint C mostrou que a docstring do fake declarava só C5,
C10 e A4(c) como não-cobertos, e que o ramo de C3 por **monitor** vazio é
inalcançável sob a geometria do splitter (o `if not fitted` dispara antes),
ficando sem teste nas duas pernas.
**Razão:** duas correções de honestidade da cobertura. (a) A lista passou a
incluir **A4(a)/A4(b)** — a saída do fake não depende de `calib`, então uma prova
de anti-vazamento escrita sobre ele seria vácua — e o **guardrail I5**, porque a
grade do fake é monótona por construção e nunca exercita o rearranjo; quem
escrever o teste do use case (Task 05) precisa de uma grade cruzada de propósito.
(b) O ramo de monitor de C3 ganhou teste por chamada direta com `early_stop` na
cauda do painel. Também documentei que o determinismo do fake é ausência de
estado, não semeadura — ele não lê `params.seed`, então essa cláusula de I9 é da
perna real.

### 2026-08-09 — [deviation] cláusula de I8 migrou da Task 08 para a 09 — Claude (Opus 5)
**Contexto:** o plano punha "exatamente um ajuste por fold" (cláusula de I8 em
A2) como critério da Task 08.
**Razão:** a Task 08 entrega o seam `fit(...)`; quem pode ser contado é
`train_and_predict`, que só existe na Task 09. Contar ajustes dentro da própria
`fit` seria tautológico. A asserção foi para
`test_pf_tft_prediction.py::TestSingleFitPerCall`, com `monkeypatch` contando
chamadas de `fit`. Nenhuma cobertura perdida — só deslocada uma Task adiante.

### 2026-08-09 — [decision] decodificador variável gera mais de uma amostra por decisão — Claude (Opus 5)
**Contexto:** com `min_prediction_length=1` no dataset de predição (necessário
para a regra de cauda de I16/D2), a `pytorch-forecasting` gera **também** as
janelas curtas: na geometria canônica a decisão 49 aparece com decodificador de
comprimento 2 **e** de comprimento 1. O plano não previa a duplicata.
**Razão:** o adapter mantém, por decisão, a amostra de decodificador **mais
longo**. Treino e monitor usam sempre `max_horizon` passos, então a janela longa
é a geometria com que o modelo foi treinado; ficar com a curta avaliaria o
candidato numa forma de entrada que ele nunca viu — e faria `h=2` desaparecer da
decisão 49, quebrando a contagem de A13. Reversível-barata e ancorada em D2
(a perda do paper é sobre o decodificador completo), então decidida sem
pergunta, com o teste
`TestAlignment::test_longest_decoder_wins_when_a_decision_repeats` pinando a
escolha.

### 2026-08-11 — [fix] Checkpoint C dos blocos 4–5: 3 mutações sobreviventes mortas — Claude (Opus 5)
**Contexto:** o revisor adversarial rodou 11 mutações sobre as Tasks 10–14; três
sobreviveram à suíte inteira, mais um achado sistêmico de configuração.
**Razão e correção, uma a uma:**

- **F1 (sistêmico, fora da 5.4):** `exclude_lines` do `pyproject.toml` trazia o
  padrão `\.\.\.` **sem âncora**. Qualquer linha contendo três pontos — corpo de
  `Protocol`, mas também docstrings e reticências em comentários — saía da
  medição, e com ela FUNÇÕES INTEIRAS (o `split()` do `WalkForwardSplitter`
  entre elas). Trocado por `^\s*\.\.\.\s*$`. A remedição expôs 505 statements
  antes invisíveis e o gate seguiu verde (97,76%) — o achado é de confiança na
  métrica, não de dívida de teste.
- **F2 (M2 sobreviveu):** nenhum teste asseria QUAL valor chega ao
  `HyperparameterSearch.tell`; uma varredura que alimentasse o TPE com uma
  constante — busca aleatória disfarçada — mantinha o DTO de saída correto e a
  suíte verde. `TestObjectiveReachesTheStudy` agora pina
  `objectives == {n: min(history)}` e que trial falho não recebe objetivo.
- **F3:** `params = replace(...)` estava FORA do `try` do trial, então um
  `TypeError` de recasting derrubava a varredura inteira em vez de descartar o
  trial. Movido para dentro; `except` ampliado para `(ValueError, RuntimeError,
  TypeError)`.
- **F4 (M4 sobreviveu):** trocar `folds[-1]` por `folds[0]` não reprovava nada.
  `TestFoldChoice` recalcula os folds pelo splitter e assere os índices de treino
  do último.
- **F5 (M11 sobreviveu):** a guarda anti-suíte-de-uma-perna era vácua —
  `isinstance(x, Fake | Real)` é satisfeita pelo fake nas DUAS parametrizações.
  Uma fixture que devolvesse sempre o fake apagaria a perna real (e com ela C5,
  C10, A4c) com 40 testes verdes. Nos dois contratos a fixture virou
  `leg` + `trainer(leg)`, e a asserção amarra parâmetro ao TIPO.
- **F6:** `run_tft_sweep.py` estava em 88%, abaixo do mínimo por arquivo de A17.
  Cobertos absorção de falha do tracker, C1, C6 e as cláusulas restantes de C2 —
  96%.
- **F7:** a Task 14 listava `tests/unit/shared/test_composition_root.py` como
  arquivo a modificar e ele não fora tocado; o e2e só asseria `is not None`.
  Três testes novos: colaboradores compartilhados (I9), proxies lazy sem
  delegate construído, e a AUSÊNCIA de `_persist_predictions`/
  `_analytics_repository` no `RunTftSweep` — é essa asserção negativa que
  impede um wiring futuro de reintroduzir o vazamento que ADR 5.4.0005 barra.
- **F9:** `_LazyPfTftTrainer.train_and_predict` usava `**kwargs: object` com
  `type: ignore`, o que aceitava silenciosamente qualquer chamada errada.
  Reescrito espelhando o port campo a campo; o `type: ignore` caiu.
- **F10:** o port não tinha como marcar trial inviável. Um objetivo inventado
  contaminaria o amostrador e deixar pendente cria zumbi no estudo. Adicionado
  `fail(*, trial_number)` ao Protocol, ao fake e ao adapter
  (`study.tell(..., state=TrialState.FAIL)`).

### 2026-08-11 — [finding] duplicação de `_load_dataset` entre `TrainTft` e `RunTftSweep` — escalado para a 5.5 — Claude (Opus 5)
**Contexto:** os dois use cases repetem a leitura do dataset TFT (read + C1 + C6
+ ordenação temporal) e os três *helpers* de tipagem de linha
(`_timestamp_of`, `_target_return_of`, `_feature_value_of`) — cerca de 55 linhas.
**Por que NÃO foi extraído agora:** (a) as duas cópias já **divergem** — a do
treino devolve também os timestamps ISO e ergue "nothing to train", a da
varredura devolve 3-tupla e ergue "nothing to sweep"; uma extração hoje teria de
parametrizar as duas diferenças no chute de qual o terceiro chamador vai querer;
(b) `docs/LAYOUT.md` reserva `application/use_cases/` para **um arquivo por use
case**, e nem `domain/services/` (isto lê por port) nem uma pasta nova servem
sem justificativa de convenção; (c) com dois chamadores a forma certa ainda não
está determinada. A 5.5 (avaliação) traz o terceiro consumidor do mesmo dataset
e é o ponto natural de decidir a assinatura — registrado aqui para não virar
dívida silenciosa.

### 2026-08-11 — [decision] Task 15 — gate agregado, cobertura por arquivo e R1/R2 finais — Claude (Opus 5)
**Bloco YAML do roadmap reconciliado** com a entrega: `contratos_introduzidos`
passou de 2 para 4 (`HyperparameterSearch` e `RunTftSweep` entraram porque ADR
5.4.0005 põe o laço de trials no use case, não no adapter) e
`arquivos_a_criar` foi desdobrado — `optuna_sweep.py` virou `optuna_search.py`
(o port é uma **busca**; a varredura é o use case), o smoke único virou três
e2e por seam do adapter mais o e2e do use case, e
`test_known_unknown_typing.py` virou teste do use case. Linha da tabela de
Stages: `draft` → `done`; `updated_at`/`last_reviewed_at` do roadmap para
2026-08-11.

**Gate agregado (Docker, `uv run pytest tests/`):**

```
1659 passed, 23 skipped in 321.20s (0:05:21)
TOTAL 4162 stmts, 85 missed, 98%
Required test coverage of 90.0% reached. Total coverage: 97.96%
```

**Cobertura por arquivo tocado** (`term-missing`, todos ≥ 90% — critério de A17):

| arquivo | stmts | miss | % |
|---|---|---|---|
| `ports/out/tft_trainer.py` | 57 | 0 | 100% |
| `ports/out/hyperparameter_search.py` | 38 | 0 | 100% |
| `use_cases/train_tft.py` | 201 | 6 | 97% |
| `use_cases/run_tft_sweep.py` | 140 | 6 | 96% |
| `adapters/out/pytorch_forecasting/pf_tft_trainer.py` | 183 | 3 | 98% |
| `adapters/out/optuna/optuna_search.py` | 43 | 2 | 95% |
| `shared/infrastructure/config/settings.py` | 17 | 0 | 100% |
| `composition_root.py` | 136 | 14 | 90% |

**Justificativa do piso do `composition_root.py`** (90%, o mais baixo): as
linhas descobertas 299–320 são os corpos DELEGANTES dos proxies lazy
(`_LazyPfTftTrainer.train_and_predict`, os cinco métodos de
`_LazyOptunaSearch`). Exercitá-las é, por construção, importar torch/optuna —
exatamente o que o proxy existe para adiar. Cobri-las num unit test do
composition root pagaria ~5 s de import em toda rodada da suíte para provar uma
delegação de uma linha; o e2e `test_train_tft.py` já atravessa esse caminho com
o adapter real, e `test_composition_root.py` assere a superfície do proxy e que
o delegate NÃO foi construído. É custo desproporcional, não buraco de teste.

**R1 (instalação) — risco não materializou.** Medido na Task 01 dentro do
Docker: 3 min 11 s antes da migração para `uv sync --locked`, 3 min 18 s depois
(+7 s). O concept estimava ~8 min; a estimativa estava conservadora demais.

**R2 (suite do adapter) — risco não materializou.** `test_pf_tft_*`:
`45 passed in 28.39s`, contra o limiar de ~3 min do plano. Nenhuma marcação
`slow` foi necessária. O teste mais caro da Stage não é do adapter e sim o e2e
de determinismo (`test_two_isolated_runs_agree`, 32,01 s), que treina DUAS vezes
por desenho — é o preço de provar I9, não desperdício.

### 2026-08-11 — [fix] auditoria de testes independente: 27 mutações, 5 sobreviventes mortas — Claude (Opus 5)
**Contexto:** auditor independente rodou **27 mutações semânticas reais** sobre
os seis arquivos de produção da Stage, com árvore commitada em `d43ea57`.
Resultado: 22 mortas, 5 sobreviventes. Os invariantes que são a razão de existir
da Stage — I4(a) monitor, I4(b)/I8 normalizador, I7 `calib` fora de ajuste e
seleção, I14 isolamento estrutural da varredura, A5 restauração do checkpoint,
I15/I16 recorte e cauda — todos morreram, incluindo os casos estruturais.
Zero skips na 5.4. Correções das cinco sobreviventes, cada uma verificada
re-aplicando a mutação original:

- **S1 (M3 — teto do quadro de predição).** A geometria canônica põe o bloco de
  teste na PONTA do painel, então `max(test) + max_horizon + 1 > len(painel)` e
  o recorte é um **no-op**: apagá-lo não mudava nada. A garantia inteira estava
  no filtro `requested_decisions` — uma camada, não as duas que a docstring
  afirma. `test_prediction_frame_has_a_ceiling_on_a_non_final_fold` mede o teto
  onde ele é observável: painel de 64 sessões, teste em `[49,54)`, e assere
  `max(prediction.data["time"]) == max(test) + max_horizon`. Verificado:
  com `frame` inteiro em vez de `frame.iloc[:...]`, `1 failed, 19 passed`.
- **S2 (M11 — "decodificador mais longo vence").** Indistinguível de "a primeira
  amostra vence": a `pytorch-forecasting` hoje entrega a longa primeiro, então
  a suíte era refém da ordenação interna da biblioteca. Um `batch_size`, um
  sampler ou um release diferente faria decisões de teste serem avaliadas com
  decodificador de 1 passo — geometria que o modelo nunca viu no treino — e
  `h=2` sumiria em silêncio, quebrando a paridade de base amostral com a 5.3.
  `test_the_rule_is_length_and_not_arrival_order` chama `_emit` com um
  modelo-stub cuja ordem é a INVERSA. Verificado: com "primeira vence",
  `1 failed, 14 passed`.
- **S3 (M17 — tipagem na identidade do run). A mais grave.** O teste
  `test_typing_is_part_of_the_run_identity` já existia e passava — **pelo motivo
  errado**. `feature_names = unknown_names + known_names`, então mover a
  PRIMEIRA spec de `unknown` para `known` também muda a ORDEM da lista, e o
  run_id diferia por ordem mesmo com `known_feature_names` fora do payload. O
  cenário de colisão real é mover a ÚLTIMA spec `unknown`: ela cai imediatamente
  antes do calendário e a lista concatenada fica byte a byte idêntica. O teste
  agora move a última e **assere `first_columns == second_columns`** antes de
  comparar os run_id — é essa asserção do meio que separa "a tipagem entra na
  identidade" de "a ordem mudou". Estendido também a `config_signature`, que
  tem a mesma forma e é por onde a 5.5 reconhece "mesma configuração".
  Verificado: sem `known_feature_names` no payload, `1 failed, 30 passed`.
- **S4/S5 (M25/M26 — guarda de sanidade do `_LossHistory`).** D11 é defendido em
  dois lugares (a guarda no callback e `num_sanity_val_steps=0` no `Trainer`) e
  `test_history_has_one_entry_per_executed_epoch` só reprovava se AS DUAS
  caíssem. Risco evolutivo: quem reabilitar a passagem de sanidade para depurar
  passa a depender só da guarda, sem prova de que ela existe — e uma entrada
  antes da época 0 desloca o índice inteiro, quebrando `best_epoch == argmin`,
  de que A5 depende. `test_the_sanity_guard_holds_on_its_own` chama o gancho
  direto com um trainer-stub. Verificado: sem a guarda, `1 failed, 12 passed`.

**Não corrigido, por desenho:** o auditor apontou três invariantes com **prova
em ponto único** (artefato ↔ `best_epoch`; monitor/predição herdam o
normalizador; tipo explícito do normalizador). Não é vácuo — cada um TEM teste e
cada um morreu sob mutação (M9, M6, M7). Duplicar a prova não aumentaria
garantia, só custo de manutenção; fica registrado como fragilidade a exclusões
futuras.

### 2026-08-11 — [decision] Gate de saída da Stage 5.4 — evidência literal — Claude (Opus 5)

Todos os itens do checklist de fechamento (§3) verificados **dentro do Docker**,
com a saída colada abaixo. HEAD `5519a30`, árvore limpa.

**`make check` — componentes, um a um:**

```
--- ruff ---
All checks passed!
--- mypy ---
Success: no issues found in 176 source files
--- layout ---
PASSOU — nenhuma violação de arquitetura encontrada.
--- import-linter ---
Contracts: 12 kept, 0 broken.
--- docs (check_technical_postexec) ---
OK — 1 arquivo(s) validado(s).
```

**Suíte + cobertura:**

```
1662 passed, 23 skipped in 307.14s (0:05:07)
TOTAL 4162 stmts, 84 missed, 98%
Required test coverage of 90.0% reached. Total coverage: 97.98%
```

**A17 — cobertura por arquivo tocado** (todos ≥ 90%):

```
composition_root.py                              136  14   90%   167-175, 179, 299-305, 308, 311, 314, 317, 320
adapters/out/optuna/optuna_search.py              43   2   95%   84-85
adapters/out/pytorch_forecasting/pf_tft_trainer.py 183  2   99%   393-398
application/ports/out/hyperparameter_search.py    38   0  100%
application/ports/out/tft_trainer.py              57   0  100%
application/use_cases/run_tft_sweep.py           140   6   96%   291-292, 359, 366, 373, 375
application/use_cases/train_tft.py               201   6   97%   241, 452-453, 671, 679, 689
```

O piso (`composition_root.py`, 90%) está justificado na entrada da Task 15: as
linhas 299–320 são os corpos delegantes dos proxies lazy, e exercitá-las é, por
construção, importar torch/optuna — o que o proxy existe para adiar.

**A14 — as duas provas de quebra dos gates, executadas e revertidas.** Com
`import torch` em `train_tft.py` e `import optuna` em `run_tft_sweep.py`:

```
Application/domain não importam torch/lightning/pytorch_forecasting (só o adapter) BROKEN
  torch: torch (l.691)
Application/domain não importam optuna (só o adapter) BROKEN
  optuna: -> optuna (l.377)
Contracts: 10 kept, 2 broken.
```

Os contratos 11 e 12 não são decorativos: eles reprovam de fato o vazamento que
declaram barrar. Árvore revertida e `lint-imports` de volta a 12/0.

**Probe de torch CPU dentro da imagem (ADR 5.4.0003, decisão B1 do usuário):**

```
2.13.0+cpu
torch.cuda.is_available() -> False
uv pip list | grep -iE "^nvidia|cuda"  ->  (vazio)
torch        2.13.0+cpu
torchmetrics 1.9.0
```

Nenhum pacote `nvidia-*` na imagem — o índice `pytorch-cpu` do `[tool.uv.sources]`
está sendo consumido pelo `uv sync --locked`, que era a razão da migração da
Task 01.

**ADRs 5.4.0001–0006:** todos em `status: accepted` (verificado por grep).

**Checklist de fechamento:**

- [x] A1–A17 satisfeitos; divergências registradas nesta §7.
- [x] `make check` verde, saída colada acima.
- [x] Cobertura ≥ 90% global (97,98%) e por arquivo tocado (tabela acima).
- [x] `check_technical_postexec.py` verde.
- [x] Auditoria de testes independente: 27 mutações, 22 mortas, 5 sobreviventes
      **corrigidas e re-verificadas** (entrada anterior desta §7).
- [x] Checkpoints A (3 rodadas), B (2 rodadas) e C (5 rodadas, uma por bloco)
      com todos os achados dispostos por escrito.
- [x] §7 reflete a execução real, incluindo os erros de percurso.
- [x] Finding escalado com Stage candidata: duplicação de `_load_dataset` → 5.5.
- [x] `roadmap.md` com a 5.4 em `done` e datas de hoje.
- [x] ADRs 5.4.0001–0006 em `accepted`.

<!-- END: post-execution -->
