# ares NV / 基带修复项目 — 环境勘查笔记

> 设备：红米 K40 游戏增强版 = Poco F3 GT（国行），代号 **ares**，机型号 M2012K10C，SoC **MT6893**（Dimensity 1200），UFS 存储。

## 目标

- nvdata 分区丢失导致基带不工作。
- 目前商用工具（租的 "pandorabox"）能修，但没有免费方案。
- 目标：**通过对比修复前后分区变化，逆向出 NV 修改的真实机制**，做出一套免费、可 GPLv3 公开的实现。

## 设备当前状态

- 通过 USB 以 **WPD/MTP**（`USB\VID_0E8D&PID_2008`，FriendlyName `M2012K10C`）枚举。
- `adb devices` 为空、`fastboot devices` 为空 → 当前不在 adb/fastboot/BROM 模式。
- mtkclient 的 `.state`（上次会话）：
  - `flashmode=XFLASH`, `patched=true`, `flashtype=ufs`
  - `flashsize=255919652864` (~238 GiB)
  - `meid=<MEID-redacted>`
  - `target_config`: sbc/sla/daa=true, memread/memwrite=true, cmdC8=true

## 已发现的工件

| 位置 | 内容 |
| --- | --- |
| `D:\apps\mtkclient` | mtkclient（git 干净，只有未跟踪工件） |
| `D:\apps\mtkclient\{nvdata,nvcfg,persist,protect1,protect2}.img`, `nvram.bin` | **买来的"好"NV 包**（sparse 镜像） |
| `D:\apps\mtkclient\preloader_ares.bin` | preloader 备份 |
| `D:\apps\mtkclient\efuse_raw.bin`, `hwparam.json` | efuse / UFS CID 读取 |
| `D:\apps\mtkclient\backup\stock_*.img` | md 相关分区备份（10 个，每个恰好 200 MiB，疑似定长读回） |
| `D:\apps\mtkclient\eng\*.img` | md1img/scp/sspm/spmfw/audio_dsp 镜像 |
| `D:\temp\aresnv\` | 同上 NV 包 + `README.md`（说明"花钱买的、基带识别了"） |
| `D:\temp\upd\dist_aresnv\` | 该包的 Fragdown 分片分发版本（含 manifest.json 哈希） |
| `D:\temp\payload.bin` | 2.6 GiB OTA payload（疑似国行 ROM） |
| `D:\temp\boot.img`, `boot_b.img` | 各 128 MiB |
| `D:\temp\config\app_info` | 小米解锁工具（miflash_unlock）配置 |

`backup/stock_*.img` 文件头：`88 16 88 58` + 段名（`md1rom` / `tinysys-` / `hifi3_a_` …），是 MTK 签名的 md 分区镜像。

## 关键发现：这些分区内部是 ext4 文件系统

用 `tools/simg2img.py` 展开 sparse 镜像后可确认（superblock magic `0xEF53`）：

### nvdata（64 MiB ext4，挂载点 `/mnt/vendor/nvdata`）

```
md/NVRAM/INFO_FILE          # 1884B，"INFO" 头 + 表
md/NVRAM/NVD_IMEI/          # NV01A000(NV01B000/NV0S_000 — IMEI 项（"LDI" 头）
md/NVRAM/CALIBRAT/          # 125 个校准项（UL*/HL* ...）
md/NVRAM/NVD_DATA/          # 220 个数据项
md/NVRAM/NVD_CORE/  NVRAM/BACKUP/   # 空
APCFG/APRDCL/               # FILE_VER, AUXADC, MD_SBP
APCFG/APRDEB/               # BT_Addr, WIFI, WIFI_CUSTOM, GPS
md3/  md_cmn/
```

### nvcfg（32 MiB ext4，`/mnt/vendor/nvcfg`）
sensor 校准（als/gyro/mag/lux）、camera `cctNvramFile`、`agps_nvram.txt`。

### persist（~66 MiB ext4）
`data/0..32`（每个 16 KiB，疑似 key-value 存储）、`fdsd/`、`stability/`。

### protect1 / protect2（各 8 MiB ext4）
`md/` 下的 modem NV：`ER1D_002, LD40_001, LD81..97, MC00..06, MT00A/B, SL00/01,
ST33A/B, ST34A/B, ST36/37/38`（protect1 与 protect2 内容大体相同、互为备份）。

## NV 项文件格式（初步）

- 小文件带 4 字节 magic 头：`LDI\x00` 或 `INFO`。
- 例：`md/NVRAM/NVD_IMEI/NV01A000` = `4C 44 49 00 06 F0 01 00 10 00 00 00 ...`，前 0x40 字节像
  头（长度/类型/时间戳），0x40 之后是载荷（IMEI 项载荷呈加密/哈希状）。
- `NV01A000` 与 `NV01B000` 载荷完全相同 → IMEI 很可能不是明文存放，需进一步分析。

## 项目目录约定

```
D:\projects\aresnv\
  backups\      # 设备原始分区转储（修复前/后）
  dumps\        # 临时
  analysis\     # 镜像展开与对比
    raw\        # sparse -> 裸镜像
    extracted\  # ext4 解包出的文件树
  tools\        # simg2img.py / analyze_raw.py
  notes\        # 本文档
