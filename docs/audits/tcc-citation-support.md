---
title: Auditoria do respaldo das afirmações teóricas do TCC nas fontes citadas
description: Verificação, afirmação por afirmação, de que cada frase teórica do texto do TCC é sustentada pela fonte que cita, lida na fonte primária, com veredito, trecho literal e a correção aplicada
when-use: Consultar antes de alterar uma frase com \cite em text/, ao acrescentar uma fonte ao .bib, ou ao questionar se uma afirmação do TCC tem respaldo na literatura
keywords: [audit, tcc, citations, bibliography, evidence, primary-source, text, latex, bib, doi]
status: closed
created_at: 2026-10-17
updated_at: 2026-10-17
audit_id: tcc-citation-support
scope: [text/3_Revisao_Teorica/3_Revisao_Teorica.tex, text/2_Introducao/2_Introducao.tex, text/4_Metodo/4_Metodo.tex, text/5_Resultados/5_Resultados.tex, text/6_Conclusoes/6_Conclusoes.tex, text/8_Apendices/8_Apendices.tex, text/7_Referencias/7_Referencias.bib]
references:
  - domain/evaluation/probabilistic-forecast-evaluation.md
  - domain/modeling/quantile-model-training.md
---

# Auditoria do respaldo das afirmações teóricas do TCC nas fontes citadas

