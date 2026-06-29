---
title: Technical — Stage 1.3 — Contratos de arquitetura (import-linter)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, architecture-contracts, import-linter, fitness-function]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.3-architecture-contracts
stage_title: Contratos de arquitetura (import-linter)
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.2-ci-coverage]
concept_ref: ./concept.md
issue_id: 9
branch: feat/9-1-3-architecture-contracts
tasks_count: 6
---

# Technical — Stage 1.3 — Contratos de arquitetura (import-linter)

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [1.3/task-NN]`, body em bullets,
>    rodapé `Refs #9`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, decidir conforme a política da corrida autônoma (listar
>    opções, pesar trade-offs, decidir) e registrar em
>    [§7 Execução](#7-execução-post-hoc-editável-após-done) como
>    `[decision]`/`[finding]`/`[deviation]`. Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage).
>    O commit `stage 1.3: complete` e a marcação `done` no `roadmap.md`
>    **NÃO** são feitos aqui — são do **orquestrador**, após auditoria
>    independente.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/9-1-3-architecture-contracts` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo
Esta Stage encoda as regras de dependência de `docs/LAYOUT.md` §3/§6 como
contratos **import-linter** num arquivo `.importlinter` (INI, raiz,
`root_package = financial_forecasting`), torna esses contratos **efetivos no
gate** (`lint-imports` dentro de `make check` e garantido no `ci.yml`) e prova
por **quebra intencional revertida** que o domínio importando `pandas`
(ou `pyarrow`/`torch`/`pydantic`/`sqlalchemy`/`fastapi`) deixa o build vermelho.
É a **fitness function central** do Step 1: nenhum `Protocol`/value object/port
de domínio é criado; o único artefato-contrato é o de import/camadas, que
**espelha** o LAYOUT (fonte da verdade). Detalhes, invariantes (I1–I7) e
critérios de aceite (A1–A7) em [`concept.md`](./concept.md).

### Estratégia
**Stage de fundação/bootstrap** — não é vertical slice e não há domínio a
modelar, então a ordem padrão inside-out da skill `task-ordering-hex` **não se
aplica**. Ordem escolhida (declarada conforme a skill): **dependência de
ferramenta primeiro → contrato → integração no gate → regressão → evidência
de quebra revertida**. Razão:

1. Instalar `import-linter` no grupo `dev`/lock (Task 01) — sem a dep, o CLI
   `lint-imports` não existe (verificado: hoje `uv run lint-imports` falha
   `Failed to spawn`).
2. Escrever `.importlinter` e validar **0 broken** no estado atual, sem
   reprovar o esqueleto inerte (F2) nem a fronteira composition_root (Task 02).
3. Plugar no gate: alvo `lint-imports` em `make check` + garantir no `ci.yml`
   (Task 03) — só faz sentido depois que o contrato passa verde.
4. Teste de regressão em `tests/architecture/` (Task 04) — protege contra
   afrouxamento/remoção do `.importlinter` e prova detecção via config
   temporária (sem mutar a árvore real).
5. Provar a quebra intencional revertida na prática e registrar a evidência
   na §7 (Task 05) — DoD central (A3), sem deixar lixo no repo.
6. Fechar o ADR `1.3.0001` em `accepted` cobrindo D1/D2 (Task 06) — o arquivo
   já existe no repo; a Task confirma/ajusta `status` e alternativas pesadas.

Cada Task deixa o build verde: o contrato é validado verde (Task 02) antes de
virar gate (Task 03); o teste de regressão (Task 04) só roda contra um contrato
já provado.

### Pré-condições
- Stage `1.2-ci-coverage` em `done` (CI já invoca `make check`; gate de
  cobertura ≥90% no lugar).
- Branch `feat/9-1-3-architecture-contracts` em checkout.
- `docs/LAYOUT.md` existe e é a fonte da verdade (NÃO recriar — D4 do concept).

### Premissas técnicas
- Python 3.12, `uv`, `pyproject.toml` e `uv.lock` já existem.
- `import-linter` ainda **não** está instalado (`uv run lint-imports` falha
  hoje); Task 01 resolve.
- A fronteira composition_root é real: `shared/infrastructure/http/app.py:22`
  importa `financial_forecasting.composition_root`; `composition_root.py` ainda
  **não** importa `features.*.adapters` (features vazias), mas o `ignore_imports`
  já cobre esse caminho futuro (verbatim do LAYOUT §6, linhas 222–229).
- `features/` só tem `__init__.py`; `shared/adapters/` não existe — contratos
  devem tolerar camadas/módulos ausentes (F2, invariante I7, caso C5).

### Estrutura de pastas afetada

```
financial-forecasting/
├── .importlinter                      # NOVO (raiz, INI)
├── pyproject.toml                     # MOD (dev: import-linter)
├── uv.lock                            # MOD (pin)
├── Makefile                           # MOD (alvo lint-imports + check)
├── .github/workflows/ci.yml           # MOD (garantia explícita do contrato)
├── docs/
│   ├── stages/1.3-architecture-contracts/
│   │   └── technical.md               # §7 preenchida na execução
│   └── adr/
│       └── 1_3_0001-import-linter-as-architecture-fitness-function.md  # status: accepted
└── tests/
    └── architecture/
        ├── __init__.py                # NOVO
        └── test_import_contracts.py   # NOVO
