"""
EVM chain transaction importer using Etherscan-compatible APIs.

Supports: Ethereum, Polygon, Arbitrum, Base, Optimism, BSC, Avalanche,
          Fantom, zkSync, Linea, Scroll, Mantle
Fetches: normal txs, internal txs, ERC-20 transfers, ERC-721 transfers
Handles: pagination (10K max per call), rate limiting (5 req/s free tier)
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from src.config import (
    CHAIN_API_KEYS,
    CHAIN_CONFIGS,
    CHAIN_EXPLORER_URLS,
    ETHERSCAN_RATE_LIMIT,
    SUPPORTED_EVM_CHAINS,
    ChainConfig,
)
from src.importers.models import AssetTransfer, Transaction

# Wei → ETH conversion factor
WEI = Decimal("1e18")
GWEI = Decimal("1e9")

# Etherscan max results per page
PAGE_SIZE = 10_000


class EVMImporter:
    """
    Imports and normalizes transactions from EVM chains via Etherscan-compatible APIs.

    Usage:
        importer = EVMImporter("ethereum")
        txs = await importer.fetch_all("0xABC...", start_block=0)

        # Or via factory:
        importer = EVMImporter.for_chain("bsc")
    """

    def __init__(self, chain: str) -> None:
        if chain not in SUPPORTED_EVM_CHAINS:
            raise ValueError(f"Unsupported EVM chain: {chain}. Supported: {SUPPORTED_EVM_CHAINS}")
        self.chain = chain
        self._config: ChainConfig = CHAIN_CONFIGS[chain]
        self.base_url = self._config.api_url
        self.api_key = self._config.api_key
        self.native_symbol = self._config.native_token
        self._last_request_time = 0.0

    @classmethod
    def for_chain(cls, chain_name: str) -> "EVMImporter":
        """Factory method: create an EVMImporter from CHAIN_CONFIGS by name."""
        if chain_name not in CHAIN_CONFIGS:
            raise ValueError(
                f"Unknown chain '{chain_name}'. Available: {list(CHAIN_CONFIGS.keys())}"
            )
        return cls(chain_name)

    @classmethod
    def from_config(cls, chain_name: str, config: ChainConfig) -> "EVMImporter":
        """Create an EVMImporter from an explicit ChainConfig (useful for testing)."""
        instance = object.__new__(cls)
        instance.chain = chain_name
        instance._config = config
        instance.base_url = config.api_url
        instance.api_key = config.api_key
        instance.native_symbol = config.native_token
        instance._last_request_time = 0.0
        return instance

    async def _rate_limited_get(self, client: httpx.AsyncClient, params: dict) -> dict:
        """Enforce 5 req/s rate limit for free API key."""
        now = time.monotonic()
        min_gap = 1.0 / ETHERSCAN_RATE_LIMIT
        elapsed = now - self._last_request_time
        if elapsed < min_gap:
            await asyncio.sleep(min_gap - elapsed)
        self._last_request_time = time.monotonic()

        params["apikey"] = self.api_key
        resp = await client.get(self.base_url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "0" and data.get("message") not in ("No transactions found", "No records found"):
            raise RuntimeError(f"Etherscan API error: {data.get('result')}")
        return data

    async def _fetch_paginated(
        self,
        client: httpx.AsyncClient,
        action: str,
        address: str,
        start_block: int = 0,
        end_block: int = 99_999_999,
    ) -> list[dict]:
        """Fetch all pages for a given Etherscan action."""
        results: list[dict] = []
        page = 1
        while True:
            params = {
                "module": "account",
                "action": action,
                "address": address,
                "startblock": start_block,
                "endblock": end_block,
                "page": page,
                "offset": PAGE_SIZE,
                "sort": "asc",
            }
            data = await self._rate_limited_get(client, params)
            batch = data.get("result") or []
            if not isinstance(batch, list):
                break
            results.extend(batch)
            if len(batch) < PAGE_SIZE:
                break  # last page
            page += 1
            # Advance start block to avoid re-fetching (Etherscan pages by record index)
        return results

    async def fetch_all(
        self,
        address: str,
        start_block: int = 0,
        end_block: int = 99_999_999,
        wallet_addresses: Optional[set[str]] = None,
    ) -> list[Transaction]:
        """
        Fetch and normalize all transaction types for a wallet address.

        Args:
            address: Wallet address (0x...)
            start_block: Starting block (for incremental import)
            end_block: Ending block
            wallet_addresses: All known user wallet addresses (for self-transfer detection)

        Returns:
            List of normalized Transaction objects
        """
        address_lower = address.lower()
        known_wallets = {a.lower() for a in (wallet_addresses or {address})}

        async with httpx.AsyncClient(timeout=30.0) as client:
            normal_raw, internal_raw, erc20_raw, erc721_raw = await asyncio.gather(
                self._fetch_paginated(client, "txlist", address, start_block, end_block),
                self._fetch_paginated(client, "txlistinternal", address, start_block, end_block),
                self._fetch_paginated(client, "tokentx", address, start_block, end_block),
                self._fetch_paginated(client, "tokennfttx", address, start_block, end_block),
            )

        # Index internal txs and token transfers by tx hash for enrichment
        internal_by_hash: dict[str, list[dict]] = {}
        for r in internal_raw:
            internal_by_hash.setdefault(r["hash"], []).append(r)

        erc20_by_hash: dict[str, list[dict]] = {}
        for r in erc20_raw:
            erc20_by_hash.setdefault(r["hash"], []).append(r)

        erc721_by_hash: dict[str, list[dict]] = {}
        for r in erc721_raw:
            erc721_by_hash.setdefault(r["hash"], []).append(r)

        # Collect all unique tx hashes (normal + any erc20/erc721 not in normal)
        normal_hashes = {r["hash"] for r in normal_raw}
        all_raw = list(normal_raw)
        for erc20 in erc20_raw:
            if erc20["hash"] not in normal_hashes:
                all_raw.append(erc20)
        for erc721 in erc721_raw:
            if erc721["hash"] not in normal_hashes and erc721["hash"] not in {r["hash"] for r in erc20_raw}:
                all_raw.append(erc721)

        transactions: list[Transaction] = []
        seen: set[str] = set()

        for raw in all_raw:
            tx_hash = raw["hash"]
            if tx_hash in seen:
                continue
            seen.add(tx_hash)

            tx = self._normalize_transaction(
                tx_hash=tx_hash,
                raw=raw,
                address_lower=address_lower,
                known_wallets=known_wallets,
                erc20_transfers=erc20_by_hash.get(tx_hash, []),
                erc721_transfers=erc721_by_hash.get(tx_hash, []),
                internal_transfers=internal_by_hash.get(tx_hash, []),
            )
            if tx is not None:
                transactions.append(tx)

        return sorted(transactions, key=lambda t: t.timestamp)

    def _normalize_transaction(
        self,
        tx_hash: str,
        raw: dict,
        address_lower: str,
        known_wallets: set[str],
        erc20_transfers: list[dict],
        erc721_transfers: list[dict],
        internal_transfers: list[dict],
    ) -> Optional[Transaction]:
        """Convert raw Etherscan response to normalized Transaction."""
        try:
            timestamp = datetime.fromtimestamp(int(raw["timeStamp"]), tz=timezone.utc)
            block_number = int(raw.get("blockNumber", 0))
            from_addr = raw.get("from", "").lower()
            to_addr = raw.get("to", "").lower()

            # ── Gas fee calculation ──────────────────────────────────────────
            gas_used = int(raw.get("gasUsed", 0))
            gas_price = int(raw.get("gasPrice", 0))
            fee_wei = gas_used * gas_price
            fee: Optional[AssetTransfer] = None
            if fee_wei > 0 and from_addr == address_lower:
                fee = AssetTransfer(
                    token_symbol=self.native_symbol,
                    amount=Decimal(fee_wei) / WEI,
                    token_address=None,
                )

            # ── Determine assets in / out ────────────────────────────────────
            assets_in: list[AssetTransfer] = []
            assets_out: list[AssetTransfer] = []

            # Native ETH/MATIC/BNB/AVAX/FTM/MNT value
            value_wei = int(raw.get("value", 0))
            if value_wei > 0:
                native = AssetTransfer(
                    token_symbol=self.native_symbol,
                    amount=Decimal(value_wei) / WEI,
                    token_address=None,
                )
                if from_addr == address_lower:
                    assets_out.append(native)
                elif to_addr == address_lower:
                    assets_in.append(native)

            # ERC-20 token transfers
            for t in erc20_transfers:
                token_amount = Decimal(t["value"]) / (Decimal(10) ** int(t.get("tokenDecimal", 18)))
                transfer = AssetTransfer(
                    token_symbol=t.get("tokenSymbol", "UNKNOWN"),
                    amount=token_amount,
                    token_address=t.get("contractAddress", "").lower(),
                )
                if t.get("from", "").lower() == address_lower:
                    assets_out.append(transfer)
                elif t.get("to", "").lower() == address_lower:
                    assets_in.append(transfer)

            # ERC-721 NFT transfers (amount = 1)
            for t in erc721_transfers:
                transfer = AssetTransfer(
                    token_symbol=t.get("tokenName", "NFT") + " #" + t.get("tokenID", "?"),
                    amount=Decimal("1"),
                    token_address=t.get("contractAddress", "").lower(),
                )
                if t.get("from", "").lower() == address_lower:
                    assets_out.append(transfer)
                elif t.get("to", "").lower() == address_lower:
                    assets_in.append(transfer)

            # ── Classify tx type ─────────────────────────────────────────────
            tx_type = self._classify_tx_type(
                from_addr=from_addr,
                to_addr=to_addr,
                address_lower=address_lower,
                known_wallets=known_wallets,
                assets_in=assets_in,
                assets_out=assets_out,
                input_data=raw.get("input", "0x"),
            )

            return Transaction(
                tx_hash=tx_hash,
                chain=self.chain,
                block_number=block_number,
                timestamp=timestamp,
                from_address=from_addr,
                to_address=to_addr,
                tx_type=tx_type,
                assets_in=assets_in,
                assets_out=assets_out,
                fee=fee,
                protocol=None,  # Enriched later by categorizer
                raw_data=raw,
            )
        except Exception as exc:
            # Log and skip malformed records rather than crashing the import
            print(f"[EVMImporter] Skipping tx {tx_hash}: {exc}")
            return None

    def _classify_tx_type(
        self,
        from_addr: str,
        to_addr: str,
        address_lower: str,
        known_wallets: set[str],
        assets_in: list[AssetTransfer],
        assets_out: list[AssetTransfer],
        input_data: str,
    ) -> str:
        """Preliminary tx type classification. Categorizer engine refines this."""
        # Self-transfer: both sides belong to user
        if from_addr in known_wallets and to_addr in known_wallets:
            return "transfer"

        has_in = len(assets_in) > 0
        has_out = len(assets_out) > 0

        if has_in and has_out:
            return "swap"  # Categorizer will distinguish swap vs LP add/remove
        if has_in and not has_out:
            return "airdrop"  # Or staking reward - categorizer will refine
        if has_out and not has_in:
            return "transfer"
        if input_data and input_data != "0x":
            return "unknown"  # Contract call with no detected asset movement
        return "transfer"
