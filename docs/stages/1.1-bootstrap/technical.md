---
title: Technical — Stage 1.1 — Bootstrap
description: Plano de execução da fundação hexagonal (ADRs de fundação, docstrings de camada, smoke do esqueleto, refs no README) com gate check_layout + smoke; sem feature de negócio
when-use: Consultar durante a Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, bootstrap, hexagonal, adr, check-layout, smoke, fundacao]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.1-bootstrap
stage_title: Bootstrap
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: []
concept_ref: ./concept.md
issue_id: 5
branch: feat/5-1-1-bootstrap
tasks_count: 5
---

# Technical — Stage 1.1 — Bootstrap

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [1.1/task-NN]`, body em bullets, rodapé `Refs #5`.
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage 1.1: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/5-1-1-bootstrap` (ver `CONVENTIONS.md` §4). Não há sub-PRs internos.
> Governança da corrida autônoma (ADR `0.0.0050`): proibido `git push` /
> `gh pr create` / `gh pr merge` / tocar `develop`|`main` / reescrever histórico.

## 1. Contexto e estratégia de execução

### Resumo
Stage de **fundação/bootstrap pura**: não há código de negócio. Entrega (a) os
**4 ADRs de fundação** (`0_0_0002`, `0_0_0019`, `0_0_0020`, `0_0_0021`) + o ADR
local de débito (`1_1_0001`), derivados do overview §11; e (b) o fechamento das
invariantes de esqueleto hexagonal pendentes no template — **docstring de camada**
(I4/C4) em cada `__init__.py` de camada e **smoke test que exerce o esqueleto**
(I7/C5). O gate de fitness desta Stage é **somente** `scripts/check_layout.py`
(+ smoke); CI (1.2), import-linter (1.3) e cobertura `fail_under=90` (1.2) estão
**fora de escopo**.

### Estratégia
**Não é vertical slice** — a ordem inside-out de `task-ordering-hex` não se aplica
(não há `domain → application → adapters` a construir). Conforme a tabela de
exceções da skill (`Foundation / bootstrap`), a ordem é dirigida pelos
**entregáveis e invariantes**, não pelo grafo de dependência: primeiro os ADRs
(entregável documental que sustenta toda a Stage), depois o fechamento das
invariantes de esqueleto (docstrings I4, smoke I7), depois a referência no README
(A9) e por fim a validação do DoD (I7/A3). Cada Task deixa `make check` verde e é
revertível isoladamente. **O excedente do template não é tocado** (D-1 / ADR
`1_1_0001`): só se valida que não viola domínio puro nem direção (`check_layout`).

Os 5 ADrs já foram autorados na Fase 3A (conceptual): a Task 01 **verifica** que
estão completos e válidos (frontmatter + corpo Context/Decision/Alternatives/
Consequences) — se algum estiver incompleto, completá-lo é parte da Task; se já
estiverem 100% válidos, a Task confirma e não há diff de conteúdo de ADR, só o
registro de verificação no commit das refs (Task 04).

### Pré-condições
- Branch `feat/5-1-1-bootstrap` em checkout (já criada pelo orquestrador).
- Bootstrap do `whaka-dev-project-template` aplicado: toolchain (uv/ruff/mypy
  strict/pytest), `Makefile`, `scripts/check_layout.py` e esqueleto `src/` presentes.
- `make setup` executável em máquina limpa (`.venv` via uv).

### Premissas técnicas
- Python 3.12, `pyproject.toml` já existe (uv + ruff + mypy strict + pytest).
- `make check` = `lint typecheck layout-check docs-check test`; `make test` roda pytest.
- `check_layout.py` e `tests/test_smoke.py` já passam no estado atual (verificado).
- Os `__init__.py` de `shared.{domain,application,infrastructure}` e `features`
  estão **vazios** (sem docstring) no bootstrap.

### Estrutura de pastas afetada

```
docs/adr/
├── 0_0_0002-probabilistic-calibration-framing.md      # verificar/completar
├── 0_0_0019-hexagonal-enforced.md                     # verificar/completar
├── 0_0_0020-statistics-in-domain-over-value-objects.md# verificar/completar
├── 0_0_0021-per-unit-contract-tests-with-oracle.md    # verificar/completar
└── 1_1_0001-template-surplus-handling.md              # verificar/completar
src/financial_forecasting/
├── shared/domain/__init__.py                           # add docstring (I4)
├── shared/application/__init__.py                      # add docstring (I4)
├── shared/infrastructure/__init__.py                   # add docstring (I4) se faltar
└── features/__init__.py                                # add docstring (I4)
tests/
└── test_smoke.py                                       # estender p/ esqueleto (I7)
README.md                                               # seção de ADRs/fundação (A9)
```

## 2. Tasks

> Faixa saudável: **3–8 Tasks por Stage**. Esta Stage tem **5 Tasks**.

### Task 01 — Verificar/completar os 5 ADRs de fundação

- **Arquivos a criar:** nenhum (os 5 já existem no disco).
- **Arquivos a modificar (somente se incompletos):**
  - `docs/adr/0_0_0002-probabilistic-calibration-framing.md`
  - `docs/adr/0_0_0019-hexagonal-enforced.md`
  - `docs/adr/0_0_0020-statistics-in-domain-over-value-objects.md`
  - `docs/adr/0_0_0021-per-unit-contract-tests-with-oracle.md`
  - `docs/adr/1_1_0001-template-surplus-handling.md`
- **O que fazer:**
  Conferir que cada ADR está conforme `docs/templates/adr.md`: frontmatter
  (`adr_id` no formato `"N.N.NNNN"`, `status: accepted`, `context_stage:
  1.1-bootstrap`, `decision` em 1 frase) e corpo com Context / Decision /
  Alternatives (incluindo status quo descartado) / Consequences, em **inglês**.
  Conteúdo derivado do overview §11 sem reabrir a deliberação (D-2). Para o
  `1_1_0001`, as alternativas são "podar / wirar / não documentar" (D-1).
  Se algum estiver incompleto, completá-lo nesta Task; se todos já válidos,
  registrar a verificação no body do commit sem diff de conteúdo.
- **Detalhes técnicos:**
  - **Não editar** `0_0_0000`, `0_0_0001`, `0_0_0050` (I6).
  - `0_0_*` = fundação global; `1_1_*` = ADR local de Stage (D-3 / `CONVENTIONS.md` §1).
  - Não referenciar artefatos de Stage futura (CI 1.2, import-linter 1.3) como já existentes (C6).
- **Critério de aceite:**
  - Os 5 ADRs com frontmatter válido e corpo completo (A1/A2); `make docs-check` verde.
  - `0_0_0000`/`0_0_0001`/`0_0_0050` inalterados (`git diff --stat` não os lista) (A7).
- **Comando de verificação:**
  ```bash
  make docs-check
  git diff --stat docs/adr/0_0_0000* docs/adr/0_0_0001* docs/adr/0_0_0050*   # deve sair vazio
  ```
- **Commit sugerido:** `docs(adr): formalizar ADRs de fundação 0.0.0002/0019/0020/0021 e débito 1.1.0001 [1.1/task-01]`

---

### Task 02 — Docstring de camada nos `__init__.py` do esqueleto hexagonal

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `src/financial_forecasting/shared/domain/__init__.py`
  - `src/financial_forecasting/shared/application/__init__.py`
  - `src/financial_forecasting/shared/infrastructure/__init__.py` (se ainda sem docstring)
  - `src/financial_forecasting/features/__init__.py`
- **O que fazer:**
  Adicionar docstring de **uma linha** em cada `__init__.py` de camada que está
  vazio, descrevendo a responsabilidade da camada (I4/C4). Ex.: domínio puro
  (stdlib-only, sem framework); application (use cases + ports, recebe/devolve
  DTO); infrastructure (plumbing/adapters técnicos); features (slices verticais
  de negócio). Não adicionar código — só docstring.
- **Detalhes técnicos:**
  - Linguagem do texto: PT (consistente com `shared/__init__.py` já presente).
  - Não tocar `__init__.py` que já tem docstring (raiz, `shared`).
  - Não introduzir imports (manteria domínio puro; `check_layout` cobre).
- **Critério de aceite:**
  - Todo `__init__.py` de camada (`shared.{domain,application,infrastructure}`,
    `features`, raiz) tem docstring de 1 linha (A5/I4).
  - `make check` verde (ruff D-rules de docstring, se ativas, passam).
- **Comando de verificação:**
  ```bash
  make check
  python - <<'PY'
  import ast, pathlib
  for p in ["shared/domain","shared/application","shared/infrastructure","features"]:
      f = pathlib.Path(f"src/financial_forecasting/{p}/__init__.py")
      assert ast.get_docstring(ast.parse(f.read_text())), f"sem docstring: {f}"
  print("OK docstrings de camada")
  PY
  ```
- **Commit sugerido:** `docs(skeleton): adicionar docstring de responsabilidade nas camadas do hexágono [1.1/task-02]`

---

### Task 03 — Estender o smoke test para exercer o esqueleto hexagonal

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `tests/test_smoke.py`
- **O que fazer:**
  Estender o smoke test para importar, além de `financial_forecasting`, os
  subpacotes do esqueleto hexagonal — `shared.domain`, `shared.application`,
  `shared.infrastructure` e `features` — falhando imediatamente se algum import
  do esqueleto quebrar (I7/C5). Manter o teto mínimo que evita exit 5 do pytest (C3).
- **Detalhes técnicos:**
  - Importar via `import financial_forecasting.shared.domain` etc., ou um único
    teste parametrizado com `importlib.import_module` sobre a lista de subpacotes.
  - Manter `# noqa: F401` em imports não usados; sem dependência de infra externa.
  - Não importar `features.*` concretas (não existem ainda) — só o pacote `features`.
