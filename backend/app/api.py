from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .database import get_session
from .models import AgentIdentity, Payment, PaymentStatus
from .schemas import (
    AgentRead,
    DemoPaymentCreate,
    HealthRead,
    PaymentRead,
    StatsRead,
)

router = APIRouter(prefix="/api")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    settings = get_settings()
    return HealthRead(
        status="ok",
        mode="simulation" if settings.simulation_mode else "sepolia",
        chain_id=11155111,
        contract_address=settings.escrow_contract_address,
        payment_token_address=settings.payment_token_address,
        llm_enabled=settings.anthropic_api_key is not None,
        stablecoin_symbol=settings.stablecoin_symbol,
        stablecoin_decimals=settings.stablecoin_decimals,
    )


@router.get("/payments", response_model=list[PaymentRead])
async def list_payments(session: SessionDep, limit: int = 50) -> list[Payment]:
    limit = max(1, min(limit, 200))
    query = select(Payment).order_by(desc(Payment.deposited_at)).limit(limit)
    return list((await session.scalars(query)).all())


@router.get("/payments/{payment_id}", response_model=PaymentRead)
async def get_payment(payment_id: str, session: SessionDep) -> Payment:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    return payment


@router.get("/agents", response_model=list[AgentRead])
async def list_agents(session: SessionDep) -> list[AgentIdentity]:
    query = select(AgentIdentity).order_by(AgentIdentity.name)
    return list((await session.scalars(query)).all())


@router.get("/stats", response_model=StatsRead)
async def stats(session: SessionDep) -> StatsRead:
    payments = list((await session.scalars(select(Payment))).all())
    total = len(payments)
    executed = sum(payment.status == PaymentStatus.EXECUTED for payment in payments)
    recalled = sum(payment.status == PaymentStatus.RECALLED for payment in payments)
    scored = [payment.risk_score for payment in payments if payment.risk_score is not None]
    return StatsRead(
        total_payments=total,
        executed_payments=executed,
        recalled_payments=recalled,
        protected_value_units=str(sum(int(payment.amount_units) for payment in payments)),
        execution_rate=round(executed / total * 100, 1) if total else 0,
        average_risk_score=round(sum(scored) / len(scored), 1) if scored else 0,
    )


@router.post("/demo/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def create_demo_payment(payload: DemoPaymentCreate, request: Request) -> Payment:
    if not get_settings().simulation_mode:
        raise HTTPException(status_code=403, detail="demo payments are disabled in Sepolia mode")
    return await request.app.state.processor.create_demo(payload)
