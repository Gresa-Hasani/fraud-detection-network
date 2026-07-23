"""Shared mutable generation context passed between entity and scenario builders."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from faker import Faker

from .entities import EntityPools

TX_STATUSES = ["COMPLETED", "PENDING", "FAILED", "REVERSED"]
TX_TYPES = ["TRANSFER", "CARD_PAYMENT", "CASH_WITHDRAWAL", "DEPOSIT", "CRYPTO_TRANSFER"]
CHANNELS = ["MOBILE", "WEB", "ATM", "BRANCH", "API"]


@dataclass
class GenerationContext:
    pools: EntityPools
    rng: random.Random
    faker: Faker
    now: datetime
    id_prefix: str = ""

    transactions: list[dict[str, Any]] = field(default_factory=list)
    transaction_sources: list[dict[str, Any]] = field(default_factory=list)
    ground_truth: list[dict[str, Any]] = field(default_factory=list)
    customer_devices_extra: list[dict[str, Any]] = field(default_factory=list)
    customer_addresses_extra: list[dict[str, Any]] = field(default_factory=list)
    customer_phones_extra: list[dict[str, Any]] = field(default_factory=list)

    _tx_counter: int = 0

    def next_transaction_id(self) -> str:
        self._tx_counter += 1
        return f"TX-{self.id_prefix}{self._tx_counter:07d}"

    def add_transaction(
        self,
        *,
        from_account_id: str | None,
        to_account_id: str | None,
        amount: float,
        timestamp: datetime,
        transaction_type: str,
        channel: str = "WEB",
        status: str = "COMPLETED",
        description: str = "",
        country: str = "XK",
        device_id: str | None = None,
        ip: str | None = None,
        merchant_id: str | None = None,
        is_flagged: bool = False,
        risk_score: int = 0,
    ) -> str:
        tx_id = self.next_transaction_id()
        self.transactions.append(
            {
                "transaction_id": tx_id,
                "amount": round(amount, 2),
                "currency": "EUR",
                "timestamp": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "transaction_type": transaction_type,
                "channel": channel,
                "status": status,
                "description": description,
                "country": country,
                "latitude": round(self.rng.uniform(-60, 65), 6),
                "longitude": round(self.rng.uniform(-120, 120), 6),
                "risk_score": risk_score,
                "is_flagged": is_flagged,
            }
        )
        self.transaction_sources.append(
            {
                "transaction_id": tx_id,
                "from_account_id": from_account_id or "",
                "to_account_id": to_account_id or "",
                "device_id": device_id or "",
                "ip": ip or "",
                "merchant_id": merchant_id or "",
            }
        )
        return tx_id

    def add_ground_truth(
        self, entity_id: str, entity_type: str, scenario: str, expected_risk_level: str, group_id: str
    ) -> None:
        self.ground_truth.append(
            {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "fraud_scenario": scenario,
                "expected_risk_level": expected_risk_level,
                "fraud_group_id": group_id,
            }
        )

    def mark_customer_fraud_status(self, customer_id: str, status: str) -> None:
        for customer in self.pools.customers:
            if customer["customer_id"] == customer_id:
                # CONFIRMED_FRAUD takes priority over weaker statuses if already set.
                if status == "CONFIRMED_FRAUD" or customer["fraud_status"] == "CLEAR":
                    customer["fraud_status"] = status
                return
