# Sepolia demo credentials

`sepolia.env` is SOPS-encrypted to the workstation age key. Never decrypt it
to a file or copy its private keys into `contracts/.env` or `backend/.env`.

Public wallet roles:

- Deployer / demo payer: `0xfB57028cA9eeb5dF953C8bF1285a9a4c172455a0`
- Arbitration signer: `0x26e220eb8bDeA0cc238e166165e79742bE526B3D`

Run the deployment and backend without materializing plaintext secrets:

```bash
cd contracts
with-secrets ../secrets/sepolia.env -- npm run deploy:sepolia

cd ../backend
with-secrets ../secrets/sepolia.env -- uv run uvicorn app.main:app --reload
```

The deployer needs Sepolia ETH for contract deployment and test USDC for the
demo payment. The arbitrator needs Sepolia ETH to execute or recall payments.
