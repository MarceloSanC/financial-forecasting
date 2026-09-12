"""Regressão das regras do `scripts/check_layout.py` (issue #60).

O `check_layout.py` COMPLEMENTA o `.importlinter`: ele lê o AST inteiro (inclusive
imports sob `if TYPE_CHECKING:`, que o import-linter exclui por configuração) e
expressa regras de caminho que um contrato `layers`/`forbidden` não alcança.

Este módulo aplica ao script a mesma disciplina que
`test_import_contracts.py` aplica aos contratos: **provar que a regra sabe
reprovar**. A regra 3b nasceu de um falso verde de segunda ordem — a docstring do
script prometia cobrir adapter irmão desde sempre, e `FORBIDDEN_IMPORTS` só
expressava `in <-> out`, de modo que `out/pandas -> out/parquet` passava batido.
Um gate que nunca foi visto reprovando não distingue "a arquitetura está limpa"
de "eu não sei olhar".
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_layout.py"
_SRC_ROOT = _REPO_ROOT / "src" / "financial_forecasting"


def _load_check_layout() -> ModuleType:
    """Carrega `scripts/check_layout.py` como módulo (não é pacote instalável)."""
    spec = importlib.util.spec_from_file_location("_check_layout_under_test", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def check_layout() -> ModuleType:
    return _load_check_layout()


def _write_adapter_tree(root: Path, *, source_rel: str, import_line: str) -> Path:
    """Monta uma árvore-fixture mínima `src/financial_forecasting/...` em tmp."""
    src_root = root / "src" / "financial_forecasting"
    target = src_root / source_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(import_line, encoding="utf-8")
    return src_root


def test_sibling_adapter_rule_flags_out_to_out_import(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """`out/pandas -> out/parquet` reprova — o caso que a regra 3 não expressava.

    É a violação REAL que existe no repo (o montador pandas importa o schema
    pandera do adapter parquet). Aqui ela é reproduzida em árvore sintética para
    que o teste continue válido depois que a violação real for corrigida e a
    entrada sair da `SIBLING_ADAPTER_ALLOWLIST`.
    """
    check_layout.SIBLING_ADAPTER_ALLOWLIST.clear()
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="features/probe/adapters/out/pandas/assembler.py",
        import_line=(
            "from financial_forecasting.features.probe.adapters.out.parquet.schemas"
            ".probe_schema import PROBE\n"
        ),
    )

    violations = check_layout.check_sibling_adapter_imports(src_root)

    assert len(violations) == 1, f"esperava 1 violação, obtive {violations}"
    assert "adapter irmão" in violations[0]


def test_sibling_adapter_rule_allows_import_inside_the_same_slot(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """Import DENTRO do próprio slot é normal — o adapter é um pacote.

    Sem esta checagem, a regra 3b seria larga demais (todo adapter multi-arquivo
    reprovaria) e morreria como ruído no primeiro PR.
    """
    check_layout.SIBLING_ADAPTER_ALLOWLIST.clear()
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="features/probe/adapters/out/parquet/repository.py",
        import_line=(
            "from financial_forecasting.features.probe.adapters.out.parquet.schemas"
            ".probe_schema import PROBE\n"
        ),
    )

    assert check_layout.check_sibling_adapter_imports(src_root) == []


def test_sibling_adapter_rule_flags_dead_allowlist_entry(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """Exceção que não casa mais nada reprova (mesmo princípio do import-linter).

    Sem isto, a allowlist só cresce: entradas mortas viram ruído que mascara o
    próximo afrouxamento, e ninguém percebe que o débito já foi pago.
    """
    check_layout.SIBLING_ADAPTER_ALLOWLIST.clear()
    check_layout.SIBLING_ADAPTER_ALLOWLIST.append(
        ("modulo.que.nao.existe", "prefixo.morto", "fixture")
    )
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="features/probe/adapters/out/parquet/repository.py",
        import_line="PROBE = 1\n",
    )

    violations = check_layout.check_sibling_adapter_imports(src_root)

    assert len(violations) == 1
    assert "ALLOWLIST MORTA" in violations[0]


def test_sibling_adapter_rule_covers_shared_adapters(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """`shared/adapters/out/mlflow -> shared/adapters/out/parquet` reprova.

    A primeira versão de `_adapter_slot` exigia `parts[1] == "features"`, então os
    4 slots irmãos de `shared/adapters/out/` (`calendar`, `hashing`, `mlflow`,
    `parquet`) ficavam fora da regra 3b — o mesmo buraco que a regra nasceu para
    fechar do lado das features, medido pela auditoria da issue #60. Hoje não há
    import cruzado entre eles no repo real; este teste é o que impede o buraco de
    ser usado antes de alguém notar.
    """
    check_layout.SIBLING_ADAPTER_ALLOWLIST.clear()
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="shared/adapters/out/mlflow/tracker.py",
        import_line=(
            "from financial_forecasting.shared.adapters.out.parquet.schemas"
            ".bronze_schemas import PROBE\n"
        ),
    )

    violations = check_layout.check_sibling_adapter_imports(src_root)

    assert len(violations) == 1, f"esperava 1 violação, obtive {violations}"
    assert "adapter irmão" in violations[0]
    assert "('shared', 'out', 'mlflow')" in violations[0]


def test_sibling_adapter_rule_allows_import_inside_the_same_shared_slot(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """Import dentro do próprio slot de `shared` continua normal.

    Contraparte do teste acima: sem isto, estender a regra a `shared` reprovaria
    `parquet/parquet_medallion_store.py -> parquet/schemas/bronze_schemas.py`, que
    é código real e legítimo — a regra morreria como ruído no primeiro PR.
    """
    check_layout.SIBLING_ADAPTER_ALLOWLIST.clear()
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="shared/adapters/out/parquet/parquet_medallion_store.py",
        import_line=(
            "from financial_forecasting.shared.adapters.out.parquet.schemas"
            ".bronze_schemas import PROBE\n"
        ),
    )

    assert check_layout.check_sibling_adapter_imports(src_root) == []


def test_real_repo_passes_the_sibling_adapter_rule() -> None:
    """A árvore real fica limpa (com as exceções declaradas em vigor).

    Contraparte de `test_real_repo_has_zero_broken_contracts`: garante que a
    regra nova não está reprovando o repo — e, junto com o teste de allowlist
    morta, que as exceções declaradas ainda correspondem a imports reais.
    """
    module = _load_check_layout()
    assert module.check_sibling_adapter_imports(_SRC_ROOT) == []


# -- regra 6 (issue #65): hash_mapping/hash_text só são CHAMADOS nos VOs --------------


@pytest.mark.parametrize("method", ["hash_mapping", "hash_text"])
def test_hasher_call_rule_flags_call_outside_value_objects(
    check_layout: ModuleType, tmp_path: Path, method: str
) -> None:
    """`self._hasher.hash_mapping(...)` num use case reprova.

    É a violação REAL que existia em `develop` antes da #65 (3 use cases, 6 sítios,
    cada um com o seu payload privado de identidade). Reproduzida em árvore
    sintética para que o teste continue válido depois da correção.
    """
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="features/probe/application/use_cases/train.py",
        import_line=(
            "class Probe:\n"
            "    def run(self, payload):\n"
            f"        return self._hasher.{method}(payload)\n"
        ),
    )

    violations = check_layout.check_hasher_call_sites(src_root)

    assert len(violations) == 1, f"esperava 1 violação, obtive {violations}"
    assert method in violations[0]
    assert "train.py:3" in violations[0].replace("\\", "/")


def test_hasher_call_rule_allows_calls_inside_shared_value_objects(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """O VO de identidade é o único lugar que chama o port — e passa."""
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="shared/domain/value_objects/probe_id.py",
        import_line=(
            "class ProbeId:\n"
            "    @classmethod\n"
            "    def compute(cls, *, hasher, payload):\n"
            "        return cls(hasher.hash_mapping(payload))\n"
        ),
    )

    assert check_layout.check_hasher_call_sites(src_root) == []


def test_hasher_call_rule_ignores_definitions_of_the_port_and_adapter(
    check_layout: ModuleType, tmp_path: Path
) -> None:
    """Definir `hash_mapping`/`hash_text` (port, adapter) não é chamar — passa.

    Sem isto a regra reprovaria o próprio `Hasher` Protocol e o
    `CanonicalJsonHasher`, e morreria como ruído no primeiro PR.
    """
    src_root = _write_adapter_tree(
        tmp_path,
        source_rel="shared/adapters/out/hashing/probe_hasher.py",
        import_line=(
            "class ProbeHasher:\n"
            "    def hash_mapping(self, payload):\n"
            "        return 'x'\n"
            "    def hash_text(self, text):\n"
            "        return 'y'\n"
        ),
    )

    assert check_layout.check_hasher_call_sites(src_root) == []


def test_real_repo_passes_the_hasher_call_rule() -> None:
    """A árvore real fica limpa: nenhum use case hasheia identidade por conta própria."""
    module = _load_check_layout()
    assert module.check_hasher_call_sites(_SRC_ROOT) == []
