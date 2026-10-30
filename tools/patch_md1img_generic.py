#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""patch_md1img_generic.py -- firmware-agnostic IMEI-gate patcher for Xiaomi
MediaTek modems (md1img), free replacement for the paid "patch modem
signature" step.

Background
----------
The modem's custom_nvram_check_imei ("fingerprint + pool anchor") refuses to
report an IMEI unless its internal check passes.  Two 6-byte instruction
fragments in the modem firmware implement the gate.  Patching them makes the
modem report whatever IMEI the NV data carries:

    site 1  orig  11 1f 34 1e 31 fc   ->  11 1f 01 d2 e0 db
    site 2  orig  11 1f 33 1e c0 00   ->  11 1f 01 d2 e0 db

Verified present and unique across firmware generations of ares (MT6893):
stock V12.5.3, V14.0.5 base, and intermediate builds -- the site OFFSET moves
between builds, the byte PATTERN does not, so a scan-and-replace works
everywhere.  (Both patched fragments share the 111f opcode prefix; the tail
is the bypass.)

Usage
-----
    python patch_md1img_generic.py <md1img file or 200MiB partition dump> [out]
        patches a copy, writes <out> (default: <in>.patched), prints a report,
        exit 0 on success / 1 if any pattern was missing or ambiguous.

    --keyswap private_2048.pem
        additionally swap Xiaomi's factory RSA-2048 public modulus inside the
        image (CSSD/devkey trust root) with the modulus of the given key.
        Not needed on ares (CSSD untouched by the working flow), but kept for
        models whose NV chain validates device keys.

This file is intentionally self-contained: copy it next to mtkclient and it
completes the free IMEI-repair recipe together with

    python mtk.py da imei --write "<imei1>,<imei2>"
