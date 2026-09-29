"""Quality checks do refresh do gold (Stage 6.4; ADR `6_4_0002`).

Ordem canônica do registry: `alignment_check` (ERROR), `statistical_preconditions`
(ERROR), `degeneracy_check` (WARN), `realized_provenance` (WARN). O wiring (a
instância do `QualityCheckRegistry`) é do `composition_root`.
"""
