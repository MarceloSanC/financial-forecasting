---
title: Technical — Stage 2.4 — Trading Calendar
description: Plano de execução da Stage 2.4 — VO TradingSessions, domain-service TradingCalendar, port-out ExchangeCalendarProvider e adapter exchange-calendars, em 7 Tasks inside-out
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, trading-calendar, trading-sessions, exchange-calendars, port-out, value-object, domain-service, contract-test, inward-only]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 2.4-trading-calendar
stage_title: Trading Calendar
step_id: 2
step_title: Camada bronze + calendário
depends_on: [2.1-medallion-storage-contracts]
concept_ref: ./concept.md
issue_id: 17
branch: feat/17-2-4-trading-calendar
tasks_count: 7
---

# Technical — Stage 2.4 — Trading Calendar

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [2.4/task-NN]`, body em bullets, rodapé
>    `Refs #17`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar em [§7 Execução](#7-execução-post-hoc-editável-após-done) como
>    `[decision]`/`[deviation]`/`[finding]`. Nunca propagar silenciosamente.
> 7. **Fechamento é externo a você.** NÃO faça o commit `stage 2.4: complete`
>    nem marque a Stage `done` no `roadmap.md` — isso é do orquestrador, após
>    auditoria independente.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/17-2-4-trading-calendar`.

## 1. Contexto e estratégia de execução

### Resumo
Esta Stage entrega o calendário de pregão XNYS como **serviço de domínio puro**.
Um VO `TradingSessions` (frozen, stdlib-only) materializa as datas de sessão de
uma janela `[start, end]`; o domain-service `TradingCalendar` opera **só** sobre
esse VO injetado (mapeamento timestamp→dia de pregão, `is/next/prev_session`,
`shift_trading_days`). A `application` ganha o port-out `ExchangeCalendarProvider`
(`Protocol`, entrega `TradingSessions`); o adapter `ExchangeCalendarsProvider`
implementa-o sobre `exchange-calendars` (`get_calendar("XNYS")`), único lugar onde
a lib vive. Um import-linter contract novo blinda o vazamento da lib. Ver
[`concept.md`](./concept.md) §4–§7 e ADR
[`2_4_0001`](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md).

### Estratégia
**Inside-out (TDD), conforme skill `task-ordering-hex`.** Esta Stage **não tem
use case** — o port é materializado pelo `composition_root`/consumidores em Stages
futuras (3.2/3.3/5.1), fora daqui. Por isso a ordem padrão é adaptada (declaração
exigida pela skill quando o default não se aplica integralmente):

1. **domain primeiro** — VO `TradingSessions` (Task 01) e depois o domain-service
   `TradingCalendar` que o consome (Task 02–03, partido em duas Tasks por volume:
   timestamp→dia + lookups; e shift). O domínio fica verificável sem nenhuma infra.
2. **application** — port-out `Protocol` (Task 04) + **fake in-memory** + contract
   test rodando **só sobre o fake** (Task 05). Sem use case a parametrizar; o
   contrato prova a semântica observável do port.
3. **adapters/out** — dependência `exchange-calendars` + adapter real + contrato
   import-linter (Task 06), e por fim o **mesmo contract test** parametrizado para
   rodar também sobre o adapter real, garantindo paridade fake↔real (Task 07).

Cada Task deixa o build verde. Fakes antes do adapter real (CI não depende de
`exchange-calendars` até a Task 06). Port (Task 04) e adapter (Task 06) ficam em
Tasks separadas — regra dura de PIPELINE §4.3.

### Pré-condições
- Stage `2.1-medallion-storage-contracts` em `done` (postura de port/fake/contract
  herdada; nenhum dado consumido).
- Branch `feat/17-2-4-trading-calendar` em checkout (já criada).
- `make setup` aplicado (ambiente `uv`, hooks de commit instalados).

### Premissas técnicas
- Python 3.12, `pyproject.toml` e `.importlinter` já existentes.
- `exchange-calendars` disponível no PyPI; será pinada e travada no `uv.lock`.
- VOs de domínio vivem em `shared/domain/value_objects/`; serviços em
  `shared/domain/services/` (pasta a criar — hoje vazia).

### Estrutura de pastas afetada

```
src/financial_forecasting/shared/
├── domain/
│   ├── value_objects/trading_sessions.py            # Task 01 (novo)
│   └── services/trading_calendar.py                 # Task 02–03 (novo)
├── application/ports/out/exchange_calendar_provider.py  # Task 04 (novo)
└── adapters/out/calendar/exchange_calendars_provider.py # Task 06 (novo)
tests/
├── unit/shared/domain/value_objects/test_trading_sessions.py   # Task 01
├── unit/shared/domain/test_trading_calendar.py                 # Task 02–03
├── fakes/shared/in_memory_exchange_calendar_provider.py        # Task 05
└── contract/shared/test_exchange_calendar_provider_contract.py # Task 05 (fake) + 07 (real)
pyproject.toml         # Task 06 (dep nova)
uv.lock                # Task 06 (regenerado)
.importlinter          # Task 06 (contrato calendar-no-exchange-calendars-leak)
```

## 2. Tasks

> Faixa saudável: 3–8 Tasks. Esta Stage tem **7**.

### Task 01 — VO `TradingSessions` (frozen, stdlib-only)

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/value_objects/trading_sessions.py`
  - `tests/unit/shared/domain/value_objects/test_trading_sessions.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `@dataclass(frozen=True)` com `sessions: tuple[date, ...]`.
  `__post_init__` valida estritamente crescente e sem duplicatas → `ValueError`
  (C4). Propriedades `start`/`end` (primeiro/último; `ValueError` se vazio).
  Métodos `contains(d) -> bool` via `bisect` O(log n) e `in_window(d) -> bool`
  (`start <= d <= end`). stdlib only (`dataclasses`, `datetime`, `bisect`).
- **Detalhes técnicos:**
  - I7/A1: ordenado, imutável, sem duplicatas; membership O(log n).
  - C4: sessões não-ordenadas/duplicadas → `ValueError` na construção.
  - `bisect_left` + comparação de igualdade para `contains`.
- **Critério de aceite:**
  - Testes cobrem: construção válida; `start`/`end`; `contains` hit/miss;
    `in_window` dentro/fora; rejeição de desordenado e de duplicata; VO vazio.
  - `mypy --strict` limpo; `domain-purity` verde (stdlib only).
- **Comando de verificação:**
  ```bash
  pytest tests/unit/shared/domain/value_objects/test_trading_sessions.py -v
  mypy --strict src/financial_forecasting/shared/domain/value_objects/trading_sessions.py
  python scripts/check_layout.py && lint-imports
  ```
- **Commit sugerido:** `feat(trading-calendar): VO TradingSessions sobre janela fechada [2.4/task-01]`

---

### Task 02 — `TradingCalendar`: timestamp→dia + `is/next/prev_session`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/services/trading_calendar.py`
  - `src/financial_forecasting/shared/domain/services/__init__.py` (se ausente)
