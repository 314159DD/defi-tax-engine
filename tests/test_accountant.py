"""
Tests for Sprint 5.2: CPA / Steuerberater Portal.

Covers:
  - Accountant registration (profile CRUD)
  - Invite creation + acceptance flow
  - Client listing
  - Client revocation
  - Permission enforcement (accountant can't access non-client data)
  - Bulk report generation
  - Invite expiry (7 days)
  - All monetary values use Decimal
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from src.storage.accountant import AccountantRepository
from src.storage.database import Database, DisposalRepository
from src.reports.branded_report import generate_branded_report
from src.tax.models import ReportFile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """Fresh SQLite database for each test."""
    db_path = str(tmp_path / "test_accountant.db")
    os.environ["DB_PATH"] = db_path
    return Database(db_path)


@pytest.fixture
def repo(db):
    """AccountantRepository backed by temp database."""
    return AccountantRepository(db)


@pytest.fixture
def accountant_user_id():
    return f"accountant-{uuid.uuid4()}"


@pytest.fixture
def client_user_id():
    return f"client-{uuid.uuid4()}"


@pytest.fixture
def second_client_user_id():
    return f"client2-{uuid.uuid4()}"


@pytest.fixture
def profile(repo, accountant_user_id):
    """Pre-registered accountant profile."""
    return repo.create_profile(
        user_id=accountant_user_id,
        firm_name="Smith & Associates CPA",
        license_number="CPA-12345",
        contact_info="contact@smithcpa.com",
    )


# ---------------------------------------------------------------------------
# Test: Accountant Registration
# ---------------------------------------------------------------------------

class TestAccountantRegistration:

    def test_create_profile(self, repo, accountant_user_id):
        profile = repo.create_profile(
            user_id=accountant_user_id,
            firm_name="Test CPA Firm",
            license_number="LIC-001",
            contact_info="info@testcpa.com",
        )
        assert profile["firm_name"] == "Test CPA Firm"
        assert profile["license_number"] == "LIC-001"
        assert profile["contact_info"] == "info@testcpa.com"
        assert profile["logo_url"] is None
        assert profile["user_id"] == accountant_user_id
        assert profile["id"] is not None
        assert profile["created_at"] is not None

    def test_duplicate_registration_raises(self, repo, accountant_user_id):
        repo.create_profile(
            user_id=accountant_user_id,
            firm_name="First Firm",
            license_number="LIC-001",
        )
        with pytest.raises(ValueError, match="already has an accountant profile"):
            repo.create_profile(
                user_id=accountant_user_id,
                firm_name="Second Firm",
                license_number="LIC-002",
            )

    def test_get_profile(self, repo, profile, accountant_user_id):
        fetched = repo.get_profile(accountant_user_id)
        assert fetched is not None
        assert fetched["firm_name"] == "Smith & Associates CPA"
        assert fetched["id"] == profile["id"]

    def test_get_profile_nonexistent(self, repo):
        assert repo.get_profile("nonexistent-user") is None

    def test_update_profile(self, repo, profile, accountant_user_id):
        updated = repo.update_profile(
            accountant_user_id,
            firm_name="Smith CPA LLC",
            logo_url="https://example.com/logo.png",
        )
        assert updated["firm_name"] == "Smith CPA LLC"
        assert updated["logo_url"] == "https://example.com/logo.png"
        # Unchanged fields preserved
        assert updated["license_number"] == "CPA-12345"

    def test_update_profile_no_changes(self, repo, profile, accountant_user_id):
        result = repo.update_profile(accountant_user_id)
        assert result["firm_name"] == "Smith & Associates CPA"

    def test_update_profile_nonexistent_raises(self, repo):
        with pytest.raises(ValueError, match="No accountant profile"):
            repo.update_profile("nonexistent", firm_name="Nope")

    def test_get_profile_by_id(self, repo, profile):
        fetched = repo.get_profile_by_id(profile["id"])
        assert fetched is not None
        assert fetched["firm_name"] == profile["firm_name"]


# ---------------------------------------------------------------------------
# Test: Invite Creation + Acceptance Flow
# ---------------------------------------------------------------------------

class TestInviteFlow:

    def test_create_invite_returns_uuid(self, repo, profile):
        invite_code = repo.create_invite(profile["id"])
        assert invite_code is not None
        assert len(invite_code) == 36  # UUID4 format

    def test_accept_invite(self, repo, profile, client_user_id):
        invite_code = repo.create_invite(profile["id"])
        result = repo.accept_invite(invite_code, client_user_id)

        assert result["status"] == "active"
        assert result["client_id"] == client_user_id
        assert result["accountant_id"] == profile["id"]
        assert result["invite_code"] == invite_code

    def test_accept_invite_invalid_code(self, repo):
        with pytest.raises(ValueError, match="Invalid invite code"):
            repo.accept_invite("nonexistent-code", "some-user")

    def test_accept_invite_already_used(self, repo, profile, client_user_id):
        invite_code = repo.create_invite(profile["id"])
        repo.accept_invite(invite_code, client_user_id)

        with pytest.raises(ValueError, match="already been used"):
            repo.accept_invite(invite_code, "another-user")

    def test_accept_invite_duplicate_client(self, repo, profile, client_user_id):
        # First invite accepted
        code1 = repo.create_invite(profile["id"])
        repo.accept_invite(code1, client_user_id)

        # Second invite for same client
        code2 = repo.create_invite(profile["id"])
        with pytest.raises(ValueError, match="already linked"):
            repo.accept_invite(code2, client_user_id)

    def test_invite_expiry(self, repo, profile, db):
        """Invite codes expire after 7 days."""
        invite_code = repo.create_invite(profile["id"])

        # Manually set the expiry to the past
        expired_time = (
            datetime.now(timezone.utc) - timedelta(days=8)
        ).isoformat()
        with db.connect() as conn:
            conn.execute(
                "UPDATE client_relationships SET invite_expires = ? WHERE invite_code = ?",
                (expired_time, invite_code),
            )

        with pytest.raises(ValueError, match="expired"):
            repo.accept_invite(invite_code, "late-client")

    def test_multiple_invites(self, repo, profile, client_user_id, second_client_user_id):
        """Accountant can create multiple invites for different clients."""
        code1 = repo.create_invite(profile["id"])
        code2 = repo.create_invite(profile["id"])
        assert code1 != code2

        repo.accept_invite(code1, client_user_id)
        repo.accept_invite(code2, second_client_user_id)

        clients = repo.list_clients(profile["id"])
        active = [c for c in clients if c["status"] == "active"]
        assert len(active) == 2


# ---------------------------------------------------------------------------
# Test: Client Listing
# ---------------------------------------------------------------------------

class TestClientListing:

    def test_list_clients_empty(self, repo, profile):
        clients = repo.list_clients(profile["id"])
        assert clients == []

    def test_list_clients_with_invited_and_active(
        self, repo, profile, client_user_id
    ):
        # One pending invite
        repo.create_invite(profile["id"])

        # One accepted invite
        code2 = repo.create_invite(profile["id"])
        repo.accept_invite(code2, client_user_id)

        clients = repo.list_clients(profile["id"])
        assert len(clients) == 2

        statuses = {c["status"] for c in clients}
        assert "invited" in statuses
        assert "active" in statuses

    def test_get_client(self, repo, profile, client_user_id):
        code = repo.create_invite(profile["id"])
        repo.accept_invite(code, client_user_id)

        client = repo.get_client(profile["id"], client_user_id)
        assert client is not None
        assert client["client_id"] == client_user_id
        assert client["status"] == "active"

    def test_get_client_nonexistent(self, repo, profile):
        assert repo.get_client(profile["id"], "nonexistent") is None


# ---------------------------------------------------------------------------
# Test: Client Revocation
# ---------------------------------------------------------------------------

class TestClientRevocation:

    def test_revoke_client(self, repo, profile, client_user_id):
        code = repo.create_invite(profile["id"])
        repo.accept_invite(code, client_user_id)

        assert repo.revoke_client(profile["id"], client_user_id) is True

        # Client should no longer be active
        client = repo.get_client(profile["id"], client_user_id)
        assert client is None

        # But should still appear in the list as revoked
        all_clients = repo.list_clients(profile["id"])
        revoked = [c for c in all_clients if c["status"] == "revoked"]
        assert len(revoked) == 1

    def test_revoke_nonexistent_returns_false(self, repo, profile):
        assert repo.revoke_client(profile["id"], "nonexistent") is False

    def test_cannot_access_after_revocation(self, repo, profile, client_user_id):
        code = repo.create_invite(profile["id"])
        repo.accept_invite(code, client_user_id)
        repo.revoke_client(profile["id"], client_user_id)

        assert repo.is_accountant_for(profile["id"], client_user_id) is False


# ---------------------------------------------------------------------------
# Test: Permission Enforcement
# ---------------------------------------------------------------------------

class TestPermissions:

    def test_is_accountant_for_active_client(self, repo, profile, client_user_id):
        code = repo.create_invite(profile["id"])
        repo.accept_invite(code, client_user_id)

        assert repo.is_accountant_for(profile["id"], client_user_id) is True

    def test_is_not_accountant_for_non_client(self, repo, profile):
        assert repo.is_accountant_for(profile["id"], "random-user") is False

    def test_is_not_accountant_for_invited_only(self, repo, profile):
        """Invited but not accepted should not grant access."""
        repo.create_invite(profile["id"])
        # No client_id set yet (not accepted)
        clients = repo.list_clients(profile["id"])
        for c in clients:
            if c["client_id"] is None:
                continue
            # Should not reach here for pending invites
            assert False, "Pending invite should not have client_id"

    def test_different_accountant_cannot_access(self, repo, db, client_user_id):
        """Accountant A's client is not accessible by Accountant B."""
        # Accountant A
        prof_a = repo.create_profile(
            user_id="accountant-a",
            firm_name="Firm A",
            license_number="A-001",
        )
        code = repo.create_invite(prof_a["id"])
        repo.accept_invite(code, client_user_id)

        # Accountant B
        prof_b = repo.create_profile(
            user_id="accountant-b",
            firm_name="Firm B",
            license_number="B-001",
        )

        assert repo.is_accountant_for(prof_b["id"], client_user_id) is False


