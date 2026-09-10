"""
Known DeFi protocol address -> name mapping.

Addresses are lowercase. Covers Ethereum mainnet by default.
Cross-chain addresses are tagged with chain prefix where they differ.
"""
from __future__ import annotations

# ── DEX Routers & Factories ──────────────────────────────────────────────────
UNISWAP_V2_ROUTER      = "0x7a250d5630b4cf539739df2c5dacb4c659f2488d"
UNISWAP_V2_FACTORY     = "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f"
UNISWAP_V3_ROUTER      = "0xe592427a0aece92de3edee1f18e0157c05861564"
UNISWAP_V3_ROUTER2     = "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45"
UNISWAP_V3_FACTORY     = "0x1f98431c8ad98523631ae4a59f267346ea31f984"
UNISWAP_V3_NFT_MANAGER = "0xc36442b4a4522e871399cd717abdd847ab11fe88"
UNISWAP_UNIVERSAL      = "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad"
SUSHISWAP_ROUTER       = "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f"
SUSHISWAP_FACTORY      = "0xc0aee478e3658e2610c5f7a4a2e1777ce9e4f2ac"
CURVE_ROUTER           = "0x99a58482bd75cbab83b27ec03ca68ff489b5788f"
CURVE_REGISTRY         = "0x90e00ace148ca3b23ac1bc8c240c2a7dd9c2d7f5"
BALANCER_VAULT         = "0xba12222222228d8ba445958a75a0704d566bf2c8"
ONE_INCH_V5            = "0x1111111254eeb25477b68fb85ed929f73a960582"
ONE_INCH_V6            = "0x111111125421ca6dc452d289314280a0f8842a65"
PARASWAP_V5            = "0xdef171fe48cf0115b1d80b88dc8eab59176fee57"

# ── Lending / Borrowing ──────────────────────────────────────────────────────
AAVE_V2_POOL           = "0x7d2768de32b0b80b7a3454c06bdac94a69ddc7a9"
AAVE_V3_POOL           = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2"
COMPOUND_V2_COMPTROLLER= "0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b"
COMPOUND_V3_USDC       = "0xc3d688b66703497daa19211eedff47f25384cdc3"
MAKER_DAI_JOIN         = "0x9759a6ac90977b93b58547b4a71c78317f391a28"
MAKER_VAT              = "0x35d1b3f3d7966a1dfe207aa4514c12a259a0492b"

# ── Liquid Staking ───────────────────────────────────────────────────────────
LIDO_STETH             = "0xae7ab96520de3a18e5e111b5eaab095312d7fe84"
LIDO_WSTETH            = "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0"
ROCKETPOOL_DEPOSIT     = "0xdd3f50f8a6cafbe9b31a427582963f465e745af8"
ROCKETPOOL_RETH        = "0xae78736cd615f374d3085123a210448e74fc6393"
FRAX_ETH               = "0x5e8422345238f34275888049021821e8e08caa1f"
CBETH                  = "0xbe9895146f7af43049ca1c1ae358b0541ea49704"

