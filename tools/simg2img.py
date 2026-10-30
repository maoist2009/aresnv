#!/usr/bin/env python3
"""Minimal Android sparse image -> raw converter (simg2img).

Usage:
    python simg2img.py <in.img> <out.raw>

Exits 0 on success. If <in.img> is not a sparse image it is copied verbatim.
"""
import shutil
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONTCARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


def convert(src: str, dst: str) -> tuple[bool, int]:
    with open(src, "rb") as f:
        head = f.read(28)
        if len(head) < 28 or struct.unpack("<I", head[0:4])[0] != SPARSE_MAGIC:
            f.seek(0)
            with open(dst, "wb") as o:
                shutil.copyfileobj(f, o)
            return False, 0
        (_major, _minor, fh_size, _ch_size, blk_size, total_blks,
         total_chunks, _crc) = struct.unpack("<4H4I", head[4:28])
        f.seek(fh_size)
        out_size = 0
        with open(dst, "wb") as o:
            for i in range(total_chunks):
                ch = f.read(12)
                if len(ch) < 12:
                    raise EOFError(f"truncated chunk header at {i}")
                ctype, _res, cblks, _total = struct.unpack("<2H2I", ch)
                data_size = cblks * blk_size
                if ctype == CHUNK_RAW:
                    remaining = data_size
                    while remaining:
                        buf = f.read(min(1 << 20, remaining))
                        if not buf:
                            raise EOFError(f"truncated raw chunk {i}")
                        o.write(buf)
                        remaining -= len(buf)
                elif ctype == CHUNK_FILL:
                    fill = f.read(4)
                    o.write(fill * (data_size // 4))
                elif ctype == CHUNK_DONTCARE:
                    o.write(b"\x00" * data_size)
                elif ctype == CHUNK_CRC32:
                    pass
                else:
                    raise ValueError(f"unknown chunk type 0x{ctype:04x} at {i}")
                out_size += data_size
    return True, out_size


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    sparse, size = convert(sys.argv[1], sys.argv[2])
    print(f"{sys.argv[1]} -> {sys.argv[2]}: "
          f"{'sparse' if sparse else 'raw'}, {size} bytes expanded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
