"""Proveniência das fixtures do oráculo R é testada, não confiada (A5; ADR 6.2.0006 item 3).

Integração (lê arquivo). `_fixture_problems` valida **qualquer** `tests/fixtures/r_oracle/
*.json` — inclusive os de outras Stages (ex.: `var_test_cases.json` da 6.3) —, dependendo
só do bloco `provenance` e dos objetos `{"dec", "hex"}`, nunca dos nomes de campo dos casos.
Uma regra por item:

1. chave obrigatória de `provenance` ausente;
2. `generator` absoluto ou inexistente (caminho relativo à **raiz do repo**);
3. `session_info` absoluto ou inexistente (caminho relativo ao **JSON**);
4. `r_version` sem `R version <v> (` no `sessionInfo`;
5. `packages` vazio, ou pacote sem o token **inteiro** `<nome>_<versão>` no `sessionInfo`
   (ancorado em espaço/borda de linha: `forecast_8.23` e `cast_8.23.0` não casam
   `forecast_8.23.0`);
6. objeto `{"dec", "hex"}` (varredura recursiva) com formas diferentes (escalar x lista,
   listas de tamanhos diferentes) ou `float(dec) != float.fromhex(hex)`;
7. `image` diferente da imagem do `FROM` do `Dockerfile` ao lado do JSON;
8. `generated_at` fora de `^\\d{4}-\\d{2}-\\d{2}$` ou recusado por `date.fromisoformat`.

Chaves extras em `provenance` são permitidas. O validador verde sobre a fixture boa seria
vácuo sem um caso de violação construído por regra — eles estão abaixo, num repo mínimo em
`tmp_path`.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ORACLE_DIR = _REPO_ROOT / "tests" / "fixtures" / "r_oracle"
_DM_UNIT = "dm_test_cases"
_DOCKERFILE_TEXT = (
    "FROM rocker/r-ver:4.4.1\nRUN install2.r --error --ncpus 4 forecast rugarch jsonlite\n"
)
_REQUIRED_KEYS = (
    "generator",
    "image",
    "r_version",
    "packages",
    "cran_snapshot",
    "generated_at",
    "session_info",
    "command",
)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEC_HEX_KEYS = {"dec", "hex"}
_ABSOLUTE_PATH = re.compile(r"^(?:[/\\]|[A-Za-z]:)")


def _fixture_problems(json_path: Path, *, repo_root: Path) -> list[str]:
    """Todas as violações de proveniência e de round-trip de uma fixture do oráculo R."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    provenance = data.get("provenance", {}) if isinstance(data, dict) else {}
    problems = [
        f"missing provenance key {key!r}" for key in _REQUIRED_KEYS if key not in provenance
    ]
    if "generator" in provenance:
        generator = provenance["generator"]
        if _is_absolute(generator):
            problems.append(f"generator must be relative to the repo root, got {generator!r}")
        elif not (repo_root / generator).is_file():
            problems.append(f"generator not found: {generator}")
    session_text = _session_info_text(json_path, provenance, problems)
    if session_text is not None:
        problems.extend(_version_problems(provenance, session_text))
    problems.extend(_image_problems(json_path, provenance))
    problems.extend(_date_problems(provenance))
    problems.extend(_dec_hex_problems(data, "$"))
    return problems


def _session_info_text(
    json_path: Path, provenance: dict[str, Any], problems: list[str]
) -> str | None:
    if "session_info" not in provenance:
        return None
    if _is_absolute(provenance["session_info"]):
        problems.append(
            f"session_info must be relative to the JSON, got {provenance['session_info']!r}"
        )
        return None
    path = json_path.parent / provenance["session_info"]
    if not path.is_file():
        problems.append(f"session_info not found: {provenance['session_info']}")
        return None
    return path.read_text(encoding="utf-8")


def _version_problems(provenance: dict[str, Any], session_text: str) -> list[str]:
    problems = []
    if "r_version" in provenance and f"R version {provenance['r_version']} (" not in session_text:
        problems.append(f"r_version {provenance['r_version']} not in sessionInfo")
    if "packages" not in provenance:
        return problems
    packages = provenance["packages"]
    if not isinstance(packages, dict) or not packages:
        return [*problems, f"packages must be a non-empty mapping, got {packages!r}"]
    for name, version in packages.items():
        # token inteiro do sessionInfo: "forecast_8.23" não casa "forecast_8.23.0" nem
        # "cast_8.23.0" casa "forecast_8.23.0"
        token = re.escape(f"{name}_{version}")
        if not re.search(rf"(?:^|\s){token}(?:\s|$)", session_text, re.MULTILINE):
            problems.append(f"package {name}_{version} not in sessionInfo")
    return problems


