---
title: Technical — Stage 3.4 — Registro de features e derivadas causais (feature_engineering, domínio puro)
description: Plano de execução da Stage 3.4 — Tasks ordenadas (mono-layer domain, intra-domain dependency order) — FeatureSpec value-object frozen com tag de causalidade + tft_typing obrigatórios → FeatureRegistry domain service (fonte da verdade, FEATURE_SPECS imutável, feature_set_hash determinístico) → DerivedFeatures domain service em Python puro (preço/volatilidade/regimes, sentimento, fundamentos+YoY) como oráculo causal → testes de hash, rejeição-sem-contrato e causalidade. 1 Task = 1 commit, pronto para code assistant
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, feature-registry, feature-spec, derived-features, feature-engineering, pure-domain, stdlib-only, anti-leakage, causalidade, tft-typing, known-unknown, family, feature-set-hash, oracle, log-return, momentum, drawdown, amihud, volume-zscore, parkinson, garman-klass, downside-semivol, vol-of-vol, regime, sentiment-lag, sentiment-ema, yoy, pct-change, rolling, ewm, shift, ddof, clip]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 3.4-feature-registry-and-derived
stage_title: Registro de features e derivadas causais
step_id: 3
step_title: Camada de features (silver)
depends_on: [3.1-technical-indicators]
concept_ref: ./concept.md
issue_id: 29
branch: feat/29-3-4-feature-registry-and-derived
tasks_count: 8
---

# Technical — Stage 3.4 — Registro de features e derivadas causais (`feature_engineering`)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [3.4/task-NN]`, body em bullets,
>    rodapé `Refs #29`. Escopo ASCII/kebab (sem `/`); use `.` no lugar de `/`
>    para a camada (`feature-engineering.domain`), padrão aceito pelo
>    `check_commit_msg.py` (ver §7 da 2.2 / 3.1).
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[finding]`/`[deviation]`. Esta é corrida autônoma overnight
>    (ADR `0.0.0050`): **não perguntar** — decidir com julgamento, registrar e seguir.
> 7. **Fechamento NÃO é desta sessão.** O commit `stage 3.4: complete` e a marcação
>    `done` no `roadmap.md` são do **orquestrador**, após auditoria independente.
>    Esta sessão entrega concept/technical/código/testes commitados e gates verdes.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/29-3-4-feature-registry-and-derived`. Não há sub-PRs internos.

## 1. Contexto e estratégia de execução

### Resumo
Esta Stage é **mono-layer domain, tudo puro** (stdlib-only). Constrói o registry rico
de features do BC `feature_engineering` como três módulos de domínio puro:
`FeatureSpec` (value-object frozen — superset rico do `IndicatorSpec` da 3.1, com tag de
causalidade e `tft_typing` known/unknown obrigatórios), `FeatureRegistry` (domain service
que é a fonte única da verdade: `FEATURE_SPECS` imutável com todas as features das 4
famílias + derivadas, getters, e `feature_set_hash` determinístico) e `DerivedFeatures`
(domain service que computa as ~38 derivadas em Python puro — `math` stdlib sobre
sequências/tuplas — replicando as fórmulas/warmups verbatim do old como **oráculo causal**
que a 3.5 em pandas valida). Nenhum port, adapter, use case ou DTO nesta Stage; nenhuma
persistência; nenhum pandas. Os testes provam hash determinístico/sensível, rejeição de
feature sem contrato de causalidade, e causalidade das derivadas (anexar barras futuras não
altera o passado; shift sempre positivo).

### Estratégia — ordem das Tasks e razão
Esta Stage **não é vertical slice**: não há porta/adapter/use case, só domínio puro.
A skill `task-ordering-hex` (Exceptions) manda **declarar a ordem escolhida**. Aqui a ordem
é dirigida pela **dependência intra-domínio**, não pelo grafo de camadas:

1. **`FeatureSpec` (VO) primeiro** — os invariantes (tag obrigatória, `tft_typing`,
   `family` de 4, `warmup>=0`, `name` não-vazio) são a fundação; o registry e os testes
   dependem dele. Task 01, com testes de validação na mesma Task.
2. **`FeatureRegistry` (service) depois** — `FEATURE_SPECS` constrói instâncias de
   `FeatureSpec` (depende de 01); inclui `feature_set_hash`. As specs das derivadas e do
   sentimento/fundamento entram aqui (são metadados, não computação). Tasks 02–03.
3. **`DerivedFeatures` (service)** — independe do registry (opera sobre sequências, não
   sobre specs), mas é mais pesado; fatiado por família para coesão e commits pequenos
   (<=5 arquivos, derivadas verbatim por grupo). Tasks 04–06.
