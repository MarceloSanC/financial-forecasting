---
title: Technical — Stage 1.4 — Identidade e fingerprints determinísticos
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, identity, fingerprint, run-id, hasher, canonical-json, sha256, determinism]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.4-identity-and-fingerprints
stage_title: Identidade e fingerprints determinísticos
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.3-architecture-contracts]
concept_ref: ./concept.md
issue_id: 11
branch: feat/11-1-4-identity-and-fingerprints
tasks_count: 8
---

# Technical — Stage 1.4 — Identidade e fingerprints determinísticos

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [1.4/task-NN]`, body em bullets,
>    rodapé `Refs #11`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, decidir com base concreta (repo antigo / ADR / doc) e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done)
>    como `[decision]`/`[deviation]`. Nunca propagar silenciosamente.
> 7. **O fechamento da Stage (commit `stage 1.4: complete` + `roadmap.md`
>    done) é feito pelo ORQUESTRADOR após auditoria independente — NÃO
>    pelo executor desta Stage.**
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/11-1-4-identity-and-fingerprints` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo
Construímos a camada de **identidade determinística** do projeto: quatro
value objects de domínio puro (`RunId`, `DatasetFingerprint`,
`ConfigSignature`, `SplitFingerprint`), cada um uma string hex sha256 sobre
um payload canônico, produzida pela delegação a um port-out `Hasher`. O
`Hasher` encapsula a semântica canônica (JSON `sort_keys` compacto + sha256,
floats arredondados a 10 casas, NaN/±inf rejeitados, `None -> null`); um
`FakeHasher` in-memory e o `CanonicalJsonHasher` real passam o **mesmo**
contract test. Replica o esquema do repo antigo
(`analytics_store_schema.py`) **endurecido** conforme
[ADR 1.4.0001](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md).

### Estratégia
**Inside-out adaptado** (skill `task-ordering-hex`). O caso normal é
domínio → port → fake → adapter; aqui o domínio (os VOs) **consome** o port
`Hasher` por injeção na factory (duck-typing do `Protocol`, sem import do
port no domínio — pureza preservada). Logo a ordem é:

1. **Port primeiro** (Task 01): `Hasher` Protocol existe antes de qualquer
   VO que o tipa estruturalmente na factory.
2. **Fake + contrato canônico de referência** (Task 02): `FakeHasher`
   in-memory determinístico, para que os VOs sejam testáveis sem o adapter
   real. (Não cria adapter real aqui — regra "fake antes do real".)
3. **VOs de domínio** (Tasks 03–05), do mais simples ao mais complexo,
   cada um com unit test contra o `FakeHasher`: ConfigSignature +
   SplitFingerprint (Task 03), DatasetFingerprint com a lógica de
   float/NaN/inf (Task 04), RunId com os 9 campos e `None -> null`
   (Task 05).
4. **Adapter real + contract test** (Tasks 06–07): `CanonicalJsonHasher`
   (Task 06) e o contract test parametrizado sobre `[FakeHasher,
   CanonicalJsonHasher]` provando paridade (Task 07). O adapter real vem
   **depois** do fake (regra do skill); o contract test é a última peça
   porque exige ambas as implementações existindo.
5. **Fitness arquitetural** (Task 08): rodar `make check` completo,
   confirmar que a subárvore nova `shared/adapters/out/hashing` é coberta
   pelos contratos import-linter (camada `(adapters)` opcional do container
   `shared`) e ajustar `.importlinter` **somente** se algum contrato não
   cobrir; fechar cobertura ≥ 90% nos módulos novos.

Cada Task deixa o build verde: após Task 05 já existem 4 VOs testados com o
fake (sem adapter real); reverter Task 07 não derruba o domínio.

> **Nota de ordenação (desvio declarado vs. default do skill):** o port
> (`application`) vem **antes** do domínio porque o domínio depende do port
> por injeção, e não o contrário — a factory dos VOs tipa o parâmetro
> `hasher: Hasher` estruturalmente. Não há violação de pureza: o domínio
> não importa o port (Protocol é satisfeito por duck-typing); o type hint
> usa `typing.TYPE_CHECKING` se necessário para evitar import em runtime.

### Pré-condições
- Stage `1.3-architecture-contracts` em `done`: contratos import-linter
  (`hexagonal-layers`, `domain-purity`, `inward-only`, `shared-no-features`)
  ativos e verdes no branch.
- [ADR 1.4.0001](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md)
  em `status: accepted` (fixa `round(x, 10)`, strip de chaves voláteis,
  rejeição de NaN/±inf). **Já existe no repo.**
- Branch `feat/11-1-4-identity-and-fingerprints` em checkout.

### Premissas técnicas
- Python 3.12, `uv`, `ruff`, `mypy --strict`, `pytest`. `pyproject.toml` e
  `.importlinter` já existem.
- Domínio stdlib-only: apenas `json`, `hashlib`, `math`, `dataclasses`,
  `typing`, `collections.abc`. **Sem** pandas/pyarrow/torch/numpy/pydantic/
  sqlalchemy/fastapi (gate `domain-purity`).
- O chamador entrega datas **já formatadas como string ISO8601** e o
  `parquet_file_hash` **já calculado** — nenhum I/O nesta Stage.
- A camada `(adapters)` é opcional no container `shared` do `.importlinter`
  (`exhaustive = False`), portanto criar `shared/adapters/out/hashing/` não
  exige editar `.importlinter` — confirmar em Task 08, não assumir.

### Estrutura de pastas afetada

```
src/financial_forecasting/shared/
├── application/ports/out/
│   └── hasher.py                          # Task 01 (port Hasher)
├── domain/value_objects/
│   ├── config_signature.py                # Task 03
│   ├── split_fingerprint.py               # Task 03
│   ├── dataset_fingerprint.py             # Task 04
│   └── run_id.py                          # Task 05
└── adapters/                              # subárvore NOVA (criada nesta Stage)
    └── out/hashing/
        ├── __init__.py
        └── canonical_json_hasher.py       # Task 06

