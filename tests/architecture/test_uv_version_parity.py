"""Paridade da versão do `uv` entre a imagem de dev (`Dockerfile`) e o CI (issue #198).

Os gates locais (`uv lock --check`, `uv sync --locked`, `make check`) rodam na imagem
construída pelo `Dockerfile`; o CI instala o `uv` pelo passo `astral-sh/setup-uv` com
`version:` pinada. Se as duas versões divergirem, o verde local deixa de ser evidência do
verde no CI (um resolvedor diferente pode aceitar ou recusar o `uv.lock` de outro jeito).

Onde trocar a versão: o `version:` do `setup-uv` em `.github/workflows/*.yml` **e** a tag
de `COPY --from=ghcr.io/astral-sh/uv:<versão>` no `Dockerfile`, no mesmo commit. Este
teste falha se divergirem, se a imagem voltar a uma tag flutuante (`latest`, `0.11`) ou se
algum `setup-uv` ficar sem `version:`.

Fica em `tests/architecture/` porque lê arquivos do repo, como os outros testes de
arquivos do repo (ex.: `test_stage_7_3_repo_files.py`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[2]
_DOCKERFILE = _REPO / "Dockerfile"
_WORKFLOWS = _REPO / ".github" / "workflows"

# Versão exata `X.Y.Z` — `latest`, `0.11` ou um range não contam como pin.
_EXACT = re.compile(r"^\d+\.\d+\.\d+$")
_IMAGE_TAG = re.compile(r"ghcr\.io/astral-sh/uv:([^\s/@]+)")
_SETUP_UV = re.compile(r"uses:\s*astral-sh/setup-uv@")
_VERSION = re.compile(r"""^\s*version:\s*["']?([^"'\s#]+)["']?""")
_STEP_START = re.compile(r"^\s*-\s")


def dockerfile_uv_tags(text: str) -> list[str]:
    """Tags de toda referência `ghcr.io/astral-sh/uv:<tag>` do Dockerfile."""
    return _IMAGE_TAG.findall(text)


def workflow_uv_versions(text: str) -> list[str | None]:
    """O `version:` de cada passo `astral-sh/setup-uv` (None se o passo não pinar).

    O `version:` procurado é o do mesmo passo: a busca para no início do próximo
    item de lista (`- ...`), para não pegar o `version:` de outro passo.
    """
    lines = text.splitlines()
    found: list[str | None] = []
    for index, line in enumerate(lines):
        if not _SETUP_UV.search(line):
            continue
        version: str | None = None
        for following in lines[index + 1 :]:
            if _STEP_START.match(following):
                break
            match = _VERSION.match(following)
            if match:
                version = match.group(1)
                break
        found.append(version)
    return found


def parity_problems(dockerfile: str, workflows: list[str]) -> list[str]:
    """Divergências entre o uv da imagem e o do CI; lista vazia = paridade."""
    ci = [v for text in workflows for v in workflow_uv_versions(text)]
    tags = dockerfile_uv_tags(dockerfile)
    problems: list[str] = []
    if not ci:
        problems.append("nenhum passo astral-sh/setup-uv nos workflows")
    if any(v is None or not _EXACT.match(v) for v in ci):
        problems.append(f"setup-uv sem versão exata: {ci}")
    if len(set(ci)) > 1:
        problems.append(f"CI com mais de uma versão do uv: {ci}")
    if not tags:
        problems.append("Dockerfile sem ghcr.io/astral-sh/uv:<versão>")
    if any(not _EXACT.match(tag) for tag in tags):
        problems.append(f"tag não pinada no Dockerfile: {tags}")
    if tags and ci and set(tags) != set(ci):
        problems.append(f"Dockerfile uv {tags} != CI setup-uv {ci}")
    return problems


def test_dev_image_uv_matches_ci() -> None:
    workflows = [path.read_text(encoding="utf-8") for path in sorted(_WORKFLOWS.glob("*.y*ml"))]
    assert parity_problems(_DOCKERFILE.read_text(encoding="utf-8"), workflows) == []


# --- O gate pega as divergências que ele existe para pegar ----------------------------


_CI_STEP = (
    "      - name: Install uv\n"
    "        uses: astral-sh/setup-uv@v3\n"
    "        with:\n"
    '          version: "0.11.28"\n'
    "          enable-cache: true\n"
)


def _copy(tag: str) -> str:
    return f"COPY --from=ghcr.io/astral-sh/uv:{tag} /uv /uvx /usr/local/bin/\n"


def test_matching_pins_have_no_problem() -> None:
    assert parity_problems(_copy("0.11.28"), [_CI_STEP]) == []


def test_version_mismatch_is_a_problem() -> None:
    problems = parity_problems(_copy("0.12.3"), [_CI_STEP])
    assert problems == ["Dockerfile uv ['0.12.3'] != CI setup-uv ['0.11.28']"]


def test_floating_latest_tag_is_a_problem() -> None:
    problems = parity_problems(_copy("latest"), [_CI_STEP])
    assert any("não pinada" in p for p in problems), problems


def test_minor_only_tag_is_a_problem() -> None:
    problems = parity_problems(_copy("0.11"), [_CI_STEP])
    assert any("não pinada" in p for p in problems), problems


def test_dockerfile_without_uv_image_is_a_problem() -> None:
    problems = parity_problems("FROM python:3.12-slim\n", [_CI_STEP])
    assert problems == ["Dockerfile sem ghcr.io/astral-sh/uv:<versão>"]


def test_ci_without_setup_uv_is_a_problem() -> None:
    problems = parity_problems(_copy("0.11.28"), ["jobs: {}\n"])
    assert problems == ["nenhum passo astral-sh/setup-uv nos workflows"]


def test_unpinned_setup_uv_is_a_problem() -> None:
    unpinned = "      - uses: astral-sh/setup-uv@v3\n"
    problems = parity_problems(_copy("0.11.28"), [_CI_STEP, unpinned])
    assert any("sem versão exata" in p for p in problems), problems


def test_two_ci_versions_are_a_problem() -> None:
    other = _CI_STEP.replace("0.11.28", "0.12.3")
    problems = parity_problems(_copy("0.11.28"), [_CI_STEP, other])
    assert any("mais de uma" in p for p in problems), problems


def test_every_dockerfile_reference_must_match() -> None:
    text = _copy("0.11.28") + _copy("0.12.3")
    problems = parity_problems(text, [_CI_STEP])
    assert any("!=" in p for p in problems), problems


def test_dockerfile_tags_stop_at_digest_and_path() -> None:
    text = (
        "FROM ghcr.io/astral-sh/uv:0.11.28@sha256:abc AS uv\n"
        "COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/\n"
    )
    assert dockerfile_uv_tags(text) == ["0.11.28", "0.12.3"]


def test_workflow_version_is_read_from_the_same_step() -> None:
    assert workflow_uv_versions(_CI_STEP) == ["0.11.28"]


def test_workflow_step_without_version_is_unpinned() -> None:
    text = (
        "      - uses: astral-sh/setup-uv@v3\n"
        "        with:\n"
        "          enable-cache: true\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        '          version: "9.9.9"\n'
    )
    assert workflow_uv_versions(text) == [None]


def test_workflow_unquoted_and_commented_version() -> None:
    text = "      - uses: astral-sh/setup-uv@v5\n        with:\n          version: 0.12.3  # x\n"
    assert workflow_uv_versions(text) == ["0.12.3"]
