"""Router `POST /inference/run` do slice `inference` (Stage 7.4; ADR 7.4.0002 item 6).

ATENÇÃO — módulo sob `adapters/in/` (keyword `in`): carregue com
`importlib.import_module` (LAYOUT §8). A composition root inclui o `router` na app e
troca o provedor `get_serve_inference` por `dependency_overrides` quando há cohort
configurado (LAYOUT §5 opção 2, §6).

Router fino (concept I10): pedido → `ServeInferenceQuery` → `ServeInference` →
resposta. Não filtra, não decide e não captura exceção: `NoServedDataError` (404),
`ApplicationError` (500) e a validação de corpo (422) saem pelos handlers globais.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from financial_forecasting.features.inference.application.use_cases.serve_inference import (
    ServeInference,
)
from financial_forecasting.shared.application.exceptions import ApplicationError

from .schemas.inference_schemas import InferenceRunRequest, InferenceRunResponse

NOT_CONFIGURED = "serviço de inferência sem cohort configurado"

router = APIRouter(prefix="/inference", tags=["inference"])


class ServingNotConfiguredError(ApplicationError):
    """O processo da API subiu sem arquivo de cohort configurado (concept I12)."""


def get_serve_inference() -> ServeInference:
    """Provedor padrão: sem cohort configurado, todo pedido é 500 (concept I12)."""
    raise ServingNotConfiguredError(NOT_CONFIGURED)


_DESCRIPTION = (
    "Serve as predições de teste já gravadas do candidato para a data de decisão, sem "
    "rodar o modelo: uma grade por seed e horizonte, o intervalo conformal de cada par "
    "(cobertura empírica, não garantida; um intervalo pode vir cruzado, porque a saída "
    "não é rearranjada) e a leitura descritiva de H3. Pedido sem dado gravado → 404."
)


@router.post(
    "/run",
    response_model=InferenceRunResponse,
    summary="Predições gravadas do candidato para uma data de decisão",
    description=_DESCRIPTION,
)
def run_inference(
    request: InferenceRunRequest,
    serve: Annotated[ServeInference, Depends(get_serve_inference)],
) -> InferenceRunResponse:
    """Converte o pedido, chama o use case e converte o payload."""
    return InferenceRunResponse.from_payload(serve(request.to_query()))
