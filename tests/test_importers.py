"""
Smoke tests for Task 1.1: Multi-Chain Wallet Import.

Tests the data models and CSV parsers using local fixture files.
Network-dependent tests (EVM, Solana) are skipped unless env keys are set.
"""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from src.importers.exchange import ExchangeImporter
from src.importers.models import AssetTransfer, Transaction

FIXTURES = Path(__file__).parent / "fixtures"


# ── Model tests ───────────────────────────────────────────────────────────────

class TestAssetTransfer:
    def test_decimal_amount_accepted(self):
        t = AssetTransfer(token_symbol="ETH", amount=Decimal("1.5"))
        assert t.amount == Decimal("1.5")

    def test_float_amount_rejected(self):
        """Transaction.__post_init__ must reject float amounts."""
        from datetime import datetime, timezone
        with pytest.raises(TypeError, match="Decimal"):
            Transaction(
                tx_hash="0xabc",
                chain="ethereum",
                block_number=1,
                timestamp=datetime.now(timezone.utc),
                from_address="0x1",
                to_address="0x2",
                tx_type="transfer",
                assets_in=[AssetTransfer(token_symbol="ETH", amount=1.5)],  # type: ignore
                assets_out=[],
                fee=None,
                protocol=None,
            )


# ── Coinbase CSV tests ────────────────────────────────────────────────────────

class TestCoinbaseImporter:
    def setup_method(self):
        self.importer = ExchangeImporter()
        self.fixture = FIXTURES / "coinbase_sample.csv"

    def test_parses_four_rows(self):
        txs = self.importer.parse_file(self.fixture, "coinbase")
        assert len(txs) == 4

    def test_buy_is_swap(self):
        txs = self.importer.parse_file(self.fixture, "coinbase")
        buy = next(t for t in txs if t.tx_type == "swap" and any(a.token_symbol == "ETH" for a in t.assets_in))
        assert buy is not None

    def test_sell_has_eth_out(self):
        txs = self.importer.parse_file(self.fixture, "coinbase")
        sell = next(t for t in txs if t.tx_type == "swap" and any(a.token_symbol == "ETH" for a in t.assets_out))
        assert sell is not None

    def test_earn_is_airdrop(self):
        txs = self.importer.parse_file(self.fixture, "coinbase")
        earn = next(t for t in txs if "ALGO" in [a.token_symbol for a in t.assets_in])
        assert earn.tx_type == "airdrop"

    def test_all_amounts_are_decimal(self):
        txs = self.importer.parse_file(self.fixture, "coinbase")
        for tx in txs:
            for transfer in [*tx.assets_in, *tx.assets_out]:
                assert isinstance(transfer.amount, Decimal), f"Float found in {tx.tx_hash}"

    def test_sorted_by_timestamp(self):
        txs = self.importer.parse_file(self.fixture, "coinbase")
        timestamps = [t.timestamp for t in txs]
        assert timestamps == sorted(timestamps)


# ── Binance CSV tests ─────────────────────────────────────────────────────────

class TestBinanceImporter:
    def setup_method(self):
        self.importer = ExchangeImporter()
        self.fixture = FIXTURES / "binance_sample.csv"

    def test_parses_three_rows(self):
        txs = self.importer.parse_file(self.fixture, "binance")
        assert len(txs) == 3

    def test_all_are_swaps(self):
        txs = self.importer.parse_file(self.fixture, "binance")
        assert all(t.tx_type == "swap" for t in txs)

    def test_buy_eth_assets_in(self):
        txs = self.importer.parse_file(self.fixture, "binance")
        eth_buy = next(t for t in txs if any(a.token_symbol == "ETH" for a in t.assets_in))
        assert any(a.token_symbol == "USDT" for a in eth_buy.assets_out)

    def test_all_amounts_are_decimal(self):
        txs = self.importer.parse_file(self.fixture, "binance")
        for tx in txs:
            for transfer in [*tx.assets_in, *tx.assets_out]:
                assert isinstance(transfer.amount, Decimal)


# ── Database smoke test ───────────────────────────────────────────────────────

class TestDatabase:
    def test_initialize_and_store(self, tmp_path):
        from src.storage.database import Database, TransactionRepository, WalletRepository
        from datetime import datetime, timezone

        db = Database(str(tmp_path / "test.db"))
        wallet_repo = WalletRepository(db)
        tx_repo = TransactionRepository(db)

        wallet_repo.add("0xabc", "ethereum", "Test wallet")
        wallets = wallet_repo.get_all()
        assert len(wallets) == 1
        assert wallets[0]["address"] == "0xabc"

        tx_repo.upsert(
            tx_hash="0xdeadbeef",
            chain="ethereum",
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            tx_type="swap",
            protocol="Uniswap",
            raw_data={"test": True},
        )
        assert tx_repo.count("ethereum") == 1
        assert tx_repo.exists("0xdeadbeef", "ethereum")
        assert not tx_repo.exists("0xdeadbeef", "polygon")
