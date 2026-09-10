"""
SQLite storage layer for defi-tax-engine.

Schema:
    wallets       - user-configured wallet addresses
    transactions  - raw normalized transactions (PK: tx_hash + chain)
    tax_lots      - one row per acquisition lot
    disposals     - one row per disposal event (per method)
    price_cache   - cached historical prices (PK: token + date)

All monetary values are stored as TEXT and loaded as Decimal to avoid
floating-point drift.

WAL mode is enabled for safe concurrent reads during long import jobs.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Generator, Optional

from src.config import DB_PATH


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decimal(value: str | None) -> Optional[Decimal]:
    return Decimal(value) if value is not None else None


def _iso(dt: datetime | str | None) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.isoformat()
    return dt


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS wallets (
    id               TEXT PRIMARY KEY,
    address          TEXT NOT NULL,
    chain            TEXT NOT NULL,
    label            TEXT,
    last_imported_at TEXT
);

CREATE TABLE IF NOT EXISTS transactions (
    tx_hash    TEXT NOT NULL,
    chain      TEXT NOT NULL,
    timestamp  TEXT NOT NULL,
    tx_type    TEXT,
    protocol   TEXT,
    raw_json   TEXT,
    PRIMARY KEY (tx_hash, chain)
);

CREATE TABLE IF NOT EXISTS tax_lots (
    id               TEXT PRIMARY KEY,
    token            TEXT NOT NULL,
    amount           TEXT NOT NULL,
    cost_basis_usd   TEXT NOT NULL,
    acquisition_date TEXT NOT NULL,
    remaining        TEXT NOT NULL,
    source           TEXT NOT NULL,
    tx_hash          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS disposals (
    id             TEXT PRIMARY KEY,
    token          TEXT NOT NULL,
    amount         TEXT NOT NULL,
    proceeds_usd   TEXT NOT NULL,
    cost_basis_usd TEXT NOT NULL,
    gain_loss_usd  TEXT NOT NULL,
    holding_period TEXT NOT NULL,
    method         TEXT NOT NULL,
    disposal_date  TEXT NOT NULL,
    tx_hash        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_cache (
    token     TEXT NOT NULL,
    date      TEXT NOT NULL,
    usd_price TEXT NOT NULL,
    source    TEXT,
    PRIMARY KEY (token, date)
);
"""


