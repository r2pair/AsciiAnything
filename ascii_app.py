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
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
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

# Reuse the code we already wrote! This imports from ascii_art.py, so the
# app and the terminal program share the same logic.
from ascii_art import IMAGE_ERRORS, image_to_art, load_image

# The fewest and most characters wide the art can be (the slider's range).
MIN_WIDTH = 20
MAX_WIDTH = 250

# How many pixels wide a saved or copied PNG picture is, and the tallest
# it is allowed to be.
EXPORT_WIDTH = 2000
EXPORT_MAX_HEIGHT = 6000


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
            painter.drawText(self.rect(), Qt.AlignCenter, "Choose an image to begin")
            return

        # SPEED: Qt asks us to repaint often (for example when another
        # window moves across ours). Drawing thousands of characters each
        # time would be wasteful, so we draw the art once into an off-screen
        # picture (the "cache") and afterwards just stamp that picture on.
        if self.cache is None:
            # Modern Mac screens pack 2 real pixels into each "point" of
            # size. Drawing at that ratio keeps the text sharp.
            self.cache = self.render(self.width(), self.height(), self.devicePixelRatioF())
        painter.drawPixmap(0, 0, self.cache)

    def export_picture(self):
        """Return the art as a picture for saving or copying, on a black background."""
        # The art's size if drawn with the size-100 font.
        base_width = len(self.lines[0]) * self.base_cell_width
        base_height = len(self.lines) * self.base_cell_height

        # Normally the picture is EXPORT_WIDTH pixels wide, however big the
        # window is. Very tall, thin art is limited by height instead, so the
        # picture can never become enormous.
        scale = min(EXPORT_WIDTH / base_width, EXPORT_MAX_HEIGHT / base_height)
        width = max(1, round(base_width * scale))
        height = max(1, round(base_height * scale))
        return self.render(width, height, 1.0, background=QColor("black"))

    def render(self, width, height, ratio, background=None):
        """Draw the art into an off-screen picture and return it.

        `width` and `height` are the picture's size, and `ratio` is how many
        real pixels to use per unit of size. If `background` is given, the
        picture is filled with that colour behind the art; otherwise the
        gaps between characters are left see-through.
        """

        pixmap = QPixmap(QSize(width, height) * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)  # start completely see-through

        row_count = len(self.lines)
        column_count = len(self.lines[0])

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
        for y, line in enumerate(self.lines):  # enumerate gives (position, item)
            baseline = y * self.base_cell_height + self.base_ascent
            painter.drawText(QPointF(0, baseline), line)

        if self.color_image is not None:
            # SPEED: colour every character in ONE step. "SourceIn" means
            # "paint only where something is already drawn". So when we
            # stretch the tiny colour image (one pixel per character) over
            # the text, each white character soaks up the colour of its own
            # pixel, and the see-through gaps between them stay see-through.
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.drawImage(QRectF(0, 0, art_width, art_height), self.color_image)

        painter.resetTransform()  # back to normal, unscaled drawing

        if background is not None:
            # "DestinationOver" means "paint BEHIND what is already drawn",
            # so this fills in the see-through gaps without covering the art.
            painter.setCompositionMode(QPainter.CompositionMode_DestinationOver)
            painter.fillRect(QRectF(0, 0, width, height), background)

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
        self.image = None       # no image chosen yet
        self.image_name = ""    # the chosen file's name, without ".jpg" etc.

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

        # The buttons for getting the art OUT of the app. They start
        # switched off ("disabled") because there is nothing to export yet.
        self.copy_text_button = QPushButton("Copy Text")
        self.copy_image_button = QPushButton("Copy Image")
        self.save_png_button = QPushButton("Save PNG…")
        self.export_buttons = [self.copy_text_button, self.copy_image_button, self.save_png_button]
        for button in self.export_buttons:
            button.setEnabled(False)

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

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.art_view, 1)  # the 1 means "take all spare space"
        layout.addLayout(export_row)

        # -- Connect the controls to actions --
        # "connect" means: when this happens, call that function.
        self.choose_button.clicked.connect(self.choose_image)
        self.copy_text_button.clicked.connect(self.copy_text)
        self.copy_image_button.clicked.connect(self.copy_image)
        self.save_png_button.clicked.connect(self.choose_save_location)
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
        except IMAGE_ERRORS:
            # IMAGE_ERRORS covers "missing file", "not an image" and similar.
            # The previously chosen image (if any) stays on screen.
            QMessageBox.warning(self, "AsciiAnything", "That file couldn't be opened as an image.")
            return

        name = os.path.basename(path)                   # just the file's name
        self.image_name = os.path.splitext(name)[0]     # ...without ".jpg" etc.
        if len(name) > 30:
            name = name[:27] + "…"  # shorten long names so they don't crowd the controls
        self.file_label.setText(name)

        for button in self.export_buttons:
            button.setEnabled(True)  # now there is something to export
        self.refresh()

    def show_status(self, message):
        """Show a short confirmation message that disappears after 4 seconds."""
        self.status_label.setText(message)
        self.status_timer.start(4000)  # in milliseconds; restarts if already running

    def copy_text(self):
        """Put the art on the clipboard as plain text, ready to paste."""
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
        suggested = os.path.join(os.path.expanduser("~/Desktop"), self.image_name + "-ascii.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save as PNG", suggested, "PNG image (*.png)")
        if path:  # path is empty if the user pressed Cancel
            self.save_png(path)

    def save_png(self, path):
        """Save a picture of the art as a PNG file at `path`."""
        if not path.lower().endswith(".png"):
            path += ".png"
        # save() returns True if it worked and False if it didn't
        # (for example, if the folder can't be written to).
        if self.art_view.export_picture().save(path, "PNG"):
            self.show_status(f"Saved {os.path.basename(path)}")
        else:
            QMessageBox.warning(self, "AsciiAnything", "The picture couldn't be saved there.")

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