4. **Testes transversais** de causalidade + hash + rejeição (Task 07) — cruzam VO + registry
   + derivadas; ficam por último porque consolidam invariantes de toda a Stage.
5. **Gate agregado** (Task 08) — pureza (import-linter `domain-purity` + `check_layout`),
   `make check`, cobertura `>= 90%`.

Cada Task deixa o build verde: o módulo de uma Task e seus testes existem antes do módulo
da Task seguinte que depende dele. As derivadas (04–06) são acumulativas no mesmo módulo
`derived_features.py`, mas cada Task adiciona funções coesas + seus testes de causalidade,
mantendo verde.

### Pré-condições
- Stage `3.1-technical-indicators` em `done` (BC `feature_engineering` é container layered
  com prova de pureza; `IndicatorSpec`/`indicator_registry_hash` existem como molde/postura).
- Branch `feat/29-3-4-feature-registry-and-derived` em checkout (já criada).
- `make setup` executado (hooks de commit instalados; `uv` sincronizado).

### Premissas técnicas
- Python 3.12; `pyproject.toml`/`uv.lock` já existem; nenhuma dependência nova (stdlib-only).
- As fórmulas/warmups do old são corretas e estáveis (produção); a tarefa é **traduzir**
  semântica pandas → Python puro, não reinventar (concept §3 Premissas).
- O oráculo opera sobre sequências já alinhadas no tempo (uma barra por timestamp), forward
  fill da grade densa é responsabilidade da 3.5; aqui chegam sequências 1:1.
- Convenção de tradução pandas → puro (concept §4 Introduzidos / §5):
  `rolling(window=n, min_periods=n)` → `None` nas `n-1` primeiras posições;
  `std(ddof=0)` (variância populacional, divide por `n`); `ewm(span=s, adjust=False)`
  recursiva com `alpha=2/(s+1)`; `pct_change(n, fill_method=None)` → `None` nos `n` primeiros;
  `shift(n)` com `n>0` sempre; `clip(lower=0)` antes de `sqrt`; `_safe_ratio` devolve `None`
  quando denominador é `None`/`0`/`NaN`.

### Estrutura de pastas afetada

```
src/financial_forecasting/features/feature_engineering/
└── domain/
    ├── value_objects/
    │   ├── __init__.py            # novo (pacote ainda não existe)
    │   └── feature_spec.py        # novo — Task 01
    └── services/
        ├── feature_registry.py    # novo — Tasks 02–03
        └── derived_features.py    # novo — Tasks 04–06
tests/unit/features/feature_engineering/domain/
├── test_feature_spec.py           # novo — Task 01
├── test_feature_registry.py       # novo — Tasks 02–03, 07
└── test_derived_features_causal.py # novo — Tasks 04–07
```

> `indicator_spec.py` da 3.1 vive em `domain/services/`. `FeatureSpec` é value-object e vai
> em `domain/value_objects/` (alinha DDD; pacote criado nesta Stage). `feature_registry.py`
> e `derived_features.py` são domain **services** (roadmap §3.4), vão em `domain/services/`.

## 2. Tasks

### Task 01 — domain: `FeatureSpec` (VO frozen) com tag de causalidade + `tft_typing` obrigatórios

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/value_objects/__init__.py`
  - `src/financial_forecasting/features/feature_engineering/domain/value_objects/feature_spec.py`
  - `tests/unit/features/feature_engineering/domain/test_feature_spec.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o value-object `FeatureSpec` (`@dataclass(frozen=True)`) — superset rico do
  `IndicatorSpec` da 3.1. Campos exatos do concept §4: `name: str`, `family: str`,
  `source_cols: tuple[str, ...]`, `formula_desc: str`, `anti_leakage_tag: str`,
  `warmup_count: int`, `tft_typing: str`, `null_policy: str = "allow"`,
  `dtype: str = "float64"`, `enabled_by_default: bool = True`. `__post_init__` valida os
  invariantes e levanta `ValueError` de domínio (mensagens incluindo `name`, espelhando o
  estilo do `indicator_spec.py`).
- **Detalhes técnicos:**
  - Conjuntos permitidos como `frozenset[str]` no módulo:
    - `_ALLOWED_FAMILIES = {price, technical, sentiment, fundamental}` (I4, ADR 0.0.0016).
    - `_ALLOWED_TAGS = {point_in_time_ohlcv, same_timestamp_ohlc_derived, trailing_window_causal, lagged_causal, publication_cutoff_asof, reported_date_asof}` (superset das 2 tags da 3.1; concept §4).
    - `_ALLOWED_TFT_TYPING = {known, unknown}` (I3).
  - `__post_init__` (concept §6): `name` vazio → `ValueError` (C1); `warmup_count<0` →
    `ValueError` (C2); `family ∉` set → `ValueError` (C3); `anti_leakage_tag ∉` vocabulário
    → `ValueError` (C4, espinha do DoD); `tft_typing ∉ {known,unknown}` → `ValueError` (C5).
  - Imports: **só stdlib** (`dataclasses`). Sem numpy/pandas/pydantic.
