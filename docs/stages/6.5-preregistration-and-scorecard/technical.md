---
title: Technical — Stage 6.5 — Pré-registro imutável e scorecard confirmatório (hash exato, âncora, leitura do gold, regra H1 → H2 mecânica)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit, salvo a do roadmap e a de congelamento), TDD inside-out no BC evaluation — PreregistrationHash em shared, VO Preregistration com catálogo de regras, poder exato e VOs de evidência, H1Gate e ConfirmatoryScorecard, dono do schema do gold e montagem única da geração lida, ports PreregistrationSource e GoldGenerationReader com fake, real e contrato, derivação do comando e conferência do gold, perfil, use case BuildConfirmatoryScorecard, wiring, e2e sintético, roadmap e o congelamento e a âncora do r0 (bloqueada pela declaração de cegamento)
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite, tokens de teste e blocos de verificação Container/Host
keywords: [technical, plano de execução, preregistration-and-scorecard, evaluation, preregistration, preregistration-hash, rule-catalog, h1-gate, h1-gate-power, confirmatory-scorecard, scorecard-evidence, gold-schema, gold-generation, gold-generation-reader, preregistration-source, toml, refresh-command-from, profile, academic-decision-ready, anchor, blinding, port-coverage]
status: done
created_at: 2026-09-30
updated_at: 2026-09-30
stage_id: 6.5-preregistration-and-scorecard
stage_title: Pré-registro imutável e scorecard confirmatório
step_id: 6
step_title: Núcleo estatístico confirmatório
depends_on: [6.4-gold-builders-and-quality-gates, 5.5-confirmatory-retrain]
concept_ref: ./concept.md
issue_id: 127
branch: feat/127-6-5-preregistration-and-scorecard
tasks_count: 13
---

# Technical — Stage 6.5 — Pré-registro imutável e scorecard confirmatório

