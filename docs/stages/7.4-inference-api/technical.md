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

<!-- END: post-execution -->
