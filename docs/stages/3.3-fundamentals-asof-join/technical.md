---
title: Technical — Stage 3.3 — Junção as-of backward de fundamentals (feature_engineering)
description: Plano de execução da Stage 3.3 — FundamentalsAsofPolicy (domain puro + fallback 45d + invariante anti-leakage + 3 ratios point-in-time), port-out AsofJoinAdapter (Protocol), fake in-memory, adapter DuckDB ASOF JOIN backward e contract test parametrizado fake↔real
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, fundamentals-asof-join, fundamentals-asof-policy, asof-join-adapter, duckdb, anti-leakage, fallback-45d, safe-ratio, contract-test, hex-arch]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.3-fundamentals-asof-join
stage_title: Junção as-of backward de fundamentals
step_id: 3
step_title: Camada de features (silver)
depends_on: [2.1-medallion-storage-contracts, 2.3-news-fundamentals-ingestion, 2.4-trading-calendar, 3.1-technical-indicators]
concept_ref: ./concept.md
issue_id: 27
branch: feat/27-3-3-fundamentals-asof-join
tasks_count: 5
---

# Technical — Stage 3.3 — Junção as-of backward de fundamentals (`feature_engineering`)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.3/task-NN]`, body em bullets, rodapé `Refs #27`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage).
>    **O commit `stage 3.3: complete` e a marcação `done` no `roadmap.md` são do
>    ORQUESTRADOR, após auditoria independente — NÃO os faça nesta sessão.**
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/27-3-3-fundamentals-asof-join` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

Decompor a lógica monolítica de as-of de fundamentos do old
(`build_tft_dataset_use_case.py`) nas peças hexagonais corretas do BC
`feature_engineering` (container layered desde a 3.1 — **não recriar**): (1) um
**domain service puro** `FundamentalsAsofPolicy` (stdlib-only) que calcula
`effective_date` (`reported_date` OU `fiscal_date_end + 45d` calendário, ledger
H-3), **valida o invariante anti-leakage** (`effective_date <= sample_date` →
`AntiLeakageError`) e expõe os **3 ratios point-in-time** com divisão segura
(`net_margin`/`leverage_ratio`/`cashflow_efficiency`); (2) um **port-out**
`AsofJoinAdapter` (`Protocol` estrutural, sem `duckdb`/`pandas` na fronteira);
(3) um **fake** in-memory comportamental do port; (4) o **adapter DuckDB ASOF JOIN
backward** que traduz o `merge_asof(direction="backward")` do old e re-checa o
invariante (defense-in-depth); (5) o **contract test parametrizado** fake↔real. O
YoY é deferido (ADR `3_3_0002`); os ADRs `0_0_0022`/`3_3_0001`/`3_3_0002` já estão
`accepted` no repo (criados na Fase 3A) — esta Fase **não** os reescreve.

### Estratégia

**Inside-out / TDD** conforme `task-ordering-hex` (Stage vertical-slice tocando
`domain` + `adapters/out`): domain puro + testes primeiro (Task 01), depois o port
`Protocol` (Task 02), depois o **fake** (Task 03) — que torna o contrato testável
**sem** instalar/rodar DuckDB —, depois o **adapter real** + contract test
parametrizado fake↔real (Task 04), e por fim o **gate de gates** + teste-foco do
invariante anti-leakage e confirmação do `import-linter` (Task 05). Cada Task deixa
o build verde; reverter a Task 04 (adapter real) não quebra domain/port/fake.

**Desvios de ordenação declarados** (exceções a `task-ordering-hex`):
- **Não há use case nesta Stage** (D5/concept §1 "fora do escopo": montagem do
  dataset e wiring no `composition_root` são da 3.5). O port-out existe para o
  consumidor futuro (3.4/3.5); aqui o contrato é validado por **fake + contract
  test**, não por um use case. Por isso o passo 2 do skill (port + use case +
  fake) vira **só port + fake** (Tasks 02-03), sem use case.
- **Port (Task 02) e adapter real (Task 04) ficam em Tasks separadas** com o
  **fake entre eles** (Task 03) — regra dura de `task-ordering-hex`/PIPELINE §4.3.

### Pré-condições

- Stages `2.1`, `2.3`, `2.4`, `3.1` em `done` e mergeadas (dependências satisfeitas):
  `MedallionStore` + bronze `fundamental` + `DomainError`; entity `FundamentalReport`;
  `TradingCalendar.trading_day_from_timestamp` raise-sem-clamp; BC
  `feature_engineering` container layered com `store-no-storage-leak`
  (`duckdb` já em `forbidden_modules`) + `domain-purity`.
- ADRs `0_0_0022`, `3_3_0001`, `3_3_0002` presentes em `docs/adr/` com
  `status: accepted` (verificado: já criados na Fase 3A).
- Branch `feat/27-3-3-fundamentals-asof-join` em checkout.

### Premissas técnicas

- Python 3.12, `uv`, `pyproject.toml` já existe; `make check`/`make test` operantes.
- `duckdb` já é dependência do projeto (engine de leitura do `ParquetMedallionStore`,
  2.1) — **sem dependência nova**.
- `FundamentalReport` é importável de
  `financial_forecasting.features.market_data.domain.entities.fundamental_report`
  (a `domain`/`application` do BC `feature_engineering` pode importar `domain`
  cross-BC — LAYOUT §3/§7).
- A sintaxe exata do DuckDB ASOF JOIN na versão pinada (`ASOF JOIN … ON d.date >=
  f.effective_date` vs `MATCH_CONDITION`) é confirmada **na Task 04**; o contract
  test (Task 04) é a rede de segurança (concept Q1) — divergência de sintaxe entra
  como `[decision]`/`[deviation]` na §7, sem mudar o contrato.

### Estrutura de pastas afetada

```
src/financial_forecasting/features/feature_engineering/
├── domain/services/
│   └── fundamentals_asof_policy.py            # Task 01 (NOVO)
├── application/ports/out/
│   └── asof_join.py                           # Task 02 (NOVO — D3, desvio de lista)
└── adapters/out/duckdb/
    ├── __init__.py                            # Task 04 (NOVO)
    └── asof_join_adapter.py                   # Task 04 (NOVO)

