"""Configuration and environment variables for defi-tax-engine."""
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# --- Project root ---
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Database ---
DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "tax.db"))

# --- Etherscan-compatible API keys (one per chain) ---
ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
POLYGONSCAN_API_KEY: str = os.getenv("POLYGONSCAN_API_KEY", ETHERSCAN_API_KEY)
ARBISCAN_API_KEY: str = os.getenv("ARBISCAN_API_KEY", ETHERSCAN_API_KEY)
BASESCAN_API_KEY: str = os.getenv("BASESCAN_API_KEY", ETHERSCAN_API_KEY)
OPTIMISM_API_KEY: str = os.getenv("OPTIMISM_API_KEY", ETHERSCAN_API_KEY)
BSCSCAN_API_KEY: str = os.getenv("BSCSCAN_API_KEY", "")
SNOWTRACE_API_KEY: str = os.getenv("SNOWTRACE_API_KEY", "")
FTMSCAN_API_KEY: str = os.getenv("FTMSCAN_API_KEY", "")
ZKSYNC_API_KEY: str = os.getenv("ZKSYNC_API_KEY", "")
LINEASCAN_API_KEY: str = os.getenv("LINEASCAN_API_KEY", "")
SCROLLSCAN_API_KEY: str = os.getenv("SCROLLSCAN_API_KEY", "")
MANTLESCAN_API_KEY: str = os.getenv("MANTLESCAN_API_KEY", "")

# --- Solana ---
HELIUS_API_KEY: str = os.getenv("HELIUS_API_KEY", "")

# --- Price data ---
COINGECKO_API_KEY: str = os.getenv("COINGECKO_API_KEY", "")  # optional - free tier works without it

# --- Supabase (auth only, NOT financial data) ---
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# --- Stripe ---
STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Stripe Price IDs - create these in Stripe Dashboard and add to .env
STRIPE_PRICE_PRO_MONTHLY: str = os.getenv("STRIPE_PRICE_PRO_MONTHLY", "")
STRIPE_PRICE_PRO_ANNUAL: str = os.getenv("STRIPE_PRICE_PRO_ANNUAL", "")
STRIPE_PRICE_UNLIMITED_MONTHLY: str = os.getenv("STRIPE_PRICE_UNLIMITED_MONTHLY", "")
STRIPE_PRICE_UNLIMITED_ANNUAL: str = os.getenv("STRIPE_PRICE_UNLIMITED_ANNUAL", "")


# --- Structured chain configuration ---
@dataclass(frozen=True)
class ChainConfig:
    """Configuration for an EVM chain with an Etherscan-compatible API."""
    api_url: str
    native_token: str
    api_key_env: str
    chain_id: int
    api_key: str = ""  # resolved at load time


