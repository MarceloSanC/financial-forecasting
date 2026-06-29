---
title: Concept — Stage 2.4 — Trading Calendar
description: Calendário de pregão XNYS como serviço de domínio puro sobre um VO de sessões materializadas, com port-out e adapter exchange-calendars
when-use: Consultar ao iniciar Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, trading-calendar, trading-sessions, exchange-calendars, xnys, port-out, value-object, domain-service, embargo, shift-trading-days]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 2.4-trading-calendar
stage_title: Trading Calendar
step_id: 2
step_title: Camada bronze + calendário
depends_on: [2.1-medallion-storage-contracts]
---

# Concept — Stage 2.4 — Trading Calendar

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo
- **VO de domínio `TradingSessions`** (frozen, stdlib-only): conjunto ordenado e
  imutável de datas de pregão XNYS para uma janela `[start, end]`; membership
  O(log n) via `bisect`, bounds `start`/`end`. É o *boundary value object* (ADR
  0.0.0020) que cruza do adapter para o domínio.
- **Serviço de domínio `TradingCalendar`** (stdlib-only) que opera **sobre o VO
  injetado**:
  - `trading_day_from_timestamp(ts, close_hour) -> date` — mapeia timestamp →
    dia de pregão (semântica do old: tz-aware obrigatório, normaliza p/ UTC,
    `ts.time() > close_hour` rola para a **próxima sessão**);
  - `is_session(d) -> bool`, `next_session(d) -> date`, `prev_session(d) -> date`;
  - `shift_trading_days(d, n, *, direction) -> date` — offset de N pregões
    forward/backward (embargo/purga da Stage 5.1).
- **Port-out `ExchangeCalendarProvider`** (`Protocol` em `application/ports/out/`)
  que entrega sessões materializadas: `sessions(start, end) -> TradingSessions`.
- **Adapter `ExchangeCalendarsProvider`** sobre `exchange-calendars`
  (`get_calendar("XNYS")`) — **único lugar** onde a lib vive; converte sessões
  para `date` puro e materializa o VO.
- **Dependência nova** `exchange-calendars` pinada no `pyproject.toml` (+ `uv.lock`).
- **Novo contrato import-linter** `calendar-no-exchange-calendars-leak` em
  `.importlinter` (enforce de I3, espelha `tracker-no-mlflow-leak`/`store-no-storage-leak`).
- **Testes:** unit do VO e do domain-service contra fixtures determinísticas
  (feriados NYSE 2023 conhecidos); contract test paritário fake↔real.
- **ADR** resolvendo a direção inward-only (`2.4.0001`).

### Fora do escopo (explicitamente)
- Calendários 24/7 (cripto) e intraday — `non_goals` do roadmap.
- Qualquer lógica de trading/execução.
- Fechamento de sessão / orquestração — é responsabilidade do orquestrador.
- Wiring no `composition_root` e o consumo por 3.2/3.3/5.1 (Stages futuras).
- Persistência do calendário (não há tabela medalhão de sessões nesta Stage).

### Vínculo com o roadmap
Esta Stage entrega o contrato `TradingCalendar` (domain-service) e
`ExchangeCalendarProvider` (port-out) do Step 2 ("Camada bronze + calendário"),
fechando o gap do repo antigo (calendário weekday-only **sem feriados**). É
pré-condição de 3.2 (sentimento agregado por dia de pregão), 3.3 (as-of join de
fundamentals na grade diária) e 5.1 (embargo de H pregões no walk-forward). Ver
`roadmap.md` Stage `2.4-trading-calendar` e `overview.md` §11
(`0_0_0019`/`0_0_0020`).

## 2. Objetivo da Stage

Ao final, existe um serviço de domínio puro que, dado um conjunto de sessões XNYS
materializado por um adapter validado (`exchange-calendars`), resolve dia de
pregão a partir de timestamp, testa/itera sessões e desloca por N pregões em
qualquer direção — testado contra feriados NYSE conhecidos e com paridade
fake↔real garantida por contract test.

## 3. Contexto e premissas

### Contexto
O repo antigo (`financial-time-series-forecasting/src/domain/time/trading_calendar.py`)
mapeava timestamp→dia com `TradingDayPolicy(close_hour, weekends)`, mas o
"calendário" era weekday-only (`_roll_to_business_day` pula só sábado/domingo) e
**não conhecia feriados reais**; o mesmo gap aparece em
`sentiment_feature_engineering_use_case.py:184-190` (`weekday<5`) e
`data_quality_reporter.py:175-181` (`pd.bdate_range`). Esta Stage preserva a
**semântica** timestamp→dia e o conceito de `close_hour`, mas substitui a fonte
de verdade dos feriados por `exchange-calendars` (XNYS). Nenhum offset de N
pregões existia no old — `shift_trading_days` é projeto novo derivado da
semântica de sessões.

