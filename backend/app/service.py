import asyncio
import hashlib
import secrets
import time
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .blockchain import DepositEvent, EscrowChain
from .fraud import FraudEngine, RiskAssessment
from .models import AgentIdentity, Payment, PaymentStatus, RegistryStatus, utc_now
from .schemas import DemoPaymentCreate, PaymentRead
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
            payment = Payment(
                payment_id=event.payment_id,
                sender=event.sender,
                receiver=event.receiver,
                amount_units=str(event.amount_units),
                metadata_hash=event.metadata_hash,
                description="On-chain autonomous agent payment",
                deposit_tx_hash=event.transaction_hash,
                block_number=event.block_number,
                deposited_at=event.deposited_at,
                recall_deadline=event.recall_deadline,
                status=PaymentStatus.SCORING,
                source="sepolia",
            )
            session.add(payment)
            await session.commit()
            await self.websocket.broadcast("payment_detected", as_payload(payment))
            await self._assess(payment, session, settle_immediately=False)

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
                Payment.decision == "execute",
                Payment.recall_deadline < now,
            )
            for payment in (await session.scalars(query)).all():
                await self._resolve(payment, session, "execute")

    async def _resolve(self, payment: Payment, session, decision: str) -> None:
        try:
            payment.resolution_tx_hash = await self.chain.resolve(payment.payment_id, decision)
            payment.status = (
                PaymentStatus.RECALLED if decision == "recall" else PaymentStatus.EXECUTED
            )
        except Exception as exc:
            payment.status = PaymentStatus.FAILED
            payment.risk_reasons = [
                *payment.risk_reasons,
                f"Resolution failed: {type(exc).__name__}",
            ]
        await session.commit()
        await self.websocket.broadcast("payment_resolved", as_payload(payment))
