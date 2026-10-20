# Prompt da sessão Linux — Stage 7.3 (fase Linux, L0–L8)

> Para colar numa sessão nova do Claude Code no Linux (VS Code), depois de
> `git fetch && git checkout feat/186-7-3-explainability`. A sessão Linux não vê o
> histórico nem a memória da sessão Windows: tudo de que ela precisa está neste
> arquivo, na §7 do [technical.md](technical.md) e na issue #186.

## Antes de abrir a sessão (humano)

1. Copiar para o Linux, **fora da árvore do repo**, o par gerado no Windows:
   `C:\Users\Marcelo\ff-transfer-7.3\transfer-in.tar` e `transfer-in.sha`
   (dados do cohort, silver com as tabelas da Etapa W, manifestos e os 60 checkpoints).
2. Ter `gh` autenticado e a GPU (RX 7700 XT, ROCm) visível.

## Prompt

```text
Você vai executar a fase Linux (L0–L8) da Stage 7.3-explainability (issue #186,
PR #200, branch feat/186-7-3-explainability), seguindo docs/PROMPT-step-single-session.md
(Fase 4 em diante: autonomia, gates, auditoria, fechamento).

Leia antes, inteiros: CLAUDE.md; docs/stages/7.3-explainability/concept.md e technical.md
— em especial a §7, entrada "### 2026-10-19 — [decision] handoff — fase Windows → fase
Linux (Task 33)", que é o roteiro L0–L8 com comandos, saída esperada e critério de parada;
o comentário de handoff na #186
(https://github.com/MarceloSanC/financial-forecasting/issues/186#issuecomment-6278999689);
ADRs docs/adr/7_3_0001..0006.

Estado herdado do Windows:
- fase Windows concluída (Tasks 01–33, 8 Checkpoints C, auditoria de testes, Ponto C
  verde: 7969 passed, cobertura 98,79 %);
- Etapa W feita no Windows: attribute nos 60 runs do confirmatório, todos strict com
  max|d| 0; fact_permuted_predictions 8 655 920 linhas, fact_vsn_weights 891 490,
  attribution_manifest.json com 60 completed. Logo a L6 vira re-conferência na L0;
- o par transfer-in.tar/.sha está em <IN> (fora da árvore) — me pergunte o caminho se
  não souber;
- pendência do Windows (CA16): registrar na §7 a URL do comentário de handoff acima.
  Faça isso como primeiro commit, `docs(stages): ... [7.3/--]`.

Execute L0 → L8 na ordem da tabela do handoff:
- L0 chegada (uv, gh, make setup, X = pai da Task 33, TRANSFER_OK, verify, attribute
  só verificando); L1 torch ROCm + probe; L2 piloto; L3 número de seeds — é decisão P
  do humano: PARE e me pergunte no formato "Anatomia da pergunta" do PROMPT-step §2,
  com teto e estimativa do piloto; L4 freeze + tag cohort/<id> + comentário na #186;
  L5 treino da ablação (retomável) + ablation-verify; L6 N/A salvo se a L0 não
  re-conferir; L6b transferência/arquivamento; L7 r3 preenchida, testes de repo,
  tag, ordem das tags, comentário, .anchor.toml, espelho; L8 stage-audit, make check
  num venv travado sem o torch ROCm (ou o CI), roadmap done, `stage 7.3: complete`,
  `Closes #186` no corpo do PR, merge autônomo.
- Qualquer saída diferente da esperada na tabela: pare, registre [finding] na §7 e me
  reporte. Não contorne.

Restrições:
- cegamento: nenhuma métrica sobre o cohort real (nem sonda) antes da âncora da r3 (L7);
- nenhuma mudança em src/ entre a L4 e o fim da L5;
- depois da tag da r3, nunca rebase (atualizar com o develop só por merge);
- `uv run --no-sync` sempre que o torch ROCm estiver instalado (uv run puro reinstala
  o torch CPU);
- ajustes de GPU que surgirem (C12) viram [decision] na §7 e commit antes da L4;
- toda entrada nova na §7 leva data e autor; commits em PT com escopo e [7.3/...].
```
