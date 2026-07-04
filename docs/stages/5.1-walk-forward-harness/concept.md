---
title: Concept — Stage 5.1 — Harness de walk-forward (purga + embargo + calib dedicado)
description: Serviço de domínio WalkForwardSplitter (folds walk-forward expansivos com purga+embargo em dias de pregão via TradingCalendar, região de val particionada em early-stop + calib dedicado adjacente ao test), VOs FoldSplit/ScopeSpec, SplitFingerprint estendido para 4 vias, e serviço de dedup operationally-latest
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar as Tasks 5.1
keywords: [concept, walk-forward-harness, purge, embargo, calibration-partition, conformal, cqr, scope-spec, fold-split, operationally-latest-dedup, expanding-window, anti-leakage, modeling]
status: done
created_at: 2026-07-04
updated_at: 2026-07-04
stage_id: 5.1-walk-forward-harness
stage_title: Harness de walk-forward
step_id: 5
step_title: Modelagem, baselines e treino
depends_on: [3.5-dataset-builder-and-contracts, 4.3-prediction-persister, 2.4-trading-calendar, 1.4-identity-and-fingerprints]
---

# Concept — Stage 5.1 — Harness de walk-forward

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task), ver [`PIPELINE.md`](../../PIPELINE.md) §4.

## 1. Escopo

### Dentro do escopo

- **Novo bounded context `modeling`** (camadas `domain` apenas nesta Stage),
  registrado nas fitness functions (`.importlinter` contratos `hexagonal-layers`
  e `domain-purity`).
- **Serviço de domínio `WalkForwardSplitter`**
  (`features/modeling/domain/services/walk_forward_splitter.py`): gera folds
  walk-forward de **janela expansiva** (anchored) sobre a sequência ordenada de
  dias de pregão do dataset, com **purga + embargo** medidos em dias de pregão
  via `TradingCalendar.shift_trading_days` (2.4). Cada fold particiona a região
  de validação em **early-stop** e **calib dedicado** (calib adjacente ao test,
  intocado por early stopping — invariante do conformal do Step 7).
- **Value object `FoldSplit`**
  (`features/modeling/domain/value_objects/fold_split.py`): 4 listas disjuntas
  de timestamps (`train` / `early_stop` / `calib` / `test`), `fold_index` e a
  `SplitFingerprint` do fold. Invariantes de disjunção e ordenação temporal
  verificadas na construção.
- **Value object `ScopeSpec`**
  (`features/modeling/domain/value_objects/scope_spec.py`): identidade do
  **cohort** que isola comparações justas (`asset_id`, `feature_set_name`,
  `max_horizon`, `cohort_id`). `max_horizon` fixa a largura da purga.
- **Serviço de domínio de dedup operationally-latest**
  (`features/modeling/domain/services/operationally_latest_dedup.py`): função
  pura que, por chave de alinhamento OOS, mantém o registro **operacionalmente
  mais recente** (maior rank operacional), colapsando duplicatas de folds
  sobrepostos.
- **Extensão do VO `SplitFingerprint` (1.4)** com um campo opcional e
  retrocompatível `calib`, para que a impressão do split ateste a fronteira do
  calib dedicado (ver §7, ADR 5.1.0003).

### Fora do escopo (explicitamente)

- **Combinatorial Purged Cross-Validation** (López de Prado 2018, cap. 12):
  cogitada e descartada — o piloto AAPL é single-asset com pouca história
  (~4000 pregões) e o confirmatório exige um protocolo temporal único e
  pré-registrável, não uma família combinatória de caminhos (roadmap `non_goals`).
- **Treino de modelos** (baselines 5.2, GBM 5.3, TFT 5.4) e qualquer uso de
  bibliotecas de ML/dados — o harness é domínio puro sobre listas de datas.
- **Persistência** de folds/predições (já entregue em 4.3; o harness não grava).
- **Janela deslizante (rolling)** — descartada nesta Stage a favor da expansiva
  (ver §7, ADR 5.1.0001); permanece como extensão futura documentada.
- **Camada `application`** do BC `modeling` (ports/use cases) — nasce em 5.2+,
  quando os treinadores orquestram o harness.

### Vínculo com o roadmap