- **Critério de aceite:**
  - Construir um spec válido funciona; instância é frozen (atribuir campo levanta erro).
  - Testes cobrem C1–C5 (cada erro com `pytest.raises(ValueError)`), happy path, defaults.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_feature_spec.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/value_objects/feature_spec.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): FeatureSpec com tag de causalidade e tft_typing obrigatorios [3.4/task-01]`

---

### Task 02 — domain: `FeatureRegistry` — `FEATURE_SPECS` (preço/técnico/sentimento/fundamento) + getters + `feature_set_hash`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/feature_registry.py`
  - `tests/unit/features/feature_engineering/domain/test_feature_registry.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o domain service `FeatureRegistry` com o registry estático `FEATURE_SPECS`
  (`Mapping[str, FeatureSpec]` via `MappingProxyType`, read-only). Nesta Task entram as
  features **base** das 4 famílias (sem as derivadas, que vêm na 03): preço/baseline
  (`open`/`high`/`low`/`close`/`volume` → `family="price"`, tag `point_in_time_ohlcv`,
  `tft_typing="unknown"`), técnico (os 10 indicadores da 3.1 + `candle_*` → `technical`,
  tags `trailing_window_causal`/`same_timestamp_ohlc_derived`), sentimento
  (`sentiment_score`/`news_volume`/`sentiment_std`/`has_news` → `sentiment`,
  `publication_cutoff_asof`) e fundamento base (`revenue`/`net_income`/
  `operating_cash_flow`/`total_shareholder_equity`/`total_liabilities` → `fundamental`,
  `reported_date_asof`). Implementar `get_feature_spec(name)`, `list_feature_specs(*,
  family=None, enabled_only=False)` e `feature_set_hash(specs=None) -> str`.
- **Detalhes técnicos:**
  - **Mapeamento de família (I4):** o old usava `group` de 5 valores; aqui `baseline` →
    `price`, `derived` NÃO é família (a derivada herda a família da sua natureza: preço/
    volatilidade → `price`/`technical`, sentimento → `sentiment`, fundamento →
    `fundamental`). Documentar a tabela de mapeamento em docstring.
  - **`tft_typing` (I3, D4):** calendário (`day_of_week`/`month`/`time_idx`, se presentes
    como features) = `known`; todo o resto (preço/indicador/sentimento/fundamento/derivada)
    = `unknown`. Registrar a regra única na docstring do módulo.
  - **`feature_set_hash` (I5, D3):** `sha256` inline (postura idêntica a
    `indicator_registry_hash` da 3.1) — itera `sorted(registry.keys())`, serializa cada spec
    numa string canônica delimitada por `|` cobrindo **todos** os campos
    (`name|family|source_cols(join ",")|formula_desc|anti_leakage_tag|warmup_count|tft_typing|null_policy|dtype|enabled_by_default`),
    junta por `\n`, `.encode("utf-8")`, `sha256().hexdigest()`. Aceita `specs` alternativo
    (default `FEATURE_SPECS`) para teste de perturbação.
  - Imports: **só stdlib** (`collections.abc`, `dataclasses` não precisa, `hashlib`,
    `types.MappingProxyType`, `typing`) + `from ..value_objects.feature_spec import FeatureSpec`.
- **Critério de aceite:**
  - `FEATURE_SPECS` é `MappingProxyType` (mutação levanta `TypeError`); construir não levanta
    (toda feature base tem contrato — A2 parcial).
  - `get_feature_spec`/`list_feature_specs(family=...)` retornam o esperado.
  - Testes de hash: estável (mesmo set → mesmo hash), independente da ordem de inserção
    (construir dict reordenado → mesmo hash), e muda quando qualquer campo de qualquer spec
    é perturbado (A4/I5).
  - Teste de rejeição: instanciar `FeatureSpec` sem tag válida / sem `tft_typing` válido
    levanta `ValueError` (A3 — reusa o VO da Task 01, prova que o registry não consegue
    conter feature sem contrato).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_feature_registry.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/feature_registry.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): FeatureRegistry com FEATURE_SPECS base e feature_set_hash deterministico [3.4/task-02]`

---

