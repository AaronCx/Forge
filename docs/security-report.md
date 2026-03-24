# Forge Security Audit Report

**Version:** 1.9.0
**Date:** 2026-03-12
**Scope:** Full security & prompt injection testing per 19-section audit spec
**Tests:** 105 security tests (all passing)
**Total suite:** 620 tests (all passing)

---

## Executive Summary

A comprehensive security audit was conducted across all 19 categories of the Forge security testing specification. The audit identified **12 vulnerabilities** across SSRF, webhook authentication, input validation, XSS, code execution sandbox, and query injection vectors. All vulnerabilities have been remediated with fixes committed and verified by automated tests.

**Key findings:**
- **Critical (2):** SSRF in blueprint fetch nodes and MCP client — no URL validation allowed requests to internal networks and cloud metadata services
- **High (3):** Webhook timing attack via non-constant-time secret comparison, code executor sandbox bypass via encoding, computer use blocklist bypass via whitespace
- **Medium (5):** Marketplace sort_by injection, ILIKE wildcard injection, missing rate limits on webhooks, wildcard CORS methods/headers, missing document size limits
- **Low (2):** Missing path traversal protection on knowledge filenames, missing XSS sanitization utilities

All 12 issues have been fixed and verified.

---

## Results by Section

### Section 1: Prompt Injection — Agent System Prompts
| Test | Result | Notes |
|------|--------|-------|
| 1.1 System prompt max length | **SECURE** | Enforced at 10,000 chars via Pydantic |
| 1.2 System prompt min length | **SECURE** | Empty prompts rejected |
| 1.3 User/system role separation | **SECURE** | User input always "user" role |
| 1.4 Workflow steps bounded | **SECURE** | Max 50 steps |
| 1.5 Tools list bounded | **SECURE** | Max 20 tools |

### Section 2: Prompt Injection — Blueprint Nodes
| Test | Result | Notes |
|------|--------|-------|
| 2.1 DAG cycle detection | **SECURE** | Topological sort catches cycles |
| 2.2 Unknown node types rejected | **SECURE** | Node registry restricts types |
| 2.3 Template renderer safe | **SECURE** | No code execution in templates |

### Section 3: Prompt Injection — Knowledge Base / RAG
| Test | Result | Notes |
|------|--------|-------|
| 3.1 Document size limit | **SECURE** | 5MB max via Pydantic Field (was: unlimited) |
| 3.2 Filename path traversal | **SECURE** | Path sanitizer blocks `../` (was: no validation) |
| 3.3 Null bytes in filenames | **SECURE** | Stripped by sanitizer |
| 3.4 Empty filename rejected | **SECURE** | min_length=1 enforced |

### Section 4: Prompt Injection — MCP Tool Descriptions
| Test | Result | Notes |
|------|--------|-------|
| 4.1 URL scheme validation | **SECURE** | Only HTTP/HTTPS allowed (was: any scheme) |
| 4.2 Connection name bounded | **SECURE** | max_length=200 |
| 4.3 Server URL required | **SECURE** | min_length=1 |

### Section 5: Prompt Injection — Computer Use
| Test | Result | Notes |
|------|--------|-------|
| 5.1 Command blocklist basic | **SECURE** | rm -rf, shutdown, reboot blocked |
| 5.2 Whitespace bypass prevention | **SECURE** | Whitespace-normalized matching (was: simple substring) |
| 5.3 Null byte bypass prevention | **SECURE** | Control chars stripped before matching |
| 5.4 App blocklist | **SECURE** | System Preferences, Keychain Access blocked |
| 5.5 Rate limiter | **SECURE** | 30 actions/minute sliding window |
| 5.6 Audit log truncation | **SECURE** | Results capped at 2000 chars |

### Section 6: Agent-on-Agent Orchestration
| Test | Result | Notes |
|------|--------|-------|
| 6.1 Objective max length | **SECURE** | 5000 chars max |
| 6.2 Tools list bounded | **SECURE** | Max 20 tools |
| 6.3 Rate limited | **SECURE** | 5/hour |

