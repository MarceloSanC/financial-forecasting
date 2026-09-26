"""Verifica mecanicamente se citações existem e batem com os metadados oficiais.

Uso (stdlib only — roda no host sem venv):
    python scripts/verify_citations.py docs/adr/0_0_0009-*.md
    python scripts/verify_citations.py --doi 10.1038/s41598-023-41032-5
    python scripts/verify_citations.py --arxiv 2309.11495
    python scripts/verify_citations.py --title "Specification curve analysis" --year 2020

Extrai DOIs e ids arXiv dos arquivos e consulta Crossref / arXiv; `--title` busca por
título na Crossref (para livros e papers sem DOI no texto). Saída: uma linha TSV por
citação `STATUS  id  ano  primeiro-autor  título`. Exit 1 se alguma for NOT_FOUND ou
MISMATCH; exit 2 se a rede falhou (resultado inconclusivo, não aprovado).

Não prova que o trecho citado sustenta a afirmação — isso é o verificador adversarial
da skill `evidence-resolution`. Prova só que a fonte existe e é a que se diz ser.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>()\[\]{},;`|]+")
_ARXIV_RE = re.compile(r"(?:arXiv[:\s]\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})", re.IGNORECASE)
_USER_AGENT = "financial-forecasting-citation-check/1.0"
_TIMEOUT_S = 20
_TITLE_MATCH_MIN = 0.90
_HTTP_NOT_FOUND = 404
_HTTP_RETRYABLE = (429, 503)


@dataclass(frozen=True)
class Result:
    status: str  # OK | NOT_FOUND | MISMATCH | ERROR
    ident: str
    year: str = ""
    author: str = ""
    title: str = ""

    def line(self) -> str:
        return "\t".join((self.status, self.ident, self.year, self.author, self.title))


def extract_dois(text: str) -> list[str]:
    found = (m.group(0).rstrip(".") for m in _DOI_RE.finditer(text))
    return list(dict.fromkeys(found))


def extract_arxiv_ids(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _ARXIV_RE.finditer(text)))


def title_similarity(a: str, b: str) -> float:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def _get(url: str, retries: int = 2) -> bytes:
    """GET com retry curto: arXiv pede ~3 s entre chamadas e responde 429/503 sob carga."""
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                body: bytes = resp.read()
                return body
        except urllib.error.HTTPError as exc:
            if exc.code not in _HTTP_RETRYABLE or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(3 * (attempt + 1))
    raise AssertionError("unreachable")


def _crossref_fields(item: dict[str, object]) -> tuple[str, str, str]:
    titles = item.get("title") or [""]
    title = str(titles[0]) if isinstance(titles, list) and titles else ""
    authors = item.get("author") or []
    author = ""
    if isinstance(authors, list) and authors and isinstance(authors[0], dict):
        author = str(authors[0].get("family") or authors[0].get("name") or "")
    year = ""
    for key in ("published-print", "published-online", "issued"):
        parts = item.get(key)
        if isinstance(parts, dict) and parts.get("date-parts"):
            year = str(parts["date-parts"][0][0])
            break
    return year, author, title


def check_doi(doi: str) -> Result:
    try:
        data = json.loads(_get("https://api.crossref.org/works/" + urllib.parse.quote(doi)))
    except urllib.error.HTTPError as exc:
        return Result("NOT_FOUND" if exc.code == _HTTP_NOT_FOUND else "ERROR", doi)
    except (urllib.error.URLError, TimeoutError):
        return Result("ERROR", doi)
    return Result("OK", doi, *_crossref_fields(data["message"]))


def check_arxiv(arxiv_id: str) -> Result:
    url = "https://export.arxiv.org/api/query?id_list=" + urllib.parse.quote(arxiv_id)
    try:
        root = ET.fromstring(_get(url))
    except (urllib.error.URLError, TimeoutError, ET.ParseError):
        return Result("ERROR", "arXiv:" + arxiv_id)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = root.find("a:entry", ns)
    title = entry.findtext("a:title", "", ns) if entry is not None else ""
    if entry is None or not title or entry.findtext("a:id", "", ns).endswith("/api/errors"):
        return Result("NOT_FOUND", "arXiv:" + arxiv_id)
    author = entry.findtext("a:author/a:name", "", ns).split(" ")[-1]
    year = entry.findtext("a:published", "", ns)[:4]
    return Result("OK", "arXiv:" + arxiv_id, year, author, " ".join(title.split()))


def check_title(title: str, year: str | None) -> Result:
    query = {"query.bibliographic": title, "rows": "5"}
    try:
        data = json.loads(_get("https://api.crossref.org/works?" + urllib.parse.urlencode(query)))
    except (urllib.error.URLError, TimeoutError):
        return Result("ERROR", title)
    best: tuple[float, dict[str, object]] | None = None
    for item in data["message"]["items"]:
        score = title_similarity(title, _crossref_fields(item)[2])
        if best is None or score > best[0]:
            best = (score, item)
    if best is None or best[0] < _TITLE_MATCH_MIN:
        return Result("NOT_FOUND", title)
    item_year, author, found_title = _crossref_fields(best[1])
    status = "MISMATCH" if year and item_year and item_year != year else "OK"
    return Result(status, str(best[1].get("DOI", title)), item_year, author, found_title)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--doi", action="append", default=[])
    parser.add_argument("--arxiv", action="append", default=[])
    parser.add_argument("--title", action="append", default=[])
    parser.add_argument("--year", help="ano esperado (só com um --title)")
    args = parser.parse_args(argv)

    dois, arxiv_ids = list(args.doi), list(args.arxiv)
    for path in args.files:
        text = path.read_text(encoding="utf-8")
        dois += extract_dois(text)
        arxiv_ids += extract_arxiv_ids(text)

    results = [check_doi(d) for d in dict.fromkeys(dois)]
    results += [check_arxiv(a) for a in dict.fromkeys(arxiv_ids)]
    results += [check_title(t, args.year if len(args.title) == 1 else None) for t in args.title]
    if not results:
        print("nenhuma citação verificável (DOI/arXiv/--title) encontrada", file=sys.stderr)
        return 1

    for r in results:
        print(r.line())
    statuses = {r.status for r in results}
    if statuses & {"NOT_FOUND", "MISMATCH"}:
        return 1
    return 2 if "ERROR" in statuses else 0


if __name__ == "__main__":
    sys.exit(main())
