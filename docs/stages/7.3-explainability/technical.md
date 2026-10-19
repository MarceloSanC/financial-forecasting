---
title: Technical — Stage 7.3 — Explicabilidade para H3 (treino LOCO por configuração, device por instância, predições permutadas e VSN no silver, estatística de H3 no evaluation, rascunhos do cohort de ablação e da r3, handoff para o Linux)
description: Plano de execução da Stage 7.3 em 33 Tasks inside-out (1 Task = 1 commit) na fase Windows — VO de identidade da partição, subconjunto de famílias no TrainTft, device por instância e probe com GPU observada, spec e loader do cohort de ablação, executor compartilhado, RunAblationCohort, piloto, subcomandos de ablação, predição de atribuição no port do modeling, plano de permutação, duas tabelas silver, ports do consumidor e manifesto da atribuição, RunPermutationInference e subcomando attribute, H3Parameters e bloco [h3], reduções por run, AttributionAssembly, FamilyContribution com oráculo arch, ContributionAgreement e VsnSummary, integração no gold, rascunho da r3 e handoff — mais a Etapa W (attribute sobre os 60 runs reais, sem pontuar) e as Etapas L0–L8 da fase Linux
when-use: Consultar durante a Fase 4 da Stage 7.3 — no Windows (Tasks 01–33 e Etapa W) e no Linux (Etapas L0–L8, a partir da entrada [handoff] da §7); cada Task traz lista fechada de arquivos, testes a escrever primeiro, o gate da camada (T1/T2/T3), o critério do concept que cobre e a verificação
keywords: [technical, plano de execução, explainability, h3, permutation-importance, loco, ablation-cohort, vsn, family-partition-hash, device, rocm, attribute, refresh-gold, gold, preregistration, r3, handoff, port-coverage, import-linter, blinding, etapa-w]
status: done
created_at: 2026-10-18
updated_at: 2026-10-18
stage_id: 7.3-explainability
stage_title: Explicabilidade para H3
step_id: 7
step_title: Inferência, conformal, explicabilidade e API
depends_on: [7.1-inference-engine, 6.1-scoring-and-calibration-metrics, 7.2-conformal-cqr]
concept_ref: ./concept.md
issue_id: 186
branch: feat/186-7-3-explainability
tasks_count: 33
---

# Technical — Stage 7.3 — Explicabilidade para H3

> **Como usar este documento (para code assistant):**
> 1. Ler §1 inteiro antes da Task 01. A **premissa P1** (7.2 mergeada) e a
>    **verificação de gap contra a 7.2** (§1, "Preparação da Fase 4") vêm antes
>    de qualquer Task.
> 2. Executar as Tasks na ordem de §2. **1 Task = 1 commit.** A lista de
>    arquivos de cada Task é **fechada**: tocar arquivo fora dela = parar e
>    perguntar (RUNBOOK Passo 8, "Escopo estrito"). Arquivos `__init__.py`
>    marcados *(pacote)* não contam na contagem de arquivos (PIPELINE §4.3
>    item 2), mas estão na lista fechada.
> 3. Escrever primeiro os testes de "Testes primeiro" (vermelho), depois o
>    código (verde). O gate de commit é a camada indicada (T1/T2/T3,
>    [RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)).
> 4. Commit: `<type>(<escopo>): <descrição> [7.3/task-NN]`, body em bullets,
>    `Refs #186`, subject ≤ 100 caracteres, mensagem UTF-8 sem BOM por
>    `git commit -F` ([`CONVENTIONS.md`](../../CONVENTIONS.md) §4).
> 5. Algo não previsto em §1–§6, no concept ou nos ADRs → pausar, perguntar com
>    opções, registrar em §7. Nunca propagar em silêncio.
> 6. Fase Windows: Tasks 01–32 → **Etapa W** → auditoria de testes → Task 33
>    (handoff, PR aberto). Fase Linux: **Etapas L0–L8** (§2, "Fase Linux"), a
>    partir da entrada `[handoff]` da §7; o commit `stage 7.3: complete` e o
>    merge são da L8.
>
> **Stage = 1 branch, 1 PR** (ADR 7.3.0006): `feat/186-7-3-explainability`,
> worktree própria no Windows; checkout da mesma branch no Linux.
>
> **Cegamento (I9, inegociável).** Nenhuma Task, teste, script ou Etapa desta
> Stage calcula pinball, b̂, intervalo, participação ou leitura de H3 sobre
> linhas do cohort `aapl_confirmatory-r0-665f45d9169a` ou do cohort de ablação,
> e nenhum `RefreshGold` roda sobre dado real. A Etapa W, o piloto (L2) e o
> treino (L5) leem e gravam só predições, pesos, tempos e épocas. A primeira
> pontuação real é a da 8.1, depois da âncora da r3 (L7).

## 1. Contexto e estratégia de execução

### Resumo

O concept aprovado ([`concept.md`](./concept.md); ADRs
[7.3.0001](../../adr/7_3_0001-attribution-statistics-in-evaluation-gold-via-refresh-gold.md)–[7.3.0006](../../adr/7_3_0006-stage-split-windows-linux-with-in-repo-handoff.md))
pede, no **shared**, o VO de identidade `FamilyPartitionHash`; no **modeling**,
o treino por subconjunto de famílias (`excluded_family`, `model_version` por
configuração, corte do grid pelo conjunto completo), o device por instância do
`PfTftTrainer` com o probe observando GPU e HIP, o `AblationCohortSpec` que
referencia o confirmatório pelo hash, o executor `RunAblationCohort` sobre a
máquina extraída do `RunConfirmatoryCohort`, o piloto `MeasureAblationCost`, os
subcomandos `ablation-*`, e a predição de atribuição (identidade + permutadas +
VSN) pelo port `TftCheckpointPredictor` com o fornecedor
`PredictTftAttributionFromCheckpoints`; no **analytics_store**, as tabelas
`fact_permuted_predictions` e `fact_vsn_weights` e seus escritores; no
**inference**, o `FamilyPermutationPlan`, quatro ports do consumidor, o manifesto
JSON da atribuição, o `RunPermutationInference` e o subcomando `attribute`; no
**evaluation**, `H3Parameters` e o bloco `[h3]`, as reduções por run,
`AttributionAssembly`, `FamilyContribution`, `ContributionAgreement`,
`VsnSummary`, o `h3_parameters` do `RefreshParameters`, quatro tabelas gold e o
`RefreshGold` publicando H3. Fecham a fase Windows o rascunho da r3, a Etapa W e
o handoff; a fase Linux faz piloto, seeds, freeze e âncora do cohort de ablação,
treino, r3 ancorada, auditoria e merge.

### Estratégia (ordem e porquê)

TDD inside-out (skill `task-ordering-hex`), fornecedor antes do consumidor, por
slice:

1. **Identidade compartilhada primeiro (Task 01):** `FamilyPartitionHash` é usado
   pelo inference ao gravar e pelo evaluation ao conferir; sem ele nenhum dos
   dois fecha.
2. **Treino LOCO no modeling (Tasks 02–10):** subconjunto → device → probe → spec
   → loader e rascunho → extração do executor (refactor com a rede da 5.5) →
   `RunAblationCohort` → piloto → CLI e wiring.
3. **Predição de atribuição (Tasks 11–12):** a extensão do Protocol
   `TftCheckpointPredictor` obriga real, proxy lazy e fake no mesmo commit (skill
   `task-ordering-hex`, "EXTENDING an existing Protocol"); o fornecedor vem logo
   depois.
4. **Domain do inference e silver (Tasks 13–15):** plano de permutação; schemas;
   escritores (os reais dos ports do consumidor do inference).
5. **Inference de fora para dentro do use case (Tasks 16–20):** ports cujos reais
   já existem (sem baseline) → port do manifesto com o par do ADR 6.1.0005 →
   adapter que reverte o par → use case com as arestas de dados → wiring, CLI e
   ponta a ponta.
6. **Evaluation (Tasks 21–31):** VO e bloco `[h3]` → VOs de redução →
   montagem (com a aresta 7) → contribuição com oráculo → leitura e VSN →
   `RefreshParameters` → `H3Reports` → tabelas gold → `RefreshGold` → ponta a
   ponta e memória.
7. **Fecho Windows (Task 32, Etapa W, Task 33):** rascunho da r3; `attribute`
   sobre os 60 runs reais (só predições); handoff e PR.

**Exceções declaradas à regra 4 do PIPELINE §4.3 (port × adapter):**

- `AttributionManifest` (Task 17) nasce **sem** adapter real. A Task 17
  acrescenta a entrada temporária em `scripts/arch_baseline.toml`
  (`key = "AttributionManifest"`, `issue = 186`, `motivo` citando o
  [ADR 6.1.0005](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md))
  **e**, no mesmo commit, troca a lista literal de
  `test_real_repo_violations_are_exactly_the_declared_baseline` em
  `tests/architecture/test_port_coverage_gate.py` de `["Hasher"]` para
  `["AttributionManifest", "Hasher"]`, com comentário citando o ADR 6.1.0005. A
  Task 18 (adapter) reverte as duas edições. As duas Tasks são T3; os dois
  arquivos estão nas listas fechadas das duas. O gate da fase Windows e o de
  saída exigem o bloco `[port_coverage]` de `scripts/arch_baseline.toml` sem
  diferença contra `$BASE` (a única diferença aceita no arquivo é a remoção de
  `[schema_literals]` da Task 07, abaixo) e a lista literal de volta a `["Hasher"]`.
- `CheckpointAttributionPredictor`, `PermutedPredictionPersister` e
  `VsnWeightPersister` (Task 16) **não** precisam de baseline: os reais
  (`PredictTftAttributionFromCheckpoints`, Task 12; `PersistPermutedPredictions` e
  `PersistVsnWeights`, Task 15) já existem e são reconhecidos pela regra #93 do
  `check_port_coverage.py` (anotações textualmente iguais + contrato
  `[fake, real]` que importa os dois pelo nome).
- **Homônimos e port-coverage por `(slice, nome)`:** o gate é cego a slice; a
  Task 16 acrescenta `test_real_repo_attribution_ports_resolve` e a Task 18
  `test_real_repo_attribution_manifest_resolves`, ambos indexando por
  `_by_slice_and_name` (`("inference", <nome>)`). Nenhum port novo é homônimo de
  outro slice (conferido no teste: `("modeling", nome)` e `("evaluation", nome)`
  ausentes do inventário).
- `TftCheckpointPredictor` **não** é port novo: é extensão (Task 11), sem
  baseline; o real, o proxy lazy e o fake mudam no mesmo commit.
