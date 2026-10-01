# Paradime API

FastAPI service for agent registry checks, deterministic and LLM-assisted fraud
scoring, Sepolia event ingestion, autonomous escrow resolution, signed spending
mandates, an x402-aware buyer, and an MCP seller compute tool.

In simulation mode, exercise the complete autonomous loop without a wallet:

```bash
curl -sS http://localhost:8000/api/autonomous/demo \
  -H 'content-type: application/json' \
  -d '{"prompt":"Classify this trusted and safe compute result","budget_units":"3000000"}'
```

The response links the mandate, x402 challenge and delegate-signed payload,
Paradime payment, and seller result. `POST /mcp/seller` exposes MCP
`initialize`, `tools/list`, and `tools/call`. See the repository root README for
the signed-mandate and Sepolia configuration boundaries.