### Premissas
- A janela `[start, end]` de sessões necessária a um caso de uso é conhecida e
  carregada **antes** de o domain-service rodar (decorre de D1).
- `exchange-calendars` XNYS é fonte de verdade aceita para sessões/feriados NYSE
  (mesma postura de `pyarrow`/`duckdb`/`mlflow`: lib externa vive só no adapter).
- O contrato `MedallionStore` (2.1) está `done`; esta Stage não o consome, mas
  herda a postura de port Protocol + fake + contract test ali estabelecida.

### Dependências
- `2.1-medallion-storage-contracts`: padrão de port-out (`Protocol` estrutural,
  sem vazar libs), de fake in-memory e de contract test paritário fake↔real
  (reusado aqui; nenhum dado/medalhão é consumido).

## 4. Contratos

### Introduzidos

- **`TradingSessions`** (`value-object`, `shared/domain/value_objects/trading_sessions.py`)
  - Frozen, stdlib-only. Conjunto ordenado e imutável de datas de pregão XNYS para
    `[start, end]`; lookup O(log n) via `bisect`; bounds `start`/`end`.

  ```python
  from __future__ import annotations
  from dataclasses import dataclass
  from datetime import date

  @dataclass(frozen=True)
  class TradingSessions:
      """Sessões XNYS materializadas para uma janela fechada [start, end]."""
      sessions: tuple[date, ...]   # estritamente crescente, sem duplicatas

      @property
      def start(self) -> date: ...
      @property
      def end(self) -> date: ...
      def contains(self, d: date) -> bool: ...        # bisect, O(log n)
      def in_window(self, d: date) -> bool: ...        # start <= d <= end
  ```

- **`TradingCalendar`** (`domain-service`, `shared/domain/services/trading_calendar.py`)
  - Stdlib-only; opera **só** sobre `TradingSessions` injetado (zero import de
    `application` em runtime — I2/D1).

  ```python
  from datetime import date, datetime, time
  from typing import Literal

  Direction = Literal["forward", "backward"]

  class TradingCalendar:
      def __init__(self, sessions: TradingSessions) -> None: ...

      def trading_day_from_timestamp(self, ts: datetime, close_hour: time) -> date: ...
      def is_session(self, d: date) -> bool: ...
      def next_session(self, d: date) -> date: ...
      def prev_session(self, d: date) -> date: ...
      def shift_trading_days(
          self, d: date, n: int, *, direction: Direction = "forward"
      ) -> date: ...
  ```

- **`ExchangeCalendarProvider`** (`port-out`, `shared/application/ports/out/exchange_calendar_provider.py`)
  - `Protocol` estrutural; não vaza tipos de `exchange-calendars`/`pandas`/`numpy`.

  ```python
  from datetime import date
  from typing import Protocol

  class ExchangeCalendarProvider(Protocol):
      def sessions(self, *, start: date, end: date) -> TradingSessions: ...
  ```

- **`ExchangeCalendarsProvider`** (`adapter`, `shared/adapters/out/calendar/exchange_calendars_provider.py`)
  - Implementa o port via `exchange_calendars.get_calendar("XNYS")`; converte
    sessões para `date` puro e materializa `TradingSessions`. Único lugar onde a
    lib vive.

### Consumidos
- Nenhum contrato de Stage anterior é consumido em runtime. Reusa-se a **postura**
  de port/fake/contract-test da Stage 2.1 (ADR 2.1.0002 / 0.0.0021), não os tipos.

> **Downstream (NÃO nesta Stage):** 3.2 (sentiment) e 3.3 (fundamentals as-of)
> consomem `trading_day_from_timestamp` para agregar por dia de pregão; 5.1
> (walk-forward) consome `shift_trading_days` para o offset de embargo/purga.

## 5. Invariantes e regras

- **I1 — Domínio puro.** `shared/domain/*` (VO e service) importa SÓ stdlib
  (`datetime`, `bisect`, `dataclasses`, `typing`) — sem
  `pandas`/`numpy`/`pyarrow`/`torch`/`pydantic`/`sqlalchemy`/`fastapi`
  (gate `domain-purity`).
- **I2 — Direção inward-only.** O domain-service **não importa**
  `ExchangeCalendarProvider` em runtime (gate `hexagonal-layers`,
  `application > domain`); recebe o VO `TradingSessions` por injeção. Pela opção
  (a) escolhida (D1), nem import `TYPE_CHECKING` é necessário.
