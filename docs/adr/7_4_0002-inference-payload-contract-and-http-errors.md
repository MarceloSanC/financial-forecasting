---
title: ADR 7.4.0002 — Inference payload contract (integer schema_version in the body, explicit infinity, labels checked against their evaluation owners) and HTTP error mapping through global handlers keeping the project's error body
description: Architecture Decision Record
when-use: Reference when changing the payload of POST /inference/run (when to bump schema_version), when serializing an infinite limit, when adding an HTTP error mapping, or when asking why the API does not use /api/v1, problem+json or status 400/422 for missing data
keywords: [adr, inference-api, payload, schema-version, versioning, backward-compatibility, json, infinity, labels, http-errors, exception-handlers, problem-details, fastapi]
status: accepted
created_at: 2026-10-21
updated_at: 2026-10-21
adr_id: 7.4.0002
decision: Every 200 answer of POST /inference/run carries an integer schema_version in the body (1 at birth; bumped when a field is removed, renamed, changes type or meaning — a label included — and not bumped for a new optional field whose absence keeps the previous behaviour), every limit that can be infinite (conformal and H3 share intervals) carries an *_infinite flag (null + true ⇔ infinite; null + false only without a value), the labels are the evaluation domain constants, always present, with the labels stored in the gold checked against them (the H3 reading label in every status; a VSN row's label per its status), and errors are mapped only by the global handlers in shared/infrastructure/http — NotFoundError → 404, DomainError → 422 and a new ApplicationError → 500 with the project's {detail, type} body, while request validation keeps FastAPI's standard 422 body.
context_stage: 7.4-inference-api
bounded_context: inference
---

# ADR 7.4.0002 — Inference payload contract and HTTP error mapping

> ADRs are written and consumed in **English**, even when the rest of the project docs are in Portuguese. This keeps them grep-friendly and reusable across projects.

## Status

`accepted` — Stage 7.4 concept (issue #201), 2026-10-21. The status code of
missing data (404) is the human's (B1/B3, ADR 7.4.0001 item 4); the rest
closes by evidence or convention (skill `evidence-resolution`). Revised after
Checkpoint A before the concept was approved.

## Context

- The roadmap fixes the route `POST /inference/run` and asks for "payload com
  schema versionado definido no technical da Stage"; the inference domain doc
  §6 abandons the old "contrato P2" and leaves the schema to this Stage.
- Conformal limits can be infinite (rank above n, ADR 7.2.0002), and so can
  the bootstrap bounds of the H3 shares; the gold stores both as `null` + an
  `infinite`/`*_infinite` flag (technical 7.2 §1; `h3_shares` builder).
- JSON has no infinity: "Numeric values that cannot be represented in the
  grammar below (such as Infinity and NaN) are not permitted" (RFC 8259 §6).
  Starlette 1.3.1 `JSONResponse.render` calls `json.dumps(...,
  allow_nan=False)`, and with a response model Pydantic 2.13 serializes
  `inf` as `null` (`ser_json_inf_nan = 'null'`) — a silent loss of meaning,
  not an error.
- The project's HTTP handlers (Stage 1.1, ADR 1.1.0001) answer
  `NotFoundError → 404` and `DomainError → 422` with `{"detail", "type"}`;
  `ApplicationError` has no handler (FastAPI then answers a plain-text 500).
  FastAPI answers body validation with 422 and `{"detail": [...]}` (a list of
  errors), which its generated OpenAPI documents.
- The labels "cobertura empírica (não garantida)", "descritiva (sem claim
  causal)" and the VSN's horizon-invariant label are constants of the
  evaluation domain (`EMPIRICAL_COVERAGE_LABEL`, `H3_LABEL`, `VSN_LABEL`);
  `gold_h3_reading` and `gold_h3_vsn` also store the label of the generation.
  The inference domain doc §4.11 makes the first mandatory "em toda tabela,
  gráfico e payload".

## Decision

1. **Version in the body.** `[decision:C] 7.4-VER — where the payload version lives`
   `Escolha: integer schema_version in the response body · Alternativas: /api/v1 path prefix (AIP-185); version header or media type; "major.minor" string · Degrau: 1`
   Base: project precedent of a per-record `schema_version` bumped locally
   (ADR 4.1.0001) and the roadmap's fixed route without a version segment;
   the version travels with the document, which can be stored and re-read
   off the route. No primary source chooses between body, path and header —
   convention. `Reversível: sim (a path prefix can be added later).`
2. **When to bump.** `[decision:E] 7.4-BUMP — breaking vs additive change`
   `Escolha: bump on removal, rename, type change or change of meaning (labels included); no bump for a new optional field whose absence keeps the previous behaviour`
   Base: Google AIP-180 — new fields may be added in the same major version
   when they are not required and keep the previous behaviour; "Removing a
   component is a backwards incompatible change"; visible semantics must not
   change "in ways that are likely to break reasonable user code". A label
   ("empírica", "descritiva") is semantics: changing it bumps.
3. **Explicit infinity.** `[decision:E] 7.4-INF — infinite limits in JSON`
   `Escolha: lower_infinite/upper_infinite flag on every limit that can be infinite (conformal intervals and H3 share bounds): null + true ⇔ infinite; null + false only when the interval or share status is not ok (no value); a finite number + false otherwise`
   Base: RFC 8259 §6; Starlette `JSONResponse.render(allow_nan=False)`;
   Pydantic's silent `null`; the gold's `null` + flag convention. The
   application DTOs keep `math.inf` (and `None` for "no value"); only the
   HTTP schema maps them, and no other (value, flag) pair is emitted.
4. **Labels from their owners, checked against the gold.** `[decision:E] 7.4-LABEL`
   The three payload labels are the evaluation domain constants
   (`EMPIRICAL_COVERAGE_LABEL`, `H3_LABEL`, `VSN_LABEL`), always present, also
   in an `unavailable` block (doc §4.11: "em toda tabela, gráfico e
   payload"). The evaluation reader checks what the generation stored: the
   `gold_h3_reading` row carries `H3_LABEL` (the builder writes it in every
   status); every `ok` row of `gold_h3_vsn` carries `VSN_LABEL` and every
   non-`ok` row a null label (an `undefined` summary, a legitimate state) —
   any other combination is a `GoldGenerationCorruptError` (ADR 7.4.0001 item
   7). No literal of the labels in the inference slice or the adapter.
   Inference domain doc §2.4, §4.11, §5.8.
5. **Error mapping only in global handlers.** `[decision:C] 7.4-ERR — error body and mapping`
   `Escolha: keep {detail, type} for domain and application errors and add ApplicationError → 500 ("application_error"); keep FastAPI's standard 422 body for request validation · Alternativas: RFC 9457 problem+json; a custom validation handler flattening errors; 400 or 422 for missing data; handling inside the route · Degrau: 1 (project body) e 2 (FastAPI default)`
   Base: the project's handlers already define the error body; RFC 9457 §4
   allows that "an application might have a more appropriate way to carry an
   error in a format that it already defines"; FastAPI's validation body is
   the reference implementation's default and is documented in the OpenAPI it
   generates. Missing data → 404 is the human's decision. Data defects reach
   the handler as `ApplicationError` (ADR 7.4.0001 item 3). The route catches
   nothing (skill `fastapi-thin-adapter`: "Don't catch exceptions and return
   JSON manually — register a handler").
6. **Route and in-port.** `POST /inference/run` as the roadmap fixes it; the
   in-port is the use case `ServeInference`, injected with `Depends` and
   replaced in `app.py` through `dependency_overrides` — the project's wiring
   pattern (LAYOUT §5 option 2, §6), although FastAPI documents
   `dependency_overrides` under testing.

## Alternatives considered

### Alternative A — Version in the path (`/api/v1/inference/run`)
- **Pros:** Google AIP-185 puts the major version "as the first part of the URI
  path for REST APIs"; the template's `app.py` sketch uses `/api/v1`.
- **Cons:** contradicts the roadmap's route; the version would not travel
  with a stored payload.
- **Why rejected:** degree 1 (roadmap + ADR 4.1.0001 precedent). Adding a
  prefix later does not break the body version.

### Alternative B — RFC 9457 problem details (`application/problem+json`)
- **Pros:** standard members (`type` as URI, `title`, `status`, `detail`).
- **Cons:** changes the project's existing error body and requires
  overriding FastAPI's validation handler; under that media type the
  existing `"type": "not_found"` would read as a relative URI.
- **Why rejected:** degree 1; RFC 9457 §4 allows an application's own format.

### Alternative C — Flatten request validation into `{detail, type}`
- **Pros:** one body for every 4xx.
- **Cons:** loses the per-field error list FastAPI documents; one more
  handler that every route inherits.
- **Why rejected:** degree 2 (reference implementation default).

### Alternative D — 400 or 422 for missing data
- **Pros:** RFC 9110 §15.5.5 defines 404 for the *target resource*, and the
  missing (asset, date) travels in the body; Amazon Forecast answers
  `ResourceNotFoundException` with 400.
- **Cons:** 422 already means request validation and `DomainError` in this
  app; 400 would hide "not found" among malformed requests.
- **Why rejected:** human decision (404, "não há dados para o pedido
  solicitado"); using 404 for an item named in the body is the project's
  judgment, not the RFC's text.

### Alternative E — Infinity as a string (`"Infinity"`) or a large sentinel
- **Cons:** a string breaks the numeric type; a sentinel is a fake number a
  client can use in arithmetic.
- **Why rejected:** `null` + flag is explicit and is the gold's convention.

### Alternative F — Status quo (no ApplicationError handler)
- **Cons:** gold corruption and inconsistent silver would surface as a
  plain-text "Internal Server Error".
- **Why rejected:** one general handler covers every route.

## Consequences

### Positive
- A client knows which contract it parsed; a stored payload is
  self-describing.
- Domain and application errors share one body; validation errors keep the
  documented FastAPI body.

### Negative
- Clients read two fields for an infinite limit.
- Two error body shapes coexist under 422 (domain vs validation).
- Exceptions outside the mapped hierarchies (e.g. an I/O error of the storage
  engine) still answer FastAPI's plain-text 500.

### Neutral / trade-offs accepted
- The HTTP QUERY method (RFC 10008, 2026) would state a safe query
  explicitly; the route stays POST as the roadmap fixes it.

## References

- Related ADRs: 1.1.0001, 4.1.0001, 7.2.0002, 7.2.0003, 7.4.0001.
- Bray, T. (ed.) (2017). RFC 8259 *The JavaScript Object Notation (JSON)
  Data Interchange Format*, §6.
- Fielding, R., Nottingham, M., Reschke, J. (2022). RFC 9110 *HTTP
  Semantics*, §9.3.3, §15.3.1, §15.5.5.
- Nottingham, M., Wilde, E., Dalal, S. (2023). RFC 9457 *Problem Details for
  HTTP APIs*, §4.
- Reschke, J., Snell, J., Bishop, M. (2026). RFC 10008 *The HTTP QUERY
  Method*, §1.
- Google API Improvement Proposals: AIP-180 "Backwards compatibility",
  AIP-185 "API Versioning" (google.aip.dev).
- JSON:API v1.1, §"JSON:API Object" (version member in the document).
- Starlette 1.3.1 `responses.py` (`JSONResponse.render`); Pydantic 2.13
  `config.py` (`ser_json_inf_nan`); FastAPI docs, "Handling Errors" and
  "Testing Dependencies with Overrides"; FastAPI 0.138.1
  `exception_handlers.py` (`request_validation_exception_handler`).
- Issue #201 (`## Referências`).
