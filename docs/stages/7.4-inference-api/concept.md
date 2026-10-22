---
title: Concept — Stage 7.4 — API de inferência (serve as predições gravadas do candidato com intervalo conformal e leitura de H3 do gold)
description: POST /inference/run fino sobre o use case ServeInference, que lê as predições de teste já gravadas do candidato TFT (sem carregar checkpoint), aplica a correção conformal do gold pela PairCorrection.limits e anexa a leitura de H3 do gold, num payload com versão de schema; pedido sem dado gravado devolve 404 "não há dados para o pedido solicitado"; blocos do gold com estado disponível/indisponível; leitor do gold no evaluation por port do consumidor no inference
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; ao subir ou consumir a API de inferência; ao mudar o payload servido (versão de schema); ao ligar a API a um cohort; ao questionar por que a API não roda o modelo, não agrega seeds ou responde 404
keywords: [concept, inference-api, inference, fastapi, thin-adapter, serving, batch-prediction, payload, schema-version, conformal, empirical-coverage, h3, explainability, vsn, gold, not-found, http-errors]
status: done
created_at: 2026-10-21
updated_at: 2026-10-21
stage_id: 7.4-inference-api
stage_title: API de inferência
step_id: 7
step_title: Inferência, conformal, explicabilidade e API
depends_on: [7.2-conformal-cqr, 7.3-explainability]
---

# Concept — Stage 7.4 — API de inferência

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

A teoria do que a API serve está fechada no
[doc de domínio inference](../../domain/inference/conformal-benchmark-and-feature-attribution.md)
§6 (com o rótulo de §4.11 e a linguagem de §5.8): a API **não tem teoria
própria**, serve o que as Stages anteriores produziram e **não recalibra, não
re-treina e não calcula atribuição**. Este concept decide **de onde** cada
bloco do payload vem, **como** um pedido se liga ao dado gravado, **o que** o
payload carrega (com versão de schema) e **como** a falta de dado vira HTTP. O
alinhamento de abordagem (RUNBOOK Passo 1b) foi validado pelo humano em
2026-10-21 na issue #201 (B1–B3).

## 1. Escopo

### Dentro do escopo

1. **Use case `ServeInference`** (`inference/application/use_cases/`): recebe
   (ativo, data de decisão, horizontes e seeds opcionais) e devolve o payload
   como DTO. Lê, pelo port `SilverTableReader` que a 7.1 já declarou, o
   `dim_run` do cohort servido e as linhas `split = "test"` do candidato em
   `fact_oos_predictions` — gravadas pelo treinador do cohort (5.5) e cuja
   reprodução a partir do checkpoint a 7.1 provou; liga cada (seed, horizonte)
   ao run de teste que contém a decisão; monta a grade nativa rearranjada;
   aplica a correção conformal da mesma unidade (`fold_raw`, seed, horizonte,
   par) por `PairCorrection.limits` (domain do inference, 7.2); anexa a
   leitura de H3. Não carrega checkpoint, não lê o realizado, não escreve nada.
2. **Leitura do gold pelo padrão do D9 da 7.2**: port do consumidor
   `ServingGoldReader` em `inference/application/ports/out/`, com DTOs do
   inference em `inference/application/dtos/`; o real é o use case
   `ReadServingGold` do **evaluation**, que lê a geração `current/` pelo
   `GoldGenerationReader` existente (manifesto primeiro,
   `GoldGeneration.from_stored`), seleciona as colunas pelo `gold_schema` (dono
   único) e monta os DTOs do inference. Fake em `tests/fakes/` e suíte de
   contrato `[fake, real]`. Uma aresta de dados nova declarada no
   `bc-independence`, na direção evaluation → inference — **exceção declarada**
   aos itens 2–3 do ADR 0.0.0053 (D5).
3. **Adapter HTTP fino** (`inference/adapters/in/http/`): `POST
   /inference/run`, schemas Pydantic de pedido e resposta com
   `schema_version`, router sem regra (pedido → DTO de consulta → use case →
   resposta), provedor do use case trocado no `app.py` por
   `dependency_overrides` (LAYOUT §5 opção 2, §6).
4. **Mapeamento de erros** pelos handlers globais de
   `shared/infrastructure/http/error_handlers.py`: pedido sem dado gravado →
   `NotFoundError` → **404** `{detail, type}` com "não há dados para o pedido
   solicitado" e o que faltou (B1/B3); corpo inválido → **422** no formato
   padrão do FastAPI; `ApplicationError` (gold corrompido, silver
   inconsistente, serviço sem cohort configurado) → **500** `{detail, type}`
   — handler novo, geral, no lugar de tratamento local na rota.
5. **Wiring**: `Settings` ganha o arquivo do cohort servido (opcional); o
   composition root expõe a fábrica `serve_inference_for(cohort_path)`, que lê
   o cohort pelo leitor da 5.5, exige cohort congelado, deriva o `cohort_id`
   pelo `CohortHash` e monta o escopo e o `ServeInference`; só o `create_app`
   a chama, na subida (a CLI não é afetada). Silver e gold são lidos sob o
   `data_root` (o do cohort real é `data/cohorts/aapl`).
6. **Excedente `http/` do template** (ADR 1.1.0001): esta Stage liga o
   `app.py` e o `error_handlers.py`; o `middlewares.py` (CORS do template)
   continua como está — sem autenticação nem credencial servida (non-goal).
7. **Gates de fronteira**: o contrato `inference-no-torch-leak` passa a cobrir
   o pacote do router; teste em subprocesso prova que subir a app e atender um
   pedido não carrega `torch`, `lightning` nem `pytorch_forecasting`.
8. **Testes**: unitários do use case e do leitor (fakes), contrato do port
   novo, integração do router (cliente HTTP do FastAPI com use case de teste) e
   **e2e** pela app completa sobre silver e gold reais em `tmp_path`.
9. **Docs**: roadmap alinhado antes da aprovação deste concept (bloco 7.4,
   linha da tabela, changelog — D12); LAYOUT §7 (doutrina da aresta, contagem);
   nota de emenda no ADR 0.0.0053; errata do localizador Huyen no ADR 7.1.0001
   e no concept 7.1; overview §10 com as fontes novas; issue do job agendado de
   atualização (D10).

### Fora do escopo (explicitamente)

- **Autenticação, servir treino, streaming** — `non_goals` do roadmap.
- **Rodar o modelo por pedido** (predição online a partir do checkpoint) — D1.
- **Datas fora das partições de teste do cohort** e previsão "ao vivo": não há
  dado gravado → 404. Manter dados atualizados é desenho de outro pipeline
  (D10), registrado como issue.
- **Recalibrar, recalcular atribuição, calcular qualquer métrica** sobre o
  realizado (doc §6, §7) — a API não lê o realizado.
- **Agregar seeds** (média de quantis entre seeds) — D2.
- **Baselines, partição `calib` e cohort de ablação** no payload: o objeto
  servido é o candidato, no teste (doc §2.1).
- **Variante de sensibilidade NexCP** e **coberturas conformais** no payload
  (D6).
