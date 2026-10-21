"""Interpolação linear determinística na GPU (Stage 7.3, C12; ADR 7.3.0004 item 5).

O backward de `F.interpolate(mode="linear")` na GPU (`upsample_linear1d_backward`) usa
`atomicAdd` e não tem kernel determinístico em CUDA/ROCm; sob
`use_deterministic_algorithms(True)` o treino do TFT aborta. O adapter troca a
interpolação do `TimeDistributedInterpolation` por uma combinação linear dos 2 vizinhos
via `index_select` (determinística) — SÓ na GPU; a CPU fica byte-idêntica à lib.

Estes testes rodam na CPU (CI sem GPU): conferem a equivalência numérica da reescrita
contra `F.interpolate` e o liga/desliga do context manager. O determinismo bit-exato em
GPU é um smoke pulado sem GPU (e verificado de fato no piloto da fase Linux).
"""

from __future__ import annotations

import pytest
import torch
import torch.nn.functional as F
from pytorch_forecasting.models.temporal_fusion_transformer.sub_modules import (
    TimeDistributedInterpolation,
)

from financial_forecasting.features.modeling.adapters.out.pytorch_forecasting import (
    pf_tft_trainer as module,
)

pytestmark = [pytest.mark.integration]


def _native_interpolate(x: torch.Tensor, out_size: int) -> torch.Tensor:
    """O op exato do `TimeDistributedInterpolation` (x é (N, W_in))."""
    return F.interpolate(x.unsqueeze(1), out_size, mode="linear", align_corners=True).squeeze(1)


@pytest.mark.parametrize(
    ("width", "out_size"),
    [(3, 8), (4, 7), (64, 128), (128, 64), (16, 37), (16, 16), (1, 5), (5, 1)],
)
def test_gather_matches_native_interpolate_on_cpu(width: int, out_size: int) -> None:
    """A reescrita por gather é a MESMA interpolação linear (diferença só de arredondamento)."""
    torch.manual_seed(0)
    x = torch.randn(8, width)
    reference = _native_interpolate(x, out_size)
    gathered = module._gather_linear_1d(x, out_size)
    assert gathered.shape == reference.shape
    assert torch.allclose(gathered, reference, atol=1e-5, rtol=0.0)


def test_gather_identity_when_sizes_match() -> None:
    """Quando `out_size == width` a interpolação é identidade exata."""
    x = torch.randn(4, 11)
    assert torch.equal(module._gather_linear_1d(x, 11), x)


def test_gather_backward_is_deterministic_and_errorless_on_cpu() -> None:
    """Sob determinismo, o gradiente da reescrita roda e é bit-idêntico entre execuções."""
    torch.use_deterministic_algorithms(True)
    try:

        def once() -> torch.Tensor:
            x = torch.randn(6, 16, generator=torch.Generator().manual_seed(1)).requires_grad_(True)
            module._gather_linear_1d(x, 40).sum().backward()
            assert x.grad is not None
            return x.grad.clone()

        assert torch.equal(once(), once())
    finally:
        torch.use_deterministic_algorithms(False)


def test_context_manager_is_noop_off_gpu() -> None:
    """`accelerator != "gpu"` não troca o método da lib."""
    original = TimeDistributedInterpolation.interpolate
    with module._deterministic_gpu_interpolation("cpu"):
        assert TimeDistributedInterpolation.interpolate is original
    assert TimeDistributedInterpolation.interpolate is original


def test_context_manager_swaps_on_gpu_and_restores() -> None:
    """`accelerator == "gpu"` troca o método dentro do escopo e restaura ao sair."""
    original = TimeDistributedInterpolation.interpolate
    with module._deterministic_gpu_interpolation("gpu"):
        assert TimeDistributedInterpolation.interpolate is not original
    assert TimeDistributedInterpolation.interpolate is original


def test_patched_method_leaves_cpu_tensors_on_native_path() -> None:
    """Dentro do patch de GPU, um tensor de CPU ainda passa pelo caminho original da lib."""
    layer = TimeDistributedInterpolation(output_size=9)
    x = torch.randn(3, 4)
    expected = layer.interpolate(x)
    with module._deterministic_gpu_interpolation("gpu"):
        patched = layer.interpolate(x)
    assert torch.equal(patched, expected)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="sem GPU visível ao torch")
def test_native_interpolate_backward_raises_under_determinism_on_gpu() -> None:
    """Prova da necessidade: o op nativo aborta no backward sob determinismo na GPU."""
    torch.use_deterministic_algorithms(True)
    try:
        x = torch.randn(8, 3, device="cuda", requires_grad=True)
        with pytest.raises(RuntimeError, match="upsample_linear1d_backward"):
            _native_interpolate(x, 8).sum().backward()
    finally:
        torch.use_deterministic_algorithms(False)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="sem GPU visível ao torch")
def test_gather_is_bit_identical_across_runs_on_gpu() -> None:
    """A reescrita treina sob determinismo na GPU e é bit-idêntica entre execuções."""
    torch.use_deterministic_algorithms(True)
    try:

        def once() -> tuple[torch.Tensor, torch.Tensor]:
            x = torch.randn(
                64, 512, device="cuda", generator=torch.Generator(device="cuda").manual_seed(7)
            ).requires_grad_(True)
            y = module._gather_linear_1d(x, 1024)
            y.sum().backward()
            assert x.grad is not None
            return y.detach().clone(), x.grad.clone()

        y1, g1 = once()
        y2, g2 = once()
        assert torch.equal(y1, y2)
        assert torch.equal(g1, g2)
    finally:
        torch.use_deterministic_algorithms(False)
