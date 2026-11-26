"""Payments: money received from a customer, allocated to their invoices.

One transaction per payment. Nothing here moves stock. Outstanding is derived on read
(invoice total - allocations), never stored, so it can't drift from the payments that back it.

The Idempotency-Key header gates POST /payments the same way it does POST /orders: a replayed
key with the same body returns the first receipt (never a second one); a different body under the
same key is a 409 conflict; keys belong to the user who first used them. Shares the
`idempotency_key` table and the `route` field tells them apart.
"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.auth.models import AppUser
from app.billing.models import Invoice, InvoiceStatus
from app.core.errors import AppError, not_found
from app.masters import service as masters
from app.payments.models import Payment, PaymentAllocation
from app.payments.schemas import (
    AllocationOut,
    CustomerOutstanding,
    InvoiceOutstanding,
    PaymentCreate,
    PaymentOut,
)
from app.sales.models import IdempotencyKey

PAYMENT_ROUTE = "POST /payments"


def _allocated(db: Session, invoice_id: int) -> int:
    """How much has already been allocated to an invoice across all payments."""
    return int(
        db.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount_paise), 0)).where(
                PaymentAllocation.invoice_id == invoice_id
            )
        )
    )


def _out(db: Session, payment: Payment, invoices: dict[int, Invoice]) -> PaymentOut:
    return PaymentOut(
        id=payment.id,
        customer_id=payment.customer_id,
        payment_date=payment.payment_date,
        amount_paise=payment.amount_paise,
        reference=payment.reference,
        allocations=[
            AllocationOut(
                invoice_id=a.invoice_id,
                invoice_no=invoices[a.invoice_id].invoice_no,
                amount_paise=a.amount_paise,
            )
            for a in payment.allocations
        ],
    )


def _request_hash(data: PaymentCreate) -> str:
    """A stable fingerprint of the request body: same body → same hash → replay as one."""
    return hashlib.sha256(data.model_dump_json().encode()).hexdigest()


def _replay(existing: IdempotencyKey, request_hash: str, user: AppUser) -> PaymentOut:
    # Same rule as orders: the key belongs to the user who first used it. Handing a receipt to a
    # different user who happened to reuse the key would leak the customer and the amount.
    if existing.user_id != user.id:
        raise AppError(403, "FORBIDDEN", "this Idempotency-Key belongs to another user")
    if existing.route != PAYMENT_ROUTE or existing.request_hash != request_hash:
        raise AppError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "this Idempotency-Key was already used for a different request",
        )
    return PaymentOut.model_validate(existing.response_json)


def record_payment(db: Session, key: str, data: PaymentCreate, user: AppUser) -> PaymentOut:
    """Record a receipt and allocate it to invoices. The allocations must sum to the amount, and
    no invoice may be paid beyond its total (checked under a row lock, so concurrent payments to
    the same invoice can't both slip past). A cancelled invoice takes no payment.

    Idempotency: a repeat of the same key + same body returns the first receipt; a different body
    under the same key is a 409."""
    request_hash = _request_hash(data)
    existing = db.get(IdempotencyKey, key)
    if existing is not None:
        return _replay(existing, request_hash, user)

    customer = masters.get_customer(db, data.customer_id)
    allocated_total = sum(a.amount_paise for a in data.allocations)
    if allocated_total != data.amount_paise:
        raise AppError(
            422,
            "ALLOCATION_MISMATCH",
            f"allocations total {allocated_total} but the payment is {data.amount_paise}",
        )
    ids = [a.invoice_id for a in data.allocations]
    if len(set(ids)) != len(ids):
        raise AppError(422, "DUPLICATE_ALLOCATION", "an invoice is allocated twice in one payment")
    # Everything from the first INSERT to the commit runs in one try: a concurrent double-tap
    # under the same key fires the UNIQUE on idempotency_key, so we roll back and replay the
    # winner instead of 500-ing the loser (same guard orders.service uses).
    try:
        # Lock the invoice rows (id order) so a concurrent payment to the same invoice waits and
        # sees our allocation before it runs its own over-allocation check.
        invoices = {
            inv.id: inv
            for inv in db.scalars(
                select(Invoice).where(Invoice.id.in_(ids)).order_by(Invoice.id).with_for_update()
            )
        }
        payment = Payment(
            customer_id=customer.id,
            payment_date=data.payment_date,
            amount_paise=data.amount_paise,
            reference=data.reference,
            created_by=user.id,
        )
        db.add(payment)
        db.flush()
        for alloc in data.allocations:
            invoice = invoices.get(alloc.invoice_id)
            if invoice is None:
                raise not_found("invoice", alloc.invoice_id)
            if invoice.customer_id != customer.id:
                raise AppError(
                    422, "WRONG_CUSTOMER", f"{invoice.invoice_no} is not this customer's"
                )
            if invoice.status == InvoiceStatus.CANCELLED.value:
                raise AppError(409, "INVOICE_CANCELLED", f"{invoice.invoice_no} is cancelled")
            already = _allocated(db, invoice.id)
            if already + alloc.amount_paise > invoice.total_paise:
                raise AppError(
                    409,
                    "OVER_ALLOCATION",
                    f"{invoice.invoice_no}: {already + alloc.amount_paise} exceeds its total "
                    f"{invoice.total_paise}",
                    details={
                        "invoice_id": invoice.id,
                        "total_paise": invoice.total_paise,
                        "already_paid_paise": already,
                        "requested_paise": alloc.amount_paise,
                    },
                )
            db.add(
                PaymentAllocation(
                    payment_id=payment.id,
                    invoice_id=invoice.id,
                    amount_paise=alloc.amount_paise,
                )
            )
        db.flush()
        db.refresh(payment)
        out = _out(db, payment, invoices)
        db.add(
            IdempotencyKey(
                key=key,
                user_id=user.id,
                route=PAYMENT_ROUTE,
                request_hash=request_hash,
                status_code=201,
                response_json=out.model_dump(mode="json"),
            )
        )
        audit.record(
            db,
            entity="payment",
            entity_id=payment.id,
            action="RECORD",
            user_id=user.id,
            after=out.model_dump(mode="json"),
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        winner = db.get(IdempotencyKey, key)
        if winner is None:
            raise
        return _replay(winner, request_hash, user)
    return out


def customer_outstanding(db: Session, customer_id: int) -> CustomerOutstanding:
    """What a customer still owes: for each non-cancelled invoice, total - allocations, summed."""
    masters.get_customer(db, customer_id)  # 404 if the customer does not exist
    invoices = db.scalars(
        select(Invoice)
        .where(Invoice.customer_id == customer_id, Invoice.status != InvoiceStatus.CANCELLED.value)
        .order_by(Invoice.id)
    )
    rows: list[InvoiceOutstanding] = []
    total_outstanding = 0
    for invoice in invoices:
        paid = _allocated(db, invoice.id)
        owing = invoice.total_paise - paid
        total_outstanding += owing
        if owing != 0:
            rows.append(
                InvoiceOutstanding(
                    invoice_id=invoice.id,
                    invoice_no=invoice.invoice_no,
                    total_paise=invoice.total_paise,
                    paid_paise=paid,
                    outstanding_paise=owing,
                )
            )
    return CustomerOutstanding(
        customer_id=customer_id, outstanding_paise=total_outstanding, invoices=rows
    )
