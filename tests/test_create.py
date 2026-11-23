from threading import Event
from base64 import b64encode
from unittest import TestCase
from unittest.mock import Mock, patch

from PIL import Image

from thumb_finder import comfy, services, studio


def response(body=None, content=b"", status=200):
    return Mock(status_code=status, content=content, json=Mock(return_value=body))


class CreateTests(TestCase):
    def test_workflow_text_and_reference_modes_use_builtin_nodes(self):
        plain = comfy.workflow("Cinematic scene", [], 42)
        edited = comfy.workflow("Use both references", ["composition.png", "cast.png"], 43)
        self.assertEqual(plain["5"]["inputs"]["width"], 1024)
        self.assertEqual(plain["5"]["inputs"]["height"], 576)
        self.assertEqual(plain["7"]["inputs"]["conditioning"], ["4", 0])
        self.assertEqual(edited["7"]["inputs"]["conditioning"], ["65", 0])
        self.assertEqual(edited["65"]["inputs"]["conditioning"], ["62", 0])
        self.assertEqual(edited["12"]["class_type"], "PreviewImage")

    def test_submit_wait_and_fetch_preview(self):
        image = studio.image_bytes(Image.new("RGB", (40, 30), "purple"))
        session = Mock()
        stop = Mock()
        stop.wait.return_value = False
        session.request.side_effect = [
            response({}),
            response({"prompt_id": "job"}),
            response({"job": {"outputs": {"12": {"images": [{"filename": "draft.png", "type": "temp"}]}}}}),
            response(content=image),
        ]
        stop.is_set.return_value = False
        client = comfy.ComfyUI(comfy.DEFAULT_SERVER, stop, session)
        self.assertEqual(list(client.generate("A movie scene", [], 1)), [image])
        submit = session.request.call_args_list[1]
        self.assertEqual(submit.args[0], "POST")
        self.assertTrue(submit.args[1].endswith("/prompt"))
        self.assertIn("A movie scene", submit.kwargs["json"]["prompt"]["4"]["inputs"]["text"])
        self.assertEqual(session.request.call_args.kwargs["params"]["filename"], "draft.png")

    def test_missing_weights_report_actionable_message(self):
        session = Mock()
        session.request.return_value = response({"node_errors": {"1": {"errors": [
            {"details": "Missing diffusion model"}
        ]}}}, status=400)
        client = comfy.ComfyUI(comfy.DEFAULT_SERVER, Event(), session)
        with self.assertRaisesRegex(ValueError, "Missing diffusion model"):
            client.render("Test", [])

    @patch("thumb_finder.services.requests.post")
    def test_cloud_generation_decodes_api_image(self, post):
        data = studio.image_bytes(Image.new("RGB", (40, 30), "purple"))
        post.return_value = response({"result": {"image": b64encode(data).decode()}})
        post.return_value.headers = {"Content-Type": "application/json"}
        self.assertEqual(services.cloud_image("a" * 32, "token", "Action scene", [("source", data)]), data)
        fields = post.call_args.kwargs["files"]
        self.assertEqual(fields["prompt"], (None, "Action scene Attached image 1 is the source."))
        self.assertEqual(fields["width"], (None, "512"))
        self.assertEqual(fields["height"], (None, "288"))
        self.assertEqual(fields["input_image_0"], ("reference-1.png", data, "image/png"))
        self.assertTrue(post.call_args.args[0].endswith("/flux-2-klein-4b"))
        self.assertEqual(services.cloud_image("a" * 32, "token", "Action scene", model="9b"), data)
        self.assertTrue(post.call_args.args[0].endswith("/flux-2-klein-9b"))
        self.assertEqual(post.call_args.kwargs["files"]["width"], (None, "1024"))

    def test_rectangular_and_brush_masks_keep_marked_pixels_only(self):
        for selection in (
            ("box", [(0.55, 0.55), (0.45, 0.45)], 0.04),
            ("brush", [(0.45, 0.45), (0.55, 0.55)], 0.05),
        ):
            mask = services.mask_image((100, 100), *selection)
            self.assertEqual(mask.getpixel((50, 50)), 255)
            self.assertEqual(mask.getpixel((10, 10)), 0)
