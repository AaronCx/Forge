#!/bin/bash
# Forge macOS Computer Use Bootstrap
# Run this once on a new Mac to set up computer use capabilities.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "🔧 Forge Computer Use Bootstrap"
echo "======================================"
echo ""

# ─── System Info ─────────────────────────────────────────────────────────────
echo "📋 System Info"
sw_vers
echo "Architecture: $(uname -m)"
echo "User: $(whoami)"
echo ""

# ─── Homebrew ────────────────────────────────────────────────────────────────
echo "📦 Checking Homebrew..."
if ! command -v brew &>/dev/null; then
    echo "  Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
fi
echo "  ✅ Homebrew $(brew --version | head -1)"

# ─── tmux ────────────────────────────────────────────────────────────────────
echo "📦 Checking tmux..."
if ! command -v tmux &>/dev/null; then
    echo "  Installing tmux..."
    brew install tmux
fi
echo "  ✅ $(tmux -V)"

# ─── ffmpeg ──────────────────────────────────────────────────────────────────
echo "📦 Checking ffmpeg..."
if ! command -v ffmpeg &>/dev/null; then
    echo "  Installing ffmpeg..."
    brew install ffmpeg
fi
echo "  ✅ ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"

# ─── cliclick ────────────────────────────────────────────────────────────────
echo "📦 Checking cliclick..."
if ! command -v cliclick &>/dev/null; then
    echo "  Installing cliclick..."
    brew install cliclick
fi
echo "  ✅ cliclick installed"

# ─── OCR Helper (Swift Vision framework) ─────────────────────────────────────
echo "📦 Building OCR helper..."
if [ ! -f "$SCRIPT_DIR/ocr-helper" ]; then
    if [ -f "$SCRIPT_DIR/ocr-helper.swift" ]; then
        swiftc -O -o "$SCRIPT_DIR/ocr-helper" "$SCRIPT_DIR/ocr-helper.swift"
        echo "  ✅ OCR helper compiled"
    else
        echo "  ⚠️  ocr-helper.swift not found"
    fi
else
    echo "  ✅ OCR helper already built"
fi

# ─── Steer & Drive CLIs ─────────────────────────────────────────────────────
echo "📦 Setting up Steer & Drive CLIs..."
chmod +x "$SCRIPT_DIR/steer" "$SCRIPT_DIR/drive" 2>/dev/null || true

# Add to PATH via ~/bin symlinks
mkdir -p "$HOME/bin"
ln -sf "$SCRIPT_DIR/steer" "$HOME/bin/steer"
ln -sf "$SCRIPT_DIR/drive" "$HOME/bin/drive"

if command -v steer &>/dev/null; then
    echo "  ✅ $(steer --version)"
else
    echo "  ⚠️  steer not in PATH — add ~/bin to your PATH"
fi
if command -v drive &>/dev/null; then
    echo "  ✅ $(drive --version)"
else
    echo "  ⚠️  drive not in PATH — add ~/bin to your PATH"
fi

# ─── Permissions Check ───────────────────────────────────────────────────────
echo ""
echo "🔐 Checking Permissions..."

# Screen Recording
SR_OK=false
TMPFILE=$(mktemp /tmp/sr-test-XXXXXX.png)
if screencapture -x "$TMPFILE" 2>/dev/null; then
    SIZE=$(stat -f%z "$TMPFILE" 2>/dev/null || echo "0")
    [ "$SIZE" -gt 1000 ] && SR_OK=true
fi
rm -f "$TMPFILE"

if $SR_OK; then
    echo "  ✅ Screen Recording: Granted"
else
    echo "  ❌ Screen Recording: NOT GRANTED"
    echo "     → Open System Settings > Privacy & Security > Screen Recording"
    echo "     → Enable for Terminal / your SSH client"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture" 2>/dev/null || true
fi

# Accessibility
ACC_OK=false
if timeout 3 osascript -e 'tell application "System Events" to count of (every process)' &>/dev/null; then
    ACC_OK=true
fi

if $ACC_OK; then
    echo "  ✅ Accessibility: Granted"
else
    echo "  ❌ Accessibility: NOT GRANTED (or timed out on headless Mac)"
    echo "     → Open System Settings > Privacy & Security > Accessibility"
    echo "     → Enable for Terminal / your SSH client / cliclick"
    open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility" 2>/dev/null || true
fi

# ─── Smoke Tests ─────────────────────────────────────────────────────────────
echo ""
echo "🧪 Running smoke tests..."
"$SCRIPT_DIR/bootstrap-verify.sh"

echo ""
echo "✅ Bootstrap complete!"
