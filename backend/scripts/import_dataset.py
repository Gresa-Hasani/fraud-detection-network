"""Idempotent ingestion of generated CSV files into Neo4j.

Usage:
    python scripts/import_dataset.py --data-dir data/generated

Rerunning against the same directory is safe: every load uses MERGE on the
entity's natural identifier, so existing nodes/relationships are updated in
place rather than duplicated.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingestion import loaders  # noqa: E402
from ingestion.validation import SchemaError, load_and_validate  # noqa: E402

from app.core.database import Neo4jConnection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_dataset")

# (filename, required_columns, not_null_columns, loader_fn)
NODE_FILES = [
    ("customers.csv", ["customer_id", "full_name", "fraud_status"], ["customer_id"], loaders.load_customers),
    ("accounts.csv", ["account_id", "account_type", "currency"], ["account_id"], loaders.load_accounts),
    ("devices.csv", ["device_id", "fingerprint"], ["device_id"], loaders.load_devices),
    ("ip_addresses.csv", ["ip", "country"], ["ip"], loaders.load_ip_addresses),
    ("merchants.csv", ["merchant_id", "name"], ["merchant_id"], loaders.load_merchants),
    ("phone_numbers.csv", ["phone", "country_code"], ["phone"], loaders.load_phone_numbers),
    ("email_addresses.csv", ["email", "domain"], ["email"], loaders.load_email_addresses),
    ("addresses.csv", ["address_id", "country"], ["address_id"], loaders.load_addresses),
    (
        "transactions.csv",
        ["transaction_id", "amount", "transaction_type"],
        ["transaction_id"],
        loaders.load_transactions,
    ),
]

RELATIONSHIP_FILES = [
    ("customer_accounts.csv", ["customer_id", "account_id"], ["customer_id", "account_id"], loaders.load_owns),
    ("customer_devices.csv", ["customer_id", "device_id"], ["customer_id", "device_id"], loaders.load_uses_device),
    ("customer_phones.csv", ["customer_id", "phone"], ["customer_id", "phone"], loaders.load_uses_phone),
    ("customer_emails.csv", ["customer_id", "email"], ["customer_id", "email"], loaders.load_uses_email),
    ("customer_addresses.csv", ["customer_id", "address_id"], ["customer_id", "address_id"], loaders.load_lives_at),
    (
        "transaction_sources.csv",
        ["transaction_id"],
        ["transaction_id"],
        loaders.load_transaction_edges,
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "generated")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir: Path = args.data_dir
    if not data_dir.exists():
        logger.error("Data directory not found: %s", data_dir)
        sys.exit(1)

    connection = Neo4jConnection()
    connection.connect()

    overall_start = time.perf_counter()
    total_counters = loaders.ImportCounters()

    try:
        for filename, required, not_null, loader_fn in NODE_FILES + RELATIONSHIP_FILES:
            path = data_dir / filename
            if not path.exists():
                logger.warning("Skipping missing file: %s", path)
                continue

            file_start = time.perf_counter()
            try:
                validated = load_and_validate(str(path), required, not_null)
            except SchemaError as exc:
                logger.error("Aborting import of %s: %s", filename, exc)
                continue

            file_counters = loaders.ImportCounters()
            file_counters.rows_rejected = validated.rejected_count
            loader_fn(connection, validated.records, file_counters)

            total_counters.nodes_created += file_counters.nodes_created
            total_counters.relationships_created += file_counters.relationships_created
            total_counters.properties_set += file_counters.properties_set
            total_counters.rows_rejected += file_counters.rows_rejected

            duration = time.perf_counter() - file_start
            logger.info(
                "%s: %d rows processed (%d rejected) in %.2fs -- nodes=%d rels=%d props=%d",
                filename,
                len(validated.records),
                validated.rejected_count,
                duration,
                file_counters.nodes_created,
                file_counters.relationships_created,
                file_counters.properties_set,
            )
    finally:
        connection.close()

    total_duration = time.perf_counter() - overall_start
    logger.info(
        "Import complete in %.2fs. Totals: %s",
        total_duration,
        total_counters.as_dict(),
    )


if __name__ == "__main__":
    main()
