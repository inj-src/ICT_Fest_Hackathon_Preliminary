# CoWork API Bug Report

This report summarizes the bugs found and fixed for the CoWork API preliminary
round. Each item lists the affected file(s), the incorrect behavior, and the
fix applied.

## 1. Offset-aware datetimes were not converted to UTC

- Files/lines: `app/timeutils.py:11-16`
- Bug: Offset-aware ISO datetimes were stripped with `replace(tzinfo=None)`.
  For example, `12:00+05:00` was stored as naive `12:00` instead of UTC
  `07:00`. This broke booking conflicts, availability, reports, quotas, and
  response times.
- Fix: Convert offset-aware inputs with `astimezone(timezone.utc)` before
  dropping tzinfo for naive-UTC storage.

## 2. Access-token lifetime was 15 hours instead of 900 seconds

- Files/lines: `app/auth.py:66-78`
- Bug: Access-token expiration used `timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES
  * 60)`, turning 15 minutes into 900 minutes.
- Fix: Use `timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)`, preserving the
  required 900-second access-token lifetime.

## 3. Logout did not invalidate access tokens

- Files/lines: `app/auth.py:118-145`, `app/routers/auth.py:282-285`,
  `app/models.py:72-78`
- Bug: Logout stored one token identifier but validation checked another, so a
  logged-out access token could still be reused.
- Fix: Store revoked access-token `jti` values in the durable `token_states`
  table and check that table during authenticated request parsing.

## 4. Refresh tokens were reusable

- Files/lines: `app/auth.py:103-133`, `app/routers/auth.py:264-279`,
  `app/models.py:72-78`
- Bug: `/auth/refresh` decoded a refresh token and issued new tokens without
  recording that the refresh token had been consumed. The same refresh token
  could be replayed repeatedly.
- Fix: Record consumed refresh-token `jti` values in `token_states` with a
  uniqueness guarantee. Reusing the same refresh token now returns 401.

## 5. Duplicate usernames returned success

- Files/lines: `app/routers/auth.py:186-242`
- Bug: Registering an existing username in the same organization returned the
  existing user with 201 instead of `409 USERNAME_TAKEN`.
- Fix: Raise `AppError(409, "USERNAME_TAKEN", ...)` when the same org already
  has the username. IntegrityError handling was also added for concurrent
  registration races.

## 6. Concurrent registration could surface database errors

- Files/lines: `app/routers/auth.py:219-236`
- Bug: Concurrent creation of the same organization or username could lose a
  unique-constraint race and produce an unhandled 500.
- Fix: Registration now flushes inside a transaction, catches `IntegrityError`,
  rolls back, re-evaluates the org/user state, and returns the correct 201 or
  409 response.

## 7. Back-to-back bookings were rejected as conflicts

- Files/lines: `app/routers/bookings.py:334-346`
- Bug: Conflict detection used inclusive comparisons, so a booking ending at
  10:00 conflicted with one starting at 10:00.
- Fix: Use the required strict overlap condition:
  `existing.start_time < new.end_time and new.start_time < existing.end_time`.

## 8. Double-booking and quota checks were not atomic

- Files/lines: `app/routers/bookings.py:312-316`, `app/routers/bookings.py:386-420`
- Bug: Booking creation checked conflicts and quota before inserting, but those
  checks were not coupled to the insert. Concurrent requests could all pass and
  create overlapping bookings or exceed quota.
- Fix: A shared booking write lock now protects the conflict check, quota check,
  reference-code generation, insert, and commit as one critical section.

## 9. Booking windows allowed past, zero, or negative durations

- Files/lines: `app/routers/bookings.py:391-400`
- Bug: `start_time` allowed a five-minute grace period in the past, and duration
  validation only enforced whole hours and max duration. Zero-hour and negative
  bookings could pass.
- Fix: Require `start_time > now`, require whole-hour duration, and enforce
  `1 <= duration_hours <= 8`.

## 10. Reference codes were not safe under concurrency or restart

- Files/lines: `app/models.py:55`, `app/services/reference.py:359-380`,
  `app/routers/bookings.py:412-420`
- Bug: Reference codes came from an unlocked in-memory counter and the database
  did not require uniqueness. Later, a locked counter alone still reset after
  restart and could collide with persisted bookings.
- Fix: Add a unique constraint on `Booking.reference_code`. Generate codes under
  a lock while seeding from the highest existing `CW-...` value in the database.

## 11. Rate limiting was not concurrency-safe

