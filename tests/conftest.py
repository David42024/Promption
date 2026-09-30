import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _reset_singletons():
    """The MLFilter is a process-wide singleton; reset between tests to avoid
    cross-test state (fake encoders vs real model)."""
    from src.filter.ml_filter import MLFilter
    MLFilter._instance = None
    yield
    MLFilter._instance = None


@pytest.fixture
def scope_in_scope(monkeypatch):
    """Stub the independent semantic classifier for unrelated chat unit tests."""
    from promption import AsyncScopeGuard
    from app import routes

    async def evaluate(request):
        return {"classification": "IN_SCOPE", "reason": "in_scope"}

    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(evaluate))
