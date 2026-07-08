import unittest
from knowledge.timeline import (
    TimelineEvent, KnowledgeTimeline,
    get_timeline, list_timelines, timeline_to_text,
    build_timeline_from_consensus, get_key_turning_points,
)


class TestTimelineTemplates(unittest.TestCase):
    def test_get_existing_timeline(self):
        timeline = get_timeline("dopamine")
        self.assertIsNotNone(timeline)
        self.assertEqual(timeline.topic, "dopamine")
        self.assertGreater(len(timeline.events), 0)

    def test_get_nonexistent_timeline(self):
        timeline = get_timeline("nonexistent")
        self.assertIsNone(timeline)

    def test_list_timelines(self):
        timelines = list_timelines()
        self.assertGreater(len(timelines), 0)
        self.assertIn("topic", timelines[0])
        self.assertIn("topic_ru", timelines[0])
        self.assertIn("events", timelines[0])

    def test_dopamine_timeline_has_events(self):
        timeline = get_timeline("dopamine")
        self.assertEqual(len(timeline.events), 5)
        self.assertEqual(timeline.events[0].event_type, "discovery")
        self.assertEqual(timeline.events[-1].event_type, "consensus")

    def test_sleep_timeline_has_events(self):
        timeline = get_timeline("sleep")
        self.assertEqual(len(timeline.events), 4)
        self.assertIn("REM", timeline.events[0].title)

    def test_adhd_timeline_has_events(self):
        timeline = get_timeline("ADHD")
        self.assertEqual(len(timeline.events), 4)
        self.assertEqual(timeline.current_consensus[:3], "СДВ")


class TestTimelineToText(unittest.TestCase):
    def test_timeline_to_text_contains_required_sections(self):
        timeline = get_timeline("dopamine")
        text = timeline_to_text(timeline)
        self.assertIn("История развития знаний", text)
        self.assertIn("Текущий консенсус", text)
        self.assertIn("Хронология", text)

    def test_timeline_to_text_contains_events(self):
        timeline = get_timeline("sleep")
        text = timeline_to_text(timeline)
        self.assertIn("1950s", text)
        self.assertIn("REM", text)

    def test_timeline_to_text_contains_major_shifts(self):
        timeline = get_timeline("dopamine")
        text = timeline_to_text(timeline)
        self.assertIn("Ключевые сдвиги", text)
        self.assertIn("1980s → 1990s", text)


class TestBuildTimelineFromConsensus(unittest.TestCase):
    def test_build_from_empty(self):
        timeline = build_timeline_from_consensus("test", "Тест", [])
        self.assertEqual(timeline.topic, "test")
        self.assertEqual(len(timeline.events), 0)

    def test_build_from_consensus_history(self):
        consensus_history = [
            {"version": 1, "consensus_level": "insufficient_data", "confidence": 0.3, "summary": "Initial.", "created_at": "2024-01-01"},
            {"version": 2, "consensus_level": "supported", "confidence": 0.8, "summary": "Confirmed.", "created_at": "2024-06-01"},
        ]
        timeline = build_timeline_from_consensus("sleep", "Сон", consensus_history)
        self.assertEqual(len(timeline.events), 2)
        self.assertEqual(timeline.events[0].event_type, "discovery")
        self.assertEqual(timeline.events[1].event_type, "confirmation")


class TestKeyTurningPoints(unittest.TestCase):
    def test_no_turning_points_stable(self):
        timeline = KnowledgeTimeline(
            topic="test",
            topic_ru="Тест",
            events=[
                TimelineEvent("e1", "discovery", "2020", "Event 1", "Desc", "test", confidence_at_time=0.5),
                TimelineEvent("e2", "confirmation", "2021", "Event 2", "Desc", "test", confidence_at_time=0.55),
                TimelineEvent("e3", "consensus", "2022", "Event 3", "Desc", "test", confidence_at_time=0.6),
            ],
        )
        turning = get_key_turning_points(timeline)
        self.assertEqual(len(turning), 0)

    def test_detect_turning_points(self):
        timeline = KnowledgeTimeline(
            topic="test",
            topic_ru="Тест",
            events=[
                TimelineEvent("e1", "discovery", "2020", "Event 1", "Desc", "test", confidence_at_time=0.3),
                TimelineEvent("e2", "confirmation", "2021", "Event 2", "Desc", "test", confidence_at_time=0.6),
                TimelineEvent("e3", "consensus", "2022", "Event 3", "Desc", "test", confidence_at_time=0.9),
            ],
        )
        turning = get_key_turning_points(timeline)
        self.assertGreater(len(turning), 0)
        self.assertEqual(turning[0].event_id, "e2")

    def test_single_event_no_turning(self):
        timeline = KnowledgeTimeline(
            topic="test",
            topic_ru="Тест",
            events=[TimelineEvent("e1", "discovery", "2020", "Event 1", "Desc", "test", confidence_at_time=0.5)],
        )
        turning = get_key_turning_points(timeline)
        self.assertEqual(len(turning), 0)


if __name__ == "__main__":
    unittest.main()
