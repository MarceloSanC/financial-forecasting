---
title: Concept — Stage 7.2 — Conformal CQR assimétrico como benchmark (calibrador no domain do inference, MAPIE e código dos autores como oráculos, emenda cega r2)
description: ConformalCalibrator stdlib no domain do inference (split-CQR assimétrico sem pesos de registro e NexCP ρ = 0,99 de sensibilidade, posto e pesos em aritmética racional exata, +∞ sem corte), use case CalibrateConformal sobre DTOs primitivos que impõe calib dedicado e embargo por (fold, seed, horizonte), ConformalBackend com MAPIE como oráculo e fixture do NexCP tirada do código dos autores, cobertura conformal no evaluation sobre a série nativa embutida (mesma máscara e mesmo n), integração no RefreshGold (port do consumidor, montagem calib/teste a partir do silver, bloco [conformal] no RefreshParameters e duas tabelas gold), emenda cega r2 do pré-registro ancorada na #158 e a política de reprodução da 7.1 movida para o domain; sem métrica nem refresh sobre o cohort real
when-use: Consultar ao iniciar a Fase 3B (technical) desta Stage; ao rodar o refresh confirmatório na 8.1 ou servir o intervalo conformal na 7.4; ao ler as tabelas gold conformais; ao ler ou emendar a r2 do aapl_confirmatory; ao questionar posto, empate, pesos ou limite infinito do CQR
keywords: [concept, conformal-cqr, inference, conformal, cqr, asymmetric-cqr, nexcp, mapie, oracle, fixture, coverage, empirical-coverage, degeneracy, wilson, preregistration, amendment, r2, anchor, blinding, reproduction-policy, embargo, calib]
status: done
created_at: 2026-10-17
updated_at: 2026-10-17
stage_id: 7.2-conformal-cqr
stage_title: Conformal CQR (benchmark)
step_id: 7
step_title: Inferência, conformal, explicabilidade e API
depends_on: [7.1-inference-engine, 5.1-walk-forward-harness, 6.1-scoring-and-calibration-metrics]
---

# Concept — Stage 7.2 — Conformal CQR (benchmark)

> **Escopo deste documento:** o que será feito nesta Stage, por quê, e
> decisões técnicas relevantes para entender o "porquê". O plano executável
> fica no [`technical.md`](./technical.md) correspondente.
>
> **Stage é a unidade de ciclo concept→technical→execução.** Sobre
> hierarquia (Step → Stage → Task) e critérios de atomicidade, ver
> [`PIPELINE.md`](../../PIPELINE.md) §4.
>
> **Status (apenas dois estados).** `draft` desde a criação; `done` após
> o gate humano. Regressão `done → draft` é **permitida** quando a
> Fase 3B (Technical) revela gap material aqui — neste caso, commit
> `chore(concept): revert to draft — revision-from-technical: <motivo>`.
> O Passo 8 do runbook (início da Fase 4) exige `concept.status == done`
> **e** `technical.status == done` simultaneamente.

A teoria está fechada no [doc de domínio inference](../../domain/inference/conformal-benchmark-and-feature-attribution.md)
§4 e §7 e no [ADR 0.0.0008](../../adr/0_0_0008-native-quantiles-with-conformal-benchmark.md).
Este concept não re-decide mecânica, variante, pares, seeds nem horizonte. Ele
decide quem calcula, contra que oráculo, onde o resultado vive (gold, pelo
`RefreshGold`), como a cobertura entra nas estruturas existentes e como o
pré-registro congela os detalhes.

## 1. Escopo

### Dentro do escopo

1. **Política de reprodução da 7.1 no domain** ([decision] F3 do technical
   7.1 §7; ADR 7.2.0005): `reproduction_mode`, `within_mode`, as tolerâncias e
   a comparação de chaves e valores do C7 viram funções puras em
   `inference/domain/services/reproduction_policy.py`, com as chaves ignoradas
   por parâmetro. O `RunInference` passa a chamá-las, sem mudar comportamento,
   e o `inference_commands.py` (CLI) passa a importar `STRICT` do domain.
2. **`ConformalCalibrator`** (domain do inference, stdlib; ADR 7.2.0002):
   escores unilaterais sobre o par rearranjado, posto ⌈(n+1)(1−α_cauda)⌉ e
   pesos do NexCP em aritmética racional exata, +∞ sem corte, empates
   agrupados. VOs `CalibrationSet` (calib dedicado + embargo) e
   `TailCorrection`/`PairCorrection`; referência Beta(n+1−l, l) só por cauda
   e só na variante sem pesos (parâmetros, média, dp; `None` quando l = 0).
3. **Oráculos** (ADR 7.2.0002): port `ConformalBackend` + fake + suíte de
   contrato `[fake, mapie]`; adapter `MapieCqrBackend` (`mapie>=1.5,<1.6` em
   `dependencies`; contrato import-linter `inference-no-mapie-leak`); fixture
   congelada do NexCP gerada do bloco de limiar do `splitCP_LS` dos autores,
   com golden test.
4. **`CalibrateConformal`** (use case do inference; ADR 7.2.0003): comando de
   DTOs primitivos por unidade (fold, seed, horizonte) → correções, postos,
   flags de infinito, referência Beta e limites conformais de cada ponto de
   teste, por (par, cauda, variante), com status por unidade (`ok` |
   `undefined` | `error`). Não lê nem grava nada.
5. **Cobertura conformal** (domain do evaluation; ADR 7.2.0004):
   `ConformalCoverageSeries` (série nativa embutida + limites conformais por
   ponto) e `ConformalCoverage` (ĉ por limite conformal, PICP/MPIW, Wilson nos
   níveis dados, taxas de violação de aninhamento e de cruzamento, média de
   contagens entre seeds, rótulo "cobertura empírica (não garantida)").
6. **Integração no gold** (ADR 7.2.0003):
   - port do consumidor `ConformalCalibration` em
     `evaluation/application/ports/out/`, com fake e contrato `[fake, real]`
     cuja perna real é o `CalibrateConformal`; uma aresta de dados declarada
     no `bc-independence` (`refresh_gold` → DTOs do `calibrate_conformal`);
   - serviço de domínio `ConformalAssembly` (evaluation): unidades
     (fold, seed, horizonte) do candidato a partir dos registros
     `split = "calib"` e `split = "test"` que o `RefreshGold` já lê e do
     realizado da grade de treino, mais o fold de cada ponto da série nativa
     completa; unidade incompleta vira `undefined` com motivo;
   - `RefreshParameters` com a chave obrigatória `conformal_parameters`
     (`None` em r0/r1), preenchida pelo `refresh_command_from` e conferida
     pelo `check_manifest`;
   - `RefreshGold` chama o port, monta as `ConformalCoverageSeries` e avalia
     a `ConformalCoverage` (por seed e média entre seeds); falha de unidade
     vira linha `error`, contada em `conformal_error_units`, sem abortar o
     refresh; geração BLOCKED não constrói as tabelas conformais;
   - tabelas gold `gold_conformal_corrections` e `gold_conformal_coverage`
     (schema no `gold_schema`, um builder de mapeamento puro cada, mesma
     geração, manifesto por último), e o wiring no composition root;
   - tudo testado só com silver sintético (nenhum refresh real).
