---
title: Visão Geral — Previsão Probabilística de Retornos Financeiros (TFT)
description: Business briefing autocontido do projeto que caracteriza a calibração probabilística de um TFT asset-specific sobre retornos diários (piloto AAPL), com comparação honesta a baselines e análise de contribuição de features
when-use: Consultar no início de qualquer nova sessão de detalhamento ou planejamento; é o livro-verdade base do projeto inteiro
keywords: [overview, briefing, tft, calibracao, conformal, pinball, medalhao, clean-architecture, forecasting]
status: draft
created_at: 2026-06-22
updated_at: 2026-06-22
project_name: Previsão Probabilística de Retornos Financeiros (TFT)
stakeholders:
  - Autor / Decisor / Pesquisador: Marcelo Santos (TCC, Eng. Mecatrônica — UFSC)
  - Orientação acadêmica / banca
---

# Visão Geral — Previsão Probabilística de Retornos Financeiros (TFT)

> **Este documento é o livro-verdade base do projeto.** Cada decisão registrada aqui foi tomada por análise própria dos trade-offs (não por herança). A deliberação completa (alternativas consideradas e por que descartadas) vive nos ADRs listados na §11. Mudanças estruturais (escopo, objetivos, hipóteses) exigem revisão consciente.

## 1. Resumo executivo

Estudo que **caracteriza em que medida um Temporal Fusion Transformer (TFT) específico por ativo produz previsões probabilísticas calibradas de retornos diários** — piloto **AAPL**, horizontes h+1 e h+7 (h+30 suplementar) — comparando-o de forma honesta a uma hierarquia de baselines e medindo a contribuição relativa de famílias de features. O objeto científico central é a **distribuição preditiva** (calibração e sharpness), não a acurácia pontual: para retornos diários de ações líquidas o componente previsível da média é minúsculo (R² OOS ~0,1–1%), e a calibração probabilística é o resultado que tem sinal real e é academicamente defensável. **Refutação é resultado válido.** O projeto prioriza, acima de tudo, **modularização, arquitetura limpa e rastreabilidade/auditoria** — com a metodologia estatística implementada como domínio puro testável e apoiada em bibliotecas reconhecidas validadas contra oráculo.

## 2. Contexto de negócio

### Problema
Existe uma implementação anterior funcional deste estudo, mas que degradou em **dívida arquitetural** a ponto de ficar inauditável: regra de dependência não enforçada (lógica científica acoplada à camada de dados), ausência de ponto único de composição (mudar uma dependência exigia editar dezenas de arquivos), módulos-deus, e uma camada estatística inteiramente artesanal (incluindo um bug conhecido). Corrigir um erro passou a exigir alterar vários pontos — o que inviabiliza tanto a manutenção quanto a defesa acadêmica das evidências.

### Oportunidade
Reconstruir o estudo do zero, repensando **criticamente cada decisão** (não reaproveitando escolhas por inércia) e impondo arquitetura limpa **verificada por ferramenta**. Isso entrega simultaneamente rigor acadêmico (evidência rastreável e reproduzível) e velocidade (uso intensivo de bibliotecas confiáveis no lugar de cálculo artesanal). A estrutura de trabalho por Stages permite que cada decisão seja pesquisada e fundamentada em sua própria sessão.

### Estado atual
O alvo é uma reconstrução greenfield. Apenas os **dados brutos** (candles, news, fundamentals de AAPL) de uma coleta anterior são considerados insumo reaproveitável (camada bronze imutável); tudo a jusante é re-derivado e o modelo é **re-treinado** em código novo. Resultados confirmatórios anteriores servem apenas como **oráculo de equivalência/regressão**, com tolerância declarada — nunca como autoridade de decisão.

## 3. Escopo

