---
title: Technical — Stage 8.3 — Plots canônicos da geração julgada e dossiê final de rastreabilidade
description: Plano de execução da Stage 8.3 em 15 Tasks inside-out (1 Task = 1 commit) — matplotlib direto confinado ao adapter de plots, DTOs do dado plotado e do registro por figura, read_columns ampliado, ports e fakes do renderer e do sink, leitura do silver conferida por unidade, montagem pura das dez figuras em três grupos, dossiê citável e interno, use case GenerateReportArtifacts, renderer matplotlib determinístico, sink com staging, parser do registro curado e subcomando report-artifacts, e2e sintético e o registro curado — e a Etapa real R0–R4 (geração sobre a cópia julgada 96c05413…, saídas commitadas, segunda geração com sha256sum idêntico, data/ intacto)
when-use: Consultar durante a Fase 4 (execução) da Stage 8.3; cada Task tem arquivos (lista fechada), testes a escrever primeiro, critério de aceite do concept que cobre e verificação; a Etapa R traz o runbook da geração real com a tabela "Se falhar"
keywords: [technical, plano de execução, plots, report, dossier, traceability, evaluation, judged-generation, matplotlib, deterministic-pdf, figure-record, data-digest, silver-content, report-artifacts, p8-rot]
status: done
created_at: 2026-10-24
updated_at: 2026-10-24
stage_id: 8.3-plots-and-final-report
stage_title: Plots canônicos da geração julgada e dossiê final de rastreabilidade
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [8.2-equivalence-audit]
concept_ref: ./concept.md
issue_id: 234
branch: feat/234-8-3-plots-and-final-report
tasks_count: 15
---