- **`gold_h3_importance`** (importância por seed e permutação) — D7.
- **Cache da geração gold** entre pedidos — só se a medição do CA12 passar do
  limiar (D15).

### Vínculo com o roadmap

Última Stage do Step 7 ("Motor de inferência + conformal CQR (benchmark) +
explicabilidade (VSN/permutação/ablação) servidos por API fina"): torna
consumíveis por HTTP as predições de teste do candidato, as correções
conformais (7.2) e a leitura de H3 (7.3), como pede o overview §3 ("API de
inferência fina (FastAPI) + explicabilidade") e §6 ("FastAPI fino só como
adapter de entrada (inferência/explicabilidade); sem servir treino").

## 2. Objetivo da Stage

Ao fim da Stage, `POST /inference/run` com um ativo e uma data de decisão do
teste do cohort confirmatório devolve, lendo só o que já está gravado no silver
e no gold, a grade nativa rearranjada de cada seed por horizonte, o intervalo
conformal de cada par rotulado "cobertura empírica (não garantida)" e a
leitura de H3 rotulada descritiva, num payload com versão de schema — e
devolve 404 "não há dados para o pedido solicitado" quando o pedido não tem
dado gravado.

## 3. Contexto e premissas

### Contexto

- As linhas `split = "test"` do candidato em `fact_oos_predictions` foram
  gravadas pelo treinador do cohort confirmatório (5.5). A 7.1 re-prediz o
  teste a partir do checkpoint **em memória** e prova a reprodução no mesmo
  ambiente (ADR 7.1.0003, que rejeitou regravar o teste); ela só grava a
  partição `calib` (ADR 7.1.0002). Cohort real: 60 runs `tft_quantile` (fold
  "0"–"5" × seed 1–10) sob `parent_sweep_id = aapl_confirmatory-r0-665f45d…`;
  por seed, 1511 decisões de teste em h+1 (2019-12-26 a 2025-12-30) e 1505 em
  h+7 (até 2025-12-19); as 6 últimas sessões só têm h+1. Com `split = "test"`
  há exatamente um run por (seed, horizonte, data); sem o filtro, 82,6 % das
  datas de teste também têm um run sob `split = "calib"` (o calib do fold
  seguinte). Timestamps todos `YYYY-MM-DDT00:00:00+00:00`; a partição `year` é
  o ano da decisão. Medido em 2026-10-21 sobre `data/cohorts/aapl/silver/`,
  só colunas de predição.
- **7.2** publica as correções no gold (`gold_conformal_corrections`, duas
  linhas — uma por cauda — por unidade (`fold_raw`, seed, horizonte, par,
  variante)) pelo `RefreshGold` (ADR 7.2.0003) e deixa a regra de aplicação no
  domain do inference (`PairCorrection.limits`); o D9 da 7.2 fixou que a 7.4 lê
  o gold por port do consumidor, com o leitor no evaluation.
- **7.3** publica `gold_h3_shares`, `gold_h3_reading` e `gold_h3_vsn` (ADR
  7.3.0001); os rótulos têm dono no domain do evaluation
  (`EMPIRICAL_COVERAGE_LABEL`, `H3_LABEL`, `VSN_LABEL`) e as linhas de leitura
  e de VSN gravam o próprio `label`.
- **Estados de uma geração gold**: sem manifesto (`GoldManifestNotFoundError`);
  `BLOCKED` (o manifesto não lista as tabelas confirmatórias — ler uma delas
  ergue `GoldGenerationCorruptError`); `COMPLETED` com todas as tabelas,
  possivelmente com zero linhas quando o pré-registro não tem `[conformal]` ou
  `[h3]` (os parâmetros ficam nulos no manifesto); corrompida
  (`GoldGenerationCorruptError`). Os dois erros são subclasses de
  `ApplicationError`. O candidato da geração está em
  `manifest.parameters.candidate`.
- **O gold real ainda não existe**: a geração `current/` do cohort é publicada
  pelo refresh da 8.1.
- **`app.py`** existe desde a 1.1 (ADR 1.1.0001) sem router de feature, com
  handlers `NotFoundError → 404` e `DomainError → 422`; a validação de corpo do
  FastAPI responde 422 com `{"detail": [...]}` (lista). Nenhum slice tem
  `ports/in/` nem adapter HTTP; os adapters de entrada existentes (CLI) chamam
  o use case diretamente. A JSON não tem infinito (RFC 8259 §6); com modelo de
  resposta, o Pydantic 2.13 serializa `inf` como `null` sem aviso.

### Premissas

- **P1** — As predições de teste do candidato estão completas no silver do
  cohort servido. Ponto sem linha → 404; seed do cohort sem nenhum run → 500
  (silver incompleto, não falta de dado do pedido).
- **P2** — Um processo da API serve **um** cohort, configurado pelo arquivo do
  cohort e pelo `data_root`; pedido de outro ativo é pedido sem dado.
- **P3** — Os identificadores gravados pela 7.2 (`lower`/`upper`;
  `ConformalVariant`; `ok`/`undefined`/`error`) são os do código atual.

### Dependências

- `7.1-inference-engine`: port `SilverTableReader` do inference (fake e
  contrato `[fake, real]`); prova de reprodução do teste.
- `7.2-conformal-cqr`: `gold_conformal_corrections`, `ConformalVariant`,
  `TailCorrection`, `PairCorrection.limits`, `exact_level`; D9.
- `7.3-explainability`: `gold_h3_shares`, `gold_h3_reading`, `gold_h3_vsn`.
- `6.5`/`6.4` (`done`): `GoldGenerationReader`, `GoldGeneration`,
  `GoldPartition`, `gold_schema`, leitores de célula tipados, `ParquetGoldStore`.
- `5.5`: leitor do arquivo do cohort, `CohortSpec.cohort_id`, `MODEL_VERSION`
  do candidato (só no composition root).

## 4. Contratos

### Introduzidos

- **`ServeInference`** (use case = port-in, alcançado por `Depends`) —
  `inference/application/use_cases/serve_inference.py`:

  ```python
  class ServeInference:
      def __init__(self, *, scope: ServingScope, silver: SilverTableReader,
                   gold: ServingGoldReader) -> None: ...
      def __call__(self, query: ServeInferenceQuery) -> InferencePayload: ...
  ```

  O roadmap chamava este contrato de `RunInferencePort`; o nome muda porque
  `RunInference` já é o job em lote da 7.1 (D8).
- **DTOs da consulta e do payload** (frozen, no módulo do use case, como o
  `RunInferenceCommand` da 7.1):
  - `ServeInferenceQuery`: `asset: str`, `decision_date: date`,
    `horizons: tuple[int, ...] | None`, `seeds: tuple[int, ...] | None`
    (`None` = todos os do cohort; vazio ou repetido → `ValueError`);
  - `ServingScope`: `cohort_id`, `asset`, `feature_set_name`,
    `model_version`, `horizons`, `quantile_levels`, `seeds` — grade simétrica
    com mediana (os pares saem dela), validada na construção;
  - `InferencePayload`: `asset`, `decision_date`, `cohort_id`,
    `model_version`, `quantile_levels`, `forecasts`, `explainability`, `gold`;
  - `HorizonForecast`: `horizon`, `target_date`, `members`;
  - `SeedForecast`: `seed`, `fold` (o `fold` do `dim_run`, string), `run_id`,
    `quantiles` (alinhados a `quantile_levels`), `conformal`;
  - `ConformalBlock`: `status` (`available` | `unavailable`), `reason`,
    `label`, `variant`, `intervals`;
  - `ConformalInterval`: `lower_level`, `upper_level`, `status` (`ok` |
    `unavailable`), `gold_status` (`ok` | `undefined` | `error` | `None`),
    `reason`, `lower`, `upper` (float, ±∞ permitido; `None` quando
    `unavailable`);
  - `ExplainabilityBlock`: `status` (`available` | `unavailable`), `reason`,
    `label`, `shares`, `reading`, `vsn`, `vsn_label`;
  - `GoldProvenance`: `published: bool`, `generation_status` (`COMPLETED` |
    `BLOCKED` | `None`), `preregistration_ref`, `candidate`, `finished_at` —
    `None` nos campos da geração quando não publicada; o motivo de cada bloco
    indisponível fica no próprio bloco.
  - Rótulos: `ConformalBlock.label`, `ExplainabilityBlock.label` e
    `vsn_label` vêm **sempre** preenchidos com as constantes de dono único,
    inclusive em bloco `unavailable` (doc §4.11: o rótulo vai "em todo …
    payload").
- **`NoServedDataError`** (`NotFoundError`) —
  `inference/domain/exceptions/serving.py`: a mensagem começa por "não há dados
  para o pedido solicitado" e diz o que faltou (ativo, horizonte, seed ou
  decisão).
- **`ServingGoldReader`** (port-out do consumidor) —
  `inference/application/ports/out/serving_gold_reader.py`:

  ```python
  class ServingGoldReader(Protocol):
      def read(self, *, asset: str, cohort_id: str) -> ServingGold: ...
  ```

  Partição sem geração publicada → `ServingGold` com os dois blocos
  indisponíveis (não erro); geração que não se sustenta → `ApplicationError`.
- **DTOs do port** (frozen) — `inference/application/dtos/serving_gold.py`:
  - `ServingGold`: `published: bool`, `generation_status`,
    `preregistration_ref`, `candidate`, `finished_at`, `conformal_status`,
    `conformal_reason`, `explainability_status`, `explainability_reason`,
    `conformal_label`, `h3_label`, `vsn_label`, `corrections`, `shares`,
    `reading`, `vsn`;
  - `ConformalCorrectionRecord`: `fold_raw: str`, `seed: int`, `horizon: int`,
    `lower_level`, `upper_level`, `variant: str`, `tail: str`, `tail_level`,
    `status: str`, `reason: str | None`, `n: int | None`, `rank: int | None`,
    `correction: float | None` (`+inf` reconstruído de `infinite = true`;
    `None` fora de `ok`);
  - `H3ShareRecord`: `method`, `family`, `share_h1`, `share_h7`, `delta`,
    `lower`, `upper` (±∞ reconstruídos das flags), `level`, `side`,
    `excludes_zero`, `status`, `reason` — opcionais onde o gold é anulável;
  - `H3ReadingRecord`: `reading_rule`, `heterogeneous_permutation: bool |
    None`, `heterogeneous_ablation: bool | None`, `sustained: bool | None`,
    `agreeing_families: tuple[str, ...]`, `n_points: int | None`, `status`,
    `reason`;
  - `VsnRecord`: `kind`, `name`, `family`, `p10`, `p50`, `p90` (`float |
    None`), `n_decisions: int | None`, `status`, `reason` — medidas nulas
    quando o resumo é `undefined` (o builder grava assim).
- **`ReadServingGold`** (use case do evaluation que satisfaz o port por duck
  typing, assinatura textualmente igual à do port) —
  `evaluation/application/use_cases/read_serving_gold.py`:
  `__init__(*, gold_reader: GoldGenerationReader)`; `read(*, asset: str,
  cohort_id: str) -> ServingGold`.
- **HTTP** — `POST /inference/run`:
  - pedido: `{"asset": str, "decision_date": "YYYY-MM-DD", "horizons": [int]?,
    "seeds": [int]?}`;
  - resposta 200: `schema_version: 1` + o payload; todo limite que pode ser
    infinito (conformal e intervalo das participações de H3) vai com a flag
    `*_infinite`: `null` com flag `true` ⇔ limite infinito; `null` com flag
    `false` só quando não há valor (status não-`ok` sem limite gravado);
    limite finito com flag `false`, em qualquer status (D9);
  - 404 e 500: `{"detail": str, "type": str}` (`not_found`,
    `application_error`); 422: `{"detail": str, "type": "domain_error"}` para
    `DomainError` e o corpo padrão do FastAPI (`{"detail": [...]}`) para
    validação.

### Consumidos

- **`SilverTableReader`** (port do inference) — Stage 7.1; real
  `ParquetAnalyticsRepository`.
- **`PairCorrection`, `TailCorrection`, `ConformalVariant`, `exact_level`** —
  Stage 7.2 (domain do inference).
- **`GoldGenerationReader`, `GoldGeneration`, `GoldPartition`,
  `GOLD_CONFORMAL_CORRECTIONS`, `GOLD_H3_SHARES`, `GOLD_H3_READING`,
  `GOLD_H3_VSN`, `col_*`** — Stages 6.5, 7.2 e 7.3 (evaluation).
- **`EMPIRICAL_COVERAGE_LABEL`, `H3_LABEL`, `VSN_LABEL`** — evaluation domain
  (7.2, 7.3); só o leitor do evaluation os lê.
- **`NotFoundError`, `ApplicationError`** e os handlers HTTP — shared.
- **Leitor do arquivo do cohort, `CohortSpec.cohort_id`, `CohortHash`,
  `MODEL_VERSION`** — Stage 5.5; só no composition root.

## 5. Invariantes e regras

- **I1 — Só leitura.** O `ServeInference` e o `ReadServingGold` só chamam
  métodos de leitura dos seus ports; não carregam checkpoint. Subir a app e
  atender um pedido não carrega `torch`, `lightning` nem `pytorch_forecasting`
  (contrato `inference-no-torch-leak` estendido ao pacote do router + teste em
  subprocesso).
- **I2 — Só o candidato no teste (cegamento).** O use case lê só `dim_run` e
  `fact_oos_predictions`; linhas servidas: `split = "test"`, `model_version` do
  escopo e `run_id` de um run do `dim_run` com `parent_sweep_id = cohort_id`.
  Nada do realizado é lido (doc §7; I13 da 7.1).
- **I3 — Ligação pedido → run.** A decisão casa com a data de
  `timestamp_utc` (parte de data do timestamp gravado). Para cada (seed,
  horizonte) pedido, o run servido é o único run de teste da seed com linha
  naquela data e horizonte. Zero runs para o ponto → `NoServedDataError`. Zero
  runs do cohort no `dim_run`, seed do escopo sem nenhum run, mais de um run
  para o ponto, grade incompleta ou com nível repetido, ou `target_date`
  diferente entre seeds no mesmo horizonte → `ApplicationError`.
- **I4 — Grade servida.** Os quantis são o valor rearranjado gravado
  (`value_guardrail`), na ordem dos `quantile_levels` do escopo (doc §2.1,
  §3.3).
- **I5 — Seeds sem agregação.** Cada seed pedida aparece com a sua grade e o
  seu intervalo; nenhum valor é combinado entre seeds (D2).
- **I6 — Intervalo conformal.** Para cada par simétrico, a correção é a da
  variante de registro (`ConformalVariant.SPLIT_CQR`) da unidade (`fold_raw` do
  run servido, seed, horizonte, par), aplicada por `PairCorrection.limits` à
  grade rearranjada, **sem rearranjo da saída** (doc §4.8, §4.13; ADR
  0.0.0008): um intervalo pode vir cruzado (inferior > superior) e pares podem
  não vir aninhados — o payload não corrige nem esconde isso (as taxas são do
  gold). Estados: as duas caudas `ok` → intervalo `ok`; alguma cauda `undefined`
  ou `error` → intervalo `unavailable` com o `gold_status` e o `reason` do gold;
  unidade sem nenhuma linha na tabela → `unavailable` com motivo "unidade
  ausente na geração gold"; exatamente uma cauda ausente → `ApplicationError`
  (o builder grava sempre as duas).
- **I7 — Rótulos.** Os três rótulos do payload são as constantes de dono
  único do evaluation (`EMPIRICAL_COVERAGE_LABEL`, `H3_LABEL`, `VSN_LABEL`),
  sempre presentes, também em bloco `unavailable`. O leitor confere o que a
  geração gravou: a linha de `gold_h3_reading` traz `H3_LABEL` (o builder grava
  o rótulo em qualquer status); cada linha `ok` de `gold_h3_vsn` traz
  `VSN_LABEL` e cada linha não-`ok` traz rótulo nulo (resumo `undefined`) —
  qualquer outra combinação → `GoldGenerationCorruptError`. VSN `undefined` é
  estado legítimo: bloco `available`, linhas com o status e o motivo. Nenhum
  literal dos rótulos no inference nem no adapter.
- **I8 — Falta de dado é 404; falta de gold não é.** Ativo diferente do cohort,
  horizonte ou seed fora do cohort, ou decisão sem linha de teste para algum
  (seed, horizonte) pedido → 404 com "não há dados para o pedido solicitado" e
  o que faltou. Gold: o leitor captura **só** `GoldManifestNotFoundError`
  (nenhuma captura genérica de `ApplicationError`) → os dois blocos
  `unavailable` ("gold não publicado"); confere `manifest.status` **antes** de
  ler tabela: `BLOCKED` → os dois blocos `unavailable`; `COMPLETED` com
  `conformal_parameters` nulo → conformal `unavailable`; com `h3_parameters`
  nulo → explicabilidade `unavailable`. O `ServeInference` (não o leitor, que
  não recebe o `model_version`) compara, só com gold publicado e `COMPLETED`,
  `ServingGold.candidate` com o `model_version` servido: diferente → os dois
  blocos `unavailable` ("geração de outro candidato"). Precedência: não
  publicado > `BLOCKED` > outro candidato > bloco ausente no pré-registro. Em
  todos, resposta 200, grade servida e motivo distinto por caso ("gold não publicado", "geração gold BLOCKED", "geração
  sem bloco [conformal]", "geração sem bloco [h3]", "geração gold de outro
  candidato").
- **I9 — Versão de schema.** Toda resposta 200 carrega `schema_version`
  inteiro. Remover, renomear ou mudar o tipo ou o significado de um campo
  (rótulo incluído) incrementa a versão; campo novo opcional, cuja ausência
  mantém o comportamento anterior, não incrementa (D9).
- **I10 — Router fino.** O router só converte o pedido em
  `ServeInferenceQuery`, chama o use case e converte o DTO na resposta; não
  filtra, não decide, não captura exceção.
- **I11 — Determinismo.** Mesmo pedido sobre os mesmos dados → mesmo corpo
  (horizontes, seeds, níveis, pares e linhas de H3 em ordem fixa).
- **I12 — Um cohort por processo.** Sem arquivo de cohort configurado, a rota
  existe e responde 500 "serviço de inferência sem cohort configurado"; arquivo
  ilegível ou de cohort não congelado faz o `create_app` falhar na subida.
- **I13 — Defeito de dado não vaza como 500 cru.** `ValueError` ao montar DTO
  ou VO a partir de dado lido (silver ou gold) é traduzido para
  `ApplicationError` com o contexto; o `ValueError` da consulta inválida não
  chega ao use case (o schema do adapter o barra como 422).

## 6. Casos de erro e exceções

| Caso | Onde nasce | Resposta |
|---|---|---|
| Ativo ≠ ativo do cohort | `ServeInference` | 404 `NoServedDataError` (ativo) |
| Horizonte ou seed fora do cohort | `ServeInference` | 404 (horizonte/seed) |
| Decisão sem linha de teste para algum (seed, horizonte) pedido — datas fora do teste, datas só de `calib`, fim de semana, h+7 das 6 últimas sessões | `ServeInference` | 404 (decisão, horizonte, seeds) |
| Corpo inválido (data malformada, horizonte ≤ 0, lista vazia ou repetida) | schema do adapter | 422 (corpo padrão do FastAPI) |
| Gold sem geração publicada | `ReadServingGold` | 200, blocos `unavailable` ("gold não publicado") |
| Geração `BLOCKED` | `ReadServingGold` | 200, blocos `unavailable` |
| Geração sem `[conformal]` / sem `[h3]` | `ReadServingGold` | 200, o bloco correspondente `unavailable` |
| Geração de outro candidato | `ServeInference` | 200, blocos `unavailable` |
| Cauda `undefined`/`error`; unidade ausente | `ServeInference` | 200, intervalo `unavailable` com motivo |
| Uma cauda ausente da unidade; rótulo gravado ≠ constante; geração corrompida | `ReadServingGold` / `ServeInference` | 500 `application_error` |
| Silver inconsistente (zero runs do cohort, seed sem run, dois runs para o ponto, grade incompleta ou com nível repetido, `target_date` divergente) | `ServeInference` | 500 `application_error` |
| Sem cohort configurado | provedor do use case | 500 `application_error` |
| Arquivo de cohort ilegível ou não congelado | `create_app` (fábrica do composition root) | a app não sobe |

## 7. Decisões técnicas relevantes

### D1 — Servir as predições gravadas, sem rodar o modelo por pedido (B1)
- **O quê:** a API lê sob demanda as predições de teste já gravadas; nenhum
  checkpoint é carregado no processo da API. O bloco da 7.4 no roadmap deixa
  de consumir "ports de predição a partir do checkpoint".
- **Por quê:** o conjunto de consultas é finito e já está gravado (todas as
  decisões de teste do cohort), e a 7.1 provou que re-predizer do checkpoint
  reproduz o valor gravado no mesmo ambiente. Predizer por pedido devolveria o
  mesmo número a custo de carregar pelo menos um checkpoint por seed pedida
  (10 num pedido padrão — o port da 7.1 prediz partições inteiras por fold de
  uma seed) e a pilha de deep learning no processo web, e fora do mesmo
  ambiente a reprodução só promete tolerância (segunda via de predição ao lado
  da avaliada). Predição online quando a gravada basta é modo de falha nomeado
  na skill `dmls-ch06` (Task 1; Huyen 2022, cap. 7). Datas fora do cohort não
  têm dado novo para prever.
- **Fonte:** humano, B1 (2026-10-21); doc §6; skill `dmls-ch06`; ADRs
  7.1.0001, 7.1.0003; Sandve et al. 2013 (Rule 1).
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) item 1.

### D2 — Uma entrada por seed, sem agregação (B2)
- **O quê:** cada seed pedida aparece com a sua grade e o seu intervalo.
- **Por quê:** seeds são réplicas e só se agregam em perdas e coberturas
  (doc §2.3; ADR 0.0.0010 item 5); a média de quantis entre seeds seria um
  ensemble que nenhuma Stage avaliou para H1 (inferência do projeto; contexto:
  Fakoor et al. 2023 §2.3 — média de quantis e de probabilidades "often lead
  to markedly different outcomes").
- **Fonte:** humano, B2; doc §2.3.
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) item 2.

### D3 — Pedido sem dado: 404 "não há dados para o pedido solicitado"
- **O quê:** a falta de qualquer (seed, horizonte) pedido na data de decisão é
  404 do pedido inteiro, com o que faltou na mensagem; o cliente que quer só
  h+1 nas últimas sessões pede só h+1.
- **Por quê:** instrução do humano (B1) e proposta validada (B3); resposta
  parcial silenciosa esconderia de quem consome que parte do pedido não existe;
  `NotFoundError → 404` já é o mapeamento global. Usar 404 para um item
  nomeado no corpo do POST é juízo do projeto (RFC 9110 §15.5.5 fala do
  recurso-alvo); 422 já significa validação e `DomainError` nesta app.
- **Fonte:** humano, B1/B3; `shared/domain/exceptions/base.py`.
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) item 4.

### D4 — Gold ausente não é erro: blocos com estado (B3)
- **O quê:** sem geração publicada, com geração `BLOCKED`, sem o bloco do
  pré-registro, de outro candidato, ou sem a unidade, os blocos (ou o
  intervalo) vêm `unavailable` com motivo, e a grade é servida (I6, I8).
- **Por quê:** o gold real só existe depois da 8.1; a grade gravada é útil
  antes disso, e o estado explícito diz ao cliente por que o bloco falta.
  Geração corrompida, cauda única ausente ou rótulo divergente são defeito de
  dado e viram 500 — senão a corrupção passaria despercebida. O leitor captura
  só a subclasse exata `GoldManifestNotFoundError`, porque ela e
  `GoldGenerationCorruptError` são ambas `ApplicationError`.
- **Fonte:** humano, B3; contrato do `GoldGenerationReader` (6.5).
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) itens 5 e 6.

