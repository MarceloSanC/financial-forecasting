---
title: Treinamento de modelos quantílicos — teoria do Step 5 (baselines, GBM, TFT, cohort confirmatório)
description: Teoria canônica do subdomínio quantile-model-training — como cada baseline emite quantis, por que a pinball loss elicita o quantil, a mecânica do GBM e do TFT quantílicos, a disciplina do cohort confirmatório e o contrato de fronteira com a avaliação (Step 6)
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 5 (5.2–5.5), ao questionar uma fórmula/convenção de emissão de quantis, ou ao decidir se um tema pertence a este doc ou ao doc futuro do BC evaluation
keywords: [domain, modeling, quantile, pinball, baseline, ewma, ar1, historical-quantiles, random-walk, lightgbm, gbm, tft, early-stopping, optuna, hpo, confirmatory-cohort, seeds-folds, rearrangement, quantile-crossing, degenerate-grid]
status: accepted
created_at: 2026-07-14
updated_at: 2026-07-15
bounded_context: modeling
subdomain: quantile-model-training
references:
  - ../../adr/0_0_0051-modeling-domain-doc-scope-and-boundary.md
  - ../../adr/0_0_0052-baseline-quantile-emission-conventions.md
  - ../../adr/5_1_0001-expanding-window-walk-forward.md
  - ../../adr/5_1_0002-dedicated-calibration-partition.md
  - ../../adr/5_1_0003-split-fingerprint-four-way-calib.md
---

# Treinamento de modelos quantílicos — teoria do Step 5

> **Categoria `domain/`** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este documento é a **teoria** (o quê/por quê) do subdomínio, transversal às
> Stages. Ele **não** é spec de implementação — não define schemas, caminhos de
> arquivo nem cadências; isso pertence ao `technical.md` de cada Stage + código.
> Toda fórmula que muda um número reportado pelo projeto carrega citação
> rastreável a fonte primária.

## 1. Escopo e como consumir este doc

**Cobre** os quatro blocos de teoria do Step 5 (recorte decidido no
[ADR 0.0.0051](../../adr/0_0_0051-modeling-domain-doc-scope-and-boundary.md)):

1. a **hierarquia de baselines** e as convenções de emissão de quantis (§3);
2. o **GBM quantílico** — gradient boosting com pinball loss no LightGBM (§4);
3. o **treino do TFT quantílico** (§5);
4. o **cohort confirmatório** (§6);

apoiados nos **fundamentos comuns** a todo modelo quantílico do projeto (§2)
— base compartilhada dos quatro blocos, não um bloco em si — mais uma
seção-fronteira de **contrato com a avaliação** (§7), só com ponteiros.

**Não cobre**:

- **Implementação** (schemas de tabela, nomes de arquivo, parâmetros default,
  cadência de re-treino) → `technical.md` das Stages 5.2–5.5.
- **Teoria da avaliação confirmatória** (DM/HLN, Holm, MCS, Christoffersen,
  Kupiec, gate de degeneração) → doc de domínio futuro do BC `evaluation`
  (gate do Step 6). A §7 apenas declara o contrato que este lado da fronteira
  honra.
- **O protocolo temporal em si** (folds, purga, embargo, partição calib) — já
  teorizado e implementado na Stage 5.1; aqui é **pressuposto** (§2.5).

**Mapa de consumo** (que Stage lê o quê):

| Stage | Seções que consome |
|---|---|
| 5.2 — baselines naive/estatísticos | §3 (+ §2 e §7) |
| 5.3 — GBM quantílico | §4 (+ §2 e §7) |
| 5.4 — TFT trainer | §5 (+ §2 e §7) |
| 5.5 — re-treino confirmatório | §6 (+ §2 e §7) |
| todas | §2 (fundamentos) e §7 (fronteira) |

## 2. Fundamentos comuns

### 2.1 O alvo: retorno log de um dia, realizado em t+h

O alvo do projeto é o **retorno logarítmico backward de 1 dia**,
`target_return[t] = log(close_t / close_{t-1})`
([ADR 3.5.0001](../../adr/3_5_0001-target-definition-backward-log-return.md)).
Para o horizonte `h` (h ∈ {1, 7} sessões de pregão; h+30 é horizonte
suplementar ratificado — overview §1 — e toda a teoria deste doc é genérica em
`h`), o alvo previsto na decisão `t` é o retorno de **um** dia realizado na
sessão `t+h` — a indexação é por
posição no array de sessões, nunca por timedelta de calendário
([ADR 4.3.0001](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)).

Consequência teórica que atravessa todo o doc: como o alvo em `h` é o retorno
de UM dia (não o retorno **acumulado** de `h` dias), **nenhuma regra de escala
√h/√T se aplica** aos baselines. O √h da FPP3 (Hyndman & Athanasopoulos 2021,
Table 5.2) vale para o nível/acumulado da série `h` passos à frente — modelo
diferente do nosso alvo. Cada baseline da §3 declara explicitamente como sua
variância se comporta em `h` sob esta semântica.

### 2.2 Pinball loss: a perda que elicita o quantil

A **pinball loss** (também "quantile loss"; *check function* — função de perda
assimétrica em forma de "✓") para o nível τ ∈ (0,1) e resíduo u = y − q̂ é

    ρ_τ(u) = u · (τ − 1{u < 0})    ⟺    ρ_τ(u) = τ·u se u ≥ 0; (τ−1)·u se u < 0.

- **Origem:** Koenker & Bassett (1978), Seção 3, p. 38 — o θ-ésimo *regression
  quantile* é definido como solução da minimização da soma assimetricamente
  ponderada de resíduos absolutos (displays da p. 38, não numerados no paper).
  A grafia compacta ρ_τ e o nome "check function" são consolidação posterior:
  Koenker (2005), cap. 1. Citamos 1978 para a origem e 2005 para a notação.
- **Consistência estrita (o porquê de treinar E avaliar com ela):** Gneiting
  (2011, JASA), Eq. (24), §3.3, pp. 754–755 — a scoring function
  S_α(x,y) = (1{x ≥ y} − α)(x − y) é **estritamente consistente para o
  α-quantil** (na classe das medidas com primeiro momento finito); o
  **Theorem 9** (p. 755) mostra que as funções consistentes para o α-quantil
  são exatamente as GPL (*generalized piecewise linear*), das quais a pinball
  é o caso g(x) = x. Em prosa: minimizar a pinball média em τ elicita o
  quantil condicional verdadeiro — por isso ela é simultaneamente a **loss de
  treino** (LightGBM §4, TFT §5) e a **scoring function** da avaliação pareada
  futura (§7).

