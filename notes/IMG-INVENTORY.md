# D 盘镜像文件盘点与归位记录

Date: 2026-10-23
权威哈希清单: `refs/IMG-SHA256.txt`（128 个 >1MiB 的 .img/.bin，全量 sha256）

## 一、按来源分类

### 1. 买来的 NV 包（donor 良好状态，sparse 镜像）— 恢复材料
`D:\apps\mtkclient\{nvdata,nvcfg,persist,protect1,protect2}.img` + `nvram.bin`
- **保留原地**（mtkclient 工作位置）。
- `analysis/raw/seller_*.bin`（Jul 27 2025）**就是这个包**，不是卖家实机转储——哈希与包内文件一致
  （`seller_nvdata.img` == `nvdata.img`，x4 同哈希）。
- 关键事实：包里的 `nvram.bin` 与本机 nvram 分区**逐字节相同** → "容器损坏"是包自带的，
  买包时就已经这样，Pandora 每次跳过 NVRAM 是同一原因。

### 2. 本机转储（我们的，按时间点）
- `backups/pre/` 修复前（坏状态）；`backups/post/*_WORKING` 修好后；
  `backups/mid/`、`bkp_head/` 各实验节点。
- `nvdata_WORKING.bin` == `nvdata_beforeLD0B.bin`（哈希相同）→ WORKING 快照即 Pandora 修复后、
  我们 LD0B 实验前的状态。
- `out/parts/`、`analysis/raw/`（非 seller 部分）各分区当前态。

### 3. Pandora 产物
- `out/pandora/`（para.bin、LD0B 条目、sdA/sdB）、`out/pandora_mem.bin`（内存转储）。
- `z3x_backup/.../Repair Flash_2026-10-17_10-41-05/` 第一次修复的会话备份。
- **`refs/pandora_repair_sessions/`（本次从 D:\temp\MTK 收入）**：共 7 次会话
  （10-17 16:15、10-18 10:47/11:21/11:42/11:57/12:11），每次 nvdata/nvram/protect1 三件套。
  每次 nvdata 哈希都不同 → **这是现成的 Pandora 操作时间线**，对第二道 gate 研究直接可用。
- `C:\Program Files (x86)\Pandora\Data\DA\MTK_AllInOne_DA.bin` — Pandora 自带 DA（原地保留）。

### 4. 工厂 eng 固件
`D:\apps\mtkclient\eng\{md1img,scp,audio_dsp}.img`（canonical）；
`refs/eng_extra/{preloader,spmfw,sspm}.img`（temp 收入的小件，eng 集里没有对应物）。

### 5. 官方 ROM / donor
`analysis/raw/md1img_stock_v12_5_3.raw`、`md1rom_stock.rom`、`md1img_*_donor.bin`、
`refs/ota/{boot,boot_b}.img`（从 `D:\temp\payload.bin` 2.6GiB OTA 提取；payload 原地保留）。
注意：`analysis/raw/md1img_a_now.bin` == `md1img_b_donor.bin` == `backup/stock_md1img_b.img`
（200MiB 定长转储，x3 同哈希）。

### 6. 我们的实验产物
`out/md1img_a_v3p2_patchcert*`、`out/md1img_b_gate_*`、`out/repro_*`、`out/lk_*_policy*.img`、
`tmp/rom_v3p2.bin`、`tools/_nvdata_pretool.bin`。

## 二、重复副本统计

128 个文件 → 89 个唯一哈希，39 个冗余副本，见 `refs/IMG-SHA256.txt`。
冗余副本集中在 `refs/dupes/`（确认无用后可整目录删除回收 ~1GB，暂保留作为移动留痕）。

## 三、本次移动记录（D:\temp → aresnv/refs/）

