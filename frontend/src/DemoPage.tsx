import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  ExternalLink,
  Code2,
  Fingerprint,
  FlaskConical,
  LockKeyhole,
  Play,
  RotateCcw,
  ShieldCheck,
  ShieldX,
  Terminal,
  Wallet,
} from "lucide-react";
import { api, followDemoOperation } from "./api";
import { CopyButton } from "./components";
import { usePaymentFlow, type PaymentProgress } from "./payment-flow";
import type {
  DemoCommandResult,
  DemoMode,
  DemoOperation,
  DemoRun,
  DemoScenario,
  DemoStatus,
} from "./demo-types";
import type { Health, Payment } from "./types";
import "./demo.css";

const SCENARIOS = [
  {
    id: "purchase",
    title: "Purchase compute",
    tag: "Settlement",
    icon: Bot,
    description:
      "Sign a budget once. Discover a paid tool, satisfy its x402 challenge, and receive work.",
    command: "paradime buy --budget 3",
  },
  {
    id: "watchlist",
    title: "Recall a risky payment",
    tag: "Refund",
    icon: ShieldX,
    description:
      "A payment targets a watchlisted recipient. Inspect the risk decision and refund transaction.",
    command: "paradime pay --scenario watchlist",
  },
  {
    id: "budget",
    title: "Enforce a spending limit",
    tag: "Budget policy",
    icon: Wallet,
    description:
      "A 0.50 USDC mandate cannot authorize a 1 USDC offer. Stop it before funds move.",
    command: "paradime demo budget",
  },
  {
    id: "replay",
    title: "Reject a replay",
    tag: "Authorization",
    icon: Fingerprint,
    description:
      "Submit the same signed mandate twice and watch replay protection reject the duplicate.",
    command: "paradime demo replay",
  },
] as const;

function money(units: string | bigint): string {
  const value = BigInt(units);
  return `${(value / 1_000_000n).toLocaleString()}.${(value % 1_000_000n).toString().padStart(6, "0").slice(0, 2)}`;
}