- **Critério de aceite:**
  - `tests/test_smoke.py` importa o pacote raiz **e** os 4 subpacotes do esqueleto
    sem erro (A6/I7).
  - `make test` verde (≥ 1 teste coletado).
- **Comando de verificação:**
  ```bash
  pytest tests/test_smoke.py -v
  make test
  ```
- **Commit sugerido:** `test(smoke): exercer esqueleto hexagonal (shared.* e features) no smoke [1.1/task-03]`

---

### Task 04 — Referenciar os 4 ADRs de fundação no README

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:**
  - `README.md`
- **O que fazer:**
  Adicionar/estender uma seção de decisões/fundação no README referenciando os 4
  ADRs de fundação (`0_0_0002`, `0_0_0019`, `0_0_0020`, `0_0_0021`) com link
  relativo para `docs/adr/` (A9). Pode-se mencionar o ADR local `1_1_0001` como
  débito declarado. Não referenciar artefatos de Stage futura (CI/`.github`,
  `.importlinter`, `tests/architecture/`) como existentes (C6).
- **Detalhes técnicos:**
  - Links relativos a partir da raiz: `docs/adr/0_0_0002-...md`.
  - Não duplicar a tabela de docs existente; uma seção curta "Decisões de fundação".
- **Critério de aceite:**
  - README cita os 4 ADRs de fundação com link válido (A9).
  - Nenhuma menção a CI/import-linter/`tests/architecture` como já presentes (A8/C6).