def _is_absolute(path: object) -> bool:
    """Caminho absoluto em POSIX ou Windows (`/x`, barra invertida, `C:...`): exige-se relativo."""
    return not isinstance(path, str) or bool(_ABSOLUTE_PATH.match(path))


def _image_problems(json_path: Path, provenance: dict[str, Any]) -> list[str]:
    if "image" not in provenance:
        return []
    dockerfile = json_path.parent / "Dockerfile"
    if not dockerfile.is_file():
        return ["Dockerfile not found next to the fixture"]
    images = [
        line.split(maxsplit=1)[1].strip()
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ")
    ]
    if images != [provenance["image"]]:
        return [f"image {provenance['image']!r} differs from the Dockerfile FROM {images}"]
    return []


def _date_problems(provenance: dict[str, Any]) -> list[str]:
    if "generated_at" not in provenance:
        return []
    value = provenance["generated_at"]
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        return [f"generated_at {value!r} is not an ISO date YYYY-MM-DD"]
    try:
        date.fromisoformat(value)
    except ValueError:
        return [f"generated_at {value!r} is not a valid date"]
    return []


def _dec_hex_problems(node: object, where: str) -> list[str]:
    if isinstance(node, list):
        return [p for i, item in enumerate(node) for p in _dec_hex_problems(item, f"{where}[{i}]")]
    if not isinstance(node, dict):
        return []
    if set(node) == _DEC_HEX_KEYS:
        return _dec_hex_pair_problems(node["dec"], node["hex"], where)
    return [p for key, item in node.items() for p in _dec_hex_problems(item, f"{where}.{key}")]


def _dec_hex_pair_problems(dec: object, hexa: object, where: str) -> list[str]:
    if isinstance(dec, list) != isinstance(hexa, list):
        return [f"{where}: dec/hex shape mismatch (scalar vs list)"]
    decs = dec if isinstance(dec, list) else [dec]
    hexes = hexa if isinstance(hexa, list) else [hexa]
    if len(decs) != len(hexes):
        return [f"{where}: dec/hex length mismatch ({len(decs)} vs {len(hexes)})"]
    return [
        f"{where}[{index}]: dec {d!r} != hex {h!r}"
        for index, (d, h) in enumerate(zip(decs, hexes, strict=True))
        if float(d) != float.fromhex(h)
    ]


# ---------------------------------------------------------------------------------------
# Fixtures reais
# ---------------------------------------------------------------------------------------

_REAL_FIXTURES = sorted(_ORACLE_DIR.glob("*.json"))


@pytest.mark.integration
def test_prov_real_fixture_set_is_not_empty() -> None:
    assert _REAL_FIXTURES, f"no R-oracle fixture found in {_ORACLE_DIR}"
    assert _ORACLE_DIR / f"{_DM_UNIT}.json" in _REAL_FIXTURES


@pytest.mark.integration
@pytest.mark.parametrize("json_path", _REAL_FIXTURES, ids=lambda path: path.name)
def test_prov_real_fixture_clean(json_path: Path) -> None:
    assert _fixture_problems(json_path, repo_root=_REPO_ROOT) == []


@pytest.mark.integration
def test_prov_dockerfile_two_lines() -> None:
    assert (_ORACLE_DIR / "Dockerfile").read_bytes() == _DOCKERFILE_TEXT.encode("ascii")


# ---------------------------------------------------------------------------------------
# Uma violação construída por regra, num repo mínimo em tmp_path
# ---------------------------------------------------------------------------------------


def _mini_repo(tmp_path: Path) -> Path:
    """Cópia da unidade DM (json, R, sessionInfo, Dockerfile) sob tmp/tests/fixtures/r_oracle."""
    target = tmp_path / "tests" / "fixtures" / "r_oracle"
    target.mkdir(parents=True)
    for name in (f"{_DM_UNIT}.json", f"{_DM_UNIT}.R", f"{_DM_UNIT}.sessionInfo.txt", "Dockerfile"):
        shutil.copyfile(_ORACLE_DIR / name, target / name)
    return target / f"{_DM_UNIT}.json"


