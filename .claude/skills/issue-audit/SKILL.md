---
name: issue-audit
description: Auditoria de uma issue (ou grupo de issues) antes do PR/merge — julgamento read-only do que foi implementado × o CORPO da issue no GitHub (## Escopo + ## Critério de aceitação) + fase de aplicação SEPARADA que empurra fixes ao PR existente e registra o veredito; confere se os gates passam e classifica achados POR ESCOPO (dentro da própria issue, issue separada, ou não-issue). Invocar quando o usuário pedir "auditar issue #N", "auditoria da issue", "valida issue", "issue X está pronta pra PR?", "tem gap na issue?", "essas issues entregaram o que prometeram?", "audita o épico", "confere se a #N fechou de verdade", ou ao revisar uma issue de outra sessão/branch. Aceita uma issue ou uma lista. Triggers em PT. Skill de PROCEDIMENTO + GUARDRAIL — codifica o varredor mecânico (gh issue view, scripts de gate, cruzamento critério↔evidência) e protege contra dois falsos verdes específicos de issue: (a) marcar critério ✅ sem evidência, e (b) empurrar refino DENTRO do escopo para "melhoria futura" só porque a issue parece fechada. Lean toward triggering — custo de auditar é baixo, custo de fechar issue com gap silencioso (ou de fragmentar escopo em cards concorrentes) é alto. A SAÍDA não é só relatório de gate — sempre produz, em linguagem clara (jargão glosado entre parênteses) e com lente de valor + design escalável/responsabilidade: (1) conceitos principais, (2) tasks→arquivos (links)→o que entrega, (3) gates garantidos 100%, (4) decisões de arquitetura, (5) findings por escopo, (6) aprendizados→skills. Disparada por "Audite issue #N" / "audita a #N".
metadata:
  status: draft
  applies_when:
    camada_alvo: [any]
    invoked_at: [pre-pr, pre-merge, issue-review, epic-review]
---

# Issue Audit (read-only)

Procedimento para **auditar uma issue** (ou um **grupo de issues** /
épico) antes de abrir/mergear o PR, ou ao revisar o que outra sessão
entregou. É a irmã da skill `stage-audit`, adaptada para o contexto de
**issue avulsa** — que **não tem `concept.md`/`technical.md`**: a fonte
da verdade é o **corpo da issue no GitHub** (`## Escopo` +
`## Critério de aceitação`) cruzado com o git.

Combina quatro coisas:

1. **Varredor mecânico** — comandos que se repetem em toda auditoria
   (`gh issue view`, descoberta de commits/arquivos, scripts de gate).
2. **Pointer** — para cada item, aponta onde está o critério: o corpo
   da issue, `docs/LAYOUT.md`, `docs/GIT-WORKFLOW.md`, ADR citado. Não
   duplica regra — leva lá.
3. **Guardrail anti-viés** — força uma segunda passada que não está no
   checklist, porque verde de checklist ≠ issue bem entregue.
4. **Disciplina de escopo** — para cada achado/melhoria, classificar
   POR ESCOPO antes de recomendar: **dentro desta issue**, **issue
   separada**, ou **não-issue**. Esta é a parte que mais escapa.

> **Julgamento read-only; aplicação é fase separada.** A **passada de
> auditoria** é read-only por design (anti-viés: o veredito se forma sem a
> mão no conserto). Terminado o julgamento, a **fase de aplicação** empurra
> os fixes para o **PR existente** (push + atualiza corpo/checklist),
> completa as caixinhas validadas e **registra a auditoria no PR** —
> obrigatório, não opcional: (1) comentário com o veredito (status global +
> gates numéricos + fixes aplicados com hash) e (2) a nota de handoff
> "⚠️ precisa de auditoria" do corpo trocada por "✅ auditoria realizada em
> <data> — <veredito>". Auditoria sem marca no PR **não existe** para quem
> decide o merge. **Nunca faz merge** — é do usuário, salvo
> pedido explícito. Branch alheia: `git show` para ler; checkout + push para
> aplicar.

---

## Quando usar

- Usuário pede explicitamente ("audita issue #68", "valida a #N",
  "a issue X está pronta pra PR?", "tem gap?", "audita o épico #M").
- Antes de abrir PR que fecha uma issue (gate de saída, antes do
  `gh pr create`).
- Antes de `gh pr merge` de um PR com `Closes #N` (auditoria do reviewer).
- Ao retomar uma issue parada — confirmar se o que parece entregue
  está mesmo entregue (e se o `done` do roadmap reflete a realidade).
- **Grupo de issues / épico:** auditar N issues correlatas de uma vez,
  conferindo também a **fronteira entre elas** (escopo de uma vazou
  para o card da outra? dependência entre elas respeitada?).
- Auditar issue em **branch alheia** sem trocar working tree: use
  `git show <branch>:<path>` em vez de `Read` direto, e
  `git diff origin/<base>...<branch> --name-only` para o inventário.
  (Esta sessão teve um *flip* de checkout no meio — read-only + `git show`
  evita decidir sobre estado errado da árvore.)

**NÃO usar para:**
- Auditar uma **Stage** do pipeline (tem `concept.md`/`technical.md`,
  invariantes I*, ADRs) — usar `stage-audit`.
- Revisão de PR comum sem issue associada — usar `review`/code review.
- Auditoria de segurança — usar `security-review`.
- Verificar feature no navegador — usar `verify`/`run`.

---

## Workflow

### Fase A — Carregar contexto (a issue é a fonte da verdade)

1. **Ler o corpo da issue inteiro** no GitHub — **não** o título da
   tabela do roadmap, **não** a memória:
   ```bash
   gh issue view <num> --json number,title,body,state,labels
   ```
   Anotar, em ordem de prioridade de auditoria:
   - **`## Escopo`** — o que está dentro/fora. É o contrato do que
     deveria ter sido feito.
   - **`## Critério de aceitação`** — os checkboxes `- [ ]`. Cada um
     vira uma linha do mapeamento critério↔evidência (Fase C).
   - **`## Problema`** — o porquê; ajuda a julgar se a solução ataca a
     causa ou só o sintoma.
   - **`## Referências`** — arquivos/pontos de toque citados; viram o
     inventário esperado de arquivos tocados.
2. **Estado da issue vs roadmap vs branch** (registrar, não bloquear):
   - `state` no GitHub (`OPEN`/`CLOSED`).
   - Status na tabela do `docs/roadmap.md` (`open`/`done`).
   - Branch mergeada em `develop`?
   - **Divergência é normal pré-merge** (roadmap pode marcar `done`
     antes do merge; GitHub fica `OPEN` até o PR fechar). Mas o status
     do roadmap é **indício, não verdade** — a verdade é git + código +
     critério de aceitação. Não deixe um `done` no roadmap encurtar a
     auditoria.
3. **Grupo de issues / épico:** se o alvo é mais de uma issue, listar
   todas e suas relações antes de julgar qualquer uma:
   ```bash
   gh issue view <epico> --json body          # sub-issues listadas no corpo
   gh issue list --search "<termo do épico>" --state all
   ```
   Anotar dependências declaradas (issue B depende de A done?) e
   possíveis sobreposições de escopo entre os cards.
4. **Mapear commits → tasks da issue.** Issue avulsa usa tag
   `[#<num>/task-NN]` (ou `[#<num>/--]` para off-task) no commit:
   ```bash
   git log --grep="#<num>" --oneline
   git log --oneline origin/<base>..HEAD       # se a branch é a da issue
   ```
   Cada commit deveria entregar uma fatia coerente do `## Escopo`.
5. Ler docs referenciados **sob demanda** (LAYOUT §3 se há dúvida de
   import; GIT-WORKFLOW §Gates de PR; ADR citado no corpo da issue).

### Fase B — Varredores mecânicos (read-only; capturar números)

```bash
# Sanity do branch
git status
git log --oneline origin/<base>..HEAD     # base = develop (ou main em hotfix)
                                           # carona de outro escopo? (GIT-WORKFLOW §Etapa 4)

# Inventário de arquivos da issue
git diff --name-only origin/<base>..HEAD

# Scripts de gate do projeto (vivem em scripts/)
uv run python scripts/check_layout.py

# Gate completo (o mesmo que a CI roda)
make check

# Coverage focada nos arquivos tocados pela issue (não a média global)
uv run pytest <testes da issue> \
  --cov=<paths tocados> --cov-report=term-missing
```

**Capturar números, não impressões:** "1779 passed, 98.15% coverage"
é evidência; "tudo verde" não é.

**Antes de declarar `make check` verde, ler o target no `Makefile`** —
confirmar que cada gate declarado em config (`fail_under`, `import-linter`,
`mypy --strict`, `bandit`) é mesmo invocado. Config que nenhum comando
dispara é decoração (conceito "Gate inerte ou míope").

**Antes de atribuir um gate vermelho à branch** — checagem barata de
**falso vermelho ambiental**: se o erro aponta arquivo com
`git diff origin/develop -- <arquivo do erro>` **vazio** e o CI de
develop está verde, a causa provável é env drift do worktree (`.venv`
dessincronizado; deps novas em develop). `uv sync --extra dev` e
re-rodar **antes** de registrar finding (conceito "Falso vermelho
ambiental").

### Fase C — Cruzar implementação ↔ corpo da issue

1. **Arquivos tocados vs `## Escopo`/`## Referências`.** Os pontos de
   toque citados foram mexidos? Apareceu arquivo **fora** do escopo
   declarado (pode ser legítimo — pode ser escopo escapando)?
2. **Ler cada arquivo de implementação** (batches via Read) e comparar
   contra **cada bullet do `## Escopo`**. Um bullet de escopo sem
   código correspondente = finding.
3. **Mapear cada `## Critério de aceitação` → evidência.** Para cada
   `- [ ]`/`- [x]`:
   - **Marcado `[x]`** precisa de comando/arquivo:linha/teste que
     prova. ✅ sem evidência citada = finding (conceito
     "Verificação assimétrica").
   - **Não marcado `[ ]`** mas o escopo foi entregue = atualizar a
     issue (observação, não blocker).
   - **Critério condicional ("quando X novo aparecer, o gate faz Y"):**
     prove com uma **sonda untracked** — crie o artefato mínimo que
     dispara o critério (ex.: um módulo temporário com import proibido
     entre camadas para provar que `check_layout.py` acusa), rode o
     gate, confirme o Y, delete a sonda. Prova em segundos, sem tocar
     nada versionado.
4. **Literalidade do quantificador do critério (aprendizado-chave).**
   Ler a **palavra exata** do critério e exigir que a cobertura bata
   com ela:
   - "testes cobrindo o handler **GLOBAL**" ≠ testar a *função de
     registro* isolada num app-sonda. "Global" = ativo na app real
     (`create_app()`/composition boot). Se só há teste-sonda, falta o
     teste da **fiação** — finding.
   - "**qualquer** rota com exceção retorna X" ≠ uma rota. "todos os
     BCs" ≠ um BC. O teste tem que honrar o quantificador.
5. **Dead-config / dead-code check (aprendizado-chave).** Para cada
   peça nova ou tocada (handler, middleware, config loader, validator,
   função de boot), achar **≥ 1 call-site real fora do próprio teste**:
   ```
   Grep "<nome>"   # no projeto inteiro, excluindo o arquivo de teste
   ```
   Coverage 100% num módulo só prova que o **teste dele** roda — pode
   estar definido e **nunca plugado** no pipeline real (ex. clássico:
   `configure_logging` existia e não era chamado por ninguém até ser
   ligado no boot). Definido-sem-chamador = finding.
6. **Docs derivados.** `docs/roadmap.md`: status da issue na tabela e
   frontmatter (`updated_at`/`last_reviewed_at`) coerentes? (Issue
   **não** tem `§7 post-execution` — isso é de Stage; não cobrar aqui.)

### Fase D — Judgment por tipo de mudança (não se mecaniza)

Issues tocam as mesmas camadas das Stages; aplicar a sub-seção de cada
camada que a issue inclui (olhar os arquivos do diff). Piso, não teto.

- **`domain`:** imports só de stdlib + `domain/`; VOs `frozen=True`;
  exceções herdam de `DomainError`. (hex-arch-python, ddd-tactical-patterns)
- **`application`:** use case recebe/devolve **DTO**, nunca entidade;
  ports são `Protocol`; testado com **fake**, não mock; DTO é
  `@dataclass(frozen=True)` (pydantic só na fronteira HTTP). (pytest-with-fakes)
- **`adapters/out`:** implementa o Protocol; **contract test** fake+real;
  mapper puro; padrão async/threading consistente entre métodos; carga
  de recurso externo via `importlib.resources`, não `Path(__file__)`.
  (repository-pattern)
- **`adapters/in/http`:** router fino, sem regra de negócio; pydantic só
  na fronteira; **mapeamento erro→status bidirecional** (cada erro
  declarado tem `except`; cada `except` aparece no contrato). (fastapi-thin-adapter)
- **`adapters/in/scheduler`:** gated por flag (default `False`);
  `start`/`shutdown` idempotentes; cron validado cedo; warning quando
  lista vazia; erro do job capturado dentro do runner.
- **`composition_root`:** wiring no único arquivo permitido; adapter
  real substitui a fake. (composition-root)
- **`shared/infrastructure/http` (transversal, comum em issue de infra):**
  handler/middleware **registrado** no boot (não só definido); resposta
  de erro **sanitizada** (sem SQL/driver/segredo/stack ao cliente);
  detalhe interno só no **log**; ordem de middleware correta (ex.:
  catch-all interno ao CORS para a resposta de erro manter headers).

### Fase D-bis — Anti-viés (obrigatório antes de fechar)

> Existe porque checklist verde não significa issue bem entregue.
> Estes prompts forçam uma segunda passada que **não está na lista**.

1. **Disciplina de escopo (o anti-viés central desta skill).** Para
   **cada** achado/melhoria, classifique POR ESCOPO **antes** de
   recomendar — e **não** decida "é melhoria futura" só porque a issue
   parece fechada/`done`. O teste é o escopo, não o status:
   - **DENTRO desta issue** se: toca o **mesmo entregável / as mesmas
     linhas** que a issue criou, **ou** um `## Critério de aceitação`
     literal exige (ex.: o critério diz "handler global", e o que falta
     é justamente o teste da fiação global). → recomendar **implementar
     na própria branch da issue**, não num follow-up. Follow-up que
     mexeria nas mesmas linhas é fragmentação.
   - **ISSUE SEPARADA** se: é **capacidade nova / dependência nova /
     outro módulo** (ex.: trocar o *formato* do log para JSON é
     transporte, distinto do *mapeamento* de erro). Antes de propor o
     card, **buscar no backlog** (`gh issue list --search ... --state all`)
     e, se houver sub-issue aberta cujo escopo comporta, **anexar nela**
     em vez de abrir card concorrente (GIT-WORKFLOW §Etapa 1 +
     git-versioning-pointer §Criar issue). **Se a melhoria é separada
     mas ainda abstrata/incerta** (não se sabe se vai mesmo precisar) **e
     não se auto-anuncia** (esquecê-la geraria bug/dívida silenciosa, não
     um erro barulhento): ainda assim **registre como issue** — finding
     solto em docstring/`technical.md` tem risco de esquecimento
     permanente. Marque a incerteza explícita no corpo (`## Incerteza` +
     label `status: speculative`), declare o **momento previsto** (data
     *ou* condição de disparo, ex.: "quando o ERP modelar multi-parcelas")
     e **não crave a solução** como definitiva — é ponto de partida a
     reavaliar na implementação. Regra completa em GIT-WORKFLOW §Etapa 1.
   - **NÃO-ISSUE** se: é YAGNI **e se auto-anuncia sem custo** quando
     precisar (ex.: handler para uma exceção que nada levanta hoje; o
     catch-all já dá fallback seguro — esquecê-lo não custa nada, reaparece
     sozinho). Registrar a observação e seguir — não poluir o backlog com
     card especulativo. *Discriminador vs. ISSUE SEPARADA especulativa:* a
     melhoria **se auto-anuncia sem custo** (NÃO-ISSUE) ou é **incerta mas
     silenciosa / com risco de esquecer** (vira issue especulativa)?
   > Conceito de falso verde associado: **"Escopo empurrado pra frente"**
   > — adiar um refino que é da própria issue como se fosse futuro.
2. **Pergunta meta:** "Se eu soubesse que quem fechou esta issue tem
   histórico de mergear com bug, o que eu olharia?" — liste 2-3 itens
   **específicos desta issue** e cheque ≥ 1. Itens triviais (`make check`
   passou? coverage ≥ 90%?) **não contam** — já foram na Fase B.
3. **A solução ataca a causa do `## Problema`, ou só o sintoma?** Reler
   o `## Problema` e confirmar que o `## Escopo` entregue o neutraliza
   de verdade (não um caso particular dele).
4. **Caça ao silencioso:** no diff novo, procure `# TODO`/`FIXME`/`XXX`,
   `pytest.skip`/`xfail`, `# type: ignore`/`cast(`/`: Any` em boundary,
   `# noqa`. Cada um pede 1 linha de justificativa (commit/comentário).
   Sem justificativa = finding (conceito "Rastro perdido").
5. **Caça ao teste preguiçoso:** abra 2-3 testes do diff e leia os
   asserts. Sinais (cada um = finding): `assert x is not None` sem o
   valor concreto; `isinstance` como prova de comportamento;
   `mock.assert_called()` sem `_with(...)`; "happy path" que só checa
   presença de campo, não valor; `pytest.raises(Exception)` genérico
   em vez do tipo do contrato.
6. **Caça ao não-previsto:** arquivos/funções fora do `## Escopo`/
   `## Referências`. Refactor legítimo ou escopo escapando?
7. **Grupo de issues — fronteira entre cards:** o trabalho de uma issue
   vazou para a branch/PR de outra? Há `Refs #`/`Closes #` apontando
   para o card errado? Dependência declarada (B depende de A) foi
   respeitada na ordem de merge?
8. **Se fechou em < 5 min** sem ler nenhum arquivo de implementação
   inteiro, está rasa — volte e leia os arquivos centrais.
9. **Se delegou a sub-agente:** exija no relatório **2-3 trechos
   verbatim** das partes críticas (assinaturas, boundary, registro no
   boot). Leia à mão. Sem verbatim, "rodei rápido" só foi terceirizado
   (conceito "Delegação cega").

### Fase E — Relatório (explicação do valor entregue + gate)

> **A saída tem DUAS funções no mesmo documento, sempre as duas:**
> **explicar em linguagem clara o que a issue entregou de valor**
> (seções 1-4) e **registrar o gate + findings** (seções 5-6). Não
> escolha uma — quem dispara "Audite issue #N" recebe as seis seções.
> Toda a varredura das Fases A-D-bis **alimenta** estas seções; ela não
> é a saída.

**Regras transversais (valem para TODAS as seções):**
- **Linguagem clara.** Escreva para quem não acompanhou a implementação.
  Cada termo técnico/jargão ganha uma glosa curta entre parênteses na
  primeira aparição — ex.: "value object (objeto imutável, comparado
  pelo valor e não por um id)", "port (interface que a aplicação
  declara e um adapter implementa)".
- **Lente de valor + design (o foco do usuário).** Em cada seção,
  responda implicitamente: *o que isto entrega de valor de fato?* e
  *foi projetado como módulo escalável e de responsabilidade bem
  definida — ou não?* Aponte explicitamente onde o design ajuda e onde
  acumula dívida.
- **Listas, não tabelas, nas seções 1-4.** A única tabela é a de
  critério↔evidência (seção 3).
- **Fato, não impressão.** Toda afirmação de "existe/funciona" aponta
  `arquivo:linha`, comando+resultado numérico, ou teste. Use links
  markdown clicáveis nos arquivos (seção 2).

```markdown
## Auditoria — Issue #<num> (<título curto>)   [ou: Issues #<a>, #<b>, ...]

### Status global: ✅ APROVADA SEM BLOQUEANTES | ⚠️ APROVADA COM FINDINGS | ❌ BLOQUEADA
Estado: GitHub <OPEN/CLOSED> · roadmap <open/done> · branch <mergeada?/em PR #N>

### 1. Conceitos principais
<breve descrição dos conceitos que a issue define/usa (do `## Escopo` e
`## Problema`). O que cada conceito existe para resolver. Jargão glosado
entre (). 2-5 bullets.>

