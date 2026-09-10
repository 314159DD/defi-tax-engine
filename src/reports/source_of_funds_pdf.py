"""
Source of Funds report formatters - CSV and human-readable text output.

Designed for bank/exchange KYC submission (Herkunftsnachweis).
CSV is machine-readable; text is suitable for PDF generation or direct reading.

CRITICAL: All monetary values use decimal.Decimal - NEVER float.
"""
from __future__ import annotations

import csv
import io
from decimal import Decimal

from src.reports.source_of_funds import (
    FundingStep,
    HoldingOrigin,
    SourceOfFundsReport,
)


# ---------------------------------------------------------------------------
# Acquisition method labels (human-readable)
# ---------------------------------------------------------------------------

_METHOD_LABEL: dict[str, str] = {
    "exchange_purchase": "Exchange Purchase",
    "staking_reward": "Staking Reward",
    "defi_yield": "DeFi Yield",
    "airdrop": "Airdrop",
    "swap": "DEX Swap",
    "transfer": "Wallet Transfer",
    "mining": "Mining",
}


def _method_label(method: str) -> str:
    return _METHOD_LABEL.get(method, method.replace("_", " ").title())


# ---------------------------------------------------------------------------
# CSV generator
# ---------------------------------------------------------------------------

def generate_source_of_funds_csv(report: SourceOfFundsReport) -> str:
    """
    CSV format suitable for bank/exchange KYC submission.

    Columns: Token, Amount, Current Value (USD), Acquisition Method,
             Acquisition Date, Original Cost (USD), Source, Chain,
             Wallet Address
    """
    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        "Token",
        "Amount",
        "Current Value (USD)",
        "Acquisition Method",
        "Acquisition Date",
        "Original Cost (USD)",
        "Source",
        "Chain",
        "Wallet Address",
    ]
    writer.writerow(headers)

    for holding in report.holdings:
        # Determine the original source from the first step in the trail
        source = "N/A"
        if holding.funding_trail:
            source = holding.funding_trail[0].source

        writer.writerow([
            holding.token,
            str(holding.current_amount),
            str(holding.current_value_usd),
            _method_label(holding.acquisition_method),
            holding.original_acquisition_date.isoformat(),
            str(holding.original_acquisition_cost),
            source,
            holding.chain,
            holding.wallet_address,
        ])

    return output.getvalue()


# ---------------------------------------------------------------------------
# Text report generator
# ---------------------------------------------------------------------------

def generate_source_of_funds_text(report: SourceOfFundsReport) -> str:
    """
    Human-readable text report suitable for bank KYC submission.

    Structure:
    - Header: report date, wallets covered
    - Per-holding section with full funding trail
    - Summary: total portfolio value, total cost basis
    - Footer: methodology note
    """
    lines: list[str] = []

    # --- Header ---
    lines.append("=" * 72)
    lines.append("SOURCE OF FUNDS REPORT")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Report generated: {report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Wallets covered:  {len(report.wallet_addresses)}")
    for addr in report.wallet_addresses:
        lines.append(f"  - {addr}")
    lines.append("")
    lines.append(f"Total holdings traced: {len(report.holdings)}")
    lines.append("")
    lines.append("-" * 72)

    # --- Per-holding sections ---
    for i, holding in enumerate(report.holdings, start=1):
        lines.append("")
        lines.append(f"HOLDING {i}: {holding.current_amount} {holding.token}")
        lines.append(f"  Wallet:             {holding.wallet_address}")
        lines.append(f"  Chain:              {holding.chain}")
        lines.append(f"  Acquisition Method: {_method_label(holding.acquisition_method)}")
        lines.append(f"  Acquisition Date:   {holding.original_acquisition_date.isoformat()}")
        lines.append(f"  Original Cost:      ${holding.original_acquisition_cost}")
        lines.append(f"  Current Value:      ${holding.current_value_usd}")
        lines.append("")

        if holding.funding_trail:
            lines.append("  Transaction Trail:")
            for step in holding.funding_trail:
                tx_ref = step.tx_hash[:16] + "..." if step.tx_hash and len(step.tx_hash) > 16 else (step.tx_hash or "N/A")
                lines.append(
                    f"    Step {step.step_number}: "
                    f"{step.date.isoformat()} - {step.action} "
                    f"{step.amount} {step.token} "
                    f"(${step.value_usd}) "
                    f"via {step.source} "
                    f"[{step.chain}] "
                    f"tx: {tx_ref}"
                )
        else:
            lines.append("  Transaction Trail: No detailed trail available.")

        lines.append("")
        lines.append("-" * 72)

    # --- Summary ---
    lines.append("")
    lines.append("SUMMARY")
    lines.append("=" * 72)
    lines.append(f"Total Portfolio Value (cost basis): ${report.total_portfolio_value}")
    lines.append(f"Total Acquisition Cost:             ${report.total_acquisition_cost}")
    lines.append(f"Number of Holdings:                 {len(report.holdings)}")
    lines.append("")

    # --- Footer ---
    lines.append("-" * 72)
    lines.append("METHODOLOGY")
    lines.append("-" * 72)
    lines.append(
        "This report was generated by automated analysis of on-chain "
        "transaction data. Each holding was traced backward through the "
        "complete transaction history to identify its original acquisition "
        "source. Transaction data was obtained from public blockchain "
        "explorers and exchange import records."
    )
    lines.append("")
    lines.append(
        "Values shown are based on the fair market value (FMV) at the time "
        "of each transaction, sourced from CoinGecko price data. Cost basis "
        "is calculated using the FIFO (First In, First Out) method unless "
        "otherwise specified."
    )
    lines.append("")
    lines.append("This report is provided for informational purposes only and")
    lines.append("does not constitute tax or legal advice.")
    lines.append("")
    lines.append("=" * 72)

    return "\n".join(lines)
