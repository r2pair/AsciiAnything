"""Turn an image into ASCII art and print it in the terminal.

Usage:
    python ascii_art.py path/to/image.jpg
    python ascii_art.py path/to/image.jpg --width 120
    python ascii_art.py path/to/image.jpg --invert
    python ascii_art.py path/to/image.jpg --color
    python ascii_art.py path/to/image.jpg --style blocks
    python ascii_art.py path/to/animation.gif

An animated GIF plays in the terminal, over and over, until you press Ctrl+C.
Only the first 30 seconds of a longer animation are used.
"""

# --- STEP 1: Imports -------------------------------------------------------
# "import" pulls in code other people already wrote so we don't have to.
import argparse  # reads options typed after the program name (built into Python)
import shutil    # lets us ask how wide the terminal window is (built into Python)
import sys       # lets us exit with an error message (built into Python)
import time      # lets us pause between the frames of an animation (built into Python)

# Pillow: the library that opens and resizes images.
from PIL import Image, ImageOps, ImageSequence

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

# More of those codes, used to play animations.
# The "alternate screen" is a blank spare page that full-screen programs
# draw on. Leaving it puts back everything that was in the terminal before.
ALT_SCREEN_ON = "\033[?1049h"
ALT_SCREEN_OFF = "\033[?1049l"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CURSOR_HOME = "\033[H"  # jump back to the top-left corner

# An animation is a series of pictures called "frames", each shown for a
# set time, measured in milliseconds (thousandths of a second). Some GIFs
# ask for an impossibly short time; like web browsers, we show those
# frames for DEFAULT_FRAME_TIME instead.
MIN_FRAME_TIME = 20
DEFAULT_FRAME_TIME = 100

# The kinds of file we treat as animations. Some other kinds can hold
# several pictures too (a scanned document saved as a many-page TIFF, or a
# camera photo with a hidden preview picture inside), but those are not
# animations, so for them we use just the first picture.
ANIMATED_FORMATS = ("GIF", "PNG", "WEBP")

# The longest animation we will load, in milliseconds (30 seconds). Every
# frame is held in the computer's memory at once, so a very long animation
# could use it all up. Anything after this point in the file is ignored.
MAX_ANIMATION_TIME = 30_000  # the underscore is only there to make the number easier to read

# The kinds of error that opening an image can cause. OSError covers missing
# files, files that aren't images, damaged images and "permission denied".
# DecompressionBombError is Pillow refusing an absurdly large image.
IMAGE_ERRORS = (OSError, Image.DecompressionBombError)


def tidy_image(image, max_width=None):
    """Turn a freshly opened image (or one frame of an animation) into a
    plain colour image, shrunk to at most `max_width` pixels wide."""

    # Phone photos are often stored sideways with a note saying "rotate me".
    # This applies that note so the picture is the right way up.
    image = ImageOps.exif_transpose(image)

    # Some images (logos, stickers) have see-through areas. Those pixels
    # still have a hidden colour, which can be anything, so we lay the image
    # over a plain black background to make see-through areas properly dark.
    if image.has_transparency_data:
        image = image.convert("RGBA")  # the A is "alpha": how solid each pixel is
        background = Image.new("RGBA", image.size, "black")
        image = Image.alpha_composite(background, image)

    # "RGB" mode means each pixel is three numbers: how much red, green and
    # blue it contains, each from 0 to 255.
    image = image.convert("RGB")

    if max_width and image.width > max_width:
        # thumbnail() shrinks the image, keeping its shape, so that it fits
        # inside the given (width, height) box.
        image.thumbnail((max_width, image.height))

    return image


