"""
Bitcoin transaction importer via Blockstream.info API.

Handles UTXO model: parses inputs/outputs to determine send, receive,
and self-transfer transactions. Calculates fees from input_total - output_total.

API docs: https://github.com/Blockstream/esplora/blob/master/API.md
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from src.config import BLOCKSTREAM_RATE_LIMIT
from src.importers.models import AssetTransfer, Transaction

# Satoshi → BTC conversion factor
SATS = Decimal("100000000")

# Blockstream paginates by last_seen_txid
BLOCKSTREAM_PAGE_SIZE = 25  # API returns 25 txs per page


class BitcoinImporter:
    """
    Import Bitcoin transactions via Blockstream.info API.

    Parses the UTXO model to determine:
      - send: address appears in inputs (spending)
      - receive: address appears in outputs (receiving)
      - self-transfer: address appears in both and all outputs go to known wallets
      - fee: total_input - total_output for transactions the user sent

    Usage:
        importer = BitcoinImporter()
        txs = await importer.import_address("bc1q...")
    """

    API_URL = "https://blockstream.info/api"

    def __init__(self, api_url: Optional[str] = None) -> None:
        self.api_url = api_url or self.API_URL
        self._last_request_time = 0.0

    async def _rate_limited_get(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """Enforce rate limit for Blockstream API."""
        now = time.monotonic()
        min_gap = 1.0 / BLOCKSTREAM_RATE_LIMIT
        elapsed = now - self._last_request_time
        if elapsed < min_gap:
            await asyncio.sleep(min_gap - elapsed)
        self._last_request_time = time.monotonic()

        resp = await client.get(url)
        resp.raise_for_status()
        return resp

    async def _fetch_all_txs(self, client: httpx.AsyncClient, address: str) -> list[dict]:
        """Fetch all transactions for an address, handling pagination."""
        all_txs: list[dict] = []
        last_seen_txid: Optional[str] = None

        while True:
            url = f"{self.api_url}/address/{address}/txs"
            if last_seen_txid:
                url = f"{url}/chain/{last_seen_txid}"

            resp = await self._rate_limited_get(client, url)
            batch = resp.json()
            if not batch:
                break

            all_txs.extend(batch)

            if len(batch) < BLOCKSTREAM_PAGE_SIZE:
                break  # last page
            last_seen_txid = batch[-1]["txid"]

        return all_txs

    async def import_address(
        self,
        address: str,
        wallet_addresses: Optional[set[str]] = None,
    ) -> list[Transaction]:
        """
        Import all Bitcoin transactions for an address.

        Args:
            address: Bitcoin address (legacy, segwit, or bech32)
            wallet_addresses: All known user wallet addresses (for self-transfer detection)

        Returns:
            List of normalized Transaction objects
        """
        known_wallets = wallet_addresses or {address}
        known_wallets_set = set(known_wallets)

        async with httpx.AsyncClient(timeout=30.0) as client:
            raw_txs = await self._fetch_all_txs(client, address)

        transactions: list[Transaction] = []
        for raw in raw_txs:
            tx = self._parse_transaction(raw, address, known_wallets_set)
            if tx is not None:
                transactions.append(tx)

        return sorted(transactions, key=lambda t: t.timestamp)

    def _parse_transaction(
        self,
        raw: dict,
        address: str,
        known_wallets: set[str],
    ) -> Optional[Transaction]:
        """Parse a single Blockstream transaction into a normalized Transaction."""
        try:
            txid = raw["txid"]
            status = raw.get("status", {})

            # Skip unconfirmed transactions
            if not status.get("confirmed", False):
                return None

            block_time = status.get("block_time")
            block_height = status.get("block_height", 0)
            if block_time is None:
                return None

            timestamp = datetime.fromtimestamp(block_time, tz=timezone.utc)

            # ── Analyze inputs (what the address spent) ──────────────────────
            total_input_value = Decimal("0")
            user_input_value = Decimal("0")
            user_is_sender = False
            input_addresses: set[str] = set()

            for vin in raw.get("vin", []):
                prevout = vin.get("prevout") or {}
                script_addr = prevout.get("scriptpubkey_address", "")
                value_sats = prevout.get("value", 0)
                total_input_value += Decimal(str(value_sats))

                if script_addr:
                    input_addresses.add(script_addr)
                if script_addr == address or script_addr in known_wallets:
                    user_input_value += Decimal(str(value_sats))
                    user_is_sender = True

            # ── Analyze outputs (what the address received) ──────────────────
            total_output_value = Decimal("0")
            user_output_value = Decimal("0")
            user_is_receiver = False
            output_addresses: set[str] = set()
            all_outputs_to_known = True

            for vout in raw.get("vout", []):
                script_addr = vout.get("scriptpubkey_address", "")
                value_sats = vout.get("value", 0)
                total_output_value += Decimal(str(value_sats))

                if script_addr:
                    output_addresses.add(script_addr)
                    if script_addr not in known_wallets:
                        all_outputs_to_known = False

                if script_addr == address or script_addr in known_wallets:
                    user_output_value += Decimal(str(value_sats))
                    user_is_receiver = True

            # ── Fee calculation ──────────────────────────────────────────────
            fee_sats = total_input_value - total_output_value
            fee: Optional[AssetTransfer] = None
            if fee_sats > Decimal("0") and user_is_sender:
                fee = AssetTransfer(
                    token_symbol="BTC",
                    amount=fee_sats / SATS,
                    token_address=None,
                )

            # ── Determine tx type and assets in/out ──────────────────────────
            assets_in: list[AssetTransfer] = []
            assets_out: list[AssetTransfer] = []

            if user_is_sender and user_is_receiver and all_outputs_to_known:
                # Self-transfer: all outputs go to known wallets
                tx_type = "transfer"
                # Net movement is zero (minus fee), but track gross for display
                if user_output_value > Decimal("0"):
                    assets_in.append(AssetTransfer(
                        token_symbol="BTC",
                        amount=user_output_value / SATS,
                    ))

            elif user_is_sender:
                # Sending: the amount sent is user_input_value minus change back to self
                sent_amount = user_input_value - user_output_value - fee_sats
                if sent_amount > Decimal("0"):
                    assets_out.append(AssetTransfer(
                        token_symbol="BTC",
                        amount=sent_amount / SATS,
                    ))
                tx_type = "transfer"

            elif user_is_receiver:
                # Receiving
                if user_output_value > Decimal("0"):
                    assets_in.append(AssetTransfer(
                        token_symbol="BTC",
                        amount=user_output_value / SATS,
                    ))
                tx_type = "transfer"

            else:
                # Edge case: address not found in inputs or outputs
                return None

            # Determine from/to for display
            from_addr = next(iter(input_addresses), "unknown")
            to_addr = next(iter(output_addresses - known_wallets), next(iter(output_addresses), "unknown"))

            return Transaction(
                tx_hash=txid,
                chain="bitcoin",
                block_number=block_height,
                timestamp=timestamp,
                from_address=from_addr,
                to_address=to_addr,
                tx_type=tx_type,
                assets_in=assets_in,
                assets_out=assets_out,
                fee=fee,
                protocol=None,
                raw_data=raw,
            )
        except Exception as exc:
            print(f"[BitcoinImporter] Skipping tx {raw.get('txid', '?')}: {exc}")
            return None
