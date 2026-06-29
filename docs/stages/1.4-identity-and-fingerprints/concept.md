---
title: Concept — Stage 1.4 — Identidade e fingerprints determinísticos
description: Quatro value objects de identidade (RunId, DatasetFingerprint, ConfigSignature, SplitFingerprint) em domínio puro + port-out Hasher e adapter de hashing canônico, com canonicalização endurecida de floats e rejeição de NaN/inf
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar os value objects e o adapter de hashing
keywords: [concept, identity, fingerprint, run-id, hasher, canonical-json, sha256, determinism, value-object, port-out, hexagonal]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.4-identity-and-fingerprints
stage_title: Identidade e fingerprints determinísticos
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.3-architecture-contracts]
---

# Concept — Stage 1.4 — Identidade e fingerprints determinísticos

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo
- Quatro **value objects de identidade determinística** em domínio puro
  (`shared/domain/value_objects/`), cada um frozen dataclass, stdlib-only,
  cujo valor é uma **string hex canônica** produzida por delegação ao port:
  - **`RunId`** — identidade composta de 9 campos do run.
  - **`DatasetFingerprint`** — impressão digital estrutural de um dataset
    (com floats canonicalizados e rejeição de NaN/inf).
  - **`ConfigSignature`** — assinatura de um dict de config após remover
    chaves voláteis.
  - **`SplitFingerprint`** — impressão das listas de timestamps de
    train/val/test, invariante à ordem dentro de cada split.
- **Port-out `Hasher`** (Protocol) em
  `shared/application/ports/out/hasher.py`, que define a **semântica
  canônica** de hashing (não o algoritmo concreto): `hash_mapping` sobre um
  mapping e `hash_text` sobre uma string.
- **Adapter `CanonicalJsonHasher`** em `shared/adapters/out/hashing/`
  (a subárvore `shared/adapters/` **não existe hoje** e é criada nesta
  Stage), implementando `Hasher` com `json.dumps(sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)` + `sha256` hex.
- **Endurecimento da canonicalização de floats e tratamento de NaN/inf**
  em relação ao repo antigo (que serializava floats crus).
- Testes: **unit dos 4 VOs** + **contract test do `Hasher`** parametrizado
  sobre fake in-memory e adapter real (ambos passam o **mesmo** contrato).
- **ADR** `1_4_0001` para a política de canonicalização de hash.

### Fora do escopo (explicitamente)
- **Persistência** de identidade/fingerprints (Step 4) — nenhum I/O.
- **Schemas de tabela** do silver (Stage 4.1).
- **Leitura de disco / `_sha256_file`** e a variante
  `compute_dataset_fingerprint_from_file` — pertencem ao adapter de
  persistência (Step 4.x); `DatasetFingerprint` recebe o
  `parquet_file_hash` **já calculado**.
- **`feature_set_hash` como VO** — é apenas **insumo** do `RunId`, exposto
  como método `hash_text` do `Hasher`, não uma identidade de primeira
  classe desta Stage.
- **Grade de quantis**, `Settings`, MLflow / `ExperimentTracker`
  (Stage 1.5).
- **Pydantic** em qualquer ponto do domínio.

### Vínculo com o roadmap
Esta Stage entrega a base de **rastreabilidade/auditoria** do Step 1
(Fundação): identidade determinística é o que torna cada decisão
reconstruível por `run_id` + `config_signature` + `split_fingerprint`
(Overview §3, §4 "Reprodutibilidade"). O `Hasher` introduzido aqui é
**consumido** pela Stage 1.5 (`contratos_consumidos: [Hasher (1.4)]`) e os
VOs alimentam o silver da Stage 4.1 (`contratos_consumidos: [RunId,
fingerprints (1.4)]`). Ver `roadmap.md` §"Stage 1.4".

## 2. Objetivo da Stage

Ao final desta Stage, **o mesmo conjunto canônico de campos sempre produz o
mesmo `run_id`/fingerprint** — determinístico e repetível entre
processos/plataformas, com float/NaN/datetime canonicalizados de forma
estável — exposto como value objects de domínio puro que delegam o hash a
um port-out `Hasher` testável por contrato.

## 3. Contexto e premissas

