from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, Payment, utc_now
from app.service import PaymentProcessor


@pytest.mark.parametrize("decision", ["execute", "recall"])
async def test_settlement_compares_reloaded_sqlite_deadlines_with_utc_chain_time(decision):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    now = utc_now()
    identifier = "0x" + "a" * 64
    async with sessions() as session:
        session.add(
            Payment(
                payment_id=identifier,
                sender="0x" + "1" * 40,
                receiver="0x" + "2" * 40,
                amount_units="1000000",
                metadata_hash="0x" + "b" * 64,
                deposit_tx_hash="0x" + "c" * 64,
                deposited_at=now - timedelta(seconds=40),
                recall_deadline=now + timedelta(seconds=10 if decision == "recall" else -10),
                decision=decision,
                status="approved",
                source="sepolia",
            )
        )
        await session.commit()

    class Chain:
        enabled = True
        calls = []

        async def current_time(self):
            return now

        async def resolve(self, payment_id, resolution):
            self.calls.append((payment_id, resolution))
            return "0x" + "d" * 64

    class Websocket:
        async def broadcast(self, *_args):
            pass

    chain = Chain()
    await PaymentProcessor(sessions, None, chain, Websocket()).settle_due()
    async with sessions() as session:
        stored = await session.get(Payment, identifier)
        assert stored.status == ("executed" if decision == "execute" else "recalled")
        assert stored.resolution_tx_hash == "0x" + "d" * 64
    assert chain.calls == [(identifier, decision)]
    await engine.dispose()
