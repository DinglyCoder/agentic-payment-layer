export interface Payment {
  payment_id: string;
  sender: string;
  receiver: string;
  amount_units: string;
  metadata_hash: string;
  description: string;
  deposit_tx_hash: string;
  resolution_tx_hash: string | null;
  block_number: number | null;
  deposited_at: string;
  recall_deadline: string;
  status:
    | "detected"
    | "scoring"
    | "approved"
    | "executed"
    | "recalled"
    | "failed";
  decision: "execute" | "recall" | null;
  risk_score: number | null;
  risk_level: "low" | "medium" | "high" | null;
  risk_reasons: string[];
  risk_signals: RiskSignal[];
  policy_version: string | null;
  llm_score: number | null;
  source: string;
  decision_latency_ms: number | null;
  resolution_attempts: number;
  resolution_error: string | null;
}

export interface RiskSignal {
  name: string;
  contribution: number;
  weight: number;
  evidence: Record<string, unknown>;
}

export interface IntentEnvelopeInput {
  payment_id: string;
  sender: string;
  receiver: string;
  amount_units: string;
  token: string;
  purpose: string;
  service_or_sku: string;
  mandate: string;
  expires_at: string;
  nonce: string;
  metadata_hash: string;
  signature: string;
}

export interface Agent {
  address: string;
  name: string;
  status: "verified" | "watchlist" | "unknown";
  trust_score: number;
}

export interface Stats {
  total_payments: number;
  executed_payments: number;
  recalled_payments: number;
  protected_value_units: string;
  execution_rate: number;
  average_risk_score: number;
}

export interface Health {
  status: string;
  mode: "simulation" | "sepolia";
  testnet_available: boolean;
  chain_id: number;
  contract_address: string | null;
  payment_token_address: string | null;
  llm_enabled: boolean;
  stablecoin_symbol: string;
  stablecoin_decimals: number;
}

export interface DemoPaymentInput {
  sender: string;
  receiver: string;
  amount_usdc: string;
  description: string;
}

export interface ManagedDemoWallet {
  enabled: boolean;
  address: string | null;
  balance_units: string | null;
  native_balance_wei: string | null;
  max_amount_units: string;
  remaining_session_budget_units: string;
}

export interface ManagedDemoPayment {
  payment_id: string;
  deposit_tx_hash: string;
  approval_tx_hash: string | null;
  sender: string;
  receiver: string;
  amount_units: string;
}

export interface PaymentPreviewInput {
  kind: "direct" | "scenario" | "command";
  mode: "simulation" | "sepolia";
  payer?: "managed" | "browser";
  sender?: string;
  receiver?: string;
  amount_usdc?: string;
  description?: string;
  scenario?: "purchase" | "trusted" | "watchlist" | "budget" | "replay";
  command?: string;
  budget_units?: string;
}

export interface PaymentReview {
  mode: "simulation" | "sepolia";
  title: string;
  amount_units: string;
  offer_units: string | null;
  budget_units: string | null;
  sender: string | null;
  receiver: string | null;
  token_symbol: string;
  token_decimals: number;
  balance_units: string | null;
  native_balance_wei: string | null;
  remaining_session_budget_units: string | null;
  can_submit: boolean;
  policy_only: boolean;
  blockers: string[];
  notes: string[];
}
