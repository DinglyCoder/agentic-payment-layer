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

1. `EscrowChain` polls confirmed `PaymentDeposited` logs from a configurable
   start block. A database primary key makes ingestion idempotent.
2. `PaymentProcessor` records the deposit before invoking external services.
3. `FraudEngine` looks up both wallets, queries recent sender velocity, and
   applies amount policy. It optionally asks Claude for a bounded 0–100 signal.
4. The final score can only stay at or increase above the deterministic rule
   score. At 70 or above the signer recalls immediately; otherwise the payment
   is queued until the contract's recall deadline passes.
5. Every persisted state transition is broadcast to dashboard clients.

## Threat model

| Threat | Prototype control | Production follow-up |
|---|---|---|
| Signer compromise | Dedicated arbitrator role; sender escape hatch | HSM/MPC signer, rotation delay, multisig pause |
| Duplicate/replayed deposit | On-chain mapping + DB primary key | Cross-chain domain separator |
| Reentrancy | Checks-effects-interactions + lock | External audit and fuzzing |
| RPC reorganization | Configurable confirmation depth | Redundant RPCs and finalized-block tracking |
| LLM outage or malformed output | Deterministic rules remain authoritative | Circuit breakers and provider telemetry |
| LLM prompt injection in metadata | Structured, bounded facts only | Classifier isolation and signed service schemas |
| Backend restart near deadline | DB-backed approved state is rescanned | Durable job queue and active/standby signer |
| Stuck funds | Sender recovery after one day | Policy-specific timeout and formal verification |

## Stablecoin policy

Each deployment accepts one immutable ERC-20 token address, which prevents an
agent from substituting a malicious asset per payment. The payer approves the
escrow and `deposit` pulls integer token base units with `SafeERC20`. Token
decimal handling stays at the API edge; the contract never uses floating-point
or price data.
