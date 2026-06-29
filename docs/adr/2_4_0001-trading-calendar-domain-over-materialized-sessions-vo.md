---
title: ADR 2.4.0001 — TradingCalendar as a pure domain service over a materialized TradingSessions value object
description: Architecture Decision Record
when-use: Reference before changing how the domain calendar logic obtains sessions/holidays, before letting the domain import a port, or before moving the calendar logic out of the domain
keywords: [adr, trading-calendar, value-object, domain-service, port, hexagonal, inward-only, exchange-calendars, xnys, sessions, embargo]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
adr_id: "2.4.0001"
decision: TradingCalendar is a pure stdlib-only domain service that operates over an injected TradingSessions value object; the application materializes that VO via an ExchangeCalendarProvider port-out, so the domain never imports the port at runtime
context_stage: 2.4-trading-calendar
---

# ADR 2.4.0001 — TradingCalendar as a pure domain service over a materialized TradingSessions value object

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted`

## Context

Stage 2.4 introduces the project's trading-calendar logic: mapping a publication
timestamp to the trading day it belongs to (`trading_day_from_timestamp`),
testing whether a date is a valid XNYS/NYSE session, walking to the next/previous
session, and offsetting by *N* trading days in either direction (the embargo/purge
operation that Stage 5.1's walk-forward harness will consume). The truth of which
days are sessions and which are holidays must come from a validated source —
`exchange-calendars` (XNYS) — not from the naive weekday-only roll of the prior
codebase (`financial-time-series-forecasting/src/domain/time/trading_calendar.py`,
which only rolls weekends via `_roll_to_business_day` and has **no real holidays**).

The roadmap (Stage 2.4 `arquivos_a_criar`) places three collaborators in three
layers:

- `TradingCalendar` as a **domain service** (`shared/domain/services/`),
- `ExchangeCalendarProvider` as a **port-out** (`shared/application/ports/out/`),
- the `exchange-calendars` adapter in `shared/adapters/out/calendar/`.

Forces and constraints:

- **Inward-only is enforced, not advisory.** The `.importlinter` `hexagonal-layers`
  contract orders `adapters > application > domain` per container; `domain`
  importing `application` (the port) at runtime is rejected. `exclude_type_checking_imports = True`
  tolerates `TYPE_CHECKING`-only imports, but a runtime dependency from the domain
  service on the port would fail the gate. So the literal roadmap shape — a domain
  service that calls a port living in `application` — cannot be implemented as
  stated.
- **Domain purity (ADR 0.0.0019).** `domain/` is stdlib-only; `exchange-calendars`
  (which pulls `pandas`/`numpy`) must not touch the domain. It belongs in the
  adapter, the same posture `pyarrow`/`duckdb`/`mlflow` already hold (Stages
  1.5/2.1).
- **A clean boundary already exists in this project.** ADR 0.0.0020 fixes the
  pattern "*the boundary is the value object*": data engineering produces a typed,
  invariant-bearing value object at the adapter edge, and the pure domain consumes
  that VO and returns results, with no library type crossing the line. The
  calendar problem is the same shape: the set of sessions is a value object; the
  calendar arithmetic is pure logic over it.
- **The prior repo already injected the calendar rule as data.** `TradingDayPolicy`
  was a frozen value passed into `trading_day_from_timestamp(ts, policy)` — the
  domain function operated over injected data, not over a service it reached out
  to. We are extending that posture: replace the naive policy with a materialized
  set of real sessions.
- **`gate_mode: strict`** (roadmap): coverage ≥90%, mypy --strict, ruff,
  `check_layout.py` + import-linter all green.

## Decision

`TradingCalendar` is a **pure, stdlib-only domain service** in
`shared/domain/services/trading_calendar.py` that **operates over an injected
`TradingSessions` value object** (`shared/domain/value_objects/trading_sessions.py`,
frozen, stdlib-only). The VO materializes the ordered, immutable set of XNYS
session dates for a window `[start, end]` and exposes O(log n) membership
(`bisect`) plus bounds.

The application loads sessions through the `ExchangeCalendarProvider` **port-out**
(`shared/application/ports/out/exchange_calendar_provider.py`, a structural
`Protocol`) — `sessions(start, end) -> TradingSessions` — and **injects** the
resulting VO into the domain service. The real adapter
(`shared/adapters/out/calendar/exchange_calendars_provider.py`) implements the port
over `exchange-calendars` `get_calendar("XNYS")`, converting sessions to plain
Python `date`s and constructing the VO.

Consequently:

- The **domain service never imports the port** — not even under `TYPE_CHECKING`.
  It depends only on the domain VO and the standard library (`datetime`, `bisect`,
  `dataclasses`). The `hexagonal-layers` contract is satisfied structurally, not
  by a tolerance.
- `exchange-calendars` lives **only** in the adapter; it never reaches `application`
  or `domain` (`domain-purity` + the data-leak contracts stay green).
- The port returns the domain VO (`TradingSessions`), which is stdlib-only, so no
  `exchange-calendars`/`pandas`/`numpy` type crosses into `application`.

The VO is the boundary object of ADR 0.0.0020, applied to calendar data.

## Alternatives considered

### Alternative A — Materialized `TradingSessions` value object (chosen)
- **Description:** Application materializes a domain VO via the port and injects it
  into the domain service, which is pure logic over the VO.
- **Pros:** Domain stays stdlib-only and maximally testable (deterministic fixtures,
  no I/O); reuses the established "boundary = value object" pattern (ADR 0.0.0020);
  mirrors how the old repo injected `TradingDayPolicy` as data; the port stays in
  `application/ports/out/` exactly where the roadmap places it, consumed by whoever
  materializes the VO — never by the domain; satisfies `hexagonal-layers` with zero
  type-only escape hatches.
- **Cons:** The window `[start, end]` must be decided and loaded before the domain
  service runs; an offset/lookup outside the materialized window is an error the
  caller must handle (this Stage defines that error explicitly).
- **Why chosen:** Simplest option that respects LAYOUT, is the most testable, and
  is the established project pattern. Simple-and-swappable.

### Alternative B — Declare the Protocol as a *domain* port
- **Description:** Put the `Protocol` the domain consumes in `shared/domain/` and
  have the adapter implement it (a "domain port").
- **Pros:** Lets the domain service reach for sessions lazily; one fewer VO type.
- **Cons:** Introduces a concept — a port living in the domain — that exists
  nowhere else in this project (every other port is an `application/ports/out/`
  Protocol: `MedallionStore`, `ExperimentTracker`, `Hasher`, `Clock`). It would be
  a one-off pattern to learn and police; the domain would still need the sessions
  loaded by *someone*, so it does not actually remove the materialization step,
  only relocates the interface. Contradicts the roadmap, which explicitly places
  the port in `application/ports/out/`.
- **Why rejected:** Adds a novel architectural concept for no real gain over (A);
  the materialization still happens. Higher cognitive cost, same runtime work.

### Alternative C — Make `TradingCalendar` an application service
- **Description:** Move the calendar arithmetic into the application layer where it
  may call the port directly.
- **Pros:** No VO needed; the service can lazily pull sessions through the port.
- **Cons:** Removes calendar logic from the domain, contradicting both the roadmap
  (which names it a domain service) and the project's domain-service pattern; the
  arithmetic (`trading_day_from_timestamp`, `shift_trading_days`) is pure business
  logic with invariants — exactly what ADR 0.0.0020 says belongs in the domain over
  a VO; it would tempt direct library use in the orchestration layer (the failure
  mode 0.0.0020 §Alternative B rejects for statistics).
- **Why rejected:** Misplaces domain logic into application and erodes the very
  boundary the project protects.

### Alternative D — Do nothing / replicate the old weekday-only calendar in the domain
- **Description:** Port the old `_roll_to_business_day` (weekday roll, no holidays)
  straight into the new domain, hard-coding the calendar.
- **Why rejected:** The old calendar has **no real holidays** — it is the documented
  gap (sentiment/feature code used `weekday<5` and `pd.bdate_range`, both missing
  NYSE holidays). A pilot whose anti-leakage and embargo depend on real session
  boundaries cannot ship a calendar that treats 2023-07-04 as a trading day.

## Consequences

### Positive
- The domain service is a pure function over a value object: testable in isolation
  against deterministic fixtures (known NYSE 2023 holidays), no I/O, no mocks.
- `exchange-calendars` is swappable behind the port; switching calendar source
  (or adding a second exchange) is an adapter change, not a domain rewrite.
- One contract test proves fake↔real parity (ADR 0.0.0021 posture), so the
  in-memory fake the application tests against is guaranteed to behave like XNYS.
- The architecture gates pass without `TYPE_CHECKING` escape hatches — the
  inward-only direction is honored structurally.

### Negative
- The caller must materialize a sufficiently wide `[start, end]` window before the
  domain service runs; a lookup/offset beyond the window is an explicit error
  rather than a lazy fetch. (Acceptable: the pilot's windows are known up front.)
- Extra ceremony: a VO + port + adapter triple instead of one library call — the
  same trade-off ADR 0.0.0020 already accepts for statistics.

### Neutral / trade-offs accepted
- The VO holds the whole window's session set in memory. For the AAPL pilot (daily
  frequency, bounded history) this is trivially small; revisable under a new ADR if
  a multi-decade multi-asset materialization ever becomes heavy.
- `close_hour` is passed per call to `trading_day_from_timestamp` (semantic carried
  from the old `TradingDayPolicy.close_hour`), not stored on the VO; the VO is the
  *session set*, not the intraday policy.

## Implementation notes
- VO: `shared/domain/value_objects/trading_sessions.py`, `@dataclass(frozen=True)`,
  stdlib-only; sorted tuple of `date` + `bisect` membership; `start`/`end` bounds.
- Domain service: `shared/domain/services/trading_calendar.py`, stdlib-only;
  `trading_day_from_timestamp` raises `ValueError` on naive `ts`, normalizes via
  `astimezone(UTC)`, and rolls to the **next session** (not merely the next civil
  day) when `ts.time() > close_hour`; `shift_trading_days` takes an explicit
  `direction` (forward/backward) — it does **not** inherit the old roll-forward-only
  behavior, because the 5.1 embargo needs backward offsets.
- Port: `shared/application/ports/out/exchange_calendar_provider.py`, structural
  `Protocol`, `sessions(start, end) -> TradingSessions`; mirrors the shape of
  `medallion_store.py`/`experiment_tracker.py`.
- Adapter: `shared/adapters/out/calendar/exchange_calendars_provider.py`,
  `get_calendar("XNYS")`; `exchange-calendars` pinned in `pyproject.toml`,
  `uv.lock` regenerated in the same commit.
- Fake: `tests/fakes/shared/in_memory_exchange_calendar_provider.py`, stdlib-only,
  satisfies the Protocol from a hand-built session set; same contract test as the
  real adapter (`tests/contract/shared/test_exchange_calendar_provider_contract.py`).

## References
- Related ADRs:
  [0.0.0019 — hexagonal enforced](./0_0_0019-hexagonal-enforced.md) (the gate that
  forbids domain→application at runtime);
  [0.0.0020 — statistics in domain over value objects](./0_0_0020-statistics-in-domain-over-value-objects.md)
  (the "boundary = value object" pattern applied here);
  [0.0.0021 — per-unit contract tests with oracle](./0_0_0021-per-unit-contract-tests-with-oracle.md)
  (fake↔real contract-test posture);
  [2.1.0002 — MedallionStore port shape](./2_1_0002-medallion-store-port-shape.md)
  (Protocol-not-ABC, no-library-leak port shape mirrored here).
- Overview: `docs/overview.md` §6 (Restrições — domínio puro), §7 (Abordagem),
  §11 (Arquitetura e ferramentas — `0.0.0019`/`0.0.0020`).
- Roadmap: `docs/roadmap.md` Stage `2.4-trading-calendar`.
- Old repo: `financial-time-series-forecasting/src/domain/time/trading_calendar.py`
  (`TradingDayPolicy` + `trading_day_from_timestamp`; naive weekday-only roll, **no
  holidays** — semantics replicated, holiday mechanism replaced by
  `exchange-calendars`); `.../src/use_cases/sentiment_feature_engineering_use_case.py:184-190`
  and `.../src/domain/services/data_quality_reporter.py:175-181` (the weekday-only /
  `pd.bdate_range` gaps this Stage closes).
- Conversation/issue: GitHub issue #17.
