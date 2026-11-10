import type { ManagedDemoWallet, Payment } from "./types";

export type DemoMode = "sepolia" | "simulation";

export type DemoScenario =
  | "purchase"
  | "trusted"
  | "watchlist"
  | "budget"
  | "replay";

export interface DemoMandate {
  mandate_id: string;
  owner: string;
  delegate: string;
  token: string;
  max_amount_per_payment_units: string;
  total_budget_units: string;
  spent_units: string;
  allowed_receiver: string;
  allowed_service: string;
  expires_at: string;
  nonce: string;
  signature: string;
}

export interface DemoRun {
  scenario: DemoScenario;
  title: string;
  outcome: "completed" | "recalled" | "blocked";
  summary: string;
  simulation: boolean;
  explorer_links: Record<string, string>;
  steps: { label: string; detail: string; status: "passed" | "blocked" }[];
  payment: Payment | null;
  mandate: DemoMandate | null;
  offer: Record<string, unknown> | null;
  purchase: {
    purchase_id: string;
    status: string;
    x402_requirement: Record<string, unknown>;
    x402_payload: Record<string, unknown> | null;
    result: Record<string, unknown> | null;
  } | null;
}

export interface DemoCommandResult {
  command: string;
  exit_code: number;
  output: string[];
  run: DemoRun | null;
  operation: DemoOperation | null;
  data: Record<string, unknown> | Record<string, unknown>[] | null;
}

export interface DemoOperation {
  operation_id: string;
  mode: DemoMode;
  scenario: DemoScenario;
  status: "queued" | "running" | "completed" | "failed" | "interrupted";
  phase: string;
  error: string | null;
  payment: Payment | null;
  result: DemoRun | null;
  explorer_links: Record<string, string>;
}

export interface DemoStatus {
  testnet_available: boolean;
  managed_wallet: ManagedDemoWallet | null;
  seller_address: string | null;
  contract_address: string | null;
  chain_confirmations: number;
}
