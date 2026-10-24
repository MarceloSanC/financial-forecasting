"""Use case `GenerateReportArtifacts` — figuras e dossiê da cópia julgada (Stage 8.3).

Orquestração pura (concept 8.3 §4; ADRs `8_3_0001`-`8_3_0004`), na ordem, guardas antes
de efeitos (I9, I10):

1. foto do ambiente do gerador: `code_dirty` diferente de `"false"` → `DirtyCodeError`
   (I10), antes de qualquer leitura;
2. a revisão julgada (`resolve_judged_revision`) e a partição pelo plano
   (`refresh_command_from(plan, ref).partition` — nunca de um argumento);
3. o `.judged.toml` commitado da referência e a cópia selada cujo digest ele nomeia
   (`judged_copy.sealed_matching_record`; sem registro → `ReportArtifactsError`); a cópia
   como geração (`read_judged_generation` — nunca `current/`, I1); o scorecard (ausente →
   `ReportArtifactsError`) e o `run_record.json` da cópia;
4. o `result_digest` da última `input_read` (`judged_copy.last_input_read_digest`;
   nenhuma → `ReportArtifactsError`);
5. o silver e o realizado conferidos por unidade contra o `silver_content` julgado (D4, I2);
6. as dez `FigureSpec` na ordem do catálogo, um `FigureRecord` por figura e o dossiê —
   tudo puro;
7. só então `renderer.render` de cada spec e **uma** `sink.write` com tudo (I9).

Nenhum byte é escrito se qualquer passo de 1 a 6 falhar, e nada é renderizado antes do 6.
"""

from __future__ import annotations

from collections.abc import Callable