### Task 03 — domain: specs das ~38 derivadas no `FEATURE_SPECS` (metadados + warmups verbatim)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/feature_registry.py`
  - `tests/unit/features/feature_engineering/domain/test_feature_registry.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:**
  Adicionar ao `FEATURE_SPECS` as specs (metadados, **não** computação) das ~38 derivadas do
  old, com `formula_desc`/`warmup_count`/`anti_leakage_tag`/`family`/`tft_typing`/`dtype`
  verbatim do `feature_registry.py` do old: log-returns (1d/5d/21d), momentum (5/21/63d),
  reversal (1d/5d), `drawdown_lookback`, `amihud_illiquidity_proxy`, `volume_zscore`,
  `volume_spike_flag` (int), volatilidades (`parkinson`/`garman_klass`/`downside_semivolatility`/
  `vol_of_vol`), regimes (`volatility_regime`/`trend_regime` int, `stress_tail_return_flag`
  int), sentimento dinâmico (`sentiment_lag_1/3/5`, `sentiment_ema`, `sentiment_surprise`,
  `sentiment_x_volatility`, `sentiment_x_volume`) e fundamento derivado (`net_margin`,
  `leverage_ratio`, `cashflow_efficiency`, `revenue_yoy_growth`, `net_income_yoy_growth`).
- **Detalhes técnicos:**
  - **Família das derivadas (I4):** preço/volatilidade/regime → `price` (ou `technical` se
    deriva de indicador, ex.: `vol_of_vol`/`volatility_regime` de `volatility_20d`,
    `trend_regime` de `ema_10`/`ema_50`); sentimento dinâmico → `sentiment`; fundamento
    derivado/YoY → `fundamental`. **Decisão** registrada em docstring (sem ADR: mapeamento
    mecânico de `group=derived` do old para as 4 famílias por natureza da fonte).
  - **Tags:** derivadas de OHLCV/preço → `trailing_window_causal` (ou `lagged_causal` para
    os puros `shift` de sentimento — `sentiment_lag_*`); fundamento derivado/YoY →
    `reported_date_asof` (verbatim old). Onde o old usava `trailing_window_causal` para
    `sentiment_lag_*`, **avaliar** promover para `lagged_causal` (tag nova do vocabulário
    3.4) — se mudar, registrar `[decision]` em §7 e ajustar o teste de tag.
  - **Warmups verbatim + efetivo (I7):** copiar `warmup_count` do old (ex.: `vol_of_vol`=40
    documentado como 20+20; `volume_zscore`=20 como estatística trailing `t-20..t-1` +
    numerador corrente; YoY=252). Documentar o warmup efetivo na docstring quando diferir do
    tamanho de janela nominal.
  - **`tft_typing`:** todas as derivadas = `unknown` (I3).
  - Sem novo import (continua só stdlib + `FeatureSpec`).
- **Critério de aceite:**
  - `FEATURE_SPECS` agora cobre **todas** as features (base + ~38 derivadas) — `len` e
    presença das chaves derivadas testadas; construir não levanta (A2 completo).
  - `list_feature_specs(family="fundamental")` inclui `revenue_yoy_growth`/
    `net_income_yoy_growth`; `volume_spike_flag`/regimes/`stress_tail_return_flag` têm
    `dtype` int.
  - Teste de cobertura de famílias/tft_typing: toda spec tem `family ∈` set, `tft_typing ∈
    {known,unknown}`, `anti_leakage_tag ∈` vocabulário (A2/A7).
  - `feature_set_hash` recalculado é estável após adicionar as derivadas (snapshot de hash
    determinístico no teste).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_feature_registry.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/feature_registry.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): registrar specs das ~38 derivadas no FEATURE_SPECS [3.4/task-03]`

---

