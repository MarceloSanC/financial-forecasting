---
name: stage-audit
description: Auditoria de uma Stage do pipeline antes do PR/merge — passada de julgamento read-only (confere se o que foi implementado bate com `concept.md`/`technical.md`, se os gates passam e se há gaps/findings bloqueantes) + fase de aplicação separada que empurra os fixes ao PR existente e registra o veredito. Invocar quando o usuário pedir "auditar stage N.M", "auditoria da stage", "valida stage", "stage X está pronta para PR?", "tem gap na stage?", "tudo verde para abrir PR?", "confere se o stage X fechou", ou ao revisar uma stage de outra sessão. Triggers em PT. Skill de PROCEDIMENTO + GUARDRAIL — codifica o varredor mecânico (quais scripts rodar, quais arquivos cruzar) e protege contra o falso verde do checklist (anti-viés: a auditoria que só marca caixinhas perde o achado que importa). Lean toward triggering — custo de auditar é baixo, custo de mergear stage com gap silencioso é alto. A SAÍDA não é só relatório de gate — sempre produz, em linguagem clara (jargão glosado entre parênteses) e com lente de valor + design escalável/responsabilidade: (1) overview e conceitos, (2) tasks→arquivos (links)→o que entrega, (3) gates garantidos 100%, (4) decisões de arquitetura, (5) findings por escopo, (6) aprendizados→skills. Disparada por "Audite stage N.M" / "auditar stage N.M".
metadata:
  status: accepted
  applies_when:
    camada_alvo: [any]
    invoked_at: [pre-pr, pre-merge, stage-review]
---

# Stage Audit (read-only)

Procedimento para **auditar uma Stage** depois que ela é declarada
`done` localmente e antes de abrir/mergear o PR. Combina três coisas:

1. **Varredor mecânico** — comandos e cruzamentos que se repetem em
   toda auditoria (descoberta de arquivos, scripts de gate, mapeamento
   de invariantes → testes).
2. **Pointer** — para cada item, aponta o trecho exato dos docs do
   próprio projeto que define o critério (concept §11, technical §3,
   PIPELINE §9.5, etc.). Não duplica regra — só te leva lá.
3. **Guardrail anti-viés** — instruções explícitas para que o agente
   **não termine** a auditoria apenas porque o checklist deu verde.
   Auditoria que vira "marcar caixinhas" é pior que nenhuma.

> **Julgamento read-only; aplicação é fase separada.** A **passada de
> auditoria** (Fases A–D-bis) é read-only por design — o anti-viés depende
> de o auditor formar o veredito **sem a mão no conserto** (senão racionaliza
> o próprio verde). Terminado o julgamento, a **fase de aplicação** empurra
> os fixes para o **PR existente** (push na branch + atualiza o corpo e o
> checklist do PR), **completa as caixinhas que a auditoria validou** e
> **registra a auditoria no PR** — obrigatório, não opcional: (1) comentário
> com o veredito (status global + gates numéricos + fixes aplicados com
> hash) e (2) a nota de handoff "⚠️ precisa de auditoria" do corpo trocada
> por "✅ auditoria realizada em <data> — <veredito>". Auditoria sem marca no
> PR **não existe** para quem decide o merge.
> **Nunca faz merge** — é do usuário, salvo pedido explícito. O push da fase
> de aplicação vai **apenas para a branch do PR sob auditoria** (nunca outra):
> se for branch de outra sessão, `git show` para ler e `checkout` + `push`
> **só nessa branch** para aplicar.

---

## Quando usar

- Usuário pede explicitamente ("audita stage 4.1", "valida stage X",
  "stage Y está pronto para PR?", "tem gap?").
- Antes de abrir PR de uma Stage (gate de saída da Fase 4, antes do
  `gh pr create`).
- Antes de fazer `gh pr merge` em PR de Stage (auditoria do reviewer).
- Ao retomar uma Stage que ficou parada — confirmar se o que está
  marcado `done` está mesmo `done`.
- Auditar Stage em **branch alheia** sem trocar working tree: use
  `git show <branch>:<path>` em vez de `Read` direto (e
  `git diff origin/<base>...<branch> --name-only` para o inventário).

**NÃO usar para:**
- Revisão de PR comum (não-Stage) — usar skill `review` ou code review
  manual.
- Auditoria de segurança — usar `security-review`.
- Verificar feature funcionando no navegador — usar `verify` ou `run`.

---

## Workflow

### Fase A — Carregar contexto (sem julgar ainda)

1. Ler **`docs/stages/<N.M>-<slug>/concept.md`** inteiro. Pontos-chave
   a anotar: §1 (escopo dentro/fora), §4 (contratos), §5 (invariantes
   I1..IN), §6 (casos de erro C1..CN), §7 (decisões D1..DN),
   §11 (critérios de aceitação A1..AN), §13 (questões em aberto Q1..QN).
2. Ler **`docs/stages/<N.M>-<slug>/technical.md`** inteiro. Pontos-chave:
   §1 (estratégia, estrutura de pastas), §2 (Tasks), §3 (gate de saída +
   mapping invariante↔teste), §7 (post-execution `[decision]`/`[finding]`/`[deviation]`).