- **Arquivos a modificar:**
  - `tests/unit/shared/domain/test_trading_calendar.py` (criar)
- **O que fazer:** classe `TradingCalendar` com `__init__(self, sessions:
  TradingSessions)`. Implementar `is_session(d) -> bool` (delega `contains`),
  `next_session(d) -> date` (menor sessão `> d`), `prev_session(d) -> date`
  (maior sessão `< d`), e `trading_day_from_timestamp(ts: datetime, close_hour:
  time) -> date`. Importa **só** `TradingSessions` do próprio domínio + stdlib —
  zero import de `application` (I2/A2).
- **Detalhes técnicos:**
  - I5/C1/A3: `ts.tzinfo is None` → `ValueError` (naive proibido); normaliza com
    `ts.astimezone(UTC)`; a sessão-base é `ts.date()` (em UTC); se `ts.time() >
    close_hour` **ou** a base não é sessão, rola para `next_session`.
  - C2/D5: resultado além de `[start, end]` (ex.: `next_session` no fim da janela)
    → `ValueError` (janela insuficiente, sem clamp).
  - I4/A5: corretude contra feriados NYSE 2023 conhecidos.
- **Critério de aceite:**
  - Testes: `is_session` em dia útil/feriado/fim de semana; `next/prev_session`
    pulando feriado e fim de semana; `trading_day_from_timestamp` naive→`ValueError`,
    antes/depois de `close_hour`, base não-sessão→próxima; estouro de janela→`ValueError`.
  - A4: fixture do old — sexta após `close_hour` → próxima sessão (segunda; se
    segunda é feriado, terça).
  - `domain-purity` e `hexagonal-layers` verdes.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/shared/domain/test_trading_calendar.py -v
  mypy --strict src/financial_forecasting/shared/domain/services/trading_calendar.py
  python scripts/check_layout.py && lint-imports
  ```
- **Commit sugerido:** `feat(trading-calendar): mapeamento timestamp->dia de pregao e lookups de sessao [2.4/task-02]`

---

### Task 03 — `TradingCalendar.shift_trading_days`

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/domain/services/trading_calendar.py`
  - `tests/unit/shared/domain/test_trading_calendar.py`
