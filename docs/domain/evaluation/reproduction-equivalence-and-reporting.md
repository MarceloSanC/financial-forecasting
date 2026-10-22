---
title: Reprodução, equivalência e relatório — teoria do Step 8 (corrida confirmatória, reprodução da corrida, auditoria de equivalência, plots canônicos e dossiê)
description: Teoria canônica do subdomínio reproduction-equivalence-and-reporting — o que a corrida confirmatória executa (por ponteiro), o que significa reproduzi-la a partir dos artefatos persistidos (bit a bit no mesmo ambiente, por classe entre ambientes), como se audita a equivalência com a evidência confirmatória anterior na interseção comum com tolerância declarada em unidades de dispersão entre seeds, o que conta como divergência explicada pela teoria, que estatuto e rótulo cada plot canônico carrega e o conteúdo mínimo do dossiê de rastreabilidade
when-use: Consultar antes de escrever o concept.md de qualquer Stage do Step 8 (8.1–8.3), ao questionar o que a reprodução da corrida promete, qual tolerância vale entre ambientes, como comparar a pipeline oficial com a evidência anterior, que rótulo um gráfico do relatório leva, ou o que o dossiê final tem de listar
keywords: [domain, evaluation, reproducibility, reproduction, bitwise, tolerance, floating-point, ieee-754, rng-stream, equivalence-audit, prior-evidence, regression-oracle, seed-dispersion, tost, explained-divergence, scaffold-retirement, plots, reliability-diagram, quantile-score-plot, sharpness-diagram, picp-mpiw, dm-matrix, fan-chart, h3, conformal, traceability-dossier, sandve, per-horizon, editorial-policy]
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
  - ../../adr/0_0_0011-preregistration-invariants-and-h1-gate.md
  - ../../adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md
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
> `[SEM-FONTE-PRIMÁRIA]` e a regra vira convenção (§9); contas feitas para
> este doc são marcadas como **derivação**. As bifurcações do gate foram
> triadas pela skill `evidence-resolution` (2026-10-22): as de classe E/C
> foram fechadas pelo agente e registradas em §9.1 no formato
> `[decision:E|C]`; a de classe P (o que a 8.2 compara — **B1**) foi decidida
> pelo humano na issue #208 (2026-10-22), e a política editorial do TCC é
> decisão do humano anterior a este gate. Todas as convenções são anteriores
> a qualquer dado confirmatório (a 8.1 não rodou), então nenhuma C virou P.
> Doc aceito em 2026-10-22 (`status: accepted`) — gate do Step 8.

## 1. Escopo e como consumir este doc

**Cobre** os três blocos do Step 8, todos sobre o mesmo objeto — a **geração
julgada**: o gold e o scorecard que a 8.1 produz do cohort persistido, por
horizonte (§2.1):

1. **corrida confirmatória (8.1)** — só ponteiros: o que ela executa e em que
   ordem teórica (§3);
2. **reprodução e equivalência (8.2)** — (i) a **reprodução da própria
   corrida** a partir dos artefatos persistidos, que é o claim citável no TCC
   (§4); (ii) a **auditoria de equivalência** da pipeline oficial com a
   evidência confirmatória anterior, na interseção comum, como auditoria
   interna do repositório (§5);
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
| 8.1 — corrida confirmatória | §3 (ponteiros), §2.1–§2.2, §4.5 (o que a 8.1 precisa registrar para ser reproduzível), §7 (o que o dossiê vai pedir) |
| 8.2 — reprodução e auditoria de equivalência | §4 (reprodução), §5 (equivalência), §2 |
| 8.3 — plots canônicos e dossiê | §6 (plots), §7 (dossiê), §2.3 (rótulos), §2.4 |
| todas | §2 (fundamentos), §8 (fronteira), §9 (convenções) |

**Hierarquia de fontes.** Overview > Roadmap > Domain (este doc, o de
avaliação e o de inferência) > `concept.md` das Stages. O que já estava
ratificado no repo (overview §2–§4/§8/§10; evaluation §2/§4/§6/§8; inference
§3/§4.11/§5.7–§5.8/§7; ADRs 0.0.0011, 6.5.0003, 6.5.0007, 6.5.0008, 7.1.0003,
7.3.0005) é citado como tal e **não** re-derivado; a pesquisa externa entrou
só nas lacunas (forma da tolerância entre ambientes, garantias dos geradores
aleatórios, equivalência sem margem), sob a barra de fontes do gate
(`PROMPT-step-single-session.md` §1).

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
reprodução é comparada (§4). Ela não é re-escrita por nenhuma etapa
posterior: a reprodução **compara-se a ela**, nunca a substitui (§4.6).

### 2.2 Três camadas de um artefato: entrada, resultado, proveniência

Todo artefato da cadeia tem três tipos de campo, e cada um tem um tratamento
diferente na reprodução e no dossiê:

| Camada | Exemplos | Papel | Na reprodução |
|---|---|---|---|
| **identidade da entrada** | hash do cohort, `preregistration_ref` e hash de cada revisão r0–r3, `feature_set_hash`, `split_fingerprint`, `config_signature`, fingerprint do dataset, `run_id` | prova **qual** entrada foi usada | têm de ser **iguais** — senão não é reprodução, é outra corrida |
| **resultado** | valores das tabelas gold por chave, campos do scorecard, contagens, decisões | o que se afirma | comparados bit a bit ou por tolerância (§4.2–§4.4) |
| **proveniência** | timestamps, id da geração, host, URL do comentário de âncora | quando/onde foi feito | **esperado que difiram**; excluídos da comparação, registrados no dossiê |

