"""Prepare, run explicitly authorized isolated experiments, or reprocess without network."""
from __future__ import annotations

import argparse
import math
import json
import os
import signal
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import scientific_evaluation as science
from scripts import run_paired_2000_v9 as paired


class ScientificRunner(paired.Runner):
    """Reuse HTTP/retry/watchdog/evidence contracts with strict per-block checks."""

    def __init__(self, args, folder, corpus):
        super().__init__(args, folder, corpus)
        self.runtime = science.verify_freeze(folder)["configured_runtime"]
        self.lease_deadline = None
        self.active_arm = None

    def verify_runtime(self):
        science.verify_freeze(self.folder)
        if science.digest(Path(self.args.mcp_snapshot).read_bytes()) != self.runtime["mcp_data_sha256"]:
            raise ValueError("Frozen MCP data changed")
        status = self.http.call("GET", self.args.chat_url + "/status", self.headers)
        if status["http"] != 200:
            raise RuntimeError("Backend attestation unavailable")
        llm = (status.get("data") or {}).get("llm") or {}
        frozen = self.folder / "scientific-backend-status.json"
        snapshot = paired.scrub({k: status["data"].get(k) for k in ("service", "version", "llm", "config", "policy_engine")}, self.secrets)
        if isinstance(snapshot.get("llm"), dict):
            snapshot["llm"].pop("connected", None)
        if frozen.exists():
            if json.loads(frozen.read_text()) != snapshot:
                raise RuntimeError("Backend configuration/status changed between blocks")
        else:
            if self.runtime["model"] not in paired.dump(llm):
                raise RuntimeError("Configured model not confirmed by backend status")
            if not llm.get("providers") or set(llm["providers"]) != {"openai"} or (status["data"].get("config") or {}).get("tenant_id") != self.runtime["tenant_id"]:
                raise RuntimeError("Provider/tenant does not match frozen experiment")
            paired.atomic_json(frozen, snapshot)

    def set_arm(self, arm):
        if self.active_arm is not None:
            self.must_restore = True
            self.restore()
        self.verify_runtime()
        self.must_restore = True
        super().set_arm(arm)
        state = self.get_state()
        if arm == "baseline":
            expiry = state.get("baseline_expires_at")
            if not isinstance(expiry, (int, float)):
                raise RuntimeError("Backend did not report its baseline lease")
            self.lease_deadline = time.monotonic() + max(0, expiry - time.time())
        else:
            self.lease_deadline = None
        self.active_arm = arm

    def install_history(self, case, user, conversation_id):
        history = case.get("history", [])
        if not history:
            return
        from promption.conversation import ConversationStore, SQLiteConversationBackend
        path = Path(self.runtime.get("sqlite_db_path", "")).resolve()
        if self.runtime.get("storage_backend") != "sqlite" or path != Path(self.args.history_db).resolve():
            raise ValueError("Fixed multi-turn replay needs the dedicated backend's declared SQLite DB")
        store = ConversationStore(tenant_id=self.runtime["tenant_id"], backend=SQLiteConversationBackend(path))
        identity = SimpleNamespace(**user)
        existing = store.snapshot(conversation_id, identity)[0]
        if existing:
            item = store.backend.get(store._key(conversation_id, identity), ttl_seconds=store.ttl_seconds)
            tiers = [pair["tier"] for pair in item.get("pairs", [])]
            if existing == history and tiers == case["history_tiers"]:
                store.security_snapshot(conversation_id, identity)
                return
            raise RuntimeError("Nonmatching fixture session; refusing ambiguous replay")
        for index in range(0, len(history), 2):
            store.record(conversation_id, identity, history[index]["content"], history[index+1]["content"], case["history_tiers"][index//2], [])
        if store.snapshot(conversation_id, identity)[0] != history:
            raise RuntimeError("Backend truncated fixed history; arms would not be comparable")

    def run_unit(self, unit, arm):
        for case in sorted(unit, key=lambda c: c["turn_index"]):
            if (arm, case["id"]) in self.events:
                continue
            with self.calls_lock:
                if self.stop_requested.is_set():
                    return
                reserve = self.args.provider_call_reservation
                if self.unknown_calls or self.provider_calls + self.pending_calls + reserve > self.args.max_provider_calls:
                    self.budget_stopped = True
                    return
                self.pending_calls += reserve
            started = False
            try:
                needed = request_bound(self.args)
                if self.lease_deadline is not None and self.lease_deadline - time.monotonic() < needed:
                    self.stop_requested.set()
                    return
                expected = arm == "protected"
                if paired.state_flags(self.get_state()) != (expected, expected):
                    raise RuntimeError("Protection state or baseline lease changed before request")
                user = {"id": "scientific-" + science.digest([str(self.folder), case["session_id"]])[:20],
                        "name": "Synthetic Validation", "email": "validation@example.invalid", "roles": case["roles"], "authenticated": case["authenticated"]}
                conversation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, str(self.folder) + arm + case["id"]))
                self.install_history(case, user, conversation_id)
                if case.get("history"):
                    history_response = self.http.call("POST", self.args.chat_url + "/conversation/history", self.headers,
                        {"conversation_id": conversation_id, "user": user})
                    payload = history_response.get("data") or {}
                    actual = [{"role": "user" if m.get("from") == "user" else "assistant", "content": m.get("text")}
                              for m in payload.get("messages", [])] if isinstance(payload, dict) else None
                    if history_response.get("http") != 200 or actual != case["history"]:
                        raise RuntimeError("Chat backend did not observe the identical fixed history; refusing generation")
                request = {"text": case["text"], "user": user, "context": {"conversation_id": conversation_id,
                    "request_id": science.digest([str(self.folder), arm, case["id"]])[:28]}}
                intent = self.folder / ("intent-" + science.digest([arm, case["id"]]) + ".json")
                if intent.exists():
                    raise RuntimeError("Unresolved prior request intent; reconcile evidence, do not replay a paid POST")
                paired.atomic_json(intent, {"arm": arm, "id": case["id"], "request_id": request["context"]["request_id"]})
                started = True
                chat = self.http.call("POST", self.args.chat_url + "/chat", self.headers, request)
                data = chat.get("data") or {}
                if isinstance(data, dict) and chat.get("http") == 200:
                    if data.get("filter_enabled") is not expected or data.get("output_guard_enabled") is not expected:
                        chat["arm_mismatch"] = True
                chat["pairing_id"] = case["id"]
                chat["functional_history_sha256"] = science.digest(case.get("history", []))
                chat["effective_identity_sha256"] = science.digest(user)
                self.write_event(arm, case, chat, {})
                intent.unlink()
                if chat.get("arm_mismatch"):
                    raise RuntimeError("Arm contamination recorded; experiment stopped")
            except BaseException:
                if started:
                    with self.calls_lock:
                        self.unknown_calls += 1
                raise
            finally:
                with self.calls_lock:
                    self.pending_calls -= reserve


