# apps/backend/smoke_test_exe.py
# Tiny CI helper: runs after the .exe is already spawned and the ready-file
# has appeared. Verifies Socket.IO + HTTPS, exits 0 on success / non-zero on failure.

import argparse
import sys

import requests
import socketio


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    # 1. Socket.IO round-trip (verifies engineio.async_drivers.threading hidden import).
    client = socketio.Client(logger=False, engineio_logger=False)
    try:
        client.connect(f"http://127.0.0.1:{args.port}", wait_timeout=5)
        assert client.connected, "Socket.IO did not connect"
        client.disconnect()
    except Exception as e:
        print(f"FAIL socket.io: {e}", file=sys.stderr)
        return 1

    # 2. HTTPS GET (verifies certifi bundling).
    try:
        r = requests.get("https://example.com/", timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"FAIL https: {e}", file=sys.stderr)
        return 1

    print("smoke OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
