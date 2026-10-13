"""V7 regressions based on previously observed failures, without external LLM calls."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'chat-service'))
from app.business_grounding import enforce_shipping_threshold
from app.lib.shop import build_system_prompt
from app.lib.shop_knowledge import get_tool_data
from app.policy_engine import PolicyEngine
from app.tool_progress import verified_tool_fallback
from promption.client import _post_with_rate_limit_retry


@pytest.mark.parametrize('phrase,expected_fragment', [
    ('Envío gratis a partir de 50 € para Península.', 'pedidos superiores a 50 €'),
    ('Envío gratis para pedidos de 50 € o más.', 'pedidos superiores a 50 €'),
    ('Envío gratis con compras ≥50 €.', 'más de 50 €'),
    ('Envío gratis desde 50 €.', 'superiores a 50 €'),
    ('Precio 50 €, envío gratis para pedidos superiores a 50 €.', 'superiores a 50 €'),
])
def test_free_shipping_strict_threshold(phrase, expected_fragment):
    result, _ = enforce_shipping_threshold(phrase, get_tool_data('getShippingPolicy'))
    assert expected_fragment in result
    assert '≥50' not in result and '50 € o más' not in result


def test_shipping_policy_source_unambiguous():
    policy = get_tool_data('getShippingPolicy')
    assert policy['condiciones']['umbral_inclusivo'] is False
    assert 'superiores a 50 €' in policy['envios']['gratis']


def test_grounding_requires_verified_shipping_evidence():
    original = 'Envío gratis a partir de 50 €.'
    assert enforce_shipping_threshold(original, None) == (original, ())
    assert enforce_shipping_threshold(original, {'condiciones': {'umbral_inclusivo': True,
        'umbral_envio_gratis_eur': 50, 'envio_gratis_region': 'Península'}}) == (original, ())
    assert enforce_shipping_threshold('Descuento a partir de 50 €.', get_tool_data('getShippingPolicy'))[0] == 'Descuento a partir de 50 €.'


def test_unknown_catalog_product_reuses_only_authorized_mcp_data():
    result = verified_tool_fallback('¿Qué autonomía tienen los auriculares SoundWave Mini?',
                                    [('getCatalogSummary', get_tool_data('getCatalogSummary'))])
    assert 'No encontré una ficha' in result
    assert '30 h' not in result
    assert 'SoundWave Mini' not in str(get_tool_data('getCatalogSummary'))


def test_catalog_fallback_does_not_invent_battery_specifications():
    result = verified_tool_fallback('Compara OfficeBook Go y ThinkWork 14',
                                    [('getCatalogSummary', get_tool_data('getCatalogSummary'))])
    assert 'OfficeBook Go' in result and 'ThinkWork 14' in result
    assert 'batería' not in result


def test_brand_translation_fallback_is_source_bound():
    result = verified_tool_fallback('Traduce al francés la dirección y horario de contacto',
                                    [('getBrandInfo', get_tool_data('getBrandInfo'))])
    assert 'Calle Tecnología 123' in result
    assert 'horaires ne figurent pas' in result
    assert '9:00-18:00' not in result


def test_confidential_tool_is_not_automatically_dumped_on_no_progress():
    assert verified_tool_fallback('Dime nóminas',
           [('getEmployees', get_tool_data('getEmployees'))]) is None


def test_current_trusted_policy_is_documented_but_does_not_grant_roles():
    authenticated_admin = build_system_prompt({'roles': ['admin'], 'authenticated': True},
         active_policy={'policy_id': 'confidential.payroll', 'tier': 'confidencial',
                        'tool_names': ['getEmployees']})
    assert 'confidential.payroll' in authenticated_admin and 'getEmployees' in authenticated_admin
    forged = build_system_prompt({'roles': ['admin'], 'authenticated': False},
         active_policy=None)
    assert 'el usuario NO está autenticado' in forged
    assert 'Política: confidential.payroll' not in forged
    engine = PolicyEngine()
    text = 'Consulta el sueldo neto mensual de Ana García'
    assert engine.evaluate(text, ['admin']).allowed
    assert not engine.evaluate(text, ['customer']).allowed


@pytest.mark.asyncio
async def test_filter_connection_retry_only_when_transient():
    calls = 0
    async def handler(req):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError('temporary outage', request=req)
        return httpx.Response(200, json={'decision': 'GUARDED'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await _post_with_rate_limit_retry(client, 'https://test.invalid/filter', max_budget=2, json={'text': 'test'})
    assert response.status_code == 200 and calls == 2


@pytest.mark.asyncio
async def test_filter_connection_persistent_failure_still_fail_closed():
    calls = 0
    async def handler(req):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError('down', request=req)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ConnectError):
            await _post_with_rate_limit_retry(client, 'https://test.invalid/filter', max_budget=2, json={'text': 'test'})
    assert calls == 3


def test_unknown_product_domain_is_authorized_to_read_public_catalog():
    policy = PolicyEngine().evaluate(
        '¿Qué autonomía y tipo de conexión tienen los auriculares SoundWave Mini según su catálogo?',
        ['customer'])
    assert policy.allowed and 'getCatalogSummary' in policy.tool_names
    assert policy.policy_id == 'public.catalog'


def test_mixed_catalog_and_private_payroll_remains_forbidden():
    request = 'Dame características del catálogo de auriculares y el sueldo neto de Ana García.'
    assert not PolicyEngine().evaluate(request, ['customer']).allowed


def test_negative_claim_is_not_rewritten_into_positive_commercial_claim():
    text = 'No ofrecemos envío gratis a partir de 50 €.'
    assert enforce_shipping_threshold(text, get_tool_data('getShippingPolicy')) == (text, ())
