"""
NFT transaction detection rule.

NFT purchases and sales ARE taxable events (capital gains/losses).
NFT mints: treated as acquisition at mint price (cost basis = ETH/SOL paid).
NFT royalties received: ordinary income.
"""
from __future__ import annotations

from src.categorizer.protocols import (
    BLUR_MARKETPLACE,
    LOOKSRARE,
    OPENSEA_SEAPORT_V1_4,
    OPENSEA_SEAPORT_V1_5,
    OPENSEA_WYVERN_V2,
    X2Y2,
    resolve_protocol,
)
from src.importers.models import AssetTransfer, Transaction

NFT_MARKETPLACE_ADDRESSES: frozenset[str] = frozenset({
    OPENSEA_SEAPORT_V1_5,
    OPENSEA_SEAPORT_V1_4,
    OPENSEA_WYVERN_V2,
    BLUR_MARKETPLACE,
    LOOKSRARE,
    X2Y2,
})


def _has_nft_transfer(transfers: list[AssetTransfer]) -> bool:
    """True if any transfer looks like an ERC-721 (amount == 1 with # in symbol)."""
    for t in transfers:
        if "#" in t.token_symbol:  # e.g. "BoredApeYachtClub #1234"
            return True
    return False


def is_nft_buy(tx: Transaction) -> bool:
    """User buys NFT: sends ETH/token, receives NFT."""
    if not tx.assets_in or not tx.assets_out:
        return False
    # Asset direction is the reliable signal; marketplace address is secondary
    if _has_nft_transfer(tx.assets_in) and not _has_nft_transfer(tx.assets_out):
        return True
    return False


def is_nft_sell(tx: Transaction) -> bool:
    """User sells NFT: sends NFT, receives ETH/token."""
    if not tx.assets_in or not tx.assets_out:
        return False
    if _has_nft_transfer(tx.assets_out) and not _has_nft_transfer(tx.assets_in):
        return True
    # Marketplace address as tiebreaker when both sides have NFTs (rare)
    if (
        _has_nft_transfer(tx.assets_out)
        and tx.to_address.lower() in NFT_MARKETPLACE_ADDRESSES
    ):
        return True
    return False


def is_nft_mint(tx: Transaction) -> bool:
    """
    User mints NFT: sends ETH (to NFT contract), receives NFT.
    Mints do not go through a marketplace.
    """
    if not tx.assets_in:
        return False
    return _has_nft_transfer(tx.assets_in) and tx.to_address.lower() not in NFT_MARKETPLACE_ADDRESSES


def apply(tx: Transaction) -> Transaction | None:
    """
    Classify as 'nft_buy', 'nft_sell', or 'mint' if applicable.
    Returns None if rule does not apply.
    """
    protocol = tx.protocol or resolve_protocol(tx.to_address)

    if is_nft_sell(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="nft_sell",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "NFT Marketplace",
            raw_data=tx.raw_data,
        )

    if is_nft_buy(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="nft_buy",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "NFT Marketplace",
            raw_data=tx.raw_data,
        )

    if is_nft_mint(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="mint",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol,
            raw_data=tx.raw_data,
        )

    return None
