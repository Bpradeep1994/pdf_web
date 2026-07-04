"""
Admin Dashboard API — RBAC-protected (admin role only).
Aggregates platform stats and exposes user management. All microservices share
one Postgres database, so cross-domain counts are read with parameterized SQL
(no cross-service model imports).
"""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_db
from shared.audit import record as audit
from models import User, UserRole
from routes import _get_current_user

admin_router = APIRouter()


_LEVELS = {"user": 0, "moderator": 1, "admin": 2, "superadmin": 3}


def _level(u: User) -> str:
    lv = getattr(u, "admin_level", "user") or "user"
    if u.role == UserRole.admin and _LEVELS.get(lv, 0) < 3:   # legacy platform admins
        lv = "superadmin"
    return lv


def _rank(u: User) -> int:
    return _LEVELS.get(_level(u), 0)


async def require_admin(current_user: User = Depends(_get_current_user)) -> User:
    """Panel access — Moderator and up (Moderators are read-only; writes are gated separately)."""
    if _rank(current_user) < 1:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


async def require_admin_write(current_user: User = Depends(_get_current_user)) -> User:
    if _rank(current_user) < 2:
        raise HTTPException(status_code=403, detail="Admin (write) access required")
    return current_user


async def require_superadmin(current_user: User = Depends(_get_current_user)) -> User:
    if _rank(current_user) < 3:
        raise HTTPException(status_code=403, detail="Super Admin access required")
    return current_user


async def _scalar(db: AsyncSession, sql: str) -> int:
    """Run a COUNT-style query, returning 0 if the table doesn't exist yet."""
    try:
        return int((await db.execute(text(sql))).scalar() or 0)
    except Exception:
        return 0


# ── Stats ───────────────────────────────────────────────────────────────────────

