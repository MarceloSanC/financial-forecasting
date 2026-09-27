---
title: Avaliação probabilística de previsões — teoria do Step 6 (scoring, calibração, inferência pareada, backtests, pré-registro)
description: Teoria canônica do subdomínio probabilistic-forecast-evaluation — como se pontua uma grade finita de quantis (pinball, CRPS, interval score), como se caracteriza calibração e sharpness, o que é o gate de degeneração, como se faz inferência pareada (DM/HLN, Holm, MCS), como se backtesta cobertura (Christoffersen, Kupiec, VaR descritivo) e o que o pré-registro congela para que o scorecard seja mecânico
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 6 (6.1–6.5), ao questionar uma fórmula/convenção de avaliação, ou ao decidir se um tema pertence a este doc ou ao doc de modeling
keywords: [domain, evaluation, pinball, crps, interval-score, winkler, picp, mpiw, reliability, sharpness, degeneracy-gate, diebold-mariano, hln, holm, mcs, christoffersen, kupiec, var, preregistration, scorecard, per-horizon]
status: draft
created_at: 2026-09-12
updated_at: 2026-09-26
bounded_context: evaluation
subdomain: probabilistic-forecast-evaluation
references:
  - ../modeling/quantile-model-training.md
  - ../../adr/0_0_0054-evaluation-domain-doc-scope-and-boundary.md
  - ../../adr/0_0_0009-pinball-primary-crps-complementary.md
  - ../../adr/0_0_0010-paired-inference-dm-holm-mcs.md
  - ../../adr/0_0_0011-preregistration-invariants-and-h1-gate.md
  - ../../adr/0_0_0020-statistics-in-domain-over-value-objects.md
  - ../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md
  - ../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md
  - ../../adr/0_0_0052-baseline-quantile-emission-conventions.md
---

# Avaliação probabilística de previsões — teoria do Step 6

> **Categoria `domain/`** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este documento é a **teoria** (o quê/por quê) do subdomínio, transversal às
> Stages. Ele **não** é spec de implementação — não define schemas, caminhos de
> arquivo, nomes de classe nem cadências; isso pertence ao `technical.md` de
> cada Stage + código. Toda fórmula que muda um número reportado pelo projeto
> carrega citação rastreável a fonte primária. Onde a fonte **não** foi lida
> em primária, a citação carrega o rótulo `[CITAÇÃO-NÃO-ACESSADA]` e o texto
> diz o que está inferido; onde não existe fonte primária e a regra é política
> do projeto, o texto diz `[SEM-FONTE-PRIMÁRIA]` e a regra vira convenção
> (§10). As bifurcações do gate (**B-…**) foram triadas pela skill
> `evidence-resolution` (2026-09-26): as de classe E/C (evidência ou convenção,
> todas anteriores aos dados) foram fechadas pelo agente e registradas em §10.1
> no formato `[decision:E|C]`, com o degrau que decidiu e a verificação da
> citação; a única de classe P (redação do claim de H1, **B1**) foi decidida
> pelo humano (issue #78, 2026-09-26). A ratificação do doc inteiro
> (`status: accepted`) continua humana.

## 1. Escopo e como consumir este doc

**Cobre** os cinco blocos de teoria do Step 6, todos sobre o mesmo objeto (a
grade de quantis emitida pelo Step 5, alinhada ao realizado):

1. **scoring próprio sobre a grade** — pinball por nível e média, CRPS a partir
   da grade, interval/Winkler score por par simétrico (§3);
2. **caracterização de calibração e sharpness + gate de degeneração** —
   cobertura marginal por τ, PICP/MPIW, bandas, o que é uma grade colapsada e
   o que se faz com ela (§4, §5);
3. **inferência pareada** — Diebold–Mariano com correção HLN, Holm, Model
   Confidence Set, e as decisões de pareamento (folds, seeds, interseção) (§6);
4. **backtests de cobertura condicional e VaR descritivo** — Christoffersen,
   Kupiec, hits por cauda, o caso multi-passo (§7);
5. **pré-registro e scorecard mecânico** — o que se congela, quando, por quê,
   e a estrutura do veredito por horizonte (§8);

apoiados nos **fundamentos comuns** (§2) e fechados por uma seção-fronteira
(§9), uma tabela-resumo de convenções (§10) e as referências (§11).

**Não cobre**:

- **Implementação** (value objects, serviços, ports, schemas gold, fixtures,
  tolerâncias numéricas concretas) → `technical.md` das Stages 6.1–6.5.
- **Conformal / CQR** e a "cobertura empírica" do conformal → Step 7 (o doc
  de domínio daquele gate; ver §9.2).
- **Teoria do Step 5** (como cada modelo emite a grade, pinball como loss de
  treino, rearranjo, cohort) → pressuposta; vive em
  [`quantile-model-training.md`](../modeling/quantile-model-training.md) e é
  citada por ponteiro (§2.8).

**Mapa de consumo** (que Stage lê o quê):

| Stage | Seções que consome |
|---|---|
| 6.1 — scoring e métricas de calibração | §3, §4.1–§4.3, §4.5–§4.6, §5 (+ §2) |
| 6.2 — inferência pareada (DM/MCS/Holm) | §6 (+ §2.5, §2.7, §5.3 sobre não-exclusão) |
| 6.3 — backtests de calibração e risco | §7, §4.4 (bandas) (+ §4.1–§4.2 para os hits) |
| 6.4 — gold builders e quality gates | sem teoria própria; consome os **invariantes** §2.1 (objeto), §2.7 (por horizonte), §5.3 (taxa de degeneração), §6.7 (alinhamento) |
| 6.5 — pré-registro e scorecard | §8 (+ os parâmetros pré-registráveis de §4.4, §5.3, §6.4–§6.5, §7.4, §7.6) |
| 8.1 / 8.2 — execução confirmatória e auditoria de equivalência | §8.2 (ordem), §8.6 (veredito), §10 |
| todas | §2 (fundamentos) e §9 (fronteira) |

**Hierarquia de fontes.** Overview > Roadmap > este doc > `concept.md` das
Stages. O que já estava ratificado no repo (overview §4/§7/§10/§11, doc de
modeling §2/§3.4/§7, ADRs 0.0.0020/0.0.0021/0.0.0052/4.3.0002) é citado como
tal e **não** re-derivado; a pesquisa externa entrou só nas lacunas, sob a
barra de fontes do gate (paper revisado, livro-texto consagrado ou
documentação/código oficial de biblioteca; nunca blog ou fórum).

## 2. Fundamentos comuns

### 2.1 O objeto avaliado

Para cada modelo m, horizonte h e ponto alinhado t, a previsão é um vetor de
K quantis sobre uma **grade comum** G = {τ_1 < … < τ_K} ⊂ (0,1), a mesma para
candidato, GBM e baselines (contrato do modeling §7 item 1). A grade é
**simétrica** — τ_{K+1−k} = 1 − τ_k, com a mediana no centro — de modo que os
níveis se organizam em (K−1)/2 **pares simétricos** (τ_k, 1 − τ_k) mais a
mediana. Toda a teoria abaixo é escrita para uma grade simétrica genérica; os
níveis exatos são entrada do cohort (5.5) e conteúdo do pré-registro (6.5), não
decisão deste doc (tensão T14 do inventário do gate: os ADRs do Step 5
exemplificam extremos 0.02 e 0.05 sem decidir). O que muda com os extremos é
dito onde importa (poder nas caudas, §4.4 e §7.3).

O **realizado** y_t é o `target_return` do dataset persistido — o retorno log
de um dia realizado na sessão `t+h` (modeling §2.1; ADR 3.5.0001) — juntado à
previsão por `target_timestamp` (ADR 4.3.0001: índice de sessão, nunca
timedelta). **Convenção (ancorada em ADR 4.3.0001):** a avaliação **nunca
recomputa** o alvo; ela lê o realizado persistido e o junta pela chave de
alinhamento. Há **uma observação por ponto alinhado** (dedup
operationally-latest do harness — modeling §7 item 2), e tudo é feito **por
horizonte** (§2.7). T denota o número de pontos alinhados de um horizonte.

### 2.2 O que se pontua: o vetor rearranjado, nunca o bruto

O lado da modelagem persiste, por nível, tanto a saída bruta do modelo quanto o
valor **pós-guardrail** (rearranjo monótono por ordenação — modeling §2.4;
[ADR 4.3.0002](../../adr/4_3_0002-quantile-forecast-dense-grid-guardrail.md)).
A avaliação pontua **o vetor rearranjado**, por três razões:

1. **É a previsão entregue.** O score é função da previsão quotada (Gneiting &
   Raftery 2007, §1); avaliar o bruto avaliaria uma previsão que ninguém usa.
2. **Rearranjar nunca piora a pinball na grade.** Berrisch & Ziel (2023, §3.4)
   afirmam, atribuindo a Chernozhukov, Fernández-Val & Galichon (2010), que o
   rearranjo "will never reduce the forecasting performance in terms of the
   quantile loss". A garantia da Proposition 4 de CFG é em distância L_p à curva
   verdadeira (modeling §2.4); a versão **amostra a amostra** para a soma na
   grade é derivação elementar da desigualdade de rearranjo de Lorentz (1953)
   `[CITAÇÃO-NÃO-ACESSADA]` — f(τ, q) = ρ_τ(y − q) é submodular
   (∂²f/∂τ∂q = −1 < 0), logo Σ_k ρ_{τ_k}(y − q_{σ(k)}) é minimizada pelo
   emparelhamento comonotônico (q ordenado como τ). Consequência:
   P̄_G(rearranjado) ≤ P̄_G(bruto) para **todo** y, **com pesos iguais na
   grade** (a derivação usa a soma não ponderada; sob pesos de quadratura em
   τ a desigualdade pode falhar — conferido numericamente na verificação do
   gate). Não há garantia por nível τ isolado — só para a soma.
3. **O interval score só é definido para l ≤ u** (Brehmer & Gneiting 2021,
   §3.2: domínio de ação {[a, b] : a ≤ b}); um par cruzado no bruto obrigaria a
   inventar uma convenção.

**Convenção (ancorada em modeling §2.4 + ADR 4.3.0002 Alt C):** pontua-se o
vetor rearranjado; o bruto **não** é pontuado; a **taxa de aplicação do
guardrail** por (modelo, horizonte) entra no perfil como diagnóstico de
cruzamento (Zamo & Naveau 2018, Fig. 7, reportam o número de quantis únicos
como diagnóstico análogo). Alternativa real descartada: pontuar ambos — nenhum
paper lido recomenda, e dobraria o que o leitor precisa reconciliar sem
acrescentar evidência.

### 2.3 Escala: ρ_τ sem o fator 2

A pinball do projeto é ρ_τ(u) = u·(τ − 1{u < 0}), u = y − q̂_τ (modeling §2.2;
Koenker & Bassett 1978 p. 38; Gneiting 2011 Eq. (24)). Existem **duas escalas**
na literatura e nas bibliotecas: ρ_τ e QS_τ = 2ρ_τ (Gneiting & Ranjan 2011
Eq. (6), onde o fator 2 vive dentro do QS para que ∫QS dτ = CRPS).
**Convenção (T8):** todo número de pinball reportado pelo projeto está na
escala ρ_τ; CRPS_Q (§3.2) está na escala do CRPS (unidade de y, com o 2). Os
oráculos: `sklearn` = ρ_τ; `scoringrules.quantile_score` = ρ_τ;
`scoringrules.crps_quantile` = 2·P̄_G; pytorch-forecasting = 2ρ_τ (modeling
§9.3). O fator constante não altera ordenação, DM nem MCS — mas altera o
número, e por isso a escala é declarada (§11.3).

### 2.4 Notação

    ρ_τ(u)          pinball no nível τ, u = y − q̂_τ
    P̄_τ             pinball média no nível τ:  (1/T) Σ_t ρ_τ(y_t − q̂_{τ,t})
    L_t             pinball média na grade no ponto t:  (1/K) Σ_k ρ_{τ_k}(y_t − q̂_{τ_k,t})
    P̄_G             pinball média na grade:  (1/T) Σ_t L_t = (1/K) Σ_k P̄_{τ_k}
    CRPS_Q          CRPS por quadratura na grade:  2·L_t (por ponto), 2·P̄_G (média)
    IS_α            interval score do par simétrico de miscobertura α = 2τ_l
    ĉ(τ)            cobertura empírica no nível τ:  (1/T) Σ_t 1{y_t ≤ q̂_{τ,t}}
    I_t             hit (acerto) de um intervalo ou de uma cauda; V_t = 1 − I_t (violação)
    d_t             diferencial de perda pareado:  L_{cand,t} − L_{comp,t}
    T               nº de pontos alinhados de um horizonte;  h = horizonte

### 2.5 Proper e consistent: por que a comparação é bem-posta

- Uma scoring rule S é **proper** se a previsão honesta maximiza o score
  esperado — S(Q, Q) ≥ S(P, Q) — e **estritamente proper** se a igualdade só
  vale para P = Q (Gneiting & Raftery 2007, §1, Eq. (1), p. 360).
- Uma scoring **function** é **consistente** para um funcional (aqui, o
  quantil τ) se E_F S(t, Y) ≤ E_F S(x, Y) para t no funcional (Gneiting 2011,
  Definition 2.1); toda scoring function consistente induz uma proper scoring
  rule (Theorem 2.4); misturas de funções consistentes para o mesmo funcional
  são consistentes (Theorem 2.3). A pinball é **estritamente consistente** para
  o τ-quantil (Eq. (24); o Theorem 9 da versão JASA — Theorem 3.3 no preprint
  arXiv:0912.0902 — caracteriza a classe GPL; modeling §2.2).
- Gneiting (2011, §1.1, Eq. (1)) fixa o critério de comparação como a **perda
  média** S̄ = (1/T) Σ S(x_t, y_t); o DM (§6.1) é a inferência sobre a diferença
  de duas S̄. E §5 (a *plea*): "it is essential that either the scoring function
  be specified ex ante, or an elicitable target functional be named" — este
  projeto faz as duas coisas (nomeia o quantil, fixa a pinball ex ante).
- **Preditor pontual como Dirac.** O CRPS "generalizes the absolute error to
  which it reduces if F is a deterministic forecast — that is, a point measure.
  Thus the CRPS provides a direct way to compare deterministic and
  probabilistic forecasts" (Gneiting & Raftery 2007, §4.2, p. 367). Reafirmado
  em Gneiting & Ranjan (2011, §3.1) e Bracher et al. (2021, §2.2). É o que
  torna bem-posta a comparação candidato × baselines pontuais (modeling §3.4).
- O que a consistência **não** dá: comparabilidade entre τ distintos (escalas
  diferentes de ρ_τ) — compara-se o mesmo τ entre modelos, nunca τ's entre si;
  e não dá calibração — um modelo pode ter pinball menor sendo pior calibrado.
  Daí o gate H1 separado (§8.5).

### 2.6 O princípio: sharpness sujeito a calibração

Gneiting, Balabdaoui & Raftery (2007, §1 p. 246; §2.4 p. 250): "the paradigm of
maximizing the sharpness of the predictive distributions subject to
calibration. Calibration refers to the statistical consistency between the
distributional forecasts and the observations and is a joint property of the
predictions and the observed values. Sharpness refers to the concentration of
the predictive distributions and is a property of the forecasts only." A
Definition 1 (p. 247) distingue calibração **probabilística** (Eq. (3): a
média de G_t(F_t⁻¹(p)) → p para todo p), *exceedance* (Eq. (4)) e
**marginal** (as médias de F_t e G_t coincidem). Neste doc, calibração é a
**restrição** (gate H1) e o skill relativo em score próprio é o **objetivo**
(H2) — a ponte "skill só faz sentido sob calibração" é aplicação do paradigma,
não frase de GBR (que falam de sharpness, não de pinball vs baselines).

### 2.7 Por horizonte, sempre

Toda métrica, teste e veredito é por horizonte; **nada é agregado entre
horizontes** (overview §7). O fundamento é a estrutura de dependência
específica de h do diferencial de perda (erros ótimos h-passos são MA(h−1) —
Diebold & Mariano 1995, p. 254; Harvey, Leybourne & Newbold 1997, pp. 281–282)
mais a prática consolidada de avaliação por horizonte na origem rolante (FPP3
§5.10). Não é teorema, e o doc o diz: argumento completo, com o que está
inferido de fontes não acessadas, em §8.7. Consequências: família de Holm por
horizonte (§6.4), MCS por horizonte (§6.5), veredito por horizonte (§8.6).

### 2.8 O que o Step 5 promete (ponteiro)

Este doc consome, sem re-derivar, o contrato do modeling §7: (1) grade comum
para todos os modelos, em formato long com o nível na chave — pinball pareável
nível a nível; (2) uma observação por `target_timestamp`; (3) a mesma ρ_τ como
loss de treino e scoring function da avaliação (Gneiting 2011 Thm 9); (4) grade
degenerada dos baselines pontuais como Dirac (modeling §3.4), cujo tratamento
na avaliação é assunto **deste** doc (§5). Também pressupõe o protocolo temporal
da 5.1 (folds expansivos, purga+embargo, partição quádrupla — ADRs 5.1.0001–3).

## 3. Proper scoring rules sobre a grade (Stage 6.1)

### 3.1 Pinball por nível e média na grade

**O que é.** A scoring function estritamente consistente para o τ-quantil
(§2.5); loss de treino do GBM/TFT e **métrica primária** de H2 (overview §4).

**Como se calcula.** Por nível, P̄_τ = (1/T) Σ_t ρ_τ(y_t − q̂_{τ,t}); na grade,
P̄_G = (1/K) Σ_k P̄_{τ_k} com **pesos iguais** por nível (§2.4). A convenção de
empate (1{u < 0} vs 1{u ≤ 0}) é irrelevante: em y = q̂ o fator (q̂ − y) é zero.

**Fonte.** Koenker & Bassett (1978) p. 38 (origem); Gneiting (2011) Eq. (24)
§3.3 e Thm 9 (consistência estrita); Gneiting & Raftery (2007) §6.1 Eq. (41)
p. 370 — "the econometric literature refers to the scoring rule (41) as the
tick or check loss function". **P̄_G é ela própria uma proper scoring rule**,
não só "aproximação": Gneiting & Ranjan (2011, §3.1, texto após a Eq. (17))
— "the discrete versions themselves are proper scoring rules, that arise as
special cases … if the integral is taken with respect to a discrete Stieltjes
measure".

**Como se aplica aqui.** K números P̄_τ + um número P̄_G por (modelo,
horizonte). A série por ponto L_t é a **loss pareada** de H2 (§6). O gráfico
P̄_τ × τ é o *quantile score plot* (Gneiting & Ranjan 2011, Eq. (23), atribuído
a Laio & Tamea 2007) — perfil de onde (cauda vs centro) o skill vive.

**Convenções.** (FA2) pesos iguais na grade, ratificado de fato (modeling
§2.3 fala em quadratura; a lib usa iguais; é score próprio); pesos de
quadratura em τ ficam como sensibilidade **só** se um dia a grade for
não-equiespaçada por desenho — e, nesse caso, sem a garantia "rearranjar
nunca piora" do §2.2 (que vale para pesos iguais). (T8) escala ρ_τ.

**Fork descartado.** Pesos trapezoidais em τ aproximam melhor ∫ρ_α dα mas
mudam o número e potencialmente a ordenação; pesos iguais super-representam as
caudas (Bracher et al. 2021, Appendix A, dizem o mesmo da grade do Forecast
Hub: "we thus put slightly more weight on the tails"). Não adotado.

### 3.2 CRPS a partir da grade

**O que é.** O CRPS é a integral do quantile score sobre τ:
CRPS(F, y) = ∫₀¹ QS_α(F⁻¹(α), y) dα, QS_α = 2ρ_α (Gneiting & Ranjan 2011,
Eq. (6); Laio & Tamea 2007, Eqs. (11)–(14), pp. 1271–1272 — origem da
decomposição quantílica; modeling §2.3). Com uma grade finita, "CRPS" só existe
via **estimador**, e há três famílias na literatura (fork FA1):

- **(a) quadratura uniforme na grade:**
  CRPS_Q(y) = (2/K) Σ_k ρ_{τ_k}(y − q̂_{τ_k}) = 2·L_t. Berrisch & Ziel (2023,
  §3.1, Eq. (9)): "CRPS(F, y) ≈ (2/M) Σ_m QL_{p_m}(F⁻¹(p_m), y)" para uma grade
  equidistante; Bracher et al. (2021, Appendix A, Eq. (6)) — a mesma soma sobre
  os 2K+1 níveis do Forecast Hub. É o que `scoringrules.crps_quantile`
  implementa (§11.3).
- **(b) K quantis tratados como ensemble** (CDF em degraus; estimadores
  INT/NRG/PWM/Fair de Zamo & Naveau 2018, §2, Eq. (2), §3.2): ignoram os τ_k;
  para níveis "regulares" a CDF em degraus fica **abaixo** da CDF prevista
  (viés); empates (comuns em regressão quantílica) tornam os estimadores
  "inaccurate … biased" (§3.2.3).
- **(c) função quantílica interpolada linearmente + convenção de cauda**
  (Gasthaus et al. 2019, §3, Eqs. (10)–(11): integral fechada para spline
  linear monótono em [0,1]). Exige F⁻¹ em **todo** [0,1]; a grade começa em τ_1
  > 0 e termina em τ_K < 1, logo as caudas [0, τ_1) e (τ_K, 1] precisam de
  extrapolação por convenção — e o número depende dela.

**Caso Dirac.** Com q̂_{τ_k} ≡ x para todo k, (a) devolve
2|y − x|·mean_k(τ_k) se y ≥ x e 2|y − x|·(1 − mean_k τ_k) se y < x; para grade
**simétrica** (mean τ_k = 0.5) isso é **exatamente |y − x|** = CRPS do Dirac
(Gneiting & Raftery 2007 §4.2). Derivação elementar, conferida numericamente;
para grade assimétrica o estimador fica enviesado. Fixture analítica: baseline
pontual + grade simétrica ⇒ CRPS_Q = |y − x|, P̄_G = |y − x|/2 (o "pinball ≈
MAE/2" do modeling §3.4, confirmado pelo User Guide do sklearn: "half of
mean_absolute_error when alpha = 0.5").

**Convenção do projeto (B-CRPS — decidida, §10.1).** O CRPS reportado é o
estimador (a): CRPS_Q = 2·P̄_G, pesos iguais, na grade comum. O doc **declara
explicitamente**: com grade comum, CRPS_Q carrega a **mesma ordenação** da
pinball média para todo modelo e toda observação — mesmo DM (a estatística de
2d_t é idêntica), mesmo MCS — e portanto **não é evidência independente**. O
papel "complementar" (overview §11, linha `0_0_0009`) é (i) **escala**: reportar
na unidade de y, comparável ao MAE dos baselines pontuais **do próprio
projeto** ("the units are those of the absolute error", Bracher et al. §2.2);
e (ii) **perfil por τ**: o quantile score plot (§3.1). Nunca um segundo
veredito. **Não** é comparável a CRPS publicado: a aproximação de Berrisch &
Ziel (2023, Eq. (9)) pressupõe grade **densa e equidistante**, e a grade de
~7 níveis não é nenhuma das duas — CRPS_Q aproxima o CRPS da distribuição
só na medida em que a grade o permite, e o erro dessa aproximação é
desconhecido. Rotulagem honesta: "CRPS_Q = 2 × pinball média na grade (pesos
iguais)", nunca "CRPS" sem qualificador. Oráculo: `scoringrules.crps_quantile`
(§11.3), cuja versão a Stage 6.1 **pina** em `pyproject.toml`/`uv.lock` (hoje
a lib não está nas dependências). Alternativa real descartada: (b)/(c) dariam um número
**diferente** (métrica nova, com viés ou convenção de cauda próprios) sem
oráculo direto na biblioteca e sem o Dirac exato; a informação distribucional
"a mais" que prometeriam vem de uma convenção, não dos dados.

### 3.3 Interval score / Winkler score por par simétrico

**O que é.** O score próprio do intervalo central (1−α) com extremos nos
quantis α/2 e 1−α/2 — o intervalo *equal-tailed* (ETI).

**Fórmula.** Gneiting & Raftery (2007, §6.2, Eq. (43), p. 370):

    IS_α(l, u; y) = (u − l) + (2/α)(l − y)·1{y < l} + (2/α)(y − u)·1{y > u}

"The forecaster is rewarded for narrow prediction intervals, and he or she
incurs a penalty, the size of which depends on α, if the observation misses the
interval." Origem: Winkler (1972) `[CITAÇÃO-NÃO-ACESSADA]` (Brehmer &
Gneiting 2021 §3.2 chamam-no "classical interval score of Winkler (1972)"; GR
2007 §6.2 remontam-no a Dunsmore (1968), Winkler (1972) e Winkler & Murphy
(1979)). Propriedade: Brehmer & Gneiting
(2021, §3.2, Eqs. (5)–(6), Theorem 3.1) — o IS é, a menos de equivalência, o
**único** score consistente para o ETI que é invariante por translação e
simétrico; domínio {[a, b] : a ≤ b}, logo largura zero está no domínio:
IS_α([x, x], y) = (2/α)|y − x| (finito, bem-posto).

