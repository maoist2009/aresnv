# Pandora (Z3X) "修复 IMEI" 工具分析

> 工具本体：`C:\Program Files (x86)\Pandora\`（`PandoraTool.exe` v10.3.2，安装包在
> `C:\Users\<user>\Desktop\Pandora_setup_10.3.2.exe`）。产品名 **Z3X Pandora Box**。
> 用于对比逆向的是它自己的"操作前自动备份"。

## 1. 它读/写哪些分区

每次操作前它打印：

```
读取安全数据... nvdata, protect1, nvram 确定
已保存至 备份目录
```

→ **它的"安全数据"= `nvdata` + `protect1` + `nvram`**（不含 nvcfg / persist / protect2）。

备份落地位置（两次都见过）：

- `D:\projects\aresnv\z3x_backup\MTK\Xiaomi_Redmi K40 Gaming (Ares)\Repair Flash_<ts>\`
- `D:\temp\MTK\Xiaomi_Redmi K40 Gaming (Ares)\Repair Flash_<ts>\`

每次三个文件：`nvdata.bin`(64 MiB) / `protect1.bin`(8 MiB) / `nvram.bin`(64 MiB)，
就是**分区裸读**，没有封装。→ 正好是免费的"修复前/后"快照。

## 2. 它内部用什么

| 组件 | 作用 |
| --- | --- |
| `MetaCore.dll` (14 MB) | **MTK 官方 META 库 + SP Flash Tool 引擎**。字符串里有 `AP_NVRAM_Read_Cnf` / `NVRAM_Write_Cnf` / `SP_META_*_WriteNVRAM_r` / `WM_META_Nvram_Backup_Block` / `SPFlashTool::SmartPhoneLayoutCfgParser` / `EXT4_IMG` 等 |
| `emi_base.db3` (22 MB) | SQLite，表 `EmiInfo(id, brand, model, emmc_id, sub_ver, m_type, id_len, emi_crc, data, data_size, src_name, src_path, created)`，**29941 行**。本机型一行：`model='Poco F3 GT'`, `m_type=6`, `data` 仅 84 B，来源 `ares_images_OS1.0.2.0.TKJCNXM_13.0.zip!.../preloader_ares.bin` → **这是机型指纹库，不是 NV 本体** |
| `Firmwares.db3` (1 MB) | 7307 个固件文件名索引（真正的文件在它的支持服务器 `X:\PANDORA_SUPPORT\...`） |
| `models.mdb` (34 MB) | 机型库（MS Access） |
| `Languages\ZHO.json` | 中文界面串（"读取安全数据/计算中/重启设备/操作失败"都来自这里） |

**没有硬编码任何 NV 密钥**（标准 MT67xx key `3f06bd14…` 在二进制里搜不到）→ 加解密要么在
modem 侧（经 META），要么用设备相关的 key。

## 3. 报错语义（关键）

| 报错 | 含义 |
| --- | --- |
| `错误 error (EXT4 init failed)` | `nvdata` 分区**开头不是有效 ext4**（superblock 不在 0x438） |
| `错误 error (NVDATA parent directory not found)` | ext4 有效，但**缺少 IMEI 文件要放进去的那个父目录**（`md/NVRAM`） |
| `操作失败：修复 IMEI 文件创建失败` | 上面任一步失败后的统一收尾提示 |

流程：`读取 nvdata/protect1/nvram` → `备份` → `计算中`（挂载 nvdata ext4，写入/替换
IMEI 项文件）→ `重启设备`。

## 4. 三次运行的实测（决定性证据）

| 时间 | nvdata.bin 内容 | 结果 |
| --- | --- | --- |
| 10:41:05 | **有效 ext4**（只有 `APCFG/*` + 空 `md`/`md3`/`media`） | — |
| 10:44:59 | **有效 ext4**（同上，与上者仅差 2793 B，都在 superblock 区） | — |
| 10:53:22 | **不是 ext4**：开头 `3a ff 26 ed…` = Android **sparse 魔数** | `EXT4 init failed` |

决定性事实：**10:53 的 `nvdata.bin[0:6582948]` 与买来的 `nvdata.img`（sparse）逐字节完全相同**
（之后补零）。

→ 有人把 **sparse 格式的 `nvdata.img` 原样写进了分区**。mtkclient 的写分区不做 sparse 展开
（`xflash_lib.py: writeflash()` 直接 `fh.read()` 送 DA），所以

```powershell
python mtk.py w nvdata D:\apps\mtkclient\nvdata.img   # ← 错！把 sparse 容器写进去了
```

分区里就是 sparse 文件本身，ext4 没了 → 工具 `EXT4 init failed`。

另外 `protect1.bin` 三次完全一致，`nvram.bin` 三次全零 → 这两个当时没被动过。

## 5. 设备自建 nvdata 缺什么

格式化（erase）后开机，设备/系统重建的 nvdata ext4 只有：

```
lost+found/  md/  md3/  media/  APCFG/APRDCL/{FILE_VER,AUXADC}  APCFG/APRDEB/{BT_Addr,WIFI,WIFI_CUSTOM}
```

**`md/` 是空的** —— 没有 `md/NVRAM/`，没有 `NVD_IMEI/`，没有 `CALIBRAT/`。

对比买来的 `nvdata.img`（展开后）结构完整：

```
md/NVRAM/INFO_FILE
md/NVRAM/NVD_IMEI/{NV01A000(96B), NV01B000(96B), NV0S_000(144B)}
md/NVRAM/CALIBRAT/* (125 项)
md/NVRAM/NVD_DATA/* (220 项)
md/NVRAM/NVD_CORE/  md/NVRAM/BACKUP/   (空)
```

→ 所以"格式化后直接跑工具"必然报 `NVDATA parent directory not found`：工具要往**已存在的
`md/NVRAM/` 目录**里写 IMEI 文件，它不负责建目录。

## 6. NVD_IMEI 载荷（crypto 进度）

```
NV01A000 (96B)  4c 44 49 00 | 06 f0 01 00 | ... 头 0x40 字节 ...
                0x40: ec 8d 30 e4 53 18 84 82 2b 21 12 1b 73 d1 e2 8a
                      84 b4 1f 9f a2 e8 a8 ff ee 97 20 b3 ab 79 9a 8c
NV01B000 (96B)  = 与 NV01A000 完全相同（含载荷）→ IMEI1 == IMEI2（本机双卡同 IMEI）
NV0S_000 (144B) 头 0x40 字节，载荷 80 B（0x40..0x90）
```

- 头：`LDI\0` + format 常量（A/B 用 `06F00100`，S 用 `08F00200`）+ 后面像长度/时间戳。
- 载荷 32 B（= 2 个 AES 块）与社区格式吻合：明文 = BCD IMEI(8) + 填充(2) + MD5-XOR 校验(8) + pad(14)。
- **用标准 MT67xx key `3f06bd14d45fa985dd027410f0214d22` 试解（off=0x00/0x40，16/32/80 B）→ 都不是可读 BCD IMEI。**

→ MT6893 用的是**非默认 key**（或设备相关 key），这正是"免费工具缺失"的核心。
下一步要靠"修复前/后 diff + 已知我机 IMEI"来定。

## 7. 免费实现路线

1. 让付费工具**成功跑一次**（前提：nvdata 是有效 ext4，且有 `md/NVRAM/`）。
2. dump 修复前/后的 `nvdata`（+`protect1`/`nvram`）→ diff。
3. diff 出来的 `md/NVRAM/NVD_IMEI/*` 变化 = 付费工具的全部秘密。
4. 用"已知 IMEI + 已知密文"验证/推导 key 与格式，写进 GPLv3 工具。

## CRACKED: Pandora's IMEI write fully reverse-engineered (free reproduction)

The paid 'IMEI repair' is an NV item named LD0B_001 (LID 0xEF10) in
/mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/, 10 entries x 0x20 bytes:
  entry = packed IMEI (8B nibble-swapped BCD, 15 digits + 'F')
        + 2 zero bytes
        + checksum (md5(data[:0xA]), then h[i]^=h[i+8] for i<8) = 8B
        + 14 zero bytes
  empty entry = 0xFF*10 + checksum + 14 zero
  IMEI1 -> entry[0], IMEI2 -> entry[1], entries[2..9] = empty
Payload (0x140) is AES-ECB encrypted with MTK's GLOBAL nvram SW key
the same key is used by mtkclient (seed 0102030405060708...), i.e. NO
per-device key, NO DA/BROM needed. Proved by taking the tool's own output
from nvdata_afterpatch.bin, decrypting to '86xxxxxxxxxxx'/'86xxxxxxxxxxx',
and re-encrypting to a BYTE-IDENTICAL 0x180-byte item (
'tools/imei_ld0b.py verify bkp_head/nvdata_afterpatch.bin -> all True).

Tool also creates md/NVRAM/NVD_IMEI/FILELIST =
'NV01A000\0NV01B000\0NV0S_000\0LD0B_001\0FILELIST\0' (45 bytes).

Write path (no BROM): create LD0B_001 + FILELIST as files in the mounted
nvdata (owner system:radio, label u:object_r:nvdata_file:s0), sync, reboot.
Tool: tools/imei_ld0b.py (build/dump/verify).

## SOLVED (mechanism): why the paid tool needs THREE things, not one

The paid 'Repair IMEI' is only ONE third of the story. Working repair needs:

  (1) md1img 'Patch CERT'  -> modem that accepts/uses the SW-keyed IMEI item
  (2) NV tree VERSION-MATCHED to the modem build
  (3) LD0B_001 IMEI item   -> written AFTER (1)+(2), else the modem deletes it

Evidence (this session, on-device):
 - With the STOCK modem (V1.P25) + our own regenerated NV + a byte-identical
   LD0B_001 (md5 79268f2f, the exact file the paid tool writes):
       vendor.ril.imei.check = fail      <-- IMEI NOT accepted
 - Flash the tool's patched modem (bkp_head/md1img_b_patched.bin, V1.P51):
       modem boots, md1.status = ready, baseband = V1.P51
       -> the patched md1rom/cert2 image DOES pass LK on this phone (unlocked)
       -> but the modem REGENERATED the whole NV tree (P25->P51 version change)
          and DELETED our LD0B_001 + FILELIST.
 - After that self-regeneration the tree matched the P51 modem, so on the NEXT
   boot the modem kept the NV; re-writing LD0B_001 (+FILELIST) then made the
   item SURVIVE the boot untouched (md5 79268f2f) and imei.check stopped being
   reported as 'fail' (prop now unset).

 => Free recipe: patched md1img + let the modem regenerate NV once + write LD0B.
 => The 'donor NV package' is NOT required: the phone's OWN regenerated NV works
    (only the modem patch + version match + LD0B item were missing).

### Patch CERT exact transform (ares, md1img from V12.5.3.0 / V1.P51 donor)
 src  md1img md5 d66bcec073b2d1fec496590701b1fc5c
 out  md1img md5 be3a9abcaa155c7ac403321a2b0f13e7
 - md1rom code stub @ 0x223dda: 34 1e 31 fc  ->  01 d2 e0 db   (4 bytes)
 - cert2 @ 0x1f784b8 replaced: 0x3bd bytes -> 0x7d9 bytes (md5 14028be2.. -> eb488689..)
 - everything from md1dsp (0x1f78a78) on is shifted +0x420 and section tables updated
 - cert1 @ 0x1f77c08 unchanged

## EXACT nvdata footprint of the paid tool (ext4 file-level diff, verified)

Compared the seller package `analysis/raw/nvdata.raw` (pristine) with
`bkp_head/nvdata_aftertool.bin` (identical run output) using `tools/ext4_tree.py`
(a real ext4 reader, not a byte scan). The tool's ENTIRE nvdata change is:

```
+ md/NVRAM/NVD_IMEI/LD0B_001   384 B  md5 79268f2fbc1ca2b3603c20084364a887
+ md/NVRAM/NVD_IMEI/FILELIST    45 B  md5 e8ac8c2d5ea0a05614a71a09d9c79ac1
~ md/NVRAM/INFO_FILE         1884 B  first 8 bytes INFO fb fb fd fd -> 00*8
~ APCFG/APRDCL/FILE_VER      5772 B  one NV category version byte 006 -> 011
~ APCFG/APRDEB/WIFI          6146 B  (AP-side side effect)
```

- `INFO_FILE` is the NV index; zeroing its magic makes the NV system rebuild
  it. On a live device this happens automatically after we drop LD0B in
  (observed: live INFO_FILE mtime is *later* than our LD0B write, magic intact,
  and it lists our items) -> no manual step needed.
- `NV01A000` / `NV01B000` / `NV0S_000` are NOT touched by the tool. They are
  encrypted with a **per-device NVM key** (the one the tool "Reads NVM key" for);
  they do NOT decrypt with MTK's global key, so they cannot be built offline.
  LD0B is the *only* IMEI item that uses the global key -> which is exactly why
  the paid tool (and our free recipe) writes LD0B.
- Same per-device key applies to `protect1` (all 23 `md/*` items change payload
  only), so the tool's `protect1` write is device-specific junk that the modem
  re-encrypts/regenerates anyway -> copying the donor's `protect1` is pointless.
- `nvram` is all-zero in the seller package AND on our running device -> not
  part of the fix.

Conclusion: our on-device state is at **full parity** with the paid tool:
patched md1img + version-matched NV + LD0B_001/FILELIST (byte-identical).

## Why the IMEI can look "missing" on this ROM (verified 2026-04, on device)

The Android framework on this LineageOS build **cannot read the IMEI at all**:

1. The RIL never sends `AT+CGSN` / `AT+EGMR` — with `persist.log.tag.AT=V` the
   whole boot AT log was captured and contains 66 distinct AT commands, none
   IMEI-related.
2. The MTK radio HAL advertises HIDL radio < 2.1, so RILJ logs
   `getImei not supported on service MODEM < 2.1` and returns null.
3. Direct binder calls agree: `service call iphonesubinfo {1..6} s16
   com.android.phone` return a clean null String (no exception).

=> Settings > About, `*#06#` and any "IMEI invalid/null" popup are EXPECTED on
this ROM even when the IMEI is perfectly valid. They are NOT evidence.
The only authoritative sources are (a) a SIM that registers, or (b) reading the
modem over META/AT (the paid tool's "read" does this; userspace cannot: ttyC0 is
claimed by the CCCI kernel driver, `/dev/socket/rild-atci` needs the RIL's
private framing, and no `atcid` client exists on this ROM).

Also note `vendor.ril.imei.check` is driven by the SIM-lock **BLOB** path
(`AT+ESLBLOB`, errors `CME_BLOB_IMEI_MISMATCH`, `CME_BLOB_VALIDATION_FAILED`,
...), not by the plain IMEI value:
- stock modem + our LD0B  -> `fail`  (blob/IMEI mismatch reported by the modem)
- patched modem + our LD0B -> unset  (no complaint)
i.e. the modem *does* obtain a device IMEI; the patch stops it from rejecting it.

## NV item-set difference vs the seller package

The seller package tree is a **pre-OTA (P25-era) NV** (356 files, no
`SWCHANGE.TXT`). Our device OTA'd it to P51 (see `md/NVRAM/SWCHANGE.TXT`:
`OTA from ...V1.P25 to ...V1.P51(2021/11/29 20:17), ...XIAOMI_R0MP2_K6893V1_64`),
which removed 58 legacy `NVD_DATA` items and added a few (`LD32_002`,
`MTCR_000`). `NVD_IMEI` is complete: `NV01A000`, `NV01B000`, `NV0S_000`,
`LD0B_001`, `FILELIST`. So the smaller tree is the *correct* P51 set, not a loss.

## 6. 2026-10-17 追加：直接问 modem，结果它说 IMEI 是空的（结论修正）

之前的"逆向出它写 `LD0B_001` + `FILELIST`"是对的，但**那不等于修好了 IMEI**。
本轮把 AT 通道打通，直接问 modem，证据如下。

### 打通往运行中 modem 的 AT 通道

modem 的 AT 通道在 `/dev/ttyC0`（内核 CCCI 持有），由 `gsm0710muxd` 做 CMUX 复用，
每个通道以 pty 形式暴露。rild 持有 pty 的 **slave** 并往里写 AT 命令 ——
**所以往同一个 slave 写命令，就等于把命令注入 modem**：

- ATCI 通道：`/dev/radio/atci1 -> /dev/pts/5`（muxer DLCI 61）
- RIL 主命令通道：`/dev/radio/pttycmd1 -> /dev/pts/2`（muxer DLCI 26）

送达证明（muxer 自己的日志）：

```
pseudo_device_read(): Data from channel 61, actual_read=9
write_frame(): Write data len=9 written=9 errno=0
```

回读靠 rild：它把 modem 的每一行原始应答记进 radio buffer：

```
logcat -b radio -d -s AT:V -v time
```

`AT>`/`AT<` 行会带 reader 线程名（我们注入的走 `RIL_ATCI_READER`）。
注意：**必须让 rild 在 `persist.log.tag.AT=V` 已设置的情况下启动**，否则 buffer 永远是空的。
现成工具：`tools/at_probe.py`（GPL-3.0-or-later）。

### 实测：对照命令正常，身份命令里 IMEI 是空的

| 命令 | modem 应答 |
| --- | --- |
| `AT+CGMI` | `+CGMI: MTK1` |
| `AT+CGMR` | `+CGMR: MOLY.NR15.R3.TC8.PR2.SP.V1.P51, 2021/11/29 20:17` |
| `AT+EGMR=0,4` | `+EGMR: "XIAOMI_R0MP2_K6893V1_64"`（机型） |
| `AT+EGMR=0,9` | `+EGMR: "78"`（IMEI SVN，**有值**） |
| `AT+EGMR=0,13` | `+EGMR: "NLWCG_CUSTOM"`（市场） |
| **`AT+CGSN`** | **只有 `OK`，没有任何数据行 = 没有 IMEI** |
| **`AT+EGMR=0,7`** | **`+EGMR: ""` = 明确的空串** |
| `AT+GSN` | `ERROR` |

`AT+CGSN` 就是 MTK RIL 自己用的那条命令：反汇编
`RmcOemRequestHandler::requestGetImei` @ `0x2e7608`，在 `0x2e76e8` 载入字符串
`"AT+CGSN"`。

### 写入尝试：全部被 modem 拒绝

| 命令 | 应答 |
| --- | --- |
| `AT+EGMR=1,7,"86xxxxxxxxxxx"` | `+CME ERROR: 100` |
| 先 `AT+CFUN=0` 关射频再写 | 仍然无效 |
| `AT+EGMR=1,7,"86xxxxxxxxxxx",78` | 无效 |
| `AT+EGMR=1,7,86xxxxxxxxxxx`（不加引号） | `+CME ERROR: 100` |
| `AT+ESLBLOB=2/5/6/7` | `+CME ERROR: 3`（不允许） |

RIL 自己的字符串表里只有 `AT+EGMR=0,9`（读 SVN）和 `AT+EGMR=1,9,"%s"`（写 SVN），
以及 `AT+ESLBLOB=1,%d,"%s",%d`（写签名 blob）。
**RIL 里根本没有"I写 IMEI"的命令** —— IMEI 字段在普通 AT 口上被设计成不可写（防篡改）。

### 最关键的自相矛盾

我们写进去的 NV 项**在文件系统里是好的**：

```
md/NVRAM/NVD_IMEI/LD0B_001  384 B  md5 79268f2fbc1ca2b3603c20084364a887
md/NVRAM/NVD_IMEI/FILELIST   45 B  md5 e8ac8c2d5ea0a05614a71a09d9c79ac1
```

用 `tools/imei_ld0b.py` 解出来就是 **IMEI1 86xxxxxxxxxxx / IMEI2 86xxxxxxxxxxx**，
和 Pandora 自己产出的字节完全一致，md5 经过所有探测和重启都没变。

**但 modem 说 `+EGMR: ""`、`AT+CGSN` 没有 IMEI。**

→ **modem 不从这个 `LD0B_001` 读 IMEI**，所以 Pandora 的全部足迹
（`+LD0B_001`、`+FILELIST`）**不足以修复 IMEI**。之前在 Settings / `*#06#`
看到的"未知"是**真的没有 IMEI**，不是显示问题。

同一结论也从另一边印证：modem 的机型串、SVN、市场串都在（`AT+EGMR=0,4/9/13` 都有值），
唯独 IMEI 是空的 —— 这就是"NV 被清过、IMEI 没被真正写回去"的样子。

### 那 IMEI 到底藏在哪

- `NVD_IMEI/NV01A000`（96 B）、`NV01B000`（96 B）：头 `LDI`、lid `0xF006`，
  后面 32 B 密文。**两个文件的密文逐字节相同**（同明文同密钥，AES-ECB 特征），
  且用 MTK 全局 key 解不开 → **per-device NVM key 加密**。`NV0S_000`（144 B, lid 0xF008）同理。
- `AT+ESLBLOB`（签名补贴锁/IMEI blob 通道）在这里直接被拒（`+CME ERROR: 3`），
  所以那也不是目前的卡点，而是"根本没用上"。

### 对免费方案的意义

**写 `LD0B_001` + `FILELIST` 不是修复。** 第 1 节里的三段式是必要但不充分的。
要让 modem 真的报出 IMEI，必须写到 modem 愿意接受的地方：

1. **META / DIAG 模式**（modem 的工厂口）。在 META 里 `AT+EGMR=1,7,"<imei>"`
   不会被拒。META 靠 boot-mode 标志（MTK `misc`/`para`）或 DA 握手进入，
   免费工具可以用 mtkclient 的 BROM/DA 路径去置这个标志，**不用动 nvdata**。
   Pandora 内置 MTK 官方 `MetaCore.dll` 正是干这个的 —— 这解释了为什么它能修而我们
   只写文件不能。
2. 或者找到让运行中的 modem 从 NV 导入 IMEI 的项/锁路径（未解，承运 IMEI 的
   `protect*` 项是 per-device key 加密的）。

验证手段已就绪：META 写完之后，在普通 AT 口上 `AT+CGSN` / `AT+EGMR=0,7`
必须能读到 IMEI；否则就是没写成。

> **SUPERSEDED（同日追加 2，见第 8 节）**：上面"只能走 META"的结论是错的。
> Pandora 同时有 **非-META** 的 `Repair IMEI / Patch CERT`（文件+DA 路径，就是本
> 文档一直在分析的那条）和独立的 `META Repair IMEI` 菜单项；有 META 不等于用 META。
> 用户实测日志走的是前者。真正的卡点见第 8 节：Xiaomi 在 modem 里加的
> `custom_nvram_sec.c` 校验（`custom_nvram_check_imei` / `devPubKeyModulus`）。

## 7. 2026-10-17（追加 2）：找到 Xiaomi 的 modem 侧校验 = "Patch CERT" 真正要补的东西

### 7.1 nvram 为什么"一直有问题"（实测）

`nvram` 分区在**所有**拿得到的镜像里都是 **64 MiB 全零**
（md5 `7f614da9329cd3aebf59b91aadc30bf0`，nonzero=0）：

| 来源 | 结果 |
| --- | --- |
| 卖家"好包" `D:\APPS\mtkclient\nvram.bin` | 全零 |
| 我们设备 `backups/pre/nvram_pre.bin`、`backups/post/nvram_now.bin`、`bkp_head/nvram_pre.bin` | 全零 |
| **Pandora 自己 11 次"操作前备份"的每一份 `nvram.bin`** | 全零 |
| eng 工厂固件 `D:\APPS\mtkclient\eng\` | **没有 nvram 镜像**（只有 audio_dsp/md1img/scp/spmfw/sspm） |

→ ares 这个平台**天生不用 nvram**：IMEI/NV 全在 `nvdata` 的 `md/NVRAM/`。
Pandora 的通用 MTK 流程按老平台布局去 nvram 里找 NVRAM 容器，全零没有头/锚点，于是报
它自己的原文 `Write IMEI [NVRAM]... skip (bad container)`（ZHO.json 的键）=
"写入 IMEI [NVRAM]... 跳过（容器损坏）"。
**语义是"跳过"（skip），不是致命错误** —— 失败发生在下一步。

### 7.2 真正失败的那一步 = `Patch CERT` / patch modem signature

用户日志：`正在修补调制解调器签名... 错误(5)` →
`调制解调器签名修补失败：Exception: custom_nvram_check_imei: fingerprint + pool anchor both failed`

Pandora 自己的字符串表（`Languages\ZHO.json`，键=英文原文）说明这一步是什么：

| 键 | 中文 |
| --- | --- |
| `Patching modem signature...` | 正在修补调制解调器签名... |
| `Load partition for patching...` | 加载用于打补丁的分区中... |
| `Patch CERT: custom_nvram symbol missing` | Patch CERT：custom_nvram 符号缺失 |
| `arch: %s, sig: %s, sml_Check @ 0x%x, bytes: %d, cert2: %s` | 报告镜像里找到的 `sml_Check` 地址、cert2 大小 |
| `OK (%s, %d code patches, %d strings, cert2 %d->%d B)` | 成功时：N 处代码补丁 + M 处字符串补丁 + cert2 大小变化 |
| `Patch CERT requires Bypass` | 必须开 Bypass |
| `Patch Xiaomi modem CERT failed` | 打补丁 Xiaomi 调制解调器 CERT 失败 |

→ 这一步进 md1img 找符号（`sml_Check`、`custom_nvram*`），打 **code patches + strings**，
并**替换 cert2**。"fingerprint" 和 "pool anchor" 是两种定位策略，两个都失败 → 操作失败。
另有 `already patched, skip` / `Check patch state...`：它**会先查是否已打过补丁**。

### 7.3 决定性证据：Xiaomi 的校验本体就在 modem 镜像里（明文）

`analysis\raw\md1img_stock_v12_5_3.raw`，文件偏移 `0x1815600` 附近整段明文
（`python tools/imgscan.py strings <img> 0x1815300 0x1815d00`）：

```
custom/service/nvram/custom_nvram_sec.c
custom_nvram_check_imei%d not identical
custom_nvram_check_imei%d re-write imei fail
custom_nvram_check_imei%d re-write with signed data
devPubKeyModulus:
custom_nvram_check_signed_critical_data devPubKeyModulus not found
devPubKeySign:
custom_nvram_check_signed_critical_data devPubKeySign not found
custom_nvram_get_product got error:%d
ares
custom_nvram_check_signed_critical_data dev_pub_key verify fail %d
criticalData:
custom_nvram_check_signed_critical_data criticalData not found
crticalDataSign:
custom_nvram_check_signed_critical_data criticalDataSign not found
custom_nvram_check_signed_critical_data ciritical_data verify fail %d
custom_nvram_check_cpuid not identical %x != %x
custom_nvram_check_meid not identical / re-write meid fail / re-write with signed data
custom_nvram_check_critical_data tag:%d len%d check fail
custom_nvram_check_signed_critical_data return %d
custom_nvram_get_product get %s
aresin
ro.product.vendor.name
OLD VERSION, return true
MP version, return true
imei_check NV not 0
skip IMEI check
custom_nvram_read_and_check_signed_critical_data read imei fail
custom_nvram_read_and_check_signed_critical_data read critical data fail
custom_nvram_read_and_check_signed_critical_data sign data is default value, check fail
```

（同一段在 eng 固件 `eng\md1img.img` 里也存在，只是地址不同 → 刷 eng 的 md1img 也绕不过；
这同时说明 eng 镜像和我们的是同一套 Xiaomi 定制，只是构建不同。）

**这就是"小米自己加的 RSA 校验"**：

- Xiaomi 在 modem 里加了 `custom/service/nvram/custom_nvram_sec.c`，把 **IMEI / MEID / CPUID**
  放进一份**带 RSA 签名的 critical data**：`criticalData:` + `crticalDataSign:`，
  外层再套 `devPubKeyModulus:` + `devPubKeySign:`（内嵌**小米公钥**）。
- 开机时 `custom_nvram_check_signed_critical_data` 验签；`custom_nvram_check_imei` 比较
  **NV 里的 IMEI 与签名数据里的 IMEI**，不一致就 `custom_nvram_check_imei%d not identical`
  → 用签名数据回写 / `re-write imei fail`。
- `custom_nvram_check_cpuid not identical %x != %x` → 数据还绑 CPUID。

**这解释了第 6 节那个自相矛盾**：NV 文件里 IMEI 完全正确（`LD0B_001` 解出
86xxxxxxxxxxx），modem 却答 `+EGMR: ""` / `AT+CGSN` 空 —— 因为这份 IMEI
**没有配套的小米签名数据**，被 `custom_nvram_check_imei` 判成 "not identical" 而丢弃。
只写 NV 文件永远修不好，除非补掉这条检查。

### 7.4 与我们的"Patch CERT"的关系 / 下一步

我们复现的 Patch CERT（`md1rom` stub @ `0x223dda`: `34 1e 31 fc → 01 d2 e0 db` +
替换 cert2 `0x3bd → 0x7d9` 字节）解决的是"**改过的镜像能不能通过签名校验跑起来**"。
还差 Pandora 真正的那一下：**把 `custom_nvram_check_imei` /
`custom_nvram_check_signed_critical_data` 这条检查本身补掉**（它的 `code patches + strings`）。

顺带两条"可能不用改代码"的线索（都在上面的字符串里）：

- `OLD VERSION, return true` / `MP version, return true` → 检查有**版本门**，
  让 modem 认为 NV 是旧版/MP 版就直接 `return true`（跳过检查）。
- `imei_check NV not 0` / `skip IMEI check` → 有某个 NV 标记非 0 就跳过 IMEI 检查。

下一步（仍只做"参照 Pandora"的离线分析，不动机器）：

1. 在 md1img 里 xref 这些字符串 → 反汇编 `custom_nvram_check_imei` /
   `custom_nvram_check_signed_critical_data`，定位"not identical → 拒绝"的分支和
   `devPubKeyModulus` 验签点 → 得到**数据驱动**的补丁（不写死偏移）= 免费的 Patch CERT。
2. 判断版本门 / NV 标记能否用纯 NV 数据达成（那会是更干净的免费方案）。
3. 复核 `already patched` 判定：Pandora 这次失败是否因为镜像已被我们打过补丁
   （指纹不匹配）—— 用原厂 stock md1img 再比对一次即可判定。

### 7.5 工具

- `tools/pandora_scan.py`（GPL-3.0-or-later）：扫 Pandora 自己的二进制/语言包，
  定位它的阶段名与错误串（`strings` / `scan` / `db` / `zh` 四个模式）。
- `tools/imgscan.py`（GPL-3.0-or-later）：镜像指纹 + ASCII/UTF-16 needle 扫描 +
  指定偏移范围的字符串导出；用来验证"符号是否还在镜像里"。
- `tools/snapdiff.py`（GPL-3.0-or-later）：分区快照指纹化与逐字节 diff。

---

## 8. 2026-10-17（追加 3）：md1img 容器结构 + **modem 是 MIPS16**（决定性）

### 8.1 nvram 被跳过 = 平台本来就没有 NVRAM 容器（不是故障）

Pandora 的 IMEI 写入是**按"载体清单"逐个尝试**的（语言包里同时存在
`Write IMEI [NVDATA]` / `[NVRAM]` / `[OTP]` / `[RPMB]` / `[LG]` / `Write IMEI [%s]`，
以及 `Write IMEI failed`、`Write IMEI [NVRAM]... skip (bad container)`）。
它只写"这台机器实际存在"的载体；ares 只有 NVDATA 载体，NVRAM 那条就被**跳过**。

跳过而不是报错的依据（都已实测）：

1. `nvram` 分区在**每一台**都是 64 MiB 全 0：Pandora 的 11 份快照、卖家包
   `nvram.bin`、我们自己的 `nvram_pre/nvram_now`，md5 全为
   `7f614da9329cd3aebf59b91aadc30bf0`、nonzero=0；`eng/` 里甚至没有 nvram 镜像。
2. 设备挂载表里没有 nvram（只有 nvdata / nvcfg / persist / protect_f / protect_s）。
3. modem 自己的 NV 路径表写的是 `Z:\NVRAM\NVD_IMEI\LD0B_001` —— 它要的 IMEI
   在 **nvdata**（`/mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001`），不在 nvram 分区。
4. Pandora 自己的 GUI 文案：`NV data is erased or damaged (NVRAM container/FILELIST
   missing). Restore NVRAM structure?` —— 它**知道**这是"容器缺失"状态并按 skip 处理。

结论：`Write IMEI [NVRAM]... skip` 是**预期行为**，和本次失败无关；失败的是
`Patch CERT`（"Patching modem signature"）。

### 8.2 md1img 是 GFH 段容器（`tools/mtkimg.py info`）

`md1img_stock_v12_5_3.raw`（65,048,352 B, md5 `db71ecfd372f4d0c153cc05c90bdecfe`）：

| 偏移 | 段名 | 大小 |
| --- | --- | --- |
| `0x00000000` | `md1rom` | `0x1f73b00` (32,979,712) |
| `0x01f73d00` | `cert1` | `0x6ad` |
| `0x01f745b0` | `cert2` | `0x3bd` |
| `0x01f74b70` | `md1dsp` | `0x819630` |
| `0x0278e3a0` | `cert1` | `0x6ad` |
| `0x0278ec50` | `cert2` | `0x3bd` |
| `0x0278f210…` | `md1_filter` ×7（PLS_PS_ONLY / 1_Moderate / 2_Standard / 3_Slim / 4_UltraSlim / LowPowerMonitor） | `0x12a90` each |
| `0x02812a00` | `md1_emfilter` | `0x8cc` |
| `0x028134d0` | `md1_dbginfodsp` | `0x166a37` |
| `0x0297a110` | `md1_dbginfo` | `0x114488` |
| `0x02a8e7a0` | `md1_mddbmeta` | `0xaed02` |
| `0x02b3d6b0` | `md1_mddbmetaodb` | `0x6ef0e` |
| `0x02bac7c0` | `md1_mddb` | `0xa72e29`（**熵 8.000 = 加密**） |
| `0x0361f7f0` | `md1_mdmlayout` | `0x7e8fd6`（大量字符串，文本/表） |
| `0x03e089d0` | `md1_file_map` | `0x342` |

每个 payload 前面是 0x200 字节 GFH 头；**镜像里没有 ELF**（`7f454c46` ABSENT）。
`md1rom` 的 payload = 文件 `0x200..0x1f73d00`（提取见
`analysis/raw/md1rom_stock.rom`）。

### 8.3 md1rom 内部分区（`tools/mtkimg.py entropy`）

| 区域 | 熵 | 性质 |
| --- | --- | --- |
| `0x0000000–0x1800000` (24 MB) | 7.20–7.30 | **代码**（见 8.4） |
| `0x1800000–0x1f73b00` (9.4 MB) | 1.9–5.5 | 明文数据/字符串（Xiaomi 校验串在这里） |

`md1_mddb` 是唯一熵 8.000 的段（真加密）；`md1rom` 的代码段**不是**加密
（零字节占比 4–7%，而加密/压缩会趋近 0.4%）。

### 8.4 **决定性：modem 代码是 little-endian MIPS16**

`tools/mtkimg.py mipsops`（把 16 位半字的 opcode 域 `bits15:11` 做直方图）：

代码区 `[0x400000:+0x200000]`（LE）—— 分布强烈偏离均匀，峰值全部落在
MIPS16 的常用 opcode 上：

```
op 16 lb                       143715  4.39x
op  0 addiu rx,sp              134983  4.12x
op  2 b                        102846  3.14x
op  4 beqz                      70549  2.15x
op 18 lw(sp)                    62300  1.90x
op 12 save/restore/mov/addu sp  57300  1.75x
op  5 bnez                      56058  1.71x
op  3 jal/jalx                  45160  1.38x
op 22 lw pool                   27236  0.83x
```

数据区（`0x1800000` 起）则是 op 0 一枝独秀（20x，任意字节碰巧落入该区间），
没有代码谱形。BE 解释**没有** `save/restore`、`lw(sp)`、`jal` 的峰值 →
**LE 正确**（与 biloba 一致）。

这解释了此前所有"反汇编碰壁"：镜像不是 ELF、没有 ARM/Thumb/AArch64/MIPS32
返回指令、也没有指向字符串的绝对指针（MIPS16 用 op-22 literal pool / op-1
PC 相对来取地址）。**对策：用现成的 GPLv3 MIPS16 解码器。**

### 8.5 现成参照：`refs/mtk-imei-switcheroo`（**GPLv3，与本项目同许可证**）

这是社区已有的同类问题完整解法（设备是 biloba / MT6768，Redmi Note 8 2021），
结论对我们**方法上**直接适用（*偏移与镜像不可平移*，其文档也明确警告）：

- 它面对的正是同一个东西：**LD0B 校验之外还有"签名 covering critical data"检查**。
- 它的解法 = **两处一起改**：
  1. **modem 的 gate 函数返回 0**：MIPS16 六字节 `li v0,0; jrc ra; nop`
     = `00 6a a0 e8 00 65`（`cf 64 20 6e 0c 04` → 改掉）。
     gate 名：V12 = `is_enable_critical_data_check`，
     V13/V14 = `is_need_enable_critical_data_check`；
     `ro.boot.hwlevel` 是它的判据串。
     **我们的 md1img 里没有这两个名字**（已实测 ABSENT）→ 名字/偏移必须重新在
     ares 上确定。
  2. **LK 的 md1img 校验策略字节**：`01 00 03 02` → `01 00 03 00`
     （最后一位 = secure-boot-enabled + unlocked 的状态位，bit1 控制校验）。
- 关键教训：**只改 modem 会 bootloop；modem + LK 一起改才被报告成功。**
- 它还给出可复用的工具：`research/biloba/tools/mips16_subset.py`（自写 MIPS16
  解码器，GPLv3，可整体移植）。

### 8.6 Pandora 为什么在我们这台失败（而不是我们的机器有问题）

- `models.mdb`（其实是 SQLite）里有 ares 条目：
  id 3989 `Poco F3 GT` / id 4008 `Redmi K40 Gaming`，platform `MEDIATEK`，
  每台都带 **2825 字节 payload**，但 payload 是加密容器（magic `PNDMODEL1`）。
- 语言包里的 `Cannot build md1img basename: fingerprint unparsable ("%s")` +
  报错 `custom_nvram_check_imei: fingerprint + pool anchor both failed`
  → "fingerprint" 和 "pool anchor" 是它**定位补丁点的两种手段**；两种都失败 =
  它认不出我们这个 modem 构建（所以给不出 code patches）。
- 也就是说：**Pandora 在这台机器上能力不足**；我们自己定位并打补丁，反而能覆盖它
  覆盖不了的构建 —— 这正是免费实现的价值点。

### 8.7 下一步（离线，按优先级）

1. 把 `research/biloba/tools/mips16_subset.py` 移植为 `tools/mips16.py`（GPLv3，
   注明来源），用来反汇编 ares 的 md1rom。
2. 解出 MIPS16 的取址方式后找回 mod1rom 的运行基址（用 op-3 `jal` 目标自洽求解），
   再 xref `custom_nvram_check_imei` / `custom_nvram_check_signed_critical_data`
   相关串 → 定位 gate。
3. 用 `li v0,0; jrc ra; nop` 同款做法把 gate 改成 return 0（数据驱动：先按
   gate 的 opcode 谱/字面量指纹定位，不写死偏移）。
4. 找 ares 的 LK 分区，按 biloba 的做法改 md1img 策略字节（`02` → `00`）。
5. 用原厂 stock md1img 复核 Pandora 的 `already patched` 判定（判断它这次失败是否
   也有"镜像已被我们改过"的成分）。

### 8.8 Pandora 到底怎么改 md1img（它自己的字符串为证）

它**不是**靠"加载未经验证的镜像"绕 preloader，它的流程是：

```
Read LK partition...            → 读 LK
Search LK patch offset...       → 找 LK 里的补丁点
Patching LK image...            → 改 LK
Backup LK to / Patched LK saved to / Writing patched LK...
Patch CERT: md1img patch impossible by LK policy
Modem patch impossible by LK policy
Boot patch impossible by LK policy
OK (%s, %d code patches, %d strings, cert2 %d->%d B)
arch: %s, sig: %s, sml_Check @ 0x%x, op129 @ 0x%x, bytes: %d, cert2: %s
```

要点：

- `Patch CERT: md1img patch impossible by LK policy` —— **Pandora 自己承认"能不能改
  md1img"取决于 LK 策略**。它把"改 LK 策略"当作"改 md1img"的前置条件，先改 LK 再改 CP。
- md1img 的改动 = **code patches + strings + 换 cert2**（`cert2 %d->%d B`）。
- `sml_Check` 是 **LK** 里的符号（在 md1img 里实测 ABSENT），`op129` = modem 里的
  `smu_op129_check_sml` —— 正好对应"LK 侧校验点"与"modem 侧检查点"两处。

这与社区独立实现（`refs/mtk-imei-switcheroo`，biloba）**完全一致**：改 modem gate
（return 0）+ 改 LK 的 md1img 校验策略位（`01 00 03 02 → 01 00 03 00`，bit1 控制校验）。

### 8.9 本机实测（决定性）：签名不匹配的 md1img 现在就能启动

`bkp_head/md1img_b_patched.bin` 是一个**签名必然不匹配**的镜像：md1rom 代码被改
（`0x223dda` 4 字节）+ cert2 被换（`0x3bd → 0x7d9`）+ 段整体移位 —— 它照样启动：

- `vendor.mtk.md1.status = ready`
- `gsm.version.baseband = MOLY.NR15.R3.TC8.PR2.SP.V1.P51`
- rild 正常（见本文件 "SOLVED (mechanism)" 一节第 157 行：
  "the patched md1rom/cert2 image DOES pass LK on this phone (unlocked)"）

→ 结论（**已被 §8.10 修正为"未完全分离"**）：在当前（已解锁）状态下，本机可以加载
我们改过的 md1img（实测）。但严格说起来，那次同时做了两件事（改 md1rom 内容 + 换 cert2），
所以**还没有证明"随便改一个字节也能起来"** —— 见 §8.10。

（另：我们那份 `0x3bd → 0x7d9` 的 cert2 是**从哪来的，笔记里没有记录** —— 待确认。
如果不是我们自己生成的，就说明这一步目前仍依赖外部产物。）

### 8.10 LK 侧证据 + 修正：md1img 的 auth 是 LK 在管（本机 expdb 里的 LK 日志）

`notes/lk_log_from_expdb.txt` 是**本机 LK 自己的日志**（多次启动，从 expdb 里取出来的）。
每次加载 md1img（`ccci_load_raw_data`）LK 都会打印一整套策略判定：

```
ptr hdr verify:partition[md1img], image_name[md1rom]
policy_entry_idx = 12
[SEC_POLICY] sboot_state = 0x1
[SEC_POLICY] lock_state = 0x3
img_auth_required = 1
Image name matched
[SBC] image md1rom auth init pass
[IMG_VER] img ver check, (group, key ver, cnt ver, otp)=(1, 1, 1, 1) ...ok
Verify md1rom cert chain cost 10 ms
image verify:partition[md1img], image_name[md1rom], addr[0xe0000000], size[0x1f77a00]
LTE now, and lte sbc en != 0x1          <-- 运行时开关，紧贴 pass 之前
[SBC][oem] img auth pass
Image hash verification success: ret = 0
Verify md1rom image hash cost 153 ms
```

要点：

- **加载 + 校验 md1img 的是 LK，不是 preloader**（`ccci_load_raw_data` / `[SBC]` / `[IMG_VER]`
  都在 LK 的日志里）。preloader 那条链是 preloader → LK。
- **策略说"必须校验"**：`img_auth_required = 1`；`policy_entry_idx = 12` 是 md1img 的那条策略项；
  `sboot_state = 0x1`（安全启动开）、`lock_state = 0x3`。
- 但 md1rom 的 verify 后面紧跟 `LTE now, and lte sbc en != 0x1` —— **"LTE 安全启动检查使能"
  运行时开关不为 1**，之后才报 `img auth pass`。这条是本机"校验实际上不强制"的最可疑证据。
- LK **对校验失败是容忍的**（不是 halt）：`[SBC] image dconfig-dt auth init fail (0x6003)` /
  `dconfig image cert verify failed` → LK 继续 `[SEC_POLICY] reached the end, use default policy`。
- AVB 分区在解锁状态下 `[avb] img_auth_required = 0`（即解锁确实让 AVB 不要求 auth）。
- 另注意 `md1dsp` 也有完整一遍（`image verify:... image_name[md1dsp]` +
  `Image hash verification success: ret = 0`）—— **md1dsp 我们没动，它的 hash 本来就该对**。

**日志里的启动 ↔ 本地镜像对应**（LK 打印的 size 反查；工具 `tools/logsize_match.py`）：

| LK 打印的 size | 对应镜像 |
| --- | --- |
| md1rom `0x1f77a00`（3 次启动） | `analysis/raw/md1img_a_donor.bin`（md5 `d66bcec0…`）= 我们的补丁**源**；**我们的 patched 镜像 md1rom 尺寸与它完全相同** |
| md1rom `0x20cb440`（1 次启动） | `analysis/raw/md1img_b_donor.bin`（md5 `42f2e27b…`）= 另一种 ares modem 版本 |

→ 因为 patched 镜像与 donor_a 的 `md1rom` 尺寸**一样**（我们只改了 4 字节内容、并把 cert2
从 `0x3bd` 长到 `0x7d9`），**单靠日志分不出"原厂 donor_a"和"我们改过的 patched"**。
所以日志里那几次 `img auth pass` 到底有没有包含"改过的镜像"，目前无法定论。

**要定论，两条路（都不需要猜）：**

1. **读 LK 本身**（离线、零风险）：拿到 ares 的 `lk_a`/`lk_b`（GPT：`lk_a` @ LBA 168704、
   `lk_b` @ LBA 348928，各 8 MiB，见 `tools/gpt.py`），就能读出 `policy_entry_idx = 12`
   的那条策略到底怎么算 `img_auth_required`、`lte_sbc_en` 从哪里来、以及 Pandora 的
   `sml_Check @ 0x%x`。若策略确实要改，位置就是这张表（biloba 的 `01 00 03 02 → 01 00 03 00`）。
2. **一次最小实测**（低风险、可秒回退）：取 donor_a 原图，md1rom 里**只改 1 个字节**，
   **cert1/cert2 完全不动**，刷入 slot b → 看 (a) 能否进系统 (b) LK 日志里 md1rom 那两行是
   `pass` 还是 `fail` (c) `md1.status`。
   - 起来了 ⇒ 校验确实没开 ⇒ **真·任意 md1img**，后面的补丁随便改。
   - 起不来/报 fail ⇒ 校验是开的 ⇒ 我们走"换 cert2"那条路（就是 Pandora 的 Patch CERT）。

（新工具：`tools/gpt.py`（自动识别 512/4096 扇区）、`tools/logsize_match.py`。）


