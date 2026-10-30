# Pandora "修复 IMEI" — fully reverse-engineered (ares / MT6893)

Status: **SOLVED, byte-for-byte validated, and reproduced with a free GPLv3 tool.**

Date: 2026-10-18

---

## 1. What Pandora actually does

Its own log (Chinese) is a precise recipe:

```
读取 IMEI...                确定            <- derives the IMEI for this CPUID
IMEI 1: 86xxxxxxxxxxx                     -+
IMEI 2: 86xxxxxxxxxxx                      |
写入 IMEI [NVDATA]...        确定            |  (1) write NV item LD0B_001 + FILELIST
写入 IMEI [NVRAM]...         跳过（容器损坏）  |      (nvram skipped: container corrupt)
加载用于打补丁的分区中...       确定            |
正在修补调制解调器签名...       确定            |  (2) patch md1img: code sites + rebuild cert2
保存已打补丁的分区中...        确定            |
正在验证已刷写的桩代码...       确定            <- verifies the patched bytes
正在格式化 "para" 分区...      确定            <- (3) erase `para` (NOT explained, see 1.1)
修复安全完成！
```

### 1.1 The `para` step is NOT explained (correction, 2026-10-23)

The recipe above is byte-exact for steps (1) and (2). Step (3) is **not**:
we never proved why the tool reformats `para`, and we cannot reproduce it.

What `para` actually contains (both dumps are 512 KiB, only `ENV_v1` is used):

```
analysis/raw/seller_para.bin   (seller-repaired device, works)
    ENV_v1
    md1_ccb_cap_gear=4
    md1_ccb_gear_list=1(2,20);2(2,10);3(0,0);4(2,30);11(2,2);12(2,62)

out/pandora/para.bin           (after Pandora's "format para")
    ENV_v1
    off-mode-charge=1
    md1_ccb_cap_gear=12
    md1_ccb_gear_list=1(2,20);2(2,10);3(0,0);4(2,30);11(2,2);12(2,62)
```

* no IMEI, no NV item, no key material — it is an LK/bootloader env block;
* the two images differ exactly where the seller's working device and a
  Pandora-formatted device should differ (`cap_gear`, `off-mode-charge`),
  so **`para` does not gate the IMEI**;
* best guess (unproven): after replacing `md1img`, stale AP<->modem CCB gear
  values are dropped so LK renegotiates them.  It is hygiene, not IMEI.

