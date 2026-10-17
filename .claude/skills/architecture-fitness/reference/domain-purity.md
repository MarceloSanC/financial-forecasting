# Pureza e determinismo do domínio (R3)

## Fontes (conferidas na fonte bruta, #161)

Evans, *Domain-Driven Design Reference*, 2015-03 (domainlanguage.com). "p. PDF" = página do
arquivo; a impressa no rodapé é 7 a menos.

- LAYERED ARCHITECTURE, p.17 PDF (p.10 impressa): "Isolate the expression of the domain
  model and the business logic, and eliminate any dependency on infrastructure, user
  interface, or even application logic that is not business logic."
- SIDE-EFFECT-FREE FUNCTIONS, p.28 PDF (p.21 impressa): "Place as much of the logic of the
  program as possible into functions, operations that return results with no observable side
  effects."

## O que o gate reprova

`scripts/check_domain_determinism.py`, em todo módulo sob `*/domain/`; chave
`<arquivo>::<nome qualificado>`; aliases de import resolvidos.

| Família | Nomes |
|---|---|
| relógio | `datetime.now/utcnow/today`, `date.today`, `time.time/time_ns/monotonic/perf_counter` |
| id aleatório | `uuid.uuid1/uuid4`, `secrets.*` |
| acaso global | `random.<função>`, `random.SystemRandom`, `random.Random()` sem semente |
| sistema operacional | `os.*`, `shutil.*`, `subprocess.*`, `socket.*`, `tempfile.*`, `glob.*` |
| arquivo | `open`, `io.open`, `pathlib.Path` |

Passam por desenho: `random.Random(seed)`, a anotação `rng: random.Random`, `PurePath`/
`PurePosixPath`, campo `open: float` de dataclass, parâmetro chamado `open`.

## Correção

| Precisa de | Faça |
|---|---|
| hora atual | receber do port `Clock` (ADR 4.2.0002) ou como argumento |
| id | receber pronto do application/adapter |
| acaso | `random.Random(seed)` com semente explícita, passada de fora |
| arquivo, ambiente, processo | adapter (`adapters/out/`) atrás de um port |
| caminho como valor | `PurePosixPath` |

O hook `arch_feedback` aponta a violação na edição; o veredito é o `make arch-ast`.
