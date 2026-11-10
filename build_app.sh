#!/bin/zsh
# Builds AsciiAnything.app from the Python code.
# Run this again whenever you change ascii_app.py or ascii_art.py:
#     ./build_app.sh
# The finished app appears in the "dist" folder.

cd "$(dirname "$0")"

# PyInstaller bundles our code, Python itself, and the libraries we use
# (Pillow and PySide6) into one self-contained Mac app.
#   --windowed    make a real Mac app with no Terminal window
#   --name        what the app is called
#   --icon        the picture shown in the Dock and Finder
#   --noconfirm   replace the previous build without asking
.venv/bin/pyinstaller --windowed --name AsciiAnything --icon icon.icns --noconfirm ascii_app.py
