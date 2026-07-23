"""Builders for the ten intentional fraud scenarios injected into the dataset.

Each function mutates the shared `GenerationContext`: it adds transactions
(and their source links), may add extra device/IP/address/phone sharing
links, flips `fraud_status` on the customers involved, and always appends
rows to `ctx.ground_truth` so detection results can later be scored against
a known answer key.
"""

from __future__ import annotations

from datetime import timedelta

from .context import GenerationContext


def _pick_unused_customers(ctx: GenerationContext, used: set[str], n: int) -> list[str]:
    available = [c["customer_id"] for c in ctx.pools.customers if c["customer_id"] not in used]
    chosen = ctx.rng.sample(available, min(n, len(available)))
    used.update(chosen)
    return chosen


def _first_account(ctx: GenerationContext, customer_id: str) -> str:
    return ctx.pools.customer_accounts_index[customer_id][0]


def scenario_shared_device_ring(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 1: 8-20 unrelated customers sharing one (often emulator/rooted) device."""
    group_id = f"FRD-DEVICE-{group_no:03d}"
    ring_size = ctx.rng.randint(8, 20)
    members = _pick_unused_customers(ctx, used, ring_size)
    if len(members) < 5:
        return

    device = ctx.rng.choice(ctx.pools.devices)
    device["is_emulator"] = ctx.rng.random() < 0.6
    device["is_rooted"] = ctx.rng.random() < 0.5
    device["risk_score"] = 80

    mule = members[-1]
    mule_account = _first_account(ctx, mule)

    for member in members:
        first_seen = ctx.now - timedelta(days=ctx.rng.randint(1, 30))
        ctx.customer_devices_extra.append(
            {
                "customer_id": member,
                "device_id": device["device_id"],
                "first_seen": first_seen.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "last_seen": ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "usage_count": ctx.rng.randint(1, 20),
            }
        )
        ctx.mark_customer_fraud_status(member, "SUSPICIOUS")
        ctx.add_ground_truth(member, "Customer", "SHARED_DEVICE_RING", "HIGH", group_id)
        ctx.add_ground_truth(_first_account(ctx, member), "Account", "SHARED_DEVICE_RING", "HIGH", group_id)

        if member != mule:
            account = _first_account(ctx, member)
            ts = ctx.now - timedelta(days=ctx.rng.randint(0, 20), hours=ctx.rng.randint(0, 23))
            ctx.add_transaction(
                from_account_id=account,
                to_account_id=mule_account,
                amount=ctx.rng.uniform(200, 3000),
                timestamp=ts,
                transaction_type="TRANSFER",
                channel="MOBILE",
                device_id=device["device_id"],
                is_flagged=True,
                risk_score=70,
                description="Ring member transfer to mule account",
            )

    ctx.mark_customer_fraud_status(mule, "CONFIRMED_FRAUD")
    ctx.add_ground_truth(device["device_id"], "Device", "SHARED_DEVICE_RING", "CRITICAL", group_id)


def scenario_shared_ip(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 2: many unrelated customers transacting from the same risky IP."""
    group_id = f"FRD-IP-{group_no:03d}"
    ring_size = ctx.rng.randint(8, 18)
    members = _pick_unused_customers(ctx, used, ring_size)
    if len(members) < 5:
        return

    ip = ctx.rng.choice(ctx.pools.ip_addresses)
    ip["is_vpn"] = True
    ip["is_proxy"] = ctx.rng.random() < 0.5
    ip["is_tor"] = ctx.rng.random() < 0.2
    ip["country"] = ctx.rng.choice(["RU", "NG", "IR"])
    ip["risk_score"] = 85

    for member in members:
        account = _first_account(ctx, member)
        ts = ctx.now - timedelta(days=ctx.rng.randint(0, 25), hours=ctx.rng.randint(0, 23))
        ctx.add_transaction(
            from_account_id=account,
            to_account_id=None,
            amount=ctx.rng.uniform(50, 1500),
            timestamp=ts,
            transaction_type=ctx.rng.choice(["CARD_PAYMENT", "CRYPTO_TRANSFER"]),
            channel="WEB",
            ip=ip["ip"],
            is_flagged=True,
            risk_score=65,
            description="Transaction originated from shared high-risk IP",
        )
        ctx.mark_customer_fraud_status(member, "SUSPICIOUS")
        ctx.add_ground_truth(member, "Customer", "SHARED_IP", "MEDIUM", group_id)
        ctx.add_ground_truth(account, "Account", "SHARED_IP", "MEDIUM", group_id)

    ctx.add_ground_truth(ip["ip"], "IPAddress", "SHARED_IP", "CRITICAL", group_id)


def scenario_circular_transfers(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 3: A -> B -> C -> ... -> A cycles of length 3-6, similar amounts, short window."""
    group_id = f"FRD-CYCLE-{group_no:03d}"
    cycle_len = ctx.rng.randint(3, 6)
    members = _pick_unused_customers(ctx, used, cycle_len)
    if len(members) < 3:
        return

    accounts = [_first_account(ctx, m) for m in members]
    base_amount = ctx.rng.uniform(1000, 8000)
    ts = ctx.now - timedelta(days=ctx.rng.randint(0, 15))

    for i in range(len(accounts)):
        src = accounts[i]
        dst = accounts[(i + 1) % len(accounts)]
        amount = base_amount * ctx.rng.uniform(0.95, 1.05)
        ts = ts + timedelta(minutes=ctx.rng.randint(5, 45))  # strictly increasing -- each hop follows the last
        ctx.add_transaction(
            from_account_id=src,
            to_account_id=dst,
            amount=amount,
            timestamp=ts,
            transaction_type="TRANSFER",
            channel="WEB",
            is_flagged=True,
            risk_score=90,
            description=f"Circular transfer step {i + 1}/{len(accounts)}",
        )

    for member, account in zip(members, accounts, strict=False):
        ctx.mark_customer_fraud_status(member, "SUSPICIOUS")
        ctx.add_ground_truth(member, "Customer", "CIRCULAR_TRANSFER", "HIGH", group_id)
        ctx.add_ground_truth(account, "Account", "CIRCULAR_TRANSFER", "CRITICAL", group_id)


def scenario_rapid_pass_through(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 4: receive a large sum and forward most of it within 30 minutes."""
    group_id = f"FRD-RAPID-{group_no:03d}"
    members = _pick_unused_customers(ctx, used, 3)
    if len(members) < 3:
        return

    source, pass_through, destination = members[0], members[1], members[2]
    src_acc = _first_account(ctx, source)
    mid_acc = _first_account(ctx, pass_through)
    dst_acc = _first_account(ctx, destination)

    incoming = ctx.rng.uniform(5000, 20000)
    outgoing = incoming * ctx.rng.uniform(0.9, 0.97)
    ts_in = ctx.now - timedelta(days=ctx.rng.randint(0, 20), hours=ctx.rng.randint(0, 20))
    ts_out = ts_in + timedelta(minutes=ctx.rng.randint(3, 29))

    ctx.add_transaction(
        from_account_id=src_acc,
        to_account_id=mid_acc,
        amount=incoming,
        timestamp=ts_in,
        transaction_type="TRANSFER",
        is_flagged=True,
        risk_score=80,
        description="Large inbound transfer preceding rapid pass-through",
    )
    ctx.add_transaction(
        from_account_id=mid_acc,
        to_account_id=dst_acc,
        amount=outgoing,
        timestamp=ts_out,
        transaction_type="TRANSFER",
        is_flagged=True,
        risk_score=85,
        description="Rapid forwarding of received funds",
    )

    ctx.mark_customer_fraud_status(pass_through, "SUSPICIOUS")
    ctx.add_ground_truth(pass_through, "Customer", "RAPID_PASS_THROUGH", "HIGH", group_id)
    ctx.add_ground_truth(mid_acc, "Account", "RAPID_PASS_THROUGH", "CRITICAL", group_id)


def scenario_fan_in(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 5: many source accounts funnel money into one destination account."""
    group_id = f"FRD-FANIN-{group_no:03d}"
    n_sources = ctx.rng.randint(15, 25)
    members = _pick_unused_customers(ctx, used, n_sources + 1)
    if len(members) < 10:
        return

    destination, sources = members[0], members[1:]
    dst_acc = _first_account(ctx, destination)
    start = ctx.now - timedelta(hours=ctx.rng.randint(1, 20))

    for source in sources:
        src_acc = _first_account(ctx, source)
        ts = start + timedelta(minutes=ctx.rng.randint(0, 180))
        ctx.add_transaction(
            from_account_id=src_acc,
            to_account_id=dst_acc,
            amount=ctx.rng.uniform(300, 4000),
            timestamp=ts,
            transaction_type="TRANSFER",
            is_flagged=True,
            risk_score=60,
            description="Fan-in contribution",
        )
        ctx.add_ground_truth(src_acc, "Account", "FAN_IN", "MEDIUM", group_id)

    ctx.mark_customer_fraud_status(destination, "SUSPICIOUS")
    ctx.add_ground_truth(destination, "Customer", "FAN_IN", "HIGH", group_id)
    ctx.add_ground_truth(dst_acc, "Account", "FAN_IN", "CRITICAL", group_id)


def scenario_fan_out(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 6: one source account distributes money to many destination accounts."""
    group_id = f"FRD-FANOUT-{group_no:03d}"
    n_targets = ctx.rng.randint(12, 18)
    members = _pick_unused_customers(ctx, used, n_targets + 1)
    if len(members) < 8:
        return

    source, targets = members[0], members[1:]
    src_acc = _first_account(ctx, source)
    start = ctx.now - timedelta(hours=ctx.rng.randint(1, 20))

    for target in targets:
        dst_acc = _first_account(ctx, target)
        ts = start + timedelta(minutes=ctx.rng.randint(0, 180))
        ctx.add_transaction(
            from_account_id=src_acc,
            to_account_id=dst_acc,
            amount=ctx.rng.uniform(200, 2500),
            timestamp=ts,
            transaction_type="TRANSFER",
            is_flagged=True,
            risk_score=60,
            description="Fan-out distribution",
        )
        ctx.add_ground_truth(dst_acc, "Account", "FAN_OUT", "MEDIUM", group_id)

    ctx.mark_customer_fraud_status(source, "SUSPICIOUS")
    ctx.add_ground_truth(source, "Customer", "FAN_OUT", "HIGH", group_id)
    ctx.add_ground_truth(src_acc, "Account", "FAN_OUT", "CRITICAL", group_id)


def scenario_account_takeover(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 7: new device + foreign/proxy IP + high-value transaction at an odd hour."""
    group_id = f"FRD-ATO-{group_no:03d}"
    members = _pick_unused_customers(ctx, used, 1)
    if not members:
        return
    victim = members[0]
    account = _first_account(ctx, victim)

    odd_hour_ts = (ctx.now - timedelta(days=ctx.rng.randint(0, 10))).replace(
        hour=ctx.rng.choice([2, 3, 4]), minute=ctx.rng.randint(0, 59)
    )

    new_device = ctx.rng.choice(ctx.pools.devices)
    # Backdate first_seen to just before the takeover transaction -- this must actually be a
    # "new" device at the moment of the transaction, not a random pre-existing one, or FD-008's
    # device-age check (first seen within N days of the transaction) never fires.
    new_device["first_seen"] = (odd_hour_ts - timedelta(hours=ctx.rng.randint(1, 36))).strftime("%Y-%m-%dT%H:%M:%SZ")
    ip = ctx.rng.choice(ctx.pools.ip_addresses)
    ip["is_proxy"] = True
    ip["country"] = ctx.rng.choice(["RU", "NG", "IR", "KP"])
    ip["risk_score"] = 75
    ctx.add_transaction(
        from_account_id=account,
        to_account_id=None,
        amount=ctx.rng.uniform(8000, 18000),
        timestamp=odd_hour_ts,
        transaction_type="TRANSFER",
        channel="WEB",
        device_id=new_device["device_id"],
        ip=ip["ip"],
        country=ip["country"],
        is_flagged=True,
        risk_score=95,
        description="High-value transfer from unrecognized device/IP shortly after login",
    )

    ctx.mark_customer_fraud_status(victim, "UNDER_INVESTIGATION")
    ctx.add_ground_truth(victim, "Customer", "ACCOUNT_TAKEOVER", "CRITICAL", group_id)
    ctx.add_ground_truth(account, "Account", "ACCOUNT_TAKEOVER", "CRITICAL", group_id)


def scenario_merchant_collusion(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 8: a merchant receiving repeated round-amount payments from a connected group."""
    group_id = f"FRD-MERCH-{group_no:03d}"
    members = _pick_unused_customers(ctx, used, ctx.rng.randint(6, 10))
    if len(members) < 4:
        return

    merchant = ctx.rng.choice(ctx.pools.merchants)
    merchant["risk_level"] = "HIGH"
    round_amounts = [500, 1000, 1500, 2000, 2500]

    for member in members:
        account = _first_account(ctx, member)
        for _ in range(ctx.rng.randint(2, 4)):
            ts = ctx.now - timedelta(days=ctx.rng.randint(0, 60))
            status = "REVERSED" if ctx.rng.random() < 0.25 else "COMPLETED"
            ctx.add_transaction(
                from_account_id=account,
                to_account_id=None,
                amount=ctx.rng.choice(round_amounts),
                timestamp=ts,
                transaction_type="CARD_PAYMENT",
                merchant_id=merchant["merchant_id"],
                status=status,
                is_flagged=True,
                risk_score=55,
                description="Round-amount payment to high-risk merchant",
            )
        ctx.add_ground_truth(account, "Account", "MERCHANT_COLLUSION", "MEDIUM", group_id)

    ctx.add_ground_truth(merchant["merchant_id"], "Merchant", "MERCHANT_COLLUSION", "HIGH", group_id)


def scenario_structuring(ctx: GenerationContext, used: set[str], group_no: int) -> None:
    """Scenario 9: several transfers just below a reporting threshold in a short window."""
    group_id = f"FRD-STRUCT-{group_no:03d}"
    members = _pick_unused_customers(ctx, used, 1)
    if not members:
        return
    customer = members[0]
    account = _first_account(ctx, customer)
    threshold = 10000.0
    start = ctx.now - timedelta(days=ctx.rng.randint(0, 10))

    for i, offset in enumerate([300, 200, 100]):
        ts = start + timedelta(hours=i * ctx.rng.randint(2, 10))
        ctx.add_transaction(
            from_account_id=account,
            to_account_id=None,
            amount=threshold - offset - ctx.rng.uniform(0, 50),
            timestamp=ts,
            transaction_type="CASH_WITHDRAWAL",
            channel="ATM",
            is_flagged=True,
            risk_score=75,
            description="Withdrawal just below reporting threshold",
        )

    ctx.mark_customer_fraud_status(customer, "SUSPICIOUS")
    ctx.add_ground_truth(customer, "Customer", "STRUCTURING", "HIGH", group_id)
    ctx.add_ground_truth(account, "Account", "STRUCTURING", "HIGH", group_id)


def scenario_fraud_proximity(
    ctx: GenerationContext, used: set[str], group_no: int, confirmed_fraud_pool: list[str]
) -> None:
    """Scenario 10: an otherwise-normal customer sits 1-3 hops from a confirmed fraudster."""
    group_id = f"FRD-PROX-{group_no:03d}"
    if not confirmed_fraud_pool:
        return
    fraudster = ctx.rng.choice(confirmed_fraud_pool)
    members = _pick_unused_customers(ctx, used, 1)
    if not members:
        return
    normal_customer = members[0]

    link_type = ctx.rng.choice(["address", "phone", "transaction"])
    if link_type == "address":
        addr_id = ctx.pools.customer_addresses[0]["address_id"]
        for entry in ctx.pools.customer_addresses:
            if entry["customer_id"] == fraudster:
                addr_id = entry["address_id"]
                break
        ctx.customer_addresses_extra.append(
            {
                "customer_id": normal_customer,
                "address_id": addr_id,
                "from_date": ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to_date": "",
                "is_current": True,
            }
        )
    elif link_type == "phone":
        phone = next(
            (e["phone"] for e in ctx.pools.customer_phones if e["customer_id"] == fraudster),
            ctx.pools.phone_numbers[0]["phone"],
        )
        ctx.customer_phones_extra.append(
            {
                "customer_id": normal_customer,
                "phone": phone,
                "verified": False,
                "first_seen": ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "last_seen": ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    else:
        normal_acc = _first_account(ctx, normal_customer)
        fraud_acc = _first_account(ctx, fraudster)
        ts = ctx.now - timedelta(days=ctx.rng.randint(0, 30))
        ctx.add_transaction(
            from_account_id=normal_acc,
            to_account_id=fraud_acc,
            amount=ctx.rng.uniform(50, 500),
            timestamp=ts,
            transaction_type="TRANSFER",
            risk_score=20,
            description="One-hop transaction link to a confirmed fraud account",
        )

    ctx.add_ground_truth(normal_customer, "Customer", "FRAUD_PROXIMITY", "LOW", group_id)


def run_all_scenarios(ctx: GenerationContext, target_fraud_customers: int) -> set[str]:
    """Run every scenario repeatedly until roughly `target_fraud_customers` are touched."""
    used: set[str] = set()
    confirmed_fraud_pool: list[str] = []
    group_no = 1

    builders = [
        scenario_shared_device_ring,
        scenario_shared_ip,
        scenario_circular_transfers,
        scenario_rapid_pass_through,
        scenario_fan_in,
        scenario_fan_out,
        scenario_account_takeover,
        scenario_merchant_collusion,
        scenario_structuring,
    ]

    while len(used) < target_fraud_customers:
        builder = builders[(group_no - 1) % len(builders)]
        before = len(used)
        builder(ctx, used, group_no)
        if len(used) == before:
            break  # ran out of customers to allocate
        group_no += 1

    confirmed_fraud_pool = [c["customer_id"] for c in ctx.pools.customers if c["fraud_status"] == "CONFIRMED_FRAUD"]
    n_proximity = max(1, target_fraud_customers // 10)
    for _ in range(n_proximity):
        before = len(used)
        scenario_fraud_proximity(ctx, used, group_no, confirmed_fraud_pool)
        if len(used) == before:
            break
        group_no += 1

    return used
