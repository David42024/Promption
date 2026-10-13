"""Dedicated experimental OpenAI gateway; persistent limits before paid dispatch."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from filelock import FileLock


class BudgetRejected(ValueError):
    """Request was rejected without dispatching to the provider."""


class BudgetGateway:
    """Reserve a conservative upper charge for every attempt, including failures."""

    def __init__(self, ledger, api_key, max_calls=40, max_usd="1", client=None):
        if not api_key or max_calls < 1 or Decimal(str(max_usd)) <= 0:
            raise ValueError("Valid credential and positive limits required")
        self.path = Path(ledger)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key
        self.lock = FileLock(str(self.path) + ".lock")
        self.max_calls = max_calls
        self.max_usd = Decimal(str(max_usd))
        self.client = client or httpx.Client(timeout=125, trust_env=False, follow_redirects=False)
        self.config = {"model": "gpt-5-nano", "max_calls": max_calls, "max_usd": str(self.max_usd),
                       "input_usd_per_million": "0.05", "output_usd_per_million": "0.40",
                       "input_upper_tokens": 400000, "output_upper_tokens": 6144}
        with self.lock:
            self._state()

    def _state(self):
        if not self.path.exists():
            return {"config": self.config, "attempts": []}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("config") != self.config or not isinstance(state.get("attempts"), list):
            raise ValueError("Ledger/configuration mismatch; refusing dispatch")
        for i, item in enumerate(state["attempts"], 1):
            if item.get("attempt") != i or Decimal(item["reserved_usd"]) != self.upper_charge():
                raise ValueError("Invalid persistent reservation")
        return state

    def upper_charge(self):
        return (Decimal(400000) * Decimal("0.05") + Decimal(6144) * Decimal("0.40")) / 1000000

    def _save(self, state):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, self.path)

    def snapshot(self):
        with self.lock:
            state = self._state()
            return {"attempts": len(state["attempts"]), "reserved_usd": str(sum(
                (Decimal(a["reserved_usd"]) for a in state["attempts"]), Decimal(0))),
                "max_calls": self.max_calls, "max_usd": str(self.max_usd)}

    def forward(self, path, body, authorization):
        if not hmac.compare_digest(authorization, "Bearer " + self.api_key):
            raise BudgetRejected("Unauthorized gateway request")
        if path not in {"/v1/responses", "/v1/chat/completions"}:
            raise BudgetRejected("Unsupported provider endpoint")
        payload = json.loads(body)
        output_limit = payload.get("max_output_tokens", payload.get("max_completion_tokens"))
        if payload.get("model") != "gpt-5-nano":
            raise BudgetRejected("Only the frozen model is allowed")
        if "stream" in payload and not isinstance(payload["stream"], bool):
            raise BudgetRejected("Invalid streaming transport flag")
        if isinstance(output_limit, bool) or not isinstance(output_limit, int) or not 0 < output_limit <= 6144:
            raise BudgetRejected("Explicit bounded output tokens required")
        if any(t.get("type") != "function" for t in payload.get("tools", [])):
            raise BudgetRejected("Provider-billed built-in tools are not allowed")
        with self.lock:
            state = self._state()
            charge = self.upper_charge()
            reserved = sum((Decimal(a["reserved_usd"]) for a in state["attempts"]), Decimal(0))
            if len(state["attempts"]) >= self.max_calls or reserved + charge > self.max_usd:
                raise BudgetRejected("Experimental call or monetary budget exhausted")
            attempt = len(state["attempts"]) + 1
            state["attempts"].append({"attempt": attempt, "reserved_usd": str(charge),
                "state": "RESERVED_BEFORE_DISPATCH", "time": time.time(), "endpoint": path,
                "request_sha256": hashlib.sha256(body).hexdigest(), "output_limit": output_limit})
            self._save(state)
        try:
            response = self.client.post("https://api.openai.com" + path, content=body,
                headers={"Authorization": authorization, "Content-Type": "application/json"})
        except Exception as exc:
            self._finish(attempt, {"state": "TRANSPORT_FAILURE_OR_UNKNOWN", "error_type": type(exc).__name__})
            raise
        self._finish(attempt, {"state": "PROVIDER_RESPONDED", "http": response.status_code,
                              "provider_request_id": response.headers.get("x-request-id"),
                              **response_usage(response)})
        return response

    def _finish(self, attempt, fields):
        with self.lock:
            state = self._state()
            state["attempts"][attempt - 1].update(fields)
            self._save(state)


def response_usage(response):
    """Extract only provider usage metadata; retain no generated content."""
    candidates = []
    if "text/event-stream" in response.headers.get("Content-Type", ""):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                try:
                    item = json.loads(line[5:].strip())
                    if item.get("type") == "response.completed":
                        candidates.append(item.get("response", {}))
                except (ValueError, AttributeError):
                    continue
    else:
        try:
            candidates.append(response.json())
        except ValueError:
            pass
    for item in reversed(candidates):
        if not isinstance(item, dict):
            continue
        usage = item.get("usage")
        if isinstance(usage, dict):
            safe_usage = {}
            for k in ("input_tokens", "output_tokens", "total_tokens", "prompt_tokens", "completion_tokens"):
                n = usage.get(k)
                safe_usage[k] = n if isinstance(n, int) and not isinstance(n, bool) and n >= 0 else None
            return {"provider_model": item.get("model"), "provider_usage": safe_usage}
    return {"provider_usage": None}


def serve(gateway, port):
    """Buffer internal SSE unchanged; never expose it directly to end users."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            return

        def respond(self, status, content, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path != "/budget":
                return self.respond(404, b'{}')
            self.respond(200, json.dumps(gateway.snapshot()).encode())

        def do_POST(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 2097152 or self.headers.get("Transfer-Encoding"):
                    raise BudgetRejected("Bounded Content-Length required")
                response = gateway.forward(self.path, self.rfile.read(size), self.headers.get("Authorization", ""))
                self.respond(response.status_code, response.content, response.headers.get("Content-Type", "application/json"))
            except (BudgetRejected, ValueError, TypeError):
                self.respond(429, b'{"error":{"message":"Experimental gateway refused dispatch","type":"budget_or_contract_rejection"}}')
            except Exception:
                self.respond(502, b'{"error":{"message":"Experimental provider transport failed","type":"provider_transport_failure"}}')
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--port", type=int, default=3199)
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--max-usd", default="1")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute requires explicit operator paid-call authorization")
    serve(BudgetGateway(args.ledger, os.environ.get("OPENAI_API_KEY"), args.max_calls, args.max_usd), args.port)


if __name__ == "__main__":
    main()