tests/
├── unit/features/feature_engineering/
│   ├── domain/
│   │   └── test_fundamentals_asof_policy.py   # Task 01 (NOVO)
│   └── test_asof_anti_leakage_invariant.py    # Task 05 (NOVO)
├── fakes/features/feature_engineering/
│   └── in_memory_asof_join_adapter.py         # Task 03 (NOVO)
└── contract/features/feature_engineering/
    └── test_asof_join_contract.py             # Task 04 (NOVO — parametrizado fake↔real)
```

## 2. Tasks

> Faixa saudável: **3–8 Tasks por Stage**. ≥ 10 = Stage provavelmente
> está grande demais; reabrir Fase 3A para dividir.

### Task 01 — `FundamentalsAsofPolicy` (domain puro: effective_date + invariante + 3 ratios)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/fundamentals_asof_policy.py`
  - `tests/unit/features/feature_engineering/domain/test_fundamentals_asof_policy.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o domain service **puro stdlib-only** `FundamentalsAsofPolicy` com a
  constante `FUNDAMENTALS_FALLBACK_DAYS = 45`, o erro de domínio
  `AntiLeakageError(DomainError)`, o método `effective_date(report) -> date`, o
  método `validate_not_future(effective_date, sample_date) -> None` e os 3 ratios
  estáticos point-in-time com divisão segura.
- **Detalhes técnicos:**
  - Imports permitidos APENAS: `datetime` (`date`, `timedelta`), `math` (para
    detectar `NaN`), a entity `FundamentalReport` (cross-BC `domain` — LAYOUT §3/§7)
    e `DomainError` de `shared/domain/exceptions/base.py`. **SEM**
    `pandas`/`pyarrow`/`duckdb`/`torch`/`pydantic` (I5).
  - `effective_date(report)`: `report.reported_date` se não-`None`; senão
    `report.fiscal_date_end + timedelta(days=FUNDAMENTALS_FALLBACK_DAYS)` (45d
    **calendário** — I2, ledger H-3). Porta `build_tft_dataset_use_case.py:116-143`.
  - `validate_not_future(effective_date, sample_date)`: `if effective_date >
    sample_date: raise AntiLeakageError(...)` com mensagem citando `sample_date`,
    `effective_date` e o ADR `0.0.0018` (I1/C1/D4). `==` e `<` não levantam.
  - `net_margin(net_income, revenue)`, `leverage_ratio(total_liabilities,
    total_shareholder_equity)`, `cashflow_efficiency(operating_cash_flow, revenue)`:
    `@staticmethod`, assinatura `(float | None, float | None) -> float | None`.
    **Divisão segura** (porta de `_safe_ratio` `:256-263`): se numerador é `None`
    **ou** denominador é `None`/`0`/`NaN` → `None`; senão `num / den` (I4/C3). Usar
    helper privado `_safe_ratio(num, den)`.
- **Critério de aceite:**
  - A1: `effective_date` com `reported_date` presente → usa-o; ausente → `fiscal_date_end
    + 45d`; teste-oráculo `Fri 2023-12-01 → Mon 2024-01-15` (sem roll) verde.
  - A2: `validate_not_future`: `>` levanta `AntiLeakageError` (subclasse de `DomainError`,
    verificado por `issubclass`/`isinstance`); `==` e `<` não levantam; mensagem cita
    dia, effective_date e `0.0.0018`.
  - A3: ratios corretos em fixture; `revenue=0`/`None` → `net_margin None`; `equity=0`
    → `leverage_ratio None`; numerador `None` → `None`; `NaN` no denominador → `None`.
  - Stdlib-only: nenhum import de lib de dados.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/feature_engineering/domain/test_fundamentals_asof_policy.py -v
  mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/fundamentals_asof_policy.py
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(feature-engineering): política as-of de fundamentos pura no domínio [3.3/task-01]`

