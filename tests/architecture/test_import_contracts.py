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
3. **Contrato míope (mira o alvo errado)** — o `forbidden` existe e quebra em
   tese, mas seus `source_modules` apontam para o pacote errado, de modo que
   uma violação REAL no domínio passa batida. Esse modo NÃO é pego pelos itens
   acima (a config sintética nunca exercita o `.importlinter` de produção, e
   `test_real_repo_has_zero_broken_contracts` continua verde porque o repo real
   está limpo). Guardado por `test_production_contract_reacts_to_real_violation`,
   que injeta TEMPORARIAMENTE um módulo real violando a regra (domínio
   importando `pandas`; `shared` importando `features`), roda o `.importlinter`
   de PRODUÇÃO e exige que o contrato esperado fique `broken` — automatizando a
   prova manual da A3/C1/C3 (concept §6) e travando o drift de `source_modules`.

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
    "tracker-no-mlflow-leak",
    "store-no-storage-leak",
    # Stage 5.2 (I8/A9): statsforecast/numba/numpy confinados ao adapter
    # features/modeling/adapters/out/statsforecast/ (ADR 5.2.0001).
    "modeling-no-statsforecast-leak",
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


_SRC_ROOT = _REPO_ROOT / "src" / "financial_forecasting"

# Violações REAIS expressáveis como arquivo injetado na árvore de produção.
# Cada caso: (contrato esperado broken, arquivos {caminho relativo a _SRC_ROOT:
# conteúdo}). O contrato de produção (.importlinter) é exercitado de ponta a
# ponta — pega o "contrato míope" que mira `source_modules` errado.
_REAL_VIOLATION_CASES = (
    pytest.param(
        "domain-purity",
        {"shared/domain/_arch_audit_taint.py": "import pandas  # violação temporária\n"},
        id="domain-purity:domain-imports-pandas",
    ),
    pytest.param(
        "shared-no-features",
        {
            "features/_arch_audit_probe/__init__.py": "PROBE = 1\n",
            "shared/_arch_audit_taint.py": (
                "from financial_forecasting.features._arch_audit_probe import PROBE\n"
                "\n_use = PROBE\n"
            ),
        },
        id="shared-no-features:shared-imports-feature",
    ),
    pytest.param(
        "tracker-no-mlflow-leak",
        {"shared/application/_arch_audit_taint.py": "import mlflow  # violação temporária\n"},
        id="tracker-no-mlflow-leak:application-imports-mlflow",
    ),
    # Stage 4.1 (A9): o domínio do novo BC analytics_store importando pandas precisa
    # reprovar domain-purity. Automatiza a prova manual da Task 09 e trava o drift de
    # source_modules (contrato míope: se alguém esquecer de incluir
    # `analytics_store.domain` em domain-purity, este caso fica verde e o teste falha).
    pytest.param(
        "domain-purity",
        {
            "features/analytics_store/domain/_arch_audit_taint.py": (
                "import pandas  # violação temporária\n"
            )
        },
        id="domain-purity:analytics-store-domain-imports-pandas",
    ),
    # Stage 4.1 (A9): o mesmo import também precisa reprovar store-no-storage-leak
    # (que cobre pandas/pyarrow/duckdb/pandera em application+domain do BC).
    pytest.param(
        "store-no-storage-leak",
        {
            "features/analytics_store/domain/_arch_audit_taint.py": (
                "import pandera  # violação temporária\n"
            )
        },
        id="store-no-storage-leak:analytics-store-domain-imports-pandera",
    ),
    # Stage 5.1: o domínio do novo BC modeling importando pandas precisa reprovar
    # domain-purity. Trava o drift de source_modules (contrato míope: se alguém
    # esquecer de incluir `modeling.domain` em domain-purity, este caso fica verde
    # e o teste falha).
    pytest.param(
        "domain-purity",
        {
            "features/modeling/domain/_arch_audit_taint.py": (
                "import pandas  # violação temporária\n"
            )
        },
        id="domain-purity:modeling-domain-imports-pandas",
    ),
    # Stage 5.2 (A9): a application do BC modeling importando statsforecast precisa
    # reprovar o novo contrato modeling-no-statsforecast-leak. Automatiza a prova
    # manual da Task 08 e trava o drift de source_modules (contrato míope: se alguém
    # esquecer `modeling.application` no contrato, este caso fica verde e o teste
    # falha).
    pytest.param(
        "modeling-no-statsforecast-leak",
        {
            "features/modeling/application/_arch_audit_taint.py": (
                "import statsforecast  # violação temporária\n"
            )
        },
        id="modeling-no-statsforecast-leak:modeling-application-imports-statsforecast",
    ),
    # Stage 5.2 (A9): o mesmo BC importando pandas na application precisa reprovar
    # store-no-storage-leak (registro do finding da 5.1 §7 — o RunBaselines consome o
    # MedallionStore trocando só primitivos; pandas vive nos adapters).
    pytest.param(
        "store-no-storage-leak",
        {
            "features/modeling/application/_arch_audit_taint.py": (
                "import pandas  # violação temporária\n"
            )
        },
        id="store-no-storage-leak:modeling-application-imports-pandas",
    ),
)