# ── Bridges ──────────────────────────────────────────────────────────────────
ARBITRUM_BRIDGE        = "0x8315177ab297ba92a06054ce80a67ed4dbd7ed3a"
ARBITRUM_GATEWAY       = "0x72ce9c846789fdb6fc1f34ac4ad25dd9ef7031ef"
OPTIMISM_BRIDGE        = "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1"
OPTIMISM_L2BRIDGE      = "0x4200000000000000000000000000000000000010"
BASE_BRIDGE            = "0x3154cf16ccdb4c6d922629664174b904d80f2c35"
POLYGON_BRIDGE         = "0xa0c68c638235ee32657e8f720a23cec1bfc77c77"
POLYGON_POS_BRIDGE     = "0x40ec5b33f54e0e8a33a975908c5ba1c14e5bbbdf"
HOP_ETH_BRIDGE         = "0xb8901acb165ed027e32754e0ffe830802919727f"
HOP_USDC_BRIDGE        = "0x3666f603cc164936c1b87e207f36beba4ac5f18a"
HOP_DAI_BRIDGE         = "0x3d4cc8a61c7528fd86c55cfe061a78dcba48edd1"
STARGATE_ROUTER        = "0x8731d54e9d02c286767d56ac03e8037c07e01e98"
STARGATE_ROUTER_V2     = "0x45f1a95a4d3f3836523f5c83673c797f4d4d263b"
ACROSS_BRIDGE          = "0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5"
ACROSS_V3              = "0x5ef6c01e11412d2723d600d7a4e40b9e0c441ab0"
SYNAPSE_BRIDGE         = "0x2796317b0ff8538f3370fef76e4058e5d13c4c37"
ORBITER_BRIDGE         = "0x80c67432656d59144ceff962e8faf8926599bcf8"
ORBITER_V2             = "0xe4edb277e41dc89ab076a1f049f4a3efa700bce8"
WORMHOLE_BRIDGE        = "0x3ee18b2214aff97000d974cf647e7c347e8fa585"
WORMHOLE_TOKEN_BRIDGE  = "0x98f3c9e6e3face36baad05fe09d375ef1464288b"
CELER_BRIDGE           = "0x5427fefa711eff984124bfbb1ab6fbf5e3da1820"
MULTICHAIN_ROUTER      = "0x6b7a87899490ece95443e979ca9485cbe7e71522"
LAYERZERO_ENDPOINT     = "0x66a71dcef29a0ffbdbe3c6a460a3b5bc225cd675"

# ── Yield / Vaults ───────────────────────────────────────────────────────────
YEARN_VAULT_V2         = "0x19d3364a399d251e894ac732651be8b0e4e85001"  # yvDAI example
YEARN_VAULT_V2_USDC    = "0xa354f35829ae975e850e23e9615b11da1b3dc4de"
YEARN_VAULT_V2_WETH    = "0xa258c4606ca8206d8aa700ce2143d7db854d168c"
CONVEX_BOOSTER         = "0xf403c135812408bfbe8713b5a23a04b3d48aae31"
CONVEX_CVX_TOKEN       = "0x4e3fbd56cd56c3e72c1403e103b45db9da5b9d2b"
BEEFY_VAULT            = "0x453d4ba9a2d594314df88564248497f7d74d6b2c"  # example

# ── NFT Marketplaces ─────────────────────────────────────────────────────────
OPENSEA_SEAPORT_V1_5   = "0x00000000000000adc04c56bf30ac9d3c0aaf14dc"
OPENSEA_SEAPORT_V1_4   = "0x00000000000001ad428e4906ae43d8f9852d0dd6"
OPENSEA_WYVERN_V2      = "0x7be8076f4ea4a4ad08075c2508e481d6c946d12b"
BLUR_MARKETPLACE       = "0x00000000000111abe46ff893f3b2fdf1f759a8a8"
LOOKSRARE              = "0x59728544b08ab483533076417fbbb2fd0b17ce3a"
X2Y2                   = "0x74312363e45dcaba76c59ec49a13aa114034c39b"

# ── Wrapped Tokens (non-taxable wraps) ───────────────────────────────────────
WETH_ADDRESS           = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
WBTC_ADDRESS           = "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599"
STETH_ADDRESS          = LIDO_STETH

# ── PancakeSwap (BSC) ────────────────────────────────────────────────────────
PANCAKESWAP_V2_ROUTER  = "0x10ed43c718714eb63d5aa57b78b54704e256024e"
PANCAKESWAP_V2_FACTORY = "0xca143ce32fe78f1f7019d7d551a6402fc5350c73"
PANCAKESWAP_V3_ROUTER  = "0x13f4ea83d0bd40e75c8222255bc855a974568dd4"
PANCAKESWAP_V3_FACTORY = "0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865"
PANCAKESWAP_NFT_MANAGER= "0x46a15b0b27311cedf172ab29e4f4766fbe7f4364"

