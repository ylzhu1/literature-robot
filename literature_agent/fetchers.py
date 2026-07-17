from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional

from .models import LiteratureItem

ACCEPT_HEADER = "application/json, application/atom+xml, application/rss+xml, text/xml, */*"

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def _request_text(url: str, user_agent: str = "LiteratureAgent/0.1", timeout: int = 30) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": ACCEPT_HEADER,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError:
        raise
    except Exception as exc:
        return _request_text_with_curl(url, user_agent=user_agent, timeout=timeout, first_error=exc)


def _request_text_with_curl(
    url: str,
    user_agent: str,
    timeout: int,
    first_error: Exception,
) -> str:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise first_error

    completed = subprocess.run(
        [
            curl,
            "--location",
            "--silent",
            "--show-error",
            "--fail",
            "--max-time",
            str(timeout),
            "--user-agent",
            user_agent,
            "--header",
            f"Accept: {ACCEPT_HEADER}",
            url,
        ],
        capture_output=True,
        timeout=timeout + 10,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"urllib request failed ({first_error}); curl fallback failed: "
            f"{detail or f'exit code {completed.returncode}'}"
        ) from first_error
    return completed.stdout.decode("utf-8", errors="replace")


def _request_text_with_retries(
    url: str,
    user_agent: str = "LiteratureAgent/0.1",
    timeout: int = 30,
    attempts: int = 3,
) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return _request_text(url, user_agent=user_agent, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 or attempt == attempts - 1:
                raise
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 2 * (attempt + 1)
            time.sleep(delay)
        except Exception as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError(f"request failed: {last_error}")


def _clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_dt(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _abstract_from_inverted_index(index: Optional[Dict[str, List[int]]]) -> str:
    if not index:
        return ""
    positioned = []
    for word, positions in index.items():
        for position in positions:
            positioned.append((position, word))
    positioned.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positioned)


def _date_parts_to_datetime(date_parts: Any) -> Optional[datetime]:
    if not date_parts:
        return None
    try:
        parts = date_parts[0]
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return datetime(year, month, day, tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_arxiv(config: Dict[str, Any], since: datetime) -> List[LiteratureItem]:
    source_config = config["sources"].get("arxiv", {})
    if not source_config.get("enabled", False):
        return []

    categories = source_config.get("categories", [])
    query_terms = source_config.get("query_terms", [])
    max_results = int(source_config.get("max_results_per_query", 20))
    items: List[LiteratureItem] = []

    category_clause = " OR ".join(f"cat:{category}" for category in categories)
    for term in query_terms:
        words = [part.strip() for part in term.split() if part.strip()]
        all_clause = " AND ".join(f'all:"{word}"' for word in words)
        search_query = all_clause
        if category_clause:
            search_query = f"({category_clause}) AND ({all_clause})"

        params = urllib.parse.urlencode(
            {
                "search_query": search_query,
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        url = f"https://export.arxiv.org/api/query?{params}"
        try:
            xml_text = _request_text(url, user_agent="LiteratureAgent/0.1 (arxiv fetcher)")
        except Exception as exc:
            print(f"[warn] arXiv fetch failed for query '{term}': {exc}")
            continue

        root = ET.fromstring(xml_text)
        for entry in root.findall("atom:entry", ATOM_NS):
            uid = _clean_text(entry.findtext("atom:id", default="", namespaces=ATOM_NS))
            title = _clean_text(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
            abstract = _clean_text(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
            published = _parse_dt(entry.findtext("atom:published", default="", namespaces=ATOM_NS))
            doi = _clean_text(entry.findtext("arxiv:doi", default="", namespaces=ARXIV_NS))
            if published and published.replace(tzinfo=timezone.utc) < since:
                continue
            authors = [
                _clean_text(author.findtext("atom:name", default="", namespaces=ATOM_NS))
                for author in entry.findall("atom:author", ATOM_NS)
            ]
            items.append(
                LiteratureItem(
                    uid=uid or title,
                    title=title,
                    abstract=abstract,
                    url=uid,
                    source="arXiv",
                    published=published,
                    authors=[author for author in authors if author],
                    venue="arXiv",
                    doi=doi,
                )
            )
        time.sleep(1.0)

    return items


def fetch_openalex(config: Dict[str, Any], since: datetime) -> List[LiteratureItem]:
    source_config = config["sources"].get("openalex", {})
    if not source_config.get("enabled", False):
        return []

    query_terms = source_config.get("query_terms", [])
    max_results = int(source_config.get("max_results_per_query", 25))
    mailto = source_config.get("mailto", "")
    items: List[LiteratureItem] = []
    from_date = since.date().isoformat()

    for term in query_terms:
        params = {
            "search": term,
            "filter": f"from_publication_date:{from_date},type:article",
            "sort": "publication_date:desc",
            "per-page": max_results,
        }
        if mailto and "@" in mailto:
            params["mailto"] = mailto
        url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
        try:
            payload = json.loads(
                _request_text_with_retries(url, user_agent="LiteratureAgent/0.1 (OpenAlex fetcher)")
            )
        except Exception as exc:
            print(f"[warn] OpenAlex fetch failed for query '{term}': {exc}")
            continue

        for work in payload.get("results", []):
            title = _clean_text(work.get("title") or work.get("display_name") or "")
            abstract = _clean_text(_abstract_from_inverted_index(work.get("abstract_inverted_index")))
            published = _parse_dt(work.get("publication_date", ""))
            if published and published.replace(tzinfo=timezone.utc) < since:
                continue
            ids = work.get("ids") or {}
            doi = (ids.get("doi") or "").replace("https://doi.org/", "")
            url_value = ids.get("doi") or work.get("id") or ""
            authors = []
            for authorship in work.get("authorships", [])[:8]:
                author = authorship.get("author", {})
                name = author.get("display_name")
                if name:
                    authors.append(name)
            venue = ""
            primary_location = work.get("primary_location") or {}
            source = primary_location.get("source") or {}
            if source:
                venue = source.get("display_name") or ""
            items.append(
                LiteratureItem(
                    uid=doi or work.get("id") or title,
                    title=title,
                    abstract=abstract,
                    url=url_value,
                    source="OpenAlex",
                    published=published,
                    authors=authors,
                    venue=venue,
                    doi=doi,
                )
            )
        time.sleep(1.2)

    return items


def fetch_crossref(config: Dict[str, Any], since: datetime) -> List[LiteratureItem]:
    source_config = config["sources"].get("crossref", {})
    if not source_config.get("enabled", False):
        return []

    query_terms = source_config.get("query_terms", [])
    max_results = int(source_config.get("max_results_per_query", 12))
    mailto = source_config.get("mailto", "")
    items: List[LiteratureItem] = []
    start_date = since.date().isoformat()
    end_date = datetime.now(timezone.utc).date().isoformat()

    for term in query_terms:
        params = {
            "query.bibliographic": term,
            "filter": f"from-pub-date:{start_date},until-pub-date:{end_date},type:journal-article",
            "rows": max_results,
            "select": "DOI,title,abstract,author,container-title,issued,published-online,URL",
        }
        if mailto and "@" in mailto:
            params["mailto"] = mailto
        url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
        try:
            payload = json.loads(
                _request_text_with_retries(url, user_agent="LiteratureAgent/0.1 (Crossref fetcher)")
            )
        except Exception as exc:
            print(f"[warn] Crossref fetch failed for query '{term}': {exc}")
            continue

        for work in payload.get("message", {}).get("items", []):
            title_list = work.get("title") or []
            title = _clean_text(title_list[0] if title_list else "")
            abstract = _clean_text(work.get("abstract", ""))
            issued = _date_parts_to_datetime((work.get("issued") or {}).get("date-parts"))
            published_online = _date_parts_to_datetime((work.get("published-online") or {}).get("date-parts"))
            published = published_online or issued
            if published and published.replace(tzinfo=timezone.utc) < since:
                continue
            doi = _clean_text(work.get("DOI", ""))
            authors = []
            for author in work.get("author", [])[:8]:
                given = author.get("given", "").strip()
                family = author.get("family", "").strip()
                name = " ".join(part for part in [given, family] if part).strip()
                if name:
                    authors.append(name)
            venue_list = work.get("container-title") or []
            venue = _clean_text(venue_list[0] if venue_list else "")
            url_value = work.get("URL") or (f"https://doi.org/{doi}" if doi else "")
            items.append(
                LiteratureItem(
                    uid=doi or url_value or title,
                    title=title,
                    abstract=abstract,
                    url=url_value,
                    source="Crossref",
                    published=published,
                    authors=authors,
                    venue=venue,
                    doi=doi,
                    raw=work,
                )
            )
        time.sleep(0.2)

    return items


def fetch_rss(config: Dict[str, Any], since: datetime) -> List[LiteratureItem]:
    source_config = config["sources"].get("rss", {})
    if not source_config.get("enabled", False):
        return []

    items: List[LiteratureItem] = []
    for feed in source_config.get("feeds", []):
        name = feed.get("name", "RSS")
        url = feed.get("url", "")
        if not url:
            continue
        try:
            xml_text = _request_text(url, user_agent="LiteratureAgent/0.1 (RSS fetcher)")
        except Exception as exc:
            print(f"[warn] RSS fetch failed for '{name}': {exc}")
            continue
        root = ET.fromstring(xml_text)
        channel_items = root.findall(".//item")
        if not channel_items:
            channel_items = root.findall("atom:entry", ATOM_NS)

        for node in channel_items:
            title = _clean_text(node.findtext("title", default="") or node.findtext("atom:title", default="", namespaces=ATOM_NS))
            link = _clean_text(node.findtext("link", default="") or node.findtext("atom:id", default="", namespaces=ATOM_NS))
            if not link:
                link_node = node.find("atom:link", ATOM_NS)
                if link_node is not None:
                    link = link_node.attrib.get("href", "")
            abstract = _clean_text(
                node.findtext("description", default="")
                or node.findtext("summary", default="")
                or node.findtext("atom:summary", default="", namespaces=ATOM_NS)
            )
            published = _parse_dt(
                node.findtext("pubDate", default="")
                or node.findtext("published", default="")
                or node.findtext("atom:published", default="", namespaces=ATOM_NS)
            )
            if published and published.replace(tzinfo=timezone.utc) < since:
                continue
            items.append(
                LiteratureItem(
                    uid=link or f"{name}:{title}",
                    title=title,
                    abstract=abstract,
                    url=link,
                    source=name,
                    published=published,
                    venue=name,
                )
            )
    return items


def fetch_all(config: Dict[str, Any]) -> List[LiteratureItem]:
    lookback_days = int(config.get("lookback_days", 7))
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    items: List[LiteratureItem] = []
    for fetcher in (fetch_arxiv, fetch_crossref, fetch_openalex, fetch_rss):
        items.extend(fetcher(config, since))
    return items


def sample_items() -> List[LiteratureItem]:
    now = datetime.now(timezone.utc)
    return [
        LiteratureItem(
            uid="sample:cu-oxidation-mlp",
            title="[DEMO] Machine learning potential accelerated simulation of copper surface oxidation",
            abstract=(
                "A machine learning force field is trained with DFT data to simulate oxygen adsorption, "
                "oxide nucleation, and oxide growth on Cu(111), Cu(100), and stepped copper surfaces. "
                "The model reveals that step edges lower the oxygen dissociation barrier and promote "
                "subsurface oxygen incorporation."
            ),
            url="https://example.com/cu-oxidation-mlp",
            source="Sample",
            published=now,
            authors=["A. Researcher", "B. Scientist"],
            venue="Example Journal",
        ),
        LiteratureItem(
            uid="sample:operando-xps-pt",
            title="[DEMO] Operando AP-XPS study of oxygen adsorption on platinum stepped surfaces",
            abstract=(
                "Ambient pressure XPS and DFT calculations are combined to identify coverage-dependent "
                "oxygen species on Pt(111) and high-index stepped surfaces under oxidizing conditions."
            ),
            url="https://example.com/pt-apxps",
            source="Sample",
            published=now,
            authors=["C. Author"],
            venue="Surface Science Letters",
        ),
    ]
