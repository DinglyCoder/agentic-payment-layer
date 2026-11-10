from fastapi.testclient import TestClient

from app.main import app


def test_health_and_demo_payment_flow():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["mode"] == "simulation"
        assert health.json()["testnet_available"] is False
        assert health.json()["payment_token_address"] is None
        demo_wallet = client.get("/api/testnet/demo-wallet")
        assert demo_wallet.status_code == 200
        assert demo_wallet.json()["enabled"] is False

        response = client.post(
            "/api/demo/payments",
            json={
                "sender": "0x1111111111111111111111111111111111111111",
                "receiver": "0x2222222222222222222222222222222222222222",
                "amount_usdc": "4.2",
                "description": "Agent compute settlement",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "executed"
        assert body["decision"] == "execute"
        assert body["deposited_at"].endswith("Z")

        payments = client.get("/api/payments").json()
        assert len(payments) == 1
        assert len(client.get("/api/payments?mode=simulation").json()) == 1
        assert client.get("/api/payments?mode=sepolia").json() == []
        stats = client.get("/api/stats").json()
        assert stats["total_payments"] == 1
        assert stats["execution_rate"] == 100.0
        assert client.get("/api/stats?mode=sepolia").json()["total_payments"] == 0


def test_websocket_connects():
    with TestClient(app) as client, client.websocket_connect("/ws/payments") as websocket:
        assert websocket.receive_json() == {"event": "connected", "payment": None}