### Task 04 — domain: `DerivedFeatures` — derivadas de preço/retorno/liquidez (Python puro)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/derived_features.py`
  - `tests/unit/features/feature_engineering/domain/test_derived_features_causal.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer:**
  Criar o domain service `DerivedFeatures` com os helpers de tradução pandas → puro e o
  primeiro grupo de derivadas (preço/retorno/liquidez), funções puras `seq -> tuple` que
  recebem sequências alinhadas e devolvem tuplas alinhadas 1:1 com `None` nos warmups.
  Grupo: `log_return_1d/5d/21d` (`log(close_t/close_{t-n})`), `momentum_5/21/63d`
  (`close_t/close_{t-n} - 1`), `reversal_1d` (`-pct_change_1`), `reversal_5d`
  (`-momentum_5d`), `drawdown_lookback` (`close_t/rolling_max(close,63)_t - 1`),
  `amihud_illiquidity_proxy` (`abs(pct_change_1)/volume_t`, `None` se `volume<=0`),
  `volume_zscore` (`(volume_t - mean(volume_{t-20..t-1}))/std_pop(...)`, `None` se `std<=0`),
  `volume_spike_flag` (`1 if zscore>3 else 0`).
- **Detalhes técnicos:**
  - **Helpers internos puros (concept §4/§5)** no módulo: `_safe_ratio(num, den) -> float |
    None` (`None` se `den` é `None`/`0`/`NaN`); `_pct_change(seq, n)` (`None` nos `n`
    primeiros); `_shift(seq, n)` com `n>0`; `_rolling(seq, n)` que itera janelas `min_periods=n`;
    `_mean`/`_std_pop` (ddof=0); `_rolling_max`. Todos puros (`math` stdlib).
  - **Causalidade (I6):** `volume_zscore` usa `volume` **shiftado 1** na janela de 20
    (`volume_{t-20..t-1}`), numerador é `volume_t` corrente (warmup efetivo = 20 + corrente).
    Nenhum shift negativo.
  - **Erros (C6/C7):** divisão por zero/None → `None` (não `inf`/`NaN` propagado); posição
    em warmup → `None`.
  - Imports: **só stdlib** (`math`, `collections.abc`, `typing`). Sem numpy/pandas.
- **Critério de aceite:**
  - Testes contra valores conhecidos (oráculo manual / paridade com fórmula): ex.
    `log_return_1d` numa sequência pequena bate com `ln(c1/c0)`; `None` no warmup.
  - **Teste de causalidade central (I6):** anexar barras **futuras** à sequência NÃO altera
    o prefixo já computado (prefixo estável) — para cada função do grupo.
  - `volume_spike_flag ∈ {0,1}`; `volume_zscore`=`None` quando `std` trailing é 0.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_derived_features_causal.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/derived_features.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): DerivedFeatures de preco/retorno/liquidez em Python puro [3.4/task-04]`

---

### Task 05 — domain: `DerivedFeatures` — volatilidades + regimes (Parkinson/GK/downside/vol-of-vol/regimes/stress)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/derived_features.py`
  - `tests/unit/features/feature_engineering/domain/test_derived_features_causal.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:**
  Adicionar o grupo de volatilidades e regimes: `volatility_parkinson`
  (`sqrt(rolling_mean(ln(h/l)^2,20)/(4*ln2))`), `volatility_garman_klass`
  (`sqrt(rolling_mean(0.5*ln(h/l)^2-(2ln2-1)*ln(c/o)^2,20))`), `downside_semivolatility`
  (`sqrt(rolling_mean(min(pct_change_1,0)^2,20))`), `vol_of_vol`
  (`rolling_std_pop(volatility_20d,20)`, warmup efetivo 40), `volatility_regime` (tercis
  trailing shiftados de `volatility_20d`, janela 63 → 0/1/2), `trend_regime` (spread
  `ema_10-ema_50` com deadband `0.10*rolling_std_pop(spread.shift(1),63)` → -1/0/1),
  `stress_tail_return_flag` (`pct_change_1 <= rolling_quantile(pct_change_1.shift(1),63,0.10)`
  → 0/1).
- **Detalhes técnicos:**
  - **`clip(lower=0)` antes de `sqrt` (C8/I7):** Parkinson/GK/downside fazem
    `max(var, 0.0)` antes da raiz (paridade old; nunca `NaN` de raiz negativa).
  - **Helper `_rolling_quantile(seq, n, q)`** (interpolação linear estilo pandas default)
    para `stress_tail_return_flag` e a base dos tercis de `volatility_regime`.
  - **Causalidade dos regimes (I6):** thresholds (`q33`/`q66`/`deadband`/`tail_q10`) usam
    janela trailing **shiftada 1** (`.shift(1).rolling(63)`); o valor corrente é comparado
    ao threshold de `t-1..t-63`. Warmup 63. `volatility_20d`/`ema_10`/`ema_50` chegam como
    sequências de entrada (computadas pela 3.1 na 3.5; aqui são argumentos).
  - Erros (C7/C8): warmup → `None`; raiz negativa → clip; valores faltantes em
    `volatility_20d`/`ema` → `None` naquela posição.
- **Critério de aceite:**
  - `volatility_*` `>= 0` (ou `None`); `volatility_regime ∈ {0,1,2}` (ou `None`);
    `trend_regime ∈ {-1,0,1}`; `stress_tail_return_flag ∈ {0,1}` (ou `None` no warmup).
  - **Causalidade (I6):** anexar barras futuras não altera prefixo; thresholds usam janela
    shiftada (teste: alterar a barra `t` não muda o regime de `t` se o threshold só olha
    `t-1..t-63`; alterar barra futura `t+k` não muda nada em `t`).
  - `vol_of_vol` `None` antes da posição 40 (20 da entrada `volatility_20d` já consumidos +
    20 da janela std) — warmup efetivo documentado.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_derived_features_causal.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/derived_features.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): DerivedFeatures de volatilidade e regimes em Python puro [3.4/task-05]`

---