- Files/lines: `app/services/ratelimit.py:419-449`
- Bug: The rolling-window rate limiter used a shared dictionary without locking.
  Concurrent requests could each read the old bucket and all pass.
- Fix: Protect trim, append, store, and count with a `threading.Lock`.

## 12. Booking pagination used wrong sort, offset, and limit

- Files/lines: `app/routers/bookings.py:434-454`
- Bug: `GET /bookings` sorted descending, used `offset(page * limit)`, and
  hardcoded `limit(10)`, causing skipped first pages and ignored limits.
- Fix: Sort by ascending `start_time` then `id`, offset by `(page - 1) * limit`,
  and apply the requested `limit`.

## 13. Members could read other members' booking details

- Files/lines: `app/routers/bookings.py:456-483`
- Bug: `GET /bookings/{id}` filtered only by organization. A member could read
  another member's booking in the same org.
- Fix: After org-scoped lookup, non-admin users must also own the booking or
  receive `404 BOOKING_NOT_FOUND`.

## 14. Booking detail returned the wrong start time

- Files/lines: `app/routers/bookings.py:472-483`
- Bug: `GET /bookings/{id}` overwrote the serialized `start_time` with
  `created_at`, returning an incorrect booking time.
- Fix: Removed that overwrite and now rely on the shared booking serializer.

## 15. Refund tiers were wrong

- Files/lines: `app/routers/bookings.py:366-372`
- Bug: Cancellation refund logic treated exactly 48 hours as 50% instead of
  100%, and less than 24 hours as 50% instead of 0%.
- Fix: Implement the required thresholds directly:
  `>=48h -> 100`, `>=24h -> 50`, otherwise `0`.

## 16. Refund amount in response could differ from RefundLog

- Files/lines: `app/services/refunds.py:394-418`,
  `app/routers/bookings.py:506-523`
- Bug: The response and refund ledger calculated amounts independently, using
  different rounding behavior.
- Fix: Compute the refund once using integer math with half-cent round-up and
  use the exact value for both the `RefundLog` and cancel response.

## 17. Concurrent cancellation could create multiple refund logs

- Files/lines: `app/routers/bookings.py:486-523`,
  `app/services/refunds.py:403-418`
- Bug: Cancellation checked status, committed a refund log, then changed booking
  status. Concurrent cancels could both log refunds before either saw the
  cancelled status.
- Fix: The booking write lock now covers lookup, authorization, status check,
  refund-log staging, status update, and commit. Refund logging no longer
  commits independently.

## 18. Report and availability caches went stale

- Files/lines: `app/routers/bookings.py:422-423`,
  `app/routers/bookings.py:518-519`, `app/routers/rooms.py:120-137`
- Bug: Usage reports were not invalidated on booking creation or room creation,
  and availability was not invalidated on cancellation. Read endpoints could
  return stale data despite the rule requiring immediate consistency.
- Fix: Invalidate report cache after booking creation, cancellation, and room
  creation. Invalidate availability after booking creation and cancellation.

## 19. Room stats could drift or reset

- Files/lines: `app/routers/rooms.py:183-195`,
  `app/services/stats.py:487-510`
- Bug: Room stats were stored as an in-memory incremental cache. Restarting the
  app, cancelling old bookings, or concurrent updates could make stats disagree
  with the actual booking table.
- Fix: Compute confirmed booking count and revenue directly from the database on
  every stats request.

## 20. Admin export leaked cross-org data

- Files/lines: `app/services/export.py:291-335`,
  `app/routers/admin.py:260-268`
- Bug: `include_all=true&room_id=<foreign-room>` bypassed org scoping and could
  export another organization's bookings. Supplying a foreign `room_id` could
  also return 200 instead of behaving as nonexistent.
- Fix: Validate any supplied `room_id` belongs to the admin's organization before
  exporting, and use org-scoped queries for all export modes.

## 21. Notification lock order could deadlock

- Files/lines: `app/services/notifications.py:473-486`
- Bug: Booking creation acquired locks in email-then-audit order while
  cancellation acquired audit-then-email. Concurrent create/cancel flows could
  deadlock.
- Fix: Both paths now acquire locks in the same email-then-audit order.

## Validation performed

- `python -m pytest -q` passes.
- Local curl smoke test covered health, registration, login, room creation,
  booking creation, list/detail, availability, stats, usage report, export,
  cancellation, refresh-token reuse rejection, logout, and post-logout access
  rejection.
