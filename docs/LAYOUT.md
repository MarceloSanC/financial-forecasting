# LAYOUT.md — Convenções de Arquitetura

Este documento é a fonte da verdade sobre como o código está organizado e quais regras de
dependência devem ser seguidas. **Leia antes de criar qualquer arquivo.**

---

## 1. Visão Geral

A arquitetura combina dois padrões complementares:

**Vertical Slices (Feature-based):** cada funcionalidade de negócio vive em seu próprio
diretório (`features/<feature>/`), contendo todas as camadas necessárias — desde a entidade
de domínio até o controller HTTP. Isso maximiza a coesão: tudo relacionado a um bounded
context fica em `features/<feature>/`.

**Ports & Adapters (Hexagonal) dentro de cada slice:** o interior de cada feature é dividido
em camadas com regras rígidas de dependência. O domínio não sabe nada sobre o mundo externo;
a aplicação orquestra via interfaces (ports); os adapters conectam ao mundo real.

**Shared (Preocupações Transversais):** código genuinamente reutilizável entre features fica
em `shared/`. Tudo que é específico de uma feature fica na feature.

---

## 2. Estrutura de Pastas

```
src/financial_forecasting/
├── main.py                         # Entrypoint ASGI
├── cli.py                          # Entrypoint de linha de comando (runner do cohort, 5.5):
│                                   #   monta Settings, chama wire_dependencies e despacha
│                                   #   para adapters/in/cli via importlib (§8)
├── composition_root.py             # Única wiring point — instancia dependências concretas
│
├── features/                       # Um diretório por bounded context / vertical slice
│   └── <feature>/                  # Placeholder: cada feature do seu projeto
│       ├── domain/                 # Núcleo — zero dependências externas
│       │   ├── entities/           # Objetos com identidade
│       │   ├── value_objects/      # Objetos imutáveis sem identidade
│       │   ├── services/           # Serviços de domínio (lógica que não cabe em entidade)
│       │   └── exceptions/         # Exceções de domínio
│       │
│       ├── application/            # Orquestração — depende apenas de domain + ports
│       │   ├── use_cases/          # Um arquivo por use case (create_order.py, cancel_order.py)
│       │   ├── dtos/               # Objetos de transferência (commands, queries, results)
│       │   └── ports/              # Interfaces (Protocols Python)
│       │       ├── in/             # Ports primários / driving (atenção: 'in' é keyword Python)
│       │       └── out/            # Ports secundários / driven
│       │
│       └── adapters/               # Implementações concretas dos ports
│           ├── in/                 # Adapters primários (HTTP, CLI, workers)
│           │   └── http/           # Router FastAPI, schemas Pydantic de request/response
│           └── out/                # Adapters secundários (banco, email, APIs externas)
│               └── postgres/       # Repositório SQLAlchemy, mappers
│
└── shared/                         # Código transversal — usado por múltiplas features
    ├── domain/                     # Exceções base, value objects genéricos (Pagination)
    ├── application/                # Ports compartilhados (Clock, Hasher, calendário…)
    └── infrastructure/             # Implementações de infraestrutura
        ├── config/                 # Settings (pydantic-settings)
        ├── database/               # Engine SQLAlchemy, sessões
        ├── http/                   # FastAPI app factory, middlewares, error handlers
        ├── logging/                # Configuração de logging estruturado
        └── clock/                  # SystemClock (implementa shared Clock port)

tests/
├── unit/                           # Testes sem I/O — rápidos, sem fixtures de banco
│   └── features/<feature>/
│       ├── domain/                 # Testam entidades, value objects, serviços
│       └── application/            # Testam use cases com fakes
├── integration/                    # Testam adapters reais contra banco/serviços
│   └── features/<feature>/adapters/out/postgres/
├── contract/                       # Validam que fake e implementação real respeitam o contrato
│   └── features/<feature>/
├── e2e/                            # Sobem a app completa via HTTP
│   └── features/<feature>/
├── fakes/                          # Implementações fake dos ports para uso em testes
│   └── features/<feature>/
│       └── in_memory_<entity>_repository.py
├── fixtures/                       # Dados de teste versionados (lidos só por integration)
│   ├── r_oracle/                   # Oráculo R: <unidade>.{json,R,sessionInfo.txt} + Dockerfile (ADR 6.2.0006)
│   └── nexcp_oracle/               # Oráculo NexCP: gerador + JSON do `splitCP_LS` dos autores (ADR 7.2.0002)
└── architecture/                   # Testes dos próprios gates (import-linter, layout, fake-parity, port-coverage, arch-ast)

migrations/
├── alembic.ini
├── env.py
└── versions/                       # Arquivos gerados pelo alembic revision
```