- **Comando de verificação:**
  ```bash
  make docs-check
  grep -E "0_0_0002|0_0_0019|0_0_0020|0_0_0021" README.md
  ```
- **Commit sugerido:** `docs(readme): referenciar ADRs de fundação na seção de decisões [1.1/task-04]`

---

### Task 05 — Validar o DoD da Stage em máquina limpa

- **Arquivos a criar:** nenhum.
- **Arquivos a modificar:** nenhum (Task de verificação + commit de fechamento da Stage).
- **O que fazer:**
  Rodar o gate de saída completo do zero (`make setup && make check && make test`)
  e confirmar que `check_layout.py` está verde incluindo o excedente herdado
  (I1/I2/A4), que o smoke exerce o esqueleto (I7/A6), e que nenhum artefato de
  Stage futura foi introduzido (A8). Não havendo retoque pendente, aplicar o
  commit de fechamento `stage 1.1: complete` e marcar a Stage `done` no roadmap.
- **Detalhes técnicos:**
  - `make setup` recria `.venv` via uv; deve terminar exit 0.
  - Cobertura ≥ 90% **não** é gate aqui (entra na 1.2) — não exigir `fail_under`.
  - Atualizar `docs/roadmap.md` (Stage 1.1 → `done`, `updated_at`/`last_reviewed_at`).
- **Critério de aceite:**
  - `make setup && make check && make test` retorna exit 0 em máquina limpa (A3/I7).
  - `python scripts/check_layout.py` verde (A4); `0_0_0000`/`0_0_0001`/`0_0_0050` intactos (A7).