```

## 2. Tasks

> Faixa saudável: **3–8 Tasks por Stage**. Esta Stage tem **6 Tasks**.

### Task 01 — Adicionar `import-linter` ao grupo `dev` e fixar no lock

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `pyproject.toml` (grupo `[project.optional-dependencies].dev`)
  - `uv.lock`
- **O que fazer:**
  Adicionar `import-linter>=2.0` ao grupo `dev` do `pyproject.toml` (junto de
  ruff/mypy/pre-commit) e regenerar o lock (`uv lock` / `uv sync --extra dev`)
  para fixar a versão. Sem `.importlinter` ainda (vem na Task 02): apenas a
  dependência e o CLI disponíveis.
- **Detalhes técnicos:**
  - `import-linter` expõe o entrypoint `lint-imports` (exit ≠ 0 em violação).
  - Não tocar em deps de runtime (`[project].dependencies`).
- **Critério de aceite:**
  - `uv run lint-imports --help` executa (exit 0) — antes falhava
    `Failed to spawn`.
  - `import-linter` presente no `uv.lock`.
- **Comando de verificação:**
  ```bash
  uv sync --extra dev
  uv run lint-imports --help
  grep -n "import-linter" pyproject.toml uv.lock
  ```
- **Commit sugerido:** `chore(deps): adicionar import-linter ao grupo dev [1.3/task-01]`

---

### Task 02 — Criar `.importlinter` espelhando o LAYOUT (0 broken no estado atual)

- **Arquivos a criar:**
  - `.importlinter`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Escrever `.importlinter` (INI) na raiz com `root_package =
  financial_forecasting` e os contratos que espelham `docs/LAYOUT.md` §3/§6:
  - **`layers`** (`hexagonal-layers`) — direção `adapters > application >
    domain` no container `shared` (e replicável por feature à medida que
    surgirem), com `containers` e `exhaustive = False` para tolerar camadas
    ausentes/inertes (F2/I7/C5). Modelar `shared.domain` e
    `shared.application` como camadas inward; **não** listar layers de feature
    inexistente.
  - **`forbidden`** `domain-purity` — `*.domain` e `shared.domain` proibidos de
    importar `pandas`, `pyarrow`, `torch`, `pydantic`, `sqlalchemy`, `fastapi`
    (DoD central — LAYOUT linha 104).
  - **`forbidden`** `inward-only` — `*.application`/`shared.application`
    proibidos de importar `*.adapters`/`shared.infrastructure`; `*.domain`/
    `shared.domain` proibidos de importar `*.application`/`*.adapters`/
    `shared.infrastructure` (LAYOUT linhas 94/110).
  - **`forbidden`** `shared-no-features` — `shared.*` proibido de importar
    `features.*` (LAYOUT linha 244).
  - **`ignore_imports`** (no contrato/contratos pertinentes) — exceção verbatim
    da fronteira composition_root: `...shared.infrastructure.http.app ->
    ...composition_root` e `...composition_root -> ...features.*.adapters`
    (LAYOUT §6, linhas 222–229).
- **Detalhes técnicos:**
  - Usar caminhos absolutos `financial_forecasting.*` em todos os módulos.
  - `forbidden_modules`/`source_modules` devem refletir a estrutura modular
    real; usar wildcards (`financial_forecasting.*.domain`) onde import-linter
    suportar, ou listar `shared.domain` explicitamente.
  - **Não** criar contrato `independence` (features×features) — desnecessário
    com `features/` vazio (D2 do concept).
  - Em caso de divergência LAYOUT × contrato, **LAYOUT vence** (I6) — ajustar o
    contrato, nunca o LAYOUT.
- **Critério de aceite:**
  - `uv run lint-imports` retorna **0 broken** no estado atual (A2): não
    reprova esqueleto inerte (F2) nem a fronteira composition_root (C4).
  - Saída lista os contratos `hexagonal-layers`, `domain-purity`,
    `inward-only`, `shared-no-features` como `KEPT`.
- **Comando de verificação:**
  ```bash
  uv run lint-imports
  uv run lint-imports --verbose
  ```
- **Commit sugerido:** `feat(arch): adicionar contratos import-linter espelhando LAYOUT [1.3/task-02]`

---

### Task 03 — Plugar `lint-imports` no gate (`make check` + `ci.yml`)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `Makefile` (novo alvo `lint-imports`; incluí-lo na cadeia `check`)
  - `.github/workflows/ci.yml` (garantia explícita de que o contrato roda)
- **O que fazer:**
  Criar alvo Make `lint-imports` (`uv run lint-imports`) e adicioná-lo à lista
  de dependências do alvo `check` (hoje `lint typecheck layout-check docs-check
  test`). Atualizar `.PHONY`, o bloco de `help` e o comentário do `check`.
  No `ci.yml`, tornar **explícito** que o contrato roda no CI — o job já chama
  `make check`; ajustar o nome/descrição do step para citar `import-linter`
  (e, se desejado como defesa extra, um step dedicado `uv run lint-imports`).
- **Detalhes técnicos:**
  - Ordem em `check`: rodar `lint-imports` antes de `test` é barato e falha
    cedo. Sugestão: `check: lint typecheck layout-check lint-imports docs-check
    test` (posição não é crítica; objetivo é estar na cadeia bloqueante — I5).
  - `lint-imports` complementa `check_layout.py` (não substitui): ele cobre o
    caminho indireto da fronteira que o script não enxerga (D3 do concept).
- **Critério de aceite:**
  - `make lint-imports` executa o contrato e sai 0 no estado atual.
  - `make check` inclui e executa `lint-imports` e fica **verde** (A4).
  - `ci.yml` cita explicitamente `import-linter` no gate (step name/descrição
    e/ou step dedicado).
- **Comando de verificação:**
  ```bash
  make lint-imports
  make check
  grep -n "lint-imports\|import-linter" Makefile .github/workflows/ci.yml
  ```
- **Commit sugerido:** `build(make): integrar lint-imports ao gate check e ci [1.3/task-03]`

---

### Task 04 — Teste de regressão dos contratos em `tests/architecture/`

- **Arquivos a criar:**
  - `tests/architecture/__init__.py`
  - `tests/architecture/test_import_contracts.py`
- **Arquivos a modificar:** nenhum
- **O que fazer:**
  Criar teste de regressão que (a) exige `lint-imports` **exit 0** no estado
  atual do repo (`subprocess` chamando `uv run lint-imports` ou a API
  `importlinter.api.lint_imports`); e (b) prova que um import proibido é
  **detectado** — via **config temporária** que aponta `root_package` para um
  módulo-fixture proibido criado em `tmp_path` (NÃO mutar a árvore real),
  esperando exit ≠ 0 / contrato `broken`. Adicionar uma asserção que o teste
  falha se o `.importlinter` for removido/afrouxado (ex.: checar que os nomes
  de contrato esperados estão presentes no `.importlinter`).
- **Detalhes técnicos:**
  - Preferir a API pública do import-linter (`read_user_options`,
    `create_report`) para o caso (b), apontando para uma config sintética; ou
    `subprocess.run(["uv","run","lint-imports","--config", <tmp_ini>])`.
  - Marcar como `unit` ou `slow` conforme o tempo; manter determinístico e sem
    rede.
  - O caso (a) é a guarda contra "contrato verde por acaso"; o caso (b) é a
    guarda contra "contrato que aprova tudo" (anti-example da skill).
- **Critério de aceite:**
  - `pytest tests/architecture/test_import_contracts.py -v` passa (A5).
  - O teste detecta um import proibido em config sintética (exit ≠ 0 / broken).
  - O teste falha se `.importlinter` perder um dos contratos esperados (C6).
  - Cobertura global ≥90% mantida (não introduzir código de produção sem teste).
- **Comando de verificação:**
  ```bash
  pytest tests/architecture/test_import_contracts.py -v
  make test
  ```
- **Commit sugerido:** `test(arch): regressão dos contratos import-linter [1.3/task-04]`

---

### Task 05 — Provar quebra intencional revertida e registrar evidência (DoD central)

- **Arquivos a criar:** nenhum
- **Arquivos a modificar:**
  - `docs/stages/1.3-architecture-contracts/technical.md` (apenas §7, dentro dos
    marcadores `BEGIN/END: post-execution`)
- **O que fazer:**
  Executar a prova manual do DoD central (A3): inserir temporariamente
  `import pandas` em um módulo de `shared/domain/` (ex.:
  `value_objects/pagination.py`), rodar `uv run lint-imports` e **confirmar exit
  ≠ 0** pelo contrato `domain-purity`; **reverter** e confirmar volta a **0
  broken**. Registrar a evidência (saída resumida, antes/depois) como entrada
  `[decision]`/`[deviation]` ou nota de execução na §7 deste technical.
  **Nenhuma mudança de código de produção permanece** — a mutação é revertida
  integralmente.
- **Detalhes técnicos:**
  - Este é o único Task cujo "entregável" é evidência documentada, não código.
  - Garantir `git status` limpo (fora da §7) ao final.
  - A §7 é a **única** seção editável após `status: done`; este Task escreve
    ali. O frontmatter `updated_at` **não** muda por edição na §7.
- **Critério de aceite:**
  - Evidência da quebra revertida registrada na §7 (saída com `domain-purity`
    `BROKEN` durante a mutação e `0 broken` após reverter).
  - `uv run lint-imports` volta a **0 broken**; `git diff` mostra somente a §7
    alterada.
- **Comando de verificação:**
  ```bash
  uv run lint-imports          # deve voltar a "0 broken" após reverter
  git status --porcelain       # só docs/stages/.../technical.md (se editado)
  ```
- **Commit sugerido:** `docs(arch): registrar prova de quebra revertida do domain-purity [1.3/task-05]`

---

### Task 06 — Confirmar ADR `1.3.0001` em `accepted`

- **Arquivos a criar:** nenhum (arquivo já existe no repo)
- **Arquivos a modificar:**
  - `docs/adr/1_3_0001-import-linter-as-architecture-fitness-function.md`
    (se necessário ajustar `status`/conteúdo)
- **O que fazer:**
  Revisar o ADR `1.3.0001` e garantir: `status: accepted`; cobre **D1**
  (`.importlinter` standalone vs `[tool.importlinter]` no `pyproject`) e **D2**
  (tipos `layers` + `forbidden` vs `independence`) com as alternativas pesadas
  e razão concreta (repo antigo 23/36 arquivos, LAYOUT, roadmap). Alinhar ao
  template `docs/templates/adr.md`. Só commitar se houver mudança real; se já
  estiver correto e `accepted`, registrar isso como `[deviation]` na §7 e
  pular o commit desta Task.
- **Detalhes técnicos:**
  - Não criar ADR novo; o slug e o número já existem.
  - Conferir frontmatter conforme `CONVENTIONS.md` §2/§3.
- **Critério de aceite:**
  - ADR em `status: accepted`, cobrindo D1 e D2 com alternativas (A7).
  - Consistente com `concept.md` §7 e §14.
- **Comando de verificação:**
  ```bash
  grep -n "status:" docs/adr/1_3_0001-import-linter-as-architecture-fitness-function.md
  make docs-check
  ```
- **Commit sugerido:** `docs(adr): aceitar 1.3.0001 import-linter como fitness function [1.3/task-06]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 1.3: complete` (feito pelo **orquestrador**, não nesta sessão) e ser
> mergeada em `develop`.

### Verificações automatizadas
```bash
make check                 # lint + typecheck + layout-check + lint-imports + docs-check + test
uv run lint-imports        # 0 broken no estado atual
pytest tests/architecture/ # teste de regressão dos contratos
```

### Verificações funcionais
- [ ] `uv run lint-imports` retorna **0 broken** no estado atual — não reprova
      esqueleto inerte (F2) nem a fronteira composition_root (A2/I7/C4/C5).
- [ ] Inserir `import pandas` em `shared/domain/value_objects/pagination.py`
      faz `uv run lint-imports` retornar exit ≠ 0 pelo `domain-purity`; após
      reverter, volta a 0 broken (A3, evidência na §7).
- [ ] `make check` inclui e executa `lint-imports` e fica verde; `ci.yml`
      cita o contrato explicitamente (A4).

### Mapping invariante ↔ teste/evidência (gate de saída)

| Invariante (concept §5) | Como é garantido | Verificação |
|---|---|---|
| **I1** Domínio puro (`domain` ⊬ pandas/pyarrow/torch/pydantic/sqlalchemy/fastapi) | `forbidden:domain-purity` no `.importlinter` | A3 quebra revertida (§7) + `test_import_contracts` caso (b) |
| **I2** Direção outside-in (`adapters→application→domain`) | `layers:hexagonal-layers` + `forbidden:inward-only` | `uv run lint-imports` 0 broken + `test_import_contracts` caso (a) |
| **I3** Shared não importa de features | `forbidden:shared-no-features` | `uv run lint-imports` 0 broken |
| **I4** Exceção única composition_root | `ignore_imports` verbatim (LAYOUT §6) | `lint-imports` 0 broken (fronteira não reprova) — C4 |
| **I5** Gate efetivo | alvo `lint-imports` em `make check` + `ci.yml` | `make check` verde (Task 03) + A3 |
| **I6** LAYOUT é a fonte | contrato espelha LAYOUT §3/§6; ADR 1.3.0001 | revisão Task 02/06 |
| **I7** Sem reprovar excedente inerte | `layers` com `exhaustive=False`/containers tolerantes | `uv run lint-imports` 0 broken no estado atual (F2) — C5 |

### Checklist de fechamento da Stage
- [ ] Todas as 6 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch (inclui `lint-imports`)
- [ ] Quebra intencional revertida provada e registrada na §7 (A3)
- [ ] `tests/architecture/test_import_contracts.py` passa (A5)
- [ ] ADR `1.3.0001` em `status: accepted` cobrindo D1/D2 (A7)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
- [ ] **NÃO** feito aqui: commit `stage 1.3: complete` e marcação `done` no
      `roadmap.md` — responsabilidade do **orquestrador** pós-auditoria

## 4. Ordem de dependência entre Tasks

Ordem estritamente linear (fundação/bootstrap, não vertical slice):

```
Task 01 (dep import-linter)
   └─► Task 02 (.importlinter, 0 broken)
          └─► Task 03 (gate: make check + ci.yml)
                 └─► Task 04 (teste de regressão)
                        └─► Task 05 (prova de quebra revertida → §7)
                               └─► Task 06 (ADR accepted)
