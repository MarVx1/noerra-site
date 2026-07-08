import unittest
from unittest.mock import patch, MagicMock
from knowledge.audit import (
    TopicAudit, ConfidenceDrift,
    audit_topic, audit_all_topics,
    detect_stale_topics, detect_contradicted_topics,
    track_confidence_drift, detect_knowledge_debt,
    _build_recommendation,
)


class TestRecommendationBuilder(unittest.TestCase):
    def test_stale_topic(self):
        rec = _build_recommendation(True, False, 5, 0.7, 2)
        self.assertIn("stale", rec.lower())

    def test_contradictions(self):
        rec = _build_recommendation(False, True, 5, 0.7, 2)
        self.assertIn("Contradictions", rec)

    def test_no_claims(self):
        rec = _build_recommendation(False, False, 0, 0.0, 0)
        self.assertIn("No claims", rec)

    def test_low_confidence(self):
        rec = _build_recommendation(False, False, 5, 0.3, 2)
        self.assertIn("Low", rec)

    def test_many_questions(self):
        rec = _build_recommendation(False, False, 5, 0.7, 8)
        self.assertIn("open questions", rec.lower())

    def test_good_shape(self):
        rec = _build_recommendation(False, False, 5, 0.8, 2)
        self.assertIn("good shape", rec.lower())


class TestAuditTopic(unittest.TestCase):
    @patch("knowledge.audit.db")
    def test_audit_empty_topic(self, mock_db):
        mock_db.get_claims_for_topic.return_value = []
        mock_db.get_consensus_for_topic.return_value = []
        mock_db.get_open_questions.return_value = []
        mock_db.get_myths.return_value = []
        mock_db.get_latest_knowledge_version.return_value = None

        audit = audit_topic("sleep")
        self.assertEqual(audit.topic, "sleep")
        self.assertEqual(audit.claims_count, 0)
        self.assertTrue(audit.is_stale)
        self.assertEqual(audit.consensus_level, "insufficient_data")

    @patch("knowledge.audit.db")
    def test_audit_with_data(self, mock_db):
        mock_db.get_claims_for_topic.return_value = [
            {"id": 1, "claim_text": "Sleep improves memory.", "consensus_level": "supported"},
            {"id": 2, "claim_text": "Sleep affects mood.", "consensus_level": "contested"},
        ]
        mock_db.get_consensus_for_topic.return_value = [
            {"consensus_level": "supported", "confidence": 0.8, "contradict_count": 0, "claim_id": 1, "version": 1},
            {"consensus_level": "contested", "confidence": 0.4, "contradict_count": 2, "claim_id": 2, "version": 1},
        ]
        mock_db.get_open_questions.return_value = [{"question": "Does timing matter?"}]
        mock_db.get_myths.return_value = [{"myth_text": "Sleep is only rest."}]
        mock_db.get_latest_knowledge_version.return_value = {"created_at": "2025-01-01 10:00:00"}

        audit = audit_topic("sleep", stale_days=365)
        self.assertEqual(audit.claims_count, 2)
        self.assertTrue(audit.has_contradictions)
        self.assertEqual(audit.open_questions_count, 1)
        self.assertEqual(audit.myths_count, 1)

    @patch("knowledge.audit.db")
    def test_audit_all_topics(self, mock_db):
        mock_db.execute_query.return_value = [{"topic": "sleep"}, {"topic": "dopamine"}]
        mock_db.get_claims_for_topic.return_value = []
        mock_db.get_consensus_for_topic.return_value = []
        mock_db.get_open_questions.return_value = []
        mock_db.get_myths.return_value = []
        mock_db.get_latest_knowledge_version.return_value = None

        audits = audit_all_topics()
        self.assertEqual(len(audits), 2)
        self.assertEqual(audits[0].topic, "sleep")

    @patch("knowledge.audit.db")
    def test_detect_stale_topics(self, mock_db):
        mock_db.execute_query.return_value = [{"topic": "sleep"}]
        mock_db.get_claims_for_topic.return_value = []
        mock_db.get_consensus_for_topic.return_value = []
        mock_db.get_open_questions.return_value = []
        mock_db.get_myths.return_value = []
        mock_db.get_latest_knowledge_version.return_value = None

        stale = detect_stale_topics(stale_days=30)
        self.assertIn("sleep", stale)

    @patch("knowledge.audit.db")
    def test_detect_contradicted_topics(self, mock_db):
        mock_db.execute_query.return_value = [{"topic": "dopamine"}]
        mock_db.get_claims_for_topic.return_value = [{"id": 1, "claim_text": "Test."}]
        mock_db.get_consensus_for_topic.return_value = [
            {"consensus_level": "contested", "confidence": 0.4, "contradict_count": 3, "claim_id": 1, "version": 1},
        ]
        mock_db.get_open_questions.return_value = []
        mock_db.get_myths.return_value = []
        mock_db.get_latest_knowledge_version.return_value = {"created_at": "2099-01-01 10:00:00"}

        contradicted = detect_contradicted_topics()
        self.assertIn("dopamine", contradicted)