---

### Task 02 — Port-out `AsofJoinAdapter` (`Protocol` estrutural, sem libs de dados)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/application/ports/out/asof_join.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o port-out `AsofJoinAdapter` como `Protocol` estrutural (não ABC), na mesma
  postura de `IndicatorCalculator`/`SentimentModel` (D3 — adiciona arquivo omitido na
  `arquivos_a_criar` do roadmap; registrar `[deviation]` na §7).
- **Detalhes técnicos:**
  - Imports APENAS: `collections.abc` (`Mapping`, `Sequence`), `datetime` (`date`),
    `typing` (`Protocol`). **SEM** `duckdb`/`pandas`/adapters/`FundamentalReport`
    (I7 — a fronteira é só primitivos/`Mapping`).
  - `Row = Mapping[str, object]`.
  - Método único:
    `asof_join_backward(self, *, grid_days: Sequence[date], reports: Sequence[Row]) -> Sequence[Row]`.
  - Docstring fixa a semântica (concept §4): 1 linha por dia de `grid_days`; cada dia
    recebe o **último** `report` cujo `effective_date <= day` (backward); cada `report`
    de entrada traz `effective_date` (já calculado pela policy) + campos fundamentais;
    a saída expõe a coluna de auditoria `fundamentals_effective_date` (I8 — **nunca**
    o nome interno `effective_date`); re-checa o invariante anti-leakage (I1
    defense-in-depth); dia sem fundamento elegível → fundamentos `None` (I3/C4); NÃO
    vaza `duckdb`/`pandas` (I7).
  - **Não** criar use case (não há nesta Stage — ver §1 desvio de ordenação).
- **Critério de aceite:**
  - A4: arquivo existe; `AsofJoinAdapter` é `Protocol`; assinatura
    `asof_join_backward(*, grid_days, reports) -> Sequence[Mapping]`; docstring cobre
    backward + `fundamentals_effective_date`; **sem** import de `duckdb`/`pandas`/adapters;
    `mypy --strict` + `lint-imports` verdes.
- **Comando de verificação:**
  ```bash
  mypy --strict src/financial_forecasting/features/feature_engineering/application/ports/out/asof_join.py
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(feature-engineering): port-out AsofJoinAdapter como Protocol [3.3/task-02]`

---

### Task 03 — Fake `InMemoryAsofJoinAdapter` (comportamental, stdlib-only)

- **Arquivos a criar:**
  - `tests/fakes/features/feature_engineering/in_memory_asof_join_adapter.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Implementar o fake comportamental (não `Mock`, stdlib-only) que satisfaz o
  `Protocol` `AsofJoinAdapter` por duck-typing, com a semântica backward de
  referência. É a base do contract test (Task 04) e torna o contrato testável sem
  DuckDB (ADR `0.0.0021`).
- **Detalhes técnicos:**
  - Imports APENAS stdlib (`collections.abc`, `datetime`) + opcionalmente a policy
    para re-checar o invariante; **sem** `duckdb`/`pandas`.
  - Algoritmo backward puro: para cada `day` de `grid_days`, escolher o report com
    o **maior** `effective_date <= day` (ordenar reports por `effective_date`); montar
    a `Row` de saída com os campos fundamentais + `fundamentals_effective_date =
    effective_date` (renomear na fronteira — I8) + os 3 ratios via
    `FundamentalsAsofPolicy` (ou deixar ratios para o consumidor — ratios entram na
    saída do join conforme concept §9 `ASOF_ROW`; o fake calcula-os via a policy para
    paridade com o real). Dia sem fundamento elegível → campos `None` (I3/C4).
  - Re-checar o invariante anti-leakage (`effective_date <= day`) e levantar
    `AntiLeakageError` se violado (I1 defense-in-depth) — mesma semântica que o real.
  - Determinístico, ordem de `grid_days` preservada.
- **Critério de aceite:**
  - A7: o fake satisfaz o `Protocol` (atribuível a uma variável tipada
    `AsofJoinAdapter` sob `mypy --strict`); produz 1 linha por dia com semântica
    backward + `fundamentals_effective_date`; roda **sem** instalar nada novo.
  - Teste mínimo do fake isolado (smoke) verde, OU coberto integralmente pelo contract
    test da Task 04 (não duplicar assertivas).
- **Comando de verificação:**
  ```bash
  mypy --strict tests/fakes/features/feature_engineering/in_memory_asof_join_adapter.py
  pytest tests/fakes/features/feature_engineering/ -q || true   # fakes não têm teste próprio obrigatório
  ```
- **Commit sugerido:** `test(feature-engineering): fake in-memory do AsofJoinAdapter [3.3/task-03]`

---

### Task 04 — Adapter `AsofJoinDuckdbAdapter` + contract test parametrizado fake↔real

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/adapters/out/duckdb/__init__.py`
  - `src/financial_forecasting/features/feature_engineering/adapters/out/duckdb/asof_join_adapter.py`
  - `tests/contract/features/feature_engineering/test_asof_join_contract.py`
