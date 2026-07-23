# Performance and Query Optimization

All numbers below were measured against the default-scale generated dataset (5,000
customers, ~7,100 accounts, ~52,000 transactions -- some overlap from repeated
integration-test runs) on a single local Neo4j 5.26 Community instance. They are meant to
show real orders of magnitude and real trade-offs made during development, not to claim
production-scale benchmarks.

Reproduce with:

```bash
make benchmark
```

which runs [`backend/scripts/benchmark.py`](../backend/scripts/benchmark.py).

## Best practices already applied

- **Constraints and indexes** on every natural identifier and every commonly-filtered
  property (see [`constraints.cypher`](../backend/app/cypher/constraints.cypher) /
  [`indexes.cypher`](../backend/app/cypher/indexes.cypher)).
- **Every query is parameterized** (`$param`, never string-built Cypher) so the same query
  plan is reused across calls instead of being reparsed and replanned each time.
- **Every list endpoint is paginated** (`SKIP`/`LIMIT`) and every graph-traversal query has a
  bounded hop count (`[*1..3]`, never an unbounded `[*]`).
- **Batched writes**: ingestion and fraud-alert persistence both use `UNWIND` + batched
  transactions (500-1000 rows per round trip) rather than one write per row -- see
  [`ingestion/loaders.py`](../backend/scripts/ingestion/loaders.py) and
  [`fraud_repository.py`](../backend/app/repositories/fraud_repository.py).
- **Graph Data Science projections are ephemeral**: `GraphAnalyticsService` always drops its
  in-memory projection in a `finally` block so repeated runs don't leak server memory.

## Case study: the unbounded-MATCH trap (circular transfers, fan-in, fan-out)

The first implementation of "find circular transfers" was the textbook Cypher approach:

```cypher
MATCH path = (a:Account)-[:FROM_ACCOUNT|TO_ACCOUNT*6..12]-(a)
WITH path, [n IN nodes(path) WHERE n:Transaction] AS txs, ...
WHERE size(txs) >= 3 AND size(txs) <= 6 ...
RETURN ...
```

**Observed issue:** against the full dataset this query did not return within several
minutes and had to be killed. Relationship-uniqueness is the only pruning Cypher applies to
a variable-length path by default; on a graph where "hub" accounts (mule accounts from the
fan-in/fan-out scenarios) have dozens of transaction edges, the number of dead-end paths the
engine explores before finding one that closes back on the start node grows combinatorially.
This is exactly the "avoidance of unbounded MATCH patterns" anti-pattern called out as a
best practice to avoid -- it's easy to write without noticing until it's run against
realistic data volume.

**Fix:** fetch `TRANSFER` edges with one cheap, indexed, un-nested query, then run a
depth- and time-bounded search over that small in-memory edge list in Python:

```cypher
MATCH (t:Transaction {transaction_type: 'TRANSFER'})-[:FROM_ACCOUNT]->(src:Account)
MATCH (t)-[:TO_ACCOUNT]->(dst:Account)
RETURN src.account_id AS src, dst.account_id AS dst,
       t.transaction_id AS transaction_id, t.amount AS amount, t.timestamp AS timestamp
```

Measured PROFILE for the fetch (18,287 TRANSFER edges):

```text
ProduceResults          rows=18287  dbHits=0
  Projection             rows=18287  dbHits=18287
    Filter                rows=18287  dbHits=18287
      Expand(All)          rows=18287  dbHits=84329
        CacheProperties     rows=18287  dbHits=73148
          Filter             rows=18287  dbHits=36574
            Expand(All)       rows=18287  dbHits=92117
              NodeByLabelScan  rows=7123   dbHits=7124
resultAvailableAfter=18ms  resultConsumedAfter=204ms
```

The subsequent Python-side depth-bounded DFS (see `_find_temporal_cycles` in
`investigation_repository.py`) additionally enforces a constraint Cypher variable-length
paths can't express directly anyway: each hop must be chronologically *after* the previous
one, within a configurable time window, at a similar amount. End-to-end this query now
returns in the low seconds (`find_circular_transfers`: ~2.8s in the benchmark run below) --
slower than a truly small query, but bounded and *reliably* terminating instead of hanging.
The same fetch-then-scan approach was applied to `find_fan_in_accounts` /
`find_fan_out_accounts`, which had a second, independent bug: comparing an account's
all-time min/max transaction timestamp against the window (instead of a genuine sliding
window) silently missed real bursts on any account that also had years of unrelated,
incidental activity. See `_find_fan_pattern` for the two-pointer sliding-window fix.

## EXPLAIN/PROFILE on five important queries

### 1. List flagged transactions (`GET /transactions/flagged`)

```cypher
PROFILE MATCH (t:Transaction)
WHERE t.is_flagged = true AND t.risk_score >= 0
RETURN t ORDER BY t.timestamp DESC SKIP 0 LIMIT 25
```

```text
ProduceResults        rows=25   dbHits=325
  Skip                  rows=25   dbHits=0
    Top                  rows=25   dbHits=0
      Projection          rows=288  dbHits=288
        Filter              rows=288  dbHits=52000
          NodeIndexSeekByRange rows=52000 dbHits=52001
```

**Observation:** the `risk_score >= 0` range predicate is unselective (matches every
transaction), so the index seek still touches all 52,000 nodes before the `is_flagged`
filter narrows it to 288. The index is used, but the query is only as selective as its most
restrictive predicate -- passing a real `min_risk_score` (as the `/transactions/high-risk`
endpoint does) makes this seek genuinely selective instead of a full index scan in disguise.

