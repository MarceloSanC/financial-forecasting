---
title: Pré-registro confirmatório AAPL — espelho legível
description: Espelho em linguagem simples do pré-registro confirmatório AAPL; o arquivo TOML de cada revisão é o canônico e este documento cita o hash completo de cada revisão
when-use: Ao ler o que o estudo confirmatório AAPL congelou (hipóteses, gate H1, regra H2, parâmetros, perfis, cegamento) ou ao conferir a âncora de uma revisão; nunca como fonte dos números que julgam (essa é o TOML)
keywords: [preregistration, pre-registro, aapl, confirmatory, h1-gate, h2, scorecard, anchor, blinding, espelho]
status: accepted
created_at: 2026-09-30
updated_at: 2026-10-06
---

# Pré-registro confirmatório AAPL — espelho

> **O TOML é canônico.** Os números e as regras que julgam o estudo vêm **só** de
> `config/preregistration/aapl_confirmatory-r<rev>.toml` (ADR 6.5.0001). Este
> documento explica cada valor em linguagem simples e cita, por revisão, o hash
> completo e o `preregistration_ref`; um teste (`test_preregistration_consistency.py`)
> recalcula o hash de todo arquivo de revisão e exige a citação aqui. Seções são
> **acrescentadas** por revisão, nunca reescritas (ADR 6.5.0001 item 6). Uma emenda
> é um arquivo novo `aapl_confirmatory-r<rev+1>.toml` com `amends`,
> `justification` e `blind_status` (ADR 6.5.0002).

## Revisão r0

- **Arquivo:** `config/preregistration/aapl_confirmatory-r0.toml`
- **`preregistration_ref`:** `aapl_confirmatory-r0-4526c437c296`
- **Hash completo (sha256, floats codificados exatamente):**
  `4526c437c2964eb5d38f634c4614074388ed4ce37c6f843c1780faa2ac8081b1`

### O que é julgado

- **Ativo e cohort:** AAPL; o cohort de treino confirmatório é referenciado pelo id
  `aapl_confirmatory-r0-665f45d9169a` e pelo hash completo
  `665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1` (Stage 5.5).
- **Realizado:** o `target_return` da grade de treino, com a impressão digital
  `00e4406dcd96658d557f7d4d86face9874fac42385e3cb182d54c5d2286695bd`.
- **Horizontes avaliados:** 1 e 7 sessões; o horizonte 30 é declarado **não
  avaliado** (não está no cohort).
- **Grade de quantis:** 0,02; 0,1; 0,25; 0,5; 0,75; 0,9; 0,98.
- **Candidato:** `tft_quantile` (seeds 1 a 10).
- **Comparadores por nível:** naive = `baseline_zero_return`,
  `baseline_historical_mean`; estatístico forte = `baseline_ar1`,
  `baseline_ewma_vol`, `baseline_historical_quantiles`; ML = `gbm_quantile`
  (seed 0). As baselines não têm seed. Todo modelo tem déficit de janela 0.
- **Regras nomeadas** (cada uma aceita só se o código a implementa; mudar a regra
  muda o hash): métrica primária = pinball médio na grade por horizonte; as
  secundárias são só perfil; DM unilateral "candidato com perda menor", retangular
  com lag h − 1, correção HLN com t de Student em T − 1 graus, variância ≤ 0 com
  h > 1 recalculada em h = 1 e registrada; MCS com a estatística `R` e bloco
  max(h, ⌈max b̂⌉); sem exclusões; seeds agregadas pela média das perdas e das
  contagens; forma do gate H1 e da árvore H2 versionadas (`…_v1`); sucesso do
  estudo = H1 não rejeitada em pelo menos um horizonte.

### Gate H1 (calibração do candidato)

- Linhas do candidato na amostra do próprio modelo, variante mascarada, cauda
  inferior τ = 0,1 e superior τ = 0,9; contagens médias entre as seeds.
- Passa se as duas bandas de Wilson a **97,5 %** por cauda contêm a taxa nominal e a
  degeneração média é **≤ 1 %** (limiar do pesquisador, ADR 6.5.0010).
