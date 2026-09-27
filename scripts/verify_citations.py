"""Verifica mecanicamente se citações existem e batem com os metadados oficiais.

Uso (stdlib only — roda no host sem venv):
    python scripts/verify_citations.py docs/adr/0_0_0009-*.md
    python scripts/verify_citations.py --doi 10.1038/s41598-023-41032-5
    python scripts/verify_citations.py --arxiv 2309.11495
    python scripts/verify_citations.py --title "Specification curve analysis" --year 2020

Extrai DOIs e ids arXiv dos arquivos e consulta Crossref / DataCite (arXiv); `--title` busca por
título na Crossref (para livros e papers sem DOI no texto). Saída: uma linha TSV por
citação `STATUS  id  ano  primeiro-autor  título`. Exit 1 se alguma for NOT_FOUND ou
MISMATCH; exit 2 se a rede falhou (resultado inconclusivo, não aprovado).

Não prova que o trecho citado sustenta a afirmação — isso é o verificador adversarial
da skill `evidence-resolution`. Prova só que a fonte existe e é a que se diz ser.
"""

from __future__ import annotations

import argparse
import contextlib
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

# Parênteses entram (Elsevier: 10.1016/S0169-2070(96)00719-4); o `)` final desbalanceado sai.
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"'<>\[\]{},;`|]+")
_ARXIV_RE = re.compile(r"(?:arXiv[:\s]\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})", re.IGNORECASE)
_USER_AGENT = "financial-forecasting-citation-check/1.0"
_TIMEOUT_S = 20
_TITLE_MATCH_MIN = 0.90
_HTTP_NOT_FOUND = 404
_HTTP_RETRYABLE = (406, 429, 503)  # arXiv limita taxa com 406 (fora do padrão)
_ARXIV_BATCH = 20
_ARXIV_PAUSE_S = 3  # termos da API do arXiv: no máximo 1 requisição a cada 3 s


@dataclass(frozen=True)
class Result:
    status: str  # OK | NOT_FOUND | MISMATCH | ERROR
    ident: str
    year: str = ""
    author: str = ""
    title: str = ""

    def line(self) -> str:
        return "\t".join((self.status, self.ident, self.year, self.author, self.title))


def _clean_doi(raw: str) -> str:
    doi = raw
    while doi and (doi[-1] in ".:" or (doi[-1] == ")" and doi.count(")") > doi.count("("))):
        doi = doi[:-1]
    return doi


def extract_dois(text: str) -> list[str]:
    return list(dict.fromkeys(_clean_doi(m.group(0)) for m in _DOI_RE.finditer(text)))


def extract_arxiv_ids(text: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in _ARXIV_RE.finditer(text)))


def title_similarity(a: str, b: str) -> float:
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def _get(url: str, retries: int = 3) -> bytes:
    """GET com retry curto para limitação de taxa (406/429/503) e falha de rede."""
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
        time.sleep(5 * 3**attempt)  # 5, 15, 45 s: a janela de limitação do arXiv dura dezenas de s
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


def parse_arxiv_feed(feed: bytes, ids: list[str]) -> list[Result]:
    """Resultados na ordem de `ids`; id ausente do feed = NOT_FOUND."""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    found: dict[str, Result] = {}
    for entry in ET.fromstring(feed).findall("a:entry", ns):
        match = re.search(r"abs/(\d{4}\.\d{4,5})", entry.findtext("a:id", "", ns))
        title = " ".join(entry.findtext("a:title", "", ns).split())
        if match and title:
            author = entry.findtext("a:author/a:name", "", ns).split(" ")[-1]
            year = entry.findtext("a:published", "", ns)[:4]
            found[match.group(1)] = Result("OK", "arXiv:" + match.group(1), year, author, title)
    return [found.get(i, Result("NOT_FOUND", "arXiv:" + i)) for i in ids]


def _check_arxiv_datacite(arxiv_id: str) -> Result:
    """Todo paper do arXiv tem DOI DataCite 10.48550/arXiv.<id>; outra infraestrutura, sem o
    limite de taxa agressivo da API do arXiv (que responde 406 sob rajada)."""
    ident = "arXiv:" + arxiv_id
    try:
        raw = _get("https://api.datacite.org/dois/10.48550/arXiv." + urllib.parse.quote(arxiv_id))
    except urllib.error.HTTPError as exc:
        return Result("NOT_FOUND" if exc.code == _HTTP_NOT_FOUND else "ERROR", ident)
    except (urllib.error.URLError, TimeoutError):
        return Result("ERROR", ident)
    try:
        attrs = json.loads(raw)["data"]["attributes"]
    except (ValueError, KeyError, TypeError):
        return Result("ERROR", ident)  # payload inesperado → cai na reserva (API do arXiv)
    titles = attrs.get("titles") or [{}]
    creators = attrs.get("creators") or [{}]
    author = str(creators[0].get("familyName") or creators[0].get("name") or "")
    title = " ".join(str(titles[0].get("title", "")).split())
    return Result("OK", ident, str(attrs.get("publicationYear") or ""), author, title)


def check_arxiv(ids: list[str]) -> list[Result]:
    """DataCite por id; a API do arXiv (lote, com pausa) só para o que o DataCite não respondeu."""
    results = {i: _check_arxiv_datacite(i) for i in ids}
    retry = [i for i, r in results.items() if r.status == "ERROR"]
    for start in range(0, len(retry), _ARXIV_BATCH):
        chunk = retry[start : start + _ARXIV_BATCH]
        time.sleep(_ARXIV_PAUSE_S)
        ids_param = ",".join(urllib.parse.quote(i) for i in chunk)
        try:
            feed = _get(
                f"https://export.arxiv.org/api/query?id_list={ids_param}&max_results={len(chunk)}"
            )
        except (urllib.error.URLError, TimeoutError):
            continue
        with contextlib.suppress(ET.ParseError):
            results.update(
                {r.ident.removeprefix("arXiv:"): r for r in parse_arxiv_feed(feed, chunk)}
            )
    return [results[i] for i in ids]


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
    results += check_arxiv(list(dict.fromkeys(arxiv_ids)))
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
