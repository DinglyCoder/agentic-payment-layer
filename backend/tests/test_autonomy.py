from datetime import timedelta

from eth_account import Account
from fastapi.testclient import TestClient

from app.autonomy import canonical_hash, signature_hex
from app.main import app
from app.models import utc_now


def signed_mandate(buyer_address: str, *, budget: str = "1000000") -> dict:
    owner = Account.create()
    expires_at = (utc_now() + timedelta(minutes=10)).replace(microsecond=0)
    unsigned = {
        "owner": owner.address.lower(),
        "delegate": buyer_address,
        "token": "0x1c7d4b196cb0c7b01d743fbc6116a902379c7238",
        "max_amount_per_payment_units": budget,
        "total_budget_units": budget,
        "allowed_receiver": "0x2222222222222222222222222222222222222222",
        "allowed_service": "text-analysis-v1",
        "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        "nonce": "0x" + "a" * 64,
    }
    mandate_id = canonical_hash(unsigned)
    return {
        **unsigned,
        "mandate_id": mandate_id,
        "signature": signature_hex(owner, mandate_id),
    }


def test_autonomous_demo_completes_signed_mandate_x402_and_mcp_flow():
    with TestClient(app) as client:
        buyer = client.get("/api/autonomous/buyer")
        assert buyer.status_code == 200
        assert buyer.json()["enabled"] is True

        response = client.post(
            "/api/autonomous/demo",
            json={
                "prompt": "Trusted compute should produce a good result",
                "budget_units": "3000000",
            },
        )
        assert response.status_code == 201, response.text
        purchase = response.json()
        assert purchase["status"] == "completed"
        assert purchase["amount_units"] == "1000000"
        assert purchase["result"]["classification"] == "positive"
        assert purchase["x402_requirement"]["x402Version"] == 2
        assert purchase["x402_requirement"]["accepts"][0]["scheme"] == "paradime-escrow"
        assert purchase["x402_payload"]["payload"]["paymentId"] == purchase["payment_id"]

        payment = client.get(f"/api/payments/{purchase['payment_id']}").json()
        assert payment["status"] == "executed"
        assert payment["sender"] == buyer.json()["address"]


def test_signed_mandate_is_enforced_without_an_additional_owner_signature():
    with TestClient(app) as client:
        buyer_address = client.get("/api/autonomous/buyer").json()["address"]
        mandate = signed_mandate(buyer_address)
        registration = client.post("/api/autonomous/mandates", json=mandate)
        assert registration.status_code == 201, registration.text

        first = client.post(
            "/api/autonomous/purchases",
            json={"mandate_id": mandate["mandate_id"], "prompt": "Analyze this safe result"},
        )
        assert first.status_code == 201, first.text
        assert first.json()["status"] == "completed"

        second = client.post(
            "/api/autonomous/purchases",
            json={"mandate_id": mandate["mandate_id"], "prompt": "Analyze another result"},
        )
        assert second.status_code == 422
        assert "remaining mandate budget" in second.json()["detail"]


def test_seller_mcp_advertises_tool_and_returns_x402_payment_required():
    with TestClient(app) as client:
        listing = client.post(
            "/mcp/seller",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        ).json()
        assert listing["result"]["tools"][0]["name"] == "analyze_text"

        call = client.post(
            "/mcp/seller",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "analyze_text",
                    "arguments": {
                        "prompt": "Analyze this text",
                        "purchase_id": "0x" + "0" * 64,
                    },
                },
            },
        ).json()["result"]
        assert call["isError"] is True
        assert call["structuredContent"]["x402Version"] == 2
        assert call["content"][0]["text"]


def test_mandate_tampering_and_nonce_replay_are_rejected():
    with TestClient(app) as client:
        buyer_address = client.get("/api/autonomous/buyer").json()["address"]
        mandate = signed_mandate(buyer_address)
        tampered = {**mandate, "total_budget_units": "2000000"}
        rejected = client.post("/api/autonomous/mandates", json=tampered)
        assert rejected.status_code == 422
        assert "mandate_id" in rejected.json()["detail"]

        assert client.post("/api/autonomous/mandates", json=mandate).status_code == 201
        replay = signed_mandate(buyer_address, budget="2000000")
        rejected = client.post("/api/autonomous/mandates", json=replay)
        assert rejected.status_code == 422
        assert "nonce" in rejected.json()["detail"]
