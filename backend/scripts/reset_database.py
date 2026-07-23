"""Wipe all graph data and (re)apply constraints and indexes.

Usage:
    python scripts/reset_database.py [--keep-schema]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Neo4jConnection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reset_database")

CYPHER_DIR = Path(__file__).resolve().parents[1] / "app" / "cypher"


def _load_statements(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    without_comments = "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))
    return [stmt.strip() for stmt in without_comments.split(";") if stmt.strip()]


def wipe_data(connection: Neo4jConnection) -> None:
    logger.info("Deleting all nodes and relationships in batches...")
    deleted_total = 0
    while True:
        result = connection.run_write_query("MATCH (n) WITH n LIMIT 20000 DETACH DELETE n RETURN count(n) AS deleted")
        deleted = result["records"][0]["deleted"] if result["records"] else 0
        deleted_total += deleted
        if deleted == 0:
            break
    logger.info("Deleted %s nodes total.", deleted_total)


def apply_schema(connection: Neo4jConnection) -> None:
    for filename in ("constraints.cypher", "indexes.cypher"):
        statements = _load_statements(CYPHER_DIR / filename)
        logger.info("Applying %s (%d statements)...", filename, len(statements))
        for stmt in statements:
            connection.run_write_query(stmt)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-schema", action="store_true", help="Skip re-applying constraints/indexes")
    args = parser.parse_args()

    connection = Neo4jConnection()
    connection.connect()
    try:
        wipe_data(connection)
        if not args.keep_schema:
            apply_schema(connection)
        logger.info("Database reset complete.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
