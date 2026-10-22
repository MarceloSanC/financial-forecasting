---
title: Reprodução, equivalência e relatório — teoria do Step 8 (corrida confirmatória, reprodução da corrida, auditoria de equivalência, plots canônicos e dossiê)
description: Teoria canônica do subdomínio reproduction-equivalence-and-reporting — o que a corrida confirmatória executa (por ponteiro), o que significa reproduzi-la a partir dos artefatos persistidos (bit a bit no mesmo ambiente, por classe entre ambientes), como se audita a equivalência com a evidência confirmatória anterior (tolerância numérica declarada no alvo e no código de métrica; nos números do modelo a tolerância é o sentido, com deltas documentados e divergência de sentido sem explicação registrada como finding), que estatuto e rótulo cada plot canônico carrega e o conteúdo mínimo do dossiê de rastreabilidade
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 8 (8.1–8.3), ao questionar o que a reprodução da corrida promete, qual tolerância vale entre ambientes, como comparar a pipeline oficial com a evidência anterior, que rótulo um gráfico do relatório leva, ou o que o dossiê final tem de listar
keywords: [domain, evaluation, reproducibility, reproduction, bitwise, tolerance, floating-point, ieee-754, rng-stream, equivalence-audit, prior-evidence, regression-oracle, storage-precision, metric-code-regression, tost, explained-divergence, scaffold-retirement, plots, reliability-diagram, quantile-score-plot, sharpness-diagram, picp-mpiw, dm-table, fan-chart, h3, conformal, traceability-dossier, sandve, per-horizon, editorial-policy]
status: accepted
created_at: 2026-10-22
updated_at: 2026-10-22
bounded_context: evaluation
subdomain: reproduction-equivalence-and-reporting
references:
  - ./probabilistic-forecast-evaluation.md
  - ../inference/conformal-benchmark-and-feature-attribution.md
  - ../modeling/quantile-model-training.md
  - ../../adr/0_0_0060-reproduction-equivalence-reporting-domain-doc-scope-and-boundary.md
  - ../../adr/0_0_0061-step-8-compares-own-run-reproduction-and-internal-prior-equivalence.md
  - ../../adr/0_0_0062-equivalence-tolerance-numeric-where-equality-expected-direction-for-model-numbers.md
  - ../../adr/0_0_0011-preregistration-invariants-and-h1-gate.md
  - ../../adr/6_4_0005-gold-full-refresh-per-cohort-partition.md
  - ../../adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md
  - ../../adr/6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md
  - ../../adr/6_5_0007-verdict-logical-form-and-decision-readiness.md
  - ../../adr/6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md
  - ../../adr/7_1_0003-reproduction-contract-strict-same-environment-tolerance-across.md
  - ../../adr/7_3_0005-h3-preregistration-r3-details.md
---

# Reprodução, equivalência e relatório — teoria do Step 8

> **Categoria `domain/`** ([ADR 0.0.0003](../../adr/0_0_0003-formalize-domain-and-audits-doc-categories.md)):
> este documento é a **teoria** (o quê/por quê) do subdomínio, transversal às
> Stages 8.1–8.3. Ele **não** é spec de implementação — não define schemas,
> caminhos de arquivo, nomes de classe nem cadências; isso pertence ao
> `technical.md` de cada Stage + código. Toda regra que muda um número ou um
> rótulo reportado carrega citação rastreável a fonte primária. Onde a fonte
> **não** foi lida em primária, a citação carrega `[CITAÇÃO-NÃO-ACESSADA]`;
> onde não existe fonte primária e a regra é política do projeto, o texto diz
> `[SEM-FONTE-PRIMÁRIA]` e a regra vira convenção (§9); contas e inferências
> feitas para este doc são marcadas como **derivação**. As bifurcações do
> gate foram triadas pela skill `evidence-resolution` (2026-10-22): as de
> classe E/C foram fechadas pelo agente e registradas em §9.1 no formato
> `[decision:E|C]`; as de classe P (o que a 8.2 compara — **B1**, ADR
> 0.0.0061; a tolerância declarada nos números do modelo — **B2**, ADR
> 0.0.0062) foram decididas pelo humano na issue #208 (2026-10-22), e a política editorial do TCC é
> decisão do humano anterior a este gate. Todas as convenções são anteriores
> a qualquer dado confirmatório (a 8.1 não rodou), então nenhuma C virou P.
> Rodadas de revisão: verificação adversarial de citações e revisão de
> completude (2026-10-22), aplicadas nesta versão (§9.2). Doc aceito em
> 2026-10-22 (`status: accepted`) — gate do Step 8.

## 1. Escopo e como consumir este doc

**Cobre** os três blocos do Step 8, todos sobre o mesmo objeto — a **geração
julgada**: o gold e o scorecard que a 8.1 produz do cohort persistido, por
horizonte (§2.1):

1. **corrida confirmatória (8.1)** — só ponteiros: o que ela executa e em que
   ordem teórica, e o que ela precisa registrar e preservar (§3, §4.5);
2. **reprodução e equivalência (8.2)** — (i) a **reprodução da própria
   corrida** a partir dos artefatos persistidos, que é o claim citável no TCC
   (§4); (ii) a **auditoria de equivalência** da pipeline oficial com a
   evidência confirmatória anterior, como auditoria interna do repositório
   (§5);
3. **plots canônicos e dossiê (8.3)** — o que cada gráfico representa, sua
   fonte e seu rótulo obrigatório (§6), e o conteúdo mínimo do dossiê de
   rastreabilidade (§7);

apoiados nos **fundamentos comuns** (§2), fechados pela **seção-fronteira**
(§8), pela tabela de convenções com o registro das decisões (§9) e pelas
referências (§10).

**Não cobre**:

- **Implementação** (onde a reprodução grava ou compara, schemas do relatório
  de equivalência e do dossiê, leitores da evidência anterior, biblioteca de
  plotagem, cores, eixos) → `technical.md` das Stages 8.1–8.3.
- **Toda a teoria do Step 6** (pinball, CRPS, IS, ĉ(τ), PICP/MPIW, Wilson,
  gate de degeneração, DM/HLN, Holm, MCS, Christoffersen, pré-registro, forma
  do veredito) → [doc de avaliação](./probabilistic-forecast-evaluation.md),
  por ponteiro, **sem re-derivação**.
- **Toda a teoria do Step 7** (contrato de reprodução da inferência, CQR,
  leitura de H3, rótulos de conformal e de H3) →
  [doc de inferência](../inference/conformal-benchmark-and-feature-attribution.md),
  por ponteiro.
- **Redação do TCC** (non-goal da 8.3) e dashboards interativos.

**Mapa de consumo** (que Stage lê o quê):

| Stage | Seções que consome |
|---|---|
| 8.1 — corrida confirmatória | §3 (ponteiros), §2.1–§2.2, §4.5 (o que a 8.1 precisa registrar e preservar), §7 (o que o dossiê vai pedir) |
| 8.2 — reprodução e auditoria de equivalência | §4 (reprodução), §5 (equivalência), §2 |
| 8.3 — plots canônicos e dossiê | §6 (plots), §7 (dossiê), §2.3 (rótulos), §2.4 |
| todas | §2 (fundamentos), §8 (fronteira), §9 (convenções) |

**Hierarquia de fontes.** Overview > Roadmap > Domain (este doc, o de
avaliação e o de inferência) > `concept.md` das Stages. O que já estava
ratificado no repo (overview §2–§4/§8/§10; evaluation §2/§4/§6/§8; inference
§3/§4.11/§5.7–§5.8/§7; ADRs 0.0.0011, 6.4.0005, 6.5.0003, 6.5.0006, 6.5.0007,
6.5.0008, 7.1.0003, 7.3.0005) é citado como tal e **não** re-derivado; a
pesquisa externa entrou só nas lacunas (garantias de ponto flutuante e dos
geradores aleatórios, equivalência sem margem), sob a barra de fontes do gate
(`PROMPT-step-single-session.md` §1). O texto do roadmap da 8.2 foi emendado
no mesmo PR, ancorado na decisão B1 do humano (ADR 0.0.0061).

**Política editorial (decisão do humano).** O texto do TCC **não menciona** o
projeto anterior. Consequência para este doc: a parte (i) da 8.2 (§4) e os
plots e o dossiê (§6–§7) entram no texto; a parte (ii) (§5) é **auditoria
interna**, registrada só no repositório, e cumpre ASSUM-4 / R-REPRO-1 do
overview sem virar claim do texto. Nenhum gráfico do relatório compara com a
evidência anterior.

## 2. Fundamentos comuns

### 2.1 O objeto: a geração julgada

A 8.1 lê o cohort persistido (predições de teste e de calibração no silver,
predições permutadas e cohort de ablação da 7.3), publica **uma geração de
gold** e computa o **scorecard** pela revisão ancorada mais recente da cadeia
do pré-registro (roadmap 8.1; ADRs 6.4.0005, 6.5.0003, 6.5.0007). Essa
geração — tabelas, manifesto e scorecard — é o **resultado julgado**: é o que
o dossiê identifica (§7), o que os plots desenham (§6) e aquilo contra o que a
reprodução é comparada (§4). Como um refresh novo do gold **substitui** a
geração viva da partição (ADR 6.4.0005 itens 4–5: `current/` é trocado e a
geração anterior apagada), a geração julgada tem de ser **preservada** pela
8.1 antes de qualquer outro refresh, e a reprodução roda em **destino
separado** (§4.5–§4.6).

### 2.2 Três camadas de um artefato: entrada, resultado, proveniência

Todo artefato da cadeia tem três tipos de campo, e cada um tem um tratamento
diferente na reprodução e no dossiê:

| Camada | Exemplos | Papel | Na reprodução |
|---|---|---|---|
| **identidade da entrada** | hash do cohort, `preregistration_ref` e hash de cada revisão r0–r3, `feature_set_hash`, `split_fingerprint`, `config_signature`, fingerprint do dataset, `run_id`, **hash de conteúdo das tabelas do silver lidas** (exigido da 8.1 — §4.5) | prova **qual** entrada foi usada | têm de ser **iguais** — senão não é reprodução, é outra corrida |
| **resultado** | valores das tabelas gold por chave, campos do scorecard, contagens, decisões | o que se afirma | comparados bit a bit ou por tolerância (§4.2–§4.3) |
| **proveniência** | timestamps, id da geração, host, URL do comentário de âncora | quando/onde foi feito | **esperado que difiram**; excluídos da comparação, registrados no dossiê |

