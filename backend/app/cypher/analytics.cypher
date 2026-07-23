// Reference catalog of the investigation Cypher queries used by the platform.
//
// These are the canonical, human-readable versions of the parameterized
// queries implemented in app/repositories/investigation_repository.py --
// that module is what the API actually executes (with $-parameters bound
// safely by the driver). This file exists so the query patterns can be
// reviewed, profiled with EXPLAIN/PROFILE, and run ad hoc in Neo4j Browser
// without spinning up the API. See docs/performance.md for EXPLAIN/PROFILE
// output on the queries most sensitive to dataset size.
//
// Query techniques demonstrated across this catalog: node lookup,
// relationship traversal, aggregation, time filtering, variable-length
// paths, shortest paths, cycle detection, UNWIND, OPTIONAL MATCH, CASE,
// COLLECT, UNION, CALL {} subqueries, and result pagination.

// 1. Node lookup -----------------------------------------------------------
MATCH (c:Customer {customer_id: $customer_id}) RETURN c;

// 2. Relationship traversal + aggregation: a customer's accounts with
//    running transaction counts.
MATCH (c:Customer {customer_id: $customer_id})-[:OWNS]->(a:Account)
OPTIONAL MATCH (a)<-[:FROM_ACCOUNT|TO_ACCOUNT]-(t:Transaction)
RETURN a, count(t) AS transaction_count
ORDER BY transaction_count DESC;

// 3. Devices shared by many customers (FD-001 evidence). Aggregation + COLLECT.
MATCH (d:Device)<-[:USES_DEVICE]-(c:Customer)
WITH d, collect(DISTINCT c.customer_id) AS customers, count(DISTINCT c) AS customer_count
WHERE customer_count >= $minimum_customers
RETURN d.device_id AS device_id, d.is_emulator AS is_emulator, d.is_rooted AS is_rooted,
       customer_count, customers
ORDER BY customer_count DESC;

// 4. Customers sharing BOTH a device and an IP -- graph pattern filtering.
MATCH (c:Customer {customer_id: $customer_id})-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Customer)
WHERE other.customer_id <> $customer_id
WITH c, other, collect(DISTINCT d.device_id) AS shared_devices
MATCH (c)-[:OWNS]->(:Account)<-[:FROM_ACCOUNT]-(t1:Transaction)-[:ORIGINATED_FROM]->(ip:IPAddress)
MATCH (other)-[:OWNS]->(:Account)<-[:FROM_ACCOUNT]-(t2:Transaction)-[:ORIGINATED_FROM]->(ip)
WITH other, shared_devices, collect(DISTINCT ip.ip) AS shared_ips
WHERE size(shared_ips) > 0
RETURN other.customer_id AS customer_id, shared_devices, shared_ips;

// 5. Shortest path from a customer to any confirmed fraudster -- variable-length
//    path bounded to avoid unbounded traversal.
MATCH (start:Customer {customer_id: $customer_id})
MATCH (fraud:Customer {fraud_status: 'CONFIRMED_FRAUD'})
WHERE start.customer_id <> fraud.customer_id
MATCH path = shortestPath((start)-[*..4]-(fraud))
RETURN path, length(path) AS hops
ORDER BY hops ASC
LIMIT 1;

// 6. Circular transfers of length 3-6 within a time window and amount tolerance.
//
//    NOTE: a naive `MATCH path = (a)-[*6..12]-(a)` cycle search (as shown below, for
//    reference/EXPLAIN comparison only) is an unbounded-MATCH trap: on a dense transaction
//    graph the engine explores a combinatorial number of dead-end paths before finding a
//    closed cycle. See docs/performance.md for the measured before/after. The implementation
//    in investigation_repository.find_circular_transfers instead fetches TRANSFER edges with
//    the simple, cheap query below and performs the temporal/amount-tolerance-constrained
//    cycle search as a depth-bounded DFS in Python -- Cypher variable-length paths also have
//    no native way to require "each hop happens after the previous one" anyway.
MATCH (t:Transaction {transaction_type: 'TRANSFER'})-[:FROM_ACCOUNT]->(src:Account)
MATCH (t)-[:TO_ACCOUNT]->(dst:Account)
RETURN src.account_id AS src, dst.account_id AS dst,
       t.transaction_id AS transaction_id, t.amount AS amount, t.timestamp AS timestamp;

// 6b. (Reference only -- do not run against a large dataset without a LIMIT on paths explored.)
// MATCH path = (a:Account)-[:FROM_ACCOUNT|TO_ACCOUNT*6..12]-(a)
// WITH path, [n IN nodes(path) WHERE n:Transaction] AS txs, [n IN nodes(path) WHERE n:Account] AS accts
// WHERE size(txs) >= 3 AND size(txs) <= 6 AND size(accts) = size(txs)
// RETURN [n IN accts | n.account_id] AS account_cycle, [n IN txs | n.transaction_id] AS transaction_ids;

