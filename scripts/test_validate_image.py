"""Regression tests using the same fwtool binary that builds the firmware."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

FWTOOL = str(Path(sys.argv.pop(1)).resolve())
VALIDATOR = Path(__file__).with_name("validate-image.sh")


class ImageValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root / "firmware.img.gz"
        self.metadata = self.root / "input.json"
        self.output = self.root / "output.json"
        self.metadata.write_text(json.dumps({"supported_devices": ["x86_64"]}))
        self.payload = gzip.compress(os.urandom(128 * 1024))
        self.image.write_bytes(self.payload)

    def append_metadata(self):
        subprocess.run([FWTOOL, "-I", str(self.metadata), str(self.image)], check=True)

    def append_signature(self):
        # fwtool treats the signature as opaque bytes; these tests check trailer
        # framing/CRC, not a cryptographic signature's authenticity.
        signature = self.root / "signature"
        signature.write_bytes(b"signature trailer fixture")
        subprocess.run([FWTOOL, "-S", str(signature), str(self.image)], check=True)

    def validate(self, expected_success):
        before = hashlib.sha256(self.image.read_bytes()).digest()
        result = subprocess.run(
            ["bash", str(VALIDATOR), FWTOOL, str(self.image), str(self.output)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, expected_success, result.stderr)
        self.assertEqual(hashlib.sha256(self.image.read_bytes()).digest(), before)

    def test_valid_metadata_is_accepted(self):
        self.append_metadata()
        # Reproduce the original failure before testing the fixed validator.
        old = subprocess.run(["gzip", "-t", str(self.image)], capture_output=True)
        self.assertEqual(old.returncode, 2)
        self.validate(True)
        self.assertEqual(json.loads(self.output.read_text())["metadata"], json.loads(self.metadata.read_text()))

    def test_plain_gzip_is_accepted(self):
        self.validate(True)

    def test_signature_only_x86_image_is_accepted(self):
        self.append_signature()
        self.validate(True)
        report = json.loads(self.output.read_text())
        self.assertTrue(report["signature_present"])
        self.assertIsNone(report["metadata"])

    def test_metadata_and_signature_are_accepted(self):
        self.append_metadata()
        self.append_signature()
        self.validate(True)

    def test_small_signed_image_is_accepted(self):
        self.image.write_bytes(gzip.compress(b"small fixture"))
        self.append_signature()
        self.validate(True)

    def test_bad_gzip_crc_with_signature_is_rejected(self):
        broken = bytearray(self.payload)
        broken[-8] ^= 1
        self.image.write_bytes(broken)
        self.append_signature()
        self.validate(False)

    def test_damaged_signature_trailer_is_rejected(self):
        self.append_signature()
        broken = bytearray(self.image.read_bytes())
        broken[-17] ^= 1
        self.image.write_bytes(broken)
        self.validate(False)

    def test_truncated_signature_trailer_is_rejected(self):
        self.append_signature()
        self.image.write_bytes(self.image.read_bytes()[:-5])
        self.validate(False)

    def test_garbage_before_valid_signature_is_rejected(self):
        self.image.write_bytes(self.payload + b"garbage")
        self.append_signature()
        self.validate(False)

    def test_duplicate_signature_is_rejected(self):
        self.append_signature()
        self.append_signature()
        self.validate(False)

    def test_truncated_gzip_with_valid_metadata_is_rejected(self):
        self.image.write_bytes(self.payload[:-8])
        self.append_metadata()
        self.validate(False)

    def test_bad_gzip_crc_with_valid_metadata_is_rejected(self):
        broken = bytearray(self.payload)
        broken[-8] ^= 1
        self.image.write_bytes(broken)
        self.append_metadata()
        self.validate(False)

    def test_damaged_fwtool_crc_is_rejected(self):
        self.append_metadata()
        broken = bytearray(self.image.read_bytes())
        broken[50] ^= 1
        self.image.write_bytes(broken)
        self.validate(False)

    def test_unknown_trailing_data_is_rejected(self):
        self.append_metadata()
        with self.image.open("ab") as image:
            image.write(b"unexpected trailing data")
        self.validate(False)

    def test_invalid_metadata_json_is_rejected(self):
        self.metadata.write_text("invalid JSON")
        self.append_metadata()
        self.validate(False)


if __name__ == "__main__":
    unittest.main()
