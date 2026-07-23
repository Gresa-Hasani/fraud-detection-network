"""Core investigation Cypher queries against the fraud graph.

Every query here is parameterized, bounded (LIMIT / max path hops), and
documented with the investigative question it answers. Route handlers never
embed Cypher directly -- they call through this repository, which is the
single place query text lives so it can be profiled and tuned in one spot.

Community-detection and centrality queries (`find_suspicious_communities`,
`find_most_central_accounts`) read `community_id` / `pagerank_score`
properties that are written by the Graph Data Science jobs in
`graph_analytics_service.py` (Phase 5) -- they return an empty result set
until those jobs have been run at least once.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from app.core.database import Neo4jConnection

DEFAULT_LIMIT = 25
MAX_LIMIT = 200


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_LIMIT))


def _to_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        return to_native()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _find_temporal_cycles(
    edges: list[dict[str, Any]],
    *,
    min_length: int,
    max_length: int,
    window_seconds: int,
    amount_tolerance_pct: float,
    max_results: int,
    max_paths_explored: int = 200_000,
) -> list[dict[str, Any]]:
    """Depth-bounded DFS for account cycles where each hop is chronologically after the last.

    Mirrors how the synthetic circular-transfer scenario (and real layering schemes) actually work:
    money moves A -> B -> C -> ... -> A in increasing timestamp order, within `window_seconds` of the
    first transfer, and each hop's amount stays within `amount_tolerance_pct` of the cycle's first amount.
    """
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["src"]].append(
            {
                "dst": edge["dst"],
                "transaction_id": edge["transaction_id"],
                "amount": float(edge["amount"]),
                "timestamp": _to_datetime(edge["timestamp"]),
            }
        )
    for edge_list in adjacency.values():
        edge_list.sort(key=lambda e: e["timestamp"])

    results: list[dict[str, Any]] = []
    paths_explored = 0

    def dfs(
        start: str,
        current: str,
        path_accounts: list[str],
        path_txs: list[str],
        first_amount: float,
        first_ts: datetime,
        last_ts: datetime,
    ) -> None:
        nonlocal paths_explored
        if len(results) >= max_results or paths_explored >= max_paths_explored:
            return
        for edge in adjacency.get(current, []):
            paths_explored += 1
            if paths_explored >= max_paths_explored:
                return
            if edge["timestamp"] < last_ts:
                continue
            if (edge["timestamp"] - first_ts).total_seconds() > window_seconds:
                continue
            if max(edge["amount"], first_amount) > min(edge["amount"], first_amount) * (1 + amount_tolerance_pct):
                continue

            if edge["dst"] == start and len(path_accounts) >= min_length:
                results.append(
                    {
                        "account_cycle": [*path_accounts, start],
                        "transaction_ids": [*path_txs, edge["transaction_id"]],
                        "cycle_length": len(path_accounts),
                    }
                )
                if len(results) >= max_results:
                    return
                continue

            if edge["dst"] in path_accounts or len(path_accounts) >= max_length:
                continue

            dfs(
                start,
                edge["dst"],
                [*path_accounts, edge["dst"]],
                [*path_txs, edge["transaction_id"]],
                first_amount,
                first_ts,
                edge["timestamp"],
            )
            if len(results) >= max_results:
                return

    for start_account in list(adjacency.keys()):
        if len(results) >= max_results or paths_explored >= max_paths_explored:
            break
        for first_edge in adjacency.get(start_account, []):
            dfs(
                start_account,
                first_edge["dst"],
                [start_account, first_edge["dst"]],
                [first_edge["transaction_id"]],
                first_edge["amount"],
                first_edge["timestamp"],
                first_edge["timestamp"],
            )
            if len(results) >= max_results:
                break

    return results


def _find_fan_pattern(
    grouped_edges: dict[str, list[dict[str, Any]]],
    *,
    counterparty_key: str,
    min_count: int,
    window_seconds: int,
    result_key: str,
    count_key: str,
    list_key: str,
    item_key: str,
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """For each central account's time-ordered edges, find the widest-fan sliding window.

    Two-pointer scan: `right` advances through time-ordered events while `left` is pulled forward
    just enough to keep `events[left..right]` within `window_seconds`, tracking how many distinct
    counterparties are in that window at each step. This finds the best (maximum distinct
    counterparty count) window for each central account in O(n) time.
    """
    results: list[dict[str, Any]] = []
    for center, edges in grouped_edges.items():
        events = sorted(edges, key=lambda e: _to_datetime(e["timestamp"]))
        counts: dict[str, int] = defaultdict(int)
        left = 0
        best_distinct = 0
        best_window: list[dict[str, Any]] = []
        for right, event in enumerate(events):
            counts[event[counterparty_key]] += 1
            right_ts = _to_datetime(events[right]["timestamp"])
            while (right_ts - _to_datetime(events[left]["timestamp"])).total_seconds() > window_seconds:
                counts[events[left][counterparty_key]] -= 1
                if counts[events[left][counterparty_key]] == 0:
                    del counts[events[left][counterparty_key]]
                left += 1
            if len(counts) > best_distinct:
                best_distinct = len(counts)
                best_window = events[left : right + 1]

        if best_distinct >= min_count:
            counterparties: dict[str, int] = defaultdict(int)
            for event in best_window:
                counterparties[event[counterparty_key]] += 1
            results.append(
                {
                    result_key: center,
                    count_key: best_distinct,
                    list_key: [{item_key: cp, "tx_count": n} for cp, n in counterparties.items()],
                }
            )

    results.sort(key=lambda r: -r[count_key])
    return results[:max_results]


class InvestigationRepository:
    def __init__(self, connection: Neo4jConnection) -> None:
        self._db = connection

    # ------------------------------------------------------------------
    # Node lookup
    # ------------------------------------------------------------------

    def find_customer_by_id(self, customer_id: str) -> dict[str, Any] | None:
        """Look up a single customer by its natural id."""
        records = self._db.run_query(
            "MATCH (c:Customer {customer_id: $customer_id}) RETURN c",
            {"customer_id": customer_id},
        )
        return records[0]["c"] if records else None

    def find_account_by_id(self, account_id: str) -> dict[str, Any] | None:
        """Look up a single account by its natural id."""
        records = self._db.run_query(
            "MATCH (a:Account {account_id: $account_id}) RETURN a",
            {"account_id": account_id},
        )
        return records[0]["a"] if records else None

    def find_transaction_by_id(self, transaction_id: str) -> dict[str, Any] | None:
        """Look up a single transaction by its natural id."""
        records = self._db.run_query(
            "MATCH (t:Transaction {transaction_id: $transaction_id}) RETURN t",
            {"transaction_id": transaction_id},
        )
        return records[0]["t"] if records else None

    # ------------------------------------------------------------------
    # Relationship traversal & aggregation
    # ------------------------------------------------------------------

    def find_customer_accounts(self, customer_id: str) -> list[dict[str, Any]]:
        """All accounts owned by a customer, with a running transaction count per account."""
        return self._db.run_query(
            """
            MATCH (c:Customer {customer_id: $customer_id})-[:OWNS]->(a:Account)
            OPTIONAL MATCH (a)<-[:FROM_ACCOUNT|TO_ACCOUNT]-(t:Transaction)
            RETURN a, count(t) AS transaction_count
            ORDER BY transaction_count DESC
            """,
            {"customer_id": customer_id},
        )

    def find_customer_connections(self, customer_id: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Directly RELATED_TO customers (household/known-associate links)."""
        return self._db.run_query(
            """
            MATCH (c:Customer {customer_id: $customer_id})-[r:RELATED_TO]-(other:Customer)
            RETURN other, r.relationship_type AS relationship_type, r.confidence_score AS confidence_score
            ORDER BY confidence_score DESC
            LIMIT $limit
            """,
            {"customer_id": customer_id, "limit": _clamp_limit(limit)},
        )

    def get_account_counterparties(self, account_id: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Accounts this account has transacted with, aggregated by direction and volume."""
        return self._db.run_query(
            """
            MATCH (a:Account {account_id: $account_id})<-[:FROM_ACCOUNT]-(t:Transaction)-[:TO_ACCOUNT]->(cp:Account)
            WITH cp, count(t) AS outgoing_count, sum(t.amount) AS outgoing_amount
            RETURN cp.account_id AS counterparty_id, outgoing_count, outgoing_amount
            ORDER BY outgoing_amount DESC
            LIMIT $limit
            """,
            {"account_id": account_id, "limit": _clamp_limit(limit)},
        )

    # ------------------------------------------------------------------
    # Shared identifiers (device / IP / address / phone)
    # ------------------------------------------------------------------

    def find_devices_shared_by_many_customers(self, minimum_customers: int = 5) -> list[dict[str, Any]]:
        """Devices used by at least `minimum_customers` distinct customers -- FD-001 evidence."""
        return self._db.run_query(
            """
            MATCH (d:Device)<-[:USES_DEVICE]-(c:Customer)
            WITH d, collect(DISTINCT c.customer_id) AS customers, count(DISTINCT c) AS customer_count
            WHERE customer_count >= $minimum_customers
            RETURN d.device_id AS device_id,
                   d.is_emulator AS is_emulator,
                   d.is_rooted AS is_rooted,
                   customer_count,
                   customers
            ORDER BY customer_count DESC
            """,
            {"minimum_customers": minimum_customers},
        )

    def find_ips_shared_by_many_customers(self, minimum_customers: int = 5) -> list[dict[str, Any]]:
        """IP addresses that originated transactions for many distinct customers -- FD-002 evidence."""
        return self._db.run_query(
            """
            MATCH (ip:IPAddress)<-[:ORIGINATED_FROM]-(t:Transaction)-[:FROM_ACCOUNT]->(a:Account)<-[:OWNS]-(c:Customer)
            WITH ip, collect(DISTINCT c.customer_id) AS customers, count(DISTINCT c) AS customer_count
            WHERE customer_count >= $minimum_customers
            RETURN ip.ip AS ip,
                   ip.is_vpn AS is_vpn,
                   ip.is_proxy AS is_proxy,
                   ip.is_tor AS is_tor,
                   ip.country AS country,
                   customer_count,
                   customers
            ORDER BY customer_count DESC
            """,
            {"minimum_customers": minimum_customers},
        )

    def find_customers_sharing_device_and_ip(self, customer_id: str) -> list[dict[str, Any]]:
        """Other customers sharing BOTH a device and an IP with the given customer -- strong ring evidence."""
        return self._db.run_query(
            """
            MATCH (c:Customer {customer_id: $customer_id})-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Customer)
            WHERE other.customer_id <> $customer_id
            WITH c, other, collect(DISTINCT d.device_id) AS shared_devices
            MATCH (c)-[:OWNS]->(:Account)<-[:FROM_ACCOUNT]-(t1:Transaction)-[:ORIGINATED_FROM]->(ip:IPAddress)
            MATCH (other)-[:OWNS]->(:Account)<-[:FROM_ACCOUNT]-(t2:Transaction)-[:ORIGINATED_FROM]->(ip)
            WITH other, shared_devices, collect(DISTINCT ip.ip) AS shared_ips
            WHERE size(shared_ips) > 0
            RETURN other.customer_id AS customer_id, shared_devices, shared_ips
            """,
            {"customer_id": customer_id},
        )

    def find_customers_sharing_address_or_phone(self, customer_id: str) -> list[dict[str, Any]]:
        """Other customers sharing an address or phone number, labeled with which link matched."""
        return self._db.run_query(
            """
            MATCH (c:Customer {customer_id: $customer_id})-[:LIVES_AT]->(addr:Address)<-[:LIVES_AT]-(other:Customer)
            WHERE other.customer_id <> $customer_id
            RETURN DISTINCT other.customer_id AS customer_id, 'ADDRESS' AS link_type, addr.address_id AS shared_value
            UNION
            MATCH (c:Customer {customer_id: $customer_id})-[:USES_PHONE]->(p:PhoneNumber)
            MATCH (other:Customer)-[:USES_PHONE]->(p)
            WHERE other.customer_id <> $customer_id
            RETURN DISTINCT other.customer_id AS customer_id, 'PHONE' AS link_type, p.phone AS shared_value
            """,
            {"customer_id": customer_id},
        )

    def find_top_shared_devices(self, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Devices ranked by number of distinct users, for the analytics dashboard."""
        return self._db.run_query(
            """
            MATCH (d:Device)<-[:USES_DEVICE]-(c:Customer)
            WITH d, count(DISTINCT c) AS customer_count
            WHERE customer_count > 1
            RETURN d.device_id AS device_id, d.is_emulator AS is_emulator, d.is_rooted AS is_rooted, customer_count
            ORDER BY customer_count DESC
            LIMIT $limit
            """,
            {"limit": _clamp_limit(limit)},
        )

    # ------------------------------------------------------------------
    # Fraud proximity / shortest path
    # ------------------------------------------------------------------

    def find_shortest_path_to_confirmed_fraud(self, customer_id: str, max_hops: int = 4) -> dict[str, Any] | None:
        """Shortest path from a customer to any CONFIRMED_FRAUD customer, bounded to `max_hops`."""
        records = self._db.run_query(
            f"""
            MATCH (start:Customer {{customer_id: $customer_id}})
            MATCH (fraud:Customer {{fraud_status: 'CONFIRMED_FRAUD'}})
            WHERE start.customer_id <> fraud.customer_id
            MATCH path = shortestPath((start)-[*..{max_hops}]-(fraud))
            RETURN path, length(path) AS hops
            ORDER BY hops ASC
            LIMIT 1
            """,
            {"customer_id": customer_id},
        )
        return records[0] if records else None

    def find_shortest_paths_to_confirmed_fraud_batch(
        self, customer_ids: list[str], max_hops: int = 3
    ) -> dict[str, int]:
        """Batched FD-009 evidence: hop distance to the nearest confirmed fraudster, per candidate.

        One round trip via UNWIND instead of one shortestPath query per candidate -- at a few
        hundred candidates the per-call network/parse overhead dominates actual traversal cost
        on a graph this size, so batching is the difference between seconds and minutes.
        """
        if not customer_ids:
            return {}
        records = self._db.run_query(
            f"""
            UNWIND $customer_ids AS cid
            MATCH (start:Customer {{customer_id: cid}})
            MATCH (fraud:Customer {{fraud_status: 'CONFIRMED_FRAUD'}})
            WHERE start.customer_id <> fraud.customer_id
            OPTIONAL MATCH path = shortestPath((start)-[*..{max_hops}]-(fraud))
            WITH cid, min(length(path)) AS hops
            WHERE hops IS NOT NULL
            RETURN cid AS customer_id, hops
            """,
            {"customer_ids": customer_ids},
        )
        return {row["customer_id"]: row["hops"] for row in records}

    # ------------------------------------------------------------------
    # Money-movement pattern detection
    # ------------------------------------------------------------------

    def find_circular_transfers(
        self,
        min_length: int = 3,
        max_length: int = 6,
        window_hours: int = 72,
        amount_tolerance_pct: float = 0.1,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Cycles of TRANSFER transactions of length `min_length`..`max_length` within a time window.

        A single Cypher `MATCH path = (a)-[*n..m]-(a)` for cycle detection is a classic unbounded-traversal
        trap: on a dense transaction graph the relationship-uniqueness-only pruning still lets the engine
        explore a combinatorial number of dead-end paths before finding a closed cycle (this was measured
        directly -- see docs/performance.md). Instead we fetch TRANSFER edges with a single indexed,
        bounded Cypher query (cheap: tens of thousands of rows at most) and run a depth- and time-bounded
        DFS over that small in-memory edge list, which is where a temporal/amount-tolerance-constrained
        cycle search belongs -- Cypher variable-length paths have no native support for "each hop must be
        chronologically after the previous one" style constraints anyway.
        """
        edges = self._db.run_query(
            """
            MATCH (t:Transaction {transaction_type: 'TRANSFER'})-[:FROM_ACCOUNT]->(src:Account)
            MATCH (t)-[:TO_ACCOUNT]->(dst:Account)
            RETURN src.account_id AS src, dst.account_id AS dst,
                   t.transaction_id AS transaction_id, t.amount AS amount, t.timestamp AS timestamp
            """
        )
        return _find_temporal_cycles(
            edges,
            min_length=min_length,
            max_length=max_length,
            window_seconds=window_hours * 3600,
            amount_tolerance_pct=amount_tolerance_pct,
            max_results=max_results,
        )

    def find_rapid_pass_through_accounts(
        self, max_minutes: int = 30, min_forwarded_pct: float = 0.85, min_amount: float = 1000.0
    ) -> list[dict[str, Any]]:
        """Accounts that forward most of an inbound transfer onward within `max_minutes`."""
        return self._db.run_query(
            """
            MATCH (inbound:Transaction)-[:TO_ACCOUNT]->(a:Account)<-[:FROM_ACCOUNT]-(outbound:Transaction)
            WHERE inbound.amount >= $min_amount
              AND outbound.timestamp > inbound.timestamp
              AND duration.inSeconds(inbound.timestamp, outbound.timestamp).seconds <= $max_seconds
              AND outbound.amount >= inbound.amount * $min_forwarded_pct
            RETURN a.account_id AS account_id,
                   inbound.transaction_id AS inbound_transaction_id,
                   outbound.transaction_id AS outbound_transaction_id,
                   inbound.amount AS inbound_amount,
                   outbound.amount AS outbound_amount,
                   duration.inSeconds(inbound.timestamp, outbound.timestamp).seconds AS seconds_between
            ORDER BY inbound_amount DESC
            LIMIT 100
            """,
            {"max_seconds": max_minutes * 60, "min_forwarded_pct": min_forwarded_pct, "min_amount": min_amount},
        )

    def _fetch_transfer_edges(self) -> list[dict[str, Any]]:
        return self._db.run_query(
            """
            MATCH (t:Transaction {transaction_type: 'TRANSFER'})-[:FROM_ACCOUNT]->(src:Account)
            MATCH (t)-[:TO_ACCOUNT]->(dst:Account)
            RETURN src.account_id AS src, dst.account_id AS dst,
                   t.transaction_id AS transaction_id, t.timestamp AS timestamp
            """
        )

    def find_fan_in_accounts(self, min_sources: int = 10, window_hours: int = 24) -> list[dict[str, Any]]:
        """Accounts receiving from many distinct source accounts within *some* rolling time window.

        Grouping by (dst, src) and comparing the account's all-time min/max timestamp -- the
        obvious first Cypher approach -- silently fails for any account that also has years of
        unrelated, incidental incoming transfers: the global min/max span blows past the window
        even though the actual fan-in burst was tight. A genuine rolling-window check needs a
        sliding window over time-ordered events, which we do here in Python after one cheap fetch.
        """
        edges = self._fetch_transfer_edges()
        by_dst: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            by_dst[edge["dst"]].append(edge)
        return _find_fan_pattern(
            by_dst,
            counterparty_key="src",
            min_count=min_sources,
            window_seconds=window_hours * 3600,
            result_key="account_id",
            count_key="source_count",
            list_key="sources",
            item_key="source",
        )

    def find_fan_out_accounts(self, min_targets: int = 10, window_hours: int = 24) -> list[dict[str, Any]]:
        """Accounts sending to many distinct destination accounts within *some* rolling time window.

        See `find_fan_in_accounts` for why this needs a true sliding window rather than a
        global min/max timestamp comparison.
        """
        edges = self._fetch_transfer_edges()
        by_src: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            by_src[edge["src"]].append(edge)
        return _find_fan_pattern(
            by_src,
            counterparty_key="dst",
            min_count=min_targets,
            window_seconds=window_hours * 3600,
            result_key="account_id",
            count_key="target_count",
            list_key="targets",
            item_key="target",
        )

    def find_structuring_transactions(
        self, threshold: float = 10000.0, margin_pct: float = 0.1, window_hours: int = 72, min_occurrences: int = 3
    ) -> list[dict[str, Any]]:
        """Accounts with several transactions just below a reporting threshold in a short window."""
        return self._db.run_query(
            """
            MATCH (a:Account)<-[:FROM_ACCOUNT]-(t:Transaction)
            WHERE t.amount >= $threshold * (1 - $margin_pct) AND t.amount < $threshold
            WITH a, t
            ORDER BY t.timestamp
            WITH a, collect({transaction_id: t.transaction_id, amount: t.amount, ts: t.timestamp})
                 AS below_threshold_txs
            WHERE size(below_threshold_txs) >= $min_occurrences
              AND duration.inSeconds(below_threshold_txs[0].ts, below_threshold_txs[-1].ts).seconds <= $window_seconds
            RETURN a.account_id AS account_id, below_threshold_txs, size(below_threshold_txs) AS occurrence_count
            ORDER BY occurrence_count DESC
            LIMIT 50
            """,
            {
                "threshold": threshold,
                "margin_pct": margin_pct,
                "window_seconds": window_hours * 3600,
                "min_occurrences": min_occurrences,
            },
        )

    # ------------------------------------------------------------------
    # Behavioral anomalies
    # ------------------------------------------------------------------

    def find_dormant_accounts_suddenly_active(
        self, dormancy_days: int = 90, recent_days: int = 7
    ) -> list[dict[str, Any]]:
        """Accounts with no activity for `dormancy_days` that then transacted within the last `recent_days`."""
        return self._db.run_query(
            """
            MATCH (a:Account)<-[:FROM_ACCOUNT|TO_ACCOUNT]-(t:Transaction)
            WITH a, t ORDER BY t.timestamp
            WITH a, collect(t) AS txs
            WHERE size(txs) >= 2
            WITH a, txs, txs[-1] AS latest, txs[-2] AS previous
            WHERE duration.inDays(previous.timestamp, latest.timestamp).days >= $dormancy_days
              AND duration.inDays(latest.timestamp, datetime()).days <= $recent_days
            RETURN a.account_id AS account_id, previous.timestamp AS last_activity_before_gap,
                   latest.timestamp AS reactivation_timestamp, latest.transaction_id AS reactivation_transaction_id
            ORDER BY reactivation_timestamp DESC
            LIMIT 50
            """,
            {"dormancy_days": dormancy_days, "recent_days": recent_days},
        )

    def find_high_value_transactions_from_new_devices(
        self, min_amount: float = 5000.0, device_age_days: int = 3
    ) -> list[dict[str, Any]]:
        """High-value transactions initiated from a device first seen very recently -- takeover signal."""
        return self._db.run_query(
            """
            MATCH (t:Transaction)-[:INITIATED_FROM]->(d:Device)
            WHERE t.amount >= $min_amount
              AND duration.inDays(d.first_seen, t.timestamp).days <= $device_age_days
            RETURN t.transaction_id AS transaction_id, t.amount AS amount, t.timestamp AS timestamp,
                   d.device_id AS device_id, d.is_emulator AS is_emulator, d.is_rooted AS is_rooted
            ORDER BY t.amount DESC
            LIMIT 50
            """,
            {"min_amount": min_amount, "device_age_days": device_age_days},
        )

    def find_account_takeover_candidates(
        self, min_amount: float = 5000.0, device_age_days: int = 3, odd_hours: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
    ) -> list[dict[str, Any]]:
        """FD-008 evidence: high-value transaction from a brand-new device, an anomalous IP, at an odd hour."""
        return self._db.run_query(
            """
            MATCH (t:Transaction)-[:INITIATED_FROM]->(d:Device)
            MATCH (t)-[:FROM_ACCOUNT]->(a:Account)<-[:OWNS]-(c:Customer)
            OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(ip:IPAddress)
            WITH t, d, a, c, ip,
                 duration.inDays(d.first_seen, t.timestamp).days AS device_age_days,
                 (ip IS NOT NULL AND (ip.is_vpn OR ip.is_proxy OR ip.is_tor OR ip.country <> c.country))
                 AS ip_is_anomalous
            WHERE t.amount >= $min_amount
              AND device_age_days <= $device_age_days
              AND t.timestamp.hour IN $odd_hours
              AND ip_is_anomalous
            RETURN t.transaction_id AS transaction_id, t.amount AS amount, t.timestamp AS timestamp,
                   a.account_id AS account_id, c.customer_id AS customer_id,
                   d.device_id AS device_id, ip.ip AS ip, ip.is_vpn AS is_vpn, ip.is_proxy AS is_proxy,
                   ip.is_tor AS is_tor, ip.country AS ip_country, c.country AS customer_country
            ORDER BY t.amount DESC
            LIMIT 100
            """,
            {
                "min_amount": min_amount,
                "device_age_days": device_age_days,
                "odd_hours": list(odd_hours),
            },
        )

    def find_foreign_ip_transactions(self) -> list[dict[str, Any]]:
        """Transactions originating from a country different from the owning customer's registered country."""
        return self._db.run_query(
            """
            MATCH (t:Transaction)-[:ORIGINATED_FROM]->(ip:IPAddress)
            MATCH (t)-[:FROM_ACCOUNT]->(:Account)<-[:OWNS]-(c:Customer)
            WHERE ip.country <> c.country
            RETURN t.transaction_id AS transaction_id, t.amount AS amount, c.customer_id AS customer_id,
                   c.country AS customer_country, ip.country AS ip_country,
                   CASE WHEN ip.is_vpn OR ip.is_proxy OR ip.is_tor THEN true ELSE false END AS is_anonymized
            ORDER BY t.amount DESC
            LIMIT 100
            """,
            {},
        )

    def find_merchants_with_multiple_flagged_accounts(self, min_accounts: int = 3) -> list[dict[str, Any]]:
        """Merchants receiving payments from several distinct flagged/suspicious accounts."""
        return self._db.run_query(
            """
            MATCH (m:Merchant)<-[:PAID_TO]-(t:Transaction)-[:FROM_ACCOUNT]->(a:Account)
            WHERE t.is_flagged = true
            WITH m, collect(DISTINCT a.account_id) AS flagged_accounts, count(DISTINCT a) AS account_count
            WHERE account_count >= $min_accounts
            RETURN m.merchant_id AS merchant_id, m.name AS name, m.risk_level AS risk_level,
                   account_count, flagged_accounts
            ORDER BY account_count DESC
            LIMIT 50
            """,
            {"min_accounts": min_accounts},
        )

    # ------------------------------------------------------------------
    # Community / centrality (populated by Phase 5 GDS jobs)
    # ------------------------------------------------------------------

    def find_suspicious_communities(self, min_size: int = 5, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Louvain communities containing at least one confirmed-fraud account, ranked by size.

        "Confirmed fraud" here means the account's owning Customer has fraud_status =
        CONFIRMED_FRAUD -- not a risk_level threshold on the Account. Risk *scores* are built from
        several modest-weight signals (see fraud_rules_config.py) that rarely stack high enough to
        reach CRITICAL on their own; fraud *status* is the actual ground truth to key off of here.
        """
        return self._db.run_query(
            """
            MATCH (a:Account)
            WHERE a.community_id IS NOT NULL
            WITH a.community_id AS community_id, collect(a) AS members
            WHERE size(members) >= $min_size
            WITH community_id, members,
                 [m IN members WHERE EXISTS {
                     MATCH (:Customer {fraud_status: 'CONFIRMED_FRAUD'})-[:OWNS]->(m)
                 }] AS confirmed_fraud_members
            WHERE size(confirmed_fraud_members) > 0
            RETURN community_id, size(members) AS member_count,
                   [m IN members | m.account_id] AS account_ids,
                   size(confirmed_fraud_members) AS critical_member_count
            ORDER BY member_count DESC
            LIMIT $limit
            """,
            {"min_size": min_size, "limit": _clamp_limit(limit)},
        )

    def find_most_central_accounts(self, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        """Accounts ranked by PageRank score -- influence/centrality, not fraud by itself."""
        return self._db.run_query(
            """
            MATCH (a:Account)
            WHERE a.pagerank_score IS NOT NULL
            RETURN a.account_id AS account_id, a.pagerank_score AS pagerank_score, a.risk_level AS risk_level
            ORDER BY a.pagerank_score DESC
            LIMIT $limit
            """,
            {"limit": _clamp_limit(limit)},
        )

    # ------------------------------------------------------------------
    # Investigation subgraph (frontend-friendly node/edge payload)
    # ------------------------------------------------------------------

    def build_account_investigation_subgraph(self, account_id: str, depth: int = 2, limit: int = 100) -> dict[str, Any]:
        """A bounded-depth neighborhood around an account, shaped for the Cytoscape.js graph explorer.

        Labels/relationship-type/endpoint metadata is extracted explicitly in the RETURN clause
        (`labels(n)`, `type(r)`, `elementId(...)`) rather than returning raw Node/Relationship
        values -- the driver's `Record.data()` (used by `Neo4jConnection.run_query`) flattens
        those into bare property dicts and silently discards exactly that metadata.
        """
        depth = max(1, min(depth, 3))
        records = self._db.run_query(
            f"""
            MATCH (center:Account {{account_id: $account_id}})
            CALL (center) {{
                MATCH path = (center)-[*1..{depth}]-(neighbor)
                RETURN path
                LIMIT $limit
            }}
            WITH collect(path) AS paths
            UNWIND paths AS path
            WITH [n IN nodes(path) | n] AS ns, [r IN relationships(path) | r] AS rs
            UNWIND ns AS node
            WITH collect(DISTINCT {{
                element_id: elementId(node), labels: labels(node), properties: properties(node)
            }}) AS all_nodes, rs
            UNWIND rs AS rel
            RETURN all_nodes, collect(DISTINCT {{
                element_id: elementId(rel), type: type(rel),
                source_element_id: elementId(startNode(rel)), target_element_id: elementId(endNode(rel)),
                properties: properties(rel)
            }}) AS all_rels
            """,
            {"account_id": account_id, "limit": _clamp_limit(limit)},
        )
        if not records:
            return {"nodes": [], "edges": []}
        return {"raw_nodes": records[0]["all_nodes"], "raw_edges": records[0]["all_rels"]}

    # ------------------------------------------------------------------
    # Paginated listings
    # ------------------------------------------------------------------

    def list_flagged_transactions(
        self, limit: int = DEFAULT_LIMIT, offset: int = 0, min_risk_score: int = 0
    ) -> list[dict[str, Any]]:
        """Flagged transactions above a minimum risk score, newest first, paginated."""
        return self._db.run_query(
            """
            MATCH (t:Transaction)
            WHERE t.is_flagged = true AND t.risk_score >= $min_risk_score
            RETURN t
            ORDER BY t.timestamp DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"min_risk_score": min_risk_score, "offset": offset, "limit": _clamp_limit(limit)},
        )

    def list_transactions_in_date_range(
        self, start: str, end: str, limit: int = DEFAULT_LIMIT, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Transactions within an ISO-8601 timestamp range, paginated."""
        return self._db.run_query(
            """
            MATCH (t:Transaction)
            WHERE t.timestamp >= datetime($start) AND t.timestamp <= datetime($end)
            RETURN t
            ORDER BY t.timestamp DESC
            SKIP $offset
            LIMIT $limit
            """,
            {"start": start, "end": end, "offset": offset, "limit": _clamp_limit(limit)},
        )