```

## 付费工具已定位（详见 `notes/PANDORA.md`）

- 工具：**Z3X Pandora**（`C:\Program Files (x86)\Pandora`，v10.3.2）。
- 它关心三个分区：**`nvdata` + `protect1` + `nvram`**。
- 每次操作前自动备份到 `z3x_backup\MTK\Xiaomi_Redmi K40 Gaming (Ares)\Repair Flash_<ts>\`
  （`nvdata.bin` 64 MiB / `protect1.bin` 8 MiB / `nvram.bin` 64 MiB，均为分区裸读）。
- 它要求 `nvdata` 分区**是有效 ext4 且已存在 `md/NVRAM/` 目录**，它只负责往里写 IMEI 项文件。

### 三个已知故障态

| 现象 | 原因 |
| --- | --- |
| `error (EXT4 init failed)` | 分区里不是 ext4 —— 被写进了**未展开的 sparse `nvdata.img`**（mtkclient `w` 不做 sparse 展开） |
| `error (NVDATA parent directory not found)` | ext4 有效但 `md/` 是空的（格式化后设备自建的默认 nvdata 没有 `md/NVRAM/`） |
| `操作失败：修复 IMEI 文件创建失败` | 上面任一步失败的统一收尾 |

## 待办 / 阻塞点

1. **让 nvdata 变成"有效 ext4 + 含 `md/NVRAM/`"**：
   写回展开后的捐赠镜像 `analysis\raw\nvdata.raw`（= 买来的 `nvdata.img` 展开，64 MiB）：
   ```powershell
   cd D:\apps\mtkclient
   python mtk.py w nvdata D:\projects\aresnv\analysis\raw\nvdata.raw
   ```
   然后重启再跑一次工具。
2. 修复前/后各 dump 一次 `nvdata`/`protect1`/`nvram` → diff（秘密就在 `md/NVRAM/NVD_IMEI/*`）。
3. 用"已知我机 IMEI + 工具产出的密文"确定 MT6893 的 NV 加密 key/格式。
4. 备份存放位置与磁盘空间（D: 仅剩 ~8.5 GB）。

## FIXED STATE (2026-04-01 ~02:00 device time) - the working repair

- modem (slot b, active): Patch-CERT'd md1img = bkp_head/md1img_b_patched.bin
    -> md1.status=ready, baseband=MOLY.NR15.R3.TC8.PR2.SP.V1.P51
- NV: the phone's OWN tree, regenerated once by the P51 modem (version match)
    -> modem no longer regenerates / deletes items
- IMEI item: md/NVRAM/NVD_IMEI/LD0B_001 (384 B) + FILELIST (45 B)
    -> decrypted from the LIVE image: IMEI1=86xxxxxxxxxxx  IMEI2=86xxxxxxxxxxx
    -> SURVIVES boot (md5 79268f2f, unchanged)
- vendor.ril.imei.check: NOT reported (with the stock modem it was 'fail')
    -> that prop is set from the modem's CME_BLOB_IMEI_MISMATCH error;
       the patched modem no longer reports a mismatch.

Restore points:
    backups/post/nvdata_FIXED.bin   (this state, md5 d4895d6a45f7100b0d0d3951ed5462ee)
    backups/post/nvdata_WORKING.bin (earlier P25 state, stock modem)
    bkp_head/md1img_b_patched.bin   (Patch CERT'd modem)
    analysis/raw/md1img_stock_v12_5_3.raw (stock V1.P25 modem)

ROM quirk: framework cannot SHOW the IMEI on this ROM - the MTK RIL advertises
IRadio < 2.1 so TelephonyManager.getImei() is refused ("getImei not supported on
service MODEM < 2.1"). Not an IMEI problem; verify via a SIM/network instead.

## Verdict (2026-10-17): we are at FULL PARITY with the paid tool

> **SUPERSEDED — see "2026-10-17 (late): the modem itself reports NO IMEI" at the
> bottom of this file.** Parity with the paid tool is parity with a tool that does
> not actually restore the modem's IMEI.

Re-checked everything with a real ext4 reader (`tools/ext4_tree.py`) and direct
binder calls, and the repair is complete:

- The paid tool's ENTIRE nvdata change = `+NVD_IMEI/LD0B_001`, `+NVD_IMEI/FILELIST`,
  `~INFO_FILE` (magic zeroed -> auto-rebuilt by the NV system), minor APCFG churn.
  We have byte-identical LD0B_001 (79268f2f) + FILELIST (e8ac8c2d), and our live
  INFO_FILE was rebuilt by the modem AFTER our write (so LD0B is indexed).
- `protect1` and all classic `NV01A000/1B000/NV0S_000` items use a per-device NVM
  key (verified: they do not decrypt with MTK's global key) -> they cannot be
  pre-generated and the tool's `protect1` write is device-specific junk the modem
  regenerates. `nvram` is all-zero in the seller package and on our device.
- The ROM cannot display the IMEI at all (proved three ways: verbose AT log shows
  no CGSN/EGMR ever sent; RILJ "getImei not supported on service MODEM < 2.1";
  `service call iphonesubinfo {1..6} s16 com.android.phone` -> clean null String).
  So Settings/`*#06#`/popups are a false negative on this ROM.
- `vendor.ril.imei.check` is the SIM-lock BLOB verdict (`AT+ESLBLOB`,
  `CME_BLOB_IMEI_MISMATCH`), not the IMEI value.
- NV item-set: the seller tree is a pre-OTA P25 NV (356 files); our device OTA'd
  it to P51 and dropped 58 legacy NVD_DATA items -> our 303-file tree is the
  correct P51 set, not a loss.

Open question that needs the device, not the code: does the modem's IMEI = ours?
Userspace cannot read it here (ttyC0 is kernel-claimed via CCCI; rild-atci needs
the RIL's private framing; no atcid binary). Authoritative checks are a SIM that
registers, or a META/AT read (what the paid tool does).

New tools added this session (all GPL-3.0-or-later under `tools/`):
  ext4_tree.py   real ext4 file-tree dump/diff (item-level NV comparison)
  sparse.py      Android sparse image -> raw (mtkclient/SP Flash reads are sparse)
  dis_elf.py     ELF64 symbol lookup + capstone AArch64 disassembly (reversing RIL)
  probe_iphonesubinfo.py  brute-forces IPhoneSubInfo binder codes
  dev_*.sh       on-device probes (AT channel, fd owners, RIL log switches)

## 2026-10-17 (late): the modem itself reports NO IMEI  [DECISIVE]

We finally got a direct AT channel into the running modem, so the question "does
the modem have the IMEI?" is now *measured*, not inferred.  It does not.

### How the channel was obtained (repeatable)

- The modem's AT channels are on /dev/ttyC0 (kernel CCCI), multiplexed by
  gsm0710muxd.  The muxer exposes each channel as a pty; rild holds the pty
  **slave** and writes AT into it.  **Writing an AT command to the same slave
  injects it into the modem.**
  - ATCI channel: `/dev/radio/atci1` -> `/dev/pts/5`  (muxer DLCI 61)
  - RIL main channel: `/dev/radio/pttycmd1` -> `/dev/pts/2` (muxer DLCI 26)
- Proof of delivery: the muxer logs it -
  `pseudo_device_read(): Data from channel 61, actual_read=9` then
  `write_frame(): Write data len=9 written=9 errno=0`.
- Proof of the return path: rild logs every raw modem line in the radio buffer,
  `logcat -b radio -d -s AT:V -v time`, attributed to a reader thread
  (`RIL_ATCI_READER` for the ATCI channel).
- AT logging only happens if `persist.log.tag.AT=V` was set **before rild
  started**; otherwise the buffer is empty.  Set it, then reboot.
- Reusable tool: `tools/at_probe.py` (GPL-3.0-or-later).

### The measurements

Control commands - the channel and the modem are healthy:

| command | modem answer |
| --- | --- |
| `AT+CGMI` | `+CGMI: MTK1` |
| `AT+CGMR` | `+CGMR: MOLY.NR15.R3.TC8.PR2.SP.V1.P51, 2021/11/29 20:17` |
| `AT+EGMR=0,4` | `+EGMR: "XIAOMI_R0MP2_K6893V1_64"` (product) |
| `AT+EGMR=0,9` | `+EGMR: "78"` (IMEI SVN - present!) |
| `AT+EGMR=0,13` | `+EGMR: "NLWCG_CUSTOM"` (market) |

Identity - **the IMEI is empty**:

| command | modem answer |
| --- | --- |
| `AT+CGSN` | bare `OK` - **no IMEI, no data line at all** |
| `AT+EGMR=0,7` | `+EGMR: ""` - **explicit empty string** (reproducible) |
| `AT+GSN` | `ERROR` |

`AT+CGSN` is the *exact* command MTK's own RIL uses: disassembly of
`RmcOemRequestHandler::requestGetImei` @ `0x2e7608` loads the string at
`0x2e76e8` = `"AT+CGSN"`.

Write attempts - all rejected, so the IMEI cannot simply be poked in over AT:

| command | answer |
| --- | --- |
| `AT+EGMR=1,7,"86xxxxxxxxxxx"` | `+CME ERROR: 100` |
| same, with radio off (`AT+CFUN=0`) first | `+CME ERROR: 100` / no effect |
| `AT+EGMR=1,7,"86xxxxxxxxxxx",78` | no effect |
| `AT+EGMR=1,7,86xxxxxxxxxxx` (unquoted) | `+CME ERROR: 100` |
| `AT+ESLBLOB=2` / `=5` / `=6` / `=7` | `+CME ERROR: 3` (operation not allowed) |

The RIL's own string table only contains `AT+EGMR=0,9` (read SVN) and
`AT+EGMR=1,9,"%s"` (write SVN) plus `AT+ESLBLOB=1,%d,"%s",%d` (write the signed
subsidy/IMEI blob).  **There is no IMEI write in the RIL at all** - the IMEI field
is deliberately not writable over the normal AT port (anti-tamper).

### The contradiction that settles it

Our NV item is intact and correct *in the file system*:

    /mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001   384 B  md5 79268f2fbc1ca2b3603c20084364a887
    /mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/FILELIST    45 B  md5 e8ac8c2d5ea0a05614a71a09d9c79ac1

decrypts (tools/imei_ld0b.py, AES-ECB, MTK global software key) to
**IMEI1 86xxxxxxxxxxx / IMEI2 86xxxxxxxxxxx** - byte-identical to the paid
tool's own output - and the md5s were unchanged through every probe and reboot.

Yet the modem answers `+EGMR: ""` and `AT+CGSN -> OK`.  So **the modem does not
read the IMEI from `LD0B_001`**, and the paid tool's entire footprint
(`+LD0B_001`, `+FILELIST`) is therefore **not sufficient to restore the IMEI**.

Same conclusion from the other side: after the paid tool's write the user still
saw "IMEI unknown" in Settings and `*#06#` - that was not a display quirk.

### What the modem does keep

- `NVD_IMEI/NV01A000` (96 B) and `NV01B000` (96 B): header `LDI`, lid 0xF006,
  then a 32-byte payload.  **The two payloads are byte-identical** - i.e. the same
  plaintext under the same key, AES-ECB style - and do not decrypt with MTK's
  global key: per-device NVM key.  `NV0S_000` (144 B, lid 0xF008) is the same
  story, 80 encrypted bytes.
- The modem's own identity fields (product name, SVN, market) *are* populated, so
  the modem is not blank in general - only the IMEI is missing.
- `AT+ESLBLOB` (the signed subsidy/IMEI blob path) is refused outright here
  (`+CME ERROR: 3`), so that is not the blocker either.

### Why the framework shows nothing either (secondary, but measured)

- `PhoneInterfaceManager.getImeiForSlot` returns null **before** touching the
  modem: `PhoneFactory.getPhone(slot)` may be null, or the
  `checkCallingOrSelfReadDeviceIdentifiers` permission gate fails (that is what
  our uid-1000 "android" probe hit).
- `getPrimaryImei` throws `UnsupportedOperationException("Operation not
  supported")` because no `Phone` reports `getImeiType() == IMEI_TYPE_PRIMARY`.
- Every AT log we captured (474 lines live, 110 AT commands at boot) contains
  **zero** CGSN/EGMR/IMEI traffic: the stack never asks the modem.
- Setting `persist.radio.imei` by hand changes nothing (the framework does not
  read that property on this build).

So there are two independent defects: the modem has no IMEI, and the framework
never queries it.  Fixing only the second would still show nothing.

### Consequence for the GPLv3 deliverable

> **SUPERSEDED (same day, second pass).** The META route below is wrong:
> Pandora has BOTH a non-META `Repair IMEI / Patch CERT` path (the file+DA path its
> log actually shows) and a separate `META Repair IMEI` menu entry - bundling
> `MetaCore.dll` does not mean the IMEI repair uses META.  The real blocker is a
> **Xiaomi-added modem-side check** (`custom/service/nvram/custom_nvram_sec.c`:
> `custom_nvram_check_imei` + `custom_nvram_check_signed_critical_data` +
> `devPubKeyModulus`), i.e. Xiaomi's own RSA-signed "critical data" that the NV
> IMEI must match.  `Patch CERT` / "patch modem signature" exists to patch that
> check out; on this md1img build the tool cannot locate it
> (`custom_nvram_check_imei: fingerprint + pool anchor both failed`).
> See PANDORA.md sections 7-8.

Writing `LD0B_001` + `FILELIST` is *not* the repair.  The three-part recipe in
PANDORA.md is necessary but **not sufficient**.  To make the modem actually
report the IMEI, the write has to happen where the modem accepts it:

1. **META / DIAG mode** - the modem's factory interface, where
   `AT+EGMR=1,7,"<imei>"` (and the per-slot equivalent) is *not* refused.  META is
   entered by a boot-mode flag (MTK `misc`/`para`) or a DA handshake; a free tool
   can set that flag with mtkclient's BROM/DA path **without touching nvdata**.
   This is the most promising route and matches what the commercial tools do
   (Pandora bundles MTK's official `MetaCore.dll`).
2. Or find the item/lock path that makes the running modem import the IMEI from
   its NV (unresolved; the `protect*` items that carry it are per-device keyed).
3. Or patch the Xiaomi check out of md1img (what `Patch CERT` does) - string
   evidence and the exact strings are in PANDORA.md section 8.

The AT harness (`tools/at_probe.py`) makes (1) verifiable: after a META write,
`AT+CGSN` / `AT+EGMR=0,7` on the normal channel must return the IMEI.

### Device state after this session

Restored: SELinux Enforcing, `persist.sys.root_access` / `persist.radio.imei` /
`persist.radio.imeisv` / `persist.vendor.service.atci.sim` cleared, device-id
appops reset, adb forwards removed, all /data/local/tmp artifacts deleted, one
reboot.  Baseband P51, `vendor.mtk.md1.status=ready`, rild running, SIM absent.
`persist.log.tag.AT=V` was left in place - it is the observation channel, it is
harmless, and removing it needs another restart.

================================================================================
2026-10-18  UPDATE -- SOLVED.  See notes/PANDORA-REVERSE-ENGINEERED.md
================================================================================

Pandora's "修复 IMEI" was run on this device and SUCCEEDED (IMEI live:
AT+EGMR=0,7 -> +EGMR: "86xxxxxxxxxxx", AT+CFUN? -> 1).  Its exact
transformation was then reproduced byte-for-byte from a stock image alone, so
the paid step is now available for free under GPLv3:

    tools/patch_md1img.py            (validated: P25 == Pandora's own output,
                                      P51 == seller's patched image, 0 diffs)

The "Patch CERT" / "修补调制解调器签名" step is:

  1. md1rom payload, two 4-byte sites (anchors 11 1f + 4 bytes, unique):
         11 1f 34 1e 31 fc -> 11 1f 01 d2 e0 db
         11 1f 33 1e c0 00 -> 11 1f 01 d2 e0 db
     (site distance is build-specific: 0x860 P25/P51, 0x894 V3.P2)
  2. first cert2 rebuilt 957 -> 2009 bytes:
         03 82 03 be 00 + OLD + a0 58{hashblock} + OLD
     hashblock = 06 07 ..02 04 03 21 00 <sha256 md1rom header>
                 06 07 ..02 01 03 21 00 <sha256 md1rom payload>
     cert2 GFH size := 2009, everything after shifts +0x420 (7 pad bytes).

WHY THE OLD ATTEMPT BRICKED: we had patched the same 8 bytes but only refreshed
the OLD digest in place (cert2 stayed 957, digest at +0x1F3).  Every genuine
patch uses the 2009-byte form with the digest at +0x3FC.  Never ship the
in-place form.

NV SIDE (Pandora): writes nvdata/md/NVRAM/NVD_IMEI/LD0B_001 (384 B) +
FILELIST (45 B, byte-identical to ours), then erases `para`.  The IMEI values
(86xxxxxxxxxxx / 86xxxxxxxxxxx) are what tools/imei_ld0b.py already derives.
It tried "写入 IMEI [NVRAM]" and skipped it: the nvram container is corrupt
(sdc40 reads as all zeros), so there is no durable copy of the IMEI.

MAGISK INTEL EXPLAINED: /mnt/vendor/nvdata/md/NVRAM/SWCHANGE.TXT now reads
"OTA from MOLY.NR15.R3.TC8.PR2.SP.V3.P2 to MOLY.NR15.R3.TC8.PR2.SP.V1.P25...",
i.e. the modem tracks a software-change stamp and REGENERATES its NV tree when
it decides the software changed.  A regeneration drops non-default overrides,
and the IMEI is only such an override (nvram is empty) -> IMEI gone.  Hence a
boot/ROM flash can require re-running just the IMEI write, while the md1img
patch itself survives.  Durable fix = also populate nvram (repair the container).

DEVICE STATE at time of writing: slot A = P25 + Pandora patch (2009 cert2),
slot B = untouched stock P25, IMEI live, RF on, SIM absent, adb root ok.
Stock slot-A restore image (pre-everything) = analysis/raw/md1img_a_now.bin.

================================================================================
2026-10-18  OFFLINE RESEARCH: LD0B FORMAT + WHERE THE KEY LIVES
================================================================================
Device is away; everything below is from on-disk artifacts + the Pandora binary.

1) LD0B ENTRY FORMAT is now authoritative (mtkclient mtk_da_handler.py, same
   code path as `da imei --write`):
        data  = encode_imei(imei) + 00 00            (10 B, little-endian BCD)
        csum  = MD5(data[:10])[0:8] XOR [8:16]        (8 B)
        entry = data + csum + 00 * 0x0E               (32 B)
        empty = FF*10 + csum(FF*10) + 00*0x0E
   File = 64 B LDI header + 10 entries.  Our three Pandora samples match it.

2) HEADER attr (offset 0x0c) = 0x00402a on ares:
        bit3 (0x08) -> swcrypt = 1
        bit5 (0x20) -> cryptmode = HW_ENCRYPTED_5G (2)
   mtkclient then calls the DA custom command CUSTOM_SEJ_HW (0x0F000B) with
   otp(32 B) + seed(8 B) + aeskey(32 B) and lets the DA/SEJ do the AES.

3) KEY MATERIAL
        otp    <- preloader bytes at "MMM\x01\x30" + 0xC   -> ALL ZERO on ares
        seed   <- constant b"12abcdef"
        aeskey <- constant 01 02 .. 1C 00 00 00 00
   SEJ derives the real key through R2K|BK2C (chip root key).  Per-chip,
   not present in any flashable partition.

4) PROOF THAT PANDORA HAS NO OFFLINE KEY (240 MB memory dump of the unpacked
   process):
        MTK SST nvsw_kgen constant .......... 0 occurrences
        g_aes_swotp / g_UnqKey_* ............ 0 occurrences
        CustomSeed .......................... 0 occurrences
        "12abcdef" .......................... 1 occurrence (DA argument only)
        AES S-box / inverse / rcon .......... present (software AES available,
                                               used by FireDAC + seccfg/RSA code)
   Pandora's own unit names recovered: uPndCrypto, TPndRsa, MTKCryptoInfo,
   TNvItem, MTKops_ReadImei.  Message table shows the full flow including
   "Repair crypto detection failed", "Check seccfg key...",
   "NVDATA IMEI structure is incomplete. Restore it?", "V1 write: %s",
   "Update IMEI signature failed", and the four write paths
   [NVDATA] / [NVRAM] / [OTP] / [RPMB] / [LG].
   Pandora also ships its own ext4 writer (C:\PND\FS\uMakeExt4.pas) to
   recreate md/NVRAM/NVD_IMEI + INFO_FILE on a blank nvdata.

5) NEGATIVE RESULTS (do not repeat):
   - 32 B seed scan over protect1 / nvdata tree / md1img (aligned + full)  -> 0
   - AES key scan (IV-independent oracle) over protect1 (1.38 M windows),
     persist / nvcfg / proinfo / protect2 / seccfg                        -> 0
   - MTK default / BU vt / Samsung seeds, raw and via SST_Get_NVRAM_SW_Key -> 0
   - MEID / CPUID / UFS CID+SN derived seeds (76 combos)                   -> 0
   - RC4 / stream cipher ruled out (full 16-byte avalanche on IMEI change)
   - "LD0B is only a signature" ruled out (IMEI exists nowhere in plaintext)

6) THEREFORE the free GPLv3 route is NOT a key: it is to let the phone encrypt,
   exactly like the paid tool:
        python mtk.py da patchmodem
        python mtk.py da imei --write "IMEI1,IMEI2"
   Caveat: `da imei --write` needs an existing LD0B_001 in nvdata.  The official
   ROM ships no nvdata.img; the "全字库" nvdata.img is a blank ext4 (only
   lost+found + empty md), so a wiped device needs the container recreated
   first (Pandora does it with its ext4 writer; mtkclient cannot yet).

7) NEW HYPOTHESIS for the current "both IMEIs empty" state: the IMEI has a
   second, signed copy.  IM03_001 is a 40-byte record with an 8-byte trailer
   that the modem rewrites on every boot, and Pandora has an explicit
   "Update IMEI signature failed" step.  Restoring LD0B alone would then leave
   the signature stale.  Needs verification once the phone is back.

Full write-up: notes/IMEI-CRYPTO-AND-FREE-PATH.md

--------------------------------------------------------------------------------
2026-10-18 (2)  SOURCE-LEVEL PROOF: THE KEY IS THE CHIP'S HUK
--------------------------------------------------------------------------------
Upstream source for the DA extension (da_x) is public: shomykohai/mtk-payloads
(da_x = AGPL-3.0, common/crypto/sej = MIT).  It settles the question:

    sej.c      : case AES_HW_KEY -> sej_aes_kdf(true)  /* HRK256 */
                 legacy     -> ACONK |= SEJ_AES_BK2C  /* "Bind HUK" */
    sej_hk.c   : SEJ_V3_init() sets ACONK = BK2C|R2K and calls sej_aes_kdf()
                 "BK2C = Bind Hardware Unique Key"
    commands.c : sej_init(g_da_ctx.sej_base)  <- the DA just drives MMIO that
                 the host configures; no key material crosses the wire.

