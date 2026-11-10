#!/bin/zsh
# Builds AsciiAnything.app from the Python code.
# Run this again whenever you change ascii_app.py or ascii_art.py:
#     ./build_app.sh
# The finished app appears in the "dist" folder.

cd "$(dirname "$0")"

# The app's version number, shown in Finder's "Get Info" window.
# Change this each time you publish a new release.
VERSION="1.1.0"

# PyInstaller bundles our code, Python itself, and the libraries we use
# (Pillow and PySide6) into one self-contained Mac app.
#   --windowed    make a real Mac app with no Terminal window
#   --name        what the app is called
#   --icon        the picture shown in the Dock and Finder
#   --noconfirm   replace the previous build without asking
#
# "|| exit 1" means: if the build fails, stop here instead of carrying on.
.venv/bin/pyinstaller --windowed --name AsciiAnything --icon icon.icns --noconfirm ascii_app.py || exit 1

# Write the version number into the app's information file.
APP="dist/AsciiAnything.app"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist" || exit 1

# macOS seals every app with a signature that covers its files. We just
# changed one, so the app must be re-signed or macOS will refuse to open it.
# "--sign -" makes a basic signature that needs no Apple Developer account.
codesign --force --deep --sign - "$APP" || exit 1

echo "Built $APP (version $VERSION)"
