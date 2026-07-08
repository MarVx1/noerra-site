# ============================================================
#  parsers/pubmed.py — парсер PubMed через официальное API
#  Не требует API-ключа (до 3 запросов/сек)
# ============================================================

import requests
import logging
from xml.etree import ElementTree as ET
from parsers.base import BaseParser, RawArticle
from config.settings import PUBMED_MAX_RESULTS

logger = logging.getLogger(__name__)

SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
FETCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

QUERIES = [
    "ADHD neuroscience",
    "dopamine reward brain",
    "sleep cognition",
    "stress cortisol brain",
    "anxiety amygdala",
    "neuroplasticity learning",
    "cognitive neuroscience",
    "mental health psychology",
]


class PubMedParser(BaseParser):
    source_name = "pubmed"

    def fetch(self) -> list[RawArticle]:
        articles = []
        seen_ids = set()

        for query in QUERIES:
            ids = self._search(query)
            new_ids = [i for i in ids if i not in seen_ids]
            seen_ids.update(new_ids)
            if new_ids:
                articles += self._fetch_details(new_ids)

        return articles

    def _search(self, query: str) -> list[str]:
        """Возвращает PubMed ID по запросу с retry."""
        for attempt in range(2):
            try:
                resp = requests.get(SEARCH_URL, params={
                    "db":      "pubmed",
                    "term":    query,
                    "retmax":  PUBMED_MAX_RESULTS,
                    "retmode": "json",
                    "sort":    "date",
                }, timeout=25)
                resp.raise_for_status()
                return resp.json()["esearchresult"]["idlist"]
            except requests.Timeout:
                if attempt == 0:
                    logger.warning(f"PubMed timeout ({query}), retrying...")
                    import time
                    time.sleep(2)
                else:
                    logger.error(f"PubMed search timeout after retry ({query})")
            except Exception as e:
                logger.error(f"PubMed search error ({query}): {e}")
                return []
        return []

    def _fetch_details(self, pmids: list[str]) -> list[RawArticle]:
        """Загружает детали статей с retry."""
        for attempt in range(2):
            try:
                resp = requests.get(FETCH_URL, params={
                    "db":      "pubmed",
                    "id":      ",".join(pmids),
                    "rettype": "abstract",
                    "retmode": "xml",
                }, timeout=30)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                break
            except requests.Timeout:
                if attempt == 0:
                    logger.warning(f"PubMed fetch timeout for {len(pmids)} IDs, retrying...")
                    import time
                    time.sleep(3)
                else:
                    logger.error(f"PubMed fetch timeout after retry")
                    return []
            except Exception as e:
                logger.error(f"PubMed fetch error: {e}")
                return []
        else:
            return []

        articles = []
        for article_el in root.findall(".//PubmedArticle"):
            try:
                pmid    = article_el.findtext(".//PMID", "")
                title   = article_el.findtext(".//ArticleTitle", "").strip()
                abstract = " ".join(
                    t.text or "" for t in article_el.findall(".//AbstractText")
                ).strip()

                authors = [
                    f"{a.findtext('LastName', '')} {a.findtext('ForeName', '')}".strip()
                    for a in article_el.findall(".//Author")[:3]
                ]

                pub_year  = article_el.findtext(".//PubDate/Year", "")
                pub_month = article_el.findtext(".//PubDate/Month", "")

                if not title or not pmid:
                    continue

                articles.append(RawArticle(
                    title=title,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    abstract=abstract,
                    source="pubmed",
                    external_id=pmid,
                    authors=authors,
                    published=f"{pub_year} {pub_month}".strip(),
                    is_peer_reviewed=True,
                ))
            except Exception as e:
                logger.warning(f"PubMed parse error for one article: {e}")

        return articles