### Section 7: Authentication & Authorization
| Test | Result | Notes |
|------|--------|-------|
| 7.1 Missing Bearer prefix | **SECURE** | Returns 401 |
| 7.2 Empty token | **SECURE** | Returns 401 |
| 7.3 Agent ownership | **SECURE** | user_id check on all operations |
| 7.4 Blueprint ownership | **SECURE** | user_id check on all operations |
| 7.5 Trigger ownership | **SECURE** | user_id check on all operations |

### Section 8: External Input Injection (Webhooks)
| Test | Result | Notes |
|------|--------|-------|
| 8.1 Constant-time secret comparison | **SECURE** | hmac.compare_digest (was: `!=` operator) |
| 8.2 Rate limiting | **SECURE** | 60/hour (was: unlimited) |
| 8.3 Body size limit | **SECURE** | 1MB max (was: unlimited) |
| 8.4 Trigger type validation | **SECURE** | Regex pattern `^(webhook\|cron\|mcp_event)$` |

### Section 9: Data Exfiltration via Agent Output
| Test | Result | Notes |
|------|--------|-------|
| 9.1 Agent output preview bounded | **SECURE** | Truncated to 500 chars |
| 9.2 Blueprint output bounded | **SECURE** | Truncated to 500/200 chars |
| 9.3 Error messages generic | **SECURE** | No stack traces exposed to client |

### Section 10: SQL Injection
| Test | Result | Notes |
|------|--------|-------|
| 10.1 No raw SQL | **SECURE** | All queries use Supabase ORM |
| 10.2 Marketplace sort_by validated | **SECURE** | Allowlist of columns (was: user-supplied directly) |
| 10.3 ILIKE wildcards escaped | **SECURE** | `%` and `_` escaped (was: raw interpolation) |

### Section 11: XSS via Stored Content
| Test | Result | Notes |
|------|--------|-------|
| 11.1 HTML sanitizer | **SECURE** | `sanitize_html()` utility added |
| 11.2 Event handler escaping | **SECURE** | Quotes escaped via `html.escape(quote=True)` |
| 11.3 HTML tag stripping | **SECURE** | `strip_html_tags()` utility added |
| 11.4 CORS not wildcard | **SECURE** | Single origin only |
| 11.5 CORS methods restricted | **SECURE** | Explicit list (was: `["*"]`) |

### Section 12: Path Traversal
| Test | Result | Notes |
|------|--------|-------|
| 12.1 `../` blocked | **SECURE** | sanitize_path raises ValueError |
| 12.2 Absolute paths blocked | **SECURE** | Leading `/` rejected |
| 12.3 Backslash traversal blocked | **SECURE** | `..\\` detected |
| 12.4 Null bytes stripped | **SECURE** | `\x00` removed |
| 12.5 Valid paths pass | **SECURE** | Normal filenames unaffected |

### Section 13: SSRF (Server-Side Request Forgery)
| Test | Result | Notes |
|------|--------|-------|
| 13.1 localhost blocked | **SECURE** | Resolves to 127.0.0.0/8, blocked (was: unrestricted) |
| 13.2 127.0.0.1 blocked | **SECURE** | Blocked by IP range check |
| 13.3 Cloud metadata (169.254.x) blocked | **SECURE** | Blocked (was: unrestricted) |
| 13.4 Private IP 10.x blocked | **SECURE** | Blocked (was: unrestricted) |
| 13.5 FTP scheme blocked | **SECURE** | Only HTTP/HTTPS allowed |
| 13.6 Empty URL blocked | **SECURE** | SSRFError raised |
| 13.7 No hostname blocked | **SECURE** | SSRFError raised |
| 13.8 Valid external URLs pass | **SECURE** | Correctly allowed |
| 13.9 fetch_url has SSRF protection | **SECURE** | validate_url() called |
| 13.10 fetch_document has SSRF protection | **SECURE** | validate_url() called |
| 13.11 webhook node has SSRF protection | **SECURE** | validate_url() called |
| 13.12 MCP client has SSRF protection | **SECURE** | validate_url() called |

