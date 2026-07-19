# ============================================================
#  database/db.py — SQLite с оптимизацией
# ============================================================

import sqlite3
import logging
import json
from contextlib import contextmanager
from config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)

# Connection pool для производительности
_connection_cache = {}

@contextmanager
def get_conn():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # Быстрее для записи
    conn.execute("PRAGMA cache_size=10000")   # Кэш 10MB
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                source       TEXT NOT NULL,
                external_id  TEXT,
                title        TEXT NOT NULL,
                abstract     TEXT,
                url          TEXT UNIQUE NOT NULL,
                topic        TEXT,
                score        INTEGER DEFAULT 0,
                status       TEXT DEFAULT 'new',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS summaries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id   INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                summary_ru   TEXT,
                post_text    TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS publications (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id       INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                telegraph_url    TEXT,
                telegram_post_id BIGINT,
                status           TEXT DEFAULT 'pending',
                published_at     TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_articles_url    ON articles(url);
            CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
            CREATE INDEX IF NOT EXISTS idx_articles_topic  ON articles(topic);
        """)

        # Migration: add reject_reason column if not exists
        cols = conn.execute("PRAGMA table_info(articles)").fetchall()
        col_names = {c[1] for c in cols}
        if "reject_reason" not in col_names:
            conn.execute("ALTER TABLE articles ADD COLUMN reject_reason TEXT DEFAULT NULL")
            logger.info("Migration: added reject_reason column to articles")

        # FTS5 full-text search on articles
        conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
                title, abstract, content='articles', content_rowid='id'
            );
        """)
        # table for caching translations
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS translations (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                source_text    TEXT NOT NULL UNIQUE,
                translated_text TEXT,
                lang           TEXT DEFAULT 'ru',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_translations_source ON translations(source_text);
        """)
        # editor drafts and feedback
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS drafts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id     INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                title          TEXT,
                lead           TEXT,
                body           TEXT,
                short_version  TEXT,
                full_version   TEXT,
                sources        TEXT,
                topic          TEXT,
                format         TEXT,
                confidence     REAL,
                audience       TEXT,
                status         TEXT DEFAULT 'pending',
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS editor_feedback (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id       INTEGER REFERENCES drafts(id) ON DELETE CASCADE,
                editor         TEXT,
                decision       TEXT,
                reason         TEXT,
                notes          TEXT,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Knowledge Core tables
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS research_passports (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id        INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                doi               TEXT,
                journal           TEXT,
                authors           TEXT,
                published_at      TEXT,
                study_type        TEXT,
                peer_reviewed     INTEGER DEFAULT 0,
                sample_size       TEXT,
                methodology       TEXT,
                limitations       TEXT,
                practical_value   TEXT,
                evidence_strength TEXT,
                topic             TEXT,
                key_findings      TEXT,
                trust_level       REAL DEFAULT 0,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scientific_claims (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_text      TEXT NOT NULL,
                normalized_text TEXT NOT NULL UNIQUE,
                topic           TEXT,
                status          TEXT DEFAULT 'active',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS claim_evidence (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id          INTEGER REFERENCES scientific_claims(id) ON DELETE CASCADE,
                article_id        INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                relation          TEXT,
                evidence_strength TEXT,
                confidence        REAL DEFAULT 0,
                reasoning         TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(claim_id, article_id)
            );

            CREATE TABLE IF NOT EXISTS consensus_states (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                claim_id         INTEGER REFERENCES scientific_claims(id) ON DELETE CASCADE,
                support_count    INTEGER DEFAULT 0,
                contradict_count INTEGER DEFAULT 0,
                mention_count    INTEGER DEFAULT 0,
                consensus_level  TEXT,
                confidence       REAL DEFAULT 0,
                summary          TEXT,
                version          INTEGER DEFAULT 1,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS knowledge_versions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                topic           TEXT NOT NULL,
                version         TEXT NOT NULL,
                summary         TEXT,
                changed_because TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(topic, version)
            );

            CREATE TABLE IF NOT EXISTS knowledge_diffs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                topic           TEXT NOT NULL,
                from_version    TEXT,
                to_version      TEXT,
                before_text     TEXT,
                after_text      TEXT,
                reason          TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS open_questions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                topic           TEXT NOT NULL,
                question        TEXT NOT NULL,
                current_status  TEXT DEFAULT 'open',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS myths (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                topic           TEXT NOT NULL,
                myth_text       TEXT NOT NULL,
                correction      TEXT,
                evidence_summary TEXT,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_research_passports_article ON research_passports(article_id);
            CREATE INDEX IF NOT EXISTS idx_scientific_claims_topic ON scientific_claims(topic);
            CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim ON claim_evidence(claim_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_versions_topic ON knowledge_versions(topic);
            CREATE INDEX IF NOT EXISTS idx_open_questions_topic ON open_questions(topic);
            CREATE INDEX IF NOT EXISTS idx_myths_topic ON myths(topic);
        """)

        # Reasoning chains
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS reasoning_chains (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                topic             TEXT NOT NULL,
                claim_text        TEXT NOT NULL,
                chain_json        TEXT,
                final_confidence  REAL DEFAULT 0,
                conclusion        TEXT,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_reasoning_chains_topic ON reasoning_chains(topic);
            CREATE INDEX IF NOT EXISTS idx_drafts_article ON drafts(article_id);
            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
            CREATE INDEX IF NOT EXISTS idx_editor_feedback_draft ON editor_feedback(draft_id);
            CREATE INDEX IF NOT EXISTS idx_claim_evidence_article ON claim_evidence(article_id);
            CREATE INDEX IF NOT EXISTS idx_summaries_article ON summaries(article_id);
        """)

        # Audience metrics (Business Model MVP шаг 3 — "проверить реакцию
        # аудитории"): то, что реально отдаёт Bot API без MTPToto-клиента —
        # агрегированные реакции на пост (message_reaction_count, без деанона
        # юзеров) и число подписчиков канала (get_chat_member_count,
        # периодический снимок). Просмотры/репосты постфактум через Bot API
        # недоступны — этих таблиц под них нет, честно не притворяемся.
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS post_reactions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id        TEXT NOT NULL,
                message_id     INTEGER NOT NULL,
                reaction_type  TEXT NOT NULL,
                total_count    INTEGER DEFAULT 0,
                updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, message_id, reaction_type)
            );
            CREATE INDEX IF NOT EXISTS idx_post_reactions_message
                ON post_reactions(chat_id, message_id);

            CREATE TABLE IF NOT EXISTS channel_stats (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id            TEXT NOT NULL,
                subscriber_count   INTEGER NOT NULL,
                snapshot_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_channel_stats_chat_time
                ON channel_stats(chat_id, snapshot_at);
        """)

        # FTS triggers: keep index in sync when articles change
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO articles_fts(rowid, title, abstract)
                VALUES (new.id, new.title, new.abstract);
            END;
            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, abstract)
                VALUES ('delete', old.id, old.title, old.abstract);
            END;
            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO articles_fts(articles_fts, rowid, title, abstract)
                VALUES ('delete', old.id, old.title, old.abstract);
                INSERT INTO articles_fts(rowid, title, abstract)
                VALUES (new.id, new.title, new.abstract);
            END;
        """)
        # Populate FTS index from existing articles (safe to run repeatedly)
        conn.execute("""
            INSERT OR IGNORE INTO articles_fts(rowid, title, abstract)
            SELECT id, title, abstract FROM articles
        """)
    logger.info("БД инициализирована")


def article_exists(url: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM articles WHERE url = ?", (url,)
        ).fetchone() is not None


def save_article(
    source: str, title: str, url: str,
    abstract: str = "", external_id: str = "",
    topic: str = "", score: int = 0, status: str = "new",
) -> int | None:
    if article_exists(url):
        return None
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO articles (source, external_id, title, abstract, url, topic, score, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source, external_id, title, abstract, url, topic, score, status),
        )
        return cur.lastrowid


def save_summary(article_id: int, summary_ru: str, post_text: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO summaries (article_id, summary_ru, post_text) VALUES (?, ?, ?)",
            (article_id, summary_ru, post_text),
        )


def replace_summary(article_id: int, summary_ru: str, post_text: str) -> None:
    """Как save_summary(), но идемпотентно — для scripts/regenerate_summaries.py.

    save_summary() всегда INSERT, без уникального ограничения на
    article_id — повторный запуск плодил бы вторую строку, и все места,
    читающие summaries через LEFT JOIN без LIMIT 1 (get_article_by_id и
    остальные, database/db.py), начали бы получать статью задвоенной."""
    with get_conn() as conn:
        conn.execute("DELETE FROM summaries WHERE article_id = ?", (article_id,))
        conn.execute(
            "INSERT INTO summaries (article_id, summary_ru, post_text) VALUES (?, ?, ?)",
            (article_id, summary_ru, post_text),
        )


def get_latest_draft_for_article(article_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM drafts WHERE article_id = ? ORDER BY id DESC LIMIT 1",
            (article_id,),
        ).fetchone()


def update_draft_content(
    draft_id: int,
    title: str,
    lead: str,
    body: str,
    short_version: str,
    full_version: str,
    sources: str,
    topic: str,
    format: str,
    confidence: float,
    audience: str,
) -> None:
    """Обновляет текстовые поля существующего драфта, не трогая id/status —
    /drafts (bot/commands.py) и карточка модерации в Telegram ссылаются
    на конкретный draft_id, INSERT новой строки оставил бы их указывать
    на устаревший текст."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE drafts SET
                title = ?, lead = ?, body = ?, short_version = ?, full_version = ?,
                sources = ?, topic = ?, format = ?, confidence = ?, audience = ?
               WHERE id = ?""",
            (title, lead, body, short_version, full_version, sources, topic, format, confidence, audience, draft_id),
        )


def get_articles_by_statuses(statuses: tuple[str, ...]) -> list[sqlite3.Row]:
    """Статьи в любом из перечисленных статусов, со старым сохранённым
    текстом (для отчёта "было -> стало") — для scripts/regenerate_summaries.py."""
    with get_conn() as conn:
        placeholders = ",".join("?" * len(statuses))
        return conn.execute(
            f"""SELECT a.id, a.source, a.external_id, a.title, a.abstract, a.url,
                       a.topic, a.score, a.status, s.post_text AS old_post_text
                FROM articles a
                LEFT JOIN summaries s ON s.article_id = a.id
                WHERE a.status IN ({placeholders})
                ORDER BY a.id""",
            statuses,
        ).fetchall()


def get_recent_titles_and_leads_by_topic(topic: str, limit: int = 10) -> tuple[set[str], list[str]]:
    """Заголовки и лиды недавних драфтов по теме — для anti-repeat в
    _build_title()/_build_lead() (см. editorial_engine.py): банк
    TITLE_PATTERNS/LEAD_PATTERNS конечен, и при частой теме коллизии
    неизбежны при чистом random.choice (найдено на живых данных
    2026-07-15 — draft id 185/186, дословно одинаковый заголовок для
    разных статей "Когниция" подряд, даже после расширения банка до 8
    вариантов)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT title, lead FROM drafts WHERE topic = ? ORDER BY created_at DESC LIMIT ?",
            (topic, limit),
        ).fetchall()
        titles = {r["title"] for r in rows if r["title"]}
        leads = [r["lead"] for r in rows if r["lead"]]
        return titles, leads


