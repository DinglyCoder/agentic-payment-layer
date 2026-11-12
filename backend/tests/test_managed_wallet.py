import pytest

from app.blockchain import DepositSubmission
from app.config import Settings
from app.managed_wallet import ManagedDemoWallet
from app.schemas import ManagedDemoPaymentCreate


class RecordingProcessor:
    def __init__(self):
        self.envelope = None

    async def register_intent(self, envelope):
        self.envelope = envelope


class StubChain:
    def __init__(self):
        self.deposit = None

    async def token_balance(self, address):
        return 20_000_000

    async def native_balance(self, address):
        return 10**17

    async def deposit_from(self, account, payment_id, receiver, amount_units, metadata_hash):
        self.deposit = (account.address, payment_id, receiver, amount_units, metadata_hash)
        return DepositSubmission(
            deposit_tx_hash="0x" + "ab" * 32,
            approval_tx_hash="0x" + "cd" * 32,
        )


def managed_settings(**overrides):
    values = {
        "_env_file": None,
        "simulation_mode": True,
        "testnet_enabled": True,
        "sepolia_rpc_url": "https://rpc.example",
        "escrow_contract_address": "0x" + "11" * 20,
        "payment_token_address": "0x" + "22" * 20,
        "arbitrator_private_key": "0x" + "33" * 32,
        "deployer_private_key": "0x" + "44" * 32,
        "managed_demo_wallet_enabled": True,
        "managed_demo_max_amount_units": 5_000_000,
        "managed_demo_session_budget_units": 6_000_000,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_managed_wallet_signs_intent_and_deposits_without_exposing_key():
    processor = RecordingProcessor()
    chain = StubChain()
    wallet = ManagedDemoWallet(managed_settings(), processor, chain)

    status = await wallet.status()
    assert status.enabled is True
    assert status.balance_units == "20000000"

    result = await wallet.pay(
        ManagedDemoPaymentCreate(
            receiver="0x" + "55" * 20,
            amount_usdc="4.2",
            description="Managed wallet demo payment",
        )
    )

    assert result.sender == status.address
    assert result.amount_units == "4200000"
    assert processor.envelope.sender == status.address
    assert processor.envelope.signature.startswith("0x")
    assert chain.deposit[1] == result.payment_id
    assert chain.deposit[4] == processor.envelope.metadata_hash


@pytest.mark.asyncio
async def test_managed_wallet_enforces_session_budget():
    wallet = ManagedDemoWallet(managed_settings(), RecordingProcessor(), StubChain())
    request = ManagedDemoPaymentCreate(
        receiver="0x" + "55" * 20,
        amount_usdc="4",
        description="Managed wallet demo payment",
    )
    await wallet.pay(request)

    with pytest.raises(ValueError, match="session budget"):
        await wallet.pay(request)


@pytest.mark.asyncio
async def test_ambiguous_submission_retains_funding_reservation():
    class UncertainChain(StubChain):
        async def deposit_from(self, *_args, **_kwargs):
            raise TimeoutError("receipt outcome unknown")

    wallet = ManagedDemoWallet(managed_settings(), RecordingProcessor(), UncertainChain())
    request = ManagedDemoPaymentCreate(
        receiver="0x" + "55" * 20, amount_usdc="4", description="Receipt timeout test"
    )
    with pytest.raises(TimeoutError):
        await wallet.pay(request)
    with pytest.raises(ValueError, match="session budget"):
        await wallet.pay(request)


@pytest.mark.asyncio
async def test_token_contract_recipient_is_rejected_before_signing_or_spending():
    processor = RecordingProcessor()
    chain = StubChain()
    wallet = ManagedDemoWallet(managed_settings(), processor, chain)
    with pytest.raises(ValueError, match="token contract"):
        await wallet.pay(
            ManagedDemoPaymentCreate(
                receiver=wallet.settings.payment_token_address,
                amount_usdc="4.2",
                description="Invalid token recipient",
            )
        )
    assert processor.envelope is None
    assert chain.deposit is None
    assert (await wallet.status()).remaining_session_budget_units == "6000000"
