import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  ExternalLink,
  Fingerprint,
  Gauge,
  Landmark,
  LockKeyhole,
  Menu,
  MessageSquareText,
  Network,
  Radio,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  ShieldX,
  SlidersHorizontal,
  Sparkles,
  WalletCards,
  Wallet,
  X,
} from "lucide-react";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { api, openPaymentStream } from "./api";
import type { Agent, DemoPaymentInput, Health, Payment, Stats } from "./types";
import type { ChainDepositResult, WalletState } from "./wallet";

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

const CHAT_PRESETS = [
  { label: "Pay for an inference run", amount: "4.20", description: "GPU inference batch settlement" },
  { label: "Purchase API credits", amount: "25.00", description: "Agent API credit purchase" },
  { label: "Settle a data license", amount: "48.00", description: "Training data license settlement" },
];

type Page = "/" | "/pay" | "/dashboard" | "/agents";
type PaymentMode = "direct" | "chat";

function currentPage(): Page {
  const path = window.location.pathname.replace(/\/$/, "") || "/";
  return (["/", "/pay", "/dashboard", "/agents"] as Page[]).includes(path as Page)
    ? (path as Page)
    : "/";
}

export default function App() {
  const [page, setPage] = useState<Page>(currentPage);
  const [menuOpen, setMenuOpen] = useState(false);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [health, setHealth] = useState<Health | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onPopState = () => setPage(currentPage());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

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
        void api.stats().then(setStats).catch(() => undefined);
      },
      setConnected,
    );
  }, []);

  function navigate(next: Page) {
    window.history.pushState({}, "", next);
    setPage(next);
    setMenuOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function handlePayment(payment: Payment) {
    setPayments((current) => [payment, ...current.filter((item) => item.payment_id !== payment.payment_id)]);
    setSelectedId(payment.payment_id);
    void api.stats().then(setStats).catch(() => undefined);
  }

  const selected = useMemo(
    () => payments.find((payment) => payment.payment_id === selectedId) ?? payments[0],
    [payments, selectedId],
  );
  const agentNames = useMemo(
    () => new Map(agents.map((agent) => [agent.address.toLowerCase(), agent.name])),
    [agents],
  );

  return (
    <div className="site-shell">
      <Header page={page} connected={connected} health={health} menuOpen={menuOpen} onMenu={() => setMenuOpen((open) => !open)} navigate={navigate} />
      {error && page !== "/" && <div className="global-error" role="alert">Live data unavailable: {error}</div>}
      {page === "/" && <LandingPage stats={stats} health={health} navigate={navigate} />}
      {page === "/pay" && <PayPage agents={agents} health={health} onPayment={handlePayment} navigate={navigate} />}
      {page === "/dashboard" && <DashboardPage payments={payments} stats={stats} health={health} selected={selected} selectedId={selectedId} agentNames={agentNames} setSelectedId={setSelectedId} />}
      {page === "/agents" && <AgentsPage agents={agents} payments={payments} health={health} navigate={navigate} />}
      <Footer navigate={navigate} />
    </div>
  );
}

function Header({ page, connected, health, menuOpen, onMenu, navigate }: { page: Page; connected: boolean; health: Health | null; menuOpen: boolean; onMenu: () => void; navigate: (page: Page) => void }) {
  const links: { path: Page; label: string }[] = [
    { path: "/", label: "Product" },
    { path: "/pay", label: "Pay" },
    { path: "/dashboard", label: "Payments" },
    { path: "/agents", label: "Agents" },
  ];
  return (
    <header className="site-header">
      <button className="wordmark" onClick={() => navigate("/")} aria-label="Paradime home"><span className="wordmark-icon"><ShieldCheck size={20} /></span><span>Paradime</span></button>
      <nav className={menuOpen ? "open" : ""} aria-label="Primary navigation">
        {links.map((link) => <button className={page === link.path ? "active" : ""} onClick={() => navigate(link.path)} key={link.path}>{link.label}</button>)}
      </nav>
      <div className="header-actions">
        <span className={`live-state ${connected ? "connected" : ""}`}><span /> {connected ? (health?.mode === "sepolia" ? "Sepolia live" : "Simulation live") : health ? "Reconnecting" : "Demo"}</span>
        <button className="header-cta" onClick={() => navigate("/pay")}>Make a payment <ArrowUpRight size={15} /></button>
        <button className="menu-button" onClick={onMenu} aria-label="Toggle navigation">{menuOpen ? <X /> : <Menu />}</button>
      </div>
    </header>
  );
}

