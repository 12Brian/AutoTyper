"""Generate the application icon set for all three platforms.

Run this once after cloning (``python assets/make_icon.py``) to (re)create the
PNG/ICO/ICNS files. It needs only Qt (already a runtime dependency), so no extra
tooling is required.

The mark is deliberately simple - a rounded keycap with a typing caret - so it
stays legible at 16 px in a taskbar or menu bar.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QApplication

ASSETS = Path(__file__).resolve().parent

#: Rendered at 1024 px and downsampled so every icon size looks clean.
CANVAS = 1024


def render_icon(size: int = CANVAS) -> QImage:
    """Draw the AutoTyper mark at ``size`` pixels.

    Args:
        size: Edge length in pixels (square).

    Returns:
        A transparent QImage with the mark centred.
    """
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    margin = size * 0.055
    body = QRectF(margin, margin, size - 2 * margin, size - 2 * margin)
    radius = body.width() * 0.235

    gradient = QLinearGradient(body.topLeft(), body.bottomRight())
    gradient.setColorAt(0.0, QColor("#5B6CFF"))
    gradient.setColorAt(0.55, QColor("#4F5FF0"))
    gradient.setColorAt(1.0, QColor("#3543C4"))
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(body, radius, radius)

    # Inner keycap face for depth.
    inset = body.adjusted(size * 0.085, size * 0.085, -size * 0.085, -size * 0.085)
    painter.setBrush(QColor(255, 255, 255, 26))
    painter.setPen(QPen(QColor(255, 255, 255, 46), max(1.0, size * 0.008)))
    painter.drawRoundedRect(inset, radius * 0.62, radius * 0.62)

    # Caret plus two text rules: instantly reads as "typing".
    caret_width = size * 0.072
    caret_height = size * 0.30
    caret_x = size * 0.5 - caret_width / 2
    caret_y = size * 0.245
    painter.setBrush(QColor("#FFFFFF"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(
        QRectF(caret_x, caret_y, caret_width, caret_height),
        caret_width / 2,
        caret_width / 2,
    )

    rule_height = size * 0.058
    for index, (width_fraction, y_fraction) in enumerate(
        ((0.46, 0.625), (0.30, 0.725))
    ):
        width = size * width_fraction
        rect = QRectF(
            size * 0.5 - width / 2,
            size * y_fraction,
            width,
            rule_height,
        )
        painter.setBrush(QColor(255, 255, 255, 235 if index == 0 else 150))
        painter.drawRoundedRect(rect, rule_height / 2, rule_height / 2)

    painter.end()
    return image


def scaled(image: QImage, size: int) -> QImage:
    """Return a smoothly downsampled copy of ``image``."""
    return image.scaled(
        size,
        size,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def write_png(image: QImage, path: Path) -> None:
    """Save ``image`` as PNG.

    Raises:
        RuntimeError: If Qt cannot write the file.
    """
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"Could not write {path}")


def main() -> int:
    """Generate every icon file and report what was written."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    assert app is not None  # noqa: S101 - defensive, keeps type checkers happy

    print("Rendering icon…")
    base = render_icon(CANVAS)

    png_path = ASSETS / "autotyper.png"
    write_png(base, png_path)
    print(f"  {png_path.name} ({CANVAS}x{CANVAS})")

    for size in (16, 32, 48, 64, 128, 256, 512):
        target = ASSETS / f"autotyper-{size}.png"
        write_png(scaled(base, size), target)
        print(f"  {target.name}")

    # Windows: Qt writes a single-size .ico; 256 px covers the modern shell and
    # Windows rescales it for the small variants.
    ico_path = ASSETS / "autotyper.ico"
    if scaled(base, 256).save(str(ico_path), "ICO"):
        print(f"  {ico_path.name}")
    else:  # pragma: no cover - platform dependent
        print("  could not write .ico; the .png files are still used by the app")

    # macOS: fall back to a 512 px PNG when the icns writer is unavailable.
    icns_path = ASSETS / "autotyper.icns"
    if scaled(base, 512).save(str(icns_path), "ICNS"):
        print(f"  {icns_path.name}")
    else:  # pragma: no cover - platform dependent
        print("  could not write .icns; PyInstaller will use autotyper.png")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