So the LD0B session key is f(chip HUK, fixed patterns).  HUK is burned into
the SoC.  => The ciphertext can only be produced on the phone.  This is now
proven from source, not inferred: STOP looking for an offline key.

The AES S-box inside da_x.bin belongs to the software paths
(SW_ENCRYPTED / TZCC), not to SEJ.

Other verified corrections (2026-10-18):
  * IM03_001 trailer is NOT a keyed MAC.  It is calc_checksum(rec[0:0x18],
    0x18) = MD5 folded -- the same unkeyed function as the LD0B entry
    checksum.  Reproducible offline.  Record payload does not contain the
    IMEI text, so its role in the IMEI chain is still unverified.
  * KDF brute force around the DA arguments (6 684 candidates: permutations of
    seed/aeskey/otp/LID/attr/header through md5/sha1/sha256/sha512/blake2s/
    blake2b, plus AES-ECB and AES-CMAC derivations) -> 0 hits.
  * tools/imei_ld0b.py corrected: the old docstring claimed offline generation
    with MTK's global seed.  Decrypting the real Pandora item with that seed
    yields garbage for every entry (all "BAD CHK").  Added `build-plain`
    (emits the 64-byte header + 320 bytes of clear entries, to be fed to
    `mtk.py da nvitem --encrypt`), and `build` now prints a warning.

