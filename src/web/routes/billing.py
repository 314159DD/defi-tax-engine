"""
Stripe billing routes - checkout, webhooks, portal, status.

Routes:
    POST /api/billing/create-checkout  - create Stripe checkout session
    POST /api/billing/webhook          - Stripe webhook handler
    GET  /api/billing/portal           - create Stripe customer portal session
    GET  /api/billing/status           - get current subscription status
    GET  /api/billing/tiers            - return tier definitions

Webhook updates user's plan tier in Supabase profiles table.
Tier enforcement happens client-side (engine checks tier before running).
"""
from __future__ import annotations

import logging
from typing import Any

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import (
    STRIPE_PRICE_PRO_ANNUAL,
    STRIPE_PRICE_PRO_MONTHLY,
    STRIPE_PRICE_UNLIMITED_ANNUAL,
    STRIPE_PRICE_UNLIMITED_MONTHLY,
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    SUPABASE_KEY,
    SUPABASE_URL,
    SUPPORTED_CHAINS,
)
from src.web.routes.auth import verify_jwt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

# ---------------------------------------------------------------------------
# Stripe setup
# ---------------------------------------------------------------------------
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ---------------------------------------------------------------------------
# Tier definitions
# ---------------------------------------------------------------------------
TIER_LIMITS: dict[str, dict] = {
    "free": {
        "max_wallets": 1,
        "chains": ["ethereum"],
        "max_transactions": 100,
        "methods": ["FIFO"],
        "reports": ["form_8949", "turbotax"],
        "harvest": False,
        "price_monthly": None,
        "price_annual": None,
    },
    "pro": {
        "max_wallets": 5,
        "chains": SUPPORTED_CHAINS,
        "max_transactions": 5000,
        "methods": ["FIFO", "LIFO", "HIFO"],
        "reports": ["form_8949", "schedule_d", "turbotax", "json"],
        "harvest": False,
        "price_monthly": "999",
        "price_annual": "4999",
    },
    "unlimited": {
        "max_wallets": None,
        "chains": SUPPORTED_CHAINS,
        "max_transactions": None,
        "methods": ["FIFO", "LIFO", "HIFO"],
        "reports": ["form_8949", "schedule_d", "turbotax", "json"],
        "harvest": True,
        "price_monthly": "2999",
        "price_annual": "14999",
    },
}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    tier: str
    interval: str = "monthly"  # "monthly" | "annual"
    success_url: str
    cancel_url: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/create-checkout")
async def create_checkout(
    body: CheckoutRequest,
    user: dict = Depends(verify_jwt),
):
    """Create a Stripe Checkout session for a tier upgrade."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured.")

    tier_prices = {
        "pro": {"monthly": STRIPE_PRICE_PRO_MONTHLY, "annual": STRIPE_PRICE_PRO_ANNUAL},
        "unlimited": {"monthly": STRIPE_PRICE_UNLIMITED_MONTHLY, "annual": STRIPE_PRICE_UNLIMITED_ANNUAL},
    }
    if body.tier not in tier_prices:
        raise HTTPException(status_code=400, detail=f"Invalid tier '{body.tier}'")
    if body.interval not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="interval must be 'monthly' or 'annual'")

    price_id = tier_prices[body.tier][body.interval]
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail=f"Stripe price ID for {body.tier}/{body.interval} not configured.",
        )

    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            client_reference_id=user["sub"],
            customer_email=user.get("email"),
            metadata={"tier": body.tier, "user_id": user["sub"]},
        )
        return JSONResponse(content={"url": session.url, "session_id": session.id})
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(default="", alias="stripe-signature"),
):
    """
    Stripe webhook: handle checkout completion and subscription changes.
    Updates user tier in Supabase.
    """
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook secret not configured.")

    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
        tier = (session.get("metadata") or {}).get("tier")
        if user_id and tier:
            await _update_supabase_tier(user_id, tier)

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        user_id = (sub.get("metadata") or {}).get("user_id")
        if not user_id:
            try:
                customer = stripe.Customer.retrieve(sub["customer"])
                user_id = (customer.get("metadata") or {}).get("user_id")
            except stripe.StripeError:
                pass

        if user_id:
            if event["type"] == "customer.subscription.deleted":
                await _update_supabase_tier(user_id, "free")
            else:
                status = sub.get("status")
                if status in ("canceled", "unpaid", "past_due"):
                    await _update_supabase_tier(user_id, "free")

    return JSONResponse(content={"received": True})


@router.get("/portal")
async def customer_portal(
    request: Request,
    user: dict = Depends(verify_jwt),
):
    """Create a Stripe Customer Portal session for subscription management."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured.")

    # Accept return_url from query param or default
    return_url = request.query_params.get("return_url", "http://localhost:3000/dashboard")

    try:
        customers = stripe.Customer.search(query=f'metadata["user_id"]:"{user["sub"]}"')
        if not customers.data:
            raise HTTPException(status_code=404, detail="No billing account found.")
        portal_session = stripe.billing_portal.Session.create(
            customer=customers.data[0].id,
            return_url=return_url,
        )
        return JSONResponse(content={"url": portal_session.url})
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status")
async def billing_status(user: dict = Depends(verify_jwt)):
    """Return current user's tier and limits."""
    tier = user.get("tier", "free")
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    return JSONResponse(content={
        "tier": tier,
        "limits": limits,
    })


@router.get("/tiers")
async def get_tiers():
    """Return tier definitions for the pricing page."""
    return JSONResponse(content=TIER_LIMITS)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _update_supabase_tier(user_id: str, tier: str) -> None:
    """Update user tier in Supabase user_metadata."""
    if not SUPABASE_URL:
        return
    try:
        from supabase import create_client
        admin_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        admin_client.auth.admin.update_user_by_id(
            user_id,
            {"user_metadata": {"tier": tier}},
        )
        logger.info("Updated user %s to tier %s", user_id, tier)
    except Exception:
        logger.exception("Failed to update Supabase tier for user %s", user_id)