from financial_forecasting.features.evaluation.application.dtos.confirmatory_run import (
    DirtyCodeError,
)
from financial_forecasting.features.evaluation.application.dtos.confirmatory_scorecard import (
    refresh_command_from,
)
from financial_forecasting.features.evaluation.application.dtos.judged_generation import (
    RUN_RECORD_DOCUMENT,
    SCORECARD_DOCUMENT,
)
from financial_forecasting.features.evaluation.application.dtos.report_artifacts import (
    CODE_RECORD_KEYS,
    FIGURE_IDS,
    FigureRecord,
    GenerateReportArtifactsCommand,
    ReportArtifactsError,
    ReportArtifactsResult,
)
from financial_forecasting.features.evaluation.application.ports.out.evaluation_environment import (
    CODE_DIRTY_KEY,
    FALSE,
    EvaluationEnvironment,
)
from financial_forecasting.features.evaluation.application.ports.out.figure_renderer import (
    FigureRenderer,
)
from financial_forecasting.features.evaluation.application.ports.out.judged_generation_store import (  # noqa: E501
    JudgedGenerationStore,
)
from financial_forecasting.features.evaluation.application.ports.out.preregistration_source import (
    PreregistrationSource,
)
from financial_forecasting.features.evaluation.application.ports.out.report_artifact_sink import (
    ReportArtifactSink,
)
from financial_forecasting.features.evaluation.application.ports.out.silver_table_reader import (
    SilverTableReader,
)
from financial_forecasting.features.evaluation.application.ports.out.training_grid_reader import (
    TrainingGridReader,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_copy import (
    committed_records,
    last_input_read_digest,
    sealed_matching_record,
)
from financial_forecasting.features.evaluation.application.use_cases.judged_revision import (
    resolve_judged_revision,
)
from financial_forecasting.features.evaluation.application.use_cases.report_dossier import (
    build_dossier,
)
from financial_forecasting.features.evaluation.application.use_cases.report_figures import (
    FigureAssembly,
    ReportInputs,
    dm_figure,
    fan_chart_figure,
    h3_figure,
    loss_differential_figure,
    native_vs_conformal_figure,
    picp_mpiw_figure,
    quantile_score_figure,
    reliability_figure,
    sharpness_figure,
    vsn_figure,
)
from financial_forecasting.features.evaluation.application.use_cases.report_silver import (
    VerifiedSilver,
    read_verified_silver,
)
from financial_forecasting.shared.application.ports.out.hasher import Hasher


def _builders(
    silver: VerifiedSilver, cohort_seeds: tuple[int, ...]
) -> dict[str, Callable[[ReportInputs], FigureAssembly]]:
    """O montador de cada figura do catálogo (as do silver recebem o silver conferido)."""
    return {
        "reliability_diagram": reliability_figure,
        "quantile_score_plot": quantile_score_figure,
        "sharpness_diagram": lambda inputs: sharpness_figure(inputs, silver),
        "picp_mpiw_plot": picp_mpiw_figure,
        "dm_candidate_vs_comparators": dm_figure,
        "oos_fan_chart": lambda inputs: fan_chart_figure(inputs, silver, cohort_seeds),
        "loss_differential_acf": loss_differential_figure,
        "h3_family_importance": h3_figure,
        "vsn_weights": vsn_figure,
        "native_vs_conformal": native_vs_conformal_figure,
    }


class GenerateReportArtifacts:
    """Gera as dez figuras canônicas, os registros e o dossiê da cópia julgada."""

    def __init__(  # noqa: PLR0913 — 8 colaboradores (concept 8.3 §4)
        self,
        *,
        judged_store: JudgedGenerationStore,
        preregistration_source: PreregistrationSource,
        silver_reader: SilverTableReader,
        grid_reader: TrainingGridReader,
        hasher: Hasher,
        environment: EvaluationEnvironment,
        renderer: FigureRenderer,
        sink: ReportArtifactSink,
    ) -> None:
        self._judged_store = judged_store
        self._source = preregistration_source
        self._silver_reader = silver_reader
        self._grid_reader = grid_reader
        self._hasher = hasher
        self._environment = environment
        self._renderer = renderer
        self._sink = sink

    def __call__(self, command: GenerateReportArtifactsCommand) -> ReportArtifactsResult:
        """Lê, confere, monta, renderiza e escreve (tudo ou nada).

        Raises:
            DirtyCodeError / MissingImageIdError: o gerador não identifica o código (I10).
            PreregistrationNotFoundError / PreregistrationChainError /
                PreregistrationHashMismatchError / PreregistrationNotAnchoredError: a
                revisão não se resolve.
            ReportArtifactsError: sem registro commitado, sem scorecard na cópia ou sem
                `input_read` da referência.
            JudgedGenerationNotFoundError / JudgedGenerationTamperedError: cópia ausente,
                adulterada ou de outro digest.
            SilverContentMismatchError / GridFingerprintMismatchError: silver ou realizado
                diferente do julgado.
            ReportSourceMismatchError: fontes persistidas incoerentes entre si.
        """
        snapshot = self._environment.snapshot()
        if snapshot.get(CODE_DIRTY_KEY) != FALSE:
            raise DirtyCodeError(
                "the generator code tree is dirty: a committed figure needs a clean tree"
            )
        ref = command.preregistration_ref
        resolved = resolve_judged_revision(
            source=self._source,
            hasher=self._hasher,
            name=command.name,
            revision=command.revision,
            preregistration_ref=ref,
        )
        plan = resolved.plan
        partition = refresh_command_from(plan, ref).partition
        sealed = sealed_matching_record(
            source=self._source,
            judged_store=self._judged_store,
            name=command.name,
            preregistration_ref=ref,
            partition=partition,
        )
        if sealed is None:
            raise ReportArtifactsError(f"no committed judged record of {ref}")
        judged_record = committed_records(self._source, name=command.name, preregistration_ref=ref)[
            -1
        ]
        generation = self._judged_store.read_judged_generation(
            partition=partition, preregistration_ref=ref
        )
        scorecard = sealed.documents.get(SCORECARD_DOCUMENT)
        if scorecard is None:
            raise ReportArtifactsError(f"the judged copy of {ref} has no {SCORECARD_DOCUMENT}")
        run_record = sealed.documents[RUN_RECORD_DOCUMENT]
        attempts = self._judged_store.attempts(partition=partition)
        result_digest = last_input_read_digest(attempts, ref)
        if result_digest is None:
            raise ReportArtifactsError(f"no input_read attempt line of {ref}")
        silver = read_verified_silver(
            silver_reader=self._silver_reader,
            grid_reader=self._grid_reader,
            hasher=self._hasher,
            partition=partition,
            expected_fingerprint=plan.realized.dataset_fingerprint,
            judged=generation.manifest.silver_content,
        )
        inputs = ReportInputs(
            plan=plan,
            preregistration_ref=ref,
            partition=partition,
            generation=generation,
            scorecard=scorecard,
        )
        builders = _builders(silver, command.cohort_seeds)
        assemblies = [builders[figure_id](inputs) for figure_id in FIGURE_IDS]
        code = {key: snapshot[key] for key in sorted(CODE_RECORD_KEYS)}
        identity = self._renderer.identity()
        records = tuple(
            FigureRecord(
                figure_id=assembly.spec.figure_id,
                data_digest=assembly.spec.data_digest,
                generation_digest=sealed.generation_digest,
                preregistration_ref=ref,
                revision=command.revision,
                partition=partition,
                sources=assembly.sources,
                silver_units=assembly.silver_units,
                excluded_degenerate=assembly.excluded_degenerate,
                omissions=assembly.spec.omissions,
                code=code,
                renderer=identity,
            )
            for assembly in assemblies
        )
        dossier = build_dossier(
            plan_chain=resolved,
            judged_record=judged_record,
            attempts=attempts,
            result_digest=result_digest,
            revision_digests=resolved.digests,
            run_record=run_record,
            scorecard=scorecard,
            manifest=generation.manifest,
            runs=silver.runs,
            split_fingerprints=silver.split_fingerprints,
            records=records,
            register=command.register,
            snapshot=snapshot,
        )
        figures = [
            (assembly.spec.figure_id, self._renderer.render(assembly.spec), record)
            for assembly, record in zip(assemblies, records, strict=True)
        ]
        self._sink.write(figures=figures, dossier=dossier)
        return ReportArtifactsResult(
            preregistration_ref=ref,
            generation_digest=sealed.generation_digest,
            figures=tuple((record.figure_id, record.data_digest) for record in records),
            register_entries=len(command.register),
        )