// 7. Rapid pass-through: inbound transfer forwarded onward within N minutes.
MATCH (inbound:Transaction)-[:TO_ACCOUNT]->(a:Account)<-[:FROM_ACCOUNT]-(outbound:Transaction)
WHERE inbound.amount >= $min_amount
  AND outbound.timestamp > inbound.timestamp
  AND duration.inSeconds(inbound.timestamp, outbound.timestamp).seconds <= $max_seconds
  AND outbound.amount >= inbound.amount * $min_forwarded_pct
RETURN a.account_id AS account_id, inbound.transaction_id, outbound.transaction_id,
       inbound.amount, outbound.amount;

// 8 & 9. Fan-in / fan-out: accounts receiving from (or sending to) many distinct counterparty
// accounts within *some* rolling time window -- not the account's all-time activity span.
//
// NOTE: comparing an account's global min/max transaction timestamp (as below, for reference
// only) silently misses real fan-in/fan-out bursts on any account that *also* has ordinary
// incidental activity spread across its whole history -- the global span blows past the window
// even though the actual burst was tight. find_fan_in_accounts / find_fan_out_accounts instead
// fetch TRANSFER edges with the query below and run a two-pointer sliding-window scan in Python
// (see _find_fan_pattern in investigation_repository.py) to find the true best window per account.
MATCH (t:Transaction {transaction_type: 'TRANSFER'})-[:FROM_ACCOUNT]->(src:Account)
MATCH (t)-[:TO_ACCOUNT]->(dst:Account)
RETURN src.account_id AS src, dst.account_id AS dst,
       t.transaction_id AS transaction_id, t.timestamp AS timestamp;

// 8b/9b. (Reference only -- global-span version, misses bursts mixed with incidental activity.)
// MATCH (src:Account)<-[:FROM_ACCOUNT]-(t:Transaction)-[:TO_ACCOUNT]->(dst:Account)
// WITH dst, src, min(t.timestamp) AS first_ts, max(t.timestamp) AS last_ts, count(t) AS tx_count
// WITH dst, collect({source: src.account_id, tx_count: tx_count}) AS sources,
//      count(DISTINCT src) AS source_count, min(first_ts) AS window_start, max(last_ts) AS window_end
// WHERE source_count >= $min_sources
//   AND duration.inSeconds(window_start, window_end).seconds <= $window_seconds
// RETURN dst.account_id AS account_id, source_count, sources
// ORDER BY source_count DESC;

// 10. Structuring: several transactions just under a reporting threshold, short window.
MATCH (a:Account)<-[:FROM_ACCOUNT]-(t:Transaction)
WHERE t.amount >= $threshold * (1 - $margin_pct) AND t.amount < $threshold
WITH a, t ORDER BY t.timestamp
WITH a, collect({transaction_id: t.transaction_id, amount: t.amount, ts: t.timestamp}) AS below_threshold_txs
WHERE size(below_threshold_txs) >= $min_occurrences
  AND duration.inSeconds(below_threshold_txs[0].ts, below_threshold_txs[-1].ts).seconds <= $window_seconds
RETURN a.account_id AS account_id, below_threshold_txs;

// 11. Suspicious communities (Phase 5, uses Louvain-assigned community_id). A community is
// "suspicious" when it contains an account owned by a CONFIRMED_FRAUD customer -- fraud status
// is ground truth; risk_score rarely stacks high enough alone to use as the filter here.
MATCH (a:Account)
WHERE a.community_id IS NOT NULL
WITH a.community_id AS community_id, collect(a) AS members
WHERE size(members) >= $min_size
WITH community_id, members,
     [m IN members WHERE EXISTS {
         MATCH (:Customer {fraud_status: 'CONFIRMED_FRAUD'})-[:OWNS]->(m)
     }] AS confirmed_fraud_members
WHERE size(confirmed_fraud_members) > 0
RETURN community_id, size(members) AS member_count, [m IN members | m.account_id] AS account_ids;

// 12. Most central accounts (Phase 5, uses PageRank score).
MATCH (a:Account)
WHERE a.pagerank_score IS NOT NULL
RETURN a.account_id AS account_id, a.pagerank_score AS pagerank_score
ORDER BY a.pagerank_score DESC
LIMIT $limit;

// 13. Customers sharing an address OR a phone number -- UNION + CASE-style labeling.
MATCH (c:Customer {customer_id: $customer_id})-[:LIVES_AT]->(addr:Address)<-[:LIVES_AT]-(other:Customer)
WHERE other.customer_id <> $customer_id
RETURN DISTINCT other.customer_id AS customer_id, 'ADDRESS' AS link_type, addr.address_id AS shared_value
UNION
MATCH (c:Customer {customer_id: $customer_id})-[:USES_PHONE]->(p:PhoneNumber)<-[:USES_PHONE]-(other:Customer)
WHERE other.customer_id <> $customer_id
RETURN DISTINCT other.customer_id AS customer_id, 'PHONE' AS link_type, p.phone AS shared_value;

