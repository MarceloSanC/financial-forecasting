"""Use case `RunPermutationInference` — predições de atribuição do candidato no silver (7.3).

Para o cohort confirmatório congelado, por seed e por run do candidato TFT: pede ao
fornecedor do `modeling` a identidade, as predições com a janela inteira do encoder de
cada família trocada entre as decisões de teste do fold (K_p permutações por fold, a
MESMA para toda seed e família) e os pesos da VSN; confere a identidade contra as linhas
de teste da 7.1 pela política de reprodução; e grava as duas tabelas silver com manifesto
write-ahead (concept 7.3 §1 item 6, I6, I7, I17, I19; ADR 7.3.0002 itens 2-3). Só
predições: nada do realizado, nada de `evaluation` (cegamento, I9).

Ordem por run (technical 7.3 §1): validação do comando → lock → probe → resolução →
leitura do silver de teste do run → plano → predição (guardas do fornecedor) →
identidade x silver pela política de reprodução da 7.2 → manifesto `started`
(write-ahead) → `PersistPermutedPredictions` → `PersistVsnWeights` → manifesto
`completed`. Falha antes do write-ahead não grava nada.

Retomada (C8): run com entrada `completed` no manifesto é re-conferido por leitura —
contagem por `(família, k)` igual à da identidade para cada família e k = 1..K_p, as
colunas do plano e da partição iguais às do manifesto e as linhas da VSN iguais às
gravadas — e não é predito de novo (status `verified`). Linhas no silver sem `completed`,
ou contagem incompleta, erguem `PartialAttributionError`. A predição é por seed: uma seed
com algum run a gravar é predita inteira, e só os runs não `completed` são gravados.

Arestas de dados de runtime (declaradas no `bc-independence`, uma linha cada, exceção do
MÓDULO; ADR 7.3.0002, ADR 0.0.0053 item 3): os DTOs de comando de
`ResolveTftCheckpoints` e de `PredictTftAttributionFromCheckpoints`, as chaves do port do
probe do `modeling`, os DTOs de comando dos dois escritores do `analytics_store` e o VO
`QuantileForecast` (guardrail, ADR 4.3.0002).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from financial_forecasting.features.analytics_store.application.use_cases.persist_permuted_predictions import (  # noqa: E501
    PermutedDecisionEntry,
    PersistPermutedPredictionsCommand,
)
from financial_forecasting.features.analytics_store.application.use_cases.persist_vsn_weights import (  # noqa: E501
    PersistVsnWeightsCommand,
    VsnDecisionEntry,
)
from financial_forecasting.features.analytics_store.domain.value_objects.quantile_forecast import (
    QuantileForecast,
)
from financial_forecasting.features.inference.application.ports.out.attribution_manifest import (
    COMPLETED,
    STARTED,
)
from financial_forecasting.features.inference.application.use_cases.run_inference import (
    ArtifactChangedError,
    CohortNotFrozenError,
    InferenceEnvironmentError,
    ReproductionError,
    UnknownRunError,
    check_normalizer_scale,
    check_prediction,
    environment_mode,
    float_cell,
    recorded_threads,
    validate_justification,
)
from financial_forecasting.features.inference.domain.services.reproduction_policy import (
    STRICT,
    ReproductionMode,
    compare_reproduction,
)
from financial_forecasting.features.inference.domain.value_objects.permutation_plan import (
    K_P,
    PERMUTATION_ALGORITHM,
    PERMUTATION_SEED,
    FamilyPermutationPlan,
)
from financial_forecasting.features.modeling.application.ports.out.runtime_environment_probe import (  # noqa: E501
    DIRTY_KEY,
)
from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
    PredictTftAttributionCommand,
)
from financial_forecasting.features.modeling.application.use_cases.resolve_tft_checkpoints import (
    ResolveTftCheckpointsCommand,
)
from financial_forecasting.shared.application.exceptions import ApplicationError
from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.family_partition_hash import (
    FamilyPartitionHash,
)

if TYPE_CHECKING:
    from financial_forecasting.features.inference.application.ports.out.attribution_manifest import (  # noqa: E501
        AttributionManifest,
    )
    from financial_forecasting.features.inference.application.ports.out.checkpoint_attribution_predictor import (  # noqa: E501
        CheckpointAttributionPredictor,
    )
    from financial_forecasting.features.inference.application.ports.out.checkpoint_resolver import (
        CheckpointResolver,
    )
    from financial_forecasting.features.inference.application.ports.out.cohort_ledger import (
        CohortLedger,
    )
    from financial_forecasting.features.inference.application.ports.out.permuted_prediction_persister import (  # noqa: E501
        PermutedPredictionPersister,
    )
    from financial_forecasting.features.inference.application.ports.out.runtime_environment_probe import (  # noqa: E501
        RuntimeEnvironmentProbe,
    )
    from financial_forecasting.features.inference.application.ports.out.silver_table_reader import (
        SilverTableReader,
    )
    from financial_forecasting.features.inference.application.ports.out.vsn_weight_persister import (  # noqa: E501
        VsnWeightPersister,
    )
    from financial_forecasting.features.modeling.application.dtos.cohort_spec import CohortSpec
    from financial_forecasting.features.modeling.application.use_cases.predict_tft_attribution_from_checkpoints import (  # noqa: E501
        AttributionRunPrediction,
    )
    from financial_forecasting.shared.application.ports.out.clock import Clock
    from financial_forecasting.shared.application.ports.out.hasher import Hasher

_SILVER = "silver"
_FACT = "fact_oos_predictions"
_PERMUTED = "fact_permuted_predictions"
_VSN = "fact_vsn_weights"
_TEST = "test"
_IDENTITY_FAMILY = "none"
_VERIFIED = "verified"
_WRITTEN = "written"

Row = Mapping[str, object]


class AblationBaseMismatchError(ApplicationError):
    """A partição veio de um arquivo de ablação cuja base não é o cohort do comando."""


class PartialAttributionError(ApplicationError):
    """Run com linhas de atribuição no silver sem `completed`, ou incompleto (C8)."""


class IncompleteAttributionError(ApplicationError):
    """A predição não cobre o plano: (família, k), decisões x horizontes ou pesos da VSN."""


def check_attribution_coverage(
    run: AttributionRunPrediction,
    *,
    partition: Mapping[str, Sequence[str]],
    test_points: set[tuple[int, int]],
) -> None:
    """C5-1: todo (família, k) do plano, cada grade cobrindo as decisões x horizontes do
    teste da 7.1 e um peso da VSN por decisão de teste — antes de qualquer escrita."""
    expected = {(family, k) for family in partition for k in range(1, K_P + 1)}
    if set(run.permuted) != expected:
        missing = sorted(expected - set(run.permuted))
        extra = sorted(set(run.permuted) - expected)
        raise IncompleteAttributionError(
            f"run {run.run_id}: permuted (family, k) missing {missing[:3]} extra {extra[:3]} "
            f"of the {len(expected)} of the plan (C5-1)"
        )
    grids = {(_IDENTITY_FAMILY, 0): run.identity, **run.permuted}
    for label, by_decision in grids.items():
        points = {(d, h) for d, by_h in by_decision.items() for h in by_h}
        if points != test_points:
            raise IncompleteAttributionError(
                f"run {run.run_id} {label}: {len(points)} decision x horizon grids, the 7.1 "
                f"test has {len(test_points)} (C5-1)"
            )
    decisions = {d for d, _ in test_points}
    if set(run.encoder_weights) != decisions or not all(run.encoder_weights.values()):
        raise IncompleteAttributionError(
            f"run {run.run_id}: vsn weights for {len(run.encoder_weights)} decisions, the 7.1 "
            f"test has {len(decisions)} (C5-1)"
        )


@dataclass(frozen=True)
class RunPermutationInferenceCommand:
    """DTO de entrada — o spec congelado, a partição de famílias, o lock e a justificativa.

    `base_cohort_hash` é o hash da base declarada pelo arquivo de ablação, de onde veio a
    partição: tem de ser o do `spec` (C6-8; o CLI só traduz a recusa em exit 2).
    """

    spec: CohortSpec
    family_partition: Mapping[str, tuple[str, ...]]
    base_cohort_hash: str
    break_stale_lock: bool = False
    cross_environment_justification: str | None = None


@dataclass(frozen=True)
class AttributionRunOutcome:
    """O que aconteceu com um run: gravado ou re-conferido, modo e contagens."""

    run_id: str
    fold_index: int
    seed: int
    status: str
    reproduction_mode: str
    identity_values_compared: int
    max_abs_diff: float
    max_normalized_diff: float
    permuted_rows_written: int
    permuted_rows_verified: int
    vsn_rows_written: int
    vsn_rows_verified: int


@dataclass(frozen=True)
class RunPermutationInferenceResult:
    """DTO de saída — o cohort, o hash da partição e um desfecho por run."""

    cohort_id: str
    partition_hash: str
    outcomes: tuple[AttributionRunOutcome, ...]


def grids_of(run: AttributionRunPrediction) -> int:
    """Grades por valor de teste: a identidade e cada (família, k)."""
    return 1 + len(run.permuted)


def variable_families(
    partition: Mapping[str, Sequence[str]], variables: Sequence[str]
) -> dict[str, str]:
    """Família de cada variável do encoder pela MESMA partição do `partition_hash` (C4-3).

    Variável fora de toda família (calendário, alvo passado, índice relativo) é `"none"`.
    """
    family_of = {feature: family for family, features in partition.items() for feature in features}
    return {variable: family_of.get(variable, _IDENTITY_FAMILY) for variable in variables}


def _refuse_started_elsewhere(
    context: _Context, run_id: str, entry: Mapping[str, object] | None
) -> None:
    """`started` sem linhas só é retomado no ambiente da primeira escrita (C11, como na 7.1).

    A entrada é reescrita (`started` de novo, com o ambiente atual) só quando os dois
    ambientes dão `strict`; senão a retomada é recusada e nada é gravado.
    """
    if entry is None or entry.get("status") != STARTED:
        return
    recorded = entry.get("first_write_environment")
    first = {str(k): str(v) for k, v in recorded.items()} if isinstance(recorded, Mapping) else {}
    differing = environment_mode(first, context.current_environment, None)
    if differing.name != STRICT:
        raise InferenceEnvironmentError(
            f"run {run_id} was started in another environment ({differing.reason}) — "
            "resume it in the original environment (C11)"
        )


def _test_decisions(test_rows: Sequence[Row]) -> set[int]:
    return {int(str(r["decision_idx"])) for r in test_rows}


def _entry_problems(
    context: _Context, entry: Mapping[str, object], *, fold_index: int, test_rows: Sequence[Row]
) -> list[str]:
    """A entrada contra as constantes do plano e o plano gerado (C5-4)."""
    expected: dict[str, object] = {
        "k_p": K_P,
        "permutation_seed": PERMUTATION_SEED,
        "permutation_algorithm": PERMUTATION_ALGORITHM,
        "partition_hash": context.partition_hash,
        "fold_index": fold_index,
        "n_decisions": len(_test_decisions(test_rows)),
    }
    return [
        f"manifest {key} {entry.get(key)!r} != {value!r}"
        for key, value in expected.items()
        if entry.get(key) != value
    ]


def _permuted_problems(
    context: _Context,
    entry: Mapping[str, object],
    permuted: Sequence[Row],
    *,
    test_rows: Sequence[Row],
) -> list[str]:
    """Uma contagem igual à do teste da 7.1 por (família, k), as decisões e as colunas."""
    counts: dict[tuple[str, int], int] = {}
    for row in permuted:
        key = (str(row["permuted_family"]), int(str(row["permutation_index"])))
        counts[key] = counts.get(key, 0) + 1
    expected = {(_IDENTITY_FAMILY, 0)} | {
        (family, k) for family in context.partition for k in range(1, K_P + 1)
    }
    problems: list[str] = []
    if set(counts) != expected or any(counts[key] != len(test_rows) for key in expected):
        problems.append(
            f"permuted counts {dict(sorted(counts.items()))}, {len(test_rows)} test rows each"
        )
    if {int(str(row["decision_idx"])) for row in permuted} != _test_decisions(test_rows):
        problems.append("permuted decisions differ from the 7.1 test decisions")
    for column in ("permutation_seed", "permutation_algorithm", "partition_hash"):
        if any(row.get(column) != entry.get(column) for row in permuted):
            problems.append(f"column {column} differs from the manifest")
    return problems


def _vsn_problems(context: _Context, vsn: Sequence[Row], *, test_rows: Sequence[Row]) -> list[str]:
    """As decisões da VSN são as de teste e a família de cada variável é a da partição."""
    problems: list[str] = []
    if {int(str(row["decision_idx"])) for row in vsn} != _test_decisions(test_rows):
        problems.append("vsn decisions differ from the 7.1 test decisions")
    families = variable_families(context.partition, sorted({str(r["variable"]) for r in vsn}))
    if any(row.get("family") != families[str(row["variable"])] for row in vsn):
        problems.append("vsn family differs from the partition")
    return problems


@dataclass(frozen=True)
class _Context:
    spec: CohortSpec
    cohort_id: str
    seed: int
    partition: Mapping[str, tuple[str, ...]]
    partition_hash: str
    cohort_environment: Mapping[str, str]
    current_environment: Mapping[str, str]
    justification: str | None


class RunPermutationInference:
    """Grava as predições de atribuição de cada run do candidato do cohort congelado."""

    def __init__(  # noqa: PLR0913 — os ports do consumidor (concept 7.3 §4)
        self,
        *,
        resolver: CheckpointResolver,
        predictor: CheckpointAttributionPredictor,
        probe: RuntimeEnvironmentProbe,
        permuted_persister: PermutedPredictionPersister,
        vsn_persister: VsnWeightPersister,
        silver: SilverTableReader,
        ledger: CohortLedger,
        manifest: AttributionManifest,
        hasher: Hasher,
        clock: Clock,
    ) -> None:
        self._resolver = resolver
        self._predictor = predictor
        self._probe = probe
        self._permuted_persister = permuted_persister
        self._vsn_persister = vsn_persister
        self._silver = silver
        self._ledger = ledger
        self._manifest = manifest
        self._hasher = hasher
        self._clock = clock

    def __call__(self, command: RunPermutationInferenceCommand) -> RunPermutationInferenceResult:
        spec = command.spec
        if not spec.is_frozen():
            raise CohortNotFrozenError(
                f"cohort {spec.name!r} r{spec.revision} is not frozen — nothing to attribute"
            )
        justification = validate_justification(command.cross_environment_justification)
        partition = {family: tuple(f) for family, f in command.family_partition.items()}
        partition_hash = FamilyPartitionHash.compute(
            hasher=self._hasher, feature_set_hash=spec.feature_set_hash, partition=partition
        ).value
        cohort_hash = CohortHash.compute(hasher=self._hasher, payload=spec.hash_payload())
        if command.base_cohort_hash != cohort_hash.value:  # C6-8 — antes do lock
            raise AblationBaseMismatchError(
                f"the ablation cohort declares base cohort_hash {command.base_cohort_hash[:12]}, "
                f"but the cohort {spec.name!r} r{spec.revision} has {cohort_hash.value[:12]} — "
                "attribute the base of the ablation cohort"
            )
        cohort_id = spec.cohort_id(cohort_hash)

        self._ledger.acquire_writer(break_stale=command.break_stale_lock)
        try:
            current = dict(self._probe.snapshot())
            if current.get(DIRTY_KEY) == "true":
                raise InferenceEnvironmentError(
                    "tracked uncommitted changes in src/, uv.lock or the cohort file — "
                    "commit first (C11)"
                )
            recorded_environment = self._ledger.environment(cohort_id)
            if recorded_environment is None:
                raise InferenceEnvironmentError(
                    f"cohort {cohort_id} has no recorded environment — run the cohort first (C11)"
                )
            recorded_threads(recorded_environment, cohort_id)
            outcomes: list[AttributionRunOutcome] = []
            for seed in spec.seeds:
                context = _Context(
                    spec=spec,
                    cohort_id=cohort_id,
                    seed=seed,
                    partition=partition,
                    partition_hash=partition_hash,
                    cohort_environment=dict(recorded_environment),
                    current_environment=current,
                    justification=justification,
                )
                outcomes.extend(self._run_seed(context))
        finally:
            self._ledger.release_writer()
        return RunPermutationInferenceResult(
            cohort_id=cohort_id, partition_hash=partition_hash, outcomes=tuple(outcomes)
        )

    # -- seed ---------------------------------------------------------------------

    def _recorded_runs(self, cohort_id: str) -> Mapping[str, Mapping[str, object]]:
        document = self._manifest.recorded(cohort_id) or {}
        runs = document.get("runs", {})
        return runs if isinstance(runs, Mapping) else {}

    def _run_seed(self, context: _Context) -> list[AttributionRunOutcome]:
        spec = context.spec
        resolution = self._resolver(ResolveTftCheckpointsCommand(spec=spec, seed=context.seed))
        if resolution.cohort_id != context.cohort_id or resolution.seed != context.seed:
            raise UnknownRunError(
                f"resolver answered for cohort {resolution.cohort_id} seed {resolution.seed}, "
                f"asked for {context.cohort_id} seed {context.seed}"
            )
        recorded = self._recorded_runs(context.cohort_id)
        test_rows = self._test_rows(spec, {run.run_id for run in resolution.runs})
        allowed: dict[str, str] = {}
        donors_by_fold: dict[int, tuple[tuple[int, ...], ...]] = {}
        verified: list[AttributionRunOutcome] = []
        pending: set[str] = set()
        for run in resolution.runs:
            entry = recorded.get(run.run_id)
            if entry is not None and entry.get("checkpoint_sha256") != run.checkpoint_sha256:
                raise ArtifactChangedError(
                    f"run {run.run_id}: checkpoint sha256 {run.checkpoint_sha256[:12]} != "
                    f"attribution manifest {str(entry.get('checkpoint_sha256'))[:12]} (C7)"
                )
            allowed[run.run_id] = run.checkpoint_sha256
            decisions = sorted({int(str(r["decision_idx"])) for r in test_rows.get(run.run_id, [])})
            if not decisions:
                raise UnknownRunError(f"run {run.run_id} has no test rows in the silver")
            plan = FamilyPermutationPlan.generate(
                permutation_seed=PERMUTATION_SEED,
                k_p=K_P,
                fold_index=run.fold_index,
                n_decisions=len(decisions),
            )
            donors_by_fold[run.fold_index] = plan.permutations
            if entry is not None and entry.get("status") == COMPLETED:
                verified.append(
                    self._reconfer(
                        context,
                        run.run_id,
                        run.fold_index,
                        entry,
                        test_rows=test_rows.get(run.run_id, []),
                    )
                )
                continue
            self._refuse_partial(context, run.run_id, entry)
            _refuse_started_elsewhere(context, run.run_id, entry)  # C11, como na 7.1
            pending.add(run.run_id)
        if not pending:
            return sorted(verified, key=lambda o: o.fold_index)

        prediction = self._predictor(
            PredictTftAttributionCommand(
                spec=spec,
                seed=context.seed,
                allowed=allowed,
                num_threads=recorded_threads(context.cohort_environment, context.cohort_id),
                donors_by_fold=donors_by_fold,
                family_partition=context.partition,
            )
        )
        check_prediction(
            prediction, cohort_id=context.cohort_id, seed=context.seed, allowed=allowed
        )  # C6/C10: seed, run_id repetido e sha256 por run
        written = [
            self._write_run(
                context,
                run=run,
                plan_n=len(donors_by_fold[run.fold_index][0]),
                test_rows=test_rows.get(run.run_id, []),
                settings=prediction.settings,
                timestamps=tuple(prediction.dataset_timestamps),
            )
            for run in sorted(prediction.runs, key=lambda r: r.fold_index)
            if run.run_id in pending
        ]
        return sorted([*verified, *written], key=lambda o: o.fold_index)

    def _test_rows(self, spec: CohortSpec, run_ids: set[str]) -> dict[str, list[Row]]:
        by_run: dict[str, list[Row]] = {}
        for fact in self._silver.read(
            layer=_SILVER,
            table=_FACT,
            filters={"asset": spec.asset_id, "feature_set_name": spec.feature_set_name},
        ):
            run_id = str(fact["run_id"])
            if run_id in run_ids and fact.get("split") == _TEST:
                by_run.setdefault(run_id, []).append(fact)
        return by_run

    def _attribution_rows(self, spec: CohortSpec, table: str, run_id: str) -> list[Row]:
        filters = {
            "asset": spec.asset_id,
            "feature_set_name": spec.feature_set_name,
            "run_id": run_id,
        }
        return [
            row
            for row in self._silver.read(layer=_SILVER, table=table, filters=filters)
            if str(row["run_id"]) == run_id
        ]

    # -- retomada (C8) ---------------------------------------------------------------

    def _refuse_partial(
        self, context: _Context, run_id: str, entry: Mapping[str, object] | None
    ) -> None:
        """Linhas presentes sem `completed` são gravação parcial (C8): nunca reescreve."""
        permuted = self._attribution_rows(context.spec, _PERMUTED, run_id)
        vsn = self._attribution_rows(context.spec, _VSN, run_id)
        if permuted or vsn:
            status = None if entry is None else entry.get("status")
            raise PartialAttributionError(
                f"run {run_id} has {len(permuted)} permuted and {len(vsn)} vsn rows in the "
                f"silver with manifest status {status!r} — partial attribution (C8)"
            )

    def _reconfer(
        self,
        context: _Context,
        run_id: str,
        fold_index: int,
        entry: Mapping[str, object],
        *,
        test_rows: Sequence[Row],
    ) -> AttributionRunOutcome:
        """Run `completed`: as contagens e o plano gravados batem com o manifesto (C8)."""
        permuted, vsn = self._check_rows(
            context, run_id, entry, fold_index=fold_index, test_rows=test_rows
        )
        return AttributionRunOutcome(
            run_id=run_id,
            fold_index=fold_index,
            seed=context.seed,
            status=_VERIFIED,
            reproduction_mode=str(entry.get("mode")),
            identity_values_compared=0,
            max_abs_diff=float(str(entry.get("max_abs_diff"))),
            max_normalized_diff=float(str(entry.get("max_normalized_diff", 0.0))),
            permuted_rows_written=0,
            permuted_rows_verified=len(permuted),
            vsn_rows_written=0,
            vsn_rows_verified=len(vsn),
        )

    def _check_rows(
        self,
        context: _Context,
        run_id: str,
        entry: Mapping[str, object],
        *,
        fold_index: int,
        test_rows: Sequence[Row],
    ) -> tuple[list[Row], list[Row]]:
        """A regra única de conferência das duas tabelas contra uma entrada (C8, C5-1, C5-4).

        Usada na retomada (`_reconfer`) e depois de gravar, antes do `completed`. A entrada
        é conferida contra as constantes do plano e o plano gerado; as linhas, contra a
        entrada, o teste da 7.1 (contagem da identidade e decisões) e a partição (família
        de cada variável da VSN).
        """
        permuted = self._attribution_rows(context.spec, _PERMUTED, run_id)
        vsn = self._attribution_rows(context.spec, _VSN, run_id)
        problems = _entry_problems(context, entry, fold_index=fold_index, test_rows=test_rows)
        problems += _permuted_problems(context, entry, permuted, test_rows=test_rows)
        problems += _vsn_problems(context, vsn, test_rows=test_rows)
        if len(permuted) != entry.get("permuted_rows") or len(vsn) != entry.get("vsn_rows"):
            problems.append(
                f"{len(permuted)} permuted / {len(vsn)} vsn rows, manifest "
                f"{entry.get('permuted_rows')} / {entry.get('vsn_rows')}"
            )
        if problems:
            raise PartialAttributionError(
                f"run {run_id}: the silver differs from the manifest entry: "
                + "; ".join(problems)
                + " (C8)"
            )
        return permuted, vsn

    # -- escrita de um run -----------------------------------------------------------

    def _mode(self, context: _Context) -> ReproductionMode:
        return environment_mode(
            context.cohort_environment, context.current_environment, context.justification
        )

    def _write_run(  # noqa: PLR0913 — o run predito e o que a escrita precisa
        self,
        context: _Context,
        *,
        run: AttributionRunPrediction,
        plan_n: int,
        test_rows: Sequence[Row],
        settings: Mapping[str, str],
        timestamps: tuple[str, ...],
    ) -> AttributionRunOutcome:
        spec = context.spec
        silver_decisions = sorted({int(str(r["decision_idx"])) for r in test_rows})
        if list(run.test_decisions) != silver_decisions or len(run.test_decisions) != plan_n:
            raise ReproductionError(
                f"run {run.run_id}: predicted test decisions differ from the 7.1 silver "
                f"({len(run.test_decisions)} vs {len(silver_decisions)}) (C3-4)"
            )
        check_normalizer_scale(run.run_id, run.normalizer_scale)  # C7
        test_points = {(int(str(r["decision_idx"])), int(str(r["horizon"]))) for r in test_rows}
        check_attribution_coverage(run, partition=context.partition, test_points=test_points)
        mode = self._mode(context)
        reference = {
            (
                int(str(r["decision_idx"])),
                int(str(r["horizon"])),
                float_cell(r["quantile_level"]),
            ): float_cell(r["value_raw"])
            for r in test_rows
        }
        predicted = {
            (decision, horizon, float(level)): float(value)
            for decision, by_horizon in run.identity.items()
            for horizon, grid in by_horizon.items()
            for level, value in zip(spec.quantile_levels, grid, strict=True)
        }
        comparison = compare_reproduction(
            reference,
            predicted,
            mode=mode.name,
            center=run.normalizer_center,
            scale=run.normalizer_scale,
        )
        if not comparison.passed:  # C6 — antes de qualquer escrita
            raise ReproductionError(
                f"run {run.run_id} ({mode.name}): identity outside the reproduction policy — "
                f"{comparison.failures} of {comparison.compared} values, keys match "
                f"{comparison.keys_match}, max|d| {comparison.max_abs_diff:.3e} (C6)"
            )
        entry: dict[str, object] = {
            "checkpoint_sha256": run.checkpoint_sha256,
            "first_write_environment": dict(context.current_environment),
            "settings": dict(settings),
            "mode": mode.name,
            "max_abs_diff": comparison.max_abs_diff,
            "max_normalized_diff": comparison.max_normalized_diff,
            "permutation_seed": PERMUTATION_SEED,
            "k_p": K_P,
            "permutation_algorithm": PERMUTATION_ALGORITHM,
            "fold_index": run.fold_index,
            "n_decisions": plan_n,
            "family_partition": {f: list(v) for f, v in context.partition.items()},
            "partition_hash": context.partition_hash,
            "permuted_rows": 0,
            "vsn_rows": 0,
            "started_at": self._clock.now().isoformat(),
        }
        # C5-8: tudo o que pode recusar a predição (o guardrail do `from_raw`, as famílias
        # da VSN) é montado ANTES do write-ahead; o `started` só precede a escrita.
        entries = self._entries(run, spec)
        variables = sorted({v for weights in run.encoder_weights.values() for v in weights})
        families = variable_families(context.partition, variables)
        decisions = [
            VsnDecisionEntry(decision, dict(weights))
            for decision, weights in sorted(run.encoder_weights.items())
        ]
        model_version, feature_set_name = self._identity_of(test_rows)
        self._manifest.record_run(context.cohort_id, run.run_id, {**entry, "status": STARTED})
        permuted = self._permuted_persister(
            PersistPermutedPredictionsCommand(
                run_id=run.run_id,
                model_version=model_version,
                asset=spec.asset_id,
                feature_set_name=feature_set_name,
                schema_version=self._schema_version(test_rows),
                permutation_seed=PERMUTATION_SEED,
                permutation_algorithm=PERMUTATION_ALGORITHM,
                partition_hash=context.partition_hash,
                dataset_timestamps=timestamps,
                entries=entries,
            )
        )
        vsn = self._vsn_persister(
            PersistVsnWeightsCommand(
                run_id=run.run_id,
                model_version=model_version,
                asset=spec.asset_id,
                feature_set_name=feature_set_name,
                schema_version=self._schema_version(test_rows),
                dataset_timestamps=timestamps,
                variable_families=families,
                decisions=decisions,
            )
        )
        completed = {
            **entry,
            "status": COMPLETED,
            "permuted_rows": len(test_rows) * grids_of(run),
            "vsn_rows": len(decisions) * len(variables),
            "completed_at": self._clock.now().isoformat(),
        }
        if (permuted.rows_written, vsn.rows_written) != (
            completed["permuted_rows"],
            completed["vsn_rows"],
        ):
            raise PartialAttributionError(
                f"run {run.run_id}: wrote {permuted.rows_written} permuted / {vsn.rows_written} "
                f"vsn rows, expected {completed['permuted_rows']} / {completed['vsn_rows']} — "
                "left started (C5-1)"
            )
        # ADR 7.1.0004: o `completed` só depois de reler o silver pela regra do `_reconfer`
        self._check_rows(
            context, run.run_id, completed, fold_index=run.fold_index, test_rows=test_rows
        )
        self._manifest.record_run(context.cohort_id, run.run_id, completed)
        return AttributionRunOutcome(
            run_id=run.run_id,
            fold_index=run.fold_index,
            seed=context.seed,
            status=_WRITTEN,
            reproduction_mode=mode.name,
            identity_values_compared=comparison.compared,
            max_abs_diff=comparison.max_abs_diff,
            max_normalized_diff=comparison.max_normalized_diff,
            permuted_rows_written=permuted.rows_written,
            permuted_rows_verified=0,
            vsn_rows_written=vsn.rows_written,
            vsn_rows_verified=0,
        )

    @staticmethod
    def _entries(run: AttributionRunPrediction, spec: CohortSpec) -> list[PermutedDecisionEntry]:
        """A identidade (`none`, 0) e cada (família, k), com o guardrail do 4.3 (`from_raw`)."""
        levels = tuple(spec.quantile_levels)

        def forecasts(by_horizon: Mapping[int, Sequence[float]]) -> dict[int, QuantileForecast]:
            return {
                horizon: QuantileForecast.from_raw(levels=levels, raw_values=tuple(grid))
                for horizon, grid in sorted(by_horizon.items())
            }

        entries = [
            PermutedDecisionEntry(_IDENTITY_FAMILY, 0, decision, forecasts(by_horizon))
            for decision, by_horizon in sorted(run.identity.items())
        ]
        for (family, k), grids in sorted(run.permuted.items()):
            entries.extend(
                PermutedDecisionEntry(family, k, decision, forecasts(by_horizon))
                for decision, by_horizon in sorted(grids.items())
            )
        return entries

    @staticmethod
    def _identity_of(test_rows: Sequence[Row]) -> tuple[str, str]:
        first = test_rows[0]
        return str(first["model_version"]), str(first["feature_set_name"])

    @staticmethod
    def _schema_version(test_rows: Sequence[Row]) -> int:
        return int(str(test_rows[0]["schema_version"]))
