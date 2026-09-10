"""
Solana transaction importer using the Helius API.

Helius normalizes Solana's instruction-based model into higher-level events
(transfers, swaps, NFT events, staking, etc.), making it much easier to parse
than raw RPC calls.

Free tier: 1,000 requests / day
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from src.config import HELIUS_API_KEY
from src.importers.models import AssetTransfer, Transaction

# Lamports → SOL
LAMPORTS_PER_SOL = Decimal("1_000_000_000")

# Helius endpoints
HELIUS_BASE = "https://api.helius.xyz/v0"
HELIUS_TXS_ENDPOINT = f"{HELIUS_BASE}/addresses/{{address}}/transactions"


class SolanaImporter:
    """
    Imports and normalizes transactions from Solana via the Helius API.

    Usage:
        importer = SolanaImporter()
        txs = await importer.fetch_all("5rEq...")
    """

    def __init__(self) -> None:
        if not HELIUS_API_KEY:
            raise RuntimeError("HELIUS_API_KEY is not set. Add it to your .env file.")
        self.api_key = HELIUS_API_KEY

    async def fetch_all(
        self,
        address: str,
        before: Optional[str] = None,
        limit: int = 100,
        wallet_addresses: Optional[set[str]] = None,
    ) -> list[Transaction]:
        """
        Fetch all transactions for a Solana wallet.

        Args:
            address: Base58 wallet address
            before: Pagination cursor - fetch transactions before this signature
            limit: Max per request (Helius max: 100)
            wallet_addresses: All known user wallet addresses for self-transfer detection

        Returns:
            Sorted list of normalized Transaction objects (oldest first)
        """
        known_wallets = {a for a in (wallet_addresses or {address})}
        all_raw: list[dict] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            cursor = before
            while True:
                params: dict = {"api-key": self.api_key, "limit": limit}
                if cursor:
                    params["before"] = cursor

                url = HELIUS_TXS_ENDPOINT.format(address=address)
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                batch: list[dict] = resp.json()

                if not batch:
                    break

                all_raw.extend(batch)
                if len(batch) < limit:
                    break  # last page

                cursor = batch[-1]["signature"]
                await asyncio.sleep(0.1)  # be polite to free tier

        transactions: list[Transaction] = []
        for raw in all_raw:
            tx = self._normalize_transaction(raw, address, known_wallets)
            if tx:
                transactions.append(tx)

        return sorted(transactions, key=lambda t: t.timestamp)

    def _normalize_transaction(
        self,
        raw: dict,
        wallet_address: str,
        known_wallets: set[str],
    ) -> Optional[Transaction]:
        """Convert a Helius enhanced transaction to a normalized Transaction."""
        try:
            sig = raw.get("signature", "")
            timestamp = datetime.fromtimestamp(raw["timestamp"], tz=timezone.utc)
            tx_type_helius = raw.get("type", "UNKNOWN")

            assets_in: list[AssetTransfer] = []
            assets_out: list[AssetTransfer] = []
            fee: Optional[AssetTransfer] = None

            # ── Fee ─────────────────────────────────────────────────────────
            fee_lamports = raw.get("fee", 0)
            if fee_lamports > 0:
                fee_payer = raw.get("feePayer", "")
                if fee_payer == wallet_address:
                    fee = AssetTransfer(
                        token_symbol="SOL",
                        amount=Decimal(fee_lamports) / LAMPORTS_PER_SOL,
                        token_address=None,
                    )

            # ── Native SOL transfers ─────────────────────────────────────────
            for native_tx in raw.get("nativeTransfers", []):
                amount_sol = Decimal(native_tx.get("amount", 0)) / LAMPORTS_PER_SOL
                if amount_sol == Decimal("0"):
                    continue
                transfer = AssetTransfer(
                    token_symbol="SOL",
                    amount=amount_sol,
                    token_address=None,
                )
                if native_tx.get("fromUserAccount") == wallet_address:
                    assets_out.append(transfer)
                elif native_tx.get("toUserAccount") == wallet_address:
                    assets_in.append(transfer)

            # ── SPL token transfers ──────────────────────────────────────────
            for token_tx in raw.get("tokenTransfers", []):
                decimals = int(token_tx.get("tokenAmount", {}).get("decimals", 9))
                ui_amount = token_tx.get("tokenAmount", {}).get("uiAmount") or 0
                amount = Decimal(str(ui_amount))
                if amount == Decimal("0"):
                    continue
                transfer = AssetTransfer(
                    token_symbol=token_tx.get("symbol") or token_tx.get("mint", "UNKNOWN"),
                    amount=amount,
                    token_address=token_tx.get("mint"),
                )
                if token_tx.get("fromUserAccount") == wallet_address:
                    assets_out.append(transfer)
                elif token_tx.get("toUserAccount") == wallet_address:
                    assets_in.append(transfer)

            tx_type = self._classify_helius_type(
                helius_type=tx_type_helius,
                assets_in=assets_in,
                assets_out=assets_out,
                known_wallets=known_wallets,
                raw=raw,
            )

            # Extract from/to from the first account key (fee payer is typically the signer)
            account_keys = raw.get("accountData", [])
            from_addr = raw.get("feePayer", wallet_address)
            to_addr = raw.get("instructions", [{}])[0].get("programId", "") if raw.get("instructions") else ""

            return Transaction(
                tx_hash=sig,
                chain="solana",
                block_number=raw.get("slot", 0),
                timestamp=timestamp,
                from_address=from_addr,
                to_address=to_addr,
                tx_type=tx_type,
                assets_in=assets_in,
                assets_out=assets_out,
                fee=fee,
                protocol=raw.get("source"),  # e.g. "RAYDIUM", "ORCA", "JUPITER"
                raw_data=raw,
            )
        except Exception as exc:
            sig = raw.get("signature", "?")
            print(f"[SolanaImporter] Skipping tx {sig}: {exc}")
            return None

    def _classify_helius_type(
        self,
        helius_type: str,
        assets_in: list[AssetTransfer],
        assets_out: list[AssetTransfer],
        known_wallets: set[str],
        raw: dict,
    ) -> str:
        """Map Helius transaction type to our normalized tx_type."""
        type_map = {
            "TRANSFER": "transfer",
            "TOKEN_MINT": "mint",
            "BURN": "burn",
            "SWAP": "swap",
            "ADD_LIQUIDITY": "lp_add",
            "REMOVE_LIQUIDITY": "lp_remove",
            "STAKE_SOL": "stake",
            "UNSTAKE_SOL": "unstake",
            "STAKE_TOKEN": "stake",
            "NFT_MINT": "mint",
            "NFT_SALE": "swap",
            "NFT_LISTING": "unknown",
            "NFT_CANCEL_LISTING": "unknown",
            "AIRDROP": "airdrop",
            "UNKNOWN": "unknown",
        }
        normalized = type_map.get(helius_type.upper(), "unknown")

        # Fallback: infer from asset movement if Helius type is generic
        if normalized in ("transfer", "unknown"):
            has_in = len(assets_in) > 0
            has_out = len(assets_out) > 0
            if has_in and has_out:
                normalized = "swap"
            elif has_in and not has_out:
                normalized = "airdrop"

        return normalized