### 2. Tasks → arquivos → o que entrega (lista, não tabela)
- **task-NN — <nome>**: mexeu em [arquivo](caminho), [arquivo](caminho)
  — entrega de fato: <o que passou a existir/funcionar, em linguagem clara>.
- ...

### 3. Gates de saída — o que a issue garante 100% que existe e funciona
Gate: <comando> → <resultado numérico>   (ex.: `make check` → 1779 passed, 98% cov)

| Critério de aceitação (corpo da issue) | Status | Evidência (arquivo:linha / comando→resultado / teste) |
|---|---|---|
| <texto do checkbox> | ✅/⚠️/❌ | <prova concreta> |

### 4. Decisões que impactam arquitetura / conceito / projeto
- <decisão> — impacto: <…>; valor de design vs dívida: <…>.

### 5. Findings / melhorias (classificados POR ESCOPO)
**F<N> — <título>** (blocker | non-blocker | observação)
- Contexto: <fato> · Onde: <arquivo:linha> · Por que importa: <consequência>
- Escopo: **dentro da #<num>** | **issue separada** | **não-issue**
- Recomendação: <proposta — não execute, proponha>

### 6. Aprendizados → skills
<algum padrão novo (falso verde, decisão recorrente, jargão mal
explicado) que vale virar/atualizar conceito numa skill? Qual skill e
qual conceito. Se nada novo: dizer "nada novo" explicitamente.>