CHAIN_CONFIGS: dict[str, ChainConfig] = {
    # ── Existing chains ──────────────────────────────────────────────────────
    "ethereum": ChainConfig(
        api_url="https://api.etherscan.io/v2/api",
        native_token="ETH",
        api_key_env="ETHERSCAN_API_KEY",
        chain_id=1,
        api_key=ETHERSCAN_API_KEY,
    ),
    "polygon": ChainConfig(
        api_url="https://api.etherscan.io/v2/api",
        native_token="MATIC",
        api_key_env="POLYGONSCAN_API_KEY",
        chain_id=137,
        api_key=POLYGONSCAN_API_KEY,
    ),
    "arbitrum": ChainConfig(
        api_url="https://api.etherscan.io/v2/api",
        native_token="ETH",
        api_key_env="ARBISCAN_API_KEY",
        chain_id=42161,
        api_key=ARBISCAN_API_KEY,
    ),
    "base": ChainConfig(
        api_url="https://api.etherscan.io/v2/api",
        native_token="ETH",
        api_key_env="BASESCAN_API_KEY",
        chain_id=8453,
        api_key=BASESCAN_API_KEY,
    ),
    "optimism": ChainConfig(
        api_url="https://api.etherscan.io/v2/api",
        native_token="ETH",
        api_key_env="OPTIMISM_API_KEY",
        chain_id=10,
        api_key=OPTIMISM_API_KEY,
    ),
    # ── New EVM chains (Sprint 5.4) ──────────────────────────────────────────
    "bsc": ChainConfig(
        api_url="https://api.bscscan.com/api",
        native_token="BNB",
        api_key_env="BSCSCAN_API_KEY",
        chain_id=56,
        api_key=BSCSCAN_API_KEY,
    ),
    "avalanche": ChainConfig(
        api_url="https://api.snowtrace.io/api",
        native_token="AVAX",
        api_key_env="SNOWTRACE_API_KEY",
        chain_id=43114,
        api_key=SNOWTRACE_API_KEY,
    ),
    "fantom": ChainConfig(
        api_url="https://api.ftmscan.com/api",
        native_token="FTM",
        api_key_env="FTMSCAN_API_KEY",
        chain_id=250,
        api_key=FTMSCAN_API_KEY,
    ),
    "zksync": ChainConfig(
        api_url="https://block-explorer-api.mainnet.zksync.io/api",
        native_token="ETH",
        api_key_env="ZKSYNC_API_KEY",
        chain_id=324,
        api_key=ZKSYNC_API_KEY,
    ),
    "linea": ChainConfig(
        api_url="https://api.lineascan.build/api",
        native_token="ETH",
        api_key_env="LINEASCAN_API_KEY",
        chain_id=59144,
        api_key=LINEASCAN_API_KEY,
    ),
    "scroll": ChainConfig(
        api_url="https://api.scrollscan.com/api",
        native_token="ETH",
        api_key_env="SCROLLSCAN_API_KEY",
        chain_id=534352,
        api_key=SCROLLSCAN_API_KEY,
    ),
    "mantle": ChainConfig(
        api_url="https://api.mantlescan.xyz/api",
        native_token="MNT",
        api_key_env="MANTLESCAN_API_KEY",
        chain_id=5000,
        api_key=MANTLESCAN_API_KEY,
    ),
}


# --- Legacy dicts (backward-compat - prefer CHAIN_CONFIGS for new code) ---
CHAIN_EXPLORER_URLS: dict[str, str] = {
    name: cfg.api_url for name, cfg in CHAIN_CONFIGS.items()
}

CHAIN_API_KEYS: dict[str, str] = {
    name: cfg.api_key for name, cfg in CHAIN_CONFIGS.items()
}

SUPPORTED_EVM_CHAINS: list[str] = list(CHAIN_CONFIGS.keys())
SUPPORTED_CHAINS: list[str] = SUPPORTED_EVM_CHAINS + ["solana", "bitcoin", "cosmoshub", "osmosis"]

# --- Non-EVM chain support ---
NON_EVM_CHAINS: list[str] = ["bitcoin", "cosmoshub", "osmosis"]

# --- Cosmos LCD endpoints ---
COSMOS_LCD_ENDPOINTS: dict[str, str] = {
    "cosmoshub": "https://rest.cosmos.directory/cosmoshub",
    "osmosis": "https://rest.cosmos.directory/osmosis",
}

COSMOS_NATIVE_TOKENS: dict[str, str] = {
    "cosmoshub": "ATOM",
    "osmosis": "OSMO",
}

COSMOS_DENOMS: dict[str, str] = {
    "uatom": "ATOM",
    "uosmo": "OSMO",
}

# --- Rate limits ---
ETHERSCAN_RATE_LIMIT: int = 5   # requests per second (free API key)
COINGECKO_RATE_LIMIT: int = 10  # requests per minute (free tier)
HELIUS_DAILY_LIMIT: int = 1000  # requests per day (free tier)
BLOCKSTREAM_RATE_LIMIT: int = 10  # requests per second (no API key needed)
