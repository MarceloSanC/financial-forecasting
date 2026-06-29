---
title: Concept — Stage 1.3 — Contratos de arquitetura (import-linter)
description: Encodar as regras de dependência do LAYOUT como contratos import-linter que quebram o build, fechando o gate de fitness arquitetural
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; revisar antes de executar os contratos
keywords: [concept, architecture-contracts, import-linter, fitness-function, hexagonal, layers, forbidden, composition-root]
status: done
created_at: 2026-06-29
updated_at: 2026-06-29
stage_id: 1.3-architecture-contracts
stage_title: Contratos de arquitetura (import-linter)
step_id: 1
step_title: Fundação e fitness arquitetural
depends_on: [1.2-ci-coverage]
---

# Concept — Stage 1.3 — Contratos de arquitetura (import-linter)

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes. O plano executável fica no
> [`technical.md`](./technical.md).

## 1. Escopo

### Dentro do escopo

- Criar **`.importlinter`** (formato INI, na raiz, `root_package = financial_forecasting`)
  espelhando `docs/LAYOUT.md` §3/§6, com três famílias de contrato:
  - **`layers`**: direção `adapters > application > domain`, com
    `shared.application.ports` e `shared.domain` como camadas-base inward,
    modelado por **containers** (`shared` e cada `features.<feature>`) sem
    reprovar pelo esqueleto genérico/excedente inerte do template (finding F2).
  - **`forbidden`** (regras que quebram o build):
    - `*.domain` e `shared.domain` proibidos de importar `pandas`, `pyarrow`,
      `torch` (**DoD central**) e também `pydantic`, `sqlalchemy`, `fastapi`
      (LAYOUT linha 104);
    - `application`/`shared.application` proibidos de importar `adapters` e
      `shared.infrastructure` (LAYOUT linha 110);
    - `shared.*` proibido de importar `features.*` (LAYOUT linha 244).
  - **`ignore_imports`**: exceção única da fronteira composition_root
    (`shared.infrastructure.http.app → composition_root` e
    `composition_root → features.*.adapters`), LAYOUT linhas 222–229.
- Tornar o contrato **efetivo no gate**: alvo Make `lint-imports`
  (`uv run lint-imports`) incluído em `check`, e presença explícita no
  `ci.yml` (o CI já chama `make check`). Validar por **quebra intencional
  revertida** (domain importando `pandas` ⇒ build vermelho).
- Adicionar `import-linter` ao grupo `dev` do `pyproject.toml` e fixar no
  lock.
- Teste de regressão `tests/architecture/test_import_contracts.py` que
  (a) exige `lint-imports` verde no estado atual e (b) prova que um import
  proibido (via config temporária, sem mutar a árvore real) é detectado.
- ADR [`1.3.0001`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md)
  (status `accepted`) para as decisões não-triviais.

### Fora do escopo (explicitamente)

- Implementar features de negócio (`features/` tem apenas `__init__.py`).
- Regras específicas de bounded contexts ainda inexistentes — não se modela
  isolamento feature×feature (`independence`) enquanto só houver uma feature
  potencial; é desnecessário hoje.
- Value objects de identidade/fingerprints (Stage 1.4).
- Settings tipados, composition_root populado, MLflow (Stage 1.5).
- Deploy/release, cache de deps, matrix de versões (não pertencem a esta
  Stage; alguns já tratados na 1.2).
- **Recriar** `docs/LAYOUT.md`: ele **já existe** e é a fonte da verdade; o
  `.importlinter` apenas o espelha. (O roadmap lista `docs/LAYOUT.md` em
  `arquivos_a_criar` por herança da 1.1; aqui ele não é criado — ver D4.)
- O commit de fechamento `stage 1.3: complete` e a marcação `done` da Stage
  no roadmap — feitos pelo **orquestrador** após auditoria independente.

### Vínculo com o roadmap

