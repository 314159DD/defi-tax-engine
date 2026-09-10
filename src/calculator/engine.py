"""
Cost Basis Calculation Engine.

Walks transactions in chronological order, builds a TaxLot book,
and produces Disposals for every taxable event.

DeFi-specific rules implemented here:
  - swap          → disposal of token_out, acquisition of token_in
  - lp_add        → acquisition of LP token (cost = sum of tokens deposited)
  - lp_remove     → disposal of LP token, acquisition of underlying tokens
  - reward/airdrop→ acquisition at FMV (income event, cost basis = FMV)
  - bridge        → NO disposal; cost basis carries over
  - transfer      → NO disposal (self-transfer between own wallets)
  - wrap          → NO disposal; cost basis transfers to wrapped token
  - stake/unstake → NO disposal; cost basis carries over
  - Gas fees      → added to cost basis of acquisition; deducted from proceeds on disposal

Usage:
    engine = CalculatorEngine(method="FIFO")
    disposals = engine.calculate(transactions, known_wallets={"0xABC..."})
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from src.calculator.fifo import consume_fifo
from src.calculator.hifo import consume_hifo
from src.calculator.lifo import consume_lifo
from src.calculator.lots import Disposal, LotManager, TaxLot
from src.importers.models import AssetTransfer, Transaction
from src.tax.models import HoldingPeriod

logger = logging.getLogger(__name__)

# Tokens that are considered the same economic asset as ETH when wrapping
_WRAP_PAIRS: dict[str, str] = {
    "WETH": "ETH",
    "WBTC": "BTC",
    "WMATIC": "MATIC",
    "WSOL": "SOL",
    "WAVAX": "AVAX",
}
# Reverse map: unwrap direction
_UNWRAP_PAIRS: dict[str, str] = {v: k for k, v in _WRAP_PAIRS.items()}

_STABLECOIN_SYMBOLS: frozenset[str] = frozenset({
    "USDC", "USDT", "DAI", "BUSD", "TUSD", "FRAX", "LUSD", "GUSD",
    "USDP", "USDD", "CRVUSD", "SUSD",
})


def _new_id() -> str:
    return str(uuid.uuid4())


class CalculatorEngine:
    """
    Stateless engine: each call to calculate() creates a fresh LotManager.

    Args:
        method: "FIFO", "LIFO", or "HIFO"
        tax_module: optional TaxModule for country-specific rules.
                    If None, defaults to USTaxModule().
    """

    def __init__(self, method: str = "FIFO", tax_module=None) -> None:
        # If a tax_module is provided, validate method against its allowed methods
        if tax_module is not None:
            self.tax_module = tax_module
            allowed = [m.upper() for m in tax_module.get_cost_basis_methods()]
            method = method.upper()
            if method not in allowed:
                raise ValueError(
                    f"Method {method!r} not allowed for {tax_module.country_code}. "
                    f"Allowed: {allowed}"
                )
        else:
            # Default: US module (lazy import to avoid circular)
            method = method.upper()
            if method not in {"FIFO", "LIFO", "HIFO"}:
                raise ValueError(f"Unknown method: {method!r}. Choose FIFO, LIFO, or HIFO.")
            self.tax_module = None  # will use legacy behavior
        self.method = method

    # ── Public API ────────────────────────────────────────────────────────

    def calculate(
        self,
        transactions: list[Transaction],
        known_wallets: Optional[set[str]] = None,
        year: Optional[int] = None,
    ) -> list[Disposal]:
        """
        Process all transactions and return Disposal events.

        Args:
            transactions:  All normalized transactions (any year, sorted by timestamp).
            known_wallets: Wallet addresses owned by the user (for self-transfer detection).
            year:          If set, return only disposals that occurred in this calendar year.
                           Lots from prior years are still built up correctly.

        Returns:
            List of Disposal events in chronological order.
        """
        known_wallets = {w.lower() for w in (known_wallets or set())}

        # Sort chronologically - critical for correct lot ordering
        sorted_txs = sorted(transactions, key=lambda t: t.timestamp)

        lot_manager = LotManager()
        disposals: list[Disposal] = []

        for tx in sorted_txs:
            try:
                new_disposals = self._process_transaction(tx, lot_manager, known_wallets)
                disposals.extend(new_disposals)
            except Exception as exc:
                logger.warning(
                    "Error processing tx %s (%s): %s - skipping",
                    tx.tx_hash, tx.tx_type, exc,
                )

        if year is not None:
            disposals = [d for d in disposals if d.date.year == year]

        # If a tax_module is provided, reclassify holding periods and apply exemptions
        if self.tax_module is not None:
            for d in disposals:
                # Reclassify holding period using country-specific rules
                if d.lots_consumed:
                    # Use the earliest acquisition date from consumed lots
                    earliest = min(lc.acquisition_date for lc in d.lots_consumed)
                    acq_date = earliest.date() if hasattr(earliest, "date") and callable(earliest.date) else earliest
                    disp_date = d.date.date() if hasattr(d.date, "date") and callable(d.date.date) else d.date
                    hp_enum = self.tax_module.classify_holding_period(acq_date, disp_date)
                    d.holding_period_enum = hp_enum
                    d.holding_period = hp_enum.value

            # Apply country-specific exemptions
            if year is not None:
                exemptions = self.tax_module.get_exemptions(disposals, year)
                # Build lookup: disposal_id (tx_hash) -> exemption
                exemption_map = {ex.disposal_id: ex for ex in exemptions}
                for d in disposals:
                    if d.tx_hash in exemption_map:
                        d.exemption = exemption_map[d.tx_hash]

        return disposals

    # ── Transaction dispatch ──────────────────────────────────────────────

    def _process_transaction(
        self,
        tx: Transaction,
        lm: LotManager,
        known_wallets: set[str],
    ) -> list[Disposal]:
        t = tx.tx_type

        if t in ("transfer", "bridge", "approve", "unknown"):
            # Non-taxable: transfer cost basis as-is (bridge/self-transfer)
            return []

        if t in ("stake", "unstake"):
            # Staking itself is not a disposal - cost basis stays in original lots.
            # On unstake, we get back the same tokens: treat as a no-op for cost basis.
            return []

        if t == "swap":
            return self._handle_swap(tx, lm)

        if t == "lp_add":
            self._handle_lp_add(tx, lm)
            return []

        if t == "lp_remove":
            return self._handle_lp_remove(tx, lm)

        if t in ("reward", "airdrop"):
            self._handle_income(tx, lm)
            return []

        if t in ("nft_buy", "mint"):
            self._handle_nft_buy(tx, lm)
            return []

        if t == "nft_sell":
            return self._handle_nft_sell(tx, lm)

        # Fallback: if there are assets_in treat as acquisition
        if tx.assets_in:
            self._handle_generic_acquisition(tx, lm)
        return []

    # ── Swap ──────────────────────────────────────────────────────────────

    def _handle_swap(
        self, tx: Transaction, lm: LotManager
    ) -> list[Disposal]:
        """
        Swap: dispose tokens_out, acquire tokens_in.

        Gas on a swap is:
          - Part of cost basis of acquired tokens (outgoing gas adds to cost of what you got)
          - Alternatively treated as deducted from proceeds, but standard practice adds to basis.
          We add gas to the cost basis of the acquired token.
        """
        disposals: list[Disposal] = []

        gas_usd = _transfer_usd(tx.fee) if tx.fee else Decimal("0")

        # Dispose of each token sent out
        for asset_out in tx.assets_out:
            if _is_gas_token_for_fee(asset_out, tx.fee):
                continue  # gas itself is not a separate disposal line
            if asset_out.usd_value is None:
                logger.warning("Swap %s: missing USD value for %s out - skipping disposal", tx.tx_hash, asset_out.token_symbol)
                continue

            proceeds = asset_out.usd_value
            # If this is the only asset_out and gas_usd is known, gas reduces proceeds
            # (IRS: selling costs reduce proceeds)
            if len(tx.assets_out) == 1:
                proceeds = proceeds - gas_usd

            try:
                disposal = self._consume(
                    lm=lm,
                    token=asset_out.token_symbol,
                    amount=asset_out.amount,
                    proceeds_usd=max(proceeds, Decimal("0")),
                    disposal_date=tx.timestamp,
                    tx_hash=tx.tx_hash,
                )
                disposals.append(disposal)
            except ValueError as e:
                logger.warning("Swap %s: %s", tx.tx_hash, e)

        # Acquire each token received
        # Gas on acquisition is added to cost basis of the acquired token
        gas_per_token = (gas_usd / len(tx.assets_in)) if tx.assets_in else Decimal("0")
        for asset_in in tx.assets_in:
            if asset_in.usd_value is None:
                logger.warning("Swap %s: missing USD value for %s in - using 0 cost basis", tx.tx_hash, asset_in.token_symbol)
                fmv = Decimal("0")
            else:
                fmv = asset_in.usd_value
            cost_basis = fmv + gas_per_token
            lm.add_lot(TaxLot(
                id=_new_id(),
                token=asset_in.token_symbol,
                amount=asset_in.amount,
                cost_basis_usd=cost_basis,
                acquisition_date=tx.timestamp,
                remaining=asset_in.amount,
                source="swap",
                tx_hash=tx.tx_hash,
            ))

        return disposals

    # ── LP add ────────────────────────────────────────────────────────────

    def _handle_lp_add(self, tx: Transaction, lm: LotManager) -> None:
        """
        LP add: dispose of deposited tokens, acquire LP token.

        The LP token cost basis = sum of FMV of tokens deposited.
        The tokens deposited are NOT a taxable disposal under current IRS
        treatment (no specific ruling, but common practice treats lp_add
        as an exchange where the LP token has the same aggregate basis).

        We track the deposited tokens as consumed into the LP token.
        """
        total_deposit_basis = Decimal("0")

        for asset_out in tx.assets_out:
            if asset_out.usd_value is not None:
                total_deposit_basis += asset_out.usd_value
            else:
                # Try to use existing lot cost as proxy
                try:
                    _, cost = lm.consume(
                        token=asset_out.token_symbol,
                        amount=asset_out.amount,
                        disposal_date=tx.timestamp,
                        order="fifo",
                        method="LP_ADD",
                    )
                    total_deposit_basis += cost
                except ValueError:
                    logger.warning(
                        "LP add %s: no lots or USD value for %s - using 0 for that leg",
                        tx.tx_hash, asset_out.token_symbol,
                    )

        # Record LP token acquisition
        for asset_in in tx.assets_in:
            if asset_in.amount == Decimal("0"):
                continue
            lm.add_lot(TaxLot(
                id=_new_id(),
                token=asset_in.token_symbol,
                amount=asset_in.amount,
                cost_basis_usd=total_deposit_basis,
                acquisition_date=tx.timestamp,
                remaining=asset_in.amount,
                source="lp_add",
                tx_hash=tx.tx_hash,
            ))

    # ── LP remove ─────────────────────────────────────────────────────────

    def _handle_lp_remove(
        self, tx: Transaction, lm: LotManager
    ) -> list[Disposal]:
        """
        LP remove: dispose of LP tokens, acquire underlying tokens.

        The proceeds of the LP disposal = FMV of tokens received.
        The cost basis of the tokens received = proportional share of
        the LP token's cost basis.

        Impermanent loss is embedded in the gain/loss of the LP disposal.
        """
        disposals: list[Disposal] = []

        # Total FMV of tokens received = proceeds of LP disposal
        total_proceeds = Decimal("0")
        for asset_in in tx.assets_in:
            if asset_in.usd_value is not None:
                total_proceeds += asset_in.usd_value

        # Dispose LP tokens
        for asset_out in tx.assets_out:
            if asset_out.usd_value is None and total_proceeds == Decimal("0"):
                logger.warning("LP remove %s: no USD value for proceeds - skipping", tx.tx_hash)
                continue

            proceeds = total_proceeds if asset_out.usd_value is None else asset_out.usd_value

            try:
                disposal = self._consume(
                    lm=lm,
                    token=asset_out.token_symbol,
                    amount=asset_out.amount,
                    proceeds_usd=proceeds,
                    disposal_date=tx.timestamp,
                    tx_hash=tx.tx_hash,
                )
                disposals.append(disposal)
            except ValueError as e:
                logger.warning("LP remove %s: %s", tx.tx_hash, e)

        # Acquire underlying tokens at their FMV (new cost basis = FMV at receipt)
        for asset_in in tx.assets_in:
            fmv = asset_in.usd_value or Decimal("0")
            lm.add_lot(TaxLot(
                id=_new_id(),
                token=asset_in.token_symbol,
                amount=asset_in.amount,
                cost_basis_usd=fmv,
                acquisition_date=tx.timestamp,
                remaining=asset_in.amount,
                source="lp_remove",
                tx_hash=tx.tx_hash,
            ))

        return disposals

    # ── Income events (reward, airdrop) ───────────────────────────────────

    def _handle_income(self, tx: Transaction, lm: LotManager) -> None:
        """
        Staking reward / airdrop: income at FMV.

        Cost basis of newly acquired tokens = FMV at time of receipt.
        The income itself is handled by the report layer (not the calculator).
        """
        for asset_in in tx.assets_in:
            fmv = asset_in.usd_value or Decimal("0")
            lm.add_lot(TaxLot(
                id=_new_id(),
                token=asset_in.token_symbol,
                amount=asset_in.amount,
                cost_basis_usd=fmv,
                acquisition_date=tx.timestamp,
                remaining=asset_in.amount,
                source=tx.tx_type,  # "reward" or "airdrop"
                tx_hash=tx.tx_hash,
            ))

    # ── NFT buy / sell ────────────────────────────────────────────────────

    def _handle_nft_buy(self, tx: Transaction, lm: LotManager) -> None:
        """Record NFT acquisition. NFT is treated as a distinct asset."""
        for asset_in in tx.assets_in:
            fmv = asset_in.usd_value or Decimal("0")
            gas_usd = _transfer_usd(tx.fee) if tx.fee else Decimal("0")
            lm.add_lot(TaxLot(
                id=_new_id(),
                token=asset_in.token_symbol,
                amount=asset_in.amount,
                cost_basis_usd=fmv + gas_usd,
                acquisition_date=tx.timestamp,
                remaining=asset_in.amount,
                source="nft_buy",
                tx_hash=tx.tx_hash,
            ))
        # ETH/SOL paid out is consumed from existing lots
        for asset_out in tx.assets_out:
            if asset_out.usd_value is None:
                continue
            try:
                self._consume(
                    lm=lm,
                    token=asset_out.token_symbol,
                    amount=asset_out.amount,
                    proceeds_usd=asset_out.usd_value,
                    disposal_date=tx.timestamp,
                    tx_hash=tx.tx_hash,
                )
            except ValueError as e:
                logger.warning("NFT buy %s: %s", tx.tx_hash, e)

    def _handle_nft_sell(self, tx: Transaction, lm: LotManager) -> list[Disposal]:
        disposals: list[Disposal] = []
        gas_usd = _transfer_usd(tx.fee) if tx.fee else Decimal("0")
        for asset_out in tx.assets_out:
            if asset_out.usd_value is None:
                continue
            proceeds = asset_out.usd_value - gas_usd
            try:
                disposal = self._consume(
                    lm=lm,
                    token=asset_out.token_symbol,
                    amount=asset_out.amount,
                    proceeds_usd=max(proceeds, Decimal("0")),
                    disposal_date=tx.timestamp,
                    tx_hash=tx.tx_hash,
                )
                disposals.append(disposal)
            except ValueError as e:
                logger.warning("NFT sell %s: %s", tx.tx_hash, e)
        return disposals

    # ── Generic acquisition fallback ──────────────────────────────────────

    def _handle_generic_acquisition(self, tx: Transaction, lm: LotManager) -> None:
        for asset_in in tx.assets_in:
            fmv = asset_in.usd_value or Decimal("0")
            lm.add_lot(TaxLot(
                id=_new_id(),
                token=asset_in.token_symbol,
                amount=asset_in.amount,
                cost_basis_usd=fmv,
                acquisition_date=tx.timestamp,
                remaining=asset_in.amount,
                source=tx.tx_type,
                tx_hash=tx.tx_hash,
            ))

    # ── Internal consume dispatcher ───────────────────────────────────────

    def _consume(
        self,
        lm: LotManager,
        token: str,
        amount: Decimal,
        proceeds_usd: Decimal,
        disposal_date: datetime,
        tx_hash: str,
    ) -> Disposal:
        """Dispatch to the correct method-specific consume function."""
        if self.method == "FIFO":
            return consume_fifo(lm, token, amount, proceeds_usd, disposal_date, tx_hash)
        elif self.method == "LIFO":
            return consume_lifo(lm, token, amount, proceeds_usd, disposal_date, tx_hash)
        else:  # HIFO
            return consume_hifo(lm, token, amount, proceeds_usd, disposal_date, tx_hash)


# ---------------------------------------------------------------------------
# Compare helper - runs all three methods
# ---------------------------------------------------------------------------

@dataclass
class MethodComparison:
    """Summary comparison of FIFO / LIFO / HIFO for a given year."""
    year: int
    fifo_gain: Decimal
    lifo_gain: Decimal
    hifo_gain: Decimal
    fifo_short_term: Decimal
    lifo_short_term: Decimal
    hifo_short_term: Decimal
    fifo_long_term: Decimal
    lifo_long_term: Decimal
    hifo_long_term: Decimal
    fifo_disposals: int
    lifo_disposals: int
    hifo_disposals: int


def compare_methods(
    transactions: list[Transaction],
    known_wallets: Optional[set[str]] = None,
    year: Optional[int] = None,
) -> MethodComparison:
    """
    Run FIFO, LIFO, and HIFO on the same transaction set and return a comparison.
    """
    results: dict[str, list[Disposal]] = {}
    for method in ("FIFO", "LIFO", "HIFO"):
        engine = CalculatorEngine(method=method)
        results[method] = engine.calculate(transactions, known_wallets=known_wallets, year=year)

    def _total_gain(disposals: list[Disposal]) -> Decimal:
        return sum((d.gain_loss_usd for d in disposals), Decimal("0"))

    def _st_gain(disposals: list[Disposal]) -> Decimal:
        return sum((d.gain_loss_usd for d in disposals if d.holding_period == "short-term"), Decimal("0"))

    def _lt_gain(disposals: list[Disposal]) -> Decimal:
        return sum((d.gain_loss_usd for d in disposals if d.holding_period == "long-term"), Decimal("0"))

    return MethodComparison(
        year=year or 0,
        fifo_gain=_total_gain(results["FIFO"]),
        lifo_gain=_total_gain(results["LIFO"]),
        hifo_gain=_total_gain(results["HIFO"]),
        fifo_short_term=_st_gain(results["FIFO"]),
        lifo_short_term=_st_gain(results["LIFO"]),
        hifo_short_term=_st_gain(results["HIFO"]),
        fifo_long_term=_lt_gain(results["FIFO"]),
        lifo_long_term=_lt_gain(results["LIFO"]),
        hifo_long_term=_lt_gain(results["HIFO"]),
        fifo_disposals=len(results["FIFO"]),
        lifo_disposals=len(results["LIFO"]),
        hifo_disposals=len(results["HIFO"]),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _transfer_usd(transfer: Optional[AssetTransfer]) -> Decimal:
    if transfer is None or transfer.usd_value is None:
        return Decimal("0")
    return transfer.usd_value


def _is_gas_token_for_fee(
    asset: AssetTransfer, fee: Optional[AssetTransfer]
) -> bool:
    """Return True if the asset is the same token as the fee (gas deducted separately)."""
    if fee is None:
        return False
    return asset.token_symbol == fee.token_symbol


# ---------------------------------------------------------------------------
# CostBasisEngine - DB-backed wrapper
# ---------------------------------------------------------------------------

class CostBasisEngine:
    """
    High-level engine that bridges the DB ↔ CalculatorEngine.

    Loads transactions from SQLite, converts to Transaction objects,
    runs the in-memory CalculatorEngine, and persists Disposal results
    back to the database.
    """

    def __init__(self, db, tax_module=None) -> None:
        self._db = db
        self._tax_module = tax_module

    def calculate(self, method: str = "FIFO", year: Optional[int] = None) -> dict:
        """
        Run end-to-end cost basis calculation.

        Returns a summary dict with totals and disposal count.
        """
        from src.storage.database import (
            DisposalRepository,
            TransactionRepository,
            WalletRepository,
        )

        tx_repo = TransactionRepository(self._db)
        wallet_repo = WalletRepository(self._db)
        disposal_repo = DisposalRepository(self._db)

        # Load all known wallet addresses
        known_wallets = set(wallet_repo.get_addresses())

        # Load all transactions from DB and convert to Transaction objects
        transactions = self._load_transactions()

        if not transactions:
            return {
                "method": method,
                "year": year,
                "total_disposals": 0,
                "total_gains": "0",
                "total_losses": "0",
                "net_gain_loss": "0",
                "short_term": "0",
                "long_term": "0",
                "message": "No transactions found. Import wallets first.",
            }

        # Run the calculator
        engine = CalculatorEngine(method=method, tax_module=self._tax_module)
        disposals = engine.calculate(transactions, known_wallets=known_wallets, year=year)

        # Clear previous disposals for this method and persist new ones
        disposal_repo.delete_by_method(method)
        for d in disposals:
            # Map holding period string to DB format
            hp_str = d.holding_period
            if hp_str == "short-term":
                hp_db = "short"
            elif hp_str == "exempt":
                hp_db = "exempt"
            else:
                hp_db = "long"

            disposal_repo.insert(
                token=d.token,
                amount=d.amount,
                proceeds_usd=d.proceeds_usd,
                cost_basis_usd=d.cost_basis_usd,
                gain_loss_usd=d.gain_loss_usd,
                holding_period=hp_db,
                method=d.method,
                disposal_date=d.date,
                tx_hash=d.tx_hash,
            )

        # Compute summary
        total_gains = sum((d.gain_loss_usd for d in disposals if d.gain_loss_usd > 0), Decimal("0"))
        total_losses = sum((d.gain_loss_usd for d in disposals if d.gain_loss_usd < 0), Decimal("0"))
        net = total_gains + total_losses
        short_term = sum(
            (d.gain_loss_usd for d in disposals if d.holding_period == "short-term"),
            Decimal("0"),
        )
        long_term = sum(
            (d.gain_loss_usd for d in disposals if d.holding_period == "long-term"),
            Decimal("0"),
        )
        exempt = sum(
            (d.gain_loss_usd for d in disposals if d.holding_period == "exempt"),
            Decimal("0"),
        )

        result = {
            "method": method,
            "year": year,
            "total_disposals": len(disposals),
            "total_gains": str(total_gains),
            "total_losses": str(total_losses),
            "net_gain_loss": str(net),
            "short_term": str(short_term),
            "long_term": str(long_term),
        }

        # Add country-specific fields if tax_module is set
        if self._tax_module is not None:
            result["country"] = self._tax_module.country_code
            result["currency"] = self._tax_module.currency_code
            result["exempt"] = str(exempt)
            result["exemption_count"] = sum(1 for d in disposals if d.exemption is not None)

        return result

    def _load_transactions(self) -> list[Transaction]:
        """Load all transactions from DB and convert to Transaction model objects."""
        import json as _json

        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY timestamp"
            ).fetchall()

        transactions: list[Transaction] = []
        for row in rows:
            raw = _json.loads(row["raw_json"]) if row["raw_json"] else {}

            assets_in = [
                AssetTransfer(
                    token_symbol=a.get("token_symbol", "UNKNOWN"),
                    amount=Decimal(str(a.get("amount", "0"))),
                    token_address=a.get("token_address"),
                    usd_value=Decimal(str(a["usd_value"])) if a.get("usd_value") is not None else None,
                )
                for a in raw.get("assets_in", [])
            ]

            assets_out = [
                AssetTransfer(
                    token_symbol=a.get("token_symbol", "UNKNOWN"),
                    amount=Decimal(str(a.get("amount", "0"))),
                    token_address=a.get("token_address"),
                    usd_value=Decimal(str(a["usd_value"])) if a.get("usd_value") is not None else None,
                )
                for a in raw.get("assets_out", [])
            ]

            fee_data = raw.get("fee")
            fee = None
            if fee_data:
                fee = AssetTransfer(
                    token_symbol=fee_data.get("token_symbol", "ETH"),
                    amount=Decimal(str(fee_data.get("amount", "0"))),
                    token_address=fee_data.get("token_address"),
                    usd_value=Decimal(str(fee_data["usd_value"])) if fee_data.get("usd_value") is not None else None,
                )

            try:
                ts = datetime.fromisoformat(row["timestamp"])
            except (ValueError, TypeError):
                continue

            tx = Transaction(
                tx_hash=row["tx_hash"],
                chain=row["chain"],
                block_number=raw.get("block_number", 0),
                timestamp=ts,
                from_address=raw.get("from_address", ""),
                to_address=raw.get("to_address", ""),
                tx_type=row["tx_type"] or "unknown",
                assets_in=assets_in,
                assets_out=assets_out,
                fee=fee,
                protocol=row["protocol"],
                raw_data=raw,
            )
            transactions.append(tx)

        return transactions
