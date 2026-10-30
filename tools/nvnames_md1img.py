#!/usr/bin/env python3
# GPL-3.0-or-later
"""Locate modem NV item names inside md1img images (the modem's NV catalog).

usage: python nvnames_md1img.py <image> [<image> ...]
"""
import re
import sys

NAMES = [b'CSSD_000', b'XPJJ_000', b'CK04_000', b'CK17_000', b'LD0B_001',
         b'NV01A000', b'NV01B000', b'NV0S_000', b'FILELIST', b'MTCR_000',
         b'ER1D_002', b'SL00_000', b'INFO_FILE']


def main():
    for p in sys.argv[1:]:
        with open(p, 'rb') as f:
            d = f.read()
        print('=== %s (%d bytes)' % (p, len(d)))
        for n in NAMES:
            offs = [m.start() for m in re.finditer(re.escape(n), d)]
            if offs:
                print('  %-10s %4d  %s' % (n.decode(), len(offs),
                                           ' '.join(hex(o) for o in offs[:8])))
            else:
                print('  %-10s    0' % n.decode())
    return 0


if __name__ == '__main__':
    sys.exit(main())