### Conclusão
<2-4 linhas: que valor a issue entregou, quão bem modularizada
(escalável/responsabilidade), pronta pra PR/merge? o que falta? o que é
da issue vs futuro?>
```

**Classificação:**
- **blocker** — não atende um `## Critério de aceitação`, contradiz o
  `## Escopo`, faz teste/gate falhar, ou vaza detalhe interno ao cliente.
- **non-blocker** — desvio sem impacto funcional, refino dentro do
  escopo que dá pra fazer agora, doc derivado desatualizado.
- **observação** — info que o reviewer deve saber sem ação obrigatória
  (ex.: GitHub `OPEN` enquanto roadmap `done` — esperado pré-merge).

---

## Conceitos de falso verde (anti-checklist)

> Conceitos, não exemplos numerados: exemplo vira pattern-match (agente
> acha "limpo" porque nenhum caso bate exato). Quando aparecer falso
> verde novo, primeiro perguntar **qual conceito existente cobre**; só
> criar conceito novo se for padrão genuinamente novo.

### Escopo empurrado pra frente
Um refino que é **da própria issue** é parqueado como "melhoria futura"
porque a issue parece fechada (`done` no roadmap, muitos commits, etc.).
O status vira desculpa para não terminar o escopo.
- Sintoma: "isso fica pra um follow-up" sobre algo que mexeria nas
  **mesmas linhas** que a issue criou, ou que um critério literal exige.
