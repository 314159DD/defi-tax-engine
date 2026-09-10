"""
Smoke tests for the storage layer (Task 1.4).

Run: pytest tests/test_storage.py -v
"""
import json
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# Override DB_PATH before importing storage
import os


@pytest.fixture
def tmp_db(tmp_path):
    db_file = str(tmp_path / "test.db")
    os.environ["DB_PATH"] = db_file
    # Re-import with patched path
    import importlib
    import src.config as cfg
    cfg.DB_PATH = db_file

    from src.storage.database import Database
    db = Database(db_path=db_file)
    yield db


def test_wallet_add_and_list(tmp_db):
    from src.storage.database import WalletRepository
    repo = WalletRepository(tmp_db)
    wid = repo.add("0xABC", "ethereum", label="Main")
    wallets = repo.get_all()
    assert len(wallets) == 1
    assert wallets[0]["address"] == "0xabc"
    assert wallets[0]["chain"] == "ethereum"


def test_wallet_last_imported(tmp_db):
    from src.storage.database import WalletRepository
    repo = WalletRepository(tmp_db)
    repo.add("0xDEF", "polygon")
    assert repo.get_last_imported("0xDEF", "polygon") is None
    repo.update_last_imported("0xDEF", "polygon")
    ts = repo.get_last_imported("0xDEF", "polygon")
    assert ts is not None


def test_transaction_upsert_and_exists(tmp_db):
    from src.storage.database import TransactionRepository
    repo = TransactionRepository(tmp_db)
    repo.upsert(
        tx_hash="0x123",
        chain="ethereum",
        timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
        tx_type="swap",
        protocol="uniswap",
        raw_data={"foo": "bar"},
    )
    assert repo.exists("0x123", "ethereum")
    assert not repo.exists("0x999", "ethereum")


def test_transaction_incremental_import_timestamp(tmp_db):
    from src.storage.database import TransactionRepository
    repo = TransactionRepository(tmp_db)
    repo.upsert("0xA", "ethereum", datetime(2024, 1, 1, tzinfo=timezone.utc), "transfer", None, None)
    repo.upsert("0xB", "ethereum", datetime(2024, 6, 15, tzinfo=timezone.utc), "swap", None, None)
    latest = repo.get_latest_timestamp("ethereum")
    assert latest.year == 2024
    assert latest.month == 6


def test_tax_lot_insert_and_query(tmp_db):
    from src.storage.database import TaxLotRepository
    repo = TaxLotRepository(tmp_db)
    lot_id = repo.insert(
        token="ETH",
        amount=Decimal("1.5"),
        cost_basis_usd=Decimal("3000.00"),
        acquisition_date=datetime(2023, 3, 1, tzinfo=timezone.utc),
        source="purchase",
        tx_hash="0xLOT1",
    )
    lots = repo.get_open_lots("ETH")
    assert len(lots) == 1
    assert lots[0]["amount"] == Decimal("1.5")
    assert lots[0]["remaining"] == Decimal("1.5")

    repo.update_remaining(lot_id, Decimal("0.5"))
    lots = repo.get_open_lots("ETH")
    assert lots[0]["remaining"] == Decimal("0.5")


def test_disposal_insert_and_query(tmp_db):
    from src.storage.database import DisposalRepository
    repo = DisposalRepository(tmp_db)
    repo.insert(
        token="ETH",
        amount=Decimal("1.0"),
        proceeds_usd=Decimal("4000.00"),
        cost_basis_usd=Decimal("3000.00"),
        gain_loss_usd=Decimal("1000.00"),
        holding_period="long-term",
        method="FIFO",
        disposal_date=datetime(2024, 5, 10, tzinfo=timezone.utc),
        tx_hash="0xDISP1",
    )
    disposals = repo.get_by_year(2024, method="FIFO")
    assert len(disposals) == 1
    assert disposals[0]["gain_loss_usd"] == Decimal("1000.00")


def test_price_cache(tmp_db):
    from src.storage.database import PriceCacheRepository
    repo = PriceCacheRepository(tmp_db)
    assert not repo.has("eth", "2024-01-15")
    repo.set("ETH", "2024-01-15", Decimal("2345.67"))
    assert repo.has("eth", "2024-01-15")
    price = repo.get("eth", "2024-01-15")
    assert price == Decimal("2345.67")


def test_full_export(tmp_db):
    from src.storage.database import (
        WalletRepository, TransactionRepository, TaxLotRepository,
        DisposalRepository, PriceCacheRepository, export_full
    )
    WalletRepository(tmp_db).add("0xEXP", "base")
    PriceCacheRepository(tmp_db).set("USDC", "2024-03-01", Decimal("1.00"))

    data = export_full(tmp_db)
    assert "wallets" in data
    assert "transactions" in data
    assert "tax_lots" in data
    assert "disposals" in data
    assert "price_cache" in data
    assert data["price_cache"][0]["usd_price"] == "1.00"
    # Ensure it serialises to JSON without error
    json.dumps(data)
