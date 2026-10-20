# PROMPT — sessão Linux da Stage 7.3 (fase Linux, L0–L8)

> **Para o agente que lê este arquivo:** isto é a sua tarefa inteira. O humano só pediu
> "atualize o repo e leia este arquivo". Execute tudo abaixo, na ordem, sem pedir OK
> fora dos pontos de parada marcados com **PARE**. Você não vê o histórico nem a memória
> da sessão Windows que preparou isto: o que precisa está aqui, na §7 do
> [technical.md](technical.md) e na issue #186.

## 0. Contexto

- Stage 7.3-explainability, issue #186, PR #200 (aberto, `Refs #186`, auditoria `review`),
  branch `feat/186-7-3-explainability`.
- Processo: [docs/PROMPT-step-single-session.md](../../PROMPT-step-single-session.md),
  Fase 4 em diante (autonomia, gates, auditoria, fechamento autônomo).
- **Fase Windows concluída:** Tasks 01–33, 8 Checkpoints C, auditoria de testes, Ponto C
  verde (7969 passed, cobertura 98,79 %).
- **Etapa W feita no Windows:** `attribute` nos 60 runs do confirmatório, todos `strict`
  com max|d| 0; `fact_permuted_predictions` 8 655 920 linhas, `fact_vsn_weights`
  891 490, `attribution_manifest.json` com 60 `completed`. A L6 vira re-conferência na L0.
- **Roteiro:** a entrada `### 2026-10-19 — [decision] handoff — fase Windows → fase Linux
  (Task 33)` da §7 do technical.md — tabela L0–L8 com comando, saída esperada e parada.
  Comentário de handoff:
  https://github.com/MarceloSanC/financial-forecasting/issues/186#issuecomment-6278999689

## 1. Preparação

1. Atualize o checkout: `git fetch origin && git checkout feat/186-7-3-explainability &&
   git pull --ff-only origin feat/186-7-3-explainability`. Árvore suja ou pull que não
   seja fast-forward: **PARE** e reporte.
2. Leia inteiros: `CLAUDE.md`; `docs/stages/7.3-explainability/concept.md`;
   `technical.md` (no mínimo §1, §2 "Fase Linux", §3 e a §7 inteira); ADRs
   `docs/adr/7_3_0001..0006`.
3. **Pacote de dados do Windows.** A L0 precisa de `transfer-in.tar` e `transfer-in.sha`
   (gerados no Windows em `C:\Users\Marcelo\ff-transfer-7.3\`, 1,87 GB, 313 arquivos:
   dataset, silver com as tabelas da Etapa W, manifestos e os 60 checkpoints).
   Procure em `~/ff-transfer-7.3/` (e, se não estiver, em `~/Downloads` e em discos
   montados em `/media` ou `/mnt`). Use o diretório encontrado como `IN`.
   **Não encontrou: PARE** e peça ao humano para copiar os dois arquivos do Windows para
   `~/ff-transfer-7.3/` (fora da árvore do repo).
4. Primeiro commit da fase Linux (pendência CA16 do Windows): registre na §7 a URL do
   comentário de handoff acima, numa entrada nova com data e autor;
   `docs(stages): url do comentário de handoff na §7 [7.3/--]`; push.

## 2. Execução L0 → L8

Siga a tabela do handoff, na ordem. Resumo do que cada etapa é:

| Etapa | O quê |
|---|---|
| L0 | uv, `gh auth status`, `make setup`, X = pai da Task 33, `TRANSFER_OK`, `verify`, `attribute` só verificando (60 `verified`, 0 written) |
| L1 | torch ROCm + probe (`gpu.available true`, RX 7700 XT, HIP), árvore e lock intocados |
| L2 | piloto `ablation-pilot`; relatório colado na §7 |
| L3 | **PARE:** número de seeds S é decisão do humano (P). Pergunte no formato "Anatomia da pergunta" do PROMPT-step §2, com teto e estimativa do piloto por S = 1..10. Com a resposta: ADR `7_3_0007-ablation-seed-count.md`, commit, push |
| L4 | `ablation-freeze`, commit, push, tag `cohort/<id>`, comentário na #186 |
| L5 | `ablation-run` (retomável) + `ablation-verify` |
| L6 | N/A (Etapa W feita), salvo se a L0 não conseguir re-conferir |
| L6b | transferência para a 8.1 e arquivamento dos checkpoints (ou N/A por `[decision]` se a 8.1 rodar no próprio Linux) |
| L7 | r3 preenchida, testes de repo, tag, `TAG_ORDER_OK`, comentário, `.anchor.toml`, espelho |
| L8 | skill `stage-audit`, `make check` num venv travado sem o torch ROCm (ou o CI), roadmap `done`, `stage 7.3: complete`, `Closes #186` no PR, merge autônomo |

Saída diferente da esperada em qualquer etapa: **PARE**, registre `[finding]` na §7 e
reporte. Não contorne.

## 3. Restrições

- **Cegamento:** nenhuma métrica sobre o cohort real (nem sonda) antes da âncora da r3
  (L7).
- Nenhuma mudança em `src/` entre a L4 e o fim da L5.
- Ajuste de GPU que surgir (C12): `[decision]` na §7 e commit **antes** da L4.
- Com o torch ROCm instalado, sempre `uv run --no-sync` (o `uv run` puro reinstala o
  torch CPU).
- Depois da tag da r3, nunca rebase: atualizar com o `develop` só por merge.
- Toda entrada nova na §7 leva data e autor; commits em PT, Conventional Commits com
  escopo, sufixo `[7.3/...]`, `Refs #186`.
- Nunca editar configurações de permissão; nunca tocar processos ou containers de outras
  sessões.

## 4. Quando parar de vez

Depois do merge do PR #200 na L8: reporte ao humano em PT o veredito da auditoria, o
hash do merge, as tags (`cohort/<id>`, `preregistration/<ref r3>`) e o que ficou para a
Stage 7.4.