3. Identificar **`camada_alvo`** no frontmatter — muda o checklist da
   Fase D (mono-layer domain ≠ vertical-slice multi).
4. Ler docs referenciados apenas **sob demanda** (ex.: `LAYOUT.md` §3
   se há dúvida sobre regra de import; `PIPELINE.md` §4.2/4.3 se há
   dúvida sobre atomicidade da Stage; `GIT-WORKFLOW.md` §Gates de PR).

### Fase B — Rodar varredores mecânicos (paralelo quando possível)

Todos read-only. Salvar saída para mapear contra concept/technical.

```bash
# Estado do branch (sanity)
git status
git log --oneline origin/$(base)..HEAD     # base = develop (ou main em hotfix)

# Scripts de gate do projeto (vivem em scripts/)
uv run python scripts/check_layout.py
uv run python scripts/check_technical_postexec.py docs/stages/<N.M>-<slug>/technical.md

# Testes + coverage da Stage
uv run pytest tests/unit/features/<bc>/<camada>/ -v \
  --cov=src/financial_forecasting/features/<bc>/<camada> \
  --cov-report=term-missing --cov-fail-under=90

# Gate completo (mesmo que CI vai rodar)
make check
```

**Capturar números, não impressões:** "143 passed, 100% coverage" é
evidência; "está tudo verde" não é.

**Antes de declarar `make check` verde, ler o target literal no
`Makefile`** — confirmar que cada gate declarado em config (`fail_under`
do `pyproject`, `import-linter`, `mypy --strict`, `bandit`, `safety`)
está mesmo invocado por algum comando do alvo `check`. Configuração que
nenhum comando dispara é decoração — conceito "Gate inerte ou míope".

**Antes de atribuir um gate vermelho à branch** — checagem barata de
**falso vermelho ambiental**: se o erro aponta arquivo com
`git diff origin/develop -- <arquivo do erro>` **vazio** e o CI de
develop está verde, a causa provável é env drift do worktree (`.venv`
dessincronizado; deps novas em develop). `uv sync --extra dev` e
re-rodar **antes** de registrar finding.

**Nota — pré-requisito de Stage anterior.** Stage atual pode declarar
a anterior como pré-requisito. Pré-requisito real é "mergeada em
`develop`", não "status `done` no roadmap local". Conferir com
`git log develop --oneline | head`. Se a anterior ainda não foi mergeada,
sinalizar ao usuário — não é blocker da auditoria atual, é blocker da
**ordem de merge**.

### Fase C — Cruzar implementação ↔ docs

1. **Listar arquivos novos/modificados** vs §technical §1 (estrutura
   de pastas). Comando: `git diff --name-only origin/<base>..HEAD`.
   Comparar com `arquivos_a_criar` / `arquivos_a_modificar` declarados
   no roadmap.md para a Stage.
2. **Ler cada arquivo de implementação** (parallel batches via Read).
   Comparar contra:
   - Contratos de concept §4 (assinaturas batem?)
   - Invariantes de concept §5 (`__post_init__` valida o que se prometeu?)
   - Decisões de concept §7 (a implementação segue D1..DN ou
     contradiz silenciosamente?)
   - Detalhes técnicos da Task em technical §2 (o "Detalhes técnicos"
     foi seguido?)
   - **Invariantes negativas** (`I*` com forma "X NÃO está em Y",
     ex.: "DTO não vaza PII raw", "domain não importa adapters") —
     `assert isinstance(...)` ou type-check cobrem presença, não ausência.
     Rodar `Grep` ativo (`pattern: "<X>"`, `path: <Y>/`) e exigir
     **0 matches**. Ver conceito "Verificação assimétrica".
3. **Mapear invariantes → testes**. Para cada `IN` em concept §5,
   localizar o teste que cobre (technical §3 já tem a tabela
   "mapping invariantes ↔ testes" — confirmar que existe e roda).
   Se faltar teste para uma invariante, é **finding**.
4. **Mapear critérios de aceitação (A1..AN) → evidência**. Cada `AN`
   tem que ter um comando ou inspeção que prova. `[ ]` não marcado
   sem evidência = finding.
   - **Critério condicional ("quando X novo aparecer, o gate faz Y"):**
     prove com uma **sonda untracked** — crie o artefato mínimo que
     dispara o critério (ex.: um `technical.md` temporário), rode o
     gate, confirme o Y, delete a sonda. Prova em segundos, sem tocar
     nada versionado.
5. **Verificar atualização de docs derivados** (gate clássico):
   - **5.a `docs/roadmap.md`:**
     - Status da Stage na tabela §"Stages" atualizado para `done`?
     - Frontmatter `updated_at` e `last_reviewed_at` na data do merge?
     - (Se aplicável) Step que contém a Stage avançou de `not_started`
       para `in_progress`?
   - **5.b ADRs derivados (se a Stage declarou D* com ADR formal):**
     - Para cada D* em concept §7 que diz `ADR: sim` (ou cita
       `docs/adr/N_M_NNNN-<slug>.md`), abrir o arquivo do ADR e
       confirmar **`status: accepted`** no frontmatter (não
       `draft`/`proposed`).
     - ADR novo em `draft` ao merge = blocker — a decisão precisa
       fechar antes da Stage fechar (CONVENTIONS §3).
