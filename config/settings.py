import os

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return int(value)


# Telegram
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_CHAT_ID = _int_env("ADMIN_CHAT_ID", 0)
CHANNEL_ID = os.getenv("CHANNEL_ID", "")

# Telegraph
TELEGRAPH_TOKEN = os.getenv("TELEGRAPH_TOKEN", "")
TELEGRAPH_AUTHOR = os.getenv("TELEGRAPH_AUTHOR", "Noerra")
TELEGRAPH_AUTHOR_URL = os.getenv("TELEGRAPH_AUTHOR_URL", "https://t.me/noerra_publishes")

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "noerra.db")

# Schedule
PARSE_INTERVAL_MINUTES = _int_env("PARSE_INTERVAL_MINUTES", 360)
DIGEST_HOUR = _int_env("DIGEST_HOUR", 10)

# Digest
TOP_PER_TOPIC = _int_env("TOP_PER_TOPIC", 2)
MAX_TOPICS_IN_DIGEST = _int_env("MAX_TOPICS_IN_DIGEST", 4)

# Scoring
MIN_SCORE_TO_MODERATE = _int_env("MIN_SCORE_TO_MODERATE", 20)
MAX_ARTICLES_PER_RUN = _int_env("MAX_ARTICLES_PER_RUN", 30)

# PubMed
PUBMED_MAX_RESULTS = _int_env("PUBMED_MAX_RESULTS", 5)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "noerra.log")
