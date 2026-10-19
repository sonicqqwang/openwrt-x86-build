"""Check fwtool trailer CRCs and gzip integrity without modifying the firmware.

x86 generic has no SUPPORTED_DEVICES, so append-metadata may append only a
signature. A signature trailer's CRC is an integrity check, not proof of trust.
Use fwtool -t on a temporary copy: -T can emit damaged output when a requested
metadata chunk does not exist. Never suppress a failed extraction or gzip test.
"""
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


def validate(fwtool, image, report):
    fwtool = str(Path(fwtool).resolve())
    report = Path(report)
    report.unlink(missing_ok=True)
    chunks = []
    metadata = None
    with tempfile.TemporaryDirectory(prefix="firmware-validation-") as directory:
        work = Path(directory) / "payload.img.gz"
        shutil.copyfile(image, work)
        while work.stat().st_size >= 16:
            with work.open("rb") as stream:
                stream.seek(-16, 2)
                magic, crc, kind, size = struct.unpack(">IIB3xI", stream.read(16))
            if magic != 0x46577830:
                break  # gzip -t below still rejects unknown trailing garbage.
            if kind not in (0, 1) or kind in chunks:
                raise ValueError("Unknown or duplicate fwtool trailer")
            before = work.stat().st_size
            if not 16 < size <= min(before, 32768):
                raise ValueError("Invalid fwtool trailer length")
            extracted = Path(directory) / f"chunk-{kind}"
            subprocess.run(
                [fwtool, "-s" if kind == 0 else "-i", str(extracted), "-t", str(work)],
                check=True,
            )
            if work.stat().st_size != before - size:
                raise ValueError("Unexpected size after removing fwtool trailer")
            chunks.append(kind)
            if kind == 1:
                metadata = json.loads(extracted.read_text())
                if not isinstance(metadata, dict):
                    raise ValueError("Firmware metadata must be a JSON object")
        subprocess.run(["gzip", "-t", str(work)], check=True)
    result = {
        "gzip_integrity": "passed",
        "trailer_crc_checks": "passed" if chunks else "not_applicable",
        "signature_present": 0 in chunks,
        "signature_authenticity_verified": False,
        "metadata": metadata,
    }
    report.write_text(json.dumps(result, indent=2) + "\n")
    print("Firmware gzip and trailer integrity checks passed.")


if __name__ == "__main__":
    try:
        validate(*sys.argv[1:])
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f"Firmware validation failed: {error}")