def _edit_json(json_path: Path, edit: Callable[[dict[str, Any]], None]) -> None:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    edit(data)
    json_path.write_text(json.dumps(data), encoding="utf-8")


def _problems_after(
    tmp_path: Path, edit: Callable[[dict[str, Any]], None] | None = None
) -> list[str]:
    json_path = _mini_repo(tmp_path)
    if edit is not None:
        _edit_json(json_path, edit)
    return _fixture_problems(json_path, repo_root=tmp_path)


def _first_float_input(data: dict[str, Any]) -> dict[str, Any]:
    number: dict[str, Any] = data["cases"][0]["inputs"]["candidate_losses"]
    return number


@pytest.mark.integration
def test_prov_mini_repo_copy_is_clean(tmp_path: Path) -> None:
    assert _problems_after(tmp_path) == []


@pytest.mark.integration
@pytest.mark.parametrize("key", _REQUIRED_KEYS)
def test_prov_missing_key(tmp_path: Path, key: str) -> None:
    problems = _problems_after(tmp_path, lambda data: data["provenance"].pop(key))
    assert f"missing provenance key {key!r}" in problems


@pytest.mark.integration
def test_prov_generator_missing(tmp_path: Path) -> None:
    json_path = _mini_repo(tmp_path)
    (json_path.parent / f"{_DM_UNIT}.R").unlink()
    problems = _fixture_problems(json_path, repo_root=tmp_path)
    assert problems == [f"generator not found: tests/fixtures/r_oracle/{_DM_UNIT}.R"]


@pytest.mark.integration
def test_prov_session_info_missing(tmp_path: Path) -> None:
    json_path = _mini_repo(tmp_path)
    (json_path.parent / f"{_DM_UNIT}.sessionInfo.txt").unlink()
    problems = _fixture_problems(json_path, repo_root=tmp_path)
    assert problems == [f"session_info not found: {_DM_UNIT}.sessionInfo.txt"]


@pytest.mark.integration
def test_prov_r_version_mismatch(tmp_path: Path) -> None:
    problems = _problems_after(tmp_path, lambda data: data["provenance"].update(r_version="4.4.2"))
    assert problems == ["r_version 4.4.2 not in sessionInfo"]


@pytest.mark.integration
def test_prov_package_version_mismatch(tmp_path: Path) -> None:
    problems = _problems_after(
        tmp_path, lambda data: data["provenance"]["packages"].update(forecast="8.24.0")
    )
    assert problems == ["package forecast_8.24.0 not in sessionInfo"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("packages", "expected"),
    [
        pytest.param(
            {"forecast": "8.23", "jsonlite": "1.8.9"},
            "package forecast_8.23 not in sessionInfo",
            id="version-prefix",
        ),
        pytest.param(
            {"forecast": "8.23.0", "jsonlite": "1.8"},
            "package jsonlite_1.8 not in sessionInfo",
            id="version-prefix-jsonlite",
        ),
        pytest.param(
            {"cast": "8.23.0", "jsonlite": "1.8.9"},
            "package cast_8.23.0 not in sessionInfo",
            id="name-suffix",
        ),
        pytest.param({}, "packages must be a non-empty mapping, got {}", id="empty"),
    ],
)
def test_prov_package_token_anchored(
    tmp_path: Path, packages: dict[str, str], expected: str
) -> None:
    problems = _problems_after(tmp_path, lambda data: data["provenance"].update(packages=packages))
    assert problems == [expected]


@pytest.mark.integration
def test_prov_r_version_prefix_rejected(tmp_path: Path) -> None:
    """ "4.4" é prefixo de "4.4.1": a checagem exige `R version <v> (`."""
    problems = _problems_after(tmp_path, lambda data: data["provenance"].update(r_version="4.4"))
    assert problems == ["r_version 4.4 not in sessionInfo"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "path", ["/abs/dm_test_cases.R", r"\\server\dm.R", "C:/repo/dm_test_cases.R"]
)
def test_prov_absolute_generator_rejected(tmp_path: Path, path: str) -> None:
    problems = _problems_after(tmp_path, lambda data: data["provenance"].update(generator=path))
    assert problems == [f"generator must be relative to the repo root, got {path!r}"]


