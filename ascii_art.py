"""Turn an image into ASCII art and print it in the terminal.

Usage:
    python ascii_art.py path/to/image.jpg
    python ascii_art.py path/to/image.jpg --width 120
    python ascii_art.py path/to/image.jpg --invert
    python ascii_art.py path/to/image.jpg --color
    python ascii_art.py path/to/image.jpg --style blocks
"""

# --- STEP 1: Imports -------------------------------------------------------
# "import" pulls in code other people already wrote so we don't have to.
import argparse  # reads options typed after the program name (built into Python)
import shutil    # lets us ask how wide the terminal window is (built into Python)
import sys       # lets us exit with an error message (built into Python)

from PIL import Image, ImageOps  # Pillow: the library that opens and resizes images

# --- STEP 2: The character "palette" ---------------------------------------
# These characters are ordered from visually lightest (a space) to
# heaviest (@). A dark pixel gets a light character and a bright pixel a
# heavy one, because most terminals show bright text on a dark background.
#
# This is a "dictionary": it pairs up names (the "keys", on the left) with
# values (on the right), so we can look a palette up by its name.
# To add your own style, add another line here with a new name.
PALETTES = {
    "chars": " .:-=+*#%@",   # ordinary keyboard characters
    "blocks": " ░▒▓█",       # shaded blocks, for a smoother gradient look
}

# Terminal characters are roughly twice as tall as they are wide. Without
# correcting for that, every picture would look stretched vertically.
CHAR_HEIGHT_RATIO = 0.5

# Terminals understand special invisible codes called "ANSI escape codes".
# Printing one doesn't show anything; it changes how the text AFTER it looks.
# RESET switches the text back to the terminal's normal colour.
RESET = "\033[0m"


def load_image(path, max_width=None):
    """Open the image file at `path` and return it as a colour image.

    If `max_width` is given, the image is shrunk to at most that many pixels
    wide. A phone photo has millions of pixels but the art only needs a few
    hundred across, so shrinking it once, up front, makes every later step
    much faster.
    """

    # --- STEP 3: Open the image --------------------------------------------
    image = Image.open(path)

    if max_width:
        # SPEED: JPEG files can be decoded directly at 1/2, 1/4 or 1/8 size,
        # which is far quicker than decoding every pixel and then shrinking.
        # draft() asks for that. It does nothing for other kinds of file.
        image.draft("RGB", (max_width, max_width))

    # Phone photos are often stored sideways with a note saying "rotate me".
    # This applies that note so the picture is the right way up.
    image = ImageOps.exif_transpose(image)

    # "RGB" mode means each pixel is three numbers: how much red, green and
    # blue it contains, each from 0 to 255.
    image = image.convert("RGB")

    if max_width and image.width > max_width:
        # thumbnail() shrinks the image, keeping its shape, so that it fits
        # inside the given (width, height) box.
        image.thumbnail((max_width, image.height))

    return image


