"""AsciiAnything: a desktop app that turns images into ASCII art.

Animated GIFs play as moving ASCII art, with controls to pause, step
through the frames one at a time, and save the result as a new GIF.

Run it with:
    python ascii_app.py

or double-click "AsciiAnything.command" in Finder.
"""

# --- STEP 1: Imports -------------------------------------------------------
import os
import sys
import time

# PySide6 is a library for building windows, buttons and other controls.
# (It is the Python version of a toolkit called "Qt".)
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Reuse the code we already wrote! This imports from ascii_art.py, so the
# app and the terminal program share the same logic.
from PIL import Image  # Pillow, used here to write GIF files

from ascii_art import IMAGE_ERRORS, MAX_ANIMATION_TIME, image_to_art, load_frames

# The fewest and most characters wide the art can be (the slider's range).
MIN_WIDTH = 20
MAX_WIDTH = 250

# How many pixels wide a saved or copied PNG picture is, and the tallest
# it is allowed to be.
EXPORT_WIDTH = 2000
EXPORT_MAX_HEIGHT = 6000

# How many pixels wide a saved GIF is. A GIF holds one picture for every
# frame, so it is kept smaller than a PNG to stop the file becoming huge.
GIF_EXPORT_WIDTH = 800


# Our own kind of error, used to stop saving a GIF part-way through when
# the user presses Cancel. "pass" means "nothing to add": it behaves like
# any other error, just with its own name.
class SaveCancelled(Exception):
    pass


# --- STEP 2: An on/off switch ----------------------------------------------
# Qt doesn't come with a sliding on/off switch, so we draw our own.
# A "class" is a blueprint for a kind of object. "Switch(QAbstractButton)"
# means: a Switch is a button (so it already knows how to be clicked and
# to remember on/off), and we only add how it should LOOK.
class Switch(QAbstractButton):
    def __init__(self):
        super().__init__()        # do the normal button setup first
        self.setCheckable(True)   # it stays on or off, rather than just clicking
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)

    # Qt calls paintEvent whenever the switch needs to be drawn.
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)  # smooth edges
        painter.setPen(Qt.NoPen)                      # no outlines

        # The track: green when on, gray when off.
        painter.setBrush(QColor("#34c759") if self.isChecked() else QColor("#8e8e93"))
        painter.drawRoundedRect(0, 0, 44, 24, 12, 12)

        # The white knob: on the right when on, on the left when off.
        knob_x = 22 if self.isChecked() else 2
        painter.setBrush(QColor("white"))
        painter.drawEllipse(knob_x, 2, 20, 20)


