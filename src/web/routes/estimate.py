"""
Quick Estimate route - no authentication required.

POST /api/estimate
  body: { "address": "0x...", "chain": "ethereum" }
  Returns: top-level gains/losses summary (no lot detail, no auth needed).
  Rate-limited per IP: 5 requests / minute (in-process token bucket).

The estimate is intentionally shallow:
  - Reads from the local transactions DB (if already imported).
  - If the wallet hasn't been imported, returns a teaser response with a
    sign-up CTA.
  - Only returns aggregated totals - never individual lot details.
  - All monetary values returned as strings (Decimal-safe).
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/estimate", tags=["estimate"])

# ---------------------------------------------------------------------------
# In-process rate limiter (token bucket, per IP, 5 req/min)
# ---------------------------------------------------------------------------
_RATE_LIMIT = 5          # max requests
_RATE_WINDOW = 60.0      # seconds

_ip_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    bucket = _ip_buckets[ip]
    # Drop timestamps outside the window
    _ip_buckets[ip] = [t for t in bucket if now - t < _RATE_WINDOW]
    if len(_ip_buckets[ip]) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please sign up for a full account to remove limits.",
        )
    _ip_buckets[ip].append(now)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class EstimateRequest(BaseModel):
    address: str
    chain: str = "ethereum"
    year: int | None = None


class EstimateResponse(BaseModel):
    address: str
    chain: str
    year: int
    imported: bool
    total_gains: str
    total_losses: str
    net_gain_loss: str
    transaction_count: int
    teaser_message: str
    cta: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post("", response_model=EstimateResponse)
async def quick_estimate(body: EstimateRequest, request: Request):
    """
    Return a top-level gains/losses estimate for a wallet address.
    No authentication required - rate-limited by IP.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    year = body.year or datetime.now(timezone.utc).year
    address = body.address.lower().strip()
    chain = body.chain.lower().strip()

    # Import the DB lazily so this module can be tested independently
    try:
        from src.config import DB_PATH
        from src.storage.database import Database, DisposalRepository, TransactionRepository

        db = Database(DB_PATH)
        tx_repo = TransactionRepository(db)
        disposal_repo = DisposalRepository(db)
    except Exception:
        # DB unavailable - return a teaser-only response
        return EstimateResponse(
            address=address,
            chain=chain,
            year=year,
            imported=False,
            total_gains="0",
            total_losses="0",
            net_gain_loss="0",
            transaction_count=0,
            teaser_message=(
                "We couldn't reach the calculation engine right now. "
                "Sign up for a free account to import your wallet and see your full tax report."
            ),
            cta="Sign up free - no credit card required",
        )

    # Check if we have any transactions for this address
    with db.connect() as conn:
        tx_count = conn.execute(
            "SELECT COUNT(*) AS n FROM transactions WHERE raw_json LIKE ? AND chain = ?",
            (f"%{address}%", chain),
        ).fetchone()["n"]

    if tx_count == 0:
        return EstimateResponse(
            address=address,
            chain=chain,
            year=year,
            imported=False,
            total_gains="0",
            total_losses="0",
            net_gain_loss="0",
            transaction_count=0,
            teaser_message=(
                f"No data found for {address[:8]}…{address[-4:]} on {chain}. "
                "Sign up to import your full transaction history and calculate your exact tax liability."
            ),
            cta="Import your wallet - free for up to 100 transactions",
        )

    # We have data - compute a quick FIFO estimate from disposals table
    disposals = disposal_repo.get_by_year(year, "FIFO")

    total_gains = Decimal("0")
    total_losses = Decimal("0")

    for d in disposals:
        gl = d["gain_loss_usd"]
        if gl > 0:
            total_gains += gl
        else:
            total_losses += gl

    net = total_gains + total_losses

    teaser_parts: list[str] = []
    if abs(float(net)) < 1:
        teaser_parts.append("Your estimated net gain/loss is near zero this year.")
    elif float(net) > 0:
        teaser_parts.append(f"You may owe taxes on ~{fmt_usd(net)} in net gains.")
    else:
        teaser_parts.append(f"You have ~{fmt_usd(abs(net))} in net losses - potential tax savings available.")

    teaser_parts.append(
        "Sign up for the full report: Form 8949, Schedule D, TurboTax export, and HIFO/LIFO optimization."
    )

    return EstimateResponse(
        address=address,
        chain=chain,
        year=year,
        imported=True,
        total_gains=str(total_gains),
        total_losses=str(total_losses),
        net_gain_loss=str(net),
        transaction_count=tx_count,
        teaser_message=" ".join(teaser_parts),
        cta="Get your full tax report - free for up to 100 transactions",
    )


def fmt_usd(val: Decimal) -> str:
    return f"${float(val):,.2f}"