### Task 06 — domain: `DerivedFeatures` — sentimento dinâmico + fundamento derivado + YoY (`pct_change(252)`)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/feature_engineering/domain/services/derived_features.py`
  - `tests/unit/features/feature_engineering/domain/test_derived_features_causal.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:**
  Adicionar os grupos de sentimento dinâmico e fundamento derivado (incluindo o YoY deferido
  da 3.3). Sentimento: `sentiment_lag_1/3/5` (`shift(n)`), `sentiment_ema`
  (`ewm(span=10, adjust=False)`, recursivo `alpha=2/11`), `sentiment_surprise`
  (`sentiment_t - rolling_mean(sentiment.shift(1),5)`), `sentiment_x_volatility`
  (`sentiment * volatility_20d`), `sentiment_x_volume` (`sentiment * volume`). Fundamento:
  `net_margin` (`_safe_ratio(net_income, revenue)`), `leverage_ratio`
  (`_safe_ratio(total_liabilities, total_shareholder_equity)`), `cashflow_efficiency`
  (`_safe_ratio(operating_cash_flow, revenue)`), `revenue_yoy_growth`
  (`pct_change(revenue, 252, fill_method=None)`), `net_income_yoy_growth`
  (`pct_change(net_income, 252, fill_method=None)`).
- **Detalhes técnicos:**
  - **`_ewm(seq, span, adjust=False)`** recursivo: `y_0 = x_0`; `y_t = alpha*x_t +
    (1-alpha)*y_{t-1}`, `alpha = 2/(span+1)`; propaga `None` antes do primeiro valor válido
    (paridade `ewm(adjust=False).mean()`). Warmup do `sentiment_ema` = 1 (verbatim old).
  - **YoY (ADR 3.3.0002):** `_pct_change(seq, 252, fill_method=None)` → `None` nas 252
    primeiras posições; opera sobre a série diária as-of (forward-filled na 3.5; aqui é
    sequência de entrada). Tag `reported_date_asof`, warmup 252.
  - **`paridade lag==shift`:** `sentiment_lag_n(seq)[t] == seq[t-n]` (e `None` em
    `t<n`) — teste direto.
  - Erros: `_safe_ratio` → `None` em denom `0`/`None`/`NaN` (C6); warmup → `None` (C7).
- **Critério de aceite:**
  - `sentiment_lag_n` == `shift(n)` posição a posição (paridade lag==shift); `None` antes de `n`.
  - `net_margin`/`leverage_ratio`/`cashflow_efficiency` = `None` quando denom é `0`/`None`.
  - **YoY (A5/A6):** `revenue_yoy_growth`/`net_income_yoy_growth` = `None` antes da posição
    252; valor em 252 bate com `seq[252]/seq[0]-1`.
  - **Causalidade (I6):** anexar barras futuras não altera prefixo para todos os grupos.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/test_derived_features_causal.py -v
  uv run mypy --strict src/financial_forecasting/features/feature_engineering/domain/services/derived_features.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(feature-engineering.domain): DerivedFeatures de sentimento, fundamento e YoY em Python puro [3.4/task-06]`

---

### Task 07 — test: bateria transversal de causalidade, rejeição-sem-contrato e hash

- **Arquivos a modificar:**
  - `tests/unit/features/feature_engineering/domain/test_derived_features_causal.py`
  - `tests/unit/features/feature_engineering/domain/test_feature_registry.py`
- **Arquivos a criar:** nenhum.
- **O que fazer:**
  Consolidar e fechar os invariantes da Stage com testes transversais que cruzam VO +
  registry + derivadas, garantindo que todos os critérios de aceite do concept §11 ficam
  cobertos. Não introduz código de produção; só endurece a malha de testes.
- **Detalhes técnicos (mapa para concept §11 / §5):**
  - **A3 / I2 (rejeição):** parametrizar a construção de `FeatureSpec` com tag inválida e
    com `tft_typing` inválido → `ValueError`; afirmar que o registry não tem nenhuma spec
    fora do contrato.
  - **A4 / I5 (hash):** mesmo set → mesmo hash; reordenar inserção → mesmo hash; perturbar
    **cada campo** de um spec (loop sobre os campos) → hash diferente.
  - **A6 / I6 (causalidade global):** teste único parametrizado que, para **toda** função
    de `DerivedFeatures`, prova prefixo estável ao anexar barras futuras + ranges de
    flags/regimes/volatilidades + `shift>0` (nenhum shift negativo).
  - **A7 / I3 (tft_typing):** se houver features de calendário no registry → `known`; todas
    as demais → `unknown`; afirmação sobre o conjunto inteiro.
  - **A5 (YoY):** reafirmar `None` antes de 252 no contexto da bateria.
- **Critério de aceite:**
  - Todos os itens A1–A7 do concept §11 têm pelo menos um teste verde apontando para eles
    (tabela invariante↔teste em §3 fecha 100%).
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/features/feature_engineering/domain/ -v
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `test(feature-engineering.domain): bateria transversal de causalidade, rejeicao-sem-contrato e hash [3.4/task-07]`

