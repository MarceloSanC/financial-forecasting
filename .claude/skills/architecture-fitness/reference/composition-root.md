# Composition root e estado de adapter (R2, R7)

## Fontes (conferidas na fonte bruta, #161)

- Seemann, *Composition Root*, blog.ploeh.dk, 2011-07-28: "A Composition Root is a
  (preferably) unique location in an application where modules are composed together." e,
  logo depois, "all the application code relies solely on Constructor Injection (or other
  injection patterns), but is never composed. Only at the entry point of the application is
  the entire object graph finally composed."
- Mesmo texto: "Only applications should have Composition Roots. Libraries and frameworks
  shouldn't."

## Como o projeto aplica

- `src/financial_forecasting/composition_root.py` é o único lugar onde adapters concretos
  são instanciados (CLAUDE.md nota 5, LAYOUT §6). Proxies lazy (import pesado adiado) moram
  **dentro** dele.
- Use case recebe colaboradores pelo construtor; não importa adapter, não tem default
  concreto de infraestrutura. Default de **domínio puro** (política, quality gate) é permitido.
- Por que não há gate: a #61 cortou `check_composition_root.py` — o diagnóstico de "proxies
  fora do root" estava errado (estão dentro) e um gate que nasceria verde sem achar nada não
  prova saber reprovar. Fica com o revisor.

## R7 — estado mutável em adapter (revisor)

Sem fonte primária verificada (ver Lacunas no `SKILL.md`); é regra do projeto (#61 §Fora de
escopo). O que procurar:

| Suspeito | Legítimo quando |
|---|---|
| atributo de **classe** mutável (`_cache: dict = {}`) | nunca — vaza entre instâncias e testes |
| global de módulo mutado por função do adapter | nunca |
| instância mutada entre chamadas (contador, buffer) | o port declara o efeito, ou é proxy lazy / rate limiter criado no composition root com o motivo na docstring |
| conexão/cliente guardado na instância | criado no `__init__` a partir do que o composition root injeta |

## Correção

1. Estado de classe/módulo → atributo de instância criado no `__init__`.
2. Estado legítimo → documentar o motivo na docstring e garantir que nasce no composition root.
3. Default concreto num use case → parâmetro obrigatório, montado no composition root.
