"""No-network tests for experimental pre-dispatch budget enforcement."""
import concurrent.futures
import json

import httpx
import pytest

from scripts.experimental_openai_budget_gateway import BudgetGateway, BudgetRejected


BODY = json.dumps({"model": "gpt-5-nano", "max_output_tokens": 6144, "input": "synthetic"}).encode()


def make(tmp_path, max_calls=40, max_usd="1", handler=None):
    seen = []
    def transport(request):
        seen.append(request)
        return handler(request) if handler else httpx.Response(200, json={"id": "mock-local"})
    client = httpx.Client(transport=httpx.MockTransport(transport))
    return BudgetGateway(tmp_path / "ledger.json", "local-test-only", max_calls, max_usd, client), seen


def test_exact_concurrent_call_cap(tmp_path):
    gateway, seen = make(tmp_path, max_calls=4)
    def send(_):
        try:
            gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
            return True
        except BudgetRejected:
            return False
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(send, range(20))) == 4
    assert len(seen) == gateway.snapshot()["attempts"] == 4
    assert all(str(r.url) == "https://api.openai.com/v1/responses" for r in seen)


def test_monetary_reservation_cap_and_resume(tmp_path):
    gateway, seen = make(tmp_path, max_usd="0.023")
    gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    with pytest.raises(BudgetRejected):
        gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    resumed, more = make(tmp_path, max_usd="0.023")
    with pytest.raises(BudgetRejected):
        resumed.forward("/v1/responses", BODY, "Bearer local-test-only")
    assert len(seen) == 1 and not more


@pytest.mark.parametrize("patch", [{"model": "other"}, {"stream": "invalid"}, {"max_output_tokens": None},
    {"max_output_tokens": 6145}, {"max_output_tokens": True}, {"tools": [{"type": "web_search"}]}])
def test_invalid_contract_never_dispatches(tmp_path, patch):
    gateway, seen = make(tmp_path)
    body = json.loads(BODY); body.update(patch)
    with pytest.raises(BudgetRejected):
        gateway.forward("/v1/responses", json.dumps(body).encode(), "Bearer local-test-only")
    assert not seen and gateway.snapshot()["attempts"] == 0


def test_unknown_transport_consumes_reservation_without_retry(tmp_path):
    def fail(request):
        raise httpx.ReadTimeout("local controlled failure", request=request)
    gateway, seen = make(tmp_path, max_calls=1, handler=fail)
    with pytest.raises(httpx.ReadTimeout):
        gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    with pytest.raises(BudgetRejected):
        gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    assert len(seen) == 1
    assert json.loads(gateway.path.read_text())["attempts"][0]["state"] == "TRANSPORT_FAILURE_OR_UNKNOWN"


def test_persistence_failure_prevents_dispatch(tmp_path, monkeypatch):
    gateway, seen = make(tmp_path)
    def fail(state):
        raise OSError("controlled filesystem failure")
    monkeypatch.setattr(gateway, "_save", fail)
    with pytest.raises(OSError):
        gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    assert not seen


def test_authentication_and_endpoint_rejected(tmp_path):
    gateway, seen = make(tmp_path)
    with pytest.raises(BudgetRejected):
        gateway.forward("/v1/responses", BODY, "Bearer incorrect")
    with pytest.raises(BudgetRejected):
        gateway.forward("/v1/files", BODY, "Bearer local-test-only")
    assert not seen


def test_ledger_contains_no_credentials_or_prompt(tmp_path):
    gateway, seen = make(tmp_path)
    gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    raw = gateway.path.read_text()
    assert "local-test-only" not in raw and "synthetic" not in raw


def test_corrupt_or_different_ledger_fails_closed(tmp_path):
    gateway, seen = make(tmp_path)
    gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    with pytest.raises(ValueError):
        make(tmp_path, max_calls=100)
    gateway.path.write_text("not-json")
    with pytest.raises(ValueError):
        make(tmp_path)


def test_internal_stream_preserved_and_usage_only_recorded(tmp_path):
    content = b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"synthetic-private-response"}\n\nevent: response.completed\ndata: {"type":"response.completed","response":{"model":"gpt-5-nano","usage":{"input_tokens":10,"output_tokens":0,"total_tokens":10}}}\n\n'
    gateway, seen = make(tmp_path, handler=lambda _: httpx.Response(200, content=content,
        headers={"Content-Type": "text/event-stream"}))
    body = json.loads(BODY); body["stream"] = True
    result = gateway.forward("/v1/responses", json.dumps(body).encode(), "Bearer local-test-only")
    assert result.content == content
    assert json.loads(seen[0].content)["stream"] is True
    ledger = json.loads(gateway.path.read_text())["attempts"][0]
    assert ledger["provider_usage"]["output_tokens"] == 0
    assert ledger["provider_usage"]["input_tokens"] == 10
    assert "synthetic-private-response" not in gateway.path.read_text()


def test_partial_provider_usage_remains_unknown(tmp_path):
    gateway, seen = make(tmp_path, handler=lambda _: httpx.Response(200, json={"model":"gpt-5-nano",
        "usage":{"input_tokens":15,"output_tokens":None,"total_tokens":None}}))
    gateway.forward("/v1/responses", BODY, "Bearer local-test-only")
    usage = json.loads(gateway.path.read_text())["attempts"][0]["provider_usage"]
    assert usage["input_tokens"] == 15
    assert usage["output_tokens"] is None and usage["total_tokens"] is None