function LandingPage({ stats, health, navigate }: { stats: Stats; health: Health | null; navigate: (page: Page) => void }) {
  return (
    <main className="landing-page">
      <section className="hero section-wrap">
        <div className="hero-copy">
          <p className="kicker"><span /> Infrastructure for autonomous commerce</p>
          <h1>Payments agents can make.<br /><em>Trust people can verify.</em></h1>
          <p className="hero-intro">Identity, real-time risk controls, and reversible stablecoin settlement—built for software that transacts on its own.</p>
          <div className="hero-actions"><button className="button button-dark" onClick={() => navigate("/pay")}>Try a payment <ArrowRight size={17} /></button><button className="text-link" onClick={() => navigate("/dashboard")}>Explore the dashboard <ArrowUpRight size={15} /></button></div>
          <div className="hero-proof"><div><strong>30 sec</strong><span>recall window</span></div><div><strong>{stats.total_payments || "Live"}</strong><span>payments screened</span></div><div><strong>{health?.stablecoin_symbol ?? "USDC"}</strong><span>stablecoin settlement</span></div></div>
        </div>
        <div className="hero-visual" aria-label="A protected agent payment in progress">
          <div className="visual-topline"><span>Payment protection</span><span className="status-clean"><span /> Screening</span></div>
          <div className="visual-payment"><div><small>Amount</small><strong>4.20 <span>USDC</span></strong></div><span className="token-mark">$</span></div>
          <div className="agent-route"><div className="route-agent"><Bot /><span><strong>Procurement agent</strong><small>Verified · 0x11…1111</small></span></div><div className="route-line"><span /></div><div className="route-agent"><Landmark /><span><strong>Compute provider</strong><small>Verified · 0x22…2222</small></span></div></div>
          <div className="risk-strip"><span><ShieldCheck /> Risk controls passed</span><strong>12 <small>/ 100</small></strong></div>
          <div className="visual-foot"><LockKeyhole /> Funds remain reversible during screening</div>
          <div className="float-card float-card-one"><Fingerprint /><span><small>Identity</small><strong>Verified</strong></span><Check /></div>
          <div className="float-card float-card-two"><Activity /><span><small>Decision</small><strong>Approve</strong></span><ArrowRight /></div>
        </div>
      </section>
      <section className="confidence-bar"><div className="section-wrap confidence-inner"><span>Designed around verifiable controls</span><div><LockKeyhole /> Non-custodial</div><div><Network /> Sepolia-native</div><div><RotateCcw /> Reversible</div><div><Radio /> Real-time</div></div></section>
      <section className="section-wrap product-section">
        <div className="section-heading split-heading"><div><p className="kicker">The trust layer</p><h2>Stablecoin rails need<br />payment-grade controls.</h2></div><p>Paradime sits between autonomous agents and settlement, evaluating who is transacting, what looks unusual, and whether funds should move.</p></div>
        <div className="capability-grid">
          <article><span className="capability-number">01</span><Fingerprint /><h3>Know the agent</h3><p>Registry status and wallet identity establish who is behind each side of a transaction.</p><span className="article-link">Identity verification <ArrowRight /></span></article>
          <article><span className="capability-number">02</span><Activity /><h3>Assess the intent</h3><p>Amount, velocity, reputation, and bounded machine analysis create a clear risk decision.</p><span className="article-link">Risk intelligence <ArrowRight /></span></article>
          <article><span className="capability-number">03</span><RotateCcw /><h3>Keep a way back</h3><p>A short escrow window allows suspicious payments to be recalled before final settlement.</p><span className="article-link">Reversible settlement <ArrowRight /></span></article>
        </div>
      </section>
      <section className="how-section"><div className="section-wrap"><div className="section-heading centered"><p className="kicker">How it works</p><h2>One transaction. Three control points.</h2><p>Every payment follows the same observable path from intent to settlement.</p></div><div className="steps-line"><article><span>1</span><div className="step-icon"><WalletCards /></div><h3>Deposit</h3><p>An agent deposits ERC-20 funds into the escrow with a payment identifier.</p></article><article><span>2</span><div className="step-icon"><Gauge /></div><h3>Screen</h3><p>Paradime scores identity, value, and behavioral signals during the recall window.</p></article><article><span>3</span><div className="step-icon"><ShieldCheck /></div><h3>Resolve</h3><p>Approved funds settle to the receiver. Flagged funds return to the sender.</p></article></div></div></section>
      <section className="section-wrap closing-cta"><div><p className="kicker light">Run the payment flow</p><h2>See trust decisions<br />as they happen.</h2></div><button className="button button-light" onClick={() => navigate("/pay")}>Open payment console <ArrowRight /></button></section>
    </main>
  );
}

