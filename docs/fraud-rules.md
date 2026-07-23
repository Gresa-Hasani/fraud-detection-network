# Fraud Detection Rules

Every rule below is a **risk signal**, not proof of fraud. Language throughout this
document and the application itself is deliberately hedged ("suspicious", "requires
investigation", "risk signal") -- a detected pattern means an investigator should look, not
that fraud is confirmed. See `docs/performance.md` and the evaluation report
(`make` target below) for measured, imperfect precision/recall on the synthetic dataset;
this is by design, not a bug to be hidden.

Rule identifiers, weights, and descriptions are centralized in
[`backend/app/core/fraud_rules_config.py`](../backend/app/core/fraud_rules_config.py).
Evidence-gathering Cypher lives in
[`investigation_repository.py`](../backend/app/repositories/investigation_repository.py);
rule-to-signal mapping and scoring live in
[`fraud_detection_service.py`](../backend/app/services/fraud_detection_service.py).

Run all rules: `make detect-fraud` (also runs the GDS pipeline first, since FD-010 depends
on `community_id`). Evaluate against ground truth: `python backend/scripts/evaluate_detection.py`.

---

## FD-001: Shared Device

**Business description:** A device (phone, browser fingerprint) used by many distinct
customers is either a shared household device (usually benign at low counts) or a fraud
ring deliberately reusing one device across fake/mule identities.

**Graph pattern:** `(Device)<-[:USES_DEVICE]-(Customer)`, grouped by device, filtered on
distinct customer count.

**Threshold:** `default_shared_device_min_customers` (default `5`), in `Settings`.

**Score contribution:** base `15`; `+10` if the device is an emulator; `+10` if rooted
(both bonuses can apply, so a rooted-emulator ring maxes at `35`).

**False-positive risk:** family/household device sharing, shared work devices, or public
kiosk devices (bank branch tablets, internet cafes) can trigger this at low customer counts
with no fraud intent. The emulator/rooted bonus is the main precision lever.

**Example result:** `"Device is shared by 17 unrelated customers (emulator) (rooted)."` with
`score_contribution: 35`.

**Test scenario:** `test_shared_device_detection` in
`tests/integration/test_fraud_detection_service.py`, against the planted
`SHARED_DEVICE_RING` scenario (8-20 customers sharing one device).

---

## FD-002: Shared IP

**Business description:** Same idea as FD-001 but for originating IP address. Much noisier
in practice: CGNAT, mobile carrier NAT, and corporate proxies legitimately put many unrelated
customers behind one IP.

**Graph pattern:** `(Transaction)-[:ORIGINATED_FROM]->(IPAddress)`, joined back to the
owning customer via `FROM_ACCOUNT`/`OWNS`, grouped by IP.

**Threshold:** `default_shared_ip_min_customers` (default `5`).

**Score contribution:** base `15`; `+10` if the IP is a known VPN, proxy, or Tor exit node.

**False-positive risk:** measured directly on this dataset -- ~300 of 4,000 IPs have 5+
distinct customers purely from normal usage patterns (see `docs/performance.md`). This rule
alone has low precision; it is meant to be combined with the VPN/proxy/Tor bonus and other
signals (FD-009, FD-010) rather than acted on in isolation.

**Example result:** `"IP 204.29.134.208 is shared by 22 unrelated customers."`

**Test scenario:** `test_shared_ip_detection`, against the planted `SHARED_IP` scenario.

---

## FD-003: Circular Transfer

**Business description:** Money laundering "layering" -- funds move through a closed loop
of accounts (A -> B -> C -> A) to obscure origin, often in similar amounts within a short
window.

**Graph pattern:** cycle in the `TRANSFER`-edge account graph, 3-6 accounts, each hop
chronologically after the previous, within a configurable time window and amount tolerance.
Implemented as a Cypher fetch + Python depth-bounded DFS, not a raw variable-length
`MATCH` -- see `docs/performance.md` for why.

**Thresholds:** `default_cycle_min_length`/`max_length` (3/6), `default_cycle_time_window_hours`
(72), `default_cycle_amount_tolerance_pct` (0.1).

**Score contribution:** flat `30` (highest base weight -- closed transfer loops have very
little legitimate explanation).

**False-positive risk:** low by construction (a genuine closed loop within a tight time and
amount window rarely happens by chance), but small cycles can occur from legitimate round-
trip business payments (e.g., invoice + refund) that happen to close a loop.

**Example result:** `"Account participates in a 4-account transaction cycle."`

**Test scenario:** `test_circular_transfer_detection`, against the planted
`CIRCULAR_TRANSFER` scenario.

---

## FD-004: Rapid Pass-Through

**Business description:** An account receives a large sum and forwards nearly all of it
onward within minutes -- classic mule-account behavior (the account is a pass-through, not a
destination).

**Graph pattern:** `(inbound:Transaction)-[:TO_ACCOUNT]->(a)<-[:FROM_ACCOUNT]-(outbound:Transaction)`
where `outbound` follows `inbound` within the time window and forwards at least the minimum
percentage.

**Thresholds:** `default_rapid_pass_through_minutes` (30), `default_rapid_pass_through_min_pct`
(0.85).

**Score contribution:** `20`.

**False-positive risk:** legitimate quick forwarding happens (e.g., splitting a shared bill,
paying a supplier immediately on receipt of funds) -- this rule alone shouldn't be treated as
high-confidence without corroborating signals.

**Example result:** `"Received 10000.00 and forwarded 9700.00 within 12 minutes."`

**Test scenario:** `test_rapid_pass_through_detection`, against the planted
`RAPID_PASS_THROUGH` scenario.

---

## FD-005 / FD-006: Fan-In / Fan-Out

**Business description:** Many source accounts converging into one destination (fan-in,
often a collection point before consolidation) or one source distributing to many
destinations (fan-out, often distributing stolen/laundered funds to mules) within a short
window.

**Graph pattern:** central account with >= N distinct counterparties in *some* rolling time
window (two-pointer sliding-window scan over fetched `TRANSFER` edges -- see
`docs/performance.md` for why a naive all-time-span check misses real bursts).

**Thresholds:** `default_fan_in_min_sources`/`default_fan_out_min_targets` (10),
`default_fan_window_hours` (24).

**Score contribution:** `15` each.

**False-positive risk:** payroll accounts (fan-out to many employees) and merchant
settlement/collection accounts (fan-in from many customers) are legitimate high-fan-out/
fan-in patterns; account type and merchant association should be checked before escalating.
Recall on the planted scenario is intentionally partial: only the central account gets an
alert (contributing source/target accounts are recorded as `related_entities`, not
separately alerted), since a single normal customer paying into a legitimate collection
account isn't itself suspicious.

**Example result:** `"Received transfers from 22 distinct accounts in a short window."`

**Test scenario:** `test_fan_in_detection` / `test_fan_out_detection`.

---

## FD-007: Structuring

**Business description:** Multiple transactions kept just under a reporting threshold to
avoid triggering mandatory reporting ("smurfing").

**Graph pattern:** an account with >= N transactions in `[threshold * (1 - margin), threshold)`
within a time window.

**Thresholds:** `default_structuring_threshold` (10,000), `default_structuring_margin_pct`
(0.1), `default_structuring_window_hours` (72).

**Score contribution:** `20`.

**False-positive risk:** low if the threshold is set to match an actual regulatory
reporting limit; coincidental clustering of legitimate withdrawals near a round number is
possible but rare with 3+ occurrences required.

**Example result:** `"3 transfers just below the 10000 reporting threshold in a short window."`

**Test scenario:** `test_structuring_detection`.

---

## FD-008: Account Takeover

**Business description:** A high-value transaction from a brand-new device, at an unusual
hour, combined with an anomalous IP (VPN/proxy/Tor or a country mismatch) -- the profile of
a compromised-credential takeover rather than the genuine account holder transacting.

**Graph pattern:** `Transaction-[:INITIATED_FROM]->Device` where the device's `first_seen`
is within days of the transaction, `Transaction-[:ORIGINATED_FROM]->IPAddress` flagged
anonymized or country-mismatched, transaction hour in a configurable odd-hours set, amount
above a minimum.

**Thresholds:** `min_amount` (5,000), `device_age_days` (3), `odd_hours` (00:00-05:00).

**Score contribution:** flat `30`.

**False-positive risk:** genuine customers do occasionally use a new device while
travelling (new IP, new country) and transact at odd local hours if their timezone differs
from the account's registered country -- this rule benefits most from corroboration (e.g.,
combined with FD-009 proximity or a prior alert history).

