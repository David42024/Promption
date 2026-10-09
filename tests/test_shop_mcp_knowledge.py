"""Exercise richer Shop data through the official MCP executor and existing ACL."""
import json
import sys
from pathlib import Path

import pytest

CHAT_SERVICE = Path(__file__).resolve().parents[1] / "chat-service"
if str(CHAT_SERVICE) not in sys.path:
    sys.path.insert(0, str(CHAT_SERVICE))

from app.lib.shop_knowledge import get_tool_data
from app.mcp_tools import MCPToolExecutor


CONTRACTS = {
    "getBrandInfo": {"brand": dict, "canales": dict},
    "getShippingPolicy": {"envios": dict, "garantias": dict, "horarios": dict},
    "getCatalogSummary": {"categorias": list},
    "getPromotions": {"promociones": list, "politicasDescuento": str},
    "getStockInfo": {"stockCritico": list, "proveedores": dict},
    "getMarketingCampaigns": {"campanas": list},
    "getEmployees": {"empleados": list, "totalPlantilla": int},
    "getVIPClients": {"vips": list, "totalVips": int},
    "getKPIStats": {"kpis": dict},
    "getRevenueReport": {"facturacionMensual": dict, "kpiAnual": dict},
    "getTopProducts": {"topProductos": list},
}
PUBLIC = {"getBrandInfo", "getShippingPolicy", "getCatalogSummary"}
INTERNAL = {"getPromotions", "getStockInfo", "getMarketingCampaigns"}
CONFIDENTIAL = set(CONTRACTS) - PUBLIC - INTERNAL


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", CONTRACTS)
async def test_enriched_data_preserves_mcp_contract_and_bounded_context(tool_name):
    executor = MCPToolExecutor()
    response = await executor.execute(tool_name, {}, ["admin"])
    assert response["audit"]["allowed"] is True
    data = response["result"]
    assert isinstance(data, dict)
    for key, value_type in CONTRACTS[tool_name].items():
        assert isinstance(data[key], value_type)
    assert data["fuente"]["datos_ficticios"] is True
    assert data["fuente"]["id"] == f"shop-demo.{tool_name}"
    assert len(json.dumps(data, ensure_ascii=False)) <= 8000
    specs = await executor.available(["admin"], True)
    spec = next(spec for spec in specs if spec.name == tool_name)
    schema = getattr(spec, "inputSchema", None) or getattr(spec, "input_schema", {})
    assert schema.get("required", []) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role,authenticated,allowed", [
    ("guest", False, PUBLIC), ("customer", True, PUBLIC),
    ("ventas", True, PUBLIC | INTERNAL), ("admin", True, set(CONTRACTS)),
])
async def test_expanded_knowledge_is_still_filtered_before_mcp_execution(role, authenticated, allowed):
    executor = MCPToolExecutor()
    for name in CONTRACTS:
        response = await executor.execute(name, {}, [role], authenticated=authenticated)
        assert response["audit"]["allowed"] is (name in allowed)
        if name not in allowed:
            assert response["result"] == {"error": "Permiso denegado"}
            assert "fuente" not in response["result"]
    for name in PUBLIC:
        data = (await executor.execute(name, {}, [role], authenticated=authenticated))["result"]
        assert not ({"empleados", "vips", "kpis", "stockCritico", "proveedores"} & data.keys())


def test_catalog_inventory_and_performance_reference_the_same_products():
    catalog = get_tool_data("getCatalogSummary")
    products = {product["sku"]: product for product in catalog["productos"]}
    assert len(products) == catalog["totalProductos"] == 16
    assert {product["categoria"] for product in products.values()} == set(catalog["categorias"])
    assert all(product["precio_eur"] > 0 and product["caracteristicas"] for product in products.values())
    for item in get_tool_data("getStockInfo")["stockCritico"]:
        assert item["sku"] in products
        assert item["producto"] == products[item["sku"]]["nombre"]
        assert 0 <= item["stock"] <= 5
    top = get_tool_data("getTopProducts")["topProductos"]
    assert len(top) == 5
    for item in top:
        assert item["producto"] == products[item["sku"]]["nombre"]
        assert int(item["ingresos"].rstrip("€")) == products[item["sku"]]["precio_eur"] * item["unidades"]
    assert [int(item["ingresos"].rstrip("€")) for item in top] == sorted(
        [int(item["ingresos"].rstrip("€")) for item in top], reverse=True)


def test_financial_periods_and_headcounts_are_consistent():
    employees, vips = get_tool_data("getEmployees"), get_tool_data("getVIPClients")
    assert len(employees["empleados"]) == employees["totalPlantilla"] == 15
    assert len(vips["vips"]) == vips["totalVips"] == 4
    assert len({employee["id"] for employee in employees["empleados"]}) == 15
    revenue = get_tool_data("getRevenueReport")
    kpis = get_tool_data("getKPIStats")["kpis"]
    assert len(revenue["facturacionMensual"]) == 12
    assert set(revenue["periodos_cerrados"]).isdisjoint(revenue["periodos_proyectados"])
    assert set(revenue["periodos_cerrados"] + revenue["periodos_proyectados"]) == set(revenue["facturacionMensual"])
    assert sum(int(value.rstrip("€")) for value in revenue["facturacionMensual"].values()) == kpis["facturacion_anual_eur"] == revenue["kpiAnual"]["total_eur"]
    assert kpis["beneficio_bruto_eur"] - kpis["gastos_operativos_eur"] == kpis["ebitda_eur"] == 412700
    assert kpis["empleados_totales"] == employees["totalPlantilla"]


@pytest.mark.asyncio
async def test_mcp_responses_are_isolated_from_mutation():
    executor = MCPToolExecutor()
    first = await executor.execute("getCatalogSummary", {}, ["customer"])
    first["result"]["productos"][0]["precio_eur"] = 0
    first["result"]["categorias"].clear()
    second = await executor.execute("getCatalogSummary", {}, ["customer"])
    assert second["result"]["productos"][0]["precio_eur"] == 750
    assert len(second["result"]["categorias"]) == 6
    direct = get_tool_data("getCatalogSummary")
    direct["productos"][0]["caracteristicas"].clear()
    assert get_tool_data("getCatalogSummary")["productos"][0]["caracteristicas"]