--------------------------------------------------------------------------------
2026-10-24  DEVICE BACK ONLINE: FULL TARGETED SNAPSHOT + STATE DISCOVERY
--------------------------------------------------------------------------------
* Device rooted (su uid=0), BL reports locked (green) — likely fake-locked seccfg.
* Radio ALIVE: LTE cells visible (CHN-CT, rsrp -91), but OUT_OF_SERVICE,
  no mBasebandVersion, iphonesubinfo = -4  ->  classic no-valid-IMEI state.
* SNAPSHOTTED 28 partitions -> backups/snap_20261024/ (742 MB, on-device sha256
  == PC sha256; nvdata double-read identical, no live churn). Full list:
  misc para expdb frp nvcfg nvdata metadata persist protect1 protect2 seccfg
  otp sec1 proinfo efuse nvram boot_para gsort ffu mem oops oem_misc1 backup1-5.
* Inventory of D:-drive images done: notes/IMG-INVENTORY.md, refs/IMG-SHA256.txt.
* nvram identical to ALL previous states (x14 finding holds: never touched).
* para == out/pandora/para.bin (still Pandora post-format rebuild state).
* nvdata / protect1 / nvcfg match NO known snapshot -> device is in a NEW state
  (changed after 10-18).
* KEY FINDING: nvdata_WORKING (= nvdata_beforeLD0B, IMEI-alive state) has NO
  LD0B_001 and NO FILELIST in md/NVRAM/NVD_IMEI — only NV01A000/NV01B000/NV0S_000.
  The CURRENT (dead-IMEI) nvdata HAS LD0B_001 (384B, attr 0x402a) + FILELIST,
  NV01A/B header field differs slightly (0x102f4 vs 0x1032d @0x28), IM03_001 is
  the stock default (mtime = image build date).
  => Model correction: the IMEI-alive state carried IMEI in NV01A/B WITHOUT any
  LD0B_001.  LD0B_001 arrived with the 10-17 23:46 Pandora/tool writes and the
  IMEI has been dead since.  Leading hypothesis: stale/mismatched LD0B_001 makes
  custom_nvram_check_imei ("fingerprint + pool anchor") fail and the modem
  refuses the IMEI even though NV01A/B look valid.