- **O que fazer:** adicionar `shift_trading_days(self, d: date, n: int, *,
  direction: Direction = "forward") -> date`, com `Direction = Literal["forward",
  "backward"]`. `n=0` retorna a sessão-âncora (a própria `d` se for sessão; caso
  contrário a primeira sessão na direção pedida — decidir e documentar; preferir
  exigir `d` ser sessão ou ancorar via next/prev conforme `direction`). `n>0`:
  avança/recua `n` pregões reusando `next_session`/`prev_session`.
- **Detalhes técnicos:**
  - I6/A6: pula feriados+fins de semana em ambas as direções; default `forward`.
  - C3: `n < 0` → `ValueError` (sinal não expressa direção; use `direction`).
  - C2/D5/A6: offset que estoura `[start, end]` → `ValueError` (sem clamp).
  - Fixtures A6: shift backward atravessando `2023-07-04` e `2023-11-23`.
- **Critério de aceite:**
  - Testes: forward/backward N pregões pulando feriado; `n=0` identidade/âncora;
    `n<0`→`ValueError`; estouro de janela→`ValueError`; fixtures de Thanksgiving e
    4 de julho atravessadas.
  - `domain-purity`/`hexagonal-layers` verdes; cobertura do service ≥90%.
- **Comando de verificação:**
  ```bash
  pytest tests/unit/shared/domain/test_trading_calendar.py -v
  mypy --strict src/financial_forecasting/shared/domain/services/trading_calendar.py
  python scripts/check_layout.py && lint-imports
  ```
- **Commit sugerido:** `feat(trading-calendar): offset de N pregoes com direcao explicita [2.4/task-03]`

---

### Task 04 — Port-out `ExchangeCalendarProvider` (Protocol)

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/application/ports/out/exchange_calendar_provider.py`
- **Arquivos a modificar:** nenhum (mypy valida o Protocol via uso no fake na Task 05)
- **O que fazer:** `Protocol` (`@runtime_checkable` se o padrão de 2.1 o usa)
  `ExchangeCalendarProvider` com `def sessions(self, *, start: date, end: date) ->
  TradingSessions: ...`. Importa o VO de `shared/domain/value_objects` (application
  pode importar domain — direção para dentro). **Não** importa
  `exchange-calendars`/`pandas`/`numpy` (I3/A7).
- **Detalhes técnicos:**
  - A7: shape estrutural; troca só `date`/VO de domínio.
  - C5 (semântica `start > end`→`ValueError`) é responsabilidade das implementações
    (fake e adapter), documentada no docstring do port; o Protocol só declara shape.
  - Espelha `medallion_store.py`/`experiment_tracker.py`.
- **Critério de aceite:**
  - `mypy --strict` limpo; `inward-only`/`hexagonal-layers` verdes; nenhuma lib
    externa importada (lint-imports verde).
- **Comando de verificação:**
  ```bash
  mypy --strict src/financial_forecasting/shared/application/ports/out/exchange_calendar_provider.py
  python scripts/check_layout.py && lint-imports
  ```
- **Commit sugerido:** `feat(trading-calendar): port-out ExchangeCalendarProvider [2.4/task-04]`

---

### Task 05 — Fake in-memory + contract test (só fake)

- **Arquivos a criar:**
  - `tests/fakes/shared/in_memory_exchange_calendar_provider.py`
  - `tests/contract/shared/test_exchange_calendar_provider_contract.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:** `FakeExchangeCalendarProvider` que satisfaz o `Protocol`,
  construído com um conjunto fixo de sessões (fixtures NYSE 2023, com feriados
  conhecidos ausentes); `sessions(start, end)` recorta a janela e devolve
  `TradingSessions`; `start > end` → `ValueError` (C5). Escrever o contract test
  **parametrizado** (fixture `provider_factory`) já preparado para `[fake]` agora
  e `[fake, real]` na Task 07 (mesma estrutura da Task 05/07 de 2.1).