- **I3 — Lib só no adapter.** `exchange-calendars` vive SÓ em
  `shared/adapters/out/calendar/`; não cruza para `application`/`domain` (mesma
  postura de `pyarrow`/`duckdb`/`mlflow` das Stages 1.5/2.1; gate de
  no-library-leak verde). **Enforce:** novo contrato import-linter
  `calendar-no-exchange-calendars-leak` (`type = forbidden`,
  `source_modules = shared.application + shared.domain`,
  `forbidden_modules = exchange_calendars`), espelhando `tracker-no-mlflow-leak`
  (1.5) e `store-no-storage-leak` (2.1). `.importlinter` é modificado nesta Stage.
- **I4 — Determinismo.** Sessões/feriados XNYS são reprodutíveis e testados contra
  fixtures de feriados NYSE conhecidos — `2023-01-02` (Ano Novo observado),
  `2023-07-04`, `2023-11-23` (Thanksgiving), `2023-12-25` — **ausentes** do
  conjunto de sessões.
- **I5 — timestamp→dia.** `ts` naive levanta `ValueError`; conversão sempre via
  `astimezone(UTC)`; `ts.time() > close_hour` avança para a **próxima sessão**
  (não apenas o próximo dia civil — upgrade sobre o old, que só rolava fim de
  semana). O resultado é sempre uma sessão válida do VO.
- **I6 — Direção explícita no shift.** `shift_trading_days` respeita `direction`
  por caso de uso (`forward` p/ notícia→próximo pregão; `backward` p/
  embargo/purga); `n=0` é identidade. Não herda o roll-forward-only do old.
- **I7 — VO ordenado e imutável.** `TradingSessions.sessions` é estritamente
  crescente, sem duplicatas; o VO é frozen; membership é O(log n).
- **I8 — Paridade fake↔real.** O MESMO contract test roda contra o fake in-memory
  e contra o adapter `exchange-calendars` real (ADR 0.0.0021 / postura 2.1).
- **I9 — Pydantic só na fronteira `adapters/in/http`.** Não se aplica aqui; não
  introduzir Pydantic nesta Stage.
- **I10 — Gates strict.** Cobertura ≥90%, mypy --strict, ruff,
  `check_layout.py` + import-linter verdes (`gate_mode: strict`).

## 6. Casos de erro e exceções

- **C1 — `ts` naive em `trading_day_from_timestamp`** → `ValueError` (timestamp
  precisa ser tz-aware; replica o old). Mensagem explícita.
- **C2 — lookup/offset fora da janela materializada.** `next_session`,
  `prev_session`, `shift_trading_days` ou `trading_day_from_timestamp` cujo
  resultado cairia **além** de `[start, end]` do VO levantam `ValueError`
  (janela insuficiente) — falha explícita, **sem clamp silencioso**. O caller
  materializa uma janela mais larga. (Decisão D5.)
- **C3 — `n` negativo em `shift_trading_days`** → `ValueError`. A direção é
  expressa por `direction` (forward/backward), não pelo sinal de `n`; `n >= 0`.
- **C4 — VO construído com sessões não-ordenadas / com duplicatas** → `ValueError`
  na construção do VO (I7). Garante a pré-condição do `bisect` de uma vez só.
- **C5 — janela inválida no provider (`start > end`)** → `ValueError` no port/
  adapter antes de tocar `exchange-calendars`.

## 7. Decisões técnicas relevantes

### D1 — Como o domain-service obtém sessões sem violar inward-only
- **O quê:** Opção (a) — VO de sessões materializadas. A `application` carrega
  sessões via `ExchangeCalendarProvider` (port-out em `application/ports/out/`,
  como o roadmap pede) e **injeta** um VO de domínio `TradingSessions` no
  `TradingCalendar`, que opera SÓ sobre o VO. O port é consumido por quem
  materializa o VO — nunca pelo domain-service.
- **Por quê:** `hexagonal-layers` reprova domínio importando `application` em
  runtime; (a) é o padrão "the boundary is the value object" do ADR 0.0.0020
  (data eng produz VO na borda; domínio consome VO puro), mantém o domínio
  stdlib-only e maximamente testável, e espelha como o old já injetava a regra
  como dado (`TradingDayPolicy`). Alternativas descartadas: (b) port-de-domínio
  introduz conceito ausente no resto do projeto e não remove a materialização;
  (c) application-service tira a lógica de calendário do domínio, contrariando o
  roadmap e o padrão domain-service. (a) é o simples-e-trocável.