function PayPage({ agents, health, onPayment, navigate }: { agents: Agent[]; health: Health | null; onPayment: (payment: Payment) => void; navigate: (page: Page) => void }) {
  const [mode, setMode] = useState<PaymentMode>("direct");
  const [input, setInput] = useState(DEFAULT_INPUT);
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [created, setCreated] = useState<Payment | null>(null);
  const [chainSubmission, setChainSubmission] = useState<ChainDepositResult | null>(null);
  const [wallet, setWallet] = useState<WalletState | null>(null);
  const [chainStage, setChainStage] = useState<"approval" | "deposit" | null>(null);
  const [chatStep, setChatStep] = useState(0);

  useEffect(() => {
    if (health?.mode === "sepolia") {
      setInput((current) => ({ ...current, receiver: current.receiver === DEFAULT_INPUT.receiver ? "" : current.receiver }));
      return;
    }
    if (agents.length < 2) return;
    setInput((current) => ({ ...current, sender: agents.some((agent) => agent.address === current.sender) ? current.sender : agents[0].address, receiver: agents.some((agent) => agent.address === current.receiver) ? current.receiver : agents[1].address }));
  }, [agents, health?.mode]);

  async function connectWallet() {
    if (!health) return;
    setLocalError(null);
    try {
      const { connectSepoliaWallet } = await import("./wallet");
      const next = await connectSepoliaWallet(health);
      setWallet(next);
      setInput((current) => ({ ...current, sender: next.address }));
    } catch (reason) {
      setLocalError(reason instanceof Error ? reason.message : "Unable to connect wallet");
    }
  }

  async function createPayment(paymentInput: DemoPaymentInput) {
    setSubmitting(true);
    setLocalError(null);
    try {
      if (health?.mode === "sepolia") {
        if (!wallet) throw new Error("Connect a Sepolia wallet before submitting a payment");
        const { depositSepoliaUsdc } = await import("./wallet");
        const submission = await depositSepoliaUsdc(paymentInput, health, setChainStage);
        setChainSubmission(submission);
      } else {
        const payment = await api.simulate(paymentInput);
        setCreated(payment);
        onPayment(payment);
      }
    } catch (reason) {
      setLocalError(reason instanceof Error ? reason.message : "Unable to create payment");
    } finally {
      setSubmitting(false);
      setChainStage(null);
    }
  }

  function submitDirect(event: FormEvent) { event.preventDefault(); void createPayment(input); }
  function selectPreset(preset: (typeof CHAT_PRESETS)[number]) { setInput((current) => ({ ...current, amount_usdc: preset.amount, description: preset.description })); setChatStep(1); }

  return (
    <main className="inner-page pay-page">
      <section className="inner-hero section-wrap compact"><p className="kicker">Payment console</p><h1>Move funds with a safety net.</h1><p>Choose a standard transfer or use the guided assistant to compose an agent payment.</p></section>
      <section className="section-wrap pay-layout">
        <div className="payment-workspace">
          <div className="mode-switch" role="tablist" aria-label="Payment method"><button className={mode === "direct" ? "active" : ""} onClick={() => setMode("direct")}><WalletCards /> Direct payment</button><button className={mode === "chat" ? "active" : ""} onClick={() => setMode("chat")}><MessageSquareText /> Guided chat <span>New</span></button></div>
          {chainSubmission ? <ChainPaymentSuccess submission={chainSubmission} health={health} onAgain={() => { setChainSubmission(null); setChatStep(0); }} navigate={navigate} /> : created ? <PaymentSuccess payment={created} health={health} onAgain={() => { setCreated(null); setChatStep(0); }} navigate={navigate} /> : mode === "direct" ? <DirectPaymentForm agents={agents} health={health} input={input} setInput={setInput} wallet={wallet} chainStage={chainStage} onConnect={() => void connectWallet()} submitting={submitting} error={localError} onSubmit={submitDirect} /> : <ChatPayment agents={agents} health={health} input={input} setInput={setInput} wallet={wallet} chainStage={chainStage} onConnect={() => void connectWallet()} step={chatStep} setStep={setChatStep} submitting={submitting} error={localError} onPreset={selectPreset} onCreate={() => void createPayment(input)} />}
        </div>
        <aside className="payment-aside"><p className="kicker">Protected by default</p><h2>Every payment is screened before settlement.</h2><div className="aside-timeline"><div><span><Check /></span><p><strong>Agent identities checked</strong><small>Sender and receiver are matched against the registry.</small></p></div><div><span><Activity /></span><p><strong>Risk assessed in real time</strong><small>Value, velocity, and behavioral signals are evaluated.</small></p></div><div><span><Clock3 /></span><p><strong>30-second recall window</strong><small>Suspicious transfers can return before final settlement.</small></p></div></div>{health?.mode === "sepolia" ? <div className="chain-note"><Network /><p><strong>Ethereum Sepolia</strong><span>Real test USDC, real wallet signatures, and publicly verifiable transactions.</span></p>{health.contract_address && <ExplorerLink kind="address" value={health.contract_address} label="View escrow" />}</div> : <div className="simulation-note"><LockKeyhole /><p><strong>Safe demonstration</strong><span>This environment uses simulated funds. No wallet is required.</span></p></div>}</aside>
      </section>
    </main>
  );
}

