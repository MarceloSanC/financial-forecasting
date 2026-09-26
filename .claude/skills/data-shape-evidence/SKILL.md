---
name: data-shape-evidence
description: "Invocar antes de decidir modelagem, feature, filtro, janela ou tratamento sobre dado do medalhão (bronze/silver/gold: candles, news, fundamentals, dataset TFT, fact_oos_predictions) — inclusive \"esse campo é X ou Y?\", \"quantas linhas caem no fallback?\", \"vale simplificar?\", \"o gate de degeneração pega quantas?\" — e sempre que uma decisão citar número vindo de doc, ADR, ledger ou roadmap em vez de medição da sessão. Par da evidence-resolution: ela cobre o que a literatura diz; esta cobre o que o NOSSO dado é."
metadata:
  status: draft
  applies_when:
    camada_alvo: [domain, application, adapters]
---

# Evidência da forma do dado antes de decidir

Decisão sobre dado se toma **olhando linhas reais** — não o nome da coluna, não o número que um
doc registrou, não a descrição da fonte. Recomendação certa sobre premissa rasa é o pior caso:
parece sólida e leva para o lugar errado.

## Os cinco testes

1. **Puxe linhas, não só agregados.** Um `COUNT(*)` agrupado esconde estrutura. Traga ~20 linhas
   reais com as colunas que importam e **leia**; padrões distintos dentro do mesmo agregado só
   aparecem aí.
2. **Teste contra o que o campo reconcilia, nunca contra o nome.** O significado é a coluna/regra
   com que ele fecha (ex.: `target_return` recomputado de `close` bate linha a linha?
   `effective_date` ≤ data da linha em 100% das linhas?).
3. **Prove que a guarda morde antes de confiar no "100%".** Veja o denominador e o sentinela:
   coluna nunca nula com sentinela `0`/`""`/`NaN`-como-float torna "100% preenchido" verdadeiro e
   vazio. Conte o **valor real**, não a ausência de nulo.
4. **Simule cada opção sobre uma linha real** e escreva o que cada uma faz com o número. A que
   erra aparece sozinha; comparação abstrata não mostra.
5. **Remeça o número do doc e confira se a medição delegada aconteceu.** Dado cresce e ADR que
   delega "medir na Stage seguinte" frequentemente não é cumprido. Ex. deste repo: "17/81
   `reported_date` NaT" (ADR 2.1.0001, medido na 2.1 sobre o raw reusado) vale para aquele
   snapshot — remeça antes de decidir o fallback em cima dele.

## Como registrar

Número medido entra no concept/ADR **com a data da medição e a consulta** que o produziu (a
consulta commitada ou colada). Número datado já existente **não se reescreve** — some a medição
nova ao lado; reescrever registro datado é falsificar histórico. Quando a medição que decidiria
não é possível, **nomeie a limitação** em vez de preencher com suposição.

## Gotchas

- **Em 2026-09-26 não há dado materializado neste checkout** (`DATA_ROOT=data`, diretório
  ausente). Materializar pelos use cases de ingestão/dataset ou declarar a limitação — nunca
  medir no repo antigo e citar como se fosse desta base.
- **Rodar a medição no container** (workflow Docker-only): consulta DuckDB sobre o Parquet
  particionado (`read_parquet('data/<camada>/<tabela>/**/*.parquet', hive_partitioning=true)`).
- **Grave a consulta com Write e rode por caminho** — heredoc do Bash come barras invertidas
  (regex e `\n` quebram em silêncio).
- Parquet `float32` (indicadores) vs `float64` (alvo): comparação exata falha por arredondamento;
  compare com tolerância declarada.