---

## 3. Camadas e Regras de Dependência

A regra fundamental: **as dependências apontam para dentro** (em direção ao domínio),
nunca para fora.

```
adapters  →  application  →  domain
               ↑
           shared/application/ports
               ↑
           shared/infrastructure  (apenas via composition_root)
```

### Domain

- **Pode importar de:** apenas stdlib Python e outros módulos dentro de `domain/`
- **Nunca pode importar de:** `application/`, `adapters/`, `shared/infrastructure/`, FastAPI, SQLAlchemy
- **Contém:** entidades, value objects, serviços de domínio, exceções de domínio

### Application

- **Pode importar de:** `domain/`, `shared/domain/`, `shared/application/ports/`
- **Nunca pode importar de:** `adapters/`, `shared/infrastructure/`
- **Contém:** use cases, DTOs (commands, queries, results), ports (Protocols)

### Adapters

- **Pode importar de:** `application/` (ports e DTOs), `domain/` (entidades para mappers)
- **Nunca pode importar de:** outros adapters da mesma feature (exceto via port)
- **Contém:** implementações concretas dos ports (repositórios, controllers HTTP)

### Shared

- `shared/domain/` — mesmas regras de `domain/`
- `shared/application/` — mesmas regras de `application/`
- `shared/infrastructure/` — pode usar qualquer lib externa; é instanciado no composition_root

> **Trocar uma dependência operacional** (provedor LLM, banco, scheduler)
> sem quebrar o port nem perder o rastro de decisão: ver
> [`operational-evolution-policy.md`](./operational-evolution-policy.md)
> (3 invariantes de neutralidade do port + ADR antigo com `superseded_by`).

---

## 4. Features vs Shared

O critério é **quem é dono** do tipo ou da regra, não quantas features o consomem.

**Coloque em `features/<nome>/`** quando:
- A lógica é específica de um slice (ex: indicadores técnicos, treino do TFT)
- O slice **produz** o tipo e mantém as suas invariantes — mesmo que outros slices o
  consumam (ex: `Candle` é de `market_data`, `QuantileForecast` é de `analytics_store`).
  O consumidor importa o tipo como **aresta de dados declarada** no contrato
  `bc-independence`; comportamento entra por port do consumidor (§7, ADR 0.0.0053)
- O port é consumido apenas por aquela feature

**Coloque em `shared/`** quando **não há slice dono**:
- Infraestrutura cross-cutting (ex: configuração, logging, `Clock`, `Hasher`, factory do FastAPI)
- Conceito transversal que nenhum slice produz (ex: `TradingSessions`/calendário de pregão,
  ADR 2.4.0001; identidade de run `RunId`/fingerprints, ADR 5.2.0004)
- Abstração de domínio agnóstica (ex: `DomainError`, `NotFoundError`, `Pagination`)

**Por que não "2+ consumidores → shared":** mover um tipo com dono para `shared/` separa-o
das invariantes e das decisões do slice que o produz (o módulo se organiza pela decisão de
projeto que esconde — Parnas 1972, p.1056, doi:10.1145/361598.361623) e transforma
`shared/` num pacote de tipos de negócio sem dono. O que vai para módulo à parte é o
genérico, "sem traço das especialidades" do domínio (Evans, *DDD Reference* 2015,
GENERIC SUBDOMAINS, p.41). Shared Kernel não se aplica entre slices de um mesmo
contexto (ADR 0.0.0053).

**Regra prática:** em caso de dúvida, comece na feature. Um segundo consumidor não é motivo
para mover: é uma aresta de dados a declarar.

---

## 5. Portas (Ports)

Ports são interfaces Python (`Protocol`) que definem contratos entre camadas.

### Ports Primários / Driving (`ports/in/`)

São acionados por atores externos (HTTP, CLI, mensageria). Definem o que a aplicação
**aceita** como entrada. O adapter `in` (ex: router FastAPI) chama o use case via este port.

