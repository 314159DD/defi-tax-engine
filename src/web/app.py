"""
FastAPI application for defi-tax-engine.

Routes:
  /api/wallets         - CRUD for watched wallet addresses
  /api/import          - trigger chain import jobs
  /api/calculate       - run cost-basis calculations (FIFO/LIFO/HIFO)
  /api/transactions    - paginated transaction viewer with filters
  /api/reports         - generate + download tax reports
  /api/auth            - Supabase JWT verification
  /api/billing         - Stripe Checkout + Customer Portal + webhook

All monetary values returned as strings (not floats) to preserve Decimal precision.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import stripe
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator

from src.config import (
    DB_PATH,
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
from src.storage.database import (
    Database,
    DisposalRepository,
    TaxLotRepository,
    TransactionRepository,
    WalletRepository,
)
from src.tax import get_tax_module, get_supported_countries
from src.web.routes.accountant import router as accountant_router
from src.web.routes.estimate import router as estimate_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Stripe setup
# ---------------------------------------------------------------------------
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

# ---------------------------------------------------------------------------
# Tier limits
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
        "price_monthly": "999",   # cents → $9.99
        "price_annual": "4999",   # cents → $49.99
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
# Database singleton
# ---------------------------------------------------------------------------
_db: Optional[Database] = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database(DB_PATH)
    return _db


# ---------------------------------------------------------------------------
# Auth (Supabase JWT)
# ---------------------------------------------------------------------------
async def verify_token(authorization: str = Header(default="")) -> dict:
    """
    Validate a Supabase JWT passed as 'Bearer <token>'.
    Returns the decoded payload (sub = user id).
    Skips verification if SUPABASE_URL is not configured (dev mode).
    """
    if not SUPABASE_URL:
        # Dev mode - accept any token or no token
        return {"sub": "dev-user", "email": "dev@localhost", "tier": "unlimited"}

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.removeprefix("Bearer ")
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        user = client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid token")
        # Attach tier from user metadata (set by Stripe webhook)
        tier = (user.user.user_metadata or {}).get("tier", "free")
        return {"sub": user.user.id, "email": user.user.email, "tier": tier}
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_tier(minimum: str):
    """Dependency factory: require at least this tier."""
    tier_order = ["free", "pro", "unlimited"]

    async def _check(user: dict = Depends(verify_token)):
        user_tier = user.get("tier", "free")
        if tier_order.index(user_tier) < tier_order.index(minimum):
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires the '{minimum}' tier or higher.",
            )
        return user

    return _check


# ---------------------------------------------------------------------------
# Pydantic request/response models
# ---------------------------------------------------------------------------
class WalletCreate(BaseModel):
    address: str
    chain: str
    label: Optional[str] = None

    @field_validator("chain")
    @classmethod
    def chain_must_be_supported(cls, v: str) -> str:
        if v.lower() not in SUPPORTED_CHAINS:
            raise ValueError(f"Unsupported chain '{v}'. Supported: {SUPPORTED_CHAINS}")
        return v.lower()


class ImportRequest(BaseModel):
    address: str
    chain: str
    force: bool = False   # re-import even if already up to date


class CalculateRequest(BaseModel):
    method: str = "FIFO"
    year: int = datetime.now().year
    wallet_addresses: Optional[list[str]] = None  # None = all wallets

    @field_validator("method")
    @classmethod
    def method_must_be_valid(cls, v: str) -> str:
        if v.upper() not in ("FIFO", "LIFO", "HIFO"):
            raise ValueError("method must be FIFO, LIFO, or HIFO")
        return v.upper()


class CategoryOverride(BaseModel):
    tx_hash: str
    chain: str
    new_type: str


# ---------------------------------------------------------------------------
# Background import task
# ---------------------------------------------------------------------------
_import_status: dict[str, dict] = {}


async def _run_import(address: str, chain: str, force: bool, db: Database) -> None:
    """Fetch transactions from chain, categorize them, and store in the database."""
    key = f"{chain}:{address}"
    _import_status[key] = {"status": "running", "started_at": _now_iso(), "count": 0}
    try:
        from src.categorizer.engine import categorize_transactions
        from src.storage.database import TransactionRepository, WalletRepository

        wallet_repo = WalletRepository(db)
        tx_repo = TransactionRepository(db)

        # Gather all known wallet addresses for self-transfer detection
        known_wallets = set(wallet_repo.get_addresses())
        known_wallets.add(address.lower())

        # Fetch raw transactions from chain
        if chain == "solana":
            from src.importers.solana import SolanaImporter
            importer = SolanaImporter()
            transactions = await importer.fetch_all(address, wallet_addresses=known_wallets)
        else:
            from src.importers.evm import EVMImporter
            importer = EVMImporter(chain)
            transactions = await importer.fetch_all(address, wallet_addresses=known_wallets)

        # Categorize transactions
        categorized = categorize_transactions(transactions, known_wallets)

        # Store in database
        rows = [
            {
                "tx_hash": tx.tx_hash,
                "chain": tx.chain,
                "timestamp": tx.timestamp,
                "tx_type": tx.tx_type,
                "protocol": tx.protocol,
                "raw_data": tx.raw_data,
            }
            for tx in categorized
        ]
        tx_repo.upsert_many(rows)

        # Update last imported timestamp
        wallet_repo.update_last_imported(address, chain)

        count = len(categorized)
        _import_status[key] = {
            "status": "done",
            "finished_at": _now_iso(),
            "count": count,
        }
    except Exception as exc:
        logger.exception("Import failed for %s:%s", chain, address)
        _import_status[key] = {
            "status": "error",
            "error": str(exc),
            "finished_at": _now_iso(),
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# App lifespan + CORS
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    get_db()  # ensure schema is applied at startup
    yield


app = FastAPI(
    title="Crypto Tax DeFi",
    version="0.1.0",
    description="Multi-chain crypto tax calculator with DeFi support.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accountant_router)
app.include_router(estimate_router)


# ---------------------------------------------------------------------------
# Custom JSON encoder for Decimal
# ---------------------------------------------------------------------------
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def _json_response(data: Any, status_code: int = 200) -> JSONResponse:
    content = json.loads(json.dumps(data, cls=DecimalEncoder))
    return JSONResponse(content=content, status_code=status_code)


# ---------------------------------------------------------------------------
# /api/wallets
# ---------------------------------------------------------------------------
@app.get("/api/wallets")
async def list_wallets(
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    repo = WalletRepository(db)
    wallets = repo.get_all()
    # Attach import status
    for w in wallets:
        key = f"{w['chain']}:{w['address']}"
        w["import_status"] = _import_status.get(key, {})
    return _json_response(wallets)


@app.post("/api/wallets", status_code=201)
async def add_wallet(
    body: WalletCreate,
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    repo = WalletRepository(db)
    tier = user.get("tier", "free")
    limits = TIER_LIMITS[tier]

    # Tier: max_wallets check
    if limits["max_wallets"] is not None:
        existing = repo.get_all()
        if len(existing) >= limits["max_wallets"]:
            raise HTTPException(
                status_code=403,
                detail=f"Free tier allows {limits['max_wallets']} wallet(s). Upgrade to Pro for more.",
            )

    # Tier: chain check
    if body.chain not in limits["chains"]:
        raise HTTPException(
            status_code=403,
            detail=f"Chain '{body.chain}' requires Pro tier or higher.",
        )

    wallet_id = repo.add(body.address, body.chain, body.label)
    return _json_response({"id": wallet_id, "address": body.address, "chain": body.chain})


@app.delete("/api/wallets/{wallet_id}", status_code=204)
async def delete_wallet(
    wallet_id: str,
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    with db.connect() as conn:
        conn.execute("DELETE FROM wallets WHERE id=?", (wallet_id,))
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# /api/import
# ---------------------------------------------------------------------------
@app.post("/api/import")
async def trigger_import(
    body: ImportRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Start a background import job for a wallet. Returns immediately."""
    tier = user.get("tier", "free")
    limits = TIER_LIMITS[tier]

    if body.chain not in limits["chains"]:
        raise HTTPException(
            status_code=403,
            detail=f"Chain '{body.chain}' not available on your current tier.",
        )

    # Tier: transaction limit check
    if limits["max_transactions"] is not None:
        tx_repo = TransactionRepository(db)
        current_count = tx_repo.count()
        if current_count >= limits["max_transactions"]:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"{tier.capitalize()} tier allows up to {limits['max_transactions']:,} transactions. "
                    f"You have {current_count:,}. Upgrade to Pro for up to 5,000."
                ),
            )

    key = f"{body.chain}:{body.address}"
    if _import_status.get(key, {}).get("status") == "running":
        return _json_response({"message": "Import already running", "key": key})

    background_tasks.add_task(_run_import, body.address, body.chain, body.force, db)
    return _json_response({"message": "Import started", "key": key})


