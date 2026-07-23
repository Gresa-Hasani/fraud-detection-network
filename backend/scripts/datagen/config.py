"""Configuration for the synthetic fraud dataset generator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GeneratorConfig:
    customers: int = 5000
    accounts: int = 7000
    transactions: int = 50000
    devices: int = 6000
    ip_addresses: int = 4000
    merchants: int = 500
    phone_numbers: int = 6000
    email_addresses: int = 6000
    addresses: int = 5000
    fraud_rate: float = 0.03
    seed: int = 42

    # Non-empty for fixture/test datasets so their sequential IDs (CUS-000001, TX-0000001, ...)
    # can never collide with a default (unprefixed) generation run merged into the same database.
    id_prefix: str = ""

    countries: tuple[str, ...] = (
        "XK",
        "AL",
        "MK",
        "DE",
        "CH",
        "AT",
        "IT",
        "US",
        "GB",
        "TR",
    )
    high_risk_countries: tuple[str, ...] = ("RU", "NG", "IR", "KP", "VE")
    home_country: str = "XK"
