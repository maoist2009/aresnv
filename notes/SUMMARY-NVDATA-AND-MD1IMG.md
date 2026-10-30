# 总结：nvdata 的结构、我们对它做过的每一步、以及 md1img 补丁原理

项目：小米 Redmi K40 游戏增强版（ares，MT6893/天玑1200）基带/IMEI 修复的完全免费实现
日期：2026-10-24
状态：NV 侧端到端实测通过；md1img 补丁模式化并三重验证；全部证据在本仓库内

---

## 0. 一段话结论

IMEI 修复 = **两半缺一不可（"双向奔赴"）**：
① **NV 侧**——把加密后的 IMEI 身份写进 nvdata 的 LD0B 条目（密钥在芯片里，加密必须在手机上完成）；
② **modem 侧**——md1img 里两段 6 字节指令构成 IMEI 校验门禁（`custom_nvram_check_imei`，报错文案
"fingerprint + pool anchor both failed"），不打补丁，NV 写得再对 modem 也不报。
两侧都没有任何秘密密钥参与；付费工具（Pandora）的全部秘密就是这两步的配方。

---

## 1. nvdata 分区结构

64 MiB **ext4**（superblock magic `0xEF53`），挂载点 `/mnt/vendor/nvdata`。
注意：它不是 userdata，也不是传统 NVRAM 数据库（那是另一个 64 MiB 的 `nvram` 分区，
本机出厂即"容器损坏"，全程从未被任何工具修改——14 份跨时间快照逐字节相同，见 §4）。

```
nvdata (ext4)
├── md/NVRAM/
│   ├── INFO_FILE            1884 B   "INFO" 头 + 表
│   ├── NVD_IMEI/                     ← IMEI 相关条目全在这
│   │   ├── FILELIST        45 B    纯文件名列表：NV01A000\0NV01B000\0NV0S_000\0LD0B_001\0FILELIST\0
│   │   ├── LD0B_001       384 B    ★ 主条目：64 B 头 + 10×32 B 条目（见 §2）
│   │   ├── NV01A000        96 B    传统 IMEI 项（"LDI" magic，LID 0xF006）
│   │   ├── NV01B000        96 B    与 NV01A000 载荷相同（双卡）
│   │   └── NV0S_000       144 B
│   ├── NVD_DATA/                    220 个数据项（含 IM03_001，见下）
│   │   └── IM03_001       128 B    modem 每次开机重写；尾部是**无密钥**校验和
│   │                                 （MD5 折叠，同 LD0B 条目算法），不是 MAC；
│   │                                 载荷不含 IMEI 明文。死/活状态逐字节相同
│   ├── CALIBRAT/                    125 个校准项（UL*/HL*...）
│   ├── NVD_CORE/  BACKUP/           空
├── APCFG/APRDCL/  (FILE_VER, AUXADC, MD_SBP...)
├── APCFG/APRDEB/  (BT_Addr, WIFI, WIFI_CUSTOM, GPS)
├── md3/  md_cmn/
```

所有小文件共享 "LDI\0" 头族。以 NV01A000 为例（真实字节）：

```
4c 44 49 00  06 f0 01 00  10 00 00 00  ae 60 00 00   magic | LID=0xF006 | items=1 | size=0x10 | attr=0x60AE
00 24 00 00  ...                     5e 44   校验
00 00 f4 02 01 00 ...                        计数器/时间类字段（死活状态仅此字节组微变）
0x40 起：载荷（加密/哈希状，无 IMEI 明文）
```

### 兄弟分区（同一安全链）

| 分区 | 大小 | 内容 | 角色 |
|---|---|---|---|
| nvram | 64 MiB | NVRAM 旧容器 | **出厂即坏，全程无人碰，与 IMEI 修复无关** |
| protect1/2 | 8 MiB ×2 | ext4，`md/` 下 ER1D_002、LD40_001、LD81..97、MC00..06、MT00A/B、SL00/01、ST33A/B、ST34A/B、ST36/37/38 | modem NV，互为备份 |
| nvcfg | 32 MiB | sensor/相机/GPS 校准 | 与 IMEI 无关但随套件备份 |
| persist | 66.5 MiB | key-value（data/0..32） | 同上 |
| seccfg | 8 MiB | BL 锁状态 | 本机被改回"锁定"（假锁） |
| otp / efuse | 48 MiB / 0.5 MiB | 芯片熔丝/校准 | 只读 |

