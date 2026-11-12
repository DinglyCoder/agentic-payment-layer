# Paradime API

FastAPI service for agent registry checks, deterministic and LLM-assisted fraud
scoring, Sepolia event ingestion, autonomous escrow resolution, signed spending
mandates, an x402-aware buyer, and an MCP seller compute tool.

Run `./demo` from the repository root for the real Sepolia playground. It loads
SOPS-encrypted configuration through `with-secrets`, starts both applications,
and preserves payment records. `./demo --simulation` explicitly selects offline
simulation instead.

The browser terminal and local CLI share `POST /api/demo/commands`. Sepolia is
the default; each purchase creates a persisted operation and publishes approval,
deposit, and resolution links. `POST /api/demo/scenarios/{scenario}` accepts
`purchase`, `trusted`, `watchlist`, `budget`, or `replay` and returns an operation.
Poll `GET /api/demo/operations/{operation_id}` to observe progress and result.
A repeated request ID returns the same operation without another payment.
Budget and replay rejections happen before any transaction is sent.

`POST /api/payments/preview` provides read-only confirmation details for direct
payments, scenarios, and browser-terminal commands. It returns the actual charge,
authorization budget, RPC-backed USDC/ETH balances, and submission blockers.
Command previews share the execution parser; read-only commands return `null`.
Previews never create mandates, reserve budget, sign intents, or submit payments.
They are UI checks, not an authorization primitive: server-side spending limits
and signed-intent validation still enforce the actual payment path. The managed
wallet status endpoint also includes `native_balance_wei` for Sepolia gas.

The original credential-free autonomous endpoint remains available when the
main service runs in simulation mode:

```bash
curl -sS http://localhost:8000/api/autonomous/demo \
  -H 'content-type: application/json' \
  -d '{"prompt":"Classify this trusted and safe compute result","budget_units":"3000000"}'
```

`POST /mcp/seller` exposes MCP `initialize`, `tools/list`, and `tools/call`.
The x402 adapter uses the custom `paradime-escrow` scheme. The main dedicated
buyer, when configured, remains separate from the explicitly enabled managed
payer used by the guided Sepolia workspace. See the root README and architecture
notes for signer ownership, testnet finality, and prototype limits.
