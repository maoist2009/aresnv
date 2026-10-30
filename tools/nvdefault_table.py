#!/usr/bin/env python3
# GPL-3.0-or-later
"""Parse the modem's default-NV catalog embedded in md1rom.

Each record is 0x40 bytes:

    u32 lid
    u32 flags
    u32 count
    u32 size          payload size in bytes
    u32 blob_off      offset of the default payload (56-byte header + payload)
    u32 idx
    u32 idx
    char path[0x24]   "Z:\\NVRAM\\..."

The payloads live in a separate blob; if the records' blob_off values are
contiguous with stride size+56, the blob is a straighforward image we can
lift out.

usage: python nvdefault_table.py <md1rom-containing image> [lid-hex ...]
"""
import re
import struct
import sys

REC = 0x40
NAMEOFF = 0x1C
NAMELEN = 0x24


def main():
    path = sys.argv[1]
    wants = set(int(a, 16) for a in sys.argv[2:])
    with open(path, 'rb') as f:
        d = f.read()
    recs = []
    for m in re.finditer(rb'Z:\\NVRAM\\', d):
        off = m.start() - NAMEOFF
        if off < 0:
            continue
        rec = d[off:off + REC]
        if len(rec) < REC:
            continue
        lid, flags, count, size, blob, i1, i2 = struct.unpack('<7I', rec[:28])
        name = rec[NAMEOFF:NAMEOFF + NAMELEN].split(b'\x00')[0].decode('latin1')
        recs.append((off, lid, count, size, blob, name))
    print('%d records' % len(recs))
    if not recs:
        return 1
    offs = [r[0] for r in recs]
    gaps = set(b - a for a, b in zip(offs, offs[1:]))
    print('record offsets: %x .. %x, strides=%s' % (offs[0], offs[-1], sorted(gaps)))
    blobs = [(r[4], r[3], r[5]) for r in recs]
    lo = min(b[0] for b in blobs)
    hi = max(b[0] + b[1] for b in blobs)
    print('blob_off range: 0x%x .. 0x%x  => blob span ~0x%x (%d bytes)'
          % (lo, hi, hi - lo, hi - lo))
    # contiguity check: sort by blob_off, verify stride == size + 56
    srt = sorted(blobs)
    stride_ok = 0
    stride_bad = []
    for a, b in zip(srt, srt[1:]):
        if b[0] - a[0] == a[1] + 56:
            stride_ok += 1
        else:
            stride_bad.append((hex(a[0]), a[1], hex(b[0] - a[0])))
    print('contiguous (size+56): %d ok, %d mismatched' % (stride_ok, len(stride_bad)))
    for row in stride_bad[:10]:
        print('   off=%s size=%d next_delta=%s' % row)
    if wants:
        for r in recs:
            if r[1] in wants:
                print('  lid=0x%04x count=%d size=%d blob=0x%x  %s'
                      % (r[1], r[2], r[3], r[4], r[5]))
    else:
        print('first 5 / last 5:')
        for r in recs[:5] + recs[-5:]:
            print('  lid=0x%04x count=%d size=%d blob=0x%x  %s'
                  % (r[1], r[2], r[3], r[4], r[5]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
