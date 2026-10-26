---
title: Concept — Stage 8.4 — Job de cohort de produção (rodada que retreina o candidato em dado novo, sob um data_root próprio, e publica o ponteiro que a API serve)
description: Comando idempotente `production-round` que, sob um lock da raiz de produção, copia os brutos para a raiz de uma rodada datada, materializa o dataset, deriva do modelo de produção versionado o spec congelado da rodada (hiperparâmetros herdados do cohort confirmatório, impressão digital do dado novo), retreina baselines, GBM e as seeds do TFT num único fold, confere a corrida pela contagem e só então troca, de forma atômica e monotônica, o arquivo `serving.env` com `DATA_ROOT` e `SERVING_COHORT_FILE`; a API serve a rodada nova depois de recriada com esse arquivo, sem mudança no caminho de serviço
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; ao rodar ou agendar o job de produção; ao trocar o cohort servido pela API; ao questionar por que a rodada retreina em vez de usar os checkpoints do confirmatório, por que não publica gold, ou como a janela de publicação do ADR 6.4.0005 deixa de existir
keywords: [concept, production-cohort-job, inference, modeling, scheduler, batch-prediction, retraining, data-root, serving-pointer, atomic-switch, idempotency, cohort-spec, frozen-hyperparameters]
status: done
created_at: 2026-10-25
updated_at: 2026-10-25
stage_id: 8.4-production-cohort-job
stage_title: Job de cohort de produção
step_id: 8
step_title: Reprodução, equivalência e relatório
depends_on: [7.4-inference-api, 8.1-confirmatory-run, 8.3-plots-and-final-report]
---

# Concept — Stage 8.4 — Job de cohort de produção

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

A API da 7.4 serve, sem rodar o modelo, as predições `split = "test"` já
gravadas de **um** cohort configurado (concept 7.4 D1, D10; ADR 7.4.0001 itens
1 e 8). Para servir datas posteriores ao teste do cohort confirmatório é
preciso **outro** cohort, com dado, treino e predição próprios, sob outro
`data_root`, mantido por um job agendado (B1 do humano na 7.4). Esta Stage
decide a forma desse cohort, o retreino, o escopo do gold, onde o agendamento
roda e como a troca do cohort servido evita a janela de publicação do ADR
6.4.0005, e entrega o job.

**Execução autônoma.** O dono delegou a Stage sem paradas (sessão de
2026-10-25). As decisões E e C fecham por evidência ou convenção (skill
`evidence-resolution`). As decisões P foram **tomadas** pela sessão com o
motivo escrito e estão marcadas **[P — a ratificar pelo dono]** (D1, D2, D3,
D4, D7, D9). Cada uma é reversível sem mudar a API.

## 1. Escopo

### Dentro do escopo

- **Modelo de produção versionado**: `config/cohorts/aapl_production.toml`,
  um `CohortSpec` no schema de sempre, **sem** `dataset_fingerprint` (logo, não
  congelado e recusado pelo `run` confirmatório). Herda do confirmatório r0 os
  hiperparâmetros congelados, a proveniência dos sweeps, o feature set, os
  horizontes, a grade de quantis e as baselines. Difere dele no nome, na
  geometria (`n_folds = 1`), nas seeds e no `dataset_start` declarado (D1, D2,
  D7).
- **Spec da rodada**: o modelo de produção mais a impressão digital do grid
  materializado **da rodada**, gravado em `<raiz da rodada>/cohort.toml`. É um
  `CohortSpec` congelado comum: o `cohort_id` sai do hash dele (ADR 5.5.0001), o
  `verify` o confere e a API o carrega como `SERVING_COHORT_FILE` (D1).
- **Corrida da rodada**: o `RunConfirmatoryCohort` montado pela composition
  root para produção, com uma única diferença declarada: os hiperparâmetros
  herdados de sweeps feitos sobre **outro** dado não são recusados. Todas as
  outras pré-condições valem: lock, impressão digital observada = declarada,
  `feature_set_hash`, `pipeline_version`, device, geometria, árvore limpa,
  ambiente da retomada. A foto do ambiente usa o modelo de produção versionado
  como arquivo do cohort (D5).
- **Comando `production-round`** (CLI, idempotente): sob o lock da raiz de
  produção, copia os brutos para a raiz da rodada, materializa, deriva e grava
  o spec da rodada, corre, verifica e publica o ponteiro. Repetido com o mesmo
  `--round`, retoma (D6).
- **Ponteiro publicado**: `<raiz de produção>/serving.env` com `DATA_ROOT` e
  `SERVING_COHORT_FILE` da rodada verificada mais recente, trocado por
  `os.replace` (D8).
- **Runbook** do job: agendamento (cron no host ou Agendador de Tarefas do
  Windows), os comandos exatos da rodada e da troca do cohort servido
  (recriar o container da API com `--env-file`), retomada, rollback e limpeza
  de rodadas antigas (D4, D8).
- **Execução real** de duas rodadas (brutos cortados em 2025-06-30 e brutos
  inteiros) com a API servindo cada uma (CA6).

### Fora do escopo (explicitamente)

- Mudar o contrato da API (`POST /inference/run`, schema 1) ou o caminho de
  serviço (`features/inference/`, `shared/infrastructure/http/`,
  `serve_inference_for`, `register_http_routes`).
- Predição online por pedido (rejeitada no ADR 7.4.0001, alternativas A e B).
- Escrever no `data_root` do cohort confirmatório, ler métrica dele ou tocar a
  geração julgada, as tags `confirmatory-run/*` e o pré-registro.
- **Gold de produção** (conformal e H3) — D3. Sem ele, a API serve os blocos
  `unavailable` ("gold não publicado"), comportamento já contratado na 7.4.
- **Aquisição dos brutos** a partir dos provedores (yfinance, Alpha Vantage).
  Os fetchers existem no `market_data`, mas nenhum está ligado ao runner. O job
  lê os brutos de um diretório que o operador mantém (D9). Fica na issue #241.
