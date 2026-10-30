#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dump an ext4 image's file tree as {path: (size, md5, hex-prefix)} and diff trees.

Usage:
    python ext4_tree.py dump <image> [out.json]
    python ext4_tree.py diff <a.json> <b.json>
"""
import hashlib
import json
import sys

from ext4x import Ext4

FT_DIR = 2


def walk(fs, ino, prefix, out, depth=0):
    if depth > 8:
        return
    for name, child, ftype in fs.listdir(ino):
        if name in (".", ".."):
            continue
        path = prefix + "/" + name
        try:
            if ftype == FT_DIR or fs.inode(child)["mode"] & 0xF000 == 0x4000:
                walk(fs, child, path, out, depth + 1)
                continue
            data = fs.read_inode_data(child)
        except Exception as exc:  # noqa: BLE001
            out[path] = {"error": str(exc)}
            continue
        out[path] = {
            "size": len(data),
            "md5": hashlib.md5(data).hexdigest(),
            "head": data[:64].hex(),
        }


def cmd_dump(img, outfile):
    fs = Ext4(img)
    out = {}
    walk(fs, 2, "", out)
    if outfile:
        with open(outfile, "w") as f:
            json.dump(out, f, indent=1, sort_keys=True)
        print("%s -> %s (%d files)" % (img, outfile, len(out)))
    else:
        for p in sorted(out):
            e = out[p]
            print("%-46s %-8s %s %s" % (p, e.get("size", "-"), e.get("md5", e.get("error")),
                                        e.get("head", "")))


def cmd_diff(fa, fb):
    a = json.load(open(fa))
    b = json.load(open(fb))
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    print("== only in %s (%d) ==" % (fa, len(only_a)))
    for p in only_a:
        print("   -", p, a[p].get("size"), a[p].get("md5"))
    print("== only in %s (%d) ==" % (fb, len(only_b)))
    for p in only_b:
        print("   +", p, b[p].get("size"), b[p].get("md5"))
    print("== changed ==")
    for p in sorted(set(a) & set(b)):
        if a[p] != b[p]:
            print("   ~ %-44s %s(%s) -> %s(%s)" % (p, a[p].get("size"), a[p].get("md5", "")[:12],
                                                    b[p].get("size"), b[p].get("md5", "")[:12]))
            print("       a: %s" % a[p].get("head", ""))
            print("       b: %s" % b[p].get("head", ""))


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "dump":
        cmd_dump(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    elif mode == "diff":
        cmd_diff(sys.argv[2], sys.argv[3])
