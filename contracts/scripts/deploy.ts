import { network } from "hardhat";

const { ethers, networkName } = await network.create();
const [deployer] = await ethers.getSigners();
const arbitrator = process.env.ARBITRATOR_ADDRESS ?? deployer.address;
const paymentToken = process.env.PAYMENT_TOKEN_ADDRESS;

if (!paymentToken) {
  throw new Error("PAYMENT_TOKEN_ADDRESS must identify a Sepolia ERC-20 stablecoin");
}

console.log(`Deploying VisaTrustEscrow to ${networkName}`);
console.log(`Deployer: ${deployer.address}`);
console.log(`Arbitrator: ${arbitrator}`);
console.log(`Payment token: ${paymentToken}`);

const escrow = await ethers.deployContract("VisaTrustEscrow", [paymentToken, arbitrator]);
await escrow.waitForDeployment();

console.log(`VisaTrustEscrow: ${await escrow.getAddress()}`);
