"""
Tests for the transaction categorization engine.

Covers:
- Uniswap V2/V3 swap detection
- LP add/remove detection
- Staking reward / stake / unstake
- Bridge detection (no tax)
- Airdrop detection (income)
- Self-transfer detection (no tax)
- NFT buy/sell/mint
- Taxable / income helpers
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.categorizer.engine import (
    CategorizerEngine,
    categorize_transactions,
    is_income_event,
    is_taxable_disposal,
)
from src.categorizer.protocols import (
    LIDO_STETH,
    UNISWAP_V2_ROUTER,
    UNISWAP_V3_ROUTER,
    ARBITRUM_BRIDGE,
    OPENSEA_SEAPORT_V1_5,
)
from src.importers.models import AssetTransfer, Transaction

# ── Helpers ────────────────────────────────────────────────────────────────────

USER_WALLET  = "0xuser000000000000000000000000000000000001"
USER_WALLET2 = "0xuser000000000000000000000000000000000002"
KNOWN_WALLETS = {USER_WALLET, USER_WALLET2}
UNKNOWN_CONTRACT = "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"

_TS = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _t(
    tx_hash: str = "0xabc",
    chain: str = "ethereum",
    from_addr: str = USER_WALLET,
    to_addr: str = UNISWAP_V2_ROUTER,
    tx_type: str = "unknown",
    assets_in: list[AssetTransfer] | None = None,
    assets_out: list[AssetTransfer] | None = None,
    fee: AssetTransfer | None = None,
    protocol: str | None = None,
) -> Transaction:
    return Transaction(
        tx_hash=tx_hash,
        chain=chain,
        block_number=1,
        timestamp=_TS,
        from_address=from_addr.lower(),
        to_address=to_addr.lower(),
        tx_type=tx_type,
        assets_in=assets_in or [],
        assets_out=assets_out or [],
        fee=fee,
        protocol=protocol,
        raw_data={},
    )


def _a(symbol: str, amount: str = "1", addr: str | None = None) -> AssetTransfer:
    return AssetTransfer(
        token_symbol=symbol,
        amount=Decimal(amount),
        token_address=addr,
    )


engine = CategorizerEngine(known_wallets=KNOWN_WALLETS)


# ── Self-transfer ──────────────────────────────────────────────────────────────

class TestSelfTransfer:
    def test_own_to_own_wallet_is_transfer(self):
        tx = _t(from_addr=USER_WALLET, to_addr=USER_WALLET2,
                assets_out=[_a("ETH", "1")])
        result = engine.categorize(tx)
        assert result.tx_type == "transfer"

    def test_own_to_external_not_transfer(self):
        tx = _t(from_addr=USER_WALLET, to_addr=UNKNOWN_CONTRACT,
                assets_out=[_a("ETH", "1")])
        result = engine.categorize(tx)
        assert result.tx_type != "transfer"


# ── Bridge ────────────────────────────────────────────────────────────────────

class TestBridge:
    def test_arbitrum_bridge_detected(self):
        tx = _t(to_addr=ARBITRUM_BRIDGE,
                assets_out=[_a("ETH", "2")])
        result = engine.categorize(tx)
        assert result.tx_type == "bridge"
        assert result.protocol == "Arbitrum Bridge"

    def test_bridge_not_taxable(self):
        tx = _t(to_addr=ARBITRUM_BRIDGE,
                assets_out=[_a("ETH", "2")])
        result = engine.categorize(tx)
        assert not is_taxable_disposal(result)
        assert not is_income_event(result)


# ── Swap ──────────────────────────────────────────────────────────────────────

class TestSwap:
    def test_uniswap_v2_swap(self):
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("USDC", "1000")],
            assets_out=[_a("ETH", "0.5")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "swap"
        assert "Uniswap" in result.protocol

    def test_uniswap_v3_swap(self):
        tx = _t(
            to_addr=UNISWAP_V3_ROUTER,
            assets_in=[_a("DAI", "500")],
            assets_out=[_a("WBTC", "0.01")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "swap"

    def test_swap_is_taxable_disposal(self):
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("USDC", "1000")],
            assets_out=[_a("ETH", "0.5")],
        )
        result = engine.categorize(tx)
        assert is_taxable_disposal(result)

    def test_eth_to_weth_wrap_not_swap(self):
        """ETH → WETH is a wrap, not a taxable swap."""
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("WETH", "1")],
            assets_out=[_a("ETH", "1")],
        )
        result = engine.categorize(tx)
        # Should NOT be classified as swap (it's a wrap)
        assert result.tx_type != "swap"

    def test_swap_via_protocol_name(self):
        tx = _t(
            to_addr=UNKNOWN_CONTRACT,
            protocol="SushiSwap",
            assets_in=[_a("USDT", "200")],
            assets_out=[_a("ETH", "0.1")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "swap"


# ── LP ────────────────────────────────────────────────────────────────────────

class TestLiquidity:
    def test_lp_add_detected(self):
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("UNI-V2", "10")],   # LP token received
            assets_out=[_a("ETH", "1"), _a("USDC", "1800")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "lp_add"

    def test_lp_remove_detected(self):
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("ETH", "1"), _a("USDC", "1800")],
            assets_out=[_a("UNI-V2", "10")],   # burning LP token
        )
        result = engine.categorize(tx)
        assert result.tx_type == "lp_remove"

    def test_lp_remove_is_taxable(self):
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("ETH", "1"), _a("USDC", "1800")],
            assets_out=[_a("UNI-V2", "10")],
        )
        result = engine.categorize(tx)
        assert is_taxable_disposal(result)

    def test_lp_add_not_taxable(self):
        tx = _t(
            to_addr=UNISWAP_V2_ROUTER,
            assets_in=[_a("UNI-V2", "10")],
            assets_out=[_a("ETH", "1"), _a("USDC", "1800")],
        )
        result = engine.categorize(tx)
        assert not is_taxable_disposal(result)


# ── Staking ───────────────────────────────────────────────────────────────────

class TestStaking:
    def test_lido_stake_detected(self):
        tx = _t(
            to_addr=LIDO_STETH,
            assets_in=[_a("STETH", "1")],
            assets_out=[_a("ETH", "1")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "stake"
        assert result.protocol == "Lido"

    def test_staking_reward_is_income(self):
        # Receiving reward tokens with no send
        tx = _t(
            from_addr="0xstakingcontract000000000000000000000001",
            to_addr=USER_WALLET,
            assets_in=[_a("LDO", "50")],
            assets_out=[],
            protocol="Lido",
        )
        result = engine.categorize(tx)
        assert result.tx_type == "reward"
        assert is_income_event(result)

    def test_reward_not_taxable_disposal(self):
        tx = _t(
            from_addr="0xstakingcontract000000000000000000000001",
            to_addr=USER_WALLET,
            assets_in=[_a("LDO", "50")],
            assets_out=[],
            protocol="Lido",
        )
        result = engine.categorize(tx)
        assert not is_taxable_disposal(result)


# ── Airdrop ───────────────────────────────────────────────────────────────────

class TestAirdrop:
    def test_airdrop_detected(self):
        tx = _t(
            from_addr="0xairdropcontract0000000000000000000000001",
            to_addr=USER_WALLET,
            assets_in=[_a("ARB", "1000")],
            assets_out=[],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "airdrop"

    def test_airdrop_is_income(self):
        tx = _t(
            from_addr="0xairdropcontract0000000000000000000000001",
            to_addr=USER_WALLET,
            assets_in=[_a("OP", "500")],
            assets_out=[],
        )
        result = engine.categorize(tx)
        assert is_income_event(result)

    def test_airdrop_not_taxable_disposal(self):
        tx = _t(
            from_addr="0xairdropcontract0000000000000000000000001",
            to_addr=USER_WALLET,
            assets_in=[_a("UNI", "400")],
            assets_out=[],
        )
        result = engine.categorize(tx)
        assert not is_taxable_disposal(result)


# ── NFT ────────────────────────────────────────────────────────────────────────

class TestNFT:
    def test_nft_sell_detected(self):
        tx = _t(
            to_addr=OPENSEA_SEAPORT_V1_5,
            assets_in=[_a("ETH", "2")],
            assets_out=[_a("BoredApeYachtClub #1234", "1")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "nft_sell"

    def test_nft_buy_detected(self):
        tx = _t(
            to_addr=OPENSEA_SEAPORT_V1_5,
            assets_in=[_a("CryptoPunks #5678", "1")],
            assets_out=[_a("ETH", "50")],
        )
        result = engine.categorize(tx)
        assert result.tx_type == "nft_buy"

    def test_nft_sell_taxable(self):
        tx = _t(
            to_addr=OPENSEA_SEAPORT_V1_5,
            assets_in=[_a("ETH", "2")],
            assets_out=[_a("BoredApeYachtClub #1234", "1")],
        )
        result = engine.categorize(tx)
        assert is_taxable_disposal(result)


# ── Batch categorization ──────────────────────────────────────────────────────

class TestBatchCategorization:
    def test_categorize_all_returns_same_count(self):
        txs = [
            _t("h1", to_addr=UNISWAP_V2_ROUTER,
               assets_in=[_a("USDC")], assets_out=[_a("ETH")]),
            _t("h2", to_addr=ARBITRUM_BRIDGE, assets_out=[_a("ETH")]),
            _t("h3", from_addr=USER_WALLET, to_addr=USER_WALLET2, assets_out=[_a("ETH")]),
        ]
        results = categorize_transactions(txs, known_wallets=KNOWN_WALLETS)
        assert len(results) == 3

    def test_batch_types_correct(self):
        txs = [
            _t("h1", to_addr=UNISWAP_V2_ROUTER,
               assets_in=[_a("USDC")], assets_out=[_a("ETH")]),
            _t("h2", to_addr=ARBITRUM_BRIDGE, assets_out=[_a("ETH")]),
            _t("h3", from_addr=USER_WALLET, to_addr=USER_WALLET2, assets_out=[_a("ETH")]),
        ]
        results = categorize_transactions(txs, known_wallets=KNOWN_WALLETS)
        types = {r.tx_hash: r.tx_type for r in results}
        assert types["h1"] == "swap"
        assert types["h2"] == "bridge"
        assert types["h3"] == "transfer"