- Sensibilidades (perfil, nunca veredito): banda a 95 %, LR_uc de 3 estados a 5 %,
  sub-séries DGT a 1 − 0,05/(2h), o gate recomputado na amostra comum.
- **Falsa reprovação do gate:** a probabilidade exata de reprovar um candidato
  calibrado é ≈ 5 % e depende do n medido; em n = 1 512 (tamanho previsto pela
  geometria do cohort, não medido) ela vale 0,0506. O scorecard declara o valor
  exato no n que medir.
- **Tamanho condicional (ADR 6.5.0007, Negative):** o gate abre a H2 quando não
  rejeita a calibração; pela lógica dos eventos, P(declarar H2 ∧ passar H1) ≤ α,
  mas o tamanho **condicional** a ter passado H1 não é garantido por fonte primária.

### Poder declarado (ADR 6.5.0010, P3)

Probabilidade exata de o gate reprovar sob cada cenário de desvio, pela multinomial
de três células; as taxas por cauda estão escritas no TOML (as de locação vêm do
modelo normal, `NormalDist`). Valores ilustrativos em n = 1 512 (geometria); o
scorecard recalcula no n = round(n̄) medido e, para h > 1, declara que o poder
assume hits independentes (otimista).

| Cenário | Papel | Taxa inferior | Taxa superior | Reprova em n = 1 512 |
|---|---|---|---|---|
| largura ±5 p.p. (cobertura 75 %) | primário | 0,125 | 0,125 | 0,9748 |
| largura ±5 p.p. (cobertura 85 %) | primário | 0,075 | 0,075 | 0,9888 |
| locação 0,2σ | primário | 0,06923 | 0,13973 | 0,9998 |
| largura ±3 p.p. (cobertura 77 %) | secundário | 0,115 | 0,115 | 0,6366 |
| largura ±3 p.p. (cobertura 83 %) | secundário | 0,085 | 0,085 | 0,6475 |
| locação 0,1σ | secundário | 0,08355 | 0,11869 | 0,7503 |

### Regra H2 e vencedor primário (ADR 6.5.0007; P4 do ADR 6.5.0010)

Por horizonte, só se o gate H1 passa: (i) Holm (α 0,05, família dos seis
comparadores) rejeita contra **todo** naive; (ii) o candidato está no MCS primário
(estacionário, α 0,10, 1 000 réplicas, seed 127) **ou** Holm rejeita contra todo
forte (estatístico forte e ML). Desfechos: sem habilidade sobre o naive; supera só o
naive; supera o naive e empata com os fortes; supera o naive e os fortes. O vencedor
primário é o candidato se H1 ∧ (i) ∧ (ii). "Tem o menor pinball médio" é informação,
não condição. Não há vencedor entre horizontes.

### Parâmetros do refresh (ADR 6.5.0009)

DM α 0,05 com estimador retangular (primário) e Bartlett (sensibilidade); MCS α 0,10,
1 000 réplicas, seed 127, esquema estacionário (primário) e moving-block
(sensibilidade), sensibilidades de bloco l = h e l = ⌈√T⌉; bandas 0,975 (gate) e 0,95
(perfil); `min_violations` 2; tolerância de degeneração 1e-12; Monte Carlo de
Christoffersen em h + 1 com 999 sorteios e seed 128.

### Perfis declarados e onde cada um é construído (ADR 6.5.0008)

- **Na 6.5 (scorecard):** DM Bartlett, MCS moving-block, gate na amostra comum,
  LR_uc de 3 estados, DGT, banda a 95 %, variante com as degeneradas, calibração dos
  comparadores, IC do efeito do DM, `fallback_applied`, desfecho por nível, menor
  pinball médio, descritores entre seeds.
- **Issue #129 (antes da 8.1):** DM por fold, por seed e por τ; sensibilidades de
  bloco l = h e l = ⌈√T⌉; diagnóstico de estacionariedade do diferencial; degeneração
  parcial por par; p-valor Monte Carlo de Christoffersen em h + 1.
- **Stage 8.3:** diagrama de nitidez (sharpness).

### Declaração de cegamento (decisão do pesquisador, ADR 6.5.0010 P1)

