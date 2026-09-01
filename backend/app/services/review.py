"""Human authority — where automation stops and a person decides.

An adjuster can approve, amend, reject or ask for more. Whatever they choose, the write
that follows travels the same path as an autonomous one: a scoped approval token, a signed
envelope, six gateway checks, one ledger entry. Being a person does not exempt the action
from the control plane; it is what authorises it.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import AUTHORITY_LIMITS_EUR
from app.models import Claim, ReviewTask
from app.personas import staff_by_id
from app.semantic import query_api
from app.services import ledger
from app.zero_trust.crypto_guard import sign_action
from app.zero_trust.write_gateway import gateway

# Acts that move money, and acts that record a professional judgement. Conflating the two
# was the platform's sharpest structural error: an assessor holding no settlement authority
# could not confirm a total loss, and an investigator could not clear a claim — the majority
# outcome in real SIU work — while both could decline a claim outright, because the
# authority check only ever guarded approvals.
MONEY_DECISIONS = ("approve", "amend")
FINDING_DECISIONS = ("confirm", "release", "refer", "request_more",
                     "recovered", "no_recovery")
ADVERSE_DECISIONS = ("reject",)
DECISIONS = MONEY_DECISIONS + ADVERSE_DECISIONS + FINDING_DECISIONS

# Declining a claim is the most consequential outcome on a file and is not a technical
# finding. It needs settlement authority even though it pays nothing.
DECLINE_REQUIRES_AUTHORITY = True

# Which verbs each queue accepts. A task is not a generic decision slot: a recovery task
# is a question about pursuing a third party, not a second chance to settle the claim, and
# treating it as one wrote a second signed settlement against a claim already paid.
QUEUE_VERBS: dict[str, tuple[str, ...]] = {
    "handler":     ("approve", "amend", "reject", "request_more", "refer"),
    "coverage":    ("approve", "amend", "reject", "request_more", "refer"),
    "operations":  ("approve", "amend", "reject", "request_more", "refer"),
    "large_loss":  ("approve", "amend", "reject", "request_more", "refer"),
    "injury":      ("approve", "amend", "reject", "request_more", "refer"),
    # The assessor gives a technical opinion and never settles.
    "assessment":  ("confirm", "reject", "request_more"),
    # The investigator reports signals and releases or refers; never decides the money.
    "siu":         ("release", "refer", "request_more"),
    # Recovery is about the counterparty, not about paying the insured again.
    "recovery":    ("recovered", "no_recovery", "request_more"),
    "security":    ("release", "refer", "request_more"),
}

RECOVERY_DECISIONS = ("recovered", "no_recovery")


class ReviewError(RuntimeError):
    pass


def queue_state(db: Session, queue: str | None = None) -> dict[str, Any]:
    result = query_api.execute("get_queue_state", db=db, queue=queue)
    rows = result["data"]
    return {
        "tasks": rows,
        "provenance": result["provenance"],
        "queues": _queue_summary(db),
        "authority_limits_eur": AUTHORITY_LIMITS_EUR,
    }


def _queue_summary(db: Session) -> list[dict[str, Any]]:
    tasks = db.scalars(select(ReviewTask)).all()
    summary: dict[str, dict[str, Any]] = {}
    now = dt.datetime.now(dt.timezone.utc)
    for t in tasks:
        entry = summary.setdefault(
            t.queue or "unassigned",
            {"queue": t.queue or "unassigned", "open": 0, "resolved": 0,
             "sla_breached": 0, "value_eur": 0.0},
        )
        if t.status == "resolved":
            entry["resolved"] += 1
        else:
            entry["open"] += 1
            entry["value_eur"] = round(
                entry["value_eur"] + float(t.proposed_amount_eur or 0.0), 2
            )
            due = t.sla_due_at
            if due is not None:
                due = due if due.tzinfo else due.replace(tzinfo=dt.timezone.utc)
                if due < now:
                    entry["sla_breached"] += 1
    return sorted(summary.values(), key=lambda e: -e["open"])


def task_detail(db: Session, task_id: str) -> dict[str, Any] | None:
    task = db.get(ReviewTask, task_id)
    if task is None:
        return None
    claim = db.get(Claim, task.claim_reference)
    claim_360 = query_api.execute("get_claim_360", db=db, reference=task.claim_reference)
    coverage = query_api.execute("get_coverage_assessment", db=db, reference=task.claim_reference)
    estimates = query_api.execute("get_estimates", db=db, reference=task.claim_reference)
    risk = query_api.execute("get_risk_signals", db=db, reference=task.claim_reference)
    extractions = query_api.execute("get_extractions", db=db, reference=task.claim_reference)

    return {
        "task": {
            "task_id": task.task_id,
            "claim_reference": task.claim_reference,
            "queue": task.queue,
            "reason": task.reason,
            "reason_detail": task.reason_detail,
            "authority_required": task.authority_required,
            "authority_limit_eur": task.authority_limit_eur,
            "priority": task.priority,
            "status": task.status,
            "assigned_to": task.assigned_to,
            "proposed_decision": task.proposed_decision,
            "proposed_amount_eur": task.proposed_amount_eur,
            "violations": task.violations or [],
            "decision": task.decision,
            "decision_note": task.decision_note,
            "resolved_by": task.resolved_by,
            "approval_ref": task.approval_ref,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "sla_due_at": task.sla_due_at.isoformat() if task.sla_due_at else None,
            "resolved_at": task.resolved_at.isoformat() if task.resolved_at else None,
        },
        # The evidence workspace: document, extraction, clause and reasoning side by side.
        "workspace": {
            "claim": claim_360["data"],
            "coverage": coverage["data"],
            "estimates": estimates["data"],
            "risk": risk["data"],
            "documents": extractions["data"],
            "decision_package": _last_signed_package(db, task.claim_reference),
        },
        "claim_status": claim.status if claim else None,
    }


def _last_signed_package(db: Session, reference: str) -> dict[str, Any] | None:
    entries = [e for e in ledger.all_entries(db) if e["claim_id"] == reference]
    return entries[-1] if entries else None


def _onward_queue_for(claim: Claim, task: ReviewTask) -> str:
    """Where a confirmed technical finding goes for the money decision.

    Sized on the amount *proposed*, not on the claim's settled amount — a claim awaiting a
    technical confirmation has not been settled yet, so its settled amount is zero and
    reading it would route every confirmed total loss to the handler regardless of value.
    """
    from app.config import AUTHORITY_LIMITS_EUR, LARGE_LOSS_THRESHOLD_EUR

    amount = float(task.proposed_amount_eur or claim.settlement_amount_eur or 0.0)
    if amount > LARGE_LOSS_THRESHOLD_EUR:
        return "large_loss"
    return "operations" if amount > AUTHORITY_LIMITS_EUR["claim_handler"] else "handler"


def _open_recovery_if_any(
    db: Session, claim: Claim, *, previous: ReviewTask
) -> ReviewTask | None:
    """Raise a recovery task where a paid claim has somebody to recover from.

    Deliberately conservative: a recovery needs a third party on the claim and a payment
    that has actually been made. Without a third-party record the platform cannot say who
    is being pursued — that is a gap this does not close — but it can at least put the file
    in front of the person whose job it is, which is more than a status nobody ever reached.
    """
    if not claim.third_party_involved:
        return None
    if float(claim.settlement_amount_eur or 0.0) <= 0.0:
        return None

    # The same test the platform's own liability tool applies. Opening a recovery on a
    # claim `get_liability_position` calls self-inflicted put the file in front of a handler
    # with nobody to pursue — a made-up work item, which is worse than none.
    from app.agents.tools import SELF_INFLICTED_INCIDENTS

    if claim.incident_type in SELF_INFLICTED_INCIDENTS:
        return None

    existing = db.scalars(
        select(ReviewTask).where(
            ReviewTask.claim_reference == claim.reference,
            ReviewTask.queue == "recovery",
            ReviewTask.status == "open",
        )
    ).first()
    if existing is not None:
        return existing

    from app.models import Policy

    policy = db.get(Policy, claim.policy_number)
    excess = float(policy.excess_eur or 0.0) if policy else 0.0
    claim.status = "recovery_open"
    return _raise_successor(
        db, claim=claim, previous=previous, queue="recovery",
        reason="third_party_recovery",
        reason_detail=(
            f"Paid EUR {claim.settlement_amount_eur:,.2f} with a third party involved. "
            f"The customer is also out of pocket for the EUR {excess:,.2f} excess."
        ),
    )


def _handoff_for(
    decision: str, claim: Claim, task: ReviewTask, staff: dict[str, Any]
) -> tuple[str, str, str]:
    """Where a recorded finding sends the claim, and why."""
    role = staff["role_label"]
    if decision == "confirm":
        onward = _onward_queue_for(claim, task)
        return (
            onward, "technical_position_confirmed",
            f"{role} confirmed the technical position; the settlement decision is next.",
        )
    if decision == "release":
        return (
            "handler", "released_no_finding",
            f"{role} found nothing to substantiate; the claim returns to the handler.",
        )
    return (
        "siu", "referred_for_investigation",
        f"{role} referred the claim for investigation.",
    )


def _raise_successor(
    db: Session,
    *,
    claim: Claim,
    previous: ReviewTask,
    queue: str,
    reason: str,
    reason_detail: str,
    finding: str = "",
) -> ReviewTask:
    """The next task in the chain, carrying the finding that produced it.

    Refuses to stack: a claim already open on the target queue gets its existing task
    updated rather than a second one beside it. Without this a referral from the SIU queue
    back to SIU — which the verb set allows, because a referral onward is legitimate —
    would chain forever and put two open items on one desk for one claim.
    """
    import secrets

    from app.config import AUTHORITY_LIMITS_EUR
    from app.personas import QUEUE_OWNERS

    standing = db.scalars(
        select(ReviewTask).where(
            ReviewTask.claim_reference == claim.reference,
            ReviewTask.queue == queue,
            ReviewTask.status == "open",
            ReviewTask.task_id != previous.task_id,
        )
    ).first()
    if standing is not None:
        standing.reason = reason
        standing.reason_detail = (
            f"{reason_detail} {finding}".strip() if finding else reason_detail
        )
        standing.proposed_amount_eur = previous.proposed_amount_eur
        standing.proposed_decision = previous.proposed_decision
        return standing

    owners = QUEUE_OWNERS.get(queue) or ("claim_handler",)
    authority_role = owners[0]
    successor = ReviewTask(
        task_id=f"TSK-{secrets.token_hex(4).upper()}",
        claim_reference=claim.reference,
        reason=reason,
        reason_detail=(f"{reason_detail} {finding}".strip() if finding else reason_detail),
        queue=queue,
        authority_required=authority_role,
        authority_limit_eur=AUTHORITY_LIMITS_EUR.get(authority_role, 0.0),
        priority=previous.priority or 2,
        status="open",
        proposed_decision=previous.proposed_decision,
        proposed_amount_eur=previous.proposed_amount_eur,
        # The clock keeps running from the original notification: the customer has been
        # waiting since the claim arrived, not since the hand-off.
        sla_due_at=previous.sla_due_at,
    )
    db.add(successor)
    return successor


def decide(
    db: Session,
    task_id: str,
    *,
    decision: str,
    user_id: str,
    amount_eur: float | None = None,
    note: str = "",
) -> dict[str, Any]:
    """Record a human decision and, where it authorises money, write it once, signed."""
    if decision not in DECISIONS:
        raise ReviewError(f"'{decision}' is not one of {DECISIONS}.")

    task = db.get(ReviewTask, task_id)
    if task is None:
        raise ReviewError(f"Task {task_id} not found.")
    if task.status == "resolved":
        raise ReviewError(f"Task {task_id} has already been resolved.")

    staff = staff_by_id(user_id)
    if staff is None:
        raise ReviewError(f"'{user_id}' is not a known user.")

    # The verb has to belong to the queue, and the queue has to belong to the role. Neither
    # was checked, so any role could use any verb on any task — including settling a claim
    # a second time from its own recovery task.
    allowed = QUEUE_VERBS.get(task.queue)
    if allowed is not None and decision not in allowed:
        raise ReviewError(
            f"'{decision}' is not an outcome the {task.queue} queue accepts. "
            f"It accepts: {', '.join(allowed)}."
        )
    if task.queue not in set(staff.get("queues") or ()):
        raise ReviewError(
            f"{staff['role_label']} does not work the '{task.queue}' queue."
        )

    claim = db.get(Claim, task.claim_reference)
    if claim is None:
        raise ReviewError(f"Claim {task.claim_reference} not found.")

    role = staff["role"]
    authority = AUTHORITY_LIMITS_EUR.get(role, 0.0)
    steps: list[dict[str, Any]] = []
    approval_ref: str | None = None
    write_result: dict[str, Any] | None = None

    settle_amount = (
        round(float(amount_eur), 2) if amount_eur is not None
        else round(float(task.proposed_amount_eur or 0.0), 2)
    )

    # A decline is an act of authority even at nil. Previously the check sat inside the
    # approve branch, so a EUR 0-authority investigator could close a claim as declined
    # through the API — the one outcome that role must never own.
    if decision == "reject" and DECLINE_REQUIRES_AUTHORITY and authority <= 0.0:
        steps.append({
            "step": "authority_check", "passed": False,
            "detail": (
                f"{staff['role_label']} holds no settlement authority and cannot decline a "
                "claim. Record a finding and refer it to someone who can."
            ),
        })
        return {
            "accepted": False,
            "reason": "insufficient_authority_to_decline",
            "required_authority_eur": 0.01,
            "your_authority_eur": authority,
            "steps": steps,
        }

    # A claim that has already been settled is not settled again from another task. The
    # write gateway's idempotency is per action envelope, so a fresh nonce and a fresh
    # approval sail through it — the guard has to be here, on the claim's own state.
    if decision in MONEY_DECISIONS and float(claim.settlement_amount_eur or 0.0) > 0.0:
        steps.append({
            "step": "already_settled", "passed": False,
            "detail": (
                f"{claim.reference} has already been settled at "
                f"EUR {claim.settlement_amount_eur:,.2f}. A further payment is a "
                "supplementary claim, not a second approval of this one."
            ),
        })
        return {
            "accepted": False,
            "reason": "claim_already_settled",
            "steps": steps,
        }

    if decision in MONEY_DECISIONS:
        from app.config import LARGE_LOSS_THRESHOLD_EUR

        # Above every authority in the book this is a large loss. It is refused here like
        # any other over-authority act, but the refusal says where it actually goes rather
        # than leaving the file with nowhere to be.
        if settle_amount > LARGE_LOSS_THRESHOLD_EUR:
            steps.append({
                "step": "authority_check", "passed": False,
                "detail": (
                    f"EUR {settle_amount:,.2f} is above the large-loss threshold of "
                    f"EUR {LARGE_LOSS_THRESHOLD_EUR:,.2f}. This is a large-loss referral, "
                    "not a desk approval."
                ),
            })
            task.queue = "large_loss"
            claim.assigned_queue = "large_loss"
            db.commit()
            return {
                "accepted": False,
                "reason": "large_loss_referral",
                "required_authority_eur": settle_amount,
                "your_authority_eur": authority,
                "steps": steps,
            }

        if settle_amount > authority:
            # Refused before anything is signed. This is the check that stops an adjuster
            # settling a supervisor's claim, and it does not depend on the UI hiding a button.
            steps.append({
                "step": "authority_check", "passed": False,
                "detail": (
                    f"{staff['role_label']} authority is EUR {authority:,.2f}; "
                    f"EUR {settle_amount:,.2f} requires a higher authority level."
                ),
            })
            return {
                "accepted": False,
                "reason": "insufficient_authority",
                "required_authority_eur": settle_amount,
                "your_authority_eur": authority,
                "steps": steps,
            }

        steps.append({
            "step": "authority_check", "passed": True,
            "detail": f"{staff['role_label']} may approve up to EUR {authority:,.2f}.",
        })

        token = gateway.issue_approval(
            claim_id=claim.reference,
            action="claim.settlement.write",
            amount_eur=settle_amount,
            approver_id=user_id,
            approver_role=role,
            decision=decision,
            note=note,
        )
        approval_ref = token.ref
        steps.append({
            "step": "scoped_approval", "passed": True,
            "detail": (
                f"Approval {token.ref} issued — scoped to {claim.reference}, action "
                f"claim.settlement.write, limit EUR {token.limit_eur:,.2f}, expires "
                f"{token.expires_at}."
            ),
            "data": token.as_dict(),
        })

        payload = {
            "claim_id": claim.reference,
            "decision": "Approved",
            "settlement_amount_eur": settle_amount,
            "severity": claim.severity,
            "status": "approved",
            "approved_by": user_id,
            "approver_role": role,
            "human_decision": decision,
            "amended_from_eur": (
                round(float(task.proposed_amount_eur or 0.0), 2)
                if decision == "amend" else None
            ),
            "note": note,
            "review_task_id": task.task_id,
        }
        envelope = sign_action(
            payload=payload,
            nonce=ledger.next_nonce(db),
            claim_id=claim.reference,
            run_id=f"review-{task.task_id}",
            step_id="human.approve",
            agent_id="HitlCoordinatorAgent",
            action="claim.settlement.write",
            user_id=user_id,
            approval_ref=approval_ref,
            prev_hash=ledger.last_chain_hash(db),
        )
        steps.append({
            "step": "sign", "passed": True,
            "detail": f"Signed with nonce {envelope.nonce} by {envelope.signer}.",
            "data": {k: v for k, v in envelope.as_dict().items() if k != "payload"},
        })

        result = gateway.submit(
            envelope.as_dict(), requires_approval=True, amount_eur=settle_amount
        )
        ledger.append(
            db, envelope.as_dict(),
            status="VERIFIED_AUTHENTIC" if result.accepted else "REJECTED_AT_GATEWAY",
        )
        write_result = result.as_dict()
        steps.append({
            "step": "write_gateway", "passed": result.accepted,
            "detail": result.reason, "data": write_result,
        })

        if result.accepted:
            claim.decision = "Approved"
            claim.status = "approved"
            claim.stage = "settlement"
            claim.settlement_amount_eur = settle_amount
            claim.closed_at = dt.datetime.now(dt.timezone.utc)

            # A claim settled by a person is exactly as likely to have a recovery as one
            # settled autonomously — more so, because third-party claims are the ones that
            # go to a person. The graph only reached its recovery node on the
            # straight-through edge and a human approval never re-enters the graph, so
            # recovery_open was a status no claim in the system had ever held.
            recovery = _open_recovery_if_any(db, claim, previous=task)
            if recovery is not None:
                steps.append({
                    "step": "recovery_raised", "passed": True,
                    "detail": (
                        f"Third party involved and the claim is paid: {recovery.task_id} "
                        f"raised on the recovery queue for EUR {settle_amount:,.2f} plus "
                        "the excess."
                    ),
                })

    elif decision == "reject":
        claim.decision = "Declined"
        claim.status = "declined"
        claim.stage = "closed"
        claim.settlement_amount_eur = 0.0
        claim.closed_at = dt.datetime.now(dt.timezone.utc)
        steps.append({
            "step": "record_outcome", "passed": True,
            "detail": "Declined by a named person, with the reason recorded on the claim.",
        })

    elif decision in RECOVERY_DECISIONS:
        # Recovery closes on the recovery, not on the claim. Without a counterparty record
        # the platform cannot say who was pursued or what came back — that gap is real and
        # unclosed — but the file stops being open work either way.
        claim.status = "closed" if decision == "no_recovery" else "recovery_open"
        if decision == "no_recovery":
            claim.stage = "closed"
            claim.closed_at = claim.closed_at or dt.datetime.now(dt.timezone.utc)
        steps.append({
            "step": "record_recovery_outcome", "passed": True,
            "detail": (
                f"{staff['role_label']} recorded the recovery as "
                + ("pursued and open." if decision == "recovered"
                   else "not worth pursuing; the file is closed.")
            ),
        })

    elif decision in ("confirm", "release", "refer"):
        # A finding is a hand-off, not an ending. Resolving the task without raising the
        # next one would leave the claim carrying a queue label with nothing on anybody's
        # desk — the same unowned silence the platform already had at awaiting_customer.
        onward, reason, detail = _handoff_for(decision, claim, task, staff)
        claim.status = "in_review"
        claim.stage = "human_review"
        claim.assigned_queue = onward
        successor = _raise_successor(
            db, claim=claim, previous=task, queue=onward, reason=reason,
            reason_detail=detail, finding=f"{staff['role_label']}: {note}" if note else "",
        )
        steps.append({
            "step": "record_finding", "passed": True,
            "detail": f"{detail} Raised {successor.task_id} on the {onward} queue.",
        })

    else:  # request_more
        claim.status = "awaiting_customer"
        claim.stage = "intake"
        steps.append({
            "step": "record_outcome", "passed": True,
            "detail": "Further information requested from the customer.",
        })

    # A write the gateway refused is not an approval. Resolving the task and recording
    # "Approved" against it regardless would put an outcome on the audit trail that never
    # happened — and leave the claim with no open task, so nobody would ever come back to
    # it. The task stays open and the refusal is on the file.
    if decision in MONEY_DECISIONS and write_result is not None and not write_result.get("accepted", True):
        task.decision_note = (
            f"{note} — write refused at the gateway: "
            f"{write_result.get('reason', 'unknown')}"
        ).strip(" —")
        db.commit()
        return {
            "accepted": False,
            "reason": "refused_at_the_write_gateway",
            "steps": steps,
        }

    task.status = "resolved"
    task.decision = {
        "approve": "Approved", "amend": "Approved (amended)",
        "reject": "Declined", "request_more": "Request Information",
        "confirm": "Technical position confirmed",
        "release": "Released — no finding established",
        "refer": "Referred for investigation",
        "recovered": "Recovery being pursued",
        "no_recovery": "No recovery worth pursuing",
    }.get(decision, decision.replace("_", " ").capitalize())
    task.decision_note = note
    task.resolved_by = user_id
    task.resolved_at = dt.datetime.now(dt.timezone.utc)
    task.approval_ref = approval_ref
    claim.human_touches = (claim.human_touches or 0) + 1
    claim.assigned_to = user_id
    db.commit()

    return {
        "accepted": True,
        "task_id": task.task_id,
        "claim_reference": claim.reference,
        "human_decision": decision,
        "recorded_decision": task.decision,
        "settlement_amount_eur": claim.settlement_amount_eur,
        "approver": {"user_id": user_id, "name": staff["name"], "role": staff["role_label"],
                     "authority_eur": authority},
        "approval_ref": approval_ref,
        "steps": steps,
        "write": write_result,
        "audit": ledger.audit_database(db),
    }


def assign(db: Session, task_id: str, user_id: str) -> dict[str, Any]:
    task = db.get(ReviewTask, task_id)
    if task is None:
        raise ReviewError(f"Task {task_id} not found.")
    staff = staff_by_id(user_id)
    if staff is None:
        raise ReviewError(f"'{user_id}' is not a known user.")

    # The verb has to belong to the queue, and the queue has to belong to the role. Neither
    # was checked, so any role could use any verb on any task — including settling a claim
    # a second time from its own recovery task.
    allowed = QUEUE_VERBS.get(task.queue)
    if allowed is not None and decision not in allowed:
        raise ReviewError(
            f"'{decision}' is not an outcome the {task.queue} queue accepts. "
            f"It accepts: {', '.join(allowed)}."
        )
    if task.queue not in set(staff.get("queues") or ()):
        raise ReviewError(
            f"{staff['role_label']} does not work the '{task.queue}' queue."
        )
    if task.queue not in staff["queues"]:
        raise ReviewError(
            f"{staff['name']} does not work the {task.queue} queue "
            f"(queues: {staff['queues']})."
        )
    task.assigned_to = user_id
    task.status = "in_progress"
    db.commit()
    return {"task_id": task.task_id, "assigned_to": user_id, "status": task.status}
