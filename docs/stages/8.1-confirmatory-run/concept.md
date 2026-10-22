---
title: Concept — Stage 8.1 — Corrida confirmatória ponta a ponta (cohort persistido → gold → scorecard pela r3)
description: Use case RunConfirmatoryEvaluation que, depois do infer idempotente, valida a revisão ancorada r3, roda o RefreshGold derivado do plano e o BuildConfirmatoryScorecard e preserva a geração julgada (gold + manifesto + scorecard + registro de execução) numa cópia imutável com digest de conteúdo; hash de conteúdo do silver lido gravado no manifesto do gold por um VO de identidade novo; atestação por registro versionado, tag e comentário na issue
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; antes de rodar ou re-rodar a corrida confirmatória; ao consumir a geração julgada na 8.2 (reprodução) ou na 8.3 (plots e dossiê); ao questionar por que a corrida recusa re-julgar, por que o hash do silver não é o dos bytes do Parquet ou onde fica a cópia julgada
keywords: [concept, confirmatory-run, evaluation, orchestration, refresh-gold, scorecard, preregistration, r3, judged-generation, content-hash, silver-content-hash, provenance, reproducibility, replay, idempotency, anchor, blinding]
status: draft
created_at: 2026-10-22
updated_at: 2026-10-22
stage_id: 8.1-confirmatory-run
stage_title: Corrida confirmatória ponta a ponta
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [6.5-preregistration-and-scorecard, 6.6-scorecard-profiles, 7.1-inference-engine, 7.2-conformal-cqr, 7.3-explainability]
---

# Concept — Stage 8.1 — Corrida confirmatória ponta a ponta

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task) e critérios de atomicidade, ver
> [`PIPELINE.md`](../../PIPELINE.md) §4.
>
> **Status (apenas dois estados).** `draft` desde a criação; `done` após
> o gate humano. Regressão `done → draft` é **permitida** quando a
> Fase 3B (Technical) revela gap material aqui — neste caso, commit
> `chore(concept): revert to draft — revision-from-technical: <motivo>`.
> O Passo 8 do runbook (início da Fase 4) exige `concept.status == done`
> **e** `technical.status == done` simultaneamente.

## 1. Escopo

### Dentro do escopo

- **Use case de orquestração `RunConfirmatoryEvaluation`**
  (`evaluation/application/use_cases/run_confirmatory_evaluation.py`): guardas
  → `RefreshGold` → `BuildConfirmatoryScorecard` → preservação da geração
  julgada, sem regra de domínio própria (D1–D3; ADR 8.1.0001).
- **Resolução da revisão julgada extraída** do `BuildConfirmatoryScorecard`
  para uma função de aplicação de dono único (cadeia, hash e âncora), chamada
  pelo orquestrador **antes** do refresh e pelo scorecard como hoje (D2).
- **Hash de conteúdo do silver lido**: VO de identidade novo
  `SilverContentHash` em `shared/domain/value_objects/`, calculado **dentro** do
  `RefreshGold` sobre as linhas que ele consome e gravado no `GoldManifest`
  (D4; ADR 8.1.0002). O `RefreshGoldResult` passa a devolver o manifesto
  publicado.
- **Geração julgada preservada**: port-out `JudgedGenerationStore` com adapter
  de sistema de arquivos — cópia da geração (`current/` inteiro) + scorecard +
  registro de execução em `gold/asset=<a>/parent_sweep_id=<p>/judged/<preregistration_ref>/`,
  com `CONTENTS.json` (sha256 de cada arquivo e digest do conjunto) gravado por
  último, nunca sobrescrita (D5; ADR 8.1.0003).
- **Registro de execução** (`run_record.json` dentro da cópia julgada): commit,
  árvore limpa, ambiente e resumo do `infer` que precedeu a corrida, por um
  port-out do consumidor `EvaluationEnvironment` (D6; ADR 8.1.0003).
- **Lock de escritor do `data_root`** durante o use case, pelo ledger já
  existente, através de um port do consumidor (D8).
- **Subcomando `evaluate` da CLI**: roda o `infer` da 7.1 sobre o cohort e,
  só se ele terminar sem erro, o `RunConfirmatoryEvaluation`; imprime o
  desfecho e o corpo do comentário de atestação (D1, D7).
- **Atestação** (passo de runbook, depois do selo): registro versionado
  `config/preregistration/<nome>-r<rev>.judged.toml`, tag
  `confirmatory-run/<preregistration_ref>` no commit da corrida e **um**
  comentário na issue #211 (D7; ADR 8.1.0003; ADR 6.5.0003 item 4).
- **A execução real**: a corrida sobre o cohort `aapl_confirmatory-r0-665f45d9169a`
  julgada pela r3 (`aapl_confirmatory-r3-00fd83d9cd39`), no Windows/Docker
  (CPU), com o veredito gravado, a geração selada e a atestação feita (D10;
  A12–A16).

### Fora do escopo (explicitamente)

- Reprodução da corrida e equivalência com a evidência anterior — Stage 8.2
  (a 8.1 só deixa o que a 8.2 precisa, doc de domínio §4.5).
