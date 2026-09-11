import hashlib
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AgentIdentity, Payment, PaymentStatus, RiskLevel, utc_now

DEMO_AGENT_DATA = [
    ("0x1111111111111111111111111111111111111111", "Procurement Agent", "verified", 96),
    ("0x2222222222222222222222222222222222222222", "Compute Marketplace", "verified", 92),
    ("0x3333333333333333333333333333333333333333", "Data Licensing Agent", "verified", 88),
    ("0x9999999999999999999999999999999999999999", "Untrusted Relay", "watchlist", 12),
]


def fake_hash(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode()).hexdigest()


async def seed_database(session: AsyncSession, include_payments: bool) -> None:
    agents = [
        AgentIdentity(address=address, name=name, status=status, trust_score=score)
        for address, name, status, score in DEMO_AGENT_DATA
    ]
    if not await session.scalar(select(func.count()).select_from(AgentIdentity)):
        session.add_all(agents)

    if include_payments and not await session.scalar(select(func.count()).select_from(Payment)):
        now = utc_now()
        session.add_all(
            [
                Payment(
                    payment_id=fake_hash("payment-compute"),
                    sender=agents[0].address,
                    receiver=agents[1].address,
                    amount_units="4200000",
                    metadata_hash=fake_hash("gpu-inference"),
                    description="GPU inference batch settlement",
                    deposit_tx_hash=fake_hash("tx-compute"),
                    resolution_tx_hash=fake_hash("resolution-compute"),
                    deposited_at=now - timedelta(seconds=42),
                    recall_deadline=now - timedelta(seconds=12),
                    status=PaymentStatus.EXECUTED,
                    decision="execute",
                    risk_score=8,
                    risk_level=RiskLevel.LOW,
                    risk_reasons=["Verified counterparties and normal payment behavior"],
                    decision_latency_ms=184,
                    source="simulation",
                ),
                Payment(
                    payment_id=fake_hash("payment-data"),
                    sender=agents[2].address,
                    receiver=agents[1].address,
                    amount_units="18500000",
                    metadata_hash=fake_hash("dataset-license"),
                    description="Autonomous dataset license",
                    deposit_tx_hash=fake_hash("tx-data"),
                    resolution_tx_hash=fake_hash("resolution-data"),
                    deposited_at=now - timedelta(minutes=2),
                    recall_deadline=now - timedelta(seconds=90),
                    status=PaymentStatus.EXECUTED,
                    decision="execute",
                    risk_score=27,
                    risk_level=RiskLevel.LOW,
                    risk_reasons=["Amount is above the normal micropayment range"],
                    decision_latency_ms=231,
                    source="simulation",
                ),
                Payment(
                    payment_id=fake_hash("payment-fraud"),
                    sender=agents[3].address,
                    receiver=agents[1].address,
                    amount_units="82000000",
                    metadata_hash=fake_hash("suspicious-relay"),
                    description="High-volume proxy service",
                    deposit_tx_hash=fake_hash("tx-fraud"),
                    resolution_tx_hash=fake_hash("resolution-fraud"),
                    deposited_at=now - timedelta(minutes=4),
                    recall_deadline=now - timedelta(minutes=3, seconds=30),
                    status=PaymentStatus.RECALLED,
                    decision="recall",
                    risk_score=100,
                    risk_level=RiskLevel.HIGH,
                    risk_reasons=[
                        "Sender is on the agent watchlist",
                        "Amount is above the high-value agent payment threshold",
                    ],
                    decision_latency_ms=197,
                    source="simulation",
                ),
            ]
        )
    await session.commit()