function DirectPaymentForm({ agents, health, input, setInput, wallet, chainStage, onConnect, submitting, error, onSubmit }: { agents: Agent[]; health: Health | null; input: DemoPaymentInput; setInput: (input: DemoPaymentInput) => void; wallet: WalletState | null; chainStage: "approval" | "deposit" | null; onConnect: () => void; submitting: boolean; error: string | null; onSubmit: (event: FormEvent) => void }) {
  const onChain = health?.mode === "sepolia";
  const submitLabel = chainStage === "approval" ? "Approve USDC in wallet…" : chainStage === "deposit" ? "Confirm escrow deposit…" : onChain ? "Approve & deposit" : "Review and pay";
  return (
    <form className="direct-form" onSubmit={onSubmit}>
      <div className="form-title"><div><h2>New payment</h2><p>Enter the parties and settlement details.</p></div><span className="environment"><span /> {health?.mode === "sepolia" ? "Sepolia" : "Simulation"}</span></div>
      {error && <div className="form-error">{error}</div>}
      {onChain && <div className="wallet-row">{wallet ? <><span className="wallet-status"><Wallet /><span><small>Connected Sepolia wallet</small><strong>{shortAddress(wallet.address, 8)}</strong></span></span><span className="wallet-balance"><small>Test USDC balance</small><strong>{formatStablecoin(wallet.balanceUnits, health.stablecoin_decimals)} {health.stablecoin_symbol}</strong></span></> : <><span><Wallet /><span><strong>Connect your payment wallet</strong><small>MetaMask or another EIP-1193 wallet</small></span></span><button type="button" onClick={onConnect}>Connect wallet</button></>}</div>}
      <div className="field-grid">{onChain ? <label>Paying wallet<input value={wallet?.address ?? "Not connected"} readOnly /></label> : <label>Paying agent<select value={input.sender} onChange={(event) => setInput({ ...input, sender: event.target.value })}>{agents.map((agent) => <option value={agent.address} key={agent.address}>{agent.name} · {agent.status}</option>)}</select></label>}<span className="field-arrow"><ArrowRight /></span>{onChain ? <label>Receiving wallet<input required pattern="^0x[a-fA-F0-9]{40}$" value={input.receiver} onChange={(event) => setInput({ ...input, receiver: event.target.value })} placeholder="0x… recipient wallet" /></label> : <label>Receiving agent<select value={input.receiver} onChange={(event) => setInput({ ...input, receiver: event.target.value })}>{agents.map((agent) => <option value={agent.address} key={agent.address}>{agent.name} · {agent.status}</option>)}</select></label>}</div>
      <label>Amount<div className="amount-input"><input type="number" min="0.000001" step="0.000001" value={input.amount_usdc} onChange={(event) => setInput({ ...input, amount_usdc: event.target.value })} /><span>{health?.stablecoin_symbol ?? "USDC"}<ChevronDown /></span></div></label>
      <label>Payment memo<input value={input.description} minLength={3} maxLength={120} onChange={(event) => setInput({ ...input, description: event.target.value })} placeholder="What is this payment for?" /></label>
      <div className="payment-summary"><span>Network</span><strong>{onChain ? "Ethereum Sepolia" : "Simulation"}</strong><span>Recipient receives</span><strong>{input.amount_usdc || "0.00"} {health?.stablecoin_symbol ?? "USDC"}</strong></div>
      <button className="button button-dark submit-payment" disabled={submitting || (onChain && !wallet)}>{submitting ? <><span className="spinner" /> {submitLabel}</> : <>{submitLabel} <ArrowRight /></>}</button>
      <p className="secure-copy"><LockKeyhole /> Payment details are screened and stored with the decision record.</p>
    </form>
  );
}

function ChatPayment({ agents, health, input, setInput, wallet, chainStage, onConnect, step, setStep, submitting, error, onPreset, onCreate }: { agents: Agent[]; health: Health | null; input: DemoPaymentInput; setInput: (input: DemoPaymentInput) => void; wallet: WalletState | null; chainStage: "approval" | "deposit" | null; onConnect: () => void; step: number; setStep: (step: number) => void; submitting: boolean; error: string | null; onPreset: (preset: (typeof CHAT_PRESETS)[number]) => void; onCreate: () => void }) {
  const onChain = health?.mode === "sepolia";
  const senderName = wallet ? shortAddress(wallet.address, 7) : agents.find((agent) => agent.address === input.sender)?.name ?? "Buyer agent";
  const receiverName = agents.find((agent) => agent.address === input.receiver)?.name ?? "Receiver agent";
  return (
    <section className="chat-shell">
      <div className="chat-head"><div className="assistant-mark"><ShieldCheck /></div><div><strong>Payment assistant</strong><span><i /> {onChain ? "Sepolia on-chain mode" : "Ready to compose"}</span></div>{onChain && !wallet ? <button className="chat-connect" onClick={onConnect}><Wallet /> Connect</button> : <button aria-label="Reset chat" onClick={() => setStep(0)}><RotateCcw /></button>}</div>
      <div className="chat-thread"><div className="chat-day">Today</div>{onChain && !wallet && <ChatBubble assistant>Connect a Sepolia wallet first. You’ll sign a test USDC approval and the escrow deposit in your wallet.</ChatBubble>}<ChatBubble assistant>What would you like to pay for?</ChatBubble>{step === 0 && <div className="prompt-options">{CHAT_PRESETS.map((preset) => <button onClick={() => onPreset(preset)} key={preset.label}>{preset.label}<ArrowUpRight /></button>)}</div>}{step >= 1 && <><ChatBubble>{input.description}</ChatBubble><ChatBubble assistant>I can prepare that. Who should receive the payment?</ChatBubble></>}{step === 1 && (onChain ? <form className="chat-address-entry" onSubmit={(event) => { event.preventDefault(); if (/^0x[a-fA-F0-9]{40}$/.test(input.receiver)) setStep(2); }}><input required pattern="^0x[a-fA-F0-9]{40}$" value={input.receiver} onChange={(event) => setInput({ ...input, receiver: event.target.value })} placeholder="Paste the recipient's Sepolia wallet" /><button>Use wallet <ArrowRight /></button></form> : <div className="prompt-options compact-options">{agents.filter((agent) => agent.address !== input.sender).map((agent) => <button key={agent.address} onClick={() => { setInput({ ...input, receiver: agent.address }); setStep(2); }}><span><strong>{agent.name}</strong><small>{agent.status} · trust {agent.trust_score}</small></span><ChevronRight /></button>)}</div>)}{step >= 2 && <><ChatBubble>{onChain ? shortAddress(input.receiver, 8) : receiverName}</ChatBubble><ChatBubble assistant>Here’s the payment I’ve prepared. Review the details before screening begins.</ChatBubble><div className="chat-payment-card"><div><span>From</span><strong>{senderName}</strong></div><ArrowRight /><div><span>To</span><strong>{onChain ? shortAddress(input.receiver, 7) : receiverName}</strong></div><div className="chat-amount"><span>Total</span><strong>{input.amount_usdc} {health?.stablecoin_symbol ?? "USDC"}</strong></div><button className="button button-dark" disabled={submitting || (onChain && !wallet)} onClick={onCreate}>{submitting ? (chainStage === "approval" ? "Approve in wallet…" : "Deposit in wallet…") : onChain ? "Sign & deposit" : "Confirm payment"}</button></div></>}{error && <div className="form-error">{error}</div>}</div>
      <div className="chat-composer"><button><Sparkles /></button><span>{step < 2 ? "Choose a response above to continue" : "Payment ready for confirmation"}</span><button className="send-button" disabled><Send /></button></div><p className="chat-disclaimer">{onChain ? "Real Sepolia transaction · Test tokens have no financial value" : "Guided simulation · No autonomous instructions are executed"}</p>
    </section>
  );
}

