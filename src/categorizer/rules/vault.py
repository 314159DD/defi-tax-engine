"""
Auto-compounding vault deposit/withdrawal detection.

Vaults accept underlying tokens and return vault shares (yvDAI, mooXYZ, etc.).
Share price increases over time as the vault auto-compounds rewards.

Tax treatment:
- Deposit (token -> vault share): NOT immediately taxable.
  Cost basis of vault share = FMV of deposited tokens.
- Withdrawal (vault share -> token): IS taxable.
  Gain = (withdrawn FMV - deposited FMV). Treated as capital gain.

Supported protocols:
- Yearn V2/V3 (yvToken pattern)
- Beefy (mooToken pattern)
- Convex (cvxToken pattern)
"""
from __future__ import annotations

import re

from src.categorizer.protocols import resolve_protocol
from src.importers.models import AssetTransfer, Transaction

# ── Known vault contract addresses (examples - more added via protocols.py) ──
VAULT_ADDRESSES: frozenset[str] = frozenset({
    # Yearn V2 vaults (representative set)
    "0x19d3364a399d251e894ac732651be8b0e4e85001",  # yvDAI
    "0xa354f35829ae975e850e23e9615b11da1b3dc4de",  # yvUSDC
    "0xa258c4606ca8206d8aa700ce2143d7db854d168c",  # yvWETH
    "0x7da96a3891add058ada2e826306d812c638d87a7",  # yvUSDT
    # Yearn V3
    "0x028edc7d75a4f7e30755a3634e1c3cfbd6a9e101",  # Yearn V3 example
    # Beefy vaults (representative set)
    "0x453d4ba9a2d594314df88564248497f7d74d6b2c",  # moo example
    # Convex
    "0xf403c135812408bfbe8713b5a23a04b3d48aae31",  # Convex Booster
    "0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b",  # CVX token
})

# ── Vault share token patterns ──────────────────────────────────────────────
_YEARN_RE = re.compile(r"(?i)^yv[A-Z]")          # yvDAI, yvUSDC, yvWETH
_BEEFY_RE = re.compile(r"(?i)^moo[A-Z]")         # mooCurveDAI, mooAaveETH
_CONVEX_RE = re.compile(r"(?i)^cvx[A-Z]")        # cvxCRV, cvxFXS
_YEARN_V3_RE = re.compile(r"(?i)^ys?[A-Z]")      # yDAI, ysDAI (V3 naming)

_VAULT_PATTERNS = [_YEARN_RE, _BEEFY_RE, _CONVEX_RE, _YEARN_V3_RE]


def _is_vault_token(transfer: AssetTransfer) -> bool:
    """Return True if the token looks like a vault share."""
    sym = transfer.token_symbol
    return any(p.search(sym) for p in _VAULT_PATTERNS)


def _to_vault_contract(tx: Transaction) -> bool:
    """Return True if to_address is a known vault contract."""
    return tx.to_address.lower() in VAULT_ADDRESSES


def _protocol_is_vault(tx: Transaction) -> bool:
    """Return True if the protocol name indicates a vault."""
    if not tx.protocol:
        return False
    lower = tx.protocol.lower()
    return any(kw in lower for kw in ("yearn", "beefy", "convex", "vault"))


def is_vault_deposit(tx: Transaction) -> bool:
    """
    Detect vault deposit: user sends underlying token, receives vault shares.

    Patterns:
    1. assets_out has underlying tokens, assets_in has vault shares (yvX, mooX)
    2. Interacts with known vault contract
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    has_vault_in = any(_is_vault_token(t) for t in tx.assets_in)
    has_vault_out = any(_is_vault_token(t) for t in tx.assets_out)

    # Deposit: send underlying, receive vault share
    if has_vault_in and not has_vault_out:
        if _to_vault_contract(tx) or _protocol_is_vault(tx):
            return True

    return False


def is_vault_withdraw(tx: Transaction) -> bool:
    """
    Detect vault withdrawal: user burns vault shares, receives underlying tokens.

    Patterns:
    1. assets_out has vault shares (yvX, mooX), assets_in has underlying tokens
    2. Interacts with known vault contract
    """
    if not tx.assets_in or not tx.assets_out:
        return False

    has_vault_in = any(_is_vault_token(t) for t in tx.assets_in)
    has_vault_out = any(_is_vault_token(t) for t in tx.assets_out)

    # Withdraw: send vault share, receive underlying
    if has_vault_out and not has_vault_in:
        if _to_vault_contract(tx) or _protocol_is_vault(tx):
            return True

    return False


def apply(tx: Transaction) -> Transaction | None:
    """
    Classify as 'vault_deposit' or 'vault_withdraw' if applicable.
    Returns None if the rule does not apply.
    """
    protocol = tx.protocol or resolve_protocol(tx.to_address)

    if is_vault_deposit(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="vault_deposit",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Vault",
            raw_data=tx.raw_data,
        )

    if is_vault_withdraw(tx):
        return Transaction(
            tx_hash=tx.tx_hash,
            chain=tx.chain,
            block_number=tx.block_number,
            timestamp=tx.timestamp,
            from_address=tx.from_address,
            to_address=tx.to_address,
            tx_type="vault_withdraw",
            assets_in=tx.assets_in,
            assets_out=tx.assets_out,
            fee=tx.fee,
            protocol=protocol or "Vault",
            raw_data=tx.raw_data,
        )

    return None