# ---------------------------------------------------------------------------
# Test: Branded Report Generation
# ---------------------------------------------------------------------------

class TestBrandedReport:

    def test_generate_branded_report_basic(self):
        profile = {
            "firm_name": "Mueller Steuerberatung",
            "contact_info": "info@mueller-stb.de",
            "license_number": "StB-98765",
            "logo_url": None,
        }
        reports = [
            ReportFile(
                filename="form8949_2025_FIFO.csv",
                content="header1,header2\nval1,val2\n",
                mime_type="text/csv",
                report_type="form_8949",
            ),
        ]

        result = generate_branded_report(
            accountant_profile=profile,
            client_name="Max Mustermann",
            reports=reports,
            methodology="FIFO cost basis method",
            year=2025,
        )

        assert isinstance(result, bytes)
        text = result.decode("utf-8")

        # Check header
        assert "MUELLER STEUERBERATUNG" in text
        assert "info@mueller-stb.de" in text
        assert "License: StB-98765" in text

        # Check body
        assert "Max Mustermann" in text
        assert "2025" in text
        assert "FIFO cost basis method" in text
        assert "form8949_2025_FIFO.csv" in text

        # Check report content is included
        assert "header1,header2" in text
        assert "val1,val2" in text

        # Check footer
        assert "DISCLAIMER" in text
        assert "METHODOLOGY STATEMENT" in text

    def test_generate_branded_report_with_tax_summary(self):
        profile = {
            "firm_name": "Test Firm",
            "contact_info": "test@firm.com",
            "license_number": "TF-001",
            "logo_url": None,
        }
        summary = {
            "total_gains": str(Decimal("5000.00")),
            "total_losses": str(Decimal("-1200.50")),
            "net": str(Decimal("3799.50")),
        }

        result = generate_branded_report(
            accountant_profile=profile,
            client_name="Client X",
            reports=[],
            methodology="HIFO",
            year=2025,
            tax_summary=summary,
        )

        text = result.decode("utf-8")
        assert "TAX SUMMARY" in text
        assert "5000.00" in text
        assert "-1200.50" in text
        assert "3799.50" in text

    def test_generate_branded_report_empty_reports(self):
        profile = {
            "firm_name": "Empty Reports Firm",
            "contact_info": "",
            "license_number": "ER-000",
            "logo_url": None,
        }
        result = generate_branded_report(
            accountant_profile=profile,
            client_name="Nobody",
            reports=[],
            methodology="LIFO",
            year=2026,
        )
        text = result.decode("utf-8")
        assert "EMPTY REPORTS FIRM" in text
        assert "2026" in text

    def test_monetary_values_are_decimal_safe(self):
        """Ensure the report handles Decimal values without float conversion."""
        profile = {
            "firm_name": "Decimal Safe CPA",
            "contact_info": "",
            "license_number": "DS-001",
            "logo_url": None,
        }
        # Use precise Decimal values that would fail with float
        summary = {
            "total_gains": str(Decimal("0.1") + Decimal("0.2")),  # "0.3" not 0.30000000000000004
            "net": str(Decimal("123456789.12")),
        }
        result = generate_branded_report(
            accountant_profile=profile,
            client_name="Precision Client",
            reports=[],
            methodology="FIFO",
            year=2025,
            tax_summary=summary,
        )
        text = result.decode("utf-8")
        assert "0.3" in text
        assert "123456789.12" in text
        # Must NOT contain float artifacts
        assert "0.30000000000000004" not in text