Primeira Stage do **Step 5** e do BC `modeling`. Entrega a **pré-condição
temporal** de todo o Step 5 e do Step 6/7: nenhum modelo (baseline, GBM, TFT) é
treinado nem avaliado sem um protocolo walk-forward sem vazamento. Concretiza a
**regra 4 do ADR 0.0.0018** ("Purge + embargo splits … Stage 5.1") e prepara o
**invariante de calib dedicado** que o conformal CQR do Step 7.2 consome
(roadmap §Stage 5.1, §Stage 7.2).

## 2. Objetivo da Stage

Ao fechar esta Stage, existe um serviço de domínio puro que, dada a sequência de
dias de pregão do dataset e um `ScopeSpec`, produz folds walk-forward expansivos
cujas quatro partições (`train`/`early_stop`/`calib`/`test`) são **provadamente
disjuntas e temporalmente ordenadas**, separadas por **purga+embargo de dias de
pregão** que impede o horizonte-alvo de vazar entre blocos, com o **calib
dedicado adjacente ao test**; e um serviço de dedup operationally-latest que
garante **uma observação por ponto alinhado**. Tudo verificado por testes que
falham na violação (não por convenção).

## 3. Contexto e premissas

### Contexto

O dataset TFT (Stage 3.5) é uma **grade densa de dias de pregão**: uma linha por
pregão, indexada por `decision_day` (posição no array de sessões), carregando o
`target_return` backward `log(close_t/close_{t-1})` (ADR 3.5.0001) e `time_idx`.
O alvo de horizonte `h` de uma decisão no índice `t` realiza-se em
`dataset_timestamps[t + h]` — **h sessões à frente**, indexação por posição no
array de sessões (ADR 4.3.0001, "PROIBIDO `pd.Timedelta(days=h)`"). Uma amostra,
portanto, é uma **linha-pregão**; o splitter particiona a sequência ordenada
dessas linhas.

A aritmética de sessão é fornecida pelo serviço de domínio `TradingCalendar`
(2.4), cujo método `shift_trading_days(day, n, *, direction)` foi construído
**expressamente para o embargo/purga desta Stage** (docstring de
`trading_calendar.py:95-129`; ADR 2.4.0001), com deslocamento nas duas direções e
**erro (sem clamp)** em estouro de janela.

O **calib dedicado** existe por causa do benchmark conformal do Step 7.2 (CQR via
MAPIE): conformal split exige um conjunto de calibração **disjunto** do usado para
ajustar/selecionar o modelo, e sua validade de cobertura repousa nessa
independência (ver §7, ADR 5.1.0002).

### Premissas

- A sequência de dias de pregão de entrada é a **grade densa** do dataset (uma
  linha por sessão), ordenada estritamente e composta de sessões reais — cada uma
  validável em `TradingCalendar.is_session`.
- Os horizontes do cohort têm um **máximo `max_horizon`** conhecido (a maior
  distância `h` que qualquer modelo do cohort prevê), que fixa a largura da purga.
- Timestamps trafegam no domínio como `date` (grade de pregão) e são serializados
  para strings ISO8601 ao compor `FoldSplit`/`SplitFingerprint` (o domínio nunca
  recebe `datetime` cru — invariante herdada de 1.4).

### Dependências

- `3.5-dataset-builder-and-contracts` (`done`): define a grade de pregão e o
  `target_return` que o splitter particiona.
- `4.3-prediction-persister` (`done`): fixa a convenção `target_timestamp =
  timestamps[decision_idx + h]` (indexação por sessão) que a purga honra; e a PK
  LONG OOS que a chave de dedup espelha.
- `2.4-trading-calendar` (`done`): `TradingCalendar.shift_trading_days` —
  primitiva de purga/embargo em dias de pregão.
- `1.4-identity-and-fingerprints` (`done`): `SplitFingerprint` (estendido aqui) e
  o port `Hasher` (injetado para computar a impressão).

## 4. Contratos

### Introduzidos

- **`WalkForwardSplitter`** (`domain-service`) — construído com um
  `TradingCalendar`. Método:

  ```python
  def split(
      self,
      sessions: Sequence[date],            # grade densa de pregão, ordenada
      scope: ScopeSpec,
      *,
      n_folds: int,
      test_size: int,                      # sessões por bloco de test
      val_size: int,                       # sessões no early-stop
      calib_size: int,                     # sessões no calib dedicado
      embargo: int,                        # sessões de embargo (além da purga)
      hasher: Hasher,                      # port 1.4, injetado (TYPE_CHECKING)
  ) -> tuple[FoldSplit, ...]:
      ...
  ```

  Geometria por fold (ordem temporal, janela expansiva):
  `TRAIN | gap | EARLY_STOP | gap | CALIB | gap | TEST`, com `gap =
  scope.max_horizon (purga) + embargo`. Os `test` blocks ladrilham a cauda em
  `n_folds` blocos contíguos e disjuntos de tamanho `test_size`; `train` sempre
  ancora em `sessions[0]` e cresce com o fold.

