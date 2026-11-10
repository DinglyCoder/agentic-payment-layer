import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak

from .blockchain import EscrowChain
from .config import Settings
from .schemas import (
    IntentEnvelopeCreate,
    ManagedDemoPaymentCreate,
    ManagedDemoPaymentRead,
    ManagedDemoWalletRead,
)
from .service import PaymentProcessor


class ManagedDemoWallet:
    """Explicitly enabled, server-held Sepolia payer for interactive demos."""

    def __init__(self, settings: Settings, processor: PaymentProcessor, chain: EscrowChain) -> None:
        self.settings = settings
        self.processor = processor
        self.chain = chain
        self._lock = asyncio.Lock()
        self._spent_units = 0
        self.account = None
        if settings.managed_demo_wallet_available:
            assert settings.deployer_private_key is not None
            self.account = Account.from_key(settings.deployer_private_key.get_secret_value())

    @property
    def enabled(self) -> bool:
        return self.account is not None

    async def status(self) -> ManagedDemoWalletRead:
        balance = await self.chain.token_balance(self.account.address) if self.account else None
        return ManagedDemoWalletRead(
            enabled=self.enabled,
            address=self.account.address.lower() if self.account else None,
            balance_units=str(balance) if balance is not None else None,
            max_amount_units=str(self.settings.managed_demo_max_amount_units),
            remaining_session_budget_units=str(
                max(0, self.settings.managed_demo_session_budget_units - self._spent_units)
            ),
        )

    async def pay(
        self,
        request: ManagedDemoPaymentCreate,
        *,
        payment_id: str | None = None,
        on_submitted=None,
    ) -> ManagedDemoPaymentRead:
        if not self.account:
            raise PermissionError("managed demo wallet is not enabled")
        amount_units = int(request.amount_usdc * (10**self.settings.stablecoin_decimals))
        payment_id = payment_id or "0x" + secrets.token_hex(32)
        nonce = "0x" + secrets.token_hex(32)
        expires_at = (datetime.now(UTC) + timedelta(minutes=5)).replace(microsecond=0)
        payload = {
            "payment_id": payment_id,
            "sender": self.account.address.lower(),
            "receiver": request.receiver.lower(),
            "amount_units": str(amount_units),
            "token": self.settings.payment_token_address.lower(),
            "purpose": request.description,
            "service_or_sku": "interactive-payment",
            "mandate": "Application-managed demo wallet",
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "nonce": nonce,
        }
        metadata_hash = (
            "0x" + keccak(text=json.dumps(payload, separators=(",", ":"), ensure_ascii=False)).hex()
        )
        signature = self.account.sign_message(
            encode_defunct(hexstr=metadata_hash)
        ).signature.to_0x_hex()
        envelope = IntentEnvelopeCreate(**payload, metadata_hash=metadata_hash, signature=signature)
        await self.processor.register_intent(envelope)
        submission = await self.submit_deposit(
            self.account,
            payment_id,
            request.receiver,
            amount_units,
            metadata_hash,
            on_submitted=on_submitted,
        )

        return ManagedDemoPaymentRead(
            payment_id=payment_id,
            deposit_tx_hash=submission.deposit_tx_hash,
            approval_tx_hash=submission.approval_tx_hash,
            sender=self.account.address.lower(),
            receiver=request.receiver.lower(),
            amount_units=str(amount_units),
        )

    async def submit_deposit(
        self,
        account,
        payment_id: str,
        receiver: str,
        amount_units: int,
        metadata_hash: str,
        *,
        on_submitted=None,
    ):
        if not self.account or account.address.lower() != self.account.address.lower():
            raise PermissionError("managed demo wallet is not enabled for this payer")
        if amount_units <= 0 or amount_units > self.settings.managed_demo_max_amount_units:
            raise ValueError("payment exceeds the managed demo wallet per-payment limit")
        if receiver.lower() == account.address.lower():
            raise ValueError("sender and receiver must differ")
        async with self._lock:
            if self._spent_units + amount_units > self.settings.managed_demo_session_budget_units:
                raise ValueError("managed demo wallet session budget is exhausted")
            if await self.chain.token_balance(account.address) < amount_units:
                raise ValueError(f"insufficient test {self.settings.stablecoin_symbol} balance")
            # Retain the reservation on ambiguous RPC failure; retrying must not bypass the cap.
            self._spent_units += amount_units
            kwargs = {"on_submitted": on_submitted} if on_submitted else {}
            return await self.chain.deposit_from(
                account,
                payment_id,
                receiver,
                amount_units,
                metadata_hash,
                **kwargs,
            )