```

- Task 02 depende de 01 (CLI precisa existir).
- Task 03 depende de 02 (só vira gate depois de verde).
- Task 04 depende de 03 (o teste assume o contrato no gate).
- Task 05 depende de 02–04 (prova o DoD sobre o contrato já plugado e testado).
- Task 06 pode rodar a qualquer momento após 02 (depende só da decisão
  D1/D2 já tomada); posicionada por último para fechar a evidência documental.

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| Contrato `layers` quebra por module/layer ausente (skeleton inerte, F2) | Modelar `layers` com `containers` + `exhaustive = False`; validar 0 broken antes de commitar (Task 02). Se persistir, trocar `layers` por `forbidden` direcionais equivalentes e registrar `[deviation]` na §7 |
| `layers` não expressa bem a base inward (`shared.domain`/`shared.application`) | Cobrir a direção via `forbidden:inward-only` (já previsto) como rede de segurança; `layers` foca em `adapters>application>domain` |
| Wildcards (`*.domain`) não suportados como esperado pelo import-linter | Listar módulos explicitamente (`shared.domain`, e cada `features.<f>.domain` quando existir); registrar `[deviation]` |
| `ignore_imports` da fronteira reprova ou não casa o caminho | Conferir caminho verbatim em `app.py:22`/`composition_root`; ajustar `ignore_imports` ao caminho real (LAYOUT §6 linhas 222–229) — C4 |
| Teste de regressão flaky por `subprocess`/ambiente | Preferir API pública do import-linter (`importlinter.api`) sobre `subprocess`; manter fixture em `tmp_path` |
| ADR `1.3.0001` divergir do concept | LAYOUT/concept vencem; ajustar ADR (Task 06) |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage (escopo, I1–I7, A1–A7,
  D1–D4)
- [`../../overview.md`](../../overview.md) — §6 (import-linter espelha LAYOUT),
  §7 (enforcement-as-test), §11 (ADRs `0_0_0019`–`0_0_0021`)
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.3-architecture-contracts`
- [`../../LAYOUT.md`](../../LAYOUT.md) — §3 (direção, linhas 94/104/110), §6
  (fronteira composition_root, linhas 222–229), §7 (linha 244) — **fonte da
  verdade**
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status,
  frontmatter
