import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ota_privado as ota


class OTASafetyTest(unittest.TestCase):
    def test_preflight_never_calls_upload(self):
        seen = []

        class Response:
            def __init__(self, data):
                self.data = data

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, *args):
                return self.data

        class Opener:
            def open(self, request, **kwargs):
                url = request if isinstance(request, str) else request.full_url
                seen.append(url)
                html = b"<table><tr><td>Chip</td><td>ESP32</td></tr><tr><td>Running</td><td>ota_0</td></tr><tr><td>Version</td><td>2.4.22</td></tr></table>/api/ota-upload"
                return Response(html)

        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            (Path(tmp) / "resultados").mkdir()
            (Path(tmp) / "resultados" / "acceso-red-v0.4.0.json").write_text(
                json.dumps({"host": "192.168.1.50"})
            )
            with (
                patch.object(ota, "ROOT", Path(tmp)),
                patch.object(ota, "REPORT", report),
                patch.object(
                    ota, "args", SimpleNamespace(image=None, authorized_sha256=None), create=True
                ),
                patch.object(ota, "root", SimpleNamespace(after=lambda _, cb: None), create=True),
                patch.object(ota.urllib.request, "build_opener", return_value=Opener()),
            ):
                ota.operation("FAKE-TEST-PASSWORD")
            outcome = json.loads(report.read_text())
            self.assertEqual(outcome["state"], "preflight_ok")
            self.assertFalse(outcome["flash_written"])
            self.assertNotIn("FAKE-TEST-PASSWORD", report.read_text())
            self.assertFalse(any("/api/ota-upload" in url for url in seen))

    def test_bootloader_is_not_an_ota_application(self):
        from esptool.bin_image import ESP32FirmwareImage, ImageSegment

        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "bootloader.bin"
            image = ESP32FirmwareImage()
            image.segments = [ImageSegment(0x3FFF0030, bytes(512))]
            image.segments[0].name = "synthetic_bootloader"
            image.save(str(binary))
            with self.assertRaises(ValueError):
                ota.inspect_image(binary)


if __name__ == "__main__":
    unittest.main()
