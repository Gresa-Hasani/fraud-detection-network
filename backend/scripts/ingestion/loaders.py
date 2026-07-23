"""Batched, idempotent UNWIND + MERGE loaders for every node and relationship type.

Every statement here is parameterized (`$rows`) -- CSV data never touches
Cypher string construction. MERGE keys on the same identifier the CSV was
generated with, so rerunning an import updates properties in place instead
of creating duplicates.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from app.core.database import Neo4jConnection

from .validation import to_bool, to_float, to_int

logger = logging.getLogger("ingestion.loaders")

DEFAULT_BATCH_SIZE = 1000


def batched(records: list[dict[str, Any]], size: int = DEFAULT_BATCH_SIZE) -> Iterator[list[dict[str, Any]]]:
    for i in range(0, len(records), size):
        yield records[i : i + size]


class ImportCounters:
    def __init__(self) -> None:
        self.nodes_created = 0
        self.relationships_created = 0
        self.properties_set = 0
        self.rows_rejected = 0

    def add(self, counters: Any) -> None:
        self.nodes_created += getattr(counters, "nodes_created", 0)
        self.relationships_created += getattr(counters, "relationships_created", 0)
        self.properties_set += getattr(counters, "properties_set", 0)

    def as_dict(self) -> dict[str, int]:
        return {
            "nodes_created": self.nodes_created,
            "relationships_created": self.relationships_created,
            "properties_set": self.properties_set,
            "rows_rejected": self.rows_rejected,
        }


def _run_batches(
    connection: Neo4jConnection, query: str, records: list[dict[str, Any]], counters: ImportCounters
) -> None:
    for batch in batched(records):
        result = connection.run_write_query(query, {"rows": batch})
        counters.add(result["counters"])


# ---------------------------------------------------------------------------
# Node loaders
# ---------------------------------------------------------------------------


def load_customers(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (c:Customer {customer_id: row.customer_id})
    SET c.full_name = row.full_name,
        c.email = row.email,
        c.phone = row.phone,
        c.date_of_birth = row.date_of_birth,
        c.country = row.country,
        c.city = row.city,
        c.postal_code = row.postal_code,
        c.address = row.address,
        c.registration_date = datetime(row.registration_date),
        c.kyc_status = row.kyc_status,
        c.customer_status = row.customer_status,
        c.fraud_status = row.fraud_status,
        c.created_at = datetime(row.created_at),
        c.updated_at = datetime(row.updated_at)
    """
    _run_batches(connection, query, records, counters)


