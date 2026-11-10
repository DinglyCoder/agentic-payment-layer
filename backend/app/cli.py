"""Local CLI for Sepolia purchases and explicitly selected offline simulation."""

import argparse
import json
import os
import secrets
import shlex
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Paradime Sepolia CLI. Start the app with ./demo.",
        epilog="Commands: doctor, buy [--budget 3], pay, demo replay, payments, "
        "receipt latest, status ID",
    )
    parser.add_argument(
        "--api-url", default=os.environ.get("PARADIME_API_URL", "http://127.0.0.1:8000")
    )
    parser.add_argument("--json", action="store_true", help="emit the full structured response")
    parser.add_argument(
        "--simulation", action="store_true", help="explicitly use offline simulated funds"
    )
    options, command = parser.parse_known_args()
    api_url = options.api_url.rstrip("/")
    operation_id = None
    seen = set()

    def request(path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        query = Request(api_url + path, data=body, headers={"Content-Type": "application/json"})
        with urlopen(query, timeout=30) as response:
            return json.load(response)

    def progress(operation):
        lines = [
            operation["phase"],
            *[f"{key.title()}: {url}" for key, url in operation["explorer_links"].items()],
        ]
        for line in lines:
            if line not in seen and not options.json:
                print(line, flush=True)
                seen.add(line)

    try:
        result = request(
            "/api/demo/commands",
            {
                "command": shlex.join(command) if command else "help",
                "mode": "simulation" if options.simulation else "sepolia",
                "request_id": "0x" + secrets.token_hex(32),
            },
        )
        if not options.json:
            print("\n".join(result["output"]), flush=True)
            seen.update(result["output"])
        operation = result.get("operation")
        if operation:
            operation_id = operation["operation_id"]
            deadline = time.monotonic() + 600
            while operation["status"] in {"queued", "running"}:
                progress(operation)
                if time.monotonic() >= deadline:
                    raise TimeoutError("operation is still pending")
                time.sleep(1)
                operation = request(f"/api/demo/operations/{operation_id}")
            progress(operation)
            result["operation"] = operation
            result["run"] = operation["result"]
            if operation["status"] != "completed":
                result["exit_code"] = 1
                if not options.json:
                    print(operation["error"] or operation["phase"], file=sys.stderr)
            elif not options.json:
                run = operation["result"]
                print(f"[{run['outcome'].upper()}] {run['summary']}", flush=True)
                for step in run["steps"]:
                    print(
                        f"{'✓' if step['status'] == 'passed' else '⊘'} "
                        f"{step['label']}: {step['detail']}"
                    )
        if options.json:
            print(json.dumps(result, indent=2))
        return result["exit_code"]
    except (HTTPError, URLError, TimeoutError, KeyboardInterrupt) as exc:
        print(f"CLI stopped: {exc}", file=sys.stderr)
        if operation_id:
            print(
                f"Payment may still settle. Resume: ./paradime --api-url {api_url} "
                f"status {operation_id}",
                file=sys.stderr,
            )
        else:
            print("Start the API with: ./demo", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
