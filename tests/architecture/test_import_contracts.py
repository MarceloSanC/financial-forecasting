"""Regressão dos contratos de import-linter (Stage 1.3).

A fitness function de arquitetura é o arquivo `.importlinter` na raiz, que
espelha `docs/LAYOUT.md` §3/§6 (fonte da verdade). Este módulo blinda essa
fitness function contra dois modos de falha clássicos de gate inerte/míope
(lição da Stage 1.2):

1. **Contrato verde por acaso** — alguém afrouxa/remove um contrato e o build
   continua passando. Guardado por:
   - `test_real_repo_has_zero_broken_contracts` (o repo real fica 0 broken);
   - `test_importlinter_declares_expected_contracts` (os nomes de contrato
     esperados continuam presentes no `.importlinter`).
2. **Contrato que aprova tudo** — um `forbidden` que não pega nada. Guardado por
   `test_forbidden_contract_detects_violation`, que monta uma config sintética
   apontando para um pacote-fixture proibido em `tmp_path` (NÃO muta a árvore
   real do repo) e exige exit != 0 / contrato `broken`.

Usa a API pública `importlinter.cli.lint_imports` (retorna o exit code int),
evitando `subprocess` (mais determinístico, sem depender do PATH do ambiente).
"""

from __future__ import annotations

import configparser
import sys
import textwrap
from pathlib import Path

import pytest
from importlinter.cli import EXIT_STATUS_ERROR, EXIT_STATUS_SUCCESS, lint_imports

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPORTLINTER_PATH = _REPO_ROOT / ".importlinter"

# Contratos que DEVEM existir no .importlinter. Se um sumir, o gate perdeu
# cobertura — o teste falha (guarda contra afrouxamento/remoção, concept C6).
_EXPECTED_CONTRACTS = (
    "hexagonal-layers",
    "domain-purity",
    "inward-only",
    "shared-no-features",
)


def _load_importlinter() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(_IMPORTLINTER_PATH, encoding="utf-8")
    return parser


def test_importlinter_file_exists_at_repo_root() -> None:
    """O `.importlinter` precisa existir na raiz com root_package esperado."""
    assert _IMPORTLINTER_PATH.is_file(), f".importlinter ausente em {_IMPORTLINTER_PATH}"
    parser = _load_importlinter()
    assert parser["importlinter"]["root_package"] == "financial_forecasting"


def test_importlinter_declares_expected_contracts() -> None:
    """Cada contrato esperado deve estar declarado (guarda contra remoção)."""
    parser = _load_importlinter()
    declared = {
        section.split(":", 2)[2]
        for section in parser.sections()
        if section.startswith("importlinter:contract:")
    }
    missing = set(_EXPECTED_CONTRACTS) - declared
    assert not missing, f"contratos ausentes no .importlinter: {sorted(missing)}"


def test_domain_purity_forbids_the_data_ml_and_framework_libs() -> None:
    """O DoD central: domain-purity proíbe pandas/pyarrow/torch + framework.

    Lê os `forbidden_modules` declarados e exige que o conjunto não-negociável
    esteja presente — blinda contra alguém apagar `pandas` da lista e deixar o
    domínio apodrecer de novo (repo antigo: 23/36 arquivos importavam pandas).
    """
    parser = _load_importlinter()
    section = parser["importlinter:contract:domain-purity"]
    forbidden = set(section["forbidden_modules"].split())
    required = {"pandas", "pyarrow", "torch", "pydantic", "sqlalchemy", "fastapi"}
    assert required <= forbidden, f"domain-purity não proíbe: {sorted(required - forbidden)}"


def test_real_repo_has_zero_broken_contracts() -> None:
    """O repo real, com o `.importlinter` de produção, fica 0 broken.

    Guarda contra "contrato verde por acaso": se a árvore real violar a
    arquitetura (ex.: domain importando pandas), este teste falha junto com o
    gate. `no_cache=True` evita resultado preso a cache de execução anterior.
    """
    exit_code = lint_imports(config_filename=str(_IMPORTLINTER_PATH), no_cache=True)
    assert exit_code == EXIT_STATUS_SUCCESS, (
        "lint-imports deveria estar 0 broken no repo real; "
        f"exit={exit_code}. Rode `uv run lint-imports` para ver o contrato quebrado."
    )


def test_forbidden_contract_detects_violation(tmp_path: Path) -> None:
    """Prova que um `forbidden` detecta a violação (anti contrato-que-aprova-tudo).

    Monta um pacote-fixture sintético (`arch_probe_pkg`) em `tmp_path` cujo
    módulo de "domínio" importa `json` (stdlib disponível, sem instalar nada) e
    uma config sintética com um `forbidden` proibindo justamente `json`. Espera
    exit != 0 / contrato broken. NÃO toca a árvore real do repo.
    """
    pkg_name = "arch_probe_pkg"
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    # módulo que comete a violação: "domain" importando uma lib proibida (json)
    (pkg_dir / "tainted.py").write_text("import json  # violação proposital\n", encoding="utf-8")

    config = tmp_path / "synthetic.importlinter"
    config.write_text(
        textwrap.dedent(
            f"""
            [importlinter]
            root_package = {pkg_name}

            [importlinter:contract:probe-forbidden]
            name = Probe forbidden contract
            type = forbidden
            source_modules =
                {pkg_name}.tainted
            forbidden_modules =
                json
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    try:
        exit_code = lint_imports(config_filename=str(config), no_cache=True)
    finally:
        sys.path.remove(str(tmp_path))
        # limpa o pacote-fixture do cache de import para não vazar entre testes
        for mod in [m for m in sys.modules if m == pkg_name or m.startswith(f"{pkg_name}.")]:
            del sys.modules[mod]

    assert exit_code == EXIT_STATUS_ERROR, (
        "um `forbidden` que proíbe um import REALMENTE presente deveria quebrar "
        f"(exit != 0); obtido exit={exit_code} — contrato pode estar aprovando tudo."
    )


@pytest.mark.parametrize("contract_name", _EXPECTED_CONTRACTS)
def test_each_expected_contract_is_individually_checkable(contract_name: str) -> None:
    """Cada contrato roda isoladamente e fica verde (limit_to_contracts).

    Garante que cada contrato declarado é válido (parseável e satisfeito) por si
    só — uma seção mal formada ou um contrato quebrado é pego aqui, não só no
    veredito agregado.
    """
    exit_code = lint_imports(
        config_filename=str(_IMPORTLINTER_PATH),
        limit_to_contracts=(contract_name,),
        no_cache=True,
    )
    assert exit_code == EXIT_STATUS_SUCCESS, f"contrato '{contract_name}' não está verde"