- **Arquivos a modificar:** nenhum (D5: `store-no-storage-leak` já cobre `duckdb`).
- **O que fazer:**
  Implementar `AsofJoinDuckdbAdapter` traduzindo o `merge_asof(direction="backward")`
  do old (`:513-535`) para **DuckDB ASOF JOIN backward**, confinando `duckdb` AQUI
  (I5). Escrever o **contract test parametrizado** que roda o **mesmo** conjunto de
  assertivas contra o fake (Task 03) E o adapter DuckDB real (paridade, ADR `0.0.0021`).
- **Detalhes técnicos:**
  - `import duckdb` **só** neste módulo (e o `pandas` se necessário para materializar
    relações — confinado ao adapter). Satisfaz `AsofJoinAdapter` por duck-typing
    (NÃO herda da `application`).
  - SQL: `ASOF JOIN f ON d.date >= f.effective_date` (último fundamento com
    `effective_date <= date`). Confirmar a sintaxe exata na versão pinada (Q1) — se
    divergir, ajustar e registrar `[decision]`/`[deviation]` na §7.
  - **Defense-in-depth (I1):** após o join, re-checar `effective_date <= day` para cada
    linha materializada e levantar `AntiLeakageError` se violado, mesmo a
    `MATCH_CONDITION`/`ON` já garantindo a condição.
  - Saída: 1 linha por dia de `grid_days`, coluna `fundamentals_effective_date` (rename
    na fronteira — I8), campos fundamentais + 3 ratios (via `FundamentalsAsofPolicy`),
    `None` em dia sem fundamento elegível (I3/C4). Não expor `effective_date` cru.
  - **Contract test parametrizado:** `@pytest.mark.parametrize` sobre
    `[InMemoryAsofJoinAdapter(), AsofJoinDuckdbAdapter()]`; assertivas idênticas:
    (a) as-of backward (último `effective_date <= day`; fundamento NÃO visível antes
    do effective_date — I3); (b) coluna `fundamentals_effective_date` presente e `<= day`
    (I8); (c) fallback 45d aplicado **a montante** (reports já com `effective_date` da
    policy — I2); (d) dia sem fundamento elegível → `None` (C4); (e) `effective_date`
    futura ao dia → `AntiLeakageError` (I1). Oráculo: semântica do old `merge_asof`.
- **Critério de aceite:**
  - A5: `AsofJoinDuckdbAdapter` satisfaz o port; usa DuckDB ASOF JOIN backward; saída
    com 1 linha/dia + último `effective_date <= day` + `fundamentals_effective_date`;
    re-checa o invariante; `effective_date` futura → `AntiLeakageError`; `duckdb` só aqui.
  - A8: contract test parametrizado — fake E DuckDB real passam o **mesmo** conjunto de
    assertivas (paridade fake↔real); cobertura ≥90% no código vivo do BC tocado.
- **Comando de verificação:**
  ```bash
  pytest tests/contract/features/feature_engineering/test_asof_join_contract.py -v
  mypy --strict src/financial_forecasting/features/feature_engineering/adapters/out/duckdb/asof_join_adapter.py
  python scripts/check_layout.py
  lint-imports
  ```
- **Commit sugerido:** `feat(feature-engineering): adapter DuckDB ASOF JOIN backward + contract test [3.3/task-04]`

---

### Task 05 — Teste-foco do invariante anti-leakage + confirmação dos gates

- **Arquivos a criar:**
  - `tests/unit/features/feature_engineering/test_asof_anti_leakage_invariant.py`
- **Arquivos a modificar:** nenhum (D5: confirmar que `store-no-storage-leak` já cobre
  o novo `domain`/port — **sem** editar `.importlinter`; se nenhuma edição for
  necessária, registrar `[deviation]` na §7).
- **O que fazer:**
  Escrever o teste-foco do invariante razão-de-ser da Stage (anti-leakage), e
  confirmar **end-to-end** que os gates `import-linter` (`store-no-storage-leak` +
  `domain-purity`), `check_layout.py`, `mypy --strict`, `ruff` e cobertura ≥90% estão
  verdes para o código novo. Validar a quebra intencional (`import duckdb` no domain
  reprova) e revertê-la.
