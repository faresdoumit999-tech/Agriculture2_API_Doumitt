"""Dual-currency engine: every amount is stored in USD and SYP.

Rules
-----
* ``USD`` input requires a positive exchange rate.  ``amount_syp`` is derived.
* ``SYP`` input stores the SYP amount directly.  If a positive exchange rate
  was supplied the USD equivalent is derived, otherwise USD stays ``0.0``.
"""

from __future__ import annotations

from dataclasses import dataclass

from exceptions import CurrencyError

SUPPORTED_CURRENCIES = {"USD", "SYP"}


def money(value: float) -> float:
    """Round monetary values to 6 decimals to avoid float drift."""
    return round(float(value), 6)


def quantity(value: float) -> float:
    return round(float(value), 6)


@dataclass(frozen=True)
class CurrencyAmounts:
    usd: float
    syp: float
    exchange_rate: float


def resolve_exchange_rate(currency: str, exchange_rate: float | None) -> float:
    """Validate a currency/rate pair and return the effective rate."""
    currency = currency.upper().strip()
    if currency not in SUPPORTED_CURRENCIES:
        raise CurrencyError("العملة يجب أن تكون USD أو SYP فقط.")

    rate = float(exchange_rate or 0)
    if rate < 0:
        raise CurrencyError("سعر الصرف يجب أن يكون أكبر من أو يساوي صفراً.")
    if currency == "USD" and rate <= 0:
        raise CurrencyError("سعر الصرف مطلوب ويجب أن يكون أكبر من صفر عند الإدخال بالدولار.")
    return rate


def dual_amount(amount: float, currency: str, exchange_rate: float | None) -> CurrencyAmounts:
    """Convert an amount in ``currency`` to both USD and SYP."""
    amount = float(amount)
    if amount < 0:
        raise CurrencyError("المبلغ لا يمكن أن يكون سالباً.")

    currency = currency.upper().strip()
    rate = resolve_exchange_rate(currency, exchange_rate)

    if currency == "USD":
        return CurrencyAmounts(usd=money(amount), syp=money(amount * rate), exchange_rate=rate)

    return CurrencyAmounts(
        usd=money(amount / rate) if rate > 0 else 0.0,
        syp=money(amount),
        exchange_rate=rate,
    )


def compute_purchase(
    quantity_value: float,
    unit_price: float,
    currency: str,
    exchange_rate: float | None,
) -> dict:
    """Return unit prices and totals in both currencies for a purchase line."""
    quantity_value = float(quantity_value)
    if quantity_value <= 0:
        raise CurrencyError("الكمية يجب أن تكون أكبر من صفر.")
    if float(unit_price) <= 0:
        raise CurrencyError("سعر الوحدة يجب أن يكون أكبر من صفر.")

    unit = dual_amount(unit_price, currency, exchange_rate)
    total = dual_amount(quantity_value * float(unit_price), currency, exchange_rate)
    return {
        "currency": currency.upper(),
        "exchange_rate": unit.exchange_rate,
        "unit_price_usd": unit.usd,
        "unit_price_syp": unit.syp,
        "total_cost_usd": total.usd,
        "total_cost_syp": total.syp,
    }


def convert_invoice_amount(amount: float, currency: str, exchange_rate: float) -> tuple[float, float]:
    """Convert an invoice-currency amount into ``(usd, syp)``."""
    amounts = dual_amount(amount, currency, exchange_rate)
    return amounts.usd, amounts.syp


def syp_to_usd(amount_syp: float, exchange_rate: float) -> float:
    if exchange_rate <= 0:
        return 0.0
    return money(float(amount_syp) / float(exchange_rate))
