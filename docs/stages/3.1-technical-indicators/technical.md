---
title: Technical — Stage 3.1 — Indicadores técnicos causais (feature_engineering)
description: Plano de execução da Stage 3.1 — Tasks ordenadas inside-out (domain IndicatorSpec + registry + hash → port IndicatorCalculator + fake → dependência pandas-ta-classic → adapter PandasTaIndicatorCalculator + contract test → fixture-oráculo de fórmula canônica → teste de leakage → feature_engineering como container layered no import-linter), 1 Task = 1 commit, pronto para code assistant
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, technical-indicators, feature-engineering, indicator-spec, indicator-calculator, pandas-ta-classic, rsi-wilder, macd, ema, volatility, candle-range, candle-body, float32, anti-leakage, oracle, registry-hash, import-linter, layered-container]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.1-technical-indicators
stage_title: Indicadores técnicos causais
step_id: 3
step_title: Camada de features (silver)
depends_on: [2.2-market-data-ingestion, 2.4-trading-calendar]
concept_ref: ./concept.md
issue_id: 23
branch: feat/23-3-1-technical-indicators
tasks_count: 9
---

# Technical — Stage 3.1 — Indicadores técnicos causais (`feature_engineering`)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.1/task-NN]`, body em bullets,
>    rodapé `Refs #23`. Escopo ASCII/kebab (sem `/`); use `.` no lugar de `/`
>    para a camada (`feature-engineering.domain`), padrão aceito pelo
>    `check_commit_msg.py` (ver §7 da 2.2).
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[finding]`/`[deviation]`. Esta é corrida autônoma overnight
>    (ADR `0.0.0050`): **não perguntar** — decidir com julgamento, registrar e seguir.
> 7. **Fechamento NÃO é desta sessão.** O commit `stage 3.1: complete` e a marcação
>    `done` no `roadmap.md` são do **orquestrador**, após auditoria independente.
>    Esta sessão entrega concept/technical/código/testes commitados e gates verdes.
>
> **Stage = 1 branch.** Todo o trabalho acontece em
> `feat/23-3-1-technical-indicators`. Não há sub-PRs internos. Fluxo Git completo:
> [`GIT-WORKFLOW.md`](../../GIT-WORKFLOW.md).

## 1. Contexto e estratégia de execução

### Resumo

Esta Stage cria o **segundo bounded context de _feature_** — `feature_engineering`
— em `src/financial_forecasting/features/feature_engineering/`, com as três
camadas hexagonais (`domain` ← `application` ← `adapters/out`), espelhando
`market_data` (2.2). Entrega: o value-object de domínio `IndicatorSpec` (frozen,
**stdlib-only**) + o registry estático `INDICATOR_SPECS` dos **11 indicadores**
(H-2, decisão humana fechada) + o `indicator_registry_hash()` determinístico; o
port-out `IndicatorCalculator` (`Protocol`) que troca `Sequence[Candle]` →
`Sequence[Mapping[str, float]]` **sem vazar pandas/DataFrame**; o
`InMemoryIndicatorCalculator` (fake comportamental); o adapter
`PandasTaIndicatorCalculator` sobre `pandas-ta-classic` (única casa de
`pandas`/`pandas_ta_classic` no BC), validado por **fixture-oráculo de fórmula
canônica** (RSI de Wilder, MACD 12/26/9, EMA `alpha=2/(N+1)`, volatilidade =
std rolling de retornos) e por **teste de leakage** (barras futuras não alteram o
passado); e a prova **inward-only** do BC novo adicionando `feature_engineering`
aos `containers` de `hexagonal-layers` + a `domain-purity` + a
`store-no-storage-leak` no `.importlinter`.

### Estratégia

Ordem **inside-out / TDD** (skill `task-ordering-hex`, default de vertical-slice),
cada Task deixando o build verde:

1. **Domain primeiro** (Task 01): `IndicatorSpec` + `INDICATOR_SPECS` + hash, com
   unit tests no mesmo commit. Sem dependentes acima ainda — domínio puro,
   stdlib-only.
2. **Application** (Tasks 02–03): port `IndicatorCalculator` (`Protocol`)
   **antes** de qualquer adapter (regra dura §4.3 PIPELINE: port antes de adapter
   e **não** misturar criação de port com criação de adapter no mesmo commit); em
   seguida o `InMemoryIndicatorCalculator` (fake comportamental, **não** `Mock`,
   stdlib-only) + teste que prova a satisfação do `Protocol` por um consumidor
   sem `pandas`.
3. **Dependência externa** (Task 04): pinar `pandas-ta-classic` no
   `pyproject.toml` + `uv.lock` + smoke de import — **antes** do adapter, pois o
   adapter (Task 05) faz `import pandas_ta_classic` e seu teste não coleta sem a
   lib (mesma lição da 2.2 §7, em que `yfinance` migrou para a Task do adapter).
4. **Adapter out** (Task 05): `PandasTaIndicatorCalculator` (real) — ordena por
   `timestamp`, calcula os 11, coage `float32`, valida o set completo contra
   `INDICATOR_SPECS` — com contract test parametrizado **paridade fake↔real**
   (mesma postura da 2.1/2.2: `[fake, real]` no mesmo contrato de forma).
5. **Redes de segurança canônicas** (Tasks 06–07): a fixture-**oráculo** de
   fórmula canônica (I3/C6) e o teste de **leakage** (I2/C/anti-leakage) — são as
   duas DoD centrais da Stage e o que corrige os dois gaps do teste fraco do old
   (só checava presença de chave + NaN no warmup). Ficam **depois** do adapter
   porque medem a saída real do adapter contra a fórmula independente.
6. **Gate de arquitetura** (Task 08): adicionar `feature_engineering` aos
   `containers` de `hexagonal-layers`, `...domain` a `domain-purity` e
   `...{application,domain}` a `store-no-storage-leak` — **só aqui**, depois que as
   três camadas físicas existem, a prova inward-only + pureza tem o que medir.
   Quebra intencional (`import pandas` no `domain`) reprova `domain-purity` e é
   revertida.
7. **Gate agregado** (Task 09): `make check` + `make test` + cobertura ≥90% no
   diff.

**Decisão de ordering declarada:** as Tasks 06–07 (oráculo + leakage) vêm
**depois** do adapter (Task 05) — exceção justificada ao "teste no mesmo commit
do código": o contract test de forma já nasce com o adapter (Task 05), mas a
**validação de fórmula canônica** e a **prova de causalidade** são redes
analíticas independentes (ADR `0.0.0021`, postura oráculo) que medem a saída do
adapter real e merecem Task própria, sem misturar com a construção do adapter. A
dependência `pandas-ta-classic` (Task 04) precede o adapter (Task 05) pela lição
de execução da 2.2 (a dep nasce onde o `import` nasce, mantendo cada Task verde).
O `.importlinter` (Task 08) só é tocado **após** as três camadas existirem
fisicamente, pois `type=layers` precisa dos módulos reais para provar a direção.

### Pré-condições

- Stage `2.2-market-data-ingestion` em `done` (entity `Candle` em
  `features/market_data/domain/entities/candle.py` — frozen, stdlib-only,
  `timestamp` tz-aware, campos `open/high/low/close/volume`) — **verificado** no
  repo.
- Stage `2.4-trading-calendar` em `done` (dependência declarada no roadmap; **não
  consumida diretamente** nesta Stage — os indicadores operam barra-a-barra sobre
  a grade existente; concept §3).
- Branch `feat/23-3-1-technical-indicators` em checkout (já criada).
- ADRs `3_1_0001` e `0_0_0024` já presentes em `docs/adr/` — **verificado**; esta
  Stage só confere que estão `status: accepted` (concept previa "criar"; o
  as-built é "já existem", ver §7 [deviation]).

### Premissas técnicas

- Python 3.12, `uv`, `mypy --strict`, `ruff`, `pytest`.
- `features/feature_engineering/` está **vazio** hoje; é o **segundo** feature
  container — o `.importlinter` (linha 42 verbatim) e o ADR `1.3.0001` já preveem
  "cada feature vira container ao ganhar layers", e a 2.2 já provou o padrão para
  `market_data` (containers + `domain-purity` + `store-no-storage-leak`
  estendidos).
- `numpy` (`>=2.x`) já está disponível no ambiente de teste (transitivo via
  `pandas`); a fixture-oráculo (Task 06) calcula as fórmulas canônicas em
  `numpy`/stdlib **dentro de `tests/`** (fora de `domain-purity`, que cobre só
  `src/.../domain`). Se o oráculo precisar de `numpy` como dep explícita de teste,
  adicioná-lo em `[project.optional-dependencies].dev` e registrar `[deviation]`.
- `pandas-ta-classic` **não** está instalado hoje — a Task 04 o adiciona e trava
  no `uv.lock`. A paridade de fórmula com o `pandas-ta` do old é validada pela
  fixture-oráculo (Q1 do concept; a lib é só a origem, não a fonte da verdade).

### Estrutura de pastas afetada

```
src/financial_forecasting/features/feature_engineering/
├── domain/
│   └── services/indicator_spec.py                         # Task 01 (VO + registry + hash)
├── application/
│   └── ports/out/indicator_calculator.py                  # Task 02 (Protocol)
└── adapters/out/
    └── pandas_ta/pandas_ta_indicator_calculator.py        # Task 05 (real adapter)
