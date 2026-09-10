"""
Accountant / CPA portal API routes.

Routes:
    POST   /api/accountant/register             - register as accountant
    GET    /api/accountant/profile               - get accountant profile
    PUT    /api/accountant/profile               - update profile
    POST   /api/accountant/clients/invite        - generate invite link
    GET    /api/accountant/clients               - list all clients
    GET    /api/accountant/clients/{client_id}   - client detail
    DELETE /api/accountant/clients/{client_id}   - revoke access
    POST   /api/accountant/invite/{invite_code}/accept - client accepts invite
    POST   /api/accountant/clients/reports       - bulk report generation
    GET    /api/accountant/clients/{client_id}/reports - download client reports

All monetary values returned as strings (Decimal-safe).
"""
from __future__ import annotations

import io
import json
import zipfile
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.storage.accountant import AccountantRepository
from src.storage.database import Database, DisposalRepository, WalletRepository
from src.tax import get_tax_module

router = APIRouter(prefix="/api/accountant", tags=["accountant"])


# ---------------------------------------------------------------------------
# Helpers - imported lazily from app to avoid circular imports
# ---------------------------------------------------------------------------

def _get_db():
    """Late import to avoid circular dependency with app.py."""
    from src.web.app import get_db
    return get_db()


async def _verify_user(authorization: str = Header(default="")) -> dict:
    """Verify token with late import to avoid circular dependency."""
    from src.web.app import verify_token
    return await verify_token(authorization=authorization)


def _json_response(data: Any, status_code: int = 200) -> JSONResponse:
    """Decimal-safe JSON response."""

    class _Enc(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Decimal):
                return str(obj)
            return super().default(obj)

    content = json.loads(json.dumps(data, cls=_Enc))
    return JSONResponse(content=content, status_code=status_code)


def _get_accountant_repo(db: Database) -> AccountantRepository:
    return AccountantRepository(db)


# ---------------------------------------------------------------------------
# Dependency: require accountant role
# ---------------------------------------------------------------------------

async def require_accountant(
    user: dict = Depends(_verify_user),
    db: Database = Depends(_get_db),
) -> dict:
    """
    Dependency that ensures the current user has an accountant profile.
    Returns the user dict augmented with 'accountant_profile'.
    """
    repo = _get_accountant_repo(db)
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


class BulkReportRequest(BaseModel):
    client_ids: list[str]
    year: int = 2025
    method: str = "FIFO"
    country: str = "US"


# ---------------------------------------------------------------------------
# Account management
# ---------------------------------------------------------------------------

