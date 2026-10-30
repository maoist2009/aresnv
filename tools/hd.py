#!/usr/bin/env python3
# GPL-3.0-or-later
"""Hex + ASCII dump: python hd.py <file> <start> <len>"""
import sys


def main():
    path = sys.argv[1]
    start = int(sys.argv[2], 0)
    ln = int(sys.argv[3], 0)
    with open(path, 'rb') as f:
        f.seek(start)
        d = f.read(ln)
    for i in range(0, len(d), 16):
        row = d[i:i + 16]
        h = ' '.join('%02x' % c for c in row)
        a = ''.join(chr(c) if 32 <= c < 127 else '.' for c in row)
        print('%08x  %-47s  %s' % (start + i, h, a))
    return 0


if __name__ == '__main__':
    sys.exit(main())
