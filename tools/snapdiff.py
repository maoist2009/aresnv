#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# snapdiff.py - fingerprint and byte-diff raw partition snapshots.
#
# Used to read out what a commercial tool actually changes, from the tool's own
# "backup before each run" snapshots: every run N snapshot is the state after run
# N-1, so consecutive snapshots bracket exactly what one run wrote.
#
# Usage:
#   python snapdiff.py fingerprint <file> [<file> ...]
#   python snapdiff.py diff <before> <after> [--max-regions N] [--context N]
#
import hashlib
import sys


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(paths):
    rows = []
    for p in paths:
        try:
            with open(p, "rb") as f:
                data = f.read()
        except OSError as e:
            print("!! %s: %s" % (p, e))
            continue
        nz = sum(1 for b in data if b)
        rows.append((p, len(data), md5(p), nz))
    for p, size, h, nz in rows:
        print("%s  %10d  nonzero=%d" % (h, size, nz))
        print("    %s" % p)


def regions(a, b):
    """Yield (offset, len_a, len_b) runs where the two buffers differ."""
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            yield (i, b[i:j], a[i:j])
            i = j
        else:
            i += 1
    if len(a) != len(b):
        yield (n, b[n:], a[n:])


def diff(pa, pb, max_regions=40, context=16):
    a = open(pa, "rb").read()
    b = open(pb, "rb").read()
    print("before: %s  (%d bytes, md5 %s)" % (pa, len(a), md5(pa)))
    print("after : %s  (%d bytes, md5 %s)" % (pb, len(b), md5(pb)))
    if a == b:
        print("IDENTICAL")
        return
    total = 0
    shown = 0
    for off, chunk_b, chunk_a in regions(a, b):
        total += len(chunk_b)
        if shown < max_regions:
            lo = max(0, off - context)
            hi = min(len(b), off + len(chunk_b) + context)
            print("@0x%08x  %d bytes changed" % (off, len(chunk_b)))
            print("    before %s" % a[lo:hi].hex())
            print("    after  %s" % b[lo:hi].hex())
            shown += 1
    if shown < 0:
        pass
    print("---- %d differing bytes in %d regions%s" %
          (total, shown, "" if shown <= max_regions else " (truncated)"))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    mode = sys.argv[1]
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    opts = dict()
    for a in sys.argv[2:]:
        if a.startswith("--"):
            k, _, v = a[2:].partition("=")
            opts[k] = v
    if mode == "fingerprint":
        fingerprint(args)
    elif mode == "diff":
        diff(args[0], args[1],
             max_regions=int(opts.get("max-regions", 40)),
             context=int(opts.get("context", 16)))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