- **Detalhes técnicos:**
  - `test_asof_anti_leakage_invariant.py` (A6): exercita o invariante na **policy**
    (`validate_not_future`) e no **adapter**/fake (re-check defense-in-depth):
    fundamento visível **só** a partir do `effective_date` (backward, nunca antes —
    I3); `effective_date` futura ao dia → `AntiLeakageError` (I1); saída tem
    `fundamentals_effective_date` (I8); fallback 45d aplicado a montante (I2). Pode
    parametrizar fake↔real para o caminho do adapter (mesma postura do contract test).
  - Confirmar `store-no-storage-leak`: `lint-imports` verde; quebra intencional
    (adicionar `import duckdb` em `fundamentals_asof_policy.py`) faz `lint-imports`
    **reprovar**; reverter. Registrar `[deviation]` se nenhuma edição em `.importlinter`
    for necessária (D5).
- **Critério de aceite:**
  - A6: teste do invariante anti-leakage cobre visibilidade backward, futura → erro,
    coluna de auditoria, fallback a montante.
  - A9: `import-linter` verde cobrindo o novo `domain`/port; `domain-purity` verde;
    quebra intencional reprova e é revertida; `check_layout.py` verde para
    `adapters/out/duckdb`.
  - A10: `make check` + `make test` verdes; cobertura ≥90% no código vivo do BC.
  - A11: ADRs `3_3_0001`/`3_3_0002`/`0_0_0022` em `status: accepted` (já presentes).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/features/feature_engineering/test_asof_anti_leakage_invariant.py -v
  make check
  make test
  ```
- **Commit sugerido:** `test(feature-engineering): invariante anti-leakage do as-of de fundamentos [3.3/task-05]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage ser entregue ao orquestrador
> (que faz auditoria, o commit `stage 3.3: complete` e a marcação `done` no roadmap).
> **Esta sessão NÃO faz o commit de fechamento nem marca o roadmap.**

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
make test                 # todos os testes
lint-imports              # store-no-storage-leak + domain-purity cobrindo o novo domain/port
python scripts/check_layout.py
```

### Verificações funcionais
- [ ] `FundamentalsAsofPolicy.effective_date`: oráculo `Fri 2023-12-01 → Mon 2024-01-15` (I2).
- [ ] `validate_not_future`: `effective_date` futura → `AntiLeakageError` (I1).
- [ ] Contract test parametrizado: fake **e** DuckDB real passam as MESMAS assertivas (A8).
- [ ] Quebra intencional `import duckdb` no domain reprova em `lint-imports` e é revertida (A9).

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Garantido por | Teste(s) |
|---|---|---|
| **I1** — anti-leakage `effective_date <= date` → `AntiLeakageError` | `FundamentalsAsofPolicy.validate_not_future` + re-check no adapter/fake (defense-in-depth) | `test_fundamentals_asof_policy` (A2), `test_asof_anti_leakage_invariant` (A6), contract test caso (e) (A8) |
| **I2** — fallback 45d calendário | `FundamentalsAsofPolicy.effective_date` | `test_fundamentals_asof_policy` oráculo `Fri 2023-12-01 → Mon 2024-01-15` (A1), contract test caso (c) |
| **I3** — visibilidade as-of backward (último `effective_date <= day`; nunca antes) | adapter/fake `asof_join_backward` | contract test caso (a) (A8), `test_asof_anti_leakage_invariant` (A6) |
| **I4** — divisão segura nos 3 ratios | `FundamentalsAsofPolicy` `_safe_ratio` | `test_fundamentals_asof_policy` (A3) |
| **I5** — domain stdlib-only / `duckdb` confinado ao adapter | `store-no-storage-leak` + `domain-purity` + `check_layout.py` | `lint-imports` (A9), quebra intencional revertida |
| **I6** — `TradingCalendar` raise-sem-clamp fora da janela | consumido de 2.4 (não re-implementado aqui) | herdado da 2.4 (fora do escopo de teste novo) |
| **I7** — port `Protocol` + fronteira sem libs de dados | `AsofJoinAdapter` (Protocol); fake/adapter por duck-typing | `mypy --strict` + `lint-imports` (A4), atribuibilidade do fake (A7) |
| **I8** — coluna de auditoria `fundamentals_effective_date` (sem expor `effective_date`) | adapter/fake (rename na fronteira) | contract test caso (b) (A8), `test_asof_anti_leakage_invariant` (A6) |
| **I9** — só ratios point-in-time (YoY deferido) | escopo da policy (sem YoY) | `test_fundamentals_asof_policy` (ausência de YoY, A3); ADR `3_3_0002` |
| **I10** — gates verdes (mypy/ruff/import-linter/check_layout/cobertura ≥90%) | `make check` + `make test` | A10 |

### Checklist de fechamento da Stage (escopo desta sessão)
- [ ] Todas as 5 Tasks commitadas, cada uma com seu check verde, tag `[3.3/task-NN]`,
      rodapé `Refs #27`.