def image_to_art(image, width, invert=False, style="chars"):
    """Turn an image into ASCII art.

    Returns two things:
      - lines: a list of strings, one per row of the art
      - small: the shrunken colour image, which has exactly one pixel per
               character, so pixel (x, y) is the colour of character x on
               line y

    Both the terminal program (below) and the desktop app (ascii_app.py)
    use this function, so the picture-to-characters logic lives in one place.
    """

    # --- STEP 4: Shrink it -------------------------------------------------
    # One character will stand in for one pixel, so the image has to be
    # only as wide as the number of characters we want per line.
    height = int(image.height / image.width * width * CHAR_HEIGHT_RATIO)
    height = max(1, height)  # never let it shrink to zero rows
    small = image.resize((width, height))

    # --- STEP 5: Swap each pixel for a character ---------------------------
    chars = PALETTES[style]  # look up the palette by its name
    if invert:
        chars = chars[::-1]  # [::-1] reverses a string

    # SPEED: a pixel's brightness is a number from 0 to 255, so there are
    # only 256 possible answers to "which character does this brightness
    # get?". We work all 256 out once, up front, as a 256-character string
    # called a "lookup table": the character for brightness 37 is table[37].
    # "//" is division that throws away the remainder.
    table = "".join(chars[brightness * len(chars) // 256] for brightness in range(256))

    # "L" mode is grayscale: each pixel is ONE number from 0 (black) to 255
    # (white). tobytes() hands us all those numbers in one go, row after row.
    brightness_values = small.convert("L").tobytes()

    # SPEED: instead of looking at pixels one at a time in a Python loop,
    # we convert them all in a single step. decode("latin-1") turns each
    # number into the character with that number, and translate(table) then
    # swaps every character for the entry at that position in our table.
    # Both run inside Python's fast built-in machinery.
    text = brightness_values.decode("latin-1").translate(table)

    # `text` is one long string. Cut it into rows of `width` characters.
    lines = [text[start:start + width] for start in range(0, len(text), width)]

    return lines, small


def colorize(lines, small):
    """Add terminal colour codes to the art, and return the coloured lines."""

    # All the colour numbers in one long sequence: red, green, blue, red,
    # green, blue, ... for each pixel in turn.
    rgb = small.tobytes()
    width = small.width

    colored_lines = []
    for y, line in enumerate(lines):  # enumerate gives (position, item)
        # SPEED: we collect the pieces in a list and join them once at the
        # end. Adding to a string piece by piece makes Python copy the whole
        # string over and over.
        pieces = []
        previous_color = None

        offset = y * width * 3  # where this row's colours start in `rgb`
        for x, char in enumerate(line):
            if char != " ":  # a space is invisible, so it needs no colour
                position = offset + x * 3
                color = rgb[position:position + 3]

                # SPEED: only send a colour code when the colour actually
                # changes. Neighbouring characters often share a colour.
                if color != previous_color:
                    # "\033[38;2;R;G;Bm" means "set the text colour to this
                    # red/green/blue mix", each from 0 (none) to 255 (full).
                    pieces.append(f"\033[38;2;{color[0]};{color[1]};{color[2]}m")
                    previous_color = color
            pieces.append(char)

        pieces.append(RESET)  # stop the colour leaking past the end of the row
        colored_lines.append("".join(pieces))

    return colored_lines


def image_to_ascii(path, width, invert=False, color=False, style="chars"):
    """Open the image at `path` and return it as a string of ASCII art."""

    # Twice the final width keeps plenty of detail for the shrinking step.
    image = load_image(path, max_width=width * 2)
    lines, small = image_to_art(image, width, invert, style)

    if color:
        lines = colorize(lines, small)

    # Glue all the rows together with a "new line" between each one.
    return "\n".join(lines)


def main():
    # --- STEP 6: Read what the user typed ----------------------------------
    parser = argparse.ArgumentParser(description="Turn an image into ASCII art.")
    parser.add_argument("image", help="path to the image file")
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="how many characters wide the art should be (default: fit the terminal)",
    )
    parser.add_argument(
        "--invert",
        action="store_true",
        help="swap light and dark (use this if your terminal has a light background)",
    )
    parser.add_argument(
        "--color",
        action="store_true",
        help="print each character in the colour of the pixel it came from",
    )
    parser.add_argument(
        "--style",
        choices=list(PALETTES),  # only the names in PALETTES are allowed
        default="chars",
        help="which set of characters to draw with (default: chars)",
    )
    args = parser.parse_args()

    # If no width was given, use the terminal's width, capped at 100.
    width = args.width
    if width is None:
        width = min(shutil.get_terminal_size().columns, 100)
    if width < 1:
        sys.exit("Error: --width must be at least 1.")

    # --- STEP 7: Do the work, and handle things going wrong ----------------
    # "try / except" means: attempt this, and if a specific problem
    # happens, run the matching "except" block instead of crashing.
    try:
        art = image_to_ascii(args.image, width, args.invert, args.color, args.style)
    except FileNotFoundError:
        sys.exit(f"Error: can't find a file at '{args.image}'.")
    except IsADirectoryError:
        sys.exit(f"Error: '{args.image}' is a folder, not an image.")
    except Image.UnidentifiedImageError:
        sys.exit(f"Error: '{args.image}' doesn't look like an image file.")

    print(art)


# This line means "only run main() when this file is run directly",
# which is the standard way to start a Python program.
if __name__ == "__main__":
    main()
