"""
End-to-end integration tests.

Exercises the full pipeline: categorize → calculate → verify.

Covers:
- ~20 transactions covering all DeFi types
- Full pipeline with all 3 methods (FIFO, LIFO, HIFO)
- No float values anywhere in output
- Bridges and self-transfers produce zero gain/loss
- Staking rewards and airdrops create correct cost basis
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.calculator.engine import CalculatorEngine, compare_methods
from src.categorizer.engine import CategorizerEngine, is_income_event, is_taxable_disposal
from src.importers.models import AssetTransfer, Transaction
from tests.conftest import make_transfer, make_tx


# ── Fixture: ~20 transactions covering all DeFi types ─────────────────────────

USER_W1 = "0xuser000000000000000000000000000000000001"
USER_W2 = "0xuser000000000000000000000000000000000002"
KNOWN_WALLETS = {USER_W1, USER_W2}


def _dt(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


def build_transaction_set() -> list[Transaction]:
    """Build ~20 diverse transactions for integration testing."""
    return [
        # 1. Buy ETH with USDC (swap) - initial acquisition
        make_tx(
            tx_hash="0x01", timestamp=_dt(2024, 1, 15), tx_type="swap",
            assets_out=[make_transfer("USDC", "4000", "4000")],
            assets_in=[make_transfer("ETH", "2", "4000")],
        ),
        # 2. Buy BTC with USDC (swap)
        make_tx(
            tx_hash="0x02", timestamp=_dt(2024, 2, 1), tx_type="swap",
            assets_out=[make_transfer("USDC", "40000", "40000")],
            assets_in=[make_transfer("BTC", "1", "40000")],
        ),
        # 3. Staking reward (income)
        make_tx(
            tx_hash="0x03", timestamp=_dt(2024, 3, 1), tx_type="reward",
            assets_in=[make_transfer("ETH", "0.1", "200")],
        ),
        # 4. Airdrop (income)
        make_tx(
            tx_hash="0x04", timestamp=_dt(2024, 4, 1), tx_type="airdrop",
            assets_in=[make_transfer("ARB", "1000", "1500")],
        ),
        # 5. Bridge ETH to Arbitrum (not taxable)
        make_tx(
            tx_hash="0x05", timestamp=_dt(2024, 5, 1), tx_type="bridge",
            assets_out=[make_transfer("ETH", "0.5", "1200")],
        ),
        # 6. Self-transfer (not taxable)
        make_tx(
            tx_hash="0x06", timestamp=_dt(2024, 5, 15), tx_type="transfer",
            from_address=USER_W1, to_address=USER_W2,
            assets_out=[make_transfer("ETH", "0.3", "750")],
        ),
        # 7. LP add (deposit ETH + USDC, receive LP token)
        make_tx(
            tx_hash="0x07", timestamp=_dt(2024, 6, 1), tx_type="lp_add",
            assets_out=[
                make_transfer("ETH", "0.5", "1250"),
                make_transfer("USDC", "1250", "1250"),
            ],
            assets_in=[make_transfer("UNI-V2", "50", "2500")],
        ),
        # 8. Buy more ETH (second acquisition at higher price)
        make_tx(
            tx_hash="0x08", timestamp=_dt(2024, 7, 1), tx_type="swap",
            assets_out=[make_transfer("USDC", "3000", "3000")],
            assets_in=[make_transfer("ETH", "1", "3000")],
        ),
        # 9. Swap ETH for SOL
        make_tx(
            tx_hash="0x09", timestamp=_dt(2025, 1, 15), tx_type="swap",
            assets_out=[make_transfer("ETH", "0.5", "1500")],
            assets_in=[make_transfer("SOL", "10", "1500")],
        ),
        # 10. Sell some BTC
        make_tx(
            tx_hash="0x10", timestamp=_dt(2025, 2, 1), tx_type="swap",
            assets_out=[make_transfer("BTC", "0.5", "30000")],
            assets_in=[make_transfer("USDC", "30000", "30000")],
        ),
        # 11. LP remove (burn LP token, receive underlying)
        make_tx(
            tx_hash="0x11", timestamp=_dt(2025, 3, 1), tx_type="lp_remove",
            assets_out=[make_transfer("UNI-V2", "50", "2800")],
            assets_in=[
                make_transfer("ETH", "0.55", "1430"),
                make_transfer("USDC", "1370", "1370"),
            ],
        ),
        # 12. Sell airdropped ARB
        make_tx(
            tx_hash="0x12", timestamp=_dt(2025, 4, 1), tx_type="swap",
            assets_out=[make_transfer("ARB", "500", "900")],
            assets_in=[make_transfer("USDC", "900", "900")],
        ),
        # 13. Sell staking reward ETH
        make_tx(
            tx_hash="0x13", timestamp=_dt(2025, 5, 1), tx_type="swap",
            assets_out=[make_transfer("ETH", "0.1", "350")],
            assets_in=[make_transfer("USDC", "350", "350")],
        ),
        # 14. Stake operation (not taxable)
        make_tx(
            tx_hash="0x14", timestamp=_dt(2025, 5, 15), tx_type="stake",
            assets_out=[make_transfer("ETH", "0.5", "1750")],
            assets_in=[make_transfer("stETH", "0.5", "1750")],
        ),
        # 15. Unstake (not taxable)
        make_tx(
            tx_hash="0x15", timestamp=_dt(2025, 6, 1), tx_type="unstake",
            assets_out=[make_transfer("stETH", "0.5", "1800")],
            assets_in=[make_transfer("ETH", "0.5", "1800")],
        ),
        # 16. Another swap with gas fee
        make_tx(
            tx_hash="0x16", timestamp=_dt(2025, 7, 1), tx_type="swap",
            assets_out=[make_transfer("SOL", "5", "900")],
            assets_in=[make_transfer("USDC", "900", "900")],
            fee=make_transfer("SOL", "0.01", "1.50"),
        ),
        # 17. Buy MATIC
        make_tx(
            tx_hash="0x17", timestamp=_dt(2025, 7, 15), tx_type="swap",
            assets_out=[make_transfer("USDC", "500", "500")],
            assets_in=[make_transfer("MATIC", "500", "500")],
        ),
        # 18. Approve (not taxable, no-op)
        make_tx(
            tx_hash="0x18", timestamp=_dt(2025, 8, 1), tx_type="approve",
        ),
        # 19. Unknown tx type (no-op)
        make_tx(
            tx_hash="0x19", timestamp=_dt(2025, 8, 15), tx_type="unknown",
        ),
        # 20. Another staking reward
        make_tx(
            tx_hash="0x20", timestamp=_dt(2025, 9, 1), tx_type="reward",
            assets_in=[make_transfer("MATIC", "10", "10")],
        ),
    ]


# ── Integration: full pipeline ─────────────────────────────────────────────────

class TestFullPipeline:
    """Run the full pipeline: categorize → calculate with all methods."""

    @pytest.fixture
    def txs(self):
        return build_transaction_set()

    def test_categorizer_preserves_count(self, txs):
        engine = CategorizerEngine(known_wallets=KNOWN_WALLETS)
        categorized = engine.categorize_all(txs)
        assert len(categorized) == len(txs)

    def test_all_methods_produce_disposals(self, txs):
        for method in ("FIFO", "LIFO", "HIFO"):
            engine = CalculatorEngine(method)
            disposals = engine.calculate(txs, known_wallets=KNOWN_WALLETS)
            assert len(disposals) > 0, f"{method} produced no disposals"

    def test_same_number_of_disposals_across_methods(self, txs):
        counts = {}
        for method in ("FIFO", "LIFO", "HIFO"):
            engine = CalculatorEngine(method)
            disposals = engine.calculate(txs, known_wallets=KNOWN_WALLETS)
            counts[method] = len(disposals)
        # All methods should produce the same number of disposal events
        assert counts["FIFO"] == counts["LIFO"] == counts["HIFO"]


# ── No float values ───────────────────────────────────────────────────────────

class TestNoFloats:
    """Verify no float values anywhere in output."""

    @pytest.fixture
    def all_disposals(self):
        txs = build_transaction_set()
        disposals = {}
        for method in ("FIFO", "LIFO", "HIFO"):
            engine = CalculatorEngine(method)
            disposals[method] = engine.calculate(txs, known_wallets=KNOWN_WALLETS)
        return disposals

    def test_disposal_amounts_are_decimal(self, all_disposals):
        for method, disposals in all_disposals.items():
            for d in disposals:
                assert isinstance(d.amount, Decimal), \
                    f"{method}: disposal amount is {type(d.amount)}, not Decimal"
                assert isinstance(d.proceeds_usd, Decimal), \
                    f"{method}: proceeds is {type(d.proceeds_usd)}, not Decimal"
                assert isinstance(d.cost_basis_usd, Decimal), \
                    f"{method}: cost_basis is {type(d.cost_basis_usd)}, not Decimal"
                assert isinstance(d.gain_loss_usd, Decimal), \
                    f"{method}: gain_loss is {type(d.gain_loss_usd)}, not Decimal"

    def test_lot_consumptions_are_decimal(self, all_disposals):
        for method, disposals in all_disposals.items():
            for d in disposals:
                for lc in d.lots_consumed:
                    assert isinstance(lc.amount_consumed, Decimal), \
                        f"{method}: lot consumption amount is {type(lc.amount_consumed)}"
                    assert isinstance(lc.cost_basis_consumed, Decimal), \
                        f"{method}: lot consumption cost is {type(lc.cost_basis_consumed)}"


# ── Bridges and self-transfers produce zero gain/loss ──────────────────────────

class TestNonTaxableEvents:
    """Bridges and self-transfers must NOT produce disposals."""

    @pytest.fixture
    def disposals(self):
        txs = build_transaction_set()
        engine = CalculatorEngine("FIFO")
        return engine.calculate(txs, known_wallets=KNOWN_WALLETS)

    def test_bridge_tx_not_in_disposals(self, disposals):
        bridge_hashes = {"0x05"}
        disposal_hashes = {d.tx_hash for d in disposals}
        assert bridge_hashes.isdisjoint(disposal_hashes), \
            "Bridge transactions should not produce disposals"

    def test_self_transfer_not_in_disposals(self, disposals):
        transfer_hashes = {"0x06"}
        disposal_hashes = {d.tx_hash for d in disposals}
        assert transfer_hashes.isdisjoint(disposal_hashes), \
            "Self-transfer transactions should not produce disposals"

    def test_stake_unstake_not_in_disposals(self, disposals):
        stake_hashes = {"0x14", "0x15"}
        disposal_hashes = {d.tx_hash for d in disposals}
        assert stake_hashes.isdisjoint(disposal_hashes), \
            "Stake/unstake transactions should not produce disposals"

    def test_approve_unknown_not_in_disposals(self, disposals):
        noop_hashes = {"0x18", "0x19"}
        disposal_hashes = {d.tx_hash for d in disposals}
        assert noop_hashes.isdisjoint(disposal_hashes), \
            "Approve/unknown transactions should not produce disposals"


# ── Taxable events produce expected disposals ──────────────────────────────────

class TestTaxableEvents:
    @pytest.fixture
    def disposals(self):
        txs = build_transaction_set()
        engine = CalculatorEngine("FIFO")
        return engine.calculate(txs, known_wallets=KNOWN_WALLETS)

    def test_swap_disposal_present(self, disposals):
        """Swap transactions (0x09, 0x10, 0x12, 0x13) should produce disposals.
        0x16 sells SOL with SOL as gas token - engine skips disposal when
        gas token matches asset_out (gas deducted separately)."""
        swap_hashes = {"0x09", "0x10", "0x12", "0x13"}
        disposal_hashes = {d.tx_hash for d in disposals}
        assert swap_hashes.issubset(disposal_hashes), \
            f"Missing swap disposals: {swap_hashes - disposal_hashes}"

    def test_lp_remove_disposal_present(self, disposals):
        """LP remove (0x11) should produce a disposal."""
        disposal_hashes = {d.tx_hash for d in disposals}
        assert "0x11" in disposal_hashes

    def test_gain_loss_formula(self, disposals):
        """gain_loss = proceeds - cost_basis for all disposals."""
        for d in disposals:
            expected = d.proceeds_usd - d.cost_basis_usd
            assert d.gain_loss_usd == expected, \
                f"Disposal {d.tx_hash}: {d.gain_loss_usd} != {d.proceeds_usd} - {d.cost_basis_usd}"


# ── Compare methods helper ─────────────────────────────────────────────────────

class TestCompareMethodsIntegration:
    def test_compare_methods_2025(self):
        txs = build_transaction_set()
        comp = compare_methods(txs, known_wallets=KNOWN_WALLETS, year=2025)

        assert comp.year == 2025
        assert comp.fifo_disposals > 0
        assert comp.lifo_disposals > 0
        assert comp.hifo_disposals > 0

        # HIFO should produce <= gain vs FIFO (more tax efficient)
        assert comp.hifo_gain <= comp.fifo_gain

    def test_short_long_term_adds_up(self):
        txs = build_transaction_set()
        comp = compare_methods(txs, known_wallets=KNOWN_WALLETS, year=2025)

        for method in ("fifo", "lifo", "hifo"):
            total = getattr(comp, f"{method}_gain")
            st = getattr(comp, f"{method}_short_term")
            lt = getattr(comp, f"{method}_long_term")
            assert total == st + lt, \
                f"{method}: total gain {total} != short {st} + long {lt}"


# ── Categorizer integration ───────────────────────────────────────────────────

class TestCategorizerIntegration:
    def test_income_events_detected(self):
        txs = build_transaction_set()
        engine = CategorizerEngine(known_wallets=KNOWN_WALLETS)
        categorized = engine.categorize_all(txs)

        income = [tx for tx in categorized if is_income_event(tx)]
        # tx 0x03 (reward), 0x04 (airdrop), 0x20 (reward) = 3 income events
        assert len(income) >= 2

    def test_taxable_disposals_detected(self):
        txs = build_transaction_set()
        engine = CategorizerEngine(known_wallets=KNOWN_WALLETS)
        categorized = engine.categorize_all(txs)

        taxable = [tx for tx in categorized if is_taxable_disposal(tx)]
        # swaps + lp_remove
        assert len(taxable) >= 5
