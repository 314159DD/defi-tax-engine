"""
German Tax Module - EStG rules for cryptocurrency taxation.

Key rules:
  - Cost basis: FIFO only (BMF guidance)
  - Spekulationsfrist: crypto held >365 days is tax-exempt (§23 Abs. 1 EStG)
  - Freigrenze: if total short-term gains < EUR 1,000, ALL gains exempt
    (CLIFF - if total >= EUR 1,000, ALL gains are taxable, §23 Abs. 3 Satz 5 EStG)
  - Progressive tax brackets (14-45%) + Solidaritaetszuschlag (5.5%)
  - Staking rewards: Sonstige Einkuenfte (§22 Nr. 3 EStG)
  - Reports: Anlage SO, WISO Steuer CSV, DATEV export

References:
  - BMF-Schreiben 10.05.2022 (Einzelfragen zur ertragsteuerrechtlichen
    Behandlung von virtuellen Waehrungen und von sonstigen Token)
  - §23 EStG (Private Veraeusserungsgeschaefte)
  - §22 Nr. 3 EStG (Sonstige Einkuenfte)
  - §32a EStG (Einkommensteuertarif)

Tax brackets 2025/2026 (Grundtabelle, single filer):
  - 0% up to EUR 11,784 (Grundfreibetrag)
  - 14-24% zone: EUR 11,785 - EUR 17,005
  - 24-42% zone: EUR 17,006 - EUR 66,760
  - 42% zone: EUR 66,761 - EUR 277,825
  - 45% zone (Reichensteuer): above EUR 277,825
  - Plus 5.5% Solidaritaetszuschlag on tax amount
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from src.tax.base import TaxModule
from src.tax.citations import CitationCode, get_citation
from src.tax.models import (
    Exemption,
    HoldingPeriod,
    IncomeCategory,
    ReportFile,
    TaxSummary,
)

# Freigrenze threshold - §23 Abs. 3 Satz 5 EStG
_FREIGRENZE = Decimal("1000")

# German progressive tax brackets 2025/2026
_GRUNDFREIBETRAG = Decimal("11784")
_ZONE2_END = Decimal("17005")
_ZONE3_END = Decimal("66760")
_ZONE4_END = Decimal("277825")

# Solidaritaetszuschlag rate
_SOLI_RATE = Decimal("0.055")


def _calculate_german_income_tax(taxable_income: Decimal) -> Decimal:
    """
    Calculate German income tax (Einkommensteuer) per §32a EStG.

    Uses the 2025/2026 Grundtabelle (single filer).
    Returns the tax amount (before Soli).

    The formula uses the official BMF calculation zones:
      Zone 1: 0 - 11,784 EUR -> 0% (Grundfreibetrag)
      Zone 2: 11,785 - 17,005 EUR -> 14-24% progressive
      Zone 3: 17,006 - 66,760 EUR -> 24-42% progressive
      Zone 4: 66,761 - 277,825 EUR -> 42% flat
      Zone 5: > 277,825 EUR -> 45% flat (Reichensteuer)
    """
    if taxable_income <= _GRUNDFREIBETRAG:
        return Decimal("0")

    if taxable_income <= _ZONE2_END:
        # Zone 2: linear interpolation 14% -> 24%
        y = (taxable_income - Decimal("11784")) / Decimal("10000")
        tax = (Decimal("922.98") * y + Decimal("1400")) * y
        return tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if taxable_income <= _ZONE3_END:
        # Zone 3: linear interpolation 24% -> 42%
        z = (taxable_income - Decimal("17005")) / Decimal("10000")
        tax = (Decimal("181.19") * z + Decimal("2397")) * z + Decimal("1025.38")
        return tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    if taxable_income <= _ZONE4_END:
        # Zone 4: flat 42%
        tax = Decimal("0.42") * taxable_income - Decimal("10636.31")
        return tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # Zone 5: Reichensteuer 45%
    tax = Decimal("0.45") * taxable_income - Decimal("18972.06")
    return tax.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


class GermanTaxModule(TaxModule):
    """German (DE) tax rules for cryptocurrency."""

    country_code = "DE"
    country_name = "Germany"
    currency_code = "EUR"

    # ── Cost basis methods ─────────────────────────────────────────────

    def get_cost_basis_methods(self) -> list[str]:
        """FIFO is the only method accepted by German tax authorities (BMF)."""
        return ["FIFO"]

    def get_default_method(self) -> str:
        return "FIFO"

    def get_comparison_methods(self) -> list[str]:
        """Additional methods available for what-if analysis (not for filing)."""
        return ["FIFO", "LIFO", "HIFO"]

    # ── Holding period ─────────────────────────────────────────────────

    def classify_holding_period(
        self, acquired: date, disposed: date
    ) -> HoldingPeriod:
        """
        German Spekulationsfrist:
        - Held >365 days -> EXEMPT (tax-free, §23 Abs. 1 Satz 1 Nr. 2 EStG)
        - Held <=365 days -> SHORT_TERM (taxable as private Veraeusserungsgeschaeft)

        Note: Germany uses >365 days (not >=366). Held exactly 365 days = still taxable.
        Held 366 days = exempt.
        """
        days_held = (disposed - acquired).days
        if days_held > 365:
            return HoldingPeriod.EXEMPT
        return HoldingPeriod.SHORT_TERM

    # ── Exemptions ─────────────────────────────────────────────────────

    def get_exemptions(self, disposals: list, year: int) -> list[Exemption]:
        """
        Apply German exemptions:

        1. Spekulationsfrist (§23 Abs. 1 EStG):
           Disposals with holding period > 365 days are tax-exempt.

        2. Freigrenze (§23 Abs. 3 Satz 5 EStG):
           If total SHORT-TERM gains for the year < EUR 1,000,
           ALL short-term disposals are exempt.
           If total >= EUR 1,000, ALL short-term gains are taxable (CLIFF!).
        """
        exemptions: list[Exemption] = []

        # Filter to the requested year
        year_disposals = [
            d for d in disposals
            if hasattr(d.date, "year") and d.date.year == year
        ]

        # 1. Spekulationsfrist exemptions
        for d in year_disposals:
            hp = d.holding_period
            if isinstance(hp, HoldingPeriod):
                is_exempt = hp == HoldingPeriod.EXEMPT
            else:
                is_exempt = str(hp) == "exempt"

            if is_exempt:
                exemptions.append(Exemption(
                    disposal_id=d.tx_hash,
                    reason="Spekulationsfrist (held > 365 days)",
                    citation_code="\u00a723 Abs. 1 Satz 1 Nr. 2 EStG",
                    citation_text=(
                        "Private Veraeusserungsgeschaefte bei Kryptowaehrungen: "
                        "Steuerfreiheit nach Ablauf der Spekulationsfrist von einem Jahr."
                    ),
                    exempt_amount=d.gain_loss_usd,  # full gain is exempt
                ))

        # 2. Freigrenze check for short-term disposals
        short_term_disposals = [
            d for d in year_disposals
            if self._is_short_term(d)
        ]
        total_short_term_gains = sum(
            (d.gain_loss_usd for d in short_term_disposals if d.gain_loss_usd > Decimal("0")),
            Decimal("0"),
        )

        if total_short_term_gains < _FREIGRENZE and total_short_term_gains > Decimal("0"):
            # ALL short-term gains are exempt (below the Freigrenze)
            for d in short_term_disposals:
                if d.gain_loss_usd > Decimal("0"):
                    exemptions.append(Exemption(
                        disposal_id=d.tx_hash,
                        reason=(
                            f"Freigrenze: total short-term gains "
                            f"({total_short_term_gains:.2f} EUR) < 1,000 EUR"
                        ),
                        citation_code="\u00a723 Abs. 3 Satz 5 EStG",
                        citation_text=(
                            "Freigrenze fuer private Veraeusserungsgeschaefte: "
                            "Gewinne bleiben steuerfrei, wenn der aus den privaten "
                            "Veraeusserungsgeschaeften erzielte Gesamtgewinn im "
                            "Kalenderjahr weniger als 1.000 Euro betragen hat."
                        ),
                        exempt_amount=d.gain_loss_usd,
                    ))

        return exemptions

    # ── Tax liability ──────────────────────────────────────────────────

    def calculate_liability(
        self,
        gains: Decimal,
        income: Decimal,
        user_bracket: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate German tax liability on crypto gains + income.

        Args:
            gains: net taxable short-term gains (exempt gains already excluded)
            income: ordinary income from staking/airdrops (Sonstige Einkuenfte)
            user_bracket: optional override marginal rate

        Returns:
            Total tax including Solidaritaetszuschlag
        """
        if user_bracket is not None:
            total_taxable = max(gains + income, Decimal("0"))
            tax = (total_taxable * user_bracket).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            soli = (tax * _SOLI_RATE).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            return tax + soli

        total_taxable = max(gains + income, Decimal("0"))
        tax = _calculate_german_income_tax(total_taxable)
        soli = (tax * _SOLI_RATE).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return tax + soli

    # ── Citation tagging ─────────────────────────────────────────────

    def tag_citations(self, disposals: list, year: int) -> None:
        """
        Tag each disposal with the appropriate German tax citation.

        Considers Spekulationsfrist, Freigrenze cliff, LP deposits, and bridges.
        Mutates disposals in-place.
        """
        # Filter to the requested year
        year_disposals = [
            d for d in disposals
            if hasattr(d, "date") and hasattr(d.date, "year") and d.date.year == year
        ]

        # Calculate total short-term gains for Freigrenze check
        short_term_disposals = [d for d in year_disposals if self._is_short_term(d)]
        total_short_term_gains = sum(
            (d.gain_loss_usd for d in short_term_disposals if d.gain_loss_usd > Decimal("0")),
            Decimal("0"),
        )
        freigrenze_under = (
            total_short_term_gains < _FREIGRENZE
            and total_short_term_gains > Decimal("0")
        )

        for d in disposals:
            # Check for bridge transfers
            source = getattr(d, "source", None) or ""
            tx_type = getattr(d, "tx_type", None) or ""
            if source == "bridge" or tx_type == "bridge":
                citation = get_citation(CitationCode.DE_BRIDGE_TRANSFER)
                d.citation_code = CitationCode.DE_BRIDGE_TRANSFER.value
                d.citation_text = citation["text"]
                d.citation_source = citation["source"]
                d.is_gray_area = citation["is_gray_area"]
                continue

            # Check for LP deposits (gray area)
            if source in ("lp_add", "lp_deposit") or tx_type in ("lp_add", "lp_deposit"):
                citation = get_citation(CitationCode.DE_LP_DEPOSIT_GRAY_AREA)
                d.citation_code = CitationCode.DE_LP_DEPOSIT_GRAY_AREA.value
                d.citation_text = citation["text"]
                d.citation_source = citation["source"]
                d.is_gray_area = citation["is_gray_area"]
                continue

            # Determine holding period
            hp = getattr(d, "holding_period", None)
            hp_enum = getattr(d, "holding_period_enum", None)

            is_exempt = False
            if hp_enum == HoldingPeriod.EXEMPT:
                is_exempt = True
            elif isinstance(hp, str) and hp in ("exempt", "EXEMPT"):
                is_exempt = True

            if is_exempt:
                # Spekulationsfrist exempt (held > 1 year)
                citation = get_citation(CitationCode.DE_SPEKULATIONSFRIST_EXEMPT)
                d.citation_code = CitationCode.DE_SPEKULATIONSFRIST_EXEMPT.value
                d.citation_text = citation["text"]
                d.citation_source = citation["source"]
                d.is_gray_area = citation["is_gray_area"]
            else:
                # Short-term - check Freigrenze
                if freigrenze_under and d.gain_loss_usd > Decimal("0"):
                    citation = get_citation(CitationCode.DE_FREIGRENZE_EXEMPT)
                    d.citation_code = CitationCode.DE_FREIGRENZE_EXEMPT.value
                elif not freigrenze_under and total_short_term_gains >= _FREIGRENZE:
                    citation = get_citation(CitationCode.DE_FREIGRENZE_EXCEEDED)
                    d.citation_code = CitationCode.DE_FREIGRENZE_EXCEEDED.value
                else:
                    citation = get_citation(CitationCode.DE_SPEKULATIONSFRIST_TAXABLE)
                    d.citation_code = CitationCode.DE_SPEKULATIONSFRIST_TAXABLE.value

                d.citation_text = citation["text"]
                d.citation_source = citation["source"]
                d.is_gray_area = citation["is_gray_area"]

    def tag_income_citations(self, income_events: list) -> None:
        """
        Tag income events with appropriate German tax citations.

        Mutates income_events in-place.
        """
        for event in income_events:
            tx_type = event.get("tx_type", "") if isinstance(event, dict) else getattr(event, "tx_type", "")

            if tx_type in ("reward", "staking", "stake_reward", "mining", "mine", "airdrop"):
                citation = get_citation(CitationCode.DE_STAKING_INCOME)
                code = CitationCode.DE_STAKING_INCOME.value
            else:
                continue

            if isinstance(event, dict):
                event["citation_code"] = code
                event["citation_text"] = citation["text"]
                event["citation_source"] = citation["source"]
                event["is_gray_area"] = citation["is_gray_area"]
            else:
                event.citation_code = code
                event.citation_text = citation["text"]
                event.citation_source = citation["source"]
                event.is_gray_area = citation["is_gray_area"]

    # ── Reports ────────────────────────────────────────────────────────

    def generate_reports(
        self,
        disposals: list,
        income_events: list,
        year: int,
        method: str,
    ) -> list[ReportFile]:
        """Generate German tax reports: Anlage SO, WISO, DATEV."""
        # Tag all disposals and income events with citations
        self.tag_citations(disposals, year)
        self.tag_income_citations(income_events)

        from src.tax.de.anlage_so import generate_anlage_so_csv
        from src.tax.de.wiso_export import generate_wiso_csv
        from src.tax.de.datev_export import generate_datev_csv

        reports: list[ReportFile] = []

        # Anlage SO
        anlage_csv = generate_anlage_so_csv(disposals, income_events, year)
        reports.append(ReportFile(
            filename=f"anlage_so_{year}.csv",
            content=anlage_csv,
            mime_type="text/csv",
            report_type="anlage_so",
        ))

        # WISO Steuer
        wiso_csv = generate_wiso_csv(disposals, year)
        reports.append(ReportFile(
            filename=f"wiso_steuer_{year}.csv",
            content=wiso_csv,
            mime_type="text/csv",
            report_type="wiso",
        ))

        # DATEV
        datev_csv = generate_datev_csv(disposals, year)
        reports.append(ReportFile(
            filename=f"datev_{year}.csv",
            content=datev_csv,
            mime_type="text/csv",
            report_type="datev",
        ))

        return reports

    # ── Currency formatting ────────────────────────────────────────────

    def format_currency(self, amount: Decimal) -> str:
        """Format as EUR with German locale: 1.234,56 EUR"""
        abs_amount = abs(amount)
        # Round to 2 decimal places
        abs_amount = abs_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Format with US locale first, then swap separators
        formatted_us = f"{abs_amount:,.2f}"
        # Swap: comma -> X, dot -> comma, X -> dot
        formatted = formatted_us.replace(",", "X").replace(".", ",").replace("X", ".")
        formatted = f"{formatted} \u20ac"
        if amount < 0:
            formatted = f"-{formatted}"
        return formatted

    # ── Income categories ──────────────────────────────────────────────

    def get_income_categories(self) -> list[IncomeCategory]:
        return [
            IncomeCategory(
                name="Staking Rewards",
                description="Einkuenfte aus Staking von Kryptowaehrungen",
                citation="\u00a722 Nr. 3 EStG",
            ),
            IncomeCategory(
                name="Airdrops",
                description="Einkuenfte aus Airdrops",
                citation="\u00a722 Nr. 3 EStG",
            ),
            IncomeCategory(
                name="Mining",
                description="Einkuenfte aus Mining (ggf. gewerblich)",
                citation="\u00a715 EStG / \u00a722 Nr. 3 EStG",
            ),
            IncomeCategory(
                name="DeFi-Zinsen",
                description="Zinsen aus DeFi-Lending-Protokollen",
                citation="\u00a720 Abs. 1 Nr. 7 EStG / \u00a722 Nr. 3 EStG",
            ),
        ]

    # ── German-specific public helpers ─────────────────────────────────

    def get_freigrenze_status(
        self, disposals: list, year: int
    ) -> dict:
        """
        Return the Freigrenze status for the user.

        Returns dict with:
          realized_gains_ytd: total short-term gains so far
          limit: 1000
          remaining: how much more they can realize before the cliff
          status: "under" | "over"
        """
        year_disposals = [
            d for d in disposals
            if hasattr(d.date, "year") and d.date.year == year
        ]
        short_term_gains = sum(
            (d.gain_loss_usd for d in year_disposals
             if self._is_short_term(d) and d.gain_loss_usd > Decimal("0")),
            Decimal("0"),
        )

        remaining = max(_FREIGRENZE - short_term_gains, Decimal("0"))
        status = "under" if short_term_gains < _FREIGRENZE else "over"

        return {
            "realized_gains_ytd": str(short_term_gains),
            "limit": str(_FREIGRENZE),
            "remaining": str(remaining),
            "status": status,
        }

    def get_spekulationsfrist_data(self, lots: list) -> list[dict]:
        """
        Return per-lot data with Spekulationsfrist info.

        Args:
            lots: list of TaxLot objects

        Returns:
            List of dicts with token, amount, acquisition_date,
            spekulationsfrist_end, days_remaining, is_exempt
        """
        from datetime import date as date_type

        today = date_type.today()
        result = []
        for lot in lots:
            acq = lot.acquisition_date
            if hasattr(acq, "date"):
                acq_date = acq.date() if callable(acq.date) else acq.date
            else:
                acq_date = acq

            end_date = date_type(acq_date.year + 1, acq_date.month, acq_date.day) \
                if acq_date.month != 2 or acq_date.day != 29 \
                else date_type(acq_date.year + 1, 3, 1)

            days_remaining = max((end_date - today).days, 0)

            result.append({
                "token": lot.token,
                "amount": str(lot.remaining),
                "acquisition_date": str(acq_date),
                "spekulationsfrist_end": str(end_date),
                "days_remaining": days_remaining,
                "is_exempt": days_remaining == 0,
            })

        return result

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _is_short_term(d) -> bool:
        hp = d.holding_period
        if isinstance(hp, HoldingPeriod):
            return hp == HoldingPeriod.SHORT_TERM
        return str(hp) in ("short-term", "short", "SHORT_TERM")