### D5 — Gold lido por port do consumidor, leitor no evaluation (exceção ao ADR 0.0.0053)
- **O quê:** `ServingGoldReader` no inference, satisfeito por
  `ReadServingGold` no evaluation sobre o `GoldGenerationReader`; o evaluation
  monta os DTOs do inference — aresta de dados nova no `bc-independence`,
  `evaluation.application.use_cases.read_serving_gold →
  inference.application.dtos.serving_gold`; o inference não importa o
  evaluation.
- **Por quê:** o `gold_schema` é dono único de nome, chave e colunas, e o
  `GoldGeneration.from_stored` é a montagem única de uma geração lida; um
  leitor de Parquet no inference seria segunda definição dos dois. A direção
  **inverte** os itens 2–3 do ADR 0.0.0053 (o fornecedor não importa o
  consumidor; quem cruza é o DTO do port-in do fornecedor): a direção prevista
  (inference → evaluation) fecharia ciclo com a aresta evaluation → inference
  que já existe (`refresh_gold → calibrate_conformal`, ADR 7.2.0003 item 3), e
  o projeto exige grafo acíclico entre slices. A exceção já estava decidida no
  D9 da 7.2 e no roadmap da 7.4 ("direção de produção só evaluation →
  inference"); esta Stage a registra no ADR, no LAYOUT §7 e numa nota de
  emenda do ADR 0.0.0053.
- **Fonte:** concept 7.2 D9; roadmap §7.4 (comentário do bloco); ADRs
  0.0.0053, 7.2.0003; LAYOUT §7.
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) item 7.

