"""Versão do pipeline de modelagem que entra na identidade do run (`RunId`).

`pipeline_version` é um dos 9 campos do `RunId` (Stage 1.4). Ele NÃO vira
coluna de `dim_run` (a Stage 4.1 descartou a coluna) — existe só dentro do
hash. Bumpar aqui muda o `run_id` de TODO run já persistido e é o ato que torna
uma descontinuidade de identidade **explícita e rastreável** em vez de
silenciosa (issue #65): quem compara runs de versões diferentes vê hashes que
não pareiam, nunca dados diferentes sob o mesmo id.

Quando bumpar: sempre que a definição de "o mesmo run" mudar — campos que
entram/saem do payload de `config_signature`, mudança no conjunto de slots do
`RunId`, correção de precisão numérica que altera o dado sob um id inalterado
(o caso `float32`/`float64` migrado da #67). NÃO bumpar por mudança de schema
de tabela (`schema_version` é proveniência, gravado como coluna).

Histórico (uma linha por bump; nunca reciclar):

- `"1"` — payloads hand-rolled por use case (Stages 5.2-5.4), com
  `schema_version` dentro da chave. O campo não era emitido; o valor é
  atribuído retroativamente só para o registro.
- `"2"` — identidade canônica via `RunId.compute`/`ConfigSignature.compute`;
  `schema_version` fora da chave; `cohort_id`, `max_horizon` e
  `feature_set_name` dentro de `config_signature`; `feature_set_hash` = hash
  do conteúdo do `FeatureRegistry` (issue #65, ADR 5.2.0004).
"""

PIPELINE_VERSION = "2"
