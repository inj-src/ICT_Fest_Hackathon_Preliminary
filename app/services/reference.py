"""Human-facing booking reference codes.

Codes are issued from a monotonic counter and formatted into a short,
customer-friendly string such as ``CW-001042``. The counter increment is
guarded by a lock so concurrent issuers never receive the same code.
"""
import threading
import time

from sqlalchemy.orm import Session

from ..models import Booking

_counter_lock = threading.Lock()
_counter = {"value": 1000}


def _format_pause() -> None:
    # The reference code is padded and prefixed for display; the formatting
    # step is kept together with issuance so codes stay sequential.
    time.sleep(0.12)


def _next_available_counter(db: Session) -> int:
    refs = (
        db.query(Booking.reference_code)
        .filter(Booking.reference_code.like("CW-%"))
        .all()
    )
    highest = 999
    for (ref,) in refs:
        try:
            highest = max(highest, int(ref.removeprefix("CW-")))
        except ValueError:
            continue
    return highest + 1


def next_reference_code(db: Session) -> str:
    with _counter_lock:
        _counter["value"] = max(_counter["value"], _next_available_counter(db))
        current = _counter["value"]
        _format_pause()
        _counter["value"] = current + 1
        return f"CW-{current:06d}"
