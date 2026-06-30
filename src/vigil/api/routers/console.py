"""Operator console: dashboard, alert queue, the Alert-Disposition view, officer queue, SAR, eval, sources, audit."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from vigil.adapters import list_adapter_info
from vigil.api.dependencies import get_session
from vigil.api.templating import templates
from vigil.config import get_settings
from vigil.models.aml import Alert, Customer, SARDraft, TypologyHypothesis
from vigil.models.audit import AuditLog
from vigil.models.enums import AlertStatus, Disposition, ReviewStatus, SARStatus
from vigil.models.evaluation import EvalCase, EvalRun
from vigil.models.review import ReviewTask
from vigil.models.tenant import Tenant
from vigil.models.user import User
from vigil.services.audit import verify_chain, write_audit

router = APIRouter()


def _tenant(session: Session) -> Tenant | None:
    slug = get_settings().demo_brand_slug
    return session.scalars(select(Tenant).where(Tenant.slug == slug)).first()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    tenant = _tenant(session)
    ctx: dict = {"request": request, "tenant": tenant}
    if tenant:
        total = session.scalar(select(func.count()).select_from(Alert).where(Alert.tenant_id == tenant.id)) or 0

        def _count(status: str) -> int:
            return (
                session.scalar(
                    select(func.count()).select_from(Alert).where(Alert.tenant_id == tenant.id, Alert.status == status)
                )
                or 0
            )

        cleared = _count(AlertStatus.CLEARED.value)
        escalated = _count(AlertStatus.ESCALATED.value)
        rfi = _count(AlertStatus.RFI.value)
        sar_count = (
            session.scalar(
                select(func.count())
                .select_from(SARDraft)
                .join(Alert, SARDraft.alert_id == Alert.id)
                .where(Alert.tenant_id == tenant.id)
            )
            or 0
        )
        max_age = session.scalar(select(func.max(Alert.age_days)).where(Alert.tenant_id == tenant.id)) or 0
        ctx.update(
            total=total,
            cleared=cleared,
            escalated=escalated,
            rfi=rfi,
            sar_count=sar_count,
            max_age=int(max_age),
            clear_rate=round(100.0 * cleared / total, 1) if total else 0.0,
        )
    return templates.TemplateResponse(request, "console/dashboard.html", ctx)


@router.get("/alerts", response_class=HTMLResponse)
def alerts(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    tenant = _tenant(session)
    rows = []
    if tenant:
        items = list(
            session.scalars(select(Alert).where(Alert.tenant_id == tenant.id).order_by(desc(Alert.received_at)))
        )
        for a in items:
            cust = session.get(Customer, a.customer_id) if a.customer_id else None
            rows.append({"alert": a, "customer": cust, "scope": a.scope_json or {}})
    return templates.TemplateResponse(
        request, "console/alerts.html", {"request": request, "tenant": tenant, "rows": rows}
    )


@router.get("/alerts/{alert_id}", response_class=HTMLResponse)
def alert_card(alert_id: uuid.UUID, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    alert = session.get(Alert, alert_id)
    if alert is None:
        return HTMLResponse("alert not found", status_code=404)
    customer = session.get(Customer, alert.customer_id) if alert.customer_id else None
    hyps = list(session.scalars(select(TypologyHypothesis).where(TypologyHypothesis.alert_id == alert.id)))
    sar = session.scalars(select(SARDraft).where(SARDraft.alert_id == alert.id)).first()
    return templates.TemplateResponse(
        request,
        "console/alert_card.html",
        {
            "request": request,
            "alert": alert,
            "customer": customer,
            "scope": alert.scope_json or {},
            "hypotheses": hyps,
            "sar": sar,
        },
    )


@router.get("/alerts/{alert_id}/sar", response_class=HTMLResponse)
def sar_view(alert_id: uuid.UUID, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    alert = session.get(Alert, alert_id)
    sar = session.scalars(select(SARDraft).where(SARDraft.alert_id == alert_id)).first() if alert else None
    return templates.TemplateResponse(request, "console/sar.html", {"request": request, "alert": alert, "sar": sar})


@router.post("/alerts/{alert_id}/file")
def file_sar(alert_id: uuid.UUID, session: Session = Depends(get_session)) -> RedirectResponse:
    """Officer-only action: mark the SAR filed. The agent never files."""
    alert = session.get(Alert, alert_id)
    sar = session.scalars(select(SARDraft).where(SARDraft.alert_id == alert_id)).first() if alert else None
    if alert is not None and sar is not None and sar.status != SARStatus.FILED.value:
        officer = session.scalars(select(User).where(User.tenant_id == alert.tenant_id)).first()
        sar.status = SARStatus.FILED.value
        sar.filed_by = officer.id if officer else None
        before = {"status": alert.status}
        alert.status = AlertStatus.FILED.value
        write_audit(
            session,
            tenant_id=alert.tenant_id,
            case_id=alert.id,
            action="sar.file",
            actor="officer",
            before=before,
            after={"status": alert.status},
            meta={"alert": alert.external_alert_id},
        )
        session.commit()
    return RedirectResponse(url=f"/alerts/{alert_id}", status_code=303)


@router.get("/review", response_class=HTMLResponse)
def review(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    tenant = _tenant(session)
    rows = []
    if tenant:
        tasks = list(
            session.scalars(
                select(ReviewTask)
                .join(Alert, ReviewTask.alert_id == Alert.id)
                .where(Alert.tenant_id == tenant.id, ReviewTask.status == ReviewStatus.OPEN.value)
                .order_by(ReviewTask.created_at)
            )
        )
        for t in tasks:
            alert = session.get(Alert, t.alert_id)
            rows.append({"task": t, "alert": alert})
    return templates.TemplateResponse(request, "console/review.html", {"request": request, "rows": rows})


@router.post("/review/{task_id}/approve")
def review_approve(task_id: uuid.UUID, session: Session = Depends(get_session)) -> RedirectResponse:
    task = session.get(ReviewTask, task_id)
    if task is not None and task.status == ReviewStatus.OPEN.value:
        task.status = ReviewStatus.APPROVED.value
        alert = session.get(Alert, task.alert_id)
        if alert is not None:
            before = {"disposition": alert.disposition}
            alert.disposition = Disposition.ESCALATE.value
            write_audit(
                session,
                tenant_id=alert.tenant_id,
                case_id=alert.id,
                action="review.approve",
                actor="officer",
                before=before,
                after={"disposition": alert.disposition},
                meta={"task_id": str(task_id)},
            )
        session.commit()
    return RedirectResponse(url="/review", status_code=303)


@router.get("/eval", response_class=HTMLResponse)
def eval_view(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    run = session.scalars(select(EvalRun).order_by(desc(EvalRun.created_at)).limit(1)).first()
    cases_ = []
    if run:
        cases_ = list(session.scalars(select(EvalCase).where(EvalCase.eval_run_id == run.id)))
    return templates.TemplateResponse(request, "console/eval.html", {"request": request, "run": run, "cases": cases_})


@router.get("/sources", response_class=HTMLResponse)
def sources(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "console/sources.html", {"request": request, "adapters": list_adapter_info()}
    )


@router.get("/audit", response_class=HTMLResponse)
def audit(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    tenant = _tenant(session)
    rows, ok = [], True
    if tenant:
        rows = list(
            session.scalars(
                select(AuditLog).where(AuditLog.tenant_id == tenant.id).order_by(desc(AuditLog.created_at)).limit(100)
            )
        )
        ok = verify_chain(session, tenant.id)
    return templates.TemplateResponse(request, "console/audit.html", {"request": request, "rows": rows, "chain_ok": ok})
