from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image
from thumb_finder import offline, offline_worker, services


class OfflineSetupTests(TestCase):
    def test_repair_maps_separate_marks_and_preserves_surroundings(self):
        image = Image.new("RGB", (400, 225), "red")
        selections = (
            ("box", [(0, 0.30), (0.05, 0.44)], 0.04),
            ("brush", [(0.90, 0.60), (0.97, 0.60)], 0.03),
            ("brush", [(0.02, 0.41)], 0.03),
        )
        masks = services.repair_masks(image.size, selections)
        self.assertEqual(len(masks), 2)

        def reconstruct(context, selection):
            self.assertEqual(context.size, (512, 512))
            self.assertEqual(selection.size, (512, 512))
            return Image.new("RGB", context.size, "blue")

        result = image
        for mask in masks:
            result = offline_worker.repair_region(result, mask, reconstruct)
        for point in ((0, 80), (375, 135)):
            self.assertEqual(result.getpixel(point), (0, 0, 255))
        for point in ((200, 80), (100, 160)):
            self.assertEqual(result.getpixel(point), (255, 0, 0))

    def test_model_install_reuses_runtime_and_keeps_downloads_independent(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            messages = []

            def download(url, destination, *args):
                destination.write_bytes(b"synthetic model")

            with patch.object(offline, "FROZEN", False), \
                    patch.object(offline, "run_command") as command, \
                    patch.object(offline, "download", side_effect=download) as transfer:
                offline.install(root, "remove", messages.append, Event())
                self.assertTrue(offline.ready(root, "remove"))
                self.assertFalse(offline.ready(root, "enhance"))
                offline.install(root, "remove", messages.append, Event())
                offline.install(root, "enhance", messages.append, Event())
                self.assertTrue(offline.ready(root, "enhance"))
                self.assertEqual(transfer.call_count, 2)
                self.assertEqual(command.call_count, 2)
                self.assertEqual(list(root.glob("setup-*")), [])

    @patch("thumb_finder.offline.requests.get")
    def test_download_rejects_wrong_digest(self, get):
        response = Mock(headers={"Content-Length": "3"})
        response.iter_content.return_value = [b"abc"]
        get.return_value.__enter__.return_value = response
        with TemporaryDirectory() as directory:
            file = Path(directory) / "model"
            with self.assertRaisesRegex(ValueError, "integrity"):
                offline.download("https://example.org/model", file, "0" * 64, lambda _: None,
                                 Event(), "the model", 10)
            offline.download("https://example.org/model", file, sha256(b"abc").hexdigest(), lambda _: None,
                             Event(), "the model", 10)
            self.assertEqual(file.read_bytes(), b"abc")
