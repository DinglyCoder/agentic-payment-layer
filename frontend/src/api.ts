import type { Agent, DemoPaymentInput, Health, Payment, Stats } from "./types";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`);
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}
export const api = {
  payments: () => get<Payment[]>("/api/payments"),
  agents: () => get<Agent[]>("/api/agents"),
  stats: () => get<Stats>("/api/stats"),
  health: () => get<Health>("/api/health"),
  async simulate(input: DemoPaymentInput): Promise<Payment> {
    const response = await fetch(`${API_URL}/api/demo/payments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(body?.detail ?? `Payment simulation failed (${response.status})`);
    }
    return response.json() as Promise<Payment>;
  },
};

export function openPaymentStream(
  onEvent: (payment: Payment) => void,
  onConnection: (connected: boolean) => void,
): () => void {
  const wsUrl = API_URL.replace(/^http/, "ws") + "/ws/payments";
  let socket: WebSocket | null = null;
  let retry: number | undefined;
  let closed = false;

  const connect = () => {
    socket = new WebSocket(wsUrl);
    socket.onopen = () => onConnection(true);
    socket.onmessage = (message) => {
      const data = JSON.parse(message.data) as { event: string; payment: Payment | null };
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
