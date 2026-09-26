---
name: evidence-resolution
description: Triagem e resolução autônoma de perguntas teóricas/metodológicas por evidência verificada — invocar ANTES de perguntar qualquer coisa ao humano (AskUserQuestion, bloco B1/B2, "a ratificar") e sempre que um fork de concept/technical/doc de domínio/ADR/finding depender de estatística, ML, séries temporais, finanças quantitativas ou convenção de biblioteca. Triggers (PT/EN) — "fork", "bifurcação", "a ratificar", "qual convenção", "o que a literatura diz", "sem fonte primária", "qual a escolha metodológica certa", "which convention", "is this statistically valid". O agente fecha E (evidência decide) e C (convenção sem vencedor) sozinho; só P (preferência/negócio) chega ao humano. O hook `triage_gate` recusa pergunta sem header `P:`.
metadata:
  status: draft
---

# Evidence Resolution

Perguntas de **informação** se resolvem com evidência; só perguntas de **preferência** são do
decisor (a "base de decisão" de Howard 1988 separa alternativas, informação e preferências).
O humano pesquisa este tema e não tem resposta melhor que a literatura: devolver a ele uma
pergunta de informação é custo sem ganho de rigor.

## 1. Triagem — uma linha por pergunta, antes de qualquer outra coisa

| Classe | Quem fecha | Sinais |
|---|---|---|
| **P** preferência | humano | muda escopo/hipótese/claim ratificado (overview §3–§4); prioridade, prazo, custo de compute; editorial/público do TCC; ação externa irreversível (merge em `main`, publicar); a evidência entrega uma *curva* e escolher o ponto é apetite de risco sem convenção da área |
| **E** evidência decide | agente | existe resposta verificável: fórmula, propriedade de estimador, validade de um teste sob hipóteses, comportamento de lib, pré-condição de método |
| **C** convenção | agente | ≥2 opções defensáveis e a evidência não elege vencedora |

Mudanças de classe (são as únicas):
- **C vira P depois de haver dados confirmatórios** (8.1 rodado): escolher convenção vendo o
  resultado é o *garden of forking paths* (Gelman & Loken 2014), o que o pré-registro existe para
  impedir (Nosek et al. 2018). Antes disso, C é do agente.
- **E/C vira P** se a evidência verificada for conflitante **e** as opções trocarem o veredito de
  H1/H2/H3 — sobe com o dossiê (§5), não como pergunta aberta.
- Irreversível/caro (port, formato persistido) **não** é P por si: exige §4.2 obrigatório.

## 2. Pesquisa — 1 subagente fresco por lote

Juntar todas as perguntas E/C do momento num lote e despachar **um** `evidence-researcher`
(`.claude/agents/` — o protocolo de fontes já é o system prompt dele; não colar brief). A
mensagem leva só: as perguntas com as opções + os caminhos do projeto relevantes. **Não** incluir
sua inclinação (induz viés de confirmação no pesquisador). Lote > ~6 perguntas → dividir por tema
e despachar em paralelo. Fato sobre o **nosso dado** (volume, distribuição, significado de campo)
não é pesquisa bibliográfica: é medição — skill `data-shape-evidence`.

## 3. Decisão

- **E:** a opção que a evidência verificada sustenta.
- **C:** o **primeiro degrau que discrimina**:
  1. já ratificado no projeto (overview, ADR, doc de domínio) — coerência entre Stages;
  2. default da implementação de referência que serve de oráculo (ADR 0.0.0021) — mantém a
     equivalência testável;
  3. recomendação do paper de origem do método ou do livro-texto canônico;
  4. a mais conservadora para o claim confirmatório (menor risco de falso positivo);
  5. a mais simples.
- Alternativa que plausivelmente muda o resultado → **sensibilidade pré-registrada** (perfil,
  nunca veredito): a análise multiverso/especificação resolve "não há escolha única defensável"
  reportando o espaço, não elegendo por gosto (Steegen et al. 2016; Simonsohn et al. 2020).
  Alternativa que não muda nada → só "Alternativas descartadas" no ADR.

## 4. Verificação — antes de gravar

1. `python scripts/verify_citations.py <arquivo-com-as-citações>` (stdlib; roda no host) sobre
   o artefato final (o pesquisador já checou as dele; aqui entram as que você escreveu).
   `NOT_FOUND`/`MISMATCH` → corrigir ou remover a citação, nunca manter; exit 2 = rede, repetir.
   Motivo: mesmo o GPT-4 fabricou 18% das citações e errou metadados em 24% das reais
   (Walters & Wilder 2023).
2. Decisão que entra no **veredito**, num **contrato persistido** ou num **port**: despachar um
   `evidence-verifier` com só `{afirmação, trecho literal, localizador, fonte}` por item; ele
   lê a fonte bruta e responde `sustenta | parcial | não sustenta`. Verificação por perguntas
   independentes da resposta original reduz alucinação (Chain-of-Verification, Dhuliawala et al.
   2024). "Não sustenta" → volta ao §3 sem aquela evidência.
3. `[SEM-FONTE-PRIMÁRIA]` é aceitável só em **C**, declarando o degrau que decidiu; em **E** é
   lacuna → reclassificar como C (se houver opções defensáveis) ou HALT (fórmula sem nenhuma base).

## 5. Registro — decisão sai decidida

Nada de "a ratificar". Gravar onde o processo já registra (ADR §Alternatives, §7 do technical,
doc de domínio) neste formato — é por ele que o humano audita, sem ser interrompido:

```
[decision:E|C] <id> — <pergunta em 1 linha>
Escolha: <opção> · Alternativas: <…> · Degrau (C): <1–5>
Base: <Autor Ano, §/Eq./p.> "<trecho ≤2 frases>" [doi ok] · <pkg@versão função: default=…>
Sensibilidade pré-registrada: <alternativa> | nenhuma · Reversível: sim | não (motivo)
```

## 6. Pergunta ao humano — só P

- Resolver antes todos os E/C do mesmo lote; a pergunta P chega com eles como contexto decidido.
- `AskUserQuestion`: todo `header` começa com `P:` (ex.: `P:Escopo`). Fork listado em texto leva
  `[P]` na linha. O hook `.claude/hooks/triage_gate.py` bloqueia o que vier sem marca.
- Formato da pergunta: PROMPT-step §2 "Anatomia da pergunta ao humano". Havendo resultado
  executável, a pergunta vem ancorada nele (bloco "Valide você", PROMPT-stage §0 do relatório):
  saída bruta + passos para reproduzir + o que cada opção muda no resultado.

## Gotchas (execução real)

- **Pesquisar não basta.** Na #78 (set/2026) o agente citou Eq./página com rigor e ainda assim
  devolveu 11 convenções para ratificação humana: sem regra de quem decide, pesquisa boa não
  reduz perguntas. Classifique cada pergunta pelos sinais da tabela do §1, não por semelhança
  com casos anteriores.
- **Resumo ≠ fonte.** O WebFetch (resumido por modelo auxiliar) afirmou que o PreToolUse não
  intercepta `AskUserQuestion`; o markdown bruto da doc dizia o contrário. Fato load-bearing →
  ler a fonte bruta (`curl` do `.md`/PDF, código da lib na versão pinada).
- **Comportamento do oráculo é degrau 2, não motivo de parada.** Ex.: variância de longo prazo ≤ 0
  no DM → seguir o R `dm.test` e registrar a ocorrência.