- [ ] `make check` + `make test` verdes no branch.
- [ ] `concept.md` e `technical.md` commitados (`status: done`).
- [ ] ADRs `3_3_0001`/`3_3_0002`/`0_0_0022` em `status: accepted` (já presentes).
- [ ] §7 Execução preenchida com `[decision]`/`[deviation]`/`[finding]` que surgiram.
- [ ] **NÃO** fazer o commit `stage 3.3: complete` nem marcar `done` no `roadmap.md` —
      isso é do ORQUESTRADOR, após auditoria independente.

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out / `task-ordering-hex`):

```
Task 01 (domain: policy) ─► Task 02 (port Protocol) ─► Task 03 (fake) ─► Task 04 (adapter DuckDB + contract test)
   │                                                        │                          │
   └──────────────────────────────────────────────────────┴──────────────────────────┴─► Task 05 (teste anti-leakage + gates)
```

- Task 02 (port) precede Task 04 (adapter que o satisfaz) — regra dura PIPELINE §4.3.
- Task 03 (fake) precede Task 04 (adapter real + contract test parametrizado) —
  `task-ordering-hex` (fake antes do real; CI não acoplado a infra externa).
- Task 01 (policy) é consumida pelo fake (Task 03), pelo adapter (Task 04, ratios +
  re-check) e pelo teste do invariante (Task 05).
- Task 05 fecha os gates depois que todo o código vivo existe.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Sintaxe DuckDB ASOF JOIN difere na versão pinada (`ON` vs `MATCH_CONDITION`) — Q1 | Ajustar o SQL conforme a versão; o contract test (paridade fake↔real, A8) detecta divergência; registrar `[decision]`/`[deviation]` na §7. Contrato (semântica backward, coluna de auditoria, invariante) fica fixo independentemente da sintaxe. |
| DuckDB ASOF backward diverge de `merge_asof(direction="backward")` em empates de data | Definir desempate explícito (último report por `effective_date`; se mesma data, ordem estável) no SQL e no fake; assertivas idênticas no contract test garantem paridade. |
| Cobertura <90% por caminhos de erro do adapter não exercitados | Adicionar casos ao contract test (futura → erro, dia vazio → None); o fake cobre o caminho sem DuckDB. |
| `store-no-storage-leak` não cobrir o novo `domain`/port por engano | A confirmação é a quebra intencional revertida (A9); se faltar cobertura, estender `source_modules` (mas já cobre `feature_engineering.{application,domain}` — D5). |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (escopo, contratos §4,
  invariantes §5, decisões §7 D1-D7, critérios de aceitação §11 A1-A11).
- [`../../overview.md`](../../overview.md) — §3/§6/§7 (anti-leakage estrutural,
  medalhão), §11 (`0.0.0018` anti-leakage, `0.0.0022` engine pandas+duckdb / as-of joins).
- [`../../roadmap.md`](../../roadmap.md) — Stage `3.3-fundamentals-asof-join`
  (`arquivos_a_criar`, DoD, `non_goals`, contratos) e vizinhas 3.4/3.5.
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — H-3 (fallback 45d), §B 3.3 (DuckDB ASOF backward), §B 3.4 (YoY → 3.4).
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches, commits (escopo
  mínimo, body em bullets, `Refs #27`, tag `[3.3/task-NN]`), status.
- ADRs desta Stage: [`../../adr/3_3_0001-duckdb-asof-backward-join.md`](../../adr/3_3_0001-duckdb-asof-backward-join.md),
  [`../../adr/3_3_0002-defer-yoy-fundamentals.md`](../../adr/3_3_0002-defer-yoy-fundamentals.md),
  [`../../adr/0_0_0022-data-engine-pandas-duckdb.md`](../../adr/0_0_0022-data-engine-pandas-duckdb.md);
  fundação [`0.0.0018`](../../adr/0_0_0018-anti-leakage-non-negotiable.md),
  [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md).
- Skills aplicáveis: `hex-arch-python`, `pytest-with-fakes`, `repository-pattern`
  (adapter out), `task-ordering-hex`, `dmls-ch04-feature-engineering-decisions`
  (leakage), `import-linter-rules`.
