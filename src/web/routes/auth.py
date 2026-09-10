"""
Auth proxy routes - Supabase JWT validation and user profile.

Routes:
    POST /api/auth/signup    - proxy to Supabase auth
    POST /api/auth/login     - proxy to Supabase auth
    POST /api/auth/logout    - proxy to Supabase auth
    GET  /api/auth/user      - get current user from Supabase JWT
    POST /api/auth/refresh   - refresh token

All auth state lives in Supabase - this is a thin proxy that:
  1. Keeps the Supabase service key server-side (never exposed to client)
  2. Validates JWTs on protected routes
  3. Returns user profile + plan tier
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import SUPABASE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_supabase_client():
    """Create a Supabase client (lazy import to avoid startup errors)."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


async def verify_jwt(authorization: str = Header(default="")) -> dict:
    """
    Validate a Supabase JWT passed as 'Bearer <token>'.
    Returns the decoded payload (sub = user id, email, tier).
    Skips verification if SUPABASE_URL is not configured (dev mode).
    """
    if not SUPABASE_URL:
        return {"sub": "dev-user", "email": "dev@localhost", "tier": "unlimited"}

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        client = _get_supabase_client()
        user = client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        tier = (user.user.user_metadata or {}).get("tier", "free")
        return {
            "sub": user.user.id,
            "email": user.user.email,
            "tier": tier,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/signup")
async def signup(body: SignupRequest):
    """Create a new user account via Supabase Auth."""
    try:
        client = _get_supabase_client()
        result = client.auth.sign_up({
            "email": body.email,
            "password": body.password,
        })
        if not result.user:
            raise HTTPException(status_code=400, detail="Signup failed")
        return JSONResponse(content={
            "user": {
                "id": result.user.id,
                "email": result.user.email,
            },
            "session": {
                "access_token": result.session.access_token if result.session else None,
                "refresh_token": result.session.refresh_token if result.session else None,
            } if result.session else None,
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login")
async def login(body: LoginRequest):
    """Sign in with email + password via Supabase Auth."""
    try:
        client = _get_supabase_client()
        result = client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        if not result.user or not result.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        tier = (result.user.user_metadata or {}).get("tier", "free")
        return JSONResponse(content={
            "user": {
                "id": result.user.id,
                "email": result.user.email,
                "tier": tier,
            },
            "session": {
                "access_token": result.session.access_token,
                "refresh_token": result.session.refresh_token,
                "expires_in": result.session.expires_in,
            },
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout")
async def logout(authorization: str = Header(default="")):
    """Sign out - invalidate the current session."""
    if not SUPABASE_URL:
        return JSONResponse(content={"message": "Logged out (dev mode)"})

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        client = _get_supabase_client()
        # Sign out server-side
        client.auth.admin.sign_out(token)
    except Exception:
        # Best-effort - even if server revocation fails, client should clear token
        pass

    return JSONResponse(content={"message": "Logged out"})


@router.get("/user")
async def get_user(user: dict = Depends(verify_jwt)):
    """Return current user info from the validated JWT."""
    return JSONResponse(content={
        "id": user["sub"],
        "email": user["email"],
        "tier": user["tier"],
    })


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    """Refresh an expired access token using the refresh token."""
    try:
        client = _get_supabase_client()
        result = client.auth.refresh_session(body.refresh_token)
        if not result.session:
            raise HTTPException(status_code=401, detail="Refresh failed")
        return JSONResponse(content={
            "session": {
                "access_token": result.session.access_token,
                "refresh_token": result.session.refresh_token,
                "expires_in": result.session.expires_in,
            },
        })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