function ChatBubble({ children, assistant = false }: { children: ReactNode; assistant?: boolean }) { return <div className={`chat-row ${assistant ? "assistant" : "user"}`}>{assistant && <span className="bubble-mark"><ShieldCheck /></span>}<div className="chat-bubble">{children}</div></div>; }

function PaymentSuccess({ payment, health, onAgain, navigate }: { payment: Payment; health: Health | null; onAgain: () => void; navigate: (page: Page) => void }) {
  return <div className="payment-success"><div className="success-mark"><Check /></div><p className="kicker">Payment submitted</p><h2>{formatStablecoin(payment.amount_units, health?.stablecoin_decimals)} {health?.stablecoin_symbol ?? "USDC"}</h2><p>Your payment entered the trust window and received an initial risk score of <strong>{payment.risk_score ?? "—"}</strong>.</p><div className="success-detail"><span>Payment ID</span><code>{shortAddress(payment.payment_id, 9)}</code><span>Status</span><strong className={`status-text ${payment.status}`}>{payment.status}</strong><span>Decision</span><strong>{payment.decision ?? "Pending"}</strong></div><div className="success-actions"><button className="button button-dark" onClick={() => navigate("/dashboard")}>View in dashboard <ArrowRight /></button><button className="button button-outline" onClick={onAgain}>Make another</button></div></div>;
}

function ChainPaymentSuccess({ submission, health, onAgain, navigate }: { submission: ChainDepositResult; health: Health | null; onAgain: () => void; navigate: (page: Page) => void }) {
  return <div className="payment-success chain-success"><div className="success-mark"><Check /></div><p className="kicker">Confirmed on Ethereum Sepolia</p><h2>{formatStablecoin(submission.amountUnits, health?.stablecoin_decimals)} {health?.stablecoin_symbol ?? "USDC"}</h2><p>The test USDC deposit is inside the escrow. Paradime will ingest it after the configured confirmation depth and publish the risk decision.</p><div className="success-detail"><span>Payment ID</span><code>{shortAddress(submission.paymentId, 9)}</code><span>Deposit transaction</span><ExplorerLink kind="tx" value={submission.depositTxHash} label={shortAddress(submission.depositTxHash, 8)} />{submission.approvalTxHash && <><span>USDC approval</span><ExplorerLink kind="tx" value={submission.approvalTxHash} label={shortAddress(submission.approvalTxHash, 8)} /></>}<span>Escrow contract</span>{health?.contract_address ? <ExplorerLink kind="address" value={health.contract_address} label={shortAddress(health.contract_address, 8)} /> : <strong>Unavailable</strong>}</div><div className="proof-seal"><ShieldCheck /><span><strong>Publicly verifiable</strong><small>Transaction receipt confirmed by Ethereum Sepolia</small></span></div><div className="success-actions"><button className="button button-dark" onClick={() => navigate("/dashboard")}>Watch in dashboard <ArrowRight /></button><button className="button button-outline" onClick={onAgain}>Make another</button></div></div>;
}

function ExplorerLink({ kind, value, label }: { kind: "tx" | "address" | "block"; value: string | number; label: string }) {
  return <a className="explorer-link" href={`https://sepolia.etherscan.io/${kind}/${value}`} target="_blank" rel="noreferrer">{label}<ExternalLink /></a>;
}

