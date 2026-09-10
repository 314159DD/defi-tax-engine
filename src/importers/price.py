"""
Historical price lookup using CoinGecko API with SQLite caching.

Same token + same date = same price. Cache aggressively.
CoinGecko free tier: ~10-30 req/min (no key needed for basic endpoints).

Fallback: DexScreener API for obscure DeFi tokens not on CoinGecko.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import httpx

from src.config import COINGECKO_API_KEY, DB_PATH

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEXSCREENER_BASE = "https://api.dexscreener.com/latest/dex"

# Well-known CoinGecko IDs for common tokens (symbol → id)
SYMBOL_TO_CG_ID: dict[str, str] = {
    "ETH": "ethereum",
    "WETH": "weth",
    "BTC": "bitcoin",
    "WBTC": "wrapped-bitcoin",
    "SOL": "solana",
    "WSOL": "wrapped-solana",
    "MATIC": "matic-network",
    "WMATIC": "wmatic",
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "dai",
    "BUSD": "binance-usd",
    "FRAX": "frax",
    "BNB": "binancecoin",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "AAVE": "aave",
    "CRV": "curve-dao-token",
    "LDO": "lido-dao",
    "MKR": "maker",
    "SNX": "havven",
    "COMP": "compound-governance-token",
    "1INCH": "1inch",
    "ARB": "arbitrum",
    "OP": "optimism",
    "BASE": "base",  # not a token, but just in case
    "STETH": "staked-ether",
    "RETH": "rocket-pool-eth",
}

# Stablecoins always worth $1
STABLECOINS = {"USDC", "USDT", "DAI", "BUSD", "FRAX", "TUSD", "USDP", "USDD", "GUSD", "LUSD", "SUSD", "USD"}


class PriceCache:
    """
    SQLite-backed price cache for historical token prices.

    Thread-safe for single process use. Use aiosqlite for async if needed.
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(path)
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS price_cache (
                    token TEXT NOT NULL,
                    date  TEXT NOT NULL,
                    usd_price DECIMAL NOT NULL,
                    source TEXT DEFAULT 'coingecko',
                    PRIMARY KEY (token, date)
                )
            """)
            conn.commit()

    def get(self, token: str, day: date) -> Optional[Decimal]:
        """Return cached USD price or None."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT usd_price FROM price_cache WHERE token = ? AND date = ?",
                (token.upper(), day.isoformat()),
            ).fetchone()
        return Decimal(str(row[0])) if row else None

    def set(self, token: str, day: date, price: Decimal, source: str = "coingecko") -> None:
        """Store a price in the cache."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO price_cache (token, date, usd_price, source) VALUES (?, ?, ?, ?)",
                (token.upper(), day.isoformat(), str(price), source),
            )
            conn.commit()


class PriceService:
    """
    Fetches historical USD prices with aggressive SQLite caching.

    Usage:
        service = PriceService()
        price = await service.get_price("ETH", date(2024, 6, 15))
    """

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.cache = PriceCache(db_path)
        self.api_key = COINGECKO_API_KEY
        self._request_times: list[float] = []

    async def get_price(
        self,
        token_symbol: str,
        day: date,
        token_address: Optional[str] = None,
        chain: Optional[str] = None,
    ) -> Optional[Decimal]:
        """
        Return historical USD price for a token on a given date.

        Lookup order:
          1. Stablecoin shortcut → $1
          2. SQLite cache
          3. CoinGecko API (by symbol ID mapping)
          4. DexScreener API (fallback for obscure tokens)
          5. None (flag for manual entry)
        """
        symbol_upper = token_symbol.upper()

        # 1. Stablecoin shortcut
        if symbol_upper in STABLECOINS:
            return Decimal("1")

        # 2. Cache hit
        cached = self.cache.get(symbol_upper, day)
        if cached is not None:
            return cached

        # 3. CoinGecko
        price = await self._fetch_coingecko(symbol_upper, day)
        if price is not None:
            self.cache.set(symbol_upper, day, price, "coingecko")
            return price

        # 4. DexScreener fallback (needs token address)
        if token_address and chain:
            price = await self._fetch_dexscreener(token_address, chain, day)
            if price is not None:
                self.cache.set(symbol_upper, day, price, "dexscreener")
                return price

        return None  # Unknown price - will be flagged for manual entry

    async def get_prices_batch(
        self,
        requests: list[tuple[str, date]],
    ) -> dict[tuple[str, date], Optional[Decimal]]:
        """Fetch multiple prices concurrently (respects rate limit)."""
        results: dict[tuple[str, date], Optional[Decimal]] = {}
        tasks = []
        for symbol, day in requests:
            tasks.append(self.get_price(symbol, day))
        prices = await asyncio.gather(*tasks, return_exceptions=True)
        for (symbol, day), price in zip(requests, prices):
            results[(symbol, day)] = price if not isinstance(price, Exception) else None
        return results

    async def _fetch_coingecko(self, symbol: str, day: date) -> Optional[Decimal]:
        """Fetch price from CoinGecko /coins/{id}/history endpoint."""
        cg_id = SYMBOL_TO_CG_ID.get(symbol)
        if not cg_id:
            return None

        # CoinGecko date format: DD-MM-YYYY
        date_str = day.strftime("%d-%m-%Y")
        params: dict = {"date": date_str, "localization": "false"}
        if self.api_key:
            params["x_cg_pro_api_key"] = self.api_key

        await self._rate_limit()

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{COINGECKO_BASE}/coins/{cg_id}/history",
                    params=params,
                )
                if resp.status_code == 429:
                    await asyncio.sleep(60)  # Back off on rate limit
                    return None
                resp.raise_for_status()
                data = resp.json()

            market_data = data.get("market_data", {})
            price_usd = market_data.get("current_price", {}).get("usd")
            if price_usd is not None:
                return Decimal(str(price_usd))
        except Exception as exc:
            print(f"[PriceService] CoinGecko error for {symbol} on {day}: {exc}")

        return None

    async def _fetch_dexscreener(
        self, token_address: str, chain: str, day: date
    ) -> Optional[Decimal]:
        """
        Fetch current price from DexScreener as a fallback.
        NOTE: DexScreener only provides current price, not historical.
              This is a best-effort fallback for very obscure tokens.
        """
        # Only use DexScreener if the date is recent (within 30 days)
        age_days = (date.today() - day).days
        if age_days > 30:
            return None

        chain_map = {
            "ethereum": "ethereum",
            "polygon": "polygon",
            "arbitrum": "arbitrum",
            "base": "base",
            "optimism": "optimism",
            "solana": "solana",
        }
        ds_chain = chain_map.get(chain, chain)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{DEXSCREENER_BASE}/tokens/{token_address}",
                )
                resp.raise_for_status()
                data = resp.json()

            pairs = data.get("pairs") or []
            for pair in pairs:
                if pair.get("chainId") == ds_chain:
                    price_str = pair.get("priceUsd")
                    if price_str:
                        return Decimal(str(price_str))
        except Exception as exc:
            print(f"[PriceService] DexScreener error for {token_address}: {exc}")

        return None

    async def _rate_limit(self) -> None:
        """Soft rate limit: ~10 requests / minute for CoinGecko free tier."""
        import time
        now = time.monotonic()
        # Keep only requests in the last 60 seconds
        self._request_times = [t for t in self._request_times if now - t < 60]
        if len(self._request_times) >= 10:
            sleep_time = 60 - (now - self._request_times[0]) + 1
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self._request_times.append(time.monotonic())
