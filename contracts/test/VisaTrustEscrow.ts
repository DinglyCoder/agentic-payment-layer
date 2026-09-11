import { expect } from "chai";
import { network } from "hardhat";
import type { MockStablecoin, VisaTrustEscrow } from "../types/ethers-contracts/index.js";

describe("VisaTrustEscrow", function () {
  async function fixture() {
    const { ethers, networkHelpers } = await network.create();
    const [arbitrator, sender, receiver, stranger] = await ethers.getSigners();
    const token = (await ethers.deployContract("MockStablecoin")) as unknown as MockStablecoin;
    const escrow = (await ethers.deployContract("VisaTrustEscrow", [
      await token.getAddress(),
      arbitrator.address,
    ])) as unknown as VisaTrustEscrow;
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
