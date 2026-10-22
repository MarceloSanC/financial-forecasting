---
title: Handoff — Stage 7.4 — continuação no Windows
description: Estado exato da sessão Linux (2026-10-21) que executou as Fases 3A/3B e começou a Fase 4 da Stage 7.4, para uma nova sessão retomar no Windows sem perder contexto
when-use: Colar numa nova sessão Chat IDE no Windows para continuar a Fase 4 da 7.4; apagar este arquivo no último commit da Stage
keywords: [handoff, stage-7.4, inference-api, windows, continuação]
status: draft
created_at: 2026-10-21
updated_at: 2026-10-21
---

# Handoff — Stage 7.4 (API de inferência) — Linux → Windows

## Prompt para a nova sessão (colar inteiro)

> Continue a execução da Stage `7.4-inference-api` seguindo
> `docs/PROMPT-stage-single-session.md`, **a partir da Fase 4** (Fases 3A e 3B
> já fechadas e commitadas). Leia primeiro
> `docs/stages/7.4-inference-api/HANDOFF-windows.md` (este arquivo), depois
> `concept.md` e `technical.md` da Stage. Variáveis: Stage `7.4-inference-api`,
> issue `#201`, branch `feat/201-7-4-inference-api`, título humano "API de
> inferência (predições gravadas do candidato com intervalo conformal e
> leitura de H3)". Retome na **Task 01** (parcialmente commitada como WIP —
> ver §3). Checkpoints A e B já fechados (ver §4); Checkpoint C, Auditoria de
> Testes, gate de saída e PR continuam a cargo desta sessão.

## 1. Onde a Stage está

| Item | Estado |
|---|---|
| Issue | #201 (aberta; corpo tem B1–B3 validados pelo humano e `## Referências`) |
| Branch | `feat/201-7-4-inference-api`, criada de `origin/develop` em `3573e77` (merge da 7.3) |
| Concept | `done`, commit `c64dc30` (`stage 7.4: conceptual approved`) |
| ADRs | `7_4_0001` e `7_4_0002` em `accepted` (no mesmo commit) |
| Roadmap | alinhado em 3 commits off-task (`333cc36`, `ff3bdb9`, `073da06`); a Stage segue `draft` na tabela até o `complete` |
| Technical | `done`, commit `95204e6` (`stage 7.4: technical approved`), **10 Tasks**, 1 `make check` (saída) |
| Fase 4 | Task 01 começada: 3 arquivos de src/fake escritos, **sem teste e sem rodar nada** (§3) |

## 2. Decisões do humano (Passo 1b, 2026-10-21) — não reabrir

- **B1** servir as predições gravadas (sem rodar o modelo); pedido sem dado →
  404 "não há dados para o pedido solicitado"; atualização contínua = job
  agendado, fora da Stage (issue própria na Task 10).
- **B2** uma entrada por seed, sem média entre seeds.
- **B3** gold ausente/BLOCKED/sem bloco → 200 com bloco `unavailable` + motivo.

## 3. Task 01 — o que já existe (WIP, commit `wip(inference)…`)

Escritos e **não verificados** (nenhum pytest/mypy/ruff rodou sobre eles):

- `src/financial_forecasting/features/inference/application/dtos/__init__.py`
- `src/financial_forecasting/features/inference/application/dtos/serving_gold.py`
  — `ConformalCorrectionRecord`, `H3ShareRecord`, `H3ReadingRecord`,
  `VsnRecord`, `ServingGold` (+ `unpublished`), constantes `AVAILABLE`,
  `UNAVAILABLE`, `OK`, `LOWER`, `UPPER`; validações em `__post_init__`
  conforme technical §1 "Contratos".
- `src/financial_forecasting/features/inference/application/ports/out/serving_gold_reader.py`
  — `Protocol` com `read(self, *, asset: str, cohort_id: str) -> ServingGold`
  (import do DTO sob `TYPE_CHECKING`; **atenção:** o `check_port_coverage.py`
  compara anotações textualmente com o `ReadServingGold` da Task 03 — manter
  idênticas).
