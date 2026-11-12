import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  CircleAlert,
  ExternalLink,
  LoaderCircle,
  LockKeyhole,
  RotateCcw,
  Wallet,
  X,
} from "lucide-react";
import { CopyButton } from "./components";
import type { PaymentReview } from "./types";
import "./payment-flow.css";

export type PaymentProgress = (
  message: string,
  links?: Record<string, string>,
) => void;
type Completion<T> = {
  value: T;
  heading: string;
  detail: string;
  links?: Record<string, string>;
};
type FlowOptions<T> = {
  preview: () => Promise<PaymentReview | null>;
  initialReview?: PaymentReview;
  submit: (
    progress: PaymentProgress,
    review: PaymentReview,
  ) => Promise<Completion<T>>;
};
type Phase =
  | "loading"
  | "review"
  | "checking"
  | "submitting"
  | "complete"
  | "failed";
type View = {
  id: string;
  phase: Phase;
  review: PaymentReview | null;
  error: string | null;
  message: string;
  heading: string;
  links: Record<string, string>;
  minimized: boolean;
  afterReview: PaymentReview | null;
  refreshing: boolean;
};
type Session = {
  id: string;
  locked: boolean;
  approved: boolean;
  preview: () => Promise<PaymentReview | null>;
  submit: (
    progress: PaymentProgress,
    review: PaymentReview,
  ) => Promise<Omit<Completion<unknown>, "value">>;
  cancel: () => void;
  fail: (error: Error) => void;
};
const PaymentContext = createContext<{
  runPayment: <T>(options: FlowOptions<T>) => Promise<T | undefined>;
} | null>(null);

export function usePaymentFlow() {
  const context = useContext(PaymentContext);
  if (!context) throw new Error("Payment flow requires PaymentProvider");
  return context;
}

export function displayUnits(units: string, decimals = 6, fractionDigits = 6) {
  const value = BigInt(units);
  const scale = 10n ** BigInt(decimals);
  const whole = (value / scale).toLocaleString();
  const fraction = (value % scale)
    .toString()
    .padStart(decimals, "0")
    .slice(0, fractionDigits)
    .replace(/0+$/, "");
  if (value > 0n && value < scale && !fraction)
    return `<0.${"0".repeat(fractionDigits - 1)}1`;
  return `${whole}${fraction ? `.${fraction}` : ".00"}`;
}

