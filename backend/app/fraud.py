import json
import re
from dataclasses import dataclass
from datetime import timedelta

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import AgentIdentity, Payment, PaymentStatus, RegistryStatus, RiskLevel, utc_now


class RiskAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    level: RiskLevel
    decision: str
    reasons: list[str]
    llm_score: int | None = None


class LlmAssessment(BaseModel):
    score: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=180)


@dataclass(slots=True)
class VelocitySnapshot:
    count: int
    total_units: int


class FraudEngine:
    """Hybrid fraud scorer whose safety policy never depends on the LLM."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = (
            AsyncAnthropic(api_key=settings.anthropic_api_key.get_secret_value())
            if settings.anthropic_api_key
            else None
        )

    async def score(self, payment: Payment, session: AsyncSession) -> RiskAssessment:
        rule_score = 0
        reasons: list[str] = []

        sender = await session.get(AgentIdentity, payment.sender.lower())
        receiver = await session.get(AgentIdentity, payment.receiver.lower())
        rule_score += self._registry_risk("Sender", sender, reasons)
        rule_score += self._registry_risk("Receiver", receiver, reasons)

        amount = int(payment.amount_units)
        if amount >= self.settings.high_amount_units:
            rule_score += 35
            reasons.append("Amount is above the high-value agent payment threshold")
        elif amount >= self.settings.medium_amount_units:
            rule_score += 15
            reasons.append("Amount is above the normal micropayment range")

        velocity = await self._velocity(payment, session)
        if velocity.count >= self.settings.velocity_high_count:
            rule_score += 40
            reasons.append(f"High sender velocity: {velocity.count} recent payments")
        elif velocity.count >= self.settings.velocity_medium_count:
            rule_score += 20
            reasons.append(f"Elevated sender velocity: {velocity.count} recent payments")

        if payment.sender.lower() == payment.receiver.lower():
            rule_score += 80
            reasons.append("Sender and receiver are identical")

        rule_score = min(rule_score, 100)
        llm = await self._score_with_claude(payment, sender, receiver, velocity, rule_score)
        final_score = rule_score
        if llm:
            # Claude supplies context, but cannot lower a deterministic control.
            final_score = max(rule_score, round(rule_score * 0.65 + llm.score * 0.35))
            if llm.score >= 30:
                reasons.append(f"Claude review: {llm.reason}")

        if not reasons:
            reasons.append("Verified counterparties and normal payment behavior")

        level = (
            RiskLevel.HIGH
            if final_score >= self.settings.recall_threshold
            else RiskLevel.MEDIUM
            if final_score >= 30
            else RiskLevel.LOW
        )
        return RiskAssessment(
            score=final_score,
            level=level,
            decision="recall" if final_score >= self.settings.recall_threshold else "execute",
            reasons=reasons,
            llm_score=llm.score if llm else None,
        )

    @staticmethod
    def _registry_risk(party: str, identity: AgentIdentity | None, reasons: list[str]) -> int:
        if identity is None or identity.status == RegistryStatus.UNKNOWN:
            reasons.append(f"{party} is not present in the trusted agent registry")
            return 25
        if identity.status == RegistryStatus.WATCHLIST:
            reasons.append(f"{party} is on the agent watchlist")
            return 70
        if identity.trust_score < 50:
            reasons.append(f"{party} has a below-threshold identity trust score")
            return 20
        return 0

    async def _velocity(self, payment: Payment, session: AsyncSession) -> VelocitySnapshot:
        since = utc_now() - timedelta(seconds=self.settings.velocity_window_seconds)
        query = select(Payment.amount_units).where(
            func.lower(Payment.sender) == payment.sender.lower(),
            Payment.deposited_at >= since,
            Payment.payment_id != payment.payment_id,
            Payment.status != PaymentStatus.FAILED,
        )
        values = (await session.scalars(query)).all()
        return VelocitySnapshot(count=len(values), total_units=sum(int(value) for value in values))

    async def _score_with_claude(
        self,
        payment: Payment,
        sender: AgentIdentity | None,
        receiver: AgentIdentity | None,
        velocity: VelocitySnapshot,
        rule_score: int,
    ) -> LlmAssessment | None:
        if self._client is None:
            return None

        prompt = {
            "payment": {
                "amount_base_units": payment.amount_units,
                "stablecoin": self.settings.stablecoin_symbol,
                "description": payment.description,
                "sender_registry_status": sender.status if sender else "unknown",
                "sender_trust_score": sender.trust_score if sender else None,
                "receiver_registry_status": receiver.status if receiver else "unknown",
                "receiver_trust_score": receiver.trust_score if receiver else None,
                "sender_payments_last_minute": velocity.count,
                "sender_volume_last_minute_base_units": velocity.total_units,
                "deterministic_rule_score": rule_score,
            }
        }
        try:
            message = await self._client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=220,
                system=(
                    "You are a payment fraud analyst. Assess only the supplied facts. "
                    "Return JSON with integer score (0-100) and a short reason. "
                    "Do not include markdown or additional keys."
                ),
                messages=[{"role": "user", "content": json.dumps(prompt)}],
            )
            text = "".join(getattr(block, "text", "") for block in message.content)
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            return LlmAssessment.model_validate_json(match.group(0)) if match else None
        except Exception:
            # Availability of an advisory model must not disable deterministic controls.
            return None
