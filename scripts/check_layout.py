"""Script de validação de arquitetura — verifica violações das convenções do docs/LAYOUT.md.

Uso:
    python scripts/check_layout.py
    python scripts/check_layout.py --src src/financial_forecasting

Verifica:
1. Módulos de `domain/` não importam de `application/`, `adapters/`, `infrastructure/`
   ou de libs de framework (fastapi, sqlalchemy, pydantic).
2. Módulos de `application/` não importam de `adapters/` ou `infrastructure/`
   (libs de framework idem).
3. Adapters de uma feature não importam adapters de outras features nem de uma
   subcamada irmã da mesma feature (in não importa out, out não importa in).
4. `shared/` não importa de `features/` (acoplamento inverso é proibido).
5. Cada feature tem os diretórios obrigatórios (`domain/`, `application/`, `adapters/`).

Limitação conhecida: o script não valida que apenas `composition_root.py` faz
wiring (instanciação direta de adapters concretos). Essa regra é verificada por
revisão manual no gate de saída da Stage e está documentada em LAYOUT.md §6.

Retorna código de saída 0 se tudo OK, 1 se houver violações.
"""

import argparse
import ast
import sys
from pathlib import Path

# Um padrão com wildcard único tem exatamente 2 partes após split("*").
_EXPECTED_WILDCARD_PARTS = 2

# ---------------------------------------------------------------------------
# Regras de dependência
# ---------------------------------------------------------------------------

# Padrões de import proibidos por camada (chave = padrão no caminho do arquivo)
FORBIDDEN_IMPORTS: list[tuple[str, list[str]]] = [
    # domain não pode importar de application, adapters ou infrastructure
    (
        "/domain/",
        [
            "financial_forecasting.features.*.application",
            "financial_forecasting.features.*.adapters",
            "financial_forecasting.shared.infrastructure",
            "fastapi",
            "sqlalchemy",
            "pydantic",
        ],
    ),
    # application não pode importar de adapters ou infrastructure
    (
        "/application/",
        [
            "financial_forecasting.features.*.adapters",
            "financial_forecasting.shared.infrastructure",
            "fastapi",
            "sqlalchemy",
        ],
    ),
    # adapters/in não pode importar adapters/out (mesma feature) nem adapters de outras features
    (
        "/adapters/in/",
        [
            "financial_forecasting.features.*.adapters.out",
        ],
    ),
    # adapters/out não pode importar adapters/in (mesma feature) nem adapters de outras features
    (
        "/adapters/out/",
        [
            "financial_forecasting.features.*.adapters.in",
        ],
    ),
    # shared não pode importar de features (ancorado pelo prefixo do pacote)
    (
        "/financial_forecasting/shared/",
        [
            "financial_forecasting.features",
        ],
    ),
]

# Diretórios obrigatórios em cada feature
REQUIRED_FEATURE_DIRS = ["domain", "application", "adapters"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_imports(file_path: Path) -> list[str]:
    """Extrai todos os módulos importados de um arquivo Python."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def matches_pattern(import_str: str, pattern: str) -> bool:
    """Verifica se um import corresponde a um padrão simples com wildcard (*)."""
    if "*" not in pattern:
        return import_str.startswith(pattern)
    parts = pattern.split("*")
    if len(parts) != _EXPECTED_WILDCARD_PARTS:
        return import_str.startswith(parts[0])
    prefix, suffix = parts
    if not import_str.startswith(prefix):
        return False
    remaining = import_str[len(prefix):]
    # O sufixo deve aparecer em algum ponto após o prefixo
    return suffix == "" or suffix in remaining


# ---------------------------------------------------------------------------
# Verificadores
# ---------------------------------------------------------------------------


def check_layer_imports(src_root: Path) -> list[str]:
    """Verifica que cada camada só importa do que é permitido."""
    violations: list[str] = []

    for py_file in src_root.rglob("*.py"):
        file_str = py_file.as_posix()
        imports = get_imports(py_file)

        for layer_pattern, forbidden in FORBIDDEN_IMPORTS:
            # Normaliza para verificar se o arquivo pertence à camada
            if layer_pattern not in file_str.replace("\\", "/"):
                continue

            for imp in imports:
                for forbidden_pattern in forbidden:
                    if matches_pattern(imp, forbidden_pattern):
                        rel = py_file.relative_to(src_root.parent)
                        violations.append(
                            f"VIOLAÇÃO: {rel} importa '{imp}' "
                            f"(proibido para camada '{layer_pattern.strip('/')}')"
                        )
                        break

    return violations


def check_feature_structure(features_root: Path) -> list[str]:
    """Verifica que cada feature tem os diretórios obrigatórios."""
    violations: list[str] = []

    if not features_root.exists():
        return [f"AVISO: diretório de features não encontrado: {features_root}"]

    for feature_dir in features_root.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("_"):
            continue

        for required in REQUIRED_FEATURE_DIRS:
            if not (feature_dir / required).exists():
                violations.append(
                    f"ESTRUTURA: feature '{feature_dir.name}' não tem diretório '{required}/'"
                )

    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Executa todas as verificações e reporta os resultados."""
    parser = argparse.ArgumentParser(
        description="Valida a estrutura de arquitetura do projeto"
    )
    parser.add_argument(
        "--src",
        default="src/financial_forecasting",
        help="Caminho para o pacote fonte (padrão: src/financial_forecasting)",
    )
    args = parser.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        print(f"ERRO: diretório não encontrado: {src_root}")
        return 1

    features_root = src_root / "features"
    all_violations: list[str] = []

    print(f"Verificando arquitetura em: {src_root.resolve()}")
    print()

    # Verifica imports por camada
    import_violations = check_layer_imports(src_root)
    all_violations.extend(import_violations)

    # Verifica estrutura de features
    structure_violations = check_feature_structure(features_root)
    all_violations.extend(structure_violations)

    if all_violations:
        print(f"FALHOU — {len(all_violations)} violação(ões) encontrada(s):\n")
        for v in all_violations:
            print(f"  {v}")
        print()
        return 1

    print("PASSOU — nenhuma violação de arquitetura encontrada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
