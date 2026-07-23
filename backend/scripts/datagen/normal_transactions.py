"""Fills the remainder of the transaction budget with unremarkable activity."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from .context import CHANNELS, TX_STATUSES, TX_TYPES, GenerationContext


def generate_normal_transactions(ctx: GenerationContext, target_count: int) -> None:
    accounts = ctx.pools.accounts
    account_ids = [a["account_id"] for a in accounts]
    if len(account_ids) < 2:
        return

    customer_country = {c["customer_id"]: c["country"] for c in ctx.pools.customers}
    customer_devices_index: dict[str, list[str]] = defaultdict(list)
    for link in ctx.pools.customer_devices:
        customer_devices_index[link["customer_id"]].append(link["device_id"])

    remaining = target_count - len(ctx.transactions)
    for _ in range(max(0, remaining)):
        transaction_type = ctx.rng.choices(TX_TYPES, weights=[35, 30, 15, 15, 5])[0]
        src = ctx.rng.choice(account_ids)
        dst = None
        merchant_id = None
        if transaction_type == "TRANSFER":
            dst = ctx.rng.choice([a for a in account_ids if a != src])
        elif transaction_type == "CARD_PAYMENT":
            merchant_id = ctx.rng.choice(ctx.pools.merchants)["merchant_id"]

        ts = ctx.now - timedelta(
            days=ctx.rng.randint(0, 1800), hours=ctx.rng.randint(0, 23), minutes=ctx.rng.randint(0, 59)
        )
        amount = ctx.rng.lognormvariate(4.5, 1.1)  # skews toward small amounts, occasional large ones
        owner = ctx.pools.account_owner.get(src)
        country = customer_country.get(owner, "XK") if owner else "XK"

        device_id = None
        ip = None
        if owner and ctx.rng.random() < 0.7:
            device_ids = customer_devices_index.get(owner)
            if device_ids:
                device_id = ctx.rng.choice(device_ids)
        if owner and ctx.rng.random() < 0.85:
            # A customer normally transacts from their own home IP -- occasional (~15%) draws
            # from the wider pool model travel/mobile-network variance without making "many
            # unrelated customers sharing an IP" a coincidence that happens constantly by chance.
            ip = ctx.pools.customer_home_ip.get(owner)
        if ip is None and ctx.rng.random() < 0.5:
            ip = ctx.rng.choice(ctx.pools.ip_addresses)["ip"]

        ctx.add_transaction(
            from_account_id=src,
            to_account_id=dst,
            amount=round(min(amount, 15000), 2),
            timestamp=ts,
            transaction_type=transaction_type,
            channel=ctx.rng.choices(CHANNELS, weights=[45, 30, 10, 10, 5])[0],
            status=ctx.rng.choices(TX_STATUSES, weights=[92, 3, 4, 1])[0],
            country=country,
            device_id=device_id,
            ip=ip,
            merchant_id=merchant_id,
            is_flagged=False,
            risk_score=0,
        )
