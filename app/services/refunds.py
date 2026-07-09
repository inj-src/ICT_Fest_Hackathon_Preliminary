"""Refund bookkeeping.

When a booking is cancelled a refund is calculated from its price and the
applicable notice tier, then written to the refund ledger with a processed
status. Amounts are stored in whole cents and half-cent values round UP.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Booking, RefundLog


def compute_refund_amount(price_cents: int, percent: int) -> int:
    """Refund in whole cents, rounding half-cents up.

    Integer ceiling division keeps the response amount and the stored ledger
    amount identical (percent is one of 0, 50, 100).
    """
    return (price_cents * percent + 99) // 100


def log_refund(db: Session, booking: Booking, percent: int) -> tuple[RefundLog, int]:
    """Stage a refund entry for ``booking``.

    The entry is added to the session but NOT committed here; the caller is
    responsible for committing it together with the booking status transition
    so the cancel is atomic.
    """
    amount_cents = compute_refund_amount(booking.price_cents, percent)
    entry = RefundLog(
        booking_id=booking.id,
        amount_cents=amount_cents,
        status="processed",
        processed_at=datetime.utcnow(),
    )
    db.add(entry)
    return entry, amount_cents
