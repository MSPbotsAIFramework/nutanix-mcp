# PRD-21347 · Code review

## Round 1 · 2026-11-05 · reviewed 2034950 (base 69c492f)

Verdict: approved
Status: frozen @ 2034950

### Scope

Full diff `origin/main...HEAD` (69c492f..2034950): first version of `MSPbotsAIFramework/nutanix-mcp`,
a greenfield repo (31 files, ~3000 lines). Reviewed against `docs/tickets/PRD-21347.md` (product
design, tech design, AC1-AC9) and `docs/tickets/PRD-21347.ac.json` (TC1-TC12).

### Independent verification run by the reviewer

The dev leg's gates were re-run from scratch on the reviewed commit, independently of the
self-test claims in the doc:

- `uv sync` (uv 0.13.7, Python 3.12.16) — resolved cleanly, same `mcp==1.30.0` pin reported by dev.
- `uv run ruff check .` — All checks passed.
- `uv run pytest -q` — **27 passed**, 0 failed (matches the `[DEV]` stub's claim exactly).
- `docker build --platform linux/amd64 .` — succeeds (this was flagged `not executed` in the
  dev leg's self-test because that sandbox had no usable Docker daemon; this one did).
- Ran the built image (`docker run -p 18099:8080 ...`): `GET /health` → `200 {"status":"ok"}`
  with no headers; `POST /mcp tools/list` with no credential headers → `401
  {"error":"missing_headers","missing":["X-Nutanix-Host","X-Nutanix-Username","X-Nutanix-Password"]}`.
  Container runs as non-root `app` user per the Dockerfile.
- Chinese-character scan (`grep -rnP '[\x{4e00}-\x{9fff}]' src tests README.md Dockerfile
  pyproject.toml .env.example`) — no output.
- `git log -p` secret scan — no hits beyond the test fixture placeholders
  `svc-account` / `svc-password` in `tests/conftest.py`.
- README "MSPbots Connector" section diffed byte-for-byte against
  `~/.claude/skills/vendor-mcp-development/reference/readme-connector-section.md` — identical,
  and positioned before "## Authentication headers" as required.

### AC / test-case coverage

All 9 ACs map to at least one `pass` test case in `PRD-21347.ac.json` (10 `pass`, 2 `blocked` for
"needs a real vendor account" per SOP, which is not a failure). Spot-checked the mapping against
the actual test code, not just the doc's claim:

- AC2/TC2 — `tests/test_middleware.py::test_missing_credential_headers_returns_401_and_names_them`
  and `test_partial_missing_headers_names_only_the_missing_ones` correctly assert no upstream call
  can be made (no respx mock installed, so one would raise) and that only the actually-missing
  headers are named.
- AC4/TC5-TC6 — `tests/test_tools.py::test_power_vm_returns_task_uuid` and
  `test_power_vm_unknown_uuid_returns_not_found_error` exercise the read-modify-write path in
  `client.py::NutanixClient.power_vm` and confirm a missing VM maps to `not_found`, not a 500.
- AC5/TC7-TC8 — 5xx/timeout → `upstream_error` (retryable), 401 → `unauthorized` (not retryable),
  matching `client.py::_status_to_error`.
- AC6/TC9 — `test_concurrent_requests_do_not_share_credentials_or_client` runs two concurrent
  requests through `CredentialMiddleware` with different hosts and asserts via `asyncio.gather`
  that neither ever observes the other's `ContextVar` value.
- AC7 — TLS verify defaults true, header `X-Nutanix-Verify-Ssl: false` turns it off
  (`credentials.py::_parse_verify_ssl`, `test_verify_ssl_header_parsing` covers both value sets);
  the real self-signed-certificate handshake itself is correctly left as TC10 (manual, blocked —
  a mock server trivially has a trusted certificate, as the doc explains).
- AC8/TC11 — `cap()` in `tools/_common.py` defaults to 50, caps at 200, floors at 1; tested
  including the `limit=0` edge case (treated as "not specified", not as "zero results").
- AC9/TC12 — `/health` bypasses `CredentialMiddleware` entirely (it is a sibling `Route`, not
  behind the `Mount` the middleware wraps) — confirmed both by the test and by the live container
  smoke test above.

### Findings

No must-fix.

1. [suggestion] `docs/tickets/PRD-21347.md:107` (tech design "Change list") names
   `src/nutanix_mcp/errors.py` as a new file that would hold the Nutanix-error-to-envelope
   mapping. That file was never created; the equivalent logic (`ApiError`, `_status_to_error`,
   `_error_detail`) lives in `client.py` instead, which is a reasonable place for it given there is
   only one upstream to map errors from. Tech design is the dev leg's own call to adapt as long as
   user-visible behavior does not change (`SKILL.md`), and it does not here — this is a
   file-layout deviation from the written plan, not a functional gap, and it was not called out in
   the "Deviations / open items" section of the Self-test doc alongside the other three documented
   deviations. Not a reason to send this back; noted for the record only.
2. [suggestion] `src/nutanix_mcp/tools/_common.py:36` — `cap(limit)` treats `limit=0` the same as
   "no limit given" (falls back to the default of 50) rather than as "zero results requested".
   This is deliberate and tested (`test_list_limit_defaults_to_50_and_caps_at_200` asserts
   `cap(0) == 50`), and no AC calls for `limit=0` to mean "return nothing", so this is not a
   must-fix — just worth a caller noticing if they ever pass `limit=0` expecting an empty page.

### Conclusion

Code matches the frozen product design and tech design; every AC has verifiable, re-run-by-the-reviewer
evidence; no scope creep, no reinvented wheels (the skeleton is the same shape already running in
`halopsa-mcp`), no secrets, no Chinese, no destructive-by-surprise behavior (`nutanix_power_vm` is
explicitly annotated destructive/non-idempotent and the tool description tells the calling agent to
confirm with the user first). Proceeding to merge into `main`, publish to INT (new-vendor
registration, since this vendor has never been registered before), and the connector wiki.
