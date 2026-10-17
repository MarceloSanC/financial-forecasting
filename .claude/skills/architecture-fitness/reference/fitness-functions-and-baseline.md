# Fitness functions e baseline que só encolhe (R8)

## Fontes (conferidas na fonte bruta, #161)

- Paul & Wang, *Fitness function-driven development*, Thoughtworks Insights, 2019-01-11:
  "Fitness functions describe how close an architecture is to achieving an architectural
  aim."
- ArchUnit User Guide, §8.6 Freezing Arch Rules: "Consecutive runs will then only report new
  violations and ignore known violations. If violations are fixed, FreezingArchRule will
  automatically reduce the known stored violations to prevent any regression."

## Como o projeto aplica

- Cada gate de arquitetura é uma fitness function: script determinístico em `make check`/CI,
  com teste em `tests/architecture/` provando que reprova uma violação injetada (um gate que
  nunca reprovou não prova nada — #60).
- `scripts/arch_baseline.toml` + `scripts/arch_baseline_lib.py` (#62) congelam o débito:
  - violação fora do baseline reprova;
  - entrada sem `motivo` (texto) ou `issue` (inteiro > 0) reprova — baseline sem dono é
    sedimento;
  - entrada que não ocorre mais reprova ("baseline morto"): a lista encolhe sozinha, como no
    `FreezingArchRule`, mas exigindo a remoção explícita no diff.
- Gates com baseline: `fake_parity`, `port_coverage`, `use_case_deps`, `domain_determinism`,
  `schema_literals`, `vo_invariants`.

## Correção

| Situação | Ação |
|---|---|
| corrigiu uma violação do baseline | apagar a entrada `[[<gate>.allow]]` (o hook avisa na edição) |
| débito novo inevitável | abrir issue real; entrada com `key`, `motivo`, `issue` |
| gate novo | começar com baseline populado pela medição, nunca com permissão genérica |

Baseline não é permissão: entrada nova no PR precisa de justificativa no corpo do PR.