def get_recent_summaries(limit: int = 30) -> list[sqlite3.Row]:
    """Последние сгенерированные посты для автоматической вычитки
    (adaptation/content_audit.py) — самые свежие summaries вне
    зависимости от статуса статьи, чтобы ловить дефекты до публикации."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT s.article_id AS id, a.title, a.topic, s.post_text, s.created_at
               FROM summaries s
               JOIN articles a ON a.id = s.article_id
               ORDER BY s.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()


def save_research_passport(passport) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO research_passports (
                article_id, doi, journal, authors, published_at, study_type,
                peer_reviewed, sample_size, methodology, limitations,
                practical_value, evidence_strength, topic, key_findings, trust_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                passport.article_id,
                passport.doi,
                passport.journal,
                json.dumps(passport.authors, ensure_ascii=False),
                passport.published_at,
                passport.study_type,
                1 if passport.peer_reviewed else 0,
                passport.sample_size,
                passport.methodology,
                passport.limitations,
                passport.practical_value,
                passport.evidence_strength,
                passport.topic,
                json.dumps(passport.key_findings, ensure_ascii=False),
                passport.trust_level,
            ),
        )
        return cur.lastrowid


def upsert_scientific_claim(claim_text: str, normalized_text: str, topic: str) -> int:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO scientific_claims (claim_text, normalized_text, topic)
               VALUES (?, ?, ?)""",
            (claim_text, normalized_text, topic),
        )
        row = conn.execute(
            "SELECT id FROM scientific_claims WHERE normalized_text = ?",
            (normalized_text,),
        ).fetchone()
        return row["id"]


