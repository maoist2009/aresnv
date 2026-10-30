# NV 分区恢复记录 (2026-10-17)

## 背景

用户此前（按卖家教程）用 mtkclient 把买来的 NV 包原样写入分区。**mtkclient `w` 不会展开 Android sparse 镜像**
(`Library/DA/xflash/xflash_lib.py:835` 直接读文件原始字节)，所以多个分区里躺着的是稀疏镜像文件本身，
而不是它展开后的 ext4 文件系统。

### 恢复前的分区状态（实测首 4KiB 魔数）

| 分区 | 块设备 | 恢复前内容 | 判定 |
|---|---|---|---|
| `nvdata` | sdc6 | ext4 (inode **512**) | 运行时重建的 FS，`md/` 空 |
| `nvcfg` | sdc5 | ext4 (inode **512**) | 运行时重建，与买来的不一致 |
| `nvram` | sdc40 | 全 0 | 与买来的 `nvram.bin` 相同（本来就全 0）|
| `persist` | sdc14 | `3aff26ed` sparse | ❌ 裸写稀疏镜像，**无法挂载** |
| `protect1` | sdc15 | `3aff26ed` sparse | ❌ 裸写稀疏镜像，**无法挂载** |
| `protect2` | sdc16 | `3aff26ed` sparse | ❌ 裸写稀疏镜像，**无法挂载** |
| `proinfo` | — | 首 4KiB 全 0 | 待查 |
| `seccfg` | — | `MMMM\x04` | ✅ 正常 |

## Pandora 报错的根因

Pandora v10.3.2 的三次报错是同一条链路上的三个不同阶段：

| 报错 | 含义 |
|---|---|
| `error (EXT4 init failed)` | 分区里是**未展开的稀疏镜像**，根本不是 ext4 |
| `error (NVDATA parent directory not found)` | ext4 有效，但 `md/` 为空（没有 `md/NVRAM/`）|
| `error (NVDATA parent SELinux metadata unavailable)` | ext4 有效、目录也在，但**读不到父目录的 SELinux xattr** |

最后一条的根因（本次用 `tools/ext4x.py` 离线验证确定）：

```
工厂镜像 nvdata.raw      : inode_size=128  md/NVRAM ino=25 file_acl=1551  -> security.selinux 存在【外部 xattr 块】
设备重建 nvdata_mid.bin  : inode_size=512  md/NVRAM ino=23 file_acl=0     -> security.selinux 存在【inode 内联】
```

- 工厂 ext4：`inode_size = 128`，xattr 只能放**外部 xattr 块**，由 `i_file_acl` 指向。
- 运行时重建的 ext4：`inode_size = 512`，xattr **内联**在 inode 尾部（`i_extra_isize = 32`），`i_file_acl = 0`。

Pandora 的 ext4 解析器是按工厂布局写的：它只通过 `i_file_acl` 找 xattr。设备重建的 FS 里
`i_file_acl = 0`，于是"父目录的 SELinux 元数据不可用" → 无法给要创建的文件盖上
`u:object_r:nvdata_file:s0` 标签 → `修复 IMEI 文件创建失败`。

另外 `Languages/ZHO.json` 里能看到工具的工作流字符串：
`Patch CERT [NVDATA]...`、`Write IMEI [NVDATA]...`、`Update IMEI signature failed`、
`Write IMEI1 item failed`、`Write IMEI2 item failed`、`NVDATA IMEI structure is incomplete. Restore it?`

## 恢复方法（不需要 BROM！）

之前认为必须进 BROM 才能写这些分区，实测**不需要**：`fastboot flash nvdata` 被 bootloader
写保护（`Partition is write protected`），但可以在系统内完成：

```sh
setenforce 0                      # adb root 之后可用，Enforcing 下 umount 会 EPERM
umount /mnt/vendor/nvdata         # 关键：先卸载，否则内核会回写脏元数据覆盖我们写的内容
umount /mnt/vendor/nvcfg
dd if=<展开后的 raw> of=/dev/block/by-name/<分区> bs=1048576
sync
md5sum /dev/block/by-name/<分区>   # 与本地 raw 校验
```

写回并校验的文件：

| 分区 | 写入源 | md5 |
|---|---|---|
| `nvdata` | `analysis/raw/nvdata.raw` | `5902febe19d94b2931557492b239afdb` |
| `nvcfg` | `analysis/raw/nvcfg.raw` | `3f8e368b6902b5d79c1c4a2f7c624e72` |
| `persist` | `analysis/raw/persist.raw` | `55f0ec94378f380ba44ca9a51a7e3041` |
| `protect1` | `analysis/raw/protect1.raw` | `74782f332c6c97f0229b936e8d56325c` |
| `protect2` | `analysis/raw/protect2.raw` | `3149370bed92f079033128dd34eb795f` |

展开后的尺寸与分区尺寸完全一致：
nvdata 67108864 / nvcfg 33554432 / persist 69697536 / protect1 8388608 / protect2 8388608。

## 恢复后状态

- 五个分区全部是合法 ext4 并成功挂载：
  `nvdata`→sdc6、`nvcfg`→sdc5、`persist`→sdc14、`protect1`→sdc15(`/mnt/vendor/protect_f`)、`protect2`→sdc16(`/mnt/vendor/protect_s`)
- `nvdata` 为工厂布局：`inode_size=128`，`md/NVRAM/{NVD_IMEI,NVD_DATA,NVD_CORE,BACKUP,CALIBRAT,INFO_FILE}` 齐全，
  `md/NVRAM/NVD_IMEI/{NV01A000,NV01B000,NV0S_000}` 存在，`security.selinux` 位于**外部块 1551** ✅
- `persist` 从"无法挂载"变成正常挂载
- **基带仍未起来**：`gsm.version.baseband` 为空；dmesg 里 `ccci_mdinit` 正常退出（status 0），
  但 radio 侧报
  `Could not find android.hardware.radio.modem.IRadioModem/slot1 in the VINTF manifest`
  —— 这是 **ROM/HAL 侧**的问题，与 NV 数据无关（用户跑的是 Android 16 类原生 ROM）。

## 工具/脚本

- `tools/ext4x.py` — 离线 ext4 检查器：superblock、路径查找、inode 字段、xattr（内联 vs 外部块）。
  ```sh
  python tools/ext4x.py info <image>
  python tools/ext4x.py path <image> /md /md/NVRAM /md/NVRAM/NVD_IMEI
  ```
- `tools/simg2img.py` — Android sparse → raw 展开。
- `tools/dev_status.sh` — 设备端状态探测（属性/挂载/nvdata 树/dmesg）。
