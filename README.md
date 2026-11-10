# AsciiAnything

Turn any image into ASCII art, in a Mac desktop app or in the terminal.

## Features

- **Color**: draw each character in the colour of the pixel it came from
- **Blocks**: switch between keyboard characters (` .:-=+*#%@`) and a block gradient (` ░▒▓█`)
- **Invert**: swap light and dark
- **Width**: choose how many characters wide the art is

## Setup

You need Python 3.9 or newer.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the desktop app

```
python ascii_app.py
```

## Run in the terminal

```
python ascii_art.py path/to/image.jpg --color --style blocks --width 120
```

Run `python ascii_art.py --help` to see every option.

## Build the Mac app

```
./build_app.sh
```

The finished `AsciiAnything.app` appears in the `dist` folder. Drag it into Applications.

## Files

- `ascii_art.py`: the image-to-characters logic and the terminal program
- `ascii_app.py`: the desktop app
- `build_app.sh`: builds `AsciiAnything.app` with PyInstaller
- `AsciiAnything.command`: double-click to run the app from the code without building
- `icon.icns`: the app icon