def save_claim_evidence(
    claim_id: int,
    article_id: int,
    relation: str,
    evidence_strength: str,
    confidence: float,
    reasoning: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO claim_evidence (
                claim_id, article_id, relation, evidence_strength, confidence, reasoning
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (claim_id, article_id, relation, evidence_strength, confidence, reasoning),
        )


def update_consensus_for_claim(claim_id: int) -> None:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT relation, confidence FROM claim_evidence WHERE claim_id = ?",
            (claim_id,),
        ).fetchall()
        support = sum(1 for row in rows if row["relation"] == "supports")
        contradict = sum(1 for row in rows if row["relation"] == "contradicts")
        mentions = sum(1 for row in rows if row["relation"] == "mentions")
        total = max(len(rows), 1)
        avg_confidence = sum(float(row["confidence"] or 0) for row in rows) / total

        if support >= 3 and contradict == 0 and avg_confidence >= 0.65:
            level = "emerging_consensus"
        elif support > contradict:
            level = "supported"
        elif contradict > support:
            level = "contested"
        elif support and contradict:
            level = "mixed"
        else:
            level = "insufficient_data"

        summary = f"support={support}; contradict={contradict}; mentions={mentions}"
        conn.execute(
            """INSERT INTO consensus_states (
                claim_id, support_count, contradict_count, mention_count,
                consensus_level, confidence, summary, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((
                SELECT MAX(version) + 1 FROM consensus_states WHERE claim_id = ?
            ), 1))""",
            (claim_id, support, contradict, mentions, level, avg_confidence, summary, claim_id),
        )