def load_accounts(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["balance"] = to_float(row.get("balance"))
        row["risk_score"] = to_int(row.get("risk_score"))
    query = """
    UNWIND $rows AS row
    MERGE (a:Account {account_id: row.account_id})
    SET a.account_number = row.account_number,
        a.account_type = row.account_type,
        a.currency = row.currency,
        a.balance = row.balance,
        a.opened_at = datetime(row.opened_at),
        a.status = row.status,
        a.country = row.country,
        a.risk_score = row.risk_score,
        a.risk_level = row.risk_level,
        a.last_risk_calculation = datetime(row.last_risk_calculation)
    """
    _run_batches(connection, query, records, counters)


def load_transactions(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["amount"] = to_float(row.get("amount"))
        row["risk_score"] = to_int(row.get("risk_score"))
        row["is_flagged"] = to_bool(row.get("is_flagged"))
        row["latitude"] = to_float(row.get("latitude"))
        row["longitude"] = to_float(row.get("longitude"))
    query = """
    UNWIND $rows AS row
    MERGE (t:Transaction {transaction_id: row.transaction_id})
    SET t.amount = row.amount,
        t.currency = row.currency,
        t.timestamp = datetime(row.timestamp),
        t.transaction_type = row.transaction_type,
        t.channel = row.channel,
        t.status = row.status,
        t.description = row.description,
        t.country = row.country,
        t.latitude = row.latitude,
        t.longitude = row.longitude,
        t.risk_score = row.risk_score,
        t.is_flagged = row.is_flagged
    """
    _run_batches(connection, query, records, counters)


def load_devices(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["is_emulator"] = to_bool(row.get("is_emulator"))
        row["is_rooted"] = to_bool(row.get("is_rooted"))
        row["risk_score"] = to_int(row.get("risk_score"))
    query = """
    UNWIND $rows AS row
    MERGE (d:Device {device_id: row.device_id})
    SET d.device_type = row.device_type,
        d.operating_system = row.operating_system,
        d.browser = row.browser,
        d.fingerprint = row.fingerprint,
        d.first_seen = datetime(row.first_seen),
        d.last_seen = datetime(row.last_seen),
        d.is_emulator = row.is_emulator,
        d.is_rooted = row.is_rooted,
        d.risk_score = row.risk_score
    """
    _run_batches(connection, query, records, counters)


def load_ip_addresses(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["is_vpn"] = to_bool(row.get("is_vpn"))
        row["is_proxy"] = to_bool(row.get("is_proxy"))
        row["is_tor"] = to_bool(row.get("is_tor"))
        row["latitude"] = to_float(row.get("latitude"))
        row["longitude"] = to_float(row.get("longitude"))
        row["risk_score"] = to_int(row.get("risk_score"))
    query = """
    UNWIND $rows AS row
    MERGE (ip:IPAddress {ip: row.ip})
    SET ip.country = row.country,
        ip.city = row.city,
        ip.isp = row.isp,
        ip.is_vpn = row.is_vpn,
        ip.is_proxy = row.is_proxy,
        ip.is_tor = row.is_tor,
        ip.latitude = row.latitude,
        ip.longitude = row.longitude,
        ip.risk_score = row.risk_score
    """
    _run_batches(connection, query, records, counters)


def load_merchants(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    query = """
    UNWIND $rows AS row
    MERGE (m:Merchant {merchant_id: row.merchant_id})
    SET m.name = row.name,
        m.category = row.category,
        m.country = row.country,
        m.city = row.city,
        m.risk_level = row.risk_level,
        m.created_at = datetime(row.created_at)
    """
    _run_batches(connection, query, records, counters)


def load_phone_numbers(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["verified"] = to_bool(row.get("verified"))
        row["risk_score"] = to_int(row.get("risk_score"))
    query = """
    UNWIND $rows AS row
    MERGE (p:PhoneNumber {phone: row.phone})
    SET p.country_code = row.country_code,
        p.verified = row.verified,
        p.first_seen = datetime(row.first_seen),
        p.last_seen = datetime(row.last_seen),
        p.risk_score = row.risk_score
    """
    _run_batches(connection, query, records, counters)


def load_email_addresses(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["verified"] = to_bool(row.get("verified"))
        row["risk_score"] = to_int(row.get("risk_score"))
    query = """
    UNWIND $rows AS row
    MERGE (e:EmailAddress {email: row.email})
    SET e.domain = row.domain,
        e.verified = row.verified,
        e.first_seen = datetime(row.first_seen),
        e.last_seen = datetime(row.last_seen),
        e.risk_score = row.risk_score
    """
    _run_batches(connection, query, records, counters)


def load_addresses(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["latitude"] = to_float(row.get("latitude"))
        row["longitude"] = to_float(row.get("longitude"))
        row["risk_score"] = to_int(row.get("risk_score"))
    query = """
    UNWIND $rows AS row
    MERGE (a:Address {address_id: row.address_id})
    SET a.street = row.street,
        a.city = row.city,
        a.postal_code = row.postal_code,
        a.country = row.country,
        a.latitude = row.latitude,
        a.longitude = row.longitude,
        a.risk_score = row.risk_score
    """
    _run_batches(connection, query, records, counters)


# ---------------------------------------------------------------------------
# Relationship loaders
# ---------------------------------------------------------------------------


def load_owns(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (a:Account {account_id: row.account_id})
    MERGE (c)-[:OWNS]->(a)
    """
    _run_batches(connection, query, records, counters)


def load_uses_device(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["usage_count"] = to_int(row.get("usage_count"))
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (d:Device {device_id: row.device_id})
    MERGE (c)-[r:USES_DEVICE]->(d)
    SET r.first_seen = datetime(row.first_seen),
        r.last_seen = datetime(row.last_seen),
        r.usage_count = row.usage_count
    """
    _run_batches(connection, query, records, counters)


def load_uses_phone(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["verified"] = to_bool(row.get("verified"))
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (p:PhoneNumber {phone: row.phone})
    MERGE (c)-[r:USES_PHONE]->(p)
    SET r.verified = row.verified,
        r.first_seen = datetime(row.first_seen),
        r.last_seen = datetime(row.last_seen)
    """
    _run_batches(connection, query, records, counters)


def load_uses_email(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["verified"] = to_bool(row.get("verified"))
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (e:EmailAddress {email: row.email})
    MERGE (c)-[r:USES_EMAIL]->(e)
    SET r.verified = row.verified,
        r.first_seen = datetime(row.first_seen),
        r.last_seen = datetime(row.last_seen)
    """
    _run_batches(connection, query, records, counters)


def load_lives_at(connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters) -> None:
    for row in records:
        row["is_current"] = to_bool(row.get("is_current"))
    query = """
    UNWIND $rows AS row
    MATCH (c:Customer {customer_id: row.customer_id})
    MATCH (addr:Address {address_id: row.address_id})
    MERGE (c)-[r:LIVES_AT]->(addr)
    SET r.from_date = CASE WHEN row.from_date <> '' THEN datetime(row.from_date) ELSE null END,
        r.to_date = CASE WHEN row.to_date <> '' THEN datetime(row.to_date) ELSE null END,
        r.is_current = row.is_current
    """
    _run_batches(connection, query, records, counters)


def load_transaction_edges(
    connection: Neo4jConnection, records: list[dict[str, Any]], counters: ImportCounters
) -> None:
    from_rows = [r for r in records if r.get("from_account_id")]
    to_rows = [r for r in records if r.get("to_account_id")]
    device_rows = [r for r in records if r.get("device_id")]
    ip_rows = [r for r in records if r.get("ip")]
    merchant_rows = [r for r in records if r.get("merchant_id")]

    _run_batches(
        connection,
        """
        UNWIND $rows AS row
        MATCH (t:Transaction {transaction_id: row.transaction_id})
        MATCH (a:Account {account_id: row.from_account_id})
        MERGE (t)-[:FROM_ACCOUNT]->(a)
        """,
        from_rows,
        counters,
    )
    _run_batches(
        connection,
        """
        UNWIND $rows AS row
        MATCH (t:Transaction {transaction_id: row.transaction_id})
        MATCH (a:Account {account_id: row.to_account_id})
        MERGE (t)-[:TO_ACCOUNT]->(a)
        """,
        to_rows,
        counters,
    )
    _run_batches(
        connection,
        """
        UNWIND $rows AS row
        MATCH (t:Transaction {transaction_id: row.transaction_id})
        MATCH (d:Device {device_id: row.device_id})
        MERGE (t)-[:INITIATED_FROM]->(d)
        """,
        device_rows,
        counters,
    )
    _run_batches(
        connection,
        """
        UNWIND $rows AS row
        MATCH (t:Transaction {transaction_id: row.transaction_id})
        MATCH (ip:IPAddress {ip: row.ip})
        MERGE (t)-[:ORIGINATED_FROM]->(ip)
        """,
        ip_rows,
        counters,
    )
    _run_batches(
        connection,
        """
        UNWIND $rows AS row
        MATCH (t:Transaction {transaction_id: row.transaction_id})
        MATCH (m:Merchant {merchant_id: row.merchant_id})
        MERGE (t)-[:PAID_TO]->(m)
        """,
        merchant_rows,
        counters,
    )
