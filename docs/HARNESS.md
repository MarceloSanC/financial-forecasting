---
title: Convenções do harness do Claude Code — skills, subagentes e hooks
description: Onde mora cada peça do harness (.claude/), o que cada uma pode fazer e o que o check_harness valida
when-use: Antes de criar ou alterar uma skill, um subagente em .claude/agents/ ou um hook em .claude/hooks/ e .claude/settings.json; ao decidir em qual camada uma regra nova mora
keywords: [harness, claude-code, skill, subagent, agent, hook, posttooluse, pretooluse, settings, check_harness]
status: draft
created_at: 2026-10-17
updated_at: 2026-10-17
---

# Convenções do harness do Claude Code

Dono das convenções de **subagentes** e **hooks** e da **estrutura de pasta** de skill.
Formato do frontmatter de skill e catálogo de skills: [`PIPELINE.md`](./PIPELINE.md) §13.
Decisão das três camadas (gate × hook × revisor): ADR 0.0.0058.

## 1. Camadas — onde uma regra mora

| Camada | Mecanismo | Veredito? | Regra |
|---|---|---|---|
| Gate | script em `scripts/`, em `make check`/CI | **sim**, o único | teste em `tests/` que reprova uma violação injetada |
| Hook | `.claude/hooks/*.py`, tipo `command` | não — feedback ou bloqueio pontual | determinístico; sem regra própria quando espelha um gate |
| Subagente | `.claude/agents/*.md` | não — entrada para humano/auditoria | só leitura; cada achado cita regra + fonte |
| Skill | `.claude/skills/<nome>/` | não | conhecimento e procedimento; scripts executados, não lidos |

Uma regra mora numa camada só. Se dá para escrever como gate com falso-positivo aceitável, é
gate; julgamento é subagente; hook só antecipa gate ou bloqueia operação (ex.: `git_guard`).

## 2. Skills — estrutura de pasta

```
.claude/skills/<nome>/
├── SKILL.md          # ≤ 500 linhas de corpo; catálogo/índice
├── reference/        # (ou references/) material lido sob demanda — UM nível
│   └── <tema>.md     # citado direto pelo SKILL.md; > 100 linhas → sumário no topo
└── scripts/          # utilitários EXECUTADOS (só a saída entra no contexto)
```

- Script de skill que precisa de regra que já existe em `scripts/` (raiz) **importa** o
  script dono — nunca copia a lógica (ex.: `architecture-fitness/scripts/check_changed.py`).
- Script de skill e de hook é stdlib-only: roda no `python` do host, sem venv.
- Fonte citada em skill só entra lida literalmente e conferida pelo `evidence-verifier`.

## 3. Subagentes (`.claude/agents/<nome>.md`)

- `name` + `description` obrigatórios; a `description` diz o que recebe, o que devolve e
  quem despacha.
- Revisor/verificador é **só leitura**: `tools` sem `Edit`/`Write`/`NotebookEdit`, e
  `disallowedTools` explícito. Bash só para leitura (`git diff`/`git show`/`curl`), um comando
  por chamada — a permissão casa o comando inteiro.
- `skills: [<nome>]` pré-carrega a skill inteira no contexto do subagente; use quando o
  subagente precisa do catálogo (ex.: `architecture-reviewer` → `architecture-fitness`).
- Saída em formato fixo, uma linha por item; sem gravar arquivo (o relatório volta inline).
- `omitClaudeMd: true` para subagente de contexto zerado (verificador, revisor).

## 4. Hooks (`.claude/hooks/<nome>.py` + `.claude/settings.json`)

- Tipo `command` sempre; `prompt`/`agent` não (não determinísticos; `agent` é experimental).
- Registro em `settings.json` com `"command": "python"` e
  `"args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/<nome>.py"]`.
- Lê o payload JSON do stdin (decodificar `utf-8-sig`: o pipe do Windows PowerShell 5.1
  prefixa BOM).
- Saída por evento:
  - `PreToolUse` que recusa: JSON `hookSpecificOutput.permissionDecision = "deny"` com o
    motivo acionável (`git_guard`, `issue_guard`, `triage_gate`).
  - `PostToolUse` que avisa: stderr + exit 2 (o Claude vê o stderr; a ferramenta já rodou)
    — `arch_feedback`.
- **Fail open**: erro do próprio hook (JSON ruim, exceção, `SystemExit` de lib) → exit 0. O
  veredito continua no `make check`.
- Raiz do repo a partir do arquivo/`cwd` do payload quando o hook olha arquivo: a sessão
  aberta no checkout principal edita worktrees.
- Teste unitário em `tests/unit/tooling/test_<nome>.py`, incluindo o processo real por
  subprocess (stdin → exit code/stdout/stderr) e o registro em `settings.json`.
- Teste que roda `git` em `tmp_path` limpa `GIT_DIR`/`GIT_WORK_TREE` do ambiente: o container
  de check de worktree exporta os dois, e sem isso o `git init`/`git config` do teste escreve
  no repositório real.

## 5. O que o `scripts/check_harness.py` valida (em `make docs-check`)

- Frontmatter de skill e subagente (campos conhecidos, YAML válido, `description` sem
  truncamento, ≤ 1.536 caracteres).
- Estrutura de skill (§2): corpo ≤ 500 linhas, `reference/` um nível e citado pelo
  `SKILL.md`, sumário acima de 100 linhas, links e `scripts/*.py` citados existem.
- `skills:` de subagente aponta skill existente; `skillOverrides` idem.
- Todo `${CLAUDE_PROJECT_DIR}/...` dos hooks existe.
- Débito anterior à regra fica em `KNOWN_DEBT` (motivo + issue) e só encolhe.
