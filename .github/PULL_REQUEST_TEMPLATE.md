<!--
Título: siga o mesmo padrão da issue.
  PR de Stage:  feat: stage N.M — <título humano>
  PR de fix:    fix(<scope>): <descrição>
Ver docs/CONVENTIONS.md §4 e docs/GIT-WORKFLOW.md.
-->

Closes #<num-issue>

## Resumo

<!-- 1–2 frases sobre o que mudou e por quê. -->

## Tipo

- [ ] Stage do pipeline (N.M)
- [ ] Fix (bug)
- [ ] Refactor
- [ ] Docs
- [ ] Chore

## Checklist (Stage)

<!-- Marque os itens aplicáveis. Para não-Stage, ignore os irrelevantes. -->

- [ ] Todas as Tasks do `technical.md` implementadas (1 Task = 1 commit)
- [ ] `make check` verde localmente (lint + typecheck + layout-check + test)
- [ ] Coverage ≥ 90% no código novo (via `pyproject.toml [tool.coverage.report]`)
- [ ] `roadmap.md` atualizado: Stage marcada `done`, `updated_at` e `last_reviewed_at` setados
- [ ] ADRs novos (se houve) em `status: accepted`
- [ ] Runbooks operacionais criados se aplicável
- [ ] `concept.md` não precisa de retoque retrospectivo

## Como testar

```bash
make check
```

<!-- Se houver passos extras (migrations, fixtures), liste aqui. -->