@pytest.mark.integration
def test_prov_absolute_session_info_rejected(tmp_path: Path) -> None:
    path = "/work/dm_test_cases.sessionInfo.txt"
    problems = _problems_after(tmp_path, lambda data: data["provenance"].update(session_info=path))
    assert problems == [f"session_info must be relative to the JSON, got {path!r}"]


@pytest.mark.integration
def test_prov_hex_mismatch(tmp_path: Path) -> None:
    def edit(data: dict[str, Any]) -> None:
        number = _first_float_input(data)
        number["hex"][0] = (float.fromhex(number["hex"][0]) * 2).hex()

    problems = _problems_after(tmp_path, edit)
    assert len(problems) == 1
    assert "candidate_losses[0]: dec" in problems[0]
    assert "!= hex" in problems[0]


@pytest.mark.integration
def test_prov_dec_length_mismatch(tmp_path: Path) -> None:
    problems = _problems_after(tmp_path, lambda data: _first_float_input(data)["dec"].pop())
    assert len(problems) == 1
    assert "dec/hex length mismatch" in problems[0]


@pytest.mark.integration
def test_prov_scalar_list_shape_mismatch(tmp_path: Path) -> None:
    def edit(data: dict[str, Any]) -> None:
        number = _first_float_input(data)
        number["dec"] = number["dec"][0]

    problems = _problems_after(tmp_path, edit)
    assert len(problems) == 1
    assert "dec/hex shape mismatch (scalar vs list)" in problems[0]


@pytest.mark.integration
def test_prov_image_from_mismatch(tmp_path: Path) -> None:
    problems = _problems_after(
        tmp_path, lambda data: data["provenance"].update(image="rocker/r-ver:4.4.2")
    )
    assert problems == [
        "image 'rocker/r-ver:4.4.2' differs from the Dockerfile FROM ['rocker/r-ver:4.4.1']"
    ]


@pytest.mark.integration
def test_prov_generated_at_not_iso(tmp_path: Path) -> None:
    """`date.fromisoformat("20260928")` é aceito no Python ≥ 3.11: o regex é o gate de formato."""
    problems = _problems_after(
        tmp_path, lambda data: data["provenance"].update(generated_at="20260928")
    )
    assert problems == ["generated_at '20260928' is not an ISO date YYYY-MM-DD"]


@pytest.mark.integration
def test_prov_generated_at_invalid_date(tmp_path: Path) -> None:
    problems = _problems_after(
        tmp_path, lambda data: data["provenance"].update(generated_at="2026-02-30")
    )
    assert problems == ["generated_at '2026-02-30' is not a valid date"]


@pytest.mark.integration
def test_prov_dec_hex_superset_not_recognized_dhexact(tmp_path: Path) -> None:
    """Só objetos com chaves **exatamente** {dec, hex} são números do Step: um superconjunto
    (chave extra) não é conferido — mesmo com dec != hex."""

    def edit(data: dict[str, Any]) -> None:
        data["cases"][0]["inputs"]["annotated"] = {"dec": [1.0], "hex": ["0x1p+1"], "unit": "x"}

    assert _problems_after(tmp_path, edit) == []


@pytest.mark.integration
def test_prov_dockerfile_missing_dfmiss(tmp_path: Path) -> None:
    json_path = _mini_repo(tmp_path)
    (json_path.parent / "Dockerfile").unlink()
    assert _fixture_problems(json_path, repo_root=tmp_path) == [
        "Dockerfile not found next to the fixture"
    ]


@pytest.mark.integration
def test_prov_dockerfile_multi_from_dfmulti(tmp_path: Path) -> None:
    """Dois FROM (build multi-stage) não identificam uma imagem: reprova."""
    json_path = _mini_repo(tmp_path)
    dockerfile = json_path.parent / "Dockerfile"
    dockerfile.write_text(
        "FROM rocker/r-ver:4.4.1\nFROM rocker/r-ver:4.4.1\nRUN true\n", encoding="utf-8"
    )
    assert _fixture_problems(json_path, repo_root=tmp_path) == [
        "image 'rocker/r-ver:4.4.1' differs from the Dockerfile FROM "
        "['rocker/r-ver:4.4.1', 'rocker/r-ver:4.4.1']"
    ]


@pytest.mark.integration
def test_prov_extra_key_allowed(tmp_path: Path) -> None:
    """Chaves extras (ex.: `t_max` da 6.3) não são violação."""
    assert _problems_after(tmp_path, lambda data: data["provenance"].update(t_max=500)) == []
