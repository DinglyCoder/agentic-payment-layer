# Paradime product roadmap

## Product thesis

Paradime should not become another payment rail. It should become the **trust
firewall for machine payments**, verifying identity, authority, intent, risk,
and completed work before autonomous funds settle.

The product should connect existing standards rather than replace them:

```text
MPP or x402 payment challenge
            ↓
AP2 spending mandate
            ↓
ERC-8004 agent identity and reputation
            ↓
Paradime policy and risk evaluation
            ↓
Reversible escrow
            ↓
Signed trust receipt and reputation outcome
```

The core product objects should be:

1. **Mandate:** what the human authorized the agent to do.
2. **Trust Envelope:** what Paradime observed, evaluated, and decided.
3. **Outcome Proof:** what the counterparty delivered and how the funds
   resolved.

## Current strengths

- Working ERC-20 escrow with recall, execution, replay protection, and sender
  recovery.
- Sender-signed intent envelopes bind the payment ID, parties, base-unit amount,
  token, purpose, service/SKU, mandate, expiry, and nonce to the on-chain
  `metadataHash`. Missing, expired, replayed, or mismatched intent fails closed.
- Risk decisions persist their policy version and each signal's actual
  contribution, weight, and bounded evidence for direct dashboard rendering.
- Sepolia ingestion resumes from a database-backed block/hash cursor, ingests
  deposit and resolution events, retries failed resolutions with backoff, and
  reconciles terminal state against the contract.
- Frontend stablecoin formatting remains precise for arbitrarily large base-unit
  values by using `BigInt` rather than JavaScript `Number`.
- A live Ethereum Sepolia deployment using Circle test USDC.
- A completed on-chain deposit and settlement with Etherscan proof.
- Deterministic fraud rules that remain authoritative if the optional LLM
  fails.
- Simulation and Sepolia modes.
- Browser-wallet approval and deposit flow.
- Four-page responsive interface with live payment updates and proof links.
- Locked dependencies, CI, backend tests, and contract tests.

## Critical gaps

### Intent binding and bounded mandate enforcement are implemented

The browser wallet now signs a canonical intent envelope before depositing, and
the backend verifies and stores it before requiring its hash to match the
on-chain `metadataHash`. Live risk analysis receives the signed purpose instead
of a listener-generated generic description.

Week 2 added an independently owner-signed spending mandate covering a dedicated
buyer delegate, token, seller, service, per-payment limit, total budget, nonce,
and expiry. The buyer evaluates and reserves that policy before it signs a
payment. The current dedicated wallet remains application-constrained rather
than an on-chain smart-account session key.

### One autonomous flow is implemented; discovery and custody remain narrow

The buyer now discovers a deterministic seller compute tool over MCP, negotiates
a conforming x402 v2 MCP challenge using the custom `paradime-escrow` scheme,
checks a signed mandate, pays without another owner signature, waits for
Paradime's terminal decision, and receives work only after execution. Simulation
mode proves the complete loop without credentials; the Sepolia signing path is
implemented but has not been funded or exercised live.

Next autonomy work should add multiple independently hosted sellers, discovery
through a shared catalog, authenticated callers, and a smart-account or HSM/MPC
session signer whose constraints do not depend solely on this service.

### Identity and reputation are local assertions

The current registry is a local database with manually assigned statuses and
trust scores. Integrate ERC-8004 identity, reputation, and validation data.
Require wallet ownership signatures and optionally verify domains, MCP
endpoints, or other advertised services.

### Risk explanations are authoritative but policy configuration is static

The backend now persists actual signal contributions, evidence, weights, and a
policy version, and the frontend renders those records directly. Policy values
are still configured globally; named policy configurations, reason codes, and
configuration hashes remain future Trust Envelope and policy-studio work.

### Chain processing has durable recovery but is not production-grade

Implemented in Week 1:

- Persisted next-block and prior-block-hash cursor
- Confirmation-window rewind after a cursor hash mismatch
- Independent deposit, execution, and recall event ingestion
- Database-backed resolution attempts, error state, and exponential backoff
- Continuous terminal-state reconciliation against contract storage

Remaining production work includes finalized-block semantics, explicit
retryable versus permanent error classification, pending-transaction monitoring
and replacement, a general durable job queue, full orphaned-record handling
after deep reorganizations, and redundant RPC providers.

### The contract only models a timed transfer

The current escrow releases funds after a fixed 30-second window. It has no
concept of delivery, evidence, disputes, partial completion, or payment
sessions.

The next contract version should bind a mandate or policy hash to each payment
and support evidence commitments, disputes, milestones, variable policy windows,
batching, protected sessions, two-step role rotation, pausing, and threshold
arbitration.

## Differentiating capabilities

### Trust Envelopes

Every payment should produce a signed, portable record containing:

- Payment, challenge, and transaction identifiers
- Buyer and seller agent identities
- Intent and mandate hashes
- Policy name, version, and configuration hash
- Individual risk signals and evidence
- Decision, reason codes, expiry, and resolver
- Work-evidence commitment
- Deposit and resolution transactions
- Paradime signature

Trust Envelopes should be viewable in the dashboard and exportable as JSON.

### Evidence-gated settlement