# ── Trader Joe (Avalanche) ───────────────────────────────────────────────────
TRADER_JOE_ROUTER      = "0x60ae616a2155ee3d9a68541ba4544862310933d4"
TRADER_JOE_ROUTER_V2_1 = "0xb4315e873dbcf96ffd0acd8ea43f689d8c20fb30"
TRADER_JOE_FACTORY     = "0x9ad6c38be94206ca50bb0d90783181834c6a9dae"

# ── SpookySwap (Fantom) ──────────────────────────────────────────────────────
SPOOKYSWAP_ROUTER      = "0xf491e7b69e4244ad4002bc14e878a34207e38c29"
SPOOKYSWAP_FACTORY     = "0x152ee697f2e276fa89e96742e9bb9ab1f2e61be3"

# ── GMX (Arbitrum + Avalanche) ───────────────────────────────────────────────
GMX_ROUTER_ARB         = "0xabb6f0dc168da9424e8ef25fe0d7e21249e0c9fa"
GMX_VAULT_ARB          = "0x489ee077994b6658eafa855c308275ead8097c4a"
GMX_ROUTER_V2_ARB      = "0x7c68c7866a64fa2160f78eeae12217ffbf871fa8"
GMX_ROUTER_AVAX        = "0x5f719c2f1095f7b9996fd222a9e5e8a29e8e0c5c"
GMX_VAULT_AVAX         = "0x9ab2de34a33fb459b538c43f251eb825645e8595"

# ── Jupiter (Solana - program IDs, not EVM addresses) ────────────────────────
JUPITER_V6_PROGRAM     = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
JUPITER_LIMIT_ORDER    = "jupoNjAxXgZ4rjzxzPMP4oxduvQsQtZzyknqvzYNrNu"

# ── Raydium (Solana - program IDs) ──────────────────────────────────────────
RAYDIUM_AMM_V4         = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
RAYDIUM_CLMM           = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
RAYDIUM_CPSWAP         = "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"