- **Fonte:** ADR 0.0.0020; `.importlinter` `hexagonal-layers`; roadmap Stage 2.4
  (`arquivos_a_criar`); old `trading_calendar.py` (`TradingDayPolicy` injetada).
- **ADR:** [`../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md`](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md)

### D2 — Fonte de verdade dos feriados/sessões
- **O quê:** `exchange-calendars` (calendário XNYS) somente no adapter; NÃO
  replicar o calendário weekday-only ingênuo do old.
- **Por quê:** O old só faz weekend-roll por `close_hour` e não tem feriados
  reais (`_roll_to_business_day`); `exchange-calendars` é a lib validada para
  XNYS/NYSE e já é a postura do projeto (lib externa só no adapter, igual
  `pyarrow`/`duckdb`/`mlflow`). Replica-se a **semântica** timestamp→dia e o
  conceito `close_hour`, mas a verdade de feriados passa a ser a lib.
- **Fonte:** old `trading_calendar.py:_roll_to_business_day`; overview §11
  (`0_0_0019`/`0_0_0020`); roadmap Stage 2.4 (`exchange-calendars`).

### D3 — Direção do roll em `shift_trading_days`
- **O quê:** Direção explícita por caso de uso (parâmetro `direction`
  forward|backward); default `forward` para o mapeamento timestamp→próximo pregão.
- **Por quê:** O old só rola para frente (`_roll_to_business_day`), adequado para
  notícia→próximo pregão, mas o embargo/purga da 5.1 precisa rolar para trás. Não
  herdar cego evita um bug latente quando 5.1 consumir o offset.
- **Fonte:** old `_roll_to_business_day`; roadmap 5.1 (`walk-forward-harness`,
  embargo de H pregões); ledger §43 (5.1 consome offset).

### D4 — Onde mora o VO `TradingSessions`
- **O quê:** `shared/domain/value_objects/trading_sessions.py` (frozen,
  stdlib-only), ao lado dos VOs existentes (`config_signature`,
  `dataset_fingerprint`, `split_fingerprint`).
- **Por quê:** É o boundary VO consumido pelo domain-service; pertence ao domínio
  e respeita `domain-purity`. Colocá-lo na `application` quebraria a injeção limpa
  e a pureza. Segue a convenção de pasta da Stage 1.x/2.1.
- **Fonte:** ADR 0.0.0020 (boundary=VO); `shared/domain/value_objects/` existente.

### D5 — Offset/lookup fora da janela materializada falha (sem clamp)
- **O quê:** `next/prev_session`, `shift_trading_days` e `trading_day_from_timestamp`
  cujo resultado cairia além de `[start, end]` do VO levantam `ValueError`, em vez
  de retornar o bound (clamp) ou um valor parcial.
- **Por quê:** Clamp silencioso mascararia janela mal-dimensionada e produziria um
  embargo curto demais na 5.1 (anti-leakage). Falha explícita é segura e
  auditável; o caller alarga a janela. Coerente com a postura anti-leakage do
  projeto (overview ADR 0.0.0018).
- **Fonte:** overview §11 (`0_0_0018` anti-leakage não-negociável); roadmap 5.1
  (embargo).

## 8. Integrações

### Internas (com outras Stages/módulos)
- `shared/domain`: novo VO + service ao lado dos VOs/serviços existentes.
- `shared/application/ports/out`: novo port `ExchangeCalendarProvider` (espelha
  shape de `medallion_store.py`/`experiment_tracker.py`).
- `composition_root` (Stage futura): instanciará o adapter real e materializará o
  VO — **fora** desta Stage.

### Externas
- **`exchange-calendars`** (lib PyPI): `get_calendar("XNYS")` para sessões/feriados
  NYSE. Vive só no adapter `shared/adapters/out/calendar/`. Pinada no
  `pyproject.toml`; `uv.lock` regenerado no mesmo commit.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| `exchange-calendars` muda sessões históricas entre versões | B | A | Pin de versão no `pyproject`/`uv.lock`; fixtures determinísticas de feriados NYSE 2023 no contract test pegam regressão |
| Janela materializada estreita demais (offset estoura) | M | M | C2/D5: falha explícita `ValueError`, sem clamp; caller alarga a janela |
| Drift fake↔real (fake não reflete feriados reais) | B | A | I8: MESMO contract test roda nos dois; fixtures de feriados conhecidos batem nos dois |
| Semântica timestamp→dia divergir do old (regressão sutil) | B | M | Fixture replicando o caso do old (sexta após close → próxima sessão) no unit |