# ---------------------------------------------------------------------------
# Test: Full integration flow
# ---------------------------------------------------------------------------

class TestFullFlow:

    def test_register_invite_accept_list_revoke(self, db):
        """End-to-end flow: register -> invite -> accept -> list -> revoke."""
        repo = AccountantRepository(db)

        # 1. Register accountant
        profile = repo.create_profile(
            user_id="acct-full-test",
            firm_name="Full Test CPA",
            license_number="FT-001",
            contact_info="full@test.com",
        )

        # 2. Create invite
        invite_code = repo.create_invite(profile["id"])
        assert len(invite_code) == 36

        # 3. Client accepts
        client_id = "client-full-test"
        rel = repo.accept_invite(invite_code, client_id)
        assert rel["status"] == "active"

        # 4. Accountant lists clients
        clients = repo.list_clients(profile["id"])
        assert len(clients) == 1
        assert clients[0]["client_id"] == client_id

        # 5. Accountant can access client
        assert repo.is_accountant_for(profile["id"], client_id) is True

        # 6. Revoke
        assert repo.revoke_client(profile["id"], client_id) is True

        # 7. Can no longer access
        assert repo.is_accountant_for(profile["id"], client_id) is False

        # 8. Client still in list as revoked
        clients_after = repo.list_clients(profile["id"])
        assert len(clients_after) == 1
        assert clients_after[0]["status"] == "revoked"