* protect1 diff (cur vs WORKING): ER1D_002, MT00A001, MT00B001 + Journal differ.
* NEXT: experiment #1 = restore WORKING suite (nvdata_WORKING + nvcfg_WORKING +
  protect1_WORKING) via BROM (unmounted), reboot, check IMEI.  If IMEI returns,
  the free-path algorithm must NOT write LD0B_001; revisit what Pandora really
  needed it for (maybe only when nvdata is fully wiped).

--------------------------------------------------------------------------------
2026-10-24 (2)  DEAD<->ALIVE CONTROLLED COMPARISON — SECOND GATE IS NOT IN NV
--------------------------------------------------------------------------------
* Device NOW WORKS (IMEI present, can call; user reports Pandora fixed it again).
* Captured BOTH states today:
    backups/snap_20261024/         (00:19, IMEI dead)  28 partitions, sha-verified
    backups/snap_20261024_working/ (IMEI alive)        31 partitions (incl. md1img a/b
                                                       + lk a/b), sha-verified
* RESULT: all 27 NV/security partitions byte-IDENTICAL between dead and alive:
  nvdata, nvram, protect1/2, nvcfg, persist, seccfg, otp, para, proinfo, misc,
  expdb, metadata ... EVERYTHING SAME.
  => The "second gate" is NOT in ANY flash NV partition.  IM03_001-stale-
     signature hypothesis is DEAD.  nvdata content is a deterministic function
     of (IMEI, HUK) — rewrites produce identical bytes.