class TestConfidenceDrift(unittest.TestCase):
    @patch("knowledge.audit.db")
    def test_drift_decreased(self, mock_db):
        mock_db.get_consensus_for_topic.return_value = [
            {"claim_id": 1, "confidence": 0.8, "version": 1},
            {"claim_id": 1, "confidence": 0.5, "version": 2},
        ]
        mock_db.get_claims_for_topic.return_value = [
            {"id": 1, "claim_text": "Sleep improves memory."},
        ]

        drifts = track_confidence_drift("sleep")
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0].direction, "decreased")
        self.assertLess(drifts[0].delta, 0)

    @patch("knowledge.audit.db")
    def test_drift_increased(self, mock_db):
        mock_db.get_consensus_for_topic.return_value = [
            {"claim_id": 1, "confidence": 0.3, "version": 1},
            {"claim_id": 1, "confidence": 0.7, "version": 2},
        ]
        mock_db.get_claims_for_topic.return_value = [
            {"id": 1, "claim_text": "Dopamine affects motivation."},
        ]

        drifts = track_confidence_drift("dopamine")
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0].direction, "increased")

    @patch("knowledge.audit.db")
    def test_drift_stable(self, mock_db):
        mock_db.get_consensus_for_topic.return_value = [
            {"claim_id": 1, "confidence": 0.6, "version": 1},
            {"claim_id": 1, "confidence": 0.62, "version": 2},
        ]
        mock_db.get_claims_for_topic.return_value = [
            {"id": 1, "claim_text": "Stress affects health."},
        ]

        drifts = track_confidence_drift("stress")
        self.assertEqual(len(drifts), 1)
        self.assertEqual(drifts[0].direction, "stable")

    @patch("knowledge.audit.db")
    def test_no_drift_with_one_state(self, mock_db):
        mock_db.get_consensus_for_topic.return_value = [
            {"claim_id": 1, "confidence": 0.5, "version": 1},
        ]
        mock_db.get_claims_for_topic.return_value = []

        drifts = track_confidence_drift("sleep")
        self.assertEqual(len(drifts), 0)


class TestKnowledgeDebt(unittest.TestCase):
    @patch("knowledge.audit.db")
    def test_detect_debt(self, mock_db):
        mock_db.execute_query.return_value = [{"topic": "sleep", "cnt": 5}]
        mock_db.get_latest_knowledge_version.return_value = None

        debt = detect_knowledge_debt(stale_days=30)
        self.assertEqual(len(debt), 1)
        self.assertEqual(debt[0]["topic"], "sleep")
        self.assertEqual(debt[0]["new_articles"], 5)

    @patch("knowledge.audit.db")
    def test_no_debt_when_recent_update(self, mock_db):
        mock_db.execute_query.return_value = [{"topic": "sleep", "cnt": 5}]
        mock_db.get_latest_knowledge_version.return_value = {"created_at": "2099-01-01 10:00:00"}
        mock_db.get_conn.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {"diff": 1.0}

        debt = detect_knowledge_debt(stale_days=30)
        self.assertEqual(len(debt), 0)


if __name__ == "__main__":
    unittest.main()
