# Análises pós-veredito — perfil pontual (D1), média das sementes (D3) e resposta da largura (D4) — AAPL

> **Calculado depois do veredito; não altera o veredito.** Nada aqui entra no scorecard
> confirmatório nem nas famílias de Holm. D1 é descritivo; D3 é uma análise exploratória
> pós-confirmatória (WAGENMAKERS et al., 2012).

Origem: plano de fechamento do TCC (#237, `docs/tcc/PLANO-FECHAMENTO.md` §7, decisões D1 e
D3); issue #243. A especificação da D3 foi fixada no commit `cdf434bf` (2026-10-25), antes
de qualquer cálculo, e é seguida sem desvio: um único *ensemble* (média aritmética de
`value_guardrail` das dez sementes, por ponto e nível, sem rearranjo), as medidas listadas
lá e nenhuma outra combinação de sementes.

A D4 (issue #272) entrou depois, a pedido do orientador, para dar número à leitura das
figuras de nitidez e de diferencial de perda do TCC, na Seção 4.7.1 (a largura do EWMA-vol acompanha a volatilidade; a do TFT, menos).
**Não teve especificação prévia:** uma sonda exploratória sobre as mesmas previsões veio
antes deste código, e a medida foi escolhida sabendo o que ela mostrava. É descritiva,
não tem teste nem p-valor e não altera o veredito. A volatilidade de referência é a
`volatility_20d` do registro, na sessão de decisão (a mesma informação que os modelos têm).

## 1. Proveniência

| campo | valor |
|---|---|
| código | [`tests/tcc/post_verdict_report.py`](../../tests/tcc/post_verdict_report.py) e [`tests/tcc/post_verdict.py`](../../tests/tcc/post_verdict.py), commit `46acf3944047e6aca62fa56cdc010b4fc5a62100` |
| especificação da D3 | commit `cdf434bf1c10db1818ad808b5f0fe02049956c56` |
| `preregistration_ref` | `aapl_confirmatory-r3-00fd83d9cd39` |
| `generation_digest` da cópia julgada | `96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539` |
| partição | `AAPL/aapl_confirmatory-r0-665f45d9169a` |
| entrada | `data/cohorts/aapl/` montada `:ro`: cópia julgada (`CONTENTS.sha256` conferido), realizado pelo `ReadTrainingGrid` (fingerprint conferido contra o manifesto), silver do cohort (unidades conferidas contra o `silver_content` da cópia) |
| amostra | a amostra comum de H2 montada pelo próprio `SeriesAssembly` do gold, com os parâmetros do manifesto |

Como reproduzir (imprime o bloco da §2; o teste exige que ele seja idêntico ao desta página):

```sh
python -m tests.tcc.post_verdict_report <data_root>
TCC_DATA_ROOT=<data_root> uv run --no-sync pytest tests/tcc/test_post_verdict_numbers.py -rs -q
```

**Sanidade antes de qualquer número.** O código recalcula, por (modelo, semente, horizonte),
a *pinball* média da grade, o MAE da mediana (que tem de ser 2 × a *pinball* em τ = 0,5) e o
n da amostra comum, e o DM retangular do TFT contra cada comparador; tudo tem de bater com
`gold_metrics_by_run` e `gold_dm_results` da cópia julgada, senão o cálculo para. As médias
por semente do TFT (4,050 e 4,063 × 10⁻³), do EWMA-vol e do GBM bateram.

## 2. Números

O bloco abaixo é gerado pelo código (separador decimal ponto).

<!-- BEGIN: post-verdict-numbers -->

`preregistration_ref` `aapl_confirmatory-r3-00fd83d9cd39`; `generation_digest` `96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539`; n comum: h+1 = 1511, h+7 = 1505.

Sanidade: as 132 conferências contra o gold julgado bateram (tolerância relativa 1e-09): pinball média da grade, MAE = 2·pinball(0,5) e n por (modelo, semente, horizonte) na amostra comum; d̄, estatística e p do DM retangular do TFT contra cada comparador.

### D1 — perfil pontual da mediana (τ = 0,5)

RMSE e MAE em 10⁻²; TFT: média das 10 sementes [mín.; máx.]. Acurácia direcional: fração de pontos com mediana·realizado > 0 (média das sementes no TFT), IC de Wilson de 95 %.

Referência de taxa-base: fração de realizados > 0 na amostra comum, h+1 = 0.5314, h+7 = 0.5309 (uma mediana sempre positiva acerta exatamente essa fração).

| modelo | h | RMSE | MAE | acurácia direcional | IC 95 % | empates |
|---|---|---|---|---|---|---|
| Retorno nulo | 1 | 1.999 | 1.383 | não se aplica (mediana identicamente nula) | — | — |
| Média histórica | 1 | 1.997 | 1.379 | 0.5314 | [0.5062; 0.5565] | 4.0 |
| AR(1) | 1 | 2.004 | 1.385 | 0.5142 | [0.4890; 0.5394] | 4.0 |
| EWMA-vol | 1 | 1.999 | 1.383 | não se aplica (mediana identicamente nula) | — | — |
| Quantis empíricos | 1 | 2.000 | 1.384 | 0.5235 | [0.4983; 0.5486] | 4.0 |
| GBM quantílico | 1 | 1.995 | 1.379 | 0.5162 | [0.4910; 0.5413] | 4.0 |
| TFT | 1 | 2.004 [1.993; 2.019] | 1.386 [1.374; 1.404] | 0.5285 | [0.5033; 0.5536] | 4.0 |
| Retorno nulo | 7 | 2.001 | 1.385 | não se aplica (mediana identicamente nula) | — | — |
| Média histórica | 7 | 2.000 | 1.382 | 0.5309 | [0.5056; 0.5560] | 4.0 |
| AR(1) | 7 | 2.000 | 1.382 | 0.5309 | [0.5056; 0.5560] | 4.0 |
| EWMA-vol | 7 | 2.001 | 1.385 | não se aplica (mediana identicamente nula) | — | — |
| Quantis empíricos | 7 | 2.003 | 1.386 | 0.5296 | [0.5043; 0.5547] | 4.0 |
| GBM quantílico | 7 | 1.999 | 1.382 | 0.5369 | [0.5116; 0.5619] | 4.0 |
| TFT | 7 | 2.009 [2.001; 2.023] | 1.391 [1.382; 1.406] | 0.5227 | [0.4975; 0.5479] | 4.0 |

### D3 — média das sementes do TFT (especificação `cdf434bf`)

Pinball média da grade em 10⁻³. Razão < 1: o *ensemble* perde menos que a referência.

| h | n | *ensemble* | média das perdas por semente | razão | EWMA-vol | razão | GBM | razão |
|---|---|---|---|---|---|---|---|---|
| 1 | 1511 | 3.9875 | 4.0504 | 0.9845 | 3.9196 | 1.0173 | 3.9800 | 1.0019 |
| 7 | 1505 | 4.0084 | 4.0634 | 0.9865 | 4.0005 | 1.0020 | 4.0258 | 0.9957 |

Par de 80 % (τ = 0,1 e 0,9): violação inferior (y ≤ q₀,₁), superior (y > q₀,₉) e PICP (nominais 0,10, 0,10 e 0,80). A linha "por semente" é a média das taxas das 10 sementes, só como referência.

| h | série | violação inferior | violação superior | PICP |
|---|---|---|---|---|
| 1 | *ensemble* | 0.0854 | 0.0827 | 0.8319 |
| 1 | por semente | 0.0887 | 0.0936 | 0.8176 |
| 7 | *ensemble* | 0.0837 | 0.0864 | 0.8299 |
| 7 | por semente | 0.0882 | 0.0938 | 0.8181 |

DM unilateral (H1: o *ensemble* tem perda esperada menor), variância retangular até a defasagem h-1, correção HLN; d̄ em 10⁻⁵; **p-valor bruto** (sem Holm).

| h | comparador | d̄ | estatística | p bruto | fallback |
|---|---|---|---|---|---|
| 1 | EWMA-vol | 6.792 | 2.097 | 0.9819 | não |
| 1 | GBM quantílico | 0.754 | 0.422 | 0.6634 | não |
| 7 | EWMA-vol | 0.795 | 0.173 | 0.5685 | não |
| 7 | GBM quantílico | -1.734 | -0.973 | 0.1654 | não |

### D4 — resposta da largura do par de 80 % à volatilidade (issue #272)

Largura q₀,₉ - q₀,₁ por ponto (TFT: média das larguras das 10 sementes). Spearman: correlação de postos entre a largura e `volatility_20d` na sessão de decisão. Dispersão: quantil de 95 % ÷ quantil de 5 % da largura (tipo 7). Mediana em 10⁻².

| modelo | h | n | Spearman | mediana | dispersão |
|---|---|---|---|---|---|
| AR(1) | 1 | 1511 | -0.229 | 4.192 | 1.15 |
| EWMA-vol | 1 | 1511 | 0.929 | 4.264 | 3.17 |
| Quantis empíricos | 1 | 1511 | 0.361 | 4.162 | 2.17 |
| GBM quantílico | 1 | 1511 | 0.458 | 3.869 | 2.06 |
| TFT | 1 | 1511 | 0.496 | 4.404 | 1.68 |
| AR(1) | 7 | 1505 | -0.221 | 4.192 | 1.15 |
| EWMA-vol | 7 | 1505 | 0.928 | 4.273 | 3.16 |
| Quantis empíricos | 7 | 1505 | 0.359 | 4.162 | 2.17 |
| GBM quantílico | 7 | 1505 | 0.494 | 3.858 | 1.61 |
| TFT | 7 | 1505 | 0.444 | 4.405 | 1.58 |

<!-- END: post-verdict-numbers -->

## 3. Leitura

**D1 (descritivo).** O erro pontual da mediana é praticamente o mesmo em todos os modelos:
RMSE ≈ 2,0 × 10⁻² e MAE ≈ 1,38 × 10⁻² nos dois horizontes, com diferenças da ordem da
dispersão entre as sementes do TFT. Retorno nulo e EWMA-vol têm mediana identicamente nula
(previsão de retorno zero em todo ponto) e ficam fora da acurácia direcional, como o plano
fixou. Os quantis empíricos entram, porque a mediana deles não é nula; o plano os omitia da
lista de exemplos, mas a regra é a da mediana não nula. A acurácia direcional fica entre
0,51 e 0,54; vários ICs excluem 0,5, mas a referência honesta é a taxa-base de dias de alta
(0,531 em h+1 e h+7): a média histórica, de mediana sempre positiva, acerta exatamente essa
fração, e nenhum modelo se afasta dela de forma relevante. O TFT fica em 0,529 (h+1) e
0,523 (h+7), abaixo da taxa-base. Não há evidência de habilidade direcional.

**D3 (exploratório).** A média das sementes reduz a perda do TFT em 1,6 % (h+1) e 1,4 % (h+7)
contra a média das perdas por semente, como a convexidade da *pinball* garante (só a magnitude
informa). Mesmo assim, o *ensemble* continua com perda maior que a do EWMA-vol nos dois
horizontes (razão 1,017 em h+1 e 1,002 em h+7; DM unilateral sem rejeição, p bruto 0,98 e
0,57) e fica empatado com o GBM (p bruto 0,66 e 0,17). Pela leitura fixada antes do cálculo,
o resultado **reforça que o limite está na informação das *features***, não na variância
entre sementes. A média também aumenta a sobrecobertura do par de 80 % (PICP 0,832 e
0,830 contra 0,818 da média por semente; nominal 0,80). O custo do *ensemble* são dez
treinos do TFT contra um modelo de um parâmetro (o EWMA-vol).

**D4 (descritivo, sem especificação prévia).** A largura do par de 80 % do EWMA-vol segue a
volatilidade quase em postos (Spearman 0,93 nos dois horizontes), e é a que mais varia ao
longo da série (o quantil de 95 % da largura é 3,2 vezes o de 5 %). O TFT, com as larguras
médias das dez sementes, tem correlação 0,50 (h+1) e 0,44 (h+7) e varia bem menos (1,7 e 1,6
vezes), com a maior largura mediana dos modelos (4,40 × 10⁻² contra 4,26–4,27 × 10⁻² do
EWMA-vol). O GBM e os quantis empíricos ficam entre os dois; o AR(1), de variância fixa por
*fold*, tem correlação negativa (−0,23). A leitura é coerente com a figura do diferencial de perda: o TFT perde mais
para o EWMA-vol quando a volatilidade sobe de repente (início de 2020), justamente quando a
largura dele reage pouco. É uma descrição do comportamento dos intervalos, e não a causa
demonstrada da diferença de perda.
