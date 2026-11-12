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


def validate_payment_receiver(sender: str, receiver: str, token: str, escrow: str) -> None:
    if not Web3.is_address(receiver) or int(receiver, 16) == 0:
        raise ValueError("Enter a valid receiving wallet address")
    if receiver.lower() == sender.lower():
        raise ValueError("Sender and receiver wallets must differ")
    if receiver.lower() == token.lower():
        raise ValueError(
            "The USDC token contract is not a payment recipient. Enter the receiving wallet."
        )
    if receiver.lower() == escrow.lower():
        raise ValueError(
            "The escrow contract is not a payment recipient. Enter the receiving wallet."
        )


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


@dataclass(frozen=True, slots=True)
class ResolutionEvent:
    payment_id: str
    status: str
    transaction_hash: str
    block_number: int


@dataclass(frozen=True, slots=True)
class DepositSubmission:
    deposit_tx_hash: str
    approval_tx_hash: str | None


class EscrowChain:
    """Async Sepolia event source and single-key arbitrator transaction signer."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.chain_enabled
        self._stop = asyncio.Event()
        self._nonce_lock = asyncio.Lock()
        self._buyer_nonce_lock = asyncio.Lock()
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
        assert self.w3 is not None and self.contract is not None and self.account is not None
        if await self.w3.eth.chain_id != 11155111:
            raise RuntimeError("SEPOLIA_RPC_URL is not connected to Ethereum Sepolia")
        if not await self.w3.eth.get_code(self.contract.address):
            raise RuntimeError("ESCROW_CONTRACT_ADDRESS has no deployed bytecode")
        configured_token = Web3.to_checksum_address(self.settings.payment_token_address)
        contract_token = Web3.to_checksum_address(
            await self.contract.functions.paymentToken().call()
        )
        if contract_token != configured_token:
            raise RuntimeError("PAYMENT_TOKEN_ADDRESS does not match the escrow's immutable token")
        token = self.w3.eth.contract(
            address=contract_token,
            abi=[
                {
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
                    "stateMutability": "view",
                    "type": "function",
                }
            ],
        )
        if await token.functions.decimals().call() != self.settings.stablecoin_decimals:
            raise RuntimeError("STABLECOIN_DECIMALS does not match the configured token")
        contract_arbitrator = Web3.to_checksum_address(
            await self.contract.functions.arbitrator().call()
        )
        configured_arbitrator = Web3.to_checksum_address(self.account.address)
        if contract_arbitrator != configured_arbitrator:
            raise RuntimeError("ARBITRATOR_PRIVATE_KEY does not control the escrow arbitrator")

    async def current_time(self) -> datetime:
        """Return chain time so deadline decisions match contract execution."""
        if not self.enabled:
            return datetime.now(UTC)
        assert self.w3 is not None
        block = await self.w3.eth.get_block("latest")
        return datetime.fromtimestamp(block["timestamp"], UTC)

    async def listen(
        self,
        on_deposit: Callable[[DepositEvent], Awaitable[None]],
        on_resolution: Callable[[ResolutionEvent], Awaitable[None]],
        on_tick: Callable[[], Awaitable[None]],
        load_cursor: Callable[[int], Awaitable[tuple[int, str | None]]],
        save_cursor: Callable[[int, str], Awaitable[None]],
        on_reconcile: Callable[[], Awaitable[None]],
    ) -> None:
        if not self.enabled:
            return
        assert self.w3 is not None and self.contract is not None
        latest = await self.w3.eth.block_number
        default_start = self.settings.chain_start_block or max(0, latest - 100)
        next_block, previous_hash = await load_cursor(default_start)

        while not self._stop.is_set():
            try:
                head = await self.w3.eth.block_number
                safe_head = head - self.settings.chain_confirmations
                if previous_hash and next_block > 0:
                    prior = await self.w3.eth.get_block(next_block - 1)
                    if HexBytes(prior["hash"]).to_0x_hex() != previous_hash:
                        rewind = next_block - self.settings.chain_confirmations - 1
                        next_block = max(default_start, rewind)
                        previous_hash = None
                if safe_head >= next_block:
                    deposits = await self.contract.events.PaymentDeposited().get_logs(
                        from_block=next_block, to_block=safe_head
                    )
                    for log in deposits:
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
                    for event_name, status in (
                        ("PaymentExecuted", "executed"),
                        ("PaymentRecalled", "recalled"),
                    ):
                        logs = await getattr(self.contract.events, event_name)().get_logs(
                            from_block=next_block, to_block=safe_head
                        )
                        for log in logs:
                            await on_resolution(
                                ResolutionEvent(
                                    payment_id=HexBytes(log["args"]["paymentId"]).to_0x_hex(),
                                    status=status,
                                    transaction_hash=HexBytes(log["transactionHash"]).to_0x_hex(),
                                    block_number=log["blockNumber"],
                                )
                            )
                    block = await self.w3.eth.get_block(safe_head)
                    previous_hash = HexBytes(block["hash"]).to_0x_hex()
                    next_block = safe_head + 1
                    await save_cursor(next_block, previous_hash)
                await on_tick()
                await on_reconcile()
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

    async def payment_state(self, payment_id: str) -> int:
        if not self.enabled:
            return 0
        assert self.contract is not None
        payment = await self.contract.functions.payments(HexBytes(payment_id)).call()
        return int(payment[5])

    async def deposit_from(
        self,
        account: LocalAccount,
        payment_id: str,
        receiver: str,
        amount_units: int,
        metadata_hash: str,
        *,
        on_submitted: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> DepositSubmission:
        if not self.enabled:
            raise RuntimeError("chain deposit requested in simulation mode")
        assert self.w3 is not None and self.contract is not None
        token = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.payment_token_address),
            abi=[
                {
                    "inputs": [
                        {"internalType": "address", "name": "owner", "type": "address"},
                        {"internalType": "address", "name": "spender", "type": "address"},
                    ],
                    "name": "allowance",
                    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function",
                },
                {
                    "inputs": [
                        {"internalType": "address", "name": "spender", "type": "address"},
                        {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    ],
                    "name": "approve",
                    "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                    "stateMutability": "nonpayable",
                    "type": "function",
                },
            ],
        )
        approval_tx_hash = None
        async with self._buyer_nonce_lock:
            allowance = await token.functions.allowance(
                account.address, self.contract.address
            ).call()
            if allowance < amount_units:
                approval = await self._send_account_transaction(
                    account,
                    token.functions.approve(self.contract.address, amount_units),
                    stage="approval",
                    on_submitted=on_submitted,
                )
                if approval["status"] != 1:
                    raise RuntimeError("autonomous token approval reverted")
                approval_tx_hash = HexBytes(approval["transactionHash"]).to_0x_hex()
            receipt = await self._send_account_transaction(
                account,
                self.contract.functions.deposit(
                    HexBytes(payment_id),
                    Web3.to_checksum_address(receiver),
                    amount_units,
                    HexBytes(metadata_hash),
                ),
                stage="deposit",
                on_submitted=on_submitted,
            )
        if receipt["status"] != 1:
            raise RuntimeError("autonomous escrow deposit reverted")
        return DepositSubmission(
            deposit_tx_hash=HexBytes(receipt["transactionHash"]).to_0x_hex(),
            approval_tx_hash=approval_tx_hash,
        )

    async def token_balance(self, address: str) -> int:
        if not self.enabled:
            raise RuntimeError("token balance requested in simulation mode")
        assert self.w3 is not None
        token = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.payment_token_address),
            abi=[
                {
                    "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                    "stateMutability": "view",
                    "type": "function",
                }
            ],
        )
        return int(await token.functions.balanceOf(Web3.to_checksum_address(address)).call())

    async def native_balance(self, address: str) -> int:
        if not self.enabled or self.w3 is None:
            raise RuntimeError("ETH balance requested without a Sepolia connection")
        return int(await self.w3.eth.get_balance(Web3.to_checksum_address(address)))

    async def _send_account_transaction(
        self,
        account: LocalAccount,
        contract_call,
        *,
        stage: str,
        on_submitted: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        assert self.w3 is not None
        nonce = await self.w3.eth.get_transaction_count(account.address, "pending")
        transaction = await contract_call.build_transaction(
            {"from": account.address, "nonce": nonce, "chainId": await self.w3.eth.chain_id}
        )
        signed = account.sign_transaction(transaction)
        tx_hash = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        if on_submitted:
            await on_submitted(stage, tx_hash.to_0x_hex())
        return await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    def stop(self) -> None:
        self._stop.set()
