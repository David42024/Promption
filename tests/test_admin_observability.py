"""Admin audit ordering and effective security-control state."""
from pathlib import Path
import sys

from src.utils.structured_logger import StructuredLogger


CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app.security_state import SecurityStateStore


def test_structured_logs_return_most_recent_first(tmp_path):
    audit = StructuredLogger(max_entries=3)
    audit._file_path = tmp_path / "audit.jsonl"
    audit.clear()
    for index in range(4):
        audit.log("INFO", "chat", f"event-{index}")
    assert [entry["message"] for entry in audit.get_logs(limit=2)] == ["event-3", "event-2"]


def test_security_state_controls_are_persisted(tmp_path):
    store = SecurityStateStore(str(tmp_path / "security-state.json"))
    disabled = store.update("filter", False, "admin@demo.shop")
    assert disabled["filter_enabled"] is False
    assert disabled["history"][0]["action"] == "filter:OFF"

    restored = SecurityStateStore(str(tmp_path / "security-state.json")).get()
    assert restored["filter_enabled"] is False
    assert restored["updated_by"] == "admin@demo.shop"

    reset = store.update("reset", None, "admin@demo.shop")
    assert reset["filter_enabled"] is True
    assert reset["output_guard_enabled"] is True
