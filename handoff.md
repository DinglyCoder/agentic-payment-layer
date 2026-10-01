# Project handoff

This is the durable, human-readable history and current-state note for Paradime.
Keep entries newest first. Record functional commits, verification,
deployment state, and any follow-up that materially affects the next agent.
Documentation-only bookkeeping remains available in `git log` and does not
need a recursive entry in this file.

## Current state — 2026-10-01

- Branch: `main`
- Remote: `https://github.com/DinglyCoder/agentic-payment-layer.git`
- Product name: Paradime. Authored project references to the previous brand were
  removed; the outer local workspace directory retains its existing name.
- Local modes: simulation and live Sepolia flows are both implemented. The
  four frontend routes are `/`, `/pay`, `/dashboard`, and `/agents`.
- Week 1 reliability work is implemented: signed
  intent envelopes, persisted risk-signal evidence, BigInt-safe amounts, a
  durable block/hash cursor, resolution-event ingestion and retries, and
  contract-state reconciliation.
- Week 2's autonomous vertical slice is implemented: an owner-signed structured
  budget mandate authorizes a dedicated buyer wallet, which discovers an MCP
  seller tool, negotiates an x402 v2 challenge, pays through Paradime without a
  second owner signature, and receives deterministic compute after execution.
- Simulation mode completes that entire loop locally. The Sepolia buyer signing,
  approval, deposit, and terminal-state wait path is implemented but was not
  funded or exercised; it requires encrypted `AUTONOMOUS_BUYER_PRIVATE_KEY` and
  an explicit `SELLER_ADDRESS`.
- Live Sepolia deposits now require a pre-registered sender-signed intent whose
  canonical hash matches on-chain `metadataHash`. Missing, expired, replayed,
  or mismatched intent fails closed to a recall decision.
- Sepolia escrow: `0xb1248BabB341605552f228f12BcB2EE68510Ddd5` with Circle
  test USDC `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238` and arbitrator
  `0x26e220eb8bDeA0cc238e166165e79742bE526B3D`.
- The configured deployment predates the source-level `ParadimeEscrow` rename.
  It is ABI-compatible but is not source-verified under the Paradime name.
- A production-profile deployment and source-verification workflow is present,
  but no renamed contract was deployed during the Week 1 implementation. The
  attempted deployment was rejected pending explicit approval for the
  irreversible Sepolia gas spend; `secrets/sepolia.env` also has no
  `ETHERSCAN_API_KEY`, so use Sourcify or add an encrypted key before deploying.
- Live proof payment: 1 USDC deposited in transaction
  `0xd42af319d8d0b90f637882448f63045b180f1c0ad5287b006844ab1f4349d818`
  and executed in transaction
  `0x11ef1236277c8694bb9f90fc27abe173be6fd3671ff029a9268fea6ade58bd33`.
- Runtime chain configuration and wallet keys are SOPS-encrypted in
  `secrets/sepolia.env`; no plaintext secret file is required.
- Claude scoring: implemented but optional; no API key is stored in the repo.
- Latest local verification: backend 10 tests, contracts 5 tests, frontend
  production build, Ruff, Solidity/TypeScript checks, and ESLint all passed.

## Functional commit history

### This commit — Complete one autonomous purchase (2026-10-01)

- Added canonical owner-signed spending mandates with delegate, asset,
  counterparty, service, per-payment, total-budget, nonce, and expiry controls.
- Added a dedicated buyer session wallet that discovers and invokes a paid MCP
  tool, reserves budget before payment, and signs without another owner prompt.
- Added an x402 v2 MCP adapter with a custom `paradime-escrow` scheme and a
  seller that verifies the executed payment, quote, purchase, and delegate
  signature before releasing work.
- Added persisted autonomous-purchase audit records, a credential-free complete
  simulation endpoint, and an optional Sepolia approval/deposit path.
- Added API coverage for the complete flow, budget exhaustion, MCP discovery,
  and the x402 payment-required response.

Verification for the working tree:

- Backend: 10 tests passed; Ruff lint and format passed.
- Contracts: 5 tests passed; Solidity compilation and TypeScript checks passed.
- Frontend: ESLint and the Vite production build passed.

No Sepolia transaction, deployment, secret update, or test-token spend occurred.
The dedicated buyer key is constrained by application policy only; production
custody still needs authenticated tenants and HSM/MPC or smart-account controls.

### `9519913` — Implement roadmap Week 1 reliability work (2026-10-01)

- Added canonical signed intent envelopes covering payment ID, wallets, base-unit
  amount, token, purpose, service/SKU, mandate, expiry, and nonce. The backend
  verifies wallet ownership and binds each envelope to the deposit's
  `metadataHash`; invalid binding deterministically triggers recall.
- Persisted authoritative risk-signal contributions, weights, evidence, and
  policy version, and replaced the dashboard's synthetic contribution formulas.
