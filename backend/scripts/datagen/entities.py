"""Generation of the base entity pools and their normal (non-fraud) linking.

Fraud scenarios (see `scenarios.py`) layer additional entities, links, and
transactions on top of what this module produces, and may reserve some of the
pools created here (e.g. dedicated "ring" devices) before normal linking
consumes them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from faker import Faker

from .config import GeneratorConfig

KYC_STATUSES = ["VERIFIED", "PENDING", "REJECTED"]
CUSTOMER_STATUSES = ["ACTIVE", "DORMANT", "CLOSED"]
ACCOUNT_TYPES = ["CHECKING", "SAVINGS", "BUSINESS", "CRYPTO"]
ACCOUNT_STATUSES = ["ACTIVE", "FROZEN", "CLOSED"]
DEVICE_TYPES = ["MOBILE", "DESKTOP", "TABLET"]
OS_CHOICES = ["Android", "iOS", "Windows", "macOS", "Linux"]
BROWSER_CHOICES = ["Chrome", "Safari", "Firefox", "Edge", "Samsung Internet"]
MERCHANT_CATEGORIES = [
    "GROCERY",
    "ELECTRONICS",
    "TRAVEL",
    "GAMING",
    "JEWELRY",
    "MONEY_SERVICE",
    "RESTAURANT",
    "FASHION",
    "CRYPTO_EXCHANGE",
    "UTILITIES",
]


@dataclass
class EntityPools:
    customers: list[dict[str, Any]] = field(default_factory=list)
    accounts: list[dict[str, Any]] = field(default_factory=list)
    devices: list[dict[str, Any]] = field(default_factory=list)
    ip_addresses: list[dict[str, Any]] = field(default_factory=list)
    merchants: list[dict[str, Any]] = field(default_factory=list)
    phone_numbers: list[dict[str, Any]] = field(default_factory=list)
    email_addresses: list[dict[str, Any]] = field(default_factory=list)
    addresses: list[dict[str, Any]] = field(default_factory=list)

    customer_accounts: list[dict[str, Any]] = field(default_factory=list)
    customer_devices: list[dict[str, Any]] = field(default_factory=list)
    customer_phones: list[dict[str, Any]] = field(default_factory=list)
    customer_emails: list[dict[str, Any]] = field(default_factory=list)
    customer_addresses: list[dict[str, Any]] = field(default_factory=list)

    # account_id -> customer_id, used by scenario builders
    account_owner: dict[str, str] = field(default_factory=dict)
    customer_accounts_index: dict[str, list[str]] = field(default_factory=dict)
    # customer_id -> ip, the IP a customer normally transacts from (mirrors real ISP/home-network
    # stickiness); normal transaction generation uses this instead of a uniform-random IP draw so
    # that "many unrelated customers sharing an IP" stays a meaningful, rare signal rather than
    # something that happens constantly by chance across a small IP pool.
    customer_home_ip: dict[str, str] = field(default_factory=dict)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_entity_pools(cfg: GeneratorConfig) -> EntityPools:
    rng = random.Random(cfg.seed)
    faker = Faker()
    Faker.seed(cfg.seed)

    pools = EntityPools()
    now = datetime(2026, 7, 1)

    # ---- Addresses ----
    for i in range(cfg.addresses):
        country = rng.choices(cfg.countries, weights=[40] + [8] * (len(cfg.countries) - 1))[0]
        pools.addresses.append(
            {
                "address_id": f"ADDR-{cfg.id_prefix}{i + 1:06d}",
                "street": faker.street_address(),
                "city": faker.city(),
                "postal_code": faker.postcode(),
                "country": country,
                "latitude": round(rng.uniform(-60, 65), 6),
                "longitude": round(rng.uniform(-120, 120), 6),
                "risk_score": 0,
            }
        )

    # ---- Phone numbers ----
    seen_phones: set[str] = set()
    while len(pools.phone_numbers) < cfg.phone_numbers:
        country_code = rng.choice(["+383", "+355", "+389", "+49", "+41", "+43", "+39", "+1", "+44", "+90"])
        number = f"{country_code}{rng.randint(10_000_000, 99_999_999)}"
        if number in seen_phones:
            continue
        seen_phones.add(number)
        first_seen = now - timedelta(days=rng.randint(30, 1500))
        pools.phone_numbers.append(
            {
                "phone": number,
                "country_code": country_code,
                "verified": rng.random() > 0.15,
                "first_seen": _iso(first_seen),
                "last_seen": _iso(first_seen + timedelta(days=rng.randint(0, 1400))),
                "risk_score": 0,
            }
        )

    # ---- Email addresses ----
    seen_emails: set[str] = set()
    domains = ["gmail.com", "outlook.com", "yahoo.com", "protonmail.com", "hotmail.com"]
    while len(pools.email_addresses) < cfg.email_addresses:
        local = faker.user_name() + str(rng.randint(1, 9999))
        domain = rng.choice(domains)
        email = f"{local}@{domain}"
        if email in seen_emails:
            continue
        seen_emails.add(email)
        first_seen = now - timedelta(days=rng.randint(30, 1500))
        pools.email_addresses.append(
            {
                "email": email,
                "domain": domain,
                "verified": rng.random() > 0.1,
                "first_seen": _iso(first_seen),
                "last_seen": _iso(first_seen + timedelta(days=rng.randint(0, 1400))),
                "risk_score": 0,
            }
        )

    # ---- Devices ----
    for i in range(cfg.devices):
        first_seen = now - timedelta(days=rng.randint(30, 1500))
        pools.devices.append(
            {
                "device_id": f"DEV-{cfg.id_prefix}{i + 1:06d}",
                "device_type": rng.choice(DEVICE_TYPES),
                "operating_system": rng.choice(OS_CHOICES),
                "browser": rng.choice(BROWSER_CHOICES),
                "fingerprint": faker.sha1()[:16],
                "first_seen": _iso(first_seen),
                "last_seen": _iso(first_seen + timedelta(days=rng.randint(0, 1400))),
                "is_emulator": rng.random() < 0.02,
                "is_rooted": rng.random() < 0.02,
                "risk_score": 0,
            }
        )

    # ---- IP addresses ----
    for _ in range(cfg.ip_addresses):
        is_vpn = rng.random() < 0.05
        is_proxy = rng.random() < 0.03
        is_tor = rng.random() < 0.01
        country = rng.choices(cfg.countries, weights=[40] + [8] * (len(cfg.countries) - 1))[0]
        pools.ip_addresses.append(
            {
                "ip": faker.unique.ipv4_public(),
                "country": country,
                "city": faker.city(),
                "isp": faker.company() + " Telecom",
                "is_vpn": is_vpn,
                "is_proxy": is_proxy,
                "is_tor": is_tor,
                "latitude": round(rng.uniform(-60, 65), 6),
                "longitude": round(rng.uniform(-120, 120), 6),
                "risk_score": 0,
            }
        )
    faker.unique.clear()

    # ---- Merchants ----
    for i in range(cfg.merchants):
        pools.merchants.append(
            {
                "merchant_id": f"MER-{cfg.id_prefix}{i + 1:05d}",
                "name": faker.company(),
                "category": rng.choice(MERCHANT_CATEGORIES),
                "country": rng.choice(cfg.countries),
                "city": faker.city(),
                "risk_level": "LOW",
                "created_at": _iso(now - timedelta(days=rng.randint(60, 2000))),
            }
        )

    # ---- Customers ----
    for i in range(cfg.customers):
        customer_id = f"CUS-{cfg.id_prefix}{i + 1:06d}"
        country = rng.choices(cfg.countries, weights=[55] + [5] * (len(cfg.countries) - 1))[0]
        registration = now - timedelta(days=rng.randint(10, 1800))
        address = rng.choice(pools.addresses)
        pools.customers.append(
            {
                "customer_id": customer_id,
                "full_name": faker.name(),
                "email": "",  # populated via customer_emails link, kept for CSV completeness
                "phone": "",
                "date_of_birth": faker.date_of_birth(minimum_age=18, maximum_age=85).isoformat(),
                "country": country,
                "city": address["city"],
                "postal_code": address["postal_code"],
                "address": address["street"],
                "registration_date": _iso(registration),
                "kyc_status": rng.choices(KYC_STATUSES, weights=[80, 15, 5])[0],
                "customer_status": rng.choices(CUSTOMER_STATUSES, weights=[85, 10, 5])[0],
                "fraud_status": "CLEAR",
                "created_at": _iso(registration),
                "updated_at": _iso(registration),
            }
        )

        email = rng.choice(pools.email_addresses)
        phone = rng.choice(pools.phone_numbers)
        pools.customers[-1]["email"] = email["email"]
        pools.customers[-1]["phone"] = phone["phone"]
        pools.customer_emails.append(
            {
                "customer_id": customer_id,
                "email": email["email"],
                "verified": email["verified"],
                "first_seen": email["first_seen"],
                "last_seen": email["last_seen"],
            }
        )
        pools.customer_phones.append(
            {
                "customer_id": customer_id,
                "phone": phone["phone"],
                "verified": phone["verified"],
                "first_seen": phone["first_seen"],
                "last_seen": phone["last_seen"],
            }
        )
        pools.customer_addresses.append(
            {
                "customer_id": customer_id,
                "address_id": address["address_id"],
                "from_date": _iso(registration),
                "to_date": "",
                "is_current": True,
            }
        )

        device = rng.choice(pools.devices)
        pools.customer_devices.append(
            {
                "customer_id": customer_id,
                "device_id": device["device_id"],
                "first_seen": device["first_seen"],
                "last_seen": device["last_seen"],
                "usage_count": rng.randint(5, 400),
            }
        )
        pools.customer_home_ip[customer_id] = rng.choice(pools.ip_addresses)["ip"]

    # ---- Accounts (1-3 per customer, targeting cfg.accounts total) ----
    account_counter = 0
    customer_ids = [c["customer_id"] for c in pools.customers]
    remaining_accounts = cfg.accounts
    for idx, customer_id in enumerate(customer_ids):
        customers_left = len(customer_ids) - idx
        # ensure every remaining customer can still get at least 1 account
        max_extra = max(0, remaining_accounts - customers_left)
        n_accounts = 1 + (1 if max_extra > 0 and rng.random() < 0.35 else 0)
        n_accounts = min(n_accounts, remaining_accounts, 3)
        n_accounts = max(n_accounts, 1) if remaining_accounts > 0 else 0
        owner = next(c for c in pools.customers if c["customer_id"] == customer_id)
        for _ in range(n_accounts):
            account_counter += 1
            account_id = f"ACC-{cfg.id_prefix}{account_counter:06d}"
            opened = now - timedelta(days=rng.randint(5, 1700))
            account = {
                "account_id": account_id,
                "account_number": faker.iban(),
                "account_type": rng.choices(ACCOUNT_TYPES, weights=[50, 30, 15, 5])[0],
                "currency": "EUR",
                "balance": round(rng.uniform(0, 25000), 2),
                "opened_at": _iso(opened),
                "status": rng.choices(ACCOUNT_STATUSES, weights=[90, 5, 5])[0],
                "country": owner["country"],
                "risk_score": 0,
                "risk_level": "LOW",
                "last_risk_calculation": _iso(now),
            }
            pools.accounts.append(account)
            pools.account_owner[account_id] = customer_id
            pools.customer_accounts_index.setdefault(customer_id, []).append(account_id)
            pools.customer_accounts.append({"customer_id": customer_id, "account_id": account_id})
            remaining_accounts -= 1

    return pools
