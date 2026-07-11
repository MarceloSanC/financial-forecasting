<!--
Título: Conventional Commits em português, com escopo OBRIGATÓRIO (o escopo é
o BC/módulo — NUNCA a Stage). Ver docs/CONVENTIONS.md §4 e docs/GIT-WORKFLOW.md.
  PR de Stage:   <tipo>(<escopo>): stage N.M — <descrição>
                 ex.: feat(modeling): stage 5.2 — baselines naive e estatísticos
  PR avulso:     <tipo>(<escopo>): issue #<num> — <descrição>
                 ex.: fix(market-data): issue #47 — corrigir fuso do calendário
-->

Closes #<num-issue>

> **Auditoria:** `review`
>
> Label de status do gate `audit-gate` (CI) — CONVENTIONS §3.6. `review` =
> aguardando auditoria (**merge bloqueado**); `complete` = auditada
> (**liberado**). A sessão de auditoria (`stage-audit` para Stage,
> `issue-audit` para issue avulsa) grava `complete` ao validar — **não edite
> à mão**.

## Resumo

<!-- 1–2 frases sobre o que mudou e por quê. -->

## Checklist (Stage)

<!--
O checklist é um HANDOFF: marque APENAS o que você validou com certeza
nesta sessão; deixe o resto desmarcado — a auditoria completa depois.
Para não-Stage, ignore os itens irrelevantes.
-->

- [ ] Todas as Tasks do `technical.md` implementadas (1 Task = 1 commit)
- [ ] `make check` verde localmente (lint + format-check + typecheck + layout-check + test)
- [ ] Coverage ≥ 90% no código novo (via `pyproject.toml [tool.coverage.report]`)
- [ ] `roadmap.md` sincronizado **neste PR**: Stage marcada `done` (`todo→done`) — ou, em PR de issue avulsa, o item `open→closed` — + `updated_at`/`last_reviewed_at` no frontmatter (para o roadmap não defasar do GitHub ao mergear)
- [ ] ADRs novos (se houve) em `status: accepted`
- [ ] Runbooks operacionais criados se aplicável
- [ ] `concept.md` não precisa de retoque retrospectivo

## Como testar

```bash
make check
```

<!-- Se houver passos extras (dados bronze, fixtures, extra `ml`), liste aqui. -->