### Dentro do escopo
- Pipeline medalhão completa (bronze → silver → gold) em arquitetura hexagonal, com domínio puro e fronteiras verificadas por import-linter.
- Re-derivação de features e **re-treino** do TFT (reusa apenas os dados brutos).
- **Modelo estudado:** TFT asset-specific em modo quantílico (grade densa ~7–9 quantis), com arquitetura **multi-asset-ready**.
- **Comparadores:** hierarquia de baselines {naive, estatístico forte (quantis rolantes), modelo-ML (gradient boosting quantílico)}.
- **Calibração:** caracterização nativa rica (objeto primário) + **conformal prediction (CQR)** como benchmark comparativo de cobertura.
- **Camada estatística confirmatória:** pinball (primária) + CRPS (complementar), DM (HAC/HLN, one-sided) + Holm + MCS, PICP + Christoffersen, MPIW/Winkler, VaR descritivo backtestado — como serviços de domínio sobre value objects, apoiados em bibliotecas + oráculo.
- **Pré-registro** imutável hasheado; **scorecard confirmatório** mecânico; tracking (MLflow) e rastreabilidade por `run_id`/fingerprints/hash de pré-registro.
- **API de inferência fina** (FastAPI) + explicabilidade (VSN, permutação, ablação).

### Fora do escopo (explicitamente)
- Rodar ativos além de AAPL agora (a arquitetura fica pronta; a execução não).
- Trading, portfólio, backtesting financeiro, intraday.
- Inferência causal indicador→retorno; qualquer claim de "bater o mercado".
- Reaproveitar dados derivados ou checkpoints de implementações anteriores.
- **Candidatas a trabalho futuro (descartadas por ora):** features de cripto/derivativos e microestrutura (funding rate, long/short ratio, open interest, fear&greed, CVD, order rate, order book) — implicam ativo cripto-perpétuo e/ou dados intraday, fora do enquadramento atual (ação, diário).

### Premissas
- **ASSUM-1:** os dados brutos de AAPL de coleta anterior são íntegros e podem ser reusados como bronze imutável.
- **ASSUM-2:** o ambiente AMD ROCm permite re-treinar o TFT com custo aceitável para o cohort confirmatório de AAPL.
- **ASSUM-3:** chaves de API (Alpha Vantage) seguem disponíveis para re-ingestão pontual de bronze, se necessário.
- **ASSUM-4:** equivalência com evidências anteriores é aferida com **tolerância declarada** (não bit-identical), por ser re-treino com nova stack numérica.
- **ASSUM-5:** orientador/banca aceitam refutação como resultado científico válido.

## 4. Objetivos

### Objetivos gerais
- Caracterizar a **calibração probabilística** (e sharpness) das previsões de retorno do TFT, por horizonte.
- Comparar honestamente o TFT a uma hierarquia de baselines em uma proper scoring rule, com inferência estatística controlada.
- Caracterizar a **contribuição relativa das famílias de features**.
- Entregar tudo sob **arquitetura limpa, modular e rastreável**, com a ciência reproduzível a partir de dados persistidos.

### Hipóteses
- **H1 — Calibração (objeto primário + gate).** O candidato produz previsões probabilísticas calibradas de retornos diários, caracterizadas de forma rica (cobertura marginal por quantil, PICP, reliability, sharpness, cobertura condicional via Christoffersen) para ≥1 horizonte dentro de bandas pré-registradas. A calibração é também **gate de elegibilidade** para H2 (não se compara skill de modelo mal-calibrado).
- **H2 — Skill relativo (alvo honesto).** Em **pinball** (DM + Holm), o candidato é comparado a uma hierarquia pré-declarada de baselines {naive, estatístico forte, modelo-ML quantílico}. Espera-se superar os naive; o **interesse científico** é superar ou empatar com os fortes; pertencer ao **MCS** ("não rejeitado como inferior") é evidência complementar; **não-dominância é resultado válido**.
- **H3 — Contribuição de features (descritiva).** A contribuição das famílias (preço, técnico, sentimento, fundamento) é **heterogênea entre horizontes**, detectável de forma consistente em **≥2 de 3 métodos** (VSN, permutação, ablação). Sem claim causal.

### Critérios de sucesso
- **Fronteiras enforçadas:** import-linter + mypy --strict + cobertura ≥ 90% verdes em CI; **domínio sem pandas/pyarrow/torch** (build falha se violado).
- **Estatística defensável:** todo teste/métrica confirmatório validado contra **oráculo** (R `dm.test`/`rugarch`, fixtures analíticas, pacote de referência).
- **Reprodutibilidade:** artefatos de decisão reconstruíveis a partir de dados persistidos **sem re-treino**; cada decisão rastreável por `run_id` + `config_signature` + `split_fingerprint` + hash do pré-registro.
- **Veredito sem cherry-picking:** decisão por **scorecard pré-registrado mecânico** (métrica primária = pinball + gate de calibração + DM/Holm + MCS), com as demais métricas como perfil comparativo que **nunca** troca o veredito.
- **Refutação** documentada honestamente quando ocorrer.

