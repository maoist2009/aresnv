#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decode an Android sparse image (the format mtkclient/SP Flash Tool use for partition reads).

Usage:
    python sparse.py <sparse.img> <out.raw>
    python sparse.py --info <sparse.img>
"""
import struct
import sys

MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


def decode(path, outpath=None):
    d = open(path, 'rb').read()
    magic, major, minor, fhsz, chsz, blk, total_blks, total_chunks, csum = \
        struct.unpack_from('<IHHHHIIII', d, 0)
    if magic != MAGIC:
        raise ValueError('not a sparse image (magic %08x)' % magic)
    info = dict(major=major, minor=minor, file_hdr_sz=fhsz, chunk_hdr_sz=chsz,
                blk_sz=blk, total_blks=total_blks, total_chunks=total_chunks,
                checksum=csum, expanded_bytes=blk * total_blks)
    if outpath is None:
        return info, None
    out = bytearray()
    pos = fhsz
    for i in range(total_chunks):
        ctype, _res, csz_blocks, total_sz = struct.unpack_from('<HHII', d, pos)
        data_off = pos + chsz
        nbytes = csz_blocks * blk
        if ctype == CHUNK_RAW:
            out += d[data_off:data_off + nbytes]
        elif ctype == CHUNK_FILL:
            out += d[data_off:data_off + 4] * csz_blocks
        elif ctype == CHUNK_DONT_CARE:
            out += b'\x00' * nbytes
        elif ctype == CHUNK_CRC32:
            pass
        else:
            raise ValueError('unknown chunk type 0x%04x at %d' % (ctype, pos))
        pos += total_sz
    with open(outpath, 'wb') as f:
        f.write(bytes(out))
    info['written'] = len(out)
    return info, bytes(out)


if __name__ == '__main__':
    if sys.argv[1] == '--info':
        print(decode(sys.argv[2])[0])
    else:
        info, _ = decode(sys.argv[1], sys.argv[2])
        print(info)
