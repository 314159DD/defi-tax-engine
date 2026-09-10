"""
Chain RPC proxy - rate-limited proxy to blockchain APIs.

Routes:
    GET /api/chains/evm/{chain}/{address}        - proxy Etherscan-compatible API
    GET /api/chains/bitcoin/{address}             - proxy Blockstream API
    GET /api/chains/cosmos/{chain}/{address}      - proxy Cosmos LCD
    GET /api/chains/solana/{address}              - proxy Helius/Solana RPC
    GET /api/chains/prices                        - proxy CoinGecko price API
    GET /api/chains/supported                     - list supported chains

Why this exists:
    - API keys stay server-side (never exposed to browser)
    - Rate limiting per user prevents API key abuse
    - Price cache reduces CoinGecko calls
    - Returns normalized Transaction[] format for the client engine

All monetary values returned as strings (Decimal-safe).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from src.config import (
    CHAIN_CONFIGS,
    COINGECKO_API_KEY,
    COSMOS_LCD_ENDPOINTS,
    COSMOS_DENOMS,
    COSMOS_NATIVE_TOKENS,
    HELIUS_API_KEY,
    SUPPORTED_CHAINS,
)
from src.web.routes.auth import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chains", tags=["chains"])


# ---------------------------------------------------------------------------
# Rate limiter (per-user, 100 req/min)
# ---------------------------------------------------------------------------
_RATE_LIMIT = 100
_RATE_WINDOW = 60.0  # seconds

_user_buckets: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(user_id: str) -> None:
    """Token-bucket rate limiter: 100 requests per minute per user."""
    now = time.time()
    bucket = _user_buckets[user_id]
    _user_buckets[user_id] = [t for t in bucket if now - t < _RATE_WINDOW]
    if len(_user_buckets[user_id]) >= _RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded (100 requests/min). Please slow down.",
        )
    _user_buckets[user_id].append(now)


# ---------------------------------------------------------------------------
# Price cache (in-memory dict with 5-min TTL)
# ---------------------------------------------------------------------------
_PRICE_CACHE_TTL = 300  # 5 minutes

_price_cache: dict[str, tuple[float, dict[str, str]]] = {}
# key: cache_key (e.g. "bitcoin,ethereum"), value: (timestamp, {id: usd_price_str})


def _get_cached_prices(cache_key: str) -> Optional[dict[str, str]]:
    """Return cached prices if within TTL, else None."""
    entry = _price_cache.get(cache_key)
    if entry is None:
        return None
    ts, data = entry
    if time.time() - ts > _PRICE_CACHE_TTL:
        del _price_cache[cache_key]
        return None
    return data


def _set_cached_prices(cache_key: str, data: dict[str, str]) -> None:
    _price_cache[cache_key] = (time.time(), data)


# ---------------------------------------------------------------------------
# Shared HTTP client
# ---------------------------------------------------------------------------
_http_client: httpx.AsyncClient | None = None


async def _get_http() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


# ---------------------------------------------------------------------------
# Normalized transaction format for client engine
# ---------------------------------------------------------------------------

def _normalize_evm_tx(tx: dict, chain: str) -> dict:
    """Convert an Etherscan API tx to the normalized format the client expects."""
    value_wei = tx.get("value", "0")
    try:
        value_eth = str(Decimal(value_wei) / Decimal("1000000000000000000"))
    except Exception:
        value_eth = "0"

    gas_used = tx.get("gasUsed", tx.get("gas", "0"))
    gas_price = tx.get("gasPrice", "0")
    try:
        fee_eth = str(Decimal(gas_used) * Decimal(gas_price) / Decimal("1000000000000000000"))
    except Exception:
        fee_eth = "0"

    return {
        "tx_hash": tx.get("hash", ""),
        "chain": chain,
        "block_number": int(tx.get("blockNumber", 0)),
        "timestamp": tx.get("timeStamp", ""),
        "from_address": tx.get("from", "").lower(),
        "to_address": tx.get("to", "").lower(),
        "value": value_eth,
        "fee": fee_eth,
        "token_symbol": CHAIN_CONFIGS.get(chain, CHAIN_CONFIGS["ethereum"]).native_token,
        "is_error": tx.get("isError", "0") == "1",
        "method_id": tx.get("methodId", ""),
        "function_name": tx.get("functionName", ""),
        "contract_address": tx.get("contractAddress", ""),
    }


def _normalize_evm_token_tx(tx: dict, chain: str) -> dict:
    """Convert an Etherscan ERC-20 token transfer to normalized format."""
    decimals = int(tx.get("tokenDecimal", "18"))
    try:
        value = str(Decimal(tx.get("value", "0")) / Decimal(10 ** decimals))
    except Exception:
        value = "0"

    return {
        "tx_hash": tx.get("hash", ""),
        "chain": chain,
        "block_number": int(tx.get("blockNumber", 0)),
        "timestamp": tx.get("timeStamp", ""),
        "from_address": tx.get("from", "").lower(),
        "to_address": tx.get("to", "").lower(),
        "value": value,
        "fee": "0",
        "token_symbol": tx.get("tokenSymbol", "UNKNOWN"),
        "token_name": tx.get("tokenName", ""),
        "token_address": tx.get("contractAddress", "").lower(),
        "is_error": False,
        "tx_type": "token_transfer",
    }


def _normalize_btc_tx(tx: dict) -> dict:
    """Convert a Blockstream API tx to normalized format."""
    # Sum outputs for total value (simplified - client engine does proper I/O matching)
    total_out = sum(
        out.get("value", 0)
        for out in tx.get("vout", [])
    )
    total_in = sum(
        vin.get("prevout", {}).get("value", 0)
        for vin in tx.get("vin", [])
    )
    fee = total_in - total_out if total_in > total_out else 0

    return {
        "tx_hash": tx.get("txid", ""),
        "chain": "bitcoin",
        "block_number": tx.get("status", {}).get("block_height", 0),
        "timestamp": str(tx.get("status", {}).get("block_time", "")),
        "from_address": "",  # Bitcoin doesn't have simple from/to
        "to_address": "",
        "value": str(Decimal(total_out) / Decimal("100000000")),  # satoshis -> BTC
        "fee": str(Decimal(fee) / Decimal("100000000")),
        "token_symbol": "BTC",
        "is_error": not tx.get("status", {}).get("confirmed", False),
        "inputs": [
            {
                "address": vin.get("prevout", {}).get("scriptpubkey_address", ""),
                "value": str(Decimal(vin.get("prevout", {}).get("value", 0)) / Decimal("100000000")),
            }
            for vin in tx.get("vin", [])
        ],
        "outputs": [
            {
                "address": out.get("scriptpubkey_address", ""),
                "value": str(Decimal(out.get("value", 0)) / Decimal("100000000")),
            }
            for out in tx.get("vout", [])
        ],
    }


def _normalize_cosmos_tx(tx: dict, chain: str) -> dict:
    """Convert a Cosmos LCD tx to normalized format."""
    body = tx.get("tx", {}).get("body", {})
    messages = body.get("messages", [])
    tx_response = tx.get("tx_response", tx)

    # Extract first transfer message info
    from_addr = ""
    to_addr = ""
    amount = "0"
    denom = ""

    for msg in messages:
        msg_type = msg.get("@type", "")
        if "MsgSend" in msg_type:
            from_addr = msg.get("from_address", "")
            to_addr = msg.get("to_address", "")
            amounts = msg.get("amount", [])
            if amounts:
                raw_amount = amounts[0].get("amount", "0")
                denom = amounts[0].get("denom", "")
                # Convert from micro-units
                try:
                    amount = str(Decimal(raw_amount) / Decimal("1000000"))
                except Exception:
                    amount = raw_amount
            break

    token = COSMOS_DENOMS.get(denom, denom.upper())

    return {
        "tx_hash": tx_response.get("txhash", ""),
        "chain": chain,
        "block_number": int(tx_response.get("height", 0)),
        "timestamp": tx_response.get("timestamp", ""),
        "from_address": from_addr,
        "to_address": to_addr,
        "value": amount,
        "fee": "0",
        "token_symbol": token,
        "is_error": tx_response.get("code", 0) != 0,
    }


def _normalize_solana_tx(tx: dict) -> dict:
    """Convert a Helius enhanced tx to normalized format."""
    return {
        "tx_hash": tx.get("signature", ""),
        "chain": "solana",
        "block_number": tx.get("slot", 0),
        "timestamp": str(tx.get("timestamp", "")),
        "from_address": tx.get("feePayer", ""),
        "to_address": "",
        "value": "0",
        "fee": str(Decimal(tx.get("fee", 0)) / Decimal("1000000000")),  # lamports -> SOL
        "token_symbol": "SOL",
        "is_error": tx.get("transactionError") is not None,
        "description": tx.get("description", ""),
        "type": tx.get("type", "UNKNOWN"),
        "token_transfers": tx.get("tokenTransfers", []),
        "native_transfers": tx.get("nativeTransfers", []),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/supported")
async def supported_chains():
    """Return list of supported chains."""
    evm_chains = [
        {
            "name": name,
            "native_token": cfg.native_token,
            "chain_id": cfg.chain_id,
            "type": "evm",
        }
        for name, cfg in CHAIN_CONFIGS.items()
    ]
    other = [
        {"name": "bitcoin", "native_token": "BTC", "type": "utxo"},
        {"name": "solana", "native_token": "SOL", "type": "solana"},
    ]
    for chain_name, endpoint in COSMOS_LCD_ENDPOINTS.items():
        other.append({
            "name": chain_name,
            "native_token": COSMOS_NATIVE_TOKENS.get(chain_name, ""),
            "type": "cosmos",
        })
    return JSONResponse(content={"chains": evm_chains + other})


@router.get("/evm/{chain}/{address}")
async def evm_proxy(
    chain: str,
    address: str,
    action: str = Query("txlist", description="Etherscan action: txlist, tokentx, txlistinternal"),
    startblock: int = Query(0),
    endblock: int = Query(99999999),
    page: int = Query(1),
    offset: int = Query(100, le=10000),
    user: dict = Depends(verify_jwt),
):
    """Proxy Etherscan-compatible API for EVM chains. Returns normalized transactions."""
    chain = chain.lower()
    if chain not in CHAIN_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unsupported EVM chain '{chain}'. Supported: {list(CHAIN_CONFIGS.keys())}")

    _check_rate_limit(user["sub"])

    cfg = CHAIN_CONFIGS[chain]
    if not cfg.api_key:
        raise HTTPException(status_code=503, detail=f"API key not configured for {chain}")

    allowed_actions = {"txlist", "tokentx", "txlistinternal"}
    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Allowed: {allowed_actions}")

    params = {
        "chainid": cfg.chain_id,
        "module": "account",
        "action": action,
        "address": address,
        "startblock": startblock,
        "endblock": endblock,
        "page": page,
        "offset": offset,
        "sort": "asc",
        "apikey": cfg.api_key,
    }

    http = await _get_http()
    request_url = f"{cfg.api_url}?chainid={cfg.chain_id}&module=account&action={action}&address={address}"
    try:
        resp = await http.get(cfg.api_url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream API error: {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach {chain} API: {exc}") from exc

    print(f"[CHAIN_PROXY] {request_url} => status={data.get('status')} message={data.get('message')} result_preview={str(data.get('result', ''))[:200]}", flush=True)

    if data.get("status") != "1" and data.get("message") != "No transactions found":
        raw_result = data.get("result", "")
        error_detail = raw_result if isinstance(raw_result, str) else str(data.get("message", ""))
        full_error = f"{error_detail} [url={cfg.api_url} chainid={cfg.chain_id} key={'SET' if cfg.api_key else 'EMPTY'}]"
        return JSONResponse(content={
            "chain": chain,
            "address": address,
            "transactions": [],
            "raw_message": full_error,
        })

    raw_txs = data.get("result", [])
    if not isinstance(raw_txs, list):
        raw_txs = []

    # Normalize based on action type
    if action == "tokentx":
        normalized = [_normalize_evm_token_tx(tx, chain) for tx in raw_txs]
    else:
        normalized = [_normalize_evm_tx(tx, chain) for tx in raw_txs]

    return JSONResponse(content={
        "chain": chain,
        "address": address,
        "transactions": normalized,
        "count": len(normalized),
    })


@router.get("/bitcoin/{address}")
async def bitcoin_proxy(
    address: str,
    user: dict = Depends(verify_jwt),
):
    """Proxy Blockstream API for Bitcoin. Returns normalized transactions."""
    _check_rate_limit(user["sub"])

    url = f"https://blockstream.info/api/address/{address}/txs"

    http = await _get_http()
    try:
        resp = await http.get(url)
        resp.raise_for_status()
        raw_txs = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Blockstream API error: {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Blockstream API: {exc}") from exc

    if not isinstance(raw_txs, list):
        raw_txs = []

    normalized = [_normalize_btc_tx(tx) for tx in raw_txs]

    return JSONResponse(content={
        "chain": "bitcoin",
        "address": address,
        "transactions": normalized,
        "count": len(normalized),
    })


@router.get("/cosmos/{chain}/{address}")
async def cosmos_proxy(
    chain: str,
    address: str,
    limit: int = Query(50, le=100),
    user: dict = Depends(verify_jwt),
):
    """Proxy Cosmos LCD API. Returns normalized transactions."""
    chain = chain.lower()
    if chain not in COSMOS_LCD_ENDPOINTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported Cosmos chain '{chain}'. Supported: {list(COSMOS_LCD_ENDPOINTS.keys())}",
        )

    _check_rate_limit(user["sub"])

    base_url = COSMOS_LCD_ENDPOINTS[chain]

    # Query sent transactions
    url = f"{base_url}/cosmos/tx/v1beta1/txs"
    params = {
        "events": f"transfer.sender='{address}'",
        "pagination.limit": str(limit),
        "order_by": "ORDER_BY_DESC",
    }

    http = await _get_http()
    try:
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Cosmos LCD error: {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Cosmos LCD: {exc}") from exc

    raw_txs = data.get("tx_responses", [])
    txs_with_body = []
    for i, tx_resp in enumerate(raw_txs):
        txs_data = data.get("txs", [])
        tx_body = txs_data[i] if i < len(txs_data) else {}
        combined = {"tx": tx_body, "tx_response": tx_resp}
        txs_with_body.append(combined)

    normalized = [_normalize_cosmos_tx(tx, chain) for tx in txs_with_body]

    return JSONResponse(content={
        "chain": chain,
        "address": address,
        "transactions": normalized,
        "count": len(normalized),
    })


@router.get("/solana/{address}")
async def solana_proxy(
    address: str,
    limit: int = Query(50, le=100),
    user: dict = Depends(verify_jwt),
):
    """Proxy Helius API for Solana. Returns normalized enhanced transactions."""
    if not HELIUS_API_KEY:
        raise HTTPException(status_code=503, detail="Helius API key not configured")

    _check_rate_limit(user["sub"])

    url = f"https://api.helius.xyz/v0/addresses/{address}/transactions"
    params = {
        "api-key": HELIUS_API_KEY,
        "limit": limit,
    }

    http = await _get_http()
    try:
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        raw_txs = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Helius API error: {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach Helius API: {exc}") from exc

    if not isinstance(raw_txs, list):
        raw_txs = []

    normalized = [_normalize_solana_tx(tx) for tx in raw_txs]

    return JSONResponse(content={
        "chain": "solana",
        "address": address,
        "transactions": normalized,
        "count": len(normalized),
    })


@router.get("/prices")
async def prices_proxy(
    ids: str = Query(..., description="Comma-separated CoinGecko IDs (e.g. bitcoin,ethereum,solana)"),
    vs_currencies: str = Query("usd", description="Target currency"),
    user: dict = Depends(verify_jwt),
):
    """
    Proxy CoinGecko /simple/price API.
    Cached for 5 minutes to stay within rate limits.
    """
    _check_rate_limit(user["sub"])

    # Normalize and sort for consistent cache key
    id_list = sorted(set(i.strip().lower() for i in ids.split(",") if i.strip()))
    cache_key = f"{','.join(id_list)}|{vs_currencies.lower()}"

    cached = _get_cached_prices(cache_key)
    if cached is not None:
        return JSONResponse(content={"prices": cached, "cached": True})

    url = "https://api.coingecko.com/api/v3/simple/price"
    params: dict[str, str] = {
        "ids": ",".join(id_list),
        "vs_currencies": vs_currencies,
    }
    if COINGECKO_API_KEY:
        params["x_cg_demo_api_key"] = COINGECKO_API_KEY

    http = await _get_http()
    try:
        resp = await http.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"CoinGecko API error: {exc.response.status_code}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to reach CoinGecko: {exc}") from exc

    # Convert to string prices (Decimal-safe for client)
    prices: dict[str, str] = {}
    for coin_id, price_data in data.items():
        if isinstance(price_data, dict):
            for currency, price in price_data.items():
                prices[f"{coin_id}_{currency}"] = str(price)

    _set_cached_prices(cache_key, prices)

    return JSONResponse(content={"prices": prices, "cached": False})
