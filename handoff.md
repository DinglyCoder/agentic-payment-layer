# Project handoff

This is the durable, human-readable history and current-state note for Paradime.
Keep entries newest first. Record functional commits, verification,
deployment state, and any follow-up that materially affects the next agent.
Documentation-only bookkeeping remains available in `git log` and does not
need a recursive entry in this file.

## Current state — 2026-11-09

- Branch: `main`
- Remote: `https://github.com/DinglyCoder/agentic-payment-layer.git`
- Product name: Paradime. Authored project references to the previous brand were
  removed; the outer local workspace directory retains its existing name.
- Local modes: simulation and live Sepolia flows are both implemented. The
  frontend routes are `/`, `/demo`, `/pay`, `/dashboard`, and `/agents`.
- `./demo` (also `make demo`) defaults to actual Sepolia payments, loads
  `secrets/sepolia.env` through `with-secrets`, and opens `/demo`. Node.js 22+,
  npm, uv, and workstation SOPS access are required. Both server process groups
  are cleaned up on exit. Sepolia records persist in `backend/paradime-demo.db`.
  Only `./demo --simulation` uses credential-free, temporary offline data.
- The playground exposes four guided scenarios, signed mandate and risk
  inspection, x402 messages, downloadable records, and an in-browser CLI.
  Guided and CLI purchases publish actual approval, deposit, and resolution
  transaction links. Missing configuration never silently creates mock payments.
  Budget and replay rejections occur before spending and have no fabricated link.
  `./paradime` defaults to Sepolia; `--simulation` explicitly selects offline data. The
  protection lab is explicitly a client-side concept with an illustrative
  premium and mock reserve/payout, not implemented underwriting or options pricing.
- The header environment switch changes the payment console, dashboard data,
  proof links, and wallet requirements between Simulation and Testnet. Testnet
  is selectable only when the backend reports a configured Sepolia listener;
  `TESTNET_ENABLED=true` enables dual-mode startup with Simulation as default.
- Testnet payments offer an application-managed demo payer alongside the
  existing browser-wallet path. The managed payer uses encrypted
  `DEPLOYER_PRIVATE_KEY`, is gated by `MANAGED_DEMO_WALLET_ENABLED=true`, and
  enforces per-payment and per-process-session test-USDC limits.
- Week 1 reliability work is implemented: signed
  intent envelopes, persisted risk-signal evidence, BigInt-safe amounts, a
  durable block/hash cursor, resolution-event ingestion and retries, and
  contract-state reconciliation.
- Week 2's autonomous vertical slice is implemented: an owner-signed structured
  budget mandate authorizes a dedicated buyer wallet, which discovers an MCP
  seller tool, negotiates an x402 v2 challenge, pays through Paradime without a
  second owner signature, and receives deterministic compute after execution.
- Both simulation and managed-payer Sepolia purchases complete the autonomous
  loop. The optional dedicated `AUTONOMOUS_BUYER_PRIVATE_KEY` path remains
  separate and was not funded. The guided workspace uses the explicitly enabled
  encrypted demo payer; without `SELLER_ADDRESS`, its seller settles to the
  arbitration wallet. This does not establish independent seller operation.
- Persisted `DemoOperation` records expose progress and actual transaction
  hashes. Repeated request IDs do not create another payment. `./paradime resume
  OPERATION_ID` and the UI recovery button finish already-paid work without a
  second deposit. Interrupted work is never automatically charged again.
- The launcher observes mined blocks with `CHAIN_CONFIRMATIONS=0` so recall can
  fit the existing 30-second window. This is not finalized-block protection.
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
- Latest local verification: backend 28 tests, contracts 6 tests, frontend
  production build, Ruff, Solidity/TypeScript checks, and ESLint all passed.
  Headless Chrome exercised actual guided and browser-terminal purchases, a
  real refund, no-spend policy rejections, explorer links, receipt download,
  browser-wallet entry, and 390px layouts. External wallet signing still requires
  the user's wallet extension and confirmation; QA used the managed payer.