tests/
├── unit/features/feature_engineering/domain/
│   └── test_indicator_spec.py                             # Task 01
├── unit/features/feature_engineering/application/
│   └── test_indicator_calculator_fake.py                  # Task 03 (consumidor + Protocol)
├── fakes/features/feature_engineering/
│   └── in_memory_indicator_calculator.py                  # Task 03
└── contract/features/feature_engineering/
    ├── test_indicator_calculator_contract.py              # Task 05 (paridade fake↔real)
    ├── test_indicator_canonical_formulas.py               # Task 06 (oráculo)
    └── test_indicator_leakage.py                          # Task 07 (causalidade)
.importlinter                                              # Task 08
pyproject.toml / uv.lock                                   # Task 04
```

(Os `__init__.py` intermediários das novas pastas
`features/feature_engineering/**` e `tests/**/features/feature_engineering/**`
são criados junto da primeira Task que toca cada pasta.)

## 2. Tasks

> Faixa saudável: **3–8 Tasks**. Esta Stage tem **9** (decisões já fechadas no
> concept; cada Task fica pequena e com check objetivo — dentro da faixa de
> governança da corrida autônoma, ver concept §12).

### Task 01 — domain: `IndicatorSpec` (VO) + `INDICATOR_SPECS` + `indicator_registry_hash()`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/indicator_spec.py`
  - `tests/unit/features/feature_engineering/domain/test_indicator_spec.py`
  - `__init__.py` em `features/feature_engineering/`, `.../domain/`,
    `.../domain/services/` e nas pastas de teste correspondentes.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `IndicatorSpec` como `@dataclass(frozen=True)`, **domain
  puro stdlib-only** (só `dataclasses`/`hashlib`/`typing`/`collections.abc`),
  campos `name: str`, `family: str`, `source_cols: tuple[str, ...]`,
  `warmup: int`, `anti_leakage_tag: str`, `dtype: str = "float32"`, com
  `__post_init__` validando os invariantes (C1). No mesmo módulo, declarar o
  registry estático `INDICATOR_SPECS: Mapping[str, IndicatorSpec]` com os **11
  indicadores** (H-2) e a função pura `indicator_registry_hash() -> str`.
- **Detalhes técnicos:**
  - **C1 / `__post_init__`:** `name` não-vazio; `warmup >= 0`; `dtype` em
    `{"float32"}`; `anti_leakage_tag` em
    `{"trailing_window_causal", "same_timestamp_ohlc_derived"}`. Violação →
    `ValueError` com mensagem clara por campo.
  - **`INDICATOR_SPECS`** (concept §4, **warmups exatos** validados contra o
    `feature_registry.py` do old): `rsi_14`(momentum,`(close,)`,14,
    trailing_window_causal); `macd`(trend,`(close,)`,26,trailing); `macd_signal`
    (trend,`(close,)`,35,trailing); `ema_10/50/100/200`(trend,`(close,)`,N,
    trailing); `volatility_20d`(volatility,`(close,)`,20,trailing);
    `candle_range`(ohlc_derived,`(high, low)`,0,same_timestamp_ohlc_derived);
    `candle_body`(ohlc_derived,`(open, close)`,0,same_timestamp_ohlc_derived).
    **Exatamente 11 chaves** (o "11º" é o par `macd`/`macd_signal`; ver concept
    §4 nota).
  - **`indicator_registry_hash()` (I10):** `sha256` sobre os specs **ordenados
    por `name`**, serializando campos numa string determinística (replica
    `feature_registry_hash` do old:471-491). Função pura do conteúdo: mesmo
    registry → mesmo hash; mudar warmup/tag/dtype de qualquer spec **muda** o
    hash.
  - **Pureza (I1):** nenhum `import pandas`/`pandas_ta_classic`/`numpy`.
  - **Não** replicar `null_policy`/`enabled_by_default`/`group`/`formula_desc` do
    `FeatureSpec` rico do old — é escopo da Stage 3.4 (D2).
- **Critério de aceite (A2/A3):** unit test cobre `IndicatorSpec` válido + cada
  violação de C1 (`name` vazio, `warmup<0`, `dtype` inválido, `tag` inválida) →
  `ValueError`; `INDICATOR_SPECS` tem **as 11** chaves com warmups/tags/dtype
  exatos (assert por nome); `indicator_registry_hash()` é determinístico (duas
  chamadas → mesmo valor) e **muda** quando um spec é alterado (teste com registry
  perturbado local).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_indicator_spec.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/indicator_spec.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): IndicatorSpec + registry dos 11 + hash determinístico [3.1/task-01]`

---

### Task 02 — application: port-out `IndicatorCalculator` (`Protocol`)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/application/ports/out/indicator_calculator.py`
  - `__init__.py` em `.../application/`, `.../application/ports/`,
    `.../application/ports/out/`.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `IndicatorCalculator` como `typing.Protocol` estrutural
  (não ABC — I11), método
  `calculate(self, asset: str, candles: Sequence[Candle]) -> Sequence[Mapping[str, float]]`,
  tipos stdlib (`collections.abc.Sequence`/`Mapping`) + a entity `Candle`. Sem
  import de `adapters`/`pandas`/`pyarrow`/`pandas_ta_classic`.
- **Detalhes técnicos:**
  - Import de `Candle` de
    `financial_forecasting.features.market_data.domain.entities.candle` é runtime
    aqui (a `application` pode importar `domain`, inclusive de outro BC — LAYOUT
    §3/§7; concept §7 D3).
  - **I5 — port não vaza pandas/DataFrame:** uma `Mapping[str, float]` por barra
    (alinhada à ordem temporal após ordenação), chaves = nomes de
    `INDICATOR_SPECS`, valores `float` (materializados em `float32` pelo adapter),
    `NaN` tolerado no warmup. Nomes de coluna pandas-ta
    (`MACD_12_26_9`/`MACDs_12_26_9`) **não** cruzam a fronteira — ficam internos ao
    adapter.
  - Docstring documenta: ordenação por `timestamp` é responsabilidade do adapter;
    saída alinhada 1-barra→1-linha; `NaN` só no warmup declarado (I6).
  - **Não** criar adapter nesta Task (regra dura §4.3).
- **Critério de aceite (A4):** o módulo importa (`Protocol` sem corpo), `mypy
  --strict` verde; nenhum import de `adapters`/`pandas`/`pyarrow`/`pandas_ta_classic`.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/application/ports/out/indicator_calculator.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.application): port-out IndicatorCalculator (Protocol) [3.1/task-02]`

---

### Task 03 — application/tests: `InMemoryIndicatorCalculator` (fake) + teste do consumidor

- **Arquivos a criar:**
  - `tests/fakes/features/feature_engineering/in_memory_indicator_calculator.py`
  - `tests/unit/features/feature_engineering/application/test_indicator_calculator_fake.py`
  - `__init__.py` nas pastas de teste/fake.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** criar `InMemoryIndicatorCalculator` comportamental
  (stdlib-only, **não** `Mock`) que satisfaz o `Protocol` `IndicatorCalculator`
  por duck-typing — devolve, para cada `Candle`, uma `Mapping[str, float]` com
  **exatamente** as chaves de `INDICATOR_SPECS` (valores determinísticos
  pré-carregados ou derivados de forma trivial e causal — ex. `candle_range`/
  `candle_body` reais; demais como placeholders finitos pós-warmup). Escrever o
  teste que prova que um **consumidor genérico** (uma função que tipa
  `IndicatorCalculator`) usa o fake **sem importar `pandas`**.
- **Detalhes técnicos:**
  - O fake é a garantia (A5) de que a `application` é testável sem infra externa
    (skill `pytest-with-fakes`): consumidores futuros (3.5 `build_dataset`) testam
    contra ele.
  - O fake **deve** produzir o set completo dos 11 (mesma forma do real) para que
    o contract test (Task 05) rode o **mesmo** contrato sobre `[fake, real]`.
  - `NaN` durante o warmup permitido; pós-warmup finito (I6) — o fake honra essa
    forma para não divergir do real no contrato.
- **Critério de aceite (A5):** teste mostra o fake satisfazendo o `Protocol`
  (atribuível a uma variável tipada `IndicatorCalculator`, `mypy --strict`
  verde), produzindo uma `Mapping` por candle com as 11 chaves; um consumidor de
  exemplo roda sem `pandas`.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/application/test_indicator_calculator_fake.py -v
  uv run mypy --strict tests/fakes/features/feature_engineering/in_memory_indicator_calculator.py
  ```
- **Commit sugerido:** `test(feature-engineering.application): InMemoryIndicatorCalculator + teste de consumidor [3.1/task-03]`

---

### Task 04 — deps: pinar `pandas-ta-classic` + `uv.lock` + smoke de import

- **Arquivos a modificar:**
  - `pyproject.toml` (`pandas-ta-classic` em `[project].dependencies`)
  - `uv.lock` (sincronizado via `uv lock`)
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar `pandas-ta-classic` a `[project].dependencies` com
  comentário citando ADR `0.0.0024` (substitui o `pandas-ta==0.4.71b0` beta
  não-mantido do old — risco supply-chain, overview §10/§11), confinado ao adapter
  `out/pandas_ta` (Task 05). Rodar `uv lock` e o smoke de import.
- **Detalhes técnicos:**
  - Pinar por minor (`>=X.Y,<X.(Y+1)` ou equivalente segundo a versão resolvida);
    `uv.lock` trava o patch (mesma postura de `exchange-calendars`/`yfinance`).
  - Comentário no `pyproject.toml`: vive **só** no adapter
    `features/feature_engineering/adapters/out/pandas_ta/`; o gate
    `store-no-storage-leak`/`domain-purity` reprova se `pandas`/`pandas_ta_classic`
    vazar para `application`/`domain` (Task 08).
  - Se `numpy` precisar virar dep explícita de teste para a fixture-oráculo (Task
    06), adicioná-lo em `[project.optional-dependencies].dev` aqui e registrar
    `[deviation]`.
  - **Dependência nasce onde o import nasce** (lição 2.2 §7): a lib entra aqui,
    **antes** do adapter (Task 05), para o teste do adapter coletar.
- **Critério de aceite (A10):** `pandas-ta-classic` em `[project].dependencies`
  com `uv.lock` sincronizado; `uv run python -c 'import pandas_ta_classic'` ok.
- **Comando de verificação:**
  ```bash
  uv lock
  uv run python -c "import pandas_ta_classic; print('pandas_ta_classic ok')"
  ```
- **Commit sugerido:** `chore(deps): pinar pandas-ta-classic (ADR 0.0.0024) [3.1/task-04]`

---

### Task 05 — adapter: `PandasTaIndicatorCalculator` + contract test paridade fake↔real

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/adapters/out/pandas_ta/pandas_ta_indicator_calculator.py`
  - `tests/contract/features/feature_engineering/test_indicator_calculator_contract.py`
  - `__init__.py` em `.../adapters/`, `.../adapters/out/`,
    `.../adapters/out/pandas_ta/` e na pasta de teste.
- **Arquivos a modificar:** nenhum.
- **O que fazer:** implementar `PandasTaIndicatorCalculator` (satisfaz
  `IndicatorCalculator` por duck-typing) que converte `Sequence[Candle]` →
  `DataFrame` **ordenado por `timestamp`** (`.sort_values`), calcula os 11
  indicadores, coage `float32`, **valida o set completo** contra `INDICATOR_SPECS`
  e devolve `Sequence[Mapping[str, float]]`. Criar o contract test parametrizado
  rodando o **mesmo** contrato de forma sobre `[fake, real]` (paridade).
- **Detalhes técnicos:**
  - **`pandas`/`pandas_ta_classic` vivem SÓ aqui** (I12). Cálculos: `ta.rsi(close,
    length=14)` (Wilder); `ta.macd(close)` lendo `MACD_12_26_9`/`MACDs_12_26_9`
    (defaults 12/26/9); `ta.ema(close, length=N)` para 10/50/100/200;
    `volatility_20d = close.pct_change().rolling(20).std()`;
    `candle_range = high - low`; `candle_body = (close - open).abs()`.
  - **I9 — ordenação por `timestamp`** antes de calcular (base da causalidade I2 e
    do alinhamento linha-a-barra); **I8 — validação de set completo:**
    `set(produzidas) == set(INDICATOR_SPECS)` antes de devolver, senão erro
    explícito (C2; endurece o `RuntimeError("Missing technical indicators")` do old
    para igualdade de conjunto, não só presença).
  - **I4 — coerção `float32`** de cada coluna antes de mapear de volta;
    nomes de coluna pandas-ta **não** cruzam a fronteira (mapeados para os nomes
    de `INDICATOR_SPECS`). Sequência **vazia** → saída vazia (C5).
  - **Q1 (concept §13):** confirmar na execução que `pandas-ta-classic` expõe
    `ta.rsi`/`ta.macd`/`ta.ema` com esses nomes/semântica. Se divergir (ex. nomes
    de coluna ou RSI por SMA), ajustar a chamada / calcular manualmente o
    indicador e registrar `[decision]` na §7 — o contrato (11 indicadores, fórmula
    canônica, float32, causalidade) é fixo independentemente da lib; a
    fixture-oráculo (Task 06) é a rede que prova a correção.
  - **Contract test (paridade fake↔real):** fixture parametrizada `[fake, real]`,
    mesmos asserts de **forma**: `calculate` devolve uma `Mapping` por candle com
    **exatamente** as 11 chaves; valores `float` finitos pós-warmup; ordenação por
    timestamp respeitada (entrada desordenada → saída ordenada). A **fórmula**
    canônica e a **causalidade** ficam nas Tasks 06/07 (redes específicas do real).
- **Critério de aceite (A6):** contract test verde para `[fake, real]`; o real
  produz as 11 chaves coagidas a `float32`, ordenado por timestamp, com validação
  de set completo (set faltando/sobrando → erro, C2); `check_layout`/`import-linter`
  não acusam `pandas`/`pandas_ta_classic` fora do adapter.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/feature_engineering/test_indicator_calculator_contract.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/adapters/out/pandas_ta/pandas_ta_indicator_calculator.py
  ```
- **Commit sugerido:** `feat(feature-engineering.adapters): PandasTaIndicatorCalculator + contract test paridade [3.1/task-05]`

---

### Task 06 — test: fixture-oráculo de fórmula canônica (RSI-Wilder/MACD/EMA/volatility)

- **Arquivos a criar:**
  - `tests/contract/features/feature_engineering/test_indicator_canonical_formulas.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** escrever a fixture **analítica** (oráculo, ADR `0.0.0021`) que
  recalcula cada um dos 11 indicadores em `numpy`/stdlib **puro** (independente do
  `pandas-ta-classic`) e compara com a saída do `PandasTaIndicatorCalculator`
  dentro de `atol`/`rtol` declarados (calibrados para a precisão de `float32`).
- **Detalhes técnicos (I3/C6):**
  - **RSI = Wilder** (smoothing recursivo/RMA: `avg = (avg_prev*(n-1) + x)/n`,
    **não** SMA); **MACD = EMA12 − EMA26**; **signal = EMA9(MACD)**; **EMA
    recursiva** com `alpha = 2/(N+1)` (seed = primeira média/valor segundo a
    convenção da lib — alinhar na fixture); **`volatility_20d` = std rolling(20) de
    `close.pct_change()`**; `candle_range = high − low`;
    `candle_body = |close − open|`.
  - O teste **falha** se a lib produzir RSI por SMA, MACD com defaults ≠ 12/26/9,
    ou EMA com `alpha` errado (rede contra troca silenciosa de semântica —
    supply-chain, overview §10).
  - **Warmup efetivo do `volatility_20d` (I7/D6):** declarado `warmup=20`, efetivo
    **21** (1 do `pct_change` + 20 da janela `std`) — a fixture valida **finitude a
    partir da barra 21** e documenta a diferença em comentário.
  - **I6 — política de NaN:** `NaN` tolerado **só** durante o warmup declarado
    (efetivo, para o volatility); pós-warmup os valores são **finitos** (assert
    `isfinite`). Resolve o TODO "validar finitos" do old.
  - Série de entrada: gerar (ou fixar) uma série de candles longa o bastante para
    cobrir o maior warmup (`ema_200`=200) — ex. série sintética determinística com
    `seed` fixo; documentar a tolerância escolhida.
- **Critério de aceite (A7):** os 11 batem com o oráculo dentro de `atol`/`rtol`;
  RSI-Wilder/MACD=EMA12−EMA26/signal=EMA9/EMA `alpha=2/(N+1)`/volatility=std
  rolling de retornos explicitamente verificados; finitude pós-warmup (efetivo 21
  para volatility) provada.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/feature_engineering/test_indicator_canonical_formulas.py -v
  ```
- **Commit sugerido:** `test(feature-engineering): fixture-oráculo de fórmula canônica dos 11 indicadores [3.1/task-06]`

---

### Task 07 — test: causalidade / anti-leakage (barras futuras não alteram o passado)

- **Arquivos a criar:**
  - `tests/contract/features/feature_engineering/test_indicator_leakage.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:** escrever o teste de **leakage** obrigatório (I2, ADR
  `0.0.0021`): calcular os indicadores sobre N barras, **anexar** M barras
  posteriores, recalcular sobre N+M, e provar que os valores das N barras
  originais (**pós-warmup**) são **idênticos** — a chegada de futuro não muda o
  passado.
- **Detalhes técnicos (I2/I9):**
  - Rodar sobre o adapter **real** (`PandasTaIndicatorCalculator`); comparar as
    primeiras N linhas das duas execuções na região pós-warmup (do maior warmup
    relevante) com igualdade `float32` exata (ou `atol` mínimo se a lib introduzir
    ruído de recomputação — registrar `[decision]` se precisar).
  - Cobrir tanto indicadores trailing (`rsi`/`macd`/`ema`/`volatility` —
    causalidade não-trivial) quanto os `same_timestamp_ohlc_derived`
    (`candle_range`/`candle_body` — trivialmente causais, mas no mesmo teste por
    completude).
  - Incluir um caso de **entrada desordenada** (timestamps fora de ordem) para
    provar que `.sort_values` (I9) torna o resultado independente da ordem de
    entrada — reforça a causalidade.
- **Critério de aceite (A8):** valores pós-warmup das N barras originais idênticos
  após anexar M barras futuras; entrada desordenada produz a mesma saída ordenada.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/features/feature_engineering/test_indicator_leakage.py -v
  ```
- **Commit sugerido:** `test(feature-engineering): teste de leakage (causalidade dos indicadores) [3.1/task-07]`

---

### Task 08 — `feature_engineering` como container layered no `.importlinter`

- **Arquivos a modificar:**
  - `.importlinter` (3 contratos: `hexagonal-layers` containers, `domain-purity`
    source_modules, `store-no-storage-leak` source_modules)
- **Arquivos a criar:** nenhum.
- **O que fazer:** adicionar
  `financial_forecasting.features.feature_engineering` à lista `containers` de
  `hexagonal-layers` (mantendo `exhaustive = False` — não há `adapters/in`/
  `ports/in` nesta Stage); adicionar
  `...feature_engineering.domain` a `domain-purity`; adicionar
  `...feature_engineering.{application,domain}` a `store-no-storage-leak`. Provar
  inward-only + pureza por **quebra intencional revertida** (D1/I1).
- **Detalhes técnicos:**
  - **Não** criar contrato `independence` entre features (só 2 features; ADR
    `1.3.0001` difere isso). Adicionar comentário nas linhas alteradas citando
    concept 2.2 D1 / ADR `2.2.0001` / LAYOUT §3 ("cada NOVA feature com
    domain/application entra aqui").
  - Só esta Task toca `.importlinter` — e só **depois** que as três camadas
    físicas existem (Tasks 01–07), senão `type=layers` não tem módulos para medir.
  - **Prova por quebra intencional (A9):** inserir temporariamente `import pandas`
    no `domain` de `feature_engineering` (ex. no `indicator_spec.py`), rodar `uv
    run lint-imports` → deve **reprovar** `domain-purity` (e provavelmente
    `store-no-storage-leak`); reverter → verde. Registrar na §7 se relevante.
  - A lição da 2.2 (§7 [decision] import-linter) já provou que `hexagonal-layers`
    sozinho prova **direção**, não **pureza** de lib externa — por isso
    `domain-purity` + `store-no-storage-leak` precisam do `feature_engineering`
    explicitamente.
- **Critério de aceite (A9):** `uv run lint-imports` verde com
  `feature_engineering` nos `containers` + em `domain-purity` +
  `store-no-storage-leak`; quebra intencional (`import pandas` no domain) reprova e
  é revertida; `check_layout.py` verde para a estrutura da feature.
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `chore(import-linter): feature_engineering como container layered + pureza [3.1/task-08]`

---

### Task 09 — gate agregado da Stage (check + cobertura + ADRs)

- **Arquivos a modificar:** nenhum esperado (correções pontuais se um gate acusar).
- **Arquivos a criar:** nenhum.
- **O que fazer:** rodar o gate agregado e garantir tudo verde: `make check`
  (ruff + mypy --strict + import-linter + check_layout + testes), `make test`,
  cobertura ≥90% no diff (I13). Conferir A12 (ADRs `3_1_0001` e `0_0_0024` em
  `status: accepted` — já presentes no repo).
- **Detalhes técnicos:**
  - Se algum gate acusar, corrigir de forma mínima dentro do escopo da Stage (sem
    novos contratos) e re-rodar.
  - **Não** fazer o commit `stage 3.1: complete` nem marcar `done` no roadmap —
    isso é do orquestrador após auditoria (ver preâmbulo). Esta Task entrega a
    branch com gates verdes.
- **Critério de aceite (A11/A12):** `make check` e `make test` verdes; cobertura
  ≥90% no diff; `import-linter` verde com `feature_engineering` nos containers +
  `domain-purity` + `store-no-storage-leak`; ADRs `3_1_0001`/`0_0_0024`
  `accepted`.
- **Comando de verificação:**
  ```bash
  make check
  make test
  uv run pytest --cov=financial_forecasting.features.feature_engineering --cov-report=term-missing tests/
  ```
- **Commit sugerido:** `test(feature-engineering): gate verde da Stage 3.1 (check + cobertura) [3.1/task-09]`
  (omitir se a Task não produzir mudança de arquivo — neste caso é só verificação.)

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 3.1: complete` (feito pelo **orquestrador**, não por esta sessão) e ser
> mergeada em `develop`.

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
make test                 # todos os testes (unit + contract)
uv run lint-imports       # feature_engineering nos containers + domain-purity + store-no-storage-leak
uv run python scripts/check_layout.py
uv run pytest --cov=financial_forecasting.features.feature_engineering --cov-report=term-missing tests/
uv run python -c "import pandas_ta_classic; print('ok')"
```

### Verificações funcionais
- [ ] Dado um `Sequence[Candle]` de AAPL, `PandasTaIndicatorCalculator` produz uma
      `Mapping[str, float]` por barra (ordenada por timestamp) com **exatamente**
      as 11 chaves de `INDICATOR_SPECS`, em `float32`, `NaN` só no warmup.
- [ ] Os 11 indicadores batem com a fixture-oráculo (RSI-Wilder, MACD=EMA12−EMA26,
      signal=EMA9, EMA `alpha=2/(N+1)`, volatility=std rolling de retornos) dentro
      de `atol`/`rtol`.
- [ ] Teste de leakage: anexar barras futuras **não** altera os valores pós-warmup
      das barras originais; entrada desordenada → mesma saída ordenada.
- [ ] `InMemoryIndicatorCalculator` e `PandasTaIndicatorCalculator` passam o
      **mesmo** contract test parametrizado do port (paridade fake↔real).
- [ ] Quebra intencional (`import pandas` no domain de `feature_engineering`)
      reprova `domain-purity` no `import-linter` e é revertida.

### Mapeamento invariante ↔ teste

| Invariante (concept §5) | Teste / verificação |
|---|---|
| I1 — Pureza do domínio | `lint-imports` (`domain-purity` + quebra intencional, Task 08) + `check_layout.py`; ausência de `pandas`/`numpy` no `indicator_spec.py` |
| I2 — Causalidade / anti-leakage | `test_indicator_leakage.py` (barras futuras não alteram o passado; entrada desordenada → saída ordenada) |
| I3 — Fórmula canônica (oráculo) | `test_indicator_canonical_formulas.py` (RSI-Wilder/MACD/EMA/volatility vs numpy puro, `atol`/`rtol`) |
| I4 — Saída `float32` | `test_indicator_calculator_contract.py` (forma `float32`) + oráculo (tolerância de `float32`) |
| I5 — Port não vaza pandas/DataFrame | `mypy --strict` no port (só stdlib + `Candle`); `lint-imports` (`store-no-storage-leak`); contract test troca `Mapping` |
| I6 — Política de NaN explícita | `test_indicator_canonical_formulas.py` (finitude pós-warmup; `NaN` só no warmup) |
| I7 — Warmup declarado + convenção volatility | `test_indicator_spec.py` (warmups exatos) + oráculo (finitude a partir da barra 21 do volatility) |
| I8 — Set completo dos 11 validado | `test_indicator_calculator_contract.py` (11 chaves exatas; set faltando/sobrando → erro, C2) |
| I9 — Ordenação por timestamp | `test_indicator_leakage.py` (entrada desordenada → saída ordenada) + contract test |
| I10 — Hash determinístico | `test_indicator_spec.py` (mesmo registry → mesmo hash; spec alterado → hash muda) |
| I11 — Forma `Protocol` do port | `mypy --strict` + ausência de herança ABC; fake/adapter satisfazem por duck-typing (Task 03/05) |
| I12 — `pandas_ta_classic` confinado ao adapter | `lint-imports` (`store-no-storage-leak`/`domain-purity`) + inspeção: import só em `adapters/out/pandas_ta/` |
| I13 — Gates verdes | `make check` / `make test` / cobertura ≥90% (Task 09) |

### Checklist de fechamento da Stage
- [ ] Todas as 9 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` e `make test` verdes no branch; cobertura ≥90% no diff
- [ ] ADRs `3_1_0001` e `0_0_0024` em `status: accepted`
- [ ] `concept.md`/`technical.md` desta Stage não precisam de retoque material
- [ ] **(orquestrador, pós-auditoria)** commit `stage 3.1: complete` aplicado e
      `roadmap.md` marcado `done` — **fora do escopo desta sessão**

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências (inside-out). Explícito:

```
Task 01 (IndicatorSpec + registry + hash) ─► Task 02 (port) ─► Task 03 (fake + consumidor)
                                                  │
Task 04 (pandas-ta-classic dep) ──────────────────┴─► Task 05 (adapter + contract) ─┬─► Task 06 (oráculo)
                                                                                     └─► Task 07 (leakage)
Task 05 + Task 06 + Task 07 ─► Task 08 (.importlinter container + pureza) ─► Task 09 (gate agregado)
```

- Task 02 depende de 01 (o port tipa `Candle`, mas a forma da saída espelha
  `INDICATOR_SPECS`); 03 depende de 02 (o fake satisfaz o port); 04 (dep) precede
  05 (o adapter importa a lib); 05 depende de 02 (implementa o port) e de 01
  (valida set contra o registry); 06/07 dependem de 05 (medem a saída do adapter
  real); 08 depende de 01–07 (camadas físicas existem para o `type=layers` provar
  a direção); 09 é o gate agregado final.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| `pandas-ta-classic` muda semântica do RSI (SMA vs Wilder) ou nomes/defaults do MACD vs old (Q1) | Fixture-oráculo (Task 06) reprova qualquer divergência; se a lib divergir, ajustar a chamada ou calcular o indicador manualmente no adapter e registrar `[decision]` — o contrato é fixo independentemente da lib |
| Coerção `float32` perde precisão e reprova a tolerância da fixture | `atol`/`rtol` calibrados para `float32`; fixture compara em `float32` (I4); se a recomputação introduzir ruído no leakage, usar `atol` mínimo e registrar `[decision]` |
| Warmup efetivo do `volatility_20d` (20 declarado vs 21 efetivo) deixa `NaN` pós-warmup ou esconde leakage | I7/D6: fixture valida finitude a partir da barra 21; documentar a diferença; manter `warmup=20` por paridade com o old |
| `import pandas`/`pandas_ta_classic` vaza para domain/application | Task 08: `domain-purity` + `store-no-storage-leak` estendidos ao BC; quebra intencional reprova e é revertida (lição 2.2 §7) |
| `pandas-ta-classic` não resolve no `uv.lock` (supply-chain) | Pin explícito + `uv lock`; smoke `uv run python -c 'import pandas_ta_classic'`; ADR `0.0.0024` de proveniência; se travar, fixar versão compatível e registrar `[deviation]` |
| Fixture-oráculo precisa de `numpy` como dep explícita de teste | Adicionar `numpy` em `[project.optional-dependencies].dev` na Task 04 e registrar `[deviation]` (hoje é transitivo via pandas) |
| Seed da EMA do `pandas-ta-classic` difere da convenção do oráculo (primeira média vs primeiro valor) | Alinhar o seed na fixture à convenção observada da lib (documentar); a tolerância pós-warmup absorve o transiente do seed |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (escopo, contratos §4,
  invariantes §5, casos de erro §6, decisões §7, critérios §11, Q1 §13)
- [`../../overview.md`](../../overview.md) — §3/§6/§7/§10/§11
- [`../../roadmap.md`](../../roadmap.md) — Stage `3.1-technical-indicators`
  (`arquivos_a_criar`, `definition_of_done`, `non_goals`) e vizinhas (3.4/3.5)
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md)
  — H-2 (replicar os 11 indicadores + validar fórmulas, sem expansão)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §4 — branches, commits, status
- [`../../LAYOUT.md`](../../LAYOUT.md) §1/§3/§7 — estrutura `features/<feature>/`,
  direção inward, application pode importar domain de outro BC
- [`../../PIPELINE.md`](../../PIPELINE.md) §4.3 — Task atômica (port antes de adapter)
- ADRs desta Stage:
  [`3.1.0001`](../../adr/3_1_0001-feature-engineering-bc-and-indicator-contracts.md),
  [`0.0.0024`](../../adr/0_0_0024-pandas-ta-classic-over-pandas-ta.md)
- ADRs de fundação: [`0.0.0021`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md)
  (contract tests + oráculo, fixtures analíticas);
  [`1.3.0001`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md)
  (container layered por feature; `independence` diferido)
- Stage 2.2 (consumida): entity `Candle`; padrão "feature como container layered"
  (D1, ADR `2.2.0001`); lição `.importlinter` (technical 2.2 §7 [decision])
- `.importlinter` linha 42 (verbatim "cada feature vira container ao ganhar
  layers"); blocos `domain-purity` (69-83) e `store-no-storage-leak` (157-175)
- Skills aplicáveis: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `ddd-tactical-patterns`, `import-linter-rules`
- Old (semântica/warmups, **não** implementação):
  `src/adapters/technical_indicator_calculator.py:43-63` (cálculo dos 11 +
  `.sort_values` + `RuntimeError` de set incompleto),
  `src/interfaces/technical_indicator_calculator.py` (ABC → virar `Protocol`),
  `src/infrastructure/schemas/feature_registry.py:7-17/58-135/471-491` (molde
  `FeatureSpec`, warmups/tags, `feature_registry_hash`),
  `src/infrastructure/schemas/technical_indicators_schema.py` (set de 11 — H-2),
  `src/entities/technical_indicator_set.py:22-23` (TODO "validar finitos" —
  resolvido por I6), `pyproject.toml:21` (`pandas-ta==0.4.71b0` — trocado)

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
> **Corrida autônoma overnight (ADR `0.0.0050`):** nesta corrida o agente
> **não pergunta** — decide com julgamento (política de decisão do BRIEF),
> registra como `[decision]`/`[finding]`/`[deviation]` e segue. Decisões
> não-triviais viram ADR `3_1_NNNN`.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Decisão:** <o que foi decidido>                        <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage** (com direção sugerida
  e Stage candidata).
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-06-29 — [deviation] ADRs — `3_1_0001` e `0_0_0024` já presentes no repo — code assistant
**Contexto:** O concept (§1/§7 D4/A12) previa **criar** os arquivos ADR
`3_1_0001-feature-engineering-bc-and-indicator-contracts.md` e
`0_0_0024-pandas-ta-classic-over-pandas-ta.md`. Ambos **já existem** em
`docs/adr/` (verificado na Fase 3B).
**Razão:** Os ADRs foram materializados na Fase 3A (concept) desta mesma Stage.
Esta Stage apenas **confere** que estão `status: accepted` (Task 09 / A12), sem
recriá-los. Sem efeito no escopo entregue — só a redação "criar" do concept fica
imprecisa; o as-built é "já criados, conferir status".

### 2026-06-29 — [decision] Task 01 — registry tem **10 chaves** (não 11) — code assistant
**Contexto:** O concept §1/§4 e o technical Task 01 falam em "**11 indicadores**" e
o critério de aceite chegou a escrever "**Exatamente 11 chaves**". Mas a própria §4
nota do concept esclarece "10 nomes na tabela" e o set autoritativo do old
(`technical_indicators_schema.py::TECHNICAL_INDICATORS`, H-2 = replicar o EXATO) tem
**10 entradas**: `rsi_14`, `macd`, `macd_signal`, `ema_10/50/100/200`, `volatility_20d`,
`candle_range`, `candle_body`.
**Decisão:** `INDICATOR_SPECS` declara **10 chaves** (= colunas produzidas), idêntico
ao set do old. O "11º" do discurso é a contagem do par `macd`/`macd_signal` como saída
de UMA chamada `ta.macd` (vira 2 colunas). O teste assere `len == 10` e
`set == TECHNICAL_INDICATORS` do old.
**Razão:** H-2 (decisão humana fechada) manda replicar o set EXATO do old, sem
expansão. O old tem 10 colunas. "11" é fraseado do concept, não contrato — a autoridade
é o set do old. Documentado no docstring do `indicator_spec.py` e no teste.

### 2026-06-29 — [decision] Task 05/06 — Q1 confirmado: `pandas-ta-classic` 0.6.52 = semântica do old — code assistant
**Contexto:** Q1 (concept §13) pedia confirmar na execução que o `pandas-ta-classic`
expõe `ta.rsi`/`ta.macd`/`ta.ema` com os nomes de coluna e a semântica do `pandas-ta`
do old.
**Decisão:** Confirmado por probe e pela fixture-oráculo (Task 06): `ta.rsi(close,
length=14)` → Series `RSI_14` (smoothing de **Wilder/RMA**, casa com o oráculo
recursivo dentro de ~1e-14 em float64 pós-warmup 14); `ta.macd(close)` → DataFrame com
`MACD_12_26_9`/`MACDs_12_26_9` (defaults 12/26/9 = EMA12-EMA26 e EMA9(MACD)); `ta.ema(
close, length=N)` → `EMA_N` (recursiva, seed SMA, `alpha=2/(N+1)`). **Nenhum** cálculo
manual de fallback foi necessário — a chamada do concept §4 vale como escrita.
**Razão:** A lib mantida (0.6.52) preserva a semântica do beta do old; a fixture-oráculo
é a rede que prova a paridade independentemente da lib (a `test_rsi_diverges_from_sma_variant`
garante que a fixture discrimina Wilder de SMA).

### 2026-06-29 — [deviation] Task 09 — teste de guard do set (I8/C2) p/ cobrir o ramo de erro — code assistant
**Contexto:** O contract test (Task 05, caminho feliz) não atinge o ramo de erro de
`_require_complete_set` (linhas do `raise` quando o set diverge), deixando a cobertura
do adapter em 94% (3 linhas do `missing`/`extra`/`raise` descobertas).
**Razão:** I8/C2 é invariante load-bearing (endurece o `RuntimeError` do old para
igualdade de conjunto). Adicionado `tests/unit/features/feature_engineering/adapters/
test_indicator_set_guard.py` exercitando os dois lados da divergência (coluna faltando
e coluna sobrando) + o caminho feliz, levando a cobertura do BC novo a **100%**. Teste
`unit` que importa `pandas` (vive em `tests/`, fora do gate import-linter; adapters são
testados com a lib real). Sem mudança no código de produção.

### 2026-06-29 — [finding] `processed` schema + use case de gravação — Stage 3.5 — code assistant
**Contexto:** A DoD do roadmap diz "valores em float32 gravados em bronze->processed",
mas esta Stage entrega só o **cálculo** (`IndicatorCalculator` → `Sequence[Mapping]`
float32), sem schema `processed` no `MedallionStore` nem use case de gravação (concept
§1/§7 D5: "bronze→processed" = direção de fluxo, não wiring).
**Direção sugerida:** A **Stage 3.5** (`3.5-dataset-builder-and-contracts`) é dona da
montagem/persistência: ela consome `IndicatorCalculator`, define o `dataset_schema`
(pandera) e grava em `processed` via `MedallionStore`. Nenhuma ação nesta Stage; o
contrato float32 já está pronto para 3.5 consumir.

### 2026-06-29 — [deviation] Auditoria de testes — sensibilidade do hash a `family`/`source_cols` (I10) — code assistant
**Contexto:** O `test_indicator_spec.py` cobria a sensibilidade de
`indicator_registry_hash()` só a `warmup` e `anti_leakage_tag`. A serialização canônica
do hash junta **6 campos** (`name`/`family`/`source_cols`/`warmup`/`anti_leakage_tag`/
`dtype`); uma mutação que removesse `family` ou `source_cols` da string canônica deixaria
o hash ainda "determinístico" e os dois testes existentes **verdes** — o buraco
sobreviveria, violando I10 ("qualquer mudança de spec muda o hash").
**Razão:** Adicionados `test_registry_hash_changes_when_family_changes` e
`test_registry_hash_changes_when_source_cols_changes` (perturbam `family`/`source_cols`
de um spec e exigem hash diferente). Fecha o gap de mutação em I10. Sem mudança no código
de produção.

### 2026-06-29 — [deviation] Auditoria de testes — lado `NaN` do warmup (I6/I7/D6) — code assistant
**Contexto:** As asserções de finitude (`test_finite_after_*`) provavam só o **lado
pós-warmup** (valores finitos a partir de `[warmup:]`). Um cálculo que seedasse o
indicador cedo demais (seed não-causal/look-ahead a partir da barra 0) passaria nelas —
o lado `NaN` da região de aquecimento (I6/I7/D6) não era verificado, apesar de a docstring
de `test_finite_after_effective_warmup` afirmar "NaN só antes".
**Razão:** Adicionado `test_warmup_region_is_nan_before_first_finite` (parametrizado) em
`test_indicator_canonical_formulas.py`, ancorado em boundaries estáveis verificados contra
o adapter real: `ema_N` NaN em `N-2`/finito em `N-1`; `macd` NaN até 24/finito em 25
(seed da EMA26); `volatility_20d` NaN na barra 19 (dentro da janela). Prova que a região
de aquecimento existe e está na posição esperada (barra 0 + última barra do warmup = NaN).
Nota: os warmups declarados são **limites superiores conservadores** — `rsi_14` e o
`volatility_20d` na barra 20 já são finitos no adapter real, por isso o teste mira só os
boundaries estáveis (EMA/MACD/vol-19), não um "NaN imediatamente antes do warmup declarado"
genérico (que seria frágil). Sem mudança no código de produção.

<!-- END: post-execution -->