- **`FoldSplit`** (`value-object`, frozen) — `fold_index: int`, `train`,
  `early_stop`, `calib`, `test` (`tuple[str, ...]` ISO8601), `fingerprint:
  SplitFingerprint`. Construção valida: cada lista estritamente crescente; as
  quatro **pairwise disjuntas**; ordenação de bloco `max(train) < min(early_stop)
  < … < min(test)`; nenhuma lista vazia.

- **`ScopeSpec`** (`value-object`, frozen) — `asset_id: str`, `feature_set_name:
  str`, `max_horizon: int`, `cohort_id: str | None = None`. Valida
  `asset_id`/`feature_set_name` não-vazios e `max_horizon >= 1`.

- **`deduplicate_operationally_latest`** (`domain-service`, função pura):

  ```python
  def deduplicate_operationally_latest(
      records: Iterable[T],
      *,
      alignment_key: Callable[[T], Hashable],
      operational_rank: Callable[[T], int],
  ) -> tuple[T, ...]:
      ...
  ```

  Por chave de alinhamento, mantém o registro de **maior `operational_rank`**.
  Empate (mesma chave, mesmo rank) → `ValueError` (ambiguidade de "mais recente",
  fail-fast). Ordem de saída = ordem de primeira aparição de cada chave
  (determinística dada a ordem de entrada).

### Consumidos

- **`TradingCalendar`** — declarado em `2.4-trading-calendar`. Usado via
  `shift_trading_days` para resolver as fronteiras de purga/embargo em dias de
  pregão e via `is_session` para validar a grade.
- **`SplitFingerprint`** — declarado em `1.4-identity-and-fingerprints`.
  **Estendido** aqui com o campo opcional `calib` (§7, ADR 5.1.0003).
- **`Hasher`** (port-out) — declarado em `1.4`. Injetado em `split(...)` e
  repassado a `SplitFingerprint.compute`; tipado via `TYPE_CHECKING`
  (`.importlinter` `exclude_type_checking_imports = True`), sem acoplamento de
  runtime domain→application.

## 5. Invariantes e regras

- **I1 — Disjunção.** Em cada `FoldSplit`, `train`, `early_stop`, `calib` e
  `test` não compartilham nenhum timestamp.
- **I2 — Ordenação de bloco.** `max(train) < min(early_stop) < max(early_stop) <
  min(calib) < max(calib) < min(test)` (blocos temporais contíguos na ordem).
- **I3 — Purga por horizonte.** Entre o fim de um bloco e o início do próximo há
  **> `scope.max_horizon` sessões** de separação, de modo que nenhum
  `target_timestamp = t + h` (h ≤ max_horizon) de um bloco caia em bloco
  posterior. Verificado em dias de pregão (`shift_trading_days`).
- **I4 — Embargo.** Além da purga, há **≥ `embargo` sessões** de buffer em cada
  fronteira de bloco (serial-correlation buffer; requisito de embargo do 7.2).
- **I5 — Calib dedicado e adjacente.** O `calib` é o bloco **imediatamente antes
  do test** (após o gap), **nunca** usado como early-stop; é o bloco de validação
  mais recente (recency conformal — ADR 5.1.0002).
- **I6 — Janela expansiva.** Todo fold tem `train[0] == sessions[0].isoformat()`;
  `len(train)` cresce com `fold_index` (ADR 5.1.0001).
- **I7 — Ladrilhamento do test.** Os `n_folds` blocos de `test` são contíguos,
  disjuntos, de tamanho `test_size`, ancorados na cauda de `sessions`.
- **I8 — Impressão determinística.** `FoldSplit.fingerprint` é a
  `SplitFingerprint` de `{train, early_stop→val, calib, test}`; mesmos blocos →
  mesma impressão (herdado de 1.4 A5).