6. **Verificar §7 post-execution do technical.md.** Se há `[decision]`,
   `[finding]` ou `[deviation]` na execução, foi registrado? Se o histórico
   git mostra commits `[N.M/--]` ou `[N.M/task-NN-extra]` (off-task),
   `§7` deveria ter a entrada justificando.

### Fase D — Judgment (a parte que NÃO se mecaniza)

Por camada-alvo, conferir o que muda. Os itens abaixo são **piso**, não
teto — sempre faça Fase D-bis (anti-viés) antes de fechar.

**Regra de aplicação:** para Stage **vertical-slice ou multi-layer**,
aplicar **todas** as sub-seções cujas camadas a Stage inclui (frontmatter
`camada_alvo` ou `arquivos_a_criar` do roadmap). Para Stage
**mono-layer**, aplicar só a sub-seção da camada-alvo.

**Se `camada_alvo` inclui `domain`:**
- Imports de `domain/` só de stdlib + outros `domain/` (LAYOUT §3 +
  hex-arch-python skill). `check_layout.py` cobre o estrutural;
  faltar checar imports de tipos pesados (`pydantic`, `sqlalchemy`,
  `fastapi`) — costuma vazar via type-hint só pra dataclass.
- `@dataclass(frozen=True)` em VOs, `eq=False` + `__eq__`/`__hash__`
  por id em entidades (ddd-tactical-patterns skill).
- Exceções herdam de `shared.domain.exceptions.base.DomainError` para
  o error handler HTTP futuro tratar como 422.
- `__init__.py` vazios (ou só docstring placeholder — verificar
  invariante literal vs espírito; ver conceito "Literal ≠ espírito").

**Se `camada_alvo` inclui `application`:**
- Use case recebe e devolve DTO — **nunca** entidade de domínio
  (LAYOUT §7 "Regras de ouro").
- Ports são `Protocol` em `application/ports/{in,out}/`.
- Use case testado com **fake** do port (pytest-with-fakes skill),
  não mock.
- **DTOs em `application/dtos/` são `@dataclass(frozen=True)` —
  `pydantic.BaseModel` só na fronteira `adapters/in/http`** (LAYOUT
  §7). Pydantic em DTO da application = boundary leak.

**Se `camada_alvo` inclui `adapters/out`:**
- Adapter implementa o Protocol (repository-pattern skill).
- **Contract test** existe e roda contra fake E real
  (`tests/contract/`).