export function PaymentProvider({ children }: { children: ReactNode }) {
  const [view, setView] = useState<View | null>(null);
  const session = useRef<Session | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const isOpen = !!view && !view.minimized;

  useEffect(() => {
    const element = dialog.current;
    if (isOpen && element && !element.open) element.showModal();
    if (!isOpen && element?.open) element.close();
  }, [isOpen]);

  const update = (
    id: string,
    change: Partial<View> | ((current: View) => Partial<View>),
  ) => {
    setView((current) =>
      current?.id === id
        ? {
            ...current,
            ...(typeof change === "function" ? change(current) : change),
          }
        : current,
    );
  };

  async function loadReview(current: Session) {
    update(current.id, { phase: "loading", error: null });
    try {
      const review = await current.preview();
      if (!review) throw new Error("This action does not initiate a payment.");
      update(current.id, { phase: "review", review });
    } catch (error) {
      update(current.id, {
        phase: "review",
        error:
          error instanceof Error
            ? error.message
            : "Could not load wallet balances.",
      });
    }
  }

  function runPayment<T>(options: FlowOptions<T>): Promise<T | undefined> {
    if (session.current && !session.current.approved)
      return Promise.reject(
        new Error("Finish or cancel the open payment review first."),
      );
    if (session.current?.locked)
      return Promise.reject(
        new Error(
          "A payment is already in progress. Open its status window to track it.",
        ),
      );
    return new Promise((resolve, reject) => {
      const current: Session = {
        id: crypto.randomUUID(),
        locked: false,
        approved: false,
        preview: options.preview,
        cancel: () => resolve(undefined),
        fail: reject,
        submit: async (progress, review) => {
          const completion = await options.submit(progress, review);
          resolve(completion.value);
          return completion;
        },
      };
      session.current = current;
      setView({
        id: current.id,
        phase: options.initialReview ? "review" : "loading",
        review: options.initialReview ?? null,
        error: null,
        message: "",
        heading: "",
        links: {},
        minimized: false,
        afterReview: null,
        refreshing: false,
      });
      if (!options.initialReview) void loadReview(current);
    });
  }

  async function refreshBalance(current: Session) {
    update(current.id, { refreshing: true });
    try {
      const afterReview = await current.preview();
      update(current.id, { afterReview, refreshing: false });
    } catch {
      update(current.id, { refreshing: false });
    }
  }

  async function confirm() {
    const current = session.current;
    if (!current || !view?.review || current.locked || current.approved) return;
    current.locked = true;
    update(current.id, { phase: "checking", error: null });
    let latest: PaymentReview | null;
    try {
      latest = await current.preview();
      if (session.current !== current) return;
      if (!latest) throw new Error("Payment details could not be verified.");
      const refreshed = latest;
      const changed = (
        [
          "mode",
          "sender",
          "receiver",
          "amount_units",
          "budget_units",
          "token_symbol",
          "token_decimals",
        ] as const
      ).some((key) => refreshed[key] !== view.review?.[key]);
      if (!latest.can_submit || changed) {
        update(current.id, {
          phase: "review",
          review: latest,
          error: changed
            ? "Payment details changed. Review the updated amount and wallet before confirming."
            : null,
        });
        current.locked = false;
        return;
      }
    } catch (error) {
      update(current.id, {
        phase: "review",
        error:
          error instanceof Error
            ? error.message
            : "Could not refresh balances. Nothing has been submitted.",
      });
      current.locked = false;
      return;
    }
    current.approved = true;
    update(current.id, {
      phase: "submitting",
      review: latest,
      message: "Preparing your payment…",
    });
    const progress: PaymentProgress = (message, links = {}) =>
      update(current.id, (state) => ({
        message,
        links: { ...state.links, ...links },
      }));
    try {
      const completion = await current.submit(progress, latest);
      current.locked = false;
      update(current.id, (state) => ({
        phase: "complete",
        heading: completion.heading,
        message: completion.detail,
        links: { ...state.links, ...completion.links },
        error: null,
      }));
      void refreshBalance(current);
    } catch (error) {
      current.locked = false;
      const failure =
        error instanceof Error
          ? error
          : new Error("Payment could not be confirmed.");
      update(current.id, { phase: "failed", error: failure.message });
      current.fail(failure);
      void refreshBalance(current);
    }
  }

  function close() {
    const current = session.current;
    if (current?.locked && current.approved) {
      update(current.id, { minimized: true });
      return;
    }
    current?.cancel();
    session.current = null;
    setView(null);
  }

  const review = view?.review;
  const working = view?.phase === "submitting" || view?.phase === "checking";
  const settled = view?.phase === "complete" || view?.phase === "failed";
  const simulation = review?.mode === "simulation";
  const balanceAfter =
    review?.balance_units !== null && review?.balance_units !== undefined
      ? BigInt(review.balance_units) - BigInt(review.amount_units)
      : null;
  const refreshedBalance = view?.afterReview?.balance_units;
  const heading =
    view?.phase === "complete"
      ? view.heading
      : view?.phase === "failed"
        ? "Payment needs attention"
        : working
          ? "Payment in progress"
          : review?.policy_only
            ? "Review policy check"
            : "Review payment";

  return (
    <PaymentContext.Provider value={{ runPayment }}>
      {children}
      <dialog
        ref={dialog}
        className={`payment-dialog ${view ? `payment-phase-${view.phase}` : ""}`}
        aria-labelledby="payment-dialog-title"
        aria-describedby="payment-dialog-description"
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        {view && (
          <>
            <header className="payment-dialog-header">
              <span className="payment-window-mark">
                {settled ? (
                  view.phase === "complete" ? (
                    <CheckCircle2 />
                  ) : (
                    <CircleAlert />
                  )
                ) : (
                  <Wallet />
                )}
              </span>
              <span className="payment-network">
                <i />{" "}
                {review
                  ? simulation
                    ? "Offline simulation"
                    : "Ethereum Sepolia"
                  : "Payment review"}
              </span>
              <button
                className="payment-window-close"
                onClick={close}
                aria-label={
                  view.phase === "submitting"
                    ? "Minimize payment status"
                    : "Close payment review"
                }
              >
                <X size={18} />
              </button>
            </header>
            <div className="payment-dialog-body">
              <h2 id="payment-dialog-title" aria-live="polite">
                {heading}
              </h2>
              <p id="payment-dialog-description">
                {settled
                  ? view.phase === "failed"
                    ? "No completion was confirmed. Inspect activity and submitted transactions before retrying."
                    : view.message
                  : (review?.title ??
                    "Loading your wallet and payment details…")}
              </p>
              {review ? (
                <>
                  <div className="payment-charge">
                    <span>
                      {review.policy_only
                        ? "Charge"
                        : simulation
                          ? "Simulated charge"
                          : "Amount to escrow"}
                    </span>
                    <strong>
                      {displayUnits(review.amount_units, review.token_decimals)}{" "}
                      <small>{review.token_symbol}</small>
                    </strong>
                    {review.budget_units && (
                      <small>
                        Authorized budget:{" "}
                        {displayUnits(
                          review.budget_units,
                          review.token_decimals,
                        )}{" "}
                        {review.token_symbol}
                        {review.policy_only && review.offer_units
                          ? ` · offer ${displayUnits(review.offer_units, review.token_decimals)} ${review.token_symbol}`
                          : ""}
                      </small>
                    )}
                  </div>
                  <section
                    className="payment-balance-window"
                    aria-label="Wallet balances"
                  >
                    <div className="payment-balance-heading">
                      <Wallet size={15} />
                      <strong>
                        {simulation
                          ? "Simulation environment"
                          : "Sepolia wallet balance"}
                      </strong>
                      {!working && (
                        <button
                          className="payment-balance-refresh"
                          disabled={view.refreshing || view.phase === "loading"}
                          onClick={() => {
                            if (session.current) {
                              if (settled) void refreshBalance(session.current);
                              else void loadReview(session.current);
                            }
                          }}
                          aria-label="Refresh wallet balance"
                        >
                          <RotateCcw
                            size={13}
                            className={view.refreshing ? "payment-spin" : ""}
                          />
                        </button>
                      )}
                    </div>
                    {review.sender && (
                      <div className="payment-wallet-id">
                        <code title={review.sender}>{review.sender}</code>
                        <CopyButton
                          value={review.sender}
                          label="Copy paying wallet address"
                        />
                      </div>
                    )}
                    <dl>
                      <div>
                        <dt>
                          {settled
                            ? "Balance before payment"
                            : "Available balance"}
                        </dt>
                        <dd>
                          {review.balance_units !== null
                            ? `${displayUnits(review.balance_units, review.token_decimals)} ${review.token_symbol}`
                            : "No on-chain balance"}
                        </dd>
                      </div>
                      <div className="payment-balance-after">
                        <dt>{settled ? "Current balance" : "After deposit"}</dt>
                        <dd>
                          {simulation ? (
                            "Simulated funds"
                          ) : settled ? (
                            view.refreshing ? (
                              <span
                                className="payment-balance-skeleton"
                                aria-label="Refreshing balance"
                              />
                            ) : refreshedBalance !== null &&
                              refreshedBalance !== undefined ? (
                              `${displayUnits(refreshedBalance, review.token_decimals)} ${review.token_symbol}`
                            ) : (
                              "Refresh unavailable"
                            )
                          ) : balanceAfter !== null && balanceAfter >= 0n ? (
                            `${displayUnits(balanceAfter.toString(), review.token_decimals)} ${review.token_symbol}`
                          ) : (
                            "Insufficient balance"
                          )}
                        </dd>
                      </div>
                      {!simulation && (
                        <div>
                          <dt>ETH available for gas</dt>
                          <dd>
                            {review.native_balance_wei !== null
                              ? `${displayUnits(view.afterReview?.native_balance_wei ?? review.native_balance_wei, 18)} ETH`
                              : "Unavailable"}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </section>
                  {review.receiver && (
                    <div className="payment-recipient">
                      <span>Recipient</span>
                      <code title={review.receiver}>{review.receiver}</code>
                      <CopyButton
                        value={review.receiver}
                        label="Copy recipient address"
                      />
                    </div>
                  )}
                  {!settled &&
                    review.notes.map((note) => (
                      <p className="payment-review-note" key={note}>
                        {note}
                      </p>
                    ))}
                  {!settled && review.blockers.length > 0 && (
                    <div className="payment-review-error" role="alert">
                      {review.blockers.map((message) => (
                        <p key={message}>
                          <CircleAlert size={15} />
                          {message}
                        </p>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div
                  className="payment-review-loading"
                  aria-label="Loading payment details"
                >
                  <span />
                  <span />
                  <span />
                </div>
              )}
              {view.error && (
                <div className="payment-review-error" role="alert">
                  <CircleAlert size={16} />
                  <span>{view.error}</span>
                </div>
              )}
              {working && (
                <div className="payment-progress" role="status">
                  <div
                    className="payment-transfer-animation"
                    aria-hidden="true"
                  >
                    <Wallet size={18} />
                    <span>
                      <i />
                      <i />
                      <i />
                    </span>
                    <LockKeyhole size={18} />
                  </div>
                  <strong>
                    {view.phase === "checking"
                      ? "Refreshing your balance…"
                      : view.message}
                  </strong>
                  <small>
                    {review?.policy_only
                      ? "Running the policy check"
                      : simulation
                        ? "Running explicitly offline checks"
                        : "Confirmations follow the network. You can minimize this window."}
                  </small>
                  <ol>
                    <li className="done">
                      <Check size={12} />
                      Reviewed
                    </li>
                    <li className="current">
                      <LoaderCircle size={12} className="payment-spin" />
                      {view.phase === "checking" ? "Verify balance" : "Submit"}
                    </li>
                    <li>Receipt</li>
                  </ol>
                </div>
              )}
              {Object.keys(view.links).length > 0 && (
                <div className="payment-receipt-links">
                  {Object.entries(view.links).map(([label, url]) => (
                    <a href={url} target="_blank" rel="noreferrer" key={label}>
                      {label === "resolution" ? "Settlement / refund" : label}{" "}
                      transaction
                      <ExternalLink size={13} />
                    </a>
                  ))}
                </div>
              )}
            </div>
            <footer className="payment-dialog-footer">
              {settled ? (
                <button className="button button-dark" onClick={close}>
                  Done <Check size={15} />
                </button>
              ) : working ? (
                <button className="button button-outline" onClick={close}>
                  {view.phase === "checking"
                    ? "Cancel payment review"
                    : "Keep tracking in background"}
                </button>
              ) : (
                <>
                  <button className="button button-outline" onClick={close}>
                    Cancel
                  </button>
                  {view.error && (
                    <button
                      className="payment-retry"
                      onClick={() => {
                        if (session.current) void loadReview(session.current);
                      }}
                    >
                      Retry balance check
                    </button>
                  )}
                  <button
                    className="button button-dark payment-confirm"
                    disabled={
                      !review?.can_submit ||
                      view.phase === "loading" ||
                      !!view.error
                    }
                    onClick={() => void confirm()}
                  >
                    {view.phase === "loading" ? (
                      <>
                        <LoaderCircle size={15} className="payment-spin" />
                        Loading balance…
                      </>
                    ) : (
                      <>
                        {review?.policy_only
                          ? "Run policy check"
                          : "Confirm payment"}
                        <ArrowRight size={15} />
                      </>
                    )}
                  </button>
                </>
              )}
            </footer>
          </>
        )}
      </dialog>
      {view?.minimized && (
        <button
          className={`payment-floating-status ${view.phase}`}
          onClick={() => update(view.id, { minimized: false })}
        >
          {settled ? (
            view.phase === "complete" ? (
              <CheckCircle2 size={20} />
            ) : (
              <CircleAlert size={20} />
            )
          ) : (
            <LoaderCircle size={20} className="payment-spin" />
          )}
          <span>
            <strong>{heading}</strong>
            <small>
              {review
                ? `${displayUnits(review.amount_units, review.token_decimals)} ${review.token_symbol} · `
                : ""}
              {settled ? "View receipt and balance" : "View payment status"}
            </small>
          </span>
          <ArrowRight size={16} />
        </button>
      )}
    </PaymentContext.Provider>
  );
}