**Decomposição.** Bracher et al. (2021, §2.2): largura u − l ("describes the
sharpness of F") + penalidade inferior + penalidade superior; ainda no §2.2:
as médias "represent the sharpness and calibration of the forecasts,
respectively" (o §4.1 é a representação gráfica).

**Identidade com as pinballs extremas (load-bearing).** Bracher et al. (2021,
Appendix A, Eq. (5)): IS_α = (QS_{α/2} + QS_{1−α/2})/α; em pinball,

    IS_α = (2/α) · [ ρ_{α/2}(y − l) + ρ_{1−α/2}(y − u) ]

(casos y < l, l ≤ y ≤ u, y > u conferidos algebricamente e numericamente).
Segunda fonte: Brehmer & Gneiting Eq. (5)–(6) com w_1 = w_2 = 2/α; Askanazi et
al. (2018, §3.2.2): "all Winkler-type loss functions are quantile-type loss
functions". Consequência: o Winkler **não** exige cálculo próprio — é (2/α)
vezes a soma de duas pinballs já computadas; o oráculo vira teste de
identidade.

**Nominal dinâmico.** Para o par (τ_l, τ_u) = (α/2, 1−α/2) da grade, o nominal
é 1 − α = τ_u − τ_l — ex.: (0.02, 0.98) ⇒ 96 %, (0.1, 0.9) ⇒ 80 %,
(0.25, 0.75) ⇒ 50 % (mapeamento idêntico ao do Forecast Hub — Bracher §2.2).
"Dinâmico" significa: o nominal é **função da grade pré-registrada**, não uma
constante do doc.

**Por que não WIS agregado.** O *weighted interval score* com pesos canônicos
(Bracher Eqs. (1)–(2), w_0 = 1/2, w_m = α_m/2, com M = (K−1)/2 pares — o "K"
de Bracher é o nosso M) satisfaz (Eqs. (4)/(6))
WIS = (1/(2M+1)) Σ_k 2·{1(y ≤ q_k) − τ_k}(q_k − y) — isto é, **WIS ≡ 2 × pinball
média sobre os K = 2M+1 níveis ≡ CRPS_Q** na grade {mediana + M pares}
(conferido numericamente na grade de 7). Reportar WIS, CRPS_Q e P̄_G é reportar o mesmo
número três vezes. A informação **nova** é o IS_α **por par**, não escalado,
com a decomposição largura/penalidade.

**No Dirac.** IS_α = (2/α)|y − x| — para α = 0.04 é 50·|y − x|: a "penalização
severa nos extremos, esperada e informativa" do modeling §3.4 tem aqui sua
expressão exata.

**Convenção do projeto (FA4/FA10).** IS_α **por par simétrico** (um número por
par, por (modelo, horizonte)), não escalado, com a decomposição em largura
média (= MPIW do §4.2) + penalidade média inferior + superior; WIS agregado
**não** reportado; **só pares simétricos** (pares assimétricos não são ETI —
o score consistente teria pesos 1/τ_l e 1/(1−τ_u), derivação do Corollary 1 de
GR 2007, e não é "Winkler"; Askanazi et al.: o Winkler pressupõe *equal-tailed*,
que é o caso do projeto). Convenção de `alpha` das libs: **miscobertura**
(§11.3).

## 4. Caracterização de calibração e sharpness (Stages 6.1 / 6.3)

### 4.1 Cobertura marginal por τ (reliability)

**O que é.** Para cada nível da grade, a frequência com que o realizado fica
abaixo do quantil previsto deve tender ao próprio nível:

    ĉ(τ) = (1/T) Σ_t 1{y_t ≤ q̂_{τ,t}}   →   τ

**Fonte.** GBR (2007, §3.1, Theorem 2, p. 252): sob F_t, G_t contínuas e
estritamente crescentes e {x_t} α-mixing, "(1/T) Σ 1(p_t ≤ p) → p almost surely for all p if and only if (F_t)
is probabilistically calibrated" (p_t = PIT); como x_t ≤ F_t⁻¹(p) ⟺ p_t ≤ p, a
condição **é** a cobertura empírica por quantil, e "stands in its own right as
a criterion for the validity of probabilistic forecasts". Kuleshov, Fenner &
Ermon (2018, §3.1 Eq. (3); §3.5 Eq. (8)): o gráfico {(τ_k, ĉ(τ_k))} é o
**reliability diagram para quantis** — calibrado ⟺ diagonal. Nome canônico
do objeto de H1: *unconditional α-quantile calibration* (Gneiting & Resin 2023,
Definition 2.9 / Eq. (9)); a versão **condicional** (T-calibration, Definition
2.7; CORP via regressão isotônica) é extensão fora do escopo 6.1 — o
Christoffersen (§7) cobre dependência **temporal**, não condicionamento no
valor previsto.

**Como se aplica aqui.** Vetor ĉ(τ_k), k = 1..K, por (modelo, horizonte),
pooled sobre folds (§4.4), + reliability diagram. O "calibration error"
Σ_j w_j (p_j − p̂_j)² de Kuleshov Eq. (9) é diagnóstico, **não** proper score —
não pode ser veredito. A ressalva do modeling §2.4 vale: o rearranjo corrige
monotonicidade, não calibração; ADR 0.0.0052 antecipa que as caudas gaussianas
de EWMA/AR(1) devem sub-cobrir em τ extremo — achado informativo, não defeito.

### 4.2 PICP e MPIW por par (nominal dinâmico)

**Definições.** Khosravi, Nahavandi, Creighton & Atiya (2011a, IEEE TNN 22(3);
2011b, IEEE TNN 22(9)) `[CITAÇÃO-NÃO-ACESSADA]` — ambos fechados; as definições
foram verificadas em fonte revisada por pares que as reproduz citando Khosravi:
Pearce, Brintrup, Zaki & Neely (2018, ICML, §3, Eqs. (4)–(7)):

    k_t  = 1{ l_t ≤ y_t ≤ u_t }
    PICP = (1/T) Σ_t k_t
    MPIW = (1/T) Σ_t (u_t − l_t)

Para o par (τ_l, τ_u) e F contínua, P(q_{τ_l} < Y ≤ q_{τ_u}) = τ_u − τ_l
(elementar; Brehmer & Gneiting §3.2 Eq. (4) definem o ETI via quantis e notam
que só para distribuições **discretas** a cobertura pode diferir). Logo o
**nominal** do PICP é τ_u − τ_l (0.96 / 0.80 / 0.50 na grade de 7). Com empates
de medida zero, **PICP = ĉ(τ_u) − ĉ(τ_l)** (§2.4): cobertura marginal correta
nas duas caudas ⇒ PICP nominal, **mas não o inverso** — o PICP é invariante a
um deslocamento comum da miscobertura das duas caudas (ĉ(τ_l) = τ_l + δ e
ĉ(τ_u) = τ_u + δ dão PICP exatamente nominal com as caudas miscalibradas em
sentidos opostos). O perfil ĉ(τ) por cauda (§4.1) e os hits unilaterais (§7.5)
são o que detecta assimetria; um gate só por PICP seria **necessário, não
suficiente** — por isso o gate H1 (§8.5) é definido **por cauda** do par
primário, e o PICP fica no perfil. O PICP dos intervalos centrais "can be
read off the PIT histogram" (GBR §3.1).

**Como se aplica aqui.** PICP e MPIW por par simétrico, por (modelo,
horizonte). O PICP do par primário é **perfil** de H1 — o gate usa as duas
caudas desse par separadamente (§8.5); o MPIW é a largura
média do IS_α (§3.3) e é **descritivo** (roadmap 6.3: "descritivas
não-inferenciais").

### 4.3 Sharpness

GBR (2007, §3.3, p. 255): "Sharpness refers to the concentration of the
predictive distributions and is a property of the forecasts only. … To assess
sharpness, we use numerical and graphical summaries of the width of prediction
intervals … In real world applications, conditional heteroscedasticity often
leads to considerable variability in the width of the prediction intervals.
The average width then is insufficient to characterize sharpness, and we follow
Bremnes (2004) in proposing box plots as a more instructive graphical device.
We refer to this type of display as a sharpness diagram."

**Convenção (FA5).** Sharpness = MPIW **em unidade de y** (log-retorno), não
NMPIW (÷ amplitude do alvo): para retornos diários a amplitude no OOS é
dominada por um ou dois dias extremos e muda por fold/horizonte —
normalizar tornaria a métrica instável e não-pareável; MPIW na unidade de y é
comparável a IS_α e CRPS_Q (mesma escala). `[SEM-FONTE-PRIMÁRIA]` para a
preferência (a teoria só diz que ambos são descritivos) — política. Além da
média, o **sharpness diagram** (box plot / quantis das larguras) entra no
perfil, como GBR recomendam sob heterocedasticidade. Kuleshov Eq. (10)
(variância média de F_t) é inaplicável a uma grade finita sem convenção de
cauda. Sharpness **nunca** é score: só "subject to calibration" (§2.6).

### 4.4 Bandas de cobertura empírica

**Modelo de referência.** Sob calibração **e** independência dos hits, c = Σ_t
1{y_t ≤ q̂_{τ,t}} ~ Binomial(T, τ), Var(ĉ) = τ(1−τ)/T. Fontes que usam
exatamente esta estrutura: Bröcker & Smith (2007, §2–§3: *consistency bars*
por reamostragem sob a nula de confiabilidade, "the number of … events in each
bin would follow a binomial distribution"); Pearce et al. (2018, §3: "k_i ~
Bernoulli(1 − α) … iid … c ~ Binomial(n, 1 − α)", com o aviso "This
independence assumption may not hold for data points clustered close
together"); Gneiting & Resin (2023, Appendix B.1, Algorithms 2–3 —
referenciados em §3.2: *consistency bands* sob a nula). Kupiec (1995) POF e Christoffersen (1998) LR_uc são o **mesmo
modelo binomial** em forma de teste (§7.2–§7.3).

**Intervalo de Wilson.** Brown, Cai & DasGupta (2001, §3.1.1, Eq. (4),
p. 107), com c acertos em T, p̂ = c/T, q̂ = 1 − p̂, κ = z_{α/2}:

    CI_W = (c + κ²/2)/(T + κ²)  ±  κ·√T/(T + κ²) · ( p̂q̂ + κ²/(4T) )^{1/2}

— "the confidence interval based on inverting the test … that uses the null
standard error (pq)^{1/2} n^{−1/2}". O Wald p̂ ± κ√(p̂q̂/T) (Eq. (1), p. 103) é
desaconselhado: "the chaotic coverage properties of the Wald interval are far
more persistent than is appreciated … we recommend the Wilson interval or the
equal-tailed Jeffreys prior interval for small n" (abstract, p. 101). Origem:
Wilson (1927) `[CITAÇÃO-NÃO-ACESSADA]`.

**Ordem de grandeza (cálculo próprio a partir da Eq. (4), 95 %, c = round(T·p)):**
τ = 0.02: T = 500 → [0.011, 0.036]; T = 1000 → [0.013, 0.031]. Intervalo 96 %:
T = 500 → [0.939, 0.974]. Intervalo 80 %: T = 500 → [0.763, 0.833]. Intervalo
50 %: T = 500 → [0.456, 0.544]. Qualquer tolerância fixa mais estreita que ±1
p.p. em τ = 0.02 com T de centenas está **abaixo da resolução estatística**; e
com n ≈ 250 por fold e τ = 0.02 (E[c] = 5), o erro-padrão é ≈ 0.009 — nada é
rejeitável por fold. O poder vem do **pooling por horizonte**.

**Dependência serial (aviso obrigatório).** A banda binomial pressupõe hits
iid. GBR Theorem 2 exige α-mixing só para a consistência (convergência), nada
diz da variância finita, que sob dependência positiva (clustering de
volatilidade ⇒ clustering de violações) é **maior** que τ(1−τ)/T; e mesmo
previsões ótimas h-passos podem ter hits dependentes até o lag h−1 (Askanazi
et al. 2018, nota 1: "In the general h-step-ahead case we simply replace 'iid'
with 'at most (h − 1)-dependent'"; §7.4). Consequência: a banda binomial é
**anti-conservadora** (estreita demais) para h+7 e sob clustering. Alternativas
legítimas (block bootstrap dos hits, erro-padrão HAC do hit médio, reamostragem
tipo Bröcker–Smith condicionada) — nenhuma é canônica para quantis de retornos;
a correção HAC seria composição com o que a 6.2 usa `[SEM-FONTE-PRIMÁRIA para a
combinação]`.

**Convenção do projeto (B-BANDAS — decidida, §10.1).** A banda de cobertura
de H1 é o **intervalo de Wilson** (BCD 2001 Eq. (4)), computado **por
horizonte, pooled sobre folds** (T = soma dos blocos de test), e o critério é
"a banda **contém o nominal**" — a banda escala com T e tem fonte primária
para a fórmula. Nível: **95 %** para um teste isolado (PICP e ĉ(τ) no
perfil); **97,5 % por cauda** no gate H1, que testa as duas caudas do par
primário com Bonferroni (§8.5). Com S seeds, o n da banda é o de **um** conjunto de pontos alinhados (≈ T; ver abaixo), **nunca S·T**:
as seeds são réplicas do mesmo ponto alinhado, não observações novas (a
cobertura entra como média entre seeds — §6.9). O LR_uc/POF (§7.2–§7.3) é reportado como o **teste formal
associado** — mesma nula binomial, mas é um teste de razão de verossimilhanças,
enquanto o Wilson inverte o teste *score* (BCD 2001 §3.1.1); as regiões de
aceitação **diferem em até uma violação na fronteira** (ex.: τ = 0.02,
T = 500: Wilson aceita c ∈ [4, 16], LR_uc a 5 % aceita c ∈ [5, 16] —
cálculo próprio). O pré-registro nomeia a banda de Wilson como critério
**decisivo** de H1; a discordância com o LR_uc, quando ocorrer, é
**reportada, não arbitrada** —, e as zonas
verde/amarela/vermelha do Basel (1996, §III(c)) entram como leitura auxiliar
no perfil (o Basel é unilateral — só excesso de violações; H1 é **bilateral**:
intervalo largo demais também é miscalibração). Os níveis (95 % isolado;
97,5 % por cauda no gate), o T mínimo e o tratamento de h+7 são **conteúdo do
pré-registro** (6.5). **n da banda:** o número de pontos alinhados
**não-degenerados** do horizonte (as métricas de calibração excluem as linhas
degeneradas — §5.3, item 2), que o limiar de degeneração mantém próximo de T;
com S seeds, a média entre seeds desse número, nunca a soma. Alternativas reais
descartadas: (i) tolerância absoluta fixa δ — sem fonte que fixe δ e cega ao T
(o exemplo acima mostra que δ < 0.01 em τ = 0.02 é irrealizável); (ii) banda
"conformal-relativa" (comparar à cobertura do CQR) — o CQR é benchmark, não
régua (overview §11, `0_0_0008`).

### 4.5 Convenção de empate y = q̂

Irrelevante nos proper scores (o produto é zero; o IS da lib usa < e >).
Relevante nos indicadores: 1{y ≤ q̂} (Kuleshov Eq. (3); Bracher; GBR Thm 2 via
p_t ≤ p) vs 1{y < q̂} (Gneiting & Ranjan; `scoringrules.quantile_score`).
**Convenção (FA7):** 1{y ≤ q̂_τ} para a cobertura marginal e [l ≤ y ≤ u]
(intervalo fechado, Pearce Eq. (4)) para o PICP; para retornos contínuos o
empate tem medida zero, e a diferença só aparece em grade degenerada ou
previsões discretas. O oráculo R do backtest usa a desigualdade estrita
(`actual < VaR`, §7.7); as fixtures do golden-test devem evitar empates exatos.

### 4.6 Por que não CWC (nem qualquer combinação ad hoc largura × cobertura)

O *coverage-width criterion* de Khosravi et al. (2011a) `[CITAÇÃO-NÃO-ACESSADA]`
— NMPIW·(1 + 1{PICP < μ}·e^{−η(PICP − μ)}), forma inferida; Pearce Eq. (16)
reproduz a versão-loss — é uma **loss de treino heurística**, não um score
próprio. Gneiting & Raftery (2007, §9.3, p. 376) mostram, sob a loss
c·λ(I) − 1{θ ∈ I} de Casella, Hwang & Robert (1993) `[CITAÇÃO-NÃO-ACESSADA]`,
que "the classical t-interval is dominated by a misguided interval estimate
that shrinks to the sample mean in the cases of the highest uncertainty …
'there is a problem with the loss function.' We concur, and propose using
proper scoring rules to assess interval estimators … a meaningful comparison
of interval estimators requires either equal coverage or equal width". E §6.3
(Table 2): o intervalo K, o mais estreito com cobertura nominal correta, "seems
misguided, in that it collapses to a point forecast when the conditional
predictive variance is highest" — e perde no interval score. Askanazi et al.
(2018, §3.1–§3.2): o *Casella paradox* "emerges when loss functions place 'too
much' weight on length as opposed to coverage … those 'scoring rules' are not
'proper'". **Consequência:** PICP e MPIW entram como **perfil** (calibração
empírica + sharpness descritiva); o veredito fica com scores próprios (§3) e
com o gate de calibração (§8.5). CWC não existe no domínio.

## 5. Gate de degeneração (Stage 6.1)

### 5.1 Definição

Uma linha (modelo, horizonte, ponto t) é **degenerada** quando **todos** os
níveis da grade recebem o mesmo valor — a grade é uma medida de Dirac
(modeling §3.4): colapso **total**. **Degeneração parcial** — só alguns pares
colapsados (ex.: q_0.25 = q_0.75 com q_0.02 < q_0.98), possível em modelos
quantílicos (Zamo & Naveau 2018 §3.2.3: empates são comuns em regressão
quantílica; boosters por nível podem empatar após a ordenação) — é reportada
como **diagnóstico por par**, sem invalidar nada. Empates são **invariantes ao
rearranjo**: o gate dá o mesmo resultado no vetor bruto e no rearranjado; o
guardrail nem mascara nem cria degeneração (coerente com ADR 4.3.0002:
"q_low == q_high passes through unchanged"). A tolerância numérica de "igual"
é conteúdo do pré-registro (Wagenmakers et al. 2012, p. 635: o pré-registro
declara "which outlier criteria or data transformations will be applied").

### 5.2 O que a teoria diz — e o que não diz

**Diz:** (i) o Dirac é **bem-posto** em todo proper score — CRPS → |y − x|
(GR 2007 §4.2), IS → (2/α)|y − x| (Brehmer & Gneiting: a = b no domínio),
pinball → ρ_τ(y − x) (consistência vale para qualquer previsor, Gneiting 2011
Eq. (24)); "comparação direta entre determinístico e probabilístico". (ii)
Colapso **intencional** é penalizado pelos scores próprios, não por regra: GR
2007 §6.3, o intervalo que "collapses to a point forecast" perde no interval
score apesar de ter cobertura nominal. (iii) Nas **métricas de calibração** a
linha degenerada é **não-informativa por construção**: PICP = (1/T) Σ 1{y = x}
≈ 0 (medida zero), MPIW = 0, ĉ(τ) = (1/T) Σ 1{y ≤ x} idêntica para todo τ (a
curva de reliability é horizontal; não há PIT); nos backtests, hits ≈ 0 ⇒ π̂ =
0, LR_uc = −2·T·log(1 − p) (rejeição trivial), n_10 + n_11 = 0 ⇒ π̂_11
indefinido (§7.7 — o oráculo falha nesse caso). Reportar "cobertura 0 %" é
verdadeiro mas vazio.

**Não diz:** nenhuma fonte primária prescreve detectar e **invalidar/excluir**
previsões degeneradas na avaliação (na literatura de intervalos, largura zero
aparece só como consequência indesejada de losses ad hoc — Pearce §3). O gate
é, portanto, **política do projeto** `[SEM-FONTE-PRIMÁRIA]`; o que a teoria
faz é delimitar o que a política pode dizer sem contradizer os scores.

### 5.3 Convenção do projeto (B-GATE — decidida, §10.1; ADR 0.0.0011)

1. **Proper scores sempre computados em todas as linhas** — pinball por τ,
   P̄_G, CRPS_Q, IS_α — inclusive nas degeneradas (Dirac bem-posto; a
   penalização é o valor da informação distribucional que falta — modeling
   §3.4). Sem isso **H2 não existe**: não haveria pinball para os naive, e
   "superar os naive" (overview §4) ficaria vazio.
2. **Métricas de calibração e sharpness** (ĉ(τ), PICP, MPIW, hits de
   Christoffersen/Kupiec/VaR) computadas **só nas linhas não-degeneradas**, e
   marcadas **"não aplicável"** quando a taxa é 100 % — os baselines pontuais
   (`zero_return`, `historical_mean`) são degenerados por **especificação**
   (ADR 0.0.0052; modeling §3.2–§3.4), e a taxa esperada de 100 % é registrada
   a priori.
3. A **taxa de degeneração** por (modelo, horizonte) é **sempre** reportada
   (Simmons, Nelson & Simonsohn 2011, requisito 5: "If observations are
   eliminated, authors must also report what the statistical results are if
   those observations are included"; ICH E9 §5.2: "The frequency and type of
   protocol violations … should be documented").
4. Para os **modelos distribucionais** (candidato, GBM, AR(1), EWMA-vol, quantis
   rolantes), a degeneração é **defeito**: uma taxa acima de um **limiar
   pré-registrado** reprova o gate H1 desse (modelo, horizonte) → inelegível
   para H2 (§8.5). Abaixo do limiar, a linha degenerada conta como linha do
   modelo (item 1) e sai só das métricas de calibração (item 2).
5. **Não há exclusão de linhas** — nem *listwise* por `target_timestamp` nem
   *pairwise* — para a inferência pareada (§6). Excluir observações é grau de
   liberdade do pesquisador (Simmons et al. 2011, p. 1359: "Should some
   observations be excluded?" está na lista de exemplos; os autores notam na
   p. 1361 que a exclusão de subconjuntos **não** entrou na simulação da
   Table 1 — que chega a 61 % com quatro outros graus — e por isso a
   estimativa é "conservadora") e **quebraria a contiguidade** que o
   estimador HAC e o bootstrap em bloco pressupõem (série consecutiva e
   equiespaçada — §6.7).

**Consequência de redação.** O DoD da Stage 6.1 ("invalida métricas da linha
e reporta rate") e o modeling §7 item 4 leem-se "invalida as métricas de
**calibração** da linha e reporta a taxa" — o DoD da 6.1 no roadmap foi
ajustado na PR da #78; o texto do modeling §7 item 4 é ajustado na próxima
revisão daquele doc e, até lá, lê-se assim. Isto resolve a tensão T1 do inventário: o modeling §3.4 (Dirac bem-posto,
penalização informativa) e o DoD 6.1 (invalidar) só eram contraditórios sob a
leitura "invalidar **tudo**".

**Limitação declarada.** Para um modelo distribucional com taxa baixa mas
não-nula, retirar as linhas degeneradas do hit sequence (item 2) abre lacunas
nas **transições** de que o LR_ind depende (§7.2); o limiar do item 4 mantém a
taxa pequena, e o pré-registro deve declarar que, nesse caso, LR_ind/LR_cc são
computados sobre a sequência com lacunas, com a versão "com/sem" as lacunas
reportada lado a lado **no perfil** (ICH E9 §5.3) — LR_ind/LR_cc nunca entram
no gate H1 (§8.5), logo a escolha não troca o veredito.

**Alternativas reais descartadas.** (ii) Invalidar **todas** as métricas da
linha (leitura literal do DoD) — equivale a excluir os naive de H2; a teoria
não sustenta. (iii) Exclusão **pareada** por `target_timestamp` quando um
modelo distribucional colapsa — preserva o pareamento mas reduz T, quebra a
contiguidade e introduz seleção condicionada ao comportamento de um modelo
(viés); a literatura só diz "mesma amostra" (DM 1995 §1), a regra de quando
excluir seria política sem fonte. Registrada no
[ADR 0.0.0011](../../adr/0_0_0011-preregistration-invariants-and-h1-gate.md).

### 5.4 Relação com o guardrail e com os baselines pontuais

Guardrail ≠ gate (overview §7; ADR 4.3.0002; modeling §3.4/§7.4): o guardrail
**conserta ordem** (rearranjo, com a garantia de CFG Prop. 4) e é aplicado
antes da persistência; o gate **detecta ausência de informação distribucional**
e vive na avaliação. Um vetor pode passar no guardrail (ordenação fraca aceita
empates) e ser degenerado; nunca o inverso. Os baselines pontuais são o caso
em que a degeneração é **propriedade declarada** — a régua de locação de H2
(GKX 2020 p. 2246, via modeling §3.1) — e não entram na caracterização H1 nem
no gate de calibração (§8.5): H1 é julgada só para modelos que **deveriam**
emitir distribuição.

## 6. Inferência pareada (Stage 6.2)

### 6.1 Diebold–Mariano (1995)

**O que é.** Teste da nula de **igual acurácia esperada** entre duas séries de
previsões da mesma variável, sob perda arbitrária, com erros possivelmente
não-gaussianos, viesados, serial e contemporaneamente correlacionados. É um
z-teste da média de uma série observada (o diferencial de perda) com variância
de longo prazo estimada de forma robusta.

**Como se calcula** (Diebold & Mariano 1995, §1.1, p. 254). Com d_t = L_{1,t}
− L_{2,t}, d̄ a média e γ̂_d(k) = (1/T) Σ_{t=k+1}^{T} (d_t − d̄)(d_{t−k} − d̄):

    H0: E[d_t] = 0
    S1 = d̄ / sqrt( 2π·f̂_d(0) / T )   ~a  N(0,1) sob H0
    2π·f̂_d(0) = Σ_k 1(k/S(T)) · γ̂_d(k)        (lag window 1(·), truncation lag S(T))
    janela retangular com S(T) = h−1:   2π·f̂_d(0) = γ̂_d(0) + 2·Σ_{k=1}^{h−1} γ̂_d(k)

"the 'equal accuracy' null hypothesis is equivalent to the null hypothesis that
the population mean of the loss-differential series is 0" (§1, p. 254). A
escolha do truncamento: "optimal k-step-ahead forecast errors are at most
(k−1)-dependent … This suggests the attractiveness of the uniform, or
rectangular, lag window … S(T) = (k−1). This is legitimate (i.e., the estimator
is consistent) under (k−1)-dependence so long as a uniform window is used"
(p. 254). Sobre variância negativa: a janela retangular "is not guaranteed to
be positive semidefinite … in the rare event that a negative estimate arises,
we treat it as 0 and automatically reject the null … If it is viewed as
particularly important to impose nonnegativity … it may be enforced by using a
Bartlett lag window … as in the work of Newey and West (1987)" (p. 254).
Monte Carlo (§3, p. 257): "S1 is robust to contemporaneous and serial
correlation in large samples, but it is oversized in small samples" — a
motivação da correção HLN (§6.3).

**Direção e sinal.** DM 1995 apresenta S1 como N(0,1) sem fixar a direção. Com
d_t = L_{cand,t} − L_{comp,t}, a alternativa **unilateral** "candidato melhor"
é H1: E[d_t] < 0, rejeitando para S1 na cauda **esquerda**; p-valor unilateral
= Φ(S1) (ou a t_{T−1} após HLN). É a semântica `alternative = "less"` do
oráculo R (§11.3).

**Como se aplica aqui.** Loss = L_t (pinball média na grade por ponto, §2.4);
por horizonte; por comparador; série alinhada por `target_timestamp`, 1
obs/ponto. lag = h−1 (roadmap 6.2) coincide com S(T) = k−1 de DM 1995: para
h = 1 a variância é γ̂_d(0)/T (sem HAC); para h = 7, seis autocovariâncias.
Nota sobre o alvo: o alvo em h é o retorno de **um** dia em t+h (modeling
§2.1), não o acumulado — a (h−1)-dependência vale do mesmo jeito (o erro ótimo
de prever y_{t+h} com informação até t é MA(h−1) pela representação de Wold);
mas o **nível** da pinball é heteroscedástico (clusters de volatilidade) e o
diferencial pode reter correlação além de h−1 por suboptimalidade dos modelos
— exatamente o "may be violated for a variety of reasons … readily assessed
empirically" de DM 1995, que sustenta o diagnóstico do §6.2.

**Convenção do projeto (FB2, pré-registrável).** **Kernel retangular com lag
h−1** (DM 1995; R `dm.test` com `varestimator = "acf"`) + correção HLN (§6.3)
+ t_{T−1}; se a variância estimada for ≤ 0 (possível só para h > 1), o
**fallback é declarado e registrado**: o oráculo R recalcula com h = 1 e emite
aviso (com h = 1 a variância nula é erro, não fallback); DM 1995 trataria como
0 e rejeitaria. O projeto **segue o oráculo** (h = 1) e registra a ocorrência —
regra `[SEM-FONTE-PRIMÁRIA]` (convenção de software contra a prescrição do
paper), pré-registrada (**B-DM — decidida, §10.1**: degrau 2, o oráculo fixa a
convenção e mantém a equivalência testável).
**Bartlett** (Newey & West 1987 `[CITAÇÃO-NÃO-ACESSADA]`; pesos 1 − k/h para
k = 0..h−1, inferidos das implementações verificadas em R e statsmodels) fica
como **sensibilidade**: é sempre ≥ 0, mas sob MA(h−1) exata com
autocovariâncias positivas subestima a LRV (pesos < 1) e tende a sobre-rejeitar
(derivação); e a combinação Bartlett + fator HLN é convenção de software, não
derivação de HLN. Razão da escolha: o oráculo R reproduz **exatamente** o
retangular, e HLN derivaram o fator para esse estimador. Fork descartado:
bandwidth automático (Newey & West 1994 `[CITAÇÃO-NÃO-ACESSADA]`, regra
floor(4(T/100)^{2/9}); Andrews 1991 `[CITAÇÃO-NÃO-ACESSADA]`) — desvincula o
bandwidth da estrutura MA(h−1) pré-registrada e não é reproduzível por
`dm.test`.

### 6.2 Diebold (2015): Assumption DM e o diagnóstico

Diebold (2015, JBES 33(1)): **Assumption DM** (§2.1, Eq. (1), p. 2) — o
diferencial é covariância-estacionário (média constante, autocovariâncias
constantes, variância finita positiva); "DM requires only that the loss
differential be covariance stationary … If Assumption DM holds, then the N(0,1)
limiting distribution of test statistic DM must hold." Implementação por
regressão (§2.1): "regression of the loss differential on an intercept, using
… HAC standard errors". **Diagnóstico** (§2.2, "Fourth"): "One can plot the
loss differential series, examine its sample autocorrelations and spectrum,
test it for unit roots and other nonstationarities including trend, structural
breaks or evolution". Modelos estimados (§3.1–§3.2): a convergência de
parâmetros introduz não-estacionariedade no diferencial, mas se "parameter
estimation uncertainty might be small … the loss differential would be
approximately stationary and the DM N(0,1) null distribution would be
approximately valid"; modelos aninhados (§3.4): Clark & McCracken (2011)
`[CITAÇÃO-NÃO-ACESSADA]` — valores críticos normais "often approximate the
exact null distribution very well" sob hipótese local-a-zero. Conclusão (§7,
p. 8): "traditional DM tests, with traditional DM N(0,1) critical values, are
likely fine (subject to Assumption DM, of course, but … Assumption DM is
empirically verifiable and typically reasonable)".

**Como se aplica aqui.** Os baselines pontuais são casos particulares de
modelos maiores (zero_return e historical_mean estão "dentro" do AR(1)); a
objeção do *nesting* é coberta por Diebold 2015 §3.4/§3.5 e Giacomini & White
(2006). O **diagnóstico empírico do ACF e da estacionariedade de d_t** faz
parte do protocolo (pré-registrado; §6.8) — não muda a fórmula, diagnostica sua
premissa.

### 6.3 Harvey, Leybourne & Newbold (1997)

**O que é.** Modificação do DM para amostras moderadas e h > 1: um fator de
escala que corrige o viés do estimador de variância de d̄, e valores críticos da
t de Student com T−1 graus de liberdade.

**Como se calcula** (HLN 1997, IJF 13(2)). Premissa (pp. 281–282): "for
optimal h-steps ahead forecasts, the sequence of forecast errors follows a
moving average process of order (h−1) … it will be assumed … that all
autocorrelations of order h or higher of the sequence d_t are zero". Eq. (8)
(§2, p. 283): E[V̂(d̄)] ≈ [(T + 1 − 2h + T⁻¹h(h−1))/T]·V(d̄), "exact in the special
case where d_t is white noise". Eq. (9):

    S1* = [ (T + 1 − 2h + h(h−1)/T) / T ]^{1/2} · S1

comparada "with critical values from the Student's t distribution with (n−1)
degrees of freedom, rather than from the standard normal distribution"
(pp. 283–284). As duas modificações contribuem, "the former somewhat more than
the latter" (p. 284). Table 1 (p. 285; nível nominal 10 %, bilateral), teste
modificado + t: h = 7, T = 256 → 11,6 %; T = 512 → 11,4 %; h = 1, T = 256 →
10,4 %. Caudas pesadas (t_6), MA(1) e correlação contemporânea (p. 286):
"virtually identical" / "closer to the nominal sizes". §5 (pp. 290–291): "Our
recommendation is the use of the modified Diebold-Mariano test … The original
test can be quite seriously over-sized in small and moderate samples — a
problem that becomes particularly acute for longer forecast horizons. Our
modification goes a long way towards rectifying this problem, but does not
cure it entirely."

**Como se aplica aqui.** Fator para h = 7: T = 250 → 0,974; T = 500 → 0,987;
T = 1000 → 0,9935; para h = 1, √((T−1)/T). Pequeno mas não nulo; o uso da
t_{T−1} é o que mais importa em T de centenas. Com T de algumas centenas em
h+7 o teste modificado ainda rejeita ~11,5 % ao nível 10 % — argumento para
**reportar o tamanho esperado junto ao resultado** e não empurrar o nível
nominal para cima; para h+30 o excesso cresce com h (Table 1, h = 10 é a pior
linha) — reforça o status suplementar desse horizonte. O oráculo R aplica
exatamente Eq. (9) + t_{T−1}; a implementação própria deve bater com ele
dentro de tolerância declarada (ADR 0.0.0021). Não há fork: a fórmula é única;
HLN a derivaram para o estimador **retangular** (Eq. (5)).

### 6.4 Holm (1979) e a definição da família

**O que é.** Procedimento *step-down* ("sequentially rejective Bonferroni")
que controla a **FWER no sentido forte** — para qualquer combinação de nulas
verdadeiras — e domina Bonferroni em poder.

**Como se calcula** (Holm 1979, Scand. J. Statist. 6(2)). Definição (p. 65):
nível múltiplo α "for free combinations" se, para qualquer subconjunto I de
nulas verdadeiras, P(∪_{i∈I} C_i) ≤ α. Scheme 1 (§2, pp. 66–67): com
p_(1) ≤ … ≤ p_(m) e as hipóteses correspondentes,

    passo k: se p_(k) ≤ α/(m − k + 1)  rejeita H_(k) e segue; senão aceita H_(k), …, H_(m) e PARA

— "compared to α/n, α/(n−1), …, α whereas in the classical Bonferroni test
they are compared to α/n". Theorem 1 (p. 67): o procedimento "has the multiple
level of significance α for free combinations" (desigualdade de Boole); na
introdução (p. 66): "can be applied to any parametric or non-parametric
model" e "can easily be used to make one-sided rejections". P-valores ajustados (não estão em Holm;
convenção de software): p̃_(k) = max_{j≤k} min(1, (m − j + 1)·p_(j)).

**Sobre a família — o que a literatura diz.** Holm e Romano & Wolf (2005)
pressupõem a família **dada** antes do teste; não há teorema que a escolha — é
decisão de desenho (pré-registro). Romano & Wolf (§2 do WP; enunciam Holm com
"<" estrito — o projeto segue o "≤" de Holm, que é o do `statsmodels`): "the
Holm method can be
quite conservative … they achieve control of the FWE by assuming a worst-case
dependence structure" — o StepM deles usa a distribuição conjunta e é mais
poderoso (alternativa **não** adotada pelo roadmap). White (2000, §2, p. 1101):
a nula após uma busca é H0: max_k E[f*_k] ≤ 0 — o que infla os falsos positivos
é o **número de comparações efetivamente consideradas** para a claim, não só as
reportadas. O desenho do projeto elimina a busca (modeling §6.1); a família
congelada é o que torna Holm válido. Regra operacional (derivação): a família é
o conjunto de hipóteses cujas rejeições sustentam **uma mesma claim**;
comparações que não podem trocar o veredito (perfil) ficam fora.

**Convenção do projeto (B-FAMILIA — decidida, §10.1; ADR 0.0.0010).** A **loss pareada
confirmatória é a pinball média na grade** (L_t), por horizonte; **um DM por
(candidato, comparador, horizonte)**; a **família de Holm = os B comparadores
dentro de um horizonte** (m = B = 6: cinco baselines + GBM), com FWER = α por
horizonte — coerente com "nunca agregar entre horizontes" (§2.7) e com H2
enunciada por horizonte. **DM por nível τ é perfil descritivo, sem inferência
corrigida** — mostra onde (cauda vs centro) o skill vive, mas não alimenta o
veredito (overview §4: perfil nunca troca o veredito). Alternativas reais
descartadas: (b) família global m = H × B (12–18) — controla a FWER da claim
"supera em algum horizonte", mais conservadora, e mistura horizontes na
correção embora não nas métricas; (c) família por nível τ (m = K × B = 42–54
por horizonte) — Holm fica muito conservador sob a forte dependência entre
níveis do mesmo par (Romano & Wolf §3), e nos τ extremos o diferencial contra
um baseline pontual é dominado pela penalização estrutural do Dirac (rejeições
"fáceis" nas caudas e possivelmente o oposto no centro), o que a média na grade
embute; (d) sub-famílias por camada (naive m = 2; fortes m = 4) — ganha poder
mas exige declarar duas claims independentes. Registrada no
[ADR 0.0.0010](../../adr/0_0_0010-paired-inference-dm-holm-mcs.md). O CQR
(Step 7) **não** está na família: é benchmark de calibração, não de skill.

**A família não depende de H1 dos comparadores.** Um comparador
distribucional que reprova o seu próprio H1 (ex.: EWMA-vol sub-cobrindo nas
caudas, como o ADR 0.0.0052 antecipa) **continua** na família de Holm e em
M0 do MCS. O gate H1 decide **só a elegibilidade do candidato** (§8.5): se
também filtrasse comparadores, m e M0 passariam a depender de um resultado
observado nos mesmos dados — exatamente o "número de comparações
efetivamente consideradas" que White (2000, §2) mostra inflar o erro, e uma
família que não é mais a congelada no pré-registro. A calibração dos
comparadores entra no perfil de H1. É também a leitura que o overview já
impõe: os baselines pontuais não têm calibração nenhuma (grade degenerada
por especificação, §5.3) e ainda assim são comparadores de H2 (overview §4);
"não se compara skill de modelo mal-calibrado" refere-se ao **candidato**,
cujo skill é o objeto de H2.

### 6.5 Model Confidence Set — Hansen, Lunde & Nason (2011)

**O que é.** Conjunto aleatório M̂*_{1−α}, construído por eliminação
sequencial, que contém o(s) melhor(es) modelo(s) com probabilidade
assintótica ≥ 1−α — análogo de um intervalo de confiança para "o melhor
modelo". Não exige benchmark; dados pouco informativos produzem MCS grande.

**Definições e algoritmo** (HLN 2011, Econometrica 79(2)). Perdas L_{i,t},
i ∈ M0; **variáveis de desempenho relativo** d_{ij,t} = L_{i,t} − L_{j,t},
μ_ij = E(d_{ij,t}) (p. 458). Definition 1: M* = {i ∈ M0 : μ_ij ≤ 0 para todo
j}. Eq. (1): H_{0,M}: μ_ij = 0 para todo i, j ∈ M. Definition 2 (p. 459): "Step
0. Initially set M = M0. Step 1. Test H_{0,M} using δ_M at level α. Step 2. If
H_{0,M} is accepted, define M̂*_{1−α} = M; otherwise, use e_M to eliminate an
object from M and repeat the procedure from Step 1." Theorem 1 (p. 459):
lim inf P(M* ⊂ M̂*_{1−α}) ≥ 1−α e lim P(i ∈ M̂*_{1−α}) = 0 para i ∉ M*.
Estatísticas (§3.1.2, p. 465):

    d̄_ij = (1/T) Σ_t d_{ij,t};   t_ij = d̄_ij / sqrt(var̂(d̄_ij))
    d̄_i· = (1/m) Σ_{j∈M} d̄_ij;    t_i· = d̄_i· / sqrt(var̂(d̄_i·))
    T_R,M = max_{i,j∈M} |t_ij|;    T_max,M = max_{i∈M} t_i·

"The first statistic, t_ij, is used in the well known test for comparing two
forecasts; see Diebold and Mariano (1995)". Regras de eliminação (p. 466):
e_R,M = arg max_i sup_j t_ij; e_max,M = arg max_i t_i· — Proposition 1 prova a
coerência de ambas. **P-valor MCS** (Definition 4, p. 462): p̂_{e_{Mj}} =
max_{i≤j} P_{H0,Mi} (máximo cumulativo na ordem de eliminação; P_{H0,Mm0} ≡
1); Theorem 3: i ∈ M̂*_{1−α} ⟺ p̂_i ≥ α; "The MCS p-value also cannot be
interpreted as the probability that a particular model is the best model"
(p. 463). Assumption 2 (p. 464): momentos r+δ finitos, estacionariedade
estrita e α-mixing de {d_{ij,t}} — "restrictions on the relative performance
variables … not directly on the loss variables". As distribuições são
não-padrão ⇒ **bootstrap em bloco** (§5.1, p. 477: l = 2, B = 1.000, n = 250
nas simulações; fn. 14, p. 484: l = 12 na aplicação, "qualitatively similar"
com l = 6 e 9 — a prática de reportar sensibilidade ao bloco). Relação com o
Reality Check (§4.1, p. 474): com benchmark natural, "observing whether the
designated benchmark is in the MCS … corresponds to a rejection of the null
hypothesis that is relevant for a SPA test". **Leitura do overview** ("não
rejeitado como inferior") = pertencer a M̂*_{1−α}: não eliminado por nenhum
teste de equivalência ao nível α.

**Bootstrap em bloco.** Politis & Romano (1994) `[CITAÇÃO-NÃO-ACESSADA]`
(*stationary bootstrap*: blocos de comprimento geométrico com média b);
semântica confirmada em Politis & White (2004, §2, pp. 55–56) — "(B) The
distribution F_b is a Geometric distribution with mean equal to the real
number b; this is the stationary bootstrap (SB)"; §3.2 Eq. (6): b_opt,SB =
(2G²/D_SB)^{1/3}·N^{1/3} (taxa N^{1/3}, G estimado por janela *flat-top* sobre
as autocovariâncias); correção em Patton, Politis & White (2009)
`[CITAÇÃO-NÃO-ACESSADA]`. Precedente: White (2000, §2.c, p. 1104) usa o
stationary bootstrap para o Reality Check.

**Como se aplica aqui.** Por horizonte, M0 = {candidato, GBM, AR(1), EWMA-vol,
quantis rolantes, zero_return, historical_mean} (7), matriz T × 7 de L_t
(§2.4). Assumption 2 recai sobre d_{ij,t}: a heterocedasticidade comum a todos
(clusters de vol) pode "sumir" no diferencial (mesmo argumento de Diebold 2015
§2.2). As séries dos dois baselines pontuais são correlacionadas mas não
idênticas. Perdas **idênticas** (ou com diferencial de variância nula) são
**pré-condição de domínio** a validar antes de chamar o backend — var(L_i −
L_j) > 0 para todo par —, porque com `method='R'` o backend **não avisa**:
produz NaN/erro silencioso (§11.3); o aviso de desvio-padrão zero existe só em
`method='max'`. A duplicidade de spec é o que ADR 0.0.0052 evitou ao colapsar
zero_return ≡ RW.

**Convenção do projeto (T6/FB4/FB8/FB9).** Estatística **'R' (t_ij)** —
coerente com a família de pares do DM (HLN 2011 p. 465); **α_MCS = 0,10**
(HLN 2011 reportam M̂*_{90%}); **reps ≥ 1.000**; **stationary bootstrap**
(Politis & Romano 1994; default do backend; precedente White 2000 §2.c no
Reality Check — HLN 2011 usam o *moving-block bootstrap*, §5.1 p. 477 e §6.1
p. 484, logo a variante é escolha do projeto `[SEM-FONTE-PRIMÁRIA]`, com o
*moving-block* de bloco igual como sensibilidade) com **bloco = comprimento
automático de Politis–White 2004** — b_opt é definido para a média de **uma**
série; com C(k, 2) diferenciais, a regra operacional é **o maior b̂_sb entre
todos os d_{ij,t} do horizonte, com piso h** (l = max(h, max b̂_sb): a
dependência MA(h−1) do diferencial é estrutural, e o roadmap já fixa a grade
de sensibilidade de bloco em "≥ h"; o mais persistente; `[SEM-FONTE-PRIMÁRIA]`
para a agregação — **B-MCS, decidida, §10.1**) e **sensibilidade a l = h e
l = √T reportada**; tudo pré-registrado (6.5), inclusive a semente do
bootstrap. O "bug de eliminação"
do projeto antigo (overview §2) não está descrito neste repo — o doc dá a
**regra correta** (Definition 2 + Definition 4/Theorem 3) e nada mais. Forks
descartados: √T como regra de bloco `[SEM-FONTE-PRIMÁRIA]` (default de
software; as docs dizem que o bloco "should be provided and chosen to be
appropriate for the data"); l = h fixo (ignora persistência além de h−1
induzida por heterocedasticidade residual); 'max' (compara cada modelo com a
média do conjunto — sem recomendação primária de um sobre o outro; 'R' foi
preferido pela coerência com t_ij).

### 6.6 Comparabilidade via scores próprios: Dirac × probabilístico

A ordenação por **perda média** tem sentido para qualquer emissor de q̂_τ: o
quantil condicional verdadeiro minimiza E[ρ_τ] (Gneiting 2011 Eq. (24) + Thm
9), logo E[L_1] < E[L_2] significa que o modelo 1 está, em esperança de score,
mais perto do quantil verdadeiro — **inclusive** o que emite o mesmo número
para todo τ (Dirac; modeling §3.4). A soma na grade é separável em scoring
functions cada uma consistente para o seu quantil, e é minimizada em
esperança pelo vetor de quantis verdadeiros (Gneiting 2011 Def. 2.1
coordenada a coordenada; Thm 2.3 para misturas — derivação). A versão
distribucional é GR 2007 §4.2 ("direct way to compare deterministic and
probabilistic forecasts"). Sem forks.

### 6.7 Pareamento estrito

O diferencial d_t só existe onde **ambas** as perdas existem para o mesmo t
(DM 1995 §1, p. 253: "two forecasts … of the time series {y_t}"; HLN 1997
p. 281: "a pair of h-steps ahead forecasts have produced errors (e_1t, e_2t);
t = 1, …, n"; HLN 2011 p. 458: L_{i,t}, t = 1..n para todo i — o backend exige
matriz T × k completa). O estimador HAC pressupõe "a single time series with
zero axis consecutive, equal spaced time periods" (statsmodels, §11.3); o
bootstrap em bloco trabalha com X_1..X_N consecutivos (Politis & White 2004).

**Convenção (1.21b).** Pareamento por **interseção exata** de
`target_timestamp` entre **todos** os modelos da família do horizonte (a
mesma amostra para todo DM e para o MCS — T comum); o déficit de janela do
candidato (ADR 5.4.0001) reduz a amostra comum, e **T é reportado** por
horizonte. A interseção é **estrutural** (disponibilidade das previsões), nunca
condicionada a valores, e tem de resultar num **bloco contíguo** — na prática,
truncamento de prefixo pelo déficit de janela; uma lacuna **interior** (fold
que falhou, sessão ausente em um modelo) violaria a contiguidade que HAC e
bootstrap em bloco pressupõem e é **violação de invariante da 6.4**, não caso
de pareamento (coerente com §5.3 item 5). O dedup operationally-latest (5.1)
precede o pareamento: 1 obs por
ponto é pré-condição do d_t (modeling §7 item 2). A validação de igualdade de
grade entre os modelos pareados é papel do Step 6 (concept 5.2 I11).

### 6.8 Folds concatenados e o esquema expansivo

**Geometria.** Os blocos de test dos folds são contíguos, disjuntos e
ladrilham a cauda da série (concept 5.1, I7); o treino é expansivo (ADR
5.1.0001). Concatenar as perdas OOS de todos os folds, por horizonte, produz
**uma série contígua** de T = n_folds × test_size pontos, vinda de modelos
re-estimados a cada origem.

**O que a literatura diz.** (a) Concatenar e rodar um DM/MCS é o desenho
*recursive/expanding scheme* da avaliação OOS; Diebold (2015, §3.1–§3.2):
validade aproximada sob Assumption DM com incerteza de estimação pequena,
**verificável**. Mas HLN 2011 (p. 484): "our MCS bootstrap implementation …
relies on an assumption that d_{ij,t} is stationary. This is not plausible
when the parameters are estimated with a recursive estimation scheme … We
avoid this problem by following Giacomini and White (2006) and present
empirical results that are based on parameters estimated over a rolling
window with a fixed number of observations"; e Giacomini & White (2006, §3.2,
comentário 2 do WP): "the requirement of finite estimation window rules out the use
of a recursive forecasting scheme, which utilizes an expanding estimation
window". Mas os próprios HLN relatam (nota 11 do working paper CREATES
RP 2010-76, a versão lida; a numeração na Econometrica não foi conferida)
que, "although our assumption do not justify the recursive estimation scheme, it produces
pseudo-MCS results that are very similar to those obtained under the rolling
window estimation scheme" — evidência empírica, não teorema, de que o esquema
expansivo não distorce o MCS de forma material. (b) Testar por fold e agregar: T_fold é pequeno (HLN 1997 Table 1: n
entre 16 e 64 com h = 7 → tamanho 16,8–19,5 %) e agregar p-valores entre folds
exigiria
independência que não existe (treino compartilhado; blocos adjacentes) — sem
fonte para um agregador nesse contexto `[SEM-FONTE-PRIMÁRIA]`. Sobre **poder**
para pinball em h+7 com T de centenas não há tabela primária (HLN 1997 Table 3
é só h = 1) `[SEM-FONTE-PRIMÁRIA]` — o pré-registro reporta **efeito + IC**,
não só p; Diebold 2015 §7 lembra que comparações pseudo-OOS "are typically
costly in terms of power loss" — preço aceito pela validade temporal (ADR
0.0.0018).

