# Bug Report

This document outlines all 24 bugs discovered in the codebase, their root causes based on the PDF specification, and the applied fixes.

---

### Bug 1: Logout JWT Revocation
- **File / Line:** `app/auth.py` (~Line 97)
- **What:** The `get_token_payload` function checks if the user's ID (`sub`) was in the revoked tokens list, rather than the unique token ID (`jti`), rendering the token invalidation useless.
- **Fix:** Changed `if payload.get("sub") in _revoked_tokens` to use `payload.get("jti")`.

### Bug 2: Timezone Conversion
- **File / Line:** `app/timeutils.py` (~Line 12)
- **What:** When a datetime string had a UTC offset, `parse_input_datetime` simply removed the offset (`replace(tzinfo=None)`) without shifting the time to UTC first, violating the storage business rule.
- **Fix:** Converted the datetime to UTC before stripping the timezone: `dt.astimezone(timezone.utc).replace(tzinfo=None)`.

### Bug 3: Registration Duplicate Username
- **File / Line:** `app/routers/auth.py` (~Line 37)
- **What:** When a duplicate username was registered within an org, the API returned 200 OK with the existing user data instead of the required `409 USERNAME TAKEN` error.
- **Fix:** Added an explicit `raise AppError(409, "USERNAME_TAKEN", ...)` when `existing is not None`.

### Bug 4: Refresh Token Reuse
- **File / Line:** `app/routers/auth.py` (~Line 82)
- **What:** Refresh tokens were never invalidated upon use. The specification explicitly dictates they must be single-use.
- **Fix:** Validated the refresh token `jti` against `_revoked_tokens` and added it to the set after successful rotation.

### Bug 5: Pagination Offset Calculation
- **File / Line:** `app/routers/bookings.py` (~Line 135)
- **What:** The `list_bookings` offset was calculated as `page * limit` which caused page 1 to start at index 10, incorrectly skipping the first page of items.
- **Fix:** Adjusted the offset formula to `(page - 1) * limit`.

### Bug 6: Pagination Limit Hardcoding
- **File / Line:** `app/routers/bookings.py` (~Line 135)
- **What:** The `.limit(10)` function in `list_bookings` was hardcoded, completely ignoring the `limit` query parameter.
- **Fix:** Changed to `.limit(limit)`.

### Bug 7: Pagination Ordering
- **File / Line:** `app/routers/bookings.py` (~Line 135)
- **What:** `list_bookings` incorrectly ordered bookings descending (`Booking.start_time.desc()`), violating the "sorted ascending by start time" specification.
- **Fix:** Changed the sort criteria to `Booking.start_time.asc()`.

### Bug 8: Booking Details Start Time Override
- **File / Line:** `app/routers/bookings.py` (~Line 161)
- **What:** The `get_booking` endpoint overrode the `start_time` field with the booking's `created_at` timestamp before returning.
- **Fix:** Removed the `response["start_time"] = iso_utc(booking.created_at)` assignment.

### Bug 9: Multi-tenancy Visibility Leak
- **File / Line:** `app/routers/bookings.py` (~Line 161)
- **What:** Members were allowed to read any booking in the organization (including other members') via the `get_booking` endpoint because a role/user ID check was missing.
- **Fix:** Added an explicit permission check: `if user.role != "admin" and booking.user_id != user.id: raise AppError(...)`.

### Bug 10: Cancellation Notice Tier Math
- **File / Line:** `app/routers/bookings.py` (~Line 200)
- **What:** The cancellation notice tier checked `if notice_hours > 48` for a 100% refund, violating the specification which states `>= 48`.
- **Fix:** Changed the conditional to `>= 48`.

### Bug 11: Cancellation 0% Refund Tier
- **File / Line:** `app/routers/bookings.py` (~Line 200)
- **What:** Notices under 24 hours were given a `refund_percent = 50` rather than the specified 0%.
- **Fix:** Changed the `else:` block to `refund_percent = 0`.

### Bug 12: Refund Rounding Policy
- **File / Line:** `app/routers/bookings.py` (~Line 200)
- **What:** The `cancel_booking` logic used python's native `round(...)` (banker's rounding - half-to-even) instead of "half-cents rounding up".
- **Fix:** Implemented precise integer rounding: `(booking.price_cents * refund_percent + 50) // 100`.

### Bug 13: Cancellation Double Refund (Race Condition)
- **File / Line:** `app/routers/bookings.py` (~Line 200)
- **What:** A race condition existed where concurrent cancel requests for the same booking passed the status check before either committed, leading to duplicate refund log entries.
- **Fix:** Replaced python state assignment with an atomic SQLite update query: `updated = db.query(...).update({"status": "cancelled"})`. If `updated == 0`, a 409 is raised.

