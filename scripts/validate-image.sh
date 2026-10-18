#!/usr/bin/env bash
# x86 .img.gz images have fwtool metadata appended AFTER the gzip stream.
# Validate its CRC and test the extracted gzip stream without changing the image.
set -euo pipefail
if (( $# != 3 )); then
  echo "Usage: $0 FWTOOL IMAGE METADATA_OUTPUT" >&2
  exit 2
fi
fwtool=$1
image=$2
metadata=$3
"$fwtool" -i "$metadata" -T "$image" | gzip -t
python3 -m json.tool "$metadata" >/dev/null