O hash de conteúdo do silver precisa ser **acrescentado** à identidade: hoje o
gold não o grava (ADR 6.4.0005 item 9: "No content hash of the silver in this
Stage … 8.1 may add a content hash"), e o `run_id` não carrega impressão
digital do conteúdo do dado (roadmap 8.1, nota da issue #163). Sem ele, "as
predições lidas são as mesmas" não é conferível.

Um hash **identifica** uma entrada, não certifica um resultado: igualdade de
hash prova que a reprodução partiu do mesmo dado e da mesma configuração; a
igualdade do resultado é o que a reprodução testa (**derivação**, a partir da
Rule 1 de Sandve et al. 2013: "For every involved step, you should ensure that
every detail that may influence the execution of the step is recorded … the
critical details include the name and version of the program, as well as the
exact parameters and inputs that were used").

### 2.3 Estatuto de cada número: confirmatório, descritivo, exploratório

Toda tabela e todo gráfico do Step 8 declara o estatuto do que mostra, com
**três** rótulos (convenção **P8-ROT**, §9.1):

- **confirmatório** — só os elementos da árvore de decisão pré-registrada
  (evaluation §8.6; ADR 6.5.0007), **nos horizontes em que se aplicam**: o
  gate H1 (cada cauda do par primário na banda de Wilson 97,5 % + taxa de
  degeneração ≤ limiar, na variante do ADR 6.5.0006, com o poder declarado),
  as decisões de Holm na família do horizonte e a pertença ao MCS ao nível
  α_MCS **só onde H1 passa** (onde H1 reprova, H2 é "não aplicável" e esses
  números são perfil), o desfecho de H2, o vencedor primário e o critério
  "≥ 1 horizonte". Base: "Only results from analyses envisaged in the
  protocol (including amendments) can be regarded as confirmatory" (ICH E9
  §5.1, via evaluation §8.1);
- **descritivo** — o que o pré-registro declara mas que **nunca troca o
  veredito**: o perfil (ADR 6.5.0008; evaluation §8.6), a leitura de H3 (regra
  mecânica com conclusão descritiva — inference §5.8, C7) e o benchmark
  conformal (inference §4.11, B8). H3 e conformal carregam, além disso, a
  frase obrigatória do seu doc: linguagem estritamente descritiva (H3) e
  **"cobertura empírica (não garantida)"** (conformal);
- **exploratório** — tudo o que **não** está declarado no pré-registro: "Other
  analyses can be carried out but these should be labeled 'exploratory'"
  (Wagenmakers et al. 2012, p. 632, via evaluation §8.3).

Um gráfico que mistura estatutos rotula **cada elemento** (§6.2).

### 2.4 Por horizonte, seeds como réplicas (ponteiro)

Toda grandeza deste doc é **por horizonte**, nunca agregada entre horizontes
(overview §7; evaluation §2.7, §8.7). Seeds são réplicas do mesmo ponto
alinhado: perdas entram como média ponto a ponto, coberturas como média entre
seeds com n ≈ T, e a dispersão entre seeds é perfil (evaluation §6.9, §8.4;
B-SEEDS). O GBM é determinístico e entra com uma execução; os baselines não
têm seed (evaluation §6.9).

## 3. A corrida confirmatória (Stage 8.1) — ponteiros

A 8.1 **não tem teoria própria**; ela executa, em ordem, o que os docs de
avaliação e de inferência já fixaram. A ordem teórica, com a fonte de cada
passo:

| # | Passo | Regra | Fonte |
|---|---|---|---|
| 1 | Cohort congelado e treinado; cohort de ablação congelado e treinado | o que se treina tem hash próprio | evaluation §8.2 (B-ORDEM); ADRs 5.5.0001, 7.3.0003 |
| 2 | Cadeia do pré-registro ancorada (r0 → r1 → r2 → r3); julga-se pela revisão ancorada mais recente | como se julga é congelado e hasheado **antes** de qualquer métrica confirmatória | evaluation §8.1–§8.2; ADRs 6.5.0002, 6.5.0003, 7.2.0001, 7.3.0005 |
| 3 | Insumos completos: calib (7.1, idempotente), predições permutadas e VSN (7.3) | ver predições não viola o cegamento; computar métricas viola | inference §7; evaluation §8.2 |
| 4 | Uma geração de gold, iniciada **depois** da âncora da revisão julgada | `academic_decision_ready` exige a ordem | ADRs 6.4.0005, 6.5.0003, 6.5.0007 |
| 5 | Veredito **por horizonte**: H1 (gate, só o candidato) → H2 (i) supera os naive, (ii) supera/empata os fortes, (iii) MCS complementar → vencedor primário | árvore pré-registrada aplicada mecanicamente; perfil nunca troca o veredito | evaluation §8.5–§8.8 (B-GATE-H1, conv. 26–28); ADRs 6.5.0006, 6.5.0007, 6.5.0010 |
| 6 | H3: regra de leitura mecânica (C4 + C5), conclusão descritiva, **separada** de H1 → H2 | não altera o veredito | inference §5.7–§5.8; ADRs 0.0.0007, 7.3.0005 |
| 7 | Conformal como eixo comparativo descritivo, mesmas definições de cobertura | "cobertura empírica (não garantida)"; nenhum teste novo | inference §4.11 (B8), §4.13; ADR 0.0.0008 |
| 8 | Critério de sucesso do estudo: "≥ 1 horizonte" com H1 não rejeitado, com o poder declarado | não é agregação | evaluation §8.8 (T11); overview §4 |

O que a 8.1 precisa **registrar e preservar** para que a 8.2 consiga
reproduzi-la e a 8.3 consiga documentá-la está em §4.5 e §7 — é a única
contribuição deste doc à 8.1.

## 4. Reprodução da própria corrida (Stage 8.2, parte i)

### 4.1 O que é reproduzir a corrida

Reproduzir a 8.1 é **re-executar a cadeia silver → gold → scorecard** a partir
dos artefatos persistidos (cohort, pré-registro, silver), **sem re-treino**
(overview §4, critério "Reprodutibilidade"; roadmap 8.1 DoD), num **destino
separado**, e comparar o resultado com a geração julgada preservada (§2.1)
campo a campo, na camada "resultado" (§2.2). A reprodução das **predições** a
partir dos checkpoints já foi provada na 7.1 — 60 runs em modo `strict` com
max |Δ| = 0 (ADR 7.1.0003; roadmap, histórico de 2026-10-12) — e não é
repetida como claim aqui; ela é o elo anterior da mesma corrente.

A reprodução é o **claim citável** do Step 8 no TCC: "a evidência julgada é
reconstruída, a partir dos dados persistidos e no ambiente registrado, bit a
bit" (decisão B1 do humano; ADR 0.0.0061; roadmap 8.2 emendado). O motivo de
o claim ser **exatidão** e não "aproximação" é o da Rule 6 de Sandve et al.
(2013): "There is a large difference between observing that a result has been
reproduced exactly or only approximately. While achieving equal results is a
strong indication that a procedure has been reproduced exactly, it is often
hard to conclude anything when achieving only approximately equal results."
O non-goal "bit-identical" do roadmap refere-se à comparação com a evidência
**anterior** (§5), não a esta.

### 4.2 No mesmo ambiente: bit a bit (R-BIT — evidência)

**Decisão (R-BIT, classe E, §9.1).** Com a mesma entrada (camada de
identidade igual), o **mesmo caminho de cálculo** (abaixo) e o **mesmo
ambiente pinado** — as chaves não-código do ambiente registradas pelo ADR
7.1.0003 (imagem, versões de interpretador e bibliotecas, plataforma,
`machine/cpu_count`), **mais** a mesma capacidade de CPU, que aquele ADR
registra mas não usa como chave (ADR 7.1.0003, contexto e item 2) e que aqui
entra porque o NumPy só promete o fluxo aleatório "on the same machine"
(abaixo) —, **todo** campo da camada "resultado" tem de sair **igual bit a bit**, inclusive
os que dependem de números aleatórios. As fontes:

- **Aritmética.** "The IEEE standard requires that the result of addition,
  subtraction, multiplication and division be exactly rounded. That is, the
  result must be computed exactly and then rounded to the nearest
  floating-point number (using round to even)"; e "the IEEE standard also
  specifies that square root, remainder, and conversion between integer and
  floating-point be correctly rounded" (Goldberg 1991, §The IEEE Standard,
  subseção *Operations* — já ratificado, inference §3.1). A mesma sequência de
  operações sobre as mesmas entradas dá, portanto, os mesmos bits. As entradas
  do silver são lidas exatamente (float64 de float32 — ida e volta exata; ADR
  7.1.0003).
- **Funções transcendentais.** "The IEEE standard does not require
  transcendental functions to be exactly rounded because of the table maker's
  dilemma" (Goldberg 1991, mesma subseção). No caminho do gold, as
  transcendentais (log, exp, gamma incompleta das distribuições t e χ², quantil
  normal do Wilson) são do **domínio stdlib** do projeto (overview §6; ADRs
  0.0.0020, 0.0.0056 — a t do DM pela beta incompleta da NIST DLMF §8.17,
  evaluation §11.2), logo passam pelo módulo `math`, que "consists mostly of
  thin wrappers around the platform C math library functions" (Python 3.12,
  `library/math`, nota *impl-detail*); a única biblioteca numérica consumida
  pelo refresh do gold é a do MCS (índices de bootstrap e b̂_sb — ADR
  6.4.0008). No **mesmo** ambiente a biblioteca C e o build são os mesmos, logo
  a mesma chamada dá o mesmo resultado (**derivação**: função determinística
  do mesmo binário); entre ambientes, não (§4.3).
- **Números aleatórios** (bootstrap do MCS, Monte Carlo do Christoffersen,
  permutações e bootstrap de H3): o NumPy promete o mesmo fluxo "with the same
  `BitGenerator`, with the same seed, perform the same sequence of method calls
  with the same arguments, on the same build of numpy, in the same
  environment, on the same machine" (NumPy 2.5.0, *Compatibility policy*); o
  `random` do Python: "By reusing a seed value, the same sequence should be
  reproducible from run to run as long as multiple threads are not running"
  (Python 3.12, `library/random`, *Notes on Reproducibility*). As seeds são
  pré-registradas (ADRs 6.5.0009, 7.3.0005) — a Rule 6 de Sandve: "given the
  same initial seed, all random numbers used in an analysis will be equal,
  thus giving identical results every time it is run".

**Mesmo caminho de cálculo, commit posterior (R-BIT-COMMIT).** A reprodução da
8.2 roda num commit **posterior** ao da 8.1. Como no ADR 7.1.0003 (as chaves de
código ficam fora da escolha do modo), o commit não decide o critério; decide
o **diff** entre o commit da geração julgada e o da reprodução:

- se o diff **não toca** o caminho de cálculo da cadeia silver → gold →
  scorecard (o código-fonte do projeto executado pelo refresh e pelo
  scorecard), o critério continua **bit a bit**;
- se o diff **toca** esse caminho, a reprodução é registrada como
  `[deviation]` com o diff, e a diferença, se houver, é diagnosticada; o
  claim do TCC só vale para a reprodução feita com o caminho de cálculo da
  geração julgada (o que pode exigir re-executar no commit dela). As
  dependências de terceiros **não** fazem parte do caminho de cálculo: uma
  mudança no lock é mudança de **ambiente** e cai em §4.3, coerente com o ADR
  7.1.0003 (versões de biblioteca são chaves de ambiente, não de código).

**Falha no mesmo ambiente é parada para diagnóstico, não troca de critério.**
Se algum campo de resultado difere com as condições acima satisfeitas, algo
que as chaves não capturam mudou: registra-se um `[finding]` e diagnostica-se
antes de qualquer uso da geração reproduzida. Uma tolerância **não** é usada
para "salvar" uma falha não diagnosticada (ADR 7.1.0003 item 6 e alternativa
H), porque "a tolerance hides a reconstruction bug … whose effect is below it"
(ADR 7.1.0003, alternativa A). Como no item 3 daquele ADR
(`--cross-environment`), **depois** do diagnóstico, se o `[finding]` mostrar
uma diferença numérica de ambiente que as chaves não capturam (ex.: outra
capacidade de CPU), a reprodução pode ser julgada pelas classes da §4.3,
citando o `[finding]`; ela passa então a sustentar só o claim (c) da §4.7, não
o (a). Um diagnóstico que aponte defeito de código é desvio (§4.6).

### 4.3 Entre ambientes: por classe de grandeza (R-ENV — convenção)

Quando o ambiente difere (outra versão do interpretador ou de biblioteca,
outra plataforma), o bit a bit **não** é prometido — exatamente o regime de
A1-TOL (inference §3.1) aplicado à cadeia de avaliação. Um exemplo concreto do
porquê: "`sum()` now uses Neumaier summation to improve accuracy and
commutativity when summing floats" (Python 3.12, *What's New*, §Other
Language Changes) — o **mesmo código-fonte** soma de outro jeito em 3.11 e em
3.12. Um ambiente diferente é, para a Rule 3 de Sandve, outro programa: "In
order to exactly reproduce a given result, it may be necessary to use programs
in the exact versions used originally".

