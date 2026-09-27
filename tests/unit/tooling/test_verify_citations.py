"""Unit das partes puras de `scripts/verify_citations.py` (sem rede)."""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_EXIT_OK, _EXIT_FAIL, _EXIT_INCONCLUSIVE = 0, 1, 2
_UNRELATED_MAX = 0.5

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "verify_citations.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("verify_citations", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass resolve o módulo pelo nome
    spec.loader.exec_module(module)
    return module


vc = _load()


def test_extract_dois_strips_trailing_punctuation_and_dedups() -> None:
    text = (
        "Walters (2023), doi:10.1038/s41598-023-41032-5. De novo "
        "(https://doi.org/10.1038/s41598-023-41032-5) e 10.1287/mnsc.34.6.679;"
    )
    assert vc.extract_dois(text) == ["10.1038/s41598-023-41032-5", "10.1287/mnsc.34.6.679"]


def test_extract_dois_keeps_balanced_parentheses() -> None:
    # caso real (doc da #78): DOIs da Elsevier eram truncados em "S0169-2070" → falso NOT_FOUND
    text = "Tashman (2000, doi:10.1016/S0169-2070(00)00065-0). Ver 10.1016/S0169-2070(96)00719-4."
    assert vc.extract_dois(text) == [
        "10.1016/S0169-2070(00)00065-0",
        "10.1016/S0169-2070(96)00719-4",
    ]


_FEED = b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/0912.0902v2</id>
    <published>2009-12-04T00:00:00Z</published>
    <title>Making and Evaluating
      Point Forecasts</title>
    <author><name>Tilmann Gneiting</name></author>
  </entry>
</feed>"""


def test_parse_arxiv_feed_maps_entries_and_marks_missing() -> None:
    found, missing = vc.parse_arxiv_feed(_FEED, ["0912.0902", "9999.99999"])
    assert (found.status, found.author, found.year) == ("OK", "Gneiting", "2009")
    assert found.title == "Making and Evaluating Point Forecasts"
    assert missing.status == "NOT_FOUND"


def test_check_arxiv_falls_back_to_arxiv_api_when_datacite_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vc, "_check_arxiv_datacite", lambda i: vc.Result("ERROR", "arXiv:" + i))
    monkeypatch.setattr(vc, "_get", lambda _url: _FEED)
    monkeypatch.setattr(vc.time, "sleep", lambda _s: None)
    [result] = vc.check_arxiv(["0912.0902"])
    assert result.status == "OK"


class _Resp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def _http_error(url: str, code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "http error", Message(), None)


def test_get_retries_on_arxiv_rate_limit_406(monkeypatch: pytest.MonkeyPatch) -> None:
    # caso real (sessão da #78): o arXiv responde HTTP 406 sob rajada, não erro de rede
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_urlopen(req: urllib.request.Request, timeout: float) -> _Resp:
        calls.append(req.full_url)
        if len(calls) == 1:
            raise _http_error(req.full_url, 406)
        return _Resp(b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(vc.time, "sleep", sleeps.append)
    url = "https://export.arxiv.org/api/query?id_list=0912.0902"
    assert vc._get(url) == b"ok"
    assert calls == [url, url]
    assert sleeps == [5]


_DATACITE = (
    b'{"data": {"attributes": {"titles": [{"title": "Making and Evaluating Point Forecasts"}],'
    b' "creators": [{"name": "Gneiting, Tilmann", "familyName": "Gneiting"}],'
    b' "publicationYear": 2009}}}'
)


def test_check_arxiv_datacite_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vc, "_get", lambda _url: _DATACITE)
    result = vc._check_arxiv_datacite("0912.0902")
    assert result == vc.Result(
        "OK", "arXiv:0912.0902", "2009", "Gneiting", "Making and Evaluating Point Forecasts"
    )


def test_check_arxiv_datacite_404_is_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_404(url: str) -> bytes:
        raise _http_error(url, 404)

    monkeypatch.setattr(vc, "_get", raise_404)
    assert vc._check_arxiv_datacite("9999.99999").status == "NOT_FOUND"


def test_check_arxiv_datacite_unexpected_payload_is_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # ERROR (não exceção) para o check_arxiv cair na reserva da API do arXiv
    monkeypatch.setattr(vc, "_get", lambda _url: b'{"errors": [{"status": "500"}]}')
    assert vc._check_arxiv_datacite("0912.0902").status == "ERROR"


def test_extract_arxiv_ids_from_prefix_and_url() -> None:
    text = "arXiv:2309.11495 e https://arxiv.org/abs/2104.08542v2, não 12.34"
    assert vc.extract_arxiv_ids(text) == ["2309.11495", "2104.08542"]


def test_title_similarity_ignores_case_and_punctuation() -> None:
    title = "Specification curve analysis"
    assert vc.title_similarity(title, "Specification Curve Analysis.") == 1.0
    assert vc.title_similarity(title, "Deep residual learning") < _UNRELATED_MAX


def test_main_without_citations_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty.md"
    empty.write_text("sem referências aqui", encoding="utf-8")
    assert vc.main([str(empty)]) == _EXIT_FAIL


def test_main_exit_codes_follow_worst_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(status: str) -> object:
        return lambda ident: vc.Result(status, ident)

    monkeypatch.setattr(vc, "check_doi", fake("OK"))
    assert vc.main(["--doi", "10.1/x"]) == _EXIT_OK
    monkeypatch.setattr(vc, "check_doi", fake("ERROR"))
    assert vc.main(["--doi", "10.1/x"]) == _EXIT_INCONCLUSIVE
    monkeypatch.setattr(vc, "check_doi", fake("NOT_FOUND"))
    assert vc.main(["--doi", "10.1/x"]) == _EXIT_FAIL