- ADRs desta Stage: [`../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md);
  fundação `0_0_0019`, `1_2_0011`
- Skills aplicáveis: `import-linter-rules`, `task-ordering-hex`
- Repo antigo (exemplo negativo): `/home/marcelo/Code/financial-time-series-forecasting`
  (`src/domain/services/dataset_quality_gate.py:1`, `holm_family_6.py:3`)

## 7. Execução (post-hoc, editável após done)
<!-- BEGIN: post-execution -->

> Preenchida durante/após a **Fase 4**. **Apenas esta seção é editável
> após `status: done`** — alterações fora dos marcadores
> `BEGIN/END: post-execution` são rejeitadas no Passo 10 do
> [`RUNBOOK-STAGE-LIFECYCLE.md`](../../RUNBOOK-STAGE-LIFECYCLE.md) via
> `scripts/check_technical_postexec.py`. O frontmatter `updated_at`
> **não muda** com edições aqui — cada entrada carrega data + autor.
> Seção pode estar vazia se a execução não produziu notas relevantes.
>
> **Regra de pergunta antes da nota.** Em corrida autônoma, decidir conforme a
> política da corrida (listar opções, pesar trade-offs com base concreta,
> decidir simples-e-trocável) e registrar a entrada abaixo. Não propagar
> silenciosamente.

**Formato de cada entrada** (ADR-like, ordem cronológica):

```markdown
### YYYY-MM-DD — [tag] escopo — Autor
**Contexto:** <o que foi encontrado durante a execução>
**Pergunta:** <o que precisava ser decidido>            <!-- só [decision] -->
**Opções:**                                              <!-- só [decision] -->
- A — <descrição>
- B — <descrição> ✅ recomendada
**Decisão:** B                                           <!-- só [decision] -->
**Razão:** <por que>
```

- `[decision]` — algo não previsto foi decidido durante a execução.
  Inclui pergunta, opções, decisão, razão.
- `[finding]` — gap/observação a tratar em **próxima Stage**; corpo
  inclui "direção sugerida" e Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original; corpo
  diz o que mudou e por que ficou abaixo do threshold de perguntar.

### 2026-06-29 — [deviation] task-02 — Claude (autonomous run)
**Contexto:** ao escrever o `.importlinter` (Task 02), o `ignore_imports` da
fronteira composition_root inclui o leg futuro
`composition_root -> features.**`, que ainda **não casa** nenhum import (o
`features/` só tem `__init__.py`). O import-linter emite alerta de "ignored
import não casado" para esse leg.
**O que mudou:** adicionei `unmatched_ignore_imports_alerting = none` **apenas**
ao contrato `shared-no-features`, e deixei o caminho verbatim da fronteira
(LAYOUT §6, 222–229) documentado desde já.
**Razão:** o leg só passa a casar quando a 1ª feature ganhar um adapter wireado
pelo composition_root; até lá o alerta é ruído (não viola nada). A presença do
caminho documenta a exceção e evita reescrever o contrato depois. Reversível e
abaixo do threshold de perguntar (ajuste de configuração, sem mudar a regra).
Quando o caminho existir e quisermos detectar "exceção morta", basta remover o
`none`. Demais contratos mantêm o alerting padrão.

### 2026-06-29 — [deviation] task-02 — Claude (autonomous run)
**Contexto:** o `lint-imports` cria o diretório de cache `.import_linter_cache/`
na raiz, não previsto em `arquivos_a_criar`.
**O que mudou:** adicionei `.import_linter_cache/` ao `.gitignore` (junto de
`.ruff_cache/`/`.mypy_cache/`/`.pytest_cache/`).
**Razão:** cache de ferramenta não entra em VCS; consistente com os demais
caches já ignorados. Mudança trivial, reversível, em suporte direto à Task 02.

### 2026-06-29 — [decision] task-02 — Claude (autonomous run)
**Contexto:** a lista `forbidden_modules` do `domain-purity` precisava cobrir o
DoD (`pandas`/`pyarrow`/`torch`) + framework (`pydantic`/`sqlalchemy`/`fastapi`,
LAYOUT linha 104). O repo antigo importava também `numpy` no "domínio".
**Pergunta:** incluir `numpy` na lista de proibidos do domínio?
**Opções:**
- A — proibir só o conjunto literal do LAYOUT/concept (sem `numpy`)
- B — incluir `numpy` como defesa em profundidade ✅ recomendada
**Decisão:** B
**Razão:** no repo de referência o apodrecimento veio de `pandas`/`numpy`/`torch`
juntos (ex.: `holm_family_6.py:3`). `numpy` é vetor de cálculo numérico que não
pertence ao domínio puro (a estatística vive no domínio como serviço puro sobre
value objects, mas o cálculo numérico mora em adapters — ADR 0.0.0020). Incluir
`numpy` é barato e fecha o vetor exato que sangrou antes; não diverge do LAYOUT
(que lista o conjunto como exemplos não-exaustivos de "libs de framework").
LAYOUT permanece a fonte; se um dia uma exceção legítima a `numpy` no domínio
surgir, o contrato é afrouxado com justificativa (improvável).

### 2026-06-29 — [decision] task-04 — Claude (autonomous run)
**Contexto:** o teste de regressão precisava (a) exigir 0 broken no repo real e
(b) provar detecção de import proibido sem mutar a árvore real. O technical
sugeria `subprocess` OU a API pública.
**Pergunta:** `subprocess.run(["uv","run","lint-imports"])` ou a API pública?
**Opções:**
- A — `subprocess` chamando o CLI
- B — `importlinter.cli.lint_imports(config_filename=...)` (API pública) ✅
**Decisão:** B
**Razão:** `importlinter.api` 2.12 não expõe `lint_imports`; a função pública é
`importlinter.cli.lint_imports`, que retorna o exit code `int` (0/1) e aceita
`config_filename`/`limit_to_contracts`/`no_cache`. Evita dependência do PATH e
do spawn do `uv` dentro do pytest (mais determinístico, sem flakiness de
ambiente — risco listado em §5). O caso (b) usa um pacote-fixture sintético em
`tmp_path` proibindo `json` (stdlib, sem instalar nada), provando que um
`forbidden` realmente quebra.

### 2026-06-29 — prova de quebra intencional revertida (DoD central A3) — Task 05
**Contexto:** verificação manual do DoD central (concept A3 / invariante I1):
domínio importando `pandas` deve deixar o build vermelho pelo contrato
`domain-purity`, e a reversão deve voltar a 0 broken sem deixar lixo.
**Procedimento:** injetei `import pandas` na linha 1 de
`src/financial_forecasting/shared/domain/value_objects/pagination.py`, rodei
`uv run lint-imports --no-cache`, e revertei.

**Saída (resumida):**

```
=== BASELINE (antes) ===
Contracts: 4 kept, 0 broken.

=== COM 'import pandas' em shared/domain/value_objects/pagination.py ===
Domain puro — sem pandas/pyarrow/torch/pydantic/sqlalchemy/fastapi BROKEN
Contracts: 3 kept, 1 broken.
financial_forecasting.shared.domain is not allowed to import pandas:
-   financial_forecasting.shared.domain.value_objects.pagination -> pandas (l.1)
exit = 1

=== APÓS REVERTER ===
Contracts: 4 kept, 0 broken.
exit = 0
git status --porcelain  ->  (vazio: nenhum código de produção alterado)
```

**Resultado:** A3 satisfeito. `domain-purity` quebra o build (exit 1) quando o
domínio importa `pandas`; após reverter, `0 broken` (exit 0). Nota: o
import-linter detectou `pandas` **estaticamente** pelo grafo de imports — nem
precisa estar instalado. Nenhuma mudança de produção permaneceu (`git status`
limpo fora desta §7). A mesma prova roda automatizada no caso (b) de
`tests/architecture/test_import_contracts.py` (sem mutar a árvore real).

### 2026-06-29 — [deviation] task-06 — Claude (autonomous run)
**Contexto:** a Task 06 manda confirmar o ADR `1.3.0001` em `accepted`,
commitando só se houver mudança real.
**O que mudou:** nada — o ADR já estava `status: accepted`, com frontmatter
conforme `docs/templates/adr.md` (todos os campos: `adr_id`, `decision`,
`context_stage` etc.), cobrindo **D1** (`.importlinter` standalone vs
`[tool.importlinter]`, Alternative A) e **D2** (`layers` + `forbidden` vs
`independence`, Alternatives B/C) com razão concreta (repo antigo 23/36
arquivos, LAYOUT §3/§6/§7, roadmap). Consistente com `concept.md` §7 (D1/D2).
**Razão:** o ADR foi autorado na Fase 3 e não precisou de retoque; o `numpy`
adicionado ao `domain-purity` (decision task-02 acima) é defesa em profundidade
aditiva que não contradiz o ADR (que lista o conjunto como exemplos de "data/ML
libs" e "framework libs"). Sem mudança real => commit da Task 06 pulado (A7
satisfeito sem edição).

### 2026-06-29 — [finding] task-04-extra (auditoria de testes) — Claude (autonomous run)
**Contexto:** na auditoria de testes da Stage, a análise por mutação revelou um
gap real no `tests/architecture/test_import_contracts.py`. A suíte cobria
"contrato verde por acaso" e "contrato que aprova tudo" (config sintética em
`tmp_path`), mas **não** cobria o terceiro modo de falha de gate míope:
**`source_modules` mirando o alvo errado**. Mutação verificada: trocar
`source_modules` de `domain-purity` de `shared.domain` para `shared.application`
(módulo real, mas que não importa libs proibidas). Com essa mutação aplicada e
um módulo de domínio real importando `pandas`, **as 9 asserções originais
continuavam verdes** — exatamente o falso-verde que a Stage existe para barrar
(DoD central A3/C1). O caso (b) sintético prova que "um `forbidden` quebra em
tese", mas nunca exercita o `.importlinter` de PRODUÇÃO contra a árvore real, e
`test_real_repo_has_zero_broken_contracts` segue verde porque o repo real está
limpo. A prova manual da A3 (Task 05) cobre isso uma vez, mas não roda no CI.
**O que foi adicionado:** `test_production_contract_reacts_to_real_violation`
(parametrizado em 2 casos: domínio importando `pandas` ⇒ `domain-purity` broken;
`shared` importando um módulo real de `features` ⇒ `shared-no-features` broken).
Injeta o módulo-violação na árvore de produção, roda o `.importlinter` REAL com
`limit_to_contracts`, exige exit != 0, e limpa em `finally` (incluindo
`__pycache__`). Mais `test_real_repo_clean_after_injection_fixture` como sanidade
de que o cleanup não deixou resíduo. Verificado: as duas mutações míopes
(`domain-purity` e `shared-no-features` apontando `source_modules` para o alvo
errado) agora **falham** o teste novo, enquanto as demais seguem verdes —
poder de matar mutante confirmado. Automatiza A3/C1/C3 (concept §6) no gate.
**Direção sugerida:** ao adicionar contratos `forbidden` em Stages futuras
(ex.: regras por bounded context na 1.4+), estender `_REAL_VIOLATION_CASES` com
a violação real correspondente, mantendo a fitness function imune a drift de
`source_modules`. Commit: `test(arch): cobrir contrato míope via violação real
injetada [1.3/task-04-extra]`.

### 2026-06-29 — [deviation] F1 (comentário do .importlinter) — orquestrador pós-auditoria
**Contexto:** A stage-audit (F1) verificou empiricamente que `include_external_packages = True` é
FUNCIONALMENTE OBRIGATÓRIA — sem ela o `import-linter` aborta ("must have
include_external_packages=True when there are external forbidden modules"), pois o contrato
domain-purity lista forbidden_modules externos (pandas/torch/etc.). O comentário antigo (linhas
20-22) atribuía a flag a um mecanismo de alerta de `ignore_imports` morto, que na verdade é
governado por `unmatched_ignore_imports_alerting`.
**Razão:** Corrigido o comentário para refletir o motivo real (conceito "Rastro perdido"), evitando
desorientar o próximo mantenedor. Mudança de comentário apenas; `lint-imports` segue 4 kept / 0
broken; `make check` verde.

<!-- END: post-execution -->
