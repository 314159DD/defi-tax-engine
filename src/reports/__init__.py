"""
Tax report generators for defi-tax-engine.

NOTE: The report implementations are being migrated to src/tax/{country}/ modules.
These imports are maintained for backward compatibility. New code should use
the TaxModule.generate_reports() interface instead.
"""
import warnings as _warnings

from src.reports.csv_export import TurboTaxExporter
from src.reports.form_8949 import Form8949Generator, Form8949Line
from src.reports.harvest import HarvestAnalyzer, HarvestSuggestion
from src.reports.income_report import IncomeReportGenerator, IncomeSummary
from src.reports.schedule_d import ScheduleDGenerator, ScheduleDSummary
from src.reports.source_of_funds import (
    FundingStep,
    HoldingOrigin,
    SourceOfFundsReport,
    trace_holdings,
)
from src.reports.source_of_funds_pdf import (
    generate_source_of_funds_csv,
    generate_source_of_funds_text,
)

__all__ = [
    "Form8949Generator",
    "Form8949Line",
    "ScheduleDGenerator",
    "ScheduleDSummary",
    "IncomeReportGenerator",
    "IncomeSummary",
    "TurboTaxExporter",
    "HarvestAnalyzer",
    "HarvestSuggestion",
    "FundingStep",
    "HoldingOrigin",
    "SourceOfFundsReport",
    "trace_holdings",
    "generate_source_of_funds_csv",
    "generate_source_of_funds_text",
]


def _deprecation_notice(name: str) -> None:
    _warnings.warn(
        f"src.reports.{name} is deprecated. Use src.tax.us.{name} or "
        f"TaxModule.generate_reports() instead.",
        DeprecationWarning,
        stacklevel=3,
    )
