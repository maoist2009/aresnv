#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Byte-level diff of two images: list differing ranges, hexdump with context.

Usage:
    python diff_img.py <before> <after> [--ctx N] [--max N]
"""
import sys


def ranges(a, b, chunk=1 << 22):
    fa, fb = open(a, "rb"), open(b, "rb")
    pos = 0
    out = []
    cur = None
    while True:
        ba, bb = fa.read(chunk), fb.read(chunk)
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
                        out.append(cur)
                    cur = [g, g + 1]
        pos += n
    if cur:
        out.append(cur)
    return out


def hexdump(d, off, n=16):
    lines = []
    for i in range(0, len(d), n):
        chunk = d[i:i + n]
        lines.append("      %08x  %-47s  |%s|" % (
            off + i,
            " ".join("%02x" % c for c in chunk),
            "".join(chr(c) if 32 <= c < 127 else "." for c in chunk)))
    return lines


def main():
    before, after = sys.argv[1], sys.argv[2]
    ctx = 32
    maxn = 40
    if "--ctx" in sys.argv:
        ctx = int(sys.argv[sys.argv.index("--ctx") + 1])
    if "--max" in sys.argv:
        maxn = int(sys.argv[sys.argv.index("--max") + 1])

    da = open(before, "rb").read()
    db = open(after, "rb").read()
    print("before %s  %d bytes  md5=%s" % (before, len(da), __import__("hashlib").md5(da).hexdigest()))
    print("after  %s  %d bytes  md5=%s" % (after, len(db), __import__("hashlib").md5(db).hexdigest()))

    rng = ranges(before, after)
    total = sum(e - s for s, e in rng)
    print("\n===== %d differing range(s), %d bytes total =====" % (len(rng), total))
    for s, e in rng[:maxn]:
        print("\n--- 0x%08x .. 0x%08x  (%d bytes)" % (s, e, e - s))
        lo = max(0, s - ctx)
        hi = min(len(da), e + ctx)
        for ln in hexdump(da[lo:hi], lo):
            print("   BEFORE " + ln)
        for ln in hexdump(db[lo:hi], lo):
            print("   AFTER  " + ln)
    if len(rng) > maxn:
        print("\n... +%d more ranges" % (len(rng) - maxn))


if __name__ == "__main__":
    main()
