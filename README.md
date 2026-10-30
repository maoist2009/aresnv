# ares-nv — free IMEI repair for Xiaomi MediaTek phones

GPL-3.0. Research outcome of reverse-engineering a paid "repair box" workflow
(Pandora) on a Redmi K40 Gaming (ares, MT6893 / Dimensity 1200), reduced to a
free, reproducible recipe and the format/structure analysis behind it.

> **This repository contains no device-specific data** — no IMEIs, serials,
> logs or firmware images. Only formats, algorithms and tools. Repair your own
> device; IMEI tampering is illegal in many jurisdictions — know your local law.

## TL;DR — the whole repair is two halves (they need each other)

```
1. modem gate bypass   python mtk.py --preloader <preloader> da patchmodem
2. identity write      python mtk.py da imei --write "<IMEI1>,<IMEI2>"
3. reboot, dial *#06#
```

* **Half 1 — md1img (modem firmware).** Two 6-byte instruction fragments
  implement Xiaomi's `custom_nvram_check_imei` gate ("fingerprint + pool
  anchor both failed"). Unpatched, the modem refuses to report *any* IMEI —
  even byte-perfect original NV data. The patch is **pattern-based** (site
  offsets move between firmware builds, the bytes do not; each pattern occurs
  exactly once per image):

  ```
  site1  11 1f 34 1e 31 fc -> 11 1f 01 d2 e0 db
  site2  11 1f 33 1e c0 00 -> 11 1f 01 d2 e0 db
  ```

  Patch both A/B slots to avoid slot roulette.

* **Half 2 — nvdata (identity).** The IMEI lives in NV item `LD0B_001`
  (LID 0xEF10): a 64-byte header + 10×0x20-byte entries
  (`entry[0]`=IMEI1, `entry[1]`=IMEI2). Each entry: nibble-swapped BCD IMEI +
  an *unkeyed* MD5-folded checksum. The payload is encrypted **on the phone**
  by the SEJ engine, keyed from the chip's HUK — offline encryption is
  impossible by design, so the tool lets the DA drive the modem's own crypto
  (`da imei --write` reads the partition, finds the magic, re-encrypts
  on-device, keeps the original header, writes back unmounted).

Verified end-to-end: `*#06#` reported deliberately absurd (but Luhn-valid)
IMEIs written exclusively with the free toolchain; the device was then
restored. See `notes/SUMMARY-NVDATA-AND-MD1IMG.md` for the full write-up —
structures, evidence chain, dead/alive controlled comparison, and the
negative results (the key is the chip HUK; stop looking for one in flash).

## Repo layout

```
notes/                analysis write-ups (start with SUMMARY-NVDATA-AND-MD1IMG.md,
                      then STATE.md for the chronological lab log)
tools/                the reusable scripts (see below)
guided_repair.py      interactive wizard (repo root)
repair.bat            Windows entry point for the wizard
refs/                 checksums of held evidence + mtkclient-local-additions.patch
```

## Guided one-click workflow

`repair.bat` (or `python tools/guided_repair.py`) starts an interactive wizard.
Nothing is hard-coded: on first run it asks for your mtkclient directory, an
optional preloader binary and a backup location, and stores them in
`~/.mtk_imei_repair.json`. Menu:

1. **device status check** — adb/root/radio state, no BROM needed
2. **full backup** — NV security set + both md1img slots into a timestamped
   folder. *Run this first, always.*
3. **repair IMEI** — asks for two IMEIs (Luhn auto-corrected), then ONE BROM
   session does everything (`da repair`: patch both md1img slots + write the
   IMEIs with on-device SEJ encryption). Prerequisites and warnings are shown
   inline (e.g. a wiped-nvdata device needs a donor container first —
   automatic rebuild is not supported yet).
4. **verify** — `*#06#` cross-check, registration state, LD0B file.
5. **restore NV set** — rescue: writes back the newest backup.

The `da repair` command (plus `da imei --write`, `da nvitem --encrypt` and the
pattern-based `patchmodem`) is implemented in our mtkclient checkout; the
exact diff is kept in `refs/mtkclient-local-additions.patch` for review and
upstreaming.

## tools/ — what each script is for

**Core recipe**

| script | purpose |
|---|---|
| `patch_md1img_generic.py` | firmware-agnostic gate patcher (scan & replace, refuses ambiguous input) |
| `imei_ld0b.py` | LD0B_001 item builder (`build-plain`: 64B header + plaintext entries, feed to `mtk da nvitem --encrypt`) |
| `validate_ld0b.py` | validate a LD0B item (header, entry layout, checksums) |

**Structure / offline analysis**

| script | purpose |
|---|---|
| `ext4x.py`, `ext4_tree.py` | minimal ext4 reader; dump & diff an nvdata tree (path, size, md5) |
| `sparse.py`, `simg2img.py`, `inspect_sparse.py` | Android sparse images |
| `gpt.py` | GPT partition table parsing (mind UFS 4 KiB sectors) |
| `analyze_raw.py` | quick structural summary of a raw partition dump |
| `diff_nv.py`, `diff_img.py`, `snapdiff.py` | image / NV-tree / snapshot differ |
| `nvnames_md1img.py`, `nvdefault_table.py`, `nv_catalog.py` | parse the modem's embedded NV catalog (names & default values) from md1rom |
| `payload_info.py`, `payload_dump.py` | Android OTA payload.bin reader/extractor |
| `binstr.py`, `hd.py` | generic strings / hexdump utilities |

One-off exploration probes from the investigation are not part of the repo.

## mtkclient

The recipe depends on [mtkclient](https://github.com/bkerler/mtkclient) (GPL-3.0).
This project's mtkclient checkout carries local additions — `da imei --write`,
`da nvitem --encrypt`, `da patchmodem` (now with the pattern-based gate patch)
— which are intended to be upstreamed; the essential patcher is standalone in
`tools/patch_md1img_generic.py`.

## Evidence policy

Firmware images, partition snapshots, device logs and every device identifier
are deliberately excluded from version control. Checksums of the held
evidence live in `refs/IMG-SHA256.txt` so the chain can be audited offline.

## License

GPL-3.0-or-later. Built on mtkclient (GPL-3.0) and knowledge from the open
MTK community (`shomykohai/mtk-payloads` settled the SEJ/HUK question).
