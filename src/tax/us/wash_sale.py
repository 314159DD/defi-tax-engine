"""
Wash sale detection and basis adjustment for US tax rules.

IRS wash sale rule: If you sell a security at a loss and buy a substantially
identical security within 30 days before or after the sale, the loss is
disallowed. The disallowed loss is added to the cost basis of the replacement
lot.

IMPORTANT: As of 2026, the IRS has not definitively ruled that crypto wash
sales apply. However, Section 1091 may be extended to digital assets in future
guidance. This module provides tracking and warnings for conservative filers.

All monetary values use Decimal - NEVER float.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from src.calculator.lots import TaxLot

# Wash sale window: 30 days before + 30 days after = 61-day total window
_WASH_SALE_WINDOW = 30


@dataclass
class WashSaleWindow:
    """
    Represents a wash sale window triggered by a disposal at a loss.

    The window spans from (sale_date - 30 days) to (sale_date + 30 days).
    Any acquisition of the same token within this window creates a wash sale:
    the loss is disallowed and added to the replacement lot's basis.
    """
    token: str
    sale_date: date
    window_start: date          # sale_date - 30 days
    window_end: date            # sale_date + 30 days
    disallowed_loss: Decimal    # the loss that is disallowed (positive value)
    replacement_lot_id: Optional[str] = None  # lot that triggered the wash sale
    disposal_tx_hash: Optional[str] = None    # the sale transaction

    def as_dict(self) -> dict:
        return {
            "token": self.token,
            "sale_date": str(self.sale_date),
            "window_start": str(self.window_start),
            "window_end": str(self.window_end),
            "disallowed_loss": str(self.disallowed_loss),
            "replacement_lot_id": self.replacement_lot_id,
            "disposal_tx_hash": self.disposal_tx_hash,
        }

    def is_active(self, as_of: date) -> bool:
        """Check if this wash sale window is currently active."""
        return self.window_start <= as_of <= self.window_end


def check_wash_sales(
    disposals: list[dict],
    acquisitions: list[dict],
) -> list[WashSaleWindow]:
    """
    Detect wash sale violations by cross-referencing disposals with acquisitions.

    Args:
        disposals: list of disposal dicts with keys:
            token, disposal_date (date|str), gain_loss_usd (Decimal|str),
            tx_hash (optional)
        acquisitions: list of acquisition dicts with keys:
            token, acquisition_date (date|str), lot_id (str)

    Returns:
        List of WashSaleWindow objects for each detected wash sale.
    """
    windows: list[WashSaleWindow] = []

    for disposal in disposals:
        # Only consider disposals at a loss
        gl = _to_decimal(disposal.get("gain_loss_usd", "0"))
        if gl >= Decimal("0"):
            continue

        token = disposal["token"].upper()
        sale_date = _to_date(disposal["disposal_date"])
        if sale_date is None:
            continue

        loss_amount = abs(gl)
        window_start = sale_date - timedelta(days=_WASH_SALE_WINDOW)
        window_end = sale_date + timedelta(days=_WASH_SALE_WINDOW)

        # Find any acquisition of the same token within the window
        replacement_lot_id = None
        for acq in acquisitions:
            acq_token = acq["token"].upper()
            if acq_token != token:
                continue

            acq_date = _to_date(acq["acquisition_date"])
            if acq_date is None:
                continue

            if window_start <= acq_date <= window_end:
                # This acquisition is within the wash sale window
                replacement_lot_id = acq.get("lot_id") or acq.get("id")
                break  # first match is sufficient

        if replacement_lot_id is not None:
            windows.append(WashSaleWindow(
                token=token,
                sale_date=sale_date,
                window_start=window_start,
                window_end=window_end,
                disallowed_loss=loss_amount,
                replacement_lot_id=replacement_lot_id,
                disposal_tx_hash=disposal.get("tx_hash"),
            ))

    return windows


def get_active_windows(
    token: str,
    as_of_date: date,
    windows: list[WashSaleWindow],
) -> list[WashSaleWindow]:
    """
    Filter wash sale windows to only those that are currently active
    for a specific token.

    Args:
        token: token symbol (case-insensitive)
        as_of_date: the date to check against
        windows: all known wash sale windows

    Returns:
        List of active WashSaleWindow objects for the given token.
    """
    token_upper = token.upper()
    return [
        w for w in windows
        if w.token == token_upper and w.is_active(as_of_date)
    ]


def adjust_basis_for_wash_sale(
    window: WashSaleWindow,
    replacement_lot: TaxLot,
) -> TaxLot:
    """
    Adjust the cost basis of the replacement lot for a wash sale.

    The disallowed loss is added to the cost basis of the replacement lot,
    effectively deferring the loss recognition until the replacement lot
    is eventually disposed of.

    Args:
        window: the WashSaleWindow with the disallowed loss
        replacement_lot: the TaxLot whose basis should be adjusted

    Returns:
        The same TaxLot object with adjusted cost_basis_usd (mutated in place
        and also returned for convenience).
    """
    replacement_lot.cost_basis_usd = replacement_lot.cost_basis_usd + window.disallowed_loss
    return replacement_lot


def would_trigger_wash_sale(
    token: str,
    proposed_sale_date: date,
    acquisitions: list[dict],
) -> Optional[dict]:
    """
    Pre-sale check: would selling this token on the proposed date trigger
    a wash sale based on recent acquisitions?

    Args:
        token: token symbol
        proposed_sale_date: the date the user wants to sell
        acquisitions: list of acquisition dicts with token, acquisition_date

    Returns:
        Dict with warning info if wash sale would be triggered, else None.
    """
    token_upper = token.upper()
    window_start = proposed_sale_date - timedelta(days=_WASH_SALE_WINDOW)
    window_end = proposed_sale_date + timedelta(days=_WASH_SALE_WINDOW)

    for acq in acquisitions:
        if acq["token"].upper() != token_upper:
            continue

        acq_date = _to_date(acq["acquisition_date"])
        if acq_date is None:
            continue

        if window_start <= acq_date <= window_end:
            return {
                "warning": True,
                "token": token_upper,
                "acquisition_date": str(acq_date),
                "sale_date": str(proposed_sale_date),
                "window_start": str(window_start),
                "window_end": str(window_end),
                "lot_id": acq.get("lot_id") or acq.get("id"),
            }

    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_decimal(value) -> Decimal:
    """Safely convert to Decimal."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _to_date(value) -> Optional[date]:
    """Safely convert to date."""
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None