## 5. Stakeholders

| Papel | Nome / Área | Interesse principal |
|---|---|---|
| Autor / Decisor / Pesquisador | Marcelo Santos (UFSC) | Pipeline limpa, auditável e academicamente defensável; resultado reprodutível para o TCC |
| Orientação acadêmica / banca | — | Rigor metodológico, rastreabilidade das evidências, honestidade sobre limites (incl. refutação) |

## 6. Restrições

### Técnicas
- **Python 3.12+**, **uv**, **Makefile**; arquitetura **hexagonal + vertical slices**; gates **import-linter + mypy --strict + ruff + pytest + cobertura ≥ 90%**.
- Persistência **Parquet + DuckDB**; **sem Postgres**. Tracking **MLflow** (backend SQLite local).
- **torch** (AMD ROCm) + **pytorch-forecasting** (TFT quantílico); **LightGBM** (GBM quantílico); **statsforecast** (baselines); **MAPIE** (conformal).
- **FastAPI fino** só como adapter de entrada (inferência/explicabilidade); sem servir treino.
- Domínio **puro** (stdlib only): métricas/testes como serviços de domínio sobre value objects; bibliotecas vivem em adapters.

### Negócio
- Projeto **acadêmico (TCC)**, recurso essencialmente solo, com prazo de defesa.
- Dados restritos a **free tiers** (Alpha Vantage); hardware local (AMD GPU) — custo de re-treino limita o cohort a AAPL.

## 7. Abordagem geral

Reconstrução incremental seguindo o **fluxo medalhão** (bronze → features/silver → modelagem/treino → gold/estatística → inferência/relatório), cada etapa com gate humano. O princípio organizador é **enforcement-as-test**: as regras de arquitetura viram fitness functions (import-linter espelhando o LAYOUT, mypy strict, checagem de camadas) e a corretude estatística vira **contratos por unidade + oráculo** (fixtures analíticas + biblioteca/R), substituindo o snapshot global "byte-idêntico" que entrincheirava o monólito.

O **domínio** carrega a metodologia como serviços puros sobre value objects tipados (ex.: `PairedLossSeries`, `QuantileForecast`, `CoverageSeries`) com invariantes (alinhada, 1 obs/unidade, monotonicidade). **Bibliotecas confiáveis** entram como adapters por trás de portas: `arch` (MCS, bootstrap, VaR), `statsmodels` (Holm, HAC), `sklearn`/`scoringrules` (pinball, Winkler/CRPS), `statsforecast` (baselines), `LightGBM` (GBM quantílico), `MAPIE` (CQR), `pandas`+`duckdb` (transformações e as-of joins), `pandera` (contratos de schema), `pandas-ta-classic`/TA-Lib (indicadores, validados contra o paper), FinBERT (sentimento, version-pinned), `pydantic-settings` + `mlflow` (config + tracking). Para testes sem lib canônica em Python (Diebold-Mariano, Christoffersen, Kupiec), a postura é **implementação própria fina atrás de porta + golden-tests contra oráculo R + fixtures**.

A disciplina anti-p-hacking é estrutural: **pré-registro imutável hasheado** antes do confirmatório (o hash é a âncora), métricas **nunca agregadas entre horizontes**, alinhamento OOS estrito por `target_timestamp`, dedup operationally-latest, e **gate de degeneração** de quantis separado do guardrail de monotonicidade.

## 8. Riscos conhecidos

