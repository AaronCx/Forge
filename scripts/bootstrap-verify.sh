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

# Test steer see (uses CoreGraphics — works over SSH)
check "steer_see" steer see --output /tmp/steer-verify-see.png
SR_OK=false
[ -f /tmp/steer-verify-see.png ] && SR_OK=true
rm -f /tmp/steer-verify-see.png

if $SR_OK && [ -f "$(dirname "$0")/ocr-helper" ]; then
    check "steer_ocr" steer ocr
    # steer_find may not find text depending on what's on screen
    steer find "Finder" &>/dev/null && {
        echo "  ✅ steer_find"
        PASS=$((PASS + 1))
    } || {
        echo "  ⏭️  steer_find — text not on screen (normal)"
        SKIP=$((SKIP + 1))
    }
else
    skip "steer_ocr" "steer_see failed or ocr-helper not built"
    skip "steer_find" "requires steer_see + OCR"
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

# Hotkey/focus — try them directly, they may work or may not over SSH
check "steer_focus (Finder)" steer focus Finder
check "steer_hotkey (cmd+a)" steer hotkey "cmd+a"
check "steer_scroll (down 1)" steer scroll down 1

if command -v cliclick &>/dev/null; then
    check "steer_click (center)" steer click 500 500
    check "steer_type" steer type "test"
    check "steer_drag" steer drag 100 100 200 200
else
    skip "steer_click" "cliclick not installed"
    skip "steer_type" "cliclick not installed"
    skip "steer_drag" "cliclick not installed"
fi

if $SR_OK; then
    steer wait "Finder" --timeout 3 &>/dev/null && {
        echo "  ✅ steer_wait"
        PASS=$((PASS + 1))
    } || {
        echo "  ⏭️  steer_wait — timed out (normal if text not on screen)"
        SKIP=$((SKIP + 1))
    }
else
    skip "steer_wait" "needs screenshot"
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