- **Pergunta:** "este achado toca o mesmo entregável desta issue, ou é
  capacidade/módulo/dependência nova?" Mesmo entregável → é desta issue.
- **Tratamento:** classificar por escopo (Fase D-bis #1), não por
  status. Dentro → propor implementar na branch da issue. Separada →
  buscar backlog antes de abrir card (evita fragmentação). Não-issue →
  só observação.

### Verificação assimétrica
Confundir presença com ausência, ou execução com asserção; ou cobrir
*a peça* e assumir *a fiação*.
- ✅ marcado sem evidência citada; teste-sonda da função de registro
  tomado como prova do "handler **global**" (a fiação no boot fica sem
  teste); `assert "field_hash" in dto` "provando" ausência do raw.
- **Pergunta:** "este check prova o critério, ou só a contrapositiva /
  só a peça isolada?"
- **Tratamento:** para "global/qualquer/todos", exigir teste pela app
  real (`create_app()`/boot). Para invariante negativa, `Grep` ativo
  com **0 matches**. Para coverage alto, ler 2-3 asserts (D-bis #5).

### Definido mas não plugado (dead-config)
Módulo/handler/validator existe, tem coverage, mas **nenhum call-site
real** fora do teste — nunca entra no pipeline.
- Ex.: `configure_logging` existindo sem ser chamado no boot; validator
  com teste unitário verde mas nunca registrado no router.
- **Pergunta:** "qual linha de produção **chama** isto?"
- **Tratamento:** `Grep "<nome>"` no projeto excluindo o teste; exigir
  ≥ 1 call-site real. Zero = finding.

### Gate inerte ou míope
Config declara o gate mas nada invoca (**inerte**); ou invoca global e
mascara o granular (**míope**: média ≥ 90% com arquivo da issue em 70%).
- **Pergunta:** "qual comando real exercita este gate, e em que
  granularidade?"
- **Tratamento:** ler o target do Makefile/CI; rodar coverage focada
  nos arquivos da issue. Gate inerte = blocker (config que ninguém roda
  é decoração).

### Sintoma ≠ causa
O `## Escopo` entregue cobre um caso particular do `## Problema`, não a
causa. O critério passa para o exemplo testado, mas o problema real
reaparece por outra porta.
- **Pergunta:** "se eu trocar o input do exemplo por um vizinho, o
  problema volta?"
- **Tratamento:** reler `## Problema`, conferir que a solução é geral
  (ex.: catch-all para **qualquer** Exception, não só a do bug que
  originou a issue).

### Rastro perdido
Decisão (off-task, silenciador, refactor, doc parcial) sem registro
onde o reviewer procuraria.
- `[#<num>/--]` sem justificativa no body; `# type: ignore`/`# noqa`
  em boundary sem 1 linha de motivo; roadmap table atualizado mas
  frontmatter esquecido (ou inverso); commit de outro escopo de carona
  na branch da issue.
- **Tratamento:** non-blocker em geral (corrigir antes do PR); blocker
  se carona de escopo (pedir rebase — GIT-WORKFLOW §Etapa 4) ou padrão
  repetido em ≥ 3 lugares.

### Delegação cega
Sub-agente devolve OK em batch e o auditor lê só o resumo.
- **Pergunta:** "o resumo cita 2-3 trechos verbatim, ou só veredito?"
- **Tratamento:** exigir verbatim das partes críticas; ler à mão;
  re-prompt se não pediu. (D-bis #9)

### Falso vermelho ambiental
O **espelho** dos falsos verdes: gate vermelho local atribuído à branch
quando a causa é o ambiente (típico: `.venv` de worktree dessincronizado
— mypy/lint-imports falham em arquivo **intocado**). Custo invertido:
finding falso + investigação na branch errada.
- **Pergunta:** "o arquivo do erro mudou nesta branch, e o CI de develop
  está verde?" (`git diff origin/develop -- <arquivo>` vazio + CI verde
  ⇒ ambiente, não branch.)
- **Tratamento:** `uv sync --extra dev` e re-rodar o gate; só então
  julgar. Registrar como **observação**, nunca como finding da branch.

---

### Casos históricos (rastreabilidade do loop recursivo)

| Caso | Conceito | Onde aconteceu |
|---|---|---|
| Refino da própria issue adiado como "futuro" porque o roadmap já marcava `done` | Escopo empurrado pra frente | issue #68 (sessão de auditoria; itens 5.1 traceback e 5.4 teste global eram da própria #68) |
| Teste-sonda da função de registro tomado como prova do "handler global" | Verificação assimétrica | issue #68 critério "testes cobrindo o handler global" |
| `configure_logging` definido e nunca chamado no boot | Definido mas não plugado | issue #68 task-03 |
| JSON logging proposto como parte da #68 (era transporte, não mapeamento) → vira issue separada | Escopo empurrado pra frente (lado oposto: NÃO inflar a issue) | issue #68 → issue #169 |
| GitHub `OPEN` enquanto roadmap `done` lido como gap | (observação esperada) | issue #68 pré-merge |
| `make check` vermelho (mypy/lint-imports) em arquivo com diff 0 vs develop — `.venv` do worktree defasado | Falso vermelho ambiental | auditoria em worktree com `.venv` defasado |

Quando esta skill falhar (auditoria deu verde, reviewer/CI/produção
pegou algo): **primeiro perguntar qual conceito existente cobre**.
Adicionar caso novo na tabela. Só criar conceito novo se for padrão
genuinamente novo.

---

## Anti-padrões a evitar

Os **Conceitos de falso verde** acima são a lista de anti-padrões de
*conteúdo* (✅ sem evidência → Verificação assimétrica; `make check` verde
tomado como auditoria → Gate inerte; empurrar refino da própria issue →
Escopo empurrado pra frente; follow-up sem buscar backlog → tratamento do
mesmo conceito). Não há por que repeti-los aqui.

Sobram só os anti-padrões de **procedimento** (não são conceito de falso
verde — são regra de execução, já ancorada acima):
- **Não editar código na passada de julgamento** — read-only (anti-viés); a
  correção vai para a **fase de aplicação** separada, que empurra os fixes
  para o PR (ver callout no topo). Merge nunca — é do usuário.
- **Não auditar sem ler o corpo da issue inteiro** — é a única fonte do
  "porquê" e do contrato (Fase A #1). Sem ele vira inspeção sem âncora.

---

## Mapa rápido (onde está cada critério)

| Procura por... | Está em |
|---|---|
| Escopo da issue (dentro/fora) | corpo da issue → `## Escopo` |
| Critérios de aceitação | corpo da issue → `## Critério de aceitação` (checkboxes) |
| Problema/causa que a issue ataca | corpo da issue → `## Problema` |
| Pontos de toque esperados | corpo da issue → `## Referências` |
| Estado real da issue | `gh issue view <num> --json state` |
| Commits da issue | `git log --grep="#<num>"` (tag `[#<num>/task-NN]`) |
| Carona de outro escopo | `git log --oneline origin/<base>..HEAD` |
| Regras de import / layers | `docs/LAYOUT.md` §3 + `hex-arch-python` skill |
| Gates de PR (CI verde, ≥90%, aprovação) | `docs/GIT-WORKFLOW.md` §Gates de PR |
| Convenção de commit/branch/PR de issue avulsa | `docs/CONVENTIONS.md` §4 + `git-versioning-pointer` |
| Buscar issue duplicada antes de criar follow-up | `git-versioning-pointer` §Criar issue + GIT-WORKFLOW §Etapa 1 |
| Validador estrutural | `scripts/check_layout.py` |

---

## Skills relacionadas

- `stage-audit` — a irmã desta skill, para **Stages** do pipeline
  (com `concept.md`/`technical.md`/invariantes/ADRs). Muitos conceitos
  de falso verde são compartilhados.
- `git-versioning-pointer` — antes de qualquer git/GitHub pós-auditoria
  (push, PR, merge, abrir issue de follow-up).
- `hex-arch-python`, `ddd-tactical-patterns`, `pytest-with-fakes`,
  `repository-pattern`, `fastapi-thin-adapter`, `composition-root` —
  para julgar o diff por camada na Fase D.
- `skill-builder` — quando esta skill falhar em prevenir um falso
  verde, refinar a seção "Conceitos de falso verde" (conceito existente
  primeiro; conceito novo só se padrão genuinamente novo).