Issue [#169](https://github.com/MarceloSanC/financial-forecasting/issues/169). Remediação aplicada no
mesmo PR (commits `[#169/task-01]` a `[#169/task-03]` e as correções pós-verificação), por isso a
auditoria nasce `closed`. Auditoria nível raiz: o texto do TCC não pertence a nenhum bounded context.

## 1. Como a auditoria foi feita

- **Texto auditado:** o estado de `develop` em `c96db62`. Todo `arquivo:linha` abaixo se refere a
  esse estado. Cada linha dos `.tex` é um parágrafo inteiro, então a linha localiza o parágrafo e o
  trecho citado localiza a frase.
- **Extração:** todas as ocorrências de `\cite` em `text/` (119 comandos, 136 pares chave × local,
  61 chaves distintas; a cobertura de cada par por uma linha da tabela foi conferida por script) e
  todas as frases do capítulo de Fundamentação Teórica (`3_Revisao_Teorica.tex`), com ou sem `\cite`.
- **Leitura das fontes:** 15 lotes de até 4 fontes, cada um com um pesquisador que leu o texto bruto
  da fonte primária (PDF do periódico, *working paper* ou *preprint* dos próprios autores, código da
  versão pinada), seguido de uma repescagem de 3 lotes para as fontes inacessíveis na primeira
  rodada. Resumo de ferramenta, wiki, blog e os docs de domínio do projeto não contaram como fonte;
  serviram só como pista de localizador.
- **Verificação adversarial:** as afirmações que sustentam uma decisão do projeto (rearranjo, CQR,
  NexCP, Beta da cobertura, DM, subséries, Monte Carlo, Wilson, MCS, bloco do *bootstrap*, H3,
  CRPS) foram reconferidas por três verificadores independentes, sem contexto prévio, sobre o trecho
  literal e a fonte bruta (§5).
- **Metadados do `.bib`:** cada entrada citada foi conferida contra o DOI (Crossref) ou a página do
  editor; `python scripts/verify_citations.py text/7_Referencias/7_Referencias.bib` devolve `OK` para
  os 53 DOIs do arquivo (§4).
- **Versão lida:** quando a versão lida não é a publicada, a coluna "Fonte" diz qual foi
  (WP = *working paper*; TR = *technical report*). A paginação, nesses casos, é a da versão lida.

**Vereditos:** **S** sustenta · **R** sustenta com ressalva (condição omitida, generalização, direção
ou atribuição) · **N** não sustenta · **NV** não verificável (fonte inacessível; declarado, nunca
presumido). Toda linha R, N ou NV tem correção aplicada ou mitigação declarada.

## 2. Resumo

| | Quantidade |
|---|---|
| Linhas da tabela §3 (uma afirmação, às vezes repetida em mais de um local) | 101 |
| Vereditos (linhas com locais de veredito diferente contam mais de um) | 109 |
| Sustenta | 34 |
| Sustenta com ressalva | 61 |
| Não sustenta | 7 |
| Não verificável | 7 (3 passaram a "sustenta" com fonte substituta lida: B5.3, B6.3, B7.6) |
| Entradas do `.bib` citadas conferidas | 61, mais 8 novas e ACERBI2002, que já estava no `.bib` mas não era citada |

As 68 ressalvas e não sustentações estão corrigidas no texto. As 4 não verificáveis que restam
(B9.5, B15.1, B15.2 e a parte de McNeil em B7.7) foram rebaixadas ou trocadas de fonte, conforme o §6.

Os sete "não sustenta":

1. **Fama (1991)** — o texto dizia que Fama consolida a tese de que a previsibilidade é "a exceção";
   Fama relata previsibilidade documentada e diz que a hipótese conjunta impede interpretá-la (B1.1).
2. **Koenker e Bassett (1978)** como fonte de "arcabouço para representar incerteza em faixas de
   risco": o artigo trata de estimação robusta no modelo linear (B3.4).
3. **Convenção do DM com variância negativa** atribuída implicitamente a Diebold e Mariano: eles
   tratam a variância como nula e **rejeitam** a nula; o recálculo com \(h = 1\) é do `dm.test` (B9.4).
4. **Pineau et al. (2021)** como medição de "fração significativa" de trabalhos irreprodutíveis com
   código aberto, por omissões que incluiriam sementes: o relatório descreve o programa e lista causas
   genéricas, sem medir essa fração; a variação por inicialização aleatória aparece só no §2, citando
   outros trabalhos (B13.1).
5. **Krishna et al. (2024)** como fonte da regra de sinal da H3: a métrica deles é descritiva, sobre
   explicações locais (B12.5).
6. **Hooker et al. (2021)** como fonte da rejeição da permutação dentro do tempo: o artigo não trata
   de séries temporais (B12.6).
7. **"Saída conformal rearranjada anularia a garantia por cauda"**: para um único par, ordenar
   preserva as garantias; a perda só ocorre na ordenação conjunta entre níveis (B8.9).

## 3. Tabela de auditoria

Colunas: ID · local em `c96db62` · afirmação (trecho) · fonte, versão lida e localizador · trecho
literal da fonte · veredito · correção aplicada (commit). A correção completa em LaTeX é o diff do
commit indicado; a coluna traz o sentido dela.

### 3.1 Previsão financeira e aprendizado profundo

| ID | Local | Afirmação | Fonte · versão · localizador | Trecho literal | V | Correção |
|---|---|---|---|---|---|---|
| B1.1 | T:7 | Fama "consolida a tese de que preços refletem rapidamente a informação pública [...] retornos anormais sustentáveis dependem de informação privada [...]"; "previsibilidade estável da média dos retornos é a exceção, não a regra" | FAMA1991 · JF 46(5), scan · p. 1575, 1577 | "security prices fully reflect all available information"; "Thus, market efficiency per se is not testable."; "the new work says that returns are predictable from past returns, dividend yields, and various term-structure variables"; "the apparent predictability of returns may be spurious, the result of data-dredging and chance sample-specific conditions."; e, na mesma página, a evidência "leans me toward the conclusion that it is real and rational" | N | Reescrito: definição, hipótese conjunta, previsibilidade documentada e risco de mineração (task-02) |
| B1.2 | I:9 | HME: "os preços incorporam rapidamente a informação disponível, tornando a previsão sistemática um desafio" | FAMA1991 · idem · p. 1575 | idem | R | "refletem plenamente" + hipótese conjunta (task-03) |
| B1.3 | T:9 | Lo: "eficiência e ineficiência coexistem [...] sinais [...] contextuais, multivariados e temporalmente localizados" | LO2004 · JPM PDF (MIT) · p. 23–25 | "Market efficiency cannot be evaluated in a vacuum, but is highly context-dependent and dynamic"; "investment strategies will also wax and wane, performing well in certain environments and performing poorly in other environments" | R | Grau de eficiência variável; "multivariados" removido (task-02) |
| B1.4 | I:9 | Lo: "abrindo espaço para modelos que capturem não linearidades e mudanças de regime" | LO2004 · idem · p. 23–24 | idem | R | Modelos não lineares passam a ser motivação deste trabalho, não de Lo (task-03) |
| B1.5 | T:9 (sem `\cite`) | "não estacionariedade de primeira e segunda ordem dos retornos diários e a aglomeração de volatilidade" | CONT2001 (nova) · preprint do autor · §2, fato 6; §3.1 | "Volatility clustering: different measures of volatility display a positive autocorrelation over several days" | R | Aglomeração e caudas pesadas com `\cite{CONT2001}`; não estacionariedade sem fonte sai (task-02) |
| B1.6 | T:11 | Gu et al.: \(R^2\) de 0,4% mensal no melhor modelo; médias históricas perdem para a nula; "em frequência diária, a previsibilidade da média é ainda menor" | GU2020 · NBER WP 25398 rev. set/2019 · §2.8, §3.1, §3.2 | "R2oos is 0.33% for NN1 and peaks at 0.40% for NN3."; "Predicting future excess stock returns with historical averages typically underperforms a naive forecast of zero by a large margin."; "We obtain monthly total individual equity returns from CRSP" | R | Frase diária sem fonte removida; acrescentado o \(R^2\) do índice (task-02) |
| B1.7 | I:11 | "\(R^2\) [...] para retornos de ações líquidas é da ordem de 0,1% a 1%" (GU2020, RAPACH2013) | GU2020 · idem · §1.5, §3.2; RAPACH2013 · WP "Forthcoming in the Handbook" · p. 34, 39 | Gu: "out-of-sample R2's between 1.08% to 1.80% per month" (S&P 500); RZ: "The R2OS statistics for these four forecasts range from 0.44% (POOL-AVG) to 0.93% (sum-of-the-parts)"; "12 of the 14 R2OS statistics are negative" | R | Faixa por horizonte e nível de agregação, com os números de cada fonte (task-03) |
| B1.8 | T:11 | Rapach e Zhou "chegam a magnitudes compatíveis e discutem como pequenos \(R^2\) [...] podem ainda ser economicamente relevantes" | RAPACH2013 · WP · p. 42, 52 | "the monthly R2OS statistics for these four forecasts, while below 1%, still represent excessive stock return predictability [...] making them economically relevant."; "monthly R2OS statistics below 1% can be economically relevant." | S | Acrescentados os números (0,44% a 0,93%) (task-02) |
| B1.9 | T:11, I:11 (sem `\cite`) | "o valor agregável [...] está na escala e na forma da distribuição condicional"; "aglomeração de volatilidade, caudas e forma [...] são mais previsíveis do que seu centro" | CONT2001 · preprint · §2 | valor absoluto e quadrado dos retornos "exhibit significant positive autocorrelation or persistence"; autocorrelação dos retornos "often insignificant" | R | Cont sustenta só "escala mais previsível que a locação"; o "valor" passa a ser hipótese de trabalho declarada (task-02, task-03) |
| B1.10 | M:115 | \(s_f(h)=I_f(h)/\sum_g I_g(h)\) `\cite{GU2020}` | GU2020 · WP · §3.3 | "Variable importances within a model are normalized to sum to one, giving them the interpretation of relative importance for that particular model." | R | "analogamente a" — a normalização por família e horizonte é adaptação (task-03) |
| B1.11 | C:41 | "retornos diários de ativos líquidos têm previsibilidade muito baixa na média" `\cite{GU2020}` | GU2020 · WP · §3.1 | dados mensais (acima) | R | Frequência mensal explícita; diário como inferência (task-03) |
| B2.1 | T:16 | Lim e Zohren: famílias de arquiteturas; papéis "pontual, multi-horizonte, probabilística e multivariada"; flexibilidade com "interações entre covariáveis heterogêneas"; "sensibilidade a *leakage* temporal sutil" | LIMZOHREN2021 · arXiv 2004.13408v2 · §1, §2, §3 p. 7 | "While we focus on univariate forecasting in this survey [...]"; "the flexibility of machine learning methods can be a double-edged sword - making them prone to overfitting"; "machine learning models can be sensitive to how inputs are pre-processed" | R | Usos reais do survey; *leakage* e covariáveis heterogêneas saem da atribuição (task-02) |
| B2.2 | I:13 | AM "passaram a ocupar papel central em previsão financeira, especialmente em cenários multivariados" | LIMZOHREN2021 · idem · §1 | "machine learning has become a vital part of the next generation of time series forecasting models" | R | Séries temporais em geral, multi-horizonte (task-03) |
| B2.3 | T:18, M:57 | Purga e embargo exigidos pela dependência serial; "o embargo corta a dependência serial na fronteira" | LOPEZDEPRADO2018 (livro) não lido; lido LOPEZDEPRADO2018JPM · WP de 27/01/2018 = JPM 44(6) · Solução #8, p. 11–12 | "eliminate from the training set all observations whose labels overlapped in time with those labels included in the testing set. I call this process purging."; "The embargo does not need to affect training observations prior to a test" | R | Purga pela sobreposição do rótulo; embargo do autor é para treino posterior ao teste; aqui é margem conservadora; cita a versão lida (task-02, task-03) |
| B2.4 | T:23 | TFT: estágios (i)–(v) | LIMETAL2021TFT · arXiv 1912.09363v3 · §4, §4.5.1, §4.6 | "Variable selection networks to select relevant input variables at each time step"; "long-term dependencies are captured using a novel interpretable multi-head attention block" | S | — |
| B2.5 | T:25 | Tipos de entrada; alvo e observadas até \(t\), conhecidas até \(t+h\) | LIMETAL2021TFT · idem · §3, Eq. (1) | "observed inputs z [...] which can only be measured at each step and are unknown beforehand, and known inputs x [...] which can be predetermined (e.g. the day-of-week at time t)" | S | Localizador Eq. 1 acrescentado (task-02) |
| B2.6 | T:27 | Artigo original usa {0,1; 0,5; 0,9}; multi-horizonte em um ajuste | LIMETAL2021TFT · idem · §3, §5 | "we use Q = {0.1, 0.5, 0.9} in our experiments"; "we simultaneously output forecasts for τmax time steps" | S | — |
| B2.7 | T:29 (sem `\cite`) | Observadas entram só no codificador, cuja VSN é a mesma para todos os horizontes | LIMETAL2021TFT · idem · §4.2, §4.5.1 | "All static, past and future inputs make use of separate variable selection networks"; "feeding ξ̃_{t−k:t} into the encoder and ξ̃_{t+1:t+τmax} into the decoder" | S | `\cite` com localizador; registrado que o eixo de horizonte está na atenção (task-02) |
| B2.8 | T:31 | Saídas quantílicas lineares, treinadas conjuntamente, sem restrição de não cruzamento | LIMETAL2021TFT · idem · §4.6 Eq. (23), §5 | "Quantile forecasts are generated using linear transformation of the output from the temporal fusion decoder"; "TFT is trained by jointly minimizing the quantile loss" | S | — |
| B2.9 | M:84 | "a função de perda é a soma da *pinball loss* sobre os níveis da grade e sobre os passos" | LIMETAL2021TFT · idem · Eq. (24); `pytorch-forecasting` 1.8.0 `metrics/quantile.py` | Eq. (24): soma sobre quantis e passos dividida por \(M\cdot\tau_{\max}\) | R | "agregada e normalizada", Eq. 24 (task-03) |
| B2.10 | I:13, I:21, A:94 | TFT combina modelagem temporal, seleção de variáveis, quantis nativos e interpretabilidade; "cenários multivariados" | LIMETAL2021TFT · idem · abstract | "TFT uses recurrent layers for local processing and interpretable self-attention layers for long-term dependencies. TFT utilizes specialized components to select relevant features" | R | "multivariados" → "covariáveis heterogêneas" (alvo escalar) (task-03) |
| B2.11 | M:14 | Sentimento por FinBERT | ARACI2019 · arXiv 1908.10063v1 · §1 | "polarity analysis, which is classifying text as positive, negative or neutral" | S | — |
| B11.1 | I:16, T:107, M:49 | *Data snooping* faz o melhor de uma busca parecer significativo; M:49 "elimina a busca em vez de corrigi-la `\cite{...}`" | ROMANOWOLF2005 · WP UPF #712 · §1; WHITE2000 · periódico · p. 1097 | R-W: "If many strategies are evaluated, some are bound to appear superior to the benchmark by chance alone [...] This effect is known as data snooping"; White: "any satisfactory results obtained may simply be due to chance" | S (I:16, T:107); R (M:49) | M:49: as fontes sustentam o problema; eliminar a busca é decisão do trabalho (task-03) |
| B12.7 | M:9 | Duas rodadas, exploratória e confirmatória `\cite{RASCHKA2018}` | RASCHKA2018 · arXiv 1811.12808v3 · §3.3 p. 22; §4.14 p. 45 | "Having a training-validation pair for hyperparameter tuning and model selections allows us to keep the test set 'independent' for model evaluation." | R | Fonte sustenta a separação seleção/avaliação; os termos são do trabalho (task-03) |
| B12.8 | M:86, C:47 | Configurações congeladas `\cite{RASCHKA2018}`; exploratória não é evidência | RASCHKA2018 · idem · §3.3 p. 23 | "use the independent test set to estimate the generalization performance [...] Re-using this test set may result in an overoptimistic bias" | R | Fixadas antes do teste; viés otimista como motivo (task-03) |

### 3.2 Predição quantílica, calibração e rearranjo

| ID | Local | Afirmação | Fonte · versão · localizador | Trecho literal | V | Correção |
|---|---|---|---|---|---|---|
| B3.1 | T:31 | Regressores por nível produzem *crossing* e, "no extremo, uma grade colapsada" `\cite{KOENKER2005,CHERNOZHUKOV2010REARRANGEMENT,BONDELL2010,CANNON2018}` | BONDELL2010 · PMC3371721 · Summary; CANNON2018 · OA Springer · abstract, §3; CFG · arXiv 0704.3649v3 · §2.1; KOENKER2005 · só sumário | Bondell: "Since quantile regression curves are estimated individually, the quantile curves can cross"; Cannon: "These estimates are prone to 'quantile crossing'"; CFG: "the map u ↦ Q̂(u\|x) may not be increasing in u" | R | *Crossing* sustentado; colapso não tratado por nenhuma fonte — declarado como tal (task-02) |
| B3.2 | C:62 | Quantis não cruzantes por construção `\cite{BONDELL2010,CANNON2018}` | Cannon §2.3; Bondell §4.1 | "Non-crossing is imposed by construction."; "by fitting simultaneously, it is guaranteed that they will not cross" | S | — |
| B3.3 | T:34 | Koenker e Bassett introduzem a regressão quantílica; quantis condicionais sem forma paramétrica do erro; minimização da *pinball* | KOENKERBASSETT1978 · scan JSTOR · abstract p. 33, §3 p. 38; KOENKER2005 · excerto CUP · Eq. (1.19) | "a new class of statistics we term 'regression quantiles.'"; "The θth regression quantile [...] is defined as any solution to the minimization problem: min_b [Σ θ\|y_t−x_tb\| + Σ (1−θ)\|y_t−x_tb\|]" | R | "no modelo linear", sistematizada por Koenker 2005 (task-02) |
| B3.4 | I:18 | "arcabouço consolidado para representar incerteza em diferentes faixas de risco" `\cite{KOENKERBASSETT1978}` | KOENKERBASSETT1978 · abstract; KOENKER2005 · §1.1 p. 1 | "These results permit a natural generalization to the linear model of certain well-known robust estimators of location."; "Quantile regression is intended to offer a comprehensive strategy for completing the regression picture." | N | "descrever a distribuição condicional além da média" + KOENKER2005 (task-03) |
| B4.1 | T:41 | Regras estritamente próprias: "minimização em esperança [...] se e somente se" | GNEITING2007 · JASA (cópia UW) · §1 p. 359 | "We take scoring rules to be positively oriented rewards that a forecaster wishes to maximize."; "...with equality if and only if P = Q. A scoring rule with this property is said to be strictly proper." | R | Classe de distribuições e orientação explícitas (task-02) |
| B4.2 | T:41 | Gneiting (2011) "mostra que a *pinball loss* é estritamente consistente" | GNEITING2011 · arXiv 0912.0902v2 · §3.3 Eq. (24) | "which is strictly consistent for the α-quantile relative to the class of the probability measures with finite first moment (Raiffa and Schlaifer 1961, p. 196; Ferguson 1967, p. 51)" | R | "sintetiza o resultado clássico", primeiro momento finito (task-02) |
| B4.3 | T:41 (sem `\cite`) | Cobertura agregada "pode ser otimizada com estratégias degeneradas" | GNEITINGBALABDAOUI2007 (nova) · PDF do autor · §3.3 p. 255, Tabs. 3–4 | "the sharper the better, subject to calibration" (previsor climatológico com cobertura nominal e intervalos mais largos) | R | "não discriminam previsores" + `\cite` (task-02) |
| B4.4 | T:43, A:56 | Representação quantílica do CRPS de Gneiting e Ranjan, Eq. CRPS = 2∫L_α dα | GNEITINGRANJAN2011 · TR 533 (UW, 2008) · §3.1 Eq. (13) | "The equivalence to (13), to which we refer as the quantile decomposition of the score, was noted by Laio and Tamea (2007)." | R | "decomposição apresentada por" (sem reivindicar a origem) (task-02) |
| B4.5 | T:48, T:51 (iii) | "a *pinball* média sobre uma grade finita é uma aproximação por quadratura de CRPS/2; quanto mais densa, melhor" | GNEITINGRANJAN2011 · TR 533 · §3.1 Eq. (17) (α_j = j/J) | "the computation of a suitably discretized approximate version is always feasible, to any degree of accuracy"; "Note that the discrete versions themselves are proper scoring rules." | R | Só com níveis equiespaçados; a grade do trabalho não é, e o texto passa a dizê-lo, alinhado ao ADR 0.0.0009 (task-02) |
| B4.6 | T:69 | "*interval score* de Winkler (1972) [...] próprio `\cite{GNEITING2007}`" | GNEITING2007 · §6.2 Eq. (43) p. 370; WINKLER1972 NV | "This scoring rule has intuitive appeal and can be traced back to Dunsmore (1968), Winkler (1972), and Winkler and Murphy (1979)." | R | "cuja forma remonta a Winkler" (task-02) |
| B4.7 | I:18 | Avaliar só o ponto é insuficiente; calibração e cobertura com regras próprias | GNEITING2007 · §1 p. 359 | "the goal of probabilistic forecasting is to maximize the sharpness of the predictive distributions subject to calibration." | R | Reescrito com calibração e nitidez (task-03) |
| B4.8 | M:96 | Previsor pontual equivale a uma distribuição concentrada | GNEITING2007 · §4.2 p. 367 | "it generalizes the absolute error to which it reduces if F is a deterministic forecast--that is, a point measure." | S | — |
| B5.1 | T:51 | M5 *Uncertainty*: nove quantis, "suficiente para descrever a distribuição" | MAKRIDAKIS2022 · abstract (IDEAS) | "the competition required the prediction of nine different quantiles (0.005, 0.025, 0.165, 0.250, 0.500, 0.750, 0.835, 0.975, and 0.995), that can sufficiently describe the complete distributions of future sales." | S | — (corpo não lido; abstract do editor) |
| B5.2 | T:51 (sem `\cite`) | *Default* de sete níveis da perda da biblioteca | `pytorch-forecasting` 1.8.0 (`uv.lock`) · `metrics/quantile.py:30–31` | `if quantiles is None: quantiles = [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98]` | R | Biblioteca, classe e versão nomeadas (task-02) |
| B5.3 | T:59 | PICP e MPIW `\cite{KHOSRAVI2011}` | KHOSRAVI2011 NV (IEEE fechado); PEARCE2018 (nova) · arXiv 1802.07167v3 · §3.1 Eqs. (6)–(7) | "Let Prediction Interval Coverage Probability (PICP) and Mean Prediction Interval Width (MPIW) be defined as, PICP := c/n, (6) MPIW := (1/n) Σ ŷUi − ŷLi. (7)" | NV → S | `\cite{KHOSRAVI2011,PEARCE2018}` (task-02) |
| B5.4 | T:71 | Wilson preferível ao Wald, "cuja cobertura é errática mesmo em amostras grandes" | WILSON1927 · scan JSTOR · p. 209; BROWN2001 · PDF publicado · p. 102, 103, 107, 110 | Wilson: "(p0−p)² = λ²pq/n, where q=1−p, is quadratic in p and may be solved to find p"; BCD: "The chaotic behavior does not go away even when n is quite large and p is not near the boundaries."; "For larger n (n > 40), the Wilson, the Jeffreys and the Agresti-Coull interval are all very similar"; "Coverage of the Wilson interval fluctuates acceptably near 1 − α, except for p very near 0 or 1." | R | Ressalva de *p* nas fronteiras e equivalência para *n* > 40 (task-02) |
| B5.5 | A:68 | Banda de Wilson: intervalo para proporção binomial `\cite{WILSON1927,BROWN2001}` | WILSON1927 · p. 209; BROWN2001 · §3.1.1 p. 107 | idem B5.4 | S | — |
| B6.1 | T:71 | Para \(h>1\), "as violações [...] compartilham parte do período do alvo"; subséries espaçadas de \(h\) `\cite{DIEBOLDGUNTHERTAY1998}` | DIEBOLDGUNTHERTAY1998 · cópia JSTOR (NYU SOR-98-6) · p. 880–881 | "so long as we make provisions for serial correlation in z, in a fashion [analogous] to the usual MA(h − 1) structure"; "Under the assumption that the z series is (h − 1)-dependent, each of the following h sub-series will be i.i.d. [...] performing h tests, each of size α/h" | R | Mecanismo errado (o alvo é retorno de um dia, sem sobreposição): passa a ser dependência até \(h-1\), com Bonferroni (task-02) |
| B6.2 | M:135 | Subséries de DGT para \(h+7\) `\cite{DIEBOLDGUNTHERTAY1998}` | DIEBOLDGUNTHERTAY1998 · p. 880–881 | idem B6.1 | S | — |
| B6.3 | T:73 | Christoffersen decompõe a razão de verossimilhança em cobertura incondicional (= Kupiec) e independência | CHRISTOFFERSEN1998 NV (sem cópia legível); CHRISTOFFERSENPELLETIER2004 (nova) · CIRANO WP 2003s-05 · §2 p. 2–3; KUPIEC1995 · FEDS 95-24 · Eq. (6) p. 19 | CP: "Christoffersen (1998) tests the null hypothesis that I_t ~ i.i.d. Bernoulli(p) [...] one can combine the two tests in a test of conditional coverage (cc) H0,cc: π01 = π11 = p"; Kupiec: "The maximum likelihood estimate of p is the sample proportion of failures" | NV → S (indireta) | `\cite` de CP 2004 acrescentado (task-02) |
| B6.4 | T:73 | "Com poucas violações a distribuição assintótica χ² [...] é imprecisa" (sem `\cite`); Monte Carlo exato se α(B+1) inteiro `\cite{DUFOUR2006}` | CHRISTOFFERSENPELLETIER2004 · §4.3 p. 8; DUFOUR2006 · CIRANO WP 2005s-02 · Prop. 2.4, Eqs. (2.2), (2.37) | CP: "the scarcity of violations of for example the 1% VaR renders the effective sample size small"; Dufour: "P[p̂_N(S0) ≤ α] ≤ P[p̃_N(S0) ≤ α] = I[α(N+1)]/(N+1)"; "this distribution does not depend on (unknown) nuisance parameters" | R | Fonte para a χ² (Kupiec diz o contrário para outro teste); condição de ausência de parâmetros de incômodo explícita (task-02) |
| B6.5 | T:91, A:118 | Kupiec avalia a proporção; Christoffersen acrescenta a independência | KUPIEC1995 · Eq. (6); CHRISTOFFERSEN1998 NV, descrito por CP2004 · §2 | idem | S | `\cite` de CP 2004 em T:91 (task-02) |
| B6.6 | M:135 | p-valor de Monte Carlo de Christoffersen para \(h+1\) `\cite{DUFOUR2006}` | DUFOUR2006; CP2004 §4.3 | "We thus benefit from the advantage of not having nuisance parameters under the null hypothesis." | S | CP 2004 acrescentado (task-03) |
| B7.1 | T:76–81 | Proposição 4: \(\|\hat Q^*-Q_0\|_p\le\|\hat Q-Q_0\|_p\); estrita sob decrescimento em conjunto de medida positiva | CHERNOZHUKOV2010REARRANGEMENT · manuscrito final (MIT DSpace, = arXiv v2) e arXiv v3 · Prop. 4, §2.1 | "Suppose that Q̂ is an estimator (not necessarily consistent) for some true quantile curve Q0. Then [...] for each x ∈ X, ‖Q̂* − Q0‖p ≤ ‖Q̂ − Q0‖p, p ∈ [1, ∞]"; "The inequality is strict for p ∈ (1, ∞) whenever u ↦ Q̂(u\|x) is strictly decreasing on a subset of U of positive Lebesgue measure, while u ↦ Q0(u\|x) is strictly increasing on U." | R | Norma \(L^p\) em [0,1], para cada valor das covariáveis; numeração confirmada no manuscrito final (task-02) |
| B7.2 | T:81 | "Ordenar os K valores da grade é exatamente esse operador na leitura discreta" | CFG · §2.1 | "it is helpful to think of rearrangement as sorting [...] where {u1, ..., uk} is a sufficiently fine net of equidistant indices in [0, 1]." | R | Caso discreto declarado como derivação (desigualdade de rearranjo), em distância agregada (task-02) |
| B7.3 | T:83 | Rearranjo corrige monotonicidade, não calibração | CFG · Prop. 4 | (enunciado sobre norma; o artigo não trata de cobertura) | S | — |
| B7.5 | C:15, A:64 | Rearranjo "sem afastar a previsão da curva verdadeira" | CHERNOZHUKOV2010REARRANGEMENT · Prop. 4 | idem | S (C:15); R (A:64) | A:64: "sem aumentar a distância \(L^p\) agregada" (task-03) |
| B7.6 | T:91 | "o VaR é um quantil da distribuição de perdas" `\cite{JORION2007,MCNEIL2005}` | JORION2007, MCNEIL2005 NV (livros); ACERBI2002 · arXiv cond-mat/0104295 · Def. 2.2 | "VaR_α = VaR_α(X) = −x^(α) = q_{1−α}(−X) is the value-at-risk at level α of X." | NV → S | Fonte trocada por ACERBI2002 com localizador (task-02) |
| B7.7 | M:92 | EWMA RiskMetrics λ = 0,94, média nula, quantis gaussianos `\cite{RISKMETRICS1996,MCNEIL2005}` | RISKMETRICS1996 · 4ª ed. · §5.3.2 p. 97; §4.6 p. 74; Ap. B.1 | "one for the daily data set (λ = 0.94), and the other for the monthly data set (λ = 0.97)"; "the mean return represented by μi is set to zero"; "the standard RiskMetrics model assumes that returns follow a conditional normal distribution" | S (RiskMetrics); NV (McNeil) | MCNEIL2005 retirado da frase (task-03) |
| B8.1 | T:86 | Conformal: cobertura em amostra finita sob permutabilidade | ROMANO2019CQR · arXiv 1905.03222v1 · Teorema 1 | "If (Xi, Yi), i = 1, ..., n+1 are exchangeable, then the prediction interval C(Xn+1) [...] satisfies P{Yn+1 ∈ C(Xn+1)} ≥ 1−α." | S | — |
| B8.2 | T:86 | CQR com calibração "disjunta de tudo o que ajustou ou selecionou"; Teorema 2 por cauda "ao custo de intervalos ligeiramente mais largos" | ROMANO2019CQR · §1 p. 2, Teorema 2, §6.2 | "We first split the training data into two disjoint subsets, a proper training set and a calibration set."; "adopting the two-tailed, asymmetric conformalization proposed in Theorem 2 causes an increase in average interval length [...] from 1.40 to 1.58" | R | "ligeiramente" → números dos autores (1,40→1,58 com redes neurais; 1,41→1,57 com florestas); exigência sobre seleção como consequência do argumento (task-02, pós-verificação) |
| B8.3 | M:57 | Validade conformal exige conjunto disjunto de tudo o que ajustou ou selecionou | ROMANO2019CQR · §4 p. 5 | "our framework affords broad flexibility in hyper-parameter tuning [...] selected, as usual, by cross validation" | R | "todo o ajuste, inclusive seleção e parada antecipada, fora da calibração" (task-03) |
| B8.4 | T:86, M:105 | Cobertura condicional segue uma Beta conhecida | ANGELOPOULOS2023 · arXiv 2107.07511v6 · §3.2 pp. 13–14, Ap. D | "P(Ytest ∈ C(Xtest) \| {(Xi,Yi)}) ~ Beta(n+1−l, l), where l = ⌊(n+1)α⌋" | R | Parâmetros explícitos; resultado atribuído pelos autores a Vovk, no caso permutável (task-02, pós-verificação) |
| B8.5 | T:88 | NexCP: pesos fixos \(\rho^{n+1-i}\), "cota que depende da magnitude da mudança" | BARBER2023 · arXiv 2202.13415v5 · Eq. (10), Teorema 2 p. 15, §5 p. 22 | "P{Yn+1 ∈ Cn(Xn+1)} ≥ 1−α − Σ_i w̃_i·d_TV(R(Z), R(Z^i))" | R | Forma exata da cota (task-02) |
| B8.6 | M:105 | Massa \((1-\rho)/(1-\rho^{n+1})\) > 0,02 para ρ ≤ 0,98 com n = 252 | BARBER2023 · Eqs. (10)–(11) | quantil de \(\sum_i \tilde w_i\delta_{R_i}+\tilde w_{n+1}\delta_{+\infty}\) | S | — (derivação conferida: ρ = 0,98 → 0,0201; ρ = 0,99 → 0,0109) |
| B8.7 | T:88, M:105 | ACI exige o valor realizado a cada passo | GIBBS2021 · arXiv 2106.00170v3 · §2 p. 3 | "we consider the simple online update α_{t+1} := α_t + γ(α − err_t)." | S | — |
| B8.8 | R:26, C:49 | Não permutabilidade limita a garantia; quebra no teste "não é coberta por nenhuma cota" | BARBER2023 · abstract; §4.4 p. 19 | "if the data distribution drifts over time, then the data points are no longer exchangeable"; "Coverage gap ≤ Σ_{i≤n−k} w̃_i [...] This yields a small coverage gap as long as k is large" | S (R:26); R (C:49) | C:49: a cota existe mas fica vazia (task-03) |
| B8.9 | M:105 | "a saída conformal não é rearranjada, pois isso anularia a garantia por cauda" | sem fonte; ROMANO2019CQR não trata | (derivação: para um par, min/max preserva as garantias unilaterais) | N | Justificativa correta: ordenação conjunta entre níveis troca o nível de cada limite; marcada como derivação (task-03) |

### 3.3 Avaliação fora da amostra e testes

| ID | Local | Afirmação | Fonte · versão · localizador | Trecho literal | V | Correção |
|---|---|---|---|---|---|---|
| B9.1 | T:96 | DM testa igualdade de perda esperada; Eq. DM | DIEBOLDMARIANO1995 · NBER TWP 169 · pp. 2–4 | "The null hypothesis of equal forecast accuracy for two forecasts is E[g(e_it)] = E[g(e_jt)], or E[d_t] = 0" | S | — |
| B9.2 | T:101 | Erros ótimos com dependência até \(h-1\); janela retangular | idem · pp. 4–5 | "optimal k-step-ahead forecast errors are at most (k-1)-dependent [...] This suggests the attractiveness of the uniform, or rectangular, lag window"; "(k-1)-dependence may be violated for a variety of reasons" | R | "no máximo", com a ressalva dos autores (task-02) |
| B9.3 | T:101 | Bartlett "garante variância positiva" | NEWEYWEST1987 · NBER TWP 55 (rev. 1986) · Eq. (5); título | "w(j,m) = 1 − [j/(m+1)]"; "Positive Semi-Definite" | R | "não negativa (semidefinida positiva)" (task-02) |
| B9.4 | T:101, M:103, A:30 | "nesse caso, segue-se a convenção de recalcular com \(h=1\)" | DIEBOLDMARIANO1995 · p. 5; RFORECAST (nova) · `forecast` 8.23.0 `R/DM2.R:93–100` | DM: "in the rare event that a negative estimate arises, we treat it as zero and automatically reject the null hypothesis of equal forecast accuracy"; R: `warning("Variance is negative. Try varestimator = bartlett. Proceeding with horizon h=1.")` | N | Convenção atribuída ao `dm.test`, contrastada com a de DM (task-02, task-03) |
| B9.5 | T:101 | HLN: ajuste da estatística e \(t_{T-1}\) | HARVEY1997 NV (paywall); RFORECAST · `R/DM2.R` | `k <- ((n + 1 - 2*h + (h/n)*(h-1))/n)^(1/2)`; `pt(..., df = n - 1)` | NV | Fator explícito "na forma implementada em `dm.test`" (task-02) |
| B9.6 | T:103, A:114 | Holm controla a FWER | HOLM1979 · JSTOR · p. 65–66 | "the test has a prescribed level of significance protection against error of the first kind for any combination of true hypotheses."; "based on the simple Boole inequality and can be applied to any parametric or non-parametric model" | S | Precisão "sentido forte, qualquer dependência" (task-02) |
| B9.7 | I:18 | DM: "comparações devem respeitar alinhamento temporal e teste apropriado" | DIEBOLDMARIANO1995 · p. 2–3 | "Consider two forecasts, {ŷ_it} and {ŷ_jt}, of the time series {y_t}" | R | "previsões pareadas do mesmo alvo na mesma data" (task-03) |
| B9.8 | R:17, A:30 | Usos repetidos: DM unilateral com janela retangular \(h-1\), HLN, Bartlett como sensibilidade, Holm e MCS `\cite{DIEBOLDMARIANO1995,HARVEY1997,NEWEYWEST1987,HOLM1979,HANSEN2011MCS}` | idem B9.1–B9.6, B10.1 | — | S (herdam) | O unilateral é escolha do trabalho; o recálculo com \(h=1\) em A:30 segue B9.4 (task-03) |
| B9.9 | A:110 | Glossário DM | DIEBOLDMARIANO1995 · p. 2–3 | idem B9.1 | S | — |
| B10.1 | T:105, A:116 | MCS "contém o melhor modelo com confiança \(1-\alpha\)" | HANSEN2011MCS · CREATES RP 2010-76 · Def. 2, Teorema 1 | "lim inf n→∞ P(M* ⊂ M̂*1−α) ≥ 1−α" | R | Modelos superiores, probabilidade assintótica (task-02, task-03) |
| B10.2 | T:105 | *Bootstrap* estacionário `\cite{POLITISROMANO1994}` e bloco automático `\cite{POLITISWHITE2004}` | HANSEN2011MCS · §3.2.1; POLITISROMANO1994 · abstract publicado; POLITISWHITE2004 · versão publicada · §3.2 Eq. (9) p. 58; PATTON2009 (nova) | HLN: "This justifies our use of the moving-block bootstrap"; PR: "The stationary procedure is based on resampling blocks of random length, where the length of each block has a geometric distribution."; PPW: "The correct value for the variance constant DSB [...] is DSB = 2g²(0)" | R | HLN usam blocos móveis; PW 2004 citado com a correção de 2009 (task-02) |
| B10.3 | M:103, M:137 | Estatística \(T_R\); "α = 0,10, o nível reportado por HLN" | HANSEN2011MCS · §3.1, §5, Tab. 4 | "TR,M ≡ max_{i,j∈M} \|t_ij\|"; "We report two statistics from our simulation experiment based on α = 10%"; "M̂*90% and M̂*75%" | S (T_R); R (α) | "nível das simulações; aplicações também a 75%" (task-03) |
| B10.4 | M:103, A:30 | \(\hat b\) de Politis e White | POLITISWHITE2004; PATTON2009; `arch` 8.0.0 `base.py:117–120` | idem | R | `\cite{POLITISWHITE2004,PATTON2009}` (task-03) |
| B10.7 | M:103, A:30 | 1.000 réplicas de *bootstrap* estacionário `\cite{POLITISROMANO1994}` | POLITISROMANO1994 · abstract (corpo NV) | idem | R | Atribuição do método sustentada pelo abstract; 1.000 é parâmetro do trabalho |
| B11.2 | T:110 | Permutação "de um modelo fixo" `\cite{BREIMAN2001}` | BREIMAN2001 · manuscrito 2001 · §10; FISHER2019 · JMLR · §3.1 | Breiman: "the values of the mth variable in the out-of-bag examples are randomly permuted"; Fisher: "we permute inputs to the overall model, rather than permuting the inputs to each individual ensemble member. Thus, our approach can be used generally" | R | Breiman para florestas; generalização de Fisher (task-02) |
| B11.3 | T:110 | Extensão a grupo `\cite{FISHER2019}` | FISHER2019 · §2 | "covariate subsets X1 [...] and X2 [...] may each be multivariate" | S | GREGORUTTI2015 acrescentado (task-02) |
| B11.4 | T:110 | "a exceção é um modelo aditivo com variáveis independentes dentro do grupo" | GREGORUTTI2015 · arXiv 1411.4170v2 · §1, §2.1 Cor. 1 | "Generally speaking, the grouped variable importance does not reduce to the sum of the individual importances"; "If f is additive and if the variables of the group are independent, the grouped variable importance is nothing more than the sum of the individual importances." | R | Função de regressão, perda quadrática (task-02) |
| B11.5 | M:112 | Permutação de grupo `\cite{BREIMAN2001,FISHER2019}` | idem | idem | R | GREGORUTTI2015 acrescentado (task-03) |
| B12.1 | T:110 | Permutação gera combinações "que o modelo nunca viu" | HOOKER2021 · arXiv 1905.03151v2 · abstract | "breaking dependencies between features in hold-out data places undue emphasis on sparse regions of the feature space by forcing the original model to extrapolate to regions where there is little to no data." | R | "pouco ou nenhum dado"; viés para variáveis correlacionadas (task-02) |
| B12.2 | T:112, M:113 | LOCO para grupos `\cite{LEI2018,HOOKER2021}` | LEI2018 · arXiv 1604.04173v2 · §6 p. 32–33; HOOKER2021 · §5 p. 12–13 | Lei: "To investigate the importance of the jth covariate, we refit our estimate"; Hooker: "examine the effect of jointly removing or permuting pairs of features, and then re-learning." | R | LOCO por variável (Lei); extensão a grupos (Hooker) (task-02, task-03) |
| B12.3 | T:112 (sem `\cite`) | Estimandos distintos | HOOKER2021 · §5 p. 12; LEI2018 · §6 | "Using these measures changes the estimand of variable importance." | R | `\cite{HOOKER2021,LEI2018}` (task-02) |
| B12.4 | T:112 | "a concordância entre eles é uma das métricas propostas" `\cite{KRISHNA2024}` | KRISHNA2024 · arXiv 2202.01602v6 (TMLR 06/2024) · §2, §3.2 | "analyzing the disagreements among explanations generated by the aforementioned local post hoc explanation methods"; "we propose six different metrics: feature agreement, rank agreement, sign agreement, [...]" | R | Explicações locais; seis métricas; divergência global via Hooker (task-02) |
| B12.5 | M:115 | Regra de concordância de sinal da H3 `\cite{KRISHNA2024}` | idem · §3.2.1 | "computes the fraction of features that are not only common between the sets of top-k features of two explanations, but also share the same sign" | N | Regra declarada como escolha do trabalho, inspirada em Krishna (task-03) |
| B12.6 | M:112 | "a permutação dentro do tempo é rejeitada" `\cite{HOOKER2021}` | HOOKER2021 · (não trata de tempo) | — | N | Decisão do trabalho, por analogia a Hooker (task-03) |
| B13.1 | T:115 | Pineau et al. "documentam que uma fração significativa [...] permanece difícil de reproduzir mesmo com código aberto, por omissões em [...] sementes" | PINEAU2021REPRODUCIBILITY · JMLR PDF · abstract, §1 p. 2 | "The program contained three components: a code submission policy, a community-wide reproducibility challenge, and the inclusion of the Machine Learning Reproducibility checklist"; "the reasons for this gap are numerous and include: Lack of access to the same training data… Misspecification or under-specification of the model or training procedure; Lack of availability of the code…" | N | Descreve o programa e as causas listadas, inclusive a variação por inicialização do §2 (task-02, pós-verificação) |
| B13.2 | I:23, M:7 | Recomendações de rigor em AM `\cite{PINEAU2021REPRODUCIBILITY,NOSEK2018}` | PINEAU2021REPRODUCIBILITY · abstract; NOSEK2018 · PMC5856500 | Pineau: "designed to improve the standards across the community for how we conduct, communicate, and evaluate machine learning research" | S (M:7); R (I:23) | Nosek separado como pré-registro (não é de AM) (task-03) |
| B13.3 | T:115, M:79 | Bouthillier: amostragem e inicialização; comparar distribuições | BOUTHILLIER2021 · arXiv 2103.03098v1 · abstract, §1, §2 | "variance due to data sampling, parameter initialization and hyperparameter choice impact markedly the results."; "Bootstrapping data stands out as the most important source of variance." | R (T:115); S (M:79) | Hiperparâmetros, fonte dominante, múltiplas execuções (task-02) |
| B13.4 | T:119 | Pré-registro "elimina graus de liberdade [...] p-hacking e seleção adversa de *baselines*"; nova revisão; cegamento | NOSEK2018 · PMC | "Preregistration does not eliminate the possibility of poor statistical practices, but it does make them detectable."; "Jolene can transparently report changes that were made and why."; "An effective preregistration will account for any loss of blinding" | R | "restringe e torna detectáveis"; *baselines* como extensão do trabalho (task-02) |
| B13.5 | M:86 | Pesos da época de menor perda de validação | PRECHELT1998 · preprint do autor · §2.1 | "the result of the training is then the set of weights that exhibited the lowest validation error E_opt(t)." | S | — |
| B14.1 | M:55 | *Walk-forward* de janela expansiva `\cite{TASHMAN2000,HYNDMANATHANASOPOULOS2021}` | HYNDMANATHANASOPOULOS2021 · otexts.com/fpp3 · §5.10; TASHMAN2000 · resumo do editor (corpo NV) | FPP3: "The corresponding training set consists only of observations that occurred prior to the observation that forms the test set."; Tashman: "can be improved by employing rolling-origin evaluations, recalibrating coefficients, and using multiple test periods." | R | Origem rolante (Tashman) e janela expansiva (FPP3) separadas (task-03) |
| B14.2 | M:79 | Múltiplas origens mais robustas que *holdout* `\cite{TASHMAN2000,BERGMEIR2012}` | TASHMAN2000 e BERGMEIR2012 · resumos do editor | Bergmeir: "the use of cross-validation techniques led to a more robust model selection." | R | Tashman para múltiplas origens; Bergmeir para validação cruzada em blocos (task-03) |
| B14.4 | M:86 | "Optuna e amostrador TPE" `\cite{AKIBA2019}` | AKIBA2019 · arXiv 1907.10902v1 · §3.1; BERGSTRA2011 (nova) · NeurIPS 24 · §4 | Akiba: "it can handle various independent sampling methods including TPE"; Bergstra: "Tree-structured Parzen Estimator Approach (TPE)" | R | TPE atribuído a Bergstra et al. (task-03) |
| B15.1 | M:91 | Retorno nulo = passeio aleatório sem *drift* `\cite{CAMPBELL1997}` | CAMPBELL1997 NV (livro) | — | NV | Modelo escrito explicitamente; resultado declarado como derivação elementar (task-03) |
| B15.2 | M:92 | AR(1) com média e variância a \(h\) passos em forma fechada `\cite{HAMILTON1994}` | HAMILTON1994 NV (livro) | — | NV | Fórmulas escritas no texto (conferidas com o doc de domínio de modelagem e o ADR 0.0.0052); gaussiana declarada como suposição do trabalho (task-03) |
| B15.3 | M:92 | Quantis amostrais do tipo 7 | HYNDMANFAN1996 · PDF publicado · p. 363 | "Definition 7. Gumbel (1939) also considered the modal position p_k = modeF(X_(k)) = (k − 1)/(n − 1)." | S | — |
| B15.4 | M:93 | "*Gradient boosting* quantílico `\cite{FRIEDMAN2001}`" | FRIEDMAN2001 · resumo publicado (corpo NV) | "A general gradient descent 'boosting' paradigm is developed for additive expansions based on any fitting criterion."; "Specific algorithms are presented for least-squares, least absolute deviation, and Huber-M loss" | R | Arcabouço genérico; quantílica como perda escolhida, LAD como caso τ = 0,5 (task-03) |
| B15.5 | M:93 | LightGBM | KE2017LIGHTGBM · NeurIPS · p. 1 | "We call our new GBDT implementation with GOSS and EFB LightGBM." | S | — |
| B15.6 | M:52 (sem `\cite`) | Sem escala \(\sqrt h\) para alvo de um dia | — | — | S | Derivação elementar |

### 3.4 Frases sem `\cite` e frases não teóricas

Frases do capítulo de Fundamentação Teórica que não citam fonte foram classificadas assim:

- **Afirmação teórica que exigia fonte:** B1.5, B1.9, B2.7, B4.3, B5.2, B6.4, B12.3 — todas
  receberam fonte ou foram reformuladas (tabela acima).
- **Derivação elementar declarada no texto:** pinball como \(\max(\tau u,(\tau-1)u)\) (T:36); PICP,
  MPIW e cobertura como médias de indicadoras (T:56–68); contagem binomial sob calibração e
  independência (T:71); ordenação discreta como rearranjo (B7.2); massa do ponto de teste no NexCP
  (B8.6); não rearranjo da saída conformal (B8.9); quantil infinito com \(\rho \le 0{,}98\) (M:105);
  ausência de escala \(\sqrt h\) (M:52); retorno nulo sob passeio aleatório (M:91).
- **Argumentação do autor ou descrição do protocolo, sem conteúdo atribuível à literatura:** T:13,
  T:18 (segunda e terceira frases), T:20, T:27 (justificativas), T:29 (consequência para H3), T:31
  (mecanismos adotados), T:39, T:83 (persistência bruto/rearranjado), T:88 (última frase), T:91
  (uso do VaR), T:94, T:101 (última frase), T:103 (regra de H2), T:105 (última frase), T:107
  (governança de coorte), T:112 (última frase), T:117, T:119 (âncora e *hash*) e T:121. Essas
  frases afirmam o que este trabalho faz, não o que a literatura diz.

## 4. Metadados do `.bib`

Todas as 61 entradas citadas foram conferidas contra o DOI (Crossref) ou a página do editor.
Divergências corrigidas no commit `[#169/task-01]`:

| Entrada | Divergência | Correção |
|---|---|---|
| 39 entradas | campo `doi` ausente | DOI acrescentado; `verify_citations.py` → 53/53 `OK` |
| BOUTHILLIER2021 | autores "and others" | 16 autores da página do MLSys |
| KE2017LIGHTGBM | autores "and others" | 8 autores da página do NeurIPS |
| GIBBS2021 | sem volume e páginas | vol. 34, pp. 1660–1672 |
| HOOKER2021 | sem número; "pages = 82" | número 6; "Artigo 82" |
| KOENKER2005 | sem série | Econometric Society Monographs 38 |
| KOENKERBASSETT1978 | "Gilbert Bassett" | "Gilbert Bassett, Jr." |
| PINEAU2021REPRODUCIBILITY | título com dois-pontos; autores já corretos | título do JMLR, com parênteses; URL |
| LIMZOHREN2021 | veículo abreviado | título completo do periódico |
| KRISHNA2024 | sem localizador (TMLR não tem volume) | URL do OpenReview |

Conferidas e sem divergência: as demais entradas citadas. Entradas novas, todas lidas na fonte:
CONT2001, CHRISTOFFERSENPELLETIER2004, PATTON2009, RFORECAST (`forecast` 8.23.0, a versão do
oráculo R do projeto), BERGSTRA2011, GNEITINGBALABDAOUI2007, LOPEZDEPRADO2018JPM, PEARCE2018 e
ACERBI2002 (já existia no `.bib`, sem citação). BERGSTRA2011 e PEARCE2018 não têm DOI: conferidas nas
páginas do NeurIPS e do PMLR e, no caso de Pearce, pelo arXiv. Deixaram de ser citadas JORION2007 e
MCNEIL2005 (inacessíveis; substituídas por ACERBI2002 e RISKMETRICS1996) e LOPEZDEPRADO2018
(livro não lido; substituído pelo artigo do mesmo autor que foi lido).

## 5. Verificação adversarial

Três verificadores independentes (agente `evidence-verifier`, sem contexto da auditoria) receberam
só {afirmação, trecho literal, localizador, fonte} e leram a fonte bruta. Resultado: 18 itens,
13 "sustenta" e 5 "parcial", nenhum "não sustenta". Os parciais viraram correção:

| Item | Achado do verificador | O que mudou |
|---|---|---|
| B8.2 (CQR) | o 1,40 → 1,58 vale só para redes neurais; com florestas aleatórias é 1,41 → 1,57 | texto traz os dois casos |
| B8.4 (Beta) | o resultado é atribuído a Vovk, sem a condição de escores sem empates no §3.2 (o Ap. D trata da cota superior) | condição removida; atribuição a Vovk no caso permutável |
| B11.4 (Gregorutti) | "Generally speaking..." está no §1, não no abstract | localizador corrigido |
| B5.4 (BCD) | o trecho sobre a cobertura do Wilson está na p. 110, não na p. 108 | localizador corrigido |
| B13.1 (Pineau) | o §2 trata de resultados que mudam com a inicialização aleatória, citando outros trabalhos | o texto inclui essa causa |

Ressalvas dos itens "sustenta" que também foram incorporadas: Fama (p. 1577) se inclina a ler a
previsibilidade como "real and rational"; Nosek et al. apresentam o relato de mudanças como prática
recomendada, não como obrigação; DGT apresentam as subséries como extensão em pesquisa futura.

Itens verificados (V1–V3): Proposição 4 de CFG; Teorema 2 e §6.2 da CQR; Beta de Angelopoulos e
Bates; Eqs. (10)–(11) e Teorema 2 de Barber et al.; Corolário 1 de Gregorutti et al.; métricas de
Krishna et al.; convenção de DM com variância negativa (p. 5, conferida nas páginas renderizadas);
subséries e Bonferroni de DGT; Prop. 2.4 de Dufour; trechos de Brown et al.; Teorema 1 e α = 10% de
HLN 2011; correção de Patton et al.; Eq. (17) de Gneiting e Ranjan; Eq. (24) de Gneiting (2011);
Fama (1991, pp. 1575 e 1577, conferido nas páginas renderizadas); Pineau et al.; Nosek et al.;
Hooker et al.

## 6. Fontes não verificáveis e o que foi feito

| Fonte | Motivo | Tratamento |
|---|---|---|
| CHRISTOFFERSEN1998 | IER fechado; nenhuma cópia legível | Descrição confirmada por Christoffersen e Pelletier (2004), citada junto |
| HARVEY1997 | IJF fechado | Fator e graus de liberdade conferidos no `dm.test` e atribuídos à implementação |
| KHOSRAVI2011 | IEEE fechado | Definições de PICP e MPIW citadas também por Pearce et al. (2018) |
| WINKLER1972 | JASA fechado | Atribuição por Gneiting e Raftery (2007, §6.2) |
| POLITISROMANO1994 (corpo) | JASA fechado | Abstract publicado lido; método também descrito por White (2000, p. 1104) |
| TASHMAN2000, BERGMEIR2012 (corpo) | fechados | Afirmações reduzidas ao que os resumos do editor sustentam |
| KOENKER2005 §2.5 | livro | *Crossing* sustentado pelas outras três fontes da mesma citação; KOENKER2005 mantido pelo excerto do cap. 1 (B3.3) |
| FRIEDMAN2001 (corpo) | scan sem texto | Resumo publicado; afirmação reduzida ao arcabouço genérico |
| CAMPBELL1997, HAMILTON1994 | livros | Fórmulas escritas no texto como derivação elementar |
| JORION2007, MCNEIL2005 | livros | Substituídos por ACERBI2002 e RISKMETRICS1996 |

## 7. Achados que afetam documentos de decisão do projeto

O desenho do estudo não muda. Dois documentos de decisão carregam a mesma imprecisão que o texto
carregava e foram registrados como issue própria (§8):

1. **ADR 0.0.0007, regra 2** — "Within-time shuffling is rejected (Hooker, Mentch & Zhou 2021)": a
   fonte não trata de séries temporais; a rejeição é decisão do projeto, por analogia (B12.6).
2. **`docs/domain/modeling/quantile-model-training.md` §2.3** — "a pinball média ρ̄ sobre uma grade
   finita é [...] uma aproximação por quadratura [...] de CRPS/2 — quanto mais densa a grade, melhor"
   contradiz o ADR 0.0.0009 e Gneiting e Ranjan (TR 533, Eq. 17), que exigem níveis equiespaçados
   (B4.5).

Os demais achados já estavam corretos nos docs de domínio: a convenção de DM com variância negativa
(evaluation, l. 725), a correção de Patton, Politis e White (l. 954) e o mecanismo de dependência das
violações para \(h > 1\) (l. 1310–1325).

## 8. Encaminhamentos

- Issue de acompanhamento dos dois achados do §7: [#171](https://github.com/MarceloSanC/financial-forecasting/issues/171).
- Nenhum ADR novo.