- **Comando de verificação:**
  ```bash
  make setup && make check && make test
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `chore(bootstrap): validar DoD da fundação hexagonal (check_layout + smoke verdes) [1.1/task-05]`

---

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage 1.1: complete` e ser mergeada em `develop` (merge feito pelo orquestrador).

### Verificações automatizadas
```bash
make setup                 # .venv via uv, hooks pre-commit/commit-msg
make check                 # lint (ruff) + typecheck (mypy --strict) + layout-check + docs-check + test
make test                  # pytest — smoke do esqueleto coletado e verde
python scripts/check_layout.py   # fitness function da Stage 1.1 (única; import-linter só na 1.3)
```

### Verificações funcionais
- [ ] `pytest tests/test_smoke.py -v` importa `financial_forecasting` **e**
      `shared.{domain,application,infrastructure}` + `features` sem erro (I7).
- [ ] `make check` verde incluindo o excedente herdado do template (não podado — D-1).

### Mapeamento invariante → teste/verificação

| Invariante / critério | Verificação |
|---|---|
| I1 — Direção de dependência | `python scripts/check_layout.py` verde (Task 02/05) → A4 |
| I2 — Domínio puro (stdlib-only) | `check_layout.py` (imports proibidos no domínio) — A4 |
| I3 — Ponto único de wiring | `composition_root.py` intacto; nenhuma instanciação fora dele (não tocado — D-1) |
| I4 — Docstring de camada | assert `ast.get_docstring` em cada `__init__.py` de camada (Task 02) → A5 |
| I5 — ADRs em inglês, `accepted` | `make docs-check` + frontmatter `status/adr_id/context_stage` (Task 01) → A1/A2 |
| I6 — Não retocar fundação existente | `git diff --stat docs/adr/0_0_0000* 0_0_0001* 0_0_0050*` vazio (Task 01/05) → A7 |
| I7 — Gate de saída (DoD) | `make setup && make check && make test` exit 0 + smoke do esqueleto (Task 03/05) → A3/A6 |
| I8 — Governança corrida autônoma | sem `git push`/`gh pr *`/toque em develop|main (revisão do histórico do branch) |
| I9 — Commits | subject Conventional Commits + tag `[1.1/task-NN]` + `Refs #5` (hook `commit-msg`) |
| A8 — Sem artefato de Stage futura | `grep` por `.github`/`.importlinter`/`tests/architecture` no diff (Task 04/05) |
| A9 — README referencia ADRs | `grep -E "0_0_0002|0_0_0019|0_0_0020|0_0_0021" README.md` (Task 04) |

