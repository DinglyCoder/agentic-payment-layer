"""Read-only payment review. A preview never signs, reserves, or submits funds."""

import asyncio
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .blockchain import validate_payment_receiver
from .demo import DemoInput, Mode, Scenario, payment_command
from .schemas import ADDRESS_PATTERN
from .seed import DEMO_AGENT_DATA

router = APIRouter(prefix="/api", tags=["Payment review"])


class PaymentPreviewInput(BaseModel):
    kind: Literal["direct", "scenario", "command"]
    mode: Mode
    payer: Literal["managed", "browser"] = "managed"
    sender: str | None = Field(default=None, pattern=ADDRESS_PATTERN)
    receiver: str | None = Field(default=None, pattern=ADDRESS_PATTERN)
    amount_usdc: Decimal | None = Field(default=None, gt=0, le=1_000_000, decimal_places=6)
    description: str = Field(default="Payment", max_length=240)
    scenario: Scenario | None = None
    command: str | None = Field(default=None, min_length=1, max_length=512)
    budget_units: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$", max_length=78)


class PaymentPreviewRead(BaseModel):
    mode: Mode
    title: str
    amount_units: str
    offer_units: str | None = None
    budget_units: str | None = None
    sender: str | None
    receiver: str | None
    token_symbol: str
    token_decimals: int
    balance_units: str | None = None
    native_balance_wei: str | None = None
    remaining_session_budget_units: str | None = None
    can_submit: bool = True
    policy_only: bool = False
    blockers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


async def preview_payment(payload: PaymentPreviewInput, workspace) -> PaymentPreviewRead | None:
    mode = payload.mode
    simulation = mode == "simulation"
    settings = workspace.settings if simulation else workspace.live_settings
    scenario = payload.scenario
    request = DemoInput(mode=mode, budget_units=payload.budget_units)
    if payload.kind == "command":
        if not payload.command:
            raise ValueError("A command is required")
        plan = payment_command(payload.command, mode)
        if plan is None:
            return None  # Inspection, recovery, and invalid commands cannot start a new payment.
        scenario, request = plan

    if not simulation and (not workspace.chain or not workspace.chain.enabled):
        raise ValueError("Sepolia is not configured. A live balance cannot be loaded.")

    budget = None
    offer = None
    policy_only = False
    notes = []
    if payload.kind == "direct":
        if payload.amount_usdc is None or not payload.receiver:
            raise ValueError("Payment amount and receiving wallet are required")
        amount = int(payload.amount_usdc * 10**settings.stablecoin_decimals)
        receiver = payload.receiver.lower()
        sender = payload.sender
        title = payload.description
    else:
        if scenario is None:
            raise ValueError("A payment scenario is required")
        sender = workspace.buyer.address if simulation else None
        receiver = (
            workspace.seller.address
            if simulation
            else settings.seller_address
            or (workspace.chain.account.address.lower() if workspace.chain else None)
        )
        title = {
            "purchase": "Purchase compute",
            "trusted": "Compute payment",
            "watchlist": "Watchlist recall",
            "budget": "Spending limit check",
            "replay": "Replay protection check",
        }[scenario]
        if scenario in {"trusted", "watchlist"}:
            amount = (
                (82_000_000 if scenario == "watchlist" else 4_200_000)
                if simulation
                else 10**settings.stablecoin_decimals
            )
            if simulation and scenario == "trusted":
                sender, receiver = DEMO_AGENT_DATA[0][0], DEMO_AGENT_DATA[1][0]
            if scenario == "watchlist":
                if simulation:
                    sender, receiver = DEMO_AGENT_DATA[3][0], DEMO_AGENT_DATA[1][0]
                else:
                    receiver = DEMO_AGENT_DATA[3][0]
                notes.append(
                    "The full amount enters escrow first. The watchlist scenario then "
                    "attempts a refund; gas is still spent."
                )
        else:
            budget = int(request.budget_units or ("500000" if scenario == "budget" else "3000000"))
            offer = settings.seller_price_units
            policy_only = scenario == "replay" or budget < offer
            amount = 0 if policy_only else offer
            if policy_only:
                notes.append(
                    "This checks a policy rejection before spending. "
                    "No USDC or gas should be charged."
                )
            else:
                notes.append(
                    "The budget is an authorization limit, not an additional charge. "
                    "Only the seller's price is deposited."
                )

    review = PaymentPreviewRead(
        mode=mode,
        title=title,
        amount_units=str(amount),
        offer_units=str(offer) if offer is not None else None,
        budget_units=str(budget) if budget is not None else None,
        sender=sender,
        receiver=receiver,
        token_symbol=settings.stablecoin_symbol,
        token_decimals=settings.stablecoin_decimals,
        policy_only=policy_only,
        notes=notes,
    )
    if simulation:
        review.notes.append(
            "Explicit offline simulation. No real wallet balance or blockchain transaction."
        )
        return review

    chain = workspace.chain
    managed = payload.kind != "direct" or payload.payer == "managed"
    if managed:
        workspace.require_sepolia()
        wallet = await workspace.wallet.status()
        review.sender = wallet.address
        review.balance_units = wallet.balance_units
        review.native_balance_wei = wallet.native_balance_wei
        review.remaining_session_budget_units = wallet.remaining_session_budget_units
        if amount > int(wallet.max_amount_units):
            review.blockers.append("Charge exceeds the managed wallet's per-payment limit.")
        if amount > int(wallet.remaining_session_budget_units):
            review.blockers.append("Charge exceeds the managed wallet's remaining session budget.")
    else:
        if not payload.sender:
            raise ValueError("Connect your Sepolia wallet before reviewing a payment.")
        balance, native = await asyncio.gather(
            chain.token_balance(payload.sender),
            chain.native_balance(payload.sender),
        )
        review.balance_units, review.native_balance_wei = str(balance), str(native)

    if amount > 0:
        if not review.sender or not receiver:
            review.blockers.append("A paying wallet and receiving wallet are required.")
        else:
            try:
                validate_payment_receiver(
                    review.sender,
                    receiver,
                    settings.payment_token_address,
                    settings.escrow_contract_address,
                )
            except ValueError as error:
                review.blockers.append(str(error))
        if int(review.balance_units or "0") < amount:
            review.blockers.append("Insufficient test USDC for this payment.")
        if int(review.native_balance_wei or "0") == 0:
            review.blockers.append("The paying wallet needs Sepolia ETH for transaction gas.")
        review.notes.append(
            "Network gas is charged separately in Sepolia ETH. "
            "The displayed USDC balance after payment excludes gas."
        )
    review.can_submit = not review.blockers
    return review


@router.post("/payments/preview", response_model=PaymentPreviewRead | None)
async def payment_preview(payload: PaymentPreviewInput, request: Request):
    try:
        return await preview_payment(payload, request.app.state.demo)
    except (ValueError, InvalidOperation) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        # Provider exceptions can include authenticated RPC URLs; don't expose them.
        raise HTTPException(
            status_code=503, detail="Could not load the live wallet balance. Retry before paying."
        ) from error
