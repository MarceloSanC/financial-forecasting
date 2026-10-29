---
title: Auditoria final do fechamento do TCC e da Stage 8.4
description: Veredito por critério (C1–C8) do plano de fechamento, com a evidência conferida na fonte por uma sessão separada de contexto limpo, os achados de requisito e as ameaças à validade da própria auditoria
when-use: Consultar antes de enviar a cópia à banca, ao fechar a #237 e ao tratar os achados abertos pela auditoria final (E9)
keywords: [tcc, auditoria, fechamento, criterios, c1, c8, stage-8.4, banca]
status: done
created_at: 2026-10-26
updated_at: 2026-10-26
references:
  - tcc/PLANO-FECHAMENTO.md
  - tcc/RUBRICA-E-REFERENCIAS.md
  - reports/reproduction_audit.md
  - reports/post_verdict_analyses.md
  - reports/final_traceability_dossier.md
---

# Auditoria final do fechamento do TCC (E9)

Sessão separada, de contexto limpo, em 2026-10-26. O objeto é o `origin/develop` em `fc0aa828`
(merge do PR #262) e o PR #261, ainda aberto. A geração julgada é
`judged/aapl_confirmatory-r3-00fd83d9cd39/`, montada `:ro`. Procurei só gap de requisito contra
os critérios C1–C8 do [plano](./PLANO-FECHAMENTO.md) §3. Nenhum relatório de agente foi tomado
como evidência: cada item abaixo foi conferido no gold, nos relatórios, no PDF ou na fonte
primária.

## Resumo

| Critério | Veredito | Em uma linha |
|---|---|---|
| C1 | atende | testes opt-in verdes (34 passed) e 35 números de prosa conferidos à mão no gold, sem divergência |
| C2 | **não atende** | grep = 0 e log sem `undefined`, mas as páginas 3 a 6 do PDF imprimem texto do template → #263 |
| C3 | atende com ressalva | 13 citações novas; 11 com verificação registrada por fonte; Herrig (2023) e Amjad et al. (2026) só com registro genérico, conferidas aqui na fonte |
| C4 | atende com ressalva | nota 2 em 10 dos 12 critérios; elementos formais com nota 1 (#263); não inferior às referências |
| C5 | atende | mecanismo, números da corrida e nove fontes primárias na `sec:discussao` |
| C6 | atende | o piloto é declarado como não evidência; os 5 achados conferidos nas fontes do repositório |
| C7 | atende | PR #258 mergeado, CI verde, 3 critérios da #202 com evidência em disco e no ADR |
| C8 | atende com ressalva | slides compilam (28 p.), números batem com o texto, 18,6 min estimados; o PR #261 está aberto, com a CI pendente |

## Estado das entregas

| Entrega | Issue | PR | Estado em 2026-10-26 |
|---|---|---|---|
| E1 | #233 (fechada) | #240 | mergeado |
| E2a | #250 (fechada) | #254 | mergeado |
| E2 | #244 (fechada) | #257 | mergeado |
| E3 | #245 (fechada) | #252 | mergeado |
| E4a | #243 (fechada) | #255 | mergeado |
| E4 | #246 (fechada) | #256 | mergeado |
| E5 | #247 (fechada) | #251 | mergeado |
| E6 | #248 (fechada) | #262 | mergeado; achado de requisito → #263 |
| E7 | #249 (aberta) | #261 | **aberto**: auditoria `complete`, `lint-and-test` pendente |
| E8 | #202 (fechada) | #258 | mergeado em `4ce33a4d` |
| Plano | #237 (aberta) | #238 | **aberto** (esta branch) |

## C1 — números do capítulo 5 contra a geração julgada: atende

**Teste opt-in.** Rodei a pasta `tests/tcc/` de um export do `origin/develop`
(`git archive`), na imagem `financial_forecasting-app:dev`, com `--cpus 2 --memory 3g`, o volume
`financial-forecasting_app-venv` e o gold montado `:ro`:

```
TCC_JUDGED_ROOT=/judged pytest tests/tcc/ -rs -q
33 passed, 1 skipped   (o pulado é test_post_verdict_numbers: pede TCC_DATA_ROOT)
TCC_DATA_ROOT=/data pytest tests/tcc/test_post_verdict_numbers.py -rs -q
1 passed               (recalcula D1 e D3 e confere o bloco de docs/reports/post_verdict_analyses.md)
```

**Amostra independente.** Usei scripts próprios, que leem as parquet de `generation/` e o
scorecard. Conferi 35 números de prosa que o teste não cobre, nos capítulos 5 e 6, e todos batem
no arredondamento exibido:

| Número no texto | Onde | Fonte | Valor gravado |
|---|---|---|---|
| cobertura média do par de 80% = 0,818 | Cap. 5 §H1; Resumo | `gold_metrics_by_run`, `picp`, TFT, h+1 | 0,8176 |
| cobertura por semente de 0,772 a 0,872 (h+1) | Cap. 5; Cap. 6 | idem, mín./máx. | 0,7717 / 0,8716 |
| banda de 95% contém o nominal em 4 de 10 sementes | Cap. 5 | `gold_calibration_table`, `wilson_contains_nominal` | sementes 2, 4, 5 e 9 |
| Christoffersen MC: p ≤ 0,003 no TFT em h+1; rejeita nos comparadores | Cap. 5 | `gold_christoffersen_monte_carlo`, `mc_p_ind` | máx. 0,003; comparadores de 0,001 a 0,003 |
| frequências abaixo de τ (h+1): 0,023, 0,089, 0,227, 0,766, 0,906 e 0,977 | Cap. 5 | `gold_calibration_table`, n_violations/n_observed | 0,0233, 0,0887, 0,2272, 0,7663, 0,9064, 0,9766 |
| em h+7, diferença máxima de meio ponto percentual | Cap. 5 | idem, h+7 | máx. 0,50 p.p. (τ = 0,25) |
| nível Bonferroni das subséries: 99,64% | Cap. 5 | scorecard, `gate_sensitivities.dgt_band_level` | 0,99643 |
| MPIW/cobertura: GBM 0,0396/0,769, EWMA 0,0471/0,827, TFT 0,0464 | Cap. 5 | `gold_metrics_by_run` | 0,03959/0,7690; 0,04706/0,8266; 0,04644 |
| CQR: desvio-padrão de 0,016; MPIW de 0,0457 e 0,0456 | Cap. 5 | `gold_conformal_coverage` | 0,0159/0,0161; 0,04569/0,04560 |
| cauda inferior de 0,089 para 0,109 (h+1) | Cap. 5 | idem, `lower_tail` 0,1 | 0,1086 |
| 96% conformal = 0,947; nativo 0,953 e 0,956; cauda 0,02 = 0,028 e 0,029, fora da banda | Cap. 5 | idem; `picp` 0,02 | 0,9473/0,9469; 0,9533/0,9560; 0,0283/0,0288, `wilson_contains_nominal` falso |
| rearranjo alterou 0,20% do GBM em h+1 e nada em h+7 | Cap. 5 | `guardrail_applied_rate` | 0,00199 / 0 |
| redução de 41% a 43% sobre os naive | Cap. 5 | `pinball_grid_mean` | 40,8% a 43,3% (h+1); 40,9% a 42,2% (h+7) |
| diferença entre os fortes de no máximo cerca de 4% | Cap. 5 | idem | 4,2% (h+1) |
| DM por semente: AR(1) 5 e 2; quantis empíricos 3 e 0; EWMA-vol e GBM 0 | Cap. 5 | `gold_dm_profiles`, `dimension = seed` | 5/2, 3/0, 0/0, 0/0 |
| permutação da família técnica = 2,0 × 10⁻⁵ (≈ 0,5% da perda); fundamentos negativos em h+7 | Cap. 5 | `gold_h3_importance` | 1,99 × 10⁻⁵; −8 × 10⁻⁷ |
| ablação de 1,5 a 6,3 × 10⁻⁵ em h+1 | Cap. 5 | idem, `loco` | 1,50 a 6,28 × 10⁻⁵ |
| blocos de 61; 1.000 réplicas; 1 e 12 réplicas indefinidas | Cap. 5 | `gold_h3_reading` | 61; 1000; 1; 12 |
| blocos do MCS de 65 e 64; √T = 39 | Cap. 5 | `gold_mcs_results`, `gold_mcs_block_sensitivity` | 65, 64, 39 |
| VaR 98% do TFT por semente: de 1,2% a 3,0%, rejeita em 4 de 10 (h+1); 1 de 10 (h+7) | Cap. 5; Cap. 6 | `gold_calibration_table`, `kupiec_pof_p_value` | 0,0119 a 0,0298, 4; 1 |
| VaR 90%: todas as taxas médias entre 8% e 12% | Cap. 5 | idem, `lower_tail` 0,1 | 0,0827 a 0,1171 |
| D3: 3,988 e 4,008; −1,6% e −1,4%; +1,7% e +0,2%; p 0,98 e 0,57; PICP 0,832 e 0,830 | Cap. 5; Cap. 6 | `post_verdict_analyses.md` l. 77–78 e 113–120 (atado ao gold pelo teste acima) | 3,9875/4,0084; 0,9845/0,9865; 1,0173/1,0020 |
| perfil pontual: acurácia do TFT 0,529 e 0,523; taxa-base 0,531 | Cap. 5; Cap. 6 | idem, l. 52–69 | 0,5285; 0,5227; 0,5314/0,5309 |
| 1.173.254 valores; 19 tabelas; 66.117 folhas | Cap. 5; Ap. C.4 | `final_traceability_dossier.md` l. 657 (882.727 + 288.671 + 1.856); `reproduction_audit.md` l. 81 | iguais |

## C2 — espaço reservado e referência quebrada: não atende

**O que passa:**
- grep, sensível a maiúsculas, de "A ser preenchido", "TODO", "versão posterior" e "Nota de versão"
  (mais `FIXME`, `XXX` e `??`) em `text/**/*.tex` e no `.bib`: 0 ocorrências;
- `build_tex.sh` no export do develop: `exit=0`, 92 páginas, nenhuma linha com `undefined` nem
  erro, nenhuma linha em "comandos LaTeX colapsados";
- o aviso "Label(s) may have changed" continua depois de 5 passadas, mas o `Main.aux` não muda
  entre a 5ª e a 6ª passada (`diff` vazio) e não há rótulo duplicado. Leio isso como ruído de
  pacote, não como referência instável.

**O que falha.** O texto extraído do PDF (pypdf) mostra o seguinte nas páginas pré-textuais:

| Página | Texto impresso | Origem |
|---|---|---|
| 2–3 | "Orientador(a): Dr(a). Pedro Paulo de Andrade Júnior"; "Coorientador(a): Dr(a). …" | `text/Main.tex` l. 85–86 |
| 3 | "Joinville (SC), 00 de mês de 2026"; "Prof. Dr. Nome do Membro A / Universidade do Membro A"; idem B | `text/Main.tex` l. 95–103 |
| 4 | "Dedico este trabalho a ........................" | `text/1_Resumo/1_1_Dedicatoria.tex` |
| 5 | "Inserir os agradecimentos aos colaboradores à execução do trabalho. Xxxx…" | `text/1_Resumo/1_2_Agradecimentos.tex` |
| 6 | "Texto da Epígrafe. Citação relativa ao tema do trabalho. É opcional. […] (GIL, 2010)" | `text/1_Resumo/1_3_Epigrafe.tex` |

Isso é espaço reservado pelo próprio enunciado do C2. A medida mecânica do plano não o pega,
porque procura só quatro marcadores. A E6 (#248) tinha "elementos formais" no escopo. O PR #262
registrou a banca, a data e o gênero do orientador como dados do dono, para uma "lista de
pendências do relatório final" que não existe em nenhum artefato. A dedicatória, os
agradecimentos e a epígrafe não aparecem em nenhum registro. O título também termina em ponto
("…FORA DA AMOSTRA.").

**Ação:** #263, ligada à #237 e à #248. Ela pede dados do dono (banca, data, tratamento) e a
decisão de manter ou retirar os elementos opcionais. Também estende a varredura do C2 aos
marcadores de template.

## C3 — citações novas sustentadas pela fonte primária: atende com ressalva

`git diff a0d2dde4 origin/develop -- text/7_Referencias/7_Referencias.bib` acrescenta 13
entradas: HANSEN2005, MAKRIDAKIS2018, ZENG2023, ELSAYED2021, MONTEROMANSO2021, LIPTON2019,
ORMANIEC2022, HERRIG2023, AMJAD2026, MORAIS2023, EUZEBIO2025, WAGENMAKERS2012 e THABANE2010.

| Citações | Registro da verificação |
|---|---|
| Hansen e Lunde, Makridakis et al., Zeng et al., Elsayed et al., Lim et al. (já existente), Montero-Manso e Hyndman, Lipton e Steinhardt | tabela por fonte no corpo do PR #256, com veredito e ressalva; a auditoria releu Elsayed e Lim no PDF |
| Wagenmakers et al., Thabane et al. | PR #252: corpo e auditoria, com trecho literal |
| Ormaniec et al., Morais, Euzébio | comentário de auditoria do PR #262, com o texto integral relido |
| **Herrig, Amjad et al.** | **só a frase genérica do PR #262** ("cada afirmação passou pelo evidence-verifier"), sem veredito por fonte |

**Minhas três conferências na fonte:**

1. **HERRIG2023** (PDF do arXiv:2501.01278, texto extraído). Página de rosto: "A thesis presented
   for the degree of Master of Science (MSc.) […] University of St. Andrews […] 15.08.2023".
   Resumo: três índices; 2017–2018 calmo e 2021–2022 turbulento; "LSTM-MDNs performed poorly for
   2017/2018 but outperformed benchmark models in 2021/2022"; comparadores "historical
   simulation, CMM, and GARCH". No §2, o VaR de 99% (α = 0,99, Basileia), o POF de Kupiec (1995)
   e o teste de Christoffersen (1998). **Sustenta** a frase do `sec:correlatos` e a linha do
   quadro.
2. **AMJAD2026** (Crossref, 10.3390/risks14100228; o MDPI recusou o acesso automático). O resumo
   traz doze índices, GARCH(1,1)-t com FHS, Kupiec, Christoffersen e QLIKE; o DM com
   Holm–Bonferroni favorece o GARCH em nove de doze mercados; o LSTM "is not significantly more
   accurate than GARCH in any market, before or after correction"; e "These results are reported
   for a specific neural implementation". **Sustenta.** Depois, na #272, o texto integral (PDF obtido pelo autor) foi lido:
   teste de jul/2022 a jul/2026 na maioria dos mercados, divisão 70/15/15, GJR-GARCH na
   robustez, cobertura conjunta 8/12 (GARCH-FHS) contra 2/12 (LSTM) e 6/12 (LSTM com
   perda pinball), e nenhuma menção a pré-registro. A linha do quadro e a frase passaram a
   vir do texto integral, e a nota "a partir do resumo" saiu.
3. **HANSEN2005** (Crossref, 10.1002/jae.800). O resumo traz 330 modelos ARCH; para o câmbio
   DM–US$, nenhuma evidência de que o GARCH(1,1) seja superado; para a IBM, o GARCH(1,1) é
   claramente inferior a modelos com efeito alavancagem. **Sustenta** a frase da `sec:discussao`
   e a ressalva da RUBRICA §6. Não li o "um dia à frente" no resumo (ver ameaças).

**Ressalva.** A verificação de Herrig e Amjad não estava registrada por fonte. Este relatório
passa a ser o registro. As duas se sustentam, então o furo é só de registro e não pede issue.

## C4 — rubrica do §2 da RUBRICA: atende com ressalva

| # | Critério | Onde o texto atende | Nota |
|---|---|---|---|
| 1 | Relevância e originalidade | Introdução §Justificativa; `sec:correlatos` (posicionamento: nenhum correlato combina retorno como alvo, quantis avaliados por calibração, testes corrigidos e pré-registro) | 2 |
| 2 | Problema, objetivos e hipóteses | Introdução §Problema, §Objetivos (geral e cinco específicos), §Hipóteses H1–H3 com regra operacional | 2 |
| 3 | Fundamentação com fontes primárias | Cap. 3, auditado na #169; as citações novas foram conferidas (C3) | 2 |
| 4 | Estado da arte e correlatos | `sec:correlatos` com o quadro `tab:correlatos` (alvo, validação, comparadores, teste e correção, saída probabilística, pré-registro) | 2 |
| 5 | Metodologia reprodutível | Cap. 4 (protocolo, comparadores, métricas, regra pré-registrada); Ap. C (ambiente, reprodução bit a bit) | 2 |
| 6 | Resultados coerentes com o prometido | Cap. 5: perfil pontual (`tab:pontual`), Winkler (prosa), VaR/Kupiec (`tab:var`); a frase "figuras em versão posterior" saiu; C1 verde | 2 |
| 7 | Análise e discussão | `sec:discussao` (porquê, literatura, "o TFT foi mal usado?", explicação × hipótese); 5 figuras no Cap. 5, 1 no Cap. 4 e 4 no Ap. E, cada uma com um parágrafo de leitura | 2 |
| 8 | Conclusões coerentes com os objetivos | Cap. 6, `tab:objetivos` (objetivo → onde → resultado); 4 + 4 contribuições, apresentadas como integração | 2 |
| 9 | Limitações e ameaças | Cap. 6 §Limitações (nove itens, inclusive o as-of e as notícias); Cap. 5 §Ameaças remete às Limitações. Ainda há sobreposição parcial (conformal e h+7 aparecem nos dois lugares), sem contradição | 2 |
| 10 | Escrita e legibilidade | Resumo com 346 palavras e sem siglas de teste; exemplo dos mil dias na Introdução; "*scorecard*" só no rótulo e na explicação do Método | 2 |
| 11 | ABNT e elementos formais | o ano 2026, o anexo de exemplo e a nota de versão foram resolvidos; **as páginas 2 a 6 ainda trazem texto do template e o título termina em ponto** (C2, #263) | **1** |
| 12 | Apresentação e arguição | o material existe e confere (C8), com 10 reservas para os riscos da RUBRICA §5; desempenho na arguição não é julgável aqui | 2 (material) |

**Não inferioridade.** As referências do §4 são os premiados do CTIC/SBC (artigos curtos, sem
teste de hipótese, um único comparador, limitações rasas) e os TCCs da área. Morais (UFU, 2023)
usa *holdout* único e compara só com o passeio aleatório. Euzébio (Unilasalle, 2025) chama 52% de
acerto de vantagem, sem teste. O texto auditado é não inferior a todas e superior em rigor:
- retorno como alvo;
- *walk-forward* com purga e embargo;
- seis comparadores, um deles de ML com as mesmas *features*;
- DM-HLN com Holm e MCS com sensibilidade de bloco;
- poder declarado do teste de calibração;
- pré-registro com *hash*;
- reprodução bit a bit;
- discussão que separa explicação de hipótese.

O ponto em que os premiados se destacam é a clareza. Aqui o resumo reescrito, o exemplo da
Introdução e as figuras com parágrafo de leitura cobrem esse ponto. A única dimensão em que o
texto fica abaixo de qualquer trabalho depositado é a forma pré-textual (critério 11), e isso se
resolve pela #263.

## C5 — por que o EWMA-vol venceu: atende

A `sec:discussao` (Cap. 5, l. 281–299) tem os três elementos:
- **Mecanismo:** o ganho vem da escala; o EWMA-vol, com λ = 0,94 fixo, acompanha a magnitude
  recente.
- **Números da corrida, conferidos no C1:**
  - GBM 3,980 contra EWMA-vol 3,920 × 10⁻³;
  - TFT de 3,987 a 4,117 por semente;
  - permutação técnica ≈ 0,5% da perda;
  - D3 com −1,6% e −1,4%, ainda acima do EWMA-vol.
- **Fontes primárias:** RiskMetrics (1996), Hansen e Lunde (2005), Makridakis et al. (2018), Zeng
  et al. (2023), Elsayed et al. (2021, usado como contraste), Lim et al. (2021), Cont (2001),
  Montero-Manso e Hyndman (2021) e Bouthillier et al. (2021).

A seção separa as leituras apoiadas pelos dados (i–v) das hipóteses não testadas (vi–vii), e as
hipóteses viram a sexta direção dos trabalhos futuros.

## C6 — estudo piloto como motivação: atende

O Cap. 4, `sec:piloto`, diz em negrito: "O piloto não constitui evidência para nenhuma das
hipóteses deste trabalho". Diz também que os números não entram nos Caps. 5 e 6, e enquadra o
piloto por Thabane et al. e Wagenmakers et al., como analogia. Conferi cada achado da
`tab:piloto` na fonte:

| Achado | Fonte conferida |
|---|---|
| 0 de 685 linhas iguais em h = 1; alvo deslocado por dias corridos | `docs/adr/4_3_0001-…md` l. 31–37: "**0 of 685** rows had matching `y_true`"; "`pd.Timedelta(days=h)` — a **calendar** timedelta" |
| 91,25% de grade degenerada | `git show 97d867d8:text/6_Conclusoes/6_Conclusoes.tex` l. 44: "91,25% de degenerescência quantilica em runs com parent_sweep_id nulo" |
| grade p10/p50/p90 | `97d867d8:text/4_Metodo/4_Metodo.tex`, apontado no PR #252 e na auditoria; não reli a linha |
| MCS artesanal com erro | apontado no PR #252 (`docs/overview.md:26`, ADR 6.2.0004); não reli |
| *fallback* de +45 dias em 17 de 81 | `docs/autonomous-run-decision-ledger.md` l. 29: "17/81 usaram fallback, sem leakage" |

A política editorial (memória `tcc-text-editorial-policy`) foi seguida: enquadramento
metodológico, sem narrativa de dívida de software.

## C7 — Stage 8.4: atende

- **PR #258:** mergeado em 2026-10-26 (`4ce33a4d`); a #202 está fechada.
  `gh pr checks 258`: `lint-and-test` pass (44 min) e `audit-status` pass. Há comentário de
  `stage-audit` com veredito `complete`.
- **Critério 1 da #202:** em disco existem `data/production/aapl/rounds/2025-06-30/` e
  `…/2025-12-31/`. O `serving.env` aponta
  `DATA_ROOT=/app/data/production/aapl/rounds/2025-12-31`, fora de `data/cohorts/aapl`. O
  isolamento por *hash* dos 355 arquivos está no technical §7 e no e2e
  `tests/e2e/test_production_round_cli.py`; não o refiz (ver ameaças).
- **Critério 2:** o ADR 8.4.0002, item 3, diz que a janela do ADR 6.4.0005 não ocorre (raiz
  imutável e ponteiro lido só na partida). Traz ainda o trecho "**Residual risk, measured and
  accepted:** while the container is recreated the API does not answer". O risco está aceito por
  escrito.
- **Critério 3:** `git diff --name-only 4ce33a4d^1 4ce33a4d` lista 20 arquivos, nenhum em
  `features/inference` nem em `shared/infrastructure/http`. O diff do `composition_root.py` só
  acrescenta a montagem do cohort de produção (`production_cohort_for`, `cohort_runner`,
  `writer_lock_for`).
- As decisões P da Stage (D1, D2, D3, D4, D7, D9 e a indisponibilidade de 19–23 s) seguem a
  ratificar pelo dono. Isso não é gap de requisito.

## C8 — apresentação: atende com ressalva

- **Compilação:** o export do `origin/docs/249-tcc-defense-slides` (`23e19f85`) com
  `latexmk -pdf` na imagem texlive dá `rc=0`, 28 páginas, 0 `undefined` e 0 erros.
- **Números:** meu script extrai os números visíveis (sem comentários) e procura cada um em
  `text/*/*.tex` do develop. Na parte principal e nas reservas, os únicos números ausentes são
  coordenadas TikZ e dimensões de figura (com ponto decimal), anos de citação e o "−0,051"
  (presente no texto como `\(-0{,}051\)`). Nenhum número de resultado diverge.
- **Tempo:** a soma dos tempos por frame dá 0,3 + 18,3 = 18,6 min ≤ 20 (Art. 16), com as 10
  reservas fora do tempo.
- **Ressalvas:**
  - o PR #261 está aberto, com o `lint-and-test` pendente. O C8 só vale para o develop depois do
    merge;
  - o tempo é uma estimativa por slide, não um ensaio cronometrado;
  - o slide de abertura repete "Dr." sem o "(a)" do PDF. Isso é coerente com a #263, que vai
    fixar o tratamento.

## Achados e encaminhamento

| Achado | Entrega | Encaminhamento |
|---|---|---|
| Páginas pré-textuais com texto do template e título com ponto final (C2, rubrica 11) | E6 (#248, fechada) | **#263**, com `Refs #237, #248`; depende de dados do dono |
| Verificação de Herrig e Amjad sem registro por fonte (C3) | E6 (#248) | registrada neste relatório (§C3); as duas se sustentam; sem issue |

Nenhum achado fora das entregas do plano.

## Ameaças à validade desta auditoria

- **Mesmo modelo como autor e auditor.** Contexto limpo e sem a conclusão do autor, mas a
  auto-preferência não fica eliminada (plano §8).
- **O teste do C1 foi escrito pelo autor.** Por isso amostrei 35 números com scripts próprios.
  Não conferi todos os números de prosa dos capítulos 5 e 6: ficaram de fora, entre outros, a
  faixa de 0,075 a 0,119 das subséries de h+7 e parte das linhas da `tab:pontual`. Desta tabela
  conferi contra o relatório todas as linhas de h+1, exceto a do GBM, e as linhas dos quantis
  empíricos, do GBM e do TFT em h+7.
- **Fontes com acesso bloqueado.** O MDPI e a Wiley recusaram o acesso automático (403). Hansen e
  Lunde foi conferido pelo resumo do Crossref, não pelo texto integral; Amjad et al. foi lido
  depois no texto integral (#272). O "um
  dia à frente" de Hansen e Lunde não está no resumo.
- **C4 e C8 dependem de julgamento.** Não há banca simulada humana nem ensaio cronometrado.
- **Leitura parcial.** Li por inteiro o Resumo e os Caps. 5 e 6. Do Cap. 4 li o §piloto e os
  trechos de comparadores e busca. Dos Caps. 2 e 3 li os trechos citados. O Cap. 3 antigo e os
  apêndices não foram relidos frase a frase; dependo da auditoria de citações da #169.
- **Stage 8.4.** Não rodei o `make check` nem o e2e de duas rodadas. Usei a CI verde do PR, os
  arquivos em disco, o ADR e o diff.
- **Estado em movimento.** O PR #261 está aberto e a CI pendente. Se o develop mudar antes do
  merge, o C8 precisa ser reconferido.

VEREDITO FINAL: atende com ressalvas
