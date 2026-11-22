import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from thumb_finder.app import Window


def smoke_test(app, window, marker):
    from PIL import Image
    from thumb_finder.studio import image_bytes

    if not window.isVisible() or window.windowIcon().pixmap(64, 64).isNull():
        raise RuntimeError("The window or its icon failed to load.")
    window.show_page(1)
    window.show_page(2)
    window.install_source(0, image_bytes(Image.new("RGB", (320, 180), "#6853d8")), "Smoke test")

    def check_preview():
        if window.preview.pixmap.isNull():
            timer.start(50)
            return
        timer.stop()
        marker.write_text(app.platformName(), encoding="utf-8")
        app.exit(0)

    timer = QTimer(window, singleShot=True)
    timer.timeout.connect(check_preview)
    timer.start(50)
    QTimer.singleShot(10000, lambda: app.exit(1))


def main():
    smoke_marker = Path(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test" else None
    app = QApplication(sys.argv[:1] if smoke_marker else sys.argv)
    app.setOrganizationName("ThumbFinderSmoke" if smoke_marker else "ThumbFinder")
    app.setApplicationName("Thumb Finder")
    window = Window()
    window.show()
    if smoke_marker:
        smoke_test(app, window, smoke_marker)
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
