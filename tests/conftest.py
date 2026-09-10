"""Shared test fixtures for defi-tax-engine."""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.importers.models import AssetTransfer, Transaction
from src.storage.database import Database


# ---------------------------------------------------------------------------
# Database fixture - each test gets a fresh in-memory SQLite
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Return a Database backed by a temp file (SQLite in-memory doesn't
    survive re-opens, so we use a tmpdir file instead)."""
    db_path = str(tmp_path / "test_tax.db")
    os.environ["DB_PATH"] = db_path
    return Database(db_path)


# ---------------------------------------------------------------------------
# Transaction builder helpers
# ---------------------------------------------------------------------------

def make_tx(
    tx_hash: str = "0xtest",
    chain: str = "ethereum",
    timestamp: datetime | None = None,
    from_address: str = "0xuser1",
    to_address: str = "0xcontract",
    tx_type: str = "swap",
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
    fee: AssetTransfer | None = None,
    protocol: str | None = None,
) -> Transaction:
    return Transaction(
        tx_hash=tx_hash,
        chain=chain,
        block_number=1,
        timestamp=timestamp or datetime(2025, 6, 1, tzinfo=timezone.utc),
        from_address=from_address,
        to_address=to_address,
        tx_type=tx_type,
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=fee,
        protocol=protocol,
        raw_data={},
    )


def make_transfer(
    symbol: str,
    amount: str,
    usd_value: str | None = None,
    token_address: str | None = None,
) -> AssetTransfer:
    return AssetTransfer(
        token_symbol=symbol,
        amount=Decimal(amount),
        token_address=token_address,
        usd_value=Decimal(usd_value) if usd_value else None,
    )
