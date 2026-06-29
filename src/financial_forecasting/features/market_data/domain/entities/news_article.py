"""Entity `NewsArticle` — notícia financeira de um ativo (domínio puro, stdlib-only).

`NewsArticle` é a entity de domínio do bounded context `market_data` para notícias:
identidade lógica `(asset_id, article_id)` (mesma PK lógica da bronze `news`, Stage
2.1) e invariantes validadas na construção (`__post_init__`). Portada quase 1:1 do
old (`financial-time-series-forecasting/src/entities/news_article.py:32-77`), com
um único recorte de julgamento: a validação tz-aware de `published_at` delega ao
helper de domínio `require_tz_aware` (2.2), em vez de reimplementar inline.

Domínio puro: importa SÓ `dataclasses` + `datetime` (stdlib) e o helper UTC do
próprio BC. Sem `pandas`/`pyarrow`/`pydantic` — o gate `import-linter`
`hexagonal-layers`/`domain-purity` reprova qualquer vazamento (concept 2.3 I3).

Invariantes (concept 2.3 §5 I1, levantadas no `__post_init__`):

- `asset_id` é `str` não-vazia (vazio/`None` → `ValueError`).
- `published_at` é `datetime` tz-aware (naive → `ValueError` via `require_tz_aware`).
- `headline`/`summary`/`source` são `str` (não `None` → `TypeError`); `source`
  não-vazia.
- `url`, quando dado, começa com `http://`/`https://` (senão `ValueError`).
- `article_id`, quando dado, é `str` (`TypeError` se não).
- `language`, quando dado, é normalizado para lowercase contendo só letras e `-`
  (caractere inválido → `ValueError`); normalização via `object.__setattr__`
  (frozen). O default `"en"` é normalizado idempotentemente.

Os campos opcionais (`url`/`article_id`/`language`) são `nullable=False` no schema
bronze `NEWS` (2.1): o fallback non-null é responsabilidade do row-mapper do use
case `IngestNews` (concept 2.3 I6/D5), NÃO desta entity — a entity preserva a
semântica de "opcional ausente = `None`".
"""

from dataclasses import dataclass
from datetime import datetime

from financial_forecasting.features.market_data.domain.time.utc import require_tz_aware


@dataclass(frozen=True, slots=True)
class NewsArticle:
    """Notícia financeira imutável com invariantes validadas (concept 2.3 §5 I1).

    Identidade lógica: `(asset_id, article_id)`. `published_at` é tz-aware (UTC no
    pipeline). Construir uma `NewsArticle` que viole qualquer invariante levanta
    `ValueError`/`TypeError` antes de qualquer escrita (concept 2.3 C1).
    """

    asset_id: str
    published_at: datetime
    headline: str
    summary: str
    source: str
    url: str | None = None
    article_id: str | None = None
    language: str | None = "en"

    def __post_init__(self) -> None:
        self._require_asset_id()
        self._require_published_at_tz_aware()
        self._require_text_fields()
        self._require_url()
        self._require_article_id()
        self._normalize_language()

    # -- invariantes ---------------------------------------------------------

    def _require_asset_id(self) -> None:
        """`asset_id` é `str` não-vazia."""
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise ValueError("asset_id must be a non-empty string")

    def _require_published_at_tz_aware(self) -> None:
        """`published_at` é `datetime` tz-aware (naive → `ValueError`)."""
        if not isinstance(self.published_at, datetime):
            raise TypeError("published_at must be a datetime")
        require_tz_aware(self.published_at, "published_at")

    def _require_text_fields(self) -> None:
        """`headline`/`summary`/`source` são `str`; `source` não-vazia."""
        for field_name in ("headline", "summary", "source"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name} must be a string")
        if not self.source.strip():
            raise ValueError("source must be a non-empty string")

    def _require_url(self) -> None:
        """`url`, quando dado, é `str` http(s)."""
        if self.url is None:
            return
        if not isinstance(self.url, str):
            raise TypeError("url must be a string when provided")
        stripped = self.url.strip()
        if stripped and not (stripped.startswith("http://") or stripped.startswith("https://")):
            raise ValueError("url must start with http:// or https://")

    def _require_article_id(self) -> None:
        """`article_id`, quando dado, é `str`."""
        if self.article_id is not None and not isinstance(self.article_id, str):
            raise TypeError("article_id must be a string when provided")

    def _normalize_language(self) -> None:
        """`language`, quando dado, normalizado para lowercase com letras e `-`."""
        if self.language is None:
            return
        if not isinstance(self.language, str):
            raise TypeError("language must be a string when provided")
        lang = self.language.strip().lower()
        if not lang:
            raise ValueError("language must be non-empty when provided")
        if not all(ch.isalpha() or ch == "-" for ch in lang):
            raise ValueError("language must contain only letters and '-'")
        object.__setattr__(self, "language", lang)