**Example result:** `"High-value transaction (14711.03) from a new device at an unusual
hour, with anonymized IP (VPN/proxy/Tor)."`

**Test scenario:** `test_account_takeover_detection`.

---

## FD-009: Fraud Proximity

**Business description:** How close (in hops) is this account's owner to a *confirmed*
fraudster? Closer connections carry more risk, but this is explicitly a graph-proximity
heuristic, not evidence the account itself did anything.

**Graph pattern:** `shortestPath` (bounded to 3 hops) from the customer to any
`Customer {fraud_status: 'CONFIRMED_FRAUD'}`, batched across all candidates in one query
(see `find_shortest_paths_to_confirmed_fraud_batch`) rather than one shortestPath call per
candidate, for performance.

**Score contribution:** hop-distance-dependent, not a flat weight: 1 hop = `30`,
2 hops = `20`, 3 hops = `10` (see `PROXIMITY_WEIGHTS_BY_HOP`). No signal beyond 3 hops.

**False-positive risk:** by design, this rule *will* flag innocent people who happen to
share an address, phone, device, or transaction history with a fraudster without knowing it
(a roommate, a family member, a landlord). It is a prioritization signal for investigators,
explicitly weighted lower than direct-evidence rules for exactly this reason.

**Example result:** `"2-hop connection to a confirmed fraud customer."`

