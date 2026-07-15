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


def audit_text(text: str) -> list[str]:
    """Возвращает список проблем (пусто — текст чист)."""
    if not text:
        return []
    problems = []
    if check_abrupt_cutoff(text):
        problems.append("Текст обрывается на середине (обрезка без завершения мысли).")
    if check_leaked_metadata(text):
        problems.append("Утечка служебных меток источника (Announce Type / Тип объявления).")
    problems.extend(EditorialCritic().check_language_is_russian(text))
    return problems
