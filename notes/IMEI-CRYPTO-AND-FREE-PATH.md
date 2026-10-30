# LD0B / IMEI：格式、加密、以及免费（GPLv3）实现路径

日期：2026-10-18
状态：离线研究结论（设备不在手边）

---

## 0. 一句话结论

**LD0B 里的 IMEI 是"加密"，不是"签名"；加密由机器自己的 SEJ 硬件完成，
PC 侧只负责组明文和发 DA 命令。因此不存在"离线密钥"，也不需要——
免费工具要做的就是像 Pandora 一样，让机器自己加密。**

---

## 1. LD0B 条目格式（权威来源：mtkclient 源码）

`mtkclient/Library/DA/mtk_da_handler.py` 的 `da imei --write` 分支就是同一件事的
开源实现，条目布局逐字节一致：

```python
data  = encode_imei(imei) + b"\x00\x00"       # 10 B：BCD 小端半字节对 + 2 字节
csum  = calc_checksum(data, 0xA)              # 8 B：MD5(data[:10]) 前 8 字节 XOR 后 8 字节
entry = data + csum + b"\x00" * 0x0E          # 32 B
# 空槽：
empty = b"\xFF" * 0x0A + calc_checksum(b"\xFF"*0x0A, 0xA) + b"\x00" * 0x0E
```

文件结构：

```
0x000  64 B   LDI 头
0x040  32 B   entry 0   (IMEI 1)
0x060  32 B   entry 1   (IMEI 2)
0x080  32 B   entry 2..9 ← 全部相同（空槽），共 8 个
0x180  结束（= 384 字节）
```

`encode_imei` 是 **半字节交换**（小端 BCD）：`86xxxxxxxxxxx` →
`68 54 01 50 11 54 41 f5`；第 16 个半字节补 `F`。

LDI 头（本项目设备实测）：

```
4c 44 49 00   "LDI\0"
0x04  10 ef       LID 编号（LD0B = 0xef10）
0x08  0a 00 00 00 条目数 = 10
0x0c  2a 40 00 00 属性 attr = 0x402a     ← 决定用哪种加密
0x10  00 20 00 00
0x1c  c2 44 00 00
0x2c  01 00 00 00
```

---

## 2. attr 位决定加密方式（mtkclient `nvitem()`）

```python
attr = int.from_bytes(header[0xc:0xf], "little")   # 0x00402a
if attr & 0x08: swcrypt  = 1                       # ← 置位
if attr & 0x20: cryptmode = HW_ENCRYPTED_5G (=2)   # ← 置位
```

`0x2a = 0b0010_1010`，bit1 / bit3 / bit5 都置位 ⇒ **SW + HW-5G 双标志**，
最终 `cryptmode = 2`。

随后 DA 收到自定义命令：

```
XCmd.CUSTOM_SEJ_HW = 0x0F000B
flags  = (enxor<<24) | (encrypt<<16) | (swcrypt<<8) | cryptmode
otp    = 32 B
seed   = 8 B      (默认 b"12abcdef")
aeskey = 32 B     (默认 MTK 种子 01 02 … 1C 00 00 00 00)
len + data
```

**加解密发生在 DA（运行在手机 SoC 上）里，用的是 SEJ 安全引擎寄存器。**

---

## 3. 密钥从哪里来

| 材料 | 来源 | 本项目实测值 |
|---|---|---|
| `otp` (32 B) | **preloader** 里 `MMM\x01\x30` + 0xC | **全 0** |
| `seed` (8 B) | 常量 | `b"12abcdef"` |
| `aeskey` (32 B) | 常量（MTK 种子） | `0102…1C00000000` |

SEJ 侧（`mtkclient/Library/Hardware/hwcrypto_sej.py`）：

* `sej_set_otp(g_aes_swotp)` —— 用的是**固定**的 32 B `g_aes_swotp`；
* `SST_SEJ_Derive_AES_128_Key(g_UnqKey_Fixed_Pattern)` —— AKEY 全 0，
  `HACC_ACONK = R2K | BK2C`，IV 用固定的 `g_UnqKey_IV`；
* `R2K/BK2C` 表示**由芯片根密钥派生**（root-to-key）。

### 3.1 源码级确认（决定性）

`shomykohai/mtk-payloads`（DA 扩展 `da_x` 的上游，AGPL-3.0；其中
`common/crypto/sej/*` 为 MIT）给出了 SEJ 的真实语义：

```c
/* common/crypto/sej/sej.c */
case AES_HW_KEY:
    g_sej_ctx.blk_sz = key_sz;
    if (g_sej_ctx.legacy) {
        writel(readl(SEJ_ACONK) | SEJ_AES_BK2C, SEJ_ACONK);   /* Bind HUK */
        return 0;
    }
    sej_aes_kdf(true);                                        /* HRK256 KDF */
    return 0;
```

