# Regra de dependência e inversão (R1, R6)

## Fontes (conferidas na fonte bruta, #161)

- Martin, *The Dependency Inversion Principle*, C++ Report, 1996, p.6:
  "A. HIGH LEVEL MODULES SHOULD NOT DEPEND UPON LOW LEVEL MODULES. BOTH SHOULD DEPEND UPON
  ABSTRACTIONS."
- Parnas, *On the Criteria To Be Used in Decomposing Systems into Modules*, CACM 15(12),
  1972, p.1058 (Conclusion), doi:10.1145/361598.361623: "We propose instead that one begins
  with a list of difficult design decisions or design decisions which are likely to change.
  Each module is then designed to hide such a decision from the others."

## Como o projeto aplica

- Direção de import (domain ← application ← adapters; features → shared): import-linter,
  contratos em `.importlinter` (LAYOUT §3, ADR 1.3.0001).
- O colaborador do use case é o **port** (`Protocol` em `<slice>/application/ports/out/`), nunca
  a classe do adapter, de `shared/infrastructure/` nem o use case de outro slice. Serviço de
  domínio concreto é permitido (é domínio puro, não detalhe). Gate:
  `scripts/check_use_case_deps.py`, chave `<arquivo>::<Classe>.__init__(<param>)`.
- Comportamento de outro slice entra por port definido no **consumidor** e satisfeito por
  duck-typing (ADR 0.0.0053).

## R6 — vocabulário de fornecedor no port (revisor)

O port esconde a decisão "qual fornecedor/tecnologia" (Parnas). Se a assinatura nomeia o
fornecedor, trocar de fornecedor muda o port e todos os consumidores.

| Viola (assinatura) | Não viola |
|---|---|
| `def fetch_yfinance_history(...)` | `def fetch_candles(...)` |
| parâmetro `mlflow_run_id: str` | `run_id: str` |
| retorno `pd.DataFrame` / `pa.Table` | `Sequence[Mapping[str, object]]`, VO de domínio |
| `def write_parquet(path, ...)` | `def write(layer, table, rows)` |
| — | docstring que cita o adapter real (`Real: ParquetAnalyticsRepository`) |

Nome do conceito do domínio que coincide com produto (ex.: `sentiment` de um modelo FinBERT)
não viola; viola o nome que só faz sentido para aquele fornecedor.

## Correção

1. Renomear pelo que o consumidor precisa; mover a tradução para o adapter.
2. Tipo de biblioteca na assinatura → tipo `collections.abc`/primitivo ou VO.
3. Se o import da lib já está no port, o import-linter reprova antes do revisor
   (`store-no-storage-leak`, `sentiment-no-ml-leak`).
