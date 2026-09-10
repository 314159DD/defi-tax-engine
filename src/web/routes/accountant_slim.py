"""
Slim CPA / Accountant portal routes.

Keeps the invite/accept/list/revoke flow from accountant.py
BUT removes all report generation endpoints (client generates reports now).

Routes kept:
    POST   /api/accountant/register                    - register as accountant
    GET    /api/accountant/profile                      - get accountant profile
    PUT    /api/accountant/profile                      - update profile
    POST   /api/accountant/clients/invite               - generate invite link
    GET    /api/accountant/clients                      - list all clients
    GET    /api/accountant/clients/{client_id}           - client detail
    DELETE /api/accountant/clients/{client_id}           - revoke access
    POST   /api/accountant/invite/{invite_code}/accept  - client accepts invite

Removed (client-side now):
    POST   /api/accountant/clients/reports              - bulk report generation
    GET    /api/accountant/clients/{client_id}/reports   - download client reports
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.web.routes.auth import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/accountant", tags=["accountant"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_response(data: Any, status_code: int = 200) -> JSONResponse:
    """Decimal-safe JSON response."""
    class _Enc(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return str(obj)
            return super().default(obj)
    content = json.loads(json.dumps(data, cls=_Enc))
    return JSONResponse(content=content, status_code=status_code)


def _get_accountant_repo():
    """Late import to avoid circular dependency issues."""
    from src.storage.accountant import AccountantRepository
    from src.storage.database import Database
    from src.config import DB_PATH
    db = Database(DB_PATH)
    return AccountantRepository(db)


# ---------------------------------------------------------------------------
# Dependency: require accountant role
# ---------------------------------------------------------------------------

async def require_accountant(user: dict = Depends(verify_jwt)) -> dict:
    """Ensure the current user has an accountant profile."""
    repo = _get_accountant_repo()
    profile = repo.get_profile(user["sub"])
    if not profile:
        raise HTTPException(
            status_code=403,
            detail="You must register as an accountant first.",
        )
    user["accountant_profile"] = profile
    return user


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    firm_name: str
    license_number: str
    contact_info: Optional[str] = None


class ProfileUpdate(BaseModel):
    firm_name: Optional[str] = None
    license_number: Optional[str] = None
    contact_info: Optional[str] = None
    logo_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register_accountant(
    body: RegisterRequest,
    user: dict = Depends(verify_jwt),
):
    """Register the current user as an accountant."""
    repo = _get_accountant_repo()
    try:
        profile = repo.create_profile(
            user_id=user["sub"],
            firm_name=body.firm_name,
            license_number=body.license_number,
            contact_info=body.contact_info,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _json_response(profile, status_code=201)


@router.get("/profile")
async def get_profile(user: dict = Depends(require_accountant)):
    """Return the accountant's profile."""
    return _json_response(user["accountant_profile"])


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: dict = Depends(require_accountant),
):
    """Update the accountant's profile fields."""
    repo = _get_accountant_repo()
    updates = body.model_dump(exclude_none=True)
    try:
        profile = repo.update_profile(user["sub"], **updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _json_response(profile)


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------

@router.post("/clients/invite")
async def create_invite(user: dict = Depends(require_accountant)):
    """Generate a unique invite link for a client."""
    repo = _get_accountant_repo()
    profile = user["accountant_profile"]
    invite_code = repo.create_invite(profile["id"])
    return _json_response({
        "invite_code": invite_code,
        "invite_url": f"/accountant/invite/{invite_code}",
        "expires_in_days": 7,
    })


@router.get("/clients")
async def list_clients(user: dict = Depends(require_accountant)):
    """List all clients with their status."""
    repo = _get_accountant_repo()
    profile = user["accountant_profile"]
    clients = repo.list_clients(profile["id"])

    enriched = []
    for c in clients:
        enriched.append({
            "id": c["id"],
            "client_id": c["client_id"],
            "status": c["status"],
            "invite_code": c["invite_code"],
            "created_at": c["created_at"],
        })

    return _json_response(enriched)


@router.get("/clients/{client_id}")
async def get_client_detail(
    client_id: str,
    user: dict = Depends(require_accountant),
):
    """Get info about a specific client (no report data - client generates reports now)."""
    repo = _get_accountant_repo()
    profile = user["accountant_profile"]

    if not repo.is_accountant_for(profile["id"], client_id):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this client.",
        )

    client_rel = repo.get_client(profile["id"], client_id)
    if not client_rel:
        raise HTTPException(status_code=404, detail="Client not found")

    return _json_response({"relationship": client_rel})


@router.delete("/clients/{client_id}", status_code=204)
async def revoke_client(
    client_id: str,
    user: dict = Depends(require_accountant),
):
    """Revoke access to a client."""
    repo = _get_accountant_repo()
    profile = user["accountant_profile"]

    if not repo.revoke_client(profile["id"], client_id):
        raise HTTPException(
            status_code=404,
            detail="No active relationship found for this client.",
        )
    return None


# ---------------------------------------------------------------------------
# Client accepts invite
# ---------------------------------------------------------------------------

@router.post("/invite/{invite_code}/accept")
async def accept_invite(
    invite_code: str,
    user: dict = Depends(verify_jwt),
):
    """Client accepts an accountant's invite, granting read access."""
    repo = _get_accountant_repo()
    try:
        relationship = repo.accept_invite(invite_code, user["sub"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _json_response(relationship)
