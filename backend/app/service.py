import asyncio
import hashlib
import json
import secrets
import time
from datetime import UTC, timedelta
from decimal import Decimal

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .blockchain import DepositEvent, EscrowChain, ResolutionEvent
from .fraud import FraudEngine, RiskAssessment
from .models import (
    AgentIdentity,
    ChainCursor,
    IntentEnvelope,
    Payment,
    PaymentStatus,
    RegistryStatus,
    utc_now,
)
from .schemas import DemoPaymentCreate, IntentEnvelopeCreate, PaymentRead
from .websocket import ConnectionManager


def as_payload(payment: Payment) -> dict:
    return PaymentRead.model_validate(payment).model_dump(mode="json")


class PaymentProcessor:
    def __init__(
        self,
        sessions: async_sessionmaker,
        fraud: FraudEngine,
        chain: EscrowChain,
        websocket: ConnectionManager,
    ) -> None:
        self.sessions = sessions
        self.fraud = fraud
        self.chain = chain
        self.websocket = websocket

    @staticmethod
    def _intent_payload(request: IntentEnvelopeCreate) -> dict:
        return {
            "payment_id": request.payment_id.lower(),
            "sender": request.sender.lower(),
            "receiver": request.receiver.lower(),
            "amount_units": request.amount_units,
            "token": request.token.lower(),
            "purpose": request.purpose,
            "service_or_sku": request.service_or_sku,
            "mandate": request.mandate,
            "expires_at": request.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "nonce": request.nonce.lower(),
        }

    async def register_intent(self, request: IntentEnvelopeCreate) -> IntentEnvelope:
        payload = self._intent_payload(request)
        digest = (
            "0x" + keccak(text=json.dumps(payload, separators=(",", ":"), ensure_ascii=False)).hex()
        )
        if digest.lower() != request.metadata_hash.lower():
            raise ValueError("metadata_hash does not match the canonical intent envelope")
        recovered = Account.recover_message(
            encode_defunct(hexstr=digest), signature=request.signature
        ).lower()
        if recovered != request.sender.lower():
            raise ValueError("intent signature is not from the sender wallet")
        expires_at = request.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= utc_now() or expires_at > utc_now() + timedelta(days=1):
            raise ValueError("intent expiry must be in the next 24 hours")
        configured_token = self.chain.settings.payment_token_address
        if not configured_token or request.token.lower() != configured_token.lower():
            raise ValueError("intent token does not match the configured payment token")

        async with self.sessions() as session:
            if await session.get(IntentEnvelope, request.payment_id.lower()):
                raise ValueError("payment intent already exists")
            envelope = IntentEnvelope(
                payment_id=payload["payment_id"],
                sender=payload["sender"],
                receiver=payload["receiver"],
                amount_units=payload["amount_units"],
                token=payload["token"],
                purpose=payload["purpose"],
                service_or_sku=payload["service_or_sku"],
                mandate=payload["mandate"],
                nonce=payload["nonce"],
                expires_at=expires_at,
                metadata_hash=digest,
                signature=request.signature,
                verified=True,
            )
            session.add(envelope)
            await session.commit()
            return envelope

    async def process_deposit(self, event: DepositEvent) -> None:
        async with self.sessions() as session:
            if await session.get(Payment, event.payment_id):
                return
            for address in (event.sender, event.receiver):
                if await session.get(AgentIdentity, address) is None:
                    session.add(
                        AgentIdentity(
                            address=address,
                            name=f"Sepolia wallet {address[:8]}…{address[-4:]}",
                            status=RegistryStatus.UNKNOWN,
                            trust_score=50,
                        )
                    )
            intent = await session.get(IntentEnvelope, event.payment_id)
            intent_valid = (
                intent is not None
                and intent.verified
                and intent.consumed_at is None
                and intent.sender == event.sender
                and intent.receiver == event.receiver
                and intent.amount_units == str(event.amount_units)
                and intent.metadata_hash == event.metadata_hash
                and intent.expires_at.replace(tzinfo=UTC) >= event.deposited_at
            )
            payment = Payment(
                payment_id=event.payment_id,
                sender=event.sender,
                receiver=event.receiver,
                amount_units=str(event.amount_units),
                metadata_hash=event.metadata_hash,
                description=(
                    intent.purpose if intent_valid else "Unverified on-chain payment intent"
                ),
                deposit_tx_hash=event.transaction_hash,
                block_number=event.block_number,
                deposited_at=event.deposited_at,
                recall_deadline=event.recall_deadline,
                status=PaymentStatus.SCORING,
                source="sepolia",
            )
            session.add(payment)
            if intent_valid:
                intent.consumed_at = utc_now()
            await session.commit()
            await self.websocket.broadcast("payment_detected", as_payload(payment))
            if intent_valid:
                await self._assess(payment, session, settle_immediately=False)
            else:
                payment.status = PaymentStatus.APPROVED
                payment.decision = "recall"
                payment.risk_score = 100
                payment.risk_level = "high"
                payment.policy_version = "2026-10-01"
                payment.risk_reasons = ["Signed intent is missing, expired, or mismatched"]
                payment.risk_signals = [
                    {
                        "name": "intent_binding",
                        "contribution": 100,
                        "weight": 100,
                        "evidence": {"metadata_hash": event.metadata_hash, "verified": False},
                    }
                ]
                await session.commit()
                await self._resolve(payment, session, "recall")

    async def create_demo(self, request: DemoPaymentCreate) -> Payment:
        now = utc_now()
        random_bytes = secrets.token_bytes(32)
        payment_id = "0x" + hashlib.sha256(random_bytes).hexdigest()
        metadata_hash = "0x" + hashlib.sha256(request.description.encode()).hexdigest()
        deposit_tx_hash = "0x" + hashlib.sha256(b"deposit" + random_bytes).hexdigest()
        amount_units = int(
            request.amount_usdc * Decimal(10**self.fraud.settings.stablecoin_decimals)
        )

        async with self.sessions() as session:
            payment = Payment(
                payment_id=payment_id,
                sender=request.sender.lower(),
                receiver=request.receiver.lower(),
                amount_units=str(amount_units),
                metadata_hash=metadata_hash,
                description=request.description,
                deposit_tx_hash=deposit_tx_hash,
                deposited_at=now,
                recall_deadline=now + timedelta(seconds=30),
                status=PaymentStatus.SCORING,
                source="simulation",
            )
            session.add(payment)
            await session.commit()
            await self.websocket.broadcast("payment_detected", as_payload(payment))
            await asyncio.sleep(0.2)
            await self._assess(payment, session, settle_immediately=True)
            return payment

    async def _assess(
        self, payment: Payment, session, *, settle_immediately: bool
    ) -> RiskAssessment:
        started = time.perf_counter()
        assessment = await self.fraud.score(payment, session)
        payment.risk_score = assessment.score
        payment.risk_level = assessment.level
        payment.risk_reasons = assessment.reasons
        payment.risk_signals = assessment.signals
        payment.policy_version = assessment.policy_version
        payment.llm_score = assessment.llm_score
        payment.decision = assessment.decision
        payment.decision_latency_ms = round((time.perf_counter() - started) * 1000)
        payment.status = (
            PaymentStatus.RECALLED
            if settle_immediately and assessment.decision == "recall"
            else PaymentStatus.EXECUTED
            if settle_immediately
            else PaymentStatus.APPROVED
        )
        if settle_immediately:
            payment.resolution_tx_hash = (
                "0x" + hashlib.sha256(f"resolution:{payment.payment_id}".encode()).hexdigest()
            )
        await session.commit()
        await self.websocket.broadcast("payment_scored", as_payload(payment))

        if not settle_immediately and assessment.decision == "recall":
            await self._resolve(payment, session, "recall")
        return assessment

    async def settle_due(self) -> None:
        if not self.chain.enabled:
            return
        now = await self.chain.current_time()
        async with self.sessions() as session:
            query = select(Payment).where(
                Payment.status == PaymentStatus.APPROVED,
                (Payment.next_resolution_attempt_at.is_(None))
                | (Payment.next_resolution_attempt_at <= now),
            )
            for payment in (await session.scalars(query)).all():
                if payment.decision == "recall" and payment.recall_deadline >= now:
                    await self._resolve(payment, session, "recall")
                elif payment.decision == "execute" and payment.recall_deadline < now:
                    await self._resolve(payment, session, "execute")

    async def _resolve(self, payment: Payment, session, decision: str) -> None:
        try:
            payment.resolution_attempts += 1
            payment.resolution_tx_hash = await self.chain.resolve(payment.payment_id, decision)
            payment.status = (
                PaymentStatus.RECALLED if decision == "recall" else PaymentStatus.EXECUTED
            )
            payment.resolution_error = None
            payment.next_resolution_attempt_at = None
        except Exception as exc:
            payment.resolution_error = f"{type(exc).__name__}: {str(exc)[:180]}"
            delay = min(300, 2 ** min(payment.resolution_attempts, 8))
            payment.next_resolution_attempt_at = utc_now() + timedelta(seconds=delay)
        await session.commit()
        await self.websocket.broadcast("payment_resolved", as_payload(payment))

    async def process_resolution(self, event: ResolutionEvent) -> None:
        async with self.sessions() as session:
            payment = await session.get(Payment, event.payment_id)
            if payment is None:
                return
            payment.status = event.status
            payment.resolution_tx_hash = event.transaction_hash
            payment.resolution_error = None
            payment.next_resolution_attempt_at = None
            await session.commit()
            await self.websocket.broadcast("payment_resolved", as_payload(payment))

    async def load_cursor(self, default_next_block: int) -> tuple[int, str | None]:
        async with self.sessions() as session:
            cursor = await session.get(ChainCursor, "sepolia-escrow")
            if cursor:
                return cursor.next_block, cursor.last_block_hash
            return default_next_block, None

    async def save_cursor(self, next_block: int, last_block_hash: str) -> None:
        async with self.sessions() as session:
            cursor = await session.get(ChainCursor, "sepolia-escrow")
            if cursor is None:
                cursor = ChainCursor(name="sepolia-escrow", next_block=next_block)
                session.add(cursor)
            cursor.next_block = next_block
            cursor.last_block_hash = last_block_hash
            await session.commit()

    async def reconcile(self) -> None:
        if not self.chain.enabled:
            return
        async with self.sessions() as session:
            query = select(Payment).where(Payment.source == "sepolia")
            payments = (await session.scalars(query)).all()
            changed: list[Payment] = []
            for payment in payments:
                state = await self.chain.payment_state(payment.payment_id)
                chain_status = {2: PaymentStatus.EXECUTED, 3: PaymentStatus.RECALLED}.get(state)
                if chain_status and payment.status != chain_status:
                    payment.status = chain_status
                    payment.resolution_error = None
                    payment.next_resolution_attempt_at = None
                    changed.append(payment)
            await session.commit()
            for payment in changed:
                await self.websocket.broadcast("payment_reconciled", as_payload(payment))
