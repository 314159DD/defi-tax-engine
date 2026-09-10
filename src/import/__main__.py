"""
Import CLI entry point.

Usage:
    python -m src.import wallet 0xABC... --chain ethereum
    python -m src.import wallet 5rEq... --chain solana
    python -m src.import csv coinbase_export.csv --format coinbase
    python -m src.import csv trades.csv --format binance
    python -m src.import all --wallets wallets.json
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

from src.importers.evm import EVMImporter
from src.importers.exchange import ExchangeImporter
from src.importers.models import Transaction
from src.importers.price import PriceService
from src.importers.solana import SolanaImporter
from src.storage.database import (
    Database,
    TransactionRepository,
    WalletRepository,
)


def _get_db() -> Database:
    return Database()


def _store_transactions(db: Database, wallet_address: str, chain: str, transactions: list[Transaction]) -> int:
    """Persist imported transactions and update wallet import timestamp."""
    tx_repo = TransactionRepository(db)
    wallet_repo = WalletRepository(db)

    rows = [
        {
            "tx_hash": tx.tx_hash,
            "chain": tx.chain,
            "timestamp": tx.timestamp,
            "tx_type": tx.tx_type,
            "protocol": tx.protocol,
            "raw_data": tx.raw_data,
        }
        for tx in transactions
    ]
    tx_repo.upsert_many(rows)
    wallet_repo.update_last_imported(wallet_address, chain)
    return len(rows)


@click.group()
def cli() -> None:
    """Crypto Tax - multi-chain transaction importer."""


# ── wallet ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("address")
@click.option("--chain", required=True, type=click.Choice(
    ["ethereum", "polygon", "arbitrum", "base", "optimism", "solana"],
    case_sensitive=False,
), help="Blockchain network")
@click.option("--start-block", default=0, show_default=True, help="Starting block (EVM only, for incremental import)")
@click.option("--label", default=None, help="Human-readable label for this wallet")
@click.option("--no-prices", is_flag=True, default=False, help="Skip historical price enrichment")
def wallet(address: str, chain: str, start_block: int, label: str | None, no_prices: bool) -> None:
    """Import all transactions for a single wallet address."""
    chain = chain.lower()
    db = _get_db()
    wallet_repo = WalletRepository(db)
    wallet_repo.add(address, chain, label)

    click.echo(f"Importing {chain} wallet: {address}")

    async def _run() -> None:
        if chain == "solana":
            importer = SolanaImporter()
            transactions = await importer.fetch_all(address)
        else:
            importer = EVMImporter(chain)
            transactions = await importer.fetch_all(address, start_block=start_block)

        click.echo(f"  Fetched {len(transactions)} transactions")

        if not no_prices and transactions:
            await _enrich_prices(transactions)

        count = _store_transactions(db, address, chain, transactions)
        click.echo(f"  Stored {count} transactions for {address} ({chain})")

    asyncio.run(_run())


# ── csv ───────────────────────────────────────────────────────────────────────

@cli.command("csv")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--format", "fmt", required=True,
              type=click.Choice(["coinbase", "binance", "kraken", "generic"], case_sensitive=False),
              help="CSV export format")
@click.option("--no-prices", is_flag=True, default=False, help="Skip historical price enrichment")
def import_csv(filepath: str, fmt: str, no_prices: bool) -> None:
    """Import transactions from a CEX CSV export file."""
    click.echo(f"Parsing {fmt} CSV: {filepath}")
    importer = ExchangeImporter()
    transactions = importer.parse_file(filepath, fmt)
    click.echo(f"  Parsed {len(transactions)} transactions")

    db = _get_db()

    async def _run() -> None:
        if not no_prices and transactions:
            await _enrich_prices(transactions)
        count = _store_transactions(db, f"csv:{filepath}", fmt, transactions)
        click.echo(f"  Stored {count} transactions from {Path(filepath).name}")

    asyncio.run(_run())


# ── all ───────────────────────────────────────────────────────────────────────

@cli.command("all")
@click.option("--wallets", "wallets_file", required=True, type=click.Path(exists=True),
              help="JSON file listing wallets: [{address, chain, label?}]")
@click.option("--no-prices", is_flag=True, default=False, help="Skip historical price enrichment")
def import_all(wallets_file: str, no_prices: bool) -> None:
    """Import all wallets defined in a JSON config file."""
    wallets_data = json.loads(Path(wallets_file).read_text())
    if not isinstance(wallets_data, list):
        wallets_data = wallets_data.get("wallets", [])

    click.echo(f"Importing {len(wallets_data)} wallets from {wallets_file}")

    async def _run() -> None:
        db = _get_db()
        wallet_repo = WalletRepository(db)
        known_addresses = {w["address"].lower() for w in wallets_data}

        for w in wallets_data:
            addr = w["address"]
            chain = w.get("chain", "ethereum").lower()
            label = w.get("label")
            wallet_repo.add(addr, chain, label)

            click.echo(f"\n  [{chain}] {addr} ({label or 'no label'})")
            try:
                if chain == "solana":
                    importer = SolanaImporter()
                    transactions = await importer.fetch_all(addr, wallet_addresses=known_addresses)
                else:
                    importer = EVMImporter(chain)
                    transactions = await importer.fetch_all(addr, wallet_addresses={a for a in known_addresses})

                if not no_prices and transactions:
                    await _enrich_prices(transactions)

                count = _store_transactions(db, addr, chain, transactions)
                click.echo(f"    Stored {count} transactions")
            except Exception as exc:
                click.echo(f"    ERROR: {exc}", err=True)

    asyncio.run(_run())


# ── helpers ───────────────────────────────────────────────────────────────────

async def _enrich_prices(transactions: list[Transaction]) -> None:
    """
    Resolve USD prices for all asset transfers that are missing usd_value.
    Modifies transactions in-place.
    """
    service = PriceService()
    # Collect unique (symbol, date) pairs to batch-resolve
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

    # Apply prices back to transfers
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
        click.echo(f"  Warning: {missing} transfers have no USD price (flag for manual entry)", err=True)


if __name__ == "__main__":
    cli()
