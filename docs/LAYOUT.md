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
    ├── application/                # Ports compartilhados (Clock, IdGenerator)
    └── infrastructure/             # Implementações de infraestrutura
        ├── config/                 # Settings (pydantic-settings)
        ├── database/               # Engine SQLAlchemy, sessões
        ├── http/                   # FastAPI app factory, middlewares, error handlers
        ├── logging/                # Configuração de logging estruturado
        ├── clock/                  # SystemClock (implementa shared Clock port)
        └── uuid_generator/         # Uuid4Generator (implementa shared IdGenerator port)

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
└── fakes/                          # Implementações fake dos ports para uso em testes
    └── features/<feature>/
        └── in_memory_<entity>_repository.py

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

**Coloque em `features/<nome>/`** quando:
- A lógica é específica de um bounded context (ex: cálculo de desconto de pedidos)
- A entidade tem identidade própria naquele contexto (ex: `Payment`, `Customer`)
- O port é consumido apenas por aquela feature

**Coloque em `shared/`** quando:
- É genuinamente reutilizado por 2+ features (ex: `Clock`, `IdGenerator`, `Pagination`)
- É infraestrutura cross-cutting (ex: configuração, logging, factory do FastAPI)
- É uma abstração de domínio agnóstica (ex: `DomainError`, `NotFoundError`)

**Regra prática:** em caso de dúvida, comece na feature. Mova para shared apenas quando
a segunda feature precisar do mesmo código.

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
- **Use cases retornam DTOs, não entidades.** Entidades de domínio (com identidade, mutáveis) não vazam para fora da camada application. **Value objects** imutáveis de domínio (ex: `Money`) **podem** trafegar em DTOs — são valores puros sem identidade, indistinguíveis de tipos primitivos do ponto de vista do consumidor.
- **Um use case por arquivo.** `create_order.py`, não `order_use_cases.py`.
- **Adapters implementam ports.** `PostgresPaymentRepository` satisfaz `PaymentRepository` Protocol.
- **Fakes implementam os mesmos ports.** `InMemoryPaymentRepository` satisfaz `PaymentRepository` Protocol.
- **Testes unitários usam fakes.** Nenhum teste unitário toca banco ou rede.
- **Tests de contrato validam a equivalência.** A fake e a implementação real devem passar nos mesmos testes.
- **Imports sempre absolutos.** Nunca `from ..domain import` — use o caminho completo.
- **Nenhum import circular.** Se você precisar, é sinal de que a camada está errada.
- **Shared não importa de features.** O fluxo é sempre: features → shared, nunca o contrário.
- **Features não importam de outras features.** Cada slice é uma unidade
  substituível; o que precisa ser compartilhado sobe para `shared/`.

  **Perímetro do gate hoje** — dito aqui porque doutrina mais larga que o gate é
  falso verde de segunda ordem, o defeito que a issue #60 existe para matar: o
  contrato `bc-independence` do `.importlinter` cobre **apenas** `modeling`,
  `analytics_store` e `feature_engineering`. Dentro desse trio, as 11 arestas de
  runtime existentes estão declaradas UMA A UMA como exceção comentada (débito
  medido, não permissão) e **uma aresta nova reprova o build**. Fora dele, a regra
  é doutrina sem gate:

  - **`market_data` está FORA do contrato.** Não é exceção declarada — é slice
    **não coberto**: qualquer aresta envolvendo `market_data`, inclusive uma nova,
    passa verde. As 9 arestas `feature_engineering → market_data.domain.entities`
    (`Candle`, `NewsArticle`, `FundamentalReport` em assinatura de port) **não**
    estão declaradas uma a uma. Incluir `market_data` no contrato forçaria agora a
    decisão sobre essas entidades, que a issue #68 defere para ADR própria.
  - **Arestas sob `if TYPE_CHECKING:` são invisíveis ao contrato**
    (`exclude_type_checking_imports = True`, ver §3). As 3 referências
    `modeling → analytics_store.application.ports.out.analytics_repository` são
    type-only e por isso não entram na contagem de 11.

  **Nota de escopo:** esta regra enforça direção de dependência e aciclicidade
  entre slices — NÃO afirma que cada slice é um Bounded Context separado no
  sentido de Evans (a pré-condição desse padrão é escala de time, que não existe
  neste projeto).

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