Use a richer lifecycle:

```text
Funded → Accepted → Work submitted → Validated → Settled
                    ↘ Disputed → Refunded or settled
```

Start with signed seller receipts and deterministic validation. Later, support
independent validator agents, trusted execution attestations, stake-backed
validation, or zero-knowledge proofs.

### Policy studio

Let users configure:

- Per-payment and daily budgets
- Approved service categories and counterparties
- Minimum identity and reputation thresholds
- Human-approval thresholds
- Required evidence types
- Recall or dispute windows
- Velocity and anomaly limits

The decision view should explain which rules passed or failed instead of only
showing a generic score.

### Payment-backed reputation graph

Build a graph across agents, wallets, operators, domains, services, payments,
disputes, validators, and reputation issuers. Derive reputation from completed
work, recalls, disputes, delivery latency, repeat transactions, and validator
agreement.

### Attack laboratory

Provide reproducible scenarios demonstrating:

- Budget violations
- Unknown or newly rotated wallets
- Coordinated payment rings
- Price manipulation after authorization
- Replayed mandates
- Intent and payment mismatches
- Invalid work submissions
- Abnormal payment velocity

Each scenario should produce an explainable decision and, where applicable, a
real on-chain recall.

### Protected payment sessions

One blockchain transaction per API call is unsuitable for micropayments. Add a
session flow that locks a budget once, increments authorized usage, monitors the
session continuously, settles consumed value, and refunds the remainder.

## Prioritized four-week build

### Week 1: Make the current product truthful and reliable

- [x] Signed intent envelope bound to `metadataHash`
- [x] Persisted risk-signal contributions
- [x] BigInt-safe amount formatting
- [x] Durable event cursor and deposit/resolution event ingestion
- [x] Resolution retries and on-chain reconciliation
- [ ] Redeployed and source-verified `ParadimeEscrow`

The implementation items above landed in commit `9519913`. The configured live
contract remains the earlier ABI-compatible deployment at
`0xb1248BabB341605552f228f12BcB2EE68510Ddd5`; it predates the source-level
Paradime rename and must not be described as source-verified under that name.
Deployment and verification commands are ready, but running them requires
explicit authorization for the Sepolia gas spend and a verification provider
path such as Sourcify or an encrypted Etherscan API key.

### Week 2: Complete one real autonomous purchase

- [x] Buyer agent with a signed spending mandate
- [x] Seller compute agent exposed through MCP
- [x] x402 v2 MCP payment adapter using the `paradime-escrow` scheme
- [x] Dedicated, application-constrained agent wallet
- [x] No additional owner signature below the authorized limit

The local integration test completes the full discovery, quote, mandate,
payment, risk decision, x402 retry, and seller-result loop. Sepolia autonomous
approval and deposit signing are implemented behind
`AUTONOMOUS_BUYER_PRIVATE_KEY`, but no wallet was funded and no live autonomous
purchase was submitted as part of this implementation. Production custody still
requires on-chain smart-account constraints or HSM/MPC policy enforcement.

### Week 3: Close the trust loop

- Seller output commitment
- Independent validator agent
- Evidence-gated settlement
- ERC-8004 identity lookup
- Payment-backed reputation update
- Trust Envelope generation

### Week 4: Build the memorable demonstration

- Policy studio
- Trust Envelope viewer
- Agent and payment relationship graph
- Interactive attack laboratory
- One-click repeatable demo environment
- Automated browser and chain integration tests

## Target demo

1. A user asks a buyer agent to obtain an inference for less than 3 USDC.
2. The user signs a constrained mandate once.
3. The buyer discovers multiple seller agents.
4. Paradime rejects one seller because of identity or coordinated-wallet risk.
5. The selected seller presents an MPP or x402 payment challenge.
6. Paradime verifies authority, identity, price, reputation, and policy.
7. USDC enters reversible escrow.
8. The seller submits the inference result and an evidence commitment.
9. A validator checks the result.
10. Paradime releases payment and records payment-backed reputation.
11. The dashboard displays the complete causal chain and public proofs.
12. A manipulated version of the transaction is replayed and recalled.

## Production work after the differentiated demo

- Authentication, tenant isolation, wallet login, and admin roles
- PostgreSQL, migrations, durable jobs, and an outbox
- HSM, MPC, or multisig signing
- Multiple RPC providers and finalized-block tracking
- Rate limiting, signed webhooks, audit logs, tracing, and alerts
- Contract invariant and fuzz tests
- Browser wallet end-to-end tests
- Protocol conformance and replay tests
- Independent smart-contract audit

## Avoid for now

- Supporting many chains before one complete flow works
- Training a bespoke fraud model
- Adding decorative analytics that are not backed by stored evidence
- Launching a token or arbitration DAO
- Mainnet deployment
- More scripted chat UI without real agent behavior
- Complex zero-knowledge systems before signed intent and evidence work

## Standards to build with

- [ERC-8004: Trustless Agents](https://eips.ethereum.org/EIPS/eip-8004)
- [Google Agent Payments Protocol](https://github.com/google-agentic-commerce/AP2)
- [x402 protocol](https://github.com/x402-foundation/x402)
- [Machine Payments Protocol](https://mpp.dev/)
