"""
Uniswap V3 concentrated liquidity position detection.

Uni V3 positions are ERC-721 NFTs managed by the NonfungiblePositionManager.
Each position has a specific price range (tickLower, tickUpper).

Lifecycle: mint -> increaseLiquidity -> decreaseLiquidity -> collect -> burn

Tax treatment:
- Mint / increase: NOT taxable. Cost basis = sum of token0 + token1 at FMV.
- Collect fees: IS income at FMV on collection date.
- Decrease / burn: IS a taxable disposal. Gain/loss vs cost basis of deposited tokens.

Key contract:
    NonfungiblePositionManager: 0xC36442b4a4522E871399CD717aBDD847Ab11FE88
"""
from __future__ import annotations

from src.categorizer.protocols import resolve_protocol
from src.importers.models import Transaction

# Uniswap V3 NonfungiblePositionManager (Ethereum mainnet, same on L2s)
UNI_V3_POSITION_MANAGER = "0xc36442b4a4522e871399cd717abdd847ab11fe88"

# Known method selectors (first 4 bytes of keccak256 of function signature)
_METHOD_SIGS: dict[str, str] = {
    "0x88316456": "mint",              # mint((address,address,uint24,int24,int24,...))
    "0x219f5d17": "increaseLiquidity", # increaseLiquidity((uint256,uint256,...))
    "0x0c49ccbe": "decreaseLiquidity", # decreaseLiquidity((uint256,uint128,...))
    "0xfc6f7865": "collect",           # collect((uint256,address,uint128,uint128))
    "0x42966c68": "burn",              # burn(uint256)
    "0xac9650d8": "multicall",         # multicall(bytes[])
}

# Mapping from detected method to our tx_type
_METHOD_TO_TYPE: dict[str, str] = {
    "mint":              "uni_v3_mint",
    "increaseLiquidity": "uni_v3_increase",
    "decreaseLiquidity": "uni_v3_decrease",
    "collect":           "uni_v3_collect",
    "burn":              "uni_v3_burn",
}


def _get_method_name(tx: Transaction) -> str | None:
    """
    Extract the Uni V3 method from raw transaction input data.

    Falls back to heuristic detection from asset flow patterns.
    """
    input_data = tx.raw_data.get("input", "") or tx.raw_data.get("methodId", "")
    if isinstance(input_data, str) and len(input_data) >= 10:
        selector = input_data[:10].lower()
        return _METHOD_SIGS.get(selector)
    return None


def _is_position_manager(tx: Transaction) -> bool:
    """Return True if the transaction interacts with the Uni V3 position manager."""
    return tx.to_address.lower() == UNI_V3_POSITION_MANAGER


def _detect_from_assets(tx: Transaction) -> str | None:
    """
    Heuristic: classify Uni V3 action from asset flow when input data is unavailable.

    - Mint / increase: user sends 1-2 tokens, receives nothing (or NFT position)
    - Decrease: user receives 1-2 tokens, sends nothing
    - Collect: user receives tokens (fee collection), no send
    - Burn: no asset flow (just destroys the NFT)
    """
    has_in = bool(tx.assets_in)
    has_out = bool(tx.assets_out)

    if has_out and not has_in:
        # Sending tokens to position manager - mint or increase
        return "mint"
    if has_in and not has_out:
        # Receiving tokens from position manager - could be collect or decrease
        # If amounts are small relative to position, likely collect (fees)
        # Without on-chain data, default to decrease (safer for tax)
        return "decreaseLiquidity"
    if has_in and has_out:
        # Both directions - multicall combining decrease + collect
        return "decreaseLiquidity"
    if not has_in and not has_out:
        # No asset movement - pure burn
        return "burn"
    return None


def is_uni_v3(tx: Transaction) -> bool:
    """Return True if this transaction interacts with Uniswap V3 position manager."""
    if _is_position_manager(tx):
        return True
    # Also check protocol name
    if tx.protocol and "uniswap v3" in tx.protocol.lower():
        if tx.to_address.lower() == UNI_V3_POSITION_MANAGER:
            return True
    return False


def apply(tx: Transaction) -> Transaction | None:
    """
    Classify Uniswap V3 position transactions.

    Returns a Transaction with tx_type set to one of:
        uni_v3_mint, uni_v3_increase, uni_v3_decrease, uni_v3_collect, uni_v3_burn

    Returns None if the rule does not apply.
    """
    if not _is_position_manager(tx):
        return None

    # Try method signature first, fall back to asset heuristic
    method = _get_method_name(tx) or _detect_from_assets(tx)
    if method is None:
        return None

    tx_type = _METHOD_TO_TYPE.get(method, "uni_v3_mint")
    protocol = tx.protocol or resolve_protocol(tx.to_address) or "Uniswap V3"

    # Extract position data from raw_data if available
    raw = dict(tx.raw_data)
    if "tokenId" not in raw:
        # Try to extract from logs
        logs = tx.raw_data.get("logs", [])
        for log in logs if isinstance(logs, list) else []:
            if isinstance(log, dict) and log.get("address", "").lower() == UNI_V3_POSITION_MANAGER:
                topics = log.get("topics", [])
                if len(topics) >= 2:
                    raw.setdefault("tokenId", topics[1])

    return Transaction(
        tx_hash=tx.tx_hash,
        chain=tx.chain,
        block_number=tx.block_number,
        timestamp=tx.timestamp,
        from_address=tx.from_address,
        to_address=tx.to_address,
        tx_type=tx_type,
        assets_in=tx.assets_in,
        assets_out=tx.assets_out,
        fee=tx.fee,
        protocol=protocol,
        raw_data=raw,
    )
