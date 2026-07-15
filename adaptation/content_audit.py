# ============================================================
#  adaptation/content_audit.py — автоматическая часть ручной вычитки
#  (см. project memory project-noerra-editorial-engine: "главный рабочий
#  приём — вычитка сгенерированных статей на реальных данных").
#
#  Rule-based: ловит только структурные дефекты, которые уже встречались
#  в реальных публикациях (обрыв текста на середине слова, утечка
#  служебных меток источника, непереведённая латиница вне акронимов).
#  Смысловые дефекты (не тот вывод, скучный текст) сюда не входят —
#  это по-прежнему требует человека.
# ============================================================

import re

from adaptation.critic import EditorialCritic
from adaptation.transitions import (
    TRANSITION_INTO_BODY, TRANSITION_INTO_ANALOGY, TRANSITION_INTO_SIGNIFICANCE,
)
from adaptation.utils import _RU_SECTION_LABEL_RE, _SECTION_LABEL_RE

# Сигнатура обрыва: и adaptation/utils.py:_shorten() (fallback-ветка
# cut + '...'), и старый баг domain/knowledge/mental_models.py оставляли
# ровно такой хвост — литеральные три точки без завершённой мысли перед
# ними. Обычный редакционный текст три точки подряд не использует
# (EDITORIAL_PLAYBOOK запрещает драматизм/многоточия как приём).
def check_abrupt_cutoff(text: str) -> bool:
    return text.rstrip().endswith("...")


_LEAKED_METADATA_RE = re.compile(
    r"Announce Type|Тип объявления", re.IGNORECASE
)


def check_leaked_metadata(text: str) -> bool:
    return bool(_LEAKED_METADATA_RE.search(text))


_STRUCTURED_ABSTRACT_LABEL_RE = re.compile(
    "|".join([_SECTION_LABEL_RE.pattern, _RU_SECTION_LABEL_RE.pattern])
)


def check_structured_abstract_leak(text: str) -> bool:
    """Метка раздела структурированного абстракта ("ЦЕЛЬ:", "AIM:" и
    т.п.) осталась в тексте поста — переиспользует те же паттерны, что
    adaptation/utils.py:_strip_section_labels()/_strip_translated_section_labels()
    применяют на входе; этот audit-проход — не фильтр, а сигнал того,
    что фильтр где-то не сработал (найдено на живой публикации "СДВГ:
    свежие данные", article id=634, 2026-07-15)."""
    return bool(_STRUCTURED_ABSTRACT_LABEL_RE.search(text))


_QUOTE_STRIP_RE = re.compile(r'^[«"\']+|[»"\']+$')
_TRAILING_PUNCT_RE = re.compile(r'[.?!…]+$')


def _normalize_fragment(s: str) -> str:
    return _TRAILING_PUNCT_RE.sub("", _QUOTE_STRIP_RE.sub("", s.strip())).strip()


def check_duplicate_long_sentence(text: str, min_words: int = 8) -> bool:
    """Один и тот же протяжённый (min_words+) фрагмент текста встречается
    в посте дважды — например, находка сначала в лиде как утверждение, а
    затем то же самое дословно в вопросе-заголовке в кавычках (article
    id=634, "СДВГ: свежие данные": находка про фармацевтов и услуги по
    СДВГ повторена в лиде и в reader_question без единого изменения).

    Проверяет вхождение подстрокой между парами предложений, а не точное
    совпадение целых предложений: дубликат в реальном случае не
    отдельное предложение само по себе, а хвост более длинного вопроса
    ("Что именно показало исследование: <дословный повтор находки>?") —
    только начальные/конечные кавычки и пунктуация нормализуются.
    """
    if not text:
        return False
    raw_fragments = re.split(r'(?<=[.!?])\s+', text.replace("\n\n", " "))
    long_fragments = [
        f for f in (_normalize_fragment(r) for r in raw_fragments)
        if len(f.split()) >= min_words
    ]
    for i, a in enumerate(long_fragments):
        for b in long_fragments[i + 1:]:
            if a == b or a in b or b in a:
                return True
    return False


_ALL_TRANSITIONS = TRANSITION_INTO_BODY + TRANSITION_INTO_ANALOGY + TRANSITION_INTO_SIGNIFICANCE


def check_dangling_transition(text: str) -> bool:
    """Переход-обещание (TRANSITION_INTO_ANALOGY и т.п.) — последний
    абзац текста, без содержательного блока сразу за ним. В текущем
    build_structure() такое структурно невозможно (переход и его
    содержание добавляются одним условным блоком), но это регрессионная
    страховка, а не догадка — если условие в будущем случайно сломают,
    этот audit должен это поймать."""
    if not text:
        return False
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return False
    return paragraphs[-1] in _ALL_TRANSITIONS


def audit_text(text: str) -> list[str]:
    """Возвращает список проблем (пусто — текст чист)."""
    if not text:
        return []
    problems = []
    if check_abrupt_cutoff(text):
        problems.append("Текст обрывается на середине (обрезка без завершения мысли).")
    if check_leaked_metadata(text):
        problems.append("Утечка служебных меток источника (Announce Type / Тип объявления).")
    if check_structured_abstract_leak(text):
        problems.append("Утечка метки раздела структурированного абстракта (ЦЕЛЬ:/AIM: и т.п.).")
    if check_duplicate_long_sentence(text):
        problems.append("Один и тот же протяжённый фрагмент текста повторяется дважды.")
    if check_dangling_transition(text):
        problems.append("Переход-обещание в конце текста без содержания за ним.")
    problems.extend(EditorialCritic().check_language_is_russian(text))
    return problems


def check_title_or_lead_repeats_recent(topic: str, title: str, lead: str) -> list[str]:
    """Заголовок/лид совпадает с уже опубликованными по той же теме —
    отдельная функция (не часть audit_text): нужен доступ к БД
    (database.get_recent_titles_and_leads_by_topic), а не только к
    голому тексту поста. Проверяет, что anti-repeat в _build_title()/
    _build_lead() (editorial_engine.py) реально сработал, а не просто
    существует в коде."""
    from database.db import get_recent_titles_and_leads_by_topic

    problems: list[str] = []
    recent_titles, recent_leads = get_recent_titles_and_leads_by_topic(topic)
    if title in recent_titles:
        problems.append(f"Заголовок повторяет уже использованный для темы {topic!r}.")
    if any(lead == prev for prev in recent_leads):
        problems.append(f"Лид дословно повторяет уже использованный для темы {topic!r}.")
    return problems
