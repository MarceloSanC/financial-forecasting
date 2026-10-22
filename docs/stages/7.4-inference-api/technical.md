---
title: Technical — Stage 7.4 — API de inferência
description: Plano de execução da API de inferência — DTOs e port do leitor do gold servido, use case ServeInference sobre as predições de teste gravadas, leitor ReadServingGold no evaluation com a aresta declarada, contrato [fake, real], handler de ApplicationError, rota POST /inference/run, wiring e e2e, gate de torch fora do processo da API e docs (1 Task = 1 commit)
when-use: Consultar durante a Fase 4 (execução) da Stage 7.4; cada Task tem arquivos (lista fechada), o que fazer, critério de aceite, verificação e commit; §3 traz a verificação end-to-end sobre o cohort real e a medição de tempo
keywords: [technical, plano de execução, inference-api, serve-inference, serving-gold-reader, read-serving-gold, fastapi, router, error-handlers, e2e, import-linter, coverage]
status: done
created_at: 2026-10-21
updated_at: 2026-10-21
stage_id: 7.4-inference-api
stage_title: API de inferência
step_id: 7
step_title: Inferência, conformal, explicabilidade e API
depends_on: [7.2-conformal-cqr, 7.3-explainability]
concept_ref: ./concept.md
issue_id: 201
branch: feat/201-7-4-inference-api
tasks_count: 10
---