**密钥模型（源码级钉死）**：LD0B 条目由 SoC 的 **SEJ 引擎**加密，会话密钥从芯片
**HUK（硬件唯一密钥，熔在 SoC 里）**派生——上游公开源码 `shomykohai/mtk-payloads`
（`sej.c`: `AES_HW_KEY → BK2C "Bind HUK"`；`sej_hk.c`: `SEJ_V3_init`）。因此：
**PC 离线生成密文原理上不可能**；合法路径只有让 DA 驱动手机自算。
6 684 个离线 KDF 候选 + 上百万窗口密钥扫描全部 0 命中（负结果清单见 STATE.md §5）。

---

## 2. LD0B_001 条目格式（本项目的核心格式成果）

**头（64 字节，写入时原样保留旧头）**：

```
4c 44 49 00  10 ef 0a 00  0a 00 00 00  2a 40 00 00   "LDI\0" | LID=0xEF10 | items=0x0A | itemsize=0x20 | attr=0x402A
00 20 00 00  ...                     c2 44           ...
...                                     01 00 00 00
```

- `attr = 0x402A`：bit5 = **HW_ENCRYPTED_5G**（SEJ 硬件加密），bit3 = SW 位（未用）
- 条目区：10 × 0x20 字节，`entry[0]=IMEI1，entry[1]=IMEI2，entry[2..9]=空`

**每条 0x20 字节**：

| 偏移 | 长度 | 内容 |
|---|---|---|
| 0x00 | 8 | 打包 IMEI：nibble 交换的 BCD，15 位数字，'F' 填充 |
| 0x08 | 2 | 零 |
| 0x0A | 8 | 校验和 = `MD5(data[0:0x0A])` 折叠（`h[i] ^= h[i+8], i=0..7`），**无密钥，可离线重算** |
| 0x12 | 14 | 零 |

空条目 = `0xFF*10 + checksum(0xFF*10) + 0x00*14`。
IMEI 本身建议 Luhn 合法（第 15 位校验码）——modem 有理由拒绝非法值。

**实测证据（2026-10-24 离谱 IMEI 实验）**：写入
`111111111111119` / `114514191981029` 后，设备上 LD0B_001 密文由
`7b5d2942…` 变为 `6d4e3f12…`（头部逐字节未动）——同一明文每次加密产生相同密文，
即 **NV 内容是 (IMEI, HUK) 的确定性函数**。`*#06#` 现场报出两个离谱值 =
NV 侧端到端打通。证据：`analysis/absurd_test/`。

---

## 3. 我们对 nvdata 做过的每一步（操作史 + 字节证据）

| # | 时间 | 操作 | 结果/证据 |
|---|---|---|---|
| 1 | 起始 | 设备 nvdata 分区**整个丢失**（故障起点） | 无基带、无 IMEI |
| 2 | 10-17 | 写入买来的 NV 包（donor 良好状态：nvdata/nvcfg/persist/protect1/protect2；`seller_*.bin` 即该包） | 容器回来了 |
| 3 | 10-17 | Pandora 修复：写 LD0B_001+FILELIST+NV01A/B（23:46）、打 md1img 补丁、格 para | 首次失败（活动槽没补丁），后多次成功——A/B 槽轮盘 |
| 4 | 10-18 | 把设备自己的合法 LD0B 密文写回 → **IMEI 仍死** | 关键反例 → 推出"第二道 gate 在别处" |
| 5 | 10-24 00:19 | 死状态全量快照（28 分区，sha256 双端验证） | `backups/snap_20261024/` |
| 6 | 10-24 | Pandora 再修成功，活状态全量快照（31 分区含 md1img a/b） | `backups/snap_20261024_working/` |
| 7 | 10-24 | **死↔活对照：27 个 NV/安全分区逐字节相同** | IM03_001 过期签名假设死亡；gate 不在任何 NV 分区 |
| 8 | 10-24 | `mtk da imei --write` 写离谱 IMEI → `*#06#` 验证 | **NV 侧端到端打通（免费工具）** |
| 9 | 10-24 | 从 C 盘救援包恢复原始 LD0B（哈希 `5b66453d…` 验证一致）+ 重启 | `*#06#` 回到 86xxxxxxxxxxx/496 |

对 nvdata 的全部合法操作模式（免费实现）：

