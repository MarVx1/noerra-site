# ============================================================
#  tests/test_regression_corpus.py — постоянный регрессионный корпус
#  (дополнение №2 к ТЗ "редакционное качество", п.2.4).
#
#  Реальные абстракты (не выдуманные) статей, каждая из которых была
#  источником конкретного, найденного на живых данных дефекта в ходе
#  вычитки/батч-аудита 2026-07-15. Раньше баг чинился и забывался —
#  здесь он остаётся закреплённым тестом, чтобы будущие правки не
#  могли тихо его вернуть. Текст скопирован из noerra.db на момент
#  написания (не зависит от живой БД/сети — детерминирован).
# ============================================================

import unittest

from parsers.base import RawArticle
from adaptation.editorial_engine import EditorialEngine
from adaptation.content_audit import audit_text, check_duplicate_long_sentence


def _generate(title: str, abstract: str, topic: str, source: str) -> tuple[dict, str]:
    engine = EditorialEngine()
    article = RawArticle(title=title, url="https://example.com/regression", abstract=abstract, source=source)
    passport = engine.analyze(article, topic)
    structure = engine.build_structure(passport)
    text = engine.generate_text(passport, structure)
    return passport, text


class TestRegressionCorpus(unittest.TestCase):
    def test_article_634_no_structured_abstract_label_leak(self):
        """Живая публикация 'СДВГ: свежие данные' — PubMed-абстракт с
        меткой "AIM:" СПЛОШНЫМИ ЗАГЛАВНЫМИ, дошедшей до поста как
        'ЦЕЛЬ: Этот обзор...' (2026-07-15). Корень — _SECTION_LABEL_RE
        не матчил ALL CAPS, список меток был в Title Case."""
        _, text = _generate(
            title="Roles and impacts of pharmacists in attention-deficit hyperactivity disorder services: a scoping review.",
            abstract=(
                "Demand for attention-deficit hyperactivity disorder (ADHD) services has increased substantially "
                "across health systems, placing pressure on specialist services and contributing to prolonged "
                "waiting times and inconsistent medication monitoring. Pharmacists have established expertise in "
                "medicines optimisation and, in some settings, are authorised to prescribe. Yet their role within "
                "ADHD care pathways remains poorly characterised. AIM: This scoping review aims to map the existing "
                "empirical evidence on pharmacist involvement in ADHD services, synthesise reported roles and "
                "impacts, and identify key evidence gaps to inform future research and service development. "
                "A scoping review was conducted in accordance with the Arksey and O'Malley framework."
            ),
            topic="ADHD", source="pubmed",
        )
        self.assertNotIn("ЦЕЛЬ", text)
        self.assertNotIn("AIM", text)
        self.assertEqual(audit_text(text), [])

    def test_article_552_no_structured_label_and_no_false_positive_on_practical_opener(self):
        """Систематический обзор про музыку и тревожность у подростков —
        глеенные метки "BackgroundAdolescence"/"MethodsThis"/"ResultsAcross"/
        "ConclusionMusic" (без пробела/двоеточия) плюс регрессия: первый
        вариант фикса (граница \\b) ложно резал собственный шаблон
        "Практический вывод:" — тут же проверяем, что этого больше нет."""
        _, text = _generate(
            title="Effect of music on anxiety among adolescents: a systematic review",
            abstract=(
                "BackgroundAdolescence is a developmental period marked by heightened vulnerability to anxiety, "
                "driven by academic pressure, social expectations, and rapid emotional changes. Music-based "
                "interventions have been examined as accessible, low-risk approaches for anxiety reduction; "
                "however, existing evidence remains conceptually fragmented and methodologically diverse."
                "MethodsThis systematic review followed PRISMA 2020 guidelines. Twenty studies met the inclusion "
                "criteria. ResultsAcross 1,912 adolescents aged 12-18, most studies reported reductions in anxiety "
                "following music-based interventions. ConclusionMusic-based interventions appear beneficial for "
                "reducing anxiety among adolescents in both school and clinical contexts."
            ),
            topic="anxiety", source="frontiers",
        )
        # Практический блок случаен по формулировке (PRACTICAL_OPENERS,
        # см. editorial_engine.py) — "Практический вывод:" лишь один из
        # трёх вариантов, поэтому здесь не проверяем конкретную фразу
        # (детерминированная проверка именно на неё — в
        # test_adaptation_utils.py:test_does_not_touch_own_practical_opener_template).
        # Здесь важно только общее отсутствие утечки меток раздела.
        self.assertEqual(audit_text(text), [])

    def test_article_534_finding_aware_question_does_not_restate_lead_verbatim(self):
        """Реальная публикация про социальных роботов и iCBT — короткая
        находка без реальной точки обрезки: вопрос-заголовок дословно
        повторял всё предложение лида целиком (2026-07-15)."""
        passport, text = _generate(
            title="Examining the Potential of Social Robots to Increase Adherence in Internet-based CBT.",
            abstract=(
                "Internet-based applications of Cognitive Behavioral Therapy (iCBT) are promising to alleviate "
                "mood problems and depression. However, versions without personal support still fall short in "
                "establishing meaningful therapeutic relationships. Overall, results showed the social robot "
                "intervention to increase therapeutic alliance, adherence, and satisfaction compared to the same "
                "screen-based intervention, with alliance in a mediating role, but did not significantly improve "
                "participants' mood."
            ),
            topic="psychology", source="pubmed",
        )
        self.assertFalse(check_duplicate_long_sentence(text))
        self.assertNotIn("«", passport["reader_question"])

    def test_article_604_short_finding_falls_back_to_generic_question(self):
        """Тот же класс дефекта, что и 534 (короткая находка без точки
        обрезки) — на другой статье, тема 'стресс'."""
        _, text = _generate(
            title="Stress and resilience: cortisol hypo-response to acute stress in non-resilient individuals.",
            abstract=(
                "Resilience is a dynamic construct referring to the preservation or quick recovery of mental "
                "health in the face of significant stressors. Despite the crucial role of the acute stress "
                "response in coping with adversity, no consensus exists regarding its relationship with "
                "resilience. Inconsistent findings may be due to variability in the assessment of resilience."
            ),
            topic="stress", source="pubmed",
        )
        self.assertFalse(check_duplicate_long_sentence(text))

    def test_article_389_partial_quote_overlap_is_a_known_accepted_case(self):
        """Пограничный случай, оставленный осознанно: находка достаточно
        длинная, обрезка по запятой реально сработала (~40% исходной
        находки остаётся), но обрезанный фрагмент всё ещё >= 8 слов и
        технически повторяется в лиде и в цитате вопроса. Это НЕ
        подавляется (иначе finding-aware вопрос гаснет почти для всех
        статей — см. историю правки reader_question.py, 2026-07-15) —
        тест фиксирует осознанное решение, а не забытый баг: если
        поведение когда-нибудь изменится, тест явно об этом сообщит."""
        passport, text = _generate(
            title=(
                "High-Intensity Virtual Reality Exergaming for Adolescents With "
                "Attention-Deficit/Hyperactivity Disorder: Protocol for a Randomized Clinical Trial."
            ),
            abstract=(
                "Attention-deficit/hyperactivity disorder (ADHD) is a prevalent neurodevelopmental condition "
                "affecting approximately 7% to 8% of children and adolescents, characterized by persistent "
                "inattention, hyperactivity, and impulsivity. Adolescence represents a period of heightened "
                "vulnerability, during which pharmacological treatments are frequently limited by adverse "
                "effects, suboptimal adherence, and partial response. Physical exercise, particularly "
                "high-intensity interval training (HIIT), has demonstrated superior effects on inhibitory "
                "control and inattention compared with moderate-intensity continuous exercise. However, the "
                "repetitive nature and high perceived exertion of traditional HIIT protocols result in poor "
                "adherence, especially in individuals with ADHD. Virtual reality (VR)-based exergames have "
                "been proposed as a strategy to sustain vigorous physiological demands while maintaining "
                "intrinsic motivation. This paper presents the protocol for a randomized clinical trial "
                "designed to evaluate whether an HIIT-based VR exergame produces greater improvements in "
                "inhibitory control and inattention symptoms compared with an active, nonexercise VR control "
                "condition in adolescents with ADHD."
            ),
            topic="ADHD", source="pubmed",
        )
        self.assertTrue(check_duplicate_long_sentence(text))
        # finding-aware вопрос сохранён, не подавлен (не откатился на
        # generic) — проверяем по содержанию находки, не по кавычкам:
        # из 3 шаблонов FINDING_QUESTION_PATTERNS["discovery"] кавычки
        # «» использует только один, выбор шаблона случаен (_pick).
        self.assertIn("нервной системы", passport["reader_question"])

    def test_article_511_scoping_review_gets_significance_frame_and_clean_review_wording(self):
        """Article id=511 — исходный пример из первого раунда ТЗ:
        'обзорный обзор' (scoping->обзорный, review->обзор — тавтология
        от Google Translate) и отсутствие рамки значимости для короткого
        review-абстракта. Оба уже чинились раньше — здесь закреплено,
        чтобы не вернулись."""
        _, text = _generate(
            title="Neuroplasticity and Neural Adaptations in Singing Voice Skill Learning: A Scoping Review.",
            abstract=(
                "This scoping review aimed to map and characterize the available evidence on neural adaptations "
                "associated with singing expertise, with a focus on experience-dependent neuroplasticity "
                "underlying vocal motor control. This scoping review was conducted in accordance with the "
                "PRISMA-ScR guidelines. Two reviewers independently screened studies, with disagreements resolved "
                "by a third reviewer. Data were extracted and synthesized descriptively."
            ),
            topic="neuroplasticity", source="pubmed",
        )
        self.assertNotIn("обзорный обзор", text.lower())
        has_significance = any(
            marker in text for marker in
            ("Это лабораторное исследование", "Прямого применения", "Такие фундаментальные результаты")
        )
        has_practical = "Практический вывод" in text or "На практике это означает" in text
        self.assertTrue(has_significance or has_practical)

    def test_article_588_colon_introduced_list_does_not_truncate_mid_item(self):
        """Опубликованный пост 'СДВГ: чего мы раньше не знали' — обрезка
        находки по первой запятой рвала мысль посреди первого элемента
        перечисления после двоеточия ('...вопросов: факторы')."""
        passport, _ = _generate(
            title="The increasing use of cognitive enhancing drugs by those with ADHD and neurotypical individuals.",
            abstract=(
                "Attention deficit hyperactivity disorder (ADHD) is a highly heritable neurodevelopmental "
                "condition. This review examines five key issues: factors driving rising ADHD diagnoses and "
                "prescriptions; the cognitive profile of ADHD and mechanisms of pharmacological treatments; "
                "reasons for increasing cognitive enhancer use in neurotypical populations."
            ),
            topic="ADHD", source="pubmed",
        )
        self.assertNotIn(": факторы»", passport["reader_question"])
        self.assertNotIn(": factors»", passport["reader_question"])

    def test_article_398_clause_boundary_cut_not_mid_verb(self):
        """article id=398 — обрезка по числу слов (без учёта границы
        клаузы) обрывала на середине глагола без дополнения."""
        passport, _ = _generate(
            title="Imputation-free transformer learning enables robust Alzheimer's disease prediction.",
            abstract=(
                "Accurate diagnostic classification and disease-severity prediction for Alzheimer's disease are "
                "hampered by the incompleteness and heterogeneity of real-world clinical data. Left unaddressed, "
                "these barriers prevent reliable disease modelling and hinder effective clinical evaluation."
            ),
            topic="cognition", source="arxiv",
        )
        self.assertTrue(passport["reader_question"].strip().endswith("?"))

    def test_article_483_jargon_glossary_annotates_methodology_terms(self):
        """article id=483 — исходный пример: необъяснённый методологический
        жаргон (тесты на грызунах) в теле статьи."""
        _, text = _generate(
            title="Sex-specific role of body weight in mediating stress susceptibility through MeA Tac2-Nk3R signaling.",
            abstract=(
                "We found that two-week social isolation during adolescence induced depressive-like behaviors "
                "in the sucrose preference test, forced swimming test and social interaction test, and "
                "anxiety-like behaviors in the elevated plus maze, novelty suppressed feeding test and open "
                "field test in female but not male mice."
            ),
            topic="stress", source="pubmed",
        )
        self.assertIn("(", text)  # хотя бы один термин аннотирован


if __name__ == "__main__":
    unittest.main()