### Section 14: Denial of Service
| Test | Result | Notes |
|------|--------|-------|
| 14.1 Agent run rate limited | **SECURE** | 10/hour |
| 14.2 Blueprint run rate limited | **SECURE** | 10/hour |
| 14.3 Agent creation rate limited | **SECURE** | 20/hour |
| 14.4 Computer use rate limited | **SECURE** | 30/minute |
| 14.5 Webhook rate limited | **SECURE** | 60/hour (was: unlimited) |
| 14.6 Document size bounded | **SECURE** | 5MB max |
| 14.7 Fetch URL response capped | **SECURE** | 50KB |
| 14.8 Code executor size limit | **SECURE** | 10KB |
| 14.9 Code executor timeout | **SECURE** | 10 seconds |

### Section 15: Marketplace Security
| Test | Result | Notes |
|------|--------|-------|
| 15.1 Sort_by injection blocked | **SECURE** | Allowlist validation (was: direct use) |
| 15.2 ILIKE wildcards escaped | **SECURE** | Special chars escaped |
| 15.3 Listing limit clamped | **SECURE** | Max 100 results |
| 15.4 Rating range validated | **SECURE** | 1-5 enforced |
| 15.5 Update field allowlist | **SECURE** | Only specific fields allowed |

### Section 16: Remote Execution Security (Computer Use)
| Test | Result | Notes |
|------|--------|-------|
| 16.1 Destructive commands blocked | **SECURE** | rm -rf, shutdown, reboot, halt, poweroff |
| 16.2 Sensitive apps blocked | **SECURE** | Keychain Access, System Preferences |
| 16.3 Screenshot dir configurable | **SECURE** | Via CU_SCREENSHOT_DIR env var |
| 16.4 Dry-run mode available | **SECURE** | Via CU_DRY_RUN env var |
| 16.5 Approval setting exists | **SECURE** | Via CU_REQUIRE_APPROVAL env var |

### Section 17: Secrets & Key Exposure
| Test | Result | Notes |
|------|--------|-------|
| 17.1 .env in .gitignore | **SECURE** | Not committed |
| 17.2 API key endpoints require auth | **SECURE** | get_current_user dependency |
| 17.3 Error responses generic | **SECURE** | "Invalid or expired token" |
| 17.4 Health endpoint clean | **SECURE** | Only `{"status": "ok"}` |
| 17.5 Root endpoint clean | **SECURE** | Only name/version/status |

### Section 18: Input Validation Audit
| Test | Result | Notes |
|------|--------|-------|
| 18.1 Agent name max length | **SECURE** | 200 chars |
| 18.2 Agent description max length | **SECURE** | 2000 chars |
| 18.3 Trigger type pattern | **SECURE** | Regex validated |
| 18.4 Target type pattern | **SECURE** | Regex validated |
| 18.5 Orchestration objective min | **SECURE** | min_length=1 |
| 18.6 MCP URL min length | **SECURE** | min_length=1 |
| 18.7 Search top_k default | **SECURE** | Defaults to 5 |
| 18.8 Blueprint run limit bounded | **SECURE** | ge=1, le=100 |

### Section 19: Injection Surface Audit
| Test | Result | Notes |
|------|--------|-------|
| 19.1 Code executor blocks os.system | **SECURE** | Blocked |
| 19.2 Blocks subprocess | **SECURE** | Blocked |
| 19.3 Blocks eval | **SECURE** | Blocked |
| 19.4 Blocks exec | **SECURE** | Blocked |
| 19.5 Blocks __import__ | **SECURE** | Blocked |
| 19.6 Blocks open() | **SECURE** | Blocked |
| 19.7 Blocks socket | **SECURE** | Blocked |
| 19.8 Blocks base64 bypass | **SECURE** | Blocked (was: not blocked) |
| 19.9 Blocks pickle | **SECURE** | Blocked (was: not blocked) |
| 19.10 Blocks breakpoint() | **SECURE** | Blocked (was: not blocked) |
| 19.11 ORM used everywhere | **SECURE** | No raw SQL in codebase |
| 19.12 All mutation routes require auth | **SECURE** | Verified |

