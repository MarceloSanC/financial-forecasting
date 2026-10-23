# Auditoria de reprodução da geração julgada — AAPL, pré-registro `aapl_confirmatory` r3

Stage 8.2 (A3, A3b, A4, A7, A8). Fonte do procedimento:
[`docs/stages/8.2-equivalence-audit/technical.md`](../stages/8.2-equivalence-audit/technical.md)
(Etapas E2 e E3; saídas literais no §7). Teoria:
[`docs/domain/evaluation/reproduction-equivalence-and-reporting.md`](../domain/evaluation/reproduction-equivalence-and-reporting.md) §4.

## 1. Claim

- **(a) Afirmado.** No ambiente registrado da corrida confirmatória e no caminho de cálculo da
  geração julgada (commit `060537fc7069b38a318bb5cf839d84b7767b1b4f`), a cadeia silver → gold →
  scorecard, executada de novo a partir dos dados persistidos (backup de entrada da 8.1
  restaurado num `data_root` descartável), **sem re-treino**, reproduz a geração julgada **bit a
  bit**: as 19 tabelas gold e o scorecard, inclusive as colunas das etapas aleatórias (R3).
- **(b) Citado.** As predições de teste reproduzem a partir dos checkpoints bit a bit no ambiente
  do cohort — resultado da Stage 7.1
  ([`docs/stages/7.1-inference-engine/concept.md`](../stages/7.1-inference-engine/concept.md));
  esta Stage não o reexecuta.
- **(c) Não executado.** Reprodução em outro ambiente (classes R1/R2/R3 com tolerância R2) não foi
  feita: houve um único ambiente (decisão D4 do concept). Nada aqui afirma (c).

O claim é o da **execução em `060537fc`**: a árvore usada é a desse commit; o HEAD da 8.2 só
fornece o driver (montado fora dos caminhos do probe) e o comparador.

## 2. Identidade

| campo | julgada | reproduzida | igual |
|---|---|---|---|
| `preregistration_ref` | `aapl_confirmatory-r3-00fd83d9cd39` | `aapl_confirmatory-r3-00fd83d9cd39` | sim |
| partição | `AAPL/aapl_confirmatory-r0-665f45d9169a` | `AAPL/aapl_confirmatory-r0-665f45d9169a` | sim |
| `silver_content.digest` | `7ac4c759c966b8e1914cd33492a8a598a3b57bcb63eff1e80e9ede1bd02a74e2` | idem | sim |
| `dataset_fingerprint` | `00e4406dcd96658d557f7d4d86face9874fac42385e3cb182d54c5d2286695bd` | idem | sim |

`generation_digest` da cópia julgada (sha256 do `CONTENTS.sha256`):
`96c0541301885ed1c6688a517176f63a54e872a3e18ee82fbb5c23121747e539`.

## 3. `result_digest`

| lado | digest |
|---|---|
| julgado | `7c7940d4f77ff772212d5ddc392ee46e5f46cebe06506c17a20885b7f0e31b7e` |
| reproduzido | `7c7940d4f77ff772212d5ddc392ee46e5f46cebe06506c17a20885b7f0e31b7e` |
| esperado (`input_read` do `ATTEMPTS.jsonl`) | `7c7940d4f77ff772212d5ddc392ee46e5f46cebe06506c17a20885b7f0e31b7e` |

`audit-reproduction` (HEAD, raízes `:ro`): exit 0, `bit_identical true`.

## 4. Comparação por classe e por tabela

Totais:

| classe | comparados | diferentes | max \|Δ\| |
|---|---|---|---|
| R1 | 882 727 | 0 | 0.0 |
| R2 | 288 671 | 0 | 0.0 |
| R3 | 1 856 | 0 | 0.0 |

Por tabela (`comparados/diferentes/max |Δ|`; `None` = sem valor numérico na classe):

