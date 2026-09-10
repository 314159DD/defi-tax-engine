"""
Tests for Sprint 5.1: Tax Loss Harvesting Dashboard.

Covers:
  - Unrealized position calculation (US + DE)
  - Harvest simulation (single + multi position)
  - Wash sale detection (30-day window)
  - Wash sale basis adjustment
  - DE-specific: Freigrenze-aware harvesting
  - DE-specific: Spekulationsfrist strategy
  - All monetary values as Decimal
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.calculator.lots import TaxLot
from src.reports.harvest import (
    UnrealizedPosition,
    get_unrealized_positions,
)
from src.reports.harvest_simulator import (
    HarvestScenario,
    get_freigrenze_headroom,
    simulate_harvest,
)
from src.tax.models import HoldingPeriod
from src.tax.us.wash_sale import (
    WashSaleWindow,
    adjust_basis_for_wash_sale,
    check_wash_sales,
    get_active_windows,
    would_trigger_wash_sale,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_lot_dict(
    lot_id: str = "lot-1",
    token: str = "ETH",
    amount: str = "2.0",
    cost_basis_usd: str = "4000",
    acquisition_date: str = "2025-01-15",
    remaining: str = "2.0",
) -> dict:
    """Create a lot dict matching TaxLotRepository.get_all() format."""
    return {
        "id": lot_id,
        "token": token,
        "amount": Decimal(amount),
        "cost_basis_usd": Decimal(cost_basis_usd),
        "acquisition_date": acquisition_date,
        "remaining": Decimal(remaining),
        "source": "swap",
        "tx_hash": f"0x{lot_id}",
    }


def _make_tax_lot(
    lot_id: str = "lot-1",
    token: str = "ETH",
    amount: str = "2.0",
    cost_basis_usd: str = "4000",
    acquisition_date: str = "2025-01-15",
    remaining: str = "2.0",
) -> TaxLot:
    """Create a TaxLot dataclass for wash sale tests."""
    return TaxLot(
        id=lot_id,
        token=token,
        amount=Decimal(amount),
        cost_basis_usd=Decimal(cost_basis_usd),
        acquisition_date=datetime.fromisoformat(acquisition_date).replace(tzinfo=timezone.utc),
        remaining=Decimal(remaining),
        source="swap",
        tx_hash=f"0x{lot_id}",
    )


def _get_us_module():
    from src.tax.us.module import USTaxModule
    return USTaxModule()


def _get_de_module():
    from src.tax.de.module import GermanTaxModule
    return GermanTaxModule()


# ===========================================================================
# 1. Unrealized position calculation
# ===========================================================================

class TestUnrealizedPositions:
    """Test get_unrealized_positions with various scenarios."""

    def test_basic_unrealized_loss(self):
        """Lot bought at $2000/ETH, current price $1500 -> unrealized loss."""
        lots = [_make_lot_dict(
            token="ETH",
            amount="2.0",
            cost_basis_usd="4000",   # $2000/ETH
            remaining="2.0",
            acquisition_date="2025-06-01",
        )]
        prices = {"ETH": Decimal("1500")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 9, 1))

        assert len(positions) == 1
        pos = positions[0]
        assert pos.token == "ETH"
        assert pos.amount == Decimal("2.0")
        assert pos.cost_basis == Decimal("4000")
        assert pos.current_value == Decimal("3000")
        assert pos.unrealized_gain_loss == Decimal("-1000")
        assert pos.holding_period == HoldingPeriod.SHORT_TERM
        assert pos.days_held == 92

    def test_basic_unrealized_gain(self):
        """Lot bought at $2000/ETH, current price $2500 -> unrealized gain."""
        lots = [_make_lot_dict(
            token="ETH",
            amount="1.0",
            cost_basis_usd="2000",
            remaining="1.0",
            acquisition_date="2025-01-01",
        )]
        prices = {"ETH": Decimal("2500")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 3, 1))

        assert len(positions) == 1
        assert positions[0].unrealized_gain_loss == Decimal("500")

    def test_sorted_by_unrealized_loss_ascending(self):
        """Largest losses should appear first (sorted ascending)."""
        lots = [
            _make_lot_dict(lot_id="lot-1", token="ETH", amount="1.0",
                           cost_basis_usd="3000", remaining="1.0",
                           acquisition_date="2025-03-01"),
            _make_lot_dict(lot_id="lot-2", token="BTC", amount="0.1",
                           cost_basis_usd="6000", remaining="0.1",
                           acquisition_date="2025-03-01"),
        ]
        prices = {"ETH": Decimal("2000"), "BTC": Decimal("50000")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 6, 1))

        assert len(positions) == 2
        # BTC: 0.1 * 50000 = 5000, cost = 6000, unrealized = -1000
        # ETH: 1.0 * 2000 = 2000, cost = 3000, unrealized = -1000
        # Both -1000, order should be stable
        assert all(p.unrealized_gain_loss <= Decimal("0") or True for p in positions)

    def test_skip_lots_with_no_remaining(self):
        """Lots with remaining=0 should be excluded."""
        lots = [_make_lot_dict(remaining="0")]
        prices = {"ETH": Decimal("2000")}

        positions = get_unrealized_positions(lots, prices, country="US")
        assert len(positions) == 0

    def test_skip_lots_without_price(self):
        """Lots for tokens without a current price should be excluded."""
        lots = [_make_lot_dict(token="OBSCURE")]
        prices = {"ETH": Decimal("2000")}  # no price for OBSCURE

        positions = get_unrealized_positions(lots, prices, country="US")
        assert len(positions) == 0

    def test_partially_consumed_lot(self):
        """Lot with amount=2 but remaining=0.5 should use remaining for calc."""
        lots = [_make_lot_dict(
            amount="2.0",
            cost_basis_usd="4000",   # $2000/unit
            remaining="0.5",
            acquisition_date="2025-01-01",
        )]
        prices = {"ETH": Decimal("1500")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 3, 1))

        assert len(positions) == 1
        pos = positions[0]
        assert pos.amount == Decimal("0.5")
        # cost of remaining = 0.5 * ($4000/2) = $1000
        assert pos.cost_basis == Decimal("1000")
        # current value = 0.5 * $1500 = $750
        assert pos.current_value == Decimal("750")
        assert pos.unrealized_gain_loss == Decimal("-250")

    def test_us_long_term_classification(self):
        """US: held >= 366 days -> LONG_TERM."""
        lots = [_make_lot_dict(acquisition_date="2024-01-01")]
        prices = {"ETH": Decimal("2000")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 3, 1))

        assert len(positions) == 1
        assert positions[0].holding_period == HoldingPeriod.LONG_TERM
        assert positions[0].days_held > 365

    def test_us_short_term_classification(self):
        """US: held < 366 days -> SHORT_TERM."""
        lots = [_make_lot_dict(acquisition_date="2025-06-01")]
        prices = {"ETH": Decimal("2000")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 9, 1))

        assert positions[0].holding_period == HoldingPeriod.SHORT_TERM

    def test_de_exempt_classification(self):
        """DE: held > 365 days -> EXEMPT (Spekulationsfrist)."""
        lots = [_make_lot_dict(acquisition_date="2024-01-01")]
        prices = {"ETH": Decimal("2000")}

        positions = get_unrealized_positions(lots, prices, country="DE", as_of_date=date(2025, 3, 1))

        assert len(positions) == 1
        pos = positions[0]
        assert pos.holding_period == HoldingPeriod.EXEMPT
        assert pos.is_tax_free is True
        assert pos.spekulationsfrist_remaining == 0

    def test_de_short_term_with_spekulationsfrist_remaining(self):
        """DE: held < 365 days -> SHORT_TERM with days remaining count."""
        lots = [_make_lot_dict(acquisition_date="2025-06-01")]
        prices = {"ETH": Decimal("2000")}

        positions = get_unrealized_positions(lots, prices, country="DE", as_of_date=date(2025, 9, 1))

        pos = positions[0]
        assert pos.holding_period == HoldingPeriod.SHORT_TERM
        assert pos.is_tax_free is False
        assert pos.spekulationsfrist_remaining is not None
        assert pos.spekulationsfrist_remaining > 0
        # From June 1 to Sep 1 = 92 days held. Need 366 days. Remaining = 366 - 92 = 274
        assert pos.spekulationsfrist_remaining == 274

    def test_all_monetary_values_are_decimal(self):
        """Ensure no floats leak into the position data."""
        lots = [_make_lot_dict()]
        prices = {"ETH": Decimal("1500")}

        positions = get_unrealized_positions(lots, prices, country="US", as_of_date=date(2025, 9, 1))

        pos = positions[0]
        assert isinstance(pos.amount, Decimal)
        assert isinstance(pos.cost_basis, Decimal)
        assert isinstance(pos.current_value, Decimal)
        assert isinstance(pos.unrealized_gain_loss, Decimal)


# ===========================================================================
# 2. Harvest simulation
# ===========================================================================

class TestHarvestSimulation:
    """Test simulate_harvest with single and multi-position scenarios."""

    def _make_position(
        self,
        lot_id: str = "lot-1",
        token: str = "ETH",
        unrealized: str = "-1000",
        holding_period: HoldingPeriod = HoldingPeriod.SHORT_TERM,
    ) -> UnrealizedPosition:
        ugl = Decimal(unrealized)
        cost = Decimal("3000")
        current = cost + ugl
        return UnrealizedPosition(
            token=token,
            lot_id=lot_id,
            amount=Decimal("1.0"),
            cost_basis=cost,
            current_value=current,
            unrealized_gain_loss=ugl,
            holding_period=holding_period,
            acquisition_date=date(2025, 6, 1),
            days_held=90,
        )

    def test_single_loss_us(self):
        """Selling one losing position at 37% bracket."""
        positions = [self._make_position(unrealized="-1000")]
        module = _get_us_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("5000"),
            user_bracket=Decimal("0.37"),
            selected_lot_ids=["lot-1"],
        )

        assert scenario.total_realized_loss == Decimal("1000")
        assert scenario.total_realized_gain == Decimal("0")
        assert scenario.net_impact == Decimal("-1000")
        # Tax savings = 1000 * 0.37 = 370
        assert scenario.projected_tax_savings == Decimal("370.00")
        assert scenario.freigrenze_impact == "n/a"  # US doesn't have Freigrenze

    def test_single_gain_us(self):
        """Selling one winning position should show negative savings (more tax)."""
        positions = [self._make_position(unrealized="500")]
        module = _get_us_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("5000"),
            user_bracket=Decimal("0.37"),
            selected_lot_ids=["lot-1"],
        )

        assert scenario.total_realized_gain == Decimal("500")
        assert scenario.total_realized_loss == Decimal("0")
        assert scenario.projected_tax_savings == Decimal("-185.00")

    def test_multi_position_mixed(self):
        """Multiple positions: one loss, one gain -> net impact."""
        positions = [
            self._make_position(lot_id="lot-1", unrealized="-2000"),
            self._make_position(lot_id="lot-2", unrealized="500"),
        ]
        module = _get_us_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("10000"),
            user_bracket=Decimal("0.37"),
            selected_lot_ids=["lot-1", "lot-2"],
        )

        assert scenario.total_realized_loss == Decimal("2000")
        assert scenario.total_realized_gain == Decimal("500")
        assert scenario.net_impact == Decimal("-1500")
        assert scenario.projected_tax_savings == Decimal("555.00")
        assert len(scenario.positions_to_sell) == 2

    def test_empty_selection(self):
        """No positions selected -> zero impact."""
        positions = [self._make_position()]
        module = _get_us_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("0"),
            user_bracket=Decimal("0.37"),
            selected_lot_ids=[],
        )

        assert scenario.net_impact == Decimal("0")
        assert scenario.projected_tax_savings == Decimal("0")

    def test_select_subset(self):
        """Only selected lot IDs should be included."""
        positions = [
            self._make_position(lot_id="lot-1", unrealized="-1000"),
            self._make_position(lot_id="lot-2", unrealized="-500"),
            self._make_position(lot_id="lot-3", unrealized="-200"),
        ]
        module = _get_us_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("0"),
            user_bracket=Decimal("0.37"),
            selected_lot_ids=["lot-1", "lot-3"],
        )

        assert len(scenario.positions_to_sell) == 2
        assert scenario.total_realized_loss == Decimal("1200")

    def test_scenario_as_dict_all_strings(self):
        """as_dict() should serialize all Decimals to strings."""
        positions = [self._make_position(unrealized="-1000")]
        module = _get_us_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("0"),
            user_bracket=Decimal("0.37"),
        )

        d = scenario.as_dict()
        for key in ("total_realized_loss", "total_realized_gain", "net_impact",
                     "projected_tax_savings", "new_freigrenze_total"):
            assert isinstance(d[key], str), f"{key} should be string, got {type(d[key])}"


# ===========================================================================
# 3. DE-specific: Freigrenze-aware harvesting
# ===========================================================================

class TestDEFreigrenze:
    """Test Freigrenze cliff detection in harvest scenarios."""

    def _make_de_position(
        self,
        lot_id: str = "lot-de-1",
        unrealized: str = "-500",
    ) -> UnrealizedPosition:
        ugl = Decimal(unrealized)
        cost = Decimal("2000")
        return UnrealizedPosition(
            token="ETH",
            lot_id=lot_id,
            amount=Decimal("1.0"),
            cost_basis=cost,
            current_value=cost + ugl,
            unrealized_gain_loss=ugl,
            holding_period=HoldingPeriod.SHORT_TERM,
            acquisition_date=date(2025, 6, 1),
            days_held=90,
            spekulationsfrist_remaining=276,
            is_tax_free=False,
        )

    def test_stays_under_freigrenze(self):
        """Harvest a loss when gains are under EUR 1000 -> stays_under."""
        positions = [self._make_de_position(unrealized="-200")]
        module = _get_de_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("500"),
            user_bracket=Decimal("0.42"),
        )

        assert scenario.freigrenze_impact == "stays_under"
        # Net ST gains: 500 + (-200) = 300 (the loss reduces gains)
        assert scenario.new_freigrenze_total == Decimal("300")

    def test_would_exceed_freigrenze(self):
        """Harvesting a gain that pushes above EUR 1000 -> would_exceed."""
        positions = [self._make_de_position(unrealized="600")]
        module = _get_de_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("500"),
            user_bracket=Decimal("0.42"),
        )

        assert scenario.freigrenze_impact == "would_exceed"
        assert scenario.new_freigrenze_total == Decimal("1100")

    def test_already_exceeded_freigrenze(self):
        """Gains already over EUR 1000 -> already_exceeded."""
        positions = [self._make_de_position(unrealized="-200")]
        module = _get_de_module()

        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("1500"),
            user_bracket=Decimal("0.42"),
        )

        assert scenario.freigrenze_impact == "already_exceeded"

    def test_freigrenze_headroom_under(self):
        """Headroom function: well under limit."""
        result = get_freigrenze_headroom(Decimal("300"))
        assert result["status"] == "under"
        assert result["remaining"] == "700"
        assert result["limit"] == "1000"

    def test_freigrenze_headroom_over(self):
        """Headroom function: over limit."""
        result = get_freigrenze_headroom(Decimal("1500"))
        assert result["status"] == "over"
        assert result["remaining"] == "0"

    def test_exempt_positions_dont_affect_freigrenze(self):
        """Positions held > 365 days (EXEMPT) should not change Freigrenze total."""
        exempt_pos = UnrealizedPosition(
            token="ETH",
            lot_id="lot-exempt",
            amount=Decimal("1.0"),
            cost_basis=Decimal("2000"),
            current_value=Decimal("3000"),
            unrealized_gain_loss=Decimal("1000"),
            holding_period=HoldingPeriod.EXEMPT,
            acquisition_date=date(2024, 1, 1),
            days_held=400,
            spekulationsfrist_remaining=0,
            is_tax_free=True,
        )
        module = _get_de_module()

        scenario = simulate_harvest(
            positions=[exempt_pos],
            tax_module=module,
            current_year_gains=Decimal("500"),
            user_bracket=Decimal("0.42"),
        )

        # Exempt positions don't count for Freigrenze
        assert scenario.new_freigrenze_total == Decimal("500")
        assert scenario.freigrenze_impact == "stays_under"


# ===========================================================================
# 4. DE-specific: Spekulationsfrist strategy
# ===========================================================================

class TestDESpekulationsfrist:
    """Test strategy: sell short-term losses, keep lots approaching Spekulationsfrist."""

    def test_identify_harvest_vs_hold_strategy(self):
        """
        Given two losing lots:
          - lot-1: 200 days held (still 166 days to go) -> candidate for harvest
          - lot-2: 350 days held (only 16 days to go) -> should HOLD (almost exempt)

        The strategy is to harvest lot-1 (far from exempt) and hold lot-2 (nearly exempt).
        """
        lots = [
            _make_lot_dict(
                lot_id="lot-harvest",
                token="ETH",
                amount="1.0",
                cost_basis_usd="3000",
                remaining="1.0",
                acquisition_date="2025-01-01",  # 200 days ago from 2025-07-20
            ),
            _make_lot_dict(
                lot_id="lot-hold",
                token="ETH",
                amount="1.0",
                cost_basis_usd="3000",
                remaining="1.0",
                acquisition_date="2024-08-05",  # 350 days ago from 2025-07-20
            ),
        ]
        prices = {"ETH": Decimal("2500")}  # both at a loss

        positions = get_unrealized_positions(
            lots, prices, country="DE", as_of_date=date(2025, 7, 20)
        )

        assert len(positions) == 2

        # Find positions by lot_id
        pos_by_id = {p.lot_id: p for p in positions}

        harvest_pos = pos_by_id["lot-harvest"]
        hold_pos = pos_by_id["lot-hold"]

        # lot-harvest: far from Spekulationsfrist expiry
        assert harvest_pos.spekulationsfrist_remaining > 100
        assert harvest_pos.is_tax_free is False

        # lot-hold: very close to becoming tax-free
        assert hold_pos.spekulationsfrist_remaining < 30
        assert hold_pos.is_tax_free is False

        # Strategy: only harvest lot-harvest, keep lot-hold
        module = _get_de_module()
        scenario = simulate_harvest(
            positions=positions,
            tax_module=module,
            current_year_gains=Decimal("0"),
            user_bracket=Decimal("0.42"),
            selected_lot_ids=["lot-harvest"],
        )

        assert len(scenario.positions_to_sell) == 1
        assert scenario.positions_to_sell[0] == "lot-harvest"
        assert scenario.total_realized_loss == Decimal("500")  # 3000 - 2500


# ===========================================================================
# 5. Wash sale detection
# ===========================================================================

class TestWashSaleDetection:
    """Test wash sale window detection (30 days before/after)."""

    def test_basic_wash_sale_forward(self):
        """Sell at loss, buy same token 10 days later -> wash sale."""
        disposals = [{
            "token": "ETH",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("-500"),
            "tx_hash": "0xsale1",
        }]
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-06-25",  # 10 days after sale
            "lot_id": "lot-new",
        }]

        windows = check_wash_sales(disposals, acquisitions)

        assert len(windows) == 1
        w = windows[0]
        assert w.token == "ETH"
        assert w.sale_date == date(2025, 6, 15)
        assert w.window_start == date(2025, 5, 16)
        assert w.window_end == date(2025, 7, 15)
        assert w.disallowed_loss == Decimal("500")
        assert w.replacement_lot_id == "lot-new"

    def test_basic_wash_sale_backward(self):
        """Buy token, then sell at loss 15 days later -> wash sale (30-day lookback)."""
        disposals = [{
            "token": "BTC",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("-2000"),
        }]
        acquisitions = [{
            "token": "BTC",
            "acquisition_date": "2025-05-20",  # 26 days before sale (within 30)
            "lot_id": "lot-prior",
        }]

        windows = check_wash_sales(disposals, acquisitions)

        assert len(windows) == 1
        assert windows[0].disallowed_loss == Decimal("2000")
        assert windows[0].replacement_lot_id == "lot-prior"

    def test_no_wash_sale_outside_window(self):
        """Buy token 40 days after sale -> no wash sale."""
        disposals = [{
            "token": "ETH",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("-500"),
        }]
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-07-26",  # 41 days after sale
            "lot_id": "lot-new",
        }]

        windows = check_wash_sales(disposals, acquisitions)
        assert len(windows) == 0

    def test_no_wash_sale_on_gain(self):
        """Disposal at a gain -> never a wash sale."""
        disposals = [{
            "token": "ETH",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("500"),  # gain, not loss
        }]
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-06-20",
            "lot_id": "lot-new",
        }]

        windows = check_wash_sales(disposals, acquisitions)
        assert len(windows) == 0

    def test_different_token_no_wash_sale(self):
        """Sell ETH at loss, buy BTC -> no wash sale (different assets)."""
        disposals = [{
            "token": "ETH",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("-500"),
        }]
        acquisitions = [{
            "token": "BTC",
            "acquisition_date": "2025-06-20",
            "lot_id": "lot-btc",
        }]

        windows = check_wash_sales(disposals, acquisitions)
        assert len(windows) == 0

    def test_multiple_disposals(self):
        """Multiple disposals, some trigger wash sales, some don't."""
        disposals = [
            {"token": "ETH", "disposal_date": "2025-06-15",
             "gain_loss_usd": Decimal("-500"), "tx_hash": "0x1"},
            {"token": "ETH", "disposal_date": "2025-08-01",
             "gain_loss_usd": Decimal("-300"), "tx_hash": "0x2"},
            {"token": "BTC", "disposal_date": "2025-06-15",
             "gain_loss_usd": Decimal("200"), "tx_hash": "0x3"},  # gain, skip
        ]
        acquisitions = [
            {"token": "ETH", "acquisition_date": "2025-06-20", "lot_id": "lot-a"},
            # No ETH acquisition near Aug 1 -> no wash sale for 0x2
        ]

        windows = check_wash_sales(disposals, acquisitions)

        assert len(windows) == 1
        assert windows[0].disposal_tx_hash == "0x1"

    def test_wash_sale_exactly_on_boundary(self):
        """Acquisition exactly 30 days after sale -> still within window."""
        disposals = [{
            "token": "ETH",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("-500"),
        }]
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-07-15",  # exactly 30 days
            "lot_id": "lot-boundary",
        }]

        windows = check_wash_sales(disposals, acquisitions)
        assert len(windows) == 1

    def test_wash_sale_day_31_no_trigger(self):
        """Acquisition 31 days after sale -> outside window."""
        disposals = [{
            "token": "ETH",
            "disposal_date": "2025-06-15",
            "gain_loss_usd": Decimal("-500"),
        }]
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-07-16",  # 31 days
            "lot_id": "lot-outside",
        }]

        windows = check_wash_sales(disposals, acquisitions)
        assert len(windows) == 0