- **Detalhes técnicos:**
  - I8/A9: o contrato valida semântica observável: janela recortada corretamente;
    feriados NYSE 2023 conhecidos (`2023-01-02`, `2023-07-04`, `2023-11-23`,
    `2023-12-25`) ausentes; VO retornado é ordenado/sem duplicatas; `start>end`→erro.
  - Fake é teste (vive em `tests/fakes/`), nunca em `src/` (postura 2.1).
- **Critério de aceite:**
  - Contract test verde sobre o fake; `mypy --strict` no fake; cobertura mantida.
- **Comando de verificação:**
  ```bash
  pytest tests/contract/shared/test_exchange_calendar_provider_contract.py -v
  mypy --strict tests/fakes/shared/in_memory_exchange_calendar_provider.py
  python scripts/check_layout.py && lint-imports
  ```
- **Commit sugerido:** `test(trading-calendar): fake e contract test do ExchangeCalendarProvider [2.4/task-05]`

---

### Task 06 — Dependência, adapter real e contrato import-linter

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/adapters/out/calendar/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/calendar/exchange_calendars_provider.py`
- **Arquivos a modificar:**
  - `pyproject.toml` (dep `exchange-calendars` pinada, com comentário de razão)
  - `uv.lock` (regenerado no mesmo commit)
  - `.importlinter` (contrato `calendar-no-exchange-calendars-leak`)
- **O que fazer:** `ExchangeCalendarsProvider` implementa o port via
  `exchange_calendars.get_calendar("XNYS")`; `sessions(start, end)` (com
  `start>end`→`ValueError`, C5) consulta a lib, converte cada sessão para `date`
  puro (sem vazar `pd.Timestamp`/`numpy`) e materializa `TradingSessions`. Adicionar
  o contrato import-linter `type = forbidden`, `source_modules = shared.application
  + shared.domain`, `forbidden_modules = exchange_calendars`, espelhando
  `tracker-no-mlflow-leak`/`store-no-storage-leak`.
- **Detalhes técnicos:**
  - I3/A8: a lib vive SÓ neste adapter; conversão para `date` é interna.
  - Pin de versão (mitiga risco de mudança de sessões históricas entre versões);
    `uv.lock` no mesmo commit (determinismo).
  - Contract test ainda **não** parametriza o real aqui — isso é Task 07; mas o
    adapter já deve ser importável e tipado.
- **Critério de aceite:**
  - `lint-imports` verde COM o novo contrato (lib não vaza para application/domain).
  - `mypy --strict` no adapter; `uv lock` consistente; `make check` verde.
- **Comando de verificação:**
  ```bash
  uv lock && uv sync
  mypy --strict src/financial_forecasting/shared/adapters/out/calendar/exchange_calendars_provider.py
  lint-imports && python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(trading-calendar): adapter exchange-calendars XNYS e contrato anti-leak [2.4/task-06]`

---

### Task 07 — Paridade fake↔real no contract test

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `tests/contract/shared/test_exchange_calendar_provider_contract.py`
- **O que fazer:** adicionar `_build_real` (`ExchangeCalendarsProvider()`) à
  parametrização do contract test, de modo que o **mesmo** contrato rode sobre
  `[fake, real]`. Confirmar que os feriados NYSE 2023 conhecidos batem nos dois e
  que o recorte de janela é idêntico (I8/A9).
- **Detalhes técnicos:**
  - I8/A9: paridade fake↔real é o gate central desta Task; o real exercita
    `exchange-calendars` de verdade.
  - Marcar com `@pytest.mark.integration`/lib externa se o padrão de 2.1 separa o
    real (seguir exatamente o que `test_medallion_store_contract.py` faz na Task 07).
- **Critério de aceite:**
  - O contrato roda verde sobre fake E real; feriados conhecidos ausentes nos dois.
  - `make check` e `make test-cov` (≥90%) verdes — gate de saída.
- **Comando de verificação:**
  ```bash
  pytest tests/contract/shared/test_exchange_calendar_provider_contract.py -v
  make check && make test-cov
  ```
- **Commit sugerido:** `test(trading-calendar): paridade fake<->real do contract test [2.4/task-07]`

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage ser considerada pronta para PR.
> **O commit `stage 2.4: complete` e a marcação `done` no `roadmap.md` são feitos
> pelo orquestrador, não nesta sessão.**

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + lint-imports + check_layout
make test-cov             # todos os testes + cobertura ≥90%
pytest tests/unit/shared/domain/ tests/contract/shared/test_exchange_calendar_provider_contract.py -v
lint-imports              # inclui o novo contrato calendar-no-exchange-calendars-leak
```

