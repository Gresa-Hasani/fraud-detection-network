"""Generate a reproducible synthetic financial fraud dataset as CSV files.

Usage:
    python scripts/generate_dataset.py \\
        --customers 5000 \\
        --accounts 7000 \\
        --transactions 50000 \\
        --fraud-rate 0.03 \\
        --seed 42 \\
        --output-dir ../data/generated
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from datagen.config import GeneratorConfig  # noqa: E402
from datagen.context import GenerationContext  # noqa: E402
from datagen.entities import build_entity_pools  # noqa: E402
from datagen.normal_transactions import generate_normal_transactions  # noqa: E402
from datagen.scenarios import run_all_scenarios  # noqa: E402
from datagen.writer import write_csv  # noqa: E402
from faker import Faker  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_dataset")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customers", type=int, default=5000)
    parser.add_argument("--accounts", type=int, default=7000)
    parser.add_argument("--transactions", type=int, default=50000)
    parser.add_argument("--devices", type=int, default=6000)
    parser.add_argument("--ip-addresses", type=int, default=4000)
    parser.add_argument("--merchants", type=int, default=500)
    parser.add_argument("--phone-numbers", type=int, default=6000)
    parser.add_argument("--email-addresses", type=int, default=6000)
    parser.add_argument("--addresses", type=int, default=5000)
    parser.add_argument("--fraud-rate", type=float, default=0.03)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--id-prefix",
        default="",
        help=(
            "Prefix inserted into every generated id (CUS-<prefix>000001, TX-<prefix>0000001, ...). "
            "Leave empty for a normal full-scale dataset. Set to a distinct value (e.g. 'TST-') for "
            "fixture/test datasets so their ids can never collide with an unprefixed dataset merged "
            "into the same database."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "generated",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started = time.perf_counter()

    cfg = GeneratorConfig(
        customers=args.customers,
        accounts=args.accounts,
        transactions=args.transactions,
        devices=args.devices,
        ip_addresses=args.ip_addresses,
        merchants=args.merchants,
        phone_numbers=args.phone_numbers,
        email_addresses=args.email_addresses,
        addresses=args.addresses,
        fraud_rate=args.fraud_rate,
        seed=args.seed,
        id_prefix=args.id_prefix,
    )

    logger.info("Building entity pools (customers=%d, accounts=%d)...", cfg.customers, cfg.accounts)
    pools = build_entity_pools(cfg)

    rng = random.Random(cfg.seed + 1)
    faker = Faker()
    Faker.seed(cfg.seed + 1)
    ctx = GenerationContext(pools=pools, rng=rng, faker=faker, now=datetime(2026, 7, 1), id_prefix=cfg.id_prefix)

    target_fraud_customers = max(1, int(cfg.customers * cfg.fraud_rate))
    logger.info("Injecting fraud scenarios (target ~%d customers)...", target_fraud_customers)
    touched = run_all_scenarios(ctx, target_fraud_customers)
    logger.info(
        "Fraud scenarios touched %d customers across %d ground-truth rows.", len(touched), len(ctx.ground_truth)
    )

    logger.info("Filling remaining transaction budget to %d total...", cfg.transactions)
    generate_normal_transactions(ctx, cfg.transactions)

    output_dir = args.output_dir
    logger.info("Writing CSV files to %s ...", output_dir)

    counts = {}
    counts["customers"] = write_csv(
        pools.customers,
        output_dir / "customers.csv",
        [
            "customer_id",
            "full_name",
            "email",
            "phone",
            "date_of_birth",
            "country",
            "city",
            "postal_code",
            "address",
            "registration_date",
            "kyc_status",
            "customer_status",
            "fraud_status",
            "created_at",
            "updated_at",
        ],
    )
    counts["accounts"] = write_csv(
        pools.accounts,
        output_dir / "accounts.csv",
        [
            "account_id",
            "account_number",
            "account_type",
            "currency",
            "balance",
            "opened_at",
            "status",
            "country",
            "risk_score",
            "risk_level",
            "last_risk_calculation",
        ],
    )
    counts["transactions"] = write_csv(
        ctx.transactions,
        output_dir / "transactions.csv",
        [
            "transaction_id",
            "amount",
            "currency",
            "timestamp",
            "transaction_type",
            "channel",
            "status",
            "description",
            "country",
            "latitude",
            "longitude",
            "risk_score",
            "is_flagged",
        ],
    )
    counts["devices"] = write_csv(
        pools.devices,
        output_dir / "devices.csv",
        [
            "device_id",
            "device_type",
            "operating_system",
            "browser",
            "fingerprint",
            "first_seen",
            "last_seen",
            "is_emulator",
            "is_rooted",
            "risk_score",
        ],
    )
    counts["ip_addresses"] = write_csv(
        pools.ip_addresses,
        output_dir / "ip_addresses.csv",
        ["ip", "country", "city", "isp", "is_vpn", "is_proxy", "is_tor", "latitude", "longitude", "risk_score"],
    )
    counts["merchants"] = write_csv(
        pools.merchants,
        output_dir / "merchants.csv",
        ["merchant_id", "name", "category", "country", "city", "risk_level", "created_at"],
    )
    counts["phone_numbers"] = write_csv(
        pools.phone_numbers,
        output_dir / "phone_numbers.csv",
        ["phone", "country_code", "verified", "first_seen", "last_seen", "risk_score"],
    )
    counts["email_addresses"] = write_csv(
        pools.email_addresses,
        output_dir / "email_addresses.csv",
        ["email", "domain", "verified", "first_seen", "last_seen", "risk_score"],
    )
    counts["addresses"] = write_csv(
        pools.addresses,
        output_dir / "addresses.csv",
        ["address_id", "street", "city", "postal_code", "country", "latitude", "longitude", "risk_score"],
    )
    counts["customer_accounts"] = write_csv(
        pools.customer_accounts,
        output_dir / "customer_accounts.csv",
        ["customer_id", "account_id"],
    )
    counts["customer_devices"] = write_csv(
        pools.customer_devices + ctx.customer_devices_extra,
        output_dir / "customer_devices.csv",
        ["customer_id", "device_id", "first_seen", "last_seen", "usage_count"],
    )
    counts["customer_phones"] = write_csv(
        pools.customer_phones + ctx.customer_phones_extra,
        output_dir / "customer_phones.csv",
        ["customer_id", "phone", "verified", "first_seen", "last_seen"],
    )
    counts["customer_emails"] = write_csv(
        pools.customer_emails,
        output_dir / "customer_emails.csv",
        ["customer_id", "email", "verified", "first_seen", "last_seen"],
    )
    counts["customer_addresses"] = write_csv(
        pools.customer_addresses + ctx.customer_addresses_extra,
        output_dir / "customer_addresses.csv",
        ["customer_id", "address_id", "from_date", "to_date", "is_current"],
    )
    counts["transaction_sources"] = write_csv(
        ctx.transaction_sources,
        output_dir / "transaction_sources.csv",
        ["transaction_id", "from_account_id", "to_account_id", "device_id", "ip", "merchant_id"],
    )
    counts["fraud_ground_truth"] = write_csv(
        ctx.ground_truth,
        output_dir / "fraud_ground_truth.csv",
        ["entity_id", "entity_type", "fraud_scenario", "expected_risk_level", "fraud_group_id"],
    )

    duration = time.perf_counter() - started
    logger.info("Done in %.1fs. Row counts: %s", duration, counts)


if __name__ == "__main__":
    main()
