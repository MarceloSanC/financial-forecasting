---
name: didactic-explanation
description: Como explicar conceitos teóricos, arquiteturais ou de domínio ao humano de forma clara e didática. Invocar SEMPRE que for explicar um conceito ao usuário — alinhamento de abordagem no kickoff de Stage (RUNBOOK Passo 1b), walkthrough de concept/ADR, veredito de auditoria, resposta a "me explica X", "o que é", "como funciona", "qual a ideia de" — ANTES de escrever a explicação. Não governa artefatos técnicos (concept/ADR/código mantêm precisão e nomes exatos).
metadata:
  status: draft
  applies_when:
    camada_alvo: [any]
    stage_kind: any
    fase: [any]
---

# Didactic Explanation

Explicação dirigida ao humano existe para habilitar o julgamento que só ele tem —
nuance de negócio, correlação sutil com o resto do projeto. Se a explicação exige
esforço para decodificar, esse julgamento não acontece (ou acontece tarde, na
auditoria, quando redirecionar custa retrabalho). Regra-mestre: **o custo de
entender é do autor, não do leitor** — o texto também será lido no fim de um dia
de trabalho intelectual pesado.

## Fronteira: dois registros

- **Explicação para o humano** (chat, kickoff, walkthrough, veredito de
  auditoria) → esta skill.
- **Artefato técnico** (concept, ADR, technical, código, docstring) → precisão
  total, nomes exatos — **fora** desta skill. Não "didatizar" artefato.

## Regras

### 1. Um assunto por vez, completo

Agrupar pelo **objeto** da explicação (a entidade, a decisão, a métrica),
esgotando o que importa sobre ele antes de passar ao próximo — nunca pelo
aspecto/fase que atravessa vários objetos. Cada troca de assunto no meio força o
leitor a recarregar o contexto mental e segurar ideias meio-explicadas.

```
Estrutura difícil (por aspecto):        Estrutura fácil (por objeto):
  Aspecto 1: fala de X, Y e Z             Sobre X: aspectos 1, 2 e 3
  Aspecto 2: fala de X, Y e Z             Sobre Y: aspectos 1, 2 e 3
  Aspecto 3: fala de X, Y e Z             Sobre Z: aspectos 1, 2 e 3
  Conclusão sobre X, Y e Z                Conclusão sobre X, Y e Z
```

### 2. O que é → o que faz no sistema → por que importa

Nessa ordem, antes de qualquer detalhe. O leitor precisa da ideia completa do
objeto antes das suas nuances.

### 3. Termos técnicos são bem-vindos — desde que carregados

Termo técnico e sigla **devem** aparecer (enriquecem o vocabulário do time) —
mas os com chance de serem desconhecidos ou mal interpretados ganham
explicação/contextualização na primeira ocorrência. O anti-padrão é despejar
termos para encurtar o texto: fica sucinto e caro de decodificar. **Não trocar
clareza por concisão.**

### 4. Sem metáforas e analogias ilustrativas

Dizer diretamente o que a coisa é e o que faz no sistema. Metáfora adiciona uma
camada de tradução que o leitor precisa desfazer — e pode traduzir errado.

### 5. Sem palavras de duplo sentido ou jargão coloquial

"morde", "machuca", "paga o preço"… → usar o termo direto: "afeta", "degrada",
"limita".

### 6. Nome de variável/campo só quando o nome é o assunto

Referenciar o conceito ("a data de vencimento"), não o identificador
(`due_date`) — exceto quando o identificador em si é o que está em discussão.
O nome exato vive no artefato técnico, que o leitor consulta quando precisar.

### 7. Decisão para o humano: formato proporcional ao contexto

- Pergunta direta, de pouco contexto → `AskUserQuestion`.
- Decisão que exige contexto rico e análise das opções → **bloco numerado
  identificável** (B1, B2…) dentro da explicação; o humano responde
  referenciando o bloco (mesmo padrão dos findings F1/F2/F3 das auditorias).

### 8. Tamanho: ~1 tela

Se a explicação cresce além disso, ela mesma vira barreira. Cortar detalhe que
não muda o entendimento; o detalhe fino vive no artefato técnico.

## Gotchas (das falhas reais que geraram esta skill — sessão 2026-07-15)

- **Duplo sentido + siglas sem carga:** "onde o limite (I12) morde: a faixa em
  t0 é a linha da matriz" obriga o leitor a decodificar "morde", "I12", "t0" e
  "linha da matriz" ao mesmo tempo. Reescrita: "onde o limite pesa: a
  reconstrução só conhece o vencimento atual, então a faixa de atraso calculada
  para datas passadas é aproximada quando o vencimento foi renegociado — e essa
  faixa é exatamente o ponto de partida da matriz de rolagem".
- **Organização por aspecto:** uma explicação organizada pelas etapas do
  processo ("na etapa 1 fazemos A com X e Y; na etapa 2…") obrigou o leitor a
  "lembrar sobre o que você está falando em cada etapa". Reorganizada por
  objeto (cada entidade explicada por completo), a mesma informação ficou
  legível de uma passada.
- **Metáfora no lugar da função:** explicar uma camada de dados por analogia
  culinária pareceu didático, mas o leitor pediu a explicação direta — o que a
  camada faz (valida, data e isola o que entra) e por que existe (para o
  cálculo não ler dado cru). A analogia só adiou essa resposta.
- **Explicar-primeiro vence perguntar-primeiro:** o questionário "perguntas até
  saturar" caiu em desuso porque exigia do humano gerar respostas a frio.
  Apresentar o quadro e colher a reação é o formato de menor custo que
  funciona — e é onde as bifurcações reais aparecem.