tests/
├── fakes/shared/
│   └── in_memory_hasher.py                # Task 02 (FakeHasher)
├── unit/shared/domain/value_objects/
│   ├── test_config_signature.py           # Task 03
│   ├── test_split_fingerprint.py          # Task 03
│   ├── test_dataset_fingerprint.py        # Task 04
│   └── test_run_id.py                     # Task 05
└── contract/shared/
    └── test_hasher_contract.py            # Task 07 (parametrizado fake↔real)
```

## 2. Tasks

### Task 01 — Port-out `Hasher` (Protocol)

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/application/ports/out/hasher.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar o `Protocol` `Hasher` com dois métodos semânticos:
  `hash_mapping(self, payload: Mapping[str, object]) -> str` e
  `hash_text(self, text: str) -> str`. Docstring de módulo + de classe +
  de cada método em PT, no padrão de `clock.py`/`id_generator.py`
  (explicar a semântica canônica garantida: `sort_keys`, floats
  canonicalizados de forma estável, NaN/±inf rejeitados com `ValueError`,
  `None -> null`; ordem de chaves irrelevante; `hash_text` é sensível à
  ordem). **Apenas a interface** — sem implementação, sem adapter.
- **Detalhes técnicos:**
  - `from collections.abc import Mapping`, `from typing import Protocol`.
  - Sem dependências externas (vive em `application`, mas não importa nada
    de `adapters`/`infrastructure` — contrato `inward-only`).
  - Assinatura exata em concept §4 ("Introduzidos / `Hasher`").
- **Critério de aceite:**
  - `Hasher` é `Protocol` com `hash_mapping` e `hash_text`; docstrings PT
    presentes; mypy strict verde.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/shared/application/ports/out/hasher.py
  uv run ruff check src/financial_forecasting/shared/application/ports/out/hasher.py
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(shared-hasher): port Hasher de hashing canônico [1.4/task-01]`

---

### Task 02 — `FakeHasher` in-memory (fake do port)