The `md1img` half of the claim stands (0 diffs vs Pandora's slot A and vs the
seller's P51 image).  The word "fully" applied to the whole recipe was too
strong.

There is **no secret key material involved**. The whole thing is:

* a **4-byte × 2 code patch** inside `md1rom`, and
* a **deterministic rebuild of the `cert2` (signature) section of `md1rom`**, and
* writing the **IMEI into the normal NV item `LD0B_001`** (the same item any
  free tool can write), and
* erasing `para`.

---

## 2. The `md1img` transformation (the whole "Patch CERT")

### 2.1 Code patch

In the `md1rom` payload, two 4-byte sites are replaced, each preceded by the
marker bytes `11 1f`:

```
11 1f  34 1e 31 fc   ->   11 1f  01 d2 e0 db
11 1f  33 1e c0 00   ->   11 1f  01 d2 e0 db
```

* The 6-byte anchors `11 1f 34 1e 31 fc` and `11 1f 33 1e c0 00` are **unique**
  in every build tested (the bare 4-byte patterns are not — `33 1e c0 00`
  occurs 4–5 times).
* The **distance between the two sites is build-specific** (`0x860` for P25/P51,
  `0x894` for V3.P2) → always anchor on both patterns, never on a fixed delta.
* Both originals are replaced by the *same* 4 bytes `01 d2 e0 db`, i.e. the
  patched sites become a single common (no-op / always-pass) idiom.

### 2.2 `cert2` rebuild

The `cert2` section that follows `md1rom` is replaced. Let
`P` = the original `cert2` payload (957 bytes), and

```
H = sha256(md1rom GFH header  = image[md1rom_off .. md1rom_off+0x200])
D = sha256(md1rom payload     = image[md1rom_off+0x200 .. +size])
```

then

```
new_cert2_payload =
     03 82 03 be 00                 # wrapper
  + P                                # verbatim copy #1 (still holds the OLD hashes)
  + a0 58                            # DER: context[0], 88 content bytes
      06 07 60 86 76 93 16 02 04     #   OID (hash algorithm)
      03 21 00 H                     #   BIT STRING(33) = sha256 of the md1rom *header*
      06 07 60 86 76 93 16 02 01     #   OID (hash algorithm)
      03 21 00 D                     #   BIT STRING(33) = sha256 of the md1rom *payload*
  + P                                # verbatim copy #2

= 5 + 957 + 90 + 957 = 2009 bytes           (stock: 957 bytes)
```

The `cert2` GFH header keeps everything except its size field → `2009`.
Everything after `cert2` in the image is **shifted, unmodified, by**
`align(0x200+2009) - align(0x200+957) = 0x420` bytes, with 7 zero pad bytes.

### 2.3 Portability

| build | site 1 (file) | site 2 (file) | delta | cert2 |
|---|---|---|---|---|
| P25 (`SP.V1.P25`) | `0x22330c` | `0x223b6c` | `0x860` | 957 → 2009 |
| P51 (`SP.V1.P51`) | `0x223dda` | `0x22463a` | `0x860` | 957 → 2009 |
| P11 (`SP.V1.P11`) | *already patched* | — | — | 2009 |
| V3.P2 (`SP.V3.P2`) | `0x22b84c` | `0x22c0e0` | `0x894` | 957 → 2009 |

---

## 3. Proof

The tool `tools/patch_md1img.py` was fed **only the stock image** and compared
against images produced by the paid tools:

| stock input | reference | result |
|---|---|---|
| `md1img_stock_v12_5_3.raw` (P25) | `out/pandora/sdA.bin` — dumped from the device **after Pandora itself ran** | **0 differing bytes** |
| `md1img_a_donor.bin` (P51) | `bkp_head/md1img_b_patched.bin` — seller-patched | **0 differing bytes** |

Two independent references, two different builds, zero differences. The
transformation above *is* the commercial "Patch CERT" / "修补调制解调器签名".

---

## 4. Why the earlier in-place patch bricked the device

The previous attempt patched the same 8 bytes but then **only updated the old
hash field in place** (`cert2+0x1F3`, keeping `cert2` at 957 bytes).

```
my earlier image : cert2 = 957 bytes,  payload digest at +0x1F3
Pandora / seller : cert2 = 2009 bytes, payload digest at +0x3FC
```

Every genuine patch — Pandora's and both seller images — uses the **2009-byte**
form. The 957-byte in-place form is rejected by LK, which is why the device did
not come back. This was verified across all 9 held md1img images
(`tools/cert2_survey.py`): *only* the three genuinely-patched images have a
2009-byte first `cert2`, and *all* of them carry the digest at `0x3FC`.

---

## 5. What the patch does

Before: `AT+EFUN=1` → `ERROR` + URC `+ENVSIGERR: 1` (repeatedly, driven by the
ROM's RIL), `AT+CFUN?` → `4` (RF off), `AT+EGMR=0,7` → `+EGMR: ""`.

After the patch: `AT+CFUN?` → **`1`**, `AT+EGMR=0,7` →
**`+EGMR: "86xxxxxxxxxxx"`**, no `+ENVSIGERR`, `vendor.ril.imei.check` empty.

So the two patched sites sit on the modem's **signed-critical-data gate**
(`custom/service/nvram/custom_nvram_sec.c`: `dev_pub_key verify fail` /
`ciritical_data verify fail`), and making them always pass is what lets the
modem power RF and publish the IMEI that lives in `NVD_IMEI/LD0B_001`.

`+ENVSIGERR` is therefore **not** about the `para` partition's `ENV_v1` block
(that is only LK's plain key=value environment: `off-mode-charge=1`,
`md1_ccb_cap_gear=12`, …), even though the names look similar.

---

## 6. The NV side

Pandora writes, into `nvdata`:

* `md/NVRAM/NVD_IMEI/LD0B_001` — 384 bytes (`LDI\0`, LID `0xEF10`, 10 × 32-byte
  records: `[0]` = IMEI 1, `[1]` = IMEI 2, `[2..9]` = repeated constant), and
* `md/NVRAM/NVD_IMEI/FILELIST` — 45 bytes, byte-identical to the file we already
  had (`NV01A000\0NV01B000\0NV0S_000\0LD0B_001\0FILELIST\0`).

The IMEI values Pandora computed are exactly `86xxxxxxxxxxx` /
`86xxxxxxxxxxx` — the same ones derived independently by
`tools/imei_ld0b.py`. **The NV write was never the hard part; the modem gate
was.** With the gate patched, the ordinary NV write is sufficient.

Pandora also tries `写入 IMEI [NVRAM]` and logs `跳过（容器损坏）` — it refused to
write the durable copy because the `nvram` container is damaged on this device.

---

## 7. Why flashing Magisk root loses the IMEI again

Reported intel: *"刷 magisk root 会掉 imei，需要重新刷"* (after flashing Magisk root
the IMEI disappears and the repair must be re-run).

This is consistent with everything measured here:

* The IMEI on this device lives **only** as a non-default override in `nvdata`
  (`NVD_IMEI/LD0B_001`). The durable copy in `nvram` was **skipped** because that
  container is corrupt. `md/NVRAM/` also contains `SWCHANGE.TXT`, i.e. the
  modem tracks an "SW change" stamp and **rebuilds/regenerates its NVRAM tree**
  when it decides the software changed — a regeneration drops non-default
  overrides that it cannot re-derive.
* Flashing Magisk means flashing `boot`/`init_boot`/`vbmeta`, which changes what
  the boot chain presents to the modem. A modem NVRAM (re)initialisation then
  discards `LD0B_001`, and with it the IMEI.
* The **modem patch in `md1img` is not lost** by a Magisk flash (it lives in its
  own partition) — which is why the fix is reproducibly just "re-run the IMEI
  write", not "re-patch the modem".

Practical consequences for a free tool:

1. Always also write the IMEI to the **`nvram`** container (Pandora couldn't,
   because it was corrupt) — that is the copy that survives an NVRAM reset. Fixing
   the `nvram` container is therefore worth doing, and would make the repair
   durable across Magisk / ROM reflashes.
2. Prefer a boot state that does not trip a modem NVRAM regeneration; at minimum,
   **re-verify with `AT+EGMR=0,7` after any boot-image flash** and re-write
   `LD0B_001` if it is empty. `+ENVSIGERR` / `AT+CFUN?` are instant canaries.

---

## 8. Reproducing the fix for free (GPLv3)

```
# 1. obtain the stock md1img for the build that is running (fastboot / BROM dump
#    of the active slot, or the firmware package)
python tools/patch_md1img.py stock_md1img.bin patched_md1img.bin

# 2. flash it to the ACTIVE slot only (never to both, never keep the old one
#    in the other slot as the fallback needs a *matching* build)
fastboot flash md1img_a patched_md1img.bin

# 3. write the IMEI NV items (LD0B_001 + FILELIST) - see tools/imei_ld0b.py

# 4. reboot; verify with AT+EGMR=0,7 and AT+CFUN?
```

`tools/patch_md1img.py` is self-contained (stdlib only) and prints exactly what
it changed. It refuses to run if the anchors are not unique.

---

## 9. Artifacts

| file | meaning |
|---|---|
| `out/pandora/sdA.bin` | 64 MiB of slot A **after Pandora ran** — the ground-truth reference |
| `out/pandora/sdB.bin` | 64 MiB of slot B (untouched stock P25) |
| `out/pandora/para.bin` | `para` after Pandora erased it |
| `out/pandora/pd_LD0B_001.bin`, `pd_FILELIST.bin` | what Pandora wrote into `NVD_IMEI` |
| `out/repro_P25.bin`, `out/repro_P51.bin` | our reproduction from stock only |
| `tools/patch_md1img.py` | the GPLv3 patch tool (validated) |
| `tools/cert2_survey.py`, `cert2_template.py`, `find_sites.py`, `cmp_sections.py` | the analysis that established the above |
