import json
import time

from fastapi.testclient import TestClient

from app.cli import main as cli_main
from app.main import app


def finish(client, operation):
    deadline = time.monotonic() + 10
    while operation["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.02)
        operation = client.get(f"/api/demo/operations/{operation['operation_id']}").json()
    assert operation["status"] == "completed", operation
    return operation["result"]


def scenario(client, name, **input):
    response = client.post(f"/api/demo/scenarios/{name}", json={"mode": "simulation", **input})
    assert response.status_code == 200, response.text
    return finish(client, response.json())


def test_demo_purchase_exposes_authority_offer_evidence_and_output():
    with TestClient(app) as client:
        run = scenario(client, "purchase")
        assert run["simulation"] is True
        assert run["outcome"] == "completed"
        assert run["payment"]["source"] == "simulation"
        assert run["payment"]["status"] == "executed"
        assert run["payment"]["risk_signals"]
        assert run["mandate"]["spent_units"] == "1000000"
        assert run["mandate"]["signature"].startswith("0x")
        assert run["offer"]["accepts"][0]["scheme"] == "paradime-escrow"
        assert run["purchase"]["result"]["classification"] == "positive"
        assert run["explorer_links"] == {}
        assert (
            run["purchase"]["x402_payload"]["payload"]["paymentId"] == run["payment"]["payment_id"]
        )


def test_demo_budget_and_replay_reject_before_any_payment_exists():
    with TestClient(app) as client:
        for name in ("budget", "replay"):
            run = scenario(client, name)
            assert run["outcome"] == "blocked"
            assert run["payment"] is None
            assert run["mandate"]["spent_units"] == "0"
            assert run["steps"][-1]["status"] == "blocked"
            assert run["explorer_links"] == {}
        assert client.get("/api/payments").json() == []


def test_demo_watchlist_recall_is_backed_by_persisted_policy():
    with TestClient(app) as client:
        run = scenario(client, "watchlist")
        assert run["outcome"] == "recalled"
        payment = run["payment"]
        assert payment["risk_score"] == 100
        assert any(
            signal["name"] == "sender_identity" and signal["contribution"] == 70
            for signal in payment["risk_signals"]
        )
        assert client.get(f"/api/payments/{payment['payment_id']}").json() == payment


def test_terminal_calls_the_same_actions_and_cannot_execute_shell_commands():
    with TestClient(app) as client:

        def command(text):
            response = client.post(
                "/api/demo/commands", json={"command": text, "mode": "simulation"}
            )
            assert response.status_code == 200
            result = response.json()
            if result["operation"]:
                result["run"] = finish(client, result["operation"])
            return result

        assert command("paradime doctor")["exit_code"] == 0
        assert command("paradime buy --budget 0.5")["run"]["outcome"] == "blocked"
        bought = command("paradime buy --budget 3")
        assert bought["run"]["outcome"] == "completed"
        assert (
            command("paradime receipt latest")["data"]["payment_id"]
            == bought["run"]["payment"]["payment_id"]
        )
        assert len(command("paradime payments")["data"]) == 1
        for invalid in (
            "rm -rf /",
            "paradime doctor; pwd",
            "paradime buy --budget NaN",
            "paradime buy --budget 0.0000001",
            "paradime buy --budget -1",
            "paradime buy --budget 3 --budget 4",
            "paradime pay --scenario mainnet",
            'paradime buy "',
        ):
            assert command(invalid)["exit_code"] == 2


def test_sepolia_is_default_and_never_silently_simulates():
    with TestClient(app) as client:
        rejected = client.post("/api/demo/scenarios/purchase", json={})
        assert rejected.status_code == 422
        assert "Sepolia is not configured" in rejected.json()["detail"]
        cli = client.post("/api/demo/commands", json={"command": "paradime buy"}).json()
        assert cli["exit_code"] == 2
        assert cli["operation"] is None
        assert client.get("/api/payments").json() == []


def test_request_id_reuses_existing_operation_without_another_payment():
    with TestClient(app) as client:
        identifier = "0x" + "e" * 64
        first = client.post(
            "/api/demo/scenarios/purchase", json={"mode": "simulation", "request_id": identifier}
        ).json()
        finish(client, first)
        repeat = client.post(
            "/api/demo/scenarios/purchase", json={"mode": "simulation", "request_id": identifier}
        ).json()
        assert repeat["operation_id"] == first["operation_id"]
        assert len(client.get("/api/payments").json()) == 1
        mismatch = client.post(
            "/api/demo/scenarios/replay", json={"mode": "simulation", "request_id": identifier}
        )
        assert mismatch.status_code == 422
        assert len(client.get("/api/demo/operations?mode=simulation").json()) == 1
        assert client.get("/api/demo/operations?mode=sepolia").json() == []


def test_simulation_workspace_never_inherits_live_signer_or_chain():
    from pydantic import SecretStr

    from app.config import get_settings
    from app.demo import DemoWorkspace
    from app.websocket import manager

    with TestClient(app):
        live_settings = get_settings().model_copy(
            update={
                "simulation_mode": False,
                "testnet_enabled": True,
                "sepolia_rpc_url": "https://example.invalid",
                "arbitrator_private_key": SecretStr("0x" + "1" * 64),
                "autonomous_buyer_private_key": SecretStr("0x" + "2" * 64),
                "anthropic_api_key": SecretStr("synthetic-test-value"),
            }
        )
        workspace = DemoWorkspace(live_settings, app.state.sessions, manager)
        assert workspace.processor.chain.enabled is False
        assert workspace.settings.autonomous_buyer_private_key is None
        assert workspace.settings.arbitrator_private_key is None
        assert workspace.settings.anthropic_api_key is None


def test_local_cli_preserves_arguments_json_output_and_exit_codes(monkeypatch, capsys):
    from io import BytesIO

    requests = []

    def open_request(request, timeout):
        requests.append(request)
        return BytesIO(json.dumps({"exit_code": 2, "output": ["blocked"]}).encode())

    monkeypatch.setattr("app.cli.urlopen", open_request)
    monkeypatch.setattr(
        "sys.argv",
        ["paradime", "--api-url", "http://127.0.0.1:8123", "--json", "buy", "--budget", "0.5"],
    )
    assert cli_main() == 2
    assert json.loads(capsys.readouterr().out)["output"] == ["blocked"]
    assert requests[0].full_url == "http://127.0.0.1:8123/api/demo/commands"
    body = json.loads(requests[0].data)
    assert body["command"] == "buy --budget 0.5"
    assert body["mode"] == "sepolia"


def test_paid_work_can_finish_after_interruption_without_another_deposit(monkeypatch):
    from app.models import AutonomousPurchase

    with TestClient(app) as client:
        original = scenario(client, "purchase")
        buyer = app.state.demo.buyer

        async def forbidden_deposit(*_args, **_kwargs):
            raise AssertionError("recovery must not submit another deposit")

        monkeypatch.setattr(buyer, "_submit_deposit", forbidden_deposit)

        async def recover_paid_work():
            async with app.state.sessions() as session:
                purchase = await session.get(
                    AutonomousPurchase, original["purchase"]["purchase_id"]
                )
                purchase.status = "failed"
                purchase.result = None
                purchase.failure_reason = "worker interrupted after payment"
                await session.commit()
            recovered = await buyer.fulfill_purchase(original["purchase"]["purchase_id"])
            repeated = await buyer.fulfill_purchase(recovered.purchase_id)
            return recovered.result, repeated.result

        restored, repeated = client.portal.call(recover_paid_work)
        assert restored == original["purchase"]["result"] == repeated
        assert len(client.get("/api/payments").json()) == 1


def test_concurrent_request_id_retries_create_one_payment():
    import asyncio

    from app.demo import DemoInput

    with TestClient(app) as client:

        async def submit_twice():
            request = DemoInput(mode="simulation", request_id="0x" + "f" * 64)
            return await asyncio.gather(
                app.state.demo.start("purchase", request),
                app.state.demo.start("purchase", request),
            )

        first, second = client.portal.call(submit_twice)
        assert first.operation_id == second.operation_id
        finish(client, first.model_dump(mode="json"))
        assert len(client.get("/api/payments").json()) == 1