- **Arquivos a criar:**
  - `tests/fakes/shared/__init__.py`
  - `tests/fakes/shared/in_memory_hasher.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar `FakeHasher`, implementação in-memory **determinística** do
  `Hasher`, que aplica a **mesma semântica canônica** do adapter real
  (sort_keys, `round(float, 10)`, rejeição de NaN/±inf, `None -> null`,
  `'|'`-free `hash_text`) usando `json`/`hashlib` stdlib. O fake NÃO é um
  mock: produz hashes reais e estáveis, idênticos em comportamento ao real
  (paridade I11). Pode compartilhar a lógica de canonicalização que o
  adapter usará — mas como o adapter ainda não existe, o fake encapsula sua
  própria cópia mínima da regra (a duplicação é resolvida no contract test
  da Task 07, que prova que ambos coincidem).
- **Detalhes técnicos:**
  - Implementa `hash_mapping(Mapping[str, object]) -> str` e
    `hash_text(str) -> str`.
  - Canonicalização: percorrer o mapping recursivamente, arredondar floats
    com `round(x, 10)`, `raise ValueError` em `math.isnan`/`math.isinf`,
    `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`,
    `sha256(text.encode("utf-8")).hexdigest()`.
  - `bool` NÃO é arredondado (é subtipo de `int`; tratar antes de `float`).
- **Critério de aceite:**
  - `FakeHasher` satisfaz estruturalmente o `Hasher` (mypy strict aceita
    `hasher: Hasher = FakeHasher()`); produz hash estável para o mesmo
    input; levanta `ValueError` em NaN/inf.
- **Comando de verificação:**
  ```bash
  uv run mypy --strict tests/fakes/shared/in_memory_hasher.py
  uv run ruff check tests/fakes/shared/in_memory_hasher.py
  ```
- **Commit sugerido:** `test(shared-hasher): FakeHasher in-memory determinístico [1.4/task-02]`

---

### Task 03 — VOs `ConfigSignature` + `SplitFingerprint`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/value_objects/config_signature.py`
  - `src/financial_forecasting/shared/domain/value_objects/split_fingerprint.py`
  - `tests/unit/shared/domain/value_objects/test_config_signature.py`
  - `tests/unit/shared/domain/value_objects/test_split_fingerprint.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar os dois VOs frozen mais simples, cada um `@dataclass(frozen=True)`
  com um único campo `value: str` (hex) e uma classmethod
  `compute(*, hasher: Hasher, ...) -> Self`.
  - `ConfigSignature.compute(*, hasher, config: Mapping[str, object])`:
    copiar o dict, **remover** as chaves voláteis
    `("created_at", "started_at", "ended_at", "timestamp")`, delegar a
    `hasher.hash_mapping(cleaned)`.
  - `SplitFingerprint.compute(*, hasher, train, val, test: Sequence[str])`:
    montar `{"train": sorted(train), "val": sorted(val), "test":
    sorted(test)}` e delegar a `hasher.hash_mapping(...)`.
- **Detalhes técnicos:**
  - O type hint `hasher: Hasher` usa `TYPE_CHECKING` (import do port só sob
    `typing.TYPE_CHECKING`) para **não** importar `application` em runtime
    no domínio — preserva pureza e direção inward-only.
  - stdlib-only; sem pandas/numpy. Tipos: `Mapping`/`Sequence` de
    `collections.abc`.
  - Testes contra `FakeHasher`: I1 (determinismo), I2 (ordem de chaves
    irrelevante no config), I5 (variar `created_at` não muda assinatura),
    I6 (split order-invariant por split; trocar ordem dentro de `train`
    não muda, trocar conteúdo muda), I9 (frozen → `FrozenInstanceError`).
- **Critério de aceite:**
  - Critérios A2 e A3 do concept cobertos por teste; ambos VOs frozen,
    stdlib-only; mypy strict + `check_layout.py` + `domain-purity` verdes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/domain/value_objects/test_config_signature.py tests/unit/shared/domain/value_objects/test_split_fingerprint.py -v
  uv run mypy --strict src/financial_forecasting/shared/domain/value_objects/config_signature.py src/financial_forecasting/shared/domain/value_objects/split_fingerprint.py
  uv run lint-imports
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(shared-identity): VOs ConfigSignature e SplitFingerprint [1.4/task-03]`

---