```bash
# 读（快照/比对）
python mtk.py r nvdata out_dir
# 写 IMEI（一条龙：读分区→扫 LD0B magic→编码→设备端 SEJ 加密→原头保留→整分区写回）
python mtk.py --preloader preloader_ares.bin da imei --write "<IMEI1>,<IMEI2>"
```

`da imei --write` 的关键性质：**模型无关**（magic 扫描，不硬编码偏移）、**确定性**
（同 IMEI 重写产生相同字节）、**卸载状态写入**（BROM/DA 下分区未挂载，干净）。

---

## 4. md1img：结构、门禁、补丁

### 4.1 结构

md1img_a/b 各 200 MiB（定长分区，实际镜像 ~65 MiB 起），内含 **md1rom**（modem
程序本体）、tinysys、hifi3 等段。两槽独立——**活动槽决定一切**（A/B 槽轮盘：
10-17 首次修复失败 = 补丁写进了一个槽而系统从另一个槽启动）。

### 4.2 门禁机制

modem 内部有小米定制的 `custom_nvram_check_imei`（错误文案
`"fingerprint + pool anchor both failed"`）。它对 NV 数据与 modem 侧锚点做一致性
校验；不通过则**拒绝报出 IMEI**——哪怕 NV 完全合法（§3 操作 #4 的反例）。

### 4.3 补丁（跨版本稳定，偏移会漂移，模式不变）

```
site1  原始 11 1f 34 1e 31 fc   →  补丁 11 1f 01 d2 e0 db
site2  原始 11 1f 33 1e c0 00   →  补丁 11 1f 01 d2 e0 db
```

- `111f` 为共享指令前缀，尾部即绕过本体；
- 每个模式在每个镜像中**恰好出现 1 次**（已验证 stock V12.5.3 / V14.0.5 / 中间版本）；
- 站点偏移跨版本漂移（0x22330a ↔ 0x22b84a），故用**模式扫描**而非硬编码偏移；
- 死↔活对照中，A/B diff 的前两个区间就是这两处（0x22330c-0f、0x223b6c-6f，各 4 字节）。

**三重离线验证**（`tools/patch_md1img_generic.py`）：
1. patch(working_b，V14 未打补丁基座) 两站点字节 == 正在工作的 working_a；
2. patch(stock V12.5.3) == repro_P25（历史 Pandora 输出逐字节复现）；
3. patch(a_now，另一版本) 唯一命中、干净打上。

### 4.4 RSA 模幂（CSSD 信任根，可选）

md1img 内嵌小米工厂 RSA-2048 公钥（modulus 见 `mtk_crypto.py`）。对需要 CSSD
设备密钥链的机型，可将其替换为自生成公钥（`--keyswap`）。**ares 实测不需要**：
活状态的 CSSD 块未被改动，IMEI 照常工作。

### 4.5 免费操作

```bash
python mtk.py --preloader preloader_ares.bin da patchmodem   # 读活动槽→模式补丁→写回
# 建议两个槽都打（或切槽后各打一次），根除 A/B 轮盘
```

---

## 5. 最终免费配方（GPLv3，全流程无付费组件）

```
1. mtk.py --preloader <preloader> da patchmodem          # ① modem 门禁绕过
2. mtk.py da imei --write "<IMEI1>,<IMEI2>"              # ② NV 身份写入（设备端加密）
3. 重启 → *#06# 验证
```

已知边界：
- BROM 利用依赖 mtkclient 各 hwcode payload（6893 已证；6891/6877/6853 上游支持）；
- 若某代固件两段指令变化 → 往 `patch_md1img_generic.py` 的 PATCHES 表加模式；
- nvdata 被彻底清空的设备需先重建 LD0B 容器（ext4 写入器，mtkclient 尚缺，罕见场景）。

## 6. 证据索引

| 证据 | 位置 |
|---|---|
| 死/活双快照（含 md1img） | `backups/snap_20261024{,_working}/`（sha256 双端验证） |
| 离谱 IMEI 实验现场 | `analysis/absurd_test/`、`out/imei_write.log` |
| A/B diff（配方提取） | 本文档 §4.3，原始镜像在快照内 |
| Pandora 7 次会话备份 | `refs/pandora_repair_sessions/` |
| 历史逐字节复现真值 | `out/repro_P25.bin` |
| 格式实现 | `tools/imei_ld0b.py`、`tools/patch_md1img_generic.py`、`mtkclient mtk_crypto.py` |
| 全部中间结论与负结果 | `notes/STATE.md`（追加式日志，勿重写） |