@pytest.mark.parametrize(("contract_name", "files"), _REAL_VIOLATION_CASES)
def test_production_contract_reacts_to_real_violation(
    contract_name: str, files: dict[str, str]
) -> None:
    """O `.importlinter` de PRODUÇÃO fica `broken` numa violação REAL injetada.

    Diferente de `test_forbidden_contract_detects_violation` (config sintética em
    `tmp_path`), aqui exercitamos o `.importlinter` de produção contra a árvore
    real: injetamos um módulo que viola a regra, rodamos o contrato esperado
    isoladamente e exigimos exit != 0. Isso automatiza a prova manual da A3/C1/C3
    e — crucial — pega o "contrato míope": se alguém apontar `source_modules` do
    contrato para o pacote errado, a violação real passa batida e ESTE teste
    falha (os demais continuam verdes). Cleanup garantido em `finally`.
    """
    created: list[Path] = []
    try:
        for rel_path, content in files.items():
            target = _SRC_ROOT / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            # registra o diretório-pai criado (para o caso do pacote-probe), além
            # do arquivo, garantindo remoção completa no finally.
            if target.parent != _SRC_ROOT and not any(p == target.parent for p in created):
                created.append(target.parent)
            target.write_text(content, encoding="utf-8")
            created.append(target)

        exit_code = lint_imports(
            config_filename=str(_IMPORTLINTER_PATH),
            limit_to_contracts=(contract_name,),
            no_cache=True,
        )
        assert exit_code == EXIT_STATUS_ERROR, (
            f"o contrato de produção '{contract_name}' NÃO reagiu a uma violação "
            f"real injetada ({sorted(files)}); exit={exit_code}. Indício de "
            "contrato míope (source_modules mirando o alvo errado) — a fitness "
            "function aprovaria a violação que a Stage existe para barrar."
        )
    finally:
        # remove arquivos primeiro, depois diretórios criados (ordem reversa).
        for path in reversed(created):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                # só remove o que está vazio (não toca pastas pré-existentes).
                pycache = path / "__pycache__"
                if pycache.is_dir():
                    for cached in pycache.iterdir():
                        cached.unlink()
                    pycache.rmdir()
                if not any(path.iterdir()):
                    path.rmdir()


def test_real_repo_clean_after_injection_fixture() -> None:
    """Sanidade: depois dos testes de injeção, o repo real volta a 0 broken.

    Garante que o cleanup em `finally` de
    `test_production_contract_reacts_to_real_violation` não deixou módulo-lixo
    na árvore de produção (que tornaria o gate vermelho de forma espúria).
    """
    exit_code = lint_imports(config_filename=str(_IMPORTLINTER_PATH), no_cache=True)
    assert exit_code == EXIT_STATUS_SUCCESS, (
        "o repo real não voltou a 0 broken — possível resíduo de fixture de "
        f"injeção não limpo; exit={exit_code}."
    )