- Mapper domain↔ORM existe e é puro (sem I/O).
- **Padrão async/threading:** se a Stage (ou Stage anterior do mesmo
  BC) declarou padrão de concorrência (ex.: D* "todo método `async`
  delega para `_sync` via `asyncio.to_thread`", ou "usar `AsyncEngine`
  fim a fim"), ler **1 método como amostra** e confirmar que segue.
  Inconsistência entre métodos do mesmo adapter = finding.
- **Carga de recursos externos** (arquivos `.sql`, templates, fixtures,
  schemas): conferir que usa **`importlib.resources.files(...)`** (ou
  equivalente robusto a wheel/editable install), **não**
  `Path(__file__).parent / "..."`. O segundo quebra em pacote instalado.

**Se `camada_alvo` inclui `adapters/in/http`:**
- Router fino — sem regra de negócio (fastapi-thin-adapter skill).
- Pydantic só na fronteira; converte DTO → schema.
- Exceções de domínio mapeadas para status HTTP coerentes —
  **bidirecionalmente**: se concept §6 declarou tabela `erro → status`,
  conferir que (a) **cada linha** da tabela tem um `except` correspondente
  no router e (b) **cada `except` no router** aparece na tabela. Integration
  test deveria cobrir cada status code declarado.

**Se `camada_alvo` inclui `adapters/in/scheduler`:**
- **Gated por flag** em `Settings` (default `False` — não arranca em
  CI/dev sem opt-in). Composition root constrói sempre; lifespan decide
  se chama `start()`.
- `start()` / `shutdown()` **idempotentes** — segunda chamada não
  duplica jobs nem quebra.
- **Cron string validada cedo** no startup (`CronTrigger.from_crontab(...)`
  levanta `ValueError`) — preferível a job falhar silenciosamente.
- **Warning explícito quando lista de unidades/jobs está vazia** —
  silêncio aqui esconde misconfig (scheduler rodando sem nada
  registrado).
- Erros do use case **capturados dentro do job runner** com log `ERROR`
  — uma exceção não tratada não pode matar o scheduler nem os outros
  jobs.

**Se a Stage toca `composition_root`:**
- Wiring no único arquivo permitido (`composition_root.py` —
  composition-root skill).
- Adapter real **substitui** a fake do use case.

### Fase D-bis — Anti-viés (obrigatório antes de fechar)

> **Esta seção existe porque checklist verde não significa Stage boa.**
> Skills criam falsos verdes ao fazer o agente confundir "rodei o
> procedimento" com "auditei substantivamente". Estes prompts forçam
> uma segunda passada que **não está na lista**.

1. **Disciplina de escopo.** Para cada finding/melhoria, classificar
   POR ESCOPO **antes** de recomendar — e **não** parquear como
   "futuro" um gap que é da própria Stage só porque o roadmap já diz
   `done` ou porque o §7/§13 oferece uma saída fácil:
   - **Dentro da Stage** (concept §1 "dentro" ou critério de aceitação
     A*) → corrigir antes do PR (ou virar Task, se ainda há ciclo). É a
     fatia que a Stage prometeu; follow-up que mexeria nas **mesmas
     linhas** é fragmentação, não cuidado.
   - **Q\* deferida-por-design** (concept §13) → só se a resposta
     provisória **não** dizia "fazer se trivial"; senão é
     Literal ≠ espírito (a Q* virou desculpa).
   - **Issue pós-Stage separada** → capacidade/dependência/módulo novo;
     **buscar o backlog antes** de abrir card (`gh issue list --search`;
     git-versioning-pointer §Criar issue) para não fragmentar.
   O teste é o **escopo** (concept §1 + A*), não o **status**. Ver
   conceito "Escopo empurrado pra frente".
2. **Pergunta meta:** "Se eu soubesse que o agente que fechou esta
   Stage tem **histórico de mergear com bug**, o que eu olharia?" —
   Liste 2-3 itens **específicos desta Stage** e confira pelo menos
   um. Itens triviais (`make check` passou? coverage ≥ 90%?) **não
   contam** — eles já foram checados na Fase B. O alvo aqui é
   substância: defaults numéricos coerentes (ex.: "os pesos da fórmula
   X somam 1.0?"), invariantes de negócio que o teste não cobre
   (ex.: "se `bucket_180_plus` é 100% da provisão, isso é conservador
   ou bug de YAML?"), comportamento sob entrada degenerada
   (ex.: "use case retorna o que se a lista vier vazia?").
3. **Caça ao silencioso:** Procure no diff novo por:
   - `# TODO`, `# FIXME`, `# XXX`, `pass  # noqa`
   - `pytest.skip`, `xfail`, `@pytest.mark.skip`
   - **Silenciadores de type-checker:** `# type: ignore`,
     `cast(`, `: Any` em ponto sensível (boundary de adapter,
     conversão de DTO/entidade, retorno de função pública)
   - **Silenciadores de linter:** `# noqa`, `# noqa: <code>`
   Cada ocorrência pede 1 linha justificando (em commit, comentário
   ou §6/§7 do concept). Ausência de justificativa = finding. Ver
   conceito "Rastro perdido".
4. **Caça ao não-previsto:** Procure por arquivos/funções/classes
   **fora** do que `arquivos_a_criar` do roadmap previu. Pode ser
   refactor legítimo — pode ser escopo escapando.
5. **Caça à decisão escondida:** Procure por `if`/`match` no código
   novo cujo critério **não** aparece em concept §6 (casos de erro)
   ou §7 (decisões). Decisão de comportamento sem rastro = finding.
   - **Sub-bullet — cross-check de uso ativo (dead-config check):**
     para validators/hooks/handlers/middlewares novos, encontrar
     **≥ 1 call-site fora do próprio teste**. Coverage 100% em
     validator só prova que o teste unitário dele roda — pode estar
     definido e nunca plugado no pipeline real. Comando útil:
     `Grep "<nome_do_validator>"` no projeto inteiro, excluindo o
     próprio arquivo de teste. Ver conceito "Definido mas não plugado".
6. **Caça ao teste preguiçoso:** abra 2-3 arquivos de teste no
   diff novo e leia os asserts. Sinais de preguiça (cada um = finding):
   - `assert result is not None` / `assert len(x) > 0` sem cobrir
     o valor concreto.
   - `assert isinstance(x, T)` usado como prova de comportamento
     (prova tipo, não comportamento).
   - `mock.assert_called()` sem `assert_called_with(...)` específico
     (prova que chamou, não com o quê).
   - Cenário rotulado "happy path" mas asserts só sobre presença de
     campos, não sobre valores numéricos calculados.
   - Teste de erro com `pytest.raises(Exception)` genérico em vez do
     tipo específico do contrato.
7. **Pense diferente do shape do checklist:** se a Stage é
   `mono-layer domain`, o checklist é curto; isso **não significa**
   que a auditoria é curta. Em mono-layer, o risco se concentra
   na modelagem — gaste mais tempo lendo as entidades/VOs do que
   rodando scripts.
8. **Se a auditoria fechou em < 5 minutos** sem ler nenhum arquivo
   de implementação inteiro, provavelmente está rasa. Volte e leia
   pelo menos os arquivos centrais da camada-alvo.
9. **Se delegou a sub-agente** (Explore, general-purpose) para
   carregar contexto ou checar itens em batch: o relatório dele
   precisa trazer **2-3 trechos de código verbatim** (não só
   veredito A/I/C) das partes críticas — Protocol assinaturas,
   mappers de boundary, §7 post-execution, validators de invariante.
   Leia esses trechos à mão e confirme. Sem isso, "rodei < 5 min"
   só foi **terceirizado**, não evitado (conceito "Delegação cega").
   Se o prompt do sub-agente não pediu verbatim, re-prompt antes de
   fechar.

### Fase E — Relatório (explicação do valor entregue + gate)

> **A saída tem DUAS funções no mesmo documento, sempre as duas:**
> **explicar em linguagem clara o que a Stage entregou de valor**
> (seções 1-4) e **registrar o gate + findings** (seções 5-6). Não
> escolha uma — quem dispara "Audite stage N.M" recebe as seis seções.
> Toda a varredura das Fases A-D-bis **alimenta** estas seções; ela não
> é a saída.

**Regras transversais (valem para TODAS as seções):**
- **Linguagem clara.** Escreva para quem não acompanhou a implementação.
  Cada termo técnico/jargão ganha glosa curta entre parênteses na
  primeira aparição — ex.: "invariante (regra que o objeto garante
  sempre verdadeira)", "port (interface que a aplicação declara e um
  adapter implementa)".
- **Lente de valor + design (o foco do usuário).** Em cada seção,
  responda implicitamente: *o que isto entrega de valor de fato?* e
  *foi projetado como módulo escalável e de responsabilidade bem
  definida — ou não?* Aponte onde o design ajuda e onde acumula dívida.
- **Listas, não tabelas, nas seções 1-4.** As tabelas (invariante↔teste,
  critério↔evidência) ficam na seção 3.
- **Fato, não impressão.** Toda afirmação de "existe/funciona" aponta
  `arquivo:linha`, comando+resultado numérico, ou teste. Links markdown
  clicáveis nos arquivos (seção 2).

```markdown
## Auditoria — Stage <N.M> (<slug>)

### Status global: ✅ APROVADA SEM BLOQUEANTES | ⚠️ APROVADA COM FINDINGS | ❌ BLOQUEADA
Estado: roadmap <not_started/in_progress/done> · branch <mergeada?/em PR #N> · pré-req <Stage anterior mergeada?>

### 1. Overview e conceitos principais
<o que a Stage se propõe (concept §1 escopo + overview) e os conceitos
que ela define/usa. O que cada conceito existe para resolver. Jargão
glosado entre (). 2-5 bullets.>

### 2. Tasks → arquivos → o que entrega (lista, não tabela)
- **Task NN (technical §2) — <nome>**: mexeu em [arquivo](caminho),
  [arquivo](caminho) — entrega de fato: <o que passou a existir/funcionar>.
- ...

### 3. Gates de saída — o que a Stage garante 100% que existe e funciona
Gate (concept §11 + technical §3): <comando> → <resultado numérico>

| Invariante / Critério (concept §5 / §11) | Status | Evidência (arquivo:linha / teste / comando→resultado) |
|---|---|---|
| I1 / A1 (...) | ✅/⚠️/❌ | <prova concreta> |

### 4. Decisões que impactam arquitetura / conceito / projeto
- <D* concept §7> — impacto: <…>; valor de design vs dívida: <…>; ADR: <status>.

### 5. Findings / melhorias (classificados POR ESCOPO)
**F<N> — <título curto>** (blocker | non-blocker | observação)
- Contexto: <fato> · Onde: <arquivo:linha> · Por que importa: <consequência>
- Escopo: **dentro da Stage** | **Q\* deferida** | **issue pós-Stage** | **não-issue**
- Recomendação: <proposta — não execute, proponha>

### 6. Aprendizados → skills
<algum padrão novo (falso verde, decisão recorrente, jargão mal
explicado) que vale virar/atualizar conceito numa skill? Qual skill e
qual conceito. Se nada novo: dizer "nada novo" explicitamente.>

### Conclusão
<2-4 linhas: que valor a Stage entregou, quão bem modularizada
(escalável/responsabilidade), pronta pra PR? o que falta?>
```

**Regra de classificação:**
- **blocker** — viola invariante I*, contradiz decisão D*, faz teste
  falhar, ou faz script de gate falhar.
- **non-blocker** — desvio do plano sem impacto funcional, sugestão
  de melhoria, falsa positiva conhecida (`__init__.py` com docstring
  é exemplo).
- **observação** — info que o reviewer humano deve saber mas não
  exige ação (ex.: coverage de arquivo de Stage anterior está em 0%).

---

## Conceitos de falso verde (anti-checklist)

> Esta seção é **conceitos**, não exemplos numerados. Por quê:
> exemplo vira pattern-match — agente acha "limpo" só porque nenhum
> caso bate exatamente. Conceito força raciocínio: "qual destes
> padrões está acontecendo aqui?"
>
> Quando aparecer falso verde novo, primeiro perguntar **qual
> conceito existente cobre**. Só criar conceito novo se for padrão
> genuinamente novo. Casos individuais entram na tabela de
> rastreabilidade no fim.

### Escopo empurrado pra frente

Um gap que é da **própria Stage** (concept §1 "dentro", critério A*, ou
uma Q* cuja resposta provisória dizia "fazer se trivial") é parqueado
como "issue futura"/Q*/§7 porque a Stage **parece** fechada (`done` no
roadmap, §7 já escrito, muitos commits). O status — ou o escape-hatch
do §7/§13 — vira desculpa para não terminar o escopo.

- Sintoma: "isso fica pra depois" sobre algo que mexeria nas **mesmas
  linhas** que a Stage criou, ou que um critério A* exige na letra.
- O oposto também é falso verde: **inflar** a Stage puxando para ela
  capacidade que é de outra (aí o certo é issue pós-Stage separada).

**Pergunta:** "este achado é da fatia que esta Stage prometeu, ou é
capacidade/módulo novo?"

**Tratamento:** classificar por escopo (D-bis #1), não por status.
Dentro → corrigir/Task antes do PR. Fora → issue pós-Stage (buscar
backlog antes). Roadmap `done` não encurta a auditoria nem move o gap
para "futuro".

### Literal ≠ espírito

Regra escrita não captura a intenção real. Acontece quando:
- Docs/invariantes copiados entre Stages (concept §I, ADR herdado)
  ficam fora de sincronia com o código que evoluiu.
- Código tecnicamente atende a invariante mas não o espírito (ex.:
  `__init__.py` com docstring "vazio até Stage X" — literalmente
  não-vazio, mas `Stmts: 0` no coverage).
- Question Q* marcada "não trava" deixa de ser implementada quando
  a resposta provisória dizia "fazer se trivial".

**Pergunta:** "esta regra ainda descreve o que a Stage realmente quer?"

**Tratamento:** se regra **strict demais** (gate cobre, código viola,
ADR justifica) → finding non-blocker, alinhar regra com o gate
real. Se **strict de menos** (gate cego, intenção burlada) → blocker.
Para divergência §I vs gate estrutural: ver se ADR justifica
relaxamento; se sim, §I errado; se não, decisão escondida (D-bis #5).

### Verificação assimétrica

Confundir presença com ausência, ou execução com asserção. O check
prova um lado, a auditoria assume o outro.

- `assert "field_hash" in dto` prova **presença do hash**, não
  **ausência do raw** — afirmações independentes.
- Coverage 100% prova **linha executada**, não **resultado
  verificado** (`def test_foo(): foo()` sem assert tem coverage cheio).

**Pergunta:** "este check prova o que eu queria, ou só a contrapositiva?"

**Tratamento:** para invariante negativa ("X NÃO em Y"), rodar
`Grep "<X>"` em Y/ e exigir **0 matches**. `check_layout.py` cobre
algumas estruturais (LAYOUT §3) mas **não** as específicas da Stage.
Para coverage alto, abrir 2-3 arquivos de teste e ler asserts
(Fase D-bis #6).

### Gate inerte ou míope

Config declara o gate, mas nada o invoca (**inerte**); ou invoca de
forma global e mascara comportamento granular (**míope**).

- Inerte: `[tool.coverage.report] fail_under = 90` no pyproject mas
  `make check` roda `pytest` sem `--cov`. Gate decorativo.
- Míope: `fail_under = 90` global passa, mas arquivo individual da
  Stage está em 75% porque outros puxam a média.

Mesmo padrão para `import-linter`, `bandit`, `safety`, `mypy --strict` —
config existe, falta invocação ou granularidade.

**Pergunta:** "qual comando real exercita este gate, e em que
granularidade?"

**Tratamento:** ler o target do Makefile (ou job do CI) e confirmar
invocação. Para coverage, rodar
`pytest --cov=src/financial_forecasting/features/<bc>/<camada>` focado. Gate
inerte é **blocker** (configuração que ninguém roda é decoração).

### Definido mas não plugado (dead-config)

Módulo/handler/validator/middleware existe, tem coverage, mas **nenhum
call-site real** fora do próprio teste — nunca entra no pipeline. Parente
do "Gate inerte", mas do lado do código: a peça roda no teste unitário e
**não** no fluxo de produção.

- Validator/guard com teste verde mas nunca registrado no router/app.
- Config loader (ex.: `configure_logging`) definido e jamais chamado no
  boot/composition root.

**Pergunta:** "qual linha de produção **chama/registra** isto?"

**Tratamento:** `Grep "<nome>"` no projeto inteiro **excluindo** o arquivo
de teste; exigir **≥ 1 call-site real**. Zero = finding. Codificado no
sub-bullet de uso ativo (D-bis #5). Coverage 100% num módulo prova que o
**teste dele** roda, não que o **pipeline** o usa.

### Estrutural ≠ semântico

Tipo/assinatura/import bate com o que o concept pediu, mas a intenção
semântica (instância compartilhada, decisão consciente, comportamento)
ficou perdida.

- D* "X compartilhado entre A e B" → ambos têm `engine: Engine` no
  construtor (estrutural OK), mas composition root injeta duas
  instâncias diferentes (semântica quebrada).
- Use case implementa `IPort` (tipo OK), mas comportamento contradiz
  o contrato do Protocol em casos não testados.

**Pergunta:** "este tipo/assinatura prova o comportamento que o
concept prometeu, ou só a forma?"

**Tratamento:** para cada D* do tipo "X compartilhado", abrir
`composition_root.py` e **contar instanciações** de X (`Grep` por
`create_engine(`, `httpx.AsyncClient(`, etc.) — exatamente 1
esperada, com o mesmo handle injetado em ambos os callers.

### Rastro perdido

Decisão tomada (off-task, silenciador, refactor inesperado, doc
parcialmente atualizado) sem registro onde o reviewer iria procurar.

- Commit `[N.M/task-NN-extra]` ou `[N.M/--]` sem entrada `[deviation]`
  em technical §7 (CONVENTIONS §3.4).
- `# type: ignore`, `cast(...)`, `: Any`, `# noqa` em ponto sensível
  (boundary de adapter, mapper DTO↔entidade, retorno público) sem
  justificativa próxima.
- `roadmap.md` table atualizado mas frontmatter (`updated_at`,
  `last_reviewed_at`) esquecido — ou inverso.
- Branch com commit de outro escopo (`fix:` solto, `chore: bump`)
  pegando carona no PR da Stage.

**Pergunta:** "se o reviewer abrir só este arquivo/commit, ele
entende por que esta linha/commit está aqui?"

**Tratamento:** non-blocker em geral, corrigir antes do PR. Blocker
se padrão repetido em ≥3 lugares no mesmo arquivo, ou se for carona
de escopo (pedir rebase — GIT-WORKFLOW §Etapa 4).

### Delegação cega

Sub-agente (Explore, general-purpose) ou ferramenta devolve OK em
batch, e o auditor lê só o resumo.

- Sub-agente alucina referência (`arquivo:linha` que não confere)
  ou afirma "Protocol X bate" sem ter lido o arquivo inteiro.
- Tabela A/I/C com 30 itens marcados OK vira ✅ no relatório sem
  verificação amostral.

**Pergunta:** "o resumo cita 2-3 trechos verbatim, ou só veredito?"

**Tratamento:** quando delegar, exigir no prompt que o relatório
traga **2-3 trechos literais** das partes críticas (Protocol
assinaturas, mappers de boundary, §7 post-execution, validators de
invariante negativa). Ler à mão e conferir. Se não pediu verbatim,
re-prompt antes de fechar. Codificado em Fase D-bis #9.

### Falso vermelho ambiental

O **espelho** dos falsos verdes: gate vermelho local atribuído à branch
quando a causa é o ambiente (típico: `.venv` de worktree dessincronizado
— mypy/lint-imports falham em arquivo **intocado**). Custo invertido:
finding falso + investigação na branch errada.

- Sintoma: `make check` falha em arquivo que a branch não tocou; deps
  "sumidas" (`sqlalchemy`, `lint-imports`) num worktree criado antes de
  develop avançar.

**Pergunta:** "o arquivo do erro mudou nesta branch, e o CI de develop
está verde?" (`git diff origin/develop -- <arquivo>` vazio + CI verde
⇒ ambiente, não branch.)

**Tratamento:** `uv sync --extra dev` e re-rodar o gate; só então
julgar. Registrar como **observação**, nunca como finding da branch.
Codificado na checagem barata da Fase B.

---

### Casos históricos (rastreabilidade do loop recursivo)

Cada linha é um falso verde já observado, mapeado ao conceito que o
cobre. Cresce sem inflar a seção conceitual.

| Caso | Conceito | Onde aconteceu |
|---|---|---|
| Refino in-scope adiado como "futuro" porque o roadmap já dizia `done` | Escopo empurrado pra frente | auditoria de Stage (espelhado na skill issue-audit) |
| `__init__.py` placeholder herdado | Literal ≠ espírito | recorrente em camadas vazias |
| Q* "não trava" sem follow-through | Literal ≠ espírito | concept §13 |
| §I copiado literal vs ADR de relaxamento | Literal ≠ espírito | §I herdado vs ADR de relaxamento (pydantic em application) |
| Coverage global mascara arquivo individual | Gate inerte ou míope (míope) | repetente |
| Gate em pyproject sem invocação em `make check` | Gate inerte ou míope (inerte) | recorrente |
| Config/validator com teste verde mas sem call-site real (ex.: `configure_logging` nunca chamado no boot) | Definido mas não plugado | recorrente (peça testada, não plugada no boot) |
| Teste cobre branch sem assertar resultado | Verificação assimétrica | repetente |
| Invariante negativa sem `Grep` ativo | Verificação assimétrica | recorrente em camadas com PII/boundary |
| Engine compartilhado vira 2 instâncias | Estrutural ≠ semântico | D3 da 3.1 |
| `roadmap.md` table sem frontmatter (ou inverso) | Rastro perdido | recorrente |
| Branch com carona de outro escopo | Rastro perdido | GIT-WORKFLOW §Etapa 4 |
| Silenciador sem justificativa em mapper | Rastro perdido | recorrente em fronteiras async↔sync |
| Commit off-task sem `[deviation]` em §7 | Rastro perdido | CONVENTIONS §3.4 |
| Sub-agente alucina `arquivo:linha` | Delegação cega | repetente em auditorias longas |
| `make check` vermelho em arquivo com diff 0 vs develop — `.venv` do worktree defasado | Falso vermelho ambiental | worktree com `.venv` defasado (espelhado na issue-audit) |
| Critério A* exige teste numa perna onde o comportamento é **inatingível por construção** (C5 na perna fake: emissão tipo-7 de labels finitos é sempre finita) — pergunta-guia: "esta perna CONSEGUE exibir o comportamento?" | Literal ≠ espírito | auditoria 5.3 (A8/C5); errata em §7 em vez de retocar o concept |

Quando esta skill falhar (auditoria deu verde, reviewer/CI/produção
pegou algo): **primeiro perguntar qual conceito existente cobre**.
Adicionar caso novo na tabela. Só criar conceito novo se for padrão
genuinamente novo — caso contrário, refinar o conceito existente.

---

## Anti-padrões a evitar

Os **Conceitos de falso verde** acima são a lista de anti-padrões de
*conteúdo* (✅ sem evidência → Verificação assimétrica; `make check` verde
tomado como auditoria → Gate inerte; gap da própria Stage parqueado como
"futuro" → Escopo empurrado pra frente). Não há por que repeti-los aqui.

Sobram só os anti-padrões de **procedimento** (não são conceito de falso
verde — são regra de execução, já ancorada acima):
- **Não editar código na passada de julgamento** — ela é read-only (anti-viés);
  a correção vai para a **fase de aplicação** separada, que empurra os fixes
  para o PR (ver callout no topo). Merge nunca — é do usuário.
- **Não usar o checklist da Fase D como única fonte** — ele é incompleto
  por definição (cada Stage tem shape novo); a Fase D-bis existe por isso.
- **Não auditar sem ter lido `concept.md` inteiro** — é a única fonte que
  cobre o "porquê" (Fase A #1). Sem ele vira inspeção sem âncora.

---

## Mapa rápido (onde está cada critério)

| Procura por... | Está em |
|---|---|
| Critérios de aceitação da Stage (A1..AN) | `concept.md` §11 |
| Invariantes (I1..IN) | `concept.md` §5 |
| Casos de erro/exceção (C1..CN) | `concept.md` §6 |
| Decisões técnicas (D1..DN) | `concept.md` §7 |
| Questões em aberto (Q1..QN) | `concept.md` §13 |
| Gate de saída + mapping invariante↔teste | `technical.md` §3 |
| Tasks executadas | `technical.md` §2 |
| §7 post-execution (`[decision]`/`[finding]`/`[deviation]`) | `technical.md` §7 |
| Regras de import / layers | `docs/LAYOUT.md` §3 + `hex-arch-python` skill |
| Atomicidade da Stage | `docs/PIPELINE.md` §4.2 / §4.3 |
| Stage vs issue avulsa (o concept cabe no corpo?) | `docs/PIPELINE.md` §4.5 |
| Gates de PR (CI verde, ≥90%, aprovação) | `docs/GIT-WORKFLOW.md` §Gates de PR |
| Convenção de commit/branch/PR | `docs/CONVENTIONS.md` §4 + `git-versioning-pointer` skill |
| §7 post-exec — formato e regra | `docs/CONVENTIONS.md` §3.4 |
| Status de Stage (`draft`/`approved`/`done`) | `docs/CONVENTIONS.md` §3 |
| `arquivos_a_criar` declarados | `docs/roadmap.md` §"Stage N.M" (bloco YAML) |
| Validador estrutural | `scripts/check_layout.py` |
| Validador §7 post-exec | `scripts/check_technical_postexec.py` |
| Validador "Stage exige issue" | `scripts/check_stage_issue.py` |

---

## Skills relacionadas (consultar quando o caso aparecer)

- `git-versioning-pointer` — antes de qualquer operação git/GitHub
  pós-auditoria (push, PR, merge).
- `hex-arch-python` — para julgar imports/camadas no diff.
- `ddd-tactical-patterns` — para julgar Entity vs VO, agregados.
- `pytest-with-fakes` — para julgar se teste de application usa fake
  vs mock.
- `repository-pattern` — para julgar adapter de persistência.
- `fastapi-thin-adapter` — para julgar router HTTP.
- `composition-root` — para julgar wiring.
- `import-linter-rules` — para julgar contratos do import-linter
  quando a Stage muda regras de dependência.
- `task-ordering-hex` — para julgar ordem das Tasks (inside-out vs
  vertical-slice).
- `skill-builder` — quando esta skill falhar em prevenir um falso
  verde, atualizar a seção "Conceitos de falso verde" (refinar
  conceito existente; só criar novo se padrão genuinamente novo).