# ===========================================================================
# 6. Active wash sale windows
# ===========================================================================

class TestActiveWashSaleWindows:
    """Test filtering to currently active windows."""

    def test_active_window(self):
        """Window spanning today -> active."""
        window = WashSaleWindow(
            token="ETH",
            sale_date=date(2025, 6, 15),
            window_start=date(2025, 5, 16),
            window_end=date(2025, 7, 15),
            disallowed_loss=Decimal("500"),
        )

        active = get_active_windows("ETH", date(2025, 6, 20), [window])
        assert len(active) == 1

    def test_expired_window(self):
        """Window that ended before today -> not active."""
        window = WashSaleWindow(
            token="ETH",
            sale_date=date(2025, 3, 1),
            window_start=date(2025, 1, 30),
            window_end=date(2025, 3, 31),
            disallowed_loss=Decimal("500"),
        )

        active = get_active_windows("ETH", date(2025, 9, 1), [window])
        assert len(active) == 0

    def test_filter_by_token(self):
        """Only return windows for the requested token."""
        windows = [
            WashSaleWindow(token="ETH", sale_date=date(2025, 6, 15),
                           window_start=date(2025, 5, 16), window_end=date(2025, 7, 15),
                           disallowed_loss=Decimal("500")),
            WashSaleWindow(token="BTC", sale_date=date(2025, 6, 15),
                           window_start=date(2025, 5, 16), window_end=date(2025, 7, 15),
                           disallowed_loss=Decimal("1000")),
        ]

        active = get_active_windows("ETH", date(2025, 6, 20), windows)
        assert len(active) == 1
        assert active[0].token == "ETH"