* md1img_a/b (captured only in alive pass) match NO known image (a_now, donor,
  stock v12.5.3, all repro builds).  working_a vs stock = 27.6MB diff / 1868
  ranges (modem version much newer than stock ROM).  lk_a == lk_b == old lk_b.
* NEW MODEL: the gate is the md1img PATCHED state itself — the modem-side
  custom_nvram_check_imei ("fingerprint + pool anchor") validates NV against
  code/data inside md1img.  Dead-IMEI eras correlate with md1img lacking the
  correct patched cert, NOT with NV content.  This also explains why writing
  the ORIGINAL LD0B back (10-18) did not revive IMEI, and why the WORKING
  nvdata of 10-18 had no LD0B at all (NV-side content is nearly irrelevant;
  the modem patch is what matters).
* LESSON: md1img must be captured in EVERY future snapshot (200MB each, cheap).
* NEXT: (1) get today's successful Pandora log from user; (2) check the two
  4-byte code sites + cert2 in working md1img vs our P25/P51 recipe; (3) the
  free-path algorithm = patch_md1img on the CURRENT md1img base + deterministic
  NV write (NV write may even be optional in this episode).

--------------------------------------------------------------------------------
2026-10-24 (3)  SMOKING GUN: md1img PATCH SITE — AND A/B SLOT ROULETTE
--------------------------------------------------------------------------------
* P25 patch site (11 1f 34 1e 31 fc -> 11 1f 01 d2 e0 db) per image:
    working_a (alive):  site 0x22330a = PATCHED (no orig bytes anywhere)
    working_b (alive):  site 0x22330a = ORIGINAL (unpatched, stock-like)
    a_now  (dead era):  site 0x22b84a = ORIGINAL (unpatched; different modem ver)
    b_cur  (dead era):  no orig hits (patched at its shifted sites)
    stock v12.5.3:      site 0x22330a = ORIGINAL (reference)