- Plots canônicos e dossiê de rastreabilidade — Stage 8.3.
- Qualquer métrica, teste, perfil ou regra de veredito novo: a 8.1 executa o
  que 6.4–7.3 já fixaram (doc de domínio §3: "A 8.1 **não tem teoria
  própria**").
- Re-treino, nova `attribute` (7.3) ou nova corrida da ablação: o silver de
  atribuição e o da ablação já estão gravados e são **lidos** (e hasheados).
- Mecanismo de desvio ("re-julgar" depois de um defeito achado): a 8.1 **recusa**
  re-julgar uma revisão já selada; uma correção posterior é desvio do plano
  (doc de domínio §4.6), decidido pelo humano em issue própria.
- Publicar o comentário de atestação por código (port de GitHub): fica como
  passo de runbook, como as âncoras do pré-registro (D7).
- Amarrar o checkpoint ao conteúdo do dado de treino (lacuna da #163: o
  `RunId` não carrega impressão digital do dado) — o hash do silver identifica
  o que o gold leu, não o que o modelo treinou; segue na #163.
- As issues bloqueadas pela 8.1 (#58 calendário, #163 DST/as-of): só depois.
- CLI de `refresh` avulso do gold: o único caminho que publica gold real é o
  `evaluate` (o `RefreshGold` segue sem subcomando próprio).

### Vínculo com o roadmap

Stage 8.1 do Step 8 — *Reprodução, equivalência e relatório*
([`roadmap.md`](../../roadmap.md) §Step 8). Produz, pela primeira vez, a
evidência confirmatória do overview §4 (H1/H2/H3 por horizonte), com a
rastreabilidade que o critério "Reprodutibilidade" do overview exige e que a
8.2 (reprodução bit a bit, claim citável — ADR 0.0.0061) e a 8.3 (plots e
dossiê) consomem. A teoria que a 8.1 executa está apontada no doc de domínio
[`reproduction-equivalence-and-reporting`](../../domain/evaluation/reproduction-equivalence-and-reporting.md)
§3; o que ela precisa registrar e preservar, em §4.5.

## 2. Objetivo da Stage

Ao fim da Stage existe, no `data_root` do cohort AAPL, **uma** geração julgada
selada da revisão r3 — tabelas gold, manifesto (com o hash de conteúdo do
silver lido), scorecard confirmatório e registro de execução, numa cópia
imutável com digest de conteúdo —, produzida por um único comando que parte do
cohort persistido sem re-treino, e atestada no repositório e na issue.

## 3. Contexto e premissas

### Contexto

Todas as peças do confirmatório existem e foram provadas sobre silver
sintético, mas nunca rodaram juntas sobre o cohort real:

- **7.1** — `infer` idempotente: reproduz o teste a partir dos 60 checkpoints
  TFT (modo `strict`, max |Δ| = 0 na execução real de 2026-10-12) e completa a
  partição `calib` (211.680 linhas já gravadas); manifesto de inferência
  write-ahead (ADRs 7.1.0002–7.1.0004).
- **6.4/6.6/7.2/7.3** — `RefreshGold` regenera a geração inteira da partição
  `(asset, parent_sweep_id)`, com perfis (6.6), conformal (7.2) e leitura de H3
  (7.3), e a publica em `current/` por troca de diretórios; o refresh seguinte
  **substitui** a geração anterior (ADR 6.4.0005 itens 4–5).
- **6.5** — `BuildConfirmatoryScorecard(revision=N)` valida cadeia, hash e
  âncora, lê a geração viva e aplica a árvore do veredito; `refresh_command_from(plano, ref)`
  é a derivação única do comando do refresh.
- **Pré-registro**: cadeia r0 → r1 → r2 → r3 ancorada; a r3
  (`aapl_confirmatory-r3-00fd83d9cd39`, `anchored_at = 2026-10-21T17:41:23Z`,
  comentário na #186) é a revisão ancorada mais recente e traz os blocos
  `[conformal]` (r2) e `[h3]` com o cohort de ablação
  `aapl_ablation-r0-8a2d1de2dd8c`.
- **Gate de domínio do Step 8** (#208; ADRs 0.0.0060–0.0.0062): impõe à 8.1 a
  preservação da geração julgada antes de qualquer outro refresh
  (R-PRESERVA), a identidade completa **incluindo o hash de conteúdo do silver
  lido** (R-CAMADAS; lacuna do ADR 6.4.0005 item 9), commit, ambiente e seeds
  (§4.5).
- Não há CLI que publique gold: o `RefreshGold` e o `BuildConfirmatoryScorecard`
  estão montados no composition root, mas nenhum subcomando os chama.

**Forma medida do silver do cohort** (skill `data-shape-evidence`, só schema e
contagens, sem valor de métrica; `data/cohorts/aapl/silver` do checkout
principal, 2026-10-22):

| Tabela | Linhas | Observação |
|---|---|---|
| `dim_run` | 396 | 96 do confirmatório, 300 da ablação; `seed` nulo em 30 (baselines sem seed); tem `created_at_utc` |
| `fact_oos_predictions` | 1.605.072 | `fs_all` (confirmatório): 549.472; `fs_all_ablation`: 1.055.600; `split`: 211.680 `calib`, 1.393.392 `test` |
| `fact_permuted_predictions` | 8.655.920 | 120 arquivos, só `fs_all` |
| `fact_vsn_weights` | 891.490 | 120 arquivos, só `fs_all` |

Nenhum nulo nem valor não-finito nas colunas float dessas tabelas. A coluna
`year` é `int64` dentro dos arquivos e inferida `int32` pelo particionamento
hive do pyarrow (a união dos dois falha) — a identidade do silver não pode
depender de como o leitor tipa a partição (D4). Os 60 checkpoints do
confirmatório estão em `artifacts/tft` do checkout principal (60 de 60) e no
backup `data/backups/tft-pre-7.4-20261022-030008/` (technical 7.4 §7). Não há
`gold/` no `data_root` do cohort.

### Premissas

- O ambiente da corrida é a imagem `financial_forecasting-app:dev` em CPU no
  Windows/Docker; a máquina Linux saiu do projeto. A 8.2 reproduz no ambiente
  registrado aqui (D6).
- A r3 em `HEAD` hasheia para `aapl_confirmatory-r3-00fd83d9cd39` (o resolver
  confere; se não, a corrida recusa — D2).
- O silver do cohort e o da ablação estão completos (7.1 `verify`, 7.3
  `ablation-verify` e `attribute` com 60 `verified`); o `infer` reconfirma o
  confirmatório antes de qualquer gold.
- O custo do `RefreshGold` sobre o silver real cabe numa execução (6.4 mediu
  ≈ 19 s antes de perfis, conformal e H3; H3 lê ≈ 8,7 M linhas permutadas). O
  hash do silver acrescenta uma passada sobre as linhas que o refresh já lê;
  o custo é medido na corrida real (R3).

### Dependências

- `6.5-preregistration-and-scorecard`: `BuildConfirmatoryScorecard`,
  `refresh_command_from`, `ScorecardResult.as_mapping()`, `PreregistrationSource`
  e o mecanismo de âncora (ADR 6.5.0003).
- `6.6-scorecard-profiles`: tabelas de perfil na mesma geração, nunca no
  veredito (ADR 6.6.0002).
- `7.1-inference-engine`: subcomando `infer` idempotente e manifesto de
  inferência (ADRs 7.1.0002–7.1.0004).
- `7.2-conformal-cqr`: tabelas conformais publicadas pelo `RefreshGold`
  derivado da revisão (ADR 7.2.0003).
- `7.3-explainability`: tabelas gold de H3 pelo `RefreshGold` com o bloco
  `[h3]` da r3 (ADR 7.3.0001), silver de atribuição e cohort de ablação
  treinado; r3 ancorada (ADR 7.3.0005).
- Gate de domínio do Step 8 (#208): doc de reprodução §3, §4.5, §4.6.

## 4. Contratos

Assinaturas indicativas; nomes de campo e tipos exatos fecham no technical.

### Introduzidos

- **`RunConfirmatoryEvaluation`** (use case, `evaluation/application/use_cases/run_confirmatory_evaluation.py`)

  ```python
  class RunConfirmatoryEvaluation:
      def __init__(
          self, *,
          source: PreregistrationSource,          # 6.5
          hasher: Hasher,
          refresh_gold: GoldRefresh,              # Protocol local; real = RefreshGold
          build_scorecard: ScorecardBuilder,      # Protocol local; real = BuildConfirmatoryScorecard
          judged_store: JudgedGenerationStore,
          environment: EvaluationEnvironment,
          writer_lock: EvaluationWriterLock,
      ) -> None: ...

      def __call__(self, command: RunConfirmatoryEvaluationCommand) -> RunConfirmatoryEvaluationResult: ...
  ```

  O `__init__` anota ports, nunca classes concretas (LAYOUT §7, gate
  `check_use_case_deps.py`); a forma exata dos dois Protocols locais é do
  technical.

- **`RunConfirmatoryEvaluationCommand`** (dto): `name` (`"aapl_confirmatory"`),
  `revision` (`3`), `preregistration_ref` esperado, `break_stale_lock`,
  `inference_summary` (resumo do `infer` que a CLI acabou de rodar: runs,
  quantos `strict`/`tolerance`, max |Δ|, linhas `calib` verificadas — dado,
  sem tipo do `inference`).
- **`RunConfirmatoryEvaluationResult`** (dto): `status`
  (`ConfirmatoryRunStatus`), `preregistration_ref`, `partition`,
  `generation_digest`, `refresh_status` (`COMPLETED`/`BLOCKED`), o
  `ScorecardResult` quando houver, `failed_checks` quando `BLOCKED`, e
  `attestation_body` (texto determinístico do comentário, D7).
- **`ConfirmatoryRunStatus`** (dto, `StrEnum`): `JUDGED` | `BLOCKED` |
  `ALREADY_JUDGED` (D3). Falha é exceção, nunca status.
- **`resolve_judged_revision`** (função de aplicação, dono único da validação
  hoje privada do `BuildConfirmatoryScorecard`): lê as revisões 0..r, confere
  cadeia, hash esperado e âncora de cada revisão; devolve o plano julgado, a
  cadeia de referências e a âncora. Os erros são os de hoje
  (`PreregistrationChainError`, `PreregistrationHashMismatchError`,
  `PreregistrationNotAnchoredError`), na mesma ordem.
- **`SilverContentHash`** (value-object, `shared/domain/value_objects/silver_content_hash.py`)

  ```python
  @dataclass(frozen=True)
  class SilverContentHash:
      value: str                                   # sha256 hex, validate_sha256_hex

      @classmethod
      def of_unit(cls, *, hasher: Hasher, table: str,
                  rows: Sequence[Mapping[str, object]]) -> SilverContentHash: ...
      @classmethod
      def combine(cls, *, hasher: Hasher,
                  digests: Mapping[str, SilverContentHash]) -> SilverContentHash: ...
  ```

  Floats codificados exatamente (`repr`, como o `PreregistrationHash`), linhas
  em ordem canônica, colunas por nome, tipos normalizados (inteiros de
  numpy/pandas → `int`, flutuantes → `float`; outro tipo → `ValueError`),
  colunas de proveniência de escrita (`created_at_utc`) fora; NaN/±inf
  recusados (D4; ADR 8.1.0002).
- **`GoldManifest.silver_content`** (campo novo do dto, ADR 6.4.0005 item 8
  ampliado): digest combinado, digest por tabela consumida e digest por
  unidade de conteúdo (D4). Serializado em `as_mapping()` e lido por
  `from_stored`.
- **`RefreshGoldResult.manifest`** (campo novo do dto): o `GoldManifest`
  publicado, para o orquestrador conferir a cópia (I8).
- **`JudgedGenerationStore`** (port-out, `evaluation/application/ports/out/judged_generation_store.py`)

  ```python
  class JudgedGenerationStore(Protocol):
      def find(self, *, partition: GoldPartition,
               preregistration_ref: str) -> JudgedGeneration | None: ...
      def preserve(self, *, partition: GoldPartition, preregistration_ref: str,
                   expected_manifest: GoldManifest,
                   documents: Mapping[str, Mapping[str, object]]) -> JudgedGeneration: ...
  ```

  `find` devolve a geração selada **depois de conferir o digest** (divergente
  ou arquivo faltando → `JudgedGenerationTamperedError`); `preserve` copia
  `current/` da partição, confere o manifesto copiado contra
  `expected_manifest`, grava os documentos JSON
  (`gold_model_comparison_confirmatory_scorecard`, `run_record`), grava
  `CONTENTS.json` por último e troca o diretório de staging para o
  definitivo; existindo selada → `JudgedGenerationExistsError` (D5). Real:
  adapter de sistema de arquivos ao lado do `ParquetGoldStore`; fake em
  `tests/fakes/features/evaluation/`; contrato `[fake, real]`.
- **`JudgedGeneration`** (dto): `preregistration_ref`, `partition`,
  `generation_digest`, `refresh_status`, `files` (caminho relativo → sha256).
- **`EvaluationEnvironment`** (port-out do consumidor): `snapshot() -> Mapping[str, str]`
  com as chaves do D6; real montado no composition root reusando o probe da
  5.5 para as chaves que ele já tem (sem redeclarar como o hash de `src/` é
  calculado) e acrescentando as do caminho do gold.
- **`EvaluationWriterLock`** (port-out do consumidor): `acquire_writer(*, break_stale)`
  / `release_writer()`, satisfeito por duck typing pelo
  `JsonCohortProgressLedger` (precedente: `CohortLedger` do `inference`,
  ADR 7.1.0004 item 5).
- **Erros novos** (`ApplicationError`): `DirtyCodeError`,
  `JudgedGenerationTamperedError`, `JudgedGenerationMismatchError`,
  `JudgedGenerationExistsError`.
- **Subcomando `evaluate`** (adapter primário, `cli.py` + módulo de comandos do
  `evaluation` sob `adapters/in/cli/`):
  `python -m financial_forecasting.cli evaluate --data-root <dir> --cohort <toml> --preregistration aapl_confirmatory --revision 3 --preregistration-ref <ref> [--break-stale-lock]`.
- **Registro de atestação** `config/preregistration/<nome>-r<rev>.judged.toml`
  (formato de repositório, como o `.anchor.toml` do ADR 6.5.0003 item 2):
  `preregistration_ref`, `generation_digest`, `refresh_status`, `commit`,
  `tag`, `comment_url`, `commented_at` (D7).

### Consumidos

- **`RefreshGold`**, **`RefreshGoldCommand`**, **`GoldManifest`**,
  **`GoldPartition`**, **`ParquetGoldStore`** — Stage 6.4 (ADR 6.4.0005).
- **`BuildConfirmatoryScorecard`**, **`refresh_command_from`**,
  **`ScorecardResult.as_mapping()`**, **`PreregistrationSource`** /
  **`TomlPreregistrationSource`** — Stage 6.5 (ADRs 6.5.0001–6.5.0007).
- Tabelas de perfil (6.6), conformais (7.2) e de H3 (7.3) — publicadas pelo
  `RefreshGold` derivado da r3; a 8.1 só as executa.
- **Subcomando `infer`** / **`RunInference`** — Stage 7.1, chamado pela CLI
  antes do use case (D1).
- **`RuntimeEnvironmentProbe`** (snapshot com `code.src`, `code.uv_lock`,
  `code_dirty`, versões, `cpu`) — Stage 5.5, reusado pelo real de
  `EvaluationEnvironment`.
- **`JsonCohortProgressLedger`** (lock de escritor do `data_root`) — Stage 5.5.
- **`Hasher`** canônico (ADR 1.4.0001) — via os VOs de identidade.

## 5. Invariantes e regras

- **I1 — Orquestrador sem regra de domínio.** O use case sequencia, confere
  igualdades de identidade e grava; não calcula métrica, limiar, nem decide
  veredito (skill `orchestrator-design`). Todo número julgado sai do
  `RefreshGold` e do `BuildConfirmatoryScorecard`, sem alteração.
- **I2 — Guardas antes de efeitos, nesta ordem:** (G1) resolução da revisão
  julgada — cadeia, hash = `command.preregistration_ref`, âncora de toda
  revisão; (G2) ambiente — `code_dirty = "false"`; (G3) lock de escritor;
  (G4) `find` da geração julgada da revisão **e** recusa se a partição já tem
  geração julgada de **outra** revisão. Só então (E1) `RefreshGold` → (E2) scorecard
  em memória → (E3) `preserve`. Falha em G1–G4 → **zero** publicação de gold e
  zero escrita em `judged/`.
- **I3 — Nenhuma métrica antes da âncora.** O refresh só roda com a revisão
  julgada ancorada (G1); o manifesto publicado tem `started_at` ≥
  `anchored_at` da r3 (o scorecard já marca o contrário como
  `GOLD_BEFORE_ANCHOR`, ADR 6.5.0003 item 3).
- **I4 — Uma geração julgada por partição.** `judged/<preregistration_ref>/`
  existe no máximo uma vez e nunca é sobrescrita nem apagada pelo código. Com
  ela selada, a corrida não chama o refresh nem o scorecard (D3). Uma revisão
  nova (r4) ancorada depois de ver a r3 **não** abre um segundo julgamento
  pelo `evaluate`: G4 recusa (`JudgedGenerationExistsError`) se a partição já
  tem geração julgada de outra revisão; re-julgar é desvio decidido pelo
  humano.
- **I5 — `BLOCKED` é desfecho, não falha.** Um refresh `BLOCKED` sobre a r3 é
  preservado e selado como os demais, com os checks que falharam no registro, e
  não é re-tentado: rodar de novo até passar seria escolher o resultado
  olhando-o (D3). Consequência declarada: com `BLOCKED` não há veredito, o DoD
  do roadmap ("veredito mecânico H1/H2/H3 produzido") **não** é cumprido, e a
  Stage para com um `[finding]` para decisão humana (desvio ou emenda do DoD),
  sem re-rodar.
- **I6 — Identidade do silver pelo conteúdo consumido.** O
  `SilverContentHash` depende só do multiconjunto de linhas que o refresh
  consome (depois do pós-filtro ao cohort), sem as colunas de proveniência de
  escrita, nunca da ordem de leitura, da divisão em arquivos, do tipo que o
  leitor dá a um número nem dos bytes do Parquet; linhas de outro cohort na
  mesma partição não o mudam (D4). A série realizada que o refresh usa
  (timestamps + retorno-alvo da grade) entra como unidade própria, em float
  exato, ao lado do `DatasetContentFingerprint` (que arredonda e segue como
  identidade ancorada do cohort).
- **I7 — Floats exatos na identidade.** Nenhum arredondamento entra no hash do
  silver: dois valores distintos dão hashes distintos (D4).
- **I8 — A cópia é a geração publicada.** O manifesto copiado é **igual** ao
  `RefreshGoldResult.manifest` desta execução e, quando há scorecard, ao
  `ScorecardResult.manifest_read`; divergente → erro, nada selado.
- **I9 — Selo por último.** `CONTENTS.json` (sha256 de cada arquivo da cópia e
  o `generation_digest` sobre a lista ordenada) é o último arquivo escrito, e
  o diretório só aparece como `judged/<ref>/` depois dele; leitor sem
  `CONTENTS.json` válido trata a cópia como corrompida.
- **I10 — Proveniência fora da identidade da entrada.** Timestamps de
  escrita (inclusive `created_at_utc` do `dim_run`), host e URL do comentário
  são registrados e nunca entram no hash do silver (doc de
  domínio §2.2, R-CAMADAS); o `generation_digest` cobre a cópia inteira
  (inclusive o manifesto com timestamps) porque seu papel é integridade da
  cópia, não comparação entre corridas (D5).
- **I11 — Perfil e eixos descritivos não trocam o veredito** (herdado: I12 da
  6.5, ADR 6.6.0002, inference §4.11/§5.8): a 8.1 não reordena nem filtra
  nada do `ScorecardResult`.
- **I12 — Cegamento até a Task da corrida real.** Nenhum teste nem Task antes
  da execução real roda refresh ou scorecard sobre o cohort real; testes de
  integração e e2e usam silver sintético (evaluation §8.2 B-ORDEM).

## 6. Casos de erro e exceções

| Situação | Onde | Comportamento |
|---|---|---|
| Checkpoint ausente/ambíguo, divergência de reprodução no `infer` | CLI, antes do use case | erro da 7.1 propaga (`CheckpointNotFoundError`, `ReproductionError`…), exit 2; use case não roda; nada de gold |
| Revisão inexistente, cadeia quebrada, hash ≠ esperado, revisão sem âncora ou âncora de outro hash | G1 | erros da 6.5 (`PreregistrationNotFoundError`, `PreregistrationChainError`, `PreregistrationHashMismatchError`, `PreregistrationNotAnchoredError`); zero efeito |
| Código ou `config/preregistration/` com mudança rastreada não commitada | G2 | `DirtyCodeError`; zero efeito |
| Lock ocupado / órfão | G3 | erro do ledger; `--break-stale-lock` é decisão explícita do operador (como na 5.5/7.1) |
| Partição já tem geração julgada de outra revisão | G4 | `JudgedGenerationExistsError`; zero efeito |
| Geração julgada selada e íntegra | G4 | `ALREADY_JUDGED`, devolve o registro; sem refresh, scorecard nem escrita |
| Geração julgada com digest divergente ou arquivo faltando | G4 | `JudgedGenerationTamperedError`; zero efeito; diagnóstico humano |
| Sobra de staging de corrida interrompida | E3 | removida pelo `preserve` antes de copiar (como `.staging/` do ADR 6.4.0005 item 5) |
| `GridFingerprintMismatchError`, cohort vazio, linha mal-formada, não-finito no silver | E1 | propaga do `RefreshGold`; `current/` intacto; nada selado; re-execução permitida (determinística) |
| Refresh `BLOCKED` | E1 → E3 | sem scorecard; `preserve` com status `BLOCKED` e checks que falharam; status `BLOCKED`; na corrida real, `[finding]` e parada para decisão humana (I5) |
| Gold corrompido ou de outro plano na leitura do scorecard | E2 | erros da 6.5 (`GoldGenerationCorruptError`, `PreregistrationMismatchError`) propagam; nada selado |
| Manifesto copiado ≠ publicado / ≠ lido pelo scorecard | E3 | `JudgedGenerationMismatchError`; staging descartado; nada selado |
| `judged/<ref>/` aparece entre G4 e E3 | E3 | `JudgedGenerationExistsError`; nada sobrescrito |
| Falha de escrita na cópia | E3 | `OSError` propaga; staging fica para o próximo `preserve` limpar; nada selado |
| Exceção em qualquer ponto depois de G3 | use case | lock liberado em `finally` |

Re-executar depois de qualquer falha antes do selo é seguro: a cadeia é
determinística (doc de domínio §4.2), então a nova geração tem o mesmo
resultado da que não foi selada; só a proveniência muda.

## 7. Decisões técnicas relevantes

> Registros `[decision:E|C]` da triagem `evidence-resolution` estão nos ADRs.
> Nenhum fork desta Stage é P: todos são anteriores ao primeiro dado
> confirmatório e não trocam o veredito de H1/H2/H3.

### D1 — Forma da orquestração: use case no evaluation; `infer` encadeado pela CLI

- **O quê:** `RunConfirmatoryEvaluation` vive em `evaluation/application/use_cases/`
  e não conhece o slice `inference`. O subcomando `evaluate` roda, no mesmo
  processo, o comando `infer` da 7.1 sobre o mesmo spec do cohort e só chama o
  use case se ele terminar sem exceção; o resumo do `infer` entra no comando
  como dado.
- **Por quê:** o `RunInference` recebe um `CohortSpec` do `modeling` e
  adquire o lock por conta própria; chamá-lo de dentro do use case exigiria um
  port do consumidor que carrega DTOs de dois slices e um lock reentrante. A
  CLI já é o adapter primário que monta o spec e despacha comandos de três
  slices (`cli.py`); sequenciar dois comandos é coordenação de processo, não
  regra de domínio. O `infer` não é pulado: é o elo checkpoint → silver
  reconfirmado imediatamente antes do julgamento.
- **Fonte:** issue #211 (abordagem passo 1); `cli.py` (`_dispatch_inference_command`);
  ADR 0.0.0053 (comportamento de outro slice só por port do consumidor); ADR
  7.1.0004 item 5 (lock do `RunInference`).
- **ADR:** [`8.1.0001`](../../adr/8_1_0001-confirmatory-run-orchestration-guards-status-replay.md)

### D2 — Guardas antes de efeitos, com a resolução da revisão extraída

- **O quê:** ordem I2 (G1 resolução → G2 ambiente limpo → G3 lock → G4
  geração julgada → E1 refresh → E2 scorecard → E3 preservação). A validação
  de cadeia/hash/âncora sai do `BuildConfirmatoryScorecard` para
  `resolve_judged_revision`, chamada pelos dois.
- **Por quê:** o `RefreshGold` não confere âncora; rodá-lo antes do G1 seria
  computar as métricas confirmatórias sob um plano possivelmente não ancorado
  — exatamente o que B-ORDEM proíbe (evaluation §8.2). Copiar a validação
  para o orquestrador criaria um segundo dono da regra da âncora.
- **Fonte:** skill `orchestrator-design` ("Side effects after gates");
  ADR 6.4.0005 item 3; ADR 6.5.0003 itens 1, 3; evaluation §8.2.
- **ADR:** [`8.1.0001`](../../adr/8_1_0001-confirmatory-run-orchestration-guards-status-replay.md)

### D3 — Status determinístico e replay

- **O quê:** três status (`JUDGED`, `BLOCKED`, `ALREADY_JUDGED`); falha é
  exceção. Replay: geração julgada selada e íntegra → no-op; digest divergente
  → recusa; sem selo → corrida completa (sobras descartadas). Não há flag para
  re-julgar.
- **Por quê:** uma vez que o veredito (ou o `BLOCKED`) existe, rodar de novo
  com outra escolha é o *garden of forking paths* que o pré-registro existe
  para impedir; antes do selo, como nada foi gravado como julgado e a cadeia é
  determinística, re-executar não muda o resultado. Decidir por hash, não por
  timestamp (contraparte GNU make, issue #211).
- **Fonte:** skill `evidence-resolution` §1 (Gelman & Loken 2014; Nosek et al.
  2018, via evaluation §8.3); doc de domínio §4.2 (R-BIT) e §4.6; ADR 6.4.0005
  item 5 (limpeza de staging); ADR 7.1.0002 (complementação idempotente).
- **ADR:** [`8.1.0001`](../../adr/8_1_0001-confirmatory-run-orchestration-guards-status-replay.md)

### D4 — Hash de conteúdo do silver: VO novo, linhas consumidas, floats exatos, dentro do refresh

- **O quê:** `SilverContentHash` em `shared/domain/value_objects/`; o
  `RefreshGold` calcula um digest por **unidade de conteúdo** — `(tabela,
  parent_sweep_id)` para `dim_run`; `(tabela, run_id, year)` para as tabelas
  de fato, com `year` lido da linha; `(realized, asset)` para a série
  realizada que ele usa — sobre as linhas que consome depois do pós-filtro,
  combina por tabela e no total, e grava em `GoldManifest.silver_content`.
  Linhas canonizadas: colunas por nome, sem as de proveniência de escrita
  (`created_at_utc`), ordem canônica das linhas, tipos numéricos normalizados
  (`int`/`float` do Python), floats por `repr`, `None` → `null`.
- **Por quê:** (a) o `DatasetContentFingerprint` não serve: arredonda a 10
  casas (ADR 5.5.0004) e seu valor está congelado no cohort e nas revisões
  r0–r3 — mudar sua codificação mudaria uma identidade ancorada; (b) arredondar
  a 10 casas colide valores float32 distintos abaixo de ≈ 8,4·10⁻⁴ (o
  espaçamento do float32 em x é ≈ 1,19·10⁻⁷·x), faixa em que caem quantis de
  retorno diário — a identidade deixaria de distinguir entradas; (c) bytes do
  Parquet carregam a versão do escritor (`FileMetaData.created_by`) e o tipo
  da partição varia com o leitor (medido: `year` int64 × int32); (d) calcular
  no próprio refresh evita uma segunda definição de "quais linhas o refresh lê"
  (pós-filtros, leitura por ano da ablação, um run por vez da atribuição) e
  garante que o hash descreve as linhas usadas, sem janela entre hash e
  leitura; (e) `created_at_utc` é o instante da escrita — proveniência, que
  R-CAMADAS exclui da identidade; (f) o realizado entra exato pelo mesmo
  argumento de (b), sem mexer no `DatasetContentFingerprint` ancorado.
- **Fonte:** ADR 6.4.0005 item 9; LAYOUT §7 ("identidade só pelos VOs de
  `shared/domain/value_objects/`"); `PreregistrationHash` (floats exatos, ADR
  6.5.0001); doc de domínio §2.2 (R-CAMADAS); issue #211 §Referências
  (DVC `.dir`, MLflow, `parquet.thrift`).
- **ADR:** [`8.1.0002`](../../adr/8_1_0002-silver-content-hash-exact-rows-consumed-by-refresh.md)

### D5 — Geração julgada: cópia em `judged/<ref>/`, integridade por sha256 dos bytes, selo por último

- **O quê:** `gold/asset=<a>/parent_sweep_id=<p>/judged/<preregistration_ref>/`
  com `generation/` (cópia byte a byte de `current/`: tabelas e
  `MANIFEST.json`), `gold_model_comparison_confirmatory_scorecard.json`
  (`ScorecardResult.as_mapping()`, ausente se `BLOCKED`), `run_record.json`
  (D6) e `CONTENTS.json` (sha256 de cada arquivo + `generation_digest` =
  sha256 da lista ordenada `caminho → sha256`), escrito por último; staging +
  rename como o `ParquetGoldStore`. O nome do diretório é a referência da
  revisão, não o digest.
- **Por quê:** a cópia tem papel de **arquivo imutável** (Sandve Rule 5),
  então o hash certo é o dos bytes guardados — detecta qualquer alteração da
  cópia; a comparação de resultado da 8.2 é campo a campo (doc de domínio §4.6),
  não por esse digest. Endereçar o diretório pelo digest (como objetos do git)
  permitiria várias gerações julgadas por revisão — o que I4 proíbe; a chave
  natural é a revisão. Fica fora de `current/` porque o próximo refresh o
  substitui (ADR 6.4.0005 itens 4–5). O caminho do roadmap
  (`scorecard/<preregistration_ref>/`) é refinado para `judged/<ref>/`
  porque o diretório guarda a geração inteira, não só o scorecard; o nome
  `gold_model_comparison_confirmatory_scorecard` do roadmap é mantido no
  arquivo.
- **Fonte:** doc de domínio §2.1, §4.5 item 1, §4.6 (R-PRESERVA); ADR 6.4.0005
  itens 4–5; ADR 7.1.0004 item 1 (sha256 por streaming dos bytes do checkpoint);
  Chacon & Straub, *Pro Git* 2ª ed. §10.2.
- **ADR:** [`8.1.0003`](../../adr/8_1_0003-judged-generation-preserved-copy-run-record-attestation.md)

### D6 — Registro de execução

- **O quê:** `run_record.json` com: `commit` (`git rev-parse HEAD`),
  `code_dirty` (`false` por G2), as chaves do probe da 5.5 (`code.src`,
  `code.uv_lock`, versões, `cpu`), a **capacidade de CPU** (a mesma grandeza
  que o manifesto de inferência grava, ADR 7.1.0003 item 2 — a `cpu` do probe é
  só máquina/contagem, e R-BIT pede a capacidade), se `config/preregistration/`
  tem mudança não commitada (o `.anchor.toml` lido pelo G1 não entra no
  `code_dirty` da 5.5; sujo → `DirtyCodeError`), versões das bibliotecas do caminho do gold
  que o probe não tem (o technical fecha a lista; no mínimo `arch`,
  `statsmodels`, `scipy`, `scikit-learn`, `scoringrules`, `duckdb`),
  plataforma e número de CPUs, identificação da imagem quando disponível,
  o `inference_summary` e a referência às seeds — que já estão no manifesto
  (`RefreshParameters`: MCS, Monte Carlo, permutação e bootstrap de H3) e no
  spec do cohort, e não são duplicadas.
- **Por quê:** são os itens 3–5 da §4.5 do doc de domínio (commit, ambiente,
  seeds) e o que a 8.2 usa para decidir "mesmo ambiente" (R-BIT). O probe da
  5.5 **não** ganha chaves: a inferência compara o snapshot com o ambiente
  gravado do cohort, e chave nova tiraria o `infer` do modo `strict`.
- **Fonte:** doc de domínio §4.5, §7 (DOSSIE); Sandve et al. 2013 Rules 1, 3,
  4, 6; ADR 7.1.0003 itens 2–3; `runtime_environment_probe.py`.
- **ADR:** [`8.1.0003`](../../adr/8_1_0003-judged-generation-preserved-copy-run-record-attestation.md)

### D7 — Atestação: registro versionado, tag e um comentário, por runbook

- **O quê:** depois do selo, o operador (a sessão da Stage) cria a tag
  `confirmatory-run/<preregistration_ref>` no commit da corrida e a envia;
  posta **um** comentário na #211 com o corpo que a CLI imprimiu (referência,
  `generation_digest`, status, commit, tag, `started_at`/`finished_at` do
  manifesto, prontidão e o veredito por horizonte); grava
  `config/preregistration/aapl_confirmatory-r3.judged.toml` com os campos do §4
  (`commented_at` = `created_at` do servidor) e o commita. Antes de postar,
  procura o digest nos comentários da issue (não duplica).
- **Por quê:** o comentário dá, com timestamp do servidor, o limite
  **superior** do primeiro refresh confirmatório (o refresh terminou antes do
  comentário), fechando a cadeia do ADR 6.5.0003 item 4; o limite inferior
  (refresh depois da âncora) é o G1 no código mais o `started_at` do
  manifesto, relógio local que pega o erro honesto, não um relógio forjado
  (ADR 6.5.0003 item 3) — a mesma força de prova que a 6.5 declarou; o
  digest no repositório e na issue é uma atestação **externa** ao `data_root`
  (git-ignorado), que sozinho não prova nada sobre si mesmo; a tag mantém o
  commit alcançável depois do rebase do fechamento (precedente ADR 5.5.0001 /
  6.5.0003). Publicar por código pediria port + adapter de GitHub + fake +
  contrato para um efeito único — as âncoras do pré-registro já são passo de
  runbook.
- **Fonte:** ADR 6.5.0003 itens 1, 2, 4; issue #211 (abordagem passo 5).
- **ADR:** [`8.1.0003`](../../adr/8_1_0003-judged-generation-preserved-copy-run-record-attestation.md)

### D8 — Lock de escritor durante o use case

- **O quê:** o use case adquire o lock do `data_root` (G3) e o libera em
  `finally`; o `infer` adquire e libera o seu antes.
- **Por quê:** o `RefreshGold` tem como **pré-condição** escritor único por
  partição (ADR 6.4.0005 item 6), e a preservação exige que nenhuma outra
  geração seja publicada entre o refresh e a cópia. O lock já existe e é
  usado do mesmo jeito pelo `infer`; nenhum mecanismo novo.
- **Fonte:** ADR 6.4.0005 item 6; ADR 7.1.0004 item 5.
- **ADR:** [`8.1.0001`](../../adr/8_1_0001-confirmatory-run-orchestration-guards-status-replay.md)

### D9 — Nenhum número novo; canal de emissão

- **O quê:** a 8.1 não introduz métrica: os canais de emissão são as tabelas
  gold que o `RefreshGold` já publica (com perfis, conformal e H3), o
  `ScorecardResult.as_mapping()` gravado na cópia julgada e o comentário de
  atestação.
- **Fonte:** doc de domínio §3; roadmap 8.1 DoD.

### D10 — Execução real

- **O quê:** a Task final roda `evaluate` sobre o `data_root` do checkout
  principal (`data/cohorts/aapl`, montado no container da worktree), com
  `ARTIFACTS_ROOT` contendo os 60 checkpoints; antes, cópia de segurança do
  `data_root` com sha256 (precedente dos backups `aapl-pre-7.x`); depois, uma
  segunda execução para provar o `ALREADY_JUDGED`. Roda em CPU no
  Windows/Docker.
- **Por quê:** é o DoD da Stage ("pipeline confirmatória roda do cohort
  persistido até o scorecard"); a máquina Linux saiu do projeto e a corrida é
  só CPU (technical 7.3 §7, decisão L6b).
- **Fonte:** issue #211; roadmap 8.1; technical 7.4 §7 (checkpoints).

## 8. Integrações

### Internas (com outras Stages/módulos)

- `evaluation` (6.4): `RefreshGold` ganha o cálculo do hash do silver nas
  leituras e devolve o manifesto; `GoldManifest` ganha `silver_content`;
  `ParquetGoldStore` serializa/lê o campo. Os testes da 6.4–7.3 seguem verdes
  (campo novo, nenhum número muda).
- `evaluation` (6.5): `BuildConfirmatoryScorecard` passa a usar
  `resolve_judged_revision`, mesma ordem de erros; comportamento externo
  idêntico.
- `inference` (7.1): só pela CLI (`infer` antes do use case); nenhuma aresta
  nova de import do `evaluation` para o `inference`.
- `modeling` (5.5): o `JsonCohortProgressLedger` e o probe de ambiente
  satisfazem ports do consumidor do `evaluation` por duck typing; montagem no
  composition root.
- `shared`: VO `SilverContentHash`; LAYOUT §7 passa a listá-lo entre os VOs de
  identidade (regra 6 do `check_layout.py`).
- 8.2 / 8.3: consomem `judged/<ref>/`, o `run_record.json` e o registro
  `.judged.toml` (§14).

### Externas

- **GitHub** (passo de runbook, `gh` autenticado do operador): push da tag e
  um comentário na #211; `created_at` do servidor lido da API.
- **Sistema de arquivos** (bind mount do Windows no Docker): staging + rename
  de diretório, como o gold (residual do ADR 6.4.0005 aceito: o leitor
  depende do arquivo escrito por último).

## 9. Modelo de dados

```text
<data_root>/gold/asset=AAPL/parent_sweep_id=aapl_confirmatory-r0-665f45d9169a/
├── current/                                   # geração viva (ADR 6.4.0005), substituível
│   ├── <tabela>.parquet …
│   └── MANIFEST.json                          # + silver_content (D4)
└── judged/
    └── aapl_confirmatory-r3-00fd83d9cd39/     # uma por revisão; nunca sobrescrita
        ├── generation/                        # cópia byte a byte de current/
        │   ├── <tabela>.parquet …
        │   └── MANIFEST.json
        ├── gold_model_comparison_confirmatory_scorecard.json   # ausente se BLOCKED
        ├── run_record.json                    # D6
        └── CONTENTS.json                      # escrito por último: sha256 por arquivo + generation_digest
```

`MANIFEST.json.silver_content` (forma indicativa):

```json
{
  "digest": "<sha256 combinado>",
  "tables": {"dim_run": "<sha256>", "fact_oos_predictions": "<sha256>", "...": "..."},
  "units": {"dim_run|aapl_confirmatory-r0-665f45d9169a": "<sha256>",
            "fact_oos_predictions|<run_id>|2021": "<sha256>", "...": "..."}
}
```

A chave da unidade e o local dos digests por unidade (manifesto ou arquivo ao
lado na geração) ficam para o technical; o digest combinado e os por tabela
ficam no manifesto.

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| R1 — Checkpoints fora do `ARTIFACTS_ROOT` | B | M | o `infer` falha antes de qualquer escrita (`CheckpointNotFoundError`); restaurar do backup `tft-pre-7.4-…`; pré-condição conferida na Task real (60/60) |
| R2 — `infer` sai em `tolerance` (ambiente ≠ o gravado no cohort) | M | B | política da 7.1 (ADR 7.1.0003): passa se dentro da tolerância e fica registrado no manifesto de inferência e no `inference_summary`; não bloqueia a 8.1 |
| R3 — Custo do hash do silver (≈ 11 M linhas consumidas) | M | M | digest por unidade (memória limitada a uma unidade); medido na corrida real (tempo por etapa no log do refresh); se inviável, `[finding]` e revisão do technical antes de rodar |
| R4 — Corrida interrompida | M | B | nada selado ⇒ re-execução completa, determinística; sobras de staging removidas |
| R5 — Rename de diretório no bind mount do Windows | B | M | selo = `CONTENTS.json` por último; `find` confere o digest; residual do ADR 6.4.0005 |
| R6 — Desfecho `BLOCKED` no real | B | A | é resultado confirmatório (I5): selado, atestado e relatado; o DoD de veredito fica não cumprido e a Stage para com `[finding]`; qualquer correção vira desvio decidido pelo humano em issue própria |
| R7 — Defeito descoberto depois do selo | B | A | desvio do plano (doc de domínio §4.6): a geração julgada não é trocada; nova issue; listado no dossiê |
| R8 — Commit da corrida inalcançável depois do rebase | M | M | tag `confirmatory-run/<ref>` (D7); `code.src` (hash de conteúdo de `src/`) sobrevive ao rebase |
| R9 — Cegamento quebrado durante o desenvolvimento | B | A | I12: só silver sintético até a Task real; a Task real confere que não existe `gold/` no `data_root` antes de rodar |
| R10 — r3 alterada em `HEAD` | B | A | G1 recusa (hash ≠ esperado) antes de qualquer efeito |
| R11 — Comentário duplicado | B | B | runbook procura o digest nos comentários antes de postar |
| R12 — Tipo numérico do leitor real (DuckDB → pandas, `seed` `Int64` anulável) diferente do medido pelo pyarrow | M | M | o VO normaliza `int`/`float` e recusa outros tipos; teste com o leitor real sobre silver sintético (A2) |

## 11. Critérios de aceitação

Código (silver sintético; nenhum teste toca o cohort real):

- [ ] **A1** — `SilverContentHash`: valor fixo (golden) para um payload pequeno;
  invariante à ordem das linhas e das colunas; floats exatos (dois valores
  float32 vizinhos com |x| < 10⁻⁴ dão hashes distintos); `numpy.int64`/`int`
  e `numpy.float64`/`float` de mesmo valor dão o mesmo hash; `created_at_utc`
  diferente não muda o hash; `None` aceito;
  NaN/±inf → `ValueError`; construtor cru valida `validate_sha256_hex`.
- [ ] **A2** — `RefreshGold` grava `silver_content` no manifesto: duas
  execuções sobre o mesmo silver dão o mesmo digest; mudar um `value_raw` de
  uma linha consumida muda o digest daquela unidade, da sua tabela e o
  combinado, e nenhum outro; acrescentar linhas de outro `parent_sweep_id` na
  mesma partição não muda nada; dividir a mesma tabela em outros arquivos não
  muda nada; as tabelas gold são idênticas às de antes da mudança (mesmos
  testes da 6.4–7.3 verdes); `RefreshGoldResult.manifest` igual ao publicado.
- [ ] **A3** — `resolve_judged_revision` extraído: os testes do
  `BuildConfirmatoryScorecard` passam sem alteração de asserção.
- [ ] **A4** — Ordem das guardas (fakes): cadeia quebrada, hash divergente,
  revisão sem âncora, código ou `config/preregistration/` sujo e geração
  julgada de outra revisão na partição → exceção nomeada com **zero** `publish` no
  gold e zero escrita no `JudgedGenerationStore`; lock liberado em toda saída
  depois de adquirido.
- [ ] **A5** — Replay: geração julgada selada e íntegra → `ALREADY_JUDGED`,
  zero chamadas ao refresh e ao scorecard; um byte alterado na cópia →
  `JudgedGenerationTamperedError`; sobra de staging → removida e corrida
  completa.
- [ ] **A6** — `JudgedGenerationStore` (contrato `[fake, real]`): `preserve`
  copia `current/` byte a byte, grava os documentos e `CONTENTS.json` por
  último; `generation_digest` recomputável a partir dos arquivos; manifesto
  copiado ≠ `expected_manifest` → `JudgedGenerationMismatchError` sem selo;
  `preserve` sobre selada → `JudgedGenerationExistsError` sem tocar nada.
- [ ] **A7** — Caminho `BLOCKED`: silver sintético que bloqueia → status
  `BLOCKED`, cópia selada sem scorecard, checks que falharam no
  `run_record.json`; segunda execução → `ALREADY_JUDGED`.
- [ ] **A8** — `EvaluationEnvironment` (contrato): todas as chaves do D6
  presentes (inclusive a capacidade de CPU), `commit` com 40 hex, `code_dirty ∈ {"true","false"}`; o probe da
  5.5 inalterado (mesmo conjunto de `REQUIRED_KEYS`).
- [ ] **A9** — Integração
  `tests/integration/features/evaluation/test_run_confirmatory_evaluation.py`
  (silver sintético com revisão de teste ancorada com `[conformal]` e `[h3]`,
  `ParquetGoldStore` e store julgado reais): `JUDGED`; o JSON do scorecard
  na cópia é igual a `ScorecardResult.as_mapping()`; as tabelas em
  `judged/<ref>/generation/` são byte a byte as de `current/`; o manifesto da
  cópia tem `silver_content`; `started_at` ≥ `anchored_at` da revisão de teste.
- [ ] **A10** — CLI `evaluate` (e2e sintético): `infer` antes do use case;
  `infer` com checkpoint faltando → exit 2 e nenhum diretório `gold/`;
  sucesso → imprime status, digest e o corpo da atestação.
- [ ] **A11** — `make check` verde (lint, mypy, layout com o VO novo na regra 6
  e no LAYOUT §7, import-linter sem aresta nova `evaluation → inference`,
  fake-parity, port-coverage dos ports novos, docs).

Execução real (cohort `aapl_confirmatory-r0-665f45d9169a`, r3):

- [ ] **A12** — Pré-condições registradas no technical §7 antes de rodar: 60/60
  checkpoints do confirmatório em `ARTIFACTS_ROOT`; nenhum `gold/` no
  `data_root`; backup do `data_root` com sha256 conferido; commit limpo.
- [ ] **A13** — `evaluate` roda até o fim: `infer` com 60 runs (modo e max |Δ|
  registrados), status `JUDGED` ou `BLOCKED`, `judged/aapl_confirmatory-r3-00fd83d9cd39/`
  selado; com `JUDGED`, o scorecard gravado traz a `preregistration_ref` da
  r3, veredito por horizonte, `academic_decision_ready` e as razões, e o
  manifesto traz `silver_content` cobrindo `dim_run`, `fact_oos_predictions`,
  `fact_permuted_predictions`, `fact_vsn_weights` e o realizado, e as tabelas
  conformais e de H3 com contagem de linhas registrada; com `BLOCKED`, o
  `silver_content` cobre só o que o refresh leu (`dim_run`,
  `fact_oos_predictions` do cohort e o realizado) e a Stage registra
  `[finding]` e para para decisão humana (I5); `started_at` > `2026-10-21T17:41:23Z`.
- [ ] **A14** — Integridade: `generation_digest` recomputado de fora do código
  (sha256 dos arquivos listados em `CONTENTS.json`) igual ao gravado.
- [ ] **A15** — Segunda execução de `evaluate` → `ALREADY_JUDGED` com o mesmo
  digest, sem nova publicação em `current/` (manifesto de `current/`
  inalterado).
- [ ] **A16** — Atestação: tag `confirmatory-run/aapl_confirmatory-r3-00fd83d9cd39`
  enviada; **um** comentário na #211 com o digest, cujo `created_at` é
  posterior ao `anchored_at` da r3; `config/preregistration/aapl_confirmatory-r3.judged.toml`
  commitado com os campos do §4; entrada no technical §7 com os tempos por
  etapa do refresh (inclusive o custo do hash do silver).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4, com a
  forma exata dos campos fechada no technical (indicado onde).
- [x] Toda decisão em §7 tem fonte rastreável? — sim, D1–D10.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)?
  — GitHub por `gh` autenticado do operador (tag + comentário, D7); sistema de
  arquivos com o mesmo protocolo staging + rename do gold.
- [x] Decisões com alternativa real descartada têm ADR escrito? — 8.1.0001
  (orquestração, guardas, status, replay, lock), 8.1.0002 (hash do silver),
  8.1.0003 (geração julgada, registro de execução, atestação).
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 6.5, 6.6,
  7.1, 7.2, 7.3 `done`; gate de domínio do Step 8 aceito (#208).
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)?
  — estimativa: VO; hash no refresh + manifesto; extração do resolver; port +
  fake do store julgado; adapter + contrato; port + real do ambiente; use case +
  DTOs; integração; CLI + wiring + e2e; corrida real + atestação ≈ 10–12.
- [x] Riscos críticos têm mitigação plausível? — §10 (R6, R7, R9 de impacto
  alto têm resposta definida sem re-julgar).
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — (i) identidade/fingerprint do silver: concern transversal tratado no lugar geral — VO de identidade em `shared/` pela regra única do LAYOUT §7, calculado pelo dono da leitura (o `RefreshGold`), não um hash ad hoc no orquestrador; generalizar o `DatasetContentFingerprint` foi a opção mais geral avaliada e recusada porque mudaria uma identidade ancorada (D4); (ii) a lacuna da #163 (o `RunId` não carrega impressão digital do dado de treino) **não** é capturada aqui: o hash do silver identifica o que o gold leu, e a amarração checkpoint ↔ dado segue na #163; (iii) a cópia julgada reusa o protocolo staging + rename do `ParquetGoldStore` e o hash por streaming do checkpoint (ADR 7.1.0004), sem mecanismo novo de atomicidade; (iv) lock: reusa o ledger da 5.5; (v) comentário: passo de runbook como as âncoras, sem integração nova; (vi) nenhuma métrica nova (D9).
- [x] A Stage calcula alguma métrica sobre o cohort real antes da âncora? —
  não: G1 exige a r3 ancorada antes do refresh (I3), e só a Task real roda
  sobre o cohort (I12).
- [x] A corrida pode ser re-julgada escolhendo o resultado? — não: uma geração
  julgada por partição do cohort (recusa revisão nova), sem flag de re-julgamento (I4, I5).

## 13. Questões em aberto

Nenhuma crítica. Ficam para o technical, sem mudar contrato: a chave exata das
unidades do hash do silver e se os digests por unidade vão no manifesto ou num
arquivo ao lado; a lista final de bibliotecas do `run_record.json` e como a
identificação da imagem chega ao container; a forma dos Protocols do refresh e
do scorecard no `__init__` do use case.

## 14. O que fica para a 8.2 e a 8.3

- **8.2 (reprodução, parte i):** re-executa silver → gold → scorecard em
  **destino separado** a partir dos artefatos persistidos; usa o
  `silver_content` do manifesto julgado como pré-condição de identidade (igual
  ⇒ mesma entrada), o `run_record.json` para decidir "mesmo ambiente" (R-BIT)
  e o diff de commit contra o da corrida (R-BIT-COMMIT); compara classe por
  classe contra `judged/<ref>/generation/` e o scorecard julgado. Como montar o
  `RefreshGold`/scorecard sobre outra raiz de gold é do technical da 8.2 (os
  dois já recebem o store por injeção).
- **8.2 (equivalência, parte ii):** lê as tabelas da cópia julgada; nada da
  8.1 muda por ela.
- **8.3:** plots e dossiê a partir de `judged/<ref>/` (nunca de `current/`), do
  `run_record.json`, do `.judged.toml` e das âncoras r0–r3.

## 15. Referências

- [`../../overview.md`](../../overview.md) — §4 (H1–H3, reprodutibilidade)
- [`../../roadmap.md`](../../roadmap.md) — Stage `8.1-confirmatory-run`, 8.2, 8.3
- Doc de domínio [`reproduction-equivalence-and-reporting`](../../domain/evaluation/reproduction-equivalence-and-reporting.md) §2.1–§2.2, §3, §4.2, §4.5, §4.6, §9 (R-CAMADAS, R-PRESERVA)
- Doc de domínio [`probabilistic-forecast-evaluation`](../../domain/evaluation/probabilistic-forecast-evaluation.md) §8 (B-ORDEM, veredito por horizonte)
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `8_1_`)
- ADRs consumidos: 1.4.0001, 5.5.0001, 5.5.0004, 6.4.0005, 6.5.0001, 6.5.0003,
  6.5.0005, 6.5.0007, 6.6.0002, 7.1.0002–7.1.0004, 7.2.0003, 7.3.0001,
  7.3.0005, 0.0.0053, 0.0.0060–0.0.0062
- Issue #211 §Referências (pesquisa: Sandve et al. 2013; DVC; MLflow; Sacred;
  GNU make; *Pro Git* §10.2; `parquet.thrift`)