> **Como usar (para code assistant):** ler §1, executar as Tasks em ordem (§2 e
> §4), 1 Task = 1 commit (as Tasks 12 e 13 têm dois commits cada, declarados), não avançar
> sem verificação verde; ao fim validar §3 e registrar §7. Commits seguem
> [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
> `<type>(<escopo>): <descrição> [6.5/task-NN]`, `Refs #127`, subject
> ≤ 100 caracteres (hook `commit-msg`), mensagem UTF-8 sem BOM por
> `git commit -F`. Escopo `evaluation`, salvo a Task 01 (`shared`) e o 1º
> commit da Task 12 (`roadmap`).
>
> **Cegamento (I15, inegociável).** Nenhuma Task, bloco de verificação, e2e ou
> medição desta Stage lê `data/cohorts/**`, roda o refresh sobre o cohort
> `aapl_confirmatory-r0-665f45d9169a` ou calcula qualquer métrica sobre ele
> (gold `COMPLETED`, scorecard, calibração, DM, MCS, taxa de degeneração). Todo
> teste usa silver/gold sintético. A corrida real é da 8.1. A Task 13
> (congelamento e âncora) não roda refresh nenhum.
>
> **Task 13 bloqueada por decisão humana (P).** O conteúdo — ou a ausência — do
> `blinding_statement` do r0 (concept §13, ADR 6.5.0010 P1) é **entrada** da
> Task 13; ela não roda antes da resposta. As **ações externas** da Task 13
> (push da tag e comentário na #127) exigem, além da decisão humana, um
> **go-ahead explícito da sessão mestra**. Todo o resto (Tasks 01–12) é
> executável agora.
>
> Ao encontrar algo não previsto em §1–§6 ou no `concept.md`: **pausar**,
> resolver pelo §2 de [`PROMPT-step-single-session.md`](../../PROMPT-step-single-session.md)
> (docs → ADR; E/C → `evidence-resolution` + ADR 6.5.0011+; P → sobe à sessão
> mestra) e registrar em §7. Gap que muda contrato, fronteira ou critério do
> concept não é resolvido aqui: sobe. Nunca propagar silenciosamente.

## 1. Contexto e estratégia de execução

### Resumo

Quarta fatia do BC `evaluation` e a que fecha o Step 6: o **pré-registro** do
estudo AAPL vira um arquivo TOML por revisão, lido por um port de saída
(`PreregistrationSource`, adapter `tomllib`) e transformado no VO
`Preregistration` (números coagidos ao tipo declarado, regras nomeadas por
identificadores de um catálogo que o domínio implementa), hasheado sem
arredondamento pelo VO novo `PreregistrationHash` de `shared`, com
`preregistration_ref = "<name>-r<rev>-<hash12>"`. Do plano sai, por uma função
única, o `RefreshGoldCommand` inteiro (`refresh_command_from`). O gold da 6.4
passa a ter dono de schema (`gold_schema.py`) e montagem única da geração lida
(`GoldGeneration.from_stored`), lido por um port do consumidor
(`GoldGenerationReader`, real no `ParquetGoldStore`). O use case
`BuildConfirmatoryScorecard` valida cadeia, hash e âncora antes de ler o gold,
confere o gold contra o plano (conjuntos primeiro, linhas faltando depois),
monta a evidência por horizonte e aplica no domínio o gate H1 sobre contagens
médias entre seeds (`H1Gate`, com poder exato por `H1GatePower`) e a árvore H2
(`ConfirmatoryScorecard`), separa o perfil do veredito e calcula
`academic_decision_ready` só dos gates de validade. Fecham a Stage o wiring, um
e2e sobre silver sintético, a redação do roadmap e — depois da decisão humana —
o congelamento e a âncora do pré-registro AAPL r0.

Todas as decisões vêm do concept **por referência** — nenhuma é re-derivada:
D1 ([ADR 6.5.0001](../../adr/6_5_0001-preregistration-canonical-toml-hashed-value-object.md)),
D2 ([ADR 6.5.0002](../../adr/6_5_0002-amendment-as-new-revision-file.md)),
D3 ([ADR 6.5.0003](../../adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md)),
D4 ([ADR 6.5.0004](../../adr/6_5_0004-judging-values-in-preregistration-cohort-by-reference.md)),
D5 ([ADR 6.5.0005](../../adr/6_5_0005-gold-generation-reader-port-manifest-first.md)),
D6 ([ADR 6.5.0006](../../adr/6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md)),
D7 ([ADR 6.5.0007](../../adr/6_5_0007-verdict-logical-form-and-decision-readiness.md)),
D8 ([ADR 6.5.0008](../../adr/6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md)),
D9 ([ADR 6.5.0009](../../adr/6_5_0009-preregistered-conventional-values.md),
[ADR 6.5.0010](../../adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md)),
D10 (roadmap). Nenhum ADR novo nesta Fase 3B: as decisões de detalhe abaixo
ficam abaixo do limiar de concept (não mudam contrato, fronteira nem critério)
e viram `[decision]` em §7 ao executar.

### Premissas verificadas no código (HEAD `29c9184`)

| Premissa | Onde (arquivo:linha) | Consequência no plano |
|---|---|---|
| O hasher arredonda floats a 10 casas | `shared/adapters/out/hashing/canonical_json_hasher.py:33` (`_FLOAT_PRECISION = 10`), `:54` (`round`) | `PreregistrationHash` troca todo `float` por `f"float:{x!r}"` antes do hasher (Task 01); `str` atravessa o `_canonicalize` intacto (`:57-60`) |
| Só VOs de `shared/domain/value_objects/` chamam `hash_mapping` | `scripts/check_layout.py:96-99`, `:286` (regra 6) | o hash do plano mora em `shared` (Task 01); o use case chama o VO, nunca o hasher |
| O precedente de identidade por VO de shared | `shared/domain/value_objects/cohort_hash.py:26-38` | `PreregistrationHash` com a mesma forma (`compute(*, hasher, payload)`) |
| Chaves do gold privadas em cada builder | `gold_builders/calibration_table.py:31`, `dm_results.py:19`, `mcs_results.py:27`, `metrics_by_run.py:31`, `quality_checks.py:20` (`_KEY`); nome `f"gold_{self.name}"` em cada `build` | `gold_schema.py` vira o dono; os `_KEY` somem (Task 05) |
| O manifesto só serializa (não tem inversa) | `application/dtos/refresh_gold.py:142` (`RefreshParameters.as_mapping`), `:362` (`GoldManifest.as_mapping`) | `from_mapping` das duas, ao lado (Task 05) |
| Coerência de geração com dono único | `refresh_gold.py:388` (`check_generation`) | `GoldGeneration.from_stored` reusa-o (Task 05) |
| Layout e nome do manifesto com dono no adapter | `adapters/out/duckdb/parquet_gold_store.py:51` (`MANIFEST_NAME`), `:72-85` (`partition_root`, `current_dir`) | `read_generation` no mesmo módulo (Task 07) |
| Port-coverage reconhece fake por nome e real por citação | `scripts/check_port_coverage.py:160-176` (`fake_names`, `real_adapter_classes`), `:277-327` (`inventory`) | fakes `InMemoryPreregistrationSource`/`InMemoryGoldGenerationReader`; docstrings dos reais citam o port; contratos `[fake, real]` (Tasks 06, 07) |
| Piso do inventário de ports | `tests/architecture/test_port_coverage_gate.py:279` (`len(ports) >= 26`) | sobe para 28 na Task 07 |
| Unit do `evaluation` não importa adapter nem lê arquivo | `tests/architecture/test_unit_evaluation_purity.py:18-20` (`.adapters.`, `open`/`read_text`/`read_bytes`/`load`) | testes unitários usam dublê de hasher stdlib; leitura de arquivo só em contrato/integração |
| Validadores públicos donos | `count_input_validation.py:47` (`validate_rate`), `inference_input_validation.py:34` (`validate_alpha`), `value_objects/_tolerance.py:20` (`validate_tolerance`), `christoffersen_test.py:111` (`validate_min_violations`), `model_confidence_set.py:62` (`validate_mcs_reps`), `bootstrap_indices.py:59` (`validate_bootstrap_parameters`), `value_objects/_horizon.py:16,25` | o `Preregistration` só chama os donos (Task 02) |
| Validador de `draws`/`seed` do Monte Carlo é privado | `christoffersen_test.py:631` (`_validate_draws_and_seed`) | vira público `validate_draws_and_seed` (Task 02) |
| Estatística e regra de bloco do MCS sem nome público | `model_confidence_set.py:58` (`_STATISTIC = "R"`), `:195` (`max(series.horizon, math.ceil(...))` dentro de `block_length`) | `MCS_STATISTIC` público e `block_length_rule(*, horizon, max_estimate)` como dono da regra; `block_length` delega (Task 02) |
| Kernels de contagem aceitam médias reais | `wilson_band.py:42` (`wilson_interval(count: float, n: float, …)`), `:165` (`WilsonBand.evaluate`); `christoffersen_test.py:459` (`lr_uc_three_state`); `chi_square.py:68` (`chi_square_sf`) | `H1Gate` só os chama (Task 04) |
| Taxa nominal da cauda tem dono | `value_objects/hit_sequence.py:66` (`violation_rate_for`) | a nominal da cauda superior é `violation_rate_for(UPPER_TAIL, (τ_u,))`, nunca `1 − τ` escrito de novo (Tasks 03, 04) |
| Só existe a CDF da t de Student | `student_t.py:79` (`student_t_cdf`) | `student_t_quantile` por bisseção sobre a CDF (Task 09, junto do seu único consumidor, o IC do efeito do DM) |
| Estatística do DM com HLN | `diebold_mariano.py:195` (`statistic = _hln_factor(...) * mean / sqrt(variance)`), p unilateral `student_t_cdf(statistic, T − 1)` | IC do efeito = d̄ ± t_{T−1,0,975}·(d̄/estatística) usa exatamente essa escala (Task 09) |
| Nomes dos checks exigidos | `quality_checks/degeneracy_check.py:24`, `alignment_check.py:24`, `statistical_preconditions_check.py:48`; severidade/outcome em `value_objects/quality_check_result.py:31-50` | a prontidão lê esses nomes do domínio (Task 10) |
| Nomes de modelo dos escritores | `modeling/application/use_cases/train_tft.py:121` (`tft_quantile`), `train_gbm_quantile.py:124` (`gbm_quantile`), `modeling/domain/value_objects/baseline_spec.py:88-90` (`baseline_<family>`) | só o teste de consistência (Task 13) os importa |
| Cohort r0 | `config/cohorts/aapl_confirmatory.toml` (`asset_id`, `horizons`, `quantile_levels`, `seeds`, `dataset_fingerprint`, `[gbm_params] seed = 0`, cinco `[[baselines]]`); loader `modeling/adapters/in/cli/cohort_file.py:88` (`parse`), `modeling/application/dtos/cohort_spec.py:184,206` (`hash_payload`, `cohort_id`) | teste de consistência da Task 13; hash completo `665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1` (technical 5.5 §7); âncora do cohort #102 `2026-09-28T20:27:09Z` (runbook `confirmatory-cohort-aapl.md:190`) |
| Raiz do repo nas settings | `shared/infrastructure/config/settings.py:92` (`repo_root`) | `TomlPreregistrationSource(root=cfg.repo_root / "config" / "preregistration")` (Task 11) |
| Wiring do gold | `composition_root.py:791-804` (`RefreshGold(... gold_store=ParquetGoldStore(cfg.data_root) ...)`) | uma instância `ParquetGoldStore` compartilhada pelo refresh e pelo scorecard (Task 11) |

### Estratégia

**TDD inside-out** (skill `task-ordering-hex`): identidade em `shared` (Task 01)
→ VO do plano + donos públicos da 6.2/6.3 que ele consome (Task 02) → poder
exato e VOs de evidência (Task 03) → serviços `H1Gate` e
`ConfirmatoryScorecard` (Task 04) → dono do schema e montagem da geração lida
(Task 05) → port `PreregistrationSource` com fake, real e contrato (Task 06) →
port `GoldGenerationReader` com fake, real e contrato (Task 07) → derivação do
comando e mapeador linhas → evidência com a conferência do gold (Task 08) →
perfil (Task 09) → use case (Task 10) → wiring + e2e (Task 11) → roadmap
(Task 12) → congelamento e âncora do r0 (Task 13, bloqueada). Cada commit deixa
o build verde.

**Exceções de ordem/contagem declaradas (PIPELINE §4.3; skill `task-ordering-hex`):**

- **13 Tasks** (estimativa do concept: 12; teto de saúde 12, alarme em 14 —
  CONVENTIONS §6). A 13ª vem de **um commit = um escopo**: o
  `PreregistrationHash` e o LAYOUT §7 são de `shared` e ganham a Task 01; o
  resto do item (1) do concept vira a Task 02.
- **Tasks com mais de 5 arquivos** (PIPELINE §4.3 "tipicamente"):
  - **02 (8)** — o VO + dois testes + a fábrica de payload de teste; e os
    donos públicos que ele consome (`MCS_STATISTIC`, `validate_draws_and_seed`;
    `block_length_rule`, no mesmo arquivo da 6.2, só é consumido na Task 08)
    em dois arquivos da 6.2/6.3, com os seus
    testes só ganhando casos. **Motivo real:** uma Task própria para os donos
    públicos levaria a 14 Tasks, o alarme do CONVENTIONS §6; o custo aceito é um
    commit com dois módulos da 6.2/6.3 a mais, cobertos pelo diff "só `+`" dos
    seus testes. `block_length_rule` fica sem consumidor da Task 02 à 08 (o VO
    não o usa) — aceito pelo mesmo motivo.
  - **05 (9)** — `gold_schema.py` + os cinco builders (troca mecânica de
    import, ADR 6.5.0005 Negative) + os dois testes existentes que ganham
    casos: o schema nasce junto dos seus importadores, senão o `_KEY` viraria
    segunda escrita por um commit. As inversas, o `from_stored` e os dois erros
    do gold entram no **mesmo** commit **por escolha** (poderiam ser Task
    própria; ficam juntos porque o `from_stored` monta cada tabela com a chave
    do schema recém-nascido e uma Task a mais levaria a 14).
  - **09 (7)** — o perfil (helper + teste + DTO) com os seus dois kernels
    (`dm_effect_interval` e `student_t_quantile`) e os testes existentes que
    ganham casos: cada kernel nasce junto do seu **único** consumidor
    (Checkpoint B r1, A11), em vez de ficar seis commits sem uso.
- **Port + real no mesmo commit (06, 07):** port, fake, adapter e contrato
  numa Task só (5 arquivos cada), **sem** janela de baseline do
  `port-coverage` (precedente 6.4 Task 14; o concept veda entrada nova no
  baseline). Isso não "mistura criação de port com adapter" no sentido do
  PIPELINE §4.3: a regra existe para a janela de baseline de um commit (ADR
  6.1.0005), que aqui é zero.
- **Task 13 com dois commits** (mesma tag `[6.5/task-13]`, precedente 5.5
  Task 34): o arquivo do plano precisa estar commitado **antes** da tag e do
  comentário, e o registro da âncora só existe **depois** do comentário (ADR
  6.5.0003 item 2: fora do hash por construção). **Task 12 com dois commits**
  (um escopo por commit): o roadmap (`docs(roadmap)`) e a nota de emenda datada
  no topo do ADR 6.5.0009 (`docs(evaluation)`, T-F11 — ver §7 `[finding]`).
- **Gates de arquitetura tocados:** Task 01 (`check_layout` regra 6 exercida
  pelo VO novo; LAYOUT §7), Task 07 (`test_port_coverage_gate.py`: piso
  26 → 28 e caso de resolução dos dois ports novos). Essas rodam T3 ou
  `check-block` (tabela de gates abaixo).

**Decisões de detalhe planejadas (abaixo do limiar de concept — não mudam
contrato, fronteira nem critério; viram `[decision]` em §7 ao executar):**

- **Direção VO → serviço de domínio.** O `Preregistration`
  (`value_objects/`) chama validadores que moram em `services/`
  (`validate_rate`, `validate_alpha`, `validate_min_violations`,
  `validate_mcs_reps`, `validate_draws_and_seed`) — é o que o ADR 6.5.0001
  item 2 manda ("the public owner validators"). É aresta nova dentro do domínio
  do slice; não há ciclo (nenhum desses módulos importa o do plano) e o
  `.importlinter` não tem contrato de camadas internas ao domínio. Os serviços
  novos (`h1_gate`, `h1_gate_power`, `confirmatory_scorecard`) importam o VO
  (direção usual). **Reversão deliberada de uma postura registrada:** o
  technical 6.4 (Task 03, `forecast_record.py`: "o VO não importa
  `validate_rate` de `services/`, direção VO → serviço que o slice não tem")
  evitou essa direção; aqui ela é adotada sob o ADR 6.5.0001 item 2 (validar
  pelos donos públicos, sem segunda escrita) e registrada como `[decision]` em
  §7 ao executar a Task 02 (um ciclo de import falharia já na coleta dos
  testes; nenhum teste dedicado).
- **Catálogo de regras no módulo do VO.** `RULE_CATALOG: Final[Mapping[str,
  str]]` em `preregistration.py`: chave pontuada do TOML (`"dm.kernel_lag"`,
  `"h1_gate.form"`, …) → o **único** identificador implementado (ADR 6.5.0004
  item 2). `MCS_STATISTIC` vem de `model_confidence_set` (dono) — não é
  reescrito. `from_mapping` recusa identificador diferente com a mensagem
  `"rules.<chave> must be <implementado> (the only rule the domain implements),
  got <valor>"`. O `ConfirmatoryScorecard.decide` (que recebe o plano
  inteiro) confere, na entrada, que os identificadores das regras que ele e o
  `H1Gate` aplicam são os do catálogo (defesa: o VO já garante; a assinatura
  `H1Gate.evaluate(spec, evidence)` do concept fica intacta). Idem `PROFILE_CATALOG` (os perfis
  declaráveis, ADR 6.5.0008 item 1) e `REALIZED_SOURCES`
  (`"training_grid_target_return"`).
- **Dublê de hasher nos testes unitários do `evaluation`.** O gate de pureza
  proíbe importar `CanonicalJsonHasher` em `tests/unit/features/evaluation/**`
  e o `Hasher` não tem fake por desenho (#70). Um dublê **que recusa float**
  (`FloatRefusingHasher`: percorre o payload, ergue `AssertionError` se achar
  `float`, devolve o sha256 de `json.dumps(..., sort_keys=True)`) é definido
  **uma vez**, em `_preregistration_payload.py` — **fora** de `tests/fakes/` e
  **sem** prefixo `Fake`/`InMemory` (senão o `check_port_coverage` o tomaria
  por fake do `Hasher`, que está no baseline por desenho, e acusaria "baseline
  morto"). Prova que o `PreregistrationHash` codifica todo float antes de
  delegar. O comportamento contra o hasher real (arredondamento) é provado em
  `tests/unit/shared/domain/value_objects/test_preregistration_hash.py`
  (precedente `test_cohort_hash.py`, fora do gate de pureza do `evaluation`).
- **Fábrica de payload de teste única.**
  `tests/unit/features/evaluation/_preregistration_payload.py` (módulo privado,
  sem `test_`) expõe `valid_payload() -> dict[str, object]` (cópia profunda de
  um dict literal: plano sintético completo, valores do r0 salvo `name =
  "test_plan"` e cohort/fingerprint sintéticos); `to_toml(payload) -> str` —
  **escritor TOML só de teste** (stdlib não tem escritor: `tomllib` só lê;
  Checkpoint B r1, A3), que cobre exatamente o que o esquema usa (`str` com
  escape de `"`/`\`, `int`, `float` por `repr`, `bool`, `datetime` — com fuso
  vira *offset date-time*, sem fuso vira *local date-time* (para o caso
  negativo da âncora) —, listas de escalares, tabelas e *arrays of tables*;
  lista de tabelas **vazia** vira `key = []`; `str` com quebra de linha ou
  caractere de controle sai escapado (`\n`, `\t`, `\r`, `\uXXXX`), nunca
  literal),
  com a regra "chaves escalares antes das
  tabelas"; `PAYLOAD_TOML = to_toml(valid_payload())`; `leaf_paths(payload)`
  enumera **toda** folha com caminho indexado (`"dm.alpha"`, `"horizons[1]"`,
  `"h1_gate.power_scenarios[0].lower_rate"`); `with_leaf(payload, path,
  value)` devolve cópia profunda com a folha trocada; `FloatRefusingHasher`
  (acima). O teste `payload_toml_writer_round_trip` prova `tomllib.loads(
  to_toml(p)) == p` para o plano base, para um r1 com emenda, para um plano
  com `blinding_statement` contendo aspas, barra invertida, `\n` e um
  caractere de controle, e para um payload com lista de tabelas vazia (o gate de pureza
  proíbe `load`, não `loads`). O contrato (Task 06) e o e2e (Task 11) gravam em
  disco o texto de `to_toml` dos planos que montam — nenhum TOML escrito à
  mão.
- **Registro do source no módulo do port.** `PreregistrationRecord(payload:
  Mapping[str, object], anchor: PreregistrationAnchor | None)` e
  `PreregistrationAnchor(tag, commit, comment_url, anchored_at)` (frozen;
  `anchored_at` `datetime` com fuso, textos não vazios, `tag` começando por
  `"preregistration/"`) e `PreregistrationNotFoundError(ApplicationError)`
  moram em `ports/out/preregistration_source.py` — são a forma do retorno do
  port (concept §4 os descreve junto do port). `anchored_at` no arquivo
  `.anchor.toml` é um *offset date-time* TOML nativo (`anchored_at =
  2026-10-01T12:00:00Z`); data local sem fuso → `ValueError`.
- **Os cinco erros do scorecard no módulo de DTOs** (`dtos/confirmatory_scorecard.py`,
  criado na Task 08): `PreregistrationHashMismatchError`,
  `PreregistrationChainError`, `PreregistrationNotAnchoredError`,
  `PreregistrationMismatchError` (com atributo `field`) e `GoldNotReadyError`
  (com `failed_checks`), todos `ApplicationError`. O concept §4 os põe "no
  módulo do use case"; o mapeador (`use_cases/scorecard_evidence.py`) ergue o
  de C8 e é importado pelo use case — defini-los no use case criaria ciclo.
  Mesma forma dos erros do gold, definidos no módulo de DTOs (ADR 6.5.0005 item
  5). **Sem reexportação** pelo use case (decisão da sessão mestra no
  Checkpoint B r1): o import é do módulo de DTOs. Registrado como
  `[deviation]` (lugar do erro ≠ texto do concept) em §7 ao executar a
  Task 08.
- **Ordem das tuplas derivadas.** `refresh_command_from` monta
  `band_levels = tuple(sorted({gate_band_level, profile_band_level}))`
  (`(0.95, 0.975)`), `dm_variance_estimators = (primary,) + sensitivity`,
  `mcs_schemes = (primary,) + sensitivity`, `horizons = prereg.horizons`,
  `window_deficits = dict(prereg.window_deficits)`. A conferência do manifesto
  compara `as_mapping()` do comando derivado com o do manifesto lido (mesma
  função, mesma ordem).
- **Evidência de T comum.** T do horizonte = `n_points` das linhas
  `gold_dm_results` do horizonte (a amostra comum em que o DM rodou); linhas do
  mesmo horizonte com `n_points` diferentes → `GoldGenerationCorruptError`.
- **Linhas do gate pelo nível da banda.** A calibração tem uma linha por nível
  de banda (0,95 e 0,975, com as mesmas contagens por construção da 6.4); o
  mapeador lê as caudas do gate **só** nas linhas com `band_level ==
  gate_band_level` (e as do perfil a 95 % nas de `profile_band_level`), nunca
  "qualquer uma" — um teste com contagens diferentes por nível prova a
  seleção (Checkpoint B r1, T-F7).
- **O que o gold `COMPLETED` não pode ter** (C6, corrupção, não prontidão):
  linha `ERROR` + `FAIL` em `gold_quality_checks` (o `GoldInputs` da 6.4 nunca
  grava isso num `COMPLETED`; `refresh_gold.py` `GoldInputs.__post_init__`) e
  `max_block_estimate` `None` numa linha do MCS → `GoldGenerationCorruptError`
  no mapeador. Por isso a prontidão **não** tem razão "check exigido falhou":
  um `ERROR`+`FAIL` só existe em gold `BLOCKED` (→ `GoldNotReadyError`) ou
  corrompido (Checkpoint B r1, T-F4).
- **O `preregistration_ref` mascara os demais campos do manifesto.** Qualquer
  folha do plano muda o hash e portanto o `preregistration_ref`, que a
  conferência do manifesto compara **antes** de `parameters`, horizontes,
  déficits e fingerprint. Um gold refrescado com outro plano erra sempre com
  `field == "preregistration_ref"`; os campos seguintes só são alcançáveis por
  manifesto adulterado (testes do mapeador, Task 08). O e2e (Task 11) prova as
  duas situações reais: plano alterado → `preregistration_ref`; e o **mesmo**
  plano sobre um silver com uma seed a mais → `seeds` (Checkpoint B r1, T-F1).
- **Veredito sempre com os fatos.** `HorizonVerdict.beats_naive`,
  `beats_or_ties_strong` e `in_mcs` são preenchidos mesmo com H1 reprovado (são
  fatos do gold); `h2 = NOT_APPLICABLE` e `primary_winner = None` quando H1
  reprova. O concept pede "um teste por desfecho" e "H1 reprovado com DM todo
  rejeitado dá `NOT_APPLICABLE` e sem vencedor" — os dois valem.
- **Poder sem O(n²).** A aceitação de uma cauda é "a banda de Wilson 97,5 %
  contém a nominal"; o conjunto de contagens aceitas `A` é calculado varrendo
  c = 0..n com `WilsonBand.evaluate` (dono; n + 1 chamadas). P(passar) =
  Σ_{l∈A} P(L = l) · Σ_{u∈A, u ≤ n−l} P(U = u | L = l), U | L = l ~
  Binomial(n − l, p_u/(1 − p_l)), pmf por `math.lgamma` em escala log. Só as
  contagens aceitas entram (≈ 50 × 50 termos em n ≈ 1 500). Um teste compara
  com a soma dupla bruta em n pequeno.
- **Quantil da t.** `student_t_quantile(p, df)` por bisseção sobre
  `student_t_cdf` (dono) em [−10⁶, 10⁶], até `hi − lo ≤ 1e-12·max(1, |x|)` ou
  200 iterações; `p` em (0, 1), `df ≥ 1`; sem aproximação nova.
- **IC do efeito do DM.** `dm_effect_interval(*, mean_differential, statistic,
  n_points, level) -> tuple[float, float] | None` em `diebold_mariano.py`
  (dono do DM): `None` quando `statistic == 0` (ADR 6.5.0008 item 2); senão
  d̄ ± t_{T−1,(1+level)/2} · |d̄/statistic|.
- **Descritores do perfil sem regra nova.** Agrupar as linhas de
  `gold_metrics_by_run` por (horizonte, modelo, amostra, métrica, níveis) e
  reportar média, mínimo e máximo entre seeds (`SeedSpread.of(values)` em
  `value_objects/scorecard_evidence.py`, a regra de agregação `mean_...` com um
  dono); com S = 1, média = mínimo = máximo. Calibração a 95 %: por série
  (horizonte, modelo, amostra, kind, níveis, com/sem degeneradas, DGT), médias
  de `n_violations`/`n_observed` e a fração de seeds com
  `wilson_contains_nominal`; LR_ind/LR_cc: fração de seeds com `p_ind`/`p_cc`
  < `sensitivity_alpha` (status `independence_status` diferente de aplicável →
  fora da fração, contado à parte). Nada recomputado (I8).
- **Hasher no use case.** `BuildConfirmatoryScorecard` recebe o `Hasher` e
  calcula o hash de cada revisão por `PreregistrationHash.compute(hasher=...,
  payload=prereg.as_payload())`; o teste unitário usa o dublê que recusa float;
  o e2e, o `CanonicalJsonHasher` real.
- **Tabela vazia e coluna toda nula na leitura real.** `read_generation` lê cada
  tabela listada no manifesto com `pyarrow.parquet.read_table(path,
  partitioning=None).to_pylist()`; tabela com 0 linhas no manifesto é passada
  como `[]` sem abrir o schema do arquivo (o arquivo ainda precisa existir —
  ausente é corrupção). Coluna toda `None` volta como `None` (tipo `null` do
  pyarrow); o tipo para consultas DuckDB ad hoc é da 8.3 (ADR 6.5.0005 item 4).
- **Gold lido por um dono de erro.** `GoldGeneration.from_stored` converte
  `ValueError` de `GoldManifest.from_mapping`, de `GoldTable` (ordem, colunas)
  e de `check_generation` em `GoldGenerationCorruptError` (com `from error`);
  tabela listada ausente em `rows_by_table` ou contagem divergente ergue
  diretamente. O `BLOCKED` volta normal (a recusa é do use case).

**Gate por Task (RUNBOOK §Gates em camadas, ADR 0.0.0055):** T1 =
`make check-task SLICE=evaluation` nas Tasks 02, 03, 04, 05, 06, 08, 09, 10 e
13; `make check-block` na Task 01 (`shared` + LAYOUT) e na 11 (composition
root); T3 = `make check` na Task 07 (`tests/architecture/`). Task 12 (docs,
dois commits): `make docs-check`. **Checkpoint C (T2, `make check-block`)** após as Tasks 04,
07 e 10; o bloco 4 após a 12 (antes da espera humana). T3 no gate de saída
(§3), depois da Task 13.

**Onde rodar — convenção dos blocos de verificação (vale para §2 e §3; regra
do Step):**

- Cada verificação vem rotulada **Container** ou **Host**. O host não tem o
  toolchain (`uv`/`make` só no container).
- **Container:** o bloco inteiro roda num **único** `bash -euo pipefail -c`,
  dentro de **um** `docker run`, com o venv da 6.5 (volume `ff-step62-venv`,
  que tem `arch`/`statsmodels` do lock atual do `develop`; se o lock mudar,
  `uv sync --inexact --extra dev` uma vez; nenhuma dependência nova nesta
  Stage):
  ```bash
  WT=feat-127-6-5-preregistration-and-scorecard
  MSYS_NO_PATHCONV=1 docker run --rm \
    -v "<raiz-das-worktrees>/$WT:/app" \
    -v "<raiz-do-repo>/.git:/main.git" \
    -v ff-step62-venv:/app/.venv \
    -e GIT_DIR=/main.git/worktrees/$WT -e GIT_WORK_TREE=/app \
    -w /app financial_forecasting-app:dev bash -euo pipefail -c "$(cat <<'EOF'
  git config --global --add safe.directory '*'
  # <linhas do bloco Container da Task>
  EOF
  )"
  ```
  (script por `-c`, não por stdin: um comando que lesse stdin consumiria o
  resto do script.) O bind mount é a worktree inteira em `/app`; nenhum bloco
  copia código por cima de `/app`.
- **Host:** Git Bash na raiz da worktree, o bloco como um só script
  `bash -euo pipefail` (scripts stdlib `python scripts/check_*.py`, greps de
  docs, `git`, `gh`).
- **Indentação:** os blocos dentro de itens de lista aparecem indentados no
  markdown; copiar **sem** a indentação comum (um heredoc `<<'PY'` exige o
  `PY` de fechamento na coluna 0). A validação da Fase 3B (`bash -n`) roda
  sobre os blocos com a indentação removida.
- **Negação:** `set -e` ignora o status de `! cmd`; toda asserção negativa é
  `if <cmd>; then echo "FAIL: <motivo>"; exit 1; fi`. Pipeline dentro de `if`
  nunca termina em `grep -q` (com `pipefail`, o SIGPIPE do produtor vira falso
  negativo): a saída vai para arquivo e o `grep` lê o arquivo. Arquivo
  produzido e lido no mesmo bloco; toda leitura começa por `test -s "$f"` (o
  `/tmp` não sobrevive entre `docker run --rm`; `grep` sobre arquivo ausente
  devolve 2).
- **Tokens de nome de teste:** cada Task lista, por arquivo, os tokens que os
  nomes dos seus testes **devem** conter. O §3 prova por coleta que cada token
  casa ≥ 1 teste do arquivo — casado contra o nome da função após o `::`,
  **sem** o id `[...]` de parametrização, substring sem distinção de caixa — e
  **recusa a lista** se um token repetir ou estiver contido em outro do mesmo
  arquivo (prova vácua). Os tokens são novos: nenhum casa um teste que já
  existe em `tests/` no HEAD `29c9184` (conferido na Fase 3B por script;
  Tasks 02, 03, 05, 07, 09 e 11 acrescentam a arquivos existentes).

### Pré-condições

- Stages `6.4` (PR #126) e `5.5` (PR #121) em `done` e mergeadas em `develop`:
  `GoldManifest`, `RefreshParameters`, `RefreshGoldCommand`, `GoldPartition`,
  `GoldTable`, `RefreshStatus`, `check_generation`, `ParquetGoldStore`,
  `InMemoryGoldStore`, `RefreshGold`, os cinco builders; `CohortHash`,
  `cohort_file.parse`, cohort r0 ancorado (#102).
- Concept desta Stage em `done` (commit `29c9184`, após o Checkpoint A rodada 1
  e as decisões P do humano); ADRs 6.5.0001–0010 em `accepted`.
- Working tree na branch `feat/127-6-5-preregistration-and-scorecard`; volume
  `ff-step62-venv` presente.
- Issue de seguimento dos perfis de séries novas aberta pela sessão mestra:
  **#129** (ADR 6.5.0008 item 3) — citada no roadmap pela Task 12.
- **Só para a Task 13:** a decisão humana sobre o `blinding_statement` do r0
  (texto ou ausência); `gh` autenticado no host (tag + comentário).
- Nenhuma dependência nova (`pyproject.toml`/`uv.lock` intocados): `tomllib` é
  stdlib; `pyarrow` já é dependência (4.2).

### Premissas técnicas

- Python 3.12; `uv`; `make check` = ruff + mypy strict + check_layout +
  lint-imports + fake-parity + port-coverage + docs-check + pytest com
  cobertura ≥ 90 %.
- Domínio só stdlib (`math`, `statistics.NormalDist` só em teste,
  `dataclasses`, `enum.StrEnum`, `types.MappingProxyType`) + domínio do slice +
  `shared/domain`. `tomllib` **só** em `evaluation/adapters/out/toml/`;
  `pyarrow` **só** em `evaluation/adapters/out/duckdb/` (A12).
- Gold e silver sintéticos em todos os testes; o e2e grava silver sintético
  pelo `ParquetAnalyticsRepository` real num `tmp_path` e roda o `RefreshGold`
  wirado (precedente 6.4 Task 12).
- Tolerâncias numéricas declaradas no módulo de teste (ADR 0.0.0021);
  igualdade de VO (`==`) quando o teste compara com a chamada direta ao dono.

### Esquema do arquivo de pré-registro (contrato do `from_mapping`)

Uma revisão por arquivo `config/preregistration/<name>-r<rev>.toml`; blocos =
VOs aninhados frozen de `preregistration.py`. **Toda chave é obrigatória**,
salvo `blinding_statement` (I14) e os três campos de emenda (proibidos em r0,
obrigatórios em r ≥ 1 — ADR 6.5.0002). Chave desconhecida → `ValueError`.
Coerção (ADR 6.5.0001 item 2): campos `float` aceitam `int`/`float`
não-`bool` e guardam `float`; campos `int` aceitam só `int` não-`bool` (float,
mesmo integral, → erro).

| Chave TOML | VO / campo | Tipo | Validador (dono) | Valor r0 (ADR) |
|---|---|---|---|---|
| `name` | `Preregistration.name` | str | `validate_path_identifier` | `"aapl_confirmatory"` |
| `revision` | `.revision` | int ≥ 0 | `int` não-`bool` ≥ 0 (checagem de forma do VO; não há dono "int ≥ 0" — #118) | `0` |
| `asset` | `.asset` | str | `validate_path_identifier` | `"AAPL"` (0004) |
| `horizons` | `.horizons` | tuple[int] estritamente crescente | `validate_horizon` por item | `[1, 7]` (0009) |
| `quantile_levels` | `.quantile_levels` | tuple[float] estritamente crescente | `validate_rate` por item | `[0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98]` |
| `candidate` | `.candidate` | str | não vazio | `"tft_quantile"` |
| `blinding_statement` (opcional) | `.blinding_statement` | str \| None | não vazio se presente | **pendente (P, Task 13)** |
| `amends`, `justification`, `blind_status` (r ≥ 1) | `.amendment: Amendment \| None` | str, str, `BlindStatus` | não vazios; `blinded`/`unblinded` | ausentes em r0 |
| `[cohort] cohort_id`, `cohort_hash` | `CohortReference` | str, str (64 hex) | `validate_path_identifier`; hex minúsculo de 64 | `aapl_confirmatory-r0-665f45d9169a`, `665f45d9…65b1` |
| `[realized] source`, `dataset_fingerprint` | `RealizedSource` | str (catálogo), str (64 hex) | `REALIZED_SOURCES`; hex de 64 | `training_grid_target_return`, `00e4406d…95bd` |
| `[[horizons_not_evaluated]] horizon`, `reason` | `tuple[HorizonNotEvaluated, ...]` | int, str | `validate_horizon`; disjunto de `horizons` | `30`, `"not in the cohort"` |
| `[comparators] naive`, `strong_statistical`, `ml` | `ComparatorTiers` | tuple[str] não vazias | disjuntas, sem o candidato, sem repetição | ADR 6.5.0007 item 1 |
| `[seeds] <modelo>` | `seeds: Mapping[str, SeedSpec]` | lista de int ≥ 0 distintos ou `"seedless"` | chaves = candidato ∪ comparadores | TFT `1..10`, GBM `[0]`, baselines `"seedless"` |
| `[window_deficits] <modelo>` | `window_deficits: Mapping[str, int]` | int ≥ 0 | chaves = candidato ∪ comparadores | `0` para todos |
| `[rules] primary_metric`, `secondary_roles`, `exclusions`, `seed_aggregation`, `success_criterion`; `[rules.dm] direction`, `kernel_lag`, `small_sample`, `negative_variance_fallback`; `[rules.mcs] statistic`, `block_rule`; `[rules.h1_gate] form`; `[rules.verdict] form` | `RuleIdentifiers` | str | `RULE_CATALOG` (um identificador por chave) | ADR 6.5.0004 item 2 |
| `[dm] alpha`, `primary_estimator`, `sensitivity_estimators` | `DmSpec` | float, `DmVarianceEstimator`, tuple | `validate_alpha`; valores do enum; sensibilidades sem o primário | `0.05`, `rectangular`, `["bartlett"]` |
| `[mcs] alpha`, `reps`, `seed`, `primary_scheme`, `sensitivity_schemes`, `block_sensitivities` | `McsSpec` | float, int, int, `BootstrapScheme`, tuple, tuple | `validate_alpha`; `validate_bootstrap_parameters` + `validate_mcs_reps`; enum; `{"h", "sqrt_T"}` | `0.10`, `1000`, `127`, `stationary`, `["moving_block"]`, `["h", "sqrt_T"]` |
| `[h1_gate] lower_level`, `upper_level`, `gate_band_level`, `profile_band_level`, `degeneracy_threshold`, `degeneracy_tolerance`, `sensitivity_alpha` | `H1GateSpec` | float | `validate_rate` (níveis ∈ grade, `lower < 0.5 < upper`); `validate_rate` (bandas, limiar); `validate_tolerance`; `validate_alpha` | `0.1`, `0.9`, `0.975`, `0.95`, `0.01`, `1e-12`, `0.05` |
| `[[h1_gate.power_scenarios]] label`, `role`, `lower_rate`, `upper_rate` | `tuple[TailDeviation, ...]` | str único, `ScenarioRole`, float, float | `validate_rate` cada; soma < 1; ≥ 1 primário | primário: `width_5pp_wide` (0.125/0.125), `width_5pp_narrow` (0.075/0.075), `location_0_2_sigma` (≈0.0692/0.1397); secundário: `width_3pp_wide` (0.115/0.115), `width_3pp_narrow` (0.085/0.085), `location_0_1_sigma` (≈0.0836/0.1187) — ADR 6.5.0010 P3; taxas de locação com o `repr` do `NormalDist` |
| `[backtests] min_violations`; `[backtests.monte_carlo] draws`, `seed` | `min_violations`, `MonteCarloSpec` | int, int, int | `validate_min_violations`; `validate_draws_and_seed` | `2`, `999`, `128` |
| `[profiles] declared` | `ProfileSpec` | tuple[str] | `PROFILE_CATALOG`, sem repetição | ADR 6.5.0008 item 1 (lista no espelho) |

`PROFILE_CATALOG` (identificadores declaráveis; ADR 6.5.0008 item 1):
`dm_bartlett`, `mcs_moving_block`, `mcs_block_h`, `mcs_block_sqrt_t`,
`gate_common_sample`, `gate_lr_uc_three_state`, `gate_dgt`,
`band_95_isolated`, `without_gaps_variant`, `comparators_calibration`,
`dm_effect_ci`, `dm_fallback_applied`, `tier_outcomes`,
`lowest_mean_pinball`, `metrics_descriptors`, `christoffersen_monte_carlo_h1`,
`dm_per_fold`, `dm_per_seed`, `dm_per_tau`, `dm_differential_stationarity`,
`partial_degeneracy_per_pair`, `sharpness_diagram`. O r0 declara todos.

`as_payload()` devolve um `dict` com as mesmas chaves do TOML (tuplas como
listas, enums pelo valor, `SeedSpec` sem seed como `"seedless"`,
`blinding_statement` e emenda só se presentes); `from_mapping(as_payload(p)) ==
p` (A1).

### Tabelas gold lidas (dono: `application/dtos/gold_schema.py`)

`GoldTableSchema(name, key, read_columns)` frozen; `GOLD_SCHEMAS` indexado
pelo nome. As chaves são as de hoje (technical 6.4 §1 "Tabelas gold"); os
`read_columns` são o que o scorecard e o perfil leem — nenhuma outra coluna é
lida por nome fora do schema.

| Tabela | `key` | `read_columns` |
|---|---|---|
| `gold_quality_checks` | `check, kind, horizon, model, seed` | `severity, outcome, occurrences, detail` |
| `gold_metrics_by_run` | `model, seed, horizon, sample, metric, level_low, level_high` | `value, n_points` |
| `gold_calibration_table` | `model, seed, horizon, sample, kind, level_low, level_high, includes_degenerate, dgt_offset, dgt_step, band_level` | `n_observed, n_violations, degeneracy_rate, wilson_contains_nominal, p_ind, p_cc, independence_status` |
| `gold_dm_results` | `horizon, variance_estimator, candidate, comparator` | `n_points, mean_differential, statistic, adjusted_p_value, rejected, fallback_applied, alpha` |
| `gold_mcs_results` | `horizon, scheme, model` | `included, statistic, block_size, max_block_estimate, alpha, reps, seed` |

### Estrutura de pastas afetada

```
config/preregistration/
├── aapl_confirmatory-r0.toml                                    # NOVO (13, 1º commit)
└── aapl_confirmatory-r0.anchor.toml                             # NOVO (13, 2º commit)
docs/
├── preregistration/aapl_confirmatory.md                         # NOVO (13); âncora no 2º commit
├── adr/6_5_0009-preregistered-conventional-values.md             # MODIFICADO (12, 2º commit): nota de emenda datada no topo
├── LAYOUT.md                                                     # MODIFICADO (01): §7 lista PreregistrationHash
└── roadmap.md                                                    # MODIFICADO (12): §Stage 6.5, 8.1 (#129), 8.2 e tabela
src/financial_forecasting/
├── composition_root.py                                           # MODIFICADO (11)
├── shared/domain/value_objects/preregistration_hash.py           # NOVO (01)
└── features/evaluation/
    ├── domain/
    │   ├── value_objects/
    │   │   ├── preregistration.py                                # NOVO (02)
    │   │   └── scorecard_evidence.py                             # NOVO (03)
    │   └── services/
    │       ├── model_confidence_set.py                           # MODIFICADO (02): MCS_STATISTIC, block_length_rule
    │       ├── christoffersen_test.py                            # MODIFICADO (02): validate_draws_and_seed público
    │       ├── h1_gate_power.py                                  # NOVO (03)
    │       ├── student_t.py                                      # MODIFICADO (09): student_t_quantile
    │       ├── h1_gate.py                                        # NOVO (04)
    │       ├── confirmatory_scorecard.py                         # NOVO (04)
    │       └── diebold_mariano.py                                # MODIFICADO (09): dm_effect_interval
    ├── application/
    │   ├── dtos/gold_schema.py                                   # NOVO (05)
    │   ├── dtos/refresh_gold.py                                  # MODIFICADO (05): inversas, GoldGeneration, erros
    │   ├── dtos/confirmatory_scorecard.py                        # NOVO (08: comando + cinco erros); MODIFICADO (09, 10)
    │   ├── ports/out/preregistration_source.py                   # NOVO (06)
    │   ├── ports/out/gold_generation_reader.py                   # NOVO (07)
    │   └── use_cases/
    │       ├── scorecard_evidence.py                             # NOVO (08)
    │       ├── scorecard_profile.py                              # NOVO (09)
    │       └── build_confirmatory_scorecard.py                   # NOVO (10)
    └── adapters/out/
        ├── toml/{__init__.py, toml_preregistration_source.py}    # NOVO (06)
        └── duckdb/
            ├── parquet_gold_store.py                             # MODIFICADO (07): read_generation
            └── gold_builders/{quality_checks, metrics_by_run, calibration_table, dm_results, mcs_results}.py  # MODIFICADO (05)
tests/
├── architecture/test_port_coverage_gate.py                       # MODIFICADO (07)
├── unit/shared/domain/value_objects/test_preregistration_hash.py # NOVO (01)
├── unit/shared/test_composition_root.py                          # MODIFICADO (11)
├── unit/features/evaluation/
│   ├── _preregistration_payload.py                               # NOVO (02)
│   ├── _scorecard_factory.py                                     # NOVO (08)
│   ├── test_preregistration_value_object.py                      # NOVO (02)
│   ├── test_preregistration_immutable_hash.py                    # NOVO (02)
│   ├── test_mcs_vs_arch.py                                       # MODIFICADO (02): só acréscimos
│   ├── test_christoffersen_monte_carlo.py                        # MODIFICADO (02): só acréscimos
│   ├── test_h1_gate_power.py                                     # NOVO (03)
│   ├── test_student_t.py                                         # MODIFICADO (09): só acréscimos
│   ├── test_scorecard_evidence.py                                # NOVO (03)
│   ├── test_h1_gate.py                                           # NOVO (04)
│   ├── test_scorecard_mechanical_rule.py                         # NOVO (04)
│   ├── gold/test_refresh_gold_dtos.py                            # MODIFICADO (05): só acréscimos
│   ├── test_refresh_command_from.py                              # NOVO (08)
│   ├── test_scorecard_evidence_mapper.py                         # NOVO (08)
│   ├── test_dm_vs_r_oracle.py                                    # MODIFICADO (09): só acréscimos
│   ├── test_scorecard_profile.py                                 # NOVO (09)
│   └── test_build_confirmatory_scorecard_use_case.py             # NOVO (10)
├── fakes/features/evaluation/
│   ├── in_memory_preregistration_source.py                       # NOVO (06)
│   └── in_memory_gold_generation_reader.py                       # NOVO (07)
├── contract/features/evaluation/
│   ├── test_gold_builder_contract.py                             # MODIFICADO (05): só acréscimos
│   ├── test_preregistration_source_contract.py                   # NOVO (06)
│   └── test_gold_generation_reader_contract.py                   # NOVO (07)
└── integration/features/evaluation/
    ├── test_build_confirmatory_scorecard.py                      # NOVO (11): e2e sintético
    └── test_preregistration_consistency.py                       # NOVO (13)
```

Intocados por decisão: `pyproject.toml`, `uv.lock`, `.importlinter`,
`scripts/arch_baseline.toml`, `concept.md`, ADRs 6.5.0001–0010 (salvo a nota
de emenda datada no topo do 6.5.0009 — o corpo `accepted` não muda; Task 12),
`src/**/modeling/**`, `config/cohorts/**`, `data/**` (nunca lido), o
`RefreshGold` e os serviços da 6.1–6.4 salvo os quatro arquivos de domínio
listados acima (acréscimos de API pública, mesmas mensagens).

### Rastreabilidade — concept §11 (critérios A*) → Tasks

Notação dos checks: `arquivo::token` — ver "Tokens de nome de teste" acima;
`U` = `tests/unit/features/evaluation/`, `S` =
`tests/unit/shared/domain/value_objects/`, `K` =
`tests/contract/features/evaluation/`, `I` =
`tests/integration/features/evaluation/`.

| # | Critério de aceitação (concept §11) | Tasks | Check objetivo |
|---|---|---|---|
| A1 | `from_mapping` recusa chave desconhecida/ausente, identificador não implementado e cada valor inválido pela mensagem do dono (um teste por bloco); `blinding_statement` ausente aceito, vazio recusado; ida e volta; qualquer folha muda o hash; 1e-12 × 1e-11 diferem; 0 × 0.0 iguais; referência `<name>-r<rev>-<hash12>`; emenda em r0 e r ≥ 1 sem emenda erguem | 01, 02 | `U/test_preregistration_value_object.py` (tokens da Task 02); `U/test_preregistration_immutable_hash.py::every_leaf_changes_hash`, `::leaf_paths_cover_payload`, `::tolerance_exponents_differ`, `::zero_int_float_same_hash`, `::reference_uses_hash12`; `S/test_preregistration_hash.py::prereg_hash_float_encoded_exactly`; `U/test_preregistration_value_object.py::payload_toml_writer_round_trip` |
| A2 | `check_layout` verde: `hash_mapping` só no `PreregistrationHash` (e nos VOs existentes) | 01 | Container da Task 01 (`uv run python scripts/check_layout.py`) + grep Host do §3 (única chamada nova em `shared/domain/value_objects/preregistration_hash.py`) |
| A3 | `refresh_command_from` devolve o comando com cada campo do plano (teste por campo) | 08 | `U/test_refresh_command_from.py::command_field_from_plan`, `::command_partition_from_cohort`, `::command_parameters_from_plan` |
| A4 | `H1GatePower` reproduz a tabela do doc §8.5 em n = 500 (0,041; 0,840; 0,996; 0,580; 0,536); taxas de locação do r0 recalculadas com `NormalDist` batem com o arquivo | 03, 13 | `U/test_h1_gate_power.py::power_doc_table_n500`; `I/test_preregistration_consistency.py::r0_location_rates_normal` |
| A5 | `H1Gate`: S = 2 com médias (nunca S·T) = `WilsonBand` à mão; degeneração > 1 % reprova com bandas contendo o nominal; não aplicável reprova; LR_uc 3 estados e DGT das mesmas médias; divergência nos dois sentidos; h = 1 sem DGT; n̄, T e aviso | 04 | `U/test_h1_gate.py` (tokens da Task 04; fronteira `::gate_degeneracy_at_threshold_passes`) |
| A6 | `decide`: um teste por desfecho e pelo vencedor; H1 reprovado com DM todo rejeitado → `NOT_APPLICABLE`; fora do MCS e supera os fortes vence; menor P̄_G só informação; comparador mal calibrado segue na leitura; horizontes independentes; sucesso = ≥ 1 horizonte; veredito idêntico com e sem perfil | 04, 10 | `U/test_scorecard_mechanical_rule.py` (tokens da Task 04, inclusive `::ml_tier_counts_as_strong` — P4: o GBM é forte); `U/test_build_confirmatory_scorecard_use_case.py::verdict_unchanged_by_profile` |
| A7 | Perfil: desfecho por nível, efeito do DM com IC, `fallback_applied`, calibração e limiar dos comparadores, 95 %, amostra comum, "sem lacunas", Bartlett e moving-block com divergências | 09 | `U/test_scorecard_profile.py` (tokens da Task 09); `U/test_dm_vs_r_oracle.py::dm_effect_interval_formula`; `U/test_student_t.py::t_quantile_published_values` |
| A8 | Use case com fakes: ordem I5 sem chamar o leitor; `GoldNotReadyError`; `PreregistrationMismatchError` por campo, modelo, seed, grade, estatística, bloco; `GoldGenerationCorruptError` por linha faltando; as duas falhas juntas → mismatch; prontidão falsa com razão (gold antes da âncora, emenda `unblinded`, check `SKIPPED`), verdadeira com refutação; declaração ecoada | 08, 10 | `U/test_scorecard_evidence_mapper.py` (tokens da Task 08); `U/test_build_confirmatory_scorecard_use_case.py` (tokens da Task 10; fronteira `::ready_true_started_at_anchor`) |
| A9 | Fakes e contratos `[fake, real]` dos dois ports (revisão inexistente, âncora ausente/presente; zero linhas, coluna toda `None`, `BLOCKED`, manifesto ausente, ida e volta); `GoldManifest.from_mapping(as_mapping(m)) == m` e `preregistration_ref` divergente recusado; builders com as chaves do `gold_schema`; `check_port_coverage` sem entrada nova | 05, 06, 07 | `K/test_preregistration_source_contract.py`, `K/test_gold_generation_reader_contract.py` (tokens das Tasks 06/07); `U/gold/test_refresh_gold_dtos.py::manifest_from_mapping_round_trip`, `::manifest_prereg_ref_divergent_rejected`; `K/test_gold_builder_contract.py::builders_use_schema_keys`; `tests/architecture/test_port_coverage_gate.py::scorecard_ports_resolve`; Host do §3 (baseline intocado) |
| A10 | E2E sintético (≥ 2 horizontes, candidato com 2 seeds, seis comparadores): plano → `refresh_command_from` → `RefreshGold` real → scorecard real no Parquet → veredito esperado; parâmetro alterado → mismatch em `preregistration_ref` (o hash muda primeiro, §1); mesmo plano sobre silver com seed a mais → mismatch em `seeds` | 11 | `I/test_build_confirmatory_scorecard.py` (tokens da Task 11), zero `SKIPPED`; `::e2e_paths_under_tmp` |
| A11 | r0 congelado com os valores dos ADRs 0009/0010; consistência com o cohort e com o espelho; nenhum texto afirma que nenhuma métrica foi computada sobre o r0; tag e comentário; `anchor.toml`; §7 com os dois carimbos na ordem e "a 6.5 não calculou nada sobre o cohort" | 13 | `I/test_preregistration_consistency.py` (tokens da Task 13); Host da Task 13 (tag remota, `created_at` do comentário, grep de afirmação proibida); Host do §3 (entrada única `[decision] Task 13 — âncora do pré-registro r0`) |
| A12 | `lint-imports` verde; nada de runtime de `modeling` em `src/**/evaluation`; `tomllib` só em `adapters/out/toml/`; `pyarrow` só em `adapters/out/duckdb/` | todas (T1); §3 | `uv run lint-imports` + greps Host do §3 |
| A13 | Roadmap §Stage 6.5 (DoD e descrição), 8.1 e 8.2 conforme D10 (8.1 depende da #129); LAYOUT §7 com o `PreregistrationHash` | 01, 12 | greps Host das Tasks 01 e 12 (reprovam no HEAD `29c9184`) |
| A14 | `make check` verde | todas; §3 | bloco Container do §3 (inclui cobertura por arquivo) |

### Rastreabilidade — invariantes (I*) e casos de erro (C*) → Tasks

| # | Regra (concept §5/§6) | Tasks | Check objetivo |
|---|---|---|---|
| I1 | Um artefato canônico por revisão; espelho cita o hash completo de cada revisão | 02, 13 | `U/test_preregistration_value_object.py::prereg_payload_round_trip`; `I/test_preregistration_consistency.py::every_revision_hash_quoted` |
| I2 | Qualquer folha muda o hash; 1e-12 × 1e-11; 0 × 0.0; emenda = revisão nova com `amends` | 01, 02, 10 | `U/test_preregistration_immutable_hash.py::every_leaf_changes_hash`, `::tolerance_exponents_differ`, `::zero_int_float_same_hash`; `S/test_preregistration_hash.py::prereg_hash_float_encoded_exactly`; `U/test_build_confirmatory_scorecard_use_case.py::chain_broken_before_reader` |
| I3 | Só o `PreregistrationHash` chama `hash_mapping`; referência por uma função | 01, 02 | `check_layout` (Task 01); `U/test_preregistration_immutable_hash.py::hasher_never_sees_float`, `::reference_uses_hash12` |
| I4 | Regras nomeadas aceitas só se implementadas | 02, 04 | `U/test_preregistration_value_object.py::prereg_rule_identifier_unimplemented`, `::prereg_rule_catalog_complete`; `U/test_scorecard_mechanical_rule.py::services_check_rule_identifiers` |
| I5 | Ordem: cadeia → hash → âncora antes de ler o gold | 10 | `U/test_build_confirmatory_scorecard_use_case.py::hash_mismatch_before_reader`, `::chain_broken_before_reader`, `::unanchored_before_reader`, `::validation_order_chain_hash_anchor` |
| I6 | Uma derivação; partição do plano; gold conferido nos dois sentidos | 08, 10, 11 | `U/test_refresh_command_from.py::command_field_from_plan`; `U/test_build_confirmatory_scorecard_use_case.py::reader_reads_derived_partition`, `::command_has_no_partition`; `U/test_scorecard_evidence_mapper.py::mismatch_manifest_field`; `I/test_build_confirmatory_scorecard.py::e2e_parameter_changed_mismatch` |
| I7 | Manifesto primeiro; um dono do schema e da montagem; `partitioning=None`; zero linhas pelo `rows_by_table` | 05, 07 | `U/gold/test_refresh_gold_dtos.py::from_stored_empty_table`, `::schema_tables_complete`; `K/test_gold_generation_reader_contract.py::real_reads_manifest_first`, `::real_no_hive_inference`, `::real_single_assembly`, `::reader_zero_row_table`; `U/test_scorecard_evidence_mapper.py::mapper_gate_rows_band_level` |
| I8 | Nada recomputado: só médias, kernels de contagem, poder, IC e lógica | 04, 08, 09 | `U/test_h1_gate.py::gate_calls_count_kernels`; `U/test_scorecard_profile.py::profile_copies_gold_values`; grep Host do §3 (sem `DieboldMariano`/`HolmCorrection`/`ModelConfidenceSet.evaluate`/`CoverageMetrics`/`HitSequences` nos módulos novos da application) |
| I9 | Por horizonte; nenhum campo agrega horizontes | 04 | `U/test_scorecard_mechanical_rule.py::horizons_independent`, `::study_success_one_horizon` |
| I10 | Só o candidato é filtrado; Holm = seis, MCS = sete | 04, 08, 09 | `U/test_scorecard_mechanical_rule.py::comparator_miscalibrated_stays_in_family`; `U/test_scorecard_evidence_mapper.py::mismatch_model_extra_missing`; `U/test_scorecard_profile.py::profile_comparators_threshold` |
| I11 | n nunca é S·T | 04 | `U/test_h1_gate.py::gate_seed_mean_not_st` |
| I12 | Perfil nunca troca o veredito | 04, 10 | `U/test_scorecard_mechanical_rule.py::verdict_without_profile_fields`; `U/test_build_confirmatory_scorecard_use_case.py::verdict_unchanged_by_profile` |
| I13 | Prontidão ≠ vitória; razões nomeadas | 10 | `U/test_build_confirmatory_scorecard_use_case.py::ready_true_refutation`, `::blinding_echoed_not_conjoined`, `::ready_false_gold_before_anchor` |
| I14 | Sem default; só `blinding_statement` opcional | 02 | `U/test_preregistration_value_object.py::prereg_missing_key_rejected` (parametrizado sobre toda chave), `::prereg_blinding_absent_accepted` |
| I15 | Nenhuma métrica sobre o cohort nesta Stage; nenhuma afirmação sobre o passado do r0 | todas; 13; §3 | grep Host do §3 (nenhum arquivo novo de `src/`/`tests/` cita `data/cohorts`); `I/test_preregistration_consistency.py::no_claim_about_r0_past`; entrada `[decision] Task 13` em §7 |
| C1 | Pré-registro malformado → `ValueError` pela mensagem do dono | 02 | tokens da Task 02 em `U/test_preregistration_value_object.py` |
| C2 | Revisão inexistente → `PreregistrationNotFoundError` | 06, 10 | `K/test_preregistration_source_contract.py::source_missing_revision_raises`; `U/test_build_confirmatory_scorecard_use_case.py::not_found_propagates` |
| C3 | Hash divergente → `PreregistrationHashMismatchError` antes do gold | 10 | `U/test_build_confirmatory_scorecard_use_case.py::hash_mismatch_before_reader` |
| C4 | Cadeia quebrada → `PreregistrationChainError` | 10 | `U/test_build_confirmatory_scorecard_use_case.py::chain_broken_before_reader` |
| C5 | Revisão sem âncora → `PreregistrationNotAnchoredError` | 10 | `U/test_build_confirmatory_scorecard_use_case.py::unanchored_before_reader` |
| C6 | Sem manifesto → `GoldManifestNotFoundError`; tabela ausente/contagem/incoerente → `GoldGenerationCorruptError`; linha faltando para modelo/seed presente → corrupt (depois de C8) | 05, 07, 08 | `U/gold/test_refresh_gold_dtos.py::from_stored_missing_table_corrupt`, `::from_stored_count_mismatch_corrupt`, `::from_stored_incoherent_corrupt`; `K/test_gold_generation_reader_contract.py::reader_missing_manifest_raises`, `::real_missing_table_file_corrupt`; `U/test_scorecard_evidence_mapper.py::corrupt_seed_missing_tail`, `::corrupt_horizon_row_missing`, `::corrupt_estimator_row_missing`, `::corrupt_scheme_row_missing`, `::mismatch_before_corrupt`; `U/test_scorecard_evidence_mapper.py::corrupt_block_estimate_missing`, `::corrupt_completed_with_failed_check` |
| C7 | `BLOCKED` → `GoldNotReadyError` com os checks | 10 | `U/test_build_confirmatory_scorecard_use_case.py::blocked_gold_not_ready` |
| C8 | Outro plano/cohort (manifesto, modelos, seeds, grade, estatística, bloco) → `PreregistrationMismatchError` nomeando o campo | 08, 11 | `U/test_scorecard_evidence_mapper.py::mismatch_manifest_field`, `::mismatch_model_extra_missing`, `::mismatch_seed_extra_missing`, `::mismatch_grid_levels`, `::mismatch_mcs_statistic`, `::mismatch_block_rule`; `I/test_build_confirmatory_scorecard.py::e2e_parameter_changed_mismatch`, `::e2e_extra_seed_mismatch` |
| C9 | Candidato 100 % degenerado → banda não aplicável, gate reprova, `NOT_APPLICABLE` | 04 | `U/test_h1_gate.py::gate_not_applicable_fails`; `U/test_scorecard_mechanical_rule.py::outcome_not_applicable` |
| C10 | Gold antes da âncora, emenda `unblinded`, check exigido `SKIPPED` → prontidão falsa com razão | 10 | `U/test_build_confirmatory_scorecard_use_case.py::ready_false_gold_before_anchor`, `::ready_false_unblinded_amendment`, `::ready_false_required_check_skipped`; fronteira `::ready_true_started_at_anchor` |
| C11 | Erro de programação propaga | 04, 10 | `U/test_scorecard_mechanical_rule.py::decide_horizon_set_mismatch_raises`; `U/test_build_confirmatory_scorecard_use_case.py::programming_error_propagates` |

## 2. Tasks

> Faixa desta Stage: **13 Tasks** (estimativa do concept: 12 — exceção
> declarada no §1). A ordem executável é 01 → 12; a 13 espera a decisão humana
> do `blinding_statement` (§4). Blocos de verificação conforme a convenção
> **Container/Host** do §1.

### Task 01 — `PreregistrationHash` em `shared` + LAYOUT §7

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/value_objects/preregistration_hash.py`
  - `tests/unit/shared/domain/value_objects/test_preregistration_hash.py`
- **Arquivos a modificar:**
  - `docs/LAYOUT.md` — §7 "Identidade só pelos VOs…": acrescenta
    `PreregistrationHash` (hash do pré-registro confirmatório, floats
    codificados exatamente, ADR 6.5.0001) à lista.
- **O que fazer (concept §4 "Shared", D1, I2, I3; ADR 6.5.0001 item 3):**
  VO frozen `PreregistrationHash(value: str)` com
  `compute(*, hasher: Hasher, payload: Mapping[str, object]) ->
  PreregistrationHash`: percorre o payload recursivamente (mapeamentos,
  listas, tuplas) e troca **todo** `float` `x` por `f"float:{x!r}"` (o `bool`
  fica intacto — é subtipo de `int`, não de `float`; `int` fica `int`), sem
  mutar o payload de entrada; delega `hasher.hash_mapping` sobre a cópia
  codificada. Docstring: por que a codificação (o `CanonicalJsonHasher`
  arredonda a 10 casas, ADR 1.4.0001) e por que a coerção int/float é do
  chamador (o VO do plano), não daqui. `Hasher` só sob `TYPE_CHECKING`
  (precedente `CohortHash`).
- **Critério de aceite (A1, A2, I2, I3):** com o `CanonicalJsonHasher` real:
  `{"tol": 1e-12}` × `{"tol": 1e-11}` dão hashes diferentes (e o hasher sozinho,
  sem o VO, dá o mesmo — prova de que o teste discrimina); floats aninhados em
  listas e mapas também codificados; `{"x": 0}` × `{"x": 0.0}` diferem **aqui**
  (a coerção é do chamador); `True` não vira `"float:..."`; ordem de chaves
  irrelevante; o payload de entrada não muda; sha256 hex de 64. `check_layout`
  verde (a única chamada nova de `hash_mapping` está em
  `shared/domain/value_objects/`).
- **Tokens:** `tests/unit/shared/domain/value_objects/test_preregistration_hash.py`:
  `prereg_hash_float_encoded_exactly`, `prereg_hash_nested_floats_encoded`,
  `prereg_hash_int_not_coerced`, `prereg_hash_bool_untouched`,
  `prereg_hash_key_order_irrelevant`, `prereg_hash_payload_not_mutated`.
- **Verificação (T1 = `check-block`, toca `shared` e LAYOUT) — Container:**
  ```bash
  uv run pytest tests/unit/shared/domain/value_objects/test_preregistration_hash.py tests/unit/shared/domain/value_objects/test_cohort_hash.py -v
  uv run python scripts/check_layout.py
  f=$(mktemp)
  grep -rn "hash_mapping" src/financial_forecasting/shared/domain/value_objects/preregistration_hash.py > "$f"
  test -s "$f"
  make check-block
  ```
  **Host:**
  ```bash
  test -s docs/LAYOUT.md
  grep -q "PreregistrationHash" docs/LAYOUT.md
  python scripts/check_docs_pointers.py
  ```
- **Commit sugerido:** `feat(shared): PreregistrationHash com floats codificados exatamente [6.5/task-01]`

---

### Task 02 — VO `Preregistration` com catálogo de regras + donos públicos da 6.2/6.3

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/value_objects/preregistration.py`
  - `tests/unit/features/evaluation/_preregistration_payload.py`
  - `tests/unit/features/evaluation/test_preregistration_value_object.py`
  - `tests/unit/features/evaluation/test_preregistration_immutable_hash.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/model_confidence_set.py`
    — `_STATISTIC` → `MCS_STATISTIC: Final = "R"` público;
    `block_length_rule(*, horizon: int, max_estimate: float) -> int` público
    (`max(horizon, math.ceil(max_estimate))`, com `validate_horizon` e
    estimativa finita ≥ 0); `ModelConfidenceSet.block_length` passa a chamá-lo
    (mesmas mensagens, mesma ordem de validação).
  - `src/financial_forecasting/features/evaluation/domain/services/christoffersen_test.py`
    — `_validate_draws_and_seed` → `validate_draws_and_seed(draws, seed)`
    público; as chamadas internas passam a usá-lo (mesmas mensagens).
  - `tests/unit/features/evaluation/{test_mcs_vs_arch.py, test_christoffersen_monte_carlo.py}`
    — **só acréscimos**.
- **O que fazer (concept §4 "Domínio", D1, D2, D4, D9, I1–I4, I14, C1; ADRs
  6.5.0001 item 2, 6.5.0002 item 1, 6.5.0004 itens 1–2, 6.5.0009, 6.5.0010):**
  - `preregistration.py` (frozen, stdlib + validadores donos): `Preregistration`
    e os VOs aninhados do §1 "Esquema" (`CohortReference`, `RealizedSource`,
    `HorizonNotEvaluated`, `ComparatorTiers`, `SeedSpec`, `RuleIdentifiers`,
    `DmSpec`, `McsSpec`, `H1GateSpec`, `TailDeviation`, `ScenarioRole`,
    `MonteCarloSpec`, `ProfileSpec`, `Amendment`, `BlindStatus`),
    `RULE_CATALOG`, `PROFILE_CATALOG`, `REALIZED_SOURCES`.
    `Preregistration.from_mapping(mapping)` na ordem: chaves desconhecidas/
    ausentes por bloco (mensagem com o caminho pontuado, ex. `"h1_gate.
    degeneracy_threshold"`) → coerção de tipo → validadores donos → regras
    cruzadas (níveis disjuntos e sem candidato; chaves de `seeds`/
    `window_deficits` = candidato ∪ comparadores; seeds sem repetição; déficit
    ≥ 0; par do gate na grade com `lower < 0.5 < upper`; `lower_level +
    upper_level == 1`; cenário com taxas em (0, 1) e soma < 1; ≥ 1 cenário
    primário; rótulos únicos; `horizons_not_evaluated` disjunto de `horizons`;
    sensibilidades sem o primário; emenda proibida em r0 e obrigatória em r ≥ 1;
    `blinding_statement` não vazio se presente). `as_payload()` (§1) e
    `reference(digest: PreregistrationHash) -> str` =
    `f"{name}-r{revision}-{digest.value[:12]}"` (única função da referência).
    Propriedades de leitura usadas adiante: `comparators` (os seis, na ordem
    naive → estatístico forte → ML), `models` (candidato + comparadores),
    `strong` (estatístico forte ∪ ML).
  - `_preregistration_payload.py` — decisão de detalhe do §1
    (`valid_payload()`, `to_toml(...)`, `PAYLOAD_TOML`, `key_paths(...)`
    pontuado sem índices, `leaf_paths(...)` com caminhos indexados,
    `with_leaf(...)`, `FloatRefusingHasher`).
- **Critério de aceite (A1, I1–I4, I14, C1):** chave desconhecida e cada chave
  ausente (parametrizado sobre **toda** chave obrigatória do payload, via
  `key_paths(payload)` — caminhos pontuados de **chave**, sem índices, ex.
  `"h1_gate.power_scenarios"`, `"dm.alpha"`; remover um elemento de lista não
  é "chave ausente"; Checkpoint B r2, item 4) erguem nomeando o caminho; `blinding_statement` ausente aceito,
  `""` recusado; cada identificador de regra diferente do catálogo recusado; o
  catálogo cobre exatamente os campos de `RuleIdentifiers` e
  `RULE_CATALOG["mcs.statistic"] is MCS_STATISTIC`; um caso por bloco com valor
  inválido casando a mensagem do validador dono (`validate_alpha`,
  `validate_rate`, `validate_tolerance`, `validate_min_violations`,
  `validate_mcs_reps`, `validate_bootstrap_parameters`,
  `validate_draws_and_seed`, `validate_horizon`, `validate_path_identifier`);
  níveis sobrepostos ou com o candidato, modelo sem seed ou sem déficit, seed
  repetida, déficit negativo, cenário inválido, perfil fora do catálogo erguem;
  `0` num campo float vira `0.0` e `1.0` num campo int ergue, `True` em campo
  numérico ergue; emenda em r0 ergue e r1 sem `amends` ergue, r1 completo é
  aceito; `from_mapping(p.as_payload()) == p`; `tomllib.loads(to_toml(q)) ==
  q` para o plano base, um r1 com emenda, um `blinding_statement` com aspas,
  barra invertida, `\n` e caractere de controle, e uma lista de tabelas vazia. Hash (com o dublê que recusa float): para **todo** caminho
  de `leaf_paths(p.as_payload())`, `PreregistrationHash.compute` direto sobre
  `with_leaf(p.as_payload(), path, alt)` difere do hash de `p` — **sem**
  passar por `from_mapping`, porque várias folhas só têm um valor válido
  (identificadores de regra, `realized.source`, `revision` de r0, nomes de
  modelo, par do gate; Checkpoint B r1, T-F2); `alt` por tipo (`str` + `"_x"`,
  `int` + 1, `float` × 1,5 ou 1,0 se zero, `bool` negado); e
  `leaf_paths(p.as_payload()) == leaf_paths(valid_payload())` (o payload
  canônico não perde nem ganha folha);
  `degeneracy_tolerance` 1e-12 × 1e-11 diferem; `0` × `0.0` num campo float
  dão o mesmo hash; referência = `"test_plan-r0-" + hash[:12]`.
  Donos públicos: `MCS_STATISTIC == "R"` e o `McsReport` ainda recusa outra;
  `block_length_rule(horizon=7, max_estimate=3.2) == 7`,
  `(horizon=1, max_estimate=3.2) == 4`; `ModelConfidenceSet.block_length`
  ergue um sentinela quando `model_confidence_set_module.block_length_rule` é
  trocado (dono único); `validate_draws_and_seed` ergue em `draws` 0/`True`,
  `seed` `True`/`1.5`, e o Monte Carlo ergue o sentinela quando é trocado; os
  testes existentes dos dois arquivos da 6.2/6.3 verdes **sem alteração** (diff
  só com `+`).
- **Tokens:** `test_preregistration_value_object.py`:
  `prereg_unknown_key_rejected`, `prereg_missing_key_rejected`,
  `prereg_rule_identifier_unimplemented`, `prereg_rule_catalog_complete`,
  `prereg_owner_validator_messages`, `prereg_tiers_overlap_rejected`,
  `prereg_candidate_in_tier_rejected`, `prereg_model_without_seed_rejected`,
  `prereg_model_without_deficit_rejected`, `prereg_repeated_seeds_rejected`,
  `prereg_negative_deficit_rejected`, `prereg_power_scenario_invalid`,
  `prereg_profile_unknown_rejected`, `prereg_amendment_in_revision_zero`,
  `prereg_amendment_required_after_zero`, `prereg_amendment_complete_accepted`,
  `prereg_blinding_absent_accepted`, `prereg_blinding_empty_rejected`,
  `prereg_int_coerced_to_float`, `prereg_float_rejected_where_int`,
  `prereg_bool_rejected_as_number`, `prereg_payload_round_trip`,
  `payload_toml_writer_round_trip`;
  `test_preregistration_immutable_hash.py`: `every_leaf_changes_hash`,
  `leaf_paths_cover_payload`, `tolerance_exponents_differ`, `zero_int_float_same_hash`,
  `hasher_never_sees_float`, `reference_uses_hash12`; `test_mcs_vs_arch.py`:
  `mcs_statistic_public_constant`, `block_rule_single_owner`,
  `block_rule_ceiling_values`; `test_christoffersen_monte_carlo.py`:
  `draws_seed_validator_public`, `draws_seed_single_owner`.
- **Verificação (T1) — Container:**
  ```bash
  U=tests/unit/features/evaluation
  D=src/financial_forecasting/features/evaluation/domain
  uv run pytest $U/test_preregistration_value_object.py $U/test_preregistration_immutable_hash.py $U/test_mcs_vs_arch.py $U/test_christoffersen_monte_carlo.py -v
  test -s $D/services/model_confidence_set.py
  test -s $D/services/christoffersen_test.py
  if grep -nE "(^|[^A-Z])_STATISTIC\b|_validate_draws_and_seed" $D/services/model_confidence_set.py $D/services/christoffersen_test.py; then echo "FAIL: dono privado remanescente"; exit 1; fi
  test "$(grep -cE "^\s+return max\(horizon, math\.ceil\(" $D/services/model_confidence_set.py)" -eq 1
  d=$(mktemp)
  base=$(git merge-base origin/develop HEAD)
  git diff "$base" -- $U/test_mcs_vs_arch.py $U/test_christoffersen_monte_carlo.py > "$d"
  test -s "$d"
  if grep -nE '^-([^-]|$)' "$d"; then echo "FAIL: teste existente da 6.2/6.3 alterado"; exit 1; fi
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): VO Preregistration com catálogo de regras e donos da 6.2/6.3 [6.5/task-02]`

---

### Task 03 — `H1GatePower` e VOs de evidência

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/h1_gate_power.py`
  - `src/financial_forecasting/features/evaluation/domain/value_objects/scorecard_evidence.py`
  - `tests/unit/features/evaluation/test_h1_gate_power.py`
  - `tests/unit/features/evaluation/test_scorecard_evidence.py`
- **Arquivos a modificar:** nenhum (o quantil da t foi para a Task 09, junto
  do seu consumidor — Checkpoint B r1, A11).
- **O que fazer (concept §4 "Domínio", D6, D8; ADR 6.5.0006 itens 2, 5,
  6.5-POWER; ADR 6.5.0008 item 2):**
  - `H1GatePower.failure_probability(*, n: int, spec: H1GateSpec, deviation:
    TailDeviation) -> float` — algoritmo do §1 ("Poder sem O(n²)"); nominais
    por `violation_rate_for` (cauda inferior `(τ_l,)`, superior `(τ_u,)`);
    `n` `int` não-`bool` ≥ 1. O poder ignora a degeneração (declarado na
    docstring e no resultado do gate).
  - `scorecard_evidence.py` (frozen): `SeedTailCounts(seed, n_violations,
    n_observed, degeneracy_rate)`; `TailEvidence(level, seeds)` com
    `mean_violations`, `mean_observed`, `mean_degeneracy`, `mean_of_seed_rates`
    (ADR 6.5.0006 item 2: razão de médias para a banda; média das taxas só para
    o perfil); `DgtTailEvidence(offset, step, lower, upper)`;
    `CalibrationEvidence(sample, lower, upper, dgt)` (seeds iguais nas duas
    caudas e em cada sub-série; `dgt` com offsets 0..h−1 e `step = h` quando
    h > 1, vazio quando h = 1); `ComparatorCalibration(model, lower, upper)`;
    `DmEvidence(comparator, estimator, n_points, mean_differential, statistic,
    adjusted_p_value, rejected, fallback_applied)`; `McsEvidence(scheme, model,
    included)`; `HorizonEvidence(horizon, common_points, gate, common,
    comparators_calibration, mean_pinball, dm, mcs)` (coerência: horizontes
    iguais, `gate.sample == "model_full"`, `common.sample == "common"`, DM sem
    par (comparador, estimador) repetido, MCS sem par (esquema, modelo)
    repetido); `SeedSpread.of(values) -> SeedSpread(mean, minimum, maximum,
    n_seeds)` (dono da agregação entre seeds dos descritores).
- **Critério de aceite (A4):** em n = 500 com os cenários do doc §8.5 —
  calibrado (0,10/0,10), locação 0,2σ e 0,3σ (taxas pelo `NormalDist` no
  teste), cobertura 75 % (0,125/0,125) e 85 % (0,075/0,075) — a probabilidade
  de reprovar arredondada a 3 casas é 0,041; 0,840; 0,996; 0,580; 0,536; em
  n ∈ {5, 20} o algoritmo iguala a soma dupla bruta da multinomial (tolerância
  1e-12); a aceitação vem do `WilsonBand` (monkeypatch do dono muda o
  resultado); `n` 0/`True`/`2.0` erguem. VOs: cada invariante com um caso;
  médias com S = 2 de n_observed diferentes dão razão de médias ≠ média das
  taxas; `SeedSpread` de um valor tem média = mínimo = máximo.
- **Tokens:** `test_h1_gate_power.py`: `power_doc_table_n500`,
  `power_equals_brute_double_sum`, `power_acceptance_from_wilson_owner`,
  `power_invalid_n_rejected`;
  `test_scorecard_evidence.py`: `evidence_seed_counts_invalid`,
  `evidence_tail_ratio_of_means`, `evidence_dgt_offsets_complete`,
  `evidence_single_step_without_dgt`, `evidence_horizon_incoherent`,
  `evidence_dm_pair_repeated`, `evidence_seed_spread`.
- **Verificação (T1) — Container:**
  ```bash
  U=tests/unit/features/evaluation
  uv run pytest $U/test_h1_gate_power.py $U/test_scorecard_evidence.py -v --durations=3
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): poder exato do gate H1 e VOs de evidência [6.5/task-03]`

---

### Task 04 — `H1Gate` e `ConfirmatoryScorecard`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/domain/services/h1_gate.py`
  - `src/financial_forecasting/features/evaluation/domain/services/confirmatory_scorecard.py`
  - `tests/unit/features/evaluation/test_h1_gate.py`
  - `tests/unit/features/evaluation/test_scorecard_mechanical_rule.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, D6, D7, I8–I12, C9, C11; ADRs 6.5.0006 itens
  1–5, 7, 6.5.0007 itens 1–7):**
  - `H1Gate.evaluate(spec: H1GateSpec, evidence: HorizonEvidence) ->
    H1Result`: médias da `evidence.gate` (c̄_l, c̄_u, n̄, degeneração média);
    `WilsonBand.evaluate(horizon, count=c̄, n=n̄, nominal, band_level=
    spec.gate_band_level)` por cauda (nominais por `violation_rate_for`);
    `passed` ⇔ as duas bandas aplicáveis e contendo a nominal ∧ degeneração
    média ≤ `degeneracy_threshold`. Sensibilidades (nunca veredito): LR_uc de 3
    estados (`lr_uc_three_state` + `chi_square_sf(df=2)`, rejeita se p <
    `sensitivity_alpha`) sobre as mesmas médias; DGT (h > 1) sobre as médias de
    cada sub-série, banda a `1 − sensitivity_alpha/(2h)`, passa se as 2h bandas
    contêm a nominal (h = 1 → `None`); gate recomputado na amostra comum
    (`evidence.common`). `H1Result`: `horizon`, `passed`, `lower_band`,
    `upper_band`, `mean_observed` (n̄), `common_points` (T),
    `serial_dependence_warning`, `mean_degeneracy_rate`,
    `degeneracy_above_threshold`, `mean_of_seed_rates` (perfil),
    `power: tuple[GatePower, ...]` (`label`, `role`, `n = round(n̄)`,
    `failure_probability`; vazio se n̄ < 0,5), `power_assumes_independence`
    (= h > 1), `lr_uc`, `dgt`, `common_sample_passed`, `divergences:
    tuple[str, ...]` (nome de cada sensibilidade cujo resultado difere do gate,
    nos dois sentidos). Banda não aplicável → sensibilidades `None`, gate
    reprova. Assinatura do concept mantida (`evaluate(spec, evidence)`); quem
    confere `rules.h1_gate.form` contra o catálogo é o `decide`, que recebe o
    plano inteiro. As bandas das duas
    caudas saem de um método público `H1Gate.tail_bands(spec, *, horizon,
    lower: TailEvidence, upper: TailEvidence, band_level)` — o mesmo que o
    perfil usa para os comparadores (S = 1) e para a banda a 95 % (Task 09),
    sem segunda escrita da regra.
  - `ConfirmatoryScorecard.decide(prereg: Preregistration, evidence:
    Sequence[HorizonEvidence]) -> ScorecardVerdict`: horizontes da evidência =
    `prereg.horizons` (senão `ValueError`, C11); por horizonte: `h1`; linhas DM
    do estimador primário; `beats_naive` = Holm rejeita contra **todo** naive;
    `beats_every_strong` = rejeita contra todo forte (estatístico forte ∪ ML);
    `in_mcs` = candidato incluído no esquema primário;
    `beats_or_ties_strong` = `in_mcs ∨ beats_every_strong`; `h2`:
    `NOT_APPLICABLE` se H1 reprova, senão `NO_SKILL_OVER_NAIVE` /
    `BEATS_NAIVE_ONLY` / `BEATS_NAIVE_TIES_STRONG` / `BEATS_NAIVE_AND_STRONG`
    (ADR 6.5.0007 item 2); `primary_winner` = candidato ⇔ H1 ∧ (i) ∧ (ii);
    `candidate_has_lowest_mean_pinball` (P̄_G da amostra comum; informação).
    `ScorecardVerdict(horizons, study_success_h1)` com `study_success_h1` =
    "≥ 1 horizonte com H1". `tier_readings(prereg, evidence) ->
    tuple[TierReading, ...]` (por horizonte e nível naive/estatístico forte/ML:
    Holm rejeita contra todos? candidato no MCS com eles?) — função separada,
    consumida pelo perfil (Task 09); `decide` não a chama. Na entrada, `decide`
    confere `rules.h1_gate.form`, `rules.verdict.form` e
    `rules.success_criterion` contra o catálogo.
- **Critério de aceite (A5, A6, I8–I12, C9, C11):** gate com S = 2 e n_observed
  diferentes entre seeds: as bandas são **iguais** (`==`) a `WilsonBand.evaluate`
  chamado à mão com as médias e **diferentes** das com S·T; degeneração média
  0,011 reprova com as duas bandas contendo a nominal e degeneração média
  **exatamente** 0,01 passa (limiar inclusivo, "≤", ADR 6.5.0006 item 3);
  n̄ = 0 → não aplicável e
  reprova; espião nos kernels (`WilsonBand.evaluate`, `lr_uc_three_state`,
  `chi_square_sf`) mostra as mesmas médias; DGT com h = 3 usa o nível
  `1 − 0,05/6` e as 6 bandas; h = 1 → `dgt is None`; um caso gate passa /
  LR_uc rejeita e outro gate reprova / comum passa listam a divergência;
  resultado carrega n̄, T, aviso e poder com `n = round(n̄)`. Scorecard: um
  teste por desfecho; vencedor só com H1 ∧ (i) ∧ (ii); H1 reprovado com DM
  todo rejeitado → `NOT_APPLICABLE` e `primary_winner is None`; candidato fora
  do MCS que supera todos os fortes vence; (i) verdadeiro, candidato fora do
  MCS primário, Holm rejeita contra os três estatísticos fortes mas **não**
  contra o `gbm_quantile` → `BEATS_NAIVE_ONLY` e `primary_winner is None` (o
  nível ML conta como forte — P4, ADR 6.5.0010; Checkpoint B r1, T-F3);
  candidato sem a menor P̄_G vence (a
  flag é falsa); comparador com a própria banda reprovada e degeneração acima
  do limiar continua nas contagens de Holm e no MCS; mudar a evidência de um
  horizonte não muda o outro; `study_success_h1` verdadeiro com um horizonte
  só; `ScorecardVerdict`/`HorizonVerdict` não têm campo de tipo do perfil
  (inspeção de `dataclasses.fields`); horizontes da evidência ≠ do plano
  ergue; identificador de regra fora do catálogo (plano montado com
  `object.__setattr__`) ergue.
- **Tokens:** `test_h1_gate.py`: `gate_seed_mean_not_st`,
  `gate_degeneracy_over_threshold_fails`, `gate_degeneracy_at_threshold_passes`,
  `gate_not_applicable_fails`,
  `gate_calls_count_kernels`, `gate_lr_uc_sensitivity`,
  `gate_dgt_bonferroni_level`, `gate_single_step_no_dgt`,
  `gate_common_sample_sensitivity`, `gate_divergence_both_directions`,
  `gate_result_carries_n_t_warning`, `gate_power_rounded_n`;
  `test_scorecard_mechanical_rule.py`: `outcome_not_applicable`,
  `outcome_no_skill_over_naive`, `outcome_beats_naive_only`,
  `outcome_beats_naive_ties_strong`, `outcome_beats_naive_and_strong`,
  `winner_requires_gate_and_both`, `h1_fail_all_rejected_no_winner`,
  `outside_mcs_beats_strong_wins`, `ml_tier_counts_as_strong`,
  `lowest_pinball_only_information`,
  `comparator_miscalibrated_stays_in_family`, `horizons_independent`,
  `study_success_one_horizon`, `verdict_without_profile_fields`,
  `tier_reading_per_tier`, `decide_horizon_set_mismatch_raises`,
  `services_check_rule_identifiers`.
- **Verificação (T1) — Container:**
  ```bash
  U=tests/unit/features/evaluation
  uv run pytest $U/test_h1_gate.py $U/test_scorecard_mechanical_rule.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): gate H1 sobre contagens médias e árvore H1 → H2 por horizonte [6.5/task-04]`

> **Checkpoint C (T2) após esta Task:** `make check-block` + revisão
> independente do bloco 01–04.

---

### Task 05 — `gold_schema` dono + inversas + `GoldGeneration.from_stored`; builders com as chaves do schema

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/gold_schema.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/refresh_gold.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders/{quality_checks.py, metrics_by_run.py, calibration_table.py, dm_results.py, mcs_results.py}`
  - `tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py` — **só acréscimos**
  - `tests/contract/features/evaluation/test_gold_builder_contract.py` — **só acréscimos**
- **O que fazer (concept §4 "Application", D5, I7, C6; ADR 6.5.0005 itens 2,
  3, 5):**
  - `gold_schema.py`: `GoldTableSchema(name, key, read_columns)` frozen;
    `GOLD_QUALITY_CHECKS`, `GOLD_METRICS_BY_RUN`, `GOLD_CALIBRATION_TABLE`,
    `GOLD_DM_RESULTS`, `GOLD_MCS_RESULTS` com o conteúdo do §1 "Tabelas gold
    lidas"; `GOLD_SCHEMAS: Mapping[str, GoldTableSchema]` pelo nome;
    `CONFIRMATORY_TABLES` (as quatro com `preregistration_ref`).
  - Builders: apagam `_KEY` e o `f"gold_{self.name}"`; `build` devolve
    `GoldTable.sorted_by_key(SCHEMA.name, SCHEMA.key, rows)`. Nenhuma linha
    muda.
  - `refresh_gold.py` (aditivo): `RefreshParameters.from_mapping(mapping)`
    (inversa de `as_mapping`: listas → tuplas, enums pelo valor);
    `GoldManifest.from_mapping(mapping)` (inversa: partição, status, fingerprint
    pelo VO, `datetime.fromisoformat`; recusa `preregistration_ref` de topo ≠
    `parameters.preregistration_ref`, e chave desconhecida/ausente);
    `GoldManifestNotFoundError(ApplicationError)` e
    `GoldGenerationCorruptError(ApplicationError)`; `GoldGeneration(manifest,
    tables: Mapping[str, GoldTable])` com `table(schema) -> GoldTable`;
    `GoldGeneration.from_stored(manifest: Mapping[str, object], rows_by_table:
    Mapping[str, Sequence[Row]]) -> GoldGeneration` — decisão "Gold lido por um
    dono de erro" do §1; uma `GoldTable` por tabela do manifesto com a chave do
    `GOLD_SCHEMAS` (nome desconhecido → corrupt); `check_generation` no fim.
- **Critério de aceite (A9, I7, C6):** `GoldManifest.from_mapping(m.as_mapping())
  == m` e o mesmo para `RefreshParameters` (inclusive após `json.dumps`/
  `json.loads`); `preregistration_ref` de topo divergente e chave a mais
  erguem `ValueError`; `from_stored`: tabela com `0` no manifesto e `[]` nas
  linhas → tabela vazia; tabela listada ausente em `rows_by_table`, contagem
  divergente, linha fora de ordem e linha de outra partição → 
  `GoldGenerationCorruptError`; `BLOCKED` volta com o status; a chave de cada
  tabela é a do schema. Schema: cinco tabelas, `key` ⊆ colunas escritas pelo
  builder correspondente, `read_columns` ⊆ colunas escritas (contrato dos
  builders, cada perna); os testes existentes dos builders e dos DTOs verdes
  sem alteração; nenhum `_KEY` sobra em `gold_builders/`.
- **Tokens:** `gold/test_refresh_gold_dtos.py`: `schema_tables_complete`,
  `parameters_from_mapping_round_trip`, `manifest_from_mapping_round_trip`,
  `manifest_prereg_ref_divergent_rejected`, `manifest_unknown_key_rejected`,
  `from_stored_empty_table`, `from_stored_missing_table_corrupt`,
  `from_stored_count_mismatch_corrupt`, `from_stored_incoherent_corrupt`,
  `from_stored_blocked_returned`, `from_stored_uses_schema_keys`;
  `test_gold_builder_contract.py`: `builders_use_schema_keys`,
  `schema_columns_written`.
- **Verificação (T1) — Container:**
  ```bash
  B=src/financial_forecasting/features/evaluation/adapters/out/duckdb/gold_builders
  uv run pytest tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py tests/contract/features/evaluation/test_gold_builder_contract.py tests/contract/features/evaluation/test_gold_store_contract.py tests/integration/features/evaluation/test_refresh_gold.py -v
  test -d "$B"
  k=$(mktemp)
  grep -rn "_KEY\|f\"gold_" "$B" > "$k" || true
  if test -s "$k"; then cat "$k"; echo "FAIL: chave ou nome privado remanescente nos builders"; exit 1; fi
  d=$(mktemp)
  base=$(git merge-base origin/develop HEAD)
  git diff "$base" -- tests/unit/features/evaluation/gold/test_refresh_gold_dtos.py tests/contract/features/evaluation/test_gold_builder_contract.py > "$d"
  test -s "$d"
  if grep -nE '^-([^-]|$)' "$d"; then echo "FAIL: teste existente da 6.4 alterado"; exit 1; fi
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): dono do schema do gold e montagem única da geração lida [6.5/task-05]`

---

### Task 06 — Port `PreregistrationSource` + `InMemoryPreregistrationSource` + `TomlPreregistrationSource` + contrato `[fake, real]`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/preregistration_source.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/toml/__init__.py`
  - `src/financial_forecasting/features/evaluation/adapters/out/toml/toml_preregistration_source.py`
  - `tests/fakes/features/evaluation/in_memory_preregistration_source.py`
  - `tests/contract/features/evaluation/test_preregistration_source_contract.py`
- **Arquivos a modificar:** nenhum (o contrato usa `valid_payload`/`to_toml`
  da Task 02).
- **O que fazer (concept §4 "Application"/"Adapters", §8 "Externas", C2; ADR
  6.5.0003 itens 2–3):**
  - Port: `PreregistrationSource(Protocol)` com `read(self, *, name: str,
    revision: int) -> PreregistrationRecord`; `PreregistrationRecord`,
    `PreregistrationAnchor`, `PreregistrationNotFoundError` (decisão do §1).
  - Real `TomlPreregistrationSource(root: Path)` (docstring: satisfaz o port
    `PreregistrationSource`): lê `<root>/<name>-r<revision>.toml` com
    `tomllib.loads(path.read_text(encoding="utf-8"))` (ausente →
    `PreregistrationNotFoundError`; TOML inválido → `ValueError` com o caminho);
    lê `<root>/<name>-r<revision>.anchor.toml` se existir, com exatamente as
    chaves `tag`, `commit`, `comment_url`, `anchored_at` (a mais/a menos →
    `ValueError`) → `PreregistrationAnchor`; devolve o payload **sem** validar
    o plano (o VO valida). `validate_path_identifier` em `name` antes de montar
    o caminho; `revision` `int` não-`bool` ≥ 0.
  - Fake `InMemoryPreregistrationSource`: `add(name, revision, payload,
    anchor=None)`; `read` devolve cópia profunda do payload; ausente → o mesmo
    erro; `reads` conta as chamadas (usado pela Task 10).
  - Contrato: *harness* por perna (`fake`; `toml` num `tmp_path` com o
    `PAYLOAD_TOML` e o `.anchor.toml` gravados por `to_toml` — nenhum TOML
    escrito à mão; o caso sem fuso usa um `datetime` ingênuo), ids `["fake",
    "toml"]`, sem `skipif`.
- **Critério de aceite (A9, C2):** nas duas pernas: o payload lido é igual ao
  `valid_payload()`; revisão inexistente → `PreregistrationNotFoundError`;
  sem âncora → `anchor is None`; com âncora → `PreregistrationAnchor` com
  `anchored_at` com fuso UTC; âncora com data sem fuso → `ValueError`.
  Só-do-real: âncora com chave a mais → `ValueError`; TOML malformado →
  `ValueError` com o nome do arquivo; `name` com `/` ergue antes de tocar o
  disco. `check_port_coverage --list`: `PreregistrationSource` com fake,
  `TomlPreregistrationSource` e o contrato; baseline intocado.
- **Tokens:** `test_preregistration_source_contract.py`:
  `source_reads_payload`, `source_missing_revision_raises`,
  `source_anchor_absent_none`, `source_anchor_present_parsed`,
  `source_anchor_naive_rejected`, `real_anchor_extra_key_rejected`,
  `real_malformed_toml_raises`, `real_name_identifier_checked`.
- **Verificação (T1) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_preregistration_source_contract.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  grep -q "\[fake" "$f"
  grep -q "\[toml" "$f"
  l=$(mktemp)
  uv run python scripts/check_port_coverage.py --list > "$l"
  test -s "$l"
  grep -q "TomlPreregistrationSource" "$l"
  uv run python scripts/check_fake_parity.py
  make check-task SLICE=evaluation
  ```
  **Host:**
  ```bash
  EV=src/financial_forecasting/features/evaluation
  t=$(mktemp)
  grep -rlE "^\s*(import|from)\s+tomllib\b" "$EV" > "$t"
  test -s "$t"
  if grep -v "/adapters/out/toml/" "$t"; then echo "FAIL: tomllib fora de adapters/out/toml"; exit 1; fi
  test -s scripts/arch_baseline.toml
  if grep -n "PreregistrationSource" scripts/arch_baseline.toml; then echo "FAIL: baseline"; exit 1; fi
  ```
- **Commit sugerido:** `feat(evaluation): port PreregistrationSource com adapter TOML, fake e contrato [6.5/task-06]`

---

### Task 07 — Port `GoldGenerationReader` + `InMemoryGoldGenerationReader` + `ParquetGoldStore.read_generation` + contrato `[fake, real]`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/ports/out/gold_generation_reader.py`
  - `tests/fakes/features/evaluation/in_memory_gold_generation_reader.py`
  - `tests/contract/features/evaluation/test_gold_generation_reader_contract.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/adapters/out/duckdb/parquet_gold_store.py`
  - `tests/architecture/test_port_coverage_gate.py` — piso 26 → 28 e um caso
    que resolve os dois ports novos (real e contrato).
- **O que fazer (concept §4, D5, I7, C6; ADR 6.5.0005 itens 1, 4, 5):**
  - Port: `GoldGenerationReader(Protocol)` com `read_generation(self, *,
    partition: GoldPartition) -> GoldGeneration`; reexporta
    `GoldManifestNotFoundError`/`GoldGenerationCorruptError` (`__all__`).
  - Real: `ParquetGoldStore.read_generation` (docstring do módulo e do método
    cita `GoldGenerationReader`): `current_dir(partition)`; sem
    `MANIFEST.json` → `GoldManifestNotFoundError`; lê o manifesto
    (`json.loads`) **antes** de qualquer tabela; para cada tabela de
    `rows_by_table`: arquivo ausente → `GoldGenerationCorruptError`; 0 linhas →
    `[]`; senão `pq.read_table(path, partitioning=None).to_pylist()` (função
    privada `_read_rows`); chama `GoldGeneration.from_stored` — nenhuma
    montagem própria.
  - Fake: `InMemoryGoldGenerationReader(store: InMemoryGoldStore)` —
    `read_generation` pega `store.current(partition)` (ausente →
    `GoldManifestNotFoundError`) e chama `GoldGeneration.from_stored`.
  - Contrato: *harness* por perna (`fake` sobre `InMemoryGoldStore`,
    `parquet` sobre `ParquetGoldStore` num `tmp_path`): publica e lê de volta;
    ids `["fake", "parquet"]`, sem `skipif`.
- **Critério de aceite (A9, I7, C6):** nas duas pernas: ida e volta `publish`
  → `read_generation` com manifesto e linhas iguais; tabela de zero linhas
  volta vazia; coluna toda `None` volta `None`; geração `BLOCKED` volta com o
  status; partição sem geração → `GoldManifestNotFoundError`. Só-do-real: as
  colunas `asset`/`parent_sweep_id` voltam como `str` do conteúdo (sem
  inferência hive; o caminho tem `asset=`/`parent_sweep_id=`); arquivo de
  tabela apagado → corrupt; `MANIFEST.json` com contagem adulterada → corrupt;
  espião: o manifesto é lido antes do primeiro `_read_rows`; espião em
  `GoldGeneration.from_stored` chamado uma vez. `check_port_coverage` verde sem
  entrada nova; `test_port_coverage_gate.py` com piso 28 e o caso novo.
- **Tokens:** `test_gold_generation_reader_contract.py`:
  `reader_round_trip_equal`, `reader_zero_row_table`, `reader_all_none_column`,
  `reader_blocked_returned`, `reader_missing_manifest_raises`,
  `real_no_hive_inference`, `real_missing_table_file_corrupt`,
  `real_count_mismatch_corrupt`, `real_reads_manifest_first`,
  `real_single_assembly`; `tests/architecture/test_port_coverage_gate.py`:
  `scorecard_ports_resolve`.
- **Verificação (T3) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/contract/features/evaluation/test_gold_generation_reader_contract.py tests/contract/features/evaluation/test_gold_store_contract.py -v -rs | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  grep -q "\[fake" "$f"
  grep -q "\[parquet" "$f"
  uv run pytest tests/architecture/test_port_coverage_gate.py -v
  l=$(mktemp)
  uv run python scripts/check_port_coverage.py --list > "$l"
  test -s "$l"
  grep -q "GoldGenerationReader" "$l"
  uv run python scripts/check_fake_parity.py
  make check
  ```
  **Host:**
  ```bash
  test -s scripts/arch_baseline.toml
  if grep -nE "GoldGenerationReader|PreregistrationSource" scripts/arch_baseline.toml; then echo "FAIL: baseline"; exit 1; fi
  test -s tests/architecture/test_port_coverage_gate.py
  grep -q ">= 28" tests/architecture/test_port_coverage_gate.py
  ```
- **Commit sugerido:** `feat(evaluation): port GoldGenerationReader lendo o manifesto primeiro [6.5/task-07]`

> **Checkpoint C (T2) após esta Task:** coberto pelo `make check` da própria
> Task + revisão independente do bloco 05–07.

---

### Task 08 — `refresh_command_from` + mapeador linhas → evidência com a conferência do gold

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
  - `src/financial_forecasting/features/evaluation/application/use_cases/scorecard_evidence.py`
  - `tests/unit/features/evaluation/_scorecard_factory.py`
  - `tests/unit/features/evaluation/test_refresh_command_from.py`
  - `tests/unit/features/evaluation/test_scorecard_evidence_mapper.py`
- **Arquivos a modificar:** nenhum.
- **O que fazer (concept §4, D4, I6, I8, I10, C6, C8; ADRs 6.5.0004 itens 3,
  5, 6.5.0006 itens 1, 6):**
  - `dtos/confirmatory_scorecard.py`: `refresh_command_from(prereg:
    Preregistration, reference: str) -> RefreshGoldCommand` (decisão "Ordem
    das tuplas derivadas" do §1; `asset`, `parent_sweep_id =
    cohort.cohort_id`, `horizons`, `window_deficits`, `dataset_fingerprint =
    realized.dataset_fingerprint`, `RefreshParameters` inteiro);
    `BuildConfirmatoryScorecardCommand(name, revision, preregistration_ref)` —
    **sem** partição; os **cinco erros** do scorecard (decisão do §1):
    `PreregistrationHashMismatchError`, `PreregistrationChainError`,
    `PreregistrationNotAnchoredError`, `PreregistrationMismatchError` (campo no
    atributo `field` e na mensagem) e `GoldNotReadyError` (`failed_checks:
    tuple[FailedCheck, ...]`).
  - **Nomes de `field` fixados** (o e2e depende de `"preregistration_ref"` e
    `"seeds"`; Checkpoint B r2, item 2): manifesto → `"partition"`,
    `"preregistration_ref"`, `"parameters"`, `"horizons"`, `"window_deficits"`,
    `"dataset_fingerprint"`; conjuntos → `"models"`, `"seeds"`,
    `"quantile_levels"`; MCS → `"mcs.statistic"`, `"mcs.block_rule"`.
    Constantes públicas no módulo de DTOs (`MismatchField(StrEnum)`), usadas
    pelo mapeador e pelos testes.
  - `use_cases/scorecard_evidence.py`: `evidence_from_generation(*, prereg, command: RefreshGoldCommand,
    generation: GoldGeneration) -> tuple[HorizonEvidence, ...]`, na ordem de
    C6/C8 do concept: (1) manifesto × comando — `partition`,
    `preregistration_ref`, `parameters` (`as_mapping`), `horizons`,
    `window_deficits`, `dataset_fingerprint`; (2) conjuntos por tabela —
    modelos em `gold_dm_results` (candidato + comparadores do plano), em
    `gold_mcs_results` (os sete), nas linhas de calibração (os sete); seeds por
    modelo em `gold_metrics_by_run` e `gold_calibration_table` (`seedless` ↔
    `{None}`); níveis da grade (os `level_low` das linhas `pinball` de
    `gold_metrics_by_run`) = `quantile_levels`; (3) MCS — `statistic` =
    `MCS_STATISTIC` do plano e `block_size = block_length_rule(horizon=h,
    max_estimate=max_block_estimate)` por linha (`max_block_estimate` `None`
    num gold `COMPLETED` → `GoldGenerationCorruptError`, decisão do §1); (4)
    só então: linha `ERROR` + `FAIL` em `gold_quality_checks` de um gold
    `COMPLETED` → `GoldGenerationCorruptError`; linhas esperadas
    por modelo/seed presentes (duas caudas do gate em `model_full` mascarado e
    em `common`, lidas **só** nas linhas `band_level == gate_band_level`, DGT 0..h−1 quando h > 1, um DM por comparador e estimador, um
    MCS por esquema e modelo, a linha `pinball_grid_mean` da amostra comum por
    modelo/seed) → `GoldGenerationCorruptError` nomeando a linha; (5) monta
    `HorizonEvidence` (T da decisão do §1; P̄_G do candidato = média entre seeds
    por `SeedSpread`). Colunas lidas só por `GoldTableSchema.read_columns`/
    `key`; nenhum serviço da 6.1–6.3 chamado além de `block_length_rule` e
    `MCS_STATISTIC`.
  - `_scorecard_factory.py` (stdlib + DTOs + domínio; gate de pureza):
    `make_generation(prereg, *, h1_counts=..., dm=..., mcs=..., checks=...,
    status=...) -> GoldGeneration` gera as linhas das cinco tabelas **coerentes
    com o plano** (via `GoldTable.sorted_by_key` com as chaves do schema e o
    manifesto do `refresh_command_from`), com mutadores (`drop_rows`,
    `add_seed`, `set_cell`) para cada teste aplicar uma violação só.
- **Critério de aceite (A3, A8 parcial, I6, I10, C6, C8):** um caso por campo
  do comando igual ao do plano (parametrizado); partição = `(asset,
  cohort_id)`; `BuildConfirmatoryScorecardCommand` não tem campo de partição.
  Mapeador: `PreregistrationMismatchError` para cada campo do manifesto
  alterado (partição inclusive; parametrizado), modelo a mais e a menos em DM,
  MCS e calibração, seed ausente e a mais em cada tabela, nível de grade
  diferente, `statistic` diferente e `block_size` fora da regra — cada caso
  **afirma o `field`** exato da lista acima (`error.field ==
  MismatchField.SEEDS`, etc.);
  `GoldGenerationCorruptError` para seed presente sem uma cauda, modelo sem a
  linha de um horizonte, comparador sem a linha de um estimador, esquema sem
  MCS num horizonte, `n_points` divergente no DM de um horizonte,
  `max_block_estimate` `None` e linha `ERROR` + `FAIL` num gold `COMPLETED`;
  com contagens diferentes nas linhas 0,95 e 0,975 da mesma série, a evidência
  do gate traz as de 0,975; com seed a
  mais **e** cauda faltando ao mesmo tempo, ergue o mismatch; gold coerente →
  um `HorizonEvidence` por horizonte do plano, com as contagens por seed e o
  T do DM; o mapeador lê só colunas do schema (monkeypatch de um
  `read_columns` sem a coluna faz o mapeador errar com `KeyError`).
- **Tokens:** `test_refresh_command_from.py`: `command_field_from_plan`,
  `command_partition_from_cohort`, `command_parameters_from_plan`,
  `command_tuple_order`, `scorecard_command_without_partition`;
  `test_scorecard_evidence_mapper.py`: `mismatch_manifest_field`,
  `mismatch_model_extra_missing`, `mismatch_seed_extra_missing`,
  `mismatch_grid_levels`, `mismatch_mcs_statistic`, `mismatch_block_rule`,
  `corrupt_seed_missing_tail`, `corrupt_horizon_row_missing`,
  `corrupt_estimator_row_missing`, `corrupt_scheme_row_missing`,
  `corrupt_common_points_divergent`, `mismatch_before_corrupt`,
  `evidence_built_per_horizon`, `mapper_reads_schema_columns`,
  `mapper_gate_rows_band_level`, `corrupt_block_estimate_missing`,
  `corrupt_completed_with_failed_check`.
- **Verificação (T1) — Container:**
  ```bash
  U=tests/unit/features/evaluation
  uv run pytest $U/test_refresh_command_from.py $U/test_scorecard_evidence_mapper.py -v
  make check-task SLICE=evaluation
  ```
  **Host:**
  ```bash
  M=src/financial_forecasting/features/evaluation/application/use_cases/scorecard_evidence.py
  test -s "$M"
  if grep -nE "DieboldMariano|HolmCorrection|ModelConfidenceSet|CoverageMetrics|HitSequences|WilsonBand" "$M"; then echo "FAIL: recomputação no mapeador"; exit 1; fi
  ```
- **Commit sugerido:** `feat(evaluation): comando do refresh derivado do plano e gold conferido [6.5/task-08]`

---

### Task 09 — Quantil da t, IC do efeito do DM e perfil do scorecard

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/scorecard_profile.py`
  - `tests/unit/features/evaluation/test_scorecard_profile.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/domain/services/student_t.py`
    — `student_t_quantile(p: float, df: float) -> float` (decisão do §1).
  - `tests/unit/features/evaluation/test_student_t.py` — **só acréscimos**.
  - `src/financial_forecasting/features/evaluation/domain/services/diebold_mariano.py`
    — `dm_effect_interval` (decisão do §1).
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
    — `ScorecardProfile` e os DTOs das suas linhas.
  - `tests/unit/features/evaluation/test_dm_vs_r_oracle.py` — **só acréscimos**.
- **O que fazer (concept §4, D8, I8, I10, I12; ADRs 6.5.0006 itens 4, 6, 7,
  6.5.0007 itens 4–5, 6.5.0008 item 2):**
  - `student_t_quantile(p, df)` e `dm_effect_interval(*, mean_differential,
    statistic, n_points, level)` (o IC usa o quantil).
  - `ScorecardProfile` (frozen DTO, `as_mapping()` JSON-safe): por horizonte —
    `gate_sensitivities` (copiadas do `H1Result`: LR_uc, DGT, amostra comum,
    média das taxas, divergências), `power` (idem), `tiers` (de
    `tier_readings`), `dm` por comparador e estimador (`mean_differential`,
    `statistic`, `adjusted_p_value`, `rejected`, `fallback_applied`, IC do
    efeito a 95 %), `bartlett_divergences` (comparadores em que o `rejected` do
    Bartlett difere do retangular), `mcs_moving_block_divergence` (inclusão do
    candidato difere do estacionário), `comparators_calibration` (bandas do
    gate com S = 1 por `H1Gate.tail_bands` sobre as contagens do gold — **não**
    filtra nada — e
    degeneração média acima do limiar), `calibration_95` e
    `independence_fractions` (decisão "Descritores do perfil" do §1),
    `without_gaps` (as linhas `includes_degenerate = true` das caudas do gate),
    `descriptors` (`SeedSpread` por métrica), `lowest_mean_pinball`.
    `declared_not_built`: os identificadores de `ProfileSpec.declared` que esta
    Stage não constrói (os de séries novas, #129; `sharpness_diagram`, 8.3).
  - `use_cases/scorecard_profile.py`: `build_profile(*, prereg, evidence,
    verdict, generation) -> ScorecardProfile` — só copia colunas do gold (pelo
    schema), chama `H1Gate`/`tier_readings`/`dm_effect_interval`/`SeedSpread`
    e nunca é lido por `decide`.
- **Critério de aceite (A7, I8, I10):** `student_t_quantile`: ida e volta
  com `student_t_cdf` (|cdf(q) − p| ≤ 1e-12) em p ∈ {0,025; 0,5; 0,975} e
  df ∈ {1; 10; 1 511}; valores publicados t_{0,975}: df = 1 →
  12,706204736174705, df = 10 → 2,2281388519649385, df = 30 →
  2,0422724563012373 (tolerância 1e-9); p fora de (0, 1), df < 1 erguem.
  Perfil: desfecho por nível (naive, estatístico
  forte, ML) com um caso em que o candidato supera os naive e o ML mas não um
  estatístico forte; IC do efeito igual a d̄ ± t_{T−1,0,975}·|d̄/estatística|
  com o `student_t_quantile` (tolerância 1e-12) e `None` para estatística 0;
  `fallback_applied` copiado; comparador com degeneração média 0,02 marcado
  acima do limiar e presente nas leituras; bandas a 95 % e frações de seeds;
  gate na amostra comum e "sem lacunas" presentes; divergência Bartlett ×
  retangular e moving-block × estacionário listadas; spread por seed; menor
  P̄_G; os valores copiados são idênticos às células do gold (sem cálculo);
  `declared_not_built` lista exatamente os perfis fora da 6.5.
- **Tokens:** `test_student_t.py`: `t_quantile_round_trip`,
  `t_quantile_published_values`, `t_quantile_invalid_rejected`;
  `test_dm_vs_r_oracle.py`: `dm_effect_interval_formula`,
  `dm_effect_undefined_zero_statistic`; `test_scorecard_profile.py`:
  `profile_tier_outcomes`, `profile_dm_effect_ci`, `profile_fallback_applied`,
  `profile_comparators_threshold`, `profile_band_95_fractions`,
  `profile_common_sample_gate`, `profile_without_gaps_rows`,
  `profile_bartlett_divergence`, `profile_moving_block_divergence`,
  `profile_seed_spread`, `profile_lowest_pinball`, `profile_copies_gold_values`,
  `profile_declared_not_built`.
- **Verificação (T1) — Container:**
  ```bash
  U=tests/unit/features/evaluation
  uv run pytest $U/test_scorecard_profile.py $U/test_dm_vs_r_oracle.py $U/test_student_t.py -v
  d=$(mktemp)
  base=$(git merge-base origin/develop HEAD)
  git diff "$base" -- $U/test_dm_vs_r_oracle.py $U/test_student_t.py > "$d"
  test -s "$d"
  if grep -nE '^-([^-]|$)' "$d"; then echo "FAIL: teste existente do DM ou da t alterado"; exit 1; fi
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): perfil do scorecard com IC do efeito do DM e quantil da t [6.5/task-09]`

---

### Task 10 — Use case `BuildConfirmatoryScorecard` + `ScorecardResult`

- **Arquivos a criar:**
  - `src/financial_forecasting/features/evaluation/application/use_cases/build_confirmatory_scorecard.py`
  - `tests/unit/features/evaluation/test_build_confirmatory_scorecard_use_case.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/features/evaluation/application/dtos/confirmatory_scorecard.py`
    — `ReadinessReason(StrEnum)` e `ScorecardResult`.
- **O que fazer (concept §4, I5, I6, I12, I13, C2–C5, C7, C10, C11; ADRs
  6.5.0002 item 4, 6.5.0003 item 3, 6.5.0007 item 8):**
  - Os cinco erros já existem em `dtos/confirmatory_scorecard.py` (Task 08);
    o use case os importa de lá (sem reexportação). `GoldNotReadyError` recebe
    os `FailedCheck` das linhas `ERROR` + `FAIL` de `gold_quality_checks`.
  - `BuildConfirmatoryScorecard(*, source: PreregistrationSource, reader:
    GoldGenerationReader, hasher: Hasher)`; `__call__(command) ->
    ScorecardResult`, na ordem I5: (1) lê as revisões 0..r do `name` e monta
    cada `Preregistration` (C1/C2 propagam); cadeia — `name`/`revision` do
    payload iguais aos pedidos, r0 sem emenda, r ≥ 1 com `amends` =
    `reference(hash(r−1))` → `PreregistrationChainError`; (2) referência da
    revisão julgada ≠ `command.preregistration_ref` →
    `PreregistrationHashMismatchError`; (3) toda revisão com âncora → senão
    `PreregistrationNotAnchoredError`; (4) `refresh_command_from` →
    `reader.read_generation(partition=derived.partition)`; (5) `BLOCKED` →
    `GoldNotReadyError`; (6) `evidence_from_generation`; (7)
    `ConfirmatoryScorecard.decide`; (8) `build_profile`; (9) prontidão — razões
    `REQUIRED_CHECK_SKIPPED` (linha `SKIPPED` de `DEGENERACY_CHECK`,
    `ALIGNMENT_CHECK` ou `STATISTICAL_PRECONDITIONS`), `GOLD_BEFORE_ANCHOR`
    (`manifest.started_at < anchor.anchored_at` da revisão julgada; igualdade é
    pronta — ADR 6.5.0007 item 8 "≥"), `AMENDED_AFTER_UNBLINDING` (alguma
    revisão `unblinded`); `academic_decision_ready = not reasons`. Não há razão
    "check exigido falhou": `ERROR` + `FAIL` só existe em gold `BLOCKED` (passo
    5) ou corrompido (mapeador, Task 08) — decisão do §1 (Checkpoint B r1,
    T-F4).
  - `ScorecardResult` (frozen): `preregistration_ref`, `revision_chain`
    (referências r0..r), `anchor`, `blinding_statement`, `manifest_read`
    (`GoldManifest`), `verdict`, `profile`, `academic_decision_ready`,
    `readiness_reasons`; `as_mapping()` — serialização única, JSON-safe
    (datetimes ISO, enums pelo valor).
- **Critério de aceite (A6, A8, I5, I12, I13, C2–C5, C7, C10, C11):** com
  `InMemoryPreregistrationSource` + `InMemoryGoldGenerationReader` e o dublê
  de hasher: hash divergente, cadeia quebrada (r1 com `amends` errado; payload
  com `revision` diferente do arquivo) e revisão sem âncora erguem **sem**
  chamar o leitor (espião); com as três falhas, ergue a de cadeia (ordem); o
  leitor recebe a partição derivada; `BLOCKED` → `GoldNotReadyError` com os
  checks; revisão inexistente propaga `PreregistrationNotFoundError`; exceção
  genérica do leitor propaga; prontidão falsa com a razão exata para gold
  anterior à âncora, emenda `unblinded` e check exigido `SKIPPED`; verdadeira
  com `started_at == anchored_at`; verdadeira com H1 reprovado em todos os horizontes (refutação pronta);
  `blinding_statement` ecoado e sem efeito na prontidão; `revision_chain` de
  r1 lista r0 e r1; o veredito é idêntico com `build_profile` trocado por um
  que devolve outro perfil; `json.dumps(result.as_mapping())` funciona.
- **Tokens:** `test_build_confirmatory_scorecard_use_case.py`:
  `hash_mismatch_before_reader`, `chain_broken_before_reader`,
  `unanchored_before_reader`, `validation_order_chain_hash_anchor`,
  `reader_reads_derived_partition`, `command_has_no_partition`,
  `blocked_gold_not_ready`, `not_found_propagates`,
  `programming_error_propagates`, `ready_false_gold_before_anchor`,
  `ready_false_unblinded_amendment`, `ready_false_required_check_skipped`,
  `ready_true_refutation`, `ready_true_started_at_anchor`,
  `blinding_echoed_not_conjoined`,
  `chain_listed_in_result`, `verdict_unchanged_by_profile`,
  `result_mapping_json_safe`.
- **Verificação (T1) — Container:**
  ```bash
  uv run pytest tests/unit/features/evaluation/test_build_confirmatory_scorecard_use_case.py -v
  make check-task SLICE=evaluation
  ```
- **Commit sugerido:** `feat(evaluation): use case BuildConfirmatoryScorecard com validação e prontidão [6.5/task-10]`

> **Checkpoint C (T2) após esta Task:** `make check-block` + revisão
> independente do bloco 08–10.

---

### Task 11 — Wiring no `composition_root` + e2e sobre silver sintético

- **Arquivos a criar:**
  - `tests/integration/features/evaluation/test_build_confirmatory_scorecard.py`
- **Arquivos a modificar:**
  - `src/financial_forecasting/composition_root.py`
  - `tests/unit/shared/test_composition_root.py` — **só acréscimos**
- **O que fazer (concept §8 "Internas", §11 E2E, A10; ADR 6.5.0005):**
  - `composition_root`: uma instância `gold_store = ParquetGoldStore(cfg.
    data_root)` usada pelo `RefreshGold` (como `GoldStore`) e pelo scorecard
    (como `GoldGenerationReader`); `build_confirmatory_scorecard:
    BuildConfirmatoryScorecard` em `ApplicationDependencies`, com
    `TomlPreregistrationSource(root=cfg.repo_root / "config" /
    "preregistration")` e o `hasher` já wirado.
  - `test_build_confirmatory_scorecard.py` (`pytestmark =
    pytest.mark.integration`), fixture de módulo com o cenário inteiro num
    único `tmp_path` (`Settings(_env_file=None, data_root=<tmp>/data,
    repo_root=<tmp>, artifacts_root=<tmp>/art)` — sem `.env` do checkout; o
    teste afirma que `cfg.data_root`, `cfg.repo_root` e `cfg.artifacts_root`
    estão **todos** sob `tmp_path` antes de qualquer escrita; Checkpoint B r2,
    item 3): plano
    de teste (`valid_payload()` com horizontes (1, 2), candidato com seeds
    `[1, 2]`, os seis comparadores, `cohort_id = "e2e-cohort"`, fingerprint do
    dataset sintético, montado por `with_leaf`) gravado por `to_toml` em
    `<tmp>/config/preregistration/`, com âncora (`to_toml` também) de
    `anchored_at = 2020-01-01T00:00:00Z` e o `preregistration_ref` calculado com
    o `CanonicalJsonHasher`; silver sintético (≈ 120 sessões de teste, 2 folds)
    gravado pelo `ParquetAnalyticsRepository` real e dataset com as colunas de
    `modeling_columns()` (padrão da 6.4 Task 15); **hits determinísticos por
    construção**: o candidato emite os quantis de um gerador conhecido e o
    realizado do ponto i fica abaixo do q0,10 quando `i % 20 ∈ {0, 11}` e acima
    do q0,90 quando `i % 20 ∈ {5, 16}` — 10 % por cauda, e cada paridade (as
    duas sub-séries DGT de h = 2) recebe uma violação de cada cauda a cada 20
    pontos, então a nominal fica dentro das bandas em toda amostra e sub-série
    (Checkpoint B r1, T-F10); comparadores com viés grande (perda muito maior)
    → DM rejeita contra todos. Sequência: `deps.refresh_gold(
    refresh_command_from(prereg, ref))` → `COMPLETED`;
    `deps.build_confirmatory_scorecard(command)` → veredito esperado
    `BEATS_NAIVE_AND_STRONG` com `primary_winner = "tft_quantile"` nos dois
    horizontes, `academic_decision_ready is True`, razões vazias. Casos de
    recusa (Checkpoint B r1, T-F1/A1 — o `preregistration_ref` mascara os
    demais campos, decisão do §1): (a) **plano alterado** — arquivo próprio,
    ancorado, com `mcs.seed` diferente e o **mesmo** cohort, julgando o gold do
    passo acima → `PreregistrationMismatchError` com `field ==
    "preregistration_ref"`; (b) **seed a mais no silver** (opção (b) da sessão
    mestra) — plano B (arquivo próprio, ancorado, `cohort_id =
    "e2e-cohort-extra-seed"`, candidato com seeds `[1, 2]`) e silver desse
    cohort escrito com o candidato nas seeds `{1, 2, 3}`; roda-se antes o
    `deps.refresh_gold(refresh_command_from(plano_B, ref_B))` → `COMPLETED`
    (o refresh não filtra seeds), e o scorecard do plano B →
    `PreregistrationMismatchError` com `field == "seeds"` (manifesto igual ao
    comando derivado; conjunto de seeds do gold ≠ do plano).
- **Critério de aceite (A10):** os testes acima verdes, zero `SKIPPED`;
  `test_composition_root.py`: o use case wirado com `TomlPreregistrationSource`
  na raiz `repo_root/config/preregistration` e o **mesmo** objeto
  `ParquetGoldStore` do `RefreshGold`.
- **Tokens:** `test_build_confirmatory_scorecard.py`:
  `e2e_scorecard_expected_verdict`, `e2e_ready_after_anchor`,
  `e2e_parameter_changed_mismatch`, `e2e_extra_seed_mismatch`,
  `e2e_result_mapping_serializable`, `e2e_paths_under_tmp`;
  `tests/unit/shared/test_composition_root.py`:
  `wires_build_confirmatory_scorecard`, `scorecard_shares_gold_store`.
- **Verificação (T1 = `check-block`, toca o composition root) — Container:**
  ```bash
  f=$(mktemp)
  uv run pytest tests/integration/features/evaluation/test_build_confirmatory_scorecard.py tests/unit/shared/test_composition_root.py -v -rs --durations=5 | tee "$f"
  test -s "$f"
  if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED"; exit 1; fi
  make check-block
  ```
  **Host:**
  ```bash
  E=tests/integration/features/evaluation/test_build_confirmatory_scorecard.py
  test -s "$E"
  if grep -nE "cohorts|aapl_confirmatory-r0|Settings\(\)" "$E"; then echo "FAIL: e2e toca o cohort real ou usa Settings() sem raiz"; exit 1; fi
  ```
- **Commit sugerido:** `feat(evaluation): BuildConfirmatoryScorecard no composition root e e2e sintético [6.5/task-11]`

---

### Task 12 — Roadmap §Stage 6.5, 8.1 (#129) e 8.2 (D10)

- **Arquivos a modificar:**
  - `docs/roadmap.md`
- **Arquivos a criar:** nenhum.
- **Antes de começar (Host):** `git fetch origin && git rebase origin/develop`
  (GIT-WORKFLOW Etapa 4); conflito resolvido mantendo as duas edições, com
  `[deviation]` em §7 se algo mudar de lugar; rodar de novo o T1 da Task 11
  depois do rebase se algo além de docs entrou.
- **O que fazer (concept D10; pedido da sessão mestra — #129):**
  - `#### Stage 6.5`: descrição humana ("`academic_decision_ready` só
    verdadeiro com todos os gates de validade satisfeitos"; scorecard emitido
    como resultado e gravado pela 8.1); DoD reescrito com a frase do concept
    D10; `camada_alvo: multi (domain + application + adapters/out)`;
    `arquivos_a_criar` sem `domain/services/preregistration.py`, com
    `domain/value_objects/preregistration.py`,
    `domain/value_objects/scorecard_evidence.py`,
    `shared/domain/value_objects/preregistration_hash.py`,
    `domain/services/h1_gate.py`, `domain/services/h1_gate_power.py`,
    `domain/services/confirmatory_scorecard.py`,
    `application/ports/out/preregistration_source.py`,
    `application/ports/out/gold_generation_reader.py`,
    `application/dtos/gold_schema.py`, `application/dtos/confirmatory_scorecard.py`,
    `application/use_cases/scorecard_evidence.py`,
    `application/use_cases/scorecard_profile.py`,
    `application/use_cases/build_confirmatory_scorecard.py`,
    `adapters/out/toml/toml_preregistration_source.py`,
    `config/preregistration/aapl_confirmatory-r0.toml`,
    `config/preregistration/aapl_confirmatory-r0.anchor.toml`,
    `docs/preregistration/aapl_confirmatory.md`, os dois fakes, os dois
    contratos, o e2e e o teste de consistência; `arquivos_a_modificar`:
    `application/dtos/refresh_gold.py`, `parquet_gold_store.py`, os cinco
    builders, `model_confidence_set.py`, `christoffersen_test.py`,
    `student_t.py`, `diebold_mariano.py`, `composition_root.py`,
    `docs/LAYOUT.md`, `tests/architecture/test_port_coverage_gate.py`;
    `contratos_introduzidos`: `Preregistration`, `PreregistrationHash`,
    `TailDeviation`, VOs de evidência (value-objects), `H1Gate`,
    `H1GatePower`, `ConfirmatoryScorecard` (domain-services),
    `PreregistrationSource`, `GoldGenerationReader` (ports-out),
    `BuildConfirmatoryScorecard` (use case); `contratos_consumidos`: sai a
    lista de 6.1–6.3 como recomputação; entram "tabelas gold + manifesto (6.4)
    via `GoldGenerationReader`", `RefreshParameters`/`GoldManifest`/
    `check_generation` (6.4), `WilsonBand`, `lr_uc_three_state`,
    `chi_square_sf` (6.3, sobre contagens médias), `Hasher` (1.4), cohort r0
    por referência (5.5). A nota "Leitura do gold (nota da 6.4)" passa a
    apontar o `GoldGenerationReader`.
  - Tabela de Stages: linha da 6.5 com `multi (domain + application +
    adapters/out)`; linha da 8.1 com `Depende de` = `6.5, 7.1, 7.2, #129`.
  - `#### Stage 8.1`: depende também da **issue #129** (perfis de séries novas,
    antes da 8.1) e dos pré-registros de H3 (7.3) e do CQR (7.2); grava o
    `ScorecardResult` fora de `current/` (`scorecard/<preregistration_ref>/`,
    como `gold_model_comparison_confirmatory_scorecard`); o primeiro refresh
    confirmatório posta um comentário na issue (fecho da ordem, ADR 6.5.0003
    item 4); chama `refresh_command_from`.
  - `#### Stage 8.2`: `docs/preregistration/aapl_confirmatory.md` sai de
    `arquivos_a_modificar` livre — o espelho só recebe seções acrescentadas
    por revisão (ADR 6.5.0001 item 6).
- **Critério de aceite (A13):** os greps abaixo reprovam no HEAD `29c9184` (a
  seção 6.5 cita `domain/services/preregistration.py`, não tem os nomes novos;
  a 8.1 não cita `#129`) e passam depois; `make docs-check` verde.
- **Verificação (docs) — Host:**
  ```bash
  S65=$(awk '/^#### Stage 6.5/,/^### Step 7/' docs/roadmap.md); test -n "$S65"
  S81=$(awk '/^#### Stage 8.1/,/^#### Stage 8.2/' docs/roadmap.md); test -n "$S81"
  S82=$(awk '/^#### Stage 8.2/,/^#### Stage 8.3/' docs/roadmap.md); test -n "$S82"
  if grep -n "domain/services/preregistration.py" <<<"$S65"; then echo "FAIL: roadmap 6.5 ainda cita services/preregistration.py"; exit 1; fi
  for t in value_objects/preregistration.py value_objects/scorecard_evidence.py preregistration_hash.py h1_gate.py h1_gate_power.py confirmatory_scorecard.py preregistration_source.py gold_generation_reader.py gold_schema.py scorecard_profile.py build_confirmatory_scorecard.py toml_preregistration_source.py aapl_confirmatory-r0.toml aapl_confirmatory-r0.anchor.toml docs/preregistration/aapl_confirmatory.md refresh_gold.py parquet_gold_store.py composition_root.py LAYOUT.md Preregistration PreregistrationHash TailDeviation H1Gate H1GatePower ConfirmatoryScorecard PreregistrationSource GoldGenerationReader BuildConfirmatoryScorecard RefreshParameters GoldManifest check_generation lr_uc_three_state chi_square_sf academic_decision_ready "adapters/out"; do grep -qF -- "$t" <<<"$S65" || { echo "FAIL: roadmap 6.5 sem $t"; exit 1; }; done
  for t in "#129" "scorecard/" refresh_command_from "7.3" "7.2"; do grep -qF -- "$t" <<<"$S81" || { echo "FAIL: roadmap 8.1 sem $t"; exit 1; }; done
  row=$(grep -F '| `8.1-confirmatory-run`' docs/roadmap.md); test -n "$row"
  grep -qF "#129" <<<"$row" || { echo "FAIL: tabela sem #129 na 8.1"; exit 1; }
  if grep -nE "arquivos_a_modificar: \[docs/preregistration/aapl_confirmatory.md\]" <<<"$S82"; then echo "FAIL: 8.2 ainda modifica o espelho livremente"; exit 1; fi
  python scripts/check_docs_pointers.py
  ```
  **Container:**
  ```bash
  make docs-check
  ```
- **2º commit — nota de emenda no ADR 6.5.0009 (Checkpoint B r1, T-F11):**
  o ADR (`accepted`) diz, na linha do `dm_alpha`, "the H1 gate's ≤ 5 % false
  failure"; a taxa exata de reprovação falsa do gate (Wilson 97,5 % por cauda,
  calibrado, taxas 0,10/0,10) é **0,0506 em n = 1 512** e oscila entre ≈ 0,044
  e 0,053 para n em 1 400–1 600 (cálculo exato pelo algoritmo do §1; Bonferroni
  sobre bandas de Wilson não é exato). O **corpo** do ADR não muda: uma linha
  datada logo abaixo do título (`> **Nota (2026-MM-DD, Stage 6.5 Task 12):**
  "≤ 5 % false failure" é o alvo nominal do Bonferroni; a taxa exata é
  ≈ 5 % (0,0506 em n = 1 512) — ver technical 6.5 §7 `[finding]` T-F11. O valor
  `dm_alpha` = 0,05 não muda.`) e o `updated_at` do frontmatter. Nenhum texto
  da Stage (espelho, technical, comentário) afirma "≤ 5 %".
  **Host:**
  ```bash
  A=docs/adr/6_5_0009-preregistered-conventional-values.md
  test -s "$A"
  grep -q "^status: accepted" "$A"
  grep -qF "0,0506" "$A"
  d=$(mktemp)
  base=$(git merge-base origin/develop HEAD)
  git diff "$base" -- "$A" > "$d"
  test -s "$d"
  m=$(mktemp)
  grep -E '^-([^-]|$)' "$d" > "$m" || true
  if grep -v "^-updated_at:" "$m"; then echo "FAIL: corpo do ADR aceito alterado"; exit 1; fi
  python scripts/check_adr_bounded_context.py
  ```
- **Commits sugeridos:** `docs(roadmap): Stage 6.5 com pré-registro e scorecard; 8.1 depende da #129 [6.5/task-12]`;
  `docs(evaluation): nota de emenda datada no ADR 6.5.0009 sobre a falsa reprovação [6.5/task-12]`.

> **Checkpoint C (T2) bloco 4 após esta Task** (antes da espera humana):
> `make check-block`.

---

### Task 13 — Congelamento e âncora do pré-registro AAPL r0 — **BLOQUEADA (decisão humana)**

> **Entrada bloqueante (classe P, humano; concept §13, ADR 6.5.0010 P1):**
> `BLINDING_STATEMENT` = **ausente** ou **texto aprovado pelo humano**. Restrição
> já decidida: o texto não pode afirmar nem sugerir que nenhuma métrica jamais
> foi computada sobre o r0. Enquanto a resposta não chega, a Task não começa;
> nada mais na Stage depende dela salvo o gate de saída. **Nenhum refresh é
> rodado nesta Task** (nem sobre cópia): ela só escreve arquivos, calcula o
> hash do plano e publica tag + comentário. **A publicação (tag no remoto e
> comentário na #127) só acontece com a decisão humana aplicada e um go-ahead
> explícito da sessão mestra** (item 5).

- **Arquivos a criar (1º commit — congelamento):**
  - `config/preregistration/aapl_confirmatory-r0.toml`
  - `docs/preregistration/aapl_confirmatory.md`
  - `tests/integration/features/evaluation/test_preregistration_consistency.py`
- **Arquivos a criar/modificar (2º commit — registro da âncora):**
  - `config/preregistration/aapl_confirmatory-r0.anchor.toml` (novo)
  - `docs/preregistration/aapl_confirmatory.md` (seção da âncora)
  - `tests/integration/features/evaluation/test_preregistration_consistency.py`
    (caso da âncora)
  - `docs/stages/6.5-preregistration-and-scorecard/technical.md` (§7)
- **O que fazer (concept §1, D3, D9, I1, I15; ADRs 6.5.0001 itens 5–6,
  6.5.0003 itens 1–2, 4, 6.5.0004 item 4, 6.5.0009, 6.5.0010):**
  1. **Arquivo r0** com os valores do §1 "Esquema" (ADRs 6.5.0009/0010); taxas
     de locação com o `repr` de `NormalDist().cdf(-z - δ)` e
     `1 - NormalDist().cdf(z - δ)`, `z = NormalDist().inv_cdf(0.9)`, δ ∈ {0,2;
     0,1}; `blinding_statement` conforme a entrada (ausente ⇒ a chave não
     existe).
  2. **Espelho** `docs/preregistration/aapl_confirmatory.md` (frontmatter;
     "o TOML é canônico"; seção "Revisão r0" com cada valor em linguagem
     simples, o `preregistration_ref` e o hash completo; a nota do ADR 6.5.0007
     Negative sobre o tamanho condicional do gate; o poder declarado; os perfis
     declarados e onde cada um é construído — 6.5, #129, 8.3; o que a Stage
     prova sobre a ordem, nos termos do ADR 6.5.0003 item 4, **sem** afirmação
     sobre o passado do r0).
  3. **Teste de consistência** (integração: lê arquivos versionados; o `src/`
     do `evaluation` nunca lê o cohort): lê o r0 pelo `TomlPreregistrationSource`,
     monta o VO e o hash com o `CanonicalJsonHasher`; lê
     `config/cohorts/aapl_confirmatory.toml` por `cohort_file.parse` e o hash por
     `CohortHash.compute(hasher, payload=spec.hash_payload())`; confere `asset`
     = `asset_id`, `cohort_id` = `spec.cohort_id(hash)`, `cohort_hash`,
     `dataset_fingerprint`, `horizons`, `quantile_levels`, seeds do candidato =
     `spec.seeds`, `gbm_quantile` = `[gbm_params.seed]`, baselines `seedless`,
     conjunto de modelos = {`train_tft.MODEL_VERSION`,
     `train_gbm_quantile.MODEL_VERSION`} ∪ {`b.model_version` das baselines};
     os valores dos ADRs 6.5.0009/0010 (literais no teste); as taxas de
     locação recalculadas (tolerância 1e-12); todo arquivo de
     `config/preregistration/` cujo nome casa `^(?P<name>.+)-r(?P<rev>\d+)\.toml$`
     (o `.anchor.toml` **não** casa) tem o hash completo citado no espelho;
     nenhuma **frase** do TOML e do espelho é afirmação proibida. Regra
     (`CLAIM_TERMS`, no módulo do teste; Checkpoint B r2, item 1): o texto tem as
     quebras de linha simples trocadas por espaço e é cortado em frases
     (`(?<=[.!?;])\s+` ou linha em branco); uma frase é afirmação proibida se
     casa **os quatro** termos, em **qualquer ordem**, sem distinção de caixa e
     com fronteira de palavra: negação `\b(nenhuma|nenhum|nunca|jamais|never)\b`
     ou `\bno\s+metrics?\b` (o `no` sozinho é "em o" em PT e não conta);
     métrica `\b(métricas?|metrics?)\b`; cálculo `\b(comput\w*|calcul\w*)\b`;
     alvo `\b(r0|cohort|coorte)\b`. **Sem isenção** de linha que cite `6.5`:
     o espelho descreve o que a Stage fez sem esses termos juntos (ex.: "todo
     teste e o e2e da 6.5 usam dados sintéticos"). O teste
     `no_claim_about_r0_past` também roda a regra sobre frases-amostra —
     **casam**: "Nunca foi calculada nenhuma métrica sobre o r0", "The r0
     cohort has never had a metric computed on it", "No metric was ever
     computed on the cohort"; **não casam**: "A 8.1 roda o refresh no cohort e
     cada métrica é calculada sobre o cohort r0", "o perfil jamais troca o
     veredito", "Todos os testes da 6.5 usam dados sintéticos".
  4. **Calcular a referência** (bloco Container "ref" abaixo) → escrever no
     espelho o `preregistration_ref` e o hash completo → rodar o bloco de teste
     (Container "1º commit"). **Commit 1** (congelamento). Sem rebase entre este
     commit e o push da tag.
  5. **Ações externas — só depois de (a) a decisão humana do
     `blinding_statement` estar aplicada no arquivo commitado e (b) um go-ahead
     explícito da sessão mestra para publicar** (tag no remoto e comentário na
     #127 são públicos e não se desfazem; Checkpoint B r1, A4). Sem `--force`
     em nada. Bloco Host "âncora" abaixo: confere que a tag não existe (local e
     remota), cria e empurra **só** a tag, grava o corpo do comentário num
     arquivo (ref, hash completo, tag, commit, `cohort_id` e hash do cohort —
     sem afirmação sobre o passado do r0; a mesma regra `CLAIM_TERMS` roda
     sobre o corpo antes de postar), posta com `gh issue comment 127 --body-file`, e lê
     de volta pela API **exatamente um** comentário com `preregistration/<ref>`,
     com `created_at` e `html_url`, `created_at` > `2026-09-28T20:27:09Z`
     (âncora do cohort na #102).
  6. **Commit 2** (registro): `anchor.toml` gravado com os valores lidos da API
     (`tag`, `commit`, `comment_url` = `html_url`, `anchored_at` =
     `created_at`, offset date-time TOML); seção "Âncora r0" no espelho; caso
     `anchor_record_matches_ref` no teste (tag = `preregistration/<ref>`,
     `anchored_at` > `2026-09-28T20:27:09Z`); entrada única em §7 com o título
     literal `### <AAAA-MM-DD> — [decision] Task 13 — âncora do pré-registro r0
     — <autor>`, com os carimbos do servidor da #102 (`2026-09-28T20:27:09Z`) e
     da #127 (o `anchored_at`), nessa ordem, a entrada humana do
     `blinding_statement`, o registro do go-ahead e a frase "a Stage 6.5 não
     calculou nenhuma métrica sobre o cohort".

  **Espelho sem "≤ 5 %":** o poder declarado usa os números exatos; a taxa de
  reprovação falsa do gate é ≈ 5 % (0,0506 em n = 1 512 pela geometria), nunca
  "≤ 5 %" (Checkpoint B r1, T-F11; nota de emenda no ADR 6.5.0009, Task 12).
- **Critério de aceite (A4 parcial, A11, I1, I15):** os tokens abaixo verdes;
  tag visível no remoto; exatamente um comentário da #127 com a tag, posterior
  ao da #102; `git show preregistration/<ref>:config/preregistration/aapl_confirmatory-r0.toml`
  byte-igual ao arquivo em HEAD (também depois de rebases); nenhum `refresh`
  rodado (nenhum comando desta Task cita `data/`).
- **Tokens:** `test_preregistration_consistency.py`: `r0_matches_cohort`,
  `r0_values_match_adrs`, `r0_location_rates_normal`,
  `every_revision_hash_quoted`, `no_claim_about_r0_past` (1º commit; inclui
  as frases-amostra positivas e negativas do item 3);
  `anchor_record_matches_ref` (2º commit).
- **Container "ref" (antes de escrever o espelho):**
  ```bash
  uv run python - <<'PY'
  from pathlib import Path
  from financial_forecasting.features.evaluation.adapters.out.toml.toml_preregistration_source import TomlPreregistrationSource
  from financial_forecasting.features.evaluation.domain.value_objects.preregistration import Preregistration
  from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import CanonicalJsonHasher
  from financial_forecasting.shared.domain.value_objects.preregistration_hash import PreregistrationHash
  record = TomlPreregistrationSource(root=Path("config/preregistration")).read(name="aapl_confirmatory", revision=0)
  prereg = Preregistration.from_mapping(record.payload)
  digest = PreregistrationHash.compute(hasher=CanonicalJsonHasher(), payload=prereg.as_payload())
  print("preregistration_ref", prereg.reference(digest))
  print("hash", digest.value)
  PY
  ```
- **Container "1º commit" (T1, depois do espelho):**
  ```bash
  uv run pytest tests/integration/features/evaluation/test_preregistration_consistency.py -v -rs
  make check-task SLICE=evaluation
  make docs-check
  ```
  **Host (1º commit):**
  ```bash
  P=config/preregistration/aapl_confirmatory-r0.toml
  M=docs/preregistration/aapl_confirmatory.md
  test -s "$P"
  test -s "$M"
  # mesma regra do CLAIM_TERMS do teste (frases, quatro termos, qualquer ordem)
  set -- "$P" "$M"
  python - "$@" <<'PY'
  import re, sys
  TERMS = (r"\b(nenhuma|nenhum|nunca|jamais|never)\b|\bno\s+metrics?\b",
           r"\b(métricas?|metrics?)\b", r"\b(comput\w*|calcul\w*)\b", r"\b(r0|cohort|coorte)\b")
  bad = []
  for path in sys.argv[1:]:
      flat = re.sub(r"(?<!\n)\n(?!\n)", " ", open(path, encoding="utf-8").read())
      for s in re.split(r"(?<=[.!?;])\s+|\n\s*\n", flat):
          if all(re.search(term, s, re.IGNORECASE) for term in TERMS):
              bad.append((path, s.strip()))
  print(bad)
  sys.exit(1 if bad else 0)
  PY
  if grep -nF "≤ 5 %" "$M"; then echo "FAIL: espelho afirma <= 5 % de falsa reprovação"; exit 1; fi
  n=$(mktemp)
  git show --name-only --format= HEAD > "$n"
  test -s "$n"
  if grep -n "^data/" "$n"; then echo "FAIL: dado no commit de congelamento"; exit 1; fi
  ```
  **Host "âncora" (só com a decisão humana aplicada E o go-ahead da sessão
  mestra; `REF`/`HASH` do bloco "ref"):**
  ```bash
  REF="<ref>"; HASH="<hash>"
  COHORT_ID="aapl_confirmatory-r0-665f45d9169a"
  COHORT_HASH="665f45d9169aba576d194e73d45c0508f51f231f573c4de283c96fc5847365b1"
  test -n "$REF"; test -n "$HASH"
  TAG="preregistration/$REF"
  if git rev-parse -q --verify "refs/tags/$TAG" > /dev/null; then echo "FAIL: tag já existe localmente"; exit 1; fi
  r=$(mktemp)
  git ls-remote --tags origin "$TAG" > "$r"
  if test -s "$r"; then echo "FAIL: tag já existe no remoto"; exit 1; fi
  COMMIT=$(git rev-parse HEAD); test -n "$COMMIT"
  git tag "$TAG" "$COMMIT"
  git push origin "refs/tags/$TAG"
  git ls-remote --tags origin "$TAG" > "$r"
  test -s "$r"
  grep -qF "$COMMIT" "$r"
  body=$(mktemp)
  printf '%s\n' "Âncora do pré-registro (ADR 6.5.0003)" "" "- preregistration_ref: $REF" "- hash: $HASH" "- tag: $TAG" "- commit: $COMMIT" "- cohort_id: $COHORT_ID" "- cohort_hash: $COHORT_HASH" > "$body"
  test -s "$body"
  # mesma regra do CLAIM_TERMS do teste sobre o corpo do comentário
  set -- "$body"
  python - "$@" <<'PY'
  import re, sys
  TERMS = (r"\b(nenhuma|nenhum|nunca|jamais|never)\b|\bno\s+metrics?\b",
           r"\b(métricas?|metrics?)\b", r"\b(comput\w*|calcul\w*)\b", r"\b(r0|cohort|coorte)\b")
  bad = []
  for path in sys.argv[1:]:
      flat = re.sub(r"(?<!\n)\n(?!\n)", " ", open(path, encoding="utf-8").read())
      for s in re.split(r"(?<=[.!?;])\s+|\n\s*\n", flat):
          if all(re.search(term, s, re.IGNORECASE) for term in TERMS):
              bad.append((path, s.strip()))
  print(bad)
  sys.exit(1 if bad else 0)
  PY
  gh issue comment 127 --body-file "$body"
  a=$(mktemp)
  gh api --paginate repos/{owner}/{repo}/issues/127/comments --jq '.[] | select(.body | contains("'"$TAG"'")) | "\(.created_at) \(.html_url)"' > "$a"
  test -s "$a"
  test "$(wc -l < "$a")" -eq 1
  TS=$(cut -d' ' -f1 "$a"); URL=$(cut -d' ' -f2 "$a")
  test -n "$URL"
  [[ "$TS" > "2026-09-28T20:27:09Z" ]] || { echo "FAIL: âncora do pré-registro não é posterior à do cohort"; exit 1; }
  echo "anchored_at=$TS comment_url=$URL commit=$COMMIT"
  ```
  **Host (2º commit):**
  ```bash
  A=config/preregistration/aapl_confirmatory-r0.anchor.toml
  T=docs/stages/6.5-preregistration-and-scorecard/technical.md
  test -s "$A"
  TAG=$(sed -nE 's/^tag = "(.*)"$/\1/p' "$A"); test -n "$TAG"
  r=$(mktemp)
  git ls-remote --tags origin "$TAG" > "$r"
  test -s "$r"
  d=$(mktemp)
  git show "$TAG:config/preregistration/aapl_confirmatory-r0.toml" > "$d"
  test -s "$d"
  cmp "$d" config/preregistration/aapl_confirmatory-r0.toml
  test -s "$T"
  test "$(grep -cE "^### [0-9-]+ — \[decision\] Task 13 — âncora do pré-registro r0" "$T")" -eq 1
  python scripts/check_technical_postexec.py "$T"
  ```
  **Container (2º commit):**
  ```bash
  uv run pytest tests/integration/features/evaluation/test_preregistration_consistency.py -v -rs
  make check-task SLICE=evaluation
  ```
- **Commits sugeridos:**
  `feat(evaluation): pré-registro AAPL r0 congelado com espelho e teste de consistência [6.5/task-13]`;
  `docs(evaluation): âncora do pré-registro AAPL r0 registrada [6.5/task-13]`.

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 6.5: complete` e ser mergeada em `develop`. Antes: `git fetch` +
> `git rebase origin/develop` (§5), a Task 13 concluída e o push só depois do
> T3 verde. **Nada neste gate lê `data/` nem roda refresh sobre o cohort real.**

### Verificações automatizadas

**Container** (um único `bash -euo pipefail -c` no wrapper do §1):
```bash
make check                 # ruff + mypy strict + check_layout + lint-imports + fake-parity + port-coverage + docs-check + testes (cov >= 90%)

# A14 — cobertura por arquivo de src/ novo/modificado nesta Stage (lista DERIVADA do git, não
# escrita à mão — inclui composition_root.py; Checkpoint B r1, A6). Lê o .coverage deixado pelo
# `make check` acima no MESMO docker run (sem segunda rodada da suíte); falha se < 90% ou ausente.
base=$(git merge-base origin/develop HEAD)
src=$(mktemp)
git diff --name-only --diff-filter=AM "$base" -- 'src/*.py' > "$src"
test -s "$src"
test -s .coverage
cov=$(mktemp --suffix=.json)
uv run coverage json -o "$cov"
test -s "$cov"
uv run python - "$cov" "$src" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))["files"]
norm = {f.replace(chr(92), "/"): v["summary"]["percent_covered"] for f, v in d.items()}
need = [line.strip() for line in open(sys.argv[2]) if line.strip()]
scope = {n: [p for f, p in norm.items() if n.endswith(f) or f.endswith(n)] for n in need}
miss = [n for n, ps in scope.items() if not ps]
bad = {n: ps for n, ps in scope.items() if ps and min(ps) < 90}
print(len(need), "arquivos no escopo; abaixo de 90%:", bad, "; ausentes:", miss)
sys.exit(1 if bad or miss else 0)
PY

# A9 — duas suítes de contrato novas + as da 6.4 tocadas, todas as pernas, zero skips
f=$(mktemp)
uv run pytest tests/contract/features/evaluation/test_preregistration_source_contract.py tests/contract/features/evaluation/test_gold_generation_reader_contract.py tests/contract/features/evaluation/test_gold_store_contract.py tests/contract/features/evaluation/test_gold_builder_contract.py -v -rs | tee "$f"
test -s "$f"
if grep -q "SKIPPED" "$f"; then echo "FAIL: SKIPPED no contrato"; exit 1; fi
for id in fake toml parquet; do grep -q "\[$id" "$f" || { echo "FAIL: perna $id ausente"; exit 1; }; done

# A10/A11 — e2e e consistência, zero skips
g=$(mktemp)
uv run pytest tests/integration/features/evaluation/test_build_confirmatory_scorecard.py tests/integration/features/evaluation/test_preregistration_consistency.py tests/integration/features/evaluation/test_refresh_gold.py -v -rs | tee "$g"
test -s "$g"
if grep -q "SKIPPED" "$g"; then echo "FAIL: SKIPPED no e2e/consistência"; exit 1; fi

# A2/A12 — gates de arquitetura
uv run python scripts/check_layout.py
uv run lint-imports
uv run pytest tests/architecture/test_port_coverage_gate.py tests/architecture/test_unit_evaluation_purity.py tests/architecture/test_import_contracts.py -v

# Matriz — cada token casa >= 1 teste do arquivo (coleta uma vez por arquivo; token casado contra o
# nome da função após o '::' SEM o id '[...]', substring sem distinção de caixa, como o -k).
# A lista é recusada se um token repetir ou estiver contido em outro do mesmo arquivo (prova vácua).
U=tests/unit/features/evaluation; K=tests/contract/features/evaluation; I=tests/integration/features/evaluation
while read -r file toks; do
  test -s "$file"
  for a in $toks; do for b in $toks; do
    [ "$a" = "$b" ] || [[ "$b" != *"$a"* ]] || { echo "FAIL: token '$a' contido em '$b' ($file)"; exit 1; }
  done; done
  test "$(tr ' ' '\n' <<<"$toks" | sort | uniq -d | wc -l)" -eq 0
  ids=$(uv run pytest --co -q "$file" </dev/null | grep '::' | sed 's/^[^:]*:://; s/\[.*//' | sort -u)
  test -n "$ids"
  for t in $toks; do grep -qi -- "$t" <<<"$ids" || { echo "FAIL: sem teste '$t' em $file"; exit 1; }; done
done <<LIST
tests/unit/shared/domain/value_objects/test_preregistration_hash.py prereg_hash_float_encoded_exactly prereg_hash_nested_floats_encoded prereg_hash_int_not_coerced prereg_hash_bool_untouched prereg_hash_key_order_irrelevant prereg_hash_payload_not_mutated
$U/test_preregistration_value_object.py prereg_unknown_key_rejected prereg_missing_key_rejected prereg_rule_identifier_unimplemented prereg_rule_catalog_complete prereg_owner_validator_messages prereg_tiers_overlap_rejected prereg_candidate_in_tier_rejected prereg_model_without_seed_rejected prereg_model_without_deficit_rejected prereg_repeated_seeds_rejected prereg_negative_deficit_rejected prereg_power_scenario_invalid prereg_profile_unknown_rejected prereg_amendment_in_revision_zero prereg_amendment_required_after_zero prereg_amendment_complete_accepted prereg_blinding_absent_accepted prereg_blinding_empty_rejected prereg_int_coerced_to_float prereg_float_rejected_where_int prereg_bool_rejected_as_number prereg_payload_round_trip payload_toml_writer_round_trip
$U/test_preregistration_immutable_hash.py every_leaf_changes_hash tolerance_exponents_differ zero_int_float_same_hash hasher_never_sees_float reference_uses_hash12 leaf_paths_cover_payload
$U/test_mcs_vs_arch.py mcs_statistic_public_constant block_rule_single_owner block_rule_ceiling_values
$U/test_christoffersen_monte_carlo.py draws_seed_validator_public draws_seed_single_owner
$U/test_h1_gate_power.py power_doc_table_n500 power_equals_brute_double_sum power_acceptance_from_wilson_owner power_invalid_n_rejected
$U/test_student_t.py t_quantile_round_trip t_quantile_published_values t_quantile_invalid_rejected
$U/test_scorecard_evidence.py evidence_seed_counts_invalid evidence_tail_ratio_of_means evidence_dgt_offsets_complete evidence_single_step_without_dgt evidence_horizon_incoherent evidence_dm_pair_repeated evidence_seed_spread
$U/test_h1_gate.py gate_seed_mean_not_st gate_degeneracy_over_threshold_fails gate_not_applicable_fails gate_calls_count_kernels gate_lr_uc_sensitivity gate_dgt_bonferroni_level gate_single_step_no_dgt gate_common_sample_sensitivity gate_divergence_both_directions gate_result_carries_n_t_warning gate_power_rounded_n gate_degeneracy_at_threshold_passes
$U/test_scorecard_mechanical_rule.py outcome_not_applicable outcome_no_skill_over_naive outcome_beats_naive_only outcome_beats_naive_ties_strong outcome_beats_naive_and_strong winner_requires_gate_and_both h1_fail_all_rejected_no_winner outside_mcs_beats_strong_wins lowest_pinball_only_information comparator_miscalibrated_stays_in_family horizons_independent study_success_one_horizon verdict_without_profile_fields tier_reading_per_tier decide_horizon_set_mismatch_raises services_check_rule_identifiers ml_tier_counts_as_strong
$U/gold/test_refresh_gold_dtos.py schema_tables_complete parameters_from_mapping_round_trip manifest_from_mapping_round_trip manifest_prereg_ref_divergent_rejected manifest_unknown_key_rejected from_stored_empty_table from_stored_missing_table_corrupt from_stored_count_mismatch_corrupt from_stored_incoherent_corrupt from_stored_blocked_returned from_stored_uses_schema_keys
$K/test_gold_builder_contract.py builders_use_schema_keys schema_columns_written
$K/test_preregistration_source_contract.py source_reads_payload source_missing_revision_raises source_anchor_absent_none source_anchor_present_parsed source_anchor_naive_rejected real_anchor_extra_key_rejected real_malformed_toml_raises real_name_identifier_checked
$K/test_gold_generation_reader_contract.py reader_round_trip_equal reader_zero_row_table reader_all_none_column reader_blocked_returned reader_missing_manifest_raises real_no_hive_inference real_missing_table_file_corrupt real_count_mismatch_corrupt real_reads_manifest_first real_single_assembly
tests/architecture/test_port_coverage_gate.py scorecard_ports_resolve
$U/test_refresh_command_from.py command_field_from_plan command_partition_from_cohort command_parameters_from_plan command_tuple_order scorecard_command_without_partition
$U/test_scorecard_evidence_mapper.py mismatch_manifest_field mismatch_model_extra_missing mismatch_seed_extra_missing mismatch_grid_levels mismatch_mcs_statistic mismatch_block_rule corrupt_seed_missing_tail corrupt_horizon_row_missing corrupt_estimator_row_missing corrupt_scheme_row_missing corrupt_common_points_divergent mismatch_before_corrupt evidence_built_per_horizon mapper_reads_schema_columns mapper_gate_rows_band_level corrupt_block_estimate_missing corrupt_completed_with_failed_check
$U/test_dm_vs_r_oracle.py dm_effect_interval_formula dm_effect_undefined_zero_statistic
$U/test_scorecard_profile.py profile_tier_outcomes profile_dm_effect_ci profile_fallback_applied profile_comparators_threshold profile_band_95_fractions profile_common_sample_gate profile_without_gaps_rows profile_bartlett_divergence profile_moving_block_divergence profile_seed_spread profile_lowest_pinball profile_copies_gold_values profile_declared_not_built
$U/test_build_confirmatory_scorecard_use_case.py hash_mismatch_before_reader chain_broken_before_reader unanchored_before_reader validation_order_chain_hash_anchor reader_reads_derived_partition command_has_no_partition blocked_gold_not_ready not_found_propagates programming_error_propagates ready_false_gold_before_anchor ready_false_unblinded_amendment ready_false_required_check_skipped ready_true_refutation blinding_echoed_not_conjoined chain_listed_in_result verdict_unchanged_by_profile result_mapping_json_safe ready_true_started_at_anchor
$I/test_build_confirmatory_scorecard.py e2e_scorecard_expected_verdict e2e_ready_after_anchor e2e_parameter_changed_mismatch e2e_extra_seed_mismatch e2e_result_mapping_serializable e2e_paths_under_tmp
tests/unit/shared/test_composition_root.py wires_build_confirmatory_scorecard scorecard_shares_gold_store
$I/test_preregistration_consistency.py r0_matches_cohort r0_values_match_adrs r0_location_rates_normal every_revision_hash_quoted no_claim_about_r0_past anchor_record_matches_ref
LIST
```

**Host** (Git Bash, raiz da worktree, um script `bash -euo pipefail`):
```bash
T=docs/stages/6.5-preregistration-and-scorecard/technical.md
EV=src/financial_forecasting/features/evaluation
# A9 — baseline intocado
test -s scripts/arch_baseline.toml
if grep -nE "PreregistrationSource|GoldGenerationReader" scripts/arch_baseline.toml; then echo "FAIL: baseline"; exit 1; fi
# A2 — entre os arquivos de src/ desta Stage, só o VO de shared chama hash_mapping
base=$(git merge-base origin/develop HEAD)
m=$(mktemp)
git diff --name-only "$base" -- src/ > "$m"
test -s "$m"
h=$(mktemp)
while read -r path; do if test -f "$path" && grep -qE "\.hash_mapping\(" "$path"; then echo "$path" >> "$h"; fi; done < "$m"
test -s "$h"
test "$(wc -l < "$h")" -eq 1
grep -q "shared/domain/value_objects/preregistration_hash.py" "$h"
# A12 — tomllib só no adapter toml; pyarrow só no adapter duckdb
t=$(mktemp)
grep -rlnE "^\s*(import|from)\s+tomllib\b" "$EV" > "$t" || true
test -s "$t"
if grep -v "/adapters/out/toml/" "$t"; then echo "FAIL: tomllib fora de adapters/out/toml"; exit 1; fi
e=$(mktemp)
grep -rlnE "^\s*(import|from)\s+(duckdb|pyarrow|pandas)\b" "$EV" > "$e" || true
test -s "$e"
if grep -v "/adapters/out/duckdb/" "$e"; then echo "FAIL: engine fora de adapters/out/duckdb"; exit 1; fi
# A12 — a única referência a modeling em evaluation segue a anotação type-only da 6.4
r=$(mktemp)
grep -rnE "^\s*(from|import)\s+financial_forecasting\.features\.modeling" "$EV" > "$r" || true
test -s "$r"
test "$(wc -l < "$r")" -eq 1
grep -q "training_grid_reader.py" "$r"
# I8 — nenhum módulo novo da application recomputa o que o gold tem
n=$(mktemp)
grep -nE "DieboldMariano\b|HolmCorrection|ModelConfidenceSet\b|CoverageMetrics|HitSequences" "$EV"/application/use_cases/scorecard_evidence.py "$EV"/application/use_cases/scorecard_profile.py "$EV"/application/use_cases/build_confirmatory_scorecard.py > "$n" || true
if test -s "$n"; then cat "$n"; echo "FAIL: recomputação na application do scorecard"; exit 1; fi
# I15 — cegamento: nenhuma linha ACRESCENTADA por esta Stage em src/ ou tests/ cita o dado do
# cohort, usa Settings() sem raiz (cairia no data_root padrão) ou cita "cohorts" — exceto
# config/cohorts no teste de consistência (versionado) — Checkpoint B r1, A7. Só linhas novas:
# arquivos existentes tocados (ex. test_composition_root.py) já citam config/cohorts da 5.5.
base=$(git merge-base origin/develop HEAD)
c=$(mktemp)
git diff --name-only "$base" -- src/ tests/ > "$c"
test -s "$c"
b=$(mktemp)
while read -r path; do
  test -f "$path" || continue
  added=$(mktemp)
  git diff -U0 "$base" -- "$path" > "$added"
  test -s "$added"
  plus=$(mktemp)
  grep -E '^\+[^+]' "$added" > "$plus" || true
  if grep -qE "data/cohorts|Settings\(\)" "$plus"; then echo "$path" >> "$b"; fi
  if [[ "$path" == *test_preregistration_consistency.py ]]; then
    k=$(mktemp)
    grep "cohorts" "$plus" > "$k" || true
    if grep -qv "config/cohorts" "$k"; then echo "$path" >> "$b"; fi
  elif grep -q "cohorts" "$plus"; then echo "$path" >> "$b"; fi
done < "$c"
if test -s "$b"; then cat "$b"; echo "FAIL: linha nova da 6.5 toca o dado do cohort"; exit 1; fi
# A11 — âncora registrada uma vez em §7 (recortada: o grep não casa o próprio plano acima),
# com os carimbos da #102 e da #127, na ordem — Checkpoint B r1, A2
test -s "$T"
S7=$(awk '/<!-- BEGIN: post-execution -->/,/<!-- END: post-execution -->/' "$T"); test -n "$S7"
ENTRY=$(awk '/^### [0-9-]+ — \[decision\] Task 13 — âncora do pré-registro r0/{f=1; print; next} f && /^### /{f=0} f' <<<"$S7")
test -n "$ENTRY"
test "$(grep -cE "^### [0-9-]+ — \[decision\] Task 13 — âncora do pré-registro r0" <<<"$S7")" -eq 1
A=config/preregistration/aapl_confirmatory-r0.anchor.toml
test -s "$A"
TS=$(sed -nE 's/^anchored_at = ([0-9TZ:-]+)$/\1/p' "$A"); test -n "$TS"
grep -qF "2026-09-28T20:27:09Z" <<<"$ENTRY"
grep -qF "$TS" <<<"$ENTRY"
[[ "$TS" > "2026-09-28T20:27:09Z" ]] || { echo "FAIL: âncora do pré-registro não é posterior à do cohort"; exit 1; }
# A11 — tag no remoto e conteúdo da tag = arquivo em HEAD (conferência por conteúdo, ADR 6.5.0003 item 1)
TAG=$(sed -nE 's/^tag = "(.*)"$/\1/p' "$A"); test -n "$TAG"
r=$(mktemp)
git ls-remote --tags origin "$TAG" > "$r"
test -s "$r"
d=$(mktemp)
git show "$TAG:config/preregistration/aapl_confirmatory-r0.toml" > "$d"
test -s "$d"
cmp "$d" config/preregistration/aapl_confirmatory-r0.toml
# ADRs; §7; issue; nada de caminho do host versionado (dois padrões, montados em partes)
test -z "$(grep -L '^status: accepted' docs/adr/6_5_00*.md)"
HP="C:""/Users"   # montado em partes: o literal não aparece neste arquivo
HQ="/c""/Users"
for pat in "$HP" "$HQ"; do
  if git grep -n "$pat" -- docs/ tests/ src/ config/; then echo "FAIL: caminho do host versionado"; exit 1; fi
done
# o gate não é vácuo: um arquivo de rascunho com caminho de host é pego pelos mesmos padrões
s=$(mktemp); printf '%s\n' "x ${HP}/alguem/y" "x ${HQ}/alguem/y" > "$s"; test -s "$s"; grep -q "$HP" "$s"; grep -q "$HQ" "$s"; rm -f "$s"
python scripts/check_technical_postexec.py "$T"
python scripts/check_stage_issue.py
python scripts/check_docs_pointers.py
```

(A saída dos blocos A14, A9, A10/A11, A12 e do laço de tokens é colada no PR.)

### Verificações funcionais

- [ ] **Artefato novo consumível por fora (RUNBOOK Passo 10, último
      quilômetro):** no e2e (A10), `ScorecardResult.as_mapping()` serializa em
      JSON com `preregistration_ref`, a cadeia, a âncora, o manifesto lido, o
      veredito por horizonte, o perfil e `academic_decision_ready`; a 8.1 grava
      esse mapeamento fora de `current/` (roadmap, Task 12).
- [ ] Um plano alterado julgando o mesmo gold é recusado com
      `PreregistrationMismatchError` em `preregistration_ref` (o hash muda
      primeiro); o mesmo plano sobre um silver com uma seed a mais é recusado
      em `seeds` (e2e, A10).
- [ ] **Sem entrypoint de runtime na 6.5:** o scorecard é exercido pelo e2e
      via `wire_dependencies`; o runner (CLI/orquestrador) é da 8.1.
- [ ] O pré-registro r0 está no remoto (tag) e na #127 (comentário), com o
      carimbo do servidor posterior ao da âncora do cohort na #102; o arquivo em
      HEAD é byte-igual ao da tag.
- [ ] Nenhuma métrica foi calculada sobre o cohort pela Stage (I15): nenhum
      bloco, teste ou medição leu `data/cohorts/**`.

### Checklist de fechamento da Stage

- [ ] Todas as Tasks commitadas, cada uma com o seu gate (T1/T3/`check-block`)
      verde; Checkpoints C após 04, 07, 10 e 12.
- [ ] Task 13 executada depois da decisão humana do `blinding_statement` e,
      para a tag e o comentário, do go-ahead explícito da sessão mestra
      (ambos registrados na §7 junto da âncora).
- [ ] **Auditoria de testes independente** (PROMPT-stage §Auditoria de
      testes) com **mutação real** em `H1Gate.evaluate`,
      `ConfirmatoryScorecard.decide` e `evidence_from_generation` (ex.: `≤` →
      `<` no limiar, estimador Bartlett no lugar do retangular, `n·S` no lugar
      de `n̄`, pular a checagem de seeds): cada mutante morto por ≥ 1 teste;
      disposição de cada achado (A/B/C) registrada.
- [ ] Todo `[finding]` de §7 com a Stage candidata (ex. #129, 8.1, 8.3).
- [ ] `make check` verde no branch (após rebase em `origin/develop`);
      cobertura por arquivo (A14) colada.
- [ ] Laço de tokens da matriz verde, saída colada.
- [ ] `scripts/arch_baseline.toml` intocado; `test_port_coverage_gate.py` com
      piso 28.
- [ ] §7 com as decisões de detalhe do §1 efetivamente aplicadas e a entrada
      única da âncora (Task 13).
- [ ] Issue #129 citada na 8.1 do roadmap (Task 12).
- [ ] Commit final `stage 6.5: complete` aplicado (pós-auditoria).
- [ ] `roadmap.md`: Stage 6.5 marcada `done`, `updated_at` e
      `last_reviewed_at` no fechamento.
- [ ] ADRs 6.5.0001–0010 em `accepted`.
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo.

## 4. Ordem de dependência entre Tasks

```
Task 01 (PreregistrationHash, shared) ─► Task 02 (Preregistration + donos 6.2/6.3)
Task 02 ─► Task 03 (poder, VOs de evidência) ─► Task 04 (H1Gate + ConfirmatoryScorecard)
Task 05 (gold_schema + inversas + from_stored) ─► Task 07 (GoldGenerationReader + read_generation)
Task 02 ─► Task 06 (PreregistrationSource + TOML)
Tasks 04, 05, 07 ─► Task 08 (refresh_command_from + mapeador + erros) ─► Task 09 (quantil da t + perfil) ─► Task 10 (use case)
Task 06 ─► Task 10 (o use case consome o port PreregistrationSource e o fake)
Task 07 ─► Task 10 (o use case consome o port GoldGenerationReader e o fake)
Tasks 06, 10 ─► Task 11 (wiring + e2e) ─► (rebase) ─► Task 12 (roadmap + nota no ADR 6.5.0009)
[decisão humana: blinding_statement] + [go-ahead da sessão mestra p/ publicar] + Tasks 06, 11 ─► Task 13 (congelamento + âncora r0) ─► §3
```

- A 05 não depende de 01–04 (DTOs/builders da 6.4); pode vir antes da 06 sem
  mudar nada, mas fica depois da 04 para o Checkpoint C fechar o bloco de
  domínio primeiro.
- A 06 usa `valid_payload`/`to_toml` da 02 no contrato; a 07 usa o
  `from_stored` da 05; a 10 usa os ports e fakes da 06 e da 07.
- A 08 precisa do VO (02), da evidência (03), do `block_length_rule` (02), do
  schema/`from_stored` (05) e do leitor fake (07, pela fábrica).
- A 13 precisa do adapter TOML (06) para calcular a referência e do teste de
  consistência rodar pelo mesmo caminho do use case; ela é a **única** que
  espera o humano — se a decisão chegar antes da 12, pode rodar antes da 12
  (a 12 não depende dela).
- O §3 só roda depois da 13 (A11 e o grep da âncora).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| e2e de seed a mais não disparar `seeds` (o refresh filtrar seeds ou bloquear) | O refresh da 6.4 não filtra seeds do silver (conjunto vem do cohort sintético); se bloquear por `seed_horizon_coverage`, a seed 3 é gravada em todos os horizontes e folds; se ainda assim mudar, `[decision]` com o caso refeito como gold adulterado no nível do mapeador (Task 08 já cobre `mismatch_seed_extra_missing`) |
| A decisão do `blinding_statement` atrasar | Tasks 01–12 seguem; a Stage fica pronta menos a 13 e o §3; PR só depois da 13 (A11 é critério) |
| Coerção int/float esconder erro de digitação (ex. `reps = 1000.0`) | Campos `int` recusam float mesmo integral (§1); caso de teste `prereg_float_rejected_where_int` |
| O `repr` das taxas de locação divergir entre plataformas no último ULP | O arquivo guarda o `repr` gerado uma vez; o teste compara com tolerância 1e-12 (declarada); o hash é do arquivo, não do cálculo |
| Poder lento em n ≈ 1 500 | Algoritmo restrito ao conjunto aceito (§1); `--durations=3` no bloco da Task 03; se passar de 1 s por cenário, `[decision]` com medição |
| `student_t_quantile` por bisseção não convergir em df pequeno com p extremo | Intervalo [−10⁶, 10⁶] e 200 iterações; o perfil só usa p = 0,975 e df = T − 1 ≥ 1; ramo não convergente ergue `ArithmeticError` (mesmo contrato da CDF) |
| `check_port_coverage` não reconhecer `ParquetGoldStore` como real do `GoldGenerationReader` | A docstring do módulo cita o port (heurística documentada); conferir com `--list` na Task 07 antes do commit; nunca abrir entrada no baseline |
| `check_fake_parity` acusar bloco idêntico entre o fake do leitor e o `read_generation` | Os dois só chamam `GoldGeneration.from_stored` (a montagem sobe para o DTO); o real faz só I/O |
| pyarrow devolver tipo inesperado (coluna toda `None`, int nulo) e o `GoldTable` recusar | Contrato com coluna toda `None`; `GoldTable` aceita `None`; se aparecer outro tipo, conversão no `_read_rows` com `[decision]` (sem mudar o schema escrito) |
| e2e não dar o veredito esperado por ruído | Hits construídos deterministicamente (1 em 10 por cauda) e comparadores com viés grande; se o DM não rejeitar com T ≈ 120, aumentar T ou o viés, com `[decision]` |
| e2e lento (`ArchMcs` real, 2 horizontes × 2 esquemas × `reps = 1000`, `import arch` ≈ 8 s a frio) | Medido na 6.4 (< 1 s por par horizonte/esquema com T = 10³); `--durations=5` no bloco da Task 11 |
| Rebase conflitar em `docs/roadmap.md`, `composition_root.py` ou nos builders (Stages vizinhas em voo) | `git fetch && git rebase origin/develop` antes da Task 12 e de novo no PR; manter as duas edições; rerodar os greps da Task 12 e o T1 da 11 |
| Rebase depois da Task 13 mudar o commit do congelamento | A tag preserva o commit original; a conferência é por conteúdo (`cmp` do arquivo da tag com HEAD no §3/Task 13, ADR 6.5.0003 item 1) |
| Algum texto (arquivo, espelho, comentário) afirmar algo sobre o passado do r0 | Grep da Task 13 + `no_claim_about_r0_past`; o comentário é revisado antes de postar; se postado errado, novo comentário corrige e a âncora continua sendo o primeiro com o ref (registrado em §7) |
| Perfil de séries novas (#129) precisar de parâmetro não declarado no r0 (ex. número de lags do ACF de d_t) | Não bloqueia a 6.5; a #129 decide; se precisar de valor novo, é emenda **cega** (r1 `blinded`, ADR 6.5.0002) antes da 8.1 — registrado como `[finding]` |
| Verde falso por shell (`!` sob `set -e`, `grep -q` num pipe com `pipefail`, arquivo lido em outro `docker run`) | Convenção do §1: um `bash -euo pipefail -c` por bloco, negação por `if …; then exit 1; fi`, saída em arquivo antes do `grep`, `test -s` antes de ler |

## 6. Referências

- [`./concept.md`](./concept.md) — escopo, contratos (§4), invariantes (§5),
  erros (§6), decisões D1–D10 (§7), integrações (§8), modelo de dados (§9),
  critérios (§11), questão aberta (§13).
- ADRs desta Stage:
  [`6.5.0001`](../../adr/6_5_0001-preregistration-canonical-toml-hashed-value-object.md),
  [`6.5.0002`](../../adr/6_5_0002-amendment-as-new-revision-file.md),
  [`6.5.0003`](../../adr/6_5_0003-anchor-by-tag-and-issue-comment-and-order-check.md),
  [`6.5.0004`](../../adr/6_5_0004-judging-values-in-preregistration-cohort-by-reference.md),
  [`6.5.0005`](../../adr/6_5_0005-gold-generation-reader-port-manifest-first.md),
  [`6.5.0006`](../../adr/6_5_0006-scorecard-inputs-gate-from-seed-mean-counts.md),
  [`6.5.0007`](../../adr/6_5_0007-verdict-logical-form-and-decision-readiness.md),
  [`6.5.0008`](../../adr/6_5_0008-profiles-declared-in-preregistration-built-where-inputs-exist.md),
  [`6.5.0009`](../../adr/6_5_0009-preregistered-conventional-values.md),
  [`6.5.0010`](../../adr/6_5_0010-human-decisions-blinding-threshold-deviation-winner.md);
  relacionados: [`1.4.0001`](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md),
  [`5.5.0001`](../../adr/5_5_0001-frozen-hashed-cohort-spec.md),
  [`6.1.0005`](../../adr/6_1_0005-transient-port-coverage-baseline-between-port-and-first-adapter.md),
  [`6.2.0005`](../../adr/6_2_0005-mcs-block-length-ceiling-integer.md),
  [`6.3.0005`](../../adr/6_3_0005-count-kernels-accept-mean-counts.md),
  [`6.4.0005`](../../adr/6_4_0005-gold-full-refresh-per-cohort-partition.md),
  [`6.4.0006`](../../adr/6_4_0006-refresh-parameters-explicit-no-domain-defaults.md),
  [`6.4.0007`](../../adr/6_4_0007-gold-persists-both-samples-identified.md),
  [`0.0.0053`](../../adr/0_0_0053-slices-as-modules-of-one-context-consumer-owned-ports.md),
  [`0.0.0055`](../../adr/0_0_0055-tiered-quality-gates.md).
- Doc de domínio: [`probabilistic-forecast-evaluation.md`](../../domain/evaluation/probabilistic-forecast-evaluation.md)
  §4.4, §5.3, §6.4, §6.7–§6.10, §7.4, §7.6, §8, §10.
- [`../../LAYOUT.md`](../../LAYOUT.md) §2, §3, §7; [`../../PIPELINE.md`](../../PIPELINE.md) §4.3;
  [`../../RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) §Gates em camadas;
  [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §2, §3.4, §4, §6;
  runbook [`confirmatory-cohort-aapl.md`](../../runbooks/confirmatory-cohort-aapl.md) (âncora do cohort).
- Skills: `task-ordering-hex`, `hex-arch-python`, `ddd-tactical-patterns`,
  `pytest-with-fakes`, `repository-pattern`, `composition-root`,
  `orchestrator-design`, `git-versioning-pointer`.
- Stages de referência: [`../6.4-gold-builders-and-quality-gates/technical.md`](../6.4-gold-builders-and-quality-gates/technical.md)
  (+ §7 `[finding]` Task 08, Encaminhamentos, Exposição de cegamento),
  [`../5.5-confirmatory-retrain/technical.md`](../5.5-confirmatory-retrain/technical.md) (Task 34, âncora).
- Issues: [#127](https://github.com/MarceloSanC/financial-forecasting/issues/127),
  [#102](https://github.com/MarceloSanC/financial-forecasting/issues/102),
  [#129](https://github.com/MarceloSanC/financial-forecasting/issues/129),
  [#118](https://github.com/MarceloSanC/financial-forecasting/issues/118),
  [#125](https://github.com/MarceloSanC/financial-forecasting/issues/125).
- Python `tomllib`, `statistics.NormalDist`, `math.lgamma`; pyarrow
  `parquet.read_table(partitioning=None)`.

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a Fase 4. Apenas esta seção é editável após
> `status: done`. Cada entrada carrega data + autor.

### 2026-09-30 — [finding] Checkpoint B r1 (T-F11): falsa reprovação exata do gate H1 ≈ 5 %, não "≤ 5 %" — Claude (Opus 5.5)
**Contexto:** o ADR 6.5.0009 (linha do `dm_alpha`) justifica α = 0,05 citando
"the H1 gate's ≤ 5 % false failure" (Bonferroni 97,5 % por cauda). Pelo cálculo
exato do algoritmo do §1 (multinomial de 3 células, aceitação = as duas bandas
de Wilson 97,5 % contêm 0,10), a probabilidade de reprovar um candidato
calibrado é **0,0506 em n = 1 512** (n da geometria do cohort, não medido) e
oscila entre ≈ 0,044 e 0,053 para n em 1 400–1 600 (em n = 500 é 0,041, a
tabela do doc §8.5). Bonferroni sobre bandas de Wilson não garante ≤ 5 %
exato. Nenhuma métrica do cohort foi usada (cálculo sobre taxas nominais).
**Direção sugerida:** nota de emenda datada no topo do ADR 6.5.0009 (corpo
`accepted` intacto), no 2º commit da Task 12; o espelho do pré-registro (Task
13) declara a taxa como ≈ 5 % com o valor exato no n que o scorecard medir,
nunca "≤ 5 %"; o `dm_alpha` = 0,05 não muda (é escolha de coerência, ADR
6.5.0009). **Stage candidata:** esta (Tasks 12 e 13). **Seguimento (sem
edição agora; Checkpoint B r2, item 6):** o mesmo "≤ 5 %" aparece no ADR
0.0.0011 (`docs/adr/0_0_0011-preregistration-invariants-and-h1-gate.md:59`,
item 4 "Bonferroni over two tails, ≤ 5 % false failure") e no doc de domínio
(`docs/domain/evaluation/probabilistic-forecast-evaluation.md:1614`, §8.5 "a
probabilidade de reprovar um modelo calibrado é ≤ 5 %") — a corrigir por nota
datada pela sessão mestra (issue de docs), fora desta Stage.

### 2026-09-30 — [decision] Task 02: direção VO → serviço de domínio no slice `evaluation` (reverte a postura do technical 6.4 Task 03) — Claude (Opus 5.5)
**Contexto:** o `Preregistration` (`domain/value_objects/preregistration.py`)
valida cada valor pelos donos públicos, e vários moram em `domain/services/`
(`validate_rate`, `validate_alpha`, `validate_min_violations`,
`validate_mcs_reps`, `validate_draws_and_seed`, além de `DmVarianceEstimator` e
`MCS_STATISTIC`). O technical 6.4 (Task 03, `forecast_record.py`) evitou essa
direção ("o VO não importa `validate_rate` de `services/`, direção VO → serviço
que o slice não tem"). **Decisão:** adotar a aresta VO → serviço aqui, sob o ADR
6.5.0001 item 2 ("the public owner validators" — validar pelos donos, sem
segunda escrita); a reversão da postura 6.4 é deliberada. O mesmo vale para
`value_objects/scorecard_evidence.py` (Task 03: `validate_rate`,
`DmVarianceEstimator`). **Por que não cicla:** nenhum dos módulos de serviço
importados importa o VO do plano nem o de evidência; os serviços novos
(`h1_gate_power`, `h1_gate`, `confirmatory_scorecard`) importam os VOs (direção
usual). O `.importlinter` não tem contrato de camadas internas ao domínio; um
ciclo falharia já na coleta dos testes (nenhum teste dedicado).
**Stage candidata:** esta.

### 2026-09-30 — [decision] Tasks 03–04: leituras de detalhe do gate, da evidência e do veredito — Claude (Opus 5.5)
**Contexto:** pontos que o concept/technical deixam implícitos, resolvidos na
execução abaixo do limiar de concept (nenhum muda contrato, fronteira ou
critério). **Decisões:**
1. **Degeneração média do gate** = a maior entre as médias das duas caudas
   (`CalibrationEvidence.mean_degeneracy`): por construção da 6.4 as duas caudas
   da mesma série têm a mesma taxa; o `max` só escolhe o lado conservador se o
   gold um dia divergir.
2. **Sensibilidade "amostra comum"** recomputa o gate **inteiro** (as duas bandas
   ao nível do gate ∧ degeneração média ≤ limiar) sobre `HorizonEvidence.common`.
3. **Bandas DGT** chamam o `WilsonBand` com o horizonte h da série de origem (o
   aviso de dependência sai ligado, como na banda da série inteira); o nível é
   1 − `sensitivity_alpha`/(2h) e a sensibilidade passa só se as 2h bandas são
   aplicáveis e contêm a nominal.
4. **Divergência do LR_uc** = "rejeita" quando o gate passa, ou "não rejeita"
   quando o gate reprova (nos dois sentidos, ADR 6.5.0006 item 4).
5. **`HorizonEvidence`** exige `n_points` de toda linha DM = `common_points`
   (invariante do VO; o mapeador da Task 08 ergue `GoldGenerationCorruptError`
   antes, ao ler), `gate.dgt` com h sub-séries (offsets 0..h−1, passo h) para
   h > 1 e vazio para h = 1; `common.dgt` pode vir vazio.
6. **`candidate_has_lowest_mean_pinball`**: empate com o menor P̄_G conta como
   "tem a menor" (é informação, nunca condição — ADR 6.5.0007 item 4).
7. **`TierReading.ties_in_mcs`** (perfil, ADR 6.5.0007 item 5) = o candidato e
   **todos** os membros do nível estão no MCS primário ("o candidato está no MCS
   com eles"); `holm_rejects_all` = Holm rejeita contra todo membro.
8. **Poder**: `accepted_counts` varre c = 0..n com `WilsonBand.evaluate(horizon=1, …)`
   (só a aceitação importa); medido em n = 1 000 (seis cenários × dois
   horizontes) ≈ 0,3 s por `decide` — abaixo do limite de 1 s por cenário do §5.
**Stage candidata:** esta.

<!-- END: post-execution -->
