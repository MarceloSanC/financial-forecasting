"""Adapter de plots do `evaluation` (Stage 8.3): o único lugar de `src/` que importa matplotlib.

Este `__init__` não importa matplotlib (o contrato `evaluation-no-matplotlib-leak` ignora só
`plots.**`); o renderizador mora em `matplotlib_figure_renderer`.
"""