### 2. Confirmed-fraud customer lookup (used by FD-009 proximity and dashboard counts)

```cypher
PROFILE MATCH (c:Customer {fraud_status: 'CONFIRMED_FRAUD'}) RETURN count(c)
```

```text
ProduceResults      rows=1  dbHits=0
  EagerAggregation    rows=1  dbHits=0
    NodeIndexSeek       rows=2  dbHits=3
```

**Observation:** this is the ideal case -- the `customer_fraud_status` index turns an
otherwise full label scan into a 3-dbHit lookup. This is why FD-009 fetches the confirmed-
fraud set once (via this index) and reuses it, rather than re-querying per candidate.

### 3. Shared devices (`FD-001` evidence, `GET /fraud/shared-devices`)

```cypher
PROFILE MATCH (d:Device)<-[:USES_DEVICE]-(c:Customer)
WITH d, collect(DISTINCT c.customer_id) AS customers, count(DISTINCT c) AS customer_count
WHERE customer_count >= 5
RETURN d.device_id, customer_count ORDER BY customer_count DESC
```

```text
ProduceResults      rows=16
  Projection          rows=16    dbHits=16
    Sort                rows=16    dbHits=0
      Filter              rows=16    dbHits=0
        EagerAggregation    rows=3381  dbHits=0
          Filter              rows=5025  dbHits=0
            Expand(All)         rows=5025  dbHits=31779
              CacheProperties     rows=5000  dbHits=5000
                NodeByLabelScan     rows=5000  dbHits=5001
```

**Observation:** there's no way to index-seek this query -- "which devices have >= 5
distinct users" is inherently an aggregation over every `USES_DEVICE` edge, so a full
`Customer` label scan (5,000 dbHits) plus relationship expansion is the correct plan.
Bounding this further would mean pre-aggregating device usage counts (e.g. a scheduled job
writing a `device.customer_count` property) -- not done here since the dataset is small
enough that ~32K dbHits completes in ~27ms (see benchmark below); flagged as a scaling
consideration in `docs/graph-model.md` if the dataset grows by orders of magnitude.

### 4. Structuring candidates (`FD-007`, threshold-adjacent transactions)

```cypher
PROFILE MATCH (a:Account)<-[:FROM_ACCOUNT]-(t:Transaction)
WHERE t.amount >= 9000.0 AND t.amount < 10000.0
RETURN a.account_id, t.transaction_id
```

```text
ProduceResults      rows=6
  Projection          rows=6      dbHits=6
    Filter              rows=6      dbHits=52006
      Expand(All)         rows=52000  dbHits=92117
        CacheProperties     rows=7123   dbHits=7123
          NodeByLabelScan     rows=7123   dbHits=7124
```

**Observation:** `Transaction.amount` has no index (see `indexes.cypher`), so every
transaction is expanded from every account before the amount filter runs -- 92K dbHits to
return 6 rows. This is the clearest concrete optimization opportunity this project didn't
take: adding a range index on `Transaction.amount` would let this become an index seek.
It was left out deliberately because `amount` ranges differ per rule (structuring threshold
is configurable) and a single index doesn't help every range equally -- documented here
rather than "fixed" with a narrow index that only helps one query.

### 5. Circular-transfer edge fetch (see case study above)

Already profiled above: 18,287 rows via two label-scan-seeded expansions, ~204ms total. The
`*6..12` unbounded variable-length equivalent did not complete within several minutes and
was abandoned rather than profiled to completion.

## Benchmark results (full run, `make benchmark`)

| Query | Duration | Records |
|---|---:|---:|
| `find_devices_shared_by_many_customers` | 27.4 ms | 16 |
| `find_ips_shared_by_many_customers` | 169.3 ms | 302 |
| `find_circular_transfers` | 2,841.3 ms | 4 |
| `find_rapid_pass_through_accounts` | 50.2 ms | 10 |
| `find_fan_in_accounts` | 2,604.2 ms | 3 |
| `find_fan_out_accounts` | 2,972.9 ms | 3 |
| `find_structuring_transactions` | 75.8 ms | 2 |
| `list_flagged_transactions` | 48.7 ms | 25 |
| **Full fraud-detection run (`run_all`, all 9 rules)** | **13.1 s** | 734 alerts created |

The three fetch-then-scan queries (circular transfers, fan-in, fan-out) dominate total
runtime at ~2.5-3s each -- all of that time is the Python-side windowed scan over the fetched
edge list, not the Cypher fetch itself (which is ~50-200ms per the PROFILE above). This is
an acceptable trade-off at this dataset size: reliable, bounded, and an order of magnitude
faster than the unbounded-MATCH version that didn't terminate at all.

## Ingestion performance

Importing the full generated dataset (5,000 customers, ~7,100 accounts, ~52,000
transactions, ~190K relationships) via `make import-data` takes **~30-55s**, dominated by
`transactions.csv` (50K nodes, ~9s) and `transaction_sources.csv` (50K rows expanding into
~160K relationships across five separate UNWIND passes, ~15-28s). Batch size is 1,000 rows
per transaction (`DEFAULT_BATCH_SIZE` in `ingestion/loaders.py`); rerunning the same import
is idempotent and touches ~0 nodes/relationships on the second pass (verified in
`tests/integration/test_ingestion.py`).