### Verificações funcionais
- [ ] `TradingCalendar` resolve `trading_day_from_timestamp` (rola após `close_hour`
      e pula feriado/fim de semana) sobre o VO injetado.
- [ ] `shift_trading_days` pula feriados+fins de semana em ambas as direções;
      `n<0` e estouro de janela levantam `ValueError`.
- [ ] Adapter real e fake passam o MESMO contract test; feriados NYSE 2023
      conhecidos ausentes nos dois.
- [ ] `exchange-calendars` não vaza para `application`/`domain` (lint-imports verde).

### Mapeamento invariante ↔ teste

| Invariante / critério | Teste que o prova |
|---|---|
| I1 domínio puro (A2) | `lint-imports` (`domain-purity`) + ausência de import externo no VO/service |
| I2 inward-only (A2) | `lint-imports` (`hexagonal-layers`) — service não importa application |
| I3 lib só no adapter (A7/A8) | `lint-imports` (`calendar-no-exchange-calendars-leak`) |
| I4 determinismo / feriados (A5) | `test_trading_calendar.py` (fixtures `2023-01-02/07-04/11-23/12-25`) + contract test |
| I5 timestamp→dia (A3/A4/C1) | `test_trading_calendar.py::test_*_from_timestamp` (naive→erro, after-close→próxima, fixture do old) |
| I6 direção explícita no shift (A6/C3) | `test_trading_calendar.py::test_shift_*` (forward/backward, `n<0`→erro, `n=0`) |
| I7 VO ordenado/imutável (A1/C4) | `test_trading_sessions.py` (desordenado/duplicata→erro, frozen, `contains` O(log n)) |
| I8 paridade fake↔real (A9) | `test_exchange_calendar_provider_contract.py` parametrizado `[fake, real]` |
| C2/D5 estouro de janela | `test_trading_calendar.py` (next/prev/shift/timestamp além de `[start,end]`→`ValueError`) |
| C5 `start>end` no provider | contract test (fake e real levantam `ValueError`) |
| I10 gates strict (A10) | `make check` + `make test-cov` (≥90%) |

### Checklist de fechamento da Stage (parte do orquestrador, exceto onde marcado)
- [ ] (você) Todas as 7 Tasks commitadas, cada uma com check verde
- [ ] (você) `make check` e `make test-cov` verdes no branch
- [ ] (você) ADR `2_4_0001` em `status: accepted`
- [ ] (você) `concept.md`/`technical.md` em `status: done`, sem retoque pendente
- [ ] (orquestrador) commit `stage 2.4: complete`
- [ ] (orquestrador) Stage marcada `done` + `updated_at`/`last_reviewed_at` no `roadmap.md`
- [ ] (orquestrador) branch em PR contra `develop`

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out):

```
Task 01 (VO) ─► Task 02 (service: ts→dia + lookups) ─► Task 03 (service: shift)
                                                          │
Task 04 (port) ──────────────────────────────────────────┤
   │                                                      ▼
   └─► Task 05 (fake + contract só-fake) ─► Task 06 (dep + adapter + import-linter)
                                                ─► Task 07 (contract fake↔real)
```

- Task 02/03 dependem de Task 01 (consomem o VO).
- Task 04 (port) é independente do service mas precisa do VO (Task 01); listada
  após Task 03 só por organização — pode ser feita em paralelo conceitualmente.
