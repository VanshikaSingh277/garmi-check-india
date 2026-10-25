# Phase 4 test cases

Format: ID | Title | Preconditions | Steps | Expected | Priority | Type.
Runner: `python tests/qa/p4_qa.py <server-log>` against a server started with **test** secrets, a throwaway state folder and `HOUSEHOLDS_ENABLED=true`. In production the switch stays off until the frontend prerequisite is done (spec §6.3).

| ID | Title | Preconditions | Steps | Expected | Priority | Type |
|---|---|---|---|---|---|---|
| P4-01 | Save a home | — | POST /api/v1/households (consent, place, home, summary, alerts) | 201 with `household_id` and a token shown once | High | Functional |
| P4-02 | No GPS, no token, no people stored | P4-01 | Read the database file | No exact coordinates, no raw token; only the 0.1° cell | High | Privacy |
| P4-03 | Read and edit | P4-01 | GET /me; PATCH /me with a new place and `ac: true` | Cell and district follow the new place; other answers kept | High | Functional |
| P4-04 | Export | P4-01 with an SMS target | GET /me/export | All stored data; phone shown masked (…NN); a consent event "exported" | High | Privacy |
| P4-05 | Rotate token | P4-01 | POST /me/token/rotate | Old token 401, new token 200 | High | Security |
| P4-06 | Delete in one step | P4-01 | DELETE /me | 204; home, push targets and notices gone; consent events kept | High | Privacy |
| P4-07 | Status with people from the phone | P4-01 | POST /me/status with one older person | Same body as the family result plus `per_person`, `calibration` | High | Functional |
| P4-08 | Outlook | P4-01 | POST /me/outlook `days: 7`; then `days: 8` | Up to 7 days with level, reasons, temperatures; 8 → 422 | Medium | Functional |
| P4-09 | Bad requests | — | Old consent version; `accepted: false`; a place outside India; an extra `gps` field; no token | 409, 422, 422, 422, 401 | High | Negative |
| P4-10 | New-home limit | — | 61 creates from one IP within an hour | The 61st gets 429 with Retry-After | Medium | Security |
| P4-11 | Browser push only to real push services | A token | POST /api/v1/push webpush with evil.example.com; then fcm.googleapis.com | 422, then 201 | High | Security |
| P4-12 | Web push key when not set up | No VAPID keys | GET /api/v1/vapid-public-key | 503 `not_configured` | Low | Functional |
| P4-13 | Tokens never in logs | Server log | Run P4-01..07; read the log | No token, no Authorization header value | High | Privacy |
| P4-14 | Push crypto and FCM | — | Automated: `tests/test_households.py` (RFC 8291 vector, VAPID JWT, FCM token request) | Pass | High | Security |
