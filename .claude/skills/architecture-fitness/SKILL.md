---
name: architecture-fitness
description: "Catálogo das regras de arquitetura do projeto — para cada uma, a violação, a fonte primária (trecho literal + localizador), a camada que a enforça (gate de make check, hook de edição ou revisor) e como corrigir — mais o executor que roda os gates AST só nos arquivos alterados. Invocar ao corrigir um achado do hook arch_feedback ou de make arch-ast, antes de criar port/use case/VO/adapter, ao revisar um diff por arquitetura (o subagente architecture-reviewer a pré-carrega) e antes de propor regra nova de arquitetura (em qual camada ela mora)."
metadata:
  status: draft
  applies_when:
    camada_alvo: [any]
    stage_kind: any
    fase: [3B, 4]
    invoked_at: [stage-review, issue-review]
---

# Architecture fitness

As regras de arquitetura vivem em **uma** de três camadas (ADR 0.0.0058):

| Camada | O que é | Onde | Vale como veredito? |
|---|---|---|---|
| **Gate** | script determinístico, reprova o build | `scripts/check_*.py` + `.importlinter`, em `make check`/CI | **sim** — o único |
| **Hook** | os mesmos gates, só no arquivo editado, na hora | `.claude/hooks/arch_feedback.py` (PostToolUse `Edit\|Write`) | não — feedback |
| **Revisor** | julgamento sobre o que script não expressa | subagente `architecture-reviewer` (só leitura) | não — entrada para humano/auditoria |

Fonte das regras: `docs/LAYOUT.md` §3/§6/§7 (dono). Este catálogo não redefine regra —
liga cada uma à fonte primária e ao gate. Detalhe e exemplos ficam em `reference/`.

## Executor (gates AST só nos arquivos alterados)

```bash
python .claude/skills/architecture-fitness/scripts/check_changed.py <arquivo.py> [...]
python .claude/skills/architecture-fitness/scripts/check_changed.py     # diff vs origin/develop
```

Roda os quatro gates de `make arch-ast` importando os próprios `scripts/check_*.py` (nenhuma
regra copiada) e mostra só as chaves dos arquivos pedidos: violação fora do baseline e
entrada de baseline que deixou de ocorrer. Exit 0 = limpo, 1 = achados. Não substitui o
`make check` — import-linter, `check_layout`, `check_fake_parity` e `check_port_coverage`
ficam de fora (raciocinam sobre o grafo ou sobre pares de arquivos, não sobre um arquivo).

## Catálogo

Cada linha: violação → fonte → camada/gate → correção. Citação com "p. PDF" usa a página
do arquivo do *DDD Reference* (2015-03); a impressa é 7 a menos.

### R1. Use case depende de port, não de concreto — [reference/dependency-rule.md](reference/dependency-rule.md)

- **Violação:** `__init__` de use case anota classe de `adapters/`, de `shared/infrastructure/`
  ou use case de outro slice.
- **Fonte:** "A. HIGH LEVEL MODULES SHOULD NOT DEPEND UPON LOW LEVEL MODULES. BOTH SHOULD
  DEPEND UPON ABSTRACTIONS." — Martin, *The Dependency Inversion Principle*, C++ Report, 1996, p.6.
- **Gate:** `scripts/check_use_case_deps.py` (+ import-linter para a direção dos imports).
- **Correção:** anotar o `Protocol` do port (`<slice>/application/ports/out/`); o concreto
  entra pelo composition root.

### R2. Concreto só nasce no composition root — [reference/composition-root.md](reference/composition-root.md)

- **Violação:** adapter instanciado fora de `src/financial_forecasting/composition_root.py`; default concreto
  de infraestrutura num construtor.
- **Fonte:** "A Composition Root is a (preferably) unique location in an application where
  modules are composed together." — Seemann, *Composition Root*, blog.ploeh.dk, 2011-07-28.
- **Camada:** revisor (o gate dedicado foi cortado na #61: os proxies lazy já estão dentro do
  `composition_root.py`; ver a reference).
- **Correção:** receber o colaborador pelo construtor; montar no composition root.

### R3. Domínio sem relógio, acaso global, ambiente nem I/O — [reference/domain-purity.md](reference/domain-purity.md)

- **Violação:** `datetime.now`, `time.time`, `uuid4`, `random.<função>`, `open`,
  `pathlib.Path`, `os.*`/`shutil.*`/`subprocess.*` sob `*/domain/`.
- **Fonte:** "Isolate the expression of the domain model and the business logic, and
  eliminate any dependency on infrastructure, user interface, or even application logic that
  is not business logic." — Evans, *DDD Reference*, 2015, LAYERED ARCHITECTURE, p.17 PDF.
- **Gate:** `scripts/check_domain_determinism.py` (hook: sim).
- **Correção:** tempo pelo port `Clock` (ADR 4.2.0002); arquivo/ambiente pelo adapter;
  caminho como valor puro com `PurePath`; acaso com `random.Random(seed)` explícito.

