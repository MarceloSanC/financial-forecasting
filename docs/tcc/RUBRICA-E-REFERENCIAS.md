---
title: Rubrica de avaliação e referências de excelência para o fechamento do TCC
description: Regulamento de TCC do Campus Joinville (UFSC), rubrica consolidada de fichas de avaliação de universidades públicas, nota atual do texto por critério, lacunas priorizadas, diferenciais e riscos para a defesa
when-use: Consultar ao escrever ou revisar qualquer entrega do texto do TCC (E2–E7 do plano de fechamento), ao montar a apresentação e na auditoria final (critério C4)
keywords: [tcc, rubrica, avaliacao, banca, ufsc, joinville, abnt, defesa, referencias]
status: in_progress
created_at: 2026-10-25
updated_at: 2026-10-25
references:
  - tcc/PLANO-FECHAMENTO.md
  - audits/tcc-citation-support.md
---

# Rubrica de avaliação e referências de excelência

Produzida no §5 do [plano de fechamento](./PLANO-FECHAMENTO.md). A coleta foi feita por quatro
pesquisas online (agentes Sonnet) e mais uma pesquisa dirigida ao regulamento da UFSC. A síntese
foi feita por um agente Opus 5.5.

Marcas usadas:
- **[V]** fonte aberta e lida;
- **[S]** só o resumo do buscador;
- **[R]** exigência de regulamento ou norma;
- **[P]** preferência, sem exigência formal.

## 1. O instrumento que vale: regulamento do Campus Joinville

O texto é do curso de Engenharia Mecatrônica (UFSC, Campus Joinville). O PPC remete ao
regulamento comum de TCC do campus [V]:
<http://secretariaacademicajoi.paginas.ufsc.br/files/2017/05/TCC-Regulamento_alteração-2017_nov.pdf>.

| Item | Regra | Fonte |
|---|---|---|
| Formato | Monografia para as engenharias, seguindo as normas ABNT NBR 14724 e NBR 6022; sem limite de páginas | Art. 2º [V] |
| Banca | No mínimo três membros, com o orientador como presidente | Art. 14, IV [V] |
| Cópia à banca | 15 dias antes da defesa, com o formulário "Sugestões para Avaliação" encadernado como primeira página | Art. 13, IV [V] |
| Apresentação | **Até 20 minutos**; arguição sugerida de 10 minutos por membro; total sugerido de até 50 minutos | Art. 16 [V] |
| Nota | Aprovação com nota final de 6,0 a 10,0; média ponderada das notas da banca, calculada pelo orientador. O regulamento **não fixa pesos** | Art. 17–18 [V] |
| Critérios ("Sugestões para Avaliação") | **Escrito:** problema caracterizado; objetivos claros e coerentes; tema relevante e atual; redação clara, objetiva e correta; relação entre revisão e objetivos; argumentação coerente; material adequado. **Apresentação:** desenvoltura; domínio do tema; qualidade técnica ao expor os princípios; capacidade de resposta | formulário [V] |
| Calendário 2026/2 | Bancas de 09/nov a 27/nov; versão revisada ao orientador até 03/dez; depósito obrigatório no Repositório (PDF/A) em 14/dez | cronograma TCC 2026 [V; extração de PDF pode ter desalinhado as datas] |

**Pendente com o dono:** pesos no plano de ensino da disciplina de TCC da Mecatrônica;
confirmação das datas; se o template LaTeX de Joinville é o mesmo do `text/` (o `README.txt`
diz "Template para TCC da UFSC").

## 2. Rubrica consolidada e nota atual do texto

A rubrica vem das fichas abertas de UFMG-FACE, UFG, UNIPAMPA, UFRGS (ESE e CCA) e Unicamp-FT
[V], mais o formulário de Joinville. Funciona como piso. As notas vão de 0 (ausente) a 2 (pleno)
e se referem ao texto da #233.

