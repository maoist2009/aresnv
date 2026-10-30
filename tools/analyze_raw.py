#!/usr/bin/env python3
"""Quick structural summary of a raw partition dump.

Usage: python analyze_raw.py <file> [more files...]
"""
import re
import sys
from collections import Counter

PRINTABLE = re.compile(rb"[\x20-\x7e]{6,}")


def summarize(path: str) -> None:
    with open(path, "rb") as f:
        data = f.read()
    size = len(data)
    counts = Counter(data)
    zero = counts.get(0, 0)
    ff = counts.get(0xFF, 0)
    other = size - zero - ff
    print(f"\n=== {path} ({size} bytes = {size/1024/1024:.2f} MiB) ===")
    print(f"  0x00: {zero} ({zero*100/size:.1f}%)  "
          f"0xFF: {ff} ({ff*100/size:.1f}%)  other: {other} ({other*100/size:.1f}%)")
    print(f"  first 32 bytes: {data[:32].hex(' ')}")
    uniq = len(counts)
    print(f"  distinct byte values: {uniq}")
    strings = [m.group().decode("latin-1") for m in PRINTABLE.finditer(data)]
    print(f"  printable strings (>=6): {len(strings)}")
    for s in strings[:35]:
        print(f"    {s!r}")
    if len(strings) > 35:
        print(f"    ... (+{len(strings)-35} more)")


def main() -> int:
    for path in sys.argv[1:]:
        summarize(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