### 2.3 A grade densa de ~7–9 quantis

O projeto emite uma grade densa de ~7–9 níveis de quantil (overview §3/§11 —
decisão já ratificada). O fundamento citável é um **triângulo** — não existe
teorema de cardinalidade ótima da grade:

1. **Default da biblioteca:** o `QuantileLoss` do pytorch-forecasting usa 7
   níveis por default ({0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98}) — fonte de
   mecânica: código-fonte oficial da biblioteca.
2. **Padrão de competição:** a M5 Uncertainty exigiu 9 quantis
   ({0.005, 0.025, 0.165, 0.25, 0.5, 0.75, 0.835, 0.975, 0.995}) como
   suficientes para descrever a distribuição (Makridakis et al. 2022).
3. **Quadratura do CRPS:** Gneiting & Ranjan (2011), Eq. (6):
   `CRPS(F,y) = ∫₀¹ QS_α(F⁻¹(α), y) dα`, com `QS_α(q,y) = 2(1{y<q} − α)(q−y)`
   — o fator 2 vive **dentro** do QS_α; equivalentemente,
   `CRPS = 2∫₀¹ ρ_α dα` com ρ_α a pinball usual. A pinball média ρ̄ sobre uma
   grade finita é, portanto, uma aproximação por quadratura (soma finita que
   aproxima a integral) de **CRPS/2** — quanto mais densa a grade, melhor a
   aproximação. O fator constante 2 não altera nenhuma comparação ou
   ordenação entre modelos.

Contra o excesso: Wen et al. (2017, §4.2) treinaram apenas 5 quantis e
interpolaram linearmente para os 99 exigidos pela GEFCom2014 (Hong et al.
2016) com resultado vencedor nas duas tracks — a grade de 99 é artefato do
formato de submissão, não necessidade de treino. **Atenção de atribuição:** o
paper do TFT (Lim et al. 2021) usa apenas Q = {0.1, 0.5, 0.9}; a grade densa
do projeto **nunca** deve ser atribuída a ele (ver §5.1).

### 2.4 Quantile crossing e o rearranjo

**Quantile crossing** (cruzamento de quantis): quando níveis de quantil são
estimados sem acoplamento, nada garante q̂_{τ₁} ≤ q̂_{τ₂} para τ₁ < τ₂ — a
"curva" prevista pode ser não monótona, o que é incoerente com qualquer
distribuição.

A correção canônica é o **rearranjo monótono** de Chernozhukov, Fernández-Val
& Galichon (2010): ordenar os valores da curva estimada. A **Proposition 4**
(cf. §2.4 do paper) garante que, para qualquer estimador Q̂ (nem precisa ser
consistente) de uma curva quantílica verdadeira Q₀,
‖Q̂* − Q₀‖_p ≤ ‖Q̂ − Q₀‖_p para todo p ∈ [1, ∞] (estrita para p ∈ (1, ∞)
quando a curva estimada é estritamente **decrescente** em um subconjunto de
medida de Lebesgue positiva **enquanto** a curva verdadeira é estritamente
crescente — as duas condições, conforme o paper), **em amostra finita e
independente de como a estimativa foi obtida** — rearranjar nunca piora e
tipicamente melhora.

O guardrail `sorted()` do projeto
([ADR 4.3.0002](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md))
é exatamente este operador na leitura discreta: ordenar o vetor de valores da
grade equivale ao rearranjo de CFG aplicado à grade **com pesos iguais por
nível** (massa 1/K por τ_k), herdando a garantia da Proposition 4 nas normas
ℓ_p da grade. Este doc só adiciona o fundamento — o guardrail já existia.

**Ressalva obrigatória:** o rearranjo corrige **monotonicidade**, não
**calibração** (cobertura empírica dos quantis) — a Prop. 4 fala de distância
à curva verdadeira, não de cobertura. Quantis rearranjados podem continuar
mal calibrados; a caracterização de calibração (Step 6) e o conformal
(Step 7) continuam necessários.

### 2.5 Protocolo temporal pressuposto (ponteiro)

Todo treino e emissão de predição deste doc pressupõe o harness da Stage 5.1:
folds walk-forward expansivos com purga+embargo em dias de pregão, partição
quádrupla `train / early_stop / calib / test`
([ADR 5.1.0001](../../adr/5_1_0001-expanding-window-walk-forward.md),
[5.1.0002](../../adr/5_1_0002-dedicated-calibration-partition.md),
[5.1.0003](../../adr/5_1_0003-split-fingerprint-four-way-calib.md)), `ScopeSpec`
como identidade do cohort e dedup *operationally-latest* (1 observação por
ponto alinhado). A teoria desses elementos vive no
[`concept.md` da 5.1](../../stages/5.1-walk-forward-harness/concept.md) §4–§7 e
não é re-derivada aqui.

## 3. Hierarquia de baselines e emissão de quantis

### 3.1 Papel científico da hierarquia

Gu, Kelly & Xiu (2020) definem o R² out-of-sample contra o benchmark **zero**
(Eq. 19, §1.8, pp. 2245–2246 — denominador sem demeaning), justificando:
"Predicting future excess stock returns with historical averages typically
underperforms a naive forecast of zero by a large margin" (p. 2246). Nos seus
painéis mensais de ações individuais, o melhor método (NN3) atinge R²_oos de
**0,40%** no pico (p. 2251; Table 1, pp. 2249–2250) — em frequência diária a
previsibilidade da média é ainda menor. Duas consequências estruturam a
hierarquia:

1. baselines de média (zero, média histórica) são **réguas competitivas** na
   locação — é honesto e necessário compará-los;
2. o valor agregável de um modelo está majoritariamente na **distribuição**
   (escala/formato — volatilidade e quantis), não na média — exatamente o
   terreno dos baselines EWMA-vol e quantis históricos, e do objeto científico
   do projeto (calibração, overview §1/§4).

A hierarquia sobe em informação distribucional: pontuais degenerados (§3.2,
§3.3) → paramétricos condicionais na média (AR(1), §3.5) → condicionais na
variância (EWMA, §3.6) → incondicionais não paramétricos (quantis históricos,
§3.7). Convenções de emissão decididas no
[ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md).

