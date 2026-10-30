#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Extract printable ASCII strings from a binary, optionally filtered.

Usage:
    python binstr.py <file> [substring ...] [--min N] [--offset]

Prints each matching string with its file offset (hex).  Useful for pulling
property names, socket names and log formats out of a vendor .so.
"""

import argparse
import re
import sys

PRINTABLE = re.compile(rb'[\x20-\x7e]{4,}')


def iter_strings(data, minlen):
    for m in PRINTABLE.finditer(data):
        if len(m.group()) >= minlen:
            yield m.start(), m.group().decode('ascii', 'replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('needles', nargs='*')
    ap.add_argument('--min', type=int, default=4)
    ap.add_argument('--offset', action='store_true')
    args = ap.parse_args()

    data = open(args.file, 'rb').read()
    seen = set()
    for off, text in iter_strings(data, args.min):
        if args.needles and not any(n.lower() in text.lower() for n in args.needles):
            continue
        if text in seen:
            continue
        seen.add(text)
        print('%08x  %s' % (off, text) if args.offset else text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
