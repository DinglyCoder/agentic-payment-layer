from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.fraud import FraudEngine
from app.models import (
    AgentIdentity,
    Base,
    Payment,
    PaymentStatus,
    RegistryStatus,
    utc_now,
)

SENDER = "0x1111111111111111111111111111111111111111"
RECEIVER = "0x2222222222222222222222222222222222222222"
WATCHLIST = "0x9999999999999999999999999999999999999999"


def payment(sender: str = SENDER, amount: int = 1_000_000) -> Payment:
    now = utc_now()
    return Payment(
        payment_id="0x" + "a" * 64,
        sender=sender,
        receiver=RECEIVER,
        amount_units=str(amount),
        metadata_hash="0x" + "b" * 64,
        description="Compute service",
        deposit_tx_hash="0x" + "c" * 64,
        deposited_at=now,
        recall_deadline=now + timedelta(seconds=30),
        status=PaymentStatus.SCORING,
        source="test",
    )


async def test_verified_micropayment_is_low_risk():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all(
            [
                AgentIdentity(
                    address=SENDER,
                    name="Buyer",
                    status=RegistryStatus.VERIFIED,
                    trust_score=95,
                ),
                AgentIdentity(
                    address=RECEIVER,
                    name="Seller",
                    status=RegistryStatus.VERIFIED,
                    trust_score=90,
                ),
            ]
        )
        candidate = payment()
        session.add(candidate)
        await session.commit()
        result = await FraudEngine(Settings(seed_demo_data=False)).score(candidate, session)

    assert result.score == 0
    assert result.decision == "execute"
    assert result.reasons == ["Verified counterparties and normal payment behavior"]
    await engine.dispose()


async def test_watchlisted_high_value_sender_is_recalled():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all(
            [
                AgentIdentity(
                    address=WATCHLIST,
                    name="Relay",
                    status=RegistryStatus.WATCHLIST,
                    trust_score=5,
                ),
                AgentIdentity(
                    address=RECEIVER,
                    name="Seller",
                    status=RegistryStatus.VERIFIED,
                    trust_score=90,
                ),
            ]
        )
        candidate = payment(WATCHLIST, 100_000_000_000_000_000)
        session.add(candidate)
        await session.commit()
        result = await FraudEngine(Settings(seed_demo_data=False)).score(candidate, session)

    assert result.score == 100
    assert result.decision == "recall"
    assert any("watchlist" in reason for reason in result.reasons)
    await engine.dispose()


async def test_velocity_rule_counts_recent_sender_payments():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add_all(
            [
                AgentIdentity(
                    address=SENDER,
                    name="Buyer",
                    status=RegistryStatus.VERIFIED,
                    trust_score=95,
                ),
                AgentIdentity(
                    address=RECEIVER,
                    name="Seller",
                    status=RegistryStatus.VERIFIED,
                    trust_score=90,
                ),
            ]
        )
        candidate = payment()
        session.add(candidate)
        for index in range(5):
            prior = payment()
            prior.payment_id = "0x" + f"{index + 1:064x}"
            prior.deposit_tx_hash = "0x" + f"{index + 20:064x}"
            session.add(prior)
        await session.commit()
        result = await FraudEngine(Settings(seed_demo_data=False)).score(candidate, session)

    assert result.score == 40
    assert any("High sender velocity" in reason for reason in result.reasons)
    await engine.dispose()
