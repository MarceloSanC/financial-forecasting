---
title: Benchmark conformal e atribuição por família — teoria do Step 7 (inferência determinística, CQR, H3, API)
description: Teoria canônica do subdomínio conformal-benchmark-and-feature-attribution — o que a inferência do candidato garante reproduzir, como o CQR assimétrico recalibra os pares da grade como benchmark de cobertura empírica sob dependência temporal, como se mede e se lê a contribuição das famílias de features entre horizontes (H3) e o que a API serve
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 7 (7.1–7.4), ao questionar a mecânica ou a variante do CQR, a leitura de H3 ou o contrato de reprodução da inferência, e antes de pré-registrar CQR e H3 para a 8.1
keywords: [domain, inference, determinism, reproducibility, dropout, mc-dropout, guardrail, conformal, split-conformal, cqr, asymmetric-cqr, nexcp, aci, enbpi, exchangeability, beta-coverage, empirical-coverage, h3, feature-attribution, vsn, permutation-importance, grouped-importance, loco, ablation, block-bootstrap, per-horizon, preregistration, api]
status: accepted
created_at: 2026-10-06
updated_at: 2026-10-06
bounded_context: inference
subdomain: conformal-benchmark-and-feature-attribution
references:
  - ../modeling/quantile-model-training.md
  - ../evaluation/probabilistic-forecast-evaluation.md
  - ../../adr/0_0_0057-inference-domain-doc-scope-and-boundary.md
  - ../../adr/0_0_0007-h3-family-contribution-across-horizons.md
  - ../../adr/0_0_0008-native-quantiles-with-conformal-benchmark.md
  - ../../adr/0_0_0016-four-feature-families.md
  - ../../adr/0_0_0010-paired-inference-dm-holm-mcs.md
  - ../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md
  - ../../adr/5_1_0002-dedicated-calibration-partition.md
  - ../../adr/5_4_0001-encoder-context-across-partitions.md
  - ../../adr/5_4_0002-single-multi-horizon-decoder.md
  - ../../adr/5_5_0001-frozen-hashed-cohort-spec.md
  - ../../adr/6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md
---

# Benchmark conformal e atribuição por família — teoria do Step 7

> **Categoria `domain/`** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este documento é a **teoria** (o quê/por quê) do subdomínio, transversal às
> Stages. Ele **não** é spec de implementação — não define schemas, caminhos de
> arquivo, nomes de classe nem cadências; isso pertence ao `technical.md` de
> cada Stage + código. Toda fórmula que muda um número reportado pelo projeto
> carrega citação rastreável a fonte primária. Onde a fonte **não** foi lida
> em primária, a citação carrega o rótulo `[CITAÇÃO-NÃO-ACESSADA]` e o texto
> diz o que está inferido; onde não existe fonte primária e a regra é política
> do projeto, o texto diz `[SEM-FONTE-PRIMÁRIA]` e a regra vira convenção
> (§10); contas feitas para este doc são marcadas como **derivação**. As
> bifurcações do gate foram triadas pela skill `evidence-resolution`
> (2026-10-05/06): as de classe E/C foram fechadas pelo agente e registradas em
> §10.1 no formato `[decision:E|C]`, com o degrau que decidiu; as duas de
> classe P (papel da VSN em H3 e desenho da ablação) foram decididas pelo
> humano em 2026-10-06. **Doc ratificado em 2026-10-06 por delegação do
> humano — gate do Step 7 fechado.**

## 1. Escopo e como consumir este doc

**Cobre** os blocos de teoria do Step 7, todos sobre o mesmo objeto (a grade de
quantis do candidato TFT, por horizonte — §2.1):

1. **inferência determinística** — o que a reprodução de uma predição garante,
   por que a seed não importa na inferência, dropout desligado, MC dropout fora,
   guardrail reusado e a emissão da partição de calibração (§3; Stage 7.1);
2. **conformal CQR como benchmark** — split conformal, CQR simétrico e
   assimétrico, os 4 invariantes, por que a permutabilidade falha em série
   financeira e o que sobra, a variante de registro e a sensibilidade, pares,
   seeds, dispersão por tamanho de calibração e a comparação descritiva com a
   calibração nativa (§4; Stage 7.2);
3. **atribuição por família para H3** — a H3 reformulada, VSN como descrição
   horizonte-invariante, importância por permutação de grupo, ablação LOCO com
   re-treino, incerteza, a regra de leitura (heterogeneidade + concordância) e a
   linguagem descritiva (§5; Stage 7.3);
4. **API** — sem teoria própria; o que o payload carrega conceitualmente (§6;
   Stage 7.4);

apoiados nos **fundamentos comuns** (§2), com uma seção sobre **pré-registro e
cegamento** (§7), a **seção-fronteira** (§8), o **vocabulário órfão** do roadmap
(§9), a tabela de convenções com o registro das decisões (§10) e as referências
(§11).

**Não cobre**:

- **Implementação** (value objects, serviços, ports, schemas, onde se persistem
  as predições de calibração, papel exato do MAPIE como backend ou oráculo,
  forma do pré-registro) → `technical.md` das Stages 7.1–7.4.
- **Definições de cobertura e sharpness** (ĉ(τ), PICP, MPIW, banda de Wilson,
  hits, convenção de empate) → reusadas **sem re-derivação** do
  [doc de avaliação §4](../evaluation/probabilistic-forecast-evaluation.md)
  (ADR 0.0.0054, Alt. B; evaluation §9.2).
- **Pinball, d_t, bootstrap estacionário e regra do bloco** → evaluation §2.4,
  §6.1, §6.5 (ponteiro).
- **Treino do TFT, grade, rearranjo, cohort** → [doc de modelagem](../modeling/quantile-model-training.md)
  §2, §5, §6 (ponteiro).
- **Mecânica do pré-registro** (TOML hasheado, âncora, emendas) → evaluation §8
  e ADRs 6.5.0001–6.5.0003.
- **Inferência causal** indicador→retorno (overview §3) e SHAP local
  (non-goal da 7.3).
- **ACI/EnbPI** além do motivo da exclusão (§4.6).

**Mapa de consumo** (que Stage lê o quê):

| Stage | Seções que consome |
|---|---|
| 7.1 — motor de inferência | §3 (+ §2) |
| 7.2 — conformal CQR | §4, §7 (+ §2, §3.4) |
| 7.3 — explicabilidade (H3) | §5, §7 (+ §2) |
| 7.4 — API de inferência | §6 (+ §4.11 rótulo, §5.8 linguagem) |
| 8.1 — execução confirmatória | §4.11–§4.12 (eixo comparativo), §5.7–§5.8 (regra de leitura de H3), §7 |
| 8.3 — plots e relatório | §4.11 e §5.8 (o que se mostra e com que rótulo), §5.3 (VSN) |
| todas | §2 (fundamentos) e §8 (fronteira) |

**Hierarquia de fontes.** Overview > Roadmap > este doc > `concept.md` das
Stages. O que já estava ratificado no repo (overview §3/§4/§8/§10/§11, doc de
modeling §2.4/§5/§6/§7, doc de evaluation §2/§4/§6/§8, ADRs 0.0.0010,
0.0.0016, 4.3.0002, 5.1.0002, 5.4.0001, 5.4.0002, 5.5.0001, 6.5.0008) é citado
como tal e **não** re-derivado; a pesquisa externa entrou só nas lacunas, sob a
barra de fontes do gate (`PROMPT-step-single-session.md` §1). Preprints entram
**só como contexto** (rótulo "preprint"), nunca como base de decisão de classe E.

## 2. Fundamentos comuns

### 2.1 O objeto

Para cada fold, seed e horizonte h ∈ {1, 7} (h+30 não é avaliado — fora do
cohort), o candidato TFT emite uma grade de **7 quantis**
G = {0.02, 0.10, 0.25, 0.50, 0.75, 0.90, 0.98}, rearranjada pelo guardrail
(modeling §2.4; ADR 4.3.0002). A grade é simétrica e se organiza em **3 pares
simétricos** (0.02, 0.98), (0.10, 0.90), (0.25, 0.75) mais a mediana
(evaluation §2.1). Um único modelo por fold emite todos os horizontes como
passos do decoder (ADR 5.4.0002). O cohort que congela tudo isso é o da 5.5
(ADR 5.5.0001; modeling §6).

O Step 7 trabalha **sobre** esse objeto: a 7.1 o reproduz, a 7.2 recalibra
pares dele, a 7.3 mede quanto cada família de features contribui para a perda
dele, a 7.4 o serve.

### 2.2 Por horizonte, sempre

Toda grandeza deste doc é por horizonte: o CQR calibra cada horizonte
separadamente (§4.7) e H3 **compara** horizontes por meio de grandezas
calculadas por horizonte, nunca de uma perda agregada entre horizontes
(overview §7; evaluation §2.7, §8.7; ADR 0.0.0010).

### 2.3 Seeds

O candidato tem 10 seeds (cohort 5.5). Seeds são réplicas do mesmo ponto
alinhado, não observações novas: perdas entram como **média ponto a ponto**;
coberturas como **média entre seeds**, com n ≈ T (nunca S·T); a dispersão entre
seeds vai ao perfil (evaluation §6.9, §8.4; ADR 0.0.0010 item 5, B-SEEDS;
Bouthillier et al. 2021). O Step 7 herda essa regra: o CQR conformaliza **cada
seed** e reporta a média das coberturas (§4.9); H3 agrega seeds pela média
ponto a ponto (§5.6).

### 2.4 Cobertura empírica × garantida

"Cobertura" aqui é sempre a **frequência observada** no teste, com as
definições do evaluation §4 (ĉ(τ) §4.1; PICP/MPIW §4.2; Wilson §4.4; empate
§4.5). Garantias de cobertura em amostra finita existem **só** sob
permutabilidade (§4.1); em série financeira ela falha (§4.4). Por isso o
projeto nunca diz "cobertura garantida" — diz **"cobertura empírica (não
garantida)"** (overview §8 R-CONFORMAL-1; ADR 5.1.0002).

### 2.5 Notação

    G               grade de 7 quantis; K = 7 níveis
    (τ_lo, τ_hi)    par simétrico, τ_hi = 1 − τ_lo
    α_lo, α_hi      miscobertura-alvo por cauda: α_lo = τ_lo, α_hi = 1 − τ_hi
    α               miscobertura do par: α = α_lo + α_hi = 2·τ_lo
    n               tamanho do calib por fold e horizonte (252 no cohort)
    E_i             escore de não-conformidade do ponto i do calib
    Q̂_{1−a}(E)      ⌈(n+1)(1−a)⌉-ésimo menor escore (quantil de amostra finita)
    L_t             pinball média na grade no ponto t (evaluation §2.4)
    f               família de features ∈ {price, technical, sentiment, fundamental}
    I_f(h)          importância da família f no horizonte h (perda média a mais)
    s_f(h)          participação: I_f(h) / Σ_g I_g(h)
    Δ_f             s_f(h+7) − s_f(h+1)
    S, K_p          nº de seeds; nº de permutações por família

### 2.6 O que o Step 5 e o Step 6 prometem (ponteiro)

Consumido sem re-derivar: a grade comum em formato long, uma observação por
`target_timestamp`, a pinball como loss de treino e métrica, o rearranjo que
corrige monotonicidade e **não** calibração (modeling §2.4, §7); a partição
`calib` dedicada, disjunta, mais recente e embargada (modeling §2.5; ADRs
5.1.0001–5.1.0003); a tipagem known/observed do TFT (modeling §5.2; ADR
5.4.0004); o objeto avaliado, a pontuação do vetor rearranjado, as definições
de cobertura, o bootstrap estacionário e o pré-registro (evaluation §2, §4,
§6.5, §8).

## 3. Inferência determinística (Stage 7.1)

### 3.1 Contrato de reprodução

**O que é reproduzir.** Dado o artefato treinado de um (fold, seed), o mesmo
dataset de entrada e os mesmos parâmetros de inferência, a grade emitida deve
sair igual. "Igual" precisa de escopo, porque a aritmética de ponto flutuante
não é associativa: "Due to roundoff errors, the associative laws of algebra do
not necessarily hold for floating-point numbers" (Goldberg 1991, §Systems
Aspects › Languages and Compilers › Ambiguity). A documentação do PyTorch tira
a consequência: "floating point addition and multiplication are not
associative, so the order of the operations affects the results. Because of
this, PyTorch is not guaranteed to produce bitwise identical results"
(PyTorch v2.13.0, `notes/numerical_accuracy.md`); e, em lote, "`(A@B)[0]` ...
is not guaranteed to be bitwise identical to `A[0]@B[0]`" (mesmo doc,
§Batched computations). Sobre ambientes: "Completely reproducible results are
not guaranteed across PyTorch releases, individual commits, or different
platforms" (`notes/randomness.md`, §Reproducibility); o modo determinístico
promete algoritmos que, "given the same input, and when run on the same
software and hardware, always produce the same output" (docstring de
`torch.use_deterministic_algorithms`, v2.13.0). A falta de reprodutibilidade
sob paralelismo + não-associatividade é tema conhecido de computação numérica
(Ahrens, Demmel & Nguyen — abstract do relatório técnico UCB/EECS-2016-121;
versão de periódico `[CITAÇÃO-NÃO-ACESSADA]`).