function DashboardPage({ payments, stats, health, selected, selectedId, agentNames, setSelectedId }: { payments: Payment[]; stats: Stats; health: Health | null; selected: Payment | undefined; selectedId: string | null; agentNames: Map<string, string>; setSelectedId: (id: string) => void }) {
  const riskCounts = useMemo(() => ({ low: payments.filter((payment) => payment.risk_level === "low").length, medium: payments.filter((payment) => payment.risk_level === "medium").length, high: payments.filter((payment) => payment.risk_level === "high").length }), [payments]);
  const activity = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - (6 - index));
      const next = new Date(date);
      next.setDate(date.getDate() + 1);
      return {
        label: date.toLocaleDateString(undefined, { weekday: "short" }),
        count: payments.filter((payment) => {
          const deposited = new Date(payment.deposited_at);
          return deposited >= date && deposited < next;
        }).length,
      };
    });
    const maximum = Math.max(1, ...days.map((day) => day.count));
    const points = days.map((day, index) => ({ x: index * (620 / 6), y: 170 - (day.count / maximum) * 145 }));
    const line = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
    return { days, maximum, line, area: `${line} L620 190 L0 190 Z`, last: points[points.length - 1] };
  }, [payments]);
  const maxRiskCount = Math.max(1, riskCounts.low, riskCounts.medium, riskCounts.high);
  return (
    <main className="inner-page dashboard-page">
      <section className="dashboard-head section-wrap compact"><div><p className="kicker">Trust operations</p><h1>Payments dashboard</h1><p>Monitor settlement activity and investigate risk decisions.</p></div><div className="dashboard-controls"><button><SlidersHorizontal /> Filters</button><span className="last-updated"><Radio /> Live updates</span></div></section>
      <section className="section-wrap dashboard-content">
        {health?.mode === "sepolia" ? <div className="chain-verification-strip"><div className="chain-verified-mark"><Check /></div><div><strong>Live on Ethereum Sepolia</strong><span>Payment records below are ingested from the deployed escrow contract.</span></div><div className="chain-contract-links">{health.contract_address && <ExplorerLink kind="address" value={health.contract_address} label={`Escrow ${shortAddress(health.contract_address, 6)}`} />}{health.payment_token_address && <ExplorerLink kind="address" value={health.payment_token_address} label={`Test USDC ${shortAddress(health.payment_token_address, 6)}`} />}</div></div> : <div className="simulation-strip"><LockKeyhole /><span><strong>Simulation workspace</strong> These records are generated locally and are not on Etherscan. Switch the backend to Sepolia mode for publicly verifiable proof.</span></div>}
        <div className="metrics-row"><MetricCard icon={<CircleDollarSign />} label="Protected volume" value={formatStablecoin(stats.protected_value_units, health?.stablecoin_decimals)} suffix={health?.stablecoin_symbol ?? "USDC"} note="Across all screened payments" /><MetricCard icon={<Activity />} label="Payments screened" value={stats.total_payments.toString()} note={`${stats.executed_payments} successfully settled`} /><MetricCard icon={<ShieldCheck />} label="Execution rate" value={stats.execution_rate.toFixed(1)} suffix="%" note={`${stats.recalled_payments} recalled by controls`} /><MetricCard icon={<Gauge />} label="Average risk" value={stats.average_risk_score.toFixed(1)} suffix="/100" note="Rules + decision intelligence" /></div>
        <div className="analytics-grid">
          <section className="dash-panel volume-chart-panel"><div className="panel-title"><div><p className="kicker">Activity</p><h2>Payment volume</h2></div><button>Last 7 days <ChevronDown /></button></div><div className="volume-chart"><div className="chart-y"><span>{activity.maximum}</span><span>{Math.round(activity.maximum * .67)}</span><span>{Math.round(activity.maximum * .33)}</span><span>0</span></div><svg viewBox="0 0 620 190" preserveAspectRatio="none" role="img" aria-label="Payment volume trend"><defs><linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1c4b40" stopOpacity=".18"/><stop offset="1" stopColor="#1c4b40" stopOpacity="0"/></linearGradient></defs><path className="chart-grid" d="M0 20H620 M0 70H620 M0 120H620 M0 170H620" /><path className="chart-area" d={activity.area} /><path className="chart-line" d={activity.line} /><circle cx={activity.last.x} cy={activity.last.y} r="5" /></svg><div className="chart-x">{activity.days.map((day) => <span key={day.label}>{day.label}</span>)}</div></div></section>
          <section className="dash-panel distribution-panel"><div className="panel-title"><div><p className="kicker">Risk posture</p><h2>Risk distribution</h2></div><span className="clean-badge"><ShieldCheck /> Stable</span></div><div className="risk-bars">{(["low", "medium", "high"] as const).map((level) => <div className={`risk-bar-row ${level}`} key={level}><span>{level}</span><div><i style={{ width: `${Math.max(4, (riskCounts[level] / maxRiskCount) * 100)}%` }} /></div><strong>{riskCounts[level]}</strong></div>)}</div><div className="risk-average"><span>Average score</span><strong>{stats.average_risk_score.toFixed(1)}</strong><div><i style={{ width: `${stats.average_risk_score}%` }} /></div><small>0 — lower risk <b>100 — higher risk</b></small></div></section>
        </div>
        <div className="payments-layout"><section className="dash-panel payment-table-panel"><div className="panel-title"><div><p className="kicker">Settlement feed</p><h2>Recent payments</h2></div><div className="table-tools"><button><Search /></button><span>{payments.length} records</span></div></div><div className="table-wrap"><table><thead><tr><th>Payment</th><th>Parties</th><th>Amount</th><th>Status</th><th>Risk</th><th>Proof</th></tr></thead><tbody>{payments.map((payment) => <tr className={selectedId === payment.payment_id ? "selected" : ""} onClick={() => setSelectedId(payment.payment_id)} key={payment.payment_id}><td><div className={`table-payment-icon ${payment.status}`}>{payment.status === "recalled" ? <RotateCcw /> : <ArrowUpRight />}</div><span><strong>{payment.description}</strong><small>{timeAgo(payment.deposited_at)}</small></span></td><td><span className="party-cell"><strong>{agentNames.get(payment.sender) ?? shortAddress(payment.sender)}</strong><small>to {agentNames.get(payment.receiver) ?? shortAddress(payment.receiver)}</small></span></td><td><strong>{formatStablecoin(payment.amount_units, health?.stablecoin_decimals)}</strong><small>{health?.stablecoin_symbol ?? "USDC"}</small></td><td><StatusPill status={payment.status} /></td><td><RiskBadge score={payment.risk_score} level={payment.risk_level} /></td><td>{payment.source === "sepolia" ? <span onClick={(event) => event.stopPropagation()}><ExplorerLink kind="tx" value={payment.deposit_tx_hash} label="Etherscan" /></span> : <span className="simulation-label">Simulated</span>}</td></tr>)}</tbody></table>{!payments.length && <div className="empty-state"><Activity /><p>Waiting for the first escrow deposit</p></div>}</div></section><RiskDetail payment={selected} health={health} /></div>
      </section>
    </main>
  );
}

