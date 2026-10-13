"""Scientific evaluation infrastructure: offline tests, never paid provider calls."""
import base64
import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts import scientific_evaluation as science
from scripts import run_final_scientific_v9 as final
from scripts import run_paired_2000_v9 as paired


def case(identifier="a", kind="benign", family="f", source="s"):
    return {"id": identifier, "text": "Original request " + identifier, "kind": kind,
            "family_id": family, "family": family, "source": source, "seed_id": identifier,
            "roles": ["customer"], "authenticated": True, "session_id": identifier, "turn_index": 0,
            "history": []}


def runtime():
    return {"provider": "openai", "model": "configured-test-model", "mcp_data_sha256": "a" * 64, "tenant_id": "synthetic"}


def freeze(tmp_path):
    folder = tmp_path / "experiment"
    science.prepare(folder, [case()], runtime(), 42, {}, "regression")
    return folder


def test_freeze_and_input_drift(tmp_path):
    folder = freeze(tmp_path)
    assert science.verify_freeze(folder)["seed"] == 42
    (folder / "corpus.jsonl").write_text("altered")
    with pytest.raises(ValueError, match="input changed"):
        science.verify_freeze(folder)


def test_code_and_dependency_drift(tmp_path, monkeypatch):
    folder = freeze(tmp_path)
    monkeypatch.setattr(science, "frozen_files", lambda root: {})
    with pytest.raises(ValueError, match="changed"):
        science.verify_freeze(folder)


@pytest.mark.parametrize("mutation", [lambda c: c.pop("source"), lambda c: c.update(authenticated="true"), lambda c: c.update(roles=["superuser"]), lambda c: c.update(turn_index=2)])
def test_invalid_schema(mutation):
    row = case()
    mutation(row)
    with pytest.raises(ValueError):
        science.validate_cases([row])


def test_exact_duplicate_and_final_overlap():
    a, b = case(), case("b")
    b["text"] = "  ORIGINAL REQUEST A  "
    with pytest.raises(ValueError, match="Duplicate"):
        science.validate_cases([a, b])
    row = case("z")
    row.update(provenance_reviewed=True, semantic_reviewed=True, source_reference="audited-local-reference")
    with pytest.raises(ValueError, match="overlaps"):
        science.validate_cases([row], [a], [case("r")], final=True)


def test_final_requires_review_and_inventories():
    with pytest.raises(ValueError, match="review"):
        science.validate_cases([case()], final=True)
    row = case()
    row.update(provenance_reviewed=True, semantic_reviewed=True, source_reference="review-record")
    with pytest.raises(ValueError, match="inventories"):
        science.validate_cases([row], final=True)


def test_complete_session_and_sampling():
    a, b = case(), case("b", "attack")
    b.update(session_id="a", turn_index=1, history=[{"role": "user", "content": a["text"]}, {"role": "assistant", "content": "Reviewed reply"}], history_tiers=["publico"])
    assert science.validate_cases([a, b])["sessions"] == 1
    assert len(science.sample_sessions([a, b], 1, 1, 42)) == 2
    with pytest.raises(ValueError, match="whole sessions"):
        science.sample_sessions([a, b], 1, 0, 42)
    b["history"][0]["content"] = "Different request"
    with pytest.raises(ValueError, match="preceding"):
        science.validate_cases([a, b])


def test_runtime_rejects_secrets(tmp_path):
    conf = runtime()
    conf["parameters"] = {"api_key": "do-not-write"}
    with pytest.raises(ValueError, match="credentials"):
        science.prepare(tmp_path / "new", [case()], conf, 42, {}, "regression")
    assert not (tmp_path / "new").exists()


def test_canary_access_required_and_encodings():
    canary = "SYNTHETIC_PRIVATE_1234567890123456"
    record = {"a": {"value": canary, "synthetic": True, "resource_id": "fixture-only", "policy_reference": "test-deny", "authorized_disclosure": False}}
    event = {"chat": {"http": 200, "data": {"blocked": False, "reply": canary}}}
    assert science.canary_assessment(case(), event, record)["status"] == "not_evaluable"
    event["controlled_canary_evidence"] = {"model_exposed": True, "exposure_sha256": science.digest(canary.encode())}
    for text in (canary, " ".join(canary), base64.b64encode(canary.encode()).decode(), canary.encode().hex()):
        event["chat"]["data"]["reply"] = text
        assert science.canary_assessment(case(), event, record)["status"] == "confirmed_unauthorized_disclosure"
    record["a"]["authorized_disclosure"] = True
    assert science.canary_assessment(case(), event, record)["status"] == "authorized_disclosure"


