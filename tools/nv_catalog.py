#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# nv_catalog.py - dump the modem's complete NV item catalog from an md1img.
#
# Each NV item is described by a 0x40-byte record:
#     +0x00 u32 0
#     +0x04 u32 LID
#     +0x08 u32 0
#     +0x0c u32 count        (records per item)
#     +0x10 u32 size         (total file size = 0x40 header + payload)
#     +0x14 u32 ?            (internal layout offset)
#     +0x18 u32 index
#     +0x1c u32 index
#     +0x20     path string  Z:\NVRAM\<DIR>\<NAME>
#
# usage: python nv_catalog.py <md1img.bin> [filter]
#
import sys

BS = bytes([0x5C])            # a single backslash, without any escape games
PREFIX = b'Z:' + BS + b'NVRAM' + BS

img = sys.argv[1]
flt = sys.argv[2].lower() if len(sys.argv) > 2 else None
d = open(img, 'rb').read()

rows = []
i = 0
while True:
    i = d.find(PREFIX, i)
    if i < 0:
        break
    j = i
    while j < len(d) and (48 <= d[j] <= 57 or 65 <= d[j] <= 90 or 97 <= d[j] <= 122
                          or d[j] == 0x5C or d[j] == 0x5F or d[j] == 0x3A):
        j += 1
    name = d[i:j].decode('latin-1')
    base = i - 0x20
    if base >= 0:
        rec = d[base:i]
        lid = int.from_bytes(rec[4:8], 'little')
        cnt = int.from_bytes(rec[0x0c:0x10], 'little')
        size = int.from_bytes(rec[0x10:0x14], 'little')
        rows.append((name, lid, cnt, size, base))
    i = j

print('%-40s %-6s %-7s %-9s %s' % ('path', 'LID', 'count', 'size', 'rec@'))
for name, lid, cnt, size, base in rows:
    if flt and flt not in name.lower():
        continue
    print('%-40s 0x%04x %-7d %-9d 0x%08x' % (name, lid, cnt, size, base))
print('total records: %d' % len(rows))
