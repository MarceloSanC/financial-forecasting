---
title: Technical — GBM quantílico (LightGBM)
description: Plano de execução desta Stage, lista ordenada de Tasks (1 Task = 1 commit), pronto para ser consumido por code assistant
when-use: Consultar durante Fase 4 (execução) desta Stage; cada Task tem critério de aceite e comando de verificação
keywords: [technical, plano de execução, gbm-quantile-baseline, lightgbm]
status: draft
created_at: 2026-07-19
updated_at: 2026-07-19
stage_id: 5.3-gbm-quantile-baseline
stage_title: GBM quantílico (LightGBM)
step_id: 5
step_title: Modelagem e harness de walk-forward
depends_on: [5.1-walk-forward-harness]
concept_ref: ./concept.md
issue_id: 53
branch: feat/53-5-3-gbm-quantile-baseline
tasks_count: 0
---

# Technical — Stage N.M — <Título da Stage>

> **Como usar este documento (para code assistant):**
> 1. Ler primeiro [§1 Contexto e estratégia](#1-contexto-e-estratégia-de-execução).
> 2. Executar Tasks em ordem (§2). **1 Task = 1 commit.**
> 3. Cada Task traz: arquivos a tocar, descrição, critério de aceite,
>    comando de verificação.
> 4. **Não avançar para próxima Task sem verificação verde.**
> 5. Mensagem de commit segue [`CONVENTIONS.md`](../../CONVENTIONS.md) §4:
>    `<type>(<scope>): <description> [N.M/task-NN]`
> 6. Ao encontrar algo não previsto em §1–§6 ou no `concept.md`:
>    **pausar**, perguntar ao humano com opções e recomendação, e
>    registrar a decisão em [§7 Execução](#7-execução-post-hoc-editável-após-done).
>    Nunca propagar silenciosamente.
> 7. Ao fim da última Task, validar [§3 Gate de saída da Stage](#3-gate-de-saída-da-stage),
>    fazer commit `stage N.M: complete` e atualizar `roadmap.md`.
>
> **Stage = 1 branch.** Todo o trabalho desta Stage acontece em
> `feat/<num-issue>-<N-M>-<slug>` (ver `CONVENTIONS.md` §4). Não há
> sub-PRs internos. Sobre o fluxo Git completo ver
> [`PIPELINE.md`](../../PIPELINE.md) §10.

## 1. Contexto e estratégia de execução

### Resumo
<1 parágrafo. O que vamos construir nesta Stage, em termos técnicos.>

### Estratégia
<Como vamos construir. Bottom-up? Top-down? Spike primeiro? Mock
dependências externas? Ordem das Tasks e razão.>

### Pré-condições
- <ex.: Stage `<stage_id>` em `done` e mergeada em develop>
- <ex.: migration X aplicada localmente>
- <ex.: variáveis de ambiente conforme `.env.example`>

### Premissas técnicas
- <ex.: Python 3.12+, pyproject já existe>
- <ex.: redis local rodando em porta 6379>

### Estrutura de pastas afetada

```
src/financial_forecasting/
├── <camada-alvo>/
│   └── <novos arquivos>
tests/
└── <pasta>/
    └── <novos arquivos>
```

## 2. Tasks

> Faixa saudável: **3–8 Tasks por Stage**. ≥ 10 = Stage provavelmente
> está grande demais; reabrir Fase 3A para dividir.

### Task 01 — <descrição curta>

- **Arquivos a criar:**
  - `src/financial_forecasting/<camada>/<arquivo>.py`
  - `tests/<pasta>/test_<arquivo>.py`
- **Arquivos a modificar:**
  - <caminho ou "nenhum">
- **O que fazer:**
  <Prosa direta descrevendo a mudança material. Sem código completo;
  apenas indicações como "criar Protocol com método `X(arg: A) -> B`".>
- **Detalhes técnicos:**
  - <interface esperada, comportamento esperado, exceções>
- **Critério de aceite:**
  - <ex.: testes em `tests/.../test_<arquivo>.py` cobrem happy path e erro>
- **Comando de verificação:**
  ```bash
  pytest tests/<pasta>/test_<arquivo>.py -v
  mypy --strict src/financial_forecasting/<camada>/<arquivo>.py
  python scripts/check_layout.py
  ```
- **Commit sugerido:** `feat(<scope>): <description> [N.M/task-01]`

---

### Task 02 — <descrição curta>

- **Arquivos a criar:** <...>
- **Arquivos a modificar:** <...>
- **O que fazer:** <...>
- **Detalhes técnicos:** <...>
- **Critério de aceite:** <...>
- **Comando de verificação:**
  ```bash
  <comando>
  ```
- **Commit sugerido:** `<type>(<scope>): <description> [N.M/task-02]`

---

<Repetir Tasks.>

## 3. Gate de saída da Stage

> O que precisa estar verdadeiro para a Stage receber o commit
> `stage N.M: complete` e ser mergeada em `develop`.

### Verificações automatizadas
```bash
make check                # lint + type + import-linter + check_layout + testes
pytest tests/             # todos os testes
<outros comandos específicos da Stage>
```

### Verificações funcionais
- [ ] <comportamento end-to-end que precisa funcionar — ex.: "rodar `python -m financial_forecasting.cli ingest sample.csv` produz N registros no banco">
- [ ] <outro>

### Checklist de fechamento da Stage
- [ ] Todas as Tasks commitadas, cada uma com seu check verde
- [ ] `make check` verde no branch
- [ ] Commit final `stage N.M: complete` aplicado
- [ ] Branch mergeado em `develop`
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e
      `last_reviewed_at` no mesmo merge (ou em PR de docs imediato)
- [ ] ADRs novos (se houve) em `status: accepted`
- [ ] Runbooks operacionais criados se aplicável
- [ ] `concept.md` desta Stage não precisa de retoque retrospectivo
      (se precisa, abrir TODO ou nova Stage de correção)

## 4. Ordem de dependência entre Tasks

<Texto ou lista mostrando quais Tasks dependem de quais. Por padrão a
ordem listada em §2 já respeita dependências; explicitar aqui só os
casos não óbvios.>

```
Task 01 ─► Task 02 ─► Task 04
              │
              └──► Task 03
```

## 5. Riscos de execução e fallbacks

| Risco | Fallback |
|---|---|
| <ex.: lib X não suporta caso Y> | <ex.: cair para lib Z, ADR registrando> |

## 6. Referências

- [`./concept.md`](./concept.md) — conceito desta Stage
- [`../../overview.md`](../../overview.md)
- [`../../roadmap.md`](../../roadmap.md)
- [`../../CONVENTIONS.md`](../../CONVENTIONS.md) — branches, commits, status
- ADRs desta Stage: [`../../adr/`](../../adr/) (filtrar por prefixo `N_M_`)
- Skills aplicáveis: <ids de `skills/`>
- Docs externos: <links>

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
> **recomendada** + razão (via `AskUserQuestion` ou equivalente).
> Apenas após a decisão, registre a entrada abaixo. Na dúvida sobre
> se algo é "pequeno o suficiente para decidir sozinho", **pergunte**.

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

### YYYY-MM-DD — [tag] <Task NN ou escopo> — <Autor>
<!-- preencher quando aplicável; remover este placeholder se vazio -->

<!-- END: post-execution -->