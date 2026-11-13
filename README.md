# AsciiAnything

Turn any image into ASCII art, in a Mac desktop app or in the terminal.

## Features

- **Color**: draw each character in the colour of the pixel it came from
- **Blocks**: switch between keyboard characters (` .:-=+*#%@`) and a block gradient (` ░▒▓█`)
- **Invert**: swap light and dark
- **Width**: choose how many characters wide the art is
- **Animated GIFs**: a GIF plays as moving ASCII art, and the switches and width slider work while it plays. Only the first 30 seconds of a longer animation are used
- **Playback controls**: play, pause, step one frame back or forward, and drag the bar to move through the animation
- **Save GIF**: save the whole animation as a new ASCII art GIF, 800 pixels wide
- **Copy Text**: copy the art to the clipboard as plain text
- **Copy Image** and **Save PNG**: copy or save the art as a picture, in colour if Color is on

## Download

Get the ready-made Mac app from the [Releases page](https://github.com/r2pair/AsciiAnything/releases/latest). It needs a Mac with Apple Silicon (M1 or newer). The release notes explain how to open it the first time.

## Setup

To run from the code instead:

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

Give it an animated GIF and it plays in the terminal until you press Ctrl+C:

```
python ascii_art.py path/to/animation.gif --color
```

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
