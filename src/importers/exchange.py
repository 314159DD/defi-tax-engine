"""
CEX CSV importers for Coinbase, Binance, and Kraken.

Each exchange exports in a different format. This module normalizes them all
into the common Transaction model.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional
from uuid import uuid4

from src.importers.models import AssetTransfer, Transaction

# Supported formats
SUPPORTED_FORMATS = (
    "coinbase", "binance", "kraken",
    "bitpanda", "bison", "trade_republic",
    "gemini", "kucoin", "okx", "crypto_com",
    "generic",
)


def parse_decimal(value: str) -> Decimal:
    """Parse a decimal string, stripping currency symbols and commas."""
    cleaned = value.strip().replace(",", "").lstrip("$€£")
    try:
        return Decimal(cleaned) if cleaned else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def parse_datetime_utc(value: str, fmt: str) -> datetime:
    dt = datetime.strptime(value.strip(), fmt)
    return dt.replace(tzinfo=timezone.utc)


class ExchangeImporter:
    """
    Parses CEX CSV exports and returns normalized Transaction objects.

    Usage:
        importer = ExchangeImporter()
        txs = importer.parse_file("coinbase_export.csv", format="coinbase")
    """

    def parse_file(self, filepath: str | Path, fmt: str) -> list[Transaction]:
        """Parse a CSV file in the given format."""
        fmt = fmt.lower()
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format '{fmt}'. Supported: {SUPPORTED_FORMATS}")

        path = Path(filepath)
        content = path.read_text(encoding="utf-8-sig")  # handle BOM

        parser_map = {
            "coinbase": self._parse_coinbase,
            "binance": self._parse_binance,
            "kraken": self._parse_kraken,
            "bitpanda": self._parse_bitpanda,
            "bison": self._parse_bison,
            "trade_republic": self._parse_trade_republic,
            "gemini": self._parse_gemini,
            "kucoin": self._parse_kucoin,
            "okx": self._parse_okx,
            "crypto_com": self._parse_crypto_com,
            "generic": self._parse_generic,
        }
        return parser_map[fmt](content)

    # ── Coinbase ─────────────────────────────────────────────────────────────

    def _parse_coinbase(self, content: str) -> list[Transaction]:
        """
        Parse Coinbase transaction history CSV.
        Columns: Timestamp, Transaction Type, Asset, Quantity Transacted,
                 Spot Price Currency, Spot Price at Transaction, Subtotal,
                 Total (inclusive of fees and/or spread), Fees and/or Spread, Notes
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                tx_type_raw = row.get("Transaction Type", "").strip().lower()
                asset = row.get("Asset", "").strip()
                quantity = parse_decimal(row.get("Quantity Transacted", "0"))
                total = parse_decimal(row.get("Total (inclusive of fees and/or spread)", "0"))
                fees = parse_decimal(row.get("Fees and/or Spread", "0"))
                spot_currency = row.get("Spot Price Currency", "USD").strip()
                timestamp_str = row.get("Timestamp", "").strip()

                if not timestamp_str or not asset or quantity == Decimal("0"):
                    continue

                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)

                # USD value at time of tx
                usd_value = abs(total) if spot_currency == "USD" else None
                fee_usd = fees if spot_currency == "USD" else Decimal("0")

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if fee_usd > Decimal("0"):
                    fee = AssetTransfer(
                        token_symbol="USD",
                        amount=fee_usd,
                        token_address=None,
                        usd_value=fee_usd,
                    )

                if tx_type_raw in ("buy", "receive", "coinbase earn", "rewards income", "learning reward"):
                    assets_in.append(AssetTransfer(
                        token_symbol=asset,
                        amount=quantity,
                        usd_value=usd_value,
                    ))
                    if tx_type_raw == "buy":
                        assets_out.append(AssetTransfer(
                            token_symbol=spot_currency,
                            amount=abs(total),
                            usd_value=usd_value,
                        ))
                elif tx_type_raw in ("sell", "send"):
                    assets_out.append(AssetTransfer(
                        token_symbol=asset,
                        amount=quantity,
                        usd_value=usd_value,
                    ))
                    if tx_type_raw == "sell":
                        assets_in.append(AssetTransfer(
                            token_symbol=spot_currency,
                            amount=abs(total) - fee_usd,
                            usd_value=abs(total) - fee_usd if spot_currency == "USD" else None,
                        ))
                elif tx_type_raw == "convert":
                    # Coinbase converts show only one side; notes field has the other asset
                    assets_out.append(AssetTransfer(
                        token_symbol=asset,
                        amount=quantity,
                        usd_value=usd_value,
                    ))
                else:
                    continue  # Skip unrecognized types

                normalized_type = self._coinbase_type_to_tx_type(tx_type_raw)

                transactions.append(Transaction(
                    tx_hash=f"coinbase_{tx_type_raw}_{asset}_{timestamp.isoformat()}_{uuid4().hex[:8]}",
                    chain="coinbase",
                    block_number=0,
                    timestamp=timestamp,
                    from_address="coinbase",
                    to_address="wallet",
                    tx_type=normalized_type,
                    assets_in=assets_in,
                    assets_out=assets_out,
                    fee=fee,
                    protocol="Coinbase",
                    raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Coinbase] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    def _coinbase_type_to_tx_type(self, coinbase_type: str) -> str:
        return {
            "buy": "swap",
            "sell": "swap",
            "send": "transfer",
            "receive": "transfer",
            "convert": "swap",
            "coinbase earn": "airdrop",
            "rewards income": "reward",
            "learning reward": "airdrop",
        }.get(coinbase_type, "unknown")

    # ── Binance ──────────────────────────────────────────────────────────────

    def _parse_binance(self, content: str) -> list[Transaction]:
        """
        Parse Binance trade history CSV.
        Columns: Date(UTC), Pair, Side, Price, Executed, Amount, Fee
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                date_str = row.get("Date(UTC)", "").strip()
                pair = row.get("Pair", "").strip()          # e.g. "ETHUSDT"
                side = row.get("Side", "").strip().lower()  # buy or sell
                price = parse_decimal(row.get("Price", "0"))
                executed_raw = row.get("Executed", "0").strip()  # e.g. "0.5ETH"
                amount_raw = row.get("Amount", "0").strip()      # e.g. "1000USDT"
                fee_raw = row.get("Fee", "0").strip()            # e.g. "0.001BNB"

                if not date_str or not pair:
                    continue

                timestamp = parse_datetime_utc(date_str, "%Y-%m-%d %H:%M:%S")

                # Parse executed / amount values with trailing symbols
                executed_qty, executed_symbol = self._split_amount_symbol(executed_raw)
                amount_qty, amount_symbol = self._split_amount_symbol(amount_raw)
                fee_qty, fee_symbol = self._split_amount_symbol(fee_raw)

                usd_value = price * executed_qty if price > Decimal("0") else None

                if side == "buy":
                    assets_in = [AssetTransfer(token_symbol=executed_symbol, amount=executed_qty, usd_value=usd_value)]
                    assets_out = [AssetTransfer(token_symbol=amount_symbol, amount=amount_qty, usd_value=usd_value)]
                else:  # sell
                    assets_out = [AssetTransfer(token_symbol=executed_symbol, amount=executed_qty, usd_value=usd_value)]
                    assets_in = [AssetTransfer(token_symbol=amount_symbol, amount=amount_qty, usd_value=usd_value)]

                fee: Optional[AssetTransfer] = None
                if fee_qty > Decimal("0"):
                    fee = AssetTransfer(token_symbol=fee_symbol, amount=fee_qty)

                transactions.append(Transaction(
                    tx_hash=f"binance_{pair}_{side}_{date_str}_{uuid4().hex[:8]}",
                    chain="binance",
                    block_number=0,
                    timestamp=timestamp,
                    from_address="binance",
                    to_address="wallet",
                    tx_type="swap",
                    assets_in=assets_in,
                    assets_out=assets_out,
                    fee=fee,
                    protocol="Binance",
                    raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Binance] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── Kraken ───────────────────────────────────────────────────────────────

    def _parse_kraken(self, content: str) -> list[Transaction]:
        """
        Parse Kraken ledger CSV export.
        Columns: txid, refid, time, type, subtype, aclass, asset, amount, fee, balance
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))
        rows_by_refid: dict[str, list[dict]] = {}

        for row in reader:
            refid = row.get("refid", "").strip()
            if refid:
                rows_by_refid.setdefault(refid, []).append(dict(row))

        # Pair rows with same refid (trades have two sides)
        processed_refids: set[str] = set()
        for refid, rows in rows_by_refid.items():
            if refid in processed_refids:
                continue
            processed_refids.add(refid)

            try:
                if len(rows) == 2:
                    tx = self._kraken_trade_pair(rows[0], rows[1])
                elif len(rows) == 1:
                    tx = self._kraken_single_row(rows[0])
                else:
                    continue
                if tx:
                    transactions.append(tx)
            except Exception as exc:
                print(f"[ExchangeImporter/Kraken] Skipping refid {refid}: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    def _kraken_trade_pair(self, row_a: dict, row_b: dict) -> Optional[Transaction]:
        """Combine a matched Kraken trade pair (spend + receive) into one Transaction."""
        time_str = row_a.get("time", "").strip()
        timestamp = parse_datetime_utc(time_str, "%Y-%m-%d %H:%M:%S")

        assets_in: list[AssetTransfer] = []
        assets_out: list[AssetTransfer] = []
        fee: Optional[AssetTransfer] = None

        for row in (row_a, row_b):
            amount = parse_decimal(row.get("amount", "0"))
            fee_val = parse_decimal(row.get("fee", "0"))
            asset = self._kraken_normalize_asset(row.get("asset", ""))

            if fee_val > Decimal("0"):
                fee = AssetTransfer(token_symbol=asset, amount=fee_val)

            if amount > Decimal("0"):
                assets_in.append(AssetTransfer(token_symbol=asset, amount=amount))
            elif amount < Decimal("0"):
                assets_out.append(AssetTransfer(token_symbol=asset, amount=abs(amount)))

        return Transaction(
            tx_hash=f"kraken_{row_a.get('refid', '')}_{uuid4().hex[:8]}",
            chain="kraken",
            block_number=0,
            timestamp=timestamp,
            from_address="kraken",
            to_address="wallet",
            tx_type="swap",
            assets_in=assets_in,
            assets_out=assets_out,
            fee=fee,
            protocol="Kraken",
            raw_data={"rows": [row_a, row_b]},
        )

    def _kraken_single_row(self, row: dict) -> Optional[Transaction]:
        """Handle Kraken deposit/withdrawal/staking rows."""
        tx_type_raw = row.get("type", "").strip().lower()
        if tx_type_raw not in ("deposit", "withdrawal", "staking", "earn"):
            return None

        time_str = row.get("time", "").strip()
        timestamp = parse_datetime_utc(time_str, "%Y-%m-%d %H:%M:%S")
        amount = parse_decimal(row.get("amount", "0"))
        asset = self._kraken_normalize_asset(row.get("asset", ""))

        if amount == Decimal("0"):
            return None

        if tx_type_raw in ("deposit", "staking", "earn"):
            assets_in = [AssetTransfer(token_symbol=asset, amount=abs(amount))]
            assets_out = []
        else:
            assets_out = [AssetTransfer(token_symbol=asset, amount=abs(amount))]
            assets_in = []

        normalized_type = {"deposit": "transfer", "withdrawal": "transfer", "staking": "reward", "earn": "reward"}.get(tx_type_raw, "unknown")

        return Transaction(
            tx_hash=f"kraken_{row.get('txid', '')}_{uuid4().hex[:8]}",
            chain="kraken",
            block_number=0,
            timestamp=timestamp,
            from_address="kraken",
            to_address="wallet",
            tx_type=normalized_type,
            assets_in=assets_in,
            assets_out=assets_out,
            fee=None,
            protocol="Kraken",
            raw_data=row,
        )

    def _kraken_normalize_asset(self, asset: str) -> str:
        """Kraken prefixes assets with X (crypto) or Z (fiat). Strip them."""
        mapping = {
            "XETH": "ETH", "XXBT": "BTC", "XLTC": "LTC", "XXRP": "XRP",
            "XXLM": "XLM", "XXDG": "DOGE", "ZUSD": "USD", "ZEUR": "EUR",
            "ZGBP": "GBP",
        }
        return mapping.get(asset.upper(), asset.upper().lstrip("XZ") if len(asset) > 3 else asset)

    # ── Bitpanda (Austrian - huge in DACH) ──────────────────────────────────

    def _parse_bitpanda(self, content: str) -> list[Transaction]:
        """
        Parse Bitpanda CSV export.
        Columns: Transaction ID, Timestamp, Transaction Type, In/Out, Amount Fiat,
                 Fiat, Amount Asset, Asset, Asset market price, Asset market price currency,
                 Asset class, Product ID, Fee, Fee asset, Spread, Spread Currency, Status
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                # Filter crypto-only (Bitpanda also handles stocks, metals, indices)
                asset_class = (row.get("Asset class") or "").strip().lower()
                if asset_class and asset_class not in ("cryptocurrency", "crypto"):
                    continue

                status = (row.get("Status") or "").strip().lower()
                if status not in ("finished", "completed", "confirmed", ""):
                    continue

                timestamp_str = (row.get("Timestamp") or "").strip()
                tx_type_raw = (row.get("Transaction Type") or "").strip().lower()
                direction = (row.get("In/Out") or "").strip().lower()
                asset = (row.get("Asset") or "").strip()
                amount = parse_decimal(row.get("Amount Asset") or "0")
                fiat_amount = parse_decimal(row.get("Amount Fiat") or "0")
                fiat_currency = (row.get("Fiat") or "EUR").strip()
                fee_val = parse_decimal(row.get("Fee") or "0")
                fee_asset = (row.get("Fee asset") or fiat_currency).strip()

                if not timestamp_str or not asset or amount == Decimal("0"):
                    continue

                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if fee_val > Decimal("0"):
                    fee = AssetTransfer(token_symbol=fee_asset, amount=fee_val)

                if direction == "incoming" or tx_type_raw in ("buy", "deposit", "reward"):
                    assets_in.append(AssetTransfer(token_symbol=asset, amount=amount))
                    if tx_type_raw == "buy" and fiat_amount > Decimal("0"):
                        assets_out.append(AssetTransfer(token_symbol=fiat_currency, amount=fiat_amount))
                elif direction == "outgoing" or tx_type_raw in ("sell", "withdrawal"):
                    assets_out.append(AssetTransfer(token_symbol=asset, amount=amount))
                    if tx_type_raw == "sell" and fiat_amount > Decimal("0"):
                        assets_in.append(AssetTransfer(token_symbol=fiat_currency, amount=fiat_amount))
                else:
                    continue

                normalized_type = {
                    "buy": "swap", "sell": "swap", "deposit": "transfer",
                    "withdrawal": "transfer", "transfer": "transfer", "reward": "reward",
                }.get(tx_type_raw, "unknown")

                tx_id = row.get("Transaction ID") or f"bitpanda_{uuid4().hex[:8]}"
                transactions.append(Transaction(
                    tx_hash=f"bitpanda_{tx_id}",
                    chain="bitpanda", block_number=0, timestamp=timestamp,
                    from_address="bitpanda", to_address="wallet",
                    tx_type=normalized_type,
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="Bitpanda", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Bitpanda] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── Bison (German - Börse Stuttgart) ─────────────────────────────────────

    def _parse_bison(self, content: str) -> list[Transaction]:
        """
        Parse Bison CSV export.
        Columns: Datum, Typ, Kryptowährung, Menge, Kurs, EUR-Betrag, Gebühr
        (German headers - Date, Type, Cryptocurrency, Amount, Price, EUR Amount, Fee)
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content), delimiter=";")

        for row in reader:
            try:
                date_str = (row.get("Datum") or row.get("Date") or "").strip()
                tx_type_raw = (row.get("Typ") or row.get("Type") or "").strip().lower()
                asset = (row.get("Kryptowährung") or row.get("Cryptocurrency") or "").strip()
                amount = parse_decimal(row.get("Menge") or row.get("Amount") or "0")
                eur_amount = parse_decimal(row.get("EUR-Betrag") or row.get("EUR Amount") or "0")
                fee_val = parse_decimal(row.get("Gebühr") or row.get("Fee") or "0")

                if not date_str or not asset or amount == Decimal("0"):
                    continue

                # Try multiple German date formats
                timestamp = None
                for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y"):
                    try:
                        timestamp = parse_datetime_utc(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    continue

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if fee_val > Decimal("0"):
                    fee = AssetTransfer(token_symbol="EUR", amount=fee_val)

                # Map German type names
                if tx_type_raw in ("kauf", "buy"):
                    assets_in.append(AssetTransfer(token_symbol=asset, amount=amount))
                    if eur_amount > Decimal("0"):
                        assets_out.append(AssetTransfer(token_symbol="EUR", amount=abs(eur_amount)))
                    normalized_type = "swap"
                elif tx_type_raw in ("verkauf", "sell"):
                    assets_out.append(AssetTransfer(token_symbol=asset, amount=amount))
                    if eur_amount > Decimal("0"):
                        assets_in.append(AssetTransfer(token_symbol="EUR", amount=abs(eur_amount)))
                    normalized_type = "swap"
                elif tx_type_raw in ("einzahlung", "deposit", "empfang", "receive"):
                    assets_in.append(AssetTransfer(token_symbol=asset, amount=amount))
                    normalized_type = "transfer"
                elif tx_type_raw in ("auszahlung", "withdrawal", "senden", "send"):
                    assets_out.append(AssetTransfer(token_symbol=asset, amount=amount))
                    normalized_type = "transfer"
                else:
                    continue

                transactions.append(Transaction(
                    tx_hash=f"bison_{asset}_{date_str}_{uuid4().hex[:8]}",
                    chain="bison", block_number=0, timestamp=timestamp,
                    from_address="bison", to_address="wallet",
                    tx_type=normalized_type,
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="Bison", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Bison] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── Trade Republic (German neobroker - crypto subset) ─────────────────────

    def _parse_trade_republic(self, content: str) -> list[Transaction]:
        """
        Parse Trade Republic CSV export. Filter crypto-only rows.
        Columns: Datum, Typ, ISIN, Name, Stück, Kurs, Betrag, Gebühren
        (Date, Type, ISIN, Name, Shares/Amount, Price, Total, Fees)
        Note: Crypto rows have no ISIN (or crypto-specific identifier).
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content), delimiter=";")

        # Known crypto assets on Trade Republic
        crypto_keywords = {
            "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "cardano", "ada",
            "polygon", "matic", "polkadot", "dot", "chainlink", "link", "avalanche",
            "avax", "litecoin", "ltc", "uniswap", "uni", "dogecoin", "doge", "shiba",
            "shib", "ripple", "xrp",
        }

        for row in reader:
            try:
                date_str = (row.get("Datum") or row.get("Date") or "").strip()
                tx_type_raw = (row.get("Typ") or row.get("Type") or "").strip().lower()
                name = (row.get("Name") or "").strip()
                isin = (row.get("ISIN") or "").strip()
                amount = parse_decimal(row.get("Stück") or row.get("Shares") or row.get("Amount") or "0")
                total = parse_decimal(row.get("Betrag") or row.get("Total") or "0")
                fee_val = parse_decimal(row.get("Gebühren") or row.get("Fees") or "0")

                if not date_str or amount == Decimal("0"):
                    continue

                # Filter: skip if has ISIN (stocks/ETFs have ISINs, crypto does not)
                if isin and len(isin) == 12:
                    continue

                # Check if name matches known crypto
                name_lower = name.lower()
                is_crypto = any(kw in name_lower for kw in crypto_keywords)
                if not is_crypto:
                    continue

                # Extract the crypto symbol from the name (best effort)
                asset = self._extract_crypto_symbol(name)

                # Parse date
                timestamp = None
                for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y"):
                    try:
                        timestamp = parse_datetime_utc(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    continue

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if fee_val > Decimal("0"):
                    fee = AssetTransfer(token_symbol="EUR", amount=abs(fee_val))

                if tx_type_raw in ("kauf", "buy", "sparplan", "savings plan"):
                    assets_in.append(AssetTransfer(token_symbol=asset, amount=amount))
                    if total != Decimal("0"):
                        assets_out.append(AssetTransfer(token_symbol="EUR", amount=abs(total)))
                    normalized_type = "swap"
                elif tx_type_raw in ("verkauf", "sell"):
                    assets_out.append(AssetTransfer(token_symbol=asset, amount=amount))
                    if total != Decimal("0"):
                        assets_in.append(AssetTransfer(token_symbol="EUR", amount=abs(total)))
                    normalized_type = "swap"
                else:
                    continue

                transactions.append(Transaction(
                    tx_hash=f"trade_republic_{asset}_{date_str}_{uuid4().hex[:8]}",
                    chain="trade_republic", block_number=0, timestamp=timestamp,
                    from_address="trade_republic", to_address="wallet",
                    tx_type=normalized_type,
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="Trade Republic", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/TradeRepublic] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    @staticmethod
    def _extract_crypto_symbol(name: str) -> str:
        """Best-effort extraction of crypto ticker from Trade Republic asset name."""
        symbol_map = {
            "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "cardano": "ADA",
            "polygon": "MATIC", "polkadot": "DOT", "chainlink": "LINK", "avalanche": "AVAX",
            "litecoin": "LTC", "uniswap": "UNI", "dogecoin": "DOGE", "shiba": "SHIB",
            "ripple": "XRP",
        }
        name_lower = name.lower()
        for keyword, symbol in symbol_map.items():
            if keyword in name_lower:
                return symbol
        # Fallback: use first word or the name itself
        return name.split()[0].upper() if name else "UNKNOWN"

    # ── Gemini ────────────────────────────────────────────────────────────────

    def _parse_gemini(self, content: str) -> list[Transaction]:
        """
        Parse Gemini CSV export.
        Columns: Date, Time (UTC), Type, Symbol, Specification, Liquidity Indicator,
                 Trading Fee Currency, Trading Fee Amount, USD Amount, Trading Fee (USD),
                 Amount, Balance, Trade ID, Order ID, Order Date, Order Time,
                 Client Order ID, API Session, Tx Hash, Deposit Destination, Deposit Tx Output,
                 Withdrawal Destination, Withdrawal Tx Output
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                date_str = (row.get("Date") or "").strip()
                time_str = (row.get("Time (UTC)") or "").strip()
                tx_type_raw = (row.get("Type") or "").strip().lower()
                symbol = (row.get("Symbol") or "").strip()
                amount = parse_decimal(row.get("Amount") or row.get(symbol + " Amount") or "0")
                usd_amount = parse_decimal(row.get("USD Amount") or "0")
                fee_val = parse_decimal(row.get("Trading Fee (USD)") or row.get("Trading Fee Amount") or "0")

                if not date_str or amount == Decimal("0"):
                    continue

                datetime_str = f"{date_str} {time_str}".strip()
                timestamp = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S"):
                    try:
                        timestamp = parse_datetime_utc(datetime_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    continue

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if fee_val > Decimal("0"):
                    fee = AssetTransfer(token_symbol="USD", amount=fee_val, usd_value=fee_val)

                if tx_type_raw in ("buy", "credit", "deposit"):
                    assets_in.append(AssetTransfer(token_symbol=symbol, amount=abs(amount)))
                    if tx_type_raw == "buy" and usd_amount != Decimal("0"):
                        assets_out.append(AssetTransfer(token_symbol="USD", amount=abs(usd_amount), usd_value=abs(usd_amount)))
                    normalized_type = "swap" if tx_type_raw == "buy" else "transfer"
                elif tx_type_raw in ("sell", "debit", "withdrawal"):
                    assets_out.append(AssetTransfer(token_symbol=symbol, amount=abs(amount)))
                    if tx_type_raw == "sell" and usd_amount != Decimal("0"):
                        assets_in.append(AssetTransfer(token_symbol="USD", amount=abs(usd_amount), usd_value=abs(usd_amount)))
                    normalized_type = "swap" if tx_type_raw == "sell" else "transfer"
                else:
                    continue

                trade_id = row.get("Trade ID") or f"{uuid4().hex[:8]}"
                transactions.append(Transaction(
                    tx_hash=f"gemini_{trade_id}",
                    chain="gemini", block_number=0, timestamp=timestamp,
                    from_address="gemini", to_address="wallet",
                    tx_type=normalized_type,
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="Gemini", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Gemini] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── KuCoin ────────────────────────────────────────────────────────────────

    def _parse_kucoin(self, content: str) -> list[Transaction]:
        """
        Parse KuCoin CSV export.
        Columns: oid, symbol, dealPrice, dealValue, amount, fee, direction,
                 createdDate (or tradeCreatedAt)
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                oid = (row.get("oid") or row.get("orderOid") or "").strip()
                symbol = (row.get("symbol") or "").strip()  # e.g. "BTC-USDT"
                deal_price = parse_decimal(row.get("dealPrice") or row.get("price") or "0")
                amount = parse_decimal(row.get("amount") or row.get("dealValue") or "0")
                fee_val = parse_decimal(row.get("fee") or "0")
                direction = (row.get("direction") or row.get("side") or "").strip().lower()
                date_str = (row.get("createdDate") or row.get("tradeCreatedAt") or row.get("createdAt") or "").strip()

                if not date_str or not symbol or amount == Decimal("0"):
                    continue

                # Parse symbol pair (e.g. BTC-USDT)
                parts = symbol.split("-")
                base_asset = parts[0] if parts else symbol
                quote_asset = parts[1] if len(parts) > 1 else "USDT"

                # Parse date
                timestamp = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                    try:
                        timestamp = parse_datetime_utc(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    # Try epoch milliseconds
                    try:
                        ts = int(date_str) / 1000 if len(date_str) > 10 else int(date_str)
                        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
                    except (ValueError, OSError):
                        continue

                quote_amount = amount * deal_price if deal_price > Decimal("0") else parse_decimal(row.get("dealValue") or "0")

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if fee_val > Decimal("0"):
                    fee_symbol = (row.get("feeCurrency") or base_asset).strip()
                    fee = AssetTransfer(token_symbol=fee_symbol, amount=fee_val)

                if direction == "buy":
                    assets_in.append(AssetTransfer(token_symbol=base_asset, amount=amount))
                    assets_out.append(AssetTransfer(token_symbol=quote_asset, amount=quote_amount))
                elif direction == "sell":
                    assets_out.append(AssetTransfer(token_symbol=base_asset, amount=amount))
                    assets_in.append(AssetTransfer(token_symbol=quote_asset, amount=quote_amount))
                else:
                    continue

                transactions.append(Transaction(
                    tx_hash=f"kucoin_{oid or uuid4().hex[:8]}",
                    chain="kucoin", block_number=0, timestamp=timestamp,
                    from_address="kucoin", to_address="wallet",
                    tx_type="swap",
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="KuCoin", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/KuCoin] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── OKX ───────────────────────────────────────────────────────────────────

    def _parse_okx(self, content: str) -> list[Transaction]:
        """
        Parse OKX CSV export (trade history).
        Columns: Order ID, Trade Time, Pair, Side, Price, Amount, Total, Fee, Fee Currency
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                order_id = (row.get("Order ID") or row.get("orderId") or "").strip()
                date_str = (row.get("Trade Time") or row.get("tradeTime") or row.get("time") or "").strip()
                pair = (row.get("Pair") or row.get("instId") or "").strip()  # e.g. "BTC-USDT"
                side = (row.get("Side") or row.get("side") or "").strip().lower()
                price = parse_decimal(row.get("Price") or row.get("px") or "0")
                amount = parse_decimal(row.get("Amount") or row.get("sz") or "0")
                total = parse_decimal(row.get("Total") or "0")
                fee_val = parse_decimal(row.get("Fee") or row.get("fee") or "0")
                fee_currency = (row.get("Fee Currency") or row.get("feeCcy") or "").strip()

                if not date_str or not pair or amount == Decimal("0"):
                    continue

                parts = pair.replace("/", "-").split("-")
                base_asset = parts[0] if parts else pair
                quote_asset = parts[1] if len(parts) > 1 else "USDT"

                timestamp = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
                    try:
                        timestamp = parse_datetime_utc(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    try:
                        ts = int(date_str) / 1000 if len(date_str) > 10 else int(date_str)
                        timestamp = datetime.fromtimestamp(ts, tz=timezone.utc)
                    except (ValueError, OSError):
                        continue

                quote_amount = total if total > Decimal("0") else amount * price

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if abs(fee_val) > Decimal("0"):
                    fee = AssetTransfer(token_symbol=fee_currency or quote_asset, amount=abs(fee_val))

                if side == "buy":
                    assets_in.append(AssetTransfer(token_symbol=base_asset, amount=amount))
                    assets_out.append(AssetTransfer(token_symbol=quote_asset, amount=quote_amount))
                elif side == "sell":
                    assets_out.append(AssetTransfer(token_symbol=base_asset, amount=amount))
                    assets_in.append(AssetTransfer(token_symbol=quote_asset, amount=quote_amount))
                else:
                    continue

                transactions.append(Transaction(
                    tx_hash=f"okx_{order_id or uuid4().hex[:8]}",
                    chain="okx", block_number=0, timestamp=timestamp,
                    from_address="okx", to_address="wallet",
                    tx_type="swap",
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="OKX", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/OKX] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── Crypto.com ────────────────────────────────────────────────────────────

    def _parse_crypto_com(self, content: str) -> list[Transaction]:
        """
        Parse Crypto.com CSV export.
        Columns: Timestamp (UTC), Transaction Description, Currency, Amount,
                 To Currency, To Amount, Native Currency, Native Amount,
                 Native Amount (in USD), Transaction Kind, Transaction Hash
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                date_str = (row.get("Timestamp (UTC)") or row.get("Timestamp") or "").strip()
                description = (row.get("Transaction Description") or "").strip()
                currency = (row.get("Currency") or "").strip()
                amount = parse_decimal(row.get("Amount") or "0")
                to_currency = (row.get("To Currency") or "").strip()
                to_amount = parse_decimal(row.get("To Amount") or "0")
                native_amount_usd = parse_decimal(row.get("Native Amount (in USD)") or "0")
                tx_kind = (row.get("Transaction Kind") or "").strip().lower()
                tx_hash_raw = (row.get("Transaction Hash") or "").strip()

                if not date_str or not currency or amount == Decimal("0"):
                    continue

                timestamp = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S.%f"):
                    try:
                        timestamp = parse_datetime_utc(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    continue

                assets_in: list[AssetTransfer] = []
                assets_out: list[AssetTransfer] = []
                fee: Optional[AssetTransfer] = None

                if tx_kind in ("crypto_purchase", "viban_purchase", "buy"):
                    assets_in.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    if to_currency:
                        assets_out.append(AssetTransfer(token_symbol=to_currency, amount=abs(to_amount)))
                    normalized_type = "swap"

                elif tx_kind in ("crypto_viban_exchange", "crypto_exchange"):
                    # Swap between cryptos
                    assets_out.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    if to_currency and to_amount > Decimal("0"):
                        assets_in.append(AssetTransfer(token_symbol=to_currency, amount=abs(to_amount)))
                    normalized_type = "swap"

                elif tx_kind in ("crypto_withdrawal", "crypto_to_exchange", "withdrawal"):
                    assets_out.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    normalized_type = "transfer"

                elif tx_kind in ("crypto_deposit", "exchange_to_crypto_transfer", "deposit"):
                    assets_in.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    normalized_type = "transfer"

                elif tx_kind in ("referral_bonus", "referral_card_cashback", "reimbursement",
                                  "card_cashback_reverted", "crypto_earn_interest_paid",
                                  "mco_stake_reward", "rewards_platform_deposit_credited"):
                    assets_in.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    normalized_type = "reward"

                elif tx_kind in ("card_top_up", "dust_conversion_credited", "dust_conversion_debited"):
                    if amount > Decimal("0"):
                        assets_in.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    else:
                        assets_out.append(AssetTransfer(token_symbol=currency, amount=abs(amount)))
                    normalized_type = "swap"

                else:
                    continue

                tx_id = tx_hash_raw or f"crypto_com_{uuid4().hex[:8]}"
                transactions.append(Transaction(
                    tx_hash=f"crypto_com_{tx_id}",
                    chain="crypto_com", block_number=0, timestamp=timestamp,
                    from_address="crypto_com", to_address="wallet",
                    tx_type=normalized_type,
                    assets_in=assets_in, assets_out=assets_out, fee=fee,
                    protocol="Crypto.com", raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Crypto.com] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── Generic / fallback ───────────────────────────────────────────────────

    def _parse_generic(self, content: str) -> list[Transaction]:
        """
        Generic CSV parser: expects columns Date, Type, Asset, Amount, Fee, Notes.
        Amount can be negative (out) or positive (in).
        """
        transactions: list[Transaction] = []
        reader = csv.DictReader(io.StringIO(content))

        for row in reader:
            try:
                date_str = (row.get("Date") or row.get("date", "")).strip()
                asset = (row.get("Asset") or row.get("asset", "")).strip()
                amount = parse_decimal(row.get("Amount") or row.get("amount", "0"))
                fee_val = parse_decimal(row.get("Fee") or row.get("fee", "0"))
                tx_type_raw = (row.get("Type") or row.get("type", "unknown")).strip().lower()

                if not date_str or not asset or amount == Decimal("0"):
                    continue

                # Try multiple date formats
                timestamp = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y"):
                    try:
                        timestamp = parse_datetime_utc(date_str, fmt)
                        break
                    except ValueError:
                        continue
                if timestamp is None:
                    continue

                transfer = AssetTransfer(token_symbol=asset, amount=abs(amount))
                assets_in = [transfer] if amount > Decimal("0") else []
                assets_out = [transfer] if amount < Decimal("0") else []
                fee: Optional[AssetTransfer] = AssetTransfer(token_symbol="USD", amount=fee_val) if fee_val > Decimal("0") else None

                transactions.append(Transaction(
                    tx_hash=f"generic_{asset}_{date_str}_{uuid4().hex[:8]}",
                    chain="csv",
                    block_number=0,
                    timestamp=timestamp,
                    from_address="exchange",
                    to_address="wallet",
                    tx_type=tx_type_raw,
                    assets_in=assets_in,
                    assets_out=assets_out,
                    fee=fee,
                    protocol=None,
                    raw_data=dict(row),
                ))
            except Exception as exc:
                print(f"[ExchangeImporter/Generic] Skipping row: {exc}")

        return sorted(transactions, key=lambda t: t.timestamp)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _split_amount_symbol(value: str) -> tuple[Decimal, str]:
        """Split '0.5ETH' → (Decimal('0.5'), 'ETH'). Also handles '1000 USDT'."""
        value = value.strip()
        # Strip trailing whitespace, find where digits end
        i = 0
        while i < len(value) and (value[i].isdigit() or value[i] in (".", ",", "-")):
            i += 1
        num_part = value[:i].replace(",", "")
        sym_part = value[i:].strip()
        try:
            qty = Decimal(num_part) if num_part else Decimal("0")
        except InvalidOperation:
            qty = Decimal("0")
        return qty, sym_part or "UNKNOWN"
