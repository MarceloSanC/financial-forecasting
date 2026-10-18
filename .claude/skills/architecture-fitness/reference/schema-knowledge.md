# Conhecimento de schema com dono único (R5)

## Fontes (conferidas na fonte bruta, #161)

- Hunt & Thomas, *The Pragmatic Programmer*, 20th Anniversary Edition, Tip 15, p.31 (lista
  oficial em pragprog.com/tips): "Every piece of knowledge must have a single, unambiguous,
  authoritative representation within a system."
- Parnas, CACM 15(12), 1972, p.1058, doi:10.1145/361598.361623: "Each module is then designed
  to hide such a decision from the others."

## O que o gate reprova

`scripts/check_schema_literals.py`, escopado a `features/modeling/application/`: os literais
`"processed"`, `"dataset_tft"` e `"target_return"` fora de docstring. Chave
`<arquivo>::"<literal>"`. Débito de hoje no baseline → #159.

Perímetro estreito de propósito: `"timestamp"` **não** entra — é legítimo em
`build_dataset`/`ingest_candles`, que falam do schema da bronze; gate largo dá
falso-vermelho e morre (#61).

## Correção

1. Importar a constante do módulo dono do schema em vez de redeclarar o literal.
2. Se o dono ainda não existe, o refactor é a #159 — não criar um segundo dono.
3. Redeclarar como constante local (`_DATASET_LAYER = "processed"`) **não** corrige: é o
   mesmo conhecimento em dois lugares.

## Regra geral (fora do gate)

O mesmo vale para qualquer coordenada de schema repetida entre slices: o revisor aponta,
citando Tip 15; o gate só cobre o perímetro medido.
