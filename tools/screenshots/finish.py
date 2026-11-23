"""Copy the raw grabs that guide.md uses to the output folder as PNGs of at
most about 300 KB: saved optimized, and reduced to a 256-colour palette
only when the full-colour file is larger than that.

    python3 finish.py RAW_DIR OUT_DIR
"""

import os
import sys

from PIL import Image

LIMIT = 300 * 1024
SHOTS = [
    "salt-package", "libraries", "place-nfet", "nfet-l-corrected", "nfet-placed",
    "via1-too-small", "layout-overview", "properties-edit", "log-viewer", "stamp",
    "reopen-with-library", "reopen-without-library",
]


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    missing = []
    for name in SHOTS:
        src = os.path.join(raw, name + ".png")
        if not os.path.exists(src):
            missing.append(name)
            continue
        dst = os.path.join(out, name + ".png")
        im = Image.open(src).convert("RGB")
        im.save(dst, optimize=True)
        if os.path.getsize(dst) > LIMIT:
            im.quantize(256, method=Image.Quantize.MEDIANCUT).save(dst, optimize=True)
        print("%-22s %4d x %-4d %4d KB" % (name, im.width, im.height, os.path.getsize(dst) // 1024))
    if missing:
        print("missing: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
