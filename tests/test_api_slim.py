"""
Tests for the slim API server (app_slim.py).

Tests:
    1. Health endpoint returns compute: client-side
    2. Chain proxy returns normalized transactions (mocked upstream)
    3. Price cache (second call within 5min uses cache)
    4. Rate limiting (100 req/min per user)
    5. Billing webhook signature verification
    6. Auth JWT validation (dev mode)
"""
from __future__ import annotations

import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.web.app_slim import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a test client for the slim app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_rate_limits():
    """Clear rate limit buckets between tests."""
    from src.web.routes import chain_proxy
    chain_proxy._user_buckets.clear()
    chain_proxy._price_cache.clear()
    yield
    chain_proxy._user_buckets.clear()
    chain_proxy._price_cache.clear()


@pytest.fixture(autouse=True)
def _fake_api_keys():
    """Inject fake API keys so chain proxy doesn't 503 in tests."""
    from src.web.routes import chain_proxy
    from src.config import CHAIN_CONFIGS, ChainConfig

    original_configs = dict(CHAIN_CONFIGS)
    for name, cfg in CHAIN_CONFIGS.items():
        if not cfg.api_key:
            CHAIN_CONFIGS[name] = ChainConfig(
                api_url=cfg.api_url,
                native_token=cfg.native_token,
                api_key_env=cfg.api_key_env,
                chain_id=cfg.chain_id,
                api_key="test-fake-key",
            )
    yield
    CHAIN_CONFIGS.clear()
    CHAIN_CONFIGS.update(original_configs)


# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"
        assert data["compute"] == "client-side"

    def test_health_includes_endpoints(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "endpoints" in data
        assert "/api/auth" in data["endpoints"]["auth"]
        assert "/api/billing" in data["endpoints"]["billing"]
        assert "/api/chains" in data["endpoints"]["chains"]

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "v2.0.0" in data["message"]


# ---------------------------------------------------------------------------
# 2. Chain proxy - normalized transactions (mocked)
# ---------------------------------------------------------------------------

class TestChainProxy:
    def test_supported_chains(self, client):
        """Test /api/chains/supported returns chain list."""
        resp = client.get("/api/chains/supported")
        assert resp.status_code == 200
        data = resp.json()
        assert "chains" in data
        chain_names = [c["name"] for c in data["chains"]]
        assert "ethereum" in chain_names
        assert "bitcoin" in chain_names

    @patch("src.web.routes.chain_proxy._get_http")
    def test_evm_proxy_normalized(self, mock_get_http, client):
        """Test EVM proxy returns normalized transaction format."""
        # Mock the httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "1",
            "message": "OK",
            "result": [
                {
                    "hash": "0xabc123",
                    "blockNumber": "12345678",
                    "timeStamp": "1700000000",
                    "from": "0xsender",
                    "to": "0xreceiver",
                    "value": "1000000000000000000",  # 1 ETH in wei
                    "gas": "21000",
                    "gasPrice": "20000000000",
                    "gasUsed": "21000",
                    "isError": "0",
                    "methodId": "0x",
                    "functionName": "",
                    "contractAddress": "",
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_http.return_value = mock_client

        resp = client.get("/api/chains/evm/ethereum/0xTestAddress")
        assert resp.status_code == 200
        data = resp.json()

        assert data["chain"] == "ethereum"
        assert data["count"] == 1
        tx = data["transactions"][0]
        assert tx["tx_hash"] == "0xabc123"
        assert tx["chain"] == "ethereum"
        assert tx["value"] == "1"  # 1 ETH normalized
        assert tx["token_symbol"] == "ETH"
        assert tx["from_address"] == "0xsender"
        assert tx["to_address"] == "0xreceiver"
        assert tx["is_error"] is False

    @patch("src.web.routes.chain_proxy._get_http")
    def test_bitcoin_proxy_normalized(self, mock_get_http, client):
        """Test Bitcoin proxy returns normalized format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "txid": "btctx123",
                "status": {"confirmed": True, "block_height": 800000, "block_time": 1700000000},
                "vin": [
                    {"prevout": {"scriptpubkey_address": "bc1qsender", "value": 50000000}},
                ],
                "vout": [
                    {"scriptpubkey_address": "bc1qreceiver", "value": 49900000},
                    {"scriptpubkey_address": "bc1qchange", "value": 50000},
                ],
            },
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_http.return_value = mock_client

        resp = client.get("/api/chains/bitcoin/bc1qTestAddress")
        assert resp.status_code == 200
        data = resp.json()

        assert data["chain"] == "bitcoin"
        assert data["count"] == 1
        tx = data["transactions"][0]
        assert tx["tx_hash"] == "btctx123"
        assert tx["chain"] == "bitcoin"
        assert tx["token_symbol"] == "BTC"
        assert "inputs" in tx
        assert "outputs" in tx

    def test_evm_proxy_unsupported_chain(self, client):
        """Test requesting an unsupported EVM chain returns 400."""
        resp = client.get("/api/chains/evm/notachain/0xTestAddress")
        assert resp.status_code == 400

    def test_evm_proxy_invalid_action(self, client):
        """Test requesting an invalid action returns 400."""
        resp = client.get("/api/chains/evm/ethereum/0xTestAddress?action=dangerous")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 3. Price cache
# ---------------------------------------------------------------------------

class TestPriceCache:
    @patch("src.web.routes.chain_proxy._get_http")
    def test_price_cache_hit(self, mock_get_http, client):
        """Test that second price request within 5min uses cache."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bitcoin": {"usd": 65000.50},
            "ethereum": {"usd": 3500.25},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_http.return_value = mock_client

        # First request - should hit upstream
        resp1 = client.get("/api/chains/prices?ids=bitcoin,ethereum")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["cached"] is False
        assert "bitcoin_usd" in data1["prices"]

        # Second request - should use cache
        resp2 = client.get("/api/chains/prices?ids=bitcoin,ethereum")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["cached"] is True
        assert data2["prices"] == data1["prices"]

        # Upstream should only have been called once
        assert mock_client.get.call_count == 1

    @patch("src.web.routes.chain_proxy._get_http")
    def test_price_cache_expired(self, mock_get_http, client):
        """Test that cache expires after TTL."""
        from src.web.routes import chain_proxy

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bitcoin": {"usd": 65000}}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_get_http.return_value = mock_client

        # First request
        resp1 = client.get("/api/chains/prices?ids=bitcoin")
        assert resp1.status_code == 200
        assert resp1.json()["cached"] is False

        # Manually expire the cache
        for key in list(chain_proxy._price_cache.keys()):
            ts, data = chain_proxy._price_cache[key]
            chain_proxy._price_cache[key] = (ts - 400, data)  # expired 400s ago

        # Second request - cache expired, should hit upstream again
        resp2 = client.get("/api/chains/prices?ids=bitcoin")
        assert resp2.status_code == 200
        assert resp2.json()["cached"] is False
        assert mock_client.get.call_count == 2


# ---------------------------------------------------------------------------
# 4. Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_rate_limit_enforcement(self, client):
        """Test that exceeding 100 req/min triggers 429."""
        from src.web.routes import chain_proxy

        # Manually fill the bucket for dev-user to 100 entries (all within last 10s)
        user_id = "dev-user"
        now = time.time()
        chain_proxy._user_buckets[user_id] = [now - (i * 0.1) for i in range(100)]

        # Next request should be rate limited
        resp = client.get("/api/chains/supported")
        # /supported doesn't use rate limiting (no auth required in the route)
        # Use an endpoint that does rate limiting
        resp = client.get("/api/chains/evm/ethereum/0xTest")
        assert resp.status_code == 429
        assert "Rate limit" in resp.json()["detail"]

    def test_rate_limit_allows_normal_usage(self, client):
        """Test that normal usage is not rate limited."""
        # /supported doesn't require auth or rate limiting
        resp = client.get("/api/chains/supported")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. Billing webhook signature verification
# ---------------------------------------------------------------------------

class TestBillingWebhook:
    def test_webhook_rejects_invalid_signature(self, client):
        """Test that webhook rejects requests with invalid Stripe signature."""
        with patch("src.web.routes.billing.STRIPE_WEBHOOK_SECRET", "whsec_test123"):
            resp = client.post(
                "/api/billing/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={"stripe-signature": "invalid_sig"},
            )
            assert resp.status_code == 400
            assert "Invalid Stripe signature" in resp.json()["detail"]

    def test_webhook_rejects_missing_secret(self, client):
        """Test that webhook returns 503 when secret not configured."""
        with patch("src.web.routes.billing.STRIPE_WEBHOOK_SECRET", ""):
            resp = client.post(
                "/api/billing/webhook",
                content=b'{}',
                headers={"stripe-signature": "test"},
            )
            assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 6. Auth JWT validation
# ---------------------------------------------------------------------------

class TestAuth:
    def test_dev_mode_returns_user(self, client):
        """In dev mode (no SUPABASE_URL), /api/auth/user returns dev user."""
        with patch("src.web.routes.auth.SUPABASE_URL", ""):
            resp = client.get("/api/auth/user")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "dev-user"
            assert data["tier"] == "unlimited"

    def test_auth_rejects_missing_bearer(self, client):
        """Test that auth rejects requests without Bearer token when Supabase is configured."""
        with patch("src.web.routes.auth.SUPABASE_URL", "https://test.supabase.co"):
            resp = client.get(
                "/api/auth/user",
                headers={"Authorization": "not-bearer-token"},
            )
            assert resp.status_code == 401

    def test_billing_status_dev_mode(self, client):
        """Test billing status returns tier info in dev mode."""
        with patch("src.web.routes.auth.SUPABASE_URL", ""):
            resp = client.get("/api/billing/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["tier"] == "unlimited"
            assert "limits" in data

    def test_billing_tiers_public(self, client):
        """Test that tier definitions are publicly accessible."""
        resp = client.get("/api/billing/tiers")
        assert resp.status_code == 200
        data = resp.json()
        assert "free" in data
        assert "pro" in data
        assert "unlimited" in data


# ---------------------------------------------------------------------------
# 7. Accountant slim routes
# ---------------------------------------------------------------------------

class TestAccountantSlim:
    def test_register_requires_auth(self, client):
        """Test that accountant registration requires auth."""
        # In dev mode, auth is bypassed, so this should work with mock repo
        # Just verify the endpoint exists and returns a valid response shape
        with patch("src.web.routes.auth.SUPABASE_URL", "https://test.supabase.co"):
            resp = client.post(
                "/api/accountant/register",
                json={"firm_name": "Test CPA", "license_number": "CPA-123"},
            )
            # Should fail auth (no valid bearer)
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 8. Old monolith endpoints are NOT present
# ---------------------------------------------------------------------------

class TestRemovedEndpoints:
    def test_no_import_endpoint(self, client):
        """Verify /api/import is not in the slim server."""
        resp = client.post("/api/import", json={"address": "0x123", "chain": "ethereum"})
        assert resp.status_code in (404, 405)

    def test_no_calculate_endpoint(self, client):
        """Verify /api/calculate is not in the slim server."""
        resp = client.post("/api/calculate", json={"method": "FIFO", "year": 2025})
        assert resp.status_code in (404, 405)

    def test_no_transactions_endpoint(self, client):
        """Verify /api/transactions is not in the slim server."""
        resp = client.get("/api/transactions")
        assert resp.status_code in (404, 405)

    def test_no_reports_endpoint(self, client):
        """Verify /api/reports/* is not in the slim server."""
        resp = client.get("/api/reports/form8949")
        assert resp.status_code in (404, 405)

    def test_no_wallets_endpoint(self, client):
        """Verify /api/wallets is not in the slim server."""
        resp = client.get("/api/wallets")
        assert resp.status_code in (404, 405)

    def test_no_harvest_endpoint(self, client):
        """Verify /api/harvest/* is not in the slim server."""
        resp = client.get("/api/harvest/positions")
        assert resp.status_code in (404, 405)

    def test_no_reconciliation_endpoint(self, client):
        """Verify /api/reconciliation/* is not in the slim server."""
        resp = client.post("/api/reconciliation/upload")
        assert resp.status_code in (404, 405, 422)
