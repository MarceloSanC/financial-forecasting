"""Adapters out DuckDB do bounded context `feature_engineering`.

Única casa de `duckdb` no BC (concept 3.3 I5/D1): o ASOF JOIN backward de
fundamentos vive aqui; `application`/`domain` permanecem stdlib-only (gate
`import-linter` `store-no-storage-leak`).
"""