### Task 04 — VO `DatasetFingerprint` (float/NaN/inf)

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/value_objects/dataset_fingerprint.py`
  - `tests/unit/shared/domain/value_objects/test_dataset_fingerprint.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar `DatasetFingerprint` frozen (`value: str`) com
  `compute(*, hasher, asset: str, timestamp_min: str, timestamp_max: str,
  row_count: int, close_sum: float, volume_sum: float, parquet_file_hash:
  str) -> Self`. Montar o payload estruturado (concept §4 / old
  `analytics_store_schema.py:68-76`): `{asset, timestamp_min, timestamp_max,
  row_count: int, close_sum: float, volume_sum: float, parquet_file_hash}` e
  delegar a `hasher.hash_mapping(payload)`. A canonicalização/rejeição de
  floats acontece **dentro do hasher** (não duplicar no VO) — o VO apenas
  monta o payload com os floats crus e confia no contrato do port (que
  arredonda e rejeita NaN/inf).
- **Detalhes técnicos:**
  - `int(row_count)` / `float(close_sum)` / `float(volume_sum)` para
    normalizar o tipo de entrada (espelha o old), mas a regra de
    arredondamento/NaN é do hasher (D2/D3, ADR 1.4.0001).
  - Adotar **somente** o esquema estruturado; descartar o esquema ad-hoc
    `'|'.join` do old (`run_baselines_use_case.py:365-389`) — concept D4,
    registrar como `[finding]` em §7 se reaparecer.
  - Testes contra `FakeHasher`: A4 — mesmo valor matemático de
    `close_sum`/`volume_sum` → mesmo hash (ex.: `100.0` vs `100.00000000001`
    arredondados a 10 casas; e diferença real muda o hash); C1 — `NaN` em
    `close_sum`/`volume_sum` → `ValueError`; C2 — `+inf`/`-inf` →
    `ValueError`; I1/I9.
- **Critério de aceite:**
  - A4 + C1 + C2 cobertos; VO frozen, stdlib-only; mypy strict +
    `domain-purity` verdes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/domain/value_objects/test_dataset_fingerprint.py -v
  uv run mypy --strict src/financial_forecasting/shared/domain/value_objects/dataset_fingerprint.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(shared-identity): VO DatasetFingerprint com floats canônicos [1.4/task-04]`

---

### Task 05 — VO `RunId` (9 campos, None→null)

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/domain/value_objects/run_id.py`
  - `tests/unit/shared/domain/value_objects/test_run_id.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar `RunId` frozen (`value: str`) com `compute(*, hasher, asset: str,
  feature_set_hash: str, trial_number: int | None, fold: str | None,
  seed: int | None, model_version: str, config_signature: str,
  split_signature: str, pipeline_version: str) -> Self`. Montar o payload de
  9 campos (concept §4 / old `analytics_store_schema.py:101-124`) e delegar
  a `hasher.hash_mapping(payload)`. Os opcionais
  `trial_number/fold/seed` entram **explicitamente** no payload (`None ->
  null` via `json.dumps`), nunca omitidos (I7).
- **Detalhes técnicos:**
  - `feature_set_hash` chega como string já calculada (via
    `hasher.hash_text("|".join(features_ordered))` no chamador — concept
    D5; não criar VO para ele).
  - Testes contra `FakeHasher`: A1 — determinismo + sensibilidade a **cada
    um** dos 9 campos (variar 1 campo por vez muda o hash; inclusive
    `None -> valor` em `trial_number/fold/seed`); I7 — `None` participa da
    chave (dois runs idênticos exceto `seed=None` vs `seed=0` diferem);
    I9 frozen.
- **Critério de aceite:**
  - A1 + I7 cobertos com teste parametrizado sobre os 9 campos; VO frozen,
    stdlib-only; mypy strict + `domain-purity` verdes.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/unit/shared/domain/value_objects/test_run_id.py -v
  uv run mypy --strict src/financial_forecasting/shared/domain/value_objects/run_id.py
  uv run lint-imports
  ```
- **Commit sugerido:** `feat(shared-identity): VO RunId com identidade de 9 campos [1.4/task-05]`

---

### Task 06 — Adapter `CanonicalJsonHasher`