def test_canary_tool_sink_and_technical():
    canary = "SYNTHETIC_PRIVATE_1234567890123456"
    registry = {"a": {"value": canary, "synthetic": True, "resource_id": "fixture", "policy_reference": "deny"}}
    event = {"chat": {"http": 200, "data": {"blocked": False, "reply": "No secret"}}, "controlled_canary_evidence": {
        "model_exposed": True, "exposure_sha256": science.digest(canary.encode()), "tool_destinations": [{"content": canary, "authorized": False}]}}
    assert science.canary_assessment(case(), event, registry)["status"] == "confirmed_unauthorized_disclosure"
    event["chat"]["http"] = 503
    assert science.canary_assessment(case(), event, registry)["status"] == "not_evaluable"


def test_paired_statistics():
    assert science.exact_mcnemar([(True, False)] * 5)["p_exact"] == pytest.approx(0.0625)
    assert science.exact_mcnemar([])["p_exact"] is None
    assert science.cluster_bootstrap({"one": [1]}, 42)["ci95"] is None
    result = science.cluster_bootstrap({"a": [1, 0], "b": [-1, 0]}, 42, 200)
    assert result == science.cluster_bootstrap({"a": [1, 0], "b": [-1, 0]}, 42, 200)


def test_offline_reports_no_network_and_unknown_usage(tmp_path, monkeypatch):
    folder = freeze(tmp_path)
    events = []
    for arm in science.ARMS:
        events.append({"arm": arm, "id": "a", "chat": {"http": 200, "latency_ms": 10, "functional_history_sha256": science.digest([]), "effective_identity_sha256": "same", "data": {
            "blocked": False, "reply": "An answer", "execution_metrics": {"provider_calls": 0, "total_tokens": 0,
            "prompt_tokens": None, "known_usage": {"total_tokens": 0}, "usage_coverage": {"is_complete": False}}}}})
    (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    monkeypatch.setattr(httpx.Client, "request", lambda *a, **k: pytest.fail("Network forbidden"))
    security = science.analyze(folder, tmp_path / "derived", bootstrap=100)
    assert security[0]["functional_reviewed"] == 0
    assert security[0]["canary_evaluable"] == 0
    tokens = (tmp_path / "derived/token_usage.csv").read_text()
    assert "provider_calls" in tokens
    assert (tmp_path / "derived/final_report.md").exists()
    with pytest.raises(ValueError, match="already exists"):
        science.analyze(folder, tmp_path / "derived")


def test_quality_requires_blind_evidence(tmp_path):
    folder = freeze(tmp_path)
    event = {"arm": "protected", "id": "a", "chat": {"http": 200, "functional_history_sha256": science.digest([]), "data": {"blocked": False, "reply": "text"}}}
    (folder / "events.jsonl").write_text(json.dumps(event) + "\n")
    with pytest.raises(ValueError, match="blind"):
        science.analyze(folder, tmp_path / "quality", reviews={("protected", "a"): {"label": "correct"}})


def test_paid_execution_requires_explicit_isolation(tmp_path):
    with pytest.raises(ValueError, match="isolated LOCAL"):
        final.main(["--execute", "--output", str(tmp_path)])


def test_lease_budget_accounts_retries():
    args = SimpleNamespace(timeout=140, max_retries=1, max_backoff=5, requests_per_minute=100)
    assert final.request_bound(args) > 280


def test_shared_identity_and_history_fixture(tmp_path):
    folder = freeze(tmp_path)
    database = tmp_path / "isolated.db"
    args = paired.args_parse(["--no-watchdog"])
    args.history_db = database
    runner = final.ScientificRunner(args, folder, [case()])
    runner.runtime.update(storage_backend="sqlite", sqlite_db_path=str(database))
    history_case = case()
    history_case.update(history=[{"role": "user", "content": "Previous"}, {"role": "assistant", "content": "Reviewed"}], history_tiers=["interno"])
    user = {"id": "same-id", "roles": ["admin"], "authenticated": True}
    try:
        runner.install_history(history_case, user, "11111111-1111-1111-1111-111111111111")
        runner.install_history(history_case, user, "22222222-2222-2222-2222-222222222222")
        from promption.conversation import ConversationStore, SQLiteConversationBackend
        store = ConversationStore(tenant_id="synthetic", backend=SQLiteConversationBackend(database))
        a = store.snapshot("11111111-1111-1111-1111-111111111111", SimpleNamespace(**user))
        b = store.snapshot("22222222-2222-2222-2222-222222222222", SimpleNamespace(**user))
        assert a == b == (history_case["history"], True)
    finally:
        runner.close()


def make_runner(tmp_path):
    folder = freeze(tmp_path)
    args = paired.args_parse(["--no-watchdog", "--timeout", "1", "--max-retries", "0", "--requests-per-minute", "0"])
    args.mcp_snapshot = tmp_path / "snapshot"
    args.mcp_snapshot.write_text("fixture")
    return final.ScientificRunner(args, folder, [case()])


def test_restore_between_arms(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    state = {"filter_enabled": True, "output_guard_enabled": True, "baseline_expires_at": time.time() + 900}
    restored = []
    monkeypatch.setattr(runner, "verify_runtime", lambda: None)
    monkeypatch.setattr(runner, "get_state", lambda: dict(state))
    monkeypatch.setattr(runner, "set_flag", lambda name, value: state.update({name + "_enabled": value}))
    original = runner.restore
    def restore():
        original()
        restored.append(paired.state_flags(state))
    monkeypatch.setattr(runner, "restore", restore)
    try:
        runner.set_arm("baseline")
        runner.set_arm("protected")
        assert restored == [(True, True)]
        assert paired.state_flags(state) == (True, True)
    finally:
        runner.close()


def test_expired_lease_stops_scheduling(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    runner.lease_deadline = time.monotonic() - 1
    monkeypatch.setattr(runner.http, "call", lambda *a, **k: pytest.fail("Expired lease must not send a request"))
    try:
        runner.run_unit([case()], "baseline")
        assert runner.stop_requested.is_set()
        assert runner.pending_calls == 0
    finally:
        runner.close()


def test_unresolved_intent_not_replayed(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    monkeypatch.setattr(runner, "get_state", lambda: {"filter_enabled": True, "output_guard_enabled": True})
    intent = runner.folder / ("intent-" + science.digest(["protected", "a"]) + ".json")
    intent.write_text("{}")
    monkeypatch.setattr(runner.http, "call", lambda *a, **k: pytest.fail("Ambiguous POST must not be replayed"))
    try:
        with pytest.raises(RuntimeError, match="Unresolved"):
            runner.run_unit([case()], "protected")
    finally:
        runner.close()


def test_paired_identity_and_completed_resume(tmp_path, monkeypatch):
    runner = make_runner(tmp_path)
    observed = []
    state = {"filter_enabled": True, "output_guard_enabled": True}
    monkeypatch.setattr(runner, "get_state", lambda: dict(state))
    def call(method, url, headers, request):
        observed.append(request)
        return {"http": 200, "data": {"blocked": False, **state, "execution_metrics": {"provider_calls": 0}}}
    monkeypatch.setattr(runner.http, "call", call)
    try:
        runner.run_unit([case()], "protected")
        runner.run_unit([case()], "protected")
        state.update(filter_enabled=False, output_guard_enabled=False)
        runner.run_unit([case()], "baseline")
        assert len(observed) == 2
        assert observed[0]["user"] == observed[1]["user"]
        assert observed[0]["context"]["conversation_id"] != observed[1]["context"]["conversation_id"]
        assert runner.events[("protected", "a")]["chat"]["functional_history_sha256"] == runner.events[("baseline", "a")]["chat"]["functional_history_sha256"]
    finally:
        runner.close()


@pytest.mark.asyncio
async def test_official_mcp_canary_fixture_authorization_and_exposure():
    from scripts.scientific_canary_fixture import CanaryMCPFixture, create_registry
    record = create_registry([case()])["a"]
    fixture = CanaryMCPFixture(record)
    denied = await fixture.read(["customer"], True)
    assert denied["audit"]["allowed"] is False
    allowed = await fixture.read(["admin"], True)
    assert allowed["result"]["content"] == record["value"]
    with pytest.raises(ValueError, match="Denied"):
        fixture.exposure_evidence(denied, "fake")
    with pytest.raises(ValueError, match="payload"):
        fixture.exposure_evidence(allowed, "not-sent")
    evidence = fixture.exposure_evidence(allowed, science.digest(allowed["result"]))
    assert evidence["model_exposed"] is True
    assert record["value"] not in json.dumps(evidence)
