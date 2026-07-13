"""Understanding Graph: connections between concepts, claims, causes, and effects."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from collections import defaultdict


@dataclass
class GraphNode:
    node_id: str
    node_type: str  # concept, claim, cause, effect, myth, question
    label: str
    topic: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: str  # supports, contradicts, causes, leads_to, related_to, corrects
    weight: float = 1.0
    metadata: Dict = field(default_factory=dict)


@dataclass
class UnderstandingGraph:
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str, edge_type: str = None) -> List[GraphNode]:
        neighbors = []
        for edge in self.edges:
            if edge.source_id == node_id and (edge_type is None or edge.edge_type == edge_type):
                node = self.nodes.get(edge.target_id)
                if node:
                    neighbors.append(node)
            elif edge.target_id == node_id and (edge_type is None or edge.edge_type == edge_type):
                node = self.nodes.get(edge.source_id)
                if node:
                    neighbors.append(node)
        return neighbors

    def get_edges_for_node(self, node_id: str) -> List[GraphEdge]:
        return [e for e in self.edges if e.source_id == node_id or e.target_id == node_id]

    def get_subgraph_for_topic(self, topic: str) -> "UnderstandingGraph":
        sub = UnderstandingGraph()
        for node_id, node in self.nodes.items():
            if node.topic == topic:
                sub.add_node(node)
        node_ids = set(sub.nodes.keys())
        for edge in self.edges:
            if edge.source_id in node_ids and edge.target_id in node_ids:
                sub.add_edge(edge)
        return sub

    def find_path(self, start_id: str, end_id: str) -> Optional[List[str]]:
        if start_id not in self.nodes or end_id not in self.nodes:
            return None
        if start_id == end_id:
            return [start_id]

        visited: Set[str] = set()
        queue = [[start_id]]

        while queue:
            path = queue.pop(0)
            node_id = path[-1]
            if node_id in visited:
                continue
            visited.add(node_id)

            for edge in self.edges:
                neighbor = None
                if edge.source_id == node_id:
                    neighbor = edge.target_id
                elif edge.target_id == node_id:
                    neighbor = edge.source_id

                if neighbor and neighbor not in visited:
                    new_path = path + [neighbor]
                    if neighbor == end_id:
                        return new_path
                    queue.append(new_path)

        return None

    def get_concept_map(self, topic: str) -> Dict[str, List[str]]:
        """Return adjacency map for concepts in a topic."""
        sub = self.get_subgraph_for_topic(topic)
        adj: Dict[str, List[str]] = defaultdict(list)
        for edge in sub.edges:
            adj[edge.source_id].append(edge.target_id)
            adj[edge.target_id].append(edge.source_id)
        return dict(adj)

    def get_central_nodes(self, topic: str, top_n: int = 5) -> List[GraphNode]:
        """Find most connected nodes in a topic subgraph."""
        sub = self.get_subgraph_for_topic(topic)
        degree: Dict[str, int] = defaultdict(int)
        for edge in sub.edges:
            degree[edge.source_id] += 1
            degree[edge.target_id] += 1

        sorted_ids = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:top_n]
        return [sub.nodes[nid] for nid, _ in sorted_ids if nid in sub.nodes]


def build_graph_from_claims(
    topic: str,
    claims: List[Dict],
    consensus: List[Dict],
    myths: List[str] = None,
    open_questions: List[str] = None,
) -> UnderstandingGraph:
    graph = UnderstandingGraph()
    myths = myths or []
    open_questions = open_questions or []

    for claim in claims:
        claim_id = f"claim_{claim.get('id', '')}"
        graph.add_node(GraphNode(
            node_id=claim_id,
            node_type="claim",
            label=claim.get("claim_text", "")[:100],
            topic=topic,
        ))

        for cs in consensus:
            if cs.get("claim_id") == claim.get("id"):
                cs_id = f"consensus_{cs.get('id', '')}"
                graph.add_node(GraphNode(
                    node_id=cs_id,
                    node_type="consensus",
                    label=cs.get("consensus_level", "unknown"),
                    topic=topic,
                ))
                graph.add_edge(GraphEdge(
                    source_id=claim_id,
                    target_id=cs_id,
                    edge_type="has_consensus",
                    weight=float(cs.get("confidence", 0.5)),
                ))
                break

    for i, myth_text in enumerate(myths):
        myth_id = f"myth_{topic}_{i}"
        graph.add_node(GraphNode(
            node_id=myth_id,
            node_type="myth",
            label=myth_text[:100],
            topic=topic,
        ))
        # Link myth to closest claim
        for claim in claims[:1]:
            claim_id = f"claim_{claim.get('id', '')}"
            graph.add_edge(GraphEdge(
                source_id=myth_id,
                target_id=claim_id,
                edge_type="corrects",
                weight=0.8,
            ))

    for i, question in enumerate(open_questions):
        q_id = f"question_{topic}_{i}"
        graph.add_node(GraphNode(
            node_id=q_id,
            node_type="question",
            label=question[:100],
            topic=topic,
        ))

    return graph


def graph_to_text(graph: UnderstandingGraph, topic: str = None) -> str:
    """Convert graph to human-readable text."""
    if topic:
        graph = graph.get_subgraph_for_topic(topic)

    lines = [f"\U0001f578 <b>Understanding Graph</b> ({len(graph.nodes)} nodes, {len(graph.edges)} edges)\n"]

    type_groups: Dict[str, List[GraphNode]] = defaultdict(list)
    for node in graph.nodes.values():
        type_groups[node.node_type].append(node)

    type_labels = {
        "claim": "Утверждения",
        "consensus": "Консенсус",
        "myth": "Мифы",
        "question": "Открытые вопросы",
        "concept": "Концепции",
        "cause": "Причины",
        "effect": "Следствия",
    }

    for node_type, label in type_labels.items():
        nodes = type_groups.get(node_type, [])
        if nodes:
            lines.append(f"<b>{label}:</b>")
            for node in nodes[:5]:
                lines.append(f"  \u2022 {node.label}")
            if len(nodes) > 5:
                lines.append(f"  ... и ещё {len(nodes) - 5}")
            lines.append("")

    if graph.edges:
        lines.append(f"<b>Связи:</b> {len(graph.edges)}")

    return "\n".join(lines)
