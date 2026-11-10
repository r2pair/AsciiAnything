#!/bin/zsh
# Double-click this file in Finder to start AsciiAnything.
# It moves into this file's folder, then runs the app with the project's Python.
cd "$(dirname "$0")" && .venv/bin/python ascii_app.py
