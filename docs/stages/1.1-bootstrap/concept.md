---
title: Concept — Stage 1.1 — Bootstrap
description: Fundação do repositório (toolchain uv/ruff/mypy/pytest, estrutura hexagonal vazia, gate de layout) e autoria dos ADRs de fundação derivados do overview §11
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar
keywords: [concept, bootstrap, hexagonal, adr, toolchain, check-layout, fitness-function, fundacao]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.1-bootstrap
stage_title: Bootstrap
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: []
---

# Concept — Stage 1.1 — Bootstrap

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e decisões técnicas
> relevantes. O plano executável fica no [`technical.md`](./technical.md) correspondente.

## 1. Escopo

### Dentro do escopo

- **Autorar os 4 ADRs de fundação** derivados do overview §11 (em inglês, `status: accepted`,
  template `docs/templates/adr.md`):
  - `0_0_0002` — enquadramento = calibração probabilística (não acurácia pontual);
  - `0_0_0019` — hexagonal pleno enforçado por ferramenta;
  - `0_0_0020` — estatística como serviços de domínio puros sobre value objects;
  - `0_0_0021` — testes de regressão por unidade + oráculo (não snapshot global).
- **Confirmar/ajustar** os artefatos de toolchain e a estrutura hexagonal que o roadmap lista em
  `arquivos_a_criar` — todos já presentes via bootstrap do template
  (`pyproject.toml` uv+ruff+mypy strict+pytest; `Makefile` com `setup/check/fmt/test`; `README.md`;
  `.pre-commit-config.yaml`; `scripts/check_layout.py`;
  `src/financial_forecasting/{__init__, shared/{domain,application,infrastructure}, features}/__init__.py`;
  `tests/test_smoke.py`) e validar que os gates (layout-check + smoke) passam.
- **Decidir o tratamento do excedente do template** (composition_root, main, infra http/database/
  logging/clock/uuid, `pagination.py`, ports stub clock/id_generator) que conflita com a noção de
  "estrutura vazia" — registrado no ADR local `1_1_0001` (decisão D-1).
- **Garantir a invariante de docstring** em cada `__init__.py` de camada e que o smoke test exerce
  o esqueleto hexagonal (subpacotes `shared.*`/`features`).
- **Validar o DoD:** `make setup && make check && make test` verde em máquina limpa.

### Fora do escopo (explicitamente)

- Qualquer feature ou lógica de negócio (modelagem, métricas, ingestão).
- CI / GitHub Actions — Stage 1.2.
- Contratos `import-linter` / `.importlinter` / `tests/architecture/` — Stage 1.3. Em 1.1 a fitness
  function é **só** `scripts/check_layout.py`.
- Gate de cobertura `fail_under=90` — Stage 1.2.
- Identidade determinística / fingerprints (value objects + hasher) — Stage 1.4.
- Config tipada de projeto e tracking MLflow — Stage 1.5.
- Qualquer decisão humana 🤖 do ledger §B (a primeira só na Stage 1.4).

### Vínculo com o roadmap

Primeira Stage do **Step 1 — Fundação e fitness arquitetural**. Entrega a base que faltava ao
projeto anterior: repositório hexagonal com a direção de dependência já verificável por ferramenta,
e as decisões de fundação formalizadas como ADRs `accepted` consumidos por todas as Stages
seguintes. Fonte: `docs/roadmap.md` Stage 1.1; `docs/overview.md` §2, §7, §11.

## 2. Objetivo da Stage

Ao fim desta Stage, o repositório tem a **fundação hexagonal verificada por ferramenta** e as
**quatro decisões de fundação formalizadas como ADRs `accepted`** — `make setup && make check &&
make test` verde em máquina limpa, com o smoke test exercendo o esqueleto hexagonal e o excedente
herdado do template explicitamente tratado como débito declarado.

## 3. Contexto e premissas

### Contexto

O projeto é uma reconstrução greenfield (overview §2): o código anterior degradou em dívida
arquitetural por não enforçar a regra de dependência. Esta Stage estabelece a fundação *antes* de
qualquer código de negócio, materializando o ADR 0.0.0001 (hexagonal-from-day-one) com um gate
ativo (`check_layout.py`) e registrando as escolhas científicas/arquiteturais pré-decididas no
overview §11.

### Premissas

- O bootstrap do `whaka-dev-project-template` já entregou toolchain e estrutura funcionais; os
  gates `layout-check` e `smoke` já passam (verificado).
- O excedente do template não é feature de negócio — é plumbing herdado (premissa que sustenta a
  decisão D-1).
- As 4 decisões de fundação já foram ratificadas no overview §11; o ADR só materializa
  alternativas/trade-offs/reversibilidade, sem reabrir a deliberação (decisão D-2).

