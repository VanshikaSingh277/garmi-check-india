"""Release hardening (spec §10.3, Phase 7): CGNAT (many tokens from one IP are not blocked at the defaults), made-up
tokens put the IP back under a limit, and no secret-shaped strings in the files git tracks or would commit."""
import os
import re
import subprocess

from fastapi.testclient import TestClient

import main
from app import config, db, http, secure
from app.models import Household

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _homes_with_tokens(n: int) -> list[str]:
    tokens = [secure.new_token() for _ in range(n)]
    with db.session() as s:
        for t in tokens:
            s.add(Household(cell_lat=26.9, cell_lon=75.8, district="Jaipur", managed_by="self", consent_version="draft-1",
                            token_hash=secure.token_hash(t)))
    return tokens


def test_cgnat_many_tokens_from_one_ip_are_not_blocked_at_the_defaults():
    old = config.HOUSEHOLDS_ENABLED
    config.HOUSEHOLDS_ENABLED = True
    c = TestClient(http.Guard(main.api, "default-src 'self'", http.RateLimiter(config.RATE_STATELESS_PER_MIN)))
    try:
        tokens = _homes_with_tokens(40)
        # 40 homes behind one carrier IP, 10 requests each: 400 requests in a minute, above the 300/min IP limit
        codes = [c.get("/api/v1/households/me", headers={"Authorization": "Bearer " + t}).status_code for t in tokens for _ in range(10)]
        assert set(codes) == {200}
        # requests without a token from the same IP still share the IP limit
        stateless = [c.get("/api/health").status_code for _ in range(config.RATE_STATELESS_PER_MIN + 1)]
        assert stateless[-1] == 429 and set(stateless[:-1]) == {200}
    finally:
        config.HOUSEHOLDS_ENABLED = old


def test_made_up_tokens_put_the_ip_back_under_a_limit():
    old = config.HOUSEHOLDS_ENABLED
    config.HOUSEHOLDS_ENABLED = True
    http.BAD_TOKENS._hits.clear()
    c = TestClient(main.app)
    try:
        codes = [c.get("/api/v1/households/me", headers={"Authorization": "Bearer " + secure.new_token()}).status_code
                 for _ in range(config.RATE_BAD_TOKEN_PER_MIN + 1)]
        assert set(codes[:-1]) == {401} and codes[-1] == 429
        real = _homes_with_tokens(1)[0]                       # the IP is held back, valid tokens included, for a minute
        r = c.get("/api/v1/households/me", headers={"Authorization": "Bearer " + real})
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        r = c.get("/api/v1/workers/me", headers={"Authorization": "Bearer " + secure.new_token()})
        assert r.status_code == 429                          # worker routes share the same bad-token limit
    finally:
        http.BAD_TOKENS._hits.clear()
        config.HOUSEHOLDS_ENABLED = old


SECRET_SHAPES = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("API key", re.compile(r"sk-(ant-)?[A-Za-z0-9_\-]{32,}")),
    ("secret assigned in code", re.compile(r"(?i)(secret|pepper|password|passwd|api_key|private_key|enc_keys?|hmac_key|token)"
                                           r"[\"']?\s*[:=]\s*[\"']([A-Za-z0-9+/=_\-]{20,})[\"']")),
]
BINARY = re.compile(r"\.(png|jpe?g|gif|ico|webp|svg|ubj|bin|gz|zip|woff2?|ttf|pdf|xlsx|parquet|npy|pkl|jar|keystore|apk|aab)$", re.I)


def test_no_secret_shaped_strings_in_tracked_or_committable_files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split("\n")
    # .env-style files are never opened (project rule); their names are checked by .gitignore and CI instead
    files = [f for f in out if f and not BINARY.search(f) and not os.path.basename(f).startswith(".env")]
    assert len(files) > 100
    hits = []
    for f in files:
        path = os.path.join(ROOT, f)
        if not os.path.isfile(path) or os.path.getsize(path) > 3_000_000:
            continue
        try:
            text = open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        hits += [f"{f}:{n} ({name})" for n, line in enumerate(text.splitlines(), 1) for name, p in SECRET_SHAPES if p.search(line)]
    assert hits == []


def test_json_nested_too_deep_is_422_not_400_or_500():
    r = TestClient(main.app).post("/api/status/individual", content="[" * 5000 + "]" * 5000, headers={"content-type": "application/json"})
    assert r.status_code == 422 and r.json()["error"] == "invalid_input"
