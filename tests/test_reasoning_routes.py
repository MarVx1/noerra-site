import unittest
from knowledge.reasoning import (
    ReasoningStep, ReasoningChain,
    build_reasoning_chain, chain_to_text, validate_chain,
)
from knowledge.routes import (
    RouteStep, KnowledgeRoute,
    get_route, list_routes, build_route_from_topics,
    route_to_text, suggest_route_for_topic, get_topics_from_route,
)


class TestReasoningChain(unittest.TestCase):
    def test_build_chain_with_evidence(self):
        evidence = [
            {"claim_text": "Sleep improves memory.", "url": "https://example.com/1", "confidence": 0.8, "study_type": "rct", "peer_reviewed": True},
            {"claim_text": "Sleep deprivation impairs cognition.", "url": "https://example.com/2", "confidence": 0.7, "study_type": "cohort", "peer_reviewed": True, "limitations": "Small sample"},
        ]
        consensus = {"consensus_level": "supported", "confidence": 0.85, "support_count": 5, "contradict_count": 0}

        chain = build_reasoning_chain("sleep", "Sleep improves memory", evidence, consensus)

        self.assertEqual(chain.topic, "sleep")
        self.assertEqual(len(chain.steps), 3)  # 2 evidence + 1 inference
        self.assertGreater(chain.final_confidence, 0.7)
        self.assertIn("supported", chain.conclusion.lower())

    def test_build_chain_contested(self):
        evidence = [
            {"claim_text": "Dopamine is only about pleasure.", "url": "https://example.com/1", "confidence": 0.4},
        ]
        consensus = {"consensus_level": "contested", "confidence": 0.45, "support_count": 2, "contradict_count": 4}

        chain = build_reasoning_chain("dopamine", "Dopamine claim", evidence, consensus)

        self.assertIn("contested", chain.conclusion.lower())
        self.assertLess(chain.final_confidence, 0.6)

    def test_chain_to_text(self):
        evidence = [{"claim_text": "Test claim.", "url": "https://example.com", "confidence": 0.7}]
        consensus = {"consensus_level": "supported", "confidence": 0.8, "support_count": 3, "contradict_count": 0}
        chain = build_reasoning_chain("test", "Test", evidence, consensus)

        text = chain_to_text(chain)
        self.assertIn("Reasoning Chain", text)
        self.assertIn("Evidence Trail", text)
        self.assertIn("📚", text)

    def test_validate_chain_valid(self):
        evidence = [
            {"claim_text": "Claim 1.", "url": "https://example.com/1", "confidence": 0.8},
            {"claim_text": "Claim 2.", "url": "https://example.com/2", "confidence": 0.7},
        ]
        consensus = {"consensus_level": "supported", "confidence": 0.85, "support_count": 5, "contradict_count": 0}
        chain = build_reasoning_chain("test", "Test", evidence, consensus)

        result = validate_chain(chain)
        self.assertTrue(result["valid"])
        self.assertGreaterEqual(result["step_count"], 2)

    def test_validate_chain_few_steps(self):
        chain = ReasoningChain(
            topic="test", claim_text="Test", steps=[
                ReasoningStep(step_type="evidence", description="One step", source="url", confidence=0.5),
            ],
            final_confidence=0.5, conclusion="Test", assumptions=[], limitations=[],
        )
        result = validate_chain(chain)
        self.assertFalse(result["valid"])
        self.assertTrue(any("few steps" in issue.lower() for issue in result["issues"]))


class TestKnowledgeRoutes(unittest.TestCase):
    def test_get_route_exists(self):
        route = get_route("adhd_fundamentals")
        self.assertIsNotNone(route)
        self.assertEqual(route.route_id, "adhd_fundamentals")
        self.assertGreater(len(route.steps), 0)

    def test_get_route_not_exists(self):
        route = get_route("nonexistent_route")
        self.assertIsNone(route)

    def test_list_routes(self):
        routes = list_routes()
        self.assertGreater(len(routes), 0)
        self.assertIn("id", routes[0])
        self.assertIn("title", routes[0])

    def test_build_route_from_topics(self):
        route = build_route_from_topics(["sleep", "memory", "cognition"], "Custom Route")
        self.assertEqual(route.route_id, "custom_sleep_memory_cognition")
        self.assertEqual(len(route.steps), 3)
        self.assertEqual(route.steps[0].topic, "sleep")

    def test_route_to_text(self):
        route = get_route("sleep_science")
        text = route_to_text(route)
        self.assertIn("Наука сна", text)
        self.assertIn("Шаги:", text)
        self.assertIn("⏱", text)

    def test_suggest_route_for_topic(self):
        route = suggest_route_for_topic("ADHD")
        self.assertIsNotNone(route)
        self.assertEqual(route.route_id, "adhd_fundamentals")

    def test_suggest_route_no_match(self):
        route = suggest_route_for_topic("nonexistent_topic_xyz")
        self.assertIsNone(route)

    def test_get_topics_from_route(self):
        route = get_route("sleep_science")
        topics = get_topics_from_route(route)
        self.assertIn("sleep", topics)
        self.assertIn("memory", topics)
        self.assertGreater(len(topics), 0)
        # Check uniqueness
        self.assertEqual(len(topics), len(set(topics)))


if __name__ == "__main__":
    unittest.main()
