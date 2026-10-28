# Ensaio da defesa — respostas curtas

Perguntas que o orientador anteviu na revisão de 2026-10-28 (#272). Cada resposta cabe em
cerca de 40 segundos e usa só números que estão no texto; a seção de onde vem cada um está
entre colchetes. O que não está no texto aparece marcado como **fora do texto**.

## 1. Se o EWMA venceu, qual a contribuição de usar o TFT?

- A contribuição pretendida nunca foi a arquitetura, e sim a avaliação [2.8]. A pergunta é se
  um modelo profundo, avaliado com regras fixadas antes, entrega uma distribuição calibrada e
  se supera comparadores fortes. A resposta tem valor qualquer que seja o resultado.
- O TFT entregou o que H1 pedia: a calibração do intervalo de 80% não foi rejeitada nos dois
  horizontes, com poder acima de 0,97 [5.1]. Ele também supera os ingênuos e empata com os
  fortes em h+7 [4.4].
- O resultado negativo é informativo. O GBM, com as mesmas 55 *features*, também perdeu para o
  EWMA-vol. Então o limite está mais na informação das *features* sobre a escala do que no
  TFT [4.7.1].
- Na cauda, o quadro se inverte. No VaR de 98%, o EWMA-vol viola 3,31% contra 2% nominais, e
  o TFT, 2,33% [4.2.1 e 5.3]. A menor perda média não garante a melhor cauda.
- Mensagem prática: um modelo de volatilidade simples é a barra mínima para qualquer modelo
  de retornos diários avaliado pela distribuição preditiva [5.3].

## 2. Por que EWMA e não GARCH?

- O EWMA da RiskMetrics é o comparador de volatilidade mais simples e mais usado na prática.
  O λ = 0,94 vem fixado do documento técnico, e nada é estimado com os dados. Por isso ele
  não abre nenhum grau de liberdade para escolher depois [3.7].
- O GARCH é o próximo degrau natural. Hansen e Lunde (2005) mostram que o GARCH(1,1) é difícil
  de superar e que, em ações, modelos com efeito alavancagem foram melhores [4.7.2]. Por isso
  o comparador assimétrico (GJR-GARCH) está nos trabalhos futuros, como hipótese (vii) [5.5].
- Se o EWMA, que é mais simples, já não foi superado, um GARCH bem ajustado só tornaria a
  barra mais alta. A conclusão de H2 não muda de direção.
- **Fora do texto:** o EWMA costuma ser lido como um GARCH(1,1) integrado e sem constante. Se
  for usar esse argumento na banca, confira a fonte antes.

## 3. Qual modelo você entregaria, já que várias sementes isoladas não passam na calibração?

- A calibração vale para o procedimento de treino, em média sobre as sementes. A cobertura do
  intervalo de 80% de uma semente isolada variou de 0,772 a 0,872 em h+1 [5.3]. Um único
  treino do TFT, portanto, não é garantia de intervalo calibrado.
- Para o intervalo central, eu entregaria o EWMA-vol: menor perda nos dois horizontes, um
  parâmetro, nenhum treino [4.3].
- Se a exigência for a cauda (VaR de 98%), o EWMA gaussiano subestima o risco, e o TFT e o
  GBM ficam mais perto do nominal [5.3]. Nesse caso, o candidato é o TFT com as dez sementes
  combinadas e com correção conformal.
  - A média das sementes reduziu a perda em 1,6%, mas ficou sobrecoberta (0,832) [4.7.3].
  - A CQR levou a cobertura do intervalo de 80% a 0,798 e 0,800 [4.2.2].
  - **A combinação das duas não foi avaliada.** É o que eu testaria antes de entregar.

## 4. Por que prever o retorno de um dia sete pregões à frente, e não o acumulado de sete dias?

- O decodificador do TFT emite um valor por passo, e o alvo de cada passo é o retorno de um
  dia [3.4]. Com o mesmo tipo de alvo nos dois horizontes, a diferença entre h+1 e h+7 mede
  só quanto a informação envelhece. Não entra mudança de escala, e por isso nenhuma regra √h
  se aplica aos comparadores [3.4].
- O retorno acumulado de sete dias é outra pergunta: o risco de quem fica posicionado por uma
  semana. Os alvos de decisões vizinhas se sobreporiam em seis de sete dias, o que cria
  dependência serial forte entre os erros e reduz a amostra efetiva.
- É uma extensão legítima, sobretudo para risco (VaR de período de manutenção), e cabe
  num novo pré-registro.

## Perguntas administrativas do orientador (só o autor responde)

Prazo para protocolar a defesa, pedido de defesa e composição da banca:
- as bancas de 2026/2 vão de 09 a 27/nov;
- a cópia vai à banca 15 dias antes (Art. 13 do regulamento de Joinville; PLANO-FECHAMENTO §10, item 5);
- os nomes da banca e a data de aprovação seguem pendentes em `text/Main.tex` (§10, itens 1 e 2).
