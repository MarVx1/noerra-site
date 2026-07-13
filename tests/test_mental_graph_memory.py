import unittest
from domain.knowledge.mental_models import (
    MentalModel, get_mental_model, list_mental_models,
    model_to_text, get_model_brief,
)
from domain.knowledge.graph import (
    GraphNode, GraphEdge, UnderstandingGraph,
    build_graph_from_claims, graph_to_text,
)
from domain.knowledge.editorial_memory import (
    EditorialDecision, Pattern, EditorialMemory,
    build_editorial_memory, memory_to_text,
)


class TestMentalModels(unittest.TestCase):
    def test_get_existing_model(self):
        model = get_mental_model("dopamine")
        self.assertIsNotNone(model)
        self.assertIn("prediction", model.correct_understanding.lower())

    def test_get_nonexistent_model(self):
        model = get_mental_model("nonexistent")
        self.assertIsNone(model)

    def test_list_models(self):
        models = list_mental_models()
        self.assertGreater(len(models), 0)
        self.assertIn("topic", models[0])
        self.assertIn("title", models[0])

    def test_model_to_text(self):
        model = get_mental_model("sleep")
        text = model_to_text(model)
        self.assertIn("Модель понимания", text)
        self.assertIn("Правильное понимание", text)
        self.assertIn("заблуждение", text.lower())

    def test_get_model_brief(self):
        brief = get_model_brief("dopamine")
        self.assertIn("Как это понимать", brief)

    def test_get_model_brief_empty(self):
        brief = get_model_brief("nonexistent")
        self.assertEqual(brief, "")


class TestUnderstandingGraph(unittest.TestCase):
    def test_add_and_get_node(self):
        graph = UnderstandingGraph()
        graph.add_node(GraphNode("n1", "claim", "Test claim", "sleep"))
        node = graph.get_node("n1")
        self.assertIsNotNone(node)
        self.assertEqual(node.label, "Test claim")

    def test_add_edge_and_neighbors(self):
        graph = UnderstandingGraph()
        graph.add_node(GraphNode("n1", "claim", "Claim 1", "sleep"))
        graph.add_node(GraphNode("n2", "consensus", "supported", "sleep"))
        graph.add_edge(GraphEdge("n1", "n2", "has_consensus"))
        neighbors = graph.get_neighbors("n1")
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0].node_id, "n2")

    def test_subgraph_for_topic(self):
        graph = UnderstandingGraph()
        graph.add_node(GraphNode("n1", "claim", "Claim 1", "sleep"))
        graph.add_node(GraphNode("n2", "claim", "Claim 2", "dopamine"))
        sub = graph.get_subgraph_for_topic("sleep")
        self.assertEqual(len(sub.nodes), 1)

    def test_find_path(self):
        graph = UnderstandingGraph()
        for i in range(4):
            graph.add_node(GraphNode(f"n{i}", "concept", f"Node {i}", "test"))
        graph.add_edge(GraphEdge("n0", "n1", "related_to"))
        graph.add_edge(GraphEdge("n1", "n2", "related_to"))
        graph.add_edge(GraphEdge("n2", "n3", "related_to"))
        path = graph.find_path("n0", "n3")
        self.assertIsNotNone(path)
        self.assertEqual(path[0], "n0")
        self.assertEqual(path[-1], "n3")

    def test_find_path_no_connection(self):
        graph = UnderstandingGraph()
        graph.add_node(GraphNode("n0", "concept", "Node 0", "test"))
        graph.add_node(GraphNode("n1", "concept", "Node 1", "test"))
        path = graph.find_path("n0", "n1")
        self.assertIsNone(path)

    def test_build_graph_from_claims(self):
        claims = [
            {"id": 1, "claim_text": "Sleep improves memory."},
            {"id": 2, "claim_text": "Sleep affects mood."},
        ]
        consensus = [
            {"id": 1, "claim_id": 1, "consensus_level": "supported", "confidence": 0.8},
            {"id": 2, "claim_id": 2, "consensus_level": "contested", "confidence": 0.4},
        ]
        myths = ["Sleep is only rest."]
        questions = ["Does sleep timing matter?"]

        graph = build_graph_from_claims("sleep", claims, consensus, myths, questions)
        self.assertGreater(len(graph.nodes), 4)  # 2 claims + 2 consensus + 1 myth + 1 question
        self.assertGreater(len(graph.edges), 0)

    def test_graph_to_text(self):
        claims = [{"id": 1, "claim_text": "Test claim."}]
        consensus = [{"id": 1, "claim_id": 1, "consensus_level": "supported", "confidence": 0.8}]
        graph = build_graph_from_claims("test", claims, consensus)
        text = graph_to_text(graph, "test")
        self.assertIn("Understanding Graph", text)
        self.assertIn("Утверждения", text)

    def test_central_nodes(self):
        graph = UnderstandingGraph()
        graph.add_node(GraphNode("center", "claim", "Central", "test"))
        for i in range(5):
            graph.add_node(GraphNode(f"n{i}", "concept", f"Node {i}", "test"))
            graph.add_edge(GraphEdge("center", f"n{i}", "related_to"))
        central = graph.get_central_nodes("test", top_n=1)
        self.assertEqual(len(central), 1)
        self.assertEqual(central[0].node_id, "center")