# --- STEP 3: The area that shows the art -----------------------------------
class ArtView(QWidget):
    def __init__(self):
        super().__init__()
        self.lines = []          # the rows of text
        self.color_image = None  # one pixel per character, or None for white text
        self.cache = None        # a saved picture of the finished drawing
        self.setMinimumSize(480, 360)

        # SPEED: measure the font once, here, instead of on every redraw.
        # We measure one character at size 100; any other size is just
        # these numbers scaled up or down.
        self.base_font = QFont("Menlo")  # a font where every character is the same width
        self.base_font.setStyleHint(QFont.Monospace)
        self.base_font.setPointSizeF(100)
        metrics = QFontMetricsF(self.base_font)
        self.base_cell_width = metrics.horizontalAdvance("M")
        self.base_cell_height = metrics.height()
        # The "ascent" is how far the tallest letters rise above the line
        # the text sits on. We need it to position each row.
        self.base_ascent = metrics.ascent()

    def show_art(self, lines, color_image):
        self.lines = lines
        self.color_image = color_image
        self.cache = None  # the saved drawing is out of date; throw it away
        self.update()      # tells Qt "please redraw me", which calls paintEvent

    # Qt calls resizeEvent whenever this area changes size.
    def resizeEvent(self, event):
        self.cache = None  # the art must be redrawn at the new size

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("black"))

        if not self.lines:
            painter.setPen(QColor("#8e8e93"))
            painter.drawText(self.rect(), Qt.AlignCenter, "Choose a file to begin")
            return

        # SPEED: Qt asks us to repaint often (for example when another
        # window moves across ours). Drawing thousands of characters each
        # time would be wasteful, so we draw the art once into an off-screen
        # picture (the "cache") and afterwards just stamp that picture on.
        if self.cache is None:
            # Modern Mac screens pack 2 real pixels into each "point" of
            # size. Drawing at that ratio keeps the text sharp.
            self.cache = self.render(
                self.lines, self.color_image, self.width(), self.height(), self.devicePixelRatioF()
            )
        painter.drawPixmap(0, 0, self.cache)

    def export_picture(self):
        """Return the art on screen as a picture for saving or copying."""
        return self.picture_of(self.lines, self.color_image, EXPORT_WIDTH)

    def picture_of(self, lines, color_image, picture_width):
        """Return a picture of the given art, on a black background.

        The art doesn't have to be what is on screen: saving a GIF uses
        this to draw every frame of an animation in turn.
        """
        # The art's size if drawn with the size-100 font.
        base_width = len(lines[0]) * self.base_cell_width
        base_height = len(lines) * self.base_cell_height

        # Normally the picture is `picture_width` pixels wide, however big
        # the window is. Very tall, thin art is limited by height instead,
        # so the picture can never become enormous.
        scale = min(picture_width / base_width, EXPORT_MAX_HEIGHT / base_height)
        width = max(1, round(base_width * scale))
        height = max(1, round(base_height * scale))
        return self.render(lines, color_image, width, height, 1.0, background=QColor("black"))

    def render(self, lines, color_image, width, height, ratio, background=None):
        """Draw art into an off-screen picture and return it.

        `lines` and `color_image` are the art to draw. `width` and `height`
        are the picture's size, and `ratio` is how many real pixels to use
        per unit of size. If `background` is given, the
        picture is filled with that colour behind the art; otherwise the
        gaps between characters are left see-through.
        """

        pixmap = QPixmap(QSize(width, height) * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)  # start completely see-through

        row_count = len(lines)
        column_count = len(lines[0])

        # The art's size if drawn with the size-100 font.
        art_width = column_count * self.base_cell_width
        art_height = row_count * self.base_cell_height

        # How much to shrink (or grow) that so the whole picture just fits.
        scale = min(width / art_width, height / art_height)

        # Centre the art in the available space.
        left = (width - art_width * scale) / 2
        top = (height - art_height * scale) / 2

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setFont(self.base_font)
        painter.setPen(QColor("white"))

        # Rather than choosing a font size to fit (font sizes get rounded to
        # whole numbers, so the art could end up slightly too big and get cut
        # off), we always draw with the size-100 font and tell the painter to
        # scale everything it draws. translate() moves the starting corner;
        # scale() shrinks or grows all drawing after it.
        painter.translate(left, top)
        painter.scale(scale, scale)

        # SPEED: draw each row as one whole string, in white, rather than
        # one character at a time.
        for y, line in enumerate(lines):  # enumerate gives (position, item)
            baseline = y * self.base_cell_height + self.base_ascent
            painter.drawText(QPointF(0, baseline), line)

        if color_image is not None:
            # SPEED: colour every character in ONE step. "SourceIn" means
            # "paint only where something is already drawn". So when we
            # stretch the tiny colour image (one pixel per character) over
            # the text, each white character soaks up the colour of its own
            # pixel, and the see-through gaps between them stay see-through.
            #
            # The colour image has a one-pixel border all round (see
            # to_qimage), so we stretch it over an area one character
            # bigger than the art on every side. Some characters, the solid
            # blocks especially, are drawn a hair wider than their slot.
            # Without the border, that sliver outside the art would get no
            # colour and show as a thin white line down the edge.
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.drawImage(
                QRectF(
                    -self.base_cell_width,
                    -self.base_cell_height,
                    art_width + 2 * self.base_cell_width,
                    art_height + 2 * self.base_cell_height,
                ),
                color_image,
            )

        painter.resetTransform()  # back to normal, unscaled drawing

        if background is not None:
            # "DestinationOver" means "paint BEHIND what is already drawn",
            # so this fills in the see-through gaps without covering the art.
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
            painter.fillRect(QRectF(0, 0, width, height), background)

        painter.end()
        return pixmap


