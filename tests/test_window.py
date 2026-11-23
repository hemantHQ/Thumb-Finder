import os
from time import monotonic
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QSettings, QStandardPaths, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from thumb_finder.app import Window
from thumb_finder.studio import image_bytes
from thumb_finder.youtube import Channel, Video, YouTube


class WindowTests(TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication([])
        self.app.setOrganizationName("ThumbFinderTests")
        self.app.setApplicationName("UI smoke")
        QSettings().clear()
        self.directory = TemporaryDirectory()
        with patch.object(QStandardPaths, "writableLocation", return_value=self.directory.name):
            self.window = Window()
        self.window.show()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.directory.cleanup()

    def wait_for(self, condition):
        deadline = monotonic() + 4
        while not condition() and monotonic() < deadline:
            QTest.qWait(15)
        self.assertTrue(condition())

    def test_search_cards_and_independent_editor_previews(self):
        data = image_bytes(Image.new("RGB", (360, 220), "purple"))
        first = Video("one", "First", "Channel", 30, "2026-01-01", 2900, {})
        second = Video("two", "Second", "Channel", 60, "2026-01-01", 3200, {})
        self.window.youtube = YouTube(["mock"])
        self.window.query.setText("movie")
        with patch.object(YouTube, "page", return_value=([first, second], None)), \
                patch("thumb_finder.app.thumbnail", return_value=data):
            self.window.start_search()
            self.wait_for(lambda: len(self.window.cards) == 2)
            self.assertIs(self.window.results_grid.itemAtPosition(0, 0).widget(),
                          self.window.cards[second.id])
            self.wait_for(lambda: all(not card.layout().itemAt(0).widget().pixmap.isNull()
                                      for card in self.window.cards.values()))
        self.window.show_page(1)
        self.assertEqual(self.window.pages.currentIndex(), 1)
        self.window.show_page(2)
        for slot, color in enumerate(("red", "green", "blue")):
            self.window.install_source(slot, image_bytes(Image.new("RGB", (360, 220), color)), color)
        self.wait_for(lambda: all(not image.pixmap.isNull() for image in self.window.slot_images))
        self.assertTrue(self.window.export_button.isEnabled())
        self.window.overlay.setText("Candidate C")
        self.window.select_slot(0)
        self.assertEqual(self.window.overlay.text(), "")
        self.window.select_slot(2)
        self.assertEqual(self.window.overlay.text(), "Candidate C")
        self.window.before.setChecked(True)
        self.window.small.setChecked(True)
        self.assertEqual(self.window.preview.maximumWidth(), 240)
        previous = self.window.dark
        self.window.toggle_theme()
        self.assertNotEqual(self.window.dark, previous)

    def test_create_renders_draft_and_sends_it_to_editor(self):
        from pathlib import Path

        self.window.show_page(1)
        self.assertFalse(self.window.windowIcon().pixmap(42, 42).isNull())
        self.window.generate_images()
        self.assertIn("Enter a prompt", self.window.create_status.text())
        self.window.create_prompt.setPlainText("A tense movie scene")
        data = image_bytes(Image.new("RGB", (360, 220), "purple"))
        source = Path(self.directory.name) / "reference.png"
        source.write_bytes(data)
        self.assertFalse(self.window.create_reference_buttons[0].isHidden())
        self.window.set_create_reference(0, str(source))
        with patch("thumb_finder.services.cloud_image", return_value=data) as generate:
            self.window.generate_images()
            self.wait_for(lambda: len(self.window.create_outputs) == 1)
            self.wait_for(self.window.generate_button.isEnabled)
        self.assertIn("A tense movie scene", generate.call_args.args[2])
        self.assertEqual(generate.call_args.args[3][0][0], "source image to edit")
        self.assertEqual(self.window.create_history.count(), 2)
        self.assertFalse(self.window.draft_images[0].pixmap.isNull())
        self.window.create_history.setCurrentIndex(0)
        self.window.display_drafts([])
        self.window.create_history.setCurrentIndex(1)
        self.wait_for(lambda: len(self.window.create_outputs) == 1)
        self.window.send_draft(0)
        self.assertEqual(self.window.pages.currentIndex(), 2)
        self.assertEqual(self.window.candidates[0].source, data)
        self.wait_for(lambda: not self.window.preview.pixmap.isNull())

    def test_argentina_channel_search_opens_popular_videos(self):
        data = image_bytes(Image.new("RGB", (360, 220), "purple"))
        channel = Channel("channel-id", "Cinema", 600, {})
        video = Video("video-id", "A movie", "Cinema", 50, "2026-01-01", 3600, {}, channel.id)
        self.window.youtube = YouTube(["mock"])
        self.window.search_market.setCurrentIndex(self.window.search_market.findData("AR"))
        self.window.search_language.setCurrentIndex(self.window.search_language.findData("pt-BR"))
        self.window.search_source.setCurrentIndex(self.window.search_source.findData("en"))
        self.window.search_mode.setCurrentIndex(1)
        self.window.query.setText("action movie")
        with patch.object(YouTube, "page", return_value=([video], None)) as page, \
                patch.object(YouTube, "channels", return_value=[channel]), \
                patch("thumb_finder.app.translate_query", return_value="filme de ação"), \
                patch("thumb_finder.app.thumbnail", return_value=data):
            self.window.start_search()
            self.wait_for(lambda: channel.id in self.window.cards)
            self.assertEqual(page.call_args.args[0], "filme de ação")
            actions = self.window.cards[channel.id].layout()
            actions.itemAt(actions.count() - 1).layout().itemAt(0).widget().click()
            self.wait_for(lambda: video.id in self.window.cards)
            self.assertEqual(page.call_args.kwargs["channel_id"], channel.id)
            self.assertEqual(page.call_args.kwargs["region"], "AR")
            self.assertEqual(page.call_args.kwargs["language"], "pt-BR")

    def test_create_keeps_finished_draft_when_a_later_request_fails(self):
        self.window.show_page(1)
        self.window.create_prompt.setPlainText("Movie action scene")
        self.window.create_count.setCurrentIndex(1)
        data = image_bytes(Image.new("RGB", (250, 250), "orange"))
        with patch("thumb_finder.services.cloud_image", side_effect=[data, ValueError("Quota reached")]):
            self.window.generate_images()
            self.wait_for(self.window.generate_button.isEnabled)
        self.assertEqual(self.window.create_status.text(), "Quota reached")
        self.assertEqual(len(self.window.create_outputs), 1)
        self.assertEqual(self.window.draft_images[0].pixmap.size().toTuple(), (640, 360))
        self.assertTrue(self.window.reuse_prompt.isEnabled())
        self.window.create_prompt.clear()
        self.window.reuse_prompt.click()
        self.assertEqual(self.window.create_prompt.toPlainText(), "Movie action scene")

    def test_offline_edit_undo_and_enhanced_export(self):
        from pathlib import Path
        from thumb_finder import studio

        self.window.show_page(2)
        data = image_bytes(Image.new("RGB", (360, 220), "red"))
        self.window.install_source(0, data, "test.png")
        repaired = image_bytes(Image.new("RGB", studio.SIZE, "green"))
        enhanced = image_bytes(Image.new("RGB", studio.FHD, "blue"))
        selection = ("box", [(0.1, 0.1), (0.2, 0.2)], 0.04)
        with patch("thumb_finder.offline.process", side_effect=[repaired, enhanced]) as engine:
            self.window.remove_region(selection)
            self.assertFalse(self.window.preview.mask_preview.isNull())
            self.window.apply_selection()
            self.wait_for(lambda: not self.window.offline_busy)
            self.assertEqual(engine.call_args.args[2], (selection,))
            self.assertEqual(self.window.candidates[0].edit.repaired, repaired)
            self.assertTrue(self.window.preview.mask_preview.isNull())
            self.window.run_offline_edit(None)
            self.wait_for(lambda: self.window.candidates[0].edit.enhanced)
        self.window.history(True)
        self.assertFalse(self.window.candidates[0].edit.enhanced)
        self.assertEqual(self.window.candidates[0].edit.repaired, repaired)
        self.window.history(False)
        candidates = self.window.candidates
        candidates[1] = studio.Candidate(data, "second.png")
        candidates[2] = studio.Candidate(data, "third.png")
        output = studio.export(candidates, Path(self.directory.name), "Example")
        with Image.open(output / "A.jpg") as image:
            self.assertEqual(image.size, (1920, 1080))
        with Image.open(output / "B.jpg") as image:
            self.assertEqual(image.size, (1280, 720))

    def test_first_use_prompts_and_remove_arms_after_install(self):
        from thumb_finder import offline

        self.window.show_page(2)
        data = image_bytes(Image.new("RGB", (360, 220), "red"))
        self.window.install_source(0, data, "test.png")

        def answer(text):
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QMessageBox):
                next(widget for widget in dialog.buttons() if widget.text().replace("&", "") == text).click()

        def install(root, tool, report, stop):
            (root / offline.RUNTIME).mkdir(parents=True)
            (root / offline.RUNTIME / ".ready").touch()
            offline.model_path(root, tool).touch()

        with patch("thumb_finder.offline.install", side_effect=install) as setup:
            QTimer.singleShot(0, lambda: answer("Cancel"))
            self.window.remove_button.click()
            setup.assert_not_called()
            self.assertTrue(self.window.remove_mode.isHidden())
            QTimer.singleShot(0, lambda: answer("Download"))
            self.window.remove_button.click()
            self.wait_for(lambda: self.window.preview.selectable)
            self.assertEqual(self.window.remove_mode.currentText(), "Rectangle")
            self.assertFalse(self.window.remove_mode.isHidden())
            self.window.remove_mode.setCurrentIndex(1)
            self.assertEqual(self.window.preview.selection_mode, "brush")
            self.assertEqual(setup.call_count, 1)

    def test_download_is_available_for_one_candidate(self):
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog

        self.window.show_page(2)
        self.assertFalse(self.window.download_button.isEnabled())
        source = image_bytes(Image.new("RGB", (360, 220), "red"))
        self.window.install_source(1, source, "test.png")
        self.assertTrue(self.window.download_button.isEnabled())
        self.assertEqual(self.window.download_button.text(), "Download B")
        self.assertFalse(self.window.export_button.isEnabled())
        path = Path(self.directory.name) / "Edited B.jpg"
        with patch.object(QFileDialog, "exec", return_value=True), \
                patch.object(QFileDialog, "selectedFiles", return_value=[str(path)]):
            self.window.download_button.click()
            self.wait_for(path.exists)
        with Image.open(path) as image:
            self.assertEqual((image.format, image.size), ("JPEG", (1280, 720)))