- **I9 — Uma observação por ponto alinhado.** Após `deduplicate_operationally_
  latest`, cada chave de alinhamento aparece uma única vez (o registro
  operacionalmente mais recente).
- **I10 — Domínio puro.** Nenhum arquivo de `modeling.domain` importa
  pandas/pyarrow/torch/numpy (fitness `domain-purity`); a única referência a
  `application` é o tipo `Hasher` sob `TYPE_CHECKING`.

## 6. Casos de erro e exceções

- **Grade inválida.** `sessions` não estritamente crescente, com duplicatas, ou
  contendo uma data que não é sessão (`is_session` falso) → `ValueError`.
- **Janela insuficiente.** Um fold cujo `train` ficaria vazio (história curta
  demais para acomodar `train + gaps + val + calib + test`) → `ValueError` (sem
  clamp — a política do projeto é **erguer, não fabricar**; ADR 0.0.0018 alt. B,
  espelha `TradingCalendar` C2/D5).
- **Parâmetros inválidos.** `n_folds < 1`, `test_size < 1`, `val_size < 1`,
  `calib_size < 1`, `embargo < 0` → `ValueError`.
- **Estouro de janela do calendário.** Propagado de
  `TradingCalendar.shift_trading_days` (`ValueError`, sem clamp) quando um offset
  cairia fora de `[start, end]` das sessões materializadas.
- **`FoldSplit` inconsistente.** Qualquer violação de I1/I2 na construção →
  `ValueError` (invariante verificada, não assumida).
- **Empate no dedup.** Duas entradas com mesma chave e mesmo `operational_rank`
  → `ValueError` (ambiguidade de "operacionalmente mais recente").

## 7. Decisões técnicas relevantes

> Cada decisão tem fonte rastreável; as três com alternativa real descartada
> viram ADR (base acadêmica citada no ADR, para rastreio do TCC).

### D1 — Janela expansiva (anchored), não deslizante

- **O quê:** os folds usam **janela expansiva** — `train` cresce desde
  `sessions[0]` a cada fold.
- **Por quê:** avaliação por rolling-origin com janela crescente é o padrão para
  séries curtas ("leverages the full data history"); o piloto AAPL tem ~4000
  pregões e o TFT é data-hungry. A não-estacionariedade é absorvida por
  **refit por fold + recency do conformal + embargo**, não por encurtar a janela.
- **Fonte:** roadmap Stage 5.1 (`non_goals`: descarta rolling implicitamente ao
  não pedi-lo); Hyndman & Athanasopoulos, *FPP3* §5.10; Tashman (2000).
- **ADR:** [`../../adr/5_1_0001-expanding-window-walk-forward.md`](../../adr/5_1_0001-expanding-window-walk-forward.md)

### D2 — Calib dedicado, disjunto do early-stop, adjacente ao test, embargoed

- **O quê:** a região de validação é particionada em `early_stop` (seleção/parada)
  e um `calib` **dedicado** que é o bloco mais recente antes do `test`, separado
  dele por purga+embargo, e **nunca** consultado para early stopping.
- **Por quê:** conformal split/CQR exige que o conjunto de calibração seja
  **disjunto** do usado para ajustar e **selecionar** o modelo — usá-lo em early
  stopping viola a independência e anula a garantia de cobertura. Sob quebra de
  exchangeability (séries temporais), a cobertura degrada quando o calib é
  desatualizado; o calib **mais recente** (adjacente ao test) é o mais
  representativo ("recent past matters most"). Espelha o invariante do 7.2 DoD
  ("calibra no calib dedicado, não no early-stop, … com embargo").
- **Fonte:** Romano, Patterson & Candès (2019) CQR; *A Gentle Introduction to
  Conformal Time Series Forecasting* (2025); Barber, Candès, Ramdas & Tibshirani
  (2023); roadmap Stage 7.2; ADR 0.0.0018.
- **ADR:** [`../../adr/5_1_0002-dedicated-calibration-partition.md`](../../adr/5_1_0002-dedicated-calibration-partition.md)

### D3 — `SplitFingerprint` estendido para 4 vias (calib first-class)

- **O quê:** o VO compartilhado `SplitFingerprint` (1.4) ganha um campo
  **opcional e retrocompatível** `calib`; quando presente, entra no payload
  canônico do hash. Callers 3-vias existentes produzem a mesma impressão de antes.