def get_article_by_id(article_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            """SELECT a.*, s.summary_ru, s.post_text
               FROM articles a
               LEFT JOIN summaries s ON s.article_id = a.id
               WHERE a.id = ?""",
            (article_id,),
        ).fetchone()


def update_article_status(article_id: int, status: str, reject_reason: str = ""):
    with get_conn() as conn:
        if reject_reason:
            conn.execute(
                "UPDATE articles SET status = ?, reject_reason = ? WHERE id = ?",
                (status, reject_reason, article_id),
            )
        else:
            conn.execute(
                "UPDATE articles SET status = ? WHERE id = ?",
                (status, article_id),
            )


def save_publication(article_id: int, telegraph_url: str, telegram_post_id: int = 0):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO publications (article_id, telegraph_url, telegram_post_id, status, published_at)
               VALUES (?, ?, ?, 'published', CURRENT_TIMESTAMP)""",
            (article_id, telegraph_url, telegram_post_id),
        )


def get_recent_articles(limit: int = 3) -> list[sqlite3.Row]:
    """
    Возвращает последние статьи за 24 часа, отсортированные по score.
    Полезно для быстрой проверки содержимого базы.
    """
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT a.*, s.summary_ru, s.post_text
            FROM articles a
            LEFT JOIN summaries s ON s.article_id = a.id
            WHERE a.status = 'new'
              AND a.created_at >= datetime('now', '-24 hours')
            ORDER BY a.score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def get_top_per_topic(top_n: int = 3) -> dict[str, list[sqlite3.Row]]:
    """
    Возвращает словарь {тема: [топ N статей]} за последние 24 часа.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT a.*, s.summary_ru, s.post_text
            FROM articles a
            LEFT JOIN summaries s ON s.article_id = a.id
            WHERE a.status = 'new'
              AND a.created_at >= datetime('now', '-24 hours')
            ORDER BY a.topic, a.score DESC
            """,
        ).fetchall()

    result: dict[str, list] = {}
    for row in rows:
        topic = row["topic"] or "unknown"
        if topic == "unknown":
            continue
        if topic not in result:
            result[topic] = []
        if len(result[topic]) < top_n:
            result[topic].append(row)

    return result


def get_stats() -> dict:
    with get_conn() as conn:
        total     = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        pending   = conn.execute("SELECT COUNT(*) FROM articles WHERE status='pending'").fetchone()[0]
        approved  = conn.execute("SELECT COUNT(*) FROM articles WHERE status='approved'").fetchone()[0]
        rejected  = conn.execute("SELECT COUNT(*) FROM articles WHERE status='rejected'").fetchone()[0]
        published = conn.execute("SELECT COUNT(*) FROM articles WHERE status='published'").fetchone()[0]
        today     = conn.execute(
            "SELECT COUNT(*) FROM articles WHERE created_at >= datetime('now', '-24 hours')"
        ).fetchone()[0]

        # Топ-3 причины отказа за последнюю неделю
        reject_rows = conn.execute(
            """SELECT reject_reason, COUNT(*) as cnt
               FROM articles
               WHERE reject_reason IS NOT NULL
                 AND created_at >= datetime('now', '-7 days')
               GROUP BY reject_reason
               ORDER BY cnt DESC
               LIMIT 3"""
        ).fetchall()
        top_reject_reasons = [(r["reject_reason"], r["cnt"]) for r in reject_rows]

        return {
            "total": total, "pending": pending, "approved": approved,
            "rejected": rejected, "published": published, "today": today,
            "top_reject_reasons": top_reject_reasons,
        }


def get_top_articles_by_topic(
    top_per_topic: int = 2,
    max_topics: int = 4,
    min_score: int = 20,
) -> list:
    """
    Возвращает топ статей по каждой теме за последние 24 часа.
    Только новые (status = 'new'), с score >= min_score.
    """
    with get_conn() as conn:
        # Получаем темы с наибольшим числом качественных статей
        topics = conn.execute("""
            SELECT topic, COUNT(*) as cnt
            FROM articles
            WHERE status = 'new'
              AND score >= ?
              AND created_at >= datetime('now', '-24 hours')
            GROUP BY topic
            ORDER BY MAX(score) DESC
            LIMIT ?
        """, (min_score, max_topics)).fetchall()

        result = []
        for row in topics:
            topic = row["topic"]
            articles = conn.execute("""
                SELECT a.id, a.title, a.url, a.score, a.topic, a.source,
                       s.summary_ru, s.post_text, a.abstract
                FROM articles a
                LEFT JOIN summaries s ON s.article_id = a.id
                WHERE a.topic = ?
                  AND a.status = 'new'
                  AND a.score >= ?
                  AND a.created_at >= datetime('now', '-24 hours')
                ORDER BY a.score DESC
                LIMIT ?
            """, (topic, min_score, top_per_topic)).fetchall()
            result.extend(articles)

        return result


def get_articles_by_topic(topic: str, limit: int = 5, min_score: int = 10, status: str = "new") -> list[sqlite3.Row]:
    """Возвращает статьи по теме для построения knowledge context."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT id, title, url, source, abstract, score, created_at
            FROM articles
            WHERE topic = ? AND score >= ? AND status = ?
            ORDER BY score DESC
            LIMIT ?
        """, (topic, min_score, status, limit)).fetchall()


def search_articles_fts(query: str, limit: int = 10) -> list[sqlite3.Row]:
    """Полнотекстовый поиск по статьям через FTS5."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.id, a.title, a.abstract, a.url, a.topic, a.score, a.source,
                   s.summary_ru, s.post_text
            FROM articles_fts f
            JOIN articles a ON a.id = f.rowid
            LEFT JOIN summaries s ON s.article_id = a.id
            WHERE articles_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit)).fetchall()