- **Servir a decisão de hoje** (alvo ainda não realizado). O persister só grava
  decisões cujo alvo `t + h` cabe no painel (`CohortGeometry.expected_prediction_rows`),
  então a rodada serve até a sessão `T − h`. Prever o pregão seguinte é outro
  modo de predição. Fica na issue #242 (D10).
- Orquestrador (Airflow, Prefect, Dagster), recarga a quente da configuração
  da API, mudança no `docker-compose.yml` e retenção automática de rodadas
  antigas (D4, D8).

### Vínculo com o roadmap

Última Stage do Step 8 (roadmap, bloco "Stage 8.4 — `8.4-production-cohort-job`",
criado pelo PR #239). Ela transforma a API da 7.4, que serve a reprodução do
estudo, numa API que pode servir datas novas, sem misturar dado de produção com
a evidência confirmatória, que a 8.3 fechou. Overview §3: a "API de inferência
fina" está no escopo; o re-treino reusa só os brutos.

## 2. Objetivo da Stage

Uma rodada do comando `production-round` deixa sob uma raiz própria um cohort
congelado, treinado e verificado sobre o dado mais recente, e troca de forma
atômica o ponteiro `serving.env`. A API, recriada com esse ponteiro, serve as
datas da rodada sem mudança no caminho de serviço, e nenhuma rodada escreve no
`data_root` do cohort confirmatório nem no de outra rodada.

## 3. Contexto e premissas

### Contexto

- **A API serve qualquer cohort congelado.** `serve_inference_for(cohort_path)`
  (composition root) lê o arquivo, exige `is_frozen()`, calcula o `cohort_id`
  pelo `CohortHash` e monta o `ServeInference` sobre o silver e o gold do
  `DATA_ROOT`. O `ServeInference` é montado **uma vez, na subida** (concept 7.4
  D8). Trocar de cohort, portanto, é trocar duas variáveis de ambiente e subir
  o processo de novo.
- **O cohort confirmatório é congelado e não aceita dado novo.** Uma sessão a
  mais muda o `DatasetContentFingerprint`, cujo hash inclui os timestamps, e o
  runner recusa (`DatasetMismatchError`, `cohort_unit_runner.check_cohort_declarations`).
- **O `run` confirmatório recusa hiperparâmetros de outro dado.**
  `check_cohort_declarations` exige `provenance.dataset_fingerprint ==
  dataset_fingerprint` ("sweeps ran on a different dataset than the one declared
  for the run"). No confirmatório essa é a garantia de que o sweep viu o mesmo
  dado do cohort (I4 da 5.5). Na produção, os hiperparâmetros **são** de outro
  dado, por desenho (D2).
- **O probe do ambiente exige o arquivo do cohort versionado.**
  `GitRuntimeEnvironmentProbe` lê `git rev-parse HEAD:<arquivo do cohort>` e
  recusa arquivo fora do repositório. Um spec gerado por rodada, fora do git,
  não passa. Por isso a foto usa o modelo de produção versionado (D5).
- **O persister não grava decisão sem alvo realizado.** O bloco de teste são
  as últimas `test_size` sessões do grid. No último fold, as decisões a menos de
  `h` sessões do fim do painel não têm linha
  (`CohortGeometry.expected_prediction_rows`): com 252 sessões, h+1 serve 251
  decisões e h+7 serve 245.
- **Treino e decisão ficam afastados pela geometria.** O fold é
  `treino | gap | early_stop | gap | calib | gap | teste`
  (`cohort_geometry.py`). Com 252/252/252 e gap = h máx + embargo = 14, o treino
  termina 547 sessões antes da primeira decisão servida e 797 antes da última.
  É o mesmo afastamento de todos os folds que o estudo avaliou.
- **Tracking.** O `TrainTft` registra parâmetros e `val_loss` no MLflow
  (`Settings.mlflow_tracking_uri`, padrão `sqlite:///mlruns.db` relativo ao
  diretório de trabalho) e copia o checkpoint para o store de artefatos do
  MLflow, que com backend SQLite fica em `./mlruns/` do diretório de trabalho.
- **Custo medido do retreino.** A 5.5 mediu 1,5–2,9 h por seed do TFT nos 6
  folds (runbook do cohort, Step 9), com baselines em 823 s e GBM em 235 s.
  Medido nesta sessão, para um fold no último corte (D2): 1.642 s (~27 min) para uma seed do TFT num fold, sobre o dataset do
  confirmatório, com 6 CPUs no container e outro gate disputando a máquina
  (`[measurement]` no §7 do technical).
- **Brutos.** Os três arquivos de entrada vivem sob o `data_root`
  (`raw/market/candles`, `raw/news`, `processed/fundamentals`), lidos pelos
  fetchers Parquet da 5.5. O `materialize` ingere e roda o FinBERT, que exige o
  extra `sentiment` (~13–15 min no AAPL). A ingestão acrescenta ao bronze e
  recusa chave repetida (`DuplicateKeyError`). Os brutos disponíveis vão até
  2025-12-31, o mesmo fim do dataset confirmatório.
- **Compose.** O serviço `app` do `docker-compose.yml` lê só `.env`, monta o
  venv de dev (sem o extra `sentiment`) e roda o uvicorn com `--reload`. O
  `--env-file` do `docker compose` só alimenta a interpolação do arquivo, não o
  ambiente do container.

### Premissas

- **PRE-1:** o operador (ou um processo fora do job) mantém o diretório de
  brutos atualizado. Sem brutos novos, uma rodada nova reproduz o mesmo dado
  sob outra raiz (correto, só redundante).
- **PRE-2:** o job roda na imagem `financial_forecasting-app:dev` com um volume
  de venv que tem o extra `sentiment` e um cache do Hugging Face (o mesmo
  arranjo do runbook do cohort, Step 2), a partir da raiz de um checkout limpo
  (exigência do probe da 5.5).
- **PRE-3:** o job e a API montam a raiz de produção no **mesmo caminho** do
  container, porque o `serving.env` grava caminhos absolutos do container.

### Dependências

- `7.4-inference-api`: `serve_inference_for`, `Settings.serving_cohort_file`,
  `DATA_ROOT`, o 404 e os blocos `unavailable`.
- `8.1-confirmatory-run`: fecha o uso do cohort confirmatório e da geração
  julgada. Esta Stage não os toca.
- `8.3-plots-and-final-report`: o relatório está fechado, então nenhum dado de
  produção se mistura à evidência.
- `5.5-confirmatory-retrain` (indireta): `CohortSpec`, `cohort_file`,
  `RunConfirmatoryCohort`, `verify`, `materialize`, ledger e lock.

## 4. Contratos

### Introduzidos

- **`config/cohorts/aapl_production.toml`** (arquivo versionado, schema do
  `CohortSpec`): modelo de produção, sem `dataset_fingerprint`. Campos iguais
  aos do confirmatório r0, exceto `name = "aapl_production"`,
  `geometry.n_folds = 1`, `seeds = [1, 2, 3]` e `dataset_start = 2010-04-20`.
  Um teste compara campo a campo com o confirmatório.
- **`CohortSpec.production_round(dataset_fingerprint: str) -> CohortSpec`**
  (método do DTO): devolve o spec congelado da rodada. Recusa (`ValueError`)
  um modelo que já tenha `dataset_fingerprint`, ao qual falte qualquer outro
  campo de congelamento (`tft_params`, `gbm_params`, `provenance`, `seeds`,
  `sweep.n_trials`), ou uma impressão digital que não seja sha256 hex.
- **`RunConfirmatoryCohort(..., inherited_hyperparameters: bool = False)`** e
  **`check_cohort_declarations(..., inherited_hyperparameters: bool = False)`**:
  com `True`, a igualdade entre a impressão digital dos sweeps e a do dado
  declarado não é exigida. O resto do I4 continua valendo. Só a fábrica de
  produção da composition root passa `True`.
- **`ApplicationDependencies.production_cohort_for(template_path: Path, device:
  str) -> RunConfirmatoryCohort`** (composition root): o runner com
  `inherited_hyperparameters=True` e o probe sobre o arquivo do modelo de
  produção.
- **`ApplicationDependencies.writer_lock_for(root: Path) -> CohortProgressLedger`**
  (composition root): o lock de escritor único do ledger da 5.5 sobre uma raiz
  qualquer, usado como lock da raiz de produção (só `acquire_writer`/`release_writer`).
- **Subcomando `production-round`** (`cli.py`):

  ```
  python -m financial_forecasting.cli production-round \
      --production-root <dir> --round <AAAA-MM-DD[.N]> --raw-root <dir> \
      --cohort config/cohorts/aapl_production.toml [--break-stale-lock]
  ```

  Exit 0 com a rodada verificada (publicada, ou não publicada por ser mais
  antiga que a do ponteiro, com a linha `not published: …`); 1 se o `verify`
  da rodada divergir (nada é publicado); 2 em erro. A saída tem uma linha por
  etapa e termina em `published <cohort_id> → <production-root>/serving.env`
  quando publica.
- **`Settings` da rodada**: o comando monta o processo com
  `data_root = <rodada>`, `artifacts_root = <rodada>/artifacts` e
  `mlflow_tracking_uri = sqlite:///<rodada>/mlruns.db`; os demais campos vêm do
  ambiente.
- **Leiaute da raiz de produção** (formato persistido):

  ```
  <production-root>/
  ├── .writer.lock                 # lock do job (um por raiz de produção)
  ├── serving.env                  # DATA_ROOT=<abs>/rounds/<id>
  │                                # SERVING_COHORT_FILE=<abs>/rounds/<id>/cohort.toml
  └── rounds/<id>/
      ├── raw/…, processed/fundamentals/…   # cópia dos brutos
      ├── .materialized                    # marca: materialização concluída
      ├── bronze/, processed/dataset_tft/, silver/
      ├── artifacts/                       # checkpoints e ledger da rodada
      ├── mlruns.db                        # tracking da rodada
      └── cohort.toml                      # spec congelado da rodada
  ```

### Consumidos

- **`CohortSpec`, `cohort_file.load/parse/dump`, `CohortHash`** — Stage 5.5.
- **`RunConfirmatoryCohort`, `check_cohort_declarations`, `load_training_grid`,
  `grid_fingerprint`, `cohort_commands.verify`, `CohortProgressLedger`
  (lock)** — Stage 5.5.
- **`_materialize` (ingestão local + `BuildDataset`)** — Stages 2.2, 3.5, 5.5.
- **`serve_inference_for`, `Settings.serving_cohort_file`, `Settings.data_root`,
  `create_app`** — Stage 7.4.
- **`validate_sha256_hex`** — LAYOUT §7.

## 5. Invariantes e regras

- **I1 — Isolamento do confirmatório.** O comando recusa uma raiz de produção
  igual a `<repo_root>/data/cohorts/`, dentro dela ou que a contenha (é onde
  vivem o cohort confirmatório e o de ablação, convenção do `cli.py`),
  comparando os caminhos resolvidos sem diferenciar maiúsculas. Dentro da raiz
  de produção, uma rodada só escreve em `rounds/<id>/`, no `serving.env` e no
  lock. Fora dela, o job só escreve a cópia de artefato do MLflow em `./mlruns/`
  do diretório de trabalho, como todo treino do projeto (git-ignorada, nunca
  lida por ninguém).
- **I2 — Rodada imutável depois de publicada.** O `serving.env` só aponta para
  uma rodada com `verify` OK. Nenhuma rodada reescreve a raiz de outra.
- **I3 — Ponteiro atômico.** O `serving.env` é escrito num temporário de nome
  único no mesmo diretório (`tempfile.mkstemp`) e trocado por `os.replace`.
- **I4 — Spec da rodada derivado, nunca editado.** O `cohort.toml` da rodada é
  `production_round(<impressão digital observada>)` do modelo versionado. Se o
  arquivo já existe e difere do derivado, o comando para
  (`ProductionRoundError`) em vez de sobrescrever.
- **I5 — Mesmas garantias de corrida.** Lock de escritor único da rodada,
  impressão digital observada = declarada, `feature_set_hash`,
  `pipeline_version`, device, geometria, árvore limpa e ambiente da retomada
  valem como no confirmatório. Só a igualdade "dado dos sweeps = dado do
  cohort" é dispensada, e só pela fábrica de produção.
- **I6 — Idempotência e retomada.** Enquanto código, ambiente e modelo não
  mudaram, repetir o comando com o mesmo `--round` não refaz o que terminou:
  materialização marcada é pulada, spec igual é mantido, unidades concluídas são
  `skipped_completed`, o `verify` roda de novo e o ponteiro só é regravado se
  a rodada continuar sendo a mais recente (I9). Se algo mudou, o erro do runner
  aparece e a remediação é uma rodada nova (`--round <data>.1`), nunca subir a
  `revision` do modelo.
- **I7 — Brutos da rodada fixos.** Na primeira execução, os brutos são
  copiados para a raiz da rodada. Depois da marca `.materialized`, a rodada usa
  só a cópia; se o `--raw-root` atual difere dela, o comando avisa numa linha e
  segue.
- **I8 — Sem avaliação.** O job não roda `RefreshGold` nem calcula métrica de
  avaliação fora da amostra (pinball, cobertura, DM, MCS); o módulo de comandos
  de produção não importa `features.evaluation`. O `val_loss` do early stopping
  é parte do treino.
- **I9 — Ponteiro monotônico e serializado.** O comando inteiro (cópia,
  materialização, corrida, verificação e publicação) roda sob o lock da raiz de
  produção, então duas rodadas nunca correm juntas. A rodada só troca o ponteiro
  se não houver ponteiro, se ele já apontar para ela, ou se o nome dela for
  posterior ao da rodada apontada (ordem por data e sufixo). Uma rodada mais
  antiga termina verificada e não publica.

## 6. Casos de erro e exceções

| Situação | Comportamento |
|---|---|
| `--round` fora de `AAAA-MM-DD` ou `AAAA-MM-DD.N` (inclusive `.`, `..`, `/`) | `ValueError` antes de criar diretório (exit 2) |
| `--raw-root` sem um dos três brutos | `ProductionRoundError` nomeando o arquivo ausente (exit 2), nada criado |
| raiz de produção igual, dentro ou contendo `<repo_root>/data/cohorts/` | `ProductionRoundError` (exit 2), nada criado |
| outro job segura o lock da raiz de produção | `CohortRunLockedError` nomeando o dono (exit 2), nada apagado; `--break-stale-lock` só depois de confirmar que o dono morreu |
| materialização interrompida (sem `.materialized`) | na próxima execução, as camadas derivadas da rodada (`bronze/`, `processed/`) e os brutos copiados são apagados e refeitos |
| `--raw-root` difere da cópia de uma rodada já materializada | aviso numa linha; a rodada segue com a cópia |
| modelo de produção já congelado ou incompleto | `ValueError` de `production_round` (exit 2) |
| `cohort.toml` da rodada diferente do derivado | `ProductionRoundError` (exit 2), arquivo intacto |
| dado materializado diferente do declarado na retomada | `DatasetMismatchError` do runner (exit 2) |
| árvore suja; ambiente, código ou modelo diferente na retomada | `EnvironmentMismatchError` (exit 2); remediação: rodada nova |
| unidade parcial ou corrompida (`PartialCohortUnitError`, `CompletedUnitCorruptedError`, `UnitOutputMismatchError`) | exit 2; remediação: rodada nova (`--round <data>.1`), não `revision += 1` |
| `verify` da rodada com divergência | exit 1, ponteiro **não** trocado |
| rodada mais antiga que a do ponteiro | exit 0 com `not published: …`; ponteiro intacto |
| falha ao gravar o ponteiro | exit 2, ponteiro anterior intacto (I3) |
| `run` confirmatório chamado com o modelo de produção | `CohortNotFrozenError` (sem `dataset_fingerprint`) |

## 7. Decisões técnicas relevantes

### D1 — Forma: rodada = cohort congelado próprio, derivado de um modelo versionado [P — a ratificar pelo dono]

- **O quê:** cada rodada é um cohort novo, com raiz própria
  (`<production-root>/rounds/<id>/`) e spec congelado próprio (o modelo de
  produção mais a impressão digital do grid da rodada). O `cohort_id` muda
  sozinho quando o dado muda, porque o hash do spec inclui a impressão digital
  (`aapl_production-r0-<hash12>`). A `revision` do modelo só sobe quando o
  modelo muda (hiperparâmetros, geometria, seeds). A API **não** recarrega a
  configuração a quente: o container é recriado com o ponteiro novo. Rodadas de
  produção não têm âncora pública (tag + comentário) como o confirmatório: elas
  não sustentam claim nenhum.
- **Por quê:** é a forma que reusa o que existe sem mudar contrato. O spec da
  rodada é um `CohortSpec` congelado comum, então o `cohort_id`, o `verify` e o
  `serve_inference_for` funcionam sem mudança. A alternativa "um cohort de
  produção que cresce" exigiria escrita incremental no silver de uma raiz que a
  API lê ao mesmo tempo, e o `cohort_id` (hash do spec) mudaria a cada rodada
  de qualquer jeito. Recarga a quente mudaria o caminho de serviço
  (`register_http_routes`, `create_app`), o que o critério 3 da #202 proíbe.
- **Fonte:** issue #202 (incerteza 1); composition root
  `serve_inference_for`; ADR 5.5.0001 (identidade pelo hash do spec);
  concept 7.4 D8.
- **ADR:** [`8_4_0001`](../../adr/8_4_0001-production-round-own-frozen-cohort-retrained-without-gold.md) itens 1–3.

### D2 — Retreino a cada rodada, num único fold [P — a ratificar pelo dono]

- **O quê:** a rodada retreina baselines, GBM e as seeds do TFT com os
  hiperparâmetros congelados do confirmatório r0, na geometria do confirmatório
  com `n_folds = 1` (treino, early stopping, calibração e teste com os mesmos
  tamanhos e embargo). O bloco de teste servido são as últimas 252 sessões do
  grid (sem as `h` finais, D10). Não há sweep novo.
- **Por quê:** predizer com os checkpoints congelados do confirmatório exigiria
  (a) um modo novo no port da 7.1, que só prediz partições inteiras por fold;
  (b) uma identidade de run para linhas de teste que nenhum treino da rodada
  produziu, contra a regra de gravar a proveniência do que é servido (Sandve et
  al. 2013, regra 1; ADR 7.1.0003 rejeitou regravar o teste); e (c) servir, a
  cada rodada, um modelo cujo treino termina no corte do fold 5 do
  confirmatório e envelhece sem limite. O retreino reusa o runner existente sem
  modo novo. Com um fold só, o custo cai para ~1 h 45 min (FinBERT ~15 min, baselines e GBM em minutos, três seeds × ~27 min) por rodada
  (medido, §3). Um fold só basta porque a produção não estima desempenho: ela
  serve o bloco mais recente. A geometria fica a do confirmatório, então o
  afastamento entre o fim do treino e cada decisão servida (547 a 797 sessões,
  §3) é o mesmo dos folds que o estudo avaliou: o modelo servido é o que foi
  avaliado, no mesmo regime de antecedência. Encolher `val`/`calib` deixaria o
  modelo mais fresco ao custo de servir um regime que ninguém avaliou; fica
  como opção do dono. Repetir o sweep a cada rodada mudaria os hiperparâmetros
  que o estudo avaliou e custa ~10 h (runbook do cohort, Step 7).
- **Fonte:** issue #202 (incerteza 2); ADR 7.4.0001 Alternativa A; ADR
  7.1.0001; runbook `confirmatory-cohort-aapl` Steps 7 e 9;
  `cohort_geometry.py`; medição desta Stage (§7 do technical, `[measurement]`).
- **ADR:** [`8_4_0001`](../../adr/8_4_0001-production-round-own-frozen-cohort-retrained-without-gold.md) item 4.

### D3 — Sem gold de produção [P — a ratificar pelo dono]

- **O quê:** a rodada não publica gold. A API serve a grade nativa de cada seed
  com os blocos de conformal e explicabilidade `unavailable` ("gold não
  publicado"), como já contratado na 7.4 (ADR 7.4.0001 item 5).
- **Por quê:** o gold do conformal exige uma revisão de pré-registro com
  `[conformal]` para o cohort de produção e o `infer` da 7.1 para gravar a
  partição `calib`. O de H3 exige o cohort de ablação, que custou dias de
  computação (ADR 7.3.0006/7.3.0007). Nenhum dos dois é necessário para servir
  as predições, que é o que a #202 pede. Sem gold, a janela de publicação do
  ADR 6.4.0005 também não aparece na rodada (D8). Se um gold de produção vier
  depois, ele é publicado na raiz da rodada **antes** da troca do ponteiro, sem
  mudar este desenho.
- **Fonte:** issue #202 (incerteza 3); ADR 7.4.0001 item 5; ADR 6.4.0006
  (parâmetros explícitos do refresh, com referência de pré-registro).
- **ADR:** [`8_4_0001`](../../adr/8_4_0001-production-round-own-frozen-cohort-retrained-without-gold.md) item 5.

### D4 — Agendamento fora do código: comando idempotente + cron ou Agendador [P — a ratificar pelo dono]

- **O quê:** o job é o subcomando `production-round`, rodado por `docker run
  --rm` da imagem de dev com o venv `sentiment`, o cache do Hugging Face e o
  checkout montados. O agendamento é uma linha de cron no host (ou uma tarefa
  do Agendador de Tarefas do Windows) que chama esse comando com
  `--round $(date +%F)` e, se ele publicou, recria o container da API. O
  runbook traz os comandos exatos. Sem orquestrador e sem mudança no
  `docker-compose.yml`. Cadência sugerida: semanal (o retreino leva
  ~1 h 45 min (FinBERT ~15 min, baselines e GBM em minutos, três seeds × ~27 min)).
- **Por quê:** a #202 classifica o lugar do scheduler como "decisão de
  infraestrutura, fora do v0". O comando idempotente é o que um orquestrador
  chamaria de qualquer forma; o agendador se troca sem tocar no código
  (`operational-evolution-policy.md`). Skill `project-scope-principles`:
  caminho simples e robusto antes de automação complexa. O serviço `app` do
  compose não serve: monta o venv sem `sentiment` e o `--env-file` do compose
  não chega ao container (§3).
- **Fonte:** issue #202 (incerteza 4); skill `orchestrator-design`
  (idempotência e retomada); LAYOUT §3 (política de evolução operacional);
  `docker-compose.yml`; `Dockerfile`.
- **ADR:** [`8_4_0002`](../../adr/8_4_0002-immutable-round-roots-and-atomic-serving-pointer.md) item 4.

### D5 — Corrida de produção: o mesmo runner, com a herança de hiperparâmetros declarada [decision:C]

- **O quê:** a rodada usa o `RunConfirmatoryCohort` montado por uma fábrica
  própria da composition root (`production_cohort_for`), com
  `inherited_hyperparameters=True` e o probe sobre o modelo de produção
  versionado. Não há use case novo de treino.
- **Por quê:** as unidades, a classificação de retomada, o lock e o ledger são
  os mesmos; um runner paralelo duplicaria a máquina que a 7.3 já extraiu para
  `cohort_unit_runner`. A única regra do confirmatório que não vale na produção
  é a igualdade "dado dos sweeps = dado do cohort". Ela vira um parâmetro
  nomeado com default seguro (`False`), não um ramo escondido. O probe sobre o
  modelo versionado mantém a exigência de árvore limpa, e o spec da rodada é
  derivado só dele (I4). Degrau 5 (a mais simples) entre "parâmetro no runner
  existente" e "use case paralelo"; o degrau 1 (coerência com o projeto) não
  discrimina: a 7.3 fez um executor próprio para a ablação porque as unidades
  eram outras, o que não é o caso aqui.
- **Fonte:** `run_confirmatory_cohort.py`, `cohort_unit_runner.py`,
  `git_runtime_environment_probe.py`; ADR 7.3.0003 item 3.
- **ADR:** [`8_4_0001`](../../adr/8_4_0001-production-round-own-frozen-cohort-retrained-without-gold.md) item 6.

### D6 — Identidade, exclusão e retomada da rodada [decision:C]

- **O quê:** o nome da rodada é uma data ISO, com sufixo opcional `.N` para
  refazer uma rodada do mesmo dia (`2026-10-25`, `2026-10-25.1`), vindo do
  agendador. O comando inteiro roda sob o lock de escritor único da raiz de
  produção (o mesmo lock do ledger da 5.5, `writer_lock_for`), além do lock da
  rodada que o runner já toma. Repetir o mesmo nome retoma a rodada (I6). A
  materialização usa uma marca `.materialized`, gravada só depois de o
  `BuildDataset` terminar, porque a ingestão acrescenta ao bronze e recusa chave
  repetida. Sem a marca, as camadas derivadas e os brutos copiados da rodada
  são apagados e refeitos.
- **Por quê:** a data é o que um agendador produz sem ler dado, ordena as
  rodadas (I9) e fecha os nomes perigosos (`.`, `..`) que o
  `validate_path_identifier` aceitaria. O lock da raiz serializa o job inteiro,
  o que cobre duas rodadas sobrepostas e a mesma rodada disparada duas vezes;
  é o lock já testado da 5.5, sem mecanismo novo. Derivar o nome do conteúdo
  dos brutos pediria um hash de arquivo fora dos VOs de identidade (regra 6 do
  `check_layout`) para ganhar só a deduplicação de rodadas com os mesmos brutos
  (PRE-1). Degrau 5.
- **Fonte:** skill `orchestrator-design` (idempotência, replay, exclusão);
  runbook do cohort (Step 4, `DuplicateKeyError`; Step 9, lock órfão);
  `json_cohort_progress_ledger.py`.
- **ADR:** [`8_4_0002`](../../adr/8_4_0002-immutable-round-roots-and-atomic-serving-pointer.md) item 5.

### D7 — Seeds da produção: `[1, 2, 3]` [P — a ratificar pelo dono]

- **O quê:** o modelo de produção declara as seeds `[1, 2, 3]`.
- **Por quê:** a API serve um membro por seed, sem agregar (ADR 7.4.0001 item 2), e o
  estudo trata as seeds como réplicas (doc de domínio inference §2.3). Uma seed
  só esconderia a dispersão entre réplicas que o payload existe para mostrar.
  As dez do confirmatório custariam ~4,5 h de TFT por rodada. Três seeds mostram
  a dispersão por ~81 min de TFT, o que cabe numa cadência semanal. As três
  primeiras do confirmatório mantêm a correspondência seed a seed com ele.
- **Fonte:** medição desta Stage (§3); ADR 7.4.0001 item 2 (um membro por
  seed, sem agregação).

### D8 — Janela de publicação do ADR 6.4.0005: tratada por raiz imutável + ponteiro atômico + recriação da API [decision:E]

- **O quê:** a rodada escreve só na raiz dela, que nenhuma API lê enquanto ela
  é escrita. Depois do `verify`, o comando troca o `serving.env` por
  `os.replace`. A API passa a servir a rodada nova quando o container é
  recriado com o ponteiro novo, e a raiz anterior fica intacta. A janela entre
  as duas trocas de pasta do `ParquetGoldStore` não ocorre: a rodada não
  publica gold (D3) e, se publicar no futuro, publica numa raiz que ninguém
  serve ainda.
- **Por quê:** é a primeira das duas saídas que a #202 lista ("publicar em
  outro `data_root` e trocar a configuração da API"). A troca de arquivo único
  por `os.replace` é atômica no POSIX (Python docs, `os.replace`: "If
  successful, the renaming will be an atomic operation (this is a POSIX
  requirement)"); no bind mount do host Windows ela é **observada, não
  documentada**, como o ADR 6.4.0005 já registrou para o mesmo tipo de mount.
  A correção também não depende disso: a API lê o ponteiro uma vez, na subida
  (concept 7.4 D8), e o operador só recria a API depois de o comando terminar.
  Resta o intervalo da recriação, em que a API não responde. Esse risco fica
  medido e aceito por escrito no CA6.
- **Fonte:** issue #202 (Restrição conhecida); ADR 6.4.0005 (Decision 5,
  Residual risk); concept 7.4 §8; `create_app`.
- **ADR:** [`8_4_0002`](../../adr/8_4_0002-immutable-round-roots-and-atomic-serving-pointer.md) itens 1–3.

### D9 — Brutos de um diretório mantido fora do job [P — a ratificar pelo dono]

- **O quê:** `--raw-root` aponta para um diretório com o leiaute de entrada da
  5.5 (`raw/market/candles/<ativo>/candles_<ativo>_1d.parquet`,
  `raw/news/<ativo>/news_<ativo>.parquet`,
  `processed/fundamentals/<ativo>/fundamentals_<ativo>.parquet`). A aquisição a
  partir dos provedores fica na issue #241.
- **Por quê:** os fetchers de rede existem, mas nenhum está ligado ao runner, e
  ligá-los traz chave de API, limite de chamadas e testes de rede. Nada disso é
  exigido pelos três critérios da #202. O job materializa o que estiver no
  diretório: o critério "materializa dado novo" vale quando o diretório é
  atualizado.
- **Fonte:** `composition_root.py` (ingestão local da 5.5); overview ASSUM-3.

### D10 — O que a rodada serve: decisões com alvo realizado [decision:E]

- **O quê:** a rodada serve as decisões do bloco de teste cujo alvo `t + h`
  cabe no painel. Num painel que termina em `T`, h+1 vai até `T − 1` e h+7 até
  `T − 7`. Um pedido pela decisão de `T` responde 404, como qualquer data sem
  linha.
- **Por quê:** é o que o persister grava (`expected_prediction_rows`; "menos as
  decisões do ÚLTIMO fold cujo alvo `t + h` cai além do painel"). Servir a
  previsão do pregão seguinte é outro modo de predição, rejeitado para a API no
  ADR 7.4.0001 e não pedido pela #202. Fica registrado na issue #242.
- **Fonte:** `cohort_geometry.py`; ADR 7.4.0001 Contexto.

## 8. Integrações

### Internas (com outras Stages/módulos)

- **modeling:** `CohortSpec.production_round` (novo método),
  `RunConfirmatoryCohort`/`check_cohort_declarations` (parâmetro novo),
  `cohort_commands.verify` e `cohort_file` (reusados), um módulo novo
  `adapters/in/cli/production_commands.py` (derivar e gravar o spec da
  rodada, publicar o ponteiro).
- **market_data + feature_engineering:** reuso do `_materialize` do `cli.py`.
- **composition root:** fábricas `production_cohort_for` e `writer_lock_for`.
  `serve_inference_for` e `register_http_routes` não mudam.
- **inference (7.4):** nenhum código muda. A API é exercitada no e2e e na
  execução real com `DATA_ROOT` e `SERVING_COHORT_FILE` da rodada.
- **evaluation:** nenhuma chamada (I8).

### Externas

- **Agendador do host** (cron ou Agendador de Tarefas): chama o `docker run
  --rm … production-round …` e, se a saída tem `published`, recria o container
  da API (`docker rm -f` + `docker run -d --env-file <raiz de produção no
  host>/serving.env …`). Formato do `serving.env`: `CHAVE=valor`, uma por
  linha, lido pelo `--env-file` do `docker run`.

## 9. Modelo de dados

Sem tabela nova. O silver da rodada usa as tabelas da 4.1 (`dim_run`,
`fact_oos_predictions`) sob o `parent_sweep_id` da rodada. O spec da rodada
segue o schema do `cohort_file`. O `serving.env` tem exatamente duas linhas:

```
DATA_ROOT=/app/data/production/aapl/rounds/2025-12-31
SERVING_COHORT_FILE=/app/data/production/aapl/rounds/2025-12-31/cohort.toml
```

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Job escrever no `data_root` confirmatório | B | A | I1: recusa por caminho resolvido; raiz de produção separada; na execução real o `data_root` confirmatório nem é montado no container do job |
| Hiperparâmetros herdados sem querer no `run` confirmatório | B | A | parâmetro com default `False`; só a fábrica de produção passa `True`; teste do caso confirmatório segue recusando |
| Modelo de produção divergir do confirmatório sem decisão | M | M | teste que compara campo a campo; mudança deliberada sobe a `revision` |
| Rodada longa demais para a cadência, ou sobreposta | M | M | custo medido (D2); cadência semanal; lock da raiz serializa (I9); retomada por unidade |
| Ponteiro voltar para uma rodada antiga | B | M | publicação monotônica (I9) |
| Disco cresce com rodadas antigas | M | B | runbook manda apagar rodadas que não são a servida; retenção automática fica fora |
| API fora do ar durante a recriação | A | B | medido e aceito no CA6; troca fora do horário de uso |
| Brutos não atualizados | M | M | PRE-1 declarada; aviso de brutos divergentes (I7); issue #241 |
| Cliente esperar a previsão de hoje | M | M | D10 declarada no runbook; issue #242 |

## 11. Critérios de aceitação

- [ ] **CA1 (rodada servível, #202 critério 1)** e2e pelo `cli.main` real com
      brutos sintéticos, treinos reais e sentimento fake, num repositório git
      descartável, sem override de `data_root`, `artifacts_root` nem
      `mlflow_tracking_uri` e com o diretório de trabalho num `tmp_path`:
      `production-round` sai com 0, grava a rodada sob
      `<production-root>/rounds/<id>/` (incluindo `artifacts/` e `mlruns.db`),
      o `verify` da rodada imprime `OK` e o `serving.env` aponta para ela. Os
      arquivos de um `data/cohorts/conf/` sintético do repositório têm o mesmo
      hash antes e depois, e nada foi criado no repositório fora da raiz de
      produção.
- [ ] **CA2 (API sem mudança no caminho de serviço, #202 critério 3)** no mesmo
      e2e, `create_app(Settings(...))` com os valores lidos do `serving.env`
      responde `POST /inference/run` com 200 numa data do teste da rodada, com
      as seeds do modelo de produção, o `cohort_id` da rodada e os blocos do
      gold `unavailable` ("gold não publicado"); uma data posterior ao teste
      responde 404. `git diff origin/develop` não toca `features/inference/`,
      `shared/infrastructure/http/` nem as funções `serve_inference_for` e
      `register_http_routes` (conferido no gate de saída).
- [ ] **CA3 (idempotência, retomada e imutabilidade)** repetir o comando com o
      mesmo `--round` sai com 0, sem treinar (unidades `skipped_completed`), e o
      `serving.env` tem o mesmo conteúdo. Uma segunda rodada com mais sessões
      publica, e os arquivos da primeira têm o mesmo hash antes e depois dela
      (I2). Rodar de novo a primeira depois disso sai com 0 e `not published`,
      com o ponteiro intacto (I9). Materialização interrompida (sem a marca) é
      refeita do zero; `cohort.toml` da rodada adulterado → exit 2, arquivo
      intacto.
- [ ] **CA4 (ponteiro só depois do verify)** com o `verify` forçado a divergir,
      o comando sai com 1 e o `serving.env` anterior fica byte a byte igual.
      Teste da função de publicação: o conteúdo tem exatamente as duas linhas
      absolutas; uma exceção no `os.replace` deixa o ponteiro anterior byte a
      byte igual e nenhum temporário no diretório.
- [ ] **CA5 (garantias do runner)** unit: com `inherited_hyperparameters=False`,
      a impressão digital dos sweeps diferente da do dado segue recusada
      (`CohortDeclarationMismatchError`); com `True`, passa, e as outras
      recusas (impressão digital observada ≠ declarada, `feature_set_hash`,
      device, `pipeline_version`) continuam. `production_round` recusa modelo
      já congelado, incompleto ou impressão digital malformada. O modelo
      versionado é igual ao confirmatório r0 fora dos campos declarados em §4,
      e o `run` confirmatório recusa o modelo (`CohortNotFrozenError`). Só
      `production_cohort_for` passa `True` (`grep` no gate de saída).
- [ ] **CA6 (execução real e janela, #202 critérios 1–3)** duas rodadas reais
      sobre os brutos do AAPL, a primeira com os brutos cortados em 2025-06-30
      e a segunda com os brutos inteiros (até 2025-12-31, o mesmo fim do
      confirmatório: a segunda rodada simula a chegada de dado novo em relação
      à primeira, não traz sessões além do confirmatório), sob a raiz de
      produção `data/production/aapl` da worktree, com o `data_root`
      confirmatório fora do container do job. Com a API recriada pelo comando
      do runbook apontando para a primeira, um pedido de uma decisão de
      setembro de 2025 responde 404; depois da segunda rodada e da recriação
      com o novo `serving.env`, o mesmo pedido responde 200 com as seeds da
      produção e o `cohort_id` da segunda. Colados como `[measurement]`: o
      tempo de cada rodada, a data do fim do treino de cada uma, o tempo da
      recriação da API e o `sha256` dos arquivos do `data_root` confirmatório
      antes e depois. O risco da recriação fica aceito por escrito no §7 do
      technical.
- [ ] **CA7 (validação antes de escrever)** raiz de produção dentro de
      `<repo_root>/data/cohorts/` (e o contrário, e com outra caixa de letra),
      `--round` inválido (`..`, `.`, `2026-13-01`, `x`) e bruto ausente → exit
      2 sem criar nada sob a raiz de produção; lock da raiz ocupado → exit 2
      sem apagar nada da rodada.
- [ ] **CA8 (fronteira e docs)** teste AST: `production_commands.py` não
      importa `features.evaluation`. Runbook
      `docs/runbooks/production-cohort-job.md` com os comandos exatos da rodada,
      da recriação da API e do agendamento (cron e Agendador de Tarefas),
      retomada, rollback, lock órfão, limpeza e os limites D9/D10; ADRs
      8.4.0001 e 8.4.0002 `accepted`; issues #241 e #242 citadas; roadmap
      atualizado.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4: método do DTO, parâmetro do runner, fábricas, subcomando, `Settings` da rodada, leiaute e `serving.env`.
- [x] Toda decisão em §7 tem fonte rastreável? — cada D cita a issue #202, código, ADR, runbook, skill ou medição.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)? — agendador do host chamando o subcomando por `docker run`; `serving.env` em `CHAVE=valor` para o `--env-file`; sem auth.
- [x] Decisões com alternativa real descartada têm ADR escrito? — 8.4.0001 (forma, retreino, gold, runner) e 8.4.0002 (raiz imutável, ponteiro, recriação, agendamento, identidade e exclusão). D9 e D10 seguem fato de código e escopo da issue.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 7.4, 8.1 e 8.3 `done` no roadmap.
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)? — 8: método do DTO; parâmetro do runner; modelo versionado; fábricas; comandos de produção; subcomando; e2e; runbook. Mais a execução real.
- [x] Riscos críticos têm mitigação plausível? — §10.
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — (i) frescor do dado: tratado a montante, por um cohort novo, não por um caso especial na API (D1); (ii) identidade da rodada: o `CohortHash` de sempre sobre o spec da rodada, sem identidade nova (D1); (iii) treino: o runner existente com um parâmetro nomeado, sem runner paralelo (D5); (iv) exclusão: o lock do ledger da 5.5 sobre a raiz de produção, sem lock novo (D6); (v) publicação atômica: a primitiva que o ADR 6.4.0005 já usa (`os.replace`), aplicada a um arquivo único, sem leitura atômica nova no gold (D8); (vi) agendamento: fora do código (D4); (vii) aquisição de brutos e previsão do pregão seguinte: concerns a montante, registrados como issues em vez de embutidos no job (D9, D10). Nenhuma captura local de concern transversal identificada.
- [x] A Stage calcula alguma métrica sobre o cohort confirmatório? — não: o job não roda `RefreshGold` nem métrica de avaliação (I8); a execução real copia só os brutos e não monta o `data_root` confirmatório no container do job (I1, CA6).
- [x] As decisões P estão marcadas para ratificação? — D1, D2, D3, D4, D7 e D9.

## 13. Questões em aberto

Nenhuma bloqueante. As decisões P (D1–D4, D7, D9) foram tomadas com motivo
escrito e aguardam a ratificação do dono. Todas podem ser revertidas sem mudar
a API.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §3 (API fina; re-treino a partir dos brutos)
- [`../../roadmap.md`](../../roadmap.md) — Stage `8.4-production-cohort-job`
- [`../7.4-inference-api/concept.md`](../7.4-inference-api/concept.md) — D1, D8, D10, §8
- [`../../runbooks/confirmatory-cohort-aapl.md`](../../runbooks/confirmatory-cohort-aapl.md) — Steps 2, 4, 7, 9, 10
- ADRs: 5.5.0001, 5.5.0003, 6.4.0005, 6.4.0006, 7.1.0001, 7.1.0003, 7.3.0003, 7.4.0001; desta Stage: 8.4.0001, 8.4.0002
- Skills: `orchestrator-design`, `composition-root`, `hex-arch-python`, `dmls-ch06-deployment-and-inference-decisions`, `project-scope-principles`
- Issues: #202 (esta Stage), #241 (aquisição dos brutos), #242 (previsão do pregão seguinte)
- Huyen, C. (2022). *Designing Machine Learning Systems*. O'Reilly — cap. 7, "Batch Prediction Versus Online Prediction"
- Sandve, G. K. et al. (2013). "Ten Simple Rules for Reproducible Computational Research". PLoS Comput Biol 9(10), DOI 10.1371/journal.pcbi.1003285 — regra 1
- Python docs, `os.replace`