@router.post("/register", status_code=201)
async def register_accountant(
    body: RegisterRequest,
    user: dict = Depends(_verify_user),
    db: Database = Depends(_get_db),
):
    """Register the current user as an accountant."""
    repo = _get_accountant_repo(db)
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
async def get_profile(
    user: dict = Depends(require_accountant),
):
    """Return the accountant's profile."""
    return _json_response(user["accountant_profile"])


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """Update the accountant's profile fields."""
    repo = _get_accountant_repo(db)
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
async def create_invite(
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """Generate a unique invite link for a client."""
    repo = _get_accountant_repo(db)
    profile = user["accountant_profile"]
    invite_code = repo.create_invite(profile["id"])
    return _json_response({
        "invite_code": invite_code,
        "invite_url": f"/accountant/invite/{invite_code}",
        "expires_in_days": 7,
    })


@router.get("/clients")
async def list_clients(
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """List all clients with their status."""
    repo = _get_accountant_repo(db)
    profile = user["accountant_profile"]
    clients = repo.list_clients(profile["id"])

    # Enrich with summary data for active clients
    enriched = []
    for c in clients:
        client_data = {
            "id": c["id"],
            "client_id": c["client_id"],
            "status": c["status"],
            "invite_code": c["invite_code"],
            "created_at": c["created_at"],
        }
        if c["status"] == "active" and c["client_id"]:
            wallet_repo = WalletRepository(db)
            # Count wallets (all wallets are shared in single-user SQLite)
            wallets = wallet_repo.get_all()
            client_data["wallet_count"] = len(wallets)
        enriched.append(client_data)

    return _json_response(enriched)


@router.get("/clients/{client_id}")
async def get_client_detail(
    client_id: str,
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """Get detailed info about a specific client."""
    repo = _get_accountant_repo(db)
    profile = user["accountant_profile"]

    if not repo.is_accountant_for(profile["id"], client_id):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this client.",
        )

    client_rel = repo.get_client(profile["id"], client_id)
    if not client_rel:
        raise HTTPException(status_code=404, detail="Client not found")

    # Get wallet count and basic tax summary
    wallet_repo = WalletRepository(db)
    disposal_repo = DisposalRepository(db)

    wallets = wallet_repo.get_all()
    disposals = disposal_repo.get_all()

    total_gains = sum(
        (Decimal(d["gain_loss_usd"]) for d in disposals if Decimal(d["gain_loss_usd"]) > 0),
        Decimal("0"),
    )
    total_losses = sum(
        (Decimal(d["gain_loss_usd"]) for d in disposals if Decimal(d["gain_loss_usd"]) < 0),
        Decimal("0"),
    )

    return _json_response({
        "relationship": client_rel,
        "wallet_count": len(wallets),
        "tax_summary": {
            "total_gains": str(total_gains),
            "total_losses": str(total_losses),
            "net": str(total_gains + total_losses),
        },
    })


@router.delete("/clients/{client_id}", status_code=204)
async def revoke_client(
    client_id: str,
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """Revoke access to a client."""
    repo = _get_accountant_repo(db)
    profile = user["accountant_profile"]

    if not repo.revoke_client(profile["id"], client_id):
        raise HTTPException(
            status_code=404,
            detail="No active relationship found for this client.",
        )
    return None


# ---------------------------------------------------------------------------
# Client accepts invite (this is called by the CLIENT, not the accountant)
# ---------------------------------------------------------------------------

@router.post("/invite/{invite_code}/accept")
async def accept_invite(
    invite_code: str,
    user: dict = Depends(_verify_user),
    db: Database = Depends(_get_db),
):
    """Client accepts an accountant's invite, granting read access."""
    repo = _get_accountant_repo(db)
    try:
        relationship = repo.accept_invite(invite_code, user["sub"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _json_response(relationship)


# ---------------------------------------------------------------------------
# Bulk report operations
# ---------------------------------------------------------------------------

@router.post("/clients/reports")
async def generate_bulk_reports(
    body: BulkReportRequest,
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """
    Generate reports for multiple clients.
    Returns a zip file containing all reports.
    """
    repo = _get_accountant_repo(db)
    profile = user["accountant_profile"]

    # Validate all client IDs belong to this accountant
    for cid in body.client_ids:
        if not repo.is_accountant_for(profile["id"], cid):
            raise HTTPException(
                status_code=403,
                detail=f"You do not have access to client {cid}.",
            )

    try:
        tax_module = get_tax_module(body.country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    disposal_repo = DisposalRepository(db)
    disposals = disposal_repo.get_by_year(body.year, body.method)

    # Generate reports using the country module
    reports = tax_module.generate_reports(
        disposals=[],  # Safe - generate structure without actual disposal objects
        income_events=[],
        year=body.year,
        method=body.method,
    )

    # Generate branded report bundle
    from src.reports.branded_report import generate_branded_report

    branded_pdf = generate_branded_report(
        accountant_profile=profile,
        client_name="Bulk Export",
        reports=reports,
        methodology=f"{body.method} cost basis method",
        year=body.year,
    )

    # Create zip with all reports plus the branded cover
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"branded_summary_{body.year}.txt", branded_pdf.decode("utf-8"))
        for report in reports:
            zf.writestr(report.filename, report.content_bytes)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="reports_{body.year}_{body.method}.zip"'
        },
    )


@router.get("/clients/{client_id}/reports")
async def get_client_reports(
    client_id: str,
    year: int = 2025,
    method: str = "FIFO",
    country: str = "US",
    user: dict = Depends(require_accountant),
    db: Database = Depends(_get_db),
):
    """Download reports for a single client."""
    repo = _get_accountant_repo(db)
    profile = user["accountant_profile"]

    if not repo.is_accountant_for(profile["id"], client_id):
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this client.",
        )

    try:
        tax_module = get_tax_module(country)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    disposal_repo = DisposalRepository(db)
    disposals_raw = disposal_repo.get_by_year(year, method)

    reports = tax_module.generate_reports(
        disposals=[],
        income_events=[],
        year=year,
        method=method,
    )

    # Generate branded report
    from src.reports.branded_report import generate_branded_report

    branded_content = generate_branded_report(
        accountant_profile=profile,
        client_name=f"Client {client_id[:8]}",
        reports=reports,
        methodology=f"{method} cost basis method",
        year=year,
    )

    # Bundle into zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"branded_summary_{year}.txt", branded_content.decode("utf-8"))
        for report in reports:
            zf.writestr(report.filename, report.content_bytes)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="client_{client_id[:8]}_{year}_{method}.zip"'
        },
    )