- `tests/fakes/features/inference/in_memory_serving_gold_reader.py` —
  `InMemoryServingGoldReader(golds, *, error=None)`, **sem fallback**
  (`KeyError` em partição não carregada), registra `calls`.

Falta na Task 01: `tests/unit/features/inference/application/test_serving_gold_dtos.py`
(casos listados no technical, Task 01, "Critério de aceite"), rodar o T1
(`pytest … --no-cov` + `uv run mypy --strict tests/fakes/features/inference/in_memory_serving_gold_reader.py`),
formatar só os arquivos tocados com `uvx ruff@0.6.9 format <arquivos>` e
fechar com o commit `feat(inference): DTOs e port do leitor do gold servido, com fake [7.4/task-01]`.
O WIP fica no histórico (commit não-amendável depois de push); o commit da
Task 01 completa o trabalho.

## 4. Checkpoints já executados (disposições — para o relatório final §3)

**Checkpoint A (concept)** — 3 revisores na rodada 1 (conformidade,
domínio/testabilidade, completude das decisões), rodada 2 e rodada 3 de
re-verificação. Total: 30 achados na rodada 1 (3 major de conformidade: A1
aresta evaluation→inference sem exceção declarada ao ADR 0.0.0053; A2
camada/gate_mode do roadmap; A3 CA10 sem gate de torch no router; 2 major de
domínio: T1 corpo do 422 de validação é lista; T3 semântica de disponibilidade
ambígua), 6 contradições novas na rodada 2 (N1 major: VSN `undefined` grava
rótulo nulo → conferência viraria 500). **Todos `corrigido`** no concept/ADRs/
roadmap; nenhum `refutado`, nenhum `escalado`. Rodada 3: 4 resíduos de redação
corrigidos; zero blocker. Detalhe completo no scratchpad da sessão Linux
(perdido) — o resumo acima é o registro.

**Checkpoint B (technical)** — 2 revisores (rastreabilidade/atomicidade/gates;
viabilidade contra o código com probes). 12 achados minor (B1–B12) + 4 (V1–V4).
Todos `corrigido` na reescrita do technical (9 → 10 Tasks: handler de
`ApplicationError` virou Task 05 própria em `feat(http)`; router passou a ser
registrado pela composition root, não por `importlib` no `app.py`; `omit` de
`shared/infrastructure/http/*` sai do `pyproject.toml` na Task 07; mypy
explícito sobre fake/contrato nas Tasks 01 e 04; seed nula no gold descartada;
`ok ⇒ n`/limites não nulos). Matriz CA1–CA14 → Tasks sem órfão (está implícita
nos "Critério de aceite" de cada Task).

## 5. Fatos medidos no dado real (só colunas de predição)

- Silver: `data/cohorts/aapl/silver/` (no Linux: `/home/marcelo/Code/financial-forecasting/data/cohorts/aapl`); candidato `tft_quantile`,
  `parent_sweep_id = aapl_confirmatory-r0-665f45d9169a`, 60 runs (fold `"0"`–`"5"` str × seed 1–10); o mesmo
  `parent_sweep_id` tem 6 runs `gbm_quantile` (filtrar por `model_version`!).
- Teste por seed: 1511 decisões h+1 (2019-12-26…2025-12-30), 1505 h+7 (…2025-12-19); últimas 6 sessões só h+1.
- Com `split="test"`: exatamente 1 run por (seed, h, data); sem o filtro, 82,6 % das datas também têm run `calib` do fold seguinte.
- `timestamp_utc` = `YYYY-MM-DDT00:00:00+00:00`; partição `year` = ano da decisão; leitura de um ano ≈ 89 488 linhas em ~0,8–2 s.
- Gold real: **não existe** `current/` (8.1 publica). `config/cohorts/aapl_confirmatory.toml` é congelado; `cohort_id` derivado = `aapl_confirmatory-r0-665f45d9169a`.

