"""
Quick estimate route for the slim backend - no DB, no auth required.

POST /api/estimate
  body: { "address": "0x...", "chain": "ethereum", "year": 2024 }

Fetches the last 100 normal transactions from Etherscan for the address,
runs a simple FIFO calculation in memory (incoming = acquisition at 0 basis,
outgoing ETH = disposal). Returns a top-level gains/losses estimate.

This is intentionally shallow - it's a marketing teaser. The real computation
runs client-side via the Web Worker with full DeFi categorization.

Rate-limited: 5 requests / minute per IP.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import CHAIN_CONFIGS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/estimate", tags=["estimate"])

# ---------------------------------------------------------------------------
# Rate limiter (5 req/min per IP)
# ---------------------------------------------------------------------------
_RATE_LIMIT = 5
_RATE_WINDOW = 60.0

_ip_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(ip: str) -> None:
    now = time.time()
    _ip_buckets[ip] = [t for t in _ip_buckets[ip] if now - t < _RATE_WINDOW]
    if len(_ip_buckets[ip]) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Sign up for a full account to remove limits.",
        )
    _ip_buckets[ip].append(now)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class EstimateRequest(BaseModel):
    address: str
    chain: str = "ethereum"
    year: int | None = None


# ---------------------------------------------------------------------------
# Etherscan helper
# ---------------------------------------------------------------------------
async def _fetch_etherscan_txs(address: str, chain: str, api_key: str, api_url: str, chain_id: int = 1) -> list[dict]:
    """Fetch the last 100 normal transactions for an address from Etherscan."""
    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 100,
        "sort": "asc",
        "apikey": api_key,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(api_url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") != "1":
        return []
    return data.get("result", [])


# ---------------------------------------------------------------------------
# Quick in-memory FIFO estimate
# ---------------------------------------------------------------------------
def _quick_fifo(txs: list[dict], address: str, year: int, native_token: str) -> dict:
    """
    Minimal FIFO on native-token movements.

    Rules (simplified for estimate only):
    - Incoming ETH (to == address, value > 0) → acquisition lot at value=0 basis
      (we don't know the purchase price from Etherscan alone)
    - Outgoing ETH (from == address, value > 0) → disposal; proceeds = 0 (unknown)

    Since we don't have historical prices, we can at minimum count:
    - tx_count: total transactions
    - incoming_count / outgoing_count
    - And flag that a full calculation requires sign-up

    This is intentionally a teaser, not a tax calculation.
    """
    address = address.lower()
    tx_count = len(txs)
    year_txs = []

    for tx in txs:
        ts = int(tx.get("timeStamp", 0))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if dt.year == year:
            year_txs.append(tx)

    incoming = sum(
        1 for tx in year_txs
        if tx.get("to", "").lower() == address
        and Decimal(tx.get("value", "0")) > 0
        and tx.get("isError", "0") == "0"
    )
    outgoing = sum(
        1 for tx in year_txs
        if tx.get("from", "").lower() == address
        and Decimal(tx.get("value", "0")) > 0
        and tx.get("isError", "0") == "0"
    )

    return {
        "tx_count": tx_count,
        "year_tx_count": len(year_txs),
        "incoming": incoming,
        "outgoing": outgoing,
    }


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------
@router.post("")
async def quick_estimate(body: EstimateRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    year = body.year or datetime.now(timezone.utc).year
    address = body.address.lower().strip()
    chain = body.chain.lower().strip()

    # Look up chain config
    cfg = CHAIN_CONFIGS.get(chain, CHAIN_CONFIGS.get("ethereum"))
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"Unsupported chain: {chain}")

    api_key = getattr(cfg, "api_key", None) or ""
    api_url = getattr(cfg, "api_url", None) or ""
    native_token = getattr(cfg, "native_token", "ETH")
    chain_id = getattr(cfg, "chain_id", 1)

    if not api_key or not api_url:
        return JSONResponse(content={
            "address": address,
            "chain": chain,
            "year": year,
            "imported": False,
            "transaction_count": 0,
            "teaser_message": (
                f"Chain {chain} is supported in the full version. "
                "Sign up to import your wallet and calculate your exact tax liability."
            ),
            "cta": "Sign up free - no credit card required",
        })

    try:
        txs = await _fetch_etherscan_txs(address, chain, api_key, api_url, chain_id)
    except Exception as e:
        logger.warning(f"Etherscan fetch failed for {address} on {chain}: {e}")
        return JSONResponse(content={
            "address": address,
            "chain": chain,
            "year": year,
            "imported": False,
            "transaction_count": 0,
            "teaser_message": (
                "Could not reach the blockchain right now. "
                "Sign up to import your full transaction history."
            ),
            "cta": "Sign up free",
        })

    if not txs:
        return JSONResponse(content={
            "address": address,
            "chain": chain,
            "year": year,
            "imported": False,
            "transaction_count": 0,
            "teaser_message": (
                f"No transactions found for {address[:8]}…{address[-4:]} on {chain}. "
                "Try a different address or chain."
            ),
            "cta": "Sign up free - supports 13 chains",
        })

    stats = _quick_fifo(txs, address, year, native_token)

    teaser = (
        f"Found {stats['tx_count']} transactions. "
        f"In {year}: {stats['year_tx_count']} transactions "
        f"({stats['incoming']} incoming, {stats['outgoing']} outgoing {native_token}). "
        "For exact gains/losses with DeFi categorization - LP positions, bridges, "
        "staking rewards, and phantom-gain-free LP deposits - sign up for the full report."
    )

    return JSONResponse(content={
        "address": address,
        "chain": chain,
        "year": year,
        "imported": True,
        "transaction_count": stats["tx_count"],
        "year_transaction_count": stats["year_tx_count"],
        "teaser_message": teaser,
        "cta": "Get your full tax report - free for up to 100 transactions",
        "note": "Full FIFO/HIFO/LIFO calculation and DeFi categorization runs in your browser - no financial data stored on our servers.",
    })
