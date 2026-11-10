"""Run the Sepolia demo, or explicitly select offline simulation."""

import argparse
import errno
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from contextlib import ExitStack
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def available_port(preferred: int) -> int:
    for candidate in range(preferred, min(preferred + 20, 65536)):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
                return candidate
            except OSError as exc:
                if exc.errno != errno.EADDRINUSE:
                    raise RuntimeError(f"Cannot bind a local demo server: {exc}") from exc
                continue
    raise RuntimeError(f"No available port near {preferred}; use --port or --api-port.")


def wait_ready(url: str, process: subprocess.Popen, timeout: int = 30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"A demo server exited with code {process.returncode}.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.15)
    raise RuntimeError(f"Timed out waiting for {url}")


def stop(process: subprocess.Popen):
    # Each child owns its process group, including npm's Vite subprocess.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5173)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--simulation", action="store_true", help="use offline simulated funds")
    args = parser.parse_args()
    if not args.simulation and not os.environ.get("PARADIME_SECRETS_LOADED"):
        encrypted = ROOT / "secrets" / "sepolia.env"
        if encrypted.exists() and shutil.which("with-secrets"):
            os.execvpe(
                "with-secrets",
                [
                    "with-secrets",
                    str(encrypted),
                    "--",
                    sys.executable,
                    str(Path(__file__).resolve()),
                    *sys.argv[1:],
                ],
                {**os.environ, "PARADIME_SECRETS_LOADED": "1"},
            )
        elif not all(
            os.environ.get(name)
            for name in (
                "SEPOLIA_RPC_URL",
                "ESCROW_CONTRACT_ADDRESS",
                "PAYMENT_TOKEN_ADDRESS",
                "ARBITRATOR_PRIVATE_KEY",
                "DEPLOYER_PRIVATE_KEY",
            )
        ):
            print(
                "Sepolia configuration is missing. Configure encrypted secrets/sepolia.env "
                "and with-secrets. Offline simulation is available as ./demo --simulation.",
                file=sys.stderr,
            )
            return 1
    if not all(0 < port < 65517 for port in (args.port, args.api_port)):
        parser.error("ports must be between 1 and 65516")
    for tool in ("uv", "node", "npm"):
        if not shutil.which(tool):
            print(
                f"Missing {tool}. Install Node.js 22+ and uv, then run make demo.",
                file=sys.stderr,
            )
            return 1
    major = int(
        subprocess.check_output(["node", "--version"], text=True).strip().lstrip("v").split(".")[0]
    )
    if major < 22:
        print("Node.js 22 or newer is required.", file=sys.stderr)
        return 1
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules" / ".bin" / "vite").exists():
        print("Installing the locked frontend dependencies…", flush=True)
        subprocess.run(["npm", "ci"], cwd=frontend, check=True)

    children: list[subprocess.Popen] = []
    try:
        with (
            tempfile.TemporaryDirectory(prefix="paradime-demo-") as scratch,
            ExitStack() as cleanup,
        ):
            api_port = available_port(args.api_port)
            ui_port = available_port(args.port if args.port != api_port else args.port + 1)
            api_url = f"http://127.0.0.1:{api_port}"
            ui_url = f"http://127.0.0.1:{ui_port}"
            environment = {
                **os.environ,
                "SIMULATION_MODE": "true" if args.simulation else "false",
                "TESTNET_ENABLED": "false" if args.simulation else "true",
                "SEED_DEMO_DATA": "true" if args.simulation else "false",
                "MANAGED_DEMO_WALLET_ENABLED": "false" if args.simulation else "true",
                "DATABASE_URL": (
                    f"sqlite+aiosqlite:///{scratch}/demo.db"
                    if args.simulation
                    else f"sqlite+aiosqlite:///{ROOT / 'backend' / 'paradime-demo.db'}"
                ),
                "FRONTEND_ORIGIN": ui_url,
                "ANTHROPIC_API_KEY": "",
                "VITE_API_URL": "",
                "PARADIME_BACKEND_URL": api_url,
            }
            if args.simulation:
                environment.update(
                    {
                        name: ""
                        for name in (
                            "SEPOLIA_RPC_URL",
                            "ARBITRATOR_PRIVATE_KEY",
                            "DEPLOYER_PRIVATE_KEY",
                            "AUTONOMOUS_BUYER_PRIVATE_KEY",
                        )
                    }
                )
            else:
                # Observe freshly mined logs so recall can land inside the existing 30s window.
                # This is low-latency testnet processing, not finalized-block protection.
                environment.update({"CHAIN_CONFIRMATIONS": "0", "POLL_INTERVAL_SECONDS": "0.5"})
            backend = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "--frozen",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
                cwd=ROOT / "backend",
                env=environment,
                start_new_session=True,
            )
            children.append(backend)
            cleanup.callback(stop, backend)
            wait_ready(api_url + "/api/health", backend, timeout=90)
            frontend_environment = {
                key: value
                for key, value in environment.items()
                if key
                in {
                    "PATH",
                    "HOME",
                    "USER",
                    "LOGNAME",
                    "SHELL",
                    "TMPDIR",
                    "LANG",
                    "LC_ALL",
                    "LC_CTYPE",
                    "TERM",
                    "COLORTERM",
                    "SSL_CERT_FILE",
                    "SSL_CERT_DIR",
                    "NODE_EXTRA_CA_CERTS",
                    "VITE_API_URL",
                    "PARADIME_BACKEND_URL",
                }
            }
            ui = subprocess.Popen(
                [
                    "npm",
                    "run",
                    "dev",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(ui_port),
                    "--strictPort",
                ],
                cwd=frontend,
                env=frontend_environment,
                start_new_session=True,
            )
            children.append(ui)
            cleanup.callback(stop, ui)
            wait_ready(ui_url + "/demo", ui)
            print(
                f"\nParadime demo ready: {ui_url}/demo\nAPI docs: {api_url}/docs",
                flush=True,
            )
            cli = "./paradime" if api_port == 8000 else f"./paradime --api-url {api_url}"
            print(
                f"Local CLI: {cli} buy --budget 3\n"
                + (
                    "Offline simulation. Temporary database.\n"
                    if args.simulation
                    else "Sepolia: actual test USDC and gas. Records persist across restarts.\n"
                )
                + "Ctrl+C stops both servers.\n",
                flush=True,
            )
            if not args.no_open:
                webbrowser.open(ui_url + "/demo")
            while all(child.poll() is None for child in children):
                time.sleep(0.5)
            raise RuntimeError("A demo server stopped unexpectedly; see its output above.")
    except KeyboardInterrupt:
        print("\nStopping the demo…", flush=True)
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    # SIGTERM should run the same teardown path as Ctrl+C.
    def interrupt(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    raise SystemExit(main())
