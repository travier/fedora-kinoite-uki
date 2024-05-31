#!/usr/bin/env bash
set -xeuo pipefail

# Workaround for Python timestamp mismatch
# See: https://github.com/ostreedev/ostree/issues/1469

echo '
import os
import re

MIN_MAGIC = 3390  # The first magic number supporting PEP 552
ZERO = bytes((0, 0, 0, 0))

def pyc_set_zero_mtime(pyc_path):
    with open(pyc_path, "r+b") as f:
        w = f.read(4)
        if len(w) < 4:
            return 0

        magic = (w[0] + (w[1] << 8) + (w[2] << 16) + (w[3] << 24)) & 0xFFFF
        if magic < MIN_MAGIC:
            invalidation = ZERO
        else:
            invalidation = f.read(4)
            if len(invalidation) < 4:
                return 0

        if invalidation == ZERO:
            f.write(ZERO)
            return 1
    return 0

if __name__ == "__main__":
    REGEX = re.compile(r".*/__pycache__/[^/]+\.cpython-.*(\.opt-1|\.opt-2)?\.pyc$")
    count = 0

    for root, dirs, files in os.walk("/usr"):
        for file in files:
            path = os.path.join(root, file)
            if REGEX.match(path):
                count += pyc_set_zero_mtime(path)

    print(f"Processed {count} pyc files")
' | python