Um hash **identifica** uma entrada, não certifica um resultado: igualdade de
hash prova que a reprodução partiu do mesmo dado e da mesma configuração; a
igualdade do resultado é o que a reprodução testa (Sandve et al. 2013, Rule 1:
"For every involved step, you should ensure that every detail that may
influence the execution of the step is recorded … the critical details include
the name and version of the program, as well as the exact parameters and inputs
that were used").

### 2.3 Estatuto de cada número: confirmatório, descritivo, exploratório

Toda tabela e todo gráfico do Step 8 declara o estatuto do que mostra, com
**três** rótulos (convenção **P8-ROT**, §9.1):

- **confirmatório** — só os elementos da árvore de decisão pré-registrada
  (evaluation §8.6; ADR 6.5.0007): o gate H1 (cada cauda do par primário na
  banda de Wilson 97,5 % + taxa de degeneração ≤ limiar), as decisões de Holm
  na família do horizonte, a pertença ao MCS ao nível α_MCS, o desfecho de H2,
  o vencedor primário e o critério "≥ 1 horizonte". Base: "Only results from
  analyses envisaged in the protocol (including amendments) can be regarded as
  confirmatory" (ICH E9 §5.1, via evaluation §8.1);
- **descritivo** — o que o pré-registro declara mas que **nunca troca o
  veredito**: o perfil (ADR 6.5.0008; evaluation §8.6), a leitura de H3 (regra
  mecânica com conclusão descritiva — inference §5.8, C7) e o benchmark
  conformal (inference §4.11, B8). H3 e conformal carregam, além disso, a
  frase obrigatória do seu doc: linguagem estritamente descritiva (H3) e
  **"cobertura empírica (não garantida)"** (conformal);
- **exploratório** — tudo o que **não** está declarado no pré-registro: "Other
  analyses can be carried out but these should be labeled 'exploratory'"
  (Wagenmakers et al. 2012, p. 632, via evaluation §8.3).

Um gráfico que mistura estatutos rotula **cada elemento** (ex.: no reliability
diagram, as caudas do par primário são do gate; os demais níveis são perfil —
§6.2).

### 2.4 Por horizonte, seeds como réplicas (ponteiro)

Toda grandeza deste doc é **por horizonte**, nunca agregada entre horizontes
(overview §7; evaluation §2.7, §8.7). Seeds são réplicas do mesmo ponto
alinhado: perdas entram como média ponto a ponto, coberturas como média entre
seeds com n ≈ T, e a dispersão entre seeds é perfil (evaluation §6.9, §8.4;
B-SEEDS). O GBM é determinístico e entra com uma execução; os baselines não
têm seed (evaluation §6.9). A §5.5 usa essa mesma dispersão como **unidade** da
tolerância de equivalência.

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
| 5 | Veredito **por horizonte**: H1 (gate, só o candidato) → H2 (i) supera os naive, (ii) supera/empata os fortes, (iii) MCS complementar → vencedor primário | árvore pré-registrada aplicada mecanicamente; perfil nunca troca o veredito | evaluation §8.5–§8.8 (B-GATE-H1, conv. 26–28); ADRs 6.5.0007, 6.5.0010 |
| 6 | H3: regra de leitura mecânica (C4 + C5), conclusão descritiva, **separada** de H1 → H2 | não altera o veredito | inference §5.7–§5.8; ADRs 0.0.0007, 7.3.0005 |
| 7 | Conformal como eixo comparativo descritivo, mesmas definições de cobertura | "cobertura empírica (não garantida)"; nenhum teste novo | inference §4.11 (B8), §4.13; ADR 0.0.0008 |
| 8 | Critério de sucesso do estudo: "≥ 1 horizonte" com H1 não rejeitado, com o poder declarado | não é agregação | evaluation §8.8 (T11); overview §4 |

O que a 8.1 precisa **registrar** para que a 8.2 consiga reproduzi-la e a 8.3
consiga documentá-la está em §4.5 e §7 — é a única contribuição deste doc à
8.1.

## 4. Reprodução da própria corrida (Stage 8.2, parte i)

### 4.1 O que é reproduzir a corrida

Reproduzir a 8.1 é **re-executar a cadeia silver → gold → scorecard** a partir
dos artefatos persistidos (cohort, pré-registro, silver), **sem re-treino**
(overview §4, critério "Reprodutibilidade"; roadmap 8.1 DoD), e comparar o
resultado com a geração julgada (§2.1) campo a campo, na camada "resultado"
(§2.2). A reprodução das **predições** a partir dos checkpoints já foi provada
na 7.1 — 60 runs em modo `strict` com max |Δ| = 0 (ADR 7.1.0003; roadmap,
histórico de 2026-10-12) — e não é repetida como claim aqui; ela é o elo
anterior da mesma corrente.

A reprodução é o **claim citável** do Step 8 no TCC: "a evidência julgada é
reconstruída, a partir dos dados persistidos e no ambiente registrado, bit a
bit" (decisão B1 do humano; ADR 0.0.0061). O motivo de o claim ser
**exatidão** e não "aproximação" é o da Rule 6 de Sandve et al. (2013): "There
is a large difference between observing that a result has been reproduced
exactly or only approximately. While achieving equal results is a strong
indication that a procedure has been reproduced exactly, it is often hard to
conclude anything when achieving only approximately equal results."

### 4.2 No mesmo ambiente: bit a bit (R-BIT — evidência)

**Decisão (R-BIT, classe E, §9.1).** Com a mesma entrada (camada de
identidade igual), o mesmo código (mesmo commit, árvore limpa) e o **mesmo
ambiente pinado** (mesma imagem, mesmas versões de interpretador e
bibliotecas, mesma capacidade de CPU — as chaves não-código do ADR 7.1.0003),
**todo** campo da camada "resultado" tem de sair **igual bit a bit**, inclusive
os que dependem de números aleatórios. As fontes:

- **Aritmética.** "The IEEE standard requires that the result of addition,
  subtraction, multiplication and division be exactly rounded. That is, the
  result must be computed exactly and then rounded to the nearest
  floating-point number (using round to even)"; e "the IEEE standard requires
  that square root be exactly rounded" (Goldberg 1991, §The IEEE Standard —
  já ratificado, inference §3.1). A mesma sequência de operações sobre as
  mesmas entradas dá, portanto, os mesmos bits. As entradas do silver são
  lidas exatamente (float64 de float32 — ida e volta exata; ADR 7.1.0003).
- **Funções transcendentais** (log, exp, gamma incompleta das distribuições t
  e χ², quantil normal do Wilson): "The IEEE standard does not require
  transcendental functions to be exactly rounded because of the table maker's
  dilemma" (Goldberg 1991, mesma seção); no Python, "The math module consists
  mostly of thin wrappers around the platform C math library functions"
  (Python 3.12, `library/math`, nota *impl-detail*). No **mesmo** ambiente a
  biblioteca C é a mesma, logo o resultado também; entre ambientes, não
  (§4.3).
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

**Falha no mesmo ambiente é parada, não troca de critério.** Se algum campo
de resultado difere com as três condições acima satisfeitas, algo que as
chaves não capturam mudou (código, kernel, ordem de iteração, um dado
re-lido de outro lugar): registra-se um `[finding]` e diagnostica-se antes de
qualquer uso da geração reproduzida. Nunca se passa ao critério por tolerância
para "salvar" a reprodução — mesma regra do ADR 7.1.0003 item 6 (alternativa
H rejeitada lá), pela mesma razão: uma tolerância aceita um defeito cujo
efeito fique abaixo dela.

### 4.3 Entre ambientes: por classe de grandeza (R-ENV — convenção)

Quando o ambiente difere (outra versão do interpretador ou de biblioteca,
outra plataforma), o bit a bit **não** é prometido — exatamente o regime de
A1-TOL (inference §3.1) e de ASSUM-4 aplicado à cadeia de avaliação. Um
exemplo concreto do porquê: "`sum()` now uses Neumaier summation to improve
accuracy and commutativity when summing floats" (Python 3.12, *What's New*,
§Other Language Changes) — o **mesmo código-fonte** soma de outro jeito em
3.11 e em 3.12. Um ambiente diferente é, para a Rule 3 de Sandve, outro
programa: "In order to exactly reproduce a given result, it may be necessary
to use programs in the exact versions used originally".

**Convenção (R-ENV, classe C, §9.1).** A expectativa entre ambientes é
declarada **por classe** de grandeza:

| Classe | O que é | Critério entre ambientes |
|---|---|---|
| **R1 — discreta** | contagens (T, hits, violações, linhas degeneradas), decisões (gate, Holm, pertença ao MCS, desfecho de H2, vencedor, H3 sustentada), conjuntos e rótulos | **igualdade exata**; uma diferença é `[finding]`, salvo a exceção de fronteira abaixo |
| **R2 — contínua determinística** | toda grandeza contínua que não depende de número aleatório (pinball, CRPS_Q, IS, MPIW, PICP, d̄, variâncias HAC, estatísticas e p-valores analíticos, limites de Wilson, participações de H3 sobre perdas persistidas) | \|a − b\| ≤ max(10⁻⁹ · max(\|a\|, \|b\|), 10⁻¹²) |
| **R3 — dependente de aleatoriedade** | p-valores do MCS por bootstrap, p-valores de Monte Carlo, intervalos bootstrap de H3 | bit a bit se o gerador e sua versão forem os mesmos (o fluxo do `random.random()` do Python é garantido entre versões; o `Generator` do NumPy, só no mesmo build e máquina); senão, a diferença é reportada em unidades do erro de Monte Carlo (abaixo) |

- **R2.** O par de tolerâncias é o default documentado de `math.isclose` para
  a tolerância relativa — "The default tolerance is 1e-09, which assures that
  the two values are the same within about 9 decimal digits" (Python 3.12,
  `library/math`) — com o piso absoluto 10⁻¹² que o projeto já ratificou como
  ordem do ruído de soma em float64 (ADR 6.1.0001, notas de implementação:
  "float64 summation-order noise, order 1e-12"). O piso é necessário porque a
  tolerância só relativa falha perto de zero (a própria documentação: "isclose(x,
  0) … is False for any nonzero x"; d̄ e LR's podem valer ≈ 0) — o mesmo motivo
  da alternativa F rejeitada no ADR 7.1.0003. A escala do ADR 7.1.0003 (o par
  float32 do `assert_close` no espaço normalizado) **não** se transpõe: lá a
  rede computa em float32; aqui a cadeia de avaliação computa em float64 sobre
  entradas idênticas, e o ruído esperado é de arredondamento de float64, sete
  ordens abaixo. `[SEM-FONTE-PRIMÁRIA]` para o par como critério de
  reprodução — convenção (degraus 1 e 2).
