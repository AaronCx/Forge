# Forge — QA Playbook Summary

Single-page summary of `forge-qa-playbook.pdf` execution against a fresh local
SQLite + Ollama stack on 2026-04-28. Full evidence at `qa-evidence/findings.md`.

## Scope of run

- **Live target:** `localhost:8000` (FastAPI/SQLite) + `localhost:3000` (Next.js) + `localhost:11434` (Ollama llama3.2:3b)
- **Test user:** `qa@forge.test` (created via `forge auth signup`)
- **Sections executed end-to-end:** 1, 2.1, 4.1, 5.1, 6.1, 11.1, 11.2, 11.3, 18.1, 18.2, 17 (covered by existing Demo Parity Smoke Test in `e2e/demo-parity.spec.ts`)
- **Sections blocked by environmental constraints (see findings #14–#23):** 2.2–2.4, 3, 4.2–4.3, 6.2–6.4, 7.2–7.3, 8, 9, 10, 11.3 (playback), 13, 14, 15, 16

## Top 5 critical findings

| # | Severity | What | Status |
|---|---|---|---|
| 1 | Critical | `forge auth login` wrote token to `[defaults]` instead of `[api].key`; every authenticated CLI call ran without auth | **Fixed** in PR #59 |
| 6 | Critical | `/api/dashboard/metrics` 500'd on SQLite (`ambiguous column name: created_at` from joined query) | **Fixed** in PR #59 |
| 7 | Critical | `POST /api/agents` 500'd after row was committed (DB defaults missing from response → phantom writes) | **Fixed** in PR #59 |
| 5 | High | Local-mode JWTs had no `exp` claim → tokens never expired | **Fixed** in PR #59 |
| 2 | High | `forge auth whoami` called `/api/stats` instead of `/api/auth/me` → always printed "User: unknown" | **Fixed** in PR #59 |

## Other findings

| # | Severity | Section | Summary |
|---|---|---|---|
| 3 | Pass (doc gap) | 1.1/1.2/1.4 | Web and CLI sessions are independent stores — works as designed but undocumented; recommend adding `docs/auth-model.md` |
| 4 | Pass | 1.3 | JWT exp parity (after #5 fix) |
| 8 | Pass | 2.1 | Cross-surface count parity verified for the zero-state baseline |
| 9 | Medium | 4.1 | `forge config set-default-model` and `forge config show` use mismatched TOML keys (`default_model` vs `model`) |
| 10 | Medium | 5.1 | `/api/providers.default_model` reports `gpt-4o-mini` even when OpenAI isn't configured |
| 11 | Pass | 6.1 | Agent CRUD via CLI is visible at the same id on `/api/agents` |
| 12 | Pass | 11 | `/api/mcp`, `/api/targets`, `/api/recordings` all return 200 with consistent structure |
| 13 | Medium | 18.1 | Web dashboard silently renders zeros when backend is unreachable instead of a "backend unreachable" banner |

## Pass rate

- **Critical findings shipped:** 3 (all fixed)
- **High findings:** 2 (both fixed)
- **Medium findings filed:** 4 (#9, #10, #13, plus the auth-model doc gap from #3) — tracked, not blocking deploy
- **Pass entries:** 6 (across §1.1–1.4, §2.1, §6.1, §11)
- **Blocked sections:** 10 (LLM-quality / multi-machine / interactive bootstrap dependencies — documented for the next QA pass when those constraints lift)

## Deploy-readiness call

The five Critical/High findings shipped in PR #59 unblock every authenticated
CLI command and the `/api/dashboard/metrics` endpoint that the unified web
dashboard depends on. The Medium findings are real-but-non-blocking UX
inconsistencies that should be filed as tracking issues but do not need to
ship in the same wave.

**Recommendation: ship.** Re-run §2.2–2.4, §3, §6.2–6.4, §7.2–7.3, §8 in a
follow-up session with either OpenAI keys (reliable tool-use) or Ollama
running a function-calling-grade model (qwen2.5:7b-instruct or larger). The
parity smoke test in CI (`e2e/demo-parity.spec.ts`) already protects the
demo-side regressions; adding a similar smoke test against a live stack with
seeded data is a worthwhile follow-up.

## Regression tests added

- `backend/tests/test_sqlite_qa_fixes.py` — covers Finding #6 (join + WHERE on shared column) and #7 (insert response includes DB defaults)
- `backend/tests/test_auth_api_jwt.py` — covers Finding #5 (`_build_jwt_payload` includes `iat` + `exp`)

Three new pytest entries; full backend suite (531 tests + 3 new) green.

## Files

- `qa-evidence/findings.md` — full per-finding entries with repro / root cause / suggested fix / evidence links
- `qa-evidence/finding-01-config.toml` — captured config file showing the misplaced token
- `qa-evidence/finding-02-whoami.txt` — pre-fix CLI output
- `qa-evidence/finding-05-jwt-payload.json` — decoded JWT showing missing exp
- `qa-evidence/finding-06-trace.txt` — full traceback for the SQLite ambiguous-column 500
- `qa-evidence/finding-07-trace.txt` — full traceback for the AgentResponse validation 500