| tabela | linhas | chaves iguais | R1 | R2 | R3 |
|---|---|---|---|---|---|
| gold_calibration_table | 10368/10368 | sim | 279936/0/0.0 | 186624/0/0.0 | 0/0/None |
| gold_christoffersen_monte_carlo | 576/576 | sim | 9216/0/0.0 | 1152/0/0.0 | 1728/0/0.0 |
| gold_conformal_corrections | 1440/1440 | sim | 23040/0/0.0 | 10080/0/0.0 | 0/0/None |
| gold_conformal_coverage | 704/704 | sim | 12672/0/0.0 | 14080/0/0.0 | 0/0/None |
| gold_differential_acf | 1302/1302 | sim | 11718/0/0.0 | 1302/0/0.0 | 0/0/None |
| gold_differential_breaks | 42/42 | sim | 588/0/0.0 | 126/0/0.0 | 0/0/None |
| gold_dm_profiles | 276/276 | sim | 5244/0/0.0 | 1380/0/0.0 | 0/0/None |
| gold_dm_results | 24/24 | sim | 336/0/0.0 | 144/0/0.0 | 0/0/None |
| gold_dm_seed_fraction | 12/12 | sim | 108/0/0.0 | 24/0/0.0 | 0/0/None |
| gold_h3_importance | 256/256 | sim | 2816/0/0.0 | 256/0/0.0 | 0/0/None |
| gold_h3_reading | 1/1 | sim | 20/0/0.0 | 1/0/0.0 | 0/0/None |
| gold_h3_shares | 8/8 | sim | 120/0/0.0 | 32/0/0.0 | 16/0/0.0 |
| gold_h3_vsn | 63/63 | sim | 630/0/0.0 | 189/0/0.0 | 0/0/None |
| gold_loss_differentials | 63336/63336 | sim | 506688/0/0.0 | 63336/0/0.0 | 0/0/None |
| gold_mcs_block_sensitivity | 28/28 | sim | 448/0/0.0 | 28/0/0.0 | 56/0/0.0 |
| gold_mcs_results | 28/28 | sim | 420/0/0.0 | 56/0/0.0 | 56/0/0.0 |
| gold_metrics_by_run | 1880/1880 | sim | 22560/0/0.0 | 7520/0/0.0 | 0/0/None |
| gold_partial_degeneracy | 576/576 | sim | 5760/0/0.0 | 2304/0/0.0 | 0/0/None |
| gold_quality_checks | 37/37 | sim | 407/0/0.0 | 37/0/0.0 | 0/0/None |

Scorecard (sem `manifest_read.started_at`/`finished_at`): igual, 66 117 folhas, 0 diferentes,
max |Δ| 0.0. Driver: `refresh COMPLETED tables 19`, `scorecard sha256
25b3e0a6e279c96aee1c825cdf1891a863c252064f4cc17ca0f14683a96d3ebf`.

## 5. Ambiente

| item | valor |
|---|---|
| imagem | `sha256:b69a7620e7bd8449369bde2f46e903c5f46c25e9efb3597f452af3272e0a8f45` (pelo id) |
| `cpu.max` | `600000 100000` (6 CPUs; `--cpus 6 --memory 8g`) |
| kernel | `6.18.54.1-microsoft-standard-WSL2` |
| Python / torch | `3.12.13` / `2.13.0+cpu`, `torch_threads 6` |
| `uv pip freeze` (sha256) | `0c95c798bd37701400d62f8b2f17e4504277fc71b91d64566b34091eb328035f` na E2 e na E3 (`FREEZE_SAME`) |
| `.env` copiado (sha256) | `408e44ff45f7883e2540d2e38650dea3f61d8e36a9a96bb51c6bce9f28bfd69b` |
| `uv.lock` de `060537fc` = do HEAD | sim |
| `ENV_EQUAL` | `--check` e corrida: todas as chaves `code.*`/`env.*` iguais às da linha `started` do `ATTEMPTS.jsonl` da ref (`code.src 4d2b2540…`, `code.uv_lock 0f36050a…`, `code.cohort_file 6d7c8b82…`, `code_dirty false`, `preregistration_dirty false`, imagem, libs e probe); foto da corrida byte a byte igual à do `--check` |

Tempo da corrida: 2026-10-23T20:08:36Z → 20:22:49Z (14,2 min; exit 0, sem OOM).

Blobs do driver e dos scripts de evidência (iguais no HEAD e no `GATE1`
`096a2e9be7452fd3989abf9896300d6fc99dda0e`, cópia de trabalho = blob):