### Contexto
O repo antigo
(`/home/marcelo/Code/financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`)
já implementa funções de hash canônico (`_canonical_json`, `_sha256_text`,
`compute_config_signature`, `compute_split_fingerprint`,
`compute_dataset_fingerprint`, `compute_run_id`) que constituem o **contrato
a replicar com julgamento**. Lá essas funções vivem na camada de
infraestrutura, acopladas a I/O e sem teste de float/NaN. Nesta reconstrução
hexagonal, a **identidade vira domínio** (VOs puros) e o **algoritmo vira
adapter** atrás de um port, fechando duas lacunas conhecidas: (a) floats
crus serializados (`analytics_store_schema.py:73-74`) e (b) ausência de
guard para NaN/inf.

### Premissas
- O chamador entrega **datas já formatadas como strings ISO8601** (faz
  `.isoformat()` antes); o VO nunca recebe `datetime` cru.
- `parquet_file_hash` chega **pré-calculado** (o I/O fica no adapter de
  persistência da Stage 4.x).
- A regra de pureza de domínio da Stage 1.3 (import-linter
  `domain-purity`) está ativa e **reprova** qualquer import de
  pandas/pyarrow/torch/numpy/pydantic/sqlalchemy no domínio.

### Dependências
- `1.3-architecture-contracts`: os contratos import-linter (layers +
  forbidden) que esta Stage precisa manter verdes; em especial a regra de
  pureza de domínio que os 4 VOs devem satisfazer (stdlib-only).

## 4. Contratos

### Introduzidos

- **`Hasher`** (`port-out`) — `shared/application/ports/out/hasher.py`.
  Define a semântica canônica de hashing determinístico; o adapter
  implementa o algoritmo concreto.

  ```python
  from collections.abc import Mapping
  from typing import Protocol

  class Hasher(Protocol):
      """Contrato de hashing canônico determinístico."""

      def hash_mapping(self, payload: Mapping[str, object]) -> str:
          """sha256 hex sobre JSON canônico do mapping.

          Semântica canônica garantida: chaves ordenadas (sort_keys);
          floats canonicalizados de forma estável; NaN/±inf REJEITADOS
          (ValueError); None -> null. A ORDEM das chaves é irrelevante.
          """
          ...

      def hash_text(self, text: str) -> str:
          """sha256 hex sobre o texto (usado p.ex. p/ feature_set_hash
          via '|'.join de features ordenadas — sensível à ordem)."""
          ...
  ```

- **`RunId`** (`value-object`) — frozen dataclass; valor = hex string.
  Identidade composta de **9 campos**:
  `{asset, feature_set_hash, trial_number|None, fold|None, seed|None,
  model_version, config_signature, split_signature, pipeline_version}`.
  Factory `RunId.compute(*, hasher: Hasher, ...) -> RunId`. Variar
  **qualquer** campo (inclusive `None -> valor`) muda o `run_id`.

- **`DatasetFingerprint`** (`value-object`) — frozen; valor = hex string.
  Payload `{asset, timestamp_min: str-ISO, timestamp_max: str-ISO,
  row_count: int, close_sum: float, volume_sum: float,
  parquet_file_hash: str}`. Floats **canonicalizados** antes do hash;
  NaN/±inf **rejeitados** (`ValueError`). Recebe `parquet_file_hash` já
  calculado (sem I/O no domínio).

- **`ConfigSignature`** (`value-object`) — frozen; valor = hex string.
  Hash de um dict de config após **remover** as chaves voláteis
  `("created_at", "started_at", "ended_at", "timestamp")`. `None -> null`
  nativo do `json.dumps`.

- **`SplitFingerprint`** (`value-object`) — frozen; valor = hex string.
  Payload `{train, val, test}` com listas de timestamps ISO **ordenadas
  (`sorted`) por split** antes do hash; order-invariance dentro de cada
  split é garantia testada.

### Consumidos
- Nenhum contrato de Stage anterior é consumido em runtime (a Stage 1.3
  entrega gates, não interfaces). Os VOs **consomem o port `Hasher`**
  introduzido nesta mesma Stage por injeção na factory.

## 5. Invariantes e regras

- **I1 — Determinismo:** o mesmo conjunto canônico de campos sempre produz
  o mesmo hash (run_id/fingerprint), repetível entre processos/plataformas.
  *Testado.*
- **I2 — Ordem de chaves irrelevante:** a ordem de inserção das chaves do
  dict não altera o hash (garantido por `json.dumps(sort_keys=True)`).
  *Testado.*
- **I3 — Floats canonicalizados:** floats entram no payload de forma
  estável (arredondamento declarado no ADR 1.4.0001), nunca como `repr`
  cru; o mesmo valor matemático produz o mesmo hash. *Testado.*