As tabelas confirmatórias do cohort r0 foram calculadas uma vez num teste de
software da Stage 6.4 (Task 15), num container descartado. Nenhum valor resultante
foi lido. Nenhuma escolha deste plano usou informação de desempenho.

O que aquele teste da 6.4 exibiu foi só o status da execução, as durações e as
contagens por etapa, as contagens de linhas por tabela, o resumo do realizado (número
de sessões, datas e soma dos retornos) e os quality checks agrupados com as suas
contagens — nenhum valor de desempenho (registro completo no technical da Stage 6.4,
§7, "Exposição de cegamento").

### O que a Stage 6.5 prova sobre a ordem (ADR 6.5.0003 item 4)

- A âncora do cohort referenciado (comentário na #102, 2026-09-28T20:27:09Z) é
  anterior à âncora deste pré-registro (tag e comentário na #127, abaixo).
- Todo teste e o e2e da 6.5 usam dados sintéticos; a Stage não rodou o refresh do
  gold sobre o cohort.
- O scorecard marca como não pronto um gold gerado antes da âncora desta revisão.

### Âncora r0 (ADR 6.5.0003)

- **Tag:** `preregistration/aapl_confirmatory-r0-4526c437c296` (commit
  `128d23eec95eea4f7ab183e075dfacac14985c66`).
- **Comentário na #127:**
  <https://github.com/MarceloSanC/financial-forecasting/issues/127#issuecomment-5918567606>,
  criado pelo servidor em **2026-09-30T19:53:47Z** — posterior à âncora do cohort
  referenciado na #102 (2026-09-28T20:27:09Z).
- **Registro:** `config/preregistration/aapl_confirmatory-r0.anchor.toml` (fora do
  hash). A conferência é por conteúdo: o arquivo do plano na tag é byte-igual ao de
  HEAD.

## Revisão r1 (emenda cega, Stage 6.6)

- **Arquivo:** `config/preregistration/aapl_confirmatory-r1.toml`
- **`preregistration_ref`:** `aapl_confirmatory-r1-d0d20b9ddbb7`
- **Hash completo (sha256, floats codificados exatamente):**
  `d0d20b9ddbb71edae3a3745b049633979d4c1b1d300fa5c8f45d8c79d4645417`
- **Emenda de:** `aapl_confirmatory-r0-4526c437c296` (`blind_status = "blinded"`).

### O que muda

Só o bloco `[profile_parameters]`, que dá nome às regras dos perfis de séries novas
que o r0 declara mas não especifica (auditoria F7; ADRs 6.6.0001-0003). Todo outro
campo é igual ao do r0 (um teste confere campo a campo), então o que julga H1, H2 e
H3 não muda: o veredito nunca lê as tabelas desses perfis (ADR 6.6.0002).

- **Recortes do DM** (por fold, por seed do candidato e por quantil):
  descritivos, com p bruto e sem correção de Holm entre recortes
  (`none_raw_p_descriptive_v1`).
- **Degeneração parcial por par:** pares simétricos e pares adjacentes da grade,
  sobre as linhas não degeneradas, com a tolerância do gate
  (`symmetric_and_adjacent_non_degenerate_rows_v1`).
- **MCS com bloco l = h e l = ⌈√T⌉:** só no esquema primário (`primary_scheme`).
- **Estacionariedade do diferencial de perdas d_t:** ACF até
  L = min(⌊10·log10 T⌋, T − 1), o default do statsmodels
  (`min_floor_10_log10_T_T_minus_1`); teste de quebra da média por CUSUM escalado
  pela variância de longo prazo do DM primário, com p-valor de Kolmogorov
  (`cusum_mean_dm_primary_variance_kolmogorov_v1`); nível 0,05.

Sob o r0, esses sete perfis ficam como "regra não congelada na revisão" no scorecard
e as suas tabelas saem vazias; o Monte Carlo de Christoffersen, cujos sorteios e
semente já estão no r0, roda nas duas revisões.

### Declaração de cegamento da emenda

As regras acima foram escolhidas pela literatura e pelos defaults das bibliotecas
de referência (registros `[decision]` da Stage 6.6), antes de qualquer execução do
refresh sobre o cohort e sem nenhum valor de desempenho à vista. A emenda é
ancorada antes da Stage 8.1, que julga pela r1.
