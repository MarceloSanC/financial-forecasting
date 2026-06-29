---
title: Concept — Stage 1.2 — CI e gate de cobertura efetivo
description: Tornar o gate de qualidade (lint+types+layout+testes+cobertura≥90%) um enforcement real no CI e tratar o excedente herdado do template
when-use: Consultar ao iniciar a Fase 3B (technical) da Stage 1.2; revisar antes de executar
keywords: [concept, ci-coverage, fail_under, gate, fitness-function, template-surplus, omit, pragma, layout-check, github-actions]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.2-ci-coverage
stage_title: CI e gate de cobertura efetivo
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.1-bootstrap]
---

# Concept — Stage 1.2 — CI e gate de cobertura efetivo

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes. O plano executável fica no
> [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo
- **Tornar o gate de cobertura ≥ 90% efetivo no CI (corrigir F3).** Fazer o caminho que o CI executa
  (`make check`) passar por `pytest --cov=src/financial_forecasting --cov-report=term-missing`, de
  modo que o `fail_under=90` já declarado no `pyproject.toml` **efetivamente dispare**. Hoje
  `make check → make test` roda `pytest -v` **sem `--cov`**, então o gate é inerte (cobertura real
  medida: **33.01%**).
- **Tratar o excedente herdado do template** (modulos inertes a ~33%: `main.py`,
  `composition_root.py`, `shared/infrastructure/{http,database,logging,clock,uuid_generator,config}`,
  stub out-ports, `pagination.py`) por **combinação guiada por escopo**: poda do que está fora de
  escopo (assunção SQLAlchemy/Postgres — overview §6 "sem Postgres") + `omit`/`exclude_lines` do
  wiring legítimo (composition root, `main.py`, `__main__`, stubs de Protocol) + `# pragma: no cover`
  pontual — até a cobertura do **código vivo** ficar ≥ 90%.
- **Endurecer `.github/workflows/ci.yml`:** garantir que o passo de gate roda a cobertura
  efetivamente (consequência de `make check`), adicionar `timeout-minutes` por job, preservar
  `guard-main-source` e a toolchain `uv`/`setup-uv`. Job único `lint-and-test`.
- **Validar o gate por quebra intencional revertida** (DoD): provar que reprovam (a) erro de lint,
  (b) erro de tipo mypy, (c) violação de import (`check_layout.py`), (d) cobertura < 90%; reverter
  cada quebra; registrar a evidência na §7 do `technical.md`.
- **Atualizar `README.md`:** seção de CI/qualidade documentando o contrato (lint+types+layout+testes
  +cobertura≥90%), badge de status do workflow `ci`, e nota de que os contratos import-linter formais
  chegam em 1.3.

### Fora do escopo (explicitamente)
- Deploy / release.
- Cache de dependências no CI.
- Matrix de versões Python.
- Features de negócio.
- **Contratos import-linter formais** (`.importlinter`, `tests/architecture/`) — são Stage 1.3
  (`non_goal` explícito da 1.2; ver D3 e ADR 1.2.0010). A direção de dependência **já é gateada hoje**
  por `scripts/check_layout.py` em `make layout-check`; 1.2 garante que esse mecanismo reprova, 1.3
  troca/expande para import-linter.

### Vínculo com o roadmap
Esta Stage entrega a parte de **CI/cobertura** do Step 1 ("Fundação e fitness arquitetural"):
"qualquer mudança que viole arquitetura/cobertura é barrada automaticamente antes do merge". Depende
de `1.1-bootstrap` (que montou os checks individuais e o `fail_under=90` ainda inerte) e habilita
`1.3-architecture-contracts` (que substitui o `layout-check` pelos contratos import-linter formais).
Fonte: `roadmap.md` Stage 1.2; `overview.md` §4/§7.

## 2. Objetivo da Stage

Após esta Stage, **um PR que viole ruff, mypy `--strict`, a direção de dependência hexagonal
(`check_layout.py`), a suíte de testes OU a cobertura < 90% falha no CI antes do merge** — provado por
quebra intencional revertida — com a cobertura medida sobre código vivo e em escopo (excedente
herdado tratado), sem que código de wiring/diferido reprove o gate.

## 3. Contexto e premissas

### Contexto
- **F3 (carregado da stage-audit 1.1) — gate inerte e míope.** `pyproject.toml` já tem
  `[tool.coverage.report] fail_under = 90`, mas `fail_under` é setting de `coverage report`: só
  dispara quando a cobertura está sendo medida. O caminho do CI (`make check → make test = pytest
  tests/ -v`) **não passa `--cov`**, então nunca dispara. Medido ao vivo: 33.01%
  (`pytest --cov` → `FAIL Required test coverage of 90.0% not reached. Total coverage: 33.01%`). A
  config está correta; o caminho de invocação é que neutraliza o gate.
- **O 33% é dominado pelo excedente herdado**, não por falta de teste de domínio. ADR 1.1.0001 aceitou
  o esqueleto web/DB do template como dívida técnica inerte declarada. Números por módulo: `main.py`
  0%, `http/*` 40–75%, `database/connection.py` 0%, `logging/config.py` 0%, stub ports 0%,
  `pagination.py` 0%, `composition_root.py` 71%.
- **Precedentes do repo antigo** (`financial-time-series-forecasting`): `make test` passava `--cov`
  (positivo) mas **nunca tinha `fail_under`** (negativo — cobertura era só relatório);
  `[tool.coverage]` tinha `exclude_lines` com `__main__`/`NotImplementedError`/`AssertionError`
  (precedente a replicar) **e** `omit = ["src/adapters/*"]` (anti-precedente — **não** replicar; em
  hexagonal adapters têm contract test e devem contar).

### Premissas
- A toolchain do projeto novo (`uv sync --extra dev` + ruff + mypy + pytest) é preservada; nada de
  pip/black/pytest-direto do repo antigo.
- O `make check` atual já encadeia `lint → typecheck → layout-check → docs-check → test`; basta o
  `test` (ou o alvo que o CI usa) ganhar cobertura para o gate fechar.
- `scripts/check_layout.py` já reprova violação de direção de dependência (verificado no Stage 1.1).

### Dependências
- `1.1-bootstrap` (`done`): provê `pyproject.toml` com `fail_under=90`, `Makefile`, `ci.yml`,
  `scripts/check_layout.py`, e o excedente do template tratado como dívida declarada (ADR 1.1.0001).

## 4. Contratos

### Introduzidos
- **Nenhum contrato de código** (port/DTO/entidade/value-object) é introduzido — esta Stage é infra
  de CI/cobertura.
- **Contrato operacional (fitness function / enforcement-as-test):** após esta Stage o CI **deve**
  reprovar qualquer PR que viole `ruff`, `mypy --strict`, `scripts/check_layout.py` (direção de
  dependência hexagonal) **ou** cobertura `< 90%`. "CI verde = todas as fronteiras seguraram"
  (overview §4/§7; formalizado no ADR 1.2.0011).

### Consumidos
- **`check_layout.py`** — mecanismo de gate de direção de dependência declarado/instalado na Stage
  `1.1-bootstrap`; reusado aqui como o "contrato de import" da 1.2 (D3).
- **`fail_under=90`** — config declarada na Stage `1.1-bootstrap`; tornada efetiva aqui.

## 5. Invariantes e regras

- **I1 — CI verde ⟹ todas as fronteiras seguraram.** CI verde implica `ruff` OK **e** `mypy --strict`
  OK **e** `check_layout.py` OK **e** `pytest` OK **e** cobertura ≥ 90%. A falha de **qualquer um**
  falha o job `lint-and-test` e bloqueia o merge. (overview §4/§7; ADR 1.2.0011)
- **I2 — `fail_under=90` é efetivamente exercitado no caminho do CI (não inerte).** O alvo que o CI
  roda passa por `pytest --cov`; provado por quebra intencional revertida (remover/quebrar um teste
  ou baixar cobertura deixa o CI vermelho). (corrige F3; ADR 1.2.0010 D1)
- **I3 — A cobertura medida reflete código VIVO e em escopo.** Exclusões (`omit`/`exclude_lines`/
  `pragma`) são restritas a wiring/DI/`__main__`/stubs de Protocol/infra diferida declarada —
  **nunca** usadas para inflar o número sobre lógica de domínio/application. **Adapters com contract
  test CONTAM** (não replicar o `omit = adapters/*` do repo antigo). (ADR 1.2.0010 D2)
- **I4 — Toolchain preservada.** `uv sync --extra dev` + `ruff` + `mypy` + `pytest`; nenhuma
  ferramenta do repo antigo (pip/black) importada — só o **conceito** de gate de cobertura.
- **I5 — Um único job de gate basta.** `lint-and-test` rodando `make check` (que após a Stage inclui
  cobertura); `guard-main-source` preservado e ortogonal; **não** fragmentar em jobs encadeados com
  `needs:`. (ADR 1.2.0011 alt. B)
- **I6 — A Stage 1.2 NÃO introduz `.importlinter` nem `tests/architecture/`** (isso é 1.3). O
  "contrato de import" da 1.2 é o `check_layout.py` existente. (ADR 1.2.0010 D3; `non_goal` do
  roadmap)
- **I7 — `make check` local == veredito do CI.** O gate que o desenvolvedor roda localmente
  (`make check`) e o que o CI roda devem ser o mesmo, sem drift (a cobertura entra dentro de
  `make check`, não num passo separado pulável). (ADR 1.2.0011 alt. A)

## 6. Casos de erro e exceções

- **C1 — Cobertura < 90% (após tratamento do excedente).** `pytest --cov` reporta
  `FAIL Required test coverage of 90.0% not reached`; o job `lint-and-test` falha (exit ≠ 0); o merge
  é bloqueado.
- **C2 — Violação de lint.** `ruff check` falha; `make check` aborta no passo `lint`; job vermelho.
- **C3 — Erro de tipo.** `mypy src/` falha; `make check` aborta no `typecheck`; job vermelho.
- **C4 — Violação de direção de dependência.** `check_layout.py` retorna erro; `make check` aborta no
  `layout-check`; job vermelho. (é o "contrato de import" gateado em 1.2)
- **C5 — Teste quebrado.** `pytest` falha; `make check` aborta no `test`; job vermelho.
- **C6 — PR para `main` de origem inválida.** `guard-main-source` falha (origem ≠ `develop`/
  `hotfix/*`); preservado da Stage 1.1, ortogonal ao gate de qualidade.
- **C7 — Job travado.** `timeout-minutes` por job aborta o run em vez de consumir minutos do Free
  indefinidamente.

> Os casos C1–C5 são exatamente as 4–5 quebras intencionais que a validação do DoD exercita e
> reverte (lint, tipos, layout, cobertura; e o teste quebrado como variante de cobertura/suite).

## 7. Decisões técnicas relevantes

### D1 — Como o gate de cobertura roda efetivamente no CI (corrige F3)
- **O quê:** adicionar `--cov=src/financial_forecasting --cov-report=term-missing` ao alvo `test`
  (chamado por `make check`, chamado pelo job `lint-and-test`), mantendo `fail_under=90` no
  `pyproject.toml`; manter `test-fast` sem cobertura para o loop local e `test-cov` com relatório
  HTML.
- **Por quê:** `fail_under` só dispara sob `pytest --cov`; hoje `make test` não passa `--cov`, logo o
  gate é inerte (F3). Pôr `--cov` dentro do `make check` mantém **uma só fonte da verdade**: o que o
  dev roda localmente == o que o CI roda (I7). Espelha o repo antigo (`Makefile` L29-33) **corrigindo**
  sua omissão (faltava `fail_under`). Simples e trocável: uma flag num alvo existente.
- **Fonte:** F3 (stage-audit 1.1); `overview.md` §4/§7; repo antigo `Makefile` L29-33 (positivo) e
  `pyproject` L68-83 (sem `fail_under`, negativo); medição local 33.01%.
- **ADR:** [`../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md`](../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md) (D1).

### D2 — Tratamento do excedente herdado do template a 33% (F3)
- **O quê:** combinação guiada por escopo — **podar** o que o overview §6 declara fora (assunção
  SQLAlchemy/Postgres: `database/connection.py`); **omit/`exclude_lines`** do wiring legítimo
  (composition root, `main.py`, `__main__`, `TYPE_CHECKING`, stubs de Protocol `...`,
  `NotImplementedError`/`AssertionError`); **`# pragma: no cover`** pontual em ramos defensivos —
  até a cobertura do código vivo ficar ≥ 90%. **Não** replicar `omit = adapters/*`.
- **Por quê:** manter o gate **honesto** — medir cobertura sobre código vivo, não inflar
  cosmeticamente sobre código morto/wiring. A poda alinha com overview §3 ("não reaproveitar
  implementações anteriores") e paga a dívida da 1.1.0001 no momento mais barato. Adapters têm
  contract test (ADR 0.0.0021) e devem contar.
- **Fonte:** F3; `overview.md` §3/§6; ADR 1.1.0001; repo antigo `pyproject` L68-83 (`exclude_lines`
  positivo; `omit adapters/*` negativo).
- **ADR:** [`../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md`](../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md) (D2).

### D3 — Escopo de "contrato de import" no DoD de 1.2 (tensão roadmap-humano vs YAML)
- **O quê:** cumprir o DoD via o mecanismo de contrato **já existente** — `scripts/check_layout.py`
  em `make layout-check` dentro de `make check` (reprova violação de direção). Os contratos
  import-linter formais (`.importlinter`, `tests/architecture/test_import_contracts.py`) ficam para
  a Stage 1.3.
- **Por quê:** tensão real — a prosa humana de 1.2 diz "import-linter no CI", mas (i) o YAML formal de
  1.2 não lista `.importlinter` (está em 1.3); (ii) import-linter não está instalado; (iii) o
  `non_goal` de 1.2 é literalmente "import-linter contracts (1.3)". O outcome de *enforcement* já é
  atendido hoje (layout-check reprova); 1.2 garante que reprova, 1.3 troca/expande.
- **Fonte:** `roadmap.md` Stage 1.2 (`arquivos_a_criar` vs 1.3; `non_goals`); `Makefile`
  `layout-check`; `check_layout.py`.
- **ADR:** [`../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md`](../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md) (D3).

### D4 — Gate de qualidade como fitness function única e bloqueante
- **O quê:** definir "CI verde" como uma fitness function única (ruff + mypy + layout + pytest +
  cobertura≥90%) implementada como **um** job `lint-and-test` rodando `make check`; `guard-main-source`
  preservado; **não** fragmentar em jobs encadeados.
- **Por quê:** enforcement-as-test (overview §7) — um check que não bloqueia é decoração; um job único
  é o gate honesto mínimo (simples e trocável); fragmentar não traz ganho na escala atual e custa
  minutos do Free + complexidade.
- **Fonte:** `overview.md` §4/§7; roadmap Step 1; repo antigo `ci.yml` (2 jobs — não replicar a
  fragmentação).
- **ADR:** [`../../adr/1_2_0011-coverage-gate-as-foundational-fitness-function.md`](../../adr/1_2_0011-coverage-gate-as-foundational-fitness-function.md) (ADR de fundação derivado do overview §4/§7).

### D5 — Endurecimento operacional do workflow (timeout, estrutura de jobs)
- **O quê:** adicionar `timeout-minutes` por job; manter job único `lint-and-test`; preservar
  `guard-main-source` e a toolchain `uv`/`setup-uv`.
- **Por quê:** `timeout-minutes` é barato e evita job travado consumindo minutos do Free; decisão
  operacional menor, sem ADR próprio (coberta pela D4/ADR 1.2.0011).
- **Fonte:** repo antigo `ci.yml` L9-12 (`timeout-minutes: 40/20` — precedente positivo); `ci.yml`
  atual (`guard-main-source` a preservar).

## 8. Integrações

### Internas
- `Makefile`: alvo `test` (e portanto `check`) passa a medir cobertura; `test-fast`/`test-cov`
  mantidos.
- `pyproject.toml` `[tool.coverage]`: `source = src/financial_forecasting`, `exclude_lines`
  defensivos, `omit` restrito a wiring, `fail_under=90` intacto.
- `scripts/check_layout.py`: reusado como o gate de "contrato de import" da 1.2.

### Externas
- **GitHub Actions** (`actions/checkout@v4`, `actions/setup-python@v5`, `astral-sh/setup-uv@v3`):
  workflow `ci.yml` roda `make check` com cobertura; badge de status referenciado no README.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Poda incompleta quebra `make setup`/imports/`layout-check` | M | M | Após podar, rodar `make check` + smoke import (DoD 1.1); reverter se layout-check/mypy ficarem vermelhos |
| `omit`/`pragma` usados para inflar o número sobre lógica real | B | A | I3 + revisão: exclusões só em wiring/stubs; adapters contam; lista auditável no `pyproject.toml` |
| Gate continua inerte por erro de invocação (`--cov` no alvo errado) | B | A | Validação por quebra intencional revertida (DoD): baixar cobertura deve deixar o CI vermelho |
| Drift entre `make check` local e CI | B | M | Cobertura entra **dentro** de `make check`, não em passo separado (I7) |

## 11. Critérios de aceitação

- [ ] **A1** — `make check` (caminho do CI) executa `pytest --cov=src/financial_forecasting
  --cov-report=term-missing` e o `fail_under=90` dispara (verificável: antes do tratamento do
  excedente, o gate REPROVA a 33%). (I2, D1)
- [ ] **A2** — Após o tratamento do excedente, `make check` fica **verde** com cobertura ≥ 90%
  medida **apenas** sobre código vivo; nenhuma exclusão sobre lógica de domínio/application;
  `adapters/*` não está em `omit`. (I3, D2)
- [ ] **A3** — `pyproject.toml` `[tool.coverage]`: `source` fixado em `src/financial_forecasting`,
  `exclude_lines` defensivos presentes (`__main__`, `NotImplementedError`, `AssertionError`,
  `TYPE_CHECKING`, `...`), `fail_under=90` intacto; `mypy`/`ruff` verdes. (D2)
- [ ] **A4** — `.github/workflows/ci.yml` válido (yaml), job único `lint-and-test` roda `make check`
  (que inclui cobertura), `timeout-minutes` presente por job, `guard-main-source` intacto, toolchain
  `uv`/`setup-uv` preservada. (I5, D5)
- [ ] **A5** — Validação por quebra intencional revertida registrada na §7 do `technical.md`: para
  cada uma de (a) lint, (b) tipo mypy, (c) violação de import (`layout-check`), (d) cobertura<90%
  (remover um teste) — o gate fica **VERMELHO**; após reverter, **VERDE**. (I1, I2, DoD)
- [ ] **A6** — `README.md` descreve o contrato de cobertura e o que reprova um PR (lint+types+layout+
  testes+cobertura≥90%), exibe o badge de status do workflow `ci`, e nota que os contratos
  import-linter formais chegam em 1.3; coerente com `CLAUDE.md`/`GIT-WORKFLOW.md`. (D3, D4)
- [ ] **A7** — `.importlinter` e `tests/architecture/` **não** são criados nesta Stage (respeito ao
  `non_goal`); o "contrato de import" da 1.2 é `check_layout.py`. (I6, D3)
- [ ] **A8** — `make check` verde no estado final; `make docs-check` (check_technical_postexec +
  check_stage_issue) não reprova.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (não há contrato de código; o contrato
  operacional está em §4)
- [x] Toda decisão em §7 tem fonte rastreável? (sim — F3, overview §3/§4/§6/§7, roadmap, repo antigo)
- [x] Toda integração externa tem contrato definido? (GitHub Actions — §8)
- [x] Decisões com alternativa real descartada têm ADR escrito? (D1/D2/D3 → ADR 1.2.0010; D4 → ADR de
  fundação 1.2.0011; D5 coberta por 1.2.0011)
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? (1.1-bootstrap = `done`)
- [x] Stage cabe em ~3–8 Tasks? (7 tasks)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] A validação do gate por quebra intencional revertida está prevista como critério? (A5; §7 do
  technical)

## 13. Questões em aberto

- Nenhuma. (As decisões D1–D5 fecham o escopo; o `non_goal` de import-linter resolve a tensão
  roadmap-humano vs YAML via D3.)

## 14. Referências

- [`../../overview.md`](../../overview.md) — §3 (escopo), §4 (fronteiras enforçadas / ≥90%), §6 (sem
  Postgres; domínio puro), §7 (enforcement-as-test).
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.2-ci-coverage` (DoD, `non_goals`); Stage
  `1.3-architecture-contracts` (import-linter formal).
- ADRs desta Stage:
  [`../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md`](../../adr/1_2_0010-cobertura-no-ci-e-tratamento-do-excedente-herdado.md),
  [`../../adr/1_2_0011-coverage-gate-as-foundational-fitness-function.md`](../../adr/1_2_0011-coverage-gate-as-foundational-fitness-function.md).
- ADRs relacionados: [`../../adr/1_1_0001-template-surplus-handling.md`](../../adr/1_1_0001-template-surplus-handling.md)
  (excedente herdado), [`../../adr/0_0_0019-hexagonal-enforced.md`](../../adr/0_0_0019-hexagonal-enforced.md)
  (fitness function), [`../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md`](../../adr/0_0_0021-per-unit-contract-tests-with-oracle.md)
  (adapters contam).
- F3 — findings carregados da stage-audit 1.1 (gate inerte/míope; excedente a 33.01%).
</content>
</invoke>