- **`[schema_literals]` (#159), Task 07:** o `load_training_grid` sai do
  `run_confirmatory_cohort.py`, que hoje redeclara `"processed"`/`"dataset_tft"` e
  está no baseline. O `cohort_unit_runner` **importa** as constantes de coordenada do
  `train_tft` (sem redeclarar o literal), e as duas entradas
  `run_confirmatory_cohort.py::"processed"` e `::"dataset_tft"` do baseline ficam mortas
  e saem na mesma Task (dívida reduzida, nunca aumentada). Por isso a Task 07 é T3 e
  tem `scripts/arch_baseline.toml` na lista fechada.
- **Diferença aceita no `scripts/arch_baseline.toml` contra `$BASE`** (§3 e gate da
  fase Windows): **só** a remoção dessas duas chaves de `[schema_literals]`. A entrada
  `[port_coverage]` das Tasks 17–18 tem de estar revertida. Conferência:
  `git -C "$WTH" diff "$BASE" -- scripts/arch_baseline.toml | grep -E '^[+-][^+-]'`
  mostra só linhas `-` do bloco dessas duas chaves.

**Tasks acima de 5 arquivos** (pacotes não contam; justificadas na própria Task):
10, 11, 14, 16, 19, 20, 23, 24, 27 e 29.

**Etapa W = execução real, não Task** (concept §1 item 10): não produz código; a
evidência vai para §7 num commit `docs(inference): evidência da Etapa W [7.3/--]`.
**Etapas L0–L8 = fase Linux, não Tasks** (ADR 7.3.0006 item 3): cada uma tem
comando, saída esperada e parada, e é copiada para a entrada `[handoff]` da §7
pela Task 33.

### Preparação da Fase 4 (antes da Task 01)

**P1 — 7.2 mergeada.** A Fase 4 só começa com a Stage 7.2 mergeada em `develop`
(r2 ancorada) e esta branch rebaseada sobre ela. Este technical referencia os
contratos da 7.2 **pelo technical da 7.2** (`feat/158-7-2-conformal-cqr`,
`docs/stages/7.2-conformal-cqr/technical.md` §1–§2), porque ainda não estão em
`develop` quando ele é escrito.

**Verificação de gap contra a 7.2 mergeada (uma passada, obrigatória).** No
início da Fase 4, o executor confere cada forma abaixo contra o código real; se
alguma mudou, registra `[deviation] gap-7.2` em §7 com a forma observada e a
consequência para as Tasks afetadas (sem mudar a lista fechada sem perguntar):

| Contrato da 7.2 consumido | Forma esperada (technical 7.2) | Tasks 7.3 afetadas |
|---|---|---|
| `inference/domain/services/reproduction_policy.py` | `STRICT`, `TOLERANCE`, `ReproductionMode`, `reproduction_mode(..., *, ignored_keys)`, `within_mode`, `ReproductionComparison`, `compare_reproduction` (stdlib) | 19 |
| `inference/domain/value_objects/` e `tests/unit/features/inference/domain/` | pacotes existentes | 13 |
| `evaluation/domain/services/series_assembly.py` | `RuleViolation(kind, detail)`, `duplicate_levels(...)`, `index_violations(...)`, `missing_levels(...)` | 24 |
| `evaluation/domain/value_objects/preregistration.py` | campo `conformal: ConformalParameters \| None`; chave em `_OPTIONAL_KEYS`; `as_payload` só com a chave presente | 22 |
| `config/preregistration/aapl_confirmatory-r2.toml` + `.anchor.toml` | r2 ancorada; `preregistration_ref` lido do arquivo | 22, 32 |
| `RefreshParameters.conformal_parameters`, `GoldInputs.conformal_reports`, `EMPTY_CONFORMAL_REPORTS` | campos obrigatórios; BLOCKED ⇒ vazio | 27, 28, 30 |
| `GOLD_SCHEMAS`/`CONFIRMATORY_TABLES` com 15 tabelas; 15 builders no composition root | conjuntos exatos em `test_refresh_gold_dtos.py` e `test_composition_root.py` | 29 |
| Padrão de infinito no gold | `null` + flag booleana no builder; `math.inf` no domain e nos DTOs | 29 |
| Helpers de teste | `tests/unit/features/evaluation/_preregistration_payload.py::r2_payload()`, `_conformal_parameters.py`, `gold/_cohort_factory.py`, `tests/contract/features/evaluation/_gold_inputs.py::completed_inputs()` | 22, 24, 28, 30, 31 |
| `.importlinter` / LAYOUT §7 | contrato `inference-no-mapie-leak`; **28** arestas de runtime | 19, 24 |
| `tests/architecture/test_port_coverage_gate.py` | lista literal de volta a `["Hasher"]` | 17, 18 |

Comando e saída esperada por linha (qualquer outra saída ⇒ `[deviation] gap-7.2`):

```bash
S="$WTH/src/financial_forecasting/features"
grep -cE "^def (reproduction_mode|within_mode|compare_reproduction)|^class (ReproductionMode|ReproductionComparison)" "$S/inference/domain/services/reproduction_policy.py"   # 5
grep -rn "^class ReproductionError" "$S/inference"                  # 1 linha; o módulo dono é importado pela Task 19 (hoje: application/use_cases/run_inference.py)
test -f "$S/inference/domain/value_objects/__init__.py" && test -f "$WTH/tests/unit/features/inference/domain/__init__.py" && echo PKGS_OK   # PKGS_OK
grep -cE "^class RuleViolation|^def (duplicate_levels|index_violations|missing_levels)" "$S/evaluation/domain/services/series_assembly.py"   # 4
grep -c "conformal: ConformalParameters | None" "$S/evaluation/domain/value_objects/preregistration.py"   # 1
test -f "$WTH/config/preregistration/aapl_confirmatory-r2.toml" && test -f "$WTH/config/preregistration/aapl_confirmatory-r2.anchor.toml" && echo R2_OK   # R2_OK
grep -cE "conformal_parameters|conformal_reports|EMPTY_CONFORMAL_REPORTS" "$S/evaluation/application/dtos/refresh_gold.py"   # ≥ 3
grep -n '_timed("conformal"' "$S/evaluation/application/use_cases/refresh_gold.py"   # 1 linha; a etapa "h3" da Task 30 entra logo depois dela, com a mesma assinatura de _timed
grep -c "inference-no-mapie-leak" "$WTH/.importlinter"             # ≥ 1
grep -n "arestas de runtime" "$WTH/docs/LAYOUT.md"                 # "As 28 arestas de runtime"
grep -c 'violating == \["Hasher"\]' "$WTH/tests/architecture/test_port_coverage_gate.py"   # 1
grep -rlE "RefreshParameters\(" "$WTH/tests" | sort                  # = a lista de construções da Task 27
grep -rlE "GoldInputs\(" "$WTH/tests" | sort                         # conferida contra a lista da Task 28
```

**Ambiente:** esta Stage não muda `pyproject.toml` nem `uv.lock`, então não tem
volume próprio. Depois da 7.2 mergeada, `VENV=financial-forecasting_app-venv` (o
volume compartilhado), **sem** `uv sync` explícito nele: o primeiro `make` sincroniza
por `uv run`, em modo inexato. Conferência, colada no `[deviation] gap-7.2`:

1. `run sh -c "$PRE; uv lock --check"` → exit 0;
2. `run sh -c "$PRE; uv run python -c 'import torch, mapie; print(torch.__version__, mapie.__version__)'"`
   → `2.13.0+cpu 1.5.x`.

Volume próprio só se alguma Task passar a mudar o lock, e então com `[decision]` e o
padrão do ff72 da 7.2.

**Comandos no container.** Fluxo Docker-only; a worktree roda por `docker run`
avulso com os limites de recurso do projeto e a trava `ff-gate` (um gate por vez;
container alheio nunca é removido; um `ff-gate` parado pode sair com `docker rm`).
Git Bash:

```bash
WT=feat-186-7-3-explainability
WTH=/c/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
WTD=C:/Users/Marcelo/Documents/Code/financial-forecasting-worktrees/$WT
MAINH=/c/Users/Marcelo/Documents/Code/financial-forecasting
MAIND=C:/Users/Marcelo/Documents/Code/financial-forecasting
VENV=financial-forecasting_app-venv
# função, não string: o VENV é lido a cada chamada
run() {
  if [ -n "$(docker ps --filter name=ff-gate -q)" ]; then echo "ff-gate ocupado — esperar"; return 75; fi
  MSYS_NO_PATHCONV=1 docker run --name ff-gate --rm --cpus 6 --memory 8g --memory-swap 8g \
    -v "$WTD:/app" -v "$MAIND/.git:/main.git" -v "$VENV:/app/.venv" \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -w /app financial_forecasting-app:dev "$@"; }
PRE="git config --global --add safe.directory '*'"
PAR="PYTEST_PAR='-n 4 --dist loadgroup'"
BASE=$(git -C "$WTH" merge-base origin/develop HEAD)   # base de todo diff "contra o develop"
# uso: run sh -c "$PRE; make check-task SLICE=modeling $PAR"
#      run sh -c "$PRE; make check-task SLICE='modeling inference' $PAR"
```

Caminhos com barra normal (com `\` o bind mount sai vazio sem erro). Nos blocos de
verificação, as linhas `make …`/`uv run …` rodam dentro de `run sh -c "$PRE; …"`;
as linhas `git -C "$WTH" …`, `grep`, `test` e `python scripts/…` rodam no host.
**Dentro de `sh -c "…"` só aspas simples** (`SLICE='a b'`, `PYTEST_PAR='…'`): aspas
duplas internas fecham a string do host e derrubam o segundo slice e o
`PYTEST_PAR`. Todo diff "contra o develop" usa `$BASE`.

### Decisões de forma fixadas aqui (o concept deixou para a Fase 3B)

- **`FamilyPartitionHash`** (`shared/domain/value_objects/family_partition_hash.py`):
  `compute(*, hasher, feature_set_hash, partition) -> FamilyPartitionHash` com
  `value` (64 hex) = `hasher.hash_mapping({"feature_set_hash": h, "partition":
  {família: sorted(features)}})` — as features de cada família são ordenadas antes
  do hash (a troca conjunta não depende da ordem das colunas); as chaves de família
  são ordenadas pelo hasher canônico. Recusa (`ValueError` nomeando o campo):
  partição vazia, família vazia, feature repetida dentro ou entre famílias, texto
  vazio, `feature_set_hash` fora de 64 hex, e `value` fora de 64 hex na construção
  direta (`__post_init__`). O `feature_set_hash` passado vem **sempre** de
  `spec.feature_set_hash` (do `CohortSpec` confirmatório; no rascunho da r3, o literal
  `7df0e1b4…`), nunca recalculado pelo chamador.
- **Invariantes nos VOs novos de `domain/value_objects`** (Tasks 01, 13, 21, 23, 24):
  todo VO valida as suas invariantes no `__post_init__`, e cada Task tem um teste de
  **construção crua recusada** (o construtor chamado direto, sem a fábrica, com valor
  inválido ⇒ `ValueError`). O `CohortHash` não valida o próprio `value` (dívida #160) e
  **não** é o padrão a copiar.
- **Famílias e partição da registry** (modeling, `train_tft.py`):
  `TFT_FAMILIES: Final = ("price", "technical", "sentiment", "fundamental")` (ordem
  do ADR 0.0.0016); `registry_family_partition() -> Mapping[str, tuple[str, ...]]`
  (por `spec.family` da registry habilitada, na ordem da registry);
  `tft_feature_set_hash(excluded_family: str | None) -> str` (=
  `feature_set_hash()` quando `None`; senão o hash das specs sem a família);
  `loco_model_version(configuration: str) -> str` = `"tft_quantile_loco_" +
  configuration`.
- **`FamilyFeatureKnownError`** mora no módulo do port
  `modeling/application/ports/out/tft_checkpoint_predictor.py` (ao lado de
  `ArtifactChangedError`): quem o ergue de fato é o adapter, que vê o
  `dataset_parameters` do checkpoint; o fornecedor `PredictTftAttributionFromCheckpoints`
  importa-o de lá, faz a pré-checagem contra a tipagem do painel e propaga o do
  adapter. O nome e a semântica são os do concept §4 (C5).
- **`PredictTftAttributionCommand.family_partition: Mapping[str, tuple[str, ...]]`**
  é campo do comando do fornecedor (o concept §4 o omitiu da forma ilustrativa; o
  ADR 7.3.0002 item 1 exige "the command's family partition must equal the
  registry's"). O `RunPermutationInference` repassa o seu.
- **Constantes do plano** (`inference/domain/value_objects/permutation_plan.py`):
  `PERMUTATION_ALGORITHM = "fisher_yates_random_random_v1"`, `PERMUTATION_SEED = 130`,
  `K_P = 10`. O CLI `attribute` não expõe semente nem K_p: usa as constantes. A
  duplicação com o catálogo do evaluation é travada pelo teste de integração da
  Task 21 e pelo da r3 (Task 32) — I17.
- **Troca no tensor:** os blocos doadores são extraídos de uma passagem prévia do
  dataloader de identidade (amostra de decodificador mais longo por decisão, pela
  mesma seleção do `_emit`, extraída para `_best_sample_by_decision`); todas as
  decisões de teste de um fold têm o mesmo comprimento de encoder L (o adapter
  confere e ergue `ValueError` se receptor e doador diferirem — nunca trunca nem
  completa); o `collate_fn` envolve o default da lib e troca
  `encoder_cont[i, :L, colunas de f]` pelo bloco do doador `donors[k][pos(d_i)]`,
  com a decisão da amostra lida de `decoder_time_idx[i, 0] - 1`. O `_emit` passa a
  receber o dataloader (construído exatamente como o `predict` o constrói:
  `to_dataloader(train=False, batch_size=..., num_workers=0)`); o caminho da 7.1
  passa o default.
- **VSN:** uma passagem extra do dataloader de identidade com `mode="raw"`,
  `return_x=True`; `interpret_output(raw.output, reduction="none")["encoder_variables"]`
  (média sobre os passos do encoder, como a lib reduz), um vetor por decisão
  (amostra de decodificador mais longo), chaveado por `model.encoder_variables`.
- **Escritores por run** (desempenho: ~8,7 M linhas): `PersistPermutedPredictions`
  recebe **um run por chamada** (`entries: Sequence[PermutedDecisionEntry]`, cada uma
  `(permuted_family, permutation_index, decision_idx, forecasts)`), e
  `PersistVsnWeights` idem (`decisions: Sequence[VsnDecisionEntry]`); uma escrita
  append-only por run e tabela. `target_timestamp_utc` pela mesma regra do
  `PersistPredictions` (serviço `multi_horizon_prediction_persister`, dono único,
  ADR 4.3.0001); `year = int(timestamp_utc[:4])` (ano da decisão).
- **Retomada da atribuição:** run com entrada `completed` no manifesto e linhas no
  silver ⇒ **re-conferido por leitura** (sem re-predizer): contagem por
  `(permuted_family, permutation_index)` = contagem da identidade para as 4 famílias
  × k = 1..K_p, colunas `permutation_seed`/`permutation_algorithm`/`partition_hash`
  iguais às do manifesto, linhas de VSN = decisões × variáveis gravadas; status
  `verified`. Linhas presentes sem `completed`, ou contagem incompleta ⇒
  `PartialAttributionError` (C8). É a re-conferência das transferências (ADR
  7.3.0006 item 5), que roda em qualquer máquina sem GPU nem tempo de predição.
- **Ordem do `RunPermutationInference` por run:** validação do comando → lock →
  probe → resolução → leitura do silver de teste do run → plano → predição (guardas
  do fornecedor) → identidade × silver pela política de reprodução da 7.2 →
  manifesto `started` (write-ahead) → `PersistPermutedPredictions` →
  `PersistVsnWeights` → manifesto `completed`. Falha antes do write-ahead não grava
  nada.
- **Manifesto:** `<data_root>/inference/<cohort_id>/attribution_manifest.json`, mesmo
  formato de escrita atômica do `JsonInferenceManifest`, reusando `merge_run_entry`/
  `apply_run_entry` de `inference/application/ports/out/inference_manifest.py`
  (fake e adapter importam as mesmas funções). Entrada por run: `status`
  (`started`/`completed`), `checkpoint_sha256`, `environment` da primeira escrita,
  `settings`, `mode`, `max_abs_diff`, `permutation_seed`, `k_p`,
  `permutation_algorithm`, `fold_index`, `n_decisions`, `family_partition`,
  `partition_hash`, `permuted_rows`, `vsn_rows`.
- **Reduções no evaluation:** os VOs `PermutedRunLosses`, `AblationRunLosses` e
  `VsnRunWeights` moram em `value_objects/` (stdlib); `reduce_vsn_run` fica em
  `vsn_run_weights.py`; **`reduce_permuted_run` e `reduce_ablation_run` ficam em
  `services/attribution_assembly.py`**, porque constroem `CoverageSeries` (e portanto
  `QuantileForecast`) e esse é o único módulo novo com a aresta de dados declarada
  (aresta 7 do concept §8). Assim a contagem de arestas novas fica em 7.
- **Leitura da ablação por `year`:** os anos lidos são os anos distintos
  (`int(ts[:4])`) dos `timestamp_utc` das decisões de teste do candidato, já
  presentes nas reduções; uma chamada `read(layer="silver",
  table="fact_oos_predictions", filters={"asset", "feature_set_name":
  "fs_all_ablation", "year": y})` por ano, filtro por `run_id ∈ runs da ablação` e
  `split == "test"` dentro do bloco, redução por run e descarte do bloco antes do
  seguinte; reduções parciais de um run que cruza o ano são unidas por
  `merge_ablation_parts` (decisões disjuntas, senão `undefined`).
- **Subcomandos de ablação em módulo próprio:** `modeling/adapters/in/cli/ablation_commands.py`
  com `AblationCommandDeps` (o `CohortCommandDeps` da 5.5 e os testes que o
  constroem ficam intocados; o roadmap citava `cohort_commands.py`); o `cli.py`
  despacha `ablation-pilot`, `ablation-run`, `ablation-verify`, `ablation-freeze` e
  `attribute`. O `attribute` recebe `--ablation-cohort` e o `cli.py` (fora dos
  slices) lê o `[partition]` pelo loader do modeling e o passa ao comando do
  inference — o slice inference nunca importa o loader do modeling.
- **Chaves do TOML de ablação** (`config/cohorts/aapl_ablation.toml`): topo `name`,
  `revision`, `feature_set_name = "fs_all_ablation"`, `device`, `seeds` (lista; vazia
  no rascunho), `torch_build` (ausente no rascunho); `[base]` `cohort_file`,
  `cohort_id`, `cohort_hash`; `[partition]` família → lista; `[configurations.<nome>]`
  `feature_set_hash` (as 5; `excluded_family` e `model_version` são derivados do nome,
  nunca declarados). Qualquer outra chave (inclusive `tft_params`, `geometry`,
  `horizons`, `quantile_levels`, `dataset_fingerprint`, `pipeline_version` — I4) ⇒
  `ValueError` com o caminho pontuado.
- **Chaves finais do bloco `[h3]`** (catálogo `H3_RULE_CATALOG`; valores do concept
  §4 e do ADR 7.3.0005):

  | chave | valor |
  |---|---|
  | `families` | `["price", "technical", "sentiment", "fundamental"]` |
  | `feature_set_hash` | `"7df0e1b4d6e93e3edb5695414a47d2d77882a2ffc674d00037f2a9f87a6409e0"` |
  | `partition_rule` | `"registry_family_lists_frozen_v1"` |
  | `permutation_scheme` | `"whole_encoder_window_joint_between_fold_test_decisions_v1"` |
  | `permutation_algorithm` | `"fisher_yates_random_random_v1"` |
  | `k_p` | `10` |
  | `permutation_seed` | `130` |
  | `measure` | `"grid_mean_pinball_difference_guardrail_v1"` |
  | `pairing` | `"decision_point_horizon_intersection_v1"` |
  | `seed_aggregation` | `"pointwise_seed_mean_then_permutation_mean_v1"` |
  | `bootstrap_scheme` | `"stationary"` |
  | `block_rule` | `"max_7_ceil_max_bsb_joint_16_series_v1"` |
  | `reps` | `1000` |
  | `bootstrap_seed` | `129` |
  | `interval` | `"basic_linear_percentile_v1"` |
  | `multiplicity` | `"bonferroni_over_families_v1"` |
  | `family_alpha` | `0.05` (nível `1 − α/4 = 0.9875`) |
  | `nonpositive_total` | `"undefined_if_point_total_nonpositive_replicas_as_infinite_v1"` |
  | `reading_rule` | `"interval_side_agreement_same_family_v1"` |
  | `vsn_summary` | `"per_decision_seed_mean_p10_p50_p90_family_sum_v1"` |
  | `[h3.partition]` | `partition_hash` (literal, 64 hex) + as 4 listas |
  | `[h3.ablation]` | `cohort_id`, `cohort_hash`, `seeds` (sentinela `"__FILL_AFTER_FREEZE__"` no rascunho), `reference_model = "tft_quantile_loco_full"`, `models` (família → `tft_quantile_loco_minus_<f>`) |

- **Colunas das tabelas gold** (ADR 7.3.0001 item 4; mais `asset`,
  `parent_sweep_id`, `preregistration_ref` por `partition_columns(confirmatory=True)`):
  - `gold_h3_importance` — chave `(method, family, horizon, seed, permutation_index)`;
    `seed` nulo = média nas seeds, `permutation_index` nulo = média nas permutações
    (sempre nulo no LOCO); `read_columns = (importance, n_points, status, reason)`.
    Linhas: a agregada `(seed nulo, k nulo)` = I_f(h); perfil por seed `(s, nulo)`;
    perfil por permutação `(nulo, k)` só no método `permutation`.
  - `gold_h3_shares` — chave `(method, family)`; `read_columns = (share_h1, share_h7,
    delta, lower, upper, lower_infinite, upper_infinite, level, side, excludes_zero,
    status, reason, nonpositive_replicas_h1, nonpositive_replicas_h7, method_status,
    method_reason)`. Limite infinito ⇒ `null` + flag `true` (padrão da 7.2); método
    `undefined` ⇒ as 4 linhas com medidas nulas, `status = "undefined"` e o motivo.
  - `gold_h3_reading` — chave `(reading_rule,)` (uma linha); `read_columns =
    (heterogeneous_permutation, heterogeneous_ablation, sustained, agreeing_families,
    block_length, max_block_estimate, reps, bootstrap_seed, n_points,
    nonpositive_permutation_h1, nonpositive_permutation_h7, nonpositive_ablation_h1,
    nonpositive_ablation_h7, ablation_cohort_id, label, status, reason)`;
    `agreeing_families` em texto `"a,b"` ordenado (`""` sem família); `label =
    "descritiva (sem claim causal)"`.
  - `gold_h3_vsn` — chave `(kind, name)` com `kind ∈ {variable, family}`;
    `read_columns = (family, p10, p50, p90, n_decisions, label, status, reason)`;
    `family` = família da registry ou `"none"` (calendário, alvo passado, índice
    relativo); `label = "horizonte-invariante; descreve quanto o modelo usa cada família"`.
- **Chaves do probe para device ≠ `cpu`** (port `runtime_environment_probe.py` do
  modeling): `GPU_KEYS = ("gpu.available", "gpu.name", "gpu.hip_version")`, valores
  `"true"`/`"false"`, o nome do dispositivo 0 e `torch.version.hip` (`""` quando
  `None`). Para `cpu` o snapshot tem exatamente as chaves de hoje (`REQUIRED_KEYS`).
- **Saída do `attribute`** (uma linha por run e um resumo, padrão do `infer`):
  `run <id> fold <f> seed <s>: <strict|tolerance> identity compared <n> max|d| <x> max|d|/s <y> permuted written <p> vsn written <v>`
  (ou `… verified` na re-conferência) e
  `attribution <cohort_id>: <N> runs (<a> strict, <b> tolerance); permuted rows written <P>, verified <Q>; vsn rows written <V>, verified <W>`.
- **Saída do `ablation-verify`:**
  `ablation <cohort_id>: 5 configurations x <n_folds> folds x <S> seeds = <R> runs; rows expected <E>, observed <O>`
  e `OK` (padrão do `verify` da 5.5).
- **Saída do `ablation-freeze`:**
  `frozen <cohort_id>: cohort_hash <64 hex>; seeds <S>; torch_build <versão>` (o
  `cohort_id` e o hash são os que a L4 publica na tag e no comentário da #186).

### Matrícula dos módulos novos nos contratos do `.importlinter`

Os contratos são por pacote; todo módulo novo cai dentro de um `source_modules` já
matriculado. O que esta Stage prova é que cada contrato **reage** no perímetro novo
e que cada aresta nova é uma exceção **do módulo**, não do slice:

| Módulo(s) novo(s) | Contratos que o cobrem | Caso de violação real |
|---|---|---|
| `shared/domain/value_objects/family_partition_hash.py` | `hexagonal-layers`, `domain-purity`, `inward-only`, `shared-no-features` | existentes (`domain-purity:domain-imports-pandas`, `shared-no-features:shared-imports-feature`) |
| `modeling/application/{dtos,use_cases}/*` novos | `hexagonal-layers`, `inward-only`, `modeling-no-torch-leak`, `modeling-no-statsforecast-leak`, `modeling-no-lightgbm-leak`, `modeling-no-optuna-leak`, `store-no-storage-leak`, `bc-independence` | existentes; a guarda AST da Task 08 cobre os dois executores |
| `inference/domain/value_objects/permutation_plan.py` | `hexagonal-layers`, `domain-purity`, `inward-only`, `inference-no-torch-leak`, `inference-no-mapie-leak` (7.2), `bc-independence` | existentes (7.1/7.2) |
| `inference/application/{ports/out,use_cases}/*` novos | idem + `store-no-storage-leak` | existentes + **novos por aresta** (Task 19): um módulo irmão que faça o mesmo import reprova `bc-independence` |
| `analytics_store/*` novos, `evaluation/*` novos | contratos do slice | existentes; aresta 7 com caso novo (Task 24) |

Casos novos em `tests/architecture/test_import_contracts.py` (`_REAL_VIOLATION_CASES`):
`bc-independence:other-inference-module-imports-resolve-tft-checkpoints-for-attribution`,
`bc-independence:other-inference-module-imports-predict-tft-attribution`,
`bc-independence:other-inference-module-imports-probe-code-keys`,
`bc-independence:other-inference-module-imports-persist-permuted-predictions`,
`bc-independence:other-inference-module-imports-persist-vsn-weights`,
`bc-independence:other-inference-module-imports-quantile-forecast` (Task 19) e
`bc-independence:other-evaluation-module-imports-quantile-forecast-for-h3` (Task 24).
O comentário de cabeçalho do contrato `bc-independence` no `.importlinter` (contagem de
arestas de runtime declaradas) sobe junto com o LAYOUT §7: 28 → 34 na Task 19 e
34 → 35 na Task 24.
A Task 29 acrescenta `test_stage_7_3_new_modules_are_enrolled` (lê o `.importlinter` e
afirma que cada módulo de `src/` criado pela Stage está sob o `source_modules` de cada
contrato da sua camada e do seu slice).

### Pré-condições

- Concept `done` (`be50d72`) e ADRs 7.3.0001–0006 `accepted`; roadmap emendado no
  concept (`58e70aa`).
- P1 cumprida e verificação de gap registrada em §7.
- Imagem `financial_forecasting-app:dev`; volume `financial-forecasting_app-venv`
  conferido (acima).
- Etapa W: `data/cohorts/aapl/` no checkout principal com `silver/` e
  `inference/aapl_confirmatory-r0-665f45d9169a/manifest.json` (7.1, Etapa E; 60
  `completed`), sem `gold/`; `artifacts/` com os 60 checkpoints.

### Premissas técnicas

- Python 3.12, mypy strict, `from __future__ import annotations`; imports cross-slice
  de tipo só sob `TYPE_CHECKING` (invisíveis ao import-linter,
  `exclude_type_checking_imports = True`) — daí as guardas AST em
  `tests/architecture/test_stage_7_3_regression_guards.py`.
- `make check-task SLICE=…` (T1) aceita `shared`, `modeling`, `inference`,
  `analytics_store` e `evaluation`; **não** roda `tests/architecture/` — Task que toca
  `.importlinter`, `pyproject.toml`, `uv.lock`, `scripts/arch_baseline.toml`,
  `conftest.py` compartilhado ou `tests/architecture/` é T3. Task que toca `shared/` ou
  `composition_root.py` é, no mínimo, T2 (`make check-block`).
- `tests/architecture/test_unit_evaluation_purity.py`: nenhum
  `tests/unit/features/evaluation/**` importa `numpy`/`scipy`/`sklearn`/`arch`/adapter
  nem chama `open`/`read_text`/`json.load`. **Toda Task que cria ou muda teste em
  `tests/unit/features/evaluation/`** (21–30) roda também
  `uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov`.
- **Teste que lê arquivo do repo** (TOML de cohort, rascunho da r3, este technical,
  `.importlinter`) fica em `tests/architecture/` (Tasks 06, 08, 29, 32, 33).
- `GoldTable` recusa float não-finito; `GoldGeneration.from_stored` exige que uma
  geração `COMPLETED` liste toda tabela de `GOLD_SCHEMAS` e que `BLOCKED` não liste
  tabela de `CONFIRMATORY_TABLES`; `check_manifest` compara
  `parameters.as_mapping()` inteiro.
- O mypy roda só sobre `src/`; arquivo de teste quebra pelo pytest (import).
- `slow` marca teste com custo de minutos (treino real, volume real); sai só do T1.

### Estrutura de pastas afetada

```
.importlinter, docs/LAYOUT.md §7, tests/architecture/test_import_contracts.py   (mod, Tasks 19, 24)
docs/LAYOUT.md §7 (VO de identidade)                                              (mod, Task 01)
scripts/arch_baseline.toml                                                        (mod, 07, 17, 18)
tests/architecture/test_port_coverage_gate.py                                     (mod, 16, 17, 18)
tests/architecture/test_stage_7_3_regression_guards.py                            (novo 08; mod 29)
tests/architecture/test_stage_7_3_repo_files.py                                   (novo 06; mod 32)
tests/architecture/test_stage_7_3_handoff_commands.py                             (novo 33)
config/cohorts/aapl_ablation.toml                                                 (novo 06; freeze na L4)
docs/stages/7.3-explainability/aapl_confirmatory-r3.draft.toml                    (novo 32)
src/financial_forecasting/
├── cli.py, composition_root.py                                                   (mod 03, 10, 11, 20, 29)
├── shared/domain/value_objects/family_partition_hash.py                          (01)
└── features/
    ├── modeling/
    │   ├── application/dtos/ablation_cohort_spec.py                              (05)
    │   ├── application/ports/out/{tft_checkpoint_predictor (11), runtime_environment_probe (04)}.py
    │   ├── application/use_cases/{train_tft (mod 02, 07), cohort_unit_runner (07), run_confirmatory_cohort (mod 07),
    │   │                          run_ablation_cohort (08), measure_ablation_cost (09),
    │   │                          predict_tft_attribution_from_checkpoints (12)}.py
    │   ├── adapters/in/cli/{ablation_cohort_file (06), ablation_commands (10)}.py
    │   └── adapters/out/{pytorch_forecasting/pf_tft_trainer (03, 11), runtime/git_runtime_environment_probe (04)}.py
    ├── analytics_store/
    │   ├── adapters/out/parquet/schemas/{fact_permuted_predictions_schema, fact_vsn_weights_schema (14), silver_registry (mod 14)}.py
    │   ├── application/ports/out/analytics_repository.py, adapters/out/parquet/parquet_analytics_repository.py (docstrings, 14)
    │   └── application/use_cases/{persist_permuted_predictions, persist_vsn_weights}.py (15)
    ├── inference/
    │   ├── domain/value_objects/permutation_plan.py                              (13)
    │   ├── application/ports/out/{checkpoint_attribution_predictor, permuted_prediction_persister,
    │   │                          vsn_weight_persister (16), attribution_manifest (17)}.py
    │   ├── application/use_cases/run_permutation_inference.py                    (19)
    │   ├── adapters/out/filesystem/json_attribution_manifest.py                  (18)
    │   └── adapters/in/cli/inference_commands.py                                 (mod 20)
    └── evaluation/
        ├── domain/value_objects/{h3_parameters (21), preregistration (mod 22), permuted_forecast_record,
        │                         vsn_weight_record, permuted_run_losses, ablation_run_losses,
        │                         vsn_run_weights (23), family_loss_differentials (24)}.py
        ├── domain/services/{attribution_assembly (24), family_contribution (25),
        │                    contribution_agreement, vsn_summary (26)}.py
        ├── application/dtos/{refresh_gold (27, 28), confirmatory_scorecard (27), gold_schema (29)}.py
        ├── application/use_cases/refresh_gold.py                                 (mod 28, 30)
        └── adapters/out/duckdb/gold_builders/{h3_importance, h3_shares, h3_reading, h3_vsn}.py (29)
tests/  (por Task, em §2)
```

## 2. Tasks

> Faixa de referência: 3–12 Tasks (CONVENTIONS §6). **Esta Stage tem 33**, mais a
> Etapa W e as Etapas L0–L8. A contagem é referência, não gate: o concept (§12) não
> tem fronteira de escopo real para dividir (treino LOCO, permutação e leitura são
> uma capacidade, testada ponta a ponta no e2e), e a estimativa de ~20 cresceu
> porque a extensão do port e o fornecedor, o port do manifesto e o seu adapter (ADR
> 6.1.0005), os DTOs do gold e o `RefreshGold`, e as reduções e a montagem são
> commits separados para que cada um fique verde.

### Task 01 — `FamilyPartitionHash`: VO de identidade da partição

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/value_objects/family_partition_hash.py`
  - `tests/unit/shared/domain/value_objects/test_family_partition_hash.py`
- **Arquivos a modificar:**
  - `docs/LAYOUT.md` §7 (o VO na lista de VOs de identidade de `shared`, ao lado de
    `CohortHash` e `PreregistrationHash`; regra 6 do `check_layout`)
- **Testes primeiro** (hasher real `CanonicalJsonHasher`, como os testes dos outros
  VOs de identidade): `test_value_is_the_canonical_hash_of_the_documented_payload`;
  `test_order_within_a_family_does_not_change_the_hash`;
  `test_moving_a_feature_between_families_changes_the_hash` (mata o hash só dos nomes
  de família); `test_feature_set_hash_changes_the_hash`;
  `test_repeated_feature_within_or_across_families_refused`;
  `test_empty_partition_or_family_refused`; `test_feature_set_hash_must_be_64_hex`;
  `test_value_is_64_hex`; `test_raw_construction_with_invalid_value_refused`
  (`FamilyPartitionHash(value="xyz")` ⇒ `ValueError`).
- **O que fazer (concept §4 "Shared", I17; ADR 7.3.0002 item 4):** VO frozen no
  padrão do `CohortHash`, payload do §1.
- **Critério de aceite (I17, parte VO):** testes verdes; `check_layout` regra 6 verde
  (o `hash_mapping` só é chamado em `shared/domain/value_objects`).
- **Verificação (T2 — shared):**
  ```bash
  uv run --no-sync pytest tests/unit/shared/domain/value_objects/test_family_partition_hash.py -v --no-cov
  make check-block $PAR
  ```
- **Commit:** `feat(shared): VO de identidade da partição de famílias [7.3/task-01]`

---

### Task 02 — `TrainTft` por subconjunto de famílias, com identidade por configuração

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/train_tft.py`
- **Arquivos a criar:**
  - `tests/unit/features/modeling/application/test_train_tft_family_subset.py`
- **Testes primeiro:**
  - `test_default_command_keeps_the_pinned_run_id_and_config_signature` (CA1/I1: os
    dois literais de um fold confirmatório **medidos em `$BASE` antes da mudança** —
    o teste nasce verde e continua verde);
  - `test_registry_family_partition_is_17_17_11_10_in_registry_order`;
  - `test_every_family_feature_is_unknown` (I8, metade da registry; P2);
  - `test_subset_panel_columns_are_registry_minus_family_in_order` (parametrizado nas 4
    famílias; os `known` ficam);
  - `test_subset_grid_is_trimmed_on_the_full_column_set` (CA2/I2: dataset sintético em
    que a família removida tem o maior aquecimento; timestamps, folds, decisões e
    `split_fingerprint` iguais aos da configuração completa — mata o corte pelo
    subconjunto);
  - `test_subset_run_id_carries_subset_hash_and_loco_model_version`;
  - `test_tft_feature_set_hash_matches_the_measured_prefixes` (`None` → `7df0e1b4…`;
    sem price `7631c0ae…`, sem technical `b75eca48…`, sem sentiment `5f737061…`,
    sem fundamental `c58b322f…` — concept §3);
  - `test_loco_full_differs_from_candidate_only_in_model_version` (mesma
    `config_signature`, `run_id` diferente);
  - `test_subset_rows_and_dim_run_carry_loco_model_version` (toda linha gravada em
    `fact_oos_predictions` e a linha do `dim_run` do run têm `model_version =
    tft_quantile_loco_<configuração>` — o `model_version` do comando chega ao que é
    persistido, não só ao `RunId`);
  - `test_tracking_phase_tag_of_loco_runs` (a tag `phase` do tracker nos runs LOCO —
    valor decidido abaixo);
  - `test_model_version_pairing_refused_before_any_io` (C1, parametrizado:
    `excluded_family = f` com `model_version ≠ tft_quantile_loco_minus_<f>`;
    `None` com `model_version ∉ {tft_quantile, tft_quantile_loco_full}`; família fora
    das 4; o store fake não é lido).
- **O que fazer (concept §1 item 1, §4; ADR 7.3.0003 item 2):** campos
  `excluded_family: str | None = None` e `model_version: str = MODEL_VERSION` no
  `TrainTftCommand`; `load_tft_panel(*, store, asset_id, excluded_family=None)` lê e
  apara pelo conjunto completo (`build_training_grid`) e só então tira as colunas;
  `tft_run_identity` usa `tft_feature_set_hash(command.excluded_family)` e
  `command.model_version`; funções do §1 (`TFT_FAMILIES`, `registry_family_partition`,
  `tft_feature_set_hash`, `loco_model_version`); validação no `_validate_command`; o
  `model_version` do comando vai a todo `PersistPredictionsCommand` e ao `RunRecord`.
  **Tag `phase` do tracker nos runs LOCO:** a opção recomendada é manter
  `"confirmatory_ready"` (o run LOCO é do procedimento pré-registrado e a configuração
  já está no `model_version`); a alternativa é uma tag nova `"ablation"`. O executor
  registra a escolha como `[decision]` em §7 na Task 02, e o teste fixa o valor.
- **Critério de aceite (CA1, CA2; I1, I2, I3 parte; C1 parte):** testes novos verdes;
  nenhum teste existente alterado.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/application/test_train_tft_family_subset.py -v --no-cov
  make check-task SLICE='modeling inference' $PAR
  git -C "$WTH" status --short -- tests/   # só "?? tests/unit/features/modeling/application/test_train_tft_family_subset.py"
  ```
- **Commit:** `feat(modeling): treino do TFT por subconjunto de famílias com identidade própria [7.3/task-02]`

---

### Task 03 — Device por instância do `PfTftTrainer`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/adapters/out/pytorch_forecasting/pf_tft_trainer.py`
  - `src/financial_forecasting/composition_root.py` (`_SUPPORTED_DEVICES = {"cpu": "cpu", "rocm": "gpu"}`; `_LazyPfTftTrainer(accelerator)`; um proxy lazy por device; as fábricas confirmatória e de inferência usam `"cpu"`)
  - `tests/unit/shared/test_composition_root.py`
- **Arquivos a criar:**
  - `tests/integration/features/modeling/test_pf_tft_accelerator.py`
- **Testes primeiro:**
  - adapter: `test_default_instance_uses_cpu_in_fit_emit_and_checkpoint_prediction`
    (captura os kwargs do `Trainer` de Lightning e os `trainer_kwargs` do `predict`
    por `monkeypatch`, sem treinar); `test_gpu_instance_passes_gpu_everywhere`
    (o mesmo, com `PfTftTrainer(accelerator="gpu")`, sem GPU — o `Trainer` capturado
    ergue um sentinela antes de alocar); `test_settings_report_the_instance_accelerator`;
    `test_gpu_fit_smoke` (`skipif(not torch.cuda.is_available())`);
  - composition root: `test_supported_devices_map_is_cpu_and_rocm`;
    `test_device_outside_the_map_refused_without_importing_torch` (subprocesso: `torch`
    fora de `sys.modules`); `test_confirmatory_and_inference_factories_use_cpu`.
- **O que fazer (concept §1 item 2; ADR 7.3.0004 itens 1–2):** `PfTftTrainer(accelerator:
  str = "cpu")`; `fit`, `_emit` e `predict_from_checkpoint` usam a instância; a chave
  `accelerator` dos `settings` reporta o valor; mapa e proxies no composition root.
- **Critério de aceite (CA5 parte; I1, I5 parte):** testes verdes; os goldens do
  treinador e da predição a partir do checkpoint intocados e verdes.
- **Verificação (T2 — composition root):**
  ```bash
  uv run --no-sync pytest tests/integration/features/modeling/test_pf_tft_accelerator.py tests/unit/shared/test_composition_root.py -v --no-cov
  git -C "$WTH" diff --exit-code "$BASE" -- tests/contract/features/modeling/test_tft_trainer_golden.py tests/integration/features/modeling/test_pf_tft_checkpoint_prediction.py
  make check-block $PAR
  ```
- **Commit:** `feat(modeling): device por instância do treinador do TFT [7.3/task-03]`

---

### Task 04 — Probe com GPU e HIP observados para device ≠ `cpu`

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/ports/out/runtime_environment_probe.py` (`GPU_KEYS`, docstring)
  - `src/financial_forecasting/features/modeling/adapters/out/runtime/git_runtime_environment_probe.py`
  - `tests/fakes/features/modeling/in_memory_runtime_environment_probe.py` (snapshot configurável com as chaves de GPU)
  - `tests/contract/features/modeling/test_runtime_environment_probe_contract.py`
- **Testes primeiro** (`[fake, real]`; a perna real com `torch.cuda.is_available`,
  `torch.cuda.get_device_name` e `torch.version.hip` por `monkeypatch`):
  `test_cpu_snapshot_has_exactly_todays_keys` (conjunto literal = `REQUIRED_KEYS`;
  mata a chave de GPU vazando para `cpu`); `test_non_cpu_snapshot_adds_the_observed_gpu_keys`;
  `test_gpu_keys_are_observed_not_echoed` (`device="rocm"` com GPU indisponível ⇒
  `gpu.available == "false"`); `test_absent_hip_is_empty_string`.
- **O que fazer (concept I5; ADR 7.3.0004 item 3):** chaves do §1.
- **Critério de aceite (CA5 parte "snapshot do probe com cpu igual ao de hoje"; I5):**
  testes verdes; a perna real do `cpu` sem diferença de chaves.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/contract/features/modeling/test_runtime_environment_probe_contract.py -v --no-cov
  make check-task SLICE='modeling inference' $PAR
  ```
- **Commit:** `feat(modeling): probe observa GPU e HIP fora do device cpu [7.3/task-04]`
- **Checkpoint C** (T2 `make check-block $PAR` + revisão do diff das Tasks 01–04).

---

### Task 05 — `AblationCohortSpec`: spec por referência, identidade por configuração

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/dtos/ablation_cohort_spec.py`
  - `tests/unit/features/modeling/application/test_ablation_cohort_spec.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_five_configurations_in_fixed_order`;
  `test_configuration_identity_derived_from_the_name` (`excluded_family` e
  `model_version = tft_quantile_loco_<nome>` — mata o `model_version` único);
  `test_missing_repeated_or_unknown_configuration_refused` (C1);
  `test_repeated_or_non_positive_seed_refused`; `test_partition_overlap_or_missing_family_refused`;
  `test_is_frozen_requires_seeds_and_torch_build` (parametrizado);
  `test_every_field_changes_the_hash` (parametrizado sobre todo campo, inclusive
  `device`, `torch_build`, `feature_set_name`, `base_cohort_hash` e a partição — I5);
  `test_cohort_id_pattern` (`<nome>-r<rev>-<12 hex>`);
  `test_with_freeze_sets_seeds_and_build_only`.
- **O que fazer (concept §4; ADR 7.3.0003 item 1):** `ABLATION_CONFIGURATIONS`,
  `ABLATION_FEATURE_SET_NAME = "fs_all_ablation"`, `AblationConfiguration`,
  `AblationCohortSpec` (`is_frozen`, `hash_payload`, `cohort_id`, `with_freeze`) e
  `AblationDeclarationError(ApplicationError)` (C2).
- **Critério de aceite (CA3 parte VO; I3, I5 parte; C1 parte):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/application/test_ablation_cohort_spec.py -v --no-cov
  make check-task SLICE=modeling $PAR
  ```
- **Commit:** `feat(modeling): spec do cohort de ablação por referência ao confirmatório [7.3/task-05]`

---

### Task 06 — Loader do TOML de ablação e rascunho `aapl_ablation.toml`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/adapters/in/cli/ablation_cohort_file.py`
  - `config/cohorts/aapl_ablation.toml` (rascunho: `seeds = []`, sem `torch_build`, `device = "rocm"`, `[base]` com o id e o hash do r0, `[partition]` medida da registry, `[configurations.*]` com os 5 hashes)
  - `tests/unit/features/modeling/adapters/in_/test_ablation_cohort_file.py`
  - `tests/architecture/test_stage_7_3_repo_files.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:**
  - unit (arquivos em `tmp_path`, base sintética): `test_draft_shape_loads_unfrozen`;
    `test_base_hash_mismatch_refused` (C2); `test_partition_different_from_registry_refused`;
    `test_declared_subset_hash_different_from_registry_refused`;
    `test_procedure_fields_in_the_ablation_file_refused` (I4: `tft_params`, `geometry`,
    `horizons`, `quantile_levels`, `dataset_fingerprint`, `pipeline_version`);
    `test_unknown_key_refused_with_dotted_path`; `test_dump_then_load_round_trip`
    (com seeds e `torch_build`);
  - arquitetura (lê o repo): `test_ablation_draft_loads_unfrozen_with_registry_partition`
    (base real `config/cohorts/aapl_confirmatory.toml`, `CanonicalJsonHasher`);
    `test_confirmatory_cohort_file_hash_unchanged` (CA1:
    `665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1`).
- **O que fazer (concept §4 "Config", C2; ADR 7.3.0003 item 1):**
  `load_ablation_cohort(path, *, hasher, load_base) -> AblationCohortSpec` (relê a base,
  recalcula o `CohortHash`, confere partição e hashes de subconjunto contra
  `registry_family_partition`/`tft_feature_set_hash`) e
  `dump_ablation_cohort(spec) -> str`; chaves do §1.
- **Critério de aceite (CA3 carga e recusas; I4; C2):** testes verdes.
- **Verificação (T3 — `tests/architecture/`):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/adapters/in_/test_ablation_cohort_file.py tests/architecture/test_stage_7_3_repo_files.py -v --no-cov
  make check $PAR
  ```
- **Commit:** `feat(modeling): loader e rascunho do cohort de ablação [7.3/task-06]`

---

### Task 07 — Máquina de unidades do executor extraída para `cohort_unit_runner`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/cohort_unit_runner.py`
  - `tests/unit/features/modeling/application/test_cohort_unit_runner.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/run_confirmatory_cohort.py`
  - `scripts/arch_baseline.toml` (remove as duas entradas mortas de `[schema_literals]` do `run_confirmatory_cohort.py`, §1)
  - `src/financial_forecasting/features/modeling/application/use_cases/train_tft.py` (só os nomes públicos `DATASET_LAYER = _DATASET_LAYER` e `DATASET_TABLE = _DATASET_TABLE`, para o import sem nome privado; nenhum literal novo)
- **Testes primeiro** (sobre os fakes da 5.5): `test_ledger_unit_is_reconferred`;
  `test_silver_complete_unit_is_verified_and_marked`; `test_partial_unit_raises`;
  `test_absent_unit_runs_and_is_marked_after_success`;
  `test_environment_recorded_first_then_compared`; `test_dirty_tree_refused`;
  `test_lock_released_on_error`.
- **O que fazer (concept D7; ADR 7.3.0003 item 3):** movem para o módulo novo as
  exceções (`CohortNotFrozenError`, `DatasetMismatchError`,
  `CohortDeclarationMismatchError`, `EnvironmentMismatchError`, `PartialCohortUnitError`,
  `CompletedUnitCorruptedError`, `UnitOutputMismatchError`), `check_cohort_declarations`,
  `recorded_run_problems`, `load_training_grid` (que **importa** as constantes de
  coordenada do dataset TFT do `train_tft`, sem redeclarar `"processed"`/`"dataset_tft"`),
  `CohortUnitOutcome` e a máquina
  (`UnitPlan(key, execute, model_keys)`, `writer_lock(ledger, break_stale)`,
  `check_environment(ledger, probe, cohort_id)`, `classify_and_run(...)`). O
  `run_confirmatory_cohort.py` reexporta os nomes públicos (`X as X`, para que os
  importadores da 5.5/7.1 e os testes fiquem intocados) e define só a lista de
  unidades e as pré-condições.
- **Critério de aceite (CA4 parte "testes da 5.5 sem mudar asserção"; D7):** testes
  novos verdes; suítes da 5.5 e da 7.1 sem diferença e verdes; o arch-ast
  (`check_schema_literals.py`) verde sem baseline morto.
- **Verificação (T3 — `scripts/arch_baseline.toml`):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/application/test_cohort_unit_runner.py tests/unit/features/modeling/application/test_run_confirmatory_cohort.py -v --no-cov
  uv run --no-sync python scripts/check_schema_literals.py
  git -C "$WTH" diff HEAD -- scripts/arch_baseline.toml | grep -E '^\+[^+]'   # vazio: só remoções
  git -C "$WTH" status --short -- tests/   # só "?? tests/unit/features/modeling/application/test_cohort_unit_runner.py"
  make check $PAR
  ```
- **Commit:** `refactor(modeling): máquina de unidades do executor de cohort compartilhada [7.3/task-07]`

---

### Task 08 — `RunAblationCohort`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/run_ablation_cohort.py`
  - `tests/unit/features/modeling/application/test_run_ablation_cohort.py`
  - `tests/architecture/test_stage_7_3_regression_guards.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (fakes da 5.5 + `InMemoryTftTrainer` que registra os comandos):
  - `test_unfrozen_spec_refused_before_lock_and_probe` (C3);
  - `test_units_are_configurations_outer_seeds_inner` (`tft:<configuração>:seed=<s>`);
  - `test_each_unit_trains_with_its_configuration_identity` (`excluded_family`,
    `model_version`, `feature_set_name = "fs_all_ablation"`, `parent_sweep_id` = o
    `cohort_id` da ablação);
  - `test_no_run_id_collision_across_configurations_and_seeds` (I3: conjuntos de
    `run_id` e de `(model_version, seed)` com 5 · S · n_folds e 5 · S elementos);
  - `test_geometry_equal_across_configurations_and_base` (I2: folds e
    `split_fingerprint` iguais aos do confirmatório);
  - `test_base_declarations_checked_with_the_base_device` (dataset com fingerprint
    errado ⇒ `DatasetMismatchError`; base `cpu` passa com ablação `rocm`);
  - `test_probe_guard_refuses_before_training` (parametrizado: GPU indisponível, HIP
    vazio, torch ≠ `torch_build`; o treinador não é chamado — C3) e
    `test_probe_guard_accepts_gpu_hip_and_build`;
  - `test_resume_reconfers_ledger_units`; `test_silver_complete_unit_verified`;
    `test_partial_unit_raises` (C4); `test_environment_mismatch_on_resume` (C3);
    `test_recorded_run_problems_over_model_version_seed_keys`;
  - guarda (arquitetura): `test_cohort_runners_never_import_each_other` (AST, inclusive
    `TYPE_CHECKING` e `importlib.import_module` com constante: nenhum dos dois
    executores importa o outro; os dois importam `cohort_unit_runner`;
    `test_guard_catches_every_import_form` planta as formas num módulo temporário).
- **O que fazer (concept §1 item 3, I2–I5; ADR 7.3.0003 item 3, ADR 7.3.0004 item 3):**
  `RunAblationCohortCommand(spec, base, break_stale_lock=False)`; pré-condições na ordem
  frozen → lock → declarações da base (`check_cohort_declarations`, device da base) →
  guarda de hardware observado → ambiente → unidades (`TrainTft` com o comando por
  configuração); resultado com `cohort_id`, hash e desfecho por unidade.
- **Critério de aceite (CA4; I2, I3, I5; C3, C4):** testes verdes.
- **Verificação (T3 — `tests/architecture/`):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/application/test_run_ablation_cohort.py tests/architecture/test_stage_7_3_regression_guards.py -v --no-cov
  make check $PAR
  ```
- **Commit:** `feat(modeling): executor retomável do cohort de ablação [7.3/task-08]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 05–08).

---

### Task 09 — Piloto `MeasureAblationCost`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/measure_ablation_cost.py`
  - `tests/unit/features/modeling/application/test_measure_ablation_cost.py`
  - `tests/integration/features/modeling/test_measure_ablation_cost.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:**
  - unit (treinador fake com `val_loss_by_epoch` programável, `Clock` fake):
    `test_pilot_uses_full_configuration_last_fold_seed_1`;
    `test_ceiling_is_5_folds_s_max_epochs_seconds_per_epoch` (S = 1..10);
    `test_estimate_is_5_folds_s_wall_seconds_and_labelled_estimate`;
    `test_report_fields` (`epochs_run = len(val_loss_by_epoch)`, `best_epoch`,
    `max_epochs` do `tft_params` congelado, device e `torch_build` do probe);
    `test_nothing_is_persisted` (nenhuma chamada a persister, store nem ledger);
  - integração (`PfTftTrainer` real minúsculo em CPU, `tmp_path`):
    `test_pilot_on_a_tiny_real_trainer_writes_no_silver` (`silver/` e `dim_run`
    inexistentes depois; artefatos só no diretório temporário do piloto).
- **O que fazer (concept D8, CA6; ADR 7.3.0003 item 4):** `AblationCostReport` e
  `MeasureAblationCost(command)` chamando o `TftTrainer` direto (nunca o `TrainTft`).
- **Critério de aceite (CA6; I9 parte):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/application/test_measure_ablation_cost.py tests/integration/features/modeling/test_measure_ablation_cost.py -v --no-cov
  make check-task SLICE=modeling $PAR
  ```
- **Commit:** `feat(modeling): piloto de custo do cohort de ablação [7.3/task-09]`

---

### Task 10 — Subcomandos `ablation-*` e wiring

> **> 5 arquivos, justificado:** o parser e o despacho (`cli.py`), o módulo de comandos,
> a fábrica no composition root e os três testes que os cobrem nascem juntos para que
> nenhum subcomando exista sem wiring.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/adapters/in/cli/ablation_commands.py`
  - `tests/unit/features/modeling/adapters/in_/test_ablation_commands.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/cli.py` (`ablation-pilot`, `ablation-run`, `ablation-verify`, `ablation-freeze --seeds 1,2,…`)
  - `src/financial_forecasting/composition_root.py` (`ablation_cohort_for(path)` e `measure_ablation_cost_for(path)` lendo o device do spec; `load_ablation_spec`/`dump_ablation_spec`)
  - `tests/unit/test_cli.py`
  - `tests/unit/shared/test_composition_root.py`
- **Testes primeiro:** comandos (deps fakes): `test_pilot_prints_the_report_with_ceiling_and_estimate`;
  `test_run_refuses_unfrozen_spec`; `test_verify_counts_runs_and_rows` (saída do §1);
  `test_freeze_writes_seeds_and_the_observed_torch_build_atomically`
  (`torch_build` = a chave `torch` do probe; arquivo trocado por `os.replace`);
  `test_freeze_refuses_when_already_frozen`; CLI: `test_ablation_subcommands_have_help`;
  composition root: `test_ablation_factory_reads_the_device_from_the_spec`;
  `test_ablation_factory_refuses_device_outside_the_map_without_importing_torch`.
- **O que fazer (concept §1 item 3, D9; ADR 7.3.0004 item 2):** `AblationCommandDeps`
  e as quatro funções; o `ablation-verify` usa o `CohortRunIndex` com as chaves
  `(model_version, seed)` da ablação.
- **Critério de aceite (CA3 "device fora do mapa", CA5 "composition root recusa sem
  importar torch"; C1 device):** testes verdes.
- **Verificação (T2 — composition root):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/adapters/in_/test_ablation_commands.py tests/unit/test_cli.py tests/unit/shared/test_composition_root.py -v --no-cov
  make check-block $PAR
  ```
- **Commit:** `feat(modeling): subcomandos do cohort de ablação [7.3/task-10]`

---

### Task 11 — `predict_attribution_from_checkpoint` no port e no `PfTftTrainer`

> **> 5 arquivos, justificado:** estender um Protocol obriga o real, o proxy lazy do
> composition root e o fake no mesmo commit (mypy estrutural); a suíte `[fake, real]` e
> o teste de adapter da CA7 provam a extensão; a fixture de checkpoint ganha o caso com
> coluna de família `known`.

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/modeling/application/ports/out/tft_checkpoint_predictor.py` (`TftAttributionPrediction`, `FamilyFeatureKnownError`, método novo)
  - `src/financial_forecasting/features/modeling/adapters/out/pytorch_forecasting/pf_tft_trainer.py`
  - `src/financial_forecasting/composition_root.py` (método no `_LazyPfTftTrainer`)
  - `tests/fakes/features/modeling/in_memory_tft_checkpoint_predictor.py`
  - `tests/contract/features/modeling/test_tft_checkpoint_predictor_contract.py`
  - `tests/contract/features/modeling/_tft_checkpoint_fixture.py` (**só acréscimo**: uma fábrica nova de checkpoint minúsculo com uma coluna de família tipada `known`; o checkpoint default fica intocado)
- **Arquivos a criar:**
  - `tests/integration/features/modeling/test_pf_tft_attribution_prediction.py`
- **Testes primeiro:**
  - adapter (TFT minúsculo real, `batch_size` < nº de decisões — CA7):
    `test_identity_equals_predict_from_checkpoint_value_by_value` (I7);
    `test_identity_permutation_reproduces_the_identity`;
    `test_donor_in_another_batch_gets_the_donor_block` — a referência é
    **independente** da tabela de doadores do adapter: um espião grava os lotes da
    passagem de identidade, e o bloco esperado para a decisão i é
    `encoder_cont[:L, colunas de f]` da amostra da decisão doadora **naquela passagem
    de identidade**; o teste afirma explicitamente que (a) existe i com doador ≠ i e
    (b) o doador de algum i está num lote diferente do lote do receptor, e então
    compara bit a bit com o lote permutado capturado; mata o doador tomado dentro do
    lote e o doador tomado por posição no lote;
    `test_non_permuted_columns_and_decoder_bit_identical`;
    `test_constant_family_swap_changes_nothing`;
    `test_informative_family_swap_changes_the_grid`;
    `test_vsn_weights_sum_to_one_per_decision_over_encoder_variables`;
    `test_known_family_column_raises_family_feature_known` e
    `test_family_column_absent_from_unknown_reals_raises` (C5; nada emitido);
    `test_encoder_length_mismatch_refused`; `test_wrong_sha_raises_before_load` (C7);
    `test_settings_report_the_accelerator`;
  - contrato `[fake, real]`: `test_attribution_identity_matches_the_grid_method`;
    `test_donors_that_are_not_permutations_refused`;
    `test_permuted_keys_are_family_and_one_based_k`; `test_wrong_sha_raises`.
- **O que fazer (concept §1 item 4, I6–I8; ADR 7.3.0002 item 1):** a assinatura do
  concept §4; a troca, a extração dos doadores e a VSN conforme §1; `_emit` recebe o
  dataloader; `_best_sample_by_decision` compartilhado.
- **Critério de aceite (CA7; I6, I7 parte "mesmo processo", I8 parte adapter; C5, C7):**
  testes verdes; goldens da 7.1 intocados.
- **Verificação (T2 — composition root):**
  ```bash
  uv run --no-sync pytest tests/integration/features/modeling/test_pf_tft_attribution_prediction.py tests/contract/features/modeling/test_tft_checkpoint_predictor_contract.py tests/integration/features/modeling/test_pf_tft_checkpoint_prediction.py -v --no-cov
  git -C "$WTH" diff --exit-code "$BASE" -- tests/integration/features/modeling/test_pf_tft_checkpoint_prediction.py tests/contract/features/modeling/test_tft_trainer_golden.py
  git -C "$WTH" diff -U0 HEAD -- tests/contract/features/modeling/_tft_checkpoint_fixture.py | grep -E '^-[^-]'   # vazio: só acréscimos
  make check-block $PAR
  ```
- **Commit:** `feat(modeling): predição de atribuição a partir do checkpoint pelo port do TFT [7.3/task-11]`

---

### Task 12 — Fornecedor `PredictTftAttributionFromCheckpoints`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/modeling/application/use_cases/predict_tft_attribution_from_checkpoints.py`
  - `tests/unit/features/modeling/application/test_predict_tft_attribution_from_checkpoints.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (fake da Task 11): `test_run_ids_equal_what_train_tft_records`;
  `test_donors_must_be_k_p_permutations_of_the_fold_test_positions` (C1);
  `test_partition_different_from_registry_refused_before_predicting` (CA9 parte);
  `test_family_column_known_in_the_panel_raises_before_predicting` (I8);
  `test_adapter_family_known_error_propagates`; `test_run_outside_allowlist_raises`;
  `test_donor_positions_map_to_sorted_test_decisions`;
  `test_result_carries_family_columns_and_normalizer`;
  `test_emission_outside_request_raises`.
- **O que fazer (concept §4; ADR 7.3.0002 item 1):** espelho do
  `PredictTftFromCheckpoints` (mesmas checagens de declaração, mesma derivação de
  `run_id`, mesma lista permitida e guarda de emissão) mais as três guardas; comando com
  `family_partition` (§1). A partição de referência é **injetada** no construtor
  (`registry_partition: Mapping[str, tuple[str, ...]]`; o composition root passa
  `registry_family_partition()`), e os testes usam uma registry **sintética diferente da
  real** (outras features e outros tamanhos), para que a guarda "partição ≠ registry"
  não passe por coincidência com a registry de produção.
- **Critério de aceite (CA9 parte fornecedor; I8; C1, C5):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/modeling/application/test_predict_tft_attribution_from_checkpoints.py -v --no-cov
  make check-task SLICE=modeling $PAR
  ```
- **Commit:** `feat(modeling): fornecedor das predições de atribuição por checkpoint [7.3/task-12]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 09–12).

---

### Task 13 — `FamilyPermutationPlan` no domain do inference

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/domain/value_objects/permutation_plan.py`
  - `tests/unit/features/inference/domain/test_permutation_plan.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_generates_k_p_permutations_of_range_n`;
  `test_same_input_same_permutations`; `test_golden_n5_kp3_seed130_fold2` (literal
  fixado **e** re-derivação independente no próprio teste com
  `random.Random(130 * 1000 + 2)` e Fisher–Yates de `i = n − 1` a `1`, `r =
  floor(random() · (i + 1))`); `test_seed_formula_is_seed_times_1000_plus_fold`
  (fold 2 ≠ fold 3; mata `seed + fold`); `test_is_not_random_shuffle` (o literal ≠
  `random.shuffle` sob a mesma semente); `test_indices_are_one_based`;
  `test_constants_are_130_10_and_the_algorithm_id`; `test_invalid_inputs_refused`
  (`k_p < 1`, `n < 1`, fold negativo, `bool`);
  `test_raw_construction_with_non_permutation_refused` (construtor direto com uma tupla
  que não é permutação de `range(n_decisions)`, ou com `len(permutations) ≠ k_p` ⇒
  `ValueError` no `__post_init__`).
- **O que fazer (concept §4 "Inference", I6; ADR 7.3.0005 H3-PI):** VO stdlib e as
  constantes do §1.
- **Critério de aceite (CA8; I6):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/inference/domain/test_permutation_plan.py -v --no-cov
  make check-task SLICE=inference $PAR
  ```
- **Commit:** `feat(inference): plano de permutação por fold no domain [7.3/task-13]`

---

### Task 14 — Tabelas silver `fact_permuted_predictions` e `fact_vsn_weights`

> **> 5 arquivos, justificado:** dois schemas e seus testes, o registry e o teste do
> registry, as duas docstrings "1..3 → 1..4 níveis" (mecânicas) e o registry-leve do
> `FakeAnalyticsRepository`, que tem de conhecer as tabelas novas no mesmo commit em
> que o `SILVER_REGISTRY` as ganha.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/fact_permuted_predictions_schema.py`
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/fact_vsn_weights_schema.py`
  - `tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_fact_permuted_predictions_schema.py`
  - `tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_fact_vsn_weights_schema.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/schemas/silver_registry.py`
  - `src/financial_forecasting/features/analytics_store/application/ports/out/analytics_repository.py` (docstring L18–21)
  - `src/financial_forecasting/features/analytics_store/adapters/out/parquet/parquet_analytics_repository.py` (docstring L12)
  - `tests/unit/features/analytics_store/adapters/out/parquet/schemas/test_silver_registry.py`
  - `tests/fakes/features/analytics_store/in_memory_analytics_repository.py` (`FakeAnalyticsRepository`: `_PK_BY_TABLE`, `_PARTITION_BY_TABLE` e a política append-only das duas tabelas novas, partição `(asset, feature_set_name, run_id, year)`)
- **Testes primeiro:** `test_primary_key_repeated_refused` (as duas);
  `test_family_outside_vocabulary_refused`; `test_none_iff_index_zero` (parametrizado:
  `none` com índice 2 e família com índice 0 recusados); `test_negative_index_refused`;
  `test_partition_by_has_run_id` (`(asset, feature_set_name, run_id, year)`);
  `test_vsn_family_vocabulary_includes_none`; `test_registry_has_seven_tables`;
  `test_schema_version_is_1_for_the_new_tables`;
  `test_fake_registry_mirrors_silver_registry` (novo, em `test_silver_registry.py`: para
  toda tabela do `SILVER_REGISTRY`, PK, partição e política do registry-leve do
  `FakeAnalyticsRepository` iguais — não existia teste de paridade; ele trava o drift
  das 7 tabelas).
- **O que fazer (concept §1 item 5, I19; ADR 7.3.0002 item 4):** colunas, PK e
  partição do ADR; `schema_version = 1` nas duas (o mesmo das tabelas existentes; o
  `test_silver_schema_version_matches_every_silver_table` do composition root exige um
  só valor); `fact_oos_predictions` intocado.
- **Critério de aceite (CA10 parte schema; I19):** testes verdes.
- **Verificação (T1 com `shared` no `SLICE`, porque o teste de `shared` lê o `SILVER_REGISTRY`):**
  ```bash
  uv run --no-sync pytest tests/unit/features/analytics_store tests/unit/shared/test_composition_root.py::test_silver_schema_version_matches_every_silver_table -v --no-cov
  make check-task SLICE='analytics_store shared' $PAR
  ```
- **Commit:** `feat(analytics-store): tabelas silver das predições permutadas e dos pesos da VSN [7.3/task-14]`

---

### Task 15 — Escritores `PersistPermutedPredictions` e `PersistVsnWeights`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/analytics_store/application/use_cases/persist_permuted_predictions.py`
  - `src/financial_forecasting/features/analytics_store/application/use_cases/persist_vsn_weights.py`
  - `tests/unit/features/analytics_store/application/test_persist_permuted_predictions.py`
  - `tests/unit/features/analytics_store/application/test_persist_vsn_weights.py`
- **Arquivos a modificar:**
  - `tests/integration/features/analytics_store/test_parquet_analytics_repository.py`
- **Testes primeiro:** unit (`FakeAnalyticsRepository`, com as tabelas novas desde a Task 14):
  `test_rows_cell_by_cell`; `test_target_timestamp_follows_persist_predictions`
  (mesma entrada ⇒ mesmo `target_timestamp_utc` do `PersistPredictions`);
  `test_year_is_the_decision_year`; `test_one_write_per_run_call`;
  `test_identity_entry_must_be_none_zero`; `test_vsn_family_from_the_command`;
  integração (Parquet real): `test_permuted_round_trip_and_run_filter_pushdown` (dois
  runs gravados; leitura com `run_id` devolve só um);
  `test_vsn_round_trip_and_run_filter_pushdown`.
- **O que fazer (concept §1 item 5; ADR 7.3.0002 item 4):** comandos por run do §1;
  satisfazem os ports do consumidor por duck typing (padrão do `PersistPredictions`).
- **Critério de aceite (CA10 persistência e leitura de volta; I19):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/analytics_store/application tests/integration/features/analytics_store -v --no-cov
  make check-task SLICE=analytics_store $PAR
  ```
- **Commit:** `feat(analytics-store): escritores por run das predições permutadas e da VSN [7.3/task-15]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 13–15).

---

### Task 16 — Ports do consumidor da atribuição (reais já existentes)

> **> 5 arquivos, justificado:** três ports de um método, três fakes e uma suíte
> `[fake, real]`, mais o teste do gate por `(slice, nome)`.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/ports/out/checkpoint_attribution_predictor.py`
  - `src/financial_forecasting/features/inference/application/ports/out/permuted_prediction_persister.py`
  - `src/financial_forecasting/features/inference/application/ports/out/vsn_weight_persister.py`
  - `tests/fakes/features/inference/in_memory_checkpoint_attribution_predictor.py`
  - `tests/fakes/features/inference/in_memory_permuted_prediction_persister.py`
  - `tests/fakes/features/inference/in_memory_vsn_weight_persister.py`
  - `tests/contract/features/inference/test_attribution_ports_contract.py`
- **Arquivos a modificar:**
  - `tests/architecture/test_port_coverage_gate.py` (acréscimo `test_real_repo_attribution_ports_resolve`)
- **Testes primeiro:** contrato (o módulo importa fakes e reais **pelo nome**):
  `test_predictor_identity_and_permuted_keys` (real = `PredictTftAttributionFromCheckpoints`
  com os fakes do modeling); `test_predictor_refuses_non_permutation_donors`;
  `test_persisters_write_one_run_and_read_back` (real = `Persist*` com
  `FakeAnalyticsRepository`); `test_persisters_refuse_identity_not_none_zero`;
  `test_predictor_refuses_partition_different_from_its_registry` (o fake do predictor
  tem `registry_partition` configurável e, no contrato, sintética ≠ a real, a mesma
  dada ao real);
  gate: `test_real_repo_attribution_ports_resolve` (`("inference", nome)` → real pela
  regra #93, contrato satisfazendo o predicado; nenhum homônimo em `modeling` nem em
  `evaluation`).
- **O que fazer (concept §4 "Inference"; ADR 0.0.0053):** anotações **textualmente
  iguais** às dos fornecedores; DTOs só sob `TYPE_CHECKING`.
- **Critério de aceite (CA9 parte "suíte `[fake, real]` dos ports novos e
  port-coverage"):** suíte verde; `check_port_coverage.py --list` com os três ports, fake,
  real e contrato, sem baseline.
- **Verificação (T3 — `tests/architecture/`):**
  ```bash
  uv run --no-sync pytest tests/contract/features/inference/test_attribution_ports_contract.py tests/architecture/test_port_coverage_gate.py -v --no-cov
  uv run --no-sync python scripts/check_port_coverage.py --list
  make check $PAR
  ```
- **Commit:** `feat(inference): ports do consumidor da atribuição com fakes e contrato [7.3/task-16]`

---

### Task 17 — Port `AttributionManifest` (perna fake; baseline do ADR 6.1.0005)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/ports/out/attribution_manifest.py`
  - `tests/fakes/features/inference/in_memory_attribution_manifest.py`
  - `tests/contract/features/inference/test_attribution_manifest_contract.py`
- **Arquivos a modificar:**
  - `scripts/arch_baseline.toml` (entrada temporária `AttributionManifest`, §1)
  - `tests/architecture/test_port_coverage_gate.py` (lista literal → `["AttributionManifest", "Hasher"]`, comentário citando o ADR 6.1.0005)
- **Testes primeiro** (contrato `[fake]`; a perna real entra na Task 18):
  `test_absent_cohort_is_none`; `test_started_then_completed_merges_first_write_fields`
  (`environment` e `checkpoint_sha256` da 1ª escrita nunca sobrescritos);
  `test_entry_has_the_plan_identity_and_partition` (campos do §1);
  `test_runs_shape_problem_is_unreadable`.
- **O que fazer (ADR 7.3.0002 item 2; padrão do ADR 7.1.0004):**
  `AttributionManifest.recorded(cohort_id)` e `record_run(cohort_id, run_id, entry)`;
  o fake reusa `merge_run_entry`/`apply_run_entry`.
- **Critério de aceite (CA9 parte manifesto):** suíte verde; `check_port_coverage.py`
  verde **com** a entrada temporária.
- **Verificação (T3 — baseline e `tests/architecture/`):**
  ```bash
  uv run --no-sync pytest tests/contract/features/inference/test_attribution_manifest_contract.py tests/architecture/test_port_coverage_gate.py -v --no-cov
  uv run --no-sync python scripts/check_port_coverage.py --list
  make check $PAR
  ```
- **Commit:** `feat(inference): port do manifesto da atribuição com fake e contrato [7.3/task-17]`

---

### Task 18 — `JsonAttributionManifest` (perna real; reverte o baseline)

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/adapters/out/filesystem/json_attribution_manifest.py`
- **Arquivos a modificar:**
  - `tests/contract/features/inference/test_attribution_manifest_contract.py` (perna real)
  - `scripts/arch_baseline.toml` (reverte a entrada da Task 17)
  - `tests/architecture/test_port_coverage_gate.py` (lista literal de volta a `["Hasher"]`; acréscimo `test_real_repo_attribution_manifest_resolves` por `("inference", "AttributionManifest")`)
- **Testes primeiro:** os da Task 17 parametrizados `[fake, json]`;
  `test_write_is_atomic_by_replace`; `test_file_path_is_attribution_manifest_json`.
- **O que fazer:** arquivo do §1, escrita atômica (`.tmp-<pid>` + `os.replace`).
- **Critério de aceite (CA9 parte; port-coverage sem baseline):** suíte verde; o bloco
  `[port_coverage]` de `scripts/arch_baseline.toml` sem diferença contra `$BASE` (a
  remoção de `[schema_literals]` da Task 07 é a única diferença aceita, §1).
- **Desvio declarado do padrão do ADR 6.1.0005:** o par é revertido, mas
  `test_port_coverage_gate.py` **não** volta byte a byte ao `$BASE`, porque ganha
  `test_real_repo_attribution_manifest_resolves` (e a Task 16 já acrescentou
  `test_real_repo_attribution_ports_resolve`). O grep final confere só a lista literal
  `["Hasher"]`, não o arquivo inteiro.
- **Verificação (T3):**
  ```bash
  uv run --no-sync pytest tests/contract/features/inference/test_attribution_manifest_contract.py tests/architecture/test_port_coverage_gate.py -v --no-cov
  git -C "$WTH" diff "$BASE" -- scripts/arch_baseline.toml | grep -E '^[+-][^+-]'   # só as linhas "-" das 2 chaves de [schema_literals]
  grep -c 'violating == \["Hasher"\]' "$WTH/tests/architecture/test_port_coverage_gate.py"   # 1
  make check $PAR
  ```
- **Commit:** `feat(inference): manifesto JSON da atribuição [7.3/task-18]`

---

### Task 19 — `RunPermutationInference` e as arestas de dados 1–6

> O use case importa em runtime os DTOs de comando dos fornecedores;
> `unmatched_ignore_imports_alerting = error` reprova o ignore sem import e o
> `bc-independence` reprova o import sem ignore — `.importlinter`, os casos de
> arquitetura e LAYOUT §7 entram no mesmo commit.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/inference/application/use_cases/run_permutation_inference.py`
  - `tests/unit/features/inference/application/test_run_permutation_inference.py`
- **Arquivos a modificar:**
  - `.importlinter` (arestas 1–6 do concept §8, uma linha cada, comentário: ADR 7.3.0002, ADR 0.0.0053; exceção do **módulo**; comentário de cabeçalho do `bc-independence` 28 → 34)
  - `docs/LAYOUT.md` §7 (as seis arestas; contagem de arestas de runtime 28 → 34)
  - `tests/architecture/test_import_contracts.py` (os seis casos `other-inference-module-imports-*` do §1)
  - `tests/fakes/features/evaluation/fake_silver_table_reader.py` (`SILVER_PARTITIONS` ganha `fact_permuted_predictions` e `fact_vsn_weights` com `(asset, feature_set_name, run_id, year)` — o use case lê as duas na re-conferência; o mesmo fake serve à Task 30)
- **Testes primeiro** (fakes das Tasks 16–17, fakes espelho da 7.1, `FakeSilverTableReader`):
  - `test_identity_outside_policy_raises_and_writes_nothing` (C6; manifesto intocado);
  - `test_strict_in_the_recorded_environment_tolerance_across` (política da 7.2);
  - `test_cross_environment_with_equal_keys_forces_tolerance`;
  - `test_manifest_started_before_first_write_with_plan_identity` (semente, K_p,
    algoritmo, fold, n, partição e `partition_hash`);
  - `test_rows_carry_permutation_seed_algorithm_and_partition_hash` (o
    `partition_hash` = `FamilyPartitionHash` da partição **do comando**; mata o hash da
    registry e o literal fixo);
  - `test_same_permutation_for_every_seed_and_family` (I6: os doadores passados ao
    predictor são os do plano por fold, iguais entre seeds e famílias);
  - `test_completed_run_is_reconferred_by_reading_and_skipped` (status `verified`, o
    predictor não é chamado);
  - `test_partial_run_raises_partial_attribution` (C8; parametrizado: linhas sem
    `completed`; k faltando; VSN faltando);
  - `test_guardrail_applied_with_from_raw` (grade crua cruzada gravada crua, guardrail
    monótono);
  - `test_partition_refused_by_supplier_before_any_write` (CA9);
  - `test_lock_released_on_error`; `test_artifact_changed_propagates` (C7);
  - arquitetura: os seis casos do §1; `test_real_repo_has_zero_broken_contracts`.
- **O que fazer (concept §1 item 6, I6, I7, I17, I19; ADR 7.3.0002 itens 2–3):** ordem
  do §1; por seed do candidato; `AttributionRunOutcome` por run.
- **Critério de aceite (CA9; I6, I7, I17 parte, I19 retomada; C6, C7, C8):** testes
  verdes; `lint-imports` com exatamente seis arestas novas.
- **Verificação (T3):**
  ```bash
  uv run --no-sync pytest tests/unit/features/inference/application/test_run_permutation_inference.py tests/architecture/test_import_contracts.py -v --no-cov
  uv run --no-sync lint-imports
  git -C "$WTH" diff "$BASE" -- .importlinter | grep -cE '^\+\s*financial_forecasting\..* -> '   # = 6
  make check $PAR
  ```
- **Commit:** `feat(inference): inferência por permutação com manifesto write-ahead [7.3/task-19]`

---

### Task 20 — Wiring, subcomando `attribute` e ponta a ponta sintético

> **> 5 arquivos, justificado:** a fábrica, o subcomando, o despacho e os três testes
> que os cobrem nascem juntos.

- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py` (`permutation_inference_for(path)` com o treinador `cpu`)
  - `src/financial_forecasting/features/inference/adapters/in/cli/inference_commands.py` (`attribute`)
  - `src/financial_forecasting/cli.py` (`attribute --ablation-cohort`, `--cross-environment`, `--break-stale-lock`; lê o `[partition]` pelo loader do modeling)
  - `tests/unit/test_cli.py`
  - `tests/unit/shared/test_composition_root.py`
- **Arquivos a criar:**
  - `tests/integration/features/inference/test_run_permutation_inference.py`
- **Testes primeiro:** composition root: `test_permutation_inference_uses_the_cpu_trainer`;
  `test_permutation_inference_wires_no_evaluation_use_case`; CLI:
  `test_attribute_help`; integração (cohort sintético minúsculo treinado em `tmp_path`,
  padrão do e2e do `infer`; `slow`): `test_attribute_writes_every_run_strict_with_zero_diff`;
  `test_row_counts_are_41_times_test_rows_and_vsn_decisions_times_variables`;
  `test_second_attribute_verifies_all_and_writes_zero`; `test_manifest_is_complete`;
  `test_no_gold_directory_created` (I9).
- **O que fazer (concept §1 item 6; ADR 7.3.0004 item 2):** saída do §1.
- **Critério de aceite (CA9 ponta a ponta; I9; base de CA15):** testes verdes.
- **Verificação (T2 — composition root):**
  ```bash
  uv run --no-sync pytest tests/integration/features/inference/test_run_permutation_inference.py tests/unit/test_cli.py tests/unit/shared/test_composition_root.py -v --no-cov
  make check-block $PAR
  ```
- **Commit:** `feat(inference): subcomando attribute e wiring da inferência por permutação [7.3/task-20]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 16–20).

---

### Task 21 — `H3Parameters` e o catálogo das regras de H3

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/h3_parameters.py`
  - `tests/unit/features/evaluation/test_h3_parameters.py`
  - `tests/unit/features/evaluation/_h3_parameters.py` (helper `h3_block()`/`h3_parameters()` com os valores do §1 e a ablação sintética)
  - `tests/integration/features/evaluation/test_h3_catalog_matches_permutation_plan.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_round_trip`; `test_unknown_and_missing_keys_refused_with_dotted_path`
  (C11); `test_identifier_outside_the_catalog_refused`; `test_sentinel_value_refused`
  (`"__FILL_AFTER_FREEZE__"` em cada um dos três campos);
  `test_partition_must_cover_the_four_families_disjointly`;
  `test_interval_level_is_0_9875` (`1 − 0.05/4`; mata o nível sem Bonferroni);
  `test_ablation_models_are_the_loco_versions`; `test_k_p_and_reps_positive_ints`;
  `test_raw_construction_with_invalid_field_refused` (construtor direto sem
  `from_mapping`: `family_alpha` fora de (0, 1), `partition_hash` fora de 64 hex,
  famílias ≠ as 4 ⇒ `ValueError` no `__post_init__`);
  integração `test_catalog_algorithm_k_p_and_seed_equal_the_inference_plan` (I17:
  `PERMUTATION_ALGORITHM`, `K_P`, `PERMUTATION_SEED` = os do helper; compõe os slices só
  no teste).
- **O que fazer (concept §4; ADR 7.3.0005):** `H3_RULE_CATALOG`, o VO e `as_payload`
  como única serialização.
- **Critério de aceite (CA11 parte C11 e I17):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_h3_parameters.py tests/integration/features/evaluation/test_h3_catalog_matches_permutation_plan.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): regras nomeadas do bloco de H3 do pré-registro [7.3/task-21]`

---

### Task 22 — `Preregistration` aceita `[h3]` (opcional, proibido no r0)

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/preregistration.py`
  - `tests/unit/features/evaluation/test_preregistration_value_object.py`
  - `tests/unit/features/evaluation/test_preregistration_immutable_hash.py`
  - `tests/unit/features/evaluation/_preregistration_payload.py` (acréscimo `r3_payload()`)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_h3_block_forbidden_in_revision_0`;
  `test_h3_families_must_be_the_adr_0016_four`; `test_ablation_models_distinct_from_candidate_and_comparators`;
  `test_plan_with_h3_round_trips`; `test_h3_block_changes_the_hash`;
  `test_r0_to_r2_payload_hashes_unchanged`.
- **O que fazer (concept §4, I18; C11):** campo `h3: H3Parameters | None`, chave em
  `_OPTIONAL_KEYS`, cruzamentos no `__post_init__`, `as_payload` só com a chave.
- **Critério de aceite (CA11 parte; I18 hashes; C11):** testes verdes;
  `test_preregistration_consistency.py` verde sem mudança.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_preregistration_value_object.py tests/unit/features/evaluation/test_preregistration_immutable_hash.py tests/integration/features/evaluation/test_preregistration_consistency.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): pré-registro aceita o bloco de H3 opcional [7.3/task-22]`

---

### Task 23 — Registros e reduções por run (VOs)

> **> 5 arquivos, justificado:** cinco VOs frozen stdlib de uma responsabilidade cada,
> testados num arquivo só.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/permuted_forecast_record.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/vsn_weight_record.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/permuted_run_losses.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/ablation_run_losses.py` (com `merge_ablation_parts`)
  - `src/financial_forecasting/features/evaluation/domain/value_objects/vsn_run_weights.py` (com `reduce_vsn_run`)
  - `tests/unit/features/evaluation/test_h3_run_reductions_value_objects.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_permuted_record_none_iff_index_zero`;
  `test_permuted_record_family_vocabulary`; `test_run_losses_lengths_match_decisions`;
  `test_run_losses_decisions_strictly_increasing`; `test_reduce_vsn_run_groups_by_decision`;
  `test_reduce_vsn_run_refuses_duplicate_variable`; `test_ablation_losses_merge_disjoint_parts`
  e `test_overlapping_parts_refused`; `test_raw_construction_refused` (parametrizado nos
  cinco VOs: o construtor direto com a invariante violada ⇒ `ValueError`).
- **O que fazer (concept §4 "value_objects/permuted_run_losses.py"; I19):** VOs do
  concept; as funções de redução de perda ficam no serviço (§1).
- **Critério de aceite (CA12 base; I19 parte reduções):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_h3_run_reductions_value_objects.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): registros e reduções por run da atribuição [7.3/task-23]`

---

### Task 24 — `FamilyLossDifferentials` e `AttributionAssembly` (aresta 7)

> **> 5 arquivos, justificado:** a montagem constrói `CoverageSeries` (aresta de dados 7);
> `.importlinter`, o caso de arquitetura e LAYOUT §7 entram no mesmo commit; a fábrica de
> cohort sintético ganha os registros novos.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/family_loss_differentials.py`
  - `src/financial_forecasting/features/evaluation/domain/services/attribution_assembly.py` (com `reduce_permuted_run` e `reduce_ablation_run`)
  - `tests/unit/features/evaluation/gold/test_attribution_assembly.py`
- **Arquivos a modificar:**
  - `.importlinter` (aresta 7; comentário de cabeçalho do `bc-independence` 34 → 35)
  - `docs/LAYOUT.md` §7 (34 → 35)
  - `tests/architecture/test_import_contracts.py` (`bc-independence:other-evaluation-module-imports-quantile-forecast-for-h3`)
  - `tests/unit/features/evaluation/gold/_cohort_factory.py` (só acréscimo: `with_permuted(...)`, `with_ablation(...)`, `with_vsn(...)` geram registros sintéticos pelos mesmos runs)
- **Testes primeiro:** `test_permutation_d_t_equals_the_hand_computed_value` (2 seeds,
  K_p = 2, 3 decisões: média nas seeds da média nas k de L^perm − L^id);
  `test_loco_d_t_is_seed_mean_minus_seed_mean` (mata a média das diferenças por seed
  pareada); `test_losses_use_value_guardrail` (`value_raw ≠ value_guardrail` muda o
  resultado se trocado); `test_decisions_are_the_h1_h7_intersection`;
  `test_decision_sets_differ_between_methods_is_undefined`;
  `test_missing_seed_k_family_or_configuration_is_undefined` (parametrizado, I11);
  `test_wrong_permutation_seed_or_algorithm_is_undefined` (C9);
  `test_partition_hash_mismatch_is_undefined` (I17; mata a comparação ausente);
  `test_alignment_rules_from_series_assembly` (duplicata, nível faltando, realizado
  faltando ⇒ `undefined` com o motivo da regra pública da 7.2);
  `test_violation_is_never_an_alignment_finding`; `test_seed_and_k_profiles`;
  `test_permutation_uses_its_own_identity_not_fact_oos` (I7: no fixture, a grade de
  identidade de `fact_permuted_predictions` difere da linha de teste de
  `fact_oos_predictions` da mesma decisão; d_t sai da identidade da tabela permutada —
  mata a troca de fonte); `test_raw_construction_of_family_loss_differentials_refused`
  (comprimentos ≠ decisões, horizonte fora de `(1, 7)`, família fora das 4, método
  fora de `{permutation, loco}`).
- **O que fazer (concept §4, I10, I11; ADR 7.3.0001 item 1):** VO e serviço;
  `PinballScore.per_point_losses` sobre `CoverageSeries` construída dos valores
  persistidos (nunca `from_raw`).
- **Critério de aceite (CA12; I10, I11, I17 conferência; C9 parte):** testes verdes;
  `lint-imports` com exatamente uma aresta nova nesta Task.
- **Verificação (T3):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold/test_attribution_assembly.py tests/architecture/test_import_contracts.py -v --no-cov
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  git -C "$WTH" diff "$BASE" -- .importlinter | grep -cE '^\+\s*financial_forecasting\..* -> '   # = 7
  make check $PAR
  ```
- **Commit:** `feat(evaluation): montagem das séries d_t de H3 nos dois métodos [7.3/task-24]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 21–24).

---

### Task 25 — `FamilyContribution`, `linear_quantile` e o oráculo `arch`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/family_contribution.py`
  - `tests/unit/features/evaluation/test_family_contribution.py`
  - `tests/integration/features/evaluation/test_h3_basic_interval_vs_arch.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:**
  - unit (casos analíticos): `test_importance_share_and_delta`;
    `test_linear_quantile_is_type_7` (casos à mão); `test_linear_quantile_propagates_infinity_never_nan`;
    `test_basic_interval_formula` (`[2Δ̂ − q_{1−a/2}, 2Δ̂ − q_{a/2}]`; mata o percentil);
    `test_level_uses_a_over_two_with_a_0_0125` (B = 1000 réplicas conhecidas; nível 0,95
    daria outro limite — mata o Bonferroni ausente);
    `test_point_total_nonpositive_is_undefined` (h = 1 e h = 7, I14);
    `test_nonpositive_replicas_enter_as_plus_inf_upper_minus_inf_lower` (contagem
    pequena: os dois limites alargam, valores à mão; mata o descarte e o mesmo sinal nas
    duas caudas; parametrizado com Σ* ≤ 0 **só em h = 7** e **só em h = 1** — mata a
    regra aplicada a um horizonte só); `test_many_nonpositive_replicas_make_bounds_infinite_and_method_ok`
    (> a/2 · B); `test_nonpositive_counts_by_horizon`;
    `test_side_is_the_sign_of_delta_hat`; `test_interval_excluding_zero_on_the_opposite_side_is_undefined`;
    `test_bound_exactly_zero_is_undefined`; `test_heterogeneous_iff_some_ok_family_excludes_zero`;
    `test_same_indices_for_both_horizons_and_all_families` (uma `BootstrapIndices`; mata
    índices por família);
  - integração: `test_basic_interval_equals_arch_conf_int_basic` (mesmos índices,
    nenhuma réplica com Σ* ≤ 0, `abs_tol = 1e-12`); `test_linear_quantile_equals_numpy_percentile_on_finite`.
- **O que fazer (concept §4, I13–I15; ADR 7.3.0005 H3-CI, H3-LEVEL, H3-NEG, H3-READ):**
  `FamilyShare`, `FamilyContributionReport`, `FamilyContribution.evaluate`,
  `linear_quantile`.
- **Critério de aceite (CA13 parte contribuição e oráculo; I13, I14, I15 por método):**
  testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_family_contribution.py tests/integration/features/evaluation/test_h3_basic_interval_vs_arch.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): participação por família com intervalo básico de Bonferroni [7.3/task-25]`

---

### Task 26 — `ContributionAgreement` e `VsnSummary`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/contribution_agreement.py`
  - `src/financial_forecasting/features/evaluation/domain/services/vsn_summary.py`
  - `tests/unit/features/evaluation/test_contribution_agreement.py`
  - `tests/unit/features/evaluation/test_vsn_summary.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro:** `test_sustained_when_same_family_excludes_zero_in_both_with_same_sign`;
  `test_opposite_signs_not_sustained_status_ok`; `test_different_families_not_sustained`;
  `test_any_undefined_method_gives_undefined_with_reason` (`sustained is False`,
  `heterogeneous = None` no método indefinido); `test_label_is_exact`;
  `test_vsn_per_decision_seed_mean_then_percentiles` (tipo 7); `test_vsn_family_is_the_sum_of_its_variables`;
  `test_non_family_variables_reported_apart`; `test_vsn_label_is_exact`.
- **O que fazer (concept §4, I15; ADR 7.3.0005 H3-READ, H3-VSN).**
- **Critério de aceite (CA13 parte leitura e rótulos; I15):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/test_contribution_agreement.py tests/unit/features/evaluation/test_vsn_summary.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): leitura mecânica de H3 e resumo da VSN [7.3/task-26]`

---

### Task 27 — `RefreshParameters.h3_parameters` pela derivação única

> **> 5 arquivos, justificado:** o campo obrigatório quebra cada construção literal de
> `RefreshParameters` nos testes (mecânico; precedente: 7.2 Task 16).

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
  - `tests/unit/features/evaluation/test_refresh_command_from.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/unit/features/evaluation/test_scorecard_evidence_mapper.py`
  - construções de `RefreshParameters`: `tests/contract/features/evaluation/_gold_inputs.py`,
    `tests/contract/features/evaluation/test_gold_generation_reader_contract.py`,
    `tests/contract/features/evaluation/test_gold_store_contract.py`,
    `tests/integration/features/evaluation/test_refresh_gold.py`,
    `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
    (a lista exata é a que a 7.2 deixar, conferida pelo `grep -rlE "RefreshParameters\("`
    da verificação de gap do §1 — hoje bate; diferença ⇒ `[deviation]`)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_r0_to_r2_derive_no_h3_parameters`; `test_plan_with_h3_derives_the_block`;
  `test_check_manifest_refuses_a_divergent_h3_block`; `test_manifest_without_h3_parameters_is_corrupt`
  (C10); `test_as_mapping_round_trip_with_h3`.
- **O que fazer (concept §4; I17; ADR 7.3.0001 item 3):** campo, chave obrigatória,
  `as_mapping`/`from_mapping`; `refresh_command_from` preenche com `prereg.h3`.
- **Critério de aceite (I17 derivação única; C10):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation tests/contract/features/evaluation tests/integration/features/evaluation/test_refresh_gold.py -q --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): bloco de H3 na derivação única do refresh [7.3/task-27]`

---

### Task 28 — `H3Reports` nos insumos do gold

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/refresh_gold.py` (passa `EMPTY_H3_REPORTS`; o cálculo entra na Task 30)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py`
  - `tests/contract/features/evaluation/_gold_inputs.py` (`completed_inputs()` com `h3_reports` cheios: um método `ok`, uma família `undefined`, limite infinito, VSN; `completed_inputs_without_h3()`)
- **Arquivos a criar:** nenhum.
- **Testes primeiro:** `test_h3_reports_validate_their_fields`; `test_blocked_inputs_have_no_h3_reports`;
  `test_completed_inputs_accept_h3_reports`.
- **O que fazer (concept §4 `H3Reports`):** `H3Reports`, `EMPTY_H3_REPORTS`,
  `GoldInputs.h3_reports` (BLOCKED ⇒ vazio). Nenhum import do inference nem do modeling
  neste módulo.
- **Critério de aceite (I16 BLOCKED; base de CA14):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold tests/contract/features/evaluation -q --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): relatórios de H3 nos insumos do gold [7.3/task-28]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 25–28).

---

### Task 29 — Tabelas gold de H3: schemas, builders, registro e matrícula

> **> 5 arquivos, justificado:** os schemas entram em `GOLD_SCHEMAS`, e a regra
> "COMPLETED lista toda tabela" reprova o refresh sem os builders registrados — schema,
> builders e registro nascem juntos; a guarda de matrícula fica aqui porque os builders
> são os últimos módulos de `src/` da Stage.

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/h3_importance.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/h3_shares.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/h3_reading.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/h3_vsn.py`
  - `tests/contract/features/evaluation/test_h3_gold_builders.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
  - `src/financial_forecasting/composition_root.py` (registra os quatro builders)
  - `tests/contract/features/evaluation/test_gold_builder_contract.py` (ids novos)
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py` (conjuntos exatos)
  - `tests/unit/shared/test_composition_root.py` (`build_order` com 19 builders)
  - `tests/integration/features/evaluation/test_refresh_gold.py` (`_H3_TABLES`; as quatro existem com zero linhas no cenário sem `[h3]`)
  - `tests/architecture/test_stage_7_3_regression_guards.py` (`test_stage_7_3_new_modules_are_enrolled`; `test_h3_builders_dtos_and_domain_never_import_inference_or_modeling`)
- **Testes primeiro:** `test_importance_rows_cell_by_cell` (agregada, perfil por seed e
  por k); `test_shares_rows_cell_by_cell`; `test_infinite_bound_maps_to_null_with_flag`;
  `test_undefined_method_rows_carry_reason_and_null_measures`;
  `test_reading_single_row_with_label_and_counts`; `test_vsn_rows_by_variable_and_family`;
  `test_without_h3_inputs_all_four_tables_are_empty`.
- **O que fazer (concept §4; ADR 7.3.0001 item 4):** schemas com as colunas do §1, em
  `GOLD_SCHEMAS` e `CONFIRMATORY_TABLES`; builders de mapeamento puro,
  `depends_on = {QUALITY_CHECKS}`, `runs_when_blocked = False`.
- **Critério de aceite (CA14 parte "4 tabelas, zero linhas sem `[h3]`, BLOCKED sem
  elas"; CA13 "limite infinito null + flag"; I16):** testes verdes.
- **Verificação (T3 — `tests/architecture/` e composition root):**
  ```bash
  uv run --no-sync pytest tests/contract/features/evaluation tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py tests/integration/features/evaluation/test_refresh_gold.py tests/architecture/test_stage_7_3_regression_guards.py -q --no-cov
  make check $PAR
  ```
- **Commit:** `feat(evaluation): tabelas gold de H3 [7.3/task-29]`

---

### Task 30 — `RefreshGold` publica H3

- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/refresh_gold.py`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py`
  - `tests/unit/features/evaluation/gold/_cohort_factory.py` (só acréscimo, se a Task 24 não cobrir o cenário)
  - `tests/integration/features/evaluation/test_refresh_gold.py` (sem `[h3]`: zero linhas, nenhuma leitura das tabelas novas)
- **Arquivos a criar:** nenhum.
- **Testes primeiro** (fakes; `FakeMcsBackend` contando chamadas):
  `test_permuted_and_vsn_read_one_run_per_call_with_run_id_filter` (CA14b);
  `test_ablation_partition_read_once_per_year_never_without_year` (mata a leitura por
  run e a leitura sem ano); `test_confirmatory_records_never_read_fs_all_ablation` (I3);
  `test_one_bootstrap_indices_call_serves_both_methods` (bloco = `block_length_rule(7,
  max b̂ das 16 séries)`; `optimal_block_length` chamado 16 vezes);
  `test_invalid_series_or_arithmetic_error_gives_undefined_reading` (C9; nada aborta);
  `test_h3_failure_never_changes_other_tables` (I16);
  `test_without_h3_block_no_h3_read`; `test_blocked_generation_has_no_h3`;
  `test_unexpected_exception_propagates` (C9 "erro de programação");
  `test_contribution_receives_the_bonferroni_level` (o `level` passado ao
  `FamilyContribution.evaluate` nos dois métodos é `h3_parameters.interval_level` =
  0,9875, nunca 0,95 nem um literal; mata o Bonferroni perdido no wiring).
- **O que fazer (concept §1 item 8, I12, I16, I19; ADR 7.3.0001 itens 2–3):** etapa
  `_timed("h3", …)` depois da conformal, só sem bloqueio e com `h3_parameters`: runs do
  candidato → leitura e redução por run das duas tabelas → `dim_run` da ablação pelo
  `cohort_id` do bloco → leitura por ano (§1) → `AttributionAssembly` → um plano de
  bootstrap → `FamilyContribution` ×2 → `ContributionAgreement` → `VsnSummary` →
  `H3Reports`; o manifesto lista o `cohort_id` da ablação.
- **Critério de aceite (CA14b parte leitura; I12, I16, I19; C9):** testes verdes.
- **Verificação (T1):**
  ```bash
  uv run --no-sync pytest tests/unit/features/evaluation/gold/test_refresh_gold_use_case.py tests/integration/features/evaluation/test_refresh_gold.py -v --no-cov
  make check-task SLICE=evaluation $PAR
  uv run --no-sync pytest tests/architecture/test_unit_evaluation_purity.py --no-cov
  ```
- **Commit:** `feat(evaluation): refresh do gold publica a leitura de H3 [7.3/task-30]`

---

### Task 31 — Ponta a ponta do refresh de H3 e teto de memória

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_h3_refresh_end_to_end.py`
  - `tests/integration/features/evaluation/test_h3_refresh_memory.py`
- **Arquivos a modificar:** nenhum.
- **Testes primeiro** (silver sintético em `tmp_path`, adapters reais de arquivo;
  planos sintéticos r2 e r3 por `r2_payload()`/`r3_payload()` com `cohort_id` sintético):
  - e2e: `test_known_effect_family_is_sustained` (permutar uma família piora mais h+7
    que h+1; ablação coerente; d_t não constante; Σ com folga);
    `test_null_case_both_methods_ok_and_not_sustained`;
    `test_opposite_sides_between_methods_not_sustained_ok`;
    `test_undefined_method_gives_undefined_reading_with_reason`;
    `test_partition_hash_mismatch_makes_permutation_undefined`;
    `test_completed_generation_has_the_four_tables_and_h3_in_manifest`;
    `test_shares_level_is_0_9875` (toda linha `ok` de `gold_h3_shares` com `level ==
    0.9875`);
    `test_r2_plan_writes_empty_h3_tables`; `test_blocked_generation_has_no_h3_tables`;
    `test_r2_and_r3_same_verdict_and_same_previous_tables` (I16; sem
    `preregistration_ref`); `test_manifest_before_this_stage_is_unreadable` (C10);
    `test_real_use_cases_through_the_composition_root` (`wire_dependencies`).
  - memória (`slow`): `test_ablation_partition_read_once_per_year_at_real_size` (leitor
    que gera ~1 M linhas sob demanda por ano — 5 × 6 × 10 × ~3 500 — e devolve o
    superconjunto da partição, como o adapter; conta chamadas e linhas, e mede o pico do
    `tracemalloc` durante o refresh: ≤ 512 MiB, o mesmo limiar do teste seguinte);
    `test_peak_memory_bounded_and_flat_in_runs` (`tracemalloc`; volumes por run de um
    fold real — permutadas 41 × 252 × 2 × 7, VSN 252 × 59, ablação 252 × 2 × 7 — pico
    ≤ 512 MiB com 3 runs de cada tipo e pico com 6 ≤ 1,1 × o de 3).
- **O que fazer (concept CA14, CA14b):** como acima; nenhum teste lê o
  `parent_sweep_id` real.
- **Critério de aceite (CA14, CA14b; I16):** testes verdes.
- **Verificação (T1 + `slow` explícito):**
  ```bash
  uv run --no-sync pytest tests/integration/features/evaluation/test_h3_refresh_end_to_end.py tests/integration/features/evaluation/test_h3_refresh_memory.py -v --no-cov -m 'slow or not slow'
  make check-task SLICE=evaluation $PAR
  ! grep -rn "aapl_confirmatory-r0-665f45d9169a" "$WTH/tests" --include=*.py | grep -v -e test_preregistration_consistency -e test_stage_7_3_repo_files
  ```
- **Commit:** `test(evaluation): ponta a ponta e teto de memória do refresh de H3 [7.3/task-31]`
- **Checkpoint C** (T2 + revisão do diff das Tasks 29–31).

---

### Task 32 — Rascunho da r3 e consistência

- **Arquivos a criar:**
  - `docs/stages/7.3-explainability/aapl_confirmatory-r3.draft.toml`
- **Arquivos a modificar:**
  - `tests/architecture/test_stage_7_3_repo_files.py`
- **Testes primeiro:** `test_r3_draft_is_r2_plus_amendment_plus_h3` (todo campo igual ao
  r2 salvo `revision = 3`, `amends` = ref da r2, `justification`, `blind_status =
  "blinded"`, `h3`); `test_r3_draft_filled_with_synthetic_values_parses`
  (`Preregistration.from_mapping`); `test_r3_draft_unfilled_is_refused` (C11);
  `test_partition_hash_literal_recomputes` (`FamilyPartitionHash` + `CanonicalJsonHasher`);
  `test_r3_partition_equals_registry_and_ablation_draft`;
  `test_r3_k_p_seed_algorithm_equal_the_inference_plan` (I17);
  `test_filled_r3_differs_from_draft_only_in_h3_ablation` (pulado sem
  `config/preregistration/aapl_confirmatory-r3.toml`; **roda na L7**);
  `test_r0_to_r2_files_unchanged`.
- **O que fazer (concept §1 item 9, I18; ADR 7.3.0005 itens 1–2):** r2 literal + emenda +
  `[h3]` com as três sentinelas; o `partition_hash` literal calculado ao redigir. Nenhum
  `aapl_confirmatory-r3.toml` criado.
- **Critério de aceite (CA11 rascunho; I17, I18):** testes verdes.
- **Verificação (T3):**
  ```bash
  uv run --no-sync pytest tests/architecture/test_stage_7_3_repo_files.py -v -rs --no-cov
  test ! -e "$WTH/config/preregistration/aapl_confirmatory-r3.toml" && echo NO_R3_BEFORE_LINUX
  git -C "$WTH" diff --exit-code "$BASE" -- config/preregistration/
  make check $PAR
  ```
- **Commit:** `docs(evaluation): rascunho cego da emenda r3 com o bloco de H3 [7.3/task-32]`
- **Checkpoint C** (T2 + revisão do diff da Task 32 e do conjunto contra o concept).

---

### Etapa W — `attribute` sobre os 60 runs reais (só predições; opcional no Windows)

Não é Task numerada (concept §1 item 10): não produz código. Roda **depois** da Task
32, com a árvore limpa e `make check` verde no HEAD. Se o Docker do Windows não
sustentar a corrida, a Etapa vai para a L6 (registrar `[decision]`). Evidência literal
em §7 (`[deviation] etapa-w`), num commit `docs(inference): evidência da Etapa W [7.3/--]`.

**W0 — Pré-condições (host, Git Bash; variáveis do §1).**
```bash
SCRATCH=<diretório de scratchpad da sessão, caminho absoluto, fora do repo>
git -C "$WTH" status --short                                      # vazio
docker ps --format '{{.Names}} {{.Mounts}}'                       # nenhum ff-gate; nada usando data/cohorts/aapl
ls -a "$MAINH/data/cohorts/aapl" | tee "$SCRATCH/w0-ls.txt"       # sem gold/ nem .writer.lock
ls "$MAINH/data/cohorts/aapl/silver" | grep -E "fact_permuted|fact_vsn"   # vazio (primeira corrida)
```

**W1 — Backup do `data_root`** (igual ao E1 da 7.1):
```bash
STAMP=$(date +%Y%m%d-%H%M%S); BK="$MAINH/data/backups/aapl-pre-7.3-$STAMP"
mkdir -p "$BK" && cp -a "$MAINH/data/cohorts/aapl/." "$BK/"
(cd "$MAINH/data/cohorts/aapl" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$BK.src.sha"
(cd "$BK" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$BK.bak.sha"
diff "$BK.src.sha" "$BK.bak.sha" && echo BACKUP_OK
```

**W2 — Container** (worktree em `/app`; `.git` só leitura; `data_root` real em
leitura e escrita; `artifacts/` só leitura; trava e limites):
```bash
RUNW() { MSYS_NO_PATHCONV=1 docker run --name ff-gate --rm --cpus 6 --memory 8g --memory-swap 8g \
  -v "$WTD:/app" -v "$MAIND/.git:/main.git:ro" \
  -v C:/Users/Marcelo/Documents/Code/financial-forecasting/data/cohorts/aapl:/app/data/cohorts/aapl \
  -v "$MAIND/artifacts:/app/artifacts:ro" -v "$VENV:/app/.venv" \
  -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app -e GIT_OPTIONAL_LOCKS=0 \
  -e MLFLOW_TRACKING_URI=sqlite:////tmp/mlruns.db -w /app financial_forecasting-app:dev "$@"; }
CLI="uv run --no-sync python -m financial_forecasting.cli"
ATTR="--data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml --ablation-cohort config/cohorts/aapl_ablation.toml"
```

**W3 — Pré-voo** (o comando E3 da 7.1, colado aqui; nenhuma escrita):
```bash
RUNW sh -c "$PRE; git status --short; uv run --no-sync python -c \"import json, pathlib; from financial_forecasting.features.modeling.adapters.out.runtime.git_runtime_environment_probe import GitRuntimeEnvironmentProbe as P; from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import CODE_KEYS, DIRTY_KEY; cur = dict(P(repo_root=pathlib.Path('/app'), cohort_file=pathlib.Path('config/cohorts/aapl_confirmatory.toml').resolve(), device='cpu').snapshot()); ref = json.load(open('artifacts/cohorts/aapl_confirmatory-r0-665f45d9169a/progress.json'))['environment']; skip = set(CODE_KEYS) | {DIRTY_KEY}; print('dirty', cur[DIRTY_KEY]); print('non-code diff', sorted(k for k in set(cur) | set(ref) if k not in skip and cur.get(k) != ref.get(k)))\""
```
(As aspas duplas internas são escapadas `\"`, como no E3 da 7.1.) Esperado: `git
status` vazio, `dirty false`, `non-code diff []`. Outra saída ⇒ não rodar (tabela
abaixo).

**W4 — Atribuição.**
```bash
RUNW sh -c "$PRE; $CLI attribute $ATTR" 2>&1 | tee "$SCRATCH/attribute-1.log"; echo "EXIT=${PIPESTATUS[0]}"
```
Esperado: `EXIT=0`; 60 linhas `strict identity compared <n> max|d| 0.000e+00 …` (n =
3528, fold 5 = 3472); por run `permuted written` = **41 × n** (as 40 permutadas mais a
identidade, que também vai para `fact_permuted_predictions`) e `vsn written` =
decisões × `len(encoder_variables)` lido do checkpoint (252 ou 248 decisões; esperado
59 variáveis — 55 features, 2 do calendário, o alvo passado e o índice relativo);
resumo `attribution aapl_confirmatory-r0-665f45d9169a: 60 runs (60 strict, 0 tolerance); permuted rows written 8655920, verified 0; vsn rows written 889720, verified 0`
(41 × 211 120 = 8 655 920; 15 080 decisões × 59 = 889 720). Se o checkpoint tiver outro
número de variáveis, o total de VSN é 15 080 × esse número, registrado no `[deviation]`
da Etapa W.

**W5 — Conferências.**
```bash
RUNW sh -c "$PRE; $CLI attribute $ATTR" 2>&1 | tee "$SCRATCH/attribute-2.log"; echo "EXIT=${PIPESTATUS[0]}"   # 60 verified, 0 written
RUNW sh -c "$PRE; $CLI verify --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml"; echo "VERIFY_EXIT=$?"
ls -a "$MAINH/data/cohorts/aapl" | diff "$SCRATCH/w0-ls.txt" -       # vazio: só silver/ ganhou as duas tabelas; sem gold/
# partition_hash gravado = o literal do rascunho da r3 (antes de qualquer âncora)
python -c "import json, tomllib, sys; m = json.load(open(sys.argv[1])); d = tomllib.load(open(sys.argv[2], 'rb')); want = d['h3']['partition']['partition_hash']; got = {e['partition_hash'] for e in m['runs'].values()}; print('PARTITION_HASH_OK' if got == {want} else ('MISMATCH', got, want))" "$MAINH/data/cohorts/aapl/inference/aapl_confirmatory-r0-665f45d9169a/attribution_manifest.json" "$WTH/docs/stages/7.3-explainability/aapl_confirmatory-r3.draft.toml"
```
Esperado: segunda corrida `… permuted rows written 0, verified 8655920 …`; `VERIFY_EXIT=0`
com `rows expected 337792, observed 337792` / `OK`; `attribution_manifest.json` com 60
entradas `completed` e `strict`; **sem** `gold/`; `PARTITION_HASH_OK` (um `MISMATCH`
é HALT: o rascunho ou a partição do `aapl_ablation.toml` divergem, e a r3 não pode ser
ancorada assim).

Colar em §7: W3, as duas últimas linhas e uma linha de run de cada log, o `verify`, a
contagem do manifesto e o `ls`. Nenhuma métrica.

**Se falhar** (nunca editar o silver à mão):

| Sintoma | Ação |
|---|---|
| W3 com `non-code diff` não vazio ou `dirty true` | não rodar; corrigir o ambiente (venv/imagem/CPUs) ou levar a Etapa para a L6 com `[decision]` |
| `ReproductionError` em `strict` com chaves iguais | **parar**; `[finding]` com run, nº de valores e max \|Δ\|; diagnóstico antes de qualquer outra corrida (ADR 7.1.0003 item 6) |
| `FamilyFeatureKnownError` | **HALT**; a premissa P2 caiu; perguntar (P-H3-VSN reaberta) |
| `PartialAttributionError` / queda no meio | restaurar o backup inteiro (`rm -rf "$MAINH/data/cohorts/aapl" && cp -a "$BK" "$MAINH/data/cohorts/aapl"`, conferido com `$BK.bak.sha`) e rodar de novo |
| Docker instável / tempo inviável | parar; restaurar o backup; a Etapa W vai para a L6 (`[decision]`) |

---

### Task 33 — Handoff para o Linux (§7, comentário na #186, PR aberto)

- **Arquivos a criar:**
  - `tests/architecture/test_stage_7_3_handoff_commands.py`
- **Arquivos a modificar:**
  - `docs/stages/7.3-explainability/technical.md` (só a §7: entrada `[handoff]`)
- **Testes primeiro:** `test_every_cited_subcommand_has_help` (roda `--help` de
  `attribute`, `ablation-pilot`, `ablation-run`, `ablation-verify`, `ablation-freeze`,
  `verify`); `test_handoff_cites_only_known_subcommands` (lê a entrada `[handoff]` da §7
  deste technical e afirma que todo `financial_forecasting.cli <sub>` citado está na
  lista acima — um subcomando renomeado reprova o CI antes do Linux).
- **O que fazer (concept CA16; ADR 7.3.0006 itens 2, 5, 6):** a entrada `[handoff]` com:
  o hash **X** do commit pai (o HEAD com `make check` verde **antes** do commit desta
  Task — o arquivo não pode citar o próprio commit, que ainda não existe), as Etapas
  L0–L8 e a L6b da "Fase Linux" abaixo (comando, saída esperada, parada mapeada a um
  C*), as transferências com conferência, o estado da Etapa W (feita no Windows ou
  movida para a L6). Depois do commit: `git push`; comentário na **#186** com o mesmo
  passo a passo **e o hash do commit da Task 33** (agora conhecido)
  (`gh issue comment 186 --body-file`); PR contra `develop` (`gh pr create`, título e
  corpo em PT, `Closes #186`, marcado "aguarda fase Linux") — o PR fica aberto.
- **Refinamento declarado da tabela do ADR 7.3.0006 item 6:** a fase Linux ganha a
  **L0** (chegada: checkout, dados, ambiente travado e as conferências que precisam
  dele — antes a L1 acumulava tudo e rodava `verify` antes de o venv existir) e a
  **L6b** (saída Linux → máquina da 8.1, que o ADR exige no item 5 mas a tabela não
  tinha). A L1 fica só com o torch ROCm e o probe. O ADR não é editado (`accepted`); a
  §7 registra o refinamento junto do `[handoff]`.
- **Critério de aceite (CA16):** teste verde; comentário publicado (URL em §7); PR aberto.
- **Verificação (T3):**
  ```bash
  X=$(git -C "$WTH" rev-parse HEAD)          # antes do commit; vai para o [handoff]
  uv run --no-sync pytest tests/architecture/test_stage_7_3_handoff_commands.py -v --no-cov
  make check $PAR
  # depois do commit e do push:
  test "$(git -C "$WTH" rev-parse HEAD^)" = "$X" && echo PARENT_OK
  git -C "$WTH" log origin/develop..HEAD --oneline   # só commits desta Stage
  gh issue view 186 --comments | grep -F "$(git -C "$WTH" rev-parse HEAD)"
  gh pr view --json url,state
  ```
- **Commit:** `docs(inference): handoff da Stage 7.3 para a fase Linux [7.3/task-33]`

---

### Fase Linux — Etapas L0–L8 (não são Tasks do Windows)

Executadas na máquina Linux com a RX 7700 XT, **nativas** (sem Docker), a partir da
entrada `[handoff]` da §7. Toda entrada nova na §7 durante a fase Linux leva data e
autor. Variáveis:

```bash
CLI="uv run --no-sync python -m financial_forecasting.cli"   # nunca `uv run` puro: ressincroniza o torch CPU
ABL="--data-root data/cohorts/aapl --cohort config/cohorts/aapl_ablation.toml"
ATTR="--data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml --ablation-cohort config/cohorts/aapl_ablation.toml"
```

**Transferências de dado** (ADR 7.3.0006 item 5; `data/` e `artifacts/` são
git-ignorados). O `.tar` e o `.sha` ficam **fora da árvore** do repo nos dois lados.

Windows → Linux (antes da L0; host, Git Bash):
```bash
OUT=<diretório fora da árvore, caminho absoluto>
cd "$MAINH"
LIST="data/cohorts/aapl/processed/dataset_tft data/cohorts/aapl/silver data/cohorts/aapl/inference artifacts/tft artifacts/cohorts/aapl_confirmatory-r0-665f45d9169a"
find $LIST -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/transfer-in.sha"
tar -cf "$OUT/transfer-in.tar" $LIST
```
(`artifacts/tft` = os 60 checkpoints; `artifacts/cohorts/aapl_confirmatory-r0-665f45d9169a/`
= o ledger `progress.json` da 5.5, que o probe da W3/E3 e o `verify` leem.)

Linux → máquina da 8.1 (L6b, depois da L5 e da L6; no checkout do Linux):
```bash
OUT=<diretório fora da árvore>
LIST="data/cohorts/aapl/silver/dim_run data/cohorts/aapl/silver/fact_oos_predictions artifacts/cohorts/<cohort_id da ablação>"
# se a L6 rodou no Linux, acrescentar:
LIST="$LIST data/cohorts/aapl/silver/fact_permuted_predictions data/cohorts/aapl/silver/fact_vsn_weights data/cohorts/aapl/inference/aapl_confirmatory-r0-665f45d9169a/attribution_manifest.json"
find $LIST -type f -print0 | sort -z | xargs -0 sha256sum > "$OUT/transfer-out.sha"
tar -cf "$OUT/transfer-out.tar" $LIST
```
No destino, cada sentido com o seu par de arquivos (nunca glob):
- Windows → Linux: `cd <checkout>; tar -xf "$IN/transfer-in.tar" && sha256sum -c --quiet "$IN/transfer-in.sha" && echo TRANSFER_OK`;
- Linux → 8.1: `cd <checkout>; tar -xf "$IN/transfer-out.tar" && sha256sum -c --quiet "$IN/transfer-out.sha" && echo TRANSFER_OK`.

As saídas vão para §7.

| Etapa | Comando | Saída esperada | Parada |
|---|---|---|---|
| **L0** chegada | `uv --version` (instalar `curl -LsSf https://astral.sh/uv/0.11.28/install.sh \| sh` se diferente — o mesmo uv do CI); `git fetch && git checkout feat/186-7-3-explainability`; `T33=$(git log --format=%H -1 --grep='\[7.3/task-33\]')`; `git rev-parse "$T33^"` (= **X** do `[handoff]`, mesmo que haja commits depois da Task 33) e `git diff --name-only "$T33^" "$T33"` (contém o `technical.md`); `tar -xf "$IN/transfer-in.tar" && sha256sum -c --quiet "$IN/transfer-in.sha" && echo TRANSFER_OK`; `uv sync --locked --extra dev`; só então `$CLI verify --data-root data/cohorts/aapl --cohort config/cohorts/aapl_confirmatory.toml` e, se a Etapa W rodou, `$CLI attribute $ATTR` | `uv 0.11.28`; `$T33^` = X; `TRANSFER_OK`; `rows expected 337792, observed 337792` + `OK`; `attribute`: 60 `verified`, 0 written | qualquer divergência: não seguir; `[finding]` |
| **L1** ambiente ROCm | `uv pip install --no-sources --no-deps --reinstall --index-url https://download.pytorch.org/whl/rocm<X.Y> "torch==2.13.0+rocm<X.Y>"`; snapshot do probe com `device="rocm"` (`uv run --no-sync python -c` com `GitRuntimeEnvironmentProbe(repo_root='.', cohort_file='config/cohorts/aapl_ablation.toml', device='rocm').snapshot()`); `git status --short`; `git diff --exit-code -- uv.lock pyproject.toml` | `gpu.available true`, `gpu.name` da RX 7700 XT, `gpu.hip_version` não vazio, `torch 2.13.0+rocm…`; árvore limpa; lock intocado | C12 |
| **L2** piloto | `$CLI ablation-pilot $ABL` | relatório (`seconds_per_epoch`, `max_epochs`, teto e estimativa por S = 1..10) colado em §7 | C12 (kernel sem determinismo / falha do ROCm): `[decision]` em §7 e commit **antes** da L4 |
| **L3** seeds (P) | pergunta ao humano no formato "Anatomia da pergunta" de `PROMPT-step-single-session.md` §2, com o teto e a estimativa do piloto por S; ADR `docs/adr/7_3_0007-ablation-seed-count.md`; commit `docs(adr): número de seeds do cohort de ablação [7.3/--]` e `git push` **antes** da L4 | ADR `accepted` com S, no remoto | — |
| **L4** freeze e âncora | `$CLI ablation-freeze $ABL --seeds 1,…,S`; commit `chore(modeling): congela o cohort de ablação [7.3/--]`; `git push origin feat/186-7-3-explainability`; `git tag cohort/<cohort_id da ablação> <commit>`; `git push origin <tag>`; `gh issue comment 186` com id, hash completo, commit e tag | `ablation-freeze` imprime `frozen <cohort_id>: cohort_hash <64 hex>; seeds <S>; torch_build <versão>` (spec com `seeds` e `torch_build` = a chave `torch` do probe); branch e tag no remoto; comentário publicado | C2, C13 (não seguir sem a tag e o comentário) |
| **L5** treino | `$CLI ablation-run $ABL` (retomável; `--break-stale-lock` só sem processo vivo); `$CLI ablation-verify $ABL` | `ablation <id>: 5 configurations x 6 folds x S seeds = 30·S runs; rows expected 105560·S, observed 105560·S` + `OK` | C3, C4 (unidade parcial ⇒ nova revisão do spec, nunca editar o silver); **nenhuma mudança em `src/` entre a L4 e o fim da L5** |
| **L6** atribuição (se a W não rodou) | `$CLI attribute $ATTR`; o `python -c` do `PARTITION_HASH_OK` da W5 (caminhos relativos ao checkout) | 60 entradas `completed`, modo `tolerance` (ambiente ≠ 7.1), max \|Δ\| por run dentro da tolerância; contagens da W4; sem `gold/`; `PARTITION_HASH_OK` antes de qualquer âncora | C5–C8; `MISMATCH` ⇒ HALT |
| **L6b** saída para a 8.1 | no Linux: `tar` + `sha256sum` de "Linux → máquina da 8.1" (acima); no destino: `git pull origin feat/186-7-3-explainability` (traz o spec congelado da L4), `tar -xf "$IN/transfer-out.tar" && sha256sum -c --quiet "$IN/transfer-out.sha" && echo TRANSFER_OK`, `$CLI ablation-verify $ABL` e `$CLI attribute $ATTR` — se o destino for o Windows com Docker, os dois últimos rodam pelo `RUNW` da W2 (`MSYS_NO_PATHCONV=1`): `RUNW sh -c "$PRE; $CLI ablation-verify $ABL"` e `RUNW sh -c "$PRE; $CLI attribute $ATTR"` | `TRANSFER_OK`; `ablation-verify` `OK`; `attribute` com 60 `verified`, 0 written | qualquer divergência: `[finding]`. Se a 8.1 rodar no próprio Linux, a L6b é N/A por `[decision]` declarada em §7 |
| **L7** r3 | preencher os três valores do rascunho a partir do spec congelado; copiar para `config/preregistration/aapl_confirmatory-r3.toml`; `uv run --no-sync pytest tests/architecture/test_stage_7_3_repo_files.py -v -rs` (inclui `test_filled_r3_differs_from_draft_only_in_h3_ablation`, agora não pulado); acrescentar r3 em `test_every_revision_hash_quoted`; commit; tag `preregistration/<ref r3>`; comentário na #186 (ref, hash completo, tag, commit, os dois `cohort_id` e hashes); `.anchor.toml` com o `created_at` lido por `gh api`; seções "Revisão r3" e "Âncora r3" no espelho `docs/preregistration/aapl_confirmatory.md` | só `[h3.ablation]` difere do rascunho; `anchored_at(r3) > anchored_at(r2)`; a âncora da ablação (L4) anterior à da r3 | C11, C13 (rede/permissão ⇒ não gravar `.anchor.toml`, repetir) |
| **L8** fecho | skill `stage-audit`; `make check` num venv travado separado, sem o torch ROCm (`export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/ff-ci"; uv sync --locked --extra dev && uv run --no-sync make check`) ou o CI do PR; roadmap `done`; `stage 7.3: complete`; merge | veredito da auditoria no PR; CI verde | — |

Arquivos da L7 (lista fechada): `config/preregistration/aapl_confirmatory-r3.toml`,
`config/preregistration/aapl_confirmatory-r3.anchor.toml`,
`docs/preregistration/aapl_confirmatory.md`,
`tests/integration/features/evaluation/test_preregistration_consistency.py`. Depois da
tag da r3, **nenhum rebase** da branch (atualização com o `develop` só por merge).

## 3. Gate de saída da Stage

### Gate da fase Windows (antes da Task 33 e do PR)
```bash
make check $PAR                                                       # T3, idêntico ao CI (no container)
uv run --no-sync pytest tests/ --cov=src/financial_forecasting --cov-report=term-missing -q   # cada arquivo de src/ tocado >= 90%
git -C "$WTH" diff --name-only "$BASE" HEAD -- src/                   # a lista conferida contra a tabela de cobertura
uv run --no-sync python scripts/check_port_coverage.py
git -C "$WTH" diff "$BASE" -- scripts/arch_baseline.toml | grep -E '^[+-][^+-]'   # só as linhas "-" das 2 chaves run_confirmatory_cohort.py de [schema_literals]; nenhum "+"
grep -n 'violating == \["Hasher"\]' "$WTH/tests/architecture/test_port_coverage_gate.py"
python scripts/check_technical_postexec.py docs/stages/7.3-explainability/technical.md
! grep -rn "aapl_confirmatory-r0-665f45d9169a" "$WTH/tests" --include=*.py | grep -v -e test_preregistration_consistency -e test_stage_7_3_repo_files
test ! -e "$WTH/config/preregistration/aapl_confirmatory-r3.toml" && echo NO_R3_BEFORE_LINUX
```

### Verificações funcionais
- [ ] Ponta a ponta sintético do refresh (Task 31): família sustentada, caso nulo,
      lados opostos, método indefinido, `partition_hash` divergente, r2 × r3 com o mesmo
      veredito, use cases reais pelo composition root.
- [ ] Ponta a ponta sintético do `attribute` (Task 20): strict, contagens, segunda
      corrida só re-confere, sem `gold/`.
- [ ] **Último quilômetro:** as tabelas gold de H3 são dado novo, mas o cegamento (I9)
      proíbe produzi-las sobre dado real nesta Stage; a verificação de ponta a ponta é a
      da Task 31 sobre silver sintético com os adapters reais de arquivo. O dado real
      novo desta Stage é o silver da Etapa W/L6 e do cohort de ablação (L5), cuja
      verificação é a saída literal da W4–W5/L6 e do `ablation-verify` em §7.
- [ ] Etapa W concluída (ou registrada como movida para a L6) com a saída em §7.
- [ ] Linux: L0–L7 com as saídas em §7; transferências conferidas nos dois sentidos;
      r3 ancorada antes de qualquer métrica de H3 (CA19).

### Checklist de fechamento
- [ ] 33 Tasks commitadas, cada uma com o seu gate verde; Checkpoints C nas fronteiras
      de §4 com disposições registradas
- [ ] Auditoria de testes (subagente) com todos os itens "sim", inclusive **mutação
      real** das regras críticas: doador fora do lote (Task 11), bootstrap pareado e
      Bonferroni (Task 25), ±∞ das réplicas (Task 25), `partition_hash` (Tasks 19, 24),
      `model_version` por configuração (Tasks 02, 08), leitura por `year` (Task 30)
- [ ] Verificação de gap contra a 7.2 registrada em §7
- [ ] `[handoff]` em §7, comentário na #186 e PR aberto (fase Windows)
- [ ] ADR da decisão das seeds (L3) `accepted`; ADRs 7.3.0001–0006 `accepted`
- [ ] `docs/roadmap.md`: 7.3 `done`, `updated_at` e `last_reviewed_at` do dia da L8
      (commit `docs(roadmap): … [7.3/--]`); commit `stage 7.3: complete`
- [ ] PR contra `develop` com `Closes #186`, mergeado na L8
- [ ] `concept.md` sem retoque retrospectivo pendente

## 4. Ordem de dependência entre Tasks

```
shared:     01
modeling:   02 ─► 03 ─► 04 ─► 05 ─► 06 ─► 07 ─► 08 ─► 09 ─► 10 ─► 11 ─► 12
inference:  13 ;  14 ─► 15 (analytics_store)
            16 (após 12, 15) ─► 17 ─► 18 ─► 19 (após 01, 13) ─► 20 (após 10)
evaluation: 21 (após 13) ─► 22 ─► 23 ─► 24 (após 01) ─► 25 ─► 26 ─► 27 ─► 28 ─► 29 ─► 30 ─► 31
fecho:      32 (após 22, 06) ─► [Etapa W] (após 20 e 32) ─► (auditoria de testes) ─► 33 ─► [L0–L8]
```

- 01 antes de 19 e 24 (quem grava e quem confere o `partition_hash`); 02 antes de 05/06
  (funções da registry); 03 antes de 10/11 (o treinador por device); 04 antes de 08 (as
  chaves observadas); 05 antes de 06 e 08; 07 antes de 08; 11 antes de 12 (port antes
  do fornecedor); 12 e 15 antes de 16 (os reais dos ports); 17 antes de 18 (port antes do
  adapter); 16–18 antes de 19; 19 antes de 20; 13 antes de 21 (constantes do plano no
  teste de I17); 23 antes de 24; 24–26 antes de 30; 27 antes de 28; 28 antes de 29; 29
  antes de 30; 30 antes de 31; 06 e 22 antes de 32; a Etapa W depois do último código de
  atribuição (20) e do rascunho (32); 33 por último no Windows.
- A ordem linear de §2 (01 → 33) respeita todas essas arestas.
- **Checkpoint C** (T2 `make check-block $PAR` + revisão do diff) depois de 04, 08, 12,
  15, 20, 24, 28, 31 e 32.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| A 7.2 mergeou com forma diferente da do technical dela | verificação de gap (§1) → `[deviation] gap-7.2`; mudança de contrato consumido ⇒ perguntar antes da Task afetada |
| Extrair o executor (Task 07) muda a retomada da 5.5 | parar; os testes da 5.5 são a rede; diferença = bug da extração, nunca asserção atualizada |
| `_emit` com dataloader muda o golden da 7.1 | parar; o dataloader tem de ser o que o `predict` constrói; diferença = bug, nunca golden atualizado |
| O `collate_fn` da lib não expõe `decoder_time_idx` por amostra | ler a decisão pelo índice do dataset (`dataset.x_to_index`) na mesma ordem do dataloader sem embaralhar; `[decision]` em §7 |
| Comprimento de encoder diferente entre decisões de teste de um fold | o adapter recusa (`ValueError`); medir na Task 11 sobre o cohort sintético e, se ocorrer no real (Etapa W), HALT e perguntar |
| `interpret_output(reduction="none")` com outra forma na 1.8.0 | conferir na fonte pinada; ajustar a redução sobre o tempo; `[deviation]` |
| `check_port_coverage.py` não reconhece um fornecedor como real | alinhar o texto das anotações do port ao do fornecedor; nunca entrada nova no baseline |
| Teste de memória (Task 31) passa de 120 s ou de 512 MiB | `slow` (sai do T1); se o pico passar, é defeito da leitura por run/ano — corrigir no `RefreshGold`, nunca subir o limiar |
| A Etapa W demora demais ou o Docker cai | backup restaurado; a Etapa vai para a L6 (`[decision]`) |
| `torch 2.13.0` sem roda ROCm para o driver da máquina | C12: `[decision]` em §7 na L1/L2 com a versão disponível; `torch_build` declara a versão usada (o cohort de ablação é autocontido) |
| Kernel sem determinismo no ROCm (L2) | C12: `[decision]` e commit antes da L4; nunca depois de o treino começar |
| Âncora (L4/L7) falha por rede ou permissão | não gravar `.anchor.toml`; repetir; nunca inventar `anchored_at` (C13) |
| Mudança em `src/` depois da L4 | proibida até o fim da L5 (o executor recusa `code.src` diferente na retomada); achado vira `[finding]` |

## 6. Referências

- [`./concept.md`](./concept.md); ADRs
  [7.3.0001](../../adr/7_3_0001-attribution-statistics-in-evaluation-gold-via-refresh-gold.md),
  [7.3.0002](../../adr/7_3_0002-permuted-predictions-and-vsn-via-modeling-port-persisted-in-silver.md),
  [7.3.0003](../../adr/7_3_0003-ablation-cohort-spec-by-reference-identity-per-configuration.md),
  [7.3.0004](../../adr/7_3_0004-device-per-trainer-instance-torch-build-declared.md),
  [7.3.0005](../../adr/7_3_0005-h3-preregistration-r3-details.md),
  [7.3.0006](../../adr/7_3_0006-stage-split-windows-linux-with-in-repo-handoff.md);
  consumidos: 0.0.0007, 0.0.0016, 0.0.0053, 0.0.0055, 4.3.0001, 5.5.0001, 5.5.0003,
  5.5.0004, 6.1.0005, 6.5.0003, 6.5.0004, 7.1.0001–7.1.0004, 7.2.0003, 7.2.0005
- [`../../LAYOUT.md`](../../LAYOUT.md) §3, §7; [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  [`../../PIPELINE.md`](../../PIPELINE.md) §4.3; [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) Passos 6–10 e §Gates em camadas
- Technicals [7.1](../7.1-inference-engine/technical.md) (Etapa E, §7) e 7.2
  (`feat/158-7-2-conformal-cqr`, `docs/stages/7.2-conformal-cqr/technical.md`: função
  `run()`, trava `ff-gate`, venv dedicado, ADR 6.1.0005, Etapa G)
- Skills: `task-ordering-hex`, `hex-arch-python`, `pytest-with-fakes`, `composition-root`,
  `import-linter-rules`, `orchestrator-design`
- Issue [#186](https://github.com/MarceloSanC/financial-forecasting/issues/186)

### Matriz de rastreabilidade (concept §11, §5, §6 → Task → teste)

**Critérios de aceite**

| # | Critério (concept §11) | Task(s) | Teste / evidência |
|---|---|---|---|
| CA1 | Confirmatório intacto: `run_id`/`config_signature` fixados; 5.4/5.5/7.1 sem mudar asserção; hash do TOML confirmatório | 02, 03, 06, 07 | `test_default_command_keeps_the_pinned_run_id_and_config_signature`; `git status --short -- tests/` (Tasks 02, 07); `test_confirmatory_cohort_file_hash_unchanged` |
| CA2 | Subconjunto: colunas, geometria igual com aquecimento maior, hash do subconjunto, `model_version` | 02 | `test_subset_panel_columns_are_registry_minus_family_in_order`; `test_subset_grid_is_trimmed_on_the_full_column_set`; `test_subset_run_id_carries_subset_hash_and_loco_model_version`; `test_subset_rows_and_dim_run_carry_loco_model_version`; `test_tft_feature_set_hash_matches_the_measured_prefixes` |
| CA3 | Spec de ablação: carga, recusas, `is_frozen`, hash por campo, `cohort_id`, device fora do mapa | 05, 06, 10 | `test_ablation_cohort_spec.py::*`; `test_ablation_cohort_file.py::*`; `test_ablation_draft_loads_unfrozen_with_registry_partition`; `test_ablation_factory_refuses_device_outside_the_map_without_importing_torch` |
| CA4 | Executor de ablação: ordem, retomada, parcial, guarda do probe; 5.5 intacta depois da extração | 07, 08 | `test_cohort_unit_runner.py::*`; `test_run_ablation_cohort.py::*`; suíte da 5.5 sem diferença; `test_cohort_runners_never_import_each_other` |
| CA5 | Device: `cpu` default, `gpu` passado, composition root recusa sem torch, probe `cpu` igual, GPU pulado | 03, 04, 10 | `test_pf_tft_accelerator.py::*`; `test_cpu_snapshot_has_exactly_todays_keys`; `test_device_outside_the_map_refused_without_importing_torch`; `test_gpu_fit_smoke` (skip) |
| CA6 | Piloto: relatório com teto e estimativa rotulados; nada no silver | 09 | `test_measure_ablation_cost.py::*` (unit e integração) |
| CA7 | Atribuição no adapter: identidade = 7.1, π = id, doador fora do lote, colunas não permutadas e decoder bit a bit, constante/informativa, VSN soma 1, `known` ⇒ erro | 11 | `test_pf_tft_attribution_prediction.py::*`; `test_tft_checkpoint_predictor_contract.py` (casos novos) |
| CA8 | Plano de permutação: K_p permutações, determinismo, golden, índices 1..K_p, independente de seed/família | 13 | `test_permutation_plan.py::*` |
| CA9 | Use case de atribuição: política, re-conferência, parcial, write-ahead, colunas do plano, partição ≠ registry, `[fake, real]`, port-coverage | 12, 16, 17, 18, 19, 20 | `test_run_permutation_inference.py::*` (unit e integração); `test_predict_tft_attribution_from_checkpoints.py::test_partition_different_from_registry_refused_before_predicting`; `test_attribution_ports_contract.py::*`; `test_attribution_manifest_contract.py::*`; `test_port_coverage_gate.py::{test_real_repo_attribution_ports_resolve, test_real_repo_attribution_manifest_resolves}` |
| CA10 | Silver: PK, vocabulário, `none ⇔ 0`; persistência e leitura de volta | 14, 15 | `test_fact_permuted_predictions_schema.py::*`; `test_fact_vsn_weights_schema.py::*`; `test_permuted_round_trip_and_run_filter_pushdown`; `test_vsn_round_trip_and_run_filter_pushdown` |
| CA11 | `H3Parameters` e r3: r0–r2 e r3 sintética; hashes; C11; rascunho preenchido valida; catálogo = inference | 21, 22, 32 | `test_h3_parameters.py::*`; `test_h3_catalog_matches_permutation_plan.py::*`; `test_preregistration_value_object.py` (casos novos); `test_stage_7_3_repo_files.py::{test_r3_draft_is_r2_plus_amendment_plus_h3, test_r3_draft_filled_with_synthetic_values_parses, test_r3_k_p_seed_algorithm_equal_the_inference_plan}` |
| CA12 | Assembly: d_t à mão, interseção, I11 ⇒ `undefined`, seed/k faltando | 23, 24 | `test_attribution_assembly.py::*`; `test_h3_run_reductions_value_objects.py::*` |
| CA13 | Contribuição e leitura: analíticos, oráculo `arch`, `linear_quantile`, ±∞, Σ ≤ 0, limites infinitos `null` + flag, lado, limite 0, sustentada, rótulos | 25, 26, 29 | `test_family_contribution.py::*`; `test_h3_basic_interval_vs_arch.py::*`; `test_contribution_agreement.py::*`; `test_vsn_summary.py::*`; `test_infinite_bound_maps_to_null_with_flag` |
| CA14 | Refresh sintético: sustentada, nulo, lados opostos, indefinido, `partition_hash`, COMPLETED com 4 tabelas, sem `[h3]` vazio, BLOCKED, I16, manifesto antigo, composition root | 27–31 | `test_h3_refresh_end_to_end.py::*`; `test_manifest_without_h3_parameters_is_corrupt`; `test_h3_gold_builders.py::*` |
| CA14b | Memória: filtro por run, leitura por ano, confirmatório sem `fs_all_ablation`, partição real, pico | 30, 31 | `test_permuted_and_vsn_read_one_run_per_call_with_run_id_filter`; `test_ablation_partition_read_once_per_year_never_without_year`; `test_confirmatory_records_never_read_fs_all_ablation`; `test_h3_refresh_memory.py::*` |
| CA15 | Etapa W: 60 `completed`, strict com \|Δ\| = 0, contagens, sem `gold/`, saída em §7 | 20, Etapa W | saída de W3–W5 em §7 |
| CA16 | Handoff: `[handoff]` com as Etapas L0–L8, transferências, commit de partida; comentário na #186; `--help`; PR aberto | 33 | `test_stage_7_3_handoff_commands.py::*`; URL do comentário e do PR em §7 |
| CA17 | Roadmap e LAYOUT §7 emendados; `make docs-check` | concept (`58e70aa`), 01, 19, 24, §3 | diff do LAYOUT §7 nas Tasks 01, 19 e 24; `make docs-check` dentro do `make check` |
| CA18 | `make check` verde (cobertura ≥ 90 %, mypy, import-linter com as arestas uma a uma, layout, fake-parity, port-coverage) | §3 | saída do `make check` no relatório; contagem `= 6` (Task 19) e `= 7` (Task 24) das arestas |
| CA19 | Linux: piloto, ADR das seeds, freeze e âncora antes do treino, `ablation-verify`, r3 ancorada, `attribute` completo, transferências, auditoria | L0–L8 | saídas de L0–L8 em §7; tags `cohort/<id>` e `preregistration/<ref r3>`; comentários na #186; veredito da auditoria |

**Invariantes**

| # | Invariante (concept §5) | Task(s) | Teste / evidência |
|---|---|---|---|
| I1 | Confirmatório intacto | 02, 03, 07 | CA1; goldens da 5.4/7.1 intocados |
| I2 | Geometria fixa | 02, 08 | `test_subset_grid_is_trimmed_on_the_full_column_set`; `test_geometry_equal_across_configurations_and_base` |
| I3 | Identidade por configuração; `fs_all_ablation`; sem colisão | 02, 05, 08, 30 | `test_configuration_identity_derived_from_the_name`; `test_no_run_id_collision_across_configurations_and_seeds`; `test_confirmatory_records_never_read_fs_all_ablation` |
| I4 | Mesmo procedimento herdado da base | 06, 08 | `test_procedure_fields_in_the_ablation_file_refused`; `test_base_hash_mismatch_refused` |
| I5 | Device e build declarados e observados | 04, 05, 08 | `test_every_field_changes_the_hash`; `test_gpu_keys_are_observed_not_echoed`; `test_probe_guard_refuses_before_training` |
| I6 | Permutação por fold, compartilhada, doador em qualquer lote | 11, 13, 19 | `test_golden_n5_kp3_seed130_fold2`; `test_donor_in_another_batch_gets_the_donor_block`; `test_same_permutation_for_every_seed_and_family` |
| I7 | Identidade = `_emit`; política da 7.2 antes de gravar | 11, 19 | `test_identity_equals_predict_from_checkpoint_value_by_value`; `test_identity_outside_policy_raises_and_writes_nothing` |
| I8 | Guarda C6 | 02, 11, 12 | `test_every_family_feature_is_unknown`; `test_known_family_column_raises_family_feature_known`; `test_family_column_known_in_the_panel_raises_before_predicting` |
| I9 | Cegamento | 09, 20, Etapa W, L2–L6 | `test_nothing_is_persisted`; `test_no_gold_directory_created`; `grep` do `cohort_id` (§3); W5 sem `gold/` |
| I10 | Medida (média nas seeds da média nas k; LOCO por médias; `value_guardrail`; interseção) | 24 | `test_permutation_d_t_equals_the_hand_computed_value`; `test_loco_d_t_is_seed_mean_minus_seed_mean`; `test_losses_use_value_guardrail` |
| I11 | Alinhamento pelas regras públicas; `undefined`, nunca `AlignmentFinding` | 24 | `test_alignment_rules_from_series_assembly`; `test_violation_is_never_an_alignment_finding`; `test_missing_seed_k_family_or_configuration_is_undefined` |
| I12 | Bootstrap único | 25, 30 | `test_same_indices_for_both_horizons_and_all_families`; `test_one_bootstrap_indices_call_serves_both_methods` |
| I13 | Intervalo básico, tipo 7, a = 0,0125 (também no wiring), oráculo | 25, 30, 31 | `test_basic_interval_formula`; `test_level_uses_a_over_two_with_a_0_0125`; `test_basic_interval_equals_arch_conf_int_basic`; `test_contribution_receives_the_bonferroni_level`; `test_shares_level_is_0_9875` |
| I14 | Total não positivo; réplicas ±∞; contagem | 25, 29 | `test_point_total_nonpositive_is_undefined`; `test_nonpositive_replicas_enter_as_plus_inf_upper_minus_inf_lower`; `test_many_nonpositive_replicas_make_bounds_infinite_and_method_ok`; `test_nonpositive_counts_by_horizon` |
| I15 | Leitura | 25, 26 | `test_side_is_the_sign_of_delta_hat`; `test_interval_excluding_zero_on_the_opposite_side_is_undefined`; `test_bound_exactly_zero_is_undefined`; `test_contribution_agreement.py::*` |
| I16 | Isolamento | 28, 29, 30, 31 | `test_h3_failure_never_changes_other_tables`; `test_r2_and_r3_same_verdict_and_same_previous_tables`; `test_blocked_generation_has_no_h3_tables`; `test_r2_plan_writes_empty_h3_tables` |
| I17 | Derivação única; duplicação travada; `partition_hash` | 01, 19, 21, 24, 27, 32 | `test_catalog_algorithm_k_p_and_seed_equal_the_inference_plan`; `test_rows_carry_permutation_seed_algorithm_and_partition_hash`; `test_partition_hash_mismatch_is_undefined`; `test_plan_with_h3_derives_the_block`; `test_partition_hash_literal_recomputes` |
| I18 | r3: rascunho, hashes r0–r2, âncora depois da r2 e antes de métrica | 22, 32, L7 | `test_r3_draft_is_r2_plus_amendment_plus_h3`; `test_r0_to_r2_files_unchanged`; `NO_R3_BEFORE_LINUX`; saída da L7 |
| I19 | Silver append-only, `run_id` na partição, leitura por run e por ano, retomada por run | 14, 15, 19, 23, 30 | `test_partition_by_has_run_id`; `test_one_write_per_run_call`; `test_completed_run_is_reconferred_by_reading_and_skipped`; `test_partial_run_raises_partial_attribution`; CA14b |

**Casos de erro**

| # | Caso (concept §6) | Task(s) | Teste / evidência |
|---|---|---|---|
| C1 | Comando ou VO inválido → `ValueError` antes de I/O | 02, 05, 10, 12, 13 | `test_model_version_pairing_refused_before_any_io`; `test_missing_repeated_or_unknown_configuration_refused`; `test_donors_must_be_k_p_permutations_of_the_fold_test_positions`; `test_invalid_inputs_refused`; `test_ablation_factory_refuses_device_outside_the_map_without_importing_torch` |
| C2 | Base com hash errado, partição ou subconjunto ≠ registry | 06, L4 | `test_base_hash_mismatch_refused`; `test_partition_different_from_registry_refused`; `test_declared_subset_hash_different_from_registry_refused` |
| C3 | Spec não congelado; probe com device/torch diferentes; ambiente | 08, 10 | `test_unfrozen_spec_refused_before_lock_and_probe`; `test_probe_guard_refuses_before_training`; `test_environment_mismatch_on_resume`; `test_run_refuses_unfrozen_spec` |
| C4 | Unidade de ablação parcial | 07, 08 | `test_partial_unit_raises` (Tasks 07 e 08) |
| C5 | Coluna de família não `unknown` no checkpoint | 11, 12 | `test_known_family_column_raises_family_feature_known`; `test_family_column_absent_from_unknown_reals_raises`; `test_adapter_family_known_error_propagates` |
| C6 | Identidade fora da política → `ReproductionError` antes de gravar | 19 | `test_identity_outside_policy_raises_and_writes_nothing` |
| C7 | sha256 ≠ esperado | 11, 19 | `test_wrong_sha_raises_before_load`; `test_artifact_changed_propagates` |
| C8 | Run de atribuição parcial; completo re-conferido | 19, 20 | `test_partial_run_raises_partial_attribution`; `test_completed_run_is_reconferred_by_reading_and_skipped`; `test_second_attribute_verifies_all_and_writes_zero` |
| C9 | No refresh: semente/algoritmo, k/família/seed faltando, decisões diferentes, Σ ≤ 0, b̂ inválido, `ArithmeticError` → `undefined`; outra exceção propaga | 24, 25, 30 | `test_wrong_permutation_seed_or_algorithm_is_undefined`; `test_decision_sets_differ_between_methods_is_undefined`; `test_point_total_nonpositive_is_undefined`; `test_invalid_series_or_arithmetic_error_gives_undefined_reading`; `test_unexpected_exception_propagates` |
| C10 | Manifesto de gold anterior não lê | 27, 31 | `test_manifest_without_h3_parameters_is_corrupt`; `test_manifest_before_this_stage_is_unreadable` |
| C11 | `[h3]` no r0, id fora do catálogo, chave desconhecida/ausente, partição incompleta/repetida, sentinela | 21, 22, 32 | `test_h3_parameters.py::*`; `test_h3_block_forbidden_in_revision_0`; `test_r3_draft_unfilled_is_refused` |
| C12 | GPU sem kernel determinístico / falha do ROCm | L1, L2 | `[decision]` em §7 antes da L4 |
| C13 | Âncora falha | L4, L7 | procedimento da L4/L7; `.anchor.toml` só com `created_at` lido por `gh api` |

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

### 2026-10-18 — [deviation] concept §9 — volume da identidade: 211 540 → 211 120 — Claude (Opus 5.5)
**Contexto:** o concept §9 estima as linhas de `fact_permuted_predictions` como
4 × 10 × 211 540 + 211 540 (~8,7 M). O medido na Etapa E da 7.1 (technical 7.1 §7, E4) é
211 120 linhas de teste do candidato (3 528 por run, 3 472 no fold 5; 10 × 21 112).
**O que mudou:** este technical usa o valor medido: 41 × 211 120 = 8 655 920 linhas
(identidade incluída) na W4/W5 e na L6; VSN 15 080 decisões × 59 = 889 720. O concept não
é editado (`done`); a diferença é de estimativa, não de contrato nem de critério.
**Razão:** o número esperado das Etapas tem de bater com o silver real, e a ordem de
grandeza do concept (memória, CA14b) continua a mesma.

### 2026-10-19 — [decision] rebase — branch rebaseada sobre a 7.2 mergeada (P1) — Claude (Opus 5.5)
**Contexto:** a premissa P1 do §1 pede a 7.2 mergeada e esta branch rebaseada sobre ela.
A 7.2 entrou em `develop` pelo PR #196 (merge `0f461e1`). Antes do rebase, nenhum
artefato fora deste technical citava hash da branch, e não havia tag.
**O que foi feito:** `git fetch origin` e `git rebase origin/develop`. Houve conflito só
em `docs/roadmap.md`, no commit do roadmap do concept, em cinco trechos:
- tabela de Stages: a linha da 7.2 ficou como o develop deixou (`done`, `+ evaluation`) e
  a da 7.3 como o concept deixou (camadas, fases Windows + Linux, depende de 7.2);
- bloco da 7.4: o comentário do D9 da 7.2 continua. `contratos_introduzidos` junta o
  port do consumidor da 7.2 com as tabelas gold de H3 (um port do inference e um leitor
  no evaluation, padrão do D9). `contratos_consumidos` mantém o item conformal da 7.2 e
  troca `explainability (7.3)` pelas três tabelas gold de H3;
- bloco da 8.1: mantém "tabelas gold conformais do RefreshGold e revisão r2 (7.2)" e põe
  os itens da 7.3 no lugar de `PermutationImportance…`;
- lacunas: a da variante do CQR ficou como o develop deixou, e a do pré-registro de H3
  como o concept deixou ("decidido");
- histórico: as linhas de 2026-10-17 e 2026-10-19 do develop continuam, e a de
  2026-10-18 da 7.3 entrou entre elas, em ordem de data.

HEAD novo: `1507e5a` (`stage 7.3: technical approved`). `$BASE` = `0f461e1`.
**Mapeamento de hashes (antigo → novo):**

| Commit | Antes | Depois |
|---|---|---|
| `stage 7.3: conceptual draft` | `4008871` | `61f95a5` |
| `docs(roadmap): alinha a 7.3 ao concept…` | `58e70aa` | `8292d88` |
| `stage 7.3: conceptual approved` | `be50d72` | `5341530` |
| `stage 7.3: technical approved` | `3204d62` | `1507e5a` |

As citações `be50d72` (§1, Pré-condições) e `58e70aa` (§1 e CA17) devem ser lidas como
`5341530` e `8292d88`. O §1 não é editado (`check_technical_postexec`).
**Razão:** é a P1 do plano. O mapeamento fica aqui porque o §1–§6 está congelado.

### 2026-10-19 — [deviation] gap-7.2 — verificação de gap contra a 7.2 mergeada e o develop — Claude (Opus 5.5)
**Contexto:** a verificação de gap do §1 ("Preparação da Fase 4") rodou sobre o HEAD
rebaseado (`$BASE` = `0f461e1`). Também foi conferido o que o develop trouxe depois da
escrita do plano: a #159 (contrato do dataset TFT), os gates de arquitetura da #61/#160 e
o dono único do evaluation (#118/#167).

**Saída da tabela do §1.** Bateram com o esperado:
- `reproduction_policy.py` (5);
- `ReproductionError` em `inference/application/use_cases/run_inference.py:125`;
- `PKGS_OK`;
- `series_assembly.py` (4);
- o campo `conformal: ConformalParameters | None` (1);
- `R2_OK`;
- `refresh_gold.py` dos DTOs (22);
- `inference-no-mapie-leak` (2);
- `violating == ["Hasher"]` (1);
- as listas de `RefreshParameters(` e `GoldInputs(`.

A lista de `RefreshParameters(` tem seis arquivos: `_gold_inputs.py`,
`test_gold_generation_reader_contract.py`, `test_gold_store_contract.py`,
`test_refresh_gold.py`, `test_refresh_gold_dtos.py` e `test_refresh_gold_use_case.py`.
Todos estão na lista da Task 27. A de `GoldInputs(` tem `_gold_inputs.py` e
`test_refresh_gold_dtos.py`, os dois na Task 28. Também conferem:
- a forma do bloco `[conformal]` (default `None`, `_OPTIONAL_KEYS`, `_check_conformal`
  recusa no r0, `as_payload` só com a chave);
- a r2 ancorada (`aapl_confirmatory-r2-f32ef5ebbbb8`, tag
  `preregistration/aapl_confirmatory-r2-f32ef5ebbbb8`, `.anchor.toml` com `commit`,
  `comment_url` e `anchored_at = 2026-10-19T02:45:31Z`);
- `test_every_revision_hash_quoted` com `[r0, r1, r2]`;
- os helpers `r2_payload()`, `_conformal_parameters.py`, `gold/_cohort_factory.py` e
  `completed_inputs()`, este com `completed_inputs_without_conformal()` e
  `completed_inputs_r0()` ao lado;
- o padrão de infinito (`correction = null` + `infinite`);
- os builders com `depends_on = {QUALITY_CHECKS}` e `runs_when_blocked = False`;
- `RefreshParameters.conformal_parameters` e `refresh_command_from` com
  `prereg.conformal`;
- a aresta única `refresh_gold → calibrate_conformal`.

**Divergências e ajustes:**

| # | Observado | Tasks | Ajuste |
|---|---|---|---|
| G1 | O LAYOUT §7 (l. 311) e o cabeçalho do `bc-independence` contam **34** arestas de runtime, não 28 (a #159 trouxe 6 e a 7.2, 1). O concept §8 já dizia "sobe 7 sobre o número que a 7.2 deixar" | 19, 24 | Task 19: **34 → 40**. Task 24: **40 → 41**. O comentário "(34 hoje)" do `.importlinter` sobe junto |
| G2 | O `grep -cE '^\+…-> '` contra `$BASE` também conta a linha trocada pela Task 07 (G4) | 19, 24 | Contagem por `… \| grep -vc cohort_unit_runner`: **= 6** na Task 19 e **= 7** na Task 24 |
| G3 | `grep -n '_timed("conformal"'` não acha nada, porque a chamada é multilinha (`_timed(` l. 345, `"conformal",` l. 346). A forma é a esperada: `_timed(step, n_in, action, count)`, dentro do ramo sem bloqueio e sob `if parameters.conformal_parameters is not None` | 30 | Conferência por `grep -n '"conformal",'`. A etapa `"h3"` entra logo depois desse bloco, com a mesma forma |
| G4 | `[schema_literals]` já está **vazio** (#159). O `run_confirmatory_cohort.py` importa `DATASET_TFT_LAYER`/`DATASET_TFT_TABLE` do `dataset_tft_contract`, e a aresta está declarada no `.importlinter`. Se o `load_training_grid` sair desse módulo, a linha `run_confirmatory_cohort -> dataset_tft_contract` deixa de casar (`unmatched_ignore_imports_alerting = error`), e `cohort_unit_runner -> dataset_tft_contract` vira aresta nova, que reprova o `bc-independence` | 07, §3 | Proposta, que **muda a lista fechada e aguarda OK antes da Task 07**: sai `scripts/arch_baseline.toml` (nada a remover), sai `train_tft.py` (o alias `DATASET_LAYER` fica desnecessário) e entra `.importlinter`, onde a linha `run_confirmatory_cohort -> …dataset_tft_contract` vira `cohort_unit_runner -> …dataset_tft_contract`. A contagem continua 34, e o LAYOUT §7 continua certo ("as seis `modeling.application.use_cases → …dataset_tft_contract`"). Verificação da Task 07: `lint-imports` + `test_import_contracts.py`. No §3 e na Task 18, o `arch_baseline.toml` passa a não ter **nenhuma** diferença contra `$BASE` (`git diff --exit-code "$BASE" -- scripts/arch_baseline.toml`) |
| G5 | `GOLD_SCHEMAS` e o composition root têm **15** tabelas e builders, mas `CONFIRMATORY_TABLES` tem **14** (sem `quality_checks`) | 29 | Depois da Task 29: 19 schemas, 18 confirmatórias e 19 builders. O `build_order` do `test_composition_root.py` é `quality_checks` seguido dos outros em ordem alfabética, então os `h3_*` entram entre `dm_seed_fraction` e `loss_differentials` |
| G6 | `duplicate_levels(rows_by_level: Mapping[float, Sequence[ForecastRecord]], …)` é tipado pelo `ForecastRecord` | 23, 24 | `PermutedForecastRecord` **compõe** um `ForecastRecord` (`forecast`) com `permuted_family`, `permutation_index`, `permutation_seed`, `permutation_algorithm` e `partition_hash`. A montagem passa os `ForecastRecord` às regras públicas sem cast nem cópia da regra. Os arquivos não mudam |
| G7 | Os gates novos do develop não aparecem no plano: `check_vo_invariants`, `check_use_case_deps`, `check_domain_determinism`, `test_evaluation_validation_single_owner` e as guardas da 7.2 (`test_refresh_gold_imports_only_calibrate_conformal_from_inference`, `test_evaluation_dtos_builders_and_domain_never_import_inference`, `test_refresh_gold_imports_only_the_command_dtos_at_runtime`) | 01, 07–09, 12, 13, 15, 19, 21–30 | O código novo do evaluation valida inteiro por `is_int`/`validate_int_at_least`, número por `is_real_number`/`is_finite_number` e ordem de timestamps por `check_strictly_increasing`. O `permutation_plan` usa `random.Random(semente)` local, nunca função de módulo do `random`. Os `__init__` de use case recebem ports, ou use case do mesmo slice (`TrainTft` no `RunAblationCohort`). `refresh_gold.py`, DTOs, builders e domain do evaluation não importam nada novo do inference, e o catálogo de H3 duplica as constantes, travado pelo teste de integração da Task 21. A guarda da Task 29 cobre o modeling. A parte do inference já é coberta pela guarda da 7.2 |
| G8 | Os testes unitários do `RunInference` (7.1) leem o silver pelo `FakeAnalyticsRepository`, não pelo `FakeSilverTableReader` do evaluation | 19 | A Task 19 segue o padrão da 7.1: o `FakeAnalyticsRepository` já tem as tabelas novas desde a Task 14. A edição do `fake_silver_table_reader.py`, que está na lista, continua para servir à Task 30 |
| G9 | `[handoff]` não é tag aceita por `check_technical_postexec.py` (`ENTRY_TAGS` = decision, finding, deviation, measurement, CONVENTIONS §3.4) | 33, L0 | O cabeçalho da entrada fica `### <data> — [decision] handoff — …`. O `test_handoff_cites_only_known_subcommands` localiza a entrada pelo escopo `handoff`, e "a entrada `[handoff]`" do plano se lê assim |
| G10 | O composition root tem `_TRAINERS_DEVICE = "cpu"` como `supported_device` de cinco construções | 03 | Não é divergência. O `_SUPPORTED_DEVICES` novo convive com ele, e as fábricas confirmatória e de inferência seguem com `"cpu"` |

**Ambiente** (o §1 manda colar aqui). Por orientação do orquestrador, a Stage usa o volume
próprio `financial-forecasting_ff73-venv`, sincronizado por `uv sync --extra dev`, e não
o compartilhado `financial-forecasting_app-venv`. Os gates rodam como
`--name ff-gate-186`, com `--cpus 6 --memory 8g --memory-swap 8g`,
`PYTEST_PAR='-n 4 --dist loadgroup'` e um gate de 8 GB por vez. O nome é a trava, e
container alheio nunca é tocado. A função `run()` do §1 fica com
`VENV=financial-forecasting_ff73-venv` e `--name ff-gate-186`. Saída medida:
1. `uv lock --check` → `Resolved 182 packages`, exit 0 (uv 0.12.3 na imagem; o CI pina
   0.11.28, `[finding]` da 7.2);
2. `import torch, mapie` → `2.13.0+cpu 1.5.0`.

**Razão:** G1–G3, G5 e G10 são números e formas medidos, e nenhuma assinatura consumida
mudou. G6–G9 cabem nas listas fechadas. Só G4 mexe numa lista fechada, por isso fica
como pergunta antes da Task 07 (§1, "sem mudar a lista fechada sem perguntar").

### 2026-10-19 — [decision] gates — plano de gates da fase Windows pela ADR 0.0.0059 (Tasks 01–33) — Claude (Opus 5.5)
**Contexto:** este technical foi escrito sob a ADR 0.0.0055 e roda `make check` por Task
em 06, 07, 08, 16, 17, 18, 19, 24, 29, 32 e 33, `make check-block` em 01, 03, 10, 11 e
20, `check-task` nas demais e `check-block` em cada Checkpoint C. O develop agora segue
a [ADR 0.0.0059](../../adr/0_0_0059-planned-full-gate-budget-per-stage.md) (fonte
operacional: [RUNBOOK §Gates em camadas](../../RUNBOOK-STAGE-LIFECYCLE.md#gates-em-camadas)):
por Task, só os testes da Task, e de 1 a 3 `make check` por Stage, a saída incluída. O
plano entra aqui porque o §1–§6 está congelado. **Esta entrada prevalece** sobre as
linhas `make check-task …`, `make check-block …`, `make check $PAR` e "Checkpoint C (T2
…)" das Verificações das Tasks 01–33. As demais linhas das Verificações (`git diff`,
`grep`, `test`, `scripts/check_*.py` citados) continuam, com os ajustes G1–G4 do
`[deviation] gap-7.2`.
**Pergunta:** onde rodam os `make check` da fase Windows?
**Opções:**
- A — manter o plano aprovado: mais de 25 gates de suíte, muito acima do orçamento.
- B — três pontos (depois da 12, depois da 24 e na saída, antes da Task 33). Por Task,
  só os testes da Task e os gates específicos que ela toca. ✅ recomendada.
**Decisão:** B.

**Por Task (T1).** Antes de todo commit roda `run sh -c "$PRE; uv run --no-sync pytest
<arquivos de teste que a Task escreveu ou alterou> -q --no-cov"`. Também rodam
`uvx ruff@0.6.9 format` só nos arquivos tocados pela Task (o ruff pinado do hook; ver o
`[decision] ambiente` do formatador abaixo), `uv run --no-sync ruff check <arquivos
tocados>` e `uv run --no-sync mypy src/`, à mão e no container, porque a worktree só tem o hook
`commit-msg` e não o pre-commit. Teste vermelho bloqueia o commit. Os extras abaixo
rodam só quando a Task toca o que eles guardam. São scripts e testes de segundos, sem
`make`:

| Task toca… | Roda também | Tasks |
|---|---|---|
| VO novo ou alterado em `domain/value_objects/` | `python scripts/check_vo_invariants.py` | 01, 13, 21, 22, 23, 24 |
| módulo de `*/domain/` | `python scripts/check_domain_determinism.py` | 01, 13, 21–26 |
| `shared/domain/value_objects/` com hasher, ou `docs/LAYOUT.md` | `python scripts/check_layout.py` | 01, 19, 24 |
| `__init__` de use case novo ou alterado | `python scripts/check_use_case_deps.py` | 07, 08, 09, 12, 15, 19 |
| `application/` do modeling que lê o dataset | `python scripts/check_schema_literals.py` | 02, 07, 08, 09, 12 |
| `.importlinter` | `uv run --no-sync lint-imports` + `pytest tests/architecture/test_import_contracts.py --no-cov` + a contagem G2 | 07 (se o G4 for aprovado), 19, 24 |
| port, fake de port ou `[port_coverage]` do baseline | `python scripts/check_port_coverage.py --list` + `pytest tests/architecture/test_port_coverage_gate.py --no-cov` | 04, 11, 16, 17, 18 |
| fake novo ou alterado em `tests/fakes/` | `python scripts/check_fake_parity.py` | 04, 11, 14, 16, 17, 19 |
| `src/` do evaluation | `pytest tests/architecture/test_evaluation_validation_single_owner.py --no-cov` | 21–30 |
| `tests/unit/features/evaluation/` | `pytest tests/architecture/test_unit_evaluation_purity.py --no-cov` | 21–30 |
| `refresh_gold.py`, DTOs, builders ou domain do evaluation | `pytest tests/architecture/test_stage_7_2_regression_guards.py --no-cov` | 21–30 |
| composition root, ou `SILVER_REGISTRY` lido por ele | `pytest tests/unit/shared/test_composition_root.py --no-cov` (inteiro) | 03, 10, 11, 14, 20, 29 |
| `docs/LAYOUT.md` ou a §7 deste technical | `python scripts/check_technical_postexec.py docs/stages/7.3-explainability/technical.md` + `python scripts/check_docs_pointers.py` | 01, 19, 24, 33 e todo commit `[7.3/--]` |

Os `python scripts/…` rodam como `uv run --no-sync python scripts/…` no container, porque
os de arquitetura importam a lib AST do repo. Os testes de `tests/architecture/` que a
própria Task cria (06, 08, 16–18, 29, 32, 33) já estão nos testes da Task. Esses extras
não são gate completo: cobrem o ponto cego do T1, que não roda `tests/architecture/`,
só para o gate que a Task pode quebrar. `check-task` e `check-block` saem da rotina.
`check-task` só roda com motivo concreto registrado aqui.

**Gates completos (`make check $PAR`, T3): 3 pontos, a saída incluída.**

| # | Depois de | Por quê |
|---|---|---|
| A | Task 12 | Fecha o grupo **modeling + shared**: o VO de `shared/` e o LAYOUT (01), o composition root e o CLI (03, 10, 11), a extração do executor com a rede da 5.5 e a aresta trocada (07, G4), a guarda AST nova (08) e a extensão do Protocol `TftCheckpointPredictor` com o fornecedor (11, 12). É também o primeiro gate completo depois do rebase sobre a 7.2 e no volume novo. Esperar o ponto B deixaria as Tasks 13–24 construídas sobre uma base possivelmente quebrada, entre elas o contrato `[fake, real]` da Task 16, que importa o fornecedor da 12, e as suítes da 5.5/7.1 |
| B | Task 24 | Fecha o grupo **contratos entre slices e config de gate**: o `SILVER_REGISTRY` lido pelo teste do composition root (14), o par do ADR 6.1.0005 no `arch_baseline.toml` e no `test_port_coverage_gate.py` (17 → 18), `tests/architecture/` (16–19), as arestas 1–6 e 7 no `.importlinter`/LAYOUT §7 (19, 24), o wiring e o CLI do `attribute` (20) e o `Preregistration` com `[h3]` (22), lido pelo refresh (27) e pelo rascunho da r3 (32). As duas edições do `.importlinter` ficam sob um ponto só. Nada em 21–24 depende do wiring da 20, porque o evaluation não importa o inference. Por isso um defeito em 19–20 se corrige no lugar, sem refazer Tasks, e o ponto não precisa vir depois da 20 |
| C | saída da fase Windows (§3) | Depois da Task 32, do Checkpoint C 29–32 e da auditoria de testes, **antes da Etapa W e da Task 33**. É o "Gate da fase Windows" do §3, com as conferências de lá: cobertura ≥ 90 % por arquivo tocado, port-coverage, `arch_baseline.toml` sem diferença contra `$BASE` (G4), `["Hasher"]`, `check_technical_postexec` e `NO_R3_BEFORE_LINUX`. Cobre 25–32: o refresh mecânico (27), o `gold_schema` com o composition root e a guarda (29), o `RefreshGold` (30), o e2e (31) e o rascunho (32). É a pré-condição "`make check` verde no HEAD" da Etapa W |

**Ordem do fecho Windows.** A sequência fica Task 32 → Checkpoint C 29–32 → auditoria
de testes, com os seus `fix` → **ponto C** → Etapa W → commit de evidência (só §7) →
Task 33. Isso troca a ordem do §2 entre a Etapa W e a auditoria. A Etapa W não produz
código, e auditar antes deixa o ponto C como o último. Entre o ponto C e a Task 33 só
entram commits de §7, conferidos por `check_technical_postexec` e
`run sh -c "$PRE; make docs-check"`. O X do handoff é o HEAD antes da Task 33: o do
ponto C ou um descendente dele que só muda a §7. A Task 33 roda o T1 (o seu teste,
`check_technical_postexec` e `make docs-check`), e o CI do PR (T4) é o gate completo
do commit dela. Se alguma mudança em `src/` ou `tests/` entrar depois do ponto C (falha
da Etapa W que peça correção, por exemplo), o ponto C roda de novo e isso vira
`[deviation]` de 4º ponto, com a justificativa.

A saída de cada ponto é colada nesta §7. Ponto vermelho → commit
`fix(<escopo>): … [7.3/task-NN-fix]` antes da próxima Task.

**Checkpoint C** (revisão do diff do bloco por subagente de contexto zerado, **sem** gate
de suíte), em blocos de 3 a 5 Tasks: **01–04**, **05–08**, **09–12** (depois do ponto A),
**13–15**, **16–20**, **21–24** (depois do ponto B), **25–28** e **29–32**. O último bloco
inclui a revisão do conjunto contra o concept. O plano tinha um bloco só para a 32, e
ele foi unido ao 29–31 para ficar na faixa de 3 a 5.

**Fase Linux (L0–L8):** fora deste plano. Valem os gates da tabela do §2: os testes de
repo da L7 e o `make check` da L8, num venv travado sem o torch ROCm, ou o CI do PR.

**Ambiente:** o do `[deviation] gap-7.2`. Gate completo como `--name ff-gate-186`, um
por vez, volume `financial-forecasting_ff73-venv`, log em arquivo montado, só aspas
simples dentro de `sh -c "…"`.
**Razão:** ADR 0.0.0059 itens 1–6. O orçamento fica em 3, e cada ponto do meio fecha um
grupo cuja quebra invalidaria as Tasks seguintes.

### 2026-10-19 — [decision] Task 07 — lista fechada ajustada pelo G4 (aprovação do orquestrador) — Claude (Opus 5.5)
**Contexto:** o G4 do `[deviation] gap-7.2` ficou como pergunta, porque mexe numa lista
fechada. O orquestrador aprovou a proposta recomendada em 2026-10-19, junto com o plano
de gates.
**O que foi decidido:**
- **Task 07, lista fechada:** saem `scripts/arch_baseline.toml` e `train_tft.py`, e entra
  `.importlinter`. Lá, a linha `…use_cases.run_confirmatory_cohort ->
  …feature_engineering.domain.services.dataset_tft_contract` vira `…use_cases.cohort_unit_runner
  -> …dataset_tft_contract`. O `cohort_unit_runner` importa `DATASET_TFT_LAYER` e
  `DATASET_TFT_TABLE` do `dataset_tft_contract`. A contagem de arestas de runtime
  continua 34, e o LAYOUT §7 não muda.
- **Verificação da Task 07:** `lint-imports` + `pytest tests/architecture/test_import_contracts.py`
  + `python scripts/check_schema_literals.py` + `git diff --exit-code "$BASE" --
  scripts/arch_baseline.toml`.
- **§3 e Task 18:** o `scripts/arch_baseline.toml` não pode ter **nenhuma** diferença contra
  `$BASE` (`git diff --exit-code "$BASE" -- scripts/arch_baseline.toml`). Não sobra a
  remoção das chaves de `[schema_literals]`, porque elas não existem mais.
- **Lock do índice:** se um `index.lock` órfão aparecer de novo, ele é removido só sem
  processo git nem container ativo, e a ocorrência vira `[finding]` apontando a #199. Os
  containers desta Stage rodam com `GIT_OPTIONAL_LOCKS=0`.
**Razão:** aprovação explícita do orquestrador. A troca mantém o débito medido igual: a
aresta muda de módulo dentro do mesmo slice, e o `unmatched_ignore_imports_alerting =
error` continua cobrando a lista.

### 2026-10-19 — [decision] Task 02 — tag `phase` dos runs LOCO e literais medidos — Claude (Opus 5.5)
**Contexto:** a Task 02 deixa a tag `phase` do tracker nos runs LOCO para o executor,
com `"confirmatory_ready"` recomendada e `"ablation"` como alternativa.
**O que foi decidido:**
- Fica **`phase = "confirmatory_ready"`**. O run LOCO segue o procedimento
  pré-registrado, e a configuração já está no `model_version`
  (`tft_quantile_loco_<configuração>`), na tag `model_version` e nos params do tracker.
  `test_tracking_phase_tag_of_loco_runs` fixa o valor.
- Os literais de `test_default_command_keeps_the_pinned_run_id_and_config_signature` foram
  medidos no `$BASE` (`0f461e1`), antes da mudança, com as fixtures de `test_train_tft.py`:
  `run_id` do fold 0 `ea8ed2e8…216d`, do fold 1 `640eb66b…f279`, `config_signature`
  `b5d077bd…4c62`. O teste usa os valores completos.
- O teste do corte do grid foi conferido por mutação: aparar pelo subconjunto
  (`trim_columns = feature_names`) reprova os 4 casos parametrizados.
**Razão:** é a opção recomendada pelo plano, e é reversível (só a tag do tracker, fora
do `run_id` e do silver).

### 2026-10-19 — [decision] ambiente — formatador pinado e git sem locks opcionais (aprovação do orquestrador) — Claude (Opus 5.5)
**Contexto:** a worktree não tem o hook de pre-commit, e o ruff do venv (0.15.20)
reformataria 33 arquivos já commitados. O hook pina o ruff 0.6.9
(`.pre-commit-config.yaml`).
**O que foi decidido:**
- O check de formato de cada Task é `uvx ruff@0.6.9 format` só nos arquivos tocados,
  igual ao hook. `ruff check` e `mypy src/` rodam com as versões do venv, iguais às do
  `make lint`/`make typecheck`.
- Todo container desta Stage roda com `GIT_OPTIONAL_LOCKS=0`, porque o `git status` de
  dentro do container não deve deixar `index.lock` na worktree.
Os dois foram aprovados pelo orquestrador junto com as Tasks 01–04.
**Razão:** mantém o estilo já commitado e evita o lock órfão. Nenhum contrato muda.

### 2026-10-19 — [finding] tooling — deriva do formatador: ruff 0.15.20 do venv × 0.6.9 do pre-commit — Claude (Opus 5.5)
**Contexto:** `uv run --no-sync ruff format --check src tests` com o ruff 0.15.20 do
`uv.lock` reformataria **33 arquivos** já commitados, todos anteriores a esta Stage. O
ruff 0.6.9 pinado no `.pre-commit-config.yaml` aceita os mesmos arquivos. A diferença
mais vista é a junção de strings implícitas concatenadas. O `make check` não roda
`ruff format --check`, então a deriva não aparece no gate.
**Direção sugerida:** tratar na #198, alinhando o pin do hook à versão do `uv.lock` (ou o
contrário) e reformatando o repo num commit só de formato, fora desta Stage. Até lá, a
7.3 formata só os arquivos tocados com `uvx ruff@0.6.9` (`[decision] ambiente` acima).
Achado C1-6 do Checkpoint C 01–04.

### 2026-10-19 — [finding] tooling — correção do achado anterior: o ruff 0.6.9 também reformata arquivos commitados — Claude (Opus 5.5)
**Contexto:** a entrada anterior diz que o ruff 0.6.9 do hook "aceita os mesmos
arquivos". Isso não confere. Uma chamada acidental de `uvx ruff@0.6.9 format` sem
argumentos (lista de arquivos vazia) formatou o repo inteiro e mudou **38 arquivos**:
34 anteriores à Stage, em `scripts/`, `.claude/hooks/`, `src/` e `tests/`, mais os desta
Stage. A mudança foi revertida por `git checkout` antes de qualquer commit, e nada
dela entrou na branch.
**O que muda:** a deriva é dos dois lados. Nem o 0.15.20 nem o 0.6.9 deixam o repo
como está. A direção da #198 continua: um pin só e um commit só de formato. A regra
da 7.3 também continua: formatar só os arquivos tocados. A partir de agora, todo
comando de format é guardado por `[ -n "$F" ] || exit 1`.

### 2026-10-19 — [deviation] Task 07 — logger da máquina compartilhada com o nome do próprio módulo (C2-11) — Claude (Opus 5.5)
O `cohort_unit_runner` loga em `logging.getLogger(__name__)`, e não mais no logger
`…run_confirmatory_cohort`. As mensagens por unidade são as mesmas, e o
`test_each_unit_logs_its_start_and_outcome` da 5.5 segue verde sem mudança. Achado
C2-11 do Checkpoint C 05–08, aceito pelo orquestrador.

### 2026-10-19 — [deviation] Tasks 06 e 08 — `check_ablation_declarations` mora na application (C2-6) — Claude (Opus 5.5)
**Contexto:** a Task 06 pôs a conferência da base e da registry
(`check_ablation_declarations`) no loader (`adapters/in/cli/ablation_cohort_file.py`).
Assim, só quem carregava o arquivo por ali estava protegido. O Checkpoint C 05–08
(C2-6) pediu que o executor também conferisse.
**O que mudou:**
- a função foi para `modeling/application/use_cases/run_ablation_cohort.py`;
- o loader continua chamando a função, agora importada de lá;
- o `RunAblationCohort` também chama a função, antes do lock e do probe, e recalcula
  o `CohortHash` da base contra `spec.base_cohort_hash`.

Também antes do lock, o executor passou a recusar duas coisas: `feature_set_name` igual
ao da base (C2-1) e um `trainer_device` injetado diferente do `device` declarado (C2-2).
A guarda de hardware passou a comparar também o `device` da foto do probe. O composition
root passa como `trainer_device` o mesmo device com que montou o proxy do treinador. O
`device = "cuda"`, fora do mapa, já é recusado pela fábrica sem importar torch
(`test_ablation_factory_refuses_device_outside_the_map_without_importing_torch`, CA3).
**Razão:** é defesa em profundidade pedida pela revisão. Nenhum contrato publicado muda.
O construtor do `RunAblationCohort` ganha `trainer_device`, e a Task 10 já o passa.

### 2026-10-19 — [decision] Task 11 — forma da predição de atribuição no adapter — Claude (Opus 5.5)
**O que foi decidido** (escolhas locais que o §1 não fixa):
- **Uma passagem `mode="raw"` com `return_x`** produz os blocos doadores e os pesos da
  VSN de uma vez. Ela é seguida da identidade, pelo `_emit` sobre o dataloader que o
  `predict` montaria (`to_dataloader(train=False, batch_size, num_workers=0)`), e de
  uma passagem por (família, k). O `_emit` não mudou de assinatura: recebe o dataloader
  pelo parâmetro de sempre, e o caminho da 7.1 segue passando o dataset.
- **Decisão sem amostra de predição** (a última decisão de um fold que encosta no fim do
  painel, sem nenhum horizonte) não pode doar nem receber: o adapter ergue `ValueError`.
  O fornecedor da Task 12 passa só as decisões de teste que têm emissão, as mesmas do
  silver da 7.1, que formam uma faixa contígua.
- **Regras compartilhadas, sem cópia:** a carga com sha256 e entradas declaradas
  (`_load_checked_checkpoint`), a seleção da amostra de decodificador mais longo
  (`_best_sample_by_decision`) e os `settings` são as mesmas funções da 7.1.
  `check_donors` mora no módulo do port, para o real e o fake usarem a mesma regra.
- **Verificação:** os goldens da 7.1 seguem sem diferença contra `$BASE`. O mutante
  "doador = a própria posição" (`blocks[p]`) reprova o teste do doador em outro lote e
  o da família informativa.
**Razão:** são escolhas reversíveis dentro da lista fechada da Task 11.

### 2026-10-19 — [measurement] gates — ponto A (depois da Task 12 e dos fixes do Checkpoint C 05–08) — Claude (Opus 5.5)
Container `ff-gate-186` (`--cpus 6 --memory 8g --memory-swap 8g`, volume
`financial-forecasting_ff73-venv`), comando `uv lock --check && make check
PYTEST_PAR='-n 4 --dist loadgroup'`.

**1ª corrida (HEAD `d53bbc9`): vermelha.** `4 failed, 7441 passed, 26 skipped`, EXIT=2:
- três testes de `tests/integration/features/modeling/test_pf_tft_prediction.py` (5.4)
  chamam `PfTftTrainer._emit` sem `accelerator`, que a Task 03 tornou obrigatório
  (`TypeError`);
- a guarda I14 da 6.6 (`test_no_test_or_script_reads_the_real_cohort`) achou o
  `cohort_id`/hash do r0 como literal em `test_stage_7_3_repo_files.py` e em
  `test_ablation_cohort_spec.py`.

**Fixes:**
- `8e65e0f`: `fix(modeling): accelerator do _emit com default cpu [7.3/task-03-fix]`;
- `28b8510`: `test(modeling): testes da 7.3 sem os literais do cohort real
  [7.3/task-06-fix]`. Os testes de repo comparam com o `[cohort]` da r2 ancorada, e o
  teste do spec usa um `cohort_id` sintético.

Fica registrado para o §3: a linha `! grep … "aapl_confirmatory-r0-665f45d9169a"` do gate
da fase Windows excluía `test_stage_7_3_repo_files`, mas a guarda da 6.6 não exclui. A
regra que vale é a da guarda: nenhum teste da 7.3 cita o literal.

**2ª corrida (HEAD `28b8510`): verde.** lint, mypy (364 arquivos), layout, import-linter
(17 kept, 0 broken), fake-parity, port-coverage (1 no baseline), use_case_deps,
domain_determinism, schema_literals e vo_invariants passaram. Últimas linhas:
```
Required test coverage of 90.0% reached. Total coverage: 98.97%
========== 7445 passed, 26 skipped, 701 warnings in 875.60s (0:14:35) ==========
EXIT=0
```
Sem "node down". A 2ª corrida é a repetição do ponto A depois do vermelho (ADR
0.0.0059 item 7), e não um ponto novo do orçamento.

### 2026-10-19 — [deviation] Task 14 — registry com 4 tabelas e docstrings do repositório sem mudança — Claude (Opus 5.5)
**Observado:** o `SILVER_REGISTRY` do develop tem **2** tabelas (`dim_run`,
`fact_oos_predictions`), porque a #164 tirou as 3 que não tinham escritor. Com as duas
novas, ficam **4**, e não as 7 que a Task 14 supõe
(`test_registry_has_seven_tables`). O teste da Task se chama
`test_registry_has_four_tables_with_the_stage_7_3_pair`.

As docstrings de `analytics_repository.py` e `parquet_analytics_repository.py` já
descrevem a partição de forma genérica ("quantos níveis o `partition_by` declarar",
"N níveis"), sem o "1..3" que a Task mandava trocar. Por isso não foram editadas, e os
dois arquivos ficaram de fora do commit. O adapter monta o glob e os predicados a partir
de `partition_by`, sem profundidade fixa. A ida e volta com 4 níveis em Parquet real
(`run_id=…` no caminho) é coberta pelos testes de integração da Task 15.

**Também:** o vocabulário de famílias dos schemas (`price`, `technical`, `sentiment`,
`fundamental`, `none`) é literal no `analytics_store`, que é o dono do schema e não
importa o `modeling`. A partição real fica travada pela conferência do `partition_hash`
(I17).

<!-- END: post-execution -->
