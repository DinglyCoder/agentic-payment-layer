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
  status: "detected" | "scoring" | "approved" | "executed" | "recalled" | "failed";
  decision: "execute" | "recall" | null;
  risk_score: number | null;
  risk_level: "low" | "medium" | "high" | null;
  risk_reasons: string[];
  llm_score: number | null;
  source: string;
  decision_latency_ms: number | null;
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
  chain_id: number;
  contract_address: string | null;
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
