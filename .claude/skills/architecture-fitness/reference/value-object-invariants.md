# Invariantes de value object (R4)

## Fontes (conferidas na fonte bruta, #161)

- Evans, *DDD Reference*, 2015-03, VALUE OBJECTS, p.19 PDF (p.12 impressa): "Treat the value
  object as immutable. Make all operations Side-effect-free Functions that don't depend on
  any mutable state."
- Evans, idem, ASSERTIONS, p.29 PDF (p.22 impressa): "State post-conditions of operations and
  invariants of classes and aggregates."
- Wlaschin, *Designing with types: Single case union types*, fsharpforfunandprofit.com,
  §Forcing use of the constructor: "One issue is that you cannot force callers to use the
  constructor. Someone could just bypass the validation and create the type directly." e
  "If you really want to encapsulate the internals of the type and force callers to use a
  constructor function, you can use module signatures."

## O que o gate reprova

`scripts/check_vo_invariants.py`: `@dataclass(frozen=True)` em `*/domain/value_objects/` sem
`__post_init__`. Chave `<arquivo>::<Classe>`. Débito de hoje no baseline → #160.

Por que factory validadora não basta: em Python o construtor da dataclass segue chamável —
`Cls(value=...)` contorna a `from_raw()` (o problema que Wlaschin descreve, sem o recurso de
module signatures do F#).

## Opt-out por desenho

VO sem invariante **por desenho** declara, entre o decorador e o `class`:

```python
# vo-invariant: none — <motivo>
@dataclass(frozen=True)
class Label: ...
```

Marcador sem motivo reprova. Débito (VO que **deveria** validar) vai para o baseline com
`motivo` + `issue`, não para o marcador.

## Correção

1. Escrever `__post_init__` que levanta `ValueError` para valor fora da invariante
   documentada na docstring.
2. Teste unit do VO com um caso inválido por invariante.
3. Se o VO estava no baseline, apagar a entrada (o hook avisa "baseline morto").
