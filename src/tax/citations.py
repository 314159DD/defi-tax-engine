"""
Tax citation database - maps tax treatments to legal references.

Every Disposal and IncomeEvent can be tagged with a citation that explains
*why* a particular tax treatment was applied. This builds user trust by
making the logic transparent and auditable.

US citations reference IRS guidance (IRC, Revenue Rulings, Notices).
DE citations reference BMF-Schreiben 2025 and EStG paragraphs.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional


class CitationCode(str, Enum):
    """Unique code for each tax treatment citation."""

    # ── US citations ──────────────────────────────────────────────────────
    US_SHORT_TERM_GAIN = "US_SHORT_TERM_GAIN"
    US_LONG_TERM_GAIN = "US_LONG_TERM_GAIN"
    US_STAKING_INCOME = "US_STAKING_INCOME"
    US_MINING_INCOME = "US_MINING_INCOME"
    US_AIRDROP_INCOME = "US_AIRDROP_INCOME"
    US_BRIDGE_TRANSFER = "US_BRIDGE_TRANSFER"
    US_WASH_SALE_WARNING = "US_WASH_SALE_WARNING"

    # ── DE citations ──────────────────────────────────────────────────────
    DE_SPEKULATIONSFRIST_TAXABLE = "DE_SPEKULATIONSFRIST_TAXABLE"
    DE_SPEKULATIONSFRIST_EXEMPT = "DE_SPEKULATIONSFRIST_EXEMPT"
    DE_FREIGRENZE_EXEMPT = "DE_FREIGRENZE_EXEMPT"
    DE_FREIGRENZE_EXCEEDED = "DE_FREIGRENZE_EXCEEDED"
    DE_STAKING_INCOME = "DE_STAKING_INCOME"
    DE_FIFO_METHOD = "DE_FIFO_METHOD"
    DE_LP_DEPOSIT_GRAY_AREA = "DE_LP_DEPOSIT_GRAY_AREA"
    DE_BRIDGE_TRANSFER = "DE_BRIDGE_TRANSFER"


# Type: {code, text, source, is_gray_area}
CITATIONS: dict[CitationCode, dict] = {
    # ── US ─────────────────────────────────────────────────────────────────
    CitationCode.US_SHORT_TERM_GAIN: {
        "code": "US_SHORT_TERM_GAIN",
        "text": "IRC \u00a71222(1) \u2014 Short-term capital gain on property held one year or less.",
        "source": "Internal Revenue Code \u00a71222(1)",
        "is_gray_area": False,
    },
    CitationCode.US_LONG_TERM_GAIN: {
        "code": "US_LONG_TERM_GAIN",
        "text": "IRC \u00a71222(3) \u2014 Long-term capital gain on property held more than one year.",
        "source": "Internal Revenue Code \u00a71222(3)",
        "is_gray_area": False,
    },
    CitationCode.US_STAKING_INCOME: {
        "code": "US_STAKING_INCOME",
        "text": (
            "Rev. Rul. 2023-14 \u2014 Staking rewards are gross income at fair market "
            "value upon receipt for cash-method taxpayers."
        ),
        "source": "Revenue Ruling 2023-14",
        "is_gray_area": False,
    },
    CitationCode.US_MINING_INCOME: {
        "code": "US_MINING_INCOME",
        "text": (
            "Notice 2014-21, Q&A 8 \u2014 Mining rewards constitute gross income "
            "at fair market value on the date of receipt."
        ),
        "source": "IRS Notice 2014-21, Q-8",
        "is_gray_area": False,
    },
    CitationCode.US_AIRDROP_INCOME: {
        "code": "US_AIRDROP_INCOME",
        "text": (
            "Rev. Rul. 2019-24 \u2014 Airdrop of cryptocurrency constitutes gross "
            "income at fair market value on date of receipt."
        ),
        "source": "Revenue Ruling 2019-24",
        "is_gray_area": False,
    },
    CitationCode.US_BRIDGE_TRANSFER: {
        "code": "US_BRIDGE_TRANSFER",
        "text": (
            "Non-taxable \u2014 Bridge transfer is a movement of the same asset between "
            "chains by the same taxpayer. No change in economic interest; cost basis "
            "carries over."
        ),
        "source": "General tax principles (same taxpayer, same economic interest)",
        "is_gray_area": False,
    },
    CitationCode.US_WASH_SALE_WARNING: {
        "code": "US_WASH_SALE_WARNING",
        "text": (
            "IRC \u00a71091 \u2014 Wash sale rules may apply. Note: the IRS has not "
            "formally extended wash sale rules to cryptocurrency as of 2025. "
            "Proposed legislation may change this."
        ),
        "source": "Internal Revenue Code \u00a71091 (applicability to crypto uncertain)",
        "is_gray_area": True,
    },

    # ── DE ─────────────────────────────────────────────────────────────────
    CitationCode.DE_SPEKULATIONSFRIST_TAXABLE: {
        "code": "DE_SPEKULATIONSFRIST_TAXABLE",
        "text": (
            "\u00a723 Abs. 1 Satz 1 Nr. 2 EStG \u2014 "
            "Ver\u00e4u\u00dferung innerhalb der Spekulationsfrist von einem Jahr. "
            "Der Gewinn ist als privates Ver\u00e4u\u00dferungsgesch\u00e4ft steuerpflichtig."
        ),
        "source": "\u00a723 Abs. 1 Satz 1 Nr. 2 EStG",
        "is_gray_area": False,
    },
    CitationCode.DE_SPEKULATIONSFRIST_EXEMPT: {
        "code": "DE_SPEKULATIONSFRIST_EXEMPT",
        "text": (
            "\u00a723 Abs. 1 Satz 1 Nr. 2 EStG \u2014 "
            "Steuerfrei nach Ablauf der Spekulationsfrist. "
            "Kryptow\u00e4hrungen, die l\u00e4nger als ein Jahr gehalten wurden, "
            "sind von der Besteuerung ausgenommen."
        ),
        "source": "\u00a723 Abs. 1 Satz 1 Nr. 2 EStG",
        "is_gray_area": False,
    },
    CitationCode.DE_FREIGRENZE_EXEMPT: {
        "code": "DE_FREIGRENZE_EXEMPT",
        "text": (
            "\u00a723 Abs. 3 Satz 5 EStG \u2014 Freigrenze von 1.000 EUR. "
            "Der Gesamtgewinn aus privaten Ver\u00e4u\u00dferungsgesch\u00e4ften "
            "im Kalenderjahr liegt unter der Freigrenze und ist daher steuerfrei."
        ),
        "source": "\u00a723 Abs. 3 Satz 5 EStG",
        "is_gray_area": False,
    },
    CitationCode.DE_FREIGRENZE_EXCEEDED: {
        "code": "DE_FREIGRENZE_EXCEEDED",
        "text": (
            "\u00a723 Abs. 3 Satz 5 EStG \u2014 Freigrenze \u00fcberschritten. "
            "Der Gesamtgewinn aus privaten Ver\u00e4u\u00dferungsgesch\u00e4ften "
            "im Kalenderjahr betr\u00e4gt 1.000 EUR oder mehr. "
            "S\u00e4mtliche Gewinne sind steuerpflichtig (Freigrenze, kein Freibetrag!)."
        ),
        "source": "\u00a723 Abs. 3 Satz 5 EStG",
        "is_gray_area": False,
    },
    CitationCode.DE_STAKING_INCOME: {
        "code": "DE_STAKING_INCOME",
        "text": (
            "\u00a722 Nr. 3 EStG \u2014 Sonstige Eink\u00fcnfte. "
            "Staking-Ertr\u00e4ge sind als sonstige Eink\u00fcnfte zum "
            "Zeitpunkt des Zuflusses mit dem gemeinen Wert zu versteuern "
            "(vgl. BMF-Schreiben 06.03.2025, Rn. 56)."
        ),
        "source": "\u00a722 Nr. 3 EStG; BMF-Schreiben 06.03.2025, Rn. 56",
        "is_gray_area": False,
    },
    CitationCode.DE_FIFO_METHOD: {
        "code": "DE_FIFO_METHOD",
        "text": (
            "BMF-Schreiben 06.03.2025, Rn. 45 \u2014 "
            "FIFO (First In, First Out) als Verbrauchsreihenfolge f\u00fcr "
            "die Bestimmung der Anschaffungskosten bei Ver\u00e4u\u00dferung "
            "von Kryptow\u00e4hrungen."
        ),
        "source": "BMF-Schreiben 06.03.2025, Rn. 45",
        "is_gray_area": False,
    },
    CitationCode.DE_LP_DEPOSIT_GRAY_AREA: {
        "code": "DE_LP_DEPOSIT_GRAY_AREA",
        "text": (
            "BMF-Schreiben 06.03.2025, Rn. 68 \u2014 "
            "Tauschvorgang bei Liquidit\u00e4tspool-Einlage. "
            "Die Einlage in einen Liquidit\u00e4tspool wird als Tausch behandelt "
            "(strittig). Konservative Behandlung angewandt."
        ),
        "source": "BMF-Schreiben 06.03.2025, Rn. 68",
        "is_gray_area": True,
    },
    CitationCode.DE_BRIDGE_TRANSFER: {
        "code": "DE_BRIDGE_TRANSFER",
        "text": (
            "Kein steuerbarer Vorgang \u2014 Bridge-Transfer zwischen Chains "
            "durch denselben Steuerpflichtigen. Die Anschaffungskosten werden "
            "fortgef\u00fchrt."
        ),
        "source": "Allgemeine Grunds\u00e4tze (gleicher Steuerpflichtiger, gleicher Verm\u00f6genswert)",
        "is_gray_area": False,
    },
}


def get_citation(code: CitationCode) -> dict:
    """
    Retrieve citation data for a given CitationCode.

    Args:
        code: CitationCode enum value

    Returns:
        dict with keys: code, text, source, is_gray_area

    Raises:
        KeyError: if the code is not in the database
    """
    if code not in CITATIONS:
        raise KeyError(f"Unknown citation code: {code!r}")
    return CITATIONS[code]


def get_citations_for_country(country_code: str) -> dict[CitationCode, dict]:
    """
    Return all citations for a given country code.

    Args:
        country_code: "US" or "DE" (case-insensitive)

    Returns:
        dict mapping CitationCode -> citation data for that country
    """
    prefix = country_code.upper() + "_"
    return {
        code: data
        for code, data in CITATIONS.items()
        if code.value.startswith(prefix)
    }
