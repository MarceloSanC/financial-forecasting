---
title: Política de Evolução Operacional — Dependências Substituíveis
description: Critérios e processo para substituir dependências operacionais de alto acoplamento (LLM provider, banco de dados, scheduler) mantendo os ports neutros e o rastro de decisão auditável
when-use: Antes de iniciar uma Stage que substitui uma dependência operacional (troca de provedor LLM, banco, scheduler); ao avaliar se uma dependência precisa ser blindada via port; ao revisar se um ADR de componente substituível está desatualizado
keywords: [política, dependências, substituição, evolução, port, adr, runbook, llm, scheduler, database]
status: accepted
created_at: 2026-06-28
updated_at: 2026-07-05
---

# Política de Evolução Operacional — Dependências Substituíveis

> Documentação em **português**. Esta política governa como o projeto evolui dependências
> operacionais de alto acoplamento sem quebrar a arquitetura hexagonal nem perder o rastro
> de decisão.

---

## 1. Objetivo

Definir os critérios e o processo para substituir uma **dependência operacional substituível**
(LLM provider, banco de dados, scheduler) garantindo que:

1. O **port** (interface interna) permaneça neutro — sem vazamento de detalhes do fornecedor.
2. A **decisão seja auditável** via ADR — por que foi substituída, o que foi descartado.
3. O **runbook operacional** seja atualizado — quem opera o sistema sabe o que mudou.
4. A substituição seja reversível enquanto não houver ADR `accepted` que a consolide.

---

## 2. O que é uma dependência substituível

Uma dependência é **substituível** quando:

- Ela implementa um **port** (Protocol Python) definido na camada `application/` — a troca
  é transparente para o domínio e para os use cases.
- Ela tem concorrentes razoáveis que cumprem o mesmo contrato funcional.
- O custo operacional, desempenho, ou restrição de licença/compliance podem justificar a troca.

A tabela abaixo é **ilustrativa** — preencha conforme as dependências do seu projeto.
Os nomes de port, adapter e ADR são **exemplos**, não fatos deste template:

| Dependência atual (exemplo) | Port que implementa (exemplo) | ADR de referência |
|---|---|---|
| SDK de provedor LLM (ex.: `LLMProviderGateway`) | `LLMGateway` em `features/<feature>/application/ports/out/` | (ADR a criar) |
| SQLAlchemy + PostgreSQL (ex.: `PostgresEntityRepository`) | `<Entity>Repository` em `features/<feature>/application/ports/out/` | (ADR a criar) |
| Scheduler in-process (ex.: APScheduler) | port de agendamento via `Settings` flags + lifespan | (ADR a criar) |

> Substitua cada linha pelas dependências reais do seu `financial_forecasting` e crie o ADR
> correspondente quando a dependência for de fato adotada (ver §5).

---

## 3. Critérios para substituir uma dependência

Uma substituição é **elegível** quando pelo menos um dos seguintes for verdadeiro:

1. **Custo/compliance:** o fornecedor atual não cumpre restrições legais, de custo ou de SLA
   que surgem no ambiente de produção.
2. **Capacidade funcional:** o substituto habilita um caso de uso que a dependência atual não
   consegue suportar sem mudanças no port (o que seria um _vazamento_).
3. **Disponibilidade/maturidade:** a dependência atual entrou em modo _sunset_ ou apresenta
   indisponibilidade recorrente inaceitável.
4. **Reversibilidade necessária:** a equipe precisa poder fazer rollback rápido para um
   fornecedor anterior sem reescrever os use cases.

Uma substituição **não** deve acontecer por:

- Preferência estética ou novidade tecnológica sem critério operacional.
- Mimetismo com outros projetos sem análise do contexto do projeto.
- "Otimização prematura" sem métrica ou incidente que justifique.

---

## 4. Como manter o port neutro

Antes de iniciar a substituição, valide os três invariantes do port:

1. **Sem tipos do fornecedor na assinatura.** O port (`Protocol`) em `application/ports/`
   deve aceitar e retornar apenas tipos do `domain/` ou tipos primitivos Python. Nunca
   tipos da lib de terceiros (ex.: o tipo de mensagem do SDK do provedor LLM, um `Row` do
   driver SQL, etc.).