# ── Aggregate lookup dict ────────────────────────────────────────────────────
PROTOCOL_ADDRESSES: dict[str, str] = {
    # Uniswap
    UNISWAP_V2_ROUTER:       "Uniswap V2",
    UNISWAP_V2_FACTORY:      "Uniswap V2",
    UNISWAP_V3_ROUTER:       "Uniswap V3",
    UNISWAP_V3_ROUTER2:      "Uniswap V3",
    UNISWAP_V3_FACTORY:      "Uniswap V3",
    UNISWAP_V3_NFT_MANAGER:  "Uniswap V3",
    UNISWAP_UNIVERSAL:       "Uniswap",
    # SushiSwap
    SUSHISWAP_ROUTER:        "SushiSwap",
    SUSHISWAP_FACTORY:       "SushiSwap",
    # Curve
    CURVE_ROUTER:            "Curve",
    CURVE_REGISTRY:          "Curve",
    # Balancer
    BALANCER_VAULT:          "Balancer",
    # Aggregators
    ONE_INCH_V5:             "1inch",
    ONE_INCH_V6:             "1inch",
    PARASWAP_V5:             "ParaSwap",
    # Aave
    AAVE_V2_POOL:            "Aave V2",
    AAVE_V3_POOL:            "Aave V3",
    # Compound
    COMPOUND_V2_COMPTROLLER: "Compound V2",
    COMPOUND_V3_USDC:        "Compound V3",
    # Maker
    MAKER_DAI_JOIN:          "MakerDAO",
    MAKER_VAT:               "MakerDAO",
    # Lido
    LIDO_STETH:              "Lido",
    LIDO_WSTETH:             "Lido",
    # RocketPool
    ROCKETPOOL_DEPOSIT:      "Rocket Pool",
    ROCKETPOOL_RETH:         "Rocket Pool",
    # Bridges
    ARBITRUM_BRIDGE:         "Arbitrum Bridge",
    ARBITRUM_GATEWAY:        "Arbitrum Bridge",
    OPTIMISM_BRIDGE:         "Optimism Bridge",
    OPTIMISM_L2BRIDGE:       "Optimism Bridge",
    BASE_BRIDGE:             "Base Bridge",
    POLYGON_BRIDGE:          "Polygon Bridge",
    POLYGON_POS_BRIDGE:      "Polygon Bridge",
    HOP_ETH_BRIDGE:          "Hop Protocol",
    HOP_USDC_BRIDGE:         "Hop Protocol",
    HOP_DAI_BRIDGE:          "Hop Protocol",
    STARGATE_ROUTER:         "Stargate",
    STARGATE_ROUTER_V2:      "Stargate",
    ACROSS_BRIDGE:           "Across",
    ACROSS_V3:               "Across",
    SYNAPSE_BRIDGE:          "Synapse",
    ORBITER_BRIDGE:          "Orbiter",
    ORBITER_V2:              "Orbiter",
    WORMHOLE_BRIDGE:         "Wormhole",
    WORMHOLE_TOKEN_BRIDGE:   "Wormhole",
    CELER_BRIDGE:            "Celer",
    MULTICHAIN_ROUTER:       "Multichain",
    LAYERZERO_ENDPOINT:      "LayerZero",
    # Yield
    YEARN_VAULT_V2:          "Yearn",
    YEARN_VAULT_V2_USDC:     "Yearn",
    YEARN_VAULT_V2_WETH:     "Yearn",
    CONVEX_BOOSTER:          "Convex",
    CONVEX_CVX_TOKEN:        "Convex",
    BEEFY_VAULT:             "Beefy",
    # NFT marketplaces
    OPENSEA_SEAPORT_V1_5:    "OpenSea",
    OPENSEA_SEAPORT_V1_4:    "OpenSea",
    OPENSEA_WYVERN_V2:       "OpenSea",
    BLUR_MARKETPLACE:        "Blur",
    LOOKSRARE:               "LooksRare",
    X2Y2:                    "X2Y2",
    # PancakeSwap (BSC)
    PANCAKESWAP_V2_ROUTER:   "PancakeSwap V2",
    PANCAKESWAP_V2_FACTORY:  "PancakeSwap V2",
    PANCAKESWAP_V3_ROUTER:   "PancakeSwap V3",
    PANCAKESWAP_V3_FACTORY:  "PancakeSwap V3",
    PANCAKESWAP_NFT_MANAGER: "PancakeSwap V3",
    # Trader Joe (Avalanche)
    TRADER_JOE_ROUTER:       "Trader Joe",
    TRADER_JOE_ROUTER_V2_1:  "Trader Joe V2.1",
    TRADER_JOE_FACTORY:      "Trader Joe",
    # SpookySwap (Fantom)
    SPOOKYSWAP_ROUTER:       "SpookySwap",
    SPOOKYSWAP_FACTORY:      "SpookySwap",
    # GMX (Arbitrum + Avalanche)
    GMX_ROUTER_ARB:          "GMX",
    GMX_VAULT_ARB:           "GMX",
    GMX_ROUTER_V2_ARB:       "GMX V2",
    GMX_ROUTER_AVAX:         "GMX",
    GMX_VAULT_AVAX:          "GMX",
}

# ── Bridge contract set (for bridge detection) ────────────────────────────────
BRIDGE_ADDRESSES: frozenset[str] = frozenset({
    ARBITRUM_BRIDGE, ARBITRUM_GATEWAY,
    OPTIMISM_BRIDGE, OPTIMISM_L2BRIDGE,
    BASE_BRIDGE,
    POLYGON_BRIDGE, POLYGON_POS_BRIDGE,
    HOP_ETH_BRIDGE, HOP_USDC_BRIDGE, HOP_DAI_BRIDGE,
    STARGATE_ROUTER, STARGATE_ROUTER_V2,
    ACROSS_BRIDGE, ACROSS_V3,
    SYNAPSE_BRIDGE,
    ORBITER_BRIDGE, ORBITER_V2,
    WORMHOLE_BRIDGE, WORMHOLE_TOKEN_BRIDGE,
    CELER_BRIDGE,
    MULTICHAIN_ROUTER,
    LAYERZERO_ENDPOINT,
})

