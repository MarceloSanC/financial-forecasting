"""Gate: a API de inferência não carrega a pilha de deep learning (Stage 7.4, Task 08) — CA10.

Em subprocesso limpo (`sys.executable`), monta a app com o cenário mínimo do e2e (silver
sintético e gold publicado em `tmp_path`, cohort real só como arquivo de configuração),
atende um pedido e afirma que `torch`, `lightning` e `pytorch_forecasting` não estão em
`sys.modules`. O processo do pytest não serve de prova, porque outros testes podem ter
carregado torch antes. O contrato estático é o `inference-no-torch-leak`, estendido ao
pacote do router (ADR 7.4.0001 item 1).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

_REPO = Path(__file__).resolve().parents[4]
_FORBIDDEN = ("torch", "lightning", "pytorch_forecasting")

_SCRIPT = """
import json, sys
from pathlib import Path
from fastapi.testclient import TestClient
from financial_forecasting.shared.infrastructure.http.app import create_app
from tests.e2e.features.inference.test_inference_api_e2e import (
    _publish, _settings, _write_silver,
)

root = Path(sys.argv[1])
_write_silver(root)
_publish(root)
client = TestClient(create_app(_settings(root)))
response = client.post("/inference/run", json={"asset": "AAPL", "decision_date": "2024-03-15"})
forbidden = sorted(
    name for name in sys.modules
    if name.split(".")[0] in {"torch", "lightning", "pytorch_forecasting"}
)
print(json.dumps({"status": response.status_code, "forbidden": forbidden}))
"""


def test_serving_a_request_loads_no_deep_learning_stack(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(tmp_path)],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert report["status"] == 200  # noqa: PLR2004
    assert report["forbidden"] == [], f"carregados: {report['forbidden']} (proibidos: {_FORBIDDEN})"
