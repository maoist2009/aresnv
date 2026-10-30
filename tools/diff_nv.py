#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare two nvdata images: whole-image diff + NVD_IMEI item payloads.

Usage:
    python diff_nv.py <before.img> <after.img>
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ext4x import Ext4  # noqa: E402

FILES = ("NV01A000", "NV01B000", "NV0S_000")


def item(fs, name):
    ino = fs.lookup("/md/NVRAM/NVD_IMEI/" + name)
    if ino is None:
        return None, None
    return ino, fs.read_inode_data(ino)


def img_diff(a, b):
    fa, fb = open(a, "rb"), open(b, "rb")
    pos = 0
    ranges = []
    cur = None
    while True:
        ba, bb = fa.read(1 << 20), fb.read(1 << 20)
        if not ba and not bb:
            break
        n = min(len(ba), len(bb))
        for i in range(n):
            if ba[i] != bb[i]:
                g = pos + i
                if cur and g - cur[1] <= 64:
                    cur[1] = g + 1
                else:
                    if cur:
                        ranges.append(cur)
                    cur = [g, g + 1]
        pos += n
    if cur:
        ranges.append(cur)
    return ranges


def main(before, after):
    for tag, p in (("before", before), ("after", after)):
        print("%s: %s  md5=%s" % (tag, p, __import__("hashlib").md5(open(p, "rb").read()).hexdigest()))

    rng = img_diff(before, after)
    print("\n===== whole-image differing byte ranges: %d =====" % len(rng))
    for s, e in rng[:40]:
        print("    0x%08x .. 0x%08x  (%d bytes)" % (s, e, e - s))
    if len(rng) > 40:
        print("    ... +%d more" % (len(rng) - 40))

    fsa, fsb = Ext4(before), Ext4(after)
    print("\n===== NVD_IMEI items =====")
    for name in FILES:
        ia, da = item(fsa, name)
        ib, db = item(fsb, name)
        print("--- %s (ino %s -> %s, size %s -> %s)" % (
            name, ia, ib, len(da) if da else None, len(db) if db else None))
        if da and db:
            for i in range(0, 0x40, 0x10):
                print("     hdr[%02x]  before %s" % (i, da[i:i + 0x10].hex(" ")))
                print("              after  %s" % db[i:i + 0x10].hex(" "))
            print("     PLAIN-AREA before: %s" % da[0x40:0x60].hex())
            print("     PLAIN-AREA after : %s" % db[0x40:0x60].hex())
            if len(da) > 0x60:
                print("     tail     before: %s" % da[0x60:].hex())
                print("     tail     after : %s" % db[0x60:].hex())


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
