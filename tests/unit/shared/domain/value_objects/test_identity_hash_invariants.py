"""Invariante de construção dos VOs de identidade de `shared` (issue #160).

Cada VO guarda um sha256 hex. A factory `compute` sempre produz um, mas o construtor
da dataclass segue chamável. O teste prova que o caminho cru `Cls(value=...)` também
valida: aceita o `hexdigest()` e recusa o resto, com a mensagem nomeando a classe.
"""

from __future__ import annotations

from hashlib import sha256

import pytest

from financial_forecasting.shared.domain.value_objects.cohort_hash import CohortHash
from financial_forecasting.shared.domain.value_objects.config_signature import ConfigSignature
from financial_forecasting.shared.domain.value_objects.dataset_content_fingerprint import (
    DatasetContentFingerprint,
)
from financial_forecasting.shared.domain.value_objects.preregistration_hash import (
    PreregistrationHash,
)
from financial_forecasting.shared.domain.value_objects.run_id import RunId
from financial_forecasting.shared.domain.value_objects.split_fingerprint import (
    SplitFingerprint,
)

_IDENTITY_VOS = [
    RunId,
    ConfigSignature,
    SplitFingerprint,
    DatasetContentFingerprint,
    CohortHash,
    PreregistrationHash,
]
_HEX = sha256(b"identity").hexdigest()


@pytest.mark.unit
@pytest.mark.parametrize("cls", _IDENTITY_VOS, ids=lambda cls: cls.__name__)
def test_raw_constructor_accepts_a_sha256_hex(cls: type) -> None:
    assert cls(value=_HEX).value == _HEX


@pytest.mark.unit
@pytest.mark.parametrize("cls", _IDENTITY_VOS, ids=lambda cls: cls.__name__)
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("run-1", id="label"),
        pytest.param("", id="empty"),
        pytest.param(_HEX.upper(), id="uppercase"),
        pytest.param(_HEX[:-1], id="63-chars"),
        pytest.param(None, id="none"),
    ],
)
def test_raw_constructor_rejects_anything_else(cls: type, value: object) -> None:
    with pytest.raises(ValueError, match=rf"^{cls.__name__}\.value must be a lowercase sha256"):
        cls(value=value)
