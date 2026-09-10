"""
1099-DA CSV importer for US crypto tax reporting.

Starting 2025 tax year, centralized exchanges issue Form 1099-DA reporting
gross proceeds from digital asset dispositions. This module parses CSV exports
from major exchanges and normalizes them into Form1099DAEntry objects.

Supported formats:
  - Coinbase 1099-DA CSV
  - Kraken 1099-DA CSV
  - Binance.US 1099-DA CSV
  - Generic CSV with user-provided column mapping

CRITICAL: All monetary values use decimal.Decimal - NEVER float.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Form1099DAEntry:
    """A single line item from a 1099-DA form."""
    asset: str
    date_acquired: Optional[date]  # may be "VARIOUS" → None
    date_sold: date
    proceeds: Decimal
    cost_basis: Optional[Decimal]  # not required for 2025
    gain_loss: Optional[Decimal]
    broker_name: str
    is_covered: bool
    raw_row: dict  # original CSV row for debugging

    def __post_init__(self) -> None:
        if not isinstance(self.proceeds, Decimal):
            raise TypeError(f"proceeds must be Decimal, got {type(self.proceeds)}")
        if self.cost_basis is not None and not isinstance(self.cost_basis, Decimal):
            raise TypeError(f"cost_basis must be Decimal, got {type(self.cost_basis)}")
        if self.gain_loss is not None and not isinstance(self.gain_loss, Decimal):
            raise TypeError(f"gain_loss must be Decimal, got {type(self.gain_loss)}")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_decimal(value: str) -> Optional[Decimal]:
    """Parse a decimal string, stripping currency symbols and commas."""
    if not value or not value.strip():
        return None
    cleaned = value.strip().replace(",", "").lstrip("$").rstrip()
    if not cleaned or cleaned == "-" or cleaned.lower() in ("n/a", "na", "none", ""):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_decimal_required(value: str) -> Decimal:
    """Parse a decimal that must be present. Returns Decimal('0') if unparseable."""
    result = _parse_decimal(value)
    return result if result is not None else Decimal("0")


def _parse_date(value: str) -> Optional[date]:
    """Parse a date string. Returns None for 'VARIOUS' or empty."""
    if not value or not value.strip():
        return None
    cleaned = value.strip().upper()
    if cleaned in ("VARIOUS", "N/A", "NA", "NONE", "-", ""):
        return None

    # Try common date formats
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    # Try ISO datetime
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        pass

    return None


def _parse_date_required(value: str) -> date:
    """Parse a date that must be present. Raises ValueError if unparseable."""
    result = _parse_date(value)
    if result is None:
        raise ValueError(f"Could not parse required date: {value!r}")
    return result


def _normalize_asset(value: str) -> str:
    """Normalize asset name: uppercase, strip whitespace."""
    return value.strip().upper()


def _detect_covered(row: dict) -> bool:
    """Detect if a transaction is a covered security from various column names."""
    for key in ("covered", "is_covered", "security_type", "box_5"):
        val = row.get(key, "").strip().lower()
        if val in ("yes", "true", "1", "covered", "y"):
            return True
        if val in ("no", "false", "0", "uncovered", "n", "non-covered"):
            return False
    # Default: assume uncovered for 2025 (first year, most are uncovered)
    return False


# ---------------------------------------------------------------------------
# Header detection for auto-format detection
# ---------------------------------------------------------------------------

# Canonical header signatures per exchange
_COINBASE_HEADERS = {"asset name", "date acquired", "date sold or disposed", "proceeds"}
_KRAKEN_HEADERS = {"asset", "date acquired", "date of sale", "gross proceeds"}
_BINANCE_HEADERS = {"asset", "date acquired", "date sold", "gross proceeds"}


def detect_format(headers: set[str]) -> str:
    """
    Auto-detect exchange format from CSV headers.

    Returns one of: 'coinbase', 'kraken', 'binance', 'generic'.
    """
    lower_headers = {h.strip().lower() for h in headers}

    if _COINBASE_HEADERS.issubset(lower_headers):
        return "coinbase"
    if _KRAKEN_HEADERS.issubset(lower_headers):
        return "kraken"
    if _BINANCE_HEADERS.issubset(lower_headers):
        return "binance"
    return "generic"


# ---------------------------------------------------------------------------
# Per-exchange parsers
# ---------------------------------------------------------------------------

def parse_coinbase_1099da(csv_path: str | Path) -> list[Form1099DAEntry]:
    """
    Parse a Coinbase 1099-DA CSV export.

    Expected columns:
      Asset Name, Date Acquired, Date Sold or Disposed, Proceeds,
      Cost Basis, Gain or Loss, Covered
    """
    content = Path(csv_path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    entries: list[Form1099DAEntry] = []
    for row in reader:
        # Normalize keys to lower case for flexible matching
        norm = {k.strip().lower(): v for k, v in row.items()}

        asset = _normalize_asset(
            norm.get("asset name", "") or norm.get("asset", "")
        )
        if not asset:
            continue  # skip empty rows

        entries.append(Form1099DAEntry(
            asset=asset,
            date_acquired=_parse_date(
                norm.get("date acquired", "")
            ),
            date_sold=_parse_date_required(
                norm.get("date sold or disposed", "")
                or norm.get("date sold", "")
            ),
            proceeds=_parse_decimal_required(
                norm.get("proceeds", "")
            ),
            cost_basis=_parse_decimal(
                norm.get("cost basis", "")
            ),
            gain_loss=_parse_decimal(
                norm.get("gain or loss", "")
                or norm.get("gain/loss", "")
            ),
            broker_name="Coinbase",
            is_covered=_detect_covered(norm),
            raw_row=dict(row),
        ))

    return entries


def parse_kraken_1099da(csv_path: str | Path) -> list[Form1099DAEntry]:
    """
    Parse a Kraken 1099-DA CSV export.

    Expected columns:
      Asset, Date Acquired, Date of Sale, Gross Proceeds,
      Cost Basis, Gain/Loss, Transaction Type
    """
    content = Path(csv_path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    entries: list[Form1099DAEntry] = []
    for row in reader:
        norm = {k.strip().lower(): v for k, v in row.items()}

        asset = _normalize_asset(norm.get("asset", ""))
        if not asset:
            continue

        entries.append(Form1099DAEntry(
            asset=asset,
            date_acquired=_parse_date(
                norm.get("date acquired", "")
            ),
            date_sold=_parse_date_required(
                norm.get("date of sale", "")
                or norm.get("date sold", "")
            ),
            proceeds=_parse_decimal_required(
                norm.get("gross proceeds", "")
                or norm.get("proceeds", "")
            ),
            cost_basis=_parse_decimal(
                norm.get("cost basis", "")
            ),
            gain_loss=_parse_decimal(
                norm.get("gain/loss", "")
                or norm.get("gain or loss", "")
            ),
            broker_name="Kraken",
            is_covered=_detect_covered(norm),
            raw_row=dict(row),
        ))

    return entries


def parse_binance_1099da(csv_path: str | Path) -> list[Form1099DAEntry]:
    """
    Parse a Binance.US 1099-DA CSV export.

    Expected columns:
      Asset, Date Acquired, Date Sold, Gross Proceeds,
      Cost Basis, Gain/Loss, Covered
    """
    content = Path(csv_path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    entries: list[Form1099DAEntry] = []
    for row in reader:
        norm = {k.strip().lower(): v for k, v in row.items()}

        asset = _normalize_asset(norm.get("asset", ""))
        if not asset:
            continue

        entries.append(Form1099DAEntry(
            asset=asset,
            date_acquired=_parse_date(
                norm.get("date acquired", "")
            ),
            date_sold=_parse_date_required(
                norm.get("date sold", "")
            ),
            proceeds=_parse_decimal_required(
                norm.get("gross proceeds", "")
                or norm.get("proceeds", "")
            ),
            cost_basis=_parse_decimal(
                norm.get("cost basis", "")
            ),
            gain_loss=_parse_decimal(
                norm.get("gain/loss", "")
                or norm.get("gain or loss", "")
            ),
            broker_name="Binance.US",
            is_covered=_detect_covered(norm),
            raw_row=dict(row),
        ))

    return entries


def parse_generic_1099da(
    csv_path: str | Path,
    column_mapping: dict[str, str],
) -> list[Form1099DAEntry]:
    """
    Parse a generic 1099-DA CSV with user-provided column mapping.

    column_mapping maps our field names to the actual CSV column names:
      {
        "asset": "Token Name",
        "date_acquired": "Purchase Date",
        "date_sold": "Sale Date",
        "proceeds": "Sale Proceeds",
        "cost_basis": "Cost Basis",      # optional
        "gain_loss": "Gain/Loss",         # optional
        "covered": "Covered Security",    # optional
      }

    At minimum, "asset", "date_sold", and "proceeds" must be provided.
    """
    required = {"asset", "date_sold", "proceeds"}
    missing = required - set(column_mapping.keys())
    if missing:
        raise ValueError(f"column_mapping missing required keys: {missing}")

    content = Path(csv_path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    broker_name = column_mapping.get("broker_name", "Unknown Broker")

    entries: list[Form1099DAEntry] = []
    for row in reader:
        asset_col = column_mapping["asset"]
        asset = _normalize_asset(row.get(asset_col, ""))
        if not asset:
            continue

        date_sold_col = column_mapping["date_sold"]
        date_acquired_col = column_mapping.get("date_acquired")
        proceeds_col = column_mapping["proceeds"]
        cost_basis_col = column_mapping.get("cost_basis")
        gain_loss_col = column_mapping.get("gain_loss")
        covered_col = column_mapping.get("covered")

        entries.append(Form1099DAEntry(
            asset=asset,
            date_acquired=_parse_date(row.get(date_acquired_col, "")) if date_acquired_col else None,
            date_sold=_parse_date_required(row.get(date_sold_col, "")),
            proceeds=_parse_decimal_required(row.get(proceeds_col, "")),
            cost_basis=_parse_decimal(row.get(cost_basis_col, "")) if cost_basis_col else None,
            gain_loss=_parse_decimal(row.get(gain_loss_col, "")) if gain_loss_col else None,
            broker_name=broker_name,
            is_covered=row.get(covered_col, "").strip().lower() in ("yes", "true", "1", "covered", "y") if covered_col else False,
            raw_row=dict(row),
        ))

    return entries


def parse_1099da_auto(csv_path: str | Path) -> list[Form1099DAEntry]:
    """
    Auto-detect the exchange format from CSV headers and parse accordingly.

    Falls back to a best-effort generic parse if format is unrecognized.
    """
    content = Path(csv_path).read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    headers = set(reader.fieldnames or [])

    fmt = detect_format(headers)

    parser_map = {
        "coinbase": parse_coinbase_1099da,
        "kraken": parse_kraken_1099da,
        "binance": parse_binance_1099da,
    }

    if fmt in parser_map:
        return parser_map[fmt](csv_path)

    # Generic fallback: try common column name patterns
    lower_headers = {h.strip().lower(): h for h in headers}

    # Build a best-effort mapping
    mapping: dict[str, str] = {}

    # Asset
    for candidate in ("asset", "asset name", "token", "currency", "symbol"):
        if candidate in lower_headers:
            mapping["asset"] = lower_headers[candidate]
            break

    # Date sold
    for candidate in ("date sold", "date sold or disposed", "date of sale",
                       "sale date", "disposal date"):
        if candidate in lower_headers:
            mapping["date_sold"] = lower_headers[candidate]
            break

    # Proceeds
    for candidate in ("proceeds", "gross proceeds", "sale proceeds", "total proceeds"):
        if candidate in lower_headers:
            mapping["proceeds"] = lower_headers[candidate]
            break

    # Date acquired (optional)
    for candidate in ("date acquired", "acquisition date", "purchase date", "date purchased"):
        if candidate in lower_headers:
            mapping["date_acquired"] = lower_headers[candidate]
            break

    # Cost basis (optional)
    for candidate in ("cost basis", "cost", "basis"):
        if candidate in lower_headers:
            mapping["cost_basis"] = lower_headers[candidate]
            break

    # Gain/loss (optional)
    for candidate in ("gain/loss", "gain or loss", "gain_loss", "realized gain/loss"):
        if candidate in lower_headers:
            mapping["gain_loss"] = lower_headers[candidate]
            break

    # Covered (optional)
    for candidate in ("covered", "is_covered", "security_type"):
        if candidate in lower_headers:
            mapping["covered"] = lower_headers[candidate]
            break

    required_found = {"asset", "date_sold", "proceeds"}
    if not required_found.issubset(set(mapping.keys())):
        raise ValueError(
            f"Could not auto-detect required columns. Found: {list(headers)}. "
            f"Mapped: {mapping}. Missing: {required_found - set(mapping.keys())}"
        )

    mapping["broker_name"] = "Unknown Broker"
    return parse_generic_1099da(csv_path, mapping)
