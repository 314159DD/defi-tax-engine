"""
Tests for Sprint 5.4: Additional Chain & Protocol Coverage.

Covers:
  - Chain config loading for all new EVM chains
  - EVMImporter factory method
  - Bitcoin address parsing (simple send/receive)
  - Cosmos delegation/reward parsing
  - Each new CEX CSV parser with sample data
  - Protocol address lookups for new chains
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from src.config import (
    CHAIN_CONFIGS,
    COSMOS_LCD_ENDPOINTS,
    COSMOS_NATIVE_TOKENS,
    SUPPORTED_CHAINS,
    SUPPORTED_EVM_CHAINS,
    ChainConfig,
)
from src.categorizer.protocols import (
    DEX_ADDRESSES,
    PANCAKESWAP_V2_ROUTER,
    PROTOCOL_ADDRESSES,
    SOLANA_DEX_PROGRAMS,
    SOLANA_PROGRAM_ADDRESSES,
    SPOOKYSWAP_ROUTER,
    TRADER_JOE_ROUTER,
    VAULT_ADDRESSES,
    resolve_protocol,
)
from src.importers.bitcoin import BitcoinImporter
from src.importers.cosmos import CosmosImporter
from src.importers.evm import EVMImporter
from src.importers.exchange import ExchangeImporter


# =============================================================================
# Chain Config Tests
# =============================================================================

class TestChainConfigs:
    """Test that all new EVM chains are properly configured."""

    NEW_EVM_CHAINS = ["bsc", "avalanche", "fantom", "zksync", "linea", "scroll", "mantle"]

    def test_all_new_chains_in_config(self):
        for chain in self.NEW_EVM_CHAINS:
            assert chain in CHAIN_CONFIGS, f"{chain} not found in CHAIN_CONFIGS"

    def test_chain_config_has_required_fields(self):
        for chain_name, cfg in CHAIN_CONFIGS.items():
            assert isinstance(cfg, ChainConfig), f"{chain_name} config is not a ChainConfig"
            assert cfg.api_url.startswith("https://"), f"{chain_name} api_url must be HTTPS"
            assert cfg.native_token, f"{chain_name} missing native_token"
            assert cfg.api_key_env, f"{chain_name} missing api_key_env"
            assert cfg.chain_id > 0, f"{chain_name} chain_id must be positive"

    def test_native_tokens_correct(self):
        expected = {
            "bsc": "BNB",
            "avalanche": "AVAX",
            "fantom": "FTM",
            "zksync": "ETH",
            "linea": "ETH",
            "scroll": "ETH",
            "mantle": "MNT",
        }
        for chain, expected_token in expected.items():
            assert CHAIN_CONFIGS[chain].native_token == expected_token

    def test_chain_ids_unique(self):
        chain_ids = [cfg.chain_id for cfg in CHAIN_CONFIGS.values()]
        assert len(chain_ids) == len(set(chain_ids)), "Duplicate chain IDs found"

    def test_supported_evm_chains_includes_new(self):
        for chain in self.NEW_EVM_CHAINS:
            assert chain in SUPPORTED_EVM_CHAINS

    def test_supported_chains_includes_non_evm(self):
        for chain in ["bitcoin", "cosmoshub", "osmosis", "solana"]:
            assert chain in SUPPORTED_CHAINS

    def test_cosmos_endpoints_configured(self):
        assert "cosmoshub" in COSMOS_LCD_ENDPOINTS
        assert "osmosis" in COSMOS_LCD_ENDPOINTS

    def test_cosmos_native_tokens(self):
        assert COSMOS_NATIVE_TOKENS["cosmoshub"] == "ATOM"
        assert COSMOS_NATIVE_TOKENS["osmosis"] == "OSMO"


# =============================================================================
# EVM Importer Tests
# =============================================================================

class TestEVMImporter:
    """Test EVMImporter with new chain support."""

    def test_for_chain_factory_existing(self):
        importer = EVMImporter.for_chain("ethereum")
        assert importer.chain == "ethereum"
        assert importer.native_symbol == "ETH"

    def test_for_chain_factory_new_bsc(self):
        importer = EVMImporter.for_chain("bsc")
        assert importer.chain == "bsc"
        assert importer.native_symbol == "BNB"
        assert "bscscan.com" in importer.base_url

    def test_for_chain_factory_new_avalanche(self):
        importer = EVMImporter.for_chain("avalanche")
        assert importer.chain == "avalanche"
        assert importer.native_symbol == "AVAX"
        assert "snowtrace.io" in importer.base_url

    def test_for_chain_factory_new_fantom(self):
        importer = EVMImporter.for_chain("fantom")
        assert importer.chain == "fantom"
        assert importer.native_symbol == "FTM"

    def test_for_chain_factory_new_mantle(self):
        importer = EVMImporter.for_chain("mantle")
        assert importer.chain == "mantle"
        assert importer.native_symbol == "MNT"

    def test_for_chain_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown chain"):
            EVMImporter.for_chain("nonexistent_chain")

    def test_from_config_factory(self):
        custom_cfg = ChainConfig(
            api_url="https://test.example.com/api",
            native_token="TEST",
            api_key_env="TEST_API_KEY",
            chain_id=99999,
            api_key="fake_key",
        )
        importer = EVMImporter.from_config("test_chain", custom_cfg)
        assert importer.chain == "test_chain"
        assert importer.native_symbol == "TEST"
        assert importer.base_url == "https://test.example.com/api"

    def test_all_new_chains_instantiate(self):
        for chain in ["bsc", "avalanche", "fantom", "zksync", "linea", "scroll", "mantle"]:
            importer = EVMImporter(chain)
            assert importer.chain == chain


# =============================================================================
# Bitcoin Importer Tests
# =============================================================================

class TestBitcoinImporter:
    """Test Bitcoin UTXO transaction parsing."""

    def _make_raw_tx(
        self,
        txid: str = "abc123",
        block_time: int = 1700000000,
        block_height: int = 800000,
        inputs: list[dict] | None = None,
        outputs: list[dict] | None = None,
    ) -> dict:
        """Helper to create a raw Blockstream transaction."""
        return {
            "txid": txid,
            "status": {
                "confirmed": True,
                "block_time": block_time,
                "block_height": block_height,
            },
            "vin": inputs or [],
            "vout": outputs or [],
        }

    def test_simple_receive(self):
        """Test parsing a simple receive transaction."""
        address = "bc1qtest_receiver"
        raw = self._make_raw_tx(
            inputs=[
                {"prevout": {"scriptpubkey_address": "bc1qsender", "value": 100000}},
            ],
            outputs=[
                {"scriptpubkey_address": address, "value": 90000},
                {"scriptpubkey_address": "bc1qsender", "value": 10000},  # change
            ],
        )

        importer = BitcoinImporter()
        tx = importer._parse_transaction(raw, address, {address})

        assert tx is not None
        assert tx.chain == "bitcoin"
        assert tx.tx_type == "transfer"
        assert len(tx.assets_in) == 1
        assert tx.assets_in[0].token_symbol == "BTC"
        assert tx.assets_in[0].amount == Decimal("90000") / Decimal("100000000")
        assert len(tx.assets_out) == 0
        assert tx.fee is None  # receiver doesn't pay fee

    def test_simple_send(self):
        """Test parsing a simple send transaction."""
        address = "bc1qsender"
        raw = self._make_raw_tx(
            inputs=[
                {"prevout": {"scriptpubkey_address": address, "value": 100000}},
            ],
            outputs=[
                {"scriptpubkey_address": "bc1qreceiver", "value": 89000},
                {"scriptpubkey_address": address, "value": 10000},  # change
            ],
        )

        importer = BitcoinImporter()
        tx = importer._parse_transaction(raw, address, {address})

        assert tx is not None
        assert tx.tx_type == "transfer"
        assert len(tx.assets_out) == 1
        assert tx.assets_out[0].token_symbol == "BTC"
        # Sent: 100000 (input) - 10000 (change) - 1000 (fee) = 89000 sats
        assert tx.assets_out[0].amount == Decimal("89000") / Decimal("100000000")
        assert tx.fee is not None
        assert tx.fee.amount == Decimal("1000") / Decimal("100000000")

    def test_self_transfer(self):
        """Test self-transfer detection."""
        address1 = "bc1qwallet1"
        address2 = "bc1qwallet2"
        known = {address1, address2}

        raw = self._make_raw_tx(
            inputs=[
                {"prevout": {"scriptpubkey_address": address1, "value": 50000}},
            ],
            outputs=[
                {"scriptpubkey_address": address2, "value": 49500},
            ],
        )

        importer = BitcoinImporter()
        tx = importer._parse_transaction(raw, address1, known)

        assert tx is not None
        assert tx.tx_type == "transfer"
        # Self-transfer: all outputs go to known wallets
        assert len(tx.assets_in) == 1  # shows gross received

    def test_unconfirmed_skipped(self):
        """Test that unconfirmed transactions are skipped."""
        raw = {
            "txid": "unconfirmed_tx",
            "status": {"confirmed": False},
            "vin": [], "vout": [],
        }
        importer = BitcoinImporter()
        tx = importer._parse_transaction(raw, "bc1qtest", {"bc1qtest"})
        assert tx is None


# =============================================================================
# Cosmos Importer Tests
# =============================================================================

class TestCosmosImporter:
    """Test Cosmos transaction message parsing."""

    def _make_tx_response(
        self,
        txhash: str = "COSMOSHASH123",
        messages: list[dict] | None = None,
        timestamp: str = "2024-01-15T12:00:00Z",
        height: str = "18000000",
        fee_amount: str = "5000",
        fee_denom: str = "uatom",
    ) -> dict:
        return {
            "txhash": txhash,
            "height": height,
            "timestamp": timestamp,
            "code": 0,
            "tx": {
                "body": {"messages": messages or []},
                "auth_info": {
                    "fee": {"amount": [{"denom": fee_denom, "amount": fee_amount}]}
                },
            },
            "logs": [],
        }

    def test_parse_msg_send_outgoing(self):
        """Test parsing a MsgSend (outgoing transfer)."""
        address = "cosmos1sender"
        msg = {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": address,
            "to_address": "cosmos1receiver",
            "amount": [{"denom": "uatom", "amount": "1000000"}],
        }
        raw = self._make_tx_response(messages=[msg])
        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, address, {address}, "cosmoshub", "ATOM")

        assert len(results) == 1
        tx = results[0]
        assert tx.tx_type == "transfer"
        assert len(tx.assets_out) == 1
        assert tx.assets_out[0].token_symbol == "ATOM"
        assert tx.assets_out[0].amount == Decimal("1")  # 1000000 / 1000000

    def test_parse_msg_send_incoming(self):
        """Test parsing a MsgSend (incoming transfer)."""
        address = "cosmos1receiver"
        msg = {
            "@type": "/cosmos.bank.v1beta1.MsgSend",
            "from_address": "cosmos1sender",
            "to_address": address,
            "amount": [{"denom": "uatom", "amount": "5000000"}],
        }
        raw = self._make_tx_response(messages=[msg])
        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, address, {address}, "cosmoshub", "ATOM")

        assert len(results) == 1
        tx = results[0]
        assert len(tx.assets_in) == 1
        assert tx.assets_in[0].amount == Decimal("5")

    def test_parse_msg_delegate(self):
        """Test parsing a MsgDelegate (staking)."""
        address = "cosmos1delegator"
        msg = {
            "@type": "/cosmos.staking.v1beta1.MsgDelegate",
            "delegator_address": address,
            "validator_address": "cosmosvaloper1val",
            "amount": {"denom": "uatom", "amount": "10000000"},
        }
        raw = self._make_tx_response(messages=[msg])
        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, address, {address}, "cosmoshub", "ATOM")

        assert len(results) == 1
        tx = results[0]
        assert tx.tx_type == "stake"
        assert tx.protocol == "Cosmos Staking"
        assert len(tx.assets_out) == 1
        assert tx.assets_out[0].amount == Decimal("10")

    def test_parse_msg_undelegate(self):
        """Test parsing a MsgUndelegate (unstaking)."""
        address = "cosmos1delegator"
        msg = {
            "@type": "/cosmos.staking.v1beta1.MsgUndelegate",
            "delegator_address": address,
            "validator_address": "cosmosvaloper1val",
            "amount": {"denom": "uatom", "amount": "5000000"},
        }
        raw = self._make_tx_response(messages=[msg])
        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, address, {address}, "cosmoshub", "ATOM")

        assert len(results) == 1
        tx = results[0]
        assert tx.tx_type == "unstake"
        assert len(tx.assets_in) == 1
        assert tx.assets_in[0].amount == Decimal("5")

    def test_parse_msg_withdraw_rewards(self):
        """Test parsing a MsgWithdrawDelegatorReward."""
        address = "cosmos1delegator"
        msg = {
            "@type": "/cosmos.distribution.v1beta1.MsgWithdrawDelegatorReward",
            "delegator_address": address,
            "validator_address": "cosmosvaloper1val",
        }
        raw = self._make_tx_response(messages=[msg])
        # Add reward amount in logs
        raw["logs"] = [{
            "events": [{
                "type": "withdraw_rewards",
                "attributes": [
                    {"key": "amount", "value": "250000uatom"},
                    {"key": "validator", "value": "cosmosvaloper1val"},
                ],
            }],
        }]

        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, address, {address}, "cosmoshub", "ATOM")

        assert len(results) == 1
        tx = results[0]
        assert tx.tx_type == "reward"
        assert len(tx.assets_in) == 1
        assert tx.assets_in[0].amount == Decimal("0.25")

    def test_parse_ibc_transfer(self):
        """Test parsing a MsgTransfer (IBC)."""
        address = "cosmos1sender"
        msg = {
            "@type": "/ibc.applications.transfer.v1.MsgTransfer",
            "sender": address,
            "receiver": "osmo1receiver",
            "token": {"denom": "uatom", "amount": "3000000"},
        }
        raw = self._make_tx_response(messages=[msg])
        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, address, {address}, "cosmoshub", "ATOM")

        assert len(results) == 1
        tx = results[0]
        assert tx.tx_type == "bridge"
        assert tx.protocol == "IBC"
        assert len(tx.assets_out) == 1
        assert tx.assets_out[0].amount == Decimal("3")

    def test_failed_tx_skipped(self):
        """Test that failed transactions are skipped."""
        raw = self._make_tx_response()
        raw["code"] = 11  # out of gas
        importer = CosmosImporter()
        results = importer._parse_tx_response(raw, "cosmos1test", {"cosmos1test"}, "cosmoshub", "ATOM")
        assert len(results) == 0

    def test_unsupported_chain_raises(self):
        importer = CosmosImporter()
        with pytest.raises(ValueError, match="Unsupported Cosmos chain"):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                importer.import_address("cosmos1test", chain="unknown_chain")
            )


# =============================================================================
# CEX CSV Parser Tests
# =============================================================================

class TestBitpandaParser:
    def test_parse_crypto_buy(self):
        csv_data = (
            "Transaction ID,Timestamp,Transaction Type,In/Out,Amount Fiat,Fiat,"
            "Amount Asset,Asset,Asset market price,Asset market price currency,"
            "Asset class,Product ID,Fee,Fee asset,Spread,Spread Currency,Status\n"
            "tx001,2024-01-15T10:00:00Z,buy,incoming,500.00,EUR,0.025,BTC,"
            "20000.00,EUR,Cryptocurrency,prod1,2.50,EUR,5.00,EUR,finished\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_bitpanda(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.chain == "bitpanda"
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"
        assert tx.assets_in[0].amount == Decimal("0.025")
        assert tx.assets_out[0].token_symbol == "EUR"
        assert tx.fee is not None
        assert tx.fee.amount == Decimal("2.50")

    def test_skip_non_crypto(self):
        csv_data = (
            "Transaction ID,Timestamp,Transaction Type,In/Out,Amount Fiat,Fiat,"
            "Amount Asset,Asset,Asset market price,Asset market price currency,"
            "Asset class,Product ID,Fee,Fee asset,Spread,Spread Currency,Status\n"
            "tx002,2024-01-15T10:00:00Z,buy,incoming,100.00,EUR,1,AAPL,"
            "150.00,EUR,Stock,prod2,1.00,EUR,0,EUR,finished\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_bitpanda(csv_data)
        assert len(txs) == 0


class TestBisonParser:
    def test_parse_buy(self):
        csv_data = "Datum;Typ;Kryptowährung;Menge;Kurs;EUR-Betrag;Gebühr\n"
        csv_data += "15.01.2024 10:00:00;Kauf;BTC;0.01;40000;400.00;1.50\n"
        importer = ExchangeImporter()
        txs = importer._parse_bison(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.chain == "bison"
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"
        assert tx.assets_in[0].amount == Decimal("0.01")
        assert tx.assets_out[0].token_symbol == "EUR"

    def test_parse_sell(self):
        csv_data = "Datum;Typ;Kryptowährung;Menge;Kurs;EUR-Betrag;Gebühr\n"
        csv_data += "15.01.2024 12:00:00;Verkauf;ETH;0.5;2000;1000.00;2.00\n"
        importer = ExchangeImporter()
        txs = importer._parse_bison(csv_data)
        assert len(txs) == 1
        assert txs[0].tx_type == "swap"
        assert txs[0].assets_out[0].token_symbol == "ETH"


class TestTradeRepublicParser:
    def test_parse_crypto_buy(self):
        csv_data = "Datum;Typ;ISIN;Name;Stück;Kurs;Betrag;Gebühren\n"
        csv_data += "15.01.2024 10:00:00;Kauf;;Bitcoin;0.005;40000;200.00;1.00\n"
        importer = ExchangeImporter()
        txs = importer._parse_trade_republic(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"

    def test_skip_stock_with_isin(self):
        csv_data = "Datum;Typ;ISIN;Name;Stück;Kurs;Betrag;Gebühren\n"
        csv_data += "15.01.2024 10:00:00;Kauf;US0378331005;Apple Inc;1;150;150.00;1.00\n"
        importer = ExchangeImporter()
        txs = importer._parse_trade_republic(csv_data)
        assert len(txs) == 0


class TestGeminiParser:
    def test_parse_buy(self):
        csv_data = (
            "Date,Time (UTC),Type,Symbol,Specification,Liquidity Indicator,"
            "Trading Fee Currency,Trading Fee Amount,USD Amount,Trading Fee (USD),"
            "Amount,Balance,Trade ID,Order ID,Order Date,Order Time,"
            "Client Order ID,API Session,Tx Hash,Deposit Destination,Deposit Tx Output,"
            "Withdrawal Destination,Withdrawal Tx Output\n"
            "2024-01-15,10:00:00,Buy,BTC,,,USD,5.00,10000.00,5.00,"
            "0.25,,trade001,,,,,,,,,,\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_gemini(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"
        assert tx.assets_in[0].amount == Decimal("0.25")


class TestKuCoinParser:
    def test_parse_buy(self):
        csv_data = (
            "oid,symbol,dealPrice,dealValue,amount,fee,direction,createdDate,feeCurrency\n"
            "order001,BTC-USDT,42000,420.00,0.01,0.00001,buy,2024-01-15 10:00:00,BTC\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_kucoin(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.chain == "kucoin"
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"
        assert tx.assets_in[0].amount == Decimal("0.01")
        assert tx.assets_out[0].token_symbol == "USDT"


class TestOKXParser:
    def test_parse_buy(self):
        csv_data = (
            "Order ID,Trade Time,Pair,Side,Price,Amount,Total,Fee,Fee Currency\n"
            "ord001,2024-01-15 10:00:00,BTC-USDT,buy,42000,0.01,420,0.042,USDT\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_okx(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.chain == "okx"
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"

    def test_parse_sell(self):
        csv_data = (
            "Order ID,Trade Time,Pair,Side,Price,Amount,Total,Fee,Fee Currency\n"
            "ord002,2024-01-15 11:00:00,ETH-USDT,sell,2200,1.0,2200,2.20,USDT\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_okx(csv_data)
        assert len(txs) == 1
        assert txs[0].assets_out[0].token_symbol == "ETH"
        assert txs[0].assets_in[0].token_symbol == "USDT"


class TestCryptoComParser:
    def test_parse_purchase(self):
        csv_data = (
            "Timestamp (UTC),Transaction Description,Currency,Amount,"
            "To Currency,To Amount,Native Currency,Native Amount,"
            "Native Amount (in USD),Transaction Kind,Transaction Hash\n"
            "2024-01-15 10:00:00,Buy BTC,BTC,0.01,,,USD,420,420.00,crypto_purchase,\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_crypto_com(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.chain == "crypto_com"
        assert tx.tx_type == "swap"
        assert tx.assets_in[0].token_symbol == "BTC"
        assert tx.assets_in[0].amount == Decimal("0.01")

    def test_parse_reward(self):
        csv_data = (
            "Timestamp (UTC),Transaction Description,Currency,Amount,"
            "To Currency,To Amount,Native Currency,Native Amount,"
            "Native Amount (in USD),Transaction Kind,Transaction Hash\n"
            "2024-01-15 10:00:00,CRO Staking Reward,CRO,50.0,,,USD,5,5.00,mco_stake_reward,\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_crypto_com(csv_data)
        assert len(txs) == 1
        assert txs[0].tx_type == "reward"
        assert txs[0].assets_in[0].token_symbol == "CRO"

    def test_parse_exchange(self):
        csv_data = (
            "Timestamp (UTC),Transaction Description,Currency,Amount,"
            "To Currency,To Amount,Native Currency,Native Amount,"
            "Native Amount (in USD),Transaction Kind,Transaction Hash\n"
            "2024-01-15 10:00:00,Convert BTC to ETH,BTC,0.01,"
            "ETH,0.15,USD,420,420.00,crypto_exchange,\n"
        )
        importer = ExchangeImporter()
        txs = importer._parse_crypto_com(csv_data)
        assert len(txs) == 1
        tx = txs[0]
        assert tx.tx_type == "swap"
        assert tx.assets_out[0].token_symbol == "BTC"
        assert tx.assets_in[0].token_symbol == "ETH"


# =============================================================================
# Protocol Address Tests
# =============================================================================

class TestProtocolExpansion:
    """Test new protocol addresses and lookups."""

    def test_pancakeswap_in_protocol_addresses(self):
        assert PANCAKESWAP_V2_ROUTER in PROTOCOL_ADDRESSES
        assert PROTOCOL_ADDRESSES[PANCAKESWAP_V2_ROUTER] == "PancakeSwap V2"

    def test_trader_joe_in_protocol_addresses(self):
        assert TRADER_JOE_ROUTER in PROTOCOL_ADDRESSES
        assert PROTOCOL_ADDRESSES[TRADER_JOE_ROUTER] == "Trader Joe"

    def test_spookyswap_in_protocol_addresses(self):
        assert SPOOKYSWAP_ROUTER in PROTOCOL_ADDRESSES
        assert PROTOCOL_ADDRESSES[SPOOKYSWAP_ROUTER] == "SpookySwap"

    def test_gmx_in_protocol_addresses(self):
        from src.categorizer.protocols import GMX_ROUTER_ARB, GMX_VAULT_ARB
        assert GMX_ROUTER_ARB in PROTOCOL_ADDRESSES
        assert PROTOCOL_ADDRESSES[GMX_ROUTER_ARB] == "GMX"
        assert GMX_VAULT_ARB in PROTOCOL_ADDRESSES

    def test_new_dexes_in_dex_set(self):
        assert PANCAKESWAP_V2_ROUTER in DEX_ADDRESSES
        assert TRADER_JOE_ROUTER in DEX_ADDRESSES
        assert SPOOKYSWAP_ROUTER in DEX_ADDRESSES

    def test_gmx_vaults_in_vault_set(self):
        from src.categorizer.protocols import GMX_VAULT_ARB, GMX_VAULT_AVAX
        assert GMX_VAULT_ARB in VAULT_ADDRESSES
        assert GMX_VAULT_AVAX in VAULT_ADDRESSES

    def test_resolve_protocol_pancakeswap(self):
        result = resolve_protocol(PANCAKESWAP_V2_ROUTER)
        assert result == "PancakeSwap V2"

    def test_resolve_protocol_case_insensitive(self):
        upper = PANCAKESWAP_V2_ROUTER.upper()
        result = resolve_protocol(upper)
        assert result == "PancakeSwap V2"

    def test_resolve_protocol_none(self):
        assert resolve_protocol(None) is None
        assert resolve_protocol("0x0000000000000000000000000000000000000000") is None

    def test_solana_program_addresses(self):
        from src.categorizer.protocols import JUPITER_V6_PROGRAM, RAYDIUM_AMM_V4
        assert JUPITER_V6_PROGRAM in SOLANA_PROGRAM_ADDRESSES
        assert SOLANA_PROGRAM_ADDRESSES[JUPITER_V6_PROGRAM] == "Jupiter"
        assert RAYDIUM_AMM_V4 in SOLANA_PROGRAM_ADDRESSES
        assert SOLANA_PROGRAM_ADDRESSES[RAYDIUM_AMM_V4] == "Raydium"

    def test_solana_dex_programs_set(self):
        from src.categorizer.protocols import JUPITER_V6_PROGRAM, RAYDIUM_AMM_V4
        assert JUPITER_V6_PROGRAM in SOLANA_DEX_PROGRAMS
        assert RAYDIUM_AMM_V4 in SOLANA_DEX_PROGRAMS

    def test_resolve_protocol_solana_program(self):
        from src.categorizer.protocols import JUPITER_V6_PROGRAM
        result = resolve_protocol(JUPITER_V6_PROGRAM)
        assert result == "Jupiter"

    def test_resolve_protocol_solana_case_sensitive(self):
        """Solana program IDs are Base58 and case-sensitive."""
        from src.categorizer.protocols import JUPITER_V6_PROGRAM
        # The correct ID should work
        assert resolve_protocol(JUPITER_V6_PROGRAM) == "Jupiter"
        # A lowercased version should NOT match (Base58 is case-sensitive)
        lowered = JUPITER_V6_PROGRAM.lower()
        # Only fails if original had uppercase chars
        if lowered != JUPITER_V6_PROGRAM:
            assert resolve_protocol(lowered) is None


# =============================================================================
# Exchange Importer Format Registration
# =============================================================================

class TestExchangeFormats:
    """Test that all new formats are registered correctly."""

    def test_all_new_formats_supported(self):
        from src.importers.exchange import SUPPORTED_FORMATS
        for fmt in ["bitpanda", "bison", "trade_republic", "gemini", "kucoin", "okx", "crypto_com"]:
            assert fmt in SUPPORTED_FORMATS, f"{fmt} not in SUPPORTED_FORMATS"

    def test_parse_file_invalid_format(self):
        importer = ExchangeImporter()
        with pytest.raises(ValueError, match="Unsupported format"):
            importer.parse_file("dummy.csv", "nonexistent_exchange")
