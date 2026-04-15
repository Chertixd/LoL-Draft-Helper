#!/usr/bin/env python3
"""Upload artifact to VirusTotal and fail if detections > threshold.

Usage: python virustotal_check.py <file> --max-detections 3
Exits 0 on success, 1 if detections > max, 2 on API/network error.
VT_API_KEY env var required; when unset, prints a warning and exits 0 (skip).
"""
import argparse
import os
import sys
import time

import requests


def upload(path: str, api_key: str) -> str:
    """Upload a file to VirusTotal's /files endpoint.

    :param path: Absolute or relative path to the file to scan.
    :param api_key: VirusTotal API key.
    :return: analysis_id for polling.
    """
    with open(path, "rb") as f:
        r = requests.post(
            "https://www.virustotal.com/api/v3/files",
            headers={"x-apikey": api_key},
            files={"file": f},
            timeout=300,
        )
    r.raise_for_status()
    return r.json()["data"]["id"]


def poll(analysis_id: str, api_key: str, timeout_s: int = 600) -> int:
    """Poll the /analyses/<id> endpoint until completed.

    :param analysis_id: ID returned by upload().
    :param api_key: VirusTotal API key.
    :param timeout_s: Max wall-clock seconds before raising TimeoutError.
    :return: malicious + suspicious count from the final analysis.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(
            f"https://www.virustotal.com/api/v3/analyses/{analysis_id}",
            headers={"x-apikey": api_key},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()["data"]
        if data["attributes"]["status"] == "completed":
            stats = data["attributes"]["stats"]
            return stats["malicious"] + stats["suspicious"]
        time.sleep(15)
    raise TimeoutError("VT analysis did not complete within timeout")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("file")
    p.add_argument("--max-detections", type=int, default=3)
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    api_key = os.environ.get("VT_API_KEY")
    if not api_key:
        print("VT_API_KEY not set; skipping VirusTotal check", file=sys.stderr)
        return 0
    try:
        analysis_id = upload(args.file, api_key)
        detections = poll(analysis_id, api_key, args.timeout)
    except Exception as e:
        print(f"VirusTotal error: {e}", file=sys.stderr)
        return 2
    print(f"VirusTotal detections: {detections} (max: {args.max_detections})")
    return 0 if detections <= args.max_detections else 1


if __name__ == "__main__":
    sys.exit(main())