**Convenção (A1 — decidida, §10.1).** A reprodução é **bit a bit só no mesmo
ambiente pinado**: mesma build do torch, mesmo SO/CPU, **tamanho de lote de
inferência fixo e registrado** (o lote muda a ordem das somas), carregamento sem
paralelismo. **Entre ambientes**, a igualdade é **por tolerância declarada** —
o mesmo regime da equivalência da 8.2 (overview ASSUM-4; roadmap ROADMAP-5) e
o mesmo escopo do determinismo do treino (concept 5.4 I9: "no mesmo processo e
ambiente"; reprodutibilidade entre plataformas "não é afirmada"). O padrão
"tolerância declarada" não tem fonte primária própria `[SEM-FONTE-PRIMÁRIA]` —
é a consequência prática das fontes acima. Isto **qualifica** o "bit a bit" sem
escopo da DoD original da 7.1. Lacunas declaradas: a documentação não promete
determinismo entre processos distintos na mesma máquina (só "same
environment"), e o efeito do número de threads intra-op não foi verificado — o
`technical.md` da 7.1 fixa e registra esses parâmetros.

**Referência de reprodução da 7.1.** A referência é o **artefato**
(checkpoint) de cada (fold, seed) **re-executado no mesmo ambiente**, com o
lote de inferência igual ao `batch_size` do treinador — o treinador emite as
predições de teste com o mesmo `batch_size` do treino (111 no cohort;
`pf_tft_trainer.py` l. 258–266 e 311–317; `config/cohorts/aapl_confirmatory.toml`
l. 119). Comparar a reprodução com as predições de teste **já persistidas no
silver** é **teste de equivalência por tolerância**, não bit a bit — a menos
que o lote e o ambiente coincidam com os da corrida que as gravou.

### 3.2 Seed, dropout e por que MC dropout fica fora

**A seed não importa na inferência.** Nenhum componente do caminho de predição
consome o gerador aleatório: a perda quantílica devolve as próprias saídas da
rede como quantis (`QuantileLoss.to_quantiles` → `return y_pred`,
pytorch-forecasting 1.8.0), o dataset de predição é construído sem
randomização de comprimento (`stop_randomization`), e o carregamento roda sem
workers. Inferido do código, não testado — o teste fica para a 7.1.

**Dropout desligado.** O laço de predição do Lightning chama `.eval()` no
modelo ("The predict loop by default calls ``.eval()``", Lightning 2.6.5,
`core/hooks.py`), e em avaliação o `nn.Dropout` "simply computes an identity
function" (torch 2.13.0, `nn/modules/dropout.py`). Todo dropout do TFT é
`nn.Dropout` ou dropout interno de LSTM, ambos sujeitos ao modo de treino.

**MC dropout fora (A2 — decidida, §10.1).** Manter o dropout ligado na
predição e repetir passadas estocásticas é outra coisa: "We refer to this Monte
Carlo estimate as MC dropout. In practice this is equivalent to performing T
stochastic forward passes through the network and averaging the results" (Gal
& Ghahramani 2016, §4, Eq. (6)) — o objeto é uma distribuição preditiva
aproximada da incerteza **do modelo** (epistêmica), distinta da incerteza
inerente aos dados (aleatória): "Aleatoric uncertainty captures noise inherent
in the observations. On the other hand, epistemic uncertainty accounts for
uncertainty in the model" (Kendall & Gal 2017, Abstract). A grade quantílica
nativa estima quantis condicionais de y (Koenker & Bassett 1978; modeling §2.2)
— objeto do H1. MC dropout mudaria o objeto e reintroduziria dependência de
seed na inferência.

### 3.3 Guardrail reusado

A inferência **reusa** o rearranjo monótono já ratificado (ADR 4.3.0002;
fundamento em modeling §2.4, Chernozhukov, Fernández-Val & Galichon 2010
Prop. 4) — não cria um serviço novo de guardrail (**A3**, §10.1). O rearranjo
conserta ordem, não calibração, e não mascara degeneração, que é gate separado
(modeling §7 item 4; evaluation §5.4).

### 3.4 Emissão da partição de calibração (requisito de fronteira 7.1 → 7.2)

O CQR precisa das predições do candidato na partição `calib` de cada fold
(§4.1). Hoje os treinadores só emitem a partição de teste; o concept 5.2
delega essa emissão à inferência. **Requisito (A4, §10.1):** a 7.1 emite, para
cada (fold, seed, horizonte) do candidato, as predições sobre `calib` com o
mesmo artefato e o mesmo contrato de reprodução de §3.1. Ler o contexto do
encoder sobre sessões de `early_stop`/`calib` anteriores à decisão é legítimo
(ADR 5.4.0001); usar `calib` para ajustar ou selecionar qualquer coisa não é
(ADR 5.1.0002). Onde e como essas predições se persistem é decisão do
`technical.md` da 7.1, não deste doc.

## 4. Conformal CQR como benchmark (Stage 7.2)

### 4.1 Split conformal e CQR

**Split conformal** (Lei et al. 2018): ajusta-se o preditor numa partição de
treino; numa partição de **calibração disjunta** calculam-se escores de
não-conformidade; o quantil de amostra finita desses escores define a correção
do intervalo. A validade vem da separação de papéis (ADR 5.1.0002; modeling
§5.3: o `early_stop` é seleção e por isso nunca é calib).

**CQR** (Romano, Patterson & Candès 2019) aplica isso a um par de quantis
(q̂_lo, q̂_hi). O escore é

    E_i = max{ q̂_lo(X_i) − Y_i ,  Y_i − q̂_hi(X_i) }                (Eq. (9))

e o intervalo é [q̂_lo(X) − Q̂, q̂_hi(X) + Q̂], com Q̂ = "(1 − α)(1 + 1/|I2|)-th
empirical quantile of {E_i : i ∈ I2}" (Eq. (11); I2 = calib, |I2| = n) —
(numeração de equação não conferida) — isto
é, o ⌈(n+1)(1−α)⌉-ésimo menor escore. **Theorem 1:** "If (X_i, Y_i), i = 1, …,
n + 1 are exchangeable … P{Y_{n+1} ∈ C(X_{n+1})} ≥ 1 − α"; com escores quase
certamente distintos, a cobertura também é "≤ 1 − α + 1/(|I2| + 1)"; a prova
vale "even … conditionally on the proper training set". O escore é negativo
quando y cai dentro do par e positivo fora: o CQR **encolhe** ou **alarga** o
par conforme a cobertura que ele teve no calib.

### 4.2 A versão assimétrica (Theorem 2)

O Theorem 1 "allows coverage errors to be spread arbitrarily over the left and
right tails". O **Theorem 2** (Romano et al. 2019, §4, Eqs. (15)–(16)) calibra
as caudas separadamente, com escores unilaterais

    E_i^lo = q̂_lo(X_i) − Y_i          E_i^hi = Y_i − q̂_hi(X_i)

e garante, sob permutabilidade, P{Y ≥ q̂_lo − Q̂_{1−α_lo}(E^lo)} ≥ 1 − α_lo e
P{Y ≤ q̂_hi + Q̂_{1−α_hi}(E^hi)} ≥ 1 − α_hi — "control[s] the left and right
tails independently". Com α_lo = τ_lo e α_hi = 1 − τ_hi, cada limite
conformalizado tem miscobertura de cauda ≤ τ_lo, e o par cobre ≥ τ_hi − τ_lo
(união das caudas).

**Convenção (B1 — decidida, §10.1): CQR assimétrico.** O gate de H1 é **por
cauda** (evaluation §8.5, §10 conv. 26; ADR 0.0.0011; ADR 6.5.0006), e o
argumento do evaluation §4.2 — o PICP é invariante a um deslocamento comum das
caudas — vale igual para o intervalo conformal: só o Theorem 2 produz um objeto
comparável cauda a cauda com o nativo. Custo declarado: intervalos um pouco mais
largos ("the average length for CQR neural networks increases from 1.40 to
1.58, while the coverage rate stays about the same", Romano et al. 2019,
§6.2).

**Nota de fonte.** O enunciado do Theorem 2 na v1 do paper fala em
"(1 − α_lo)-th empirical quantile", sem o fator (1 + 1/n), mas a prova usa o
Lemma 2, que é a versão inflada; o projeto usa a **inflada**, que é também a do
MAPIE (§4.12). **Derivação:** aplicando o argumento do Theorem 1 a cada escore
unilateral (escores distintos), a miscobertura de cada cauda fica em
[τ_lo − 1/(n+1), τ_lo] sob permutabilidade — o limite inferior é conta deste
doc, não enunciado do paper.

### 4.3 Os 4 invariantes

Ratificados em overview §8 (R-CONFORMAL-1) e no roadmap 7.2, com redações
ligeiramente diferentes; este doc os fixa assim (ADR 0.0.0008):

1. **Calib dedicado.** Calibra-se só na partição `calib` — disjunta do treino e
   do `early_stop`, a mais recente antes do teste, nunca usada em seleção (ADR
   5.1.0002; modeling §5.3, §8 conv. 10).
2. **Por fold e por horizonte.** Uma calibração por (fold, horizonte, seed,
   par, cauda); nada é reutilizado entre folds nem agregado entre horizontes
   (§2.2, §4.7).
3. **Embargo.** O `calib` termina `max_horizon + embargo` sessões antes do
   teste (no cohort, 14 pregões — concept 5.5 D7, valor `[SEM-FONTE-PRIMÁRIA]`
   declarado lá), de modo que nenhum alvo do calib se sobrepõe ao teste.
4. **Linguagem: cobertura empírica.** Todo número de cobertura do CQR é
   rotulado "cobertura empírica (não garantida)" (§2.4). O "linguagem" do
   overview e o "cobertura **empírica**" do roadmap são o mesmo invariante.

A recência do calib não é um quinto invariante: ela é o que o ADR 5.1.0002
escolheu e é o que torna a variante sem pesos defensável (§4.5).

### 4.4 Por que a permutabilidade falha — e o que sobra

Retornos diários têm dependência serial na escala (clustering de volatilidade)
e mudam de regime; os escores do calib e o ponto de teste não são permutáveis.
O que a literatura oferece sem permutabilidade são **limites com um termo de
perda**:

- **Barber et al. (2023), §4.1 Theorem 2** (p. 15): com pesos fixos w_i,
  P{Y_{n+1} ∈ Ĉ_n(X_{n+1})} ≥ 1 − α − Σ_i w̃_i · d_TV(R(Z), R(Z^i)), e "the same
  result holds true for nonexchangeable split conformal"; com w_i ≡ 1 o termo
  mede a perda do split comum. §4.4 (pp. 18–19): sob uma quebra (changepoint)
  ocorrida k passos atrás, o termo de perda fica "≤ ρ^k. This yields a small
  coverage gap as long as k is large".
- **Oliveira et al. (2024)**: Theorem 1 (p. 5), cobertura ≥ 1 − α − ε_cal −
  δ_cal − ε_train; Theorem 4 (p. 8), sob β-mixing estacionário, ε_train =
  β(i − n_train), da mesma ordem que no caso iid quando β(k) ≤ k^(−b);
  Theorem 6 (§3.4, p. 9), split não ponderado em série não estacionária,
  ≥ 1 − α − η − δ(j), com δ(j) a distância de variação total entre o teste e o
  ponto de calibração.
- **Chernozhukov, Wüthrich & Zhu (2018)**, §3.2 Theorem 2 (p. 7): validade
  "approximately valid" sob ergodicidade aproximada — fundamento de validade
  aproximada sob dependência.

**O que sobra.** Sob dependência fraca e estacionária, o split conformal perde
pouco; sob mudança de distribuição entre calib e teste, a perda é proporcional
à distância entre elas e **nenhum** limite é calculável na prática (os termos
dependem da distribuição desconhecida). E há um caso que nenhum limite cobre:
o CQR é calibrado **uma vez por fold**, e uma quebra de regime **dentro** da
janela de teste tem, para os pontos posteriores a ela, k = 0 no bound de Barber
§4.4 — inferência deste doc a partir do enunciado, sem fonte que a discuta para
CQR. Consequência: a cobertura do CQR é sempre reportada como **empírica**
(§4.3 item 4), e a comparação com o nativo é descritiva (§4.11).

### 4.5 Variante: split-CQR de registro + NexCP como sensibilidade

**Variante de registro (B2 — decidida, §10.1): split-CQR assimétrico sem
pesos.** Degrau 2: é o default do oráculo de referência (o MAPIE 1.5.0 não
implementa pesos — §4.12), e a recência — o motivo para ponderar — já está
garantida pelo calib mais recente (ADR 5.1.0002). "Não fazer CQR" não é opção:
contraria overview §3/§11, onde o CQR é o benchmark ratificado.

**Sensibilidade pré-registrada: NexCP.** O conformal não permutável de Barber
et al. (2023) troca a distribuição empírica dos escores por uma ponderada:

    Ĉ_n(X_{n+1}) = μ̂(X_{n+1}) ± Q_{1−α}( Σ_{i=1..n} w̃_i·δ_{R_i} + w̃_{n+1}·δ_{+∞} )
    w̃_i = w_i / (w_1 + … + w_n + 1)                          (Eqs. (10)–(11), pp. 10–11)

com "the weights w_i … fixed" (§3.1, p. 10), estendido a "arbitrary
nonconformity scores" no Appendix A — logo aplicável aos escores unilaterais
do CQR (composição deste doc: cada cauda com seus escores e o mesmo esquema de
pesos). Os experimentos do paper usam w_i = 0,99^(n+1−i) (§5.1, p. 22); como
escolher pesos de forma ótima fica "for future work" (§4.3, p. 18). Esquema do
projeto: **w_i = ρ^(n+1−i), ρ = 0,99**, reportado como **perfil**, nunca
veredito (evaluation §8.6).

**Por que não ρ ≤ 0,98 (derivação, Eq. (10), n = 252).** A massa do ponto
+∞ é

    w̃_{n+1} = 1 / Σ_{j=0..n} ρ^j = (1 − ρ) / (1 − ρ^(n+1))

ρ = 0,99 → 0,0109; ρ = 0,98 → 0,0201; ρ = 0,97 → 0,030. Se w̃_{n+1} > α_cauda, o
quantil (1 − α_cauda) cai no átomo em +∞ e o limite conformalizado vira
infinito. Na cauda extrema (α_cauda = 0,02), ρ = 0,98 já dá 0,0201 > 0,02: o
par 0.02/0.98 deixaria de ter limite finito. Com ρ = 0,99 o tamanho efetivo de
Kish do calib cai de 252 para ≈ 170 (com 0,98, ≈ 98) — a sensibilidade troca
viés de recência por mais variância. Nenhuma fonte calibra ρ para retornos
diários; ρ = 0,99 é o valor dos experimentos de Barber §5.1 e o maior que não
degenera a cauda extrema `[SEM-FONTE-PRIMÁRIA para o valor]`.

**Contexto (preprint, não base).** Stocker et al. (2025) — a referência "*A
Gentle Introduction to Conformal Time Series Forecasting*" já citada sem autores
no ADR 5.1.0002 — relatam o split conformal caindo para ≈ 0,84 de cobertura
nominal 0,90 num cenário de mudança de média (§4.3, p. 15) e recomendam
ponderação com decaimento (p. 17). É de onde vem o "0,90 → 0,84" do ADR
5.1.0002; entra aqui só como motivação da sensibilidade.

### 4.6 ACI e EnbPI fora do confirmatório

**ACI** (Gibbs & Candès 2021) atualiza o nível a cada passo,
α_{t+1} := α_t + γ(α − err_t) (Eq. (2), p. 3); a garantia principal é de
**frequência de longo prazo** — |1/T Σ err_t − α| ≤ (max{α_1, 1−α_1} + γ)/(Tγ)
(Prop. 4.1, p. 6) — e depende de atualização online com Y_t observado a cada
passo. Cobertura marginal o paper só afirma **aproximada**, sob pequenos
drifts num modelo específico (§4.2). O caso em que Y chega "in a delayed
fashion or in large batches" é problema aberto (§7, p. 10) — exatamente h+7. **EnbPI** (Xu & Xie 2021, 2023) "leverages
feedback by updating past residuals using a sliding window" (§3.1, p. 4); sem
feedback ("When s = ∞, no feedback is available", §3, item (5)) a garantia
aproximada do Theorem 1 apoia-se em resíduos estacionários e fortemente
mixing (§4.1, Assumption 1). Oliveira et al. (2024, §2, p. 4) resumem, na
leitura deles, que ACI e afins "have no marginal coverage guarantees, and the
online aspect of their method, which requires updates at every step, may be
undesirable" — a ressalva que pesa aqui é a segunda. **B3 (decidida, §10.1):**
ambos ficam fora do caminho confirmatório — o motivo é o **online**: suas
garantias pressupõem atualização com o realizado a cada passo, incompatível
com a calibração uma vez por fold dos 4 invariantes.

### 4.7 Por horizonte: cobertura marginal, não conjunta

**B4 (decidida, §10.1):** calibra-se **cada horizonte separadamente** e
reporta-se a cobertura marginal por horizonte (Oliveira et al. 2024, Theorems
1 e 4; overview §7; ADR 0.0.0010). A alternativa de cobertura **conjunta** sobre
os horizontes — dividir α por H e corrigir cada horizonte por Bonferroni
(Stankevičiūtė et al. 2021, §3.3, p. 5: "the original α is divided by H") — foi
descartada: o próprio paper exige "a set of independent time-series" (Fig. 1,
p. 3), e numa série única "temporally dependent (non-exchangeable)" o Theorem 1
dele não se aplica; além disso, cobertura conjunta é outra pergunta que não a
do H1. Lacuna declarada: resíduos de h+7 se sobrepõem no tempo, o que aumenta
o termo ε_cal de Oliveira (inferência; sem fonte primária sobre resíduos
h-passos sobrepostos em split conformal).

### 4.8 Pares, assimetria e aninhamento

**Quais pares (B5 — decidida, §10.1).** O CQR assimétrico é aplicado aos **3
pares simétricos** da grade, cada cauda calibrada independentemente; o **par
primário de comparação é (0.10, 0.90)** — o mesmo do gate de H1 (ADR
6.5.0006). Os outros dois pares são perfil.

**Por que não conformalizar a distribuição inteira.** O conformal
distribucional (Chernozhukov, Wüthrich & Zhu 2021, Alg. 2: escore
ψ(F̂(Y_t, X_t)) com ψ(x) = |x − 1/2|; Vovk et al. 2019, Def. 1) produz uma
família aninhada por construção, mas exige F̂ contínua; com 7 quantis isso
obriga a interpolar entre níveis e **extrapolar além de [0.02, 0.98]** —
justamente as caudas onde H1 se decide. Rejeitado.

**Aninhamento não garantido.** CQR por par não é aninhado por construção: na
família de Gupta, Kuchibhotla & Ramdas (2022, Tab. 1) o CQR é
[q̂_{α/2}(x) − t, q̂_{1−α/2}(x) + t], com o par de base dependente de α — nada
impede o limite conformalizado de 0.10 ficar abaixo do de 0.02. **Convenção:**
a saída conformal **não é rearranjada** — rearranjar mudaria cada limite e a
garantia por cauda do Theorem 2 é sobre cada limite como calibrado; a **taxa de
violação de aninhamento** entre pares conformalizados é reportada como perfil.
(Uma derivação do pesquisador sugere que ordenar limites unilaterais preserva a
garantia nível a nível; sem fonte primária, não é adotada.)

**Insumo do CQR.** O par de base é o do **vetor rearranjado** — a previsão
entregue (§3.3; evaluation §2.2, que pontua só o rearranjado). Consequência de
A3 + evaluation §2.2, não decisão nova.

**Par extremo.** Com n = 252, a cauda 0.02 tem τ·n ≈ 5 pontos de calib além do
limite (concept 5.5 D6: "afeta o CQR da 7.2 nesses níveis"). O par é
**reportado, sem exclusão**, com a dispersão de §4.10 ao lado.

### 4.9 Seeds

**B6 (decidida, §10.1):** conformaliza-se **cada seed separadamente** (cada
seed tem seu artefato e suas predições de calib) e reporta-se a **média das
coberturas** entre seeds, com a dispersão no perfil — coerente com ADR 0.0.0010
item 5 ("Coverage and degeneracy are seed means"), que rejeitou o ensemble de
predições por mudar o objeto. Conformalizar a média das seeds também é válido
("The estimators can be even be aggregates of different quantile regression
algorithms" [sic], Romano et al. 2019, §4; Fakoor et al. 2023, §5.3), mas
avaliaria um ensemble, que não é o candidato. Combinar os conjuntos das seeds
por voto dá só 1 − 2α (Gasparin & Ramdas 2024, Theorem 2.1 — preprint,
contexto).

### 4.10 Dispersão por tamanho de calibração

Mesmo sob permutabilidade, a cobertura **condicional ao calib sorteado** varia:
ela segue Beta(n + 1 − l, l) com l = ⌊(n + 1)α⌋ (Angelopoulos & Bates 2023,
§3.2; Vovk 2012, Prop. 2, para a versão (ε, δ)). Para n = 252 (**derivação**,
quantis da Beta calculados para este doc):

| Objeto | α | Beta | média | dp | IC 90 % |
|---|---|---|---|---|---|
| par 0.02/0.98 (simétrico) | 0,04 | (243, 10) | 0,961 | 0,012 | [0,939; 0,978] |
| par 0.10/0.90 (simétrico) | 0,20 | (203, 50) | 0,802 | 0,025 | [0,760; 0,842] |
| par 0.25/0.75 (simétrico) | 0,50 | (127, 126) | 0,502 | 0,031 | [0,450; 0,554] |
| cauda 0.02 (assimétrico) | 0,02 | (248, 5) | 0,980 | 0,0087 | [0,964; 0,992] |
| cauda 0.10 (assimétrico) | 0,10 | — | — | 0,019 | — |
| cauda 0.25 (assimétrico) | 0,25 | — | — | 0,027 | — |

Leitura: com um calib de 252, um fold pode cobrir 0,94 ou 0,98 no par extremo
**sem nada errado** — a variação por fold é esperada e não é evidência contra o
método. Angelopoulos & Bates sugerem n ≈ 1000 como suficiente "for most
purposes" (guia, não regra). O quantil é finito sempre que α ≥ 1/(n + 1)
(Angelopoulos & Bates, App. D: "q̂ = ∞ otherwise"); com n = 252 isso só falharia
para α < 1/253 ≈ 0,004 — não ocorre na grade. **Ressalvas:** a Beta pressupõe
permutabilidade e escores contínuos — sob dependência é **referência**, não
banda; a cobertura observada no teste é ainda mais dispersa (Beta-Binomial,
Angelopoulos & Bates, App. C).

### 4.11 Comparação nativo × conformal: descritiva

**B8 (decidida, §10.1).** O CQR é **benchmark comparativo** — não régua de H1
(evaluation §4.4, alt. (ii) rejeitada) nem membro da família de H2 (evaluation
§6.4). A comparação reusa **sem re-derivar** as definições do evaluation §4:
ĉ(τ) por cauda conformalizada, PICP/MPIW por par, banda de Wilson com o mesmo
n (pontos alinhados, nunca S·T) e hits. **Nenhum teste de hipótese novo** é
introduzido. O que ela responde é a pergunta da banca: "quanto a calibração
nativa fica atrás (ou à frente) de uma recalibração empírica feita no calib
mais recente?" — com o rótulo obrigatório **"cobertura empírica (não
garantida)"** em toda tabela, gráfico e payload.

### 4.12 Referência de oráculo (MAPIE)

**B9 (decidida, §10.1).** O papel exato do MAPIE (backend × oráculo de uma
implementação própria no domínio) é decisão do concept/technical da 7.2, pelo
padrão ADR 0.0.0056 / 6.1.0001. Este doc só registra a fórmula que o MAPIE usa,
como referência de oráculo: q = (1 − α)(1 + 1/n), com `np.quantile(...,
method="higher")`, e por padrão (`symmetric_correction=False`) α/2 por cauda —
o Theorem 2 de Romano (§11.3). Para os α da grade, o posto resultante coincide
com ⌈(n + 1)(1 − α)⌉ em n = 252 (derivação).

### 4.13 O que é pré-registrado do CQR

Variante de registro (split-CQR assimétrico sem pesos), sensibilidade NexCP
(ρ = 0,99, pesos fixos), os 3 pares e o par primário de comparação,
assimetria, tratamento de seeds (por seed, média das coberturas), por horizonte,
a métrica de comparação (§4.11) e a ausência de rearranjo da saída conformal.
Mecanismo e ordem: §7.

## 5. Atribuição por família para H3 (Stage 7.3)

### 5.1 H3 reformulada

**Texto ratificado (overview §4; ADR 0.0.0007; decisão P do humano,
2026-10-06):**

> **H3 — Contribuição de features (descritiva).** A contribuição relativa das
> famílias (preço, técnico, sentimento, fundamento) é **heterogênea entre h+1 e
> h+7**: para ao menos uma família, a variação da sua participação entre os
> horizontes tem o **mesmo sinal na importância por permutação e na ablação por
> família** (LOCO com re-treino), com intervalo (bootstrap em bloco pareado)
> excluindo zero nos dois métodos. Os pesos da VSN são reportados como
> descrição geral, horizonte-invariante, de quanto o modelo usa cada família.
> Sem claim causal.

**Por que o "≥ 2 de 3 métodos" saiu.** O texto antigo previa triangular VSN,
permutação e ablação. Mas a VSN deste modelo **não tem eixo de horizonte**
(§5.3): com as 55 features como observed (só encoder) e um decoder único
multi-horizonte, os pesos são os mesmos para h+1 e h+7 por construção — a VSN
não pode votar sobre heterogeneidade entre horizontes. Manter "≥ 2 de 3"
prometeria uma triangulação inexistente; trocar a VSN por um terceiro método
resolvido por horizonte (ex.: gradientes integrados por saída) foi descartado
pelo humano (ADR 0.0.0007, alternativas). Restam **dois métodos que resolvem
horizonte**, e H3 exige que **concordem**.

### 5.2 A unidade: as 4 famílias

A unidade de H3 é a família (ADR 0.0.0016; ADR 3.4.0002): price,
technical, sentiment, fundamental — partição mutuamente exclusiva das 55
features do registry.

**Features sem família (C6 — decidida, §10.1).** O TFT também recebe o
calendário (`day_of_week`, `month`, known), o alvo passado e o índice relativo
de tempo — fora do registry e de qualquer família. Eles **não são permutados
nem ablacionados**: ficam no modelo em todas as configurações, e a participação
s_f é calculada **só sobre as 4 famílias**. As interações cross-família
(`sentiment_x_volatility`, `sentiment_x_volume`) seguem o rótulo do registry
(sentiment) — ressalva declarada: parte do sinal atribuído a sentiment passa
por variáveis de outras famílias.

**Premissa verificável antes da 7.3 (C6, P-H3-VSN).** Nenhuma feature de
família é `known`: hoje a registry só tem specs `unknown` (observed), e o caso
de uso do TFT incorpora **automaticamente** qualquer spec `known` às entradas
do decoder (`train_tft.py` l. 23–26, 196–207). Se uma feature de família passar
a `known`, a VSN do decoder ganha eixo de horizonte, o argumento de §5.3 deixa
de valer e a decisão P-H3-VSN deve ser **reaberta**.

**Ressalva pendente — partição da volatilidade.** O ADR 0.0.0016 diz que
features derivadas de preço "(returns, momentum, drawdown, volatility) all
belong to the **price** family", mas o registry classifica seis features de
volatilidade (`volatility_20d`, `volatility_parkinson`,
`volatility_garman_klass`, `downside_semivolatility`, `vol_of_vol`,
`volatility_regime`) como **technical**. A divergência muda a partição de H3 e
fica **fora do escopo deste doc** (issue separada, a abrir): ela **precisa estar
resolvida antes do pré-registro de H3**, porque a partição é parte do que se
pré-registra (§7).

### 5.3 VSN: descrição geral, horizonte-invariante

**Definição.** No TFT, cada grupo de entradas (estáticas, passadas, futuras)
tem sua *variable selection network*: "Variable selection weights are generated
by feeding both Ξ_t and an external context vector c_s through a GRN, followed
by a Softmax layer" (Lim et al. 2021, §4.2, Eq. (6)) — v_{χ_t} =
Softmax(GRN(Ξ_t, c_s)), um vetor de pesos por passo de tempo que soma 1 sobre
as variáveis; "All static, past and future inputs make use of separate variable
selection networks" (§4.2). A entrada processada é a soma ponderada das
transformações de cada variável (Eq. (8)).

**Por que é horizonte-invariante aqui.** Os pesos dependem do passo do encoder
e do contexto estático — não do passo do decoder. Todas as 55 features são
observed (só entram no encoder, até t — modeling §5.2); a VSN do decoder só vê
entradas known (calendário). Logo, para um mesmo ponto de decisão, os pesos das
famílias são **os mesmos** para h+1 e h+7 (Lim 2021 §4.2 Eq. (6), §7.1 Eq.
(27); pytorch-forecasting 1.8.0 — a VSN do encoder é aplicada só às posições
do encoder, e a agregação de interpretação faz a média sobre os passos do
encoder — §11.3; trechos conferidos por verificador adversarial). A análise
por horizonte que o paper faz (§7.2) é da **atenção temporal**, não da VSN.

**Como se reporta (C5, parte VSN).** Como o paper: agregam-se os pesos de cada
variável sobre o teste e reportam-se os **percentis 10/50/90** ("we aggregate
selection weights ... for each variable across our entire test set, recording
the 10th, 50th and 90th percentiles of each sampling distribution", Lim 2021,
§7.1); por família, a **soma** dos pesos das suas variáveis = parcela da massa
softmax (a soma, e não a média, porque o softmax reparte uma unidade entre
variáveis; agregar por família não tem fonte — `[SEM-FONTE-PRIMÁRIA]`). Rótulo
obrigatório: "horizonte-invariante; descreve quanto o modelo usa cada família".

**Ressalvas.** Peso não é efeito: o peso multiplica uma transformação não
normalizada da variável (Eq. (8)), então peso alto não implica contribuição
alta para a previsão. E pesos de gating/atenção não são explicação causal:
"learned attention weights are frequently uncorrelated with gradient-based
measures of feature importance" (Jain & Wallace 2019, abstract); se servem de
explicação "depends on one's definition of explanation" (Wiegreffe & Pinter
2019, conclusão).

### 5.4 Importância por permutação de grupo

**Esquema (C1 — decidida, §10.1).** Para cada família f, permuta-se entre as
amostras do teste a **janela inteira** (todos os lags do encoder) de **todas**
as features de f, **em conjunto**; o resto da entrada fica intacto e o modelo
fica fixo. É o "switch" de Fisher, Rudin & Dominici (2019, §2) com um
subconjunto multivariado de covariáveis ("the covariate subsets X_1 ... may each
be multivariate"); a importância de grupo é a quantidade certa porque, "in
general, the grouped variable importance is not comparable with the sum of the
individual importances" — com a exceção explícita "If f is additive and if the
variables of the group are independent, the grouped variable importance is
nothing more than the sum of the individual importances" (Gregorutti, Michel &
Saint-Pierre 2015, arXiv:1411.4170 §2.1; versão publicada CSDA 90). A exceção
não se aplica aqui (inferência deste doc: o TFT não é aditivo e as features de
uma família são correlacionadas), então se permuta o grupo em vez de somar
importâncias individuais. Embaralhar
**dentro** do tempo (a ordem dos lags) foi rejeitado: quebra a estrutura
temporal da própria variável e força o modelo a extrapolar ("breaking
dependencies between features in hold-out data ... forcing the original model
to extrapolate", Hooker, Mentch & Zhou 2021, abstract; "observations of the same
feature over subsequent time steps are not independent", Leung et al. 2023).
**Ressalva:** permutar entre amostras ainda quebra a correlação entre famílias
(Hooker et al. 2021; Strobl et al. 2008) — é exatamente por isso que a
ablação, com outro estimando, é o segundo método (§5.5).

**Medida (C2 — decidida, §10.1).** Por horizonte, a **diferença** de perda
pinball média na grade:

    d_{f,t}(h) = L_t^{perm f}(h) − L_t(h)        (média sobre K_p permutações)
    I_f(h)     = (1/T) Σ_t d_{f,t}(h)

com L_t do evaluation §2.4 sobre o vetor rearranjado. A razão (Breiman 2001,
§10: "percent increase in misclassification rate"; Fisher et al. 2019, §3,
Eq. (3.1), MR = e_switch / e_orig, que "could alternatively be defined as a
difference") foi descartada porque a diferença é **aditiva por observação**: a
série d_{f,t} admite o mesmo bootstrap em bloco que o d_t do DM (evaluation
§6). Para comparar horizontes, cuja perda de base difere em escala, usa-se a
**participação normalizada** s_f(h) = I_f(h) / Σ_g I_g(h) ("Variable importance
within each model is normalized to sum to one", Gu, Kelly & Xiu 2020, §1.9).
K_p (permutações por família) é parâmetro pré-registrado; aumentar K_p só reduz
o erro de Monte Carlo (§5.6).

### 5.5 Ablação por família: LOCO com re-treino

**Desenho (decisão P do humano, 2026-10-06).** Ablação = **leave-one-covariate-out
com re-treino**: para cada família f, treina-se o TFT **sem** as features de f
e compara-se a sua perda com a de um modelo completo, no mesmo teste:

    I_f^LOCO(h) = (1/T) Σ_t [ L_t^{−f}(h) − L_t^{full}(h) ]

É o LOCO de Lei et al. (2018, §6 — localizador da sessão de pesquisa, não
relido); Hooker et al. (2021, §5, p. 12) chamam o re-treino de "Dropped
Variable Importance ... learning a model f_{−j} ... This is equivalent to the
LOCO methods"; Covert, Lundberg & Lee (2021, §8.2): "Training separate models
should provide the best approximation". O estimando é diferente do da
permutação: LOCO mede **quanta informação aproveitável a família traz ao
aprendiz** (com as outras famílias podendo compensar — Hooker et al. 2021,
p. 13: a importância cai "when these become more correlated"); a permutação
mede **quanto o modelo treinado depende da família** fora do suporte dos dados.
É essa diferença de estimandos que dá valor à concordância (§5.7).

**N + 1 configurações e cohort próprio.** São **4 + 1 = 5 configurações** (as 4
famílias removidas uma a uma + o modelo completo de referência) × **10 seeds**
× 6 folds — esta é a definição do "N+1" do roadmap 7.3 (§9). Os modelos
ablacionados não existem no cohort confirmatório (ADR 5.5.0001), então a
ablação tem um **cohort de ablação próprio, congelado e hasheado**, separado do
confirmatório. O modelo completo é **re-treinado dentro dele**, no **mesmo
ambiente** das ablações: a comparação L^{−f} − L^{full} não pode misturar
ambientes (§3.1). Cada configuração usa o mesmo procedimento de treino do
candidato (hiperparâmetros congelados) — re-ajustar hiperparâmetros por
configuração seria busca. O dispositivo (CPU ou GPU/ROCm) e a build do torch
são decisão da Stage 7.3 e **entram no hash** do cohort de ablação; comparar o
completo da ablação com o candidato confirmatório, se feito, é por tolerância.

**Custo, ancorado no medido** (exigência do ADR 0.0.0010 item 5 e do D8 da
5.5). O cohort confirmatório real de 10 seeds × 6 folds levou **~19 h em CPU**
(~1,5–2,9 h por seed; `docs/stages/5.5-confirmatory-retrain/technical.md`,
Task 35). A ablação são 5 configurações × 6 folds × 10 seeds ≈ **300 treinos ≈
~95 h em CPU**. Decisão do humano: **10 seeds**, rodando em **GPU no Linux**
(RX 7700 XT / ROCm), com um **piloto de 1 seed × 1 fold** antes; o número de
seeds pode ser revisto na 7.3 à luz do piloto (ADR 0.0.0007, Consequences).

**Código novo de modelagem exigido pela 7.3** (declarado aqui; o desenho é do
concept/technical da Stage):

- treinar o TFT com um **subconjunto** de famílias — hoje o caso de uso usa a
  registry inteira (`train_tft.py` l. 286–288);
- **identidade** de run / `feature_set_hash` por configuração — hoje o
  `feature_set_hash` é o da registry (`train_tft.py` l. 562);
- um **cohort spec de ablação** com as 5 configurações — hoje o executor de
  cohort recusa `feature_set_hash` diferente do da registry
  (`run_confirmatory_cohort.py` l. 346–357);
- **dispositivo ≠ `cpu`** — hoje o composition root só aceita `cpu`
  (`composition_root.py` l. 287–289).

**Alternativa descartada: substituir sem re-treinar.** Zerar ou trocar pela
média as features de f mantendo o modelo fixo é o precedente de Gu, Kelly & Xiu
(2020, §1.9: "setting all values of predictor j to zero, while holding the
remaining model estimates fixed"), mas substituir por um valor fixo "can be
interpreted as an additional assumption of model linearity" (Covert et al.
2021, §8.2) e avalia o **mesmo modelo fixo fora do suporte** que a permutação —
os dois métodos deixariam de ser independentes.

**"Sem re-treino" do overview §4.** O critério de sucesso fala de artefatos de
decisão reconstruíveis **a partir de dados persistidos** sem re-treino. A
ablação é treinada **uma vez**, como cohort próprio; suas predições são
persistidas; a leitura de H3 (§5.7) é reconstruível delas sem re-treino.

### 5.6 Incerteza

**C3 (decidida, §10.1).** Três fontes, tratadas separadamente:

1. **Monte Carlo da permutação** — repetir K_p permutações reduz o erro de
   Monte Carlo da permutação, não a incerteza de amostragem: "Variance
   estimators for model-PD/PFI only account for variance due to Monte Carlo
   integration" (Molnar et al. 2023, §5). Nota sobre a fonte: em Molnar et
   al. a variância de Monte Carlo dos estimadores PFI é calculada **entre as
   instâncias de teste (n2)**, não por repetição de permutações, e o IC t do
   model-PFI se justifica por **amostras independentes**.
2. **Amostragem do teste (dependente)** — **bootstrap em bloco estacionário**
   (Politis & Romano 1994) sobre as séries d_{f,t}, com bloco por Politis &
   White (2004) — a mesma maquinaria do MCS (evaluation §6.5). O bootstrap é
   **pareado**: os mesmos índices reamostrados entram nas séries de h+1 e de
   h+7 e em todas as famílias, de modo que s_f e Δ_f de cada réplica são
   coerentes. Bootstrap iid é inválido sob dependência; as fontes de
   inferência para importância supõem observações independentes (Williamson et
   al. 2023, §2: "observations Z_1, ..., Z_n are drawn independently"; Molnar
   et al. 2023, acima). Como as nossas instâncias de teste são **serialmente
   dependentes**, o bootstrap em bloco sobre d_t é **transposição declarada**
   do que a avaliação já usa para d_t — não há fonte primária de intervalo
   para importância por permutação sob dependência serial
   `[SEM-FONTE-PRIMÁRIA para a combinação]`.
   **Regra de bloco.** O bootstrap conjunto h+1/h+7 usa **um único
   comprimento de bloco**, com **piso ≥ max horizonte (7)**, por coerência com
   a regra do MCS (ADR 0.0.0010: bloco = max(h, ⌈max b̂_sb⌉) — o piso cobre a
   dependência MA(h−1); r0 `block_rule = "max_h_ceil_max_bsb"`), com b̂ = o
   máximo dos b̂ de Politis–White das séries envolvidas. O detalhe numérico vai
   ao pré-registro (§5.7).
   **Chave de pareamento entre horizontes** — ver §5.7 (ponto aberto do
   pré-registro).
3. **Variância do modelo** — seeds: as séries entram como **média ponto a
   ponto entre seeds** (§2.3); a dispersão entre seeds vai ao perfil
   (Bouthillier et al. 2021). Em Molnar et al. (2023, §7: "average the PD/PFI
   over m model fits") a variância do modelo exige **refits**, e para o
   learner-PFI o artigo corrige o caso de dados compartilhados entre refits
   (Nadeau–Bengio); aqui os refits são as seeds sobre os mesmos dados, e a sua
   dispersão é reportada como perfil, não somada ao IC.

A ablação usa a **mesma maquinaria** sobre as séries L_t^{−f} − L_t^{full},
agregando as seeds da mesma forma. Bloco, número de réplicas B e semente são
pré-registrados (§7).

### 5.7 Regra de leitura: heterogeneidade e concordância

Só h+1 e h+7 são avaliados, então "heterogênea entre horizontes" é uma
comparação de dois pontos.

**Heterogênea (C4 — decidida, §10.1).** Para cada família f e cada método,
Δ_f = s_f(h+7) − s_f(h+1). A contribuição é **heterogênea** (naquele método) se
o intervalo bootstrap pareado de Δ_f **exclui 0 para ≥ 1 família**. Mudança de
ranking foi rejeitada: com 4 famílias há só 24 ordens, a medida é grosseira e
não tem incerteza natural. `[SEM-FONTE-PRIMÁRIA]` para o procedimento — é
convenção do projeto (nenhuma fonte compara importância entre horizontes com
teste formal; Lim 2021 §7.1–§7.2 não o faz para variáveis).

**Concordância (C5 — decidida, §10.1).** H3 é **sustentada** se permutação e
ablação **concordam no sinal de Δ_f e ambas têm intervalo excluindo 0** para a
mesma família (ou famílias) — inspirado no "sign agreement", uma das seis
métricas de discordância que Krishna et al. (2024, §3.2) **propõem** ("we
propose six different metrics") — proposta do artigo, não prática geral
estabelecida —, aplicada aqui à variação entre horizontes. A VSN não entra na
regra (§5.3).

**Pontos que a Stage 7.3 ainda precisa fixar no pré-registro** (não decididos
neste gate; lista única — §5.6, §7 e §8 apontam para cá). Todos mudam o
veredito descritivo e, por isso, entram no pré-registro (§7) — não podem ser
escolhidos depois de ver os números:

1. **Nível do intervalo** de Δ_f.
2. **Multiplicidade** — se há ajuste pela leitura de "≥ 1 de 4 famílias".
3. **Importâncias negativas / Σ_g I_g(h) ≈ 0** — caso em que a participação
   normalizada fica mal definida.
4. **Chave de pareamento entre horizontes.** A avaliação alinha **por
   horizonte** por `target_timestamp` (evaluation §2.1, §6.7): o mesmo t em
   h+1 e em h+7 vem de **decisões diferentes** (t−1 vs t−7), e o número de
   pontos difere (T = 1511 em h+1 e 1505 em h+7 no cohort; concept 5.5 D6).
   Opções: parear por `target_timestamp` ou por **ponto de decisão**.
   Recomendação deste doc, como convenção a pré-registrar
   `[SEM-FONTE-PRIMÁRIA]`: parear por **ponto de decisão**, restrito à
   **interseção** dos pontos dos dois horizontes — coerente com o argumento da
   VSN (§5.3: para um mesmo ponto de decisão a entrada é a mesma) e com a
   atribuição agir sobre a mesma entrada (permutar a janela do encoder de uma
   decisão afeta h+1 e h+7 juntos).
5. **Bloco do bootstrap conjunto** — comprimento único com piso ≥ 7 pela regra
   de §5.6; o valor numérico (b̂ de Politis–White das séries envolvidas) e
   B/semente.

### 5.8 Linguagem e "veredito mecânico"

**C7 (decidida, §10.1).** A linguagem é **estritamente descritiva**: "a
família f responde por uma parcela maior da perda evitada em h+7 do que em
h+1", nunca "f causa" ou "f prevê melhor no longo prazo" (overview §3; ADR
0.0.0002). O "veredito mecânico H1/H2/H3" do roadmap 8.1 é lido assim: H3 tem
uma **regra de leitura pré-registrada e mecânica** (C4 + C5) que produz uma
**conclusão descritiva** ("sustentada" / "não sustentada"), **separada** do
veredito H1 → H2 — não o altera, e nenhum perfil troca nenhum dos dois
(evaluation §8.6). "Não sustentada" não é "sem efeito": significa que os dois
métodos não concordaram com a incerteza disponível.

## 6. API (Stage 7.4)

A API não tem teoria própria. Conceitualmente, o payload carrega três coisas,
cada uma com o seu rótulo:

1. os **quantis nativos rearranjados** da grade, por horizonte — o objeto de
   H1 (§2.1);
2. o **intervalo conformal** por par, rotulado **"cobertura empírica (não
   garantida)"** (§4.3 item 4, §4.11);
3. a **atribuição por família**, rotulada **descritiva** (§5.8), com a VSN
   marcada como horizonte-invariante (§5.3).

O "contrato P2" do roadmap não existe no repo e é **abandonado** (E2, §9): o
que a 7.4 serve é um payload com schema versionado definido no `technical.md`
da 7.4. A API serve o que foi produzido pelas Stages 7.1–7.3; ela não
recalibra, não re-treina e não calcula atribuição sob demanda sobre dados do
cohort confirmatório antes do pré-registro (§7).

## 7. Pré-registro e cegamento

**O que se pré-registra (E1 — decidida, §10.1).** Antes da 8.1:

- **CQR** — o listado em §4.13;
- **H3** — a partição de famílias (com a ressalva de §5.2 resolvida), o
  esquema de permutação, K_p, a medida, bloco/B/semente do bootstrap, a regra
  C4/C5 com os 5 pontos abertos listados em §5.7 (nível do IC,
  multiplicidade, importâncias negativas, chave de pareamento, bloco), e o
  desenho da ablação (cohort de ablação hasheado).

**Mecanismo.** A mesma maquinaria de pré-registro ratificada na 6.5 — TOML
hasheado + âncora por tag e comentário (ADRs 6.5.0001, 6.5.0002, 6.5.0003;
evaluation §8) —, ancorada **antes de qualquer métrica sobre o cohort real**. A
forma (emenda cega r1 do pré-registro confirmatório × arquivo próprio) é
decisão do `technical.md` das Stages 7.2/7.3. O ADR 6.5.0008 item 6 já diz que
H3 e CQR "are not frozen here" e que as regras "belong to the Stages that own
them". Isto corrige o "pré-registrada em ADR" da DoD original da 7.2: o ADR
registra a **decisão**; o pré-registro é o **artefato hasheado**.

**Cegamento.** Vale a regra geral: nenhuma métrica confirmatória sobre o cohort
real antes do hash (evaluation §8.2; ADR 5.5.0001; concept 5.5 D14). Para o
Step 7 isso significa: nem cobertura do CQR no teste, nem importância por
permutação, nem perdas da ablação sobre o teste antes do pré-registro
correspondente ancorado — nem como "sonda". Treinar o cohort de ablação e
**ver** predições não viola; **computar métricas** viola (evaluation §8.2).

## 8. Fronteira

### 8.1 O que este doc consome (ponteiros)

| Fonte | O quê | Onde se usa aqui |
|---|---|---|
| modeling §2.4; ADR 4.3.0002 | rearranjo = guardrail; corrige ordem, não calibração | §3.3, §4.8 |
| modeling §5.2; ADR 5.4.0004 | tipagem known/observed | §5.3 |
| modeling §5.3; ADR 5.1.0002 | early-stop ≠ calib | §4.1, §4.3 |
| modeling §6; ADR 5.5.0001 | candidato único, seeds × folds, cohort hasheado | §2.1, §5.5 |
| ADR 5.4.0001 | encoder pode ler calib | §3.4 |
| ADR 5.4.0002 | decoder único multi-horizonte | §2.1, §5.3 |
| evaluation §2.4, §2.2 | L_t, pontuar o rearranjado | §4.8, §5.4 |
| evaluation §4 | ĉ(τ), PICP/MPIW, Wilson, hits, empate | §2.4, §4.11 |
| evaluation §6.5, §6.9 | bootstrap estacionário e bloco; seeds | §2.3, §5.6 |
| evaluation §8 | pré-registro, ordem, perfil nunca troca veredito | §5.8, §7 |
| ADR 0.0.0016 | 4 famílias | §5.2 |

### 8.2 O que fica para o `technical.md`

Onde se persistem as predições de calib; lote de inferência, threads e
tolerância numérica concretos; leitura do artefato; papel do MAPIE; como os
intervalos conformais entram nas estruturas de cobertura existentes (que hoje
esperam a grade simétrica inteira); forma do pré-registro de CQR e H3; valores
de K_p, B, bloco, semente e nível do intervalo; dispositivo do cohort de
ablação; schema e versionamento do payload da API.

### 8.3 O que este doc não decide

A partição da volatilidade (§5.2 — issue separada, a abrir); os 5 pontos
abertos de H3 listados em §5.7 (nível do IC, multiplicidade, importâncias
negativas, chave de pareamento, bloco — pré-registro da 7.3); qualquer teste de
hipótese sobre o CQR.

## 9. Vocabulário órfão do roadmap

| Termo | O que significa aqui |
|---|---|
| "contrato P2" | **abandonado** — não definido no repo (herança do projeto antigo); a 7.4 serve um payload versionado (§6) |
| "N+1" (ablação) | 4 famílias ablacionadas + 1 modelo completo de referência, re-treinados no mesmo cohort de ablação (§5.5) |
| "≥ 2/3" / "triangulação" | **abandonado** — a VSN não resolve horizonte; H3 exige concordância de permutação e ablação (§5.1, §5.7) |
| "heterogênea entre horizontes" | Δ_f com intervalo excluindo 0 para ≥ 1 família (§5.7) |
| VSN | *variable selection network* do TFT (Lim et al. 2021 §4.2) — descrição horizonte-invariante (§5.3) |
| split-CQR | CQR (Romano et al. 2019) calibrado numa partição dedicada, como no split conformal de Lei et al. 2018 (§4.1) |
| NexCP | *non-exchangeable conformal prediction* de Barber et al. 2023 — pesos fixos; aqui, sensibilidade com ρ = 0,99 (§4.5) |
| ACI | *adaptive conformal inference* (Gibbs & Candès 2021) — fora do confirmatório (§4.6) |
| EnbPI | *ensemble batch prediction intervals* (Xu & Xie 2021) — fora do confirmatório (§4.6) |

## 10. Convenções decididas (tabela-resumo)

Legenda de status: **[P]** decisão do humano; **[E]** evidência decide;
**[C]** convenção sem vencedor, fechada pelo degrau indicado; todas registradas
em §10.1.

| # | Convenção | Fonte / âncora | Status | Stage |
|---|---|---|---|---|
| 1 | Reprodução bit a bit só no mesmo ambiente pinado (build, SO/CPU, lote fixo e registrado, sem workers); entre ambientes, tolerância declarada | PyTorch notes v2.13.0; Goldberg 1991; concept 5.4 I9 | [E] A1 | 7.1 |
| 2 | Seed irrelevante na inferência; dropout off; MC dropout fora | pytorch-forecasting 1.8.0; Lightning 2.6.5; Gal & Ghahramani 2016 §4; Kendall & Gal 2017 | [E] A2 | 7.1 |
| 3 | Guardrail reusado (rearranjo do ADR 4.3.0002), sem serviço novo | modeling §2.4; ADR 4.3.0002 | [C] A3, degrau 1 | 7.1 |
| 4 | A inferência emite predições da partição calib (requisito 7.1 → 7.2) | concept 5.2; ADR 5.1.0002 | [C] A4, degrau 1 | 7.1, 7.2 |
| 5 | Split-CQR assimétrico (Thm 2), quantil inflado (1−α)(1+1/n) | Romano et al. 2019 Eqs. (9), (11) (numeração de equação não conferida), Thms 1–2 | [E] B1 | 7.2 |
| 6 | Variante de registro sem pesos; NexCP ρ = 0,99 como sensibilidade; ρ ≤ 0,98 descartado | Barber et al. 2023 Eqs. (10)–(11), §4.1 Thm 2, §4.4, §5.1; derivação | [C] B2, degrau 2 | 7.2 |
| 7 | ACI/EnbPI fora do confirmatório | Gibbs & Candès 2021; Xu & Xie 2021; Oliveira et al. 2024 §2 | [E] B3 | 7.2 |
| 8 | Cobertura marginal por horizonte; conjunta Bonferroni rejeitada | Oliveira et al. 2024 Thms 1/4; Stankevičiūtė et al. 2021 §3.3 | [E] B4 | 7.2 |
| 9 | 3 pares simétricos, caudas independentes; primário (0.10, 0.90); sem rearranjo da saída conformal; taxa de violação de aninhamento no perfil; par extremo reportado | Gupta et al. 2022 Tab. 1; CWZ 2021; ADR 6.5.0006 | [C] B5, degraus 4/5 | 7.2 |
| 10 | CQR por seed, média das coberturas | ADR 0.0.0010 item 5 | [E] B6, degrau 1 | 7.2 |
| 11 | Dispersão Beta(n+1−l, l) reportada como referência | Angelopoulos & Bates 2023 §3.2; Vovk 2012 Prop. 2 | [E] B7 | 7.2, 8.3 |
| 12 | Comparação nativo × conformal descritiva, reusando evaluation §4; rótulo "cobertura empírica (não garantida)" | evaluation §4, §9.2 | [C] B8, degrau 1 | 7.2, 8.1, 8.3 |
| 13 | Papel do MAPIE decidido na 7.2; fórmula do quantil registrada como oráculo | ADRs 0.0.0056, 6.1.0001; MAPIE 1.5.0 | [C] B9, degrau 1 | 7.2 |
| 14 | H3 reformulada: permutação + ablação concordam; VSN descritiva | Lim et al. 2021 §4.2 Eq. (6) | [P] P-H3-VSN | 7.3, 8.1 |
| 15 | Ablação = LOCO com re-treino, 10 seeds, cohort de ablação próprio com referência no mesmo ambiente | Lei et al. 2018 §6; Hooker et al. 2021 §5; Covert et al. 2021 §8.2 | [P] P-ABLACAO | 7.3 |
| 16 | Permutação da janela inteira da família, entre amostras, em conjunto | Fisher et al. 2019 §2; Gregorutti et al. 2015 §2.1; Hooker et al. 2021 | [E] C1 | 7.3 |
| 17 | Medida = diferença de pinball média da grade, por horizonte; participação normalizada | Gu, Kelly & Xiu 2020 §1.9; evaluation §6 | [C] C2, degraus 1/5 | 7.3 |
| 18 | Incerteza por bootstrap em bloco estacionário pareado (transposição declarada; bloco único com piso ≥ 7, regra do MCS); seeds pela média | Politis & Romano 1994; Politis & White 2004; Molnar et al. 2023 §5, §7; ADR 0.0.0010 | [E] C3 | 7.3 |
| 19 | "Heterogênea" = IC de Δ_f exclui 0 para ≥ 1 família | `[SEM-FONTE-PRIMÁRIA]` | [C] C4, degrau 4 | 7.3, 8.1 |
| 20 | H3 sustentada = mesmo sinal de Δ_f e IC excluindo 0 nos dois métodos, mesma família | Krishna et al. 2024 §3.2 (métrica proposta pelo artigo) | [C] C5, degrau 4 | 7.3, 8.1 |
| 21 | Features sem família ficam no modelo, fora da participação; interações seguem o registry; premissa: nenhuma feature de família é `known` | ADR 0.0.0016; registry; `train_tft.py` | [C] C6, degrau 1 | 7.3 |
| 22 | Linguagem descritiva; veredito H3 = regra de leitura mecânica separada de H1 → H2 | overview §3; ADR 0.0.0002; evaluation §8.6 | [C] C7, degrau 1 | 7.3, 8.1 |
| 23 | Pré-registro de CQR e H3 pela maquinaria da 6.5, antes de qualquer métrica sobre o cohort real | ADRs 6.5.0001–3, 6.5.0008 item 6 | [C] E1, degrau 1 | 7.2, 7.3, 8.1 |
| 24 | Vocabulário órfão abandonado ou definido (§9) | — | [C] E2, degrau 1 | 7.3, 7.4 |
| 25 | ADRs do gate: 0.0.0057, 0.0.0007, 0.0.0008 | — | [C] E3, degrau 1 | — |
| 26 | Correções de texto do roadmap (Step 7 e dependência 8.1 → 7.3) | — | [C] E4, degrau 1 | 7.1–7.4, 8.1 |

### 10.1 Registro das decisões (triagem `evidence-resolution`, 2026-10-05/06)

Triagem: todas as bifurcações são anteriores a qualquer dado confirmatório (a
8.1 não rodou). As duas P foram decididas pelo humano em 2026-10-06. A
existência e os metadados de cada fonte foram conferidos mecanicamente
(`scripts/verify_citations.py`); "verificado" = trecho conferido na fonte
bruta por verificador de contexto zerado — feito nos dois itens da VSN; os
demais localizadores e trechos são os das sessões de pesquisa (lotes A, B1,
B2, C), lidos crus nas fontes indicadas.

```
[decision:P] P-H3-VSN — papel da VSN em H3
Escolha: VSN como descrição geral horizonte-invariante; heterogeneidade de H3 exige concordância de permutação e ablação · Alternativas: trocar a VSN por um 3º método resolvido por horizonte (gradientes integrados por saída); manter "≥ 2 de 3" · Decisor: humano (2026-10-06)
Base: Lim et al. 2021 §4.2 Eq. (6) "Variable selection weights are generated by feeding both Ξt and an external context vector cs through a GRN, followed by a Softmax layer"; §7.1 Eq. (27); pytorch-forecasting v1.8.0 _tft.py l. 576–596, 811–827 (VSN do encoder só nas posições do encoder; interpretação = média sobre o encoder) [verificado: "sustenta" nos 2 itens]
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash do pré-registro de H3

[decision:P] P-ABLACAO — desenho da ablação
Escolha: LOCO com re-treino; 10 seeds; 4 famílias × 6 folds + modelo completo de referência (N+1 = 5 configurações) num cohort de ablação congelado e hasheado próprio, mesmo ambiente; GPU no Linux (RX 7700 XT / ROCm) com piloto 1 seed × 1 fold antes; dispositivo e build incluídos no hash; nº de seeds revisável na 7.3 à luz do piloto · Alternativas: substituição sem re-treino; sem ablação · Decisor: humano (2026-10-06)
Base: Lei et al. 2018 §6 (LOCO; localizador não relido nesta sessão); Hooker et al. 2021 §5 p. 12 "Dropped Variable Importance … learning a model f−j … This is equivalent to the LOCO methods"; Covert, Lundberg & Lee 2021 §8.2 "Training separate models should provide the best approximation"; custo medido: cohort confirmatório 10 seeds × 6 folds ≈ 19 h em CPU (technical 5.5, Task 35) → ablação ≈ 300 treinos ≈ 95 h em CPU (§5.5)
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash do cohort de ablação

[decision:E] A1 — contrato de reprodução da inferência
Escolha: bit a bit só no mesmo ambiente pinado (build do torch, SO/CPU, lote de inferência fixo e registrado, num_workers = 0); entre ambientes, igualdade por tolerância declarada; referência da 7.1 = artefato re-executado no mesmo ambiente com lote = batch_size do treinador (111 no cohort); contra as predições já no silver, equivalência por tolerância salvo lote e ambiente coincidentes · Alternativas: bit a bit em qualquer ambiente; só tolerância
Base: PyTorch notes/randomness.md (v2.13.0) "Completely reproducible results are not guaranteed across PyTorch releases, individual commits, or different platforms."; notes/numerical_accuracy.md §Batched computations "(A@B)[0] ... is not guaranteed to be bitwise identical to A[0]@B[0]"; docstring de torch.use_deterministic_algorithms "same software and hardware"; Goldberg 1991 (DOI 10.1145/103162.103163) "the associative laws of algebra do not necessarily hold for floating-point numbers"
Sensibilidade pré-registrada: nenhuma · Reversível: sim (corrige a DoD da 7.1; coerente com concept 5.4 I9 e ROADMAP-5)

[decision:E] A2 — seed, dropout e MC dropout na inferência
Escolha: seed irrelevante (nenhum consumidor de RNG); dropout off (modo eval); MC dropout fora · Alternativas: MC dropout
Base: pytorch-forecasting 1.8.0 QuantileLoss.to_quantiles "return y_pred"; Lightning 2.6.5 core/hooks.py "The predict loop by default calls .eval()"; torch 2.13.0 nn/modules/dropout.py "during evaluation the module simply computes an identity function"; Gal & Ghahramani 2016 (arXiv:1506.02142) §4 Eq. (6) "We refer to this Monte Carlo estimate as MC dropout"; Kendall & Gal 2017 (arXiv:1703.04977) Abstract
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] A3 — guardrail na inferência
Escolha: reusar o rearranjo do ADR 4.3.0002 / modeling §2.4 · Alternativas: serviço de guardrail novo no BC inference · Degrau: 1
Base: ADR 4.3.0002; modeling §2.4 (Chernozhukov, Fernández-Val & Galichon 2010, Prop. 4)
Sensibilidade pré-registrada: nenhuma · Reversível: sim (corrige o roadmap 7.1)

[decision:C] A4 — predições da partição calib
Escolha: a inferência emite as predições de calib do candidato por (fold, seed, horizonte); forma de persistência = technical · Alternativas: nenhum dono (estado atual) · Degrau: 1
Base: concept 5.2 (o conformal "consome o calib do candidato via RunInference"); ADR 5.1.0002
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] B1 — mecânica do CQR
Escolha: split-CQR, versão assimétrica (Thm 2), α por cauda = τ_lo e 1 − τ_hi, quantil inflado (1 − α)(1 + 1/n) · Alternativas: simétrico (Thm 1)
Base: Romano, Patterson & Candès 2019 (arXiv:1905.03222) Eq. (9) "Ei := max{q̂lo(Xi) − Yi, Yi − q̂hi(Xi)}"; Eq. (11) "(1 − α)(1 + 1/|I2|)-th empirical quantile" (numeração de equação não conferida); Thm 1; §4 Thm 2 "control[s] the left and right tails independently"; §6.2 "increases from 1.40 to 1.58"; gate de H1 por cauda (evaluation §10 conv. 26)
Sensibilidade pré-registrada: nenhuma (o simétrico daria intervalos mais estreitos com a mesma garantia só no PICP) · Reversível: sim, até o hash do pré-registro do CQR

[decision:C] B2 — variante do CQR
Escolha: split-CQR sem pesos como registro; NexCP com w_i = ρ^(n+1−i), ρ = 0,99, como sensibilidade pré-registrada (perfil) · Alternativas: NexCP como registro; não fazer (contraria overview §3/§11) · Degrau: 2 (default do oráculo MAPIE 1.5.0, sem pesos; recência já garantida pelo calib mais recente, ADR 5.1.0002)
Base: Barber et al. 2023 (DOI 10.1214/23-AOS2276) Eqs. (10)–(11) pp. 10–11; §3.1 "We assume the weights wi are fixed"; §4.1 Thm 2 p. 15 "1 − α − Σ w̃i · dTV(R(Z), R(Zi))"; §4.4 pp. 18–19 "≤ ρ^k"; §5.1 p. 22 "wi = 0.99^(n+1−i)"; derivação deste doc: w̃_{n+1} = 0,0109 (ρ = 0,99) / 0,0201 (ρ = 0,98) > α_cauda 0,02 ⇒ limite infinito na cauda 0,02; contexto: Stocker et al. 2025 (arXiv:2511.13608, preprint) p. 17
Sensibilidade pré-registrada: NexCP ρ = 0,99 · Reversível: sim, até o hash

[decision:E] B3 — ACI e EnbPI
Escolha: fora do confirmatório · Alternativas: incluir
Base: Gibbs & Candès 2021 (arXiv:2106.00170) Eq. (2) p. 3, Prop. 4.1 p. 6 (garantia de frequência de longo prazo, com atualização online), §4.2 (cobertura marginal só aproximada, sob pequenos drifts num modelo específico), §7 p. 10 "delayed fashion or in large batches" (problema aberto); Xu & Xie 2021 (PMLR 139) §3.1 p. 4, §3 item (5) "When s=∞, no feedback is available", §4.1 Assumption 1; Oliveira et al. 2024 (arXiv:2203.15885) §2 p. 4 "have no marginal coverage guarantees"
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] B4 — por horizonte
Escolha: cobertura marginal por horizonte, cada horizonte calibrado à parte · Alternativas: conjunta (Bonferroni α/H)
Base: Oliveira et al. 2024 Thm 1 p. 5, Thm 4 p. 8; Stankevičiūtė et al. 2021 §3.3 p. 5 e Fig. 1 p. 3 ("a set of independent time-series"); Chernozhukov, Wüthrich & Zhu 2018 (arXiv:1802.06300) §3.2 Thm 2 p. 7; overview §7; ADR 0.0.0010
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] B5 — pares, assimetria e aninhamento
Escolha: CQR assimétrico nos 3 pares simétricos, caudas independentes; par primário de comparação (0.10, 0.90); saída conformal não rearranjada; taxa de violação de aninhamento no perfil; par extremo reportado sem exclusão · Alternativas: conformal da distribuição inteira (DCP/CPS); só um par · Degrau: 4 (DCP exigiria extrapolar além de [0.02, 0.98]) e 5 (mesmo par do gate H1)
Base: Gupta, Kuchibhotla & Ramdas 2022 (DOI 10.1016/j.patcog.2021.108496) Tab. 1; Chernozhukov, Wüthrich & Zhu 2021 (DOI 10.1073/pnas.2107794118) Alg. 2; Vovk et al. 2019 (DOI 10.1007/s10994-018-5755-8) Def. 1; ADR 6.5.0006; concept 5.5 D6
Sensibilidade pré-registrada: taxa de violação de aninhamento (perfil) · Reversível: sim, até o hash

[decision:E] B6 — seeds no CQR
Escolha: conformalizar cada seed e reportar a média das coberturas · Alternativas: conformalizar a média das seeds; voto entre seeds · Degrau: 1 (coerência)
Base: ADR 0.0.0010 item 5 "Coverage and degeneracy are seed means"; Romano et al. 2019 §4; Fakoor et al. 2023 (arXiv:2103.00083) §5.3; Gasparin & Ramdas (arXiv:2401.09379, preprint) Thm 2.1 "coverage of at least 1 − 2α"
Sensibilidade pré-registrada: dispersão entre seeds (perfil) · Reversível: sim

[decision:E] B7 — dispersão por tamanho de calibração
Escolha: reportar a Beta(n + 1 − l, l), l = ⌊(n+1)α⌋, como referência por par e por cauda (n = 252) · Alternativas: não reportar
Base: Angelopoulos & Bates 2023 (DOI 10.1561/2200000101) §3.2 "Beta(n + 1 − l, l)", App. D; Vovk 2012 (arXiv:1209.2673) Prop. 2; quantis calculados para este doc (derivação)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] B8 — comparação nativo × conformal
Escolha: descritiva, reusando evaluation §4 (ĉ(τ), PICP/MPIW, Wilson, hits); nenhum teste novo; rótulo "cobertura empírica (não garantida)" · Alternativas: teste formal de diferença de cobertura · Degrau: 1
Base: evaluation §4.4 alt. (ii), §6.4, §9.2; ADR 0.0.0054 Alt. B
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] B9 — MAPIE
Escolha: papel (backend × oráculo) decidido no concept/technical da 7.2; o doc registra a fórmula q = (1 − α)(1 + 1/n), method="higher" · Alternativas: fixar aqui · Degrau: 1
Base: ADRs 0.0.0056, 6.1.0001; MAPIE 1.5.0 regression/quantile_regression.py (não pinado no uv.lock)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] C1 — esquema de permutação
Escolha: permutar entre amostras do teste a janela inteira (todos os lags) das features da família, em conjunto · Alternativas: embaralhar dentro do tempo; blocos
Base: Fisher, Rudin & Dominici 2019 (arXiv:1801.01489) §2 "the covariate subsets X1 ... may each be multivariate"; Gregorutti, Michel & Saint-Pierre 2015 (DOI 10.1016/j.csda.2015.04.002; arXiv:1411.4170 §2.1) "in general, the grouped variable importance is not comparable with the sum of the individual importances", com a exceção "If f is additive and if the variables of the group are independent, the grouped variable importance is nothing more than the sum of the individual importances"; Hooker, Mentch & Zhou 2021 (DOI 10.1007/s11222-021-10057-z) Abstract; Leung et al. 2023 (arXiv:2107.14317)
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash de H3

[decision:C] C2 — medida da permutação
Escolha: diferença de pinball média da grade (L_perm − L_orig), por horizonte, média sobre K_p permutações; participação normalizada para comparar horizontes · Alternativas: razão (Breiman; Fisher MR) · Degrau: 1 (aditiva por observação → bootstrap em bloco como o d_t do DM) e 5
Base: Breiman 2001 (DOI 10.1023/A:1010933404324) §10; Fisher et al. 2019 §3 Eq. (3.1) "could alternatively be defined as a difference"; Gu, Kelly & Xiu 2020 §1.9 "normalized to sum to one"
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash de H3

[decision:E] C3 — incerteza da importância
Escolha: bootstrap em bloco estacionário pareado (mesmos índices para h+1, h+7 e todas as famílias) sobre d_{f,t}, bloco único com piso ≥ 7 (regra do MCS, ADR 0.0.0010); chave de pareamento entre horizontes a fixar no pré-registro (recomendação: ponto de decisão, interseção); seeds pela média, dispersão no perfil · Alternativas: repetir permutações; bootstrap iid; IC t entre instâncias (Molnar)
Base: Molnar et al. 2023 (DOI 10.1007/978-3-031-44064-9_24; arXiv:2109.01433) §5 "Variance estimators for model-PD/PFI only account for variance due to Monte Carlo integration" — variância de MC calculada entre as n2 instâncias de teste, IC t justificado por amostras independentes; §7 "average the PD/PFI over m model fits" (variância do modelo exige refits; learner-PFI corrigido para dados compartilhados, Nadeau–Bengio); Williamson et al. 2023 (DOI 10.1080/01621459.2021.2003200) §2; Politis & Romano 1994; Politis & White 2004; Bouthillier et al. 2021; ADR 0.0.0010 (block = max(h, ⌈max b̂_sb⌉))
Sensibilidade pré-registrada: nenhuma · Reversível: sim · Lacuna: sem fonte de IC de PFI sob dependência — transposição declarada (instâncias de teste serialmente dependentes)

[decision:C] C4 — "heterogênea entre horizontes"
Escolha: Δ_f = s_f(h+7) − s_f(h+1); heterogênea se o IC bootstrap pareado de Δ_f exclui 0 para ≥ 1 família · Alternativas: mudança de ranking · Degrau: 4
Base: [SEM-FONTE-PRIMÁRIA] — convenção; pontos abertos do pré-registro listados em §5.7 (nível, multiplicidade, importâncias negativas, chave de pareamento — alinhamento por target_timestamp por horizonte em evaluation §2.1/§6.7, T = 1511/1505 no concept 5.5 D6 —, bloco)
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash de H3

[decision:C] C5 — concordância entre métodos
Escolha: H3 sustentada se permutação e ablação concordam no sinal de Δ_f e ambas têm IC excluindo 0 para a mesma família; VSN reportada à parte (percentis 10/50/90; soma por família) · Alternativas: concordância de ranking (Spearman, top-k) · Degrau: 4
Base: Krishna et al. 2024 (arXiv:2202.01602) §3.2 "we propose six different metrics" — "feature agreement, rank agreement, sign agreement, ..." (métricas propostas pelo artigo, não prática geral estabelecida); Jain & Wallace 2019; Wiegreffe & Pinter 2019
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash de H3

[decision:C] C6 — features sem família
Escolha: calendário, alvo passado e índice relativo não são permutados nem ablacionados; participação só sobre as 4 famílias; interações seguem o registry; premissa verificável antes da 7.3: nenhuma feature de família é known (senão reabrir P-H3-VSN) · Alternativas: 5ª "família" residual · Degrau: 1
Base: ADR 0.0.0016; registry de features; train_tft.py l. 23–26, 196–207 (spec known vai ao decoder automaticamente)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] C7 — linguagem e "veredito mecânico H3"
Escolha: estritamente descritiva; regra de leitura pré-registrada e mecânica (C4 + C5), separada de H1 → H2 · Alternativas: H3 como teste confirmatório no veredito · Degrau: 1
Base: overview §3; ADR 0.0.0002; evaluation §8.6
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] E1 — pré-registro de CQR e H3
Escolha: o listado em §7, pela maquinaria da 6.5, ancorado antes de qualquer métrica sobre o cohort real; forma (emenda r1 × arquivo próprio) = technical 7.2/7.3 · Alternativas: "pré-registrar em ADR" · Degrau: 1
Base: ADRs 6.5.0001–6.5.0003; ADR 6.5.0008 item 6; evaluation §8.2
Sensibilidade pré-registrada: — · Reversível: não depois do hash

[decision:C] E2 — vocabulário órfão
Escolha: "contrato P2" abandonado; "N+1" = 4 famílias + completo; VSN, NexCP, ACI, EnbPI, split-CQR definidos (§9) · Degrau: 1
Base: ADR 0.0.0054 (precedente)
Sensibilidade pré-registrada: — · Reversível: sim

[decision:C] E3 — ADRs do gate
Escolha: 0.0.0057 (recorte), 0.0.0007 (H3), 0.0.0008 (quantis nativos + CQR); 7_2_0001 continua da Stage · Degrau: 1
Base: overview §11; issue #150
Sensibilidade pré-registrada: — · Reversível: sim

[decision:C] E4 — correções do roadmap
Escolha: DoD 7.1 (bit a bit qualificado; guardrail reusado; emitir calib), 7.2 (0_0_0008 sai de arquivos_a_criar; pré-registro pela maquinaria da 6.5), 7.3 (VSN descritiva; LOCO N+1; cohort de ablação; consome o treinador do TFT), 7.4 (sem "contrato P2"; app.py já existe), 8.1 depende de 7.3 · Degrau: 1
Base: este doc
Sensibilidade pré-registrada: — · Reversível: sim
```

## 11. Referências

Citações completas de todas as fontes usadas. Separadas em (11.1) já
ratificadas no overview §10 ou em ADRs aceitos, (11.2) novas deste doc
(registradas no overview §10 no mesmo PR, conforme ADR 0.0.0003) e (11.3)
documentação de biblioteca. Rótulo `[CITAÇÃO-NÃO-ACESSADA]` onde a fonte não
foi lida em primária durante o gate.

### 11.1 Já ratificadas no overview §10

- Romano, Y.; Patterson, E.; Candès, E. (2019). "Conformalized Quantile Regression". *Advances in Neural Information Processing Systems 32 (NeurIPS 2019)*. arXiv:1905.03222. (Eqs. (9), (11) — numeração de equação não conferida; Theorem 1; §4 Theorem 2, Eqs. (15)–(16); §4 "Practical considerations"; §6.2.)
- Barber, R. F.; Candès, E. J.; Ramdas, A.; Tibshirani, R. J. (2023). "Conformal prediction beyond exchangeability". *Annals of Statistics*, 51(2), 816–845. DOI: 10.1214/23-AOS2276. arXiv:2202.13415v5 (versão lida; paginação do arXiv). (§3, §3.1 p. 10; Eqs. (10)–(11) pp. 10–11; §4.1 Theorem 2 p. 15; §4.3 p. 18; §4.4 pp. 18–19; §5.1 p. 22; Appendix A.)
- Lei, J.; G'Sell, M.; Rinaldo, A.; Tibshirani, R. J.; Wasserman, L. (2018). "Distribution-Free Predictive Inference for Regression". *Journal of the American Statistical Association*, 113(523), 1094–1111. DOI: 10.1080/01621459.2017.1307116. (Split conformal; §6 LOCO — localizador da sessão de pesquisa, não relido.)
- Lim, B.; Arık, S. Ö.; Loeff, N.; Pfister, T. (2021). "Temporal Fusion Transformers for interpretable multi-horizon time series forecasting". *International Journal of Forecasting*, 37(4), 1748–1764. DOI: 10.1016/j.ijforecast.2021.03.012. (Lido em arXiv:1912.09363v3; paginação do periódico não conferida: §4.2 Eqs. (6) e (8); §7.1 Eq. (27); §7.2.)
- Gu, S.; Kelly, B.; Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning". *The Review of Financial Studies*, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009. (§1.9 pp. 2246–2247.)
- Politis, D. N.; Romano, J. P. (1994). "The Stationary Bootstrap". *JASA*, 89(428), 1303–1313. DOI: 10.1080/01621459.1994.10476870. `[CITAÇÃO-NÃO-ACESSADA]` (como em evaluation §11.2.)
- Politis, D. N.; White, H. (2004). "Automatic Block-Length Selection for the Dependent Bootstrap". *Econometric Reviews*, 23(1), 53–70. DOI: 10.1081/ETC-120028836.
- Bouthillier, X.; Delaunay, P.; Bronzi, M.; et al. (2021). "Accounting for Variance in Machine Learning Benchmarks". *Proceedings of MLSys*, 3, 747–769. arXiv:2103.03098.
- Koenker, R.; Bassett, G., Jr. (1978). "Regression Quantiles". *Econometrica*, 46(1), 33–50. DOI: 10.2307/1913643.
- Chernozhukov, V.; Fernández-Val, I.; Galichon, A. (2010). "Quantile and Probability Curves Without Crossing". *Econometrica*, 78(3), 1093–1125. DOI: 10.3982/ECTA7880. (Proposition 4, via modeling §2.4.)
- Nosek, B. A.; Ebersole, C. R.; DeHaven, A. C.; Mellor, D. T. (2018). "The preregistration revolution". *PNAS*, 115(11), 2600–2606. DOI: 10.1073/pnas.1708274114. (Via evaluation §8.)

### 11.2 Novas deste doc

Determinismo e incerteza do modelo:

- Goldberg, D. (1991). "What every computer scientist should know about floating-point arithmetic". *ACM Computing Surveys*, 23(1), 5–48. DOI: 10.1145/103162.103163. (§Systems Aspects › Languages and Compilers › Ambiguity.)
- Ahrens, P.; Demmel, J.; Nguyen, H. D. (2020). "Algorithms for Efficient Reproducible Floating Point Summation". *ACM Transactions on Mathematical Software*. DOI: 10.1145/3389360. `[CITAÇÃO-NÃO-ACESSADA]` (lido só o abstract do relatório técnico UCB/EECS-2016-121, de Ahrens, Nguyen & Demmel; nada load-bearing depende dela.)
- Gal, Y.; Ghahramani, Z. (2016). "Dropout as a Bayesian Approximation: Representing Model Uncertainty in Deep Learning". *Proceedings of the 33rd ICML*, PMLR 48, 1050–1059. arXiv:1506.02142. (§4, Eqs. (5)–(6).)
- Kendall, A.; Gal, Y. (2017). "What Uncertainties Do We Need in Bayesian Deep Learning for Computer Vision?". *Advances in Neural Information Processing Systems 30 (NeurIPS 2017)*. arXiv:1703.04977. (Abstract.)

Conformal:

- Angelopoulos, A. N.; Bates, S. (2023). "Conformal Prediction: A Gentle Introduction". *Foundations and Trends in Machine Learning*, 16(4), 494–591. DOI: 10.1561/2200000101. arXiv:2107.07511. (§3.2; Appendix C; Appendix D.)
- Vovk, V. (2012). "Conditional validity of inductive conformal predictors". *Proceedings of the Asian Conference on Machine Learning*, PMLR 25, 475–490. arXiv:1209.2673. (Proposition 2.)
- Oliveira, R. I.; Orenstein, P.; Ramos, T.; Romano, J. V. (2024). "Split Conformal Prediction and Non-Exchangeable Data". *Journal of Machine Learning Research*, 25(225). arXiv:2203.15885. (§2 p. 4; Theorem 1 p. 5; Theorem 4 p. 8; §3.4 Theorem 6 p. 9.)
- Chernozhukov, V.; Wüthrich, K.; Zhu, Y. (2018). "Exact and Robust Conformal Inference Methods for Predictive Machine Learning With Dependent Data". *Proceedings of the 31st Conference on Learning Theory (COLT)*, PMLR 75. arXiv:1802.06300. (§3.2 Theorem 2 p. 7; §3.3.)
- Stankevičiūtė, K.; Alaa, A. M.; van der Schaar, M. (2021). "Conformal time-series forecasting". *Advances in Neural Information Processing Systems 34 (NeurIPS 2021)*. (Já citado no ADR 5.4.0001; ausente do overview §10 até aqui. §3.3 p. 5; Fig. 1 p. 3.)
- Gibbs, I.; Candès, E. (2021). "Adaptive Conformal Inference Under Distribution Shift". *Advances in Neural Information Processing Systems 34 (NeurIPS 2021)*. arXiv:2106.00170. (Eq. (2) p. 3; Proposition 4.1 p. 6; §4.2; §7 p. 10.)
- Xu, C.; Xie, Y. (2021). "Conformal prediction interval for dynamic time-series". *Proceedings of the 38th ICML*, PMLR 139 (https://proceedings.mlr.press/v139/xu21h.html). arXiv:2010.09107 (título do arXiv: "Conformal prediction for time series"; título da versão PMLR não conferido mecanicamente). (§3 item (5) e §3.1 p. 4; §4.1 Assumption 1; Theorem 1.) Versão de periódico: Xu, C.; Xie, Y. (2023). "Conformal Prediction for Time Series". *IEEE Transactions on Pattern Analysis and Machine Intelligence*. DOI: 10.1109/TPAMI.2023.3272339 (não lida; os localizadores são da versão PMLR).
- Gupta, C.; Kuchibhotla, A. K.; Ramdas, A. (2022). "Nested conformal prediction and quantile out-of-bag ensemble methods". *Pattern Recognition*, 127, 108496. DOI: 10.1016/j.patcog.2021.108496. (Table 1.)
- Chernozhukov, V.; Wüthrich, K.; Zhu, Y. (2021). "Distributional conformal prediction". *PNAS*, 118(48), e2107794118. DOI: 10.1073/pnas.2107794118. (Algorithm 2; Theorems 1–3.)
- Vovk, V.; Shen, J.; Manokhin, V.; Xie, M. (2019). "Nonparametric predictive distributions based on conformal prediction". *Machine Learning*, 108(3), 445–474. DOI: 10.1007/s10994-018-5755-8. (Definition 1.)
- Fakoor, R.; Kim, T.; Mueller, J.; Smola, A. J.; Tibshirani, R. J. (2023). "Flexible Model Aggregation for Quantile Regression". *Journal of Machine Learning Research*, 24. arXiv:2103.00083. (§5.1 Eqs. (26)–(27); §5.3; §6.7.)
- Gasparin, M.; Ramdas, A. (2024). "Merging uncertainty sets via majority vote". Preprint, arXiv:2401.09379. (Theorem 2.1. **Preprint — só contexto.**)
- Stocker, M.; Małgorzewicz, W.; Fontana, M.; Ben Taieb, S. (2025). "A Gentle Introduction to Conformal Time Series Forecasting". Preprint, arXiv:2511.13608. (§4.3 p. 15; "Recommendations" p. 17. **Preprint — só contexto.** É a referência citada sem autores no ADR 5.1.0002.)

Atribuição de features:

- Breiman, L. (2001). "Random Forests". *Machine Learning*, 45(1), 5–32. DOI: 10.1023/A:1010933404324. (§10; paginação não conferida.)
- Fisher, A.; Rudin, C.; Dominici, F. (2019). "All Models are Wrong, but Many are Useful: Learning a Variable's Importance by Studying an Entire Class of Prediction Models Simultaneously". *Journal of Machine Learning Research*, 20(177), 1–81. arXiv:1801.01489. (§2; §3 Eq. (3.1).)
- Gregorutti, B.; Michel, B.; Saint-Pierre, P. (2015). "Grouped variable importance with random forests and application to multiple functional data analysis". *Computational Statistics & Data Analysis*, 90, 15–35. DOI: 10.1016/j.csda.2015.04.002. arXiv:1411.4170 (versão lida; localizador §2.1, correspondente à versão publicada no CSDA 90). (§2; §2.1.)
- Hooker, G.; Mentch, L.; Zhou, S. (2021). "Unrestricted permutation forces extrapolation: variable importance requires at least one more model, or there is no free variable importance". *Statistics and Computing*, 31, 82. DOI: 10.1007/s11222-021-10057-z. (Abstract; §5 pp. 12–13; §5.1.)
- Strobl, C.; Boulesteix, A.-L.; Kneib, T.; Augustin, T.; Zeileis, A. (2008). "Conditional variable importance for random forests". *BMC Bioinformatics*, 9, 307. DOI: 10.1186/1471-2105-9-307.
- Leung, K. K.; Rooke, C.; Smith, J.; Zuberi, S.; Volkovs, M. (2023). "Temporal Dependencies in Feature Importance for Time Series Predictions". *International Conference on Learning Representations (ICLR 2023)*. arXiv:2107.14317.
- Molnar, C.; Freiesleben, T.; König, G.; Herbinger, J.; Reisinger, T.; Casalicchio, G.; Wright, M. N.; Bischl, B. (2023). "Relating the Partial Dependence Plot and Permutation Feature Importance to the Data Generating Process". In *Explainable Artificial Intelligence (xAI 2023)*, Communications in Computer and Information Science, Springer. DOI: 10.1007/978-3-031-44064-9_24. (Lido em arXiv:2109.01433v1: §5 — variância de MC entre as n2 instâncias de teste, IC t por amostras independentes; §6; §7 — refits, "average the PD/PFI over m model fits", correção de Nadeau–Bengio para dados compartilhados no learner-PFI.)
- Williamson, B. D.; Gilbert, P. B.; Simon, N. R.; Carone, M. (2023). "A General Framework for Inference on Algorithm-Agnostic Variable Importance". *Journal of the American Statistical Association*, 118(543), 1645–1658. DOI: 10.1080/01621459.2021.2003200. (§2.)
- Covert, I.; Lundberg, S.; Lee, S.-I. (2021). "Explaining by Removing: A Unified Framework for Model Explanation". *Journal of Machine Learning Research*, 22(209), 1–90. arXiv:2011.14878. (§8.2.)
- Krishna, S.; Han, T.; Gu, A.; Wu, S.; Jabbari, S.; Lakkaraju, H. (2024). "The Disagreement Problem in Explainable Machine Learning: A Practitioner's Perspective". *Transactions on Machine Learning Research*. arXiv:2202.01602. (§3.2.)
- Jain, S.; Wallace, B. C. (2019). "Attention is not Explanation". *Proceedings of NAACL-HLT 2019*, 3543–3556. DOI: 10.18653/v1/N19-1357. (Abstract.)
- Wiegreffe, S.; Pinter, Y. (2019). "Attention is not not Explanation". *Proceedings of EMNLP-IJCNLP 2019*, 11–20. DOI: 10.18653/v1/D19-1002. (Conclusão.)

### 11.3 Documentação de biblioteca (mecânica, não teoria)

- **PyTorch v2.13.0** (pinado no uv.lock como 2.13.0+cpu; 2.12.1 no macOS — "plataforma" já implica versão diferente): `docs/source/notes/randomness.md` §Reproducibility e §PyTorch random number generator ("the same series of random numbers will be generated each time the application is run in the same environment"); `notes/numerical_accuracy.md` (não-associatividade; §Batched computations); docstring de `torch.use_deterministic_algorithms` (`torch/__init__.py`); `nn/modules/dropout.py` (identidade em eval). Neutralizar: lote de inferência, threads e build registrados (§3.1).
- **Lightning 2.6.5**: `fabric/utilities/seed.py::seed_everything` (só semeia random/numpy/torch); `trainer/connectors/accelerator_connector.py` (`deterministic=True` → `torch.use_deterministic_algorithms(True)`, nada além para CPU); `loops/prediction_loop.py` e `core/hooks.py::on_predict_model_eval` ("The predict loop by default calls ``.eval()``").
- **pytorch-forecasting 1.8.0**: `metrics/quantile.py::QuantileLoss.to_quantiles` ("return y_pred", sem amostragem); `data/timeseries/_timeseries.py` (`stop_randomization` → sem randomização de comprimento); `models/base/_base_model.py::BaseModel.predict` (cria um `Trainer` e chama `trainer.predict`; não sobrescreve `on_predict_model_eval`); `models/temporal_fusion_transformer/_tft.py` (VSN do encoder aplicada só às posições do encoder, l. 576–596; `interpret_output` faz a média sobre os passos válidos do encoder, l. 806–848) e `sub_modules.py` (softmax sobre variáveis por passo). Sem eixo de horizonte nos pesos da VSN do encoder (§5.3).
- **MAPIE 1.5.0** (lido em 2026-08-05) — **não está pinado no uv.lock nem declarado no `pyproject.toml`**; a versão efetiva é decisão da 7.2. `regression/quantile_regression.py::ConformalizedQuantileRegressor(estimator, confidence_level=0.9, prefit=False)`: com `prefit=True` exige "a list of three fitted quantile regressors … lower, upper, and median" com `fit`/`predict` (não aceita array de predições — só por wrapper); `predict_interval` com `symmetric_correction=False` por padrão → α/2 por cauda (= Theorem 2 de Romano); quantil `q = (1 − alpha) * (1 + 1/n)` com `np.quantile(..., method="higher")`; `conformalize` recebe `sample_weight` e **não o usa** (sem NexCP); `utils.py::_check_alpha_and_n_samples` recusa n < max(1/α, 1/(1−α)); `confidence_level` escalar → uma instância por (par, fold, horizonte). Neutralizar: wrapper sobre predições externas; pesos fora da lib.