| 原位置 | 新位置 | 说明 |
|---|---|---|
| `D:\temp\MTK\Xiaomi_Redmi K40 Gaming (Ares)\Repair Flash_*` ×7 | `refs/pandora_repair_sessions/` | Pandora 会话备份 |
| `D:\temp\aresnv\*`（NV 包 6 文件 + README） | `refs/dupes/temp_aresnv_nvpack/` | 与 apps 包逐哈希相同 |
| `D:\temp\a\mtkclient\`（整目录） | `refs/dupes/temp_a_mtkclient/` | mtkclient 完整副本，Loader DA 哈希相同 |
| `D:\temp\{md1img,scp,audio_dsp}.img` | `refs/dupes/eng_dups/` | 与 eng/ 逐哈希相同 |
| `D:\temp\preloader_ares.bin` | `refs/dupes/eng_dups/` | 与 apps 版哈希相同（c18be398…） |
| `D:\temp\{preloader,spmfw,sspm}.img` | `refs/eng_extra/` | eng 集外小件 |
| `D:\temp\{boot,boot_b}.img` | `refs/ota/` | OTA 提取物 |

## 四、原地保留（有理由，勿清理）

- `D:\apps\mtkclient\` — 工具 + 恢复材料 + `backup/stock_*.img`（10 个 md 分区定长备份）
- `D:\temp\upd\dist_aresnv\` — Fragdown 分片分发包，manifest.json 哈希绑定路径，不可移动
- `D:\temp\payload.bin` — OTA 源包
- `D:\temp\mi8eu\`、`D:\temp\a\a` 等与本机无关的杂项未动

## 五、盘点顺带发现的研究线索

1. **nvram.bin 全程未变**（x14 同哈希：pre → 7 次 Pandora 会话 → post → 买包）→
   修复 IMEI 从不需要动 nvram，"容器损坏"是出厂/更早遗留，与本次故障无关。
2. `seller_para.bin`（cap_gear=4）来自买包 = donor 机的 para；Pandora 格后的 para（cap_gear=12）
   才是本机自己的。此前笔记把 seller_para 当"卖家修好那台"表述需按此理解。
3. 7 次 Pandora 会话的 nvdata 各不相同 → 逐会话 diff 即 Pandora 对 nvdata 的完整操作序列，
   可与 `pandora_messages.md` 的日志对齐。

## 六、2026-10-24 清理记录（D 盘 100% 满 → 3.8G 可用）

已删除（删除前逐对 cmp 验证同哈希）：
- `refs/dupes/`（temp 收纳的重复副本，273M）
- `bkp_head/{md1img_b_gate,nvdata_mid,nvdata_pre,nvram_pre,protect1_pre}.bin`
  （分别 == `out/md1img_b_gate_raw.bin`、`backups/mid/nvdata_mid.bin`、`backups/pre/*`）
- `out/repro_from_stockP25.bin`（== `out/repro_P25.bin`）
- `out/lk_b_revert.img`（== `analysis/raw/lk_b.img`）
- `D:\temp\payload.bin`（2.6G OTA，可重新下载；boot/md1img 已提取至 refs/ota）
- `out/exp_inert.bin`（200M 惰性测试产物）

移出：`out/pandora_mem.bin` → `F:\tmp\`（230M，Pandora 内存转储证据；字符串衍生
`pandora_mem.u16.txt` 等仍在 out/）。
恢复材料位置：`C:\Users\<user>\ares_rescue\`（原始 LD0B_001 + 活状态 nvdata.img）。

## 七、2026-10-24 第二轮清理（D 3.8G → 5.1G 可用）

删除（全部可再生或已被通用补丁器取代）：
- F:/tmp 三个补丁验证产物（480M，`tools/patch_md1img_generic.py` 一分钟重生成）
- `out/md1img_{a_v3p2_patchcert,_fixed,b_gate_raw,b_gate_ok,repro_V3P2,repro_P51}.bin`
  （~865M 旧实验构建；配方已模式化并三重验证，`repro_P25.bin` 保留作历史真值）
- `out/nvdata_rom.img`（官方 ROM 空 ext4，raw 目录有副本）
- `backups/snap_20261024/nvdata_pass2.img`（双读稳定性校验的重复）
- `tmp/`（129M 中间产物）

保留的状态证据：两份全天快照（snap_20261024 + _working 含 md1img a/b）、
backups/{pre,mid,post}、analysis/raw、out/parts、out/pandora（含 sdA/sdB）、
z3x_backup、refs/pandora_repair_sessions、F:/tmp/pandora_mem.bin。
