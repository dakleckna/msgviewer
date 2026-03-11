#!/bin/bash

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC}  $1"; }
info() { echo -e "${CYAN}  →${NC}  $1"; }
fail() { echo -e "${RED}  ✗  $1${NC}"; exit 1; }

GITHUB_USER="DEIN-USERNAME"
GITHUB_REPO="msg-viewer"
BASE_URL="https://raw.githubusercontent.com/${GITHUB_USER}/${GITHUB_REPO}/main"

APP_DIR="/Applications/MSGViewer.app"
VENV="$HOME/msgviewer-env"
RESOURCES="$APP_DIR/Contents/Resources"

clear
echo ""
echo -e "${BOLD}  MSG Viewer — Installer${NC}"
echo -e "  ──────────────────────────────────────"
echo ""

# ── 1. macOS ──────────────────────────────────────────────────
[[ "$(uname -s)" == "Darwin" ]] || fail "This installer only runs on macOS."
ok "macOS $(sw_vers -productVersion)"

# ── 2. Homebrew ───────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    info "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for Apple Silicon
    [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
fi
ok "Homebrew $(brew --version | head -1)"

# ── 3. Python 3.12 ────────────────────────────────────────────
info "Installing Python 3.12 + tkinter..."
brew install python@3.12 python-tk@3.12 --quiet
PYTHON="/opt/homebrew/bin/python3.12"
# Fallback for Intel Macs
[[ ! -f "$PYTHON" ]] && PYTHON="/usr/local/bin/python3.12"
[[ ! -f "$PYTHON" ]] && fail "python3.12 not found after install — please run: brew install python@3.12"
ok "Python: $("$PYTHON" --version)"

# ── 4. tkinter check ──────────────────────────────────────────
"$PYTHON" -c "import tkinter" 2>/dev/null || fail "tkinter still missing — try: brew reinstall python-tk@3.12"
ok "tkinter available"

# ── 5. Virtual environment ────────────────────────────────────
info "Setting up virtual environment..."
[[ -d "$VENV" ]] && rm -rf "$VENV"
"$PYTHON" -m venv "$VENV"
ok "venv: $VENV"

# ── 6. Python dependencies ────────────────────────────────────
info "Installing extract-msg and Pillow..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet extract-msg Pillow
ok "extract-msg $(${VENV}/bin/pip show extract-msg | grep Version | cut -d' ' -f2)"
ok "Pillow $(${VENV}/bin/pip show Pillow | grep Version | cut -d' ' -f2)"

# ── 7. Download MSGViewer.py ──────────────────────────────────
info "Downloading MSGViewer.py..."
TMP=$(mktemp /tmp/MSGViewer_XXXX.py)
curl -fsSL "${BASE_URL}/MSGViewer.py" -o "$TMP" || fail "Download failed — check your internet connection."
ok "Downloaded MSGViewer.py"

# ── 8. Build .app bundle ──────────────────────────────────────
info "Building /Applications/MSGViewer.app..."
[[ -d "$APP_DIR" ]] && rm -rf "$APP_DIR"

mkdir -p "$APP_DIR/Contents/MacOS" "$RESOURCES"
cp "$TMP" "$RESOURCES/MSGViewer.py"
rm "$TMP"

# Launcher — points to venv python
cat > "$APP_DIR/Contents/MacOS/MSGViewer" << LAUNCHER
#!/bin/bash
exec "${VENV}/bin/python3" "${RESOURCES}/MSGViewer.py" "\$@"
LAUNCHER
chmod +x "$APP_DIR/Contents/MacOS/MSGViewer"

# Info.plist — registers .msg file type
cat > "$APP_DIR/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>              <string>MSGViewer</string>
    <key>CFBundleDisplayName</key>       <string>MSG Viewer</string>
    <key>CFBundleIdentifier</key>        <string>de.local.msgviewer</string>
    <key>CFBundleVersion</key>           <string>1.0</string>
    <key>CFBundlePackageType</key>       <string>APPL</string>
    <key>CFBundleExecutable</key>        <string>MSGViewer</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeExtensions</key>
            <array><string>msg</string></array>
            <key>CFBundleTypeName</key>      <string>Outlook Message</string>
            <key>CFBundleTypeRole</key>      <string>Viewer</string>
            <key>LSHandlerRank</key>         <string>Owner</string>
            <key>LSItemContentTypes</key>
            <array>
                <string>com.microsoft.outlook.msg</string>
                <string>public.data</string>
            </array>
        </dict>
    </array>
    <key>UTImportedTypeDeclarations</key>
    <array>
        <dict>
            <key>UTTypeIdentifier</key>      <string>com.microsoft.outlook.msg</string>
            <key>UTTypeDescription</key>     <string>Microsoft Outlook Message</string>
            <key>UTTypeConformsTo</key>
            <array><string>public.data</string></array>
            <key>UTTypeTagSpecification</key>
            <dict>
                <key>public.filename-extension</key>
                <array><string>msg</string></array>
            </dict>
        </dict>
    </array>
</dict>
</plist>
PLIST

ok "App built"

# ── 9. Register .msg file association ─────────────────────────
LSREG="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"
[[ -f "$LSREG" ]] && "$LSREG" -f "$APP_DIR" 2>/dev/null && ok ".msg file type registered"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "  ──────────────────────────────────────"
echo -e "  ${GREEN}${BOLD}✓  Installation complete!${NC}"
echo ""
echo -e "  Double-click any ${BOLD}.msg${NC} file to open it."
echo ""
echo -e "  If double-click opens another app:"
echo -e "  Right-click .msg → Open With → Other → MSGViewer"
echo ""
echo -e "  Uninstall:"
echo -e "  rm -rf /Applications/MSGViewer.app ~/msgviewer-env ~/.msgviewer_prefs"
echo ""