- **I4 — NaN/±inf rejeitados:** `NaN` e `±inf` levantam `ValueError` ao
  construir o fingerprint (não há sentinela/null); `json.dumps` default
  emitiria `NaN`/`Infinity`, que é JSON inválido e semanticamente
  não-determinístico. *Testado.*
- **I5 — ConfigSignature ignora voláteis:** as chaves
  `created_at/started_at/ended_at/timestamp` são removidas antes do hash;
  variá-las não muda a assinatura. *Testado.*
- **I6 — SplitFingerprint order-invariant por split:** ordenar (`sorted`)
  cada split antes do hash torna a impressão invariante à ordem **dentro**
  de cada split e sensível ao **conteúdo**. *Testado.*
- **I7 — `None -> null`:** campos opcionais do `RunId`
  (`trial_number/fold/seed`) entram no payload canônico como `null` e
  fazem parte da chave (não são omitidos).
- **I8 — Datas como strings ISO8601:** o VO recebe `str` já formatada,
  nunca `datetime` cru; a formatação é responsabilidade do chamador.
- **I9 — VOs frozen:** identidade por valor, imutáveis (`@dataclass(frozen=True)`).
- **I10 — Domínio stdlib-only:** apenas `json`/`hashlib` (e tipos stdlib);
  pandas/pyarrow/torch/numpy/pydantic/sqlalchemy/fastapi **proibidos**
  (import-linter `domain-purity` reprova).
- **I11 — Paridade fake↔real:** o `FakeHasher` in-memory e o
  `CanonicalJsonHasher` real passam **exatamente** o mesmo contract test
  (paridade de comportamento canônico).
- **I12 — Código vivo coberto:** cobertura ≥ 90% nos módulos novos; eles
  **não** entram em `coverage omit`.

## 6. Casos de erro e exceções

- **C1 — NaN em `close_sum`/`volume_sum`** → `ValueError` explícito ao
  construir `DatasetFingerprint` (fail-fast; NaN indica dado corrompido a
  montante, não estado legítimo a fingerprintar).
- **C2 — `+inf` ou `-inf`** em qualquer float do payload → `ValueError`
  (mesma razão de C1; `json.dumps` default os emitiria como `Infinity`,
  JSON inválido).
- **C3 — `datetime` cru passado onde se espera string ISO** → erro de tipo
  (mypy strict) / responsabilidade do chamador; o VO não converte datas.
- **C4 — Mapping com chave não-string** → comportamento indefinido do
  contrato; o port aceita `Mapping[str, object]` e o `sort_keys` do
  `json.dumps` exige chaves comparáveis/serializáveis. O contrato declara
  chaves string.

## 7. Decisões técnicas relevantes

### D1 — Algoritmo de hash vive no adapter (atrás do port), não inline no VO
- **O quê:** o algoritmo (json canônico + sha256) vive no
  `CanonicalJsonHasher` atrás do port `Hasher`; os VOs recebem o `Hasher`
  e delegam, guardando só a string hex resultante.
- **Por quê:** o roadmap §1.4 manda explicitamente Hasher (port-out) +
  adapter + contract test. Embora `json`/`hashlib` sejam stdlib (passariam
  a pureza de domínio inline), pôr o hash atrás do port (1) habilita o
  contract test fake-vs-real exigido, (2) torna o algoritmo plugável
  (trocar sha256/canonicalização sem mexer no domínio), (3) é consumido
  por 1.5/4.x como port. Custo marginal sobre inline é baixo (uma
  indireção) e o ganho de testabilidade/troca é concreto.
- **Fonte:** Roadmap §Stage 1.4 (`contratos_introduzidos: Hasher`,
  `arquivos_a_criar`); finding pré-declarado (ledger §B, 1.4).
- **ADR:** não — decisão de estrutura já pré-fechada no finding; registrada
  no `technical.md`.

### D2 — Canonicalização de floats por arredondamento declarado
- **O quê:** arredondar floats para precisão fixa declarada antes de
  serializar (round-trip via repr de float arredondado), centralizado no
  adapter; ints permanecem int.
- **Por quê:** o old serializava float cru
  (`analytics_store_schema.py:73-74`); o `repr` de float do CPython é
  estável dentro de uma versão, mas o finding pré-declarado (ledger §B)
  exige blindar contra não-determinismo da nova stack numérica (somatórios
  vindos de pandas/numpy podem diferir no último ULP entre
  versões/plataformas). Arredondamento declarado elimina a divergência de
  ULP sem perder poder discriminante prático de um fingerprint de dataset.
  Simples e trocável (precisão é parâmetro documentado).