### R4. Value object valida na construção — [reference/value-object-invariants.md](reference/value-object-invariants.md)

- **Violação:** `@dataclass(frozen=True)` em `domain/value_objects/` sem `__post_init__` e
  sem o marcador `# vo-invariant: none — <motivo>`.
- **Fonte:** "State post-conditions of operations and invariants of classes and aggregates."
  — Evans, *DDD Reference*, 2015, ASSERTIONS, p.29 PDF.
- **Gate:** `scripts/check_vo_invariants.py` (hook: sim; débito de hoje no baseline → #160).
- **Correção:** validar no `__post_init__` (factory não basta: o construtor da dataclass segue
  chamável).

### R5. Conhecimento de schema tem dono único — [reference/schema-knowledge.md](reference/schema-knowledge.md)

- **Violação:** `"processed"`, `"dataset_tft"`, `"target_return"` redeclarados como literal em
  `features/modeling/application/`.
- **Fonte:** "Every piece of knowledge must have a single, unambiguous, authoritative
  representation within a system." — Hunt & Thomas, *The Pragmatic Programmer*, 20th anniv.
  ed., Tip 15, p.31.
- **Gate:** `scripts/check_schema_literals.py` (hook: sim; débito de hoje no baseline → #159).
- **Correção:** importar a constante do dono (o módulo que define o schema).

### R6. Port sem vocabulário de fornecedor — [reference/dependency-rule.md](reference/dependency-rule.md)

- **Violação:** nome de método, parâmetro ou tipo de um port (`application/ports/`) que
  carrega o fornecedor ou a tecnologia (`fetch_yfinance_history`, `mlflow_run_id`,
  `parquet_path`, parâmetro `pd.DataFrame`). Docstring que **cita** o adapter real não viola.
- **Fonte:** "We propose instead that one begins with a list of difficult design decisions or
  design decisions which are likely to change. Each module is then designed to hide such a
  decision from the others." — Parnas, *On the Criteria To Be Used in Decomposing Systems
  into Modules*, CACM 15(12), 1972, p.1058, doi:10.1145/361598.361623.
- **Camada:** revisor (#61 §Fora de escopo: denylist de identificadores tem falso-positivo
  alto). Para imports, o import-linter já pega (`store-no-storage-leak`, `sentiment-no-ml-leak`).
- **Correção:** nomear pelo que o consumidor precisa (`fetch_candles`, `run_id`); a tradução
  para o fornecedor fica no adapter.

### R7. Adapter sem estado mutável compartilhado — [reference/composition-root.md](reference/composition-root.md)

- **Violação:** atributo de classe/módulo mutável num adapter (cache, contador, conexão em
  global) ou instância mutada entre chamadas sem que o port declare isso.
- **Fonte:** regra do projeto (#61 §Fora de escopo); sem fonte primária verificada — ver
  Lacunas.
- **Camada:** revisor (gate seria ruidoso contra proxies lazy e rate limiters legítimos).
- **Correção:** estado legítimo (proxy lazy, rate limiter) vive na instância criada pelo
  composition root, com o motivo na docstring; o resto sai.

### R8. Baseline só encolhe — [reference/fitness-functions-and-baseline.md](reference/fitness-functions-and-baseline.md)

- **Violação:** entrada de `scripts/arch_baseline.toml` sem `motivo`/`issue`, ou que não
  ocorre mais.
- **Fonte:** "Consecutive runs will then only report new violations and ignore known
  violations. If violations are fixed, FreezingArchRule will automatically reduce the known
  stored violations to prevent any regression." — ArchUnit User Guide, §8.6 Freezing Arch Rules.
- **Gate:** `scripts/arch_baseline_lib.py`, usado por todos os gates de baseline.
- **Correção:** corrigiu a violação → apagar a entrada (o hook avisa); débito novo → issue
  real + entrada com `motivo` e `issue`.

## Regra nova: em qual camada?

1. Expressável como script com falso-positivo aceitável? → **gate** em `scripts/`, com teste
   em `tests/architecture/` que reprova uma violação injetada; se a chave começa com
   `<arquivo>::`, registrar em `GATES` do executor (um teste compara com `make arch-ast`).
2. Exige julgamento (nome, intenção, estado legítimo)? → linha neste catálogo com camada
   **revisor**.
3. Hook nunca ganha regra própria nem tipo `prompt`/`agent` (ADR 0.0.0058).
4. Fonte só entra lida literalmente e conferida pelo `evidence-verifier`
   (skill `evidence-resolution`).

## Lacunas (não citadas — texto não lido literalmente)

Seemann & van Deursen, *Dependency Injection Principles, Practices, and Patterns*, cap. 5
(Control Freak, Constrained Construction); Martin, *Clean Architecture* (2017); Vernon,
*Implementing Domain-Driven Design*, cap. 6; Khorikov, *Unit Testing* (2020); Ford, slides
*Evolutionary Architectures*. R7 fica sem fonte primária até uma delas ser lida.
