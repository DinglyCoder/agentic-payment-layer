# Paradime — Escrow for AI agents that pay each other

AI agents are about to spend money on their own. What stops a rogue agent from taking the payment and disappearing?

Paradime is escrow for autonomous agent-to-agent payments in stablecoins. A buyer agent locks payment on-chain, a fraud engine gets 30 seconds to recall it, and the money only releases if the work checks out — with arbitration and refunds if it doesn't.

Honorable Mention, Visa Intern Hackathon

## Try it in 30 seconds — no wallet, no keys

Run this command:

    ./demo --simulation

That opens a live dashboard where you can run the full flow: a buyer agent discovers a seller, negotiates via x402, pays into escrow, and settles — or gets recalled on the watchlist, rejected over budget, or blocked on replay.

## What it does

- **On-chain escrow (Solidity):** 30-second fraud recall, arbitrator-only resolution, replay + reentrancy protection, sender escape hatch
- **Fraud engine (FastAPI):** registry, amount, and velocity rules + optional Claude risk assessment — fails closed if Claude is down
- **Signed intent:** the buyer signs the full purchase intent; the escrow commits its hash, so the backend can't screen a substituted memo
- **Autonomous purchase:** an owner-signed budget mandate lets a buyer agent pay without a second owner signature
- **Live dashboard (React/Vite):** real-time payments over WebSocket, with Etherscan links on Sepolia

## How a payment flows

Buyer agent → signed intent → fraud check → deposit into escrow → 30s recall window → execute (seller paid) or recall (buyer refunded)

## Real Sepolia demo

`./demo` runs the same flow on Sepolia with real Circle test USDC. Full setup is in `docs/` — start with simulation first.

## Repository layout

    contracts/   Solidity escrow, Hardhat config, deployment, and unit tests
    backend/     FastAPI service, fraud engine, chain listener, and API tests
    frontend/    React/Vite real-time operations dashboard
    docs/        Architecture and threat-model notes

## License

MIT.