### D6 — Só a variante de registro, sem cobertura no payload
- **O quê:** o intervalo servido é o da variante de registro (split-CQR
  assimétrico sem pesos); a sensibilidade NexCP e as coberturas conformais
  ficam no gold e no relatório.
- **Por quê:** o doc §6 fala de "o intervalo conformal por par"; a variante de
  registro é o benchmark e o NexCP é sensibilidade (doc §4.5); cobertura é
  propriedade medida sobre o teste, não atributo de um intervalo (Bracher et
  al. 2021 identificam o intervalo pelo nível nominal e reportam a cobertura
  empírica à parte). Acrescentar a variante depois é mudança aditiva (I9).
- **Fonte:** doc §4.5, §4.11, §6.
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) item 6.

### D7 — Explicabilidade = leitura de H3 do estudo, subconjunto curado
- **O quê:** o bloco carrega as participações por método e família, a
  leitura da regra e o resumo da VSN, com os campos que o doc §5.7–§5.8 usa
  para ler H3 (participações em h+1 e h+7, Δ, intervalo, se exclui zero,
  sustentada, famílias concordantes, rótulo, status); o mesmo bloco em toda
  resposta — descrição do estudo, não explicação local da previsão.
- **Por quê:** H3 é descritiva e por horizonte comparado (doc §5); SHAP local
  é non-goal da 7.3; a importância por seed e permutação é insumo da leitura,
  não leitura.