### Bug 14: Overbooking and Quota (Race Condition)
- **File / Line:** `app/routers/bookings.py` (~Line 100)
- **What:** The `create_booking` endpoint performed python-side conflict/quota checks and then inserted later, allowing race conditions to bypass room conflicts and quotas.
- **Fix:** Wrapped the conflict-checking and database insertion logic in a global `threading.Lock()`.

### Bug 15: Booking Minimum Duration
- **File / Line:** `app/routers/bookings.py` (~Line 92)
- **What:** `create_booking` verified maximum duration but allowed 0 or negative hours.
- **Fix:** Added a lower bounds check: `or duration_hours < MIN_DURATION_HOURS`.

### Bug 16: Overlap Detection Formula
- **File / Line:** `app/routers/bookings.py` (~Line 49)
- **What:** `_has_conflict` evaluated `<` overlaps with `<=` (`start <= b.end_time`), incorrectly marking back-to-back bookings as conflicts.
- **Fix:** Replaced `<=` with strictly less than (`<`).

### Bug 17: Usage Report Cache Invalidation
- **File / Line:** `app/routers/bookings.py` (~Line 100)
- **What:** Creating a booking updated live revenue but failed to call `cache.invalidate_report`, serving stale reports to admins.
- **Fix:** Added `cache.invalidate_report(user.org_id)` after booking creation.

### Bug 18: Availability Cache Invalidation
- **File / Line:** `app/routers/bookings.py` (~Line 200)
- **What:** Canceling a booking failed to call `cache.invalidate_availability`, showing canceled slots as continually busy.
- **Fix:** Added `cache.invalidate_availability(booking.room_id, booking.start_time.date().isoformat())`.

### Bug 19: Refund Log Floating Point Inaccuracy
- **File / Line:** `app/services/refunds.py` (~Line 14)
- **What:** `log_refund` recalculated the refund amount from the percentage using float math, which caused precision mismatches with the frontend response.
- **Fix:** Modified `log_refund` to directly accept the already correctly-rounded `amount_cents` integer.

### Bug 20: Stats Aggregation (Race Condition)
- **File / Line:** `app/services/stats.py` (~Line 15)
- **What:** In-memory tracking of confirmed booking counts and revenues suffered from a read-modify-write race condition during the pause interval.
- **Fix:** Instantiated a `threading.Lock()` to synchronize state modifications within `record_create` and `record_cancel`.

### Bug 21: Rate Limit Window (Race Condition)
- **File / Line:** `app/services/ratelimit.py` (~Line 18)
- **What:** The sliding window algorithm suffered from a read-modify-write race condition in updating the array bucket.
- **Fix:** Instantiated a `threading.Lock()` to synchronize bucket modification.

### Bug 22: Reference Code Monotonicity (Race Condition)
- **File / Line:** `app/services/reference.py` (~Line 17)
- **What:** Concurrent requests read the same initial state of `_counter["value"]` before the pause, resulting in overlapping reference codes instead of unique monotonic ones.
- **Fix:** Instantiated a `threading.Lock()` to wrap the read/increment step.

### Bug 23: Notification Logging Deadlock
- **File / Line:** `app/services/notifications.py` (~Line 31)
- **What:** `notify_created` acquired `_email_lock` then `_audit_lock`, but `notify_cancelled` acquired `_audit_lock` then `_email_lock`. This created a classic concurrency deadlock under load.
- **Fix:** Aligned `notify_cancelled` to also acquire `_email_lock` first.

### Bug 24: Admin Export Cross-Org Data Leak
- **File / Line:** `app/services/export.py` (~Line 48)
- **What:** When an admin queried `GET /admin/export?room_id=...&include_all=true`, the `generate_export` logic routed to `fetch_bookings_raw(db, room_id)` which omitted `org_id` filtering, leaking data across multi-tenant boundaries.
- **Fix:** Replaced the `fetch_bookings_raw` branch with `_fetch_scoped(db, org_id, None, room_id)` which implicitly enforces the caller's `org_id`.

### Bug 25: Swagger UI Authorization Integration
- **File / Line:** `app/auth.py` (~Line 89)
- **What:** The `get_token_payload` dependency manually extracted the token from `request.headers.get("Authorization")` instead of using FastAPI's official `HTTPBearer` security scheme. This resulted in Swagger UI failing to display the "Authorize" button, breaking the interactive docs for protected endpoints.
- **Fix:** Updated the function to depend on `credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))` so Swagger UI natively supports token injection while preserving the original custom `AppError(401, ...)` logic.
