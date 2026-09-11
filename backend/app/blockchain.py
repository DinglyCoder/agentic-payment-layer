import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from eth_account.signers.local import LocalAccount
from hexbytes import HexBytes
from web3 import AsyncHTTPProvider, AsyncWeb3, Web3

from .config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DepositEvent:
    payment_id: str
    sender: str
    receiver: str
    amount_units: int
    metadata_hash: str
    deposited_at: datetime
    recall_deadline: datetime
    transaction_hash: str
    block_number: int


class EscrowChain:
    """Async Sepolia event source and single-key arbitrator transaction signer."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.chain_enabled
        self._stop = asyncio.Event()
        self._nonce_lock = asyncio.Lock()
        self.w3: AsyncWeb3 | None = None
        self.account: LocalAccount | None = None
        self.contract = None

        if self.enabled:
            abi_path = Path(__file__).with_name("contract_abi.json")
            abi = json.loads(abi_path.read_text())
            self.w3 = AsyncWeb3(AsyncHTTPProvider(settings.sepolia_rpc_url))
            key = settings.arbitrator_private_key.get_secret_value()
            self.account = self.w3.eth.account.from_key(key)
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.escrow_contract_address), abi=abi
            )

    async def validate(self) -> None:
        if not self.enabled:
            return
        assert self.w3 is not None and self.contract is not None
        if await self.w3.eth.chain_id != 11155111:
            raise RuntimeError("SEPOLIA_RPC_URL is not connected to Ethereum Sepolia")
        if not await self.w3.eth.get_code(self.contract.address):
            raise RuntimeError("ESCROW_CONTRACT_ADDRESS has no deployed bytecode")

    async def listen(
        self,
        on_deposit: Callable[[DepositEvent], Awaitable[None]],
        on_tick: Callable[[], Awaitable[None]],
    ) -> None:
        if not self.enabled:
            return
        assert self.w3 is not None and self.contract is not None
        latest = await self.w3.eth.block_number
        next_block = self.settings.chain_start_block or max(0, latest - 100)

        while not self._stop.is_set():
            try:
                head = await self.w3.eth.block_number
                safe_head = head - self.settings.chain_confirmations
                if safe_head >= next_block:
                    logs = await self.contract.events.PaymentDeposited().get_logs(
                        from_block=next_block, to_block=safe_head
                    )
                    for log in logs:
                        args = log["args"]
                        await on_deposit(
                            DepositEvent(
                                payment_id=HexBytes(args["paymentId"]).to_0x_hex(),
                                sender=args["sender"].lower(),
                                receiver=args["receiver"].lower(),
                                amount_units=int(args["amount"]),
                                metadata_hash=HexBytes(args["metadataHash"]).to_0x_hex(),
                                deposited_at=datetime.fromtimestamp(args["depositedAt"], UTC),
                                recall_deadline=datetime.fromtimestamp(args["recallDeadline"], UTC),
                                transaction_hash=HexBytes(log["transactionHash"]).to_0x_hex(),
                                block_number=log["blockNumber"],
                            )
                        )
                    next_block = safe_head + 1
                await on_tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Sepolia polling cycle failed")
            try:
                await asyncio.wait_for(self._stop.wait(), self.settings.poll_interval_seconds)
            except TimeoutError:
                pass

    async def resolve(self, payment_id: str, decision: str) -> str:
        if not self.enabled:
            raise RuntimeError("chain resolution requested in simulation mode")
        assert self.w3 is not None and self.account is not None and self.contract is not None
        contract_call = (
            self.contract.functions.recallPayment(HexBytes(payment_id))
            if decision == "recall"
            else self.contract.functions.executePayment(HexBytes(payment_id))
        )
        async with self._nonce_lock:
            nonce = await self.w3.eth.get_transaction_count(self.account.address, "pending")
            transaction = await contract_call.build_transaction(
                {
                    "from": self.account.address,
                    "nonce": nonce,
                    "chainId": await self.w3.eth.chain_id,
                }
            )
            signed = self.account.sign_transaction(transaction)
            tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt["status"] != 1:
            raise RuntimeError(f"arbitration transaction reverted: {tx_hash.to_0x_hex()}")
        return tx_hash.to_0x_hex()

    def stop(self) -> None:
        self._stop.set()