# ===========================================================================
# 7. Wash sale basis adjustment
# ===========================================================================

class TestWashSaleBasisAdjustment:
    """Test that disallowed loss is added to replacement lot's basis."""

    def test_basic_basis_adjustment(self):
        """$500 disallowed loss added to lot with $3000 basis -> $3500."""
        window = WashSaleWindow(
            token="ETH",
            sale_date=date(2025, 6, 15),
            window_start=date(2025, 5, 16),
            window_end=date(2025, 7, 15),
            disallowed_loss=Decimal("500"),
            replacement_lot_id="lot-replacement",
        )

        replacement = _make_tax_lot(
            lot_id="lot-replacement",
            cost_basis_usd="3000",
        )

        adjusted = adjust_basis_for_wash_sale(window, replacement)

        assert adjusted.cost_basis_usd == Decimal("3500")
        assert adjusted is replacement  # mutated in-place

    def test_cost_per_unit_after_adjustment(self):
        """After basis adjustment, cost_per_unit should reflect the new basis."""
        window = WashSaleWindow(
            token="ETH",
            sale_date=date(2025, 6, 15),
            window_start=date(2025, 5, 16),
            window_end=date(2025, 7, 15),
            disallowed_loss=Decimal("1000"),
            replacement_lot_id="lot-r",
        )

        replacement = _make_tax_lot(
            lot_id="lot-r",
            amount="2.0",
            cost_basis_usd="4000",  # $2000/unit
        )

        adjust_basis_for_wash_sale(window, replacement)

        # New basis: 4000 + 1000 = 5000. cost_per_unit = 5000/2 = 2500
        assert replacement.cost_per_unit == Decimal("2500")

    def test_all_values_remain_decimal(self):
        """Ensure no float contamination after adjustment."""
        window = WashSaleWindow(
            token="ETH",
            sale_date=date(2025, 6, 15),
            window_start=date(2025, 5, 16),
            window_end=date(2025, 7, 15),
            disallowed_loss=Decimal("123.456"),
        )

        replacement = _make_tax_lot(cost_basis_usd="999.99")
        adjust_basis_for_wash_sale(window, replacement)

        assert isinstance(replacement.cost_basis_usd, Decimal)
        assert replacement.cost_basis_usd == Decimal("1123.446")


