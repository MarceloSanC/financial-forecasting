"""Golden do `Hasher` — trava byte-a-byte do esquema canônico de produção.

Rede de regressão da issue #70. Os hashes abaixo foram capturados na base
`41745d8` (develop) ANTES de remover o `FakeHasher`, com fake e adapter real
coincidindo em todos os payloads (asserção feita na captura). Cada literal é
o sha256 hex que o esquema canônico de produção (ADR 1.4.0001) emite para o
payload ao lado — o mesmo esquema que gera `run_id`, `config_signature`,
`split_fingerprint` e `dataset_fingerprint` persistidos na camada silver.

Por que um golden e não só invariantes: os testes do contrato provam
propriedades (determinismo, ordem irrelevante, arredondamento), mas nenhuma
propriedade pina o VALOR. Trocar `separators`, `sort_keys`, `ensure_ascii`, a
precisão declarada ou o algoritmo de digest preserva todas as propriedades e
invalida todo hash persistido. Este módulo torna essa troca visível: qualquer
mudança de valor aqui é uma migração de identidade (issue #65), não um ajuste.

Cobertura deliberada dos payloads:

- vazio, `None` (-> `null`), chaves fora de ordem, aninhado (mapping + lista),
  tupla (-> lista JSON), `bool` (não arredondado), `int` vs `float`, unicode
  (`ensure_ascii=False` preserva os bytes UTF-8);
- float com 12 casas decimais: `1.234567891234` colapsa para o MESMO hash de
  `1.2345678912` (as casas 11-12 são descartadas) e para um hash DIFERENTE de
  `1.234567891` (a 10ª casa sobrevive) — o arredondamento é observável e a
  precisão fica pinada em exatamente 10 casas nas duas direções.
"""

from __future__ import annotations

import pytest

from financial_forecasting.shared.adapters.out.hashing.canonical_json_hasher import (
    CanonicalJsonHasher,
)

# (id, payload, sha256 hex capturado em 41745d8)
_GOLDEN_MAPPINGS: tuple[tuple[str, dict[str, object], str], ...] = (
    (
        "empty",
        {},
        "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    ),
    (
        "flat_with_none",
        {"a": 1, "b": "x", "c": None},
        "3ffee5a45a7c21777779e132ea8221fb86e1add559d7de9ffbb9c7a39fd31845",
    ),
    (
        "dataset_like",
        {"asset": "AAPL", "row_count": 252, "close_sum": 1234.5, "volume_sum": 9.0},
        "00928c06c3b8b08613708dc2a48d4f58b3df611c052a3cd87281c642f1dce7cf",
    ),
    (
        "nested_with_bool",
        {"nested": {"k": [1, 2, 3], "f": 3.14159}, "flag": True},
        "a38bd71fadaafa385e16852b947e2441732d1a770524ee466a1291d072c6dd22",
    ),
    (
        "keys_out_of_order",
        {"z": 1, "a": 2, "m": 3},
        "ebba85cfdc0a724b6cc327ecc545faeb38b9fe02eca603b430eb872f5cf75370",
    ),
    (
        "float_12_decimals",
        {"x": 1.234567891234},
        "dc2d24c64f1f446abc128de12e8caebc0bb8d2a02aae67d70527cc6f6d2e10a7",
    ),
    (
        # MESMO hash de `float_12_decimals`: as casas 11-12 são descartadas.
        "float_rounded_to_10_decimals",
        {"x": 1.2345678912},
        "dc2d24c64f1f446abc128de12e8caebc0bb8d2a02aae67d70527cc6f6d2e10a7",
    ),
    (
        # Hash DIFERENTE: a 10ª casa decimal sobrevive ao arredondamento.
        "float_rounded_to_9_decimals",
        {"x": 1.234567891},
        "3d69eed2b2107ee89ff1bc3b29c5eeb6261ed9be4080a33bdfb35fa2f4657dee",
    ),
    (
        "high_precision_nested",
        {"outer": {"f": 1.234567891234}, "series": [0.000000000123456, 2.0]},
        "4b20930b75fee10c962cb5aa216e9388cb6c7ec2eefa52215ad409f38dcc37a3",
    ),
    (
        "unicode_preserved",
        {"nome": "ação", "símbolo": "€"},
        "f6e675a22e1de6c6ba2b6904a55a632200ba2d24cb53a24eb1e38b59dead7dd6",
    ),
    (
        "int_vs_float",
        {"n": 1, "f": 1.0},
        "ef07faa94a8175f467b6563c29d6ac3f5ec8ed96e83a468b97122c01e70b237e",
    ),
    (
        "tuple_as_json_list",
        {"t": (1, 2.5, "s")},
        "ead23d463b503733d3d0b480fe6003f2dd8056327b4347b9886877c12fc3cfd0",
    ),
    (
        "bool_not_rounded",
        {"b": True, "c": False},
        "7c7b50f79e2b93f33038c05aafd984c5c338fef7e461446c7867a9e456b86b59",
    ),
)

# (id, texto, sha256 hex capturado em 41745d8)
_GOLDEN_TEXTS: tuple[tuple[str, str, str], ...] = (
    (
        "empty",
        "",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    ),
    (
        "pipe_joined",
        "a|b|c",
        "a52dd81bfd5e4e66d96b9f598382f6cbf8c5c3897654e6ae9055e03620fcf38e",
    ),
    (
        "feature_set",
        "feature_one|feature_two",
        "829c7bc271a42f630699826b0266c5e55865caccd2ee85f073644a6e319cd24a",
    ),
    (
        "asset",
        "AAPL",
        "1eb44d625271a4eb75016f276d13783617c012685cb598f20ae93249164c0121",
    ),
    (
        "unicode",
        "ação|€",
        "a3fdb11e90b06e67dafeb5ea9e676bd5c7eaea832bf945d7c32199b87fdeb849",
    ),
)


@pytest.mark.contract
@pytest.mark.parametrize(
    ("payload", "expected"),
    [(payload, expected) for _, payload, expected in _GOLDEN_MAPPINGS],
    ids=[case_id for case_id, _, _ in _GOLDEN_MAPPINGS],
)
def test_hash_mapping_matches_golden(payload: dict[str, object], expected: str) -> None:
    """O adapter real emite, para cada payload, o hash capturado em 41745d8."""
    assert CanonicalJsonHasher().hash_mapping(payload) == expected


@pytest.mark.contract
@pytest.mark.parametrize(
    ("text", "expected"),
    [(text, expected) for _, text, expected in _GOLDEN_TEXTS],
    ids=[case_id for case_id, _, _ in _GOLDEN_TEXTS],
)
def test_hash_text_matches_golden(text: str, expected: str) -> None:
    """`hash_text` emite, para cada texto, o hash capturado em 41745d8."""
    assert CanonicalJsonHasher().hash_text(text) == expected


@pytest.mark.contract
def test_golden_ids_are_unique() -> None:
    """Sanidade do próprio golden: nenhum id duplicado esconde um caso perdido."""
    mapping_ids = [case_id for case_id, _, _ in _GOLDEN_MAPPINGS]
    text_ids = [case_id for case_id, _, _ in _GOLDEN_TEXTS]

    assert len(mapping_ids) == len(set(mapping_ids))
    assert len(text_ids) == len(set(text_ids))
