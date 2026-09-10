"""
Report CLI entry point.

Usage:
    python -m src.report form8949 --year 2025 --method FIFO --output form8949.csv
    python -m src.report schedule-d --year 2025 --method FIFO
    python -m src.report income --year 2025 --output income.csv
    python -m src.report summary --year 2025 --all-methods
    python -m src.report turbotax --year 2025 --output turbotax_import.csv
    python -m src.report harvest --suggestions
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import click

from src.storage.database import Database


def _db() -> Database:
    return Database()


# ── form8949 ──────────────────────────────────────────────────────────────────

@click.group()
def cli() -> None:
    """Crypto Tax - report generation."""


@cli.command("form8949")
@click.option("--year", required=True, type=int, help="Tax year (e.g. 2025)")
@click.option("--method", default="FIFO",
              type=click.Choice(["FIFO", "LIFO", "HIFO"], case_sensitive=False),
              show_default=True, help="Cost basis method")
@click.option("--output", default=None, help="Output CSV file path (default: stdout)")
def form8949(year: int, method: str, output: str | None) -> None:
    """Generate IRS Form 8949 CSV."""
    from src.reports.form_8949 import Form8949Generator
    gen = Form8949Generator(_db())
    csv_data = gen.to_csv(year, method.upper())
    if output:
        Path(output).write_text(csv_data, encoding="utf-8")
        click.echo(f"Form 8949 written to {output}")
    else:
        click.echo(csv_data)


# ── schedule-d ────────────────────────────────────────────────────────────────

@cli.command("schedule-d")
@click.option("--year", required=True, type=int, help="Tax year")
@click.option("--method", default="FIFO",
              type=click.Choice(["FIFO", "LIFO", "HIFO"], case_sensitive=False),
              show_default=True)
@click.option("--carryover", default="0", help="Prior year capital loss carryover (positive USD amount)")
def schedule_d(year: int, method: str, carryover: str) -> None:
    """Print Schedule D summary."""
    from src.reports.schedule_d import ScheduleDGenerator
    gen = ScheduleDGenerator(_db())
    report = gen.print_report(year, method.upper(), Decimal(carryover))
    click.echo(report)


# ── income ────────────────────────────────────────────────────────────────────

@cli.command("income")
@click.option("--year", required=True, type=int, help="Tax year")
@click.option("--output", default=None, help="Output CSV file path (default: print summary)")
def income(year: int, output: str | None) -> None:
    """Generate ordinary income report (staking, airdrops, mining)."""
    from src.reports.income_report import IncomeReportGenerator
    gen = IncomeReportGenerator(_db())
    if output:
        csv_data = gen.to_csv(year)
        Path(output).write_text(csv_data, encoding="utf-8")
        click.echo(f"Income report written to {output}")
    else:
        click.echo(gen.print_report(year))


# ── summary ───────────────────────────────────────────────────────────────────

@cli.command("summary")
@click.option("--year", required=True, type=int, help="Tax year")
@click.option("--all-methods", is_flag=True, default=False, help="Compare FIFO, LIFO, HIFO side by side")
@click.option("--method", default="FIFO",
              type=click.Choice(["FIFO", "LIFO", "HIFO"], case_sensitive=False),
              show_default=True, help="Single method (ignored if --all-methods)")
def summary(year: int, all_methods: bool, method: str) -> None:
    """Print tax year summary (capital gains + income)."""
    from src.reports.form_8949 import Form8949Generator
    from src.reports.income_report import IncomeReportGenerator
    from src.reports.schedule_d import ScheduleDGenerator

    db = _db()
    income_gen = IncomeReportGenerator(db)
    income_summary = income_gen.generate(year)

    methods = ["FIFO", "LIFO", "HIFO"] if all_methods else [method.upper()]

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Tax Summary - {year}")
    click.echo(f"{'=' * 60}\n")

    for m in methods:
        sched = ScheduleDGenerator(db)
        s = sched.generate(year, m)
        click.echo(f"  [{m}]")
        click.echo(f"    Short-term gains/losses: ${s.short_term_net:,.2f}")
        click.echo(f"    Long-term gains/losses:  ${s.long_term_net:,.2f}")
        click.echo(f"    Net capital gain/(loss): ${s.net_capital_gain_loss:,.2f}")
        if s.carryover_loss > Decimal("0"):
            click.echo(f"    Carryover loss:          ${s.carryover_loss:,.2f}")
        click.echo()

    click.echo(f"  Ordinary Income:")
    click.echo(f"    Staking rewards:  ${income_summary.total_staking:,.2f}")
    click.echo(f"    Airdrops:         ${income_summary.total_airdrop:,.2f}")
    click.echo(f"    Mining/Validator: ${income_summary.total_mining:,.2f}")
    click.echo(f"    DeFi Interest:    ${income_summary.total_interest:,.2f}")
    click.echo(f"    Total income:     ${income_summary.total_income:,.2f}")


# ── turbotax ──────────────────────────────────────────────────────────────────

@cli.command("turbotax")
@click.option("--year", required=True, type=int, help="Tax year")
@click.option("--method", default="FIFO",
              type=click.Choice(["FIFO", "LIFO", "HIFO"], case_sensitive=False),
              show_default=True)
@click.option("--output", default=None, help="Output CSV path (default: stdout)")
@click.option("--detail", is_flag=True, default=False, help="Include extra metadata columns")
def turbotax(year: int, method: str, output: str | None, detail: bool) -> None:
    """Export TurboTax / H&R Block / TaxAct compatible CSV."""
    from src.reports.csv_export import TurboTaxExporter
    exporter = TurboTaxExporter(_db())
    if detail:
        csv_data = exporter.export_full_detail(year, method.upper())
    else:
        csv_data = exporter.export(year, method.upper())
    if output:
        Path(output).write_text(csv_data, encoding="utf-8")
        click.echo(f"TurboTax CSV written to {output}")
    else:
        click.echo(csv_data)


# ── harvest ───────────────────────────────────────────────────────────────────

@cli.command("harvest")
@click.option("--suggestions", is_flag=True, default=False, help="Show tax loss harvesting suggestions")
@click.option("--prices", default=None,
              help='JSON string of current prices: \'{"ETH":"3000","BTC":"60000"}\'')
@click.option("--st-rate", default="0.37", help="Short-term tax rate (default: 0.37)")
@click.option("--lt-rate", default="0.20", help="Long-term tax rate (default: 0.20)")
def harvest(suggestions: bool, prices: str | None, st_rate: str, lt_rate: str) -> None:
    """Show tax loss harvesting opportunities."""
    import json as _json
    from src.reports.harvest import HarvestAnalyzer

    if not suggestions:
        click.echo("Use --suggestions to see harvesting opportunities.")
        return

    current_prices: dict[str, Decimal] = {}
    if prices:
        raw = _json.loads(prices)
        current_prices = {k.upper(): Decimal(str(v)) for k, v in raw.items()}
    else:
        click.echo(
            "Warning: no --prices provided. Pass current prices as JSON to see accurate suggestions.\n"
            "Example: --prices '{\"ETH\":\"3000\",\"BTC\":\"60000\"}'"
        )

    analyzer = HarvestAnalyzer(_db())
    report = analyzer.print_report(
        current_prices,
        short_term_rate=Decimal(st_rate),
        long_term_rate=Decimal(lt_rate),
    )
    click.echo(report)


if __name__ == "__main__":
    cli()