| Risco | Impacto | Mitigação inicial |
|---|---|---|
| Re-treino não reproduz evidência anterior (nova stack numérica) | médio | Equivalência por **tolerância declarada** (ASSUM-4), não bit-identical; deltas documentados |
| Libs de nicho frágeis (DM, Christoffersen, Kupiec) | médio | Wrapper próprio atrás de porta + **oráculo R** + pin de versão + ADR de proveniência |
| Conformal frágil em série temporal (permutabilidade violada) | médio | Reportar cobertura **empírica** (não "garantida") + 4 invariantes (calib set dedicado, por fold/horizonte, embargo, linguagem) |
| `pandas-ta` com fonte apagada / sem manutenção | alto | Migrar para `pandas-ta-classic`/TA-Lib + **validar cada indicador contra o paper** + teste de leakage |
| Escopo inflar (multi-asset, cripto, intraday, trading) | alto | Gates de escopo; multi-asset só **ready**; cripto/microestrutura como trabalho futuro |
| Custo de re-treino (GPU) | médio | Cohort pequeno AAPL; sweeps exploratórios separados do confirmatório |
| Métrica reimplementada divergir do correto sem detecção | alto | Contratos por unidade + oráculo + gate de degeneração separado do guardrail |

## 9. Glossário

- **Calibração / sharpness:** quão bem os quantis previstos batem com a frequência empírica (calibração) e quão estreitos são os intervalos (sharpness).
- **Pinball loss:** proper scoring rule para quantis (métrica primária do claim). **CRPS:** score distributivo agregado (complementar).
- **PICP / MPIW:** cobertura do intervalo de predição / largura média do intervalo.
- **Conformal prediction (CQR):** método que recalibra intervalos para atingir cobertura-alvo; aqui usado como **benchmark** comparativo, não como entrega primária.
- **DM / MCS / Holm:** Diebold-Mariano (igualdade de acurácia preditiva) / Model Confidence Set / correção de múltiplas comparações.
- **Medalhão (bronze/silver/gold):** bronze = raw imutável; silver = fatos atômicos rastreáveis por `run_id` (fonte da verdade); gold = decisão reconstruível sem re-treino.
- **Walk-forward com purga+embargo:** validação temporal que imita produção, separando treino/val/calibração/teste sem vazamento.
- **Pré-registro / scorecard mecânico:** config imutável hasheada antes do confirmatório + regra de veredito aplicada mecanicamente (anti cherry-picking).
- **Value object / oráculo:** objeto tipado com invariantes sobre o qual a estatística é função pura / fonte de corretude (paper + fixture + lib/R).

## 10. Referências

- Papers-âncora: Diebold-Mariano 1995; Harvey-Leybourne-Newbold 1997; Hansen-Lunde-Nason 2011 (MCS); Holm 1979; Koenker-Bassett 1978 + Gneiting 2011 (pinball); Gneiting-Raftery 2007 (interval/Winkler score, CRPS); Christoffersen 1998; Kupiec 1995; Khosravi et al. 2011 (PICP/MPIW); Romano-Patterson-Candès 2019 (CQR); Barber et al. 2023 (conformal sob drift); Chernozhukov et al. 2010 (rearranjo de quantis); López de Prado 2018 (purged/embargoed CV); Lim et al. 2021 (TFT); Gu-Kelly-Xiu 2020 (previsibilidade de retornos); White 2000 / Romano-Wolf 2005 (inferência seletiva).
- Bibliotecas: `arch`, `statsmodels`, `scikit-learn`, `scoringrules`, `statsforecast`, `LightGBM`, `MAPIE`, `pandas`, `duckdb`, `pyarrow`, `pandera`, `pandas-ta-classic`/TA-Lib, `pytorch-forecasting`, `pydantic-settings`, `mlflow`, FinBERT.
- Pipeline/arquitetura do template: `boilerplate/layout-files/docs/{PIPELINE,LAYOUT,CONVENTIONS,GIT-WORKFLOW}.md`.

## 11. Decisões-chave e ADRs a registrar

> Decisão + razão curta abaixo; a deliberação completa (alternativas e trade-offs) vira o ADR indicado (`docs/adr/0_0_NNNN-*`).

