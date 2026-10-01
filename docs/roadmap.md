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
- A live Ethereum Sepolia deployment using Circle test USDC.
- A completed on-chain deposit and settlement with Etherscan proof.
- Deterministic fraud rules that remain authoritative if the optional LLM
  fails.
- Simulation and Sepolia modes.
- Browser-wallet approval and deposit flow.
- Four-page responsive interface with live payment updates and proof links.
- Locked dependencies, CI, backend tests, and contract tests.

## Critical gaps

### Intent is not available to live risk analysis

The frontend hashes the payment memo, while the chain listener creates a
generic description. The backend therefore cannot verify or assess the real
purchase intent.

Create a signed intent envelope containing the payment ID, parties, amount,
token, purpose, service or SKU, mandate, expiry, nonce, and metadata hash. The
backend must verify the signature and bind the envelope to the on-chain
`metadataHash`.

### The flow is not yet autonomous

The guided chat is scripted, and a human still signs every wallet transaction.
Build one real buyer agent and one real seller agent. The buyer should discover
an offer, verify that it fits a signed budget mandate, pay without additional
approval when allowed, receive work, and let Paradime settle or recall.

### Identity and reputation are local assertions

The current registry is a local database with manually assigned statuses and
trust scores. Integrate ERC-8004 identity, reputation, and validation data.
Require wallet ownership signatures and optionally verify domains, MCP
endpoints, or other advertised services.

### Risk explanations are not authoritative

The frontend currently derives displayed signal contributions from presentation
formulas. Persist the actual contribution, evidence, weight, and policy version
for every risk signal and render those values directly.

### Chain processing is not durable

- The event cursor is held in memory and can miss deposits after a long outage.
- Resolution events are not independently ingested.
- A transient resolution error permanently marks a payment failed.
- There is no reorganization handling or chain-to-database reconciliation.

Persist the finalized block cursor and block hash, ingest all escrow events,
classify retryable errors, add a durable retry queue, monitor pending
transactions, and continuously reconcile database state with the contract.

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

- Signed intent envelope bound to `metadataHash`
- Persisted risk-signal contributions
- BigInt-safe amount formatting
- Durable event cursor and complete event ingestion
- Resolution retries and on-chain reconciliation
- Redeployed and source-verified `ParadimeEscrow`

### Week 2: Complete one real autonomous purchase

- Buyer agent with a signed spending mandate
- Seller compute agent exposed through MCP
- One MPP or x402 payment adapter
- Session key or constrained agent wallet
- No additional human signature below the authorized limit

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