**Convenção (R-ENV, classe C, §9.1).** A expectativa entre ambientes é
declarada **por classe** de grandeza:

| Classe | O que é | Critério entre ambientes |
|---|---|---|
| **R1 — discreta** | contagens (T, hits, violações, linhas degeneradas), decisões (gate, Holm, pertença ao MCS, desfecho de H2, vencedor, H3 sustentada), conjuntos e rótulos | **igualdade exata**; uma diferença é `[finding]`, salvo a exceção de fronteira abaixo |
| **R2 — contínua determinística** | toda grandeza contínua que não depende de número aleatório (pinball, CRPS_Q, IS, MPIW, PICP, d̄, variâncias HAC, estatísticas e p-valores analíticos, limites de Wilson, participações de H3 sobre perdas persistidas) | \|a − b\| ≤ 10⁻⁹ · max(\|a\|, \|b\|, u_q) |
| **R3 — dependente de aleatoriedade** | p-valores do MCS por bootstrap, p-valores de Monte Carlo, intervalos bootstrap de H3 | bit a bit se o gerador e sua versão forem os mesmos (o fluxo do `random.random()` do Python é garantido entre versões com o mesmo seeder; o `Generator` do NumPy, só no mesmo build e máquina); senão, a diferença é **reportada** (abaixo), não aceita nem recusada |