7. **Emenda cega r2** (ADR 7.2.0001): VO `ConformalParameters` (catálogo de
   identificadores) aceito pelo `Preregistration` como bloco opcional
   `[conformal]` (proibido no r0); `config/preregistration/aapl_confirmatory-r2.toml`;
   espelho `docs/preregistration/aapl_confirmatory.md` com a seção r2 e o hash
   completo; âncora (tag + comentário na #158 + `.anchor.toml`) como última
   Task antes do PR.
8. **Prova sintética de cobertura** (`test_cqr_empirical_coverage`): sob
   permutabilidade, a cobertura de cada cauda fica na faixa teórica; um modelo
   estreito demais é alargado e um largo demais é encolhido.
9. **Prova de geometria sobre o dado real** (sem métrica): teste de integração
   ativado por variável de ambiente e executado na Etapa G do technical (D8).
10. **Docs:** roadmap (caminho dos ADRs, camada, contratos, 8.1 julgando pela
    revisão ancorada mais recente), LAYOUT §7 (contrato novo e aresta de
    dados nova).

### Fora do escopo (explicitamente)

- **Qualquer cobertura, escore ou correção sobre o cohort real, e qualquer
  `RefreshGold` sobre ele** (cegamento, doc §7; ADR 5.5.0001). A Etapa G lê
  só timestamps, partições e fingerprints; o primeiro refresh real é o da
  8.1, que só executa.
- Leitura das tabelas conformais pelo scorecard (evidência, veredito ou
  `ScorecardProfile`): o conformal é eixo comparativo, não perfil (ADR
  7.2.0001 item 3).
- ACI/EnbPI (ADR 0.0.0008 item 6); conformal distribucional; cobertura
  conjunta entre horizontes; teste de hipótese sobre o CQR (doc §8.3).
- Hits como sequência e Christoffersen sobre limites conformais (nenhum teste
  novo, ADR 0.0.0008 item 11).
- Quantis da Beta (o IC 90 % do doc §4.10). Exigiriam a inversa da beta
  incompleta e ficam para o relatório (8.3), com scipy em adapter (D7).
- API (7.4), H3 (7.3), plots (8.3).

### Vínculo com o roadmap

Step 7, Stage 7.2 do [`roadmap.md`](../../roadmap.md): "benchmark de
calibração por conformal (CQR assimétrico), com o MAPIE como referência,
respeitando os 4 invariantes … pré-registra os detalhes pela maquinaria da 6.5
antes da 8.1". Overview §3/§11 (CQR como benchmark ratificado), §8
R-CONFORMAL-1 (cobertura empírica + 4 invariantes), §7 (MAPIE como lib do CQR).

## 2. Objetivo da Stage

Ao fechar, existe uma função de registro, no domain do inference, que
recalibra cada par simétrico da grade por CQR assimétrico (e por NexCP
ρ = 0,99) a partir de um calib dedicado e embargado, validada contra o MAPIE e
contra o código dos autores. Um `RefreshGold` derivado da r2 publica, na
mesma geração e sob o mesmo manifesto, as correções e a cobertura empírica
conformal, medida nas mesmas linhas e com o mesmo n da cobertura nativa, e as
regras disso estão congeladas numa revisão r2 ancorada antes de qualquer
métrica sobre o cohort real.

## 3. Contexto e premissas

### Contexto

- A 7.1 gravou 211.680 linhas `split = "calib"` (60 runs × 252 decisões × 2
  horizontes × 7 níveis), com `value_raw`, `value_guardrail` e
  `guardrail_applied`, e o manifesto `data/cohorts/aapl/inference/<cohort_id>/manifest.json`
  com 60 entradas `completed` (technical 7.1 §7, Etapa E). Nenhuma métrica foi
  calculada.
- O realizado vem da grade de treino do modeling, lida uma vez pelo
  `RefreshGold` (ADR 6.4.0009). O `SeriesAssembly` já descarta `split ≠ test`.
- O pré-registro ancorado é a cadeia r0 → r1 (`aapl_confirmatory-r1-bfa8028498ca`,
  âncora em 2026-10-06T09:27:41Z na #129).
- O domain do inference é um pacote vazio desde a 7.1, já matriculado em
  `domain-purity`, `inward-only`, `store-no-storage-leak` e
  `inference-no-torch-leak`.
- `FoldSplit` (5.1) garante `train < early_stop < calib < test` e
  `calib[-1] < test[0]`. O `SplitFingerprint` de 4 vias atesta o calib
  (ADR 5.1.0003) e está em `dim_run.split_fingerprint`.

### Premissas

- O calib de cada fold tem n = 252 decisões nos dois horizontes (3.528 linhas
  por run na Etapa E da 7.1), e os alvos de h+7 do calib caem antes do teste
  (embargo de 14 pregões ≥ 7). A Etapa G confirma.
- O MAPIE 1.5.x instala com o numpy/scikit-learn do lock e aceita estimadores
  `prefit` que só devolvem predições dadas (envoltório). Se falhar, vale o
  fallback do §10.
- O código dos autores segue disponível em
  `https://rinafb.github.io/code/nonexchangeable_conformal.zip` para gerar a
  fixture uma vez. O CI nunca o baixa.

### Dependências

- `7.1-inference-engine` (`done`, PR #155): linhas `split = "calib"`,
  manifesto, `run_inference.py` (F3).
- `5.1-walk-forward-harness` (`done`): `FoldSplit`, `SplitFingerprint` de 4
  vias, `WalkForwardSplitter` (Etapa G).
- `6.1-scoring-and-calibration-metrics` (`done`): `CoverageSeries`,
  predicados FA7, `DegeneracyGate`, `WilsonBand`.
- Também consumidas (já `done`): 6.5 (VO `Preregistration`, âncora) e 6.6 (r1).

## 4. Contratos

### Introduzidos

**Inference — domain** (`features/inference/domain/`, stdlib):

```python
# value_objects/calibration_set.py
@dataclass(frozen=True)
class CalibrationPoint:
    decision_timestamp: str   # ISO8601 da decisão no calib
    target_timestamp: str     # ISO8601 do alvo (decisão + h pregões)
    lower: float              # q̂_{τ_lo} do vetor rearranjado (value_guardrail)
    upper: float              # q̂_{τ_hi} do vetor rearranjado
    realized: float           # y no target_timestamp

@dataclass(frozen=True)
class CalibrationSet:
    fold_index: int
    seed: int
    horizon: int
    lower_level: float        # τ_lo; par simétrico τ_lo + τ_hi = 1
    upper_level: float
    points: tuple[CalibrationPoint, ...]   # ordem crescente de target_timestamp
    test_start: str           # timestamp da 1ª decisão de teste do fold
    # __post_init__: I7 (não vazio, crescente, finito, embargo, par válido)

# services/conformal_calibrator.py
class ConformalVariant(StrEnum):
    SPLIT_CQR = "split_cqr_asymmetric_unweighted_v1"
    NEXCP = "nexcp_fixed_geometric_weights_v1"

@dataclass(frozen=True)
class TailCorrection:
    tail: Literal["lower", "upper"]
    level: float              # τ da cauda
    alpha: Fraction           # α_lo = τ_lo; α_hi = 1 − τ_hi (exatos)
    n: int
    rank: int | None          # k = ⌈(n+1)(1−α)⌉ na variante sem pesos
    correction: float         # Q̂; +inf quando infinito
    infinite: bool

@dataclass(frozen=True)
class PairCorrection:
    variant: ConformalVariant
    rho: float | None         # só NEXCP
    lower: TailCorrection
    upper: TailCorrection
    def limits(self, *, lower: float, upper: float) -> tuple[float, float]:
        """(q̂_lo − Q̂_lo, q̂_hi + Q̂_hi): sem rearranjo, ±inf permitido (I5)."""

@dataclass(frozen=True)
class BetaReference:
    a: int
    b: int
    mean: float
    sd: float                 # Beta(n+1−l, l), l = ⌊(n+1)α⌋

class ConformalCalibrator:
    @staticmethod
    def calibrate(calib: CalibrationSet, *, variant: ConformalVariant,
                  rho: float | None = None) -> PairCorrection: ...

def split_conformal_rank(n: int, alpha: Fraction) -> int: ...
def weighted_conformal_threshold(scores: Sequence[float], weights: Sequence[Fraction],
                                 alpha: Fraction) -> float: ...
def beta_reference(n: int, alpha: Fraction) -> BetaReference | None: ...
    # None quando l = ⌊(n+1)α⌋ = 0 (α < 1/(n+1), o caso de Q̂ = +∞): a Beta não existe
def exact_level(level: float) -> Fraction: ...   # Fraction(repr(level)); também para ρ

# services/reproduction_policy.py (ADR 7.2.0005)
STRICT: Final = "strict"
TOLERANCE: Final = "tolerance"
TOLERANCE_ATOL: Final = 1e-5
TOLERANCE_RTOL: Final = 1.3e-6

@dataclass(frozen=True)
class ReproductionMode:
    name: str
    reason: str
    forced: bool

def reproduction_mode(reference: Mapping[str, str], current: Mapping[str, str],
                      justification: str | None, *,
                      ignored_keys: frozenset[str]) -> ReproductionMode: ...
def within_mode(*, new: float, ref: float, center: float, scale: float, mode: str) -> bool: ...

@dataclass(frozen=True)
class ReproductionComparison:
    compared: int
    failures: int
    missing: int
    extra: int
    max_abs_diff: float
    max_normalized_diff: float

def compare_reproduction(reference: Mapping[tuple[int, int, float], float],
                         predicted: Mapping[tuple[int, int, float], float], *,
                         mode: str, center: float, scale: float) -> ReproductionComparison: ...
```

**Inference — application:**

```python
# ports/out/conformal_backend.py  (port-out; oráculo, ADR 7.2.0002)
class ConformalBackend(Protocol):
    def split_cqr_corrections(self, *, calib_lower: Sequence[float],
                              calib_upper: Sequence[float],
                              calib_realized: Sequence[float],
                              tail_alpha: float) -> tuple[float, float]:
        """(Q̂_lo, Q̂_hi) da variante sem pesos, par simétrico com α por cauda."""

# use_cases/calibrate_conformal.py  (use case; ADR 7.2.0003)
@dataclass(frozen=True)
class ConformalPointInput:
    decision_timestamp: str
    target_timestamp: str
    grid: Mapping[float, float]      # nível → value_guardrail
    realized: float | None           # obrigatório no calib, None no teste

@dataclass(frozen=True)
class ConformalUnitInput:
    fold_index: int
    seed: int
    horizon: int
    calib: tuple[ConformalPointInput, ...]
    test: tuple[ConformalPointInput, ...]

@dataclass(frozen=True)
class CalibrateConformalCommand:
    units: tuple[ConformalUnitInput, ...]
    pairs: tuple[tuple[float, float], ...]
    variants: tuple[str, ...]        # valores de ConformalVariant
    nexcp_rho: float

class UnitStatus(StrEnum):
    OK = "ok"
    UNDEFINED = "undefined"   # entrada incompleta: ponto de calib sem realized, grade sem os níveis do par
    ERROR = "error"           # ValueError/ArithmeticError do VO ou do calibrador nesta unidade

@dataclass(frozen=True)
class ConformalUnitResult:
    fold_index: int
    seed: int
    horizon: int
    lower_level: float
    upper_level: float
    variant: str
    rho: float | None
    status: UnitStatus
    reason: str | None                       # obrigatório quando status ≠ OK
    lower: TailCorrection | None             # None quando status ≠ OK
    upper: TailCorrection | None
    lower_beta: BetaReference | None         # None para NEXCP, para status ≠ OK e para l = 0
    upper_beta: BetaReference | None
    test_lower: tuple[float, ...] | None     # alinhados a `test`; None quando status ≠ OK
    test_upper: tuple[float, ...] | None

@dataclass(frozen=True)
class CalibrateConformalResult:
    units: tuple[ConformalUnitResult, ...]   # ordem: fold, seed, horizonte, par, variante

class CalibrateConformal:
    def __call__(self, command: CalibrateConformalCommand) -> CalibrateConformalResult:
        """Captura ValueError/ArithmeticError POR UNIDADE (status ERROR + reason).

        Só erro de comando ergue `ValueError`, antes de qualquer unidade: unidade
        (fold, seed, horizonte) duplicada, variante desconhecida, ρ inválido ou
        ausente para NEXCP, par não simétrico ou τ_lo ∉ (0; 0,5).
        """
```

A Beta é só **por cauda** e só na variante sem pesos (a cobertura condicional
do par assimétrico depende das duas caudas e não é Beta; a do NexCP também
não). O `ConformalUnitResult` não tem Beta por par.

**Inference — adapters/out:** `adapters/out/mapie/mapie_cqr_backend.py`
(`MapieCqrBackend`, satisfaz `ConformalBackend`).

**Evaluation — domain:**

```python
# value_objects/conformal_coverage_series.py  (ADR 7.2.0004)
@dataclass(frozen=True)
class ConformalPairLimits:
    lower_level: float
    upper_level: float
    lower: tuple[float, ...]         # 1 por ponto nativo; ±inf ok, NaN não
    upper: tuple[float, ...]

@dataclass(frozen=True)
class ConformalCoverageSeries:
    seed: int                        # a seed da série nativa (vai ao ConformalCoverageReport)
    native: CoverageSeries           # candidato, uma seed, um horizonte (model_full)
    variant: str
    pairs: tuple[ConformalPairLimits, ...]

# services/conformal_coverage.py
EMPIRICAL_COVERAGE_LABEL: Final = "cobertura empírica (não garantida)"

@dataclass(frozen=True)
class ConformalTailCoverage:
    level: float
    count_at_or_below: int
    coverage: float
    bands: tuple[WilsonBandReport, ...]   # um por nível de banda

@dataclass(frozen=True)
class ConformalPairCoverage:
    lower_level: float
    upper_level: float
    nominal: float
    picp: float
    mpiw: float
    mpiw_infinite: bool
    crossed_rate: float
    lower_tail: ConformalTailCoverage
    upper_tail: ConformalTailCoverage

@dataclass(frozen=True)
class ConformalCoverageReport:
    seed: int                        # a seed da série nativa embutida
    horizon: int
    variant: str
    n_points: int
    n_evaluated: int
    applicable: bool
    degeneracy: DegeneracyReport     # o da série nativa embutida
    per_pair: tuple[ConformalPairCoverage, ...]
    nesting_violation_rate: float | None
    label: str = EMPIRICAL_COVERAGE_LABEL

@dataclass(frozen=True)
class ConformalSeedMeanCoverage:
    horizon: int
    variant: str
    applicable: bool                 # False ⇔ zero seeds completas (status undefined)
    seeds_used: tuple[int, ...]      # seeds dos relatórios recebidos (todas as unidades OK)
    seeds_excluded: tuple[int, ...]  # expected_seeds − seeds_used (motivo na linha da seed)
    n_mean: float | None             # n̄ = média dos n_evaluated das seeds usadas
    # por par e cauda: c̄; coverage = c̄/n̄ (estimativa da banda, ADR 6.5.0006 item 2,
    # ADR 6.3.0005); mean_of_seed_coverages = média das coberturas por seed (o literal
    # do doc §4.9 e do ADR 0.0.0008 item 9) e o dp delas; Wilson em c̄/n̄; PICP, MPIW,
    # cruzamento e aninhamento pelas duas médias
    ...

class ConformalCoverage:
    @staticmethod
    def evaluate(series: ConformalCoverageSeries, *, tolerance: float,
                 band_levels: tuple[float, ...]) -> ConformalCoverageReport: ...
    @staticmethod
    def seed_mean(reports: Sequence[ConformalCoverageReport], *, horizon: int,
                  variant: str, expected_seeds: tuple[int, ...],
                  band_levels: tuple[float, ...]) -> ConformalSeedMeanCoverage: ...
    # `reports` = os relatórios das seeds completas daquele (horizon, variant); cada um
    # tem de ter o mesmo horizon/variant e uma seed de expected_seeds, sem repetição
    # (senão ValueError); reports vazio ⇒ applicable = False (undefined)

# value_objects/conformal_parameters.py  (ADR 7.2.0001)
CONFORMAL_RULE_CATALOG: Final[Mapping[str, str]]   # chave → único identificador implementado

@dataclass(frozen=True)
class ConformalParameters:
    variant_of_record: str
    sensitivity: str
    nexcp_rho: float
    pairs: tuple[tuple[float, float], ...]
    primary_pair: tuple[float, float]
    # + identificadores de posto, quantil ponderado, unidade, saída, comparação, perfis
    @classmethod
    def from_mapping(cls, mapping: Mapping[str, object]) -> ConformalParameters: ...
    def as_payload(self) -> dict[str, object]: ...
```

**Evaluation — application e gold** (ADR 7.2.0003):

```python
# domain/services/conformal_assembly.py
@dataclass(frozen=True)
class ConformalUnitAssembly:          # primitivos; o RefreshGold mapeia para o DTO do port
    fold_index: int                   # int(CohortRun.fold): fold é str no ForecastRecord/CohortRun
    seed: int
    horizon: int
    calib: tuple[tuple[str, str, Mapping[float, float], float], ...]   # (decisão, alvo, grade, y)
    test: tuple[tuple[str, str, Mapping[float, float]], ...]
    status: str                       # "ok" | "undefined"
    reason: str | None

@dataclass(frozen=True)
class ConformalAssemblyResult:
    units: tuple[ConformalUnitAssembly, ...]
    # (seed, h) → fold por ponto da série nativa completa, alinhado por target_timestamp
    full_series_folds: Mapping[tuple[int, int], tuple[int, ...]]

class ConformalAssembly:
    @staticmethod
    def assemble(records: Sequence[ForecastRecord], runs: Sequence[CohortRun],
                 realized: RealizedReturns, native_full: Mapping[tuple[int, int], CoverageSeries],
                 *, candidate: str, horizons: tuple[int, ...],
                 levels: tuple[float, ...]) -> ConformalAssemblyResult: ...
```

Regras da montagem (A-D7): o calib passa pelas **mesmas regras** que o
`SeriesAssembly` aplica ao teste — horizonte = índice do alvo − índice da
decisão na grade; uma linha por (run, horizonte, decisão, nível), duplicata
recusada; os níveis da grade do plano completos. Hoje essas regras são
privadas do `series_assembly.py` e emitem `AlignmentFinding` direto, então a
Stage **refatora** o módulo (que entra em `arquivos_a_modificar`): cada regra
vira uma função pública do módulo que recebe os registros e **devolve a
violação** (um valor com o tipo da regra, o run e o motivo, ou nada); o
`SeriesAssembly` converte a violação em `AlignmentFinding`, como hoje (os
testes da 6.4 passam sem mudar asserção), e o `ConformalAssembly` a converte
em unidade `undefined` com o motivo, nunca em achado. Uma definição só por
regra. O join teste ↔ série nativa é por `target_timestamp`, não por
posição: por fold, o conjunto de alvos de teste da unidade tem de ser igual ao
conjunto de alvos da série nativa completa daquele fold; divergência vira
`undefined`. `fold` chega como `str` no `ForecastRecord`/`CohortRun`; a
montagem converte com `int(fold)`, e um fold que não é inteiro vira unidade
`undefined`.

```python

# application/ports/out/conformal_calibration.py  (port do consumidor)
class ConformalCalibration(Protocol):
    def __call__(self, command: CalibrateConformalCommand) -> CalibrateConformalResult: ...
    # tipos do fornecedor sob TYPE_CHECKING; satisfeito por CalibrateConformal

# application/dtos/refresh_gold.py
class RefreshParameters:   # campo novo, obrigatório no manifesto
    conformal_parameters: ConformalParameters | None
class RefreshGoldResult:   # campo novo
    conformal_error_units: int
class GoldInputs:          # campo novo (vazio se BLOCKED ou sem bloco [conformal])
    conformal_reports: ConformalReports

@dataclass(frozen=True)
class ConformalUnitRecord:   # tipo do evaluation: o resultado do port já mapeado
    fold_index: int; seed: int; horizon: int; lower_level: float; upper_level: float
    variant: str; rho: float | None; status: str; reason: str | None
    tails: tuple[ConformalTailRecord, ...]   # n, rank, correction, infinite, Beta (primitivos)

@dataclass(frozen=True)
class ConformalReports:      # só tipos do evaluation (domain e application)
    units: tuple[ConformalUnitRecord, ...]                  # montagem undefined + resultado do port
    coverage: tuple[ConformalCoverageReport, ...]           # por seed completa
    undefined_coverage: tuple[tuple[int, int, str, str], ...]   # (seed, h, variante, motivo)
    seed_means: tuple[ConformalSeedMeanCoverage, ...]
# O mapeamento CalibrateConformalResult → ConformalUnitRecord fica no refresh_gold.py,
# o único módulo com a aresta de runtime para o inference; refresh_gold.py (dtos),
# builders e GoldInputs não importam nada do inference, nem sob TYPE_CHECKING.

# application/dtos/gold_schema.py
GOLD_CONFORMAL_CORRECTIONS: Final[GoldTableSchema]
GOLD_CONFORMAL_COVERAGE: Final[GoldTableSchema]
# as duas entram em GOLD_SCHEMAS (a geração COMPLETED lista toda tabela de lá) e em
# CONFIRMATORY_TABLES (carregam a coluna preregistration_ref, ADR 6.4.0006 item 4)
```

Builders em `adapters/out/duckdb/gold_builders/{conformal_corrections.py,
conformal_coverage.py}` (mapeamento puro, fora de `runs_when_blocked`).
Colunas das duas tabelas: ADR 7.2.0003 item 7; os nomes finais ficam no
technical. A aresta de runtime nova do `bc-independence`, declarada uma a uma:
`evaluation.application.use_cases.refresh_gold →
inference.application.use_cases.calibrate_conformal` (DTOs de comando e
resultado).

O `Preregistration` ganha o campo `conformal: ConformalParameters | None`
(chave opcional `conformal`, proibida no r0; cruzamentos: pares simétricos e
na grade, par primário = par do `h1_gate`).

**Config** (forma ilustrativa; os nomes finais das chaves ficam no technical,
os valores ficam fixados aqui):

```toml
[conformal]
variant_of_record = "split_cqr_asymmetric_unweighted_v1"
rank = "ceil_n_plus_1_one_minus_tail_alpha_exact_v1"
sensitivity = "nexcp_fixed_geometric_weights_v1"
nexcp_rho = 0.99
weighted_threshold = "smallest_score_cumulative_weight_ge_v1"
calibration_unit = "fold_seed_horizon_pair_tail_v1"
base_vector = "guardrail"
output_rearrangement = "none"
pairs = [[0.02, 0.98], [0.1, 0.9], [0.25, 0.75]]
primary_pair = [0.1, 0.9]
comparison = "descriptive_model_full_native_mask_seed_mean_counts_v1"
profile_quantities = "nesting_crossing_seed_dispersion_tail_beta_reference_v1"
```

### Consumidos

- **Linhas `split = "calib"` de `fact_oos_predictions` + manifesto de
  inferência**: Stage 7.1 (ADR 7.1.0002/7.1.0004). As linhas, pelo
  `RefreshGold` (silver sintético nos testes); o manifesto, na Etapa G.
- **`RefreshGold`, `SeriesAssembly`, `ForecastRecord`, `CohortRun`,
  `RealizedReturns`, `TrainingGridReader`, `GoldStore`, `gold_schema`,
  `refresh_command_from`, `check_manifest`**: Stages 6.4–6.6.
- **`FoldSplit`, `WalkForwardSplitter`, `SplitFingerprint`**: Stage 5.1
  (Etapa G).
- **`CoverageSeries`, `is_at_or_below`, `is_inside_closed`, `pair_nominal`,
  `DegeneracyGate`, `WilsonBand`**: Stage 6.1.
- **`Preregistration`, `TomlPreregistrationSource`, âncora, espelho**: Stage
  6.5; **r1**: Stage 6.6.
- **`RunInference`, `CODE_KEYS`/`DIRTY_KEY`**: Stage 7.1 (F3).

## 5. Invariantes e regras

- **I1 — implementação de registro.** CQR e NexCP existem uma vez, no domain
  do inference, stdlib-only. `mapie`, `numpy`, `sklearn` e `scipy` não entram
  em application/domain do inference (`inference-no-mapie-leak`). Nenhum use
  case chama o `ConformalBackend` (ADR 6.4.0008).
- **I2 — escores.** E^lo = q̂_lo − y, E^hi = y − q̂_hi, com q̂ do vetor
  rearranjado (`value_guardrail`; doc §4.8 "Insumo do CQR").
- **I3 — posto exato.** α_lo = τ_lo e α_hi = 1 − τ_hi calculados em
  `Fraction` a partir do decimal mais curto de cada nível; k = ⌈(n+1)(1−α)⌉
  inteiro exato; Q̂ = k-ésimo menor escore (empates com multiplicidade);
  k > n ⇒ Q̂ = +∞, `infinite = True`, nunca cortado em n.
- **I4 — NexCP.** w_i = ρ^(n+1−i), com i crescente no `target_timestamp`
  (1 = mais antigo; o mais recente pesa ρ); w̃_i = w_i/(Σ_j w_j + 1);
  Q̂ = menor escore R com Σ_{R_j ≤ R} w̃_j ≥ 1 − α (empates entram juntos);
  massa finita < 1 − α ⇒ +∞. Aritmética exata. ρ = 1 reproduz I3 (teste de
  propriedade); ρ ∈ (0, 1], tomado exato como `exact_level(ρ)` =
  `Fraction(repr(ρ))` (0,99 é 99/100, não o binário de 0.99).
- **I5 — saída.** Limites L = q̂_lo − Q̂_lo e U = q̂_hi + Q̂_hi por ponto de
  teste; sem rearranjo e sem trocar L e U cruzados; ±∞ permitido e sinalizado.
- **I6 — unidade.** Uma calibração por (fold, seed, horizonte, par, cauda,
  variante). Nada é reaproveitado entre unidades nem agregado entre
  horizontes.
- **I7 — calib dedicado e embargo.** O `CalibrationSet` recusa: calib vazio;
  `target_timestamp` não estritamente crescente; decisão de calib ≥
  `test_start`; **alvo de calib ≥ `test_start`** (nenhum alvo do calib
  sobrepõe o teste, doc §4.3 item 3); valor não finito; par não simétrico ou
  fora de (0; 0,5). A correção depende só do calib: mudar qualquer valor de
  teste não muda Q̂ (teste de propriedade). No use case, a recusa do VO vira
  status por unidade, nunca exceção: ponto de calib sem `realized` ou grade
  sem os níveis do par ⇒ `undefined`; `ValueError`/`ArithmeticError` do VO ou
  do calibrador ⇒ `error`, com a mensagem em `reason`; as outras unidades
  seguem intactas. Só erro de comando ergue, antes de qualquer unidade:
  unidade (fold, seed, horizonte) duplicada, variante desconhecida, ρ inválido
  ou ausente para NEXCP, par não simétrico ou τ_lo ∉ (0; 0,5).
- **I8 — cobertura.** Calculada só no evaluation, sobre a série nativa
  embutida: máscara do `DegeneracyGate` dessa série com a tolerância passada
  (a do plano), logo `n_evaluated` idêntico ao do `CoverageMetrics` da mesma
  série (teste); ĉ por `is_at_or_below` em cada limite conformal, PICP por
  `is_inside_closed`, nominal por `pair_nominal`; Wilson pelo `WilsonBand`
  com nominal τ_lo e τ_hi. Qualquer unidade não-`ok` de um (seed, horizonte,
  variante) torna a cobertura daquele (seed, horizonte, variante) `undefined`
  com o motivo — nunca se mede sobre um subconjunto de folds. A média entre
  seeds usa só as seeds completas e reporta quantas e quais; com zero seeds
  completas ela é `undefined`. Persistem-se as duas médias: c̄/n̄ (ADR
  6.5.0006 item 2; é a `coverage` da linha de média e a base da banda) e a
  média das coberturas por seed (o literal do doc §4.9 e do ADR 0.0.0008 item
  9), com o dp ao lado.
- **I9 — rótulo.** Todo `ConformalCoverageReport` carrega exatamente
  `EMPIRICAL_COVERAGE_LABEL`, validado na construção.
- **I10 — sem veredito.** Nenhum teste de hipótese novo. O bloco `[conformal]`
  não é lido pelo scorecard. Como o `check_manifest` compara
  `preregistration_ref` e os parâmetros, "o mesmo gold" não serve para duas
  revisões: o teste faz **dois refreshes do mesmo silver sintético**, um com
  `refresh_command_from(r1)` e outro com `refresh_command_from(r2)`, e compara
  o `ScorecardVerdict` (igual) e as tabelas da 6.4–6.6 sem a coluna
  `preregistration_ref` (iguais). No manifesto diferem só
  `preregistration_ref` (no topo e em `parameters`), `parameters.conformal_parameters`
  (`None` × o bloco), as contagens de linhas das duas tabelas conformais e os
  timestamps do `Clock`.
- **I11 — r2.** Idêntica à r1 salvo `revision`, campos da emenda e
  `[conformal]`; hashes de r0 e r1 inalterados; `blind_status = "blinded"`;
  `anchored_at(r2) > anchored_at(r1)`; arquivos de revisões ancoradas nunca
  são editados.
- **I12 — cegamento.** Nenhum teste, script ou Etapa desta Stage calcula
  escore, Q̂ ou cobertura sobre o cohort real. A Etapa G não lê `value_*` nem
  `target_return`.
- **I13 — F3 sem regressão.** Todos os testes da 7.1 passam sem mudar
  asserção, e o domain do inference não importa o `modeling`.
- **I14 — gold.** As tabelas conformais nascem na mesma geração do
  `RefreshGold`, manifesto por último; sem bloco `[conformal]` elas existem
  com zero linhas; geração COMPLETED sem uma delas é corrompida; BLOCKED não
  as constrói. O calib de cada unidade vem só de registros `split = "calib"`
  do run daquele fold e seed; o teste, só de `split = "test"`. Para toda
  série completa, o `n_evaluated` da linha conformal de (seed, horizonte,
  par, cauda) é igual ao `n_observed` da linha nativa da
  `gold_calibration_table` com `model` = candidato, a mesma `seed` e o mesmo
  `horizon`, `sample = "model_full"`, `kind` = a mesma cauda
  (`lower_tail`/`upper_tail`), `level_low` = τ da cauda,
  `includes_degenerate = false`, `dgt_offset` nulo (qualquer `band_level`;
  teste). A linha de média entre seeds recebe n̄ = média desses `n_observed`
  sobre as seeds completas (a tabela nativa não tem linha de média). Esse n̄
  é igual ao que o scorecard calcula (ADR 6.5.0006 item 2) **quando nenhuma
  seed é excluída**; com seed excluída, é a média só das completas.
- **I15 — isolamento.** Nenhuma unidade conformal aborta o refresh nem muda
  linha de outra tabela: com e sem o bloco `[conformal]`, as tabelas da
  6.4–6.6 e o `ScorecardVerdict` saem idênticos (teste).
- **I16 — parâmetros por derivação única.** O bloco vai do plano ao
  `RefreshParameters` só por `refresh_command_from`. Os ids de variante
  existem em dois slices (catálogo do `ConformalParameters` no evaluation,
  `ConformalVariant` no inference), porque o `bc-independence` não deixa um
  importar o outro em `src/`; a duplicação é travada por teste: os ids do
  catálogo são exatamente os valores do `ConformalVariant`, e um e2e com
  `refresh_command_from(r2 sintética)` passa pelo `CalibrateConformal` real
  com `conformal_error_units == 0`.
- **I17 — ACI/EnbPI ausentes.** O `ConformalVariant` tem exatamente os dois
  membros, o catálogo aceita só esses dois ids, e o C4 recusa qualquer outro
  (ex.: `"aci"`, `"enbpi"`).

## 6. Casos de erro e exceções

- **C1** `CalibrationSet`, `ConformalCoverageSeries` ou comando inválido (I7,
  I8, limites desalinhados, NaN) → `ValueError` nomeando o campo.
- **C2** α_cauda < 1/(n+1), ou massa ponderada insuficiente → **não é erro**:
  Q̂ = +∞ com `infinite = True` (Angelopoulos & Bates 2023, App. D).
- **C3** No comando do `CalibrateConformal`: unidade duplicada, ρ fora de
  (0, 1], variante desconhecida, ρ ausente para NEXCP, par não simétrico ou
  τ_lo ∉ (0; 0,5) → `ValueError` antes de qualquer unidade. O par é do
  comando, não da unidade, então nunca vira `error` de unidade (a recusa de
  par do `CalibrationSet` é rede de segurança do VO).
- **C4** `[conformal]` no r0, identificador fora do catálogo, chave
  desconhecida ou ausente, par primário ≠ par do gate, par fora da grade →
  `ValueError` com o caminho pontuado (padrão do `Preregistration`).
- **C5** O MAPIE recusa n pequeno de duas formas, e o adapter deixa as duas
  propagarem: (i) `_check_alpha_and_n_samples` recusa n < max(1/α_par,
  1/(1−α_par)), com α_par = 2·α_cauda (para α_cauda = 0,02, n < 25); (ii) com
  q = (1 − α_par/2)(1 + 1/n) > 1 o `np.quantile` ergue — para α_cauda = 0,02,
  n de 25 a 48. A suíte de contrato usa só n ≥ 49 (o domínio cobre o caso
  pelo C2).
- **C6** Série nativa 100 % degenerada → relatório "não aplicável", sem erro.
- **C7** A Etapa G falha (fingerprint ≠ `dim_run`, decisões de calib ≠
  `FoldSplit.calib`, interseção com `early_stop`, alvo ≥ `test[0]`, manifesto
  sem as 60 entradas `completed`) → HALT para diagnóstico. O critério nunca é
  relaxado.
- **C8** A âncora falha (rede ou permissão) → não gravar `.anchor.toml` e
  repetir; nunca inventar `anchored_at`.
- **C9** Na montagem: unidade sem calib, calib parcial, duplicata, horizonte
  ≠ alvo − decisão, níveis incompletos, fold não inteiro, alvos de teste ≠
  alvos da série nativa do fold, ou realizado ausente num alvo de calib →
  `undefined` com o motivo, e a unidade não vai ao port. No port: a unidade
  volta com o status do `CalibrateConformal` (`undefined` ou `error`), e cada
  `error` soma 1 a `conformal_error_units`. Uma exceção do port (erro de
  comando, ou outra) propaga: é erro de programação, não de dado.
  > ⚠️ Errata (2026-10-19): `conformal_error_units` conta unidades, não linhas. Cada
  > unidade (fold, seed, horizonte) com `error` soma 1, como no CA15 (technical 7.2
  > §7, `[decision]` C4-6).
- **C10** Manifesto anterior a esta Stage (sem `conformal_parameters`) → não
  lê, como na 6.6 D6.

## 7. Decisões técnicas relevantes

### D1 — Implementação de registro no domain; MAPIE e código dos autores como oráculos (fork a)
- **O quê:** §1 itens 2–3 e I1–I4. Postos e pesos em `Fraction`; +∞ sem
  corte; contrato com o MAPIE só em n onde o posto "higher" coincide (o helper
  do teste calcula os dois exatamente; n = 252 incluído) e um caso que fixa a
  divergência de +1. A triagem da issue dizia que os postos coincidem "só em
  n = 252". Coincidem em muitos n: de 20 a 399, com o domínio em racional
  exato e o MAPIE calculando o posto como ele calcula (em float64), são 245 os
  n em que os três α coincidem ao mesmo tempo (344, 342 e 285 por α, para
  0,02, 0,10 e 0,25; contagem conferida pelo Checkpoint A). Em aritmética
  exata eles divergem quando há inteiro em [(1−α)n − α, (1−α)n − (1−α)/n). A
  decisão não muda.
- **Por quê:** ADR 0.0.0056/6.1.0001 (fórmula própria de registro, lib como
  oráculo atrás de port); o MAPIE não tem pesos nem o posto pré-registrado;
  `1 − 0.9 ≠ 0.1` em float64.
- **Fonte:** issue #158 (1c, fork a); doc §4.12 e B9; verificação de contexto
  zerado do `splitCP_LS` e da nota 1 de Barber et al. (2026-10-17).
- **ADR:** [7.2.0002](../../adr/7_2_0002-own-cqr-in-domain-mapie-oracle-nexcp-fixture.md).

### D2 — Intervalos sob demanda no `RefreshGold` (fork b)
- **O quê:** sem tabela silver; `CalibrateConformal` puro sobre DTOs
  primitivos, chamado pelo `RefreshGold` por um port do consumidor; cobertura
  no evaluation; duas tabelas gold na mesma geração.
- **Por quê:** ADR 4.1.0001 (tabela só com consumidor do fato), ADR 0.0.0053
  (port no consumidor), roadmap (calibrador no domain do inference).
- **Fonte:** issue #158 (fork b); ADR 6.4.0009 e 6.6.0002.
- **ADR:** [7.2.0003](../../adr/7_2_0003-conformal-intervals-on-demand-gold-via-refresh-gold.md).

### D3 — Fronteira: a integração no gold é desta Stage; a 8.1 só executa
- **O quê:** o port do consumidor, a montagem a partir do silver no
  `RefreshGold`, o bloco no `RefreshParameters`/manifesto e as duas tabelas
  gold ficam na 7.2, testados só com silver sintético. A 8.1 roda o refresh
  confirmatório e consome o calibrador pronto.
- **Por quê:** não há fronteira de escopo real entre o calibrador e a sua
  publicação no gold; a 8.1 é orquestração. A contagem de Tasks é referência,
  não gate (regra do usuário). Um rascunho anterior cortava a integração para
  a 8.1 e foi rejeitado pelo orquestrador.
- **Fonte:** orquestrador (2026-10-17); roadmap 8.1 ("orquestração
  ponta-a-ponta"); precedente da 6.6 (perfis e tabelas na mesma Stage).
- **ADR:** [7.2.0003](../../adr/7_2_0003-conformal-intervals-on-demand-gold-via-refresh-gold.md), Alternativa E.

### D4 — Cobertura conformal: série nativa embutida (fork f)
- **O quê:** `ConformalCoverageSeries` + `ConformalCoverage` (I8, I9). Refina
  a triagem da issue ("não usa a `CoverageSeries`"): os limites conformais
  nunca entram numa `CoverageSeries`, mas a série nativa entra, embutida, e é
  dela a máscara. Intervalo cruzado (L > U) é saída válida: não cobre e conta
  na taxa de cruzamento.
- **Por quê:** ADR 6.1.0004 proíbe máscara vinda de fora; ADR 0.0.0008 item 8
  proíbe rearranjar a saída; doc §4.11 manda reusar sem re-derivar.
- **Fonte:** issue #158 (fork f); doc §8.2.
- **ADR:** [7.2.0004](../../adr/7_2_0004-conformal-coverage-series-embeds-native-series.md).

### D5 — Pré-registro: emenda cega r2 com bloco `[conformal]` (fork c)
- **O quê:** §1 item 7, I10 e I11. Não estende `profiles.declared`. A 8.1
  julga pela revisão ancorada mais recente (r2; r3 se a 7.3 emendar).
- **Por quê:** ADR 6.5.0002 e precedente da r1 (6.6); o doc §7 deixa a forma
  a esta Stage; ADR 0.0.0008 item 1 (conformal fora do caminho do veredito).
- **Fonte:** issue #158 (fork c); ADR 6.5.0008 item 6.
- **ADR:** [7.2.0001](../../adr/7_2_0001-cqr-preregistration-details.md).

### D6 — Política de reprodução no domain (F3)
- **O quê:** §1 item 1. O `_verify_decision` (linhas do silver) fica no use
  case e chama o critério do domain.
- **Por quê:** o domain não pode importar as chaves do port do modeling nem o
  `QuantileForecast` sem aresta nova; a política pura é o que a F3 pede.
- **Fonte:** technical 7.1 §7, `[decision]` F3 (2026-10-12).
- **ADR:** [7.2.0005](../../adr/7_2_0005-reproduction-policy-in-inference-domain.md).

### D7 — Referência Beta sem quantis
- **O quê:** `beta_reference` devolve a, b, média e dp (forma fechada), só
  por cauda e só na variante sem pesos; com l = ⌊(n+1)α⌋ = 0 (α < 1/(n+1), o
  mesmo caso de Q̂ = +∞) devolve `None`. Não há Beta por par: sob o CQR
  assimétrico a cobertura do par depende das duas caudas e não segue uma Beta,
  e a linha "par (simétrico)" do doc §4.10 descreve o CQR simétrico. O IC
  90 % do doc §4.10 fica para o relatório (8.3).
- **Por quê:** a stdlib não tem inversa da beta incompleta, e implementá-la só
  para uma referência descritiva seria estatística nova sem oráculo na Stage
  (degrau 5, a mais simples). A B7 pede "reportar a Beta(n + 1 − l, l)", e os
  parâmetros a reportam.
- **Fonte:** doc §4.10 e §10.1 (B7). Sem ADR: a omissão não muda contrato e
  está declarada aqui e no §1.

### D8 — Prova de geometria real como teste ativado por ambiente
- **O quê:** `tests/integration/features/inference/test_conformal_geometry_real_cohort.py`,
  pulado sem `FF_REAL_COHORT_DATA_ROOT`. Na Etapa G ele roda no container com
  o `data/cohorts/aapl` montado só leitura. Lê `dim_run`, as colunas de tempo
  e de partição de `fact_oos_predictions`, os timestamps da grade de treino e
  o manifesto; recompõe o `WalkForwardSplitter` com a geometria do cohort e
  confere, por run: `SplitFingerprint` = `dim_run.split_fingerprint`;
  decisões de calib no silver = `FoldSplit.calib` (h+1 e h+7); interseção com
  `early_stop` vazia; todo `target_timestamp_utc` de calib < `test[0]`;
  manifesto com as 60 entradas `completed`.
- **Por quê:** é a única prova de "calib dedicado" sobre o dado real que não
  calcula métrica (I12). Um subcomando de CLI seria código de produção para
  uma verificação única.
- **Fonte:** instrução do orquestrador (prova só de geometria); precedente da
  Etapa E da 7.1. Sem ADR (reversível e sem efeito em contrato).

> ⚠️ Errata (2026-10-19): além dos timestamps, das partições, dos fingerprints e do
> manifesto, a Etapa G lê as features do painel do TFT, inclusive `close` e
> `log_return_*` (preços e retornos passados). Elas servem para reproduzir o corte de
> prefixo do `build_training_grid`. A prova nunca lê `value_*` nem `target_return`
> (technical 7.2 §7, `[deviation]` C5-2).

### D9 — Onde a 7.4 obtém o intervalo conformal (A-C4)
- **O quê:** o agrupamento calib/teste tem uma definição só, no
  `ConformalAssembly` do evaluation, que reusa as regras donas do
  `SeriesAssembly`. A 7.4 não monta unidades: ela lê as correções de
  `gold_conformal_corrections` da geração `current/` e aplica-as aos quantis
  nativos do ponto servido por `PairCorrection.limits` (domain do inference,
  mesmo slice da 7.4). Caminho: a 7.4 declara um **port do consumidor no
  inference** (`application/ports/out/`) que devolve as correções como DTO
  primitivo ou VO do inference; o leitor real fica no **evaluation** (o
  `gold_schema` é o dono único do nome, da chave e das colunas lidas), como
  adapter-out ou use case que satisfaz o port por duck typing. No código de
  produção a direção continua só evaluation → inference (o leitor do
  evaluation monta o tipo do inference; o inference não importa o
  evaluation). Port, adapter e a aresta são da 7.4, registrados no
  roadmap.
- **Por quê:** o doc §6 diz que a API "serve o que foi produzido pelas Stages
  7.1–7.3; ela não recalibra". Mover o agrupamento para o `CalibrateConformal`
  sobre um DTO de linhas duplicaria no inference as regras de alinhamento cujo
  dono é o `SeriesAssembly` (duas definições).
- **Fonte:** doc §6; ADR 6.4.0004/6.4.0003 (dono único do alinhamento).
  Roadmap 7.4 emendado. Sem ADR (sem alternativa que mude contrato desta
  Stage).

## 8. Integrações

### Internas (com outras Stages/módulos)

- **inference ↔ modeling:** só a F3 (o use case continua importando
  `CODE_KEYS`/`DIRTY_KEY`). Nenhuma aresta nova no `bc-independence`.
- **evaluation:** domain novo (`ConformalCoverageSeries`, `ConformalCoverage`,
  `ConformalParameters`) e `Preregistration`. Nenhum import entre evaluation e
  inference em `src/`; os testes de integração podem compor os dois slices.
- **evaluation → inference:** uma aresta de dados declarada
  (`refresh_gold` → DTOs do `calibrate_conformal`); o comportamento entra
  pelo port `ConformalCalibration`, ligado no composition root.
- **8.1:** roda o `RefreshGold` derivado da revisão ancorada mais recente,
  que já publica as tabelas conformais; não constrói nada do conformal.
- **7.4:** lê `gold_conformal_corrections` e aplica `PairCorrection.limits`
  aos quantis nativos; não monta unidades nem recalibra (D9; roadmap
  ajustado).

### Externas

- **MAPIE** `>=1.5,<1.6` (PyPI): `ConformalizedQuantileRegressor(estimator=[lo,
  hi, med], confidence_level=1−2α, prefit=True)`, `conformalize(X, y)`,
  `predict_interval(X, symmetric_correction=False)`. Só no adapter e na suíte
  de contrato.
- **Código dos autores do NexCP** (zip público, sem auth): lido uma vez pelo
  gerador da fixture. URL, sha256 e id da célula vão ao bloco de
  proveniência.
- **GitHub** (âncora): `git push` da tag `preregistration/<ref>` e comentário
  na #158 via `gh` (ADR 6.5.0003).

## 10. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| O MAPIE 1.5 recusa o envoltório `prefit` de predições | M | M | fallback: o adapter chama a função pública de mais baixo nível do MAPIE que calcula o quantil conformal sobre os escores; registro `[decision]` no §7 do technical |
| `mapie` puxa versão incompatível de numpy/sklearn | B | M | pin por minor; `uv lock` na Task; se conflitar, HALT (contrato externo) |
| Zip dos autores indisponível | B | M | gerar a fixture do código já baixado na verificação (sha256 registrado); sem ele, o NexCP fica verificado só por casos analíticos e o oráculo vira `[finding]` |
| Caso de fronteira float × exato diverge da fixture | M | B | margem ≥ 1e-9 da soma acumulada no índice escolhido, conferida pelo gerador |
| Âncora da r2 depois de alguma métrica real | B | A | a âncora é a última Task antes do PR; I12 proíbe métrica real nesta Stage; a 8.1 confere a ordem (ADR 6.5.0003) |
| A prova de geometria real acusa divergência | B | A | HALT (C7) e diagnóstico antes de qualquer correção |
| O refactor F3 muda o comportamento do `infer` | B | A | testes da 7.1 intactos; nenhuma mudança de mensagem de erro |

## 11. Critérios de aceitação

- [ ] **CA1 (F3)** `reproduction_policy.py` no domain, com testes próprios;
      `run_inference.py` sem as definições movidas; todos os testes da 7.1
      verdes sem mudar asserção; `lint-imports` sem aresta nova.
- [ ] **CA2 (posto)** testes analíticos: k = ⌈(n+1)(1−α)⌉ exato para os três
      α da grade em n = 252 (248, 228, 190) e em n pequenos; o α_hi de 0,9 dá
      o mesmo posto que o α_lo de 0,1; k > n ⇒ +∞ com flag; empates; escores
      negativos encolhem o par e positivos o alargam.
- [ ] **CA3 (NexCP)** golden test contra a fixture do `splitCP_LS` (todos os
      casos selecionam o mesmo escore); ρ = 1 ≡ variante sem pesos
      (propriedade em casos aleatórios com semente fixa); massa insuficiente ⇒
      +∞; com n = 252, a cauda 0,02 é finita com ρ = 0,99 e infinita com
      ρ = 0,98 (doc §4.5).
- [ ] **CA4 (oráculo MAPIE)** suíte `[fake, mapie]` verde nos n de
      coincidência (n = 252 incluído; todos ≥ 49), nos três pares, com o Q̂ do
      MAPIE lido do atributo que guarda o quantil conformal quando a API o
      expõe e, senão, recuperado por subtração q̂ − L e comparado com
      `abs_tol = 1e-12`; caso de divergência +1 num n divergente, só na perna
      `mapie` (o fake não reproduz o defeito); `inference-no-mapie-leak` reprova
      `import mapie` e `import numpy` no domain e na application (caso de
      quebra); `check_port_coverage.py` verde.
- [ ] **CA5 (calib dedicado e embargo)** `tests/unit/features/inference/test_conformal_calib_set_dedicated.py`
      e `tests/unit/features/inference/test_conformal_embargo.py`: Q̂
      invariante a qualquer valor de teste; o `CalibrationSet` recusa, um caso
      por recusa do I7: calib vazio; `target_timestamp` repetido; fora de
      ordem; decisão de calib = `test_start` e > `test_start`; alvo de calib
      = `test_start` e > `test_start`; `lower`, `upper` e `realized` NaN e ±inf;
      par com τ_lo + τ_hi ≠ 1; τ_lo = 0 e τ_lo = 0,5. No use case: cada recusa
      do VO **exceto as de par** vira `error` só na sua unidade, e as unidades
      vizinhas (mesmo comando) saem idênticas às de um comando sem a unidade
      ruim (independência); ponto sem `realized` e grade sem nível ⇒
      `undefined`; unidade duplicada, variante desconhecida, ρ inválido, ρ
      ausente para NEXCP, par não simétrico e τ_lo ∉ (0; 0,5) erguem
      `ValueError` antes de qualquer unidade (C3); o resultado tem uma calibração
      por (fold, seed, horizonte, par, cauda, variante), na ordem declarada.
- [ ] **CA6 (cobertura)** `ConformalCoverage`: com correções zero, ĉ, PICP,
      MPIW e `n_evaluated` iguais aos do `CoverageMetrics` da mesma série;
      máscara da série nativa (linha degenerada fora do denominador); os dois
      empates do evaluation §4.5, separados: no ĉ de cada limite,
      `is_at_or_below` conta `y == L` (e `y == U`) como "no ou abaixo do
      limite"; no PICP, `is_inside_closed` conta `y == L` e `y == U` como
      dentro; intervalo cruzado não cobre e conta em
      `crossed_rate` e na violação de aninhamento; limite infinito cobre;
      rótulo exato; 100 % degenerada ⇒ não aplicável; uma unidade não-`ok`
      ⇒ cobertura `undefined` daquele (seed, horizonte, variante); `seed_mean`
      com só as seeds completas, contagem reportada, `coverage` = c̄/n̄ e
      `mean_of_seed_coverages` ao lado; zero seeds completas ⇒ `undefined`;
      `beta_reference` devolve `None` com l = 0 (ex.: n = 10, α = 0,02).
- [ ] **CA7 (prova sintética)** `tests/integration/features/inference/test_cqr_empirical_coverage.py`:
      com dados permutáveis (y e o modelo base i.i.d.; semente 20261017;
      n = 252 de calib e m = 252 de teste por réplica; R = 1000 réplicas na
      variante sem pesos e R = 200 no NexCP, piso fixado aqui), com ĉ =
      `count_at_or_below`/n de cada limite e ±3 erros-padrão de Monte Carlo
      (dp entre réplicas/√R), nos três pares: **cauda inferior**, média de
      ĉ(L) em [α_lo − 1/(n+1), α_lo] (equivale a 1 − ĉ ∈ [1−α_lo,
      1−α_lo+1/(n+1)]); **cauda superior**, média de ĉ(U) em [τ_hi,
      τ_hi + 1/(n+1)]; no NexCP com ρ = 0,99, só o lado da garantia: ĉ(L) ≤
      α_lo + 3 EP e ĉ(U) ≥ τ_hi − 3 EP (Barber et al. 2023 §4.1: sob
      permutabilidade o termo de perda é zero); modelo base estreito ⇒ Q̂ > 0
      e largo ⇒ Q̂ < 0; tudo passando por `CalibrateConformal` +
      `ConformalCoverage`.
- [ ] **CA8 (r2)** o `Preregistration` lê r0, r1 e r2; hashes de r0 e r1
      inalterados; C4 coberto (inclusive I17: `"aci"` e `"enbpi"` recusados);
      os ids do catálogo = os valores do `ConformalVariant` (I16); dois
      refreshes do mesmo silver sintético, por r1 e por r2: `ScorecardVerdict`
      igual e tabelas da 6.4–6.6 iguais sem a coluna `preregistration_ref`, e
      no manifesto só diferem os campos listados no I10; espelho com a seção
      r2 e o hash completo; teste de consistência do espelho com a lista de
      revisões atualizada.
- [ ] **CA9 (âncora)** tag `preregistration/<ref da r2>` no commit do arquivo;
      comentário na #158 com ref, hash completo, tag, commit, cohort_id e hash
      do cohort; `.anchor.toml` com `anchored_at` do servidor posterior ao da
      r1; o `TomlPreregistrationSource` lê a cadeia r0 → r2 com âncoras.
- [ ] **CA13 (montagem)** `ConformalAssembly` sobre registros sintéticos:
      calib só de `split = "calib"` do run do fold/seed, teste só de
      `split = "test"`; realizado no alvo; fold por ponto da série completa;
      calib parcial, ausente ou sem realizado ⇒ `undefined` com motivo;
      linhas de `early_stop` (se existissem) nunca entram; as regras do teste
      aplicadas ao calib, cada uma ⇒ `undefined` com motivo: horizonte ≠
      alvo − decisão, duplicata de (run, horizonte, decisão, nível), níveis
      incompletos; fold `"x"` (não inteiro) ⇒ `undefined`; join teste ↔
      nativo por `target_timestamp`: um alvo de teste a mais, a menos ou
      trocado no fold ⇒ `undefined` (nunca casamento por posição).
- [ ] **CA14 (port)** suíte `[fake, real]` do `ConformalCalibration` com o
      `CalibrateConformal` como perna real, incluindo os três status por
      unidade (`ok`, `undefined`, `error`) e os erros de comando que erguem; `check_port_coverage.py` verde;
      `lint-imports` com exatamente uma aresta nova declarada
      (`refresh_gold` → `calibrate_conformal`) e reprovando outra.
- [ ] **CA15 (refresh sintético)** e2e sobre silver sintético com calib e
      teste: geração COMPLETED com as duas tabelas, manifesto com
      `conformal_parameters` igual ao da r2; `n_evaluated` conformal = o da
      `gold_calibration_table` nativa por (seed, horizonte); com correções
      forçadas a zero pelo fake, cobertura conformal = nativa; sem bloco
      (r1) ⇒ tabelas com zero linhas; BLOCKED ⇒ sem tabelas conformais;
      unidade devolvida como `error` pelo port ⇒ linha `error`,
      `conformal_error_units = 1`, cobertura daquele (seed, horizonte,
      variante) `undefined` e as outras unidades e seeds publicadas; tabelas
      da 6.4–6.6 e `ScorecardVerdict` idênticos com e sem o bloco (I15);
      manifesto antigo não lê (C10). **Caso com o use case real:** o
      `RefreshGold` ligado pela mesma fábrica do composition root ao
      `CalibrateConformal` real, com `refresh_command_from(r2 sintética)` e um
      modelo base estreito (correções ≠ 0): `conformal_error_units == 0`, e uma
      linha escolhida de `gold_conformal_corrections` é igual, campo a campo,
      ao `ConformalCalibrator.calibrate` chamado direto sobre o mesmo calib.
      Nenhum teste lê o `parent_sweep_id` do cohort real.
- [ ] **CA10 (geometria real, Etapa G)** o teste de D8 roda verde no
      container sobre o `data/cohorts/aapl` montado só leitura, com a saída
      colada no §7 do technical; nenhum `gold/` criado; nenhuma coluna
      `value_*` ou `target_return` lida (o teste lista as colunas que pede).
- [ ] **CA11 (docs)** roadmap e LAYOUT §7 emendados (contrato novo e aresta
      nova), com linha no changelog do roadmap; `make docs-check` verde.
- [ ] **CA12 (gates)** `make check` verde (cobertura ≥ 90 %, mypy strict,
      import-linter, layout, fake-parity, port-coverage).

## 12. Checklist de validação interna

- [x] Todos os contratos introduzidos têm assinatura definida? — §4.
- [x] Toda decisão em §7 tem fonte rastreável? — cada D cita issue, doc, ADR ou instrução do orquestrador.
- [x] Toda integração externa tem contrato definido (interface, formato, auth)? — MAPIE (API e pin), zip dos autores (URL público, sha256 na proveniência), GitHub (tag + `gh`, ADR 6.5.0003).
- [x] Decisões com alternativa real descartada têm ADR escrito? — 7.2.0001 a 7.2.0005; D7 e D8 não têm alternativa que mude contrato.
- [x] Dependências de Stages anteriores estão satisfeitas (`done`)? — 7.1, 5.1 e 6.1 (e 6.5, 6.6) estão `done` no roadmap.
- [x] Stage cabe em ~3–12 Tasks (ver [`CONVENTIONS.md`](../../CONVENTIONS.md) §6)? — ~20 Tasks (o Checkpoint A acrescentou o caso com use case real e a montagem endurecida), acima da faixa de referência; a contagem é referência e não há fronteira de escopo real para dividir (D3). Lista: F3; CQR; NexCP + fixture; port + fake do backend; MAPIE; use case; cobertura; VO do bloco; montagem; port do consumidor + contrato; `RefreshParameters`; `RefreshGold`; schema + builders; wiring + aresta; r2 + espelho; prova sintética e e2e do refresh; teste de geometria; docs; âncora. Mais a Etapa G sem código.
- [x] Riscos críticos têm mitigação plausível? — §10; os de impacto A param em HALT.
- [x] Cada mecanismo novo passou pelo **teste da solução mais direta**: não é caso especial/tipo/métrica novo remendando, local, um sintoma que recorre em outros consumidores e teria tratamento mais simples/geral em outra camada (concern compartilhado). Captura assim → piso declarado + issue, não solução local. — (i) calibrador próprio: a solução direta "usar o MAPIE" não implementa o NexCP nem o posto pré-registrado, e a postura geral do projeto (ADR 0.0.0056) já é fórmula de registro + oráculo; (ii) cobertura: em vez de métrica nova, o VO embute a série nativa e reusa os predicados FA7, o `DegeneracyGate` e o `WilsonBand` donos, e o concern compartilhado (máscara, n, empate) continua num lugar só; (iii) pré-registro: reusa a maquinaria da 6.5 (emenda), sem arquivo próprio; (iv) intervalos: sem tabela silver nem job novo, com recálculo sob demanda e gold pelo `RefreshGold` existente, que já lê o silver e a grade; (v) aritmética exata: o concern "nível em float" já tem convenção a montante (o repr mais curto do `PreregistrationHash`), aplicada aqui em vez de uma tolerância local; (vi) a F3 move a política para a camada certa sem aresta nova. Nenhuma captura local de concern transversal identificada.
- [x] A Stage calcula alguma métrica sobre o cohort real? — não. Só a Etapa G, de geometria (I12, CA10).
- [x] A r2 é ancorada antes de qualquer métrica conformal real? — sim: é a última Task antes do PR, e o primeiro refresh real é o da 8.1 (ADR 7.2.0001 item 4).
- [x] Algum teste roda `RefreshGold` sobre o cohort real? — não: só silver sintético (CA15).

## 13. Questões em aberto

Nenhuma. O corte de escopo de um rascunho anterior foi rejeitado e a
integração no gold está no escopo (D3).

## 14. Referências

- [`../../overview.md`](../../overview.md) — §3, §7, §8 (R-CONFORMAL-1), §11
- [`../../roadmap.md`](../../roadmap.md) — Stage `7.2-conformal-cqr` e vizinhas 7.3, 7.4, 8.1
- [Doc de domínio inference](../../domain/inference/conformal-benchmark-and-feature-attribution.md) §2, §4, §7, §8, §10, §10.1
- ADRs desta Stage: [7.2.0001](../../adr/7_2_0001-cqr-preregistration-details.md),
  [7.2.0002](../../adr/7_2_0002-own-cqr-in-domain-mapie-oracle-nexcp-fixture.md),
  [7.2.0003](../../adr/7_2_0003-conformal-intervals-on-demand-gold-via-refresh-gold.md),
  [7.2.0004](../../adr/7_2_0004-conformal-coverage-series-embeds-native-series.md),
  [7.2.0005](../../adr/7_2_0005-reproduction-policy-in-inference-domain.md)
- ADRs consumidos: 0.0.0008, 0.0.0053, 0.0.0056, 4.1.0001, 5.1.0002, 5.1.0003,
  6.1.0001, 6.1.0002, 6.1.0004, 6.2.0006, 6.3.0002, 6.4.0008, 6.4.0009,
  6.5.0001 a 6.5.0003, 6.5.0006, 6.5.0008, 6.6.0001, 6.6.0002, 7.1.0001 a 7.1.0004
- [Concept 7.1](../7.1-inference-engine/concept.md) e [technical 7.1 §7](../7.1-inference-engine/technical.md) (F3, Etapa E)
- Romano, Patterson & Candès (2019), arXiv:1905.03222; Barber, Candès, Ramdas & Tibshirani (2023), DOI 10.1214/23-AOS2276 (arXiv:2202.13415v5); Angelopoulos & Bates (2023), DOI 10.1561/2200000101; Gupta, Kuchibhotla & Ramdas (2022), DOI 10.1016/j.patcog.2021.108496
- Código dos autores do NexCP: https://rinafb.github.io/code/nonexchangeable_conformal.zip (`splitCP_LS`); MAPIE 1.5.0
- Issue: [#158](https://github.com/MarceloSanC/financial-forecasting/issues/158)