Exemplo: `Create<Entity>Port` — contrato que o controller HTTP usa para chamar o use case.

### Ports Secundários / Driven (`ports/out/`)

São implementados por adapters externos. Definem o que a aplicação **precisa** do mundo
externo. O use case depende da interface, não da implementação concreta.

Exemplo: `<Entity>Repository` — contrato que o use case usa para persistir uma entidade.

### Nota sobre o diretório `in`

`in` é uma palavra reservada do Python e **não pode ser usado diretamente em imports**:

```python
# ERRO — 'in' é keyword Python
from financial_forecasting.features.<feature>.application.ports.in.<port_module> import <PortClass>
```

**Workarounds disponíveis:**

```python
# Opção 1 — importlib (mais explícito)
import importlib
port_module = importlib.import_module(
    "financial_forecasting.features.<feature>.application.ports.in.<port_module>"
)
PortClass = port_module.<PortClass>

# Opção 2 — injete o use case diretamente via FastAPI Depends (recomendado)
# O router recebe o use case já instanciado pelo composition_root,
# sem nunca precisar importar o módulo 'in' diretamente.

# Opção 3 — alias no __init__.py do pacote pai (ports/__init__.py)
# Re-exporte o Protocol de lá:
# from financial_forecasting.features.<feature>.application.ports.in.<port_module> import <PortClass>
# Isso funciona porque __init__.py não usa a palavra 'in' como identificador Python.
```

A abordagem recomendada é a **Opção 2**: o composition_root instancia o use case e o injeta
via `Depends`, eliminando a necessidade de importar o módulo `in` fora do próprio pacote.

---

## 6. Composition Root

`composition_root.py` é o **único ponto de wiring** da aplicação. Ele:

1. Lê a configuração via `Settings`
2. Instancia dependências de infraestrutura (engine, clock, id generator)
3. Instancia repositórios concretos (ex: `PostgresPaymentRepository`)
4. Injeta tudo nos use cases
5. Expõe os use cases montados para o restante da aplicação

**Por que isso importa:**
- Mantém o domínio e a application totalmente desacoplados de implementações concretas
- Facilita trocar uma implementação (ex: Postgres → DynamoDB) sem tocar em nenhuma regra de negócio
- Torna o grafo de dependências explícito e auditável em um único arquivo

```python
# composition_root.py — exemplo de uso
deps = wire_dependencies()
app.dependency_overrides[get_create_order_use_case] = lambda: deps.create_order
```

**Fronteira aceita — `shared/infrastructure` ↔ `composition_root`.** O arquivo
`shared/infrastructure/http/app.py` (factory do FastAPI) importa
`composition_root`, que por sua vez importa adapters de features para fazer o
wiring. Isso parece quebrar a regra "shared não importa de features", mas é
exceção declarada: composition_root é o **único** ponto onde o caminho indireto
`shared → composition_root → features.adapters` é permitido. O
`scripts/check_layout.py` não detecta esse caminho indireto (limitação
documentada no script) — depende de revisão manual no gate de saída da Stage.

---

## 7. Regras de Ouro