- Old (semântica/lógica, não implementação):
  `financial-time-series-forecasting/src/use_cases/build_tft_dataset_use_case.py:116-143`
  (`_fundamentals_to_df` fallback 45d), `:256-263` (`_safe_ratio`), `:266-285`
  (ratios point-in-time + YoY deferido), `:513-535` (`merge_asof` backward + rename +
  invariante `ValueError`);
  `tests/unit/use_cases/test_build_tft_dataset_use_case.py:570-686` (testes de
  referência: invariante + fallback `Fri 2023-12-01 → Mon 2024-01-15`).

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
> **recomendada** + razão. Apenas após a decisão, registre a entrada
> abaixo. Na dúvida, **pergunte**.
>
> **Nesta corrida autônoma** (ADR `0.0.0050`): registrar aqui
> `[decision]`/`[deviation]`/`[finding]` conforme política da corrida.
> Desvios já antecipados no concept a registrar quando confirmados:
> **D3** (criar `application/ports/out/asof_join.py` omitido na
> `arquivos_a_criar` → `[deviation]`); **D5** (nenhuma edição em
> `.importlinter`, pois `store-no-storage-leak` já cobre `duckdb` no BC →
> `[deviation]`); **D4** (`AntiLeakageError` vs `ValueError` cru →
> `[decision]`); **Q1** (sintaxe DuckDB ASOF na versão pinada → `[decision]`
> se divergir do esperado).

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
- `[finding]` — gap/observação a tratar em **próxima Stage**.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-06-29 — [deviation] application/ports/out/asof_join.py — Claude (autonomous run)
**Contexto:** O roadmap §3.3 lista `AsofJoinAdapter (port-out)` em
`contratos_introduzidos` mas **omite o arquivo** na `arquivos_a_criar` (D3/concept §7).
**Razão:** A postura hexagonal do BC (`IndicatorCalculator`/`SentimentModel` são
`Protocol` em `application/ports/out/`) exige o arquivo do port para honrar o contrato
sem violar o LAYOUT §3. Criado `application/ports/out/asof_join.py` (Task 02). Desvio de
lista, não de design — sem ADR (já previsto no concept D3).

### 2026-06-29 — [deviation] .importlinter (nenhuma edição) — Claude (autonomous run)
**Contexto:** A `arquivos_a_criar`/`arquivos_a_modificar` cogitava editar `.importlinter`
(D5/concept §7).
**Razão:** O contrato `store-no-storage-leak` já lista
`feature_engineering.{application,domain}` em `source_modules` e `duckdb` em
`forbidden_modules` (Stages 2.1/3.1) — o novo `domain`/port herda a proteção sem
duplicação. **Nenhuma** edição em `.importlinter` foi necessária. Confirmado por quebra
intencional revertida (Task 05/A9): `import duckdb` em `fundamentals_asof_policy.py`
reprovou `store-no-storage-leak`/`domain-purity` e foi revertido. Sem ADR (previsto em D5).

### 2026-06-29 — [decision] AntiLeakageError vs ValueError — Claude (autonomous run)
**Contexto:** O old (`build_tft_dataset_use_case.py:530-535`) levanta `ValueError` cru no
invariante anti-leakage (D4/concept §7).
**Pergunta:** Manter `ValueError` ou criar erro de domínio nomeável?
**Opções:**
- A — manter `ValueError` genérico (paridade literal com o old).
- B — `AntiLeakageError(DomainError)` nomeável ✅ recomendada
**Decisão:** B — `AntiLeakageError` herda de `shared/domain/exceptions/base.DomainError`,
alinhado ao padrão `NotFoundError`/`DuplicateKeyError` (ADR 2.1.0002).
**Razão:** O invariante razão-de-ser da Stage merece um tipo observável e capturável; o
projeto já tem base de erro de domínio. Aplicação de padrão estabelecido (sem alternativa
estrutural nova) — `[decision]`, sem ADR próprio.

### 2026-06-29 — [decision] Q1: sintaxe DuckDB ASOF JOIN confirmada — Claude (autonomous run)
**Contexto:** Q1 (concept §13) deixou em aberto a sintaxe exata do ASOF JOIN na versão
pinada (`ON d.date >= f.effective_date` vs `MATCH_CONDITION`).
**Pergunta:** Qual sintaxe funciona na versão pinada (duckdb 1.5.4)?
**Opções:**
- A — `ASOF LEFT JOIN rep r ON g.day >= r.effective_date` ✅ recomendada
- B — `ASOF JOIN ... USING (...) MATCH_CONDITION (...)`
**Decisão:** A — `ASOF LEFT JOIN rep r ON g.day >= r.effective_date` (left join preserva
1 linha por dia mesmo sem fundamento elegível → C4).
**Razão:** Confirmado por prototipagem na versão pinada (duckdb 1.5.4): a semântica bate
1:1 com `merge_asof(direction="backward")` do old (último `effective_date <= day`; dia
sem fundamento → `NULL`). Sem desvio do contrato; o contract test parametrizado fake↔real
(A8) é a rede de segurança e passou idêntico para ambos.

