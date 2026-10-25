---
title: Plano de fechamento do TCC e da Stage 8.4
description: Metodologia, critérios de sucesso fixados antes da execução, triagem e ordem das entregas que fecham o texto do TCC e a Stage 8.4, mais o registro vivo de surpresas e decisões
when-use: Consultar ao retomar o fechamento do TCC, ao abrir uma entrega do texto ou da 8.4, e na auditoria final que confere os critérios C1–C8
keywords: [tcc, plano, fechamento, entregas, criterios, rubrica, auditoria, stage-8.4]
status: in_progress
created_at: 2026-10-25
updated_at: 2026-10-25
references:
  - roadmap.md
  - RUNBOOK-STAGE-LIFECYCLE.md
  - GIT-WORKFLOW.md
  - audits/tcc-citation-support.md
---

# Plano de fechamento do TCC e da Stage 8.4

Issue do resultado: #237. Este arquivo é o **plano vivo**. O progresso fica nos commits e nas
issues. Aqui ficam só a metodologia, os critérios fixados antes de executar, a triagem, as
surpresas e as decisões tomadas no caminho (§9).

## 1. Lista de resultados

| Resultado | O que passa a ser possível | Status | Entregas |
|---|---|---|---|
| **R1 — TCC fechado** | A banca recebe um texto completo, com cada número rastreável à geração julgada e cada afirmação teórica apoiada em fonte primária, e uma apresentação de defesa coerente com ele | agora | E1–E7, E9 |
| **R2 — cohort de produção servível** | A API da 7.4 serve datas posteriores ao teste do estudo sem tocar no cohort confirmatório | agora | E8 (Stage 8.4, #202) |

## 2. Metodologia

O plano combina duas fontes:

1. **O padrão do projeto, que não muda:**
   - Stage pelo [RUNBOOK](../RUNBOOK-STAGE-LIFECYCLE.md) (concept → technical → Tasks →
     `stage-audit`);
   - issue avulsa pelo [PROMPT de issue](../PROMPT-issue-single-session.md) (`issue-audit`);
   - git pelo [GIT-WORKFLOW](../GIT-WORKFLOW.md) (worktree por branch, PR contra `develop`,
     fechamento autônomo pela auditoria);
   - texto pela política editorial do TCC (foco em ML e estatística; software só em apêndice).
2. **Os conceitos do protocolo de desenvolvimento em construção no `whaka-dev-project-tamplate`**
   (branch `docs/122-evidence-based-build-protocol`: `PROTOCOLO-DESENVOLVIMENTO`,
   `PROTOCOLO-CONSTRUCAO`, `PRINCIPIOS-DO-REFACTOR`). São aplicados assim:

| Conceito do protocolo | Como entra aqui |
|---|---|
| Lista de resultados no topo; entrega = 1 PR verde | §1; cada entrega da §4 tem issue própria ligada a #237 e fecha em um PR |
| Triagem N0/N1/N2 pelo alcance, não por confiança | coluna "nível" da §4; o nível N2 (decisão com base registrada) vale para a 8.4 e para as decisões de enquadramento do texto (§7) |
| Ficha de modelagem: critérios como **efeito**, não-objetivos, opção distante e "não fazer" | §3, fixada **antes** de executar as entregas |
| Regra nº 1: nada sem embasamento | três canais: pesquisa de referência (§5); citações novas verificadas na fonte primária pelo `evidence-verifier` (critério C3); números conferidos contra a geração julgada por script (C1) |
| Teste de aceitação antes do conteúdo | cada entrega declara na §4 o "como verificar" antes de escrever; os checks mecânicos da §6 rodam em todo PR do texto |
| Revisor em contexto limpo que procura divergência da spec, não "melhoria" | `issue-audit`/`stage-audit` por entrega; auditoria final (E9) por **sessão separada** que recebe os artefatos e os critérios, nunca a conclusão do autor |
| Achado fora do escopo não fica órfão | achado vira issue ligada a #237 e ao PR de origem, ou é recusado com motivo na §9 |
| Agente enxerga os limites do que executou (C1 do refactor) | §8: ameaças à validade do próprio plano, declaradas antes do veredito final |
| Plano vivo enxuto | §9 guarda só surpresas e decisões; o progresso fica nos commits |

**Decisões que seriam do humano.** O dono delegou a execução sem paradas. Decisão de
preferência (P) é tomada pelo agente com o motivo escrito e listada na §7 como **"a ratificar"**,
para o dono revisar no fim. Decisão com evidência (E) ou convenção (C) segue a `evidence-resolution`.

## 3. Ficha de modelagem (fixada antes da execução)

**Problema.** A evidência confirmatória existe, mas o texto ainda tem espaços reservados:
- figuras e reprodução fora do texto;
- perfil pontual prometido no Método e não entregue;
- nenhuma discussão de **por que** o EWMA-vol teve a menor perda;
- nenhuma menção ao estudo piloto que motivou o desenho;
- uma limitação da #163 omitida.

Além disso, a qualidade do texto nunca foi comparada com referências externas de excelência.

**Efeito desejado.** Um avaliador que só lê o PDF entende o que foi proposto, o que foi
encontrado e por quê, consegue conferir cada número, e não acha lacuna que um TCC de nota máxima
cobriria.

### Critérios de sucesso (efeito, verificáveis)

| # | Critério | Como se mede |
|---|---|---|
| C1 | Todo número do capítulo de resultados confere com a geração julgada | script de conferência número a número contra o scorecard e as tabelas gold de `judged/<ref>/`: 0 divergências |
| C2 | O texto não tem espaço reservado nem referência quebrada | grep de "A ser preenchido", "TODO", "versão posterior" = 0; log do LaTeX sem `undefined` (referência ou citação) |
| C3 | Toda citação **nova** é sustentada pela fonte primária | `evidence-verifier` por citação nova: 0 "não sustenta" sem correção |
| C4 | O texto cobre o que a rubrica de avaliação consolidada pede | rubrica da §5 com localização no texto para cada critério; auditor independente julga "não inferior" às referências de excelência |
| C5 | A pergunta "por que o EWMA-vol venceu?" tem resposta no texto | seção de discussão com o mecanismo, os números da corrida e ≥ 2 fontes primárias |
| C6 | O estudo piloto aparece como motivação, não como evidência | cada achado do piloto citado tem fonte verificável no repositório; o texto diz que o piloto não é evidência confirmatória |
| C7 | A Stage 8.4 atende aos critérios da #202 | `stage-audit` `complete`, `make check` verde e os 3 critérios de aceitação da #202 com evidência |
| C8 | A defesa cabe no tempo e não contradiz o texto | apresentação compila; cada número dos slides aparece igual no texto; tempo estimado ≤ 20 min (Art. 16 do regulamento de TCC do Campus Joinville; ajustado em 2026-10-25, ver §9) |

### Não-objetivos

- Rodar de novo o confirmatório.
- Mudar o veredito ou o pré-registro.
- Treinar modelos novos para "salvar" o TFT. Variantes viram trabalho futuro ou, no máximo,
  análise exploratória sobre previsões já persistidas, rotulada como tal (D3).
- Tratar a #163 e a #58: ficam como limitação.
- Reescrever a fundamentação teórica já auditada (`audits/tcc-citation-support.md`).

### Opções consideradas

| Opção | Leitura |
|---|---|
| **A — fechar o texto atual por entregas pequenas** (recomendada) | aproveita o texto já auditado; cada lacuna vira um PR verificável |
| **B (distante) — reescrever como artigo curto** em formato de periódico, com a monografia reduzida a apêndices | foco maior no achado; muitos cursos não aceitam esse formato e ele descartaria a fundamentação já auditada |
| **C — não fazer nada além da #233** | o texto ficaria com espaços reservados e sem discussão; falha C2, C5 e C6 |

**Critério de escolha:** cobrir C1–C8 com o menor retrabalho. A opção A vence: B refaz o que já
passou por auditoria de citações, e C falha em três critérios.

## 4. Entregas

| # | Entrega | Issue | Nível | Depende de | Como verificar (antes de escrever) |
|---|---|---|---|---|---|
| E1 | Resultados confirmatórios no texto | #233 | N1 | — | C1 (script), C2 parcial, PDF compila |
| E2a | Estilo de apresentação das figuras (nomes em PT, sem anotações do dossiê), gerado do gold | #250 | N1 | — | dossiê da 8.3 inalterado; figuras de `text/figuras/` sem identificador interno |
| E2 | Figuras da 8.3, reprodução da 8.2, perfil pontual (D1) e Winkler/Kupiec (D5) no texto | #244 | N1 | E1 | figuras citadas e legíveis, cada uma com parágrafo de leitura; afirmação de reprodução igual ao relatório da 8.2; C1 estendido aos números novos |
| E3 | Estudo piloto como motivação do desenho | #245 | N2 (D2) | E1 | C6; política editorial atualizada |
| E4a | Análises pós-veredito: perfil pontual (D1) e média das sementes (D3, na especificação da §7) | #243 | N1 | — | números conferidos por teste opt-in; nada fora da especificação |
| E4 | Discussão: por que o EWMA-vol venceu e o que mudaria o resultado | #246 | N2 | E1, E4a, pesquisa §5 | C5, C3 |
| E5 | Limitações completas (as-of anual/trimestral, regimes de coleta das notícias) | #247 | N0 | E1 | os 3 itens da #163 e a cobertura das notícias declarados |
| E6 | Alinhamento à rubrica: introdução, resumo, ABNT, apêndice de implementação, consistência | #248 | N1 | E2–E5, síntese §5 | C4, C2 completo |
| E7 | Apresentação da defesa (Beamer, em `text/`) | #249 | N1 | E6 | C8 |
| E8 | Stage 8.4 — job de cohort de produção | #202 | N2 (Stage) | — | C7 |
| E9 | Auditoria final em sessão separada | #237 | — | E1–E8 | C1–C8 com evidência; achados viram issue ligada ou recusa com motivo |

**Paralelismo.**
- E8 corre numa worktree própria, em paralelo ao texto, porque não toca `text/`.
- As entregas do texto são sequenciais (E1 → E2 → {E3, E4, E5} → E6 → E7) porque editam os
  mesmos `.tex`.

## 5. Pesquisa de referência (TCCs de excelência)

**Coleta.** Quatro frentes de pesquisa online com agentes econômicos (Sonnet), cada uma
relatando na própria resposta, com fonte e marca de "verificado na fonte":
1. TCCs de graduação premiados ou com nota máxima em IA/ML de universidades públicas de ponta;
2. TCCs e dissertações sobre previsão financeira com deep learning, incluindo os erros comuns
   da área;
3. critérios oficiais de avaliação (fichas, rubricas, regulamentos) e normas ABNT;
4. fontes primárias para a discussão (modelos simples de volatilidade, deep learning × métodos
   simples, modelos globais, ensemble de quantis, valor de resultado negativo, relato de estudo
   piloto).

**Síntese.** Um agente Opus 5.5 recebe os quatro relatórios e o texto atual e devolve:
1. a rubrica consolidada;
2. o que os trabalhos de referência têm e o nosso não tem, priorizado;
3. o que o nosso já faz acima da referência (para a defesa).

A síntese é gravada em `docs/tcc/RUBRICA-E-REFERENCIAS.md` e alimenta E4, E6 e E7.

## 6. Verificação mecânica do texto (em todo PR que toca `text/`)

1. **Compilação** pela imagem `texlive/texlive` via Docker; log sem `undefined`.
2. **Espaços reservados:** grep dos marcadores do C2.
3. **Números:** script de conferência (E1) que relê o scorecard e as tabelas gold da geração
   julgada e compara com os números das tabelas do capítulo 5.
4. **Citações:** toda chave usada existe no `.bib`; cada citação nova passa pelo `evidence-verifier`.

## 7. Decisões

| # | Decisão | Tipo | Escolha | Motivo | Status |
|---|---|---|---|---|---|
| D1 | Perfil pontual (RMSE, MAE, acurácia direcional) | P | **calcular, de forma enxuta**, sobre as previsões persistidas: uma tabela e um parágrafo, rotulados "calculado depois do veredito, descritivo"; acurácia direcional com IC binomial contra 0,5 e reportada só para modelos de mediana não nula (TFT, AR(1), GBM, média histórica) | o Método promete o perfil; cortar exigiria reescrever o Cap. 2 e o Cap. 4; a banca de engenharia vai perguntar; custo baixo, sem re-treino (síntese §2) | a ratificar |
| D2 | Enquadrar o projeto antigo como estudo piloto | P | sim, como motivação metodológica e sem números como evidência | pedido do dono em 2026-10-24 | ratificada pelo dono |
| D3 | Análise exploratória pós-confirmatória da média das sementes | P | **fazer uma única análise**, especificada abaixo **antes** de calcular | é a pergunta mais provável da arguição; pela convexidade da *pinball* (Jensen), a perda do quantil médio é sempre ≤ a média das perdas, então o sinal é garantido e só a magnitude informa, o que reduz o risco de pesca | a ratificar |
| D4 | Formato da apresentação | C | Beamer em `text/`, compilado pela mesma imagem | coerência com o texto em LaTeX; convenção comum em defesas de exatas | a ratificar |
| D5 | Winkler e VaR/Kupiec prometidos no Método | E | entregar a partir das tabelas gold existentes (`gold_metrics_by_run` tem `interval_score`; `gold_calibration_table` tem Kupiec POF); cortar a promessa só para o que não existir | coerência entre o prometido e o entregue (rubrica, critério 6) | aceita |

### Especificação da D3 (fixada em 2026-10-25, antes de qualquer cálculo)

- **Objeto.** Em cada ponto de decisão da amostra comum de H2 (n = 1.511 em h+1; 1.505 em h+7),
  em cada nível τ da grade, o quantil do *ensemble* é a média aritmética de `value_guardrail`
  das dez sementes do TFT no mesmo `target_timestamp` e no mesmo horizonte. Não há rearranjo
  adicional: a média de grades monotônicas é monotônica.
- **Medidas.**
  - *Pinball* média da grade do *ensemble* e sua razão contra a média das perdas por semente
    (4,050 e 4,063 × 10⁻³) e contra o EWMA-vol e o GBM.
  - Taxas de violação das duas caudas do par de 80% e PICP.
  - DM unilateral (variância retangular até a defasagem h − 1, correção HLN), a mesma
    especificação do confirmatório, do *ensemble* contra o EWMA-vol e contra o GBM, com
    **p-valores brutos** (sem Holm: a análise é exploratória).
- **Rótulo no texto.** "Análise exploratória pós-confirmatória (WAGENMAKERS et al., 2012): não
  altera o veredito." Junto, o custo: dez treinos contra um modelo de um parâmetro.
- **Leitura fixada antes.**
  - Se o *ensemble* tiver perda menor que a do EWMA-vol, isso vira **hipótese** para trabalho
    futuro.
  - Se não tiver, reforça que o limite está na informação das *features*.
  - Nenhum outro *ensemble* (mediana, pesos, subconjuntos de sementes) será calculado.

## 8. Ameaças à validade deste plano

- **Mesmo modelo como autor e auditor.** O auditor final é uma sessão separada, de contexto
  limpo e sem a conclusão do autor, mas é o mesmo modelo. A auto-preferência foi medida na
  literatura (Panickssery et al., 2024) e não fica eliminada.
- **Amostra de referência.** Os TCCs de excelência acháveis online são poucos e enviesados para
  os premiados e publicados. A rubrica vale como piso, não como garantia de nota.
- **Sem banca simulada humana.** C4 e C8 dependem de julgamento, e o veredito final continua
  sendo do dono e da banca.
- **Fontes do piloto.** O repositório do piloto não está nesta máquina. Só entra no texto o que
  tem fonte verificável no repositório atual (ADRs e o texto importado no commit `97d867d8`).

## 9. Registro vivo (surpresas e decisões no caminho)

- **2026-10-25.** A worktree da #202 já tinha o commit que cria a Stage 8.4 no roadmap, sem
  push, refeito sobre o `develop` atual. A E8 começa pelo PR desse commit.
- **2026-10-25 — checkout principal.** Havia um *cherry-pick* de `acb7cca6` parado no checkout
  principal do `develop`, anterior a esta sessão; o mesmo conteúdo já estava em `b545c6f5`. Foi
  abortado e o `develop` local avançou para o `origin/develop`. O Docker Desktop também estava
  parado e foi iniciado.
- **2026-10-25 — pesquisa de referência.** Não existe corpus público de "TCC nota 10" em IA. Os
  premiados verificados (CTIC/SBC) têm menos rigor estatístico que este trabalho e se destacam
  por clareza. A síntese está em [RUBRICA-E-REFERENCIAS](./RUBRICA-E-REFERENCIAS.md).
- **2026-10-25 — instrumento real.** O curso é Engenharia Mecatrônica (UFSC Joinville). Pelo
  regulamento do campus, a apresentação tem até 20 minutos, por isso o C8 passou de 25 para 20.
  A cópia vai à banca 15 dias antes. As bancas de 2026/2 vão de 09 a 27/nov, o que deixa pouca
  folga. A data da defesa é do dono.
- **2026-10-25 — achado na E1.** A frase "a calibração é propriedade do *ensemble* de sementes"
  estava imprecisa, porque o *gate* julga a média das taxas por semente. Foi corrigida no próprio
  PR da E1 (#240).
- **2026-10-25 — entregas ajustadas pela síntese.**
  - A E2 passa a cobrir também a D1, a D5 e a reprodução.
  - A análise D3 vira uma entrega própria, a E4a: código em `tests/tcc/`, opt-in como o C1, com
    os números conferidos por teste. A E4 consome o resultado.
  - A E6 ganha trabalhos correlatos, a tabela de objetivos, contribuições reduzidas e os
    elementos formais.
- **2026-10-25 — furo no C2.** A compilação sem `undefined` não pega comando LaTeX corrompido
  que ainda compila: um `\textit` colapsado em TAB + "extit" pelo heredoc do Bash passou e só a
  auditoria da E1 achou. O script de build passou a procurar TAB, CR, FF ou BS seguidos de
  `ext`, `egin` e similares, e os fragmentos `extit`/`extbf` sem barra. Edições no texto passam a
  usar só Write/Edit ou scripts gravados por Write, nunca heredoc.
- **2026-10-25 — figuras.** As figuras da 8.3 foram desenhadas para o dossiê: identificadores
  internos e estatuto na legenda, regras internas no rodapé. Entra a E2a (#250), um estilo de
  apresentação gerado do mesmo gold, com o dossiê inalterado byte a byte.
- **2026-10-25 — gate local dos PRs só de texto (decisão da sessão mestra, a ratificar).**
  - O `make check` local leva cerca de 49 minutos e não exercita `text/`; a CI roda o mesmo
    `make check` e é condição de merge.
  - PR que só toca `text/` roda localmente a compilação e a varredura de comandos colapsados, e
    declara o desvio no corpo.
  - PR com código (#243, #250, Stage 8.4) segue com o `make check` local.
  - E1 (#240) mergeada em `a0d2dde4`.
- **2026-10-25 — E1 auditada.** Aprovada pela `issue-audit` em contexto limpo (20 testes de C1 e
  cerca de 40 números de prosa conferidos à mão); um finding dentro do escopo foi corrigido no PR.
