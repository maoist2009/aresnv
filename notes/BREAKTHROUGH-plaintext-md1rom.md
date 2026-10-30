# ares md1rom — corrected ISA finding (2026-10-18)

## The ISA question is resolved: ares md1rom is little-endian MIPS16

Earlier notes (and `notes/PANDORA.md` §8.3/§8.4) concluded "no ISA fits /
the image is opaque". That was a **false negative**. Measured properly:

| region of `md1rom_eng_p11.rom` | full-byte entropy | high-byte (opcode-half) entropy |
| --- | --- | --- |
| `0x400000` | 7.278 | **6.24 – 6.43** |
| `0x1000000` | 7.246 | **6.39** |
| `0x1818000` (strings) | 5.396 | — |

Full-byte entropy ~7.3 is **normal for compiled MIPS16**: the instruction's
low half is an immediate/operand byte and is nearly uniform. The decision
statistic is the **opcode half** (the odd-offset byte = bits 15:8), and its
entropy is only ~6.3.

Its 16-value bin profile maps exactly onto MIPS16 opcode classes, with the
proportions real compiled code shows:

| bin | permille | MIPS16 class |
| --- | --- | --- |
| `00-0f` | 111–181 | `ADDIU rx, sp/pc, imm8` (stack/PC-relative) |
| `10-1f` | 108–166 | `B`, `JAL` |
| `20-2f` | 97–137 | `BEQZ`, `BNEZ` |
| `30-3f` | 43–68 | `BTEQZ`, `BTNEZ` |
| `80-8f` | 163–185 | `LB`, `LH` |
| `90-9f` | 44–91 | `LW (sp)` |
| `b0-bf` | 35–50 | `LW` (pool) |
| `c0-df` | 71–101 | `SB`, `SH`, `SW` |
| `e0-ff` | 36–42 | `JR/JALR/MOV`, `EXTEND` |

Loads (`80-bf`) ≈ 23 %, stores (`c0-df`) ≈ 10 %, `addiu sp` heavy, `jal` ≈ 4 %.
This is textbook compiled MIPS16.

**All builds are the same kind of content** — the shipping V3.P2 image
(`md1img_a_now.bin`, byte entropy 7.31) is not "encrypted"; it measures the
same as the P11 engineering build. So the old "shipping = encrypted, P11 =
plaintext" split in this file's earlier revision was wrong, and so was the
"encrypted" reading. What remains true: two different builds
(`md1rom_donor_a.rom` vs `md1rom_eng_p11.rom`) match ~96 % inside a 1 KB
window, which is impossible for encrypted data and confirms plaintext code.
(The ~0x1BC0 window shift between those two builds is just a per-build
layout shift.)

## The remaining blocker is instruction *alignment*, not the ISA

MIPS16 instructions are 2-byte units with 2- and 4-byte encodings. A start
offset that is wrong by 2 bytes still decodes into a *fully plausible*
2-byte stream, so no statistic (`.hword%`, opcode counts, branch-target
checks) can recover the phase. Linear disassembly therefore only works from a
true instruction boundary. What is needed:

* the image entry point / a known function entry, **or**
* a disassembler that discovers entries heuristically (rizin/radare2 with
  `asm.arch=mips` + `asm.bits=16`, Ghidra's Sleigh MIPS16, or GNU MIPS
  binutils on an ELF wrapped with `EF_MIPS_ARCH_ASE_M16`).

`tools/mips16.py` is biloba's *subset* decoder; its coverage is fine, but it
cannot self-sync.

## md1rom internal layout

`MMM\x01` + u32 size + NUL-terminated name, five headers, all in the first
0x900 bytes:

```
0x00000400  MMM.8...FILE_INFO...      (size 0x38, name "FILE_INFO")
0x00000568  MMM.|...
0x00000604  MMM.....
0x00000818  MMM.....
0x00000830  MMM.....
```

So md1rom = small header area (0x0–0x900) + ~24 MB of code/program data
(0x900–~0x17F0000) + data/strings (~0x1800000–end). The 0x0–0x900 area is
*not* a simple code start: `0x0` = `c0 60 80 2c e4 01 c0 d8` does not decode
as a valid instruction at offset 0, and the same 8 bytes re-appear at 0x84e
inside an MMM block — treat 0x0–0x900 as headers, not entry code.

## The gate strings are not referenced by any stored pointer

Searched `md1rom_eng_p11.rom` for a u32 value `V` such that
`V - base == gate_string_file_offset` across every plausible base
(0, 0x200, 0x80000000, 0x8FFD2000, 0x90000000, 0xE0000000, 0xE0000200).
Also histogrammed the *implied* base (`V - offset`) over every 4-aligned
u32 in the image and in the code region separately: **no dominant value**,
i.e. no real references — the top candidates are all noise.

The gate strings (`custom/service/nvram/custom_nvram_sec.c`,
`custom_nvram_check_signed_critical_data return %d`,
`custom_nvram_get_product`, `custom_nvram_check_cpuid`, ...) live at
`0x1818b9c … 0x1818fe4`. There **is** a 745-entry pointer table at file
`0x1A4C804` (VA `0x91A1E804` with base `0x8FFD2000`) whose entries do point
at these strings, but **no code loads that table either** (0 hits for 8-bit
and ext-form op-22 pool loads targeting it).

Conclusion: the log strings are almost certainly consumed by the *PC-side*
log parser via a build-baked ID table, not materialised by the modem code.
Therefore "find the string reference, walk back to the function" — the
method that solved biloba — **cannot** be used on ares. The gate can only be
found by real disassembly + logic analysis, or by taking apart the known
seller patch.

## The seller/"Patch CERT" patch is exactly 8 bytes

`bkp_head/md1img_b_cur.bin`'s md1rom payload (`file 0x200 …`) differs from
pristine `md1rom_eng_p11.rom` by **8 bytes in 2 runs of 4**:

| payload off | file off (b_cur) | stock | patched |
| --- | --- | --- | --- |
| `0x00222eb0` | `0x002230b0` | `34 1e 31 fc` | `01 d2 e0 db` |
| `0x00223714` | `0x00223914` | `33 1e c0 00` | `01 d2 e0 db` |

Both sites are 4-aligned and immediately follow an `11 1f` halfword. Read as
MIPS16 with the `11 1f` as the start of a 4-byte `jal` (op 3):
stock `jal <t1>` / `jal <t2>` with `t2 = t1 - 4`; patched both `jal <tp>`.
The following halfword also changes (`31 fc` / `c0 00` → `e0 db`). If instead
the sites are instruction starts, the patched halfwords decode as
`sw v0, 4(sp)` + `sw v1, 0(a3)` — i.e. **the patch removes a call**.
Either way this is the shape of a "skip the check" patch, and it is the only
known-working modification of this modem.

Caveat: the surrounding region does not decode cleanly (alignment unknown),
and the same pattern can be produced by a plain table. Resolving this needs
disassembly with correct alignment.

## Next steps

1. **Get a MIPS16 disassembler with function discovery** and locate
   `custom_nvram_*`; patch the signed-critical-data check; refresh cert2 via
   `tools/md1img_cert.py`; flash to `md1img_a` (`/dev/block/sdc19`).
2. **Cheap device experiment**: flash `eng_p11 + the 8-byte seller patch`
   (digest refreshed) *and* write the IMEI NV items (`out/LD0B_001.bin`
   plus whatever else `NVD_IMEI` needs), then read back `+ENVSIGERR`,
   `AT+EGMR` / `AT+CGSN`.
3. Do not patch the image blind; always refresh the cert2 digest.