- **Arquivos a criar:**
  - `src/financial_forecasting/shared/adapters/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/hashing/__init__.py`
  - `src/financial_forecasting/shared/adapters/out/hashing/canonical_json_hasher.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar a subárvore `shared/adapters/` (não existe hoje) e implementar
  `CanonicalJsonHasher` satisfazendo `Hasher`. `hash_mapping`: canonicalizar
  recursivamente o payload (arredondar floats com `round(x, 10)`, rejeitar
  NaN/±inf com `ValueError`, `bool` antes de `float`), serializar com
  `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`,
  retornar `sha256(text.encode("utf-8")).hexdigest()`. `hash_text`:
  `sha256(text.encode("utf-8")).hexdigest()` direto (sensível à ordem).
  A precisão `10` é uma **constante de módulo documentada**
  (`_FLOAT_PRECISION = 10`), conforme ADR 1.4.0001.
- **Detalhes técnicos:**
  - Pode importar o `Hasher` Protocol para conformidade explícita, mas como
    `Protocol` a herança é opcional; preferir conformidade estrutural +
    type hint. Adapter pode importar de `application`/`domain` (direção
    inward-only permite adapters → application/domain).
  - `allow_nan=False` em `json.dumps` é uma defesa-em-profundidade
    adicional (levanta `ValueError` se algum NaN/inf escapar do guard),
    conforme ADR 1.4.0001 "belt-and-suspenders".
  - NÃO incluir `_sha256_file`/leitura de disco (fora de escopo — Step 4.x).
- **Critério de aceite:**
  - `CanonicalJsonHasher` satisfaz `Hasher` (mypy strict); precisão `10`
    documentada; ruff + `check_layout.py` + import-linter verdes (a camada
    `(adapters)` do container `shared` cobre a subárvore nova).
- **Comando de verificação:**
  ```bash
  uv run mypy --strict src/financial_forecasting/shared/adapters/out/hashing/canonical_json_hasher.py
  uv run ruff check src/financial_forecasting/shared/adapters/out/hashing/
  uv run lint-imports
  uv run python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(shared-hashing): adapter CanonicalJsonHasher [1.4/task-06]`

---

### Task 07 — Contract test parametrizado fake↔real

- **Arquivos a criar:**
  - `tests/contract/shared/__init__.py`
  - `tests/contract/shared/test_hasher_contract.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Escrever **um** contract test parametrizado sobre
  `[FakeHasher(), CanonicalJsonHasher()]` (fixture `params`) que prova o
  **mesmo** contrato para ambos (I11 paridade): I1 determinismo (mesmo
  input → mesmo hash, em duas chamadas); I2 ordem de chaves irrelevante
  (dois dicts com mesma chave/valor em ordem de inserção diferente →
  mesmo hash); `None -> null` (chave com `None` participa e difere de chave
  ausente); I3 floats canonicalizados (`round(x,10)`-equivalentes →
  mesmo hash; diferença real → hash diferente); I4 NaN/±inf → `ValueError`;
  `hash_text` determinístico e sensível à ordem (`"a|b" != "b|a"`).
  **Reforço de paridade:** para uma bateria de payloads canônicos fixos,
  `fake.hash_mapping(p) == real.hash_mapping(p)` e
  `fake.hash_text(t) == real.hash_text(t)` (provam que fake e real produzem
  o MESMO hash, não só o mesmo comportamento) — resolve a duplicação da
  Task 02.
- **Detalhes técnicos:**
  - `@pytest.fixture(params=[FakeHasher(), CanonicalJsonHasher()])` ou lista
    de instâncias parametrizada via `pytest.mark.parametrize`.
  - O teste é a fonte única que garante I11; se fake e real divergirem, o
    teste de igualdade cruzada falha.
- **Critério de aceite:**
  - A8 coberto: o contract test passa **idêntico** para ambos os hashers,
    incluindo igualdade cruzada fake==real sobre payloads fixos.
- **Comando de verificação:**
  ```bash
  uv run pytest tests/contract/shared/test_hasher_contract.py -v
  uv run mypy --strict tests/contract/shared/test_hasher_contract.py
  ```
- **Commit sugerido:** `test(shared-hashing): contract test paridade FakeHasher↔CanonicalJsonHasher [1.4/task-07]`

---

### Task 08 — Fitness arquitetural + cobertura ≥ 90%

- **Arquivos a criar:** nenhum (a menos que `.importlinter` precise de
  ajuste — só se algum contrato não cobrir a subárvore nova)
- **Arquivos a modificar:**
  - `.importlinter` (somente se necessário — ver abaixo)
  - `pyproject.toml` (somente se a config de coverage precisar garantir
    que os módulos novos **não** estão em `omit`)