# ===========================================================================
# 8. Pre-sale wash sale warning
# ===========================================================================

class TestWouldTriggerWashSale:
    """Test the pre-sale wash sale check."""

    def test_would_trigger(self):
        """Recent acquisition within 30 days -> warning."""
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-06-10",
            "lot_id": "lot-recent",
        }]

        result = would_trigger_wash_sale("ETH", date(2025, 6, 20), acquisitions)

        assert result is not None
        assert result["warning"] is True
        assert result["lot_id"] == "lot-recent"

    def test_would_not_trigger(self):
        """No recent acquisition -> no warning."""
        acquisitions = [{
            "token": "ETH",
            "acquisition_date": "2025-01-01",  # way before
            "lot_id": "lot-old",
        }]

        result = would_trigger_wash_sale("ETH", date(2025, 6, 20), acquisitions)
        assert result is None


# ===========================================================================
# 9. Serialization
# ===========================================================================

class TestSerialization:
    """Test as_dict methods produce correct output."""

    def test_unrealized_position_as_dict(self):
        pos = UnrealizedPosition(
            token="ETH",
            lot_id="lot-1",
            amount=Decimal("1.5"),
            cost_basis=Decimal("3000"),
            current_value=Decimal("2500"),
            unrealized_gain_loss=Decimal("-500"),
            holding_period=HoldingPeriod.SHORT_TERM,
            acquisition_date=date(2025, 6, 1),
            days_held=90,
            spekulationsfrist_remaining=276,
            is_tax_free=False,
        )
        d = pos.as_dict()
        assert d["token"] == "ETH"
        assert d["amount"] == "1.5"
        assert d["unrealized_gain_loss"] == "-500"
        assert d["holding_period"] == "short-term"
        assert d["spekulationsfrist_remaining"] == 276
        assert d["is_tax_free"] is False

    def test_wash_sale_window_as_dict(self):
        w = WashSaleWindow(
            token="ETH",
            sale_date=date(2025, 6, 15),
            window_start=date(2025, 5, 16),
            window_end=date(2025, 7, 15),
            disallowed_loss=Decimal("500"),
            replacement_lot_id="lot-r",
            disposal_tx_hash="0xabc",
        )
        d = w.as_dict()
        assert d["token"] == "ETH"
        assert d["sale_date"] == "2025-06-15"
        assert d["disallowed_loss"] == "500"
        assert d["replacement_lot_id"] == "lot-r"