Esta Stage é a **fitness function central** do Step 1 ("Fundação e fitness
arquitetural", roadmap linhas 120–197): "qualquer mudança que viole
arquitetura é barrada automaticamente antes do merge". Executa o handoff
declarado em ADR `0.0.0019` (1.1: `check_layout.py` → 1.3: import-linter) e
satisfaz a restrição herdada do overview §6/§7: "import-linter espelha o
LAYOUT; o build quebra se o domínio importar pandas/pyarrow/torch".

## 2. Objetivo da Stage

Ao final, o build (local e CI) **fica vermelho automaticamente** se algum
módulo de domínio importar `pandas`/`pyarrow`/`torch` (ou
`pydantic`/`sqlalchemy`/`fastapi`) ou se a direção de dependência
`adapters → application → domain` for violada — provado por quebra
intencional revertida — sem reprovar a fronteira aceita do composition_root
nem o esqueleto inerte do template.

## 3. Contexto e premissas

### Contexto

O projeto reconstrói uma implementação anterior que apodreceu por **fronteira
de domínio não enforçada**: no repo de referência
`/home/marcelo/Code/financial-time-series-forecasting`, **23 de 36** arquivos
sob `src/domain/services/` importavam `pandas`/`numpy`/`torch` (ex.:
`dataset_quality_gate.py:1`, `holm_family_6.py:3`). Aquele repo não tinha
import-linter nem `.importlinter` nem checagem de camadas; o único
"enforcement" de fronteira era o isort `known-first-party` do Ruff
(`pyproject.toml:63`), que ordena imports mas não valida direção, e o CI
(`ci.yml:27`) rodava só ruff/mypy/pytest. Esta Stage fecha exatamente esse
gap com a ferramenta-padrão.

`scripts/check_layout.py` (Stage 1.1) já cobre parte das regras, mas tem ponto
cego documentado (`check_layout.py:17`): não enxerga o caminho **indireto** da
fronteira composition_root (LAYOUT linha 228). import-linter **complementa**
(não substitui) o script.

### Premissas

- `docs/LAYOUT.md` é a fonte da verdade; se LAYOUT e `.importlinter`
  divergirem, **LAYOUT vence** e o contrato é corrigido.
- A fronteira composition_root é real e verificada **verbatim**: `app.py:22`
  importa `financial_forecasting.composition_root`.
- O esqueleto atual é majoritariamente excedente inerte do template (finding
  F2): `shared.infrastructure.{clock,http,config,logging,uuid_generator}`,
  `shared.application.ports.out.*` existem; `features/` só tem `__init__.py`;
  `shared/adapters/` **não existe** ainda. Os contratos devem refletir a
  estrutura modular real sem reprovar por pastas ausentes/inertes.

### Dependências

- `1.2-ci-coverage` (done): o CI já invoca `make check`; o `ci.yml` e o gate
  de cobertura estão no lugar. Esta Stage insere o contrato de import no mesmo
  ponto de gate.

## 4. Contratos

Stage de **fitness function**: `contratos_introduzidos: []` e
`contratos_consumidos: []` no YAML do roadmap. Nenhum `Protocol`/value
object/port de domínio é criado. O **único artefato-contrato** é o de
import/camadas em `.importlinter`, que **espelha** `docs/LAYOUT.md` §3/§6
(fonte da verdade). Os contratos import-linter introduzidos são:

### Introduzidos

- **`hexagonal-layers`** (contrato import-linter `layers`) — direção
  `adapters > application > domain`; `shared.application.ports` e
  `shared.domain` como base inward; modelado por containers (`shared`, e cada
  `features.<feature>` à medida que surgir) tolerando camadas ausentes/inertes.
- **`domain-purity`** (contrato `forbidden`) — `*.domain`/`shared.domain` ⊬
  `pandas`, `pyarrow`, `torch`, `pydantic`, `sqlalchemy`, `fastapi`.
- **`inward-only`** (contrato `forbidden`) — `application`/`shared.application`
  ⊬ `adapters`/`shared.infrastructure`; `domain` ⊬
  `application`/`adapters`/`shared.infrastructure`.
- **`shared-no-features`** (contrato `forbidden`) — `shared.*` ⊬ `features.*`.
- **Exceção `ignore_imports`** — `shared.infrastructure.http.app →
  composition_root` e `composition_root → features.*.adapters` não são
  reprovados.

### Consumidos

Nenhum contrato de domínio/aplicação consumido. Consome apenas
infraestrutura de gate da Stage 1.2 (`make check` invocado pelo CI).

## 5. Invariantes e regras

- **I1 — Domínio puro.** `domain/` e `shared/domain/` importam apenas stdlib +
  domínio; proibido `pandas`/`pyarrow`/`torch`/`pydantic`/`sqlalchemy`/
  `fastapi`. Quebra intencional (domain importando `pandas`) **deve** deixar o
  build vermelho — DoD verificável (LAYOUT linha 104).
- **I2 — Direção outside-in.** `adapters → application → domain`. `application`
  não importa `adapters` nem `shared.infrastructure`; `domain` não importa
  `application`/`adapters`/`shared.infrastructure` (LAYOUT linhas 94/110).
- **I3 — Shared não importa de features.** O fluxo é sempre `features → shared`
  (LAYOUT linha 244).
- **I4 — Exceção única composition_root.** É o único ponto onde
  `shared.infrastructure.http.app → composition_root → features.adapters` é
  permitido; declarado via `ignore_imports`, **não reprovado** (LAYOUT linhas
  222–229).
- **I5 — Gate efetivo.** `lint-imports` (`uv run lint-imports`) integrado ao
  alvo que `make check` invoca **e** garantido no `ci.yml`; validado por
  quebra intencional revertida (lição 1.2 "gate inerte ou míope").
- **I6 — LAYOUT é a fonte.** Contratos espelham `docs/LAYOUT.md` §3/§6; em
  divergência, LAYOUT vence e o contrato se ajusta.
- **I7 — Sem reprovar excedente inerte.** Os contratos refletem a estrutura
  modular real sem reprovar pastas/`__init__` inertes do template (finding F2)
  nem módulos ainda inexistentes (`shared/adapters/`, layers de features).

## 6. Casos de erro e exceções

- **C1 — Domain importa lib proibida.** Qualquer import de
  `pandas`/`pyarrow`/`torch`/`pydantic`/`sqlalchemy`/`fastapi` em
  `*.domain` ⇒ contrato `domain-purity` quebra ⇒ `lint-imports` exit ≠ 0 ⇒
  `make check`/CI vermelhos.
- **C2 — Import contra a direção.** `application` importando `adapters`/
  `shared.infrastructure`, ou `domain` importando camadas externas ⇒
  `inward-only`/`hexagonal-layers` quebra ⇒ build vermelho.
- **C3 — Shared importa feature (fora da exceção).** Qualquer
  `shared.* → features.*` que não seja o caminho composition_root declarado ⇒
  `shared-no-features` quebra ⇒ build vermelho.
- **C4 — Fronteira composition_root.** O caminho `app → composition_root →
  features.adapters` **não** pode reprovar (`ignore_imports`); se reprovar, o
  contrato está errado, não o código.
- **C5 — Módulo de layer ausente.** Container/layer ainda não criado (ex.:
  `shared/adapters`, layers de uma feature vazia) **não** pode quebrar o
  contrato — modelado como tolerante a ausência (finding F2). Falha aqui é bug
  do contrato.
- **C6 — Contrato afrouxado/removido.** Remover ou enfraquecer `.importlinter`
  é detectado pelo teste de regressão em `tests/architecture/`.

## 7. Decisões técnicas relevantes

### D1 — Local da config do import-linter
- **O quê:** `.importlinter` standalone (INI) na raiz, em vez de
  `[tool.importlinter]` no `pyproject.toml`.
- **Por quê:** o YAML do roadmap (linha 188) manda criar explicitamente
  `.importlinter`; arquivo dedicado mantém o contrato de arquitetura
  visível/auditável em um só lugar, desacoplado do manifesto de build. Custo
  de trocar depois é nulo.
- **Fonte:** Roadmap §Stage 1.3 (`arquivos_a_criar`, linha 188); LAYOUT §3.
- **ADR:** [`../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md)

### D2 — Tipos de contrato
- **O quê:** `layers` (direção) + `forbidden` (domain-purity, inward-only,
  shared-no-features) + `ignore_imports` (fronteira composition_root). Sem
  `independence` (features×features) hoje.
- **Por quê:** `forbidden` de `pandas`/`pyarrow`/`torch` no domain é o DoD
  central — o repo antigo provou (23/36 arquivos) que sem isso o domínio
  apodrece; `layers` cobre a direção; `independence` seria a forma errada (é
  simétrica, não expressa direção) e desnecessária com `features/` vazio.
- **Fonte:** LAYOUT linhas 94/104/110/222–229/244; repo antigo
  `src/domain/services/{dataset_quality_gate.py:1, holm_family_6.py:3}`.
- **ADR:** [`../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md)

### D3 — Ponto de integração no gate
- **O quê:** alvo Make `lint-imports` (`uv run lint-imports`) incluído em
  `check`; presença do contrato tornada explícita/garantida no `ci.yml`.
  import-linter **complementa** `check_layout.py`, não o substitui.
- **Por quê:** lição 1.2 ("gate inerte ou míope"): o contrato só vale se rodar
  de fato e for provado por quebra intencional. Como o CI já chama `make check`
  (`ci.yml`), inseri-lo em `check` propaga ao CI. `check_layout.py` não detecta
  o caminho indireto da fronteira (LAYOUT linha 228) — import-linter adiciona
  cobertura de direção/forbidden, mantendo ambos.
- **Fonte:** ADR `0.0.0019`; ADR `1.2.0011`; `ci.yml`; `check_layout.py:17`.

### D4 — `docs/LAYOUT.md` não é recriado
- **O quê:** apesar de o roadmap listar `docs/LAYOUT.md` em
  `arquivos_a_criar` da 1.3, o arquivo **já existe** e não será recriado nem
  reescrito; o `.importlinter` se alinha a ele.
- **Por quê:** LAYOUT é a fonte da verdade e já consolidado; recriá-lo
  arriscaria divergência. A listagem no roadmap é herança da fase de
  planejamento (o LAYOUT veio do template). Decisão de baixo risco, sem
  alternativa real descartada ⇒ não vira ADR.
- **Fonte:** finding carregado da 1.2 ("LAYOUT.md JÁ EXISTE — alinhar, NÃO
  recriar"); LAYOUT existente no repo.

## 8. Integrações

### Internas (com outras Stages/módulos)
- `make check` / `ci.yml`: ponto único onde o contrato roda como gate
  bloqueante (herdado da 1.2).
- `scripts/check_layout.py`: coexiste; cobertura sobreposta intencional
  (defesa em profundidade).

### Externas
- `import-linter` (PyPI), via `uv`: lê `.importlinter`, expõe o CLI
  `lint-imports` (exit ≠ 0 em violação). Pinado no grupo `dev` e no lock.

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Contrato `layers` quebra por module/layer ausente (skeleton inerte, F2) | M | M | Modelar containers tolerantes a camadas ausentes; validar `lint-imports` verde no estado atual antes de commitar (I7/C5) |
| Contrato reprovar a fronteira composition_root | M | A | `ignore_imports` verbatim do par `app→composition_root`/`composition_root→features.adapters`; testar caminho não reprova (I4/C4) |
| Gate inerte/míope (lição 1.2) | M | A | Provar por quebra intencional revertida (`import pandas` no domain ⇒ vermelho) + teste de regressão em `tests/architecture/` |
| Contrato divergir do LAYOUT ao longo do tempo | M | M | LAYOUT é a fonte; `.importlinter` espelha; ADR 1.3.0001 fixa a regra |

## 11. Critérios de aceitação

- [ ] **A1** — `.importlinter` existe na raiz, INI, `root_package =
  financial_forecasting`, com os contratos `layers` + `forbidden`
  (domain-purity, inward-only, shared-no-features) + `ignore_imports` da
  fronteira composition_root.
- [ ] **A2** — `uv run lint-imports` retorna **0 broken** no estado atual do
  repo (não reprova esqueleto inerte F2 nem a fronteira composition_root).
- [ ] **A3** — Inserir `import pandas` em um módulo de `shared/domain/`
  (ex.: `pagination.py`) faz `uv run lint-imports` retornar exit ≠ 0 pelo
  contrato `domain-purity`; após reverter, volta a 0 broken (DoD central,
  evidência registrada em `technical.md` §7).
- [ ] **A4** — `make check` inclui e executa `uv run lint-imports` e fica
  verde; o `ci.yml` garante explicitamente que o contrato roda no CI.
- [ ] **A5** — `tests/architecture/test_import_contracts.py` passa em
  `make test`: exige `lint-imports` exit 0 e prova que um import proibido
  (via config temporária, sem mutar a árvore real) é detectado (exit ≠ 0); o
  teste falha se `.importlinter` for removido/afrouxado.
- [ ] **A6** — `import-linter` está no grupo `dev` do `pyproject.toml` e fixado
  no `uv.lock`; `uv run lint-imports --help` executa.
- [ ] **A7** — ADR `1.3.0001` em `accepted`, cobrindo D1 e D2 com alternativas
  pesadas (pyproject vs `.importlinter`; layers vs independence).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? (são contratos
  import-linter, mapeados em §4/§5)
- [x] Toda decisão em §7 tem fonte rastreável? (LAYOUT/roadmap/repo antigo/ADR)
- [x] Toda integração externa tem contrato definido? (import-linter via uv;
  CLI `lint-imports`)
- [x] Decisões com alternativa real descartada têm ADR escrito? (1.3.0001: D1,
  D2)
- [x] Dependências de Stages anteriores estão satisfeitas? (1.2 `done`)
- [x] Stage cabe em ~3–8 Tasks? (8 Tasks no roadmap/technical)
- [x] Riscos críticos têm mitigação plausível? (§10)
- [x] O contrato é provado por quebra intencional revertida? (A3, I5)

## 14. Referências

- [`../../overview.md`](../../overview.md) — §6 (restrições: import-linter
  espelha LAYOUT), §7 (enforcement-as-test), §11 (ADRs `0_0_0019`–`0_0_0021`).
- [`../../roadmap.md`](../../roadmap.md) — Stage `1.3-architecture-contracts`
  (linhas 179–197) e vizinhas (1.1, 1.2, 1.4).
- [`../../LAYOUT.md`](../../LAYOUT.md) — §3 (direção, linhas 94/104/110), §6
  (fronteira composition_root, linhas 222–229), §7 (linha 244).
- ADRs desta Stage: [`../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md`](../../adr/1_3_0001-import-linter-as-architecture-fitness-function.md).
- ADRs de fundação: `0_0_0019` (enforce by tooling), `0_0_0020`
  (estatística no domínio), `1_2_0011` (gate como fitness function).
- Repo antigo (exemplo negativo): `/home/marcelo/Code/financial-time-series-forecasting`
  (`src/domain/services/dataset_quality_gate.py:1`, `holm_family_6.py:3`;
  `ci.yml:27`; `pyproject.toml:63`).
