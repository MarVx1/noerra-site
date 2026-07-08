# ============================================================
#  parsers/youtube.py — парсер YouTube подкастов
#  Ищет видео по теме, извлекает субтитры, находит тайминги
#  Библиотека: youtube-transcript-api (бесплатно, без ключа)
# ============================================================

import re
import logging
import requests
from parsers.base import BaseParser, RawArticle
from adaptation.editorial_engine import EditorialEngine

logger = logging.getLogger(__name__)

# Whitelist каналов из документа Noerra (проверенные актуальные ID)
YOUTUBE_CHANNELS = {
    "huberman":  "UC2D2CMWXMOVWx7giW1n3LIg",   # Huberman Lab (Andrew Huberman)
    "stanford":  "UC-EnprmCZ3OXyAoG7vjVNCA",   # Stanford
    "mit":       "UCEBb1b_L6zDS3xTUrIALZOw",   # MIT OpenCourseWare
    "lex":       "UCSHZKyawb77ixDdsGog4iWA",   # Lex Fridman
}

# Запросы по темам для поиска видео
YOUTUBE_QUERIES = {
    "neuroscience":     "neuroscience brain research podcast",
    "ADHD":             "ADHD brain neuroscience",
    "sleep":            "sleep science brain podcast",
    "neuroplasticity":  "neuroplasticity learning brain",
    "dopamine":         "dopamine reward motivation science",
    "anxiety":          "anxiety brain neuroscience",
    "cognition":        "cognitive science memory learning",
    "psychology":       "psychology research podcast",
    "stress":           "stress cortisol brain science",
}

# Ключевые слова для поиска таймингов в субтитрах
TOPIC_TRANSCRIPT_KEYWORDS = {
    "neuroscience":    ["neuroscience", "brain", "neural", "cortex"],
    "ADHD":            ["adhd", "attention deficit", "hyperactivity", "focus"],
    "sleep":           ["sleep", "circadian", "rem", "melatonin"],
    "neuroplasticity": ["neuroplasticity", "plasticity", "synapse", "learning"],
    "dopamine":        ["dopamine", "reward", "motivation", "nucleus accumbens"],
    "anxiety":         ["anxiety", "amygdala", "fear", "stress response"],
    "cognition":       ["cognition", "memory", "attention", "decision"],
    "psychology":      ["psychology", "behavior", "mental", "therapy"],
    "stress":          ["stress", "cortisol", "burnout", "resilience"],
}


