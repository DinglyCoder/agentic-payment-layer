import {
  Activity,
  ArrowRight,
  Bot,
  Check,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  Fingerprint,
  Gauge,
  LockKeyhole,
  Network,
  Radio,
  RotateCcw,
  ShieldCheck,
  ShieldX,
  Sparkles,
  WalletCards,
  Zap,
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, openPaymentStream } from "./api";
import type { Agent, DemoPaymentInput, Health, Payment, Stats } from "./types";

const EMPTY_STATS: Stats = {
  total_payments: 0,
  executed_payments: 0,
  recalled_payments: 0,
  protected_value_units: "0",
  execution_rate: 0,
  average_risk_score: 0,
};

const DEFAULT_INPUT: DemoPaymentInput = {
  sender: "0x1111111111111111111111111111111111111111",
  receiver: "0x2222222222222222222222222222222222222222",
  amount_usdc: "4.2",
  description: "GPU inference batch settlement",
};

export default function App() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [input, setInput] = useState(DEFAULT_INPUT);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStats = () => api.stats().then(setStats).catch(() => undefined);

  useEffect(() => {
    Promise.all([api.payments(), api.agents(), api.stats(), api.health()])
      .then(([paymentData, agentData, statData, healthData]) => {
        setPayments(paymentData);
        setAgents(agentData);
        setStats(statData);
        setHealth(healthData);
        setSelectedId(paymentData[0]?.payment_id ?? null);
      })
      .catch((reason: Error) => setError(reason.message));

    return openPaymentStream(
      (payment) => {
        setPayments((current) => [payment, ...current.filter((item) => item.payment_id !== payment.payment_id)]);
        setSelectedId(payment.payment_id);
        void refreshStats();
      },
      setConnected,
    );
  }, []);

  const selected = useMemo(
    () => payments.find((payment) => payment.payment_id === selectedId) ?? payments[0],
    [payments, selectedId],
  );
  const agentNames = useMemo(
    () => new Map(agents.map((agent) => [agent.address.toLowerCase(), agent.name])),
    [agents],
  );

  async function submitPayment(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const payment = await api.simulate(input);
      setPayments((current) => [payment, ...current.filter((item) => item.payment_id !== payment.payment_id)]);
      setSelectedId(payment.payment_id);
      await refreshStats();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to simulate payment");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><ShieldCheck size={24} strokeWidth={2.4} /></div>
          <div><strong>VisaTrust</strong><span>Agentic Payment Layer</span></div>
        </div>
        <div className="topbar-actions">
          <span className={`connection ${connected ? "live" : "offline"}`}>
            <Radio size={13} /> {connected ? "Live telemetry" : "Reconnecting"}
          </span>
          <span className="network-pill"><Network size={14} /> {health?.mode === "sepolia" ? "Sepolia" : "Simulation"}</span>
          <div className="avatar">VT</div>
        </div>
      </header>

      <aside className="sidebar" aria-label="Primary navigation">
        <nav>
          <a className="nav-item active" href="#overview"><Gauge size={19} /><span>Overview</span></a>
          <a className="nav-item" href="#payments"><WalletCards size={19} /><span>Payments</span></a>
          <a className="nav-item" href="#risk"><Fingerprint size={19} /><span>Risk engine</span></a>
          <a className="nav-item" href="#agents"><Bot size={19} /><span>Agent registry</span></a>
        </nav>
        <div className="sidebar-foot">
          <div className="security-icon"><LockKeyhole size={17} /></div>
          <div><strong>Non-custodial</strong><span>30s recall window</span></div>
        </div>
      </aside>

      <main>
        <section className="page-heading" id="overview">
          <div>
            <p className="eyebrow">Trust operations center</p>
            <h1>Autonomous payments,<br /><em>human-grade trust.</em></h1>
            <p className="intro">Identity, fraud intelligence, and reversible settlement for the agent economy.</p>
          </div>
          <div className="system-status">
            <div className="pulse-wrap"><span className="pulse" /></div>
            <div><span>System status</span><strong>All controls operational</strong></div>
            <Check size={18} />
          </div>
        </section>

        {error && <div className="error-banner" role="alert">{error}</div>}

        <section className="metrics" aria-label="Payment metrics">
          <Metric icon={<CircleDollarSign />} label="Protected volume" value={formatStablecoin(stats.protected_value_units, health?.stablecoin_decimals)} suffix={health?.stablecoin_symbol ?? "USDC"} trend="Escrow monitored" />
          <Metric icon={<Activity />} label="Payments screened" value={stats.total_payments.toString()} trend="Real-time decisions" />
          <Metric icon={<ShieldCheck />} label="Execution rate" value={stats.execution_rate.toFixed(1)} suffix="%" trend={`${stats.recalled_payments} recalled`} />
          <Metric icon={<Zap />} label="Average risk" value={stats.average_risk_score.toFixed(1)} suffix="/100" trend="Hybrid scoring" />
        </section>

        <section className="trust-flow" aria-label="Trust layer flow">
          <FlowNode icon={<Bot />} title="Buyer agent" detail="Authenticated wallet" />
          <div className="flow-line"><span>deposit</span><ArrowRight /></div>
          <div className="trust-core">
            <span className="core-halo" />
            <ShieldCheck size={30} />
            <div><small>VISA</small><strong>Trust Layer</strong></div>
            <span className="core-badge">Identity + risk</span>
          </div>
          <div className="flow-line"><span>resolve</span><ArrowRight /></div>
          <FlowNode icon={<Bot />} title="Seller agent" detail="Verified receiver" />
          <div className="chain-chip"><Network size={14} /> Ethereum Sepolia</div>
        </section>

        <div className="dashboard-grid">
          <section className="panel payments-panel" id="payments">
            <div className="panel-head">
              <div><p className="eyebrow">Live settlement feed</p><h2>Agent payments</h2></div>
              <span className="count-pill">{payments.length} latest</span>
            </div>
            <div className="payment-list">
              {payments.map((payment) => (
                <button
                  className={`payment-row ${selected?.payment_id === payment.payment_id ? "selected" : ""}`}
                  key={payment.payment_id}
                  onClick={() => setSelectedId(payment.payment_id)}
                >
                  <div className={`status-icon ${payment.status}`}>
                    {payment.status === "recalled" ? <RotateCcw /> : payment.status === "failed" ? <ShieldX /> : <Check />}
                  </div>
                  <div className="payment-main">
                    <strong>{payment.description}</strong>
                    <span>{agentNames.get(payment.sender) ?? shortAddress(payment.sender)} <ChevronRight size={12} /> {agentNames.get(payment.receiver) ?? shortAddress(payment.receiver)}</span>
                  </div>
                  <div className="payment-value"><strong>{formatStablecoin(payment.amount_units, health?.stablecoin_decimals)} {health?.stablecoin_symbol ?? "USDC"}</strong><span>{timeAgo(payment.deposited_at)}</span></div>
                  <RiskBadge score={payment.risk_score} level={payment.risk_level} />
                </button>
              ))}
              {!payments.length && <div className="empty-state"><Activity /><p>Waiting for the first escrow deposit</p></div>}
            </div>
          </section>

          <section className="panel risk-panel" id="risk">
            <div className="panel-head">
              <div><p className="eyebrow">Decision intelligence</p><h2>Risk analysis</h2></div>
              {selected && <span className={`decision ${selected.decision}`}>{selected.decision ?? "scoring"}</span>}
            </div>
            {selected ? (
              <>
                <div className="risk-summary">
                  <RiskGauge score={selected.risk_score ?? 0} level={selected.risk_level} />
                  <div className="risk-copy">
                    <span>Payment</span><code>{shortAddress(selected.payment_id, 8)}</code>
                    <span>Decision latency</span><strong>{selected.decision_latency_ms ?? "—"} ms</strong>
                    <span>Claude signal</span><strong>{selected.llm_score === null ? "Rules only" : `${selected.llm_score}/100`}</strong>
                  </div>
                </div>
                <div className="checks">
                  {selected.risk_reasons.map((reason) => (
                    <div className="check-row" key={reason}>
                      {selected.risk_level === "high" ? <ShieldX /> : <ShieldCheck />}
                      <span>{reason}</span>
                    </div>
                  ))}
                </div>
                <div className="deadline"><Clock3 size={15} /><span>Recall deadline</span><strong>{formatTime(selected.recall_deadline)}</strong></div>
              </>
            ) : <div className="empty-state"><Fingerprint /><p>Select a payment to inspect its risk decision</p></div>}
          </section>

          <section className="panel simulator-panel" id="agents">
            <div className="panel-head">
              <div><p className="eyebrow">Interactive demo</p><h2>Simulate payment</h2></div>
              <Sparkles size={20} />
            </div>
            <form onSubmit={submitPayment}>
              <label>Buyer agent
                <select value={input.sender} onChange={(event) => setInput({ ...input, sender: event.target.value })}>
                  {agents.map((agent) => <option value={agent.address} key={agent.address}>{agent.name} · {agent.status}</option>)}
                </select>
              </label>
              <label>Seller agent
                <select value={input.receiver} onChange={(event) => setInput({ ...input, receiver: event.target.value })}>
                  {agents.map((agent) => <option value={agent.address} key={agent.address}>{agent.name} · {agent.status}</option>)}
                </select>
              </label>
              <div className="form-split">
                <label>Amount ({health?.stablecoin_symbol ?? "USDC"})<input type="number" min="0.000001" step="0.01" value={input.amount_usdc} onChange={(event) => setInput({ ...input, amount_usdc: event.target.value })} /></label>
                <label>Service<input value={input.description} minLength={3} onChange={(event) => setInput({ ...input, description: event.target.value })} /></label>
              </div>
              <button className="primary-button" disabled={submitting || health?.mode === "sepolia"}>
                {submitting ? <><span className="spinner" /> Screening payment…</> : <><Zap size={17} /> Deposit &amp; screen</>}
              </button>
              <p className="form-note"><LockKeyhole size={13} /> Simulation uses no wallet or real funds.</p>
            </form>
          </section>
        </div>
      </main>
    </div>
  );
}