### Checklist de fechamento da Stage
- [ ] Todas as 5 Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage 1.1: complete` aplicado
- [ ] Branch mergeado em `develop` (feito pelo orquestrador — não pelo agente)
- [ ] `roadmap.md` atualizado: Stage 1.1 `done`, `updated_at`/`last_reviewed_at`
- [ ] 5 ADRs (`0_0_0002`/`0019`/`0020`/`0021` + `1_1_0001`) em `status: accepted`
- [ ] Sem runbook operacional necessário (Stage de fundação)
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo

## 4. Ordem de dependência entre Tasks

Stage de fundação — ordem dirigida por entregável/invariante (não inside-out).
Tasks 01–04 são amplamente independentes entre si; a Task 05 valida tudo.

```
Task 01 (ADRs) ─┐
Task 02 (docstrings) ─┤
Task 03 (smoke) ─────┼──► Task 05 (validar DoD + fechamento)
Task 04 (README, dep. fraca de 01) ─┘
```

- Task 04 referencia os ADRs verificados na Task 01 (dependência de conteúdo, fraca).
- Task 05 só fecha depois de 01–04 commitadas (valida o DoD agregado).

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| ADR já existente diverge do template/overview §11 | Completar o ADR na Task 01 sem reabrir a decisão (D-2); se divergência for material no contrato, ajustar concept e registrar [deviation] na §7 |
| Ruff exige docstring (regra D) em `__init__.py` e quebra `make check` | Docstring de 1 linha já satisfaz (Task 02); se regra exigir formato específico, ajustar texto |
| `make setup` falha em máquina limpa (rede/uv) | Reexecutar; se persistir, registrar [finding] — não é introduzido por esta Stage |
| Excedente do template viola domínio puro (C2) | Não ocorre hoje (`check_layout` verde); se ocorrer, inertizar/podar o módulo ofensor (ADR `1_1_0001`) e registrar [decision] |
| Smoke importa `features.*` concreto inexistente | Importar só o pacote `features` (Task 03), não submódulos de slice |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md) — §2, §6, §7, §11 (decisões de fundação)
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.1-bootstrap`
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — §1 (ADR), §2/§3 (frontmatter), §4 (branches/commits)
- [`../../LAYOUT.md`](../../LAYOUT.md) §3 — regras de import/camadas
- ADRs desta Stage: [`../../adr/`](../../adr/) — `0_0_0002`, `0_0_0019`, `0_0_0020`, `0_0_0021`, `1_1_0001`; fundação consumida: `0_0_0001`
- [`../../adr/0_0_0050-autonomous-overnight-mode.md`](../../adr/0_0_0050-autonomous-overnight-mode.md) — governança da corrida
- Skills aplicáveis: `task-ordering-hex` (exceção foundation), `hex-arch-python`, `import-linter-rules` (preparação p/ 1.3)

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
> **Regra de pergunta antes da nota.** Ao encontrar durante a Fase 4
> algo não previsto no Concept ou neste Technical, **pause** e
> levante a pergunta para o humano com 2–4 opções e uma marcada como
> **recomendada** + razão. Apenas após a decisão, registre a entrada abaixo.

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
- `[finding]` — gap/observação a tratar em **próxima Stage**; inclui direção sugerida + Stage candidata.
- `[deviation]` — ajuste pequeno aplicado vs. o plano original.

### 2026-06-29 — [deviation] Task 01 (ADRs de fundação) — agente autônomo
**Contexto:** Os 5 ADRs (`0_0_0002`/`0019`/`0020`/`0021` + `1_1_0001`) já tinham sido
autorados e **commitados** no gate da Fase 3A (`9d8152c stage 1.1: conceptual approved`),
completos e com frontmatter válido (`status: accepted`, `adr_id` no formato `"N.N.NNNN"`,
`context_stage: 1.1-bootstrap`, corpo Context/Decision/Alternatives/Consequences em inglês).
**Razão:** A própria Task 01 prevê o caso "se já válidos, registrar a verificação sem diff de
conteúdo". Como não há diff a commitar (committar nada falharia), a Task 01 ficou sem commit
próprio: a verificação está registrada aqui. `0_0_0000`/`0_0_0001`/`0_0_0050` permanecem
intactos (A7). Nenhuma ação adicional necessária — os ADRs satisfazem A1/A2/I5.

### 2026-06-29 — [deviation] Task 02 (docstrings de camada) — agente autônomo
**Contexto:** As docstrings de uma linha de `shared/domain` e `shared/application` estouraram
o `line-length = 100` do ruff (E501) na primeira redação.
**Razão:** Encurtei o texto mantendo a responsabilidade da camada legível (domain → "serviços/VOs
puros stdlib-only (sem libs)"; application → "use cases e ports que trafegam DTOs, nunca
entidades"), em vez de adicionar `# noqa`. Ajuste cosmético, sem impacto no contrato.

### 2026-06-29 — [deviation] Task 02-extra (guard de I4/A5) — agente autônomo
**Contexto:** Após `stage 1.1: complete` (`ffaccf6`), a auditoria de testes identificou que a
invariante I4 / critério A5 (docstring de responsabilidade em cada `__init__.py` de camada) não
tinha gate automatizado — o ruff não seleciona `pydocstyle (D)`. O commit
`2753f08 [1.1/task-02-extra]` adicionou `test_layer_has_responsibility_docstring` (parametrizado
nos 6 pacotes de camada enumerados em A5) e reforçou `test_hexagonal_skeleton_imports` com assert
explícito (mutation-safe).
**Razão:** Fechar o gap de cobertura da invariante I4/A5 com teste dedicado, em vez de depender de
inspeção manual. Mudança restrita a `tests/test_smoke.py`; `make check` permanece verde. Registro
posterior ao `complete` por ter surgido na auditoria de testes (rastreabilidade — finding F1 da
stage-audit).

<!-- END: post-execution -->
