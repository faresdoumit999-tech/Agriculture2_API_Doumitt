"""Sharecropper (المستلم بالحصة) settlement engine.

Invoice formulas (all values first computed in the invoice currency):

1. ``total_gross = Σ(net_weight × unit_price)``
2. ``sales_after_commission = total_gross - commission - other_deductions``
3. ``sharecropper_gross = sales_after_commission × profit_pct / 100``
4. ``sharecropper_deduction = (polystyrene + vehicle_fuel) × expense_pct / 100``
5. ``sharecropper_net = sharecropper_gross - sharecropper_deduction``
6. ``net_total = sales_after_commission - polystyrene - vehicle_fuel``
7. ``owner_net_profit = net_total - sharecropper_net``

Standalone expenses flagged with ``enters_sharecropper_calc`` deduct their
share from the sharecropper's final settlement.
"""

from __future__ import annotations

from collections.abc import Sequence

from models import ExpenseRecord, Invoice, Project
from schemas import InvoiceItemCreate
from services.currency_service import dual_amount, money, syp_to_usd


def calculate_invoice(
    items: Sequence[InvoiceItemCreate],
    *,
    commission_amount: float,
    polystyrene_expense: float,
    vehicle_fuel_expense: float,
    other_deductions: float,
    currency: str,
    exchange_rate: float,
    project: Project,
) -> dict:
    """Compute every monetary field of an invoice before persisting it."""
    rows: list[dict] = []
    total_gross = 0.0
    for item in items:
        subtotal = money(item.net_weight * item.unit_price)
        total_gross += subtotal
        rows.append(
            {
                "crop_name": item.crop_name.strip(),
                "box_count": item.box_count,
                "gross_weight": money(item.gross_weight),
                "net_weight": money(item.net_weight),
                "unit_price": money(item.unit_price),
                "subtotal": subtotal,
            }
        )

    total_gross = money(total_gross)
    sales_after_commission = money(
        total_gross - float(commission_amount) - float(other_deductions)
    )
    net_total = money(
        sales_after_commission - float(polystyrene_expense) - float(vehicle_fuel_expense)
    )

    has_sharecropper = bool(project.has_sharecropper)
    profit_pct = float(project.sharecropper_profit_pct) if has_sharecropper else 0.0
    expense_pct = float(project.sharecropper_expense_pct) if has_sharecropper else 0.0

    sharecropper_gross = money(sales_after_commission * profit_pct / 100.0)
    sharecropper_deduction = money(
        (float(polystyrene_expense) + float(vehicle_fuel_expense)) * expense_pct / 100.0
    )
    sharecropper_net = money(sharecropper_gross - sharecropper_deduction)
    owner_profit = money(net_total - sharecropper_net)

    net = dual_amount(net_total, currency, exchange_rate)
    payout = dual_amount(sharecropper_net, currency, exchange_rate)
    owner = dual_amount(owner_profit, currency, exchange_rate)
    gross_share = dual_amount(sharecropper_gross, currency, exchange_rate)
    deduction = dual_amount(sharecropper_deduction, currency, exchange_rate)
    net_usd, net_syp = net.usd, net.syp
    payout_usd, payout_syp = payout.usd, payout.syp
    owner_usd, owner_syp = owner.usd, owner.syp
    gross_share_usd, gross_share_syp = gross_share.usd, gross_share.syp
    deduction_usd, deduction_syp = deduction.usd, deduction.syp

    return {
        "items": rows,
        "total_gross": total_gross,
        "commission_amount": money(commission_amount),
        "polystyrene_expense": money(polystyrene_expense),
        "vehicle_fuel_expense": money(vehicle_fuel_expense),
        "other_deductions": money(other_deductions),
        "net_total": net_total,
        "net_total_usd": net_usd,
        "net_total_syp": net_syp,
        "sharecropper_applied_profit_pct": profit_pct,
        "sharecropper_applied_expense_pct": expense_pct,
        "sharecropper_gross_share_syp": gross_share_syp,
        "sharecropper_expense_deduction_syp": deduction_syp,
        "sharecropper_net_payout_syp": payout_syp,
        "sharecropper_net_payout_usd": payout_usd,
        "owner_net_profit_syp": owner_syp,
        "owner_net_profit_usd": owner_usd,
        # Exposed for reports/tests (not all are columns).
        "_sharecropper_gross_usd": gross_share_usd,
        "_sharecropper_deduction_usd": deduction_usd,
        "_sharecropper_net": sharecropper_net,
        "_owner_profit": owner_profit,
        "_sales_after_commission": sales_after_commission,
    }


def apply_expense_sharecropper(
    expense: ExpenseRecord,
    project: Project,
    *,
    enters: bool | None,
    custom_pct: float | None,
) -> None:
    """Apply (or clear) the sharecropper deduction of a standalone expense."""
    auto_enters = expense.category in {"POLYSTYRENE", "VEHICLE_FUEL"}
    effective_enters = auto_enters if enters is None else bool(enters)

    if not project.has_sharecropper:
        effective_enters = False

    pct = (
        float(custom_pct)
        if custom_pct is not None
        else float(project.sharecropper_expense_pct)
    )

    expense.enters_sharecropper_calc = effective_enters
    expense.custom_sharecropper_pct = custom_pct

    if not effective_enters:
        expense.sharecropper_deduction_usd = 0.0
        expense.sharecropper_deduction_syp = 0.0
        return

    expense.sharecropper_deduction_usd = money(expense.total_amount_usd * pct / 100.0)
    expense.sharecropper_deduction_syp = money(expense.total_amount_syp * pct / 100.0)


def invoice_syp_to_usd(invoice: Invoice, amount_syp: float) -> float:
    """Convert an invoice's SYP figure to USD using its exchange rate."""
    return syp_to_usd(amount_syp, float(invoice.exchange_rate or 0))