**Convenção do projeto (B-FOLDS — decidida, §10.1).** **Concatenar os folds em
uma série contígua por horizonte** para DM e MCS (esquema expansivo já
decidido — ADR 5.1.0001), com (i) **diagnóstico de estacionariedade de d_t
pré-registrado** (Diebold 2015 §2.2: ACF, gráfico, quebras) e (ii) **DM por
fold reportado como perfil descritivo** de estabilidade temporal (Diebold
2015: pseudo-OOS informa "comparative predictive performance during
particular historical episodes"). A **janela rolante** (GW 2006 / HLN 2011) é
**registrada como limitação conhecida**, não como mudança de cohort.
Alternativa real descartada: rodar um cohort rolante só para a inferência
(ou superseder o ADR 5.1.0001) — custo alto, reversibilidade cara, e a
tensão com HLN 2011 p. 484 fica declarada em vez de escondida.

### 6.9 Seeds: qual série do candidato entra no teste

O cohort tem S seeds × folds (modeling §6.2); DM/MCS exigem **uma** série por
modelo. Opções: (a) média das **perdas** entre seeds por ponto — E_seed[L_t], a
perda esperada do "método com seed aleatória", separável, permanece uma perda
válida ponto a ponto; (b) média das **previsões** (ensemble) e depois pinball
— muda o objeto (ensemble ≠ modelo único) e tende a reduzir a perda; (c) um
teste por seed e distribuição das estatísticas (Bouthillier et al. 2021:
"comparar distribuições, não runs pontuais") — sem regra de decisão única para
um scorecard mecânico; (d) seed fixa/mediana. Sem fonte primária que prescreva
uma opção para testes DM `[SEM-FONTE-PRIMÁRIA]`.

**Convenção do projeto (B-SEEDS — decidida, §10.1; ADR 0.0.0010).** A série
do candidato com S seeds é a **média ponto a ponto das perdas entre seeds**
(opção a); a **dispersão entre seeds** entra no perfil — o DM por seed e a
**fração de seeds que rejeita** (respeita "comparar distribuições" sem quebrar
o veredito mecânico). A opção (a) é **conservadora** frente ao ensemble (b):
a pinball é convexa em q̂, logo, pela desigualdade de Jensen,
ρ_τ(y − mean_s q̂_s) ≤ mean_s ρ_τ(y − q̂_s) ponto a ponto — a perda média entre
seeds nunca é menor que a do ensemble, e o claim fica sobre o modelo único
que o projeto estuda (derivação elementar).

Consequências para as métricas que não são perdas:

- **Cobertura e degeneração** do candidato são a **média entre seeds** de
  ĉ_s(τ) e da taxa de degeneração por seed; a banda de Wilson usa como n os
  pontos alinhados não-degenerados (≈ T), **nunca S·T** (§4.4) — as S
  previsões do mesmo ponto não são observações independentes do realizado.
- **Gate H1 e suas sensibilidades** (§8.5: bandas por cauda, LR_uc de 3
  estados, partição de DGT em h+7) usam **só contagens** por cauda, sem
  transições; entram com as contagens médias entre seeds e o mesmo n — uma
  única regra para o candidato, sem escolher seed.
- **Backtests com transições** (LR_ind, LR_cc — §7) exigem uma sequência
  binária; são computados **por seed** e ficam no **perfil** (distribuição
  das estatísticas entre seeds).

**GBM: seeds não criam variância.** O treino do GBM do projeto é
determinístico: `deterministic=True`, `feature_fraction = 1.0`,
`bagging_fraction = 1.0`, `bagging_freq = 0` (adapter LightGBM da Stage 5.3,
conferido no código em 2026-09-26) — não há subamostragem de linhas nem de
colunas em que o `seed` atue, e S seeds dariam S cópias idênticas. O GBM
entra, portanto, com **uma** execução por fold; a média entre seeds é a
identidade. Isso é fato de **código lido, não executado**: a Stage 5.5 o
transforma em prova com um teste de contrato "duas seeds → predições
idênticas" (DoD da 5.5 no roadmap). Se um dia o GBM ganhar subamostragem, a
regra (a) passa a valer para ele sem mudança.

**Número de seeds do candidato** — decisão **P** (custo de GPU), tomada ao
congelar o cohort (5.5), não aqui. Insumo para ela: o poder do DM vem de T;
S reduz só a parcela da variância de d̄ que vem da seed, e o ganho de S = 10
sobre S = 5 depende da razão r entre a variância entre seeds e a variância
dos dados, mensurável no split exploratório. Baselines determinísticos não
têm o problema. Alternativas descartadas: ensemble de previsões (muda o
objeto testado — o claim seria sobre um ensemble que o projeto não estuda —
e é otimista pelo Jensen acima); seed fixa (cherry-picking se escolhida por
OOS; se pré-fixada, joga fora a variância que Bouthillier mostram ser da
mesma ordem da inicialização).

### 6.10 "Superar" (DM) vs "empatar" (MCS); não-rejeição ≠ equivalência

O DM unilateral testa **"superar"**: H1: E[d_t] < 0 com d_t = L_cand − L_comp.
Um teste unilateral só produz "rejeita" / "não rejeita"; **não-rejeição não é
equivalência demonstrada** — provar "empate" exigiria um teste de equivalência
com margem pré-registrada (TOST), **não adotado**. **Convenção (T7):** "empatar
com os fortes" (overview §4) significa **pertencer ao MCS** — não ser
eliminado como inferior ao nível α_MCS — e o doc declara que a leitura "não
rejeitado" é a forma honesta de "empate"; "não-dominância é resultado válido"
(overview §1/§4) é a consequência. O que sustenta a comparação de um pontual
com um probabilístico está em §6.6.

## 7. Backtests de cobertura condicional e VaR descritivo (Stage 6.3)

### 7.1 Hit sequence e o critério de cobertura condicional (Christoffersen 1998)

Dado um intervalo ex ante [L_{t|t−1}(p), U_{t|t−1}(p)] com cobertura nominal
p, o **hit** é I_t = 1 se y_t ∈ [L, U], 0 caso contrário (Christoffersen 1998,
Definition 1, p. 843 — I_t = 1 é **acerto**, não violação). Definition 2
(p. 843): a sequência é *efficient* em relação a Ψ_{t−1} se E[I_t | Ψ_{t−1}] =
p para todo t; a cobertura incondicional é o caso Ψ = ∅. Lemma 1 (p. 844):
testar E[I_t | I_{t−1}, …, I_1] = p equivale a testar que {I_t} é i.i.d.
Bernoulli(p); Definition 3: *correct conditional coverage* ⟺ {I_t} ~ iid
Bern(p). "my testing criterion and the tests of this criterion are model
free" (p. 842). Unilateral = bilateral (pp. 843–844): "the analysis of
one-sided intervals corresponds exactly to that of two-sided intervals" — base
para aplicar o mesmo arcabouço a hits de quantil individual (§7.5). Diebold,
Gunther & Tay (1998, pp. 868–869) ligam PIT e hits: "If a sequence of density
forecasts is correctly conditionally calibrated, then every interval will be
correctly conditionally calibrated and will generate an i.i.d. Bernoulli hit
sequence". Re-rotular 0↔1 (hits vs violações) mapeia p ↔ 1−p, n_0 ↔ n_1, n_00
↔ n_11, n_01 ↔ n_10 e deixa as verossimilhanças invariantes — os três LR são
**idênticos** contando "dentro" (Christoffersen) ou "violação" (Kupiec /
oráculo R); só o p nominal muda (derivação trivial).

### 7.2 Os três testes LR (Christoffersen 1998, §3, pp. 844–847)

**Contagens — convenção "pura" (§7.7): tudo condicionado na primeira
observação**, isto é, **todas** as contagens sobre t = 2..T ("as is standard, I
condition on the first observation everywhere", p. 845, fn. 8; o mesmo em
Christoffersen & Pelletier 2004 §4.1 p. 7 e Christoffersen & Diebold 2000
fn. 13): n_ij = nº de transições (I_{t−1} = i, I_t = j), t = 2..T;
**n_1 := n_01 + n_11, n_0 := n_00 + n_10** (n_0 + n_1 = T − 1);
π̂ = n_1/(T − 1); π̂_01 = n_01/(n_00 + n_01); π̂_11 = n_11/(n_10 + n_11);
π̂_2 = (n_01 + n_11)/(n_00 + n_01 + n_10 + n_11) = π̂. A versão **impressa**
do LR_uc em Christoffersen §3.1 (e o oráculo R, §7.7) usa n_1 = Σ_{t=1}^{T} I_t
sobre as T observações — é essa a diferença entre as duas convenções, e é o
que torna a identidade (c) exata **só** na convenção pura (p. 847: "if I
condition on the first observation in the test for unconditional coverage
the result is that π̂ = π̂_2 = Π̂_2").

**(a) LR_uc — cobertura incondicional** (§3.1, pp. 844–845), H0: E[I_t] = p
"given independence":

    L(p) = (1 − p)^{n_0} · p^{n_1};   L(π̂) = (1 − π̂)^{n_0} · π̂^{n_1}
    LR_uc = −2 log[ L(p) / L(π̂) ]   ~a  χ²(1)

"This procedure tests the coverage of the interval but it does not have any
power against the alternative that the zeros and ones come clustered together
in a time-dependent fashion" (p. 845); fn. 6: Kupiec (1995) aplica teste
similar.

**(b) LR_ind — independência contra Markov de 1ª ordem** (§3.2, pp. 845–846):

    L(Π̂_1) = (1 − π̂_01)^{n_00} · π̂_01^{n_01} · (1 − π̂_11)^{n_10} · π̂_11^{n_11}
    L(Π̂_2) = (1 − π̂_2)^{n_00 + n_10} · π̂_2^{n_01 + n_11}
    LR_ind = −2 log[ L(Π̂_2) / L(Π̂_1) ]   ~a  χ²(1)

"this test does not depend on the true coverage p, and thus only tests the
independence part of my hypothesis" (p. 846).

**(c) LR_cc — cobertura condicional** (§3.3, pp. 846–847; prova p. 861):

    LR_cc = −2 log[ L(p) / L(Π̂_1) ]   ~a  χ²(2)

"when ignoring the first observation, the three LR tests are numerically
related by the following identity, LR_cc = LR_uc + LR_ind" (p. 847) — exata
**porque** as contagens acima condicionam na primeira observação também no
LR_uc (com n_1 sobre as T observações a identidade é só aproximada, §7.7).

**Amostras pequenas** (§5.1, pp. 850–853; Monte Carlo com T de 250 a 2.000):
"dependence is the hardest to reject when p is … quite large (close to 0.95)
… the number of switches between zero and one, even under the null, is quite
small … Figure 2 also illustrates the need for sizable samples … I am trying
to draw inference about the tails of the distribution; a similar point is made
… by Kupiec (1995)" (p. 852). Christoffersen & Pelletier (2004, abstract, §2):
os testes de 1998 "have relatively small power in realistic small sample
settings" e "the Markov first-order alternative may have limited power against
general forms of clustering".

**Como se aplica aqui.** Para cada (modelo distribucional, horizonte, par
simétrico da grade), o hit sequence {I_t} do intervalo aninhado com p = τ_u −
τ_l, alinhado por `target_timestamp`, 1 obs/ponto, pooled sobre folds; os três
LR com o p nominal do par. Escassez de transições nas caudas (cálculo
próprio): sob iid, E[n_11] ≈ (T−1)·p_viol²; para o intervalo 96 % (p_viol =
0.04), T = 500 → 0,8; T = 1000 → 1,6; para o hit unilateral de τ = 0.02, T = 500
→ 0,2. **LR_ind no par mais externo e nos quantis extremos é quase sem
informação** com T de centenas; para 80 % e 50 % (p_viol 0.20/0.50) há material
(E[n_11] = 20–125 com T = 500). Os baselines pontuais não entram (§5.3).

**Convenção (FC4).** Forma dos testes: **2-estados por intervalo aninhado**
(PICP/Christoffersen) + **unilateral por nível τ** (hits {y ≤ q̂_τ}; VaR
descritivo, §7.5; Kupiec por cauda). O **3-estados** de Christoffersen §4.2
(pp. 848–849: S_t ∈ {1, 2, 3} para as duas caudas de um par, com LR_uc ~ χ²(2),
LR_ind ~ χ²(4), LR_cc ~ χ²(6)) **não** é adotado como backtest: testa ambas as
caudas de uma vez, mas com E[n_ij] minúsculos nas caudas o LR_ind/LR_cc sofre
ainda mais de esparsidade. **Exceção:** o **LR_uc de 3 estados** — que só usa
as contagens das duas caudas, sem transições — é computado para o **par
primário** como sensibilidade pré-registrada do gate H1 (§8.5); com ~50
violações esperadas por cauda no par de 80 % (T = 500), a esparsidade não se
aplica. Pertence ao serviço de Christoffersen da Stage 6.3.

### 7.3 Kupiec (1995): POF ≡ LR_uc, e o poder nas caudas

Lido na versão FEDS Working Paper 95-24; a versão de periódico (*J.
Derivatives* 3(2)) é `[CITAÇÃO-NÃO-ACESSADA]` quanto à numeração de expressões
e páginas. Modelo (pp. 7–8, fn. 9): a performance é "a series of draws from an
independent Bernoulli random variable"; "Independence is an implication of an
efficient bank forecast". Fn. 8: "the magnitude of the size of the differences
… is not informative" — só o binário conta. Horizonte (pp. 8–9): "it is futile
to monitor a model's accuracy at anything but a one-day horizon". **POF**
(expressão (6), p. 20; = (8), p. 24, binomial — "the binomial coefficient
cancels out"):

    LR_POF = −2 log[ (1 − p*)^{T−x} · (p*)^x ] + 2 log[ (1 − x/T)^{T−x} · (x/T)^x ]   ~ χ²(1)

com x = nº de falhas e p* = probabilidade de falha sob H0. Trocando x ↔ n_1,
p* ↔ 1−p, é **exatamente o LR_uc** de Christoffersen (a equivalência é
algébrica; Christoffersen fn. 6 confirma). O TUFF (expressão (2), p. 12) é caso
particular do POF com x = 1 e "has particularly poor power" (p. 16) — não
implementar. **Poder** (pp. 20–23; Table 2, p. 32): "the LR test based on the
unconditional likelihood has poor power characteristics"; para p* = 0.02, o
maior T em que x falhas rejeitam a 5 % **por excesso**: x = 1 → 3; x = 2 → 17;
x = 3 → 38; x = 4 → 63 — a tabela enumera só o ramo "falhas demais" e **não** é
monotônica em T: com T = 500 e p* = 0.02, 4 falhas (0,8 %) voltam a **rejeitar**
por sub-cobertura (LR_uc = 4,74 > 3,84; região de não-rejeição x ∈ [5, 16],
tabela abaixo); "the
statistical properties of tail events make it virtually impossible to
accurately verify estimates of the probabilities associated with such rare
events" (p. 23).

**Quantificação para as caudas do projeto** (cálculo próprio a partir da
expressão (6); χ²(1) crítico 3,841; poder exato pela binomial):

| p_viol nominal | T | E[x] | região de não-rejeição (x) | poder vs 2×p | poder vs p/2 |
|---|---|---|---|---|---|
| 0.02 (τ = 0.02, unilateral) | 250 | 5 | [2, 9] | 0,55 | 0,29 |
| 0.02 | 500 | 10 | [5, 16] | 0,78 | 0,44 |
| 0.02 | 1000 | 20 | [12, 29] | 0,96 | 0,70 |
| 0.04 (intervalo 96 %, bilateral) | 500 | 20 | [13, 29] | 0,96 | 0,79 |
| 0.10 (τ = 0.10, unilateral) | 500 | 50 | [38, 63] | 0,93 (vs 0.15) | 0,99 (vs 0.05) |
| 0.20 (intervalo 80 %) | 500 | 100 | [83, 117] | 1,00 (vs 0.30) | 1,00 (vs 0.10) |

Leitura: com T ≈ 500 pontos OOS por horizonte (ordem de grandeza plausível
para o cohort, a confirmar em 6.5), o POF **não distingue** cobertura 2 % de
1 % (poder 0,44) e distingue 2 % de 4 % só com poder 0,78; o tamanho exato
oscila (0,041–0,069) pela discretude da binomial. Nas caudas extremas o
backtest é **diagnóstico de miscalibração grosseira**, não certificado de
calibração — é o que o pré-registro deve declarar, e é a razão de o gate H1
não ser definido nas caudas (§8.5).

### 7.4 Multi-passo (h+7)

**Christoffersen 1998 não trata multi-passo** — todo o arcabouço é
L_{t|t−1}, U_{t|t−1} (pp. 843–847; ausência confirmada por leitura). **Diebold,
Gunther & Tay (1998, §6, pp. 880–881):** "our methods may be generalized to
handle multi-step-ahead density forecasts, so long as we make provisions for
serial correlation in z, in a fashion [analogous] to the usual MA(h − 1)
structure for optimal h-step ahead point forecast errors … Under the
assumption that the z series is (h − 1)-dependent, each of the following h
sub-series will be i.i.d.: {z_1, z_{1+h}, z_{1+2h}, …}, …, {z_h, z_{2h}, …}. Thus,
a test with size bounded by α can be obtained by performing h tests, each of
size α/h" (Bonferroni; "such sample splitting, although inefficient, is not
likely to cause important power deterioration" — nos datasets de alta
frequência deles). **Christoffersen & Diebold (2000, §3, fn. 14)** usam
retornos de h dias **não sobrepostos** "to eliminate the need to account for
the dependence induced by overlapping observations" — reconhecem a
dependência e a **evitam**.

**O que vale aqui** (derivação, marcada). O alvo em h é o retorno de **um** dia
em t+h, logo não há sobreposição de janelas de retorno; a sobreposição é de
**conjuntos de informação**: I_s (previsão feita em s−h) e I_{s+1} (feita em
s+1−h) partilham as inovações y_{s−h+1..s−1} que nenhum dos dois pôde usar.
Sob o critério h-step E[I_s | Ψ_{s−h}] = p: para lag k ≥ h, E[I_s I_{s+k}] =
p² (não correlacionados além de h−1); para lags < h a autocorrelação pode ser
positiva. É a estrutura MA(h−1) a que DGT aludem. Consequências: (i) LR_ind e
LR_cc testam iid, que **não é implicado** por calibração condicional h-step
correta quando h ≥ 2 → sobre-rejeição possível sem que o modelo esteja errado;
(ii) LR_uc continua centrado (E[I_t] = p) mas a χ²(1) assume iid — com
autocorrelação positiva a variância de Σ I_t/T é maior → sobre-rejeição.
`[SEM-FONTE-PRIMÁRIA para o passo "hits (h−1)-dependentes ⇒ tamanho distorcido
dos LR"; é composição de DGT 1998 §6 + Christoffersen 1998 Lemma 1]`.

**Convenção do projeto (B-H7 — decidida, §10.1).** LR_uc, LR_ind e LR_cc são
**definidos e computados para todo horizonte**; para h > 1 o doc declara que a
nula de independência é violada pela sobreposição de conjuntos de informação
(DGT 1998 §6 + a derivação marcada acima; Christoffersen & Diebold 2000 fn. 14
só atesta que a dependência por sobreposição — no caso deles, de retornos
h-dias — é reconhecida e **evitada**, não é fonte para o mecanismo do
projeto) e que **LR_ind/LR_cc em
h+7 são descritivos**; o **gate H1 em h+7 usa a banda de cobertura** (§4.4,
com o aviso de anti-conservadorismo), **não LR_cc**. A versão HAC do LR_uc
(regressão I_t − p sobre constante com erro-padrão Newey–West lag h−1 —
Christoffersen §4.3, pp. 849–850, já formula o critério como regressão de hits
e como restrições de momento; Engle & Manganelli 2004 `[CITAÇÃO-NÃO-ACESSADA]`
é o parente próximo) **não é adotada**: composição sem fonte primária
`[SEM-FONTE-PRIMÁRIA]`. A **partição em h sub-séries + Bonferroni** (DGT, a
recomendação do paper de origem para o multi-passo) entra como
**sensibilidade pré-registrada do gate H1 em h+7**, aplicada ao par primário
(§8.5): cada sub-série é, sob a nula de DGT, iid, logo a banda binomial vale
nela sem o anti-conservadorismo. Não é o gate porque o poder é baixo: com
h = 7 e T = 500/1000, cada sub-série tem 71/142 pontos — para o par de 80 %,
~7/14 violações esperadas por cauda; a p_viol = 0.02, 1,4/2,8 hits, e LR_ind
fica vazio. Se gate e sensibilidade discordarem, a discordância é reportada
(ICH E9 §5.3), não arbitrada. P-valor simulado sob nula
(h−1)-dependente: inviável (a estrutura de dependência é parâmetro de incômodo
que a H0 não determina).

### 7.5 VaR descritivo a partir dos quantis

**Definição.** McNeil, Frey & Embrechts (2005, Definition 2.10, §2.2.2): com a
perda L (convenção "losses will be positive numbers and profits negative"),
VaR_α = q_α(F_L) = inf{l : F_L(l) ≥ α}, α ∈ (0,1) próximo de 1 — verificado no
material oficial dos autores (slides QRM, © 2005); a página exata do livro não
foi aberta `[CITAÇÃO-NÃO-ACESSADA quanto à página]`, mas é consistente com a
Eq. (2.19)/Example 2.14 §2.2.2 já ratificados (modeling §3.6). Para posição
unitária em retorno log r, L = −r; para F_r contínua, F_L(l) = 1 − F_r(−l) ⇒
q_α(L) = −q_{1−α}(r). Logo (derivação a partir da definição verificada):

    VaR_α(retorno) = −q_{1−α}(r)      ex.: VaR_0.98 = −q_0.02;  VaR_0.90 = −q_0.10

O evento de violação {L_t > VaR_{α,t}} = {r_t < q_{1−α,t}} é invariante a
transformações monótonas (log-retorno vs retorno simples) — o backtest é
idêntico em qualquer unidade.

**Backtest = hits unilaterais por cauda.** I_t^{VaR} = 1{y_t ≤ q̂_{τ,t}} com
p_viol = τ para a cauda inferior (τ = τ_1, τ_2, …), e simetricamente
1{y_t > q̂_{τ,t}} com p_viol = 1−τ para a superior; LR_uc/ind/cc aplicam-se sem
alteração (Christoffersen pp. 843–844). Isto **é** a cobertura marginal por
quantil de §4.1 lida com o nome da gestão de risco — não há cálculo novo, há
re-rotulação de pontos da grade (o oráculo R usa a desigualdade estrita,
§7.7; diferença de medida zero para retornos contínuos).

**O que "descritivo" significa** (política `[SEM-FONTE-PRIMÁRIA]`, com suporte
indireto): (i) não há carteira, capital, ES nem função-perda de gestor — o
overview §3 exclui trading/risco; (ii) o objeto de H1 é a calibração da
**grade inteira**; o VaR é subconjunto; (iii) o backtest só usa o binário
(Kupiec fn. 8) e, em unilateral, perde informação sob dinâmica de volatilidade
(Christoffersen 1998, p. 861: "The loss of information from having only a
one-sided interval forecast can be serious when volatility dynamics are
present"); (iv) não entra no scorecard (overview §4). "VaR descritivo
backtestado" = LR_uc/LR_cc calculados e reportados por cauda, **nenhuma claim
de gestão de risco**. ES fica fora (roadmap 6.3 *non-goal*: exige backtest
próprio).

**Convenção.** VaR_α(r) = −q_{1−α}(r); hits unilaterais por cauda; Kupiec +
Christoffersen por cauda; rótulo "descritivo" como acima.

### 7.6 P-valores e casos-limite

**Convenção (FC6).** O p-valor reportado é o **χ² assintótico** (Christoffersen
1998). Como **sensibilidade em h+1**, o p-valor **Monte Carlo exato sob iid
Bern(p)** de Christoffersen & Pelletier (2004, §4.3, p. 8–9; técnica de
Dufour): sob H0 "the hit sequence is i.i.d. Bernoulli with the mean equal to
the coverage rate … not having nuisance parameters under the null"; p̂_N(LR_0)
= (N·Ĝ_N(LR_0) + 1)/(N + 1). Só h+1 admite o MC sem parâmetro de incômodo
(§7.4). **Caso n_11 = 0** (Christoffersen & Pelletier §4.1, p. 7): "if the
sample at hand has T_11 = 0, which can easily happen in small samples and with
small coverage rates, then we calculate the first-order Markov likelihood as
ln L(I, π_01, π_11) = (1 − π_01)^{T_0 − T_01} π_01^{T_01}" — numericamente
idêntico à convenção 0^0 = 1 do oráculo R. **Regra de mínimo de violações**
para rodar LR_ind (§5, p. 11: "we do not use Monte Carlo samples with zero or
one VaR violations … a risk management team would not start backtesting unless
at least a couple of violations had occurred") — é regra de exclusão, logo
**pré-registrada** (Simmons et al. 2011; Wagenmakers et al. 2012).

### 7.7 Convenção de condicionamento e o oráculo R

O oráculo `rugarch::VaRTest` (§11.3) calcula LR_uc sobre as **T** observações e
LR_ind sobre as **T−1** transições, e devolve cc = uc + ind — a identidade da
p. 847 só é exata se LR_uc **também** condiciona na primeira observação. A
diferença entre as duas convenções **não** é uniformemente pequena: com
I_1 = 0 é O(1/T) na estatística (T = 500, p = 0.02: 0,00–0,04 na região de
não-rejeição), mas com **I_1 = 1** é O(1) (0,1–1,6 no mesmo cenário — remover
uma violação entre ~10 muda π̂ em ~10 %; cálculo próprio). **Convenção
(FC5):** o projeto adota a convenção **"pura"** — tudo condicionado na primeira
observação, com a identidade LR_cc = LR_uc + LR_ind **exata** (Christoffersen
p. 847; §7.2) — e o golden-test contra o oráculo **compara convenções iguais**:
alimenta o oráculo com a série a partir de t = 2 (ou descarta I_1 da própria
implementação só para o teste), exigindo igualdade **exata** a menos de
arredondamento; **não** se usa tolerância O(1/T). Casos em que o
oráculo não devolve valor (zero violações em toda a série; n_10 + n_11 = 0) não
são "valores do oráculo" — são casos de domínio com política própria (gate de
degeneração §5; mínimo de violações §7.6).

## 8. Pré-registro e scorecard mecânico (Stages 6.5, 8.1)

### 8.1 O que o pré-registro congela

O pré-registro congela **como se julga** — tudo o que, mudado depois de ver
resultados, mudaria um número reportado ou o veredito:

- a **grade** exata de níveis e os **horizontes** (primários e suplementar);
- a **métrica primária** (P̄_G, escala ρ_τ) e o papel de cada secundária
  (CRPS_Q, IS_α por par, ĉ(τ), PICP/MPIW, LR's, VaR descritivo = perfil);
- a **família** de H2 (candidato × B comparadores, por horizonte), o α de
  Holm, a direção do DM, o kernel e o lag (h−1), o fallback de variância;
- os **parâmetros do MCS** (α_MCS, reps, tipo de bootstrap, regra do bloco e
  grade de sensibilidade, semente);
- a **regra do gate H1** (§8.5): o par primário, as bandas por cauda (Wilson
  97,5 %, Bonferroni), o pooling por horizonte, o tratamento de h+7 e suas
  sensibilidades (LR_uc de 3 estados; partição de DGT), o **limiar de
  degeneração**, a tolerância numérica de "igual", o **desvio mínimo
  relevante** e o poder do gate contra ele no T efetivo (B1);
- a **agregação de seeds** (média das perdas; cobertura média com n = pontos não-degenerados, nunca S·T) e a
  lista de seeds;
- a **fonte do realizado** (§2.1) e a **ausência de regras de exclusão** de
  observações (§5.3), a regra de mínimo de violações (§7.6);
- a **forma lógica do veredito** por horizonte (§8.6) e o critério de sucesso
  do estudo (§8.8);
- a referência ao **hash do cohort** (5.5) que congela **o que** se treina.

Fundamento: Nosek et al. (2018): "Preregistration of an analysis plan is
committing to analytic steps without advance knowledge of the research
outcomes"; Wagenmakers et al. (2012, p. 635): o documento pré-registrado
"details … which hypotheses are of interest, which statistical tests will be
used, and which outlier criteria or data transformations will be applied";
ICH E9 §5.1 (pp. 23–24): "Only results from analyses envisaged in the protocol
(including amendments) can be regarded as confirmatory".

### 8.2 Quando: antes de qualquer métrica confirmatória

**Convenção do projeto (B-ORDEM — decidida, §10.1; ADR 0.0.0011).** O pré-registro (6.5) é
**hasheado antes de qualquer métrica confirmatória ser computada** sobre as
predições OOS do cohort (8.1). O cohort (5.5) congela **o que** se treina
(candidato, comparadores, seeds, folds, configuração, grade) e tem **hash
próprio**, referenciado pelo pré-registro — são dois hashes com papéis
distintos, e a ordem é: cohort congelado e treinado → pré-registro hasheado →
avaliação confirmatória. **Ver predições OOS brutas antes do hash não é
violação; computar métricas confirmatórias é.** Isto resolve a tensão T10 do
inventário (o grafo do roadmap faz 6.5 depender de 5.5): "antes do
confirmatório" (overview §7) significa antes da **avaliação**, não antes do
treino. Suporte: Nosek et al. (2018, "Challenge 3: Data Are Preexisting") —
pré-registro com dados pré-existentes é possível, com o aviso de que "Once the
data have been observed, there are inevitable risks for blinding …
transparency provides insight about potential biasing influences"; os dados
OOS confirmatórios nunca alimentaram nenhuma decisão (sweeps exploratórios
usaram outro split e não escrevem no silver — ADR 5.4.0005; modeling §5.4);
ICH E9 §5.1: "Formal records should be kept of when the statistical analysis
plan was finalised as well as when the blind was subsequently broken" — o
hash é esse registro formal, verificável por terceiros (o hash em si não tem
fonte primária dedicada — modeling §6.3). Alternativa real descartada:
pré-registrar antes do treino do cohort — exigiria fixar a grade e os
parâmetros de inferência antes de saber o T efetivo por horizonte (déficit de
janela, §6.7), e o roadmap já ordena 5.5 → 6.5.

### 8.3 Por quê: a literatura que sustenta o desenho

- **Pré-registro e garden of forking paths** — Nosek et al. (2018): "the
  observed P value is diagnostic about its intended likelihood only when
  analysis choices are made before observing data"; "mistaking postdiction as
  prediction underestimates the uncertainty of outcomes"; desvios do plano são
  reportados ("Challenge 1").
- **Graus de liberdade do pesquisador** — Simmons, Nelson & Simonsohn (2011):
  a lista da p. 1359 (coletar mais? excluir observações? combinar condições?);
  Table 1 (p. 1361): quatro graus combinados elevam o falso-positivo nominal
  de 5 % para **60,7 %**; requisitos (pp. 1362–1363) e Guideline 3 (p. 1363):
  "demonstrate that their results do not hinge on arbitrary analytic
  decisions". O scorecard mecânico remove os graus de liberdade **da decisão**;
  o perfil mostra que o veredito não depende de escolha arbitrária.
- **Só o pré-declarado é confirmatório** — Wagenmakers et al. (2012, p. 632):
  "Only these analyses deserve the label 'confirmatory,' and only for these
  analyses are the common statistical tests valid. Other analyses can be
  carried out but these should be labeled 'exploratory.'" Paralelo direto
  sweep/cohort (modeling §5.4; Raschka 2018 §3.3).
- **Uma variável primária** — ICH E9 §2.2.2 (pp. 7–8): "There should generally
  be only one primary variable … Redefinition of the primary variable after
  unblinding will almost always be unacceptable"; secundárias como "supportive
  measurements" com papel declarado; §5.5 (p. 28): a análise primária "should
  be clearly distinguished from supporting analyses". Pinball primária +
  CRPS/IS/MPIW/VaR como perfil é esse desenho — disciplina de outro campo, mas
  o padrão regulatório mais maduro de regra de decisão pré-declarada.
- **Candidato único + família pequena** — White (2000, abstract p. 1097): data
  snooping "occurs when a given set of data is used more than once for
  purposes of inference or model selection … practically unavoidable in the
  analysis of time-series data"; Romano & Wolf (2005, §1): "some are bound to
  appear superior to the benchmark by chance alone". O projeto **elimina a
  busca em vez de corrigi-la** (modeling §6.1); Holm/MCS operam sobre a família
  congelada (§6.4).
- **Analysis sets e missing** — ICH E9 §5.2 (p. 24), §4.2 (p. 21), §5.3
  (pp. 26–27): conjunto de análise definido prospectivamente no protocolo,
  critérios de exclusão constantes, métodos de missing/outliers pré-definidos
  + análise de sensibilidade quando substanciais — fundamento do gate de
  degeneração como analysis set prospectivo (§5.3).

### 8.4 Variância por seeds e folds

Bouthillier et al. (2021, §1, §2, §5): "As many sources of variation as
possible should be randomized"; "Deciding of whether the benchmarks give
evidence that one algorithm outperforms another should not build solely on
comparing average performance but account for variance"; "Bootstrapping data
stands out as the most important source of variance … model initialization
generally is less than 50% of the variance of bootstrap"; "We recommend to
always highlight not only the best-performing procedure, but also all those
within the significance bounds" — alinhado com o papel do MCS e com
"não-dominância é resultado válido". Raschka (2018, §3.3): o OOS confirmatório
é usado **uma vez**; §4.5: procedimentos post hoc "do not require any prior
plan" — contraste com o pré-registro. Aplicação: seeds × folds (modeling §6.2);
reportar a **distribuição por seed** (§6.9), nunca a melhor seed; a seed não
pode ser escolhida por OOS.

### 8.5 O gate H1

**O problema.** H1 é "calibrado dentro de bandas pré-registradas" sobre
{intervalos aninhados × níveis τ × LR_uc/ind/cc × horizontes}. Sem correção,
"≥ 1 passa" é seleção pós-hoc; com Holm sobre a família toda, o gate fica
muito conservador num regime em que o poder já é baixo (§7.3). E K testes
independentes a 95 % reprovariam um modelo **perfeitamente calibrado** com
probabilidade até 1 − 0.95^K (≈ 30 % para K = 7) — teto sob independência; a
dependência positiva entre pares aninhados sobre os mesmos hits reduz o valor
real, mas não o elimina.

**Redação do claim (B1 — decisão P do humano, 2026-09-26).** O gate é um
teste que só consegue **reprovar**: passar significa "não há evidência de
descalibração", não prova de calibração. H1 é enunciada como **"calibração
não rejeitada na banda de Wilson"**, sempre acompanhada do **poder
declarado** contra um desvio mínimo pré-registrado; "calibrado" sem
qualificação não é usado (overview §4). Base: ICH E9 §3.3.2 (pp. 17–18):
"Concluding equivalence or non-inferiority based on observing a
non-significant test result of the null hypothesis that there is no
difference … is inappropriate" — o mesmo tratamento dado a H2 em §6.10. Alternativa
descartada pelo humano: **B2**, teste de equivalência (IC da cobertura
inteiro dentro de nominal ± δ) — δ não tem convenção na área, e com δ = 5 p.p.
e T = 500 um modelo perfeitamente calibrado passaria só em ~60 % das vezes,
bloqueando H2 por acaso em ~40 % dos casos.

**Convenção do projeto (B-GATE-H1 — decidida, §10.1; ADR 0.0.0011).** **Um
critério-gate pré-declarado por horizonte**, sobre o **par central
primário** (τ_l, τ_u) = (α/2, 1 − α/2), com duas condições:

1. **cada cauda** do par está dentro da **banda de Wilson a 97,5 %** (§4.4),
   pooled sobre folds: ĉ(τ_l) contém τ_l **e** 1 − ĉ(τ_u) contém 1 − τ_u —
   Bonferroni sobre as duas caudas, logo a probabilidade de reprovar um
   modelo calibrado é ≤ 5 %. Par recomendado: 80 % (~50 violações esperadas
   por cauda em T = 500), **não** as caudas τ_1/τ_K (~10 violações, §7.3);
   qual par é o primário é conteúdo do pré-registro. Para o candidato com S
   seeds, ĉ é a média entre seeds, com n = pontos não-degenerados, nunca S·T (§6.9);
2. a **taxa de degeneração** ≤ limiar pré-registrado (§5.3, item 4).

**Por que por cauda e não PICP.** O PICP é invariante a um deslocamento
comum das duas caudas (§4.2): um erro de **locação** — o modelo erra o
centro, e as duas caudas miscobrem em sentidos opostos — passa num gate só
por PICP. Probabilidade de **passar** no gate (cálculo próprio, binomial e
multinomial exatas, T = 500, par de 80 %, verdade N(μ, σ²) e previsão com os
quantis de N(0, 1)):

| Cenário | PICP real | só PICP (Wilson 95 %) | por cauda (Wilson 97,5 % ×2) | LR_uc 3 estados, χ²(2) a 5 % |
|---|---|---|---|---|
| calibrado | 0,800 | 0,950 | 0,959 | 0,951 |
| locação 0,2σ | 0,791 | 0,916 | 0,160 | 0,111 |
| locação 0,3σ | 0,780 | 0,790 | 0,004 | 0,002 |
| largura: cobertura real 75 % | 0,750 | 0,220 | 0,420 | 0,330 |
| largura: cobertura real 85 % | 0,850 | 0,173 | 0,464 | 0,252 |

O custo é declarado: contra erro **puro de largura** o gate por cauda detecta
pior que o PICP (passa 0,42 contra 0,22 com cobertura real de 75 %), porque
divide o mesmo desvio em duas caudas testadas a 97,5 %. O PICP do par
continua no **perfil**, onde esse erro aparece.

**Poder declarado (B1).** O pré-registro fixa o desvio mínimo relevante —
ex.: ±5 p.p. na cobertura do par primário, em duas formas, largura (as duas
caudas miscobrem no mesmo sentido) e locação (em sentidos opostos) — e
reporta o poder do gate contra cada forma **no T efetivo** do horizonte. Ordem
de grandeza em T = 500, pela tabela: largura de 5 p.p. é detectada em ~0,54–0,58;
locação de 0,2σ (3–4 p.p. por cauda, em sentidos opostos), em ~0,84.

**Sensibilidade pré-registrada.** O **LR_uc de 3 estados** de Christoffersen
(1998, §4.2) sobre o mesmo par — as duas caudas num teste χ²(2) — domina o
gate por cauda em todos os cenários da tabela. Fica como sensibilidade, e não
como gate, porque B1 enuncia o claim na banda de Wilson (degrau 1: coerência
com o que o humano ratificou) e porque a leitura "cada cauda dentro da sua
banda" é a que o perfil ĉ(τ) já mostra. Discordância gate × sensibilidade é
reportada, não arbitrada. Em h+7, a partição de DGT (§7.4) é a segunda
sensibilidade.

**Só o candidato é filtrado.** Comparadores que reprovam o próprio H1
continuam na família de Holm e no MCS (§6.4); o gate decide apenas a
elegibilidade do candidato para H2.

O resto de H1 — cobertura por τ (com Holm **dentro** do horizonte quando se
quiser inferência), PICP e demais intervalos, LR_ind/LR_cc, sharpness, VaR
descritivo — é **perfil de H1**, não gate: caracteriza "de forma rica"
(overview §4) sem multiplicar chances de reprovação por acaso. Alternativas
reais descartadas: (a) gate só por PICP (o rascunho deste doc) — cego a
locação, tabela acima; (b) Holm sobre toda a família de H1 — conservador
demais com o poder de §7.3; (c) regra de interseção "nenhum teste rejeita a
α_gate" — conservadora no sentido oposto, sem controle explícito; (d) zonas
Basel como gate — unilateral (H1 é bilateral) e calibrado a 99 %/250 dias,
não à grade do projeto (fica no perfil); (e) PICP **e** caudas juntos —
três testes elevam a reprovação por acaso de um modelo calibrado para até
~10 % sem correção.

### 8.6 Estrutura do veredito por horizonte

O scorecard é uma **árvore de decisão pré-registrada** (Nosek et al. 2018,
"Challenge 2": "A decision tree defines the sequence of tests and decision
rules at each stage of the sequence"), aplicada mecanicamente, **por
horizonte**:

    H1 (gate, só o candidato): cada cauda do par primário na banda de Wilson 97,5 %  E  taxa de degeneração ≤ limiar
        ├─ reprova → H2 "não aplicável" neste horizonte (skill de candidato mal-calibrado não se compara — overview §4)
        └─ aprova ("calibração não rejeitada", com o poder declarado) → H2 (família e M0 inalterados pelo H1 dos comparadores):
              (i)  supera os naive?        DM unilateral + Holm (família = B comparadores do horizonte), α pré-registrado
              (ii) supera/empata os fortes? DM+Holm para "supera"; "empata" = não eliminado do MCS ao nível α_MCS (§6.10)
              (iii) pertence ao MCS?        evidência complementar, não condição

O **vencedor primário** é definido pela regra pré-registrada sobre (i)–(iii)
(a forma lógica exata — ex.: "menor P̄_G com DM+Holm significativo vs todos os
naive e não eliminado do MCS" — é conteúdo do pré-registro, não deste doc: ICH
E9 e Nosek sustentam que **exista** uma regra pré-declarada, não ditam qual).
**O perfil nunca troca o veredito** (overview §4; ICH E9 §2.2.2/§5.5; Simmons
Guideline 3) — CRPS_Q, IS_α, MPIW, cobertura por τ, LR_ind/cc, VaR, DM por τ,
DM por fold, dispersão por seed **descrevem** o resultado e mostram que ele
não depende de escolha arbitrária. `academic_decision_ready` (roadmap 6.5) é a
conjunção de gates — engenharia, sem fonte.

### 8.7 Nunca agregar entre horizontes

Princípio em §2.7; aqui o fundamento completo. (i) **Premissa dos testes:** a
dependência do diferencial de perda é função de h — erros ótimos h-passos são
MA(h−1) (DM 1995 p. 254; HLN 1997 pp. 281–282) — logo a variância de longo
prazo, o truncamento h−1 e o fator HLN são **específicos de h**; uma série que
misture horizontes não tem S(T) nem fator únicos (derivação). LR_uc/cc
pressupõem iid (só h+1, §7.4). As distribuições das perdas em h+1 e h+7 são
distintas (o erro cresce com h — FPP3 §5.10): agregar muda o estimando (vira
mistura) e invalida os lags. (ii) **Alvos duplicados:** o mesmo y_t é alvo da
previsão h=1 feita em t−1 e da h=7 feita em t−7 — empilhar horizontes duplica
alvos e cria dependência cruzada não modelada (derivação). (iii) **Literatura
por horizonte:** o teste multi-passo de Giacomini & White (2006, §3.3) é por
horizonte τ, com pesos até τ−1; FPP3 §5.10 computa e plota acurácia **por
horizonte** na origem rolante; Kupiec (1995, pp. 8–9) declara "futile"
monitorar acurácia fora do horizonte de um dia. Tashman (2000)
`[CITAÇÃO-NÃO-ACESSADA]` é citado no repo (modeling §6.2) pela avaliação em
origem rolante — que ele trate a acurácia por lead time separadamente está
**inferido**, não verificado; Bergmeir & Benítez (2012) `[CITAÇÃO-NÃO-ACESSADA
quanto a horizontes]` é citado pela multi-origem. **Conclusão honesta para o
pré-registro:** "nunca agregar" é prática consolidada + consequência das
premissas dos testes, **não teorema publicado**. ADR 5.3.0001 já rejeitou um
desenho de modelo por "blurs the per-horizon reading".

### 8.8 Critério de sucesso do estudo: "≥ 1 horizonte"

**Convenção (T11).** H1 é julgada **por horizonte**; H2 só nos horizontes que
passam H1; "calibração não rejeitada para ≥ 1 horizonte dentro de bandas
pré-registradas" (overview §4, redação B1) é o **critério de sucesso do
estudo** — existe ao menos um horizonte em que o gate não rejeita a
calibração, com o poder declarado — e não uma agregação: um horizonte reprovado em H1 é
reportado como tal, com seu perfil, e "refutação é resultado válido"
(overview §1). O h+30 suplementar segue a mesma árvore, com o excesso de
tamanho do DM crescendo com h (HLN 1997 Table 1) declarado.

## 9. Fronteira com o modeling e com o Step 7

### 9.1 O que este doc consome do modeling §7 (ponteiros)

| Contrato (modeling §7) | Onde este doc o usa |
|---|---|
| 1. Grade comum, formato long, nível na chave | §2.1 (objeto), §3.1 (pareável nível a nível), §6.7 (validação de grade no pareamento) |
| 2. Uma observação por `target_timestamp` (dedup operationally-latest) | §2.1, §6.7 (pré-condição do d_t) |
| 3. Pinball como loss de treino **e** métrica pareada (Gneiting 2011 Thm 9) | §2.5, §3.1, §6.1 (loss = L_t), §6.6 |
| 4. Grade degenerada dos baselines pontuais = Dirac; gate de degeneração é do Step 6 | §5 (definição, política, T1 resolvida), §6.6 |

Também pressupostos: alvo = retorno de um dia em t+h (modeling §2.1), o
rearranjo do guardrail (modeling §2.4; §2.2 deste doc), o protocolo temporal
da 5.1 (folds expansivos — §6.8), o cohort seeds × folds e o congelar+hashear
(modeling §6.2–§6.3; §6.9, §8.2 deste doc).

### 9.2 O que este doc NÃO deriva (Step 7)

- **Conformal / CQR** (Romano, Patterson & Candès 2019; Barber et al. 2023;
  Lei et al. 2018 — completos em ADRs 5.1.0002/5.4.0001): a recalibração
  empírica de intervalos, a partição `calib` dedicada, os 4 invariantes e a
  linguagem obrigatória "cobertura **empírica** (não 'garantida')" (overview
  §8 R-CONFORMAL-1; ADR 5.1.0002). O CQR é **benchmark comparativo** de
  cobertura (overview §11, `0_0_0008`), não régua de H1 (§4.4) nem membro da
  família de H2 (§6.4). A teoria da cobertura conformal e sua comparação com
  a calibração nativa pertencem ao doc de domínio do gate do Step 7; quando
  esse doc existir, as métricas de §4 aplicadas aos intervalos conformais
  reusam **estas** definições (PICP, MPIW, Wilson, hits) sem re-derivação.
- **Calibração condicional no valor previsto** (T-calibration / CORP de
  Gneiting & Resin 2023) — extensão não adotada (§4.1).

### 9.3 Vocabulário órfão do roadmap (T9) — abandonado

Os termos abaixo aparecem **só** no texto das Stages 6.2/6.3/6.5 do roadmap
(herança do projeto antigo) e não são definidos em nenhum outro arquivo do
repo. **Este doc não os usa**; a redação do roadmap é ajustada nas PRs dessas
Stages (registro no ADR de recorte deste gate):

| Termo órfão | O que este doc diz no lugar |
|---|---|
| "C.0" (documento de disposições) | não existe; as disposições estão em §3–§8 |
| "Gate A" (loss = pinball) | §6.4: loss pareada = P̄_G / L_t |
| "Gate B" (sem top-50) | §6.4 / §8.3: candidato único, sem seleção por OOS (modeling §6.1) |
| "Gate C" (família Holm com `split_signature`) | §6.4: família = B comparadores por horizonte, mesma amostra pareada (§6.7) |
| "Gate D" (VaR descritivo) | §7.5 |
| "Gate E" | nunca definido; sem correspondente |
| "Gate F" (dedup) | §2.1 / §6.7: 1 obs por ponto (modeling §7 item 2) |
| "top-50" | sem correspondente (é a busca que o desenho elimina) |
| "win-rate" | sem correspondente; não é reportado |
| "DELETAR prob_up / confidence / ES / expected_move / downside" | nenhum desses objetos existe no domínio; ES é *non-goal* declarado (§7.5) |
| "DESCRIPTIVE MPIW / win-rate" | MPIW é descritivo por §4.3; win-rate não existe |

## 10. Convenções decididas (tabela-resumo)

Legenda de status: **decidida** (política sem fonte primária, ancorada em doc
ratificado ou na teoria citada); **decidida — B-…** (posição recomendada
pelo gate, depois fechada pela triagem E/C com registro em §10.1; ADR onde indicado).

| # | Convenção | Fonte / âncora | Status | Stage |
|---|---|---|---|---|
| 1 | Realizado = `target_return` persistido, juntado por `target_timestamp`; a avaliação nunca recomputa o alvo (T13) | ADR 4.3.0001; modeling §2.1 | decidida (ancorada) | 6.1, 6.4 |
| 2 | Grade genérica simétrica; níveis exatos = entrada do cohort + pré-registro (T14) | concept 5.2 I11; roadmap "Lacunas" | decidida (sem decisão de níveis aqui) | 6.5 |
| 3 | Pontua-se o vetor rearranjado; bruto não pontuado; taxa de aplicação do guardrail no perfil (T4/FA9) | modeling §2.4; ADR 4.3.0002 Alt C; Berrisch & Ziel 2023 §3.4; Brehmer & Gneiting 2021 §3.2 | decidida (ancorada); ADR curto | 6.1 |
| 4 | Escala ρ_τ (sem fator 2); CRPS_Q na escala do CRPS; escala dos oráculos declarada (T8) | modeling §2.2/§9.3; §11.3 | decidida | 6.1 |
| 5 | Pesos iguais na média da grade (FA2) | Gneiting & Ranjan 2011 pós-(17) | decidida | 6.1 |
| 6 | CRPS reportado = CRPS_Q = 2·P̄_G (quadratura uniforme); não é evidência independente; papel = escala de y + perfil por τ | Berrisch & Ziel 2023 Eq. (9); Bracher et al. 2021 App. A Eq. (6); GR 2007 §4.2 | **decidida — B-CRPS** (§10.1) (ADR `0_0_0009`) | 6.1, 6.5 |
| 7 | IS_α por par simétrico, não escalado, com decomposição; WIS não reportado; só pares simétricos (FA4/FA10) | GR 2007 Eq. (43); Bracher et al. 2021 App. A Eq. (5); Brehmer & Gneiting 2021 Thm 3.1 | decidida | 6.1 |
| 8 | MPIW em unidade de y (não NMPIW) + sharpness diagram (FA5) | GBR 2007 §3.3 | decidida | 6.1, 8.3 |
| 9 | Cobertura marginal com 1{y ≤ q̂}; PICP com [l ≤ y ≤ u] (FA7) | GBR 2007 Thm 2; Kuleshov 2018 Eq. (3); Pearce 2018 Eq. (4) | decidida | 6.1, 6.3 |
| 10 | Banda de H1 = Wilson (95 % para teste isolado; 97,5 % por cauda no gate), por horizonte, pooled sobre folds, contendo o nominal (critério decisivo); n = pontos alinhados não-degenerados (≈ T), nunca S·T; LR_uc/POF como teste formal associado (pode discordar por 1 contagem — reportado, não arbitrado); zonas Basel no perfil; nível/T mín./h+7 no pré-registro (FA6/FC2) | BCD 2001 Eq. (4); Kupiec 1995 Table 2; BCBS 1996 §III | **decidida — B-BANDAS** (§10.1) | 6.3, 6.5 |
| 11 | CWC e combinações ad hoc largura×cobertura não existem no domínio | GR 2007 §9.3/§6.3; Askanazi et al. 2018 §3 | decidida | 6.1 |
| 12 | Gate de degeneração: colapso total; parcial = diagnóstico; proper scores sempre; calibração só em não-degeneradas (N/A a 100 %); taxa sempre; limiar pré-registrado reprova H1 dos distribucionais; **sem exclusão de linhas** na inferência; DoD 6.1 lê-se "métricas de calibração" (T1/FA8/FB5/FC7) | GR 2007 §4.2; Simmons 2011 req. 5; ICH E9 §5.2–§5.3; contiguidade HAC/bootstrap | **decidida — B-GATE** (§10.1) (ADR `0_0_0011`) | 6.1, 6.2, 6.4, 6.5 |
| 13 | Loss pareada = P̄_G por horizonte; 1 DM por (cand, comp, h); família de Holm = B comparadores do horizonte; DM por τ = perfil (T3/T5/FB1/FB3) | Holm 1979 Thm 1; Romano & Wolf 2005 §3; overview §7 | **decidida — B-FAMILIA** (§10.1) (ADR `0_0_0010`) | 6.2, 6.5 |
| 14 | Kernel retangular lag h−1 + HLN + t_{T−1}; Bartlett como sensibilidade (FB2) | DM 1995 p. 254; HLN 1997 Eq. (9); R `dm.test` | decidida (pré-registrável) | 6.2 |
| 14b | Variância de longo prazo ≤ 0 (h > 1) → seguir o oráculo (recalcular com h = 1), registrar a ocorrência; DM 1995 rejeitaria | R `dm.test`; `[SEM-FONTE-PRIMÁRIA]` | **decidida — B-DM** (§10.1) | 6.2, 6.5 |
| 15 | DM unilateral testa "superar" (E[d] < 0); "empatar" = pertencer ao MCS; não-rejeição ≠ equivalência; TOST não adotado (T7) | DM 1995; HLN 2011 Def. 4/Thm 3 | decidida | 6.2, 6.5 |
| 16 | MCS: estatística 'R', α_MCS = 0,10, reps ≥ 1.000, regra de eliminação correta; pré-condição var(L_i − L_j) > 0 (T6/FB4/FB8/FB9) | HLN 2011 Defs. 2/4, §5.1, fn. 14 | decidida (pré-registrável) | 6.2, 6.5 |
| 16b | Stationary bootstrap (HLN usam moving-block — sensibilidade) com bloco = maior b̂_sb de Politis–White entre os diferenciais do horizonte + sensibilidade l = h e √T | Politis & White 2004; White 2000 §2.c; `[SEM-FONTE-PRIMÁRIA]` para variante e agregação | **decidida — B-MCS** (§10.1) | 6.2, 6.5 |
| 17 | Pareamento por interseção exata de `target_timestamp` entre todos os modelos do horizonte; T reportado (1.21b) | DM 1995 §1; HLN 2011 p. 458; statsmodels HAC | decidida | 6.2, 6.4 |
| 18 | Folds concatenados em série contígua por horizonte; diagnóstico de estacionariedade; DM por fold no perfil; janela rolante = limitação declarada (FB6) | Diebold 2015 §2.2/§3; HLN 2011 p. 484 e nota 11 do WP; GW 2006 §3.2 | **decidida — B-FOLDS** (§10.1) | 6.2, 6.5 |
| 19 | Seeds → média ponto a ponto das perdas (conservadora pelo Jensen); cobertura/degeneração = média entre seeds, n ≈ T (nunca S·T); gate e sensibilidades por contagens médias; LR_ind/cc por seed e fração de seeds que rejeita no perfil; GBM determinístico → uma execução, com teste de contrato na 5.5; nº de seeds = P no congelamento do cohort (T12/FB7) | Bouthillier 2021; Jensen (derivação); código do adapter LightGBM | **decidida — B-SEEDS** (§10.1) (ADR) | 6.2, 6.5 |
| 20 | Backtests: 2-estados por intervalo aninhado + unilateral por τ; 3-estados não adotado como backtest — exceto o LR_uc de 3 estados do par primário, sensibilidade do gate H1 (FC4) | Christoffersen 1998 §3/§4.2 | decidida | 6.3 |
| 21 | Convenção "pura" de condicionamento — todas as contagens sobre t = 2..T, n_1 = n_01 + n_11 (identidade LR_cc = LR_uc + LR_ind exata); golden-test compara convenções iguais (oráculo alimentado a partir de t = 2), sem tolerância O(1/T) (FC5) | Christoffersen 1998 pp. 845/847; C&P 2004 §4.1; `rugarch` | decidida | 6.3 |
| 22 | P-valor χ² assintótico; MC exato sob iid Bern(p) como sensibilidade em h+1; mínimo de violações para LR_ind pré-registrado (FC6) | Christoffersen 1998; Christoffersen & Pelletier 2004 §4.1, §4.3, §5 | decidida | 6.3, 6.5 |
| 23 | h+7: LR's computados; LR_ind/LR_cc descritivos para h > 1; gate H1 em h+7 = banda; LR_uc-HAC não adotado; partição + Bonferroni registrada (FC1) | DGT 1998 §6 + derivação `[SEM-FONTE-PRIMÁRIA]`; Christoffersen & Diebold 2000 fn. 14 (só reconhecimento) | **decidida — B-H7** (§10.1) | 6.3, 6.5 |
| 24 | VaR_α(r) = −q_{1−α}(r); hits unilaterais por cauda; Kupiec + Christoffersen por cauda; "descritivo" = sem claim de risco | QRM 2005 Def. 2.10; Christoffersen 1998 pp. 843–844 | decidida | 6.3 |
| 25 | Pré-registro congela COMO se julga e é hasheado antes de qualquer métrica confirmatória; cohort congela O QUE e tem hash próprio referenciado (T10) | Nosek 2018; ICH E9 §5.1; modeling §6.3 | **decidida — B-ORDEM** (§10.1) | 6.5, 8.1 |
| 26 | Gate H1 = um critério por horizonte, só do candidato (cada cauda do par primário na banda de Wilson 97,5 % + taxa de degeneração ≤ limiar); claim "calibração não rejeitada" + poder declarado (B1); LR_uc 3 estados e partição DGT (h+7) como sensibilidades; PICP e o resto no perfil; comparadores ficam na família mesmo reprovando H1 (FC3) | ICH E9 §2.2.2 e §3.3.2; Nosek 2018 "Challenge 2"; Christoffersen 1998 §4.2; White 2000 §2; §8.5 (tabela de poder) | **decidida — B-GATE-H1** (§10.1) | 6.5, 8.1 |
| 27 | Veredito por horizonte: H1 → H2 = {supera naive?, supera/empata fortes?, MCS?}; perfil nunca troca o veredito; forma lógica exata no pré-registro | ICH E9 §2.2.2/§5.5; Simmons 2011; Nosek 2018 | decidida | 6.5, 8.1 |
| 28 | H1 por horizonte; H2 só onde H1 passa; "≥ 1 horizonte" = sucesso do estudo (T11) | overview §4 | decidida | 6.5, 8.1 |
| 29 | Nunca agregar entre horizontes — prática + premissas dos testes, não teorema | DM 1995; HLN 1997; GW 2006 §3.3; FPP3 §5.10; Kupiec 1995 pp. 8–9 | decidida (ancorada em overview §7) | todas |
| 30 | Vocabulário órfão do roadmap (C.0, Gate A–F, top-50, win-rate, DELETAR/DESCRIPTIVE) abandonado; roadmap ajustado nas PRs 6.2/6.3/6.5 (T9) | — | decidida (ADR de recorte) | 6.2, 6.3, 6.5 |

### 10.1 Registro das decisões (triagem `evidence-resolution`, 2026-09-26)

Triagem: todas as bifurcações abaixo são anteriores a qualquer dado
confirmatório (8.1 não rodou), logo nenhuma C virou P. A única P do lote é a
redação do claim de H1 (**B1**, decidida pelo humano na issue #78); o número
de seeds do cohort é P da Stage 5.5, fora deste doc. "Verificado" = trecho
conferido na fonte bruta por verificador de contexto zerado (skill §4.2) nesta
sessão; os demais localizadores são os da sessão do gate.

```
[decision:P] B1 — redação do claim de H1
Escolha: "calibração não rejeitada na banda de Wilson" + poder declarado contra desvio mínimo pré-registrado · Alternativas: B2 (equivalência, IC ⊂ nominal ± δ) · Decisor: humano (issue #78, 2026-09-26)
Base: ICH E9 §3.3.2 pp. 17–18 "Concluding equivalence or non-inferiority based on observing a non-significant test result … is inappropriate" [verificado]
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até o hash do pré-registro

[decision:C] B-GATE-H1 — que teste é o gate de H1 por horizonte
Escolha: cada cauda do par primário na banda de Wilson 97,5 % (Bonferroni, 2 caudas) + taxa de degeneração ≤ limiar; só o candidato · Alternativas: só PICP (Wilson 95 %); LR_uc 3 estados χ²(2); PICP e caudas juntos; Holm sobre a família de H1; Basel · Degrau: 1 (B1 ratificou o claim na banda de Wilson) e 4 (menos aprovações falsas: locação 0,3σ passa 0,004 contra 0,790 do PICP — §8.5, cálculo próprio)
Base: §4.2 (PICP invariante a deslocamento comum das caudas); Christoffersen 1998 §4.2 (3 estados) [não reverificado: as cópias acessíveis são escaneadas; localizador da sessão do gate; o χ²(2) é elementar — multinomial de 3 células, nula sem parâmetro livre]
Sensibilidade pré-registrada: LR_uc de 3 estados no mesmo par; partição DGT em h+7 · Reversível: sim, até o hash do pré-registro

[decision:C] B-BANDAS — banda de cobertura de H1
Escolha: Wilson, por horizonte, pooled sobre folds, n = pontos alinhados não-degenerados (≈ T, nunca S·T); 95 % isolado, 97,5 % por cauda no gate · Alternativas: Wald; tolerância fixa δ; banda relativa ao CQR · Degrau: 3
Base: Brown, Cai & DasGupta 2001, abstract p. 101 "we recommend the Wilson interval or the equal-tailed Jeffreys prior interval for small n" [verificado]
Sensibilidade pré-registrada: LR_uc/POF (mesma nula, teste LR) · Reversível: sim

[decision:C] B-CRPS — estimador do CRPS sobre a grade
Escolha: (a) CRPS_Q = 2·P̄_G, pesos iguais; rotulado "2 × pinball média"; sem comparação com CRPS publicado · Alternativas: (b) ensemble de quantis; (c) spline + convenção de cauda · Degrau: 2
Base: scoringrules 0.11.0 `crps_quantile` → `core/crps/_approx.py::quantile_pinball` "2 * B.mean(below + above, axis=-1)" [verificado]; Berrisch & Ziel 2023 Eq. (9) "for an equidistant dense grid" [verificado]
Sensibilidade pré-registrada: nenhuma (mesma ordenação da pinball) · Reversível: sim

[decision:C] B-GATE — semântica do gate de degeneração
Escolha: colapso total; proper scores em todas as linhas; calibração só nas não-degeneradas; taxa sempre; limiar reprova H1 dos distribucionais; sem exclusão de linhas na inferência · Alternativas: invalidar tudo (leitura literal do DoD 6.1); exclusão pareada · Degrau: 1 (modeling §3.4 e ADR 0.0.0052: Dirac bem-posto)
Base: Gneiting & Raftery 2007 §4.2 p. 367 "the CRPS provides a direct way to compare deterministic and probabilistic forecasts" [verificado]; Simmons et al. 2011 req. 5 p. 1363 "If observations are eliminated, authors must also report what the statistical results are if those observations are included" [verificado]
Sensibilidade pré-registrada: nenhuma no veredito; LR_ind/LR_cc com/sem as lacunas reportados lado a lado no perfil · Reversível: sim

[decision:C] B-DM — variância de longo prazo ≤ 0 com h > 1
Escolha: seguir o oráculo (recalcular com h = 1) e registrar a ocorrência · Alternativas: DM 1995 (tratar como 0 e rejeitar); Bartlett · Degrau: 2
Base: R forecast `R/DM2.R` warning("Variance is negative. Try varestimator = bartlett. Proceeding with horizon h=1.") [verificado]
Sensibilidade pré-registrada: Bartlett (já em §6.1) · Reversível: sim

[decision:C] B-FAMILIA — loss pareada e família de Holm
Escolha: L_t = P̄_G por ponto; 1 DM por (candidato, comparador, horizonte); família = os B comparadores do horizonte, independente do H1 deles; DM por τ = perfil · Alternativas: família global H × B; por τ; subfamílias por camada · Degrau: 1 (overview §4/§7: H2 por horizonte, nunca agregar)
Base: Holm 1979 §2 p. 67 "compared to the numbers α/n, α/(n−1), …, α" e Theorem 1 [verificado]
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] B-MCS — bootstrap e bloco do MCS
Escolha: stationary bootstrap; bloco = max(h, maior b̂_sb de Politis–White entre os d_ij do horizonte) — piso h por coerência com o roadmap ("block_len ≥ h", degrau 1) · Alternativas: moving-block (o de HLN 2011); √T (default do backend); l = h · Degrau: 2 (variante = default do `arch`) e 4 (bloco mais persistente = mais conservador); o default √T foi descartado porque a própria docstring pede escolha "appropriate for the data"
Base: `arch` `MCS(... bootstrap="stationary", block_size=None)`, docstring "In general, this should be provided and chosen to be appropriate for the data"; `optimal_block_length` → `b_sb` [verificado]
Sensibilidade pré-registrada: l = h, l = √T, moving-block · Reversível: sim

[decision:C] B-FOLDS — série de teste sob o esquema expansivo
Escolha: concatenar os folds numa série contígua por horizonte + diagnóstico de estacionariedade de d_t + DM por fold no perfil; janela rolante = limitação declarada · Alternativas: cohort rolante; teste por fold agregado · Degrau: 1 (ADR 5.1.0001, esquema expansivo)
Base: HLN (CREATES RP 2010-76, nota 11) "it produces pseudo-MCS results that are very similar to those obtained under the rolling window estimation scheme" [verificado]
Sensibilidade pré-registrada: DM por fold (perfil) · Reversível: sim (a limitação fica declarada)

[decision:C] B-SEEDS — série do candidato com S seeds
Escolha: média ponto a ponto das perdas; cobertura/degeneração = média entre seeds, n ≈ T (nunca S·T); gate e sensibilidades por contagens médias; LR_ind/cc por seed no perfil; GBM com uma execução (determinístico) · Alternativas: ensemble de previsões; teste por seed; seed fixa · Degrau: 4 (Jensen: média das perdas ≥ perda do ensemble)
Base: convexidade da pinball (derivação); adapter LightGBM `deterministic=True`, `feature_fraction=1.0`, `bagging_fraction=1.0`, `bagging_freq=0` (código lido em 2026-09-26, teste de contrato na 5.5)
Sensibilidade pré-registrada: dispersão e fração de seeds que rejeita · Reversível: sim

[decision:C] B-H7 — backtests e gate em h+7
Escolha: LR's computados; LR_ind/LR_cc descritivos para h > 1; gate = banda (§8.5), com aviso de anti-conservadorismo · Alternativas: LR_uc-HAC; partição DGT como gate · Degrau: 3 para a sensibilidade (DGT é a recomendação do paper de origem) e 5 para o gate (o mesmo critério em todo horizonte)
Base: Diebold, Gunther & Tay 1998 §6 p. 880 "each of the following h sub-series will be i.i.d. … a test with size bounded by α can be obtained by performing h tests, each of size α/h" [verificado; apresentado pelos autores como generalização, com a ideia de Bonferroni atribuída a Campbell & Ghysels 1995]
Sensibilidade pré-registrada: partição DGT + Bonferroni no par primário · Reversível: sim

[decision:C] B-ORDEM — ordem cohort × pré-registro
Escolha: cohort (5.5) congelado e treinado → pré-registro (6.5) hasheado → métricas confirmatórias (8.1); ver predições brutas não viola, computar métricas confirmatórias viola · Alternativas: pré-registrar antes do treino · Degrau: 1 (roadmap 5.5 → 6.5; overview §7)
Base: Nosek et al. 2018 "Challenge 3" "once the data have been observed, there are inevitable risks for blinding … This transparency provides insight about potential biasing influences" [verificado; a reticência une dois parágrafos]
Sensibilidade pré-registrada: nenhuma · Reversível: não depois do hash (é o objetivo)
```

## 11. Referências

Citações completas de todas as fontes usadas. Separadas em (11.1) já
ratificadas no overview §10 — várias delas só como nome curto até aqui; a
citação completa é nova —, (11.2) novas deste doc (a registrar no overview §10
no mesmo PR, conforme ADR 0.0.0003) e (11.3) documentação de biblioteca.
Rótulo `[CITAÇÃO-NÃO-ACESSADA]` onde a fonte não foi lida em primária durante
o gate; as demais foram verificadas no texto (paper, versão working paper
indicada, ou documentação/código oficial).

### 11.1 Já ratificadas no overview §10

- Diebold, F. X.; Mariano, R. S. (1995). "Comparing Predictive Accuracy". *Journal of Business & Economic Statistics*, 13(3), 253–263. DOI: 10.1080/07350015.1995.10524599. (§1–§1.1 p. 254: nula, S1, lag window retangular com S(T) = k−1, variância negativa; §3 p. 257: oversized em amostras pequenas. Lida na reimpressão JSTOR 2002; paginação original mapeada pelos cabeçalhos.)
- Harvey, D.; Leybourne, S.; Newbold, P. (1997). "Testing the equality of prediction mean squared errors". *International Journal of Forecasting*, 13(2), 281–291. DOI: 10.1016/S0169-2070(96)00719-4. (pp. 281–282 premissa MA(h−1); §2 Eqs. (5)–(9) p. 283; t_{n−1} pp. 283–284; Table 1 p. 285; §5 pp. 290–291.)
- Hansen, P. R.; Lunde, A.; Nason, J. M. (2011). "The Model Confidence Set". *Econometrica*, 79(2), 453–497. DOI: 10.3982/ECTA5771. (p. 458 d_{ij,t}, Definition 1, Eq. (1); Definition 2 p. 459; Theorem 1 p. 459; Definition 4 e Theorem 3 p. 462; Assumption 2 p. 464; §3.1.2 p. 465 t_ij/T_R; p. 466 e_R/e_max; §4.1 p. 474; §5.1 pp. 477–478; p. 484 e fn. 14. Supplemental Material não acessado. A nota sobre o esquema recursivo (§6.8) foi lida no working paper CREATES RP 2010-76, nota 11.)
- Holm, S. (1979). "A Simple Sequentially Rejective Multiple Test Procedure". *Scandinavian Journal of Statistics*, 6(2), 65–70. (Definição p. 65; §2 Scheme 1 pp. 66–67; Theorem 1 p. 67.)
- Koenker, R.; Bassett, G., Jr. (1978). "Regression Quantiles". *Econometrica*, 46(1), 33–50. DOI: 10.2307/1913643. (Displays da p. 38.)
- Gneiting, T. (2011). "Making and Evaluating Point Forecasts". *Journal of the American Statistical Association*, 106(494), 746–762. DOI: 10.1198/jasa.2011.r10138. (§1.1 Eq. (1); Definition 2.1, Theorems 2.2–2.4; Eq. (24) §3.3 pp. 754–755; Theorem 9 p. 755 — Theorem 3.3 no preprint arXiv:0912.0902, que foi a versão lida; §5.)
- Gneiting, T.; Raftery, A. E. (2007). "Strictly Proper Scoring Rules, Prediction, and Estimation". *JASA*, 102(477), 359–378. DOI: 10.1198/016214506000001437. (§1 Eq. (1) p. 360; §4.2 p. 367; §6.1 Eq. (41) e §6.2 Eq. (43) p. 370; §6.3 Table 2; §9.3 p. 376.)
- Christoffersen, P. F. (1998). "Evaluating Interval Forecasts". *International Economic Review*, 39(4), 841–862. DOI: 10.2307/2527341. (Definitions 1–3 pp. 843–844; §3.1–§3.3 pp. 844–847; §4.2 pp. 848–849; §4.3 pp. 849–850; §5.1 pp. 850–853; Apêndice p. 861.)
- Kupiec, P. H. (1995). "Techniques for Verifying the Accuracy of Risk Measurement Models". *Journal of Derivatives*, 3(2), 73–84. (Lido na versão FEDS Working Paper 95-24, Federal Reserve Board: pp. 7–9, fns. 8–9; expressão (2) p. 12; expressão (6) p. 20 e (8) p. 24; pp. 20–23; Table 2 p. 32. Numeração da versão de periódico `[CITAÇÃO-NÃO-ACESSADA]`.)
- Khosravi, A.; Nahavandi, S.; Creighton, D.; Atiya, A. F. (2011a). "Lower Upper Bound Estimation Method for Construction of Neural Network-Based Prediction Intervals". *IEEE Transactions on Neural Networks*, 22(3), 337–346. DOI: 10.1109/TNN.2010.2096824. `[CITAÇÃO-NÃO-ACESSADA]` (PICP/MPIW/NMPIW/CWC verificados via Pearce et al. 2018 §3.)
- Khosravi, A.; Nahavandi, S.; Creighton, D.; Atiya, A. F. (2011b). "Comprehensive Review of Neural Network-Based Prediction Intervals and New Advances". *IEEE Transactions on Neural Networks*, 22(9), 1341–1356. DOI: 10.1109/TNN.2011.2162110. `[CITAÇÃO-NÃO-ACESSADA]`.
- Chernozhukov, V.; Fernández-Val, I.; Galichon, A. (2010). "Quantile and Probability Curves Without Crossing". *Econometrica*, 78(3), 1093–1125. DOI: 10.3982/ECTA7880. (Proposition 4, §2.4; lido em arXiv:0704.3649.)
- White, H. (2000). "A Reality Check for Data Snooping". *Econometrica*, 68(5), 1097–1126. DOI: 10.1111/1468-0262.00152. (Abstract p. 1097; §1 pp. 1098–1099; §2 pp. 1101–1102; §2.c p. 1104.)
- Romano, J. P.; Wolf, M. (2005). "Stepwise Multiple Testing as Formalized Data Snooping". *Econometrica*, 73(4), 1237–1282. DOI: 10.1111/j.1468-0262.2005.00615.x. (Lido na versão working paper de fev. 2005: §1, §3, §4; paginação publicada não verificada.)
- Koenker, R. (2005). *Quantile Regression*. Econometric Society Monographs No. 38, Cambridge University Press. DOI: 10.1017/CBO9780511754098. (Cap. 1.)
- Gneiting, T.; Ranjan, R. (2011). "Comparing Density Forecasts Using Threshold- and Quantile-Weighted Scoring Rules". *Journal of Business & Economic Statistics*, 29(3), 411–422. DOI: 10.1198/jbes.2010.08110. (Eq. (6); §3.1 Eq. (13) e texto após Eq. (17); Eqs. (22)–(23). Lido no UW Technical Report 533.)
- McNeil, A. J.; Frey, R.; Embrechts, P. (2005). *Quantitative Risk Management: Concepts, Techniques and Tools*. Princeton University Press. (Definition 2.10 §2.2.2 — confirmada nos slides oficiais dos autores, © 2005; página do livro `[CITAÇÃO-NÃO-ACESSADA]`; Eq. (2.19)/Example 2.14 pp. 39–40 já ratificados.)
- Hyndman, R. J.; Athanasopoulos, G. (2021). *Forecasting: Principles and Practice*, 3rd ed., OTexts (otexts.com/fpp3). (§5.10 "Time series cross-validation": avaliação em origem rolante, acurácia por horizonte.)
- Tashman, L. J. (2000). "Out-of-sample tests of forecasting accuracy: an analysis and review". *International Journal of Forecasting*, 16(4), 437–450. DOI: 10.1016/S0169-2070(00)00065-0. `[CITAÇÃO-NÃO-ACESSADA]` (abstract verificado; a leitura "acurácia por lead time" está inferida).
- Bergmeir, C.; Benítez, J. M. (2012). "On the use of cross-validation for time series predictor evaluation". *Information Sciences*, 191, 192–213. DOI: 10.1016/j.ins.2011.12.028. `[CITAÇÃO-NÃO-ACESSADA quanto a horizontes]`.
- Raschka, S. (2018). "Model Evaluation, Model Selection, and Algorithm Selection in Machine Learning". arXiv:1811.12808. (§1.1; §3.3 pp. 22–23; §3.9 p. 30; §4.5 p. 38.)
- Bouthillier, X.; Delaunay, P.; Bronzi, M.; et al. (2021). "Accounting for Variance in Machine Learning Benchmarks". *Proceedings of Machine Learning and Systems (MLSys)*, 3, 747–769. arXiv:2103.03098. (§1, §2, §5.)
- Nosek, B. A.; Ebersole, C. R.; DeHaven, A. C.; Mellor, D. T. (2018). "The preregistration revolution". *PNAS*, 115(11), 2600–2606. DOI: 10.1073/pnas.1708274114. (Seções "Preregistration Distinguishes Prediction and Postdiction", "Standard Tools of Statistical Inference Assume Prediction", "Challenge 1–3"; lido em PMC, paginação do PDF não visível.)
- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple Rules for Reproducible Computational Research". *PLOS Computational Biology*, 9(10), e1003285. DOI: 10.1371/journal.pcbi.1003285.
- Gu, S.; Kelly, B.; Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning". *The Review of Financial Studies*, 33(5), 2223–2273. DOI: 10.1093/rfs/hhaa009. (p. 2246, via modeling §3.1.)

### 11.2 Novas deste doc

Scoring e calibração:

- Bracher, J.; Ray, E. L.; Gneiting, T.; Reich, N. G. (2021). "Evaluating epidemic forecasts in an interval format". *PLOS Computational Biology*, 17(2), e1008618. DOI: 10.1371/journal.pcbi.1008618. arXiv:2005.12881v3. (§2.2 IS e decomposição; Eqs. (1)–(4) WIS; §4.1; Appendix A Eq. (5) IS_α = (QS_{α/2} + QS_{1−α/2})/α, Eq. (6) CRPS ≈ média de QS.)
- Berrisch, J.; Ziel, F. (2023). "CRPS learning". *Journal of Econometrics*, 237(2), 105221. DOI: 10.1016/j.jeconom.2021.11.008. arXiv:2102.00968v3. (§3.1 Eqs. (7)–(9); §3.4 quantile crossing.)
- Zamo, M.; Naveau, P. (2018). "Estimation of the Continuous Ranked Probability Score with Limited Information and Applications to Ensemble Weather Forecasts". *Mathematical Geosciences*, 50(2), 209–234. DOI: 10.1007/s11004-017-9709-7. (§2 estimadores INT/NRG/PWM/Fair, Eq. (2); §3.2 ensemble de quantis; §3.2.3 ties; Fig. 7.)
- Laio, F.; Tamea, S. (2007). "Verification tools for probabilistic forecasts of continuous hydrological variables". *Hydrology and Earth System Sciences*, 11(4), 1267–1277. DOI: 10.5194/hess-11-1267-2007. (Eqs. (11)–(14) pp. 1271–1272.)
- Gneiting, T.; Balabdaoui, F.; Raftery, A. E. (2007). "Probabilistic forecasts, calibration and sharpness". *Journal of the Royal Statistical Society: Series B*, 69(2), 243–268. DOI: 10.1111/j.1467-9868.2007.00587.x. (§1 pp. 245–246; Definition 1 p. 247; §2.4 p. 249; §3.1 Theorem 2 p. 252; §3.3 p. 255; Tables 3–4.)
- Gneiting, T.; Resin, J. (2023). "Regression diagnostics meets forecast evaluation: conditional calibration, reliability diagrams, and coefficient of determination". *Electronic Journal of Statistics*, 17(2), 3226–3286. DOI: 10.1214/23-EJS2180. arXiv:2108.03210v3. (Definition 2.7; Definition 2.9 / Eq. (9); §3; Appendix B.)
- Bröcker, J.; Smith, L. A. (2007). "Increasing the Reliability of Reliability Diagrams". *Weather and Forecasting*, 22(3), 651–661. DOI: 10.1175/WAF993.1. (§2–§3 consistency bars, binomial.)
- Kuleshov, V.; Fenner, N.; Ermon, S. (2018). "Accurate Uncertainties for Deep Learning Using Calibrated Regression". *Proceedings of the 35th ICML*, PMLR 80, 2796–2804. (§3.1 Eq. (3); §3.5 Eqs. (8)–(10).)
- Askanazi, R.; Diebold, F. X.; Schorfheide, F.; Shin, M. (2018). "On the Comparison of Interval Forecasts". *Journal of Time Series Analysis*, 39(6), 953–965. DOI: 10.1111/jtsa.12426. (Lido na versão working paper: §2.1 e nota 1; §3.1 Casella paradox; §3.2.2; paginação da JTSA não conferida.)
- Brehmer, J. R.; Gneiting, T. (2021). "Scoring interval forecasts: Equal-tailed, shortest, and modal interval". *Bernoulli*, 27(3), 1993–2010. DOI: 10.3150/20-BEJ1298. arXiv:2007.05709v2. (§3.2 Eqs. (4)–(6), Theorem 3.1; numeração da versão Bernoulli não conferida.)
- Pearce, T.; Brintrup, A.; Zaki, M.; Neely, A. (2018). "High-Quality Prediction Intervals for Deep Learning: A Distribution-Free, Ensembled Approach". *Proceedings of the 35th ICML*, PMLR 80, 4075–4084. (§3 Eqs. (4)–(7); Eq. (16); hipótese iid/Binomial.)
- Gasthaus, J.; Benidis, K.; Wang, Y.; Rangapuram, S. S.; Salinas, D.; Flunkert, V.; Januschowski, T. (2019). "Probabilistic Forecasting with Spline Quantile Function RNNs". *Proceedings of AISTATS*, PMLR 89, 1901–1910. (§2.2 Eq. (5); §3 Eqs. (10)–(11).)
- Winkler, R. L. (1972). "A Decision-Theoretic Approach to Interval Estimation". *JASA*, 67(337), 187–191. DOI: 10.1080/01621459.1972.10481224. `[CITAÇÃO-NÃO-ACESSADA]` (origem do interval score; atribuição via GR 2007 §6.2 e Brehmer & Gneiting §3.2.)
- Gneiting, T.; Katzfuss, M. (2014). "Probabilistic Forecasting". *Annual Review of Statistics and Its Application*, 1, 125–151. DOI: 10.1146/annurev-statistics-062713-085831. `[CITAÇÃO-NÃO-ACESSADA]` (nada load-bearing depende dela.)
- Bröcker, J. (2012). "Evaluating raw ensembles with the continuous ranked probability score". *Quarterly Journal of the Royal Meteorological Society*, 138(667), 1611–1617. DOI: 10.1002/qj.1891. `[CITAÇÃO-NÃO-ACESSADA]` (níveis "ótimos" (i − 0.5)/M, via Zamo & Naveau §3.2.1.)
- Lorentz, G. G. (1953). "An inequality for rearrangements". *American Mathematical Monthly*, 60(3), 176–179. `[CITAÇÃO-NÃO-ACESSADA]` (desigualdade de rearranjo usada por CFG 2010 Prop. 4 e pela derivação de §2.2.)
- Casella, G.; Hwang, J. T. G.; Robert, C. (1993). "A paradox in decision-theoretic interval estimation". *Statistica Sinica*, 3(1), 141–155. `[CITAÇÃO-NÃO-ACESSADA]` (via GR 2007 §9.3 e Askanazi et al.)

Inferência pareada:

- Diebold, F. X. (2015). "Comparing Predictive Accuracy, Twenty Years Later: A Personal Perspective on the Use and Abuse of Diebold–Mariano Tests". *Journal of Business & Economic Statistics*, 33(1), 1–9. DOI: 10.1080/07350015.2014.983236. (§2.1 Eqs. (1)–(2) p. 2; §2.2 p. 2; §3.1–§3.5 pp. 3–5; §7 p. 8.)
- Newey, W. K.; West, K. D. (1987). "A Simple, Positive Semi-Definite, Heteroskedasticity and Autocorrelation Consistent Covariance Matrix". *Econometrica*, 55(3), 703–708. DOI: 10.2307/1913610. `[CITAÇÃO-NÃO-ACESSADA]` (pesos de Bartlett 1 − j/(m+1) inferidos das implementações verificadas em R e statsmodels.)
- Newey, W. K.; West, K. D. (1994). "Automatic Lag Selection in Covariance Matrix Estimation". *Review of Economic Studies*, 61(4), 631–653. `[CITAÇÃO-NÃO-ACESSADA]` (regra floor(4(T/100)^{2/9}), default do statsmodels; fork não adotado.)
- Andrews, D. W. K. (1991). "Heteroskedasticity and Autocorrelation Consistent Covariance Matrix Estimation". *Econometrica*, 59(3), 817–858. `[CITAÇÃO-NÃO-ACESSADA]` (citado por DM 1995 p. 254; fork não adotado.)
- Politis, D. N.; Romano, J. P. (1994). "The Stationary Bootstrap". *JASA*, 89(428), 1303–1313. DOI: 10.1080/01621459.1994.10476870. `[CITAÇÃO-NÃO-ACESSADA]` (semântica confirmada em Politis & White 2004 §2 e nas docs do backend.)
- Politis, D. N.; White, H. (2004). "Automatic Block-Length Selection for the Dependent Bootstrap". *Econometric Reviews*, 23(1), 53–70. DOI: 10.1081/ETC-120028836. (§2 pp. 55–56; §3.2 Eq. (6) p. 57; Eqs. (11)–(14) p. 60.)
- Patton, A.; Politis, D. N.; White, H. (2009). "Correction to 'Automatic Block-Length Selection for the Dependent Bootstrap'". *Econometric Reviews*, 28(4), 372–375. `[CITAÇÃO-NÃO-ACESSADA]` (citada nas docs do backend.)
- Giacomini, R.; White, H. (2006). "Tests of Conditional Predictive Ability". *Econometrica*, 74(6), 1545–1578. DOI: 10.1111/j.1468-0262.2006.00718.x. (Lido na versão working paper UCSD abr. 2003 / Boston College WP 572: §3.2 comentário 2; §3.3. Paginação publicada não verificada.)
- Clark, T. E.; McCracken, M. W. (2011). Citado por Diebold 2015 §3.4 (p. 4) — modelos aninhados, hipótese local-a-zero. `[CITAÇÃO-NÃO-ACESSADA]`; **referência bibliográfica completa não verificada** (a lista de referências do PDF de Diebold 2015 não extraiu legivelmente) — confirmar antes de registrar no overview §10.

Backtests e pré-registro:

- Diebold, F. X.; Gunther, T. A.; Tay, A. S. (1998). "Evaluating Density Forecasts with Applications to Financial Risk Management". *International Economic Review*, 39(4), 863–883. DOI: 10.2307/2527342. (§3 pp. 867–869; §6 pp. 880–881.)
- Christoffersen, P. F.; Diebold, F. X. (2000). "How Relevant is Volatility Forecasting for Financial Risk Management?". *Review of Economics and Statistics*, 82(1), 12–22. DOI: 10.1162/003465300558597. (Lido no NBER WP 6844, 1998: §2; §3 fn. 14.)
- Christoffersen, P.; Pelletier, D. (2004). "Backtesting Value-at-Risk: A Duration-Based Approach". *Journal of Financial Econometrics*, 2(1), 84–108. DOI: 10.1093/jjfinec/nbh004. (Lido no CIRANO WP 2003s-05: abstract; §2; §4.1 p. 7; §4.3 pp. 8–9; §5 p. 11.)
- Brown, L. D.; Cai, T. T.; DasGupta, A. (2001). "Interval Estimation for a Binomial Proportion". *Statistical Science*, 16(2), 101–133. DOI: 10.1214/ss/1009213286. (Abstract p. 101; Eq. (1) p. 103; §3.1.1 Eq. (4) p. 107.)
- Wilson, E. B. (1927). "Probable Inference, the Law of Succession, and Statistical Inference". *JASA*, 22(158), 209–212. DOI: 10.1080/01621459.1927.10502953. `[CITAÇÃO-NÃO-ACESSADA]` (origem do intervalo; via BCD 2001.)
- Basel Committee on Banking Supervision (1996). *Supervisory framework for the use of "backtesting" in conjunction with the internal models approach to market risk capital requirements*. Bank for International Settlements, jan. 1996. (§III(b)–(c), pp. 6–8. Documento oficial, bis.org.)
- ICH (1998). *ICH Harmonised Tripartite Guideline E9: Statistical Principles for Clinical Trials*. CPMP/ICH/363/96 (EMA). (§2.2.2 pp. 7–8; §3.3.2 pp. 17–18; §4.2 p. 21; §5.1 pp. 23–24; §5.2 p. 24; §5.3 pp. 26–27; §5.5 p. 28. Documento oficial, EMA.)
- Simmons, J. P.; Nelson, L. D.; Simonsohn, U. (2011). "False-Positive Psychology: Undisclosed Flexibility in Data Collection and Analysis Allows Presenting Anything as Significant". *Psychological Science*, 22(11), 1359–1366. DOI: 10.1177/0956797611417632. (p. 1359; Table 1 p. 1361; requisitos pp. 1362–1363; Guideline 3 p. 1363.)
- Wagenmakers, E.-J.; Wetzels, R.; Borsboom, D.; van der Maas, H. L. J.; Kievit, R. A. (2012). "An Agenda for Purely Confirmatory Research". *Perspectives on Psychological Science*, 7(6), 632–638. DOI: 10.1177/1745691612463078. (Abstract p. 632; p. 635.)
- Chambers, C. D. (2013). "Registered Reports: A new publishing initiative at Cortex". *Cortex*, 49(3), 609–610. DOI: 10.1016/j.cortex.2012.12.016. `[CITAÇÃO-NÃO-ACESSADA]` (suplementar.)
- Engle, R. F.; Manganelli, S. (2004). "CAViaR: Conditional Autoregressive Value at Risk by Regression Quantiles". *JBES*, 22(4), 367–381. DOI: 10.1198/073500104000000370. `[CITAÇÃO-NÃO-ACESSADA]` (apontador: teste DQ, parente da regressão de hits; fork não adotado.)

### 11.3 Documentação de biblioteca (mecânica, não teoria) — e o que o oráculo precisa neutralizar

- **scikit-learn** — `sklearn.metrics.mean_pinball_loss(y_true, y_pred, *, sample_weight=None, alpha=0.5, multioutput='uniform_average')` (código `sklearn/metrics/_regression.py`, branch main; User Guide §"Pinball loss"). Implementa exatamente ρ_τ com `alpha` = **nível τ** (sem fator 2); "equivalent to half of mean_absolute_error when alpha = 0.5" (User Guide). Restrição: `alpha` é float **único** — para K níveis o oráculo é chamado K vezes; `multioutput` agrega saídas com o mesmo alpha. Fixtures oficiais: y_true = [1, 2, 3], y_pred = [0, 2, 3], alpha = 0.1 → 0,0333…; y_pred = [1, 2, 4], alpha = 0.1 → 0,3. Neutralizar: nada (mesma escala do projeto).
- **scoringrules 0.11.0** — `quantile_score(obs, fct, alpha)` = (1{y < q} − τ)(q − y) = ρ_τ exatamente, `alpha` = nível, aceita vetor; `crps_quantile(obs, fct, alpha)` = (2/|Q|) Σ pinball com **pesos iguais** sobre os níveis passados, sem ordenação, sem interpolação, `alpha` ∈ (0,1) estrito, `fct.shape[-1] == alpha.shape[-1]` — identidade `crps_quantile == 2 × pinball média na grade` (conferida < 1e−15), logo **não** é oráculo independente do sklearn; `interval_score(obs, lower, upper, alpha)` = GR 2007 Eq. (43) com `alpha` = **miscobertura** (0.04 para 96 %), desigualdades **estritas** (y = l ou y = u ⇒ dentro), `alpha` pode ser array; `weighted_interval_score(obs, median, lower, upper, alpha, w_median=None, w_alpha=None)` — defaults do **código** `w_alpha = alpha/2`, `w_median = 0.5` (idênticos a Bracher Eqs. (1)–(2); a **docstring** diz 2/α_k, mas o código usa α/2); o termo da mediana **depende do backend**: com numba (default quando instalado) a lib calcula |y − m| internamente; com numpy/jax/torch usa `w_median * median` sem |·| (bug). Neutralizar: fator 2 no CRPS; `alpha` = miscobertura no IS; se o WIS for usado como identidade de teste, fixar `backend` explicitamente e passar `median = m` (numba) ou `median = |y − m|` (numpy) — ou dispensar a função e testar WIS ≡ CRPS_Q direto via `crps_quantile`.
- **statsmodels** — `stats.multitest.multipletests(pvals, alpha=0.05, method='holm', …)`: rejeita se p_(i) ≤ α/(m − i + 1) (≤, como Holm), step-down, `pvals_corrected = maximum.accumulate(pvals * arange(m, 0, −1))` truncado em 1; a correção "is independent of the alpha specified". `OLSResults.get_robustcov_results(cov_type='HAC', maxlags=m, kernel='bartlett'|'uniform', use_correction=True)` (código `stats/sandwich_covariance.py`): `weights_bartlett` = 1 − k/(m+1) (com m = h−1: 1 − k/h, idêntico ao "bartlett" do R); `weights_uniform` = 1 (janela retangular DM 1995 / "acf" do R); `nlags=None` → floor(4(T/100)^{2/9}); `use_correction=True` multiplica por T/(T−1) — coincide com o fator HLN em h = 1 e **difere** para h > 1 ("just guessing on correction factor, need reference"), por isso fica desligado em todo h e o HLN é aplicado por fora; `use_t=False` → p-valores pela normal. Neutralizar: `kernel='uniform'`, `maxlags=h−1`, `use_correction=False`, aplicar o fator HLN e a t_{T−1} por fora; o estimador pressupõe "a single time series with zero axis consecutive, equal spaced".
- **arch** — `arch.bootstrap.MCS(losses, size, reps=1000, block_size=None, method='R', bootstrap='stationary', *, seed=None)` (código `arch/bootstrap/multiple_comparison.py`): `losses` T × k completa; `block_size=None` → int(√T) ("should be provided and chosen to be appropriate for the data"); `method='R'`: d̄_ij = L̄_i − L̄_j, var̂ por bootstrap calculada **uma vez** com os mesmos índices reutilizados, estatística max t_ij, elimina o i do par que atinge o máximo (= e_R,M); `method='max'`: var recalculada a cada passo, elimina arg max t_i· (= e_max,M); p-valores = máximo cumulativo (= Definition 4 de HLN 2011); `included` = modelos com p-valor **>** `size` (HLN Theorem 3 usa ≥ α — diferença só em empate exato); o aviso "estimated standard deviation of at least one loss difference was 0" existe **só** em `method='max'` — em `method='R'` só a diagonal da matriz de variâncias é protegida (`variances += np.eye(k)`), e duas colunas de perda idênticas dão `0/0 = NaN`, p-valor 0 e `IndexError` sem diagnóstico (validar var(L_i − L_j) > 0 antes de chamar — §6.5). `StationaryBootstrap(block_size)`: `block_size` = comprimento **médio** (Politis & Romano 1994); `optimal_block_length(x)` devolve `b_sb` e `b_cb` (Politis & White 2004 + Patton et al. 2009). Neutralizar: `size` = α_MCS, `seed` fixo e `reps` pré-registrados; bloco explícito; > vs ≥ na fronteira.
- **R `forecast::dm.test(e1, e2, alternative, h, power, varestimator)`** (código `R/DM2.R`; página de referência oficial): recebe **erros** e usa d = |e1|^power − |e2|^power — para testar um diferencial de **pinball**, passar as próprias séries de perda (≥ 0) como `e1`, `e2` com `power = 1`; autocovariâncias até h−1; `varestimator = "acf"` (default) = janela retangular (γ̂_0 + 2Σγ̂_k)/n; `"bartlett"` = pesos 1 − k/h; se a variância for ≤ 0 com h > 1: aviso "Variance is negative. Try varestimator = bartlett. Proceeding with horizon h=1" e **recalcula com h = 1**; estatística × fator HLN ((n + 1 − 2h + h(h−1)/n)/n)^{1/2}; p-valor com **t de Student, df = n − 1**; variância ≤ 0 com h = 1 ⇒ `stop("Variance of DM statistic is zero")` (erro, não fallback); `alternative = "less"` = "method 2 is less accurate than method 1" ⇔ com e1 = candidato, H1 "candidato melhor". Neutralizar: nada além de `power = 1` e da convenção de sinal; é o oráculo que fixa retangular + HLN + t_{n−1}.
- **R `rugarch::VaRTest(alpha = 0.05, actual, VaR, conf.level = 0.95)`** (man page; código `R/rugarch-tests.R`): `alpha` = **probabilidade de violação**; `VaR` = quantil de **retorno** (negativo na cauda inferior); hit = `actual < VaR` (estrito); `.LR.uc` sobre as T observações, com **produtos** de verossimilhanças (sub-fluxo a 0 e `NaN` para T de milhares — fixtures em T de centenas); `.LR.cc`: tabela de transições sobre T−1 pares, `stat.cc = stat.uc + stat.ind` (identidade só aproximada — LR_uc sobre T obs; O(1/T) se I_1 = 0, O(1) se I_1 = 1, §7.7); `0^0 = 1` ⇒ N11 = 0 funciona (= Christoffersen & Pelletier §4.1); `N10 + N11 = 0` ⇒ `p11 = NaN`; erro ("subscript out of bounds") sempre que algum símbolo {0, 1} falte em `head` ou em `tail` da série — zero violações, ou **uma única** violação em t = 1 ou t = T; saída: `expected.exceed = floor(alpha·TN)`, `actual.exceed`, `uc.LRstat`, `uc.LRp`, `cc.LRstat`, `cc.LRp` (não devolve LR_ind separado — derivar como cc − uc na convenção do R). Neutralizar: alimentar o oráculo com a série a partir de t = 2 para igualar a convenção pura (§7.7) — sem tolerância O(1/T); desigualdade estrita vs ≤ (§4.5); casos-limite como casos de domínio, não valores do oráculo.
