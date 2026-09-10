"""
Calculate CLI entry point.

Usage:
    python -m src.calculate --wallets wallets.json --method FIFO --year 2025
    python -m src.calculate compare --wallets wallets.json --year 2025
"""
from __future__ import annotations

import asyncio
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

import click

from src.calculator.engine import CalculatorEngine, MethodComparison, compare_methods
from src.calculator.lots import Disposal
from src.categorizer.engine import CategorizerEngine
from src.importers.evm import EVMImporter
from src.importers.models import Transaction
from src.importers.price import PriceService
from src.importers.solana import SolanaImporter
from src.storage.database import (
    Database,
    DisposalRepository,
    TaxLotRepository,
    WalletRepository,
)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--wallets", "wallets_file", required=True, type=click.Path(exists=True),
              help="JSON file: [{address, chain, label?}]")
@click.option("--method", default="FIFO",
              type=click.Choice(["FIFO", "LIFO", "HIFO"], case_sensitive=False),
              show_default=True, help="Cost basis method")
@click.option("--year", default=None, type=int, help="Tax year to report (default: all years)")
@click.option("--no-import", is_flag=True, default=False,
              help="Skip chain import - use only data already in the local DB")
def cli(ctx: click.Context, wallets_file: str, method: str, year: Optional[int], no_import: bool) -> None:
    """Calculate cost basis and capital gains for all wallets."""
    if ctx.invoked_subcommand == "compare":
        # compare subcommand will handle everything
        return

    method = method.upper()
    wallets_data = _load_wallets(wallets_file)

    click.echo(f"Method: {method}  |  Year: {year or 'all'}  |  Wallets: {len(wallets_data)}")

    async def _run() -> None:
        db = Database()
        known_wallets = {w["address"].lower() for w in wallets_data}

        transactions = await _get_transactions(db, wallets_data, known_wallets, no_import)
        click.echo(f"Transactions loaded: {len(transactions)}")

        disposals = _calculate(transactions, known_wallets, method, year)
        _save_disposals(db, disposals, method)
        _print_summary(disposals, method, year)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# compare subcommand
# ---------------------------------------------------------------------------

@cli.command("compare")
@click.option("--wallets", "wallets_file", required=True, type=click.Path(exists=True),
              help="JSON file: [{address, chain, label?}]")
@click.option("--year", default=None, type=int, help="Tax year to compare (default: all years)")
@click.option("--no-import", is_flag=True, default=False,
              help="Skip chain import - use only data already in the local DB")
def compare(wallets_file: str, year: Optional[int], no_import: bool) -> None:
    """Run FIFO, LIFO, and HIFO side-by-side and show which saves the most tax."""
    wallets_data = _load_wallets(wallets_file)

    click.echo(f"Comparing FIFO / LIFO / HIFO  |  Year: {year or 'all'}  |  Wallets: {len(wallets_data)}")

    async def _run() -> None:
        db = Database()
        known_wallets = {w["address"].lower() for w in wallets_data}

        transactions = await _get_transactions(db, wallets_data, known_wallets, no_import)
        click.echo(f"Transactions loaded: {len(transactions)}\n")

        result = compare_methods(transactions, known_wallets=known_wallets, year=year)
        _print_comparison(result)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Pipeline helpers
# ---------------------------------------------------------------------------

async def _get_transactions(
    db: Database,
    wallets_data: list[dict],
    known_wallets: set[str],
    no_import: bool,
) -> list[Transaction]:
    """
    Import transactions from the chain (unless --no-import) and return
    a categorized list of Transaction objects.
    """
    if no_import:
        # Read wallet records from DB and reload via raw_data is not practical;
        # instead we return an empty list and warn.
        # Full "load from DB" support requires a serialization layer (future sprint).
        click.echo(
            "Warning: --no-import mode re-uses the last in-memory import.\n"
            "For offline calculation from DB, run `python -m src.import all` first,\n"
            "then omit --no-import to re-fetch and categorize.\n"
            "Exiting - no transactions available for offline-only mode yet.",
            err=True,
        )
        return []

    price_service = PriceService()
    wallet_repo = WalletRepository(db)
    all_transactions: list[Transaction] = []

    for w in wallets_data:
        addr = w["address"]
        chain = w.get("chain", "ethereum").lower()
        label = w.get("label", "")
        wallet_repo.add(addr, chain, label)

        click.echo(f"  Importing [{chain}] {addr} ({label or 'no label'})...")
        try:
            if chain == "solana":
                importer = SolanaImporter()
                txs = await importer.fetch_all(addr, wallet_addresses=known_wallets)
            else:
                importer = EVMImporter(chain)
                txs = await importer.fetch_all(addr, wallet_addresses=known_wallets)
            click.echo(f"    → {len(txs)} transactions fetched")
            all_transactions.extend(txs)
        except Exception as exc:
            click.echo(f"    ERROR importing {addr}: {exc}", err=True)

    # Enrich missing USD prices
    if all_transactions:
        await _enrich_prices(price_service, all_transactions)

    # Categorize
    categorizer = CategorizerEngine(known_wallets=known_wallets)
    categorized = categorizer.categorize_all(all_transactions)

    return categorized