## 6. Regras operacionais herdadas

- Formatar **só arquivos tocados**: `F="a.py b.py"; [ -n "$F" ] || exit 1; uvx ruff@0.6.9 format $F` (ruff do venv 0.15.20 ≠ hook 0.6.9; issue #198).
- Commits: `tipo(escopo): descrição [7.4/task-NN]` ≤ 100 chars, body em bullets, `Refs #201`, rodapé `Co-Authored-By`.
- `make check` só na saída (plano de gates); T1 por Task = pytest dos testes da Task `--no-cov` + hooks.
- Worktree no Windows: criar com `python scripts/worktree-new.py feat/201-7-4-inference-api --no-setup --no-vscode`
  **não** — a branch já existe no remoto: `git fetch` e `git worktree add ../financial-forecasting-worktrees/feat-201-7-4-inference-api feat/201-7-4-inference-api` (ou checkout em worktree pelo script se ele aceitar branch existente), depois `make setup`.
- Dados: pacote gerado no Linux em `~/ff-data-7.4.tar.gz` (136 MB, 779 entradas;
  sha256 `91d243f5e182167342fc0f4b1497531f054cb2ff5ac1ec9ec59848b2114889ff`, em
  `~/ff-data-7.4.sha`), com `data/cohorts/aapl/{bronze,raw,processed,silver,inference}`
  e `artifacts/cohorts/` (ledgers com o ambiente gravado). Transferir por fora do
  git, conferir `sha256sum -c ff-data-7.4.sha`, extrair na raiz do repo e usar
  `DATA_ROOT=data/cohorts/aapl` na verificação CA12 (§3 do technical). Serve
  também à 8.1/8.2/8.3.
- Checkpoints: `~/ff-checkpoints-tft.tar` (7,9 GB sem compressão, `artifacts/tft`
  com os 360 dirs = 60 do confirmatório + 300 da ablação; 306 arquivos `.ckpt`; sha256
  `271e7cb808669ac36a8d3dfffa0b5b2831f4b5304a49ddfc71a6040aa540e961`, em
  `~/ff-checkpoints-tft.sha`). A 7.4 não os usa; a 8.1 usa os 60 do confirmatório
  na verificação `infer`. Extrair na raiz do repo (`ARTIFACTS_ROOT=artifacts`).
  **A máquina Linux não volta ao projeto**: este tar é a única cópia a partir
  daqui — a pendência de arquivamento da 7.3 fecha com ele.
- Extras: `~/ff-extra.tar.gz` (27 MB; sha256
  `1ad257d99abb0ea2360846d18c6dc866e2b75618010b50ee3d6e3f4644c68525`, em
  `~/ff-extra.sha`): `data/{analytics,raw,processed}` da raiz (bronze/silver dos
  Steps 1–4, jun/2026 — não é o cohort), `.claude/settings.local.json`
  (permissões liberadas ao Claude) e `memory/` (os 3 arquivos da memória do
  Claude deste projeto; no Windows vão para a pasta equivalente em
  `~/.claude/projects/<slug-do-caminho>/memory/`). Extrair na raiz do repo;
  mover `memory/` para fora.
- `.env`: cópia em `~/ff-dot-env` (4 chaves de API ausentes do `.env.example`:
  ALPHAVANTAGE, BENZINGA, FINNHUB, HUGGING_FACE). Levar por fora do git.

## 7. Pendências fora da 7.4 (registrar/decidir depois)

- ~~Arquivar `artifacts/tft`~~ — feito: `~/ff-checkpoints-tft.tar` + sha (ver §6); conferir no Windows antes de descartar o Linux.
- Issues a abrir na Task 10: job agendado (D10) e "contratos da 7.1/7.3 afirmam prova por mypy que não roda sobre tests/".
- Issue #199 (hooks ausentes em worktrees) e #198 (pin do ruff) continuam abertas.
