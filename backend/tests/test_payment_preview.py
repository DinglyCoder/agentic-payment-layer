from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.main import app
from app.models import SpendingMandate
from app.payment_preview import PaymentPreviewInput, preview_payment
from app.schemas import ManagedDemoWalletRead


def live_workspace(balance="20000000", native=str(10**17)):
    settings = Settings(
        _env_file=None,
        seller_address="0x" + "55" * 20,
        payment_token_address="0x" + "22" * 20,
        escrow_contract_address="0x" + "11" * 20,
        seller_price_units=2_000_000,
    )
    status = ManagedDemoWalletRead(
        enabled=True,
        address="0x" + "44" * 20,
        balance_units=balance,
        native_balance_wei=native,
        max_amount_units="5000000",
        remaining_session_budget_units="6000000",
    )
    return SimpleNamespace(
        settings=settings,
        live_settings=settings,
        require_sepolia=lambda: None,
        chain=SimpleNamespace(
            enabled=True,
            account=SimpleNamespace(address="0x" + "33" * 20),
            token_balance=AsyncMock(return_value=int(balance)),
            native_balance=AsyncMock(return_value=int(native)),
        ),
        wallet=SimpleNamespace(status=AsyncMock(return_value=status)),
    )


def test_preview_is_read_only_and_distinguishes_charge_budget_and_policy_checks():
    with TestClient(app) as client:
        for scenario, amount in [
            ("purchase", "1000000"),
            ("trusted", "4200000"),
            ("watchlist", "82000000"),
            ("budget", "0"),
            ("replay", "0"),
        ]:
            response = client.post(
                "/api/payments/preview",
                json={
                    "kind": "scenario",
                    "mode": "simulation",
                    "scenario": scenario,
                },
            )
            assert response.status_code == 200, response.text
            review = response.json()
            assert review["amount_units"] == amount
            assert review["balance_units"] is None
            assert review["native_balance_wei"] is None
            if scenario == "purchase":
                assert review["budget_units"] == "3000000"
                assert review["offer_units"] == "1000000"
        assert client.get("/api/payments").json() == []
        assert client.get("/api/demo/operations?mode=simulation").json() == []

        async def mandate_count():
            async with app.state.sessions() as session:
                return await session.scalar(select(func.count()).select_from(SpendingMandate))

        assert client.portal.call(mandate_count) == 0


@pytest.mark.parametrize(
    ("command", "amount"),
    [
        ("./paradime buy --budget '3'", "1000000"),
        ("buy --budget 0.5", "0"),
        ("paradime pay --scenario watchlist", "82000000"),
        ("paradime demo replay", "0"),
        ("paradime doctor", None),
        ("paradime payments", None),
        ("resume 0x123", None),
        ("paradime help", None),
    ],
)
def test_command_preview_uses_dispatcher_semantics_without_executing(command, amount):
    with TestClient(app) as client:
        response = client.post(
            "/api/payments/preview",
            json={
                "kind": "command",
                "mode": "simulation",
                "command": command,
            },
        )
        assert response.status_code == 200
        if amount is None:
            assert response.json() is None
        else:
            assert response.json()["amount_units"] == amount
        assert client.get("/api/payments").json() == []


def test_invalid_command_and_unconfigured_sepolia_never_start_payments():
    with TestClient(app) as client:
        for payload in [
            {"kind": "command", "mode": "simulation", "command": "buy --budget NaN"},
            {"kind": "scenario", "mode": "sepolia", "scenario": "purchase"},
        ]:
            response = client.post("/api/payments/preview", json=payload)
            assert response.status_code == 422
        assert client.get("/api/payments").json() == []


@pytest.mark.asyncio
async def test_live_review_uses_configured_price_and_fresh_managed_balances():
    workspace = live_workspace()
    payload = PaymentPreviewInput(kind="scenario", mode="sepolia", scenario="purchase")
    first = await preview_payment(payload, workspace)
    assert first.amount_units == "2000000"
    assert first.budget_units == "3000000"
    assert first.balance_units == "20000000"
    assert first.native_balance_wei == str(10**17)
    workspace.wallet.status.return_value.balance_units = "1000000"
    second = await preview_payment(payload, workspace)
    assert not second.can_submit
    assert "Insufficient test USDC" in " ".join(second.blockers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "receiver", ["0x" + "00" * 20, "0x" + "22" * 20, "0x" + "11" * 20, "0x" + "44" * 20]
)
async def test_live_review_blocks_invalid_receivers(receiver):
    review = await preview_payment(
        PaymentPreviewInput(
            kind="direct",
            mode="sepolia",
            receiver=receiver,
            amount_usdc="4.2",
        ),
        live_workspace(),
    )
    assert not review.can_submit
    assert review.blockers


@pytest.mark.asyncio
async def test_browser_wallet_balance_and_gas_are_read_from_rpc():
    workspace = live_workspace(native="0")
    review = await preview_payment(
        PaymentPreviewInput(
            kind="direct",
            mode="sepolia",
            payer="browser",
            sender="0x" + "66" * 20,
            receiver="0x" + "55" * 20,
            amount_usdc="1.25",
        ),
        workspace,
    )
    assert review.balance_units == "20000000"
    assert review.amount_units == "1250000"
    assert not review.can_submit
    assert "Sepolia ETH" in " ".join(review.blockers)
    workspace.wallet.status.assert_not_awaited()


def test_balance_provider_errors_do_not_expose_rpc_credentials(monkeypatch):
    with TestClient(app) as client:

        async def unavailable(*_args):
            raise RuntimeError("https://rpc.invalid/private-test-credential")

        monkeypatch.setattr("app.payment_preview.preview_payment", unavailable)
        response = client.post(
            "/api/payments/preview",
            json={
                "kind": "scenario",
                "mode": "sepolia",
                "scenario": "purchase",
            },
        )
        assert response.status_code == 503
        assert "private-test-credential" not in response.text