def get_published_articles_for_site() -> list[sqlite3.Row]:
    """Опубликованные статьи для scripts/generate_site.py — берём текст
    из drafts (title/body/full_version), не summaries: summaries.summary_ru
    отсутствует у части ранних статей (article id=397 — опубликована до
    того, как save_summary() стал вызываться надёжно для каждой статьи),
    а drafts есть у всех published без исключения (проверено на
    noerra.db, 2026-07-19). d.body уже без дублирующей заголовок строки
    (см. adaptation/pipeline.py:Pipeline.run_for_article — та же сборка)."""
    with get_conn() as conn:
        return conn.execute(
            """SELECT a.id, a.url AS source_url, a.created_at, a.topic,
                      d.title, d.body, d.full_version,
                      p.telegraph_url, p.published_at
               FROM articles a
               JOIN drafts d ON d.id = (
                   SELECT id FROM drafts WHERE article_id = a.id ORDER BY id DESC LIMIT 1
               )
               LEFT JOIN publications p ON p.article_id = a.id
               WHERE a.status = 'published'
               ORDER BY COALESCE(p.published_at, a.created_at) DESC"""
        ).fetchall()


def get_youtube_by_topic(topic: str):
    """Возвращает лучшее YouTube видео по теме за последние 24 часа."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.id, a.title, a.url, a.abstract, a.score
            FROM articles a
            WHERE a.source = 'youtube'
              AND a.topic = ?
              AND a.status = 'new'
              AND a.created_at >= datetime('now', '-24 hours')
            ORDER BY a.score DESC
            LIMIT 1
        """, (topic,)).fetchone()


def get_translation(source_text: str, lang: str = "ru") -> str | None:
    """Возвращает сохранённый перевод из кеша, если есть."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT translated_text FROM translations WHERE source_text = ? AND lang = ?",
            (source_text, lang),
        ).fetchone()
        return row[0] if row else None


def save_translation(source_text: str, translated_text: str, lang: str = "ru") -> None:
    """Сохраняет перевод в кеш (INSERT OR REPLACE)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO translations (source_text, translated_text, lang) VALUES (?, ?, ?)",
            (source_text, translated_text, lang),
        )


def count_translations_matching(pattern: str) -> int:
    """Считает записи кеша, чей translated_text подходит под pattern (SQL LIKE, % — wildcard).

    Для предпросмотра перед invalidate_translations_matching().
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM translations WHERE translated_text LIKE ?",
            (pattern,),
        ).fetchone()
        return row[0] if row else 0


def invalidate_translations_matching(pattern: str) -> int:
    """Удаляет из кеша переводы, чей translated_text содержит pattern (SQL LIKE, % — wildcard).

    Нужно на случай будущих правок логики перевода (_fix_translation и
    похожие): сам фикс применяется только к новым переводам — уже
    закэшированные записи молча остаются со старым (возможно испорченным)
    текстом навсегда, пока их явно не инвалидировать. Возвращает
    количество удалённых строк.
    """
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM translations WHERE translated_text LIKE ?",
            (pattern,),
        )
        return cur.rowcount


def clear_translation_cache() -> int:
    """Полностью очищает кеш переводов (например, после смены логики перевода целиком)."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM translations")
        return cur.rowcount