function RiskDetail({ payment, health }: { payment: Payment | undefined; health: Health | null }) {
  if (!payment) return <aside className="dash-panel risk-detail"><div className="empty-state"><Fingerprint /><p>Select a payment to inspect its risk decision</p></div></aside>;
  const factors = [{ label: "Identity", value: payment.risk_level === "high" ? 74 : 12 }, { label: "Amount", value: Math.min(100, Math.max(8, Number(payment.risk_score ?? 0) * 0.7)) }, { label: "Velocity", value: Math.min(100, Math.max(5, Number(payment.risk_score ?? 0) * 1.1)) }];
  return <aside className="dash-panel risk-detail"><div className="panel-title"><div><p className="kicker">Selected payment</p><h2>Risk analysis</h2></div><span className={`decision-pill ${payment.decision ?? "pending"}`}>{payment.decision ?? "scoring"}</span></div><div className="risk-hero"><RiskGauge score={payment.risk_score ?? 0} level={payment.risk_level} /><div><span>Payment ID</span><code>{shortAddress(payment.payment_id, 7)}</code><span>Decision latency</span><strong>{payment.decision_latency_ms ?? "—"} ms</strong></div></div><div className="factor-list"><h3>Signal contribution</h3>{factors.map((factor) => <div key={factor.label}><span>{factor.label}</span><div><i style={{ width: `${factor.value}%` }} /></div><strong>{Math.round(factor.value)}</strong></div>)}</div><div className="reason-list"><h3>Decision notes</h3>{payment.risk_reasons.length ? payment.risk_reasons.map((reason) => <p key={reason}>{payment.risk_level === "high" ? <ShieldX /> : <CheckCircle2 />}{reason}</p>) : <p><CheckCircle2 /> No elevated risk signals detected</p>}</div>{payment.source === "sepolia" ? <div className="onchain-proof"><div className="proof-title"><ShieldCheck /><span><strong>Verified on Sepolia</strong><small>Public blockchain evidence</small></span></div><ExplorerLink kind="tx" value={payment.deposit_tx_hash} label="Deposit transaction" />{payment.resolution_tx_hash && <ExplorerLink kind="tx" value={payment.resolution_tx_hash} label="Resolution transaction" />}<ExplorerLink kind="address" value={payment.sender} label={`Sender ${shortAddress(payment.sender)}`} /><ExplorerLink kind="address" value={payment.receiver} label={`Receiver ${shortAddress(payment.receiver)}`} />{health?.contract_address && <ExplorerLink kind="address" value={health.contract_address} label={`Escrow ${shortAddress(health.contract_address)}`} />}{payment.block_number !== null && <ExplorerLink kind="block" value={payment.block_number} label={`Block ${payment.block_number}`} />}</div> : <div className="local-proof"><LockKeyhole /><span><strong>Simulation record</strong><small>No on-chain transaction was created.</small></span></div>}<div className="deadline-row"><Clock3 /><span>Recall deadline</span><strong>{formatTime(payment.recall_deadline)}</strong></div></aside>;
}

