# Architecture and trust boundaries

## Resolution state machine

```text
None --deposit--> Pending --arbitrator recall, <= 30s--> Recalled
                         `--arbitrator execute, > 30s--> Executed
                         `--sender recovery, > 1 day--> Recalled
```

The contract checks the state and time boundary independently of the backend.
The backend therefore cannot settle an approved transfer early, recall after
the fraud window, reuse an ID, or resolve an escrow twice.

## Service pipeline

1. The payer signs a canonical intent envelope. Paradime verifies wallet
   ownership and stores the envelope before its hash is committed as the
   escrow deposit's `metadataHash`.
2. `EscrowChain` polls confirmed deposit and resolution logs from a persisted
   block/hash cursor. A database primary key makes ingestion idempotent and a
   hash mismatch rewinds the cursor across the confirmation window.
3. `PaymentProcessor` rejects missing, expired, replayed, or mismatched intents,
   then records a valid deposit before invoking external services.
4. `FraudEngine` looks up both wallets, queries recent sender velocity, and
   applies amount policy. It optionally asks Claude for a bounded 0–100 signal.
   Every contribution, its weight, evidence, and policy version is persisted.
5. The final score can only stay at or increase above the deterministic rule
   score. At 70 or above the signer recalls immediately; otherwise the payment
   is queued until the contract's recall deadline passes.
6. Resolution failures retain the intended decision and retry with bounded
   exponential backoff. Resolution events and periodic contract reads reconcile
   database state after restarts or ambiguous transaction outcomes.
7. Every persisted state transition is broadcast to dashboard clients.

## Autonomous purchase pipeline

1. The owner signs a canonical spending mandate naming the dedicated buyer
   wallet, token, seller, service, per-payment ceiling, total budget, nonce, and
   expiry. Paradime verifies the signature and rejects replayed nonces.
2. The buyer discovers the seller's `analyze_text` tool through MCP
   `tools/list`, calls it without payment, and receives the x402 v2
   `PaymentRequired` object in both structured and text forms.
3. Before signing anything, the buyer matches the quote against every mandate
   constraint and reserves the quoted base-unit amount under an in-process
   serialization lock.
4. In simulation it creates an equivalent scored payment. In Sepolia mode the
   dedicated buyer signs the intent, registers it, approves test USDC if needed,
   deposits into escrow, and waits for the listener and arbitrator to reach a
   terminal state.
5. Only an executed payment is attached to the retried MCP `tools/call` in
   `_meta["x402/payment"]`. The seller verifies the delegate signature and the
   persisted payment's parties, amount, purchase, and quoted terms before
   returning the compute result.

This is an x402 v2 transport adapter with a custom `paradime-escrow` scheme.
It intentionally does not claim to be the EIP-3009 `exact` scheme. The session
wallet is constrained by Paradime's application policy; possession of its raw
key is still unrestricted at the chain layer.

## Threat model

| Threat | Prototype control | Production follow-up |
|---|---|---|
| Signer compromise | Dedicated arbitrator role; sender escape hatch | HSM/MPC signer, rotation delay, multisig pause |
| Duplicate/replayed deposit | On-chain mapping + DB primary key | Cross-chain domain separator |
| Reentrancy | Checks-effects-interactions + lock | External audit and fuzzing |
| RPC reorganization | Confirmation depth, persisted block hash, bounded rewind | Redundant RPCs and finalized-block tracking |
| LLM outage or malformed output | Deterministic rules remain authoritative | Circuit breakers and provider telemetry |
| LLM prompt injection in metadata | Structured, bounded facts only | Classifier isolation and signed service schemas |
| Backend restart near deadline | Persisted cursor and DB-backed retry state are rescanned | Durable job queue and active/standby signer |
| Mandate replay or over-spend | Canonical owner signature, unique nonce, per-call and total limits, serialized budget reservation | Database row locking, authenticated tenants, on-chain smart-account permissions |
| Paid tool replay or substitution | Purchase-bound delegate signature and exact payment/quote matching | Standard facilitator integration and protocol conformance suite |
| Buyer session-key compromise | Dedicated wallet with application-enforced mandate limits | HSM/MPC or smart-account session keys with on-chain constraints |
| Stuck funds | Sender recovery after one day | Policy-specific timeout and formal verification |

## Stablecoin policy

Each deployment accepts one immutable ERC-20 token address, which prevents an
agent from substituting a malicious asset per payment. The payer approves the
escrow and `deposit` pulls integer token base units with `SafeERC20`. Token
decimal handling stays at the API edge; the contract never uses floating-point
or price data.