**Test scenario:** `test_shortest_path_to_fraud_detection`, against the planted
`FRAUD_PROXIMITY` scenario.

---

## FD-010: Suspicious Community

**Business description:** Louvain community detection groups accounts by transaction
density; a community containing a confirmed-fraud account may represent a broader
coordinated ring, not just the one confirmed member.

**Graph pattern:** every `Account` in a Louvain community (`community_id`, written by
`GraphAnalyticsService.run_louvain`, see `docs/architecture.md`) where at least one member
account is owned by a `CONFIRMED_FRAUD` customer.

**Threshold:** `min_size` (default 5 accounts).

**Score contribution:** `25`.

**False-positive risk:** measured directly as high on this dataset -- Louvain communities on
a moderately-dense transaction graph tend to be large (dozens to hundreds of accounts), so
"contains one confirmed-fraud account" sweeps in many accounts with no other connection to
that fraud beyond incidental community membership. This is documented, not hidden: FD-010
is the noisiest rule and is best used as a low-weight corroborating signal, not a standalone
trigger. Restricting to smaller/denser communities (e.g. requiring a minimum modularity
contribution per member, or re-running Louvain with a resolution parameter) is a natural
follow-up not implemented here.

**Example result:** `"Member of community 267 (537 accounts, 1 critical-risk)."`

**Test scenario:** not covered by a ground-truth scenario test (community membership is
cross-cutting over every other scenario's planted accounts, not its own scenario) -- see
`backend/scripts/evaluate_detection.py` for why FD-010 is excluded from the per-rule
precision/recall report.

---

## Score aggregation

Each entity's final risk score is the sum of the *distinct rules* that fired against it
(the same rule firing twice contributes once, at its highest observed weight -- see
`RiskScoringService`), capped at 100:

| Score | Level |
|---|---|
| 0-24 | LOW |
| 25-49 | MEDIUM |
| 50-74 | HIGH |
| 75-100 | CRITICAL |

The full reasons list (rule, weight, human-readable description) is returned by
`GET /api/v1/accounts/{id}/risk` and rendered directly in the frontend's account
investigation page -- every score is explainable back to the specific evidence that produced
it.