## Functional commit history

### Working tree — Payment console UI polish (2026-11-09)

- Reworked all five screens around compact navigation, neutral surfaces, system
  fonts, readable forms and tables, and restrained status colors. The overview
  shows an actual record from the selected environment instead of a fabricated
  payment illustration.
- Added working ledger search, status filtering, filtered JSON export, and
  keyboard-accessible payment selection. The risk panel follows the visible
  selection and displays pending assessments without inventing a zero score.
- Added reusable clipboard controls for commands, wallet addresses, operation
  IDs, and transaction hashes. Agent payment actions now carry the selected
  recipient into checkout, including while backend configuration loads.
- Preserved real Sepolia payment paths, the shared CLI dispatcher, persistent
  receipts, and visibly labeled offline simulation and protection concepts.
- Verification: frontend ESLint and production build passed. Installed Chrome
  exercised search, filters, export, copy feedback, scenario execution, policy
  and x402 details, receipt downloads, terminal commands, and keyboard tabs in
  an isolated offline environment. All five routes passed layout checks at
  320, 390, 768, and 1024 pixels without document overflow or JS exceptions.
  A separate read-only check against the running Sepolia service verified real
  wallet data, existing deposit/settlement links, mobile receipt layouts, and
  browser-wallet entry. This UI pass submitted no blockchain payments.

### Working tree — Real Sepolia demo and transaction evidence (2026-11-09)

- Added a one-command launcher with encrypted Sepolia configuration, persistent
  audit records, explicit offline simulation, port selection, and process teardown.
- Added the `/demo` guided playground for successful autonomous purchases,
  watchlist recalls, budget rejection, and signed-mandate replay rejection.
- Added bounded Sepolia CLI commands shared by the browser terminal and
  `./paradime`, alongside inspectable authority, policy evidence, x402 payloads,
  seller output, and downloadable demo records.
- Added a visibly conceptual protection lab with adjustable leverage and price
  shocks. Its fixed illustrative premium does not claim financial pricing.
- Added persisted operations, idempotent request handling, submitted-transaction
  callbacks, and explicit recovery of paid work without another deposit.
- Live verification exposed and fixed the missing backend `deposit` ABI entry
  and SQLite timezone comparison in scheduled settlement. Tests now compare
  the backend ABI with compiled contract signatures and exercise reloaded
  SQLite deadlines, concurrent retries, and interrupted paid-work recovery.

Verification: `make test` and `make format` passed using temporary tool caches.
Three 1-test-USDC purchases executed and one 1-test-USDC payment was recalled.
Mined receipts, escrow storage, metadata binding, and actual ERC-20 transfer logs
were independently checked through RPC. The original CLI purchase was recovered
after restart without another deposit. No contract deployment or encrypted
configuration update occurred.

Public transaction evidence (deposit → resolution):

- Local CLI: `0xe42d9f9bd546dec140ed8b34165990dddbde7ed5c87b061cbd39698e9b0617f4`
  → `0xfdacc9d710de8e1aa3fa95813226524079dc2815c7ab7f438c095eb2ea767b74`
- Guided purchase: `0xa1e1336334b83bd80b6e1bb2ecc7c1bcb03ad436e9d49a023df8e88e61bb6d36`
  → `0x8b152a9a32059d4e785e2dff5640d7d73e424496fc5479a7c08e1370927ad090`
- Guided recall: `0x1f22d1a940c0b2ed1744cd01b9b41e3343e34af1c617a75b95472983cc9bd8db`
  → `0xbf5657670a98433a109bba1fc96dd3ed887bd0b2c84ac096640e22e7553299b5`
- Browser terminal: `0x68bccd8f2f9cbe5d077cf888b6b907c58b6e6febadef104536904ecd0350b394`
  → `0x6592f613d7480faaddc69e903abfab22d76752f82b60e5f46b27d8571c3f25e7`

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
