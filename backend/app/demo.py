"""Sepolia demo workflows, explicit offline simulation, and their shared CLI."""

import asyncio
import secrets
import shlex
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from eth_account import Account
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError

from .autonomy import BuyerAgent, SellerComputeAgent, canonical_hash, signature_hex
from .blockchain import EscrowChain
from .fraud import FraudEngine
from .models import AgentIdentity, DemoOperation, Payment, SpendingMandate, utc_now
from .schemas import (
    AutonomousPurchaseCreate,
    AutonomousPurchaseRead,
    DemoPaymentCreate,
    ManagedDemoPaymentCreate,
    PaymentRead,
    SpendingMandateCreate,
    SpendingMandateRead,
)
from .seed import DEMO_AGENT_DATA
from .service import PaymentProcessor

Scenario = Literal["purchase", "trusted", "watchlist", "budget", "replay"]
Mode = Literal["sepolia", "simulation"]


class DemoInput(BaseModel):
    mode: Mode = "sepolia"
    request_id: str | None = Field(default=None, pattern=r"^0x[a-f0-9]{64}$")
    budget_units: str | None = Field(default=None, pattern=r"^[1-9][0-9]*$", max_length=78)
    prompt: str = Field(
        default="Trusted compute delivers a safe and useful result", min_length=3, max_length=1000
    )


class DemoStep(BaseModel):
    label: str
    detail: str
    status: Literal["passed", "blocked"] = "passed"


class DemoRun(BaseModel):
    scenario: Scenario
    title: str
    outcome: Literal["completed", "recalled", "blocked"]
    summary: str
    steps: list[DemoStep]
    payment: PaymentRead | None = None
    purchase: AutonomousPurchaseRead | None = None
    mandate: SpendingMandateRead | None = None
    offer: dict | None = None
    simulation: bool
    explorer_links: dict[str, str] = Field(default_factory=dict)


class OperationRead(BaseModel):
    operation_id: str
    mode: Mode
    scenario: Scenario
    status: str
    phase: str
    error: str | None
    payment: PaymentRead | None
    result: DemoRun | None
    explorer_links: dict[str, str]


class CommandInput(BaseModel):
    command: str = Field(min_length=1, max_length=512)
    mode: Mode = "sepolia"
    request_id: str | None = Field(default=None, pattern=r"^0x[a-f0-9]{64}$")


class CommandResult(BaseModel):
    command: str
    exit_code: int = 0
    output: list[str]
    run: DemoRun | None = None
    operation: OperationRead | None = None
    data: dict | list | None = None


HELP = [
    "Paradime CLI · Sepolia testnet by default · actual test USDC and gas",
    "paradime doctor                         Check wallet and chain readiness",
    "paradime buy [--budget 3]               Buy the 1 USDC x402 compute offer",
    "paradime pay [--scenario trusted|watchlist]  Pay through the escrow",
    "paradime demo purchase|watchlist|budget|replay  Run a guided scenario",
    "paradime payments                       List payments in this environment",
    "paradime receipt latest|PAYMENT_ID      Inspect receipt and Etherscan links",
    "paradime status OPERATION_ID            Resume observing a submitted operation",
    "paradime resume OPERATION_ID            Finish paid work without another deposit",
    "Local CLI: --simulation explicitly selects offline simulation.",
]


def explorer_links(mode: str, *, approval=None, deposit=None, resolution=None) -> dict[str, str]:
    if mode != "sepolia":
        return {}
    return {
        name: f"https://sepolia.etherscan.io/tx/{value}"
        for name, value in (
            ("approval", approval),
            ("deposit", deposit),
            ("resolution", resolution),
        )
        if value
    }