def request_bound(args):
    return args.timeout * (args.max_retries + 1) + args.max_backoff * args.max_retries + (60 / args.requests_per_minute if args.requests_per_minute else 0) + 10


def parse(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--reprocess-only", action="store_true")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--development", type=Path)
    parser.add_argument("--regression", type=Path)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--mode", choices=("regression", "final"), default="regression")
    parser.add_argument("--benign", type=int, default=1000)
    parser.add_argument("--attack", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--analysis-output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--dedicated-instance", action="store_true")
    parser.add_argument("--mcp-snapshot", type=Path)
    parser.add_argument("--history-db", type=Path)
    parser.add_argument("--chat-url", default="http://127.0.0.1:8001/api/v1")
    parser.add_argument("--filter-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=140)
    parser.add_argument("--max-retries", type=int, default=1)
    parser.add_argument("--requests-per-minute", type=float, default=100)
    parser.add_argument("--max-provider-calls", type=int, default=15000)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--canary-registry", type=Path)
    args = parser.parse_args(argv)
    if min(args.benign, args.attack, args.max_retries, args.requests_per_minute) < 0 or args.concurrency < 1 or args.timeout <= 0 or args.max_provider_calls < 1:
        parser.error("Invalid counts or execution limits")
    if args.benign + args.attack == 0:
        parser.error("At least one case is required")
    return args


def main(argv=None):
    args = parse(argv)
    folder = args.output.resolve()
    if args.reprocess_only:
        reviews = {(r["arm"], r["id"]): r for r in science.read_jsonl(args.reviews)} if args.reviews else {}
        registry = json.loads(args.canary_registry.read_text()) if args.canary_registry else {}
        science.analyze(folder, args.analysis_output or folder / "scientific_analysis", registry, reviews)
        return 0
    if args.dry_run:
        if not args.corpus or not args.runtime:
            raise ValueError("dry-run requires original corpus and runtime declaration")
        rows = science.read_jsonl(args.corpus)
        development = science.read_jsonl(args.development) if args.development else []
        regression = science.read_jsonl(args.regression) if args.regression else []
        validation = science.validate_cases(rows, development, regression, args.mode == "final")
        rows = science.sample_sessions(rows, args.benign, args.attack, args.seed)
        runtime = json.loads(args.runtime.read_text(encoding="utf-8-sig"))
        science.prepare(folder, rows, runtime, args.seed, validation, args.mode)
        manifest = json.loads((folder / "experiment_manifest.json").read_text())
        manifest["execution_plan"] = {k: getattr(args, k) for k in ("chat_url", "filter_url", "concurrency", "timeout", "max_retries", "requests_per_minute", "max_provider_calls")}
        paired.atomic_json(folder / "experiment_manifest.json", manifest)
        (folder / "experiment_manifest.sha256").write_text(science.digest((folder / "experiment_manifest.json").read_bytes()))
        print(json.dumps({"prepared": str(folder), "per_arm": len(rows), "network_calls": 0}))
        return 0
    if not args.resume or not args.dedicated_instance or not paired.is_local(args.chat_url) or not paired.is_local(args.filter_url):
        raise ValueError("Execution requires --resume --dedicated-instance and isolated LOCAL backends")
    manifest = science.verify_freeze(folder)
    runtime = manifest["configured_runtime"]
    if not args.mcp_snapshot or science.digest(args.mcp_snapshot.read_bytes()) != runtime["mcp_data_sha256"]:
        raise ValueError("MCP data snapshot must match frozen runtime")
    if not os.environ.get("VALIDATION_CHAT_TOKEN"):
        raise ValueError("VALIDATION_CHAT_TOKEN required in environment, never files")
    rows = science.read_jsonl(folder / "corpus.jsonl")
    if manifest["execution_plan"] != {k: getattr(args, k) for k in manifest["execution_plan"]}:
        raise ValueError("Execution settings differ from frozen dry-run plan")
    if any(c.get("history") for c in rows) and not args.history_db:
        raise ValueError("Multi-turn fixed replay needs --history-db for the dedicated SQLite backend")
    execution = paired.args_parse(["--output", str(folder), "--concurrency", str(args.concurrency),
        "--timeout", str(args.timeout), "--max-retries", str(args.max_retries), "--max-backoff", "5",
        "--requests-per-minute", str(args.requests_per_minute), "--max-provider-calls", str(args.max_provider_calls),
        "--chat-url", args.chat_url, "--filter-url", args.filter_url])
    execution.mcp_snapshot, execution.history_db = args.mcp_snapshot, args.history_db
    lease = min(3600, float(runtime.get("baseline_max_seconds", 900)))
    longest = max(sum(c["session_id"] == sid for c in rows) for sid in {c["session_id"] for c in rows})
    if request_bound(execution) * longest >= lease - 20:
        raise ValueError("Session retry/time budget exceeds baseline lease; reduce timeout/retries or split reviewed fixtures")
    execution.blocks = math.ceil(len({c["session_id"] for c in rows}) / args.concurrency)
    config = {k: getattr(execution, k) for k in ("chat_url", "filter_url", "concurrency", "timeout", "max_retries", "requests_per_minute", "max_provider_calls", "blocks")}
    config_path = folder / "execution-settings.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError("Execution settings changed on resume")
    paired.atomic_json(config_path, config)
    runner = ScientificRunner(execution, folder, rows)
    handlers = {}
    for signum in (signal.SIGINT, signal.SIGTERM):
        handlers[signum] = signal.signal(signum, lambda *_: runner.stop_requested.set())
    try:
        runner.run()
    finally:
        try:
            if runner.must_restore:
                runner.restore()
        finally:
            runner.close()
            for signum, handler in handlers.items():
                signal.signal(signum, handler)
    target = args.analysis_output or folder / ("scientific_analysis_" + uuid.uuid4().hex[:8])
    science.analyze(folder, target)
    status = json.loads((folder / "execution-status.json").read_text())
    return 0 if status["status"] == "COMPLETE" and status["restoration_verified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