- Task 05 depende de Task 04 (implementa o Protocol).
- Task 06 depende de Task 04 (implementa o mesmo port) e de Task 01 (materializa o VO).
- Task 07 depende de Task 05 (estrutura do contrato) e Task 06 (adapter real existe).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `exchange-calendars` muda sessões históricas entre versões | Pin de versão + `uv.lock`; fixtures de feriados NYSE 2023 no contract test pegam regressão (concept §10) |
| Janela materializada estreita demais (offset estoura) | C2/D5: `ValueError` explícito, sem clamp; caller alarga a janela |
| Drift fake↔real | I8: MESMO contract test nos dois (Task 07); fixtures de feriados conhecidos batem nos dois |
| `get_calendar("XNYS")` lento/pesado no import do adapter | Instanciar a lib dentro do método `sessions`, não no import do módulo; manter o adapter barato de importar |
| `exchange_calendars` arrasta `pandas`/`numpy` para o grafo | Contrato `calendar-no-exchange-calendars-leak` cobre só application/domain; o adapter pode usar a lib — conversão para `date` na fronteira do método |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md) — §6, §7, §11 (`0_0_0019`/`0_0_0020`)
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.4-trading-calendar`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs: [`../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md`](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md);
  fundacionais `0_0_0019`/`0_0_0020`/`0_0_0021`; correlatos `2_1_0002`
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `ddd-tactical-patterns`,
  `pytest-with-fakes`, `import-linter-rules`
- Repo antigo: `financial-time-series-forecasting/src/domain/time/trading_calendar.py`,
  `.../tests/unit/domain/time/test_trading_calendar.py:24-28`
- Lib externa: [`exchange-calendars`](https://github.com/gerrymanoim/exchange_calendars)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após
> `status: done`.** Registrar `[decision]`/`[finding]`/`[deviation]` em ordem
> cronológica conforme o formato do template.

### Task 03 — `[decision]` semântica "ancora-e-conta" do `shift_trading_days`

`shift_trading_days` resolve a âncora ANTES de contar os `n` pregões: se `day` já
é sessão, a âncora é `day`; caso contrário, a âncora é a primeira sessão no
sentido `direction` (`next_session` se `forward`, `prev_session` se `backward`).
Em seguida dá `n` passos a partir da âncora. Consequência intencional: para
`day` não-sessão, `n=0` devolve a sessão de fronteira e `n=k` devolve k sessões
além dela — não há assimetria-bug, é a regra documentada (e a única que dá um
significado estável a `n=0` sobre um feriado). `n<0` é `ValueError` (a direção é
expressa por `direction`, não pelo sinal — C3). Cobre o uso do embargo da Stage
5.1 (que precisa recuar `H` pregões de pregão a partir de uma data qualquer).

### Task 06 — `[finding]` `uv sync` remove os dev-deps; o projeto usa `uv pip install -e ".[dev]"`

Ao travar a dependência nova rodei `uv lock && uv sync` (como sugeria o comando
de verificação da Task 06). `uv sync` instala SÓ as deps principais e **removeu**
o toolchain de dev (`pytest`/`ruff`/`mypy`/`pre-commit`...), porque o projeto não
declara um dependency-group e o `Makefile` instala via `uv pip install -e
".[dev]"` (extra `dev`), não via `uv sync`. Restaurado com `uv pip install -e
".[dev]"`. **Aprendizado para Stages futuras:** depois de mexer em deps, re-rodar
`uv pip install -e ".[dev]"` (ou `make setup`), não `uv sync`, senão o ambiente
de teste fica sem ferramentas. O `uv.lock` em si ficou correto (contém
`exchange-calendars` 4.13.2 + transitive `korean-lunar-calendar`/`pyluach`/
`toolz`).

### Task 06 — `[finding]` `exchange-calendars` 4.13.2; XNYS 2023 = 250 sessões; paridade fake↔real byte-idêntica

A lib resolveu para `4.13.2` (dentro do pin `>=4.5,<5.0`). Sanity check do adapter
real: XNYS 2023 tem **250 sessões** (1ª `2023-01-03`, última `2023-12-29`), com os
10 feriados de fechamento total ausentes e os vizinhos de feriado presentes; cada
elemento devolvido é `datetime.date` puro (sem `pd.Timestamp` vazando). O conjunto
de 2023 do fake (dias úteis menos os 10 feriados hard-coded) é **byte-idêntico** ao
do real — confirmado por `test_fake_and_real_produce_identical_sessions_2023` e por
verificação manual (`real == fake`, n=250 nos dois). A invariante de não-leak foi
provada por quebra intencional revertida (`import exchange_calendars` no port →
`calendar-no-exchange-calendars-leak` BROKEN; revertido → 7 kept).

### Task 07 — `[decision]` adapter real entra direto em `_FACTORIES` (sem marcador extra)

O contract test parametriza `[fake, real]` sem um `@pytest.mark.integration`
adicional além do `@pytest.mark.contract` já presente, espelhando exatamente o
`test_medallion_store_contract.py` da Stage 2.1. Justificativa: `exchange-calendars`
é uma lib **offline e determinística** (não faz rede, calendário cacheado em
processo), então o "real" roda rápido e estável no mesmo passo de `make check` —
não há custo de I/O externo que justifique separar. Avisos de `DeprecationWarning`
(numpy timedelta) vêm de dentro da lib, não do código da Stage, e não falham o CI
(o projeto não configura `filterwarnings = error`).

<!-- END: post-execution -->
