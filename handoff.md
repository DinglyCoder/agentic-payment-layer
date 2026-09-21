# Project handoff

This is the durable, human-readable history and current-state note for Paradime.
Keep entries newest first. Record functional commits, verification,
deployment state, and any follow-up that materially affects the next agent.
Documentation-only bookkeeping remains available in `git log` and does not
need a recursive entry in this file.

## Current state — 2026-09-21

- Branch: `main`
- Remote: `https://github.com/DinglyCoder/agentic-payment-layer.git`
- Product name: Paradime. Authored project references to the previous brand were
  removed; the outer local workspace directory retains its existing name.
- Local modes: simulation and live Sepolia flows are both implemented. The
  four frontend routes are `/`, `/pay`, `/dashboard`, and `/agents`.
- Sepolia escrow: `0xb1248BabB341605552f228f12BcB2EE68510Ddd5` with Circle
  test USDC `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238` and arbitrator
  `0x26e220eb8bDeA0cc238e166165e79742bE526B3D`.
- The configured deployment predates the source-level `ParadimeEscrow` rename.
  It is ABI-compatible but is not source-verified under the Paradime name.
- Live proof payment: 1 USDC deposited in transaction
  `0xd42af319d8d0b90f637882448f63045b180f1c0ad5287b006844ab1f4349d818`
  and executed in transaction
  `0x11ef1236277c8694bb9f90fc27abe173be6fd3671ff029a9268fea6ade58bd33`.
- Runtime chain configuration and wallet keys are SOPS-encrypted in
  `secrets/sepolia.env`; no plaintext secret file is required.
- Claude scoring: implemented but optional; no API key is stored in the repo.
- Local verification for `652356b`: backend 5 tests, contracts 5 tests,
  frontend production build, Ruff, Solidity/TypeScript checks, and ESLint all
  passed.

## Functional commit history

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

1. Redeploy and verify the renamed `ParadimeEscrow` source on Etherscan if
   on-chain source branding matters; otherwise retain the compatible deployment.
2. Add automated browser coverage for wallet connection, approval, deposit,
   dashboard ingestion, and resolution proof rendering.
3. Replace SQLite and in-process scheduling with durable production components
   before any multi-instance deployment.
4. Add HSM/MPC or multisig signing, database migrations, RPC failover, metrics,
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