- **Por quê:** como o calib é uma partição metodologicamente first-class (D2), a
  identidade do split precisa **atestar sua fronteira** — dobrar calib em val
  cegaria a impressão e permitiria colisões (dois folds com mesmo train/val/test e
  calib distinto). Estender o único primitivo canônico do projeto (DRY) é
  preferível a duplicá-lo num `FoldFingerprint` local.
- **Fonte:** decisão de sessão (pergunta respondida 2026-07-04, com base na
  literatura de D2); roadmap `contratos_consumidos: SplitFingerprint (1.4)`.
- **ADR:** [`../../adr/5_1_0003-split-fingerprint-four-way-calib.md`](../../adr/5_1_0003-split-fingerprint-four-way-calib.md)

### D4 — Purga/embargo em dias de pregão via `TradingCalendar` (erguer, sem clamp)

- **O quê:** as fronteiras de purga (largura `max_horizon`) e embargo são
  resolvidas em **dias de pregão** via `TradingCalendar.shift_trading_days`;
  estouro de janela **ergue** (não faz clamp).
- **Por quê:** o `target_timestamp` é indexado por sessão (ADR 4.3.0001), então a
  contaminação só pode ser medida em unidades de sessão; erguer em vez de clampar
  superfície janela estreita/dado ruim (postura do projeto).
- **Fonte:** ADR 0.0.0018 (regra 4 + alt. B "raise, no clamp"); ADR 2.4.0001;
  roadmap `contratos_consumidos: TradingCalendar (2.4)`. (Sem ADR próprio —
  decisão derivada, sem alternativa nova.)

### D5 — Dedup operationally-latest: chave OOS + tie-break que ergue

- **O quê:** a dedup colapsa registros que compartilham a chave de alinhamento OOS
  (espelha a PK LONG do 4.3: asset/split-scope, horizonte, `target_timestamp`,
  `quantile_level`), mantendo o de maior rank operacional (fold/decisão mais
  recente); empate exato ergue `ValueError`.
- **Por quê:** folds sobrepostos podem prever o mesmo `target_timestamp` mais de
  uma vez; a métrica OOS exige **1 obs/unidade** com alinhamento estrito por
  `target_timestamp` (overview §OOS; ADR 4.1.0002 PK). "Operacionalmente mais
  recente" segue do próprio termo. A função é genérica (callables) porque as
  predições concretas só existem em 5.2+.
- **Fonte:** overview §"dedup operationally-latest"; ADR 4.1.0002; roadmap Stage
  5.1. (Sem ADR próprio — convention fail-fast; registrada aqui.)

## 8. Integrações

### Internas (com outras Stages/módulos)

- `shared/domain/services/trading_calendar.py` (2.4): consumido para aritmética
  de sessão.
- `shared/domain/value_objects/split_fingerprint.py` (1.4): **modificado**
  (campo opcional `calib`) — mudança aditiva e retrocompatível; o teste de 1.4
  ganha um caso 4-vias.
- `.importlinter`: `modeling` registrado no contrato `hexagonal-layers`
  (container) e `domain-purity` (source_modules). Não entra em
  `store-no-storage-leak` (o domínio de 5.1 não toca o `MedallionStore`).
- Consumidores a jusante: 5.2/5.3/5.4 (treinadores orquestram `split`), 7.2
  (conformal consome a partição `calib`).

### Externas

- Nenhuma. O harness é domínio puro (stdlib-only); não fala com rede, disco nem
  bibliotecas de dados/ML.

## 9. Modelo de dados (se aplicável)

Não há persistência nesta Stage. O "modelo" é a geometria in-memory do fold:

```
sessions:  s0 ........................................................ sN-1
fold f:   [ TRAIN .......... ]  gap  [ EARLY_STOP ] gap [ CALIB ] gap [ TEST ]
          ^s0 (expansivo)            gap = max_horizon (purga) + embargo
```

## 10. Riscos e mitigações

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Off-by-one na purga (janela de horizonte vaza 1 sessão) | M | A | Teste dedicado com `max_horizon` variado assertando distância de sessão `> max_horizon` via `shift_trading_days`; espelha a prova de alinhamento do 4.3 |
| Calib acidentalmente usado como early-stop a jusante | B | A | `FoldSplit` expõe `calib` e `early_stop` como campos distintos e disjuntos (I1/I5); 7.2 tem teste `test_conformal_calib_set_dedicated` |
| História curta faz folds vazios silenciosos | M | M | `ValueError` explícito (sem clamp) em janela insuficiente; testado |
| Extensão do `SplitFingerprint` quebra callers 3-vias | B | M | Campo `calib` opcional com default `None`; payload inalterado quando ausente; teste de 1.4 mantém casos 3-vias verdes |
| Rolling seria necessário por não-estacionariedade | B | M | Documentado como extensão futura (ADR 5.1.0001); embargo+recency conformal cobrem o piloto |