```c
/* common/crypto/sej/sej_hk.c */
void sej_aes_kdf(bool hrk256) {          /* 由硬件唯一密钥派生 256 位会话密钥 */
    ...
    writel(readl(SEJ_ACONK2) & ~SEJ_AES_OLD_BK2C, SEJ_ACONK2);
    writel(readl(SEJ_ACONK) | SEJ_AES_BK2C, SEJ_ACONK);
}

void SEJ_V3_init(AES_OPS encrypt, const u32* iv) {
    writel(SEJ_AES_BK2C | SEJ_AES_R2K, SEJ_ACONK);   /* Bind Hardware Unique Key */
    sej_aes_kdf(true);
    ...
}
```

而 DA 扩展本身也是**拿着主机传来的 `sej_base` 去写寄存器**：

```c
/* da_x/src/commands.c */
sej_init(g_da_ctx.sej_base);
printf("SEJ base: 0x%08x\n", g_da_ctx.sej_base);
```

⇒ 密钥 = f(HUK, 固定图案)，**HUK 熔在 SoC 里**。这就是最终结论：
LD0B 的密文只能在**这台机器上**产生，PC 侧无法复算——除非拿到 HUK（不可能）。

（旁证：`da_x.bin` 里确实有 AES S-box，但那只服务 `SW_ENCRYPTED` / TZCC
等软件路径；SEJ 命令走的是 MMIO。）

---

## 4. 证据链：Pandora 自己也没有密钥

对 `PandoraTool.exe`（UPX-变体壳）做了内存脱壳/转储（240 MB），结果：

| 检查项 | 结果 | 含义 |
|---|---|---|
| MTK SST `nvsw_kgen` 常量 (`BE410C67…`) | **0 次** | 不用 `SST_Get_NVRAM_SW_Key` |
| `g_aes_swotp` / `g_UnqKey_Fixed_Pattern` / `g_UnqKey_IV` | **0 次** | 不在 PC 侧复现 SEJ |
| `CustomSeed` (`00be13bb…`) | **0 次** | 同上 |
| `12abcdef` | **1 次** | 有 seed 概念，但只作为 DA 参数 |
| `TFDCipherAES / AESECB / AESCTR` | 有 | 属 FireDAC（数据库加密），与 NV 无关 |
| `uPndCrypto` / `TPndRsa` / `CryptoLib4Pascal` | 有 | RSA/哈希，用于授权与 seccfg，不是 NV |
| `/nvram/md/NVRAM/NVD_IMEI/LD0B_001` 等路径 | 明文 | NV 项表 |

消息表（UTF-16）还原出的完整流程：

```
Read security data...            (nvdata / protect1 / nvram)
NVDATA IMEI structure is incomplete. Restore it?  [YES][NO]
LD0B / MP0B / ST02               ← 三个 IMEI 载体
Check seccfg key...              → seccfg key validation failed
protect / INFO_FILE
Read security data... error (security data format not supported)
Repair crypto detection failed
Prepare IMEI [NVDATA]...
V1 write: %s
Verify IMEI...
Write IMEI [NVDATA]... 
Write IMEI [NVRAM]... skip (bad container) / not found
Write IMEI [OTP]...   Write IMEI [RPMB]...   Write IMEI [LG]...
LD0B IMEI1 invalid / LD0B IMEI1 encode failed
Update IMEI signature failed
```

并带有自己的 **ext4 写入器**（`C:\PND\FS\uMakeExt4.pas`、`EXT4 init/write/flush`），
用于在干净的 nvdata 里**新建** `md/NVRAM/NVD_IMEI` 结构和 `INFO_FILE`。

**Pandora 里没有任何可以离线算出密文的东西** —— 它把 `otp/seed/aeskey`
发给 DA，由 SEJ 完成。这就是"IMEI 解谜不难"的真正含义。

---

## 5. 加密 vs 签名（回答那个问题）

* **LD0B = 加密**。modem 必须能还原出 IMEI 才能 `AT+EGMR` 报出来；全盘搜索
  找不到 IMEI 的任何明文/BCD 形式，唯一来源是 LD0B ⇒ 只能是对称解密。
  条目呈 16 字节分组雪崩（改 IMEI 会改掉整 32 B），符合 AES 分组密码。
* **CERT 补丁 = 签名**。`11 1f 34 1e 31 fc` → `11 1f 01 d2 e0 db` 改的是
  `custom_nvram_check_imei` 的判定，是"绕过签名校验"，与加密无关。
  这条已在 `tools/patch_md1img.py` 里逐字节复现。