- **R3.** Com o fluxo aleatório diferente, a estimativa de Monte Carlo
  p̂ = (contagem)/B muda por erro de Monte Carlo, de desvio-padrão
  √(p(1 − p)/B) (cada réplica é um indicador de Bernoulli — **derivação**
  elementar). A diferença é reportada como (p̂_novo − p̂_ref)/√(p̂_ref(1 −
  p̂_ref)/B); não é critério de aceitação, porque o claim do TCC é o do mesmo
  ambiente (§4.7). A Rule 6 de Sandve pede exatamente isso: "As a minimum, you
  should note which analysis steps involve randomness, so that a certain level
  of discrepancy can be anticipated when reproducing the results".
- **Exceção de fronteira (R1).** Uma decisão que muda entre ambientes só é
  "explicada" se a grandeza contínua que a decide estiver, nas duas corridas,
  a menos da tolerância da sua classe (R2) — ou, em R3, a menos de 2 erros de
  Monte Carlo — do limiar que a decide (ex.: p-valor de Holm a 10⁻¹² de α).
  Fora disso, é `[finding]`.

### 4.4 Rastreabilidade por hash

A igualdade da camada de identidade (§2.2) é **pré-condição** da reprodução e
se verifica por hash: o hash do cohort e das revisões do pré-registro (ADRs
5.5.0001, 6.5.0001) e os fingerprints do dataset e do split. A cadeia de
âncoras (tag + comentário com timestamp do servidor, ADR 6.5.0003) prova a
**ordem** pré-registro → avaliação; a reprodução, feita depois, não toca nem
re-ancora nada. O que o hash **não** prova: que o resultado é o mesmo (isso é
§4.2–§4.3) nem que o resultado está certo (isso é a suíte de contratos +
oráculo — ADR 0.0.0021).

### 4.5 O que a 8.1 precisa registrar (requisito de fronteira 8.1 → 8.2)

Para a reprodução ser possível sem adivinhação, a geração julgada tem de
carregar, por construção, tudo o que a §4.2 lista como condição: a camada de
identidade completa, o commit do código e o indicador de árvore limpa, o
ambiente (versões do interpretador e das bibliotecas que computam —
inclusive as que geram números aleatórios —, plataforma, capacidade de CPU) e
as seeds de cada etapa aleatória (Sandve et al. 2013, Rules 1, 3, 4 e 6). Boa
parte disso já é registrada pelo manifesto do gold e pelo do cohort (ADRs
6.4.0005, 7.1.0003, 7.1.0004); a 8.1 confere que nada falta — o *como* é do
`technical.md` dela.

### 4.6 A reprodução não substitui a evidência julgada

A geração julgada é a que o dossiê identifica e a que o TCC cita; a reprodução
é **comparada** a ela e o resultado da comparação é registrado (classe por
classe, com max |Δ| também quando passa — como o ADR 7.1.0003 item 5 faz para
as predições). Se a reprodução falha, a geração julgada **não** é trocada pela
reproduzida: o `[finding]` é diagnosticado primeiro, e qualquer correção que
mude um número confirmatório depois do hash é um **desvio do plano**, reportado
como tal ("desvios do plano são reportados" — Nosek et al. 2018, "Challenge 1",
via evaluation §8.3).

### 4.7 O claim citável

O que o TCC pode afirmar, nessa ordem de força: (a) **no ambiente registrado**,
a cadeia silver → gold → scorecard reproduz a geração julgada **bit a bit**,
inclusive as etapas aleatórias, porque as seeds estão registradas; (b) as
predições de teste reproduzem a partir dos checkpoints bit a bit (7.1); (c) em
outro ambiente, contagens e decisões são iguais e as grandezas contínuas
coincidem a menos de arredondamento de float64 (classe R2), com as etapas
aleatórias reprodutíveis na medida da garantia do gerador (R3). O item (c) só
é afirmado se tiver sido de fato executado; o TCC não promete reprodução que
não foi feita.

## 5. Equivalência com a evidência anterior (Stage 8.2, parte ii)

### 5.1 Papel: oráculo de regressão, nunca autoridade

A evidência confirmatória do projeto anterior serve "apenas como **oráculo de
equivalência/regressão**, com tolerância declarada — nunca como autoridade de
decisão" (overview §2, Estado atual). Três consequências:

1. **A pipeline oficial nunca é ajustada para "bater"** com o anterior. Uma
   divergência se explica (§5.7) ou vira `[finding]`; ela não muda método,
   parâmetro nem código do caminho oficial (non-goal da 8.2: "reabrir
   metodologia"; DoD: "divergências explicadas pela teoria (não 'bate com o
   antigo')").
2. **A comparação é simétrica no ônus da prova.** O anterior não é gabarito:
   ele tinha camada estatística artesanal "incluindo um bug conhecido"
   (overview §2, Problema). "O anterior está errado aqui, por este mecanismo"
   é uma explicação legítima — desde que o mecanismo seja demonstrado (§5.7).
3. **A evidência anterior nunca é entrada** do caminho oficial (overview §3,
   fora do escopo: "Reaproveitar dados derivados ou checkpoints de
   implementações anteriores"). Ela só é lida pela auditoria.

Pela política editorial (§1), o resultado desta auditoria fica no repositório;
o texto do TCC não a menciona.

### 5.2 Pré-requisito: congelar a evidência anterior por hash

**Convenção (EQ-HASH, classe C, §9.1).** Antes de **qualquer valor** da
evidência anterior ser lido pela auditoria, o conjunto de arquivos que servirá
de oráculo é **fixado por hash criptográfico do conteúdo** (um hash por
arquivo, mais a lista) e esse registro é **versionado no repositório** —
porque esses arquivos vivem fora do controle de versão do projeto (ficam
numa área de dados ignorada pelo git), e a Rule 4 de Sandve ("If computer code
is not systematically archived along its evolution, backtracking to a code
state that gave a certain result may be a hopeless task") e a Rule 1 (registrar
"the exact parameters and inputs that were used") só se cumprem para um
arquivo não versionado se a sua identidade for registrada. A auditoria lê
**só** arquivos cujo hash bate com o registro; arquivo que não bate é recusado,
não "atualizado".

**Ordem.** As regras de comparação (o que se compara, como se alinha, a
tolerância, o que conta como explicação) são as **deste doc**, fixadas antes de
a 8.1 rodar — portanto antes de qualquer número novo **ou** anterior ser
visto. O `technical.md` da 8.2, escrito depois da 8.1, só preenche a mecânica;
mudar uma regra deste bloco depois de ver os números é escolher a análise pelo
resultado — o *garden of forking paths* que o pré-registro existe para impedir
(Nosek et al. 2018: "the observed P value is diagnostic about its intended
likelihood only when analysis choices are made before observing data", via
evaluation §8.3) — e passa a ser decisão P do humano (skill
`evidence-resolution` §1), registrada como desvio.

### 5.3 O que se compara: a interseção comum

**Decisão do humano (B1, ADR 0.0.0061).** A comparação fica **restrita à
interseção comum** das duas evidências:

- **pinball por nível** em τ ∈ {0,1; 0,5; 0,9}, por (modelo comum, horizonte
  comum);
- **PICP e MPIW do par de 80 %** (0,1; 0,9), por (modelo comum, horizonte
  comum);
- **DM contra os baselines comuns**, por horizonte;
- **sentido do veredito** (abaixo).

Regras de alinhamento (convenção **EQ-INTER**, classe C, §9.1):

1. **Modelo comum é por definição, não por nome.** Um baseline só é comum se
   as duas definições (estimador, janela, parâmetros) forem declaradas
   equivalentes; mesmo nome com definição diferente entra só como divergência
   explicada pela categoria "definição do modelo" (§5.7) ou fica fora.
2. **Alinhamento por `target_timestamp` e horizonte, na interseção exata dos
   pontos presentes nas duas evidências** — o mesmo princípio do pareamento
   estrito do DM (evaluation §6.7, conv. 17). **Fold não é chave:** os cortes
   de fold podem não coincidir; um ponto é comparável se existe nas duas, qual
   fold for. T∩ é reportado por horizonte.
3. **Primeiro diagnóstico: o realizado.** Na interseção, o realizado y_t das
   duas evidências tem de coincidir (classe R2). Se não coincide, os alvos
   diferem (definição do retorno, ajuste de preço) e **toda** métrica difere
   por isso — a comparação para e a categoria "alvo" (§5.7) é a explicação a
   demonstrar, antes de qualquer outra.
4. **Grade: só os níveis comuns, sem reinterpolar.** Um nível ausente numa das
   grades não é reconstruído por interpolação: o score é função da previsão
   **quotada** (Gneiting & Raftery 2007, §1, via evaluation §2.2 razão 1) — um
   quantil interpolado é uma previsão que nenhuma das duas pipelines emitiu.
5. **Janelas que não coincidem:** compara-se a interseção; o que está fora dela
   (pontos só de uma das evidências) não entra, e a diferença de cobertura
   temporal é registrada como contexto. Se a interseção de um horizonte for
   vazia, aquele horizonte não tem comparação — registrado, não contornado.

**Sentido do veredito.** Para cada (horizonte, baseline comum): o **sinal** de
d̄ = L̄_cand − L̄_comp e a **rejeição** do DM unilateral ao α pré-registrado,
sem ajuste e — onde as duas famílias forem comparáveis — com Holm. É uma
comparação **categórica** (R1): igual ou não. O d̄ contínuo só é comparado
quando a loss pareada tem a mesma definição nas duas pipelines; como L_t = P̄_G
depende da grade G (evaluation §3.1, conv. 13), grades diferentes tornam d̄
incomparável e o DM fica só no sentido (**derivação**).

### 5.4 Decomposição em dois níveis: código de métrica × predição

Uma diferença total m_novo − m_ant mistura duas origens — o **código** que
calcula a métrica e as **predições** sobre as quais ele calcula. Quando a
evidência anterior traz as predições por ponto, a auditoria as separa com uma
grandeza intermediária m_A = **código novo aplicado às predições anteriores**,
na mesma interseção:

    m_novo − m_ant  =  (m_novo − m_A)   +   (m_A − m_ant)
                        predição           código de métrica

(identidade telescópica — **derivação**). O termo "código de métrica" deve ser
zero a menos de R2 quando as definições coincidem; o que sobra se explica por
definição de métrica (fator de escala, convenção de empate, pontuar bruto ou
rearranjado, amostra). O termo "predição" é o que a tolerância da §5.5 mede.
Quando só existem valores agregados do anterior (sem predições por ponto), a
decomposição não é possível: compara-se só o total, e a lista de explicações
admissíveis é declarada mais curta. A decomposição **localiza** a divergência;
é ela que torna uma explicação verificável (§5.7, condição c).

### 5.5 A escala da tolerância: unidades de dispersão entre seeds

**Convenção (EQ-TOL, classe C, §9.1).** Para cada grandeza comparada m (por
horizonte e nível/par), a diferença no termo "predição" (§5.4) — ou no total,
quando não há decomposição — é medida em **unidades da dispersão entre seeds**:

    z = (m_novo − m_ref) / σ_Δ,     σ_Δ = s_b · √(1/S_novo + 1/S_ant)

onde s_b é o desvio-padrão, **entre as seeds do cohort novo**, da mesma
grandeza calculada por seed na mesma interseção; S_novo, S_ant são os números
de seeds que cada valor médio agregou (o termo 1/S_ant é omitido se o anterior
não registra quantas seeds agregou — a escolha que **encolhe** σ_Δ e,
portanto, sinaliza mais). A regra de leitura:

- **|z| ≤ 2** → "dentro da tolerância declarada";
- **|z| > 2** → **divergência a explicar** (§5.7).

**Por que essa unidade.** O anterior e o novo são **re-treinos** do mesmo tipo
de modelo com outra pilha numérica (ASSUM-4); a variação mínima que um
re-treino carrega é a da seed — "Deciding of whether the benchmarks give
evidence that one algorithm outperforms another should not build solely on
comparing average performance but account for variance" (Bouthillier et al.
2021, §5, via evaluation §8.4). Na interseção, os pontos e os realizados são os
mesmos nos dois lados, então a variância **de amostragem dos dados** se cancela
no pareamento e o que resta é a do treino (**derivação**); a fórmula de σ_Δ é a
variância da diferença de duas médias independentes (**derivação**
elementar). Alternativas rejeitadas, com a fonte de cada rejeição:

- **tolerância absoluta δ** — sem fonte que fixe δ e cega à escala da grandeza;
  o projeto já rejeitou a mesma forma para as bandas de H1 (evaluation §4.4,
  alt. (i));
- **tolerância relativa** — instável perto de zero (d̄ e a pinball na mediana
  podem ser ≈ 0); mesmo motivo da alternativa F do ADR 7.1.0003;
- **múltiplos da dispersão entre folds** — folds são **períodos diferentes**:
  sua dispersão mede heterogeneidade temporal, não ruído de réplica, e na
  interseção a comparação é ponto a ponto, não fold a fold (evaluation §6.8:
  o DM por fold é perfil de estabilidade temporal).

**Modelos determinísticos.** Para o GBM (uma execução, determinístico) e os
baselines (sem seed), s_b = 0: **não há ruído de réplica**. Com a mesma
definição, os mesmos pontos e o mesmo realizado, o valor tem de coincidir a
menos de R2 (§4.3); **qualquer** diferença maior é divergência a explicar.
Esses modelos são, por isso, o teste mais forte da auditoria.

**O limiar 2.** Sob equivalência e aproximação normal da média de S seeds, |z| >
2 ocorre por acaso em ≈ 4,6 % das grandezas do candidato (**derivação**):
alguns sinais são esperados mesmo sem problema. O limiar **não** é teste e não
recebe correção de multiplicidade — ele decide só **o que precisa de
explicação**; o z contínuo de toda grandeza é reportado. `[SEM-FONTE-PRIMÁRIA]`
para o 2 — convenção (degrau 5).

### 5.6 Comparação descritiva, não teste de equivalência

**Convenção (EQ-DESC, classe C, §9.1).** A auditoria é **descritiva** — z por
grandeza, sinal e rejeição do DM, classificação de cada divergência — e **não**
usa teste formal de equivalência (TOST; Schuirmann 1987
`[CITAÇÃO-NÃO-ACESSADA]`). O TOST exige uma margem fixada por razão
substantiva: "An equivalence margin should be specified in the protocol; this
margin is the largest difference that can be judged as being clinically
acceptable … The choice of equivalence margins should be justified
clinically", e opera como "two simultaneous one-sided tests to test the
(composite) null hypothesis that the treatment difference is outside the
equivalence margins" (ICH E9, §3.3.2, pp. 14–15 do PDF da ICH). Aqui não
existe razão substantiva para margem nenhuma — o mesmo motivo pelo qual o
projeto não adotou TOST em H2 (evaluation §6.10, conv. 15) nem a equivalência
B2 em H1 (evaluation §8.5); e a parte (ii) não sustenta claim do texto
(política editorial), então um teste formal não compraria rigor para nenhuma
conclusão publicada. Consequência de redação, herdada de evaluation §6.10:
"dentro da tolerância declarada" **não** é "equivalência demonstrada".

### 5.7 Divergência explicada pela teoria

**Convenção (EQ-EXPL, classe C, §9.1).** Uma divergência (|z| > 2; diferença
além de R2 num modelo determinístico; sentido de veredito diferente; realizado
diferente) conta como **explicada** se, e só se, as três condições valem:

- **(a) diferença declarada** — é atribuída a uma diferença concreta e
  registrada entre as duas pipelines, de um catálogo fechado:

  | Categoria | Mecanismo que a teoria dá | Onde está a teoria |
  |---|---|---|
  | alvo (definição do retorno, ajuste de preço) | todo y muda; toda métrica muda | §5.3 item 3; ADR 3.5.0001; modeling §2.1 |
  | grade (níveis, número de níveis) | P̄_G e d̄ mudam de definição; só os níveis comuns são comparáveis | evaluation §3.1; §5.3 |
  | pontuar bruto × rearranjado | na soma da grade, o rearranjado nunca é pior; **por nível**, sem garantia de sentido | evaluation §2.2 (Lorentz; Berrisch & Ziel 2023 §3.4) |
  | escala da pinball (fator 2) | razão exata 2 | evaluation §2.3, conv. 4 |
  | convenção de empate y = q̂ | só nos indicadores de cobertura, só nos empates | evaluation §4.5 |
  | janela, folds, T | amostra diferente; fora da interseção não se compara | §5.3; evaluation §6.7–§6.8 |
  | seeds (número, agregação — média das perdas × ensemble) | ensemble tem perda ≤ média das perdas (Jensen) | evaluation §6.9 (B-SEEDS) |
  | features/famílias, dataset re-derivado | predições diferentes | ADR 0.0.0016; overview §2 |
  | definição do modelo comparador | outro modelo | §5.3 item 1 |
  | estimador do DM (lag, kernel, HLN, fallback de variância), família de Holm | estatística e decisão diferentes com a mesma d̄ | evaluation §6.1–§6.4 (conv. 13, 14, 14b) |
  | pilha numérica | diferenças da ordem do ruído de réplica | ASSUM-4; §5.5 |
  | defeito conhecido do anterior | o mecanismo do defeito | overview §2 (Problema) |

- **(b) mecanismo e sentido** — a teoria dá o mecanismo e, quando existe, o
  **sentido ou o limite** do efeito (ex.: o fator 2 prevê a razão exata; o
  rearranjo prevê o sentido só na soma da grade; Jensen prevê o sentido entre
  média das perdas e ensemble); o efeito observado é compatível com ele;
- **(c) localização** — a decomposição da §5.4 põe a divergência no nível que
  a explicação prevê (definição de métrica → termo "código de métrica";
  modelo, dados, pilha → termo "predição"), ou, com o realizado, no alvo.

O que **não** é explicação: "bate com o antigo" (DoD da 8.2), "diferença
pequena", "a nova pipeline está certa" sem mecanismo, ou uma categoria fora do
catálogo sem demonstração. Divergência não explicada é registrada como
`[finding]` com a decomposição e o z; não bloqueia o veredito da 8.1 (que é da
geração julgada), mas tem de ser investigada antes de o relatório de
equivalência ser fechado — e, se a investigação achar um defeito na pipeline
nova, a correção segue o processo normal e é **desvio** reportado (§4.6). Uma
categoria nova só entra no catálogo por emenda deste doc, com a teoria do seu
mecanismo — nunca como explicação *ad hoc* de uma divergência já vista.

### 5.8 Aposentadoria de andaime interino

"Andaime interino" é todo artefato — código, teste, leitor, fixture, cópia de
dado — que existe **só** para ligar a pipeline oficial à evidência anterior.
**Convenção (EQ-ANDAIME, classe C, §9.1).** Um andaime é aposentado quando:

1. o relatório de equivalência registra cada comparação que ele serviu, com os
   hashes dos dois lados (§5.2) e a classificação final (dentro da tolerância
   / explicada, com a categoria / `[finding]`);
2. nenhum resultado oficial depende dele — a cadeia oficial se reconstrói a
   partir dos dados persistidos sem ele (overview §4, critério
   "Reprodutibilidade"); e
3. a aposentadoria e o motivo ficam registrados no relatório.

Um andaime necessário para investigar um `[finding]` aberto só se aposenta
quando o `[finding]` fecha. E uma comparação cujo oráculo vive fora do
controle de versão não é um teste reprodutível de regressão contínua — o
registro durável é o **relatório com os hashes**, não um teste que só roda numa
máquina que tem os arquivos (Sandve et al. 2013, Rule 4). Um andaime que tenha
entrado no caminho oficial viola §5.1 item 3 e sai, não "se aposenta".

## 6. Plots canônicos (Stage 8.3)

### 6.1 Regras comuns

1. **Reconstrutível de dado persistido.** Todo gráfico é desenhado a partir da
   geração julgada (gold) ou do dado persistido de onde ela foi construída
   (predições e realizado do silver), identificado no dossiê — nunca de um
   re-treino nem de um cálculo que não deixou rastro. Sandve et al. 2013, Rule
   7: "As a minimum, one should note which data formed the basis of a given
   plot and how this data could be reconstructed"; overview §4: "artefatos de
   decisão reconstruíveis a partir de dados persistidos sem re-treino".
2. **Por horizonte, sem agregar.** Um painel por horizonte; nada mistura
   horizontes num mesmo número ou curva (evaluation §8.7). Pôr h+1 e h+7 lado a
   lado para **comparar** (como H3 exige) não é agregar.
3. **Rótulo de estatuto** (§2.3) em todo gráfico, por elemento quando
   misturado, mais a frase obrigatória de H3 e do conformal.
4. **Seeds.** Grandezas do candidato seguem B-SEEDS (média entre seeds; n ≈ T).
   Onde o gráfico precisa de **uma** previsão por ponto (série OOS), ele não
   desenha a média dos quantis entre seeds — isso é um ensemble, outro objeto
   (evaluation §6.9) — e sim uma seed **pré-declarada** (§6.2, série OOS).
5. **O gráfico não decide nada.** Nenhum gráfico é critério; o critério é a
   árvore pré-registrada (evaluation §8.6). Um gráfico pode mostrar uma
   decisão; não produz uma.

### 6.2 Catálogo

| Gráfico | O que representa | Fonte primária | Estatuto e rótulo obrigatório |
|---|---|---|---|
| **Reliability diagram por τ** | {(τ_k, ĉ(τ_k))} por modelo e horizonte, pooled sobre folds, contra a diagonal; banda de Wilson por nível | GBR 2007 Thm 2; Kuleshov et al. 2018 §3.5 Eq. (8); bandas: Brown, Cai & DasGupta 2001 Eq. (4); Bröcker & Smith 2007 (barras de consistência) — via evaluation §4.1, §4.4 | **misto, rotulado por elemento**: as caudas do par primário (0,1; 0,9) do **candidato**, com a banda **97,5 %**, são o gate (**confirmatório**); os demais níveis e modelos, com a banda **95 %**, são **descritivos** (perfil). Aviso fixo: banda binomial anti-conservadora em h+7 e sob agrupamento (evaluation §4.4) |
| **Quantile score plot** | P̄_τ × τ por modelo e horizonte — onde (cauda × centro) o skill vive | Gneiting & Ranjan 2011 Eq. (23) (atribuído a Laio & Tamea 2007), via evaluation §3.1 | **descritivo** (perfil); a métrica primária é P̄_G, não a curva |
| **Sharpness diagram** | distribuição (box plot / quantis) das larguras u − l por par, modelo e horizonte, em unidade de y | GBR 2007 §3.3 ("we follow Bremnes (2004) in proposing box plots … sharpness diagram"), via evaluation §4.3 (conv. 8) | **descritivo**; legenda: "sharpness só tem sentido sujeito à calibração" (evaluation §2.6) |
| **PICP × MPIW** | um ponto por (modelo, par) e horizonte, com a reta do nominal 1 − 2τ_l e, para o candidato, a dispersão entre seeds | Pearce et al. 2018 §3 Eqs. (4)–(7) (definições), via evaluation §4.2; GR 2007 §9.3 ("a meaningful comparison of interval estimators requires either equal coverage or equal width"), via evaluation §4.6 | **descritivo**; legenda fixa: o gráfico **não ordena** modelos — mais estreito só é melhor com cobertura igual; nenhuma combinação largura × cobertura (CWC) é desenhada (evaluation §4.6, conv. 11) |
| **Matriz de p-valores do DM** | por horizonte, célula (i, j) = p-valor do DM unilateral "linha tem perda menor que coluna", na amostra comum | DM 1995; HLN 1997; Holm 1979 — via evaluation §6.1–§6.4; Wagenmakers et al. 2012 p. 632 | **misto**: a linha do candidato × os 6 comparadores da família, com a decisão **de Holm**, é **confirmatória**; **todas as outras células** (comparador × comparador) estão **fora da família pré-registrada** e são **exploratórias**, sem ajuste de multiplicidade, rotuladas como tal. Como a estatística troca de sinal, p_ji = 1 − p_ij fora dos casos de fallback (**derivação**) |
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
(2013) — a recomendação da fonte de origem (degrau 3):

| Conteúdo mínimo | Regra de Sandve et al. 2013 (trecho) |
|---|---|
| Por decisão/afirmação: `run_id`s, `config_signature`, `split_fingerprint`, fingerprint do dataset, `feature_set_hash`; id do cohort e do cohort de ablação com seus hashes e tags | Rule 1 — "For every involved step, you should ensure that every detail that may influence the execution of the step is recorded" |
| A cadeia do pré-registro: `preregistration_ref` e hash de r0, r1, r2, r3, tags e comentários de âncora (timestamp do servidor), revisão julgada, `blind_status` de cada emenda | Rule 1 (parâmetros exatos); evaluation §8.2 / ICH E9 §5.1 ("Formal records should be kept of when the statistical analysis plan was finalised") |
| A geração julgada: identificação da geração do gold e do manifesto lido, estado (`COMPLETED`), `academic_decision_ready` e os motivos de cada conjunção | Rule 5 — "archive any intermediate result files that are produced when running an analysis" |
| Ambiente: imagem, versões do interpretador e das bibliotecas que computam (inclusive os geradores aleatórios), hash do lock de dependências, plataforma e capacidade de CPU — o do treino (CPU), o da ablação (Linux/GPU, ADR 7.3.0004) e o da avaliação | Rule 3 — "As a minimum, you should note the exact names and versions of the main programs you use" |
| Commit do código de cada etapa e indicador de árvore limpa | Rule 4 — "only that exact state of the script may be able to produce that exact output" |
| Seeds de cada etapa aleatória: treino, MCS, Monte Carlo, permutação e bootstrap de H3 (ADRs 6.5.0009, 7.3.0005) | Rule 6 — "the random seed should be recorded" |
| Por gráfico: a tabela/chave de onde cada série sai e como se reconstrói | Rule 7 — "note which data formed the basis of a given plot and how this data could be reconstructed" |
| Por afirmação do texto: o ponteiro para o número exato (tabela, chave, campo) | Rule 9 — "Such a connection can for instance be a simple file path to detailed results, or the ID of a result in an analysis framework, included within the text itself" |
| Resultado da reprodução (§4): classe por classe, max \|Δ\|, ambiente da reprodução | Rule 6 (exato × aproximado) |
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
| evaluation §8.1–§8.8; ADRs 6.5.0003, 6.5.0007 | ordem, árvore do veredito, critério de sucesso | §3 |
| evaluation §2.2, §3.1, §6.7 | pontuar a previsão quotada; P̄_G depende de G; pareamento por interseção | §5.3 |
| evaluation §6.9, §8.4 (B-SEEDS) | seeds como réplicas; dispersão entre seeds | §2.4, §5.5, §6.1 |
| evaluation §4.1–§4.6 | reliability, PICP/MPIW, sharpness, Wilson, sem CWC | §6.2 |
| evaluation §6.10, §8.5 (B2) | não-rejeição ≠ equivalência; TOST não adotado | §5.6 |
| inference §3.1 (A1, A1-TOL); ADR 7.1.0003 | bit a bit no mesmo ambiente; tolerância entre ambientes | §4.2–§4.3 |
| inference §4.10–§4.11, §5.3–§5.8 | rótulos de conformal e de H3; VSN | §6.2 |
| overview §2, §3, §4, ASSUM-4, R-REPRO-1 | oráculo, não autoridade; reprodutibilidade sem re-treino | §4, §5 |

### 8.2 O que fica para o `technical.md`

Onde e como a reprodução re-executa e compara (sem substituir a geração
julgada); o formato do registro de hashes da evidência anterior e do relatório
de equivalência; os leitores da evidência anterior; a lista concreta das
categorias de explicação que se aplicam a cada grandeza; a forma do dossiê; a
biblioteca e o estilo dos gráficos; quais gráficos exploratórios extras
existem.

### 8.3 O que este doc não decide

O que se publica junto com o TCC (Rule 10); o texto do TCC; qualquer teste de
hipótese novo (nenhum é introduzido aqui); qualquer mudança no veredito ou no
pré-registro.

## 9. Convenções decididas (tabela-resumo)

Legenda: **[P]** decisão do humano; **[E]** evidência decide; **[C]**
convenção sem vencedor, fechada pelo degrau indicado; todas em §9.1.

| # | Convenção | Fonte / âncora | Status | Stage |
|---|---|---|---|---|
| 1 | A 8.2 faz as duas comparações: (i) reprodução da própria corrida = claim citável; (ii) oficial × anterior na interseção comum = auditoria interna | issue #208; overview ASSUM-4, R-REPRO-1 | [P] B1 (ADR 0.0.0061) | 8.2 |
| 2 | O TCC não menciona o projeto anterior; (ii) fica no repositório; nenhum gráfico compara com o anterior | decisão do humano (política editorial) | [P] P-EDIT | 8.2, 8.3 |
| 3 | Três camadas: identidade (hash, igual), resultado (comparado), proveniência (excluída) | Sandve 2013 Rule 1 | [C] R-CAMADAS, degrau 3 | 8.2, 8.3 |
| 4 | Mesmo ambiente → bit a bit em todo campo de resultado, inclusive aleatório; falha = parada, nunca troca para tolerância | Goldberg 1991; NumPy 2.5.0 compat. policy; Python 3.12 random; Sandve Rule 6; ADR 7.1.0003 item 6 | [E] R-BIT | 8.2 |
| 5 | Entre ambientes, por classe: R1 discreta exata; R2 contínua \|Δ\| ≤ max(10⁻⁹·max(\|a\|,\|b\|), 10⁻¹²); R3 aleatória bit a bit só com o mesmo gerador, senão em erros de Monte Carlo | Python 3.12 math.isclose; ADR 6.1.0001; Goldberg 1991; Python 3.12 What's New | [C] R-ENV, degraus 1/2 | 8.2 |
| 6 | Evidência anterior congelada por hash de conteúdo, registro versionado, antes de ler qualquer valor; regras fixadas antes da 8.1 | Sandve Rules 1, 4; Nosek 2018 | [C] EQ-HASH, degraus 1/3 | 8.2 |
| 7 | Interseção: modelo comum por definição; alinhamento por `target_timestamp` (fold não é chave); realizado conferido primeiro; níveis comuns sem reinterpolar; janela fora da interseção não entra | evaluation §2.2, §6.7; GR 2007 §1 | [C] EQ-INTER, degrau 1 | 8.2 |
| 8 | Decomposição código de métrica × predição via código novo sobre predições anteriores | derivação | [C] EQ-DECOMP, degrau 5 | 8.2 |
| 9 | Tolerância em unidades de dispersão entre seeds: z = Δ/(s_b√(1/S_novo + 1/S_ant)), \|z\| > 2 → explicar; determinísticos: s_b = 0, diferença além de R2 → explicar | Bouthillier 2021 §5; evaluation §6.9; derivação | [C] EQ-TOL, degraus 1/3/5 | 8.2 |
| 10 | Comparação descritiva; TOST não adotado; "dentro da tolerância" ≠ equivalência | ICH E9 §3.3.2; evaluation §6.10, §8.5 | [C] EQ-DESC, degrau 1 | 8.2 |
| 11 | Divergência explicada = diferença declarada do catálogo + mecanismo/sentido compatível + localização pela decomposição; senão `[finding]` | roadmap 8.2 DoD; overview §2 | [C] EQ-EXPL, degrau 1 | 8.2 |
| 12 | Aposentadoria de andaime: comparações registradas com hashes + nenhuma dependência oficial + registro do motivo; não antes de fechar o `[finding]` que ele serve | roadmap 8.2; overview §4; Sandve Rule 4 | [C] EQ-ANDAIME, degrau 1 | 8.2 |
| 13 | Rótulos confirmatório / descritivo / exploratório; por elemento quando misturado | ICH E9 §5.1; Wagenmakers 2012 p. 632; ADR 6.5.0008 | [E] P8-ROT | 8.3 |
| 14 | Matriz DM: linha do candidato com Holm = confirmatória; demais células = exploratórias | Wagenmakers 2012 p. 632; evaluation §6.4 | [E] (parte de P8-ROT) | 8.3 |
| 15 | Fan chart com uma seed pré-declarada (a primeira do cohort), nunca média dos quantis entre seeds | evaluation §6.9; ADR 7.4.0001 | [C] P8-FAN, degraus 1/5 | 8.3 |
| 16 | Plots de dado persistido, por horizonte, rótulo por elemento | Sandve Rule 7; overview §4; evaluation §8.7 | [C] P8-PERSIST, degrau 1 | 8.3 |
| 17 | Conteúdo mínimo do dossiê pelas Rules 1, 3–9 de Sandve; Rule 10 = aspiração | Sandve 2013 | [C] DOSSIE, degrau 3 | 8.3 |

### 9.1 Registro das decisões (triagem `evidence-resolution`, 2026-10-22)

Triagem: todas as bifurcações são anteriores a qualquer dado confirmatório (a
8.1 não rodou). A existência e os metadados das fontes novas foram conferidos
nesta sessão; os trechos citados foram lidos na fonte bruta (HTML/PDF/código
da documentação) pelo autor do doc; a verificação adversarial de contexto
zerado (skill §4.2) é a etapa seguinte do gate e atualiza o campo
`Verificado`.

```
[decision:P] B1 — o que a 8.2 compara
Escolha: as duas comparações — (i) reprodução da própria corrida a partir dos artefatos persistidos (claim citável no TCC) e (ii) oficial × confirmatório anterior na interseção comum (pinball τ ∈ {0,1; 0,5; 0,9}, PICP/MPIW do par 80 %, DM contra baselines comuns, sentido do veredito) como auditoria interna · Alternativas: A — só (i); B — só (ii) (texto literal do roadmap) · Decisor: humano (issue #208, 2026-10-22)
Base: overview ASSUM-4 e R-REPRO-1 (equivalência com tolerância declarada); overview §2 (oráculo, nunca autoridade); política editorial do TCC
Sensibilidade pré-registrada: nenhuma · Reversível: sim (ADR 0.0.0061)

[decision:P] P-EDIT — política editorial do TCC
Escolha: o texto do TCC não menciona o projeto anterior; a parte (ii) fica só no repositório · Alternativas: citar a equivalência no texto · Decisor: humano (política editorial anterior a este gate, reafirmada na issue #208)
Base: —
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R-CAMADAS — o que se compara numa reprodução
Escolha: identidade da entrada por hash (igual, pré-condição), resultado (comparado), proveniência (excluída) · Alternativas: comparar o artefato inteiro byte a byte (falha por timestamps) · Degrau: 3
Base: Sandve et al. 2013, Rule 1 "For every involved step, you should ensure that every detail that may influence the execution of the step is recorded"
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] R-BIT — reprodução no mesmo ambiente
Escolha: bit a bit em todo campo de resultado, inclusive etapas aleatórias; falha = parada para diagnóstico · Alternativas: tolerância também no mesmo ambiente
Base: Goldberg 1991 §The IEEE Standard "The IEEE standard requires that the result of addition, subtraction, multiplication and division be exactly rounded"; NumPy 2.5.0 doc/source/reference/random/compatibility.rst "on the same build of numpy, in the same environment, on the same machine, you should get the same stream of numbers"; Python 3.12 Doc/library/random.rst §Notes on Reproducibility "By reusing a seed value, the same sequence should be reproducible from run to run as long as multiple threads are not running"; Sandve et al. 2013 Rule 6 "given the same initial seed, all random numbers used in an analysis will be equal"
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] R-ENV — reprodução entre ambientes
Escolha: por classe — R1 discreta exata; R2 contínua |Δ| ≤ max(1e-9·max(|a|,|b|), 1e-12); R3 aleatória bit a bit com o mesmo gerador, senão diferença em erros de Monte Carlo √(p(1−p)/B), reportada · Alternativas: par float32/float64 do torch.testing.assert_close; só relativa; bit a bit sempre · Degrau: 2 (default de math.isclose, a linguagem do domínio) e 1 (piso 1e-12 do ADR 6.1.0001)
Base: Python 3.12 Doc/library/math.rst isclose "The default tolerance is 1e-09, which assures that the two values are the same within about 9 decimal digits"; mesma página, impl-detail "The math module consists mostly of thin wrappers around the platform C math library functions"; Goldberg 1991 "The IEEE standard does not require transcendental functions to be exactly rounded"; Python 3.12 Doc/whatsnew/3.12.rst §Other Language Changes "sum() now uses Neumaier summation"; NumPy 2.5.0 compatibility.rst "different CPUs implement floating point arithmetic differently"; [SEM-FONTE-PRIMÁRIA] para o par como critério de reprodução
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma (nenhum valor nessa faixa muda decisão; a exceção de fronteira é reportada) · Reversível: sim

[decision:C] EQ-HASH — congelar a evidência anterior
Escolha: hash de conteúdo por arquivo + lista, versionados, antes de qualquer leitura de valor; regras de comparação = as deste doc, fixadas antes da 8.1 · Alternativas: ler os arquivos como estão; versionar os próprios arquivos · Degrau: 1 (issue #208: "versionada por hash antes de servir de oráculo") e 3
Base: Sandve et al. 2013 Rule 4 "If computer code is not systematically archived along its evolution, backtracking to a code state that gave a certain result may be a hopeless task"; Rule 1; Nosek et al. 2018 (via evaluation §8.3)
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma · Reversível: não depois de lidos os valores (é o objetivo)

[decision:C] EQ-INTER — alinhamento na interseção
Escolha: modelo comum por definição; interseção exata por target_timestamp e horizonte, fold não é chave; realizado conferido primeiro (R2); só níveis comuns, sem interpolação; fora da interseção não entra · Alternativas: comparar por fold; interpolar a grade anterior; comparar amostras completas · Degrau: 1
Base: evaluation §6.7 (conv. 17, interseção exata); evaluation §2.2 razão 1 via Gneiting & Raftery 2007 §1 (o score é da previsão quotada)
Verificado: não verificado (§4.2) — herdado de evaluation
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] EQ-DECOMP — separar código de métrica de predição
Escolha: m_A = código novo sobre predições anteriores; total = predição + código · Alternativas: só o total · Degrau: 5
Base: identidade telescópica (derivação)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] EQ-TOL — escala da tolerância de equivalência
Escolha: z = Δ / (s_b·√(1/S_novo + 1/S_ant)), s_b = dispersão entre seeds do cohort novo na mesma interseção; |z| > 2 → explicar; termo 1/S_ant omitido se desconhecido; determinísticos (GBM, baselines): diferença além de R2 → explicar · Alternativas: absoluta δ; relativa; múltiplos da dispersão entre folds; k = 3 · Degrau: 1 (evaluation §6.9: seeds = réplicas; §4.4 alt. (i) e ADR 7.1.0003 alt. F rejeitam absoluta e relativa), 3 (Bouthillier) e 5 (k = 2); 4 para omitir 1/S_ant (sinaliza mais)
Base: Bouthillier et al. 2021 §5 "should not build solely on comparing average performance but account for variance" (via evaluation §8.4); variância da diferença de médias independentes (derivação); [SEM-FONTE-PRIMÁRIA] para k = 2
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: o z contínuo de toda grandeza é reportado (k só rotula) · Reversível: sim, até a 8.1 rodar

[decision:C] EQ-DESC — descritivo × teste de equivalência
Escolha: comparação descritiva; TOST não adotado · Alternativas: TOST com margem absoluta; TOST com margem em unidades de seed · Degrau: 1 (evaluation §6.10 conv. 15; §8.5 B2)
Base: ICH E9 §3.3.2 (pp. 14–15 do PDF da ICH) "An equivalence margin should be specified in the protocol; this margin is the largest difference that can be judged as being clinically acceptable … The choice of equivalence margins should be justified clinically"; "two simultaneous one-sided tests"
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] EQ-EXPL — o que conta como divergência explicada
Escolha: (a) diferença declarada do catálogo fechado + (b) mecanismo e sentido/limite compatíveis + (c) localização pela decomposição; senão [finding]; categoria nova só por emenda do doc · Alternativas: julgamento caso a caso; "diferença pequena" · Degrau: 1
Base: roadmap 8.2 DoD "divergências explicadas pela teoria (não 'bate com o antigo')"; overview §2 (oráculo, nunca autoridade; bug conhecido do anterior)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] EQ-ANDAIME — aposentadoria de andaime interino
Escolha: aposentar quando as comparações estão registradas com hashes, nada oficial depende dele e o motivo está registrado; não antes de fechar o [finding] que ele serve · Alternativas: manter como teste de regressão contínua · Degrau: 1
Base: roadmap 8.2 "justificar aposentadoria de qualquer andaime interino"; overview §4 (reconstrução sem re-treino); Sandve et al. 2013 Rule 4
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:E] P8-ROT — estatuto e rótulo dos números e gráficos
Escolha: confirmatório = só a árvore pré-registrada; descritivo = perfil pré-registrado, H3, conformal; exploratório = o resto (matriz DM fora da linha do candidato); rótulo por elemento · Alternativas: rotular por gráfico inteiro
Base: Wagenmakers et al. 2012 p. 632 "Other analyses can be carried out but these should be labeled 'exploratory'"; ICH E9 §5.1 "Only results from analyses envisaged in the protocol (including amendments) can be regarded as confirmatory" (ambos via evaluation §8.1/§8.3); ADR 6.5.0008
Verificado: herdado de evaluation (§10.1 daquele doc)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] P8-FAN — que previsão a série OOS desenha
Escolha: uma seed pré-declarada (a primeira da lista do cohort), rotulada ilustrativa · Alternativas: média dos quantis entre seeds; envelope de todas as seeds · Degrau: 1 (evaluation §6.9: ensemble é outro objeto; ADR 7.4.0001 serve por seed sem agregar) e 5
Base: evaluation §6.9 (B-SEEDS); FPP3 §5.5 (forma do gráfico)
Verificado: — · Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] P8-PERSIST — origem e forma dos plots
Escolha: de dado persistido identificado no dossiê, por horizonte, rótulo por elemento · Alternativas: recomputar no plot · Degrau: 1
Base: Sandve et al. 2013 Rule 7 "As a minimum, one should note which data formed the basis of a given plot and how this data could be reconstructed"; overview §4; evaluation §8.7
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma · Reversível: sim

[decision:C] DOSSIE — conteúdo mínimo do dossiê
Escolha: a tabela da §7 (Rules 1, 3–9); Rule 10 como aspiração · Alternativas: só run_ids e hashes (texto do roadmap) · Degrau: 3
Base: Sandve et al. 2013, Rules 1, 3, 4, 5, 6, 7, 8, 9 (trechos na §7)
Verificado: não verificado (§4.2)
Sensibilidade pré-registrada: nenhuma · Reversível: sim
```

## 10. Referências

Separadas em (10.1) já ratificadas no projeto, (10.2) novas deste doc
(registradas no overview §10 no mesmo PR, conforme ADR 0.0.0003) e (10.3)
documentação de linguagem e biblioteca.

### 10.1 Já ratificadas (overview §10, docs de domínio e ADRs)

- Sandve, G. K.; Nekrutenko, A.; Taylor, J.; Hovig, E. (2013). "Ten Simple Rules for Reproducible Computational Research". *PLOS Computational Biology*, 9(10), e1003285. DOI: 10.1371/journal.pcbi.1003285. (Rules 1–10; lido no HTML da PLOS em 2026-10-22.)
- Goldberg, D. (1991). "What every computer scientist should know about floating-point arithmetic". *ACM Computing Surveys*, 23(1), 5–48. DOI: 10.1145/103162.103163. (§The IEEE Standard — operações exatamente arredondadas, raiz quadrada, transcendentais; lido na reimpressão da Oracle, *Numerical Computation Guide*, Appendix D.)
- ICH (1998). *E9 — Statistical Principles for Clinical Trials*. (§3.3.2, pp. 14–15 do PDF em database.ich.org/sites/default/files/E9_Guideline.pdf; a paginação difere da citada em evaluation §8.5; §5.1 via evaluation §8.1–§8.2.)
- Nosek, B. A.; Ebersole, C. R.; DeHaven, A. C.; Mellor, D. T. (2018). "The preregistration revolution". *PNAS*, 115(11), 2600–2606. DOI: 10.1073/pnas.1708274114. (Via evaluation §8.)
- Wagenmakers, E.-J. et al. (2012). "An Agenda for Purely Confirmatory Research". *Perspectives on Psychological Science*, 7(6), 632–638. DOI: 10.1177/1745691612463078. (p. 632, via evaluation §8.3.)
- Bouthillier, X. et al. (2021). "Accounting for Variance in Machine Learning Benchmarks". *Proceedings of MLSys*, 3, 747–769. arXiv:2103.03098. (§5, via evaluation §8.4.)
- Gneiting, T.; Raftery, A. E. (2007). "Strictly Proper Scoring Rules, Prediction, and Estimation". *JASA*, 102(477), 359–378. DOI: 10.1198/016214506000001437. (§1; §9.3 — via evaluation §2.2, §4.6.)
- Gneiting, T.; Balabdaoui, F.; Raftery, A. E. (2007). "Probabilistic forecasts, calibration and sharpness". *JRSS B*, 69(2), 243–268. DOI: 10.1111/j.1467-9868.2007.00587.x. (Thm 2; §3.3 — via evaluation §4.1, §4.3.)
- Gneiting, T.; Ranjan, R. (2011), Kuleshov, Fenner & Ermon (2018), Brown, Cai & DasGupta (2001), Bröcker & Smith (2007), Pearce et al. (2018), Diebold & Mariano (1995), Harvey, Leybourne & Newbold (1997), Holm (1979), Diebold (2015), Berrisch & Ziel (2023) — citações completas em evaluation §11.
- Hyndman, R. J.; Athanasopoulos, G. (2021). *Forecasting: Principles and Practice*, 3rd ed., OTexts. (§5.5 "Distributional forecasts and prediction intervals", subseção "Benchmark methods" — forma do gráfico de intervalos.)
- Lim et al. (2021), Angelopoulos & Bates (2023) — citações completas em inference §11.

### 10.2 Novas deste doc

- Schuirmann, D. J. (1987). "A comparison of the Two One-Sided Tests Procedure and the Power Approach for assessing the equivalence of average bioavailability". *Journal of Pharmacokinetics and Biopharmaceutics*, 15(6), 657–680. DOI: 10.1007/BF01068419. `[CITAÇÃO-NÃO-ACESSADA]` (metadados conferidos no Crossref; origem do TOST, citada só como referência histórica — o que é load-bearing é o ICH E9 §3.3.2.)

### 10.3 Documentação de linguagem e biblioteca (mecânica, não teoria)

- **Python 3.12** (versão da imagem do projeto): `Doc/library/random.rst` §Notes on Reproducibility ("By reusing a seed value, the same sequence should be reproducible from run to run as long as multiple threads are not running"; "Most of the random module's algorithms and seeding functions are subject to change across Python versions, but two aspects are guaranteed not to change … The generator's random() method will continue to produce the same sequence when the compatible seeder is given the same seed"); `Doc/library/math.rst` (`isclose`: "rel_tol=1e-09, abs_tol=0.0", "The default tolerance is 1e-09, which assures that the two values are the same within about 9 decimal digits"; nota *impl-detail*: "The math module consists mostly of thin wrappers around the platform C math library functions"); `Doc/whatsnew/3.12.rst` §Other Language Changes ("sum() now uses Neumaier summation to improve accuracy and commutativity when summing floats or mixed ints and floats").
- **NumPy 2.5.0** (pinado no lock): `doc/source/reference/random/compatibility.rst` ("If you create a Generator with the same BitGenerator, with the same seed, perform the same sequence of method calls with the same arguments, on the same build of numpy, in the same environment, on the same machine, you should get the same stream of numbers. Note that these conditions are very strict"; "different CPUs implement floating point arithmetic differently, and this can cause differences in certain edge cases that cascade to the rest of the stream"; "Breaking stream-compatibility in order to introduce new features or improve performance in Generator or default_rng will be allowed with caution").
