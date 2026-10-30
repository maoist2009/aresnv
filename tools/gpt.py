#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# gpt.py - list the partitions in a GPT image (e.g. a dumped gpt.bin).
#
# Used to locate named partitions (preloader, lk, md1img, seccfg, ...) by
# offset and size, so a partition can be dumped or written without guessing.
# Reads a primary or backup GPT header at LBA 1 / last LBA.
#
# Usage:
#   python gpt.py <gpt.bin|disk.img> [<name filter>]
#
import struct
import sys


def parse(path, needle=None, sector=None):
    data = open(path, "rb").read()
    # Auto-detect the LBA size: the primary GPT header sits at LBA 1, so its
    # byte offset equals the sector size (512 on eMMC/SD, 4096 on UFS LUNs).
    if sector is None:
        cand = []
        pos = data.find(b"EFI PART")
        while pos >= 0 and len(cand) < 4:
            cand.append(pos)
            pos = data.find(b"EFI PART", pos + 1)
        sector = 4096 if 4096 in cand else (512 if 512 in cand else 512)
        if not cand:
            print("%s: no GPT header found" % path)
            return 1
    hdr = None
    for base in (sector, len(data) - sector):
        if data[base:base + 8] == b"EFI PART":
            hdr = base
            break
    if hdr is None:
        print("%s: no GPT header found" % path)
        return 1
    entries_lba, num, esize = struct.unpack_from("<QII", data, hdr + 72)
    cur = hdr
    print("=== %s === GPT at LBA %d, %d entries x %d B, table LBA %d" %
          (path, hdr // sector, num, esize, entries_lba))
    print("  %-24s %-12s %-12s %-10s %s" %
          ("name", "first_lba", "last_lba", "size", "bytes"))
    total = 0
    for i in range(num):
        off = entries_lba * sector + i * esize
        e = data[off:off + esize]
        if len(e) < 128 or e[:16] == b"\x00" * 16:
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        name = e[56:128].decode("utf-16-le").split("\x00")[0]
        size = (last - first + 1) * sector
        if size <= 0:
            continue
        total += size
        if needle and needle.lower() not in name.lower():
            continue
        print("  %-24s %-12d %-12d %-10s %d" %
              (name, first, last, "%dM" % (size >> 20), size))
    print("  total partitions: %d, total bytes: %d" % (num, total))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(parse(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
