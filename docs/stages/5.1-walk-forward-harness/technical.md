---
title: Technical — Stage 5.1 — Harness de walk-forward (purga + embargo + calib dedicado)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), TDD inside-out no BC modeling (domínio puro)
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, walk-forward-harness, modeling, purge, embargo, calib, fold-split, scope-spec, split-fingerprint, dedup]
status: done
created_at: 2026-07-04
updated_at: 2026-07-04
stage_id: 5.1-walk-forward-harness
stage_title: Harness de walk-forward
step_id: 5
step_title: Modelagem, baselines e treino
depends_on: [3.5-dataset-builder-and-contracts, 4.3-prediction-persister, 2.4-trading-calendar, 1.4-identity-and-fingerprints]
concept_ref: ./concept.md
issue_id: 40
branch: feat/40-5-1-walk-forward-harness
tasks_count: 6
---

# Technical — Stage 5.1 — Harness de walk-forward

> **Como usar (para code assistant):** ler §1, executar Tasks em ordem (§2),
> 1 Task = 1 commit, não avançar sem verificação verde; ao fim validar §3 e
> registrar §7. Commits seguem [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(<scope>): <descrição> [5.1/task-NN]`, escopo `modeling` (ou
> `identity` para a Task da 1.4), `Refs #40`.

## 1. Contexto e estratégia de execução

### Resumo

Construímos o **BC `modeling`** (só `domain` nesta Stage) com: os VOs `ScopeSpec`
e `FoldSplit`, o serviço `WalkForwardSplitter` (folds expansivos com purga+embargo
em dias de pregão via `TradingCalendar`, val particionada em early-stop + calib
dedicado adjacente ao test) e o serviço puro `deduplicate_operationally_latest`.
Estendemos o VO compartilhado `SplitFingerprint` (1.4) com um campo opcional
`calib` (retrocompatível). Tudo domínio puro (stdlib-only), sem I/O.

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`), respeitando dependências entre
contratos: primeiro o scaffolding do BC + registro na fitness function (para o
gate cobrir `modeling.domain` desde o 1º commit), depois a extensão do
`SplitFingerprint` (que `FoldSplit` consome), depois os VOs (`ScopeSpec`,
`FoldSplit`), depois o serviço que os compõe (`WalkForwardSplitter`), e por fim o
serviço independente de dedup. Cada Task traz seu teste no mesmo commit; cada
commit deixa o build verde.

**Exceção de ordem declarada:** a Task 02 toca `shared/domain` (Stage 1.4), fora
do BC `modeling`, por ser a extensão retrocompatível do `SplitFingerprint`
decidida em ADR 5.1.0003 (contrato consumido). É intencional e mínima.

**Exceção de contagem de arquivos declarada (§4.3 critério 2):** a Task 01 cria
vários `__init__.py` vazios (scaffolding de pacotes src+tests do BC novo) além de
2 edições reais (`.importlinter`, teste de arquitetura). O excedente é boilerplate
mecânico, front-carregado para que as Tasks seguintes toquem só arquivos reais.

### Pré-condições

- Stages `3.5`, `4.3`, `2.4`, `1.4` em `done` e mergeadas em `develop`.
- `.importlinter` com `exclude_type_checking_imports = True` (permite o domínio
  tipar `hasher: Hasher` sob `TYPE_CHECKING` sem violar `hexagonal-layers`).
- Working tree na branch `feat/40-5-1-walk-forward-harness`.

### Premissas técnicas

- Python 3.12; `uv` para deps; `make check` roda ruff + mypy strict +
  `lint-imports` + `check_layout` + pytest.
- Timestamps trafegam como `date` no cálculo e como strings ISO8601 em
  `FoldSplit`/`SplitFingerprint`.

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── shared/domain/value_objects/split_fingerprint.py        # MODIFICADO (calib opcional)
└── features/modeling/                                       # NOVO BC
    ├── __init__.py
    ├── application/__init__.py                              # placeholder (layers contract)
    └── domain/
        ├── __init__.py
        ├── value_objects/
        │   ├── __init__.py
        │   ├── scope_spec.py
        │   └── fold_split.py
        └── services/
            ├── __init__.py
            ├── walk_forward_splitter.py
            └── operationally_latest_dedup.py
tests/
├── unit/features/modeling/domain/{value_objects,services}/  # NOVO (com __init__.py)
│   ├── value_objects/{test_scope_spec.py, test_fold_split.py}
│   └── services/{test_walk_forward_purge_embargo.py, test_val_calibration_partition.py, test_operationally_latest_dedup.py}
├── unit/shared/domain/value_objects/test_split_fingerprint.py  # MODIFICADO (caso 4-vias)
└── architecture/test_import_contracts.py                    # MODIFICADO (modeling.domain purity)
.importlinter                                                # MODIFICADO (registra modeling)
```

## 2. Tasks

### Task 01 — Scaffolding do BC `modeling` + registro na fitness function

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/__init__.py`
  - `src/financial_forecasting/features/modeling/application/__init__.py` (placeholder p/ o contrato `hexagonal-layers`, seguindo o precedente do `analytics_store`)
  - `src/financial_forecasting/features/modeling/domain/__init__.py`
  - `src/financial_forecasting/features/modeling/domain/value_objects/__init__.py`
  - `src/financial_forecasting/features/modeling/domain/services/__init__.py`
  - `tests/unit/features/modeling/__init__.py`, `.../domain/__init__.py`, `.../domain/value_objects/__init__.py`, `.../domain/services/__init__.py`
- **Arquivos a modificar:**
  - `.importlinter` (adiciona `financial_forecasting.features.modeling` ao container do `hexagonal-layers`; adiciona `financial_forecasting.features.modeling.domain` a `source_modules` de `domain-purity`)
  - `tests/architecture/test_import_contracts.py` (estende a prova de reação a violação real para cobrir `modeling.domain` importando `pandas`, se o teste for parametrizado por módulo)
- **O que fazer:** criar os pacotes vazios do BC e **registrar `modeling` nas
  fitness functions**, de modo que o gate `domain-purity` cubra `modeling.domain`
  desde já. NÃO adicionar `modeling` ao `store-no-storage-leak` (o domínio de 5.1
  não consome o `MedallionStore`).
- **Detalhes técnicos:** `hexagonal-layers` usa `exhaustive = False` + `(adapters)`
  opcional — a ausência de `adapters` e o `application` vazio são tolerados
  (precedente `analytics_store`, `.importlinter` linhas 59-63).
- **Critério de aceite:** `uv run lint-imports` verde com `modeling` registrado;
  teste de arquitetura verde; `import pandas` em `modeling.domain` reprova (prova
  por quebra intencional revertida, registrada em §7).
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  pytest tests/architecture/test_import_contracts.py -v
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `chore(modeling): scaffolding do BC e registro na fitness function [5.1/task-01]`

---

### Task 02 — Estender `SplitFingerprint` (1.4) para 4 vias (calib opcional)

- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/domain/value_objects/split_fingerprint.py`
  - `tests/unit/shared/domain/value_objects/test_split_fingerprint.py`
- **O que fazer:** adicionar a `compute` um parâmetro keyword-only
  `calib: Sequence[str] | None = None`; quando não-`None`, incluir
  `"calib": sorted(calib)` no payload. Quando `None`, o payload é **byte-idêntico**
  ao atual (retrocompat).
- **Detalhes técnicos:** ordem das chaves no payload é irrelevante para o hash
  (`sort_keys` no `Hasher`), mas a presença/ausência da chave `calib` muda o
  conteúdo — por isso só incluir quando fornecido. ADR 5.1.0003.
- **Critério de aceite:** novo teste 4-vias (com calib) difere do 3-vias; teste
  provando que uma chamada 3-vias produz a **mesma** impressão de antes da mudança
  (retrocompat); casos 3-vias existentes seguem verdes.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/shared/domain/value_objects/test_split_fingerprint.py -v
  mypy --strict src/financial_forecasting/shared/domain/value_objects/split_fingerprint.py
  ```
- **Commit sugerido:** `feat(identity): SplitFingerprint aceita calib opcional (split 4-vias) [5.1/task-02]`

---

### Task 03 — VO `ScopeSpec`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/value_objects/scope_spec.py`
  - `tests/unit/features/modeling/domain/value_objects/test_scope_spec.py`
- **O que fazer:** `@dataclass(frozen=True)` com `asset_id: str`,
  `feature_set_name: str`, `max_horizon: int`, `cohort_id: str | None = None`.
  `__post_init__` valida não-vazios e `max_horizon >= 1` (`ValueError`).
- **Detalhes técnicos:** VO de identidade de cohort (concept §4); `max_horizon`
  fixa a largura da purga do splitter.
- **Critério de aceite:** testes cobrem construção válida, frozen
  (`FrozenInstanceError`), e cada erro de validação (`max_horizon` 0/negativo,
  strings vazias).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/value_objects/test_scope_spec.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/value_objects/scope_spec.py
  ```
- **Commit sugerido:** `feat(modeling): VO ScopeSpec (identidade de cohort) [5.1/task-03]`

---

### Task 04 — VO `FoldSplit`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/value_objects/fold_split.py`
  - `tests/unit/features/modeling/domain/value_objects/test_fold_split.py`
- **O que fazer:** `@dataclass(frozen=True)` com `fold_index: int`, `train`,
  `early_stop`, `calib`, `test` (`tuple[str, ...]`), `fingerprint: SplitFingerprint`.
  `__post_init__` valida: `fold_index >= 0`; cada lista não-vazia e estritamente
  crescente; as quatro **pairwise disjuntas**; ordenação de bloco
  `max(train) < min(early_stop) < max(early_stop) < min(calib) < max(calib) < min(test)`.
- **Detalhes técnicos:** consome `SplitFingerprint` (import direto de `shared.domain`
  — permitido). Invariantes I1/I2 (concept §5) verificadas na construção, não
  assumidas.
- **Critério de aceite:** testes cobrem construção válida; cada violação
  (sobreposição entre pares, ordem de bloco quebrada, lista vazia, não-crescente)
  ergue `ValueError`; frozen.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/value_objects/test_fold_split.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/value_objects/fold_split.py
  ```
- **Commit sugerido:** `feat(modeling): VO FoldSplit com invariantes de disjunção/ordem [5.1/task-04]`

---

### Task 05 — Serviço `WalkForwardSplitter` (purga + embargo + calib dedicado)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/services/walk_forward_splitter.py`
  - `tests/unit/features/modeling/domain/services/test_walk_forward_purge_embargo.py`
  - `tests/unit/features/modeling/domain/services/test_val_calibration_partition.py`
- **O que fazer:** classe `WalkForwardSplitter(calendar: TradingCalendar)` com
  `split(sessions, scope, *, n_folds, test_size, val_size, calib_size, embargo,
  hasher) -> tuple[FoldSplit, ...]`. Geometria expansiva
  `TRAIN | gap | EARLY_STOP | gap | CALIB | gap | TEST`, `gap = scope.max_horizon
  + embargo`; test blocks ladrilham a cauda; `train` ancora em `sessions[0]`. Usa
  `TradingCalendar.shift_trading_days` para as fronteiras de gap e `is_session`
  para validar a grade. Serializa `date → ISO` e delega a impressão a
  `SplitFingerprint.compute(hasher=hasher, train=…, val=early_stop, calib=…, test=…)`.
- **Detalhes técnicos:** tipar `hasher: Hasher` via `TYPE_CHECKING` (espelha
  `split_fingerprint.py`); janela insuficiente / grade inválida / parâmetros
  inválidos → `ValueError` (sem clamp — concept §6). Erguer, não fabricar.
- **Critério de aceite:**
  - `test_walk_forward_purge_embargo.py`: folds expansivos (I6), ladrilhamento do
    test (I7), distância entre blocos `> max_horizon` sessões (I3) e `>= embargo`
    (I4) com `max_horizon`/`embargo` variados, janela insuficiente ergue.
  - `test_val_calibration_partition.py`: val particionada em early_stop + calib
    (I5), calib adjacente ao test e intocado, disjunção train/early_stop/calib/test
    (I1/I2), fingerprint determinística 4-vias (I8).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/services/test_walk_forward_purge_embargo.py tests/unit/features/modeling/domain/services/test_val_calibration_partition.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/services/walk_forward_splitter.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(modeling): WalkForwardSplitter expansivo com purga+embargo e calib dedicado [5.1/task-05]`

---

### Task 06 — Serviço `deduplicate_operationally_latest`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/domain/services/operationally_latest_dedup.py`
  - `tests/unit/features/modeling/domain/services/test_operationally_latest_dedup.py`
- **O que fazer:** função pura `deduplicate_operationally_latest(records, *,
  alignment_key, operational_rank) -> tuple[T, ...]`: por chave, mantém o de maior
  `operational_rank`; empate exato ergue `ValueError`; ordem de saída = 1ª aparição
  de cada chave.
- **Detalhes técnicos:** genérica (`TypeVar` + `Callable`), stdlib-only. Espelha a
  chave de alinhamento OOS do 4.3 (concept §7 D5), mas sem presumir o tipo do
  registro (predições concretas só em 5.2+).
- **Critério de aceite:** testes cobrem colapso de duplicatas mantendo o maior
  rank, preservação de chaves únicas, ordem determinística, e `ValueError` em
  empate de rank.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/modeling/domain/services/test_operationally_latest_dedup.py -v
  mypy --strict src/financial_forecasting/features/modeling/domain/services/operationally_latest_dedup.py
  ```
- **Commit sugerido:** `feat(modeling): dedup operationally-latest por chave de alinhamento [5.1/task-06]`

## 3. Gate de saída da Stage

### Verificações automatizadas
```bash
make check                 # ruff + mypy strict + lint-imports + check_layout + testes
uv run pytest --cov=financial_forecasting --cov-report=term-missing
python scripts/check_technical_postexec.py docs/stages/5.1-walk-forward-harness/technical.md
```

### Verificações funcionais
- [ ] `WalkForwardSplitter.split` sobre uma grade de sessões-fixture produz folds
      cujas 4 partições são disjuntas, com gaps de purga+embargo em dias de pregão.
- [ ] `import pandas` em qualquer módulo de `modeling.domain` reprova o
      `lint-imports` (quebra intencional revertida).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com check verde.
- [ ] `make check` verde no branch.
- [ ] Cobertura ≥ 90% no diff da Stage.
- [ ] §7 reflete a execução real.
- [ ] `roadmap.md` atualizado (Stage 5.1 `done`, datas) — **no working tree, sem
      commitar** (commit final `stage 5.1: complete` é manual, pós-auditoria).
- [ ] ADRs 5.1.0001/0002/0003 em `accepted`.
- [ ] `concept.md` não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

```
Task 01 (scaffolding+fitness) ─► Task 03 (ScopeSpec) ─┐
Task 02 (SplitFingerprint 4-vias) ─► Task 04 (FoldSplit) ─┼─► Task 05 (WalkForwardSplitter)
                                                          │
Task 01 ─────────────────────────► Task 06 (dedup) ──────┘ (independe de 02-05)
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `hexagonal-layers` reprova por `modeling.application` ausente | criar `application/__init__.py` placeholder (precedente `analytics_store`) — já previsto na Task 01 |
| import-linter conta o import `TYPE_CHECKING` de `Hasher` como runtime | `exclude_type_checking_imports = True` já ativo; se falhar, remover a anotação e usar `object`/Protocol local |
| Geometria de fold difícil de acertar de primeira | escrever primeiro os testes de invariante (I1–I7) com fixtures NYSE pequenas e derivar a implementação até verde |
| Cobertura < 90% em ramos de erro | adicionar casos de erro dedicados (§6 concept) como Tasks-extra `test(...)` |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito e decisões (D1–D5).
- ADRs: [`5.1.0001`](../../adr/5_1_0001-expanding-window-walk-forward.md),
  [`5.1.0002`](../../adr/5_1_0002-dedicated-calibration-partition.md),
  [`5.1.0003`](../../adr/5_1_0003-split-fingerprint-four-way-calib.md);
  relacionados [`0.0.0018`](../../adr/0_0_0018-anti-leakage-non-negotiable.md),
  [`2.4.0001`](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md),
  [`4.3.0001`](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md).
- Skills: `task-ordering-hex`, `ddd-tactical-patterns`, `hex-arch-python`,
  `pytest-with-fakes`, `import-linter-rules`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a Fase 4. Apenas esta seção é editável após
> `status: done`. Cada entrada carrega data + autor.

### 2026-07-05 — [deviation] Task 01 — Claude (Opus 4.8)
**Contexto:** `scripts/check_layout.py` exige que toda feature tenha os diretórios
`domain/`, `application/` **e `adapters/`** (`REQUIRED_FEATURE_DIRS`). O plano
previa só `application/__init__.py` como placeholder (para o `hexagonal-layers`),
mas não o `adapters/`.
**Razão:** criei também `features/modeling/adapters/__init__.py` (vazio) para
satisfazer o gate de estrutura — boilerplate mecânico in-scope, absorvido no
próprio commit da Task 01 (amend). Abaixo do threshold de perguntar.

### 2026-07-05 — [deviation] Task 05 — Claude (Opus 4.8)
**Contexto:** o concept §4 diz que a purga/embargo é "resolvida via
`shift_trading_days`". A implementação resolve as fronteiras por **aritmética de
índice** sobre a grade e **valida** o gap em dias de pregão via
`shift_trading_days` (o `WalkForwardSplitter._assert_trading_day_gap`).
**Razão:** `_validate_grid` já garante que a grade é um run contíguo de sessões
(cada `sessions[i+1] == next_session(sessions[i])`), logo índice == dia de pregão
e o cross-check via `shift_trading_days` é a resolução autoritativa em dias de
pregão. O ramo de erro do cross-check é inalcançável dado esse invariante e ficou
marcado `# pragma: no cover` (padrão do repo, commit `[5.1/--]`). Não muda
contrato nem critério de aceite — segue in-scope.

### 2026-07-05 — [finding] modeling.application — Claude (Opus 4.8)
**Contexto:** nesta Stage `modeling` tem só `domain`; a `application` é um pacote
placeholder vazio e NÃO entrou no contrato `store-no-storage-leak` (o domínio 5.1
não consome o `MedallionStore`).
**Direção sugerida:** quando a `application` de `modeling` nascer e consumir o
`MedallionStore` (carregar o dataset para o splitter/treinadores), registrar
`financial_forecasting.features.modeling.{application,domain}` em
`store-no-storage-leak` — mesma postura de defesa-em-profundidade dos BCs
anteriores (`.importlinter` Contrato 6). **Stage candidata: 5.2** (`RunBaselines`,
1º use case que consome `WalkForwardSplitter` + `MedallionStore`).

<!-- END: post-execution -->
