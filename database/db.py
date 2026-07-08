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


def update_article_status(article_id: int, status: str):
    with get_conn() as conn:
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
        return {
            "total": total, "pending": pending, "approved": approved,
            "rejected": rejected, "published": published, "today": today,
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