- **R2.** O fator 10⁻⁹ é o default documentado de `math.isclose` para a
  tolerância relativa — "The default tolerance is 1e-09, which assures that
  the two values are the same within about 9 decimal digits" (Python 3.12,
  `library/math`). **u_q** é a **unidade natural** da grandeza, que dá a escala
  perto de zero (a tolerância só relativa falha em ≈ 0: "isclose(x, 0) … is
  False for any nonzero x", mesma página). Ela é definida **por grandeza, na
  sua própria escala**: u_q é **a mesma estatística calculada com os termos em
  valor absoluto**, com a mesma normalização — para uma média ou soma (pinball,
  MPIW, IS, d̄), a média de |termo| (para d̄, a média de |d_t|); para uma
  variância de d̄, a média de d_t² com a mesma normalização do estimador (≈
  (1/T)·média de d_t², a escala de var(d̄)); para grandezas adimensionais
  limitadas (probabilidades, coberturas, p-valores, participações), u_q = 1;
  para estatísticas de teste, a escala dos seus componentes (|d̄| e √var̂(d̄)).
  Assim a tolerância fica na escala em que o arredondamento acontece — uma
  soma tem erro proporcional à soma dos valores absolutos dos termos, não ao
  valor da soma, que pode cancelar perto de zero (**derivação**) — e nunca é
  do tamanho do próprio valor (o defeito de um piso fixo, ou de σ_y² para uma
  variância de d̄ de ordem 10⁻¹¹). É a mesma ideia do ADR 7.1.0003 — medir na
  escala do próprio cálculo — que evita a tolerância absoluta cega à escala
  (alternativa E daquele ADR). `[SEM-FONTE-PRIMÁRIA]` para o par como
  critério de reprodução — convenção (degraus 2 e 1).
- **R3.** Com o fluxo aleatório diferente, as estimativas de Monte Carlo
  mudam por erro de Monte Carlo. A diferença é reportada; como **ordem de
  grandeza**, uma proporção estimada com B réplicas tem desvio-padrão
  √(p(1 − p)/B) (**derivação** binomial elementar) — os estimadores do código
  não são exatamente uma proporção simples (o p-valor de Monte Carlo do
  Christoffersen tem a forma (N·G̃ + 1)/(N + 1) com desempate de Dufour, e o
  p-valor do MCS é um máximo cumulativo ao longo das eliminações — evaluation
  §7.6, §6.5), e o intervalo bootstrap de H3 não tem fórmula simples de erro.
  Nada disso é critério de aceitação, porque o claim do TCC é o do mesmo
  ambiente (§4.7). A Rule 6 de Sandve pede exatamente isso: "As a minimum, you
  should note which analysis steps involve randomness, so that a certain level
  of discrepancy can be anticipated when reproducing the results".
- **Exceção de fronteira (R1).** Uma decisão que muda entre ambientes só é
  "explicada" se a grandeza contínua que a decide estiver, nas duas corridas,
  a menos da tolerância da sua classe do limiar que a decide (em R2, ex.: um
  p-valor de Holm a menos de 10⁻⁹ · max(p, 1) ≈ 10⁻⁹ do seu limiar; em R3, a
  menos de dois desvios-padrão de Monte Carlo, na ordem de grandeza acima).
  Fora disso, é `[finding]`.

### 4.4 Rastreabilidade por hash

A igualdade da camada de identidade (§2.2) é **pré-condição** da reprodução e
se verifica por hash: o hash do cohort e das revisões do pré-registro (ADRs
5.5.0001, 6.5.0001), os fingerprints do dataset e do split e o hash de
conteúdo do silver lido (§4.5). A cadeia de âncoras (tag + comentário com
timestamp do servidor, ADR 6.5.0003) prova a **ordem** pré-registro →
avaliação; a reprodução, feita depois, não toca nem re-ancora nada. O que o
hash **não** prova: que o resultado é o mesmo (isso é §4.2–§4.3) nem que o
resultado está certo (isso é a suíte de contratos + oráculo — ADR 0.0.0021).

### 4.5 O que a 8.1 precisa registrar e preservar (requisito de fronteira 8.1 → 8.2)

Para a reprodução ser possível sem adivinhação, a 8.1 tem de deixar:

1. **a geração julgada preservada** — uma cópia imutável da geração (tabelas,
   manifesto, scorecard) com o hash do seu conteúdo, feita antes de qualquer
   outro refresh da partição, porque o refresh seguinte a substituiria (ADR
   6.4.0005 itens 4–5);
2. **a identidade completa** da §2.2, **incluindo o hash de conteúdo das
   tabelas do silver lidas** (a lacuna do ADR 6.4.0005 item 9);
3. **o commit** do código e o indicador de árvore limpa;
4. **o ambiente** — versões do interpretador e das bibliotecas que computam
   (inclusive as que geram números aleatórios), hash do lock, plataforma e
   capacidade de CPU;
5. **as seeds** de cada etapa aleatória.

Base: Sandve et al. 2013, Rules 1, 3, 4, 5 e 6. Boa parte já é registrada pelos
manifestos do gold e do cohort (ADRs 6.4.0005, 7.1.0003, 7.1.0004); o *como*
(e onde fica a cópia) é do `technical.md` da 8.1.

### 4.6 A reprodução não substitui a evidência julgada

A geração julgada preservada é a que o dossiê identifica e a que o TCC cita; a
reprodução roda em destino separado, é **comparada** a ela, e o resultado da
comparação é registrado (classe por classe, com max |Δ| também quando passa —
como o ADR 7.1.0003 item 5 faz para as predições). Se a reprodução falha, a
geração julgada **não** é trocada pela reproduzida: o `[finding]` é
diagnosticado primeiro, e qualquer correção que mude um número confirmatório
depois do hash é um **desvio do plano**, reportado como tal ("desvios do plano
são reportados" — Nosek et al. 2018, "Challenge 1", via evaluation §8.3) e
listado no dossiê (§7).

### 4.7 O claim citável

O que o TCC pode afirmar, nessa ordem de força: (a) **no ambiente registrado**
e com o caminho de cálculo da geração julgada, a cadeia silver → gold →
scorecard reproduz a geração julgada **bit a bit**, inclusive as etapas
aleatórias, porque as seeds estão registradas; (b) as predições de teste
reproduzem a partir dos checkpoints bit a bit (7.1); (c) em outro ambiente,
contagens e decisões são iguais e as grandezas contínuas coincidem a menos de
10⁻⁹ relativo à escala natural de cada uma (classe R2), com as etapas
aleatórias reprodutíveis
na medida da garantia do gerador (R3). O item (c) só é afirmado se tiver sido
de fato executado; o TCC não promete reprodução que não foi feita.

## 5. Equivalência com a evidência anterior (Stage 8.2, parte ii)

### 5.1 Papel: oráculo de regressão, nunca autoridade

A evidência confirmatória do projeto anterior serve "apenas como **oráculo de
equivalência/regressão**, com tolerância declarada — nunca como autoridade de
decisão" (overview §2, Estado atual). Três consequências:

1. **A pipeline oficial nunca é ajustada para "bater"** com o anterior. Uma
   divergência se explica (§5.6) ou é registrada como não explicada; ela não
   muda método, parâmetro nem código do caminho oficial (non-goal da 8.2:
   "reabrir metodologia"; DoD: "divergências explicadas pela teoria (não 'bate
   com o antigo')").
2. **A comparação é simétrica no ônus da prova.** O anterior não é gabarito:
   ele tinha camada estatística artesanal "incluindo um bug conhecido"
   (overview §2, Problema). "O anterior está errado aqui" é explicação
   legítima **só** quando o defeito está identificado com referência (§5.6).
3. **A evidência anterior nunca é entrada** do caminho oficial (overview §3,
   fora do escopo: "Reaproveitar dados derivados ou checkpoints de
   implementações anteriores"). Ela só é lida pela auditoria.

**O que "equivalência" pode significar aqui.** O modelo anterior foi
treinado com outras features, outro dataset re-derivado e outros
hiperparâmetros (overview §2–§3). Uma tolerância estatística sobre os
**números do modelo** não mediria a equivalência de nada — os modelos são
outros. A tolerância declarada da ASSUM-4 faz sentido **onde a mesma coisa é
calculada dos dois lados**: o **alvo** e o **código de métrica** (§5.4). Os
números do modelo têm o **sentido** como tolerância, com os deltas documentados (§5.5; decisão B2 do humano, ADR 0.0.0062).

Pela política editorial (§1), o resultado desta auditoria fica no repositório;
o texto do TCC não a menciona.

### 5.2 Pré-requisito: congelar a evidência anterior por hash

**Convenção (EQ-HASH, classe C, §9.1).** Antes de **qualquer valor** da
evidência anterior ser lido pela auditoria, o conjunto de arquivos que servirá
de oráculo é **fixado por hash criptográfico do conteúdo** (um hash por
arquivo, mais a lista) e esse registro é **versionado no repositório** —
porque esses arquivos vivem fora do controle de versão do projeto (numa área
de dados ignorada pelo git), e a Rule 4 de Sandve ("If computer code is not
systematically archived along its evolution, backtracking to a code state that
gave a certain result may be a hopeless task") e a Rule 1 (registrar "the
exact parameters and inputs that were used") só se cumprem para um arquivo
não versionado se a sua identidade for registrada. A auditoria lê **só**
arquivos cujo hash bate com o registro; arquivo que não bate é recusado, não
"atualizado". A precisão de armazenamento de cada arquivo (§5.4) é lida do seu
**schema** (tipos das colunas), não dos valores, e registrada junto.

**Ordem e o que ela protege.** As regras de comparação (o que se compara,
como se alinha, as tolerâncias, o que conta como explicação) são as **deste
doc**, fixadas antes de a 8.1 rodar — portanto antes de qualquer número
**novo** ser visto. Os números agregados do anterior já são conhecidos
(overview §2: o estudo anterior existe e foi lido); o congelamento protege a
escolha do conjunto de comparação contra os números **novos**, não contra os
antigos. O `technical.md` da 8.2, escrito depois da 8.1, só preenche a
mecânica; mudar uma regra deste bloco depois de ver os números é escolher a
análise pelo resultado — o *garden of forking paths* que o pré-registro existe
para impedir (Nosek et al. 2018: "the observed P value is diagnostic about its
intended likelihood only when analysis choices are made before observing
data", via evaluation §8.3) — e passa a ser decisão P do humano (skill
`evidence-resolution` §1), registrada como desvio.

### 5.3 O que se compara: a interseção comum

**Decisão do humano (B1, ADR 0.0.0061).** A comparação fica **restrita à
interseção comum** das duas evidências:

- **pinball por nível** em τ ∈ {0,1; 0,5; 0,9}, por (modelo comum, horizonte
  comum);
- **PICP e MPIW do par de 80 %** (0,1; 0,9), por (modelo comum, horizonte
  comum);
- **DM contra os baselines comuns**, por horizonte — **só no sentido e na
  significância que cada lado reportou** (abaixo);
- **sentido do veredito** (abaixo).

Regras de alinhamento (convenção **EQ-INTER**, classe C, §9.1):

1. **Modelo comum é por definição, não por nome.** Um baseline só é comum se
   as duas definições (estimador, janela, parâmetros) forem declaradas
   equivalentes; mesmo nome com definição diferente fica fora (ou entra só no
   nível de código de métrica, §5.4, que não depende de o modelo ser comum).
   **O candidato é pareado por papel**, não por definição: o candidato do lado
   novo (o TFT do cohort, seeds pela média — B-SEEDS) contra o candidato do
   lado anterior, sabendo que diferem em features, dados e hiperparâmetros.
   Ele entra na pinball por nível, no PICP e no MPIW como "candidato novo ×
   candidato anterior" (comparação de modelo, §5.5) e em "candidato − baseline
   comum" como a diferença **dentro de cada lado** (candidato do lado contra o
   baseline comum do mesmo lado), comparando-se os dois sinais; no nível de
   código de métrica (A2) as predições do candidato anterior entram como as de
   qualquer modelo.
2. **Alinhamento por `target_timestamp` e horizonte, na interseção exata dos
   pontos presentes nas duas evidências** — o mesmo princípio do pareamento
   estrito (evaluation §6.7, conv. 17). **Fold não é chave:** os cortes de fold
   podem não coincidir; um ponto é comparável se existe nas duas, qual fold
   for. T∩ é reportado por horizonte.
3. **Grade: só os níveis comuns, sem reinterpolar.** Um nível ausente numa das
   grades não é reconstruído por interpolação: o score é função da previsão
   **quotada** (Gneiting & Raftery 2007, §1, via evaluation §2.2 razão 1) — um
   quantil interpolado é uma previsão que nenhuma das duas pipelines emitiu.
4. **Janelas que não coincidem:** compara-se a interseção; o que está fora dela
   não entra, e a diferença de cobertura temporal é registrada como contexto.
   Se a interseção de um horizonte for vazia, aquele horizonte não tem
   comparação numérica — registrado, não contornado.
5. **Evidência só agregada.** Para uma grandeza de que o anterior guardou só o
   valor agregado (sem predições por ponto), não há interseção, nem conferência
   do realizado, nem T∩: ela entra **só no sentido** (sinal, lado do nominal,
   significância), rotulada "amostras diferentes", sem delta numérico.

**DM: só o reportado, nunca recomputado.** O DM do anterior **não** é
recalculado sobre as perdas anteriores na interseção: isso seria um teste
novo, fora do pré-registro (evaluation §8.3: "Only these analyses deserve the
label 'confirmatory'"), e a interseção pode não ser contígua, violando a
pré-condição de HAC e bootstrap em bloco (evaluation §6.7, conv. 1.21b).
Compara-se o que **cada lado reportou** contra cada baseline comum: o sinal de
d̄ e a rejeição ao α de cada lado — com a declaração explícita de que as
amostras, a loss (P̄_G depende da grade — evaluation §3.1), o estimador e a
família de cada lado diferem. Do lado novo, o DM lido é o do gold, com o
estimador primário (retangular — ADR 6.5.0006), **também nos horizontes em
que H1 reprova** (lá ele é perfil, porque H2 é "não aplicável" — §2.3). Não
há teste sobre a diferença entre os lados: a tolerância é o sentido (§5.5, B2).

**Sentido do veredito.** Para cada (horizonte, baseline comum), o par (sinal
de d̄, rejeição) reportado por cada lado; e, onde o anterior tiver uma leitura
de calibração do par de 80 %, o lado do nominal. Comparação **categórica**:
igual ou não. Não se cruzam decisões de Holm entre as pipelines: as famílias,
o candidato e o gate H1 diferem (o anterior não tinha o gate do ADR 6.5.0006),
logo a decisão ajustada não tem o mesmo significado nos dois lados.

### 5.4 O que deve coincidir: alvo e código de métrica (EQ-MUST)

**Convenção (EQ-MUST, classe C, §9.1).** É aqui que a "tolerância declarada"
da ASSUM-4 se aplica, porque dos dois lados se calcula a **mesma coisa**:

**(A1) Alvo.** Na interseção, o realizado y_t das duas evidências tem de
coincidir a menos da **precisão de armazenamento do anterior**: meio ulp do
tipo gravado na magnitude do valor (ex.: float32 ⇒ |Δ| ≤ 2⁻²⁴·|y|), ou meia
unidade da última casa decimal se o arquivo for texto — a precisão vem do
schema (§5.2). Se não coincide, os alvos diferem (definição do retorno, ajuste
de preço — ADR 3.5.0001; modeling §2.1) e **toda** métrica difere por isso: a
comparação de modelo (§5.5) daquele horizonte para, e a divergência é
registrada com essa causa a demonstrar.

**(A2) Código de métrica.** Com as predições por ponto do anterior, calcula-se
m_A = **código novo aplicado às predições anteriores, na mesma amostra que o
anterior usou** para o número que gravou, e compara-se m_A com o número
anterior gravado, m_ant. Com definições iguais, a diferença tem de caber em
max(tolerância R2 da §4.3, precisão de armazenamento de m_ant). O que passa
disso só se explica por **definição de métrica**, cada uma com previsão exata
ou de sentido:

| Diferença de definição | Previsão | Onde está a teoria |
|---|---|---|
| escala da pinball (fator 2) | razão exata 2 | evaluation §2.3, conv. 4 |
| pontuar bruto × rearranjado | na soma da grade, o rearranjado nunca é pior; **por nível**, sem garantia de sentido | evaluation §2.2 (Lorentz; Berrisch & Ziel 2023 §3.4) |
| convenção de empate y = q̂ | só nos indicadores de cobertura, só nos empates; contagem verificável | evaluation §4.5 |
| amostra (pontos, dedup, exclusões) | outro T; reconstrução da amostra anterior reproduz m_ant | evaluation §2.1, §6.7 |
| pesos na grade (iguais × quadratura) | conta exata a partir dos níveis | evaluation §3.1 (FA2) |

Se a amostra que o anterior usou não puder ser reconstruída, A2 daquela
grandeza é "não realizável" e fica registrado assim. Base: identidade
telescópica m_novo − m_ant = (m_novo − m_A) + (m_A − m_ant) — o primeiro termo
é diferença de **modelo** (§5.5), o segundo de **código** (**derivação**).

### 5.5 O que se espera que difira: os números do modelo (EQ-DESC)

**Decisão do humano (B2, ADR 0.0.0062) e convenção (EQ-DESC, classe C,
§9.1).** Nos números do modelo — m_novo contra m_A na interseção (os dois pelo
código novo), ou, sem predições por ponto, os valores reportados (§5.3 item
5) — a **tolerância declarada é o sentido**; os deltas quantitativos são
documentados por horizonte, com sinal, sem limiar numérico. Há **divergência
de sentido** quando muda:

- o **sinal** da vantagem (candidato − baseline comum) na pinball de um nível
  comum;
- o **lado do nominal** do PICP do par de 80 % (abaixo, dentro ou acima da
  banda de Wilson 95 % do lado novo, no T∩);
- o **sentido** do DM reportado contra um baseline comum (sinal de d̄ ou
  rejeição — §5.3).

Toda divergência de sentido é explicada por §5.6 ou registrada como
`[finding]` **não explicado** no relatório. Os deltas sem mudança de sentido
são reportados sem exigência de explicação.

**DM e grandezas só agregadas.** Essas comparações são feitas sobre
**amostras, losses e famílias diferentes por construção**, então "janela/folds/T"
e "grade" são sempre verdade e **não** explicam uma divergência sozinhas, e a
localização da §5.6 (c) não se aplica (não há m_A): nelas a explicação exige só
(a) e (b) da §5.6, e as diferenças declaradas entram como contexto do
`[finding]`.

**Não há teste de equivalência.** O TOST (Schuirmann 1987
`[CITAÇÃO-NÃO-ACESSADA]`) exige uma margem fixada por razão substantiva: "An
equivalence margin should be specified in the protocol; this margin is the
largest difference that can be judged as being clinically acceptable … The
choice of equivalence margins should be justified clinically", e opera como
"two simultaneous one-sided tests to test the (composite) null hypothesis
that the treatment difference is outside the equivalence margins" (ICH E9,
§3.3.2, p. 18 da versão EMA CPMP/ICH/363/96 — a citada em evaluation §11.1;
p. 15 impressa da versão do site da ICH). Aqui não existe razão substantiva
para margem nenhuma entre modelos diferentes — o mesmo motivo pelo qual o
projeto não adotou TOST em H2 (evaluation §6.10, conv. 15) nem a equivalência
B2 em H1 (evaluation §8.5); e a parte (ii) não sustenta claim do texto. "Sem
divergência de sentido" **não** é "equivalência demonstrada" (evaluation §6.10).

**Não há tolerância em unidades de dispersão entre seeds.** Medir a
diferença entre os dois modelos em desvios-padrão entre seeds foi descartado
(§9.1, EQ-DESC, alternativas): a seed mede ruído de réplica do **mesmo**
modelo, e aqui os modelos diferem em features, dados e hiperparâmetros — a
variância de inicialização "actually contribute[s] a small part of the
variance … much smaller than the variance due to perturbing the split of the
data in train and test sets" (Bouthillier et al. 2021, §7), então um limiar
nessa escala seria ultrapassado quase sempre e não discriminaria nada; com 10
seeds, além disso, a referência seria uma t com 9 graus de liberdade, não uma
normal. Para o GBM e os baselines (sem seed) a escala nem existe.

### 5.6 Divergência explicada pela teoria (EQ-EXPL)

**Convenção (EQ-EXPL, classe C, §9.1).** Uma divergência — A1 ou A2 fora da
tolerância, ou divergência de sentido de modelo (§5.5) — conta como **explicada**
se, e só se, as três condições valem:

- **(a) diferença declarada** — é atribuída a uma diferença concreta e
  registrada entre as duas pipelines, de um catálogo fechado:

  | Categoria | Sentido ou previsão identificável | Onde está a teoria |
  |---|---|---|
  | alvo (definição do retorno, ajuste de preço) | A1 falha; toda métrica muda | §5.4; ADR 3.5.0001 |
  | definição de métrica (tabela da §5.4) | exata ou de sentido, por linha | §5.4 |
  | agregação de seeds do candidato (média das perdas × ensemble) | ensemble tem perda ≤ média das perdas (Jensen): pinball do candidato anterior menor se ele era ensemble | evaluation §6.9 (B-SEEDS) |
  | defeito do anterior **identificado com referência** (issue, commit ou doc que descreve o defeito e o seu efeito) | o efeito descrito na referência | overview §2 (Problema) + a referência |

  "Grade", "janela/folds/T" e "estimador do DM" não estão no catálogo de
  explicação: na interseção a grade é a comum e a amostra é a mesma, e fora
  dela (DM, grandezas só agregadas) são sempre verdade e viram contexto
  (§5.5).

  **Aplicabilidade por comparação — fixada aqui, antes da 8.1.** Qual
  categoria pode explicar qual comparação sai **mecanicamente** desta tabela;
  o `technical.md` da 8.2 não a amplia nem a escolhe depois de ver os números
  (§5.2):

  | Comparação | Categorias que podem explicá-la |
  |---|---|
  | A1 — realizado | alvo |
  | A2 — pinball por nível | escala (fator 2); bruto × rearranjado; amostra; pesos na grade (se o anterior gravou só P̄_G); defeito referenciado |
  | A2 — PICP do par 80 % | convenção de empate; bruto × rearranjado; amostra; defeito referenciado |
  | A2 — MPIW do par 80 % | bruto × rearranjado; amostra; defeito referenciado |
  | modelo — sinal de (candidato − baseline comum) na pinball por nível | alvo (se A1 falhou); agregação de seeds do candidato; defeito referenciado do modelo ou da pipeline anterior |
  | modelo — lado do nominal do PICP 80 % | alvo (se A1 falhou); agregação de seeds do candidato; defeito referenciado |
  | DM e grandezas só agregadas — sentido | agregação de seeds do candidato; defeito referenciado (condição (c) dispensada, §5.5) |

  "Features, dataset re-derivado ou hiperparâmetros diferentes" é sempre
  verdade e não prevê sentido: **não** explica uma divergência de sentido
  sozinho; é registrado como contexto da divergência não explicada. "Pilha
  numérica" não explica divergência de **modelo** (seu efeito é da ordem do
  arredondamento, §4.3); só entra em A2, já coberta pela tolerância R2.
- **(b) mecanismo e sentido** — o efeito observado é compatível com a
  previsão da linha (razão exata, sentido, limite);
- **(c) localização** — a decomposição da §5.4 põe a divergência no termo
  que a explicação prevê (definição de métrica → termo "código"; seeds,
  defeito do modelo anterior → termo "modelo"; alvo → A1).

O que **não** é explicação: "bate com o antigo" (DoD da 8.2), "diferença
pequena", "a nova pipeline está certa" sem mecanismo, ou uma categoria fora do
catálogo. Uma categoria nova só entra no catálogo por emenda deste doc, com a
teoria do seu mecanismo — nunca como explicação *ad hoc* de uma divergência já
vista.

**Como a 8.2 fecha com divergência não explicada.** Divergência não explicada
é registrada como `[finding]` no relatório de equivalência, com a
decomposição, os deltas e o contexto (as diferenças declaradas que se
aplicam). Ela **não** bloqueia o fechamento da 8.2 nem o veredito da 8.1 (que
é da geração julgada): o relatório a lista como "não explicada". A exceção é
A1 ou A2 fora da tolerância **com indício de defeito na pipeline nova**: aí o
`[finding]` é investigado antes de fechar, e, se o defeito se confirma, a
correção segue o processo normal e é **desvio** reportado (§4.6).

### 5.7 Aposentadoria de andaime interino e o teste de equivalência

"Andaime interino" é todo artefato — código, teste, leitor, fixture, cópia de
dado — que existe **só** para ligar a pipeline oficial à evidência anterior.
**Convenção (EQ-ANDAIME, classe C, §9.1).**

**Aposentadoria.** Um andaime é aposentado quando (1) o relatório de
equivalência registra cada comparação que ele serviu, com os hashes dos dois
lados (§5.2) e a classificação final (dentro da tolerância / explicada, com a
categoria / não explicada); (2) nenhum resultado oficial depende dele — a
cadeia oficial se reconstrói a partir dos dados persistidos sem ele (overview
§4, critério "Reprodutibilidade"); e (3) a aposentadoria e o motivo ficam
registrados no relatório. Um andaime necessário para investigar um
`[finding]` sob investigação (§5.6, exceção) só se aposenta quando ele fecha.
Um andaime que tenha entrado no caminho oficial viola §5.1 item 3 e sai, não
"se aposenta".

**O teste de equivalência (fora do CI).** O teste que o roadmap prevê para a
comparação com a evidência anterior tem um oráculo **fora do controle de
versão**: ele não pode ser gate de CI. Convenção: o teste é **pulado** (skip
com o motivo e a referência ao registro de hashes) quando os arquivos do
oráculo não estão presentes; quando estão, ele roda e **falha** se algum hash
não bate (nunca um skip silencioso sobre um oráculo trocado). O registro
durável da auditoria é o **relatório com os hashes**, não o teste — "only that
exact state of the script may be able to produce that exact output" (Sandve et
al. 2013, Rule 4) vale para o oráculo também.

## 6. Plots canônicos (Stage 8.3)

### 6.1 Regras comuns

1. **Reconstrutível de dado persistido.** Todo gráfico é desenhado a partir da
   geração julgada preservada (gold) ou do dado persistido de onde ela foi
   construída (predições e realizado do silver, identificados pelo hash de
   conteúdo — §4.5), identificado no dossiê — nunca de um re-treino nem de um
   cálculo que não deixou rastro. Sandve et al. 2013, Rule 7: "As a minimum,
   one should note which data formed the basis of a given plot and how this
   data could be reconstructed"; overview §4: "artefatos de decisão
   reconstruíveis a partir de dados persistidos sem re-treino".
2. **Por horizonte, sem agregar.** Um painel por horizonte; nada mistura
   horizontes num mesmo número ou curva (evaluation §8.7). Pôr h+1 e h+7 lado a
   lado para **comparar** (como H3 exige) não é agregar.
3. **Rótulo de estatuto** (§2.3) em todo gráfico, por elemento quando
   misturado, mais a frase obrigatória de H3 e do conformal.
4. **Seeds.** Grandezas do candidato seguem B-SEEDS (média entre seeds; n ≈ T).
   Onde o gráfico precisa de **uma** previsão por ponto (série OOS), ele não
   desenha a média dos quantis entre seeds — isso é um ensemble, outro objeto
   (evaluation §6.9) — e sim uma seed **pré-declarada** (§6.2, série OOS).
5. **O gráfico não decide nada e não testa nada novo.** Nenhum gráfico é
   critério; o critério é a árvore pré-registrada (evaluation §8.6). Um gráfico
   pode mostrar uma decisão; não produz uma, e não exige teste que o gold não
   tenha persistido.

### 6.2 Catálogo

| Gráfico | O que representa | Fonte primária | Estatuto e rótulo obrigatório |
|---|---|---|---|
| **Reliability diagram por τ** | {(τ_k, ĉ(τ_k))} por modelo e horizonte, pooled sobre folds, contra a diagonal; banda de Wilson por nível | GBR 2007 Thm 2; Kuleshov et al. 2018 §3.5 Eq. (8); bandas: Brown, Cai & DasGupta 2001 Eq. (4); Bröcker & Smith 2007 (barras de consistência) — via evaluation §4.1, §4.4 | **misto, rotulado por elemento**: as duas caudas do par primário (0,1; 0,9) do **candidato**, na variante do gate (amostra do próprio modelo, linhas degeneradas excluídas, contagens médias entre seeds, banda **97,5 %** — ADR 6.5.0006), com o **poder declarado** do gate, são **confirmatórias**; os demais níveis, modelos e a banda **95 %** são **descritivos** (perfil). Aviso fixo: banda binomial anti-conservadora em h+7 e sob agrupamento (evaluation §4.4) |
| **Quantile score plot** | P̄_τ × τ por modelo e horizonte — onde (cauda × centro) o skill vive | Gneiting & Ranjan 2011 Eq. (23) (atribuído a Laio & Tamea 2007), via evaluation §3.1 | **descritivo** (perfil); a métrica primária é P̄_G, não a curva |
| **Sharpness diagram** | distribuição (box plot / quantis) das larguras u − l por par, modelo e horizonte, em unidade de y | GBR 2007 §3.3 ("we follow Bremnes (2004) in proposing box plots … sharpness diagram"), via evaluation §4.3 (conv. 8) | **descritivo**; legenda: "sharpness só tem sentido sujeito à calibração" (evaluation §2.6) |
| **PICP × MPIW** | um ponto por (modelo, par) e horizonte, com a reta do nominal 1 − 2τ_l e, para o candidato, a dispersão entre seeds | Pearce et al. 2018 §3 Eqs. (4)–(7) (definições), via evaluation §4.2; GR 2007 §9.3 ("a meaningful comparison of interval estimators requires either equal coverage or equal width"), via evaluation §4.6 | **descritivo**; legenda fixa: o gráfico **não ordena** modelos — mais estreito só é melhor com cobertura igual; nenhuma combinação largura × cobertura (CWC) é desenhada (evaluation §4.6, conv. 11) |
| **Tabela/heatmap do DM: candidato × comparadores** | por horizonte, uma célula por comparador da família: p-valor **bruto** do DM unilateral "candidato com perda menor" com o estimador **primário** (retangular), e a **decisão de Holm** | DM 1995; HLN 1997; Holm 1979 — via evaluation §6.1–§6.4; ADR 6.5.0006 (estimador primário; Bartlett é perfil) | **confirmatório só nos horizontes em que H1 passa**; onde H1 reprova, H2 é "não aplicável" e a linha é **descritiva** (perfil), rotulada assim. Células comparador × comparador **não** existem: o gold não persiste esses DMs, e calculá-los seria teste novo (§6.1 item 5) |
| **Série OOS / fan chart** | por horizonte, ao longo de `target_timestamp`, o realizado y_t sobre as faixas dos pares simétricos da grade rearranjada do candidato, com os cortes de fold marcados | FPP3 §5.5 ("When plotted, the prediction intervals are shown as shaded regions, with the strength of colour indicating the probability associated with the interval"); folds concatenados: evaluation §6.8 (B-FOLDS) | **descritivo**; **uma seed pré-declarada** (a primeira da lista do cohort), com a legenda "seed s, ilustrativa; as métricas usam a média entre seeds" (convenção P8-FAN, §9.1). Inspeção visual de cobertura não é evidência |
| **Série do diferencial d_t** | por horizonte e comparador da família, d_t ao longo do tempo (+ ACF) | Diebold 2015 §2.2 ("One can plot the loss differential series, examine its sample autocorrelations"), via evaluation §6.2, §6.8 | **descritivo** (diagnóstico pré-registrado da premissa do DM; ADR 6.5.0008) |
| **Importância por família / H3** | por horizonte e família, I_f(h) e s_f(h) com intervalo bootstrap, para permutação e ablação lado a lado; Δ_f com intervalo; leitura C4/C5 | inference §5.4–§5.7 (C1–C5); ADRs 0.0.0007, 7.3.0005 | **descritivo**, com linguagem estritamente descritiva (inference §5.8, C7: "a família f responde por uma parcela maior da perda evitada em h+7 do que em h+1", nunca "f causa") |
| **Pesos da VSN** | peso médio por família na seleção de variáveis | inference §5.3; Lim et al. 2021 §4.2 | **descritivo**, rotulado **"horizonte-invariante"** — a VSN não tem eixo de horizonte e não entra na regra de H3 (inference §5.3) |
| **Nativo × conformal** | por horizonte e par, ĉ por cauda / PICP / MPIW da grade nativa e do CQR, com a banda de Wilson e a referência de dispersão Beta | inference §4.11 (B8), §4.10 (B7); Angelopoulos & Bates 2023 §3.2 | **descritivo** (benchmark), rótulo **"cobertura empírica (não garantida)"** em todo painel (overview R-CONFORMAL-1; inference §2.4) |

Gráficos fora deste catálogo podem existir; o que não está declarado no
pré-registro nem aqui é **exploratório** por definição (§2.3) e não sustenta
afirmação do texto.

## 7. Dossiê de rastreabilidade (Stage 8.3)

O dossiê é o documento que liga **cada afirmação do texto** ao resultado que a
sustenta e **cada resultado** ao modo como foi produzido. **Convenção
(DOSSIE, classe C, §9.1):** o conteúdo mínimo segue as regras de Sandve et al.
(2013) — a recomendação da fonte de origem (degrau 3) — e os registros que o
próprio protocolo do projeto já exige:

| Conteúdo mínimo | Base |
|---|---|
| Por decisão/afirmação: `run_id`s, `config_signature`, `split_fingerprint`, fingerprint do dataset, `feature_set_hash`, hash de conteúdo do silver lido; id do cohort e do cohort de ablação com seus hashes e tags | Rule 1 — "For every involved step, you should ensure that every detail that may influence the execution of the step is recorded" |
| A cadeia do pré-registro: `preregistration_ref` e hash de r0, r1, r2, r3, tags e comentários de âncora (timestamp do servidor), revisão julgada, `blind_status` de cada emenda | Rule 1; evaluation §8.2 / ICH E9 §5.1 ("Formal records should be kept of when the statistical analysis plan was finalised") |
| **Computação pré-âncora já registrada**: a medição da Stage 6.4 que computou tabelas confirmatórias do r0 num container descartado, sem valor lido (ADR 6.5.0010 P1), e a ressalva de que a ordem provada é a do ADR 6.5.0003 item 4 ("no statement is made about computations before it") | Nosek et al. 2018 (transparência sobre influências potenciais, via evaluation §8.2); ADRs 6.5.0003, 6.5.0010 |
| **Declaração de cegamento** do pré-registro (campo opcional, conteúdo decidido pelo humano — ADR 6.5.0010) | ADR 6.5.0010 P1 |
| A geração julgada preservada: identificação, hash do conteúdo, manifesto lido, estado (`COMPLETED`), `academic_decision_ready` e os motivos de cada conjunção | Rule 5 — "archive any intermediate result files that are produced when running an analysis" |
| **Poder declarado** do gate H1 por horizonte, contra os cenários pré-registrados (ADRs 6.5.0006, 6.5.0010 P3) — o claim de H1 nunca aparece sem ele | overview §4 (H1); evaluation §8.5 (B1) |
| Ambiente: imagem, versões do interpretador e das bibliotecas que computam (inclusive os geradores aleatórios), hash do lock de dependências, plataforma e capacidade de CPU — o do treino (CPU), o da ablação (Linux/GPU, ADR 7.3.0004) e o da avaliação | Rule 3 — "As a minimum, you should note the exact names and versions of the main programs you use" |
| Commit do código de cada etapa e indicador de árvore limpa | Rule 4 — "only that exact state of the script may be able to produce that exact output" |
| Seeds de cada etapa aleatória: treino, MCS, Monte Carlo, permutação e bootstrap de H3 (ADRs 6.5.0009, 7.3.0005) | Rule 6 — "the random seed should be recorded" |
| **Registro de desvios do plano**: toda correção pós-hash que mude número confirmatório (§4.6), toda reprodução com `[deviation]` (§4.2) e os `[finding]` abertos | Nosek et al. 2018, "Challenge 1" (desvios reportados — via evaluation §8.3) |
| Por gráfico: a tabela/chave de onde cada série sai e como se reconstrói | Rule 7 — "note which data formed the basis of a given plot and how this data could be reconstructed" |
| Por afirmação do texto: o ponteiro para o número exato (tabela, chave, campo) | Rule 9 — "Such a connection can for instance be a simple file path to detailed results, or the ID of a result in an analysis framework, included within the text itself" |
| Resultado da reprodução (§4): classe por classe, max \|Δ\|, ambiente e commit da reprodução | Rule 6 (exato × aproximado) |
| **Interno, fora do texto do TCC:** o registro de hashes da evidência anterior (§5.2) e o ponteiro para o relatório de equivalência | Rule 1; política editorial (§1) |

A Rule 10 ("all input data, scripts, versions, parameters, and intermediate
results should be made publicly and easily accessible") é **aspiração**, não
requisito deste gate: o que se publica com o TCC é decisão do humano. O
dossiê é organizado em camadas — do veredito para os detalhes —, como pede a
Rule 8 ("Generate Hierarchical Analysis Output, Allowing Layers of Increasing
Detail to Be Inspected").

## 8. Fronteira

### 8.1 O que este doc consome (ponteiros)

| Fonte | O quê | Onde se usa aqui |
|---|---|---|
| evaluation §8.1–§8.8; ADRs 6.5.0003, 6.5.0006, 6.5.0007 | ordem, gate H1, árvore do veredito, critério de sucesso | §3, §2.3 |
| evaluation §2.2, §3.1, §6.7 | pontuar a previsão quotada; P̄_G depende de G; pareamento por interseção contígua | §5.3–§5.4 |
| evaluation §6.9, §8.4 (B-SEEDS) | seeds como réplicas | §2.4, §6.1 |
| evaluation §4.1–§4.6 | reliability, PICP/MPIW, sharpness, Wilson, sem CWC | §6.2 |
| evaluation §6.10, §8.5 (B2) | não-rejeição ≠ equivalência; TOST não adotado | §5.5 |
| inference §3.1 (A1, A1-TOL); ADR 7.1.0003 | bit a bit no mesmo ambiente; tolerância entre ambientes no espaço normalizado | §4.2–§4.3 |
| ADR 6.4.0005 | refresh substitui a geração viva; sem hash de conteúdo do silver | §2.1–§2.2, §4.5 |
| inference §4.10–§4.11, §5.3–§5.8 | rótulos de conformal e de H3; VSN | §6.2 |
| overview §2, §3, §4, ASSUM-4, R-REPRO-1 | oráculo, não autoridade; reprodutibilidade sem re-treino | §4, §5 |

### 8.2 O que fica para o `technical.md`

Onde e como a reprodução re-executa (destino separado) e compara; onde fica a
cópia preservada da geração julgada e como se calcula o hash de conteúdo do
silver; o formato do registro de hashes da evidência anterior e do relatório
de equivalência; os leitores da evidência anterior; a forma do dossiê (a
aplicabilidade das categorias de explicação por comparação **não** fica para
o technical: está fixada na §5.6); a
biblioteca e o estilo dos gráficos; quais gráficos exploratórios extras
existem.

### 8.3 O que este doc não decide

O que se publica junto com o TCC (Rule 10); o texto do TCC; o conteúdo da
declaração de cegamento (humano, ADR 6.5.0010); qualquer teste de hipótese
novo (nenhum é introduzido aqui); qualquer mudança no veredito ou no
pré-registro.

## 9. Convenções decididas (tabela-resumo)

Legenda: **[P]** decisão do humano; **[E]** evidência decide; **[C]**
convenção sem vencedor, fechada pelo degrau indicado; todas em §9.1.

| # | Convenção | Fonte / âncora | Status | Stage |
|---|---|---|---|---|
| 1 | A 8.2 faz as duas comparações: (i) reprodução da própria corrida = claim citável; (ii) oficial × anterior na interseção comum = auditoria interna; roadmap 8.2 emendado | issue #208; overview ASSUM-4, R-REPRO-1 | [P] B1 (ADR 0.0.0061) | 8.2 |
| 2 | O TCC não menciona o projeto anterior; (ii) fica no repositório; nenhum gráfico compara com o anterior | decisão do humano (política editorial) | [P] P-EDIT | 8.2, 8.3 |
| 3 | Três camadas: identidade (hash, igual — incluindo hash de conteúdo do silver), resultado (comparado), proveniência (excluída) | Sandve 2013 Rule 1; ADR 6.4.0005 item 9 | [C] R-CAMADAS, degrau 3 | 8.1, 8.2, 8.3 |
| 4 | Mesmo ambiente e mesmo caminho de cálculo → bit a bit em todo campo de resultado, inclusive aleatório; falha = parada, nunca troca para tolerância | Goldberg 1991; NumPy 2.5.0 compat. policy; Python 3.12 random; Sandve Rule 6; ADR 7.1.0003 | [E] R-BIT | 8.2 |
| 5 | Commit posterior: diff que não toca o caminho de cálculo → bit a bit; diff que toca → `[deviation]` + diagnóstico | ADR 7.1.0003 (chaves de código fora do modo) | [C] R-BIT-COMMIT, degrau 1 | 8.2 |
| 6 | A 8.1 preserva a geração julgada (cópia + hash) e registra a identidade completa; a reprodução roda em destino separado | ADR 6.4.0005 itens 4–5, 9; Sandve Rules 1, 3–6 | [C] R-PRESERVA, degrau 1 | 8.1, 8.2 |
| 7 | Entre ambientes, por classe: R1 discreta exata; R2 \|Δ\| ≤ 1e-9·max(\|a\|,\|b\|,u_q), u_q = a mesma estatística com termos em valor absoluto (escala natural por grandeza); R3 bit a bit só com o mesmo gerador, senão reportada | Python 3.12 math.isclose; ADR 7.1.0003 (escala do próprio cálculo); Goldberg 1991 | [C] R-ENV, degraus 2/1 | 8.2 |
| 8 | Evidência anterior congelada por hash de conteúdo, registro versionado, precisão de armazenamento lida do schema; regras fixadas antes da 8.1 | Sandve Rules 1, 4; Nosek 2018 | [C] EQ-HASH, degraus 1/3 | 8.2 |
| 9 | Interseção: baseline comum por definição, candidato pareado por papel; `target_timestamp` (fold não é chave); níveis comuns sem reinterpolar; só agregado ⇒ só sentido; DM só o reportado, sem recomputar nem cruzar Holm | evaluation §2.2, §3.1, §6.7, §8.3; GR 2007 §1 | [C] EQ-INTER, degrau 1 | 8.2 |
| 10 | Deve coincidir: alvo (precisão de armazenamento do anterior) e código de métrica (m_A × m_ant em max(R2, armazenamento)), com tabela de definições de métrica | ASSUM-4; derivação | [C] EQ-MUST, degraus 1/5 | 8.2 |
| 11 | Números do modelo: tolerância = sentido (sinal de candidato − baseline comum, lado do nominal do PICP 80 %, sentido do DM); deltas documentados; divergência de sentido sem explicação → `[finding]`; sem limiar \|Δ\| ≤ X %, sem TOST, sem tolerância em unidades de seed | ICH E9 §3.3.2; evaluation §6.10, §8.5; Bouthillier 2021 §7 | [P] B2 (ADR 0.0.0062) + [C] EQ-DESC, degrau 1 | 8.2 |
| 12 | Divergência explicada = catálogo fechado com sentido identificável + compatibilidade + localização, com a aplicabilidade por comparação fixada na §5.6; features/dados/hiperparâmetros não explicam sozinhos; pilha numérica não explica modelo; defeito só com referência; não explicada → `[finding]` no relatório, não bloqueia | roadmap 8.2 DoD; overview §2 | [C] EQ-EXPL, degrau 1 | 8.2 |
| 13 | Andaime aposentado com comparações registradas + nenhuma dependência oficial + motivo; teste de equivalência pulado sem oráculo, falha com hash divergente, fora do CI | roadmap 8.2; overview §4; Sandve Rule 4 | [C] EQ-ANDAIME, degraus 1/5 | 8.2 |
| 14 | Rótulos confirmatório / descritivo / exploratório; confirmatório só onde a árvore se aplica (H2 só onde H1 passa); por elemento quando misturado | ICH E9 §5.1; Wagenmakers 2012 p. 632; ADRs 6.5.0006–6.5.0008 | [E] P8-ROT | 8.3 |
| 15 | DM no relatório = candidato × comparadores, p bruto + Holm, estimador retangular; confirmatório só onde H1 passa; sem células comparador × comparador | ADR 6.5.0006; evaluation §6.4 | [E] (parte de P8-ROT) | 8.3 |
| 16 | Fan chart com uma seed pré-declarada (a primeira do cohort), nunca média dos quantis entre seeds | evaluation §6.9; ADR 7.4.0001 | [C] P8-FAN, degraus 1/5 | 8.3 |
| 17 | Plots de dado persistido, por horizonte, rótulo por elemento, nenhum teste novo | Sandve Rule 7; overview §4; evaluation §8.7 | [C] P8-PERSIST, degrau 1 | 8.3 |
| 18 | Conteúdo mínimo do dossiê pelas Rules 1, 3–9 de Sandve + desvios, computação pré-âncora, cegamento e poder declarado; Rule 10 = aspiração | Sandve 2013; ADRs 6.5.0003, 6.5.0006, 6.5.0010; Nosek 2018 | [C] DOSSIE, degrau 3 | 8.3 |

### 9.1 Registro das decisões (triagem `evidence-resolution`, 2026-10-22)

Triagem: todas as bifurcações são anteriores a qualquer dado confirmatório (a
8.1 não rodou). A existência e os metadados das fontes foram conferidos
mecanicamente (`scripts/verify_citations.py`); "verificado" = trecho
conferido na fonte bruta por verificador de contexto zerado
(`evidence-verifier`, 2026-10-22); "parcial→corrigido" = o verificador achou
o trecho ou o localizador só parcialmente fiel e o texto foi corrigido (§9.2).

```
[decision:P] B1 — o que a 8.2 compara
Escolha: as duas comparações — (i) reprodução da própria corrida a partir dos artefatos persistidos (claim citável no TCC) e (ii) oficial × confirmatório anterior na interseção comum (pinball τ ∈ {0,1; 0,5; 0,9}, PICP/MPIW do par 80 %, DM contra baselines comuns, sentido do veredito) como auditoria interna · Alternativas: A — só (i); B — só (ii) (texto literal do roadmap) · Decisor: humano (issue #208, 2026-10-22)
Base: overview ASSUM-4 e R-REPRO-1 (equivalência com tolerância declarada); overview §2 (oráculo, nunca autoridade); política editorial do TCC
Sensibilidade pré-registrada: nenhuma · Reversível: sim (ADR 0.0.0061; roadmap 8.2 emendado)

[decision:P] B2 — o que é "tolerância declarada" (ASSUM-4) na comparação com o anterior
Escolha: opção 1 — tolerância numérica onde a igualdade é esperada (alvo realizado; código de métrica sobre as predições anteriores); nos números do modelo, a tolerância é o sentido (sinal de candidato − baseline comum, lado do nominal do PICP 80 %, sentido do DM), com deltas documentados; divergência de sentido sem explicação → [finding] · Alternativas: limiar |Δ| ≤ X % nos números do modelo; comparação só descritiva sem tolerância · Decisor: humano (issue #208, 2026-10-22)
Base: ICH E9 §3.3.2 (p. 18 da versão EMA) "The choice of equivalence margins should be justified clinically" [verificado] — não há fonte para X; overview ASSUM-4, R-REPRO-1 e §2 emendados na redação
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até a 8.1 rodar (ADR 0.0.0062)

[decision:P] P-EDIT — política editorial do TCC
Escolha: o texto do TCC não menciona o projeto anterior; a parte (ii) fica só no repositório · Alternativas: citar a equivalência no texto · Decisor: humano (política editorial anterior a este gate, reafirmada na issue #208)
Base: —
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R-CAMADAS — o que se compara numa reprodução
Escolha: identidade da entrada por hash, incluindo hash de conteúdo do silver lido (igual, pré-condição), resultado (comparado), proveniência (excluída) · Alternativas: comparar o artefato inteiro byte a byte (falha por timestamps); identidade sem hash do silver (não conferível) · Degrau: 3
Base: Sandve et al. 2013, Rule 1 "For every involved step, you should ensure that every detail that may influence the execution of the step is recorded"; ADR 6.4.0005 item 9 "No content hash of the silver in this Stage … 8.1 may add a content hash"; "hash identifica, não certifica" = derivação
Verificado: sustenta (Rule 1)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] R-BIT — reprodução no mesmo ambiente
Escolha: bit a bit em todo campo de resultado, inclusive etapas aleatórias, no mesmo ambiente (chaves não-código do ADR 7.1.0003 + capacidade de CPU, pelo "same machine" do NumPy); falha = parada para diagnóstico; só depois de um [finding] que mostre diferença de ambiente não capturada pelas chaves a reprodução é julgada pelas classes de R-ENV, e sustenta só o claim (c) (como o --cross-environment do ADR 7.1.0003 item 3) · Alternativas: tolerância também no mesmo ambiente; tolerância sem diagnóstico
Base: Goldberg 1991 §The IEEE Standard (Operations) "The IEEE standard requires that the result of addition, subtraction, multiplication and division be exactly rounded"; "the IEEE standard also specifies that square root, remainder, and conversion between integer and floating-point be correctly rounded"; NumPy 2.5.0 doc/source/reference/random/compatibility.rst "on the same build of numpy, in the same environment, on the same machine, you should get the same stream of numbers"; Python 3.12 Doc/library/random.rst §Notes on Reproducibility "By reusing a seed value, the same sequence should be reproducible from run to run as long as multiple threads are not running"; Sandve et al. 2013 Rule 6 "given the same initial seed, all random numbers used in an analysis will be equal"; transcendentais do domínio via `math` (stdlib; ADRs 0.0.0020, 0.0.0056, 6.4.0008) — mesma chamada do mesmo binário = derivação
Verificado: parcial→corrigido (localizador da raiz quadrada; base das transcendentais)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R-BIT-COMMIT — reprodução num commit posterior
Escolha: o diff decide — não toca o caminho de cálculo ⇒ bit a bit; toca ⇒ [deviation] + diagnóstico; lock de dependências = ambiente · Alternativas: exigir o mesmo commit (impossível na 8.2); ignorar o commit · Degrau: 1
Base: ADR 7.1.0003 itens 3 e 6 (chaves de código fora da escolha do modo; falha strict = parada)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R-PRESERVA — preservar a geração julgada
Escolha: a 8.1 preserva cópia imutável + hash da geração julgada antes de qualquer outro refresh; a reprodução roda em destino separado · Alternativas: reproduzir na mesma partição (destrói a julgada); comparar em memória sem preservar (a julgada some no refresh seguinte) · Degrau: 1
Base: ADR 6.4.0005 itens 4–5 (o refresh troca current/ e apaga a geração anterior); ADR 7.1.0003 alternativa D (não re-persistir sob o mesmo rótulo)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R-ENV — reprodução entre ambientes
Escolha: por classe — R1 discreta exata; R2 contínua |Δ| ≤ 1e-9·max(|a|,|b|,u_q), u_q = a mesma estatística calculada com os termos em valor absoluto e a mesma normalização (1 para probabilidades/coberturas/p-valores; escala dos componentes para estatísticas de teste); R3 aleatória bit a bit com o mesmo gerador, senão diferença reportada (ordem de grandeza √(p(1−p)/B)) · Alternativas: par do torch.testing.assert_close; só relativa; piso absoluto fixo 1e-12 em unidades naturais (1ª versão — cego à escala); u_q = σ_y^k (2ª versão — tolerância de 1–4 % para var(d̄)); bit a bit sempre · Degrau: 2 (default de math.isclose, a linguagem do domínio) e 1 (escala do próprio cálculo, como o ADR 7.1.0003)
Base: Python 3.12 Doc/library/math.rst isclose "The default tolerance is 1e-09, which assures that the two values are the same within about 9 decimal digits"; mesma página, impl-detail "The math module consists mostly of thin wrappers around the platform C math library functions"; Goldberg 1991 "The IEEE standard does not require transcendental functions to be exactly rounded"; Python 3.12 Doc/whatsnew/3.12.rst §Other Language Changes "sum() now uses Neumaier summation"; NumPy 2.5.0 compatibility.rst "different CPUs implement floating point arithmetic differently"; [SEM-FONTE-PRIMÁRIA] para o par como critério de reprodução
Verificado: sustenta (trechos); a forma é convenção
Sensibilidade pré-registrada: nenhuma (nenhum valor nessa faixa muda decisão; a exceção de fronteira é reportada) · Reversível: sim

[decision:C] EQ-HASH — congelar a evidência anterior
Escolha: hash de conteúdo por arquivo + lista + precisão de armazenamento do schema, versionados, antes de qualquer leitura de valor; regras de comparação = as deste doc, fixadas antes da 8.1 (protegem contra os números novos) · Alternativas: ler os arquivos como estão; versionar os próprios arquivos · Degrau: 1 (issue #208: "versionada por hash antes de servir de oráculo") e 3
Base: Sandve et al. 2013 Rule 4 "If computer code is not systematically archived along its evolution, backtracking to a code state that gave a certain result may be a hopeless task"; Rule 1; Nosek et al. 2018 (via evaluation §8.3)
Verificado: sustenta (Rule 4)
Sensibilidade pré-registrada: nenhuma · Reversível: não depois de lidos os valores (é o objetivo)

[decision:C] EQ-INTER — alinhamento na interseção e DM
Escolha: baseline comum por definição; candidato pareado por papel (candidato novo × candidato anterior; candidato − baseline comum dentro de cada lado); interseção exata por target_timestamp e horizonte, fold não é chave; só níveis comuns, sem interpolação; grandeza só agregada entra só no sentido; DM: só o sentido e a significância reportados por cada lado, sem recomputar sobre perdas anteriores nem cruzar Holm; do lado novo, o DM do gold com o estimador retangular, também onde H1 reprova (perfil) · Alternativas: comparar por fold; interpolar a grade anterior; recomputar o DM do anterior na interseção (teste novo; interseção possivelmente não contígua) · Degrau: 1
Base: evaluation §6.7 (conv. 17 e 1.21b — interseção exata e contígua); evaluation §2.2 razão 1 via Gneiting & Raftery 2007 §1 (o score é da previsão quotada); evaluation §8.3 (só o pré-declarado é confirmatório); ADR 6.5.0006 (estimador primário)
Verificado: herdado de evaluation
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] EQ-MUST — o que deve coincidir
Escolha: (A1) realizado na interseção a menos da precisão de armazenamento do anterior; (A2) m_A = código novo sobre as predições anteriores na amostra do anterior, contra m_ant, em max(R2, precisão de armazenamento), com a tabela de diferenças de definição de métrica · Alternativas: R2 também para o realizado (ignora float32/texto do anterior); só o total m_novo − m_ant (confunde código e modelo) · Degrau: 1 (ASSUM-4: tolerância declarada onde se calcula a mesma coisa) e 5
Base: identidade telescópica (derivação); evaluation §2.2, §2.3, §3.1, §4.5 (as definições de métrica)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim, até a 8.1 rodar

[decision:C] EQ-DESC — números do modelo
Escolha (mecânica de B2): deltas por horizonte com sinal; divergência de sentido = muda o sinal de (candidato − baseline) num nível comum, o lado do nominal do PICP 80 % ou o sentido do DM; sem explicação → [finding]; no DM e nas grandezas só agregadas a condição (c) é dispensada · Alternativas: TOST com margem; z em unidades de dispersão entre seeds com |z| > 2 (versão anterior deste doc); tolerância absoluta ou relativa · Degrau: 1 (evaluation §6.10 conv. 15; §8.5 B2)
Base: ICH E9 §3.3.2 (p. 18 da versão EMA CPMP/ICH/363/96; p. 15 impressa da versão ICH) "An equivalence margin should be specified in the protocol … The choice of equivalence margins should be justified clinically"; "two simultaneous one-sided tests"; Bouthillier et al. 2021 §7 "much smaller than the variance due to perturbing the split of the data in train and test sets" (a escala de seed não discrimina modelos diferentes); P(|t₉| > 2) ≈ 0,077 com 10 seeds (derivação)
Verificado: parcial→corrigido (paginação do ICH; localizador e leitura de Bouthillier)
Sensibilidade pré-registrada: nenhuma · Reversível: sim, até a 8.1 rodar

[decision:C] EQ-EXPL — o que conta como divergência explicada
Escolha: (a) categoria do catálogo fechado com sentido/previsão identificável, aplicável à comparação pela tabela da §5.6 (fixada antes da 8.1) + (b) compatibilidade + (c) localização pela decomposição; features/dados/hiperparâmetros não explicam sozinhos; pilha numérica não explica modelo; defeito do anterior só com referência; não explicada → [finding] listado no relatório, sem bloquear a 8.2, salvo indício de defeito na pipeline nova em A1/A2 · Alternativas: julgamento caso a caso; "diferença pequena"; catálogo aberto · Degrau: 1
Base: roadmap 8.2 DoD "divergências explicadas pela teoria (não 'bate com o antigo')"; overview §2 (oráculo, nunca autoridade; bug conhecido do anterior)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] EQ-ANDAIME — andaime interino e teste de equivalência
Escolha: aposentar quando as comparações estão registradas com hashes, nada oficial depende dele e o motivo está registrado; o teste de equivalência é pulado (skip com motivo) sem os arquivos do oráculo, falha com hash divergente, e não é gate de CI; o registro durável é o relatório · Alternativas: script de auditoria fora da suíte de testes (contraria o arquivo previsto no roadmap); teste sempre ativo (quebra o CI sem o oráculo) · Degrau: 1 (roadmap 8.2 prevê o teste) e 5
Base: roadmap 8.2 "justificar aposentadoria de qualquer andaime interino"; overview §4 (reconstrução sem re-treino); Sandve et al. 2013 Rule 4
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] P8-ROT — estatuto e rótulo dos números e gráficos
Escolha: confirmatório = só a árvore pré-registrada nos horizontes em que se aplica (H2 só onde H1 passa); descritivo = perfil pré-registrado, H3, conformal; exploratório = o resto; rótulo por elemento; DM do relatório = candidato × comparadores (p bruto + Holm, retangular), sem células comparador × comparador · Alternativas: rotular por gráfico inteiro; matriz completa de DMs par a par (teste novo, não persistido)
Base: Wagenmakers et al. 2012 p. 632 "Other analyses can be carried out but these should be labeled 'exploratory'"; ICH E9 §5.1 "Only results from analyses envisaged in the protocol (including amendments) can be regarded as confirmatory" (ambos via evaluation §8.1/§8.3); ADRs 6.5.0006, 6.5.0007, 6.5.0008
Verificado: sustenta
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] P8-FAN — que previsão a série OOS desenha
Escolha: uma seed pré-declarada (a primeira da lista do cohort), rotulada ilustrativa · Alternativas: média dos quantis entre seeds; envelope de todas as seeds · Degrau: 1 (evaluation §6.9: ensemble é outro objeto; ADR 7.4.0001 serve por seed sem agregar) e 5
Base: evaluation §6.9 (B-SEEDS); FPP3 §5.5 (forma do gráfico)
Verificado: sustenta (FPP3)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] P8-PERSIST — origem e forma dos plots
Escolha: de dado persistido identificado no dossiê, por horizonte, rótulo por elemento, nenhum teste novo · Alternativas: recomputar no plot · Degrau: 1
Base: Sandve et al. 2013 Rule 7 "As a minimum, one should note which data formed the basis of a given plot and how this data could be reconstructed"; overview §4; evaluation §8.7
Verificado: sustenta (Rule 7)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] DOSSIE — conteúdo mínimo do dossiê
Escolha: a tabela da §7 (Rules 1, 3–9 + desvios, computação pré-âncora, cegamento, poder declarado); Rule 10 como aspiração · Alternativas: só run_ids e hashes (texto do roadmap) · Degrau: 3
Base: Sandve et al. 2013, Rules 1, 3, 4, 5, 6, 7, 8, 9 (trechos na §7); ADRs 6.5.0003 item 4, 6.5.0006, 6.5.0010; Nosek et al. 2018 "Challenge 1"
Verificado: sustenta (Rules)
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

### 9.2 Rodada de revisão (2026-10-22)

Uma verificação adversarial de citações e uma revisão de completude, ambas de
contexto zerado, foram aplicadas a esta versão. Mudanças de escolha
(re-triadas pela skill): **EQ-TOL removida** (a escala por dispersão entre
seeds não mede equivalência entre modelos diferentes; virou alternativa
descartada de EQ-DESC); **EQ-MUST criada** (a tolerância declarada se aplica
ao alvo e ao código de métrica); **EQ-INTER** — o DM não é recomputado, só o
reportado é comparado, sem cruzar Holm; **EQ-EXPL** — catálogo restrito a
categorias com sentido identificável, defeito só com referência, fechamento
com `[finding]` não explicado; **P8-ROT** — DM do relatório só candidato ×
comparadores e confirmatório só onde H1 passa; **R-ENV** — piso absoluto fixo
trocado pela unidade natural u_q; **R-BIT** — regra do commit posterior
(R-BIT-COMMIT) e preservação da geração julgada (R-PRESERVA); **R-CAMADAS** —
hash de conteúdo do silver na identidade. Correções de citação: localizador
da raiz quadrada em Goldberg; base das transcendentais; paginação do ICH E9
(a versão EMA, citada em evaluation, tem §3.3.2 nas pp. 17–18 — a paginação
daquele doc está certa para a versão que ele cita, e ganhou a indicação de
versão); localizador e leitura de Bouthillier (§1 para a recomendação de
considerar variância; §7 para a variância de seed ser pequena frente à de
split); origem da razão "a tolerância esconde defeito" (ADR 7.1.0003 alt. A).
O roadmap da 8.2 foi emendado (DoD, non_goals, arquivos), ancorado em B1.

Segunda rodada (re-revisão independente, 2026-10-22): obrigações da 8.1 levadas
ao bloco do roadmap (geração julgada preservada; hash de conteúdo do silver);
o lock de dependências é ambiente, não caminho de cálculo; a capacidade de CPU
entra na definição de mesmo ambiente (o ADR 7.1.0003 a registra sem usá-la
como chave) e uma diferença diagnosticada cai nas classes da §4.3; u_q
redefinida por grandeza na sua escala natural (σ_y² dava 1–4 % para
var(d̄)); o DM e as grandezas só agregadas tiveram a localização dispensada; a
aplicabilidade das categorias por comparação foi fixada na §5.6; o candidato é
pareado por papel. A relação entre a tolerância da ASSUM-4 e os números do
modelo foi decidida pelo humano em seguida (B2, ADR 0.0.0062): numérica onde a igualdade é esperada, sentido nos números do modelo, divergência de sentido sem explicação → `[finding]`.

## 10. Referências

Separadas em (10.1) já ratificadas no projeto, (10.2) novas deste doc
(registradas no overview §10 no mesmo PR, conforme ADR 0.0.0003) e (10.3)
documentação de linguagem e biblioteca.

### 10.1 Já ratificadas (overview §10, docs de domínio e ADRs)

- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple Rules for Reproducible Computational Research". *PLOS Computational Biology*, 9(10), e1003285. DOI: 10.1371/journal.pcbi.1003285. (Rules 1–10; lido no HTML da PLOS em 2026-10-22.)
- Goldberg, D. (1991). "What every computer scientist should know about floating-point arithmetic". *ACM Computing Surveys*, 23(1), 5–48. DOI: 10.1145/103162.103163. (§The IEEE Standard, subseção *Operations* — operações e raiz quadrada exatamente arredondadas, transcendentais não; lido na reimpressão da Oracle, *Numerical Computation Guide*, Appendix D.)
- ICH (1998). *E9 — Statistical Principles for Clinical Trials*. CPMP/ICH/363/96 (EMA). (§3.3.2 pp. 17–18 da versão EMA — os trechos da margem e dos "two simultaneous one-sided tests" na p. 18; na versão do site da ICH, database.ich.org/sites/default/files/E9_Guideline.pdf, §3.3.2 = pp. 14–16 impressas, trechos na p. 15; §5.1 via evaluation §8.1–§8.2.)
- Nosek, B. A.; Ebersole, C. R.; DeHaven, A. C.; Mellor, D. T. (2018). "The preregistration revolution". *PNAS*, 115(11), 2600–2606. DOI: 10.1073/pnas.1708274114. (Via evaluation §8.)
- Wagenmakers, E.-J. et al. (2012). "An Agenda for Purely Confirmatory Research". *Perspectives on Psychological Science*, 7(6), 632–638. DOI: 10.1177/1745691612463078. (p. 632, via evaluation §8.3.)
- Bouthillier, X. et al. (2021). "Accounting for Variance in Machine Learning Benchmarks". *Proceedings of MLSys*, 3, 747–769. arXiv:2103.03098. (§1, recomendação 2 — "account for variance"; §7 Conclusion — variância de inicialização "much smaller than the variance due to perturbing the split".)
- Gneiting, T.; Raftery, A. E. (2007). "Strictly Proper Scoring Rules, Prediction, and Estimation". *JASA*, 102(477), 359–378. DOI: 10.1198/016214506000001437. (§1; §9.3 — via evaluation §2.2, §4.6.)
- Gneiting, T.; Balabdaoui, F.; Raftery, A. E. (2007). "Probabilistic forecasts, calibration and sharpness". *JRSS B*, 69(2), 243–268. DOI: 10.1111/j.1467-9868.2007.00587.x. (Thm 2; §3.3 — via evaluation §4.1, §4.3.)
- Gneiting, T.; Ranjan, R. (2011), Kuleshov, Fenner & Ermon (2018), Brown, Cai & DasGupta (2001), Bröcker & Smith (2007), Pearce et al. (2018), Diebold & Mariano (1995), Harvey, Leybourne & Newbold (1997), Holm (1979), Diebold (2015), Berrisch & Ziel (2023), NIST DLMF §8.17 — citações completas em evaluation §11.
- Hyndman, R. J.; Athanasopoulos, G. (2021). *Forecasting: Principles and Practice*, 3rd ed., OTexts. (§5.5 "Distributional forecasts and prediction intervals", subseção "Benchmark methods" — forma do gráfico de intervalos.)
- Lim et al. (2021), Angelopoulos & Bates (2023) — citações completas em inference §11.

### 10.2 Novas deste doc

- Schuirmann, D. J. (1987). "A comparison of the Two One-Sided Tests Procedure and the Power Approach for assessing the equivalence of average bioavailability". *Journal of Pharmacokinetics and Biopharmaceutics*, 15(6), 657–680. DOI: 10.1007/BF01068419. `[CITAÇÃO-NÃO-ACESSADA]` (metadados conferidos no Crossref; origem do TOST, citada só como referência histórica — o que é load-bearing é o ICH E9 §3.3.2.)

### 10.3 Documentação de linguagem e biblioteca (mecânica, não teoria)

- **Python 3.12** (versão da imagem do projeto): `Doc/library/random.rst` §Notes on Reproducibility ("By reusing a seed value, the same sequence should be reproducible from run to run as long as multiple threads are not running"; "Most of the random module's algorithms and seeding functions are subject to change across Python versions, but two aspects are guaranteed not to change … The generator's random() method will continue to produce the same sequence when the compatible seeder is given the same seed"); `Doc/library/math.rst` (`isclose`: "rel_tol=1e-09, abs_tol=0.0", "The default tolerance is 1e-09, which assures that the two values are the same within about 9 decimal digits"; nota *impl-detail*: "The math module consists mostly of thin wrappers around the platform C math library functions"); `Doc/whatsnew/3.12.rst` §Other Language Changes ("sum() now uses Neumaier summation to improve accuracy and commutativity when summing floats or mixed ints and floats").
- **NumPy 2.5.0** (pinado no lock): `doc/source/reference/random/compatibility.rst` ("If you create a Generator with the same BitGenerator, with the same seed, perform the same sequence of method calls with the same arguments, on the same build of numpy, in the same environment, on the same machine, you should get the same stream of numbers. Note that these conditions are very strict"; "different CPUs implement floating point arithmetic differently, and this can cause differences in certain edge cases that cascade to the rest of the stream"; "Breaking stream-compatibility in order to introduce new features or improve performance in Generator or default_rng will be allowed with caution").