def save_draft(
    article_id: int,
    title: str,
    lead: str,
    body: str,
    short_version: str,
    full_version: str,
    sources: str,
    topic: str,
    format: str,
    confidence: float,
    audience: str,
) -> int:
    """Save a draft publication to the editor inbox and return draft id."""
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO drafts (
                article_id, title, lead, body, short_version, full_version,
                sources, topic, format, confidence, audience, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (article_id, title, lead, body, short_version, full_version, sources, topic, format, confidence, audience),
        )
        return cur.lastrowid


def get_pending_drafts(limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM drafts WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()


def get_draft_by_id(draft_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()


def get_draft_with_context(draft_id: int) -> dict | None:
    """Возвращает драфт со связанными данными статьи и research passport."""
    with get_conn() as conn:
        draft = conn.execute(
            "SELECT * FROM drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        if not draft:
            return None

        result = dict(draft)

        # Присоединяем статью
        if draft["article_id"]:
            article = conn.execute(
                "SELECT * FROM articles WHERE id = ?",
                (draft["article_id"],),
            ).fetchone()
            if article:
                result["article"] = dict(article)

            # Присоединяем research passport
            passport = conn.execute(
                "SELECT * FROM research_passports WHERE article_id = ?",
                (draft["article_id"],),
            ).fetchone()
            if passport:
                result["passport"] = dict(passport)

        return result


def update_draft_status(draft_id: int, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE drafts SET status = ? WHERE id = ?",
            (status, draft_id),
        )


def save_editor_feedback(draft_id: int, editor: str, decision: str, reason: str = '', notes: str = '') -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO editor_feedback (draft_id, editor, decision, reason, notes) VALUES (?, ?, ?, ?, ?)""",
            (draft_id, editor, decision, reason, notes),
        )
        # update draft status
        conn.execute("UPDATE drafts SET status = ? WHERE id = ?", (decision, draft_id))
        return cur.lastrowid


# ── Knowledge Versioning ──────────────────────────────────────

def save_knowledge_version(topic: str, version: str, summary: str, changed_because: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT OR REPLACE INTO knowledge_versions (topic, version, summary, changed_because)
               VALUES (?, ?, ?, ?)""",
            (topic, version, summary, changed_because),
        )
        return cur.lastrowid


def get_latest_knowledge_version(topic: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM knowledge_versions WHERE topic = ? ORDER BY id DESC LIMIT 1",
            (topic,),
        ).fetchone()


def get_knowledge_history(topic: str, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM knowledge_versions WHERE topic = ? ORDER BY id DESC LIMIT ?",
            (topic, limit),
        ).fetchall()


def save_knowledge_diff(
    topic: str,
    from_version: str,
    to_version: str,
    before_text: str,
    after_text: str,
    reason: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO knowledge_diffs (topic, from_version, to_version, before_text, after_text, reason)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (topic, from_version, to_version, before_text, after_text, reason),
        )
        return cur.lastrowid


def get_knowledge_diffs(topic: str, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM knowledge_diffs WHERE topic = ? ORDER BY id DESC LIMIT ?",
            (topic, limit),
        ).fetchall()


# ── Open Questions ────────────────────────────────────────────

def save_open_question(topic: str, question: str, current_status: str = "open") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO open_questions (topic, question, current_status) VALUES (?, ?, ?)",
            (topic, question, current_status),
        )
        return cur.lastrowid


def get_open_questions(topic: str, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM open_questions WHERE topic = ? AND current_status = 'open' ORDER BY id DESC LIMIT ?",
            (topic, limit),
        ).fetchall()


# ── Myths ─────────────────────────────────────────────────────

def save_myth(topic: str, myth_text: str, correction: str = "", evidence_summary: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO myths (topic, myth_text, correction, evidence_summary)
               VALUES (?, ?, ?, ?)""",
            (topic, myth_text, correction, evidence_summary),
        )
        return cur.lastrowid


def get_myths(topic: str, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM myths WHERE topic = ? ORDER BY id DESC LIMIT ?",
            (topic, limit),
        ).fetchall()


# ── Research Passport queries ─────────────────────────────────

def get_research_passport(article_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM research_passports WHERE article_id = ?",
            (article_id,),
        ).fetchone()


def get_claims_for_topic(topic: str, limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT c.*, cs.consensus_level, cs.confidence, cs.support_count, cs.contradict_count
               FROM scientific_claims c
               LEFT JOIN consensus_states cs ON cs.claim_id = c.id
               WHERE c.topic = ? AND c.status = 'active'
               ORDER BY cs.confidence DESC NULLS LAST
               LIMIT ?""",
            (topic, limit),
        ).fetchall()


def get_consensus_for_topic(topic: str, limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT DISTINCT cs.*
               FROM consensus_states cs
               JOIN scientific_claims c ON c.id = cs.claim_id
               WHERE c.topic = ?
               ORDER BY cs.confidence DESC NULLS LAST
               LIMIT ?""",
            (topic, limit),
        ).fetchall()


def save_reasoning_chain(
    topic: str,
    claim_text: str,
    chain_json: str,
    final_confidence: float,
    conclusion: str,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO reasoning_chains (topic, claim_text, chain_json, final_confidence, conclusion)
               VALUES (?, ?, ?, ?, ?)""",
            (topic, claim_text, chain_json, final_confidence, conclusion),
        )
        return cur.lastrowid


def get_reasoning_chain(claim_text: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM reasoning_chains WHERE claim_text = ? ORDER BY id DESC LIMIT 1",
            (claim_text,),
        ).fetchone()


def get_editorial_decisions(limit: int = 100) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """SELECT ef.*, d.article_id, d.topic
               FROM editor_feedback ef
               JOIN drafts d ON d.id = ef.draft_id
               ORDER BY ef.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()


def get_consensus_history(claim_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM consensus_states WHERE claim_id = ? ORDER BY version DESC LIMIT ?",
            (claim_id, limit),
        ).fetchall()


def execute_query(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def cleanup_invalid_claims_and_questions() -> dict:
    """Удаляет некорректные claims, вопросы и мифы из БД.
    
    Возвращает статистику удалений.
    """
    skip_markers = (
        "we used", "we conducted", "we performed", "this study aimed",
        "the aim of", "objective:", "background:", "methods:",
        "мы использовали", "целью данного", "в данном исследовании",
    )
    
    stats = {
        "claims_deleted": 0,
        "questions_deleted": 0,
        "myths_deleted": 0,
    }
    
    with get_conn() as conn:
        # Удаляем claims с методологией или слишком длинные
        skip_patterns = [f"%{marker}%" for marker in skip_markers]
        for pattern in skip_patterns:
            result = conn.execute(
                "DELETE FROM scientific_claims WHERE claim_text LIKE ? AND length(claim_text) > 200",
                (pattern,),
            )
            stats["claims_deleted"] += result.rowcount
        
        # Удаляем вопросы с методологией
        for pattern in skip_patterns:
            result = conn.execute(
                "DELETE FROM open_questions WHERE question LIKE ?",
                (pattern.replace("%", "%%"),),  # Escape % for LIKE
            )
            stats["questions_deleted"] += result.rowcount
        
        # Удаляем мифы с методологией
        for pattern in skip_patterns:
            result = conn.execute(
                "DELETE FROM myths WHERE myth_text LIKE ?",
                (pattern.replace("%", "%%"),),
            )
            stats["myths_deleted"] += result.rowcount
        
        # Удаляем слишком длинные вопросы/мифы (>200 символов)
        result = conn.execute("DELETE FROM open_questions WHERE length(question) > 200")
        stats["questions_deleted"] += result.rowcount
        
        result = conn.execute("DELETE FROM myths WHERE length(myth_text) > 250")
        stats["myths_deleted"] += result.rowcount

    return stats


# ── Audience metrics ────────────────────────────────────────────

def save_post_reaction_counts(chat_id: str, message_id: int, counts: dict[str, int]) -> None:
    """Upsert current total per reaction emoji for one channel post.

    counts приходит из message_reaction_count-события целиком — это не
    дельта, а актуальный снимок всех реакций поста на момент события,
    поэтому просто перезаписываем, а не суммируем.
    """
    with get_conn() as conn:
        for reaction_type, total_count in counts.items():
            conn.execute(
                """INSERT INTO post_reactions (chat_id, message_id, reaction_type, total_count, updated_at)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(chat_id, message_id, reaction_type)
                   DO UPDATE SET total_count = excluded.total_count, updated_at = excluded.updated_at""",
                (str(chat_id), message_id, reaction_type, total_count),
            )


def get_post_reaction_counts(chat_id: str, message_id: int) -> dict[str, int]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT reaction_type, total_count FROM post_reactions WHERE chat_id = ? AND message_id = ?",
            (str(chat_id), message_id),
        ).fetchall()
        return {r["reaction_type"]: r["total_count"] for r in rows}


def save_channel_stats_snapshot(chat_id: str, subscriber_count: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO channel_stats (chat_id, subscriber_count) VALUES (?, ?)",
            (str(chat_id), subscriber_count),
        )
        return cur.lastrowid


def get_channel_stats_history(chat_id: str, limit: int = 90) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM channel_stats WHERE chat_id = ? ORDER BY snapshot_at DESC LIMIT ?",
            (str(chat_id), limit),
        ).fetchall()


def get_top_reacted_posts(chat_id: str, limit: int = 5) -> list[sqlite3.Row]:
    """Посты с наибольшей суммой реакций по всем эмодзи.

    Не джойнит publications напрямую: у кластерных постов один message_id
    соответствует нескольким строкам publications (по одной на статью
    кластера) — джойн размножил бы строки до GROUP BY и испортил бы сумму.
    Заголовки для отображения берёт отдельно get_publication_titles_for_message.
    """
    with get_conn() as conn:
        return conn.execute(
            """SELECT message_id, SUM(total_count) AS total
               FROM post_reactions WHERE chat_id = ?
               GROUP BY message_id ORDER BY total DESC LIMIT ?""",
            (str(chat_id), limit),
        ).fetchall()


def get_publication_titles_for_message(message_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT a.title FROM publications p
               JOIN articles a ON a.id = p.article_id
               WHERE p.telegram_post_id = ?""",
            (message_id,),
        ).fetchall()
        return [r["title"] for r in rows]