- **Fonte:** doc §5.7, §5.8, §6; concept 7.3 §8.

### D8 — O port-in é o próprio use case `ServeInference`
- **O quê:** sem `Protocol` em `application/ports/in/`; o router recebe o
  `ServeInference` por `Depends`, com o provedor trocado no `app.py`. O nome
  `RunInferencePort` do roadmap é emendado.
- **Por quê:** LAYOUT §5 recomenda a opção 2 (use case injetado por
  `Depends`, sem importar o pacote `in`); nenhum slice tem `ports/in/` e os
  adapters de entrada existentes chamam o use case direto (CLI da 7.1);
  `RunInference` já nomeia o job em lote da 7.1. A rota mantém
  `/inference/run` por ser o contrato do roadmap.
- **Fonte:** LAYOUT §5, §8; concept 7.1 D8/D9; roadmap §7.4.
- **ADR:** [`7_4_0002`](../../adr/7_4_0002-inference-payload-contract-and-http-errors.md) item 6.

### D9 — Contrato do payload: versão no corpo, infinito explícito
- **O quê:** `schema_version` inteiro no corpo da resposta (começa em 1),
  regra de incremento do I9; a rota não carrega versão; todo limite que pode
  ser infinito vai como `null` com flag `*_infinite`.
- **Por quê:** convenção (degrau 1): o projeto já versiona por registro
  (`schema_version` do ADR 4.1.0001) e o roadmap fixa a rota sem segmento de
  versão; a regra de quebra × aditiva é a do Google AIP-180. A JSON não tem
  infinito (RFC 8259 §6), o `JSONResponse` do Starlette 1.3.1 recusa
  não-finito (`allow_nan=False`) e, com modelo de resposta, o Pydantic
  serializaria `inf` como `null` **sem flag** — perda silenciosa; `null` +
  flag é a convenção que o gold já usa (`correction = null`, `infinite =
  true`).