function AgentsPage({ agents, payments, health, navigate }: { agents: Agent[]; payments: Payment[]; health: Health | null; navigate: (page: Page) => void }) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | Agent["status"]>("all");
  const visibleAgents = agents.filter((agent) => (filter === "all" || agent.status === filter) && `${agent.name} ${agent.address}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <main className="inner-page agents-page">
      <section className="agents-hero"><div className="section-wrap compact"><div><p className="kicker light">Verified network</p><h1>Agent repository</h1><p>Discover registered agents and review the trust signals behind every counterparty.</p></div><div className="repository-stat"><strong>{agents.length}</strong><span>registered agents</span></div></div></section>
      <section className="section-wrap repository-content"><div className="repository-toolbar"><div className="search-box"><Search /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search name or wallet address" /></div><div className="filter-tabs">{(["all", "verified", "watchlist", "unknown"] as const).map((status) => <button className={filter === status ? "active" : ""} onClick={() => setFilter(status)} key={status}>{status}</button>)}</div></div><div className="repository-summary"><span>Showing <strong>{visibleAgents.length}</strong> of {agents.length} agents</span><span><ShieldCheck /> Registry synchronized</span></div><div className="agent-grid">{visibleAgents.map((agent, index) => { const sent = payments.filter((payment) => payment.sender.toLowerCase() === agent.address.toLowerCase()).length; const received = payments.filter((payment) => payment.receiver.toLowerCase() === agent.address.toLowerCase()).length; return <article className="agent-card" key={agent.address}><div className="agent-card-top"><div className={`agent-avatar avatar-${index % 4}`}><Bot /></div><StatusPill status={agent.status} /></div><h2>{agent.name}</h2>{health?.mode === "sepolia" ? <ExplorerLink kind="address" value={agent.address} label={shortAddress(agent.address, 8)} /> : <code>{shortAddress(agent.address, 8)}</code>}<div className="trust-score"><div><span>Trust score</span><strong>{agent.trust_score}<small>/100</small></strong></div><div className="trust-track"><i style={{ width: `${agent.trust_score}%` }} /></div></div><div className="agent-stats"><div><strong>{sent}</strong><span>Sent</span></div><div><strong>{received}</strong><span>Received</span></div><div><strong>{sent + received}</strong><span>Total</span></div></div><button onClick={() => navigate("/pay")}>Pay this agent <ArrowRight /></button></article>; })}</div>{!visibleAgents.length && <div className="empty-state repository-empty"><Search /><p>No agents match that search.</p></div>}<div className="repository-callout"><div><Fingerprint /><span><strong>Registry-backed identity</strong><p>Every status is evaluated alongside transaction behavior. Unknown or watchlisted agents receive higher deterministic risk floors.</p></span></div><button className="button button-outline" onClick={() => navigate("/dashboard")}>View risk operations</button></div></section>
    </main>
  );
}

function Footer({ navigate }: { navigate: (page: Page) => void }) { return <footer className="site-footer"><div className="section-wrap"><div className="wordmark footer-mark"><span className="wordmark-icon"><ShieldCheck size={18} /></span><span>Paradime</span></div><p>Independent trust infrastructure for reversible agent payments.</p><nav><button onClick={() => navigate("/")}>Product</button><button onClick={() => navigate("/dashboard")}>Dashboard</button><button onClick={() => navigate("/agents")}>Agents</button></nav></div></footer>; }
function MetricCard({ icon, label, value, suffix, note }: { icon: ReactNode; label: string; value: string; suffix?: string; note: string }) { return <article className="metric-card"><div className="metric-head"><span>{icon}</span><p>{label}</p><ArrowUpRight /></div><div className="metric-value">{value}<small>{suffix}</small></div><p className="metric-note"><i />{note}</p></article>; }
function StatusPill({ status }: { status: string }) { return <span className={`status-pill ${status}`}><i />{status}</span>; }
function RiskBadge({ score, level }: { score: number | null; level: Payment["risk_level"] }) { return <span className={`risk-badge ${level ?? "pending"}`}>{score ?? "—"}<small>{level ?? "pending"}</small></span>; }
function RiskGauge({ score, level }: { score: number; level: Payment["risk_level"] }) { return <div className={`risk-gauge ${level ?? "pending"}`} style={{ "--score": `${score * 3.6}deg` } as React.CSSProperties}><div><strong>{score}</strong><span>Risk score</span></div></div>; }
function formatStablecoin(units: string, decimals = 6): string { const value = Number(units) / 10 ** decimals; return value.toLocaleString(undefined, { maximumFractionDigits: 2, minimumFractionDigits: value > 0 ? 2 : 0 }); }
function shortAddress(value: string, width = 5): string { return `${value.slice(0, width + 2)}…${value.slice(-4)}`; }
function timeAgo(value: string): string { const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000)); if (seconds < 60) return `${seconds}s ago`; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`; if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`; return `${Math.floor(seconds / 86400)}d ago`; }
function formatTime(value: string): string { return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
