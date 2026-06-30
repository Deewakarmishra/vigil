"""Append-only, hash-chained audit log.

Each row's hash covers the previous row's hash plus this row's content, so any
tampering with history is detectable. This is the artifact procurement and (for
the regulated forks) examiners actually check.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from vigil.models.audit import AuditLog


def _canonical(*parts: object) -> str:
    return json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))


def _row_hash(prev_hash: str | None, action: str, actor: str, before: dict, after: dict, meta: dict) -> str:
    payload = _canonical(prev_hash or "", action, actor, before, after, meta)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_audit(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    action: str,
    actor: str = "agent",
    before: dict | None = None,
    after: dict | None = None,
    meta: dict | None = None,
    case_id: uuid.UUID | None = None,
) -> AuditLog:
    before, after, meta = before or {}, after or {}, meta or {}
    last = session.scalars(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(desc(AuditLog.created_at)).limit(1)
    ).first()
    prev = last.hash if last else None
    row = AuditLog(
        tenant_id=tenant_id,
        case_id=case_id,
        action=action,
        actor=actor,
        before=before,
        after=after,
        meta=meta,
        prev_hash=prev,
        hash=_row_hash(prev, action, actor, before, after, meta),
    )
    session.add(row)
    session.flush()
    return row


def verify_chain(session: Session, tenant_id: uuid.UUID) -> bool:
    rows = list(session.scalars(select(AuditLog).where(AuditLog.tenant_id == tenant_id).order_by(AuditLog.created_at)))
    prev: str | None = None
    for r in rows:
        expected = _row_hash(prev, r.action, r.actor, r.before, r.after, r.meta)
        if r.prev_hash != prev or r.hash != expected:
            return False
        prev = r.hash
    return True
