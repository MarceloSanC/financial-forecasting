"""Gerador da fixture do oráculo NexCP — limiar do `splitCP_LS` dos autores (ADR 7.2.0002 item 5).

Rodado UMA vez no container, com o zip oficial do código de Barber et al. (2023)
montado só leitura; nunca no CI (o CI só lê o JSON congelado):

    uv run --no-sync python tests/fixtures/nexcp_oracle/generate_nexcp_cases.py \
        --zip /scratch/nonexchangeable_conformal.zip --sha256 <sha256> \
        --out tests/fixtures/nexcp_oracle/nexcp_cases.json

O que faz:

1. recusa o zip se o sha256 calculado ≠ `--sha256` (e grava esse valor);
2. localiza o único notebook com `def splitCP_LS(` e a célula que o define, e
   AFIRMA que cada linha transcrita do bloco de limiar está no código da célula;
3. gera escores |N(0, 1)| (semente 20261017) para n ∈ {20, 49, 100, 252},
   rho ∈ {1,0; 0,99; 0,95; 0,9} e alpha ∈ {0,02; 0,1; 0,25}, com os pesos do NexCP
   w_i = rho^(n+1-i) (i = 1 o mais antigo) e o peso 1 do ponto de teste, e aplica a
   transcrição;
4. descarta o caso cuja massa acumulada no índice escolhido (ou no anterior, ou a
   massa total no caso +∞) fica a menos de 1e-9 de 1 - alpha — float e aritmética
   exata escolhem então o mesmo escore;
5. grava o JSON: números de entrada no formato `{"dec", "hex"}` do ADR 6.2.0006
   (`%.17g` e `float.hex`), o escore esperado também em `{"dec", "hex"}` (o teste
   o lê por `float.fromhex`, exato) ou `"inf"`, e o bloco `provenance`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

URL = "https://rinafb.github.io/code/nonexchangeable_conformal.zip"
FUNCTION = "def splitCP_LS("
SEED = 20261017
SIZES = (20, 49, 100, 252)
RHOS = (1.0, 0.99, 0.95, 0.9)
ALPHAS = (0.02, 0.1, 0.25)
MARGIN = 1e-9
GENERATOR = "tests/fixtures/nexcp_oracle/generate_nexcp_cases.py"
# Linhas do bloco de limiar do `splitCP_LS`, transcritas abaixo em `_authors_threshold`.
TRANSCRIBED = (
    "weights_calib = weights[inds_even] / (np.sum(weights[inds_even])+weights[-1])",
    "if(np.sum(weights_calib) >= 1-alpha):",
    "ord_R = np.argsort(R)",
    "ind_thresh = np.min(np.where(np.cumsum(weights_calib[ord_R])>=1-alpha))",
    "calib_thresh = np.sort(R)[ind_thresh]",
    "calib_thresh = np.inf",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _locate_cell(archive: zipfile.ZipFile) -> tuple[str, str, str]:
    """(caminho do notebook, id da célula, código-fonte) da célula que define o `splitCP_LS`."""
    found: list[tuple[str, str, str]] = []
    for name in sorted(archive.namelist()):
        if not name.endswith(".ipynb") or name.startswith("__MACOSX/"):
            continue
        notebook = json.load(io.TextIOWrapper(archive.open(name), encoding="utf-8"))
        for cell in notebook["cells"]:
            source = "".join(cell["source"])
            if cell["cell_type"] == "code" and FUNCTION in source:
                found.append((name, str(cell.get("id")), source))
    if len(found) != 1:
        raise SystemExit(f"expected one cell defining splitCP_LS, found {len(found)}")
    return found[0]


def _check_transcription(source: str) -> None:
    lines = {line.strip() for line in source.splitlines()}
    missing = [line for line in TRANSCRIBED if line not in lines]
    if missing:
        raise SystemExit(f"transcribed lines not in the authors' cell: {missing}")


def _authors_threshold(
    R: np.ndarray, weights: np.ndarray, alpha: float
) -> tuple[float, float, float | None]:
    """Transcrição do bloco de limiar (o calib inteiro no papel de `inds_even`).

    Devolve (limiar, massa no índice escolhido — ou a total no caso +∞, massa no
    índice anterior ou None).
    """
    inds_even = np.arange(len(R))
    weights_calib = weights[inds_even] / (np.sum(weights[inds_even]) + weights[-1])
    if np.sum(weights_calib) >= 1 - alpha:
        ord_R = np.argsort(R)
        cumulative = np.cumsum(weights_calib[ord_R])
        ind_thresh = int(np.min(np.where(cumulative >= 1 - alpha)))
        calib_thresh = float(np.sort(R)[ind_thresh])
        before = float(cumulative[ind_thresh - 1]) if ind_thresh > 0 else None
        return calib_thresh, float(cumulative[ind_thresh]), before
    return float(np.inf), float(np.sum(weights_calib)), None


def _number(value: float) -> dict[str, object]:
    return {"dec": float(format(value, ".17g")), "hex": float(value).hex()}


def _vector(values: np.ndarray) -> dict[str, object]:
    floats = [float(v) for v in values]
    return {"dec": [float(format(v, ".17g")) for v in floats], "hex": [v.hex() for v in floats]}


def _cases() -> tuple[list[dict[str, object]], int]:
    rng = np.random.default_rng(SEED)
    cases: list[dict[str, object]] = []
    discarded = 0
    for n in SIZES:
        for rho in RHOS:
            for alpha in ALPHAS:
                R = np.abs(rng.standard_normal(n))
                weights = np.r_[rho ** (n + 1 - np.arange(1, n + 1)), 1.0]
                threshold, mass, before = _authors_threshold(R, weights, alpha)
                near = [m for m in (mass, before) if m is not None]
                if any(abs(m - (1 - alpha)) < MARGIN for m in near):
                    discarded += 1
                    continue
                cases.append(
                    {
                        "id": f"n{n}-rho{rho}-alpha{alpha}",
                        "n": n,
                        "rho": _number(rho),
                        "alpha": _number(alpha),
                        "scores": _vector(R),
                        "expected": "inf" if np.isinf(threshold) else _number(threshold),
                        "mass_at_choice": float(format(mass, ".17g")),
                    }
                )
    return cases, discarded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    data = args.zip.read_bytes()
    digest = _sha256(data)
    if digest != args.sha256:
        raise SystemExit(f"zip sha256 {digest} != --sha256 {args.sha256}")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        notebook, cell_id, source = _locate_cell(archive)
    _check_transcription(source)
    cases, discarded = _cases()
    document = {
        "provenance": {
            "generator": GENERATOR,
            "source_url": URL,
            "zip_sha256": digest,
            "notebook": notebook,
            "cell_id": cell_id,
            "function": "splitCP_LS",
            "transcribed_lines": list(TRANSCRIBED),
            "numpy_version": np.__version__,
            "python_version": sys.version.split()[0],
            "seed": SEED,
            "sizes": list(SIZES),
            "rhos": list(RHOS),
            "alphas": list(ALPHAS),
            "margin": MARGIN,
            "discarded_cases": discarded,
            "weights": "w_i = rho**(n+1-i), i = 1 oldest; test point weight 1",
            "generated_at": datetime.now(UTC).date().isoformat(),
            "command": (
                "uv run --no-sync python " + GENERATOR + " --zip "
                "/scratch/nonexchangeable_conformal.zip --sha256 <zip_sha256> --out "
                "tests/fixtures/nexcp_oracle/nexcp_cases.json"
            ),
        },
        "cases": cases,
    }
    args.out.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
