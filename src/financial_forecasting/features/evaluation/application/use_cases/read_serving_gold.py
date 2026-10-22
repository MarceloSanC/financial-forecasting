"""`ReadServingGold` — o gold que a API de inferência serve (Stage 7.4).

Satisfaz, por duck typing, o port do consumidor `ServingGoldReader` do `inference`
(concept 7.4 D5, I7, I8; ADR 7.4.0001 item 7): lê a geração viva pelo
`GoldGenerationReader` (manifesto primeiro; montagem única em
`GoldGeneration.from_stored`), seleciona as colunas pelos `GOLD_*` e pelos leitores de
célula `col_*` (donos únicos) e monta os DTOs do `inference`. É a única aresta de dados
evaluation → inference deste módulo, exceção declarada aos itens 2-3 do ADR 0.0.0053 (a
direção oposta fecharia ciclo com `refresh_gold → calibrate_conformal`).

Fluxo (technical 7.4 §1 "Fluxo do `ReadServingGold`"):

1. só `GoldManifestNotFoundError` vira `ServingGold.unpublished` (nenhuma captura
   genérica de `ApplicationError`: corrupção nunca vira "não publicado");
2. `BLOCKED` → os dois blocos indisponíveis, sem ler tabela (o status vem antes);
3. sem `[conformal]` / sem `[h3]` no pré-registro → o bloco indisponível; sem linha de
   leitura de H3 → explicabilidade indisponível;
4. infinitos reconstruídos das flags: `infinite = true` → `+inf` na correção;
   `lower_infinite`/`upper_infinite = true` → `-inf`/`+inf` no limite da participação
   (flag nula → sem valor); linha de correção com `seed` nulo (unidade de run sem
   seed, nunca servida) é descartada;
5. rótulos conferidos contra as constantes (I7): leitura com `label != H3_LABEL`,
   linha `ok` de VSN com `label != VSN_LABEL` ou linha não-`ok` de VSN com rótulo →
   `GoldGenerationCorruptError`; VSN `undefined` é bloco disponível com linhas
   não-`ok`. `ValueError` de DTO → `GoldGenerationCorruptError`.
"""

from __future__ import annotations

import math
from typing import Final