function download(value: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function JsonView({ value, label }: { value: unknown; label: string }) {
  return (
    <details className="demo-json">
      <summary>
        <Code2 size={15} />
        {label}
      </summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function ChainEvidence({
  links,
  simulation,
  blocked = false,
}: {
  links: Record<string, string>;
  simulation: boolean;
  blocked?: boolean;
}) {
  if (simulation)
    return (
      <p className="demo-evidence-note">
        Offline simulation · no blockchain transaction or explorer proof.
      </p>
    );
  return (
    <aside className="demo-chain-evidence">
      <strong>
        <ExternalLink size={15} />
        Ethereum Sepolia evidence
      </strong>
      {Object.entries(links).map(([kind, url]) => (
        <div className="demo-evidence-row" key={kind}>
          <a href={url} target="_blank" rel="noreferrer">
            <span>{kind === "resolution" ? "Settlement / refund" : kind}</span>
            <code title={url.split("/").at(-1)}>{url.split("/").at(-1)}</code>
            <ExternalLink size={14} />
          </a>
          <CopyButton
            value={url.split("/").at(-1) ?? url}
            label={`Copy ${kind} transaction hash`}
          />
        </div>
      ))}
      {!Object.keys(links).length && (
        <p>
          {blocked
            ? "Rejected before spending. No transaction was sent."
            : "A transaction link appears after submission to Sepolia."}
        </p>
      )}
    </aside>
  );
}

export default function DemoPage({
  mode,
  health,
  onPayment,
  openDashboard,
  openWallet,
}: {
  mode: DemoMode;
  health: Health | null;
  onPayment: (payment: Payment) => void;
  openDashboard: () => void;
  openWallet: () => void;
}) {
  const { runPayment } = usePaymentFlow();
  const [tab, setTab] = useState<"journey" | "terminal" | "protection">(
    "journey",
  );
  const [scenario, setScenario] = useState<DemoScenario>("purchase");
  const [runs, setRuns] = useState<DemoRun[]>([]);
  const [result, setResult] = useState<DemoRun | null>(null);
  const [operation, setOperation] = useState<DemoOperation | null>(null);
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [previous, setPrevious] = useState<DemoOperation[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tour, setTour] = useState<number | null>(null);
  const [view, setView] = useState<
    "journey" | "policy" | "exchange" | "receipt"
  >("journey");
  const [budget, setBudget] = useState("3");
  const [prompt, setPrompt] = useState(
    "Analyze this customer feedback: clear documentation and reliable service.",
  );
  const [resetKey, setResetKey] = useState(0);
  const running = useRef(false);
  const active = useRef(true);
  const simulation = mode === "simulation";
  const ready = !!health && (simulation || !!status?.managed_wallet?.enabled);
  const chosen = SCENARIOS.find((item) => item.id === scenario) ?? SCENARIOS[0];

  useEffect(() => {
    active.current = true;
    void api
      .demoStatus()
      .then((value) => {
        if (active.current) setStatus(value);
      })
      .catch((reason: Error) => {
        if (active.current) setError(reason.message);
      });
    void api
      .demoOperations(mode)
      .then((items) => {
        if (active.current) setPrevious(items);
      })
      .catch(() => undefined);
    return () => {
      active.current = false;
    };
  }, [mode]);

  function accept(run: DemoRun) {
    if (!active.current) return;
    setResult(run);
    setScenario(run.scenario);
    setRuns((current) => [run, ...current].slice(0, 12));
    if (run.payment) onPayment(run.payment);
  }

  async function run(next: DemoScenario = scenario, tourIndex?: number) {
    if (running.current) return;
    running.current = true;
    setBusy(true);
    setError(null);
    setView("journey");
    setResult(null);
    setOperation(null);
    try {
      const input =
        next === "purchase" && tourIndex === undefined
          ? { budget_units: budgetUnits(budget), prompt }
          : {};
      const finished = await runPayment({
        preview: () =>
          api.previewPayment({
            kind: "scenario",
            mode,
            scenario: next,
            ...input,
          }),
        submit: async (notify) => {
          notify("Preparing the signed payment operation…");
          const started = await api.demoScenario(next, mode, input);
          const completed = await followDemoOperation(started, (progress) => {
            notify(progress.phase, progress.explorer_links);
            if (active.current) setOperation(progress);
          });
          if (!completed.result)
            throw new Error(completed.error ?? completed.phase);
          return {
            value: completed,
            heading: simulation
              ? "Simulation complete"
              : completed.result.outcome === "recalled"
                ? "Payment refunded"
                : completed.result.outcome === "blocked"
                  ? "Policy check complete"
                  : "Payment settled",
            detail: completed.result.summary,
            links: {
              ...completed.explorer_links,
              ...completed.result.explorer_links,
            },
          };
        },
      });
      if (!finished) return;
      if (!active.current) return;
      if (!finished.result)
        throw new Error(
          finished.error ??
            "Workflow interrupted; inspect the transaction evidence before retrying.",
        );
      accept(finished.result);
      void api
        .demoStatus()
        .then(setStatus)
        .catch(() => undefined);
      void api
        .demoOperations(mode)
        .then(setPrevious)
        .catch(() => undefined);
      if (tourIndex !== undefined) setTour(tourIndex);
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "The demo could not run.",
      );
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  function reset() {
    setRuns([]);
    setResult(null);
    setOperation(null);
    setError(null);
    setTour(null);
    setScenario("purchase");
    setView("journey");
    setBudget("3");
    setPrompt("Trusted compute delivers a safe and useful result");
    setResetKey((key) => key + 1);
  }

  async function resumeExisting() {
    if (!operation || running.current) return;
    running.current = true;
    setBusy(true);
    setError(null);
    try {
      const resumed = await api.resumeDemoOperation(operation.operation_id);
      const finished = await followDemoOperation(resumed, (progress) => {
        if (active.current) setOperation(progress);
      });
      if (!finished.result) throw new Error(finished.error ?? finished.phase);
      accept(finished.result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Recovery failed.");
    } finally {
      running.current = false;
      setBusy(false);
    }
  }

  return (
    <main id="main-content" className="demo-page">
      <div className="demo-notice">
        <FlaskConical size={15} />
        <span>
          <strong>
            {simulation ? "Offline simulation." : "Ethereum Sepolia demo."}
          </strong>{" "}
          {simulation
            ? "Explicitly simulated funds. Switch to Sepolia for on-chain purchases."
            : "Actual test USDC, wallet signatures, and public transaction receipts. Test tokens have no monetary value."}
        </span>
      </div>
      <section className="demo-heading section-wrap">
        <div>
          <p className="kicker">Autonomous payments</p>
          <h1>Payment workspace</h1>
          <p>Run a purchase. Test the controls. Inspect the transaction.</p>
        </div>
        <div className="demo-heading-actions">
          <button
            className="button button-outline"
            disabled={busy || !ready}
            onClick={() => {
              setTab("journey");
              void run("purchase", 0);
            }}
          >
            <Play size={15} />
            Run guided tour
          </button>
          <span>
            {simulation
              ? "Offline policy walkthrough"
              : "Purchases wait for actual blockchain transactions"}
          </span>
        </div>
      </section>
      {!simulation && (
        <section className="section-wrap demo-wallet-panel">
          <div>
            <Wallet size={20} />
            <span>
              <strong>Managed testnet wallet</strong>
              <small
                className="demo-wallet-address"
                title={status?.managed_wallet?.address ?? undefined}
              >
                {status?.managed_wallet?.address ??
                  "Waiting for the Sepolia payer…"}
              </small>
            </span>
            {status?.managed_wallet?.address && (
              <CopyButton
                value={status.managed_wallet.address}
                label="Copy wallet address"
              />
            )}
          </div>
          <div>
            <small>Available balance</small>
            <strong>
              {status?.managed_wallet?.balance_units
                ? money(status.managed_wallet.balance_units)
                : "—"}{" "}
              <span>USDC</span>
            </strong>
          </div>
          {status?.contract_address && (
            <a
              href={`https://sepolia.etherscan.io/address/${status.contract_address}`}
              target="_blank"
              rel="noreferrer"
            >
              View escrow
              <ExternalLink size={14} />
            </a>
          )}
          <button
            className="button button-outline"
            disabled={!health?.testnet_available}
            onClick={openWallet}
          >
            <Wallet size={15} />
            Connect your wallet
          </button>
          {status && !status.managed_wallet?.enabled && (
            <p>
              Configure the encrypted payer with <code>./demo</code>, or use
              your Sepolia browser wallet in the payment console.
            </p>
          )}
        </section>
      )}
      <div
        className="demo-tabs section-wrap"
        role="tablist"
        aria-label="Demo experiences"
      >
        {(
          [
            ["journey", "Payments", ShieldCheck],
            ["terminal", "Terminal", Terminal],
            ["protection", "Protection lab", FlaskConical],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            id={`demo-tab-${id}`}
            role="tab"
            aria-controls={`demo-panel-${id}`}
            aria-selected={tab === id}
            tabIndex={tab === id ? 0 : -1}
            className={tab === id ? "active" : ""}
            key={id}
            onClick={() => setTab(id)}
            onKeyDown={(event) => {
              const tabs = ["journey", "terminal", "protection"] as const;
              const index = tabs.indexOf(tab);
              const next =
                event.key === "ArrowRight"
                  ? tabs[(index + 1) % tabs.length]
                  : event.key === "ArrowLeft"
                    ? tabs[(index + tabs.length - 1) % tabs.length]
                    : event.key === "Home"
                      ? tabs[0]
                      : event.key === "End"
                        ? tabs[2]
                        : null;
              if (next) {
                event.preventDefault();
                setTab(next);
                document.getElementById(`demo-tab-${next}`)?.focus();
              }
            }}
          >
            <Icon size={17} />
            {label}
            {id === "protection" && <small>Concept</small>}
          </button>
        ))}
        <button className="demo-reset" onClick={reset} disabled={busy}>
          <RotateCcw size={14} />
          <span>Reset view</span>
        </button>
      </div>
      <section
        className="section-wrap demo-content"
        role="tabpanel"
        id={`demo-panel-${tab}`}
        aria-labelledby={`demo-tab-${tab}`}
      >
        {tab === "journey" && (
          <>
            {tour !== null && (
              <div className="demo-tour">
                <div>
                  <span className="demo-tour-count">{tour + 1} / 4</span>
                  <span>
                    <strong>
                      {tour === 3
                        ? "Tour complete. You have seen all four outcomes."
                        : "Guided tour"}
                    </strong>
                    <small>
                      {tour === 3
                        ? "Explore the terminal, inspect receipts, or try the concept lab."
                        : "Each scenario runs the underlying signature and policy checks."}
                    </small>
                  </span>
                </div>
                {tour < 3 ? (
                  <button
                    className="button button-dark"
                    disabled={busy}
                    onClick={() => void run(SCENARIOS[tour + 1].id, tour + 1)}
                  >
                    Next scenario
                    <ArrowRight size={15} />
                  </button>
                ) : (
                  <button
                    className="button button-outline"
                    onClick={() => setTab("terminal")}
                  >
                    Try the CLI
                    <Terminal size={15} />
                  </button>
                )}
              </div>
            )}
            <div className="demo-workspace">
              <aside className="demo-scenarios">
                <p className="demo-eyebrow">Choose a scenario</p>
                {SCENARIOS.map((item, index) => (
                  <button
                    key={item.id}
                    className={`demo-scenario ${scenario === item.id ? "active" : ""}`}
                    aria-pressed={scenario === item.id}
                    disabled={busy}
                    onClick={() => {
                      setScenario(item.id);
                      setResult(null);
                      setOperation(null);
                      setError(null);
                      setTour(null);
                    }}
                  >
                    <span className="demo-scenario-icon">
                      <item.icon size={19} />
                    </span>
                    <span>
                      <small>
                        0{index + 1} · {item.tag}
                      </small>
                      <strong>{item.title}</strong>
                    </span>
                    {runs.some((run) => run.scenario === item.id) ? (
                      <CheckCircle2 size={16} />
                    ) : (
                      <ChevronRight size={16} />
                    )}
                  </button>
                ))}
                <div className="demo-side-note">
                  <LockKeyhole size={17} />
                  <p>
                    {simulation
                      ? "Offline simulation never submits a transaction."
                      : "These actions move actual test USDC. Approval, deposit, and resolution transactions are linked in the result."}
                  </p>
                </div>
                <button className="demo-dashboard-link" onClick={openDashboard}>
                  Open payment dashboard
                  <ArrowRight size={14} />
                </button>
              </aside>
              <div className="demo-stage">
                <div className="demo-stage-head">
                  <span className="demo-eyebrow">
                    {result ? "Payment record" : "Scenario preview"}
                  </span>
                  <span className="demo-sim-badge">
                    <span />
                    {simulation ? "Offline simulation" : "Sepolia testnet"}
                  </span>
                </div>
                <div className="demo-stage-intro">
                  <h2>{result?.title ?? chosen.title}</h2>
                  <p>
                    {scenario === "trusted"
                      ? "Inspect the persisted payment decision and settlement evidence."
                      : chosen.description}
                  </p>
                </div>
                {!result && !busy && (
                  <div className="demo-agent-flow">
                    <div>
                      <Bot />
                      <strong>Buyer agent</strong>
                      <small>Constrained authority</small>
                    </div>
                    <ArrowRight />
                    <div className="demo-flow-trust">
                      <ShieldCheck />
                      <strong>Paradime</strong>
                      <small>Policy + escrow</small>
                    </div>
                    <ArrowRight />
                    <div>
                      <Code2 />
                      <strong>Seller tool</strong>
                      <small>Paid compute</small>
                    </div>
                  </div>
                )}
                {scenario === "purchase" && !result && !busy && (
                  <div className="demo-config">
                    <label>
                      Authorized budget <span>USDC</span>
                      <input
                        aria-label="Authorized budget in USDC"
                        inputMode="decimal"
                        value={budget}
                        onChange={(event) => setBudget(event.target.value)}
                      />
                    </label>
                    <label>
                      What should the seller analyze?
                      <input
                        aria-label="Seller input"
                        minLength={3}
                        maxLength={1000}
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
                      />
                    </label>
                  </div>
                )}
                {error && (
                  <div className="demo-error" role="alert">
                    {error}{" "}
                    <span>
                      Inspect submitted transactions before retrying. Start the
                      app with <code>./demo</code>.
                    </span>
                  </div>
                )}
                {operation && !result && (
                  <div className="demo-detail-body">
                    <div className="demo-operation-progress" role="status">
                      {busy && <span className="spinner" />}
                      <span>
                        <small>
                          {busy
                            ? "Payment in progress"
                            : "Operation interrupted"}
                        </small>
                        <strong>{operation.phase}</strong>
                      </span>
                    </div>
                    <div className="demo-operation-identity">
                      <span>Operation</span>
                      <code title={operation.operation_id}>
                        {operation.operation_id}
                      </code>
                      <CopyButton
                        value={operation.operation_id}
                        label="Copy operation ID"
                      />
                    </div>
                    <ChainEvidence
                      links={operation.explorer_links}
                      simulation={simulation}
                    />
                    {!busy &&
                      !simulation &&
                      operation.explorer_links.deposit && (
                        <button
                          className="button button-dark"
                          onClick={() => void resumeExisting()}
                        >
                          Resume existing payment
                          <ArrowRight size={15} />
                        </button>
                      )}
                  </div>
                )}
                {result && (
                  <>
                    <div className={`demo-outcome ${result.outcome}`}>
                      <span>
                        {result.outcome === "completed" ? (
                          <CheckCircle2 />
                        ) : result.outcome === "recalled" ? (
                          <RotateCcw />
                        ) : (
                          <ShieldX />
                        )}
                      </span>
                      <div>
                        <strong>
                          {result.outcome === "completed"
                            ? "Completed"
                            : result.outcome === "recalled"
                              ? "Recalled"
                              : "Blocked before payment"}
                        </strong>
                        <p>{result.summary}</p>
                      </div>
                    </div>
                    <ChainEvidence
                      links={{
                        ...operation?.explorer_links,
                        ...result.explorer_links,
                      }}
                      simulation={result.simulation}
                      blocked={result.outcome === "blocked"}
                    />
                    <div
                      className="demo-result-tabs"
                      role="group"
                      aria-label="Result details"
                    >
                      {(
                        [
                          ["journey", "Timeline"],
                          ["policy", "Policy & risk"],
                          ["exchange", "x402 exchange"],
                          ["receipt", "Receipt"],
                        ] as const
                      ).map(([id, label]) => (
                        <button
                          key={id}
                          className={view === id ? "active" : ""}
                          onClick={() => setView(id)}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                    {view === "journey" && (
                      <div className="demo-timeline">
                        {result.steps.map((step, index) => (
                          <div
                            className={`demo-step ${step.status}`}
                            key={step.label}
                          >
                            <span>
                              {step.status === "blocked" ? (
                                <ShieldX size={15} />
                              ) : (
                                <Check size={15} />
                              )}
                            </span>
                            <div>
                              <small>STEP {index + 1}</small>
                              <strong>{step.label}</strong>
                              <p>{step.detail}</p>
                            </div>
                          </div>
                        ))}
                        {result.purchase?.result && (
                          <div className="demo-delivery">
                            <Code2 size={18} />
                            <div>
                              <strong>The seller delivered</strong>
                              <p>
                                Classification:{" "}
                                <b>
                                  {String(
                                    result.purchase.result.classification,
                                  )}
                                </b>{" "}
                                · {String(result.purchase.result.word_count)}{" "}
                                words analyzed
                              </p>
                              <code>
                                Output fingerprint:{" "}
                                {String(result.purchase.result.sha256).slice(
                                  0,
                                  24,
                                )}
                                …
                              </code>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {view === "policy" && <PolicyView run={result} />}
                    {view === "exchange" && (
                      <div className="demo-detail-body">
                        {result.offer ? (
                          <>
                            <p>
                              The seller requests payment; the buyer returns a
                              purchase-bound authorization. This uses the custom{" "}
                              <code>paradime-escrow</code> scheme.
                            </p>
                            <JsonView
                              label="Seller → buyer: payment required"
                              value={result.offer}
                            />
                            {result.purchase?.x402_payload ? (
                              <JsonView
                                label="Buyer → seller: payment proof"
                                value={result.purchase.x402_payload}
                              />
                            ) : (
                              <p className="demo-muted">
                                No payment proof was issued because the budget
                                check blocked payment.
                              </p>
                            )}
                          </>
                        ) : (
                          <p>
                            This scenario tests{" "}
                            {result.scenario === "replay"
                              ? "signed mandate replay protection"
                              : "payment risk policy"}
                            . Run the autonomous purchase to inspect an x402
                            exchange.
                          </p>
                        )}
                      </div>
                    )}
                    {view === "receipt" && (
                      <div className="demo-detail-body">
                        <p>
                          {result.simulation
                            ? "Offline simulation record; identifiers are simulated."
                            : "This record binds the mandate, payment, seller result, and actual Sepolia transaction identifiers. It is not an independently signed production receipt."}
                        </p>
                        <button
                          className="button button-outline"
                          onClick={() =>
                            download(
                              result,
                              `paradime-${result.scenario}-demo.json`,
                            )
                          }
                        >
                          <ArrowDownToLine size={15} />
                          Download demo receipt
                        </button>
                        <JsonView label="View complete record" value={result} />
                      </div>
                    )}
                  </>
                )}
                <div className="demo-stage-footer">
                  <div className="demo-command">
                    <code>{chosen.command}</code>
                    <CopyButton
                      value={chosen.command}
                      label="Copy scenario command"
                    />
                  </div>
                  <button
                    className="button button-dark"
                    disabled={
                      busy ||
                      !ready ||
                      (!!operation &&
                        !result &&
                        !!operation.explorer_links.deposit)
                    }
                    onClick={() => void run()}
                  >
                    {busy
                      ? simulation
                        ? "Running checks…"
                        : "Waiting for Sepolia…"
                      : result
                        ? "Run again"
                        : "Run scenario"}
                    <Play size={14} />
                  </button>
                </div>
              </div>
            </div>
            {runs.length > 0 && (
              <div className="demo-run-history">
                <p className="demo-eyebrow">This session</p>
                <div>
                  {runs.map((run, index) => (
                    <button
                      key={`${run.scenario}-${index}`}
                      onClick={() => {
                        setResult(run);
                        setScenario(run.scenario);
                        setView("journey");
                      }}
                    >
                      <span className={`demo-history-dot ${run.outcome}`} />
                      {run.title}
                      <small>{run.outcome}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
        <div hidden={tab !== "terminal"}>
          <DeveloperTerminal
            key={resetKey}
            mode={mode}
            onRun={accept}
            onBusy={setBusy}
          />
        </div>
        <div hidden={tab !== "protection"}>
          <ProtectionLab key={resetKey} />
        </div>
      </section>
      {previous.length > 0 && !simulation && (
        <section className="section-wrap demo-saved-operations">
          <p className="demo-eyebrow">Recent operations</p>
          {previous.map((item) => (
            <button
              disabled={busy}
              key={item.operation_id}
              onClick={() => {
                setTab("journey");
                setScenario(item.scenario);
                setOperation(item);
                setResult(item.result);
                setError(item.error);
              }}
            >
              <span>{item.scenario}</span>
              <code>{item.operation_id.slice(0, 14)}…</code>
              <strong>{item.status}</strong>
              <ChevronRight size={14} />
            </button>
          ))}
        </section>
      )}
      <section className="section-wrap demo-honesty">
        <div>
          <ShieldCheck size={18} />
          <strong>Implemented</strong>
          <p>
            Owner signatures, mandate limits, replay rejection, deterministic
            risk scoring, x402 messages, and seller proof checks.
          </p>
        </div>
        <div>
          <CircleDollarSign size={18} />
          <strong>{simulation ? "Offline simulation" : "On-chain"}</strong>
          <p>
            {simulation
              ? "Synthetic transaction identifiers are confined to this explicitly selected environment."
              : "Balances come from RPC. Deposits and arbitration are actual ERC-20 transactions. The demo observes mined blocks; finality takes longer."}
          </p>
        </div>
        <div>
          <FlaskConical size={18} />
          <strong>Concept only</strong>
          <p>
            The protection lab illustrates a possible future product. It does
            not price options, underwrite risk, or issue coverage.
          </p>
        </div>
      </section>
    </main>
  );
}

function budgetUnits(value: string): string {
  if (!/^\d+(\.\d{1,6})?$/.test(value))
    throw new Error(
      "Enter a positive USDC budget with up to six decimal places.",
    );
  const [whole, fraction = ""] = value.split(".");
  const units = BigInt(whole) * 1_000_000n + BigInt(fraction.padEnd(6, "0"));
  if (units <= 0n || units > 1_000_000_000_000n)
    throw new Error(
      "Budget must be greater than 0 and at most 1,000,000 USDC.",
    );
  return units.toString();
}

function PolicyView({ run }: { run: DemoRun }) {
  const mandate = run.mandate;
  return (
    <div className="demo-detail-body">
      {mandate && (
        <>
          <p className="demo-eyebrow">Signed authority</p>
          <div className="demo-facts">
            <div>
              <span>Per payment</span>
              <strong>
                {money(mandate.max_amount_per_payment_units)} USDC
              </strong>
            </div>
            <div>
              <span>Total budget</span>
              <strong>{money(mandate.total_budget_units)} USDC</strong>
            </div>
            <div>
              <span>Reserved / spent</span>
              <strong>{money(mandate.spent_units)} USDC</strong>
            </div>
            <div>
              <span>Allowed service</span>
              <strong>{mandate.allowed_service}</strong>
            </div>
          </div>
          <p className="demo-muted">
            The demo owner signs once. The delegate is constrained by
            application policy; its key is not constrained on-chain.
          </p>
          <JsonView
            label="Inspect owner, delegate, signature, expiry, and nonce"
            value={mandate}
          />
        </>
      )}
      {run.payment && (
        <>
          <p className="demo-eyebrow">
            Persisted risk signals · {run.payment.risk_score}/100 policy score
          </p>
          <div className="demo-signals">
            {run.payment.risk_signals.map((signal) => (
              <div key={signal.name}>
                <span>{signal.name.replaceAll("_", " ")}</span>
                <div>
                  <i
                    style={{ width: `${Math.min(100, signal.contribution)}%` }}
                  />
                </div>
                <strong>+{signal.contribution}</strong>
              </div>
            ))}
          </div>
          <JsonView
            label="Inspect bounded signal evidence"
            value={run.payment.risk_signals}
          />
        </>
      )}
      {!mandate && !run.payment && (
        <p>No authority or payment record was created.</p>
      )}
    </div>
  );
}

type TerminalEntry = {
  command: string;
  result?: DemoCommandResult;
  error?: string;
};

function TerminalOutput({ text }: { text: string }) {
  return (
    <>
      {text
        .split(
          /(https:\/\/sepolia\.etherscan\.io\/(?:tx|address)\/0x[a-fA-F0-9]+)/g,
        )
        .map((part, index) =>
          part.startsWith("https://sepolia.etherscan.io/") ? (
            <a href={part} target="_blank" rel="noreferrer" key={index}>
              {part}
            </a>
          ) : (
            part
          ),
        )}
    </>
  );
}

function DeveloperTerminal({
  mode,
  onRun,
  onBusy,
}: {
  mode: DemoMode;
  onRun: (run: DemoRun) => void;
  onBusy: (busy: boolean) => void;
}) {
  const { runPayment } = usePaymentFlow();
  const [entries, setEntries] = useState<TerminalEntry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const historyIndex = useRef<number | null>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const pending = useRef(false);
  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [entries, busy]);

  async function execute(command: string) {
    if (pending.current || !command.trim()) return;
    if (command.trim() === "clear") {
      setEntries([]);
      setInput("");
      return;
    }
    pending.current = true;
    setBusy(true);
    onBusy(true);
    setInput("");
    historyIndex.current = null;
    try {
      const review = await api.previewPayment({
        kind: "command",
        mode,
        command,
      });
      const executeCommand = async (notify?: PaymentProgress) => {
        let result = await api.demoCommand(command, mode);
        notify?.(
          "Payment operation started…",
          result.operation?.explorer_links,
        );
        setEntries((items) => [...items, { command, result }].slice(-60));
        if (result.operation) {
          const initialOutput = result.output;
          const finished = await followDemoOperation(
            result.operation,
            (progress) => {
              notify?.(progress.phase, progress.explorer_links);
              const output = [
                ...initialOutput,
                progress.phase,
                ...Object.entries(progress.explorer_links).map(
                  ([key, url]) => `${key}: ${url}`,
                ),
              ];
              result = { ...result, operation: progress, output };
              setEntries((items) => [
                ...items.slice(0, -1),
                { command, result },
              ]);
            },
          );
          result = {
            ...result,
            operation: finished,
            run: finished.result,
            exit_code: finished.status === "completed" ? 0 : 1,
            output: [
              ...result.output,
              finished.result
                ? `[${finished.result.outcome.toUpperCase()}] ${finished.result.summary}`
                : (finished.error ?? finished.phase),
            ],
          };
          setEntries((items) => [...items.slice(0, -1), { command, result }]);
        }

        return result;
      };
      const result = review
        ? await runPayment({
            initialReview: review,
            preview: () =>
              api.previewPayment({ kind: "command", mode, command }),
            submit: async (notify) => {
              const executed = await executeCommand(notify);
              if (executed.exit_code)
                throw new Error(
                  executed.output.at(-1) ?? "Payment operation failed.",
                );
              return {
                value: executed,
                heading:
                  mode === "simulation"
                    ? "Simulation complete"
                    : executed.run?.outcome === "recalled"
                      ? "Payment refunded"
                      : executed.run?.outcome === "blocked"
                        ? "Policy check complete"
                        : "Payment settled",
                detail: executed.run?.summary ?? "Operation completed.",
                links: {
                  ...executed.operation?.explorer_links,
                  ...executed.run?.explorer_links,
                },
              };
            },
          })
        : await executeCommand();
      if (!result) {
        setEntries((items) => [
          ...items,
          {
            command,
            result: {
              command,
              exit_code: 0,
              output: ["Payment cancelled. No transaction was submitted."],
              run: null,
              operation: null,
              data: null,
            },
          },
        ]);
        setInput(command);
      } else if (result.run) onRun(result.run);
    } catch (reason) {
      setEntries((items) => [
        ...items,
        {
          command,
          error:
            reason instanceof Error
              ? reason.message
              : "API unavailable. Run make demo.",
        },
      ]);
    } finally {
      pending.current = false;
      setBusy(false);
      onBusy(false);
      field.current?.focus();
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void execute(input);
  }

  return (
    <div className="demo-terminal-layout">
      <div className="demo-terminal">
        <div className="demo-terminal-bar">
          <strong>
            <Terminal size={15} /> paradime
          </strong>
          <small>
            {mode === "sepolia" ? "Sepolia session" : "Offline simulation"}
          </small>
        </div>
        <div
          className="demo-terminal-output"
          ref={scroll}
          role="log"
          aria-label="CLI output"
          aria-live="polite"
        >
          <div className="demo-terminal-welcome">
            <pre>Paradime CLI</pre>
            <p>
              The same commands work in your local terminal with{" "}
              <code>./paradime</code>.
            </p>
            <p>
              Type <b>help</b> to explore. This terminal runs a bounded command
              interface, not an operating-system shell.
            </p>
          </div>
          {entries.map((entry, index) => (
            <div className="demo-terminal-entry" key={index}>
              <div className="demo-terminal-command">
                <span>❯</span> {entry.command}
              </div>
              <pre
                className={
                  entry.error || entry.result?.exit_code
                    ? "demo-terminal-error"
                    : ""
                }
              >
                <TerminalOutput
                  text={entry.error ?? entry.result?.output.join("\n") ?? ""}
                />
              </pre>
              {entry.result?.data && (
                <JsonView label="Structured output" value={entry.result.data} />
              )}
            </div>
          ))}
          {busy && (
            <p className="demo-terminal-pending">
              {mode === "sepolia"
                ? "Waiting for the payment operation…"
                : "Running policy checks…"}
            </p>
          )}
        </div>
        <form className="demo-terminal-prompt" onSubmit={submit}>
          <span>❯</span>
          <input
            ref={field}
            aria-label="CLI command"
            value={input}
            maxLength={512}
            placeholder="paradime buy --budget 3"
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowUp" || event.key === "ArrowDown") {
                event.preventDefault();
                const next =
                  event.key === "ArrowUp"
                    ? Math.max(0, (historyIndex.current ?? entries.length) - 1)
                    : Math.min(
                        entries.length,
                        (historyIndex.current ?? entries.length) + 1,
                      );
                historyIndex.current = next;
                setInput(entries[next]?.command ?? "");
              }
            }}
          />
          <button
            disabled={busy || !input.trim()}
            type="submit"
            aria-label="Run command"
          >
            <ArrowRight size={18} />
          </button>
        </form>
      </div>
      <aside className="demo-terminal-guide">
        <p className="demo-eyebrow">Try a command</p>
        <h2>Command reference</h2>
        <p>
          Run a purchase, trigger a recall, or inspect the latest receipt.{" "}
          {mode === "sepolia"
            ? "Payment commands open a charge and balance review before submission. Read-only commands run immediately. Transaction links appear as payments progress."
            : "Explicit offline simulation creates no blockchain transactions."}
        </p>
        {[
          "paradime doctor",
          "paradime buy --budget 3",
          "paradime demo budget",
          "paradime demo replay",
          "paradime payments",
          "paradime receipt latest",
          "paradime help",
        ].map((command) => (
          <button
            disabled={busy}
            key={command}
            onClick={() => void execute(command)}
          >
            <code>{command}</code>
            <ChevronRight size={14} />
          </button>
        ))}
        <div className="demo-local-command">
          <strong>On your machine</strong>
          <code>make demo</code>
          <code>./paradime buy --budget 3</code>
          <code>./paradime --json receipt latest</code>
        </div>
      </aside>
    </div>
  );
}

function ProtectionLab() {
  const [leverage, setLeverage] = useState(5);
  const [drop, setDrop] = useState(25);
  const [equity, setEquity] = useState("1000");
  const [stage, setStage] = useState<"quote" | "active" | "resolved">("quote");
  const equityUnits = BigInt(equity) * 1_000_000n;
  const premium = equityUnits / 50n;
  const barrier = 100 - 100 / leverage;
  const liquidated = 100 - drop <= barrier;
  const payout = stage === "resolved" && liquidated ? equityUnits : 0n;
  const pointY = (price: number) => 150 - (price - 35) * 1.6;
  const path = `M 25 ${pointY(100)} L 120 ${pointY(100 - drop * 0.1)} L 210 ${pointY(100 - drop * 0.35)} L 300 ${pointY(100 - drop * 0.2)} L 390 ${pointY(100 - drop * 0.8)} L 465 ${pointY(100 - drop)}`;

  return (
    <div className="demo-protection">
      <div className="demo-concept-banner">
        <FlaskConical size={18} />
        <span>
          <strong>A preview of a possible future product.</strong> Mock coverage
          and payout; the premium is a preset 2% illustration, not a risk model
          or executable quote.
        </span>
      </div>
      <div className="demo-protection-grid">
        <div className="demo-protection-controls">
          <p className="demo-eyebrow">Design a protected position</p>
          <h2>
            What if an agent
            <br />
            could buy protection?
          </h2>
          <p>
            Walk through a quote, a reserved payout, and an adverse market move.
          </p>
          <label>
            Equity to protect
            <select
              aria-label="Equity to protect"
              value={equity}
              onChange={(event) => {
                setEquity(event.target.value);
                setStage("quote");
              }}
            >
              {["500", "1000", "5000"].map((value) => (
                <option value={value} key={value}>
                  {value} USDC
                </option>
              ))}
            </select>
          </label>
          <label>
            Leverage<strong>{leverage}×</strong>
            <input
              aria-label="Leverage"
              type="range"
              min="2"
              max="10"
              value={leverage}
              onChange={(event) => {
                setLeverage(Number(event.target.value));
                setStage("quote");
              }}
            />
          </label>
          <label>
            Simulated price drop<strong>{drop}%</strong>
            <input
              aria-label="Simulated price drop"
              type="range"
              min="5"
              max="60"
              value={drop}
              onChange={(event) => {
                setDrop(Number(event.target.value));
                setStage("quote");
              }}
            />
          </label>
          <button
            className="button button-dark"
            disabled={stage === "resolved"}
            onClick={() => setStage(stage === "quote" ? "active" : "resolved")}
          >
            {stage === "quote"
              ? "Activate demo protection"
              : stage === "active"
                ? "Run market shock"
                : "Scenario resolved"}
            <ArrowRight size={16} />
          </button>
          {stage === "resolved" && (
            <button
              className="demo-dashboard-link"
              onClick={() => setStage("quote")}
            >
              <RotateCcw size={14} />
              Try another scenario
            </button>
          )}
        </div>
        <div className="demo-protection-result">
          <div className="demo-stage-head">
            <span className="demo-eyebrow">Illustrative market path</span>
            <span className="demo-sim-badge">Concept simulation</span>
          </div>
          <svg
            className="demo-price-chart"
            viewBox="0 0 490 200"
            role="img"
            aria-label={`Illustrative price path drops ${drop} percent; toy liquidation threshold is ${barrier.toFixed(0)} percent of entry.`}
          >
            <line
              x1="25"
              x2="465"
              y1={pointY(100)}
              y2={pointY(100)}
              className="demo-chart-grid"
            />
            <line
              x1="25"
              x2="465"
              y1={pointY(barrier)}
              y2={pointY(barrier)}
              className="demo-chart-barrier"
            />
            <text x="25" y="25">
              Entry: 100
            </text>
            <text x="25" y={pointY(barrier) + 17}>
              Toy liquidation level: {barrier.toFixed(0)}
            </text>
            <path
              d={path}
              className={`demo-chart-path ${stage === "resolved" && liquidated ? "triggered" : ""}`}
            />
            <circle cx="465" cy={pointY(100 - drop)} r="5" />
            <text x="345" y="185">
              Hypothetical price · time →
            </text>
          </svg>
          <div className="demo-facts">
            <div>
              <span>Position notional</span>
              <strong>{money(equityUnits * BigInt(leverage))} USDC</strong>
            </div>
            <div>
              <span>Coverage cap</span>
              <strong>{money(equityUnits)} USDC</strong>
            </div>
            <div>
              <span>Illustrative premium</span>
              <strong>{money(premium)} USDC</strong>
            </div>
            <div>
              <span>Mock reserve</span>
              <strong>
                {stage === "quote"
                  ? "Not reserved"
                  : `${money(equityUnits)} USDC`}
              </strong>
            </div>
          </div>
          <div
            className={`demo-protection-state ${stage === "resolved" ? (liquidated ? "triggered" : "safe") : ""}`}
          >
            <ShieldCheck />
            <div>
              <strong>
                {stage === "quote"
                  ? "Review the illustrative terms"
                  : stage === "active"
                    ? "Demo cover activated · mock capital reserved"
                    : liquidated
                      ? `${money(payout)} USDC mock payout`
                      : "No trigger · no payout"}
              </strong>
              <p>
                {stage === "resolved"
                  ? liquidated
                    ? "The toy position crossed its threshold. The model reimburses covered equity, not borrowed notional."
                    : "The toy position stayed above its threshold. The illustrative premium remains a cost."
                  : "A protection payout needs separate backing capital. Payment escrow alone cannot fund it."}
              </p>
            </div>
          </div>
          <p className="demo-model-note">
            Toy model: threshold = entry × (1 − 1/leverage). It excludes
            maintenance margin, funding, fees, partial liquidation, and oracle
            behavior. No Black–Scholes pricing or real coverage is implemented.
          </p>
          {stage === "resolved" && (
            <button
              className="button button-outline"
              onClick={() =>
                download(
                  {
                    concept_only: true,
                    model: "toy-liquidation-v1",
                    premium_model: "illustrative-fixed-2-percent",
                    equity_units: equityUnits.toString(),
                    leverage,
                    price_drop_percent: drop,
                    triggered: liquidated,
                    mock_payout_units: payout.toString(),
                  },
                  "paradime-protection-concept.json",
                )
              }
            >
              <ArrowDownToLine size={15} />
              Download concept record
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
