"""Contrato de leitura do dataset TFT — dono único do endereço e da coluna-alvo (#159).

O `feature_engineering` produz o dataset TFT (Stage 3.5) e é o dono dos nomes pelos
quais ele é lido (LAYOUT §4, ADR 0.0.0053 item 3): o par `(layer, table)` com que os
consumidores o pedem ao `MedallionStore` (par read-only registrado na Stage 5.2, D3) e
o nome da coluna do alvo cuja convenção `target_definition` define (ADR 3.5.0001).

Antes desta issue, cada use case do `modeling` redeclarava os três nomes como constante
local — seis donos da mesma informação, e um rename esquecido em um deles era silencioso.
"Every piece of knowledge must have a single, unambiguous, authoritative representation
within a system." (Hunt & Thomas, *The Pragmatic Programmer*, 20th anniv., Tip 15). O
consumidor importa daqui como aresta de dados declarada no `bc-independence`.

Fora deste dono (débito registrado na #159): o registry read-only do
`ParquetMedallionStore` (`shared` não importa slice) e o `_TARGET` do `refresh_gold`
(`evaluation`), que repetem os mesmos nomes.

Pureza: só constantes e stdlib (`typing.Final`).
"""

from __future__ import annotations

from typing import Final

# Endereço lógico do dataset TFT no `MedallionStore` (par read-only, Stage 5.2 D3).
DATASET_TFT_LAYER: Final = "processed"
DATASET_TFT_TABLE: Final = "dataset_tft"

# Coluna do alvo backward log-return (`target_definition`, ADR 3.5.0001).
TARGET_COLUMN: Final = "target_return"