* Active slot = _a.  System = V14.0.5.0.TKJINXM (MIUI 14, Android 12) — NOT the
  V12.5.3 we kept as stock reference.  Explains the modem version zoo.
* UNIFYING THEORY for "后面经常成功/经常失败": A/B slot roulette.  IMEI works
  iff the md1img of the ACTIVE slot carries the patched cert/check bypass.
  10-17 11:54 run wrote patch + NV but boot landed on the unpatched slot ->
  no IMEI.  Later runs succeeded when the patched slot was active.
* Free-path recipe (now concrete):
    1. determine active slot,
    2. run patch_md1img (adapted to the V14 md1rom layout) on BOTH slots,
    3. write NV deterministically — REQUIRED, not optional (user correction,
       "双向奔赴"): the two halves are complementary.  Patched md1img without
       correct NV -> gate open but no identity to report (original wiped-device
       failure).  Correct NV without patched md1img -> identity present but
       gate closed (10-18 original-LD0B-writeback failure).  In the 10-24
       controlled comparison NV was identical dead<->alive only because it was
       already correct; md1img was the sole delta in THIS episode.
* NEXT VALIDATION (safe, does not touch slot A): patch working_b (unpatched
  V14 base) with our tool, flash to slot B, reboot to B, check IMEI.  All
  states snapshotted; rollback = restore snap_20261024_working.

