#!/bin/sh
# Unit tests (no Magic needed) and backend tests (Magic needed), in the image.
exec "$(dirname "$0")/in_image.sh" 'set -e; python3 -m unittest discover -s tests/unit -t . "$@"; python3 -m unittest discover -s tests/backend -t . "$@"' "$@"