| # | Critério | Nota | O que falta | Entrega |
|---|---|---|---|---|
| 1 | Relevância e originalidade | 1 | Mostrar contra o quê a avaliação probabilística pré-registrada se destaca | E6 (correlatos) |
| 2 | Problema, objetivos e hipóteses explícitos | 2 | — | — |
| 3 | Fundamentação atual, com fontes primárias | 2 | — | — |
| 4 | Estado da arte e trabalhos correlatos | 1 | Falta seção de correlatos com quadro comparativo [R: UFG, UNIPAMPA] | E6 |
| 5 | Metodologia adequada e reprodutível | 2 | — | — |
| 6 | Resultados mensuráveis e coerentes com o prometido | 1 | O Método promete o perfil pontual, o *interval score* de Winkler e o *backtest* de VaR por Kupiec, que não aparecem no Cap. 5; ainda há a frase "figuras em versão posterior" | E2 |
| 7 | Análise e discussão (o porquê, com figuras) | 1 | O mecanismo da vitória do EWMA-vol não é explicado; o corpo tem uma única figura | E2, E4 |
| 8 | Conclusões coerentes com os objetivos | 1 | Os objetivos específicos não são retomados um a um; as contribuições estão superdimensionadas | E6 |
| 9 | Limitações e ameaças | 1 | Faltam os regimes de coleta das notícias e o *as-of* anual/trimestral; Ameaças e Limitações se sobrepõem | E5 |
| 10 | Escrita e legibilidade | 1 | Siglas no resumo; "*scorecard*" no corpo; falta um exemplo intuitivo na Introdução | E6 |
| 11 | ABNT e elementos formais | 1 | Banca com nomes de exemplo, ano 2025, Anexo A de exemplo, nota de versão no resumo; resumo longo (NBR 6028: 150 a 500 palavras) | E6 |
| 12 | Apresentação e arguição | 0 | Não existe ainda | E7 |

## 3. Lacunas priorizadas

**Alta**

- **Figuras no corpo** (E2):
  - no Cap. 5: *fan chart* fora da amostra, *reliability diagram*, PICP × MPIW, perda por nível, matriz de DM e importância por família, cada uma com um parágrafo dizendo o que olhar;
  - no apêndice: conformal, VSN, *sharpness* e ACF dos diferenciais;
  - [P] um diagrama do desenho do estudo no Cap. 4.
- **Promessas do Método** (E2): perfil pontual (D1), Winkler e VaR/Kupiec. Entregar a partir das tabelas gold existentes ou retirar a promessa.
- **Discussão do porquê** (E4): seção de 2 a 3 páginas. O argumento central sai dos dados: o GBM, com as mesmas *features*, também ficou atrás do EWMA-vol (3,980 contra 3,920). O limite está no conteúdo informacional das *features* sobre a escala, e não só no TFT. Separar explicação de especulação (Lipton e Steinhardt, 2018).
- **Trabalhos correlatos** (E6): seção ao fim do Cap. 3, com quadro descritivo (alvo, validação, *baselines*, teste e correção múltipla, saída probabilística, pré-registro), sem desqualificar colegas.
- **Legibilidade** (E6):
  - resumo reescrito com 250 a 350 palavras, sem HAC/HLN, Holm, Wilson ou NexCP;
  - um parágrafo-exemplo na Introdução ("um intervalo de 80% deve conter o retorno em cerca de 80% dos dias");
  - "*scorecard*" substituído por "regra de decisão pré-registrada".
- **Elementos formais** (E6): banca, ano, anexos, nota de versão.

**Média**

- Estudo piloto (E3): um parágrafo no Cap. 2 e uma subseção de cerca de uma página no Cap. 4, com uma tabela que liga cada lição à decisão de desenho que ela motivou.
- Objetivos retomados nas Conclusões (E6).
- Contribuições reduzidas a 3 ou 4, apresentadas como integração e aplicação rigorosa de práticas (E6).
- Limitações completadas (E5).
- Reprodução bit a bit citada no Cap. 5, com o detalhe no apêndice (E2).

## 4. Referências de excelência e de contraste

- **Premiados verificados** [V]:
  - Gomes e Aquino (UFAL), 3º lugar no 41º CTIC/SBC, 2022;
  - finalistas do CTIC 2022 e lista do CTIC 2025.
  - São artigos curtos, com menos rigor estatístico que este trabalho: sem teste de hipótese, um único *baseline*, limitações rasas. Foram premiados por clareza e foco.
- **TCCs da área** [V]:
  - Morais (UFU, 2023): LSTM prevendo **preço**, *holdout* único, DM só contra o passeio aleatório, subperíodo escolhido depois de ver o resultado;
  - Euzébio (Unilasalle, 2025): *walk-forward* correto, mas 52% de acerto direcional chamado de "vantagem estatística" sem teste.
  - Nenhum TCC da amostra emite quantis nem avalia calibração.
