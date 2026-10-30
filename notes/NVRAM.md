# MTK NVRAM / 基带机制笔记（ares 项目）

## 分区职责（来自 MTK 平台资料）

| 分区 | 作用 | 文件系统 / 内容 |
| --- | --- | --- |
| `nvdata` | **运行时读写的主 NV 数据**：IMEI、barcode、校准、RF 参数等 | ext4，挂载 `/mnt/vendor/nvdata` |
| `nvram` | **备份分区**：备份 `NVRAM_CATEGORY_IMPORTANT` + `NVRAM_CATEGORY_CALIBRAT` 的 NV → 即 `CALIBRAT/` 与 `NVD_IMEI/` 两个目录 | ext4 / 裸（本包中是全零） |
| `protect1` (`protect_f`) | `NVRAM_CATEGORY_IMPORTANT_L4` 的 NV（SIMLOCK 相关），"A 文件" | ext4，`md/` |
| `protect2` (`protect_s`) | protect_f 中部分数据的备份（MULTIPLE 属性的 "B 文件"） | ext4，`md/` |

A/B 文件互为备份；一个损坏可由另一个修复；两者都坏时由 modem 决策。

## 关键机制：nvdata 被擦除后会发生什么

MTK 平台（SP Flash Tool "Firmware Upgrade" 行为）：

- 只擦除 `nvdata`。
- **开机时 AP（Android 侧）会把 `nvram` 分区里备份的 `CALIBRAT` 和 `NVD_IMEI` 两个目录还原到 `nvdata`。**
  → 这就是"内核读取转化给 CP"的具体所指：由 AP 侧从 `nvram` 还原，再交给 modem(CP)。
- 若 `nvdata` 为空 **且 `nvram` 也没备份** → IMEI/barcode/校准/RF 参数按 code 里的**默认值**生成新文件。

因此修基带的常见做法：

1. **擦除 `nvdata`（+ `nvram`）**，让设备进入 "NV data is corrupted" 状态（旧数据/旧校验不再干扰）；
2. 写入**正确的 NV 源**：
   - 官方做法：从 `nvram` 还原；或
   - 自制/第三方：直接写一份可用的 `nvdata`（+ `nvcfg`/`persist`/`protect`）。
3. 顺序有讲究：先写 `nvram` 再写 `nvdata`，因为 `nvram` 里有指向 `nvdata` 的校验信息。

## NVRAM "LID" 命名

每个 NV 项 = 一个文件：`<4字符前缀><3位版本号>`，例如 `LD0B_001`、`UL10_000`、`ST33A004`。
前缀来自 NVRAM LID table 的 fileprefix，版本号是 `VERNO`。

- 本地包里的文件：`md/NVRAM/NVD_IMEI/{NV01A000,NV01B000,NV0S_000}`、
  `md/NVRAM/CALIBRAT/{UL10_000,UL11_001,...,HL1A_000,...}`（共 125 个）。

## NVRAM 文件二进制头

- 4 字节 magic `4C 44 49 00`（"LDI\0"）。
- 之后 4 字节是 **格式/版本常量**，同一文件族内固定：
  - `LD0B_001`（MT67xx，community 已逆向）→ `10 EF 0A 00`
  - 本项目 `NV01A000` → `06 F0 01 00`（**不同族/版本**）

## IMEI 记录格式（MT67xx，community 已完全逆向）

来源：`alltechdev/mtk-imei-switcheroo`（**GPL-3.0**）

`LD0B_001` = 384 字节：

```
0x000   8   LDI\0 + 10 EF 0A 00
0x008  56   固定头（modem 元数据）
0x040  32   加密 IMEI slot1（AES-128-ECB，2 个 AES 块）
0x060  32   加密 IMEI slot2
0x080 256   填充
```

加密用的是 **AES-128-ECB**，key = `3f06bd14d45fa985dd027410f0214d22`
（由 MTK 标准 `SST_Get_NVRAM_SW_Key` 从固定 seed 派生，MT67xx 通用）。

明文 32 字节：

```
[0x00:0x08]  8   BCD 交换半字节编码的 15 位 IMEI（低半字节在前）
[0x08:0x0A]  2   填充（参与校验）
[0x0A:0x12]  8   MD5-XOR 校验：MD5(pt[0:10])，再把 16 字节摘要前后 8 字节异或
[0x12:0x20] 14   零填充
```

modem 读取时用同一 key 解密，重算 MD5-XOR 校验并比对，通过才使用该 IMEI。

### 本项目实测

用上面的标准 key 对本包 `NVD_IMEI/*` 各偏移做 AES-ECB 解密 → **得不到 BCD IMEI**（输出高熵）。
结论：ares(MT6893) **要么 key 不同（可能有 per-device/per-SoC 派生），要么记录布局不同**。
→ 需要拿到真机当前 NV（擦除态）与实际写入后的 NV 做对比才能确定。

## 现成的免费/GPL 先例（重要）

| 仓库 | 许可 | 说明 |
| --- | --- | --- |
| `alltechdev/mtk-imei-switcheroo` | **GPL-3.0** | 读写 NVRAM 里的 IMEI / WiFi-BT MAC；含 rooted 设备的 live patch 脚本；含 biloba(mt6768) 的 modem/LK patcher |
| `timjosten/mtk_imei` | **GPL-3.0** | 重建 NVRAM 分区，生成 TWRP 可刷 zip；用 `md_patcher.ko` 运行时 patch modem |

注意：这些针对 MT67xx(Helio G)。ares 是 MT6893，且有 **签名校验**（biloba 文档提到"Biloba adds a signed
critical-data check"）——这很可能是"没有免费工具"的真正原因。
