"""
Report methodology statements - appended to every generated tax report.

Provides a clear, professional statement of the methodology and legal basis
used to prepare the report. Builds trust with users and their tax advisors.
"""
from __future__ import annotations


def get_methodology_statement(country_code: str, method: str, year: int) -> str:
    """
    Return a methodology statement for inclusion in tax reports.

    Args:
        country_code: "US" or "DE" (case-insensitive)
        method: cost basis method used, e.g. "FIFO", "LIFO", "HIFO"
        year: the tax year

    Returns:
        Human-readable methodology statement string

    Raises:
        ValueError: if country_code is not supported
    """
    code = country_code.upper()

    if code == "US":
        return _us_methodology(method, year)
    elif code == "DE":
        return _de_methodology(method, year)
    else:
        raise ValueError(f"No methodology statement available for country: {code!r}")


def _us_methodology(method: str, year: int) -> str:
    return (
        f"This report was prepared using the {method} cost basis method per IRS guidance "
        f"in Notice 2014-21 and Revenue Ruling 2023-14. Cryptocurrency is treated as "
        f"property for federal tax purposes. Capital gains and losses are reported on "
        f"Form 8949 and Schedule D. Form 8949 categorization follows the {year} "
        f"Instructions for Form 8949. Income from staking, mining, and airdrops is "
        f"reported as ordinary income at fair market value on the date of receipt. "
        f"This report is for informational purposes only and does not constitute tax advice. "
        f"Consult a qualified tax professional for your specific situation."
    )


def _de_methodology(method: str, year: int) -> str:
    return (
        f"Dieser Bericht wurde gem\u00e4\u00df dem BMF-Schreiben vom 06.03.2025 "
        f"(Az. IV C 1 - S 2256/24/10001 :001) unter Anwendung der "
        f"{method}-Verbrauchsreihenfolge erstellt. "
        f"Kryptow\u00e4hrungen gelten als private Verm\u00f6gensgegenst\u00e4nde i.S.d. "
        f"\u00a723 EStG. Ver\u00e4u\u00dferungen innerhalb der einj\u00e4hrigen "
        f"Spekulationsfrist unterliegen der Einkommensteuer (\u00a723 Abs. 1 Satz 1 Nr. 2 EStG). "
        f"Die Freigrenze betr\u00e4gt 1.000 EUR (\u00a723 Abs. 3 Satz 5 EStG). "
        f"Staking-Ertr\u00e4ge werden als sonstige Eink\u00fcnfte gem. \u00a722 Nr. 3 EStG erfasst. "
        f"Steuerjahr: {year}. "
        f"Dieser Bericht dient ausschlie\u00dflich der Information und ersetzt keine "
        f"steuerliche Beratung durch einen Steuerberater."
    )
