# ============================================================
#  parsers/cyberleninka.py — парсер КиберЛенинки
#  API + fallback через веб-поиск
# ============================================================

import requests
import logging
import time
import re
import urllib3
from parsers.base import BaseParser, RawArticle

# Подавляем предупреждения о SSL (только для CyberLeninka fallback)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

API_URL = "https://cyberleninka.ru/api/search"
WEB_URL = "https://cyberleninka.ru/search"

QUERIES = [
    "нейропластичность",
    "когнитивная психология",
    "стресс и мозг",
    "СДВГ нейронаука",
    "тревожность нейробиология",
    "сон и память",
    "дофамин мотивация",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Referer": "https://cyberleninka.ru/",
}


class CyberLeninaParser(BaseParser):
    source_name = "cyberleninka"

    def fetch(self) -> list[RawArticle]:
        articles = []
        seen = set()

        for query in QUERIES:
            # Сначала пробуем API
            found = self._fetch_via_api(query, seen)
            if not found:
                # Fallback: веб-поиск
                found = self._fetch_via_web(query, seen)

            articles.extend(found)
            time.sleep(1)

        if articles:
            logger.info(f"CyberLeninka: найдено {len(articles)} статей")
        else:
            logger.warning("CyberLeninka: 0 статей (API и web недоступны)")

        return articles

    def _fetch_via_api(self, query: str, seen: set) -> list[RawArticle]:
        """Поиск через API."""
        api_headers = {**HEADERS, "Content-Type": "application/json", "Accept": "application/json"}
        for attempt in range(2):
            try:
                resp = requests.post(
                    API_URL,
                    json={"mode": "articles", "q": query, "size": 5, "from": 0},
                    headers=api_headers,
                    timeout=15,
                    verify=False,  # CyberLeninka имеет проблемы с SSL
                )
                if resp.status_code in (500, 502, 503):
                    logger.debug(f"CyberLeninka API {resp.status_code} ({query})")
                    break
                if resp.status_code == 429:
                    logger.warning(f"CyberLeninka rate limited ({query})")
                    time.sleep(3)
                    continue
                resp.raise_for_status()
                data = resp.json()

                results = []
                for hit in data.get("hits", []):
                    url = f"https://cyberleninka.ru/article/n/{hit.get('id', '')}"
                    if url in seen:
                        continue
                    seen.add(url)
                    results.append(RawArticle(
                        title=hit.get("name", "").strip(),
                        url=url,
                        abstract=hit.get("annotation", "").strip(),
                        source="cyberleninka",
                        external_id=str(hit.get("id", "")),
                        is_peer_reviewed=True,
                    ))
                return results
            except Exception as e:
                if attempt == 0:
                    logger.debug(f"CyberLeninka API retry ({query}): {e}")
                    time.sleep(2)
                else:
                    logger.debug(f"CyberLeninka API error ({query}): {e}")
        return []

    def _fetch_via_web(self, query: str, seen: set) -> list[RawArticle]:
        """Fallback: парсинг HTML страницы поиска."""
        try:
            resp = requests.get(
                WEB_URL,
                params={"q": query},
                headers=HEADERS,
                timeout=15,
                verify=False,  # CyberLeninka имеет проблемы с SSL
            )
            if resp.status_code != 200:
                logger.debug(f"CyberLeninka web {resp.status_code} ({query})")
                return []

            results = []
            # Ищем ссылки на статьи: /article/n/xxxxx
            article_links = re.findall(
                r'href="/article/n/([^"]+)"',
                resp.text,
            )
            # Ищем заголовки
            titles = re.findall(
                r'<h[23][^>]*>(.*?)</h[23]>',
                resp.text,
                re.DOTALL,
            )
            # Ищем аннотации
            abstracts = re.findall(
                r'<div[^>]*class="[^"]*abstract[^"]*"[^>]*>(.*?)</div>',
                resp.text,
                re.DOTALL,
            )

            for i, article_id in enumerate(article_links[:5]):
                url = f"https://cyberleninka.ru/article/n/{article_id}"
                if url in seen:
                    continue
                seen.add(url)

                title = ""
                if i < len(titles):
                    title = re.sub(r'<[^>]+>', '', titles[i]).strip()
                abstract = ""
                if i < len(abstracts):
                    abstract = re.sub(r'<[^>]+>', '', abstracts[i]).strip()

                if title:
                    results.append(RawArticle(
                        title=title,
                        url=url,
                        abstract=abstract,
                        source="cyberleninka",
                        external_id=article_id,
                        is_peer_reviewed=True,
                    ))

            if results:
                logger.info(f"CyberLeninka web fallback found {len(results)} articles ({query})")
            return results
        except Exception as e:
            logger.debug(f"CyberLeninka web error ({query}): {e}")
            return []
