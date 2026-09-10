"""
Slim API server - auth, billing, chain proxy only.
Tax computation runs client-side via Web Worker.

This replaces app.py as the production entry point. The old monolith
(app.py) is kept intact for backward compatibility and local CLI usage.

Routes provided:
    /api/health                - health check
    /api/auth/*                - Supabase auth proxy
    /api/billing/*             - Stripe billing & webhooks
    /api/chains/*              - chain RPC proxy (rate-limited, API keys server-side)
    /api/accountant/*          - slim CPA portal (invite/accept/list/revoke only)

What was REMOVED (now client-side):
    /api/wallets               - wallet CRUD (IndexedDB client-side)
    /api/import                - chain import (client fetches via /api/chains/*)
    /api/transactions          - tx viewer (client-side storage)
    /api/calculate             - cost basis engine (WASM/JS in Web Worker)
    /api/reports               - report generation (client-side)
    /api/harvest               - TLH dashboard (client-side)
    /api/tax                   - country-aware tax (bundled in client engine)
    /api/reconciliation        - 1099-DA (client-side)
    /api/source-of-funds       - source of funds (client-side)
    /api/estimate              - quick estimate (client-side)
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.web.routes.auth import router as auth_router
from src.web.routes.billing import router as billing_router
from src.web.routes.chain_proxy import router as chain_router
from src.web.routes.accountant_slim import router as accountant_router
from src.web.routes.estimate_slim import router as estimate_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CryptoTax DeFi API",
    version="2.0.0",
    description=(
        "Slim API server for CryptoTax DeFi. "
        "Handles auth, billing, and chain RPC proxy. "
        "Tax computation runs client-side."
    ),
)

# CORS - allow all origins for frontend flexibility (Vercel, localhost, custom domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wire routers
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(chain_router)
app.include_router(accountant_router)
app.include_router(estimate_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health check endpoint for Railway/Docker."""
    return JSONResponse(content={
        "status": "ok",
        "version": "2.0.0",
        "compute": "client-side",
        "endpoints": {
            "auth": "/api/auth",
            "billing": "/api/billing",
            "chains": "/api/chains",
            "accountant": "/api/accountant",
        },
    })


@app.get("/api/debug/etherscan-test")
async def debug_etherscan_test():
    """Temporary debug endpoint - test Etherscan v2 API directly. Remove after debugging."""
    import httpx
    from src.config import CHAIN_CONFIGS
    cfg = CHAIN_CONFIGS.get("ethereum")
    if not cfg:
        return JSONResponse(content={"error": "no ethereum config"})
    params = {
        "chainid": cfg.chain_id,
        "module": "account",
        "action": "txlist",
        "address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
        "startblock": 0,
        "endblock": 99999999,
        "page": 1,
        "offset": 3,
        "sort": "asc",
        "apikey": cfg.api_key,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(cfg.api_url, params=params)
        data = resp.json()
    return JSONResponse(content={
        "url_used": cfg.api_url,
        "chainid": cfg.chain_id,
        "api_key_set": bool(cfg.api_key),
        "api_key_prefix": cfg.api_key[:6] if cfg.api_key else "",
        "etherscan_status": data.get("status"),
        "etherscan_message": data.get("message"),
        "result_type": type(data.get("result")).__name__,
        "result_count": len(data.get("result", [])) if isinstance(data.get("result"), list) else "N/A",
        "result_preview": str(data.get("result", ""))[:300],
    })


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """Redirect to health check."""
    return JSONResponse(content={
        "message": "CryptoTax DeFi API v2.0.0 - tax computation runs client-side",
        "docs": "/docs",
        "health": "/api/health",
    })
