"""
Cosmos ecosystem transaction importer via LCD REST API.

Supports: Cosmos Hub (ATOM), Osmosis (OSMO)
Handles: MsgSend, MsgDelegate, MsgUndelegate, MsgWithdrawDelegatorReward,
         MsgTransfer (IBC), Osmosis MsgSwapExactAmountIn

API: /cosmos/tx/v1beta1/txs?events=...
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import httpx

from src.config import COSMOS_DENOMS, COSMOS_LCD_ENDPOINTS, COSMOS_NATIVE_TOKENS
from src.importers.models import AssetTransfer, Transaction

# Cosmos amounts are typically in micro-units (1 ATOM = 1_000_000 uatom)
MICRO = Decimal("1000000")


class CosmosImporter:
    """
    Import Cosmos ecosystem transactions via LCD REST API.

    Supports:
      - cosmoshub (ATOM): send, delegate, undelegate, claim_rewards, ibc_transfer
      - osmosis (OSMO): all of above + swap (MsgSwapExactAmountIn)

    Usage:
        importer = CosmosImporter()
        txs = await importer.import_address("cosmos1abc...", chain="cosmoshub")
    """

    def __init__(self, lcd_endpoints: Optional[dict[str, str]] = None) -> None:
        self.lcd_endpoints = lcd_endpoints or COSMOS_LCD_ENDPOINTS
        self._last_request_time = 0.0

    async def _rate_limited_get(self, client: httpx.AsyncClient, url: str, params: dict) -> dict:
        """Rate-limited GET request."""
        now = time.monotonic()
        min_gap = 0.2  # 5 req/s
        elapsed = now - self._last_request_time
        if elapsed < min_gap:
            await asyncio.sleep(min_gap - elapsed)
        self._last_request_time = time.monotonic()

        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_txs_for_event(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        event: str,
        address: str,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch transactions matching a Cosmos event query with pagination."""
        all_txs: list[dict] = []
        offset = 0

        while True:
            params = {
                "events": f"{event}='{address}'",
                "pagination.limit": str(limit),
                "pagination.offset": str(offset),
                "order_by": "ORDER_BY_ASC",
            }
            url = f"{base_url}/cosmos/tx/v1beta1/txs"
            data = await self._rate_limited_get(client, url, params)
            tx_responses = data.get("tx_responses", [])
            all_txs.extend(tx_responses)

            total = int(data.get("pagination", {}).get("total", "0"))
            offset += limit
            if offset >= total or not tx_responses:
                break

        return all_txs

    async def import_address(
        self,
        address: str,
        chain: str = "cosmoshub",
        wallet_addresses: Optional[set[str]] = None,
    ) -> list[Transaction]:
        """
        Import all transactions for a Cosmos address.

        Args:
            address: Cosmos bech32 address (cosmos1..., osmo1...)
            chain: Chain identifier (cosmoshub, osmosis)
            wallet_addresses: All known user addresses for self-transfer detection

        Returns:
            List of normalized Transaction objects
        """
        if chain not in self.lcd_endpoints:
            raise ValueError(f"Unsupported Cosmos chain: {chain}. Supported: {list(self.lcd_endpoints.keys())}")

        base_url = self.lcd_endpoints[chain]
        known_wallets = wallet_addresses or {address}
        native_token = COSMOS_NATIVE_TOKENS.get(chain, "ATOM")

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch transactions where address is sender or recipient
            sender_txs, recipient_txs = await asyncio.gather(
                self._fetch_txs_for_event(client, base_url, "message.sender", address),
                self._fetch_txs_for_event(client, base_url, "transfer.recipient", address),
            )

        # Deduplicate by tx hash
        seen: set[str] = set()
        all_raw: list[dict] = []
        for tx in sender_txs + recipient_txs:
            txhash = tx.get("txhash", "")
            if txhash and txhash not in seen:
                seen.add(txhash)
                all_raw.append(tx)

        transactions: list[Transaction] = []
        for raw in all_raw:
            parsed = self._parse_tx_response(raw, address, known_wallets, chain, native_token)
            transactions.extend(parsed)

        return sorted(transactions, key=lambda t: t.timestamp)

    def _parse_tx_response(
        self,
        tx_response: dict,
        address: str,
        known_wallets: set[str],
        chain: str,
        native_token: str,
    ) -> list[Transaction]:
        """Parse a Cosmos tx_response into one or more normalized Transactions."""
        results: list[Transaction] = []
        txhash = tx_response.get("txhash", "")
        timestamp_str = tx_response.get("timestamp", "")
        height = int(tx_response.get("height", 0))

        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            return results

        # Check if tx succeeded
        code = int(tx_response.get("code", 0))
        if code != 0:
            return results  # failed tx

        # Parse fee
        tx_body = tx_response.get("tx", {})
        auth_info = tx_body.get("auth_info", {})
        fee_obj = auth_info.get("fee", {})
        fee_amounts = fee_obj.get("amount", [])
        fee: Optional[AssetTransfer] = None
        if fee_amounts:
            fee_coin = fee_amounts[0]
            fee_denom = fee_coin.get("denom", "")
            fee_symbol = self._resolve_denom(fee_denom, native_token)
            fee_amount = Decimal(fee_coin.get("amount", "0")) / MICRO
            if fee_amount > Decimal("0"):
                fee = AssetTransfer(token_symbol=fee_symbol, amount=fee_amount)

        # Parse messages
        body = tx_body.get("body", {})
        messages = body.get("messages", [])

        for i, msg in enumerate(messages):
            msg_type = msg.get("@type", "")
            sub_hash = f"{txhash}_{i}" if len(messages) > 1 else txhash

            tx = self._parse_message(
                msg=msg,
                msg_type=msg_type,
                tx_hash=sub_hash,
                timestamp=timestamp,
                height=height,
                address=address,
                known_wallets=known_wallets,
                chain=chain,
                native_token=native_token,
                fee=fee if i == 0 else None,  # fee only on first sub-tx
                raw_data=tx_response,
            )
            if tx is not None:
                results.append(tx)

        return results

    def _parse_message(
        self,
        msg: dict,
        msg_type: str,
        tx_hash: str,
        timestamp: datetime,
        height: int,
        address: str,
        known_wallets: set[str],
        chain: str,
        native_token: str,
        fee: Optional[AssetTransfer],
        raw_data: dict,
    ) -> Optional[Transaction]:
        """Parse a single Cosmos SDK message into a Transaction."""
        try:
            # ── MsgSend ──────────────────────────────────────────────────────
            if msg_type.endswith("MsgSend"):
                from_addr = msg.get("from_address", "")
                to_addr = msg.get("to_address", "")
                amounts = msg.get("amount", [])

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []

                for coin in amounts:
                    symbol = self._resolve_denom(coin.get("denom", ""), native_token)
                    amount = Decimal(coin.get("amount", "0")) / MICRO
                    if amount <= Decimal("0"):
                        continue
                    transfer = AssetTransfer(token_symbol=symbol, amount=amount)
                    if from_addr == address or from_addr in known_wallets:
                        assets_out.append(transfer)
                    if to_addr == address or to_addr in known_wallets:
                        assets_in.append(transfer)

                # Self-transfer detection
                is_self = (from_addr in known_wallets and to_addr in known_wallets)
                tx_type = "transfer"

                return Transaction(
                    tx_hash=tx_hash, chain=chain, block_number=height,
                    timestamp=timestamp, from_address=from_addr, to_address=to_addr,
                    tx_type=tx_type, assets_in=assets_in, assets_out=assets_out,
                    fee=fee, protocol=None, raw_data=raw_data,
                )

            # ── MsgDelegate ──────────────────────────────────────────────────
            if msg_type.endswith("MsgDelegate"):
                delegator = msg.get("delegator_address", "")
                validator = msg.get("validator_address", "")
                coin = msg.get("amount", {})
                symbol = self._resolve_denom(coin.get("denom", ""), native_token)
                amount = Decimal(coin.get("amount", "0")) / MICRO

                return Transaction(
                    tx_hash=tx_hash, chain=chain, block_number=height,
                    timestamp=timestamp, from_address=delegator, to_address=validator,
                    tx_type="stake",
                    assets_in=[], assets_out=[AssetTransfer(token_symbol=symbol, amount=amount)],
                    fee=fee, protocol="Cosmos Staking", raw_data=raw_data,
                )

            # ── MsgUndelegate ────────────────────────────────────────────────
            if msg_type.endswith("MsgUndelegate"):
                delegator = msg.get("delegator_address", "")
                validator = msg.get("validator_address", "")
                coin = msg.get("amount", {})
                symbol = self._resolve_denom(coin.get("denom", ""), native_token)
                amount = Decimal(coin.get("amount", "0")) / MICRO

                return Transaction(
                    tx_hash=tx_hash, chain=chain, block_number=height,
                    timestamp=timestamp, from_address=validator, to_address=delegator,
                    tx_type="unstake",
                    assets_in=[AssetTransfer(token_symbol=symbol, amount=amount)], assets_out=[],
                    fee=fee, protocol="Cosmos Staking", raw_data=raw_data,
                )

            # ── MsgWithdrawDelegatorReward ────────────────────────────────────
            if msg_type.endswith("MsgWithdrawDelegatorReward"):
                delegator = msg.get("delegator_address", "")
                validator = msg.get("validator_address", "")

                # Reward amounts are in the logs/events, not the message itself.
                # We create a placeholder; the actual amount comes from events.
                # For now, parse from events in raw_data if available.
                reward_amount = self._extract_reward_from_events(raw_data, delegator, native_token)

                assets_in = []
                if reward_amount > Decimal("0"):
                    assets_in.append(AssetTransfer(token_symbol=native_token, amount=reward_amount))

                return Transaction(
                    tx_hash=tx_hash, chain=chain, block_number=height,
                    timestamp=timestamp, from_address=validator, to_address=delegator,
                    tx_type="reward",
                    assets_in=assets_in, assets_out=[],
                    fee=fee, protocol="Cosmos Staking", raw_data=raw_data,
                )

            # ── MsgTransfer (IBC) ────────────────────────────────────────────
            if msg_type.endswith("MsgTransfer"):
                sender = msg.get("sender", "")
                receiver = msg.get("receiver", "")
                token = msg.get("token", {})
                symbol = self._resolve_denom(token.get("denom", ""), native_token)
                amount = Decimal(token.get("amount", "0")) / MICRO

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []

                if sender == address or sender in known_wallets:
                    assets_out.append(AssetTransfer(token_symbol=symbol, amount=amount))
                if receiver == address or receiver in known_wallets:
                    assets_in.append(AssetTransfer(token_symbol=symbol, amount=amount))

                return Transaction(
                    tx_hash=tx_hash, chain=chain, block_number=height,
                    timestamp=timestamp, from_address=sender, to_address=receiver,
                    tx_type="bridge",  # IBC transfer = bridge between Cosmos chains
                    assets_in=assets_in, assets_out=assets_out,
                    fee=fee, protocol="IBC", raw_data=raw_data,
                )

            # ── MsgSwapExactAmountIn (Osmosis) ───────────────────────────────
            if msg_type.endswith("MsgSwapExactAmountIn"):
                sender = msg.get("sender", "")
                token_in = msg.get("token_in", {})
                token_out_min = msg.get("token_out_min_amount", "0")
                routes = msg.get("routes", [])

                in_denom = token_in.get("denom", "")
                in_symbol = self._resolve_denom(in_denom, native_token)
                in_amount = Decimal(token_in.get("amount", "0")) / MICRO

                # The actual output amount is in the events, not the message.
                # token_out_min_amount is just slippage protection.
                out_amount = self._extract_swap_output_from_events(raw_data, sender)
                out_denom = routes[-1].get("token_out_denom", "") if routes else ""
                out_symbol = self._resolve_denom(out_denom, native_token)

                assets_out = [AssetTransfer(token_symbol=in_symbol, amount=in_amount)]
                assets_in = []
                if out_amount > Decimal("0") and out_symbol:
                    assets_in.append(AssetTransfer(token_symbol=out_symbol, amount=out_amount))

                return Transaction(
                    tx_hash=tx_hash, chain=chain, block_number=height,
                    timestamp=timestamp, from_address=sender, to_address="osmosis_pool",
                    tx_type="swap",
                    assets_in=assets_in, assets_out=assets_out,
                    fee=fee, protocol="Osmosis DEX", raw_data=raw_data,
                )

            # Unknown message type - skip
            return None

        except Exception as exc:
            print(f"[CosmosImporter] Skipping msg in tx {tx_hash}: {exc}")
            return None

    def _resolve_denom(self, denom: str, fallback: str) -> str:
        """Convert a Cosmos denomination to a human-readable symbol."""
        if denom in COSMOS_DENOMS:
            return COSMOS_DENOMS[denom]
        # IBC denoms: ibc/HASH... → keep as-is (user can map later)
        if denom.startswith("ibc/"):
            return denom[:20] + "..."  # truncate for display
        if denom.startswith("gamm/pool/"):
            return f"GAMM-{denom.split('/')[-1]}"  # Osmosis LP token
        return denom.upper() if denom else fallback

    def _extract_reward_from_events(
        self, raw_data: dict, delegator: str, native_token: str
    ) -> Decimal:
        """Extract staking reward amount from transaction events."""
        try:
            logs = raw_data.get("logs", [])
            for log in logs:
                for event in log.get("events", []):
                    if event.get("type") == "withdraw_rewards":
                        for attr in event.get("attributes", []):
                            if attr.get("key") == "amount":
                                val = attr.get("value", "")
                                # Format: "12345uatom" or "12345uatom,6789uosmo"
                                return self._parse_coin_string(val, native_token)
        except Exception:
            pass

        # Also try tx_response.events (newer format)
        try:
            events = raw_data.get("events", [])
            for event in events:
                if event.get("type") == "withdraw_rewards":
                    for attr in event.get("attributes", []):
                        if attr.get("key") == "amount":
                            return self._parse_coin_string(attr.get("value", ""), native_token)
        except Exception:
            pass

        return Decimal("0")

    def _extract_swap_output_from_events(self, raw_data: dict, sender: str) -> Decimal:
        """Extract the actual output amount from Osmosis swap events."""
        try:
            logs = raw_data.get("logs", [])
            for log in logs:
                for event in log.get("events", []):
                    if event.get("type") == "token_swapped":
                        attrs = {a["key"]: a["value"] for a in event.get("attributes", [])}
                        if attrs.get("sender") == sender:
                            out_str = attrs.get("tokens_out", "")
                            return self._parse_coin_amount(out_str)
        except Exception:
            pass
        return Decimal("0")

    @staticmethod
    def _parse_coin_string(coin_str: str, native_token: str) -> Decimal:
        """Parse '12345uatom' or '12345uatom,6789uosmo' and return the native amount."""
        total = Decimal("0")
        for part in coin_str.split(","):
            part = part.strip()
            if not part:
                continue
            # Extract numeric prefix
            i = 0
            while i < len(part) and (part[i].isdigit() or part[i] == "."):
                i += 1
            if i > 0:
                try:
                    total += Decimal(part[:i]) / MICRO
                except Exception:
                    pass
        return total

    @staticmethod
    def _parse_coin_amount(coin_str: str) -> Decimal:
        """Parse a single coin string like '12345uosmo' and return the amount."""
        if not coin_str:
            return Decimal("0")
        i = 0
        while i < len(coin_str) and (coin_str[i].isdigit() or coin_str[i] == "."):
            i += 1
        if i > 0:
            try:
                return Decimal(coin_str[:i]) / MICRO
            except Exception:
                pass
        return Decimal("0")