- **Fonte:** ADR 4.1.0001; AIP-180; RFC 8259 §6; Starlette `responses.py`;
  `pydantic/config.py` (`ser_json_inf_nan`); technical 7.2 §1; issue #201
  §Referências.
- **ADR:** [`7_4_0002`](../../adr/7_4_0002-inference-payload-contract-and-http-errors.md) itens 1–3.

### D10 — Atualização contínua é outro pipeline (fora)
- **O quê:** a API serve o cohort configurado; ela não ingere, não prevê nem
  publica. Servir datas novas exige **outro cohort** (ou revisão do cohort) com
  dado, treino ou predição e gold próprios, sob outro `data_root`, mantido por
  um job agendado — issue própria, aberta nesta Stage, com a incerteza
  declarada.
- **Por quê:** instrução do humano (B1: "a solução para ficar sempre
  atualizado é ter um scheduler que roda de maneira agendada"). O cohort
  confirmatório é congelado: dado novo (sessões a mais) muda o fingerprint de
  conteúdo do dataset, cujo hash inclui os timestamps, e o runner o recusa
  (`DatasetMismatchError`), assim como o `RefreshGold`
  (`GridFingerprintMismatchError`); o `RunInference` da 7.1 não grava linhas de
  teste. Um job que gravasse dado novo no `data_root` do cohort confirmatório
  quebraria o refresh da 8.1. Como a API serve qualquer cohort configurado,
  um cohort de produção mantido pelo job é servido sem mudar a API.
- **Fonte:** humano, B1; `DatasetContentFingerprint` (hash inclui os
  `timestamps` — `shared/domain/value_objects/dataset_content_fingerprint.py`);
  `cohort_unit_runner.py` (`DatasetMismatchError`); `refresh_gold.py`
  (`GridFingerprintMismatchError`); o mesmo princípio do roadmap para mudar o
  dataset de um cohort congelado (revisão nova, re-treino).
- **ADR:** [`7_4_0001`](../../adr/7_4_0001-serve-persisted-predictions-per-seed-with-gold-blocks.md) item 8.

### D11 — Erros de aplicação viram 500 no handler global
- **O quê:** handler `ApplicationError → 500` com corpo `{detail, type:
  "application_error"}` em `shared/infrastructure/http/error_handlers.py`; a
  validação de corpo mantém o 422 padrão do FastAPI; defeito de dado chega
  como `ApplicationError` (I13).
- **Por quê:** o formato de erro é concern transversal da app; tratar na rota
  violaria o adapter fino (skill `fastapi-thin-adapter`: "Don't catch
  exceptions and return JSON manually — register a handler"), e sem handler o
  FastAPI devolve 500 em texto puro. O 422 de validação fica no padrão do
  FastAPI (degrau 2: default da implementação de referência, já descrito no
  OpenAPI que ela gera).
- **Fonte:** skill `fastapi-thin-adapter`; docstring de `error_handlers.py`;
  RFC 9457 §4.
- **ADR:** [`7_4_0002`](../../adr/7_4_0002-inference-payload-contract-and-http-errors.md) item 5.

### D12 — Ajustes do roadmap, do LAYOUT e dos ADRs
- **O quê:** roadmap, num commit antes da aprovação deste concept: linha da
  tabela e `camada_alvo` (multi: domain + application + adapters/in/http do
  inference; application do evaluation; shared/http); `arquivos_a_criar`/`modificar`
  (com `tests/.../adapters/in_/http/` — pasta `in_` por causa da keyword,
  precedente da 5.5); `contratos_introduzidos` (`ServeInference`,
  `ServingGoldReader`, `ReadServingGold`); `contratos_consumidos` (sem ports de
  checkpoint e sem a partição `calib`); changelog. Na execução: LAYOUT §7
  (doutrina da aresta evaluation → inference e contagem); nota de emenda no ADR
  0.0.0053; errata "ch. 6 → cap. 7" no ADR 7.1.0001 e no concept 7.1; overview
  §10 com as fontes novas.
- **Fonte:** D1, D5, D8, D13; checklist do Passo 5 (contratos batem com o
  roadmap no gate). Sem ADR (consequência das decisões acima).

### D13 — `gate_mode: batch` mantido, justificado
- **O quê:** a Stage segue `batch` como o roadmap declara.
- **Por quê:** a fundação que a API lê está validada (silver, gold, regra
  conformal, leitores e rótulos — 7.1 a 7.3 `done`); os contratos novos são de
  leitura, um port de consumidor no padrão do D9 da 7.2 e um adapter HTTP
  versionado e aditivo; a abordagem foi validada pelo humano no Passo 1b; a
  revisão por commit é substituída pelos Checkpoints A/B/C com dois revisores
  cada (escalada do PROMPT de sessão única) e pela auditoria `stage-audit`
  antes do merge.
- **Fonte:** PIPELINE §9.4 (`batch` exige justificativa); roadmap §7.4.

### D14 — Excedente `http/` do template (ADR 1.1.0001)
- **O quê:** `app.py` e `error_handlers.py` passam a ser usados; o
  `middlewares.py` (CORS aberto do template) fica como está.
- **Por quê:** o ADR 1.1.0001 deixa ao Step da API ligar ou remover o `http/`
  e registrar no technical; o CORS não altera o contrato da rota, não há
  credencial servida e autenticação é non-goal — restringir fica para quando
  houver um cliente de navegador real.
- **Fonte:** ADR 1.1.0001 (Implementation notes); roadmap `non_goals`.

### D15 — Leitura do gold por pedido, com limiar medido
- **O quê:** o leitor lê a geração viva a cada pedido (sem cache); o tempo de
  um pedido é medido com o silver real e com uma geração gold sintética do
  tamanho da real; acima de 5 s, cache por manifesto entra como Task extra.
- **Por quê:** a geração é lida inteira (todas as tabelas do manifesto) pelo
  `GoldGenerationReader`; cache é estado mutável no leitor e só se justifica
  com medição.
- **Fonte:** `ParquetGoldStore.read_generation`; skill `project-scope-principles`
  (simples e trocável).

## 8. Integrações

### Internas (com outras Stages/módulos)

- **inference ← analytics_store:** `ParquetAnalyticsRepository` satisfaz o
  `SilverTableReader` do inference (7.1); leitura de `dim_run` e
  `fact_oos_predictions`.
- **inference ← evaluation:** `ReadServingGold` satisfaz o `ServingGoldReader`
  por duck typing; aresta de dados nova evaluation → inference (D5).
- **inference (domain):** `PairCorrection.limits` e `exact_level` reusados sem
  mudança.
- **modeling:** `MODEL_VERSION` e o leitor do arquivo do cohort, só no
  composition root.
- **shared/infrastructure/http:** handler novo `ApplicationError → 500`;
  router registrado no `app.py`; `create_app` aceita `Settings` por parâmetro.
- **8.1:** quando publicar a geração real, os blocos passam a `available` sem
  mudança de código. Risco residual do ADR 6.4.0005 (janela entre as trocas de
  pasta do `ParquetGoldStore`): um pedido concorrente à publicação pode ver
  "gold não publicado" ou uma geração inconsistente — aceito porque o refresh é
  manual e raro; o job agendado do D10 deve tratá-lo.

### Externas

- **FastAPI 0.138 / Starlette 1.3 / Pydantic 2.13** (já dependências):
  `APIRouter`, `Depends`, `dependency_overrides`, modelos de pedido e resposta;
  cliente de teste do FastAPI (httpx) nos testes de integração e e2e. Sem
  autenticação (non-goal).

## 9. Modelo de dados

Sem tabela nova. O payload (schema 1), com um horizonte e uma seed:

```json
{
  "schema_version": 1,
  "asset": "AAPL",
  "decision_date": "2024-03-15",
  "cohort_id": "aapl_confirmatory-r0-665f45d…",
  "model_version": "tft_quantile",
  "quantile_levels": [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98],
  "forecasts": [
    {"horizon": 1, "target_date": "2024-03-18",
     "members": [
       {"seed": 1, "fold": "4", "run_id": "…",
        "quantiles": [-0.031, -0.014, -0.006, 0.001, 0.008, 0.016, 0.033],
        "conformal": {"status": "available", "reason": null,
                      "label": "cobertura empírica (não garantida)",
                      "variant": "split_cqr_asymmetric_unweighted_v1",
                      "intervals": [
                        {"lower_level": 0.02, "upper_level": 0.98,
                         "status": "ok", "gold_status": "ok", "reason": null,
                         "lower": -0.035, "upper": null,
                         "lower_infinite": false, "upper_infinite": true}]}}]}],
  "explainability": {"status": "available", "reason": null,
                     "label": "descritiva (sem claim causal)",
                     "shares": [{"method": "permutation", "family": "price",
                                 "share_h1": 0.4, "share_h7": 0.3, "delta": -0.1,
                                 "lower": -0.2, "upper": null,
                                 "lower_infinite": false, "upper_infinite": true,
                                 "level": 0.9, "side": "two_sided",
                                 "excludes_zero": false, "status": "ok", "reason": null}],
                     "reading": {"reading_rule": "…", "sustained": false, "…": "…"},
                     "vsn": [], "vsn_label": "horizonte-invariante; …"},
  "gold": {"published": true, "generation_status": "COMPLETED",
           "preregistration_ref": "…", "candidate": "tft_quantile", "finished_at": "…"}
}
```

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Leitura do gold inteiro por pedido lenta depois da 8.1 | M | M | medir com geração sintética do tamanho real (D15); cache por manifesto só acima de 5 s |
| Leitura do silver lenta | B | M | filtrar pelas partições (`asset`, `feature_set_name`, `year` da decisão); medido: um ano com 89 488 linhas em ~0,8 s |
| Cliente ler o intervalo como garantia | M | A | rótulo obrigatório (I7); `status` e `gold_status` por intervalo; I6 declara cruzamento possível |
| Limite infinito virar `null` silencioso | A | M | `null` + flag em todo limite que pode ser infinito (D9); CA4 |
| Gold mudar colunas ou rótulo sem o payload acompanhar | B | M | o evaluation seleciona pelo `gold_schema`; rótulo conferido (I7); contrato `[fake, real]`; `schema_version` |
| `data_root` errado parecer "sem dado" | M | M | zero runs do cohort → 500 com mensagem (I3) |
| Pedido concorrente à publicação do gold | B | B | residual do ADR 6.4.0005 declarado (§8); restrição levada à issue do job (D10) |
| "run" sugerir que a API roda o modelo | M | B | D8; a descrição da rota diz que serve o gravado |

## 11. Critérios de aceitação

- [ ] **CA1 (caminho feliz)** e2e pela app completa sobre silver e gold
      publicados em `tmp_path`: `POST /inference/run` devolve 200 com
      `schema_version = 1`, os horizontes pedidos em ordem, uma entrada por seed
      em ordem, a grade igual ao `value_guardrail` gravado, `target_date` certa e
      intervalos com **valores esperados literais** (correções com Q̂_lo ≠ Q̂_hi
      escolhidas no teste); uma data na sobreposição teste do fold k / calib do
      fold k+1 é servida pelo run de teste do fold k.
- [ ] **CA2 (404)** use case e e2e: ativo diferente; horizonte e seed fora do
      cohort; data fora do teste; data só de `calib`; h+7 das últimas sessões →
      404 com corpo `{"detail": "não há dados para o pedido solicitado…",
      "type": "not_found"}`, cada caso dizendo o que faltou; nas mesmas últimas
      sessões, pedir só h+1 → 200.
- [ ] **CA3 (gold indisponível)** sem geração publicada, com geração `BLOCKED`,
      sem `[conformal]`, sem `[h3]` e de outro candidato: 200, grade servida e
      o(s) bloco(s) `unavailable` com o motivo do I8 de cada caso; os três
      rótulos presentes mesmo assim.
- [ ] **CA4 (infinito)** correção infinita no gold e limite infinito numa
      participação de H3 → `null` com flag `true` no JSON; limite finito →
      número com flag `false` (também numa participação não-`ok` com limite
      gravado); intervalo ou participação não-`ok` sem valor → `null` com flag
      `false`; nenhum outro par (valor, flag).
- [ ] **CA5 (rótulos)** os três rótulos do payload são iguais às constantes do
      evaluation, também com blocos `unavailable`; VSN `undefined` (linhas sem
      rótulo e medidas nulas) → 200 com o bloco `available` e as linhas com
      status; → 500 em: reading (qualquer status) com rótulo ≠ `H3_LABEL`,
      linha `ok` de VSN com rótulo ≠ `VSN_LABEL` e linha não-`ok` de VSN com
      rótulo não nulo; nenhum literal dos rótulos em
      `src/financial_forecasting/features/inference/`.
- [ ] **CA6 (estados do intervalo)** cauda `undefined` e cauda `error` →
      intervalo `unavailable` com o `gold_status` e o motivo do gold; unidade
      ausente → `unavailable` "unidade ausente na geração gold"; os outros pares
      do mesmo membro seguem `ok`.
- [ ] **CA7 (inconsistência = 500)** zero runs do cohort, seed sem run, dois
      runs para o mesmo ponto, grade incompleta, nível repetido, `target_date`
      divergente entre seeds, uma cauda ausente e geração corrompida → 500
      `{"detail": …, "type": "application_error"}`.
- [ ] **CA8 (router fino)** integração do router com use case de teste: o
      pedido chega como `ServeInferenceQuery` com os tipos certos; 422 com o
      corpo padrão do FastAPI para data malformada, horizonte ≤ 0, lista vazia
      ou repetida; 404 e 500 com `{detail, type}` vindos dos handlers; o
      router não captura exceção.
- [ ] **CA9 (port do consumidor)** `ServingGoldReader` com fake e suíte de
      contrato `[fake, real]` (real = `ReadServingGold` sobre `ParquetGoldStore`
      em `tmp_path`): geração publicada → registros iguais; sem geração,
      `BLOCKED`, sem `[conformal]`/`[h3]`, VSN `undefined` → estados certos;
      `+inf` reconstruído; corrompida → erro; `check_port_coverage.py` verde.
- [ ] **CA10 (fronteiras)** `lint-imports` verde com uma aresta nova declarada
      (evaluation → inference, DTOs) e caso de violação para outro módulo do
      evaluation; `inference-no-torch-leak` cobre o pacote do router, com caso
      de violação; teste em subprocesso: depois de `create_app()` e de um
      pedido, `torch`, `lightning` e `pytorch_forecasting` não estão em
      `sys.modules`; o inference não importa o evaluation.
- [ ] **CA11 (configuração)** sem cohort configurado: 500 "serviço de
      inferência sem cohort configurado"; arquivo ilegível e cohort não
      congelado: `create_app` falha.
- [ ] **CA12 (verificação end-to-end real e tempo)** a app sobe com o cohort
      real (`DATA_ROOT=data/cohorts/aapl`) e um pedido real a uma data de teste
      devolve 200 com 10 seeds × 2 horizontes iguais à grade gravada e os blocos
      do gold `unavailable` ("gold não publicado"), em menos de 5 s; o tempo do
      leitor sobre uma geração gold sintética do tamanho da real fica abaixo de
      5 s (D15). Medições coladas como `[measurement]`.
- [ ] **CA13 (cegamento, só leitura e determinismo)** o use case lê só
      `dim_run` e `fact_oos_predictions` (fake que registra as leituras); os
      ports usados só têm métodos de leitura; dois pedidos iguais → corpos
      iguais.
- [ ] **CA14 (docs)** roadmap (alinhado antes da aprovação), LAYOUT §7, nota no
      ADR 0.0.0053, errata Huyen (ADR 7.1.0001, concept 7.1) e overview §10
      emendados; issue do job agendado aberta e citada no §7 do technical.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4, incluindo os campos dos registros de H3.
- [x] Toda decisão em §7 tem fonte rastreável? — cada D cita B1–B3 do humano, doc, ADR, skill, código ou medição.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)? — FastAPI/Starlette/Pydantic já pinados; pedido, resposta e erros em §4 e §9; sem auth (non-goal).
- [x] Decisões com alternativa real descartada têm ADR escrito? — 7.4.0001 (paradigma, seeds, ligação, 404, gold ausente, conformal, leitor e exceção ao 0.0.0053, atualização) e 7.4.0002 (payload, infinito, rótulos, erros, port-in); D7 e D12–D15 seguem fonte fechada ou medição; D10 está no item 8 do 7.4.0001.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 7.2 e 7.3 `done` no roadmap (e 7.1, 6.5).
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)? — ~8: DTOs + port + fake; exceção + use case; leitor do evaluation + aresta; contrato do port; schemas + router + handler; wiring + e2e; gates de fronteira; docs. Mais a verificação real.
- [x] Riscos críticos têm mitigação plausível? — §10.
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — (i) servir: a solução direta é ler o que já está gravado, não rodar o modelo (D1); (ii) gold: reusa o `GoldGenerationReader`, o `from_stored`, os leitores de célula e o `gold_schema`, sem leitor de Parquet no inference (D5); (iii) intervalo: reusa `PairCorrection.limits`, sem fórmula nova; (iv) rótulos: a coluna gravada conferida contra a constante de dono único, sem literal novo (I7); (v) formato de erro: concern transversal tratado no handler global da app (D11), não na rota; (vi) infinito: a convenção `null` + flag que o gold já usa (D9); (vii) atualização dos dados: concern a montante (outro cohort e job agendado), registrado como issue em vez de embutido na API (D10); (viii) cache: não entra sem medição (D15). Nenhuma captura local de concern transversal identificada.
- [x] A Stage calcula alguma métrica sobre o cohort real? — não: a API lê predições e o gold publicado; a verificação real lê só predições (CA12, CA13).
- [x] Algum caminho da API carrega checkpoint ou pilha de deep learning? — não (I1, CA10).
- [x] O `gate_mode: batch` está justificado? — D13.

