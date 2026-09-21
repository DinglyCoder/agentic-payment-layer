// SPDX-License-Identifier: MIT
pragma solidity ^0.8.34;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/// @title ParadimeEscrow
/// @notice Reversible ERC-20 stablecoin escrow for autonomous agent payments.
/// @dev The configured arbitrator is expected to be an automated trust-layer signer.
contract ParadimeEscrow {
    using SafeERC20 for IERC20;

    uint64 public constant RECALL_WINDOW = 30 seconds;
    uint64 public constant ESCAPE_HATCH_DELAY = 1 days;

    enum PaymentStatus {
        None,
        Pending,
        Executed,
        Recalled
    }

    struct Payment {
        address payable sender;
        address payable receiver;
        uint128 amount;
        uint64 depositedAt;
        uint64 recallDeadline;
        PaymentStatus status;
        bytes32 metadataHash;
    }

    IERC20 public immutable paymentToken;
    address public arbitrator;
    mapping(bytes32 paymentId => Payment) public payments;

    uint256 private locked = 1;

    error EmptyPayment();
    error InvalidAddress();
    error InvalidPaymentStatus(PaymentStatus current);
    error PaymentAlreadyExists();
    error RecallWindowClosed();
    error RecallWindowOpen();
    error Unauthorized();

    event PaymentDeposited(
        bytes32 indexed paymentId,
        address indexed sender,
        address indexed receiver,
        uint256 amount,
        uint64 depositedAt,
        uint64 recallDeadline,
        bytes32 metadataHash
    );
    event PaymentExecuted(bytes32 indexed paymentId, address indexed receiver, uint256 amount);
    event PaymentRecalled(bytes32 indexed paymentId, address indexed sender, uint256 amount, bool escaped);
    event ArbitratorChanged(address indexed previousArbitrator, address indexed newArbitrator);

    modifier onlyArbitrator() {
        if (msg.sender != arbitrator) revert Unauthorized();
        _;
    }

    modifier nonReentrant() {
        if (locked != 1) revert Unauthorized();
        locked = 2;
        _;
        locked = 1;
    }

    constructor(address token, address initialArbitrator) {
        if (token == address(0) || initialArbitrator == address(0)) revert InvalidAddress();
        paymentToken = IERC20(token);
        arbitrator = initialArbitrator;
    }

    /// @notice Lock a payment while the trust layer evaluates it.
    function deposit(bytes32 paymentId, address payable receiver, uint128 amount, bytes32 metadataHash)
        external
        nonReentrant
    {
        if (paymentId == bytes32(0) || amount == 0) revert EmptyPayment();
        if (receiver == address(0) || receiver == msg.sender) revert InvalidAddress();
        if (payments[paymentId].status != PaymentStatus.None) revert PaymentAlreadyExists();

        uint64 depositedAt = uint64(block.timestamp);
        uint64 recallDeadline = depositedAt + RECALL_WINDOW;
        payments[paymentId] = Payment({
            sender: payable(msg.sender),
            receiver: receiver,
            amount: amount,
            depositedAt: depositedAt,
            recallDeadline: recallDeadline,
            status: PaymentStatus.Pending,
            metadataHash: metadataHash
        });

        paymentToken.safeTransferFrom(msg.sender, address(this), amount);

        emit PaymentDeposited(
            paymentId,
            msg.sender,
            receiver,
            amount,
            depositedAt,
            recallDeadline,
            metadataHash
        );
    }

    /// @notice Settle an approved payment after its recall period has elapsed.
    function executePayment(bytes32 paymentId) external onlyArbitrator nonReentrant {
        Payment storage payment = _pending(paymentId);
        if (block.timestamp <= payment.recallDeadline) revert RecallWindowOpen();

        payment.status = PaymentStatus.Executed;
        uint256 amount = payment.amount;
        address payable receiver = payment.receiver;
        paymentToken.safeTransfer(receiver, amount);

        emit PaymentExecuted(paymentId, receiver, amount);
    }

    /// @notice Return a suspicious payment during the 30-second recall period.
    function recallPayment(bytes32 paymentId) external onlyArbitrator nonReentrant {
        Payment storage payment = _pending(paymentId);
        if (block.timestamp > payment.recallDeadline) revert RecallWindowClosed();
        _refund(paymentId, payment, false);
    }

    /// @notice Let the sender recover a payment if the arbitrator never resolves it.
    function recoverExpiredPayment(bytes32 paymentId) external nonReentrant {
        Payment storage payment = _pending(paymentId);
        if (msg.sender != payment.sender) revert Unauthorized();
        if (block.timestamp <= payment.recallDeadline + ESCAPE_HATCH_DELAY) revert RecallWindowOpen();
        _refund(paymentId, payment, true);
    }

    function setArbitrator(address newArbitrator) external onlyArbitrator {
        if (newArbitrator == address(0)) revert InvalidAddress();
        address previous = arbitrator;
        arbitrator = newArbitrator;
        emit ArbitratorChanged(previous, newArbitrator);
    }

    function _pending(bytes32 paymentId) private view returns (Payment storage payment) {
        payment = payments[paymentId];
        if (payment.status != PaymentStatus.Pending) revert InvalidPaymentStatus(payment.status);
    }

    function _refund(bytes32 paymentId, Payment storage payment, bool escaped) private {
        payment.status = PaymentStatus.Recalled;
        uint256 amount = payment.amount;
        address payable sender = payment.sender;
        paymentToken.safeTransfer(sender, amount);
        emit PaymentRecalled(paymentId, sender, amount, escaped);
    }
}