def load_frames(path, max_width=None):
    """Open the file at `path` and return every frame of it.

    Returns three things:
      - frames:    a list of colour images, one per frame
      - times:     a list of how long to show each frame, in milliseconds
      - shortened: True if the animation was longer than MAX_ANIMATION_TIME
                   and the rest of it was left out, otherwise False

    An ordinary still image comes back as a single frame.

    If `max_width` is given, every frame is shrunk to at most that many
    pixels wide. A phone photo has millions of pixels but the art only
    needs a few hundred across, so shrinking it once, up front, makes every
    later step much faster.
    """

    # --- STEP 3: Open the image --------------------------------------------
    image = Image.open(path)

    # Only some kinds of file (GIFs, mainly) can hold more than one frame.
    # getattr(..., False) means "use False if the image has no such setting".
    animated = image.format in ANIMATED_FORMATS and getattr(image, "is_animated", False)
    if not animated:
        if max_width:
            # SPEED: JPEG files can be decoded directly at 1/2, 1/4 or 1/8
            # size, which is far quicker than decoding every pixel and then
            # shrinking. draft() asks for that. It does nothing for other
            # kinds of file.
            image.draft("RGB", (max_width, max_width))
        return [tidy_image(image, max_width)], [0], False

    frames = []
    times = []
    total_time = 0     # how long the frames loaded so far run for
    shortened = False
    # ImageSequence.Iterator hands us the frames one at a time, in order.
    for frame in ImageSequence.Iterator(image):
        if total_time >= MAX_ANIMATION_TIME:
            # We have 30 seconds' worth already and there is still more in
            # the file. "break" leaves the loop early, skipping the rest.
            shortened = True
            break

        # Some kinds of file give the time with a decimal point (80.0);
        # round() makes it a whole number, which is what timers expect.
        frame_time = round(frame.info.get("duration", 0))  # 0 if the file doesn't say
        if frame_time < MIN_FRAME_TIME:
            frame_time = DEFAULT_FRAME_TIME
        times.append(frame_time)
        total_time += frame_time
        frames.append(tidy_image(frame, max_width))

    return frames, times, shortened


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
    # SPEED: reducing_gap=2.0 lets Pillow shrink a much bigger image in two
    # steps: a very fast rough shrink to about twice the final size, then
    # the careful one. The result looks the same and takes a third of the time.
    small = image.resize((width, height), reducing_gap=2.0)

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
    row_length = small.width * 3  # three numbers for every character in a row

    colored_lines = []
    for y, line in enumerate(lines):  # enumerate gives (position, item)
        # SPEED: we collect the pieces in a list and join them once at the
        # end. Adding to a string piece by piece makes Python copy the whole
        # string over and over.
        pieces = []
        previous_color = None

        # Cut this row's colours out of `rgb`, then split them into all the
        # reds, all the greens and all the blues. [0::3] means "start at
        # item 0 and take every 3rd item"; [1::3] starts at item 1, and so on.
        row = rgb[y * row_length:(y + 1) * row_length]
        reds, greens, blues = row[0::3], row[1::3], row[2::3]

        # SPEED: zip() hands us each character together with its red, green
        # and blue, which is quicker than looking each one up by position.
        for char, red, green, blue in zip(line, reds, greens, blues):
            if char != " ":  # a space is invisible, so it needs no colour
                color = (red, green, blue)

                # SPEED: only send a colour code when the colour actually
                # changes. Neighbouring characters often share a colour.
                if color != previous_color:
                    # "\033[38;2;R;G;Bm" means "set the text colour to this
                    # red/green/blue mix", each from 0 (none) to 255 (full).
                    pieces.append(f"\033[38;2;{red};{green};{blue}m")
                    previous_color = color
            pieces.append(char)

        pieces.append(RESET)  # stop the colour leaking past the end of the row
        colored_lines.append("".join(pieces))

    return colored_lines


def frame_to_text(image, width, invert=False, color=False, style="chars"):
    """Turn one image into a single string of ASCII art, ready to print."""

    lines, small = image_to_art(image, width, invert, style)

    if color:
        lines = colorize(lines, small)

    # Glue all the rows together with a "new line" between each one.
    return "\n".join(lines)