def to_qimage(image):
    """Convert a Pillow image into the kind of image Qt can draw.

    The result is one pixel bigger than `image` on every side: the pixels
    along each edge are repeated outwards to make a border. ArtView.render
    explains why.
    """
    width, height = image.size
    padded = Image.new("RGB", (width + 2, height + 2))
    padded.paste(image, (1, 1))  # the picture itself, one pixel in from the corner
    # crop((left, top, right, bottom)) cuts a piece out; paste() sticks it
    # down somewhere else. First copy the left and right edge columns outwards...
    padded.paste(image.crop((0, 0, 1, height)), (0, 1))
    padded.paste(image.crop((width - 1, 0, width, height)), (width + 1, 1))
    # ...then the top and bottom rows (now including the new corners).
    padded.paste(padded.crop((0, 1, width + 2, 2)), (0, 0))
    padded.paste(padded.crop((0, height, width + 2, height + 1)), (0, height + 1))
    image = padded

    data = image.tobytes()  # the raw red, green, blue numbers
    bytes_per_row = image.width * 3
    qimage = QImage(data, image.width, image.height, bytes_per_row, QImage.Format_RGB888)
    # copy() gives Qt its own copy of the numbers, so it doesn't depend on
    # `data`, which Python throws away when this function ends.
    return qimage.copy()


def to_pillow(pixmap):
    """Convert a picture drawn by Qt into a Pillow image (the reverse of to_qimage)."""
    qimage = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
    data = bytes(qimage.constBits())  # the raw red, green, blue numbers
    # Qt may add a few unused bytes to the end of each row, so we tell
    # Pillow how long a row really is (bytesPerLine) so it can skip them.
    return Image.frombuffer(
        "RGB", (qimage.width(), qimage.height()), data, "raw", "RGB", qimage.bytesPerLine(), 1
    )


def format_time(milliseconds):
    """Turn a number of milliseconds into text like "0:03.8" (minutes:seconds)."""
    # Work in whole tenths of a second, rounding first. (Rounding at the
    # end instead could turn 59.96 seconds into "0:60.0".)
    tenths = round(milliseconds / 100)
    # "//" is division that throws away the remainder, and "%" gives just
    # the remainder. There are 600 tenths of a second in a minute.
    minutes = tenths // 600
    seconds = (tenths % 600) / 10
    # "04.1f" means: one digit after the decimal point, padded with zeros
    # at the front to four characters, as in "03.8".
    return f"{minutes}:{seconds:04.1f}"


