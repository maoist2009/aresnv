#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
#
# validate_ld0b.py - sanity check the LD0B (IMEI) NV item pipeline:
#   * decrypt real device NV items pulled from the phone and show the plaintext
#   * round-trip our generated LD0B_001 (encrypt -> decrypt -> parse IMEIs)
#
import os
import sys

MTKCLIENT = os.environ.get('MTKCLIENT_PATH', r'D:\apps\mtkclient')
if MTKCLIENT not in sys.path:
    sys.path.insert(0, MTKCLIENT)

from mtkclient.Library.mtk_crypto import decrypt_nvitem  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from imei_ld0b import parse_item  # noqa: E402


def show(path, payload_off=0x40):
    d = open(path, 'rb').read()
    print("== %s (%d bytes) ==" % (os.path.basename(path), len(d)))
    print("   hdr : " + d[:0x40].hex())
    body = d[payload_off:]
    print("   body: " + body.hex())
    try:
        dec = bytes(decrypt_nvitem(bytearray(body)))
        print("   dec : " + dec.hex())
        printable = ''.join(chr(c) if 32 <= c < 127 else '.' for c in dec)
        print("   txt : " + printable)
    except Exception as exc:
        print("   decrypt failed: %r" % (exc,))


nv = os.path.join(ROOT, 'analysis', 'extracted', 'nvdata', 'md', 'NVRAM', 'NVD_IMEI')
for f in ('NV01A000', 'NV01B000', 'NV0S_000'):
    p = os.path.join(nv, f)
    if os.path.exists(p):
        show(p)

ld0b = os.path.join(ROOT, 'out', 'LD0B_001.bin')
if os.path.exists(ld0b):
    d = open(ld0b, 'rb').read()
    print("== out/LD0B_001.bin (%d bytes) ==" % len(d))
    print("   hdr : " + d[:0x40].hex())
    for i, s in enumerate(parse_item(d)):
        if s:
            print("   IMEI%d %s" % (i + 1, s))