def play_animation(frames, times, make_text):
    """Show the frames one after another, forever, until the user presses
    Ctrl+C.

    `frames` are the images, `times` says how long each one stays up, and
    `make_text` is a function that turns one image into its ASCII art.
    """

    # SPEED: converting every frame before starting would mean a long wait
    # in front of a blank screen for a long animation. Instead, each frame
    # is converted the first time it is needed and the result kept here, so
    # playing starts at once and later times round only have to print.
    # [None] * 3 makes the list [None, None, None]: an empty slot per frame.
    texts = [None] * len(frames)

    write = sys.stdout.write  # a shorter name for "send this to the terminal"
    write(ALT_SCREEN_ON + HIDE_CURSOR)

    # "try / finally" means: whatever happens in the "try" part, even an
    # error, always run the "finally" part afterwards. That guarantees the
    # terminal is put back to normal.
    try:
        # The moment the next frame is due, on a clock that counts seconds.
        due = time.monotonic()

        while True:  # loop forever; Ctrl+C is the only way out
            for index, frame_time in enumerate(times):
                if texts[index] is None:
                    # Jumping to the top-left corner and printing draws the
                    # new frame straight over the old one. Every frame is
                    # the same size, so nothing of the old one is left
                    # showing. The "jump" code is stored with the text.
                    texts[index] = CURSOR_HOME + make_text(frames[index])
                    frames[index] = None  # the image is finished with; free its memory

                write(texts[index])
                sys.stdout.flush()  # send it now rather than "when convenient"

                # Wait until the next frame is due, rather than for the
                # whole frame time: converting and printing took some of
                # that time already, and the animation would run slow.
                due += frame_time / 1000  # the clock counts in seconds
                wait = due - time.monotonic()
                if wait < 0:
                    # Running late (a slow terminal, or a busy computer).
                    # Don't race to catch up, which would make frames flash
                    # past: start counting afresh and give this frame its
                    # full time.
                    wait = frame_time / 1000
                    due = time.monotonic() + wait
                time.sleep(wait)
    except KeyboardInterrupt:
        pass  # Ctrl+C was pressed. That's the normal way to stop, not an error.
    finally:
        write(SHOW_CURSOR + ALT_SCREEN_OFF)
        sys.stdout.flush()


def main():
    # --- STEP 6: Read what the user typed ----------------------------------
    parser = argparse.ArgumentParser(
        description="Turn an image into ASCII art. Animated GIFs play until you press Ctrl+C."
    )
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
        # Twice the final width keeps plenty of detail for the shrinking step.
        frames, times, shortened = load_frames(args.image, max_width=width * 2)
    except FileNotFoundError:
        sys.exit(f"Error: can't find a file at '{args.image}'.")
    except IsADirectoryError:
        sys.exit(f"Error: '{args.image}' is a folder, not an image.")
    except Image.UnidentifiedImageError:
        sys.exit(f"Error: '{args.image}' doesn't look like an image file.")
    except IMAGE_ERRORS as error:
        # Anything else that can go wrong: no permission to read the file,
        # a damaged image, and so on. `error` holds the details.
        sys.exit(f"Error: couldn't read '{args.image}': {error}")

    # --- STEP 8: Show a still image -----------------------------------------
    # isatty() is False when the output is going into a file or another
    # program rather than onto the screen. An animation makes no sense
    # there, so we print just the first frame.
    if len(frames) == 1 or not sys.stdout.isatty():
        print(frame_to_text(frames[0], width, args.invert, args.color, args.style))
        return

    # --- STEP 9: Play an animation ------------------------------------------
    # Each frame is drawn over the last one, which only works if a whole
    # frame fits in the terminal window. Work out the widest art that does.
    terminal = shutil.get_terminal_size()
    first = frames[0]
    rows_available = max(1, terminal.lines - 1)  # leave the bottom row free
    # The art is (height / width * columns * CHAR_HEIGHT_RATIO) rows tall;
    # this is that sum turned around to give columns from rows.
    widest_for_height = int(rows_available * first.width / (first.height * CHAR_HEIGHT_RATIO))
    widest = max(1, min(terminal.columns, widest_for_height))

    if width > widest:
        if args.width is not None:
            sys.exit(
                f"Error: an animation {width} characters wide doesn't fit in this "
                f"terminal window. Use --width {widest} or less, or make the window bigger."
            )
        width = widest  # no width was asked for, so quietly use one that fits

    # A small function that turns one frame into text using the options
    # the user chose. play_animation() calls it for each frame as needed.
    def make_text(frame):
        return frame_to_text(frame, width, args.invert, args.color, args.style)

    if shortened:
        # file=sys.stderr sends this to the "error" channel, which is the
        # proper place for notes that aren't part of the art itself. It
        # stays in the terminal, above the animation, after you press Ctrl+C.
        seconds = MAX_ANIMATION_TIME // 1000
        print(f"Note: only the first {seconds} seconds of this animation are played.", file=sys.stderr)

    play_animation(frames, times, make_text)


# This line means "only run main() when this file is run directly",
# which is the standard way to start a Python program.
if __name__ == "__main__":
    main()
