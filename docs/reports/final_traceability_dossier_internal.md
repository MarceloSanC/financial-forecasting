# Interno, fora do texto do TCC — dossiê final de rastreabilidade

Como regenerar: regenerar em qualquer commit com code.src = a92759b6c813518d72588be2704340b5110636ea: `report-artifacts --data-root <data_root> --cohort <arquivo de cohort> --preregistration aapl_confirmatory --revision 3 --preregistration-ref aapl_confirmatory-r3-00fd83d9cd39`.

## Interno, fora do texto do TCC

### Registro de hashes da evidência anterior

| campo | valor |
|---|---|
| resumo | Hashes dos arquivos da evidência de 2025 usados pela equivalência interna. |

Fonte: [`docs/reports/prior_evidence_registry.toml`](prior_evidence_registry.toml)

### Relatório da equivalência interna

| campo | valor |
|---|---|
| resumo | Tabela de equivalência entre a pipeline nova e a evidência anterior (8.2 parte (ii)). |

Fonte: [`docs/reports/equivalence_audit.md`](equivalence_audit.md)

### ADR 8.2.0003: andaime da evidência anterior em tests/

| campo | valor |
|---|---|
| resumo | Andaime da equivalência em tests/equivalence/, com registro de hashes e teste opt-in. |

Fonte: [`docs/adr/8_2_0003-prior-evidence-scaffold-in-tests-with-hash-registry-and-opt-in-test.md`](../adr/8_2_0003-prior-evidence-scaffold-in-tests-with-hash-registry-and-opt-in-test.md)

### Decisão humana B3 (ADR 8.2.0004): tolerância do A1 pela precisão float32 efetiva

| campo | valor |
|---|---|
| resumo | Emenda do A1: meio ulp de float32 com pré-condição, decidida pelo humano. |

Fonte: [`docs/adr/8_2_0004-a1-tolerance-by-effective-float32-storage-precision.md`](../adr/8_2_0004-a1-tolerance-by-effective-float32-storage-precision.md)

### [deviation] B3: emenda do A1

| campo | valor |
|---|---|
| resumo | Aplicação da emenda B3 (meio ulp de float32 com pré-condição). |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-b3--emenda-do-a1-meio-ulp-de-float32-com-pré-condição-adr-820004--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-b3--emenda-do-a1-meio-ulp-de-float32-com-pré-condição-adr-820004--claude-executor-das-etapas)

### [deviation] B3 refinada

| campo | valor |
|---|---|
| resumo | Critério float32 exato, fail-closed e rótulo propagado. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-b3-refinada--critério-float32-exato-fail-closed-e-rótulo-propagado--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-b3-refinada--critério-float32-exato-fail-closed-e-rótulo-propagado--claude-executor-das-etapas)

### [finding] precisão float32 do alvo anterior (D-M6)

| campo | valor |
|---|---|
| resumo | A premissa de D-M6 não vale para os valores: o alvo anterior tem precisão efetiva float32 num double; com o critério D13 a comparação de modelo não rodou na primeira E4. Resolvido pela emenda B3. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--measurement-e4--tabela-de-equivalência-e-diagnóstico-d13-do-a1--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--measurement-e4--tabela-de-equivalência-e-diagnóstico-d13-do-a1--claude-executor-das-etapas)

### [finding] PICP 80 % do candidato: lado do nominal divergente

| campo | valor |
|---|---|
| resumo | Na E4 refeita com B3, o lado do nominal do PICP 80 % do candidato diverge do anterior nos dois horizontes (not_explained): divergência de modelo, não de código nem de alvo; não bloqueia a 8.2 nem o veredito da 8.1. Sem resolução posterior. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-24--measurement-e4-refeita-com-b3--tabela-de-equivalência--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-24--measurement-e4-refeita-com-b3--tabela-de-equivalência--claude-executor-das-etapas)

### Erratas F2–F5 da auditoria da 8.2

| campo | valor |
|---|---|
| resumo | F2 (ADR 8.2.0004: nenhum número de modelo do anterior visto ou reportado; corrigido em aad29ebc), F3 (log do make check extra não preservado), F4 (T∩ de h=7 igual ao de h=1), F5 (type: ignore do andaime fora do escopo do mypy; anotar fica para quem tocar o andaime). |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-24--finding-auditoria-da-stage--erratas-f2f5--claude-auditoria-da-stage`](../stages/8.2-equivalence-audit/technical.md#2026-10-24--finding-auditoria-da-stage--erratas-f2f5--claude-auditoria-da-stage)

### [finding] E4 do andaime: FAIL_AUDIT_TABLE por OfficialSilverMismatchError

| campo | valor |
|---|---|
| resumo | O esperado do andaime tomava todas as unidades fact_oos_predictions do silver_content, inclusive as 600 da ablação que ele não lia; nenhum valor do anterior foi visto. Resolvido pelo [deviation] E4. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--finding-e4-passo-1--fail_audit_table-por-officialsilvermismatcherror-do-andaime--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--finding-e4-passo-1--fail_audit_table-por-officialsilvermismatcherror-do-andaime--claude-executor-das-etapas)

### [deviation] E4: check_silver_units só com as unidades do cohort

| campo | valor |
|---|---|
| resumo | Correção 0e59b9f9: o esperado leva só dim_run do cohort e as unidades dos runs do cohort. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-e4--check_silver_units-só-com-as-unidades-do-cohort--claude-executor-das-etapas`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-e4--check_silver_units-só-com-as-unidades-do-cohort--claude-executor-das-etapas)

### [deviation] PRIOR_CANDIDATE_LABELS no comparison_set.py

| campo | valor |
|---|---|
| resumo | Rótulos do candidato da evidência anterior no conjunto de comparação do andaime (Task 11 da 8.2). |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-task-11-prior_candidate_labels-no-comparison_setpy--claude-executor`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-task-11-prior_candidate_labels-no-comparison_setpy--claude-executor)

### [deviation] Checkpoint C final (bloco 4), CC4-1..CC4-8 no andaime

| campo | valor |
|---|---|
| resumo | Correções do Checkpoint C final aplicadas ao andaime da equivalência. |

Fonte: [`docs/stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-checkpoint-c-final-bloco-4-cc4-1cc4-8-no-andaime--claude-executor`](../stages/8.2-equivalence-audit/technical.md#2026-10-23--deviation-checkpoint-c-final-bloco-4-cc4-1cc4-8-no-andaime--claude-executor)

### Limite da §5 do reproduction_audit.md

| campo | valor |
|---|---|
| resumo | A §5 (Ambiente) do relatório de reprodução lista o blob de tests/equivalence/prior_evidence.py (l. 106); por isso o dossiê citável aponta só as §1–§4. O artefato da 8.2 não é editado. |

Fonte: [`docs/reports/reproduction_audit.md#5-ambiente`](reproduction_audit.md#5-ambiente)