# --- STEP 4: The main window ------------------------------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AsciiAnything")
        self.image_name = ""    # the chosen file's name, without ".jpg" etc.

        # A still image is one "frame". An animated GIF is many, shown one
        # after another, each for its own length of time (in milliseconds).
        self.frames = []        # empty until an image is chosen
        self.frame_times = []   # how long each frame stays on screen
        self.frame_starts = []  # how far into the animation each frame begins
        self.frame_index = 0    # which frame is showing now (0 is the first)
        self.playing = False    # True while an animation is running
        self.frame_due = 0      # the moment the next frame should appear (a stopwatch reading)

        # The timer that moves an animation on to its next frame.
        self.frame_timer = QTimer(self)
        self.frame_timer.setSingleShot(True)
        # Ordinary timers are allowed to be a few percent early or late to
        # save power. An animation needs better timekeeping than that.
        self.frame_timer.setTimerType(Qt.PreciseTimer)
        self.frame_timer.timeout.connect(self.next_frame)

        # -- Create the controls --
        self.choose_button = QPushButton("Choose File…")
        self.file_label = QLabel("No file chosen")

        self.color_switch = Switch()
        self.blocks_switch = Switch()
        self.invert_switch = Switch()

        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(MIN_WIDTH, MAX_WIDTH)
        self.width_slider.setValue(100)
        self.width_slider.setFixedWidth(160)
        self.width_label = QLabel()

        self.art_view = ArtView()

        # The buttons for getting the art OUT of the app. They start
        # switched off ("disabled") because there is nothing to export yet.
        self.copy_text_button = QPushButton("Copy Text")
        self.copy_image_button = QPushButton("Copy Image")
        self.save_png_button = QPushButton("Save PNG…")
        self.export_buttons = [self.copy_text_button, self.copy_image_button, self.save_png_button]
        for button in self.export_buttons:
            button.setEnabled(False)
        # Saving a GIF only makes sense for an animation, so this button is
        # switched on separately from the others.
        self.save_gif_button = QPushButton("Save GIF…")
        self.save_gif_button.setEnabled(False)

        # The controls for an animation: step back a frame, play or pause,
        # step forward a frame, a bar showing how far through we are, and
        # the frame number and time in words.
        self.previous_button = QPushButton("‹ Frame")
        self.previous_button.setToolTip("Go back one frame")
        self.play_button = QPushButton("Pause")
        self.play_button.setFixedWidth(80)  # so it doesn't change size between "Play" and "Pause"
        self.next_button = QPushButton("Frame ›")
        self.next_button.setToolTip("Go forward one frame")
        # The bar is a slider with one position per frame. Dragging it
        # moves through the animation.
        self.timeline = QSlider(Qt.Horizontal)
        self.time_label = QLabel()

        # A line of text that confirms what just happened ("Text copied").
        self.status_label = QLabel()
        # A timer that wipes that message after a few seconds. "Single shot"
        # means it fires once each time it is started, rather than repeating.
        self.status_timer = QTimer(self)
        self.status_timer.setSingleShot(True)
        self.status_timer.timeout.connect(self.status_label.clear)

        # -- Arrange them --
        # A "layout" positions controls for us. QHBoxLayout puts things in
        # a horizontal row; QVBoxLayout stacks them vertically.
        controls = QHBoxLayout()
        controls.addWidget(self.choose_button)
        controls.addWidget(self.file_label)
        controls.addStretch()  # a springy gap that pushes the rest to the right
        for text, switch in [
            ("Color", self.color_switch),
            ("Blocks", self.blocks_switch),
            ("Invert", self.invert_switch),
        ]:
            controls.addSpacing(12)
            controls.addWidget(QLabel(text))
            controls.addWidget(switch)
        controls.addSpacing(12)
        controls.addWidget(self.width_label)
        controls.addWidget(self.width_slider)

        # A second row, under the art, for the status message and export buttons.
        export_row = QHBoxLayout()
        export_row.addWidget(self.status_label)
        export_row.addStretch()
        for button in self.export_buttons:
            export_row.addWidget(button)
        export_row.addWidget(self.save_gif_button)

        # The animation controls go in a row of their own, inside a plain
        # container widget, so the whole row can be hidden in one go when
        # the image isn't an animation.
        self.playback_bar = QWidget()
        playback_row = QHBoxLayout(self.playback_bar)
        playback_row.setContentsMargins(0, 0, 0, 0)  # no extra gap around the row
        playback_row.addWidget(self.previous_button)
        playback_row.addWidget(self.play_button)
        playback_row.addWidget(self.next_button)
        playback_row.addWidget(self.timeline, 1)  # the bar takes all spare space
        playback_row.addWidget(self.time_label)
        self.playback_bar.setVisible(False)  # hidden until an animation is opened

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.art_view, 1)  # the 1 means "take all spare space"
        layout.addWidget(self.playback_bar)
        layout.addLayout(export_row)

        # -- Connect the controls to actions --
        # "connect" means: when this happens, call that function.
        self.choose_button.clicked.connect(self.choose_image)
        self.copy_text_button.clicked.connect(self.copy_text)
        self.copy_image_button.clicked.connect(self.copy_image)
        self.save_png_button.clicked.connect(self.choose_save_location)
        self.save_gif_button.clicked.connect(self.choose_gif_location)
        self.previous_button.clicked.connect(self.step_back)
        self.play_button.clicked.connect(self.toggle_playing)
        self.next_button.clicked.connect(self.step_forward)
        self.timeline.valueChanged.connect(self.seek)
        self.timeline.sliderPressed.connect(self.frame_timer.stop)
        self.timeline.sliderReleased.connect(self.wait_for_next_frame)
        self.color_switch.toggled.connect(self.refresh)
        self.blocks_switch.toggled.connect(self.refresh)
        self.invert_switch.toggled.connect(self.refresh)
        self.width_slider.valueChanged.connect(self.refresh)

        self.refresh()

    def choose_image(self):
        """Show the file picker, then load whatever the user picked."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a file",
            os.path.expanduser("~/Desktop"),  # the folder the picker starts in
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.tif *.tiff)",
        )
        if path:  # path is empty if the user pressed Cancel
            self.open_image(path)

    def open_image(self, path):
        """Load the image at `path` and show it as ASCII art."""
        try:
            # SPEED: shrink the photo once, as it's loaded, to twice the
            # widest art the slider allows. Every switch flick and slider
            # move after that works from this small copy instead of from
            # millions of pixels. For an animated GIF this loads every frame.
            # Only the first 30 seconds of a longer animation are loaded;
            # `shortened` tells us if that happened.
            frames, frame_times, shortened = load_frames(path, max_width=MAX_WIDTH * 2)
        except IMAGE_ERRORS:
            # IMAGE_ERRORS covers "missing file", "not an image" and similar.
            # The previously chosen image (if any) stays on screen.
            QMessageBox.warning(self, "AsciiAnything", "That file couldn't be opened as an image.")
            return

        self.frames = frames
        self.frame_times = frame_times

        # Work out when each frame begins by keeping a running total of
        # the times of the frames before it.
        self.frame_starts = []
        total = 0
        for frame_time in frame_times:
            self.frame_starts.append(total)
            total += frame_time

        name = os.path.basename(path)                   # just the file's name
        self.image_name = os.path.splitext(name)[0]     # ...without ".jpg" etc.
        if len(name) > 30:
            name = name[:27] + "…"  # shorten long names so they don't crowd the controls
        self.file_label.setText(name)

        for button in self.export_buttons:
            button.setEnabled(True)  # now there is something to export

        # The animation controls only appear if there is more than one frame.
        animated = len(self.frames) > 1
        self.playback_bar.setVisible(animated)
        self.save_gif_button.setEnabled(animated)

        # Give the bar one position per frame. blockSignals(True) stops it
        # announcing "my value changed" while we set it up, because seek()
        # would otherwise run before the first frame is ready.
        self.timeline.blockSignals(True)
        self.timeline.setRange(0, len(self.frames) - 1)
        self.timeline.setPageStep(max(1, len(self.frames) // 10))  # the jump for a click beside the handle
        self.timeline.blockSignals(False)

        # The label's text changes on every frame. Give the label a fixed
        # width, big enough for its longest text (the last frame's, with a
        # little to spare), so the bar beside it doesn't twitch as it plays.
        self.show_frame(len(self.frames) - 1)
        longest = self.time_label.fontMetrics().horizontalAdvance(self.time_label.text())
        self.time_label.setFixedWidth(longest + 12)

        self.show_frame(0)
        # Start the animation, or (for a still image) stop any animation
        # left running from the previous image.
        self.set_playing(animated)

        if shortened:
            seconds = MAX_ANIMATION_TIME // 1000  # "//" divides and drops the remainder
            self.show_status(f"This animation is long, so only its first {seconds} seconds are used.")
        else:
            self.status_label.clear()  # wipe any message left from the previous file

    def show_frame(self, index):
        """Show frame number `index`, and move the bar and labels to match."""
        self.frame_index = index
        self.refresh()

        self.timeline.blockSignals(True)  # we are moving the bar, not the user
        self.timeline.setValue(index)
        self.timeline.blockSignals(False)

        if self.frames:
            total = self.frame_starts[-1] + self.frame_times[-1]  # [-1] is the last item
            self.time_label.setText(
                f"Frame {index + 1} of {len(self.frames)}    "
                f"{format_time(self.frame_starts[index])} / {format_time(total)}"
            )

    def set_playing(self, playing):
        """Start the animation (True) or pause it (False)."""
        self.playing = playing
        self.play_button.setText("Pause" if playing else "Play")
        if playing:
            self.wait_for_next_frame()
        else:
            self.frame_timer.stop()

    def wait_for_next_frame(self):
        """If playing, set the timer going for as long as the current frame should show."""
        if self.playing:
            frame_time = self.frame_times[self.frame_index]
            # Note the moment the next frame is due. perf_counter() is a
            # stopwatch that counts seconds; frame times are in milliseconds.
            self.frame_due = time.perf_counter() + frame_time / 1000
            self.frame_timer.start(frame_time)

    def toggle_playing(self):
        """The Play / Pause button: do whichever we aren't doing now."""
        self.set_playing(not self.playing)

    def next_frame(self):
        """Move a playing animation on by one frame. The frame timer calls this."""
        # "%" gives the remainder after dividing, so after the last frame
        # the count wraps round to 0 and the animation starts again.
        self.show_frame((self.frame_index + 1) % len(self.frames))

        # Work out when the frame after this one is due by adding this
        # frame's time to the moment THIS frame was due, not to the time
        # now. Converting and drawing take a little time, and counting
        # from "now" would let those delays pile up and slow the animation.
        self.frame_due += self.frame_times[self.frame_index] / 1000
        wait = self.frame_due - time.perf_counter()
        if wait < 0:
            # Running late (the window was being dragged, say, or the
            # computer is busy). Don't race to catch up, which would make
            # frames flash past: start counting afresh and give this frame
            # its full time.
            wait = self.frame_times[self.frame_index] / 1000
            self.frame_due = time.perf_counter() + wait
        self.frame_timer.start(round(wait * 1000))  # timers count in milliseconds

    def step_back(self):
        """The "‹ Frame" button: pause, and go back one frame."""
        self.set_playing(False)
        self.show_frame((self.frame_index - 1) % len(self.frames))

    def step_forward(self):
        """The "Frame ›" button: pause, and go forward one frame."""
        self.set_playing(False)
        self.show_frame((self.frame_index + 1) % len(self.frames))

    def seek(self, index):
        """Jump to frame `index`. The bar calls this when the user moves it."""
        self.show_frame(index)
        # If the animation is playing, carry on from the new frame, unless
        # the user is still holding the bar's handle. (Letting go of the
        # handle calls wait_for_next_frame, which carries on from there.)
        if not self.timeline.isSliderDown():
            self.wait_for_next_frame()

    def show_status(self, message):
        """Show a short confirmation message that disappears after 4 seconds."""
        self.status_label.setText(message)
        self.status_timer.start(4000)  # in milliseconds; restarts if already running

    def copy_text(self):
        """Put the art on the clipboard as plain text, ready to paste.

        For an animation, this (like Copy Image and Save PNG) uses the
        frame that is on screen at that moment.
        """
        # Plain text can't carry colour, so the text is the same with the
        # Color switch on or off.
        QApplication.clipboard().setText("\n".join(self.art_view.lines))
        self.show_status("Text copied. Paste it using a fixed-width font.")

    def copy_image(self):
        """Put a picture of the art on the clipboard."""
        QApplication.clipboard().setPixmap(self.art_view.export_picture())
        self.show_status("Image copied to the clipboard.")

    def choose_save_location(self):
        """Ask where to save the picture, then save it."""
        # An animation keeps playing while the save window is open, so take
        # the picture now: the frame saved is the one showing when the
        # button was clicked.
        picture = self.art_view.export_picture()
        suggested = os.path.join(os.path.expanduser("~/Desktop"), self.image_name + "-ascii.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save as PNG", suggested, "PNG image (*.png)")
        if path:  # path is empty if the user pressed Cancel
            self.save_png(path, picture)

    def save_png(self, path, picture):
        """Save `picture` as a PNG file at `path`."""
        if not path.lower().endswith(".png"):
            path += ".png"
        # save() returns True if it worked and False if it didn't
        # (for example, if the folder can't be written to).
        if picture.save(path, "PNG"):
            self.show_status(f"Saved {os.path.basename(path)}")
        else:
            QMessageBox.warning(self, "AsciiAnything", "The picture couldn't be saved there.")

    def choose_gif_location(self):
        """Ask where to save the animation, then save it."""
        # Pause while the save window is open, and carry on afterwards if
        # the animation was playing before.
        was_playing = self.playing
        self.set_playing(False)

        suggested = os.path.join(os.path.expanduser("~/Desktop"), self.image_name + "-ascii.gif")
        path, _ = QFileDialog.getSaveFileName(self, "Save as GIF", suggested, "GIF animation (*.gif)")
        # "try / finally": carry on playing afterwards whatever happens.
        try:
            if path:  # path is empty if the user pressed Cancel
                self.save_gif(path)
        finally:
            self.set_playing(was_playing)

    def save_gif(self, path):
        """Save the whole animation, as ASCII art, as a GIF file at `path`.

        Every frame is drawn using the current switch and slider settings.
        """
        if not path.lower().endswith(".gif"):
            path += ".gif"

        # A small window with a progress bar and a Cancel button, because
        # drawing every frame can take a few seconds.
        count = len(self.frames)
        progress = QProgressDialog("Saving GIF…", "Cancel", 0, count + 1, self)
        progress.setWindowModality(Qt.WindowModal)  # block our window while it's up
        progress.setMinimumDuration(0)              # show it straight away

        # A function containing "yield" is a "generator": instead of making
        # every picture up front, it hands them over one at a time, each
        # made only when asked for. That lets the progress bar move, and
        # Cancel work, while Pillow is collecting the frames. (Pillow still
        # keeps every finished frame in memory until the file is written,
        # so a very long animation needs a lot of memory to save.)
        def pictures():
            last_update = 0
            for number, frame in enumerate(self.frames):
                # SPEED: moving the progress bar redraws the window, which
                # is slow, so do it at most ten times a second rather than
                # once for every frame.
                now = time.perf_counter()
                if now - last_update > 0.1:
                    progress.setValue(number)
                    last_update = now
                if progress.wasCanceled():
                    raise SaveCancelled  # "raise" stops everything with this error

                lines, color_image = self.make_art(frame)
                picture = to_pillow(self.art_view.picture_of(lines, color_image, GIF_EXPORT_WIDTH))

                # SPEED: a GIF can only hold 256 different colours per
                # frame, so each picture's colours must be cut down to its
                # best 256 ("quantized"). Left alone, Pillow uses a slow,
                # careful method. FASTOCTREE is about ten times quicker,
                # looks the same for this kind of picture, and makes a
                # file less than half the size.
                yield picture.quantize(256, method=Image.Quantize.FASTOCTREE)

            # Every frame is drawn. Pillow now writes the file, which can
            # take a few seconds for a long animation and can't be cancelled.
            progress.setLabelText("Writing the file…")
            progress.setCancelButton(None)  # None removes the Cancel button
            progress.setValue(count)

        # Write to a temporary file first and rename it at the end. That
        # way a cancelled or failed save never leaves half a GIF behind, or
        # spoils a file that was already there.
        temporary = path + ".part"
        remaining = pictures()
        try:
            first = next(remaining)  # next() asks the generator for one picture
            first.save(
                temporary,
                format="GIF",
                save_all=True,             # an animation, not just the first frame
                append_images=remaining,   # the rest of the frames
                duration=self.frame_times, # how long each frame shows
                loop=0,                    # 0 means "repeat forever"
            )
            os.replace(temporary, path)  # rename it into place
            self.show_status(f"Saved {os.path.basename(path)}")
        except SaveCancelled:
            self.show_status("Saving cancelled.")
        except Exception:
            # "Exception" means any kind of error at all: the folder can't
            # be written to, the computer ran out of memory, and so on.
            QMessageBox.warning(self, "AsciiAnything", "The GIF couldn't be saved.")
        finally:
            # "finally" runs whether saving worked, failed or was cancelled.
            progress.close()
            if os.path.exists(temporary):
                os.remove(temporary)

    def refresh(self):
        """Rebuild the art using the current switch and slider settings."""
        width = self.width_slider.value()
        self.width_label.setText(f"Width: {width}")

        if not self.frames:
            return  # nothing to draw until an image has been chosen

        # For an animation this converts just the frame being shown. It is
        # quick enough to do afresh for every frame, which means the
        # switches and slider take effect instantly, even mid-animation.
        lines, color_image = self.make_art(self.frames[self.frame_index])
        self.art_view.show_art(lines, color_image)

    def make_art(self, frame):
        """Turn one frame into art using the current switch and slider settings.

        Returns the rows of text, and the colour image (one pixel per
        character), which is None when the Color switch is off.
        """
        lines, small = image_to_art(
            frame,
            self.width_slider.value(),
            invert=self.invert_switch.isChecked(),
            style="blocks" if self.blocks_switch.isChecked() else "chars",
        )
        color_image = to_qimage(small) if self.color_switch.isChecked() else None
        return lines, color_image


# --- STEP 5: Start the app ---------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AsciiAnything")
    window = MainWindow()
    window.resize(1000, 700)
    window.show()
    # app.exec() runs the "event loop": the app sits waiting for clicks and
    # key presses, and responds to them, until the window is closed.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