### Dependências

- Nenhuma (`depends_on: []`). É a primeira Stage do projeto.

## 4. Contratos

Stage de plumbing/fundação pura.

### Introduzidos

- **Contratos de código:** nenhum (`contratos_introduzidos: []`).
- **Contratos documentais** (decisões de fundação formalizadas como ADR `accepted`, consumidos por
  todas as Stages seguintes):
  - **`0.0.0002`** (`adr`) — enquadramento = calibração probabilística + contribuição de features,
    nunca acurácia pontual do retorno médio diário.
  - **`0.0.0019`** (`adr`) — hexagonal pleno enforçado por ferramenta (`check_layout.py` em 1.1;
    `import-linter` em 1.3); regra de dependência quebra o build.
  - **`0.0.0020`** (`adr`) — estatística como serviços de domínio puros sobre value objects
    (`PairedLossSeries`/`QuantileForecast`/`CoverageSeries`); libs (`arch`/`statsmodels`/`sklearn`/
    `scoringrules`/`MAPIE`) em adapters atrás de ports.
  - **`0.0.0021`** (`adr`) — testes de regressão por unidade + oráculo (fixture analítica + lib/R),
    nunca snapshot global byte-idêntico.
  - **`1.1.0001`** (`adr`, local) — tratamento do excedente do template como débito declarado (D-1).
- **Contrato de tooling herdado e estável:** `make check` = lint (ruff) + typecheck (mypy --strict)
  + layout-check (`check_layout.py`) + docs-check + test (pytest); `make setup` cria `.venv` via uv
  e instala hooks `pre-commit`/`commit-msg`.

### Consumidos

- **`0.0.0001`** — hexagonal-from-day-one (ADR global já presente). Esta Stage o materializa com um
  gate ativo. Nenhum contrato de código consumido (`contratos_consumidos: []`).

## 5. Invariantes e regras

- **I1 — Direção de dependência (gate `check_layout.py`):** `domain` não importa `application`/
  `adapters`/`infrastructure` nem `fastapi`/`sqlalchemy`/`pydantic`; `application` não importa
  `adapters`/`infrastructure` nem `fastapi`/`sqlalchemy`; `adapters/in` não importa `adapters/out`
  e vice-versa; `shared` não importa de `features`; cada feature tem `domain`/`application`/
  `adapters`.
- **I2 — Domínio puro:** `domain` é stdlib-only; proibido `pandas`/`pyarrow`/`torch`/`pydantic`/
  `sqlalchemy`. O enforce pleno (import-linter) chega na 1.3; em 1.1 não se introduz violação e o
  `check_layout.py` já cobre os imports proibidos do domínio.
- **I3 — Ponto único de wiring:** `composition_root.py` é o único lugar onde adapters concretos são
  instanciados.
- **I4 — Docstring de camada:** cada `__init__.py` de pacote/camada tem docstring de uma linha
  descrevendo a responsabilidade da camada.
- **I5 — ADRs em inglês, `accepted`:** ADRs de fundação escritos/consumidos em inglês, `status:
  accepted`, frontmatter conforme `docs/templates/adr.md` (`adr_id`, `decision`, `context_stage:
  1.1-bootstrap`); nome de arquivo `docs/adr/0_0_NNNN-<slug-en>.md` (global) ou `1_1_NNNN-...`
  (local).
- **I6 — Não retocar fundação existente:** `0_0_0000`, `0_0_0001` (hexagonal-from-day-one) e
  `0_0_0050` (autonomous-overnight-mode) **não** são editados.
- **I7 — Gate de saída (DoD):** `make setup && make check && make test` verde em máquina limpa; o
  smoke test importa `financial_forecasting` e o esqueleto hexagonal (`shared.{domain,application,
  infrastructure}`, `features`). Cobertura ≥ 90% **não** é gate em 1.1 (entra na 1.2).
- **I8 — Governança da corrida autônoma (ADR 0.0.0050):** proibido `git push` / `gh pr create` /
  `gh pr merge` / tocar `develop`|`main` / reescrever histórico — trabalho só na branch
  `feat/5-1-1-bootstrap`.
- **I9 — Commits:** Conventional Commits em PT, escopo ASCII/kebab, body em bullets, rodapé
  `Refs #5`, tag `[1.1/task-NN]` no subject; mensagens reservadas de gate (`conceptual approved` /
  `technical approved`) quando aplicável.

## 6. Casos de erro e exceções

- **C1 — `check_layout.py` falha (import proibido no domínio ou direção violada):** `make check`
  retorna ≠ 0; a Stage não pode ser marcada `done`. Tratamento: corrigir o import ou rotear via
  port antes de prosseguir.