- **Fonte:** `analytics_store_schema.py:58-77`; ledger §B (1.4); Overview
  ASSUM-4 (equivalência por tolerância declarada, não bit-identical).
- **ADR:** [`../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md`](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md)

### D3 — NaN/±inf rejeitados com ValueError (não sentinela)
- **O quê:** falhar alto (fail-fast) ao encontrar NaN/±inf no payload, em
  vez de mapear para null/sentinela e seguir.
- **Por quê:** `json.dumps` default emite `NaN`/`Infinity` (JSON inválido);
  NaN/inf num somatório indica dado corrompido a montante, não estado
  legítimo. Mascarar com sentinela esconderia corrupção. Custo: um guard.
- **Fonte:** lacuna identificada no old
  (`tests/.../test_analytics_store_schema.py` não cobre float/NaN/inf);
  ledger §B (1.4).
- **ADR:** [`../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md`](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md)
  (mesma política).

### D4 — Esquema único de dataset_fingerprint (descartar o ad-hoc do old)
- **O quê:** adotar **somente** o esquema estruturado (payload dict de
  `analytics_store_schema.py:68-76`); descartar o segundo esquema ad-hoc
  `'|'.join` de `run_baselines_use_case.py:365-389`.
- **Por quê:** o old tem duas formas divergentes do mesmo conceito —
  débito, não contrato. Um único esquema canônico evita dois fingerprints
  incompatíveis para o mesmo dataset; o estruturado é o testado/documentado.
- **Fonte:** `run_baselines_use_case.py:365-389` (débito); ledger §B (1.4).
- **ADR:** não — limpeza óbvia; registrada como `[finding]`/`[decision]` no
  `technical.md` §7.

### D5 — `feature_set_hash` é insumo via `hash_text`, não VO próprio
- **O quê:** não criar VO; expor `Hasher.hash_text(str)` e o `RunId` recebe
  `feature_set_hash` já calculado como string.
- **Por quê:** o roadmap lista só 4 VOs; `feature_set_hash` é campo do
  `run_id` no old, não identidade própria desta Stage. Manter como método
  do port evita VO fora de escopo e centraliza o `'|'.join` sensível à
  ordem no adapter. Trocável depois se virar identidade de primeira classe.
- **Fonte:** `analytics_store_schema.py:33-34, 101-124`; Roadmap §1.4
  (`contratos_introduzidos` = 4 VOs + Hasher).
- **ADR:** não.

### D6 — Assinatura do port: `hash_mapping` + `hash_text`, não `hash_bytes`
- **O quê:** dois métodos semânticos — `hash_mapping(Mapping[str, object])`
  e `hash_text(str)` — em vez de um `hash_bytes` genérico. O port encapsula
  a semântica canônica (sort_keys/float/NaN/None), não expõe bytes crus.
- **Por quê:** mapeia 1:1 os dois usos reais do old (`_canonical_json`
  sobre dict; `'|'.join` sobre lista). Um `hash_bytes` genérico empurraria
  a canonicalização para o domínio (que não pode ter a lógica de float/NaN
  sem virar impuro ou duplicado). Encapsular no port mantém o domínio limpo
  e o contrato testável.
- **Fonte:** `analytics_store_schema.py:16-22, 33-34`; finding pré-declarado.
- **ADR:** não.

## 8. Integrações

### Internas (com outras Stages/módulos)
- **`shared/application/ports/out`**: o port `Hasher` segue o padrão dos
  ports existentes (`clock.py`, `id_generator.py`) — docstring PT,
  Protocol, sem libs.
- **Stage 1.5**: consome `Hasher` (composition root injeta o
  `CanonicalJsonHasher`).
- **Stage 4.1 (silver)**: consome `RunId`/fingerprints como identidade dos
  fatos persistidos; o `_sha256_file` que calcula `parquet_file_hash` vive
  no adapter de persistência dessa Stage.

### Externas
- Nenhuma. Hashing é stdlib (`hashlib`, `json`); sem rede/serviço.

## 9. Modelo de dados (se aplicável)

