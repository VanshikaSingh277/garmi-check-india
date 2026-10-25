# Attack smoke results

Run 2026-10-25 10:51 against http://localhost:8000.

| Check | Result | Status / notes |
|---|---|---|
| wrong content type | PASS | 415 |
| no content type | PASS | 415 |
| 17 KB body | PASS | 413 |
| broken JSON | PASS | 422 |
| JSON that is a list | PASS | 422 |
| extra field | PASS | 422 |
| NaN latitude | PASS | 422 |
| huge number | PASS | 422 |
| hostile string in an enum | PASS | 422 |
| deep nesting | PASS | 422 |
| point outside India | PASS | 422 |
| lat as text | PASS | 422 |
| hostile search | PASS | 200 |
| SQL in a search | PASS | 200 |
| very long query string | PASS | 422 |
| traversal /../../etc/passwd | PASS | 404 (200 only as the site's index page) |
| traversal /%2e%2e/%2e%2e/etc/passwd | PASS | 404 (200 only as the site's index page) |
| traversal /..%5c..%5cwindows/win.ini | PASS | 404 (200 only as the site's index page) |
| traversal /static/..%2f..%2fmain.py | PASS | 404 (200 only as the site's index page) |
| traversal /.env | PASS | 404 (200 only as the site's index page) |
| traversal /.git/config | PASS | 404 (200 only as the site's index page) |
| docs off /docs | PASS | 404 |
| docs off /redoc | PASS | 404 |
| docs off /openapi.json | PASS | 404 |
| metrics without the job secret | PASS | 403 |
| metrics with a wrong secret | PASS | 403 |
| job without the secret | PASS | 403 |
| household route without a token | PASS | 401 |
| household route with a made-up token | PASS | 401 |
| worker route with a made-up token | PASS | 401 |
| token in the query string is ignored | PASS | 401 |
| unsigned WhatsApp webhook | PASS | 401 |
| bad signature | PASS | 401 |
| replayed old webhook | PASS | 401 |
| unsigned SMS status webhook | PASS | 401 |
| unknown Host header | PASS | 400 (400 when ALLOWED_HOSTS is set) |
| CORS from an unknown origin | PASS | 200 |
| CORS preflight from an unknown origin | PASS | 400 |
| X-Forwarded-For from an untrusted peer | PASS | 200 |
| TRACE method | PASS | 405 |
| flood without a token reaches 429 with Retry-After | PASS | first 429 after 275 requests |

**41 of 41 passed. Server errors (5xx): 0.**
