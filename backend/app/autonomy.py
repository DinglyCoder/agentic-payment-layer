import asyncio
import hashlib
import json
import re
import secrets
from datetime import UTC, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount
from eth_utils import keccak
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .config import Settings
from .models import AutonomousPurchase, Payment, PaymentStatus, SpendingMandate, utc_now
from .schemas import (
    AutonomousDemoCreate,
    AutonomousPurchaseCreate,
    IntentEnvelopeCreate,
    SpendingMandateCreate,
)

MCP_PROTOCOL_VERSION = "2026-07-28"
SELLER_TOOL_NAME = "analyze_text"


def canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return "0x" + keccak(text=encoded).hex()


def signature_hex(account: LocalAccount, digest: str) -> str:
    signature = account.sign_message(encode_defunct(hexstr=digest)).signature.hex()
    return signature if signature.startswith("0x") else "0x" + signature


def mandate_payload(request: SpendingMandateCreate) -> dict:
    return {
        "owner": request.owner.lower(),
        "delegate": request.delegate.lower(),
        "token": request.token.lower(),
        "max_amount_per_payment_units": request.max_amount_per_payment_units,
        "total_budget_units": request.total_budget_units,
        "allowed_receiver": request.allowed_receiver.lower(),
        "allowed_service": request.allowed_service,
        "expires_at": request.expires_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "nonce": request.nonce.lower(),
    }


class SellerComputeAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def address(self) -> str:
        address = self.settings.seller_address
        if not address and self.settings.simulation_mode:
            address = self.settings.simulation_seller_address
        if not address:
            raise ValueError("seller wallet is not configured")
        return address.lower()

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": SELLER_TOOL_NAME,
                "title": "Deterministic text analysis",
                "description": (
                    f"Analyze bounded text for {self.settings.seller_price_units} base units"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "minLength": 3, "maxLength": 1000},
                        "purchase_id": {"type": "string"},
                    },
                    "required": ["prompt", "purchase_id"],
                    "additionalProperties": False,
                },
            }
        ]

    def payment_required(self) -> dict:
        token = (
            self.settings.payment_token_address or self.settings.simulation_token_address
        ).lower()
        return {
            "x402Version": 2,
            "error": "Payment required to access this resource",
            "resource": {
                "url": f"mcp://paradime/{SELLER_TOOL_NAME}",
                "description": "Deterministic bounded text analysis",
                "mimeType": "application/json",
                "serviceName": "Paradime Compute",
                "tags": ["compute", "text-analysis"],
            },
            "accepts": [
                {
                    "scheme": "paradime-escrow",
                    "network": "eip155:11155111",
                    "amount": str(self.settings.seller_price_units),
                    "asset": token,
                    "payTo": self.address,
                    "maxTimeoutSeconds": self.settings.autonomous_purchase_timeout_seconds,
                    "extra": {
                        "assetTransferMethod": "paradime-escrow",
                        "paymentFlow": "upfront",
                        "escrow": self.settings.escrow_contract_address or "simulation",
                    },
                }
            ],
            "extensions": {},
        }

    @staticmethod
    def payment_required_result(requirement: dict) -> dict:
        return {
            "isError": True,
            "structuredContent": requirement,
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(requirement, separators=(",", ":")),
                }
            ],
        }

    async def call_tool(self, sessions, name: str, arguments: dict, meta: dict) -> dict:
        if name != SELLER_TOOL_NAME:
            raise ValueError("unknown seller tool")
        prompt = arguments.get("prompt")
        purchase_id = arguments.get("purchase_id")
        if not isinstance(prompt, str) or not 3 <= len(prompt) <= 1000:
            raise ValueError("prompt must contain 3 to 1000 characters")
        if not isinstance(purchase_id, str):
            raise ValueError("purchase_id is required")

        payment_payload = meta.get("x402/payment") if isinstance(meta, dict) else None
        if not isinstance(payment_payload, dict):
            return self.payment_required_result(self.payment_required())

        async with sessions() as session:
            purchase = await session.get(AutonomousPurchase, purchase_id.lower())
            if purchase is None or purchase.status != "paid":
                raise ValueError("purchase is not awaiting seller execution")
            if purchase.prompt != prompt:
                raise ValueError("tool arguments do not match the authorized purchase")
            payment_id = payment_payload.get("payload", {}).get("paymentId")
            if not isinstance(payment_id, str) or payment_id.lower() != purchase.payment_id:
                raise ValueError("x402 payload does not reference the purchase payment")
            payment = await session.get(Payment, purchase.payment_id)
            if payment is None or payment.status != PaymentStatus.EXECUTED:
                raise ValueError("Paradime payment has not executed")
            mandate = await session.get(SpendingMandate, purchase.mandate_id)
            if mandate is None:
                raise ValueError("purchase mandate no longer exists")
            if (
                payment.sender != mandate.delegate
                or payment.receiver != purchase.seller
                or payment.amount_units != purchase.amount_units
            ):
                raise ValueError("Paradime payment does not match the authorized purchase")
            if payment_payload.get("accepted") != purchase.x402_requirement["accepts"][0]:
                raise ValueError("x402 terms do not match the seller challenge")
            self._verify_payment_signature(payment_payload, purchase, mandate)

        result = self._analyze(prompt)
        return {
            "isError": False,
            "structuredContent": result,
            "content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}],
            "_meta": {
                "x402/payment-response": {
                    "success": True,
                    "network": "eip155:11155111",
                    "transaction": payment.resolution_tx_hash,
                    "payer": payment.sender,
                }
            },
        }

    def _verify_payment_signature(
        self,
        payment_payload: dict,
        purchase: AutonomousPurchase,
        mandate: SpendingMandate,
    ) -> None:
        payload = payment_payload.get("payload", {})
        signature = payload.get("signature")
        payer = payload.get("payer")
        signed = {
            "payment_id": payload.get("paymentId"),
            "purchase_id": purchase.purchase_id,
            "mandate_id": mandate.mandate_id,
            "payer": payer,
            "accepted": payment_payload.get("accepted"),
        }
        if not isinstance(signature, str) or not isinstance(payer, str):
            raise ValueError("x402 payload is missing payer authorization")
        recovered = Account.recover_message(
            encode_defunct(hexstr=canonical_hash(signed)), signature=signature
        ).lower()
        if recovered != mandate.delegate or recovered != payer.lower():
            raise ValueError("x402 payment was not authorized by the mandate delegate")

    @staticmethod
    def _analyze(prompt: str) -> dict:
        words = re.findall(r"[A-Za-z0-9']+", prompt.lower())
        positive = {"good", "great", "safe", "success", "trusted"}
        negative = {"bad", "fail", "fraud", "risk", "unsafe"}
        sentiment_score = sum(word in positive for word in words) - sum(
            word in negative for word in words
        )
        classification = (
            "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral"
        )
        return {
            "classification": classification,
            "word_count": len(words),
            "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        }


class BuyerAgent:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker,
        processor,
        chain,
        seller: SellerComputeAgent,
        *,
        account: LocalAccount | None = None,
        submit_deposit=None,
    ) -> None:
        self.settings = settings
        self.sessions = sessions
        self.processor = processor
        self.chain = chain
        self.seller = seller
        self._submit_deposit = submit_deposit or chain.deposit_from
        self._purchase_lock = asyncio.Lock()
        if account is not None:
            self.account = account
        elif settings.autonomous_buyer_private_key:
            self.account: LocalAccount | None = Account.from_key(
                settings.autonomous_buyer_private_key.get_secret_value()
            )
        elif settings.simulation_mode:
            self.account = Account.create()
        else:
            self.account = None

    @property
    def address(self) -> str | None:
        return self.account.address.lower() if self.account else None

    async def register_mandate(self, request: SpendingMandateCreate) -> SpendingMandate:
        if self.account is None:
            raise ValueError("autonomous buyer wallet is not configured")
        payload = mandate_payload(request)
        digest = canonical_hash(payload)
        if digest != request.mandate_id.lower():
            raise ValueError("mandate_id does not match the canonical spending mandate")
        recovered = Account.recover_message(
            encode_defunct(hexstr=digest), signature=request.signature
        ).lower()
        if recovered != request.owner.lower():
            raise ValueError("mandate signature is not from the owner wallet")
        if request.delegate.lower() != self.address:
            raise ValueError("mandate delegate does not match the configured buyer wallet")
        expires_at = request.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= utc_now() or expires_at > utc_now() + timedelta(days=30):
            raise ValueError("mandate expiry must be in the next 30 days")
        if int(request.max_amount_per_payment_units) > int(request.total_budget_units):
            raise ValueError("per-payment limit cannot exceed the total budget")

        async with self.sessions() as session:
            if await session.get(SpendingMandate, digest):
                raise ValueError("spending mandate already exists")
            existing_nonce = await session.scalar(
                select(SpendingMandate).where(SpendingMandate.nonce == payload["nonce"])
            )
            if existing_nonce:
                raise ValueError("spending mandate nonce has already been used")
            mandate = SpendingMandate(
                mandate_id=digest,
                owner=payload["owner"],
                delegate=payload["delegate"],
                token=payload["token"],
                max_amount_per_payment_units=payload["max_amount_per_payment_units"],
                total_budget_units=payload["total_budget_units"],
                allowed_receiver=payload["allowed_receiver"],
                allowed_service=payload["allowed_service"],
                expires_at=expires_at,
                nonce=payload["nonce"],
                signature=request.signature,
            )
            session.add(mandate)
            await session.commit()
            return mandate

    async def purchase(
        self,
        request: AutonomousPurchaseCreate,
        *,
        purchase_id: str | None = None,
        payment_id: str | None = None,
    ) -> AutonomousPurchase:
        if self.account is None:
            raise ValueError("autonomous buyer wallet is not configured")
        async with self._purchase_lock:
            tool = next(
                (tool for tool in self.seller.list_tools() if tool["name"] == SELLER_TOOL_NAME),
                None,
            )
            if tool is None:
                raise ValueError("seller did not advertise the required compute tool")
            challenge = await self.seller.call_tool(
                self.sessions,
                tool["name"],
                {"prompt": request.prompt, "purchase_id": "0x" + "0" * 64},
                {},
            )
            requirement = challenge["structuredContent"]
            accepted = requirement["accepts"][0]

            async with self.sessions() as session:
                mandate = await session.get(SpendingMandate, request.mandate_id.lower())
                self._enforce_mandate(mandate, accepted)
                purchase_id = purchase_id or "0x" + secrets.token_hex(32)
                purchase = AutonomousPurchase(
                    purchase_id=purchase_id,
                    mandate_id=mandate.mandate_id,
                    seller=self.seller.address,
                    service=self.settings.seller_service,
                    prompt=request.prompt,
                    amount_units=accepted["amount"],
                    status="authorized",
                    x402_requirement=requirement,
                )
                mandate.spent_units = str(int(mandate.spent_units) + int(accepted["amount"]))
                session.add(purchase)
                await session.commit()

            payment_id = payment_id or "0x" + secrets.token_hex(32)
            async with self.sessions() as session:
                stored = await session.get(AutonomousPurchase, purchase.purchase_id)
                stored.payment_id = payment_id
                await session.commit()

            try:
                payment = await self._pay(purchase, mandate, payment_id)
                if payment.status != PaymentStatus.EXECUTED:
                    await self._fail_purchase(
                        purchase.purchase_id,
                        f"Paradime decision was {payment.status}",
                        release_budget=True,
                    )
                    return await self._load_purchase(purchase.purchase_id)

                return await self.fulfill_purchase(purchase.purchase_id)
            except Exception as exc:
                await self._fail_purchase(purchase.purchase_id, str(exc), release_budget=False)
                raise

    async def fulfill_purchase(self, purchase_id: str) -> AutonomousPurchase:
        """Finish already-paid work, including after restart. Never submit a deposit here."""
        async with self.sessions() as session:
            purchase = await session.get(AutonomousPurchase, purchase_id)
            if purchase is None:
                raise ValueError("purchase not found")
            mandate = await session.get(SpendingMandate, purchase.mandate_id)
            if (
                mandate is None
                or mandate.delegate != self.address
                or purchase.seller != self.seller.address
            ):
                raise ValueError("purchase belongs to a different payer or seller")
            if purchase.status == "completed":
                return purchase
        payment = await self.processor.wait_for_terminal_payment(
            purchase.payment_id,
            self.settings.autonomous_purchase_timeout_seconds,
        )
        if payment.status != PaymentStatus.EXECUTED:
            raise ValueError("payment did not execute; work cannot be released")
        payload = self._payment_payload(
            purchase,
            mandate,
            payment,
            purchase.x402_requirement["accepts"][0],
        )
        async with self.sessions() as session:
            stored = await session.get(AutonomousPurchase, purchase_id)
            stored.x402_payload = payload
            stored.status = "paid"
            await session.commit()
        response = await self.seller.call_tool(
            self.sessions,
            SELLER_TOOL_NAME,
            {"prompt": purchase.prompt, "purchase_id": purchase_id},
            {"x402/payment": payload},
        )
        async with self.sessions() as session:
            stored = await session.get(AutonomousPurchase, purchase_id)
            stored.result = response["structuredContent"]
            stored.status = "completed"
            stored.completed_at = utc_now()
            stored.failure_reason = None
            await session.commit()
            return stored

    def _enforce_mandate(self, mandate: SpendingMandate | None, accepted: dict) -> None:
        if mandate is None:
            raise ValueError("spending mandate not found")
        expires_at = mandate.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= utc_now():
            raise ValueError("spending mandate has expired")
        if mandate.delegate != self.address:
            raise ValueError("spending mandate is for a different delegate")
        if mandate.allowed_receiver != accepted["payTo"].lower():
            raise ValueError("seller is not allowed by the spending mandate")
        if mandate.allowed_service != self.settings.seller_service:
            raise ValueError("service is not allowed by the spending mandate")
        if mandate.token != accepted["asset"].lower():
            raise ValueError("payment token is not allowed by the spending mandate")
        amount = int(accepted["amount"])
        if amount > int(mandate.max_amount_per_payment_units):
            raise ValueError("seller price exceeds the per-payment mandate limit")
        if int(mandate.spent_units) + amount > int(mandate.total_budget_units):
            raise ValueError("seller price exceeds the remaining mandate budget")

    async def _pay(
        self, purchase: AutonomousPurchase, mandate: SpendingMandate, payment_id: str
    ) -> Payment:
        expires_at = (utc_now() + timedelta(minutes=5)).replace(microsecond=0)
        intent = {
            "payment_id": payment_id,
            "sender": self.address,
            "receiver": self.seller.address,
            "amount_units": purchase.amount_units,
            "token": mandate.token,
            "purpose": purchase.prompt[:240],
            "service_or_sku": purchase.service,
            "mandate": mandate.mandate_id,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "nonce": "0x" + secrets.token_hex(32),
        }
        metadata_hash = canonical_hash(intent)
        if self.settings.simulation_mode:
            return await self.processor.create_autonomous_demo(
                payment_id=payment_id,
                sender=self.address,
                receiver=self.seller.address,
                amount_units=purchase.amount_units,
                description=purchase.prompt[:240],
                metadata_hash=metadata_hash,
            )

        envelope = IntentEnvelopeCreate(
            **intent,
            metadata_hash=metadata_hash,
            signature=signature_hex(self.account, metadata_hash),
        )
        await self.processor.register_intent(envelope)
        await self._submit_deposit(
            self.account,
            payment_id,
            self.seller.address,
            int(purchase.amount_units),
            metadata_hash,
        )
        return await self.processor.wait_for_terminal_payment(
            payment_id, self.settings.autonomous_purchase_timeout_seconds
        )

    def _payment_payload(
        self,
        purchase: AutonomousPurchase,
        mandate: SpendingMandate,
        payment: Payment,
        accepted: dict,
    ) -> dict:
        signed = {
            "payment_id": payment.payment_id,
            "purchase_id": purchase.purchase_id,
            "mandate_id": mandate.mandate_id,
            "payer": self.address,
            "accepted": accepted,
        }
        return {
            "x402Version": 2,
            "resource": purchase.x402_requirement["resource"],
            "accepted": accepted,
            "payload": {
                "paymentId": payment.payment_id,
                "mandateId": mandate.mandate_id,
                "purchaseId": purchase.purchase_id,
                "payer": self.address,
                "signature": signature_hex(self.account, canonical_hash(signed)),
            },
            "extensions": {},
        }

    async def _fail_purchase(self, purchase_id: str, reason: str, *, release_budget: bool) -> None:
        async with self.sessions() as session:
            purchase = await session.get(AutonomousPurchase, purchase_id)
            if purchase is None:
                return
            purchase.status = "failed"
            purchase.failure_reason = reason[:240]
            purchase.completed_at = utc_now()
            if release_budget:
                mandate = await session.get(SpendingMandate, purchase.mandate_id)
                mandate.spent_units = str(
                    max(0, int(mandate.spent_units) - int(purchase.amount_units))
                )
            await session.commit()

    async def _load_purchase(self, purchase_id: str) -> AutonomousPurchase:
        async with self.sessions() as session:
            return await session.get(AutonomousPurchase, purchase_id)

    async def create_demo(self, request: AutonomousDemoCreate) -> AutonomousPurchase:
        if not self.settings.simulation_mode:
            raise ValueError("autonomous demo is only available in simulation mode")
        owner = Account.create()
        expires_at = (utc_now() + timedelta(minutes=10)).replace(microsecond=0)
        unsigned = {
            "owner": owner.address.lower(),
            "delegate": self.address,
            "token": self.settings.simulation_token_address.lower(),
            "max_amount_per_payment_units": request.budget_units,
            "total_budget_units": request.budget_units,
            "allowed_receiver": self.seller.address,
            "allowed_service": self.settings.seller_service,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "nonce": "0x" + secrets.token_hex(32),
        }
        mandate_id = canonical_hash(unsigned)
        mandate = await self.register_mandate(
            SpendingMandateCreate(
                **unsigned,
                mandate_id=mandate_id,
                signature=signature_hex(owner, mandate_id),
            )
        )
        return await self.purchase(
            AutonomousPurchaseCreate(mandate_id=mandate.mandate_id, prompt=request.prompt)
        )


mcp_router = APIRouter()


@mcp_router.post("/mcp/seller")
async def seller_mcp(request: Request) -> dict:
    message = await request.json()
    request_id = message.get("id")
    method = message.get("method")
    try:
        if method == "initialize":
            result = {
                "protocolVersion": message.get("params", {}).get(
                    "protocolVersion", MCP_PROTOCOL_VERSION
                ),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "paradime-seller", "version": "0.2.0"},
            }
        elif method == "tools/list":
            result = {"tools": request.app.state.seller.list_tools()}
        elif method == "tools/call":
            params = message.get("params", {})
            result = await request.app.state.seller.call_tool(
                request.app.state.sessions,
                params.get("name"),
                params.get("arguments", {}),
                params.get("_meta", {}),
            )
        else:
            raise ValueError("unsupported MCP method")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except ValueError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32602, "message": str(exc)},
        }