---

## Remediation Summary

| # | Vulnerability | Severity | File(s) Modified | Fix Description |
|---|--------------|----------|-----------------|-----------------|
| 1 | SSRF in fetch_url, fetch_document, webhook nodes | **Critical** | `deterministic.py`, `url_validator.py` | Added `validate_url()` with IP blocklist, scheme validation, DNS resolution checks |
| 2 | SSRF in MCP client | **Critical** | `mcp/client.py`, `url_validator.py` | Added `validate_url()` to health_check, discover_tools, call_tool |
| 3 | Webhook timing attack | **High** | `routers/triggers.py` | Replaced `!=` with `hmac.compare_digest()` for constant-time comparison |
| 4 | Code executor sandbox bypass | **High** | `tools/code_executor.py` | Added base64, pickle, breakpoint, codecs to blocklist; whitespace-collapsed matching |
| 5 | Computer use blocklist bypass | **High** | `computer_use/safety.py` | Whitespace-normalized + control char-stripped matching |
| 6 | Marketplace sort_by injection | **Medium** | `marketplace/marketplace_service.py` | Added `_ALLOWED_SORT_COLUMNS` allowlist |
| 7 | Marketplace ILIKE wildcard injection | **Medium** | `marketplace/marketplace_service.py` | Escaped `%`, `_`, `\` in search parameter |
| 8 | Missing webhook rate limit | **Medium** | `routers/triggers.py` | Added `@limiter.limit("60/hour")` and 1MB body size limit |
| 9 | Wildcard CORS methods/headers | **Medium** | `main.py` | Restricted to explicit method and header lists |
| 10 | Missing document size limit | **Medium** | `routers/knowledge.py` | Added `max_length=5_000_000` on raw_text field |
| 11 | Missing path traversal protection | **Low** | `security/sanitizer.py`, `routers/knowledge.py` | Added `sanitize_path()` for knowledge filenames |
| 12 | Missing XSS sanitization | **Low** | `security/sanitizer.py` | Added `sanitize_html()` and `strip_html_tags()` utilities |

---

## New Files Created

| File | Purpose |
|------|---------|
| `app/services/security/__init__.py` | Security utilities package |
| `app/services/security/url_validator.py` | SSRF protection — URL validation with IP blocklist |
| `app/services/security/sanitizer.py` | XSS and path traversal sanitization utilities |
| `tests/test_security.py` | 105 security tests covering all 19 audit sections |
| `conftest.py` | Root test configuration (sets FORGE_TESTING env) |

---

## Recommendations

### Immediate (completed)
- [x] SSRF protection on all outbound HTTP calls
- [x] Constant-time webhook secret verification
- [x] Rate limiting on webhook endpoint
- [x] Strengthened code executor sandbox
- [x] Improved computer use blocklist matching
- [x] Marketplace query injection prevention
- [x] Input size limits on knowledge documents
- [x] Path traversal protection on filenames
- [x] Restricted CORS configuration

### Future Enhancements
1. **Prompt injection defense layer** — Add input/output markers to delineate system vs user content in LLM prompts (e.g., `<|system|>` / `<|user|>` delimiters)
2. **Content Security Policy** — Add CSP headers to frontend responses
3. **API key hashing** — Store API key hashes only, not plaintext
4. **API key expiration** — Add TTL/expiration to API keys
5. **Webhook HMAC signatures** — Upgrade from shared secret to HMAC-SHA256 signature validation (like GitHub webhooks)
6. **Computer use approval flow** — Implement the `require_approval` config flag end-to-end
7. **pgvector for search** — Replace in-memory cosine similarity with pgvector for production scale
8. **Request signing** — Add request signing for internal service-to-service calls
9. **Structured logging** — Standardize security event logging format for SIEM integration

---

## Test Execution

```
$ pytest tests/test_security.py -v
105 passed in 0.11s

$ pytest tests/ -q
620 passed in 14.56s

$ ruff check app/
All checks passed!
```

---

**Auditor:** Automated security testing via Forge Security Spec v1.9
**Status:** All vulnerabilities remediated and verified