# ── Retention cleanup ────────────────────────────────────────────

def cleanup_unpublished_older_than(days: int = 7) -> dict[str, int]:
    """Удаляет статьи (в т.ч. source='youtube'), драфты и всё, что на
    них ссылается, если они старше `days` дней и не были опубликованы.

    Опубликованное защищено по факту наличия строки в publications, а
    не по articles.status — status теоретически может разъехаться, а
    publications.article_id — прямое доказательство публикации.

    PRAGMA foreign_keys в проекте нигде не включён (см. историю ручной
    чистки 2026-07-15) — ON DELETE CASCADE в схеме не сработает сам,
    поэтому дочерние строки удаляются явно, в порядке потомок→родитель.
    """
    cutoff = f"-{days} days"
    stats = {
        "articles": 0, "drafts": 0, "summaries": 0,
        "research_passports": 0, "claim_evidence": 0, "editor_feedback": 0,
    }
    with get_conn() as conn:
        old_article_ids = [r["id"] for r in conn.execute(
            """SELECT id FROM articles
               WHERE created_at < datetime('now', ?)
                 AND id NOT IN (SELECT article_id FROM publications)""",
            (cutoff,),
        ).fetchall()]

        if old_article_ids:
            aidp = ",".join("?" * len(old_article_ids))
            draft_ids = [r["id"] for r in conn.execute(
                f"SELECT id FROM drafts WHERE article_id IN ({aidp})", old_article_ids
            ).fetchall()]
            if draft_ids:
                didp = ",".join("?" * len(draft_ids))
                stats["editor_feedback"] += conn.execute(
                    f"DELETE FROM editor_feedback WHERE draft_id IN ({didp})", draft_ids
                ).rowcount
            stats["drafts"] += conn.execute(
                f"DELETE FROM drafts WHERE article_id IN ({aidp})", old_article_ids
            ).rowcount
            stats["summaries"] += conn.execute(
                f"DELETE FROM summaries WHERE article_id IN ({aidp})", old_article_ids
            ).rowcount
            stats["research_passports"] += conn.execute(
                f"DELETE FROM research_passports WHERE article_id IN ({aidp})", old_article_ids
            ).rowcount
            stats["claim_evidence"] += conn.execute(
                f"DELETE FROM claim_evidence WHERE article_id IN ({aidp})", old_article_ids
            ).rowcount
            stats["articles"] += conn.execute(
                f"DELETE FROM articles WHERE id IN ({aidp})", old_article_ids
            ).rowcount

        # Драфты без привязки к статье (article_id 0/NULL) или чья статья
        # не старше cutoff, но сам драфт — старше (штатно не бывает, т.к.
        # драфт создаётся после статьи, но проверяем для полноты).
        standalone_draft_ids = [r["id"] for r in conn.execute(
            """SELECT id FROM drafts
               WHERE created_at < datetime('now', ?)
                 AND (article_id IS NULL OR article_id = 0
                      OR article_id NOT IN (SELECT article_id FROM publications))""",
            (cutoff,),
        ).fetchall()]
        if standalone_draft_ids:
            didp = ",".join("?" * len(standalone_draft_ids))
            stats["editor_feedback"] += conn.execute(
                f"DELETE FROM editor_feedback WHERE draft_id IN ({didp})", standalone_draft_ids
            ).rowcount
            stats["drafts"] += conn.execute(
                f"DELETE FROM drafts WHERE id IN ({didp})", standalone_draft_ids
            ).rowcount

    return stats