## 11. Critérios de aceitação

- [ ] Folds walk-forward **expansivos** (train ancora em `sessions[0]`, cresce
      com o fold) com **purga+embargo de dias de pregão** via `TradingCalendar`;
      distância entre blocos `> max_horizon` sessões (I3/I4/I6) — testado com
      `max_horizon` variado.
- [ ] Região de val particionada em **early-stop + calib dedicado**, com calib
      adjacente ao test e **intocado** por early stopping (I5) — testado.
- [ ] **Sem sobreposição** train/early_stop/calib/test em nenhum fold (I1/I2) —
      testado.
- [ ] `test_size` ladrilha a cauda em `n_folds` blocos disjuntos (I7) — testado.
- [ ] `FoldSplit` carrega a `SplitFingerprint` 4-vias determinística (I8);
      `SplitFingerprint` estendido mantém callers 3-vias idênticos — testado.
- [ ] Dedup **operationally-latest** mantém 1 registro por chave (maior rank),
      ergue em empate (I9) — testado.
- [ ] Janela insuficiente / grade inválida / parâmetros inválidos **erguem**
      `ValueError` (sem clamp) — testado (§6).
- [ ] `modeling.domain` registrado e verde em `domain-purity` e `hexagonal-layers`
      (`import pandas` no domínio reprova) — provado por quebra intencional.
- [ ] `make check` verde; cobertura ≥ 90% no diff da Stage.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4)
- [x] Toda decisão em §7 tem fonte rastreável? (roadmap/ADRs/papers/sessão)
- [x] Toda integração externa tem contrato definido? (não há externas — §8)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1/D2/D3 →
      5.1.0001/0002/0003)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (3.5, 4.3,
      2.4, 1.4 todas `done`)
- [x] Stage cabe em ~3–8 Tasks? (6 Tasks — ver `technical.md`)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] O harness é domínio puro (sem I/O, sem libs de dados)? (§5 I10)

## 13. Questões em aberto

- Nenhuma. As três bifurcações materiais (fingerprint 4-vias, esquema de janela,
  posição do calib) foram decididas na sessão com base em pesquisa acadêmica
  (§7 D1/D2/D3).

## 14. Referências

- [`../../roadmap.md`](../../roadmap.md) — Stage `5.1-walk-forward-harness` e
  vizinhas (5.2–5.5, 7.2).
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `5_1_`).
- ADRs relacionados: [0.0.0018](../../adr/0_0_0018-anti-leakage-non-negotiable.md)
  (purge+embargo), [2.4.0001](../../adr/2_4_0001-trading-calendar-domain-over-materialized-sessions-vo.md)
  (shift bidirecional), [4.3.0001](../../adr/4_3_0001-target-timestamp-trading-day-indexing-and-domain-purity.md)
  (indexação por sessão), [4.1.0002](../../adr/4_1_0002-fact-oos-predictions-long-quantile-format.md)
  (PK LONG OOS), [1.4.0001](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md)
  (hash canônico).
- Externas (base do TCC):
  - Romano, Y., Patterson, E., Candès, E. (2019). *Conformalized Quantile
    Regression*. NeurIPS. arXiv:1905.03222.
  - Barber, R. F., Candès, E. J., Ramdas, A., Tibshirani, R. J. (2023).
    *Conformal prediction beyond exchangeability*. Annals of Statistics.
  - *A Gentle Introduction to Conformal Time Series Forecasting* (2025).
    arXiv:2511.13608.
  - Hyndman, R. J., Athanasopoulos, G. *Forecasting: Principles and Practice*
    (3ª ed.), §5.10 (time series cross-validation / rolling origin).
  - Tashman, L. J. (2000). *Out-of-sample tests of forecasting accuracy: an
    analysis and review*. International Journal of Forecasting.
  - López de Prado, M. (2018). *Advances in Financial Machine Learning*, cap. 7
    (purged K-fold + embargo).