### Científicas
| Decisão | Razão | ADR |
|---|---|---|
| Enquadramento = calibração probabilística + contribuição de features (não acurácia pontual) | Média de retorno diário é quase imprevisível; a distribuição preditiva tem sinal real e é defensável | `0_0_0002` |
| Evidência por candidato único all-features + contribuição descritiva | Seleção de feature-set por OOS infla falsos-positivos (White; Romano-Wolf); design confirmatório mais limpo | `0_0_0003` |
| TFT como objeto + baseline-modelo forte de quantis (GBM) | Eleva a barra de H2; se o simples calibrar tão bem, é resultado honesto | `0_0_0004` |
| H1 = calibração como objeto primário caracterizado + gate de elegibilidade | É o objeto central do estudo; não faz sentido comparar skill de modelo mal-calibrado | `0_0_0005` |
| H2 = hierarquia de baselines com alvo honesto (superar naive; empatar/superar fortes; MCS) | Mais informativo e defensável que "superior a todos"; não-dominância é achado válido | `0_0_0006` |
| H3 = heterogeneidade entre horizontes, ≥2/3 métodos, descritiva | Específica, falseável, robusta a artefato de método | `0_0_0007` |
| Horizontes h+1/h+7 primários + h+30 suplementar | Poder estatístico em curto prazo; h+30 tem poucas amostras; ≥2 horizontes viabilizam H3 | `0_0_0025` |
| Veredito por scorecard pré-registrado mecânico | Defesa anti cherry-picking; separa vencedor primário de perfil comparativo | `0_0_0026` |

### Metodologia estatística
| Decisão | Razão | ADR |
|---|---|---|
| Quantis nativos como objeto (H1) + CQR como benchmark; 4 invariantes; variante deferida à Stage | CQR é a pergunta óbvia em estudo de calibração; invariantes evitam vazamento/fragilidade; variante pré-registrada | `0_0_0008` |
| Pinball primária + CRPS complementar | Pinball casa com o modelo quantílico e com DM; CRPS agrega o distributivo se a grade densificar | `0_0_0009` |
| Inferência frequentista DM(HAC/HLN, one-sided) + Holm + MCS, lib + oráculo | Padrão da literatura, backed por `arch`/`statsmodels`, validável; família pequena → Holm FWER | `0_0_0010` |
| Pré-registro imutável + invariantes (sem agregar horizontes, alinhamento OOS, dedup, gate de degeneração) | Espinha anti-p-hacking e de auditabilidade | `0_0_0011` |

### Modelagem e dados
| Decisão | Razão | ADR |
|---|---|---|
| Grade densificada ~7–9 quantis | Habilita CRPS/VaR/calibração mais ricos a custo baixo | `0_0_0012` |
| Walk-forward com purga+embargo + calib set dedicado | Exigido pelo conformal; imita produção; evita vazamento | `0_0_0013` |
| TFT asset-specific, multi-asset-ready | Fiel à identidade da pergunta; arquitetura preparada sem inflar o piloto | `0_0_0014` |
| Medalhão bronze/silver/gold (terminologia limpa) | Espinha de rastreabilidade/reprodutibilidade | `0_0_0015` |
| 4 famílias de features (preço, técnico, sentimento, fundamento) | Necessárias para H3 e diferencial; reusa bronze | `0_0_0016` |
| FinBERT version-pinned | Padrão de sentimento financeiro; corrige a irreprodutibilidade (sem pin) | `0_0_0017` |
| Anti-leakage não-negociável (causal + as-of backward + known/unknown + embargo); alvo = log-retorno | Validade temporal é pré-condição de qualquer claim | `0_0_0018` |

### Arquitetura e ferramentas
| Decisão | Razão | ADR |
|---|---|---|
| Hexagonal pleno enforçado por ferramenta | Cura a dor "mexer num ponto quebra vários"; impede regressão arquitetural | `0_0_0019` |
| Estatística como serviços de domínio puros sobre value objects | Testável/auditável isoladamente; desacopla a ciência da camada de dados | `0_0_0020` |
| Testes de regressão por unidade + oráculo (não snapshot global) | Barato de refatorar e diretamente auditável; evita entrincheirar o monólito | `0_0_0021` |
| Engine de dados = pandas + duckdb | Compatível com libs de modelo + SQL rápido e as-of joins sobre Parquet | `0_0_0022` |
| Tracking = MLflow local (SQLite) | Compara sweeps com UI, sem SaaS; complementa run_id/silver | `0_0_0023` |
| Indicadores = pandas-ta-classic, validados contra o paper na implementação | Resolve supply-chain do pandas-ta; corretude conferida contra a fórmula canônica | `0_0_0024` |