class YouTubeParser(BaseParser):
    source_name = "youtube"

    def fetch(self) -> list[RawArticle]:
        articles = []
        seen_videos = set()

        # Берём RSS каждого канала ОДИН раз, потом проверяем все темы
        for channel_name, channel_id in YOUTUBE_CHANNELS.items():
            channel_videos = self._fetch_channel_rss(channel_name, channel_id)
            for video in channel_videos:
                if video["video_id"] in seen_videos:
                    continue
                seen_videos.add(video["video_id"])

                # Определяем тему видео по заголовку
                topic = self._match_topic(video["title"])
                if not topic:
                    continue

                # Пытаемся получить тайминг из субтитров
                timestamp, excerpt = self._find_timestamp(video["video_id"], TOPIC_TRANSCRIPT_KEYWORDS.get(topic, []))

                # Если субтитров нет — всё равно берём видео, используем описание из RSS
                if timestamp is None:
                    excerpt = video.get("description", "")[:300]
                    url = f"https://youtu.be/{video['video_id']}"
                else:
                    url = f"https://youtu.be/{video['video_id']}?t={timestamp}"

                if not excerpt:
                    excerpt = video["title"]

                articles.append(RawArticle(
                    title=f"{video['title']} [{channel_name.capitalize()}]",
                    url=url,
                    abstract=excerpt,
                    source="youtube",
                    external_id=f"{video['video_id']}_{timestamp or 0}",
                    is_peer_reviewed=False,
                ))

        logger.info(f"YouTube: найдено {len(articles)} видео из {len(YOUTUBE_CHANNELS)} каналов")
        return articles

    def _fetch_channel_rss(self, channel_name: str, channel_id: str) -> list[dict]:
        """Получает последние видео канала через RSS."""
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            resp = requests.get(rss_url, timeout=10)
            if resp.status_code != 200:
                logger.debug(f"YouTube RSS status {resp.status_code} for {channel_name}")
                return []

            entries = re.findall(r'<entry>(.*?)</entry>', resp.text, re.DOTALL)
            videos = []
            for entry in entries[:10]:  # последние 10 видео
                video_id = re.search(r'<yt:videoId>(.*?)</yt:videoId>', entry)
                title_m  = re.search(r'<title>(.*?)</title>', entry)
                if not video_id or not title_m:
                    continue

                # Описание из RSS
                desc_m = re.search(r'<media:description>(.*?)</media:description>', entry, re.DOTALL)
                description = desc_m.group(1).strip() if desc_m else ""

                videos.append({
                    "video_id": video_id.group(1).strip(),
                    "title": title_m.group(1).strip(),
                    "description": description,
                })
            return videos
        except Exception as e:
            logger.warning(f"YouTube RSS error ({channel_name}): {e}")
            return []

    def _match_topic(self, title: str) -> str | None:
        """Определяет тему видео по ключевым словам в заголовке."""
        title_lower = title.lower()
        for topic, keywords in TOPIC_TRANSCRIPT_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                return topic
        return None

    def _find_timestamp(
        self, video_id: str, keywords: list[str]
    ) -> tuple[int | None, str]:
        """
        Скачивает субтитры и ищет первое вхождение ключевых слов.
        Возвращает (секунды, текст отрывка) или (None, "").
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            transcript = self._fetch_transcript(video_id)
            if transcript is None:
                return None, ""

            # Объединяем соседние фрагменты для контекста
            for i, segment in enumerate(transcript):
                if any(kw in segment["text"].lower() for kw in keywords):
                    start = max(0, i - 1)
                    end   = min(len(transcript), i + 4)
                    excerpt = " ".join(s["text"] for s in transcript[start:end])
                    timestamp = int(segment["start"])
                    return timestamp, excerpt.strip()

        except ImportError:
            logger.warning("youtube-transcript-api не установлен: pip install youtube-transcript-api")
        except Exception as e:
            logger.warning(f"Субтитры недоступны для {video_id}: {e}")

        return None, ""

    def _fetch_transcript(self, video_id: str) -> list[dict] | None:
        """
        Совместимость со старой и новой версией youtube-transcript-api.
        Новая версия (1.0+): нужен экземпляр класса и метод .fetch()
        Старая версия: статический метод .get_transcript()
        Возвращает список словарей {'text', 'start', 'duration'} или None.
        """
        from youtube_transcript_api import YouTubeTranscriptApi

        # ── Новый API (v1.0+): YouTubeTranscriptApi().fetch(video_id) ──
        try:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=["en", "ru"])
            return [
                {"text": s.text, "start": s.start, "duration": s.duration}
                for s in fetched
            ]
        except AttributeError:
            pass  # старая версия — падаем на следующий вариант
        except Exception as e:
            logger.debug(f"Новый API транскрипта не подошёл для {video_id}: {e}")
            return None

        # ── Старый API (< 1.0): статический метод get_transcript ──
        try:
            return YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "ru"])
        except Exception as e:
            logger.debug(f"Старый API транскрипта тоже не сработал для {video_id}: {e}")
            return None


def format_youtube_block(article: RawArticle) -> str:
    """Форматирует блок подкаста для вставки в сборный пост."""
    if not article or not article.url:
        return ""
    # Prefer engine's youtube block if available
    try:
        engine = EditorialEngine()
        return engine.generate_youtube_block(article)
    except Exception:
        # Fallback to legacy formatting
        t_match = re.search(r'\?t=(\d+)', article.url)
        seconds = int(t_match.group(1)) if t_match else 0
        minutes = seconds // 60
        secs = seconds % 60
        timecode = f"{minutes}:{secs:02d}"

        excerpt = article.abstract[:200] + "..." if len(article.abstract) > 200 else article.abstract

        return (
            f"🎙 <b>Подкаст:</b>\n"
            f"{article.title}\n"
            f"▶ <a href='{article.url}'>Слушать с {timecode}</a>\n"
            f"<i>{excerpt}</i>"
        )