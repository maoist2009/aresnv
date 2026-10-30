#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# imei_ld0b.py -- read/write MTK "LD0B" IMEI NV items (free replacement for paid IMEI tools)
#
# The IMEI on this MTK NV generation lives in an NV item with LID 0xEF10
# ("LD0B"), 10 entries of 0x20 bytes each:
#
#   entry[0]  = IMEI 1        entry[1] = IMEI 2        entry[2..9] = empty
#   entry layout (0x20 bytes):
#     0x00 8   packed IMEI (nibble-swapped BCD, 15 digits, padded with 'F')
#     0x08 2   zero
#     0x0A 8   checksum = md5(data[0:0xA]) then h[i] ^= h[i+8] for i in 0..7
#     0x12 14  zero
#   empty entry: 0xFF*10 + checksum(0xFF*10) + 0*14
#
# IMPORTANT -- the payload encryption is NOT reproducible on the PC.
#
# This generation (attr 0x402a: SW bit + HW-5G bit) is encrypted by the SoC's
# SEJ engine, driven by the DA; the key is derived from the chip root key.
# Decrypting a real device item with MTK's global NVRAM SW seed (0102...)
# yields garbage -- see notes/IMEI-CRYPTO-AND-FREE-PATH.md.
#
# Therefore:
#   `build-plain`  writes the 384-byte *plaintext* item.  Feed it to
#                  `mtk.py da nvitem --encrypt <file>` on the device; the DA
#                  returns the encrypted entries, which is what you flash.
#   `build`        legacy: encrypts with MTK's SW seed.  Only correct for
#                  chips that really use SW crypto.  Warns otherwise.
#   `dump`         legacy: decrypts with the same seed (will show BAD CHK
#                  on SEJ-protected devices).
#
# On-device write of a ready item (no BROM needed):
#   adb push LD0B_001.bin /data/local/tmp/
#   adb shell 'setenforce 0
#              cat /data/local/tmp/LD0B_001.bin > /mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001
#              sync'
#   adb reboot
#
# Requires mtkclient (GPLv3) only for the crypto primitives.

import argparse
import os
import sys

MTKCLIENT = os.environ.get('MTKCLIENT_PATH', r'D:\apps\mtkclient')
if MTKCLIENT not in sys.path:
    sys.path.insert(0, MTKCLIENT)

try:
    from mtkclient.Library.mtk_crypto import (
        decrypt_nvitem, encrypt_nvitem, encode_imei, decode_imei,
        calc_checksum, is_luhn_valid, make_luhn_checksum)
except Exception as exc:  # pragma: no cover
    sys.stderr.write("cannot import mtkclient crypto (%s); set MTKCLIENT_PATH\n" % exc)
    raise

ENTRIES = 10
ENTRY_SIZE = 0x20
LD0B_MAGIC = bytes.fromhex('4C44490010EF0A00')
# header as produced by a working commercial tool on Xiaomi ares (MT6893)
LD0B_HEADER = bytes.fromhex(
    '4c44490010ef0a000a0000002a4000000020000000000000000000000000c244'
    '0000000000000000000000000100000000000000000000000000000000000000')


def build_entry(imei=None):
    """One 0x20-byte LD0B entry (plaintext) for an IMEI, or the empty marker."""
    if imei is None:
        data = b'\xFF' * 0xA
        return data + calc_checksum(data, 0xA) + b'\x00' * 0x0E
    data = encode_imei(imei) + b'\x00\x00'
    return data + calc_checksum(data, 0xA) + b'\x00' * 0x0E


def build_plain(imeis):
    entries = [build_entry(i) for i in imeis[:2]]
    entries += [build_entry(None) for _ in range(ENTRIES - len(entries))]
    return b''.join(entries)


def build_item(imeis):
    """Full 0x180-byte LD0B_001 file content (MTK SW seed -- see warning above)."""
    plain = build_plain(imeis)
    return LD0B_HEADER + bytes(encrypt_nvitem(plain))


def build_plain_item(imeis):
    """Full 0x180-byte LD0B_001 file content with the entries left in clear.

    This is the input for the DA-side encryption:
        python mtk.py da nvitem --encrypt LD0B_plain.bin
    which prints the encrypted payload that belongs after the 64-byte header.
    """
    return LD0B_HEADER + build_plain(imeis)