2. **Sem exceções do fornecedor vazando.** O adapter captura exceções da lib de terceiros e
   as converte em exceções do domínio (ex.: uma `LLMGatewayError` própria do projeto) antes
   de propagar. Ver [docs/LAYOUT.md](LAYOUT.md) §3 (regras de dependência entre camadas).

3. **Contract tests cobrem o port, não o fornecedor.** Os testes em `tests/contract/`
   exercitam a interface do port com o adapter real; um segundo adapter deve passar nos
   mesmos testes sem modificar o contrato. Ver [docs/LAYOUT.md](LAYOUT.md) §3 (regras de
   dependência entre camadas).

Se um dos três invariantes for violado, **corrija o vazamento primeiro** — antes de escrever
o novo adapter. A violação estará na camada `application/` ou `adapters/`, nunca no port em si.

---

## 5. Como documentar a decisão (ADR)

Toda substituição de dependência operacional exige um **novo ADR** (não editar o anterior).
O **ADR antigo** recebe `superseded_by: N.M.NNNN` no frontmatter (campo canônico —
[docs/CONVENTIONS.md](CONVENTIONS.md) §5); o **novo** cita o antigo no `Context` e é criado com:

```yaml
---
title: ADR N.M.NNNN — <Substituir X por Y para Z>
status: accepted          # ou proposed, se ainda em análise
---
```

O corpo do ADR deve cobrir obrigatoriamente:

- **Context:** por que a dependência atual não atende mais (critério da §3).
- **Decision:** qual é o substituto e o que exatamente muda no adapter.
- **Alternatives considered:** pelo menos uma alternativa descartada com justificativa.
- **Consequences:** o que fica mais fácil, o que fica mais difícil, reversibilidade.
- **Migration notes:** passos de rollout e rollback — inclua se há migration de dados.

ADRs vivem em `docs/adr/` com o padrão de nomenclatura `N_M_NNNN-<slug-em-inglês>.md`.
Ver [docs/CONVENTIONS.md](CONVENTIONS.md) §5 (versionamento de docs).

---

## 6. Como atualizar o runbook correspondente

Cada dependência substituível tem (ou deve ter) um runbook em `docs/runbooks/` que documenta
como verificar, calibrar ou fazer rollback dela. Na substituição:

1. **Se o runbook cobre a dependência antiga:** crie uma nova seção `## Substituição: <Y>`
   no mesmo runbook, com o procedimento de migração e rollback. Não apague as seções
   antigas — elas documentam o estado anterior para auditoria.

2. **Se não existe runbook:** crie um seguindo o template em `docs/templates/runbook.md`.
   O runbook da nova dependência deve cobrir no mínimo: pré-requisitos, procedimento de
   validação (equivalente ao `validate-ci-gate.md` para a camada de CI), e rollback.

3. **Atualize `updated_at`** no frontmatter do runbook após qualquer edição.

---

## 7. Checklist de substituição (resumo operacional)

Use como lista de verificação ao abrir a Stage de substituição:

- [ ] Critério da §3 documentado na issue da Stage.
- [ ] Port validado contra os três invariantes da §4 — sem vazamento de tipos ou exceções.
- [ ] ADR novo redigido (`status: proposed`) e revisado antes do `stage N.M: technical approved`.
- [ ] Contract tests atualizados ou novos para o novo adapter.
- [ ] ADR antigo atualizado com `superseded_by`.
- [ ] Runbook atualizado ou criado com seção de migração e rollback.
- [ ] `make check` verde (incluindo coverage ≥ 90 %).
- [ ] ADR promovido para `status: accepted` no commit `stage N.M: complete`.

---

## 8. Referências

- Regras de dependência entre camadas: [docs/LAYOUT.md](LAYOUT.md) §3
- Ports & Adapters (hexagonal): [docs/LAYOUT.md](LAYOUT.md) §2
- Versionamento de ADRs: [docs/CONVENTIONS.md](CONVENTIONS.md) §5
- Template de runbook: [docs/templates/runbook.md](templates/runbook.md)
- Exemplo de runbook operacional: [docs/runbooks/validate-ci-gate.md](runbooks/validate-ci-gate.md)