### 2026-06-29 — [decision] saída wide por dia + materialização sem pandas — Claude (autonomous run)
**Contexto:** D6/concept §7 (saída wide por dia de pregão + `fundamentals_effective_date`).
**Decisão:** O adapter DuckDB materializa a relação via `cursor.description` + `fetchall`
e monta `list[dict]` na fronteira (sem `pandas`/`pyarrow`), devolvendo wide (1 linha por
dia com os 5 campos fundamentais + `fundamentals_effective_date` + 3 ratios). O nome
interno `effective_date` nunca é exposto (I8).
**Razão:** Mantém o port agnóstico de libs de dados (I7) sem trazer `pandas` ao caminho de
join; espelha o old (merge_asof wide + rename na fronteira) e dá a saída consumível pela
3.4/3.5. `[decision]`, sem ADR (previsto em D6).

### 2026-06-29 — [decision] unit dedicado do adapter DuckDB — Claude (autonomous run)
**Contexto:** O re-check anti-leakage no adapter é defense-in-depth (a `MATCH_CONDITION`
já garante `effective_date <= day`, então a violação é inalcançável pelo join normal); e
os ramos de coerção `_as_date`/`_as_float` (campo `None`/não-numérico, `effective_date`
não-`date`) não eram exercitados pelo contract test de forma compartilhada.
**Decisão:** Adicionado `tests/unit/features/feature_engineering/adapters/test_asof_join_duckdb_adapter.py`
(escopo da Task 04) cobrindo os ramos específicos do adapter (campos `None`/não-numéricos
→ `None`; `effective_date` não-`date` → `TypeError`).
**Razão:** Eleva a cobertura do adapter a 100% sem inflar o contract test (que prova só a
forma compartilhada fake↔real). O caminho "futura → erro" do invariante fica provado no
unit da policy (Task 01) e no teste-foco (Task 05).

### 2026-06-29 — [deviation] auditoria de testes: re-check defense-in-depth não provado — Claude (autonomous run)
**Gap fechado:** A cláusula A5/A6 exige que o adapter levante `AntiLeakageError` para
`effective_date` futura (I1, defense-in-depth). Porém o `ASOF LEFT JOIN`
(`g.day >= r.effective_date`) NUNCA materializa uma linha com data futura (verificado:
retorna `NULL`), então a linha `self._policy.validate_not_future(...)` no adapter — e a
correspondente no fake — apareciam "100% cobertas" mas **nunca eram exercitadas no caminho
de raise**: removê-las não quebrava nenhum teste (mutação sobrevivia). O invariante só
estava provado chamando a policy diretamente, não provando que adapter/fake DELEGAM a ela.
**Correção:** Adicionados `test_adapter_delegates_anti_leakage_recheck_to_policy` (unit do
adapter) e `test_both_adapters_delegate_recheck_to_policy[fake|duckdb]` (teste-foco,
parametrizado) que injetam uma `_RaisingPolicy` stub e exigem propagação do
`AntiLeakageError` — única forma de provar o cablamento, já que o join não produz linha
futura. Mutação confirmada: remover o re-check do adapter agora derruba ambos os testes.
Commit `test(feature-engineering): provar re-check anti-leakage delegado a policy [3.3/task-05-extra]`.

### 2026-06-29 — [deviation] auditoria de testes: dia vazio não deve acionar re-check — Claude (autonomous run)
**Gap fechado:** O ramo C4 (dia sem fundamento elegível → `effective is None` → return
antecipado, sem chamar `validate_not_future`) não tinha asserção provando que o re-check
NÃO é chamado no caminho vazio. Mutação que movesse o re-check para antes do guard `None`
passaria despercebida.
**Correção:** Adicionado `test_empty_day_does_not_invoke_policy_recheck` (injeta
`_RaisingPolicy`; dia vazio não levanta → prova o short-circuit C4). Commit junto à
Task 04-extra.

### 2026-06-29 — [deviation] auditoria de testes: coerção de `bool` não coberta — Claude (autonomous run)
**Gap fechado:** `_as_float` guarda `isinstance(value, bool)` porque `bool` é subclasse de
`int` (sem o guard, `True` viraria `1.0` e poluiria os ratios). Nenhum teste passava `bool`;
remover o guard sobrevivia.
**Correção:** Adicionado `test_bool_fundamental_coerced_to_none` (campo fundamental `True`
→ `None`, ratio dependente `None`). Commit `[3.3/task-04-extra]`.

### 2026-06-29 — [deviation] auditoria de testes: independência da ordem de entrada — Claude (autonomous run)
**Gap fechado:** O contract test alimentava os reports já ordenados (`[_R1, _R2]`), então a
ordenação interna do fake (`sorted` + `break` no primeiro report futuro) não era provada:
um fake que dependesse da ordem de entrada (ou um `break` mal colocado) passaria.
**Correção:** Adicionado `test_input_report_order_does_not_affect_result` (contract,
parametrizado fake↔real) com reports invertidos (`[_R2, _R1]`), exigindo que cada dia ainda
escolha o MAIOR `effective_date <= day` — paridade fake↔DuckDB. Commit `[3.3/task-08-extra]`.

<!-- END: post-execution -->