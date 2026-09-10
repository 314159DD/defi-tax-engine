"""
Transaction Categorization Engine.

Applies DeFi-specific rules in priority order to classify each transaction
by type and identify the correct tax treatment.

Rule priority (highest -> lowest):
1. Spam filter  - pre-filter known spam tokens (excluded from tax)
2. Self-transfer  - bridges and self-sends checked first (no tax)
3. Bridge         - cross-chain moves (no tax)
4. Uni V3 LP      - concentrated liquidity positions (mint/increase/decrease/collect/burn)
5. Lending        - Aave/Compound deposit/withdraw/liquidation
6. Vault          - Yearn/Beefy vault deposit/withdraw
7. Staking        - stake/unstake/reward (reward = income)
8. LP             - lp_add / lp_remove (lp_remove = taxable)
9. NFT            - nft_buy / nft_sell / mint
10. Swap          - DEX swap (taxable)
11. Airdrop       - receive with no send (income)
12. Fallback      - keep existing tx_type

Usage:
    engine = CategorizerEngine(known_wallets={"0xABC...", "0xDEF..."})
    categorized = engine.categorize_all(transactions)
"""
from __future__ import annotations

import logging
from typing import Optional

from src.categorizer.protocols import resolve_protocol
from src.categorizer.rules import (
    airdrop,
    bridge,
    lending,
    liquidity,
    nft,
    staking,
    swap,
    transfer,
    uniswap_v3,
    vault,
)
from src.categorizer.spam import SpamFilter
from src.importers.models import Transaction

logger = logging.getLogger(__name__)


class CategorizerEngine:
    """
    Applies rule-based DeFi categorization to a list of transactions.

    Args:
        known_wallets: All wallet addresses owned by the user (for self-transfer detection).
        spam_filter: Optional pre-configured SpamFilter. If None, a default one is created.
    """

    def __init__(
        self,
        known_wallets: set[str],
        spam_filter: SpamFilter | None = None,
    ) -> None:
        self.known_wallets = {w.lower() for w in known_wallets}
        self.spam_filter = spam_filter or SpamFilter()

    def categorize(self, tx: Transaction) -> Transaction:
        """
        Categorize a single transaction.

        Returns a new Transaction with updated tx_type and protocol fields.
        """
        result: Optional[Transaction] = None

        # 0. Spam filter (pre-processing step)
        if self.spam_filter.is_spam(tx):
            return Transaction(
                tx_hash=tx.tx_hash,
                chain=tx.chain,
                block_number=tx.block_number,
                timestamp=tx.timestamp,
                from_address=tx.from_address,
                to_address=tx.to_address,
                tx_type="spam",
                assets_in=tx.assets_in,
                assets_out=tx.assets_out,
                fee=tx.fee,
                protocol=tx.protocol,
                raw_data={**tx.raw_data, "spam": True},
            )

        # 1. Self-transfer (no tax event)
        result = transfer.apply(tx, self.known_wallets)
        if result:
            return result

        # 2. Bridge (no tax event, cost basis carries over)
        result = bridge.apply(tx)
        if result:
            return result

        # 3. Uniswap V3 concentrated liquidity positions
        result = uniswap_v3.apply(tx)
        if result:
            return result

        # 4. Lending rules (Aave, Compound)
        result = lending.apply(tx)
        if result:
            return result

        # 5. Vault rules (Yearn, Beefy, Convex)
        result = vault.apply(tx)
        if result:
            return result

        # 6. Staking rules (stake, unstake, reward)
        result = staking.apply(tx)
        if result:
            return result

        # 7. LP rules (lp_add, lp_remove)
        result = liquidity.apply(tx)
        if result:
            return result

        # 8. NFT rules (nft_buy, nft_sell, mint)
        result = nft.apply(tx)
        if result:
            return result

        # 9. Swap rules (taxable)
        result = swap.apply(tx)
        if result:
            return result

        # 10. Airdrop (income)
        result = airdrop.apply(tx, self.known_wallets)
        if result:
            return result

        # 11. Fallback: enrich protocol if possible, keep existing type
        protocol = tx.protocol or resolve_protocol(tx.to_address)
        if protocol != tx.protocol:
            return Transaction(
                tx_hash=tx.tx_hash,
                chain=tx.chain,
                block_number=tx.block_number,
                timestamp=tx.timestamp,
                from_address=tx.from_address,
                to_address=tx.to_address,
                tx_type=tx.tx_type,
                assets_in=tx.assets_in,
                assets_out=tx.assets_out,
                fee=tx.fee,
                protocol=protocol,
                raw_data=tx.raw_data,
            )

        return tx

    def categorize_all(self, transactions: list[Transaction]) -> list[Transaction]:
        """
        Categorize a list of transactions.

        Logs a summary of type counts when done.
        """
        results: list[Transaction] = []
        for tx in transactions:
            try:
                categorized = self.categorize(tx)
                results.append(categorized)
            except Exception as exc:
                logger.warning("Failed to categorize tx %s: %s", tx.tx_hash, exc)
                results.append(tx)  # keep original on error

        self._log_summary(results)
        return results

    def _log_summary(self, transactions: list[Transaction]) -> None:
        counts: dict[str, int] = {}
        for tx in transactions:
            counts[tx.tx_type] = counts.get(tx.tx_type, 0) + 1
        total = len(transactions)
        categorized = total - counts.get("unknown", 0)
        pct = (categorized / total * 100) if total else 0
        logger.info(
            "Categorized %d/%d transactions (%.1f%%). Breakdown: %s",
            categorized, total, pct,
            ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        )


# ── Convenience functions ─────────────────────────────────────────────────────

def categorize_transactions(
    transactions: list[Transaction],
    known_wallets: set[str],
) -> list[Transaction]:
    """Categorize a list of transactions with the given wallet set."""
    engine = CategorizerEngine(known_wallets=known_wallets)
    return engine.categorize_all(transactions)


# ── Tax event helpers ─────────────────────────────────────────────────────────

TAXABLE_TYPES: frozenset[str] = frozenset({
    "swap",
    "lp_remove",
    "nft_sell",
    "uni_v3_decrease",
    "vault_withdraw",
    "lending_withdraw",
    "lending_liquidation",
})

INCOME_TYPES: frozenset[str] = frozenset({
    "reward",
    "airdrop",
    "uni_v3_collect",
})

NON_TAXABLE_TYPES: frozenset[str] = frozenset({
    "transfer",
    "bridge",
    "stake",
    "unstake",
    "lp_add",
    "nft_buy",
    "mint",
    "approve",
    "unknown",
    "spam",
    "uni_v3_mint",
    "uni_v3_increase",
    "uni_v3_burn",
    "vault_deposit",
    "lending_deposit",
})


def is_taxable_disposal(tx: Transaction) -> bool:
    """Return True if this transaction triggers a capital gain/loss calculation."""
    return tx.tx_type in TAXABLE_TYPES


def is_income_event(tx: Transaction) -> bool:
    """Return True if this transaction is ordinary income (staking reward, airdrop)."""
    return tx.tx_type in INCOME_TYPES