# Technical — Stage 8.3 — Plots canônicos da geração julgada e dossiê final de rastreabilidade

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01 (decisões de forma fixadas aqui, comandos no
>    container, plano de gates).
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de arquivos de
>    cada Task é **fechada**: tocar arquivo fora dela = parar e triar (RUNBOOK Passo 8,
>    "Escopo estrito"). `__init__.py` marcados *(pacote)* não contam na contagem de
>    arquivos (PIPELINE §4.3 item 2).
> 3. Escrever primeiro os testes de "Testes primeiro" (vermelho), depois o código
>    (verde). **T1 verde antes de todo commit**; `make check` só nos pontos do
>    [plano de gates](#plano-de-gates)
>    ([RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)).
> 4. Commit: `<type>(<escopo>): <descrição> [8.3/task-NN]` (Etapa: `[8.3/--]`), body
>    em bullets, `Refs #234`, subject ≤ 100 caracteres, mensagem UTF-8 sem BOM por
>    `git -C <worktree> commit -F <arquivo>` ([`CONVENTIONS.md`](../../CONVENTIONS.md) §4).
> 5. Algo não previsto em §1–§6, no concept ou nos ADRs 8.3.0001–0004 → pausar, triar
>    (skill `evidence-resolution`: E/C decide e registra, ADR `8_3_0005+` se houver
>    alternativa real; só P sobe ao humano) e registrar em §7.
> 6. Depois da Task 15, da auditoria de testes e do 1º `make check`: **Etapa R**
>    (R0 → R4), 2º `make check` (saída), §3 e `stage 8.3: complete`.
>
> **Stage = 1 branch:** `feat/234-8-3-plots-and-final-report`, worktree própria.
>
> **Dado.** Nenhuma Task lê `data/`. Todo teste usa dado sintético (`tmp_path` ou
> fakes). A única leitura da cópia julgada real é a da Etapa R, só leitura.

## 1. Contexto e estratégia de execução

### Resumo

Um use case puro de orquestração (`GenerateReportArtifacts`) lê a cópia julgada
(`read_judged_generation`, conferida contra o `.judged.toml`), o scorecard e o
`run_record.json` da cópia, a cadeia do pré-registro e o silver do cohort (conferido
unidade a unidade contra o `silver_content` julgado); monta, por funções puras, as dez
`FigureSpec` do catálogo §6.2 (o dado plotado, sem tipo de biblioteca), um
`FigureRecord` por figura (`data_digest` = sha256 da `FigureSpec` canônica) e o
`TraceabilityDossier` (citável + interno); só então chama o `FigureRenderer`
(matplotlib, PDF determinístico) e uma única escrita do `ReportArtifactSink` (arquivos
com staging). O subcomando `report-artifacts` parseia o registro curado
`docs/reports/dossier_register.toml` na fronteira. A Etapa R roda a geração real sobre
`judged/aapl_confirmatory-r3-00fd83d9cd39/`, commita as saídas e prova o determinismo
por uma segunda geração.

### Estratégia (ordem e porquê)

TDD inside-out (skill `task-ordering-hex`), em quatro blocos de código e um real:

1. **Fundação (Tasks 01–04).** Dependência + contrato import-linter + guarda AST (a
   fronteira existe antes de qualquer import de matplotlib) → DTOs e catálogo fechado
   (o vocabulário de tudo o que vem depois) → `read_columns` ampliado (as colunas que
   as figuras leem por nome) → ports e fakes do renderer e do sink.
2. **Montagem pura (Tasks 05–09).** Leitura do silver conferida por unidade → figuras
   do grupo calibração/cobertura → figuras do grupo inferência/atribuição (com o teste
   AST do A6) → figuras do silver (sharpness e fan chart) → dossiê e o seu Markdown.
   Tudo testado com fakes, sem I/O.
3. **Orquestração (Task 10).** Use case com fakes: ordem, recusas, tudo ou nada.
4. **Adapters e entrada (Tasks 11–15).** Renderer matplotlib + contrato
   (subprocessos) + smoke → sink + contrato → parser do registro + subcomando +
   composition root → e2e sintético pela CLI → o registro curado real + teste do
   arquivo.
5. **Auditoria de testes com mutação real, Checkpoint C final e 1º `make check`** →
   **Etapa R** → **2º `make check`** (saída).

Todo o código antes da Etapa R: os artefatos commitados identificam o gerador por
`code.src`/`code.uv_lock`; uma correção de `src/` depois da geração real muda o
`code.src` e obriga a regenerar e recommitar. Lição da 8.1/8.2 (§7 delas): **fix
depois de um gate exige revisão independente do fix e novo `make check` antes da
etapa real** (linha `FAIL_SRC_CHANGED_SINCE_GATE1` da Etapa R).

**Contagem.** 15 Tasks, acima da faixa 3–12 do CONVENTIONS §6. A contagem é
referência, não gate (decisão do humano registrada para o processo); o concept já
estimava 12–13. Cada Task cumpre os 5 critérios da PIPELINE §4.3; nenhuma foi partida
só para caber em arquivos, e nenhuma fusão reduziria trabalho sem misturar port com
adapter ou concerns distintos.

### Decisões de forma fixadas aqui (o concept §4/§13 e os ADRs deixaram para a Fase 3B)

Todas `[decision:C]` de forma (degrau 1: convenção do próprio código ou precedente
8.1/8.2), dentro do que os ADRs 8.3.0001–0004 decidem; nenhuma pede ADR novo.

- **Arquivos.**
  - `application/dtos/report_artifacts.py` — DTOs, catálogo fechado, erros;
  - `application/ports/out/figure_renderer.py`, `application/ports/out/report_artifact_sink.py`;
  - `application/use_cases/report_silver.py` — leitura do silver/realizado com o
    pós-filtro do refresh e a conferência por unidade (I2);
  - `application/use_cases/report_figures.py` — **o módulo de montagem** (A6): as dez
    funções `*_figure(...) -> FigureSpec`, puras;
  - `application/use_cases/report_dossier.py` — montagem do `TraceabilityDossier`;
  - `application/use_cases/dossier_markdown.py` — **dono único** do Markdown dos dois
    dossiês (o sink real e os testes chamam a mesma função; o fake não a duplica —
    `check_fake_parity`);
  - `application/use_cases/judged_copy.py` — extração da conferência "registro
    commitado ↔ cópia selada" e do `result_digest` da última `input_read`, hoje
    privados do `AuditReproduction` (dono único; o `AuditReproduction` passa a chamar,
    sem mudar comportamento). As funções **não** erguem erro de chamador (CB-5: o
    `ReproductionAuditError` mora no módulo que importará `judged_copy` → import
    circular): `sealed_matching_record(...) -> JudgedGeneration | None` devolve `None`
    sem registro commitado (erguem `JudgedGenerationNotFoundError`/`…TamperedError`, que
    são do port) e `last_input_read_digest(attempts, ref) -> str | None`; cada use case
    ergue o seu (`ReproductionAuditError` / `ReportArtifactsError`);
  - `application/use_cases/generate_report_artifacts.py` — o use case;
  - `adapters/out/plots/matplotlib_figure_renderer.py` (`plots/__init__.py` não importa
    matplotlib); `adapters/out/reports/filesystem_report_sink.py`;
  - `adapters/in/cli/dossier_register.py` — parser TOML do registro curado (stdlib
    `tomllib`) → `tuple[DossierEntry, ...]`;
  - `adapters/in/cli/evaluation_commands.py` — `report_artifacts(...)`.
- **Ids e arquivos das figuras** (concept §13; ordem do catálogo §6.2, que é a ordem
  de `FIGURE_CATALOG`, das saídas e do dossiê): `reliability_diagram`,
  `quantile_score_plot`, `sharpness_diagram`, `picp_mpiw_plot`,
  `dm_candidate_vs_comparators`, `oos_fan_chart`, `loss_differential_acf`,
  `h3_family_importance`, `vsn_weights`, `native_vs_conformal` →
  `docs/reports/figures/<id>.pdf` + `<id>.json`.
- **`FigureSpec`** (frozen; construção valida e recusa): `figure_id` (do catálogo),
  `title`, `panels: tuple[PanelSpec, ...]`, `notes: tuple[str, ...]` (frases
  obrigatórias + legendas fixas), `omissions: tuple[str, ...]`. `PanelSpec`:
  `panel_id`, `scope: PanelScope` (`horizon` | `horizon_invariant` |
  `horizon_comparison`), `horizon: int | None` (obrigatório só em `horizon`), `title`,
  `x_label`, `y_label`, `series: tuple[SeriesSpec, ...]` (não vazio),
  `label: ElementLabel` (rótulo do painel). `SeriesSpec`: `series_id`,
  `kind: SeriesKind` (`line`, `points`, `band`, `interval`, `boxes`, `cells`, `stems`,
  `bars`, `vlines`, `reference`), `name` (legenda), `model: str | None`,
  `label: ElementLabel` (**obrigatório**: série sem rótulo não constrói — risco
  "figura com mais estatutos do que rótulos"), `x: tuple[float | str, ...]`,
  `y: tuple[float | None, ...]`, `low`/`high: tuple[float | None, ...] | None`
  (faixas, intervalos, caixas — mesmo comprimento de `x`), `text: tuple[str, ...] |
  None` (anotação de célula). Números finitos ou `None` (NaN/±inf recusados).
  `ElementLabel`: `status: StatusLabel` + `note: str | None`. `StatusLabel(StrEnum)`
  com os valores literais do P8-ROT em PT: `confirmatório`, `descritivo (perfil)`,
  `descritivo`, `descritivo (perfil) — H2 não aplicável`. Nenhum `exploratório` (I3:
  nenhum gráfico exploratório nesta Stage; o valor não existe no enum).
- **`FigureSpec.canonical_bytes()`** (dono único do dado plotado):
  `json.dumps(self.as_mapping(), sort_keys=True, ensure_ascii=False,
  separators=(",", ":"), allow_nan=False).encode("utf-8")`; floats pelo `repr` do
  `json` (exato, determinístico); `data_digest = hashlib.sha256(canonical_bytes()).hexdigest()`
  (propriedade da spec). O `Hasher` do projeto **não** é usado aqui: ele arredonda
  floats (contrato do port), e o digest do dado plotado tem de mudar com qualquer bit.
- **`FIGURE_CATALOG`** (`Mapping[str, FigureCatalogEntry]`, `MappingProxyType`, na
  ordem do §6.2): por figura, `omissions` (a coluna "Omissões declaradas" do D13,
  **literal**: o teste A16 compara com a lista literal do concept) e `required_notes`
  (as frases do I11/§6.2). `FigureSpec.__post_init__` exige `omissions ==
  FIGURE_CATALOG[id].omissions` e `required_notes ⊆ notes` — omissão fora da lista ou
  frase faltando não constrói. Textos fixos:
  - conformal: `cobertura empírica (não garantida)` (em **todo** painel: `note` do
    `ElementLabel` de cada painel e `notes`);
  - H3: `linguagem estritamente descritiva: a família f responde por uma parcela maior
    da perda evitada em h+7 do que em h+1; nunca "f causa"`;
  - VSN: `horizonte-invariante`;
  - PICP × MPIW: `o gráfico não ordena modelos — mais estreito só é melhor com
    cobertura igual`;
  - sharpness: `sharpness só tem sentido sujeito à calibração`;
  - reliability: `banda binomial anti-conservadora em h+7 e sob agrupamento`;
  - fan chart: `seed {s}, ilustrativa; as métricas usam a média entre seeds` (com a
    seed resolvida, I6).
- **`FigureRecord`** (frozen; `as_mapping()` → `<id>.json` pelos bytes do
  `document_bytes` de `dtos/judged_generation.py` — dono único dos documentos JSON:
  `sort_keys`, `indent=2`, LF final): `figure_id`, `data_digest`,
  `generation_digest`, `preregistration_ref`, `revision`, `partition`
  (`{"asset", "parent_sweep_id"}`), `sources: tuple[SourceRef, ...]`
  (`SourceRef`: `kind` ∈ {`gold_table`, `document`, `silver_table`, `realized`},
  `name`, `filter: Mapping[str, str|int|float|bool|None]`, `fields: tuple[str, ...]`),
  `silver_units: Mapping[str, str]` (vazio fora do fan chart e do sharpness),
  `excluded_degenerate: Mapping[str, int]` (chave `<modelo>|<seed>|h<h>|<τ_l>-<τ_u>` →
  pontos degenerados fora pela máscara do MPIW; só no sharpness, vazio nas demais —
  D4 "vai para a legenda e o registro", CB-8), `omissions`, `code: {"code.src", "code.uv_lock"}`, `renderer: Mapping[str, str]`.
  **Sem** commit HEAD, instante, host, caminho absoluto e sem sha256 do PDF (I7 deixa
  opcional; omitido para o registro só mudar com dado, código ou renderizador). A
  construção recusa chave com `commit`/`time`/`at` e valor com `/` absoluto.
- **`DossierEntry`** (frozen): `kind ∈ {deviation, finding, pre_anchor, environment,
  reproduction, internal}`, `title`, `summary`, `pointer` (caminho relativo ao repo
  com âncora opcional `#…`), `status: str | None` (obrigatório `"open"` em `finding`;
  ausente nos demais). **Primeira barreira do A17 na construção** (dono único,
  aplica-se a todo produtor, inclusive o parser): entrada não-`internal` cujo
  `pointer` case com `docs/stages/8.2-*` (exceto as âncoras citáveis declaradas em
  `CITABLE_82_ANCHORS`: as entradas `[deviation]` "E2 item 7" e "`env-equal`" e os
  `[measurement]` "E2"/"E3" do technical 8.2 §7, por âncora exata),
  `docs/reports/equivalence_audit.md`, `docs/reports/prior_evidence_registry.toml`,
  `docs/adr/8_2_0003*`, `docs/adr/8_2_0004*` ou `tests/equivalence/` →
  `ValueError`. Comparação sem caixa, `_`/`-` iguais.
- **Refinamento do A17 (2ª barreira; CB-2).** O A17 lista `equivalence_audit` entre os
  termos proibidos no texto citável, com `_` ≡ `-`; lido ao pé da letra, o termo casa
  o diretório `docs/stages/8.2-equivalence-audit/`, que as âncoras citáveis exigidas
  pelo próprio A12/A17 (E2 item 7, `env-equal`, `[measurement]` E2/E3) têm de apontar —
  os dois critérios se contradiriam. O termo efetivo é o **relatório**:
  `equivalence[_-]audit\.md` (e `equivalence_audit` fora de um caminho
  `8.2-equivalence-audit/`); os demais termos ficam como no A17. Uma única constante
  `CITABLE_FORBIDDEN_PATTERNS` (regex, `re.IGNORECASE`) em `dtos/report_artifacts.py`
  é usada pelo teste da Task 09, pelo e2e da Task 14 e **executada** pela R2 no
  container (`find_forbidden`), nunca copiada como regex. Não muda o objetivo do critério (nada da evidência anterior no
  citável); registrado aqui porque o concept está `done`.
- **`TraceabilityDossier`** (frozen): `sections: tuple[DossierSection, ...]`;
  `DossierSection`: `section_id`, `title`, `visibility` (`citable` | `internal`),
  `blocks: tuple[DossierBlock, ...]`; `DossierBlock`: `heading`, `rows:
  tuple[tuple[str, str], ...]` (campo → valor) e `pointer: str | None`. As seções
  citáveis são **exatamente** `CITABLE_SECTIONS` (uma por linha da tabela do doc §7
  menos a última — lista fechada no DTO; o teste A12 compara com a lista literal) e a
  interna é uma: `internal`.
- **Comando e resultado.** `GenerateReportArtifactsCommand`: `name`, `revision`,
  `preregistration_ref`, `cohort_seeds: tuple[int, ...]` (lista `seeds` do arquivo de
  cohort, lida no CLI — I6) e `register: tuple[DossierEntry, ...]`. A **partição não
  vem no comando**: sai do plano resolvido (`refresh_command_from(plan, ref).partition`,
  precedente `AuditReproduction`), que é mais forte que um argumento (refinamento do
  concept §4, que dizia "o comando leva a partição"; ver §6 "Verificação de gap").
  `ReportArtifactsResult`: `preregistration_ref`, `generation_digest`,
  `figures: tuple[tuple[str, str], ...]` (id, `data_digest`), `register_entries: int`.
- **Validação da escrita** (dono único, CB-4): `check_artifacts(figures, dossier)` em
  `dtos/report_artifacts.py` (ids únicos e todos os dez do catálogo, bytes começando por
  `%PDF`, registro com o mesmo id) — chamada pelo fake e pelo sink real antes de
  qualquer escrita; o contrato `[fake, real]` da Task 12 a exercita nas duas pernas.
- **Erros** (em `dtos/report_artifacts.py`, `ApplicationError`):
  `ReportArtifactsError` (registro commitado da ref ausente, scorecard ausente na
  cópia, nenhuma `input_read` da ref); `SilverContentMismatchError` (concept §4; só
  chaves de unidade na mensagem, nunca valores); `ReportSourceMismatchError` (DM gold ≠
  scorecard, `n_evaluated` ≠ `n_observed`, média das larguras ≠ `mpiw`, seeds do cohort
  ≠ revisão, seed sem predições, linha esperada ausente; mensagem com chaves, sem
  valores). Árvore suja reusa `DirtyCodeError` (8.1).
- **Filtro do gate** (D13 "constantes do dono único, não reescritas"): `sample =
  GATE_SAMPLE` (importado de `domain/value_objects/scorecard_evidence.py`),
  `includes_degenerate = False`, `dgt_offset = None` — os dois últimos são literais
  dentro de `scorecard_evidence._tail`, sem constante nomeada; tocar o código que
  produziu a geração julgada para nomeá-los não se paga. O módulo de montagem declara
  os dois e **amarra ao dono em tempo de execução**. A seleção usa a **chave completa**
  da linha de calibração do `_tail` (`model`, `sample`, `kind`, `level_low`,
  `level_high = None`, `includes_degenerate`, `dgt_offset = None`, `dgt_step = None`,
  `band_level`; CB-11) e recusa (`ReportSourceMismatchError`) se casar zero ou mais de
  uma entrada/linha por seed. Para cada horizonte, a entrada de
  `profile.horizons[h].calibration_95` do candidato com essa chave, nas caudas do gate
  (`h1_gate.lower_level`/`upper_level`), tem `mean_observed` igual a
  `verdict.horizons[h].h1.mean_observed`; diferente → `ReportSourceMismatchError`
  (filtro divergente do gate seria detectado no fake e no dado real).
- **Silver das figuras por ponto pelo dono do refresh.** As larguras do sharpness
  saem de `CoverageMetrics.interval_widths(series, tolerance=..., pair=...)`
  (`domain/services/coverage_metrics.py`, docstring "Insumo do sharpness diagram"),
  sobre as `CoverageSeries` `full` do `SeriesAssembly.assemble(...)` com os mesmos
  `horizons`, `window_deficits` e `required_models` do `refresh_command_from(plan,
  ref)` e a tolerância `h1_gate.degeneracy_tolerance` da revisão. A média desenhada
  `math.fsum(widths) / len(widths)` é a mesma conta do `_pair_coverage` (MPIW do
  gold): igualdade **exata** com `gold_metrics_by_run` `model_full`/`mpiw` exigida. O
  fan chart usa `series.scored_values(i)` (grade rearranjada, `value_guardrail`) e
  `series.realized[i]` da série `full` do candidato, seed resolvida; contagem de
  degenerados = `len(série) − len(widths)`. Nenhum desses serviços está na lista do
  A6 (não são inferenciais).
- **Leitura do silver** (`report_silver.py`): `dim_run` com `filters={"asset",
  "parent_sweep_id"}` e o pós-filtro de igualdade; `fact_oos_predictions` por
  `feature_set_name` do cohort com `filters={"asset", "feature_set_name"}`, mantendo
  as linhas com `run_id` do cohort (todas as linhas, **todos os splits**); realizado
  pelo `TrainingGridReader` (`timestamps_iso()` + coluna `target_return`), fingerprint
  igual ao `dataset_fingerprint` do plano. Os digests são recalculados por um
  `SilverContentAccumulator` novo (dono único). **O pós-filtro não é extraído do
  `RefreshGold`** (código da geração julgada; refatorá-lo por causa de uma figura não
  se paga): a duplicação é de ~20 linhas de filtro e a própria conferência por unidade
  prova a equivalência — um filtro diferente produz digest diferente e recusa.
- **Esperado (I2).** Pares lidos = `{("fact_oos_predictions", run_id)}` para todo run
  do cohort; esperado = as chaves julgadas `fact_oos_predictions|<run_id>|*` desses
  runs, `dim_run|<parent_sweep_id>` e `realized|<asset>`; comparado com as unidades
  recalculadas (chaves e digests, igualdade exata). Chave julgada de outro par
  (ablação; `fact_permuted_predictions|…`/`fact_vsn_weights|…` do mesmo `run_id`) fica
  fora. Diferença, falta ou sobra → `SilverContentMismatchError(sorted keys)`.
  `silver_units` do registro: sharpness = todas as unidades lidas; fan chart = as
  unidades dos runs da seed resolvida + `dim_run` + `realized`.
- **DM (I4).** Linhas de `gold_dm_results` com `variance_estimator == "rectangular"`
  (= `plan.dm.primary_estimator.value`, conferido), `candidate == plan.candidate` e
  `comparator` em `plan.comparator_tiers.all`; `adjusted_p_value` e `rejected`
  conferidos com `profile.horizons[h].dm` (entradas `estimator == "rectangular"`) —
  divergência ou ausência → `ReportSourceMismatchError`. Rótulo da linha por
  `verdict.horizons[h].h1.passed`.
- **Leitura do scorecard.** O scorecard é o `Mapping` JSON da cópia
  (`documents[SCORECARD_DOCUMENT]`); `verdict.horizons`/`profile.horizons` são listas
  com o campo `horizon` (o "[h]" do concept é a entrada com `horizon == h`); acesso
  por chave com `KeyError` → `ReportSourceMismatchError` (documento fora da forma).
- **Determinismo do dossiê (I8).** Nenhum instante da geração, host, caminho absoluto
  ou commit HEAD. Instantes **persistidos** (âncoras, `commented_at` do `.judged.toml`,
  `started_at` do manifesto/tentativa) são dado e entram. O dossiê diz "regenerar em
  qualquer commit com `code.src = <x>`" com o valor do snapshot.
- **Markdown dos dossiês** (`dossier_markdown.render(dossier, visibility) -> str`):
  título, parágrafo de como regenerar (comando literal do subcomando), um `##` por
  seção na ordem de `CITABLE_SECTIONS`, um `###` por bloco, tabela `| campo | valor |`,
  `Fonte:` com o ponteiro; links relativos a `docs/reports/` (figuras como
  `figures/<id>.pdf`; ponteiros como `../stages/...`, `../adr/...`); LF; termina em
  `\n`. O interno começa com o aviso "Interno, fora do texto do TCC".
- **Subcomando** (refinamento do concept §4, sem mudar o use case): `report-artifacts
  --data-root <dir> --cohort <toml> --preregistration <nome> --revision <r>
  --preregistration-ref <ref> [--output <dir>] [--register <toml>]` pelo helper
  `add(..., lock=False)` (só leitura sobre `data/`): `--data-root`/`--cohort` porque o
  probe do ambiente usa o arquivo de cohort (I10) e o silver vive na raiz do cohort;
  `--preregistration`/`--revision` pela simetria com `evaluate`/`audit-reproduction`
  (o use case resolve a revisão pela cadeia e confere a ref). Defaults: `--output` =
  `<repo_root>/docs/reports`, `--register` = `<repo_root>/docs/reports/dossier_register.toml`.
  O `cli.py` lê o cohort pelo `cohort_file` do `modeling` (já carregado ali; o slice
  `evaluation` não importa o `modeling`) e passa `spec.seeds` e `spec.device`;
  `evaluation_commands.report_artifacts(use_case, *, register_path, name, revision,
  preregistration_ref, cohort_seeds, out) -> int` parseia o registro e chama o use
  case. Exit 0 em sucesso, 2 em erro (o `main` já mapeia). Stdout:
  ```
  report <ref>: generation_digest <64 hex> figures 10 register_entries <n>
  figure <id> data_digest <64 hex>                     # 10 linhas, na ordem do catálogo
  dossier citable final_traceability_dossier.md internal final_traceability_dossier_internal.md
  ```
- **Composition root.** `ApplicationDependencies.generate_report_artifacts_for:
  Callable[[Path, str, Path], GenerateReportArtifacts]` (arquivo de cohort, device,
  diretório de saída), montada por `report_artifacts_wiring(...)` como o
  `confirmatory_wiring`: `ParquetGoldStore(cfg.data_root)` (o mesmo do refresh) como
  `judged_store`, o mesmo `TomlPreregistrationSource`, o `ParquetAnalyticsRepository`
  como `SilverTableReader`, o `ReadTrainingGrid` do refresh como `TrainingGridReader`,
  o `CanonicalJsonHasher`, `GitEvaluationEnvironment` igual ao da corrida (probe do
  cohort, `code.cohort_file`), `MatplotlibFigureRenderer()` e
  `FilesystemReportSink(output_dir)`.
- **Renderer.** `matplotlib.figure.Figure` + `FigureCanvasPdf` (sem `pyplot`, sem
  estado global); `matplotlib.rc_context` com `pdf.fonttype = 42`, `font.family =
  "DejaVu Sans"` (fonte embarcada no matplotlib: nenhuma dependência de fonte do
  sistema), tamanhos fixos (`figure.figsize` por número de painéis, 6,3 in de largura
  útil para A4 com margens do TCC), `axes.grid` recessivo, um eixo y por painel;
  `savefig(buffer, format="pdf", metadata={"CreationDate": None})`. Mapa **fixo**
  modelo → (cor, marcador, estilo de linha) declarado no adapter, cores da ordem
  categórica do `references/palette.md` da skill `dataviz`, validadas na Task 11 pelo
  `validate_palette.js --mode light` (saída em §7); heatmap e escalas sequenciais em
  `cividis`. Modelo fora do mapa → `ValueError` (nada de cor gerada). Rótulos em PT.
  `identity()` = `{"format": "pdf", "matplotlib": <__version__>, "freetype":
  <matplotlib.ft2font.__freetype_version__>}`. O processo do renderer roda com
  `MPLCONFIGDIR` gravável (o container usa `/tmp`); o adapter não lê variável de ambiente.
- **Sink.** `FilesystemReportSink(output_dir)`. `write(figures, dossier)`: valida tudo
  antes de tocar o disco (ids únicos e do catálogo, bytes começam com `%PDF`); grava
  `figures/<id>.pdf`, `figures/<id>.json` e os dois `.md` em
  `<output_dir>/.report-artifacts-staging/` (removido antes se existir); troca no fim:
  `figures/` atual → `.report-artifacts-previous/`, staging/`figures` → `figures/`,
  cada `.md` por `os.replace`; sucesso → remove o anterior; falha em qualquer passo →
  restaura o anterior e remove o staging (saída anterior intacta, I9). Só toca
  `figures/` e os dois `.md`; os demais arquivos de `docs/reports/` (relatórios da
  8.2, registro curado) nunca.

### Comandos no container

Fluxo Docker-only. Git Bash; caminhos com barra normal (com `\` o bind mount sai
vazio sem erro):

```bash
WT=feat-234-8-3-plots-and-final-report
RUN="docker run --rm --cpus 6 --memory 8g --memory-swap 8g \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT:/app \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git \
  -v financial-forecasting_app-venv:/app/.venv \
  -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e MPLCONFIGDIR=/tmp/mpl -w /app financial_forecasting-app:dev"
PRE="git config --global --add safe.directory '*'"
# T1 de uma Task (testes + ruff/mypy dos arquivos, RUNBOOK "T1 sem o hook"):
MSYS_NO_PATHCONV=1 $RUN sh -c "$PRE; uv run --no-sync pytest <arquivos> -q --no-cov && uv run --no-sync ruff format --check <arquivos> && uv run --no-sync ruff check <arquivos> && uv run --no-sync mypy"
```

Tasks que tocam `.importlinter` acrescentam `uv run --no-sync lint-imports` ao T1.

T3 (`make check`) — comando literal; **`PYTEST_PAR` como argumento do make** (a
atribuição do Makefile vence a variável de ambiente — finding da 8.1) e
`UV_NO_SYNC=1` (o volume do venv é compartilhado entre worktrees):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --cpus 6 --memory 8g --memory-swap 8g -v "C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-234-8-3-plots-and-final-report:/app" -v "C:/Users/Marcelo/Documents/Code/financial-forecasting/.git:/main.git" -v financial-forecasting_app-venv:/app/.venv -e GIT_DIR=/main.git/worktrees/feat-234-8-3-plots-and-final-report -e GIT_WORK_TREE=/app -e UV_NO_SYNC=1 -e MPLCONFIGDIR=/tmp/mpl -w /app financial_forecasting-app:dev sh -c "git config --global --add safe.directory '*'; make check PYTEST_PAR='-n 4 --dist loadgroup'"
```

Conferir no log que só sobem `gw0..gw3`. Worker do xdist caído ("node down", CPU ~0 %
perto do fim) invalida o resultado: parar e rodar de novo. `-n 4` sem `--dist
loadgroup` atropela fixtures de `tests/architecture` (8.2 §7): nunca.

### Pré-condições

- Concept `done` (`3bd4a434`) e ADRs 8.3.0001–0004; 8.2 mergeada (`done` no roadmap).
- Imagem `financial_forecasting-app:dev` com `matplotlib` 3.11.0 no volume do venv
  (`uv.lock` já trava 3.11.0). Nenhum `uv sync`/`make setup` em worktree alguma
  durante a Etapa R (volume compartilhado).
- Etapa R: partição viva `data/cohorts/aapl/` com `judged/aapl_confirmatory-r3-00fd83d9cd39/`
  íntegra (`sha256sum -c CONTENTS.sha256`) e o silver do cohort; nenhum outro processo
  escrevendo em `data/cohorts/aapl/`.

### Premissas técnicas

- Python 3.12, mypy strict (`src`, `tests/contract`, `tests/fakes`),
  `from __future__ import annotations`.
- `scripts/check_port_coverage.py`: cada port novo tem fake (`InMemory<X>`) e contrato
  `[fake, real]` — chegam nas Tasks 04 (fakes) e 11/12 (contratos); entre elas o gate
  ficaria vermelho, e nenhum `make check` roda ali (ponto 1 depois da 15).
- `scripts/check_use_case_deps.py`: o `__init__` do use case anota só ports.
- `tests/architecture/test_unit_evaluation_purity.py`: os unit de
  `tests/unit/features/evaluation/` não importam `*.adapters.*` nem abrem arquivo — o
  teste AST do A6 e os testes do registro real moram em `tests/architecture/`; o parser
  do registro e o CLI são testados em `tests/unit/test_cli.py` e em `integration/`.
- `scripts/check_layout.py`: adapter não importa outro adapter — o sink não importa o
  renderer (recebe bytes); o CLI não importa `adapters/out/`.
- O realizado do `TrainingGridReader` é a grade inteira do ativo; o
  `SeriesAssembly` casa `target_timestamp` com ela como no refresh.

### Plano de gates

| # | Depois da Task | Por quê |
|---|---|---|
| 1 | 15 (depois da auditoria de testes com mutação real e do Checkpoint C final) | Pré-geração real: o grupo de risco está todo nas Tasks 01, 11 e 13 — dependência e `uv.lock` (01), `.importlinter` (01 e 11: a linha `ignore_imports` só casa quando o adapter de plots existe), port novo consumido pelo composition root e `cli.py` (13); o T1 não roda `tests/architecture/` inteiro nem os scripts de gate (`port-coverage` só fica verde com os contratos das 11/12). Os artefatos commitados na Etapa R carregam o `code.src`: um vermelho descoberto depois da geração obrigaria a regenerar e recommitar, então o gate tem de estar verde **antes** da R2. Um ponto depois da 01 não se paga: o T1 da 01 roda `lint-imports` e os dois testes de arquitetura que ela toca, e as Tasks 02–10 não constroem sobre nada que o gate invalidaria além disso. |
| 2 | saída (depois da R4) | Gate de saída (Passo 10): a Etapa R commita `docs/reports/figures/` e os dois dossiês (e §7); confirma que nada no `src/` mudou desde o ponto 1 e que a suíte segue verde com os artefatos no repo. |

**Ponto 2 vermelho (GB-3).** Se o fix toca `src/`, `uv.lock`, `pyproject.toml` ou
`.importlinter`: o `code.src` muda e invalida os artefatos commitados → `fix` +
revisão independente + novo `make check` + `GATE1` novo + **refazer R1–R4**, com os
artefatos regenerados num commit **novo** (nunca amend). Se o vermelho é só de docs
(§7, registro, roadmap), consertar sem regenerar e rodar o `make check` de novo.

Nas demais Tasks o gate é o T1. Vermelho no ponto 1 → `fix(<escopo>): …
[8.3/task-NN-fix]`, **revisão independente do fix** (subagente) e novo `make check`
(3º ponto, justificado: só o commit verde pode ser o `GATE1` da Etapa R).

### Estrutura de pastas afetada

```
pyproject.toml, uv.lock, .importlinter                                   # T01 (+ .importlinter T11)
src/financial_forecasting/
├── cli.py                                                               # report-artifacts (T13)
├── composition_root.py                                                  # report_artifacts_wiring (T13)
└── features/evaluation/
    ├── application/
    │   ├── dtos/{report_artifacts.py (T02), gold_schema.py (T03)}
    │   ├── ports/out/{figure_renderer.py, report_artifact_sink.py}      # T04
    │   └── use_cases/{report_silver.py (T05), report_figures.py (T06–T08),
    │                  report_dossier.py, dossier_markdown.py (T09),
    │                  judged_copy.py, generate_report_artifacts.py,
    │                  audit_reproduction.py (T10)}
    └── adapters/
        ├── in/cli/{dossier_register.py, evaluation_commands.py}        # T13
        └── out/{plots/ (T11), reports/ (T12)}
tests/
├── fakes/features/evaluation/{in_memory_figure_renderer.py, in_memory_report_artifact_sink.py}   # T04
├── unit/features/evaluation/{test_report_artifacts_dtos.py (T02), test_gold_schema_report_columns.py (T03),
│     test_report_silver.py (T05), _report_inputs.py (T06), test_report_figures_calibration.py (T06),
│     test_report_figures_inference.py (T07), test_report_figures_silver.py (T08),
│     test_report_dossier.py (T09), test_generate_report_artifacts.py (T10)}
├── unit/test_cli.py                                                      # T13
├── contract/features/evaluation/{test_figure_renderer_contract.py (T11), test_report_artifact_sink_contract.py (T12)}
├── integration/features/evaluation/{test_report_figures_render_smoke.py (T11),
│     test_dossier_register_parser.py (T13), test_report_artifacts_cli.py (T14)}
└── architecture/{test_import_contracts.py (T01), test_stage_8_3_regression_guards.py (T01, T07),
                  test_stage_8_3_repo_files.py (T15)}
docs/reports/{dossier_register.toml (T15), figures/*.pdf|json, final_traceability_dossier*.md (R)}
```

## 2. Tasks

### Task 01 — matplotlib direto, contrato `evaluation-no-matplotlib-leak` e guarda contra `pyplot`

- **Arquivos a modificar:** `pyproject.toml`, `uv.lock`, `.importlinter`,
  `tests/architecture/test_import_contracts.py`
- **Arquivos a criar:** `tests/architecture/test_stage_8_3_regression_guards.py`
- **Testes primeiro:** `test_import_contracts.py` — `"evaluation-no-matplotlib-leak"`
  na lista de contratos esperados; caso em `_REAL_VIOLATION_CASES`
  `evaluation-no-matplotlib-leak:toml-adapter-imports-matplotlib` (arquivo
  `features/evaluation/adapters/out/toml/_arch_taint_mpl.py` com `import
  matplotlib` — **pacote existente** com `__init__.py`: o grimp pula módulo de
  diretório sem `__init__`, e injetar um `__init__` em `reports/` faria o `finally` do
  teste apagar o real depois da Task 12; o caso de `adapters/out/reports/` entra na
  Task 12, quando o pacote existe — CB-1) — o mesmo caso satisfaz
  `test_every_forbidden_module_has_a_real_violation_case`;
  `test_stage_8_3_regression_guards.py::test_no_pyplot_anywhere_in_src` (AST de todo
  `src/**/*.py`: `import matplotlib.pyplot`, `from matplotlib import pyplot` e `from
  matplotlib.pyplot import …` reprovam, inclusive em `adapters/out/plots/`) com um
  auto-teste sobre fonte sintética (`ast.parse` de uma string com cada forma → 3
  achados; sem o auto-teste a guarda vazia passaria).
- **O que fazer:** `"matplotlib>=3.11,<3.12"` em `[project] dependencies` com o bloco
  de comentário na postura dos demais (Stage 8.3 / ADR 8.3.0003; vive SÓ em
  `features/evaluation/adapters/out/plots/`; gate import-linter; pin por minor);
  `uv lock` no container (sem `--upgrade`); conferir que o diff do `uv.lock` fica no
  bloco `[[package]]` do próprio projeto (`{ name = "matplotlib" }` em `dependencies` e
  a linha do `requires-dist`) e que `git diff -U0 uv.lock | grep -E '^[-+](version|name) = '`
  sai vazio (nenhum pacote novo, nenhuma versão alterada — GB-5). No
  `.importlinter`, o contrato `evaluation-no-matplotlib-leak` (`type = forbidden`,
  `source_modules = financial_forecasting`, `forbidden_modules = matplotlib`,
  `allow_indirect_imports = False`) com o comentário de cabeçalho (LAYOUT §3; D6) —
  **sem** `ignore_imports` nesta Task: nenhum módulo importa matplotlib ainda, e a
  linha `plots.** -> matplotlib` sem import que case reprovaria pelo
  `unmatched_ignore_imports_alerting` (default `error`); ela entra na Task 11.
- **Critério de aceite:** A15 (dependência, contrato com prova de quebra, AST contra
  `pyplot`).
- **Verificação (T1):** `uv run --no-sync lint-imports` +
  `pytest tests/architecture/test_import_contracts.py tests/architecture/test_stage_8_3_regression_guards.py -q --no-cov`
  + `git diff -U0 uv.lock | grep -E "^[-+](version|name) = "` vazio.
- **Commit:** `build(evaluation): matplotlib direto e contrato que o confina ao adapter de plots [8.3/task-01]`

---

### Task 02 — DTOs do dado plotado, do registro, do dossiê e o catálogo fechado

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/report_artifacts.py`
  - `tests/unit/features/evaluation/test_report_artifacts_dtos.py`
- **Testes primeiro:** `test_catalog_has_the_ten_ids_in_doc_order`;
  `test_catalog_omissions_equal_concept_d13_literal` (A16: dicionário literal id →
  omissões copiado do D13; τ = 0,5 e a banda do candidato fora do gate/na média em
  `reliability_diagram`; faixa da ACF em `loss_differential_acf`; ICs de I_f e s_f em
  `h3_family_importance`; Beta agregada e Wilson do nativo na média em
  `native_vs_conformal`; vazio nas outras seis); `test_spec_rejects_omission_outside_catalog`;
  `test_spec_rejects_missing_required_note[<id>]` (parametrizado nas sete figuras com
  frase); `test_series_without_label_does_not_construct`;
  `test_status_label_has_no_exploratory`; `test_non_finite_values_rejected`;
  `test_low_high_lengths_must_match_x`; `test_horizon_panel_requires_horizon_and_invariant_forbids_it`;
  `test_canonical_bytes_are_order_independent_and_exact` (dois mapas iguais com ordem
  de inserção diferente → mesmos bytes; `math.nextafter` num valor → bytes e
  `data_digest` diferentes); `test_record_as_mapping_fields_and_no_commit_or_time`
  (chaves exatas; recusa chave `commit`/`*_at`/`time` e valor absoluto `/…`);
  `test_dossier_entry_kinds_closed_and_finding_requires_open`;
  `test_non_internal_entry_with_forbidden_pointer_rejected[<ponteiro>]` (cada prefixo
  proibido do A17, com variação de caixa e `_`/`-`); `test_citable_82_anchors_allowed`
  (as quatro âncoras declaradas passam como `deviation`/`reproduction`);
  `test_internal_entry_may_point_anywhere`; `test_dossier_sections_closed`
  (`CITABLE_SECTIONS` = lista literal das 13 linhas do doc §7 menos a última);
  `test_command_and_result_validation`;
  `test_check_artifacts_accepts_ten_catalog_ids_with_pdf_bytes_and_matching_records`,
  `test_check_artifacts_rejects_duplicate_id`, `test_check_artifacts_rejects_missing_or_unknown_id`,
  `test_check_artifacts_rejects_non_pdf_bytes`, `test_check_artifacts_rejects_record_of_other_id`;
  `test_forbidden_patterns_match_each_a17_term` (relatório `equivalence_audit.md`,
  `prior_evidence`, `tests/equivalence`, `8.2.0003`/`8_2_0004`/`8-2-0003`,
  `prior_candidate_labels`, "evidência anterior", "projeto anterior", ponteiro à §5 do
  `reproduction_audit.md`; sem caixa, `_` ≡ `-`),
  `test_forbidden_patterns_spare_citable_82_anchors` (caminho
  `docs/stages/8.2-equivalence-audit/technical.md#…` das âncoras citáveis não casa),
  `test_find_forbidden_returns_matches_in_text`.
- **O que fazer:** os DTOs, enums, `FIGURE_CATALOG`, `CITABLE_SECTIONS`,
  `CITABLE_82_ANCHORS` e erros do §1, com validação na construção (`ValueError`) e
  `as_mapping()` JSON-safe; `check_artifacts(figures, dossier)` (validação da escrita,
  dono único — §1); `CITABLE_FORBIDDEN_PATTERNS` (tupla de `re.Pattern` compilados com
  `re.IGNORECASE`, refinamento do A17 do §1, com lookbehind que poupa
  `8.2-equivalence-audit/`) e `find_forbidden(text) -> tuple[str, ...]` (os trechos que
  casam). Só stdlib (`hashlib`, `json`, `re`).
- **Critério de aceite:** A11 (forma do registro, `data_digest` pelo dono único), A16
  (omissões fechadas no tipo), A17 (1ª barreira), base do A1/A5/A12.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_report_artifacts_dtos.py -q --no-cov`
- **Commit:** `feat(evaluation): DTOs do dado plotado, do registro por figura e do dossiê [8.3/task-02]`

---

### Task 03 — `read_columns` ampliado no schema do gold (D3)

- **Arquivos a modificar:**
  `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
- **Arquivos a criar:** `tests/unit/features/evaluation/test_gold_schema_report_columns.py`
- **Testes primeiro:** `test_calibration_reads_violation_rate_and_wilson_columns`
  (`violation_rate`, `wilson_estimate`, `wilson_lower`, `wilson_upper` em
  `GOLD_CALIBRATION_TABLE.read_columns`); `test_dm_results_reads_raw_p_value`;
  `test_conformal_schemas_untouched` (tuplas literais atuais de
  `GOLD_CONFORMAL_COVERAGE.read_columns` e `GOLD_CONFORMAL_CORRECTIONS.read_columns` —
  o `_empty_row` do builder de cobertura e o literal de
  `test_conformal_gold_builders.py:95` (que compara as **correções**) dependem delas).
- **O que fazer:** acrescentar as colunas no fim das duas tuplas (ordem estável) e uma
  linha no docstring (Stage 8.3, leitura por nome das figuras). Nenhuma outra tabela:
  todas as demais colunas do D13 já estão no schema (conferido na Fase 3B).
- **Critério de aceite:** D3; risco "coluna nova quebrar leitores" coberto pelos
  existentes `test_schema_columns_written` (contrato dos builders: as colunas são
  gravadas), `test_every_schema_column_has_a_declared_class` (8.2) e
  `test_refresh_gold_dtos` (chave ∩ lidas vazio), rodados aqui.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_gold_schema_report_columns.py tests/unit/features/evaluation/test_reproduction_comparison_dtos.py tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py tests/unit/features/evaluation/test_scorecard_evidence_mapper.py tests/contract/features/evaluation/test_gold_builder_contract.py tests/contract/features/evaluation/test_conformal_gold_builders.py -q --no-cov`
- **Commit:** `feat(evaluation): colunas lidas pelas figuras no schema do gold [8.3/task-03]`

---

### Task 04 — Ports `FigureRenderer` e `ReportArtifactSink` com fakes

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/figure_renderer.py`
  - `src/financial_forecasting/features/evaluation/application/ports/out/report_artifact_sink.py`
  - `tests/fakes/features/evaluation/in_memory_figure_renderer.py`
  - `tests/fakes/features/evaluation/in_memory_report_artifact_sink.py`
- **Testes primeiro:** nenhum teste próprio — os fakes são exercitados pelos testes do
  use case (Task 10) e pelos contratos `[fake, real]` (Tasks 11–12). Port e fake na
  mesma Task (sem adapter real) não é a mistura que a PIPELINE §4.3 item 4 proíbe.
- **O que fazer:** os Protocols do concept §4 (docstrings: determinismo, PDF; uma
  chamada com tudo, tudo ou nada). `InMemoryFigureRenderer`: `render` →
  `b"%PDF-fake\n" + spec.canonical_bytes()`; `identity()` →
  `{"format": "pdf", "renderer": "in-memory"}`; conta chamadas.
  `InMemoryReportArtifactSink`: chama `check_artifacts` (dono único, Task 02) antes de
  guardar; guarda a tupla e o dossiê da **única** chamada (`writes` conta), `fail_with: Exception | None` injetável (para o tudo ou nada do use case).
- **Critério de aceite:** contratos do concept §4 presentes; `mypy` verde.
- **Verificação (T1):** `uv run --no-sync mypy` + `python scripts/check_port_coverage.py --list | grep -E "FigureRenderer|ReportArtifactSink"` (fake listado; contrato ainda ausente, esperado até a 12).
- **Commit:** `feat(evaluation): ports do renderizador de figuras e do destino dos artefatos [8.3/task-04]`

---

### Task 05 — Leitura do silver e do realizado conferida por unidade (D4, I2)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/report_silver.py`
  - `tests/unit/features/evaluation/test_report_silver.py`
- **Testes primeiro** (`FakeSilverTableReader`, `FakeTrainingGridReader`, hasher
  stdlib de teste já usado nos unit de evaluation; o "julgado" é o `SilverContent` de
  um `SilverContentAccumulator` alimentado com as mesmas linhas, como o refresh):
  `test_identical_silver_passes_and_returns_runs_records_realized`;
  `test_altered_test_row_raises_with_unit_key`;
  `test_altered_calib_row_raises` (o digest cobre todos os splits — A4);
  `test_missing_unit_raises`; `test_extra_unit_read_raises` (run do cohort com unidade
  a mais que o julgado não tem); `test_altered_realized_raises`;
  `test_altered_dim_run_raises`; `test_ablation_units_only_in_judged_pass`;
  `test_permuted_and_vsn_units_of_candidate_run_id_only_in_judged_pass`;
  `test_rows_of_other_asset_or_run_are_filtered_before_hashing` (linha de outro run no
  mesmo `feature_set_name` não entra na unidade);
  `test_grid_fingerprint_other_than_plan_raises`; `test_error_message_has_keys_not_values`.
- **O que fazer:** `read_verified_silver(*, silver_reader, grid_reader, hasher,
  partition, expected_fingerprint, judged: SilverContent) ->
  VerifiedSilver` (DTO local frozen: `runs: tuple[CohortRun, ...]`,
  `records: tuple[ForecastRecord, ...]`, `realized: RealizedReturns`,
  `units: Mapping[str, str]`) com o pós-filtro e o esperado do §1; os
  `ForecastRecord`/`CohortRun` montados com as mesmas regras do refresh (o
  `guardrail_applied` 0/1). `_check_units(judged, read, run_ids, parent_sweep_id,
  asset)` puro.
- **Critério de aceite:** A4.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_report_silver.py -q --no-cov`
- **Commit:** `feat(evaluation): silver das figuras conferido por unidade contra a cópia julgada [8.3/task-05]`

---

### Task 06 — Figuras de calibração e cobertura: reliability, quantile score, PICP × MPIW, nativo × conformal

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/report_figures.py`
  - `tests/unit/features/evaluation/_report_inputs.py` (helper: plano r3 sintético —
    candidato, tiers, seeds `[1, 2]`, níveis com dois pares simétricos —, uma
    `GoldGeneration` montada por `GoldGeneration.from_stored` com as 19 tabelas e o
    scorecard `Mapping` coerente; **fakes discriminantes**: linhas iguais na chave
    exceto um eixo (`sample` common × model_full, `includes_degenerate`, `band_level`
    0,95 × 0,975, `variance_estimator` rectangular × bartlett, horizonte, seed) com
    valores distintos, de modo que ler a linha errada muda o valor desenhado)
  - `tests/unit/features/evaluation/test_report_figures_calibration.py`
- **Testes primeiro:**
  - reliability: `test_confirmatory_tails_equal_verdict_h1_bands_and_profile_power`
    (estimativa, limites, `band_level` 0,975, poder); `test_confirmatory_only_where_h1_passes`
    (H1 passa em h+1 e reprova em h+7 → caudas do gate de h+7 `descritivo (perfil)`);
    `test_candidate_descriptive_is_ratio_of_mean_counts_of_calibration_95`;
    `test_candidate_per_seed_points_from_calibration_table_95`;
    `test_baseline_and_gbm_wilson_from_calibration_table_gate_filter_95`;
    `test_upper_tail_drawn_as_complement_with_swapped_band`;
    `test_tau_half_absent`; `test_gate_filter_bound_to_h1_mean_observed` (fake com
    `mean_observed` divergente → `ReportSourceMismatchError`); `test_reliability_note`.
  - quantile score: `test_points_from_metrics_by_run_common_pinball_per_seed`;
    `test_candidate_mean_min_max_from_profile_descriptors`.
  - PICP × MPIW: `test_one_point_per_model_pair_seed_common`;
    `test_candidate_dispersion_and_mean_from_descriptors`;
    `test_nominal_reference_line_1_minus_2_tau_low`; `test_picp_mpiw_note`.
  - nativo × conformal: `test_conformal_rows_band_095_both_variants_seed_null_and_per_seed`
    (a linha 0,975 fica fora); `test_native_from_calibration_model_full_not_degenerate`;
    `test_native_seed_mean_ratio_from_calibration_95_profile`;
    `test_native_picp_mpiw_from_metrics_model_full`;
    `test_n_evaluated_differs_from_n_observed_raises`;
    `test_every_panel_has_empirical_coverage_label`.
  - comuns: `test_one_panel_per_horizon_never_mixed` (I5);
    `test_omissions_equal_catalog_and_no_series_draws_omitted_element` (A16: nenhuma
    série com `τ = 0,5`, nenhuma banda do candidato na média/fora do gate, nenhuma
    série Beta).
- **O que fazer:** `ReportInputs` (frozen: plano, ref, partição, geração, scorecard
  `Mapping`, seeds resolvidas) e as quatro funções `reliability_figure`,
  `quantile_score_figure`, `picp_mpiw_figure`, `native_vs_conformal_figure` pelo mapa
  do D13, leitura por `col_*` + `GoldTableSchema`, rótulos P8-ROT, transformações de
  exibição só as do I3 (complemento, razão de contagens médias). Cada função devolve
  também as `SourceRef` que leu (o registro vem delas, não de uma lista paralela).
- **Critério de aceite:** A1 (parcial), A5 (calibração), A7 (quatro figuras), A16.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_report_figures_calibration.py -q --no-cov`
- **Commit:** `feat(evaluation): figuras de calibração e cobertura a partir da cópia julgada [8.3/task-06]`

---

### Task 07 — Figuras de inferência e atribuição: DM, d_t + ACF, H3, VSN; teste AST do A6

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/report_figures.py`
  - `tests/unit/features/evaluation/_report_inputs.py`
  - `tests/architecture/test_stage_8_3_regression_guards.py`
- **Arquivos a criar:** `tests/unit/features/evaluation/test_report_figures_inference.py`
- **Testes primeiro:**
  - DM: `test_cells_are_horizon_by_family_comparator_only` (A1);
    `test_raw_p_from_rectangular_row_not_bartlett`;
    `test_adjusted_and_rejected_divergent_from_scorecard_raises`;
    `test_missing_scorecard_dm_entry_raises`;
    `test_row_label_h2_not_applicable_where_h1_fails` (A5);
    `test_cell_text_has_raw_p_and_holm_decision`.
  - d_t: `test_sign_flipped_when_candidate_is_model_b` e
    `test_sign_kept_when_candidate_is_model_a` (D14, d_t = L_cand − L_comp; a
    convenção L_a − L_b do builder está no docstring de `profile_reports.py` l. 6 e
    fica fixada por estes dois testes); `test_only_candidate_family_pairs`;
    `test_acf_stems_from_gold_acf_by_lag`; `test_acf_band_absent` (omissão);
    `test_fold_cuts_from_differential_fold`.
  - H3: `test_if_h_is_aggregate_row_seed_and_permutation_null`;
    `test_per_seed_profiles_both_methods_per_permutation_only_permutation`;
    `test_shares_delta_interval_from_h3_shares`; `test_reading_label_status_from_h3_reading`;
    `test_h1_h7_side_by_side_and_comparison_panel`; `test_h3_note`;
    `test_no_if_or_sf_interval_drawn`.
  - VSN: `test_only_kind_family_rows`; `test_single_horizon_invariant_panel_with_note`.
  - `test_stage_8_3_regression_guards.py::test_report_figures_imports_no_inferential_service`
    (AST dos módulos da lista `GUARDED_MODULES` do teste — nesta Task
    `report_figures.py` e `report_silver.py`; a Task 09 acrescenta `report_dossier.py` e
    `dossier_markdown.py`, a Task 10 `generate_report_artifacts.py`, cada uma com o arquivo
    de teste na sua lista e no T1 — N1; **lista PERMITIDA** de
    `features.evaluation.domain.services` (CB-6): só `series_assembly` e
    `coverage_metrics` (e `degeneracy_gate`, se a montagem o chamar diretamente);
    qualquer outro módulo de `domain.services` reprova — cobre `diebold_mariano`,
    `holm_correction`, `model_confidence_set`, `wilson_band`, `h1_gate`,
    `h1_gate_power`, `differential_stationarity`, `kupiec_pof`, `christoffersen_test`,
    `chi_square`, `student_t`, `dm_profiles`, `confirmatory_scorecard`, `pinball_score`,
    `interval_score`, `crps_score`, `paired_pinball_losses`, `var_descriptive`,
    `conformal_*` e serviço futuro; `from …domain.services import x` é resolvido pelo
    `alias.name`; auto-teste sobre fonte sintética com as três formas de import).
- **O que fazer:** `dm_figure`, `loss_differential_figure`, `h3_figure`, `vsn_figure`
  pelo D13 e pelas decisões do §1 (DM, D14).
- **Critério de aceite:** A1 (DM e H3), A5 (DM), A6, A7 (quatro figuras), A16.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_report_figures_inference.py tests/unit/features/evaluation/test_report_figures_calibration.py tests/architecture/test_stage_8_3_regression_guards.py -q --no-cov`
- **Commit:** `feat(evaluation): figuras do DM, do diferencial, de H3 e da VSN sem teste novo [8.3/task-07]`

---

### Task 08 — Figuras do silver: sharpness diagram e fan chart (D4, I6)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/report_figures.py`
  - `tests/unit/features/evaluation/_report_inputs.py` (silver sintético coerente com o
    gold: `VerifiedSilver` com dois pares simétricos, degenerados de propósito e o
    `mpiw` `model_full` do gold calculado pelo `CoverageMetrics` sobre as mesmas linhas)
- **Arquivos a criar:** `tests/unit/features/evaluation/test_report_figures_silver.py`
- **Testes primeiro:**
  - sharpness: `test_boxes_from_interval_widths_split_test_symmetric_pairs`;
    `test_mean_of_drawn_widths_equals_gold_mpiw_model_full_exactly`;
    `test_degenerate_rows_excluded_and_counted_in_legend`;
    `test_candidate_seeds_stacked_with_legend`; `test_mpiw_mismatch_raises`
    (gold falso com `mpiw` diferente → `ReportSourceMismatchError`);
    `test_sharpness_note`.
  - fan chart: `test_uses_first_seed_of_revision_only` (A8);
    `test_cohort_seeds_differ_from_revision_raises`;
    `test_first_seed_without_predictions_raises_no_fallback`;
    `test_bands_are_value_guardrail_symmetric_pairs_and_median`;
    `test_realized_from_series_realized`; `test_fold_cuts_marked`;
    `test_legend_names_the_seed`; `test_never_mean_of_quantiles_across_seeds` (silver com
    seed 2 discriminante: nenhum valor da seed 2 aparece).
  - `test_silver_units_of_each_figure` (fan chart só as unidades da seed resolvida +
    `dim_run` + `realized`; sharpness todas).
  - `test_sharpness_returns_excluded_degenerate_counts` (o fake tem degenerados
    conhecidos por (modelo, seed, horizonte, par): a contagem devolvida é exatamente
    `len(série) − len(widths)` de cada um, com a chave do §1).
- **O que fazer:** `sharpness_figure(inputs, silver)` e `fan_chart_figure(inputs,
  silver, cohort_seeds)` pelo §1 ("Silver das figuras por ponto"): `SeriesAssembly`
  sobre `silver.records/runs/realized`, `CoverageMetrics.interval_widths`, seed =
  `plan.seeds[plan.candidate].seeds[0]` com a lista igual a `cohort_seeds`. As caixas
  do sharpness carregam mínimo, quartis e máximo das larguras por
  `statistics.quantiles(widths, n=4, method="inclusive")` (transformação de exibição
  declarada no I3, "caixa/quantis das larguras"); o renderer só desenha o que a spec
  traz (`Axes.bxp`), nunca recalcula.
  **Fluxo da contagem de degenerados (D4, CB-8):** toda função de figura devolve
  `FigureAssembly(spec, sources, silver_units, excluded_degenerate)`;
  `sharpness_figure` preenche `excluded_degenerate` (as demais devolvem vazio) e põe a
  mesma contagem na legenda da série; o use case (Task 10) copia
  `excluded_degenerate` para o `FigureRecord` — afirmado em
  `test_records_carry_data_digest_generation_digest_code_and_renderer` (Task 10).
- **Critério de aceite:** A7 (sharpness), A8.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_report_figures_silver.py tests/unit/features/evaluation/test_report_figures_inference.py tests/unit/features/evaluation/test_report_figures_calibration.py -q --no-cov`
- **Commit:** `feat(evaluation): sharpness e fan chart do silver conferido, seed pré-declarada [8.3/task-08]`

---

### Task 09 — Dossiê citável e interno e o seu Markdown (D8, D9)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/report_dossier.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/dossier_markdown.py`
  - `tests/unit/features/evaluation/test_report_dossier.py`
- **Arquivos a modificar:** `tests/architecture/test_stage_8_3_regression_guards.py`
  (`report_dossier.py` e `dossier_markdown.py` em `GUARDED_MODULES` — N1)
- **Testes primeiro** (fontes sintéticas: cadeia r0–r3 do
  `InMemoryPreregistrationSource`, `JudgedRecord`, tentativas `started`/`input_read`,
  `run_record` e scorecard `Mapping`, `dim_run`, registros de figura, registro curado):
  `test_citable_has_exactly_the_closed_sections` (A12); `test_blinding_statement_byte_for_byte`
  (D9; com acento, aspas e quebra de linha no texto sintético);
  `test_blind_status_of_each_amendment_and_ordering_caveat`;
  `test_power_next_to_each_h1_claim`; `test_one_pointer_per_verdict_claim`
  (H1×2, H2×2, vencedor, sucesso, H3, conformal: tabela/documento, chave, campo);
  `test_reproduction_section_has_claim_identities_and_pointer_to_sections_1_to_4`
  (`generation_digest`, `result_digest` da última `input_read`, commit do
  `.judged.toml`, `env.image_id` do `started`, entrada `reproduction` do registro com
  R1/R2/R3);
  `test_register_entries_routed_by_kind` (`internal` só no interno; demais só no
  citável); `test_open_findings_listed_resolved_absent`;
  `test_figures_section_lists_records_and_omissions`;
  `test_environment_commits_and_seeds_from_attempt_and_plan`;
  `test_no_generation_instant_host_or_absolute_path` (render duas vezes → bytes iguais;
  nenhum `/` absoluto; nenhum commit HEAD — o snapshot entra só por `code.src`/`code.uv_lock`);
  `test_citable_text_free_of_prior_evidence_terms` (2ª barreira do A17, sobre o texto
  renderizado, por `CITABLE_FORBIDDEN_PATTERNS`, e nenhum
  `reproduction_audit.md#5`/"§5"); `test_citable_anchors_of_82_pass_the_second_barrier`
  (registro sintético com as entradas de âncora citável `docs/stages/8.2-equivalence-audit/technical.md#…`
  de E2 item 7 e `env-equal`: o citável as contém e passa — CB-2); `test_internal_lists_required_items` (registro de
  hashes, `equivalence_audit.md`, B3/ADR 8.2.0004, `[finding]` do PICP, F2–F5, E4,
  limite da §5 — vindos das entradas `internal` do registro sintético);
  `test_markdown_is_lf_and_ends_with_newline`.
- **O que fazer:** `build_dossier(*, plan_chain, judged_record, attempts, run_record,
  scorecard, manifest, runs, records: tuple[FigureRecord, ...], register, snapshot)
  -> TraceabilityDossier` (puro) e `render(dossier, visibility) -> str` (puro, dono
  único do Markdown), com as camadas do D8 mapeadas em `CITABLE_SECTIONS`.
- **Critério de aceite:** A12, A17 (2ª barreira e completude do interno).
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_report_dossier.py tests/architecture/test_stage_8_3_regression_guards.py -q --no-cov`
- **Commit:** `feat(evaluation): dossiê de rastreabilidade citável e interno a partir das fontes [8.3/task-09]`

---

### Task 10 — Use case `GenerateReportArtifacts` com fakes

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/judged_copy.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/generate_report_artifacts.py`
  - `tests/unit/features/evaluation/test_generate_report_artifacts.py`
- **Arquivos a modificar:**
  `src/financial_forecasting/features/evaluation/application/use_cases/audit_reproduction.py`
  (passa a chamar `judged_copy`; comportamento e erros iguais);
  `tests/architecture/test_stage_8_3_regression_guards.py` (`generate_report_artifacts.py`
  em `GUARDED_MODULES` — N1)
- **Testes primeiro** (`InMemoryPreregistrationSource` com `add_judged`,
  `InMemoryJudgedGenerationStore`, `InMemoryGoldGenerationReader` com `current/`
  **diferente** da cópia, `FakeSilverTableReader`, `FakeTrainingGridReader`,
  `InMemoryEvaluationEnvironment`, `InMemoryFigureRenderer`, `InMemoryReportArtifactSink`):
  `test_ten_figures_in_catalog_order_and_one_write` (A1); `test_specs_come_from_judged_copy_never_current`
  (A2; o use case nem recebe `GoldGenerationReader` — o teste prova pelo valor);
  `test_dirty_tree_raises_before_any_read_or_write` (A13, I10);
  `test_no_committed_record_raises`; `test_record_digest_other_than_find_raises_tampered`;
  `test_missing_copy_raises_not_found`; `test_tampered_copy_propagates` (A3);
  `test_copy_without_scorecard_raises` — **toda** recusa afirma `sink.writes == 0` e
  `renderer.calls == 0` (CB-9);
  `test_confirmatory_label_only_on_gate_tails_and_dm_rows_where_h1_passes` (varre as dez
  specs do resultado: `confirmatório` só nas séries das caudas do gate da reliability e
  nas linhas do DM dos horizontes com `h1.passed`; em nenhum outro elemento — A5, CB-7); `test_silver_mismatch_writes_nothing` (A4);
  `test_dm_mismatch_writes_nothing`; `test_seed_mismatch_writes_nothing`;
  `test_nothing_rendered_when_any_build_step_fails` (renderer com 0 chamadas);
  `test_records_carry_data_digest_generation_digest_code_and_renderer` (A11; mudar um
  valor do gold falso muda o `data_digest` daquela figura; o registro do sharpness tem
  `excluded_degenerate` igual ao devolvido pela montagem e os demais vazio — CB-8);
  `test_sink_failure_propagates` (I9 do lado do use case);
  `test_result_lists_ids_and_digests`; `test_audit_reproduction_still_uses_same_errors`
  (o teste existente `test_audit_reproduction.py` roda inteiro no T1).
- **O que fazer:** construtor do concept §4; `__call__` na ordem (1) snapshot (sujo →
  `DirtyCodeError`) → `resolve_judged_revision` → partição do plano →
  `judged_copy.sealed_matching_record` (`None` → `ReportArtifactsError`) →
  `read_judged_generation` → scorecard e `run_record` da cópia; (2) `result_digest`
  por `judged_copy.last_input_read_digest`; (3) `read_verified_silver` contra
  `generation.manifest.silver_content`; (4) dez specs + registros + dossiê; (5)
  `renderer.render` de cada spec e **uma** `sink.write`.
- **Critério de aceite:** A1, A2, A3, A11, A13 (árvore suja), I9; base do A14.
- **Verificação (T1):** `pytest tests/unit/features/evaluation/test_generate_report_artifacts.py tests/unit/features/evaluation/test_audit_reproduction.py tests/architecture/test_stage_8_3_regression_guards.py tests/integration/features/evaluation/test_audit_reproduction_cli.py tests/integration/features/evaluation/test_reproduction_process_independence.py -q --no-cov`
- **Commit:** `feat(evaluation): use case que gera figuras e dossiê da cópia julgada [8.3/task-10]`

---

### Task 11 — `MatplotlibFigureRenderer` determinístico, contrato e smoke das dez figuras

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/plots/__init__.py` *(pacote; sem import de matplotlib)*
  - `src/financial_forecasting/features/evaluation/adapters/out/plots/matplotlib_figure_renderer.py`
  - `tests/contract/features/evaluation/test_figure_renderer_contract.py`
  - `tests/integration/features/evaluation/test_report_figures_render_smoke.py` (`integration`)
- **Arquivos a modificar:** `.importlinter` (linha
  `ignore_imports = financial_forecasting.features.evaluation.adapters.out.plots.** -> matplotlib`
  no contrato da Task 01)
- **Testes primeiro:** contrato `[fake, real]`:
  `test_same_spec_same_bytes_twice`; `test_starts_with_pdf_magic`;
  `test_identity_has_format` (real: também `matplotlib` = `3.11.0` e `freetype`);
  `test_different_data_different_bytes`. Só real:
  `test_bytes_equal_across_subprocesses_with_different_hash_seeds` (dois
  `subprocess.run([sys.executable, "-c", …])` com `PYTHONHASHSEED=0` e `=12345`, mesma
  spec serializada; sha256 iguais — A9); `test_no_creation_date` (`b"/CreationDate"`
  ausente); `test_type42_fonts_embedded` (`b"/FontFile2"` presente, nenhum
  `/Subtype /Type3`); `test_unknown_model_raises`; `test_one_page`
  (`b"/Type /Page\n"`/regex `/Type\s*/Page\b` conta 1).
  Smoke: `test_ten_synthetic_specs_render_one_page_each` (as dez specs montadas pelas
  funções da Tasks 06–08 sobre o `_report_inputs` — A10).
- **O que fazer:** o renderer do §1. Desenho genérico por `SeriesKind` (um eixo por
  painel; grade de painéis 1×n; `cells` = linha de células com `cividis` e texto;
  `boxes` = `Axes.bxp` com as estatísticas que a spec carrega (Task 08) — o adapter
  não recalcula quantis); `notes` como legenda de rodapé; rótulo de estatuto no título de
  cada painel e na legenda de cada série. Rodar `node <base da skill dataviz>/scripts/validate_palette.js
  "<hex,...>" --mode light` (host; sem `node`, rodar a página `<script type="module">`
  da skill) e colar a saída em §7 (`[measurement]`); FAIL → trocar o passo da cor na
  rampa da paleta e repetir.
- **Critério de aceite:** A9, A10, A15 (`ignore_imports` casado, contrato verde).
- **Verificação (T1):** `uv run --no-sync lint-imports` + `pytest tests/contract/features/evaluation/test_figure_renderer_contract.py tests/integration/features/evaluation/test_report_figures_render_smoke.py tests/architecture/test_stage_8_3_regression_guards.py tests/architecture/test_import_contracts.py -q --no-cov`
- **Commit:** `feat(evaluation): renderizador matplotlib de PDF determinístico [8.3/task-11]`

---

### Task 12 — `FilesystemReportSink` com staging e contrato

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/reports/__init__.py` *(pacote)*
  - `src/financial_forecasting/features/evaluation/adapters/out/reports/filesystem_report_sink.py`
  - `tests/contract/features/evaluation/test_report_artifact_sink_contract.py`
- **Arquivos a modificar:** `tests/architecture/test_import_contracts.py` (caso
  `evaluation-no-matplotlib-leak:reports-adapter-imports-matplotlib`, agora que o
  pacote `reports/` existe — prova do A15 "import em `adapters/out/reports/` reprova";
  CB-1)
- **Testes primeiro:** contrato `[fake, real]` (fixture devolve o sink e um leitor do
  que foi escrito por perna): `test_writes_every_figure_record_and_both_dossiers`;
  `test_record_bytes_are_document_bytes`; `test_rejects_duplicate_or_unknown_id_before_writing`;
  `test_rejects_non_pdf_bytes_before_writing`. Só real:
  `test_layout_figures_pdf_json_and_two_markdown`; `test_markdown_equals_dossier_markdown_render`;
  `test_rewrite_replaces_previous_figures_entirely` (figura antiga sem par some);
  `test_failure_midway_restores_previous_and_removes_staging` (monkeypatch de
  `os.replace` falhando na 2ª chamada; listagem sha256 do diretório igual à anterior —
  A13); `test_other_files_in_output_untouched` (`reproduction_audit.md` e o registro
  sintéticos ao lado ficam com os mesmos bytes); `test_two_writes_same_bytes` (I8).
- **O que fazer:** o sink do §1; LF; `encoding="utf-8"`; nenhum caminho absoluto no
  conteúdo.
- **Critério de aceite:** A11 (arquivos), A13 (staging), I8, I9.
- **Verificação (T1):** `uv run --no-sync lint-imports` + `pytest tests/contract/features/evaluation/test_report_artifact_sink_contract.py tests/architecture/test_import_contracts.py -q --no-cov` + `python scripts/check_port_coverage.py` + `python scripts/check_fake_parity.py`
- **Commit:** `feat(evaluation): destino de arquivos dos artefatos com troca atômica [8.3/task-12]`

---

### Task 13 — Parser do registro curado, subcomando `report-artifacts` e composition root

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/in/cli/dossier_register.py`
  - `tests/integration/features/evaluation/test_dossier_register_parser.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/adapters/in/cli/evaluation_commands.py` (`report_artifacts`)
  - `src/financial_forecasting/cli.py` (subparser pelo `add(..., lock=False)`, despacho, docstring do módulo)
  - `src/financial_forecasting/composition_root.py` (`report_artifacts_wiring`, campo `generate_report_artifacts_for`)
  - `tests/unit/test_cli.py`
  - `tests/unit/shared/test_composition_root.py`
- **Testes primeiro:** wiring: `test_report_artifacts_wiring_uses_real_collaborators`
  (precedente `test_composition_root.py` l. 682: `ParquetGoldStore` da raiz como
  `judged_store`, `TomlPreregistrationSource`, `ParquetAnalyticsRepository`,
  `ReadTrainingGrid`, `GitEvaluationEnvironment`, `MatplotlibFigureRenderer`,
  `FilesystemReportSink` no diretório pedido — CB-10). Parser (`integration`, lê `tmp_path`):
  `test_valid_register_parses_in_file_order`; `test_unknown_kind_raises`;
  `test_missing_field_raises`; `test_extra_field_raises`;
  `test_finding_without_open_status_raises`;
  `test_non_internal_forbidden_pointer_raises` (a 1ª barreira chega pelo DTO);
  `test_invalid_toml_raises`. CLI (unit, use case fake):
  `test_report_artifacts_requires_ref_name_revision_root_and_cohort`;
  `test_report_artifacts_defaults_output_and_register_under_repo_root`;
  `test_malformed_register_exits_2_before_use_case` (fake com 0 chamadas — A13);
  `test_report_artifacts_prints_contract_lines`; `test_cohort_seeds_passed_from_cohort_file`;
  `test_report_artifacts_exit_2_on_application_error`.
- **Tamanho:** 7 arquivos (acima do típico ≤ 5): parser, CLI, composition root e os
  três testes formam uma única fatia de entrada que só fica verde junta (o subcomando
  sem o parser ou sem o wiring não roda); partir deixaria commit vermelho.
- **O que fazer:** como no §1 ("Subcomando", "Composition root"); o parser recusa com
  `ValueError` (o `main` mapeia para exit 2) e nunca chega ao use case.
- **Critério de aceite:** A13 (registro malformado), A17 (o parser recusa pela fonte),
  contrato do subcomando.
- **Verificação (T1):** `pytest tests/unit/test_cli.py tests/unit/shared/test_composition_root.py tests/integration/features/evaluation/test_dossier_register_parser.py -q --no-cov` + `python scripts/check_use_case_deps.py` + `python scripts/check_layout.py`
- **Commit:** `feat(evaluation): subcomando report-artifacts com o registro curado na fronteira [8.3/task-13]`

---

### Task 14 — Ponta a ponta sintético pela CLI

- **Arquivos a criar:**
  `tests/integration/features/evaluation/test_report_artifacts_cli.py` (`integration`, `slow`)
- **Testes primeiro** (mundo julgado sintético da 8.1 — `_judged_world` de
  `test_run_confirmatory_evaluation.py`, com `[conformal]` e `[h3]` —, o `.judged.toml`
  gravado como no fixture `judged_toml`, raiz do mundo transformada em repositório git
  com `config/` commitado como no `test_evaluate_cli.py`, probe injetado pelo
  `CliWiring.runtime_probe_factory`, `IMAGE_ID` pelos `settings_overrides`, arquivo de
  cohort sintético com a lista de seeds do plano; registro sintético com uma entrada
  de cada kind): `test_generates_ten_pdfs_ten_records_and_two_dossiers_exit_0`;
  `test_second_generation_is_byte_identical` (listagem sha256 da saída igual);
  `test_data_root_unchanged` (sha256 de todo arquivo de `data/` antes e depois);
  `test_tampered_judged_copy_exit_2_nothing_written`;
  `test_judged_toml_with_other_digest_exit_2_nothing_written`;
  `test_record_data_digest_matches_spec_and_lists_silver_units` (A11 nos arquivos:
  `code.src`/`code.uv_lock` do probe, `renderer.matplotlib`);
  `test_citable_dossier_free_of_prior_evidence_terms` (A17 sobre o arquivo real
  gerado). Fallback se o repositório git no mundo sintético for inviável: montar o
  use case por `report_artifacts_wiring` com `InMemoryEvaluationEnvironment` e chamar
  `evaluation_commands.report_artifacts` (registrar `[deviation]`).
- **Critério de aceite:** A2, A3, A11, A13 (sem escrita nas recusas), A14 (forma
  sintética: determinismo e só leitura antes do dado real).
- **Verificação (T1):** `pytest tests/integration/features/evaluation/test_report_artifacts_cli.py -q --no-cov`
- **Commit:** `test(evaluation): ponta a ponta sintético do report-artifacts [8.3/task-14]`

---

### Task 15 — Registro curado de desvios e achados e teste do arquivo

- **Arquivos a criar:**
  - `docs/reports/dossier_register.toml`
  - `tests/architecture/test_stage_8_3_repo_files.py`
- **Testes primeiro:** `test_register_parses` (pelo parser da Task 13);
  `test_register_has_inherited_citable_items` (lista fechada do concept §3/A12: erratas
  O1 e O2 da 8.1 → `docs/stages/8.1-confirmatory-run/technical.md#…`; nota do
  `code.src` (formatação do ruff + docstring entre `060537fc` e o HEAD); `[deviation]`
  E2 item 7 e `env-equal` da 8.2 pelas âncoras citáveis; entrada `reproduction` com
  R1/R2/R3, imagem e ponteiro a `docs/reports/reproduction_audit.md#1-claim` …
  `#4-…` (só §1–§4); `pre_anchor` (ADR 6.5.0010 P1 e a ressalva do ADR 6.5.0003 item
  4); `environment` do treino (CPU) e da ablação (Linux/GPU, ADR 7.3.0004));
  `test_register_has_inherited_internal_items` (registro de hashes, `equivalence_audit.md`,
  B3/ADR 8.2.0004 e os `[deviation]` B3, `[finding]` do PICP 80 %, erratas F2–F5, E4 do
  andaime e `[deviation]` E4, `[deviation]`s do andaime (`PRIOR_CANDIDATE_LABELS`, CC4),
  limite da §5 do `reproduction_audit.md` — todos `internal`);
  `test_every_open_finding_entry_points_to_an_existing_section_7_heading` (âncora
  resolve num cabeçalho `[finding]` real do arquivo apontado).
- **O que fazer:** escrever o registro (comentário de cabeçalho: como editar, kinds,
  regra de visibilidade). **Varredura dos `[finding]` abertos** (definição do A12): os
  §7 dos technical das Stages 5.5, 6.x, 7.x, 8.1 e 8.2 parte (i); para cada
  `[finding]`, procurar entrada posterior (mesma §7 ou auditoria da Stage) que o declare
  corrigido/resolvido; os sem resolução entram com `kind = "finding"`,
  `status = "open"` e ponteiro para o cabeçalho; registrar a lista varrida (aberto ×
  resolvido, com a evidência da resolução) em §7 como `[measurement]`. Os sumários
  descrevem o fato; nenhum número de modelo da evidência anterior em entrada alguma.
- **Critério de aceite:** A12 (itens herdados e `[finding]` abertos), A17 (visibilidade
  pela fonte no arquivo real).
- **Verificação (T1):** `pytest tests/architecture/test_stage_8_3_repo_files.py -q --no-cov`
- **Commit:** `docs(evaluation): registro curado de desvios e achados do dossiê [8.3/task-15]`

---

### Etapa R — geração real sobre a cópia julgada (A14)

Não é Task numerada: produz o commit dos artefatos e as medições do §7. Roda **depois**
do ponto 1 verde, com a árvore limpa, na ordem R0 → R4.

**Sessão que executa.** Cada chamada de shell é um processo novo (variáveis não
persistem) e tem teto de 10 min:

- (i) todo valor calculado vai para `$SCRATCH/etapa-83.env`, e **todo** bloco começa
  com `set -eu; SCRATCH=<scratchpad da sessão, caminho absoluto literal>; . "$SCRATCH/etapa-83.env" || exit 1`;
- (ii) toda asserção que manda parar tem a forma `test … || { echo FAIL_<NOME>; exit 1; }; echo <NOME>`;
  todo comando cujo exit é evidência usa `cmd > out && rc=0 || rc=$?; echo "exit $rc"`
  e a conferência do `rc` é a linha seguinte;
- (iii) a geração roda num container **destacado** (`ff83-gen1`, `ff83-gen2`),
  esperado por `docker wait` em segundo plano (`run_in_background`), com `docker logs
  --tail`; `ExitCode`/`OOMKilled` gravados **antes** do `docker rm`;
- (iv) o container roda pelo **id** da imagem (`IMAGE_ID`), nunca pela tag; prefixar
  todo `docker run` com `MSYS_NO_PATHCONV=1`; todo `uv run` com `--no-sync`;
- (v) a mesma imagem nas duas gerações (I8); nenhum `uv sync`, `make setup`, rebuild
  de imagem ou `docker image prune` entre R2 e R4 (volume do venv compartilhado);
- (vi) push só no fim e isolado: `git -C "$WTH" push origin feat/234-8-3-plots-and-final-report`.

**R0 — Variáveis (host, Git Bash; uma vez, depois do ponto 1).**
```bash
set -eu
SCRATCH=<scratchpad da sessão, caminho absoluto literal, fora do repo>
cat > "$SCRATCH/etapa-83.env" <<EOF
SCRATCH=$SCRATCH
GATE1=<sha do commit verde do ponto 1>
WT=feat-234-8-3-plots-and-final-report
WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-234-8-3-plots-and-final-report
WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-234-8-3-plots-and-final-report
MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
REF=aapl_confirmatory-r3-00fd83d9cd39
DIGEST=96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539
LIVE=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl
P=/c/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl/gold/asset=AAPL/parent_sweep_id=aapl_confirmatory-r0-665f45d9169a
IMAGE_ID=$(docker image inspect --format '{{.Id}}' financial_forecasting-app:dev)
EOF
grep -Eq '^IMAGE_ID=sha256:[0-9a-f]{64}$' "$SCRATCH/etapa-83.env" || { echo FAIL_IMAGE_ID; exit 1; }; echo IMAGE_ID_OK
GATE1=$(grep '^GATE1=' "$SCRATCH/etapa-83.env" | cut -d= -f2)
git -C /c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/feat-234-8-3-plots-and-final-report cat-file -e "$GATE1^{commit}" || { echo FAIL_GATE1; exit 1; }; echo GATE1_OK
cat >> "$SCRATCH/etapa-83.env" <<'EOF'
RES="--cpus 6 --memory 8g --memory-swap 8g"
PRE="git config --global --add safe.directory '*'"
MOUNTS="-v $WTD:/app -v $MAIND/.git:/main.git:ro -v $MAIND/artifacts:/app/artifacts:ro -v financial-forecasting_app-venv:/app/.venv -v $MAIND/data/cohorts/aapl:/data:ro"
ENVS="-w /app -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0 -e IMAGE_ID=$IMAGE_ID -e MLFLOW_TRACKING_URI=sqlite:////tmp/mlruns.db -e MPLCONFIGDIR=/tmp/mpl -e UV_NO_SYNC=1"
GEN="uv run --no-sync python -m financial_forecasting.cli report-artifacts --data-root /data --cohort config/cohorts/aapl_confirmatory.toml --preregistration aapl_confirmatory --revision 3 --preregistration-ref $REF"
EOF
```

**R1 — HEAD íntegro (roda no início da R2 e da R3).**
```bash
set -eu; SCRATCH=<…>; . "$SCRATCH/etapa-83.env" || exit 1
test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_WT_DIRTY; exit 1; }; echo WT_CLEAN
git -C "$WTH" diff --quiet "$GATE1" HEAD -- src uv.lock pyproject.toml .importlinter || { echo FAIL_SRC_CHANGED_SINCE_GATE1; exit 1; }; echo SRC_AS_GATE1
git -C "$WTH" cat-file -e "HEAD:docs/reports/dossier_register.toml" || { echo FAIL_REGISTER_NOT_COMMITTED; exit 1; }; echo REGISTER_COMMITTED
printf 'CODE_SRC=%s\n' "$(git -C "$WTH" rev-parse HEAD:src)" >> "$SCRATCH/etapa-83.env"
```

**R2 — Antes, e a primeira geração.**
1. *Cópia julgada e listagem de `data/`:*
   ```bash
   set -eu; SCRATCH=<…>; . "$SCRATCH/etapa-83.env" || exit 1
   (cd "$P/judged/$REF" && sha256sum -c --quiet CONTENTS.sha256) || { echo FAIL_JUDGED_COPY; exit 1; }; echo JUDGED_COPY_OK
   test "$(sha256sum "$P/judged/$REF/CONTENTS.sha256" | cut -d' ' -f1)" = "$DIGEST" || { echo FAIL_DIGEST; exit 1; }; echo DIGEST_OK
   test "$(grep '^generation_digest' "$WTH/config/preregistration/aapl_confirmatory-r3.judged.toml" | cut -d'"' -f2)" = "$DIGEST" || { echo FAIL_RECORD; exit 1; }; echo RECORD_OK
   (cd "$LIVE" && find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum) > "$SCRATCH/live-before.sha256sum"
   wc -l < "$SCRATCH/live-before.sha256sum"
   test -z "$(docker ps -aq --filter name=^ff83-)" || { echo FAIL_CONTAINER_EXISTS; exit 1; }; echo NO_FF83
   ```
2. *Geração 1* (destacada; `docker wait` em segundo plano):
   ```bash
   set -eu; SCRATCH=<…>; . "$SCRATCH/etapa-83.env" || exit 1
   MSYS_NO_PATHCONV=1 docker run -d --name ff83-gen1 $RES $MOUNTS $ENVS "$IMAGE_ID" sh -c "$PRE; $GEN" > "$SCRATCH/gen1.cid"
   ```
   Ao sair: `docker logs ff83-gen1 > "$SCRATCH/gen1.out" 2>&1`; `docker inspect
   --format '{{.State.ExitCode}} {{.State.OOMKilled}}' ff83-gen1 > "$SCRATCH/gen1.state"`;
   `docker rm ff83-gen1`; `test "$(cat "$SCRATCH/gen1.state")" = "0 false" || { echo FAIL_GEN1; exit 1; }`;
   `test "$(grep -c '^figure ' "$SCRATCH/gen1.out")" = 10 || { echo FAIL_GEN1_FIGURES; exit 1; }`.
3. *Saídas e data intacto:*
   ```bash
   set -eu; SCRATCH=<…>; . "$SCRATCH/etapa-83.env" || exit 1
   (cd "$WTH/docs/reports" && sha256sum figures/*.pdf figures/*.json final_traceability_dossier.md final_traceability_dossier_internal.md) > "$SCRATCH/out-gen1.sha256sum" || { echo FAIL_OUTPUT_MISSING; exit 1; }
   test "$(wc -l < "$SCRATCH/out-gen1.sha256sum")" = 22 || { echo FAIL_OUTPUT_COUNT; exit 1; }; echo OUTPUT_22
   (cd "$LIVE" && find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum) > "$SCRATCH/live-after1.sha256sum"
   diff -q "$SCRATCH/live-before.sha256sum" "$SCRATCH/live-after1.sha256sum" || { echo FAIL_DATA_CHANGED; exit 1; }; echo DATA_INTACT
   git -C "$WTH" status --porcelain --untracked-files=all | sed 's/^...//' | LC_ALL=C sort > "$SCRATCH/written.txt"
   test "$(wc -l < "$SCRATCH/written.txt")" = 22 || { echo FAIL_UNEXPECTED_PATHS; exit 1; }
   grep -vxE 'docs/reports/figures/[a-z0-9_]+\.(pdf|json)|docs/reports/final_traceability_dossier(_internal)?\.md' "$SCRATCH/written.txt" && { echo FAIL_UNEXPECTED_PATHS; exit 1; }; echo ONLY_REPORTS_WRITTEN
   for f in "$WTH"/docs/reports/figures/*.json; do grep -q "\"code.src\": \"$CODE_SRC\"" "$f" || { echo "FAIL_CODE_SRC $f"; exit 1; }; done; echo RECORDS_CODE_SRC
   MSYS_NO_PATHCONV=1 docker run --rm $RES -v $WTD:/app:ro -v financial-forecasting_app-venv:/app/.venv -w /app -e UV_NO_SYNC=1 "$IMAGE_ID" sh -c "uv run --no-sync python -c \"import sys; from pathlib import Path; from financial_forecasting.features.evaluation.application.dtos.report_artifacts import find_forbidden; hits = find_forbidden(Path('docs/reports/final_traceability_dossier.md').read_text(encoding='utf-8')); print('HITS', len(hits)); sys.exit(1 if hits else 0)\"" > "$SCRATCH/citable-scan.txt" && rc=0 || rc=$?
   echo "exit $rc"; cat "$SCRATCH/citable-scan.txt"; test "$rc" = 0 || { echo FAIL_CITABLE_LEAK; exit 1; }; echo CITABLE_CLEAN   # a PRÓPRIA CITABLE_FORBIDDEN_PATTERNS (Task 02), nunca regex copiada
   ```
4. *Leitura humana mínima (sem decidir nada):* abrir cada PDF e conferir só forma
   (sem colisão de rótulos, uma página, rótulo de estatuto visível, frases do I11) —
   checagem de layout da skill `dataviz` passo 7; colisão → ajuste de estilo no
   renderer é mudança de `src/` → linha `FAIL_LAYOUT` da tabela.
5. *Commit das saídas* — `git add` **só** dos 22 caminhos de `written.txt` e do
   `technical.md` (`docs/reports/figures/`, os dois dossiês, §7 com a
   `[measurement]` da R2: `gen1.out`, `out-gen1.sha256sum`, `DATA_INTACT`, estado do
   container, `IMAGE_ID`, `CODE_SRC`):
   `docs(evaluation): figuras canônicas e dossiê final gerados da cópia julgada [8.3/--]`.

**R3 — Segunda geração depois do commit (I8).** Bloco R1; depois a geração 2 como
na R2 item 2 (`ff83-gen2`), e:
```bash
set -eu; SCRATCH=<…>; . "$SCRATCH/etapa-83.env" || exit 1
(cd "$WTH/docs/reports" && sha256sum figures/*.pdf figures/*.json final_traceability_dossier.md final_traceability_dossier_internal.md) > "$SCRATCH/out-gen2.sha256sum" || { echo FAIL_GEN2_OUTPUT_MISSING; exit 1; }
diff -q "$SCRATCH/out-gen1.sha256sum" "$SCRATCH/out-gen2.sha256sum" || { echo FAIL_NOT_DETERMINISTIC; exit 1; }; echo SAME_SHA256SUM
test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_REGEN_DIFFERS_FROM_COMMIT; exit 1; }; echo REGEN_EQUALS_COMMIT
(cd "$LIVE" && find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum) > "$SCRATCH/live-after2.sha256sum"
diff -q "$SCRATCH/live-before.sha256sum" "$SCRATCH/live-after2.sha256sum" || { echo FAIL_DATA_CHANGED; exit 1; }; echo DATA_INTACT
```

**R4 — Registro.** `[measurement]` em §7 com as saídas literais da R3 (as duas
listagens, `SAME_SHA256SUM`, `REGEN_EQUALS_COMMIT`, `DATA_INTACT`; a consistência do
sharpness com o `mpiw` vale porque a geração não ergueu `ReportSourceMismatchError`),
commit `docs(evaluation): determinismo e só leitura da geração real registrados [8.3/--]`,
depois o 2º `make check` (saída).

**Descartar saída não commitada (DESCARTE)** — toda linha pós-geração abaixo que manda
"descartar" usa este bloco (GB-1), depois de gravar logs e estado:
```bash
set -eu; SCRATCH=<…>; . "$SCRATCH/etapa-83.env" || exit 1
git -C "$WTH" checkout -- docs/reports
git -C "$WTH" clean -fdx -- docs/reports/figures docs/reports/final_traceability_dossier.md docs/reports/final_traceability_dossier_internal.md docs/reports/.report-artifacts-staging docs/reports/.report-artifacts-previous
test -z "$(git -C "$WTH" status --porcelain)" || { echo FAIL_DISCARD; exit 1; }; echo DISCARDED
```

**Se falhar.**

| Linha | Sintoma | Ação |
|---|---|---|
| `FAIL_IMAGE_ID`/`FAIL_GATE1` | R0 sem id de imagem ou `GATE1` inexistente | corrigir o env file; nada rodou |
| `FAIL_WT_DIRTY`/`FAIL_REGISTER_NOT_COMMITTED` | árvore suja (inclusive saída parcial anterior) ou registro fora do commit | DESCARTE para saída parcial; registro → commit dele (linha do registro abaixo) |
| `FAIL_CONTAINER_EXISTS` | `ff83-*` de tentativa anterior (parado ou vivo) | `docker logs`/`docker inspect` gravados no scratch, `docker rm -f`, repetir o passo |
| exit 2 `DirtyCodeError` | probe viu árvore suja | DESCARTE / commit pendente; repetir sem gate |
| exit 2 `MissingImageIdError` | `IMAGE_ID` não chegou ao container | corrigir `ENVS`; repetir sem gate |
| exit 2 `ReportArtifactsError` | sem `.judged.toml`, scorecard ou `input_read` | parar; `[finding]` (a cópia julgada não é a esperada) |
| exit 2 `ValueError` do parser | registro curado malformado ou ponteiro proibido | corrigir `dossier_register.toml`, T1 de `tests/architecture/test_stage_8_3_repo_files.py`, commit `docs(evaluation)`, R1 (o `GATE1` continua: o registro está fora do diff da R1) |
| registro curado muda **depois** da R2 (qualquer motivo) | o dossiê commitado deixa de corresponder ao registro | `GATE1` continua, mas **refazer R1–R4**: regenerar e commitar os artefatos num commit **novo** (nunca amend); só mudança em §7 ou no roadmap dispensa regenerar (N2) |
| `FAIL_DISCARD` | o DESCARTE não deixou a árvore limpa (arquivo fora dos caminhos de saída) | parar; listar `git status --porcelain`; nada fora de `docs/reports/` gerado pela Etapa é apagado sem decisão do coordenador |
| `FAIL_OUTPUT_MISSING`/`FAIL_GEN2_OUTPUT_MISSING` | `sha256sum` sem algum dos 22 arquivos | parar; DESCARTE; tratar como `FAIL_GEN1_FIGURES` (saída incompleta) |
| `FAIL_GEN1_FIGURES`/`FAIL_OUTPUT_COUNT`/`FAIL_UNEXPECTED_PATHS`/`FAIL_CODE_SRC` | saída incompleta, caminho inesperado ou registro com outro `code.src` | parar; DESCARTE; defeito de `src/` → linha `FAIL_SRC_CHANGED_SINCE_GATE1` |
| `FAIL_GEN2_*` (mesmas checagens na geração 2) | falha só na 2ª geração | parar; não commitar nada da 2ª; DESCARTE das mudanças (o commit da 1ª fica) e diagnóstico como `FAIL_NOT_DETERMINISTIC` |
| `FAIL_SRC_CHANGED_SINCE_GATE1` | `src/`/lock/`.importlinter` mudou depois do ponto 1 | revisão independente do fix + novo `make check` + `GATE1` novo; recomeçar da R1 |
| `FAIL_JUDGED_COPY`/`FAIL_DIGEST`/`FAIL_RECORD` | cópia julgada adulterada ou registro divergente | parar; `[finding]`; restauração só pelo backup conferido (`sha256sum -c`, ADR 8.1.0003 item 7) com decisão do coordenador |
| `FAIL_GEN1` com `SilverContentMismatchError` | unidade lida ≠ julgada | parar; diagnóstico só por chaves e hashes (nenhum valor): unidades lidas × esperadas por par (lição E4 da 8.2) — defeito do leitor é `fix` + gate; silver alterado é `[finding]` |
| `FAIL_GEN1` com `ReportSourceMismatchError` | DM gold ≠ scorecard, `n_evaluated` ≠ `n_observed`, larguras ≠ `mpiw`, filtro do gate ≠ H1, seeds | parar; `[finding]` com a chave; nenhuma figura é ajustada para "passar" (I3); correção de código passa pela linha 1 |
| `FAIL_GEN1` por escrita em `/data` (FS só leitura) | o wiring cria arquivo sob o `data_root` | `[deviation]`: montar `/data` rw; `DATA_INTACT` continua obrigatório (a listagem prova o só leitura) |
| `FAIL_GEN1` OOM | memória | registrar; `docker stats`; ler por `feature_set_name` já é o desenho; não aumentar `--memory` sem `[deviation]` |
| `FAIL_LAYOUT` | colisão de rótulo, página a mais | DESCARTE; ajuste no renderer = `src/` → linha `FAIL_SRC_CHANGED_SINCE_GATE1` |
| `FAIL_CITABLE_LEAK` | termo proibido no citável | DESCARTE; defeito do registro → linha do parser acima (T1 do teste do arquivo + commit, sem `make check`); defeito do Markdown (`src/`) → linha `FAIL_SRC_CHANGED_SINCE_GATE1`; regenerar |
| `FAIL_NOT_DETERMINISTIC`/`FAIL_REGEN_DIFFERS_FROM_COMMIT` | bytes diferentes entre gerações | parar; diagnóstico: PDF (fonte/subset, ordem de objetos) × registro × dossiê pelo `diff` das listagens; `[finding]`; nunca commitar a 2ª geração por cima |
| `FAIL_DATA_CHANGED` | `data/` mudou | parar; `[finding]`; nada é commitado |

## 3. Gate de saída da Stage

### Verificações automatizadas

Tudo no container (ADR 0.0.0059):
```bash
make check PYTEST_PAR='-n 4 --dist loadgroup'   # ponto 2 (comando literal do §1); cobertura por arquivo
                                                 # lida da tabela term-missing desta MESMA saída
                                                 # (cada arquivo de src/ tocado >= 90 %)
git diff --exit-code origin/develop...HEAD -- scripts/arch_baseline.toml   # nenhuma entrada nova de baseline
python scripts/check_technical_postexec.py docs/stages/8.3-plots-and-final-report/technical.md
```

### Verificações funcionais
- [ ] R2: `JUDGED_COPY_OK`, `DIGEST_OK`, `RECORD_OK`, geração 1 exit 0 com 10 linhas
      `figure`, `OUTPUT_22`, `DATA_INTACT`, `ONLY_REPORTS_WRITTEN`, `RECORDS_CODE_SRC`,
      `CITABLE_CLEAN`; artefatos commitados.
- [ ] R3: `SAME_SHA256SUM`, `REGEN_EQUALS_COMMIT`, `DATA_INTACT` (saídas literais em §7).
- [ ] O dossiê citável aponta cada figura e cada afirmação do veredito ao dado
      persistido; o interno lista os itens do A17.

### Checklist de fechamento
- [ ] 15 Tasks commitadas, cada uma com o seu T1 verde; Checkpoints C nas fronteiras
      do §4 com disposições registradas
- [ ] Auditoria de testes com mutação real **antes do ponto 1** (funções críticas:
      `_check_units` do silver, seleção do DM + conferência com o scorecard, rótulo por
      `h1.passed`, `DossierEntry` (ponteiro proibido) e a troca do sink), saídas em §7
- [ ] Dois `make check` do plano verdes (três se o ponto 1 precisou de `fix`), saídas
      coladas no relatório
- [ ] `docs/roadmap.md`: 8.3 `done`, `updated_at` e `last_reviewed_at` de hoje, linha
      no Histórico; commit `stage 8.3: complete`
- [ ] ADRs 8.3.0001–0004 `accepted` (e os `8_3_0005+` se houver)
- [ ] PR contra `develop` com `Closes #234`
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
01 ─► 02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10 ─► 11 ─► 12 ─► 13 ─► 14 ─► 15 ─[make check 1]─► R0..R4 ─[make check 2]
```

- 01 antes de 11 (o contrato existe antes do primeiro import; a 11 só acrescenta o
  `ignore_imports`); 02 antes de tudo que constrói specs/registros/entradas; 03 antes
  de 06–07 (colunas lidas por nome); 04 antes de 10 (fakes) e de 11–12 (contratos);
  05 antes de 08 (silver verificado); 06–08 antes de 09 (registros das figuras) e de 11
  (smoke usa as specs); 09 antes de 10; 10 antes de 13; 11–13 antes de 14; 13 antes de
  15 (o teste do arquivo usa o parser); 15 antes da R (o registro commitado é entrada).
- **Checkpoint C** (revisão do bloco por subagente, sem gate de suíte) depois de 04,
  08, 10, 13 e 15; a **auditoria de testes** com mutação real fecha antes do ponto 1.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| PDF varia entre processos (subset de fonte, ordem de objetos, id) apesar de `CreationDate None` e fonttype 42 | o contrato com `PYTHONHASHSEED` diferentes pega na Task 11; diagnosticar o objeto que varia (diff dos bytes descomprimidos) e fixar o parâmetro do backend; sem solução no backend → ADR `8_3_0005` (decisão E/C com fonte do matplotlib) antes de seguir |
| `uv lock` mexe em outra versão além do `requires-dist` | reverter, `uv lock --upgrade-package matplotlib` não; registrar e travar a versão existente; `[deviation]` com o diff |
| `SeriesAssembly` recusa o silver do cohort (achado de alinhamento) | não acontece se o refresh passou com o mesmo silver; acontecendo, é `[finding]` (o silver não é o julgado) — a conferência por unidade já teria recusado antes |
| Igualdade exata larguras × `mpiw` falha por ordem de soma | a conta é a mesma do `_pair_coverage` (mesma função de larguras e `math.fsum`); se ainda divergir, comparar a série (`n_points`) antes de qualquer tolerância; tolerância só com `[decision:E]` |
| `MPLCONFIGDIR` não gravável no container | `-e MPLCONFIGDIR=/tmp/mpl` nos comandos (já no §1); o adapter não depende de cache de fonte persistido |
| `node` ausente no host para o `validate_palette.js` | rodar o validador como `<script type="module">` numa página local (modo da skill) e colar o `console.table`; sem nenhum dos dois, `[finding]` e paleta mantida só com marcador/estilo como identidade secundária |
| Wiring completo (`wire_dependencies`) escreve sob `/data` montado `:ro` | linha da tabela "Se falhar" (`[deviation]`, montar rw, `DATA_INTACT` obrigatório) |
| Repositório git no mundo sintético inviável na Task 14 | fallback declarado na própria Task (`report_artifacts_wiring` + ambiente fake), `[deviation]` |
| Memória ao ler o silver inteiro | o refresh lê o mesmo volume em `--memory 8g`; leitura por `feature_set_name` |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs
  [8.3.0001](../../adr/8_3_0001-full-figure-catalog-and-dm-candidate-versus-comparators.md),
  [8.3.0002](../../adr/8_3_0002-figure-provenance-by-data-digest-and-verified-silver-units.md),
  [8.3.0003](../../adr/8_3_0003-deterministic-vector-pdf-with-matplotlib-in-docs-reports-figures.md),
  [8.3.0004](../../adr/8_3_0004-dossier-generated-from-persisted-sources-plus-curated-register.md);
  consumidos: 0.0.0011, 0.0.0059, 6.5.0003, 6.5.0005, 6.5.0006, 6.5.0010, 8.1.0002–8.1.0004, 8.2.0002
- Doc de domínio [`reproduction-equivalence-and-reporting`](../../domain/evaluation/reproduction-equivalence-and-reporting.md) §2.3, §6, §7, §8.2
- Technical [8.1](../8.1-confirmatory-run/technical.md) e [8.2](../8.2-equivalence-audit/technical.md)
  (modelo da etapa real, §7: finding do `PYTEST_PAR`, E4 do andaime, fix depois de gate)
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §8; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3; [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) Passos 6–10 e §Gates em camadas
- Skills: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`,
  `composition-root`, `import-linter-rules`, `architecture-fitness`, `dataviz`
- Issue [#234](https://github.com/MarceloSanC/financial-forecasting/issues/234)

### Matriz de rastreabilidade (concept §11 → Task → teste/evidência)

| # | Critério | Task(s)/Etapa | Teste / evidência |
|---|---|---|---|
| A1 | Catálogo (10 specs, painéis, DM só candidato × família) | 02, 06–08, 10 | `test_catalog_has_the_ten_ids_in_doc_order`; `test_one_panel_per_horizon_never_mixed`; `test_cells_are_horizon_by_family_comparator_only`; `test_h1_h7_side_by_side_and_comparison_panel`; `test_single_horizon_invariant_panel_with_note`; `test_ten_figures_in_catalog_order_and_one_write` |
| A2 | Fonte única (nunca `current/`) | 10, 14 | `test_specs_come_from_judged_copy_never_current` (construtor sem `GoldGenerationReader`); e2e sobre o mundo julgado |
| A3 | Cópia conferida, sem escrita | 10, 14 | `test_record_digest_other_than_find_raises_tampered`, `test_missing_copy_raises_not_found`, `test_tampered_copy_propagates`; `test_tampered_judged_copy_exit_2_nothing_written`, `test_judged_toml_with_other_digest_exit_2_nothing_written` |
| A4 | Silver por unidade | 05, 10 | `test_report_silver.py` (calib alterada, falta, sobra, realizado, ablação e permutadas/VSN só no julgado passam); `test_silver_mismatch_writes_nothing` |
| A5 | Rótulos e frases | 02, 06, 07, 10 | `test_confirmatory_label_only_on_gate_tails_and_dm_rows_where_h1_passes` (as dez specs); `test_confirmatory_only_where_h1_passes`; `test_row_label_h2_not_applicable_where_h1_fails`; `test_spec_rejects_missing_required_note[*]`; `test_every_panel_has_empirical_coverage_label` |
| A6 | Nenhum teste novo | 06, 07 | `test_report_figures_imports_no_inferential_service` (AST); `test_confirmatory_tails_equal_verdict_h1_bands_and_profile_power`; `test_raw_p_from_rectangular_row_not_bartlett`; `test_adjusted_and_rejected_divergent_from_scorecard_raises` |
| A7 | Dado plotado (fakes discriminantes) | 06–08 | testes das três suítes `test_report_figures_*` (inclusive D14 nos dois lados, `mean_of_drawn_widths_equals_gold_mpiw_model_full_exactly`, `n_evaluated_differs_from_n_observed_raises`, agregado de H3, VSN `family`) |
| A8 | Fan chart | 08 | `test_uses_first_seed_of_revision_only`, `test_cohort_seeds_differ_from_revision_raises`, `test_first_seed_without_predictions_raises_no_fallback`, `test_legend_names_the_seed` |
| A9 | Renderer determinístico | 04, 11 | `test_figure_renderer_contract.py` (`[fake, real]`; subprocessos com `PYTHONHASHSEED`; `%PDF`; sem `/CreationDate`; `identity`) |
| A10 | Smoke de geração | 11 | `test_ten_synthetic_specs_render_one_page_each` |
| A11 | Registro por figura | 02, 10, 12, 14, R | `test_record_as_mapping_fields_and_no_commit_or_time`; `test_records_carry_data_digest_generation_digest_code_and_renderer`; `test_record_bytes_are_document_bytes`; `test_record_data_digest_matches_spec_and_lists_silver_units`; `RECORDS_CODE_SRC` |
| A12 | Dossiê citável completo | 02, 09, 15 | `test_dossier_sections_closed`; `test_report_dossier.py` (seções, cegamento byte a byte, poder, ponteiros, reprodução); `test_register_has_inherited_citable_items`; `[measurement]` da varredura de `[finding]` abertos |
| A13 | Recusas do CLI e do gerador | 10, 12, 13, 14 | `test_dirty_tree_raises_before_any_read_or_write`; `test_malformed_register_exits_2_before_use_case`; `test_failure_midway_restores_previous_and_removes_staging` |
| A14 | Execução real | 14, R | e2e sintético (bytes iguais, `data/` intacto); R2/R3: `OUTPUT_22`, `SAME_SHA256SUM`, `REGEN_EQUALS_COMMIT`, `DATA_INTACT` e o sharpness sem `ReportSourceMismatchError` |
| A15 | Dependência e gates | 01, 11, 12, pontos 1–2 | `lint-imports`; casos `evaluation-no-matplotlib-leak:toml-adapter-imports-matplotlib` (01) e `:reports-adapter-imports-matplotlib` (12); `test_no_pyplot_anywhere_in_src`; `make check` |
| A16 | Omissões fechadas | 02, 06, 07 | `test_catalog_omissions_equal_concept_d13_literal`; `test_spec_rejects_omission_outside_catalog`; `test_omissions_equal_catalog_and_no_series_draws_omitted_element`; `test_acf_band_absent`; `test_no_if_or_sf_interval_drawn` |
| A17 | Citável limpo, interno completo | 02, 09, 13, 14, 15, R | `test_non_internal_entry_with_forbidden_pointer_rejected[*]`; `test_citable_anchors_of_82_pass_the_second_barrier` (refinamento §1); `test_non_internal_forbidden_pointer_raises`; `test_citable_text_free_of_prior_evidence_terms`; `test_internal_lists_required_items`; `test_register_has_inherited_internal_items`; `CITABLE_CLEAN` |

### Verificação de gap no concept (uma passada, Fase 3B)

- **Critério sem Task?** Nenhum: A1–A17 mapeiam acima.
- **Contrato contradito?** Três refinamentos de forma, sem mudar fronteira nem critério:
  (a) o comando **não** leva a partição — sai do plano resolvido, como no
  `AuditReproduction` (mais forte que um argumento); (b) o comando leva
  `cohort_seeds` (o I6 exige comparar a lista do arquivo de cohort, e o use case não
  tem port para ler o cohort — a leitura fica no CLI, fronteira); (c) o subcomando
  ganha `--data-root`, `--cohort`, `--preregistration`, `--revision` além dos três do
  concept (o probe do I10 usa o cohort; o silver vive na raiz); (d) A17 (2ª barreira):
  o termo `equivalence_audit` vale para o relatório `equivalence_audit.md`, não para o
  diretório `8.2-equivalence-audit/` das âncoras citáveis que o próprio A12/A17 exige
  (Checkpoint B CB-2); (e) D4: a contagem de degenerados vai para o registro no campo
  `excluded_degenerate` (CB-8). O Markdown do dossiê é
  renderizado por função pura da application que o sink chama — compatível com "o sink
  renderiza". Registrados aqui como `[decision:C]` de forma; não regridem o concept.
- **Decisão que pedia ADR?** Nenhuma: uso dos donos existentes (`SeriesAssembly`,
  `CoverageMetrics.interval_widths`, `document_bytes`, `SilverContentAccumulator`),
  extração de `judged_copy.py` sem mudança de comportamento e o filtro do gate amarrado
  ao H1 em tempo de execução cabem nos ADRs 8.3.0002–0004.
- **Errata menor do concept (não material):** o D3 cita `test_conformal_gold_builders.py:95`
  como comparação do `GOLD_CONFORMAL_COVERAGE`; a linha compara o
  `GOLD_CONFORMAL_CORRECTIONS.read_columns`. Nenhuma das duas tabelas é tocada (Task
  03 fixa as duas por teste).

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.
>
> **Regra de pergunta antes da nota.** Algo não previsto no Concept ou neste
> Technical → triagem `evidence-resolution` (E/C decide e registra; só P sobe ao
> humano), depois a entrada abaixo.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
  Inclui pergunta, opções, decisão, razão.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original; corpo
  diz o que mudou e por que ficou abaixo do threshold de perguntar.
- `[measurement]` — evidência que o plano manda colar aqui (tempo do
  ponta a ponta, saída de mutação obrigatória, prova manual, execução
  real, auditoria de testes), sem decisão nem desvio. Corpo:
  **Contexto:** que critério/Task pede a evidência; **Medição:** comando,
  ambiente e saída bruta; **Razão:** o que a evidência prova.

Vocabulário fechado (CONVENTIONS §3.4): `decision` (ou `decision:E` /
`decision:C`, skill `evidence-resolution` §5), `finding`, `deviation`,
`measurement`. Outra tag no cabeçalho de entrada é recusada por
`scripts/check_technical_postexec.py`.

### 2026-10-24 — [decision:C] Task 02, caixas do `SeriesSpec` com bigodes — Claude (executor)
**Contexto:** o §1 fixa os campos do `SeriesSpec` (`x`, `y`, `low`/`high`, `text`), e a
Task 08 manda as caixas do sharpness carregarem mínimo, quartis e máximo das larguras,
que o renderer desenha por `Axes.bxp` sem recalcular. Cinco estatísticas não cabem em
`y` + `low`/`high`.
**Pergunta:** onde moram o mínimo e o máximo de uma caixa?
**Opções:**
- A — uma segunda série `interval` só com os extremos.
- B — campos opcionais `whisker_low`/`whisker_high`, obrigatórios em `boxes` (com
  `y` = mediana, `low`/`high` = quartis) e proibidos nos demais tipos. ✅ recomendada
**Decisão:** B.
**Razão:** reversível barato (nada persistido antes da Etapa R); mantém uma caixa como
um elemento com um rótulo de estatuto, sem duas séries que o renderer teria de casar.

### 2026-10-24 — [decision:C] Task 02, forma do catálogo, das seções citáveis e das âncoras — Claude (executor)
**Contexto:** o §1 fecha as listas (`FIGURE_CATALOG`, `CITABLE_SECTIONS`,
`CITABLE_82_ANCHORS`), mas não escreve os ids das seções, a ordem nem a forma das
âncoras; a frase do conformal é exigida "em todo painel".
**Pergunta:** como escrever essas listas fechadas?
**Opções:**
- A — seções na ordem da tabela do doc §7; âncoras por título livre; frase de painel
  conferida só no teste da Task 06.
- B — seções `(id, título)` na ordem das camadas do D8 (do veredito para os detalhes,
  Sandve Rule 8); âncoras pelo slug do GitHub do cabeçalho da §7 da 8.2 (conferidas
  contra o arquivo nesta Task); campo `panel_note` no catálogo, que a `FigureSpec` exige
  no rótulo de todo painel; omissões do D13 literais sem a marcação Markdown (negrito e
  crase); a legenda do fan chart como modelo `{seed}` que casa um inteiro. ✅ recomendada
**Decisão:** B. Ids: `claim_pointers`, `declared_power`, `identity`,
`preregistration_chain`, `pre_anchor_computation`, `blinding_statement`,
`judged_generation`, `environment`, `code_commits`, `seeds`, `figures`, `reproduction`,
`deviations` (13) e `internal`.
**Razão:** reversível barato; o D8 é a âncora da ordem e o slug do GitHub é o que os
links do Markdown resolvem no repositório; exigir a frase na construção fecha o I11 no
tipo, como o §1 já faz com as omissões.

### 2026-10-24 — [decision:C] Task 06, forma das quatro figuras de calibração e cobertura — Claude (executor)
**Contexto:** o D13 fixa fontes e omissões, mas não a disposição das séries; o
`FigureAssembly` (§1, Task 08) já é preciso aqui, porque cada função devolve as
`SourceRef` que leu.
**Pergunta:** como dispor as séries sem cálculo novo?
**Opções:**
- A — um painel por horizonte em todas, misturando ĉ, PICP e MPIW no mesmo eixo do
  nativo × conformal.
- B — um painel por horizonte; no nativo × conformal, dois por horizonte (ĉ por cauda e
  PICP; MPIW), x categórico por cauda/par; seeds como uma série de pontos por modelo com
  o rótulo da seed em `text`; o poder declarado na nota do rótulo das caudas do gate;
  `FigureAssembly` introduzido já nesta Task (campos do silver vazios). ✅ recomendada
**Decisão:** B.
**Razão:** reversível barato; uma grandeza por eixo y (ADR 8.3.0003 item 4) e nenhum
número novo — só seleção, complemento e razão de contagens médias (I3).

### 2026-10-24 — [deviation] Task 09, 1ª barreira do A17 também no ponteiro de bloco citável — Claude (executor)
**Contexto:** o Checkpoint C do bloco 1 (CC1-1) pediu que a 1ª barreira valesse também para
`DossierBlock.pointer` em seção citável, não só para a `DossierEntry`.
**O que mudou:** `TraceabilityDossier.__post_init__` (`dtos/report_artifacts.py`, fora da
lista de arquivos da Task 09) recusa bloco de seção citável cujo ponteiro case
`is_forbidden_citable_pointer`; teste `test_citable_block_pointer_passes_the_first_barrier`.
**Razão:** abaixo do limiar de pergunta — pedido explícito do revisor, mesma regra e mesmo
dono da 1ª barreira, sem mudar contrato nem dado persistido.

### 2026-10-24 — [decision:C] Task 09, `result_digest` explícito e forma do Markdown — Claude (executor)
**Contexto:** o §1 dá `build_dossier(..., attempts, ...)`, mas o `result_digest` da última
`input_read` tem dono na Task 10 (`judged_copy.last_input_read_digest`); calcular de novo
no dossiê duplicaria a regra. O `blinding_statement` tem aspas, acento e quebra de linha,
que uma célula de tabela Markdown não transcreve byte a byte.
**Pergunta:** de onde vem o `result_digest` e como transcrever o texto literal?
**Opções:**
- A — o dossiê filtra as tentativas de novo; o texto vai à tabela com escapes.
- B — `build_dossier` recebe `result_digest` (o use case passa o do dono) e usa as
  tentativas só para a linha `started`; valor de várias linhas ou com `|` sai num bloco
  cercado literal, fora da tabela; o comando de regeneração é um bloco
  `REGENERATE_HEADING` de `code_commits` que o Markdown repete no topo. ✅ recomendada
**Decisão:** B.
**Razão:** reversível barato; dono único do `result_digest` (CB-5) e transcrição byte a
byte do D9.

### 2026-10-24 — [deviation] Task 10, `committed_records` e o mundo parametrizável — Claude (executor)
**Contexto:** o use case precisa do `JudgedRecord` da referência para o dossiê (commit,
tag, comentário), e o teste do use case precisa de uma cadeia r0-r3 com referências
**calculadas** e do `dataset_fingerprint` da grade sintética.
**O que mudou:** `judged_copy.committed_records(...)` (o filtro que `sealed_matching_record`
já fazia, agora público e dono único das duas chamadas); `_report_inputs.py` (fora da
lista da Task 10) ganhou `report_payload()` e os parâmetros `plan`/`reference` de
`make_world`, sem mudar o mundo padrão das Tasks 06-09.
**Razão:** abaixo do limiar de pergunta — mesma regra, sem cópia; helper de teste.

### 2026-10-24 — [measurement] Task 11, paleta fixa de modelos no validador da skill `dataviz` — Claude (executor)
**Contexto:** o §1 ("Renderer") manda validar o mapa modelo → cor pelo
`validate_palette.js --mode light` e colar a saída aqui.
**Medição:** host Windows, `node scripts/validate_palette.js
"#2a78d6,#eb6834,#1baf7a,#eda100,#e87ba4,#008300,#6250d6" --mode light` (as sete primeiras
cores da ordem categórica de `references/palette.md`, na ordem tft_quantile,
baseline_zero_return, baseline_historical_mean, baseline_ar1, baseline_ewma_vol,
baseline_historical_quantiles, gbm_quantile):
```
Palette (light, surface #fcfcfb, categorical): 7 slots
  [PASS] Lightness band         all 7 inside L 0.43–0.77
  [PASS] Chroma floor           all 7 >= 0.1
  [PASS] CVD separation         worst adjacent #eda100↔#1baf7a ΔE 9.1 (protan) · tritan 5.8
  [PASS] Normal-vision floor    worst adjacent #e87ba4↔#eda100 ΔE 19.6 (normal)
  [WARN] Contrast vs surface    below 3:1 — relief required (visible labels or table view): [["#1baf7a",2.74],["#eda100",2.11],["#e87ba4",2.62]]
  → ALL CHECKS PASS
```
**Razão:** o WARN de contraste é coberto pela codificação secundária do adapter (marcador e
estilo de linha fixos por modelo, legenda com o nome em toda figura): identidade nunca só
pela cor (ADR 8.3.0003 item 4).

### 2026-10-24 — [decision:C] Task 11, grade de painéis e legenda da figura — Claude (executor)
**Contexto:** o §1 diz "grade de painéis 1×n" em 6,3 in de largura; o d_t + ACF e o
nativo x conformal têm quatro painéis (≈1,5 in cada), e a legenda por eixo cobria os
pontos (conferido em pré-visualização PNG no scratchpad).
**Pergunta:** como dispor painéis e legenda sem perder legibilidade?
**Opções:**
- A — 1×n literal, legenda dentro de cada eixo.
- B — no máximo duas colunas (linhas extras quando n > 2) e uma legenda única da figura,
  entre os painéis e o rodapé de notas. ✅ recomendada
**Decisão:** B.
**Razão:** reversível barato (só desenho, os bytes do PDF não são prova de origem — o
`data_digest` é da spec); um eixo por painel continua valendo.

### 2026-10-24 — [deviation] Checkpoint C do bloco 2, CC2-1: caudas do gate H1 sempre confirmatórias — Claude (executor)
**Contexto:** a Task 06 (teste `test_confirmatory_only_where_h1_passes`) e o concept A5/I4
rotulavam as caudas do gate "descritivo (perfil)" onde H1 reprova. O doc de domínio
(reproduction §2.3 e §6.2), fonte superior, diz que o gate H1 (cada cauda, banda 97,5 %) é
confirmatório sem condição; "só onde H1 passa" vale para H2 (Holm/MCS), isto é, para a
linha do DM.
**O que mudou:** `report_figures._confirmatory_tails` rotula as duas caudas
`confirmatório` em todo horizonte, com o desfecho ("H1 passa/reprova em h+h") na nota;
o DM segue condicionado a `h1.passed`. Testes: `test_gate_tails_confirmatory_in_every_horizon`
e a lista de elementos confirmatórios do use case. O concept é emendado por outro agente.
**Razão:** correção de rótulo para a fonte superior, pedida pelo revisor; sem mudar dado
lido nem contrato de port.

### 2026-10-24 — [deviation] Task 14, mundo julgado da 8.1 refeito com `blinding_statement` — Claude (executor)
**Contexto:** a Task 14 pede o `_judged_world` de `test_run_confirmatory_evaluation.py`, mas
o plano sintético dele não tem `blinding_statement`, e o dossiê o transcreve (D9) — a
geração recusaria com `ReportSourceMismatchError`. O plano entra no hash, então o campo não
pode ser acrescentado depois.
**O que mudou:** `test_report_artifacts_cli.py` remonta o mesmo mundo com os mesmos helpers
(`_write_dataset`, `_plan_payload`, `_freeze`, `_write_silver`, `_write_attribution`,
`_write_ablation`, `_r3`, `_run`, `_record`), acrescentando o `blinding_statement` na r0
(herdado pelas emendas). O caminho é a CLI real (sem o fallback da Task); a raiz vira
repositório git com `config/` commitado.
**Razão:** abaixo do limiar de pergunta — helper de teste, mesmo mundo, só o campo que o
D9 exige.

### 2026-10-24 — [measurement] Task 15, varredura dos `[finding]` abertos (A12) — Claude (executor)
**Contexto:** a Task 15 e o A12 mandam varrer os `[finding]` do §7 dos technical das Stages
5.5, 6.x, 7.x, 8.1 e 8.2 parte (i) e registrar aberto × resolvido com a evidência; os
abertos entram no `docs/reports/dossier_register.toml` com `kind = "finding"`,
`status = "open"`.
**Medição:** `grep -n "^### .*\[finding"` nos §7 de `docs/stages/{5.5-*,6.*,7.*,8.1-*,8.2-*}/technical.md`
mais `grep -n "\[finding\]"` fora de cabeçalho (achados embutidos em outra entrada); cada
entrada lida inteira e cruzada com as entradas posteriores da mesma §7, a auditoria da
Stage, o `git log` e o estado das issues citadas (`gh issue view`, 2026-10-24). Duas
sondas no container (imagem `financial_forecasting-app:dev`, `uv run --no-sync mypy
--strict`): os três arquivos da entrada 8.1 Task 02 → `Found 1 error in 1 file`
(`test_h3_refresh_memory.py:351`); `test_refresh_gold_dtos.py` → `Found 28 errors in 1 file`.
Critério de resolução: entrada posterior (mesma §7 ou auditoria) que declara o conserto, ou
a própria entrada que registra a correção já aplicada, ou issue/commit/documento fechado
com ponteiro verificável. Resolução parcial conta como aberto. 7.1 e 6.6 não têm
`[finding]`. Contagem: 5.5 7 (1 aberto); 6.1 1 (0); 6.2 1 (0); 6.3 2 (0); 6.4 9 (0);
6.5 3 (1); 7.2 4 (0); 7.3 3 (0); 7.4 2 (0); 8.1 6 (2); 8.2 parte (i) 0. **Total 38, 4
abertos.**

| Stage | `[finding]` | status | evidência | ponteiro |
|---|---|---|---|---|
| 5.5 | Task 14, perda de early_stop do LightGBM não bit a bit | resolvido | entrada seguinte (correção do diagnóstico) a substitui | — |
| 5.5 | Task 14, correção do diagnóstico | resolvido | a própria entrada: `stable_objective` arredonda o objetivo a 12 dígitos (correção aplicada) | — |
| 5.5 | Task 28, hash do cohort `8` × `8.0` | resolvido | a própria entrada: `task-17-fix` em `CohortSpec.hash_payload` | — |
| 5.5 | Task 33, notícia depois do fechamento do último dia | resolvido | a própria entrada: folga de 14 dias + teste de regressão | — |
| 5.5 | Task 33, `materialize` não re-executável sobre bronze | resolvido | recusa é o comportamento certo; rollback e troubleshooting em `docs/runbooks/confirmatory-cohort-aapl.md` (l. 307, 315) | — |
| 5.5 | Task 34, sweep não retoma no meio do estudo | aberto | limitação declarada; nenhuma entrada posterior | `docs/stages/5.5-confirmatory-retrain/technical.md#2026-09-28--finding-task-34--sweep-interrompido-pelo-desligamento-do-host-não-retoma-no-meio-do-estudo--claude-opus-55` |
| 5.5 | A3 com os params congelados (embutido no `[measurement]` Task 34) | resolvido | a própria entrada: fixture na escala do fold 0, `4 passed` | — |
| 6.1 | A12, DoD da 6.1 depende da 5.5 em `develop` | resolvido | 5.5 mergeada; `docs/roadmap.md` l. 765 traz "métricas de **calibração**" | — |
| 6.2 | Task 03, `CoverageSeries` adota `_timestamps` | resolvido | `03a95907` (#118/task-02), issue #118 fechada | — |
| 6.3 | `CoverageSeries` adota `_horizon`/`_timestamps` | resolvido | `03a95907` (#118/task-02), issue #118 fechada | — |
| 6.3 | A10/C8, teste de proveniência da 6.2 ausente | resolvido | `[decision]` "A10/C8 fechado depois do merge da 6.2" da mesma §7 (l. 1873) | — |
| 6.4 | Checkpoint C bloco 1 (I3), tipo de `reps` | resolvido | `[decision]` Task 07 da mesma §7 (`parameters_owner_messages`) | — |
| 6.4 | Task 08, leitura do gold sem partição hive | resolvido | `[decision]` Task 12 (e2e lê com `hive_partitioning = false`) e `[deviation]` Task 13 da mesma §7; nota "Leitura do gold (nota da 6.4)" no roadmap §Stage 6.5 | — |
| 6.4 | Encaminhamentos do concept §7 para a 6.5/8.3 | resolvido | 6.5 `done`: o scorecard lê o gold e recebe `preregistration_ref` e parâmetros do plano (roadmap §Stage 6.5) | — |
| 6.4 | "int ≥ 0" `window_deficits` para a #118 | resolvido | #118 fechada; `series_assembly.py:314` usa `validate_int_at_least(..., minimum=0)` | — |
| 6.4 | Testes de log com logger desligado | resolvido | issue #125 fechada (import-linter em subprocess) | — |
| 6.4 | "int ≥ 0" `grid_trimmed_prefix` para a #118 | resolvido | #118 fechada; `quality_checks/registry.py:86` usa `validate_int_at_least` | — |
| 6.4 | Medição no cohort real: nada a encaminhar | resolvido | a própria entrada encerra sem pendência | — |
| 6.4 | Exposição de cegamento (B-ORDEM) | resolvido | decisão humana ADR 6.5.0010 P1 (vai ao registro como `pre_anchor`) | — |
| 6.4 | §3 "Resíduo herdado" | resolvido | a própria entrada: issue #123 / PR #124 | — |
| 6.5 | Checkpoint B r1 (T-F11), falsa reprovação ≈ 5 % | resolvido | entrada "Correção da faixa" da mesma §7; issue #131 fechada | — |
| 6.5 | Checkpoint C bloco 1 (A5), fronteira `lower == nominal` sem teste | aberto | encaminhado à "sessão mestra" no fechamento da 6.5; nenhum teste nem issue posterior | `docs/stages/6.5-preregistration-and-scorecard/technical.md#2026-09-30--finding-checkpoint-c-bloco-1-a5-fronteira-lower--nominal-do-wilsonband-sem-teste-na-63--claude-opus-55` |
| 6.5 | Correção da faixa da falsa reprovação (L1) | resolvido | espelho `docs/preregistration/aapl_confirmatory.md` l. 62–63 declara ≈ 5 % e 0,0506 em n = 1 512 | — |
| 7.2 | ambiente, versão do uv da imagem × CI | resolvido | issue #198 fechada | — |
| 7.2 | ambiente, 2 falhas fora do escopo no `make check` | resolvido | entrada posterior da mesma §7 (l. 1864–1867, "fecha sem ação") | — |
| 7.2 | tooling, `index.lock` velho | resolvido | issue #199 fechada | — |
| 7.2 | ponto B, `test_arch_check_changed` corre | resolvido | a própria entrada (fix `[7.2/--]`) e a rodada seguinte (l. 2015) | — |
| 7.3 | tooling, deriva do formatador | resolvido | issue #222 fechada (`15c0ed66` reformata com o ruff do venv; hooks pelo `uv run`) | — |
| 7.3 | tooling, correção do achado anterior | resolvido | issue #222 fechada (idem) | — |
| 7.3 | auditoria de testes da fase Windows | resolvido | a própria entrada: um commit por achado, mutantes mortos | — |
| 7.4 | mypy strict alcança `_gold_inputs.py` | resolvido | a própria entrada; issue #203 fechada | — |
| 7.4 | Checkpoint C3-4, numeração das skills `dmls-chNN` | resolvido | `[deviation]` F7 da auditoria (mesma §7) reclassifica como desvio aplicado (`59981a65`) | — |
| 8.1 | Task 02, erros de mypy pré-existentes em `tests/` | aberto | parcial: #204 cobriu `tests/contract`; segue 1 erro em `tests/integration` (sonda acima) | `docs/stages/8.1-confirmatory-run/technical.md#2026-10-22--finding-task-02--erros-de-mypy-pré-existentes-em-tests--claude-sessão-windows` |
| 8.1 | Task 08, erros de mypy em `test_refresh_gold_dtos.py` | aberto | `tests/unit` fora do escopo da #204; 28 erros (sonda acima) | `docs/stages/8.1-confirmatory-run/technical.md#2026-10-22--finding-task-08--erros-de-mypy-pré-existentes-em-test_refresh_gold_dtospy--claude-sessão-windows` |
| 8.1 | `PYTEST_PAR` por variável de ambiente não vale | resolvido | os technical seguintes passam o valor como argumento do make (8.2 §1 l. 301; 8.3 §1) | — |
| 8.1 | 3 falhas do 2º `make check` | resolvido | a própria entrada (`0fa4259`, `ea119d4`, `75374a5`) | — |
| 8.1 | Checkpoint C bloco 4 | resolvido | a própria entrada (`c21eaa14`, `5500ade4`) | — |
| 8.1 | auditoria, erratas O1/O2 e cobertura | resolvido | F1 corrigido (`9af1bbb3`, `062b8a8b`); O1/O2 entram no registro como `deviation` | — |

**Fora da varredura (8.2 parte (ii), tocam a evidência anterior → `internal`):** `[finding]`
E4 passo 1 do andaime (resolvido pelo `[deviation]` E4, `0e59b9f9`); `[finding]` D-M6
embutido no `[measurement]` E4 (resolvido pela emenda B3, ADR 8.2.0004); `[finding]` PICP
80 % embutido no `[measurement]` E4 refeita (sem resolução); `[finding]` erratas F2–F5 da
auditoria (F2 corrigido em `aad29ebc`, F5 sem dono). Todos entram no registro como
`internal`; a 8.2 parte (i) (E2/E3) não tem `[finding]`.
**Razão:** prova do A12 ("todo `[finding]` aberto da cadeia citável"); o teste
`test_every_open_finding_of_the_sweep_is_in_the_register` lê as linhas `aberto` desta tabela
e exige cada ponteiro no registro.

### 2026-10-24 — [deviation] Checkpoint C final (bloco 4), CC4-1..CC4-3 — Claude (executor)
**Contexto:** a revisão de `75fb57b6..5f70a5cf` não teve bloqueante; uma média e duas baixas
de código.
**O que mudou:**
- **CC4-1** (média, cobertura): o e2e `test_report_artifacts_cli.py` ganhou
  `test_revision_sha256_is_the_hash_of_each_committed_toml` (o sha256 de r0 a r3 no citável =
  `PreregistrationHash.compute` de cada TOML commitado, com o `CanonicalJsonHasher`; o prefixo
  de 12 é o sufixo da referência; a da r3 é a ref julgada) e
  `test_split_fingerprint_of_the_silver_reaches_the_citable_run_rows` (o `split_fingerprint`
  gravado no `dim_run` aparece na linha de cada run).
- **CC4-2** (baixa, contrato): `VerifiedSilver.split_fingerprints` sem default e com valor
  `str` (`dim_run.split_fingerprint` é `nullable=False`); linha do `dim_run` sem o campo →
  `ReportSourceMismatchError` antes do hash, e run sem fingerprint no `build_dossier` →
  `ReportSourceMismatchError` (nada de "—").
- **CC4-3** (baixa, regra duplicada): `JudgedRevision.digests` (o sha256 de cada revisão,
  calculado uma vez em `resolve_judged_revision`); o use case repassa `resolved.digests` em
  vez de recalcular o `PreregistrationHash`.
**Razão:** abaixo do limiar de pergunta — cobertura e dono único, sem mudar contrato de port
nem dado lido.

### 2026-10-24 — [deviation] Checkpoint C final (bloco 4), CC4-4: tags de cohort na Etapa R — Claude (executor)
**Contexto:** o CC4-4 (baixa, processo) apontou que a R1 não confere as tags `cohort/<id>`
que o dossiê cita (bloco "Tags do cohort"). O §2 é histórico aprovado e não muda; a
conferência entra aqui e é executada na R1 da Etapa R, logo depois de `REGISTER_COMMITTED`.
**O que muda (comandos literais, mesmo `$WTH` da R1):**
```
git -C "$WTH" rev-parse -q --verify "refs/tags/cohort/aapl_confirmatory-r0-665f45d9169a" >/dev/null || { echo FAIL_COHORT_TAG; exit 1; }; echo COHORT_TAG_OK
git -C "$WTH" rev-parse -q --verify "refs/tags/cohort/aapl_ablation-r0-8a2d1de2dd8c" >/dev/null || { echo FAIL_ABLATION_COHORT_TAG; exit 1; }; echo ABLATION_COHORT_TAG_OK
```
**Razão:** a tag é o que o dossiê aponta como âncora do cohort (convenção do freeze, ADR
5.5.0001); conferir que existe é uma linha a mais da R1, sem mudar a geração.

### 2026-10-24 — [measurement] auditoria de testes, mutação d1 do `blinding_statement` — Claude (executor)
**Contexto:** a auditoria de testes mostrou que a mutação d1 (`statement` →
`statement.strip()` na linha do bloco de cegamento, `report_dossier._blinding_blocks`)
**sobrevivia** (0 failed): o `BLINDING` dos testes não tem espaço nem LF nas pontas. Teste
novo `test_report_dossier.py::test_blinding_statement_keeps_edge_and_inner_whitespace`:
declaração com LF e espaços nas pontas e espaço duplo no meio; igualdade exata da linha e o
Markdown citável contém o texto byte a byte no bloco cercado (`**blinding_statement:**`,
abertura `text`, o texto, fechamento).
**Medição:** container `financial_forecasting-app:dev`, mutação aplicada por `sed` na árvore
e revertida por `git checkout --` em seguida:
```
# com a mutação d1
FAILED tests/unit/features/evaluation/test_report_dossier.py::test_blinding_statement_keeps_edge_and_inner_whitespace
1 failed, 20 passed, 1 warning in 10.25s
E       AssertionError: assert 'Declaração  ...egunda linha.' == '\n  Declaraç...da linha.  \n'
# revertida
21 passed, 1 warning in 3.00s
```
**Razão:** o D9 (transcrição byte a byte) passa a ter teste que mata a normalização de
espaço nas pontas; só o teste novo cai sob a mutação.

### 2026-10-24 — [finding] Etapa R, R2 geração 1: `mpiw` ausente no gold para os baselines pontuais — Claude (executor da Etapa R)
**Contexto:** R0 e R1 verdes (`IMAGE_ID_OK`, `GATE1_OK` com `GATE1 = d721c76c8f2b2065ec32ab58f166ff2c31021780`,
`WT_CLEAN`, `SRC_AS_GATE1`, `REGISTER_COMMITTED`, `COHORT_TAG_OK`, `ABLATION_COHORT_TAG_OK`,
`CODE_SRC = b786b7f0d7d9cff8c455a599c21cc89dfe51096a`); R2 item 1 verde (`JUDGED_COPY_OK`,
`DIGEST_OK`, `RECORD_OK`, 355 arquivos em `live-before.sha256sum`, `NO_FF83`). Imagem
`sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45`. A geração 1
(`ff83-gen1`) saiu com estado `2 false` (exit 2, sem OOM), e a saída inteira foi:
```
error: ReportSourceMismatchError: gold_metrics_by_run: expected one row for ['horizon', 'level_high', 'level_low', 'metric', 'model', 'sample', 'seed'] at model=baseline_historical_mean, seed=None, horizon=1, sample=model_full, metric=mpiw, found 0
```
Linha `FAIL_GEN1` com `ReportSourceMismatchError` da tabela "Se falhar": parada. DESCARTE →
`DISCARDED` (nada fora do lugar; a geração não escreveu nada, I9); `DATA_INTACT` (listagem
de `data/cohorts/aapl` igual à de antes). Nada commitado da geração.
**Diagnóstico (só chaves e contagens, nenhum valor):** sonda DuckDB no container (mesmo
`IMAGE_ID`, `/data` só leitura) sobre `judged/<REF>/generation/gold_metrics_by_run.parquet`:
linhas `mpiw`/`picp` existem para `baseline_ar1`, `baseline_ewma_vol`,
`baseline_historical_quantiles`, `gbm_quantile` (6 cada por amostra) e `tft_quantile` (60
cada), nas amostras `common` e `model_full`, pares (0,02; 0,98), (0,1; 0,9), (0,25; 0,75).
Para `baseline_historical_mean` e `baseline_zero_return` **não há nenhuma** linha `mpiw` nem
`picp`, em nenhuma amostra. As métricas desses dois são `coverage_n_evaluated`, `crps_q`,
`degeneracy_rate`, `guardrail_applied_rate`, `interval_score`, `interval_width`, `pinball` e
`pinball_grid_mean`. Ou seja, são os baselines pontuais com intervalo degenerado, e o gold
os grava sem métrica de cobertura. O lookup que falha é o `_verified_widths`
(`report_figures.py`, figura `sharpness`, `sample = GATE_SAMPLE = model_full`), que exige
uma linha `mpiw` para todo modelo do silver. O mundo sintético das Tasks 06–14 tem `mpiw`
para todos os modelos, e é por isso que o gate não pegou o caso.
**Direção sugerida:** é mudança de `src/` (linha `FAIL_SRC_CHANGED_SINCE_GATE1`), com revisão
independente, novo `make check` e `GATE1` novo; depois, recomeçar a Etapa R da R1. Pontos a
decidir no fix, que não são decididos aqui:
(a) o que a sharpness desenha para modelo sem `mpiw` no gold. Por exemplo, pular o modelo,
ou exigir que todas as larguras sejam degeneradas (lista vazia) e declarar isso na legenda e
em `excluded_degenerate`;
(b) conferir os outros lookups `mpiw`/`picp` por modelo (`picp_mpiw_figure`, o
nativo × conformal e a fonte da linha 1854) para o mesmo caso;
(c) um mundo sintético com um baseline pontual sem linhas `mpiw`/`picp`, num teste do use
case e no e2e.
Stage candidata: a própria 8.3 (fix antes do fechamento).
**Razão:** parada dura do runbook. Nenhuma figura é ajustada para "passar" (I3), e o
executor da Etapa R não altera `src/`.

### 2026-10-24 — [deviation] fix do achado da Etapa R: baselines pontuais omitidos e declarados nas figuras de intervalo — Claude (executor)
**Contexto:** o `[finding]` acima (R2 geração 1). Decisão da sessão mestra `[decision:C]`
(doc evaluation §6.6; o concept D13 é emendado por outro agente): nas figuras de intervalo,
modelo sem **nenhuma** linha `mpiw`/`picp` no gold é omitido, com a omissão declarada por
modelo na legenda e no registro; linha parcial continua erro (fail-closed).
**O que mudou (`040c4006`, `[8.3/task-08-fix]`):**
- `report_figures.point_forecast_models(inputs)`: os modelos do plano sem nenhuma linha de
  `gold_metrics_by_run` com `metric ∈ {picp, mpiw}`; candidato nessa lista →
  `ReportSourceMismatchError`. `omitted_model_note(model)` é a frase da legenda.
- **sharpness** e **PICP × MPIW** pulam esses modelos e põem uma nota por modelo nas notas da
  spec (entra no `data_digest`); `FigureAssembly.omitted_models` recusa omissão sem a sua nota
  (dono único da declaração). Os demais lookups por chave seguem iguais: modelo com alguma
  linha de intervalo e um par/amostra/seed faltando recusa pelo `_one`.
- **nativo × conformal**: só lê o candidato; candidato sem intervalo recusa (nada a omitir).
  A fonte `gold_metrics_by_run` do sharpness (filtro `sample`/`metric`) não muda.
- `FigureRecord.omitted_models` (obrigatório; `<id>.json` ganha a chave) e a linha
  "modelos omitidos (sem picp/mpiw no gold)" no bloco de cada figura do dossiê. A lista
  fechada `omissions` do catálogo (A16) não muda.
- Mundo sintético (`_report_inputs.POINT_FORECAST_MODELS`: `baseline_historical_mean` e
  `baseline_zero_return` sem `picp`/`mpiw`, como no gold real) e e2e (os dois baselines com
  grade de Dirac no silver: o refresh real não grava `picp`/`mpiw` deles; os registros do
  sharpness e do PICP × MPIW listam os dois e o dossiê citável traz a linha). Testes novos:
  omissão declarada (figuras, use case, e2e), parcial → erro (figuras e use case, nada
  escrito), candidato sem intervalo, omissão sem nota recusada, `omitted_models` no DTO.
**Mutações** (container, `report_figures.py` mutado e restaurado, `git diff` limpo depois):
```
== m1-picp-silent (pula o modelo sem nota nem omitted_models)
FAILED test_report_figures_calibration.py::test_picp_mpiw_omits_point_forecast_models_and_declares_them
FAILED test_generate_report_artifacts.py::test_point_forecast_models_omitted_and_declared_in_the_records
2 failed, 70 passed
== m2-sharp-silent (idem no sharpness)
FAILED test_report_figures_silver.py::test_point_forecast_model_omitted_and_declared
FAILED test_generate_report_artifacts.py::test_point_forecast_models_omitted_and_declared_in_the_records
2 failed, 70 passed
== m3-picp-partial (lookup que falha vira ponto pulado)
FAILED test_report_figures_calibration.py::test_picp_mpiw_partial_interval_rows_raise
FAILED test_report_figures_calibration.py::test_point_forecast_models_only_without_any_interval_row
FAILED test_generate_report_artifacts.py::test_partial_interval_rows_write_nothing
3 failed, 69 passed
== m4-partial-as-point (só mpiw common h+1 conta como "tem intervalo")
FAILED test_report_figures_calibration.py::test_point_forecast_models_only_without_any_interval_row
FAILED test_generate_report_artifacts.py::test_partial_interval_rows_write_nothing
2 failed, 70 passed
RESTORED True
```
T1: testes unit de evaluation e o contrato do sink 3160 passed; `tests/architecture` + e2e
`test_report_artifacts_cli.py` + `test_run_confirmatory_evaluation.py` 416 passed; ruff e
mypy de `src/` verdes.
**Razão:** decisão `[decision:C]` da sessão mestra aplicada sem afrouxar o fail-closed; a
mudança de `src/` pede revisão, `make check` e `GATE1` novos antes de recomeçar a Etapa R
da R1 (linha `FAIL_SRC_CHANGED_SINCE_GATE1`).

### 2026-10-24 — [measurement] Etapa R, novo `GATE1` depois do fix dos baselines pontuais — Claude (executor da Etapa R)
**Contexto:** a linha `FAIL_SRC_CHANGED_SINCE_GATE1` pede, antes de recomeçar a Etapa R da R1,
três coisas: revisão independente do fix, `make check` novo e `GATE1` novo.
**Medição:**
- Fix `040c4006`: revisão independente aprovada. Concept emendado em `fd3912f8`/`6effc3a9`/`272d5313`
  (regra BP no D13). A sessão mestra fez um ensaio no dado real, e ele passou: 22 saídas, 2ª
  geração idêntica, `find_forbidden` 0, `data/` intacto. O `omitted_models` foi
  `[baseline_zero_return, baseline_historical_mean]`, só em `picp_mpiw_plot` e `sharpness_diagram`.
  Esse ensaio foi descartado; nada dele foi commitado.
- `make check` em `357e6d145c261dda85fc56c294ff6f241cf9878a`: `9269 passed, 30 skipped`,
  cobertura 98,53 %, `EXIT=0` (log `make-check-83-1b.log` no scratchpad da sessão).
- `GATE1 := 357e6d145c261dda85fc56c294ff6f241cf9878a` no `etapa-83.env`, e o `CODE_SRC` anterior
  foi removido (a R1 grava o novo).
**Razão:** destrava a Etapa R a partir da R1 com o mesmo `IMAGE_ID`
(`sha256:b69a7620…8f45`). Este commit só toca o §7, fora do diff da R1.

### 2026-10-24 — [finding] Etapa R (2ª tentativa), R2 item 4: `FAIL_LAYOUT` em três figuras — Claude (executor da Etapa R)
**Contexto:** a Etapa R recomeçou da R1 com `GATE1 = 357e6d14…` e o mesmo `IMAGE_ID`. A R2
item 4 manda abrir cada PDF e conferir só a forma, sem decidir nada (skill `dataviz`, passo
7). Uma colisão ou um rótulo cortado cai na linha `FAIL_LAYOUT`: DESCARTE, e o ajuste do
renderer é mudança de `src/`.
**Medição:**
- **R1:** `WT_CLEAN`, `SRC_AS_GATE1`, `REGISTER_COMMITTED`, `COHORT_TAG_OK`, `ABLATION_COHORT_TAG_OK`,
  `CODE_SRC = 291175bb256c4f60f056758bcae59a52976e5af4`.
- **R2 item 1:** `JUDGED_COPY_OK`, `DIGEST_OK`, `RECORD_OK`, 355 arquivos, `NO_FF83`.
- **R2 item 2:** `gen1.state` = `0 false` e `GEN1_FIGURES_10`. O `gen1.out` tem 1 112 linhas; 1 100 são
  do `fontTools.subset`, e o arquivo completo fica no scratchpad. Estas são as linhas de contrato:
```
report aapl_confirmatory-r3-00fd83d9cd39: generation_digest 96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539 figures 10 register_entries 35
figure reliability_diagram data_digest 92320bf22151cd08c7484466bccff854f7034333089de0e84d5f692c400f3a51
figure quantile_score_plot data_digest 1dee7acefecc1df244b5e7c55c1b32a5ef0e5f97eb5796cf7a49af866beff11e
figure sharpness_diagram data_digest 9c3f327a5f93a0c9d2e6a29567da0655b552ed81250b261f01cd4cd25920ff06
figure picp_mpiw_plot data_digest bcfd53ece66a8e9d28a148a5c260a8239bc72e1657d792c5ed1fe309409bedcd
figure dm_candidate_vs_comparators data_digest 9d6d0dc210f0a770efc3bc3ac7a50915530862f4066cc293096c5cfed9c949a5
figure oos_fan_chart data_digest 88a6ede5a7e53ad7f129fc5e64f9fb6ad671d6474cd73ac71b9f447489a8c62d
figure loss_differential_acf data_digest 01443b683465d9360b5d32ac087b18d082ee9e530d73a5703ebbd7e751cf1b0a
figure h3_family_importance data_digest 07aec2dba5e26180acb7ae6aeb8abc9fb7ec66fbb56560bf8c1c38bf8875c386
figure vsn_weights data_digest 1574ad8ac24713c74c40f010ee85144d7c31eada8959c287b1d5a07f03f65bee
figure native_vs_conformal data_digest c75ad2eabf561bcd55d6d90627836ec6ff5eda84a6487d3f9c153290edeeeb8a
dossier citable final_traceability_dossier.md internal final_traceability_dossier_internal.md
```
- **R2 item 3:** `OUTPUT_22`, `DATA_INTACT`, `ONLY_REPORTS_WRITTEN`, `RECORDS_CODE_SRC`, `exit 0`/`HITS 0`/
  `CITABLE_CLEAN`. Os dez PDFs têm uma página cada e nenhum tem `/CreationDate`. `omitted_models` =
  `[baseline_zero_return, baseline_historical_mean]` só em `picp_mpiw_plot` e
  `sharpness_diagram`, e `[]` nas outras oito figuras.
- **R2 item 4 (forma):**
  - `sharpness_diagram`: a entrada da legenda do `tft_quantile` passa da borda direita da página
    ("…seed 10) [descritiv"). O rótulo de estatuto dessa série fica invisível, porque o texto
    lista as dez seeds empilhadas. O marcador do `baseline_ar1`, primeira entrada da legenda,
    também sai cortado na borda esquerda.
  - `dm_candidate_vs_comparators`: o rótulo do eixo x ("comparador") sai cortado na borda de
    baixo, e o tick "baseline_historical_quantiles", girado, colide com ele nos dois painéis.
  - `h3_family_importance`: o rótulo do eixo y do painel h+1 (`I_f(h)`) sai cortado na borda
    esquerda (só "_" aparece). Na legenda, os pares "I_f(h), permutation"/"I_f(h), loco" e
    "perfil por seed, permutation"/"s_f(h+1), permutation" têm o mesmo marcador e a mesma cor,
    sem diferença visível. A nota de leitura do H3 termina em "famílias concordantes =",
    sem valor depois do sinal.
  - Fora da linha `FAIL_LAYOUT`, só cosmético: `vsn_weights` repete a nota
    ("horizonte-invariante: horizonte-invariante").
  - As outras seis figuras não têm colisão nem corte visível.
- **Estabilização:** cópia das 22 saídas no scratchpad (`gen1-layout-fail/`, fora do repo).
  DESCARTE → `DISCARDED`; `DATA_INTACT` depois do descarte; `NO_FF83`. Nada da geração foi
  commitado.
- **Contagem do registro (pedido da sessão mestra):** `docs/reports/dossier_register.toml`
  tem 35 `[[entry]]` desde o único commit dele (`9376bf4c`). Por `kind`: 4 `deviation`,
  4 `environment`, 4 `finding`, 14 `internal`, 3 `pre_anchor`, 6 `reproduction` (soma 35). O
  parser reporta `register_entries 35`. Nenhum doc nem teste fixa 36, e
  `test_register_has_inherited_citable_items` (a lista fechada do A12) está verde no gate. O
  "36" do relato da Task 15 é erro de contagem do relato, não falta no registro; o registro
  não foi editado.
**Direção sugerida:** é ajuste do `MatplotlibFigureRenderer` (`src/`; linha
`FAIL_SRC_CHANGED_SINCE_GATE1`), com revisão, `make check` e `GATE1` novos e recomeço da R1.
Pontos a decidir no fix:
(a) quebra de linha ou redução do rótulo longo da legenda, e a caixa da legenda dentro da
página;
(b) espaço para o rótulo do eixo x abaixo dos ticks girados, e para o rótulo do eixo y;
(c) codificação distinta (marcador/cor/hachura) entre as séries do H3 que hoje coincidem;
(d) a nota "famílias concordantes =" vazia: conferir se é lista vazia no gold, que pede texto
explícito (por exemplo "nenhuma"), ou defeito de formatação. É conteúdo do use case, e não
foi lido valor para decidir.
Stage candidata: a própria 8.3, antes do fechamento.
**Razão:** parada dura da R2 item 4. A checagem de forma é o único gate dessas falhas: os
testes de smoke conferem página e bytes, não recorte de texto.

<!-- END: post-execution -->