- **C2 — Excedente do template viola domínio puro ou direção:** se algum módulo herdado importasse
  framework no domínio, `check_layout.py` pegaria (atualmente **não** ocorre). Tratamento previsto:
  inertizar/podar o módulo ofensor (ver D-1/ADR 1.1.0001).
- **C3 — `make test` retorna exit 5 (no tests collected):** o smoke test existe justamente para
  evitar isso; se removido, o gate quebra. Tratamento: manter ao menos o smoke test.
- **C4 — `__init__.py` de camada sem docstring (viola I4):** finding a corrigir na execução
  (os `__init__.py` de `shared.{domain,application,infrastructure}` e `features` estão vazios no
  bootstrap). Tratamento: adicionar docstring de uma linha por camada (task de execução).
- **C5 — Smoke test importa só o pacote raiz (não exerce o esqueleto, viola I7):** o
  `tests/test_smoke.py` atual importa apenas `financial_forecasting`. Tratamento: estender o smoke
  para importar os subpacotes do hexagonal (task de execução).
- **C6 — Referência quebrada a artefato de Stage futura (CI 1.2, import-linter 1.3):** introduzir
  link/menção a `.github/workflows`, `.importlinter` ou `tests/architecture/` como se já
  existissem. Tratamento: não referenciar artefatos de 1.2/1.3 como presentes.

## 7. Decisões técnicas relevantes

### D-1 — Tratamento do excedente herdado do template

- **O quê:** Manter o excedente do template (composition_root, main, `shared/infrastructure/
  {http,database,logging,clock,uuid_generator}`, `shared/domain/value_objects/pagination.py`,
  ports stub `clock`/`id_generator`, deps `fastapi`/`uvicorn`/`sqlalchemy`/`alembic`/`pydantic`)
  como **esqueleto inerte e débito declarado**; **não podar agora**. Garantir apenas que nada viole
  domínio puro nem a direção de import (já não viola). Poda/repurpose fica para a Stage que tocar
  cada módulo (1.5 config/composition root; storage para `database/`; API para `http/`).
- **Por quê:** Custo de podar agora é real e o ganho baixo — o template trouxe os módulos
  funcionais, os gates passam, e a stack obrigatória do `CLAUDE.md` (FastAPI/SQLAlchemy/Alembic) e a
  Stage 1.5 dependem desse esqueleto. O simples-e-trocável é declarar o débito. O non_goal da 1.1 é
  *features de negócio* — o excedente é plumbing, não feature. Evita HALT e mantém o DoD verde.
- **Fonte:** Roadmap Stage 1.1 (`arquivos_a_criar`, `non_goals`); `CLAUDE.md` (stack obrigatória);
  overview §11 (ADR 0.0.0022 Parquet+DuckDB motiva remoção futura do SQLAlchemy).
- **ADR:** [`../../adr/1_1_0001-template-surplus-handling.md`](../../adr/1_1_0001-template-surplus-handling.md)

### D-2 — Formalizar as 4 decisões de fundação como ADRs `accepted` sem re-deliberar

- **O quê:** Transcrever as 4 decisões pré-fechadas do overview §11 (`0_0_0002`, `0_0_0019`,
  `0_0_0020`, `0_0_0021`) para ADRs completos (Context/Decision/Alternatives/Consequences) em
  inglês, `status: accepted`, sem reabrir a decisão.
- **Por quê:** O overview §11 deixa claro que essas 4 escolhas são pré-decididas (não são decisões
  🤖 do ledger §B; a primeira 🤖 é só na 1.4). A política manda não fazer perguntas e registrar
  decisão não-trivial como ADR — aqui o ADR é o próprio entregável da Stage. Espelhar o estilo de
  `0_0_0001` mantém consistência grep-friendly.
- **Fonte:** `docs/overview.md` §11; `docs/autonomous-run-decision-ledger.md` §B; política de
  decisão do grounding.
- **ADR:** os próprios `0_0_0002`/`0_0_0019`/`0_0_0020`/`0_0_0021` (entregáveis).

### D-3 — Numeração do ADR local de débito

- **O quê:** Usar `docs/adr/1_1_NNNN-<slug>.md` (escopo da Stage) para o ADR de débito do excedente
  — `1_1_0001` — reservando a faixa `0_0_*` aos ADRs de fundação globais que o overview §11 já
  enumera.
- **Por quê:** Os `0_0_*` são fundação cross-project pré-enumerada (slots `0_0_0003..0_0_0026` já
  reservados no overview §11); misturar o débito local nessa faixa colidiria. A convenção
  (`CONVENTIONS.md` §1) aceita prefixo `N_M` para ADR de Stage.