---

### Task 08 — gate: pureza (import-linter/check_layout) + `make check` + cobertura `>= 90%`

- **Arquivos a modificar:**
  - `.importlinter` (somente se o contrato `domain-purity` não cobrir os novos módulos —
    normalmente já cobre o BC inteiro; verificar, não inflar).
- **Arquivos a criar:** nenhum (ou ADR `3_4_NNNN-*.md` apenas se uma decisão não-trivial
  surgir na execução — ex.: promover `sentiment_lag_*` para `lagged_causal`).
- **O que fazer:**
  Rodar o gate agregado da Stage e provar pureza. Confirmar que os três módulos novos
  (`feature_spec.py`, `feature_registry.py`, `derived_features.py`) importam **só stdlib**
  e que `domain-purity` + `check_layout.py` reprovam vazamento (I1/A8). Garantir cobertura
  `>= 90%` dos módulos de 3.4 e `make check` verde.
- **Detalhes técnicos:**
  - **Prova de pureza (A8/I1):** `grep` por `import numpy|import pandas|import torch|
    pydantic|sqlalchemy` nos três módulos deve dar vazio; import-linter `domain-purity`
    verde (padrão provado por quebra revertida na 3.1 Task 08).
  - **Cobertura (A9):** `make test-cov`; se algum ramo de `_safe_ratio`/clip/warmup ficar
    descoberto, adicionar caso na Task de teste correspondente (volta a 04–07; não criar
    teste novo na 08 fora do escopo).
  - Não tocar `IndicatorSpec`/`indicator_registry_hash`/contratos da 3.1 (D2 — coexistência
    sem reescrita; absorção física é da 3.5).
- **Critério de aceite:**
  - `make check` verde (ruff + mypy --strict + import-linter + `check_layout`).
  - `make test-cov` ≥ 90% nos módulos de 3.4.
  - `grep` de libs proibidas nos três módulos: vazio.
- **Comando de verificação:**
  ```bash
  make check
  uv run pytest tests/unit/features/feature_engineering/domain/ -v
  make test-cov
  uv run lint-imports
  ```
- **Commit sugerido:** `chore(feature-engineering.domain): gate de pureza e cobertura da Stage 3.4 [3.4/task-08]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit `stage 3.4: complete`
> (feito pelo **orquestrador**, não por esta sessão) e ser mergeada.

### Verificações automatizadas
```bash
make check                # ruff + mypy --strict + import-linter + check_layout + testes
uv run pytest tests/unit/features/feature_engineering/domain/ -v
make test-cov             # cobertura >= 90% dos módulos de 3.4
uv run lint-imports       # contrato domain-purity verde
```

### Mapeamento invariante ↔ teste

| Invariante / Critério (concept) | Teste / verificação |
|---|---|
| I1/A8 — pureza de domínio (stdlib-only) | import-linter `domain-purity` + `check_layout.py` + grep de libs (Task 08) |
| I2/A3/C4 — tag de causalidade obrigatória (rejeição) | `test_feature_spec.py` (C4) + `test_feature_registry.py` rejeição (Tasks 01/02/07) |
| I3/A7/C5 — `tft_typing` known/unknown obrigatório | `test_feature_spec.py` (C5) + cobertura tft_typing em `test_feature_registry.py` (Tasks 01/03/07) |
| I4/C3/A1 — `family` de 4 valores | `test_feature_spec.py` (C3) + cobertura de famílias `test_feature_registry.py` (Tasks 01/03) |
| I5/A4 — `feature_set_hash` determinístico/sensível | `test_feature_registry.py` hash estável/ordem/perturbação (Tasks 02/07) |
| I6/A6 — causalidade das derivadas (futuro não altera passado, shift>0, janelas shiftadas) | `test_derived_features_causal.py` prefixo estável + ranges + shift (Tasks 04/05/06/07) |
| I7/A5 — warmups verbatim + efetivo + YoY 252 | `test_feature_registry.py` warmups + `test_derived_features_causal.py` YoY `None`<252 + `vol_of_vol`=40 (Tasks 03/05/06) |
| A1/C1/C2 — `FeatureSpec` frozen, `name`/`warmup` válidos | `test_feature_spec.py` (Task 01) |
| A2 — `FEATURE_SPECS` imutável cobre todas as features | `test_feature_registry.py` MappingProxy + cobertura de chaves (Tasks 02/03) |
| C6/C8 — `_safe_ratio`/clip antes de sqrt | `test_derived_features_causal.py` (Tasks 04/05/06) |
| C7 — warmup → `None` (paridade `min_periods`) | `test_derived_features_causal.py` (Tasks 04/05/06) |
| A9 — gates verdes + cobertura ≥ 90% | `make check` + `make test-cov` (Task 08) |

### Verificações funcionais
- [ ] `python -c "from financial_forecasting.features.feature_engineering.domain.services.feature_registry import FEATURE_SPECS, feature_set_hash; print(len(FEATURE_SPECS), feature_set_hash())"` imprime a contagem total (base + ~38 derivadas) e um hash hex estável entre execuções.
- [ ] Importar `DerivedFeatures` e rodar `log_return_1d`/`revenue_yoy_growth` sobre sequências de exemplo devolve tuplas com `None` nos warmups (1 e 252).

### Checklist de fechamento da Stage
- [ ] Todas as Tasks (01–08) commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Cobertura `>= 90%` nos módulos de 3.4 (`make test-cov`)
- [ ] ADRs novos (se houve decisão na execução) em `status: accepted`
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
- [ ] **NÃO** fazer commit `stage 3.4: complete` nem marcar `roadmap.md` `done` — é do orquestrador, após auditoria independente

## 4. Ordem de dependência entre Tasks

A ordem listada em §2 já respeita as dependências. Não-óbvio:

```
Task 01 (FeatureSpec VO)
   └─► Task 02 (FeatureRegistry base + hash)
          └─► Task 03 (specs das derivadas no registry)
