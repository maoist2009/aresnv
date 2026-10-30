#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""guided_repair.py -- interactive, guided IMEI repair for Xiaomi MediaTek phones.

A menu-driven front end around mtkclient.  No paths are hard-coded: first run
asks for your mtkclient directory, optional preloader and backup location, and
stores them in ~/.mtk_imei_repair.json.

Menu:
  1) device status check   (adb / root / radio state, no BROM needed)
  2) full backup           (BROM: NV set + both md1img slots -> timestamped dir)
  3) repair IMEI           (BROM: patch BOTH md1img slots + write IMEIs, one session)
  4) verify                (adb: *#06# cross-check, registration state, LD0B file)
  5) restore NV set        (BROM: write back the newest backup)
  6) settings              (change mtkclient path / preloader / backup dir)

Run inside BROM steps: unplug, power off completely, hold VOL+ and VOL-,
plug the cable and keep holding for a few seconds.  A failed handshake
(USBError) is normal -- just retry.
"""
import json
import os
import re
import subprocess
import sys

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".mtk_imei_repair.json")
DEFAULT_BACKUP_SUBDIR = "mtk_imei_backups"

BROM_HOWTO = (
    "  BROM mode: unplug cable -> power off completely -> hold VOL+ and VOL-\n"
    "  -> plug the cable, keep holding ~3-5 s.  A USBError/handshake failure is\n"
    "  normal on first tries; retry the same step 2-3 times."
)


# ----------------------------------------------------------------- utilities

def ask(prompt, default=None, validate=None):
    while True:
        s = input(prompt + (f" [{default}]" if default else "") + ": ").strip()
        if not s and default is not None:
            s = default
        if validate:
            msg = validate(s)
            if msg:
                print("  ! " + msg)
                continue
        return s


def luhn_fix(imei):
    """Return a Luhn-valid 15-digit IMEI built from the input."""
    digits = re.sub(r"\D", "", imei)
    if len(digits) < 15:
        raise ValueError("need at least 15 digits")
    digits = digits[:15]
    base, check = digits[:14], digits[14]
    total = 0
    for i, ch in enumerate(reversed(base)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    fixed = base + str((10 - total % 10) % 10)
    note = "" if fixed == digits else f"  (last digit adjusted for Luhn: {digits} -> {fixed})"
    return fixed, note


def run(cmd, cwd=None, stream=True):
    """Run a command; stream output live by default. Returns exit code."""
    print("  $ " + " ".join(cmd))
    try:
        p = subprocess.run(cmd, cwd=cwd)
        return p.returncode
    except FileNotFoundError as e:
        print(f"  ! not found: {e}")
        return 127


def run_mtk(cfg, args, stream=True):
    """Run mtk.py inside the configured mtkclient directory."""
    cmd = [sys.executable, "mtk.py"]
    if cfg.get("preloader"):
        cmd += ["--preloader", cfg["preloader"]]
    cmd += args
    return run(cmd, cwd=cfg["mtkclient"], stream=stream)


# ------------------------------------------------------------------- config

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    print(f"  config saved: {CONFIG_PATH}")


def validate_mtkclient(path):
    if not os.path.isdir(path):
        return "directory does not exist"
    if not os.path.isfile(os.path.join(path, "mtk.py")):
        return "mtk.py not found in that directory"
    return None


def setup_config(cfg, first=False):
    if first:
        print("First-time setup — values are stored in", CONFIG_PATH)
    cfg["mtkclient"] = ask(
        "  mtkclient directory", cfg.get("mtkclient"), validate_mtkclient)
    cfg["preloader"] = ask(
        "  preloader binary, optional but recommended (e.g. preloader_<codename>.bin)",
        cfg.get("preloader") or None,
        validate=lambda p: None if not p or os.path.isfile(p) else "file not found (leave empty to skip)")
    if not cfg.get("backup_dir"):
        cfg["backup_dir"] = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         DEFAULT_BACKUP_SUBDIR)
    cfg["backup_dir"] = ask("  backup directory", cfg["backup_dir"])
    os.makedirs(cfg["backup_dir"], exist_ok=True)
    save_config(cfg)


# ------------------------------------------------------------- device state

def adb(serial_args=()):
    return ["adb", *serial_args]


def menu_status(cfg):
    print("\n--- adb devices ---")
    run(adb() + ["devices"])
    print("\n--- identity / radio state (needs adb + root) ---")
    checks = [
        ("IMEI props", "getprop gsm.baseband.imei"),
        ("BL state", "getprop ro.boot.flash.locked; getprop ro.boot.verifiedbootstate"),
    ]
    for name, cmd in checks:
        print(f"  {name}:")
        run(adb() + ["shell", cmd])
    print("  registration / baseband version:")
    run(adb(("-d",)) + ["shell", "dumpsys telephony.registry | grep -iE 'mVoiceRegState|mBasebandVersion'"])
    print("  LD0B_001 file (needs root):")
    run(adb() + ["shell", "su -c 'ls -la /mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001 2>/dev/null'"])
    print("\n  Interpretation: mVoiceRegState 0 = in service (good), 1 = out of")
    print("  service, 3 = radio off.  Empty IMEI props + OUT_OF_SERVICE typically")
    print("  means the gate/NV chain is broken -> use menu 3.")


def latest_backup(cfg):
    root = cfg["backup_dir"]
    dirs = sorted((d for d in os.listdir(root)
                   if d.startswith("auto_") and os.path.isdir(os.path.join(root, d))),
                  reverse=True)
    return os.path.join(root, dirs[0]) if dirs else None


# -------------------------------------------------------------------- menu 2

def menu_backup(cfg):
    print("\n" + BROM_HOWTO)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(cfg["backup_dir"], "auto_" + ts)
    os.makedirs(dest, exist_ok=True)
    parts = ("nvdata,nvram,protect1,protect2,nvcfg,para,seccfg,proinfo,misc,"
             "md1img_a,md1img_b")
    print(f"  destination: {dest}")
    rc = run_mtk(cfg, ["r", parts, dest])
    print("\n  Backup " + ("DONE." if rc == 0 else f"exit code {rc} — check output above; retry if the handshake failed."))
    print("  These files are your rescue kit. Keep at least one copy off this disk.")


# -------------------------------------------------------------------- menu 3

def menu_repair(cfg):
    print("\n" + BROM_HOWTO)
    print("""
  PREREQUISITES / what this step does:
   * Patches BOTH md1img slots (modem gate bypass) and writes the IMEIs into
     nvdata with the phone's own crypto -- one BROM session, proven components.
   * If this device previously LOST its nvdata partition entirely: a donor/
     restored nvdata must be in place first -- automatic container rebuild is
     NOT supported yet (this tool would refuse to write into an empty ext4).
   * If the modem firmware was just flashed from an official ROM: fine, the
     gate patch is applied during this step.
   * If the patcher cannot find the gate patterns (unsupported firmware
     generation), the log will say so and nothing harmful is written.
   * Always run menu 2 (backup) first.""")
    if not latest_backup(cfg):
        print("  ! no backup found via menu 2 -- strongly recommended to abort and backup first.")
        if input("  continue anyway? [y/N]: ").strip().lower() != "y":
            return
    imei1 = ask("  IMEI1 (15 digits)", validate=lambda s: None if re.fullmatch(r"\d{15}", s) else "need exactly 15 digits")
    imei2 = ask("  IMEI2 (15 digits, empty = same as IMEI1)", "") or imei1
    imei1, n1 = luhn_fix(imei1)
    imei2, n2 = luhn_fix(imei2)
    print(f"  target: {imei1} / {imei2}" + n1 + n2)
    print("\n  entering BROM now — plug the cable when ready.\n")
    rc = run_mtk(cfg, ["da", "repair", f"{imei1},{imei2}"])
    print("\n  Repair " + ("DONE — boot the phone and run menu 4." if rc == 0 else f"exit code {rc}."))
    print("  Success markers in the log above: 'md1imga/b: patched.' and")
    print("  'IMEIs were written successfully'.")


# -------------------------------------------------------------------- menu 4

def menu_verify(cfg):
    print("\n  First dial *#06# on the phone and compare, then:")
    print("\n--- IMEI props ---")
    run(adb() + ["shell", "getprop gsm.baseband.imei"])
    print("\n--- registration / baseband version ---")
    run(adb() + ["shell", "dumpsys telephony.registry | grep -iE 'mVoiceRegState|mBasebandVersion'"])
    print("\n--- LD0B_001 file ---")
    run(adb() + ["shell", "su -c 'ls -la /mnt/vendor/nvdata/md/NVRAM/NVD_IMEI/LD0B_001'"])
    print("\n  mVoiceRegState 0 (IN_SERVICE) + correct IMEI = fully repaired.")
    print("  Correct IMEI but OUT_OF_SERVICE: identity accepted, check SIM/carrier.")


# -------------------------------------------------------------------- menu 5

def menu_restore(cfg):
    src = latest_backup(cfg)
    if not src:
        print("  ! no auto_* backup found in", cfg["backup_dir"])
        return
    print("  newest backup:", src)
    if input("  restore NV set from it? [y/N]: ").strip().lower() != "y":
        return
    print("\n" + BROM_HOWTO)
    for part in ("nvdata", "nvram", "protect1", "protect2", "nvcfg",
                 "para", "seccfg", "proinfo", "misc"):
        f = os.path.join(src, part + ".bin")
        if os.path.isfile(f):
            run_mtk(cfg, ["w", part, f])
    print("\n  Note: seccfg restore also restores the bootloader lock state.")
    print("  Reboot (power button) and dial *#06#.")


# --------------------------------------------------------------------- main

def main():
    cfg = load_config()
    if not cfg.get("mtkclient"):
        setup_config(cfg, first=True)
    while True:
        print("""
================ ares-nv guided repair ================
  1) device status check      (adb, no BROM)
  2) full backup              (BROM -- do this first)
  3) repair IMEI              (BROM -- patch slots + write identity)
  4) verify after repair      (adb)
  5) restore NV set           (BROM, from newest backup)
  6) settings                 (mtkclient / preloader / backup dir)
  0) quit""")
        choice = input("select> ").strip()
        try:
            if choice == "1":
                menu_status(cfg)
            elif choice == "2":
                menu_backup(cfg)
            elif choice == "3":
                menu_repair(cfg)
            elif choice == "4":
                menu_verify(cfg)
            elif choice == "5":
                menu_restore(cfg)
            elif choice == "6":
                setup_config(cfg)
            elif choice in ("0", "q", ""):
                return 0
            else:
                print("  ? unknown option")
        except KeyboardInterrupt:
            print("\n  interrupted")
        except Exception as exc:  # noqa: BLE001
            print(f"  ! error: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
