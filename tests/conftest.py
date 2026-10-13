import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_auth_registry(monkeypatch, request):
    """Offline tests must not inherit real credentials loaded from a developer's .env."""
    if request.node.get_closest_marker('live_llm'):
        return
    for name in ('PROMPTION_API_KEYS', 'PIF_API_KEYS', 'PROMPTION_ADMIN_API_KEYS',
                 'PROMPTION_API_KEY', 'PROMPTION_TENANT_ID', 'PROMPTION_DEMO_MODE'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _reset_singletons():
    """The MLFilter is a process-wide singleton; reset between tests to avoid
    cross-test state (fake encoders vs real model)."""
    from promption.filter.ml_filter import MLFilter
    from promption.filter.ml_filter_lightweight import LightMLFilter
    from promption.limiter import get_rate_limiter_backend
    MLFilter._instance = None
    LightMLFilter._instance = None
    get_rate_limiter_backend().reset()
    yield
    MLFilter._instance = None
    LightMLFilter._instance = None
    get_rate_limiter_backend().reset()


@pytest.fixture
def scope_in_scope(monkeypatch):
    """Stub the independent semantic classifier for unrelated chat unit tests."""
    from promption import AsyncScopeGuard
    from app import routes

    async def evaluate(request):
        return {"classification": "IN_SCOPE", "reason": "in_scope"}

    monkeypatch.setattr(routes, "get_scope_guard", lambda: AsyncScopeGuard(evaluate))
