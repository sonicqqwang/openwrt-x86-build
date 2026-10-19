#!/usr/bin/env bash
# Validate gzip images with optional fwtool signature and metadata trailers.
set -euo pipefail
if (( $# != 3 )); then
  echo "Usage: $0 FWTOOL IMAGE REPORT_OUTPUT" >&2
  exit 2
fi
exec python3 "$(dirname -- "$0")/validate_image.py" "$@"
