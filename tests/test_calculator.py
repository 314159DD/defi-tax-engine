"""
Calculator unit tests.

Covers:
- FIFO / LIFO / HIFO lot selection with exact Decimal results
- DeFi scenarios: LP add/remove, staking rewards, bridge carry-over
- Gas fee attribution (cost basis adjustment, proceeds deduction)
- Holding period classification (short-term < 1 year, long-term >= 1 year)
- compare_methods helper
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.calculator.engine import CalculatorEngine, compare_methods
from src.calculator.lots import Disposal, LotManager, TaxLot, holding_period
from src.importers.models import AssetTransfer, Transaction
from tests.conftest import make_transfer, make_tx


# ── Helpers ────────────────────────────────────────────────────────────────────

def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _swap_tx(
    tx_hash: str,
    ts: datetime,
    out_symbol: str,
    out_amount: str,
    out_usd: str,
    in_symbol: str,
    in_amount: str,
    in_usd: str,
    fee: AssetTransfer | None = None,
) -> Transaction:
    return make_tx(
        tx_hash=tx_hash,
        timestamp=ts,
        tx_type="swap",
        assets_out=[make_transfer(out_symbol, out_amount, out_usd)],
        assets_in=[make_transfer(in_symbol, in_amount, in_usd)],
        fee=fee,
    )


# ── FIFO basic ─────────────────────────────────────────────────────────────────

class TestFIFO:
    """FIFO should consume the oldest lots first."""

    def test_single_lot_full_consumption(self):
        """Buy 2 ETH, sell 2 ETH → gain = proceeds - cost."""
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "4000", "4000", "ETH", "2", "4000"),
            _swap_tx("sell1", _dt(2025, 3, 1), "ETH", "2", "5000", "USDC", "5000", "5000"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        assert d.token == "ETH"
        assert d.amount == Decimal("2")
        assert d.proceeds_usd == Decimal("5000")
        assert d.cost_basis_usd == Decimal("4000")
        assert d.gain_loss_usd == Decimal("1000")
        assert d.method == "FIFO"

    def test_fifo_consumes_oldest_first(self):
        """Two buys at different prices; FIFO uses the first (cheaper) lot."""
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "1000", "1000", "ETH", "1", "1000"),
            _swap_tx("buy2", _dt(2025, 2, 1), "USDC", "3000", "3000", "ETH", "1", "3000"),
            _swap_tx("sell1", _dt(2025, 4, 1), "ETH", "1", "2500", "USDC", "2500", "2500"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        # FIFO: oldest lot ($1000 cost) consumed first
        assert d.cost_basis_usd == Decimal("1000")
        assert d.gain_loss_usd == Decimal("1500")  # 2500 - 1000

    def test_partial_lot_consumption(self):
        """Buy 3 ETH, sell 1 → partial lot consumption."""
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "6000", "6000", "ETH", "3", "6000"),
            _swap_tx("sell1", _dt(2025, 3, 1), "ETH", "1", "2500", "USDC", "2500", "2500"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        assert d.amount == Decimal("1")
        # Cost basis = 1/3 of 6000 = 2000
        assert d.cost_basis_usd == Decimal("2000")
        assert d.gain_loss_usd == Decimal("500")


# ── LIFO ───────────────────────────────────────────────────────────────────────

class TestLIFO:
    """LIFO should consume the newest lots first."""

    def test_lifo_consumes_newest_first(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "1000", "1000", "ETH", "1", "1000"),
            _swap_tx("buy2", _dt(2025, 2, 1), "USDC", "3000", "3000", "ETH", "1", "3000"),
            _swap_tx("sell1", _dt(2025, 4, 1), "ETH", "1", "2500", "USDC", "2500", "2500"),
        ]
        engine = CalculatorEngine("LIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        # LIFO: newest lot ($3000 cost) consumed first
        assert d.cost_basis_usd == Decimal("3000")
        assert d.gain_loss_usd == Decimal("-500")  # 2500 - 3000 = loss


# ── HIFO ───────────────────────────────────────────────────────────────────────

class TestHIFO:
    """HIFO should consume the highest-cost lots first."""

    def test_hifo_consumes_highest_cost_first(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "1000", "1000", "ETH", "1", "1000"),
            _swap_tx("buy2", _dt(2025, 2, 1), "USDC", "3000", "3000", "ETH", "1", "3000"),
            _swap_tx("buy3", _dt(2025, 3, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            _swap_tx("sell1", _dt(2025, 5, 1), "ETH", "1", "2500", "USDC", "2500", "2500"),
        ]
        engine = CalculatorEngine("HIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        # HIFO: highest per-unit cost ($3000) consumed first
        assert d.cost_basis_usd == Decimal("3000")
        assert d.gain_loss_usd == Decimal("-500")

    def test_hifo_minimizes_gain(self):
        """HIFO should produce less gain than FIFO for appreciating assets."""
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "1000", "1000", "ETH", "1", "1000"),
            _swap_tx("buy2", _dt(2025, 2, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            _swap_tx("sell1", _dt(2025, 5, 1), "ETH", "1", "3000", "USDC", "3000", "3000"),
        ]
        fifo_d = CalculatorEngine("FIFO").calculate(txs)
        hifo_d = CalculatorEngine("HIFO").calculate(txs)

        assert hifo_d[0].gain_loss_usd < fifo_d[0].gain_loss_usd


# ── Gas fee attribution ────────────────────────────────────────────────────────

class TestGasFees:
    """Gas fees: added to cost basis on acquisition, deducted from proceeds on disposal."""

    def test_gas_on_swap_reduces_proceeds(self):
        """When selling via a swap, gas reduces proceeds.

        Gas token (MATIC) differs from asset_out (SOL) so the disposal is not
        skipped by the _is_gas_token_for_fee guard.
        """
        fee = make_transfer("MATIC", "10", "25")  # gas in a different token
        txs = [
            make_tx(
                tx_hash="acquire1",
                timestamp=_dt(2025, 1, 1),
                tx_type="reward",
                assets_in=[make_transfer("SOL", "10", "2000")],
            ),
            make_tx(
                tx_hash="sell1",
                timestamp=_dt(2025, 3, 1),
                tx_type="swap",
                assets_out=[make_transfer("SOL", "10", "3000")],
                assets_in=[make_transfer("USDC", "3000", "3000")],
                fee=fee,
            ),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        # Proceeds should be 3000 - 25 (gas) = 2975
        assert d.proceeds_usd == Decimal("2975")
        assert d.gain_loss_usd == Decimal("975")  # 2975 - 2000

    def test_gas_on_buy_adds_to_cost_basis(self):
        """When acquiring via a swap, gas is added to cost basis of acquired token."""
        fee = make_transfer("ETH", "0.01", "25")
        txs = [
            make_tx(
                tx_hash="buy1",
                timestamp=_dt(2025, 1, 1),
                tx_type="swap",
                assets_out=[make_transfer("USDC", "2000", "2000")],
                assets_in=[make_transfer("ETH", "1", "2000")],
                fee=fee,
            ),
            _swap_tx("sell1", _dt(2025, 3, 1), "ETH", "1", "3000", "USDC", "3000", "3000"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        # Cost basis should be 2000 + 25 (gas) = 2025
        assert d.cost_basis_usd == Decimal("2025")
        assert d.gain_loss_usd == Decimal("975")  # 3000 - 2025


# ── Holding period ─────────────────────────────────────────────────────────────

class TestHoldingPeriod:
    """Held > 365 days = long-term, <= 365 days = short-term."""

    def test_short_term(self):
        hp = holding_period(_dt(2025, 1, 1), _dt(2025, 6, 1))
        assert hp == "short-term"

    def test_long_term(self):
        hp = holding_period(_dt(2024, 1, 1), _dt(2025, 6, 1))
        assert hp == "long-term"

    def test_exactly_365_days_is_short_term(self):
        hp = holding_period(_dt(2025, 1, 1), _dt(2026, 1, 1))
        assert hp == "short-term"

    def test_366_days_is_long_term(self):
        hp = holding_period(_dt(2025, 1, 1), _dt(2026, 1, 2))
        assert hp == "long-term"

    def test_disposal_marks_short_term(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            _swap_tx("sell1", _dt(2025, 6, 1), "ETH", "1", "3000", "USDC", "3000", "3000"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)
        assert disposals[0].holding_period == "short-term"

    def test_disposal_marks_long_term(self):
        txs = [
            _swap_tx("buy1", _dt(2024, 1, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            _swap_tx("sell1", _dt(2025, 6, 1), "ETH", "1", "3000", "USDC", "3000", "3000"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)
        assert disposals[0].holding_period == "long-term"


# ── DeFi: LP add/remove ───────────────────────────────────────────────────────

class TestLPScenarios:
    """LP add: cost basis = sum of deposited tokens.
    LP remove: dispose of LP token, gain/loss calculated."""

    def test_lp_add_creates_lot_with_combined_basis(self):
        txs = [
            # First acquire the tokens
            _swap_tx("buy_eth", _dt(2025, 1, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            _swap_tx("buy_usdc", _dt(2025, 1, 2), "DAI", "2000", "2000", "USDC", "2000", "2000"),
            # Then add to LP
            make_tx(
                tx_hash="lp_add",
                timestamp=_dt(2025, 2, 1),
                tx_type="lp_add",
                assets_out=[
                    make_transfer("ETH", "1", "2000"),
                    make_transfer("USDC", "2000", "2000"),
                ],
                assets_in=[make_transfer("UNI-V2", "100", "4000")],
            ),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)
        # lp_add should NOT create a disposal
        assert len(disposals) == 0

    def test_lp_remove_creates_disposal(self):
        txs = [
            # Acquire LP token via lp_add
            make_tx(
                tx_hash="lp_add",
                timestamp=_dt(2025, 1, 1),
                tx_type="lp_add",
                assets_out=[
                    make_transfer("ETH", "1", "2000"),
                    make_transfer("USDC", "2000", "2000"),
                ],
                assets_in=[make_transfer("UNI-V2", "100", "4000")],
            ),
            # Remove LP
            make_tx(
                tx_hash="lp_remove",
                timestamp=_dt(2025, 6, 1),
                tx_type="lp_remove",
                assets_out=[make_transfer("UNI-V2", "100", "5000")],
                assets_in=[
                    make_transfer("ETH", "1.1", "2750"),
                    make_transfer("USDC", "2250", "2250"),
                ],
            ),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        assert d.token == "UNI-V2"
        assert d.amount == Decimal("100")
        # Cost basis from lp_add = 4000 (ETH 2000 + USDC 2000)
        assert d.cost_basis_usd == Decimal("4000")
        assert d.proceeds_usd == Decimal("5000")
        assert d.gain_loss_usd == Decimal("1000")


# ── DeFi: staking reward cost basis ───────────────────────────────────────────

class TestStakingRewards:
    """Staking rewards are income; cost basis = FMV at receipt."""

    def test_reward_creates_lot_at_fmv(self):
        txs = [
            make_tx(
                tx_hash="reward1",
                timestamp=_dt(2025, 3, 1),
                tx_type="reward",
                assets_in=[make_transfer("LDO", "50", "100")],
            ),
            _swap_tx("sell_ldo", _dt(2025, 6, 1), "LDO", "50", "200", "USDC", "200", "200"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        assert d.token == "LDO"
        # Cost basis = FMV at reward time = $100
        assert d.cost_basis_usd == Decimal("100")
        assert d.gain_loss_usd == Decimal("100")  # 200 - 100

    def test_airdrop_creates_lot_at_fmv(self):
        txs = [
            make_tx(
                tx_hash="airdrop1",
                timestamp=_dt(2025, 1, 15),
                tx_type="airdrop",
                assets_in=[make_transfer("ARB", "1000", "1200")],
            ),
            _swap_tx("sell_arb", _dt(2025, 6, 1), "ARB", "500", "800", "USDC", "800", "800"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)

        assert len(disposals) == 1
        d = disposals[0]
        # Cost basis for 500 out of 1000 airdropped = $600 (1200 * 500/1000)
        assert d.cost_basis_usd == Decimal("600")
        assert d.gain_loss_usd == Decimal("200")


# ── Bridge / self-transfer cost carry-over ─────────────────────────────────────

class TestBridgeAndTransfer:
    """Bridges and self-transfers should produce zero disposals."""

    def test_bridge_produces_no_disposal(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            make_tx(
                tx_hash="bridge1",
                timestamp=_dt(2025, 2, 1),
                tx_type="bridge",
                assets_out=[make_transfer("ETH", "1", "2500")],
            ),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)
        assert len(disposals) == 0

    def test_self_transfer_produces_no_disposal(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            make_tx(
                tx_hash="transfer1",
                timestamp=_dt(2025, 2, 1),
                tx_type="transfer",
                from_address="0xwallet1",
                to_address="0xwallet2",
                assets_out=[make_transfer("ETH", "1", "2500")],
            ),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs, known_wallets={"0xwallet1", "0xwallet2"})
        assert len(disposals) == 0


# ── Year filtering ─────────────────────────────────────────────────────────────

class TestYearFiltering:
    def test_filter_disposals_by_year(self):
        txs = [
            _swap_tx("buy1", _dt(2024, 1, 1), "USDC", "2000", "2000", "ETH", "2", "2000"),
            _swap_tx("sell1", _dt(2024, 6, 1), "ETH", "1", "1500", "USDC", "1500", "1500"),
            _swap_tx("sell2", _dt(2025, 6, 1), "ETH", "1", "2500", "USDC", "2500", "2500"),
        ]
        engine = CalculatorEngine("FIFO")

        d_2024 = engine.calculate(txs, year=2024)
        d_2025 = engine.calculate(txs, year=2025)

        assert len(d_2024) == 1
        assert d_2024[0].date.year == 2024
        assert len(d_2025) == 1
        assert d_2025[0].date.year == 2025


# ── compare_methods ────────────────────────────────────────────────────────────

class TestCompare:
    def test_compare_returns_all_three_methods(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "1000", "1000", "ETH", "1", "1000"),
            _swap_tx("buy2", _dt(2025, 2, 1), "USDC", "3000", "3000", "ETH", "1", "3000"),
            _swap_tx("sell1", _dt(2025, 5, 1), "ETH", "1", "2500", "USDC", "2500", "2500"),
        ]
        comp = compare_methods(txs, year=2025)

        assert comp.fifo_disposals == 1
        assert comp.lifo_disposals == 1
        assert comp.hifo_disposals == 1
        # FIFO uses $1000 cost → gain $1500
        assert comp.fifo_gain == Decimal("1500")
        # LIFO uses $3000 cost → loss $500
        assert comp.lifo_gain == Decimal("-500")
        # HIFO uses $3000 cost → loss $500
        assert comp.hifo_gain == Decimal("-500")


# ── Decimal enforcement ────────────────────────────────────────────────────────

class TestDecimalEnforcement:
    """All monetary values must be Decimal, never float."""

    def test_tax_lot_rejects_float(self):
        with pytest.raises(TypeError, match="must be Decimal"):
            TaxLot(
                id="test",
                token="ETH",
                amount=1.0,  # type: ignore  # float!
                cost_basis_usd=Decimal("2000"),
                acquisition_date=_dt(2025, 1, 1),
                remaining=Decimal("1"),
                source="test",
                tx_hash="0x",
            )

    def test_disposal_rejects_float(self):
        with pytest.raises(TypeError, match="must be Decimal"):
            Disposal(
                date=_dt(2025, 1, 1),
                token="ETH",
                amount=1.0,  # type: ignore  # float!
                proceeds_usd=Decimal("3000"),
                cost_basis_usd=Decimal("2000"),
                gain_loss_usd=Decimal("1000"),
                holding_period="short-term",
                method="FIFO",
                lots_consumed=[],
                tx_hash="0x",
            )

    def test_engine_output_is_all_decimal(self):
        txs = [
            _swap_tx("buy1", _dt(2025, 1, 1), "USDC", "2000", "2000", "ETH", "1", "2000"),
            _swap_tx("sell1", _dt(2025, 3, 1), "ETH", "1", "3000", "USDC", "3000", "3000"),
        ]
        engine = CalculatorEngine("FIFO")
        disposals = engine.calculate(txs)
        for d in disposals:
            assert isinstance(d.amount, Decimal), f"amount is {type(d.amount)}"
            assert isinstance(d.proceeds_usd, Decimal), f"proceeds is {type(d.proceeds_usd)}"
            assert isinstance(d.cost_basis_usd, Decimal), f"cost_basis is {type(d.cost_basis_usd)}"
            assert isinstance(d.gain_loss_usd, Decimal), f"gain_loss is {type(d.gain_loss_usd)}"


# ── Invalid method ─────────────────────────────────────────────────────────────

class TestInvalidMethod:
    def test_rejects_unknown_method(self):
        with pytest.raises(ValueError, match="Unknown method"):
            CalculatorEngine("AVERAGE")
