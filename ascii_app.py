"""AsciiAnything: a desktop app that turns images into ASCII art.

Run it with:
    python ascii_app.py

or double-click "AsciiAnything.command" in Finder.
"""

# --- STEP 1: Imports -------------------------------------------------------
import os
import sys

# PySide6 is a library for building windows, buttons and other controls.
# (It is the Python version of a toolkit called "Qt".)
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# Reuse the code we already wrote! This imports two functions from
# ascii_art.py, so the app and the terminal program share the same logic.
from ascii_art import image_to_art, load_image

# The fewest and most characters wide the art can be (the slider's range).
MIN_WIDTH = 20
MAX_WIDTH = 250


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
        self.font = QFont("Menlo")  # a font where every character is the same width
        self.font.setStyleHint(QFont.Monospace)
        self.font.setPointSizeF(100)
        metrics = QFontMetricsF(self.font)
        self.base_cell_width = metrics.horizontalAdvance("M")
        self.base_cell_height = metrics.height()

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
            painter.drawText(self.rect(), Qt.AlignCenter, "Choose an image to begin")
            return

        # SPEED: Qt asks us to repaint often (for example when another
        # window moves across ours). Drawing thousands of characters each
        # time would be wasteful, so we draw the art once into an off-screen
        # picture (the "cache") and afterwards just stamp that picture on.
        if self.cache is None:
            self.cache = self.render()
        painter.drawPixmap(0, 0, self.cache)

    def render(self):
        """Draw the art into an off-screen picture and return it."""

        # Modern Mac screens pack 2 real pixels into each "point" of size.
        # Making the picture that much bigger keeps the text sharp.
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(self.size() * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)  # start completely see-through

        row_count = len(self.lines)
        column_count = len(self.lines[0])

        # Pick the biggest font size at which the whole picture still fits.
        scale = min(
            self.width() / (column_count * self.base_cell_width),
            self.height() / (row_count * self.base_cell_height),
        )
        font = QFont(self.font)  # a copy, so the size-100 original is untouched
        font.setPointSizeF(max(1.0, 100 * scale))

        # How big is one character cell at this size?
        metrics = QFontMetricsF(font)
        cell_width = metrics.horizontalAdvance("M")
        cell_height = metrics.height()

        # Centre the picture in the available space.
        left = (self.width() - column_count * cell_width) / 2
        top = (self.height() - row_count * cell_height) / 2

        painter = QPainter(pixmap)
        painter.setFont(font)
        painter.setPen(QColor("white"))

        # SPEED: draw each row as one whole string, in white, rather than
        # one character at a time.
        for y, line in enumerate(self.lines):  # enumerate gives (position, item)
            baseline = top + y * cell_height + metrics.ascent()
            painter.drawText(QPointF(left, baseline), line)

        if self.color_image is not None:
            # SPEED: colour every character in ONE step. "SourceIn" means
            # "paint only where something is already drawn". So when we
            # stretch the tiny colour image (one pixel per character) over
            # the text, each white character soaks up the colour of its own
            # pixel, and the see-through gaps between them stay see-through.
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            art_area = QRectF(left, top, column_count * cell_width, row_count * cell_height)
            painter.drawImage(art_area, self.color_image)

        painter.end()
        return pixmap


def to_qimage(image):
    """Convert a Pillow image into the kind of image Qt can draw."""
    data = image.tobytes()  # the raw red, green, blue numbers
    bytes_per_row = image.width * 3
    qimage = QImage(data, image.width, image.height, bytes_per_row, QImage.Format_RGB888)
    # copy() gives Qt its own copy of the numbers, so it doesn't depend on
    # `data`, which Python throws away when this function ends.
    return qimage.copy()


# --- STEP 4: The main window ------------------------------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AsciiAnything")
        self.image = None  # no image chosen yet

        # -- Create the controls --
        self.choose_button = QPushButton("Choose Image…")
        self.file_label = QLabel("No image chosen")

        self.color_switch = Switch()
        self.blocks_switch = Switch()
        self.invert_switch = Switch()

        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setRange(MIN_WIDTH, MAX_WIDTH)
        self.width_slider.setValue(100)
        self.width_slider.setFixedWidth(160)
        self.width_label = QLabel()

        self.art_view = ArtView()

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

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.art_view, 1)  # the 1 means "take all spare space"

        # -- Connect the controls to actions --
        # "connect" means: when this happens, call that function.
        self.choose_button.clicked.connect(self.choose_image)
        self.color_switch.toggled.connect(self.refresh)
        self.blocks_switch.toggled.connect(self.refresh)
        self.invert_switch.toggled.connect(self.refresh)
        self.width_slider.valueChanged.connect(self.refresh)

        self.refresh()

    def choose_image(self):
        """Show the file picker, then load whatever the user picked."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose an image",
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
            # millions of pixels.
            self.image = load_image(path, max_width=MAX_WIDTH * 2)
        except OSError:
            # OSError covers "missing file", "not an image" and similar.
            QMessageBox.warning(self, "AsciiAnything", "That file couldn't be opened as an image.")
            return
        self.file_label.setText(os.path.basename(path))  # just the file's name
        self.refresh()

    def refresh(self):
        """Rebuild the art using the current switch and slider settings."""
        width = self.width_slider.value()
        self.width_label.setText(f"Width: {width}")

        if self.image is None:
            return  # nothing to draw until an image has been chosen

        lines, small = image_to_art(
            self.image,
            width,
            invert=self.invert_switch.isChecked(),
            style="blocks" if self.blocks_switch.isChecked() else "chars",
        )
        color_image = to_qimage(small) if self.color_switch.isChecked() else None
        self.art_view.show_art(lines, color_image)


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
