import "dotenv/config";
import { defineConfig } from "hardhat/config";
import hardhatToolboxMochaEthers from "@nomicfoundation/hardhat-toolbox-mocha-ethers";

const sepoliaRpcUrl = process.env.SEPOLIA_RPC_URL;
const deployerPrivateKey = process.env.DEPLOYER_PRIVATE_KEY;

export default defineConfig({
  plugins: [hardhatToolboxMochaEthers],
  solidity: {
    version: "0.8.34",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: sepoliaRpcUrl
    ? {
        sepolia: {
          type: "http",
          chainType: "l1",
          url: sepoliaRpcUrl,
          accounts: deployerPrivateKey ? [deployerPrivateKey] : [],
        },
      }
    : {},
});
