#!/usr/bin/env bash
# Build "EQL Combat Feed.app" (and a .dmg) natively on macOS with PyInstaller.
#
#   packaging/macos/build.sh            # app + dmg in dist/
#   packaging/macos/build.sh --no-dmg   # app only
#
# Requires uv on PATH and Xcode Command Line Tools (for iconutil/codesign).
# The bundle is ad-hoc signed: Gatekeeper will ask for a right-click > Open on
# first launch until a Developer ID signature exists.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"
MAKE_DMG=1
[ "${1:-}" = "--no-dmg" ] && MAKE_DMG=0

VERSION="$(uv run --extra build python -c 'import eql_combat_feed; print(eql_combat_feed.__version__)')"
[ -n "$VERSION" ] || { echo "Unable to determine application version." >&2; exit 1; }
echo "Building EQL Combat Feed $VERSION ($(uname -m))"

APP_NAME="EQL Combat Feed"
BUILD_DIR="$PROJECT_ROOT/build/macos"
DIST_DIR="$PROJECT_ROOT/dist"
APP="$DIST_DIR/$APP_NAME.app"
rm -rf "$BUILD_DIR" "$APP" "$DIST_DIR/$APP_NAME"
mkdir -p "$BUILD_DIR"

# Derive the .icns from the shared .ico so both platforms ship the same artwork.
ICONSET="$BUILD_DIR/eql-combat-feed.iconset"
mkdir -p "$ICONSET"
uv run --extra build python - "$PROJECT_ROOT/assets/icons/eql-combat-feed.ico" "$ICONSET" <<'PY'
import sys
from pathlib import Path
from PIL import Image

source, iconset = Path(sys.argv[1]), Path(sys.argv[2])
with Image.open(source) as ico:
    # Pick the largest frame the .ico carries and resample down from it.
    sizes = sorted(ico.info.get("sizes", {ico.size}))
    ico.size = sizes[-1]
    ico.load()
    base = ico.convert("RGBA")
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        pixels = size * scale
        name = f"icon_{size}x{size}" + ("@2x" if scale == 2 else "") + ".png"
        base.resize((pixels, pixels), Image.LANCZOS).save(iconset / name)
PY
ICNS="$BUILD_DIR/eql-combat-feed.icns"
iconutil -c icns "$ICONSET" -o "$ICNS"

uv run --extra build pyinstaller \
    --noconfirm \
    --clean \
    --windowed \
    --name "$APP_NAME" \
    --icon "$ICNS" \
    --osx-bundle-identifier "zenoran.eql-combat-feed" \
    --distpath "$DIST_DIR" \
    --workpath "$BUILD_DIR/pyinstaller" \
    --specpath "$BUILD_DIR" \
    "$PROJECT_ROOT/packaging/macos/entrypoint.py"

[ -d "$APP" ] || { echo "PyInstaller did not produce $APP" >&2; exit 1; }
PLIST="$APP/Contents/Info.plist"
plist_set() {  # key type value — Set if present, Add otherwise
    /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PLIST" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PLIST"
}
plist_set CFBundleShortVersionString string "$VERSION"
plist_set CFBundleVersion string "$VERSION"
plist_set NSHighResolutionCapable bool true
# Menu-bar (accessory) app: required for the overlays to enter the game's
# full-screen Space. The tray icon and control window are the UI entry points.
plist_set LSUIElement bool true

# Ad-hoc signature over the whole bundle (PyInstaller signs pieces; re-seal it).
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
"$APP/Contents/MacOS/$APP_NAME" --version
echo "Application built at: $APP"

if [ "$MAKE_DMG" = 1 ]; then
    DMG="$DIST_DIR/EQL-Combat-Feed-$VERSION.dmg"
    STAGE="$BUILD_DIR/dmg"
    rm -rf "$STAGE" "$DMG"
    mkdir -p "$STAGE"
    cp -R "$APP" "$STAGE/"
    ln -s /Applications "$STAGE/Applications"
    hdiutil create -quiet -volname "$APP_NAME $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
    echo "Disk image built at: $DMG"
fi
