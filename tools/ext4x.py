#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal offline ext4 inspector: superblock, path lookup, inode + xattr dump.

Used to compare the factory nvdata image (inode size 128) with the
runtime-regenerated one (inode size 512) and to see exactly where the
`security.selinux` xattr lives (inline vs external xattr block).

Usage:
    python ext4x.py info <image>
    python ext4x.py path <image> <path...>
"""
import struct
import sys

EXT4_EXTENTS_FL = 0x00080000
EXT4_XATTR_MAGIC = 0xEA020000
XATTR_INDEX = {1: "user", 2: "system.posix_acl_access", 3: "system.posix_acl_default",
               4: "trusted", 5: "lustre", 6: "security", 7: "system"}


class Ext4:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.d = None
        self.sb = self._super()
        self.blk = 1 << (10 + self.sb["log_block_size"])
        self.inode_size = self.sb["inode_size"] or 128
        self.inodes_per_group = self.sb["inodes_per_group"]
        self.first_data_block = self.sb["first_data_block"]
        self.gdt_off = (self.first_data_block + 1) * self.blk
        self.desc_size = self.sb["desc_size"] if self.sb["incompat"] & 0x80 else 32

    def _super(self):
        self.f.seek(1024)
        s = self.f.read(0x400)
        g = lambda o, fmt: struct.unpack_from(fmt, s, o)[0]
        return {
            "inodes_count": g(0x00, "<I"),
            "blocks_count": g(0x04, "<I"),
            "first_data_block": g(0x14, "<I"),
            "log_block_size": g(0x18, "<I"),
            "blocks_per_group": g(0x20, "<I"),
            "inodes_per_group": g(0x28, "<I"),
            "magic": g(0x38, "<H"),
            "first_ino": g(0x54, "<I"),
            "inode_size": g(0x58, "<H"),
            "compat": g(0x5C, "<I"),
            "incompat": g(0x60, "<I"),
            "ro_compat": g(0x64, "<I"),
            "desc_size": g(0xFE, "<H"),
            "uuid": s[0x68:0x78].hex(),
            "volume_name": s[0x78:0x88].split(b"\0")[0].decode("latin-1"),
            "mtime": g(0x2C, "<I"),
            "wtime": g(0x30, "<I"),
            "feature_str": s[0x2D0:0x2D0 + 16].split(b"\0")[0].decode("latin-1"),
            "last_mounted": s[0x88 + 0x40:0x88 + 0x40 + 64].split(b"\0")[0].decode("latin-1")
            if len(s) > 0xC8 else "",
        }

    # ---------------- low level ----------------
    def read(self, off, ln):
        if self.d is not None:
            return self.d[off:off + ln]
        self.f.seek(off)
        return self.f.read(ln)

    def blk_read(self, n):
        return self.read(n * self.blk, self.blk)

    def gdesc(self, group):
        off = self.gdt_off + group * self.desc_size
        r = self.read(off, 32)
        return {
            "block_bitmap": struct.unpack_from("<I", r, 0x00)[0],
            "inode_bitmap": struct.unpack_from("<I", r, 0x04)[0],
            "inode_table": struct.unpack_from("<I", r, 0x08)[0],
        }

    def inode_raw(self, ino):
        group = (ino - 1) // self.inodes_per_group
        index = (ino - 1) % self.inodes_per_group
        it = self.gdesc(group)["inode_table"]
        return self.read(it * self.blk + index * self.inode_size, self.inode_size)

    def inode(self, ino):
        r = self.inode_raw(ino)
        g = lambda o, fmt: struct.unpack_from(fmt, r, o)[0]
        size = g(0x04, "<I") | (g(0x6C, "<I") << 32)
        i = {
            "ino": ino,
            "mode": g(0x00, "<H"),
            "size": size,
            "links": g(0x1A, "<H"),
            "blocks": g(0x1C, "<I"),
            "flags": g(0x20, "<I"),
            "block": r[0x28:0x28 + 60],
            "file_acl": g(0x68, "<I"),
            "extra_isize": g(0x80, "<H") if self.inode_size > 128 else 0,
            "raw": r,
        }
        return i

    def blocks_of(self, ino):
        i = self.inode(ino)
        out = []
        if i["flags"] & EXT4_EXTENTS_FL:
            m = struct.unpack_from("<H", i["block"], 0)[0]
            if m != 0xF30A:
                return out
            entries = struct.unpack_from("<H", i["block"], 2)[0]
            depth = struct.unpack_from("<H", i["block"], 6)[0]
            if depth == 0:
                for k in range(entries):
                    b = i["block"][12 + k * 12:12 + (k + 1) * 12]
                    ee_len = struct.unpack_from("<H", b, 4)[0]
                    hi = struct.unpack_from("<H", b, 6)[0]
                    lo = struct.unpack_from("<I", b, 8)[0]
                    first = (hi << 32) | lo
                    if ee_len > 32768:  # unwritten
                        ee_len -= 32768
                    out.extend(range(first, first + ee_len))
            else:
                for k in range(entries):
                    b = i["block"][12 + k * 12:12 + (k + 1) * 12]
                    hi = struct.unpack_from("<H", b, 6)[0]
                    lo = struct.unpack_from("<I", b, 8)[0]
                    out.extend(self._extent_leaf((hi << 32) | lo))
        else:
            p = [struct.unpack_from("<I", i["block"], k * 4)[0] for k in range(12)]
            out.extend([x for x in p if x])
        return out

    def _extent_leaf(self, blk):
        r = self.blk_read(blk)
        entries = struct.unpack_from("<H", r, 2)[0]
        out = []
        for k in range(entries):
            b = r[12 + k * 12:12 + (k + 1) * 12]
            ee_len = struct.unpack_from("<H", b, 4)[0]
            hi = struct.unpack_from("<H", b, 6)[0]
            lo = struct.unpack_from("<I", b, 8)[0]
            first = (hi << 32) | lo
            if ee_len > 32768:
                ee_len -= 32768
            out.extend(range(first, first + ee_len))
        return out

    def read_inode_data(self, ino, limit=None):
        i = self.inode(ino)
        data = b"".join(self.blk_read(b) for b in self.blocks_of(ino))
        data = data[:i["size"]]
        return data if limit is None else data[:limit]

    # ---------------- dirs ----------------
    def listdir(self, ino):
        """yield (name, inode, file_type)"""
        data = self.read_inode_data(ino)
        pos = 0
        while pos + 8 <= len(data):
            ino2, rec_len, name_len, ftype = struct.unpack_from("<IHBB", data, pos)
            if rec_len == 0:
                break
            name = data[pos + 8:pos + 8 + name_len]
            if ino2:
                yield name.decode("latin-1"), ino2, ftype
            pos += rec_len

    def lookup(self, path):
        cur = 2
        parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
        for p in parts:
            found = None
            for name, ino, _ft in self.listdir(cur):
                if name == p:
                    found = ino
                    break
            if found is None:
                return None
            cur = found
        return cur

    # ---------------- xattrs ----------------
    def xattrs(self, ino):
        """Return list of (fullname, value, location) where location is
        'inline' or 'external@block'."""
        i = self.inode(ino)
        res = []
        # inline: starts right after the extra inode fields
        if self.inode_size > 128:
            start = 0x80 + i["extra_isize"]
            if i["extra_isize"] and start + 4 <= self.inode_size:
                magic = struct.unpack_from("<I", i["raw"], start)[0]
                if magic == EXT4_XATTR_MAGIC:
                    res.extend(self._xattr_entries(i["raw"], start + 4, ino,
                                                   base_inode=True, where="inline",
                                                   limit=self.inode_size))
        if i["file_acl"]:
            blk = i["file_acl"]
            b = self.blk_read(blk)
            if struct.unpack_from("<I", b, 0)[0] == EXT4_XATTR_MAGIC:
                res.extend(self._xattr_entries(b, 32, ino, base_inode=False,
                                               where="external@block%d" % blk,
                                               limit=self.blk))
        return res

    def _xattr_entries(self, buf, pos, ino, base_inode, where, limit):
        out = []
        while pos + 16 <= limit:
            e_name_len = buf[pos]
            e_name_index = buf[pos + 1]
            e_value_offs = struct.unpack_from("<H", buf, pos + 2)[0]
            e_value_block = struct.unpack_from("<I", buf, pos + 4)[0]
            e_value_size = struct.unpack_from("<I", buf, pos + 8)[0]
            if e_name_len == 0:
                break
            name = buf[pos + 16:pos + 16 + e_name_len].decode("latin-1")
            prefix = XATTR_INDEX.get(e_name_index, "idx%d" % e_name_index)
            # inline values are offsets into the whole inode
            if base_inode:
                val = self.inode_raw(ino)[e_value_offs:e_value_offs + e_value_size]
            else:
                val = buf[e_value_offs:e_value_offs + e_value_size]
            out.append((("%s.%s" % (prefix, name)) if not prefix.startswith("system.posix")
                        else prefix, val, where,
                        {"name_index": e_name_index, "value_offs": e_value_offs,
                         "value_block": e_value_block, "value_size": e_value_size}))
            pos += 16 + ((e_name_len + 3) & ~3)
        return out


def cmd_info(img):
    fs = Ext4(img) if False else None
    with open(img, "rb") as f:
        f.seek(1024)
        s = f.read(0x400)
    g = lambda o, fmt: struct.unpack_from(fmt, s, o)[0]
    inode_size = g(0x58, "<H") or 128
    print("%-46s inode_size=%-4d blk=%d incompat=0x%08x ro_compat=0x%08x desc=%d uuid=%s vol=%r" % (
        img.split("\\")[-1] if "\\" in img else img.split("/")[-1],
        inode_size, 1 << (10 + g(0x18, "<I")), g(0x60, "<I"), g(0x64, "<I"),
        g(0xFE, "<H"), s[0x68:0x78].hex(), s[0x78:0x88].split(b"\0")[0].decode("latin-1")))
    print("    features: incompat=0x%08x compat=0x%08x ro=0x%08x  last_mounted=%r" % (
        g(0x60, "<I"), g(0x5C, "<I"), g(0x64, "<I"), s[0xC8:0xC8 + 64].split(b"\0")[0].decode("latin-1")))


def cmd_path(img, paths):
    fs = Ext4(img)
    print("== %s (inode_size=%d, blk=%d)" % (img, fs.inode_size, fs.blk))
    for p in paths:
        ino = fs.lookup(p)
        if ino is None:
            print("   %-28s MISSING" % p)
            continue
        i = fs.inode(ino)
        print("   %-28s ino=%-6d mode=0%o size=%-6d links=%d flags=0x%08x file_acl=%d extra_isize=%d" % (
            p, ino, i["mode"], i["size"], i["links"], i["flags"], i["file_acl"], i["extra_isize"]))
        for name, val, where, meta in fs.xattrs(ino):
            disp = val.decode("latin-1", "replace") if all(32 <= c < 127 for c in val) else val.hex()
            print("        xattr %-24s %-18s %s  %s" % (name, where, disp, meta))
        if i["mode"] & 0xF000 == 0x4000:
            kids = list(fs.listdir(ino))
            print("        entries: %s" % ", ".join("%s#%d" % (n, ii) for n, ii, _ in kids))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode = sys.argv[1]
    if mode == "info":
        for a in sys.argv[2:]:
            cmd_info(a)
    elif mode == "path":
        cmd_path(sys.argv[2], sys.argv[3:])