class Database:
    """Manages the SQLite connection and applies the schema."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._apply_schema()

    def _apply_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Repository: wallets
# ---------------------------------------------------------------------------

class WalletRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, address: str, chain: str, label: str | None = None) -> str:
        wallet_id = str(uuid.uuid4())
        with self._db.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO wallets (id, address, chain, label) VALUES (?,?,?,?)",
                (wallet_id, address.lower(), chain.lower(), label),
            )
        return wallet_id

    def get_all(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM wallets").fetchall()
        return [dict(r) for r in rows]

    def get_addresses(self) -> list[str]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT address FROM wallets").fetchall()
        return [r["address"] for r in rows]

    def update_last_imported(self, address: str, chain: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE wallets SET last_imported_at=? WHERE address=? AND chain=?",
                (_now_iso(), address.lower(), chain.lower()),
            )

    def get_last_imported(self, address: str, chain: str) -> Optional[datetime]:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT last_imported_at FROM wallets WHERE address=? AND chain=?",
                (address.lower(), chain.lower()),
            ).fetchone()
        if row and row["last_imported_at"]:
            return datetime.fromisoformat(row["last_imported_at"])
        return None


# ---------------------------------------------------------------------------
# Repository: transactions
# ---------------------------------------------------------------------------

class TransactionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(
        self,
        tx_hash: str,
        chain: str,
        timestamp: datetime | str,
        tx_type: str | None,
        protocol: str | None,
        raw_data: dict | None,
    ) -> None:
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transactions
                    (tx_hash, chain, timestamp, tx_type, protocol, raw_json)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    tx_hash,
                    chain.lower(),
                    _iso(timestamp),
                    tx_type,
                    protocol,
                    json.dumps(raw_data) if raw_data else None,
                ),
            )

    def upsert_many(self, rows: list[dict]) -> None:
        """Bulk upsert for efficiency during import."""
        with self._db.connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO transactions
                    (tx_hash, chain, timestamp, tx_type, protocol, raw_json)
                VALUES (:tx_hash, :chain, :timestamp, :tx_type, :protocol, :raw_json)
                """,
                [
                    {
                        "tx_hash": r["tx_hash"],
                        "chain": r["chain"].lower(),
                        "timestamp": _iso(r.get("timestamp")),
                        "tx_type": r.get("tx_type"),
                        "protocol": r.get("protocol"),
                        "raw_json": json.dumps(r["raw_data"]) if r.get("raw_data") else None,
                    }
                    for r in rows
                ],
            )

    def exists(self, tx_hash: str, chain: str) -> bool:
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM transactions WHERE tx_hash=? AND chain=?",
                (tx_hash, chain.lower()),
            ).fetchone()
        return row is not None

    def get_by_wallet(
        self,
        address: str,
        year: int | None = None,
    ) -> list[dict]:
        """Return transactions whose raw_json contains the wallet address."""
        query = "SELECT * FROM transactions WHERE raw_json LIKE ?"
        params: list = [f"%{address.lower()}%"]
        if year:
            query += " AND timestamp LIKE ?"
            params.append(f"{year}%")
        with self._db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_latest_timestamp(self, chain: str) -> Optional[datetime]:
        """Used for incremental import: find the most recent tx timestamp."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) as latest FROM transactions WHERE chain=?",
                (chain.lower(),),
            ).fetchone()
        if row and row["latest"]:
            return datetime.fromisoformat(row["latest"])
        return None

    def count(self, chain: str | None = None) -> int:
        with self._db.connect() as conn:
            if chain:
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM transactions WHERE chain=?",
                    (chain.lower(),),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()
        return row["n"] if row else 0

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("raw_json"):
            d["raw_data"] = json.loads(d.pop("raw_json"))
        else:
            d["raw_data"] = None
            d.pop("raw_json", None)
        return d


# ---------------------------------------------------------------------------
# Repository: tax_lots
# ---------------------------------------------------------------------------

class TaxLotRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(
        self,
        token: str,
        amount: Decimal,
        cost_basis_usd: Decimal,
        acquisition_date: datetime | str,
        source: str,
        tx_hash: str,
    ) -> str:
        lot_id = str(uuid.uuid4())
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO tax_lots
                    (id, token, amount, cost_basis_usd, acquisition_date, remaining, source, tx_hash)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    lot_id,
                    token,
                    str(amount),
                    str(cost_basis_usd),
                    _iso(acquisition_date),
                    str(amount),   # remaining starts equal to amount
                    source,
                    tx_hash,
                ),
            )
        return lot_id

    def update_remaining(self, lot_id: str, remaining: Decimal) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE tax_lots SET remaining=? WHERE id=?",
                (str(remaining), lot_id),
            )

    def get_open_lots(self, token: str, order_by: str = "acquisition_date ASC") -> list[dict]:
        """Return lots with remaining > 0, in the order requested (FIFO/LIFO/HIFO)."""
        allowed_orders = {
            "acquisition_date ASC": "acquisition_date ASC",
            "acquisition_date DESC": "acquisition_date DESC",
            "cost_basis_usd DESC": "CAST(cost_basis_usd AS REAL) DESC",
        }
        order_clause = allowed_orders.get(order_by, "acquisition_date ASC")
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM tax_lots WHERE token=? AND CAST(remaining AS REAL) > 0 ORDER BY {order_clause}",
                (token,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_by_tx(self, tx_hash: str) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tax_lots WHERE tx_hash=?", (tx_hash,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_all(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM tax_lots ORDER BY acquisition_date").fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["amount"] = _decimal(d["amount"])
        d["cost_basis_usd"] = _decimal(d["cost_basis_usd"])
        d["remaining"] = _decimal(d["remaining"])
        return d


# ---------------------------------------------------------------------------
# Repository: disposals
# ---------------------------------------------------------------------------

class DisposalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def insert(
        self,
        token: str,
        amount: Decimal,
        proceeds_usd: Decimal,
        cost_basis_usd: Decimal,
        gain_loss_usd: Decimal,
        holding_period: str,
        method: str,
        disposal_date: datetime | str,
        tx_hash: str,
    ) -> str:
        disposal_id = str(uuid.uuid4())
        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO disposals
                    (id, token, amount, proceeds_usd, cost_basis_usd,
                     gain_loss_usd, holding_period, method, disposal_date, tx_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    disposal_id,
                    token,
                    str(amount),
                    str(proceeds_usd),
                    str(cost_basis_usd),
                    str(gain_loss_usd),
                    holding_period,
                    method.upper(),
                    _iso(disposal_date),
                    tx_hash,
                ),
            )
        return disposal_id

    def get_by_year(self, year: int, method: str | None = None) -> list[dict]:
        query = "SELECT * FROM disposals WHERE disposal_date LIKE ?"
        params: list = [f"{year}%"]
        if method:
            query += " AND method=?"
            params.append(method.upper())
        query += " ORDER BY disposal_date"
        with self._db.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def delete_by_method(self, method: str) -> int:
        """Remove all disposals for a given method (before recalculating)."""
        with self._db.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM disposals WHERE method=?", (method.upper(),)
            )
        return cursor.rowcount

    def get_all(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM disposals ORDER BY disposal_date").fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["amount"] = _decimal(d["amount"])
        d["proceeds_usd"] = _decimal(d["proceeds_usd"])
        d["cost_basis_usd"] = _decimal(d["cost_basis_usd"])
        d["gain_loss_usd"] = _decimal(d["gain_loss_usd"])
        return d


# ---------------------------------------------------------------------------
# Repository: price_cache
# ---------------------------------------------------------------------------

class PriceCacheRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set(self, token: str, date: str, usd_price: Decimal, source: str = "coingecko") -> None:
        """Cache a price. Date must be YYYY-MM-DD."""
        with self._db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO price_cache (token, date, usd_price, source) VALUES (?,?,?,?)",
                (token.lower(), date, str(usd_price), source),
            )

    def get(self, token: str, date: str) -> Optional[Decimal]:
        """Return cached price or None if not cached."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT usd_price FROM price_cache WHERE token=? AND date=?",
                (token.lower(), date),
            ).fetchone()
        return _decimal(row["usd_price"]) if row else None

    def has(self, token: str, date: str) -> bool:
        return self.get(token, date) is not None

    def get_all(self) -> list[dict]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM price_cache").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Full export
# ---------------------------------------------------------------------------

def export_full(db: Database) -> dict:
    """
    Export the entire database as a self-contained JSON dict.
    Suitable for backup and re-import.
    """
    wallets_repo = WalletRepository(db)
    tx_repo = TransactionRepository(db)
    lots_repo = TaxLotRepository(db)
    disposals_repo = DisposalRepository(db)
    price_repo = PriceCacheRepository(db)

    def _decimal_to_str(obj):
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    data = {
        "exported_at": _now_iso(),
        "wallets": wallets_repo.get_all(),
        "transactions": tx_repo.get_by_wallet(""),  # all - we'll fix below
        "tax_lots": [
            {k: str(v) if isinstance(v, Decimal) else v for k, v in lot.items()}
            for lot in lots_repo.get_all()
        ],
        "disposals": [
            {k: str(v) if isinstance(v, Decimal) else v for k, v in d.items()}
            for d in disposals_repo.get_all()
        ],
        "price_cache": price_repo.get_all(),
    }

    # Override transactions with full unfiltered fetch
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM transactions ORDER BY timestamp").fetchall()
    data["transactions"] = [TransactionRepository._row_to_dict(r) for r in rows]

    return data