// 14. Dormant accounts that suddenly become active -- time filtering on gaps between events.
MATCH (a:Account)<-[:FROM_ACCOUNT|TO_ACCOUNT]-(t:Transaction)
WITH a, t ORDER BY t.timestamp
WITH a, collect(t) AS txs
WHERE size(txs) >= 2
WITH a, txs[-1] AS latest, txs[-2] AS previous
WHERE duration.inDays(previous.timestamp, latest.timestamp).days >= $dormancy_days
RETURN a.account_id AS account_id, previous.timestamp, latest.timestamp;

// 15. High-value transactions from newly-seen devices -- CASE-free boolean signal, time filtering.
MATCH (t:Transaction)-[:INITIATED_FROM]->(d:Device)
WHERE t.amount >= $min_amount AND duration.inDays(d.first_seen, t.timestamp).days <= $device_age_days
RETURN t.transaction_id AS transaction_id, t.amount, d.device_id, d.is_emulator, d.is_rooted
ORDER BY t.amount DESC;

// 16. Foreign-IP transactions inconsistent with the customer's registered country -- CASE.
MATCH (t:Transaction)-[:ORIGINATED_FROM]->(ip:IPAddress)
MATCH (t)-[:FROM_ACCOUNT]->(:Account)<-[:OWNS]-(c:Customer)
WHERE ip.country <> c.country
RETURN t.transaction_id AS transaction_id, c.customer_id, c.country AS customer_country, ip.country AS ip_country,
       CASE WHEN ip.is_vpn OR ip.is_proxy OR ip.is_tor THEN true ELSE false END AS is_anonymized;

// 17. Merchants connected to multiple flagged accounts -- aggregation + COLLECT.
MATCH (m:Merchant)<-[:PAID_TO]-(t:Transaction)-[:FROM_ACCOUNT]->(a:Account)
WHERE t.is_flagged = true
WITH m, collect(DISTINCT a.account_id) AS flagged_accounts, count(DISTINCT a) AS account_count
WHERE account_count >= $min_accounts
RETURN m.merchant_id AS merchant_id, m.name, account_count, flagged_accounts;

// 18. Account investigation subgraph -- CALL {} subquery + UNWIND, bounded depth,
//     shaped for the Cytoscape.js graph explorer (see build_account_investigation_subgraph).
MATCH (center:Account {account_id: $account_id})
CALL (center) {
    MATCH path = (center)-[*1..2]-(neighbor)
    RETURN path
    LIMIT $limit
}
WITH collect(path) AS paths
UNWIND paths AS path
WITH [n IN nodes(path) | n] AS ns, [r IN relationships(path) | r] AS rs
UNWIND ns AS node
WITH collect(DISTINCT node) AS all_nodes, rs
UNWIND rs AS rel
RETURN all_nodes, collect(DISTINCT rel) AS all_rels;

// 19. Flagged transactions, paginated and sorted -- result pagination via SKIP/LIMIT.
MATCH (t:Transaction)
WHERE t.is_flagged = true AND t.risk_score >= $min_risk_score
RETURN t
ORDER BY t.timestamp DESC
SKIP $offset
LIMIT $limit;

// 20. Transactions within a date range -- time filtering + pagination.
MATCH (t:Transaction)
WHERE t.timestamp >= datetime($start) AND t.timestamp <= datetime($end)
RETURN t
ORDER BY t.timestamp DESC
SKIP $offset
LIMIT $limit;

// 21. IPs shared by many distinct customers (FD-002 evidence).
MATCH (ip:IPAddress)<-[:ORIGINATED_FROM]-(t:Transaction)-[:FROM_ACCOUNT]->(a:Account)<-[:OWNS]-(c:Customer)
WITH ip, collect(DISTINCT c.customer_id) AS customers, count(DISTINCT c) AS customer_count
WHERE customer_count >= $minimum_customers
RETURN ip.ip AS ip, ip.is_vpn, ip.is_proxy, ip.is_tor, customer_count, customers
ORDER BY customer_count DESC;

// 22. Account counterparties -- aggregation over transaction volume by direction.
MATCH (a:Account {account_id: $account_id})<-[:FROM_ACCOUNT]-(t:Transaction)-[:TO_ACCOUNT]->(cp:Account)
WITH cp, count(t) AS outgoing_count, sum(t.amount) AS outgoing_amount
RETURN cp.account_id AS counterparty_id, outgoing_count, outgoing_amount
ORDER BY outgoing_amount DESC;