class DemoWorkspace:
    def __init__(self, settings, sessions, websocket, *, processor=None, chain=None, wallet=None):
        self.live_settings = settings
        self.live_processor = processor
        self.chain = chain
        self.wallet = wallet
        self.settings = settings.model_copy(
            update={
                "simulation_mode": True,
                "testnet_enabled": False,
                "sepolia_rpc_url": None,
                "arbitrator_private_key": None,
                "deployer_private_key": None,
                "autonomous_buyer_private_key": None,
                "anthropic_api_key": None,
                "seller_address": None,
                "payment_token_address": None,
                "escrow_contract_address": None,
                "stablecoin_decimals": 6,
                "stablecoin_symbol": "USDC",
                "seller_price_units": 1_000_000,
            }
        )
        self.sessions = sessions
        self._setup_lock = asyncio.Lock()
        self._resume_lock = asyncio.Lock()
        self._tasks: dict[str, asyncio.Task] = {}
        sim_chain = EscrowChain(self.settings)
        self.processor = PaymentProcessor(
            sessions, FraudEngine(self.settings), sim_chain, websocket
        )
        self.seller = SellerComputeAgent(self.settings)
        self.buyer = BuyerAgent(self.settings, sessions, self.processor, sim_chain, self.seller)

    def require_sepolia(self):
        if not self.chain or not self.chain.enabled or not self.live_processor:
            raise ValueError(
                "Sepolia is not configured. Start ./demo with encrypted Sepolia configuration; "
                "simulation requires an explicit selection."
            )
        if not self.wallet or not self.wallet.enabled:
            raise ValueError(
                "The managed Sepolia demo wallet is disabled. Enable MANAGED_DEMO_WALLET_ENABLED "
                "with its encrypted payer key, or use your browser wallet in the payment console."
            )

    async def status(self) -> dict:
        available = bool(self.chain and self.chain.enabled)
        wallet = await self.wallet.status() if available and self.wallet else None
        return {
            "testnet_available": available,
            "managed_wallet": wallet.model_dump() if wallet else None,
            "seller_address": self.live_settings.seller_address
            or (self.chain.account.address.lower() if available else None),
            "contract_address": self.live_settings.escrow_contract_address if available else None,
            "chain_confirmations": self.live_settings.chain_confirmations,
        }

    async def recover(self):
        async with self.sessions() as session:
            rows = await session.scalars(
                select(DemoOperation).where(DemoOperation.status.in_(["queued", "running"]))
            )
            for row in rows:
                row.status = "interrupted"
                row.phase = "Process restarted; inspect the recorded transaction before retrying"
                row.error = (
                    "This workflow was interrupted. Submitted transactions may still settle."
                )
            await session.commit()

    async def close(self):
        for task in list(self._tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self._tasks.values()), return_exceptions=True)

    async def start(self, scenario: Scenario, request: DemoInput) -> OperationRead:
        if request.mode == "sepolia":
            self.require_sepolia()
            if scenario == "watchlist" and self.live_settings.chain_confirmations != 0:
                raise ValueError(
                    "The 30-second escrow requires the demo's mined-block listener "
                    "(CHAIN_CONFIRMATIONS=0) for prompt recall. Start ./demo; "
                    "this setting is not finalized-block protection."
                )
        identifier = request.request_id or "0x" + secrets.token_hex(32)
        payload = request.model_dump(exclude={"request_id"})
        async with self.sessions() as session:
            existing = await session.get(DemoOperation, identifier)
            if existing:
                if existing.request != payload or existing.scenario != scenario:
                    raise ValueError("request_id was already used for a different operation")
            else:
                session.add(
                    DemoOperation(
                        operation_id=identifier,
                        mode=request.mode,
                        scenario=scenario,
                        request=payload,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    existing = await session.get(DemoOperation, identifier)
                    if not existing or existing.request != payload or existing.scenario != scenario:
                        raise ValueError(
                            "request_id was already used for a different operation"
                        ) from None
        if not existing:
            task = asyncio.create_task(self._execute(identifier, scenario, request))
            self._tasks[identifier] = task
            task.add_done_callback(lambda _: self._tasks.pop(identifier, None))
        return await self.operation(identifier)

    async def _update(self, identifier: str, **values):
        async with self.sessions() as session:
            row = await session.get(DemoOperation, identifier)
            for key, value in values.items():
                setattr(row, key, value)
            await session.commit()

    async def resume(self, identifier: str) -> OperationRead:
        async with self._resume_lock:
            operation = await self.operation(identifier)
            if identifier in self._tasks or operation.status == "completed":
                return operation
            if operation.mode != "sepolia" or not operation.explorer_links.get("deposit"):
                raise ValueError("no submitted Sepolia deposit to resume")
            self.require_sepolia()
            await self._update(
                identifier,
                status="running",
                error=None,
                phase="Resuming existing payment; no new deposit",
            )
            task = asyncio.create_task(self._resume_existing(identifier, operation.scenario))
            self._tasks[identifier] = task
            task.add_done_callback(lambda _: self._tasks.pop(identifier, None))
            return await self.operation(identifier)

    async def _resume_existing(self, identifier: str, scenario: Scenario):
        try:
            buyer, seller, processor = self._actors("sepolia", identifier)
            purchase = await buyer.fulfill_purchase(identifier) if scenario == "purchase" else None
            payment = await processor.wait_for_terminal_payment(identifier, 240)
            if payment.status not in {"executed", "recalled"}:
                raise ValueError("the existing payment has not resolved")
            async with self.sessions() as session:
                mandate = (
                    await session.get(SpendingMandate, purchase.mandate_id) if purchase else None
                )
            result = DemoRun(
                scenario=scenario,
                title="Recovered Sepolia payment",
                simulation=False,
                outcome="completed" if payment.status == "executed" else "recalled",
                summary="Existing payment recovered without a second deposit.",
                steps=[
                    DemoStep(label="Existing deposit recovered", detail=payment.deposit_tx_hash),
                    DemoStep(
                        label="Chain resolution verified", detail="; ".join(payment.risk_reasons)
                    ),
                    DemoStep(
                        label="Seller output recovered" if purchase else "Resolution recorded",
                        detail="No additional payment was submitted.",
                    ),
                ],
                payment=PaymentRead.model_validate(payment),
                mandate=SpendingMandateRead.model_validate(mandate) if mandate else None,
                purchase=AutonomousPurchaseRead.model_validate(purchase) if purchase else None,
                offer=seller.payment_required() if purchase else None,
                explorer_links=(await self.operation(identifier)).explorer_links,
            )
            await self._update(
                identifier,
                status="completed",
                phase=result.summary,
                result=result.model_dump(mode="json"),
                error=None,
            )
        except asyncio.CancelledError:
            await self._update(identifier, status="interrupted", phase="Recovery interrupted")
            raise
        except Exception as exc:
            await self._update(
                identifier,
                status="failed",
                phase="Recovery needs attention",
                error=f"{type(exc).__name__}: {str(exc)[:210]}",
            )

    async def _submitted(self, identifier: str, stage: str, transaction: str):
        await self._update(
            identifier,
            **{f"{stage}_tx_hash": transaction},
            phase=f"{stage.title()} submitted; waiting for a mined receipt",
        )

    async def _execute(self, identifier: str, scenario: Scenario, request: DemoInput):
        try:
            await self._update(identifier, status="running", phase="Checking authority and wallet")
            result = await self.run(scenario, request, identifier)
            result.explorer_links.update((await self.operation(identifier)).explorer_links)
            await self._update(
                identifier,
                status="completed",
                phase=result.summary,
                result=result.model_dump(mode="json"),
            )
        except asyncio.CancelledError:
            await self._update(
                identifier,
                status="interrupted",
                phase="Workflow interrupted",
                error="The server stopped. Check recorded chain evidence before submitting again.",
            )
            raise
        except Exception as exc:
            await self._update(
                identifier,
                status="failed",
                phase="Workflow needs attention",
                error=f"{type(exc).__name__}: {str(exc)[:210]}",
            )

    async def operation(self, identifier: str) -> OperationRead:
        async with self.sessions() as session:
            row = await session.get(DemoOperation, identifier)
            if row is None:
                raise ValueError("operation not found")
            payment = await session.get(Payment, identifier)
            result = DemoRun.model_validate(row.result) if row.result else None
            if not payment and result and result.payment:
                payment = result.payment
            phase = row.phase
            if row.status == "running" and payment and payment.status == "approved":
                phase = "Deposit mined; waiting for escrow resolution"
            links = explorer_links(
                row.mode,
                approval=row.approval_tx_hash,
                deposit=row.deposit_tx_hash or (payment.deposit_tx_hash if payment else None),
                resolution=payment.resolution_tx_hash if payment else None,
            )
            return OperationRead(
                operation_id=row.operation_id,
                mode=row.mode,
                scenario=row.scenario,
                status=row.status,
                phase=phase,
                error=row.error,
                payment=PaymentRead.model_validate(payment) if payment else None,
                result=result,
                explorer_links=links,
            )

    async def operations(self, mode: Mode) -> list[OperationRead]:
        async with self.sessions() as session:
            identifiers = list(
                await session.scalars(
                    select(DemoOperation.operation_id)
                    .where(DemoOperation.mode == mode)
                    .order_by(desc(DemoOperation.created_at))
                    .limit(12)
                )
            )
        return [await self.operation(identifier) for identifier in identifiers]

    def _actors(self, mode: Mode, identifier: str):
        if mode == "simulation":
            return self.buyer, self.seller, self.processor
        self.require_sepolia()
        settings = self.live_settings.model_copy(
            update={
                "simulation_mode": False,
                "seller_address": self.live_settings.seller_address
                or self.chain.account.address.lower(),
            }
        )
        seller = SellerComputeAgent(settings)

        async def submit(account, payment_id, receiver, amount, metadata_hash):
            async def submitted(stage, tx):
                await self._submitted(identifier, stage, tx)

            return await self.wallet.submit_deposit(
                account, payment_id, receiver, amount, metadata_hash, on_submitted=submitted
            )

        buyer = BuyerAgent(
            settings,
            self.sessions,
            self.live_processor,
            self.chain,
            seller,
            account=self.wallet.account,
            submit_deposit=submit,
        )
        return buyer, seller, self.live_processor

    async def _ensure_agents(self, mode: Mode):
        data = DEMO_AGENT_DATA if mode == "simulation" else [DEMO_AGENT_DATA[3]]
        async with self._setup_lock, self.sessions() as session:
            for address, name, status, score in data:
                if await session.get(AgentIdentity, address) is None:
                    session.add(
                        AgentIdentity(
                            address=address,
                            name=name if mode == "simulation" else "Demo watchlist fixture",
                            status=status,
                            trust_score=score,
                        )
                    )
            await session.commit()

    async def _mandate(self, budget: str, buyer, seller, mode: Mode):
        owner = buyer.account if mode == "sepolia" else Account.create()
        unsigned = {
            "owner": owner.address.lower(),
            "delegate": buyer.address,
            "token": (
                buyer.settings.payment_token_address or buyer.settings.simulation_token_address
            ).lower(),
            "max_amount_per_payment_units": budget,
            "total_budget_units": budget,
            "allowed_receiver": seller.address,
            "allowed_service": buyer.settings.seller_service,
            "expires_at": (utc_now() + timedelta(minutes=10))
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "nonce": "0x" + secrets.token_hex(32),
        }
        digest = canonical_hash(unsigned)
        envelope = SpendingMandateCreate(
            **unsigned, mandate_id=digest, signature=signature_hex(owner, digest)
        )
        return await buyer.register_mandate(envelope), envelope

    async def run(self, scenario: Scenario, request: DemoInput, identifier: str) -> DemoRun:
        simulation = request.mode == "simulation"
        buyer, seller, processor = self._actors(request.mode, identifier)
        await self._ensure_agents(request.mode)
        if scenario in {"trusted", "watchlist"}:
            flagged = scenario == "watchlist"
            if simulation:
                payment = await processor.create_demo(
                    DemoPaymentCreate(
                        sender=DEMO_AGENT_DATA[3 if flagged else 0][0],
                        receiver=DEMO_AGENT_DATA[1][0],
                        amount_usdc=Decimal("82" if flagged else "4.2"),
                        description="Watchlisted relay payment"
                        if flagged
                        else "Trusted compute payment",
                    )
                )
            else:

                async def submitted(stage, tx):
                    await self._submitted(identifier, stage, tx)

                await self.wallet.pay(
                    ManagedDemoPaymentCreate(
                        receiver=DEMO_AGENT_DATA[3][0] if flagged else seller.address,
                        amount_usdc=Decimal("1"),
                        description="Demo watchlisted recipient"
                        if flagged
                        else "Sepolia compute payment",
                    ),
                    payment_id=identifier,
                    on_submitted=submitted,
                )
                payment = await processor.wait_for_terminal_payment(identifier, 240)
            if payment.status not in {"executed", "recalled"}:
                raise RuntimeError("payment has not reached a successful on-chain resolution")
            recalled = payment.status == "recalled"
            network = "simulation" if simulation else "Ethereum Sepolia"
            return DemoRun(
                scenario=scenario,
                title="Screen a flagged payment" if flagged else "Screen a payment",
                outcome="recalled" if recalled else "completed",
                simulation=simulation,
                summary=f"Funds {'returned to the payer' if recalled else 'settled to the seller'} "
                f"on {network}.",
                payment=PaymentRead.model_validate(payment),
                explorer_links=explorer_links(
                    request.mode,
                    deposit=payment.deposit_tx_hash,
                    resolution=payment.resolution_tx_hash,
                ),
                steps=[
                    DemoStep(
                        label="Deposit recorded", detail=f"ERC-20 escrow deposit on {network}"
                    ),
                    DemoStep(label="Risk policy evaluated", detail="; ".join(payment.risk_reasons)),
                    DemoStep(
                        label="Payment recalled" if recalled else "Payment executed",
                        detail="Simulated settlement"
                        if simulation
                        else "Mined arbitration transaction; inspect the Etherscan evidence.",
                    ),
                ],
            )

        budget = request.budget_units or ("500000" if scenario == "budget" else "3000000")
        mandate, envelope = await self._mandate(budget, buyer, seller, request.mode)
        steps = [
            DemoStep(
                label="Owner signature verified",
                detail=(
                    "Temporary simulation owner signed the mandate."
                    if simulation
                    else "The funded demo wallet signed a bounded spending mandate."
                ),
            )
        ]
        if scenario == "replay":
            try:
                await buyer.register_mandate(envelope)
            except ValueError as exc:
                if "already exists" not in str(exc):
                    raise
                steps.append(DemoStep(label="Replay rejected", detail=str(exc), status="blocked"))
            else:
                raise RuntimeError("replayed mandate was unexpectedly accepted")
            return DemoRun(
                scenario=scenario,
                title="Reject a replayed mandate",
                outcome="blocked",
                summary="Duplicate authority rejected before spending. No transaction was sent.",
                steps=steps,
                mandate=SpendingMandateRead.model_validate(mandate),
                simulation=simulation,
            )
        steps.append(
            DemoStep(
                label="x402 offer received", detail="Seller requests payment using paradime-escrow."
            )
        )
        try:
            purchase = await buyer.purchase(
                AutonomousPurchaseCreate(mandate_id=mandate.mandate_id, prompt=request.prompt),
                purchase_id=identifier,
                payment_id=identifier,
            )
        except ValueError as exc:
            if "mandate limit" not in str(exc) and "mandate budget" not in str(exc):
                raise
            steps.append(
                DemoStep(label="Budget policy blocked payment", detail=str(exc), status="blocked")
            )
            return DemoRun(
                scenario=scenario,
                title="Enforce a spending budget",
                outcome="blocked",
                summary="Offer exceeds signed authority. No transaction was sent.",
                steps=steps,
                mandate=SpendingMandateRead.model_validate(mandate),
                offer=seller.payment_required(),
                simulation=simulation,
            )
        async with self.sessions() as session:
            payment = await session.get(Payment, purchase.payment_id)
            mandate = await session.get(SpendingMandate, mandate.mandate_id)
        completed = purchase.status == "completed"
        steps.extend(
            [
                DemoStep(
                    label="Budget reserved",
                    detail=f"{format_units(purchase.amount_units)} USDC reserved "
                    "against the signed mandate.",
                ),
                DemoStep(
                    label="Payment screened and resolved", detail="; ".join(payment.risk_reasons)
                ),
                DemoStep(
                    label="Seller result received" if completed else "Seller access withheld",
                    detail="Executed payment proof checked before returning compute output."
                    if completed
                    else purchase.failure_reason or "Payment did not execute.",
                    status="passed" if completed else "blocked",
                ),
            ]
        )
        return DemoRun(
            scenario=scenario,
            title="Buy compute autonomously",
            outcome="completed" if completed else "recalled",
            simulation=simulation,
            summary="Paid compute delivered after escrow execution."
            if completed
            else "Policy rejected this purchase.",
            steps=steps,
            payment=PaymentRead.model_validate(payment),
            purchase=AutonomousPurchaseRead.model_validate(purchase),
            offer=seller.payment_required(),
            mandate=SpendingMandateRead.model_validate(mandate),
            explorer_links=explorer_links(
                request.mode, deposit=payment.deposit_tx_hash, resolution=payment.resolution_tx_hash
            ),
        )

    async def payments(self, mode: Mode) -> list[PaymentRead]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(Payment)
                .where(Payment.source == mode)
                .order_by(desc(Payment.deposited_at))
                .limit(20)
            )
            return [PaymentRead.model_validate(row) for row in rows]

    async def receipt(self, identifier: str, mode: Mode) -> PaymentRead:
        if identifier == "latest":
            payments = await self.payments(mode)
            if payments:
                return payments[0]
        else:
            async with self.sessions() as session:
                payment = await session.get(Payment, identifier)
                if payment and payment.source == mode:
                    return PaymentRead.model_validate(payment)
        raise ValueError("receipt not found in this environment; run a payment first")

    async def command(self, command: str, mode: Mode, request_id=None) -> CommandResult:
        try:
            words = shlex.split(command)
            if words and words[0] in {"paradime", "./paradime"}:
                words.pop(0)
            if not words or words in (["help"], ["--help"]):
                return CommandResult(command=command, output=HELP)
            verb, *args = words
            if verb == "doctor" and not args:
                if mode == "simulation":
                    return CommandResult(
                        command=command,
                        output=[
                            "Explicit offline simulation selected. "
                            "No chain transactions or Etherscan proofs."
                        ],
                    )
                status = await self.status()
                self.require_sepolia()
                return CommandResult(
                    command=command,
                    output=[
                        "Sepolia chain and escrow configured",
                        f"Payer: {status['managed_wallet']['address']}",
                        "Test USDC balance: "
                        f"{format_units(status['managed_wallet']['balance_units'])}",
                        f"Escrow: https://sepolia.etherscan.io/address/{status['contract_address']}",
                        "Payments use real test USDC and Sepolia ETH gas. No simulation fallback.",
                    ],
                    data=status,
                )
            if verb == "status" and len(args) == 1:
                operation = await self.operation(args[0])
                if operation.mode != mode:
                    raise ValueError("operation belongs to a different environment")
                return CommandResult(command=command, output=[operation.phase], operation=operation)
            if verb == "resume" and len(args) == 1:
                operation = await self.operation(args[0])
                if operation.mode != mode:
                    raise ValueError("operation belongs to a different environment")
                operation = await self.resume(args[0])
                return CommandResult(command=command, output=[operation.phase], operation=operation)
            if verb == "payments" and not args:
                rows = await self.payments(mode)
                return CommandResult(
                    command=command,
                    output=[
                        f"{row.status:10} {format_units(row.amount_units):>10} USDC  "
                        f"{row.payment_id}"
                        for row in rows
                    ]
                    or ["No payments yet. Try paradime buy."],
                    data=[
                        row.model_dump(mode="json")
                        | {
                            "explorer_links": explorer_links(
                                mode, deposit=row.deposit_tx_hash, resolution=row.resolution_tx_hash
                            )
                        }
                        for row in rows
                    ],
                )
            if verb == "receipt" and len(args) == 1:
                receipt = await self.receipt(args[0], mode)
                links = explorer_links(
                    mode, deposit=receipt.deposit_tx_hash, resolution=receipt.resolution_tx_hash
                )
                return CommandResult(
                    command=command,
                    output=[
                        f"{mode} receipt: {receipt.payment_id}",
                        f"Status: {receipt.status} · policy score: {receipt.risk_score}/100",
                        *receipt.risk_reasons,
                        *[f"{key.title()}: {url}" for key, url in links.items()],
                    ],
                    data=receipt.model_dump(mode="json") | {"explorer_links": links},
                )
            if verb == "buy":
                options = parse_options(args, {"--budget"})
                request = DemoInput(
                    mode=mode,
                    request_id=request_id,
                    budget_units=decimal_units(options.get("--budget", "3")),
                )
                scenario = "purchase"
            elif verb == "pay":
                options = parse_options(args, {"--scenario"})
                scenario = options.get("--scenario", "trusted")
                if scenario not in {"trusted", "watchlist"}:
                    raise ValueError("pay --scenario must be trusted or watchlist")
                request = DemoInput(mode=mode, request_id=request_id)
            elif (
                verb == "demo"
                and len(args) == 1
                and args[0] in {"purchase", "watchlist", "budget", "replay"}
            ):
                scenario, request = args[0], DemoInput(mode=mode, request_id=request_id)
            else:
                raise ValueError("unknown command or arguments; run paradime help")
            operation = await self.start(scenario, request)
            return CommandResult(
                command=command,
                output=[
                    f"Started {mode} operation: {operation.operation_id}",
                    "Waiting for chain receipts…"
                    if mode == "sepolia"
                    else "Running offline simulation…",
                ],
                operation=operation,
            )
        except (ValueError, InvalidOperation) as exc:
            return CommandResult(command=command, exit_code=2, output=[f"Error: {exc}"])


def parse_options(args: list[str], allowed: set[str]) -> dict[str, str]:
    options = {}
    if len(args) % 2:
        raise ValueError("each option needs a value; run paradime help")
    for key, value in zip(args[::2], args[1::2], strict=True):
        if key not in allowed or key in options:
            raise ValueError(f"unsupported or repeated option: {key}")
        options[key] = value
    return options


def decimal_units(value: str) -> str:
    amount = Decimal(value)
    if not amount.is_finite() or not 0 < amount <= 1_000_000:
        raise ValueError("budget must be between 0 and 1,000,000 USDC")
    units = amount * 1_000_000
    if units != units.to_integral_value():
        raise ValueError("USDC supports at most six decimal places")
    return str(int(units))


def format_units(value: str) -> str:
    return str(Decimal(value) / 1_000_000)


router = APIRouter(prefix="/api/demo", tags=["Demo workspace"])


@router.get("/status")
async def demo_status(request: Request):
    return await request.app.state.demo.status()


@router.post("/scenarios/{scenario}", response_model=OperationRead)
async def run_scenario(scenario: Scenario, payload: DemoInput, request: Request):
    try:
        return await request.app.state.demo.start(scenario, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/operations", response_model=list[OperationRead])
async def list_operations(request: Request, mode: Mode = "sepolia"):
    return await request.app.state.demo.operations(mode)


@router.get("/operations/{identifier}", response_model=OperationRead)
async def get_operation(identifier: str, request: Request):
    try:
        return await request.app.state.demo.operation(identifier)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/operations/{identifier}/resume", response_model=OperationRead)
async def resume_operation(identifier: str, request: Request):
    try:
        return await request.app.state.demo.resume(identifier)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/commands", response_model=CommandResult)
async def run_command(payload: CommandInput, request: Request):
    return await request.app.state.demo.command(payload.command, payload.mode, payload.request_id)
