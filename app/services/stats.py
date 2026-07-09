"""Live per-room booking statistics.

Confirmed-booking counts and revenue are aggregated directly from the booking
table on each read so they always reflect current state (surviving restarts,
cancellations and concurrent updates) and never drift.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Booking


def get(db: Session, room_id: int) -> dict:
    count = (
        db.query(func.count(Booking.id))
        .filter(Booking.room_id == room_id, Booking.status == "confirmed")
        .scalar()
    ) or 0
    revenue = (
        db.query(func.coalesce(func.sum(Booking.price_cents), 0))
        .filter(Booking.room_id == room_id, Booking.status == "confirmed")
        .scalar()
    ) or 0
    return {"count": count, "revenue": revenue}
