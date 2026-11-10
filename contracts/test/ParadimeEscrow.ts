import { expect } from "chai";
import { network } from "hardhat";
import { readFile } from "node:fs/promises";
import type { MockStablecoin, ParadimeEscrow } from "../types/ethers-contracts/index.js";

describe("ParadimeEscrow", function () {
  it("keeps the backend payment ABI compatible with the compiled escrow", async function () {
    const { ethers } = await network.create();
    const artifact = await ethers.getContractFactory("ParadimeEscrow");
    const backendAbi = JSON.parse(await readFile(
      new URL("../../backend/app/contract_abi.json", import.meta.url), "utf8",
    ));
    const backend = new ethers.Interface(backendAbi);
    for (const name of ["deposit", "executePayment", "recallPayment", "payments", "paymentToken", "arbitrator"]) {
      expect(backend.getFunction(name), `missing ${name}`).not.to.equal(null);
      expect(backend.getFunction(name)!.format("sighash")).to.equal(
        artifact.interface.getFunction(name)!.format("sighash"),
      );
    }
    for (const name of ["PaymentDeposited", "PaymentExecuted", "PaymentRecalled"]) {
      const provided = backend.getEvent(name)!;
      const compiled = artifact.interface.getEvent(name)!;
      expect(provided.format("sighash")).to.equal(compiled.format("sighash"));
      expect(provided.inputs.map((input) => Boolean(input.indexed))).to.deep.equal(
        compiled.inputs.map((input) => Boolean(input.indexed)),
      );
    }
  });
  async function fixture() {
    const { ethers, networkHelpers } = await network.create();
    const [arbitrator, sender, receiver, stranger] = await ethers.getSigners();
    const token = (await ethers.deployContract("MockStablecoin")) as unknown as MockStablecoin;
    const escrow = (await ethers.deployContract("ParadimeEscrow", [
      await token.getAddress(),
      arbitrator.address,
    ])) as unknown as ParadimeEscrow;
    const paymentId = ethers.id("payment-001");
    const metadataHash = ethers.id("agent compute job");
    const amount = ethers.parseUnits("10", 6);
    await token.mint(sender.address, ethers.parseUnits("1000", 6));
    await token.connect(sender).approve(await escrow.getAddress(), ethers.MaxUint256);
    return { ethers, networkHelpers, token, escrow, arbitrator, sender, receiver, stranger, paymentId, metadataHash, amount };
  }

  it("records a unique escrow deposit", async function () {
    const { escrow, sender, receiver, paymentId, metadataHash, amount } = await fixture();

    await expect(
      escrow.connect(sender).deposit(paymentId, receiver.address, amount, metadataHash),
    ).to.emit(escrow, "PaymentDeposited");

    const payment = await escrow.payments(paymentId);
    expect(payment.sender).to.equal(sender.address);
    expect(payment.receiver).to.equal(receiver.address);
    expect(payment.amount).to.equal(amount);
    expect(payment.status).to.equal(1n);
  });

  it("lets only the arbitrator recall during the window", async function () {
    const { escrow, sender, receiver, stranger, paymentId, metadataHash, amount } = await fixture();
    await escrow.connect(sender).deposit(paymentId, receiver.address, amount, metadataHash);

    await expect(escrow.connect(stranger).recallPayment(paymentId)).to.be.revertedWithCustomError(escrow, "Unauthorized");
    await expect(escrow.recallPayment(paymentId)).to.emit(escrow, "PaymentRecalled");
    expect((await escrow.payments(paymentId)).status).to.equal(3n);
  });

  it("settles only after the recall window", async function () {
    const { escrow, networkHelpers, token, sender, receiver, paymentId, metadataHash, amount } = await fixture();
    await escrow.connect(sender).deposit(paymentId, receiver.address, amount, metadataHash);

    await expect(escrow.executePayment(paymentId)).to.be.revertedWithCustomError(escrow, "RecallWindowOpen");
    await networkHelpers.time.increase(31);
    const before = await token.balanceOf(receiver.address);
    await escrow.executePayment(paymentId);
    expect(await token.balanceOf(receiver.address)).to.equal(before + amount);
    expect((await escrow.payments(paymentId)).status).to.equal(2n);
  });

  it("prevents duplicate IDs and double resolution", async function () {
    const { escrow, sender, receiver, paymentId, metadataHash, amount } = await fixture();
    await escrow.connect(sender).deposit(paymentId, receiver.address, amount, metadataHash);
    await expect(
      escrow.connect(sender).deposit(paymentId, receiver.address, amount, metadataHash),
    ).to.be.revertedWithCustomError(escrow, "PaymentAlreadyExists");
    await escrow.recallPayment(paymentId);
    await expect(escrow.recallPayment(paymentId)).to.be.revertedWithCustomError(escrow, "InvalidPaymentStatus");
  });

  it("lets a sender recover an abandoned payment after one day", async function () {
    const { escrow, networkHelpers, sender, receiver, paymentId, metadataHash, amount } = await fixture();
    await escrow.connect(sender).deposit(paymentId, receiver.address, amount, metadataHash);
    await networkHelpers.time.increase(30 + 24 * 60 * 60 + 1);

    await expect(escrow.connect(sender).recoverExpiredPayment(paymentId))
      .to.emit(escrow, "PaymentRecalled")
      .withArgs(paymentId, sender.address, amount, true);
  });
});