function Metric({ icon, label, value, suffix, trend }: { icon: React.ReactNode; label: string; value: string; suffix?: string; trend: string }) {
  return <article className="metric-card"><div className="metric-top"><span className="metric-icon">{icon}</span><span>{label}</span></div><div className="metric-value">{value}<small>{suffix}</small></div><p><span className="mini-dot" />{trend}</p></article>;
}

function FlowNode({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <div className="flow-node"><span>{icon}</span><div><strong>{title}</strong><small>{detail}</small></div></div>;
}

function RiskBadge({ score, level }: { score: number | null; level: Payment["risk_level"] }) {
  return <span className={`risk-badge ${level ?? "pending"}`}>{score ?? "—"}<small> risk</small></span>;
}

function RiskGauge({ score, level }: { score: number; level: Payment["risk_level"] }) {
  return <div className={`risk-gauge ${level ?? "pending"}`} style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}><div><strong>{score}</strong><span>risk score</span></div></div>;
}

function formatStablecoin(units: string, decimals = 6): string {
  const value = Number(units) / 10 ** decimals;
  return value.toLocaleString(undefined, { maximumFractionDigits: 4, minimumFractionDigits: value > 0 ? 3 : 0 });
}

function shortAddress(value: string, width = 5): string {
  return `${value.slice(0, width + 2)}…${value.slice(-4)}`;
}

function timeAgo(value: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

function formatTime(value: string): string {
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