@app.get("/api/import/status")
async def import_status(
    address: str = Query(...),
    chain: str = Query(...),
    user: dict = Depends(verify_token),
):
    key = f"{chain}:{address}"
    status = _import_status.get(key, {"status": "not_started"})
    return _json_response(status)


# ---------------------------------------------------------------------------
# /api/transactions
# ---------------------------------------------------------------------------
@app.get("/api/transactions")
async def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    chain: Optional[str] = Query(None),
    tx_type: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    address: Optional[str] = Query(None),
    missing_price: bool = Query(False),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Paginated transaction list with optional filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if chain:
        conditions.append("chain=?")
        params.append(chain.lower())
    if tx_type:
        conditions.append("tx_type=?")
        params.append(tx_type)
    if year:
        conditions.append("timestamp LIKE ?")
        params.append(f"{year}%")
    if address:
        conditions.append("raw_json LIKE ?")
        params.append(f"%{address.lower()}%")
    if missing_price:
        # Flag transactions where raw_json does not contain a usd_value
        conditions.append("(raw_json NOT LIKE '%usd_value%' OR raw_json LIKE '%\"usd_value\": null%')")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size

    with db.connect() as conn:
        total = conn.execute(f"SELECT COUNT(*) AS n FROM transactions {where}", params).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM transactions {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()

    transactions = []
    for row in rows:
        d = dict(row)
        if d.get("raw_json"):
            d["raw_data"] = json.loads(d.pop("raw_json"))
        else:
            d.pop("raw_json", None)
            d["raw_data"] = None
        transactions.append(d)

    return _json_response({
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "transactions": transactions,
    })


@app.patch("/api/transactions/{tx_hash}/category")
async def override_category(
    tx_hash: str,
    body: CategoryOverride,
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Manually override the categorized tx_type for a transaction."""
    valid_types = {
        "transfer", "swap", "lp_add", "lp_remove", "stake", "unstake",
        "reward", "bridge", "airdrop", "mint", "burn", "approve", "unknown",
    }
    if body.new_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid tx_type '{body.new_type}'")

    with db.connect() as conn:
        result = conn.execute(
            "UPDATE transactions SET tx_type=? WHERE tx_hash=? AND chain=?",
            (body.new_type, tx_hash, body.chain.lower()),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
    return _json_response({"tx_hash": tx_hash, "tx_type": body.new_type})


# ---------------------------------------------------------------------------
# /api/calculate
# ---------------------------------------------------------------------------
@app.post("/api/calculate")
async def calculate_cost_basis(
    body: CalculateRequest,
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """
    Run cost-basis calculation and return a tax summary.
    Results are also persisted to the disposals table.
    """
    tier = user.get("tier", "free")
    limits = TIER_LIMITS[tier]

    if body.method not in limits["methods"]:
        raise HTTPException(
            status_code=403,
            detail=f"Method '{body.method}' requires Pro tier or higher.",
        )

    from src.calculator.engine import CostBasisEngine

    engine = CostBasisEngine(db)
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: engine.calculate(method=body.method, year=body.year),
    )
    return _json_response(result)


@app.get("/api/calculate/summary")
async def tax_summary(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """
    Return summary totals from already-calculated disposals:
    total_gains, total_losses, net_gain_loss, short_term, long_term, estimated_tax.
    """
    disposal_repo = DisposalRepository(db)
    disposals = disposal_repo.get_by_year(year, method)

    total_gains = Decimal("0")
    total_losses = Decimal("0")
    short_term = Decimal("0")
    long_term = Decimal("0")

    for d in disposals:
        gl = d["gain_loss_usd"]
        if gl > 0:
            total_gains += gl
        else:
            total_losses += gl

        if d["holding_period"] == "short":
            short_term += gl
        else:
            long_term += gl

    net = total_gains + total_losses
    # Rough estimated tax (not professional advice)
    est_tax = short_term * Decimal("0.37") + (long_term if long_term > 0 else Decimal("0")) * Decimal("0.20")

    return _json_response({
        "year": year,
        "method": method,
        "total_gains": str(total_gains),
        "total_losses": str(total_losses),
        "net_gain_loss": str(net),
        "short_term": str(short_term),
        "long_term": str(long_term),
        "estimated_tax": str(max(est_tax, Decimal("0"))),
        "transaction_count": len(disposals),
    })


@app.get("/api/calculate/compare")
async def compare_methods(
    year: int = Query(datetime.now().year),
    user: dict = Depends(require_tier("pro")),
    db: Database = Depends(get_db),
):
    """Return a side-by-side comparison of FIFO, LIFO, and HIFO for the given year."""
    disposal_repo = DisposalRepository(db)
    comparison: dict[str, Any] = {}

    for method in ("FIFO", "LIFO", "HIFO"):
        disposals = disposal_repo.get_by_year(year, method)
        if not disposals:
            comparison[method] = None
            continue
        total_gains = sum((d["gain_loss_usd"] for d in disposals if d["gain_loss_usd"] > 0), Decimal("0"))
        total_losses = sum((d["gain_loss_usd"] for d in disposals if d["gain_loss_usd"] < 0), Decimal("0"))
        net = total_gains + total_losses
        comparison[method] = {
            "total_gains": str(total_gains),
            "total_losses": str(total_losses),
            "net": str(net),
            "count": len(disposals),
        }

    return _json_response({"year": year, "methods": comparison})


@app.get("/api/calculate/year-over-year")
async def year_over_year(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Return side-by-side tax summary for current year vs previous year."""
    disposal_repo = DisposalRepository(db)

    def _summarize(y: int) -> dict:
        disposals = disposal_repo.get_by_year(y, method)
        gains = sum((d["gain_loss_usd"] for d in disposals if d["gain_loss_usd"] > 0), Decimal("0"))
        losses = sum((d["gain_loss_usd"] for d in disposals if d["gain_loss_usd"] < 0), Decimal("0"))
        st = sum((d["gain_loss_usd"] for d in disposals if d.get("holding_period") == "short"), Decimal("0"))
        lt = sum((d["gain_loss_usd"] for d in disposals if d.get("holding_period") == "long"), Decimal("0"))
        est_tax = st * Decimal("0.37") + (lt if lt > 0 else Decimal("0")) * Decimal("0.20")
        net = gains + losses
        return {
            "year": y,
            "method": method,
            "total_gains": str(gains),
            "total_losses": str(losses),
            "net_gain_loss": str(net),
            "short_term": str(st),
            "long_term": str(lt),
            "estimated_tax": str(max(est_tax, Decimal("0"))),
            "transaction_count": len(disposals),
        }

    current = _summarize(year)
    previous = _summarize(year - 1)

    # Compute deltas for key metrics
    def _delta(cur: str, prev: str) -> str:
        c, p = Decimal(cur), Decimal(prev)
        if p == 0:
            return "0"
        return str(((c - p) / abs(p) * 100).quantize(Decimal("0.01")))

    deltas = {
        k: _delta(current[k], previous[k])
        for k in ("total_gains", "total_losses", "net_gain_loss", "estimated_tax")
    }

    return _json_response({
        "current_year": current,
        "previous_year": previous,
        "deltas_pct": deltas,
    })


# ---------------------------------------------------------------------------
# /api/reports
# ---------------------------------------------------------------------------
@app.get("/api/reports/form8949")
async def report_form8949(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Generate and stream Form 8949 CSV."""
    from src.reports.form_8949 import Form8949Generator
    gen = Form8949Generator(db)
    csv_data = gen.to_csv(year=year, method=method)
    filename = f"form8949_{year}_{method}.csv"
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports/turbotax")
async def report_turbotax(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Generate TurboTax-compatible CSV."""
    from src.reports.csv_export import TurboTaxExporter
    exporter = TurboTaxExporter(db)
    csv_data = exporter.export(year=year, method=method)
    filename = f"turbotax_{year}_{method}.csv"
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports/schedule_d")
async def report_schedule_d(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(require_tier("pro")),
    db: Database = Depends(get_db),
):
    """Generate Schedule D summary as JSON."""
    from src.reports.schedule_d import ScheduleDGenerator
    gen = ScheduleDGenerator(db)
    summary = gen.generate(year=year, method=method)
    return _json_response(summary.as_dict())


@app.get("/api/reports/harvest")
async def report_harvest(
    user: dict = Depends(require_tier("unlimited")),
    db: Database = Depends(get_db),
):
    """Return tax loss harvesting suggestions (Unlimited tier only)."""
    from src.reports.harvest import HarvestAnalyzer
    analyzer = HarvestAnalyzer(db)
    # current_prices must be provided; for now use empty dict (no suggestions without prices)
    # In production, this would be populated from a real-time price feed
    suggestions = analyzer.analyze(current_prices={})
    return _json_response({
        "suggestions": [s.as_dict() for s in suggestions],
    })


@app.get("/api/reports/income")
async def report_income(
    year: int = Query(datetime.now().year),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Generate ordinary income report (staking rewards, airdrops, etc.)."""
    from src.reports.income_report import IncomeReportGenerator
    gen = IncomeReportGenerator(db)
    summary = gen.generate(year=year)
    return _json_response(summary.as_dict())


@app.get("/api/reports/income/csv")
async def report_income_csv(
    year: int = Query(datetime.now().year),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Download income report as CSV."""
    from src.reports.income_report import IncomeReportGenerator
    gen = IncomeReportGenerator(db)
    csv_data = gen.to_csv(year=year)
    filename = f"income_report_{year}.csv"
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# /api/source-of-funds - Source of Funds Report (Sprint 5.5)
# ---------------------------------------------------------------------------
@app.get("/api/source-of-funds")
async def source_of_funds_json(
    wallets: Optional[str] = Query(None, description="Comma-separated wallet addresses"),
    tokens: Optional[str] = Query(None, description="Comma-separated token symbols"),
    user: dict = Depends(require_tier("pro")),
    db: Database = Depends(get_db),
):
    """Generate source of funds report as JSON (Pro tier and above)."""
    from src.reports.source_of_funds import trace_holdings

    wallet_filter = [w.strip() for w in wallets.split(",") if w.strip()] if wallets else None
    token_filter = [t.strip() for t in tokens.split(",") if t.strip()] if tokens else None

    report = trace_holdings(db, wallet_filter=wallet_filter, token_filter=token_filter)
    return _json_response(report.as_dict())


@app.get("/api/source-of-funds/csv")
async def source_of_funds_csv(
    wallets: Optional[str] = Query(None, description="Comma-separated wallet addresses"),
    tokens: Optional[str] = Query(None, description="Comma-separated token symbols"),
    user: dict = Depends(require_tier("pro")),
    db: Database = Depends(get_db),
):
    """Download source of funds report as CSV for KYC submission."""
    from src.reports.source_of_funds import trace_holdings
    from src.reports.source_of_funds_pdf import generate_source_of_funds_csv

    wallet_filter = [w.strip() for w in wallets.split(",") if w.strip()] if wallets else None
    token_filter = [t.strip() for t in tokens.split(",") if t.strip()] if tokens else None

    report = trace_holdings(db, wallet_filter=wallet_filter, token_filter=token_filter)
    csv_data = generate_source_of_funds_csv(report)
    filename = "source_of_funds.csv"
    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/source-of-funds/text")
async def source_of_funds_text(
    wallets: Optional[str] = Query(None, description="Comma-separated wallet addresses"),
    tokens: Optional[str] = Query(None, description="Comma-separated token symbols"),
    user: dict = Depends(require_tier("pro")),
    db: Database = Depends(get_db),
):
    """Download source of funds report as human-readable text."""
    from src.reports.source_of_funds import trace_holdings
    from src.reports.source_of_funds_pdf import generate_source_of_funds_text

    wallet_filter = [w.strip() for w in wallets.split(",") if w.strip()] if wallets else None
    token_filter = [t.strip() for t in tokens.split(",") if t.strip()] if tokens else None

    report = trace_holdings(db, wallet_filter=wallet_filter, token_filter=token_filter)
    text_data = generate_source_of_funds_text(report)
    filename = "source_of_funds.txt"
    return StreamingResponse(
        io.BytesIO(text_data.encode()),
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# /api/harvest - Tax Loss Harvesting Dashboard (Sprint 5.1)
# ---------------------------------------------------------------------------
class HarvestSimulateRequest(BaseModel):
    lot_ids: list[str]
    country: str = "US"
    user_bracket: str = "0.37"  # sent as string to preserve Decimal precision
    current_year_gains: str = "0"

    @field_validator("country")
    @classmethod
    def country_must_be_valid(cls, v: str) -> str:
        v = v.upper()
        if v not in ("US", "DE"):
            raise ValueError("country must be 'US' or 'DE'")
        return v


@app.get("/api/harvest/positions")
async def harvest_positions(
    country: str = Query("US"),
    user: dict = Depends(require_tier("unlimited")),
    db: Database = Depends(get_db),
):
    """
    Return all unrealized positions with current prices for the harvest dashboard.

    Includes holding period classification and DE-specific Spekulationsfrist data.
    """
    from src.reports.harvest import HarvestAnalyzer

    country = country.upper()
    if country not in ("US", "DE"):
        raise HTTPException(status_code=400, detail="country must be 'US' or 'DE'")

    analyzer = HarvestAnalyzer(db)

    # Get current prices from the price cache (latest date per token)
    current_prices = _get_latest_prices(db)

    positions = analyzer.get_positions(
        current_prices=current_prices,
        country=country,
    )

    return _json_response({
        "country": country,
        "positions": [p.as_dict() for p in positions],
        "count": len(positions),
    })


@app.post("/api/harvest/simulate")
async def harvest_simulate(
    body: HarvestSimulateRequest,
    user: dict = Depends(require_tier("unlimited")),
    db: Database = Depends(get_db),
):
    """
    Simulate selling selected positions and return projected tax impact.

    Accepts a list of lot IDs and returns a HarvestScenario.
    """
    from src.reports.harvest import HarvestAnalyzer
    from src.reports.harvest_simulator import simulate_harvest

    country = body.country

    try:
        user_bracket = Decimal(body.user_bracket)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user_bracket value")

    try:
        current_year_gains = Decimal(body.current_year_gains)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid current_year_gains value")

    tax_module = get_tax_module(country)
    analyzer = HarvestAnalyzer(db)
    current_prices = _get_latest_prices(db)

    positions = analyzer.get_positions(
        current_prices=current_prices,
        country=country,
    )

    scenario = simulate_harvest(
        positions=positions,
        tax_module=tax_module,
        current_year_gains=current_year_gains,
        user_bracket=user_bracket,
        selected_lot_ids=body.lot_ids,
    )

    return _json_response(scenario.as_dict())


@app.get("/api/harvest/wash-sales")
async def harvest_wash_sales(
    year: int = Query(datetime.now().year),
    user: dict = Depends(require_tier("unlimited")),
    db: Database = Depends(get_db),
):
    """
    Return active wash sale windows for US users.

    Scans all disposals and acquisitions for the given year to detect
    30-day wash sale violations.
    """
    from src.tax.us.wash_sale import check_wash_sales
    from datetime import date as date_type

    lot_repo = TaxLotRepository(db)
    disposal_repo = DisposalRepository(db)

    disposals_raw = disposal_repo.get_by_year(year)
    lots_raw = lot_repo.get_all()

    # Build disposal list for wash sale check
    disposals_for_ws = []
    for d in disposals_raw:
        disposals_for_ws.append({
            "token": d["token"],
            "disposal_date": d.get("disposal_date", ""),
            "gain_loss_usd": d["gain_loss_usd"],
            "tx_hash": d.get("tx_hash", ""),
        })

    # Build acquisition list
    acquisitions_for_ws = []
    for lot in lots_raw:
        acquisitions_for_ws.append({
            "token": lot["token"],
            "acquisition_date": lot["acquisition_date"],
            "lot_id": lot["id"],
        })

    windows = check_wash_sales(disposals_for_ws, acquisitions_for_ws)

    # Filter to active windows (as of today)
    today = date_type.today()
    active = [w for w in windows if w.is_active(today)]

    return _json_response({
        "year": year,
        "total_windows": len(windows),
        "active_windows": len(active),
        "windows": [w.as_dict() for w in windows],
        "active": [w.as_dict() for w in active],
    })


def _get_latest_prices(db: Database) -> dict[str, Decimal]:
    """
    Get the most recent price per token from the price_cache table.

    Returns: dict of TOKEN -> latest USD price (as Decimal).
    """
    prices: dict[str, Decimal] = {}
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT token, usd_price
            FROM price_cache
            WHERE (token, date) IN (
                SELECT token, MAX(date) FROM price_cache GROUP BY token
            )
            """
        ).fetchall()
    for row in rows:
        try:
            prices[row["token"].upper()] = Decimal(row["usd_price"])
        except Exception:
            pass
    return prices


@app.get("/api/reports/json")
async def report_json_full(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(require_tier("pro")),
    db: Database = Depends(get_db),
):
    """Export full disposals dataset as JSON (Pro+)."""
    from src.storage.database import DisposalRepository
    repo = DisposalRepository(db)
    disposals = repo.get_by_year(year, method)
    content = json.dumps(
        {"year": year, "method": method, "disposals": disposals},
        cls=DecimalEncoder,
        indent=2,
    )
    filename = f"tax_report_{year}_{method}.json"
    return StreamingResponse(
        io.BytesIO(content.encode()),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# /api/billing - Stripe
# ---------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    tier: str
    interval: str = "monthly"  # "monthly" | "annual"
    success_url: str
    cancel_url: str


@app.post("/api/billing/checkout")
async def create_checkout(
    body: CheckoutRequest,
    user: dict = Depends(verify_token),
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
            detail=f"Stripe price ID for {body.tier}/{body.interval} is not configured. Set STRIPE_PRICE_{body.tier.upper()}_{body.interval.upper()} in .env.",
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
        return _json_response({"url": session.url, "session_id": session.id})
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/billing/portal")
async def customer_portal(
    request: Request,
    user: dict = Depends(verify_token),
):
    """Create a Stripe Customer Portal session for subscription management."""
    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured.")

    body = await request.json()
    return_url = body.get("return_url", "http://localhost:3000/dashboard")

    try:
        # Look up customer by user_id in Stripe metadata
        customers = stripe.Customer.search(query=f'metadata["user_id"]:"{user["sub"]}"')
        if not customers.data:
            raise HTTPException(status_code=404, detail="No billing account found.")
        portal_session = stripe.billing_portal.Session.create(
            customer=customers.data[0].id,
            return_url=return_url,
        )
        return _json_response({"url": portal_session.url})
    except stripe.StripeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/billing/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(default="")):
    """
    Stripe webhook: handle checkout.session.completed to update user tier.
    Set STRIPE_WEBHOOK_SECRET in .env.
    """
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature") from exc

    async def _update_supabase_tier(user_id: str, tier: str) -> None:
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

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("client_reference_id") or (session.get("metadata") or {}).get("user_id")
        tier = (session.get("metadata") or {}).get("tier")
        if user_id and tier:
            await _update_supabase_tier(user_id, tier)

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.deleted"):
        sub = event["data"]["object"]
        # Resolve user_id from subscription metadata or customer metadata
        user_id = (sub.get("metadata") or {}).get("user_id")
        if not user_id:
            # Fall back: look up customer metadata
            try:
                customer = stripe.Customer.retrieve(sub["customer"])
                user_id = (customer.get("metadata") or {}).get("user_id")
            except stripe.StripeError:
                pass

        if user_id:
            if event["type"] == "customer.subscription.deleted":
                await _update_supabase_tier(user_id, "free")
            else:
                # updated: check status
                status = sub.get("status")
                if status in ("canceled", "unpaid", "past_due"):
                    await _update_supabase_tier(user_id, "free")
                # active/trialing: tier was already set on checkout.session.completed

    return _json_response({"received": True})


@app.get("/api/billing/status")
async def billing_status(
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """Return current user's tier, limits, and usage."""
    tier = user.get("tier", "free")
    limits = TIER_LIMITS[tier]
    tx_repo = TransactionRepository(db)
    wallet_repo = WalletRepository(db)
    tx_count = tx_repo.count()
    wallet_count = len(wallet_repo.get_all())
    return _json_response({
        "tier": tier,
        "limits": limits,
        "usage": {
            "wallets": wallet_count,
            "transactions": tx_count,
        },
    })


@app.get("/api/billing/tiers")
async def get_tiers():
    """Return tier definitions for the pricing page."""
    return _json_response(TIER_LIMITS)


# ---------------------------------------------------------------------------
# /api/auth
# ---------------------------------------------------------------------------
@app.get("/api/auth/me")
async def get_me(user: dict = Depends(verify_token)):
    """Return current user info (from JWT)."""
    return _json_response(user)


# ---------------------------------------------------------------------------
# /api/tax - Country-aware tax endpoints
# ---------------------------------------------------------------------------
@app.get("/api/tax/countries")
async def list_tax_countries():
    """Return list of supported tax jurisdictions."""
    return _json_response(get_supported_countries())


@app.get("/api/tax/methods")
async def tax_methods(
    country: str = Query("US"),
):
    """Return available cost basis methods for a country."""
    try:
        module = get_tax_module(country)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _json_response({
        "country": module.country_code,
        "methods": module.get_cost_basis_methods(),
        "default": module.get_default_method(),
    })


@app.get("/api/tax/de/spekulationsfrist")
async def de_spekulationsfrist(
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """
    Return per-lot Spekulationsfrist data for German users.
    Shows days remaining until each lot becomes tax-exempt.
    """
    from src.tax.de.module import GermanTaxModule
    from src.calculator.engine import CostBasisEngine

    module = GermanTaxModule()

    # Load all transactions and build the lot book
    engine = CostBasisEngine(db, tax_module=module)
    transactions = engine._load_transactions()

    if not transactions:
        return _json_response({"lots": [], "message": "No transactions found."})

    from src.calculator.engine import CalculatorEngine as CalcEngine
    from src.calculator.lots import LotManager

    calc = CalcEngine(method="FIFO", tax_module=module)
    # Build the lot manager by processing all transactions
    known_wallets = set()
    try:
        wallet_repo = WalletRepository(db)
        known_wallets = set(wallet_repo.get_addresses())
    except Exception:
        pass

    sorted_txs = sorted(transactions, key=lambda t: t.timestamp)
    lot_manager = LotManager()
    for tx in sorted_txs:
        try:
            calc._process_transaction(tx, lot_manager, known_wallets)
        except Exception:
            pass

    # Get all open lots
    all_lots = []
    for token, lots in lot_manager._lots.items():
        for lot in lots:
            if lot.remaining > 0:
                all_lots.append(lot)

    data = module.get_spekulationsfrist_data(all_lots)
    return _json_response({"lots": data})


@app.get("/api/tax/de/freigrenze")
async def de_freigrenze(
    year: int = Query(datetime.now().year),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """
    Return Freigrenze status for German users.
    Shows how much of the EUR 1,000 cliff threshold has been used.
    """
    from src.tax.de.module import GermanTaxModule

    module = GermanTaxModule()

    # Load disposals from DB
    disposal_repo = DisposalRepository(db)
    disposals_raw = disposal_repo.get_by_year(year, "FIFO")

    # Convert DB rows to simple objects for the module
    from types import SimpleNamespace

    disposals = []
    for d in disposals_raw:
        ns = SimpleNamespace(
            date=datetime.fromisoformat(d["disposal_date"][:10]) if isinstance(d["disposal_date"], str) else d["disposal_date"],
            holding_period=d.get("holding_period", "short"),
            gain_loss_usd=d["gain_loss_usd"],
            tx_hash=d.get("tx_hash", ""),
        )
        disposals.append(ns)

    result = module.get_freigrenze_status(disposals, year)
    return _json_response(result)


@app.post("/api/calculate/country")
async def calculate_with_country(
    body: CalculateRequest,
    country: str = Query("US"),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """
    Run cost-basis calculation with country-specific tax rules.
    Results include country-specific exemptions and holding period classifications.
    """
    try:
        tax_module = get_tax_module(country)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    allowed_methods = [m.upper() for m in tax_module.get_cost_basis_methods()]
    if body.method not in allowed_methods:
        raise HTTPException(
            status_code=400,
            detail=f"Method '{body.method}' not allowed for {country}. Allowed: {allowed_methods}",
        )

    from src.calculator.engine import CostBasisEngine

    engine = CostBasisEngine(db, tax_module=tax_module)
    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: engine.calculate(method=body.method, year=body.year),
    )
    return _json_response(result)


# ---------------------------------------------------------------------------
# /api/reconciliation - 1099-DA Reconciliation
# ---------------------------------------------------------------------------
# In-memory storage for uploaded 1099-DA entries (keyed by user sub)
_reconciliation_uploads: dict[str, list] = {}
_reconciliation_results: dict[str, Any] = {}


@app.post("/api/reconciliation/upload")
async def reconciliation_upload(
    file: UploadFile = File(...),
    user: dict = Depends(verify_token),
):
    """
    Upload a 1099-DA CSV file. Auto-detects exchange format.
    Stores parsed entries in memory for subsequent reconciliation.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV.")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    # Write to a temp file for the parser (parsers expect file paths)
    import tempfile
    import os

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
            tmp_path = tmp.name

        from src.importers.form_1099da import parse_1099da_auto
        entries = parse_1099da_auto(tmp_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to parse 1099-DA CSV")
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    user_id = user["sub"]
    _reconciliation_uploads[user_id] = entries

    # Build a preview summary
    brokers = set(e.broker_name for e in entries)
    total_proceeds = sum((e.proceeds for e in entries), Decimal("0"))

    return _json_response({
        "message": f"Parsed {len(entries)} entries from 1099-DA",
        "entry_count": len(entries),
        "brokers": sorted(brokers),
        "total_proceeds": str(total_proceeds),
        "entries": [
            {
                "asset": e.asset,
                "date_sold": e.date_sold.isoformat(),
                "proceeds": str(e.proceeds),
                "cost_basis": str(e.cost_basis) if e.cost_basis else None,
                "broker": e.broker_name,
            }
            for e in entries[:50]  # cap preview at 50 entries
        ],
    })


@app.post("/api/reconciliation/reconcile")
async def reconciliation_reconcile(
    year: int = Query(datetime.now().year),
    method: str = Query("FIFO"),
    user: dict = Depends(verify_token),
    db: Database = Depends(get_db),
):
    """
    Run reconciliation: match uploaded 1099-DA entries against calculated disposals.
    Must call /api/reconciliation/upload first.
    """
    user_id = user["sub"]
    entries = _reconciliation_uploads.get(user_id)
    if not entries:
        raise HTTPException(
            status_code=400,
            detail="No 1099-DA data uploaded. Call POST /api/reconciliation/upload first.",
        )

    # Load disposals from DB
    disposal_repo = DisposalRepository(db)
    disposal_rows = disposal_repo.get_by_year(year, method)

    if not disposal_rows:
        raise HTTPException(
            status_code=400,
            detail=f"No calculated disposals found for {year}/{method}. Run /api/calculate first.",
        )

    # Convert DB rows to Disposal objects
    from src.calculator.lots import Disposal, LotConsumption

    disposals: list = []
    for d in disposal_rows:
        disposal_date = d.get("disposal_date") or d.get("date")
        if isinstance(disposal_date, str):
            disposal_date = datetime.fromisoformat(disposal_date)

        disposals.append(Disposal(
            date=disposal_date,
            token=d.get("token", ""),
            amount=Decimal(str(d.get("amount", "0"))),
            proceeds_usd=Decimal(str(d.get("proceeds_usd", "0"))),
            cost_basis_usd=Decimal(str(d.get("cost_basis_usd", "0"))),
            gain_loss_usd=Decimal(str(d.get("gain_loss_usd", "0"))),
            holding_period=d.get("holding_period", "short-term"),
            method=d.get("method", method),
            lots_consumed=[],
            tx_hash=d.get("tx_hash", ""),
        ))

    # Run reconciliation
    from src.tax.us.reconciliation import reconcile

    result = reconcile(entries, disposals)
    _reconciliation_results[user_id] = result

    # Serialize result for JSON response
    matched_data = []
    for m in result.matched:
        matched_data.append({
            "form_asset": m.form_entry.asset,
            "form_date": m.form_entry.date_sold.isoformat(),
            "form_proceeds": str(m.form_entry.proceeds),
            "form_cost_basis": str(m.form_entry.cost_basis) if m.form_entry.cost_basis else None,
            "our_token": m.our_disposal.token,
            "our_date": m.our_disposal.date.isoformat() if hasattr(m.our_disposal.date, "isoformat") else str(m.our_disposal.date),
            "our_proceeds": str(m.our_disposal.proceeds_usd),
            "our_cost_basis": str(m.our_disposal.cost_basis_usd),
            "confidence": m.confidence.value,
            "discrepancies": [
                {
                    "type": disc.type.value,
                    "description": disc.description,
                    "form_value": str(disc.form_value) if disc.form_value else None,
                    "our_value": str(disc.our_value) if disc.our_value else None,
                    "guidance": disc.guidance,
                }
                for disc in m.discrepancies
            ],
        })

    unmatched_1099_data = [
        {
            "asset": e.asset,
            "date_sold": e.date_sold.isoformat(),
            "proceeds": str(e.proceeds),
            "broker": e.broker_name,
            "guidance": f"Import your {e.broker_name} transactions to resolve.",
        }
        for e in result.unmatched_1099
    ]

    unmatched_ours_data = [
        {
            "token": d.token,
            "date": d.date.isoformat() if hasattr(d.date, "isoformat") else str(d.date),
            "proceeds": str(d.proceeds_usd),
            "guidance": "Self-report on Form 8949.",
        }
        for d in result.unmatched_ours
    ]

    return _json_response({
        "match_rate": str(result.match_rate),
        "total_1099_proceeds": str(result.total_1099_proceeds),
        "total_our_proceeds": str(result.total_our_proceeds),
        "matched_count": len(result.matched),
        "unmatched_1099_count": len(result.unmatched_1099),
        "unmatched_ours_count": len(result.unmatched_ours),
        "discrepancy_count": len(result.discrepancies),
        "summary_text": result.summary_text,
        "matched": matched_data,
        "unmatched_1099": unmatched_1099_data,
        "unmatched_ours": unmatched_ours_data,
    })


@app.get("/api/reconciliation/report")
async def reconciliation_report(
    user: dict = Depends(verify_token),
):
    """
    Download the reconciliation report as CSV.
    Must call /api/reconciliation/reconcile first.
    """
    user_id = user["sub"]
    result = _reconciliation_results.get(user_id)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="No reconciliation result available. Run /api/reconciliation/reconcile first.",
        )

    from src.tax.us.reconciliation_report import generate_reconciliation_csv

    csv_data = generate_reconciliation_csv(result)
    filename = "1099da_reconciliation_report.csv"

    return StreamingResponse(
        io.BytesIO(csv_data.encode()),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health():
    return {"status": "ok", "time": _now_iso()}