class TestEditorialMemory(unittest.TestCase):
    def test_add_decision(self):
        memory = EditorialMemory()
        memory.add_decision(EditorialDecision(
            draft_id=1, article_id=10, topic="sleep",
            decision="approved", reason="good quality",
            editor_id="123", timestamp="2025-01-01",
        ))
        self.assertEqual(len(memory.decisions), 1)

    def test_analyze_patterns_rejection(self):
        memory = EditorialMemory()
        for i in range(3):
            memory.add_decision(EditorialDecision(
                draft_id=i, article_id=i, topic="sleep",
                decision="rejected", reason="weak_study",
                editor_id="123", timestamp="2025-01-01",
            ))
        patterns = memory.analyze_patterns()
        self.assertGreater(len(patterns), 0)
        self.assertTrue(any("отклонения" in p.description.lower() or "rejection" in p.pattern_type for p in patterns))

    def test_analyze_patterns_topic_trend(self):
        memory = EditorialMemory()
        for i in range(6):
            memory.add_decision(EditorialDecision(
                draft_id=i, article_id=i, topic="dopamine",
                decision="approved", reason="good",
                editor_id="123", timestamp="2025-01-01",
            ))
        patterns = memory.analyze_patterns()
        trend = [p for p in patterns if p.pattern_type == "topic_trend"]
        self.assertGreater(len(trend), 0)

    def test_statistics(self):
        memory = EditorialMemory()
        memory.add_decision(EditorialDecision(
            draft_id=1, article_id=1, topic="sleep",
            decision="approved", reason="", editor_id="1", timestamp="",
        ))
        memory.add_decision(EditorialDecision(
            draft_id=2, article_id=2, topic="sleep",
            decision="rejected", reason="", editor_id="1", timestamp="",
        ))
        stats = memory.get_statistics()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertAlmostEqual(stats["approval_rate"], 0.5)

    def test_statistics_empty(self):
        memory = EditorialMemory()
        stats = memory.get_statistics()
        self.assertEqual(stats["total"], 0)

    def test_build_from_dicts(self):
        decisions = [
            {"draft_id": 1, "article_id": 10, "topic": "sleep",
             "decision": "approved", "reason": "good", "editor": "123", "created_at": "2025-01-01"},
        ]
        memory = build_editorial_memory(decisions)
        self.assertEqual(len(memory.decisions), 1)

    def test_memory_to_text(self):
        memory = EditorialMemory()
        memory.add_decision(EditorialDecision(
            draft_id=1, article_id=1, topic="sleep",
            decision="approved", reason="good", editor_id="1", timestamp="2025-01-01",
        ))
        memory.analyze_patterns()
        text = memory_to_text(memory)
        self.assertIn("Editorial Memory", text)
        self.assertIn("Всего решений", text)


if __name__ == "__main__":
    unittest.main()
