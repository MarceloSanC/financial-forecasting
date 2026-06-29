---
title: Decision Ledger — Corrida Autônoma Overnight (Stages 1.1→4.3)
description: Saída da fase 1 (rodada de perguntas) antes da corrida autônoma. Registra as decisões fechadas com humano e as decisões que o Claude tomará sozinho (com base concreta) durante a corrida. Governado pelo ADR 0.0.0050.
when-use: Ler antes de implementar qualquer stage 1.1→4.3 no modo autônomo; cada decisão 🤖 vira um ADR formal na stage correspondente.
keywords: [autonomous, overnight, decisions, prereg, fase-1, ledger]
status: accepted
created_at: 2026-06-29
updated_at: 2026-06-29
---

# Decision Ledger — Corrida Autônoma (1.1→4.3)

Saída da **fase 1 (rodada de perguntas)** da corrida autônoma overnight, governada pelo
[ADR 0.0.0050](./adr/0_0_0050-autonomous-overnight-mode.md). Fonte de referência factual:
overview §11 (24 ADRs de fundação) + repo anterior em
`/home/marcelo/Code/financial-time-series-forecasting` (implementação de referência).

> **Regra:** cada item 🤖 abaixo vira um **ADR formal** (`status: accepted`) na stage onde é
> implementado, com opções/trade-offs/reversibilidade, conforme a política de decisão autônoma.
> A grade reusa **só dados brutos** (`raw/`); features são **re-derivadas** (overview §3); os
> `processed/`/`analytics/` antigos servem como **oráculo de regressão**, não como entrada.

## A. Decisões FECHADAS com o humano (fase 1 — imutáveis nesta corrida)

| # | Decisão | Escolha | Razão |
|---|---|---|---|
| H-1 | Representação dos quantis no silver (4.1/4.3) | **Long/agnóstico à grade** — `(quantile_level, value_raw, value_guardrail)`; o schema NÃO amarra a grade densa | Mantém 1–4 desbloqueado sem pinar a grade; a grade exata ~7–9 (overview ADR 0_0_0012) fica para o Step 5; fácil de trocar |
| H-2 | Conjunto de indicadores técnicos (3.1) | **Replicar os 11 do repo antigo + validar fórmulas** (RSI-14 Wilder, MACD 12/26/9, EMA 10/50/100/200, volatilidade 20d, candle range/body); sem expansão | Reconstrução honesta; expandir agora é scope creep; nenhum paper foi citado como fonte no old — a fonte-da-verdade é o set empírico antigo + fórmula canônica |
| H-3 | Fallback as-of de fundamentos (3.3) | **Manter `reported_date` OU `fiscal_date_end + 45 dias`** (pré-registrar) | Conservador entre prazos SEC (10-Q 40d / 10-K 60–90d); anti-leakage já validado no old (17/81 usaram fallback, sem leakage); reversível |

## B. Decisões que o Claude tomará sozinho (🤖 — base concreta + ADR na stage)

| Stage | Decisão | Direção pré-declarada | Base factual |
|---|---|---|---|
| 1.4 | Canonicalização do hash (RunId/fingerprints) | `sha256` sobre JSON ordenado compacto + datas ISO8601 + **arredondar floats** (endurecer determinismo na nova stack) + `None`→null; stripar chaves voláteis do config_signature | old `analytics_store_schema.py` (replicar + hardening de float) |
| 1.5 | Settings/MLflow | pydantic-settings + composition_root + MLflow SQLite local (construir fresco — old não usava nenhum) | overview ADR 0022/0023 |
| 2.1 | Partição + schemas bronze | Hive `asset/[feature_set]/year`, append-only; pandera p/ candle/news/fundamental com colunas/dtypes do old | old `parquet_*` + `*_parquet_schema.py` |
| 2.3 | Endpoints Alpha Vantage | news + income/balance/cashflow (mesmos campos do old); dedup `article_id`; throttle free-tier | old fundamentals schema |
| 3.2 | FinBERT | `ProsusAI/finbert` + **pinar revisão (SHA)** — old não pinava (ADR 0017 manda); score `P(pos)-P(neg)`; média diária por dia de pregão | old `finbert_sentiment_model.py` (+ pin) |
| 3.3 | As-of engine | DuckDB ASOF backward (novo) portando a lógica do `merge_asof` antigo; invariante `effective_date <= date` | old `build_tft_dataset_use_case.py` |
| 3.4 | Conjunto de derivadas | Replicar as ~38 derivadas do old (log-returns, momentum, vol Parkinson/Garman-Klass, lags/interações de sentimento, ratios fundamentais), fórmulas verbatim; tagging known/unknown | old `feature_registry.py` |
| 4.1 | Tabelas silver no Step 4 | Definir as consumidas por 1–4: `dim_run`, `fact_config`, `fact_oos_predictions`, `fact_split_metrics`, `fact_failures`; **deferir** inference/feature_contrib/epoch p/ Steps 5/7 | old 13-tabelas (subset) |
| 4.3 | target_timestamp / grade | **Replicar a correção** do old ADR-0003 (R-20, opção d): `timestamp_utc = decision_day`; `target_timestamp_utc = dataset_timestamps[decision_idx + h]`; `target_return` backward; guardrail monotônico; grade persistida no formato H-1 | old `multi_horizon_prediction_persister.py` + ADR-0003 |

## C. HALT (parar a corrida e aguardar humano)

Contradição com fonte superior (Overview > Roadmap > Concept), contrato externo irreversível
ambíguo, ou gate objetivo que não fecha. Step 5+ **não** é autônomo.