- **Domain tem zero I/O.** Nenhuma entidade ou value object chama banco, rede ou arquivo.
  Nem lê relógio, ambiente ou acaso global: `datetime.now`, `time.time`, `uuid4`, `random.<função>`,
  `open`, `pathlib.Path` e qualquer `os.*`/`shutil.*`/`subprocess.*` reprovam sob `*/domain/`;
  tempo entra pelo port `Clock`, caminho como valor puro usa `PurePath`, e um
  gerador com semente explícita (`random.Random(seed)`) é permitido (gate:
  `scripts/check_domain_determinism.py`, issue #61).
- **Value object valida na construção.** `@dataclass(frozen=True)` em `domain/value_objects/`
  tem `__post_init__` — factory validadora não basta, o construtor da dataclass segue chamável;
  VO sem invariante por desenho declara `# vo-invariant: none — <motivo>` (gate:
  `scripts/check_vo_invariants.py`, issue #61; baseline zerado pela #160). Hash de identidade
  guardado como `str` valida a forma pela regra única `validate_sha256_hex`
  (`shared/domain/services/sha256_hex.py`).
- **Use cases retornam DTOs, não entidades.** Entidades de domínio (com identidade, mutáveis) não vazam para fora da camada application. **Value objects** imutáveis de domínio (ex: `Money`) **podem** trafegar em DTOs — são valores puros sem identidade, indistinguíveis de tipos primitivos do ponto de vista do consumidor.
- **Um use case por arquivo.** `create_order.py`, não `order_use_cases.py`.
- **Adapters implementam ports.** `PostgresPaymentRepository` satisfaz `PaymentRepository` Protocol.
  O `__init__` do use case anota o **port**, nunca a classe do adapter (nem de
  `shared/infrastructure/`) nem o use case de outro slice; serviço de domínio concreto é
  permitido (gate: `scripts/check_use_case_deps.py`, issue #61).
- **Fakes implementam os mesmos ports.** `InMemoryPaymentRepository` satisfaz `PaymentRepository` Protocol.
  Todo port-out tem fake em `tests/fakes/` **e** suíte de contrato `[fake, real]` — gate:
  `scripts/check_port_coverage.py` (issue #62; baseline em `scripts/arch_baseline.toml`). O real pode ser
  o use case de outro slice que satisfaz o port do consumidor por duck-typing (ADR 0.0.0053) — o gate
  o reconhece quando o contrato `[fake, real]` o importa (#93).
- **Testes unitários usam fakes.** Nenhum teste unitário toca banco ou rede.
- **Tests de contrato validam a equivalência.** A fake e a implementação real devem passar nos mesmos testes.
  A fake não pode **ser** a implementação: bloco de lógica idêntico ≥ 15 linhas entre `tests/fakes/**` e
  `src/**/adapters/**` reprova — a regra compartilhada sobe para `domain/services/` (gate:
  `scripts/check_fake_parity.py`, issue #62).
- **Conhecimento de schema tem dono único.** As coordenadas do dataset TFT (`"processed"`,
  `"dataset_tft"`) e a coluna-alvo (`"target_return"`) não se redeclaram como literal em
  `features/modeling/application/` (gate: `scripts/check_schema_literals.py`, issue #61;
  dívida de hoje no baseline → #159).
- **Imports sempre absolutos.** Nunca `from ..domain import` — use o caminho completo.
- **Nenhum import circular.** Se você precisar, é sinal de que a camada está errada.
- **Shared não importa de features.** O fluxo é sempre: features → shared, nunca o contrário.
- **Identidade só pelos VOs de `shared/domain/value_objects/`.** `RunId`, `ConfigSignature`,
  `SplitFingerprint`, `CohortHash` (hash do spec do cohort
  confirmatório, ADR 5.5.0001), `DatasetContentFingerprint` (conteúdo do grid de
  treino, ADR 5.5.0004), `PreregistrationHash` (hash do pré-registro
  confirmatório, floats codificados exatamente, ADR 6.5.0001) e `FamilyPartitionHash`
  (partição de famílias + `feature_set_hash` de H3, ADR 7.3.0002) são o único caminho de hash; fora deles ninguém
  chama `hasher.hash_mapping`/`hash_text` (payload hand-rolled num use case é uma segunda
  definição de "o mesmo run" — ADR 5.2.0004). Gate: regra 6 do `scripts/check_layout.py`.
- **Features não importam comportamento de outras features.** Cada slice é uma unidade
  substituível: comportamento de outro slice entra por port definido no consumidor;
  dados (DTO do port-in e tipos de domínio do slice dono) cruzam como aresta
  declarada; só o que não tem slice dono sobe para `shared/` (§4).

  **Perímetro do gate hoje** — dito aqui porque doutrina mais larga que o gate é
  falso verde de segunda ordem, o defeito que a issue #60 existe para matar: o
  contrato `bc-independence` do `.importlinter` cobre os **seis** slices
  (`modeling`, `analytics_store`, `feature_engineering`, `market_data`,
  `evaluation` — este desde a Stage 6.1 —, e `inference` — desde a Stage 7.1: seus
  ports do consumidor só têm imports de tipo; o contrato `inference-no-torch-leak`
  mantém `torch`/`lightning`/`pytorch_forecasting` fora da application/domain do
  slice, ADR 7.1.0001 item 4; desde a Stage 7.2, o `inference-no-mapie-leak` mantém
  `mapie`/`numpy`/`sklearn`/`scipy` fora dela — só o adapter
  `inference/adapters/out/mapie/` os importa, ADR 7.2.0002 item 1). As 40 arestas de runtime existentes
  estão declaradas UMA A UMA como exceção comentada (débito medido, não
  permissão) — as 8 `feature_engineering → market_data.domain.entities`
  (`Candle`, `NewsArticle`, `FundamentalReport`, #95), as seis
  `modeling.application.use_cases → feature_engineering.domain.services.dataset_tft_contract`
  (o par read-only do dataset TFT e a coluna-alvo, com dono no produtor, #159) e as duas
  `evaluation.domain → analytics_store.domain.value_objects.quantile_forecast`
  (o VO `QuantileForecast` guardado pela `coverage_series`, Stage 6.1 / ADR
  6.1.0002, e construído com os valores persistidos pelo `series_assembly`,
  Stage 6.4 / ADR 6.4.0004) e as cinco do `inference.application.use_cases.run_inference`
  (Stage 7.1: os DTOs de comando de `ResolveTftCheckpoints`/`PredictTftFromCheckpoints`,
  as chaves `CODE_KEYS`/`DIRTY_KEY`/`THREADS_KEY` do port do probe do `modeling`, o
  `PersistPredictionsCommand` e o VO `QuantileForecast`) e a do
  `evaluation.application.use_cases.refresh_gold → inference.application.use_cases.calibrate_conformal`
  (Stage 7.2: os DTOs de comando do `CalibrateConformal`, ADR 7.2.0003 item 3) e as seis do
  `inference.application.use_cases.run_permutation_inference` (Stage 7.3: os DTOs de comando de
  `ResolveTftCheckpoints`/`PredictTftAttributionFromCheckpoints` e dos escritores
  `PersistPermutedPredictions`/`PersistVsnWeights`, as chaves do port do probe e o VO
  `QuantileForecast`, ADR 7.3.0002) são dados, pela regra da ADR
  0.0.0053 — e **uma aresta nova reprova o build**. O que o gate não vê:

  - **Arestas sob `if TYPE_CHECKING:` são invisíveis ao contrato**
    (`exclude_type_checking_imports = True`, ver §3). Hoje as únicas type-only
    cross-slice são as assinaturas dos ports `PredictionPersister`/
    `RunRecordPersister` de `modeling` (anotam DTOs/VO do `analytics_store`), a
    anotação `NewsArticle` do `FinbertSentimentModel` (`feature_engineering`) e a
    anotação `TrainingGrid` (`modeling.domain`) do port `TrainingGridReader` de
    `evaluation` (Stage 6.4, ADR 6.4.0009 — o real é o use case `ReadTrainingGrid`) e
    a assinatura do port `ConformalCalibration` de `evaluation`, que anota o comando e o
    resultado do use case `CalibrateConformal` da `inference` (Stage 7.2, ADR 7.2.0003).

  **Nota de escopo (ADR 0.0.0053):** esta regra enforça direção de dependência e
  aciclicidade entre slices — NÃO afirma que cada slice é um Bounded Context
  separado no sentido de Evans (a pré-condição desse padrão é escala de time, que
  não existe neste projeto). Os slices são **módulos de um único contexto**: quando
  um slice precisa de comportamento de outro, define o **port no consumidor**
  (`<slice>/application/ports/out/`) e o fornecedor o satisfaz por duck-typing —
  sem Anticorruption Layer nem Shared Kernel; o que cruza a fronteira em runtime
  são dados (DTOs do port-in do fornecedor e VOs), declarados no contrato.

---

## 8. Nota sobre `in` como Nome de Diretório

O diretório `in/` existe para seguir a nomenclatura canônica de Ports & Adapters
(ports primários = "in", ports secundários = "out"). Ele é válido como diretório no sistema
de arquivos, mas **não pode ser referenciado diretamente em imports Python** porque `in`
é uma palavra reservada da linguagem.

Estratégia adotada neste projeto:

1. O diretório `in/` **existe** e contém os arquivos de port/adapter primários.
2. **Imports diretos** de `ports/in/` são evitados no código de produção usando injeção
   de dependência via `composition_root.py` + FastAPI `Depends`.
3. Quando um import direto for absolutamente necessário, use `importlib.import_module()`.
4. Docstrings nos arquivos dentro de `in/` incluem um aviso sobre a keyword.

Isso permite manter a estrutura semântica correta sem sacrificar a compatibilidade Python.
