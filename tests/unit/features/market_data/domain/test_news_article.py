"""Testes unitários da entity `NewsArticle` (concept 2.3 §5 I1, A1).

Cobre um `NewsArticle` válido + uma violação por invariante (`asset_id` vazio,
`published_at` naive, `source` vazia, `url` sem http(s), `language` com caractere
inválido, texto `None`), cada uma → `ValueError`/`TypeError`, e a normalização de
`language` (`"EN"` → `"en"`).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from financial_forecasting.features.market_data.domain.entities.news_article import (
    NewsArticle,
)

_PUBLISHED = datetime(2024, 1, 2, 11, 50, tzinfo=UTC)


def _valid(**overrides: object) -> NewsArticle:
    """Constrói um `NewsArticle` válido canônico, com overrides pontuais."""
    kwargs: dict[str, object] = {
        "asset_id": "AAPL",
        "published_at": _PUBLISHED,
        "headline": "Apple ships record iPhone",
        "summary": "Quarterly shipments beat estimates.",
        "source": "Reuters",
        "url": "https://example.com/aapl",
        "article_id": "https://example.com/aapl",
        "language": "en",
    }
    kwargs.update(overrides)
    return NewsArticle(**kwargs)  # type: ignore[arg-type]


@pytest.mark.unit
def test_valid_news_article() -> None:
    """Um `NewsArticle` canônico constrói sem erro e preserva os campos."""
    article = _valid()

    assert article.asset_id == "AAPL"
    assert article.published_at == _PUBLISHED
    assert article.headline == "Apple ships record iPhone"
    assert article.source == "Reuters"
    assert article.url == "https://example.com/aapl"
    assert article.language == "en"


@pytest.mark.unit
def test_valid_without_optional_fields() -> None:
    """Os opcionais podem ser `None` (default) — exceto `language` que vem `"en"`."""
    article = NewsArticle(
        asset_id="AAPL",
        published_at=_PUBLISHED,
        headline="h",
        summary="s",
        source="src",
    )

    assert article.url is None
    assert article.article_id is None
    assert article.language == "en"


@pytest.mark.unit
def test_is_frozen() -> None:
    """A entity é imutável (frozen)."""
    article = _valid()
    with pytest.raises(AttributeError):
        article.asset_id = "MSFT"  # type: ignore[misc]


@pytest.mark.unit
def test_empty_asset_id_raises() -> None:
    """`asset_id` vazio → `ValueError`."""
    with pytest.raises(ValueError, match="asset_id must be a non-empty string"):
        _valid(asset_id="  ")


@pytest.mark.unit
def test_naive_published_at_raises() -> None:
    """`published_at` naive → `ValueError`."""
    with pytest.raises(ValueError, match="timezone-aware"):
        _valid(published_at=datetime(2024, 1, 2, 11, 50))


@pytest.mark.unit
def test_non_datetime_published_at_raises() -> None:
    """`published_at` que não é `datetime` → `TypeError`."""
    with pytest.raises(TypeError, match="published_at must be a datetime"):
        _valid(published_at="2024-01-02")


@pytest.mark.unit
def test_empty_source_raises() -> None:
    """`source` vazia → `ValueError`."""
    with pytest.raises(ValueError, match="source must be a non-empty string"):
        _valid(source="   ")


@pytest.mark.unit
def test_none_headline_raises() -> None:
    """`headline` `None` (campo obrigatório de texto) → `TypeError`."""
    with pytest.raises(TypeError, match="headline must be a string"):
        _valid(headline=None)


@pytest.mark.unit
def test_url_without_scheme_raises() -> None:
    """`url` sem `http(s)` → `ValueError`."""
    with pytest.raises(ValueError, match="url must start with"):
        _valid(url="ftp://example.com/x")


@pytest.mark.unit
def test_non_string_url_raises() -> None:
    """`url` não-string → `TypeError`."""
    with pytest.raises(TypeError, match="url must be a string"):
        _valid(url=123)


@pytest.mark.unit
def test_non_string_article_id_raises() -> None:
    """`article_id` não-string → `TypeError`."""
    with pytest.raises(TypeError, match="article_id must be a string"):
        _valid(article_id=123)


@pytest.mark.unit
def test_language_with_invalid_char_raises() -> None:
    """`language` com caractere inválido → `ValueError`."""
    with pytest.raises(ValueError, match="language must contain only letters"):
        _valid(language="en_US")


@pytest.mark.unit
def test_non_string_language_raises() -> None:
    """`language` não-string → `TypeError`."""
    with pytest.raises(TypeError, match="language must be a string"):
        _valid(language=42)


@pytest.mark.unit
def test_blank_language_raises() -> None:
    """`language` em branco quando dado → `ValueError`."""
    with pytest.raises(ValueError, match="language must be non-empty"):
        _valid(language="   ")


@pytest.mark.unit
def test_language_is_normalized_to_lowercase() -> None:
    """`language` `"EN"` é normalizado para `"en"` (com `-` aceito)."""
    assert _valid(language="EN").language == "en"
    assert _valid(language="PT-BR").language == "pt-br"


@pytest.mark.unit
def test_empty_url_is_accepted_as_optional() -> None:
    """`url` string vazia (após strip) não dispara a validação de scheme."""
    article = _valid(url="")
    assert article.url == ""
