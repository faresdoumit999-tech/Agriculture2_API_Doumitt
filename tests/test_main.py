"""End-to-end tests for DOUMITT Agricultural ERP."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import create_project, register_and_login


@pytest.mark.asyncio
async def test_register_login_and_profile(client: AsyncClient) -> None:
    register = await client.post(
        "/api/register",
        json={"username": "newfarmer", "password": "secret123", "phone_number": "0912345678"},
    )
    assert register.status_code == 201
    body = register.json()
    assert body["username"] == "newfarmer"
    assert body["role"] == "user"
    assert "hashed_password" not in body

    duplicate = await client.post(
        "/api/register",
        json={"username": "newfarmer", "password": "secret123"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["success"] is False

    bad_login = await client.post(
        "/api/login", data={"username": "newfarmer", "password": "wrong-password"}
    )
    assert bad_login.status_code == 401

    login = await client.post(
        "/api/login", data={"username": "newfarmer", "password": "secret123"}
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    profile = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert profile.status_code == 200
    assert profile.json()["username"] == "newfarmer"

    unauthorized = await client.get("/api/me")
    assert unauthorized.status_code == 401


@pytest.mark.asyncio
async def test_project_creation_and_tenant_isolation(client: AsyncClient) -> None:
    headers = await register_and_login(client, "farmer_project")
    project = await create_project(client, headers)

    assert project["greenhouse_count"] == 10
    assert project["sharecropper_name"] == "أبو أحمد"
    assert project["sharecropper_profit_pct"] == 20
    assert project["sharecropper_expense_pct"] == 20
    assert project["financials"]["net_profit_syp"] == 0

    listing = await client.get("/api/projects", headers=headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    other_headers = await register_and_login(client, "other_farmer")
    forbidden = await client.get(f"/api/projects/{project['id']}", headers=other_headers)
    assert forbidden.status_code == 404

    other_list = await client.get("/api/projects", headers=other_headers)
    assert other_list.json() == []


@pytest.mark.asyncio
async def test_warehouse_partial_consumption_and_restore(client: AsyncClient) -> None:
    headers = await register_and_login(client, "farmer_warehouse")
    project = await create_project(client, headers)

    purchase = await client.post(
        "/api/warehouse/items",
        headers=headers,
        json={
            "product_name": "مبيد حشري",
            "pharmacy_name": "صيدلية الأمل",
            "purchase_date": "2026-02-01",
            "quantity": 1.0,
            "unit": "لتر",
            "currency": "USD",
            "unit_price": 20.0,
            "exchange_rate": 15000,
        },
    )
    assert purchase.status_code == 201, purchase.text
    item = purchase.json()
    assert item["initial_quantity"] == 1.0
    assert item["remaining_quantity"] == 1.0
    assert item["total_cost_usd"] == 20.0
    assert item["total_cost_syp"] == 300000.0
    assert item["unit_price_syp"] == 300000.0

    consumption = await client.post(
        "/api/warehouse/consume",
        headers=headers,
        json={
            "warehouse_item_id": item["id"],
            "project_id": project["id"],
            "quantity_used": 0.25,
            "date": "2026-02-05",
            "category": "PESTICIDE",
        },
    )
    assert consumption.status_code == 201, consumption.text
    payload = consumption.json()

    assert payload["warehouse_item"]["remaining_quantity"] == 0.75
    assert payload["expense"]["quantity_used"] == 0.25
    assert payload["expense"]["expense_nature"] == "DAILY"
    assert payload["expense"]["category"] == "PESTICIDE"
    assert payload["expense"]["pharmacy_name"] == "صيدلية الأمل"
    assert payload["expense"]["total_amount_usd"] == 5.0
    assert payload["expense"]["total_amount_syp"] == 75000.0
    assert payload["expense"]["enters_sharecropper_calc"] is False

    overdraw = await client.post(
        "/api/warehouse/consume",
        headers=headers,
        json={
            "warehouse_item_id": item["id"],
            "project_id": project["id"],
            "quantity_used": 2.0,
            "date": "2026-02-06",
        },
    )
    assert overdraw.status_code == 400
    assert overdraw.json()["error"]["code"] == "insufficient_stock"

    inventory = await client.get("/api/warehouse/items", headers=headers)
    assert inventory.status_code == 200
    assert inventory.json()[0]["remaining_quantity"] == 0.75
    assert inventory.json()[0]["consumed_quantity"] == 0.25

    expenses = await client.get(
        f"/api/expenses?project_id={project['id']}", headers=headers
    )
    assert len(expenses.json()) == 1
    expense_id = expenses.json()[0]["id"]

    deleted = await client.delete(f"/api/expenses/{expense_id}", headers=headers)
    assert deleted.status_code == 200

    inventory_after = await client.get("/api/warehouse/items", headers=headers)
    assert inventory_after.json()[0]["remaining_quantity"] == 1.0


@pytest.mark.asyncio
async def test_invoice_sharecropper_and_per_greenhouse_metrics(client: AsyncClient) -> None:
    headers = await register_and_login(client, "farmer_invoice")
    project = await create_project(client, headers)

    invoice = await client.post(
        "/api/invoices",
        headers=headers,
        json={
            "project_id": project["id"],
            "date": "2026-03-10",
            "currency": "SYP",
            "exchange_rate": 15000,
            "commission_amount": 35000,
            "polystyrene_expense": 20000,
            "vehicle_fuel_expense": 10000,
            "other_deductions": 0,
            "items": [
                {
                    "crop_name": "باذنجان",
                    "box_count": 10,
                    "gross_weight": 110,
                    "net_weight": 100,
                    "unit_price": 5000,
                },
                {
                    "crop_name": "خيار",
                    "box_count": 5,
                    "gross_weight": 55,
                    "net_weight": 50,
                    "unit_price": 4000,
                },
            ],
        },
    )
    assert invoice.status_code == 201, invoice.text
    data = invoice.json()

    assert data["total_gross"] == pytest.approx(700000)
    assert data["net_total"] == pytest.approx(635000)
    assert data["sharecropper_applied_profit_pct"] == 20
    assert data["sharecropper_applied_expense_pct"] == 20
    assert data["sharecropper_gross_share_syp"] == pytest.approx(133000)
    assert data["sharecropper_expense_deduction_syp"] == pytest.approx(6000)
    assert data["sharecropper_net_payout_syp"] == pytest.approx(127000)
    assert data["owner_net_profit_syp"] == pytest.approx(508000)
    assert data["net_total_usd"] == pytest.approx(635000 / 15000, rel=1e-6)
    assert data["sharecropper_net_payout_usd"] == pytest.approx(127000 / 15000, rel=1e-6)
    assert len(data["items"]) == 2
    assert data["items"][0]["subtotal"] == pytest.approx(500000)

    expense = await client.post(
        "/api/expenses",
        headers=headers,
        json={
            "project_id": project["id"],
            "date": "2026-03-11",
            "expense_nature": "DAILY",
            "category": "POLYSTYRENE",
            "item_name": "فلين إضافي",
            "quantity_used": 1,
            "unit_price": 30000,
            "currency": "SYP",
            "exchange_rate": 15000,
        },
    )
    assert expense.status_code == 201, expense.text
    expense_data = expense.json()
    assert expense_data["enters_sharecropper_calc"] is True
    assert expense_data["sharecropper_deduction_syp"] == pytest.approx(6000)

    report = await client.get(
        f"/api/reports/project/{project['id']}/full-audit", headers=headers
    )
    assert report.status_code == 200, report.text
    audit = report.json()

    assert audit["sales"]["net_sales_syp"] == pytest.approx(635000)
    assert audit["sales"]["by_crop"][0]["crop_name"] == "باذنجان"
    assert audit["sales"]["by_crop"][0]["net_weight"] == 100

    assert audit["expenses"]["total_syp"] == pytest.approx(30000)
    assert audit["expenses"]["seasonal_syp"] == 0
    assert audit["expenses"]["daily_syp"] == pytest.approx(30000)
    assert audit["expenses"]["by_category"][0]["category"] == "POLYSTYRENE"

    sharecropper = audit["sharecropper"]
    assert sharecropper["gross_share_syp"] == pytest.approx(133000)
    assert sharecropper["invoice_expense_deduction_syp"] == pytest.approx(6000)
    assert sharecropper["separate_expense_deduction_syp"] == pytest.approx(6000)
    assert sharecropper["net_payout_syp"] == pytest.approx(121000)

    assert audit["per_greenhouse_metrics"]["cost_syp"] == pytest.approx(3000)
    assert audit["per_greenhouse_metrics"]["revenue_syp"] == pytest.approx(63500)
    assert audit["per_greenhouse_metrics"]["net_profit_syp"] == pytest.approx(48400)

    assert audit["net_profit"]["owner_net_profit_syp"] == pytest.approx(484000)
    assert audit["net_profit"]["owner_net_profit_usd"] == pytest.approx(
        484000 / 15000, rel=1e-6
    )

    global_summary = await client.get("/api/reports/global-summary", headers=headers)
    assert global_summary.status_code == 200
    assert global_summary.json()["totals"]["net_profit_syp"] == pytest.approx(484000)

    history = await client.get("/api/crops/باذنجان/history", headers=headers)
    assert history.status_code == 200
    assert history.json()["total_net_weight"] == pytest.approx(100)
    assert history.json()["total_revenue_syp"] == pytest.approx(500000)