Não há schema persistido nesta Stage (persistência é Step 4). Os VOs são
estruturas de valor em memória; seu "modelo" é o payload canônico de cada
fingerprint descrito em §4.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Não-determinismo de float entre versões/plataformas (ULP) | M | A | D2: arredondamento declarado no adapter; testado por I3. |
| NaN/inf mascarado silenciosamente gera fingerprint inválido | B | A | D3: `ValueError` fail-fast; testado por C1/C2. |
| Fake e adapter real divergirem na semântica canônica | M | M | I11: contract test único parametrizado sobre ambos. |
| VO importar lib proibida e furar pureza | B | A | I10: import-linter `domain-purity` (gate da Stage 1.3) reprova. |
| Subárvore nova `shared/adapters/out/hashing` não coberta pelo `.importlinter` | M | M | Task de verificação: ajustar `.importlinter` se a Hexagonal-layers não cobrir; rodar `make check`. |

## 11. Critérios de aceitação

- [ ] **A1** — `RunId.compute` é determinístico e **sensível a cada um dos
  9 campos** (incluindo `None -> valor` em `trial_number/fold/seed`).
- [ ] **A2** — `ConfigSignature.compute` ignora as 4 chaves voláteis
  (variá-las não muda a assinatura) e produz hash estável.
- [ ] **A3** — `SplitFingerprint.compute` é invariante à ordem **dentro**
  de cada split e sensível ao conteúdo de cada split.
- [ ] **A4** — `DatasetFingerprint.compute` canonicaliza
  `close_sum`/`volume_sum` (mesmo valor matemático → mesmo hash) e levanta
  `ValueError` em NaN/±inf.
- [ ] **A5** — Determinismo geral: mesmo input canônico → mesmo hash; ordem
  de chaves do dict irrelevante (I1, I2).
- [ ] **A6** — O port `Hasher` (Protocol) tem `hash_mapping` e `hash_text`
  com docstring PT no padrão de `clock.py`/`id_generator.py`; mypy strict
  verde.
- [ ] **A7** — `CanonicalJsonHasher` implementa `Hasher` com
  `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` +
  sha256 hex, canonicaliza floats e rejeita NaN/inf conforme o ADR 1.4.0001.
- [ ] **A8** — O contract test parametrizado sobre `[FakeHasher,
  CanonicalJsonHasher]` passa **idêntico** para ambos (determinismo, ordem
  irrelevante, None→null, floats canonicalizados, NaN/inf→ValueError).
- [ ] **A9** — Os 4 VOs são frozen dataclasses, stdlib-only;
  import-linter `domain-purity` + `check_layout.py` verdes.
- [ ] **A10** — `make check` (ruff + mypy strict + import-linter +
  check_layout) e `make test` verdes; cobertura ≥ 90% nos módulos novos
  (sem `omit`).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (§4: `Hasher`
  com bloco de código; 4 VOs com payload e factory)
- [x] Toda decisão em §7 tem fonte rastreável? (Roadmap §1.4, ledger §B,
  arquivos do old com linha)
- [x] Toda integração externa tem contrato definido? (Não há integração
  externa — só stdlib)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D2/D3 →
  `1_4_0001`; alternativa "serializar float cru / sentinela" no ADR)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (1.3
  fecha os gates que esta Stage consome)
- [x] Stage cabe em ~3–8 Tasks? (11 tasks atômicas finas, mas TDD
  inside-out; agrupáveis — detalhe no `technical.md`)
- [x] Riscos críticos têm mitigação plausível? (§10: ULP, NaN/inf, paridade,
  pureza)
- [x] A canonicalização de float é estável e testável? (Sim — D2/I3,
  arredondamento declarado)

## 13. Questões em aberto

- Nenhuma bloqueante. A **precisão exata** do arredondamento de float (ex.:
  `round(x, 10)` vs ~12 dígitos significativos) é decidida e fixada no ADR
  1.4.0001 — não fica em aberto.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §3/§4 (rastreabilidade por
  `run_id`/`config_signature`/`split_fingerprint`), ASSUM-4.
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.4-identity-and-fingerprints`
  e vizinhas (1.5 consome `Hasher`; 4.1 consome os VOs).
- ADRs desta Stage: [`../../adr/`](../../adr/) (prefixo `1_4_`).
- ADRs de fundação relacionados:
  [`0_0_0019`](../../adr/0_0_0019-hexagonal-enforced.md) (pureza enforçada),
  [`1_3_0001`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md)
  (gate que esta Stage mantém verde).
- Repo antigo (contrato a replicar com julgamento):
  `/home/marcelo/Code/financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`
  (`_canonical_json`:17-18; `compute_config_signature`:37-41;
  `compute_split_fingerprint`:44-55; `compute_dataset_fingerprint`:58-77;
  `compute_run_id`:101-124; `compute_feature_set_hash`:33-34).
