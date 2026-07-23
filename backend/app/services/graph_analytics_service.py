"""Neo4j Graph Data Science integration: projections + PageRank, WCC, Louvain, betweenness,
and node similarity over the account transaction network.

Why these algorithms, specifically:

* **PageRank** -- surfaces accounts that are structurally central to money flow (many/heavy
  incoming transfers from other well-connected accounts). A high score is a *prioritization*
  signal for investigators, not evidence of fraud by itself -- a busy legitimate merchant
  settlement account can rank just as high as a laundering hub. Documented, not asserted.
* **Weakly Connected Components (WCC)** -- finds the disconnected "islands" of the transaction
  graph. Useful to confirm a suspected ring is actually isolated from the rest of the network
  (or, more often, that it isn't -- most accounts end up in one giant component).
* **Louvain** -- community detection is what FD-010 ("suspicious community") consumes: it
  writes `Account.community_id`, and a community becomes suspicious when it contains a
  confirmed-fraud member (see `investigation_repository.find_suspicious_communities`).
* **Betweenness centrality** -- identifies accounts that sit *between* otherwise-separate
  clusters (bridge/mule-like structural position), which is a different signal from PageRank's
  "receives a lot" -- betweenness is expensive (all-pairs shortest paths), so it's run last and
  only if explicitly requested.
* **Node similarity** -- finds customers who look alike by shared device/IP/merchant usage,
  surfaced as investigation evidence (not written back to the graph) for "who else looks like
  this confirmed fraud customer."

Projection management: the account-transaction network isn't a *stored* relationship (accounts
connect only via intermediate Transaction nodes, see docs/graph-model.md for why), so it's
projected with a Cypher relationship query that aggregates FROM_ACCOUNT/TO_ACCOUNT pairs into a
weighted Account-to-Account edge. Every projection is dropped in a `finally` block -- GDS graphs
live in server memory and leaking them across runs would eventually exhaust it.
"""

from __future__ import annotations

import logging
from typing import Any

from graphdatascience import GraphDataScience

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.graph_analytics")

ACCOUNT_NETWORK_GRAPH = "account-transaction-network"
CUSTOMER_SHARED_ENTITY_GRAPH = "customer-shared-entity-network"

_ACCOUNT_NODE_QUERY = "MATCH (a:Account) RETURN id(a) AS id"
_ACCOUNT_REL_QUERY = """
MATCH (a:Account)<-[:FROM_ACCOUNT]-(t:Transaction)-[:TO_ACCOUNT]->(b:Account)
RETURN id(a) AS source, id(b) AS target, count(t) AS weight
"""


class GraphAnalyticsService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._gds = GraphDataScience(
            self._settings.neo4j_uri,
            auth=(self._settings.neo4j_user, self._settings.neo4j_password),
        )

    def close(self) -> None:
        self._gds.close()

    # ------------------------------------------------------------------
    # Projection lifecycle
    # ------------------------------------------------------------------

    def _drop_if_exists(self, name: str) -> None:
        if self._gds.graph.exists(name)["exists"]:
            self._gds.graph.get(name).drop()

    def _project_account_network(self) -> tuple[Any, dict[str, Any]]:
        """Project: nodes=Account, relationships=aggregated Transaction-mediated transfers.

        Orientation NATURAL (source -> target as money flows); weight = number of transfers
        between the pair, used by PageRank as `relationshipWeightProperty` so accounts connected
        by many transfers count for more than a single incidental one.
        """
        self._drop_if_exists(ACCOUNT_NETWORK_GRAPH)
        graph, result = self._gds.graph.project.cypher(ACCOUNT_NETWORK_GRAPH, _ACCOUNT_NODE_QUERY, _ACCOUNT_REL_QUERY)
        logger.info(
            "projected graph=%s nodes=%d relationships=%d",
            ACCOUNT_NETWORK_GRAPH,
            result["nodeCount"],
            result["relationshipCount"],
        )
        return graph, result

    # ------------------------------------------------------------------
    # Algorithms
    # ------------------------------------------------------------------

    def run_pagerank(self, graph: Any) -> dict[str, Any]:
        result = self._gds.pageRank.write(graph, writeProperty="pagerank_score", relationshipWeightProperty="weight")
        return {"ran_iterations": result["ranIterations"], "did_converge": bool(result["didConverge"])}

    def run_wcc(self, graph: Any) -> dict[str, Any]:
        result = self._gds.wcc.write(graph, writeProperty="wcc_component")
        return {"component_count": result["componentCount"]}

    def run_louvain(self, graph: Any) -> dict[str, Any]:
        """Writes `Account.community_id` -- consumed directly by fraud rule FD-010."""
        result = self._gds.louvain.write(graph, writeProperty="community_id")
        return {"community_count": result["communityCount"], "modularity": result["modularity"]}

    def run_betweenness(self, graph: Any) -> dict[str, Any]:
        """All-pairs-shortest-paths based -- the most expensive algorithm here, run on demand only."""
        result = self._gds.betweenness.write(graph, writeProperty="betweenness_score")
        distribution = result["centralityDistribution"]
        return {"min_score": distribution.get("min"), "max_score": distribution.get("max")}

    def run_node_similarity_for_devices(self, top_k: int = 10, similarity_cutoff: float = 0.3) -> list[dict[str, Any]]:
        """Customers who look alike by shared device usage -- returned as evidence, not written back.

        Projects a bipartite Customer-Device graph and runs nodeSimilarity in `stream` mode
        (no write) since "customers similar to this one" is investigation-time evidence, not a
        durable property every customer needs stored.
        """
        self._drop_if_exists(CUSTOMER_SHARED_ENTITY_GRAPH)
        graph, _ = self._gds.graph.project.cypher(
            CUSTOMER_SHARED_ENTITY_GRAPH,
            "MATCH (n) WHERE n:Customer OR n:Device RETURN id(n) AS id, labels(n) AS labels",
            "MATCH (c:Customer)-[:USES_DEVICE]->(d:Device) RETURN id(c) AS source, id(d) AS target",
        )
        try:
            result_df = self._gds.nodeSimilarity.stream(graph, topK=top_k, similarityCutoff=similarity_cutoff)
            rows = []
            for _, row in result_df.iterrows():
                node1 = self._gds.util.asNode(row["node1"])
                node2 = self._gds.util.asNode(row["node2"])
                if "Customer" not in node1.labels or "Customer" not in node2.labels:
                    continue
                rows.append(
                    {
                        "customer_id_a": node1["customer_id"],
                        "customer_id_b": node2["customer_id"],
                        "similarity": float(row["similarity"]),
                    }
                )
            return rows
        finally:
            graph.drop()

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def run_all(self, include_betweenness: bool = False) -> dict[str, Any]:
        graph, projection_stats = self._project_account_network()
        try:
            summary: dict[str, Any] = {
                "graph": ACCOUNT_NETWORK_GRAPH,
                "nodes": projection_stats["nodeCount"],
                "relationships": projection_stats["relationshipCount"],
                "pagerank": self.run_pagerank(graph),
                "wcc": self.run_wcc(graph),
                "louvain": self.run_louvain(graph),
            }
            if include_betweenness:
                summary["betweenness"] = self.run_betweenness(graph)
            return summary
        finally:
            graph.drop()