"""
import sys

# (name, original bytes, patched bytes)
PATCHES = [
    ("imei_gate_1", bytes.fromhex("111f341e31fc"), bytes.fromhex("111f01d2e0db")),
    ("imei_gate_2", bytes.fromhex("111f331ec000"), bytes.fromhex("111f01d2e0db")),
]

# Xiaomi factory RSA-2048 modulus as embedded in md1img (upstream mtkclient)
XIAOMI_MODULUS = bytes([
    0xC0, 0x76, 0x21, 0xF1, 0x95, 0x51, 0x14, 0x2D, 0x3D, 0x5D, 0x9D, 0xD5, 0x14, 0x05, 0xD5, 0xD8,
    0x34, 0x70, 0xD5, 0x41, 0x7E, 0x66, 0x1C, 0xB3, 0xF5, 0x47, 0x2D, 0x2E, 0x4A, 0x9A, 0xE5, 0x63,
    0x45, 0xBF, 0x41, 0x87, 0x16, 0xFE, 0x7F, 0xB5, 0xA5, 0xC0, 0x41, 0x0E, 0x0F, 0xB1, 0x06, 0x72,
    0x59, 0x23, 0x05, 0xAC, 0x46, 0xC1, 0xB8, 0x01, 0x24, 0x06, 0xDD, 0x02, 0x8B, 0xF6, 0x68, 0x7F,
    0x39, 0xDC, 0x5C, 0xAF, 0x45, 0x82, 0x9A, 0xE0, 0x6F, 0x17, 0x58, 0x94, 0xC2, 0x0A, 0xE3, 0x5A,
    0x33, 0x3B, 0x71, 0x9D, 0x96, 0xA5, 0xD7, 0x7F, 0x85, 0x20, 0x66, 0xA8, 0xFF, 0x17, 0xCA, 0xFC,
    0x22, 0x53, 0x89, 0xC0, 0x15, 0x14, 0x92, 0xE0, 0x7F, 0x67, 0xC8, 0x82, 0xB8, 0x9D, 0x13, 0x97,
    0xF9, 0xB5, 0x6A, 0xC2, 0xE5, 0x72, 0xCB, 0x07, 0xC1, 0xCC, 0xF5, 0xD2, 0xFC, 0x59, 0x07, 0x04,
    0x37, 0xDC, 0xBB, 0x35, 0x1C, 0xE0, 0xB6, 0x3D, 0x6C, 0x76, 0x2B, 0x42, 0x7E, 0xB6, 0x6C, 0x90,
    0xD9, 0x3F, 0x6F, 0x2C, 0xCB, 0x66, 0xD4, 0xEF, 0xF2, 0x63, 0xC0, 0xDA, 0x77, 0x35, 0x5B, 0x9E,
    0xE4, 0x02, 0x6F, 0x0C, 0x80, 0x56, 0x9A, 0x19, 0xB8, 0x39, 0xD3, 0x98, 0x8F, 0x4B, 0x55, 0xB0,
    0x42, 0xE7, 0xB9, 0x77, 0x30, 0x84, 0x8F, 0xA6, 0x2D, 0xCA, 0x42, 0x72, 0x02, 0x76, 0xC6, 0x1C,
    0xC3, 0xB6, 0x98, 0x16, 0x4E, 0xE7, 0x41, 0x9B, 0xD1, 0x38, 0xB8, 0x5C, 0xAE, 0x04, 0x21, 0x74,
    0xA7, 0x49, 0x38, 0x19, 0xC8, 0x33, 0x95, 0x3A, 0x4F, 0x93, 0x06, 0x8F, 0xF5, 0x65, 0x1F, 0x31,
    0x63, 0x3A, 0x2A, 0xDB, 0xD1, 0xFB, 0x5F, 0xD8, 0xD6, 0xDD, 0x0E, 0xBF, 0xB3, 0x56, 0x16, 0x6E,
    0xB3, 0x31, 0xBD, 0xE5, 0x8D, 0x1E, 0x22, 0x84, 0xA0, 0x47, 0xC4, 0x42, 0x06, 0x2C, 0x1E, 0xB5,
])


def patch(data: bytes, keyswap_pem: str = None):
    """Return (patched_bytes, report_lines, ok)."""
    report = []
    ok = True
    buf = bytearray(data)
    for name, orig, patched in PATCHES:
        n_orig = buf.count(orig)
        n_done = buf.count(patched)
        if n_orig == 1:
            idx = buf.find(orig)
            buf[idx:idx + len(orig)] = patched
            report.append(f"[OK]   {name}: patched at 0x{idx:x} ({orig.hex()} -> {patched.hex()})")
        elif n_orig == 0 and n_done >= 1:
            report.append(f"[SKIP] {name}: already patched ({n_done} occurrences)")
        elif n_orig == 0:
            report.append(f"[FAIL] {name}: pattern not found -- unsupported firmware?")
            ok = False
        else:
            report.append(f"[FAIL] {name}: pattern found {n_orig} times -- ambiguous, refusing")
            ok = False
    if keyswap_pem:
        try:
            from Crypto.PublicKey import RSA
            from Crypto.Util.number import long_to_bytes
            key = RSA.import_key(open(keyswap_pem, "r").read(), "")
            new_mod = long_to_bytes(key.n, 2048 // 8)
            idx = buf.find(XIAOMI_MODULUS)
            if idx != -1:
                buf[idx:idx + 256] = new_mod
                report.append(f"[OK]   rsa_modulus: Xiaomi pubkey swapped at 0x{idx:x}")
            else:
                report.append("[SKIP] rsa_modulus: Xiaomi modulus not present (ok for most models)")
        except Exception as exc:  # noqa: BLE001
            report.append(f"[FAIL] rsa_modulus: {exc}")
            ok = False
    return bytes(buf), report, ok


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src + ".patched"
    keyswap = None
    if "--keyswap" in sys.argv:
        keyswap = sys.argv[sys.argv.index("--keyswap") + 1]
    data = open(src, "rb").read()
    out, report, ok = patch(data, keyswap)
    for line in report:
        print(line)
    if ok:
        open(dst, "wb").write(out)
        print(f"[DONE] wrote {dst} ({len(out)} bytes)")
        return 0
    print("[ABORT] no file written")
    return 1


if __name__ == "__main__":
    sys.exit(main())
