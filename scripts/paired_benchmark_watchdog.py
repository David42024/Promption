"""Re-enable guards if the benchmark process dies; does not generate LLM traffic."""
import argparse
import json
import os
import time
from pathlib import Path

import httpx
import psutil


def restore(url, token):
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        headers = {"X-Chat-Service-Token": token}
        for name in ("filter", "output_guard"):
            response = client.post(url+"/security/state", headers=headers,
                                   json={"action": name, "enabled": True, "updated_by": "benchmark-watchdog"})
            response.raise_for_status()
        state = client.get(url+"/security/state", headers=headers)
        state.raise_for_status()
        data = state.json()
        return data.get("filter_enabled") is True and data.get("output_guard_enabled") is True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=int, required=True)
    parser.add_argument("--chat-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()
    try:
        parent = psutil.Process(args.parent)
        args.ready.write_text(json.dumps({"watchdog_pid": os.getpid()}), encoding="utf-8")
        parent.wait()
    except psutil.NoSuchProcess:
        pass
    for attempt in range(60):
        try:
            ok = restore(args.chat_url, os.environ.get("VALIDATION_CHAT_TOKEN", ""))
            result = {"restored": ok, "attempts": attempt+1}
        except Exception as exc:
            result = {"restored": False, "attempts": attempt+1, "error_type": type(exc).__name__}
        args.output.write_text(json.dumps(result), encoding="utf-8")
        if result["restored"]:
            return 0
        time.sleep(5)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