from financial_forecasting.features.evaluation.application.dtos.gold_schema import (
    GOLD_CONFORMAL_CORRECTIONS,
    GOLD_H3_READING,
    GOLD_H3_SHARES,
    GOLD_H3_VSN,
)
from financial_forecasting.features.evaluation.application.dtos.refresh_gold import (
    GoldGeneration,
    GoldPartition,
    RefreshStatus,
    Row,
    col_bool_or_none,
    col_float,
    col_float_or_none,
    col_int,
    col_int_or_none,
    col_str,
    col_str_or_none,
)
from financial_forecasting.features.evaluation.application.ports.out.gold_generation_reader import (
    GoldGenerationCorruptError,
    GoldGenerationReader,
    GoldManifestNotFoundError,
)
from financial_forecasting.features.evaluation.domain.services.conformal_coverage import (
    EMPIRICAL_COVERAGE_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.contribution_agreement import (
    H3_LABEL,
)
from financial_forecasting.features.evaluation.domain.services.vsn_summary import VSN_LABEL
from financial_forecasting.features.inference.application.dtos.serving_gold import (
    AVAILABLE,
    OK,
    UNAVAILABLE,
    ConformalCorrectionRecord,
    H3ReadingRecord,
    H3ShareRecord,
    ServingGold,
    VsnRecord,
)

_BLOCKED: Final = "geração gold BLOCKED"
_NO_CONFORMAL: Final = "geração sem bloco [conformal]"
_NO_H3: Final = "geração sem bloco [h3]"
_NO_READING: Final = "leitura de H3 ausente na geração"


def _corrections(generation: GoldGeneration) -> tuple[ConformalCorrectionRecord, ...]:
    schema = GOLD_CONFORMAL_CORRECTIONS
    records: list[ConformalCorrectionRecord] = []
    for row in generation.table(schema).rows:
        seed = col_int_or_none(row, schema, "seed")
        if seed is None:
            continue
        infinite = col_bool_or_none(row, schema, "infinite")
        stored = col_float_or_none(row, schema, "correction")
        if infinite and stored is not None:  # o builder grava `null` + flag (TA-6)
            raise GoldGenerationCorruptError(
                f"{schema.name}: infinite = true with correction {stored!r} (expected null)"
            )
        records.append(
            ConformalCorrectionRecord(
                fold_raw=col_str(row, schema, "fold_raw"),
                seed=seed,
                horizon=col_int(row, schema, "horizon"),
                lower_level=col_float(row, schema, "lower_level"),
                upper_level=col_float(row, schema, "upper_level"),
                variant=col_str(row, schema, "variant"),
                tail=col_str(row, schema, "tail"),
                tail_level=col_float(row, schema, "tail_level"),
                status=col_str(row, schema, "status"),
                reason=col_str_or_none(row, schema, "reason"),
                n=col_int_or_none(row, schema, "n"),
                rank=col_int_or_none(row, schema, "rank"),
                correction=math.inf if infinite else stored,
            )
        )
    return tuple(records)


def _bound(row: Row, column: str, infinity: float) -> float | None:
    flag = col_bool_or_none(row, GOLD_H3_SHARES, f"{column}_infinite")
    stored = col_float_or_none(row, GOLD_H3_SHARES, column)
    if flag and stored is not None:  # o builder grava `null` + flag (mesma regra do TA-6)
        raise GoldGenerationCorruptError(
            f"{GOLD_H3_SHARES.name}: {column}_infinite = true with {column} {stored!r} "
            "(expected null)"
        )
    return infinity if flag else stored


def _shares(generation: GoldGeneration) -> tuple[H3ShareRecord, ...]:
    schema = GOLD_H3_SHARES
    return tuple(
        H3ShareRecord(
            method=col_str(row, schema, "method"),
            family=col_str(row, schema, "family"),
            share_h1=col_float_or_none(row, schema, "share_h1"),
            share_h7=col_float_or_none(row, schema, "share_h7"),
            delta=col_float_or_none(row, schema, "delta"),
            lower=_bound(row, "lower", -math.inf),
            upper=_bound(row, "upper", math.inf),
            level=col_float_or_none(row, schema, "level"),
            side=col_int_or_none(row, schema, "side"),  # sinal de Δ̂_f em {-1, 0, +1}
            excludes_zero=col_bool_or_none(row, schema, "excludes_zero"),
            status=col_str(row, schema, "status"),
            reason=col_str_or_none(row, schema, "reason"),
        )
        for row in generation.table(schema).rows
    )


def _reading(row: Row) -> H3ReadingRecord:
    schema = GOLD_H3_READING
    label = col_str_or_none(row, schema, "label")
    if label != H3_LABEL:
        raise GoldGenerationCorruptError(
            f"{schema.name}.label is {label!r}, not the H3 label {H3_LABEL!r}"
        )
    agreeing = col_str(row, schema, "agreeing_families")
    return H3ReadingRecord(
        reading_rule=col_str(row, schema, "reading_rule"),
        heterogeneous_permutation=col_bool_or_none(row, schema, "heterogeneous_permutation"),
        heterogeneous_ablation=col_bool_or_none(row, schema, "heterogeneous_ablation"),
        sustained=col_bool_or_none(row, schema, "sustained"),
        agreeing_families=tuple(agreeing.split(",")) if agreeing else (),
        n_points=col_int_or_none(row, schema, "n_points"),
        status=col_str(row, schema, "status"),
        reason=col_str_or_none(row, schema, "reason"),
    )


def _vsn(generation: GoldGeneration) -> tuple[VsnRecord, ...]:
    schema = GOLD_H3_VSN
    records: list[VsnRecord] = []
    for row in generation.table(schema).rows:
        status = col_str(row, schema, "status")
        label = col_str_or_none(row, schema, "label")
        name = col_str(row, schema, "name")
        if status == OK and label != VSN_LABEL:
            raise GoldGenerationCorruptError(
                f"{schema.name} row {name!r} is ok with label {label!r}, not {VSN_LABEL!r}"
            )
        if status != OK and label is not None:
            raise GoldGenerationCorruptError(
                f"{schema.name} row {name!r} is {status} but carries the label {label!r}"
            )
        records.append(
            VsnRecord(
                kind=col_str(row, schema, "kind"),
                name=name,
                family=col_str(row, schema, "family"),
                p10=col_float_or_none(row, schema, "p10"),
                p50=col_float_or_none(row, schema, "p50"),
                p90=col_float_or_none(row, schema, "p90"),
                n_decisions=col_int_or_none(row, schema, "n_decisions"),
                status=status,
                reason=col_str_or_none(row, schema, "reason"),
            )
        )
    return tuple(records)


_H3Records = tuple[tuple[H3ShareRecord, ...], H3ReadingRecord | None, tuple[VsnRecord, ...]]


def _published(
    generation: GoldGeneration,
    *,
    conformal: tuple[str, str | None],
    explainability: tuple[str, str | None],
    corrections: tuple[ConformalCorrectionRecord, ...] = (),
    h3: _H3Records = ((), None, ()),
) -> ServingGold:
    manifest = generation.manifest
    shares, reading, vsn = h3
    return ServingGold(
        published=True,
        generation_status=manifest.status.value,
        preregistration_ref=manifest.parameters.preregistration_ref,
        candidate=manifest.parameters.candidate,
        finished_at=manifest.finished_at.isoformat(),
        conformal_status=conformal[0],
        conformal_reason=conformal[1],
        explainability_status=explainability[0],
        explainability_reason=explainability[1],
        corrections=corrections,
        shares=shares,
        reading=reading,
        vsn=vsn,
        conformal_label=EMPIRICAL_COVERAGE_LABEL,
        h3_label=H3_LABEL,
        vsn_label=VSN_LABEL,
    )


def _serving(generation: GoldGeneration) -> ServingGold:
    parameters = generation.manifest.parameters
    if generation.manifest.status is RefreshStatus.BLOCKED:
        blocked = (UNAVAILABLE, _BLOCKED)
        return _published(generation, conformal=blocked, explainability=blocked)
    corrections: tuple[ConformalCorrectionRecord, ...] = ()
    conformal: tuple[str, str | None] = (UNAVAILABLE, _NO_CONFORMAL)
    if parameters.conformal_parameters is not None:
        conformal, corrections = (AVAILABLE, None), _corrections(generation)
    if parameters.h3_parameters is None:
        return _published(
            generation,
            conformal=conformal,
            explainability=(UNAVAILABLE, _NO_H3),
            corrections=corrections,
        )
    rows = generation.table(GOLD_H3_READING).rows
    if not rows:
        return _published(
            generation,
            conformal=conformal,
            explainability=(UNAVAILABLE, _NO_READING),
            corrections=corrections,
        )
    if len(rows) > 1:
        raise GoldGenerationCorruptError(
            f"{GOLD_H3_READING.name} has {len(rows)} rows; a generation reads H3 once"
        )
    return _published(
        generation,
        conformal=conformal,
        explainability=(AVAILABLE, None),
        corrections=corrections,
        h3=(_shares(generation), _reading(rows[0]), _vsn(generation)),
    )


class ReadServingGold:
    """Lê do gold vivo de um cohort o que a API de inferência serve."""

    def __init__(self, *, gold_reader: GoldGenerationReader) -> None:
        self._gold_reader = gold_reader

    def read(self, *, asset: str, cohort_id: str) -> ServingGold:
        """O gold servido da partição (`asset`, `cohort_id`).

        Raises:
            GoldGenerationCorruptError: a geração lida não se sustenta (inclusive rótulo
                gravado divergente da constante de dono único).
        """
        partition = GoldPartition(asset, cohort_id)
        try:
            generation = self._gold_reader.read_generation(partition=partition)
        except GoldManifestNotFoundError:
            return ServingGold.unpublished(
                reason=f"gold não publicado para o cohort {cohort_id}",
                conformal_label=EMPIRICAL_COVERAGE_LABEL,
                h3_label=H3_LABEL,
                vsn_label=VSN_LABEL,
            )
        try:
            return _serving(generation)
        except ValueError as error:
            raise GoldGenerationCorruptError(
                f"the gold generation of {asset}/{cohort_id} does not hold: {error}"
            ) from error