# ── DEX address set (for swap detection) ─────────────────────────────────────
DEX_ADDRESSES: frozenset[str] = frozenset({
    UNISWAP_V2_ROUTER, UNISWAP_V3_ROUTER, UNISWAP_V3_ROUTER2,
    UNISWAP_UNIVERSAL,
    SUSHISWAP_ROUTER,
    CURVE_ROUTER,
    BALANCER_VAULT,
    ONE_INCH_V5, ONE_INCH_V6,
    PARASWAP_V5,
    # New chains
    PANCAKESWAP_V2_ROUTER, PANCAKESWAP_V3_ROUTER,
    TRADER_JOE_ROUTER, TRADER_JOE_ROUTER_V2_1,
    SPOOKYSWAP_ROUTER,
    GMX_ROUTER_ARB, GMX_ROUTER_V2_ARB, GMX_ROUTER_AVAX,
})

# ── Lending address set ──────────────────────────────────────────────────────
LENDING_ADDRESSES: frozenset[str] = frozenset({
    AAVE_V2_POOL, AAVE_V3_POOL,
    COMPOUND_V2_COMPTROLLER, COMPOUND_V3_USDC,
})

# ── Vault address set ────────────────────────────────────────────────────────
VAULT_ADDRESSES: frozenset[str] = frozenset({
    YEARN_VAULT_V2, YEARN_VAULT_V2_USDC, YEARN_VAULT_V2_WETH,
    CONVEX_BOOSTER,
    BEEFY_VAULT,
    GMX_VAULT_ARB, GMX_VAULT_AVAX,
})

# ── Staking address set ───────────────────────────────────────────────────────
STAKING_ADDRESSES: frozenset[str] = frozenset({
    LIDO_STETH, LIDO_WSTETH,
    ROCKETPOOL_DEPOSIT, ROCKETPOOL_RETH,
    FRAX_ETH, CBETH,
})

# ── Wrapped token pairs (wrapping = NOT taxable) ──────────────────────────────
WRAP_PAIRS: dict[str, str] = {
    # address_in -> address_out (or symbol_in -> symbol_out)
    "ETH":  WETH_ADDRESS,    # ETH -> WETH
    WETH_ADDRESS: "ETH",     # WETH -> ETH
}

# ── Solana program ID lookup (case-sensitive Base58, not lowercased) ──────────
SOLANA_PROGRAM_ADDRESSES: dict[str, str] = {
    JUPITER_V6_PROGRAM:     "Jupiter",
    JUPITER_LIMIT_ORDER:    "Jupiter",
    RAYDIUM_AMM_V4:         "Raydium",
    RAYDIUM_CLMM:           "Raydium",
    RAYDIUM_CPSWAP:         "Raydium",
}

# ── Solana DEX program IDs ───────────────────────────────────────────────────
SOLANA_DEX_PROGRAMS: frozenset[str] = frozenset({
    JUPITER_V6_PROGRAM, JUPITER_LIMIT_ORDER,
    RAYDIUM_AMM_V4, RAYDIUM_CLMM, RAYDIUM_CPSWAP,
})


def resolve_protocol(address: str | None) -> str | None:
    """Return protocol name for a contract address, or None if unknown.

    Handles both EVM addresses (lowercased) and Solana program IDs (case-sensitive).
    """
    if not address:
        return None
    # Check Solana programs first (case-sensitive)
    solana_match = SOLANA_PROGRAM_ADDRESSES.get(address)
    if solana_match:
        return solana_match
    # Then EVM addresses (case-insensitive)
    return PROTOCOL_ADDRESSES.get(address.lower())