* **`IM03_001` 的尾标签不是密钥签名**（2026-10-18 实测更正）。
  LID 0x0545，2 条 0x20 字节记录，`itemsize = 0x18`，`attr = 0x0040`（无加密位）。
  记录尾部 8 字节 = `calc_checksum(rec[0:0x18], 0x18)`，即
  `MD5(rec[0:0x18])[0:8] XOR [8:16]` —— **与 LD0B 条目用的是同一个无密钥函数**：

      rec 40 00 00 00 16 00 01 00 3c 00 00 00 00 00 01 02
          31 0d 00 f2 f2 f2 f2 f2 | 7a 21 57 a6 9e 51 23 d4
                                    ↑ MD5 折叠，可离线重算

  ⇒ 「Update IMEI signature」这一步**不需要任何密钥**，可以离线重算。
  但记录内容里并不含 IMEI 文本，所以它是否属于 IMEI 修复链路仍待设备验证；
  至少可以排除"它需要 SEJ 才能更新"。
* 另外做了一次 KDF 组合爆破（6 684 个候选键：seed / aeskey / otp / LID /
  attr / header 的 1~3 元排列 × {md5,sha1,sha256,sha512,blake2s,blake2b}，
  外加以这些常量为密钥的 AES-ECB 与 AES-CMAC 派生），用与 IV 无关的判据
  检验 —— **0 命中**。基本可以关闭"密钥是这几个参数的简单函数"这条路。

---

## 6. 免费（GPLv3）实现路径

**不需要**破解密钥。用 mtkclient（GPLv3）驱动 DA，让手机自己加密：

```bash
# 1) 打 modem 补丁（本项目工具，已验证与 Pandora 逐字节一致）
python tools/patch_md1img.py <stock_md1img> <out_md1img>
#   或直接用 mtkclient
python mtk.py da patchmodem

# 2) 写 IMEI（DA 侧 SEJ 加密，等价于 Pandora 的"修复 IMEI"）
python mtk.py da imei --write "86xxxxxxxxxxx,86xxxxxxxxxxx"

# 3) 校验
python mtk.py da imei
```

前提：nvdata 里必须已经存在 `LD0B_001` 容器。官方 ROM 不自带 `nvdata.img`；
全字库里那张是**空 ext4**（只有 lost+found 和空 md），所以：

* 如果 nvdata 里已有 `md/NVRAM/NVD_IMEI/`（本机现在是有的）→ 直接执行第 2 步；
* 如果被完全擦空 → 需要先重建 ext4 结构（Pandora 用自研 ext4 写入器做的，
  mtkclient 目前没有）。可行的替代：把一张**已含容器**的 nvdata 镜像刷进去，
  再执行第 2 步。

**耐久性**：nvdata 是会被刷机覆盖的分区，IMEI 无法"烘进 ROM"——每次刷完
nvdata 都必须重新执行第 2 步。（这也是为什么卖家方案里 IMEI 不是随镜像发布的。）

---

## 7. 已排除的假设（避免重走）

| 假设 | 结论 |
|---|---|
| 密钥在 protect1 / nvdata / nvcfg / persist / proinfo / seccfg 里 | 全字节窗口扫描（含非对齐）+ 两种判据，0 命中 |
| 密钥在 md1img 里 | 1.8M 个 32 B 窗口（对齐）+ 全量，0 命中 |
| 密钥是 MTK 默认 / BLU / 三星种子 | 直接试、SST 派生试，均失败 |
| 密钥由 MEID / CPUID / UFS CID/SN 派生 | 76 种组合，失败 |
| LD0B 是 RC4 / 流密码 | 改 IMEI 会导致整块雪崩，排除 |
| LD0B 是纯签名、IMEI 存在别处 | 全分区搜不到 IMEI 明文/BCD，排除 |
| Pandora 内嵌密钥/算法 | 内存转储里没有 SEJ/SST 常量，排除 |
| OTP 存在 efuse 里（设备唯一） | OTP 来自 preloader，且本机为全 0 |

## 8. 工具与样本索引

```
tools/patch_md1img.py        md1img "Patch CERT"（GPLv3 交付物）
tools/scan_ld0b_seed.py      32 B seed 扫描（SST 口径）
tools/scan_ld0b_cbc.py       与 IV 无关的 AES 密钥扫描
tools/pe_inspect.py          PE 壳结构分析
tools/dump_process.py        进程内存转储
tools/pandora_strings.py     Pandora 字符串/数据库枚举
out/pandora_mem.bin          Pandora 脱壳内存（240 MB）
out/pandora_mem.u16.txt      UTF-16 字符串表
out/pandora/pd{,2,3}_LD0B_001.bin   三次 IMEI 写入样本
z3x_backup/…/Repair Flash_*/         Pandora 自己做的刷机前备份
```
