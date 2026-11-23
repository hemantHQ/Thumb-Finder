from hashlib import sha256
from pathlib import Path
from stat import S_IFLNK
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch
from zipfile import ZipFile, ZipInfo

from thumb_finder import updater

REPO = "https://github.com/hemantHQ/Thumb-Finder"


class UpdateTests(TestCase):
    @patch("thumb_finder.updater.requests.get")
    def test_only_newer_release_with_matching_asset_can_download(self, get):
        tag = "v1.0-build-12"
        name = f"Thumb-Finder-{tag}-macOS-arm64.zip"
        url = f"{REPO}/releases/download/{tag}/{name}"
        asset = {"name": name, "browser_download_url": url, "size": 23,
                 "state": "uploaded", "digest": "sha256:" + "a" * 64}
        get.return_value = Mock(status_code=200, json=Mock(return_value={"tag_name": tag, "assets": [asset]}))
        self.assertEqual(updater.check(REPO, 9), updater.Release(tag, url, "a" * 64, 23))
        self.assertIsNone(updater.check(REPO, 12))
        self.assertIsNone(updater.check(REPO, 13))
        asset["digest"] = None
        self.assertEqual(updater.check(REPO, 9).url, "")

    @patch("thumb_finder.updater.requests.get")
    def test_download_verifies_content_and_rejects_untrusted_redirect(self, get):
        release = updater.Release("v1.0-build-12", REPO + "/asset", sha256(b"file").hexdigest(), 4)
        reply = Mock(status_code=200, is_redirect=False)
        reply.iter_content.return_value = [b"fi", b"le"]
        get.return_value.__enter__.return_value = reply
        with TemporaryDirectory() as directory:
            path = Path(directory) / "update.zip"
            updater.fetch(release, path)
            self.assertEqual(path.read_bytes(), b"file")
            reply.iter_content.return_value = [b"fake"]
            with self.assertRaisesRegex(ValueError, "integrity"):
                updater.fetch(release, path)
            reply.is_redirect = True
            reply.headers = {"Location": "https://example.net/update.zip"}
            with self.assertRaisesRegex(ValueError, "unexpected address"):
                updater.fetch(release, path)

    def test_bundle_zip_rejects_escaping_links_and_paths(self):
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "update.zip"
            root = updater.BUNDLE
            link = ZipInfo(root + "/Contents/Frameworks/Info.plist")
            link.create_system = 3
            link.external_attr = (S_IFLNK | 0o777) << 16
            for target in ("../Info.plist", "../../../../outside"):
                with ZipFile(archive, "w") as file:
                    file.writestr(root + "/Contents/Info.plist", b"info")
                    file.writestr(link, target)
                if target == "../Info.plist":
                    updater.check_archive(archive)
                else:
                    with self.assertRaisesRegex(ValueError, "outside"):
                        updater.check_archive(archive)
            with ZipFile(archive, "w") as file:
                file.writestr(root + "/../payload", b"data")
            with self.assertRaisesRegex(ValueError, "unexpected path"):
                updater.check_archive(archive)
