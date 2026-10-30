#!/usr/bin/env python3
"""Inspect Android sparse image headers and (optionally) dump raw content.

Usage:
    python inspect_sparse.py <file.img> [--raw out.bin]

Prints the sparse header and a summary of chunks, or the first bytes if the
file is NOT a sparse image (raw dump).
"""
import struct
import sys


SPARSE_MAGIC = 0xED26FF3A
CHUNK_TYPES = {
    0xCAC1: "RAW",
    0xCAC2: "FILL",
    0xCAC3: "DONT_CARE",
    0xCAC4: "CRC32",
}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = sys.argv[1]
    raw_out = None
    if "--raw" in sys.argv:
        raw_out = sys.argv[sys.argv.index("--raw") + 1]

    with open(path, "rb") as f:
        head = f.read(28)
        if len(head) < 28:
            print("file too small")
            return 1
        magic = struct.unpack("<I", head[0:4])[0]
        if magic != SPARSE_MAGIC:
            print(f"{path}: NOT sparse (magic=0x{magic:08x})")
            f.seek(0)
            first = f.read(64)
            print("first bytes:", first[:64].hex(" "))
            return 0

        major, minor, fh_size, ch_size, blk_size, total_blks, total_chunks, \
            checksum = struct.unpack("<4H4I", head[4:28])
        print(f"{path}")
        print(f"  sparse v{major}.{minor}  fh_size={fh_size} ch_size={ch_size}")
        print(f"  block_size={blk_size}  total_blocks={total_blks} "
              f"({total_blks * blk_size} bytes expanded)")
        print(f"  total_chunks={total_chunks}  crc32=0x{checksum:08x}")

        f.seek(fh_size)
        expanded = 0
        for i in range(total_chunks):
            ch = f.read(12)
            if len(ch) < 12:
                print(f"  truncated at chunk {i}")
                break
            ctype, _res, cblks, ctotal = struct.unpack("<2H2I", ch)
            name = CHUNK_TYPES.get(ctype, f"0x{ctype:04x}")
            if i < 12:
                print(f"  chunk[{i:3}] {name:10} blocks={cblks:6} "
                      f"total_sz={ctotal:8} offset_out={expanded * 0}")
            if ctype == 0xCAC1 and raw_out is not None:
                data = f.read(ctotal)
                with open(raw_out, "ab") as o:
                    o.write(data)
            elif ctype in (0xCAC2, 0xCAC3):
                if raw_out is not None:
                    pad = b"\x00" * (cblks * blk_size)
                    with open(raw_out, "ab") as o:
                        o.write(pad)
                f.seek(ctotal, 1)
            else:
                f.seek(ctotal, 1)
            expanded += cblks
        if i + 1 < total_chunks:
            print(f"  ... ({total_chunks} chunks total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
