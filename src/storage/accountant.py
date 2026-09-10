"""
Accountant / CPA portal storage layer.

Tables:
    accountant_profiles    - one row per accountant (linked to user_id)
    client_relationships   - accountant <-> client connections with invite codes

All monetary values are stored as TEXT and loaded as Decimal.
Tables are created on first use (same pattern as database.py).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.storage.database import Database, _now_iso


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

ACCOUNTANT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accountant_profiles (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL UNIQUE,
    firm_name       TEXT NOT NULL,
    license_number  TEXT NOT NULL,
    contact_info    TEXT,
    logo_url        TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS client_relationships (
    id              TEXT PRIMARY KEY,
    accountant_id   TEXT NOT NULL,
    client_id       TEXT,
    status          TEXT NOT NULL DEFAULT 'invited',
    invite_code     TEXT UNIQUE,
    invite_expires  TEXT,
    created_at      TEXT NOT NULL,
    FOREIGN KEY (accountant_id) REFERENCES accountant_profiles(id)
);

CREATE INDEX IF NOT EXISTS idx_client_rel_accountant
    ON client_relationships(accountant_id);
CREATE INDEX IF NOT EXISTS idx_client_rel_invite
    ON client_relationships(invite_code);
CREATE INDEX IF NOT EXISTS idx_client_rel_client
    ON client_relationships(client_id);
"""

# Invite codes expire after 7 days
_INVITE_EXPIRY_DAYS = 7


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class AccountantRepository:
    """CRUD for accountant profiles and client relationships."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._db.connect() as conn:
            conn.executescript(ACCOUNTANT_SCHEMA_SQL)

    # ── Profile management ─────────────────────────────────────────────

    def create_profile(
        self,
        user_id: str,
        firm_name: str,
        license_number: str,
        contact_info: str | None = None,
    ) -> dict:
        """
        Create an accountant profile for the given user.

        Raises ValueError if the user already has an accountant profile.
        """
        profile_id = str(uuid.uuid4())
        now = _now_iso()
        with self._db.connect() as conn:
            # Check for existing profile
            existing = conn.execute(
                "SELECT id FROM accountant_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if existing:
                raise ValueError(f"User {user_id} already has an accountant profile")

            conn.execute(
                """
                INSERT INTO accountant_profiles
                    (id, user_id, firm_name, license_number, contact_info, logo_url, created_at)
                VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (profile_id, user_id, firm_name, license_number, contact_info, now),
            )
        return {
            "id": profile_id,
            "user_id": user_id,
            "firm_name": firm_name,
            "license_number": license_number,
            "contact_info": contact_info,
            "logo_url": None,
            "created_at": now,
        }

    def get_profile(self, user_id: str) -> Optional[dict]:
        """Return the accountant profile for the given user, or None."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM accountant_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_profile_by_id(self, profile_id: str) -> Optional[dict]:
        """Return the accountant profile by its ID."""
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM accountant_profiles WHERE id = ?",
                (profile_id,),
            ).fetchone()
        return dict(row) if row else None

    def update_profile(self, user_id: str, **kwargs: str | None) -> dict:
        """
        Update accountant profile fields.

        Allowed fields: firm_name, license_number, contact_info, logo_url.
        Returns the updated profile dict.

        Raises ValueError if the user has no accountant profile.
        """
        allowed = {"firm_name", "license_number", "contact_info", "logo_url"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

        if not updates:
            profile = self.get_profile(user_id)
            if not profile:
                raise ValueError(f"No accountant profile for user {user_id}")
            return profile

        set_clauses = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [user_id]

        with self._db.connect() as conn:
            cursor = conn.execute(
                f"UPDATE accountant_profiles SET {set_clauses} WHERE user_id = ?",
                values,
            )
            if cursor.rowcount == 0:
                raise ValueError(f"No accountant profile for user {user_id}")

        return self.get_profile(user_id)  # type: ignore[return-value]

    # ── Invite management ──────────────────────────────────────────────

    def create_invite(self, accountant_id: str) -> str:
        """
        Generate a unique invite code for the accountant.

        Returns the invite_code (UUID4 string).
        The invite expires after 7 days.
        """
        invite_code = str(uuid.uuid4())
        rel_id = str(uuid.uuid4())
        now = _now_iso()
        expires = (
            datetime.now(timezone.utc) + timedelta(days=_INVITE_EXPIRY_DAYS)
        ).isoformat()

        with self._db.connect() as conn:
            conn.execute(
                """
                INSERT INTO client_relationships
                    (id, accountant_id, client_id, status, invite_code, invite_expires, created_at)
                VALUES (?, ?, NULL, 'invited', ?, ?, ?)
                """,
                (rel_id, accountant_id, invite_code, expires, now),
            )
        return invite_code

    def accept_invite(self, invite_code: str, client_user_id: str) -> dict:
        """
        Client accepts an invite code, granting the accountant read access.

        Returns the updated relationship dict.

        Raises:
            ValueError: if the invite code is invalid, expired, or already used.
        """
        with self._db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM client_relationships WHERE invite_code = ?",
                (invite_code,),
            ).fetchone()

            if not row:
                raise ValueError("Invalid invite code")

            rel = dict(row)

            if rel["status"] != "invited":
                raise ValueError("Invite has already been used or revoked")

            # Check expiry
            if rel["invite_expires"]:
                expires = datetime.fromisoformat(rel["invite_expires"])
                if datetime.now(timezone.utc) > expires:
                    raise ValueError("Invite has expired")

            # Check that this client isn't already linked to this accountant
            existing = conn.execute(
                """
                SELECT id FROM client_relationships
                WHERE accountant_id = ? AND client_id = ? AND status = 'active'
                """,
                (rel["accountant_id"], client_user_id),
            ).fetchone()
            if existing:
                raise ValueError("Client is already linked to this accountant")

            conn.execute(
                """
                UPDATE client_relationships
                SET client_id = ?, status = 'active'
                WHERE id = ?
                """,
                (client_user_id, rel["id"]),
            )

        return {
            "id": rel["id"],
            "accountant_id": rel["accountant_id"],
            "client_id": client_user_id,
            "status": "active",
            "invite_code": invite_code,
            "created_at": rel["created_at"],
        }

    # ── Client management ──────────────────────────────────────────────

    def list_clients(self, accountant_id: str) -> list[dict]:
        """Return all client relationships for the accountant."""
        with self._db.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM client_relationships
                WHERE accountant_id = ?
                ORDER BY created_at DESC
                """,
                (accountant_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_client(self, accountant_id: str, client_id: str) -> Optional[dict]:
        """Return a specific client relationship, or None."""
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM client_relationships
                WHERE accountant_id = ? AND client_id = ? AND status = 'active'
                """,
                (accountant_id, client_id),
            ).fetchone()
        return dict(row) if row else None

    def revoke_client(self, accountant_id: str, client_id: str) -> bool:
        """
        Revoke access for a client. Returns True if a row was updated.
        """
        with self._db.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE client_relationships
                SET status = 'revoked'
                WHERE accountant_id = ? AND client_id = ? AND status = 'active'
                """,
                (accountant_id, client_id),
            )
        return cursor.rowcount > 0

    def is_accountant_for(self, accountant_id: str, client_id: str) -> bool:
        """Check if the accountant has active access to the given client."""
        with self._db.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM client_relationships
                WHERE accountant_id = ? AND client_id = ? AND status = 'active'
                """,
                (accountant_id, client_id),
            ).fetchone()
        return row is not None