### 3.2 `zero_return` ≡ random walk sem drift do log-preço (uma spec só)

O random walk (passeio aleatório) **sem drift do log-preço** é
p_t = p_{t−1} + ε_t (hierarquia RW1–RW3 de Campbell, Lo & MacKinlay 1997,
cap. 2, §2.1). Sob esse modelo, E_t[p_{t+h}] = p_t para todo h, logo o retorno
de um dia previsto é

    r̂_{t+h|t} = 0    para todo h

— **idêntico** ao baseline `zero_return`. Com o alvo fixado como retorno de 1
dia (§2.1), o colapso é matematicamente exato, inclusive nas bandas (a
variância do erro é σ² constante em h; o √h da FPP3 Table 5.2 é para o nível).
Decisão: **um baseline só**, documentado como "zero_return ≡ RW sem drift do
log-preço".

**A ambiguidade do rótulo é real e deve ficar registrada:** FPP3 §5.2 chama o
método naive ŷ_{T+h|T} = y_T de "random walk forecast". Aplicado à **série de
retornos**, isso daria r̂_{t+h} = r_t ≠ 0 — um baseline distinto
(naive-sobre-retornos), rejeitado por mal-especificação: retornos diários são
aproximadamente não autocorrelacionados, e tratá-los como random walk não tem
suporte. Este projeto fixa a leitura "RW do log-preço".

**Emissão:** grade **degenerada** — todos os níveis da grade recebem o mesmo
valor 0 (fundamento em §3.4).

### 3.3 `historical_mean`

Média amostral dos retornos da janela de treino:
r̂_{t+h|t} = μ̂ = (1/n)Σ r_s, para todo h. É a régua que GKX (2020, p. 2246)
mostram ser **pior que zero** para ações individuais — mantê-la na hierarquia
torna esse fato verificável nos nossos dados. **Emissão:** grade degenerada
com valor μ̂.

### 3.4 Fundamento da grade degenerada

Um preditor pontual é, na literatura de scoring rules, a distribuição
**degenerada** (medida de Dirac δ_x — toda a massa num ponto): Gneiting &
Raftery (2007, §4.2) mostram que o CRPS "generaliza o erro absoluto, ao qual
se reduz se F é um point forecast" — a comparação entre preditores pontuais e
probabilísticos é formalmente bem-posta. Pelo Theorem 9 de Gneiting (2011)
(§2.2), avaliar qualquer preditor com pinball em τ é avaliá-lo como estimador
do quantil τ. Logo, emitir a grade com q̂_τ = r̂ para todo τ e pontuá-la com a
pinball média na grade é uma aproximação discreta de **metade** do CRPS do
Dirac — isto é, de **MAE/2**, já que CRPS = 2∫₀¹ ρ_α dα (§2.3) e o CRPS do
Dirac é o MAE; o fator constante 2 não altera nenhuma comparação ou ordenação
entre modelos.

Duas notas de honestidade metodológica:

- A **penalização severa nos τ extremos é esperada e informativa** — mede
  exatamente o valor da informação distribucional que os baselines pontuais
  não têm. Não é defeito a corrigir.
- O guardrail de monotonicidade
  ([ADR 4.3.0002](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md))
  **deixa passar** q_low == q_high (empates não violam ordenação fraca); a
  detecção de grade degenerada é papel do **gate de degeneração** do Step 6
  (Stage 6.1), deliberadamente separado do guardrail (§7).

### 3.5 `AR(1)` — quantis paramétricos gaussianos

Modelo autorregressivo de ordem 1 (a média de amanhã depende linearmente do
desvio de hoje): r_t − μ = φ(r_{t−1} − μ) + ε_t, ε_t ~ WN(0, σ²_ε).

- **Média condicional h passos à frente:**

      r̂_{t+h|t} = μ + φ^h (r_t − μ)

  Fonte: Hamilton (1994), cap. 4, §4.2 *Forecasts Based on an Infinite Number
  of Observations*, pp. 77–85.
- **Variância do erro de previsão (cresce com h até a incondicional):**

      Var[e_{t+h|t}] = σ²_ε Σ_{j=0}^{h−1} φ^{2j} = σ²_ε (1−φ^{2h})/(1−φ²)  →  σ²_ε/(1−φ²)

  Fonte: Box, Jenkins, Reinsel & Ljung (2015), Eq. (5.1.16), §5.1.1, p. 132 —
  V(l) = (1 + ψ₁² + ⋯ + ψ²_{l−1})σ²_a com ψ₀ = 1 (no AR(1), ψ_j = φ^j);
  Hamilton, op. cit.
- **Emissão (decidida):** quantis **paramétricos gaussianos**
  q̂_τ(h) = r̂_{t+h|t} + σ̂_h · z_τ, onde z_τ = Φ⁻¹(τ) é o quantil da normal
  padrão e σ̂_h a raiz da variância acima com σ̂_ε dos resíduos (forma de
  intervalo padrão de livro-texto: FPP3 §5.5/§9.8). A alternativa "quantis
  empíricos dos resíduos por horizonte" foi rejeitada porque duplicaria o
  papel do conformal do Step 7.2 (recalibração empírica de intervalos é a
  função do CQR, não de um baseline) —
  [ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md).

Comportamento em h: variância **crescente** com h — contraste deliberado com
o EWMA (flat, §3.6) e os quantis históricos (incondicionais, §3.7).

### 3.6 `EWMA-vol` — volatilidade condicional, quantis gaussianos com μ = 0

EWMA (*exponentially weighted moving average* — média móvel com pesos que
decaem exponencialmente) sobre o quadrado dos retornos, forma canônica do
RiskMetrics Technical Document (J.P. Morgan/Reuters 1996):

    σ̂²_{t+1|t} = λ σ̂²_{t|t−1} + (1−λ) r_t²        (RMTD Eq. [5.3], §5.2.1, p. 81)

- **μ = 0 por construção:** a derivação do RMTD assume média amostral zero
  ("assuming again that the sample mean is zero", p. 81) — o baseline canônico
  usa μ̂ = 0, não a média amostral (coerente com GKX §3.1: a média histórica é
  ruído; e o `historical_mean` já existe como baseline separado).
- **λ = 0.94 para dados diários:** RMTD §5.3.2.2, pp. 99–100 (média ponderada
  por acurácia dos λ ótimos de 480+ séries).