- **O que fazer:**
  Rodar a fitness function completa e fechar a Stage tecnicamente
  (sem o commit de fechamento, que é do orquestrador). (1) Rodar
  `make check` e `make test`; confirmar que `domain-purity` ainda reprova
  os 4 VOs caso importem lib proibida (já garantido pelo gate da 1.3).
  (2) Confirmar que a subárvore `shared/adapters/out/hashing` é coberta
  pelos contratos `hexagonal-layers`/`inward-only` — a camada `(adapters)`
  é opcional no container `shared` (`exhaustive = False`), então **espera-se
  que nenhuma edição em `.importlinter` seja necessária**; se um contrato
  novo não cobrir, ajustar `.importlinter` espelhando `LAYOUT.md` e
  registrar `[decision]` em §7. (3) Verificar cobertura ≥ 90% nos módulos
  novos (`shared/application/ports/out/hasher.py`,
  os 4 VOs, `canonical_json_hasher.py`) — eles **não** entram em
  `coverage omit` (I12).
- **Detalhes técnicos:**
  - Se `make check` já cobre tudo e a cobertura ≥ 90% sem editar arquivos,
    esta Task pode não ter mudança de código — nesse caso é uma Task de
    **verificação** e o commit é dispensável (registrar em §7 que o gate
    fechou sem edição). Se houver edição (`.importlinter`/`pyproject.toml`),
    commitar.
- **Critério de aceite:**
  - A9 + A10 cobertos: `make check` (ruff + mypy strict + import-linter +
    `check_layout.py`) e `make test` verdes; cobertura ≥ 90% nos módulos
    novos sem `omit`.
- **Comando de verificação:**
  ```bash
  make check
  make test
  uv run pytest --cov=financial_forecasting.shared.adapters.out.hashing \
    --cov=financial_forecasting.shared.domain.value_objects \
    --cov-report=term-missing tests/
  ```
- **Commit sugerido (se houve edição):** `chore(shared-arch): cobrir hashing nos contratos de fitness [1.4/task-08]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 1.4: complete` (aplicado pelo **orquestrador**, após auditoria
> independente — não pelo executor).

### Verificações automatizadas
```bash
make check                # ruff + mypy strict + import-linter + check_layout
make test                 # todos os testes
uv run pytest tests/contract/shared/test_hasher_contract.py -v   # paridade fake↔real
uv run pytest --cov=financial_forecasting.shared --cov-report=term-missing tests/
```

### Verificações funcionais
- [ ] `RunId.compute`, `DatasetFingerprint.compute`, `ConfigSignature.compute`
      e `SplitFingerprint.compute` produzem hex strings determinísticas com
      `CanonicalJsonHasher` real.
- [ ] O contract test passa idêntico para `FakeHasher` e `CanonicalJsonHasher`,
      incluindo igualdade cruzada fake==real.
- [ ] `DatasetFingerprint.compute(..., close_sum=float("nan"))` levanta
      `ValueError`.

### Tabela invariante ↔ teste

| Invariante (concept §5) | Critério (concept §11) | Teste / arquivo |
|---|---|---|
| I1 Determinismo | A1, A5 | `test_run_id.py`, `test_hasher_contract.py` |
| I2 Ordem de chaves irrelevante | A5 | `test_config_signature.py`, `test_hasher_contract.py` |
| I3 Floats canonicalizados | A4, A7 | `test_dataset_fingerprint.py`, `test_hasher_contract.py` |
| I4 NaN/±inf rejeitados | A4, A7, A8 | `test_dataset_fingerprint.py` (C1/C2), `test_hasher_contract.py` |
| I5 ConfigSignature ignora voláteis | A2 | `test_config_signature.py` |
| I6 SplitFingerprint order-invariant por split | A3 | `test_split_fingerprint.py` |
| I7 None → null (participa da chave) | A1 | `test_run_id.py` |
| I8 Datas como string ISO | — (contrato do chamador) | type hint `str` + mypy strict |
| I9 VOs frozen | A9 | testes de cada VO (`FrozenInstanceError`) |
| I10 Domínio stdlib-only | A9 | `lint-imports` (`domain-purity`), `tests/architecture/` |
| I11 Paridade fake↔real | A8 | `test_hasher_contract.py` (parametrizado + igualdade cruzada) |
| I12 Código vivo coberto ≥ 90% | A10 | `pytest --cov`, sem `omit` |