async def _enrich_prices(service: PriceService, transactions: list[Transaction]) -> None:
    """Fill in missing usd_value on all asset transfers."""
    pairs: list[tuple[str, object]] = []
    for tx in transactions:
        day = tx.timestamp.date()
        for transfer in [*tx.assets_in, *tx.assets_out]:
            if transfer.usd_value is None:
                pairs.append((transfer.token_symbol, day))
    if not pairs:
        return

    unique_pairs = list(set(pairs))
    click.echo(f"  Resolving {len(unique_pairs)} unique prices...")
    price_map = await service.get_prices_batch(unique_pairs)

    missing = 0
    for tx in transactions:
        day = tx.timestamp.date()
        for transfer in [*tx.assets_in, *tx.assets_out]:
            if transfer.usd_value is None:
                price = price_map.get((transfer.token_symbol, day))
                if price is not None:
                    transfer.usd_value = price * transfer.amount
                else:
                    missing += 1

    if missing:
        click.echo(f"  Warning: {missing} transfers have no USD price", err=True)


def _calculate(
    transactions: list[Transaction],
    known_wallets: set[str],
    method: str,
    year: Optional[int],
) -> list[Disposal]:
    engine = CalculatorEngine(method=method)
    return engine.calculate(transactions, known_wallets=known_wallets, year=year)


def _save_disposals(db: Database, disposals: list[Disposal], method: str) -> None:
    """Overwrite disposals for this method and save fresh results."""
    repo = DisposalRepository(db)
    deleted = repo.delete_by_method(method)
    if deleted:
        click.echo(f"  Cleared {deleted} previous {method} disposals")

    for d in disposals:
        repo.insert(
            token=d.token,
            amount=d.amount,
            proceeds_usd=d.proceeds_usd,
            cost_basis_usd=d.cost_basis_usd,
            gain_loss_usd=d.gain_loss_usd,
            holding_period=d.holding_period,
            method=d.method,
            disposal_date=d.date,
            tx_hash=d.tx_hash,
        )
    click.echo(f"  Saved {len(disposals)} {method} disposals to DB")


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _fmt(amount: Decimal) -> str:
    """Format a Decimal as a USD amount with sign and commas."""
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def _print_summary(disposals: list[Disposal], method: str, year: Optional[int]) -> None:
    if not disposals:
        click.echo(f"\nNo disposals found for {method}" + (f" in {year}" if year else "") + ".")
        return

    total_gain = sum((d.gain_loss_usd for d in disposals), Decimal("0"))
    st_gain = sum((d.gain_loss_usd for d in disposals if d.holding_period == "short-term"), Decimal("0"))
    lt_gain = sum((d.gain_loss_usd for d in disposals if d.holding_period == "long-term"), Decimal("0"))
    total_proceeds = sum((d.proceeds_usd for d in disposals), Decimal("0"))
    total_basis = sum((d.cost_basis_usd for d in disposals), Decimal("0"))

    year_label = f" ({year})" if year else ""

    click.echo(f"\n{'─' * 52}")
    click.echo(f"  Cost Basis Report - {method}{year_label}")
    click.echo(f"{'─' * 52}")
    click.echo(f"  Disposals:        {len(disposals):>10,}")
    click.echo(f"  Total Proceeds:   {total_proceeds:>14,.2f} USD")
    click.echo(f"  Total Cost Basis: {total_basis:>14,.2f} USD")
    click.echo(f"{'─' * 52}")
    click.echo(f"  Short-term gain:  {_fmt(st_gain):>14}")
    click.echo(f"  Long-term gain:   {_fmt(lt_gain):>14}")
    click.echo(f"  NET GAIN/LOSS:    {_fmt(total_gain):>14}")
    click.echo(f"{'─' * 52}")


def _print_comparison(result: MethodComparison) -> None:
    year_label = f" ({result.year})" if result.year else ""
    click.echo(f"{'─' * 62}")
    click.echo(f"  Method Comparison{year_label}")
    click.echo(f"{'─' * 62}")
    click.echo(f"  {'':30s}  {'FIFO':>8}  {'LIFO':>8}  {'HIFO':>8}")
    click.echo(f"  {'─' * 58}")
    click.echo(
        f"  {'Short-term gain':30s}  "
        f"{_fmt(result.fifo_short_term):>8}  "
        f"{_fmt(result.lifo_short_term):>8}  "
        f"{_fmt(result.hifo_short_term):>8}"
    )
    click.echo(
        f"  {'Long-term gain':30s}  "
        f"{_fmt(result.fifo_long_term):>8}  "
        f"{_fmt(result.lifo_long_term):>8}  "
        f"{_fmt(result.hifo_long_term):>8}"
    )
    click.echo(f"  {'─' * 58}")
    click.echo(
        f"  {'NET GAIN / LOSS':30s}  "
        f"{_fmt(result.fifo_gain):>8}  "
        f"{_fmt(result.lifo_gain):>8}  "
        f"{_fmt(result.hifo_gain):>8}"
    )
    click.echo(f"  {'Disposals':30s}  {result.fifo_disposals:>8,}  {result.lifo_disposals:>8,}  {result.hifo_disposals:>8,}")
    click.echo(f"{'─' * 62}")

    # Highlight the best method (lowest total gain = least tax)
    best = min(
        [("FIFO", result.fifo_gain), ("LIFO", result.lifo_gain), ("HIFO", result.hifo_gain)],
        key=lambda x: x[1],
    )
    click.echo(f"\n  Best method for minimizing tax: {best[0]} ({_fmt(best[1])})")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_wallets(wallets_file: str) -> list[dict]:
    data = json.loads(Path(wallets_file).read_text())
    if isinstance(data, dict):
        data = data.get("wallets", [])
    if not data:
        click.echo("No wallets found in wallets.json", err=True)
        sys.exit(1)
    return data


if __name__ == "__main__":
    cli()
