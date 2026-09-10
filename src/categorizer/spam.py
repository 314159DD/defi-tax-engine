"""
Spam token filter.

Detects and flags spam transactions so they are excluded from tax
calculations, dashboard totals, and tier billing.  Users can manually
un-flag transactions via the UI.

Detection strategies:
1. Known spam contract addresses
2. Token name heuristics (URLs, "Visit", "Claim at", etc.)
3. Dust amounts (< $0.01 USD value)
4. Zero-value transfers

Usage:
    spam_filter = SpamFilter()
    if spam_filter.is_spam(tx):
        tx.raw_data["spam"] = True
"""
from __future__ import annotations

import logging
from decimal import Decimal

from src.data.spam_tokens import KNOWN_SPAM_CONTRACTS, SPAM_NAME_PATTERNS
from src.importers.models import AssetTransfer, Transaction

logger = logging.getLogger(__name__)

# Dust threshold - transfers below this USD value are suspicious
_DUST_THRESHOLD_USD = Decimal("0.01")


class SpamFilter:
    """
    Identifies spam transactions using contract lists, name heuristics,
    and value-based filters.

    Attributes:
        extra_spam_contracts: Additional spam addresses supplied at runtime
            (e.g. from a user blacklist).
    """

    def __init__(self, extra_spam_contracts: set[str] | None = None) -> None:
        self._spam_contracts: frozenset[str] = KNOWN_SPAM_CONTRACTS
        if extra_spam_contracts:
            self._spam_contracts = self._spam_contracts | frozenset(
                addr.lower() for addr in extra_spam_contracts
            )

    # ── Public API ───────────────────────────────────────────────────────

    def is_spam(self, tx: Transaction) -> bool:
        """
        Return True if the transaction should be flagged as spam.

        Checks are ordered from cheapest to most expensive.
        """
        if self._known_spam_contract(tx):
            return True
        if self._zero_value_transfer(tx):
            return True
        if self._spam_token_name(tx):
            return True
        if self._dust_amount(tx):
            return True
        return False

    def filter_spam(self, transactions: list[Transaction]) -> tuple[list[Transaction], list[Transaction]]:
        """
        Partition transactions into (clean, spam) lists.

        Spam transactions have ``raw_data["spam"] = True`` set.
        """
        clean: list[Transaction] = []
        spam: list[Transaction] = []
        for tx in transactions:
            if self.is_spam(tx):
                flagged = Transaction(
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
                spam.append(flagged)
            else:
                clean.append(tx)

        if spam:
            logger.info("Spam filter flagged %d / %d transactions", len(spam), len(transactions))
        return clean, spam

    # ── Private checks ───────────────────────────────────────────────────

    def _known_spam_contract(self, tx: Transaction) -> bool:
        """Check if any token address in the transaction is a known spam contract."""
        for transfer in [*tx.assets_in, *tx.assets_out]:
            if transfer.token_address and transfer.token_address.lower() in self._spam_contracts:
                return True
        # Also check if from_address is a known spam sender
        if tx.from_address.lower() in self._spam_contracts:
            return True
        return False

    def _spam_token_name(self, tx: Transaction) -> bool:
        """Check if any token symbol matches known spam name patterns."""
        for transfer in [*tx.assets_in, *tx.assets_out]:
            symbol = transfer.token_symbol
            for pattern in SPAM_NAME_PATTERNS:
                if pattern.search(symbol):
                    return True
        return False

    def _zero_value_transfer(self, tx: Transaction) -> bool:
        """
        Flag zero-value transfers (common in spam/phishing).

        Only flags if ALL transfers have zero amount and there are assets.
        """
        all_transfers = [*tx.assets_in, *tx.assets_out]
        if not all_transfers:
            return False
        return all(t.amount == Decimal("0") for t in all_transfers)

    def _dust_amount(self, tx: Transaction) -> bool:
        """
        Flag if ALL incoming assets have USD value below dust threshold
        and there are no outgoing assets (unsolicited receive).

        Only applies to receive-only transactions (potential spam airdrops).
        We do NOT flag transactions where the user actively sent something.
        """
        if tx.assets_out:
            return False
        if not tx.assets_in:
            return False

        # Only flag as dust if ALL incoming have usd_value set and below threshold
        for transfer in tx.assets_in:
            if transfer.usd_value is None:
                return False  # Unknown value - don't assume spam
            if transfer.usd_value >= _DUST_THRESHOLD_USD:
                return False
        return True