- **Não encontrado:** nenhuma ficha pública com "nota 10" em IA. A rubrica é um piso, não uma garantia.

## 5. Diferenciais para a banca e riscos

**Diferenciais:**
- retorno como alvo, e não preço;
- *walk-forward* com purga e embargo;
- hierarquia de seis comparadores, com um de ML usando as mesmas *features*;
- DM-HLN com Holm e MCS com quatro sensibilidades de bloco;
- calibração com poder declarado acima de 0,97;
- pré-registro com *hash*;
- dez sementes com a dispersão reportada;
- reprodução bit a bit.

**O risco é o inverso das referências:** rigor que não chega ao avaliador. A banca de engenharia
precisa entender o que é calibração antes de ver os testes.

| Risco | Mitigação |
|---|---|
| "O TFT perdeu, então o trabalho falhou" | Critério de sucesso fixado antes da corrida (H1 em ao menos um horizonte); seção do porquê (E4) |
| "Vencedor primário" lido como vitória | O termo vem sempre com "empate estatístico; a menor perda é do EWMA-vol" e com a sensibilidade ao bloco (p = 0,061 com l = h) |
| "O TFT foi mal usado" | O GBM também perdeu; a análise exploratória D3; modelo global multiativo como trabalho futuro |
| "Por que EWMA e não GARCH?" | Hansen e Lunde (2005), com a nuance de que, em ações, modelos com alavancagem superam; GARCH assimétrico como trabalho futuro |
| "Três revisões do pré-registro: é HARKing?" | Parágrafo e apêndice com o que mudou, com ou sem acesso a resultados |
| Tempo | Até 20 minutos (Art. 16): cerca de 15 slides de conteúdo e reservas separadas |

## 6. Citações novas e cuidados

Toda citação nova passa pelo `evidence-verifier` antes de entrar no texto (C3).

| Fonte | Uso | Cuidado |
|---|---|---|
| Hansen e Lunde (2005), JAE 20(7), DOI 10.1002/jae.800 | Modelos simples de volatilidade são difíceis de bater | Resultado misto em ações (IBM); não escrever "nada bate o GARCH" |
| RiskMetrics (1996) | λ = 0,94 é o fator ótimo para dados diários **no conjunto deles** | Não afirmar que é ótimo para AAPL |
| Makridakis, Spiliotis e Assimakopoulos (2018), PLOS ONE, DOI 10.1371/journal.pone.0194889 | Métodos estatísticos dominaram o ML na M3 | Séries univariadas mensais, ML da época |
| Zeng et al. (2023), arXiv:2205.13504 (AAAI) | Modelo linear supera Transformers | Previsão pontual de longo prazo; confirmar o *venue* |
| Elsayed et al. (2021), arXiv:2101.02118 | GBRT com janela supera DNNs | *Preprint*; previsão pontual |
| Lim et al. (2021) ✔ | O TFT é treinado sobre muitas entidades, com volatilidade realizada como alvo | Diferença de regime de uso, não prova |
| Montero-Manso e Hyndman (2021), IJF 37(4), DOI 10.1016/j.ijforecast.2021.03.004 | Métodos globais superam os locais em grupos de séries | Motivação de trabalho futuro |
| Lichtendahl, Grushka-Cockayne e Winkler (2013), Mgmt. Sci. 59(7), DOI 10.1287/mnsc.1120.1667 | A média de quantis é mais nítida | Não garante *pinball* menor; a garantia em relação à média das perdas vem da convexidade (Jensen) |
| Wagenmakers et al. (2012), PPS 7(6), DOI 10.1177/1745691612463078 | Só a análise pré-especificada é confirmatória | Abrir para a página |
| Thabane et al. (2010), BMC MRM 10:1, DOI 10.1186/1471-2288-10-1 | Piloto avalia viabilidade, não eficácia | Origem clínica: usar como analogia |
| Lipton e Steinhardt (2018), arXiv:1807.03341 | Separar explicação de especulação | — |
| Karl et al. (2024), arXiv:2406.03980 | Valor de resultado negativo | Artigo de posição |
| DL × GARCH em VaR (arXiv:2207.10539) | Evidência mista | Nunca escrever "a literatura mostra que DL perde" |