## 11. Critérios de aceitação

- [ ] **A1** — `TradingSessions` é `@dataclass(frozen=True)`, stdlib-only, com
  `contains` O(log n) via `bisect` e bounds `start`/`end`; rejeita sessões
  não-ordenadas/duplicadas na construção (I7/C4).
- [ ] **A2** — `TradingCalendar` opera SÓ sobre o VO injetado, com **zero** import
  de `application` em runtime; `domain-purity` e `hexagonal-layers` verdes (I1/I2).
- [ ] **A3** — `trading_day_from_timestamp` levanta `ValueError` em `ts` naive,
  normaliza via `astimezone(UTC)`, e rola para a **próxima sessão** quando
  `ts.time() > close_hour`; resultado sempre em sessão válida do VO (I5/C1).
- [ ] **A4** — Fixture do old replicada: sexta após `close_hour` → próxima sessão
  na segunda-feira seguinte (com feriado real intermediário, pula o feriado).
- [ ] **A5** — `is_session`/`next_session`/`prev_session` corretos contra feriados
  NYSE 2023 conhecidos (`2023-01-02`, `2023-07-04`, `2023-11-23`, `2023-12-25`
  ausentes do conjunto) (I4).
- [ ] **A6** — `shift_trading_days` pula feriados+fins de semana sobre o VO em
  ambas as direções; `n=0` identidade; `n<0` → `ValueError`; offset que estoura a
  janela → `ValueError` (I6/C2/C3/D5); fixture: shift backward atravessando
  `2023-07-04` e `2023-11-23`.
- [ ] **A7** — Port `ExchangeCalendarProvider` é `Protocol` estrutural com
  `sessions(start, end) -> TradingSessions`; não vaza tipos de
  `exchange-calendars`/`pandas`/`numpy` para a `application` (I3).
- [ ] **A8** — Adapter `ExchangeCalendarsProvider` implementa o port via
  `get_calendar("XNYS")`, materializa `TradingSessions` com `date` puro;
  `exchange-calendars` pinada no `pyproject` e `uv.lock` atualizado; contrato
  `calendar-no-exchange-calendars-leak` adicionado ao `.importlinter` e a lib NÃO
  vaza para `application`/`domain` (lint-imports verde) (I3).
- [ ] **A9** — Fake in-memory satisfaz o Protocol; o MESMO contract test roda
  verde contra fake E adapter real; feriados NYSE 2023 batem nos dois (I8).
- [ ] **A10** — `make check` (ruff + mypy --strict + lint-imports) e `make test-cov`
  (≥90%) verdes (I10).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável? (sim — old/overview/roadmap/ADR)
- [x] Toda integração externa tem contrato definido (interface, formato, auth)?
  (`exchange-calendars` `get_calendar("XNYS")`, §8)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1 → ADR 2.4.0001;
  D2/D3/D4/D5 são decisões diretas sem alternativa de igual peso → registradas
  aqui)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (2.1 `done`;
  postura de port/fake/contract herdada)
- [x] Stage cabe em ~3–8 Tasks? (8 Tasks no technical)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] A direção inward-only foi resolvida sem violar `hexagonal-layers`? (D1 / ADR
  2.4.0001 — opção (a), VO injetado)

## 13. Questões em aberto

- Nenhuma questão crítica em aberto. A largura concreta da janela `[start, end]`
  por caso de uso é decidida pelos consumidores (3.2/3.3/5.1) em suas Stages, não
  aqui — esta Stage define apenas o comportamento de falha quando a janela é
  insuficiente (C2/D5).

## 14. Referências

- [`../../overview.md`](../../overview.md) — §6, §7, §11 (`0_0_0019`/`0_0_0020`).
- [`../../roadmap.md`](../../roadmap.md) — Stage `2.4-trading-calendar`.
- ADRs desta Stage: [`../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md`](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md);
  fundacionais relacionados: `0_0_0019`, `0_0_0020`, `0_0_0021`, `2_1_0002`.
- Repo antigo: `financial-time-series-forecasting/src/domain/time/trading_calendar.py`,
  `.../src/domain/services/sentiment_aggregator.py:60`,
  `.../src/use_cases/sentiment_feature_engineering_use_case.py:184-190`,
  `.../src/domain/services/data_quality_reporter.py:175-181`,
  `.../tests/unit/domain/time/test_trading_calendar.py:24-28`.
- Lib externa: [`exchange-calendars`](https://github.com/gerrymanoim/exchange_calendars) (calendário XNYS).
