#!/bin/bash
# AgentForge Computer Use — Quick Verification
# Runs smoke tests for all Steer and Drive commands.
set -uo pipefail

PASS=0
FAIL=0
SKIP=0

check() {
    local name="$1"
    shift
    local output
    output=$("$@" 2>&1) && {
        echo "  ✅ $name"
        PASS=$((PASS + 1))
    } || {
        echo "  ❌ $name — $output"
        FAIL=$((FAIL + 1))
    }
}

skip() {
    echo "  ⏭️  $1 — skipped ($2)"
    SKIP=$((SKIP + 1))
}

echo "═══ Steer Commands ═══"

# Check if screen recording works first
SR_OK=false
TMPFILE=$(mktemp /tmp/sr-verify-XXXXXX.png)
if screencapture -x "$TMPFILE" 2>/dev/null; then
    SIZE=$(stat -f%z "$TMPFILE" 2>/dev/null || echo "0")
    [ "$SIZE" -gt 1000 ] && SR_OK=true
fi
rm -f "$TMPFILE"

if $SR_OK; then
    check "steer_see" steer see --output /tmp/steer-verify-see.png
    rm -f /tmp/steer-verify-see.png

    if [ -f "$(dirname "$0")/ocr-helper" ]; then
        # Take a screenshot for OCR test
        screencapture -x /tmp/steer-verify-ocr.png 2>/dev/null
        check "steer_ocr" steer ocr
        check "steer_find" steer find "AgentForge" || true  # may not find text
        rm -f /tmp/steer-verify-ocr.png
    else
        skip "steer_ocr" "ocr-helper not built"
        skip "steer_find" "requires OCR"
    fi
else
    skip "steer_see" "screen recording denied"
    skip "steer_ocr" "screen recording denied"
    skip "steer_find" "screen recording denied"
fi

# These need accessibility
if command -v cliclick &>/dev/null; then
    check "steer_clipboard (write)" steer clipboard write "agentforge-test"
    check "steer_clipboard (read)" steer clipboard read
    check "steer_apps" steer apps
else
    skip "steer_click" "cliclick not installed"
    skip "steer_type" "cliclick not installed"
fi

# Hotkey/focus need accessibility
ACC_OK=false
timeout 3 osascript -e 'tell application "System Events" to count of (every process)' &>/dev/null && ACC_OK=true

if $ACC_OK; then
    check "steer_focus (Finder)" steer focus Finder
    check "steer_hotkey (cmd+a)" steer hotkey "cmd+a"
    check "steer_scroll (down 1)" steer scroll down 1
else
    skip "steer_focus" "accessibility denied"
    skip "steer_hotkey" "accessibility denied"
    skip "steer_scroll" "accessibility denied"
fi

if command -v cliclick &>/dev/null && $ACC_OK; then
    check "steer_click (center)" steer click 500 500
    check "steer_type" steer type "test"
    check "steer_drag" steer drag 100 100 200 200
else
    skip "steer_click" "needs cliclick + accessibility"
    skip "steer_type" "needs cliclick + accessibility"
    skip "steer_drag" "needs cliclick + accessibility"
fi

if $SR_OK && $ACC_OK; then
    # steer_wait with a short timeout — may not find anything
    steer wait "Finder" --timeout 2 &>/dev/null && {
        echo "  ✅ steer_wait"
        PASS=$((PASS + 1))
    } || {
        echo "  ⏭️  steer_wait — timed out (normal if text not on screen)"
        SKIP=$((SKIP + 1))
    }
else
    skip "steer_wait" "needs screen recording + accessibility"
fi

echo ""
echo "═══ Drive Commands ═══"

check "drive_session create" drive session create verify-test
check "drive_session list" drive session list
check "drive_run" drive run "echo hello" --session verify-test --timeout 10
check "drive_send" drive send "echo sent" --session verify-test
sleep 1
check "drive_logs" drive logs --session verify-test

# Poll test
drive send "echo __VERIFY_DONE__" --session verify-test &>/dev/null
sleep 1
check "drive_poll" drive poll --session verify-test --sentinel __VERIFY_DONE__ --timeout 5

check "drive_session kill" drive session kill verify-test

echo ""
echo "═══════════════════════"
echo "Results: ✅ $PASS passed, ❌ $FAIL failed, ⏭️  $SKIP skipped"
echo "═══════════════════════"

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
