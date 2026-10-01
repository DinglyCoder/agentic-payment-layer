import json
from datetime import timedelta

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, IntentEnvelope, utc_now
from app.schemas import IntentEnvelopeCreate
from app.service import PaymentProcessor

TOKEN = "0x3333333333333333333333333333333333333333"
RECEIVER = "0x2222222222222222222222222222222222222222"


class StubChain:
    class Settings:
        payment_token_address = TOKEN

    settings = Settings()


class StubWebsocket:
    async def broadcast(self, _event, _payment):
        pass


async def test_signed_intent_is_verified_and_tampering_is_rejected():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    account = Account.create()
    expires_at = (utc_now() + timedelta(minutes=5)).replace(microsecond=0)
    unsigned = {
        "payment_id": "0x" + "a" * 64,
        "sender": account.address.lower(),
        "receiver": RECEIVER,
        "amount_units": "4200000",
        "token": TOKEN,
        "purpose": "GPU inference batch settlement",
        "service_or_sku": "inference-v1",
        "mandate": "Up to 5 USDC",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "nonce": "0x" + "b" * 64,
    }
    digest = (
        "0x" + keccak(text=json.dumps(unsigned, separators=(",", ":"), ensure_ascii=False)).hex()
    )
    signature = Account.sign_message(encode_defunct(hexstr=digest), account.key).signature.hex()
    request = IntentEnvelopeCreate(**unsigned, metadata_hash=digest, signature="0x" + signature)
    processor = PaymentProcessor(sessions, None, StubChain(), StubWebsocket())

    stored = await processor.register_intent(request)
    assert stored.verified
    async with sessions() as session:
        assert await session.get(IntentEnvelope, unsigned["payment_id"])

    tampered = request.model_copy(update={"payment_id": "0x" + "c" * 64, "amount_units": "4300000"})
    with pytest.raises(ValueError, match="metadata_hash"):
        await processor.register_intent(tampered)
    await engine.dispose()