Task 04 (DerivedFeatures preço/liquidez)         ─┐
   └─► Task 05 (volatilidade/regimes)              │ (mesmo módulo, acumulativo)
          └─► Task 06 (sentimento/fundamento/YoY) ─┘
Task 03 + Task 06  ─► Task 07 (bateria transversal)  ─► Task 08 (gate)
```

- Tasks 04–06 dependem só dos helpers puros (criados na 04), **não** do registry — podem em
  tese ser paralelas à 02–03, mas são sequenciais no mesmo arquivo `derived_features.py`.
- Task 07 cruza registry (03) + derivadas (06); Task 08 fecha o gate sobre tudo.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Off-by-one na tradução pandas → puro (shift/min_periods/ddof/quantile) | Warmup efetivo documentado por feature (I7); teste de paridade contra valores conhecidos do old + teste append-future-bars; `_rolling_quantile` com interpolação linear conferida contra pandas default num caso pequeno |
| `ewm(adjust=False)` divergir do pandas | Conferir recursão `alpha=2/(span+1)` contra 2-3 valores calculados à mão; `sentiment_ema` warmup=1 verbatim |
| Vazamento de lib no domínio | import-linter `domain-purity` + `check_layout` (Task 08, I1) + grep de libs; padrão já provado na 3.1 |
| Cobertura < 90% em ramos de erro (`_safe_ratio`/clip/warmup) | Adicionar casos nas Tasks 04–06 (não criar teste fora de escopo na 08) |
| Ambiguidade de tag para `sentiment_lag_*` (`trailing_window_causal` old vs `lagged_causal` novo) | Decidir na execução, registrar `[decision]` em §7, ajustar teste de tag; não bloqueia |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (§4 contratos, §5 invariantes, §11 critérios)
- [`../../overview.md`](../../overview.md) — §3 escopo, §11 ADRs de fundação
- [`../../roadmap.md`](../../roadmap.md) — Stage `3.4-feature-registry-and-derived`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs desta Stage: `3_4_0001` (oráculo puro), `3_4_0002` (superset + tft_typing), `0_0_0016` (4 famílias)
- ADRs relacionados: `3.1.0001`, `3.3.0002`, `0.0.0018`, `0.0.0021`, `1.4.0001`
- Skills aplicáveis: `ddd-tactical-patterns` (VO vs service), `task-ordering-hex` (ordem mono-layer), `pytest-with-fakes`/`hex-arch-python` (pureza), `dmls-ch04-feature-engineering-decisions` (anti-leakage)
- Old: `src/infrastructure/schemas/feature_registry.py` (FeatureSpec + hash), `src/use_cases/build_tft_dataset_use_case.py:146-285` (derivadas), `src/use_cases/train_tft_model_use_case.py:1216` (known/unknown hardcoded)
- 3.1: `src/financial_forecasting/features/feature_engineering/domain/services/indicator_spec.py` (molde/postura de hash)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável após `status:
> done`.** Corrida autônoma overnight (ADR `0.0.0050`): **não perguntar** — decidir com
> julgamento, registrar `[decision]`/`[finding]`/`[deviation]` e seguir.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Decisão:** <o que foi decidido>          <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
- `[finding]` — gap/observação a tratar em **próxima Stage** (inclui direção + Stage candidata).
- `[deviation]` — ajuste pequeno vs. o plano original (o que mudou e por quê).

<!-- END: post-execution -->