def parse_item(blob):
    """Return list of IMEI strings ('' for empty) from a 0x180-byte item."""
    out = []
    dec = bytes(decrypt_nvitem(bytes(blob[0x40:0x40 + ENTRIES * ENTRY_SIZE])))
    for i in range(ENTRIES):
        e = dec[i * ENTRY_SIZE:(i + 1) * ENTRY_SIZE]
        if len(e) < ENTRY_SIZE:
            break
        if e[:0xA] == b'\xFF' * 0xA:
            out.append('')
            continue
        good = calc_checksum(e, 0xA) == e[0xA:0xA + 8]
        imei = decode_imei(e[:0xA])
        out.append(imei + ('' if good else ' (BAD CHK)'))
    return out


def fix_luhn(imei14):
    imei14 = imei14.strip()[:14]
    return imei14 + str(make_luhn_checksum(imei14 + '0'))


def cmd_dump(args):
    data = open(args.file, 'rb').read()
    pos = -1
    found = False
    while True:
        pos = data.find(LD0B_MAGIC, pos + 1)
        if pos < 0:
            break
        found = True
        item = data[pos:pos + LD0B_HEADER.__len__() + ENTRIES * ENTRY_SIZE]
        print("LD0B item @ 0x%x" % pos)
        print("  header  " + item[:0x40].hex())
        for i, imei in enumerate(parse_item(item)):
            if imei:
                print("  IMEI%d   %s" % (i + 1, imei))
    if not found:
        print("no LD0B item found")


def _collect_imeis(args):
    imeis = []
    for s in (args.imei1, args.imei2):
        if not s:
            continue
        s = s.replace(' ', '')
        if len(s) == 14:
            s = fix_luhn(s)
        if len(s) != 15 or not s.isdigit():
            sys.exit("bad IMEI %r (need 14-15 digits)" % s)
        print("IMEI%d = %s (luhn %s)" % (len(imeis) + 1, s,
                                         'ok' if is_luhn_valid(s) else 'FAIL'))
        imeis.append(s)
    if not imeis:
        sys.exit("give --imei1")
    return imeis


def cmd_build(args):
    imeis = _collect_imeis(args)
    item = build_item(imeis)
    with open(args.out, 'wb') as f:
        f.write(item)
    print("wrote %s (%d bytes)" % (args.out, len(item)))
    print("verify: " + str(parse_item(item)))
    sys.stderr.write(
        "\nWARNING: this file is encrypted with MTK's global SW seed.\n"
        "It is only valid on devices whose LD0B attr has the SW bit set and\n"
        "NOT the HW bit.  For SEJ-protected items (attr 0x402a, ares) use\n"
        "`build-plain` and let the DA encrypt it -- see notes/\n"
        "IMEI-CRYPTO-AND-FREE-PATH.md\n")


def cmd_build_plain(args):
    imeis = _collect_imeis(args)
    item = build_plain_item(imeis)
    with open(args.out, 'wb') as f:
        f.write(item)
    print("wrote %s (%d bytes, 64 B header + 320 B PLAINTEXT entries)"
          % (args.out, len(item)))
    print("\nnext, on the device (DA does the AES):")
    print("  python mtk.py da nvitem --encrypt %s" % args.out)
    print("capture the returned payload, put it after the 64-byte header,")
    print("and write the resulting 384-byte file to")
    print("  /mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001")


def cmd_verify(args):
    """Round-trip test against an image that already contains a tool-written item."""
    data = open(args.file, 'rb').read()
    pos = data.find(LD0B_MAGIC)
    if pos < 0:
        sys.exit("no LD0B item in %s" % args.file)
    item = data[pos:pos + 0x180]
    imeis = [x for x in parse_item(item) if x and 'BAD' not in x]
    rebuilt = build_item(imeis)
    print("decoded : %s" % imeis)
    print("payload identical to source : %s" % (rebuilt[0x40:] == item[0x40:]))
    print("full item identical          : %s" % (rebuilt == item))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    d = sub.add_parser('dump', help='decode LD0B IMEI items in a raw image/file')
    d.add_argument('file')
    d.set_defaults(func=cmd_dump)

    b = sub.add_parser('build', help='build an LD0B_001.bin for given IMEI(s)')
    b.add_argument('--imei1', required=True)
    b.add_argument('--imei2', default='')
    b.add_argument('-o', '--out', default='LD0B_001.bin')
    b.set_defaults(func=cmd_build)

    bp = sub.add_parser('build-plain',
                        help='build a PLAINTEXT LD0B_001.bin for DA-side encryption')
    bp.add_argument('--imei1', required=True)
    bp.add_argument('--imei2', default='')
    bp.add_argument('-o', '--out', default='LD0B_plain.bin')
    bp.set_defaults(func=cmd_build_plain)

    v = sub.add_parser('verify', help='round-trip test on a tool-written image (SW crypto only)')
    v.add_argument('file')
    v.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