- **Fonte:** `docs/CONVENTIONS.md` §1 (numeração de ADR); `docs/overview.md` §11 (slots reservados).
- **ADR:** não requer ADR próprio (decisão de convenção, sem alternativa material descartada).

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Excedente do template confunde leitores ("estrutura vazia" vs repo real) | M | B | ADR 1.1.0001 declara o débito; concept §1/§7 referencia |
| Smoke test fraco (só pacote raiz) deixa import quebrado do esqueleto passar | M | M | Estender smoke para subpacotes do hexagonal (I7/C5) |
| `__init__.py` de camada sem docstring (viola I4) passa despercebido | M | B | Corrigir na execução; finding registrado (C4) |
| Introduzir referência a artefato de 1.2/1.3 antecipando escopo | B | M | Revisão do README/concept (C6); non_goals explícitos |
| Podar excedente por engano quebra `make setup`/Stage 1.5 | B | A | D-1: não podar em 1.1; poda só na Stage consumidora |

## 11. Critérios de aceitação

- [ ] **A1** — Os 4 ADRs de fundação existem em `docs/adr/` (`0_0_0002`, `0_0_0019`, `0_0_0020`,
  `0_0_0021`), em inglês, com frontmatter válido (`status: accepted`, `adr_id` correto,
  `context_stage: 1.1-bootstrap`, `decision` em 1 frase) e corpo Context/Decision/Alternatives
  (incl. status quo)/Consequences derivado do overview §11.
- [ ] **A2** — O ADR local `1_1_0001` existe, `accepted`, registrando a decisão D-1 sobre o
  excedente do template, com alternativas (podar / wirar / não documentar) e justificativa.
- [ ] **A3** — `make setup && make check && make test` retorna exit 0 em máquina limpa
  (lint + mypy strict + `check_layout.py` + docs-check + pytest).
- [ ] **A4** — `check_layout.py` está verde: nenhum import proibido no domínio e direção de
  dependência respeitada (I1/I2), incluindo o excedente herdado.
- [ ] **A5** — Cada `__init__.py` de camada (`shared.{domain,application,infrastructure}`,
  `features`, raiz) tem docstring de uma linha (I4).
- [ ] **A6** — O smoke test importa `financial_forecasting` **e** os subpacotes do hexagonal
  (`shared.{domain,application,infrastructure}`, `features`) sem erro (I7).
- [ ] **A7** — ADRs de fundação já presentes (`0_0_0000`, `0_0_0001`, `0_0_0050`) **não** foram
  editados (I6).
- [ ] **A8** — Nenhuma referência a artefatos de Stage futura (CI/`.github`, `.importlinter`,
  `tests/architecture/`) introduzida como se já existisse (C6); cobertura ≥ 90% não é gate.
- [ ] **A9** — README referencia os 4 novos ADRs na seção de decisões/fundação, se houver tal seção.

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (Sim — só ADRs documentais; nenhum
  contrato de código.)
- [x] Toda decisão em §7 tem fonte rastreável? (Sim — overview/roadmap/CONVENTIONS/CLAUDE.md.)
- [x] Toda integração externa tem contrato definido? (N/A — sem integração externa nesta Stage.)
- [x] Decisões com alternativa real descartada têm ADR escrito? (Sim — D-1 → 1.1.0001; as 4 de
  fundação são os próprios entregáveis.)
- [x] Dependências de Stages anteriores estão satisfeitas? (Sim — `depends_on: []`.)
- [x] Stage cabe em ~3–8 Tasks? (Sim — 6 tasks no roadmap/brief.)
- [x] Riscos críticos têm mitigação plausível? (Sim — ver §10.)
- [x] O excedente do template está tratado sem violar domínio puro? (Sim — D-1 + `check_layout`
  verde.)

## 13. Questões em aberto

- Nenhuma. Decisões D-1/D-2/D-3 fechadas; nenhuma decisão humana 🤖 do ledger §B incide nesta Stage.

## 14. Referências

- [`../../overview.md`](../../overview.md) — §1, §2, §4, §6, §7, §11 (decisões de fundação).
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.1-bootstrap` e vizinhas (1.2–1.5).
- [`../../autonomous-run-decision-ledger.md`](../../autonomous-run-decision-ledger.md) — §B.
- ADRs desta Stage: [`../../adr/`](../../adr/) — `0_0_0002`, `0_0_0019`, `0_0_0020`, `0_0_0021`,
  `1_1_0001`; fundação consumida: `0_0_0001`.
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) §1/§2/§4; [`../../LAYOUT.md`](../../LAYOUT.md) §3;
  [`../../adr/0_0_0050-autonomous-overnight-mode.md`](../../adr/0_0_0050-autonomous-overnight-mode.md).
