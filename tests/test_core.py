from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image

from thumb_finder import studio
from thumb_finder.youtube import Video, YouTube, distance, duration, signature, thumbnail, translate_query, video_id


class SearchTests(TestCase):
    @patch("thumb_finder.youtube.requests.get")
    def test_query_translation_uses_brazilian_portuguese(self, get):
        get.return_value.json.return_value = {"responseStatus": 200, "responseData": {"translatedText": "filme de ação"}}
        self.assertEqual(translate_query("action movie", "en"), "filme de ação")
        self.assertEqual(get.call_args.kwargs["params"]["langpair"], "en|pt-BR")

    def test_argentina_search_orders_popular_channel_uploads_by_views(self):
        client = YouTube(["test"])
        with patch.object(client, "request", return_value={"items": []}) as request:
            client.page("aventura", 40, "Action", region="AR", language="pt-BR", popular=True)
            self.assertEqual(request.call_args.kwargs["q"], "aventura ação filme completo")
            self.assertEqual(request.call_args.kwargs["regionCode"], "AR")
            self.assertEqual(request.call_args.kwargs["relevanceLanguage"], "pt")
            self.assertEqual(request.call_args.kwargs["order"], "viewCount")
            client.page("", 40, "", channel_id="movie-channel", region="AR", language="pt-BR")
            self.assertEqual(request.call_args.kwargs["channelId"], "movie-channel")
            self.assertEqual(request.call_args.kwargs["order"], "viewCount")
            self.assertNotIn("q", request.call_args.kwargs)
            client.page("aventura", 40, "Action", region="ES", language="es")
            self.assertEqual(request.call_args.kwargs["q"], "aventura acción película completa")
            self.assertEqual(request.call_args.kwargs["regionCode"], "ES")

    def test_video_url_and_duration(self):
        expected = "dQw4w9WgXcQ"
        for link in (f"youtu.be/{expected}", f"https://www.youtube.com/watch?v={expected}",
                     f"https://www.youtube.com/live/{expected}"):
            self.assertEqual(video_id(link), expected)
        self.assertIsNone(video_id(f"https://notyoutube.com/watch?v={expected}"))
        self.assertEqual(duration("PT1H20M41S"), 4841)

    @patch("thumb_finder.youtube.requests.get")
    def test_quota_failover_is_reused(self, get):
        denied = Mock(ok=False, status_code=403)
        denied.json.return_value = {"error": {"errors": [{"reason": "quotaExceeded"}]}}
        accepted = Mock(ok=True)
        accepted.json.return_value = {"items": []}
        get.side_effect = [denied, accepted, accepted]
        client = YouTube(["key-one", "key-two"])
        client.request("search")
        client.request("videos")
        self.assertEqual([call.kwargs["params"]["key"] for call in get.call_args_list],
                         ["key-one", "key-two", "key-two"])

    @patch("thumb_finder.youtube.requests.get")
    def test_other_forbidden_response_does_not_exhaust_key(self, get):
        get.return_value = Mock(ok=False, status_code=403)
        get.return_value.json.return_value = {"error": {"errors": [{"reason": "forbidden"}]}}
        client = YouTube(["key-one", "key-two"])
        with self.assertRaises(ValueError):
            client.request("search")
        self.assertFalse(client.exhausted)
        self.assertEqual(get.call_count, 1)

    @patch("thumb_finder.youtube.requests.get")
    def test_thumbnail_falls_back_and_preserves_bytes(self, get):
        data = studio.image_bytes(Image.new("RGB", (28, 28), "red"))
        get.side_effect = [Mock(ok=False), Mock(ok=True, content=data)]
        video = Video("id", "Title", "Channel", 17, "2026-01-01", 3000,
                      {"maxres": {"url": "maximum"}, "standard": {"url": "standard"}})
        self.assertEqual(thumbnail(video), data)
        self.assertEqual([call.args[0] for call in get.call_args_list], ["maximum", "standard"])
        self.assertEqual(distance(signature(data), signature(data)), 0)


class StudioTests(TestCase):
    def test_enhance_trims_borders_and_keeps_dark_frames(self):
        image = Image.new("RGB", (640, 360), "black")
        image.paste((181, 130, 76), (46, 28, 594, 332))
        trimmed = studio.trim_black_borders(image)
        self.assertLess(trimmed.width, 570)
        self.assertLess(trimmed.height, 320)
        self.assertEqual(trimmed.getpixel((trimmed.width // 2, 3)), (181, 130, 76))
        dark = Image.new("RGB", (640, 360), (8, 9, 10))
        self.assertEqual(studio.trim_black_borders(dark).size, dark.size)
        enhanced_input = studio.enhancement_input(studio.image_bytes(image), studio.Edit())
        self.assertEqual(enhanced_input.size, (1280, 720))
        self.assertGreater(enhanced_input.getpixel((640, 6))[0], 100)
    def test_independent_candidates_and_repeated_export(self):
        sources = [studio.image_bytes(Image.new("RGB", (550, 850), color))
                   for color in ("red", "green", "blue")]
        candidates = [studio.Candidate(source, f"{label}.png") for source, label in zip(sources, "ABC")]
        candidates[0].change(studio.Edit(text="Movie", quality=88, zoom=120, crop=100, vertical=100))
        candidates[0].step(True)
        self.assertEqual(candidates[0].edit.text, "")
        candidates[0].step(False)
        self.assertEqual(candidates[0].edit.text, "Movie")
        self.assertEqual(candidates[1].edit.quality, 94)
        with TemporaryDirectory() as directory:
            first = studio.export(candidates, directory, "A Movie")
            second = studio.export(candidates, directory, "A Movie")
            self.assertNotEqual(first, second)
            self.assertEqual(set(path.name for path in Path(first).iterdir()),
                             {"A.jpg", "B.jpg", "C.jpg", "manifest.csv"})
            for index, letter in enumerate("ABC"):
                with Image.open(first / f"{letter}.jpg") as image:
                    self.assertEqual(image.size, studio.SIZE)
                    self.assertEqual(image.format, "JPEG")
                    color = image.getpixel((10, 10))
                    self.assertEqual(color.index(max(color)), index)