```
scripts/reproduce_judged_generation.py 855aaa02744f30d13dcae74beea1274bb95b7aff
scripts/reproduction_evidence.py       960598f5229765f68b2102c3622d35aaa4e166d2
tests/equivalence/prior_evidence.py    f04e2f2a8699d05512725c563cad93d267148a76
```

## 6. R-BIT-COMMIT

`060537fc..64b8a17d` (base fixa), `ast.dump` sem docstrings no Python 3.12.13 do container —
15 arquivos, todos `AST_EQUAL` (`files 15 ast_diff 0`): `refresh_gold.py`,
`attribution_assembly.py`, `joint_contribution.py`, `cohort_progress_ledger.py`,
`run_ablation_cohort.py`, `run_gbm_sweep.py`, `run_tft_sweep.py`, `loco_identity.py`,
`training_grid.py`, `walk_forward_splitter.py`, `scope_spec.py`, `config_signature.py`,
`family_partition_hash.py`, `pagination.py`, `middlewares.py`.

`64b8a17d..HEAD -- src/` (acréscimos da 8.2), cada um fora do caminho refresh/scorecard:

| arquivo | justificativa |
|---|---|
| `application/dtos/reproduction_comparison.py` (A) | DTO do comparador |
| `application/use_cases/reproduction_comparison.py` (A) | comparador puro |
| `application/use_cases/audit_reproduction.py` (A) | use case do subcomando |
| `application/ports/out/judged_generation_store.py` (M) | leitura da cópia julgada |
| `adapters/in/cli/evaluation_commands.py` (M) | subcomando `audit-reproduction` |
| `cli.py`, `composition_root.py` (M) | wiring do subcomando (despachado antes do `wire_dependencies`, que não muda) |
| `adapters/out/duckdb/parquet_gold_store.py` (M) | **no caminho de leitura do scorecard**: extração de `_read_generation_dir` sem mudança de comportamento (suíte de contrato do `GoldGenerationReader` verde); fora do claim, que é o de `060537fc` (`[deviation]` de redação do A7 no §7) |

## 7. Partição viva e efeitos de julgamento

- Antes (E2) e depois (E3): os 355 arquivos de `data/cohorts/aapl` com o mesmo sha256 e nenhum
  arquivo novo (`LIVE_INTACT`); `current/MANIFEST.json` `56d3ee1c…`, `judged/ATTEMPTS.jsonl`
  `320def2b…`, `CONTENTS.sha256` da cópia `96c05413…` (`JUDGED_COPY_OK`, `DIGEST_OK`).
- A partição viva não foi montada no container da reprodução; o `audit-reproduction` a montou
  `:ro`.
- Nenhum `judged/` nem `ATTEMPTS.jsonl` no descartável (`NO_JUDGMENT_IN_DISPOSABLE`). O
  descartável `data/reproductions/aapl-r3-20261023-190339` (git-ignorado) fica como evidência.
- Pré-checagem de processo (A3b, I5): `test_reproduction_process_independence.py` verde no
  `make check` do `GATE1`.

## 8. Comandos

Os blocos literais estão no runbook (technical §2, E2 e E3), com as emendas do §7
(`env-equal … --preregistration-ref "$REF"`). Resumo:

```bash
git -C "$WTH" worktree add --detach "$REPROH" 060537fc7069b38a318bb5cf839d84b7767b1b4f
MSYS_NO_PATHCONV=1 docker run --rm $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; $DRIVER --check"
MSYS_NO_PATHCONV=1 docker run -d --name ff82-repro $RES $RMOUNTS $RENVS "$IMAGE_ID" sh -c "$PRE; $DRIVER"
python scripts/reproduction_evidence.py env-equal "$P/judged/ATTEMPTS.jsonl" "$DISPH/reproduction/environment.json" --preregistration-ref "$REF"
MSYS_NO_PATHCONV=1 docker run --rm $RES $HMOUNTS -v $MAIND/data/cohorts/aapl:/judged:ro -v $DISPD:/reproduced:ro $HENVS "$IMAGE_ID" \
  sh -c "$PRE; uv run --no-sync python -m financial_forecasting.cli audit-reproduction --judged-data-root /judged --reproduced-data-root /reproduced --preregistration aapl_confirmatory --revision 3 --preregistration-ref $REF"
```
