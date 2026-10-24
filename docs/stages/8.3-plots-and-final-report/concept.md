---
title: Concept — Stage 8.3 — Plots canônicos da geração julgada e dossiê final de rastreabilidade
description: Gera, a partir da cópia julgada da 8.1 (judged/<ref>/, lida pelo read_judged_generation da 8.2) e do silver conferido contra o silver_content dela, as dez figuras do catálogo §6.2 do doc de domínio de reprodução (PDF vetorial determinístico, rótulo de estatuto por elemento, nenhum teste novo), um registro de origem por figura (hash do dado plotado + generation_digest + tabela/chave + commit) e o dossiê final de rastreabilidade com todos os itens do §7, pelo use case GenerateReportArtifacts e o subcomando report-artifacts
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; antes de desenhar qualquer gráfico do gold julgado ou escrever o dossiê; ao questionar por que são dez figuras e não cinco, por que o DM é candidato × comparadores, por que a prova de origem é o hash do dado e não o da imagem, ou por que o fan chart usa a seed 1
keywords: [concept, plots, report, dossier, traceability, evaluation, judged-generation, p8-rot, p8-fan, p8-persist, dossie, matplotlib, deterministic-pdf, figure-record, data-digest, silver-content, sandve]
status: draft
created_at: 2026-10-24
updated_at: 2026-10-24
stage_id: 8.3-plots-and-final-report
stage_title: Plots canônicos da geração julgada e dossiê final de rastreabilidade
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [8.2-equivalence-audit]
---

# Concept — Stage 8.3 — Plots canônicos da geração julgada e dossiê final de rastreabilidade

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **A teoria não é reaberta aqui.** O catálogo de gráficos, os rótulos de
> estatuto e o conteúdo mínimo do dossiê são os do
> [doc de domínio](../../domain/evaluation/reproduction-equivalence-and-reporting.md)
> §2.3, §6 e §7 (convenções P8-ROT, P8-FAN, P8-PERSIST e DOSSIE, §9),
> fixados antes de a 8.1 rodar. Este concept só preenche a mecânica. Um
> gráfico não decide nada (doc §6.1 item 5): nenhuma estatística, banda ou
> teste novo nasce nesta Stage.
>
> **Cegamento.** O confirmatório já foi julgado (8.1) e reproduzido (8.2).
> Este concept foi escrito lendo só formas (schemas, chaves, nomes de
> campo), nenhum valor; os valores só aparecem na execução real (A14).

## 1. Escopo

### Dentro do escopo
- **Dez figuras**, uma por linha do catálogo do doc §6.2: reliability
  diagram por τ; quantile score plot; sharpness diagram; PICP × MPIW;
  tabela-heatmap do DM candidato × comparadores; série OOS (fan chart);
  série do diferencial d_t com a ACF; importância por família (H3); pesos
  da VSN; nativo × conformal. Um painel por horizonte (h+1 e h+7), salvo a
  VSN (horizonte-invariante) e H3 (h+1 e h+7 lado a lado para comparar,
  doc §6.1 item 2).
- **Origem:** toda figura sai da cópia julgada
  `judged/aapl_confirmatory-r3-00fd83d9cd39/` (tabelas pelo
  `JudgedGenerationStore.read_judged_generation`; scorecard e
  `run_record.json` pelo `find`), conferida contra o `.judged.toml`
  commitado (`generation_digest` `96c05413…e539`). As duas figuras que
  precisam de dado por ponto (fan chart e sharpness diagram) leem também o
  silver (`fact_oos_predictions`) e o realizado, **conferidos unidade a
  unidade** contra o `silver_content` do manifesto julgado (D4). Nunca
  `current/`, nunca a geração reproduzida, nunca re-treino.
- **Rótulo de estatuto por elemento** (P8-ROT): confirmatório só nos
  elementos da árvore pré-registrada e só nos horizontes em que H1 passa;
  descritivo e exploratório marcados; frases obrigatórias de H3, do
  conformal, da VSN, do PICP × MPIW, do sharpness, do reliability e do fan
  chart (doc §2.3, §6.2).
- **Arquivo de figura**: PDF vetorial (para o `graphicx` do TCC,
  `text/Main.tex` l. 70), bytes iguais em duas gerações no mesmo ambiente,
  paletas amigáveis a daltônicos (D7).
- **Registro de origem por figura** (`<figura>.json` ao lado do PDF):
  `generation_digest`, revisão, partição, fontes (tabela ou documento,
  filtro de chave, campos), unidades do silver usadas com o digest de
  cada uma, **hash do dado plotado** (`data_digest`), commit do gerador e
  identidade do renderizador (D5).
- **Dossiê final de rastreabilidade**
  `docs/reports/final_traceability_dossier.md`, gerado pelo mesmo use case,
  em camadas (veredito → afirmação → identidade → detalhe; Sandve Rule 8),
  com todos os itens da tabela do doc §7 (D8).
- **Registro curado de desvios e achados**
  `docs/reports/dossier_register.toml` (versionado, editado à mão), que
  alimenta as seções do dossiê que não estão em dado persistido: desvios,
  `[finding]`s abertos, computação pré-âncora, ambientes de treino e de
  ablação, resultado da reprodução, ponteiro interno da equivalência (D8).
- Use case `GenerateReportArtifacts`, ports de saída `FigureRenderer` e
  `ReportArtifactSink`, adapter matplotlib, adapter de arquivo, subcomando
  `report-artifacts` e wiring no composition root.
- `matplotlib` como dependência **direta** fixada e contrato import-linter
  que a confina ao adapter de plots (D6).
- **Execução real** sobre a cópia julgada, saídas commitadas em
  `docs/reports/figures/` e no dossiê (A14).