@admin_router.get("/stats")
async def stats(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_users   = await _scalar(db, "SELECT count(*) FROM users")
    new_users_7d  = await _scalar(db, "SELECT count(*) FROM users WHERE created_at > now() - interval '7 days'")
    total_docs    = await _scalar(db, "SELECT count(*) FROM documents")
    docs_7d       = await _scalar(db, "SELECT count(*) FROM documents WHERE created_at > now() - interval '7 days'")
    total_ai      = await _scalar(db, "SELECT count(*) FROM ai_messages")
    storage_bytes = await _scalar(db, "SELECT coalesce(sum(file_size), 0) FROM documents")
    version_bytes = await _scalar(db, "SELECT coalesce(sum(file_size), 0) FROM document_versions")

    uploads_rows = []
    try:
        res = await db.execute(text(
            "SELECT to_char(date_trunc('day', created_at), 'YYYY-MM-DD') AS d, count(*) AS c "
            "FROM documents WHERE created_at > now() - interval '30 days' GROUP BY 1 ORDER BY 1"
        ))
        uploads_rows = [{"date": r[0], "uploads": int(r[1])} for r in res.fetchall()]
    except Exception:
        uploads_rows = []

    return {
        "total_users":      total_users,
        "total_documents":  total_docs,
        "total_ai_queries": total_ai,
        "mrr":              0,            # populated once billing is live
        "new_users_7d":     new_users_7d,
        "docs_7d":          docs_7d,
        "storage_bytes":    storage_bytes + version_bytes,
        "storage_documents_bytes": storage_bytes,
        "storage_versions_bytes":  version_bytes,
        "revenue_chart":    [],           # populated once billing is live
        "uploads_chart":    uploads_rows,
    }


# ── User management ───────────────────────────────────────────────────────────

class AdminUserRow(BaseModel):
    id:         UUID
    email:      str
    full_name:  str | None
    role:       str
    is_active:  bool
    created_at: str | None

    model_config = {"from_attributes": True}


class UpdateUserRequest(BaseModel):
    role:        UserRole | None = None      # billing plan
    is_active:   bool | None = None
    admin_level: str | None = None           # user|moderator|admin|superadmin
    status:      str | None = None           # active|suspended|banned
    full_name:   str | None = None


@admin_router.get("/users")
async def list_users(
    _:        User = Depends(require_admin),
    db:       AsyncSession = Depends(get_db),
    page:     int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search:   str | None = None,
):
    stmt = select(User)
    if search:
        stmt = stmt.where(User.email.ilike(f"%{search}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()

    return {
        "items": [
            {
                "id": str(u.id), "email": u.email, "full_name": u.full_name,
                "role": u.role.value, "is_active": u.is_active,
                "admin_level": getattr(u, "admin_level", "user"),
                "status": getattr(u, "status", "active"),
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@admin_router.get("/audit-logs")
async def audit_logs(
    _:          User = Depends(require_admin),
    db:         AsyncSession = Depends(get_db),
    page:       int = Query(1, ge=1),
    page_size:  int = Query(50, ge=1, le=200),
    action:     str | None = None,
    user_id:    str | None = None,
):
    where, params = [], {}
    if action:
        where.append("action ILIKE :action"); params["action"] = f"%{action}%"
    if user_id:
        where.append("user_id = CAST(:uid AS uuid)"); params["uid"] = user_id
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    total = int((await db.execute(text(f"SELECT count(*) FROM audit_logs {clause}"), params)).scalar() or 0)
    params2 = {**params, "lim": page_size, "off": (page - 1) * page_size}
    rows = (await db.execute(text(
        f"SELECT id, user_id, action, resource, resource_id, ip_address, user_agent, created_at "
        f"FROM audit_logs {clause} ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params2)).mappings().all()

    return {
        "items": [
            {"id": str(r["id"]), "user_id": str(r["user_id"]) if r["user_id"] else None,
             "action": r["action"], "resource": r["resource"],
             "resource_id": str(r["resource_id"]) if r["resource_id"] else None,
             "ip_address": str(r["ip_address"]) if r["ip_address"] else None,
             "user_agent": r["user_agent"],
             "created_at": r["created_at"].isoformat() if r["created_at"] else None}
            for r in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@admin_router.patch("/users/{user_id}")
async def update_user(
    user_id: UUID,
    body:    UpdateUserRequest,
    request: Request,
    admin:   User = Depends(require_admin_write),
    db:      AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Guards: protect yourself + don't let a non-superadmin touch a Super Admin.
    is_self = user_id == admin.id
    if _rank(user) >= 3 and _rank(admin) < 3 and not is_self:
        raise HTTPException(status_code=403, detail="Only a Super Admin can modify a Super Admin")
    if is_self and (body.is_active is False or body.status in ("suspended", "banned")):
        raise HTTPException(status_code=400, detail="You cannot suspend/disable your own account")

    if body.role is not None:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.status is not None:
        if body.status not in ("active", "suspended", "banned"):
            raise HTTPException(status_code=400, detail="Invalid status")
        user.status = body.status
        user.is_active = body.status == "active"   # suspend/ban also blocks login
    if body.admin_level is not None:
        if body.admin_level not in _LEVELS:
            raise HTTPException(status_code=400, detail="Invalid role")
        # only a Super Admin may grant Admin or Super Admin
        if _LEVELS[body.admin_level] >= 2 and _rank(admin) < 3:
            raise HTTPException(status_code=403, detail="Only a Super Admin can assign Admin/Super Admin")
        user.admin_level = body.admin_level

    await db.flush()
    await audit(db, action="admin.user_updated", user_id=admin.id, resource="user", resource_id=user.id,
                request=request, metadata={"role": user.role.value, "is_active": user.is_active,
                                           "admin_level": user.admin_level, "status": user.status})
    return {"id": str(user.id), "role": user.role.value, "is_active": user.is_active,
            "admin_level": user.admin_level, "status": user.status}


@admin_router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, request: Request,
                      admin: User = Depends(require_superadmin), db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if _rank(user) >= 3:
        raise HTTPException(status_code=403, detail="Cannot delete a Super Admin")
    await audit(db, action="admin.user_deleted", user_id=admin.id, resource="user", resource_id=user_id,
                request=request, metadata={"email": user.email})
    await db.delete(user)   # cascades to the user's data via FK ON DELETE CASCADE


@admin_router.post("/users/{user_id}/reset-password")
async def admin_reset_password(user_id: UUID, request: Request,
                               admin: User = Depends(require_admin_write), db: AsyncSession = Depends(get_db)):
    """Issue a password-reset token and email it to the user."""
    import secrets
    from datetime import datetime, timezone, timedelta
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    token = secrets.token_urlsafe(32)
    await db.execute(text(
        "INSERT INTO user_tokens (id, user_id, token, token_type, expires_at) "
        "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :t, 'password_reset', :exp)"),
        {"u": str(user_id), "t": token, "exp": datetime.now(timezone.utc) + timedelta(hours=1)})
    try:
        from emailer import send_password_reset
        send_password_reset(user.email, token)
    except Exception:
        pass
    await audit(db, action="admin.password_reset", user_id=admin.id, resource="user", resource_id=user_id, request=request)
    return {"sent": True, "email": user.email}


# ── Documents (all tenants) ─────────────────────────────────────────────────────

@admin_router.get("/documents")
async def admin_documents(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
                          page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                          search: str | None = None):
    where, params = ["d.deleted_at IS NULL"], {}
    if search:
        where.append("d.original_name ILIKE :s"); params["s"] = f"%{search}%"
    clause = "WHERE " + " AND ".join(where)
    total = await _scalar_p(db, f"SELECT count(*) FROM documents d {clause}", params)
    rows = (await db.execute(text(
        f"SELECT d.id, d.original_name, d.file_size, d.page_count, d.status, d.created_at, u.email AS owner_email "
        f"FROM documents d LEFT JOIN users u ON u.id = d.owner_id {clause} "
        f"ORDER BY d.created_at DESC LIMIT :lim OFFSET :off"),
        {**params, "lim": page_size, "off": (page - 1) * page_size})).mappings().all()
    return {"items": [
        {"id": str(r["id"]), "original_name": r["original_name"], "file_size": r["file_size"],
         "page_count": r["page_count"], "status": r["status"], "owner_email": r["owner_email"],
         "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows],
        "total": total, "page": page, "page_size": page_size}


# ── Revenue ─────────────────────────────────────────────────────────────────────

@admin_router.get("/revenue")
async def admin_revenue(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    total_cents = await _scalar(db, "SELECT coalesce(sum(amount_paid),0) FROM invoices WHERE status='paid'")
    paid_count  = await _scalar(db, "SELECT count(*) FROM invoices WHERE status='paid'")
    active_subs = await _scalar(db, "SELECT count(*) FROM subscriptions WHERE status='active'")
    chart = []
    try:
        res = await db.execute(text(
            "SELECT to_char(date_trunc('month', created_at),'YYYY-MM') AS m, coalesce(sum(amount_paid),0) AS c "
            "FROM invoices WHERE status='paid' AND created_at > now() - interval '12 months' GROUP BY 1 ORDER BY 1"))
        chart = [{"month": r[0], "revenue": round(int(r[1]) / 100, 2)} for r in res.fetchall()]
    except Exception:
        chart = []
    return {"total_revenue": round(total_cents / 100, 2), "paid_invoices": paid_count,
            "active_subscriptions": active_subs, "revenue_chart": chart}


# ── Subscriptions ────────────────────────────────────────────────────────────────

@admin_router.get("/subscriptions")
async def admin_subscriptions(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
                              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    total = await _scalar(db, "SELECT count(*) FROM subscriptions")
    rows = (await db.execute(text(
        "SELECT s.id, u.email, s.plan, s.status, s.current_period_end, s.created_at "
        "FROM subscriptions s LEFT JOIN users u ON u.id = s.user_id "
        "ORDER BY s.created_at DESC LIMIT :lim OFFSET :off"),
        {"lim": page_size, "off": (page - 1) * page_size})).mappings().all()
    return {"items": [
        {"id": str(r["id"]), "email": r["email"], "plan": r["plan"], "status": r["status"],
         "current_period_end": r["current_period_end"].isoformat() if r["current_period_end"] else None,
         "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows],
        "total": total, "page": page, "page_size": page_size}


# ── Invoices ─────────────────────────────────────────────────────────────────────

@admin_router.get("/invoices")
async def admin_invoices(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
                         page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    total = await _scalar(db, "SELECT count(*) FROM invoices")
    rows = (await db.execute(text(
        "SELECT i.stripe_invoice_id, u.email, i.amount_paid, i.currency, i.status, i.invoice_url, i.created_at "
        "FROM invoices i LEFT JOIN users u ON u.id = i.user_id "
        "ORDER BY i.created_at DESC LIMIT :lim OFFSET :off"),
        {"lim": page_size, "off": (page - 1) * page_size})).mappings().all()
    return {"items": [
        {"stripe_invoice_id": r["stripe_invoice_id"], "email": r["email"],
         "amount": round((r["amount_paid"] or 0) / 100, 2), "currency": r["currency"], "status": r["status"],
         "invoice_url": r["invoice_url"],
         "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows],
        "total": total, "page": page, "page_size": page_size}


# ── Support tickets (admin) ──────────────────────────────────────────────────────

class TicketUpdate(BaseModel):
    status:   str | None = None
    priority: str | None = None
    response: str | None = None


@admin_router.get("/support-tickets")
async def admin_tickets(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
                        status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    where, params = [], {}
    if status:
        where.append("t.status = :st"); params["st"] = status
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = await _scalar_p(db, f"SELECT count(*) FROM support_tickets t {clause}", params)
    rows = (await db.execute(text(
        f"SELECT t.id, t.subject, t.message, t.status, t.priority, t.response, t.created_at, u.email AS user_email "
        f"FROM support_tickets t LEFT JOIN users u ON u.id = t.user_id {clause} "
        f"ORDER BY t.created_at DESC LIMIT :lim OFFSET :off"),
        {**params, "lim": page_size, "off": (page - 1) * page_size})).mappings().all()
    return {"items": [
        {"id": str(r["id"]), "subject": r["subject"], "message": r["message"], "status": r["status"],
         "priority": r["priority"], "response": r["response"], "user_email": r["user_email"],
         "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows],
        "total": total, "page": page, "page_size": page_size}


@admin_router.patch("/support-tickets/{ticket_id}")
async def admin_update_ticket(ticket_id: UUID, body: TicketUpdate, request: Request,
                              admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    sets, params = ["updated_at = now()"], {"id": str(ticket_id)}
    for f in ("status", "priority", "response"):
        v = getattr(body, f)
        if v is not None:
            sets.append(f"{f} = :{f}"); params[f] = v
    res = await db.execute(text(f"UPDATE support_tickets SET {', '.join(sets)} WHERE id = CAST(:id AS uuid)"), params)
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await audit(db, action="admin.ticket_updated", user_id=admin.id, resource="support_ticket",
                resource_id=ticket_id, request=request)
    return {"id": str(ticket_id), "updated": True}


# ── Analytics ────────────────────────────────────────────────────────────────────

async def _series(db: AsyncSession, table: str, days: int = 30) -> list[dict]:
    try:
        res = await db.execute(text(
            f"SELECT to_char(date_trunc('day', created_at),'YYYY-MM-DD') AS d, count(*) AS c "
            f"FROM {table} WHERE created_at > now() - interval '{days} days' GROUP BY 1 ORDER BY 1"))
        return [{"date": r[0], "count": int(r[1])} for r in res.fetchall()]
    except Exception:
        return []


@admin_router.get("/analytics")
async def admin_analytics(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    return {
        "signups":   await _series(db, "users"),
        "documents": await _series(db, "documents"),
        "tickets":   await _series(db, "support_tickets"),
        "totals": {
            "users":         await _scalar(db, "SELECT count(*) FROM users"),
            "documents":     await _scalar(db, "SELECT count(*) FROM documents WHERE deleted_at IS NULL"),
            "active_subs":   await _scalar(db, "SELECT count(*) FROM subscriptions WHERE status='active'"),
            "open_tickets":  await _scalar(db, "SELECT count(*) FROM support_tickets WHERE status='open'"),
        },
    }


# ── Platform settings ────────────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    key:   str
    value: dict


@admin_router.get("/settings")
async def admin_get_settings(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    try:
        rows = (await db.execute(text("SELECT key, value FROM platform_settings"))).mappings().all()
        return {"settings": {r["key"]: r["value"] for r in rows}}
    except Exception:
        return {"settings": {}}


@admin_router.put("/settings")
async def admin_put_setting(body: SettingUpdate, request: Request,
                            admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    import json
    await db.execute(text(
        "INSERT INTO platform_settings (key, value, updated_at) VALUES (:k, CAST(:v AS jsonb), now()) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()"),
        {"k": body.key, "v": json.dumps(body.value)})
    await audit(db, action="admin.setting_updated", user_id=admin.id, resource="setting", request=request,
                metadata={"key": body.key})
    return {"key": body.key, "value": body.value}


async def _scalar_p(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        return int((await db.execute(text(sql), params)).scalar() or 0)
    except Exception:
        return 0


# ── KPIs (admin dashboard) ───────────────────────────────────────────────────

async def _series_sql(db, sql, params=None):
    try:
        return [{"label": r[0], "value": int(r[1])} for r in (await db.execute(text(sql), params or {})).fetchall()]
    except Exception:
        return []


@admin_router.get("/kpis")
async def kpis(_: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    # Users
    total_users  = await _scalar(db, "SELECT count(*) FROM users")
    active_users = await _scalar(db, "SELECT count(*) FROM users WHERE is_active = TRUE")
    active_30d   = await _scalar(db, "SELECT count(DISTINCT user_id) FROM audit_logs WHERE created_at > now() - interval '30 days'")
    new_7d       = await _scalar(db, "SELECT count(*) FROM users WHERE created_at > now() - interval '7 days'")
    new_30d      = await _scalar(db, "SELECT count(*) FROM users WHERE created_at > now() - interval '30 days'")

    # Revenue (from succeeded payments, in cents → dollars)
    rev_total = await _scalar(db, "SELECT coalesce(sum(amount_cents),0) FROM payments WHERE status='succeeded'")
    rev_month = await _scalar(db, "SELECT coalesce(sum(amount_cents),0) FROM payments WHERE status='succeeded' AND created_at >= date_trunc('month', now())")
    rev_year  = await _scalar(db, "SELECT coalesce(sum(amount_cents),0) FROM payments WHERE status='succeeded' AND created_at >= date_trunc('year', now())")

    # Documents
    uploads   = await _scalar(db, "SELECT count(*) FROM documents")
    downloads = await _scalar(db, "SELECT count(*) FROM audit_logs WHERE action ILIKE '%download%'")
    storage   = (await _scalar(db, "SELECT coalesce(sum(file_size),0) FROM documents")) + \
                (await _scalar(db, "SELECT coalesce(sum(file_size),0) FROM document_versions"))

    active_subs = await _scalar(db, "SELECT count(*) FROM subscriptions WHERE status='active' AND plan <> 'free'")

    sub_growth = await _series_sql(db,
        "SELECT to_char(date_trunc('month', created_at),'YYYY-MM'), count(*) FROM subscriptions "
        "WHERE created_at > now() - interval '12 months' GROUP BY 1 ORDER BY 1")
    rev_chart = await _series_sql(db,
        "SELECT to_char(date_trunc('month', created_at),'YYYY-MM'), coalesce(sum(amount_cents),0)/100 "
        "FROM payments WHERE status='succeeded' AND created_at > now() - interval '12 months' GROUP BY 1 ORDER BY 1")
    top_countries = await _series_sql(db,
        "SELECT coalesce(country,'Unknown'), count(*) FROM analytics_events GROUP BY 1 ORDER BY 2 DESC LIMIT 6")
    traffic = await _series_sql(db,
        "SELECT coalesce(source,'Direct'), count(*) FROM analytics_events GROUP BY 1 ORDER BY 2 DESC LIMIT 6")

    return {
        "users":   {"total": total_users, "active": active_users, "active_30d": active_30d, "new_7d": new_7d, "new_30d": new_30d},
        "revenue": {"total": round(rev_total/100, 2), "monthly": round(rev_month/100, 2), "annual": round(rev_year/100, 2)},
        "documents": {"uploads": uploads, "downloads": downloads},
        "storage_bytes": storage,
        "active_subscriptions": active_subs,
        "subscription_growth": sub_growth,
        "revenue_chart": rev_chart,
        "top_countries": top_countries,
        "traffic_sources": traffic,
    }


# ── Analytics tracking (authenticated; mounted at /api/v1/analytics) ───────────

analytics_router = APIRouter()


class TrackEvent(BaseModel):
    event_type: str = "pageview"
    source:  str | None = None
    country: str | None = None
    path:    str | None = None


@analytics_router.post("/track")
async def track(body: TrackEvent, current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text(
        "INSERT INTO analytics_events (id, user_id, event_type, source, country, path) "
        "VALUES (uuid_generate_v4(), CAST(:u AS uuid), :et, :src, :c, :p)"),
        {"u": str(current_user.id), "et": (body.event_type or "pageview")[:40],
         "src": (body.source or "Direct")[:60], "c": (body.country or None),
         "p": (body.path or "")[:255]})
    return {"ok": True}


# ── User-facing support (file + view own tickets) — mounted at /api/v1/support ───

support_router = APIRouter()


class CreateTicket(BaseModel):
    subject:  str
    message:  str
    priority: str = "normal"


@support_router.post("/tickets", status_code=201)
async def create_ticket(body: CreateTicket, current_user: User = Depends(_get_current_user),
                        db: AsyncSession = Depends(get_db)):
    tid = uuid4()
    await db.execute(text(
        "INSERT INTO support_tickets (id, user_id, subject, message, priority) "
        "VALUES (CAST(:id AS uuid), CAST(:u AS uuid), :s, :m, :p)"),
        {"id": str(tid), "u": str(current_user.id), "s": body.subject, "m": body.message, "p": body.priority})
    return {"id": str(tid), "status": "open"}


@support_router.get("/tickets")
async def my_tickets(current_user: User = Depends(_get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(text(
        "SELECT id, subject, message, status, priority, response, created_at "
        "FROM support_tickets WHERE user_id = CAST(:u AS uuid) ORDER BY created_at DESC"),
        {"u": str(current_user.id)})).mappings().all()
    return [{"id": str(r["id"]), "subject": r["subject"], "message": r["message"], "status": r["status"],
             "priority": r["priority"], "response": r["response"],
             "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]
