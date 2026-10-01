import {
  BrowserProvider,
  Contract,
  Eip1193Provider,
  getAddress,
  hexlify,
  getBytes,
  keccak256,
  parseUnits,
  randomBytes,
  toUtf8Bytes,
} from "ethers";
import { api } from "./api";
import type { DemoPaymentInput, Health } from "./types";

const SEPOLIA_CHAIN_ID = 11155111n;
const SEPOLIA_HEX_CHAIN_ID = "0xaa36a7";

const TOKEN_ABI = [
  "function allowance(address owner, address spender) view returns (uint256)",
  "function approve(address spender, uint256 amount) returns (bool)",
  "function balanceOf(address owner) view returns (uint256)",
] as const;

const ESCROW_ABI = [
  "function deposit(bytes32 paymentId, address receiver, uint128 amount, bytes32 metadataHash)",
] as const;

declare global {
  interface Window {
    ethereum?: Eip1193Provider;
  }
}

export interface WalletState {
  address: string;
  balanceUnits: string;
}

export interface ChainDepositResult {
  paymentId: string;
  depositTxHash: string;
  approvalTxHash: string | null;
  sender: string;
  receiver: string;
  amountUnits: string;
}

function requireChainConfig(health: Health) {
  if (!health.contract_address || !health.payment_token_address) {
    throw new Error("Sepolia escrow or USDC contract is not configured by the backend");
  }
  return {
    escrow: getAddress(health.contract_address),
    token: getAddress(health.payment_token_address),
  };
}

async function browserProvider(): Promise<BrowserProvider> {
  if (!window.ethereum) {
    throw new Error("A browser wallet such as MetaMask is required for Sepolia payments");
  }
  let provider = new BrowserProvider(window.ethereum);
  await provider.send("eth_requestAccounts", []);
  if ((await provider.getNetwork()).chainId !== SEPOLIA_CHAIN_ID) {
    await provider.send("wallet_switchEthereumChain", [{ chainId: SEPOLIA_HEX_CHAIN_ID }]);
    provider = new BrowserProvider(window.ethereum);
  }
  return provider;
}

export async function connectSepoliaWallet(health: Health): Promise<WalletState> {
  const { token } = requireChainConfig(health);
  const provider = await browserProvider();
  const signer = await provider.getSigner();
  const address = await signer.getAddress();
  const contract = new Contract(token, TOKEN_ABI, provider);
  const balance = (await contract.balanceOf(address)) as bigint;
  return { address: address.toLowerCase(), balanceUnits: balance.toString() };
}

export async function depositSepoliaUsdc(
  input: DemoPaymentInput,
  health: Health,
  onStage: (stage: "approval" | "deposit") => void,
): Promise<ChainDepositResult> {
  const { escrow, token } = requireChainConfig(health);
  const provider = await browserProvider();
  const signer = await provider.getSigner();
  const sender = await signer.getAddress();
  const receiver = getAddress(input.receiver);
  if (sender.toLowerCase() === receiver.toLowerCase()) {
    throw new Error("Sender and receiver wallets must differ");
  }
  const amount = parseUnits(input.amount_usdc, health.stablecoin_decimals);
  const tokenContract = new Contract(token, TOKEN_ABI, signer);
  const balance = (await tokenContract.balanceOf(sender)) as bigint;
  if (balance < amount) {
    throw new Error(`Insufficient test ${health.stablecoin_symbol} balance`);
  }

  let approvalTxHash: string | null = null;
  const allowance = (await tokenContract.allowance(sender, escrow)) as bigint;
  if (allowance < amount) {
    onStage("approval");
    const approval = await tokenContract.approve(escrow, amount);
    approvalTxHash = approval.hash;
    const approvalReceipt = await approval.wait();
    if (!approvalReceipt || approvalReceipt.status !== 1) {
      throw new Error("USDC approval transaction failed");
    }
  }

  onStage("deposit");
  const paymentId = hexlify(randomBytes(32));
  const expiresAt = new Date(Math.floor((Date.now() + 5 * 60_000) / 1000) * 1000)
    .toISOString()
    .replace(".000Z", "Z");
  const nonce = hexlify(randomBytes(32));
  const intent = {
    payment_id: paymentId.toLowerCase(),
    sender: sender.toLowerCase(),
    receiver: receiver.toLowerCase(),
    amount_units: amount.toString(),
    token: token.toLowerCase(),
    purpose: input.description,
    service_or_sku: "interactive-payment",
    mandate: "User-approved wallet transaction",
    expires_at: expiresAt,
    nonce: nonce.toLowerCase(),
  };
  const metadataHash = keccak256(toUtf8Bytes(JSON.stringify(intent)));
  const signature = await signer.signMessage(getBytes(metadataHash));
  await api.registerIntent({ ...intent, metadata_hash: metadataHash, signature });
  const escrowContract = new Contract(escrow, ESCROW_ABI, signer);
  const deposit = await escrowContract.deposit(paymentId, receiver, amount, metadataHash);
  const receipt = await deposit.wait();
  if (!receipt || receipt.status !== 1) {
    throw new Error("Escrow deposit transaction failed");
  }
  return {
    paymentId,
    depositTxHash: deposit.hash,
    approvalTxHash,
    sender: sender.toLowerCase(),
    receiver: receiver.toLowerCase(),
    amountUnits: amount.toString(),
  };
}