# Technical — Stage 7.4 — API de inferência

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.** A
>    verificação da Task roda só os testes dela; o `make check` completo
>    roda só nos pontos do [plano de gates](#plano-de-gates).
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [N.M/task-NN]` (subject ≤ 100 caracteres,
>    `scripts/check_commit_msg.py`).
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage N.M: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/201-7-4-inference-api` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo

A API serve, sem rodar o modelo, as predições `split = "test"` do candidato já
gravadas em `fact_oos_predictions`, com o intervalo conformal da variante de
registro aplicado por `PairCorrection.limits` e a leitura de H3, ambos lidos do
gold. O núcleo é o use case `ServeInference` (inference/application), que lê o
silver pelo `SilverTableReader` existente e o gold pelo port novo
`ServingGoldReader`, satisfeito no evaluation por `ReadServingGold` (sobre o
`GoldGenerationReader`). O adapter HTTP é fino; os erros saem pelos handlers
globais. Decisões: concept D1–D15; ADRs 7.4.0001 e 7.4.0002.

### Estratégia

TDD inside-out (skill `task-ordering-hex`): DTOs + port + fake (01) → exceção +
use case com fakes (02) → leitor real no evaluation com a aresta declarada (03)
→ contrato `[fake, real]` (04) → handler `ApplicationError` (05) → adapter HTTP
(06) → wiring + e2e (07) → gate de torch fora do processo da API (08) → docs
(09, 10). Cada commit deixa os testes da Task verdes. O port é criado na 01 e o
seu real só na 03 (port e adapter em Tasks separadas, PIPELINE §4.3); o
`check_port_coverage.py` fica vermelho entre a 01 e a 04 (port sem contrato), o
que não aparece no T1 e se fecha antes do único `make check`.

### Pré-condições

- Stages 7.2 e 7.3 `done` e mergeadas em `develop` (`3573e77`).
- Concept 7.4 `done` (`c64dc30`); roadmap alinhado (`333cc36`, `ff3bdb9`,
  `073da06`).
- Worktree `../financial-forecasting-worktrees/feat-201-7-4-inference-api` com
  `make setup` (hooks `pre-commit` e `commit-msg`).

### Premissas técnicas

- Python 3.12, FastAPI 0.138.1, Starlette 1.3.1, Pydantic 2.13.4, httpx 0.28.1
  (já no `uv.lock`; nenhuma dependência nova).
- Formatação só dos arquivos tocados com `uvx ruff@0.6.9 format <arquivos>`,
  guardado por `[ -n "$F" ] || exit 1` (regra herdada da 7.3: os dois ruff
  divergem; issue #198).
- O mypy do projeto só cobre `src/` (`pyproject.toml` `files = ["src"]`; hook
  com `files: ^src/`): fakes e contratos são checados por `uv run mypy
  --strict <arquivos>` explícito no T1 das Tasks 01 e 04 (precedente: technical
  1.4, 2.1, 4.2).
- Testes de HTTP com `fastapi.testclient.TestClient` (síncrono; o
  `StarletteDeprecationWarning` do httpx não bloqueia — sem `-W error`).
- Pastas de teste de adapter primário usam `in_` (keyword; precedente
  `tests/unit/features/modeling/adapters/in_/`).
- O `pyproject.toml` exclui hoje `*/shared/infrastructure/http/*` da cobertura
  ("consumido só no Step de API (7.4)"); a Task 07 tira essa entrada.

### Contratos (assinaturas finais)

**`inference/application/dtos/serving_gold.py`** (frozen; `AVAILABLE =
"available"`, `UNAVAILABLE = "unavailable"`):

- `ConformalCorrectionRecord(fold_raw: str, seed: int, horizon: int,
  lower_level: float, upper_level: float, variant: str, tail: str,
  tail_level: float, status: str, reason: str | None, n: int | None,
  rank: int | None, correction: float | None)` — `tail ∈ {"lower","upper"}`;
  `status ∈ {"ok","undefined","error"}`; `status == "ok"` ⇒ `correction` e
  `n` não nulos (`math.inf` permitido, NaN recusado).
- `H3ShareRecord(method: str, family: str, share_h1: float | None,
  share_h7: float | None, delta: float | None, lower: float | None,
  upper: float | None, level: float | None, side: str | None,
  excludes_zero: bool | None, status: str, reason: str | None)` — `lower`/`upper`
  podem ser `±inf`; `status == "ok"` ⇒ `lower` e `upper` não nulos.
- `H3ReadingRecord(reading_rule: str, heterogeneous_permutation: bool | None,
  heterogeneous_ablation: bool | None, sustained: bool | None,
  agreeing_families: tuple[str, ...], n_points: int | None, status: str,
  reason: str | None)`.
- `VsnRecord(kind: str, name: str, family: str, p10: float | None,
  p50: float | None, p90: float | None, n_decisions: int | None, status: str,
  reason: str | None)`.
- `ServingGold(published: bool, generation_status: str | None,
  preregistration_ref: str | None, candidate: str | None,
  finished_at: str | None, conformal_status: str, conformal_reason: str | None,
  explainability_status: str, explainability_reason: str | None,
  conformal_label: str, h3_label: str, vsn_label: str,
  corrections: tuple[ConformalCorrectionRecord, ...],
  shares: tuple[H3ShareRecord, ...], reading: H3ReadingRecord | None,
  vsn: tuple[VsnRecord, ...])` — status de bloco ∈ {`available`,
  `unavailable`}; `unavailable` ⇒ motivo não vazio e registros do bloco vazios
  (`corrections = ()`; `shares = ()`, `reading = None`, `vsn = ()`);
  `available` ⇒ motivo `None`; `published = False` ⇒ os dois blocos
  `unavailable` e os campos da geração `None`; `finished_at` em
  `datetime.isoformat()`; os três rótulos sempre não vazios; fábrica
  `ServingGold.unpublished(*, reason, conformal_label, h3_label, vsn_label)`.

**`inference/application/ports/out/serving_gold_reader.py`**:
`class ServingGoldReader(Protocol): def read(self, *, asset: str, cohort_id: str) -> ServingGold: ...`
— anotação textualmente igual à do `ReadServingGold.read` (o
`check_port_coverage.py` compara texto; verificado por simulação no
Checkpoint B).

**`inference/domain/exceptions/serving.py`**:
`NO_SERVED_DATA = "não há dados para o pedido solicitado"`;
`class NoServedDataError(NotFoundError)` com `__init__(self, missing: str)` →
mensagem `f"{NO_SERVED_DATA}: {missing}"`.

**`inference/application/use_cases/serve_inference.py`** (frozen):

- `ServingScope(cohort_id: str, asset: str, feature_set_name: str,
  model_version: str, horizons: tuple[int, ...], quantile_levels:
  tuple[float, ...], seeds: tuple[int, ...])` — não vazios; horizontes e seeds
  únicos e crescentes; níveis estritamente crescentes em (0, 1), com mediana
  0.5 e simétricos por `exact_level` (`exact_level(lo) + exact_level(hi) ==
  1`); propriedade `pairs: tuple[tuple[float, float], ...]` do externo ao
  interno.
- `ServeInferenceQuery(asset: str, decision_date: date, horizons:
  tuple[int, ...] | None = None, seeds: tuple[int, ...] | None = None)` —
  vazio ou repetido → `ValueError`.
- `ConformalInterval(lower_level, upper_level, status, gold_status, reason,
  lower: float | None, upper: float | None)` — `status == "ok"` ⇒ `lower` e
  `upper` não nulos (podem ser `±inf`); `unavailable` ⇒ os dois `None`.
- `ConformalBlock(status, reason, label, variant, intervals)` — `variant` é
  sempre `ConformalVariant.SPLIT_CQR.value`; `unavailable` ⇒ `intervals = ()`.
- `SeedForecast(seed, fold, run_id, quantiles, conformal)`;
  `HorizonForecast(horizon, target_date: date, members)`.
- `ExplainabilityBlock(status, reason, label, shares, reading, vsn,
  vsn_label)` — `unavailable` ⇒ `shares = ()`, `reading = None`, `vsn = ()`.
- `GoldProvenance(published: bool, generation_status, preregistration_ref,
  candidate, finished_at)`.
- `InferencePayload(asset, decision_date, cohort_id, model_version,
  quantile_levels, forecasts, explainability, gold)`.
- `ServeInference(*, scope: ServingScope, silver: SilverTableReader, gold:
  ServingGoldReader)`; `__call__(query: ServeInferenceQuery) ->
  InferencePayload`.

**`evaluation/application/use_cases/read_serving_gold.py`**:
`ReadServingGold(*, gold_reader: GoldGenerationReader)`;
`read(self, *, asset: str, cohort_id: str) -> ServingGold`.

**HTTP** (`inference/adapters/in/http/`):
`router = APIRouter(prefix="/inference", tags=["inference"])`;
`get_serve_inference() -> ServeInference` (padrão: ergue
`ServingNotConfiguredError(ApplicationError)` "serviço de inferência sem
cohort configurado"); `POST /run` com `InferenceRunRequest` →
`InferenceRunResponse` (`schema_version: Literal[1]`). Limites: `lower`,
`upper` (`float | None`) + `lower_infinite`, `upper_infinite` (`bool`) nos
intervalos conformais e nas participações de H3, com a regra: `±inf` no DTO →
`null` + `true`; `None` no DTO (sem valor, status não-`ok`) → `null` +
`false`; finito → número + `false`, em qualquer status. Floats da resposta com
`allow_inf_nan=False` (`Annotated[float, Field(allow_inf_nan=False)]`).

**Composition root**: `ApplicationDependencies.serve_inference_for:
Callable[[Path], ServeInference]` e `register_http_routes(app: FastAPI, deps:
ApplicationDependencies, *, serving_cohort_file: Path | None) -> None` — carrega
o módulo do router por `importlib` (o `in` é keyword; precedente
`_MODELING_CLI`), troca o provedor quando há cohort e inclui o router.
`FastAPI` só sob `TYPE_CHECKING` (a CLI não importa fastapi por isso). O
`app.py` delega a essa função: o `shared/http` continua importando só o
composition root (contrato `shared-no-features`; LAYOUT §6).

### Fluxo do `ServeInference` (concept I2–I8, I13)

1. Ativo ≠ `scope.asset` → `NoServedDataError("ativo …")`. Horizontes/seeds
   pedidos (ou os do escopo) fora do escopo → `NoServedDataError`.
2. `dim_run` (`layer="silver"`, filtros `{"asset", "parent_sweep_id":
   cohort_id}`), só `model_version == scope.model_version` (o mesmo
   `parent_sweep_id` tem `gbm_quantile` com seed). Zero runs → `ApplicationError`
   ("o silver não tem runs do cohort …; confira o DATA_ROOT"). Seed do escopo
   sem run, ou run do candidato sem `fold` → `ApplicationError`.
3. `fact_oos_predictions` (filtros `{"asset", "feature_set_name", "year":
   decision_date.year}`), só `run_id` do cohort, `split == "test"`, horizonte
   pedido e `datetime.fromisoformat(timestamp_utc).date() == decision_date`.
4. Por (seed, horizonte) pedido: zero runs → acumula em "faltou"; mais de um →
   `ApplicationError`. "Faltou" não vazio → `NoServedDataError` com a decisão e
   os (seed, horizonte) faltantes.
5. Grade por (run, horizonte): níveis = `scope.quantile_levels` exatos (falta ou
   repetição → `ApplicationError`), valor `value_guardrail`; `target_date` da
   data de `target_timestamp_utc`, igual entre seeds do horizonte (senão
   `ApplicationError`).
6. `gold.read(asset, cohort_id)`. Precedência do concept I8 (não publicado >
   `BLOCKED` > outro candidato > bloco ausente): os dois primeiros e o último
   vêm prontos do leitor; o use case aplica "outro candidato" só com gold
   publicado e `COMPLETED` (`candidate != scope.model_version` → os dois
   blocos `unavailable`, "geração gold de outro candidato: …", sobrescrevendo
   "bloco ausente"). Os três rótulos do payload vêm do `ServingGold` em
   qualquer estado.
7. Conformal por membro e par (variante `SPLIT_CQR`; chave `(fold_raw, seed,
   horizonte, exact_level(lo), exact_level(hi))`): sem linhas → intervalo
   `unavailable` ("unidade ausente na geração gold"); uma cauda →
   `ApplicationError`; duas `ok` → `PairCorrection(variant, None,
   TailCorrection(tail, tail_level, alpha, n, rank, correction,
   math.isinf(correction)), …).limits(lower=q_lo, upper=q_hi)`; senão
   `unavailable` com o `gold_status` da primeira cauda não-`ok` e o motivo do
   gold. `alpha` da cauda: `exact_level(lo)` e `1 - exact_level(hi)`.
8. `ValueError` ao montar DTO/VO a partir do lido → `ApplicationError` com
   contexto (I13).

### Fluxo do `ReadServingGold` (concept I7, I8)

1. `GoldPartition(asset, cohort_id)`; `read_generation`; **só**
   `GoldManifestNotFoundError` → `ServingGold.unpublished(reason="gold não
   publicado para o cohort …", labels)`.
2. `manifest.status == BLOCKED` → publicado, os dois blocos `unavailable`
   ("geração gold BLOCKED"), sem ler tabela.
3. Conformal: `parameters.conformal_parameters is None` → `unavailable`
   ("geração sem bloco [conformal]"); senão os registros de
   `GOLD_CONFORMAL_CORRECTIONS` pelos `col_*` (`infinite = true` →
   `math.inf`); linha com `seed` nulo (unidade de run sem seed, nunca servida)
   é descartada (`col_int_or_none`).
4. Explicabilidade: `parameters.h3_parameters is None` → `unavailable`
   ("geração sem bloco [h3]"); sem linha em `GOLD_H3_READING` → `unavailable`
   ("leitura de H3 ausente na geração"); senão shares (flags → `±inf`; flag
   nula → `None`), reading (`agreeing_families` separado por vírgula, vazio →
   `()`) e VSN (medidas nulas aceitas). Conferência do que foi gravado: linha
   de reading com `label != H3_LABEL`, linha `ok` de VSN com `label !=
   VSN_LABEL` ou linha não-`ok` de VSN com `label` não nulo →
   `GoldGenerationCorruptError`; VSN `undefined` é bloco `available` com linhas
   não-`ok`.
5. Rótulos do `ServingGold`: `EMPIRICAL_COVERAGE_LABEL`, `H3_LABEL`,
   `VSN_LABEL`. `ValueError` de DTO → `GoldGenerationCorruptError`.

### Excedente `http/` do template (ADR 1.1.0001)

Ligados nesta Stage: `app.py` (registro do router pela composition root e
`create_app(settings)`) e `error_handlers.py` (handler `ApplicationError`); os
três passam a contar na cobertura (Task 07). Mantido: `middlewares.py` (CORS do
template; sem credencial servida, autenticação é non-goal — concept D14),
exercitado pelo `create_app`. Fora do `http/`: `database/` segue com o Step de
storage.

### Plano de gates

| # | Depois da Task | Por quê |
|---|---|---|
| 1 | saída (Task 10) | gate de saída (Passo 10). Sem ponto no meio, porque cada mudança de risco tem verificação própria no T1 e só Tasks de teste e docs vêm depois da última delas: a 03 e a 08 (`.importlinter`, `tests/architecture/`) rodam `lint-imports` e os casos de arquitetura que criam (motivo concreto: aresta nova entre slices / contrato estendido); a 05 (`shared/http`) roda a suíte nova do handler; a 07 (composition root, settings, `app.py`, `pyproject.toml`) roda as suítes do composition root, das settings e da CLI, afirma as rotas da app e mede a cobertura de `shared/infrastructure/http/` |

### Estrutura de pastas afetada

```
pyproject.toml                                           (07: omit da cobertura)
src/financial_forecasting/
├── composition_root.py                                  (07)
├── shared/infrastructure/
│   ├── config/settings.py                               (07)
│   └── http/{app.py (07), error_handlers.py (05)}
└── features/
    ├── inference/
    │   ├── domain/exceptions/{__init__,serving}.py      (02)
    │   ├── application/dtos/{__init__,serving_gold}.py  (01)
    │   ├── application/ports/out/serving_gold_reader.py (01)
    │   ├── application/use_cases/serve_inference.py     (02)
    │   └── adapters/in/http/{__init__,inference_router}.py, schemas/{__init__,inference_schemas}.py (06)
    └── evaluation/application/use_cases/read_serving_gold.py (03)
tests/
├── fakes/features/inference/in_memory_serving_gold_reader.py               (01)
├── unit/features/inference/application/{test_serving_gold_dtos,test_serve_inference}.py (01, 02)
├── unit/features/evaluation/test_read_serving_gold.py                       (03)
├── unit/shared/infrastructure/http/{__init__,test_error_handlers}.py        (05)
├── contract/features/inference/test_serving_gold_reader_contract.py         (04)
├── integration/features/inference/adapters/in_/http/test_inference_router.py (06)
├── e2e/features/inference/{test_inference_api_e2e,test_inference_api_no_deep_learning}.py (07, 08)
└── architecture/test_import_contracts.py                                    (03, 08)
.importlinter                                                                (03, 08)
docs/{LAYOUT.md, adr/0_0_0053-*.md} (09); docs/{overview.md, adr/7_1_0001-*.md, stages/7.1-inference-engine/concept.md} (10)
```

## 2. Tasks

> Faixa saudável: **3–12 Tasks por Stage** (CONVENTIONS §6). ≥ 14 =
> Stage grande demais; reabrir Fase 3A para dividir.

### Task 01 — DTOs e port do leitor do gold servido, com fake

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/dtos/__init__.py`
    (obrigatório: sem ele o grimp não resolve o módulo da aresta da Task 03)
  - `src/financial_forecasting/features/inference/application/dtos/serving_gold.py`
  - `src/financial_forecasting/features/inference/application/ports/out/serving_gold_reader.py`
  - `tests/fakes/features/inference/in_memory_serving_gold_reader.py`
  - `tests/unit/features/inference/application/test_serving_gold_dtos.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** os DTOs de §1 "Contratos" com validação em `__post_init__`
  (`ValueError`) e a fábrica `ServingGold.unpublished`; o `Protocol`
  `ServingGoldReader` com docstring de port do consumidor (real:
  `ReadServingGold` do evaluation; política: sem geração → não publicado,
  geração que não se sustenta → `ApplicationError`); o fake
  `InMemoryServingGoldReader(golds: Mapping[tuple[str, str], ServingGold],
  *, error: Exception | None = None)`, que devolve o `ServingGold` carregado
  para a partição — **sem fallback**: partição não carregada ergue `KeyError`
  (o teste carrega `ServingGold.unpublished` explicitamente) —, registra as
  chamadas e ergue `error` se configurado.
- **Detalhes técnicos:** só stdlib e `typing` na application; nenhum import do
  evaluation em `src/`.
- **Critério de aceite:** cada recusa dos DTOs tem caso (tail inválida; status
  inválido; `ok` sem correção ou sem `n`; share `ok` sem limite; NaN; bloco
  `unavailable` sem motivo ou com registros; `available` com motivo; não
  publicado com bloco `available` ou com campos de geração; rótulo vazio);
  `unpublished` válido; `+inf` aceito; o fake sem carga ergue.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/inference/application/test_serving_gold_dtos.py -q --no-cov
  uv run mypy --strict tests/fakes/features/inference/in_memory_serving_gold_reader.py
  ```
- **Commit sugerido:** `feat(inference): DTOs e port do leitor do gold servido, com fake [7.4/task-01]`

---

### Task 02 — Exceção de "sem dado" e use case `ServeInference`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/domain/exceptions/__init__.py`
  - `src/financial_forecasting/features/inference/domain/exceptions/serving.py`
  - `src/financial_forecasting/features/inference/application/use_cases/serve_inference.py`
  - `tests/unit/features/inference/application/test_serve_inference.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** `NoServedDataError` e o use case com os DTOs de §1 e o
  fluxo de §1 "Fluxo do `ServeInference`". Silver pelo `SilverTableReader` do
  inference (o mesmo port da 7.1); gold pelo `ServingGoldReader`.
- **Detalhes técnicos:** `PairCorrection`, `TailCorrection`,
  `ConformalVariant` e `exact_level` do domain do inference (sem fórmula nova);
  nenhum literal de rótulo (vêm do `ServingGold`); ordem fixa de horizontes,
  seeds, níveis e pares (I11).
- **Critério de aceite** (fakes: `FakeSilverTableReader` do evaluation e
  `InMemoryServingGoldReader`):
  - caminho feliz com valores **literais** esperados (Q̂_lo ≠ Q̂_hi; um
    intervalo cruzado servido sem correção; um `+inf`) (CA1, CA4);
  - data na sobreposição teste do fold k / calib do fold k+1 → run do fold k;
    data só de calib → 404; h+7 das últimas sessões → 404 e só h+1 → 200
    (CA1, CA2);
  - 404 por ativo, horizonte, seed e decisão, cada um dizendo o que faltou
    (CA2);
  - 500 (`ApplicationError`) por zero runs do cohort, seed sem run, run sem
    fold, dois runs no ponto, grade incompleta, nível repetido, `target_date`
    divergente e uma cauda ausente (CA7);
  - estados do intervalo: cauda `undefined`, cauda `error`, unidade ausente,
    outros pares `ok` (CA6); blocos repassados do gold (não publicado,
    `BLOCKED`, sem bloco) e outro candidato → `unavailable` (CA3);
    precedência: `BLOCKED` com candidato diferente → motivo "geração gold
    BLOCKED"; `COMPLETED` de outro candidato e sem `[conformal]` → os dois
    blocos com "geração gold de outro candidato" (CA3);
  - só `dim_run` e `fact_oos_predictions` são lidos (CA13); os membros dos
    Protocols `SilverTableReader` e `ServingGoldReader` são só `read` (CA13);
    dois pedidos iguais → payloads iguais (CA13);
  - `ServingScope` e `ServeInferenceQuery` recusam o inválido.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/inference/application/test_serve_inference.py -q --no-cov
  ```
- **Commit sugerido:** `feat(inference): use case ServeInference sobre as predições gravadas e o gold [7.4/task-02]`

---

### Task 03 — Leitor `ReadServingGold` no evaluation e a aresta declarada

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/read_serving_gold.py`
  - `tests/unit/features/evaluation/test_read_serving_gold.py`
- **Arquivos a modificar:**
  - `.importlinter` — no `bc-independence`, a linha
    `financial_forecasting.features.evaluation.application.use_cases.read_serving_gold -> financial_forecasting.features.inference.application.dtos.serving_gold`
    com comentário (exceção aos itens 2–3 do ADR 0.0.0053; ADR 7.4.0001 item 7)
    e a contagem do cabeçalho do contrato 41 → 42;
  - `tests/architecture/test_import_contracts.py` — caso
    `bc-independence:other-evaluation-module-imports-serving-gold-dtos` em
    `_REAL_VIOLATION_CASES` (outro módulo do evaluation com o mesmo import
    reprova).
- **O que fazer:** o fluxo de §1 "Fluxo do `ReadServingGold`", sobre o
  `GoldGenerationReader` existente.
- **Detalhes técnicos:** leitura só pelos `col_*` e pelos `GOLD_*` (dono único
  das colunas); captura só `GoldManifestNotFoundError`; status antes de
  `table()`.
- **Critério de aceite** (fake `InMemoryGoldGenerationReader`): não publicado;
  `BLOCKED` sem ler tabela; sem `[conformal]`; sem `[h3]`; sem leitura de H3;
  COMPLETED com os dois blocos (correções com `+inf` reconstruído e linha de
  seed nula descartada; shares com `±inf`, com limite finito em status
  não-`ok` e sem valor; `agreeing_families`); VSN `undefined` → bloco
  `available` com linhas não-`ok`; rótulo divergente em reading, em linha `ok`
  de VSN e rótulo presente em linha não-`ok` de VSN → erro; geração corrompida
  → `GoldGenerationCorruptError` propaga; `lint-imports` verde; o caso de
  arquitetura novo reprova a violação injetada (CA5, CA9 parte unitária,
  CA10).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_read_serving_gold.py -q --no-cov
  uv run lint-imports
  uv run pytest tests/architecture/test_import_contracts.py -k "serving-gold" -q --no-cov
  ```
- **Commit sugerido:** `feat(evaluation): leitor do gold servido para a API de inferência [7.4/task-03]`

---

### Task 04 — Contrato `[fake, real]` do `ServingGoldReader`

- **Arquivos a criar:**
  - `tests/contract/features/inference/test_serving_gold_reader_contract.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** suíte parametrizada nas pernas `fake`
  (`InMemoryServingGoldReader` carregado com o `ServingGold` esperado do
  cenário) e `real` (`ReadServingGold` sobre `ParquetGoldStore` em `tmp_path`,
  com a geração do cenário publicada pelo `publish` real). Cenários: não
  publicado; `BLOCKED`; COMPLETED sem `[conformal]` e sem `[h3]`; COMPLETED com
  os dois blocos (unidade `ok`, `undefined`, infinita; participação com limite
  infinito e participação não-`ok` com limite finito; VSN `ok` e VSN
  `undefined`). As duas pernas devolvem exatamente o `ServingGold` esperado.
  Fixture anotada pelo Protocol do inference, checada pelo mypy explícito do
  T1. Só na perna real: geração corrompida (tabela apagada) →
  `ApplicationError`.
- **Detalhes técnicos:** parâmetros dos blocos pelos helpers
  `tests/unit/features/evaluation/_conformal_parameters.py` e
  `_h3_parameters.py`; manifesto e `_generation()` como na suíte do
  `GoldGenerationReader` (geração publicada e relida idêntica — medido no
  Checkpoint B).
- **Critério de aceite:** as duas pernas devolvem o mesmo `ServingGold` por
  cenário; `check_port_coverage.py` e `check_fake_parity.py` verdes; mypy
  strict verde no contrato e no fake (CA9).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/inference/test_serving_gold_reader_contract.py -q --no-cov
  uv run mypy --strict tests/contract/features/inference/test_serving_gold_reader_contract.py tests/fakes/features/inference/in_memory_serving_gold_reader.py
  uv run python scripts/check_port_coverage.py
  uv run python scripts/check_fake_parity.py
  ```
- **Commit sugerido:** `test(inference): contrato [fake, real] do ServingGoldReader [7.4/task-04]`

---

### Task 05 — Handler global de `ApplicationError`

- **Arquivos a criar:**
  - `tests/unit/shared/infrastructure/http/__init__.py`
  - `tests/unit/shared/infrastructure/http/test_error_handlers.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/infrastructure/http/error_handlers.py`
- **O que fazer:** handler `ApplicationError → 500 {"detail": str(exc),
  "type": "application_error"}` em `register_error_handlers`, ao lado dos
  existentes (hierarquias disjuntas; a ordem não importa); docstring do módulo
  atualizada.
- **Critério de aceite** (app FastAPI mínima com rotas que erguem):
  `NotFoundError` → 404 `not_found`; `DomainError` → 422 `domain_error`;
  `ApplicationError` e subclasse → 500 `application_error`; validação de corpo
  → 422 com o corpo padrão do FastAPI (lista) (CA7 e CA8, parte do formato).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/infrastructure/http/test_error_handlers.py -q --no-cov
  ```
- **Commit sugerido:** `feat(http): handler global de ApplicationError com o corpo de erro do projeto [7.4/task-05]`

---

### Task 06 — Rota `POST /inference/run`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/adapters/in/http/__init__.py`
  - `src/financial_forecasting/features/inference/adapters/in/http/inference_router.py`
  - `src/financial_forecasting/features/inference/adapters/in/http/schemas/__init__.py`
  - `src/financial_forecasting/features/inference/adapters/in/http/schemas/inference_schemas.py`
  - `tests/integration/features/inference/adapters/__init__.py`,
    `tests/integration/features/inference/adapters/in_/__init__.py`,
    `tests/integration/features/inference/adapters/in_/http/__init__.py`
  - `tests/integration/features/inference/adapters/in_/http/test_inference_router.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** schemas Pydantic de pedido (`InferenceRunRequest` com
  `to_query()`) e resposta (`InferenceRunResponse.from_payload(payload)`, que
  aplica a regra de (valor, flag) de §1); router com `get_serve_inference`
  padrão (ergue `ServingNotConfiguredError`) e o endpoint fino; docstrings dos
  arquivos em `in/` com o aviso da keyword (LAYOUT §8); descrição da rota diz
  que serve o gravado, sem rodar o modelo, e que intervalos podem vir
  cruzados.
- **Detalhes técnicos:** validação de pedido no schema (data ISO, horizontes
  > 0, listas não vazias e sem repetição) → 422 padrão do FastAPI; nenhum
  `try/except` no router (I10). São 8 arquivos, 5 deles `__init__.py` de
  pacote (`src/…/http/`, `schemas/` e os três de `tests/…/adapters/in_/http/`):
  um só módulo de código novo, o router com os seus schemas.
- **Critério de aceite** (app mínima com `register_error_handlers`, o router e
  `dependency_overrides` para um use case de teste): pedido vira
  `ServeInferenceQuery` com `date` e tuplas; 422 nos quatro inválidos com corpo
  de lista; 404 e 500 com `{detail, type}`; sem override → 500 "serviço de
  inferência sem cohort configurado"; resposta com `schema_version = 1`; os
  pares (valor, flag) de §1 — infinito, sem valor, finito e finito em
  participação não-`ok` — no conformal e na participação, e nenhum outro (CA4,
  CA8, CA11 parte).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/integration/features/inference/adapters/in_/http/test_inference_router.py -q --no-cov
  ```
- **Commit sugerido:** `feat(inference): rota POST /inference/run sobre o ServeInference [7.4/task-06]`

---

### Task 07 — Wiring da API e e2e pela app completa

- **Arquivos a criar:**
  - `tests/e2e/features/inference/__init__.py`
  - `tests/e2e/features/inference/test_inference_api_e2e.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/infrastructure/config/settings.py` —
    `serving_cohort_file: Path | None = None` (env `SERVING_COHORT_FILE`);
  - `src/financial_forecasting/composition_root.py` — campo
    `serve_inference_for` e a fábrica (leitor do cohort por `importlib`;
    `CohortNotFrozenError` se não congelado; `CohortHash` + `cohort_id`;
    `ServingScope` com `MODEL_VERSION`; `ServeInference(scope,
    silver=analytics_repository, gold=ReadServingGold(gold_reader=gold_store))`)
    e `register_http_routes` (§1 "Composition root");
  - `src/financial_forecasting/shared/infrastructure/http/app.py` —
    `create_app(settings: Settings | None = None)`; `_register_feature_routers`
    delega a `register_http_routes`; com cohort configurado o use case é
    montado uma vez, na subida;
  - `pyproject.toml` — sai `"*/shared/infrastructure/http/*"` do `omit` da
    cobertura (concept D14; ADR 1.1.0001).
- **O que fazer:** o e2e sobe a app com `Settings(data_root=tmp_path,
  serving_cohort_file=config/cohorts/aapl_confirmatory.toml)` (o `cohort_id` é
  derivado pelo mesmo leitor + hasher; **nenhum dado real é lido**), grava em
  `tmp_path` um silver sintético (`dim_run` + `fact_oos_predictions` com as 10
  seeds, 2 folds, teste e calib, e um `gbm_quantile` no mesmo cohort) e publica
  a geração gold pelo `ParquetGoldStore`.
- **Critério de aceite:** CA1 (grade e intervalos literais, sobreposição); CA2
  (404 por ativo, horizonte, seed, data fora, só calib, h+7 das últimas
  sessões; só h+1 → 200); CA3 (sem gold; `BLOCKED`; outro candidato); CA4
  (JSON com os pares (valor, flag)); CA5 (rótulos = constantes; nenhum literal
  deles sob `src/financial_forecasting/features/inference/` — busca no teste);
  CA7 (geração corrompida → 500); CA11 (sem cohort → 500; arquivo ilegível e
  cohort não congelado → `create_app` falha); CA13 (dois pedidos iguais →
  corpos iguais); a CLI segue verde; `shared/infrastructure/http/` com
  cobertura ≥ 90% por arquivo.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/e2e/features/inference/test_inference_api_e2e.py tests/unit/shared/test_composition_root.py tests/unit/shared/infrastructure/config/test_settings.py tests/unit/shared/infrastructure/http/ tests/unit/test_cli.py -q --no-cov
  uv run pytest tests/e2e/features/inference/ tests/unit/shared/infrastructure/http/ -q --cov=src/financial_forecasting/shared/infrastructure/http --cov-report=term-missing
  uv run python -c "from financial_forecasting.main import app; r = sorted(x.path for x in app.routes if 'inference' in x.path); assert r == ['/inference/run'], r"
  ```
- **Commit sugerido:** `feat(inference): liga a API de inferência na app e no composition root [7.4/task-07]`

---

### Task 08 — Gate: a API não carrega a pilha de deep learning

- **Arquivos a criar:**
  - `tests/e2e/features/inference/test_inference_api_no_deep_learning.py`
- **Arquivos a modificar:**
  - `.importlinter` — `inference-no-torch-leak` ganha
    `financial_forecasting.features.inference.adapters.in.http` em
    `source_modules` (com comentário: ADR 7.4.0001 item 1);
  - `tests/architecture/test_import_contracts.py` — caso de violação do router
    importando `torch`.
- **O que fazer:** teste em subprocesso (`sys.executable -c …`) que monta a
  app com o cenário mínimo do e2e, atende um pedido e afirma que `torch`,
  `lightning` e `pytorch_forecasting` não estão em `sys.modules`.
- **Critério de aceite:** CA10 (contrato estendido com caso; subprocesso
  verde).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/e2e/features/inference/test_inference_api_no_deep_learning.py -q --no-cov
  uv run lint-imports
  uv run pytest tests/architecture/test_import_contracts.py -k "torch" -q --no-cov
  ```
- **Commit sugerido:** `test(architecture): a API de inferência não carrega torch [7.4/task-08]`

---

### Task 09 — LAYOUT §7 e nota no ADR 0.0.0053

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `docs/LAYOUT.md` — §7: a aresta `read_serving_gold →
    inference.application.dtos.serving_gold` entre as declaradas (contagem
    41 → 42), a doutrina com a exceção (DTO do port-out do consumidor quando
    a direção do 0.0.0053 fecharia ciclo) e o perímetro do
    `inference-no-torch-leak` com o router; §6: o registro dos routers de
    feature passa pela composition root;
  - `docs/adr/0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md`
    — nota de emenda apontando para o ADR 7.4.0001 item 7.
- **Critério de aceite:** a contagem do LAYOUT bate com as linhas do
  `ignore_imports`; ponteiros e bounded context verdes (CA14).
- **Comando de verificação:**
  ```bash
  awk '/^\[importlinter:contract:bc-independence\]/{f=1;next}/^\[/{f=0}f' .importlinter | grep -v '^\s*#' | grep -c ' -> '   # esperado: 42
  uv run python scripts/check_docs_pointers.py && uv run python scripts/check_adr_bounded_context.py
  ```
- **Commit sugerido:** `docs(architecture): aresta evaluation → inference no LAYOUT §7 e no ADR 0.0.0053 [7.4/task-09]`

---

### Task 10 — Fontes novas, errata do localizador e issues de follow-up

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `docs/overview.md` — §10, linha da API de inferência (RFC 8259, RFC 9110,
    RFC 9457, RFC 10008, AIP-180/AIP-185, JSON:API v1.1, documentação do
    FastAPI);
  - `docs/adr/7_1_0001-checkpoint-prediction-supplied-by-modeling-through-consumer-port.md`
    e `docs/stages/7.1-inference-engine/concept.md` — errata "ch. 6" → cap. 7
    de Huyen 2022.
- **O que fazer:** além dos docs, abrir duas issues e registrar os números na
  §7: (a) o job agendado (concept D10), com `## Incerteza`, condição de disparo
  e a restrição da janela de publicação do gold (ADR 6.4.0005); (b) os
  contratos da 7.1 e da 7.3 que afirmam prova por mypy sem que o mypy rode
  sobre `tests/` (achado B3 do Checkpoint B).
- **Critério de aceite:** CA14; issues abertas com `### BC / camada` e
  `### Depende de`.
- **Comando de verificação:**
  ```bash
  uv run python scripts/check_docs_pointers.py
  ```
- **Commit sugerido:** `docs(references): fontes da API de inferência e errata do localizador de Huyen [7.4/task-10]`

## 3. Gate de saída da Stage

### Verificações automatizadas

```bash
make check
uv run pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing -q   # cobertura por arquivo tocado ≥ 90%
uv run python scripts/check_technical_postexec.py docs/stages/7.4-inference-api/technical.md
```

### Verificações funcionais

- [ ] **Execução real (CA12)** no checkout da worktree, com o dado do cohort
      real (só leitura):
      ```bash
      DATA_ROOT=/home/marcelo/Code/financial-forecasting/data/cohorts/aapl \
      SERVING_COHORT_FILE=config/cohorts/aapl_confirmatory.toml \
      uv run uvicorn financial_forecasting.main:app --port 8077 &
      curl -s -w '\n%{http_code} %{time_total}s\n' -X POST localhost:8077/inference/run \
        -H 'content-type: application/json' -d '{"asset":"AAPL","decision_date":"2024-03-15"}'
      ```
      Esperado: 200; 2 horizontes × 10 seeds; quantis iguais ao
      `value_guardrail` gravado para essa data (conferido por DuckDB, só
      colunas de predição); `gold.published = false`,
      `gold.generation_status = null`, `explainability.status = "unavailable"`
      e `conformal.status = "unavailable"` em cada membro, com motivo começando
      por "gold não publicado"; rótulos presentes. Mais: uma data fora do teste
      → 404 com a mensagem; uma das 6 últimas sessões só com h+1 → 200.
- [ ] **Tempo de um pedido com gold de tamanho real (D15):** script no
      scratchpad que monta o `ServeInference` com o `ParquetAnalyticsRepository`
      sobre o silver real e o `ReadServingGold` sobre um `ParquetGoldStore` em
      diretório temporário, onde publica uma geração sintética COMPLETED com as
      19 tabelas e as contagens do cohort (correções: 6 folds × 10 seeds × 2
      horizontes × 3 pares × 2 variantes × 2 caudas; diferenciais de perda e
      demais tabelas com contagens da ordem do cohort, reusando os helpers da
      Task 04), e cronometra um pedido inteiro (leitura do silver + do gold +
      montagem). Limiar: o tempo **total** < 5 s; acima disso, Task extra de
      cache por manifesto (D15).
- [ ] As duas medições coladas como `[measurement]` em §7.

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage 7.4: complete` aplicado
- [ ] Branch mergeado em `develop`
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e
      `last_reviewed_at` no mesmo merge (ou em PR de docs imediato)
- [ ] ADRs novos (se houve) em `status: accepted`
- [ ] Runbooks operacionais criados se aplicável
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
      (se precisa, abrir TODO ou nova Stage de correção)

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 06 ─► 07 ─► 08
 └──► 03 ─► 04 ──┘
05 ─────────► 06
09, 10 (docs) depois de 08
```

A 03 depende só da 01 (DTOs do port); a 06 depende da 02 (DTOs do payload) e
da 05 (handler, nos testes de 404/500); a 07 depende de 03 e 06.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `check_port_coverage.py` não reconhecer o `ReadServingGold` | anotar o port e o use case com os mesmos nomes (`ServingGold`), nunca entrada no baseline (regra do script); simulado verde no Checkpoint B |
| Montar uma geração COMPLETED válida exigir peças demais | reusar o manifesto e `_generation()` da suíte do `GoldGenerationReader` e os helpers de parâmetros (publicação e releitura medidas no Checkpoint B) |
| Tirar o `omit` da cobertura derrubar o `fail_under` global por causa de `middlewares.py` | o `create_app` do e2e exercita os três arquivos; se ainda faltar, teste dedicado na própria Task 07 |
| Tempo total do pedido ≥ 5 s | Task extra: cache da geração por manifesto no leitor (D15), com teste |
| `create_app` com cohort configurado ficar lento na subida | aceitável (uma vez por processo); medir e registrar |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md)
- [`../../roadmap.md`](../../roadmap.md)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs desta Stage: [`../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md), [`../../adr/7_4_0002-inference-payload-contract-and-http-errors.md`](../../adr/7_4_0002-inference-payload-contract-and-http-errors.md)
- Skills aplicáveis: `fastapi-thin-adapter`, `hex-arch-python`, `dmls-ch06-deployment-and-inference-decisions`, `task-ordering-hex`, `pytest-with-fakes`, `composition-root`
- Docs externos: FastAPI "Handling Errors" e "Testing Dependencies with Overrides"; RFC 8259 §6

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
> **recomendada** + razão (via `AskUserQuestion` ou equivalente).
> Apenas após a decisão, registre a entrada abaixo. Na dúvida sobre
> se algo é "pequeno o suficiente para decidir sozinho", **pergunte**.

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
  Inclui pergunta, opções, decisão, razão.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original; corpo
  diz o que mudou e por que ficou abaixo do threshold de perguntar.
- `[measurement]` — evidência que o plano manda colar aqui (tempo do
  ponta a ponta, saída de mutação obrigatória, prova manual, execução
  real, auditoria de testes), sem decisão nem desvio. Corpo:
  **Contexto:** que critério/Task pede a evidência; **Medição:** comando,
  ambiente e saída bruta; **Razão:** o que a evidência prova.

Vocabulário fechado (CONVENTIONS §3.4): `decision` (ou `decision:E` /
`decision:C`, skill `evidence-resolution` §5), `finding`, `deviation`,
`measurement`. Outra tag no cabeçalho de entrada é recusada por
`scripts/check_technical_postexec.py`.

### 2026-10-22 — [decision] pontos do Checkpoint C — Claude (sessão Windows)
**Contexto:** o plano de gates (§1) fixa só o `make check` de saída e não diz onde
fecham os blocos do Checkpoint C. O PROMPT de sessão única pede um a cada 2–3
Tasks; o orquestrador da sessão Windows autorizou blocos de 3–4 Tasks, registrados
aqui antes de seguir.
**Pergunta:** onde fecham os blocos do Checkpoint C?
**Opções:**
- A — blocos fixos de 3 Tasks (01–03, 04–06, 07–09, 10).
- B — blocos pelas fronteiras do plano: C1 = 01–04 (DTOs, use case, leitor real e
  contrato: o port fecha com o `check_port_coverage.py` verde), C2 = 05–07
  (handler, rota e wiring da app), C3 = 08–10 (gate de torch e docs) ✅ recomendada
**Decisão:** B
**Razão:** cada bloco termina num estado que se revisa inteiro. O port nasce na 01 e
só tem real e contrato na 04 (§1 "Estratégia"), então cortar no meio deixaria o
revisor com um port sem real. A 05–07 é a superfície HTTP com o seu wiring. O
diff de cada bloco é `git diff <último checkpoint>..HEAD`; o C1 parte de `95204e6b`
(`stage 7.4: technical approved`), porque o WIP da Task 01 (`ef08dd9d`) já traz
código de `src/` e do fake.

### 2026-10-22 — [deviation] Task 03 — `type: ignore` sem uso no teste do leitor — Claude (sessão Windows)
**Contexto:** o mypy strict explícito da Task 04 segue o import do contrato até
`tests/unit/features/evaluation/test_read_serving_gold.py` (da Task 03) e acusou
`Unused "type: ignore" comment` na linha do `**_IDENTITY`. O T1 da Task 03 não roda
mypy sobre `tests/` (o mypy do projeto cobre só `src/`), por isso passou.
**Razão:** correção local de uma linha, sem mudar comportamento nem contrato; vai num
commit `test(evaluation): … [7.4/task-03-fix]` antes da Task 04, para o mypy strict
da Task 04 fechar verde sobre os arquivos que o contrato importa.

### 2026-10-22 — [deviation] Task 04 — fábricas da geração vindas do teste da Task 03 — Claude (sessão Windows)
**Contexto:** a Task 04 pede manifesto e `_generation()` "como na suíte do
`GoldGenerationReader`" e os parâmetros pelos helpers `_conformal_parameters.py` e
`_h3_parameters.py`. A Task 03 já escreveu, em `test_read_serving_gold.py`, a fábrica
`generation()` (manifesto + toda tabela de `GOLD_SCHEMAS`, sobre esses dois helpers) e
as linhas das quatro tabelas servidas com as colunas dos builders.
**Razão:** o contrato importa `generation`, `complete_rows` e `vsn_row` desse módulo
em vez de copiar ~150 linhas, para que as duas suítes leiam a mesma geração; nenhum
arquivo novo (a lista fechada da Task 04 continua só com o contrato). Os `ServingGold`
esperados do contrato são literais próprios, não derivados do teste unitário. O
parâmetro sem `[conformal]`/`[h3]` sai por `dataclasses.replace` do padrão, sem
importar nome privado.

### 2026-10-22 — [deviation] Checkpoint C1-1 — `H3ShareRecord.side` é `int | None` — Claude (sessão Windows)
**Contexto:** o §1 "Contratos" declara `H3ShareRecord.side: str | None`, e os testes das
Tasks 01–04 e 06 usavam `"two_sided"`. No gold real o campo é o sinal de Δ̂_f:
`FamilyShare.side: int | None` em {-1, 0, +1} (`family_contribution.py`), gravado como
inteiro pelo `H3SharesGoldBuilder`. Com os builders reais, o leitor da Task 03 erguia
`GoldGenerationCorruptError: gold_h3_shares.side: expected str, got int 1` (blocker do
Checkpoint C1, reproduzido pela sonda do revisor).
**Razão:** correção do contrato, não mudança de desenho. Vale a forma
`H3ShareRecord.side: int | None` com valor em {-1, 0, +1} (o DTO recusa outro valor e
`bool`), lida por `col_int_or_none`. O schema HTTP da Task 06 passa a `side: int | None`
no mesmo payload de schema 1, que ainda não foi publicado. Commits: `task-01-fix` (DTO),
`task-03-fix` (leitor) e `task-06-fix` (schema HTTP).

### 2026-10-22 — [decision] Checkpoint C1-5 — run do candidato com seed nula no `dim_run` — Claude (sessão Windows)
**Contexto:** o fluxo do §1 trata como `ApplicationError` o run do candidato sem `fold`,
mas não diz nada sobre o run com `seed` nula. A Task 02 o ignorava em silêncio, e o
Checkpoint C1 apontou o mutante `si-seed-none-skip` como sobrevivente.
**Pergunta:** run do candidato com `seed` nula é ignorado ou é silver inconsistente?
**Opções:**
- A — ignorar (o escopo lista as seeds; o run nunca seria servido).
- B — `ApplicationError`, como o run sem `fold` ✅ recomendada
**Decisão:** B (fixada pelo orquestrador na disposição do C1-5).
**Razão:** o candidato TFT treina com seed por unidade, então um run dele sem seed é
defeito do silver, não falta de dado do pedido (concept I3: silver inconsistente → 500).
Ignorá-lo esconderia o defeito. O teste `run-without-seed` mata o mutante.

### 2026-10-22 — [deviation] Checkpoint C1-2 — fábricas em `_serving_gold_rows.py` e cenário dos builders reais — Claude (sessão Windows)
**Contexto:** o contrato da Task 04 só via linhas escritas à mão, e foi assim que o
blocker C1-1 (`side` texto × inteiro) passou. Além disso, as fábricas eram importadas de
`test_read_serving_gold.py` (o `[deviation]` da Task 04) e tinham dois valores que o
builder real nunca grava: o método `"ablation"` (o builder grava `"loco"`) e uma unidade
sem seed com medidas e status `ok` (o builder grava `undefined` sem medidas).
**Razão:** `generation`, `complete_rows`, `correction_row`, `share_row`, `reading_row`,
`vsn_row` e `refresh_parameters` passam para
`tests/unit/features/evaluation/_serving_gold_rows.py` (arquivo novo, pedido pelo
revisor; segue o precedente de `_conformal_parameters.py`), com os valores corrigidos.
Isso substitui o `[deviation]` da Task 04. O contrato ganha
`test_real_reads_what_the_real_builders_write`: os quatro builders servidos sobre
`tests/contract/features/evaluation/_gold_inputs.completed_inputs()`, e uma variante com
VSN `undefined` (via `dataclasses.replace`), publicados pelo `ParquetGoldStore` real. O
teste afirma os tipos, `-inf`/`+inf`, `side` inteiro e `n = 10` nas unidades `ok`.

### 2026-10-22 — [finding] mypy strict do contrato alcança `_gold_inputs.py` da 7.3 — Claude (sessão Windows)
**Contexto:** com o import de `completed_inputs`, o
`mypy --strict tests/contract/features/inference/test_serving_gold_reader_contract.py …`
da Task 04 segue até `tests/contract/features/evaluation/_gold_inputs.py:231` e acusa
`no-any-return` (`samples_of`, em `dd16c1e8`, Stage 7.3), num arquivo fora da lista desta
Stage. Os arquivos da 7.4 passam limpos com
`mypy --strict --follow-imports=silent <contrato> <fake> _serving_gold_rows.py test_read_serving_gold.py`.
**Direção sugerida:** entra na issue de follow-up da Task 10 (b), "contratos da 7.1/7.3
afirmam prova por mypy que não roda sobre `tests/`". A correção de uma linha
(anotar/converter o retorno) vai com ela. Stage candidata: issue #203 (correção pontual),
irmã da #204 (mypy sobre `tests/`).

### 2026-10-22 — [deviation] Task 07 — conferência das rotas pelo OpenAPI e fábrica fora do `wire_dependencies` — Claude (sessão Windows)
**Contexto:** (1) o terceiro comando de verificação da Task 07 (`sorted(x.path for x in
app.routes if 'inference' in x.path)`) quebra no FastAPI 0.138.1:
`AttributeError: '_IncludedRouter' object has no attribute 'path'`, porque o router
incluído fica em `app.routes` como `_IncludedRouter`, sem `path`. (2) O
`wire_dependencies` estava no limite de 50 comandos do ruff (`PLR0915`), e a fábrica
aninhada o levava a 56.
**Razão:** (1) a conferência equivalente lê os caminhos do esquema que a app publica:
`sorted(p for p in app.openapi()["paths"] if "inference" in p) == ["/inference/run"]`
(saída `['/inference/run']`), e virou o caso `test_the_app_exposes_one_inference_route`
do e2e. (2) a fábrica mora em `serve_inference_factory(*, hasher, silver, gold_store)`, no
nível do módulo da composition root (o precedente é `ablation_spec_loader`). O
`ApplicationDependencies.serve_inference_for` é preenchido com ela, sem mudar o contrato
do §1.

### 2026-10-22 — [deviation] Task 10 — issues de follow-up abertas (três em vez de duas) — Claude (sessão Windows)
**Contexto:** a Task 10 prevê duas issues: (a) o job agendado (concept D10) e (b) os
contratos da 7.1/7.3 que afirmam prova por mypy sem que o mypy rode sobre `tests/`
(achado B3 do Checkpoint B). O `[finding]` da Task 04 (mypy strict alcança
`_gold_inputs.py:231`) pedia uma terceira, e o orquestrador mandou abri-la. Antes de
abrir, busquei duplicatas no GitHub (`agendado`, `scheduler`, `mypy`, `_gold_inputs`,
`no-any-return`, abertas e fechadas) e não achei nenhuma.
**Razão:** as três foram abertas com `### BC / camada` e `### Depende de`, e com
referência cruzada:
- **#202:** `feat(inference)`, o job agendado que mantém um cohort de produção servível.
  Traz `## Incerteza` (forma do cohort, retreino, escopo do gold, onde roda), a
  condição de disparo e a restrição da janela de publicação do ADR 6.4.0005.
- **#204:** `chore(tooling)`, os contratos da 7.1/7.3 que afirmam prova por mypy. A
  medição de 2026-10-22 achou 3 `unused-ignore` nos próprios arquivos e 12 erros em 5
  arquivos seguindo os imports.
- **#203:** `chore(evaluation)`, o `no-any-return` em `samples_of`. O `[finding]` da
  Task 04 aponta para ela.

Os três números foram comentados na #201.

### 2026-10-22 — [deviation] Checkpoint C2-4 — o provedor do use case é trocado na composition root, não no `app.py` — Claude (sessão Windows)
**Contexto:** o concept 7.4 D8 ("provedor trocado no `app.py`") e o ADR 7.4.0002 item 6
("replaced in `app.py` through `dependency_overrides`") localizam a troca do provedor no
`app.py`. O §1 "Composition root" deste technical, e a Task 07, a puseram em
`composition_root.register_http_routes`, que o `create_app` chama.
**Razão:** a decisão é a mesma: o port-in é o próprio use case, injetado por `Depends`,
com o provedor trocado por `dependency_overrides`. Só muda o arquivo em que a troca
acontece, porque o `shared/http` só pode importar a composition root (contrato
`shared-no-features`; LAYOUT §6). O ADR 7.4.0002 ganhou um banner de errata append-only
(CONVENTIONS, regra do ADR `accepted`), sem editar o corpo. O concept 7.4 está `done` e
não foi editado: esta entrada é o registro para ele.

### 2026-10-22 — [decision] Checkpoint C2-5 — o e2e importa as fábricas de `tests/unit/` — Claude (sessão Windows)
**Contexto:** `tests/e2e/features/inference/test_inference_api_e2e.py` importa
`complete_rows`, `correction_row` e `generation` de
`tests.unit.features.evaluation._serving_gold_rows`. O revisor do C2 apontou o import
de uma suíte de outro nível (e2e → unit).
**Pergunta:** mover as fábricas para um lugar neutro ou manter o import?
**Opções:**
- A — mover para um pacote comum de fixtures de teste (refactor de três suítes).
- B — manter: o módulo `_` é helper, não suíte, e há precedente ✅ recomendada
**Decisão:** B (o orquestrador decidiu manter, sem refactor).
**Razão:** contratos e e2e do projeto já importam helpers de `tests/unit/` (por exemplo,
os contratos do `evaluation` usam `tests/unit/features/evaluation/_conformal_parameters.py`
e `_h3_parameters.py`). Uma fonte única das linhas do gold servido para o unit, o contrato
e o e2e é o que mantém as três suítes lendo a mesma geração.

### 2026-10-22 — [finding] Checkpoint C3-4 — as skills `dmls-chNN` numeram os capítulos com 1 a menos que o livro — Claude (sessão Windows)
**Contexto:** a errata de localizador da Task 10 ("ch. 6" → cap. 7) tem causa: o ADR
7.1.0001 e o concept 7.1 tiraram o número do capítulo do nome da skill
`dmls-ch06-deployment-and-inference-decisions`. No sumário de Huyen (2022), *Designing
Machine Learning Systems* (O'Reilly), os capítulos são: 3 "Data Engineering
Fundamentals", 4 "Training Data", 5 "Feature Engineering", 6 "Model Development and
Offline Evaluation", 7 "Model Deployment and Prediction Service". Conferi o assunto de
cada skill: `ch02` (infraestrutura de dados) é o cap. 3, `ch03` (dados de treino) o 4,
`ch04` (features) o 5, `ch05` (desenvolvimento e avaliação) o 6 e `ch06` (deployment e
inferência) o 7.
**Direção sugerida:** a linha "Chapter N" de
`.claude/skills/dmls-ch0{2..6}-*/references/chapter-content.md` foi corrigida nesta Stage
(commit `docs(skills)`), sem renomear as skills, porque os nomes são referenciados em
`skills_hint`, ADRs e concepts. Ficaram como estão: os títulos `# DMLS Ch. N`, as
referências cruzadas internas entre skills ("Chapter 2 left off…", na numeração das
skills) e a `ch01`, que não foi conferida (pode cobrir os caps. 1–2). Quem citar o livro a
partir de uma skill confere o capítulo pela linha "Chapter N". Renomear as skills, se um
dia valer a pena, é issue própria de tooling; não há Stage candidata.

### 2026-10-22 — [measurement] Checkpoint C3-7 — pacotes do handoff Linux → Windows conferidos e arquivados — Claude (sessão Windows)
**Contexto:** o `HANDOFF-windows.md` é apagado no commit final da Stage, e a pendência
"conferir no Windows antes de descartar o Linux" (§6/§7 dele) precisa ficar registrada
aqui.
**Medição:** os três pacotes estão em
`C:\Users\Marcelo\Documents\Code\financial-forecasting\data\backups\handoff-7.4-linux\`:

| pacote | tamanho | sha256 |
|---|---|---|
| `ff-data-7.4.tar.gz` (dados do cohort) | 141 669 585 B | `91d243f5e182167342fc0f4b1497531f054cb2ff5ac1ec9ec59848b2114889ff` |
| `ff-checkpoints-tft.tar` (checkpoints) | 8 430 243 840 B | `271e7cb808669ac36a8d3dfffa0b5b2831f4b5304a49ddfc71a6040aa540e961` |
| `ff-extra.tar.gz` (extras) | 27 858 845 B | `1ad257d99abb0ea2360846d18c6dc866e2b75618010b50ee3d6e3f4644c68525` |

O orquestrador conferiu os três com `sha256sum -c` em 2026-10-22 (OK) e os extraiu no
checkout principal do Windows: `data/cohorts/aapl/{bronze,inference,processed,raw,silver}`,
`artifacts/tft` e `artifacts/cohorts`. A sessão executora repetiu a conferência no mesmo
dia (`sha256sum -c ff-data-7.4.sha ff-extra.sha ff-checkpoints-tft.sha` →
`ff-data-7.4.tar.gz: OK`, `ff-extra.tar.gz: OK`, `ff-checkpoints-tft.tar: OK`) e contou
o que foi extraído, só por listagem de arquivos (nenhuma métrica):

- `artifacts/tft`: **300** diretórios de run e **306** `.ckpt`, os mesmos do tar
  (`tar -tf`: 300 diretórios, 306 `.ckpt`, 607 entradas). Os 300 são exatamente os 300
  `run_id` do ledger `artifacts/cohorts/aapl_ablation-r0-8a2d1de2dd8c/progress.json`.
- **Divergência com o handoff:** o §6 dele diz que o tar tem "360 dirs = 60 do
  confirmatório + 300 da ablação". O tar medido não tem nenhum dos 60 `run_id` TFT do
  ledger `aapl_confirmatory-r0-665f45d9169a` (0 de 60 em `artifacts/tft` e 0 no `tar -tf`).
  Os 60 estão, todos com `.ckpt`, em
  `data/backups/tft-pre-7.4-20261022-030008/` (60 diretórios, 60 `.ckpt`), a cópia de
  `artifacts/tft` que existia no Windows antes da extração.
- Portanto o tar é a única cópia dos **300 checkpoints da ablação**. Os **60 do
  confirmatório**, que a verificação `infer` da 8.1 usa, estão só no backup
  `tft-pre-7.4-…` e hoje **não** estão sob `ARTIFACTS_ROOT=artifacts`.
**Razão:** fecha a pendência "conferir no Windows" para os três sha256. Deixa
registrado, antes de o handoff sumir, onde mora cada conjunto de checkpoints. A 8.1 tem
de devolver os 60 do backup a `artifacts/tft` (ou apontar o `ARTIFACTS_ROOT` para ele)
antes do `infer`. A 7.4 não usa checkpoints.

### 2026-10-22 — [deviation] Checkpoint C3-8 — CA12 e D15 pelo caminho Windows/Docker — Claude (sessão Windows)
**Contexto:** o §3 escreve as duas verificações funcionais com caminhos do Linux
(`DATA_ROOT=/home/marcelo/…`, `uvicorn … &` + `curl` no host). Nesta máquina tudo roda
por Docker (o venv do host está quebrado), e o dado real foi extraído no checkout
principal do Windows.
**Razão:** as duas rodaram num `docker run` avulso (`--cpus 3 --memory 6g`, imagem
`financial_forecasting-app:dev`, volume `financial-forecasting_ff74-venv`), com a
worktree em `/app` e `PYTHONPATH=/app/src:/app`. O dado real foi montado só leitura:
`-v C:/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl:/data/aapl:ro`,
com `DATA_ROOT=/data/aapl` (o `data/cohorts/aapl` do checkout principal). O
`curl` foi trocado por `httpx` dentro do mesmo container, e o `uvicorn` sobe como
subprocesso do script. A conferência dos quantis lê o Parquet por DuckDB, só colunas de
predição (`run_id`, `seed`, `fold`, `split`, `horizon`, `timestamp_utc`,
`quantile_level`, `value_guardrail`). Nenhuma métrica foi calculada, e o realizado não
foi lido (cegamento). Scripts: `ca12.py` e `d15.py` no scratchpad da sessão
(`…\scratchpad\verify\`).

### 2026-10-22 — [measurement] CA12 — a API real sobre o cohort real — Claude (sessão Windows)
**Contexto:** §3, "Execução real (CA12)": a app sobe com o cohort real e um pedido a uma
data de teste devolve a grade gravada, com os blocos do gold indisponíveis.
**Medição:** `python /verify/ca12.py /data/aapl` (container acima; `uvicorn
financial_forecasting.main:app --port 8077` com `DATA_ROOT=/data/aapl` e
`SERVING_COHORT_FILE=config/cohorts/aapl_confirmatory.toml`). Saída bruta, truncada:
```
[startup] 14.04s
[2024-03-15] status=200 time=1.456s
horizons: [1, 7]
seeds per horizon: [[1..10], [1..10]]
target_dates: ['2024-03-18', '2024-03-26']
grade == value_guardrail gravado (DuckDB): 20/20 membros
gold: {"published": false, "generation_status": null, "preregistration_ref": null, "candidate": null, "finished_at": null}
conformal por membro: {('unavailable', 'gold não publicado para o cohort aapl_confirmatory-r0-665f45d9169a')}
explainability: unavailable | gold não publicado para o cohort aapl_confirmatory-r0-665f45d9169a
rótulos: {'cobertura empírica (não garantida)'} | descritiva (sem claim causal) | horizonte-invariante; descreve quanto o modelo usa cada família
schema_version: 1
[2026-01-05 {}] status=404 time=0.290s -> não há dados para o pedido solicitado: decisão 2026-01-05 sem linha de teste para (seed 1, h+1), …, (seed 10, h+7)
[2025-12-30 {}] status=404 time=0.848s -> não há dados para o pedido solicitado: decisão 2025-12-30 sem linha de teste para (seed 1, h+7), …, (seed 10, h+7)
[2025-12-30 {'horizons': [1]}] status=200 time=0.849s -> 1 horizonte(s), 10 membros
```
**Razão:** prova o CA12 pelo entrypoint real.
- 200 com 2 horizontes × 10 seeds; os 20 membros são iguais, valor a valor e com o
  mesmo `run_id`, ao `value_guardrail` gravado, conferido de forma independente do
  adapter.
- Os blocos vêm `unavailable` com "gold não publicado" e os rótulos presentes.
- Uma data fora do teste dá 404 com a frase. A última sessão (2025-12-30) dá 404 no
  pedido padrão, por faltar h+7, e 200 pedindo só h+1.
- O pedido leva 1,46 s, abaixo dos 5 s. A subida da app leva 14 s, uma vez por processo
  (§5, aceitável).

### 2026-10-22 — [measurement] D15 — tempo de um pedido com gold do tamanho do real — Claude (sessão Windows)
**Contexto:** §3, "Tempo de um pedido com gold de tamanho real (D15)": acima de 5 s no
total, entra a Task extra de cache por manifesto.
**Medição:** `python /verify/d15.py /data/aapl` (container acima). O `ServeInference`
vem de `serve_inference_factory` sobre o `ParquetAnalyticsRepository` do silver real
(`:ro`) e o `ReadServingGold` sobre um `ParquetGoldStore` em diretório temporário, com
uma geração COMPLETED sintética de 19 tabelas. Saída bruta:
```
[gold sintético] 19 tabelas, 93123 linhas, publicado em 1.20s
   {'quality_checks': 60, 'metrics_by_run': 2640, 'calibration_table': 7920, 'dm_results': 24, 'mcs_results': 28, 'dm_profiles': 6480, 'dm_seed_fraction': 12, 'mcs_block_sensitivity': 28, 'christoffersen_monte_carlo': 5280, 'partial_degeneracy': 2640, 'differential_acf': 840, 'differential_breaks': 42, 'loss_differentials': 63336, 'conformal_corrections': 1440, 'conformal_coverage': 720, 'h3_importance': 1600, 'h3_shares': 8, 'h3_reading': 1, 'h3_vsn': 24}
[pedido 1] total 2.514s | membros=20 intervalos=60 conformal=available explicabilidade=available
[pedido 2] total 2.268s | membros=20 intervalos=60 conformal=available explicabilidade=available
[pedido 3] total 2.453s | membros=20 intervalos=60 conformal=available explicabilidade=available
```
As correções seguem o §3 (6 folds × 10 seeds × 2 horizontes × 3 pares × 2 variantes × 2
caudas = 1440). As demais tabelas têm contagens da ordem do cohort: 7 modelos, 10
seeds, 2 horizontes e ~1508 decisões, com `loss_differentials` = 2 × 21 pares × 1508.
**Razão:** o tempo total de um pedido (silver real + gold inteiro + montagem) fica entre
2,27 s e 2,51 s, abaixo do limiar de 5 s do D15. A Task extra de cache por manifesto
não entra.

### 2026-10-22 — [measurement] adendo ao C3-7 — os 60 checkpoints do confirmatório restaurados em `artifacts/tft` — Claude (sessão Windows)
**Contexto:** o `[measurement]` do C3-7 achou os 60 checkpoints TFT do confirmatório
só no backup `data/backups/tft-pre-7.4-20261022-030008/`, fora do `ARTIFACTS_ROOT`. Em
seguida o orquestrador os copiou do backup para `artifacts/tft` do checkout principal,
sem colisão de diretório.
**Medição:** recontagem por listagem no checkout principal, depois da cópia:
`artifacts/tft` tem **360** diretórios e **366** `.ckpt`. Os 60 `run_id` TFT do ledger
`aapl_confirmatory-r0-665f45d9169a` têm diretório com `.ckpt` lá (60 de 60). O backup
`tft-pre-7.4-20261022-030008/` continua com os 60 diretórios.
**Razão:** o estado final é este:
- O `ff-checkpoints-tft.tar` contém só os 300 checkpoints da ablação, e é a única cópia
  arquivada deles; o "360 no tar" do handoff estava errado.
- Os 60 do confirmatório estão em `artifacts/tft`, que é o `ARTIFACTS_ROOT` da
  verificação `infer` da 8.1, e no backup, como segunda cópia.

### 2026-10-22 — [deviation] Checkpoint C3-9 — #203 e #204 ficam sem label — Claude (sessão Windows)
**Contexto e razão:** o label `chore` não existe no repositório, e o hook
`publish_guard` recusa `gh issue edit` com label fora do fechamento autônomo. Por decisão
do orquestrador, as duas issues ficam sem label, sem contornar o hook. O tipo `chore` está
no título de cada uma.

### 2026-10-22 — [decision] Auditoria de testes TA-5 — o fake do `ServingGoldReader` devolve `unpublished` para partição ausente — Claude (sessão Windows)
**Contexto:** a Task 01 fixou um fake "sem fallback": partição não carregada erguia
`KeyError`. A auditoria de testes apontou que isso viola o invariante do port (gold
ausente é estado, não erro; concept I8), e que um teste com o fake pode passar sem
exercitar o caminho que o real segue.
**Pergunta:** o fake ergue `KeyError` ou devolve `ServingGold.unpublished` para partição
ausente?
**Opções:**
- 1 — devolver `ServingGold.unpublished`, com o motivo e os rótulos do real ✅ recomendada
- 2 — manter o `KeyError`.
**Decisão:** 1 (a decisão da auditoria).
**Razão:** o fake passa a seguir o invariante do port. O contrato ganhou o cenário
"outro cohort → unpublished" nas duas pernas, que prova a forma contra o
`ReadServingGold` real. Os parâmetros trocados em `gold.read` continuam cobertos: o
`calls` do fake é afirmado no contrato e no use case.

### 2026-10-22 — [decision] Auditoria de testes TA-6 — `infinite = true` com `correction` gravada é corrupção — Claude (sessão Windows)
**Contexto:** o builder da 7.2 grava a correção infinita como `correction = null` +
`infinite = true`. O leitor da Task 03 reconstruía `+inf` pela flag e ignorava um valor
gravado junto. O mutante `rg-infinite-ignored-when-value` (preferir o valor gravado à
flag) sobrevivia.
**Pergunta:** flag `true` com valor não nulo: vale a flag, vale o valor ou é corrupção?
**Opções:**
- A — vale a flag (o comportamento anterior, que esconde a contradição).
- B — `GoldGenerationCorruptError` ✅ recomendada
**Decisão:** B (a decisão da auditoria).
**Razão:** a combinação não sai do builder; aceitá-la em silêncio esconderia um gold
adulterado (concept D4: defeito de dado vira 500). Teste
`test_infinite_flag_with_a_stored_correction_is_corruption`. O mutante original perdeu a
âncora com a mudança; a versão contra o código novo (`rg-infinite-ignored-when-value-v2`,
a checagem removida) morre.

<!-- END: post-execution -->