- Replaced unsafe frontend amount conversion with `BigInt` formatting.
- Added a database-backed block/hash cursor, bounded reorg rewind, ingestion of
  deposit/execution/recall events, retryable resolution state with exponential
  backoff, and contract-to-database reconciliation.
- Added additive startup upgrades for existing SQLite payment tables, expanded
  the backend ABI, updated cross-boundary types and documentation, and added
  signed-intent tampering and risk-signal tests.
- Added production-profile Sepolia deployment and verification commands. The
  actual renamed deployment and source verification remain pending explicit
  authorization and an available verification provider credential/path.

Verification for the working tree:

- Backend: 6 tests passed; Ruff lint and format passed.
- Contracts: 5 tests passed; Solidity compilation and TypeScript checks passed.
- Frontend: ESLint and the Vite production build passed.

### `652356b` — Launch Paradime Sepolia payment experience (2026-09-21)

- Rebuilt the frontend as a polished four-page product experience with direct
  and guided-chat payments, a risk operations dashboard, an agent repository,
  responsive layouts, explicit simulation labeling, and Sepolia proof links.
- Added browser-wallet connection, chain validation, Circle test USDC approval,
  escrow deposits, and publicly verifiable transaction success states.
- Hardened Sepolia startup validation around chain ID, bytecode, immutable token,
  token decimals, and arbitrator-key ownership. Live wallet addresses are added
  to the agent registry as unknown identities when deposits are ingested.
- Switched settlement deadline decisions to the latest block timestamp to avoid
  host-clock skew at the contract's recall boundary.
- Added a SOPS-encrypted Sepolia runtime configuration and deployed the live
  escrow used by the proof payment recorded above.
- Renamed the product and authored implementation to Paradime, including
  `ParadimeEscrow`, package metadata, UI copy, API metadata, and documentation.

Verification at commit:

- Backend: 5 tests passed; Ruff lint and format passed.
- Contracts: 5 tests passed; Solidity compilation and TypeScript checks passed.
- Frontend: ESLint and the Vite production build passed.

### `65f053f` — Build the agentic payment trust layer (2026-09-11)

Recreated the hackathon project as a full-stack monorepo and pushed it to
`main`.

- Added a Hardhat 3 Solidity escrow for an immutable ERC-20 stablecoin with a
  30-second arbitrator recall window, post-window execution, replay and
  reentrancy protection, arbitrator rotation, and a one-day sender escape hatch.
- Added contract deployment configuration, a six-decimal mock stablecoin, and
  five passing tests covering deposit, authorization, timing, duplicate IDs,
  double resolution, settlement balances, and abandoned-payment recovery.
- Added a FastAPI/SQLAlchemy service with deterministic registry, amount, and
  velocity rules; optional Claude scoring; async Sepolia log polling; autonomous
  execute/recall signing; idempotent persistence; and WebSocket events.
- Added a responsive React/Vite trust-operations dashboard with seeded data,
  live payment replacement, risk explanations, status metrics, and an
  interactive credential-free payment simulator.
- Added lockfiles, environment templates, root Make targets, architecture and
  threat-model documentation, MIT license, and three-job GitHub Actions CI.

Verification at commit:

- Backend: 5 tests passed; Ruff lint and format passed.
- Contracts: 5 tests passed; Solidity compilation and TypeScript checks passed.
- Frontend: ESLint and the Vite production build passed.
- GitHub Actions run `34659791887`: all three jobs passed.

## Next useful milestones

These are not committed promises; choose them only when requested or when they
become part of the active task.

1. With explicit approval, deploy the renamed `ParadimeEscrow`, source-verify
   it through Etherscan or Sourcify, update the encrypted contract address, and
   run a signed-intent deposit through resolution before describing it as live.
2. Add independently hosted seller discovery and replace the raw dedicated
   buyer key with authenticated, hardware-backed or on-chain-constrained session
   authority before treating autonomous Sepolia purchases as production-safe.
3. Add integration coverage for cursor restart/reorg behavior, resolution
   retries, reconciliation, and invalid intent/deposit binding.
4. Add automated browser coverage for wallet intent and mandate signing, registration,
   approval, deposit, dashboard ingestion, and resolution proof rendering.
5. Replace SQLite and in-process scheduling with durable production components
   before any multi-instance deployment.
6. Add HSM/MPC or multisig signing, database migrations, RPC failover, metrics,
   and a contract security audit before considering real-value use.

## Handoff checklist

Before ending a future implementation session:

- Update this file with the functional commit hash, outcome, verification, and
  remaining deployment state.
- Keep `AGENTS.md`, `README.md`, the ABI, and architecture notes consistent with
  code behavior.
- Run the relevant locked tests and formatters.
- Confirm `git status` contains no secrets, generated state, or unrelated user
  changes.