- **Variância FLAT em h:** a Eq. [5.18] do RMTD (p. 86) enuncia
  E_t[σ²_{t+s}] = E_t[σ²_{t+s−1}] ("the variance forecasts for two
  consecutive periods are the same"); por indução imediata, a previsão de
  variância do retorno de UM dia em t+s é igual à de t+1 para todo s — a
  forma "flat para todo h" é **consequência** da equação, não texto literal.
  O acumulado T·σ²_{t+1|t} da Eq. [5.20] (regra √T) vale para o retorno
  **acumulado** de T dias e **não se aplica ao nosso alvo** (§2.1).
- **Emissão (decidida):** quantis paramétricos gaussianos com μ = 0:

      q̂_τ = σ̂_{t+1|t} · z_τ

  pela forma locação-escala VaR_α = μ + σΦ⁻¹(α) (McNeil, Frey & Embrechts
  2005, Eq. (2.19), Example 2.14, §2.2.2, pp. 39–40).
- **Melhoria futura especulativa (não default):** variante t-Student
  (Eq. (2.20) do QRM), que exigiria escolher ν e **reescalar** o σ̂ do EWMA
  por √((ν−2)/ν) — o σ da t é parâmetro de escala, não desvio-padrão
  (advertência var = νσ²/(ν−2) em QRM Example 2.14, p. 40; o fator explícito
  de reescala em QRM §4.4.2, pp. 161–162). Fica como issue especulativa a
  criar (§8); a eventual miscalibração de cauda da gaussiana é resultado
  **informativo** (é o que o TFT/conformal deve superar), não defeito do
  baseline.

### 3.7 `historical_quantiles` — quantil empírico tipo 7 da janela rolante

Quantil amostral (interpolação entre estatísticas de ordem) da janela
histórica de retornos, emitido diretamente como q̂_τ para cada nível da grade,
idêntico para todo h (método incondicional).

- **Estimador (decidido): tipo 7** de Hyndman & Fan (1996) — no paper, as
  Definitions 7/8 são dadas como *plotting positions* p_k (Def 7: m = 1−p;
  Def 8: m = (p+1)/3); as formas h = (n−1)p + 1 (tipo 7) e
  h = (n + 1/3)p + 1/3 (tipo 8) são a parametrização equivalente usada pela
  documentação do R. O paper **recomenda o tipo 8** (mediano-não-viesado);
  os defaults de R (`type=7`) e NumPy (`method='linear'`) são o **tipo 7**.
  Decisão pré-registrada: **tipo 7**, fixado em todos os baselines, por
  reprodutibilidade máxima (default de toda a stack); o tipo 8 fica como
  sensibilidade futura especulativa (mesma issue do §3.6) —
  [ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md).
- **Fundamento como baseline probabilístico:** é o método de **Historical
  Simulation** — estimar as medidas de risco pela distribuição empírica da
  janela (McNeil, Frey & Embrechts 2005, §2.3.2, Eq. (2.32), p. 50). O QRM o
  classifica explicitamente como método **incondicional** (não reage a
  clustering de volatilidade) — contraste deliberado com o EWMA condicional
  (§3.6): a dupla {EWMA, historical_quantiles} separa o valor de condicionar
  na volatilidade recente do valor de estimar caudas empíricas.

### 3.8 Tabela-resumo dos baselines

| Baseline | Estado estimado | Conversão em quantis | Comportamento em h | Fonte principal |
|---|---|---|---|---|
| `zero_return` (≡ RW sem drift do log-preço) | nenhum | grade degenerada em 0 | flat (0 para todo h) | Campbell-Lo-MacKinlay 1997 cap. 2; FPP3 §5.2; Gneiting & Raftery 2007 §4.2 |
| `historical_mean` | μ̂ da janela | grade degenerada em μ̂ | flat | GKX 2020 p. 2246; Gneiting & Raftery 2007 §4.2 |
| `ar1` | μ̂, φ̂, σ̂_ε | paramétrico gaussiano: μ + φ^h(r_t−μ) + σ̂_h z_τ | média → μ; variância cresce até a incondicional | Hamilton 1994 §4.2; Box-Jenkins 2015 Eq. (5.1.16); FPP3 §5.5 |
| `ewma_vol` | σ̂²_{t+1\|t} (λ=0.94, μ=0) | paramétrico gaussiano: σ̂ z_τ | variância flat (RMTD [5.18], por indução) | RMTD 1996 [5.3]/[5.18]/§5.3.2.2; QRM 2005 Eq. (2.19) |
| `historical_quantiles` | quantis tipo 7 da janela | direto (empírico) | flat (incondicional) | Hyndman & Fan 1996; QRM 2005 §2.3.2 Eq. (2.32) |

(O texto "6 baselines" do roadmap reflete a contagem anterior ao colapso do
§3.2; o ajuste para 5 specs acontece na Stage 5.2 —
[ADR 0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md).)

## 4. GBM quantílico (LightGBM)

### 4.1 Por que boosting funciona com a pinball

O gradient boosting genérico (Friedman 2001, Algorithm 1, pp. 1193–1194)
ajusta, a cada iteração, o base learner às **pseudo-respostas**
ỹ_i = −∂L/∂F (gradiente negativo da perda). Para perdas L1-like o gradiente é
**constante por partes**: no caso LAD (mediana), ỹ_i = sign(y_i − F(x_i))
(Eq. (13), p. 1194); a pinball é a generalização assimétrica — o gradiente
carrega só o sinal do resíduo, escalado por τ / (1−τ), não a magnitude. O que
resgata a informação de magnitude é o **refit da folha**: a atualização ótima
por folha é γ_jm = argmin_γ Σ L(y_i, F_{m−1}(x_i) + γ) (Eq. (18), p. 1196),
que para LAD dá a **mediana** dos resíduos da folha. Para a pinball, o análogo
direto é o **τ-quantil empírico dos resíduos da folha** — isto é **corolário**
da Eq. (18), não conteúdo do paper (Friedman só deriva o caso LAD); registrado
aqui como inferência.

### 4.2 Mecânica no LightGBM e a consequência do cruzamento

Pela documentação oficial de parâmetros do LightGBM: `objective` é um **enum
escalar** (com `quantile` entre as aplicações de regressão) e `alpha` é um
**único double** por modelo. **Consequência de engenharia** (inferida da doc,
não texto literal dela): não existe modo multi-quantil nativo — uma grade de
~7–9 níveis exige **um booster independente por nível**
(`objective='quantile'`, `alpha=τ_k`); e como cada booster resolve uma
minimização separada, sem acoplamento entre níveis, **os quantis previstos
podem cruzar** (§2.4).

`monotone_constraints` **não é solução**: a doc o define para monotonicidade
da predição em relação a **features de entrada** — como cada nível τ é um
booster separado (τ não é feature), o parâmetro não tem como impor
monotonicidade **entre** quantis. Fork inaplicável, declarado.

**Correção adotada:** o rearranjo do §2.4 (guardrail `sorted()` do ADR
4.3.0002), agnóstico ao modelo e com garantia finita-amostral (CFG 2010,
Prop. 4).

### 4.3 Alternativas não adotadas (citáveis)

- **Isotonização / PAVA** (projeção L₂ no cone monótono; faz *pooling* dos
  violadores em vez de permutar): Barlow et al. (1972); Robertson, Wright &
  Dykstra (1988). O próprio CFG 2010 nota propriedades contrativas similares
  do PAVA.
- **Treino conjunto com restrição de não cruzamento** (uma otimização para
  todos os τ): Takeuchi et al. (2006, JMLR); Bondell, Reich & Wang (2010,
  Biometrika). Indisponível em LightGBM.
- **Monotonicidade arquitetural em redes** (τ como input monótono): MCQRNN,
  Cannon (2018). Contraste útil: o TFT também **não** impõe não-cruzamento
  (§5.1) e, portanto, também precisa do guardrail.

## 5. Treino do TFT quantílico

### 5.1 A loss do paper e a nossa grade

O TFT (Lim et al. 2021) treina minimizando a **soma da pinball sobre a grade
de quantis e todos os horizontes**, normalizada (Eq. (24)); a QL da Eq. (25) é
a pinball: QL(y, ŷ, q) = q(y − ŷ)₊ + (1−q)(ŷ − y)₊. As saídas quantílicas são
transformações lineares do decoder, treinadas conjuntamente — mas **sem
restrição de não cruzamento**, então o guardrail do §2.4 se aplica também ao
TFT.

O paper usa **Q = {0.1, 0.5, 0.9}** (3 quantis). A grade densa ~7–9 do projeto
**não vem do paper** — vem do triângulo do §2.3 (default da biblioteca, padrão
M5, quadratura do CRPS). Nunca atribuir a grade a Lim et al. (2021).

### 5.2 Tipagem known/observed/static — a base formal do anti-leakage

A Seção 3 do paper divide as entradas de cada entidade em: covariáveis
**estáticas** s_i (invariantes no tempo); **observed inputs** z_{i,t}
("que só podem ser medidos a cada passo e são desconhecidos de antemão");
**known inputs** x_{i,t} ("que podem ser predeterminados", ex.: dia da
semana). A previsão quantílica (Eq. (1)) é
ŷ_i(q,t,τ) = f_q(τ, y_{i,t−k:t}, z_{i,t−k:t}, x_{i,t−k:t+τ}, s_i): o alvo y e
os observed z entram **só até t**; os known x entram **até t+τ**. Essa
assimetria de indexação é a **base formal do anti-leakage** (vazamento de
informação futura): preço/retornos/indicadores/sentimento são obrigatoriamente
observed (unknown); calendário é known. Casa com a promoção do known/unknown a
campo validado da FeatureSpec
([ADR 3.4.0002](../../adr/3_4_0002-featurespec-superset-and-tft-typing-promotion.md)).

### 5.3 Early stopping

*Early stopping* (parada antecipada): monitorar o erro num conjunto de
validação separado e parar quando ele deixa de melhorar.

- **Formalização:** Prechelt (1998, LNCS 1524) define as classes de critérios
  GL (generalization loss), PQ (quociente de progresso) e UP (strips de
  aumentos sucessivos — a "paciência" é a variante UP simplificada); o modelo
  retido é o de **menor erro de validação visto** (restaurar o melhor
  checkpoint, não o último).
- **Estatuto metodológico:** Goodfellow, Bengio & Courville (2016, §7.8)
  tratam early stopping como regularização E como **seleção de
  hiperparâmetro** — o número de passos de treino é um hiperparâmetro
  selecionado pelo conjunto de validação. Consequência central para o
  projeto: **o sub-split monitorado participa da seleção do modelo**.
- **Por isso, nunca reusar o val monitorado como calibração conformal:** o
  split conformal exige um conjunto de calibração **disjunto de tudo que
  ajustou/selecionou o modelo** (Lei et al. 2018); reusar o early-stop set
  como calib quebraria a premissa e anularia a leitura de cobertura. É o
  invariante do calib dedicado do harness
  ([ADR 5.1.0002](../../adr/5_1_0002-dedicated-calibration-partition.md)).
- **Alternativa registrada como NÃO adotada:** re-treinar em train+val com o
  número de épocas selecionado (discutida em Goodfellow §7.8). Rejeitada
  porque apagaria a fronteira early_stop/calib do harness (o re-treino
  consumiria a região cuja separação o ADR 5.1.0002 garante).
- **Nota de mecânica:** no PyTorch Lightning, a restauração do melhor
  checkpoint **não** é automática do callback `EarlyStopping`; é
  responsabilidade do `ModelCheckpoint` + recarga explícita — detalhe
  operacional que o `technical.md` da 5.4 deve tratar.

### 5.4 HPO exploratório, HPs congelados no confirmatório

HPO (*hyperparameter optimization* — busca de hiperparâmetros): os sweeps do
projeto usam Optuna (Akiba et al. 2019), cujo sampler default é o TPE
(Bergstra et al. 2011 — modela p(x|y) por densidades de trials bons/ruins);
random search (Bergstra & Bengio 2012) é o baseline reconhecido que qualquer
uso de TPE deve reconhecer. Tudo isso é **exploratório**.

A disciplina que separa exploração de confirmação é o protocolo de Raschka
(2018, §3–4): a seleção de hiperparâmetros usa exclusivamente treino+validação
da fase exploratória; a avaliação final acontece **uma única vez**, com os
hiperparâmetros **congelados**, em dados jamais tocados pela busca — sob pena
de viés otimista. Mapeamento direto: sweep Optuna = exploratório (5.4);
re-treino com HPs congelados no cohort = confirmatório (5.5, §6).

## 6. Cohort confirmatório

### 6.1 Candidato único all-features, sem seleção por OOS

*Data snooping* (espiar os dados): reutilizar o mesmo out-of-sample para
**selecionar** e para **inferir**. White (2000) formaliza o problema — o
"melhor" de uma busca ampla parece significativo por acaso — e o corrige
computando a distribuição do máximo sob a busca inteira; Romano & Wolf (2005)
generalizam para identificar quantas estratégias batem o benchmark controlando
o FWER (probabilidade de qualquer rejeição falsa).

O desenho do projeto **elimina a busca em vez de corrigi-la**: um único
candidato pré-declarado (TFT all-features) + comparadores pré-declarados
(§3, §4), **nenhum grau de liberdade** (feature-set, arquitetura) escolhido
olhando o desempenho confirmatório (overview §3/§4). As correções que restam
(Holm, MCS — Step 6) operam sobre uma **família pequena e congelada** de
hipóteses — exatamente o regime em que esses procedimentos são válidos.

### 6.2 Seeds × folds como composição

O desenho repete o treino sob **múltiplas seeds** (semente do gerador
aleatório) e **múltiplos folds** (origens temporais do walk-forward),
agregando a distribuição de desempenho. O fundamento é uma **composição de
duas literaturas** — não existe fonte única do produto cartesiano, e o doc o
declara honestamente:

- **Eixo seeds:** Bouthillier et al. (2021) decompõem a variância de
  benchmarks e encontram que o **data sampling/bootstrap é a maior fonte de
  variância** (a inicialização de pesos responde por menos de 50% da variância
  do bootstrap), com a recomendação explícita de **randomizar tantas fontes de
  variação quanto possível** e comparar distribuições, não runs pontuais.
- **Eixo folds:** Tashman (2000) — avaliação com origem rolante e múltiplos
  períodos de teste em vez de origem única; Bergmeir & Benítez (2012) —
  múltiplas partições que respeitam a dependência temporal produzem avaliação
  mais robusta que o holdout único de fim de série.

### 6.3 Congelar + hashear

O cohort (candidato, comparadores, seeds, folds, configuração) é **congelado
antes** da execução confirmatória e **hasheado** (resumo criptográfico que
torna qualquer alteração detectável). Fundamento composto:

- **Congelar = pré-registro:** Nosek et al. (2018) — definir plano e hipóteses
  antes de observar os resultados é o que separa análise confirmatória de
  pós-dição; a inferência só mantém as taxas de erro nominais quando as
  decisões de análise não são contingentes aos resultados.
- **Registrar = reprodutibilidade computacional:** Sandve et al. (2013),
  Rules 1/3/4/6/8 — registrar como cada resultado foi produzido, versões
  exatas, scripts versionados, **seeds anotadas** (Rule 6) e dados por trás de
  cada agregado.
- **O hash em si não tem fonte primária dedicada** — é prática de engenharia
  que **operacionaliza** as duas fontes acima (torna o congelamento
  verificável). Dizemos isso explicitamente em vez de fabricar uma citação.

## 7. Contrato com a avaliação (fronteira — ponteiros, sem derivar)

O que este subdomínio **promete** ao BC `evaluation` (Step 6); a teoria do
lado de lá fica no doc de domínio futuro daquele BC:

1. **Grade comum de quantis para todos os modelos** — candidato, GBM e
   baselines emitem a mesma grade de níveis, persistida em formato LONG com o
   nível de quantil na chave
   ([ADR 4.1.0002](../../adr/4_1_0002-fact-oos-predictions-long-quantile-format.md)),
   o que torna a pinball pareável nível a nível.
2. **Uma observação por `target_timestamp`** — o dedup operationally-latest
   do harness (5.1, D5) garante 1 obs por ponto alinhado; a inferência pareada
   pressupõe isso.
3. **Pinball como métrica pareada futura** — a mesma ρ_τ do §2.2 (consistência
   pelo Theorem 9 de Gneiting 2011) será a loss dos testes pareados; DM/HLN,
   Holm, MCS e Christoffersen são teoria do Step 6 e **não são derivados
   aqui**.
4. **Grade degenerada é assunto do gate de degeneração** (Stage 6.1), que
   invalida métricas de linhas degeneradas e reporta a taxa — papel
   **distinto** do guardrail de monotonicidade do ADR 4.3.0002 (§2.4, §3.4):
   o guardrail conserta ordem; o gate detecta ausência de informação
   distribucional.

## 8. Convenções decididas (tabela-resumo)

Legenda: **[H]** = decisão humana (2026-07-14, gate de domínio do Step 5);
**[M]** = derivação ancorada em docs já ratificados (sem decisão nova).

| # | Decisão | Quem | ADR | Reversibilidade |
|---|---|---|---|---|
| 1 | Doc de domínio único cobrindo os 4 blocos do Step 5 + seção-fronteira com a avaliação (sem teoria do Step 6) | [H] | [0.0.0051](../../adr/0_0_0051-modeling-domain-doc-scope-and-boundary.md) | Barata: dividir o doc e apontar `superseded_by` |
| 2 | EWMA-vol emite quantis gaussianos com μ = 0 (canônico RiskMetrics) | [H] | [0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md) | Variante t-Student como melhoria futura (issue especulativa #48) |
| 3 | Quantil amostral tipo 7 (Hyndman & Fan 1996), fixado e pré-registrado em todos os baselines | [H] | [0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md) | Tipo 8 como sensibilidade futura (mesma issue especulativa #48) |
| 4 | AR(1) emite quantis paramétricos gaussianos (média φ^h + σ̂_h fechado) | [H] | [0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md) | Empírico por horizonte rejeitado (duplicaria o conformal 7.2); reabrível por ADR |
| 5 | zero_return ≡ RW sem drift do log-preço → **uma** spec (5 baselines distintos; texto do roadmap ajusta na Stage 5.2) | [H] | [0.0.0052](../../adr/0_0_0052-baseline-quantile-emission-conventions.md) | Naive-sobre-retornos reintroduzível por ADR se justificado |
| 6 | Alvo em h = retorno de UM dia em t+h; nenhuma regra √h | [M] | [3.5.0001](../../adr/3_5_0001-target-definition-backward-log-return.md) + [4.3.0001](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md) | Mudar o alvo supersede os dois ADRs (cara) |
| 7 | Grade degenerada para baselines pontuais; penalização em τ extremo é informativa | [M] | DoD roadmap 5.2 + [4.3.0002](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md) | — (fundamento adicionado, decisão pré-existente) |
| 8 | Guardrail sorted() = rearranjo CFG 2010 na grade de pesos iguais; corrige monotonicidade, NÃO calibração | [M] | [4.3.0002](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md) | — (fundamento adicionado, decisão pré-existente) |
| 9 | Grade ~7–9 quantis fundamentada pelo triângulo (lib 7 / M5 9 / quadratura CRPS); jamais atribuída a Lim et al. 2021 | [M] | overview §3/§11 | — |
| 10 | Early stopping no sub-split dedicado, restaura melhor checkpoint; val monitorado nunca vira calib conformal; retrain-em-train+val não adotado | [M] | [5.1.0002](../../adr/5_1_0002-dedicated-calibration-partition.md) | Mudar exige superseder o 5.1.0002 |
| 11 | Sweeps Optuna exploratórios; HPs congelados antes do confirmatório; candidato único all-features sem seleção por OOS; seeds × folds como composição; congelar+hashear | [M] | overview §3/§4/§7 + roadmap 5.4/5.5 | Mudar reabre o desenho confirmatório (caro) |

## 9. Referências

Citações completas de todas as fontes usadas. Separadas em (a) já ratificadas
no overview §10 e (b) novas deste doc (registradas no overview §10 no mesmo
PR, conforme ADR 0.0.0003).

### 9.1 Já ratificadas no overview §10

- Koenker, R.; Bassett, G., Jr. (1978). "Regression Quantiles". *Econometrica*, 46(1), 33–50. DOI: 10.2307/1913643. (Displays da p. 38 não numerados.)
- Gneiting, T. (2011). "Making and Evaluating Point Forecasts". *Journal of the American Statistical Association*, 106(494), 746–762. DOI: 10.1198/jasa.2011.r10138. (Eq. (24) §3.3 pp. 754–755; Theorem 9 p. 755.)
- Gneiting, T.; Raftery, A. E. (2007). "Strictly Proper Scoring Rules, Prediction, and Estimation". *JASA*, 102(477), 359–378. DOI: 10.1198/016214506000001437. (§4.2: CRPS do point forecast = erro absoluto.)
- Chernozhukov, V.; Fernández-Val, I.; Galichon, A. (2010). "Quantile and Probability Curves Without Crossing". *Econometrica*, 78(3), 1093–1125. DOI: 10.3982/ECTA7880. (Proposition 4, cf. §2.4.)
- Lim, B.; Arık, S. Ö.; Loeff, N.; Pfister, T. (2021). "Temporal Fusion Transformers for interpretable multi-horizon time series forecasting". *International Journal of Forecasting*, 37(4), 1748–1764. DOI: 10.1016/j.ijforecast.2021.03.012. (Eqs. (1), (24)–(25); Q = {0.1, 0.5, 0.9}.)
- Gu, S.; Kelly, B.; Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning". *The Review of Financial Studies*, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009. (Eq. (19) pp. 2245–2246; NN3 0,40% p. 2251, Table 1 pp. 2249–2250.)
- White, H. (2000). "A Reality Check for Data Snooping". *Econometrica*, 68(5), 1097–1126. DOI: 10.1111/1468-0262.00152.
- Romano, J. P.; Wolf, M. (2005). "Stepwise Multiple Testing as Formalized Data Snooping". *Econometrica*, 73(4), 1237–1282. DOI: 10.1111/j.1468-0262.2005.00615.x.

### 9.2 Novas deste doc

- Koenker, R. (2005). *Quantile Regression*. Econometric Society Monographs No. 38, Cambridge University Press. DOI: 10.1017/CBO9780511754098. (Cap. 1: notação ρ_τ / check function.)
- Gneiting, T.; Ranjan, R. (2011). "Comparing Density Forecasts Using Threshold- and Quantile-Weighted Scoring Rules". *Journal of Business & Economic Statistics*, 29(3), 411–422. DOI: 10.1198/jbes.2010.08110. (Eq. (6): CRPS = ∫₀¹ QS_α dα, QS_α = 2·pinball.)
- J.P. Morgan/Reuters (1996). *RiskMetrics — Technical Document*, 4th ed., New York, 17 dez. 1996. (Eq. [5.3] §5.2.1 p. 81; Eq. [5.18] p. 86; Eq. [5.20] pp. 86–87; λ=0.94 §5.3.2.2 pp. 99–100.)
- McNeil, A. J.; Frey, R.; Embrechts, P. (2005). *Quantitative Risk Management: Concepts, Techniques and Tools*. Princeton University Press. (Eqs. (2.19)–(2.20), Example 2.14, §2.2.2 pp. 39–40; §2.3.2 Eq. (2.32) p. 50; fator √((ν−2)/ν) §4.4.2 pp. 161–162.)
- Hamilton, J. D. (1994). *Time Series Analysis*. Princeton University Press. (Cap. 4, §4.2 *Forecasts Based on an Infinite Number of Observations*, pp. 77–85.)
- Box, G. E. P.; Jenkins, G. M.; Reinsel, G. C.; Ljung, G. M. (2015). *Time Series Analysis: Forecasting and Control*, 5th ed., Wiley. (Eq. (5.1.16), §5.1.1, p. 132, com ψ₀ = 1.)
- Hyndman, R. J.; Fan, Y. (1996). "Sample Quantiles in Statistical Packages". *The American Statistician*, 50(4), 361–365. DOI: 10.1080/00031305.1996.10473566. (As Definitions 7/8 são dadas como plotting positions p_k; as Defs 1–3 são baseadas na inversa da CDF empírica. Recomenda o tipo 8.)
- Hyndman, R. J.; Athanasopoulos, G. (2021). *Forecasting: Principles and Practice*, 3rd ed., OTexts (otexts.com/fpp3). (§5.2 métodos simples/naive; §5.5 intervalos e Table 5.2; §9.8 ARIMA.)
- Campbell, J. Y.; Lo, A. W.; MacKinlay, A. C. (1997). *The Econometrics of Financial Markets*. Princeton University Press. (Cap. 2, §2.1: hierarquia RW1–RW3 do log-preço.)
- Friedman, J. H. (2001). "Greedy Function Approximation: A Gradient Boosting Machine". *The Annals of Statistics*, 29(5), 1189–1232. DOI: 10.1214/aos/1013203451. (Algorithm 1 pp. 1193–1194; Eq. (13) p. 1194; Eq. (18) p. 1196.)
- Makridakis, S.; Spiliotis, E.; Assimakopoulos, V.; et al. (2022). "The M5 uncertainty competition: Results, findings and conclusions". *International Journal of Forecasting*, 38(4), 1365–1385. DOI: 10.1016/j.ijforecast.2021.10.009. (9 quantis exigidos.)
- Wen, R.; Torkkola, K.; Narayanaswamy, B.; Madeka, D. (2017). "A Multi-Horizon Quantile Recurrent Forecaster". *NIPS 2017 Time Series Workshop*, Long Beach, CA. arXiv:1711.11053. (§4.1 Amazon: log-Gaussian ~2× mais largo; §4.2 GEFCom2014: 5 quantis + interpolação → 99, ambas as tracks.)
- Hong, T.; Pinson, P.; Fan, S.; Zareipour, H.; Troccoli, A.; Hyndman, R. J. (2016). "Probabilistic energy forecasting: Global Energy Forecasting Competition 2014 and beyond". *International Journal of Forecasting*, 32(3), 896–913. DOI: 10.1016/j.ijforecast.2016.02.001. (Formato de submissão de 99 percentis.)
- Prechelt, L. (1998). "Early Stopping — But When?". In Orr, G. B.; Müller, K.-R. (eds.), *Neural Networks: Tricks of the Trade*, Springer LNCS 1524, pp. 55–69. DOI: 10.1007/3-540-49430-8_3. (Critérios GL/PQ/UP.)
- Goodfellow, I.; Bengio, Y.; Courville, A. (2016). *Deep Learning*. MIT Press. (§7.8 Early Stopping, pp. 241–249.)
- Lei, J.; G'Sell, M.; Rinaldo, A.; Tibshirani, R. J.; Wasserman, L. (2018). "Distribution-Free Predictive Inference for Regression". *JASA*, 113(523), 1094–1111. DOI: 10.1080/01621459.2017.1307116. (Split conformal: calibração disjunta do fitting.)
- Akiba, T.; Sano, S.; Yanase, T.; Ohta, T.; Koyama, M. (2019). "Optuna: A Next-generation Hyperparameter Optimization Framework". *Proceedings of KDD '19*, pp. 2623–2631. DOI: 10.1145/3292500.3330701.
- Bergstra, J.; Bardenet, R.; Bengio, Y.; Kégl, B. (2011). "Algorithms for Hyper-Parameter Optimization". *Advances in Neural Information Processing Systems 24 (NeurIPS 2011)*, pp. 2546–2554. (TPE, Seção 4.)
- Bergstra, J.; Bengio, Y. (2012). "Random Search for Hyper-Parameter Optimization". *Journal of Machine Learning Research*, 13, 281–305.
- Raschka, S. (2018). "Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning". arXiv:1811.12808. (§3–4: three-way holdout; test set usado uma única vez.)
- Bouthillier, X.; Delaunay, P.; Bronzi, M.; et al. (2021). "Accounting for Variance in Machine Learning Benchmarks". *Proceedings of Machine Learning and Systems (MLSys)*, 3, 747–769. arXiv:2103.03098. (Data sampling/bootstrap como maior fonte de variância; inicialização < 50% da variância do bootstrap.)
- Tashman, L. J. (2000). "Out-of-sample tests of forecasting accuracy: an analysis and review". *International Journal of Forecasting*, 16(4), 437–450. DOI: 10.1016/S0169-2070(00)00065-0.
- Bergmeir, C.; Benítez, J. M. (2012). "On the use of cross-validation for time series predictor evaluation". *Information Sciences*, 191, 192–213. DOI: 10.1016/j.ins.2011.12.028.
- Nosek, B. A.; Ebersole, C. R.; DeHaven, A. C.; Mellor, D. T. (2018). "The preregistration revolution". *PNAS*, 115(11), 2600–2606. DOI: 10.1073/pnas.1708274114.
- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple Rules for Reproducible Computational Research". *PLOS Computational Biology*, 9(10), e1003285. DOI: 10.1371/journal.pcbi.1003285. (Rules 1/3/4/6/8.)
- Barlow, R. E.; Bartholomew, D. J.; Bremner, J. M.; Brunk, H. D. (1972). *Statistical Inference under Order Restrictions*. Wiley. (PAVA — alternativa não adotada.)
- Robertson, T.; Wright, F. T.; Dykstra, R. L. (1988). *Order Restricted Statistical Inference*. Wiley. (PAVA — alternativa não adotada.)
- Takeuchi, I.; Le, Q. V.; Sears, T. D.; Smola, A. J. (2006). "Nonparametric Quantile Estimation". *Journal of Machine Learning Research*, 7, 1231–1264. (Não cruzamento no treino conjunto — alternativa não adotada.)
- Bondell, H. D.; Reich, B. J.; Wang, H. (2010). "Noncrossing quantile regression curve estimation". *Biometrika*, 97(4), 825–838. DOI: 10.1093/biomet/asq048. (Alternativa não adotada.)
- Cannon, A. J. (2018). "Non-crossing nonlinear regression quantiles by monotone composite quantile regression neural network, with application to rainfall extremes". *Stochastic Environmental Research and Risk Assessment*, 32, 3207–3225. DOI: 10.1007/s00477-018-1573-6. (MCQRNN — alternativa não adotada.)

### 9.3 Documentação de biblioteca (mecânica, não teoria)

- LightGBM, `docs/Parameters.rst` (repositório oficial microsoft/LightGBM): `objective` (enum), `alpha` (double único), `monotone_constraints` (features de entrada).
- pytorch-forecasting, `pytorch_forecasting/metrics/quantile.py` e `models/temporal_fusion_transformer` (repositório oficial): default de 7 quantis; a implementação retorna 2× a pinball por elemento (escala constante, irrelevante para otimização).
- PyTorch Lightning, callbacks `EarlyStopping` / `ModelCheckpoint` (docs oficiais): restauração do melhor checkpoint não é automática do `EarlyStopping`.
- R `stats::quantile` e NumPy `numpy.quantile` (docs oficiais): defaults tipo 7 / `method='linear'` ↔ H&F tipo 7.