### Checklist de fechamento da Stage (executor)
- [ ] Tasks 01–08 commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] `make test` verde; cobertura ≥ 90% nos módulos novos (sem `omit`)
- [ ] Contract test fake↔real verde (paridade)
- [ ] ADR `1_4_0001` em `status: accepted` (já está)
- [ ] §7 Execução preenchida com `[decision]`/`[finding]`/`[deviation]`
      surgidos na execução
- [ ] `concept.md` não precisa de retoque retrospectivo material

> **NÃO faz parte do escopo do executor:** o commit `stage 1.4: complete`
> e marcar a Stage `done` em `roadmap.md` — feitos pelo orquestrador.

## 4. Ordem de dependência entre Tasks

```
Task 01 (port Hasher)
   └─► Task 02 (FakeHasher)
          ├─► Task 03 (ConfigSignature + SplitFingerprint)
          ├─► Task 04 (DatasetFingerprint)
          └─► Task 05 (RunId)
   └─► Task 06 (CanonicalJsonHasher real)
          └─► Task 07 (contract test fake↔real)   [precisa de 02 e 06]
                 └─► Task 08 (fitness + cobertura) [precisa de tudo]
```

Tasks 03/04/05 são independentes entre si (todas dependem só de 01+02) e
podem ser feitas em qualquer ordem; listadas do mais simples ao mais
complexo. Task 06 depende só de 01. Task 07 depende de 02 **e** 06. Task 08
fecha sobre tudo.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Type hint `hasher: Hasher` no domínio força import de `application` em runtime (viola inward-only) | Usar `from __future__ import annotations` + import do port sob `if TYPE_CHECKING:`; o Protocol é satisfeito por duck-typing, sem import runtime. |
| Subárvore `shared/adapters/out/hashing` não coberta por contrato import-linter | Confirmar em Task 08; se faltar, adicionar/ajustar contrato em `.importlinter` espelhando `LAYOUT.md` e registrar `[decision]`. (Esperado: camada `(adapters)` opcional já cobre.) |
| `bool` arredondado como `float` quebra payload (Python `bool ⊂ int`) | Checar `isinstance(x, bool)` **antes** de `isinstance(x, float)`/`Real` na canonicalização (fake e adapter). |
| Fake e real divergem (duplicação da regra de canonicalização) | Task 07 prova igualdade cruzada `fake.hash_mapping(p) == real.hash_mapping(p)`; se divergir, alinhar a regra (constante de precisão única documentada no ADR). |
| `json.dumps` default emite `NaN`/`Infinity` (JSON inválido) | Guard explícito `math.isnan`/`math.isinf` → `ValueError` **antes** do dump + `allow_nan=False` como defesa-em-profundidade (ADR 1.4.0001). |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md) — §3/§4 rastreabilidade, ASSUM-4
- [`../../roadmap.md`](../../roadmap.md) — Stage 1.4 (1.5 consome `Hasher`; 4.1 consome os VOs)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- [`../../LAYOUT.md`](../../LAYOUT.md) — §3/§6 regras de import/camadas
- [ADR 1.4.0001](../../adr/1_4_0001-canonicalizacao-de-hash-deterministico.md) — canonicalização de hash determinístico
- ADRs de fundação: [`0_0_0019`](../../adr/0_0_0019-hexagonal-enforced.md),
  [`1_3_0001`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md)
- Skills aplicáveis: `task-ordering-hex`, `pytest-with-fakes`,
  `ddd-tactical-patterns`, `hex-arch-python`
- Repo antigo (contrato a replicar com julgamento):
  `/home/marcelo/Code/financial-time-series-forecasting/src/infrastructure/schemas/analytics_store_schema.py`
  (`_canonical_json`:17-18; `compute_config_signature`:37-41;
  `compute_split_fingerprint`:44-55; `compute_dataset_fingerprint`:58-77;
  `compute_run_id`:101-124)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.

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
- `[finding]` — gap/observação a tratar em **próxima Stage**.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

<!-- END: post-execution -->