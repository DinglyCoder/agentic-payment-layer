# Paradime agent guide

This file is project-specific context for coding agents. The root `README.md`
is the operator-facing setup guide; `docs/architecture.md` explains the trust
model; `handoff.md` records completed work and the current handoff state.

## Product boundary

Paradime is a hackathon prototype for reversible AI-agent-to-AI-agent ERC-20
stablecoin payments on Ethereum Sepolia. It acts as the identity,
fraud-detection, and arbitration layer. It is not audited or production payment
infrastructure.

Keep two modes working:

- Simulation mode is the default. It needs no wallet, RPC endpoint, or Claude
  key and powers the interactive dashboard demo.
- Sepolia mode ingests escrow events and signs arbitration transactions. It is
  enabled only when all chain settings are present.

Do not replace the stablecoin escrow with native ETH. The configured ERC-20 is
immutable per deployment, and amounts remain integer base units everywhere
except at API/UI boundaries.

## Core architecture

### Smart contract (`contracts/`)

`ParadimeEscrow.sol` is the source of truth for settlement invariants:

- `deposit` pulls the immutable ERC-20 with `SafeERC20`, rejects empty,
  self-directed, and duplicate payments, and starts the 30-second window.
- `recallPayment` is arbitrator-only and is valid through the recall deadline.
- `executePayment` is arbitrator-only and is valid only after that deadline.
- `recoverExpiredPayment` lets only the sender recover an unresolved payment
  one day after the recall deadline.
- State changes precede token transfers and every token-moving entry point is
  non-reentrant.

If the contract event or callable resolution functions change, update
`backend/app/contract_abi.json` in the same commit. Keep boundary and
authorization tests in `contracts/test/ParadimeEscrow.ts`.

### Backend (`backend/`)

- `app/main.py`: FastAPI lifespan, dependency wiring, listener startup, CORS,
  and `/ws/payments`.
- `app/api.py`: health, payment, agent, statistics, and simulation endpoints.
- `app/service.py`: `PaymentProcessor` owns the transaction lifecycle.
  `process_deposit` is the real-chain entry point, `create_demo` is the
  credential-free equivalent, `_assess` persists the fraud decision,
  `settle_due` finds approved payments after their window, and `_resolve`
  submits the arbitration transaction.
- `app/fraud.py`: `FraudEngine.score` combines registry, amount, and recent
  velocity checks with an optional Claude assessment. The deterministic score
  is a floor: an LLM response may increase it but must never reduce it. LLM
  failure must leave deterministic controls operational.
- `app/blockchain.py`: `EscrowChain.listen` polls confirmed Sepolia logs and
  `resolve` serializes signer nonces while sending execute/recall calls. Use
  the latest Sepolia block timestamp—not the host clock—when deciding whether
  a payment is ready for post-window execution.
- `app/models.py`: SQLAlchemy persistence and state enums. `payment_id` is both
  the on-chain identifier and the ingestion idempotency key.
- `app/websocket.py`: in-process dashboard fanout after persisted transitions.

Store wallet addresses in lowercase in the database. Keep transaction and
payment identifiers as `0x`-prefixed 32-byte hex. SQLite drops timezone
metadata, so API schemas must continue marking stored datetimes as UTC. Commit
database state before broadcasting it.

### Frontend (`frontend/`)

`src/api.ts` owns HTTP/WebSocket transport and reconnect behavior.
`src/App.tsx` owns the landing, payment, dashboard, and agent-repository routes,
dashboard state, payment replacement by `payment_id`, agent labels, and risk
details. `src/wallet.ts` owns browser-wallet connection, Sepolia validation,
USDC approval, and escrow deposits. `src/types.ts` mirrors backend response
schemas. When an API field changes, update all affected boundaries together.

The dashboard must remain usable with an empty payment list, during API/WebSocket
failure, and on mobile widths. Do not add wallet requirements to simulation
mode.

## Required verification

Use the locked dependency managers already present: `uv` for Python and `npm`
for both Node workspaces.

```bash
make test
make format
```

For a focused change, run the relevant commands directly:

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd contracts && npm run check && npm test
cd frontend && npm run lint && npm run build
```

Contract timing, authorization, replay, refund, and token-balance behavior need
tests. Fraud-policy changes need tests for verified, unknown/watchlisted, amount,
and velocity paths as applicable. API changes need request/response coverage.

## Configuration and security

- Never commit `.env` files, keys, tokens, RPC credentials, generated database
  files, contract artifacts, or frontend build output.
- Store real durable secrets only in SOPS-encrypted files under `secrets/` and
  invoke consumers with `with-secrets FILE... -- COMMAND`.
- `ARBITRATOR_PRIVATE_KEY` must match the contract's current arbitrator.
- The current Sepolia deployment is
  `0xb1248BabB341605552f228f12BcB2EE68510Ddd5`; its immutable payment token is
  Circle test USDC at `0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238`.
- The encrypted workstation configuration is `secrets/sepolia.env`. Do not
  replace it with a plaintext environment file.
- Sepolia mode must validate chain ID `11155111` and deployed bytecode before
  starting the listener.
- The configured token's decimals must match `STABLECOIN_DECIMALS`; the default
  fraud thresholds assume six decimals.
- Treat all dashboard and on-chain descriptions as untrusted input. Do not put
  free-form metadata into system prompts or logs without bounding it.

## Known prototype limits

The service uses SQLite, an in-process WebSocket manager, one polling process,
one arbitration signer, and a single immutable stablecoin per contract. There
are no schema migrations, durable work queue, multisig/HSM integration, or
formal contract audit. Preserve these limitations in documentation unless a
change actually removes them.