--------------------------------------------------------------------------------
2026-10-24 (4)  MILESTONE: FREE TOOL END-TO-END NV WRITE — FIRST SUCCESS
--------------------------------------------------------------------------------
* User ran bat/1_write_absurd_imei.bat (mtk da imei --write, BROM, with
  --preloader): SUCCESS on a manual attempt.  The previously-never-tested
  one-shot command works:
    read nvdata partition via DA -> find LD0B magic -> encode absurd IMEIs ->
    on-device SEJ re-encrypt -> write partition back.
* VERIFIED: *#06# showed 111111111111119 / 114514191981029 (both Luhn-valid).
  LD0B_001 ciphertext on device changed 7b5d2942.. -> 6d4e3f12.., header
  attr 0x402a preserved.  Evidence: analysis/absurd_test/LD0B_001_absurd.bin.
* Radio: modem reports the absurd IMEI but network registration does not
  complete (OUT_OF_SERVICE) — carrier-side rejection of junk IMEI, expected.
* NV side of "双向奔赴" now proven with OUR tool.  Free-path status:
    NV write   : PROVEN (this test)
    md1img patch: recipe known, P25/P51 byte-verified on V12.5.3; V14-base
                  end-to-end still untested (mtk da patchmodem exists)
  => GPLv3 replacement for the paid tool is functionally complete modulo the
     md1img-patch-on-V14 validation.
* Original LD0B restored from C:\Users\<user>\ares_rescue (hash 5b66453d...
  verified match), reboot issued.  Bats live in bat/ (English-only; cmd
  garbles UTF-8 Chinese in .bat files — never put Chinese in bats).

--------------------------------------------------------------------------------
2026-10-24 (5)  GENERALIZATION: PATTERN-BASED PATCHER, TRIPLE-VALIDATED
--------------------------------------------------------------------------------
* Goal update (user): all Xiaomi MT6893-class devices (BROM-exploitable MTK)
  must be repairable with the free tool.
* md1img A/B diff isolation: first two diff ranges ARE the patch sites
  (0x22330c-0f, 0x223b6c-6f, 4 bytes each) — recipe extracted as byte PATTERNS:
    site1 orig 111f341e31fc  site2 orig 111f331ec000  -> both become 111f01d2e0db
  (111f = shared opcode prefix; tail = the bypass).  Site OFFSETS move between
  firmware builds (a_now: 0x22b84a), the PATTERNS do not; each pattern occurs
  exactly once per image (verified stock V12.5.3, V14.0.5, intermediate).
* tools/patch_md1img_generic.py: scan-and-replace patcher + optional Xiaomi
  RSA-modulus swap (--keyswap).  TRIPLE-VALIDATED offline:
    1. patch(working_b V14 base) site bytes == working_a (machine's live
       working image)  — V14 recipe reproduced
    2. patch(stock V12.5.3) == repro_P25 (historical byte-exact Pandora repro)
    3. patch(a_now other-version) — unique hits, clean patch
* mtkclient patch_md1img (mtk_crypto.py) upgraded: IMEI-gate pattern patch
  prepended before the RSA modulus swap -> `mtk da patchmodem` now functional
  for Xiaomi MTK devices.
* NV write side (proven today) is already model-agnostic: da imei --write scans
  for the LD0B magic, keeps the original header, encrypts on-device.
* Remaining per-device unknowns for "all Xiaomi MT6893":
    - BROM exploit: mtkclient payloads per hwcode (6893 proven; siblings
      6891/6877/6853 supported upstream)
    - firmware generations where gate fragments differ -> pattern DB grows
    - wiped-nvdata container rebuild (ext4) still open (rare case)
* Free recipe (final, all-free, GPLv3):
    1. mtk.py --preloader <preloader> da patchmodem      (gate bypass, 2 slots)
    2. mtk.py da imei --write "<imei1>,<imei2>"          (identity, on-device SEJ)
    3. reboot, dial *#06#