## 13. Questões em aberto

Nenhuma. B1–B3 foram respondidos pelo humano no Passo 1b; os forks de
convenção da pesquisa foram fechados pela escada da `evidence-resolution`
(ADRs 7.4.0001 e 7.4.0002).

## 14. Referências

- [`../../overview.md`](../../overview.md) — §3 (API fina), §6 (FastAPI só como adapter de entrada)
- [`../../roadmap.md`](../../roadmap.md) — Stage `7.4-inference-api` e vizinhas 7.2, 7.3, 8.1
- [`../../domain/inference/conformal-benchmark-and-feature-attribution.md`](../../domain/inference/conformal-benchmark-and-feature-attribution.md) — §2.3, §2.4, §4.5, §4.8, §4.11, §4.13, §5.7, §5.8, §6, §7
- [`../7.1-inference-engine/concept.md`](../7.1-inference-engine/concept.md) — D8, D9
- [`../7.2-conformal-cqr/concept.md`](../7.2-conformal-cqr/concept.md) — D9
- [`../7.3-explainability/concept.md`](../7.3-explainability/concept.md) — §8 (7.4)
- ADRs: 0.0.0008, 0.0.0010, 0.0.0053, 1.1.0001, 4.1.0001, 6.4.0005, 6.5.0005, 7.1.0001, 7.1.0002, 7.1.0003, 7.2.0003, 7.3.0001; desta Stage: 7.4.0001, 7.4.0002
- Skills: `fastapi-thin-adapter`, `hex-arch-python`, `dmls-ch06-deployment-and-inference-decisions`
- Issue #201 §Referências — Huyen 2022 cap. 7; Sandve et al. 2013; Fakoor et al. 2023; Barber et al. 2023; Bracher et al. 2021; RFC 8259; RFC 9110; RFC 9457; RFC 10008; Google AIP-180/AIP-185; JSON:API v1.1; documentação do FastAPI
