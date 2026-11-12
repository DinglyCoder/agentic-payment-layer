import type {
  Agent,
  DemoPaymentInput,
  Health,
  IntentEnvelopeInput,
  ManagedDemoPayment,
  ManagedDemoWallet,
  Payment,
  PaymentPreviewInput,
  PaymentReview,
  Stats,
} from "./types";
import type {
  DemoCommandResult,
  DemoMode,
  DemoOperation,
  DemoScenario,
  DemoStatus,
} from "./demo-types";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}
export const api = {
  previewPayment: (input: PaymentPreviewInput) =>
    demoPost<PaymentReview | null>("/api/payments/preview", input),
  demoScenario: (
    scenario: DemoScenario,
    mode: DemoMode,
    input: { budget_units?: string; prompt?: string } = {},
  ) =>
    demoPost<DemoOperation>(`/api/demo/scenarios/${scenario}`, {
      ...input,
      mode,
      request_id: requestId(),
    }),
  demoCommand: (command: string, mode: DemoMode) =>
    demoPost<DemoCommandResult>("/api/demo/commands", {
      command,
      mode,
      request_id: requestId(),
    }),
  demoStatus: () => get<DemoStatus>("/api/demo/status"),
  demoOperation: (id: string) =>
    get<DemoOperation>(`/api/demo/operations/${id}`),
  resumeDemoOperation: (id: string) =>
    demoPost<DemoOperation>(`/api/demo/operations/${id}/resume`, {}),
  demoOperations: (mode: DemoMode) =>
    get<DemoOperation[]>(`/api/demo/operations?mode=${mode}`),
  payments: (mode?: "simulation" | "sepolia") =>
    get<Payment[]>(`/api/payments${mode ? `?mode=${mode}` : ""}`),
  agents: () => get<Agent[]>("/api/agents"),
  stats: (mode?: "simulation" | "sepolia") =>
    get<Stats>(`/api/stats${mode ? `?mode=${mode}` : ""}`),
  health: () => get<Health>("/api/health"),
  managedDemoWallet: () => get<ManagedDemoWallet>("/api/testnet/demo-wallet"),
  async payWithManagedDemoWallet(
    input: DemoPaymentInput,
  ): Promise<ManagedDemoPayment> {
    const response = await fetch(
      `${API_URL}/api/testnet/demo-wallet/payments`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          receiver: input.receiver,
          amount_usdc: input.amount_usdc,
          description: input.description,
        }),
      },
    );
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      throw new Error(
        body?.detail ?? `Demo wallet payment failed (${response.status})`,
      );
    }
    return response.json() as Promise<ManagedDemoPayment>;
  },
  async simulate(input: DemoPaymentInput): Promise<Payment> {
    const response = await fetch(`${API_URL}/api/demo/payments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      throw new Error(
        body?.detail ?? `Payment simulation failed (${response.status})`,
      );
    }
    return response.json() as Promise<Payment>;
  },
  async registerIntent(input: IntentEnvelopeInput): Promise<void> {
    const response = await fetch(`${API_URL}/api/intents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as {
        detail?: string;
      } | null;
      throw new Error(
        body?.detail ?? `Intent registration failed (${response.status})`,
      );
    }
  },
};

function requestId(): string {
  return (
    "0x" +
    Array.from(crypto.getRandomValues(new Uint8Array(32)), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("")
  );
}

export async function followDemoOperation(
  initial: DemoOperation,
  onProgress: (operation: DemoOperation) => void,
): Promise<DemoOperation> {
  let operation = initial;
  const deadline = Date.now() + 600_000;
  onProgress(operation);
  while (operation.status === "queued" || operation.status === "running") {
    if (Date.now() > deadline)
      throw new Error(
        `Operation ${operation.operation_id} is still pending. Check its chain evidence before submitting again.`,
      );
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    operation = await api.demoOperation(operation.operation_id);
    onProgress(operation);
  }
  return operation;
}

async function demoPost<T>(path: string, input: object): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Demo request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export function openPaymentStream(
  onEvent: (payment: Payment) => void,
  onConnection: (connected: boolean) => void,
): () => void {
  const wsUrl = new URL("/ws/payments", API_URL || window.location.origin);
  wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";
  let socket: WebSocket | null = null;
  let retry: number | undefined;
  let closed = false;

  const connect = () => {
    socket = new WebSocket(wsUrl);
    socket.onopen = () => onConnection(true);
    socket.onmessage = (message) => {
      const data = JSON.parse(message.data) as {
        event: string;
        payment: Payment | null;
      };
      if (data.payment) onEvent(data.payment);
    };
    socket.onclose = () => {
      onConnection(false);
      if (!closed) retry = window.setTimeout(connect, 1500);
    };
  };
  connect();

  return () => {
    closed = true;
    if (retry) window.clearTimeout(retry);
    socket?.close();
  };
}
