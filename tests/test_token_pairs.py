"""
Tests for token equivalence mapping and rebasing token detection.

Covers:
- Wrapped ETH equivalence (WETH, stETH, cbETH, rETH)
- Wrapped BTC equivalence (WBTC, tBTC, renBTC)
- Wrapped MATIC equivalence
- Stablecoin bridge equivalence (USDC.e -> USDC)
- Non-equivalent tokens
- Rebasing token detection
- canonical_symbol function
"""
from __future__ import annotations

import pytest

from src.data.token_pairs import (
    EQUIVALENT_TOKENS,
    REBASING_TOKENS,
    canonical_symbol,
    is_equivalent,
    is_rebasing_token,
)


class TestCanonicalSymbol:
    """Test canonical_symbol mapping."""

    def test_weth_to_eth(self) -> None:
        assert canonical_symbol("WETH") == "ETH"

    def test_steth_to_eth(self) -> None:
        assert canonical_symbol("stETH") == "ETH"

    def test_cbeth_to_eth(self) -> None:
        assert canonical_symbol("cbETH") == "ETH"

    def test_reth_to_eth(self) -> None:
        assert canonical_symbol("rETH") == "ETH"

    def test_wbtc_to_btc(self) -> None:
        assert canonical_symbol("WBTC") == "BTC"

    def test_plain_eth_stays_eth(self) -> None:
        assert canonical_symbol("ETH") == "ETH"

    def test_usdc_stays_usdc(self) -> None:
        assert canonical_symbol("USDC") == "USDC"

    def test_usdc_e_to_usdc(self) -> None:
        assert canonical_symbol("USDC.E") == "USDC"

    def test_wmatic_to_matic(self) -> None:
        assert canonical_symbol("WMATIC") == "MATIC"

    def test_case_insensitive(self) -> None:
        assert canonical_symbol("weth") == "ETH"
        assert canonical_symbol("Wbtc") == "BTC"


class TestIsEquivalent:
    """Test is_equivalent function."""

    def test_weth_eth(self) -> None:
        assert is_equivalent("WETH", "ETH") is True

    def test_steth_eth(self) -> None:
        assert is_equivalent("stETH", "ETH") is True

    def test_steth_weth(self) -> None:
        """stETH and WETH both map to ETH."""
        assert is_equivalent("stETH", "WETH") is True

    def test_wbtc_btc(self) -> None:
        assert is_equivalent("WBTC", "BTC") is True

    def test_usdc_e_usdc(self) -> None:
        assert is_equivalent("USDC.E", "USDC") is True

    def test_eth_btc_not_equivalent(self) -> None:
        assert is_equivalent("ETH", "BTC") is False

    def test_usdc_usdt_not_equivalent(self) -> None:
        assert is_equivalent("USDC", "USDT") is False

    def test_same_token(self) -> None:
        assert is_equivalent("ETH", "ETH") is True
        assert is_equivalent("USDC", "USDC") is True

    def test_sol_variants(self) -> None:
        assert is_equivalent("MSOL", "SOL") is True
        assert is_equivalent("JITOSOL", "SOL") is True
        assert is_equivalent("MSOL", "JITOSOL") is True


class TestIsRebasingToken:
    """Test rebasing token detection."""

    def test_steth_is_rebasing(self) -> None:
        assert is_rebasing_token("stETH") is True

    def test_aave_atokens_are_rebasing(self) -> None:
        assert is_rebasing_token("aUSDC") is True
        assert is_rebasing_token("aDAI") is True

    def test_weth_is_not_rebasing(self) -> None:
        assert is_rebasing_token("WETH") is False

    def test_eth_is_not_rebasing(self) -> None:
        assert is_rebasing_token("ETH") is False

    def test_cbeth_is_not_rebasing(self) -> None:
        """cbETH appreciates in exchange rate, it does NOT rebase."""
        assert is_rebasing_token("cbETH") is False

    def test_case_insensitive(self) -> None:
        assert is_rebasing_token("steth") is True