### Fora do escopo (explicitamente)
- Redação do TCC e qualquer edição em `text/` (incluir as figuras no LaTeX
  é da redação; o TCC referencia os caminhos de `docs/reports/figures/`).
- Dashboards interativos e figuras HTML.
- Qualquer métrica, banda, p-valor ou teste que o gold julgado não tenha
  persistido (doc §6.1 item 5): DM comparador × comparador, ACF recalculada
  (o `plot_acf` do statsmodels recalcula — não é usado), banda de Wilson
  recalculada, CWC.
- Gráficos exploratórios extras (doc §8.2 deixa para o technical; esta
  Stage não cria nenhum — o catálogo basta para o texto).
- Qualquer gráfico ou número comparado com a evidência anterior (P-EDIT;
  doc §9 item 2). O dossiê só aponta, em seção interna, o
  `equivalence_audit.md` e o registro de hashes.
- Reprodução entre ambientes, re-julgamento, mudança no veredito ou no
  pré-registro.
- Rule 10 de Sandve (publicar dados e scripts): aspiração, decisão do
  humano (doc §7).

### Vínculo com o roadmap
Fecha o Step 8 ("a evidência final está produzida, reproduzível e auditada —
pronta para o TCC", roadmap §Step 8): a 8.1 julgou, a 8.2 provou a
reprodução bit a bit (claim (a), [`reproduction_audit.md`](../../reports/reproduction_audit.md)),
e a 8.3 entrega o insumo do texto — as figuras e o dossiê que liga cada
afirmação ao número e cada número ao modo como foi produzido (overview §4,
"artefatos de decisão reconstruíveis a partir de dados persistidos sem
re-treino"). O bloco da 8.3 no roadmap é emendado por este concept (D1,
D2, D11; contratos e arquivos).

## 2. Objetivo da Stage

Ao fechar, existe no repositório, gerado por código testado a partir da
cópia julgada `aapl_confirmatory-r3-00fd83d9cd39` sem re-treino, o conjunto
de dez figuras do catálogo §6.2 em PDF determinístico, cada uma com o seu
registro de origem pelo hash do dado, e o dossiê final de rastreabilidade
com todos os itens do doc §7 — de modo que qualquer figura ou afirmação do
TCC se reconstrói, a partir do dado persistido, pelo caminho que o dossiê
aponta.

## 3. Contexto e premissas

### Contexto
- **A geração julgada.** A 8.1 selou `judged/aapl_confirmatory-r3-00fd83d9cd39/`
  na partição `AAPL/aapl_confirmatory-r0-665f45d9169a`: 19 tabelas gold +
  `MANIFEST.json` em `generation/`, o scorecard
  (`gold_model_comparison_confirmatory_scorecard.json`), o `run_record.json`
  e o `CONTENTS.sha256`; `generation_digest`
  `96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539`,
  commit `060537fc`, tag `confirmatory-run/aapl_confirmatory-r3-00fd83d9cd39`
  ([`aapl_confirmatory-r3.judged.toml`](../../../config/preregistration/aapl_confirmatory-r3.judged.toml)).
  O `silver_content.digest` é `7ac4c759…` e o `result_digest` da tentativa,
  `7c7940d4…` (concept 8.2 §3).
- **O leitor.** A 8.2 acrescentou `JudgedGenerationStore.read_judged_generation`
  (ADR 8.2.0002 item 4), que confere o `CONTENTS.sha256` e devolve a cópia
  como `GoldGeneration`; o docstring do port já o declara "o leitor da
  reprodução (8.2) e dos gráficos da 8.3, que nunca leem `current/`".
  O `find` devolve, além do manifesto, os documentos (scorecard e
  `run_record.json`).
- **O que o gold tem e o que não tem.** Formas lidas em
  `application/dtos/gold_schema.py` e nos builders: calibração por
  (modelo, seed, horizonte, amostra, tipo, níveis, degenerados, banda) com
  `wilson_lower`/`wilson_upper`; `gold_metrics_by_run` com `pinball` por
  nível, `picp` e `mpiw` por par; `gold_dm_results` com `p_value` bruto,
  `adjusted_p_value` e `rejected` por (horizonte, estimador, candidato,
  comparador); `gold_loss_differentials` (d_t por `target_timestamp`) e
  `gold_differential_acf`; `gold_h3_importance`/`_shares`/`_reading`/`_vsn`;
  `gold_conformal_coverage`. O scorecard traz o gate H1, o poder declarado
  (`PowerProfile`) e o perfil. **Não** há no gold quantis por ponto nem
  larguras por ponto: o fan chart e o sharpness diagram (box plot das
  larguras) só existem a partir do silver, o que o doc §6.1 item 1 admite
  ("ou do dado persistido de onde ela foi construída (predições e realizado
  do silver, identificados pelo hash de conteúdo — §4.5)").
- **Lição da 8.2.** O andaime da equivalência recusou o silver vivo porque o
  "esperado" tomava **todas** as unidades `fact_oos_predictions|…` do
  `silver_content`, inclusive as 600 dos runs da ablação que ele não lia
  (technical 8.2 §7, `[finding]` E4 passo 1). A conferência da 8.3 compara
  só as unidades dos runs que lê (D4).
- **Notas herdadas que o dossiê lista.** Da 8.1: erratas O1 (a corrida rodou
  em `060537fc`, filho do `GATE2` `d3b49909`; `code.src`/`code.uv_lock`
  iguais) e O2 (2 linhas de 1 tentativa), F1 (cobertura); entre `060537fc` e
  o HEAD, `src/` mudou só por formatação do ruff e um trecho de docstring
  (`code.src` difere; concept 8.2 §3). Da 8.2: decisão humana B3 (ADR
  8.2.0004, A1 pela precisão efetiva float32) e o `[deviation]` B3; o
  `[finding]` do PICP 80 % do candidato (lado do nominal divergente do
  anterior, não explicado, não bloqueia — interno); erratas F2–F5.
- **TCC.** `text/Main.tex` carrega `graphicx` (l. 70); o template guarda
  imagem ao lado do capítulo (`text/3_Revisao_Teorica/10anos_campus_site.jpg`).

### Premissas
- A cópia julgada e o silver vivo seguem íntegros (a 8.2 conferiu
  `LIVE_INTACT` e o silver byte a byte igual ao backup de entrada da 8.1).
  Se não estiverem, o use case recusa (§6) e a restauração é pelo backup
  conferido por `sha256sum -c` (ADR 8.1.0003 item 7).
- A imagem Docker de dev atual tem `matplotlib` 3.11.0 (o `uv.lock` já trava
  3.11.0, hoje transitivo via `mlflow`); declarar a dependência direta não
  muda a versão travada.
- As colunas que as figuras leem por nome existem nas tabelas gravadas (são
  colunas dos builders; só faltam no `read_columns` do schema — D3).

### Dependências
- `8.2-equivalence-audit` (`done`): `read_judged_generation`; o
  `reproduction_audit.md` (claim (a)) e o `equivalence_audit.md` (interno)
  que o dossiê aponta.
- `8.1-confirmatory-run` (`done`): cópia julgada, `.judged.toml`,
  `ATTEMPTS.jsonl` (`result_digest`), `run_record.json`, `SilverContent` no
  manifesto e o `SilverContentAccumulator` (dono único do digest por unidade).
- `6.5`/`6.6`/`7.2`/`7.3` (`done`): o scorecard, as tabelas de perfil,
  conformais e de H3 que as figuras desenham.

## 4. Contratos

### Introduzidos
- **`GenerateReportArtifacts`** (use case,
  `application/use_cases/generate_report_artifacts.py`)
  ```python
  class GenerateReportArtifacts:
      def __init__(
          self, *, judged_store: JudgedGenerationStore,
          preregistration_source: PreregistrationSource,
          silver_reader: SilverTableReader, grid_reader: TrainingGridReader,
          hasher: Hasher, environment: EvaluationEnvironment,
          renderer: FigureRenderer, sink: ReportArtifactSink,
      ) -> None: ...
      def __call__(self, command: GenerateReportArtifactsCommand) -> ReportArtifactsResult: ...
  ```
  Ordem: (1) snapshot do ambiente (sujo → recusa); `judged_records` → o
  registro da referência pedida; `find` → `generation_digest` igual ao do
  registro, senão recusa; (2) `read_judged_generation`; (3) leituras do
  silver e do realizado com conferência por unidade (D4); (4) monta as dez
  `FigureSpec` e o `TraceabilityDossier` (puros); (5) só então renderiza e
  escreve — nenhum byte é escrito se qualquer passo de (1)–(4) falhar.
- **`GenerateReportArtifactsCommand`**, **`ReportArtifactsResult`**,
  **`FigureSpec`** (+ `PanelSpec`, `SeriesSpec`, `ElementLabel`),
  **`FigureRecord`** (+ `SourceRef`), **`TraceabilityDossier`**
  (+ `DossierEntry`) e o erro **`SilverContentMismatchError`** — em
  `application/dtos/report_artifacts.py` (DTOs frozen).
  `FigureSpec` é o **dado plotado**, sem tipo de biblioteca: id da figura,
  título, painéis (horizonte ou "horizonte-invariante"), séries (pontos,
  faixas, caixas, células, hastes) com rótulo de estatuto por elemento,
  legendas e frases obrigatórias. `FigureRecord.data_digest` = sha256 da
  serialização canônica da `FigureSpec` (dono único:
  `FigureSpec.canonical_bytes()`). O comando leva a partição, a referência,
  o nome do plano e as entradas do registro curado já parseadas
  (`tuple[DossierEntry, ...]`).
- **`FigureRenderer`** (port-out, `application/ports/out/figure_renderer.py`)
  ```python
  class FigureRenderer(Protocol):
      def render(self, figure: FigureSpec) -> bytes: ...   # PDF, determinístico
      def identity(self) -> Mapping[str, str]: ...         # ex.: {"matplotlib": "3.11.0", "format": "pdf"}
  ```
  Real: `MatplotlibFigureRenderer` (`adapters/out/plots/`); fake:
  `InMemoryFigureRenderer` (bytes = serialização da spec).
- **`ReportArtifactSink`** (port-out, `application/ports/out/report_artifact_sink.py`)
  ```python
  class ReportArtifactSink(Protocol):
      def write(
          self, *, figures: Sequence[tuple[str, bytes, FigureRecord]],
          dossier: TraceabilityDossier,
      ) -> None: ...
  ```
  Uma chamada com tudo (tudo ou nada, I9). Real: `FilesystemReportSink`
  (`adapters/out/reports/`), que grava `figures/<id>.pdf`,
  `figures/<id>.json` (registro, `sort_keys`, LF) e renderiza o dossiê em
  Markdown, num staging trocado no fim; fake: `InMemoryReportSink`.
- **Subcomando `report-artifacts`** (`adapters/in/cli/evaluation_commands.py`
  + `cli.py` + `composition_root.py`): `--preregistration-ref`,
  `--output` (padrão `docs/reports`), `--register` (padrão
  `docs/reports/dossier_register.toml`); parseia o registro curado na
  fronteira (adapter in) e chama o use case; só leitura sobre `data/`.
- **`docs/reports/dossier_register.toml`** — entradas
  `[[entry]] kind ∈ {deviation, finding, pre_anchor, environment, reproduction, internal}`,
  `title`, `summary`, `pointer` (caminho/âncora de technical §7, ADR, relatório).
- Artefatos: `docs/reports/figures/<id>.pdf` + `<id>.json` (10 pares) e
  `docs/reports/final_traceability_dossier.md`.

### Consumidos
- **`JudgedGenerationStore.find` e `.read_judged_generation`** — 8.1/8.2
  (ADRs 8.1.0003, 8.2.0002 item 4).
- **`PreregistrationSource.read` e `.judged_records`** — 6.5/8.1 (cadeia
  r0–r3 com âncoras, `blind_status`, `blinding_statement`, seeds; registro
  de atestação).
- **`SilverTableReader.read`/`.columns`** — 6.4/8.1 (`dim_run` e
  `fact_oos_predictions` do cohort).
- **`TrainingGridReader`** — 6.4 (realizado na grade do cohort).
- **`SilverContentAccumulator`** + **`Hasher`** — 8.1 (digest por unidade,
  dono único; ADR 8.1.0002).
- **`EvaluationEnvironment.snapshot`** e **`DirtyCodeError`** — 8.1 (commit
  e sujeira do gerador, imagem).
- **`GoldGeneration`, `GoldTableSchema` e os `col_*`** — 6.4/6.5 (leitura
  das tabelas por nome).
- **Scorecard** (`ScorecardResult.as_mapping()` gravado) — 6.5/6.6/8.1.

## 5. Invariantes e regras

- **I1 — Uma fonte, verificada.** Toda tabela vem da cópia julgada lida pelo
  `read_judged_generation`; o `generation_digest` do `find` é igual ao do
  `.judged.toml` commitado. Nenhum caminho do use case chama
  `GoldGenerationReader.read_generation` (`current/`).
- **I2 — Silver por unidade.** O conjunto de unidades lidas
  (`dim_run|<cohort>`, `fact_oos_predictions|<run_id>|<ano>` dos runs lidos,
  `realized|AAPL`) tem digest igual ao do `silver_content` julgado,
  unidade a unidade; para cada run lido, as chaves `<tabela>|<run_id>|*`
  lidas são exatamente as julgadas. Unidades julgadas de runs não lidos
  (ablação) não entram no esperado (lição da 8.2).
- **I3 — Nenhum teste novo.** As figuras só selecionam, reordenam e aplicam
  as transformações que o doc prescreve para a figura: média entre seeds
  (B-SEEDS, doc §6.1 item 4), largura u − l por ponto, quantis/caixa das
  larguras (sharpness, GBR 2007 §3.3). Bandas, p-valores, decisões, ACF e
  poder vêm persistidos (gold ou scorecard). Um elemento sem fonte
  persistida **não é desenhado** e o registro lista a omissão. O módulo de
  montagem não importa serviço inferencial do domínio (DM, Holm, MCS,
  Wilson, gate H1, potência, ACF, CUSUM).
- **I4 — Confirmatório só onde a árvore se aplica.** Os elementos
  confirmatórios (caudas 0,1/0,9 do candidato na variante do gate, banda
  97,5 %, poder; linha do DM com p bruto e Holm) têm os valores **lidos do
  scorecard** (o que foi julgado) e o rótulo confirmatório **só** nos
  horizontes com H1 aprovado no scorecard; onde H1 reprova, a linha do DM é
  "descritivo (perfil) — H2 não aplicável".
- **I5 — Por horizonte.** Nenhuma série ou número mistura horizontes.
- **I6 — Fan chart com a seed pré-declarada.** A seed é a primeira de
  `[seeds].tft_quantile` da revisão julgada (r3: `[1, …, 10]` → **seed 1**;
  a mesma lista do `config/cohorts/aapl_confirmatory.toml`), com a legenda
  "seed 1, ilustrativa; as métricas usam a média entre seeds"; nunca média
  dos quantis entre seeds. Os quantis desenhados são os da grade que o gold
  pontua (`value_guardrail`, montada pelo mesmo dono do refresh).
- **I7 — Prova de origem é o dado.** O registro de cada figura carrega
  `data_digest`, `generation_digest`, fontes e commit; o sha256 do PDF, se
  presente, é informativo ("identifica o arquivo nesta geração; não é prova
  de origem").
- **I8 — Determinismo.** Mesmo dado, mesmo commit e mesma imagem → bytes
  idênticos de todos os PDFs, registros e do dossiê. Nada de instante,
  host ou caminho absoluto em nenhum artefato (proveniência excluída, doc
  §2.2); data de criação do PDF removida.
- **I9 — Tudo ou nada.** Falha antes da escrita → nada escrito; a escrita
  troca o staging inteiro de uma vez.
- **I10 — Gerador limpo.** `code_dirty = "true"` no snapshot → recusa: uma
  figura commitada precisa de commit que a reproduza (Sandve Rule 4).
- **I11 — Rótulos e frases obrigatórias** (doc §2.3, §6.2): conformal
  "cobertura empírica (não garantida)" em todo painel; H3 em linguagem
  estritamente descritiva; VSN "horizonte-invariante"; PICP × MPIW "o
  gráfico não ordena modelos — mais estreito só é melhor com cobertura
  igual"; sharpness "sharpness só tem sentido sujeito à calibração";
  reliability com aviso de banda anti-conservadora em h+7 e sob
  agrupamento; fan chart com a legenda do I6.

## 6. Casos de erro e exceções

| Situação | Comportamento |
|---|---|
| Referência sem `.judged.toml` ou sem cópia (`JudgedGenerationNotFoundError`) | erro, nada escrito |
| `generation_digest` do `find` ≠ do `.judged.toml`, ou cópia adulterada (`JudgedGenerationTamperedError`) | erro, nada escrito |
| Unidade do silver/realizado com digest diferente, faltando ou a mais para um run lido | `SilverContentMismatchError` com as chaves (sem valores), nada escrito |
| Scorecard ausente na cópia (geração `BLOCKED`) | erro: sem veredito não há figura confirmatória nem dossiê |
| Coluna lida ausente/tipo errado | erro de leitura do `col_*` (já existente), nada escrito |
| Árvore do gerador suja | `DirtyCodeError` (reuso do 8.1), nada escrito |
| Registro curado malformado (kind fora da lista, campo faltando) | erro no CLI antes do use case |
| Falha de escrita no meio | staging removido; saída anterior intacta |

## 7. Decisões técnicas relevantes

Formato dos registros: skill `evidence-resolution` (E = evidência decide;
C = convenção, degrau indicado). Nenhuma decisão P restou: a única com
cara de preferência (conteúdo da declaração de cegamento) já foi decidida
pelo humano e está ancorada (D9).

### D1 — Catálogo inteiro (10 figuras), roadmap emendado
- **O quê:** a Stage gera as dez figuras do doc §6.2, não os cinco arquivos
  do roadmap (`calibration_plot`, `dm_matrix_plot`, `picp_mpiw_plot`,
  `oos_series_plot`, `contribution_plot`). Os cinco faltantes (quantile
  score, sharpness, d_t + ACF, VSN, nativo × conformal) são todos
  declarados no pré-registro (perfil, H3, conformal) e o doc os fixou para a
  8.3; o roadmap é anterior ao gate de domínio do Step 8.
- **Fonte:** doc §6.2 e §9 itens 14–17 (aceito no gate do Step 8, issue
  #208, depois do roadmap); hierarquia de fontes: doc de domínio do gate >
  descrição humana do roadmap escrita antes dele.
- `[decision:E] D1 — Escolha: as dez do §6.2 · Alternativas: só as cinco do roadmap · Base: doc §6.2 (catálogo com estatuto por linha); doc §2.3 (todo número do Step 8 tem estatuto) · Reversível: sim`
- **ADR:** [`8.3.0001`](../../adr/8_3_0001-full-figure-catalog-and-dm-candidate-versus-comparators.md)

### D2 — DM como tabela-heatmap candidato × comparadores
- **O quê:** a figura do DM é uma grade horizonte × comparador da família,
  célula colorida pelo p bruto (estimador primário retangular) e anotada
  com p bruto e a decisão de Holm; sem células comparador × comparador. O
  arquivo `dm_matrix_plot.py` do roadmap some.
- `[decision:E] D2 — Escolha: candidato × comparadores · Alternativas: matriz comparador × comparador · Base: doc §6.2 linha do DM ("Células comparador × comparador não existem: o gold não persiste esses DMs, e calculá-los seria teste novo"); doc §9 item 15; ADR 6.5.0006 (estimador primário) · Reversível: sim`
- **ADR:** [`8.3.0001`](../../adr/8_3_0001-full-figure-catalog-and-dm-candidate-versus-comparators.md)

### D3 — Leitura pelo schema do gold, com `read_columns` ampliado
- **O quê:** as figuras leem as tabelas pelos `col_*` e pelo
  `GoldTableSchema`; as colunas novas lidas por nome (ex.: `p_value` do DM,
  `wilson_lower`/`wilson_upper` da calibração) entram no `read_columns` do
  schema, dono único ("nenhuma outra coluna é lida por nome fora deste
  schema" — docstring de `gold_schema.py`).
- `[decision:C] D3 — Degrau 1 (convenção do próprio código, ADR 6.5.0005 itens 2-3) · Reversível: sim`

### D4 — Silver das duas figuras por ponto, conferido por unidade
- **O quê:** fan chart e sharpness diagram leem `dim_run` e
  `fact_oos_predictions` do cohort pelo `SilverTableReader` (com o mesmo
  pós-filtro do refresh: `asset` e `run_id` do cohort) e o realizado pelo
  `TrainingGridReader`; recalculam o digest de cada unidade lida pelo
  `SilverContentAccumulator` (dono único) e exigem igualdade com o
  `silver_content` julgado só para as unidades dos runs lidos (I2).
  Sharpness do candidato: larguras de todas as seeds empilhadas (réplicas,
  B-SEEDS; a média da distribuição empilhada é o MPIW médio entre seeds que
  o perfil reporta), legenda declara o empilhamento.
- `[decision:C] D4 — Escolha: silver conferido contra o silver_content julgado · Alternativas: só gold (fan chart e sharpness impossíveis); silver sem conferência · Degrau 1: doc §6.1 item 1 (silver "identificados pelo hash de conteúdo — §4.5"); Sandve 2013 Rule 7 · Reversível: sim`
- **ADR:** [`8.3.0002`](../../adr/8_3_0002-figure-provenance-by-data-digest-and-verified-silver-units.md)

### D5 — Prova de origem pelo hash do dado, registro por figura
- **O quê:** `<id>.json` por figura com `data_digest` (sha256 da
  `FigureSpec` canônica), `generation_digest`, revisão, partição, fontes
  (`SourceRef`: tabela ou documento, filtro de chave, campos), unidades do
  silver com digest, commit do gerador e `renderer.identity()`. O hash da
  imagem não é prova: os bytes mudam com matplotlib/FreeType mesmo com o
  dado igual.
- `[decision:E] D5 — Escolha: hash do dado + generation_digest + fontes + commit · Alternativas: hash do PDF (baseline de imagem) · Base: Sandve 2013 Rule 7 ("note which data formed the basis of a given plot and how this data could be reconstructed"); pytest-mpl (imagem muda com versão de matplotlib/FreeType — issue #234 §Referências) · Reversível: sim`
- **ADR:** [`8.3.0002`](../../adr/8_3_0002-figure-provenance-by-data-digest-and-verified-silver-units.md)

### D6 — matplotlib direto, API orientada a objeto, confinado ao adapter
- **O quê:** `matplotlib>=3.11,<3.12` em `dependencies` (pin por minor, o
  lock trava 3.11.0 — postura de todos os blocos do `pyproject.toml`);
  contrato import-linter `evaluation-no-matplotlib-leak` (matplotlib só em
  `features/evaluation/adapters/out/plots/`); o adapter usa
  `matplotlib.figure.Figure` com backend PDF e `rc_context`, sem `pyplot`
  nem estado global. Hoje matplotlib só chega transitivo via mlflow e
  nenhum código o importa — depender de transitiva é frágil.
- `[decision:E] D6 — Base: issue #234 §Síntese ([E] dependência direta); pyproject.toml (convenção de pin e de gate de vazamento por lib) · Reversível: sim`
- **ADR:** [`8.3.0003`](../../adr/8_3_0003-deterministic-vector-pdf-with-matplotlib-in-docs-reports-figures.md)

### D7 — PDF vetorial determinístico, paleta para daltônicos, figuras em `docs/reports/figures/`
- **O quê:** (a) só PDF (vetorial para o `graphicx`); (b) `savefig(...,
  format="pdf", metadata={"CreationDate": None})` explícito (não
  `SOURCE_DATE_EPOCH`, que é estado global do processo); sem SVG/PNG, então
  `svg.hashsalt` e `Software` do PNG não se aplicam; (c) heatmap e escalas
  sequenciais em `cividis` (alternativa `viridis`); séries com um mapa
  **fixo** modelo → cor de ciclo amigável a daltônicos, validado pelo
  `validate_palette.js` da skill `dataviz` no technical, identidade nunca
  só por cor (legenda + marcador/estilo de linha), um eixo y por painel;
  (d) rótulos em português (o TCC é em PT); (e) as figuras são versionadas
  em `docs/reports/figures/`, ao lado do dossiê e dos relatórios da 8.2,
  e o TCC referencia esse caminho; `text/` não é tocado (redação fora).
- `[decision:C] D7(a,c) — Degrau 3: guia "Choosing Colormaps" do matplotlib e Nuñez, Anderton & Renslow 2018 (cividis) — issue #234 §Referências · Reversível: sim`
- `[decision:E] D7(b) — Base: código-fonte do matplotlib 3.11.0 (backend_pdf: CreationDate None omite a data; SOURCE_DATE_EPOCH como alternativa) e especificação SOURCE_DATE_EPOCH rev. 1.1 — issue #234 §Referências · Reversível: sim`
- `[decision:C] D7(e) — Degrau 1: roadmap 8.2/8.3 (relatórios gerados em docs/reports/); fronteira "redação do TCC fora" (roadmap 8.3 non_goals) · Reversível: sim, barato (mover arquivos e ajustar o caminho no registro)`
- **ADR:** [`8.3.0003`](../../adr/8_3_0003-deterministic-vector-pdf-with-matplotlib-in-docs-reports-figures.md)

### D8 — Dossiê gerado pelo use case + registro curado versionado
- **O quê:** o dossiê é renderizado pelo mesmo use case, a partir das fontes
  persistidas (cópia julgada, cadeia do pré-registro, `.judged.toml`,
  `ATTEMPTS.jsonl`, `dim_run`, registros das figuras), sem transcrição de
  hash à mão. O que não está em dado persistido vem do
  `dossier_register.toml` (kinds do §4), editado à mão e versionado, com
  ponteiro para a fonte (technical §7, ADR, relatório). Camadas: (1)
  veredito e afirmações com ponteiro (tabela/documento, chave, campo) —
  H1 por horizonte com o poder declarado, H2 por horizonte, vencedor
  primário, critério "≥ 1 horizonte", leitura de H3, benchmark conformal;
  (2) identidade da entrada; (3) cadeia do pré-registro e cegamento; (4)
  geração julgada; (5) ambiente, commits e seeds; (6) figuras; (7)
  reprodução; (8) desvios e achados; (9) interno, fora do texto.
- `[decision:C] D8 — Escolha: gerado + registro curado · Alternativas: dossiê escrito à mão a partir de saídas de comando (precedente reproduction_audit.md); tudo gerado sem registro (desvios embutidos em código) · Degrau 3: Sandve 2013 Rules 1, 5, 8, 9 (registro sem transcrição, camadas, ponteiro); doc §7 (DOSSIE) · Reversível: sim`
- **ADR:** [`8.3.0004`](../../adr/8_3_0004-dossier-generated-from-persisted-sources-plus-curated-register.md)

### D9 — Declaração de cegamento é transcrição
- **O quê:** o dossiê transcreve literalmente o `blinding_statement` da
  revisão julgada (r3; o mesmo texto em r0–r3) e o `blind_status` de cada
  emenda, mais a ressalva do ADR 6.5.0003 item 4 ("no statement is made
  about computations before it") e o registro da computação pré-âncora da
  6.4 (ADR 6.5.0010 P1). O conteúdo foi decidido pelo humano (nota de
  2026-09-30 no ADR 6.5.0010) e está ancorado no hash da revisão: não é
  pergunta.
- **Fonte:** ADR 6.5.0010 (nota da Task 13); `config/preregistration/aapl_confirmatory-r3.toml` chave `blinding_statement`.

### D10 — Testar o dado plotado e um smoke de geração, não pixels
- **O quê:** testes unitários por figura comparam a `FigureSpec` montada
  contra o gold/scorecard falso (seleção, chave, rótulo, omissões); o
  contrato do `FigureRenderer` prova bytes iguais em duas chamadas, `%PDF`
  e ausência de `CreationDate`; o smoke de integração renderiza as dez
  figuras com dados sintéticos. Sem comparação de imagem.
- `[decision:C] D10 — Degrau 1: skill pytest-with-fakes; issue #234 §Síntese ([C] dado + smoke); pytest-mpl (baseline de imagem frágil entre versões) · Reversível: sim`

### D11 — Camada e ponto de entrada
- **O quê:** camada multi (application + adapters/out + adapters/in/cli +
  docs), não "adapters/out + docs": a montagem do dado plotado é pura e
  testável com fakes (application), o desenho e a escrita são adapters, e
  a execução real precisa de subcomando. O registro curado é parseado no
  CLI (fronteira) e entra no comando como DTO — sem port novo de leitura.
- **Fonte:** LAYOUT §3; precedentes 8.1/8.2 (`evaluate`, `audit-reproduction`).

### D12 — Teste da solução mais direta
- O registro por figura e a conferência do silver **reusam** os donos
  existentes (`SilverContentAccumulator`, `generation_digest`,
  `.judged.toml`, `EvaluationEnvironment`); nenhuma identidade nova é
  inventada. A conferência por unidade fica no `evaluation` porque o dono do
  `silver_content` é o `evaluation` (ADR 8.1.0002); não é concern de outro
  slice capturado aqui.

## 8. Integrações

### Internas (com outras Stages/módulos)
- `evaluation` (8.1/8.2): store julgado, source do pré-registro, ambiente,
  acumulador do silver, schema do gold.
- `analytics_store` (silver) e `modeling` (grade de treino), pelos ports do
  consumidor já existentes (`SilverTableReader`, `TrainingGridReader`) —
  nenhuma aresta nova entre slices.

### Externas
- `matplotlib` 3.11.x (backend PDF), só no adapter de plots.
- Sistema de arquivos: `data/` (só leitura) e `docs/reports/` (escrita, com
  staging).

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| PDF não determinístico (fonte embutida, ordem de objetos) mesmo com `CreationDate None` | B | M | contrato do renderer (A9) e A14 (duas gerações reais, listagem sha256 igual); falhando, fixar fonte e `rcParams` no `rc_context` |
| Esperado do silver incluir unidades não lidas (ablação) — repete o `[finding]` da 8.2 | M | M | I2 + teste com unidades de ablação no julgado (passa) e unidade do cohort adulterada (falha) |
| Valor confirmatório recalculado em vez de lido do scorecard | M | A | I3/I4 + teste de importação (A6) + teste que confronta o elemento com o campo do scorecard |
| Coluna nova no `read_columns` quebrar leitores existentes | B | M | `make check` completo; colunas já gravadas pelos builders |
| Memória ao ler o silver inteiro do cohort | M | B | o refresh já lê o mesmo volume em `--memory 8g`; ler por `feature_set_name` como o refresh |
| Registro curado esquecer um desvio | M | M | A12 lista fechada dos itens herdados (§3) verificada por teste |
| Dossiê ou figura citar número da evidência anterior | B | A | P-EDIT: seção interna só com ponteiros; nenhuma figura lê `tests/equivalence` nem `data/analytics` (import-linter `src-no-tests` já existe) |
| Figura com mais estatutos do que rótulos | M | M | `ElementLabel` obrigatório em toda série (construção do DTO recusa série sem rótulo) |

## 11. Critérios de aceitação

- [ ] **A1 — Catálogo.** O use case produz exatamente dez `FigureSpec`, uma
  por linha do doc §6.2, com um painel por horizonte (VSN com um painel
  "horizonte-invariante"; H3 com h+1 e h+7 lado a lado); a do DM só tem
  células (horizonte, comparador da família) — teste unitário com fakes.
- [ ] **A2 — Fonte única.** Com o fake em que `current/` difere da cópia
  julgada, toda `FigureSpec` sai da cópia; o use case nunca chama
  `read_generation` — teste unitário.
- [ ] **A3 — Cópia conferida.** `generation_digest` ≠ `.judged.toml`, cópia
  adulterada ou ausente → erro e o sink falso não recebe nenhuma escrita.
- [ ] **A4 — Silver por unidade.** Unidade do cohort alterada, faltando ou a
  mais (e realizado alterado) → `SilverContentMismatchError` sem escrita;
  unidades de ablação presentes só no julgado → passa.
- [ ] **A5 — Rótulos.** Com scorecard falso em que H1 passa em h+1 e reprova
  em h+7: elementos confirmatórios só em h+1, linha do DM de h+7
  "descritivo (perfil) — H2 não aplicável"; as frases obrigatórias do I11
  presentes nas figuras certas — teste unitário.
- [ ] **A6 — Nenhum teste novo.** Teste de importação: o módulo de montagem
  não importa `diebold_mariano`, `holm_correction`, `model_confidence_set`,
  `wilson_band`, `h1_gate`, `h1_gate_power`, `differential_stationarity`;
  os elementos confirmatórios igualam os campos do scorecard falso; elemento
  sem fonte persistida é omitido e listado no registro.
- [ ] **A7 — Dado plotado.** Para cada uma das dez figuras, teste unitário
  confronta as séries da `FigureSpec` com os valores fixados no gold/silver
  falso (chave e campo certos, média entre seeds onde o doc manda).
- [ ] **A8 — Fan chart.** Usa só a seed 1 (primeira de `[seeds].tft_quantile`
  da revisão julgada), quantis `value_guardrail` dos pares simétricos,
  cortes de fold marcados e a legenda do I6; com a seed 1 removida do silver
  falso, erro (não cai em outra seed nem em média).
- [ ] **A9 — Renderer determinístico.** Contrato do `FigureRenderer` (fake e
  real): a mesma `FigureSpec` → bytes idênticos em duas chamadas; real começa
  com `%PDF` e não contém `/CreationDate`.
- [ ] **A10 — Smoke de geração.** As dez `FigureSpec` sintéticas renderizam
  pelo adapter real sem erro, uma página cada — teste de integração.
- [ ] **A11 — Registro por figura.** Cada `<id>.json` tem `data_digest` igual
  ao sha256 de `FigureSpec.canonical_bytes()`, `generation_digest`, revisão,
  partição, fontes, unidades do silver (fan chart e sharpness), commit e
  identidade do renderizador; mudar um valor do gold falso muda o
  `data_digest`.
- [ ] **A12 — Dossiê completo.** O dossiê renderizado tem uma seção por
  linha da tabela do doc §7 (lista fechada no teste), o `blinding_statement`
  transcrito byte a byte da revisão julgada, o poder declarado ao lado de
  cada claim de H1, um ponteiro (tabela/documento, chave, campo) por
  afirmação do veredito (H1×2, H2×2, vencedor, sucesso, H3, conformal) e, do
  registro curado, no mínimo: B3/ADR 8.2.0004, o `[finding]` do PICP da 8.2
  (seção interna), as erratas O1/O2 da 8.1 e F2–F5 da 8.2, a nota do
  `code.src` (formatação) e o ponteiro do `reproduction_audit.md` com
  `generation_digest` e `result_digest`.
- [ ] **A13 — Recusas do CLI e do gerador.** Árvore suja → `DirtyCodeError`
  sem escrita; registro curado malformado → erro antes do use case; falha
  de escrita no meio → staging removido, saída anterior intacta.
- [ ] **A14 — Execução real.** `report-artifacts --preregistration-ref
  aapl_confirmatory-r3-00fd83d9cd39` no ambiente Docker, sobre a cópia
  julgada (`96c05413…e539`): dez PDFs + dez registros em
  `docs/reports/figures/` e o dossiê, commitados; uma segunda geração no
  mesmo commit e imagem dá listagem `sha256sum` idêntica de todos os
  artefatos; listagem sha256 de `data/` (gold e silver da partição) igual
  antes e depois (só leitura).
- [ ] **A15 — Dependência e gates.** `matplotlib>=3.11,<3.12` em
  `dependencies`; contrato import-linter que confina matplotlib ao adapter
  de plots, com prova de quebra; `make check` verde.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4.
- [x] Toda decisão em §7 tem fonte rastreável? — D1–D12 com âncora.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)? — matplotlib só atrás do `FigureRenderer`; arquivo atrás do `ReportArtifactSink`.
- [x] Decisões com alternativa real descartada têm ADR escrito? — 8.3.0001–8.3.0004.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 8.2 `done` (roadmap, Histórico 2026-10-24).
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)? — estimativa 12–13 (DTOs/ports/fakes; montagem por grupo de figuras; conferência do silver; dossiê; renderer; sink; CLI/wiring; dependência e contrato; execução real); a contagem é referência, não gate.
- [x] Riscos críticos têm mitigação plausível? — §10.
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — a identidade/fingerprint do dado não é reinventada: a conferência reusa o `SilverContentAccumulator` e o `silver_content` do manifesto (dono único no `evaluation`, ADR 8.1.0002), e a prova da cópia reusa `generation_digest` + `.judged.toml`; o registro por figura só agrega esses identificadores com o hash do dado plotado (D12).
- [x] Nenhuma figura introduz teste, banda ou p-valor que o gold não persistiu? — I3, A6.

## 13. Questões em aberto

Nenhuma crítica. Ficam para o technical (doc §8.2): o mapa exato figura →
(tabela/documento, filtro, campo), inclusive qual linha do scorecard carrega
cada banda e o poder; o nome de arquivo de cada figura; o estilo
(tamanho, fonte, `rcParams`) dentro do D7; a forma do Markdown do dossiê
dentro das camadas do D8.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §4 (reprodutibilidade sem re-treino), §2
- [`../../roadmap.md`](../../roadmap.md) — Stage `8.3-plots-and-final-report` (bloco emendado por este concept), 8.1, 8.2
- [Doc de domínio de reprodução, equivalência e relatório](../../domain/evaluation/reproduction-equivalence-and-reporting.md) — §2.2, §2.3, §6, §7, §8.2–§8.3, §9 itens 14–18
- [Doc de domínio de avaliação](../../domain/evaluation/probabilistic-forecast-evaluation.md) — §3.1, §4.1–§4.4, §4.6, §6.9, §8.7
- [Doc de domínio de inferência](../../domain/inference/conformal-benchmark-and-feature-attribution.md) — §4.11, §5.3, §5.8
- ADRs: 6.5.0003, 6.5.0005, 6.5.0006, 6.5.0010, 8.1.0002, 8.1.0003, 8.1.0004, 8.2.0002, 8.2.0004; desta Stage: [`../../adr/`](../../adr/) prefixo `8_3_`
- Concepts e technical §7 da [8.1](../8.1-confirmatory-run/technical.md) e da [8.2](../8.2-equivalence-audit/technical.md)
- Issue [#234](https://github.com/MarceloSanC/financial-forecasting/issues/234) — §Referências pesquisadas
- Sandve, Nekrutenko, Taylor & Hovig (2013), "Ten Simple Rules for Reproducible Computational Research", PLOS Comput. Biol. 9(10): e1003285
- Nuñez, Anderton & Renslow (2018), "Optimizing colormaps with consideration for color vision deficiency…", PLOS ONE 13(7): e0199239
